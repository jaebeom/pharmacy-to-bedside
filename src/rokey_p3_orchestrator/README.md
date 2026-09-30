# rokey_p3_orchestrator

v1.1.0 병원 한 바퀴에서 `orchestrator` 가 웹에서 들어온 `Deliver` 요청을 받아 조제 → 적재 → 병상 배송 → 도크 복귀를 트립 FSM 으로 돈다.
조제기 재고가 떨어지면 `/m0609/refill` 로 보충을 시키고, 약 DB(`pharmacy_db:=true`)로 M0609 의 약통 QR 을 확인해 준다.
`event_logger` 가 run 기록을 남기고 `SUCCESS` 는 Isaac 보관함 관측으로만 쓴다. `order_generator` 는 병원 구성에서 끈다(`use_order_generator:=false`).

요청 수락, 배차, 조제기 재고 로직, 주문 종료 상태, 메트릭 이벤트. **orchestration 담당**의 단독 영역이다.
공용 패키지 `rokey_p3_interfaces`, `rokey_p3_bringup`, `config/` 도 이 담당이 소유한다.

이름과 규칙의 기준은 [계약 v1](../../docs/architecture/delivery-contract-v1.md),
트립 순서의 기준은 [ADR 0001](../../docs/adr/0001-orchestrator-trip-fsm.md)이다.

## 노드

| 실행 | 무엇 | 계약 |
| --- | --- | --- |
| `ros2 run rokey_p3_orchestrator orchestrator` | `Deliver` 서버. 트립 FSM 배선, 인터락 사전 확인, 리셋 barrier, `Refill` 클라이언트 | 1절, 2.3절, 5절, 6절 |
| `ros2 run rokey_p3_orchestrator order_generator` | 주문 풀을 읽어 `Deliver` goal 을 한 건씩 낸다 | 1절, 2.5절 |
| `ros2 run rokey_p3_orchestrator event_logger` | `/events`, `/orders/status`, `/evaluator/cabinet` 을 run 별 JSONL 로 | 1절, 8절 |
| `ros2 run rokey_p3_orchestrator status_monitor` | 구독만 하는 텍스트 상태 화면(1 Hz). 시연·통합 때 한 화면으로 흐름을 본다 | 2절, 4절 |

## 순수 로직 (ROS 없이 테스트한다)

| 모듈 | 무엇 |
| --- | --- |
| `terminal_states.py` | 주문 종료 상태 이름 네 개(`SUCCESS`·`HOLD_RETURN`·`ABORT`·`TIMEOUT`)의 상수와 종료 여부·트립 성공 판정 보조 함수. 현재 상태값 저장소는 아님 |
| `order_pool.py` | 주문 풀 검사, 요청 큐(긴급 우선), `request_id` 형식, QR 접두 |
| `request_pacer.py` | 발행기가 언제 어느 요청을 보낼지. epoch 따라 큐 다시 채우기, 리셋 뒤 대기 |
| `run_log.py` | run 기록 한 줄 JSON, 주문별 종료 상태 판정, run 경계(`RunBook`: drain·라우팅) |
| `trip_fsm.py` | 트립 상태·전이·guard·이벤트. ADR 0001 의 표 |
| `dispenser_inventory.py` | 슬롯 2개, FEFO, 임계값, 정지·재개, 보충 요청 목록, 보충 선반 |
| `pharmacy_db.py` | sqlite 약 DB. 시드 세 파일(`pharmacy_catalog.yaml`·`dispenser.yaml`·`order_pool.yaml`)이 약 마스터·약통(`cn-`)·모듈(`md-`)·봉투 표를 채운다. 스캔 기록 표는 약통 확인 서비스의 `check_container`가 채운다. 정상 epoch·형식 경로는 내부에서 `record_scan`을 부르고, `bad_format`·`stale_epoch`도 별도 기록한다. AMR 봉투·인식표 판독의 DB 저장과는 별개다. QR 조회와 장착 거부(만료·회수)를 한다. 기동은 모든 표(스캔 포함)를 비우고 시드로 채우고, `reseed`(리셋)는 스캔만 남기고 나머지를 시드로 되돌린다(봉투 상태 이력도 지운다). 이름은 [QR·DB·카메라 계약](../../docs/architecture/qr-db-camera-contract-v1.md) 2절. `pharmacy_db` 파라미터로 켠다(보충 전 약통 확인 서비스) |
| `refill_planner.py` | 보충 goal 을 언제·어느 슬롯으로 보내고 결과를 재고에 넣을지. 재시도·시한·리셋 |
| `status_view.py` | status_monitor 화면 조립. 받은 메시지 모으기(`StatusModel`)와 텍스트 한 장(`render`) |
| `wait_report.py` | 트립이 guard 로 멈춰 있을 때 5 s 마다 WARN, 풀리면 INFO 를 낼지 정한다 |
| `stat_cli.py`, `stat_dispatch.py`, `stat_intake.py`, `stat_ledger.py`, `stat_stub.py` | STAT S0 합성 입력·원장·작업 실행·stub 세계([STAT 계약](../../docs/architecture/stat-delivery-contract-v1.md), proposed). 한 바퀴 노드는 이 모듈을 쓰지 않는다. 재현은 [STAT S0 런북](../../docs/runbooks/stat-s0-stub.md) |

