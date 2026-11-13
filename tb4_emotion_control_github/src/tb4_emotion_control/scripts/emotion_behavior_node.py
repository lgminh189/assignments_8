#!/usr/bin/env python3
"""Map facial emotion events to short, bounded TurtleBot 4 motions."""
import math
import time

import rclpy
from rclpy.clock import Clock, ClockType
from rclpy.node import Node
from rclpy.signals import SignalHandlerOptions
from geometry_msgs.msg import TwistStamped
from std_msgs.msg import String


class EmotionBehaviorNode(Node):
    # Duration-bounded motions: curved paths, a short reverse/forward step, and one turn.
    ACTIONS = {
        'Happy': (0.12, 0.30, 4.0),       # curve left
        'Sad': (0.12, -0.30, 4.0),        # curve right
        'Angry': (-0.08, 0.0, 0.6),       # small reverse
        'Surprise': (0.0, 0.50, 2.0 * math.pi / 0.50),  # one full turn
        'Fear': (0.08, 0.0, 0.6),         # small forward step
    }

    def __init__(self):
        super().__init__('emotion_behavior_node')
        self.declare_parameter('signal_timeout', 3.0)
        self.declare_parameter('linear_scale', 1.0)
        self.declare_parameter('angular_scale', 1.0)
        self.timeout = float(self.get_parameter('signal_timeout').value)
        self.linear_scale = float(self.get_parameter('linear_scale').value)
        self.angular_scale = float(self.get_parameter('angular_scale').value)
        if self.timeout <= 0 or not 0 < self.linear_scale <= 1 or not 0 < self.angular_scale <= 1:
            raise ValueError('timeout must be positive; velocity scales must be in (0, 1]')
        self.velocity = self.create_publisher(TwistStamped, '/cmd_vel', 1)
        self.create_subscription(String, '/detected_emotion', self.on_emotion, 1)
        self.emotion = None
        self.completed_emotion = None
        self.last_signal = time.monotonic()
        self.action_started = self.last_signal
        self.create_timer(0.05, self.on_tick, clock=Clock(clock_type=ClockType.STEADY_TIME))
        self.get_logger().info('Listening on /detected_emotion; publishing TwistStamped to /cmd_vel')

    def on_emotion(self, msg):
        now = time.monotonic()
        self.last_signal = now
        label = msg.data
        if label not in self.ACTIONS and label != 'Neutral':
            # Ambiguous predictions must stop motion and allow the next
            # confidently classified expression to trigger a new action.
            label = None

        # A missing/invalid face result rearms the last completed emotion so the
        # same expression can trigger again after the person leaves/reappears.
        if label is None:
            self.completed_emotion = None
            if self.emotion is not None:
                self.emotion = None
                self.get_logger().info('Emotion cleared; robot stopped')
            self.publish(0.0, 0.0)
            return

        if label == self.completed_emotion:
            return
        if label != self.emotion:
            self.completed_emotion = None
            self.emotion = label
            self.action_started = now
            self.get_logger().info(f'Emotion: {label or "unknown/no face"}')
            if label is None or label == 'Neutral':
                self.publish(0.0, 0.0)

    def publish(self, linear, angular):
        msg = TwistStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'base_link'
        msg.twist.linear.x = float(linear)
        msg.twist.angular.z = float(angular)
        self.velocity.publish(msg)

    def on_tick(self):
        now = time.monotonic()
        if now - self.last_signal > self.timeout:
            self.emotion = None
            self.completed_emotion = None
            self.publish(0.0, 0.0)
            return
        if self.emotion not in self.ACTIONS:
            self.publish(0.0, 0.0)
            return
        linear, angular, duration = self.ACTIONS[self.emotion]
        if self.emotion == 'Surprise':
            duration = 2.0 * math.pi / (abs(angular) * self.angular_scale)
        if now - self.action_started >= duration:
            self.completed_emotion = self.emotion
            self.emotion = None
            self.publish(0.0, 0.0)
            return
        self.publish(linear * self.linear_scale, angular * self.angular_scale)


def main(args=None):
    rclpy.init(args=args, signal_handler_options=SignalHandlerOptions.NO)
    node = EmotionBehaviorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if rclpy.ok():
            node.publish(0.0, 0.0)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
