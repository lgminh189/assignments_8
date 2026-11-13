# TurtleBot 4 Facial Emotion Control (ROS 2 Jazzy)

ROS 2 package that reads a webcam, estimates facial emotion with DeepFace, displays the prediction, and sends bounded `TwistStamped` commands to `/cmd_vel`.

## Features

- Six requested states: Happy, Sad, Neutral, Angry, Surprise, Fear.
- Separate camera preview (target 30 FPS) and DeepFace inference (default 2 FPS).
- Moving average over recent predictions and an `Uncertain` stop state.
- Separate Happy/Surprise confidence margin; class scores shown in the preview.
- Timed, low-speed motion commands; zero velocity on uncertain/no-face/timeout/exit.
- Standalone package name `tb4_emotion_control`, avoiding collisions with other workspace packages.

## Requirements

- Ubuntu 24.04, ROS 2 Jazzy, Python 3.12.
- TurtleBot 4 or its Gazebo simulation already running, with a motion controller subscribed to `/cmd_vel`.
- Webcam available to OpenCV and a graphical session for the preview.
- DeepFace's TensorFlow model is downloaded on first run; network access is required then.

## Install

From the extracted repository root:

```bash
sudo apt update
sudo apt install python3-opencv python3-venv python3-pip
python3 -m venv --system-site-packages .venv-emotion
.venv-emotion/bin/python -m pip install --upgrade pip
.venv-emotion/bin/python -m pip install --default-timeout=1800 --retries 10 -r requirements-emotion.txt
.venv-emotion/bin/python -c "import rclpy, cv2; from deepface import DeepFace; print('Imports OK')"

source /opt/ros/jazzy/setup.bash
colcon build --symlink-install --packages-select tb4_emotion_control
source install/setup.bash
```

The venv uses `--system-site-packages` so it can import ROS Python modules. Keep the GUI `opencv-python` wheel; a headless OpenCV package will make `cv2.imshow` unavailable.

## Run

Start the TurtleBot 4 simulation or real robot and its motion controller first. Then:

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
export ROS_DOMAIN_ID=23
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
ros2 launch tb4_emotion_control emotion_control.launch.py \
  python_executable:="$PWD/.venv-emotion/bin/python" \
  camera_index:=0 use_sim_time:=true \
  confidence:=0.32 emotion_margin:=0.04 \
  happy_surprise_margin:=0.15 smoothing_window:=3 \
  detector_backend:=opencv
```

Use the same `ROS_DOMAIN_ID` and RMW setting as the robot/simulation. Set `camera_index:=1` if the desired camera is index 1. Press `q` in the preview or Ctrl+C to exit. Check topics in another terminal:

```bash
ros2 topic echo /detected_emotion
ros2 topic info /cmd_vel -v
```

## Emotion-to-motion mapping

| State | Command | Duration |
|---|---|---:|
| Happy | Forward + turn left (curved path) | 4.0 s |
| Sad | Forward + turn right (curved path) | 4.0 s |
| Neutral | Stop | Immediate |
| Angry | Reverse slowly | 0.6 s |
| Surprise | Rotate in place | One nominal revolution |
| Fear | Move forward slowly | 0.6 s |
| Uncertain / no face / error | Stop | Immediate |

The preview shows class scores and the top-two margin. Face detection defaults to OpenCV for quick startup, with alignment and 5% crop expansion. It rejects frames where no face is detected rather than classifying the whole image. Close Happy/Surprise, Fear/Surprise and Angry/Sad scores are explicitly marked `Uncertain` and stop the robot. Try `detector_backend:=retinaface` if OpenCV fails to detect a visible face and the computer has enough CPU. The supplied six-expression montage is a visual reference, not a training set; personalization needs multiple webcam samples per class.

See [`docs/BAO_CAO_BAI_08.md`](docs/BAO_CAO_BAI_08.md) for implementation details, parameter descriptions, the experiment status, and diagrams. Diagrams are illustrative/theoretical; they are not captured experiment evidence.

## Safety and limitations

The emotion model estimates expression from an image; it does not determine a person's actual mental state. Lighting, pose, occlusion, camera quality and model bias affect predictions. Run at low speed in a clear area with a human supervisor. This package does not implement obstacle avoidance and must not compete with Nav2/teleoperation or another `/cmd_vel` publisher.
