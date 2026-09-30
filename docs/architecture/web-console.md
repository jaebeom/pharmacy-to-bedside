# 관제 웹 서비스

- 상태: **proposed**. 기준: main `f316197`(v1.1.0).
- "구성", "띄우는 법", "동작 규칙", "계약과의 관계", "이력 저장소"는 이 커밋의 `web/` 코드, [`web/api.md`](../../web/api.md), `tools/demo_v2.sh` 와 대조했다.
- API 정본은 [`web/api.md`](../../web/api.md)다. 이 문서는 API 세부를 옮겨 적지 않는다. 필드·코드·주기는 api.md 의 절을 본다.
- 이 문서는 [계약 v1](delivery-contract-v1.md)을 바꾸지 않는다. 계약이 적어 둔 "GUI" 소비자 자리를 웹으로 채운다. `/orders/status`·`/events` 를 보고, `/deliver` 의 클라이언트가 된다.

## 목적

| 단계 | 하는 일 |
| --- | --- |
| 1단계(보기) | 전체 상황, 배송 모드, 알람, 에러 로그를 브라우저 한 화면으로 본다 |
| 2단계(명령) | 리셋 요청, 배송 요청 넣기. `--allow-commands` 로 띄웠을 때만 열린다. 시연 기동(`tools/demo_v2.sh`)은 이 인자를 늘 넘긴다 |

