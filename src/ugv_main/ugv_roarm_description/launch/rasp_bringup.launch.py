import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction, SetEnvironmentVariable
from launch.conditions import IfCondition
from launch.substitutions import Command, LaunchConfiguration, PythonExpression
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from ament_index_python.packages import get_package_share_directory

# 시리얼 포트는 ttyUSB 번호 대신 USB 물리 포트(by-path) 기준으로 고정한다.
# ttyUSB 번호는 꽂힌 장치 수와 순서에 따라 바뀌어, RoArm이 빠지면 LiDAR가
# ttyUSB0이 되어 RoArm 드라이버가 LiDAR 포트를 잡는 문제가 있었다.
# LiDAR(LD19): RPi4 USB 허브 1.4번 포트
DEFAULT_LIDAR_PORT = ('/dev/serial/by-path/'
                      'platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.4:1.0-port0')


def generate_launch_description():

    lidar_port = LaunchConfiguration('lidar_port')
    roarm_port = LaunchConfiguration('roarm_port')
    declare_lidar_port = DeclareLaunchArgument(
        'lidar_port', default_value=DEFAULT_LIDAR_PORT,
        description='LD19 LiDAR serial port (by-path 권장)')
    declare_roarm_port = DeclareLaunchArgument(
        'roarm_port', default_value='',
        description='RoArm-M2 serial port (by-path 권장). 비우면 roarm_driver를 띄우지 않는다')
    # 대시보드 스택(Docker)을 띄운 PC의 IP. 비우면 bridge_params.yaml 값을 쓴다.
    declare_stomp_host = DeclareLaunchArgument(
        'stomp_host', default_value='',
        description='STOMP broker(RabbitMQ :15674) host = 대시보드 PC IP. 비우면 bridge_params.yaml 값')
    declare_jwks_uri = DeclareLaunchArgument(
        'oauth2_jwks_uri', default_value='',
        description='FastAPI JWT 검증용 JWKS URI. 비우면 bridge_params.yaml 값(기본 비활성)')

    pkg_dir = get_package_share_directory('ugv_roarm_description')
    # URDF via xacro
    robot_description = ParameterValue(
        Command(['xacro ', os.path.join(pkg_dir, 'urdf', 'rasp_roarm.xacro')]),
        value_type=str)

    # 1. Robot State Publisher
    robot_state_publisher_node = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[{'robot_description': robot_description}]
    )

    # 2. UGV Driver (C++) — 제어 + 센서 피드백 통합
    # (기존 ugv_bringup + ugv_driver를 하나의 C++ 노드로 통합)
    ugv_driver_node = Node(
        package='ugv_cpp_nodes',
        executable='ugv_driver_node',
        name='ugv_driver',
        output='screen',
    )

    # 4. rf2o_laser_odometry — LiDAR scan-based odometry + odom -> base_footprint TF
    rf2o_node = Node(
        package='rf2o_laser_odometry',
        executable='rf2o_laser_odometry_node',
        name='rf2o_laser_odometry',
        output='screen',
        parameters=[{
            'laser_scan_topic': '/scan',
            'odom_topic': '/odom',
            'publish_tf': True,
            'base_frame_id': 'base_footprint',
            'odom_frame_id': 'odom',
            'laser_frame_id': 'base_laser',
            'init_pose_from_topic': '',
            'freq': 20.0,
        }],
    )

    # 5. RoArm-M2 Driver — /arm_controller/joint_trajectory -> ESP32 serial (C++)
    roarm_driver_node = Node(
        package='ugv_cpp_nodes',
        executable='roarm_driver_node',
        name='roarm_driver',
        output='screen',
        parameters=[{
            'serial_port': roarm_port,
        }],
        condition=IfCondition(PythonExpression(["'", roarm_port, "' != ''"])),
    )

    # 6. LDLidar (STL-19P / LD19) — /scan laser data
    # Node launched directly (not via ld19.launch.py) to avoid its
    # conflicting base_link→base_laser static TF
    ldlidar_node = Node(
        package='ldlidar_ros2',
        executable='ldlidar_ros2_node',
        name='ldlidar_publisher_ld19',
        output='screen',
        parameters=[{
            'product_name': 'LDLiDAR_LD19',
            'laser_scan_topic_name': 'scan',
            'point_cloud_2d_topic_name': 'pointcloud2d',
            'frame_id': 'base_laser',
            'port_name': lidar_port,
            'serial_baudrate': 230400,
            'laser_scan_dir': True,
            'enable_angle_crop_func': True,
            'angle_crop_min': 210.0,
            'angle_crop_max': 329.0,
            'range_min': 0.02,
            'range_max': 12.0,
        }],
    )

    # 7. UGV Bridge — STOMP + REST API bridge for web dashboard
    # launch 인자로 준 값만 yaml 위에 덮어쓴다 (빈 값은 yaml 유지)
    bridge_params = os.path.join(
        get_package_share_directory('ugv_bridge'), 'config', 'bridge_params.yaml')

    def make_bridge_node(context):
        overrides = {}
        for key in ('stomp_host', 'oauth2_jwks_uri'):
            value = LaunchConfiguration(key).perform(context).strip()
            if value:
                overrides[key] = value
        params = [bridge_params] + ([overrides] if overrides else [])
        return [Node(
            package='ugv_bridge',
            executable='bridge_node',
            name='ugv_bridge',
            output='screen',
            parameters=params,
        )]

    bridge_node = OpaqueFunction(function=make_bridge_node)

    # 8. Static TF: base_lidar_link → base_laser
    # LiDAR publishes with frame_id 'base_laser', URDF has 'base_lidar_link'
    # yaw=π/2: LiDAR physical mounting is 90° rotated from URDF assumption
    lidar_static_tf = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='base_lidar_to_base_laser',
        arguments=['0', '0', '0', '1.5708', '0', '0',
                   'base_lidar_link', 'base_laser']
    )

    # CycloneDDS 사용 (FastDDS 2.6.x/Humble는 대형 메시지에서
    # "sequence size exceeds remaining buffer" 문제 있음. Iron+ 에서 개선 예정)
    # serdata 경고는 rcutils stderr로 출력되어 환경변수로 억제 불가.
    # 필터링 실행: ugv-launch alias 참고 (grep -v serdata)
    use_cyclonedds = SetEnvironmentVariable('RMW_IMPLEMENTATION', 'rmw_cyclonedds_cpp')

    return LaunchDescription([
        declare_lidar_port,
        declare_roarm_port,
        declare_stomp_host,
        declare_jwks_uri,
        use_cyclonedds,
        robot_state_publisher_node,
        ugv_driver_node,
        rf2o_node,
        roarm_driver_node,
        ldlidar_node,
        bridge_node,
        lidar_static_tf,
    ])
