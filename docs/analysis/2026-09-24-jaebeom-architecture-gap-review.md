# 설계 문서 ↔ 시스템 반영 점검 (9/24) — 아키텍처 갭 검토

- 상태: **unreviewed**. 검토자: 미지정. 대응 run: 없음.
- 요청: 재범 9/24 "전체 docs 를 훑고 시스템적으로 반영할 수 있는 부분을 훑어 달라".
- 기준: `main` `c99f119`(2026-09-24). **정적 점검이다.** 코드·회차를 실행하지 않았다.
- 방법: `docs/` 전체(architecture·adr·rfc·analysis·planning·process·policy·presentation·runbooks)를 읽고, 여섯 갈래로 코드와 대조했다.
  배송 계약 ↔ orchestrator, `sim/README.md` ↔ `sim/standalone` ↔ 어댑터, STAT 계획 ↔ 코드, `web/api.md` ↔ 백엔드 ↔ 프론트 ↔ orchestrator, 기획 12편 ↔ 코드, 런북·프로세스 ↔ 도구·CI.
  2절의 결함 인용(P1-1, P1-4, P1-6)과 4절의 굵은 수치는 이 점검에서 소스로 직접 다시 확인했다. 그 밖의 행 번호는 갈래별 감사 인용이다.
- 전제: [설계 갭 계획(9/24)](2026-09-24-design-gap-plan.md) G1–G8 과 [미결 결정표](2026-09-24-open-decisions.md)가 맡은 항목(계약 §1·§2·§7 현행화, 시스템 그림, G5 증거 등록)은 반복하지 않는다. 이 문서는 **구조·코드·도구에 반영할 것**만 더한다.
- 이 문서는 제안이다. 구현·통과를 선언하지 않는다. 결정은 재범이 한다. 저장소에 ADR 0006 은 없다. ADR 은 0001·0002 둘뿐이다. 둘 다 proposed 다. 2절 P0-4 가 0003부터 0006까지를 제안한다.

## 1. 문서가 정한 핵심 아키텍처 (요약)

1. 한 바퀴는 웹 요청에서 시작한다. orchestrator 의 명시적 FSM 이 받는다(ADR 0001). 조제기가 배출한다. 벨트 끝에서 UR5 가 집는다. Nav2 는 접근점까지 간다. 그 다음은 직접 추종기다. 참값으로 인증한다(v0). 보관함에 놓는다. 도크로 돌아온다. 성공은 orchestrator 의 주장이 아니다. `/evaluator/cabinet` 을 본 event_logger 의 run 기록이다.
2. Isaac(Python 3.11)은 `std_msgs/String` JSON 만 내고 `isaac_adapter` 가 계약 타입으로 옮긴다(ADR 0002). 이름·타입의 원본은 `rokey_p3_interfaces` 다.
3. 실제 배치는 마스터 한 대가 기본이다. `P3_ROLES` 로 두 대를 나눈다. 기동은 `tools/demo_v2.sh` 하나다(시스템 그림 9/24).
4. 측정 순서는 pilot 이다. 다음은 frozen protocol 이다. 다음은 acceptance 다. 증거는 `evidence/runs` 다. 외부 원본 해시도 증거다. 관측과 해석을 나눈다(지표 정책).
5. 역할은 마스터 observer 다. 클라우드 developer 다. reviewer 다. 결정은 이슈·PR·ADR 에만 둔다(공통 규칙).

## 2. 시스템 반영 필요 항목 (우선순위 순)

우선순위 기준은 일정이다. 촬영 9/26, 증거 동결 9/28, 시연 9/29 를 흔들지 않는 것이 먼저다.

| 등급 | 뜻 |
| --- | --- |
| **P0** | 문서·설정·도구. 코드 동작 불변. 촬영 전에 해도 된다 |
| **P1** | 촬영 뒤 소규모 코드. L1·L2 로 닫힌다. 동작 변경이면 마스터 L3 한 바퀴 |
| **P2** | 발표 뒤 구조 정리 |

### P0-1. 골든 구성이 런카드와 스크립트에서 다르다

- **위치**: `docs/runbooks/hospital-full.md` 150·221–237행, `tools/demo_v2.sh` 128행, `docs/runbooks/emptyworld-lap-stack.md` 30–40·125행.
- **현황·문제**: 런카드는 `P3_DISPENSE_TIMEOUT_S` 골든 값을 10 으로 적었다. 스크립트의 hospital 기본은 `af78350`(9/24)에서 30 이 됐다. 골든 명령은 이 값을 주지 않는다. 그래서 지금 골든 명령은 런카드 표와 다른 구성으로 돈다. 그 밖에 `judge_run.py --run` 호출은 `--logs`·`--stamp` 가 필수다. exit 2 다. 빈월드 기동 블록은 `need P3_DOMAIN P3_M0609 P3_DISPENSER_FILE` 에 걸린다. 런카드 6.1절이 필수로 쓰는 `tools/record_qa.py` 는 main 에 없다.
- **제안**: 런카드 3.2 골든 표와 `docs/architecture/stage-arguments.md` 에 30 과 근거(`af78350`, ord-0009 not_ready 3회)를 적는다. 또는 골든 명령에 값을 명시한다. 런북의 명령 블록은 `tools/demo_v2.sh cmds` 출력을 붙여 넣는 규칙으로 바꾼다(손으로 옮겨 적지 않는다).
- **영향·트레이드오프**: 문서만이다. 다만 "골든" 이라는 말의 근거가 바뀌므로 다음 회차 보고에 어느 값으로 돌았는지 적어야 한다.

