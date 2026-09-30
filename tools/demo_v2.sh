#!/usr/bin/env bash
# v2 시연(Isaac v2 스테이지 → 팔 노드 v2 → 어댑터 스택 → 관제 웹)을 한 명령으로 띄우고 내린다.
#
#   tools/demo_v2.sh up       기동 전 확인 → stage → PLAY 대기 → arm → 계획 캐시 16/16 대기 → stack → web → 준비
#   tools/demo_v2.sh down     이름으로 C-c(browser·cap·web·stack·arm → stage), exit 코드 확인. 안 내려가면 보고만 한다
#   tools/demo_v2.sh status   띄울 때와 지금의 트리 sha·install 시각, 세션마다 떠 있는지·기동 시각과 로그의 주요 줄
#   tools/demo_v2.sh env      쓰일 값(환경 변수)을 보여 준다
#   tools/demo_v2.sh cmds     up 이 칠 명령 넷을 띄우지 않고 보여 준다(확인용)
#
# 규칙(작전 9/18): 남의 Isaac 이 떠 있으면 멈추고 출력만 한다(절대 내리지 않음). 프로세스는 tmux 세션 이름으로만 다룬다
# (C-c 를 보낸다). PID kill·pkill·sudo 는 쓰지 않는다. 경로·도메인·자산·재고 파일은 환경 변수로 받는다(아래 표).
#
# 환경 변수(필수는 *):
#   P3_DOMAIN*          ROS_DOMAIN_ID. 스테이지·팔·스택·웹이 같은 값을 쓴다.
#                       기동 전 확인이 "도메인에 노드가 N 개" 로 걸리면 남의 것이 그 도메인에 있는 것이다.
#                       임시 도메인으로 피할 수 있다(P3_DOMAIN=121 처럼). **어느 값을 쓸지는 재범 결정이고**
#                       이 파일의 기본값이나 도메인 규칙 문서를 고치는 것이 아니다(9/21 에 두 번 있었다).
#   P3_M0609*           M0609 자산 디렉토리(Collected_m0609_gripper/, doosan-robot2/urdf/, rmpflow/ 가 그 아래)
#   P3_DISPENSER_FILE*  orchestrator 재고 파일(dispenser_file)
#   P3_ROLES            이 PC 가 띄울 역할(기본: 월드의 전부). 두 마스터로 나눌 때(재범 9/23):
#                         스테이지 PC   P3_ROLES="stage"               P3_PEER=<상대 IP>  → 먼저 up
#                         나머지 PC     P3_ROLES="arm nav stack web"   P3_PEER=<상대 IP>  → 스테이지 PC 가 준비된 뒤 up
#                       스테이지가 없는 PC 는 /clock 발행자가 **정확히 1**(상대의 Isaac)이고 시각이 흐를 때만 띄운다.
#                       다른 PC 의 역할 준비(팔 캐시 등)는 기다리지 않는다 — 그 PC 의 up 이 끝난 뒤 띄운다.
#                       절차·확인은 docs/runbooks/hospital-demo.md 10절
#   P3_PEER             상대 PC 주소(예: 10.10.0.1). 주면 두 PC 모드다 — 모든 역할에 P3_FASTDDS_PROFILE 과
#                       ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET 을 넘기고, 기동 전에 상대 ping·프로필에 두 주소·
#                       LOCALHOST 제한이 없는지 본다. 비우면 한 PC(지금 동작)
#   P3_REPO             저장소(기본: 이 스크립트의 위 디렉토리)
#   P3_INSTALL          colcon install(기본: $P3_REPO/install)
#   P3_ROS_SETUP        시스템 ROS setup(기본: /opt/ros/jazzy/setup.bash). 팔·주행·스택·웹·확인 명령이 먼저 source 한다
#   P3_ORDER_POOL       주문 풀(기본: $P3_REPO/src/rokey_p3_orchestrator/config/order_pool.yaml,
#                       hospital 은 order_pool.hospital.yaml)
#   P3_WORLD            demo(기본, v0.3.0 시연 그대로), emptyworld(빈월드 한 바퀴, 카드 K6) 또는
#                       hospital(병원 씬 전 구간, #527 — 스테이지 --preset hospital, 주행 Nav2)
#   P3_ZONES            구역 파일. 주행 launch 와 웹이 같은 값을 받는다(hospital 은 스테이지도)
#                       (기본: demo 는 config/zones.yaml, emptyworld 는 config/zones.emptyworld.yaml,
#                       hospital 은 config/zones.hospital.yaml)
#   P3_ROUTES           경로 파일(emptyworld·hospital 만. 기본: config/routes.<월드>.yaml)
#   P3_UR5_ARM_PARAMS   UR5 팔 노드의 현장값 파일. **emptyworld·hospital 에서 필수**
#   P3_WORKCELL_LAYOUT  **hospital 에서 필수**. 병원 M0609 워크셀 실측 JSON(--workcell-layout, 사이트 값).
#                       sim/standalone/prepare_workcell_integration.py 가 병원 씬 + 기준 조제기에서 만든다
#   P3_POUCH_AT_END     hospital 만. 1 이면 봉투를 A1 끝 롤러 위에 바로 놓는다(S3·S4 단독 회차, --pouch-at-end)
#   P3_HOSPITAL_SCENE   hospital 만. 병원 씬(기본: $P3_REPO/sim/scenes/hospital_navigationv1.usda)
#   P3_HOSPITAL_MAP     hospital 만. Nav2 지도(기본: $P3_REPO/src/rokey_p3_navigation/config/maps/hospital.yaml)
#   P3_AMR_START        hospital 만. AMR 출발 자리 "X Y"(기본 = zones 의 dock_1: 카메라 "-8.266 4.102", 참값 "-8.995 4.686")
#   P3_HOSPITAL_RECEIVER_PRIM  hospital 카메라 기본. 봉투가 정착하는 A1 모듈 탁자 prim(스테이지 --hospital-receiver-prim).
#                       빈 값을 주면 끈다(봉투가 롤러 끝에 선다 — 그때는 P3_ZONES 도 zones.hospital.yaml 로 준다)
#   P3_AMR_COUNT        hospital 만. 합본 AMR 대수(1-4, 기본 1). 부하 측정용이고 배송은 첫 대만 한다
#   P3_BELT_TIMEOUT_S   hospital 만. 오케스트레이터 belt_timeout_s(기본 60. 병원 컨베이어 운반 34.58 s 를 잼, #240)
#   P3_AMR_COMBINED     AMR 합본(ridgeback_ur5.usd) 경로. 주면 그 구성으로 띄운다. 비우면 받침대 UR5.
#                       **hospital 에서 필수**(롤러 끝에서 합본 팔이 집는다)
#                       합본은 팔 params 도 다르다(joint_names 의 ur_arm_*, arm_base_frame_convention).
#                       기동 전 확인이 그 두 줄이 params 파일에 있는지 본다 — 없으면 조용히 틀린다
#   P3_AMR_COMBINED_ARG 합본을 켜는 스테이지 인자 이름(기본 --amr-combined). 시뮬이 확정하면 그 값으로
#   P3_AUTO_ORDER       emptyworld 에서 1 이면 자동 주문 발행기도 띄운다. 기본은 끔 — 자동 트립이 먼저 뜨면
#                       사람이 넣은 요청이 409 trip_in_progress 가 된다(실습29). demo 월드는 늘 띄운다
#   P3_SIM_SENSORS      1 이면 스테이지 --sim-sensors 와 스택의 시뮬 센서 묶음(어댑터 둘 + 팔 둘)을 같이 켠다.
#                       주문 풀 경로가 스택·웹·스테이지에서 같아야 한다(인증의 tag_id 가 그 파일에서 나온다)
#   P3_CAMERA_POUCHES   한 바퀴 월드(emptyworld·hospital)에서 1 이면 봉투 검출을 **카메라**로 한다(기본 0, **병원 1** — 재범 9/29
#                       "QR 반드시 찍고"). 스택: stub_detector 끔 + pouch_detector(color + QR) + pouch_source:=camera +
#                       벨트 관측 자세. 봉투 QR 이 주문과 맞아야 집는다. 스테이지: 봉투에 QR 텍스처(--qr-dir)
#   P3_CAMERA_TAGS      카메라 모드에서 1 이면 인식표(pt-·st-)도 손 카메라 QR 로 읽는다(scan_tag_source:=camera).
#                       기본 0, 병원은 P3_CAMERA_POUCHES 를 따른다. 0 이면 인식표만 참값 센서(P3_SIM_SENSORS=1)다
#   P3_BELT_VIEW_STANDOFF  카메라 모드의 벨트 관측 거리 m(기본 0.30, 제안값·L3 미확인). 검출 고정 거리는 이 값 - 봉투 두께
#   P3_BELT_VIEW_OFFSET    관측점을 벨트 끝에서 진행 방향으로 옮기는 양 m(기본 -0.075 = 끝 구역 0.15 의 가운데)
#   P3_CAMERA_RESOLUTION  카메라 모드 + 합본의 손 카메라 해상도 "W H"(기본 "1280 800" = D455 컬러 기본값).
#                       9/23 L3: 640 폭에서 QR 한 변 58 px 로 판독 실패. 렌더 비용이 늘어 rtf 를 기록한다
#   P3_CONTAINER_QR     1 이면 약통 QR 로 보충 전 장착 여부를 확인한다(카드 Q1). 기본: hospital 1, 그 밖 0
#                       스테이지: 약통 QR 면(--catalog --canister-qr-dir) + M0609 손 카메라(--m0609-hand-camera).
#                       스택: M0609 QR 판독(use_m0609_detector) + 약 DB 서비스(pharmacy_db). 팔: container_check
#   P3_CATALOG          약 DB 카탈로그(기본 $P3_REPO/src/rokey_p3_orchestrator/config/pharmacy_catalog.yaml)
#   P3_CAMERA_VIEW      1 이면 손 카메라 이미지를 작은 창(rqt_image_view)으로 띄운다(기본 0, 발표 영상용).
#                       화면이 있어야 하고(headless 면 끈다) 구독이 하나 늘 뿐 렌더는 늘지 않는다. rtf 는 기록한다
#   P3_QR_DIR           카메라 모드의 QR 텍스처 디렉토리(기본 $P3_REPO/sim/outputs/qr, Git 밖)
#   P3_HEADLESS         1 이면 화면 없이 띄운다. 스테이지 --headless, 창 인자·브라우저·주기 캡처를 모두 끈다.
#                       콘솔에 사람이 있거나 콘솔이 잠겨 있을 때 쓴다(headless 는 화면 잠금과 무관하다)
#   P3_ISAAC_PY         Isaac python.sh(기본: $HOME/isaacsim/python.sh)
#   P3_ISAAC_BRIDGE_LIB Isaac 내부 Jazzy 라이브러리(기본: $HOME/isaacsim/exts/isaacsim.ros2.bridge/jazzy/lib)
#   P3_FASTDDS_PROFILE  Isaac 쪽 FASTRTPS_DEFAULT_PROFILES_FILE(기본: $HOME/.ros/fastdds_whitelist.xml, 없으면 안 넘김).
#                       두 PC 모드(P3_PEER)면 모든 역할에 넘기고, 없으면 멈춘다
#   P3_WEB_PY           웹 백엔드 python(기본: $P3_REPO/web/backend/.venv/bin/python)
#   P3_WEB_HOST/PORT    웹 bind(기본 127.0.0.1 / 8000)
#   P3_V2_SEED          팔 v2_seed 와 스테이지 --seed(진열·봉투 스폰)(기본 7). 둘이 같은 값이어야 한 회차의 seed 가 하나다
#   P3_V2_GUARDED_MODULE_PATH  기본 false(기존 시연 경로). 새 경로 L3 실행은 true 로 명시한다
#   P3_V2_RAIL_SELECT   M0609 레일 후보 순서 preferred_first(기본, 재범 9/29 "디폴트로 켜서") | first_feasible(되돌리기)
#   P3_RUN_HOST         run ID 호스트 칸(기본: hostname)
#   P3_LOG_DIR          로그 디렉토리(기본: $HOME/p3_demo_logs). 파일 이름에 기동 시각이 붙는다
#   P3_SESSION_PREFIX   tmux 세션 이름 앞부분(기본 p3v2 → p3v2-stage·-arm·-stack·-web·-cap·-browser)
#   P3_SCREEN_SIZE      발표 화면 "W H"(기본 "2048 1152" = master02 패널, 리허설 값. 발표장은 그 화면 값으로). 화면 반반(재범 9/18):
#                       Isaac 은 --window-half left --screen-size W H(스테이지가 이 인자를 알 때만), 브라우저는 W/2 x H
#   P3_ISAAC_WINDOW     half(기본, Isaac 왼쪽 반) | full(화면 전체 — 촬영 테이크, hospital-full.md 6절)
#   P3_RENDER_MAX       주면 스테이지 렌더 상한 WxH 로 넘긴다(기본 1280x720, 빈 값 = 상한 없음). 테이크는 1920x1080
#   P3_STAGE_ARGS       스테이지에 더 넘길 인자
#   P3_BROWSER          웹을 띄울 브라우저(기본 비움 = 안 띄움. 예: firefox)
#   P3_BROWSER_WIDTH/HEIGHT  브라우저 창 크기(기본 P3_SCREEN_SIZE 의 W/2, H). firefox 의 -width/-height 로 넘긴다.
#                       창 위치는 못 정한다(master02 에 wmctrl·xdotool 없음). 창 관리자가 무시하면 Super+→
#   P3_WEB_QUERY        웹 주소 뒤에 붙일 쿼리(기본 ?demo=1 = 프론트 시연 모드, #217. 빈 값으로 두면 일반 화면)
#   P3_CAPTURE_EVERY    N 초 간격 화면 캡처(기본 0 = 끔). gst-launch-1.0(ximagesrc) 또는 xwd 가 있을 때만, 없으면 끈다
#   P3_CAPTURE_WINDOW   캡처할 창 이름 일부(xwininfo 가 있으면 그 창만, 없거나 못 찾으면 화면 전체)
#   P3_ISAAC_PATTERN    "남의 Isaac" 을 찾는 pgrep -f 식(기본: isaacsim.exp.full.kit|isaacsim/python.sh|/kit/kit )
#   P3_STAGE_TIMEOUT_S·P3_ARM_TIMEOUT_S·P3_STACK_TIMEOUT_S·P3_WEB_TIMEOUT_S·P3_DOWN_TIMEOUT_S  기다림 시한(초)
#   P3_STAGE_READY·P3_ARM_READY·P3_STACK_READY  준비로 보는 로그 줄(grep -E)
#   P3_STAGE_CMD·P3_ARM_CMD·P3_NAV_CMD·P3_STACK_CMD·P3_WEB_CMD  명령을 통째로 바꾼다(GPU 없는 시험용). 비우면 아래 기본 명령
#
# 월드(P3_WORLD)로 달라지는 것은 넷뿐이다: 스테이지 preset(+ --amr), 역할에 nav 가 붙는지,
# 스택 인자 묶음, 구역·경로 파일. 그 밖의 기동·대기·down·로그 규칙은 한 벌로 같다.
# hospital 은 "전 구간 한 바퀴" 라는 점에서 emptyworld 와 같은 쪽이다(full_loop_world). 다른 것은 스테이지 preset·
# 씬 인자, Nav2 주행 인자, 스택의 belt_timeout_s, 기본 파일(zones·routes·주문 풀)뿐이다.
set -uo pipefail

