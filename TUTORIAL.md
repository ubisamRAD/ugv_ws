# UGV 실기 연동 튜토리얼

새 PC에서 대시보드(ugv-frontend)를 띄우고 RPi 실기에 연결한 뒤, 맵을 새로 만들어 교체하고 Nav2 자율주행까지 확인하는 순서입니다.
2026-11-17 실기(RPi 192.168.0.71)에서 직접 돌려 보며 정리했습니다. 로봇팔(RoArm-M2)은 이 문서에서 다루지 않습니다.

## 0. 먼저 읽기

### 0-1. 전체 구조

```
[내 PC]                                         [RPi 192.168.0.71]
 브라우저 :3000
   ├─ 로그인 ──────────→ oauth2-web :9020
   ├─ STOMP ───────────→ stomp-web  :9030 ─→ stomp-mq ←─ :15674 ── ugv_bridge (ugv-launch 안에서 실행)
   └─ 맵 PNG (REST) ─────────────────────────────────────→ :8081 ── ugv_bridge FastAPI
 Docker Desktop: oauth2-db, oauth2-web, stomp-mq, stomp-web
```

- OAuth2 토큰은 브라우저와 stomp-web 사이에서만 씁니다. 토큰 오류가 나면 이 구간을 보면 됩니다.
- RPi의 ugv_bridge는 토큰 없이 `stomp-mq` 계정으로 **내 PC의 15674 포트**에 바로 붙으므로 RPi를 띄울 때 내 PC IP를 알려 줘야 합니다.
- 맵 이미지는 브라우저가 RPi(:8081)에서 직접 받아 옵니다.
- 브리지는 한 번에 브로커 하나에만 붙습니다. 대시보드를 쓰는 PC가 바뀌면 RPi도 그 PC IP로 다시 띄워야 합니다.

### 0-2. 터미널 표기

명령 블록마다 어느 기기의 몇 번째 터미널에서 치는지 적어 두었습니다. 처음 등장할 때 새로 열고, 이후에는 같은 터미널을 계속 씁니다.

| 표기 | 기기 | 여는 방법 | 용도 | 상태 |
|------|------|-----------|------|------|
| **[PC-1]** | 내 PC | PowerShell을 새로 연다 | Docker, 포트 확인 등 일반 명령 | 계속 입력 가능 |
| **[PC-2]** | 내 PC | PowerShell을 하나 더 연다 | `npm run dev` | 실행 중에는 점유됨, 닫지 않음 |
| **[PC-3]** | 내 PC | WSL(Ubuntu 22.04) 터미널을 연다 | RViz로 SLAM 맵 보기 (선택, 4-6) | RViz 실행 중에는 점유됨 |
| **[RPi-1]** | RPi | PC에서 PowerShell을 하나 더 열고 `ssh pi@192.168.0.71` | 빌드, 정리, 확인 명령 | 계속 입력 가능 |
| **[RPi-2]** | RPi | PC에서 PowerShell을 하나 더 열고 `ssh pi@192.168.0.71` | `ugv-launch` (로봇 기동) | 실행 중에는 점유됨, 닫지 않음 |
| **[RPi-3]** | RPi | PC에서 PowerShell을 하나 더 열고 `ssh pi@192.168.0.71` | `ugv-nav` 또는 SLAM | 실행 중에는 점유됨, 둘을 번갈아 씀 |

- RPi 터미널은 모두 **PC에서 SSH로 접속한 창**입니다. 프롬프트가 `pi@ugv:~$`로 바뀌었는지 보고 입력하세요.
- 점유된 터미널의 SSH 창을 그냥 닫으면 RPi에 프로세스가 남을 수 있습니다. 끌 때는 항상 그 창에서 **Ctrl+C**를 누르고 프롬프트가 돌아온 뒤 닫습니다.

## 1. 준비물

| 항목 | 비고 |
|------|------|
| Docker Desktop | 실행 중이어야 함 |
| Node.js 18 이상, npm 9 이상 | |
| Git | |
| SSH 클라이언트 | Windows 10 이상은 PowerShell에 `ssh`가 기본으로 들어 있음 |
| RPi와 같은 네트워크 | 내 PC IP를 [PC-1]에서 `ipconfig`로 확인해 둠 (예: 192.168.0.xx) |
| RPi `pi` 계정 비밀번호 | 담당자에게 받음 |

