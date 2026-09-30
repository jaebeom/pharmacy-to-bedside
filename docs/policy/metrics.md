# 측정과 합격 판정

측정값과 해석을 나눈다. 합격 기준도 따로 둔다.
이 문서가 정책이다. 실험마다의 정의·분모·seed·반복·timeout·threshold는
[protocol](../../experiments/README.md)에 둔다. 실측 숫자를 이 문서에 계속 추가하지 않는다.

## Pilot와 acceptance

[용어](../README.md#용어)의 **pilot**(탐색 실행)과 **acceptance**(최종 평가)다.

1. 측정하려는 정의·분모·실패/누락 처리·시계·seed·반복 계획을 먼저 정한다.
2. proposed protocol을 검토해 frozen pilot protocol로 저장한다. 이 버전으로 pilot을 실행한다.
3. pilot으로 측정기·리셋·자원과 목표의 타당성을 확인한다.
4. 별도 acceptance protocol에 목표·반복·seed·제외 정책을 고정한다. 사람의 승인 PR을 기록한다.
5. **frozen protocol이 기준 브랜치에 반영된 뒤** 별도 acceptance run을 시작한다.
   기준과 결과를 같은 PR에서 사후 작성하지 않는다. 사후 작성한 것을 사전 정의라고 주장하지 않는다.

실행된 frozen protocol은 변경하지 않는다. 새 버전을 만들고 다시 검토한다.
성능·정확도 목표는 미정일 수 있다. 미정 상태에서 acceptance 합격을 주장하지 않는다.
교착·오배송·충돌 관련 금지 조건은 측정 결과를 보고 완화하지 않는다.
이 프로젝트는 교육용 시뮬레이션이다. 임상·실장비 안전성을 입증하지 않는다.

## 지금 기준 protocol

기준: main `f316197`(v1.1.0). 목록은 `experiments/protocols/` 다.

- 병원 전 구간 acceptance 는 [hospital-full-acceptance-v4](../../experiments/protocols/hospital-full-acceptance-v4.json)다. frozen 이다(#773, 2026-09-27).
  - purpose 7(a) 는 「한 회전 16 attempt 중 attempt_success==1 인 attempt 가 15 개 이상(전체의 90% 이상)이면 PASS 다」라고 쓴다(v4 protocol 문장 그대로, 승인 아님).
  - purpose 7(b) 는 실패마다 `failure_class`(robot·infra·operator)·`failure_cause`·`failure_evidence`·`retry_run_id` 를 남기라고 쓴다. protocol 이 인용한 출처는 재범 결정 2026-09-27(#240 댓글 5854486187)이다.
  - 도구가 요구하는 것은 둘이다. `tools/evidence.py` 는 `requires_failure_classification` 인 protocol 의 실패 run 에 `failure_class`·`failure_cause` 가 없으면 거부한다(215–218행).
  - `failure_evidence`·`retry_run_id` 는 실패 run 에서 선택이다. 네 필드 중 하나라도 성공 run 에 있으면 거부한다(219–222행).
- 마지막 판정 회전은 v1.0.0 의 회전 7 이다(코드 `9760d9d`). v1.0.0 릴리스 본문의 "회전 7" 표:
  - master01 attempt 1–11, 14–16: 14/14 통과(#777 #778).
  - attempt 12·13: 미실행. master02 에서 돌리지 않았다.
  - 판정 표는 #771 댓글 5867873681 이다.
- `evidence/runs/` 에 v4 로 기록된 run 은 17건이다(`9760d9d`). 회전 7 성공 14건, 회전 6 의 operator 중단 3건이다.
- v1.1.0(`f316197`) 커밋으로 돌린 acceptance 회전은 없다(v1.1.0 릴리스 본문).
- v4 purpose 1 은 카메라로 봉투를 집는 구성(`P3_CAMERA_POUCHES=1`)을 protocol 밖에 둔다. v1.1.0 의 병원 기본은 `P3_CAMERA_POUCHES=1` 이다(`tools/demo_v2.sh` 126행).
- 그 밖의 protocol:
  - [pharmacy-lap-pilot-v1](../../experiments/protocols/pharmacy-lap-pilot-v1.json)은 frozen pilot 이다(아래 절).
  - [hospital-refill-integration-pilot-v1](../../experiments/protocols/hospital-refill-integration-pilot-v1.json)은 frozen pilot 이다. run 1건이 있다.
  - hospital-full-acceptance-v1·v2·v3 은 frozen 이다. v1·v2 의 판정선은 한 회전 16/16 이다(v1 purpose 7, v4 purpose 0).
  - v4 purpose 0 은 v4 가 v3 의 purpose 문장 다섯 곳만 고친 판이라고 쓴다. 판정선·지표·attempt 구조는 v3 와 같다고 쓴다. v3 를 인용한 run 은 없다.
  - 같은 purpose 0 은 §8 이 v2 와 문자 그대로 같다고도 쓴다. v4 §8 은 판정선(성공 ≥15)을 적는다. v2 §8 에는 그 문장이 없다. 두 서술은 같이 참일 수 없다. frozen 이라 고치지 않는다. 정정은 새 protocol 이다.
  - [ward-lap-b-acceptance-v1](../../experiments/protocols/ward-lap-b-acceptance-v1.json)은 proposed 다. run 이 없다.

## 지표 정의 초안
아래는 정의 제안이다. 수집기가 구현되었다는 뜻이 아니다.
기획·계약 확정 후 실제 이벤트 이름을 protocol에 연결한다.
지금 계산 규칙이 있는 것은 protocol 별이다. 조제실 pilot 은 `tools/aggregate_runs.py`, 병원 전 구간 v1·v2·v4 는 `tools/hospital_full_metrics.py` 다(v1.1.0).

| 지표 | 정의·분모 | 같이 기록할 것 |
| --- | --- | --- |
| cycle_success | 정해진 품목 전체가 목적지에 정확히 인도된 배치 / 시작한 배치 | 부족·오배송·abort·timeout을 성공에서 제외 |
| cycle_time_s | 주문 수락부터 두 목적지 인도 확인까지 | 성공 완료 분포와 모든 실패·timeout을 별도 표시 |
| inspection | 독립 정답과 검사 결과의 confusion matrix | false accept·false reject·unknown, 클래스별 분모 |
| grasp_success | 정의된 안정 안착 / 모든 pick 시도 | 최초 시도 성공과 retry 후 성공을 분리 |
| docking | 목표 pose 대비 x/y 및 yaw 오차 | frame·rad/m·측정 시점, 실패 도킹도 기록 |
| waiting/deadlock | 정의된 교차로 대기·교착 이벤트 | 양쪽 도착·소유권·lease·heartbeat 타임라인 |

AprilTag/YOLO의 출력을 독립 정답으로 다시 쓰지 않는다.
시뮬레이터의 객체 ID/위치 ground truth 또는 독립 검토로 정답을 만든다.
인지용 정답 신호가 운영 제어로 새어 들어가 성능을 부풀리지 않게 경로를 분리한다.

### 조제실 구간 (pharmacy-lap-pilot-v1)

[pharmacy-lap-pilot-v1](../../experiments/protocols/pharmacy-lap-pilot-v1.json) 은 **frozen** pilot 이다(`frozen_at` 2026-09-19T17:44:12Z, #301).
정의·분모·성공 정의·outcome 규칙의 원문은 그 파일이다. 이 표는 각 지표가 어느 이벤트에서 오는지만 보인다.
이 절에 숫자와 합격선을 쓰지 않는다. pilot 이라 threshold 도 없다.
실행 기록은 `evidence/runs/` 에 6건 있다. master01 에서 9/19 `2c68b73` 로 3건, 9/20 `45d7fe3` 로 3건이다. 숫자는 그 run 기록을 본다.

| 지표 | 시작 이벤트 | 종료 이벤트 | 분모 | 수집 상태 |
| --- | --- | --- | --- | --- |
| `lap_s` | `REQUEST_ACCEPTED` (orchestrator) | `DOCKED` (orchestrator) | 시작한 트립 하나 | 원본 있음 |
| `load_s` | `REQUEST_ACCEPTED` (orchestrator) | `LOAD_DONE` (orchestrator) | 시작한 트립 하나 | 원본 있음 |
| `dispense_to_end_s` | `DISPENSED` (isaac) | 같은 `order_id` 의 `POUCH_AT_END` (isaac) | `DISPENSED` 가 나온 주문 하나 | 원본 있음. Isaac 스테이지와 `stub_sim` 이 낸다 |
| `return_s` | `RETURNED` (orchestrator) | `DOCKED` (orchestrator) | `RETURNED` 가 나온 트립 하나 | 원본 있음 |
| `refill_s` | `REFILL_REQUESTED` (orchestrator 재고 모듈) | `REFILL_DONE` (m0609/arm) | 그 epoch 의 보충 요청 하나 | 기본 재고 설정에서는 누락, 아래 |
| `pick_attempts` | `PICK_ATTEMPT` 의 개수 (arm) | 없음 | 시작한 트립 하나 | 원본 있음 |
| `lap_success` | `REQUEST_ACCEPTED` | `DOCKED`, 주문마다 `ORDER_DONE` 과 `HOLD_RETURN`(reason `pharmacy_only`) | 시작한 트립 | 원본 있음 |

위 초안 표와의 관계:

- `lap_success` 는 `cycle_success` 의 조제실 구간 판이고, `lap_s` 는 `cycle_time_s` 의 조제실 구간 판이다. 목적지 인도가 없으므로 성공 정의가 다르다.
- `pick_attempts` 는 `grasp_success` 의 분모 쪽만 센다.
- inspection, docking, waiting/deadlock 은 이 protocol 에 없다.

수집 상태의 근거. 기준: main `f316197`(v1.1.0). `event_logger_node.py`·`run_log.py`(`src/rokey_p3_orchestrator/rokey_p3_orchestrator/`)와 `tools/aggregate_runs.py` 를 읽고 적었다.
위 표의 일곱 지표는 모두 [`tools/aggregate_runs.py`](../../tools/README.md)가 계산한다.

- `event_logger` 는 epoch 마다 run 디렉토리 하나를 연다. 그 안에 다섯 파일을 쓴다(`run_log.py` `RUN_FILES`, `RunRecord.close`).
  - `events.jsonl`: stamp·epoch·name·request_id·order_id·robot_id·detail, 그리고 `stale` 표시
  - `order_status.jsonl`: 주문 상태, 그리고 `late` 표시
  - `cabinet.jsonl`: 보관함 관측, 그리고 `pre_reset`·`used` 표시
  - `orders.jsonl`: 주문별 판정과 reason. run 을 닫을 때 쓴다
  - `meta.json`: run_id·host·epoch·시작·끝·건수. run 을 닫을 때 쓴다
- epoch 가 오르면 새 run 을 연다. 이전 run 은 `run_drain_s`(기본 2.0 s wall) 동안 늦은 메시지를 받는다.
- `tools/aggregate_runs.py` 는 run 디렉토리 하나를 읽어 지표를 낸다. manifest 는 쓰지 않는다. 사람이 그 출력을 보고 `evidence/runs/` 기록을 따로 만든다.
  - epoch 1 은 시행에서 뺀다(protocol purpose 2). 원본은 남긴다.
- arm 과 isaac 이 내는 이벤트에는 `request_id` 가 없다. 그래서 트립은 epoch 로 묶는다.
- `DISPENSED`·`POUCH_AT_END` 는 Isaac 스테이지(`sim/standalone/p3sim/belt.py`)가 `/isaac/events` 로 낸다. `rokey_p3_bringup` 의 `isaac_adapter` 가 `/events` 로 옮긴다. `stub_sim` 도 낸다.
- `HOLD_RETURN`(reason `pharmacy_only`)은 orchestrator 파라미터 `pharmacy_only`(기본 false)를 켤 때 나온다(#57).
- `refill_s` 는 기본 재고 설정에서는 누락이다.
  - `REFILL_REQUESTED` 는 남은 봉투가 `refill_threshold` 이하일 때 나온다.
  - 리셋마다 재고가 [설정 파일](../../src/rokey_p3_orchestrator/config/dispenser.yaml) 값으로 돌아간다. 한 시행은 주문 1건이다. 그래서 기본 값(슬롯마다 5)으로는 그 조건이 오지 않는다.
  - `/m0609/refill` goal 은 orchestrator 의 보충 클라이언트가 보낸다(#58, `orchestrator_node.py`).
- 보충을 관측하려면 run 의 dispenser 설정으로 `REFILL_REQUESTED` 를 유도한다. 예: 활성 슬롯 count 1, 다른 슬롯 0. 그 설정은 config fingerprint 로 남는다(protocol purpose 7).
  - 위 6건은 모두 `refill_s` 가 누락 없이 기록됐다. 어떤 재고 설정을 썼는지는 각 run 의 deployment inventory 해시에 있다. 이 문서에서 대조하지 않았다.

## 오염을 막는 계산
실패·중단·timeout을 지우거나 성공 retry로 덮지 않는다. 분모는 시작한 모든 배치·시도다.
- 값이 없으면 null과 누락 수·이유를 쓴다. 누락을 0으로 바꾸지 않는다.
- 예정 run 목록과 수집 목록을 대조한다. 수집기 자체가 죽었으면 복구 기록을 남긴다.
- warmup 제외와 유효하지 않은 run의 기준은 미리 정한다. 사후 제외는 원본을 보존하고,
  이유·독립 리뷰, 제외 전후 결과를 함께 제시한다.
- 조건이 다른 하드웨어·씬·설정·모델은 한 성공률로 묶지 않는다.
- 개발/pilot, acceptance, 인식 train/validation/test를 분리한다.
  acceptance와 test를 튜닝에 썼으면 새 holdout/새 protocol로 재평가한다.
- 평균만 제시하지 않는다. N, 실패 수, 누락, 분포와 사전 선택한 불확실성 구간을 제시한다.
  20회는 초기 기준안일 뿐이다. 보편적인 신뢰도를 보장하지 않는다.

## 시간·재현
시뮬 사이클은 simulation time으로 잰다. 운영 timeout은 monotonic time으로 잰다.
sim reset·pause·시간 역행은 epoch로 구분한다.
호스트 간 monotonic timestamp를 직접 빼지 않는다. 한 수집기의 시계, 또는
동기 오차가 측정된 공통 시계로 구간을 정의한다.
UTC는 기록 정렬용이다. 짧은 지연 측정의 정확성을 자동으로 보장하지 않는다.
seed뿐 아니라 physics/render timestep, reset 절차, 확장·GPU driver, 센서 설정을 기록한다.

원본·manifest·교차 검토는 [evidence 절차](../../evidence/README.md)를 따른다.
