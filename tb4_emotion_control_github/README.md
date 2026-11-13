# TurtleBot 4 — Nhận diện biểu cảm khuôn mặt và điều khiển ROS 2

Package ROS 2 Jazzy độc lập dùng webcam, OpenCV và DeepFace để ước lượng sáu biểu cảm, hiển thị kết quả trực tiếp và gửi lệnh `geometry_msgs/msg/TwistStamped` lên `/cmd_vel`.

## Chức năng

| Biểu cảm | Hành vi |
| --- | --- |
| Happy | Chạy cong sang trái, tối đa 4 giây |
| Sad | Chạy cong sang phải, tối đa 4 giây |
| Neutral | Dừng |
| Angry | Lùi nhẹ, tối đa 0,6 giây |
| Surprise | Xoay tại chỗ một vòng |
| Fear | Tiến nhẹ, tối đa 0,6 giây |
| Không rõ mặt / dự đoán mơ hồ | Dừng |

Camera preview mục tiêu 30 FPS, suy luận mặc định 2 FPS để giảm giật. Lệnh chuyển động có thời lượng giới hạn. Cần TurtleBot 4 thật hoặc mô phỏng và motion controller đang nghe `/cmd_vel`.

## Yêu cầu

- Ubuntu 24.04, ROS 2 Jazzy, Python 3.12, `colcon`.
- TurtleBot 4/Gazebo đã chạy; package này không kèm launch Gazebo hay SLAM.
- Webcam và desktop GUI để mở cửa sổ OpenCV.
- Internet khi chạy lần đầu để DeepFace tải model TensorFlow.

## Cài đặt

Giải nén ZIP rồi vào thư mục `tb4_emotion_control_github` (thư mục chứa `src/` và `requirements-emotion.txt`):

```bash
cd ~/tb4_emotion_control_github
sudo apt update
sudo apt install -y python3-opencv python3-venv python3-pip
source /opt/ros/jazzy/setup.bash
python3 -m venv --system-site-packages .venv-emotion
.venv-emotion/bin/python -m pip install --upgrade pip
.venv-emotion/bin/python -m pip install --default-timeout=1800 --retries 10 -r requirements-emotion.txt

# Giữ OpenCV GUI để cv2.imshow mở được cửa sổ preview.
.venv-emotion/bin/python -m pip install --force-reinstall --no-deps opencv-python==4.11.0.86
.venv-emotion/bin/python -c "import rclpy, cv2; from deepface import DeepFace; print('Imports OK')"

colcon build --symlink-install --packages-select tb4_emotion_control
source install/setup.bash
```

Venv dùng `--system-site-packages` để nạp `rclpy` từ ROS. RetinaFace có thể cài OpenCV headless như dependency nên bước cài lại OpenCV GUI ở trên cần được giữ. Nếu `colcon` báo duplicate package, hãy build từ gốc của ZIP và không đặt bên trong workspace khác có package cùng tên.

## Chạy

Trước tiên khởi động TurtleBot 4 thật hoặc mô phỏng **riêng**. Với workspace bài thực hành đầy đủ, ví dụ lệnh Gazebo là `ros2 launch tb4_assignment sim_mapping.launch.py`; lệnh đó không nằm trong gói ZIP này. Sau khi robot và motion controller sẵn sàng, chạy lệnh sau từ gốc package ZIP:

```bash
cd ~/tb4_emotion_control_github
source /opt/ros/jazzy/setup.bash
source install/setup.bash
export ROS_DOMAIN_ID=23
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
ros2 launch tb4_emotion_control emotion_control.launch.py \
  python_executable:="$PWD/.venv-emotion/bin/python" \
  camera_index:=0 use_sim_time:=true detector_backend:=opencv
```

Đặt cùng `ROS_DOMAIN_ID` và middleware ở mọi terminal ROS. Mô phỏng dùng `use_sim_time:=true`; robot thật thường dùng `use_sim_time:=false`. Nhấn `q` trên cửa sổ preview hoặc `Ctrl+C` trong terminal để thoát. Có thể đổi `camera_index:=1` nếu webcam nằm ở index 1.

### Tham số hữu ích

```bash
ros2 launch tb4_emotion_control emotion_control.launch.py \
  python_executable:="$PWD/.venv-emotion/bin/python" camera_index:=0 \
  use_sim_time:=true detector_backend:=opencv \
  confidence:=0.32 emotion_margin:=0.04 happy_surprise_margin:=0.15 \
  smoothing_window:=3 frame_rate:=2.0 display_rate:=30.0
```

`detector_backend` nhận `opencv` hoặc `retinaface`. OpenCV nhanh hơn; RetinaFace có thể thử khi detector không bắt được mặt, nhưng cần nhiều CPU hơn. `show_window:=false` tắt cửa sổ, phù hợp headless. `linear_scale` và `angular_scale` điều chỉnh tốc độ trong khoảng `(0, 1]`.

## Kiểm tra topic

Trong terminal khác, source ROS và dùng cùng domain/middleware:

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
export ROS_DOMAIN_ID=23
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
ros2 topic echo /detected_emotion
```

Để xem lệnh vận tốc:

```bash
ros2 topic info /cmd_vel -v
ros2 topic echo /cmd_vel
```

## Xử lý lỗi nhanh

- **Không có `cv2`/`deepface`:** kiểm tra `.venv-emotion/bin/python` và cài lại requirements.
- **Không mở camera:** đóng ứng dụng khác đang dùng webcam, thử `camera_index:=1`, kiểm tra quyền `/dev/video*`.
- **Không hiện cửa sổ:** cần desktop GUI và wheel `opencv-python` GUI, không phải bản headless; không đặt `show_window:=false`.
- **Không thấy topic hoặc lỗi participant index:** dừng launch cũ, đặt cùng ROS domain/RMW ở tất cả terminal; thử domain khác nếu domain hiện tại bị dùng hết participant index.
- **No_Face/Uncertain:** tăng ánh sáng, nhìn thẳng webcam, bỏ vật che mặt và chờ vài lần suy luận. Kết quả phụ thuộc góc mặt, ánh sáng và người dùng.

## Giới hạn và an toàn

Confidence là điểm của mô hình, không phải phần trăm độ chính xác đã kiểm chứng. Mô hình suy đoán biểu cảm từ hình ảnh, không xác định trạng thái tâm lý. Thử ở tốc độ thấp, vùng trống, có người quan sát; package này không tránh vật cản. Không chạy đồng thời với Nav2, teleop hoặc publisher `/cmd_vel` khác.

## Báo cáo và ảnh

- [Báo cáo PDF](docs/BAO_CAO_BAI_08.pdf)
- [Báo cáo Word](docs/BAO_CAO_BAI_08.docx)
- [Báo cáo Markdown](docs/BAO_CAO_BAI_08.md)
- [Ảnh camera mô phỏng thực tế](docs/figures/camera_simulation_actual.png)
- [Ảnh preview nhận diện (khuôn mặt đã làm mờ)](docs/figures/webcam_emotion_actual_blurred.png)

