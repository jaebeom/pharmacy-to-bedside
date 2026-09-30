# 계약: STAT S0 승인·접수·custody v1

STAT 는 응급 물품 항공 배송 제안([계획서](../planning/p3-stat-implementation-plan.md))의 이름이다. S0 는 계약과 stub 만 돌리는 첫 단계다.
custody 는 Pod 가 지금 어디에 있는지다. journal 은 물리 작업을 명령 전·후로 한 줄씩 남기는 원장 기록이다.

- 상태: proposed
- 시연 경로에 연결되지 않았다. `tools/demo_v2.sh`·`stub_loop.launch.py`·웹·`console_scripts`(`setup.py:24–29`) 어디에서도 `stat_*` 를 부르지 않는다. 실행 길은 `python3 -m rokey_p3_orchestrator.stat_cli` 하나다(`stat_cli.py:1–13`).
- 기준: main `f316197`(v1.1.0)의 `stat_intake.py`·`stat_ledger.py`·`stat_dispatch.py`·`stat_stub.py`·`stat_cli.py` 와 대조했다(2026-09-30). STAT 코드는 9/20(`9a00242`) 뒤 바뀌지 않았다.
- 담당 / 소비자 / 이슈: orchestration(신규 파일만) / 합성 입력 CLI·시험. 웹·ROS 소비자는 아직 없다 / #299
- 버전 / 대체 계약: v1 / 없음. [배송 한 바퀴 v1](delivery-contract-v1.md)을 바꾸지 않는다
- 요구사항 / 완료 조건: [STAT 계획서](../planning/p3-stat-implementation-plan.md) §19.1 의 1–5. 계획서는 proposed 이며 이 문서도 그렇다.
  완료 = 아래 "검증" 표의 시험이 ROS 없이(L1) 통과하고, 정상 한 바퀴와 crash 복구 하나를 CLI 로 재현할 수 있다.

**이 문서가 정하는 것**: S0 의 객체 경계, 상태 축, 승인 대조, 멱등 접수, 물리 작업 journal 과 commit 조건, crash 경계별 복구,
fence, 취소, 영속 저장. 이름은 순수 파이썬 모듈(`rokey_p3_orchestrator/stat_*.py`)의 상수다.
**정하지 않는 것**: ROS 타입·토픽·QoS(계획서 §10 은 제안이다. `rokey_p3_interfaces` 추가는 v0.3.0 태그 뒤 맞춘다),
웹 표시, 본선 reset barrier 참여, 실제 장치, 합격선. v1.1.0 에도 `rokey_p3_interfaces` 에 STAT 타입은 없다.

S0 의 장치는 전부 stub 이다. 여기서 "관측"은 stub 세계가 낸 표본이며 센서 정확도가 아니다. L3 는 미실행이다.

## 1. 객체

| 객체 | 만드는 쪽 | 뜻 | 뜻하지 않는 것 |
| --- | --- | --- | --- |
| `EmergencyObservation` | 합성 입력기 | 병실 이상 징후 표본(방·침상·라벨·source·boot·seq) | 출고 권한, 진단 |
| incident | 원장 | 같은 방·침상의 관측을 시간창 안에서 묶은 사건. 상태 `ACK_REQUIRED` | 승인 |
| `ApprovalRecord` | 합성 승인 게이트웨이(원장의 별도 표) | 승인자 역할·대상·kit·수량·목적지·만료·revision | 요청 안의 `approved=true` |
| `StatOrder` | 원장(접수 시) | 승인에 결합된 시험 물품 1개의 운송 작업 | 치료 적절성 판단 |
| operation | 원장 | 물리 작업 1회. id = `<order_id>/<kind>` | 명령 ACK |
| Pod | 원장(처음 한 번 seed) | 재고 1개. kit·품질·custody·예약·보류 | |

관측은 사건만 만든다. 주문은 승인 레코드가 있어야만 생긴다. 무응답 시간이 지나도 승인으로 바뀌지 않는다.
시험 제품 ID 는 `SIM-KIT-*` 다(`stat_cli.py:29`).
ID 형식은 incident `INC-0001`, 주문 `STAT-0001`, op `<order_id>/<kind>` 다(`stat_intake.py:94·194`, `stat_dispatch.py:186`).
허용 승인자 역할은 합성 역할 `synthetic_charge_nurse` 하나다(`stat_intake.py:21`). 실제 의료진 권한 체계가 아니다.

## 2. 상태 축

한 축으로 다른 축을 추론하지 않는다.