## 2. 내 PC: 포트 충돌 확인

같은 이미지로 만든 스택(gmoma-frontend, 예전 boilerplate 등)이 이미 떠 있으면 포트가 겹칩니다.
그러면 브라우저와 브리지가 서로 다른 OAuth2, STOMP 서버에 붙어서 토큰이 안 맞거나 데이터가 안 들어옵니다.

**[PC-1]** PowerShell을 새로 엽니다.

```powershell
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
netstat -ano | findstr /R ":9020 :9030 :15672 :15674 :61613 :5432"
```

- 위 포트를 다른 컨테이너나 프로세스가 쓰고 있으면 먼저 내립니다.
- WSL 안에 Docker 엔진을 따로 설치해 쓰는 경우, 그 컨테이너는 Windows의 `docker ps`에 보이지 않습니다. WSL 터미널에서 `ss -tln | grep -E ":(9020|9030|15672|15674|61613)"`로 한 번 더 확인합니다. 그 엔진을 끄려면 WSL 터미널에서 `sudo systemctl stop docker docker.socket`을 실행합니다.
- `Dockerfile-robot.yml`의 compose 프로젝트 이름(`ugv-robot`)과 컨테이너 이름(`stomp-mq` 등)을 다른 레포와 같이 쓰면 서로 덮어씁니다.

## 3. 내 PC: 대시보드 구동

**[PC-1]**

```powershell
git clone https://github.com/ubisamRAD/ugv-frontend.git
cd ugv-frontend
docker compose -f Dockerfile-robot.yml up -d
npm install
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

컨테이너 4개가 모두 `Up`이고 PORTS 칸에 `0.0.0.0:15674->15674/tcp`처럼 호스트 포트가 보여야 합니다.
`15674/tcp`만 보이면 다른 프로세스가 포트를 먼저 잡은 것이니 2단계로 돌아갑니다.

**[PC-2]** PowerShell을 하나 더 엽니다. 이 창은 개발 서버가 계속 차지합니다.

```powershell
cd ugv-frontend
npm run dev
```

1. 브라우저에서 http://localhost:3000 에 접속합니다. 3000 포트가 이미 쓰이고 있으면 Vite가 3001 같은 다른 포트로 띄웁니다. [PC-2]에 찍힌 주소를 쓰세요.
2. **시작하기**를 누르고 `oauth2-web` / `oauth2-web`으로 로그인합니다.
3. 오른쪽 위가 **Connected**, LOG에 `STOMP connected via proxy`가 찍히면 브라우저 쪽은 정상입니다.
   아직 로봇을 연결하지 않았으니 배터리 0.0 V, LiDAR 0 pts가 맞습니다.

RPi IP가 192.168.0.71이 아니면 `ugv-frontend/.env.dev.robot.local` 파일을 만들어 `VITE_ROBOT_BRIDGE_URL=http://<RPi IP>:8081`을 넣고 [PC-2]에서 Ctrl+C 후 `npm run dev`를 다시 실행합니다.

## 4. RPi 처음 한 번 설정

### 4-1. SSH 키 등록 (선택)

키를 등록하면 RPi 터미널을 열 때마다 비밀번호를 치지 않아도 됩니다.

**[PC-1]**

```powershell
ssh-keygen -t ed25519          # 이미 키가 있으면 건너뜀. 질문은 모두 Enter
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh pi@192.168.0.71 "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
```

마지막 명령에서 RPi 비밀번호를 한 번 입력합니다.

### 4-2. RPi 터미널 1 열기

**[RPi-1]** PowerShell을 하나 더 열고 접속합니다. 앞으로 RPi에서 빌드하고 확인하는 명령은 모두 이 창에서 칩니다.

```powershell
ssh pi@192.168.0.71
```

### 4-3. 코드 최신화와 빌드

RPi는 소스(`src`)가 아니라 **빌드 결과물(`install`)**을 실행합니다. launch 파일이나 `bridge_params.yaml` 같은 설정을 고쳐도 빌드하지 않으면 반영되지 않습니다.
실제로 RPi 소스의 `stomp_host`를 바꿔 놓고 빌드를 하지 않아서 브리지가 계속 예전 PC IP로 접속하던 일이 있었습니다.

**[RPi-1]** 먼저 RPi에 남아 있는 수정 사항을 확인합니다.

