"""Launch webcam emotion recognition and its TurtleBot 4 behavior controller."""
from ament_index_python.packages import get_package_prefix
from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, ExecuteProcess, RegisterEventHandler,
                            EmitEvent, SetEnvironmentVariable)
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from pathlib import Path


def generate_launch_description():
    scripts = Path(get_package_prefix('tb4_emotion_control')) / 'lib' / 'tb4_assignment'
    camera = ExecuteProcess(
        cmd=[LaunchConfiguration('python_executable'), str(scripts / 'emotion_recognition_node.py'),
             '--ros-args', '-p', ['camera_index:=', LaunchConfiguration('camera_index')],
             '-p', ['show_window:=', LaunchConfiguration('show_window')],
             '-p', ['frame_rate:=', LaunchConfiguration('frame_rate')],
             '-p', ['display_rate:=', LaunchConfiguration('display_rate')],
             '-p', ['confidence:=', LaunchConfiguration('confidence')],
             '-p', ['emotion_margin:=', LaunchConfiguration('emotion_margin')],
             '-p', ['happy_surprise_margin:=', LaunchConfiguration('happy_surprise_margin')],
             '-p', ['smoothing_window:=', LaunchConfiguration('smoothing_window')],
             '-p', ['detector_backend:=', LaunchConfiguration('detector_backend')]], output='screen')
    behavior = Node(
        package='tb4_assignment', executable='emotion_behavior_node.py', output='screen',
        parameters=[{'use_sim_time': ParameterValue(LaunchConfiguration('use_sim_time'), value_type=bool),
                     'signal_timeout': ParameterValue(LaunchConfiguration('signal_timeout'), value_type=float),
                     'linear_scale': ParameterValue(LaunchConfiguration('linear_scale'), value_type=float),
                     'angular_scale': ParameterValue(LaunchConfiguration('angular_scale'), value_type=float)}])
    stop_on_exit = lambda action, reason: RegisterEventHandler(OnProcessExit(
        target_action=action, on_exit=[EmitEvent(event=Shutdown(reason=reason))]))
    return LaunchDescription([
        SetEnvironmentVariable('RMW_IMPLEMENTATION', 'rmw_fastrtps_cpp'),
        DeclareLaunchArgument('python_executable', default_value='/usr/bin/python3',
                              description='ROS Python with DeepFace installed'),
        DeclareLaunchArgument('camera_index', default_value='0'),
        DeclareLaunchArgument('show_window', default_value='true', choices=['true', 'false']),
        DeclareLaunchArgument('frame_rate', default_value='2.0'),
        DeclareLaunchArgument('display_rate', default_value='30.0'),
        DeclareLaunchArgument('confidence', default_value='0.32'),
        DeclareLaunchArgument('emotion_margin', default_value='0.04'),
        DeclareLaunchArgument('happy_surprise_margin', default_value='0.15'),
        DeclareLaunchArgument('smoothing_window', default_value='3'),
        DeclareLaunchArgument('detector_backend', default_value='opencv',
                              choices=['retinaface', 'opencv']),
        DeclareLaunchArgument('signal_timeout', default_value='3.0'),
        DeclareLaunchArgument('use_sim_time', default_value='true', choices=['true', 'false']),
        DeclareLaunchArgument('linear_scale', default_value='1.0'),
        DeclareLaunchArgument('angular_scale', default_value='1.0'),
        stop_on_exit(camera, 'Emotion camera exited'),
        stop_on_exit(behavior, 'Emotion behavior controller exited'),
        behavior, camera,
    ])