| 축 | 값 | 바뀌는 때 |
| --- | --- | --- |
| 주문 | `ACCEPTED · RESERVED · PREPARING · LOADED · IN_TRANSIT · HANDOVER · DELIVERED · FAILED · CANCELLED · EXPIRED · PAUSED_RECONCILE` | 접수, 예약, commit, 거부, 취소 |
| Pod custody | `SOURCE · PICKUP_STAGE · GRIPPER · DRONE · RECEIVER · RETURN_STATION · UNKNOWN` | **fresh 관측으로만**. 명령 뒤 확인하지 못하면 `UNKNOWN` |
| Pod 품질 | `QUALIFIED · QUARANTINED · UNKNOWN` | seed. S0 에서 바꾸는 경로 없음 |
| 임무 | `NOT_STARTED · ACTIVE · CLOSED · FAULT` | 비행 intent, 복귀 commit·실패 |

- `DELIVERED` 는 Pod 가 목적지 수납부에 있고 기체와 분리된 것이 관측된 상태다. 임무 종료(`CLOSED`)와 따로 기록한다.
  복귀가 실패해도 `DELIVERED` 는 되돌리지 않는다(임무만 `FAULT`).
- `UNKNOWN` 은 빈 곳·정상·성공이 아니다. 명령 전 위치를 그대로 두지 않는다.
- `DISPENSE·LOAD·RELEASE` 뒤 결과를 확정하지 못하면 custody 는 fresh 관측이 있으면 그 위치, 없으면 `UNKNOWN` 이다.
  주문은 `PAUSED_RECONCILE` 이다.
- S0 에서 쓰지 않는 값: custody `GRIPPER·RETURN_STATION`(stub 에 팔 파지·회수 장소가 없다), 품질 `QUARANTINED·UNKNOWN`.

## 3. 승인 대조와 접수

접수 요청: `request_id, incident_id, approval_id, approval_revision, subject_ref, kit_id, kit_revision, destination_id`.
빈 문자열 필드나 64자를 넘는 필드가 있으면 `invalid_request` 다(`stat_intake.py:23·164–165`). 접수는 다음 순서로 보고 첫 실패를 거부 사유로 낸다.

| 순서 | 조건 | 거부 사유 |
| --- | --- | --- |
| 1 | 같은 `request_id` 로 이미 접수됨 | 내용 해시 같음 → `REPLAY`(같은 ticket), 다름 → `request_conflict` |
| 2 | incident 가 있다 | `incident_unknown` |
| 3 | 승인 레코드가 있다 | `approval_missing` |
| 4 | revision 이 지금 것과 같다 | `approval_revision_mismatch` |
| 5 | 철회되지 않았다 | `approval_revoked` |
| 6 | 발급 시각 이후다(주입한 wall clock) | `approval_not_yet_valid` |
| 7 | 만료 전이다 | `approval_expired` |
| 8 | 승인자 역할이 허용 목록에 있다 | `approver_not_authorized` |
| 9 | 승인의 incident·대상·kit·kit revision·목적지가 요청과 같다 | `incident_mismatch · subject_mismatch · kit_mismatch · destination_mismatch` |
| 10 | 그 승인으로 만든 주문이 없다(승인 1건 = 주문 1건) | `approval_consumed` |
| 11 | 원장 쓰기가 성공했다 | `ledger_unavailable` |

- 결과 `disposition`: `ACCEPTED · REPLAY · REJECTED`. `ACCEPTED` 는 원장에 기록됐다는 뜻이지 출고가 아니다.
- 내용 해시는 `request_id` 를 뺀 요청 필드의 정렬된 JSON 의 SHA-256 이다.
- 거부는 멱등 키를 묶지 않는다. 같은 요청을 고쳐 다시 보내면 다시 판단한다.
- 거부는 `STAT_ORDER_REJECTED` 이벤트로 남긴다(`stat_intake.py:170–171`). `invalid_request` 는 원장을 열기 전에 돌려주고, `ledger_unavailable` 은 트랜잭션이 되돌려진다. 그래서 이 둘은 이벤트가 남지 않는다(`stat_intake.py:164–165·173–174`).
- 같은 사건을 여러 번 보내면 incident 의 관측 수만 늘고 주문은 생기지 않는다. 같은 source·boot·seq 표본은 한 번만 센다.
  같은 방·침상의 관측이 기존 incident 의 [처음 − 300 s, 마지막 + 300 s] 안이면 그 incident 로 묶는다.