```bash
cd ~/ugv_ws
git status --short
```

- `M`으로 표시된 파일이 있으면 누군가 RPi에서 직접 고친 것입니다. 필요한 수정이면 담당자와 확인하고 필요 없으면 `git checkout -- <파일>`로 되돌립니다.
- 특히 `bridge_params.yaml`의 `stomp_host`는 이제 고칠 필요가 없습니다. 6단계에서 기동할 때 인자로 넘깁니다.

**[RPi-1]** 최신 코드를 받고 빌드합니다.

```bash
cd ~/ugv_ws
git pull origin ros2-humble-develop
source /opt/ros/humble/setup.bash
colcon build --packages-select ugv_roarm_description ugv_bridge ugv_cpp_nodes
source install/setup.bash
```

- 빌드 끝에 `Summary: 3 packages finished`가 나오면 성공입니다. `failed`가 보이면 위로 올려 에러를 확인합니다.
- 이미 열려 있는 다른 RPi 터미널([RPi-2], [RPi-3])은 새 빌드를 모릅니다. 그 창에서 실행 중인 것을 Ctrl+C로 끄고 `source ~/ugv_ws/install/setup.bash`를 실행한 뒤 다시 띄웁니다. 새로 연 SSH 창은 `~/.bashrc`가 자동으로 불러옵니다.

어떤 파일을 고쳤을 때 무엇을 빌드해야 하는지는 아래와 같습니다.

| 고친 파일 | 빌드 명령 ([RPi-1]) |
|-----------|---------------------|
| `ugv_roarm_description/launch/*.py`, `config/*` | `colcon build --packages-select ugv_roarm_description` |
| `ugv_bridge/config/bridge_params.yaml`, `ugv_bridge/*.py` | `colcon build --packages-select ugv_bridge` |
| `ugv_cpp_nodes/src/*` | `colcon build --packages-select ugv_cpp_nodes` |

빌드한 뒤에는 항상 `source ~/ugv_ws/install/setup.bash`를 실행하고 실행 중인 launch를 다시 띄워야 반영됩니다.

### 4-4. 단축 명령 등록 (ugv-launch, ugv-nav)

`ugv-launch`와 `ugv-nav`는 긴 `ros2 launch` 명령에 CycloneDDS 경고 필터를 붙인 단축 명령입니다.
예전 `~/.bashrc`에는 **alias**로 들어 있는데, alias는 뒤에 붙인 인자를 launch가 아니라 grep에 넘깁니다. 그래서 `ugv-launch stomp_host:=...`가 동작하지 않습니다. **함수**로 바꿔야 합니다.

**[RPi-1]**

```bash
nano ~/.bashrc
```

`alias ugv-launch=...`와 `alias ugv-nav=...` 두 줄을 지우고 그 자리에 아래 세 줄을 넣고 저장합니다(Ctrl+O, Enter, Ctrl+X).

```bash
UGV_LOG_FILTER='serdata|rcutils_reset_error|error state is being overwritten|with this new error message|error_handling.c|>>>|<<<'
ugv-launch() { ros2 launch ugv_roarm_description rasp_bringup.launch.py "$@" 2>&1 | grep -v -E "$UGV_LOG_FILTER"; }
ugv-nav() { ros2 launch ugv_roarm_description nav_real.launch.py pbstream:=/home/pi/maps/lab_map.pbstream "$@" 2>&1 | grep -v -E "$UGV_LOG_FILTER"; }
```

**[RPi-1]** 적용하고 확인합니다.

```bash
source ~/.bashrc
type ugv-launch
```

`ugv-launch is a function`이 나오면 정상입니다. 이미 열려 있던 다른 RPi 터미널은 닫고 새로 열거나 그 창에서도 `source ~/.bashrc`를 실행합니다.

### 4-5. RPi에서 내 PC 브로커가 보이는지 확인

**[RPi-1]**

```bash
timeout 4 bash -c "</dev/tcp/<내 PC IP>/15674" && echo open || echo closed
curl -s -u stomp-mq:stomp-mq http://<내 PC IP>:15672/api/whoami
```