### P0-2. 증거 파이프라인이 끝에서 끊겨 있다

- **위치**: `experiments/protocols/ward-lap-b-acceptance-v1.json`, `evidence/runs/`, `evidence/deployments/`, `schemas/protocol.schema.json`, `tools/evidence.py`, `tools/hospital_orders.py`.
- **현황·문제**: frozen acceptance protocol 은 0 이다. acceptance run 은 0 이다. 병원 골든 회차의 `evidence/runs` 등록은 0 이다. 마지막 run 은 9/22 pilot 이다. 배포 기록은 0 이다. 골든 SHA 4개(`4d01333`·`138cbac`·`5a51804`·`aca8840`)는 런카드 188행 한 줄로만 관리된다. 원격 태그는 `v0.4.0` 까지다. 병원 골든에는 없다. `schedule.md` 의 "마스터 배포는 태그로만" 과 어긋난다. `hospital_orders.py` 의 판정 출력(`orders.jsonl`·`summary.md`)을 run manifest 로 옮기는 도구가 없다. `protocol.schema.json` 에는 `supersedes` 가 없다. `additionalProperties: false` 다. protocol 정정 규칙(새 파일 + supersedes)을 지킬 수 없다.
- **제안**:
  1. 실제 판정선(골든 5 + 감속기 2 + boot_check 게이트 + 10건 도구 판정)을 담은 `hospital-full-acceptance-v1.json` 을 **촬영 회차 전에** frozen 으로 머지한다. 기존 `ward-lap-b-acceptance-v1` 은 손대지 않는다.
  2. `tools/evidence.py from-run --logs <P3_LOG_DIR> --stamp <시각> --orders <hospital_orders 출력>` 을 더한다. `demo_v2.sh status` 의 tree sha·`demo_v2.sh env` 출력을 `code`·`environment` 칸에, `summary.md` 의 표를 `metrics` 에 넣은 골격을 만든다. 사람은 원본 위치·해시만 채운다.
  3. 골든 SHA 에 `v0.5.0-rc.N` 태그를 찍고 `evidence/deployments/` 에 한 건씩 남긴다.
  4. `protocol.schema.json` 에 `supersedes`·`correction_reason` 을 더한다(run 스키마와 같은 모양).
- **영향·트레이드오프**: 1은 G5 의 "이후 실행에서 수집" 원칙과 같다. 과거 회차를 소급 등록하지 않는다. 2는 도구 코드(ROS 없음, L1). 3은 저장소 관리 담당(재범) 일이다.

### P0-3. 예외 문서가 없다

- **위치**: `docs/planning/scenario.md` 39·174·196행, `docs/architecture/delivery-contract-v1.md` 12·730행, `src/rokey_p3_interfaces/msg/OrderStatus.msg` 17행, `action/PickPouch.action` 14행.
- **현황·문제**: 네 곳이 "예외 문서에서 정한다" 고 가리키는데 파일이 없다. 종료 `reason` 어휘는 `trip_fsm.py`(`_give_up_all`·`_auth_failed`·`_finish`·`redock_*`)에만 있고, web `alarms.py` 와 `tools/aggregate_runs.py` 가 각자 문자열로 다시 안다.
- **제안**: `docs/architecture/exception-outcomes-v1.md` 를 **as-built 표**로 쓴다. 조건(PickPouch outcome 7종, GoToZone outcome, 시한, 인증 불일치, 복귀 거부) → 종료 상태 → `reason` 문자열 → 재배차 가능 여부. 원본은 코드다. 새 설계를 넣지 않는다. 계약 v1 이 "예외 문서" 라고 부르는 자리를 이 파일이 맡는다.
- **영향·트레이드오프**: 문서만이다. 발표 3.5 "검증 및 분석" 의 실패 원인 표가 이 어휘를 그대로 쓴다.

### P0-4. 되돌리기 어려운 결정이 ADR 이 아니라 이슈 댓글에 있다