- 승인 레코드는 같은 approval_id 에 **새 revision** 으로만 다시 쓸 수 있다. 같은 revision 을 다시 쓰면 거부한다(철회 표시가 풀리지 않게).
- S0 승인 레코드는 수량 1 이고 만료가 발급 뒤여야 한다. 아니면 기록하지 않는다(`ValueError`, `stat_intake.py:111–112`).

## 4. 물리 작업 journal

주문 하나는 다음 작업을 이 순서로 한 번씩만 가진다. 재시도 예산은 모두 0 이다.

| kind | 전 → 후(관측으로 확인) | commit 뒤 주문 |
| --- | --- | --- |
| `DISPENSE` | Pod `SOURCE` → `PICKUP_STAGE` | `PREPARING` |
| `LOAD` | Pod `PICKUP_STAGE` → 기체(`DRONE`), 기체는 도크 | `LOADED` |
| `FLY` | 기체 도크 → 주문 목적지, Pod 는 기체 | `HANDOVER` (intent 때 `IN_TRANSIT`) |
| `RELEASE` | Pod 기체 → 목적지 수납부(`RECEIVER`) | `DELIVERED` |
| `RETURN` | 기체 → 도크 | 주문 유지, 임무 `CLOSED` |

operation 상태: `INTENT → SENT → COMMITTED`, 또는 `FAILED`, `RECONCILE`.

0. **사전 확인**: 대상(Pod 또는 기체)을 새로 관측한다. fresh 하지 않거나 "전" 상태가 아니면 명령 없이 기다린다
   (`observation_unavailable · precheck_mismatch`). 사유가 바뀔 때만 `STAT_ORDER_WAITING` 을 남긴다.
1. **INTENT**: 명령 전에 op id·generation·command seq·사전 관측의 boot·seq(하한)를 원장에 쓴다. 쓰기가 실패하면 명령을 보내지 않는다.
2. **SENT**: 장치 ACK 를 기록한다. ACK 는 완료가 아니다.
3. **COMMIT**: 장치 결과가 오면 관측을 새로 받는다. 관측이 fresh 이고 "후" 조건과 맞을 때만 custody·주문을 한 트랜잭션으로 바꾸고 이벤트를 같은 트랜잭션의 outbox 에 쓴다.
   장치 결과만으로는 commit 하지 않는다. 결과는 관측을 받을 계기일 뿐이다.
4. 결과가 시한 안에 오지 않거나 응답이 사라지면 `RECONCILE` 로 간다. 재전송하지 않는다.
   시한은 `result_timeout_s`(기본 5 s, monotonic)다(`stat_dispatch.py:33·228–229`).

**fresh 관측**: 나이가 `obs_max_age_s`(기본 1.0 s) 이하다. INTENT 때와 같은 source boot 이면 seq 가 하한보다 커야 한다.
장치가 재부팅되면(boot 변경) 나이만 본다. 같은 seq 반복·없는 관측·오래된 관측은 fresh 가 아니다.
stub 은 같은 호스트의 시계로 표본 시각을 찍는다. 호스트가 다른 장치의 시각을 이렇게 빼지 않는다(계획서 §15.1).

**대조(RECONCILE)**: 장치에 op id 로 묻고 관측을 새로 받는다.

| 관측 | 장치 답 | 처리 |
| --- | --- | --- |
| fresh, "후" 와 일치 | 무엇이든 | commit |
| fresh, "전" 그대로 | `UNKNOWN_OPERATION`(받은 적 없음) | **같은 op id** 로 한 번 재전송. 장치는 op id 로 멱등하다 |
| fresh, "전" 그대로 | `FAILED` | op `FAILED`, 주문 `FAILED` |
| fresh, "전" 그대로 | `ACCEPTED` | 기다린다 |
| fresh, "전" 그대로 | `APPLIED` 또는 `EXECUTION_UNKNOWN` | 관측 위치를 custody 로 기록, 계속 `PAUSED_RECONCILE`. 새 명령 없음 |
| fresh, 제3의 위치 | 무엇이든 | 관측된 위치를 custody 로 기록, 주문 `PAUSED_RECONCILE`(`pod_mismatch`) |
| 없음·오래됨 | 무엇이든 | 계속 `PAUSED_RECONCILE`. Pod 를 움직이는 op 면 custody `UNKNOWN` |