SELF_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
P3_REPO=${P3_REPO:-$(cd "$SELF_DIR/.." && pwd)}
P3_INSTALL=${P3_INSTALL:-$P3_REPO/install}
P3_ROS_SETUP=${P3_ROS_SETUP:-/opt/ros/jazzy/setup.bash}   # 시스템 ROS(Isaac 셸은 쓰지 않는다)
P3_WORLD=${P3_WORLD-demo}          # 빈 값은 기본값으로 보지 않는다(P3_V2_GUARDED_MODULE_PATH 와 같은 규칙)
case "$P3_WORLD" in
  demo|emptyworld|hospital) ;;
  *) printf '[demo_v2] P3_WORLD 는 demo, emptyworld 또는 hospital 이어야 한다: %s\n' "$P3_WORLD" >&2; exit 2 ;;
esac
full_loop_world() {  # 전 구간 한 바퀴(주행·UR5 팔이 붙는다): emptyworld 와 hospital
  [[ $P3_WORLD == emptyworld || $P3_WORLD == hospital ]]
}
if [[ $P3_WORLD == hospital ]]; then
  P3_ORDER_POOL=${P3_ORDER_POOL:-$P3_REPO/src/rokey_p3_orchestrator/config/order_pool.hospital.yaml}
  P3_CAMERA_POUCHES=${P3_CAMERA_POUCHES:-1}   # 아래 "병원은 QR 을 반드시 찍는다" 와 같은 기본. 적재 자리를 고르려고 먼저 정한다
  if [[ $P3_CAMERA_POUCHES == 1 ]]; then
    # v1.0.1 기본 = 9/29 master02 카메라 배송 성공 설정(#796, docs/practice/simworld/practice-45.md): 봉투가 A1 모듈
    # 탁자(receiver) 위에 정착하고, 합본이 탁자 앞 적재 자리에서 집는다. 재범 9/29 B안("그 자리에서 바로")대로
    # 그 적재 자리가 dock_1 이다(zones.hospital-receiver.yaml, hospital_nav_files.py --receiver).
    P3_ZONES=${P3_ZONES:-$P3_REPO/src/rokey_p3_description/config/zones.hospital-receiver.yaml}
    P3_ROUTES=${P3_ROUTES:-$P3_REPO/src/rokey_p3_description/config/routes.hospital-receiver.yaml}
    P3_AMR_START=${P3_AMR_START:--8.266 4.102}   # = zones.hospital-receiver 의 dock_1 = load
    P3_HOSPITAL_RECEIVER_PRIM=${P3_HOSPITAL_RECEIVER_PRIM-/World/P3Base/Scene/Environment/hospital/SM_SideTable_02a_74}
    P3_BELT_VIEW_OFFSET=${P3_BELT_VIEW_OFFSET:-0}
    P3_DISPENSE_WHILE_DISPATCHING=${P3_DISPENSE_WHILE_DISPATCHING:-true}
  fi
  P3_ZONES=${P3_ZONES:-$P3_REPO/src/rokey_p3_description/config/zones.hospital.yaml}
  P3_ROUTES=${P3_ROUTES:-$P3_REPO/src/rokey_p3_description/config/routes.hospital.yaml}
  P3_HOSPITAL_SCENE=${P3_HOSPITAL_SCENE:-$P3_REPO/sim/scenes/hospital_navigationv1.usda}
  P3_HOSPITAL_MAP=${P3_HOSPITAL_MAP:-$P3_REPO/src/rokey_p3_navigation/config/maps/hospital.yaml}
  # = zones.hospital 의 dock_1. 9/29 재범 B안: A1 충전 도크를 적재 자리로 옮겼다(도크에서 바로 파지, 전 -7.272 4.784).
  P3_AMR_START=${P3_AMR_START:--8.995 4.686}
  P3_BELT_TIMEOUT_S=${P3_BELT_TIMEOUT_S:-60}
  P3_AMR_COUNT=${P3_AMR_COUNT:-1}   # hospital 만. 합본 AMR 대수(1-4, 부하 측정용)
  P3_DISPENSE_TIMEOUT_S=${P3_DISPENSE_TIMEOUT_S:-30}   # hospital 만. 어댑터가 Isaac Dispense 응답 시한(s, wall). 10 에서 9/24 not_ready 3회(ord-0009)
fi
P3_ORDER_POOL=${P3_ORDER_POOL:-$P3_REPO/src/rokey_p3_orchestrator/config/order_pool.yaml}
if [[ $P3_WORLD == emptyworld ]]; then
  P3_ZONES=${P3_ZONES:-$P3_REPO/src/rokey_p3_description/config/zones.emptyworld.yaml}
else
  P3_ZONES=${P3_ZONES:-$P3_REPO/src/rokey_p3_description/config/zones.yaml}
fi
P3_ROUTES=${P3_ROUTES:-$P3_REPO/src/rokey_p3_description/config/routes.emptyworld.yaml}
# 병원은 흡착 그리퍼+D455 가 늘 붙는다. 팔 params 를 안 주면 그 구성의 저장소 파일을 쓴다 — 봉투를 카메라로 찾으면
# camera 파일, 참값 센서면 gripper 파일(흡착점 0.1555 는 같고 pouch_source 만 sim). 마클1 회차2(232931c)에서
# P3_CAMERA_POUCHES=0 인데 camera 파일이 잡혀 A1 검출 0건이었다.
# 병원은 QR 을 반드시 찍는다(재범 9/29: "QR 반드시 찍고 가져가야함", "병상 QR 을 찍고 약을 찍어서 매칭한 다음 내려놓기").
# 봉투는 카메라 QR 이 주문과 맞아야 집고(pick_permission.select_detection), 인식표도 카메라로 읽는다.
# 참값 센서 집기(0)는 명시적으로 줄 때만이다. 9/23 작전 결정(리하 v0 참값)을 대신한다.
if [[ $P3_WORLD == hospital ]]; then
  P3_CAMERA_POUCHES=${P3_CAMERA_POUCHES:-1}
  P3_CAMERA_TAGS=${P3_CAMERA_TAGS:-$P3_CAMERA_POUCHES}
fi
if [[ $P3_WORLD == hospital ]]; then
  if [[ ${P3_CAMERA_POUCHES:-0} == 1 ]]; then
    # 성공 회차 팔 설정(손목 고정 + 실측 추가 하강 0.05 m, 근본 수정 아님 — #796).
    P3_UR5_ARM_PARAMS=${P3_UR5_ARM_PARAMS:-$P3_REPO/src/rokey_p3_manipulation/config/ur5_arm.amr-combined.camera-receiver.yaml}
  else
    P3_UR5_ARM_PARAMS=${P3_UR5_ARM_PARAMS:-$P3_REPO/src/rokey_p3_manipulation/config/ur5_arm.amr-combined.gripper.yaml}
  fi