`ros_qos.py` 는 계약 2절의 QoS 약어(S·R·H·L)를 함수로 옮긴 것이고 `rclpy` 를 import 한다.

## 실행 상태와 JSON의 역할 (현재 구현)

| 대상 | 현재 역할 | 재시작 후 현재 상태 복원에 사용하나 |
| --- | --- | --- |
| `terminal_states.py` / `OrderStatus.msg` | 주문 종료 상태의 문자열 이름과 ROS 메시지의 숫자 코드를 정의한다. `terminal_states.py` 에는 `is_terminal()`·`trip_succeeded()` 보조 함수도 있다 | 아니요 |
| `trip_fsm.py` / `orchestrator_node.py` | AMR별 트립 상태(`IDLE`, `DISPATCHING`, `TRANSIT` 등), epoch, 진행 중인 명령·주문을 실행 중 메모리에서 관리하고 ROS 액션·토픽으로 진행한다 | 아니요 |
| `config/order_pool.yaml` / `config/dispenser.yaml` | 합성 주문 목록과 조제기 초기 재고·보충 선반을 입력한다. 종료 상태 코드나 실행 중 주문별 상태를 저장하지 않는다 | 아니요 |
| `config/pharmacy_catalog.yaml` | 약 DB 시드(약 마스터, 약통 `cn-` ID·입고일, 모듈 `md-`, 만료 기준일 `today`). 약통의 약품·유통기한·수량·위치는 `dispenser.yaml` 이 원본이고, 거기 있는 약통에는 회수 표시(`status: recalled`)만 더할 수 있다. `dispenser.yaml` 에 없는 약통만 `item_id`·`expiry`·`count`·`location`·`status` 를 적는다. 틀린 시드(형식·중복·빈 로트·모르는 약품·출처 약통과 약품 불일치 등)는 `CatalogError` 로 기동을 거부한다. 선반 약통은 16칸이다. ID 는 `cn-0101`–`cn-0116` 이다. 위치는 `shelf:<칸>` 이다. `floor_right/r0c1` 은 만료다 | 아니요 |
| `status_view.py` / `status_monitor` | 수신한 토픽으로 화면용 상태를 메모리에 모은다. 트립 단계는 이벤트로 추정하며 FSM 내부 상태를 읽지 않는다 | 아니요 |
| `event_logger` 의 run별 `*.jsonl`·`meta.json` | 받은 이벤트·주문 상태·보관함 관측, 주문별 평가 판정, run 요약을 남긴다. 사람이 실행을 확인하고 지표·증거를 검토할 때 쓴다 | 아니요 |
| Isaac ↔ ROS 어댑터의 JSON | `std_msgs/String` 토픽에 싣는 메시지 형식이다. 파일 저장 방식이 아니다 | 해당 없음 |
| `experiments/protocols/*.json` | 실행 전에 정한 실험 조건이다. 실행 중 로봇 상태가 아니다 | 해당 없음 |

run 파일의 `order_status.jsonl` 은 **주문 상태 메시지의 기록**이고, `orders.jsonl` 의 `SUCCESS` 는 `event_logger` 가 관측으로 판정한 **실험 결과**다. 어느 쪽도 지금 움직이는 로봇의 상태를 조회하는 저장소는 아니다. `Event.robot_id` 역시 이벤트가 가리키는 로봇 ID이지 DB의 로봇 행은 아니다. `terminal_states.py` 의 상수는 상태의 **가능한 이름**이고, 실제 주문별 상태는 실행 중 FSM·ROS 메시지와 run 기록에 나타난다. YAML 에 종료 상태값이 들어 있는 것은 아니다.

현재 `main` 에는 `robot_id` 별 최신 운영 상태(`IDLE`/`RUNNING` 등), 현재 작업명령 코드와 명령 이력을 영속적으로 저장·조회하는 DB가 없다. 그런 기능은 별도 요구사항과 계약으로 정의해야 한다. 그때도 현재 상태·명령 이력의 DB와 run별 검증 원본은 용도가 다르다. 이 절은 현행 구현의 경계를 설명하며 DB 방식이나 상태 코드 체계를 확정하지 않는다.

## order_generator

