# 관제 화면 — 주문 한 건의 전 과정 점검표 (오프라인)

- 무엇: 재범 지시(9/24 17:0x) "관제가 전체 프로세스를 다 알고 있어야 한다" 에 대한 점검이다. 주문 한 건의 단계마다 지금 관제 화면에 보이는지, 어느 `/events` 또는 snapshot 필드로 아는지 적는다.
- 기준: main `8caa155`(카드 기준 `874b0a3` 이후), `web/api.md`, `web/frontend/js`, `src/rokey_p3_interfaces/msg/Event.msg`(이벤트 26개). 실물 회차가 아니라 코드와 계약으로 본 것이다.
- 빠진 것은 "프론트만으로 됨"과 "백엔드 필드 필요"로 나눴다. 프론트만으로 되는 것은 같은 PR 에서 고친다. 오케스트레이터는 바꾸지 않고, 기존 26 이벤트만 쓴다.

## 화면 이름

| 이름 | 어디 |
| --- | --- |
| 스텝퍼 | 개발자 화면 트립 칸의 17단계(`status_view` 원문 `phase_label`) |
| 타임라인 | 개발자 화면 오른쪽 아래. 현재 epoch 의 이벤트 전부 |
| 조제기 칸 | 개발자 화면 가운데. 슬롯 재고, `PAUSED`·`보충 중`, 보충 흐름 띠, 마지막 보충 줄, 벨트·보관함 줄 |
| 평면도 | 개발자·간호사·촬영 화면. `robots[]` 자세와 목적지(`trip.destination_id`) |
| 간호사·촬영 | `nurse.html`(4단계), `nurse.html?film=1`(7단계, 서버 `snapshot.stage`) |
| fleet | 따로 된 fleet 칸은 없다. AMR 은 평면도 점과 트립 칸의 `robot_id` 로만 보인다 |

## 단계별