- 시나리오의 "마스터 2 상태 GUI"([시나리오 1절 호스트](../planning/scenario.md#호스트))와 터미널용 `status_monitor`(#92) 자리를 브라우저로 넓힌 것이다.
- 화면은 판정에 쓰지 않는다. 판정 원본은 `event_logger` run 기록과 protocol 이 정한 로그다.
- 예외가 하나 있다. `hospital-full-acceptance-v4` 의 `orders10_delivered`·`orders_beds_all_delivered` 는 `tools/hospital_orders.py` 의 `summary.md` 에서 온다(`tools/hospital_full_metrics.py`).
  그 도구는 웹 API 로 주문을 넣는다(`/api/requests`). 결말은 `/api/snapshot`·`/api/queue` 에서 모은다(`tools/hospital_orders.py` 머리 주석 "판정").

## 구성

| 경로 | 무엇 | 주인 |
| --- | --- | --- |
| `web/frontend/` | 빌드 단계가 없는 정적 페이지. 데이터는 `web/api.md` 의 API 만 쓰고 ROS 를 모른다 | 프론트 |
| `web/backend/` | 게이트웨이. rclpy 구독 + FastAPI(HTTP·WebSocket) | 백엔드 |
| `web/api.md` | 프론트와 백엔드 사이의 계약(HTTP·WS 모양, 거부 코드) | 백엔드 |
| `web/README.md` | 실행 방법·안전 기본값 | 백엔드 |
| `web/COLCON_IGNORE` | colcon 이 `web/` 을 빌드 대상으로 훑지 않게 한다 | 프론트·백엔드 |

- 백엔드는 `rokey_p3_orchestrator.status_view` 에서 `event_key`, 단계표(`TRIP_PHASES`), 신선도 임계를 import 한다(`web/backend/app/orchestrator_view.py:44-51`).
- 이벤트 버퍼·snapshot 조립은 백엔드의 `WorldState`(`web/backend/app/state.py`)가 한다. `status_view.StatusModel` 은 다시 내보내기만 하고 쓰지 않는다.
- 명령(2단계)은 `/orchestrator/reset` 서비스와 `/deliver` 액션 클라이언트다. `--allow-commands` 없이 띄우면 두 클라이언트를 만들지 않는다(`ros_bridge.py:139-144`). 명령 API 는 403 `commands_disabled` 를 돌려준다.

### 화면 (`web/frontend/`)

화면들은 같은 `api.js`·`store.js`·`format.js` 를 쓴다. 설명과 스크린샷은 [`web/frontend/README.md`](../../web/frontend/README.md) 0절이다.

| 화면 | 주소 | 무엇 |
| --- | --- | --- |
| 개발자 | `/`(`index.html`). `?demo=1` 은 시연 모드 | 트립·조제기·알람·신호·타임라인·로그·평면도·카메라·QR 패널(`js/panels/*.js`) |
| 간호사 | `nurse.html` | 배송 4단계, 확인할 알림, 병원 지도, 환자별 약, 요청 창 |
| 촬영 | `nurse.html?film=1` | 1920 녹화의 오른쪽 반. 일곱 단계 배너·평면도·주문 큐 |
| 설정 | `settings.html` | 이 브라우저의 밝기·글자 크기. 서버 설정은 읽기 전용 |

### 백엔드 모듈 (`web/backend/app/`)

| 모듈 | 하는 일 | api.md |
| --- | --- | --- |
| `main.py` | FastAPI 앱, HTTP·WS, 기동 인자 | §3, §10.5 |
| `state.py` | snapshot 조립, 이벤트·로그 버퍼 | §1 |
| `ros_bridge.py` | 구독과 명령 클라이언트. rclpy 를 import 하는 유일한 파일 | §6, §7 |
| `ros_spec.py`·`ros_convert.py` | 구독 표(토픽·QoS·depth), 메시지 → dict | §6 |
| `orchestrator_view.py` | `status_view` 를 import 해 다시 내보낸다 | §0.3, §1.2 |
| `alarms.py` | 알람 규칙(순수 함수) | §4 |
| `request_detail.py`·`refill_detail.py` | `REQUEST_ACCEPTED`·`REFILL_DONE` 의 `detail` JSON 파싱 | §1.3, §2.2 |
| `reject_reason.py` | `/rosout` 에서 goal 거부 사유 찾기 | §0.4 |
| `order_pool.py`·`zones.py` | 주문 풀, 목적지·구역 | §7.3–§7.5 |
| `floorplan.py`·`fleet_poses.py` | Nav2 지도, 여벌 AMR·더미 자리 | §7.6, §1.6 |
| `film.py` | 일곱 단계 `stage`, 주문 큐 | §1.7, §7.7 |
| `live_sensors.py` | 카메라 MJPEG·라이다 스캔(기본 꺼짐) | §1.8 |
| `qr_info.py` | QR 판독 ID → 사람이 읽는 요약 | §1.12 |
| `mock.py`·`faults.py` | fixture 재생, 개발용 고장 흉내 | §8, §11 |

### v1.0.0·v1.1.0 에서 더해진 것

| 무엇 | api.md | 릴리스 본문의 PR | L3 |
| --- | --- | --- | --- |
| 감속기 속도 제한 `signals.speed_limit`, WS `speed_limit` | §1.9, §3 | v1.0.0: #753 #764 | 회전 7 트리에 있었다 |
| 여벌 AMR·더미 `robots[]`·`dummies[]` | §1.6 | v1.0.0: #754 #775 | #754 는 회전 7 트리에 있었다. #775(화면 5파일)는 그 뒤다 |
| 도킹·지도 알림(`/p3/alerts`) 알람, `OBSTACLE_STOP` | §4.1 | v1.0.0: #757 #766 | 회전 7 트리에 있었다 |
| Play/Stop `sim_running` | §1.11 | v1.0.0: #759 #766 | 회전 7 트리에 있었다 |
| 두 PC `deployment` | §1.10 | v1.0.0: #766 | 다중 PC attempt 12·13 은 미실행이다 |
| 카메라·스캔 `--live-sensors` | §1.8 | v1.0.0: #763 | 회전 7 트리에 있었다. 켰는지는 미확인 |
| 약 QR 칩·사유, QR 판독 요약 `qr_reads`, QR 추적 영상 `qr_view` | §4.1, §1.12, §1.8 | v1.1.0: #785 #786 #787 | 미실행 |
| 재고 `dispenser.stock` | §6.1 | v1.1.0: #791 | 미실행 |

- 출처: `gh release view v1.0.0`("관제 웹. 속도 제한, 여벌 AMR·더미 평면도, Play/Stop, 알람, 운영 상태"), `gh release view v1.1.0`.
- "회전 7 트리"는 v1.0.0 회전 7 을 돌린 `9760d9d` 다. 그 트리에 있었다는 뜻이다. v4 지표에 웹 화면 표시 항목은 없다(웹 창은 녹화 품질 지표만 본다).
- 백엔드 쪽 PR(#767 deployment, #768 알람, #769 sim_running, #770 fleet poses)은 릴리스 본문에 없다. 넷 다 `9760d9d` 까지 들어 있다(`9760d9d` 가 #767 병합이다).
- v1.1.0 칸의 "미실행"은 #772 댓글 5891599172(9/29)의 잠금 범위 표를 따른다. v1.1.0 커밋으로 돌린 acceptance 회전은 없다.
- 9/29 연습 회차([practice-45](../practice/simworld/practice-45.md), `05b8e28`)는 관제 웹을 같이 띄웠다. 웹 표시 항목별 관측은 그 기록에 없다.

## 동작 규칙

| 항목 | 규칙 |
| --- | --- |
| WebSocket 주기 | 변화가 있으면 최대 5 Hz(0.2 s)로 합쳐 보낸다. 변화가 없어도 1 s 에 한 번 `snapshot` 을 보낸다(`main.py` `WS_MIN_INTERVAL_S`·`WS_IDLE_PUSH_S`, api.md §3) |
| 연결 끊김 판정 | 화면이 마지막 WS 프레임 뒤 3 s 로 판정한다(`web/frontend/js/api.js` `PUSH_GRACE_S`) |
| 신선도 판정 | 연결 끊김과 다른 판정이다. 신호 1.0 s, `/clock` 2.0 s, `dispenser`·`speed_limit`·`sim_running` 3.0 s(api.md §1.1, §1.9, §1.11) |
| 거부 코드 | 명령 거부는 코드 14종으로 돌려준다. 목록은 api.md §0.4 |
| `--mock-fault` | 개발 전용 고장 흉내. `--mock` 없이 주면 기동을 거부한다(`main.py` `main()`) |
| 배송 모드 출처 | `REQUEST_ACCEPTED` 이벤트의 `detail` compact JSON(#104). `detail` 이 비면 모드는 `null` 이다. 오류가 아니다(api.md §1.3) |
| 트립 상태 | `status_view` 단계표로 최근 이벤트에서 **추정**한다. orchestrator FSM 상태를 읽지 않는다 |
| 인증 | 없다. `--host` 를 `127.0.0.1` 밖으로 열면 기동 로그에 경고가 찍힌다(`main.py` `host_warnings`) |

## 띄우는 법

| 단계 | 어디서 | 조건 |
| --- | --- | --- |
| ① 개발 | 아무 PC | `--mock`(fixture 재생), `127.0.0.1` 에만 bind. ROS 가 필요 없다. 명령은 [`web/README.md`](../../web/README.md), 병원 mock 은 api.md §10.6 |
| ② ROS 연결 확인 | 개발 PC 로컬 | `stub_loop` 와 실물 모드 백엔드를 같은 PC 에서 띄운다. 남과 겹치지 않는 `ROS_DOMAIN_ID` + `ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`. 절차는 api.md §10.7 |
| ③ 시연 | 스택과 같은 PC(`tools/demo_v2.sh` 의 `web` 역할. 두 PC 면 `P3_ROLES` 에 `web` 이 있는 쪽) | 아래 |

시연 명령의 정본은 `tools/demo_v2.sh` 의 `web_cmd()` 다(483–494행). 모양은 이렇다.

```bash
cd web/backend && $P3_WEB_PY -m app.main --host $P3_WEB_HOST --port $P3_WEB_PORT \
  --allow-commands --static $P3_REPO/web/frontend \
  --order-pool $P3_ORDER_POOL --zones-file $P3_ZONES --catalog $P3_CATALOG \
  --dispenser-file $P3_DISPENSER_FILE
# P3_WORLD=hospital 이면 뒤에 붙는다:     --map-file $P3_HOSPITAL_MAP
# 두 PC(P3_PEER 있음)이면 뒤에 붙는다:   --roles "<이 PC 의 역할>" --peer $P3_PEER
```

- bind 기본은 `127.0.0.1:8000` 이다(`P3_WEB_HOST`·`P3_WEB_PORT`).
- 브라우저 주소 뒤에 `P3_WEB_QUERY` 를 붙인다. 기본은 `?demo=1` 이다(개발자 화면 시연 모드). 빈 값을 주면 일반 화면이다.
- `--live-sensors`·`--show-evaluator` 는 넘기지 않는다. 둘 다 기본 꺼짐이다.
- 실제로 칠 명령은 `tools/demo_v2.sh cmds` 로 본다. 병원 운영 절차는 [병원 월드 데모 runbook](../runbooks/hospital-demo.md)이다.
- 도메인은 **`P3_DOMAIN`** 이다. `demo_v2.sh` 가 스테이지·팔·스택·웹에 같은 값을 넘긴다. 9/23–24 회차는 131·141 이었다([9/24 설계 점검](../analysis/2026-09-24-design-gap-plan.md) G6).
- **재범 결정(9/24)**: 웹의 도메인은 고정값을 두지 않는다 — 시연 웹은 `P3_DOMAIN`(스택과 같은 값)이다. 도메인 규칙은 [9/17 실측의 도메인 규칙](../setup/ros2-wired-network.md#도메인-규칙)을 따른다.
  - 결정 기록은 [9/24 미결 결정표](../analysis/2026-09-24-open-decisions.md) 5행이다(재범 9/24 13:30 "미결 권고대로 진행", #576 댓글).
- 내릴 때는 `tools/demo_v2.sh down` 을 쓴다. tmux 세션 이름(기본 `p3v2-web`)으로 C-c 를 보낸다. 손으로 띄운 웹도 그 tmux 세션에 C-c 를 보낸다. PID kill 은 쓰지 않는다(`tools/demo_v2.sh` 10–11행).

## 계약과의 관계

- 새 msg·srv·action 타입은 없다. 메시지는 `rokey_p3_interfaces` 와 ROS 표준 패키지 것만 쓴다(`ros_bridge.py` import).
- 웹이 보려고 계약 밖 토픽이 생겼다. `/p3/alerts`(#757), `/isaac/fleet/poses`(#754), `/p3/sim_running`(#759)이다. 셋 다 `std_msgs`(String JSON·Bool)다.
- 구독 목록 전체는 api.md §6 이다. 누가 내는지는 [시스템 개요](system-overview.md)다.
- 배송 모드는 계약 메시지를 바꾸지 않고 `REQUEST_ACCEPTED.detail` 문자열(#104)에서 읽는다. 계약 2.6 에 이 한 줄을 적을지는 재범 결정 뒤다(보호 경로). v1.1.0 의 계약 2.6 에는 아직 없다.
- 2단계 명령은 계약에 이미 있는 입구(`/orchestrator/reset`, `/deliver`)만 쓴다. 수락 조건은 계약 [`/deliver`](delivery-contract-v1.md#deliver) 그대로다.
- 웹은 보내기 전에 수락 조건을 먼저 검사한다(api.md §7.2 검사 순서).
- 그중 `refill_in_progress`·`insufficient_stock` 은 orchestrator 의 goal 수락 검사(`orchestrator_node.py` `_on_deliver_goal`, `trip_fsm.py` `refusal`)에 없다. 같은 요청이 웹을 거칠 때만 이 둘로 막힌다.

## 이력 저장소 — 메모리

- **재범 결정(9/24): 메모리로 두고 한계를 명시한다.** 결정 기록은 [9/24 미결 결정표](../analysis/2026-09-24-open-decisions.md) 6행이다.
- 백엔드에는 저장소가 없다. `state.py` 가 메모리에만 이벤트를 모은다. 재시작하면 화면이 빈다(`grep -riE 'sqlite|postgres|database' web/backend/app/` 0건, v1.1.0).
- 회차 기록의 원본은 `event_logger` 의 run 디렉토리다. 로봇 제어 경로에도 DB 는 없다(FSM 은 메모리).
- 한계(v1.1.0 `state.py`):
  - 이벤트 버퍼 500건(`event_buffer`), 로그 500줄(`log_buffer`), snapshot `recent_events` 12건(`max_events`). 넘으면 오래된 것부터 버린다. `main.py` 는 기본값을 바꾸지 않는다.
  - `qr_reads` 는 최근 20줄이다(`QR_READS_MAX`).
  - 판정·큐(`/api/queue`)는 현재 epoch 만 본다. 리셋하면 지난 epoch 주문은 대기로 돌아간다.
  - 웹을 재시작하면 latched 토픽(`/events` depth 500, `/orders/status` depth 50)으로 다시 받는 만큼만 돌아온다(`ros_spec.py`).
- 옛 제안(9/24 결정으로 두지 않는다): run 별 JSONL 을 원본으로 두고, 웹 백엔드가 조회용 SQLite 하나를 둔다. 두 곳이 다르면 JSONL 이 맞다.

## 지난 기록 (9/17–9/18)

> 지금 기준이 아니다. 결론만 위 절에 옮겼다.

- `web/` 코드는 프론트 PR #112, 백엔드 PR #117(실물 브리지 포함)로 들어왔다. `check_repository` 의 `web/` 영역 허용은 PR #114 다.
- 개발은 삼성 PC(`rokey-550XBE-350XBE`)에서 했다. 그 PC 는 저장소에 deploy key(쓰기 허용)로 붙었다(9/17 기록, v1.1.0 에서 확인하지 않음).

### `master02` 환경 관측 (9/17, 미확인)

| 항목 | 값 |
| --- | --- |
| 브라우저 | `firefox`, `google-chrome` 있음 |
| Python | 3.12.3 |
| fastapi | 없음 |
| PyPI 접속 | HTTP 200 |
| 포트 8000-8010 | 비어 있음 |

### 9/17 의 미결정 표와 지금

| 항목 | 9/17 내용 | 지금(v1.1.0) |
| --- | --- | --- |
| `master02` venv 에 pip 설치 | **정함: 허용(9/17 저녁, 재범).** 관제 웹 백엔드 requirements 를 venv 안에 설치한다. sudo 없음 | `demo_v2.sh` 는 `web/backend/.venv/bin/python` 을 쓴다(`P3_WEB_PY`) |
| 9/21 범위 | 보기 + 리셋 버튼까지인지, 요청 넣기까지인지 | 시연 기동은 `--allow-commands` 로 띄운다. 보기·리셋·요청이 다 열린다 |
| 포트 | 정하지 않았다. 9/17 관측으로는 8000-8010 이 비어 있다 | `P3_WEB_PORT` 기본 8000 |
| 저장소(이력 조회) | 미결정 | 위 "이력 저장소" 절(재범 결정 9/24) |