- `open`이 나오고 `{"name":"stomp-mq",...}`가 돌아오면 됩니다.
- `closed`면 내 PC의 Windows 방화벽이나 네트워크 설정이 막고 있는 것입니다. 사내 보안 정책을 확인하고 15674, 15672 포트 인바운드 허용을 요청하세요.
- 응답은 오는데 `not_authorized`가 나오면 다른 RabbitMQ가 그 포트를 잡고 있는 것입니다. 2단계로 돌아갑니다.

### 4-6. PC에서 RViz로 보기 준비 (선택)

맵 생성 상태는 대시보드 MAP 탭으로도 볼 수 있습니다(7단계). RViz로 LiDAR 점과 맵을 겹쳐 더 자세히 보고 싶을 때만 이 설정을 합니다.
RViz는 PC의 WSL에서 ROS 2 토픽을 직접 받아 그리므로 PC와 RPi가 DDS로 서로를 찾을 수 있어야 합니다.

**WSL 네트워크를 mirrored로 설정** (처음 한 번)

WSL 기본값(NAT)에서는 WSL이 PC와 다른 IP를 써서 RPi가 WSL을 찾지 못합니다.
Windows의 `%USERPROFILE%\.wslconfig` 파일에 아래 내용을 넣습니다. 파일이 없으면 새로 만듭니다.

```ini
[wsl2]
networkingMode=mirrored
```

**[PC-1]** WSL을 재시작합니다. 열려 있던 WSL 창은 모두 닫힙니다.

```powershell
wsl --shutdown
```

**[PC-3]** WSL(Ubuntu 22.04) 터미널을 엽니다. ROS 2 Humble 설치는 README의 "WSL 초기 세팅"을 따릅니다. ugv_ws를 받아 화면 표시에 필요한 패키지만 빌드합니다.

```bash
cd ~ && git clone -b ros2-humble-develop https://github.com/ubisamRAD/ugv_ws.git
cd ~/ugv_ws
source /opt/ros/humble/setup.bash
colcon build --packages-select ugv_roarm_description ugv_description
```

이미 받아 둔 ugv_ws가 있으면 `git pull origin ros2-humble-develop` 후 같은 빌드 명령을 실행합니다.

**[RPi-1]** RPi의 DDS 피어를 내 PC IP로 바꿉니다.

```bash
nano ~/cyclonedds.xml          # <Peer address="<내 PC IP>"/>
```

이 파일은 실행 중인 노드에 바로 반영되지 않습니다. 고친 뒤에는 [RPi-2]의 `ugv-launch`와 [RPi-3]의 `ugv-nav`/SLAM을 Ctrl+C로 끄고 다시 띄웁니다.
launch 인자나 `bridge_params.yaml`을 바꿔도 이 값은 따라 바뀌지 않습니다.

**[PC-3]** RPi 토픽이 들어오는지 확인합니다. RViz를 띄우기 전에는 매번 아래 환경 설정을 먼저 실행합니다.

```bash
source /opt/ros/humble/setup.bash
source ~/ugv_ws/install/setup.bash
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file://$HOME/ugv_ws/src/ugv_main/ugv_bridge/config/cyclonedds.xml
unset ROS_DOMAIN_ID ROS_LOCALHOST_ONLY
ros2 topic hz /scan            # 약 10Hz가 나오면 Ctrl+C
```

- 레포의 `cyclonedds.xml`에는 RPi IP(192.168.0.71)가 피어로 들어 있습니다. RPi IP가 다르면 이 파일도 고칩니다.
- 다른 프로젝트 때문에 `~/.bashrc`에 `ROS_DOMAIN_ID`나 `ROS_LOCALHOST_ONLY`를 넣어 두었다면 RPi 토픽이 보이지 않습니다. 위의 `unset`이 그 설정을 이 창에서만 끕니다.

## 5. RPi: 남은 프로세스 정리 (기동 전 매번)

같은 launch를 여러 번 띄우면 드라이버가 같은 시리얼 포트를 동시에 잡고, 같은 이름의 노드가 겹쳐 토픽이 나오지 않습니다.
SSH 창을 Ctrl+C 없이 닫았거나 다른 사람이 띄워 둔 launch가 남아 있기도 하니 기동 전에 항상 확인합니다.

**[RPi-1]**

```bash
pgrep -af "ros2 launch"
```

아무것도 안 나오면 6단계로 넘어갑니다. 뭔가 떠 있으면, 다른 사람이 쓰고 있지 않은지 확인한 뒤 전부 내립니다.

