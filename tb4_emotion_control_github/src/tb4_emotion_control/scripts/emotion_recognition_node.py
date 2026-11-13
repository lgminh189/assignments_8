#!/usr/bin/env python3
"""Show a smooth webcam preview while DeepFace infers emotion in a worker thread."""
import os
import threading
from collections import deque

import cv2
import rclpy
from rclpy.clock import Clock, ClockType
from rclpy.node import Node
from rclpy.signals import SignalHandlerOptions
from std_msgs.msg import String


class EmotionRecognitionNode(Node):
    def __init__(self):
        super().__init__('emotion_recognition_node')
        self.declare_parameter('camera_index', 0)
        self.declare_parameter('show_window', True)
        self.declare_parameter('frame_rate', 2.0)  # AI inference rate
        self.declare_parameter('display_rate', 30.0)
        self.declare_parameter('confidence', 0.32)
        self.declare_parameter('emotion_margin', 0.04)
        self.declare_parameter('happy_surprise_margin', 0.15)
        self.declare_parameter('smoothing_window', 3)
        self.declare_parameter('detector_backend', 'opencv')
        self.declare_parameter('min_face_size', 60)
        p = lambda name: self.get_parameter(name).value
        self.show = p('show_window')
        self.rate = float(p('frame_rate'))
        self.display_rate = float(p('display_rate'))
        self.threshold = float(p('confidence'))
        self.emotion_margin = float(p('emotion_margin'))
        self.happy_surprise_margin = float(p('happy_surprise_margin'))
        self.smoothing_window = int(p('smoothing_window'))
        self.detector_backend = str(p('detector_backend')).lower()
        self.min_face_size = int(p('min_face_size'))
        if not 0.5 <= self.rate <= 10:
            raise ValueError('frame_rate must be in [0.5, 10]')
        if not 10 <= self.display_rate <= 60:
            raise ValueError('display_rate must be in [10, 60]')
        if not 0 < self.threshold <= 1:
            raise ValueError('confidence must be in (0, 1]')
        if not 0 <= self.emotion_margin <= 1 or not 0 <= self.happy_surprise_margin <= 1:
            raise ValueError('emotion margins must be in [0, 1]')
        if not 1 <= self.smoothing_window <= 9:
            raise ValueError('smoothing_window must be in [1, 9]')
        if self.detector_backend not in {'retinaface', 'opencv'}:
            raise ValueError('detector_backend must be retinaface or opencv')

        # Keep CPU inference from taking all cores away from camera preview.
        os.environ.setdefault('TF_NUM_INTRAOP_THREADS', '2')
        os.environ.setdefault('TF_NUM_INTEROP_THREADS', '1')
        cv2.setNumThreads(1)
        # Lazy import keeps TensorFlow out of the behavior controller process.
        from deepface import DeepFace
        self.deepface = DeepFace
        self.score_history = deque(maxlen=self.smoothing_window)

        self.publisher = self.create_publisher(String, '/detected_emotion', 1)
        self.capture = cv2.VideoCapture(p('camera_index'), cv2.CAP_V4L2)
        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not self.capture.isOpened():
            self.capture.release()
            raise RuntimeError('Cannot open webcam; check camera_index and permissions')

        self.frame_lock = threading.Lock()
        self.result_lock = threading.Lock()
        self.latest_frame = None
        self.result = ('No_Face', 0.0, None, 'H:--  S:--')
        self.result_version = 0
        self.published_version = -1
        self.stop_worker = threading.Event()
        self.last_inference_error = None
        self.last_logged_label = None
        self.closed = False
        self.create_timer(1.0 / self.display_rate, self.on_frame,
                          clock=Clock(clock_type=ClockType.STEADY_TIME))
        self.inference_thread = threading.Thread(
            target=self.inference_loop, name='emotion-inference', daemon=True)
        self.inference_thread.start()
        self.get_logger().info(
            f'Webcam ready; detector={self.detector_backend}, '
            f'display={self.display_rate:g} FPS, AI≤{self.rate:g} FPS.')

    def infer_emotion(self, frame):
        try:
            faces = self.deepface.analyze(
                img_path=frame, actions=['emotion'], enforce_detection=True,
                detector_backend=self.detector_backend, expand_percentage=5, silent=True)
        except ValueError as exc:
            # In non-enforced mode DeepFace may classify the whole frame when
            # detection fails, creating plausible-looking false labels.
            if 'face could not be detected' in str(exc).lower():
                return None
            raise
        if isinstance(faces, dict):
            faces = [faces]
        # Use the largest face to avoid reacting to small background faces.
        face = max(faces, key=lambda item: item.get('region', {}).get('w', 0)
                   * item.get('region', {}).get('h', 0), default=None)
        if not face or face.get('region', {}).get('w', 0) < self.min_face_size:
            return None
        emotions = face.get('emotion', {})
        if not emotions:
            return None
        scores = {name.lower(): float(value) / 100.0 for name, value in emotions.items()}
        region = face.get('region', {})
        box = tuple(int(region.get(k, 0)) for k in ('x', 'y', 'w', 'h'))
        return scores, box

    def classify_scores(self, scores):
        self.score_history.append(scores)
        names = set().union(*(sample.keys() for sample in self.score_history))
        averaged = {name: sum(sample.get(name, 0.0) for sample in self.score_history)
                    / len(self.score_history) for name in names}
        ranked = sorted(averaged.items(), key=lambda item: item[1], reverse=True)
        best, score = ranked[0]
        second_name, second_score = ranked[1]
        margin = score - second_score
        label = best.capitalize()
        # Require two observations before issuing a command, then reject ambiguous
        # distributions. In particular, a close Happy/Surprise score should stop.
        pair = frozenset((best, second_name))
        pair_margins = {
            frozenset(('happy', 'surprise')): self.happy_surprise_margin,
            frozenset(('fear', 'surprise')): 0.12,
            frozenset(('sad', 'angry')): 0.08,
        }
        required_margin = pair_margins.get(pair, self.emotion_margin)
        if len(self.score_history) < min(2, self.smoothing_window):
            label = 'Uncertain'
        elif score < self.threshold or margin < required_margin:
            label = 'Uncertain'
        diagnostic = (
            f'H:{averaged.get("happy", 0):.0%} S:{averaged.get("surprise", 0):.0%} '
            f'F:{averaged.get("fear", 0):.0%} A:{averaged.get("angry", 0):.0%}\n'
            f'Sad:{averaged.get("sad", 0):.0%} N:{averaged.get("neutral", 0):.0%} '
            f'D:{averaged.get("disgust", 0):.0%}\n'
            f'{best}/{second_name} Δ:{margin:.0%} (cần {required_margin:.0%})')
        return label, score, diagnostic

    def inference_loop(self):
        """Analyze a copy of the newest frame without blocking webcam display."""
        while not self.stop_worker.is_set():
            with self.frame_lock:
                frame = None if self.latest_frame is None else self.latest_frame.copy()
            if frame is None:
                self.stop_worker.wait(0.05)
                continue
            try:
                detection = self.infer_emotion(frame)
                self.last_inference_error = None
                if detection is None:
                    self.score_history.clear()
                    result = ('No_Face', 0.0, None, 'H:--  S:--')
                else:
                    scores, box = detection
                    label, score, diagnostic = self.classify_scores(scores)
                    result = (label, score, box, diagnostic)
            except Exception as exc:
                self.score_history.clear()
                result = ('Inference_Error', 0.0, None, 'inference error')
                error = f'{type(exc).__name__}: {exc}'
                if error != self.last_inference_error:
                    self.get_logger().warning(f'DeepFace inference failed: {error}')
                    self.last_inference_error = error
            with self.result_lock:
                self.result = result
                self.result_version += 1
            if result[0] != self.last_logged_label:
                self.get_logger().info(
                    f'Face result: {result[0]} ({result[1]:.0%}); {result[3]}')
                self.last_logged_label = result[0]
            self.stop_worker.wait(1.0 / self.rate)

    def on_frame(self):
        ok, frame = self.capture.read()
        if not ok:
            self.publisher.publish(String(data='Camera_Error'))
            if self.show:
                cv2.waitKey(1)
            return

        frame = cv2.flip(frame, 1)
        with self.frame_lock:
            self.latest_frame = frame.copy()
        with self.result_lock:
            label, score, box, diagnostic = self.result
            version = self.result_version
        if version != self.published_version:
            self.publisher.publish(String(data=label))
            self.published_version = version
        if box:
            x, y, w, h = box
            cv2.rectangle(frame, (x, y), (x + w, y + h), (40, 220, 40), 2)

        if self.show:
            cv2.putText(frame, f'{label}  {score:.0%}', (12, 32),
                        cv2.FONT_HERSHEY_SIMPLEX, .8, (0, 255, 255), 2)
            for line_number, line in enumerate(diagnostic.splitlines()):
                cv2.putText(frame, line, (12, 62 + line_number * 21),
                            cv2.FONT_HERSHEY_SIMPLEX, .48, (0, 255, 255), 1)
            cv2.imshow('TurtleBot 4 - Facial emotion', frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                self.close()
                raise SystemExit(0)

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.stop_worker.set()
        if hasattr(self, 'inference_thread') and self.inference_thread.is_alive():
            self.inference_thread.join(timeout=2.0)
        if rclpy.ok():
            self.publisher.publish(String(data='Camera_Error'))
        self.capture.release()
        if self.show:
            try:
                cv2.destroyAllWindows()
            except cv2.error:
                pass


def main(args=None):
    rclpy.init(args=args, signal_handler_options=SignalHandlerOptions.NO)
    node = None
    try:
        node = EmotionRecognitionNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.close()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
