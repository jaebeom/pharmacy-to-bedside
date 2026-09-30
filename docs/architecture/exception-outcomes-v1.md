# 예외 → 종료 상태 표 v1 (as-built)

상태: **현황 기록.** 기준: main `f316197`(v1.1.0)의 코드를 읽어 적었다(2026-09-30). 첫 판은 `874b0a3`(9/25)였다. 새 설계가 아니다. 코드와 이 표가 다르면 코드가 맞다. 이 표를 고친다.

[계약 v1](delivery-contract-v1.md) 머리의 "정하지 않는 것"·5절 끝·7절 끝, [`OrderStatus.msg`](../../src/rokey_p3_interfaces/msg/OrderStatus.msg) `reason`, [`PickPouch.action`](../../src/rokey_p3_interfaces/action/PickPouch.action) `outcome` 이 가리키는 "예외 문서"가 이 파일이다.
상태별 전이는 [ADR 0001](../adr/0001-orchestrator-trip-fsm.md)에 있다. 이 문서는 조건마다 끝을 한 표로 모은다. 계약 [5절](delivery-contract-v1.md#5-인터락)의 `HOLD_RETURN`·`redock_*`(도크 복귀 우선)도 이 표에 들어 있다.

## 1. 읽는 법

- **근거**는 main `f316197` 의 `src/rokey_p3_orchestrator/rokey_p3_orchestrator/trip_fsm.py` 줄 번호다. 다른 파일은 `파일:줄` 로 적는다.
- **종료 상태**는 `OrderStatus` 의 네 가지(`DELIVERED`·`HOLD_RETURN`·`ABORT`·`TIMEOUT`)다. FSM 은 `terminal_states.py:4–6` 의 셋과 자기 `DELIVERED`(100–101)로 닫는다. `SUCCESS`(`terminal_states.py:3`)는 evaluator 관측이다. 오케스트레이터가 내지 않는다(`OrderStatus.msg` 10–12행).
- 주문 하나를 닫을 때마다 `OrderState(state, reason)` 와 `ORDER_DONE` 이 함께 나간다(1354–1360).
- **`_close_all` 변환**(1370): `HOLD_RETURN` 으로 닫으려 해도 봉투가 아직 상판에 없는 주문(`ACCEPTED`·`DISPENSED`)은 `ABORT` 가 된다. reason 은 같다. 표에서 "실은 주문 `HOLD_RETURN` / 나머지 `ABORT`" 로 적은 줄이 이것이다.
- **재시도 횟수**(`TripConfig`, 163–173): `GoToZone` 거부는 2회까지다. 간격은 5 s 다. `Dispense` 호출은 3회다. 간격은 2 s 다. `PickPouch` 는 2회다. `ScanTag` 는 2회다. "N회째"는 이 한도에 닿은 때다.
- **도크 복귀 재시도**(168–169): 복귀가 실패(`not_arrived`·시한)로 끝난다. 그러면 3번 더 보낸다. 거부로 끝난 복귀는 이 재시도에 들지 않는다. 간격은 10·20·40 s(sim)다(#749).
- **시한**(`TripConfig`, 158–174, 모두 sim s): `GoToZone` 120(load·dock)·180(병동), `PickPouch` 60, `ScanTag` 30, 벨트 20, 트립 600. 액션 시한이 지나면 FSM 이 goal 을 cancel 한다. 그 goal 은 outcome `timeout` 으로 처리한다(541–544). 그 goal 의 늦은 결과는 token 으로 버린다(607–614).
- **기동 값**: 병원 `demo_v2.sh` 는 `belt_timeout_s` 60(144·465행), 한 바퀴 월드는 `deck_slots` 3(435행)을 준다. 표의 코드 기본과 다르다.

## 2. 재배차

| 항목 | as-built |
| --- | --- |
| 뜻(인터페이스) | `OrderStatus.msg` 13–14행: `HOLD_RETURN` 재배차 가능, `ABORT` 불가. `TIMEOUT` 은 적혀 있지 않다 |
| 자동 재배차 | **없다.** 오케스트레이터·웹·도구 어디에도 닫힌 주문을 다시 보내는 경로가 없다 |
| 손으로 다시 보내기 | 같은 `order_id` 는 리셋 전까지 `Deliver` 가 거부한다(`orchestrator_node.py:412–413` "이미 쓴 주문이다"). 리셋 뒤 `_reload_stores`(`orchestrator_node.py:606–614`)가 사용 표시를 비운다 |
| 상판에 남은 봉투 | 리셋이 상판 봉투 prim 을 지운다(계약 6절 2). 리셋 없이 다음 트립이 오면 FSM 은 남은 봉투를 모른다. 칸 번호는 트립마다 0 부터다(`_clear_trip`, 707) |

그래서 아래 표의 **재배차** 열은 이렇게 쓴다.

- "가능(뜻)": 봉투가 상판 칸에 남는다. 인터페이스 뜻으로는 재배차 대상이다. 지금은 리셋 뒤에야 같은 `order_id` 를 다시 보낼 수 있다. 리셋이 봉투를 지우므로 새로 배출한다. 상판 봉투를 **다시 쓰는** 재배차는 없다.
- "불가": 봉투가 없거나 어디 있는지 모른다. 새로 배출해야 한다.

## 3. 표

### 3.1 적재 (도크·벨트·상판)

| 조건 | FSM 상태 | 종료 상태 | reason | 재배차 | 근거 | 비고 |
| --- | --- | --- | --- | --- | --- | --- |
| 재고 없음 | `DOCKED_LOAD` | `ABORT` | `out_of_stock` | 불가 | 969–975, `dispenser_inventory.py:17` | `Dispense` 를 부르지 않는다 |
| 약품 ID 모름 | `DOCKED_LOAD` | `ABORT` | `unknown_item` | 불가 | 969–975, `dispenser_inventory.py:18` | 같음 |
| `Dispense` 3회째 거부 | `DOCKED_LOAD` | `ABORT` | 응답 `message`, 비면 `dispense_failed` | 불가 | 1154–1162 | reason 이 자유 문자열이다. 관측된 값: `pool_exhausted`(계약 10.2). 노드가 넣는 값: `no_server`(서버 10 s 안 보임, `orchestrator_node.py:850`)·`exception`(`:920`) |
| 배출 응답은 거부(시한)였는데 그 주문 봉투가 벨트에 있다 | `DOCKED_LOAD` | (닫지 않음) `DISPENSED` 로 받는다 | — | — | 959–962 → 1129–1143 | 방금 배출을 부른 그 주문일 때만이다 |
| 벨트 시한(기본 20 s) 안에 `at_end` 없음 | `WAIT_BELT` | `ABORT` | `belt_timeout` | 불가 | 987–988 → 1332–1338 | 그때 `belt.occupied` 면 다음 줄(막힘)로 이어진다(1335–1336) |
| 벨트 막힘 | `DOCKED_LOAD`·`WAIT_BELT` | 남은 미배출 주문 `ABORT` | `belt_blocked` | 불가 | 955–958·1336 → 1340–1347 | 이미 닫힌 주문의 봉투가 벨트에 남은 경우도 막힘이다(955–958). `LOAD_DONE` 을 내고 실은 것만 싣고 떠난다 |
| 상판 칸 없음 | `PICKING_BELT` | `ABORT` | `deck_full` | 불가 | 1000–1005 | goal 을 보내지 않는다. 봉투는 벨트에 남아 다음 주문이 벨트 막힘이 된다 |
| 벨트 픽 `PickPouch` `ok` | `PICKING_BELT` | (닫지 않음) `LOADED` | — | — | 1166–1172 | |
| 벨트 픽 `dropped` | `PICKING_BELT` | `ABORT` | `dropped` | 불가 | 1173·1176–1178 | 재시도 없음 |
| 벨트 픽 `not_detected`·`qr_mismatch`·`grasp_failed`·`timeout`·`rejected_interlock` 2회째 | `PICKING_BELT` | `ABORT` | outcome 그대로 | 불가 | 1173–1178 | 아직 실리지 않은 봉투라 `HOLD_RETURN` 이 아니다. 카메라 집기(병원 v1.1.0 기본)에서 `qr_mismatch` 는 봉투 QR 이 주문과 다름, `not_detected` 는 맞는 QR 을 못 읽음이다(`pick_permission.py:51–63`) |
| 벨트 픽 goal 거부·wrapper 취소 2회째 | `PICKING_BELT` | `ABORT` | `rejected`·`canceled` | 불가 | 1173–1178 | 7종 밖 값이다. 거부는 `orchestrator_node.py:845·859`, 취소는 `:898`(보내기 전 취소는 `:831`)이 넣는다 |

`dispense_while_dispatching`(기본 끔, `orchestrator_node.py:177`)이 켜지면 첫 `Dispense` 를 적재 이동과 같이 부른다(938–946). 그 응답은 도착 때 위 표대로 처리한다(1112–1119·1124–1127).

### 3.2 출발·주행

| 조건 | FSM 상태 | 종료 상태 | reason | 재배차 | 근거 | 비고 |
| --- | --- | --- | --- | --- | --- | --- |
| 적재 자리 = 도크(`load_at_dock`) | `DISPATCHING` | (닫지 않음) 곧바로 `DOCKED_LOAD` | — | — | 931–936 | `GoToZone(load)` 를 보내지 않는다. 노드가 `zones_file` 의 `load`·`dock_1` 자세가 같으면 켠다(`orchestrator_node.py:545–557`). 병원 두 zones 파일이 그렇다(#790). 그래서 아래 "적재 이동" 세 줄은 병원 기본에서 나오지 않는다 |
| 적재 이동 `GoToZone(load)` 2회째 거부 | `DISPATCHING` | `ABORT`(실은 주문 없음) | `goto_rejected` | 불가 | 1120–1121 → 1310–1314 → 1319–1322 | 서버 10 s 안 보임도 거부로 센다(`orchestrator_node.py:845`, `server_wait_s` 151) |
| 적재 이동 시한 120 s | `DISPATCHING` | `ABORT` | `goto_timeout` | 불가 | 1122 | |
| 적재 이동 `arrived=false` | `DISPATCHING` | `ABORT` | `goto_not_arrived` | 불가 | 1122 | 재시도 없음(Nav2 recovery 에 맡긴다) |
| 재도킹 `GoToZone(dock)` 2회째 거부 | `DISPATCHING`(재도킹) | `ABORT` | `goto_rejected` | 불가 | 1120–1121 → 1314 | 재도킹 중이어도 `redock_` 이 붙지 않는다(계약 5절) |
| 재도킹 시한 120 s | `DISPATCHING`(재도킹) | `ABORT` | `redock_timeout` | 불가 | 1122 | 지난 트립이 `DOCKED` 없이 끝났을 때만(924–929, 1376) |
| 재도킹 `arrived=false` | `DISPATCHING`(재도킹) | `ABORT` | `redock_not_arrived` | 불가 | 1122 | 같음 |
| 재도킹 도착 | `DISPATCHING`(재도킹) | (닫지 않음) | — | — | 1102–1107 | 다시 `DISPATCHING` 이다. `load_at_dock` 이면 그 자리에서 적재한다 |
| `pharmacy_only` 적재 끝 | `DEPARTING` 진입 | 실은 주문 `HOLD_RETURN` | `pharmacy_only` | 해당 없음(정상 완주) | 1014–1021 | 이상이 아니다. 웹은 `pharmacy_done` 으로 따로 보인다 |
| 출발 `GoToZone(정거장)` 2회째 거부 | `DEPARTING` | 실은 주문 `HOLD_RETURN` / 나머지 `ABORT` | `goto_rejected` | 가능(뜻) | 1183–1184 → 1314 | |
| 출발 goal 이 수락 전에 시한(180 s) | `DEPARTING` | 실은 주문 `HOLD_RETURN` / 나머지 `ABORT` | `goto_timeout` | 가능(뜻) | 1185 | 적재 이동과 **같은 문자열**이다(3.6) |
| 주행 시한 180 s | `TRANSIT` | 남은 주문 `HOLD_RETURN` / 나머지 `ABORT` | `transit_timeout` | 가능(뜻) | 1192 | 시한은 goal 을 보낸 순간부터다(1276) |
| 주행 `arrived=false` | `TRANSIT` | 같음 | `transit_not_arrived` | 가능(뜻) | 1192 | |
| 주행 goal wrapper 취소 | `TRANSIT` | 같음 | `transit_canceled` | 가능(뜻) | 1192 | FSM 이 스스로 cancel 한 goal 은 여기로 오지 않는다. 밖에서 취소된 때만이다 |

`GoToZone` 의 outcome 은 `arrived`·`not_arrived`·`canceled`(`orchestrator_node.py:897–902`), `rejected`(`:845·859`), `timeout`(FSM 시한 541–544)이다. 위의 `goto_`·`redock_`·`transit_` reason 은 모두 접두 + outcome 이다. 그래서 적재 이동·재도킹의 `goto_canceled`·`redock_canceled` 도 코드상 나올 수 있다.

### 3.3 인증

| 조건 | FSM 상태 | 종료 상태 | reason | 재배차 | 근거 | 비고 |
| --- | --- | --- | --- | --- | --- | --- |
| 읽었는데 정거장 인식표와 다름 | `AUTHENTICATING` | 이 정거장 주문 `HOLD_RETURN` | `auth_mismatch` | 가능(뜻) | 1196–1206 → 1324–1330 | 재시도 없음. `AUTH_FAIL`. 다음 정거장으로 간다. 정거장 ID 는 `pt-<환자>` 또는 `st-<zone>` 이다(766–770). 접두를 뗀 카메라 ID 도 같은 정거장이면 맞다(1197–1202, `f8341ba7`) |
| 못 읽음(`unreadable`·시한 30 s·거부·취소) 2회째 | `AUTHENTICATING` | 이 정거장 주문 `HOLD_RETURN` | `tag_unreadable` | 가능(뜻) | 1207–1210 → 1324–1330 | `AUTH_FAIL`. 다음 정거장. 스텁 L2 가 고정한다(`test_stub_station_scan.py`). 카메라 인증에서 `tag_standoff_m`·`tool_frame` 이 비면 팔이 곧바로 `UNREADABLE` 을 낸다(`arm_node.py:2018–2029`) |

### 3.4 놓기 (상판 → 보관함)

| 조건 | FSM 상태 | 종료 상태 | reason | 재배차 | 근거 | 비고 |
| --- | --- | --- | --- | --- | --- | --- |
| `PickPouch` `ok` | `DELIVERING` | `DELIVERED` | (빈 값) | — | 1214–1219 | `CABINET_LOCKED` 뒤 |
| `dropped` | `DELIVERING` | `ABORT` | `dropped` | 불가 | 1220·1223–1227 | 재시도 없음 |
| `not_detected` 2회째 | `DELIVERING` | `HOLD_RETURN` | `not_detected` | 가능(뜻) | 1220–1227 | 카메라 집기에서는 상판에서 이 주문 QR 을 못 읽은 것이다 |
| `qr_mismatch` 2회째 | `DELIVERING` | `HOLD_RETURN` | `qr_mismatch` | 가능(뜻) | 같음 | 카메라 집기에서는 읽은 봉투 QR 이 이 주문이 아닌 것이다 |
| `grasp_failed` 2회째 | `DELIVERING` | `HOLD_RETURN` | `grasp_failed` | 가능(뜻) | 같음 | |
| `timeout` 2회째 | `DELIVERING` | `HOLD_RETURN` | `timeout` | 가능(뜻) | 같음 | 봉투가 칸에 남았는지는 FSM 이 확인하지 않는다(3.6) |
| `rejected_interlock` 2회째 | `DELIVERING` | `HOLD_RETURN` | `rejected_interlock` | 가능(뜻) | 같음 | |
| goal 거부·wrapper 취소 2회째 | `DELIVERING` | `HOLD_RETURN` | `rejected`·`canceled` | 가능(뜻) | 같음 | 7종 밖 값 |

놓기 실패는 그 주문만 닫는다. 같은 정거장의 다음 주문은 이어서 놓는다.

### 3.5 트립 전체·복귀·리셋

| 조건 | FSM 상태 | 종료 상태 | reason | 재배차 | 근거 | 비고 |
| --- | --- | --- | --- | --- | --- | --- |
| 트립 600 s sim 초과 | `IDLE`·`RESETTING`·`RETURNING` 밖 | 닫히지 않은 주문 전부 `TIMEOUT` | `trip_limit` | 적혀 있지 않음 | 535–540 | `_close_all` 변환이 없다. 실은 주문도 `TIMEOUT` 이다. 진행 중 goal 을 cancel 하고 `RETURNING` |
| 복귀 `GoToZone(dock)` 2회째 거부 | `RETURNING` | (주문은 이미 닫힘) | — | — | 1232–1239 | `DOCKED` 없이 끝, `success=false`. 다음 트립이 재도킹부터 한다(1376, 924) |
| 복귀 시한 120 s·`arrived=false` | `RETURNING` | 같음 | — | — | 1240–1251 | 3번까지 10·20·40 s 뒤 다시 보낸다(#749). 매번 경고 한 줄과 `/p3/alerts` `DOCK_RETRY` 를 낸다(#757) |
| 복귀 재시도 3번 뒤에도 실패 | `RETURNING` | 같음 | — | — | 1252–1256 | 오류 한 줄 "도크 복귀 포기"와 `DOCK_GIVEUP` 을 내고 `DOCKED` 없이 끝낸다. 다음 트립 재도킹 |
| 복귀 goal wrapper 취소 | `RETURNING` | 같음 | — | — | 1257 | 다시 보내지 않는다(리셋·정지). `DOCKED` 없이 끝 |
| 복귀 도착 | `RETURNING` | 같음 | — | — | 1230–1231 | `success` 는 모든 주문 `DELIVERED` 이고 도착했을 때만(1374–1381) |
| 리셋 요청 | 어느 상태든 | 닫히지 않은 주문 `ABORT` | `reset_interrupted` | 불가 | 562–572 | 이전 epoch·이전 `request_id` 로 낸다. 이미 닫힌 주문은 덮지 않는다 |

### 3.6 알려진 모호함 (코드 그대로)

- `goto_timeout`·`goto_rejected` 는 적재 이동(`DISPATCHING`, `ABORT`)과 출발(`DEPARTING`, 실은 주문 `HOLD_RETURN`) 둘 다에서 나온다. reason 만으로 어느 쪽인지 모른다. 종료 상태와 이벤트 순서(`LOAD_DONE` 앞뒤)로 가른다.
- PickPouch reason `timeout` 은 세 곳에서 온다. 하나는 FSM 시한 60 s 다. 하나는 팔이 보낸 `timeout` 이다. 하나는 결과가 SUCCEEDED 가 아니거나 outcome 이 비고 `success=false` 인 경우다(`orchestrator_node.py:903–907`). reason 만으로는 가를 수 없다.
- 팔이 보낸 모르는 outcome(계약 11.4 의 `placement_unconfirmed`·`cancelled` 등)은 `dropped` 가 아니므로 1회 재시도한 뒤 그 문자열 그대로 닫힌다.
- 복귀 재시도 조건(1240)에 `failed` 가 있다. 노드는 `GoToZone` 결과에 `failed` 를 넣지 않는다(`orchestrator_node.py:897–902`). 그 칸은 쓰이지 않는다.
- `dispense_while_dispatching` 이 켜진 채 적재 이동이 실패하면 주문은 `goto_*` 로 `ABORT` 다(1122). 같이 부른 `Dispense` 의 늦은 응답은 버린다(`RETURNING` 에 처리기가 없다, 1259–1269). 그 봉투는 벨트에 남을 수 있다(해석). 병원 기본은 `load_at_dock` 이 먼저 걸려 이 길을 타지 않는다(931–936).

## 4. 소비자 대조 (코드 수정 없음)

| 소비자 | 쓰는 reason·알림 | 대조 결과 |
| --- | --- | --- |
| `web/backend/app/alarms.py` | `pharmacy_only`(75)를 이름으로 안다. `qr_mismatch`·`not_detected` 는 사람 말을 붙인다(`REASON_TEXT`, 200–203). 나머지는 알람 문구에 그대로 싣는다(`rule_order_terminal`, 314–335). `DOCK_RETRY`·`DOCK_GIVEUP` 알림 종류를 안다(422–423) | 문자열 불일치 없음. 72행 주석이 가리키는 `trip_fsm.py:733` 은 지금 1019 다(줄 번호만 낡음) |
| `web/frontend/js/format.js`·`nurse.js` | `pharmacy_only`(`format.js:79`), `qr_mismatch`·`not_detected`(`format.js:330`, `nurse.js:126–129`) | 문자열 불일치 없음 |
| `tools/aggregate_runs.py` | `SUCCESS_STATE`/`SUCCESS_REASON` = `HOLD_RETURN`/`pharmacy_only`(32–33). `trip_limit_s` 600 기본(30) | 문자열 불일치 없음. 이 성공 판정은 protocol `pharmacy-lap-pilot-v1` 에만 쓴다. 병원 protocol(`hospital_full_metrics.PROTOCOL_IDS`, 29·227)은 reason 이 아니라 주문의 `DELIVERED` 주장과 보관함 관측으로 본다(`tools/hospital_full_metrics.py:396–414`) |

## 5. 바꿀 때

- reason 을 새로 만들거나 이름을 바꾸면 이 표와 4절 소비자를 같은 PR 에서 고친다.
- 재배차를 구현하면 2절의 "가능(뜻)" 을 실제 경로로 바꾼다.
