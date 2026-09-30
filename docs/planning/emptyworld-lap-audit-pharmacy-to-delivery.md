# 빈월드 한 바퀴 멈춤 감사 — ⑤–⑧(적재 · 이송 · 인증 · 전달)

- 2026-09-21.
- 상태: **읽기만 한 감사.** 코드를 바꾸지 않았고 **아무것도 실행하지 않았다(L1·L2·L3 전부 미실행).**
- 기준: main `5584114`. 조합은 [빈월드 한 바퀴 스택](../runbooks/emptyworld-lap-stack.md) 1절.
- 막으려는 것: **`scan_tag` 같은 구멍이 더 있는데 K6 날 하나씩 밟는 것.**
  인벤토리(#404)는 "누가 무엇을 하나"를 적었다. 이 문서는 **"이 조합에서 누가 응답하나"** 를 본다.
- 주행 구간(②⑥⑨⑩)은 주행 쪽의 같은 감사에 있다.

**결론부터: 구멍이 둘이다. 그리고 더 이른 쪽이 아직 안 알려져 있었다.**

| | 구간 | 무엇이 막나 | 어떻게 끝나나 |
| --- | --- | --- | --- |
| **A** | **⑤ 벨트 픽** | 팔이 봉투 **검출**을 기다리는데 **주는 주체가 없다** | `not_detected` × 3 → 주문 `ABORT` |
| **B** | ⑦ 인증 | `tag_standoff_m`(0)·`tool_frame`(빈 값)이 없어 `ScanTag` 가 시도조차 안 한다 | `UNREADABLE` × 2 → `AUTH_FAIL` |

**A 가 B 보다 먼저 온다.** B 만 고치면 ⑤ 에서 선다.

**그리고 구멍이 하나 더 있다 — ② 출발이다.** 주행 감사(#419)가 짚어 준 것으로,
`arm/at_home` 이 false 면 주행이 `GoToZone` 을 아예 받지 않는다. A·B 를 다 고쳐도 거기서 선다.
경위와 해법은 [후속 문서](emptyworld-lap-audit-followup.md)에 있다 — TF 조회 실패가 닫히는 모양과
K4 L3 슬롯 재료도 같이 적었다.

---

## 1. 조합에서 누가 응답하나

`use_stub_arm:=false` · `use_ur5_arm:=true` · `pick_notice:=false` · `use_stub_fleet:=false` ·
`use_isaac_adapter:=true` · `pharmacy_only:=false`, **검출기는 기본값(스텁)**.

| orchestrator 가 기다리는 것 | 누가 주나 | 안 오면 | v0 에서 |
| --- | --- | --- | --- |
| `{ns}/arm/at_home`(Bool 5 Hz) | UR5 `arm` 노드 | `_guard(AT_HOME)` 에서 **무기한 대기**(`DISPATCHING`·`RETURNING`) | 실물 |
| `{ns}/base/stopped`(Bool) | 주행 | `_guard(BASE_STOPPED)` 에서 **무기한 대기** | 실물(주행 몫) |
| `{ns}/gripper/holding`(Bool) | Isaac 스테이지 | `HOLDING` 은 guard 에 안 쓰임(낙하 판정용) | 실물 |
| `/pharmacy/belt`(BeltState) | `isaac_adapter` | `_enter_docked_load` 가 `belt is None` 이면 **대기** | 실물 |
| `{ns}/go_to_zone`(액션) | 주행 | `goto_timeout_load_s` 120 s / `ward` 180 s | 실물(주행 몫) |
| `{ns}/pick_pouch`(액션) | UR5 `arm` 노드 | `pick_timeout_s` **60 s** | 실물 |
| `{ns}/scan_tag`(액션) | **UR5 `arm` 노드** | `scan_timeout_s` **30 s** | 실물 |
| `{ns}/hand_camera/pouches` | **스텁 검출기**(perception 미기동) | 팔이 `detection_timeout_s` 뒤 `not_detected` | **스텁** |
| `{ns}/hand_camera/tag_reads` | **스텁 검출기** | `_last_tag` 가 비어 있음 | **스텁** |
| `/evaluator/cabinet` | (빈월드에 없음) | **한 바퀴에 영향 없음** — 아래 3절 | 없음 |

`scan_tag` 서버가 **팔 노드**라는 것이 ⑦ 의 원인이다(`arm_node.py` `ScanTag` 액션 서버).

---

## 2. 구멍 A — ⑤ 벨트 픽에 검출을 주는 주체가 없다

`arm_node._wait_for_pouch` 는 **`source` 와 무관하게** `{ns}/hand_camera/pouches` 에서 `order_id` 가 맞는
검출을 기다린다. 없으면 `detection_timeout_s`(5 s) 뒤 `not_detected` 다.

이 조합에서 그 토픽을 내는 것은 **스텁 검출기**뿐인데(perception 은 안 띄운다), 스텁은 두 조건에서만 낸다.

1. `AUTH_OK` 를 봐서 `_visible = True` 가 된 뒤,
2. `POUCH_LOADED` 로 상판에 올라간 것으로 아는 주문만.

**벨트 픽은 `AUTH_OK` 보다 한참 앞이다.** 그래서 그 시점에는 빈 배열만 나가고, 팔은 "검출 0건" 으로 닫는다.
`_result_picking_belt` 가 `pick_max_attempts` 까지 다시 시도한 뒤 주문을 **`ABORT`** 한다.

그리고 스텁이 내더라도 **쓸 수 없다**: 스텁의 `PouchDetection` 은 **`pose` 를 채우지 않는다.**
팔은 `abs(x)+abs(y)+abs(z) < 1e-6` 이면 `검출기가 거리를 못 정했다(pose 가 0)` 로 거부한다
(`arm_node._pouch_pose_in_base`). 스텁 검출기는 **실물 팔과 짝이 되도록 만들어진 적이 없다.**

**즉 ⑤ 는 "스텁을 켜 두면 거짓으로 통과" 가 아니라 "아예 못 지나간다" 이다.**

---

## 3. ⑧ 전달 — 여기서는 **안 선다**

받은 질문: `AUTH_OK` 뒤 orchestrator 가 `PickPouch(SOURCE_DECK)` 를 부르기 전에 검출을 기다리는가?

**안 기다린다.** `_enter_delivering` 은 `_drained()` 와 `_guard(BASE_STOPPED)` 만 보고 바로
`SendGoal(PICK_POUCH, {source: SOURCE_DECK, target_slot: -1})` 을 낸다. `POUCH_DETECTED` 를 보지 않는다.
(그 이벤트는 **스텁 검출기가** `AUTH_OK` 에 반응해 내는 것이고, FSM 의 대기 조건이 아니다.)

→ **`deck_pick_from_frame`(PR #414)으로 팔이 검출 없이 집으면 ⑧ 은 통과한다.**

### `CABINET_LOCKED` 는 누가 내나 — orchestrator 다

`_result_delivering` 이 `PickPouch` 결과가 `OK` 일 때 `CABINET_LOCKED` 를 내고 이어서 주문을
`ORDER_DELIVERED` 로 닫으며 `ORDER_DONE` 을 낸다. **센서가 아니라 팔의 `ok` 가 근거다.**

### `/evaluator/cabinet` 이 없어도 `ORDER_DONE` 까지 간다

`CabinetObservation` 은 **평가 전용**이다 — 메시지 주석이
*"Operating nodes (orchestrator, arm, fleet) must not subscribe to it; only event_logger does.
The orchestrator claims DELIVERED, never SUCCESS."* 라고 못박는다.

**그래서 한 바퀴는 그 토픽 없이 완주한다.** 다만 run 기록의 `SUCCESS` 가 안 선다.
K5 합격선을 "놓였다" 로 두려면 그 토픽이 필요하다는 것은 그대로다(K5 인터페이스 PR #416 6절 — 아직 머지 전이다).

---

## 4. 스텁 검출기가 켜져 있을 때 **무엇이 거짓으로 통과하는가**

한 줄로: **인증의 태그가 "AMR 이 어디 서 있는가" 가 아니라 "주문 풀이 무엇을 말하는가" 에서 나온다.**

근거(`stubs/stub_detector.py`):

- `ARRIVED` 이벤트를 받으면 `_tag_id = self._stop_tag()` 로 정한다. `_stop_tag` 은 **상판에 실린 첫 주문의
  `bed` 를 주문 풀에서 찾아** 그 침상의 태그를 만든다. **AMR 의 실제 위치도 yaw 도 보지 않는다.**
- 그 값을 `{ns}/hand_camera/tag_reads` 에 5 Hz 로 낸다.
- orchestrator 는 그 토픽을 구독해 `_last_tag` 에 담고(`orchestrator_node.py` `_on_tag`),
  `_result_authenticating` 이 **`detail.get('tag_id') or self._last_tag`** 로 비교한다.

→ **`ScanTag` 가 `tag_id` 를 비워서 OK 로 닫으면, 비교는 스텁이 만든 "언제나 맞는 태그" 로 이뤄진다.**
지금은 `ScanTag` 자체가 `UNREADABLE` 이라 여기까지 오지 않지만, **⑦ 을 고치는 방식에 따라 이 경로가 열린다.**

**그래서 K6 판정선에 이 문장을 결과 전에 박아야 한다:**

> 검출기가 스텁인 동안 **인증은 센서가 아니다.** 스텁의 태그는 주문 풀에서 나오므로 AMR 이 어느 침상
> 앞에 서 있든 맞는다. "다른 침상에서 `AUTH_FAIL`" 은 **스텁 검출기를 끄거나** 시뮬 센서(`/{ns}/sim/tag_reads`)로
> 바꾼 뒤에만 의미가 있다.

---

## 5. 그래서 무엇을 해야 하나 (제안, 결정 아님)

| 구멍 | 가장 작은 판 | 누구 |
| --- | --- | --- |
| **A. ⑤ 벨트 픽** | 셋 중 하나를 골라야 한다 — ⓐ perception(`pouch_detector`)을 이 조합에 띄운다(실물 검출) ⓑ 스텁 검출기가 **벨트 봉투도, `pose` 도** 내게 고친다 ⓒ 팔에 `belt_pick_from_frame` 같은 opt-in 을 둔다(벨트 끝은 TF 가 없어 **불가**로 보인다) | **결정 필요**. ⓐ 가 계약에 맞고 ⓑ 는 스텁을 실물 팔과 짝지우는 일이다 |
| **B. ⑦ 인증** | `scan_tag_source: camera\|sim`(기본 camera). `sim` 은 `/{ns}/sim/tag_reads` 를 쓴다 | 비전(팔 opt-in) + 시뮬(센서 발행, K2 뒤) |

**A 에 대한 제 의견**: ⓒ 는 안 된다 — 벨트 끝 봉투에는 `deck_slot_*` 같은 TF 가 없다.
ⓐ 와 ⓑ 중에서는 **ⓐ 가 계약대로**이고(계약 2.1 절의 검출은 perception 몫), ⓑ 는 스텁에 실물용 기하를
넣는 일이라 "스텁이 실물처럼 보이는" 쪽으로 간다. 다만 ⓐ 는 YOLO·카메라가 빈월드에서 도는지에 달려 있다.
**이건 이 감사 범위 밖의 판단이 섞여 있어 시뮬 쪽과 같이 정해야 한다.**

---

## 6. 확인하지 않은 것

- **아무것도 실행하지 않았다.** 위 전부 코드를 읽은 것이다. 실제로 띄우면 다른 순서로 설 수 있다.
- 주행 구간(②⑥⑨⑩)과 `go_to_zone`·`base/stopped` 의 실제 응답은 **주행 쪽 감사**에 있다.
- `observation_guard` 는 꺼진 것으로 봤다(기본값). 켜면 `_enter_docked_load`·`_enter_picking_belt` 에
  guard 가 더 붙는다.
- 리셋·재기동 경로(`RESETTING`, epoch)는 이 감사에 넣지 않았다.
- 시한 값은 `TripConfig` 기본값이다. 런북이 다른 값을 주면 그쪽이 맞다.
