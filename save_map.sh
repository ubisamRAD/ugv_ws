#!/bin/bash
# Cartographer SLAM(slam_real.launch.py)이 실행 중일 때 다른 터미널에서 실행해 맵을 저장한다.
# 저장 위치: ~/maps/<이름>.pbstream (Nav2용) + <이름>.pgm/.yaml (확인·보관용)
#
# 사용법: ./save_map.sh [이름]      이름을 생략하면 map_YYYYMMDD_HHMMSS
# 저장이 끝난 뒤 SLAM 터미널에서 Ctrl+C로 SLAM을 끈다. 순서를 바꾸면 저장되지 않는다.
set -u

NAME="${1:-map_$(date +%Y%m%d_%H%M%S)}"
MAP_DIR="$HOME/maps"
OUT="$MAP_DIR/$NAME"
mkdir -p "$MAP_DIR"

if ! ros2 service list 2>/dev/null | grep -q "^/write_state$"; then
  echo "[save_map] /write_state 서비스가 없습니다. slam_real.launch.py가 실행 중인지 확인하세요." >&2
  exit 1
fi

echo "[save_map] 1/3 궤적 마무리"
ros2 service call /finish_trajectory cartographer_ros_msgs/srv/FinishTrajectory \
  "{trajectory_id: 0}" | grep -o "message='[^']*'"

echo "[save_map] 2/3 pbstream 저장: $OUT.pbstream"
ros2 service call /write_state cartographer_ros_msgs/srv/WriteState \
  "{filename: '$OUT.pbstream', include_unfinished_submaps: true}" | grep -o "message=[\"'][^\"']*[\"']"

echo "[save_map] 3/3 pgm/yaml 저장"
ros2 run nav2_map_server map_saver_cli -f "$OUT" 2>&1 | grep -E "Map saved|Failed|error" | head -2

if [ -f "$OUT.pbstream" ] && [ -f "$OUT.pgm" ] && [ -f "$OUT.yaml" ]; then
  echo "[save_map] 완료"
  ls -lh "$OUT".*
else
  echo "[save_map] 일부 파일이 없습니다. 위 메시지를 확인하세요." >&2
  ls -lh "$OUT".* 2>/dev/null
  exit 1
fi