| # | 단계 | 아는 곳(이벤트·필드) | 개발자 화면 | 간호사·촬영 | 판정 | 빠진 것 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 접수 | `REQUEST_ACCEPTED`(detail JSON: mode·목적지·주문), `trip.*` | 스텝퍼 `적재 위치로 이동`, 타임라인, 트립 칸 모드·목적지·주문 | 배너 `요청 접수`, 큐 `지금` | 보임 | — |
| 2a | M0609 보충 — 시작·끝 | `REFILL_REQUESTED`·`REFILL_DONE`, `dispenser.paused`·`refilling`·`refilling_item_ids` | 조제기 칸 `PAUSED`·`보충 중`, 보충 흐름 띠(정지·보충 중·재개), 타임라인 | 간호사 띠(보충 중·재개 대기), 촬영 `보충` 칸(이 트립 약만, §1.7) | 보임 | — |
| 2b | 보충 — round·module | `REFILL_DONE.refill.kind`(cylinder·module)·`target`(round·module) | 조제기 칸 "마지막 보충" 줄(원통형 → 원형 수납통 등), 타임라인 요약 | 없음 | 보임(백엔드 필드 뒤) | 보충 **중** 대상은 `REFILL_REQUESTED` 에 없다. 백엔드 필드는 `dispenser.refill_targets`(6f1af52)다. 보충 흐름 띠에 "drug-ibu → A · 원통형 → 원형 수납통" |
| 2c | 보충 — 약통 QR 확인 | 26 이벤트·snapshot 어디에도 없다(`refill` 필드는 item·slot·kind·cell·target·seed·draw·clearance) | 조제기 칸 "약통 QR" 줄(판독·못 읽음·tag·나이) | 없음 | 보임(백엔드 필드 뒤) | 백엔드 `dispenser.container_read`(6f1af52). 약통 확인을 켠 기동에서만 온다. **허용·거부 판정: 없음**. 토픽이 없다. |
| 3 | 조제 배출 | `AMR_DOCKED_LOAD`, `DISPENSED`, `dispenser.slots[].count` | 스텝퍼 `배출`·`벨트 이송`, 슬롯 재고 수, 타임라인 | 촬영 `조제` | 보임 | — |
| 4 | 벨트 끝 도착 | `POUCH_AT_END`, `belt.at_end`·`occupied`·`order_id` | 스텝퍼 `벨트 끝 픽`, 벨트 줄 `AT_END` | 촬영 `조제`(지금: 벨트 끝 픽) | 보임 | — |
| 5a | AMR 집기 | `PICK_ATTEMPT`(재시도는 개수), `POUCH_PICKED` | 스텝퍼 `픽`, 타임라인에 시도마다 한 줄 | 촬영 `집기` | 부분 | 몇 번째 시도인지 한눈에 없다 → **프론트만으로 됨**(PICK_ATTEMPT 개수를 트립 칸에) |
| 5b | 트레이 적재 | `POUCH_LOADED`, `LOAD_DONE`, `ARM_HOME` | 스텝퍼 `적재`·`적재 끝`·`팔 홈` | 촬영 `집기` | 보임 | — |
| 6 | 출발·이동(목적지) | `DEPARTED`, `ARRIVING`, `trip.destination_id`, `robots[]` | 스텝퍼 `병동으로 이동`·`병동 도착 직전`, 평면도 점·목적지 고리 | 배너 `배송 중 → C1 병실 D1`, 평면도 | 보임 | Nav 목표 구역(`goal_zone`)은 늘 null(§1.6). 목적지는 요청의 것으로 그린다 |
| 7 | 도착·인증 | `ARRIVED`, `AUTH_OK`·`AUTH_FAIL`(알람 AUTH_FAIL) | 스텝퍼 `인증`·`인증 실패`, 알람, 타임라인 | 간호사 `✓ 환자 확인됨`·`✕ 실패` 칩(#626), 촬영 `도착` | 보임 | 개발자 트립 칸 주문 줄에는 인증 결과 칩이 없다. **프론트만으로 됨**이다. 간호사 칩을 개발자 주문 줄에도 둔다. |
| 8 | 내려놓기 | `POUCH_DETECTED`, `POUCH_PLACED`, `CABINET_LOCKED`, `cabinet.present`·`order_id` | 스텝퍼 `보관함 배달`·`보관함 잠김`, 보관함 줄, 타임라인 | 촬영 `도착` | 보임 | — |
| 9 | 복귀 | `ORDER_DONE`(결말은 `orders[].outcome`), `RETURNED` | 스텝퍼 `주문 닫힘`·`도크로 복귀`, 주문 상태, 평면도 점 | 배너 `복귀 중`, 큐 `전달 완료` | 부분 | 복귀 중에도 평면도 목적지 고리가 병상에 남는다. 어느 도크로 가는지 필드가 없다. **백엔드 필드 필요**다. 복귀 도크 zone 또는 `goal_zone` 이다. |
| 10 | 도킹(충전 대기) | `DOCKED`(트립이 닫힌다) | 트립 칸 `대기 중` 만. 충전 표시 없음 | 간호사 `배송 로봇 대기 중`, 촬영 `대기`·끝난 배송 | 빠짐 | **프론트만으로 됨**: 이 epoch 에서 그 AMR 의 마지막 트립 이벤트가 `DOCKED` 면 `충전 중 ⚡` 배지. 배터리 수치는 모델이 없어 넣지 않는다 |

## 여러 AMR(fleet)

| 무엇 | 지금 | 판정 |
| --- | --- | --- |
| AMR 마다 위치 | `robots[]` 배열, 평면도에 전부 그린다 | 보임 |
| AMR 마다 상태(주행·도킹·충전) | 트립은 한 번에 하나(`trip.robot_id`)만 온다 | 부분이다. 이벤트의 `robot_id` 로 AMR 마다 마지막 이벤트를 모을 수 있다. 프론트만으로 된다. 이 PR 은 `충전 중 ⚡` 에만 쓴다. |

## 이 PR 에서 고치는 것(프론트만)

1. 10 도킹: `충전 중 ⚡` 배지 — 개발자 트립 칸 대기 상태, 간호사 지금 배송, 촬영 대기 배너, 평면도 AMR 이름표.
2. 5a 집기: 트립 칸에 `집기 시도 N회`(PICK_ATTEMPT 개수, 2회부터).
3. 7 인증: 개발자 트립 칸 주문 줄에 `✓ 환자 확인됨`·`✕ 환자 확인 실패`.

## 백엔드에 넘길 것

백엔드가 snapshot 이름을 제안했다(9/24). 프론트는 이견이 없다.

| 항목 | 제안 필드 | 프론트 |
| --- | --- | --- |
| 2b 보충 중 대상 | `dispenser.refill_targets` = [{item_id, slot_name, kind, target}] | 붙였다(보충 흐름 띠) |
| 2c 약통 QR | `dispenser.container_read` = {tag_id, status, stamp, wall, age_wall_s} 또는 null | 붙였다(조제기 칸 약통 QR 줄). 허용·거부 판정: 없음 |
| 9·10 도킹 | `robots[].docked` = true·false·null | **이 PR 에서 먼저 쓴다.** 없거나 null 이면 이벤트(마지막이 DOCKED)로 판정한다 |
| 9 복귀 도크 | 없음(이벤트에 없다) | `goal_zone` 은 계속 null 이다. 복귀 중 목적지 고리는 병상에 남는다 |