else
  P3_UR5_ARM_PARAMS=${P3_UR5_ARM_PARAMS:-}
fi
P3_WORKCELL_LAYOUT=${P3_WORKCELL_LAYOUT:-}
P3_POUCH_AT_END=${P3_POUCH_AT_END:-0}
P3_SIM_SENSORS=${P3_SIM_SENSORS:-0}     # emptyworld 만. 스테이지 --sim-sensors + 스택의 어댑터·팔 인자 넷
# 한 바퀴 월드(emptyworld·hospital). 1 이면 봉투 검출을 카메라로(pouch_detector). 기본 0, **병원은 1**(위).
# 9/23 작전 결정(리하 v0 참값, 41725ff 에서 카메라 QR 57 px 로 not_detected ×2)은 재범 9/29 지시로 병원에서 바뀌었다.
P3_CAMERA_POUCHES=${P3_CAMERA_POUCHES:-0}
# 1 이면 인식표(환자 pt-·스테이션 st-)도 손 카메라로 읽는다(scan_tag_source:=camera). 카메라 모드에서만 뜻이 있다.
# 기본 0, 병원은 P3_CAMERA_POUCHES 를 따른다(위). 0 이면 인식표만 참값 센서다(예전 카메라 모드).
P3_CAMERA_TAGS=${P3_CAMERA_TAGS:-0}
P3_DECK_VISION=${P3_DECK_VISION:-0}     # 1 = 상판 집기 비전 교차 확인(재범 9/25, P3_SIM_SENSORS=1 과 같이)
P3_BELT_VIEW_STANDOFF=${P3_BELT_VIEW_STANDOFF:-0.30}
P3_BELT_VIEW_OFFSET=${P3_BELT_VIEW_OFFSET:--0.075}
P3_POUCH_HEIGHT=${P3_POUCH_HEIGHT:-0.01}   # 스테이지 DEFAULT_POUCH_SIZE 의 z 와 같아야 한다
P3_QR_DIR=${P3_QR_DIR:-$P3_REPO/sim/outputs/qr}
P3_CAMERA_VIEW=${P3_CAMERA_VIEW:-0}
# 병원은 기본으로 켠다(재범 9/23: M0609 RealSense·합본 흡착 그리퍼+RealSense 를 붙여 실습한다). 끄려면 0 을 준다.
if [[ $P3_WORLD == hospital ]]; then P3_CONTAINER_QR=${P3_CONTAINER_QR:-1}; else P3_CONTAINER_QR=${P3_CONTAINER_QR:-0}; fi
P3_CATALOG=${P3_CATALOG:-$P3_REPO/src/rokey_p3_orchestrator/config/pharmacy_catalog.yaml}
P3_CAMERA_RESOLUTION=${P3_CAMERA_RESOLUTION:-1280 800}
P3_AUTO_ORDER=${P3_AUTO_ORDER:-0}       # emptyworld 만. 1 이면 자동 주문 발행기도 띄운다(기본 끔)
P3_AMR_COMBINED=${P3_AMR_COMBINED:-}    # AMR 합본 USD 경로. 비우면 받침대 UR5(지금 동작)
#: AMR 합본을 켜는 스테이지 인자 이름. **시뮬이 확정하면 이 한 줄만 고친다.**
P3_AMR_COMBINED_ARG=${P3_AMR_COMBINED_ARG:---amr-combined}
P3_HEADLESS=${P3_HEADLESS:-0}
P3_ISAAC_PY=${P3_ISAAC_PY:-$HOME/isaacsim/python.sh}
P3_ISAAC_BRIDGE_LIB=${P3_ISAAC_BRIDGE_LIB:-$HOME/isaacsim/exts/isaacsim.ros2.bridge/jazzy/lib}
P3_FASTDDS_PROFILE=${P3_FASTDDS_PROFILE:-$HOME/.ros/fastdds_whitelist.xml}
P3_WEB_PY=${P3_WEB_PY:-$P3_REPO/web/backend/.venv/bin/python}
P3_WEB_HOST=${P3_WEB_HOST:-127.0.0.1}
P3_WEB_PORT=${P3_WEB_PORT:-8000}
P3_V2_SEED=${P3_V2_SEED:-7}
P3_V2_GUARDED_MODULE_PATH=${P3_V2_GUARDED_MODULE_PATH-false}
P3_V2_RAIL_SELECT=${P3_V2_RAIL_SELECT-preferred_first}
P3_RUN_HOST=${P3_RUN_HOST:-$(hostname)}
P3_LOG_DIR=${P3_LOG_DIR:-$HOME/p3_demo_logs}
P3_SESSION_PREFIX=${P3_SESSION_PREFIX:-p3v2}
P3_STAGE_ARGS=${P3_STAGE_ARGS:-}
P3_SCREEN_SIZE=${P3_SCREEN_SIZE:-2048 1152}
P3_ISAAC_WINDOW=${P3_ISAAC_WINDOW:-half}   # half = 왼쪽 반(발표 반반 화면), full = 화면 전체(촬영 테이크, 런카드 6절)
read -r SCREEN_W SCREEN_H _ <<<"$P3_SCREEN_SIZE"
P3_BROWSER=${P3_BROWSER:-}
P3_BROWSER_WIDTH=${P3_BROWSER_WIDTH:-$((SCREEN_W / 2))}
P3_BROWSER_HEIGHT=${P3_BROWSER_HEIGHT:-$SCREEN_H}
P3_WEB_QUERY=${P3_WEB_QUERY-?demo=1}     # 빈 값을 주면 빈 값 그대로(일반 화면)
P3_CAPTURE_EVERY=${P3_CAPTURE_EVERY:-0}
# headless 에서는 볼 화면이 없다. 캡처·브라우저를 켜 두면 DISPLAY 없이 실패만 남는다.
if [[ $P3_HEADLESS == 1 ]]; then P3_CAPTURE_EVERY=0; P3_BROWSER=''; P3_CAMERA_VIEW=0; fi
P3_CAPTURE_WINDOW=${P3_CAPTURE_WINDOW:-}
P3_ISAAC_PATTERN=${P3_ISAAC_PATTERN:-isaacsim.exp.full.kit|isaacsim/python.sh|/kit/kit }
# 병원은 씬·조제기·워크셀을 다 싣고 충돌체를 굽느라 기동이 길다(9/23: 빈월드 대비 몇 배). 900 s 로 둔다.
if [[ $P3_WORLD == hospital ]]; then
  P3_STAGE_TIMEOUT_S=${P3_STAGE_TIMEOUT_S:-900}
else
  P3_STAGE_TIMEOUT_S=${P3_STAGE_TIMEOUT_S:-180}
fi
P3_ARM_TIMEOUT_S=${P3_ARM_TIMEOUT_S:-420}
P3_STACK_TIMEOUT_S=${P3_STACK_TIMEOUT_S:-60}
P3_WEB_TIMEOUT_S=${P3_WEB_TIMEOUT_S:-60}
P3_DOWN_TIMEOUT_S=${P3_DOWN_TIMEOUT_S:-30}
# 빈월드는 `stage ready` 를 기다린다. `timeline_event type=PLAY` 는 스폰·센서가 붙기 **전에** 나오고,
# `ur5 spawn_settled` 는 IK 가 풀렸을 때만 나온다(시뮬 9/21). `stage ready` 는 루프 직전 조건 밖이라
# 조각이 실패해도 반드시 나온다.
if full_loop_world; then
  P3_STAGE_READY=${P3_STAGE_READY:-stage ready}
else
  P3_STAGE_READY=${P3_STAGE_READY:-timeline_event type=PLAY}
fi
# 병원은 워크셀이 18칸이고 모듈 칸 계획은 실습37부터 안 풀린다. 데모는 원통(drug-amox)만 쓰므로
# 준비 조건을 **종류**로 본다(작전 9/23). 팔이 집계 뒤에 찍는 `완료 종류:` 줄을 기다린다 —
# 하나도 완료가 아니면 그 자리가 `(없음)` 이라 집계의 종류 이름에 걸리지 않는다. 모듈은 별도 카드다.
if [[ $P3_WORLD == hospital ]]; then
  P3_ARM_READY=${P3_ARM_READY:-완료 종류: .*cylinder}
else
  P3_ARM_READY=${P3_ARM_READY:-v2 계획 캐시: 16/16칸}
fi
P3_STACK_READY=${P3_STACK_READY:-orchestrator up}
P3_NAV_READY=${P3_NAV_READY:-fleet up}
P3_NAV_TIMEOUT_S=${P3_NAV_TIMEOUT_S:-60}

if full_loop_world; then
  ROLES=(stage arm nav stack web)     # 빈월드·병원은 실물 주행이 붙는다
  DOWN_ORDER=(camview browser cap web stack nav arm)
else
  ROLES=(stage arm stack web)
  DOWN_ORDER=(camview browser cap web stack arm)
fi
# 이 PC 가 띄울 역할(P3_ROLES). 월드의 역할 가운데서만 고르고, 순서는 월드 순서를 따른다.
WORLD_ROLES=("${ROLES[@]}")
P3_ROLES=${P3_ROLES:-${WORLD_ROLES[*]}}
for role in $P3_ROLES; do
  if [[ " ${WORLD_ROLES[*]} " != *" $role "* ]]; then
    printf '[demo_v2] P3_ROLES 의 %s 는 이 월드(%s)의 역할이 아니다: %s\n' "$role" "$P3_WORLD" "${WORLD_ROLES[*]}" >&2
    exit 2
  fi