**[RPi-1]**

```bash
pkill -9 -f "ros2.*launch|robot_state_pub|ugv_driver_node|roarm_driver_node|rf2o_laser|ldlidar|bridge_node|static_transform|cartographer|planner_server|controller_server|bt_navigator|behavior_server|lifecycle_manager"
sleep 2
pgrep -af "ros2 launch|_node|cartographer|nav2" || echo "All clean"
```

`All clean`이 나올 때까지 반복합니다.

## 6. RPi: 로봇 기동

### 6-1. LiDAR 연결 위치

- LiDAR는 **지금 꽂혀 있는 RPi USB 구멍에서 빼지 마세요.** launch가 ttyUSB 번호가 아니라 꽂힌 위치(`/dev/serial/by-path/...usb-0:1.4...`)로 LiDAR를 찾습니다.
- 다른 구멍으로 옮겼다면 [RPi-1]에서 `ls -l /dev/serial/by-path/`로 새 경로를 확인하고 아래 기동 명령 뒤에 `lidar_port:=<경로>`를 붙입니다.
- 로봇팔은 `roarm_port` 인자를 주지 않으면 띄우지 않습니다.

### 6-2. 기동

**[RPi-2]** PowerShell을 하나 더 열고 접속한 뒤 기동합니다. 로봇이 켜져 있는 동안에는 이 창에 다른 명령을 칠 수 없습니다.

```powershell
ssh pi@192.168.0.71
```

```bash
ugv-launch stomp_host:=<내 PC IP>
```

| 인자 | 기본값 | 설명 |
|------|--------|------|
| `stomp_host` | `bridge_params.yaml` 값 | 대시보드 Docker를 띄운 PC IP |
| `oauth2_jwks_uri` | 비어 있음(검증 끔) | 브리지 REST(FastAPI)에서 JWT를 검증할 때 `http://<PC IP>:9020/oauth2/jwks` |
| `lidar_port` | USB 1.4번 구멍의 by-path 경로 | LiDAR 시리얼 포트 |
| `lidar_angle_crop` | `false` (360도 전체) | 로봇팔을 다시 달면 `true`. 팔이 가리는 후방 210~329도를 스캔에서 뺌 |
| `roarm_port` | 비어 있음(로봇팔 노드 안 띄움) | RoArm 시리얼 포트 |

[RPi-2]에 아래 줄이 보이면 정상입니다. IP가 내 PC IP인지 꼭 확인하세요.

```
[ugv_bridge]: STOMP connected to ws://<내 PC IP>:15674/ws
```

### 6-3. 토픽 확인

**[RPi-1]** 각 명령은 몇 초 뒤 Ctrl+C로 멈춥니다.

```bash
ros2 topic hz /scan       # 약 10Hz
ros2 topic hz /odom       # 약 10Hz
ros2 topic hz /voltage    # 약 20Hz
```

### 6-4. 대시보드에서 확인

브라우저를 새로고침합니다. 아래 값이 들어오면 실기 연결은 끝입니다.

- ROBOT STATUS의 Battery가 11 V 안팎으로 표시됩니다.
- Yaw (LiDAR odom), Yaw (IMU)가 로봇을 돌리면 바뀝니다.
- LIDAR 탭에 점이 찍힙니다.
- DRIVE CONTROL의 방향 버튼을 누르고 있는 동안 로봇이 움직이고 떼면 0.5초 안에 멈춥니다.

## 7. 맵 만들기

맵은 Cartographer SLAM(`slam_real.launch.py`)으로 만듭니다. [RPi-2]의 `ugv-launch`는 그대로 둡니다.
Nav2와 SLAM은 둘 다 Cartographer를 띄우므로 **동시에 띄우면 안 됩니다.** [RPi-3]에서 `ugv-nav`가 돌고 있으면 그 창에서 Ctrl+C로 먼저 끕니다.

1. **[RPi-3]** 처음이면 PowerShell을 하나 더 열고 `ssh pi@192.168.0.71`로 접속합니다. 이미 열려 있으면 프롬프트가 돌아온 상태에서 그대로 씁니다. SLAM을 시작합니다.
   ```bash
   ros2 launch ugv_roarm_description slam_real.launch.py
   ```