- **위치**: `docs/adr/`(0001·0002, 둘 다 proposed), #215·#527·#576·#602 댓글, `docs/analysis/2026-09-24-open-decisions.md`.
- **현황·문제**: 위치 추정은 odom 이다. AMCL 이 아니다. Nav2 는 접근점까지다. 그 다음은 직접 추종기다. 인증·집기 v0 은 참값 센서다. 단일 마스터가 기본이다. `P3_ROLES` 로 두 대를 나눈다. 병원 씬을 채택했다. 씬 컨베이어를 쓴다. 우리 벨트는 끈다. `render_every 2` 다. 레일 드라이브 검증값이 있다. 전부 "바꾸기 비싼 결정" 인데 ADR 이 없다. `adr/README.md` 4번은 이슈·LLM 결론을 승인 이력으로 치지 않는다.
- **제안**: ADR 을 소급 기록한다. 결정 댓글 링크와 회차 ID 를 근거로 달고 상태는 재범 승인 뒤 accepted 로 한다.
  - 0003 병동 주행: odom 기준 TF, Nav2 는 접근점까지, 마지막 0.5 m 는 직접 추종기(#576, #639·#645, 회차 골든-4).
  - 0004 인증·집기 v0 = 참값 센서, 카메라는 v1 옵션(#576 결정 44, k5-delivery-interface).
  - 0005 배치: 마스터 한 대 기본, `P3_ROLES` 두 대 분리(#602, 회차19).
  - 0006 병원 씬 채택과 성능 기본값: 씬 컨베이어 사용·우리 벨트 끔(#215, #553), `render_every 2`·`rail_drive [1e5,1e4,5e4]`(회차 11·12, reha-02 F).
  - 0001·0002 는 accepted 로 올릴지 재범이 정한다(둘 다 9/17 뒤 코드가 그대로 따르고 있다).
- **영향·트레이드오프**: 문서만이다. 발표 "설계-구현 일치" 의 근거가 이슈 댓글 대신 ADR 링크가 된다.

### P0-5. 확정 시나리오와 as-built 가 13곳 다르다

- **위치**: `docs/planning/scenario.md`(팀 확정 9/16) ↔ `integration-resource-two-phase-plan.md`·`k5-delivery-interface.md`·`schedule.md`·코드.
- **현황·문제**: 대표 7건이다. 2축 레일이 3축이 됐다(`rail_z`). AMCL 이 odom 이 됐다. 손 카메라 인증이 참값 v0 이 됐다. "간호사 화면 없음" 인데 `web/frontend/nurse.html` 이 있다. 도크는 5 인데 `zones.hospital.yaml` 은 4 다. 우리 벨트가 씬 컨베이어가 됐다(`hospital_conveyor.py`). 묶음(병동) 핵심 유형이 schedule C 등급이다. 미구현이다. 나머지는 4절 5항이다.
- **제안**: `scenario.md` 본문은 그대로 두고(확정 문서 소급 금지) §10 변경 이력에 "9/24 as-built" 행을 항목별로 더한다. 각 행은 결정 출처(ADR 0003–0006 또는 댓글)를 가리킨다.
- **영향·트레이드오프**: 문서만이다. 발표에서 "계약 뒤 변경" 을 어디까지 밝힐지는 재범 결정이다.

### P0-6. 색인·이름 규칙이 강제되지 않는다

- **위치**: `docs/README.md`, `docs/analysis/README.md`, `tools/check_repository.py`, `docs/process/naming.md`.
- **현황·문제**: 골든 런카드 `hospital-full.md` 가 `docs/README.md` 운영 행에 없다. 런북 16개 중 4개만 색인에 있다. analysis 9개가 analysis 색인에 없다. analysis 날짜 접두 규칙에 안 맞는 파일이 약 17개다. `check_repository.py` 는 kebab-case 와 물결표만 본다.
- **제안**: `check_repository.py` 에 두 단계를 더한다. (a) `docs/<영역>/*.md` 가 그 영역 README 또는 `docs/README.md` 에서 링크되는지(이미 있는 `local_link_errors` 의 링크 파서를 쓴다). (b) `docs/analysis/` 의 날짜 접두. 기존 위반은 한 번에 고치지 말고 허용 목록으로 시작한다.
- **영향·트레이드오프**: 도구 코드 소량(L1). 허용 목록이 없으면 첫 CI 가 빨개진다.

### P1-1. 잠재 결함: 이전 트립의 인식표로 인증될 수 있다

- **위치**: `src/rokey_p3_orchestrator/rokey_p3_orchestrator/trip_fsm.py` 319·443·627–642·1076행, `orchestrator_node.py` 325–329행.
- **현황·문제**: `tag()` 가 채운 `_last_tag` 를 `_clear_trip` 이 비우지 않는다. 리셋도 비우지 않는다. `_result_authenticating` 은 ScanTag 결과에 `tag_id` 가 없으면 `_last_tag` 로 인증한다. 노드의 `_on_tag` 는 `stamp` 를 보지 않는다. `kind` 도 보지 않는다. 계약 2.4 "1.0 s 넘게 오래된 판독은 쓰지 않는다" 가 orchestrator 쪽에는 없다. 지금 골든 경로(`scan_tag_source: sim`)는 결과에 `tag_id` 를 채운다. 그래서 드러나지 않았다.
- **제안**: `_clear_trip` 과 리셋에서 `_last_tag` 를 비운다. `_on_tag` 에서 `kind`(PATIENT·STATION)와 stamp 나이를 검사한다. L1 시험 하나: 트립 A 의 판독이 트립 B 의 빈 결과를 통과시키지 않는다.
- **영향·트레이드오프**: 코드 10줄 안팎. 골든 경로 동작은 불변이다. 그래도 동작 변경 규칙대로 RC 뒤 L3 한 바퀴에 태운다.

### P1-2. 계약 어휘의 단일 출처가 없다

- **위치**: `Event.msg`·`OrderStatus.msg`(원본) ↔ `trip_fsm.py` 103–116, `run_log.py` 33–50, `status_view.py`, `stubs/*.py`, `isaac_json.py`, `web/backend/app/alarms.py` 43–67, `web/frontend/js/*.js`, `tools/aggregate_runs.py`·`judge_run.py`·`hospital_orders.py`, `sim/standalone/p3sim/belt.py`·`bridge.py`.
- **현황·문제**: 이벤트 26종, 주문 상태 7, 종료 4, 모드 4, 토픽 약 20, Isaac JSON 토픽 13 이 src·web·sim·tools 에 각각 문자열로 있다(`HOLD_RETURN` 26개 파일, `/pharmacy/belt` 20개 파일). 숫자↔이름 표는 4벌이다. 시간 상수도 갈라졌다: settle 3.0(orchestrator 상수)·3.5(발행기)·3.5(web), reset 30·35, refill 90·120. zone 정규식은 nav 가 `door_*`·`cp_*` 를 포함하고 web·계약은 미포함이라 같은 목적지를 웹은 막고 orchestrator 는 받는다. Isaac 쪽은 Python 3.11 이라 `rokey_p3_interfaces` 를 import 할 수 없어 구조적으로 갈라진다.
- **제안**: 2단계.
  1. `schemas/contract-v1.json` 하나에 이름(이벤트·상태·모드·토픽·JSON 토픽 13 과 필드)·정규식·시한 기본값을 둔다. `tests/test_contract_vocabulary.py` 가 위 파일들을 **글자로** 읽어 대조한다(`tests/test_interface_contract.py` 방식, ROS 없음). 어긋나면 CI 가 빨갛다.
  2. 각 모듈이 그 JSON 을 읽게 바꾼다. Isaac 3.11·web venv·tools 가 같은 파일을 읽으므로 import 경계를 넘지 않는다.
- **영향·트레이드오프**: 1단계는 시험만이라 동작 불변. 2단계는 패키지마다 PR 하나. 생산자·소비자를 함께 바꾸는 계약 규칙은 그대로다.

### P1-3. Isaac JSON 스키마가 두 벌이고 검증 규칙이 다르다

- **위치**: `sim/standalone/p3sim/bridge.py` 16–37·`SCHEMAS`, `src/rokey_p3_bringup/rokey_p3_bringup/isaac_adapter.py` 99–113, `isaac_json.py` `*_FIELDS`, `sim/README.md` 598–606, ADR 0002 41행, `sim/standalone/hospital_main.py` 29·105–127행.
- **현황·문제**: 토픽 13개 이름이 두 파일에 따로 있다. 필드 집합은 같지만 검증 규칙이 9곳 다르다(예: tag_reads `tag_id` 빈 값을 sim 은 unreadable 때 허용, 어댑터는 항상 거부. `zone_id` 는 반대). README 표는 7개만이고 opt-in 6개는 README·ADR 어디에도 없다. ADR 0002 의 "표를 바꾸면 `v` 를 올린다" 는 토픽 6개를 더하는 동안 지켜지지 않았다(`v` 1 고정). `hospital_main.py` 의 `/isaac/conveyor/pouch_request` 는 발행자·어댑터·문서·시험이 없다. 교차 시험(`test_isaac_adapter.py` 764–908)은 4개 토픽만 비교한다.
- **제안**: P1-2 의 JSON 에 13 토픽의 필드·필수 규칙을 넣고, 교차 시험을 13 토픽 전부와 검증 규칙(빈 값 허용 여부·범위)까지 넓힌다. `v` 를 2 로 올리고 README 표를 갱신한다. `pouch_request` 는 지우거나 어댑터를 붙인다(P2-2 와 함께).
- **영향·트레이드오프**: `v` 를 올리면 어댑터·스테이지를 같은 PR 에서 바꾼다. 마스터 L3 한 바퀴가 필요하다.

### P1-4. 웹이 orchestrator 의 진실을 추정하고 재구현한다

- **위치**: `web/backend/app/state.py` 41·134–183, `main.py` 105–237·264–279·563–583, `order_pool.py`, `zones.py` 35, `alarms.py`, `orchestrator_view.py` 45, `web/api.md` 629–651·896, `trip_fsm.py` 1107–1114, `orchestrator_node.py` 351–353·398.
- **현황·문제**:
  1. 수락 정책이 3벌이다(orchestrator·FSM·web). `mixed_rooms`·`refill_in_progress`·`insufficient_stock` 은 웹에만 있어 같은 요청이 웹 경유일 때만 막힌다. 주문 풀 파서 2벌은 규칙이 다르다(src 는 첫 오류에서 실패, web 은 오류 행을 버리고 계속). `web-console.md` 의 "`StatusModel` 재사용" 은 코드에 없다(`orchestrator_view.py` 가 다시 내보내기만 한다).
  2. `trip_open` 은 `DOCKED`·`RESET_BEGIN` 으로만 닫힌다. FSM 은 복귀가 끝내 거부되면 `DOCKED` 없이 IDLE 로 끝낸다(1114행). 그 뒤 웹은 `trip_in_progress` 로 요청을 계속 거부한다.
  3. `/orders/status` 는 latched 인데 epoch 이 없다. 늦게 붙은 웹이 이전 epoch 주문을 사용된 것으로 유지한다.
  4. `api.md` 의 WS `events` 타입은 서버가 내지 않는다(`broadcast` 는 snapshot·alarms 뿐). 프론트는 `recent_events` 12개에만 기댄다.
- **제안**:
  1. web 이 src 의 ROS-free 모듈(`order_pool.py`, `navigation/zones.is_zone_id`, `terminal_states`, `run_log.ORDER_STATE_NAMES`)을 import 한다(이미 `orchestrator_view.py` 가 쓰는 방식). 웹 사본은 지운다. 웹 전용 거부 3종은 계약 `/deliver` 수락 조건에 넣을지 재범이 정한다.
  2. orchestrator 가 `/orchestrator/state`(latched, depth 1: `phase`·`epoch`·`active_request_id`·`accepting`·`accept_after`) 를 낸다. 웹은 busy·`trip_open` 을 추정하지 않고 이것을 읽는다. 메시지 1개 추가라 계약 9절 호환(추가만).
  3. 웹 주문 표 키를 (epoch, order_id) 로 바꾼다. epoch 은 `RESET_DONE` 에서 안다. wire 변경 없이 된다.
  4. `api.md` 에서 `events` 를 지우거나 구현한다. `test_contract_doc.py` 가 WS `type` 과 라우트 목록도 보게 한다.
- **영향·트레이드오프**: 1·3·4 는 웹만이다. 2 는 계약 v1.2 항목이라 재범 결정이고 orchestrator 한 줄이 아니다(FSM phase 노출).

### P1-5. 배포 설정이 환경 변수 90종이다

- **위치**: `tools/demo_v2.sh`(893줄, `P3_*` 90종), `config/`(README 만), `docs/runbooks/hospital-full.md` 2절, `evidence/deployments/`(비어 있음).
- **현황·문제**: `repository-layout.md` 는 `config/` 를 배포 설정 자리로 정했다. 실제 배포 설정은 런북 명령 한 줄과 사람이 기억하는 env 다. 골든은 런카드 한 줄이다. 발표 점수표도 "P3_* 약 30종이 흩어져 한 표가 없다" 고 적었다(실제 90). `boot_check` 는 창·잠금·시계·녹화만 본다.
- **제안**: `config/profiles/<world>.<host>.env` 를 커밋한다(사이트 값인 자산 경로는 `config/local/` 로, gitignored). `P3_PROFILE=<file> tools/demo_v2.sh up` 이 그 파일을 먼저 source 한다. `demo_v2.sh env` 출력을 run 기록 `environment` 에 그대로 붙인다(P0-2 의 `from-run` 이 한다). `boot_check` 가 필수 키와 자산 sha 를 게이트로 본다. 런카드 2절 명령은 profile 이름 한 줄이 된다.
- **영향·트레이드오프**: 스크립트에 loader 20줄. 런북 명령이 짧아지는 대신 profile 파일이 골든의 일부가 된다(SHA 와 함께 태그).

### P1-6. orchestrator 시한·상수가 파라미터가 아니고 기본값이 계약과 다르다

- **위치**: `trip_fsm.py` 150–162(`TripConfig`), `orchestrator_node.py` 54·150·169·749, `refill_planner.py` 65, `isaac_adapter.py` 136, `stub_loop.launch.py` 183, 계약 §7·§3(539–547행)·§2.1(176행).
- **현황·문제**: `TripConfig` 의 goto·pick·scan 시한과 재시도 10개가 ROS 파라미터가 아니다(계약 §7 "타임아웃은 파라미터"). `RESET_SETTLE_S` 는 상수다. refill 시한 90 은 노드 파라미터로 안 나온다. `Dispense` 2 s 시한은 orchestrator 에 없고(`call_async` 무한) 어댑터에만 있어 stub 경로는 시한이 없다. `deck_slots` 기본은 세 곳 모두 5 인데 계약은 3 이고 3 을 주는 곳은 `demo_v2.sh` 뿐이다. `/clock` 2 s 정지 시 새 goal 금지(계약 105행)는 orchestrator 가 `/clock` 을 구독하지 않아 없다. `/amr_1/gripper/holding` 은 구독만 하고 판정에 안 쓴다.
- **제안**: `declare_parameter` 로 노출하고 기본값은 P1-2 의 JSON 에서 읽는다. `deck_slots` 기본을 계약대로 3 으로 맞추거나 계약을 5 로 고친다(하나를 고른다). orchestrator 에 Dispense 시한을 넣는다. `/clock` 감시와 `holding` 판정은 계약에서 지우거나 구현한다(둘 다 "있다고 적혀 있는데 없다" 상태를 끝낸다).
- **영향·트레이드오프**: 파라미터 노출은 동작 불변. 기본값 변경은 동작 변경이라 L3.

### P1-7. 프로세스 규칙이 CI 에 없다

- **위치**: `.github/workflows/ci.yml` 8–10행, 공통 규칙의 PR 전 명령, `.github/CODEOWNERS`, `docs/process/naming.md` 11행, `tools/git-hooks/pre-push`.
- **현황·문제**: base 가 `main` 이 아닌 쌓은 PR 은 CI 가 안 돈다(문서가 이미 아는 구멍, agent-workflow 4번). 브랜치 접두는 강제되지 않는다(머지 이력에 `perf/`·`exp/`·`film/` 과 도구 이름 접두). 공통 규칙의 네 명령에 `sim/tests`·web pytest·`ci_test_counts` 가 없어 sim·web 변경은 로컬 초록·CI 빨강이 가능하다. colcon 명령이 3벌이다(규칙 파일은 인자 없음, repository-layout `--base-paths src`, CI `--executor sequential`). CODEOWNERS 에 `docs/process`·`docs/runbooks`·`config`·`web` 이 없다.
- **제안**: `tools/check_local.sh` 하나가 CI 와 같은 순서로 다 돌리고, 공통 규칙은 그 한 줄만 적는다. `ci.yml` 의 `branches: [main]` 필터를 뺀다(쌓은 PR 도 돈다). `changes` job 에서 `github.head_ref` 접두를 본다. CODEOWNERS 를 채운다.
- **영향·트레이드오프**: CI 러너 사용이 는다. 쌓은 PR 에서 두 번 도는 것을 `concurrency` 가 이미 막는다.

### P2-1. god 모듈과 의존 방향

- **위치**: `orchestrator_node.py` 934줄, `pharmacy_stage.py` 3272줄(preset 9), `arm_node.py` 1932줄, `m0609_arm_node.py` 1837줄, `stub_loop.launch.py`(인자 약 40, 이중 발행 방어 3종), orchestrator `package.xml` 16행(navigation 의존), `stubs/common.py` 14행(orchestrator 의존).
- **현황·문제**: orchestrator 노드가 Deliver 서버·FSM 배선·보충 클라이언트·sqlite 약 DB·`CheckContainer` 서비스·조제기 상태 발행·리셋 barrier 를 다 한다. 계약 노드 표(67행)보다 넓다. `order_pool.yaml` 을 읽는 곳이 7곳, 기본 경로 계산이 3벌이다. epoch 상태는 노드·FSM·RefillPlanner 3벌을 손으로 맞춘다.
- **제안**: `pharmacy_db` 서비스를 별 노드로 뺀다. 스테이지 preset 을 yaml 데이터로 옮긴다. ROS-free 공용 모듈(`order_pool`, `terminal_states`, `zones`, `topology`)을 `rokey_p3_common`(ament_python, ROS 의존 0)으로 모아 orchestrator→navigation, stubs→orchestrator 의존을 끊는다. 웹도 그 패키지를 import 한다(P1-4 의 1).
- **영향·트레이드오프**: 발표 뒤. 패키지 하나가 늘고 colcon 패키지 수 검사(README "7 packages")를 고친다.

### P2-2. sim 스크립트 중복과 사각지대

- **위치**: `sim/standalone/minimal_clock.py` 207–221, `m0609_refill_stage.py` 105–133·244–250·472–498·630–635·1058–1085, `pharmacy_stage.py` 32–33·925·935–990, `hospital_main.py` 66–142·241–252·277–351, `hospital_workcell_demo.py` 73, `sim/README.md` 4·6–14·109–121·192·959.
- **현황·문제**: 기동 순서(SimulationApp → SIGINT → bridge 확장 → clock 그래프 → 타임라인 구독)가 3벌, 헬퍼 6종이 2벌, `keep_running` 이 3벌, 공통 argparse 인자가 4벌이고 기본값이 다르다. `pharmacy_stage.py` 가 다른 스크립트 둘을 라이브러리처럼 import 한다. `hospital_main.py` 의 route 경로(312–351행)는 도달 불가이고 시험이 없다. `--livestream` 은 AttributeError 로 끝난다. 스테이지 인자 약 55개가 README·stage-arguments 어디에도 없다. README 4행 "병원 씬은 아직 스테이지와 합치지 않았다" 는 낡았다.
- **제안**: `p3sim/app.py` 하나(SimulationApp·bridge·clock·SIGINT·closing 가드)로 모은다. `hospital_main.py` 는 wrapper 로 줄이거나 삭제한다. 인자 표는 argparse 에서 생성한다(`--help` 출력을 README 표로 붙이는 시험). README 4·192행을 고친다.
- **영향·트레이드오프**: 발표 뒤. 스테이지 코드 변경은 전부 마스터 L3 다.

### P2-3. STAT 의 경계를 결정으로 남긴다

- **위치**: `src/rokey_p3_orchestrator/rokey_p3_orchestrator/stat_*.py`, `docs/architecture/stat-delivery-contract-v1.md` §8·108행, `docs/planning/p3-stat-implementation-plan.md` §3.2·§10·§11.2.
- **현황·문제**: S0 CLI 만 있고 본선과 결합이 없다(orchestrator import 0, launch 0, 웹 0). 별 원장(sqlite), epoch 1 고정, wall clock, `/events`·event_logger 에 닿지 않는다. 계약 §8 의 "두 곳을 한 트랜잭션" 이 2곳에서 깨진다(FLY commit 과 `destination_mismatch` FAILED, `_fail` 과 `_stop`). fence 에 막힌 op 는 매 tick 재전송되어 `STAT_COMMAND_FENCED` 가 쌓인다(계약은 "한 번"). 계획서 §3.2 의 파일(`stat_custody`, `resource_lease`, `rokey_p3_aerial`, launch)은 전부 없다.
- **제안**: ADR 로 "발표 범위 = 고립 유지" 를 명시하고, 통합 조건(M0609 중재자·epoch 참여·sim time·event_logger 경로·독립 평가기)을 계약에 남긴다. 두 결함은 L1 로 고친다.
- **영향·트레이드오프**: 발표 뒤. 지금은 공유 자원을 안 건드려 충돌이 없다.

### P2-4. 다중 AMR 전제 vs 단일 FSM

- **위치**: `scenario.md` 1절(5대 상정), `OrderStatus.msg`(robot_id·epoch 없음), `orchestrator_node.py`(단일 `/deliver`·단일 `robot_id`), `docs/analysis/node-topology-v1.md`, `communication-state-inventory-v1.md` §7.
- **현황·문제**: 두 대를 띄우면 `/deliver` 서버·재고·epoch·`zones_tf` 가 중복된다. 화면·기록이 어느 로봇의 주문인지 모른다. 이미 두 분석 문서가 적었고 결정이 없다.
- **제안**: "v1 = AMR 1대, 배차기 없음" 을 ADR 로 못 박고, v2 항목으로 `OrderStatus`·`Event` 에 `robot_id`·`epoch` 를 더하는 계약 v1.2 초안을 둔다(run 스키마와 함께).
- **영향·트레이드오프**: 발표 뒤. 시나리오의 "5대 상정" 문장은 as-built 부록(P0-5)에서 "시뮬 1대" 로 밝힌다.

## 3. 즉각 실행 가능한 액션 아이템

한 항목 = PR 하나. 검증 명령은 공통 규칙 네 줄 + 항목별 한 줄이다. 담당은 이 문서가 정하지 않는다. #576 카드표에서 정한다. 시점은 #680 댓글 5809908189 의 권고를 따른다.

**촬영 전(문서·설정·도구, 동작 불변)**

- [ ] P0-1 런카드 3.2·stage-arguments 에 `P3_DISPENSE_TIMEOUT_S` 30 과 근거를 적는다. `judge_run` 호출 예와 빈월드 기동 블록을 `demo_v2.sh cmds` 출력으로 바꾼다. `record_qa.py` 가 main 에 들어올 때까지 6.1절 7단계를 "미실행" 으로 표시한다.
- [ ] P0-2① `hospital-full-acceptance-v1.json` 을 실제 판정선으로 써서 frozen 으로 머지한다. 촬영 회차보다 먼저다.
- [ ] P0-2② `tools/evidence.py from-run` 을 더한다. `tests/test_evidence.py` 에 골격 생성 시험.
- [ ] P0-2③ 골든 SHA 4개에 `v0.5.0-rc.N` 태그와 `evidence/deployments/` 기록.
- [ ] P0-2④ `protocol.schema.json` 에 `supersedes`·`correction_reason`. `tests/test_evidence.py` 갱신.
- [ ] P0-3 `docs/architecture/exception-outcomes-v1.md`(as-built 표) + `architecture/README.md` 표 한 줄.
- [ ] P0-4 ADR 0003–0006 초안 + `adr/README.md` 표. 0001·0002 상태는 재범 결정.
- [ ] P0-5 `scenario.md` §10 에 as-built 행(4절 5항 13건).
- [ ] P0-6 `check_repository.py` 색인 완결성·날짜 접두 검사(허용 목록으로 시작). `docs/README.md` 운영 행에 `hospital-full.md` 등 런북 12개 추가.

**촬영 뒤(소규모 코드, L1·L2, 동작 변경은 L3)**

- [ ] P1-1 `_last_tag` 초기화 + `_on_tag` stamp·kind 검사 + L1 시험. L3 한 바퀴.
- [ ] P1-2① `schemas/contract-v1.json` + `tests/test_contract_vocabulary.py`(글자 대조, 시험만).
- [ ] P1-3 교차 시험을 13 토픽·검증 규칙까지 확장, `v` 2, README 표 갱신, `pouch_request` 처리. L3.
- [ ] P1-4① 웹이 src ROS-free 모듈을 import, 사본 삭제. ③ 주문 표 키 (epoch, order_id). ④ `api.md` `events` 정리, `test_contract_doc.py` 확장.
- [ ] P1-4② `/orchestrator/state` 메시지·발행(계약 v1.2 제안). — 재범 결정 뒤 백엔드.
- [ ] P1-5 `config/profiles/` + `P3_PROFILE` loader + `boot_check` 필수 키 게이트.
- [ ] P1-6 `TripConfig` 파라미터 노출, Dispense 시한, `deck_slots` 기본값 결정(3 또는 5), `/clock`·`holding` 계약 문장 정리.
- [ ] P1-7 `tools/check_local.sh`, `ci.yml` 브랜치 필터 제거·접두 검사, CODEOWNERS.

**발표 뒤(구조)**

- [ ] P2-1 `pharmacy_db` 노드 분리, preset 데이터화, `rokey_p3_common` 패키지.
- [ ] P2-2 `p3sim/app.py`, `hospital_main.py` 정리, 인자 표 자동 생성.
- [ ] P2-3 STAT 경계 ADR + 트랜잭션·fence 결함 L1 수정.
- [ ] P2-4 다중 AMR 경계 ADR + 계약 v1.2 초안.

## 4. 근거 요약 (갈래별 관측)

검토자가 다시 볼 수 있게 갈래별 굵은 관측만 적는다. 행 번호는 `c99f119` 기준이다.

### 4.1 배송 계약 ↔ orchestrator

- 계약 2.6 이벤트 26 = `Event.msg` 26. `RESET_BEGIN` 만 계약 10절 v1.1 목록(794행)에 없다.
- 계약에 있고 코드에 없는 것: `/clock` 정지 감시, `holding` 판정, `Deliver` feedback(`publish_feedback` 없음), `dispenser/status` 변화 시 발행(1 Hz 타이머만, `queue_length` 0 고정), `/amr_1/base/docked` 소비자.
- 코드에만 있는 것: 재도킹(`_undocked`·`redock_*`), 늦은 배출 채택(`_adopt_late_dispense`), `observation_guard`, `DELIVERING` goal 의 `zone_id`, `/orchestrator/check_container`. ADR 0001 대조 1(묶음 다음 침상)은 코드가 고쳤는데 ADR 은 미해결로 남았다.
- 종료 상태 정의 2벌: `terminal_states.py` 는 SUCCESS 포함, `trip_fsm._TERMINAL` 은 DELIVERED 포함. `trip_succeeded` 는 시험 밖에서 안 쓰인다.
- 요청 수락의 `destination_id` 검사는 정규식뿐(`is_zone_id`), 계약 364행 "zones.yaml 에 있음" 과 다르다.
- `skeleton.launch.py` 는 4노드만이고 docstring 의 "config/ 로 옮긴다" 는 미이행. 계약 13·73·785행이 가리키는 `rokey_p3_bringup/config/` 는 없다.

### 4.2 sim README ↔ sim/standalone ↔ 어댑터

- 문서에 있고 코드에 없는 인자: pharmacy 의 `--tcp-speed`(README 1124행). 값이 어긋난 것: `--inlet-standoff` 기본(README 0.40, 코드 0.33), `--pouch-pool`(README "preset 에 없음", hospital preset 이 12 를 준다).
- README preset 표 5–6개, 코드 9개. `hospital-nav`·`hospital-full`·`hospital` 은 README 에 없다. `hospital_navigationv1.usda` 도 README 에 없다.
- `--workcell-layout` 을 주면 mode·scene·rail·belt·amr_start 를 덮어써서 README 158행 "명령줄 인자가 이긴다" 가 맞지 않는다.
- `sim/tests/test_pharmacy_stage.py` 는 README 예시를 실시간 파싱하지만, `test_isaac_json.py` 는 5ac8628 시점 사본이라 README 변경을 못 잡는다.
- contract vector 러너는 `dispense.json` 만 돌린다. `pick.json` 의 `at_end_vectors` 는 sim 에서 돌지 않는다.

### 4.3 STAT

- 계약 §9 의 T01–T36 은 시험 함수가 있다. 계획서 §10 의 ROS 타입·`/stat/*` 11 토픽·`enable_stat` 은 없다(계약이 범위 밖으로 명시).
- 코드에만 있는 이벤트 약 20종과 사유 코드 5종은 계약이 정하지 않았다. `invalid_request` 는 트랜잭션 전에 반환되어 이벤트가 안 남는다(계약 72행 "거부도 이벤트").
- `demo-0921-v2.md` 400행은 CLI 가 별 브랜치에 있다고 하지만 현재 트리에 있다.

### 4.4 web

- `test_contract_doc.py` 는 snapshot leaf 키·거부 코드·상수만 본다. 라우트·WS `type`·응답 본문은 안 본다. `walk()` 는 리스트 첫 원소만 본다.
- 프론트가 읽는데 서버가 안 내는 것: WS `events`, `robots[].goal_zone`(늘 null). `dev-fixture.json` 은 `accepting_requests`·`stage`·`robots` 가 없다.
- 늦은 수락: `send_delivery`·`call_reset` 은 5 s 뒤 실패를 돌려주지만 future 를 취소하지 않는다. 웹이 409·503 을 준 뒤 goal 이 실제로 돌 수 있다.
- 신선도를 벽시계(UTC)로 잰다(api.md 317–324행이 아는 차이).
- 코드 주석의 행 번호 참조 3곳이 낡았다(`main.py` 113, `state.py` 99, `alarms.py` 71).

### 4.5 기획 12편 ↔ 코드

- 시나리오 요구 중 없는 것: keepout·speed 필터 마스크(대신 `speed_governor`), 사람 인식 YOLO, Replicator, 예외 문서, 도크 5(코드 4).
- 시나리오가 "없다" 고 한 것이 있는 것: 간호사 화면(`nurse.html`, 요청 `postRequest` 포함).
- schedule 의 미이행: 9/22 protocol 동결, `hosts.yaml`, 예외 문서 초안, Replicator·YOLO 학습.
- 문서 간 모순 13건: 레일 축(2·3), AMR 대수·동결 시점(D5/D6 vs D7/D8), 레일 토픽 계약 반영(시나리오 미결정·schedule 결정됨), 도크·충전(5개 고정 vs 분산 무선), 벨트 출처(우리 벨트 vs 씬 컨베이어), 인증 방식(손 카메라 vs 참값), 묶음(병동)(핵심 vs C등급), 빈월드 범위(한 문서 안 2절 vs 0절), 호스트 배치(마스터1 Isaac vs master02), 도메인 번호(115/117 vs 117/118/119/120), 간호사 화면, `hospital-v2` 상태(L3 미확인 vs 한 번도 안 돎), 기획안 미개정(Nova Carter·AprilTag).
- 계획서가 요구했는데 없는 것: `MotionPermit`·custody·`ur5_path_validator`, `ComputePathThroughPoses`, `hospital_topology.yaml`(로더만), `scene_manifest.py`, 앵커 manifest, P7 전 항목, O0–O5 계측 profile.

### 4.6 런북·프로세스·CI

- 원격 태그: `v0.1.0`–`v0.4.0`(patch 포함 9개) + `assets/hospital-20260918`. `v0.4.0` 은 "빈월드 전 구간 통합" 이고 schedule 39행의 v0.4.0 판정(acceptance frozen)은 미충족. schedule 72행 patch 목록에 `v0.2.3`·`v0.3.1` 이 빠졌다.
- `evidence/runs` 7건 전부 pilot(pharmacy 6, hospital-refill 1 failed). frozen protocol 2, proposed 1(acceptance).
- 강제되는 것: run·frozen protocol 불변(`evidence.py check_immutable` + harness `--base`). 강제 안 되는 것: 브랜치 접두, ADR 번호·상태 전이, analysis 날짜, 색인 완결성, USD 변경 확인(CODEOWNERS 만), 봇 머지 조건(설정 파일 없음), 잔류 넷 확인(boot_check 밖).
- CI 는 세 workflow. `harness.yml` 이 `sim/tests`·ruff·`evidence validate` 를, `web-backend.yml` 이 pytest 를 돈다. 공통 규칙 네 줄과 다르다.

## 5. 한계·미실행

- 코드 실행·L3 없음. 행 번호는 감사 시점의 것이고 RC 머지로 바뀔 수 있다.
- P1-1 의 결함은 "가능한 경로" 다. 현장에서 발생한 관측은 없다.
- 담당은 이 문서가 정하지 않는다. #576 카드표에서 한다.
- 이 문서는 기존 결정을 바꾸지 않는다. `proposed` 를 `accepted` 로 올리는 것은 재범이다.
