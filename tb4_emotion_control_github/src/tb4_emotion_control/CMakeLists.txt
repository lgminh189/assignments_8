cmake_minimum_required(VERSION 3.8)
project(tb4_emotion_control)

find_package(ament_cmake REQUIRED)

install(DIRECTORY launch DESTINATION share/${PROJECT_NAME})
install(PROGRAMS
  scripts/emotion_recognition_node.py
  scripts/emotion_behavior_node.py
  DESTINATION lib/${PROJECT_NAME}
)

ament_package()
