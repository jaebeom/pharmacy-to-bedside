# 병원 월드 데모 — 기동·웹 요청·관찰·종료

- 무엇: 병원 월드(`P3_WORLD=hospital`) 한 바퀴를 웹에서 요청하고 지켜보는 절차다. 웹 요청 → M0609 보충·약통 QR → 병원 컨베이어로 A1 → 합본 UR5 집기 → Nav2 → 병상 보관함 → 도크 복귀.
- 기준: 릴리스 `v1.1.0` = main `f316197`(#797). 2026-09-30 에 `tools/demo_v2.sh` 와 대조했다.
- 한 바퀴 기동 명령과 판정의 정본은 [병원 한 바퀴 런카드](hospital-full.md)다. 이 문서는 역할·웹 요청·관찰 지점·촬영 화면·두 PC 기동을 다룬다.
- `v1.1.0` 기본(카메라 집기)으로 돈 한 바퀴 L3 기록은 이 문서를 고친 시각에 없었다. 카메라 배송 성공은 `05b8e28` 의 `bed_a1` 1건이다([실습45](../practice/simworld/practice-45.md)).
- 처음 쓴 것은 9/23 초안이다. 그때 열려 있던 #553·#566 은 병합됐다(`afe69a7`·`ea0c782`). 받는 법·멈추는 법은 [배포 런북](deployment.md)이다.

## 1. 역할

| 어디서 | 무엇을 |
| --- | --- |
| 마스터 PC(터미널) | 호스트를 재부팅·로그아웃하지 않는다. `tools/demo_v2.sh up` 으로 스테이지·팔·주행·스택·웹을 띄운다. 녹화를 켠다. 준비가 끝나면 "시작해도 된다"고 알린다 |
| 웹 화면 | 웹 화면만 조작한다. 터미널은 건드리지 않는다 |

터미널 쪽과 웹 화면 쪽이 신호를 직접 주고받는다(빈월드 리허설과 같다).

## 2. 기동 — 환경 변수

`tools/demo_v2.sh` 머리 주석과 hospital 블록의 값이다. **굵은** 것은 병원에서 필수다. 없으면 `up` 이 어떤 역할도 띄우기 전에 exit 2 로 멈춘다.
"카메라 · 참값" 으로 나눈 칸은 `P3_CAMERA_POUCHES` 가 1 일 때와 0 일 때의 기본이다.

| 변수 | `v1.1.0` 병원 기본 | 비고 |
| --- | --- | --- |
| `P3_WORLD` | `hospital` | 스테이지 `--preset hospital`, 주행 Nav2 |
| **`P3_DOMAIN`** | 사이트 값 | 어느 값을 쓸지는 재범 결정이다(머리 주석). 9/23 회차들은 121 이었다 |
| **`P3_M0609`** | M0609 자산 디렉토리 | 사이트 값(저장소 밖). [hospital-full 0절 4](hospital-full.md#0-새-pc-에서-처음-한-번만) |
| **`P3_DISPENSER_FILE`** | 재고 파일 | 한 바퀴 런카드는 `src/rokey_p3_orchestrator/config/dispenser.hospital-v0.yaml` 을 준다 |
| **`P3_AMR_COMBINED`** | `ridgeback_ur5.usd` 경로 | 사이트 값. 두 PC 모드면 두 PC 모두 그 파일이 있어야 한다(`up` 이 파일을 본다) |
| **`P3_WORKCELL_LAYOUT`** | 병원 M0609 워크셀 JSON | 스테이지 PC 에서만 필수다. `sim/standalone/prepare_workcell_integration.py` 가 만든 `workcell.json` 을 준다([hospital-full 1절](hospital-full.md#1-조제실-입력을-먼저-만든다)). #566 의 fixture 는 9/22 회차의 재현 자료다 |
| `P3_HOSPITAL_SCENE` | `sim/scenes/hospital_navigationv1.usda` | 1절이 만든 `base.usda` 를 준다. 씬 원본에는 조제실이 없다 |
| `P3_HOSPITAL_MAP` | `src/rokey_p3_navigation/config/maps/hospital.yaml` | Nav2 지도. 웹 평면도도 이 파일이다 |
| `P3_CAMERA_POUCHES` | `1` | 봉투를 손 카메라 QR 로 찾는다(#784, 재범 9/29 "QR 반드시 찍고"). 동결 protocol v4 회차는 `0` 을 준다 |
| `P3_CAMERA_TAGS` | `P3_CAMERA_POUCHES` 를 따름 | 병상 `pt-`·테이블 `st-` 인식표도 손 카메라로 읽는다 |
| `P3_ZONES`·`P3_ROUTES` | 카메라 `zones/routes.hospital-receiver.yaml` · 참값 `zones/routes.hospital.yaml` | 스테이지·주행·웹이 같은 zones 를 받는지 `up` 이 검사한다 |
| `P3_ORDER_POOL` | `order_pool.hospital.yaml` | 스택·웹·스테이지가 같은 파일을 받는다 |
| `P3_UR5_ARM_PARAMS` | 카메라 `ur5_arm.amr-combined.camera-receiver.yaml` · 참값 `ur5_arm.amr-combined.gripper.yaml` | 주지 않으면 `demo_v2.sh` 가 고른다 |
| `P3_AMR_START` | 카메라 `-8.266 4.102` · 참값 `-8.995 4.686` | 그 구성 zones 의 `dock_1` 이다. `dock_1` = `load` 다(#790, #797). 9/25 값은 `-7.272 4.784` 였다 |
| `P3_HOSPITAL_RECEIVER_PRIM` | 카메라 `/World/P3Base/Scene/Environment/hospital/SM_SideTable_02a_74` · 참값 없음 | A1 모듈 탁자다. 봉투가 여기 정착한다(#796). 빈 값이면 끈다 |
| `P3_BELT_TIMEOUT_S` | `60` | 병원 컨베이어 운반 34.58 s(#240 5790540704)는 배율 1 의 값이다. `v1.1.0` preset 은 배율 2 다(#789). 2 배의 운반 시간은 아직 없다 |
| `P3_SIM_SENSORS` | `0`(한 바퀴 런카드는 `1`) | 스테이지 `--sim-sensors`. 1 이면 카메라 집기에서도 보관함 참값(`sim_cabinet`)이 평가용으로 켜진다 |
| `P3_CONTAINER_QR` | **병원 기본 1** | M0609 손 카메라(`--m0609-hand-camera`) + 약통 QR 판독 + 약 DB. 끄려면 0 |
| 합본 손 카메라 | **늘 켜짐** | 스테이지에 `--amr-hand-camera --camera-resolution 1280 800`(흡착 그리퍼 + D455) |
| `P3_V2_RAIL_SELECT` | `preferred_first` | M0609 레일 후보 순서(#797). 되돌리기는 `first_feasible` |
| `P3_CAMERA_VIEW` | `0` | 1 이면 QR 추적 영상 `/amr_1/hand_camera/qr_view` 를 작은 창(`rqt_image_view`)으로 띄운다(#787). **촬영 회차는 1**(손 카메라 PiP, [촬영 계획](../presentation/hospital-demo-shotlist.md)) |
| `P3_AUTO_ORDER` | `0` | 자동 주문이 먼저 뜨면 사람 요청이 409 `trip_in_progress` 다 |
| `P3_WEB_PORT` | `8000` | 다른 웹이 떠 있으면 `up` 이 exit 4 로 멈춘다(#536). 그때는 비어 있는 포트를 준다 |
| `P3_SCREEN_SIZE`·`P3_BROWSER` | `2048 1152`·비움 | 화면 반반(Isaac 왼쪽, 웹 오른쪽). 한 바퀴 런카드는 `P3_BROWSER=firefox` 를 준다. 웹 창이 없으면 `boot_check` 의 `window` 점검이 걸린다 |
| `P3_RENDER_MAX` | 주지 않으면 스테이지 상한 1280x720 | 빈 값을 주면 상한이 없다. 촬영 테이크는 `1920x1080` 이다(#577 병합, [hospital-full 6절](hospital-full.md#6-촬영-테이크-재범-924-144x-확정)) |
| `P3_RUN_HOST` | `hostname` | 증거 회차는 `master01`·`master02` 를 준다([배포 런북 4절](deployment.md#4-실행)) |

**"카메라 기본 켜짐"의 뜻:** `v1.1.0` 병원에서는 셋이 다 기본으로 켜진다. 합본 손 카메라, M0609 손 카메라(약통 QR), 봉투·인식표 카메라 QR 판독이다.

기동 예(`<>` 는 사이트 값). 명령 전체와 뜻은 [hospital-full 2절](hospital-full.md#2-한-바퀴)이다.

```bash
export P3_WORLD=hospital P3_SIM_SENSORS=1 P3_AMR_COMBINED=<ridgeback_ur5.usd> P3_M0609=<M0609 자산 루트> \
  P3_HOSPITAL_SCENE=<base.usda> P3_WORKCELL_LAYOUT=<workcell.json> P3_DISPENSER_FILE=<재고 파일> \
  P3_DOMAIN=<도메인> P3_BROWSER=firefox
tools/demo_v2.sh env    # 쓰일 값. hospital 이면 P3_HOSPITAL_SCENE·P3_HOSPITAL_MAP·P3_AMR_START·P3_HOSPITAL_RECEIVER_PRIM·
                        # P3_BELT_TIMEOUT_S·P3_AMR_COUNT·P3_WORKCELL_LAYOUT·P3_POUCH_AT_END 가 더 나온다
tools/demo_v2.sh cmds   # 띄우지 않고 역할별 명령만 본다
tools/demo_v2.sh up
```

`up` 의 순서다. 기동 전 확인 → stage(`stage ready` 대기) → arm(`완료 종류: .*cylinder` 대기) → nav(`fleet up`) → stack(`orchestrator up`) → web → 브라우저·카메라 창.
남의 Isaac 이 떠 있으면 멈추고 출력만 한다.

## 3. 기동 뒤 확인

1. `tools/demo_v2.sh status` 로 세션마다 떠 있는지 본다. `tree` 줄이 받은 SHA 인지 본다.
2. 웹 주소는 `http://127.0.0.1:<포트>/?demo=1` 이다. 상단 띠가 "연결됨"이고 `sim 시간` 이 흐르는지 본다.
3. 창 배치는 Isaac 왼쪽, 웹 오른쪽이다. `tools/demo_window_layout.py` 다음 `tools/boot_check.py` 를 돌린다([hospital-full 2절](hospital-full.md#2-한-바퀴)).
4. 팔 계획 캐시 줄은 `v2 계획 캐시 종류별: cylinder=9/9 module=9/9. 완료 종류: cylinder, module` 이다. 워크셀은 18칸이다([hospital-full 3절](hospital-full.md#3-판정-다섯-장면) ①).

## 4. 웹 요청 순서 — 병실·병상

주문 풀은 `order_pool.hospital.yaml` 이다. 주문은 13건이다. 침상 10개(PDF D1–D10 = `bed_a1`–`bed_a4`·`bed_b1`–`bed_b6`)에 하나씩 있다. 테이블 셋(`station_b`·`station_c`·`station_d`)에 하나씩 있다.

| # | 누를 것 | 화면에 보여야 하는 것 |
| --- | --- | --- |
| 0 | **[리셋]** 한 번 | 트립 칸 `리셋 뒤 대기 중`. 자동 주문은 꺼져 있어 스스로 나가는 주문이 없다 |
| 1 | **[요청 넣기]** → `ord-0001` → 모드 `0 · 1인` → 목적지 **D1 = `bed_a1`** | 병동·병실 버튼(#562)에서 `bed_a1` 이 켜진다 |
| 2 | **[보내기]** → 확인 | 트립 칸에 `ord-0001`. 재고가 떨어지면 보충 흐름 띠가 `정지 → 보충 중 → 재개` 로 간다 |
| 3 | 트립 칸이 `대기 중` 이고 `PAUSED` 가 없을 때까지 기다린다 | 주문 행 `ord-0001` 이 완료 |
| 4 | 다음 요청은 3 이 끝난 뒤에만 넣는다 | — |

- 버튼 이름(`요청 넣기`·`리셋`·`보내기`)은 `web/frontend/index.html` 에 있다. 화면의 나머지 문구는 9/23 기준이다. `v1.1.0` 화면과 하나하나 대조하지 않았다(미확인).
- **첫 요청은 `bed_a1` 로 한다.** 카메라 집기로 끝까지 간 기록은 `bed_a1` 1건뿐이다(실습45). 촬영 계획(#567)의 `bed_a1` 카메라도 이 침상을 본다.
- 참값 집기(protocol v4)는 회전 7(`9760d9d`)에서 침상·테이블·긴급·병실 묶음이 통과했다([회전 장부](../reha/campaigns.md)).
- 카메라 집기에서 다른 침상·긴급·묶음은 확인하지 않았다(#796, #797).
- 보관함 놓기 goal 에는 `zone_id` 가 있다(`PickPouch.action`, 계약 10.1). 팔 params 의 `cabinet_frame` 은 비었을 때만 쓴다.

### 4.1 주문을 차례로 — `tools/hospital_orders.py`

웹 API 로 주문을 줄 세워 넣는다. 판정은 그 결과로 한다. 웹은 `--allow-commands` 로 떠 있어야 한다(`demo_v2.sh up` 이 그렇게 띄운다).

```bash
python3 tools/hospital_orders.py --web http://127.0.0.1:8000 --out $HOME/p3_demo_logs/orders-dry --dry-run   # 계획과 확인만. --out 은 필수다
python3 tools/hospital_orders.py --web http://127.0.0.1:8000 --out $HOME/p3_demo_logs/orders-$(date +%H%M%S)
```

- 프로필(`--profile`)은 셋이다. 도구 머리 주석에 표가 있다.
  - `default`: 1인 `ord-0001` → 긴급 `ord-0002` 끼어듦 → 1인 0003·0004 → 병실 묶음 C2(0005·0006·0007) → 1인 0008·0009·0010. 침상 주문 10건이다.
  - `beds-all`: 풀 13건을 다 넣는다. 요청은 13개다.
  - `station-b`: 병동 묶음 한 건을 `station_b` 로 보낸다.
- `--urgent-after N`(긴급 자리), `--batch`(묶음 주문, 빈 값이면 묶음 없음)로 바꾼다. 동결 protocol attempt 11 은 `--profile default --batch ""` 다.
- 보내기 전에 막는다. 풀에 없는 주문, **이미 쓴 주문**(리셋하고 다시 넣는다), 한 병실이 아닌 묶음이면 exit 2 다.
- 트립이 끝날 때마다 다음을 보낸다. `refill_in_progress`·`trip_in_progress`·`barrier_running`·`insufficient_stock` 은 기다렸다 다시 보낸다.
- 판정이다. 계획의 모든 주문이 `delivered` 면 PASS, exit 0 이다. 아니면 exit 1 이다. `--out` 에 `orders.jsonl`·`requests.jsonl`·`summary.md` 가 남는다.
- 병동 묶음(모드 3)은 `default` 계획에 없다. `station-b` 프로필은 zones 에 `station_b` 가 있어야 돈다. 두 병원 zones 파일에 다 있다.

## 5. 관찰 지점

판정선은 [hospital-full 3절](hospital-full.md#3-판정-다섯-장면)이다. 회차마다 아래 줄 원문을 적는다.

| 구간 | 볼 곳 | 볼 것 |
| --- | --- | --- |
| 기동 | 스테이지 로그 | `hospital_conveyor … "bodies":19 … terminal_surface`, 끝 롤러 두께 0 < t < 0.05 |
| 기동 | 스테이지 로그 | `hospital belt_model … spawn_on_belt=True`, `WARN hospital spawn` 0 줄. 카메라 기본이면 `hospital receiver prim=… settle_s=1.0` |
| ② 보충·약통 QR | 웹 보충 흐름 띠, 스테이지, 팔 로그 | `REFILL_REQUESTED` → `REFILL_DONE`, `refill_ros released … target=`, 병원 prim 과 touch 0. 약통 QR 은 보충마다 `약통 확인: <container_id> cell=<cell> 장착 허용` 한 줄(protocol v4 `scene_container_qr`) |
| ③ 컨베이어 | 스테이지 로그 | 참값: `event …DISPENSED…` → `hospital pouch_at_end …` 한 번씩, `pouch_left_belt` 0 줄, `in_sensor_zone True`. 카메라 기본은 봉투가 A1 탁자에 정착한다. 그 줄 이름은 대조하지 않았다(미확인) |
| ④ 집기 | 스택·팔 로그 | `POUCH_PICKED` → `LOAD_DONE`, 흡착 거리. 카메라 기본은 봉투 `ord-` QR 판독이 먼저다 |
| ⑤ 주행 | 주행 로그 | `Nav2 goal 을 거둔다 … 추종기로`(접근점 넘김), `Failed to make progress`·`No valid trajectories` 줄 수, `speed limit` 줄(근접 0.7 m/s = 70%, #788) |
| ⑥ 전달 | 팔 로그, `/isaac/evaluator/cabinet` | 카메라 기본은 병상 `pt-` 판독과 `AUTH_OK` 가 먼저다. `bed_a1/cabinet` present=true |
| ⑦ 복귀 | 오케스트레이터 트립 끝 줄 | 주문 1건 완료, AMR 도크 복귀(`DOCKED`) |
| 회차 전체 | 스테이지 | `stop reason=… rtf=…`, 롤러 끝(또는 탁자) 봉투 캡처 1장 |

기준을 못 넘으면 그 구간에서 멈추고 다음 구간으로 가지 않는다(RC-6).
Isaac 카메라는 `P3_STAGE_ARGS="--view <이름>"` 로 고른다. 병원 뷰 이름은 `sim/standalone/p3sim/views.py` 의 `HOSPITAL_VIEWS` 와 `amr_chase` 다.
`conveyor_a1`·`a1_pick`·`floor_top`(기본)·`bed_a1`·`station_b`·`m0609_shelf`·`m0609_dispenser`·`m0609_overhead` 가 있다.
`conveyor_a1`·`a1_pick` 은 참값 적재 자리(−8.995, 4.686) 기준으로 골랐다. 카메라 기본 적재 자리(−8.266, 4.102)를 담는지는 미확인이다.

## 6. 종료

```bash
P3_WORLD=hospital tools/demo_v2.sh down     # tmux 세션 이름으로 C-c(camview·browser·cap·web·stack·nav·arm → stage). 안 내려가면 보고만 한다
tools/demo_v2.sh status                     # 남은 세션 0 인지 본다
```

- PID kill·pkill·sudo 는 쓰지 않는다(`demo_v2.sh` 규칙). 남의 Isaac 은 내리지 않는다.
- 로그는 `P3_LOG_DIR`(기본 `$HOME/p3_demo_logs`)에 기동 시각이 붙은 이름으로 남는다. run 기록은 `$HOME/.ros/rokey_p3/runs/<run-id>/` 다.
- 녹화를 멈추고 클립 파일명·크기·sha256 을 #240 에 적는다.
- 리하 회차 기록은 `docs/reha/reha-NN.md` 에 남긴다. 회차 원문은 #240 이다. 이 규칙은 #576 이다.
- 잔류 0 을 확인한다([hospital-full 0절 7](hospital-full.md#0-새-pc-에서-처음-한-번만)).

## 7. 막혔을 때

| 증상 | 원인 | 할 것 |
| --- | --- | --- |
| `up` 이 exit 2, `병원 씬이 없다`·`병원 지도가 없다`·`워크셀 JSON 이 없다` | 필수 파일 경로 | 2절 표의 값을 채운다 |
| `up` 이 exit 2, `P3_WORLD 는 demo 또는 emptyworld` | #553 전 트리다 | 릴리스 태그로 받은 트리로 띄운다([배포 런북 3절](deployment.md#3-릴리스를-따로-받는다)) |
| `up` 이 exit 2, `카메라 집기(P3_CAMERA_POUCHES=1)인데 팔 params 에 … 가 없다` | 카메라 판이 아닌 팔 params 를 줬다 | `P3_UR5_ARM_PARAMS` 를 비워 기본을 쓰거나 camera 판을 준다 |
| 기동 전 확인이 "도메인에 노드가 N 개" | 남의 노드가 같은 도메인에 있다 | 임시 도메인을 쓴다. 어느 값인지는 재범 결정 |
| `up 중단(web) … exit=4` | 포트에 다른 웹이 있다(#536) | `P3_WEB_PORT` 를 비어 있는 포트로 |
| 요청이 409 `trip_in_progress` | 트립이 도는 중 | 트립 칸이 `대기 중` 이 될 때까지 기다린다 |

## 8. 미확인 목록

9/23 초안의 미확정 여덟은 이렇게 풀렸다.
씬과 워크셀은 hospital-full 1절 준비기 출력이다.
재고 파일은 `dispenser.hospital-v0.yaml` 이다. 팔 params 는 `demo_v2.sh` 기본이다.
캐시 대기 줄은 `완료 종류: .*cylinder` 다. 약통 QR 줄은 `약통 확인: … 장착 허용` 이다.
`bed_a1` 밖 목적지는 참값 v4 회전에서 통과했다. `P3_CAMERA_POUCHES` 는 병원 기본 1 이다. 뷰는 `P3_STAGE_ARGS="--view …"` 다.

지금 남은 것:

1. `v1.1.0` 카메라 기본 한 바퀴 L3(미실행).
2. 카메라 집기에서 `bed_a1` 밖 침상·테이블, 긴급, 묶음(미확인).
3. 컨베이어 2배(#789)의 운반 시간·튐·낙하와 근접 0.7 m/s(#788)의 touch(L3 미확인).
4. 카메라 기본에서 탁자 정착을 알리는 로그 줄 이름(미확인).
5. `conveyor_a1`·`a1_pick` 뷰가 새 적재 자리를 담는지(미확인).
6. 두 PC 구성을 `v1.0.0`·`v1.1.0` SHA 에서 돌린 기록(없음, 10절).

## 9. 촬영 화면 점검 — 실물 경로 (웹 오른쪽 절반)

- 무엇: 촬영 화면(#585, `nurse.html?film=1`)이 실물 회차에서 맞게 도는지 보는 10줄이다. 회차 중에 웹 오른쪽 절반을 보며 채운다.
- 여는 법: `P3_WEB_QUERY='nurse.html?film=1'` 을 주고 `tools/demo_v2.sh up` 하면 브라우저가 그 주소로 뜬다. 이미 떠 있으면 주소창에 `http://127.0.0.1:<포트>/nurse.html?film=1` 을 친다.
- **먼저 화면을 확인한다.** 촬영 화면은 큰 배너 아래 막대가 **7칸**이다. 요청, 보충, 조제, 집기, 배송, 도착, 복귀다. 막대가 4칸이면 간호사 화면이다. `nurse.html` 이다. 괄호 안은 약 준비, 병실로 이동, 병상 도착, 전달, 끝이다. 칸 수와 이름이 맞지 않는다. 주소 끝에 `?film=1` 을 붙인다.
- 요청은 이 화면 오른쪽 위 **[약 배송 요청]** 으로 넣어도 되고, 4절처럼 개발자 화면에서 넣어도 된다. 결과는 같다.
- 단계 규칙은 `web/api.md` §1.7 이다. 이벤트 이름은 5절 로그와 같다.
- 결과 칸에는 초록 또는 빨강만 적는다. 빨강이면 그때의 sim 시간을 #240 에 남긴다. 화면 캡처 한 장도 남긴다. 프론트는 빨간 줄만 고친다.

| # | 볼 곳 | 초록(정상) | 빨강(적는다) | 결과 |
| --- | --- | --- | --- | --- |
| 1 | 오른쪽 위 연결 표시, 그 아래 띠 | 처음부터 `실시간`(초록 점)이다. 회차 내내 빨간 `연결이 끊겼습니다` 띠가 없다 | 띠가 뜬다. 또는 `갱신 멈춤` 이 1 s 넘게 보인다. 뜬 시각과 문구를 적는다 | |
| 2 | 큰 배너, 주문 큐 | [보내기] 뒤 2 s 안이다. 배너는 `요청 접수` 다. 막대 `요청` 은 파랗다. 큐 맨 앞에 그 환자가 `지금` 이다 | 5 s 넘게 `대기` 다. 또는 큐가 안 바뀐다 | |
| 3 | 배너 옆 주황 딱지, 막대 `보충` | 이 트립 약이 보충 중이면 `보충 중 <약>` 과 주황 `보충` 칸이 켜진다. `REFILL_DONE` 뒤 꺼진다 | 다른 약 보충에 켜진다. 또는 `REFILL_DONE` 뒤 8 s 넘게 남는다 | |
| 4 | 큰 배너 | `AMR_DOCKED_LOAD`·`DISPENSED` 뒤 `조제 중` 이다 | `요청 접수` 에 멈춰 있다. 또는 단계를 건너뛴다 | |
| 5 | 큰 배너 | `PICK_ATTEMPT`·`POUCH_PICKED` 뒤 `봉투 집는 중` 이다 | 집는 동안 다른 말이다 | |
| 6 | 큰 배너, 목적지, 평면도 고리 | `DEPARTED` 뒤 `배송 중` 이다. 배너 목적지는 요청한 병상이다. 지도의 빨간 고리도 그 병상이다. 예는 `C1 병실 D1` 이다 | 병상이 다르다. 또는 고리가 없다 | |
| 7 | 큰 배너 | `ARRIVED` 부터 `ORDER_DONE` 까지 `도착 · 전달 중` 이다. `RETURNED` 뒤 `복귀 중` 이다 | 도착 전에 `도착` 이다. 또는 1인·긴급인데 막대가 뒤로 간다. 병실 묶음은 다르다. 정거장마다 `배송` 과 `도착` 을 되풀이하는 것이 정상이다(§1.7) | |
| 8 | 큰 배너, 주문 큐 | `DOCKED` 뒤 `전달 완료 · DELIVERED` 다. 큐 끝에 그 환자가 `전달 완료` 다. 다음 요청 전까지 남는다 | `대기` 로 바로 돌아간다. 또는 `배송 끝남 (결과 모름)` 이다. 이때 개발자 화면 주문 `outcome` 을 적는다 | |
| 9 | 평면도 AMR 점, 지도 머리 `위치 N s` | 점이 Isaac 화면의 AMR 과 같은 복도·병실 쪽으로 움직인다. 머리 숫자가 1.0 s 아래다. 멈추면 1 s 안에 따라 선다 | 점이 회색(stale)이다. 또는 `AMR 위치 모름` 이다. 또는 Isaac 과 방이 다르다. 또는 튀어 다닌다. 벌어진 거리를 눈대중(m)으로 적는다 | |
| 10 | 주문 큐 | 2·7·8 번 때마다 2 s 안에 칸이 옮겨진다(진행 → 완료). 리셋하면 전부 `요청 전` 이다 | 5 s 넘게 옛 칸이다. 또는 리셋 뒤에도 `전달 완료` 가 남는다 | |

- 지연의 기준: 자세는 snapshot 으로 온다. 최대 5 Hz 다. 간격은 최대 0.42 s 다(api.md §1.6). 화면은 그 사이를 보간한다. 큐는 1 s 마다 받는다. 그래서 2 s 를 넘으면 빨강으로 본다.
- mock 에서는 AMR 이 `dock_1` 에 서 있다. 9 번은 실물에서만 볼 수 있다.
- `v1.1.0` 카메라 기본은 도크 = 적재 자리다. 도크에서 바로 `AMR_DOCKED_LOAD` 가 난다(#790). 4 번에서 적재 자리로 가는 주행이 없다.

## 10. 두 마스터로 나눠 띄우기

스테이지(Isaac)는 master01 에서 띄운다. 팔, 주행, 스택, 웹은 master02 에서 띄운다. 재범 9/23 이다. `tools/demo_v2.sh` 의
`P3_ROLES`(이 PC 의 역할)와 `P3_PEER`(상대 주소)로 나눈다. 둘 다 비우면 한 PC 로 전부 띄운다.

- 두 PC 구성은 acceptance 회전 1–3 에서 돌았다(#726, #747, #745). 출처는 [v1.0.0 배포 기록](../../evidence/deployments/2026-09-28-jaebeom-v1-0-0.md)이다.
- `v1.0.0` 회전 7 의 두 PC attempt 12·13 은 미실행이다(재범 결정 A). `v1.0.0`·`v1.1.0` SHA 에서 두 PC 를 돌린 기록은 없다.

### 10.1 두 PC 에 먼저 맞출 것

| 무엇 | 값 | 확인 |
| --- | --- | --- |
| 저장소·빌드 | 같은 커밋, 각자 `colcon build` | `tools/demo_v2.sh status` 의 `tree` 줄이 두 PC 에서 같다 |
| `P3_DOMAIN` | 두 PC 같은 값 | 어느 값인지는 재범 결정(2절) |
| `P3_CAMERA_POUCHES` | 두 PC 같은 값 | 이 값이 zones·routes 기본을 가른다. 값이 다르면 스테이지와 주행·웹이 다른 zones 를 읽는다. `up` 의 대조는 한 PC 안에서만 한다 |
| DDS 프로필 | 같은 `~/.ros/fastdds_whitelist.xml` — `127.0.0.1`·`10.10.0.1`·`10.10.0.2` 가 다 있어야 한다 | [유선망 5절](../setup/ros2-wired-network.md). `up` 이 이 PC 주소·상대 주소·`127.0.0.1` 을 찾고 없으면 exit 2 |
| 포트 범위 | `net.ipv4.ip_local_port_range = 40000 60999` | [유선망 4절](../setup/ros2-wired-network.md) |
| 탐색 범위 | 셸에 `ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`·`ROS_LOCALHOST_ONLY=1` 이 없다 | 있으면 `up` 이 exit 2. 두 PC 모드에서는 모든 역할에 `SUBNET` 을 명시해 넘긴다 |
| 스테이지 PC 파일 | 병원 씬·`P3_WORKCELL_LAYOUT`·AMR 합본 | 워크셀·씬은 스테이지만 읽는다 |
| 나머지 PC 파일 | 구역·경로·주문 풀·지도·팔 params·AMR 합본 | 경로는 두 PC 에서 같게(주문 풀은 스테이지·스택·웹이 같은 내용을 읽어야 인증이 맞는다). 합본 파일은 `up` 이 있는지 본다 |

방화벽(ufw)은 9/17 실측에서 두 마스터 모두 `ENABLED=no` 였다([장비 목록](../setup/host-inventory.md)). 그 뒤 값은 미확인이다.
켜져 있으면 DDS 포트가 막힌다. UDP 다. `7400 + 250 × 도메인` 부터다. 도메인 121 이면 37650 부근이다. [유선망 4절](../setup/ros2-wired-network.md). 그러면 `/clock` 이 0 으로 보인다.

### 10.2 순서

```bash
# master01 — 스테이지. 먼저 띄운다. "준비 완료(이 PC 역할: stage)" 가 나올 때까지.
P3_WORLD=hospital P3_ROLES=stage P3_PEER=10.10.0.2 P3_DOMAIN=… P3_M0609=… P3_DISPENSER_FILE=… \
  P3_AMR_COMBINED=… P3_HOSPITAL_SCENE=… P3_WORKCELL_LAYOUT=… tools/demo_v2.sh up

# master02 — 나머지. 스테이지 PC 가 준비된 뒤.
P3_WORLD=hospital P3_ROLES="arm nav stack web" P3_PEER=10.10.0.1 P3_DOMAIN=… P3_M0609=… P3_DISPENSER_FILE=… \
  P3_AMR_COMBINED=… tools/demo_v2.sh up
```

- master01 의 기동 전 확인은 한 PC 때와 같다 — 도메인에 `/clock` 0, 노드 0.
- master02 의 기동 전 확인은 `/clock` 발행자가 정확히 1 이어야 통과한다. 그 1 은 master01 의 Isaac 이다. 0 이면 둘 중 하나다. 스테이지가 아직 안 떴다. 또는 DDS 가 서로 못 본다. 2 이상이면 다른 스택이 같은 도메인에 섞인 것이다. 어느 쪽이든 아무것도 띄우지 않는다.
- 그다음 **`/clock` 이 흐르는지**(2 s 사이 sim 시각이 늘었는지)를 기다린다. master02 는 master01 의 스테이지 로그를
  못 보므로 이것으로 PLAY 를 본다. 로그에 `/clock 공유 확인: 발행자 1(상대 PC 의 스테이지), sim A → B s — 흐른다` 가 찍힌다.
- master02 는 팔, 주행, 스택, 웹 순서로 한 PC 때처럼 기다린다. 팔은 master01 의 PhysX 를 쓴다. 그래서 팔 계획 캐시 대기가 한 PC 때보다 길어질 수 있다. 미확인이다.

### 10.3 확인

| 어디서 | 명령 | 기대 |
| --- | --- | --- |
| master02 | `ros2 topic info /clock` | `Publisher count: 1` |
| master02 | `ros2 topic hz /clock` | 스테이지의 발행 주기(값은 회차에서 적는다) |
| master01 | `ros2 node list` | master02 의 `orchestrator`·`fleet`·`web_gateway` 가 보인다 |
| 웹(master02) | `/api/snapshot` 의 `clock.alive` | `true` — 웹이 master01 의 `/clock` 을 받는다 |

### 10.4 내리기

master02 에서 먼저 `tools/demo_v2.sh down`(웹·스택·주행·팔), 그다음 master01 에서 `down`(스테이지).
나머지 PC 의 `down` 은 스테이지를 건드리지 않는다. 순서가 바뀌면 master02 의 노드가 `/clock` 을 잃는다 — 웹에는
`CLOCK_STOPPED` 가 뜬다.

### 10.5 막혔을 때

| 증상 | 원인 | 할 것 |
| --- | --- | --- |
| master02 `up` exit 2 `상대 … 에 ping 이 안 닿는다` | 유선·스위치 포트 | [host-inventory](../setup/host-inventory.md) 의 포트 배정을 본다 |
| exit 2 `DDS 프로필에 … 가 없다` | 두 PC 의 프로필이 다르다 | 10.1 의 파일을 두 PC 에 똑같이 둔다 |
| exit 3 `/clock 발행자가 0` | 스테이지가 안 떴거나 서로 못 본다 | master01 `status`, 도메인·프로필·방화벽 |
| exit 3 `/clock 발행자가 2` | 다른 스택이 같은 도메인에 있다 | 임시 도메인. 어느 값인지는 재범 결정 |
| exit 4 `/clock 이 … 흐르지 않는다` | 스테이지가 멈춰 있다(PLAY 전·정지) | master01 에서 PLAY 인지 본다 |