- 주문 풀은 `config/order_pool.yaml` 이다. 계약 7절이 정한 위치이고 봉투 QR 이미지도 이 파일로 만든다.
  **합성 데이터 전제다.** 환자 ID(`patient_id`)가 `/events`(`REQUEST_ACCEPTED` detail, #104)와 run 기록에 실린다.
  실환자 데이터를 쓰게 되면 `/events` 에 싣지 않는다.
- 한 주문이 요청 한 건이 되고 목적지는 그 주문의 침상이다. `mode: urgent` 인 주문은 큐 맨 앞으로 간다.
  긴급끼리는 FIFO 이고 진행 중인 트립은 건드리지 않는다.
- `request_id` 는 `r<epoch 3자리>-<seq 4자리>` 다. `epoch` 는 orchestrator 만 발급하므로
  발행기는 `/events` 를 구독해 따라 읽기만 하고, epoch 가 오르면 `seq` 를 1부터 다시 센다.
- goal 이 거부되면 다음 요청으로 넘어간다. 계약 2.5절대로 거부는 이벤트도 지표도 남기지 않는다.
- 리셋 뒤에는 새 epoch 의 `RESET_DONE` 을 본 뒤 `reset_settle_s`(기본 3.5 s wall, 계약 6절 5 의 3 s + 여유) 동안 보내지 않는다.
  epoch 만 오르고 `RESET_DONE` 을 아직 못 봤어도 보내지 않는다. barrier 동안 보내면 거부되고 버려져 긴급 요청까지 사라진다.
- `max_requests` 는 epoch 마다 센다. 결과까지 받은 요청만 세고, 그 요청을 보낸 epoch 가 지금 epoch 일 때만 센다.
  트립 도중 리셋하면 끊긴 요청의 abort 결과가 epoch 상승 뒤에 오는데, 그것은 새 epoch 의 수에 들어가지 않는다.
- 파라미터: `order_pool_file`(빈 값이면 share 의 `config/order_pool.yaml`), `max_requests`(`0` = 전부), `start_delay_s`(`3.0`, wall),
  `gap_s`(`1.0`, tick 주기. 0.1 보다 작으면 0.1), `reset_settle_s`(`3.5`, wall).

묶음 배송(병실·병동)은 주문 여러 개를 한 요청으로 묶어야 해서 이 파일만으로는 못 만든다. 아직 없다.

## event_logger

- run 하나가 디렉토리 하나다. `events.jsonl`, `order_status.jsonl`, `cabinet.jsonl` 은 받은 그대로,
  `orders.jsonl` 은 주문별 판정, `meta.json` 은 run 요약이다.
- **`SUCCESS` 는 `/evaluator/cabinet` 관측으로만 쓴다**(계약 8절). 오케스트레이터의 `DELIVERED` 는 주장이라
  관측이 없으면 `ABORT`(reason `eval_not_observed`)로 닫는다.
- `Event.epoch` 가 오르면 리셋이므로 새 run 을 연다(계약 6절). 이전 run 은 곧바로 닫지 않고 `run_drain_s`(기본 2.0 s wall) 동안 열어 둔다.
  `/events`·`/orders/status`·`/evaluator/cabinet` 은 다른 토픽이라 도착 순서가 정해지지 않기 때문이다(리셋으로 끊긴 주문의 `ABORT` 가 `RESET_BEGIN` 보다 늦게 올 수 있다).
  - 이벤트는 epoch 로 그 run 에 쓴다. 주문 상태는 그 `request_id` 를 아는 run 에 쓴다. `order_id` 만으로 묶지 않는다.
  - 보관함 관측은 새 run 이 자기 `RESET_DONE` 을 보기 전에는 새 run 판정에 쓰지 않는다. 이전 run 이 열려 있으면 그쪽에 쓰고,
    아니면 새 run `cabinet.jsonl` 에 `pre_reset: true` 로 남긴다. 관측은 그 run 에 상태가 있는 주문에만 쓴다(`used`).
    그래서 `orders.jsonl` 에 상태 없이 관측만 있는 행(`claim ""`)은 생기지 않는다.
  - 닫힌 run 은 고치지 않는다. drain 뒤에 온 이전 epoch 이벤트는 새 run 에 `stale: true`, 이전 요청의 상태는 `late: true` 로 남기고 판정에는 안 넣는다.
  - `meta.json` 의 `closed_by_reset_epoch` 는 그 run 을 끝낸 리셋의 epoch 다(종료 경로로 닫혔으면 `null`). `counts` 에 `late`·`pre_reset` 이 있다.
- 원본 로그는 저장소 밖에 쓴다. 기본 위치는 `$ROS_HOME/rokey_p3/runs` 이고 `log_dir` 로 바꾼다.
  run ID 의 host 칸은 `run_host`(빈 값이면 hostname)를 소문자·`[a-z0-9-]`·32자로 다듬은 값이다.
  [evidence](../../evidence/README.md) 의 증거 기록은 사람이 이 파일들을 보고 따로 만든다.
- `/evaluator/cabinet` 은 이 노드만 구독한다. 운영 노드(orchestrator·arm·fleet)는 구독하지 않는다(계약 2.1절).
- 종료: SIGINT·SIGTERM·SIGHUP(tmux 창 닫기) 어느 것으로 끝나도 열린 run 을 모두(drain 중인 이전 run 포함) 한 번 닫아 `orders.jsonl`·`meta.json` 을 남긴다. SIGKILL 은 못 막는다.
  `ros2 launch` 는 SIGTERM 을 받으면 자식에게 신호를 보내지 않고 끝나므로 SIGINT 로 내린다(docker 는 `STOPSIGNAL SIGINT` 또는 `docker kill -s INT`).
  SIGHUP 처리기는 Python 처리기라 spin 이 깨어나야 돈다. 받을 메시지가 없어도 돌도록 0.5 s steady clock 타이머로 spin 을 깨운다(`/clock` 이 멈춰도 돈다).
  같은 타이머가 `run_drain_s` 가 지난 이전 run 을 닫는다(메시지가 없어도 최대 0.5 s 늦게).

## status_monitor

시연·통합 때 마스터에서 흐름을 한 화면으로 본다(시나리오의 마스터 2 상태 GUI 자리). **구독만 한다.** 발행·서비스 호출·액션이 없고 판정에 쓰지 않는다.

```bash
ros2 run rokey_p3_orchestrator status_monitor                    # 1 Hz 로 화면을 지우고 다시 그린다
ros2 run rokey_p3_orchestrator status_monitor --no-clear         # 지우지 않고 이어 쓴다(tmux 로그)
ros2 run rokey_p3_orchestrator status_monitor --once             # 2 s wall 동안 모은 뒤 한 번 찍고 끝낸다
ros2 run rokey_p3_orchestrator status_monitor --robot-id amr_2   # AMR 네임스페이스(기본 amr_1)
```

- 머리줄: epoch(받은 이벤트 중 최대), `/clock` 의 sim time 과 신선도(2.0 s wall 넘으면 `STOPPED`), 트립 단계.
  트립 단계는 최근 트립 이벤트 이름으로 **추정**한 것이다(FSM 상태를 읽지 않는다). 조제기·M0609 이벤트는 단계를 바꾸지 않는다.
- 주문: `/orders/status` 의 최근 8행(request_id·order_id·상태·reason). 이전 epoch 요청은 `*` 로 표시한다.
- 조제기: `/pharmacy/dispenser/status` 의 약품별 슬롯 A/B(lot·수량, `*` 는 활성), 멈춘 약품 `PAUSED`, 대기열.
- 인터락 신호: `/<robot>/arm/at_home`, `/<robot>/base/stopped`, `/<robot>/gripper/holding`, `/pharmacy/belt`, `/m0609/arm/at_home`.
  값과 받은 지 몇 초인지. 1.0 s wall 을 넘으면 `unknown`(계약 4절).
- 최근 이벤트 12줄(stamp·robot_id·name·order_id·detail). `RESET_BEGIN`·`RESET_DONE` 은 구분선으로 그린다.
  도착 순서가 아니라 epoch → 구분선(`RESET_BEGIN`, `RESET_DONE`) → stamp 순이고 같은 stamp 는 도착 순이다. `/events` 는 latched 라 늦게 붙으면 이력이 작성자 단위로 뭉쳐 온다.
  트립 단계도 이 순서로 가장 늦은 트립 이벤트로 정한다.
- `/evaluator/cabinet` 은 평가 전용 경로라 기본으로 구독하지 않는다(계약 2.1절). `--with-evaluator` 면 주문 행에 관측한 보관함을 붙인다.
- 그리기는 ANSI 지우기와 다시 쓰기다(의존성 없음). 폭은 고정폭 글꼴·한 글자 한 칸으로 가정한다. 그리기 타이머는 steady clock 이라 `/clock` 이 멈춰도 화면은 갱신된다.
- Ctrl-C(SIGINT)로 끝낸다.

### `status_view` 를 코드에서 쓰기 (공개 API)

터미널 `status_monitor`는 `status_view.StatusModel`을 쓴다. 관제 웹 백엔드는 자체 `WorldState`를 쓰고 `status_view`의 공통 상수·함수를 가져온다. **아래 이름과 dict 키는 공개 API 로 취급한다.** 바꾸면 백엔드와 같은 PR 에서 고친다.
ROS 를 import 하지 않는다. 시각 인자 `wall` 은 수신 쪽 monotonic 초(`time.monotonic()`), `stamp` 는 메시지 `header.stamp` 의 sim 초(float)다.

| 메서드 | 인자 | dict 키(값) | 비고 |
| --- | --- | --- | --- |
| `StatusModel(max_events=12, event_buffer=500)` | - | - | 화면 이벤트 수, 보관 이벤트 수 |
| `note_clock(sim_s, wall)` | `/clock` 의 sim 초 | - | `/clock` 신선도 2.0 s |
| `note_event(event)` | `/events` 한 건 | `stamp`(float), `epoch`(int), `name`(str), `request_id`(str), `order_id`(str), `robot_id`(str), `detail`(str) | `epoch`·`name`·`stamp` 는 필수, 나머지는 없으면 빈 값으로 본다. 순서는 도착이 아니라 `event_key` 다 |
| `note_order(status)` | `/orders/status` 한 건 | `request_id`, `order_id`, `state`(이름. `run_log.state_name(msg.state)`: `ACCEPTED`·`IN_PROGRESS`·`DELIVERED`·`HOLD_RETURN`·`ABORT`·`TIMEOUT`), `reason` | `request_id`·`order_id`·`state` 필수, `reason` 은 없으면 빈 값. 같은 (request_id, order_id) 는 덮는다. 처음 본 request_id 의 epoch 를 붙인다 |
| `note_dispenser(status, wall)` | `/pharmacy/dispenser/status` | `slots`(목록: `item_id`, `slot`(0=A, 1=B), `lot_id`, `count`(int), `active`(bool)), `paused_item_ids`(str 목록), `queue_length`(int), `belt_occupied`(bool) | 슬롯의 `item_id`·`slot` 필수, 나머지는 없으면 빈 값·0·false. 최신 한 건만 둔다 |
| `note_signal(key, value, wall)` | 인터락 신호 | `key` 는 `arm_at_home`·`base_stopped`·`gripper_holding`·`m0609_at_home`(값 bool) 또는 `belt`(값 dict: `occupied`, `at_end`(bool), `order_id`(str)) | 신선도 1.0 s 넘으면 unknown |
| `note_cabinet(order_id, cabinet_id, present)` | `/evaluator/cabinet`(평가 전용) | - | `present=true` 만 남긴다. 운영 화면에서는 쓰지 않는다(계약 2.1절) |

읽는 쪽:

- `render(model, now_wall, options=None)` → 화면 줄 목록. `options` 는 `{'with_evaluator': bool}`.
- `model.recent_events()` → 순서 키 순 최근 `max_events` 건(dict, 도착 순번 `seq` 가 붙어 있다).
- `event_key(event)` → `(epoch, 구분, stamp, seq)`. 구분은 `RESET_BEGIN` 0, `RESET_DONE` 1, 나머지 2.
- 속성: `epoch`(받은 최대), `clock`(`(sim_s, wall)` 또는 None), `trip_event`(추정 단계의 근거 이벤트 이름), `orders`(`(request_id, order_id)` → 행 dict + `epoch`), `dispenser`(`(dict, wall)` 또는 None), `signals`(키 → `(값, wall)`), `observed`(order_id → cabinet_id).
- 상수: `TRIP_PHASES`(이벤트 이름 → 단계 문구), `SIGNALS`(신호 키·이름표 순서), `SIGNAL_FRESH_S`(1.0), `CLOCK_FRESH_S`(2.0).

## 보충 클라이언트 (orchestrator 노드 안)

조제기 보충을 M0609 에 시킨다. 판단은 `refill_planner.py`, 배선은 `orchestrator_node.py` 다.
트립 FSM 밖에 있어서 **트립 중에도 보충한다.**

- 재고의 보충 요청(`REFILL_REQUESTED` 를 낸 약품, 파일에서 0/0 으로 시작한 약품)을 요청 순서대로 `/m0609/refill` 에 보낸다.
  이벤트가 아니라 재고 상태를 읽으므로 실패 뒤에도 요청이 남아 있다. goal 은 한 번에 하나다.
- 슬롯: 그 약품의 빈 슬롯 중 A 먼저. 비지 않은 슬롯에는 보내지 않는다(보충은 추가이지 교체가 아니다).
  빈 슬롯이 없으면 기다린다. 둘 다 비었으면 A 만 채우고 B 는 다음 요청 때 채운다.
- 성공하면 장착한 캐니스터를 재고에 넣는다. 멈춰 있던 약품이면 `DISPENSER_RESUMED` 를 낸다.
  `REFILL_DONE` 은 m0609/arm 이 낸다(계약 2.6절).
- 실패(거부·서버 없음·`success=false`·90 s sim 시한 초과)는 재고를 건드리지 않는다. `refill_retry_delay_s`(5.0) 뒤 다시,
  `refill_max_attempts`(3) 번째 실패면 경고를 남기고 리셋 전까지 그 약품을 보충하지 않는다.
  시한 초과로 cancel 한 goal 은 종결이 오거나 `cancel_wait_s`(10 s wall)가 지나야 다시 보낸다. 그 사이 온 늦은 결과는 token 이 달라 재고·선반을 바꾸지 않는다.
- 리셋 barrier 에 들어가면 시도 횟수·포기 표시를 비우고 barrier 동안 새 `Refill` goal 을 내지 않는다. 활성 `Refill` 은 drain 에서 cancel 된다.
  재고·선반은 `/sim/reset` 이 ok 한 뒤 파일 값으로 돌아간다(아래 리셋 절 3). 이전 epoch 결과는 버린다.
- 캐니스터의 로트·유통기한·수량 출처는 orchestrator 데이터다(계약 2.1절 끝). `config/dispenser.yaml` 최상위 `shelf:` 에
  약품별 캐니스터를 꺼내는 순서대로 적는다. 보낼 때 맨 앞을 보고(peek), 성공했을 때만 뺀다(pop). 선반이 비면 보내지 않고 경고를 한 번 남긴다.
  리셋하면 파일을 다시 읽어 선반도 돌아간다. arm 결과의 `lot_id` 는 기록용이다. 성공 로그에만 남기고, 달라도 재고는 선반 값이다.
  m0609_arm 은 lot 을 지어내지 않아 빈 값을 낸다(#99). 그러면 로그는 `arm lot_id=-` 이고 "다르다" 경고가 나오지 않는다.
- 로트 출처는 A 안(선반 데이터)이다. B 안(`Refill.action` 에 로트 필드)은 들어가지 않았다. v1.1.0 `Refill.action` 의 goal 은 `item_id`·`slot` 뿐이다.

## orchestrator

- 입력(액션 결과, 상태 토픽, 태그, tick, 리셋)을 `trip_fsm.py` 에 넣고 돌려받은 명령을 ROS 로 옮긴다.
  이 노드에는 판단이 없다.
- **인터락 사전 확인**은 FSM 의 guard 다. 실행하는 쪽(fleet, arm)도 같은 조건을 본다(계약 5절, 이중).
  조건이 unknown 이면 기다린다. 타임아웃은 진입 허가가 아니다.
- **기다리는 이유를 로그로 남긴다.** 트립이 guard 로 멈춰 있으면 5 s(wall)마다 WARN 한 줄, 풀리면(WARN 을 냈을 때만) INFO 한 줄이다.
  예: `r001-0001: 배출 대기 10 s: /pharmacy/belt unknown(1.0 s 넘게 소식 없음. 발행하는 노드·Isaac 이 떠 있는지 확인)`, `… 배출 대기 끝. 40 s 기다렸다.`
  대상은 출발(적재 위치로·병동으로)·복귀의 `arm/at_home`, 배출의 벨트 unknown·봉투 있음·재시도, 벨트 픽·스캔·배달의 `base/stopped`, cancel 종결 대기다.
  판정은 바꾸지 않고(`TripFsm.wait_reason()` 은 읽기만) 이벤트도 내지 않는다. 관제 웹은 `/rosout` WARN 을 로그 탭에 보여 준다.
- 액션 서버·서비스가 아직 안 보이는 것도 unknown 이다. 거부로 세지 않고 `server_wait_s`(기본 10.0, wall) 까지 기다렸다 보낸다.
  `/sim/reset` 은 예외로 `reset_timeout_s`(30 s) 전체를 서버 탐색에 쓴다.
  넘으면 그때 거부로 넣는다(`Dispense` 는 `no_server` 거부, `/sim/reset` 은 리셋 실패). 기다리는 동안 epoch 가 바뀌거나 FSM 이 cancel 하면 보내지 않는다.
- goal·서비스 호출마다 token(epoch, owner `trip`·`refill`, 순번)을 붙인다. 결과·피드백은 그 token 으로 FSM·보충 클라이언트에 들어가고,
  지금 기다리는 token 이 아니면 버린다. 같은 epoch 안에서도 이전 goal 의 늦은 결과가 새 goal·재고·선반을 바꾸지 못한다.
  수락 전에 cancel 하면 수락되자마자 cancel 하고 결과(종결)까지 본다. 결과는 액션 status(CANCELED·ABORTED)를 먼저 본다.
- 액션 시한·트립 제한으로 goal 을 cancel 하면 그 goal 이 종결될 때까지(최대 `cancel_wait_s` 10 s wall) 대체 goal 을 보내지 않는다.
- `Deliver` 수락 조건은 계약 2.5절 그대로다. `request_id` 새 것, `orders` 비지 않음,
  `destination_id` 가 구역 ID, 모든 `order_id` 가 풀에 있고 미사용, 진행 중 트립 없음.
  거부는 goal 거부로 끝나고 이벤트도 지표 분모도 남기지 않는다.
  사유는 goal 거부에 실을 자리가 없어(계약 `Deliver` 결과에 message 가 없다) 로그(`/rosout`) WARN 한 줄로만 남는다(#201):
  `Deliver goal 거부 <request_id>: <사유>`. FSM 쪽 사유는 `TripFsm.refusal()` 이 만든다(`accepts()` 는 그 None 여부, 판정은 같다).

  | 경우 | 사유 |
  | --- | --- |
  | 트립 진행 중 | `진행 중 트립이 있다(상태 <state>, 트립 <request_id>)` |
  | 정거장 실패 | `정거장을 만들 수 없다: ` 뒤에 `batch_ward 인데 destination_id 가 없다` / `single 는 주문이 1개여야 한다(3개)` / `<order_id> 의 환자 '<patient_id>' 침상을 모르고 destination_id 도 없다` / `batch_room 인데 침상을 모르는 주문이 있다: [...]` |
  | 노드 선검사 | 리셋 barrier 중, `orders 가 비었다`, `<request_id> 는 이미 받은 ID 다`, `<destination_id> 는 구역 ID 가 아니다`, `<order_id> 가 주문 풀에 없다`, `<order_id> 는 이미 쓴 주문이다` |

  실습8 의 묶음 409 두 번은 주문 3개를 `"mode":0`(single)으로 보낸 것이었다. #201 뒤에는 위 표의 `single 는 주문이 1개여야 한다(3개)` 가 찍힌다.
- **`epoch` 는 이 노드만 발급한다**(계약 4절). 이전 epoch 의 액션 결과는 버린다.
- 포기해서 남은 주문을 닫을 때 `HOLD_RETURN` 은 상판에 실은(`LOADED`) 주문만이다. 아직 안 실은 주문은 같은 reason 으로 `ABORT` 다.
  이 트립에서 이미 끝난 주문의 봉투가 벨트에 남아 있으면 벨트 막힘으로 보고 남은 미배출 주문을 `ABORT`(`belt_blocked`)로 닫는다.
- 조제기 이벤트(`DISPENSER_PAUSED`, `DISPENSER_RESUMED`, `REFILL_REQUESTED`)의 `robot_id` 는 `dispenser` 다.
- `REQUEST_ACCEPTED` 의 `detail` 은 요청 요약 한 줄 JSON 이다: `{"mode":1,"destination_id":"bed_a1","orders":[{"order_id":…,"patient_id":…,"item_id":…}]}`.
  키 순서 고정·공백 없음·한글 그대로이고 `mode` 는 `DeliveryRequest` 상수 값(0 1인, 1 긴급, 2 병실 묶음, 3 병동 묶음)이다. 관제 화면 표시용이다.
  계약대로 판정·지표에는 쓰지 않는다. `event_logger` 는 받은 그대로 적기만 하고 `run_log`·`tools/aggregate_runs.py` 는 detail 을 읽지 않는다.
- 리셋 barrier 는 `ros2 service call /orchestrator/reset rokey_p3_interfaces/srv/Reset` 로 들어간다. 응답은 곧바로 ok 다(barrier 완료가 아니다).
  새 epoch 는 항상 지금 epoch + 1 이다(계약 4절). 요청의 `epoch` 는 쓰지 않고, 응답 `message` 에 실제 epoch 가 있다.
  번호는 계약 6절과 같다.
  0. Deliver 를 거부하기 시작하고 새 보충 goal 을 내지 않는다. 끊긴 주문을 이전 epoch·이전 request_id·같은 stamp 로 `ABORT`(`reset_interrupted`)·`ORDER_DONE`.
     이미 종료 상태인 주문은 덮지 않는다. Deliver 결과는 aborted 한 번. 그다음 epoch +1, `RESET_BEGIN`(새 epoch). 팔 노드는 여기서 명령을 멈춘다.
  1. drain: 활성 goal(트립·보충) 전부 cancel, 종결을 `cancel_wait_s`(wall) 까지 기다린다. 넘으면 경고를 남기고 진행하며 `RESET_DONE.detail` 이 `drain_timeout`.
     그래도 종결이 안 온 goal 은 goal 표에서 뺀다(다음 리셋이 또 기다리지 않게). 뒤늦게 수락되면 곧바로 cancel 한다.
  2. `/sim/reset(새 epoch)`. 응답 상한은 `reset_timeout_s`(wall, 서버 탐색 포함).
  3. ok 한 뒤에만 재고·선반·요청/주문 사용 표를 파일 값으로 되돌리고 `RESET_DONE`(새 epoch).
  4. fleet·arm 쪽 처리(계약 6절 4). 이 노드는 하는 일이 없다.
  5. `RESET_DONE` 뒤 3 s wall 지나야 요청을 받는다.
  - false·예외·시한 초과면 **리셋 실패로 멈춘다.** Deliver 거부, `RESET_DONE` 없음, 재고 안 되돌림, 자동 재시도 없음, ERROR 로그 한 번과 그 뒤 10 s 마다. 새 `/orchestrator/reset` 이 새 epoch 로 0 부터 다시 시작한다.
  - 1-2(drain·`/sim/reset` 응답 대기) 중에 온 리셋 요청은 합류한다(epoch·상한 그대로, 응답 ok). 상한은 wall 이라 sim 이 멈춰도 돈다.
- 복귀(도크) goal 이 거부되면 5 s 뒤 1회 더 보낸다(계약 5절). 끝내 거부·미도착이면 `DOCKED` 없이 Deliver `success=false` 다.
- **종료는 리셋이 아니다.** 트립 도중 노드를 내리면(SIGINT·`destroy_node`·rclpy 종료) `Deliver` 실행은 0.2 s 안에 기다림을 풀고 goal 을 abort 한다.
  주문 상태·이벤트는 새로 내지 않고, 결과의 `orders` 는 마지막으로 발행한 상태 그대로다. 사유(shutdown)는 결과에 칸이 없어 로그에만 남긴다.
- **`SUCCESS` 를 내지 않는다.** 주장은 `DELIVERED` 까지이고 판정은 `event_logger` 가 한다(계약 8절).
- 재고는 `config/dispenser.yaml` 이다. 리셋하면 이 파일의 값으로 되돌린다.

| 파라미터 | 기본값 | 뜻 |
| --- | --- | --- |
| `robot_id` | `amr_1` | 액션·상태 토픽의 네임스페이스 |
| `order_pool_file` | 빈 값 | 비우면 share 의 `config/order_pool.yaml` |
| `pharmacy_db` | `false` | 켜면 약 DB 를 연다. `/orchestrator/check_container`(`CheckContainer`)를 낸다. 시드가 틀리면 기동을 거부한다. 재고 파일(`dispenser_file`)과 카탈로그의 로트가 어긋나면 거부하지 않고 경고한다(계약 2.1) |
| `pharmacy_catalog_file` | 빈 값 | 비우면 share 의 `config/pharmacy_catalog.yaml` |
| `pharmacy_db_path` | 빈 값 | sqlite 파일. 비우면 메모리 |
| `pharmacy_today` | 빈 값 | 만료 기준일. 비우면 카탈로그의 `today` |
| `dispenser_file` | 빈 값 | 비우면 share 의 `config/dispenser.yaml` |
| `zones_file` | 빈 값 | 구역 파일. 병실 테이블(kind station + room)이 있으면 병실 묶음을 그 테이블 한 곳에 놓는다(재범 9/25). `load` 와 `dock_zone` 이 같은 자세면 도크에서 이동 없이 적재한다(`load_at_dock`, #790). 비우면 예전 동작 |
| `load_zone` | `load` | 적재 위치 zone |
| `dock_zone` | `dock_1` | 복귀할 도크 zone |
| `arriving_distance_m` | `3.0` | 긴급 `ARRIVING` 을 내는 남은 거리 |
| `trip_limit_s` | `600.0` | 트립 제한 시간(sim). 넘으면 남은 주문 `TIMEOUT` |
| `pharmacy_only` | `false` | true 면 조제실 구간만 돈다. 아래 절 |
| `server_wait_s` | `10.0` | 액션 서버·서비스가 안 보일 때 거부로 보기 전에 기다리는 시간(wall). 넘으면 거부. `/sim/reset` 은 `reset_timeout_s` |
| `cancel_wait_s` | `10.0` | cancel 한 goal 의 종결을 기다리는 상한(wall). 대체 goal·보충 재시도·리셋 drain 이 같이 쓴다 |
| `reset_timeout_s` | `30.0` | `/sim/reset` 응답 상한(wall, 서버 탐색 포함). 넘으면 리셋 실패로 멈춘다 |
| `observation_guard` | `false` | **시험용.** 계약 11.3·11.6 관측 guard. 켜면 `/pharmacy/belt/observation`·`<robot>/arm/clear_of_belt` 를 구독한다. 피킹은 종단 정착(END·STOPPED·STOP, 이 주문)일 때만, 다음 배출은 빈 벨트(EMPTY)·팔 통로 CLEAR·앞 벨트 픽 ok 일 때만 한다. 관측은 seq 가 앞으로 갔을 때만 신선하고, 없거나 다른 epoch 면 허가하지 않는다. `ArmClearance` 의 CLEAR 는 L3 FK↔TCP 대조 전에는 믿지 않는다 |
| `deck_slots` | `5` | AMR 상판에 실을 수 있는 봉투 수. 자리가 없으면 그 주문은 `deck_full` 로 닫는다. 통짜 트레이는 3(시뮬 #445) |
| `belt_timeout_s` | `20.0` | 조제 뒤 봉투가 벨트 끝에 닿기를 기다리는 시한(sim s). 병원 컨베이어는 약 35 s 라 `demo_v2.sh` 가 60 을 준다 |
| `dispense_while_dispatching` | `false` | 적재 자리로 가는 동안 첫 봉투 조제를 시작한다. 이동과 조제가 모두 끝난 뒤 적재한다. v1.1.0 병원 카메라 기본은 `true` |
| `refill_retry_delay_s` | `5.0` | 보충 실패 뒤 다시 보내기까지(sim) |
| `refill_max_attempts` | `3` | 이 횟수만큼 실패하면 리셋 전까지 그 약품을 보충하지 않는다 |

### 조제실 구간만 (`pharmacy_only`)

일정 P2 의 1차 시연 범위(요청 → 배출 → 픽 → 적재 → 충전 도크 복귀 → 리셋)를 같은 FSM 으로 돈다.

- 적재가 끝나 `LOAD_DONE` 을 낸 뒤 정거장으로 가지 않는다. 실은 주문을 `HOLD_RETURN`(reason `pharmacy_only`)으로 닫고
  `dock_zone` 으로 복귀한다. 벨트 막힘으로 적재를 끝낸 경우도 같은 분기다.
- 한 바퀴의 이벤트: `REQUEST_ACCEPTED → AMR_DOCKED_LOAD → DISPENSED → POUCH_AT_END → PICK_ATTEMPT → POUCH_PICKED
  → POUCH_LOADED → LOAD_DONE → ORDER_DONE → ARM_HOME → RETURNED → DOCKED`.
- `Deliver` 결과는 `success=false` 다. **1차 시연은 `HOLD_RETURN` 이 정상 종료다.** 봉투가 상판에 남은 채 복귀한 것이 사실이다.
- `HOLD_RETURN` 을 쓰는 이유: ADR 0001 주문 상태 절의 정의 "봉투가 상판 칸에 남아 있는 경우"와 물리가 같다.
  종료 상태를 새로 만들면 시나리오 5절·`run_log`·evidence 스키마가 다 바뀐다.

## 테스트

```bash
colcon test --packages-select rokey_p3_orchestrator
```

`test_trip_fsm.py` 는 ADR 0001 이 요구하는 "입력 순서 → 명령 순서" 표다.
`test_lap_order.py` 는 스텁의 규칙을 옮긴 가짜로 계약 2.6절의 스물한 줄을 ROS 없이 확인한다.
`pharmacy_only` 한 바퀴의 열두 줄도 같은 가짜로 본다.
진짜 L2 는 [rokey_p3_bringup](../rokey_p3_bringup/README.md) 에 있다.