2. 만들어지는 맵을 띄워 둡니다. 둘 중 편한 쪽을 쓰면 됩니다.
   - **브라우저** 대시보드 MAP 탭. SLAM이 만드는 맵이 1초 간격으로 갱신됩니다. 따로 설치할 것이 없습니다.
   - **[PC-3]** RViz. 4-6을 마친 경우에만 됩니다. 4-6의 환경 설정 5줄을 실행한 뒤 띄웁니다.
     ```bash
     LIBGL_ALWAYS_SOFTWARE=1 rviz2 -d $(ros2 pkg prefix ugv_roarm_description)/share/ugv_roarm_description/rviz/slam_view.rviz
     ```
     맵(`/map`), LiDAR 점(`/scan`), 로봇 모델이 위에서 내려다본 시점으로 보입니다.
     PC에서 `slam_real.launch.py use_rviz:=true`를 실행하지 마세요. RPi와 별개로 SLAM이 하나 더 떠서 맵이 꼬입니다.
3. **브라우저** DRIVE CONTROL로 공간을 천천히 한 바퀴 돕니다.
   - Linear 속도는 0.05~0.1 m/s 정도로 낮게 둡니다. 빨리 돌면 맵이 틀어집니다.
   - 같은 곳을 한 번 더 지나가면 루프 클로저로 맵이 보정됩니다.
   - 벽이 두 겹으로 보이거나 맵이 비틀리면 SLAM을 끄고 처음부터 다시 합니다.
4. **[RPi-1]** 맵이 마음에 들면 **SLAM을 켠 상태에서** 저장합니다. 이름을 생략하면 `map_날짜_시각`으로 저장됩니다.
   ```bash
   ~/ugv_ws/save_map.sh lab_map_20261117
   ```
   `[save_map] 완료`와 함께 `.pbstream`, `.pgm`, `.yaml` 세 파일이 나오면 저장된 것입니다.
   SLAM을 먼저 끄면 저장할 대상이 없어서 실패합니다. Ctrl+C만으로는 저장되지 않습니다.
5. **[RPi-3]** 저장을 확인한 뒤 Ctrl+C로 SLAM을 끕니다. RViz를 띄웠다면 [PC-3]에서도 창을 닫거나 Ctrl+C로 끕니다.
6. **[RPi-1]** 파일을 확인합니다.
   ```bash
   ls -lh ~/maps/
   ```

## 8. 맵 교체

`ugv-nav`는 `~/maps/lab_map.pbstream`을 불러옵니다. 새 맵으로 바꾸려면 기존 파일을 백업하고 새 파일을 그 이름으로 복사합니다.

**[RPi-1]** `<새 맵 이름>`은 7단계에서 저장한 이름으로 바꿉니다.

```bash
cd ~/maps
cp lab_map.pbstream lab_map_backup_$(date +%Y%m%d).pbstream
cp <새 맵 이름>.pbstream lab_map.pbstream
ls -lh ~/maps/
```

맵 파일은 빌드와 상관없어서 복사만 해 두면 다음에 `ugv-nav`를 띄울 때 새 맵이 쓰입니다.
이름을 바꾸지 않고 시험만 해 보려면 9단계에서 `ugv-nav` 대신 아래처럼 경로를 직접 넘깁니다.

**[RPi-3]**

```bash
ugv-nav pbstream:=/home/pi/maps/<새 맵 이름>.pbstream
```

Nav2가 쓰는 건 `.pbstream`입니다. 같이 저장되는 `.pgm`/`.yaml`은 확인과 보관용입니다.

## 9. Nav2로 자율주행 확인

1. **[RPi-1]** SLAM이 남아 있지 않은지 확인합니다. `rasp_bringup` 하나만 보여야 합니다.
   ```bash
   pgrep -af "ros2 launch"
   ```
2. **[RPi-3]** 프롬프트가 돌아온 상태에서 Nav2를 띄웁니다. 이 창은 Nav2가 켜져 있는 동안 계속 차지됩니다.
   ```bash
   ugv-nav
   ```
   아래 줄이 보이면 준비된 것입니다.
   ```
   [lifecycle_manager_navigation]: Managed nodes are active
   ```
3. **브라우저** MAP 탭에서 맵과 로봇 위치를 확인합니다.
   - 좌클릭 드래그로 화면을 옮기고 우클릭 드래그로 회전합니다.
   - Cartographer가 저장된 맵에서 스스로 위치를 찾습니다. 처음 몇 초는 위치가 튈 수 있으니 로봇을 조금 움직여 위치가 맵에 맞는지 봅니다.
