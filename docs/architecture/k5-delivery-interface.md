# K5 인증·전달 v0 — 팔이 필요로 하는 인터페이스

- 상태: **제안.** 구현 완료·승인 표시가 아니다. 결정 44 = A 확정(재범 9/24)이고, v1.1.0 코드에는 반영 전이다(3절). L3 는 7절에 적는다.
- 기준: main `f316197`(v1.1.0)의 코드와 대조했다(2026-09-30). [배송 계약 v1](delivery-contract-v1.md). 처음 코드는 PR #414(9/21 병합)다.
- 인증 v0 = **참값 인증**(`scan_tag_source: sim`, `ScanTag`·`CabinetObservation`). 카메라 인증은 v1 옵션이다(재범 결정 9/24, #576). 결정 44(집을 칸 전달, 3절)와는 다른 결정이다.
- **지금 코드 기본(v1.1.0)은 병원에서 카메라다.** 병원은 봉투 QR 과 인식표(`pt-`·`st-`)를 손 카메라로 읽는다(`P3_CAMERA_POUCHES`·`P3_CAMERA_TAGS` = 1, `tools/demo_v2.sh` 60–64·158–164행, 스택 `scan_tag_source:=camera` 442–444행). 재범 9/29 지시("QR 반드시 찍고", #784 본문)가 병원에서 위 결정을 대신한다고 `demo_v2.sh` 158–160행이 적는다(#797 이 v1.1.0 기본으로 묶었다). 이 결정을 대체하는 ADR 은 [ADR 0007](../adr/0007-hospital-camera-qr-dock-at-load.md)(proposed)이다. [ADR 0004](../adr/0004-auth-pick-v0-truth-sensors.md) 본문은 그대로다. 빈월드는 `P3_SIM_SENSORS=1` 일 때 참값 인증이다(454행).
- 범위: **팔(UR5) 쪽 인터페이스만.** orchestrator 의 `Deliver` 상태 머신은 재범 소유라 여기서 정하지 않는다.

**결론부터: 새 액션도 새 메시지도 필요 없다.** 기존 `PickPouch`·`ScanTag`·`TagRead`·`CabinetObservation` 으로 된다.
결정이 필요한 것은 **하나**(집을 칸 전달, 결정 44)다. 그 뒤 기존 `PickPouch` 에 `zone_id` 한 칸이 더해졌다(#624, 1절).

---

## 1. 전달 v0 — 기존 `PickPouch` 로 된다

`PickPouch.action` 이 "칸 → 보관함"을 정의한다. v1.1.0 의 goal 칸은 넷이다.

```
string order_id
uint8 source        # SOURCE_BELT=0, SOURCE_DECK=1
int32 target_slot   # 상판 칸 번호. -1 이면 보관함
string zone_id      # 보관함 침상. 비면 팔 파라미터 cabinet_frame (#624, 계약 10.1)
```

| 무엇 | 값 |
| --- | --- |
| 전달 호출 | `source=SOURCE_DECK`, `target_slot=-1`, `zone_id=<정거장 zone>`(`trip_fsm.py:1063–1065`) |
| 놓을 곳 | `zone_id` 가 있으면 **`<zone_id>/cabinet`**, 비면 `cabinet_frame` 파라미터(`arm_node.py:1112–1122`). 한 정거장에 봉투가 여럿이면 프레임 x 로 비켜 놓는다(`arm_node.py:1380–1388`) |
| 결과 | 기존 `outcome` 그대로(`ok`·`not_detected`·`qr_mismatch`·`grasp_failed`·`dropped`·`timeout`·`rejected_interlock`) |
| 이벤트 | `PICK_ATTEMPT`(detail `deck`) → `POUCH_PICKED` → **`POUCH_PLACED`** |

`POUCH_LOADED` 가 아니라 `POUCH_PLACED` 다. 지금 코드가 `target_slot < 0` 이면 그렇게 낸다(`arm_node.py:1543`).

### 놓는 높이

`place_z_offset_m = 0.015`. `<zone>/cabinet` 원점이 **"보관함 칸 바닥 윗면의 중심"**(계약 [3절](delivery-contract-v1.md#3-프레임과-단위))이고, 상판 칸과
같은 뜻의 면이므로 상판에서 쓰는 값이 그대로 온다: `rest_gap`(0.005) + 봉투 두께(0.010).
코드 기본은 0.0 이다(`arm_node.py:362`). 병원 카메라 params 가 0.015 를 준다(`ur5_arm.amr-combined.camera-receiver.yaml:44`). 봉투 두께가 바뀌면(`--pouch-size` 의 z) 이 값도 같이 바뀐다.

---

## 2. 계약 규칙과의 차이 — v0 은 **QR 없이** 집는다(v1.1.0 병원 기본은 QR 로 집는다)

계약 [2.3절](delivery-contract-v1.md#23-팔-manipulation)의 `source=DECK` 규칙은 이렇다.

> 상판에서 **QR 이 `order_id` 인 봉투를 찾아** `<zone>/cabinet` 에 놓는다.

9/21 의 v0 은 YOLO·봉투 QR 을 뒤 카드로 미뤘다. 그때는 검출(`PouchDetection`)을 낼 주체가 없었다. `_wait_for_pouch` 가
`source` 와 무관하게 검출을 기다리므로 **전달이 시작조차 못 하고 `not_detected` 로 닫혔다.**

그래서 **`deck_pick_from_frame`(기본 `false`, opt-in)** 을 둔다. 켜면 검출 대신 **칸 TF** 로 파지 자세를 만든다.
봉투가 칸 바닥 윗면(= `deck_slot_*` 원점)에 얹혀 있으므로 흡착면 목표 = **칸 원점 + `pouch_height_m`**(기본 0.01).

**이것은 계약 규칙의 v0 우회다.** 검출을 쓰지 않으므로 **봉투가 거기 있는지, 그 주문의 봉투인지 확인하지 않는다.** 그래서 opt-in 이고, 이 우회가 **결정 44 의 배경**이기도 하다.
**v1.1.0 병원 기본은 이 우회를 쓰지 않는다.** `pouch_detector`(색 + QR)가 검출을 내고, 봉투 QR 이 goal 주문과 맞아야 집는다(`pick_permission.py:51–63`, `arm_node.py:1720–1744`). `deck_pick_from_frame` 을 켜는 기동 인자는 `demo_v2.sh` 에 없다.

---

## 3. 결정 44 — 집을 칸을 어떻게 전달하는가

`source=SOURCE_DECK` 에서 **`target_slot` 은 "놓을 곳"**(보관함이면 −1)이라 **집을 칸을 담을 자리가 없다.**

| 안 | 내용 | 장단 |
| --- | --- | --- |
| **A. `source_slot` 필드 추가** | `PickPouch` 에 `int32 source_slot`(기본 0) | 뜻이 분명하다. **메시지 변경**이라 계약 9절(wire 호환)·백엔드에 알려야 한다 |
| B. `order_id` 로 찾는다 | 팔이 "그 주문을 어느 칸에 넣었는지" 기억해 되쓴다 | 메시지 불변. 다만 **팔이 상태를 갖는다** — 리셋·재기동이 잦은 이 시스템에서 나중에 물린다 |
| C. orchestrator 가 TF 이름을 준다 | 기존 문자열 필드가 없어 사실상 A 와 같다 | — |

**권고는 A 였다.** → **재범 결정 9/24(#576): A 확정.** `PickPouch` 에 `int32 source_slot` 을 더한다.
코드(`.action`·`_source_slot()`)는 **촬영 뒤 별도 카드**다(9/24). 그때까지 `.action` 은 건드리지 않는다.

그때까지 코드는 **`_source_slot(goal)` 한 함수**가 `0` 을 돌려준다. v0 한 바퀴는 1인 주문 한 건이라 적재도 전달도 칸 0 이다.
**v1.1.0(`f316197`)에서도 반영 전이다.** `PickPouch.action` 에 `source_slot` 이 없고, `_source_slot()` 은 0 을 돌려준다(`arm_node.py:1103–1110`). 영향은 7절에 적는다.

---

## 4. 인증 v0 — `scan_tag` 서버는 **팔 노드**다

**재범 결정 9/24(#576)**: 인증 v0 은 아래 `scan_tag_source: sim`(참값 인증)이다. 손 카메라 QR 판독 인증(`camera`)은 v1 옵션이다. 코드 기본값(`camera`)은 이 문서가 바꾸지 않는다 — 한 바퀴 조합은 `demo_v2.sh` 가 `P3_SIM_SENSORS=1` 일 때 `scan_tag_source:=sim` 을 준다.

**v1.1.0 병원 기본은 손 카메라 인증이다**(#784·#797). 이 결정을 대체하는 ADR 은 [ADR 0007](../adr/0007-hospital-camera-qr-dock-at-load.md)(proposed)이다. 팔이 `<zone>/tag` 를 0.25 m 에서 보고 읽는다(`tag_standoff_m`, `ur5_arm.amr-combined.camera-receiver.yaml:39`). 참값 인증은 `P3_CAMERA_TAGS=0` 과 `P3_SIM_SENSORS=1` 을 함께 줄 때다(`demo_v2.sh` 446–447행).
카메라 판독은 접두를 뗀 ID 를 낸다(`pt-2001` → `2001`, `qr_payload.py:23–29`). 참값 센서는 `pt-` 가 붙은 전체 문자열을 낸다(`truth_sensors.py:138–145`). orchestrator 는 그 정거장의 ID 이면 둘 다 받는다(`trip_fsm.py:1197–1205`, `f8341ba7`, #796).

orchestrator 는 트립마다 `{namespace}/scan_tag`(`ScanTag` 액션)를 부르고, 결과가 OK 가 아니면
`UNREADABLE` → `AUTH_FAIL` 이다. **그 액션의 서버가 UR5 `arm` 노드다.**

코드 기본은 `tag_standoff_m` 0·`tool_frame` 빈 값이다(`arm_node.py:372·374`). 이대로 `camera` 면 `run_scan_tag` 이 시도하지 않고 `UNREADABLE` 로 닫는다(`arm_node.py:2018–2029`).
병원 카메라 params 는 두 값을 준다(0.25 m, `amr_1/ur_arm_wrist_3_link`, 같은 파일 32·39행). `demo_v2.sh` 는 `P3_CAMERA_TAGS=1` 인데 `tag_standoff_m` 이 0 이하면 기동을 멈춘다(639–644행).

### `scan_tag_source: camera | sim` (코드·launch 기본 `camera`)

코드 기본은 `camera` 다(`arm_node.py:323`, `stub_loop.launch.py:226`). launch 값이 팔 params 파일 값보다 우선한다(`stub_loop.launch.py:97–98`).
`sim` 이면 **팔을 움직이지 않고** 스테이지가 내는 시뮬 센서값으로 `ScanTag` 결과를 채운다.

| 항목 | 값 |
| --- | --- |
| 토픽 | **`/{ns}/sim/tag_reads`**, 기존 `rokey_p3_interfaces/msg/TagRead`(`arm_node.py:635–638`) |
| 내용 | `kind=KIND_PATIENT`, `status=STATUS_OK`, `tag_id = "pt-" + patient_id`(계약 7절). 스테이션 자리(kind station)면 `KIND_STATION`·`st-<zone>` 이다(`truth_sensors.py:148–160`, 재범 9/25) |
| 환자 ID 출처 | **주문 풀**이다. 스테이지가 `--order-pool` 로 `bed → pt-<patient_id>` 표를 만든다 |
| 언제 내나 | **AMR 이 실제로 서 있는 침상**의 인식표. 그것이 스텁이 아니라 센서인 이유다 |

**계약 토픽 `hand_camera/tag_reads` 에 내지 않는다.** 거기는 `perception` 이 쓰는 토픽이라 작성자가 둘이 되고,
이름도 "손 카메라"라 뜻이 맞지 않는다. 토픽을 나누면 **계약 토픽의 단일 작성자가 유지되고**, perception 을
띄우지 않는 조합(빈월드)에서도 된다. 카메라 모드의 `hand_camera/tag_reads` 작성자는 `pouch_detector` 다(`pouch_detector_node.py:121`).

### ⚠️ yaw 가 판정에 들어가야 한다

`bed_a1` 과 `bed_b1` 은 **같은 (x, y) 에 yaw 만 ±π/2 반대**다(통로 하나를 두 줄이 공유한다).
**위치만 보면 못 가른다.** 위치 공차와 yaw 공차 둘 다로 판정한다(zones 의 `tol_xy`·`tol_yaw`).
이것이 빠지면 "다른 침상에서 `AUTH_FAIL`" 이라는 음성 판정이 통과해 버린다.

### fail-closed 둘

- 한 침상에 환자가 둘 이상이면 **스테이지가 기동을 거부**한다(어느 인식표를 낼지 모른다, `truth_sensors.py:232–252`).
- 풀에 없는 침상 앞에서는 **아무것도 내지 않는다** → 팔이 시한까지 기다려 `UNREADABLE`.

### 곁가지 — `sim` 이 함정 하나를 피한다

`camera` 경로는 `tool_frame` 을 쓴다. `/tf` 에 나가는 끝단 프레임은 **`amr_1/flange`** 인데(Isaac 5.1 `ur5.usd` 에
`tool0` prim 이 없다), `flange` 는 `tool0` 과 **원점은 같고 회전이 다르다**(`END_TO_TOOL` = 0.5, 0.5, 0.5, 0.5).
`arm_node` 는 tool0 규약을 가정하므로, 카메라 경로를 켤 때 이 회전을 넣지 않으면 **조용히 돌아간 자세로 간다.**
`sim` 은 팔을 움직이지 않아 이 자리를 통째로 지나간다.
v1.1.0 병원 카메라 params 의 `tool_frame` 은 `amr_1/ur_arm_wrist_3_link` 다(32행). 이 설정이 위 회전 문제를 어떻게 다루는지는 대조하지 않았다(미확인).

---

## 5. 프레임과 참값

| 무엇 | 이름 | 작성자 | 뜻 |
| --- | --- | --- | --- |
| 보관함 | **`<zone>/cabinet`**(슬래시) | `zones_tf`(주행 launch, `zones_tf_node.py:61–65`) | 보관함 칸 바닥 윗면의 중심(계약 [3절](delivery-contract-v1.md#3-프레임과-단위)) |
| 침상 인식표 | `<zone>/tag` | `zones_tf` | 계약 [3절](delivery-contract-v1.md#3-프레임과-단위) |
| 상판 칸 | `<robot>/deck_slot_N` | isaac(`p3sim/sensors.py:54`) | 칸 바닥 윗면 중심(결정 23). **N 은 1부터** — `PickPouch.target_slot` 은 0 부터라 `deck_slot_frame_base` 로 맞춘다(결정 28 대기). 코드 기본은 0, 병원 카메라 params 는 1 이다(`arm_node.py:309`, yaml 41행) |

**보관함 참값은 `/evaluator/cabinet`(`CabinetObservation`)이다.** 새 이름을 만들지 않는다.
그 메시지가 **"Operating nodes (orchestrator, arm, fleet) must not subscribe to it; only event_logger does"** 라고
못박고 있으므로 **팔은 구독하지 않는다.** 합격선은 event_logger 가 쓴 run 기록으로 본다.
이 토픽은 `P3_SIM_SENSORS=1` 일 때만 나온다(스택 `sim_cabinet:=true`, `demo_v2.sh` 445·447·454행, `isaac_adapter.py:208–209`). 병원 기본(`P3_SIM_SENSORS=0`)에서는 나오지 않는다.

보관함은 **위가 열린 칸**이어야 한다. 속이 찬 상자 위에 얹으면 `<zone>/cabinet` 이 계약과 다른 것을
가리키고, 참값도 "윗면 위에 있다"는 근사밖에 못 낸다. "월드는 갈아 끼우되 이름·프레임·계약은 같다"가 원칙이다.

---

## 6. 판정 뜻 (결과 전에 고정)

| 무엇 | 뜻 |
| --- | --- |
| 인증했다 | 스테이지가 그 침상의 센서값을 낸 **뒤에** `ScanTag` 가 OK 로 닫히고 `AUTH_OK` 가 찍힌다 |
| 인증 음성 | **AMR 이 다른 침상에 서 있으면 `AUTH_FAIL`.** 통과하면 센서가 아니라 스텁이다 |
| 인증 대기 | 센서값이 오기 전에는 시한까지 기다려 `UNREADABLE` |
| 전달했다 | **`/evaluator/cabinet` 의 `present=true`**(그 침상·그 주문) + `CABINET_LOCKED` → `ORDER_DONE` |

**"놓기 명령 완료"로 세지 않는다.** v0 은 `placement_check` 를 켜지 않으므로 팔의 `ok` 는 "놓기 명령 + 대기"일
뿐이고, 그 구멍이 P32 다. K4 에서 팔의 `ok` 가 아니라 스테이지의 `in_slot=True` 로 판정하기로 한 것과 같은 이유다.
v1.1.0 에서도 `placement_check_enabled` 는 기본 끔이고 병원 카메라 params 에 없다(`arm_node.py:205`).
v1.1.0 병원 기본에서 "센서값"은 손 카메라 판독이다. "전달했다"를 재려면 `P3_SIM_SENSORS=1` 로 보관함 참값을 켜야 한다(5절).

---

## 7. 미확정·미실행

- **결정 44** = A 확정(재범 9/24). v1.1.0 에도 코드 반영 전이다(`PickPouch.action` 에 `source_slot` 없음, `arm_node.py:1103–1110`). 집을 칸은 0 이다.
- 카메라 집기의 상판 관측 자세도 칸 0(`deck_slot_1`) 위다(`arm_node.py:1580–1581`). 봉투는 그 화면에서 주문 QR 로 고른다. 한 정거장에 봉투가 여럿일 때 다른 칸 봉투가 그 화면에 드는지는 미확인이다.
- **결정 28**(칸 프레임 번호의 기준) 대기. 그때까지 `deck_slot_frame_base` 로 덮는다. 코드 주석도 아직 열린 것으로 적는다(`arm_node.py:308`).
- `scan_tag_source` 는 main 에 있다(`arm_node.py:323`). 9/21 에 "K2 뒤 별도 PR" 이라고 적었던 항목이다.
- `<zone>/cabinet` 이름은 코드로 대조했다(`f'{zone_id}/{suffix}'`, `zones_tf_node.py:61–65`). 실행 중 `/tf_static` 원문 관측은 미확인이다.
- L3(참값 인증): v1.0.0 회전 7(`9760d9d`, protocol v4 = `P3_SIM_SENSORS=1`)에서 master01 14/14 통과했다(v1.0.0 릴리스, 판정 표 #771 `5867873681`). 그 트리에는 `P3_CAMERA_TAGS` 가 없었다.
- L3(카메라 봉투·인식표): `05b8e28` 에서 bed_a1 1건만 `DELIVERED` 였다([실습 45](../practice/simworld/practice-45.md), #796). 다른 병상·스테이션 인식표·반복은 미실행이다.
- v1.1.0(`f316197`) 커밋으로 돌린 L3 는 없다(v1.1.0 릴리스 본문).
- 이 문서의 값 중 `place_z_offset_m` 0.015·`deck_slot_frame_base` 1·`tag_standoff_m` 0.25 는 병원 카메라 params 에 들어갔다. `deck_pick_from_frame` 은 어느 기동 경로에도 켜지지 않는다.
