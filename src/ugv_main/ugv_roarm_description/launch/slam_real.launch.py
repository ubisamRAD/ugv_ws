"""
Real Robot SLAM Launch File (Cartographer)

RPi 또는 WSL에서 실행 가능.
RPi에서 실행 시: rasp_bringup과 같은 머신에서 토픽 직접 수신.
WSL에서 실행 시: CycloneDDS를 통해 RPi 토픽 수신 + RViz 시각화.

맵 저장: SLAM이 켜져 있는 동안 다른 터미널에서 ~/ugv_ws/save_map.sh [이름] 실행 후 Ctrl+C로 종료.
(Ctrl+C 시점 자동 저장은 Cartographer가 먼저 꺼져 저장 요청이 실패하므로 제거함)

Usage:
  ros2 launch ugv_roarm_description slam_real.launch.py
  ros2 launch ugv_roarm_description slam_real.launch.py use_rviz:=true  # WSL with RViz
"""

import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():

    pkg_dir = get_package_share_directory('ugv_roarm_description')
    cartographer_config_dir = os.path.join(pkg_dir, 'config')
    rviz_config = os.path.join(pkg_dir, 'rviz', 'slam_view.rviz')

    use_rviz = LaunchConfiguration('use_rviz')

    return LaunchDescription([
        DeclareLaunchArgument(
            'use_rviz',
            default_value='false',
            description='Launch RViz (set true on WSL, false on RPi)'),

        # Cartographer SLAM node
        Node(
            package='cartographer_ros',
            executable='cartographer_node',
            name='cartographer_node',
            output='screen',
            parameters=[{'use_sim_time': False}],
            arguments=[
                '-configuration_directory', cartographer_config_dir,
                '-configuration_basename', 'cartographer_mapping_2d.lua',
            ],
            remappings=[
                ('scan', '/scan'),
                ('odom', '/odom'),
            ],
        ),

        # Cartographer occupancy grid node (publishes /map)
        Node(
            package='cartographer_ros',
            executable='cartographer_occupancy_grid_node',
            name='cartographer_occupancy_grid_node',
            output='screen',
            parameters=[{
                'use_sim_time': False,
                'resolution': 0.05,
                'publish_period_sec': 1.0,
            }],
        ),

        # RViz2 (optional, for WSL only)
        Node(
            package='rviz2',
            executable='rviz2',
            name='rviz2',
            output='screen',
            arguments=['-d', rviz_config],
            additional_env={'LIBGL_ALWAYS_SOFTWARE': '1'},
            condition=IfCondition(use_rviz),
        ),
    ])
