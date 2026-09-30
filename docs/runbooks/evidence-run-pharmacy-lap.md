# 조제실 한 바퀴 증거 실행 (`pharmacy-lap-pilot-v1`)

> **상태: 지난 기록 (2026-09-20 기준).** 지금은 [병원 한 바퀴 런카드](hospital-full.md)를 따른다.

- 대상: 마스터에서 L3-1(조제실 구간 한 바퀴)을 돌려 `evidence/runs/` 에 공식 run 으로 남기려는 사람.
- 기준: `main` `e271081`. [`pharmacy-lap-pilot-v1`](../../experiments/protocols/pharmacy-lap-pilot-v1.json), `tools/aggregate_runs.py`, `tools/evidence.py`, `schemas/run.schema.json`, [evidence README](../../evidence/README.md), [tools README](../../tools/README.md#run-디렉토리-집계).
- 상태: protocol 과 도구에 있는 것만 옮겼다. 수치·합격선을 새로 만들지 않았고, 없는 것은 "미정"으로 적었다. 1.1 의 관측 말고는 코드에서 읽은 것이다.
- 스택을 띄우는 조합은 [L3 스택 기동 조합](l3-stack-combos.md)을 따른다.

## 0. 먼저 풀어야 할 것

B1 이 풀리지 않으면 기록 PR 이 CI(`evidence.py validate`)를 통과하지 못한다.

| # | 막힘 | 근거 | 결정권자 |
| --- | --- | --- | --- |
| B1 | **#301 이 머지되기 전에는 공식 run 을 남기지 못한다.** protocol 은 아직 `proposed` 다. 머지는 재범만 한다(결정 26 = A) | `evidence.py` 의 frozen protocol 검사("recorded run requires a frozen protocol", "run predates protocol freeze") | 재범(`experiments/protocols/` 는 @jaebeom 보호 경로) |
| B2 | 원본(raw) 보존 위치. **당분간 `master01` 로컬에 두고 sha256 을 기록한다. `verify-artifacts` 는 "미실행"으로 적는다.** 위치는 시연 뒤에 다시 정한다 | 결정 27 = A(9/20, 재범 위임). [evidence README](../../evidence/README.md) 수집 순서: "외부 저장소와 접근 권한은 아직 정하지 않았다" | 재범 |

- 기록할 수 있는 run 은 run 의 `created_at` 이 protocol 의 `frozen_at` 이후인 것뿐이다.
  - **그래서 9/20 02:17·02:31 의 L3-1 실행(#240)은 이 protocol 의 공식 기록이 될 수 없다.** 공식 run 은 #301 이 머지된 뒤 새로 돌린다.
  - 이 protocol 을 쓴 기록 run 은 0건이다. 그래서 새 ID 없이 그 자리에서 동결할 수 있다([tools README](../../tools/README.md): 이미 쓴 protocol 만 새 ID 로 바꾼다).
- B2(결정 27)에 따라 manifest 의 artifact URI 는 content-addressed 키(`sha256/<전체 hash>/<파일 이름>`)로 쓰고, 원본은 `master01` 에 둔다.
  - 원본이 기록 PR 작성자 PC 에 없으므로 `verify-artifacts` 는 "미실행"으로 적는다.
  - 독립 리뷰가 원본을 대조하려면 `master01` 에 접근해야 한다. 보존 위치를 시연 뒤에 다시 정하면 그때 옮기고 해시를 대조한다.

## 1. 유효 시행 3개가 나오는 순서

protocol 의 정의(purpose 2):
- 시행 하나 = **epoch 하나 안의 트립 하나**다.
- 시행마다 `/orchestrator/reset` 을 부르고, 새 epoch 의 `RESET_DONE` 을 시행 시작으로 본다.
- `order_generator` 는 새 epoch 에서 요청 1건을 보낸다.
- **기동 직후 epoch 1 의 트립은 시행이 아니다**(리셋 barrier 를 안 거쳤다). 원본은 보존하고 분모에 넣지 않는다.
- `sample_plan` 은 seed `[0, 1, 2]`, `repetitions_per_seed` 1 이다. 그래서 **시행은 3개**다.

`aggregate_runs.py` 의 판정:
- `event_logger` 는 epoch 마다 run 디렉토리를 새로 연다. 집계는 그 디렉토리 하나 단위다.
- 센 트립이 1개면 `trial` 이다. **2개 이상이면 `ambiguous`(exit 1)** 다.
- `REQUEST_ACCEPTED` 가 없으면 `trial_without_start` 다. epoch 1 은 `not_a_trial` 이다.

그래서 자동 요청 1건만으로 시행을 만든다.

| 단계 | 할 일 | 다음으로 넘어가는 조건 |
| --- | --- | --- |
| 0 | 기동. `tools/demo_v2.sh` 의 시연 조합 그대로 띄운다. 창 모드면 **녹화를 켜고** 단계마다 캡처를 남긴다([녹화·캡처](l3-stack-combos.md#32-녹화캡처-재범-규칙-920)). `P3_DISPENSER_FILE` 은 보충이 나오는 재고다(예: 약품마다 slot a 1, slot b 0) | 스택 로그 `orchestrator up` |
| 1 | epoch 1: 자동 요청 1건이 돈다. **시행이 아니다.** 웹 요청을 넣지 않는다 | `DOCKED`. 보충이 있었다면 `REFILL_DONE`·`DISPENSER_RESUMED` 도 |
| 2 | 리셋: `/orchestrator/reset` | 새 epoch 의 `RESET_DONE` |
| 3 | 자동 요청이 `RESET_DONE` 3.5 s(벽시계, `reset_settle_s`) 뒤에 1건을 보낸다. 이것이 **시행 1(seed 0)** 이다. 웹 요청을 넣지 않는다 | `DOCKED` + `REFILL_DONE` + `DISPENSER_RESUMED` |
| 4 | 2–3 을 두 번 더 한다. **시행 2(seed 1)·시행 3(seed 2)** | 같음 |

- 리셋 방법: 웹의 리셋 버튼(`POST /api/reset`)도 같은 `/orchestrator/reset` 서비스를 부른다(`web/backend/app/ros_bridge.py`). 둘 중 무엇을 썼는지 run notes 에 적는다.
- **증거 실행에서는 웹으로 요청하지 않는다.** 같은 epoch 에 트립이 둘이면 `ambiguous` 가 되어 그 epoch 는 시행이 되지 못한다.
  - 그래서 시연 대본(자동 요청 긴급 + 웹 1인·묶음, 결정 25)과 증거 실행은 **따로** 돌린다.
  - 자동 요청의 주문은 기본 풀이면 `ord-0002`(ibu, 긴급)다. 웹을 쓰지 않으므로 쓴 주문 409·보충 중 409 는 걸리지 않는다.
- **리셋은 보충이 끝난 뒤에 누른다.** 보충 중 리셋은 그 보충을 버린다([시연 runbook 3](demo-0921-v2.md#3-시연-대본)). 그러면 그 시행의 `refill_s` 가 null 이 된다.
- `RESET_DONE` 뒤 wall 900 s 안에 `DOCKED` 도 Deliver 결과도 없으면 그 시행은 `timeout` 으로 기록하고 멈춘다(protocol `timeout`: 900 s, monotonic, `record_timeout`).
- seed: Isaac 쪽 시드 파라미터가 없으면 seed 는 시행 번호로만 쓰고 notes 에 "시드 미적용"을 적는다(purpose 8). 시행 1·2·3 → seed 0·1·2, `repetition_index` 1.

### 1.1 관측과 맞춰 본 것

9/20 L3-1(`master01`, 트리 `419b20b`, #240) 두 번의 집계 결과다. 두 번 모두 동결 전이라 공식 기록이 아니다.
- 1회차: epoch 2 에 자동 요청 1건만 돌았다. 그것이 유일한 `trial` 이었다(`lap_s` 12.517 s). epoch 1 은 `not_a_trial` 이었다.
- 2회차: epoch 2 에 자동 요청 `ord-0002` 와 웹 `ord-0003` 두 트립을 돌렸다. `aggregate_runs` 가 "2 counted trips in one run directory; the protocol runs one trip per epoch"(`ambiguous`)를 내고 metrics 를 내지 않았다.
- 1절의 순서(리셋 → 자동 요청 1건 → `DOCKED` → 리셋, 세 번)는 이 결과와 맞는다.

### 1.2 보충(REFILL)이 시행 안에 들어가는 방식

- protocol purpose 7: 보충은 트립과 **별도 구간**이다.
  - `refill_s` = 그 epoch 의 첫 `REFILL_REQUESTED` 부터 그 뒤 첫 `REFILL_DONE` 까지. `lap_s` 에 더하거나 빼지 않는다.
  - 보충은 run 의 재고 설정으로 유도하고, 그 설정은 config fingerprint 에 남긴다. protocol 은 설정값을 고정하지 않는다.
- 재고가 "약품마다 slot a 1, slot b 0"이면:
  - 자동 요청이 `ord-0002`(ibu)를 꺼내는 순간 ibu 합계가 0 이 된다.
  - 그래서 **같은 epoch 에서** `DISPENSER_PAUSED`·`REFILL_REQUESTED` 가 나온다(`dispenser_inventory.py` `take`).
- 리셋은 `/sim/reset` 이 성공한 뒤 재고를 파일 값으로 되돌린다(`orchestrator_node.py` `_reload_stores`). 그래서 **시행마다 보충이 1회씩** 나오고 `refill_s` 도 시행마다 하나 생긴다.
- `lap_success` 는 보충과 무관하다. protocol 은 보충을 성공 조건으로 두지 않는다.

## 2. 기록에 필요한 칸과 넘길 packet

### 2.1 시행 하나 = `evidence/runs/<run-id>.json` 하나

`schemas/run.schema.json` 의 필수 칸이다. 값을 모르면 not_applicable 로 꾸미지 않고 이유를 적는다([evidence README](../../evidence/README.md)).

| 칸 | 값을 어디서 | 비고 |
| --- | --- | --- |
| `run_id` | `YYYYMMDDTHHMMSSZ-master0N-<8 hex>` | 파일 이름과 같다. 앞부분은 `created_at`·`host_id` 와 맞아야 한다 |
| `created_at`, `host_id` | 수집 시각, `master01` 또는 `master02` | `created_at` 은 protocol `frozen_at` 이후여야 한다 |
| `code.commit`, `code.dirty` | release 워크트리의 `git rev-parse HEAD`, `git status --porcelain` | dirty 면 patch 를 artifact 로 보존하고 `dirty_patch_sha256` 을 적는다 |
| `environment.versions` | os, ros, isaac_sim, rmw, gpu_driver, **cuda** | cuda 는 [host-inventory](../setup/host-inventory.md)에 없다. 마스터에서 `nvidia-smi` 머리글로 조회한다 |
| `environment.fingerprints` | config, scene, model, dataset | 2.2 packet 의 해시. 시연은 color 검출이라 model·dataset 은 해당 없음일 수 있다. 그때는 이유를 적는다 |
| `clocks` | `duration: simulation`, `timeout: monotonic` | protocol 과 같다 |
| `seed`, `repetition_index` | 0·1·2, 1 | 1절 |
| `protocol.path`, `protocol.sha256` | `experiments/protocols/pharmacy-lap-pilot-v1.json`, **동결 뒤** 파일의 sha256 | `aggregate_runs` 출력에도 찍힌다 |
| `phase` | `pilot` | protocol 과 같다 |
| `outcome` | succeeded / failed / aborted / timeout | purpose 5. `aggregate_runs` 의 `success_checks` 로 판정한다 |
| `artifacts[]` | `uri`(`sha256/<hash>/<파일>`), `sha256`, `size_bytes` | 2.2 packet 전부 |
| `metrics[]` | `aggregate_runs.py --json` 의 `metrics` 그대로 | 일곱 개. null 이면 `sample_count`·`missing_count` 로 누락을 표시한다 |
| `notes` | `RESET_DONE` 의 epoch(purpose 2 필수), 리셋 방법, 시드 미적용, 보충 요청 없음 등 | 집계기 notes 도 옮긴다 |

### 2.2 packet(마스터 → 기록 PR 작성자), 시행마다

| 파일 | 출처 | 넘길 값 |
| --- | --- | --- |
| `events.jsonl`, `order_status.jsonl`, `cabinet.jsonl`, `orders.jsonl`, `meta.json` | `event_logger` 의 그 epoch run 디렉토리 | sha256, 크기 |
| deployment inventory | 마스터에서 쓴다: 실행 SHA, `stub_loop.launch.py` 인자 전부, 스테이지 인자(`P3_STAGE_ARGS` 포함), `ROS_DOMAIN_ID`, 재고·주문 풀·zones 파일 경로와 해시 | 파일 하나로 sha256, 크기 |
| 스테이지 로그 | 둘째 줄 `scene base_usd_sha256=… meters_per_unit=… up_axis=…`(#259) | sha256, 크기. scene fingerprint 의 근거 |
| 스택·팔 로그 | orchestrator·adapter·m0609_arm | sha256, 크기 |
| `aggregate_runs.py --run <dir> --protocol … --json` 출력 | 마스터의 release 워크트리에서 실행 | 출력 전문. `status` 가 `trial` 인지 |
| 원본 위치 | `master01` 의 경로(사용자 이름은 빼고). 결정 27 | 텍스트 |

epoch 1(시행 아님)의 run 디렉토리도 같은 방식으로 해시해 packet 에 넣는다. protocol 이 "원본은 보존하고 분모에 넣지 않는다"고 한다.

## 3. 기록 PR 절차 (제안)

누가 무엇을 하는지는 재범이 정한다. 아래는 제안이다.

1. 마스터에는 gh 가 없다. 2.2 packet(해시·크기·집계 출력·경로)을 **텍스트로** #240 댓글로 넘긴다. 원본 파일은 `master01` 에 둔다(결정 27).
2. 기록 PR 작성자는 packet 으로 `evidence/runs/<run-id>.json` 을 시행마다 하나씩 쓰고 PR 을 올린다.
   - `python3 tools/evidence.py validate --base origin/main` 을 돌린다(schema, protocol hash, 이름, 기존 기록 불변).
   - `verify-artifacts` 는 **미실행**으로 적는다(결정 27. 원본이 작성자 PC 에 없다).
3. `evidence/` 는 @jaebeom 보호 경로라 재범 승인으로 머지한다.
4. 작성자가 아닌 한 사람이 `docs/templates/evidence-review.md` 로 원본 접근·해시·누락을 확인하고 `evidence/reviews/` 에 남긴다([evidence README](../../evidence/README.md) 수집 순서 끝). 에이전트 검토는 사람 승인이 아니다.
5. protocol 동결(#301)은 이 기록 PR 과 다른 PR 이고, 먼저 머지되어야 한다.

## 4. "3회 연속"은 protocol 에 없다

- protocol 에는 합격선이 없다("합격선은 없다", purpose 첫 문장). `metrics` 어디에도 `threshold` 가 없다.
- "연속"의 정의도 없다. 중간 실패 없이 이어진 세 번인지, 세 시행이 모두 성공인지 적혀 있지 않다.
  - protocol 이 정하는 것은 시행 3개(seed 0·1·2 × 1)와 `lap_success` 비율(성공 트립 수 / 시작한 트립 수. aborted·timeout·failed 포함)뿐이다.
- v0.3.0 의 "조제실 구간 3회 연속 성공"은 [일정표](../planning/schedule.md) 문구이고 protocol 밖이다. 판정에 쓰려면 뜻을 재범이 정한다(**미정**).
- 이 runbook 은 시행 3개를 모두 기록하는 순서만 준다. 실패한 시행도 기록한다. 재실행으로 바꿔 넣지 않는다([evidence README](../../evidence/README.md)).