done
ROLES=()
for role in "${WORLD_ROLES[@]}"; do [[ " $P3_ROLES " == *" $role "* ]] && ROLES+=("$role"); done
((${#ROLES[@]})) || { printf '[demo_v2] P3_ROLES 가 비었다\n' >&2; exit 2; }
has_role() { [[ " ${ROLES[*]} " == *" $1 "* ]]; }
DOWN_ORDER=($(for role in "${DOWN_ORDER[@]}"; do
  case $role in camview|browser|cap) echo "$role" ;; *) has_role "$role" && echo "$role" ;; esac
done))
#: down 이 보는 세션 전부(월드와 무관). 순서는 DOWN_ORDER 와 같은 뜻 — 화면·녹화 먼저, 팔 마지막, 스테이지는 따로.
DOWN_ALL=(camview browser cap web stack nav arm)
P3_PEER=${P3_PEER:-}
two_hosts() { [[ -n $P3_PEER ]]; }

STAMP_FILE="$P3_LOG_DIR/.current"

say() { printf '[demo_v2 %s] %s\n' "$(date +%H:%M:%S)" "$*"; }
session() { printf '%s-%s' "$P3_SESSION_PREFIX" "$1"; }
has_session() { tmux has-session -t "=$(session "$1")" 2>/dev/null; }
log_of() { printf '%s/%s-%s.log' "$P3_LOG_DIR" "$STAMP" "$1"; }
ros_env() {
  printf 'source %q && source %q/setup.bash && export ROS_DOMAIN_ID=%q' "$P3_ROS_SETUP" "$P3_INSTALL" "$P3_DOMAIN"
  # 두 PC 모드: .bashrc 에 기대지 않고 모든 역할이 같은 유선 프로필·탐색 범위로 뜬다(Isaac 은 stage_cmd 가 넘긴다).
  if two_hosts; then
    printf ' FASTRTPS_DEFAULT_PROFILES_FILE=%q ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET' "$P3_FASTDDS_PROFILE"
  fi
  return 0
}

need() {
  local missing=()
  for name in "$@"; do [[ -n ${!name:-} ]] || missing+=("$name"); done
  if ((${#missing[@]})); then
    say "필수 환경 변수가 없다: ${missing[*]} (tools/demo_v2.sh 머리 주석 참고)"
    exit 2
  fi
}

camera_pouches() {  # 봉투 검출을 카메라로 하는 구성인가(한 바퀴 월드: emptyworld·hospital)
  full_loop_world && [[ $P3_CAMERA_POUCHES == 1 ]]
}

stage_cmd() {
  if [[ -n ${P3_STAGE_CMD:-} ]]; then printf '%s' "$P3_STAGE_CMD"; return; fi
  local profile=() kit_log
  [[ -f $P3_FASTDDS_PROFILE ]] && profile=("FASTRTPS_DEFAULT_PROFILES_FILE=$P3_FASTDDS_PROFILE")
  kit_log="$P3_LOG_DIR/$STAMP-kit.log"
  # Isaac 셸은 시스템 ROS 를 source 하지 않는다(sim/README 0.5단계 절차 0 의 env -i 배열이 정본). 화면 변수는 넘긴다.
  printf 'cd %q && ' "$P3_REPO"
  if camera_pouches || [[ $P3_CONTAINER_QR == 1 || $P3_WORLD == hospital ]]; then
    # QR 텍스처. 시스템 python3(OpenCV 또는 qrcode)로 주문 풀(봉투 ord-)과 카탈로그(약통 cn-)에서 만든다.
    printf '/usr/bin/python3 sim/standalone/make_qr_textures.py --order-pool %q --catalog %q --out %q && ' \
      "$P3_ORDER_POOL" "$P3_CATALOG" "$P3_QR_DIR"
  fi
  printf 'env -i HOME=%q USER=%q TERM=%q PATH=/usr/local/bin:/usr/bin:/bin' \
    "$HOME" "${USER:-}" "${TERM:-xterm}"
  for var in DISPLAY XAUTHORITY XDG_RUNTIME_DIR; do
    [[ -n ${!var:-} ]] && printf ' %s=%q' "$var" "${!var}"
  done
  printf ' ROS_DISTRO=jazzy RMW_IMPLEMENTATION=rmw_fastrtps_cpp ROS_DOMAIN_ID=%q' "$P3_DOMAIN"
  ((${#profile[@]})) && printf ' %q' "${profile[@]}"
  # 렌더 상한(views.render_max). 주면 그대로 넘긴다 — 빈 값은 "상한 없음" 이라 설정 여부로 가른다(촬영 테이크 1920x1080).
  [[ -n ${P3_RENDER_MAX+x} ]] && printf ' P3_RENDER_MAX=%q' "$P3_RENDER_MAX"
  printf ' LD_LIBRARY_PATH=%q %q sim/standalone/pharmacy_stage.py' "$P3_ISAAC_BRIDGE_LIB" "$P3_ISAAC_PY"
  if [[ $P3_WORLD == hospital ]]; then
    # 병원 전 구간(#527). preset 이 조제실 모듈 평행이동·씬 컨베이어·AMR 을 켠다. 씬·출발 자리·합본은 사이트 값이라
    # 여기서 준다(preset 검사가 없으면 멈춘다). 주행이 Nav2 라 라이다를 단다(hospital-nav-l3 6절).
    # --zones-file 은 주행·웹과 같은 파일이다(belt_end·보관함·인식표가 여기서 나온다).
    # 조제실은 늘 병원 M0609 워크셀(실측 JSON)이다. 빈월드 조제실을 병원으로 옮겨 오지 않는다(재범 9/23) —
    # 그래서 preset hospital-full 로 되돌아가는 길은 없다. P3_WORKCELL_LAYOUT 은 병원에서 필수다.
    printf ' --preset hospital --workcell-layout %q' "$P3_WORKCELL_LAYOUT"
    printf ' --base-usd %q --amr-start %s --amr %s %q --amr-lidar --zones-file %q' \
      "$P3_HOSPITAL_SCENE" "$P3_AMR_START" "$P3_AMR_COMBINED_ARG" "$P3_AMR_COMBINED" "$P3_ZONES"
    [[ $P3_AMR_COUNT == 1 ]] || printf ' --amr-count %q' "$P3_AMR_COUNT"
    [[ $P3_POUCH_AT_END == 1 ]] && printf ' --pouch-at-end'
    [[ -n ${P3_HOSPITAL_RECEIVER_PRIM:-} ]] && printf ' --hospital-receiver-prim %q' "$P3_HOSPITAL_RECEIVER_PRIM"
    [[ $P3_SIM_SENSORS == 1 ]] && printf ' --sim-sensors'
    # 합본 손목에 흡착 그리퍼+D455 를 늘 붙인다(재범 9/23). 흡착점이 자산 값(0.1555 m)이 된다.
    printf ' --amr-hand-camera --camera-resolution %s' "$P3_CAMERA_RESOLUTION"
    # 봉투 ord- QR 은 병원 기본이다(재범 9/23: 화면에 봉투 QR 이 없었다). 카메라 모드와 무관하게 붙인다.
    printf ' --qr-dir %q' "$P3_QR_DIR"
    # 협탁 환자 인식표 판(시각 소품, 작전 9/23). 인증은 참값 센서 그대로다. pt- QR 은 주문 풀에서 만든다.
    printf ' --patient-plates'
  elif [[ $P3_WORLD == emptyworld ]]; then
    # preset 이 full_loop·ur5 와 stand-in 0 을 같이 켠다(#244 거부에 안 걸린다). --amr 은 preset 에 없다.
    # --sim-sensors 는 K4·K5 참값 센서다(--amr 과 --order-pool 을 요구한다. 시뮬 9/21).
    printf ' --preset emptyworld-loop --amr'
    [[ $P3_SIM_SENSORS == 1 ]] && printf ' --sim-sensors'
    camera_pouches && printf ' --qr-dir %q' "$P3_QR_DIR"
    # 합본에는 손 카메라가 없다(받침대 UR5 만 달았다). 카메라 모드면 손목 카메라를 단다.
    if camera_pouches && [[ -n $P3_AMR_COMBINED ]]; then
      printf ' --amr-hand-camera --camera-resolution %s' "$P3_CAMERA_RESOLUTION"
    fi
    # AMR 합본(ridgeback_ur5.usd). 받침대 UR5 와 대비되는 구성이다.
    [[ -n $P3_AMR_COMBINED ]] && printf ' %s %q' "$P3_AMR_COMBINED_ARG" "$P3_AMR_COMBINED"
  else
    printf ' --preset demo-ros-refill-v2'
  fi
  printf ' --kit-log-file %q --order-pool %q' "$kit_log" "$P3_ORDER_POOL"
  if [[ $P3_CONTAINER_QR == 1 ]]; then
    printf ' --catalog %q --canister-qr-dir %q --m0609-hand-camera' "$P3_CATALOG" "$P3_QR_DIR"
  fi
  printf ' --robot-usd %q --urdf %q --robot-description %q' \
    "$P3_M0609/Collected_m0609_gripper/m0609_gripper.usd" \
    "$P3_M0609/doosan-robot2/urdf/m0609_isaac_sim.urdf" \
    "$P3_M0609/rmpflow/m0609_description.yaml"
  if [[ $P3_HEADLESS == 1 ]]; then
    printf ' --headless'
  elif grep -q -- '--window-half' "$P3_REPO/sim/standalone/pharmacy_stage.py" 2>/dev/null; then
    printf ' --window-half %q --screen-size %q %q' "$( [[ $P3_ISAAC_WINDOW == full ]] && echo full || echo left)" \
      "$SCREEN_W" "$SCREEN_H"
  else
    echo "[demo_v2] 이 트리의 pharmacy_stage.py 에 --window-half 가 없어 창 인자를 넘기지 않는다(Isaac 창은 손으로 Super+←)" >&2
  fi
  # 팔과 같은 seed 를 스테이지에도 준다. 없으면 스테이지는 0 이라 P3_V2_SEED 를 바꿔도 진열이 안 바뀐다(9/24 회차38).
  # P3_STAGE_ARGS 보다 앞이라 사람이 --seed 를 따로 주면 그 값이 이긴다(argparse 는 뒤 값).
  printf ' --seed %q' "$P3_V2_SEED"
  [[ -n $P3_STAGE_ARGS ]] && printf ' %s' "$P3_STAGE_ARGS"      # 사람이 준 인자 그대로(띄어쓰기로 나뉜다)
  return 0
}

validate_arm_mode() {
  [[ -n ${P3_ARM_CMD:-} ]] && return 0      # 전체 명령 덮어쓰기는 자체 설정을 따른다
  case "$P3_V2_GUARDED_MODULE_PATH" in
    true|false) ;;
    *) say 'P3_V2_GUARDED_MODULE_PATH 는 true 또는 false 여야 한다'; return 2 ;;
  esac
  case "$P3_V2_RAIL_SELECT" in
    first_feasible|preferred_first) return 0 ;;
    *) say 'P3_V2_RAIL_SELECT 는 first_feasible 또는 preferred_first 여야 한다'; return 2 ;;
  esac
}

arm_cmd() {
  if [[ -n ${P3_ARM_CMD:-} ]]; then printf '%s' "$P3_ARM_CMD"; return; fi
  printf '%s && ros2 run rokey_p3_manipulation m0609_arm --ros-args -p use_sim_time:=true -p scene_version:=2 -p v2_seed:=%q' \
    "$(ros_env)" "$P3_V2_SEED"
  printf ' -p v2_guarded_module_path:=%q' "$P3_V2_GUARDED_MODULE_PATH"
  printf ' -p v2_rail_select:=%q' "$P3_V2_RAIL_SELECT"
  [[ $P3_CONTAINER_QR == 1 ]] && printf ' -p container_check:=true'
  return 0
}

nav_cmd() {   # emptyworld·hospital 만. waypoints 모드는 Nav2 를 띄우지 않고 map -> <ns>/odom 을 항등으로 둔다
  if [[ -n ${P3_NAV_CMD:-} ]]; then printf '%s' "$P3_NAV_CMD"; return; fi
  if [[ $P3_WORLD == hospital ]]; then
    # 병원: Nav2(기본 백엔드), 전 높이 지도 + localization:=odom, 마지막 구간은 추종기(hospital-nav-l3 6절)
    printf '%s && ros2 launch rokey_p3_navigation navigation.launch.py' "$(ros_env)"
    printf ' zones_file:=%q routes_file:=%q map:=%q nav2_final_approach:=true localization:=odom' \
      "$P3_ZONES" "$P3_ROUTES" "$P3_HOSPITAL_MAP"
    return
  fi
  printf '%s && ros2 launch rokey_p3_navigation navigation.launch.py motion_backend:=waypoints' "$(ros_env)"
  printf ' zones_file:=%q routes_file:=%q' "$P3_ZONES" "$P3_ROUTES"
}

stack_cmd() {
  if [[ -n ${P3_STACK_CMD:-} ]]; then printf '%s' "$P3_STACK_CMD"; return; fi
  if full_loop_world; then
    # use_stub_sim:=false — 어댑터 구성에서 stub_sim 에 남는 일은 gripper/holding 과 /evaluator/cabinet
    # 둘뿐이고, 둘 다 빈월드에서 해롭다. holding 은 Isaac 과 작성자가 겹치고(팔이 마지막 값 하나로
    # 파지를 판정한다), cabinet 은 팔의 주장을 참값처럼 되돌려 준다(Isaac 쪽 작성자는 K5b 에서 온다).
    printf '%s && ros2 launch rokey_p3_bringup stub_loop.launch.py use_isaac_adapter:=true pharmacy_only:=false' "$(ros_env)"
    # publish_cabinet:=false 도 같이 준다. 지금은 stub_sim 이 꺼져 있어 없어도 같지만,
    # 누가 stub_sim 을 다시 켜도 보관함 참값이 스텁에서 나오지 않게 한다(K5b 전까지).
    # 빈월드의 AMR 상판은 통짜 트레이라 자리가 셋이다(시뮬 #445). 기본 5 로 두면 넷째 주문이
    # 없는 칸(deck_slot_4)으로 가고, 그 프레임이 없어 놓는 자리에서 실패한다.
    printf ' use_stub_sim:=false publish_cabinet:=false deck_slots:=3'
    # 실물 주행·실물 UR5 팔. 뒤 네 인자는 한 묶음이라 어긋나면 launch 가 기동 전에 멈춘다.
    printf ' use_stub_fleet:=false use_stub_arm:=false pick_notice:=false use_ur5_arm:=true ur5_arm_params_file:=%q' \
      "$P3_UR5_ARM_PARAMS"
    # 시뮬 센서를 켜면 어댑터와 팔을 한 묶음으로 준다. 어긋나면 launch 가 기동 전에 멈춘다.
    # 카메라 모드면 봉투만 카메라이고 인식표·보관함은 시뮬 센서 그대로다.
    if camera_pouches; then
      if [[ $P3_CAMERA_TAGS == 1 ]]; then
        # 인식표도 카메라 QR(재범 9/29 병상 QR → 약 QR → 매칭 → 내려놓기). 보관함 참값은 평가용이라 그대로 둔다.
        printf ' scan_tag_source:=camera'
        [[ $P3_SIM_SENSORS == 1 ]] && printf ' sim_cabinet:=true'
      else
        [[ $P3_SIM_SENSORS == 1 ]] && printf ' sim_tag_reads:=true scan_tag_source:=sim sim_cabinet:=true'
      fi
      printf ' use_stub_detector:=false use_pouch_detector:=true pouch_source:=camera'
      printf ' belt_view_standoff_m:=%q belt_view_offset_m:=%q detector_pouch_distance_m:=%q' \
        "$P3_BELT_VIEW_STANDOFF" "$P3_BELT_VIEW_OFFSET" \
        "$(awk -v s="$P3_BELT_VIEW_STANDOFF" -v h="$P3_POUCH_HEIGHT" 'BEGIN { printf "%.3f", s - h }')"
    elif [[ $P3_SIM_SENSORS == 1 ]]; then
      printf ' sim_pouches:=true sim_tag_reads:=true pouch_source:=sim scan_tag_source:=sim sim_cabinet:=true'
      # 비전 교차 확인(재범 9/25 점수판 AI 비전, opt-in): 참값으로 집되 상판 집기 직전 손 카메라 검출이 참값과
      # 0.05 m 안이면 검출 좌표로 집는다. 검출기는 5 Hz 상한. 스텁 검출기와는 같이 켤 수 없다(launch 가 멈춘다).
      [[ $P3_DECK_VISION == 1 ]] && printf ' use_stub_detector:=false use_pouch_detector:=true vision_check:=true detector_max_rate_hz:=5.0 detector_pouch_distance_m:=0.30'
      # 상판 집기 뒤 손 카메라 프레임(초마다 한 장). campaign1 a01 0/13 의 화면 밖·반사를 가르려고. <기동시각>-deck-frames/
      [[ $P3_DECK_VISION == 1 ]] && printf ' detector_save_reads_dir:=%q' "$P3_LOG_DIR/${STAMP:-unknown}-deck-frames"
    fi
    # 자동 주문은 기본으로 끈다. 그것이 먼저 뜨면 사람이 넣은 요청이 409 trip_in_progress 이고,
    # 그 주문의 침상(bed_a2)이 팔의 cabinet_frame(한 zone 고정)과 부딪힌다(실습29).
    [[ $P3_AUTO_ORDER == 1 ]] || printf ' use_order_generator:=false'
    # 병원 컨베이어는 A1 롤러 끝까지 34.58 s 걸렸다(#240). 기본 20 s 면 봉투가 가는 중에 주문이 닫힌다.
    [[ $P3_WORLD == hospital ]] && printf ' belt_timeout_s:=%q' "$P3_BELT_TIMEOUT_S"
    # 병원은 스테이지 틱이 길어(9/23 rtf 0.375) 계약 기본 2 s 안에 Dispense 응답이 안 온다 —
    # `거부로 답한다. 2 s 안에 응답이 없다` ×3 으로 주문이 거부됐다. 어댑터 시한을 넓힌다.
    [[ $P3_WORLD == hospital ]] && printf ' dispense_timeout_s:=%q' "$P3_DISPENSE_TIMEOUT_S"
    printf ' dispense_while_dispatching:=%q' "${P3_DISPENSE_WHILE_DISPATCHING:-false}"
  else
    printf '%s && ros2 launch rokey_p3_bringup stub_loop.launch.py use_isaac_adapter:=true pharmacy_only:=true' "$(ros_env)"
  fi
  [[ $P3_CONTAINER_QR == 1 ]] && printf ' use_m0609_detector:=true pharmacy_db:=true'
  # 약통 QR 을 읽은 순간 손 카메라 한 장(발표 PiP, 작전 9/23). 로그 옆 <기동시각>-qr-reads/ 에 남는다.
  [[ $P3_CONTAINER_QR == 1 ]] && printf ' m0609_save_reads_dir:=%q' "$P3_LOG_DIR/${STAMP:-unknown}-qr-reads"
  printf ' publish_clock:=false emulate_m0609:=false use_stub_m0609:=false dispenser_file:=%q order_pool_file:=%q run_host:=%q' \
    "$P3_DISPENSER_FILE" "$P3_ORDER_POOL" "$P3_RUN_HOST"
  # 병원: 병실 묶음 → 그 방 테이블(C), 스테이션 자리 주문 → st- 인식표(재범 9/25). 주행·웹과 같은 구역 파일이다.
  [[ $P3_WORLD == hospital ]] && printf ' zones_file:=%q' "$P3_ZONES"
  return 0
}

web_cmd() {
  if [[ -n ${P3_WEB_CMD:-} ]]; then printf '%s' "$P3_WEB_CMD"; return; fi
  printf '%s && cd %q/web/backend && %q -m app.main --host %q --port %q --allow-commands --static %q' \
    "$(ros_env)" "$P3_REPO" "$P3_WEB_PY" "$P3_WEB_HOST" "$P3_WEB_PORT" "$P3_REPO/web/frontend"
  printf ' --order-pool %q --zones-file %q' "$P3_ORDER_POOL" "$P3_ZONES"
  # QR 판독 요약(약 이름·약통 로트, api.md §1.12). 스택과 같은 파일이다.
  printf ' --catalog %q' "$P3_CATALOG"
  [[ -n ${P3_DISPENSER_FILE:-} ]] && printf ' --dispenser-file %q' "$P3_DISPENSER_FILE"
  if [[ $P3_WORLD == hospital ]]; then printf ' --map-file %q' "$P3_HOSPITAL_MAP"; fi   # 평면도(api.md §7.6)
  # 두 PC 모드를 화면이 알게 한다(snapshot.deployment, api.md §1.10). ros_env 가 env -i 라 환경 변수로는 안 넘어간다.
  if two_hosts; then printf ' --roles %q --peer %q' "${ROLES[*]}" "$P3_PEER"; fi
}

start_role() {  # $1 역할, $2 명령. 끝나면 로그 끝에 exit=N 을 남긴다
  local role=$1 cmd=$2 log
  log=$(log_of "$role")
  printf '%s $ %s\n' "$(date +%FT%T)" "$cmd" > "$log"
  tmux new-session -d -s "$(session "$role")" -x 220 -y 50 "bash --noprofile --norc"
  # 감싸는 bash 는 INT 에 빈 처리기(trap :)를 둔다. 처리기는 exec 때 기본값으로 돌아가므로 명령은 C-c 를 그대로 받고,
  # 감싸는 쪽은 살아남아 exit= 줄을 남긴다. 대화형 셸에서 바로 치면 SIGINT 로 죽은 파이프라인 뒤의 echo 가 버려진다(9/18 docker 시험).
  local inner
  inner="trap : INT; ( echo '[demo_v2] started'; $cmd ) 2>&1 | tee -a -i $(printf '%q' "$log"); \
echo \"exit=\${PIPESTATUS[0]}\" | tee -a $(printf '%q' "$log")"
  tmux send-keys -t "=$(session "$role"):" "bash -c $(printf '%q' "$inner")" Enter
  # 셸이 줄을 받아 실행을 시작한 뒤에 돌아간다. 곧바로 C-c 가 가면 입력 줄만 지워지고 명령은 안 돈다(9/18 docker 시험).
  local start; start=$(date +%s)
  until grep -q '^\[demo_v2\] started' "$log" 2>/dev/null; do
    (($(date +%s) - start >= 10)) && { say "$role: 10 s 안에 명령이 시작되지 않았다(tmux $(session "$role") 확인)"; break; }
    sleep 0.2
  done
  say "$role 시작: tmux $(session "$role"), 로그 $log"
}

wait_line() {  # $1 역할, $2 grep -E 식, $3 시한. 준비 줄이 나오면 0, exit= 가 먼저 나오거나 시한이면 1
  local role=$1 pattern=$2 limit=$3 log start
  log=$(log_of "$role"); start=$(date +%s)
  while :; do
    # 첫 줄은 명령 원문이라 뺀다(명령에 준비 줄 글자가 들어 있을 수 있다).
    if tail -n +2 "$log" 2>/dev/null | grep -qE -- "$pattern"; then
      say "$role 준비: $(tail -n +2 "$log" | grep -m1 -E -- "$pattern" | cut -c1-160)"
      return 0
    fi
    if grep -q '^exit=' "$log" 2>/dev/null; then
      say "$role 이 준비 전에 끝났다: $(grep '^exit=' "$log" | tail -1). 로그 끝:"; tail -n 15 "$log"
      return 1
    fi
    if (($(date +%s) - start >= limit)); then
      say "$role 준비 줄('$pattern')이 ${limit} s 안에 없다. 로그 끝:"; tail -n 15 "$log"
      return 1
    fi
    sleep 1
  done
}

wait_http() {  # 웹이 응답하면 0
  local url="http://$P3_WEB_HOST:$P3_WEB_PORT/" start log
  log=$(log_of web); start=$(date +%s)
  while :; do
    # 끝난 것을 먼저 본다. 응답이 있어도 우리 웹이 이미 죽었으면 남의 서버다.
    if grep -q '^exit=' "$log" 2>/dev/null; then
      say "web 이 준비 전에 끝났다. 로그 끝:"; tail -n 15 "$log"; return 1
    fi
    if python3 -c "import sys, urllib.request; urllib.request.urlopen(sys.argv[1], timeout=2)" "$url" 2>/dev/null; then
      say "web 준비: $url 응답"
      return 0
    fi
    if (($(date +%s) - start >= P3_WEB_TIMEOUT_S)); then
      say "web 이 ${P3_WEB_TIMEOUT_S} s 안에 $url 에 응답하지 않는다. 로그 끝:"; tail -n 15 "$log"; return 1
    fi
    sleep 1
  done
}

clock_publishers() {  # 이 도메인의 /clock 발행자 수(모르면 ?)
  local out
  out=$(bash -c "$(ros_env) && timeout 20 ros2 topic info /clock --no-daemon" 2>/dev/null) || true
  if [[ $out =~ Publisher\ count:\ ([0-9]+) ]]; then echo "${BASH_REMATCH[1]}"
  elif [[ $out == *'Unknown topic'* || -z $out ]]; then echo 0
  else echo '?'
  fi
}

clock_now() {  # /clock 한 번(sim s, 소수 셋째 자리). 못 읽으면 빈 값
  local out
  out=$(bash -c "$(ros_env) && timeout 10 ros2 topic echo /clock --once --no-daemon --csv --field clock" 2>/dev/null) || true
  [[ $out =~ ^([0-9]+),([0-9]+) ]] && printf '%d.%03d' "${BASH_REMATCH[1]}" $((10#${BASH_REMATCH[2]} / 1000000))
}

wait_remote_clock() {  # 스테이지가 다른 PC 에 있을 때: /clock 발행자 1 이고 시각이 흐르면 0
  local start a b pub
  start=$(date +%s)
  while :; do
    pub=$(clock_publishers); a=$(clock_now); sleep 2; b=$(clock_now)
    if [[ $pub == 1 && -n $a && -n $b ]] && awk -v a="$a" -v b="$b" 'BEGIN { exit !(b > a) }'; then
      say "/clock 공유 확인: 발행자 1(상대 PC 의 스테이지), sim $a → $b s — 흐른다"
      return 0
    fi
    if (($(date +%s) - start >= P3_STAGE_TIMEOUT_S)); then
      say "/clock 이 ${P3_STAGE_TIMEOUT_S} s 안에 흐르지 않는다(발행자 $pub, sim ${a:-없음} → ${b:-없음}). 스테이지 PC 가 PLAY 인지 본다."
      return 1
    fi
    sleep 1
  done
}

check_peer() {  # 두 PC 모드의 망·DDS 확인. 하나라도 걸리면 멈춘다(조용히 서로 못 보는 것이 제일 늦게 드러난다)
  two_hosts || return 0
  local problems=() src
  if [[ ${ROS_AUTOMATIC_DISCOVERY_RANGE:-} == LOCALHOST || ${ROS_LOCALHOST_ONLY:-0} == 1 ]]; then
    problems+=("이 셸이 ROS 탐색을 이 PC 로 막았다(ROS_AUTOMATIC_DISCOVERY_RANGE=${ROS_AUTOMATIC_DISCOVERY_RANGE:-} ROS_LOCALHOST_ONLY=${ROS_LOCALHOST_ONLY:-}). 풀고 띄운다")
  fi
  ping -c 1 -W 2 "$P3_PEER" >/dev/null 2>&1 || problems+=("상대 $P3_PEER 에 ping 이 안 닿는다(유선·스위치 포트)")
  src=$(ip -4 -o route get "$P3_PEER" 2>/dev/null | sed -n 's/.* src \([0-9.]*\).*/\1/p')
  if [[ ! -f $P3_FASTDDS_PROFILE ]]; then
    problems+=("DDS 프로필이 없다: $P3_FASTDDS_PROFILE (docs/setup/ros2-wired-network.md 5절)")
  else
    for addr in 127.0.0.1 ${src:-} "$P3_PEER"; do
      grep -q "<address>$addr</address>" "$P3_FASTDDS_PROFILE" \
        || problems+=("DDS 프로필에 $addr 가 없다: $P3_FASTDDS_PROFILE — 두 PC 가 같은 파일(양쪽 주소 + 127.0.0.1)을 쓴다")
    done
  fi
  [[ -n $src ]] || problems+=("상대 $P3_PEER 로 가는 이 PC 의 주소를 못 찾았다(ip route get)")
  if ((${#problems[@]})); then
    say "두 PC 확인 실패(상대 $P3_PEER). 멈춘다:"; printf '  - %s\n' "${problems[@]}"; return 1
  fi
  say "두 PC: 이 PC ${src} ↔ 상대 $P3_PEER ping 됨, 프로필 $P3_FASTDDS_PROFILE 에 두 주소, 도메인 $P3_DOMAIN, 역할 ${ROLES[*]}"
}

domain_nodes() {  # 이 도메인에 이미 떠 있는 노드 이름(우리 것이 뜨기 전에만 본다)
  bash -c "$(ros_env) && timeout 20 ros2 node list --no-daemon" 2>/dev/null | grep '^/' || true
}

check_world_files() {  # 구역·경로 파일이 주행·웹에 같은 경로로 가는가. 다르면 멈춘다
  full_loop_world || return 0
  local missing=() nav web zones routes
  zones=$(printf '%q' "$P3_ZONES"); routes=$(printf '%q' "$P3_ROUTES")
  [[ -f $P3_ZONES ]] || missing+=("구역 파일 없음: $P3_ZONES")
  [[ -f $P3_ROUTES ]] || missing+=("경로 파일 없음: $P3_ROUTES")
  [[ -n $P3_UR5_ARM_PARAMS && -f $P3_UR5_ARM_PARAMS ]] || missing+=("UR5 팔 현장값 파일 없음: ${P3_UR5_ARM_PARAMS:-(없음)}")
  if [[ -n $P3_AMR_COMBINED ]]; then
    [[ -f $P3_AMR_COMBINED ]] || missing+=("AMR 합본 USD 가 없다: $P3_AMR_COMBINED")
    # 합본은 팔 params 가 다르다. 받침대용 파일로 띄우면 관절 이름과 밑동 기준이 어긋나 **조용히** 틀린다.
    if [[ -f ${P3_UR5_ARM_PARAMS:-} ]]; then
      grep -q 'ur_arm_' "$P3_UR5_ARM_PARAMS" \
        || missing+=("AMR 합본인데 팔 params 에 ur_arm_* 관절 이름이 없다: $P3_UR5_ARM_PARAMS")
      grep -q 'arm_base_frame_convention' "$P3_UR5_ARM_PARAMS" \
        || missing+=("AMR 합본인데 팔 params 에 arm_base_frame_convention 이 없다: $P3_UR5_ARM_PARAMS")
    fi
  fi
  if camera_pouches && [[ -f ${P3_UR5_ARM_PARAMS:-} ]]; then
    # 카메라 집기는 손목 기준 카메라 변환(tool_frame)과 흡착점(tcp_offset_m)이 있어야 관측·파지 자세를 만든다.
    # 없으면 팔이 "관측 자세 없음"으로 not_detected 를 내거나 흡착점이 0.1555 m 빗나간다(조용히 틀린다).
    for key in tool_frame tcp_offset_m refine_view_standoff_m; do
      grep -q "^ *$key:" "$P3_UR5_ARM_PARAMS" \
        || missing+=("카메라 집기(P3_CAMERA_POUCHES=1)인데 팔 params 에 $key 가 없다: $P3_UR5_ARM_PARAMS")
    done
    # 인식표를 카메라로 읽으면 판독 거리가 있어야 한다. 0 이면 ScanTag 가 곧바로 실패한다(arm_node tag_standoff_m).
    # 키만 보지 않고 값이 0 보다 큰지 본다(통합검증 5882413759: 0 이면 tag_view_pose 가 없어 UNREADABLE 로 닫힌다).
    if [[ $P3_CAMERA_TAGS == 1 ]]; then
      awk '/^ *tag_standoff_m:/ { found = 1; if ($2 + 0 > 0) ok = 1 } END { exit !(found && ok) }' "$P3_UR5_ARM_PARAMS" \
        || missing+=("인식표 카메라(P3_CAMERA_TAGS=1)인데 팔 params 의 tag_standoff_m 이 없거나 0 이하다: $P3_UR5_ARM_PARAMS")
    fi
  fi
  if [[ $P3_WORLD == hospital ]]; then
    [[ -n $P3_AMR_COMBINED ]] || missing+=("hospital 은 AMR 합본이 필요하다: P3_AMR_COMBINED 가 비었다")
    if has_role stage; then   # 스테이지만 읽는 파일 — 스테이지가 다른 PC 면 여기엔 없어도 된다
      [[ -f $P3_WORKCELL_LAYOUT ]] || missing+=("병원 M0609 워크셀 JSON 이 없다: ${P3_WORKCELL_LAYOUT:-(비었다)}")
      [[ -f $P3_HOSPITAL_SCENE ]] || missing+=("병원 씬이 없다: $P3_HOSPITAL_SCENE")
    fi
    [[ -f $P3_HOSPITAL_MAP ]] || missing+=("병원 지도가 없다: $P3_HOSPITAL_MAP")
  fi
  nav=$(nav_cmd); web=$(web_cmd)
  grep -qF -- "zones_file:=$zones" <<<"$nav" || missing+=("주행 명령의 zones_file 이 $P3_ZONES 가 아니다")
  grep -qF -- "routes_file:=$routes" <<<"$nav" || missing+=("주행 명령의 routes_file 이 $P3_ROUTES 가 아니다")
  grep -qF -- "--zones-file $zones" <<<"$web" || missing+=("웹 명령의 --zones-file 이 $P3_ZONES 가 아니다")
  # 주문 풀은 셋이 같아야 한다. 인증 v0 에서 스테이지가 이 파일로 bed -> pt-<patient_id> 를 만든다(통보 45).
  local pool stage
  # 이 검사는 STAMP(기동 시각)보다 먼저 돈다. stage_cmd 는 kit 로그 이름에만 쓰므로 자리만 채워 준다.
  pool=$(printf '%q' "$P3_ORDER_POOL"); stage=$(STAMP=${STAMP:-확인} stage_cmd 2>/dev/null)
  [[ -f $P3_ORDER_POOL ]] || missing+=("주문 풀 파일 없음: $P3_ORDER_POOL")
  grep -qF -- "order_pool_file:=$pool" <<<"$(stack_cmd)" || missing+=("스택 명령의 order_pool_file 이 $P3_ORDER_POOL 가 아니다")
  grep -qF -- "--order-pool $pool" <<<"$web" || missing+=("웹 명령의 --order-pool 이 $P3_ORDER_POOL 가 아니다")
  grep -qF -- "--order-pool $pool" <<<"$stage" || missing+=("스테이지 명령의 --order-pool 이 $P3_ORDER_POOL 가 아니다")
  if [[ $P3_WORLD == hospital ]]; then   # 스테이지의 belt_end·보관함·인식표가 같은 zones 에서 나와야 한다
    grep -qF -- "--zones-file $zones" <<<"$stage" || missing+=("스테이지 명령의 --zones-file 이 $P3_ZONES 가 아니다")
  fi
  if ((${#missing[@]})); then
    say "월드 파일 확인 실패. 멈춘다(경고로 넘기지 않는다 — 웹 목록과 실물 주행이 갈리면 시연 중에 못 찾는다):"
    printf '  - %s\n' "${missing[@]}"
    return 1
  fi
  say "월드 파일: zones=$P3_ZONES routes=$P3_ROUTES (주행·웹 같은 경로), 주문 풀=$P3_ORDER_POOL (스택·웹·스테이지 같은 경로), ur5 params=$P3_UR5_ARM_PARAMS"
}

ntp_state() {  # 읽기만 한다. yes / no / 모름
  local value
  value=$(timedatectl show -p NTPSynchronized --value 2>/dev/null) || value=''
  printf '%s' "${value:-모름}"
}

preflight() {
  local busy=() others clock
  for role in "${ROLES[@]}" cap browser camview; do has_session "$role" && busy+=("$(session "$role")"); done
  if ((${#busy[@]})); then
    say "이미 떠 있는 세션이 있다: ${busy[*]}. status 로 보고, 내리려면 down 한다. 멈춘다."
    return 1
  fi
  # 보기만 한다. 이 목록을 무엇에도 넘기지 않는다(남의 Isaac 은 절대 내리지 않는다).
  others=$(pgrep -af -- "$P3_ISAAC_PATTERN" 2>/dev/null | grep -v -- "pgrep -af" || true)
  if [[ -n $others ]]; then
    say "이 기계에 다른 Isaac 이 떠 있다. 띄우지 않고 멈춘다(내리지 않는다). 사람에게 알린다:"
    printf '%s\n' "$others" | cut -c1-200
    return 1
  fi
  clock=$(clock_publishers)
  if ! has_role stage; then
    # 스테이지가 다른 PC 에 있다. /clock 은 그 Isaac 하나여야 한다 — 0 이면 아직 안 떴거나 서로 못 본다,
    # 2 이상이면 다른 스택이 같은 도메인에 섞였다. 노드 0 검사는 하지 않는다(상대의 노드가 보여야 정상이다).
    if [[ $clock != 1 ]]; then
      say "도메인 $P3_DOMAIN 의 /clock 발행자가 $clock 이다. 스테이지가 다른 PC 에 있으면 1 이어야 한다" \
        "(0: 스테이지 PC 를 먼저 up 하거나 DDS 가 서로 못 본다, 2 이상: 다른 스택이 섞였다). 멈춘다."
      return 1
    fi
    say "기동 전 확인: others:[] /clock 1(다른 PC 의 스테이지) 도메인 $P3_DOMAIN 노드 $(domain_nodes | grep -c .)개"
  elif [[ $clock != 0 ]]; then
    say "도메인 $P3_DOMAIN 에 /clock 발행자가 $clock 이다(0 이어야 한다). 다른 스택·Isaac 이 같은 도메인에 있다. 멈춘다."
    return 1
  else
    # 우리 스택이 뜨기 전이므로 이 도메인의 노드는 0 이어야 한다. 남의 것이 있으면 이름으로 주인을 찾는다.
    local nodes count
    nodes=$(domain_nodes)
    count=$(grep -c . <<<"$nodes"); [[ -n $nodes ]] || count=0
    if ((count > 0)); then
      say "도메인 $P3_DOMAIN 에 노드가 $count 개 있다(0 이어야 한다). 우리 것은 아직 안 떴다. 이름 일부:"
      head -5 <<<"$nodes" | sed 's/^/  /'
      return 1
    fi
    say "기동 전 확인: others:[] /clock 0 노드 0(도메인 $P3_DOMAIN)"
  fi
  # 멈추지 않고 알리기만 한다. 웹 백엔드는 신선도를 벽시계로 잰다(계약 4절과 다름, 백엔드 #219 알려진 차이, 9/21 뒤 수정).
  local ntp; ntp=$(ntp_state)
  if [[ $ntp != yes ]]; then
    say "경고: 시계 동기화 전(NTPSynchronized=$ntp) — 웹 신선도가 시계 보정 때 한 번 틀어질 수 있다. 동기화 뒤 web 만 재기동 권장"
  fi
}

start_capture() {
  ((P3_CAPTURE_EVERY > 0)) || return 0
  local dir="$P3_LOG_DIR/$STAMP-shots" grab=''
  if command -v gst-launch-1.0 >/dev/null && gst-inspect-1.0 ximagesrc >/dev/null 2>&1; then grab=gst
  elif command -v xwd >/dev/null; then grab=xwd
  fi
  if [[ -z $grab || -z ${DISPLAY:-} ]]; then
    say "캡처 끔: gst-launch-1.0(ximagesrc)·xwd 가 없거나 DISPLAY 가 없다(설치하지 않는다)"
    return 0
  fi
  mkdir -p "$dir"
  local loop
  loop=$(cat <<EOF
xid=''
if [ -n $(printf '%q' "$P3_CAPTURE_WINDOW") ] && command -v xwininfo >/dev/null; then
  xid=\$(xwininfo -root -tree | grep -F -- $(printf '%q' "$P3_CAPTURE_WINDOW") | head -1 | awk '{print \$1}')
fi
echo "capture grab=$grab every=$P3_CAPTURE_EVERY window=\${xid:-root}"
while sleep $P3_CAPTURE_EVERY; do
  f=$(printf '%q' "$dir")/\$(date +%H%M%S)
  if [ $grab = gst ]; then
    gst-launch-1.0 -q ximagesrc \${xid:+xid=\$xid} num-buffers=1 ! videoconvert ! pngenc ! filesink location=\$f.png
  else
    xwd -silent \${xid:+-id \$xid} \${xid:--root} -out \$f.xwd
  fi
done
EOF
)
  start_role cap "$loop"
  say "캡처 켬: ${P3_CAPTURE_EVERY} s 마다 $dir ($grab)"
}

start_browser() {
  [[ -n $P3_BROWSER ]] || return 0
  if ! command -v "$P3_BROWSER" >/dev/null; then say "브라우저 $P3_BROWSER 가 없다. 웹은 떠 있다: $(web_url)"; return 0; fi
  if [[ -z ${DISPLAY:-} ]]; then say "DISPLAY 가 없어 브라우저를 띄우지 않는다. 웹: $(web_url)"; return 0; fi
  # 따로 된 프로필로 새 인스턴스를 띄워야 -width/-height 가 먹는다(이미 떠 있는 firefox 에 붙으면 창 크기를 무시한다).
  local profile="$P3_LOG_DIR/$STAMP-browser-profile"         # 기동마다 새 프로필: 지난 기동의 프론트 캐시를 쓰지 않는다
  mkdir -p "$profile"
  start_role browser "$(printf '%q --new-instance --profile %q -width %q -height %q %q' \
    "$P3_BROWSER" "$profile" "$P3_BROWSER_WIDTH" "$P3_BROWSER_HEIGHT" "$(web_url)")"
  say "브라우저 ${P3_BROWSER_WIDTH}x${P3_BROWSER_HEIGHT}(화면 $P3_SCREEN_SIZE 의 오른쪽 반). 위치는 스크립트가 못 정한다: 오른쪽에 없으면 창을 누르고 Super+→"
}

camview_cmd() {  # 손 카메라 이미지 창. 카메라 모드에서만 뜻이 있다
  # QR 추적 영상(재범 9/29): 검출기가 QR 네 꼭짓점 사각형·판정 색을 그린 것. 보는 창이 있어야 검출기가 그린다.
  printf '%s && ros2 run rqt_image_view rqt_image_view /amr_1/hand_camera/qr_view' "$(ros_env)"
}

start_camview() {
  [[ $P3_CAMERA_VIEW == 1 ]] || return 0
  camera_pouches || { say "P3_CAMERA_VIEW 는 카메라 모드(P3_CAMERA_POUCHES=1)에서만 띄운다"; return 0; }
  if [[ -z ${DISPLAY:-} ]]; then say "DISPLAY 가 없어 카메라 창을 띄우지 않는다"; return 0; fi
  start_role camview "$(camview_cmd)"
  say "카메라 창: /amr_1/hand_camera/qr_view — QR 추적 사각형 (rqt_image_view). 없으면 sudo apt install ros-jazzy-rqt-image-view"
}

web_url() { printf 'http://%s:%s/%s' "$P3_WEB_HOST" "$P3_WEB_PORT" "$P3_WEB_QUERY"; }

tree_info() {  # 지금 띄우는 것이 고친 그것인지(작전 공통 규칙 9/18): 저장소 sha·고친 파일 수, install 시각
  local sha dirty install_at head_at
  sha=$(git -C "$P3_REPO" rev-parse --short=12 HEAD 2>/dev/null || echo '?')
  dirty=$(git -C "$P3_REPO" status --porcelain --untracked-files=no 2>/dev/null | wc -l)
  head_at=$(git -C "$P3_REPO" log -1 --format=%cd --date=format-local:'%F %T' 2>/dev/null || echo '?')
  install_at=$(date -r "$P3_INSTALL/setup.bash" '+%F %T' 2>/dev/null || echo '없음')
  printf 'tree %s(커밋 %s, 커밋 안 한 변경 %s 파일) install %s(setup.bash 시각)' "$sha" "$head_at" "$dirty" "$install_at"
  # install 이 HEAD 커밋보다 오래됐으면 알린다(--symlink-install 이면 파이썬은 따라가지만 새 파일·C++·메시지는 다시 빌드해야 한다)
  if [[ $install_at != 없음 && $head_at != '?' && $install_at < $head_at ]]; then printf ' — install 이 커밋보다 오래됐다. colcon build 를 했는지 본다'; fi
  return 0
}

stage_flags_line() {  # contact_watch·ur5 를 기동 직후에 알린다(종료 줄에 가서야 알면 늦다)
  local log kit found
  log=$(log_of stage); kit="$P3_LOG_DIR/$STAMP-kit.log"
  found=$(grep -ho 'contact_watch=[a-z]*\|ur5=[a-z]*' "$log" "$kit" 2>/dev/null | sort -u | tr '\n' ' ')
  if [[ -n $found ]]; then
    say "스테이지 플래그: $found"
  else
    say "스테이지 플래그: 기동 로그에 contact_watch·ur5 가 없다(지금은 종료 줄에서만 나온다). 값을 미리 보려면 시뮬에 기동 줄 추가를 요청한다"
  fi
}

cmd_up() {
  need P3_DOMAIN P3_M0609 P3_DISPENSER_FILE
  full_loop_world && need P3_UR5_ARM_PARAMS
  [[ $P3_WORLD == hospital ]] && need P3_AMR_COMBINED
  [[ $P3_WORLD == hospital ]] && has_role stage && need P3_WORKCELL_LAYOUT
  validate_arm_mode || exit 2
  # 설정 오류를 먼저 말한다. tmux 가 없는 기계에서도 이 확인은 돈다(시험이 그렇게 본다).
  check_world_files || exit 2
  check_peer || exit 2
  command -v tmux >/dev/null || { say "tmux 가 없다"; exit 2; }
  mkdir -p "$P3_LOG_DIR"
  preflight || exit 3
  STAMP=$(date +%Y%m%d-%H%M%S)
  echo "$STAMP" > "$STAMP_FILE"
  { tree_info; echo; } > "$P3_LOG_DIR/$STAMP-tree.txt"
  say "$(head -1 "$P3_LOG_DIR/$STAMP-tree.txt")"
  if has_role stage; then
    start_role stage "$(stage_cmd)"
    if ! wait_line stage "$P3_STAGE_READY" "$P3_STAGE_TIMEOUT_S"; then
      # 스테이지가 설정 오류로 거부한 것과 장면 결함을 구별해 준다(시뮬이 접두를 붙여 준다).
      if grep -q 'sim_sensors config error:' "$(log_of stage)" 2>/dev/null; then
        say "스테이지가 **설정 오류**로 거부했다(장면 결함이 아니다):"
        grep -m3 'sim_sensors config error:' "$(log_of stage)" | sed 's/^/  /'
      fi
      say "up 중단(stage). 띄운 것은 down 으로 내린다."
      exit 4
    fi
    stage_flags_line
    start_capture
  else
    # 스테이지는 다른 PC 다. 그 로그를 못 보므로 /clock 이 흐르는 것으로 PLAY 를 본다.
    wait_remote_clock || { say "up 중단(스테이지 PC 의 /clock). 이 PC 에는 아직 띄운 것이 없다."; exit 4; }
  fi
  if has_role arm; then
    start_role arm "$(arm_cmd)"
    wait_line arm "$P3_ARM_READY" "$P3_ARM_TIMEOUT_S" || { say "up 중단(arm). 띄운 것은 down 으로 내린다."; exit 4; }
  fi
  if full_loop_world && has_role nav; then
    start_role nav "$(nav_cmd)"
    wait_line nav "$P3_NAV_READY" "$P3_NAV_TIMEOUT_S" || { say "up 중단(nav). 띄운 것은 down 으로 내린다."; exit 4; }
  fi
  if has_role stack; then
    start_role stack "$(stack_cmd)"
    wait_line stack "$P3_STACK_READY" "$P3_STACK_TIMEOUT_S" || { say "up 중단(stack). 띄운 것은 down 으로 내린다."; exit 4; }
  fi
  if ! has_role web; then
    say "준비 완료(이 PC 역할: ${ROLES[*]}). 로그 $P3_LOG_DIR/$STAMP-*.log  내리기: tools/demo_v2.sh down"
    two_hosts && say "상대 PC($P3_PEER)에서 나머지 역할을 up 한다. /clock 발행자 $(clock_publishers)"
    return 0
  fi
  # 이미 누가 그 포트에 응답하면 우리 웹이 bind 에 실패해도 "준비"로 읽는다(9/23 master02: 어제 뜬
  # 다른 웹이 8000 에 남아 있었고 첫 요청이 그쪽으로 갔다). 띄우기 전에 막는다.
  if python3 -c "import sys, urllib.request; urllib.request.urlopen(sys.argv[1], timeout=2)" \
      "http://$P3_WEB_HOST:$P3_WEB_PORT/" 2>/dev/null; then
    say "up 중단(web): $P3_WEB_HOST:$P3_WEB_PORT 에 이미 다른 서버가 응답한다. 그것을 내리거나 P3_WEB_PORT 를 바꾼다."
    exit 4
  fi
  start_role web "$(web_cmd)"
  wait_http || { say "up 중단(web). 띄운 것은 down 으로 내린다."; exit 4; }
  start_browser
  start_camview
  say "준비 완료. 웹 $(web_url)  로그 $P3_LOG_DIR/$STAMP-*.log  내리기: tools/demo_v2.sh down"
}

stop_role() {  # C-c 를 보내고 exit= 를 기다린다. 끝나면 빈 셸만 남은 세션을 닫는다. 안 끝나면 보고만 한다
  local role=$1 log start code
  has_session "$role" || { say "$role: 세션 없음"; return 0; }
  log=$(log_of "$role")
  tmux send-keys -t "=$(session "$role"):" C-c
  start=$(date +%s)
  while ! grep -q '^exit=' "$log" 2>/dev/null; do
    if (($(date +%s) - start >= P3_DOWN_TIMEOUT_S)); then
      say "$role 이 ${P3_DOWN_TIMEOUT_S} s 안에 안 내려갔다. 세션 $(session "$role") 을 그대로 둔다(kill 하지 않는다). 사람이 본다."
      return 1
    fi
    sleep 1
  done
  code=$(grep '^exit=' "$log" | tail -1)
  tmux kill-session -t "=$(session "$role")"          # 명령이 끝나 셸만 남은 우리 세션
  say "$role 내려감: $code"
}

cmd_down() {
  [[ -f $STAMP_FILE ]] && STAMP=$(<"$STAMP_FILE") || STAMP=unknown
  local failed=0
  # down 은 월드·P3_ROLES 와 상관없이 우리 세션 전부를 본다. 없는 세션은 stop_role 이 건너뛴다.
  # P3_WORLD 없이 부르면 DOWN_ORDER 에 nav 가 빠져 p3v2-nav 가 남았다(마클1 회차73, #240 5818833284).
  for role in "${DOWN_ALL[@]}"; do stop_role "$role" || failed=1; done
  if ((failed)); then
    say "안 내려간 것이 있어 stage 는 내리지 않는다. status 로 본다."
    exit 1
  fi
  has_role stage || return 0                            # 스테이지는 다른 PC 다 — 그 PC 에서 down 한다
  sleep 3                                               # 팔이 멈춘 뒤 스테이지(실습 절차와 같은 순서·간격)
  stop_role stage || exit 1
}

cmd_status() {
  [[ -f $STAMP_FILE ]] && STAMP=$(<"$STAMP_FILE") || STAMP=unknown
  say "기동 $STAMP, 도메인 ${P3_DOMAIN:-미설정}"
  [[ -f $P3_LOG_DIR/$STAMP-tree.txt ]] && say "띄울 때 $(head -1 "$P3_LOG_DIR/$STAMP-tree.txt")"
  say "지금    $(tree_info)"
  local log started
  for role in "${ROLES[@]}" cap browser camview; do
    log=$(log_of "$role")
    started=$(head -1 "$log" 2>/dev/null | cut -d' ' -f1)
    if has_session "$role"; then printf '  %-6s 떠 있음 %s(기동 %s)\n' "$role" "$(session "$role")" "${started:-?}"
    else printf '  %-6s 없음\n' "$role"
    fi
    [[ -f $log ]] || continue
    tail -n +2 "$log" | grep -E -- "$P3_STAGE_READY|$P3_ARM_READY|$P3_NAV_READY|$P3_STACK_READY|^exit=|stop reason=|error|ERROR|WARN|Traceback|capture grab" \
      | tail -n 4 | cut -c1-180 | sed 's/^/           /'
  done
  say "시계 동기화 NTPSynchronized=$(ntp_state)(no 면 웹 신선도가 보정 때 틀어질 수 있다)"
  [[ -n ${P3_DOMAIN:-} ]] && say "/clock 발행자 $(clock_publishers)"
}

cmd_env() {
  for name in P3_WORLD P3_ROLES P3_PEER P3_DOMAIN P3_M0609 P3_DISPENSER_FILE P3_REPO P3_INSTALL P3_ORDER_POOL P3_ZONES \
      P3_ROUTES P3_UR5_ARM_PARAMS P3_SIM_SENSORS P3_CAMERA_POUCHES P3_CAMERA_TAGS P3_DECK_VISION P3_CONTAINER_QR P3_CATALOG P3_CAMERA_VIEW P3_CAMERA_RESOLUTION P3_BELT_VIEW_STANDOFF P3_BELT_VIEW_OFFSET P3_QR_DIR P3_AUTO_ORDER P3_AMR_COMBINED P3_HEADLESS P3_ISAAC_PY \
      P3_ISAAC_BRIDGE_LIB P3_FASTDDS_PROFILE P3_WEB_PY P3_WEB_HOST P3_WEB_PORT P3_V2_SEED P3_RUN_HOST P3_LOG_DIR \
      P3_DISPENSE_WHILE_DISPATCHING P3_V2_GUARDED_MODULE_PATH P3_V2_RAIL_SELECT P3_SESSION_PREFIX P3_SCREEN_SIZE P3_ISAAC_WINDOW P3_STAGE_ARGS P3_BROWSER P3_BROWSER_WIDTH P3_BROWSER_HEIGHT P3_WEB_QUERY \
      P3_CAPTURE_EVERY P3_CAPTURE_WINDOW P3_ISAAC_PATTERN P3_STAGE_READY P3_STAGE_TIMEOUT_S P3_ARM_READY P3_STACK_READY; do
    printf '%-20s %s\n' "$name" "${!name:-(없음)}"
  done
  if [[ $P3_WORLD == hospital ]]; then   # 다른 월드의 env 출력은 그대로 둔다
    for name in P3_HOSPITAL_SCENE P3_HOSPITAL_MAP P3_AMR_START P3_HOSPITAL_RECEIVER_PRIM P3_BELT_TIMEOUT_S P3_AMR_COUNT \
        P3_WORKCELL_LAYOUT P3_POUCH_AT_END; do
      printf '%-20s %s\n' "$name" "${!name:-(없음)}"
    done
  fi
}

cmd_cmds() {
  need P3_DOMAIN P3_M0609 P3_DISPENSER_FILE
  [[ $P3_WORLD == hospital ]] && need P3_AMR_COMBINED
  [[ $P3_WORLD == hospital ]] && has_role stage && need P3_WORKCELL_LAYOUT
  validate_arm_mode || exit 2
  STAMP='<기동시각>'
  for role in "${ROLES[@]}"; do printf '%s: %s\n\n' "$role" "$("${role}_cmd")"; done
}

case ${1:-} in
  up) cmd_up ;;
  cmds) cmd_cmds ;;
  down) cmd_down ;;
  status) cmd_status ;;
  env) cmd_env ;;
  *) sed -n '2,9p' "$0"; exit 2 ;;
esac