4. **브라우저** **Shift + 좌클릭**으로 목표 지점을 찍습니다. Shift를 누른 채 드래그하면 도착 방향도 정할 수 있습니다.
5. **브라우저** 경로가 그려지고 로봇이 출발하면, NAVIGATION Status가 `navigating`을 거쳐 `succeeded`로 바뀌는지 확인합니다.
6. **브라우저** 멈추려면 맵 위 상태 칩의 **X** 버튼을 누릅니다. 급하면 DRIVE CONTROL의 정지 버튼을 누릅니다.

## 10. 종료

띄운 순서의 반대로 끕니다.

1. **[RPi-3]** Ctrl+C로 `ugv-nav`를 끄고 프롬프트가 돌아오면 `exit`로 창을 닫습니다.
2. **[RPi-2]** Ctrl+C로 `ugv-launch`를 끄고 `exit`로 닫습니다.
3. **[RPi-1]** 남은 게 없는지 확인하고 `exit`로 닫습니다.
   ```bash
   pgrep -af "ros2 launch" || echo "All clean"
   ```
4. **[PC-2]** Ctrl+C로 `npm run dev`를 끕니다.
5. **[PC-1]** 컨테이너를 내립니다.
   ```powershell
   cd ugv-frontend
   docker compose -f Dockerfile-robot.yml stop
   ```
   `down -v`를 쓰면 OAuth2 DB 볼륨까지 지워지니 필요할 때만 씁니다.

## 11. 자주 겪는 문제

| 증상 | 원인 | 확인과 조치 |
|------|------|-------------|
| 대시보드 STOMP 연결이 바로 끊김, 토큰 오류 | 같은 이미지의 OAuth2, STOMP 서버가 두 벌 떠서 토큰 발급 서버와 검증 서버가 다름 | 2단계 포트 확인. 브라우저 사이트 데이터를 지우고 다시 로그인 |
| Connected인데 값이 전부 0 | 브리지가 내 PC 브로커에 안 붙음 | [RPi-2] 로그의 `STOMP connected to ws://<IP>`가 내 PC IP인지 확인. 아니면 `stomp_host` 인자 확인 |
| yaml을 고쳤는데 그대로임 | 빌드 안 함 | 4-3의 빌드 명령 실행 후 [RPi-2]를 다시 띄움 |
| `ugv-launch stomp_host:=...`가 grep 에러를 냄 | `~/.bashrc`가 아직 alias | 4-4 |
| 브리지 로그 `Access refused for user 'stomp-mq'` | 내 PC 15674를 다른 RabbitMQ가 잡고 있음 | 2단계 |
| LiDAR 0 pts, 로그에 `ldlidar ... process has died` | LiDAR가 다른 USB 구멍에 꽂힘 | 6-1 |
| 토픽이 하나도 안 나옴 | launch 중복 실행 | 5단계로 전부 정리 후 한 번만 기동 |
| MAP 탭이 비어 있음 | Nav2나 SLAM이 안 떠 있음, 또는 RPi :8081 응답 없음 | [RPi-3] 로그 확인, [PC-1]에서 `curl http://192.168.0.71:8081/api/health` |
| SLAM을 끈 뒤 `~/maps`에 새 파일이 없음 | Ctrl+C로는 저장되지 않음 | SLAM을 다시 켜고 7-4의 `save_map.sh`로 저장한 뒤 끔 |
| [PC-3]에서 `ros2 topic hz /scan`이 아무것도 안 나옴 | WSL이 NAT 모드, RPi `~/cyclonedds.xml` 피어가 다른 IP, 또는 `ROS_DOMAIN_ID`/`ROS_LOCALHOST_ONLY` 설정 | 4-6 다시 확인. Windows 방화벽이 UDP를 막는지도 확인 |
| [PC-3]에서 `does not match an available interface` | 예전 `cyclonedds.xml`에 네트워크 인터페이스 이름(eth1 등)이 고정됨 | 4-6처럼 최신 코드를 pull |
| `ros2 topic list`에 다른 프로젝트 토픽이 보임 | 같은 네트워크의 다른 ROS 2 장비 | `ROS_DOMAIN_ID`를 따로 쓰는지 확인 |
