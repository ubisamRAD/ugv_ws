import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg_dir = get_package_share_directory('ugv_bridge')
    default_params = os.path.join(pkg_dir, 'config', 'bridge_params.yaml')

    return LaunchDescription([
        DeclareLaunchArgument(
            'params_file',
            default_value=default_params,
            description='Path to bridge parameters YAML',
        ),
        DeclareLaunchArgument(
            'robot_ids',
            default_value='ugv01',
            description='Comma-separated robot IDs to manage',
        ),
        DeclareLaunchArgument(
            'stomp_host',
            default_value='',
            description='STOMP broker host (대시보드 PC IP). 비우면 params_file 값',
        ),
        DeclareLaunchArgument(
            'oauth2_jwks_uri',
            default_value='',
            description='JWKS URI for FastAPI JWT 검증. 비우면 params_file 값',
        ),
        OpaqueFunction(function=_make_bridge_node),
    ])


def _make_bridge_node(context):
    overrides = {'robot_ids': LaunchConfiguration('robot_ids').perform(context)}
    for key in ('stomp_host', 'oauth2_jwks_uri'):
        value = LaunchConfiguration(key).perform(context).strip()
        if value:
            overrides[key] = value
    return [Node(
        package='ugv_bridge',
        executable='bridge_node',
        name='bridge_node',
        parameters=[LaunchConfiguration('params_file'), overrides],
        output='screen',
    )]
