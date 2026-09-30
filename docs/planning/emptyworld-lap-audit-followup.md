# 빈월드 한 바퀴 멈춤 감사 — 후속 (구멍 C · TF 실패 · K4 L3 재료)

- 2026-09-21.
- [⑤–⑧ 감사](emptyworld-lap-audit-pharmacy-to-delivery.md)의 후속이다. 주행 구간은 #419 에 있다.
- 상태: **읽기만 한 감사 + L3 준비 메모.** 코드를 바꾸지 않았고 **아무것도 실행하지 않았다.**
- 기준: main `8af3a46`.

---

## 1. 구멍 C — ② 출발에서 선다 (새로 찾은 것)

감사 본문의 표에 **한 행이 빠져 있었다.** 주행 감사(#419)가 "`arm/at_home` 없이는 `GoToZone` 을 받지 않는다"
(계약 5절 출발 인터락)를 짚어 주어 드러났다.

| | 구간 | 무엇이 막나 | 어떻게 끝나나 |
| --- | --- | --- | --- |
| **C** | **② 출발** | `arm/at_home` 이 **false** 라 주행이 `GoToZone` 을 거부한다 | 트립이 `DISPATCHING` 에서 **무기한 대기** |

### 왜

`at_home` 은 **관절값 차이**로 정해진다. 내부 상태(래치)가 아니다.

```python
def at_home(self):                                    # arm_node.py
    joints = self.joint_positions()
    if joints is None:
        return None                                   # unknown → 토픽을 아예 내지 않는다
    return kin.at_pose(joints, self._home, self._home_tolerance) and not self.moving()
```

- `_home` = `home_joint_positions`, 공차 `home_tolerance_rad` **0.05 rad, 관절마다**.
- 기동 초기값은 **unknown** 이고, `_publish_at_home` 은 unknown 이면 **아무것도 내지 않는다**
  ("오래된 true 로 출발하지 않게 한다", 계약 4절). 그래서 `joint_states` 가 오기 전에는 토픽이 비고 주행은 기다린다.
- **홈 이동이 실패해도 영영 false 가 되는 래치는 없다.** 관절이 그 자리에 오면 다시 true 가 된다.

### 그래서 어느 값을 넣어도 하나가 깨졌다

실습23a 에서 `--mode ros` 기동 직후 UR5 는 **6 관절 사실상 0**(2e-06 … 7e-08)이었고, 팔 노드는 **기동 때 홈으로
가지 않는다**(`start_homing` 은 `PickPouch` goal 이 끝난 뒤에만 불린다).

| `home_joint_positions` | ② 출발 | 첫 픽 뒤 홈 이동 |
| --- | --- | --- |
| ready 자세(재야 하는 값) | **`at_home=false` → `GoToZone` 거부 → ② 에서 섬** | 안전 |
| 키를 지움(기본 `[0.0]*6`) | 기동 직후 관절이 ≈0 이라 **지나감** | **팔을 수평으로 다 펴는 위험한 이동** |

### 해법

**스테이지가 `--mode ros` 에서도 `--ur5-ready` 자세로 스폰한다**(시뮬 `226fdb3`, `--ur5-spawn-ready`,
`emptyworld-loop` preset 에서 켜짐). 스폰 자세 = params 값이면 기동 직후 `at_home=true` 가 되어 ②를 지나가고,
첫 픽 뒤 홈 이동도 검증된 자세로 간다. **하나로 둘이 풀린다.**

`ur5 spawn_settled … joints={…}` / `ur5 home_positions=[…]` 줄의 **정착 뒤 값**을 `home_joint_positions` 에 넣는다.
`sag_rad` 이 0.05 를 넘으면 그 자체가 결함 신호다 — 스폰 자세가 중력을 못 버틴다는 뜻이고, 그러면 `at_home` 이
기동 직후 false 로 떨어져 ②가 다시 막힌다.

---

## 2. TF 조회가 실패하면 어떻게 닫히나

K5 에서 `<zone>/cabinet`(부모 `map`, 작성자 `zones_tf`)과 팔 기준 프레임이 **끊긴 두 트리**에 있으면 물린다.

- `lookup_pose` 가 `lookup_transform(..., timeout=Duration(seconds=0.5))` 을 한 번 부르고,
  `TransformException` 이면 **WARN 한 줄(`TF {parent} <- {child} 없음: …`) 뒤 `None`**. **재시도하지 않는다.**
- 그 위에서 놓을 곳 조회가 `None` 이면 **즉시 `not_detected`**(`놓을 곳 TF 없음: {frame}`).
  **`pick_timeout_s`(60 s)를 기다리지 않는다.**

**그래서 빠르게, 그러나 조용하지 않게 실패한다** — WARN + `outcome=not_detected` + detail 에 프레임 이름.

**다만 0.5 s 는 짧다.** `zones_tf` 는 static TF(latched)지만 **팔이 그보다 먼저 goal 을 받으면** 한 번 실패한다.
L3 에서 이 줄이 나오면 **기동 순서를 먼저 본다** — 고장이 아니라 순서 문제일 수 있다.

---

## 3. K4 L3 슬롯 재료

### ① 기동 확인 줄

```
arm up. robot=amr_1 base_frame=amr_1/ur_arm_base_link joints=[...]
arm sensors. pouches=/amr_1/hand_camera/pouches (camera) tag_reads=… (camera) deck_pick_from_frame=False
```

- 첫 줄의 `base_frame` 으로 **결정 47 이 적용됐는지** 본다. K4 는 params 에 명시해서 돈다.
- 둘째 줄로 **어느 토픽을 보고 있는지** 본다. 출처가 틀리면 증상이 `not_detected` 로만 보여
  **설정 문제와 센서 문제가 구별되지 않는다.**

### ② `PickPouch(BELT)` 한 번의 정상 흐름

feedback `phase` 와 `/events` 가 이 순서다.

| 순서 | feedback | 이벤트 | 그때 일어나는 것 |
| --- | --- | --- | --- |
| 1 | `detect` | **`PICK_ATTEMPT`**(detail `belt`) | 검출을 기다린다. 여기부터가 파지 시도다 |
| 2 | `approach` | | 파지 자세 위 `approach_height_m` 로 간다(계약 3절: 위에서 내려온다) |
| 3 | `grasp` | **`POUCH_PICKED`** | 그리퍼를 닫고 `holding` 을 기다린다 |
| 4 | `transfer` | | 들어 올려 놓을 곳 위로 |
| 5 | `place` | **`POUCH_LOADED`**(칸) 또는 **`POUCH_PLACED`**(보관함) | 놓고 물러난다 |
| 6 | | **`ARM_HOME`** | 결과를 돌려준 **뒤에** 홈으로 간다 |

스테이지 쪽 참값은 따로다 — **집었다 = `suction on … distance ≤ 0.01`**, **놓였다 = 명령한 칸의 `in_slot=True`**.
팔의 `ok` 로 세지 않는다(v0 은 `placement_check` 를 켜지 않는다 — 그 구멍이 P32 다).

### ③ orchestrator 없이 픽만 보기 — **된다**

`PickPouch` 는 팔 노드가 직접 서빙하는 액션이라 orchestrator 가 없어도 보낼 수 있다.

```
ros2 action send_goal /amr_1/pick_pouch rokey_p3_interfaces/action/PickPouch \
  "{order_id: 'ord-0001', source: 0, target_slot: 0}" --feedback
```

- `source`: **0 = BELT**, 1 = DECK. `target_slot` 은 **0 부터**(프레임 이름은 `deck_slot_frame_base` 가 만든다).
- **인터락이 먼저 선다**: `base/stopped` 가 true 여야 한다(계약 5절). 주행을 안 띄우면 그 토픽을 아무도 안 내
  `rejected_interlock` 으로 닫힌다 — **마스터에서 그 토픽을 직접 내거나 주행을 같이 띄워야 한다.**
- 벨트 봉투는 `/pharmacy/dispense` 를 직접 쏴서 만든다.
- 검출은 조합에 따라 다르다 — `pouch_source: sim` 이면 스테이지가, `camera` 면 perception 이 내야 한다.
  **둘 다 없으면 `not_detected` 다**(그 자체가 ④의 음성 사례다).

### ④ 음성 사례를 L3 에서 보는 법

**벨트 끝에 봉투가 없을 때 `PickPouch(BELT)` 가 `not_detected` 로 닫히는가.**

- `/pharmacy/dispense` 를 **쏘지 않고** 위 goal 을 보낸다.
- 기대: `PICK_ATTEMPT` 는 찍히고, `detection_timeout_s`(5 s) 뒤 `outcome=not_detected`,
  **`POUCH_PICKED` 는 찍히지 않고, 팔은 움직이지 않는다**(IK 목표 0건).
- 이것이 서야 "센서가 스텁이 아니다" 가 증명된다. **봉투가 없는데 집었다고 하면 그건 센서가 아니다.**
- 두 번째 음성 사례: **다른 주문의 봉투만 있을 때도 `not_detected`**(QR 대조가 산다).

---

## 4. 확인하지 않은 것

- **아무것도 실행하지 않았다.** 위 순서·줄 원문은 코드에서 읽은 것이다. 실제 로그는 다를 수 있다.
- ③의 goal 예문은 **보내 본 적이 없다.** 인터락 때문에 첫 시도가 `rejected_interlock` 으로 닫힐 수 있다.
- `sag_rad` 이 실제로 공차를 넘는지는 **L3 에서만 안다**(이 Mac 에 물리가 없다).
- 주행 구간(②⑥⑨⑩)의 판정은 #419 에 있다. 이 문서의 C 행이 그쪽 ②와 같은 자리를 본다.