재전송 횟수를 세는 칸은 없다. 대조할 때마다 "전" 관측과 `UNKNOWN_OPERATION` 이 겹치면 같은 op id 로 다시 보낸다(`stat_dispatch.py:256–257`). 장치가 op id 로 멱등하므로 적용은 한 번이다(`stat_stub.py:118–123`).
`PAUSED_RECONCILE` 은 매 tick 다시 대조한다. 새 Pod 출고·대체 주문을 자동으로 만들지 않는다.
`DISPENSE` 가 확정되지 않으면 픽업 스테이지도 관측해 예약하지 않은 Pod 가 있으면 그 Pod 의 위치를 기록하고 `RECONCILE` 보류를 건다(잘못된 Pod).

**목적지 확인**: 예약할 때(출고 전) 목적지 스테이션 관측이 fresh 이고 태그가 맞고 수납칸이 비어 있어야 한다(계획서 §12.2).
아니면 `destination_not_ready` 로 기다리고 출고하지 않는다.

**예약**: 기체가 1대라 진행 중인 주문이 있으면 예약하지 않고 기다린다(`stat_dispatch.py:135–136`).
맞는 Pod(같은 kit·revision, `QUALIFIED`, `SOURCE`, 예약·보류 없음)가 없으면 주문은 `FAILED`(`no_qualified_pod`)다(139–143).

**인계 전 확인**(`RELEASE` INTENT 전): 같은 조건에 더해 기체가 그 스테이션에 도킹해 있어야 한다. 아니면 해제하지 않고 기다린다.
기체가 다른 스테이션에 있으면 `FLY` commit 에서 `destination_mismatch` 로 주문 `FAILED`, Pod 는 `DRONE` 에 `RECOVERY_REQUIRED` 로 남고 해제 명령은 0 건이다.

**단계별 승인 재확인**: `DISPENSE`·`LOAD`·`FLY`·`RELEASE` 전마다 승인을 다시 본다(`stat_dispatch.py:111–117·123–132`).
만료는 `DISPENSE` 전에만 본다. 출고 전 만료는 `EXPIRED` 다. 철회는 어느 단계 전이든 `CANCELLED` 다.
그 밖의 승인 문제(권한·발급 전 등)는 `FAILED` 다. 비행 뒤 철회는 해제를 막고 Pod 를 실은 채 복귀한다.

## 5. crash 경계와 재시작

재시작 순서: 원장 열기 → generation +1 을 먼저 기록 → `INTENT`·`SENT` 인 op 를 모두 `RECONCILE` 로, 그 Pod 의 custody 를 `UNKNOWN` 으로 → 위 표로 대조.
재시작은 재고·Pod·op 를 seed 값으로 덮지 않는다. seed 는 Pod 표가 비었을 때만 한다.

| crash 지점 | 원장에 남은 것 | 재시작 뒤 |
| --- | --- | --- |
| 승인 기록 뒤, 접수 전 | 승인 | 같은 요청 재전송 → `ACCEPTED` 한 번 |
| 접수 기록 뒤, 응답 전 | 주문 | 재전송 → `REPLAY`, 같은 ticket |
| INTENT 뒤, 명령 전 | op `INTENT` | 장치 `UNKNOWN_OPERATION` + 관측 "전" → 같은 op id 로 한 번 전송 |
| 장치 적용 뒤, 결과 기록 전 | op `SENT` 또는 `INTENT` | 관측 "후" → commit. 두 번째 적용 없음 |
| 관측 뒤, commit 전 | op `SENT` | 다시 관측 → commit 한 번 |

## 6. fence

fence 는 낡은 명령과 결과를 막는 칸막이다. 더 큰 generation 이 나온 뒤의 작은 generation 명령은 적용하지 않는다.

- 명령은 `epoch · generation · op id · command seq` 를 싣는다. stub 장치는 본 적 있는 가장 큰 generation 보다 작은 명령을 `stale_generation` 으로 거부한다.
  거부를 받은 실행기는 상태를 바꾸지 않고 `STAT_COMMAND_FENCED` 만 남긴다.
- 결과는 지금 기다리는 op 의 id·epoch 와 같을 때만 계기로 쓴다. 다른 op·epoch 의 결과, 끝난 op 의 늦은 결과는 버리고 `STAT_STALE_RESULT` 이벤트만 남긴다.
  결과만으로는 commit 하지 않으므로 늦은 결과가 새 주문을 끝내지 못한다.
- S0 의 epoch 는 원장 생성 때 1 이다. 본선 reset barrier 참여는 이 계약 밖이다(계획서 §15.2, 별도 계약 개정).

## 7. 취소

| 취소 시점 | 처리 |
| --- | --- |
| 출고 명령 전 | 예약 반납, `CANCELLED` |
| op 진행 중 | 그 op 가 끝나거나 대조될 때까지 기다린 뒤 다음 op 를 만들지 않는다 |
| Pod 가 `SOURCE` 밖 | `CANCELLED`, Pod 는 관측된 custody 그대로 `RECOVERY_REQUIRED` 보류. 원장만 되돌리지 않는다 |
| 기체가 도크 밖 | 해제 없이 `RETURN` 으로 복귀 |
| `DELIVERED` 뒤 | 거부(`already_delivered`). 회수는 새 승인 작업이다 |
| 다른 종료 상태(`FAILED`·`CANCELLED`·`EXPIRED`) 뒤 | 거부(`already_done`). 모르는 주문이면 `order_unknown` 이다(`stat_dispatch.py:75–86`) |

`RECOVERY_REQUIRED` Pod 는 예약 대상이 아니다. S0 에서 회수 작업은 사람 절차이며 자동 명령이 없다.

## 8. 영속 저장

- 표준 라이브러리 `sqlite3` 파일 하나(`journal_mode=WAL`, `synchronous=FULL`). 상태 변경과 outbox 이벤트는 같은 트랜잭션이다.
  외부 DB 서비스·메시지 플랫폼은 쓰지 않는다. 저장소에는 durable 저장 수단이 없었다(run 기록은 JSONL, 원장은 메모리).
- stub 세계(장치 쪽 물리 상태와 장치 op 기록)는 원장과 다른 파일이다. 오케스트레이터 재시작이 물리 상태를 되돌리지 않는다.
- 원장 쓰기가 실패하면 그 뒤의 비가역 명령을 보내지 않는다.

## 9. 검증

| 시험 | 계획서 T | 확인하는 것(함수 반환값이 아니라 stub 세계의 적용 횟수·원장·이벤트) |
| --- | --- | --- |
| 승인 없는 사건 | T01 | incident 만, 출고 적용 0 |
| 긴 무응답 | T02(L1 부분) | 시계를 앞당겨도 주문 0, incident `ACK_REQUIRED` |
| 만료·철회·권한·revision | T03 | 해당 사유로 거부, 단계별 재확인 |
| 같은 사건 반복 | T04 | 관측 수만 증가, 주문 0 |
| 대상·목적지 불일치 | T07 | 거부 |
| 같은 요청 재전송·다른 내용 | T09 | 같은 ticket·출고 1 / `request_conflict` |
| 출고 뒤 ACK 소실 | T10 | 대조 후 출고 적용 1 |
| 인계 뒤 결과 소실 | T11 | 해제 적용 1, commit 1 |
| 경계별 crash + 실제 프로세스 재시작 | T12 | 이력 복구, 재고 seed 로 덮지 않음, 적용 1 |
| 오래된 generation·epoch·op 결과 | T14·T36(L1 부분) | 장치 거부 / 상태 변화 없음 |
| 관측 없음·반복 seq·오래된 표본 | T18(L1 부분) | custody `UNKNOWN`, commit 없음, 다음 단계 적용 0 |
| 잘못된 Pod·목적지, 목적지 수납칸 점유 | T05·T06(L1 부분) | 탑재·해제 적용 0, 관측된 위치 기록, 점유 중 출고·해제 0 |
| 인계 뒤 복귀 실패 | T32(L1 부분) | `DELIVERED` 유지, 임무 `FAULT` |
| 원장 쓰기 실패 | — | 명령 0 |
| 출고 전·후 취소, 늦은 결과 | — | 실제 custody 대로 종료, 새 주문 오염 없음 |

T08·T13·T15–T17·T19–T31·T33–T35·T37–T44 는 S0 에서 미구현이다. "L1 부분"은 ROS 통신·물리 없이 논리만 본 것이다.
계획서가 L2 로 적은 T09–T12 도 여기서는 ROS 없이(L1) 본 것이다. ROS L2 와 L3 는 미실행이다.
v1.1.0(`f316197`)에서 `test_stat_intake.py`·`test_stat_dispatch.py`·`test_stat_cli.py` 를 ROS 없이 돌려 63건 통과했다(로컬 macOS, Python 3.11, 2026-09-30).
CLI 손 재현([런북](../runbooks/stat-s0-stub.md))은 이번에 미실행이다.

## 10. 변경·롤백

신규 파일만 더하므로 본선 동작과 기본 launch 는 바뀌지 않는다. 되돌리려면 STAT 파일을 지운다.
ROS 타입으로 옮길 때는 이 문서의 이름을 그대로 쓰고, 바꾸면 이 문서를 먼저 고친다.
