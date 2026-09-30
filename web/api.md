# 관제 웹 서비스 — 백엔드 API v0.1 (초안)

ROKEY_P3_A3 병원 약제 배송 시뮬의 ROS 2 상태를 브라우저로 내보내는 게이트웨이.
프론트는 이 문서만 보고 시작할 수 있다.

- 상태: **초안**. `status_view.py` 원문 대조는 끝났다(§9). 남은 "미확정" 표시 항목은 바뀔 수 있다.
- 기준 코드: `v1.1.0`(`f316197`)의 `web/backend/app/main.py`. 라우트는 §1–§7 의 16개(`GET` 13, `POST` 2, `WS /ws` 1)다. 그 밖의 경로는 `--static` 을 줬을 때의 정적 파일뿐이다.
- **인증이 없다.** `127.0.0.1` 밖으로 열면 망 안의 누구나 화면을 본다. `--allow-commands` 까지 켜면 누구나 리셋·요청을 넣는다(기동 로그 경고, `host_warnings`).
- 기본 bind: `127.0.0.1:8000`. 호스트는 `--host`, 포트는 `--port` 로만 변경.
- 개발용 실행: `python -m app.main --mock` (ROS 없이 fixture 재생, 프론트는 이 모드로 개발)
- 실물 실행: `python -m app.main` (ROS 2 Jazzy 환경 source 필요)
- 명령 API(2단계)는 `--allow-commands` 로 띄웠을 때만 열린다. 기본은 **403**.

**병원 월드(9/23)에서 더해진 것 — 어디를 보나**

| 무엇 | 절 |
|---|---|
| 병상을 병실·병동으로(`group`·`label`, C1·C2·W1·D1–D10) | §7.4 |
| 병실 묶음(mode 2)에 두 병실이 섞이면 400 `mixed_rooms` | §7.2 |
| 평면도: 지도·전 구역 자세·AMR 자세(`--map-file`) | §7.5, §7.6, §1.6 |
| 촬영 화면: 일곱 단계 `stage`, 주문 큐 `/api/queue` | §1.7, §7.7 |
| 알람 문구의 목적지는 그 요청의 것, `URGENT_ARRIVING` 은 긴급만 | §4.1 |
| 병원 mock 으로 띄우기(녹화 fixture), 스텁 한 바퀴의 동작 | §10.6, §10.7 |

---

## 0. 공통 규약

### 0.1 시간

| 필드 | 뜻 |
|---|---|
| `sim_s` | 시뮬 시각(초, float). ROS `header.stamp` 기준. |
| `wall` | 서버가 **수신한** 실제 시각. ISO 8601 UTC, 밀리초 3자리 (`2026-09-17T08:12:03.412Z`). |
| `server_time` | 서버가 **이 snapshot 을 만든** 실제 시각. 같은 형식·같은 시계다. |

**`server_time` 과 모든 `wall`·`accept_after_wall` 은 같은 시계에서 나온다**(서버의 UTC 벽시계).
그래서 서로 빼는 것이 정당하다. **브라우저 시계와는 섞지 마라** — 뺄셈의 기준은 언제나
`server_time` 이지 `Date.now()` 가 아니다.

> 다만 **서버가 계산해 주는 값이 있으면 그걸 써라**(`age_wall_s`, `accept_in_s`). 빼기를
> 안 하는 것이 가장 안전하다.

판정·정렬은 `sim_s` + `epoch`, 신선도(stale) 판정은 `wall` 을 쓴다. 섞지 않는다.

**리셋이 `sim_s` 를 되감는다고 가정하지 마라.** 우리 리셋은 타임라인을 Stop 하지 않아서
`/clock` 이 되감기지 않는다(스텁도 Isaac 스테이지도). 되감길 수도 있고 아닐 수도 있다 —
**세대 구분은 언제나 `epoch` 으로 하고 `sim_s` 비교로 하지 마라.**

### 0.2 epoch 과 리셋

`Event.epoch`(uint32) 가 리셋 세대다. `RESET_BEGIN` 이 새 epoch 를 연다.
**프론트는 `epoch` 이 바뀌면 화면 상태를 통째로 버리고 새 snapshot 으로 다시 그려야 한다.**
epoch 이 다른 이벤트를 한 목록에 섞어 보여주지 말 것.

### 0.3 seq (커서)

서버는 수신한 이벤트마다 **도착 순서대로 1부터 증가하는 정수 `seq`** 를 붙인다.
`seq` 는 서버가 만든 것이고 ROS 에는 없다. 페이지네이션·재연결 복구는 전부 `seq` 로 한다.

**`seq` 는 커서일 뿐 표시 순서가 아니다.** 목록의 순서는 `status_view.event_key`
= `(epoch, 리셋 구분, stamp, 도착 순번)` 로 정한다(그 함수를 `import` 해서 쓴다).

이게 중요한 이유: `/events` 는 `transient_local` 이라 **늦게 붙으면 지난 이벤트가 작성자별로
뭉쳐서 한꺼번에 온다.** 도착 순서로 그리면 늦게 연 화면의 타임라인이 통째로 뒤죽박죽이 된다.
서버가 정렬해서 주므로 **프론트는 받은 순서대로 그리면 된다.**

서버가 재시작하면 `seq` 는 1로 돌아간다. snapshot 의 `server_run_id` 가 바뀌므로
프론트는 `server_run_id` 가 달라지면 커서를 버리고 처음부터 받는다.

### 0.4 오류

```json
{ "error": { "code": "duplicate_request_id",
             "message": "request_id 가 이미 쓰였다: web-0001",
             "detail": { "request_id": "web-0001" } } }
```

**화면 분기는 `code` 로 한다. `message` 로 분기하지 마라** — 문구는 다듬을 수 있다.
`message` 는 사람에게 그대로 보여 주는 용도다.

#### `detail` — 무엇 때문에 막혔나

**`message` 에서 값을 뽑지 마라.** 계약이 "`message` 로 분기하지 마라" 라고 하면서 값을 문장
안에만 두면 파싱을 강요하는 셈이고, 문구를 다듬을 때 조용히 깨진다. 막힌 대상은 `detail` 에
구조로 싣는다.

| `code` | `detail` |
|---|---|
| `refill_in_progress` | `item_id`(무엇이 보충 중인가), `order_id` |
| `insufficient_stock` | `item_id`·`requested`·`available`(대표 한 건) + **`shortages`**(모자란 것 전부) |
| `bad_mode_for_orders` | `mode`, `order_count` |
| `mixed_rooms` | `mode`(2), `rooms`(`[{room, order_ids}]`, 병실 순) |
| `unknown_or_used_order` | `order_id` |
| `bad_destination` | `destination_id` |
| `duplicate_request_id` | `request_id` |
| `trip_in_progress` | `request_id`(**무엇이 끝나기를 기다리나**) |
| `barrier_running` | `accept_after_wall`(**언제 풀리나**. `RESET_DONE` 전이면 `null`) |
| 그 밖 | **`detail` 키가 아예 없다** |

**대상이 없는 거부에는 `detail` 을 안 싣는다**(`empty_orders`·`bad_request`·`rejected`).
빈 객체를 보내면 화면이 있는 줄 알고 들여다본다.

`detail` 의 값은 **참고용**이다. 화면 분기는 여전히 `code` 로 하고, `detail` 은 "무엇을·언제까지
기다려야 하는지" 를 사람에게 말해 줄 때 쓴다.

| HTTP | `code` | 언제 |
|---|---|---|
| 400 | `bad_request` | 파라미터·본문 형식 오류 (`request_id` 없음, `order_id` 없음 등) |
| 400 | `bad_mode_for_orders` | 1인·긴급(mode 0·1)인데 주문이 둘 이상이다 |
| 400 | `mixed_rooms` | 병실 묶음(mode 2)인데 주문의 병상이 두 병실 이상이다 |
| 403 | `commands_disabled` | 명령 API 인데 `--allow-commands` 가 없다 |
| 503 | `no_ros` | 실물 모드인데 ROS 연결이 없다 |
| 409 | `duplicate_request_id` | `request_id` 가 이미 쓰였다 |
| 409 | `empty_orders` | `orders` 가 비었다 |
| 409 | `bad_destination` | `destination_id` 가 구역 ID 모양이 아니다 |
| 409 | `unknown_or_used_order` | 주문 풀에 없거나 이미 쓰인 `order_id` |
| 409 | `refill_in_progress` | 그 약품이 재고 0 이거나 PAUSED 다 |
| 409 | `insufficient_stock` | 요청한 개수가 가용 재고보다 많다 |
| 409 | `trip_in_progress` | 진행 중 트립이 있다 |
| 409 | `barrier_running` | 리셋 barrier 중이거나, `RESET_DONE` 뒤 3.5 s 가 안 지났다 (§1.4) |
| 409 | `rejected` | 그 밖 — **실물에서 사유 없이 거부된 경우가 여기로 온다** |

**기다리면 풀리는 것과 입력을 고쳐야 하는 것이 다르다.**

| 기다리면 풀린다 | 입력을 고쳐야 한다 |
|---|---|
| `trip_in_progress` — 곧 끝난다 | `bad_request`, `bad_mode_for_orders`, `mixed_rooms` |
| `barrier_running` — 곧 끝난다 | `empty_orders`, `bad_destination` |
| `refill_in_progress` — **얼마나 걸릴지 모른다**(아래) | `duplicate_request_id`, `unknown_or_used_order` |
| `insufficient_stock` — 보충이 끝나면 풀린다 | |

**`refill_in_progress` 는 버튼을 잠그는 데 쓰지 마라.** 보충은 28-34 sim s 이고 **실패할 수
있다.** 실패하면 잠긴 버튼이 영영 안 풀리고, 사람은 눌러 볼 수단조차 잃는다. 버튼은 열어 두고
옆에 "보충 중 — 요청은 거부됩니다" 를 적는 편이 낫다. 서버가 어차피 막으므로 잠금은 화면
편의일 뿐이다. `dispenser.refilling` 과 `paused_item_ids` 로 상태를 보여 주면 된다.

#### 실물과 mock 의 차이 — 중요

**실물에서는 goal 거부에 사유가 실려 오지 않는다.** 거부는 `Event` 도 남기지 않는다.
그래서 서버는 **보내기 전에 orchestrator 의 수락 조건을 미리 검사해서** 위 코드를 붙인다.

- 미리 잡은 것 → 구체적인 `code` (`duplicate_request_id` 등)
- **미리 못 잡고 orchestrator 가 거부한 것 → `rejected`**

`rejected` 일 때 서버는 **`/rosout` 에서 그 `request_id` 의 거부 줄을 찾아** `message` 에
붙인다(형식 `Deliver goal 거부 <request_id>: <사유>`, 최근 10 s 안).

> **`request_id` 가 있는 줄만 쓴다.** 시각만으로 맞추면 남의 거부 사유가 엉뚱한 요청에 붙는다 —
> **틀린 사유는 사유 없음보다 나쁘다.** 사람이 엉뚱한 곳을 본다.

orchestrator 가 찍는 줄은 `_refuse` 의 이것이다(#201):

```
Deliver goal 거부 {request_id or "-"}: {reason}
```

`request_id` 가 비면 `-` 가 들어간다. 그 줄은 **누구의 것인지 알 수 없으므로 쓰지 않는다.**
못 찾으면 `message` 를 비운 채로 둔다 — 없는 사유를 지어내지 않는다.

즉 `rejected` 는 "서버가 예상하지 못한 거부" 라는 뜻이다. mock 에서는 거의 안 나오지만
실물에서는 나올 수 있다. 화면은 이 경우 **"요청이 거부됐습니다 (사유 불명)"** 정도로 처리해야 한다.

---

## 1. GET /api/snapshot

현재 전체 상태 한 장. 프론트는 첫 화면에서 이것 하나만 받으면 된다.

```json
{
  "server_run_id": "5f2c1a90",
  "server_time": "2026-09-17T08:12:03.412Z",
  "mode": "mock",
  "deployment": { "multi_pc": true, "roles": ["arm", "nav", "stack", "web"], "peer": "10.10.0.1", "domain_id": 131 },
  "commands_enabled": false,
  "mock_faults": [],
  "seq": 1042,
  "epoch": 3,
  "reset_in_progress": false,
  "accepting_requests": true,
  "accept_after_wall": null,
  "accept_in_s": null,
  "clock": {
    "sim_s": 184.25,
    "alive": true,
    "age_wall_s": 0.08
  },
  "trip": {
    "request_id": "req-0007",
    "mode": 1,
    "mode_name": "MODE_URGENT",
    "mode_source": "event_detail",
    "destination_id": "bed_a1",
    "robot_id": "amr_1",
    "phase": "arriving",
    "phase_label": "병동 도착 직전",
    "phase_source": "status_view",
    "started_sim_s": 120.5,
    "last_event_sim_s": 183.9,
    "orders": [
      {
        "order_id": "ord-12",
        "patient_id": null,
        "item_id": null,
        "state": 2,
        "state_name": "DELIVERED",
        "outcome": "delivered",
        "reason": "",
        "stamp": 183.1
      }
    ]
  },
  "dispenser": {
    "paused": true,
    "paused_item_ids": ["drug-ibu"],
    "refilling": true,
    "refilling_item_ids": ["drug-ibu"],
    "refill_targets": [
      { "item_id": "drug-ibu", "slot_name": "A", "kind": "cylinder", "target": "round" }
    ],
    "container_read": {
      "tag_id": "cn-0007", "status": "ok", "stamp": 52.1,
      "wall": "2026-09-17T08:10:39.000Z", "age_wall_s": 3.2
    },
    "last_refill": {
      "stamp": 54.5,
      "parsed": true,
      "item": "drug-amox", "slot": "A", "kind": "cylinder",
      "cell": "floor_left/r0c1", "target": "round",
      "seed": 0, "draw": 3, "clearance": 0.011
    },
    "queue_length": 2,
    "belt_occupied": false,
    "slots": [
      {
        "item_id": "drug-ibu",
        "slot": 0,
        "slot_name": "A",
        "lot_id": "L-2409",
        "expiry": "2027-03-01",
        "count": 0,
        "active": false
      },
      {
        "item_id": "drug-acet",
        "slot": 1,
        "slot_name": "B",
        "lot_id": "L-2411",
        "expiry": "2027-06-30",
        "count": 7,
        "active": true
      }
    ],
    "stamp": 183.0,
    "wall": "2026-09-17T08:12:02.900Z",
    "stale": false
  },
  "belt": {
    "occupied": false,
    "at_end": false,
    "order_id": "",
    "stamp": 183.8,
    "wall": "2026-09-17T08:12:03.330Z",
    "stale": false
  },
  "signals": {
    "arm_at_home":     { "value": false, "wall": "2026-09-17T08:12:03.400Z", "age_wall_s": 0.01, "stale": false },
    "base_stopped":    { "value": false, "wall": "2026-09-17T08:12:03.400Z", "age_wall_s": 0.01, "stale": false },
    "gripper_holding": { "value": true,  "wall": "2026-09-17T08:12:03.400Z", "age_wall_s": 0.01, "stale": false },
    "belt":            { "value": false, "wall": "2026-09-17T08:12:03.330Z", "age_wall_s": 0.08, "stale": false },
    "m0609_at_home":   { "value": true,  "wall": "2026-09-17T08:10:41.000Z", "age_wall_s": 82.4, "stale": true },
    "speed_limit":     { "speed_limit_pct": 70.0, "stop_reason": null,
                         "wall": "2026-09-17T08:12:03.100Z", "age_wall_s": 0.31, "stale": false }
  },
  "sim_running": { "value": true, "wall": "2026-09-17T08:12:03.200Z", "age_wall_s": 0.2, "stale": false },
  "stage": { "key": "deliver", "label": "배송", "index": 4, "phase": "moving", "refill_item_ids": [] },
  "robots": [
    { "robot_id": "amr_1", "x": 12.41, "y": 6.93, "yaw": 0.02, "frame": "map",
      "age_wall_s": 0.12, "stale": false, "source": "tf", "goal_zone": null, "docked": false, "kind": "amr" },
    { "robot_id": "amr_2", "x": 3.20, "y": 9.10, "yaw": 1.57, "frame": "map",
      "age_wall_s": 0.15, "stale": false, "source": "fleet_poses", "goal_zone": null, "docked": null,
      "kind": "spare_amr" }
  ],
  "dummies": [
    { "id": "dummy_1", "kind": "dummy", "x": 18.4, "y": 6.9, "yaw": 3.14, "frame": "map",
      "age_wall_s": 0.15, "stale": false, "source": "fleet_poses" }
  ],
  "scan": null,
  "cabinet": {
    "order_id": "ord-12",
    "cabinet_id": "bed_a1",
    "present": true,
    "wall": "2026-09-17T08:12:01.100Z",
    "source": "evaluator",
    "display_only": true
  },
  "recent_events": [],
  "alarms": []
}
```

- `trip` 은 진행 중 트립이 없으면 `null`. (orchestrator 는 동시에 한 트립만 받는다.)
- **`mock_faults`** 가 비어 있지 않으면 **고장 흉내가 켜진 서버다**(§11). 화면은 "고장 흉내 중"
  배지를 띄워야 한다 — 그때 보이는 빨간 알람이 진짜인지 흉내인지 사람이 구분해야 한다.
  실물 모드와 평소 mock 에서는 `[]` 다.
- **`orders[].state_name` 으로 `SUCCESS` 는 절대 오지 않는다.** `OrderStatus.msg` 원문:
  *"The orchestrator never publishes this one; event_logger writes it into the run record from
  /evaluator/cabinet only."* orchestrator 가 주장하는 최선은 `DELIVERED` 이고, `SUCCESS` 판정은
  평가 노드가 기록에만 남긴다. **화면에 `SUCCESS` 자리를 만들어도 실물에서는 채워지지 않는다.**
- **`accepting_requests`** 가 `false` 면 지금 `POST /api/requests` 가 `barrier_running` 으로
  거부된다. **화면은 이 값으로 보내기 버튼을 잠가야 한다.**
- **`accept_in_s`** 는 다시 받기까지 **남은 초**다. **화면은 이것을 써라** — `accept_after_wall`
  은 절대 시각이라 화면이 제 시계와 빼야 하는데, **브라우저 시계가 서버와 같다는 보장이 없다**
  (30 s 틀어져 있으면 "33초 뒤" 라고 쓴다). 신선도를 `age_wall_s` 로 주는 것과 같은 이유다.
- **`accept_after_wall`** 은 같은 것을 절대 시각으로 준다 — 기록·디버그용이다.
  **둘은 짝으로 `null` 이 된다**(§1.4).
- **`trip.robot_id` 는 이 트립을 수행하는 AMR 이다.** `Event.msg` 의 `robot_id` 는
  `amr_1 .. amr_5`, `m0609`, `dispenser` 인데, **`m0609` 와 `dispenser` 는 조제실 설비이고
  트립의 로봇이 아니다** — 여기에는 절대 안 들어간다(단계표가 조제기 이벤트를 무시하는 것과
  같은 원칙). `REQUEST_ACCEPTED` 가 AMR 을 실었으면 그것, 아니면 `event_key` 순으로 처음
  나오는 AMR 이벤트의 것이고, 한 번 정해지면 트립 동안 바뀌지 않는다.
- **그래서 `trip.robot_id` 는 `null` 일 수 있다.** 요청이 수락된 직후에는 아직 AMR 이벤트가
  없다. 지어내지 않는다 — 화면은 로봇 자리를 비워 두면 된다.
- `dispenser`, `belt` 는 아직 한 번도 못 받았으면 `null`.
- **`cabinet` 은 기본이 `null` 이다.** `/evaluator/cabinet` 은 **평가 전용** 토픽이고, 계약상
  운영 노드는 구독하지 않는다. 웹은 운영 노드가 아니라 표시만 하므로 구독은 허용되지만
  **`--show-evaluator` 로 켜야** 나온다. 나올 때는 `source:"evaluator"`,
  `display_only:true` 가 붙는다 — **판정에 쓰지 마라.**
- `recent_events` 는 §2 의 이벤트 객체 배열(기본 12개, `status_view.StatusModel(max_events=12)` 와 같게).
- `alarms` 는 §4 의 알람 객체 배열(현재 살아있는 것).
- `signals`의 기본 키는 `arm_at_home`, `base_stopped`, `gripper_holding`, `belt`, `m0609_at_home` 다. 속도 제한을 수신하면 선택 키 `speed_limit`이 더해진다(§1.9). 이 키는 `value`가 없는 별도 구조다. 미수신 시 생략된다.

### 1.1 신선도(stale) 기준

**신선도는 언제나 `wall` 로 잰다** — sim 아니다(계약 4절).

> **알려진 차이**: 계약 4절과 `status_monitor` 는 **steady clock**(`time.monotonic()`)으로 재는데,
> 이 서버는 **시스템 UTC 벽시계**로 잰다. 평소에는 같지만, 서버 시계가 뛰면(NTP 보정 등)
> 나이와 `stale` 이 한 번 틀어진다.
>
> **뒤로 뛰면 `age_wall_s` 가 음수가 되고, `stale` 도 같이 `false` 가 된다** — 둘이 같은
> 뺄셈에서 나오므로 `stale` 은 방어선이 아니다. 화면은 **음수 나이를 "모름" 으로** 다뤄야
> 한다("싱싱함" 이 아니다). 특히 `belt` 가 걸리면 화면이 "신선" 이라고 쓰는데 실제로는
> 수십 초 전 값일 수 있다. 교육장 유선망에서 NTP 가 이미 안정된 상태라면 실질 위험은
> 낮지만 **계약과 어긋나는 것은 사실이다.** §12.2 에 미해결로 적어 둔다.

| 대상 | 임계 | 발행 주기 | 근거 |
|---|---|---|---|
| 상태 heartbeat (`signals` 기본 5개, `belt`) | `1.0 s` | **H = 5 Hz** (`gripper_holding` 은 10 Hz) | 계약 4절 값 |
| `/clock` | `2.0 s` → `clock.alive=false` | — | 계약 4절 값 |
| `dispenser` | **`3.0 s`** | **L = 변화 시 + 1 Hz** | **계약에 임계 없음 — 웹 표시용** |

`1.0 s` 는 5 Hz 에서 **5주기 누락**에 해당하므로 빡빡하지 않다.

`DispenserStatus` 는 heartbeat(H)가 아니라 **latched(L)** 다 — 변화가 있을 때와 1 Hz 로만 온다.
여기에 `1.0 s` 를 쓰면 **가짜 stale 이 깜빡인다.** 그래서 `3.0 s` 를 따로 쓴다.
이 값은 계약에 없는 **우리 표시용 판단**이고, `status_view` 가 dispenser 신선도를 어떻게 다루는지
클론 뒤 원문으로 맞춘다(**미확정**).

> `STATUS_STALE` 알람은 `signals` 5개만 본다. `dispenser.stale` 은 화면 표시용 표식이고
> 알람을 만들지 않는다.

**`belt` 가 낡으면 그냥 표시 문제가 아니다.** `BeltState.msg` 원문: *"No message for 1.0 s wall
means unknown, and unknown forbids both dispensing and picking."* 즉 벨트 상태를 모르면
**배출도 픽도 못 한다** — 조제실이 멈춘다. 화면에서 이 신호의 `stale` 은 다른 넷보다 무겁게
다루는 편이 좋다.

### 1.2 trip.phase 와 trip.phase_label

| 필드 | 쓰임 |
|---|---|
| `phase` | 영문 키. **프론트의 분기는 이것으로 한다.** |
| `phase_label` | `status_view.py` 의 **한글 원문**. **화면 표시는 이것을 그대로 찍는다.** |
| `phase_source` | 항상 `"status_view"` |

**표는 `status_view.TRIP_PHASES` 를 `import` 해서 쓴다 — 베껴 두지 않는다.** 저쪽이 바뀌면
여기도 따라 바뀐다. 영문 `phase` 는 **한글 라벨에서** 뽑으므로 라벨이 같으면 `phase` 도 같다 —
둘이 어긋날 수 없다.

**주의 — 둘은 한 칸 어긋나 보인다.** 한글 라벨은 "지금 막 무엇을 하려는가"를 말하기 때문이다.
예: `ARRIVED` 는 `phase="arrived"` 인데 `phase_label="인증"` 이다. status_monitor 터미널 화면과
같은 규칙이니 **고쳐 쓰지 말고 그대로 표시**해야 한다.

| 이벤트 | `phase` | `phase_label` |
|---|---|---|
| `REQUEST_ACCEPTED` | `accepted` | 적재 위치로 이동 |
| `AMR_DOCKED_LOAD` | `docked_load` | 배출 |
| `DISPENSED` | `dispensing` | 벨트 이송 |
| `POUCH_AT_END` | `dispensing` | 벨트 끝 픽 |
| `PICK_ATTEMPT` | `loading` | 픽 |
| `POUCH_PICKED` | `loading` | 픽 |
| `POUCH_LOADED` | `loading` | 적재 |
| `LOAD_DONE` | `load_done` | 적재 끝 |
| `ARM_HOME` | `arm_home` | 팔 홈 |
| `DEPARTED` | `moving` | 병동으로 이동 |
| `ARRIVING` | `arriving` | 병동 도착 직전 |
| `ARRIVED` | `arrived` | 인증 |
| `AUTH_OK` | `unloading` | 보관함 배달 |
| `AUTH_FAIL` | `auth` | 인증 실패 |
| `POUCH_DETECTED` | `unloading` | 보관함 배달 |
| `POUCH_PLACED` | `unloading` | 보관함 배달 |
| `CABINET_LOCKED` | `locked` | 보관함 잠김 |
| `ORDER_DONE` | `order_done` | 주문 닫힘 |
| `RETURNED` | `returning` | 도크로 복귀 |
| `DOCKED` | `docked` | 대기(도크) |
| `RESET_BEGIN` | `reset` | 리셋 중 |
| `RESET_DONE` | `reset_done` | 리셋 끝(3 s 뒤 요청 수락) |

**조제기·M0609 이벤트(`DISPENSER_*`, `REFILL_*`)는 단계를 바꾸지 않는다.** 보충이 끼어들어도
트립 단계는 그대로 유지된다. 보충 진행은 `dispenser.refilling` 으로 따로 본다.

### 1.3 mode · destination_id · 주문 상세의 출처 (`mode_source`)

`/deliver` 는 **액션**이라 goal(`DeliveryRequest`)이 토픽으로 안 나온다. 따라서 외부 관찰만으로는
`mode`, `destination_id`, `Order.patient_id`, `Order.item_id` 를 **알 수 없다**.
확인 결과 `trip_fsm.py:352` 는 `Emit(EVENT_REQUEST_ACCEPTED, request_id)` 라 **detail 이 비어 있다.**

**이미 들어갔다**(#104, `trip_fsm.request_summary`). `REQUEST_ACCEPTED.detail` 에 compact JSON
한 줄이 실린다. 계약과 msg 는 바꾸지 않았다 — `detail` 은 원래 자유 문자열이고 판정에 안 쓰는
메모다(구조 파싱은 이것과 `REFILL_DONE`(§2.2) 둘만 예외).

```json
{"mode":1,"destination_id":"bed_a1","orders":[{"order_id":"ord-12","patient_id":"p-7","item_id":"drug-ibu"}]}
```

위 네 필드는 **전부 같은 출처**다. 그래서 출처 표시는 `mode_source` **하나로 묶는다**
(snapshot 에는 `destination_source` 같은 필드를 따로 두지 않는다. `POST /api/requests` 응답의 `destination_source` 는 §7.2 에 따로 있다).

| `mode_source` | 뜻 |
|---|---|
| `"event_detail"` | `REQUEST_ACCEPTED.detail` 을 파싱해서 얻었다 |
| `"web_request"` | 웹이 직접 넣은 요청(§7)이라 서버가 원래부터 안다 |
| `null` | 얻을 길이 없었다 (detail 이 비었거나 파싱 실패) |

파싱에 실패해도 **오류가 아니다.** 조용히 `null` 로 두고 나머지 필드는 그대로 낸다.

**`null` 인 화면은 계속 필요하다.** `detail` 이 비었거나(옛 run) 파싱이 실패하면
`mode`·`destination_id`·`patient_id`·`item_id` 가 전부 `null` 이다. 그때는 "알 수 없음" 으로
표시한다 — 오류가 아니다.

### 1.4 리셋 barrier — 언제 요청을 넣을 수 있나

리셋은 **두 단계로** 요청을 막는다. 둘 다 `barrier_running` 으로 거부된다.

| 구간 | `reset_in_progress` | `accepting_requests` | `accept_in_s` | `accept_after_wall` |
|---|---|---|---|---|
| 평소 | `false` | `true` | `null` | `null` |
| `RESET_BEGIN` 부터 `RESET_DONE` 까지 | **`true`** | `false` | `null` (모른다) | `null` |
| `RESET_DONE` 부터 **3.5 s wall** 까지 | `false` | **`false`** | **남은 초** | 풀리는 시각 (ISO) |
| 그 뒤 | `false` | `true` | `null` | `null` |

**`RESET_DONE` 전에는 남은 시간을 모른다.** 리셋이 얼마나 걸릴지 서버도 알 수 없으므로
숫자를 지어내지 않는다 — `null` 이다.

**`RESET_DONE` 이 왔다고 바로 넣을 수 있는 게 아니다.** orchestrator 는 `_accept_after` 까지
약 3 s 더 거부한다(계약 6절 5). 발행기가 `reset_settle_s` 3.5 s 를 기다리는 이유이고,
status_view 의 표시가 `리셋 끝(3 s 뒤 요청 수락)` 인 이유다.

**이 창은 wall 시각으로 잰다** — sim 시각이 아니다. orchestrator 가 `time.monotonic()` 을 쓴다.

화면은 `accepting_requests` 로 버튼을 잠그고, **`accept_in_s` 를 그대로 보여 주면 된다** —
빼는 계산을 하지 마라.

### 1.5 orders[].outcome — 주문의 결말 한 낱말

`state`·`state_name`·`reason` 은 **ROS 원본 값**이다. 그 위에 서버가 파생해 싣는 한 낱말이
`outcome` 이고, **화면은 이것 하나로 분기한다.**

| `outcome` | 언제 | 뜻 |
|---|---|---|
| `accepted` | `state 0` | 접수 |
| `in_progress` | `state 1` | 진행 중 |
| `delivered` | `state 2`(또는 `10`) | 전달 완료 |
| **`pharmacy_done`** | **`state 11` + reason `pharmacy_only`** | **조제실 구간 완료 — 정상. 경고가 아니다** |
| `held` | `state 11` + 그 밖의 reason | 회수됨 — 이상 |
| `aborted` | `state 12` | 중단 |
| `timeout` | `state 13` | 시간초과 |

값은 화면이 다르게 그리는 경우와 **1:1** 이다. 합쳐 두면 화면이 `state_name` 으로 다시
갈라야 하고, 그러면 같은 규칙이 서버와 화면 두 곳에 생긴다. 모르는 `state` 는 `accepted` 로
떨어진다 — 없는 결말을 지어내지 않는다.

#### 왜 `pharmacy_done` 이 따로 있나

`pharmacy_only` 모드는 적재 뒤 정거장으로 가지 않고 도크로 복귀하며, 실은 주문을
`HOLD_RETURN(pharmacy_only)` 로 닫는다(`trip_fsm.py:733`). **봉투가 상판에 남은 채 복귀한 것이
사실이므로 `HOLD_RETURN` 은 맞다** — 다만 이 모드에서는 이상이 아니라 정상 완주다.

`HOLD_RETURN` 이 나오는 다른 자리(`trip_fsm.py:977`)는 `auth_mismatch`·`goto_rejected`·
`drain_timeout` 같은 진짜 이상이다. **두 경우를 `state_name` 만으로는 못 가른다.**

#### 트립 한 바퀴가 정상 완주인지

**모든 주문의 `outcome` 이 `pharmacy_done` 이면** 조제실 한 바퀴 정상 완주다.
트립 단위 플래그는 두지 않는다 — 주문별 값과 어긋날 수 있다.

> **`orders` 가 빈 경우를 같이 봐라.** "전부 `pharmacy_done`" 을 그대로 구현하면
> **주문이 0건일 때 공허하게 참**이 된다(트립 사이 구간). `orders` 가 비지 않았는지도 확인한다.

**묶음에서 섞일 수 있다.** 한 주문은 `pharmacy_done`, 다른 주문은 `held` 일 수 있다.
그때 **알람은 `held` 인 주문에만** 뜨고, 트립은 완주가 아니다.

### 1.6 robots — 평면도의 AMR 자세

`--map-file` 을 준 실행에서만 채워진다. 병원 월드다. 안 주면 빈 배열이다. 지금 동작 그대로다.
AMR 이 늘 수 있어 배열이고 `robot_id` 순이다. 아직 자세를 못 받았으면 빈 배열이다.

| 필드 | 뜻 |
|---|---|
| `x`, `y`, `yaw` | `map` 프레임의 `<robot>/base_link` 자세(m, rad). §7.6 의 지도와 같은 좌표계 |
| `frame` | 늘 `"map"` |
| `age_wall_s`, `stale` | 마지막으로 받은 뒤의 wall 초. `1.0 s` 를 넘으면 `stale`(signals 와 같다, §1.1) |
| `source` | `"tf"` = 실물에서 TF `map → <robot>/base_link` 를 5 Hz 로 조회한 것. `"mock"` = 아래 |
| `kind` | `"amr"` = 주 AMR(`--robot-id`, TF). `"spare_amr"` = 여벌 AMR(아래 fleet_poses) |
| `goal_zone` | 늘 `null` 이다. `GoToZone` 목표는 밖에서 안 보인다. 이벤트에도 안 실린다. 목적지는 `trip.destination_id` 다. 단계로 짐작하지 않는다. 복귀 도크 zone 도 이벤트에 없다 |
| `docked` | `true` \| `false` \| `null`. 이 epoch 에서 그 AMR(`robot_id`)의 **마지막** 이벤트가 `DOCKED`·`RESET_DONE` 이면 `true` 다. 다른 이벤트면 `false` 다. 그 AMR 의 이벤트가 없으면 `null`(모름)이다. 뜻은 "도크에 닿은 뒤 다음 트립이 시작되기 전"이다. 다음 트립의 `REQUEST_ACCEPTED` 에서 `false` 가 된다. `DOCKED` 없이 끝난 트립(복귀 실패)은 `false` 로 남는다. orchestrator 가 다음 트립을 재도킹부터 하는 것과 같은 뜻이다. `/<robot>/base/docked`(`DockingState`)는 fleet 의 opt-in(`publish_docking_state`)이다. 기본은 꺼짐이다. 그래서 쓰지 않는다 |

- `map → <robot>/odom` 은 AMCL 또는 시뮬의 `dock_origin_tf` 가 낸다. `odom → base_link` 는 base_driver 가 낸다(계약 3절). TF 가 끊기면 마지막 자세가 남는다. `stale` 이 된다. 화면은 stale 자세를 흐리게 그리는 편이 좋다.
- **mock**: fixture 에 자세가 없다. 평면도가 켜져 있으면 AMR 을 zones 의 `dock_1` 자리에 **세워 둔다**
  (`source: "mock"`, `age_wall_s: 0`, `stale: false`). 트립 단계로 움직이는 흉내는 내지 않는다.

#### 여벌 AMR 과 더미 — `/isaac/fleet/poses`

여벌 AMR(`P3_AMR_COUNT` > 1)과 가짜 AMR(더미, 스테이지 `--traffic-dummies`)은 주문·Nav2·base_driver 가 없다. 그래서 TF 가 없다.
스테이지가 대신 `/isaac/fleet/poses`(`std_msgs/String` JSON, 5 Hz, `map`)로 낸다(#754).

- 여벌 AMR 은 `robots[]` 에 `kind: "spare_amr"`, `source: "fleet_poses"` 로 붙는다. 주문이 없어 `docked`·`goal_zone` 은 `null` 이다.
- 더미는 새 최상위 `dummies[]` 다. 필드는 `id`, `kind`(`"dummy"`), `x`, `y`, `yaw`, `frame`, `age_wall_s`, `stale`, `source` 다. 없으면 `[]` 다.
- `stale` 은 1 s 넘게 안 온 것이다(5 Hz). stamp 가 같은 메시지는 새 정보로 치지 않는다(TF 와 같은 규칙).
- 마지막 메시지에 없는 id 는 빠진다. 주 AMR 과 id 가 같은 줄은 버린다. TF 가 기준이다.
- 이 토픽은 `--map-file` 과 상관없이 받는다. 여벌·더미가 없는 회차에는 안 온다.

### 1.7 stage — 촬영 화면의 일곱 단계

트립을 요청, 보충, 조제, 집기, 배송, 도착, 복귀로 묶은 것이다. 새 이벤트를 만들지 않는다. 계약 이벤트에서 나온 `trip.phase`(§1.2)를 묶는다. 두 곳만 더 본다.

| `key` | `label` | `index` | 언제 (`trip.phase`) |
|---|---|---|---|
| `request` | 요청 | 0 | `accepted` — 수락, 적재 위치로 이동 |
| `refill` | 보충 | 1 | 출발 전이다. `request` 또는 `dispense` 다. 이 트립에서 아직 조제 안 된 약품이 보충 중이거나 PAUSED 다 |
| `dispense` | 조제 | 2 | `docked_load`, `dispensing` |
| `pick` | 집기 | 3 | `loading`, `load_done`, 출발 전의 `arm_home` |
| `deliver` | 배송 | 4 | `moving`, `arriving` |
| `arrive` | 도착 | 5 | `arrived`, `auth`, `unloading`, `locked`, `order_done`, 출발 뒤의 `arm_home` |
| `return` | 복귀 | 6 | `returning` |
| `idle` | 대기 | null | 트립 없음(`DOCKED` 로 닫힘) |
| `reset` | 리셋 | null | 리셋 barrier 중 |

- `arm_home` 은 적재 뒤에도 배달 뒤에도 나온다. 그 트립에 `DEPARTED` 가 있었으면 `arrive` 다.
- `refill_item_ids` 는 `key` 가 `refill` 일 때만 채운다. 그 약품들이다. 트립의 약품은 `REQUEST_ACCEPTED.detail` 에서 읽는다. 모르면 보충으로 짐작하지 않는다. 마지막 재고를 조제하는 순간 약품이 PAUSED 가 된다. 이 트립의 봉투는 이미 나왔다. `DISPENSED` 가 난 주문의 약품은 보지 않는다.
- 병실 묶음(mode 2)은 정거장마다 `deliver → arrive` 를 되풀이한다. 화면은 `index` 가 줄어드는 것을 막지 않는다.
- `phase` 는 원문 `trip.phase` 그대로다(트립이 없으면 null).

---

### 1.9 signals.speed_limit — 감속기 속도 제한

`/amr_1/speed_limit`(`nav2_msgs/SpeedLimit`)이다. 감속기(`speed_governor`)가 코스트맵 여유로 정해 1 Hz 로 다시 낸다.
받은 적이 없으면 **키가 없다**. 다른 신호 다섯(`arm_at_home` 등)과 모양이 다르다. `value` 가 없다.

| 필드 | 뜻 |
|---|---|
| `speed_limit_pct` | 최고 속도의 몇 % 로 가는가. 100 이면 제한 없음(Nav2 의 0 도 100 으로 낸다). v1.1.0 기본 근접 감속은 70이다(0.7/1.0 m/s). m/s 로 온 값이면 `null` |
| `stop_reason` | `"obstacle_ahead"` \| `null`. 감속기 정지 규칙(비율 ≤ 1 %)이면 `"obstacle_ahead"` 다. 진행 방향 앞, 몸체 폭 띠 안에 지도에 없는 장애물이 가깝다는 뜻이다. msg 에 사유 필드가 없어서 값에서 끌어낸다. 감속은 `null` 이다 |
| `wall`, `age_wall_s` | 서버가 받은 wall 시각과 그 뒤 초 |
| `stale` | 3 s 넘게 안 왔다. 1 Hz 발행이라 다른 신호의 1 s 기준을 쓰지 않는다. `STATUS_STALE` 알람도 이 키를 세지 않는다 |

- 감속기 쪽 값은 `rokey_p3_navigation/speed_governor.py` 다(`STOP_PERCENT` 1 %, v1.1.0 근접 70 %). 이 값의 수신만으로 정지 규칙의 현장 발동이 검증되지는 않는다.
- `nav2_msgs` 가 없는 PC(Nav2 미설치 개발 PC)에서는 이 구독만 빠지고 브리지가 경고 한 줄을 남긴다. 그때는 키가 없다.

### 1.10 deployment — 한 대인가 두 PC 인가

```json
"deployment": { "multi_pc": true, "roles": ["arm", "nav", "stack", "web"], "peer": "10.10.0.1", "domain_id": 131 }
```

| 필드 | 뜻 |
|---|---|
| `multi_pc` | 두 PC 모드인가. `peer` 가 있으면 `true` 다 |
| `roles` | 이 웹이 뜬 PC 가 맡은 역할(`P3_ROLES`, 월드 순서). 한 대 기본이면 `null` 이다 |
| `peer` | 상대 PC 주소(`P3_PEER`). 한 대면 `null` 이다 |
| `domain_id` | 웹 프로세스의 `ROS_DOMAIN_ID`. mock 이거나 숫자가 아니면 `null` 이다 |

- `tools/demo_v2.sh` 는 두 PC 모드(`P3_PEER` 있음)일 때만 웹에 `--roles`·`--peer` 를 넘긴다. `ros_env` 가 환경을 비운다(`env -i`). 그래서 환경 변수로는 전달되지 않는다.
- `mode`(`"mock"`·`"ros"`)는 그대로다. 형을 바꾸면 화면이 깨진다. 그래서 새 필드로 뒀다.

### 1.11 sim_running — Isaac 타임라인 Play/Stop

`/p3/sim_running`(`std_msgs/Bool`)이다. 스테이지가 Play/Stop 이 바뀔 때 곧바로, 아니면 1 Hz 로 낸다. 끝날 때 `false` 를 한 번 낸다(#759).

| 값 | 화면 |
|---|---|
| `null` | 받은 적이 없다 |
| `{value: true, stale: false}` | 실행 중 |
| `{value: false, stale: false}` | 멈춤(Stop) |
| `stale: true` | 3 s 넘게 안 왔다 — Isaac 이 없다. `value` 는 마지막으로 받은 값이다 |

- latched 가 아니다. 죽은 프로세스의 `true` 가 남지 않게 하려는 것이다. 그래서 늦게 붙으면 최대 1 s 동안 `null` 이다.
- `/clock` 이 멈추면 뜨는 `CLOCK_STOPPED` 알람(§4.1)과는 따로다. 이 필드는 타임라인 상태를 직접 본다.

### 1.12 qr_reads — 손 카메라 QR 판독과 그 내용 요약

재범 9/29: "QR 을 찍는 걸 보여 주되, QR 이 아니라 QR 에 포함된 정보를 간략하게"(개발자·간호사 화면).
QR 안에는 ID 만 있다(`ord-` 봉투, `pt-` 환자, `st-` 스테이션, `cn-` 약통, `md-` 모듈). 서버가 그 ID 를 주문 풀(`--order-pool`),
약 카탈로그(`--catalog`), 조제기 파일(`--dispenser-file`)로 풀어 `info` 에 싣는다. 전부 합성 데이터다.

```json
"qr_reads": [
  { "robot": "amr_1", "kind": "pouch", "tag_id": "ord-0001", "count": 14,
    "first_wall": "2026-09-29T02:10:03.100Z", "last_wall": "2026-09-29T02:10:05.900Z", "age_wall_s": 0.4, "stamp": 812.3,
    "info": { "order_id": "ord-0001", "patient_id": "2001", "bed": "bed_a1", "item_id": "drug-amox", "drug": "아목시실린 캡슐 500 mg" } },
  { "robot": "amr_1", "kind": "patient", "tag_id": "2001", "count": 6, "first_wall": "…", "last_wall": "…", "age_wall_s": 3.1, "stamp": 861.0,
    "info": { "patient_id": "2001", "bed": "bed_a1", "order_ids": ["ord-0001"] } },
  { "robot": "amr_1", "kind": "station", "tag_id": "station_b", "count": 3, "first_wall": "…", "last_wall": "…", "age_wall_s": 9.0, "stamp": 700.2,
    "info": { "zone": "station_b" } },
  { "robot": "m0609", "kind": "container", "tag_id": "cn-0003", "count": 5, "first_wall": "…", "last_wall": "…", "age_wall_s": 40.2, "stamp": 31.0,
    "info": { "container_id": "cn-0003", "lot_id": "lot-ibu-01", "item_id": "drug-ibu", "drug": "이부프로펜 정 200 mg", "expiry": "2027-05-31" } }
]
```

| 필드 | 뜻 |
|---|---|
| `robot` | 읽은 카메라의 로봇. AMR 은 `--robot-id`(`/<robot>/hand_camera/tag_reads`), M0609 는 `m0609`(`/m0609/hand_camera/tag_reads`) |
| `kind` | `patient` \| `station` \| `pouch` \| `container` \| `module` (`TagRead.kind`) |
| `tag_id` | 판독 ID. 환자·스테이션은 접두를 뗀 값이다(`pt-2001` → `2001`) |
| `count` | 이 세대에 같은 (로봇, ID)를 받은 횟수. 검출기는 보이는 동안 프레임마다 낸다. 한 줄로 합친다 |
| `first_wall`·`last_wall`·`age_wall_s` | 처음·마지막으로 받은 wall 시각, 마지막 뒤 초 |
| `stamp` | 처음 받은 판독의 sim 시각(`header.stamp`) |
| `info` | 요약. 풀·카탈로그에 없는 값은 `null` 이다. 지어내지 않는다. 종류마다 키가 다르다(위 예) |

- 최근 받은 것부터 최대 20줄이다. 못 읽은 판독(`status != OK`)은 싣지 않는다. `RESET_BEGIN` 에서 비운다.
- 판독은 **주문과 맞았다는 뜻이 아니다.** 맞았는지는 이벤트다. 봉투는 `POUCH_DETECTED`·`PickPouch` 결과다. 환자는 `AUTH_OK`·`AUTH_FAIL` 이다. 약통은 `dispenser.container_read`·M0609 로그다.

### 1.8 카메라·스캔 실시간 — `--live-sensors` (기본 꺼짐)

촬영 때 비전·라이다를 보이게 하는 것이다. **기본은 꺼짐이다.** 끄면 구독이 하나도 없다. 카메라 API 는 404 `live_sensors_off` 이다. `snapshot.scan` 은 `null` 이다.

JPEG 인코더는 Pillow 다. requirements 에는 없다. 실물 PC 는 venv 가 `--system-site-packages` 다. 그래서 Ubuntu 의 `python3-pil` 을 쓴다. 없으면 서버가 `--live-sensors` 를 끈다. 한 줄을 찍는다(`** --live-sensors 를 끈다: … **`).

켜도 서버가 지키는 부하 상한:

| 항목 | 상한 |
|---|---|
| 카메라 구독 | **보는 사람이 있을 때만** 건다. 마지막 시청자가 나가면 0.5 s 안에 푼다. best effort, depth 1 |
| 카메라 프레임 | 저장·전송 ≤ 5 fps. 5 fps 를 넘는 프레임은 복사도 하지 않는다 |
| 인코딩 | 가로 ≤ 640 px 로 줄인다. JPEG 품질 50. 새 프레임일 때 한 번만 인코딩한다. 시청자가 나눠 쓴다 |
| 시청자 | 한 카메라에 ≤ 3. 넘으면 429 `too_many_viewers` |
| 스캔 | 2 Hz, 점 ≤ 360. best effort, depth 1 |

rtf 영향: 끄면 0 이다. 켜고 패널을 열면 선택한 카메라 토픽을 구독한다. 영상 전달 상한은 카메라당 5 fps다. 여러 카메라를 열면 각각의 구독과 부하가 생긴다. 발행자(Isaac)는 구독자가 없어도 같은 주기로 낸다(계약 2.1 ≤ 10 Hz). 켰을 때 rtf 를 잰 회차는 아직 없다.

#### GET /api/cameras

```json
{
  "enabled": true,
  "limits": { "fps": 5.0, "max_width": 640, "jpeg_quality": 50, "max_viewers": 3,
              "scan_hz": 2.0, "scan_max_points": 360 },
  "cameras": [
    { "name": "amr_hand", "label": "AMR 손 카메라(트레이 쪽)", "topic": "/amr_1/hand_camera/image_raw",
      "width": 1280, "height": 800, "stamp": 312.4, "age_wall_s": 0.1, "stale": false, "viewers": 1,
      "overlay": {
        "tag": { "tag_id": "pt-1001", "status": "ok", "stamp": 311.9 },
        "pouches": [ { "order_id": "ord-0001", "confidence": 0.91, "slot_index": 0 } ] } },
    { "name": "m0609_hand", "label": "M0609 손 카메라(약통 QR)", "topic": "/m0609/hand_camera/image_raw",
      "width": null, "height": null, "stamp": null, "age_wall_s": null, "stale": true, "viewers": 0,
      "overlay": { "tag": null, "pouches": [] } },
    { "name": "amr_qr", "label": "AMR QR 추적(사각형)", "topic": "/amr_1/hand_camera/qr_view",
      "width": null, "height": null, "stamp": null, "age_wall_s": null, "stale": true, "viewers": 0,
      "overlay": { "tag": null, "pouches": [] } },
    { "name": "m0609_qr", "label": "M0609 QR 추적(사각형)", "topic": "/m0609/hand_camera/qr_view",
      "width": null, "height": null, "stamp": null, "age_wall_s": null, "stale": true, "viewers": 0,
      "overlay": { "tag": null, "pouches": [] } }
  ]
}
```

- 끄면 `{"enabled": false, "limits": {...}, "cameras": []}` 이다. 404 가 아니다. 화면이 토글을 숨기는 데 쓴다.
- `width`·`height` 는 원본 해상도다. 스트림은 가로 640 으로 줄어 있다. 프레임을 아직 못 받았으면 `null` 이다. `stale: true` 다. 2 s 넘게 안 와도 `stale` 이다.
- `overlay` 는 **글자 오버레이**다.
  - `amr_hand`: `tag` 는 `/amr_1/hand_camera/tag_reads` 에서 온다. `pouches` 는 `/amr_1/hand_camera/pouches` 에서 온다(카메라 경로, `P3_CAMERA_POUCHES=1`). 참값 센서(`/amr_1/sim/*`)는 싣지 않는다. 카메라가 본 것이 아니다.
  - `m0609_hand`: `tag` 는 `dispenser.container_read` 와 같은 판독이다(§6.1).
  - `amr_hand`·`m0609_hand` 원본에는 **픽셀 박스가 없다.** `PouchDetection` 에 박스 필드가 없다. 자세만 있다.
- **QR 추적 영상** `amr_qr`·`m0609_qr`(재범 9/29): 검출기가 `/<robot>/hand_camera/qr_view` 로 낸다. 찾은 QR 마다 **네 꼭짓점
  사각형**과 판정 색을 그린 영상이다. 초록은 읽음이다. 지금 집는 주문의 봉투면 `OK` 다.
  빨강은 다른 주문의 봉투다. 화면 글자는 `NOT ORDER` 다. 팔은 그 봉투를 안 집는다. 노랑은 자리만 찾고 못 읽은 것이다. 화면 글자는 `QR ?` 다. 글자는 영상 안에 있다. `overlay` 는 비어 있다. 검출기는 **보는 구독자가 있을 때만** 그린다.
  QR 안 내용의 사람 말 요약은 §1.12 `qr_reads` 다.
- `a1_pick` 같은 촬영 시점은 ROS 토픽이 아니다. 그래서 스트림할 수 없다.

#### GET /api/cameras/{name}/stream · GET /api/cameras/{name}/frame.jpg

- `stream`: MJPEG(`multipart/x-mixed-replace; boundary=frame`). `<img src="/api/cameras/amr_hand/stream">` 로 바로 쓴다. 연결이 끊기면 시청자에서 빠진다. 화면은 패널을 닫을 때 `src` 를 비워 연결을 끊는다.
- `frame.jpg`: 한 장. 잠깐 시청자로 들어간다. 최대 약 3 s 기다린다. 프레임이 안 오면 404 `no_frame` 이다.
- 오류: 404 `live_sensors_off`, 404 `unknown_camera`(이름은 `amr_hand`·`m0609_hand`·`amr_qr`·`m0609_qr`, `live_sensors.CAMERAS`), 429 `too_many_viewers`.

#### snapshot.scan

```json
"scan": { "robot_id": "amr_1", "frame": "map", "stamp": 312.0, "wall": "2026-09-25T03:00:00.000Z",
          "age_wall_s": 0.3, "stale": false, "range_max": 20.0, "points": [[12.41, 8.02], [12.44, 8.05]] }
```

- `/amr_1/scan`(`LaserScan`)을 2 Hz 로 솎는다. 범위 밖·NaN·inf 는 뺀다. 점은 ≤ 360 개다. 소수 둘째 자리(m)다.
- `frame` 이 `"map"` 이면 TF `map → <스캔 프레임>` 으로 옮긴 좌표다. 평면도(§7.6)에 바로 찍는다. TF 는 `--map-file` 을 준 실행에서만 조회한다. 못 찾으면 스캔 프레임(`amr_1/lidar_link`) 좌표 그대로다. 화면은 그때 그리지 않는다.
- `stale`: 2 s 넘게 안 왔다.
- mock + `--live-sensors`: 합성 프레임을 낸다(보는 사람이 있을 때만). 반지름 2 m 원형 스캔을 낸다. 화면 개발용이다. 평면도가 켜져 있으면 mock AMR 자리 기준 `map` 좌표다.

## 2. GET /api/events

```
GET /api/events?epoch=3&since=1000&limit=200
```

| 파라미터 | 기본 | 뜻 |
|---|---|---|
| `epoch` | 현재 epoch | 이 세대만. `all` 이면 전부. |
| `since` | 0 | `seq > since` 인 것만 (배타) |
| `limit` | 200 | 1..500 |

```json
{
  "epoch": 3,
  "next_since": 1042,
  "has_more": false,
  "events": [
    {
      "seq": 1041,
      "name": "ARRIVING",
      "request_id": "req-0007",
      "order_id": "ord-12",
      "robot_id": "amr_1",
      "epoch": 3,
      "detail": "",
      "stamp": 180.4,
      "wall": "2026-09-17T08:11:59.900Z"
    },
    {
      "seq": 1042,
      "name": "ARRIVED",
      "request_id": "req-0007",
      "order_id": "ord-12",
      "robot_id": "amr_1",
      "epoch": 3,
      "detail": "",
      "stamp": 183.9,
      "wall": "2026-09-17T08:12:03.330Z"
    }
  ]
}
```

- `robot_id` 는 `amr_1`..`amr_5`, `m0609`, `dispenser` 중 하나.
- `detail` 은 자유 문자열이고 **판정에 쓰지 않는다**. 화면 표시에만 쓴다.
- `ORDER_DONE` 의 **종료 상태는 이벤트가 아니라 같은 stamp 의 `/orders/status`** 가 말한다.
  프론트는 `ORDER_DONE` 만 보고 성공이라 쓰면 안 된다 — `trip.orders[].state_name` 을 봐라.

### 2.1 이벤트 이름 (작성자별)

| 작성자 | 이름 |
|---|---|
| orchestrator | `REQUEST_ACCEPTED`, `AMR_DOCKED_LOAD`, `LOAD_DONE`, `DEPARTED`, `ARRIVING`, `ARRIVED`, `AUTH_OK`, `AUTH_FAIL`, `CABINET_LOCKED`, `ORDER_DONE`, `RETURNED`, `DOCKED`, `DISPENSER_PAUSED`, `DISPENSER_RESUMED`, `REFILL_REQUESTED`, `RESET_BEGIN`, `RESET_DONE` |
| isaac | `DISPENSED`, `POUCH_AT_END` |
| arm | `PICK_ATTEMPT`, `POUCH_PICKED`, `POUCH_LOADED`, `POUCH_PLACED`, `ARM_HOME` |
| m0609 | `REFILL_DONE` |
| pouch_detector | `POUCH_DETECTED` |

### 2.2 REFILL_DONE 의 `refill`

조제실 장면 v2 에서 팔 노드는 `REFILL_DONE.detail` 을 compact JSON 한 줄로 낸다.
서버가 그것을 파싱해 같은 이벤트에 `refill` 을 붙인다.

```json
{ "name": "REFILL_DONE", "robot_id": "m0609",
  "detail": "{\"item\":\"drug-amox\",\"slot\":\"a\",...}",
  "refill": { "item": "drug-amox", "slot": "A", "kind": "cylinder",
              "cell": "floor_left/r0c1", "target": "round",
              "seed": 0, "draw": 3, "clearance": 0.011 } }
```

- 필드의 뜻은 §6.1 의 `last_refill` 표와 같다.
- **파싱이 안 되면 `refill` 은 `null`** 이다 — 장면 v1 의 문자열(`"drug-amox slot a[ lot …]"`)이거나
  JSON 이 깨진 경우다. 그때는 **`detail` 원문을 그대로 찍으면 된다.**
- `REFILL_DONE` 이 **아닌** 이벤트에는 이 키가 없다(값이 `null` 이 아니라 키 자체가 없다).

**`slot` 은 대문자로 맞춘다.** 팔은 소문자로 내지만, `dispenser.slots[].slot_name` 이 `"A"`/`"B"`
이므로 소문자로 두면 화면이 "방금 보충된 칸" 을 찾을 때 `"a" === "A"` 가 거짓이 되어
**조용히 아무것도 강조되지 않는다.** 예외도 안 나고 화면도 안 깨져서 아무도 모른다.
무엇이 실제로 왔는지는 `detail` 원문이 들고 있다.

**장면 v1 의 문자열은 일부러 파싱하지 않는다.** 거기에도 item·slot 이 들어 있지만, 두 형식을
다 읽으면 유지할 규칙이 둘이 되고 v1 형식은 소비자를 위한 계약이 아니라 팔 노드 내부 문구다
(`refill_sequence` 가 만든다).

**모르는 `kind`·`target` 은 통과시키지 않고 `null` 로 둔다.** §1.3 의 `mode` 와 같은 원칙 —
계약에 없는 값을 내려보내면 화면이 그릴 수 없는 것을 받는다.

---

## 3. WS /ws

연결하면 서버가 **먼저 `hello`(전체 snapshot)를 한 번** 보낸다. 그 뒤로는 변화분만 push.
클라이언트→서버 메시지는 v0.1 에 없다(`ping` 은 WS 프로토콜 레벨 ping 을 쓴다).

공통 봉투:

```json
{ "type": "snapshot", "seq": 1042, "server_time": "2026-09-17T08:12:03.412Z", "data": {} }
```

| `type` | `data` |
|---|---|
| `hello` | §1 snapshot 전문 + `"server_run_id"` |
| `snapshot` | §1 snapshot 전문. 변화가 있으면 최대 **5 Hz** 로 합쳐서, 변화가 없어도 **최소 1 Hz** 로. `robots` 자세(§1.6)도 이 주기로 온다 — 따로 스트림이 없다 |
| `events` | §2 의 `events` 배열 (새로 온 것만) |
| `alarms` | §4 의 알람 배열 (뜨거나 사라진 것. 전체 목록이 아니라 변화분) |
| `speed_limit` | §1.9 의 `signals.speed_limit` 객체. 비율이나 정지 사유가 **바뀔 때만** 보낸다. 수신 뒤에는 snapshot 에도 실리므로 이 WS 갱신만으로 복구할 필요는 없다 |

#### 조용한 것과 죽은 것은 다르다

**변화가 없어도 서버는 1 초에 한 번은 `snapshot` 을 보낸다.** 그래서 소켓의 침묵은
**서버가 죽었거나 연결이 끊겼다는 뜻**이다 — "지금 아무 일도 안 일어난다" 가 아니다.

이게 없으면 보충 대기처럼 조용한 구간(관측된 최대 침묵 11.8 초)을 화면이 "갱신이 멎었다" 와
구별할 수 없다.

> **`age_wall_s` 에 "스냅샷을 받은 뒤 흐른 시간" 을 더하지 마라.** 서버가 보낸 값을 그대로 써라.
> 연결이 끊겼는지는 **마지막 WS 메시지 이후 경과**로 따로 판정한다. 둘을 섞으면 조용한 구간이
> 전부 "낡음" 으로 뒤집힌다.

#### 끊김 판정은 하나뿐이다

**`WS 프레임이 3 초 없음` — 이것만 쓴다.** 유휴 push 가 1 Hz 이므로 3 초는 3회 누락이다.

**REST 로 생존을 찔러 보지 마라.** 같은 일을 두 경로로 하면 어느 쪽이 화면을 갱신했는지
알 수 없게 된다. `GET /api/snapshot` 은 **첫 화면과 재연결 복구**에만 쓴다(§3.1).

**알람은 델타가 아니라 전체 목록이다.** 제거 표식 없는 델타로는 사라진 알람을 알 수 없어서,
알람 집합이 바뀔 때마다 **현재 살아있는 전체 목록**을 보낸다. 프론트는 통째로 갈아 끼우면 된다.
(개수가 적어 비용이 문제되지 않는다.)

### 3.1 재연결

끊기면 `GET /api/events?since=<마지막 seq>` 로 빈 구간을 메우고, `GET /api/snapshot` 을 한 번 받는다.
`server_run_id` 가 이전과 다르면 커서를 버리고 처음부터.

### 3.2 epoch 이 바뀌면

`RESET_BEGIN` 이 오면 서버는 즉시 `snapshot`(새 epoch, `reset_in_progress: true`)을 push 한다.
프론트는 이벤트 목록·트립·알람을 비우고 다시 쌓는다.

---

## 4. GET /api/alarms

```json
{
  "alarms": [
    {
      "id": "a3f1c2",
      "level": "error",
      "kind": "AUTH_FAIL",
      "message": "bed_a1 인증 실패 — ord-12",
      "request_id": "req-0007",
      "order_id": "ord-12",
      "stamp": 183.9,
      "epoch": 3
    },
    {
      "id": "b71e08",
      "level": "warn",
      "kind": "DISPENSER_PAUSED",
      "message": "조제기 정지 — drug-ibu",
      "request_id": null,
      "order_id": null,
      "stamp": 150.2,
      "epoch": 3
    }
  ]
}
```

알람 객체는 정확히 이 8개 필드다: `id`, `level`, `kind`, `message`, `request_id`, `order_id`, `stamp`, `epoch`.
`level` 은 `info` | `warn` | `error`. `request_id`·`order_id` 는 해당 없으면 `null`.

### 4.1 규칙표

알람 판정은 **ROS 를 import 하지 않는 순수 함수**다.
입력 = (이벤트 목록, 주문 상태, 신호 신선도), 출력 = 알람 배열.

| kind | level | 조건 | message 예 |
|---|---|---|---|
| `URGENT_ARRIVING` | `warn` | `ARRIVING` 이벤트. **그 요청이 긴급(mode 1)일 때만** — 모드를 알고 긴급이 아니면 안 낸다 | `긴급 배송 접근 중 — bed_a1` |
| `AUTH_FAIL` | `error` | `AUTH_FAIL` 이벤트. 묶음 정거장처럼 `order_id` 가 없으면 `request_id` 를 적는다 | `bed_a1 인증 실패 — ord-12` |
| `HOLD_RETURN` | `warn` | `state == 11` **이고 reason 이 `pharmacy_only` 가 아닐 때** | `주문 회수 — ord-12 (사유: auth_mismatch)` |
| `ABORT` | `error` | `OrderStatus.state == 12` | `주문 중단 — ord-12 (사유: ...)` |
| `TIMEOUT` | `error` | `OrderStatus.state == 13` | `주문 시간초과 — ord-12 (사유: ...)` |
| `DISPENSER_PAUSED` | `warn` | `DispenserStatus.paused_item_ids` 가 비지 않음 | `조제기 정지 — drug-ibu` |
| `REFILL_FAILED` | `error` | 열린 `REFILL_REQUESTED` 가 **`--refill-timeout` sim s**(기본 120) 안에 닫히지 않음. 각 `REFILL_DONE` 은 가장 이른 열린 요청만 닫는다 | `보충 실패 — 120 s 내 REFILL_DONE 없음` |
| `STATUS_STALE` | `warn` | `signals` 중 `age_wall_s > 1.0` (§1.1) | `상태 끊김 — m0609_at_home (82.4 s)` |
| `CLOCK_STOPPED` | `error` | `/clock` `age_wall_s > 2.0` | `/clock 멈춤 (3.1 s)` |
| `DOCK_RETRY` | `warn` | `/p3/alerts` 의 `DOCK_RETRY`(복귀 실패 뒤 재시도). **받은 뒤 60 wall s** 동안. `order_id` 자리에 로봇 | `도킹 재시도 — amr_1: 1/3 NOT_ARRIVED, 10 s 뒤 재시도` |
| `DOCK_GIVEUP` | `error` | `/p3/alerts` 의 `DOCK_GIVEUP`. 다음 `RESET_BEGIN` 까지(최대 600 wall s) | `도킹 포기 — amr_1: …` |
| `MAP_GUARD_INTERVENE` | `warn` | `/p3/alerts` 의 `MAP_GUARD_INTERVENE`(지도 가드가 직접 전이). 60 wall s | `지도 개입 — amr_1: …` |
| `MAP_GUARD_GIVEUP` | `error` | `/p3/alerts` 의 `MAP_GUARD_GIVEUP`. 다음 리셋까지(최대 600 wall s) | `지도 미수신 — amr_1: …` |
| `OBSTACLE_STOP` | `warn` | `signals.speed_limit.stop_reason` 이 **5 wall s** 넘게 이어짐(§1.9). 신호가 끊기면(stale) 내리지 않는다 | `AMR 정지 — 앞 장애물 (6.2 s)` |
| `RESET_IN_PROGRESS` | `info` | `RESET_BEGIN` 뒤 `RESET_DONE` 전 | `리셋 중 (epoch 4)` |
| `RESET_STUCK` | `error` | `RESET_BEGIN` 뒤 **`--reset-timeout` wall s**(기본 35) 이 지나도 `RESET_DONE` 이 없음 | `리셋이 41 s 째 안 끝났다 (epoch 4)` |

- 봉투 QR 사유(#784, 병원은 QR 을 반드시 찍는다)는 사람 말을 앞에 두고 원문 코드를 같이 싣는다:
  `qr_mismatch` → `(사유: 약 QR 이 주문과 다름 — qr_mismatch)`, `not_detected` → `(사유: 약 QR 을 못 읽음 — not_detected)`.
  벨트 끝 집기 실패는 `ABORT`, 상판(병상) 집기 실패는 `HOLD_RETURN` 으로 닫힌다. 알람 객체의 필드는 그대로 8개다.
- `RESET_STUCK` 은 **리셋이 실패로 멈춘 것(`barrier_failed`)을 밖에서 아는 유일한 신호**다.
  그 상태를 알리는 토픽이 없어서, "`RESET_DONE` 이 끝내 안 온다" 로 추론한다.
  **화면에서 확인하려면** §11 의 `--mock-fault stuck_reset` 을 쓴다. 임계는 35 s wall
  (orchestrator 의 리셋 시한 30 s + 여유). 이게 뜨면 **사람이 개입해야 한다** — 저절로 안 풀린다.
- **`HOLD_RETURN` + reason `pharmacy_only` 는 알람을 내지 않는다**(info 도 아니다). 그것은
  `pharmacy_only` 모드의 **정상 완주**다 — §1.5. 1차 시연이 이 모드이므로, 경고로 올리면
  **매 바퀴 성공이 청중에게 노란 줄로 보인다.** 그 결과 정상 한 바퀴에는 알람 목록이 비고,
  **시연 중에 노란 줄이 뜨면 진짜 이상**이라는 뜻이 된다. 흔적은 주문 행의 `outcome` 과
  타임라인의 `ORDER_DONE` 에 남는다.
- 면제는 **정확히 일치**할 때만이다. `pharmacy_only_x` 나 `PHARMACY_ONLY` 는 면제되지 않는다 —
  느슨하게 맞추면 진짜 이상이 조용히 묻힌다.
- `HOLD_RETURN`·`ABORT`·`TIMEOUT` 의 `message` 에는 `OrderStatus.reason` 을 **반드시** 넣는다.
- `REFILL_FAILED` 임계는 설정값(`--refill-timeout`, 기본 **120 sim s**)이다. orchestrator 의 실제
  규칙(refill 액션 시한 90 s, 재시도 5 s 간격 최대 3회)을 클론 뒤 코드로 확인해 맞춘다.
  정상 보충은 현재 약 28 sim s 이고, 팔 #99 가 들어가면 홈 복귀를 포함해 33-34 sim s 로 늘어난다.
  **한 품목의 `REFILL_DONE` 이 다른 품목의 열린 요청을 닫지 않는다.** 마지막 요청·마지막 완료만
  보면 A 완료가 B 의 실패 알람을 지운다.
- 조건이 풀리면 알람은 사라진다(`DISPENSER_PAUSED`, `STATUS_STALE`, `CLOCK_STOPPED`, `RESET_IN_PROGRESS`).
  이벤트성 알람(`AUTH_FAIL`, `ABORT` 등)은 epoch 이 바뀔 때까지 남는다.
  **문구의 목적지는 그 이벤트가 속한 요청의 것**이다(`REQUEST_ACCEPTED.detail` 의 `destination_id`).
  다음 트립이 열려도 지난 알람의 목적지는 바뀌지 않는다. detail 이 빈 옛 빌드면 지금 트립의 이벤트만
  `trip.destination_id` 를 쓰고, 지난 트립의 것은 `목적지` 로 적는다.
- `id` 는 `(kind, request_id, order_id, epoch)` 해시라 같은 알람이 중복으로 안 쌓인다.

---

## 5. GET /api/logs

`/rosout` 의 WARN 이상을 노드 이름과 함께 최근 N개.

```
GET /api/logs?level=warn&limit=100
```

| 파라미터 | 기본 | 값 |
|---|---|---|
| `level` | `warn` | `warn` \| `error` \| `fatal` (이 레벨 **이상**) |
| `limit` | 100 | 1..500 |

```json
{
  "logs": [
    {
      "level": "error",
      "level_value": 40,
      "node": "orchestrator",
      "message": "deliver goal rejected: destination_id 'bed_z9' not in zones.yaml",
      "stamp": 181.0,
      "wall": "2026-09-17T08:12:00.500Z"
    }
  ]
}
```

`level_value` 는 `rcl_interfaces/msg/Log` 상수: DEBUG=10, INFO=20, WARN=30, ERROR=40, FATAL=50.
`node` 는 `Log.name`, `message` 는 `Log.msg` 다. WARN 미만은 아예 담지 않는다.

`--mock` 은 하트비트 토픽을 **계약과 같은 주기로 다시 실어 준다**(H 5 Hz, `gripper_holding`
10 Hz, dispenser 1 Hz). fixture 는 값이 바뀔 때만 담고 있어서, 이걸 안 하면 mock 이 실물에는
없는 `STATUS_STALE` 을 만들어 낸다. **재생 배속과 무관하게 wall 주기로 낸다** — sim 기준으로
내면 `--speed 0.05` 같은 느린 재생에서 가짜 stale 이 뜬다.

`--mock` 은 fixture 에 **예시 `/rosout` 줄 6개**(WARN·ERROR)를 섞어 재생하므로, 에러 로그 탭을
실데이터로 그려 볼 수 있다. **문구는 예시일 뿐** 실물에서 그 문장이 나온다는 뜻이 아니다.

---

## 6. 구독하는 ROS 토픽 (참고)

프론트가 쓸 건 아니지만, 어떤 필드가 어디서 오는지 추적용.

| 토픽 | 타입 | QoS |
|---|---|---|
| `/clock` | `rosgraph_msgs/Clock` | sensor, depth 1 |
| `/events` | `Event` | reliable, transient_local, depth 500 |
| `/orders/status` | `OrderStatus` | transient_local, depth 50 |
| `/pharmacy/dispenser/status` | `DispenserStatus` | transient_local, depth 1 (변화 시 + 1 Hz) |
| `/pharmacy/belt` | `BeltState` | heartbeat 5 Hz, depth 1 |
| `/amr_1/arm/at_home` | `std_msgs/Bool` | heartbeat |
| `/amr_1/base/stopped` | `std_msgs/Bool` | heartbeat |
| `/amr_1/speed_limit` | `nav2_msgs/SpeedLimit` | transient_local, depth 1 (감속기가 1 Hz 로 다시 낸다). `nav2_msgs` 가 없는 PC 에서는 구독하지 않는다(§1.9) |
| `/amr_1/gripper/holding` | `std_msgs/Bool` | heartbeat |
| `/m0609/arm/at_home` | `std_msgs/Bool` | heartbeat |
| `/p3/alerts` | `std_msgs/String`(JSON) | transient_local, depth 20. 도킹·지도 알림(§4.1). 계약 밖 토픽(#757) |
| `/evaluator/cabinet` | `CabinetObservation` | depth 50 (선택) |
| `/isaac/fleet/poses` | `std_msgs/String`(JSON) | reliable, depth 1. 여벌 AMR·더미 자리 5 Hz(§1.6) |
| `/p3/sim_running` | `std_msgs/Bool` | reliable, volatile, depth 1. 바뀔 때 + 1 Hz(§1.11, #759) |
| `/m0609/shelf/inventory` | `std_msgs/String`(장면 v2 JSON) | transient_local, depth 1. 약 → 약통 종류만 읽는다(§6.1 `refill_targets`) |
| `/m0609/hand_camera/tag_reads` | `TagRead` | reliable, depth 10. 약통(`KIND_CONTAINER`) 판독만 쓴다(§6.1 `container_read`) |
| `/amr_1/hand_camera/tag_reads` | `TagRead` | reliable, depth 10. 봉투·환자·스테이션 판독(§1.12) |
| `/rosout` | `rcl_interfaces/Log` | reliable, transient_local, depth 200 |
| `/tf`, `/tf_static` | TF — `map → amr_1/base_link` 조회(5 Hz) | `--map-file` 을 줄 때만 (§1.6) |

구독 정본은 `backend/app/ros_spec.py`의 `SUBSCRIPTIONS`다. 공통 토픽의 QoS는 `status_monitor`와 맞추고, 웹은 속도 제한·선반·QR·알림·실행 상태·로그를 더 받는다. §1.8의 영상 구독은 `--live-sensors`와 시청자 연결에 따라 별도로 열린다.

### 6.1 서버가 파생하는 조제기 필드

`DispenserStatus` 에 없는 두 필드를 서버가 만들어 붙인다.

| 필드 | 어떻게 |
|---|---|
| `dispenser.paused` | `paused_item_ids` 가 비지 않으면 `true` |
| `dispenser.refilling` | 열린 `REFILL_REQUESTED` 가 있으면 `true`. 각 `REFILL_DONE` 은 가장 이른 열린 요청만 닫는다. **이벤트 이름만으로 판정** |
| `dispenser.refilling_item_ids` | 보충 중이면 그 시점의 `paused_item_ids`, 아니면 `[]` |
| `dispenser.refill_targets` | 보충 **중** 대상. `refilling_item_ids` 와 같은 순서의 배열(아래 표) |
| `dispenser.container_read` | M0609 손 카메라의 마지막 약통 QR 판독(아래 표). 없으면 `null` |

`refilling`·`refilling_item_ids` 는 **`detail` 을 읽지 않는다.** `detail` 은 자유 문자열이고 구조 파싱 대상이 아니다 —
유일한 예외는 `REQUEST_ACCEPTED` 의 #104 JSON 하나뿐이다(§1.3).
리셋으로 epoch 이 바뀌면 `refilling` 은 자동으로 풀린다(이벤트를 epoch 으로 거르기 때문).

#### `dispenser.refill_targets[]` — 보충 중에 무엇을 어디로

`REFILL_REQUESTED` 에는 대상이 없다(detail 이 빈다). 보충 goal(`Refill`)도 밖에서 안 보인다.
그래서 서버가 만든다. 조제기 상태와 선반 JSON 을 쓴다. 끝난 뒤의 실제 값은 `last_refill` 이다.

| 필드 | 뜻 |
|---|---|
| `item_id` | 보충 중인 약(`refilling_item_ids` 의 한 칸) |
| `slot_name` | `"A"` \| `"B"` \| `null`. 그 약의 빈 슬롯(`count == 0`) 중 A 가 먼저다. orchestrator `refill_planner.target_slot` 과 같은 규칙이다. 빈 슬롯이 없으면 `null` |
| `kind` | `cylinder` \| `module` \| `null`. `/m0609/shelf/inventory` 의 `items` 표, 없으면 칸(`cells[].item`·`type`)에서. 선반 JSON 을 못 받았으면(v1 장면·스텁) `null` |
| `target` | `round` \| `module` \| `null`. `kind` 에서 정한다(cylinder → round, module → module — 팔의 장면 v2 와 같은 짝) |

#### `dispenser.container_read` — 약통 QR 판독

`/m0609/hand_camera/tag_reads` 의 `KIND_CONTAINER` 마지막 한 건이다. 팔의 약통 확인(`container_check`,
`tools/demo_v2.sh` 의 `P3_CONTAINER_QR=1`)을 켠 기동에서 온다. 병원 기본은 1이다. 실제 판독을 받기 전에는 `null`이고, 일반 개발 구성에서는 생산자가 없을 수 있다.
리셋(`RESET_BEGIN`)에서 `null` 로 돌아간다.

| 필드 | 뜻 |
|---|---|
| `tag_id` | 읽은 QR 원문(`cn-NNNN`). 못 읽었으면 빈 문자열 |
| `status` | `"ok"` \| `"unreadable"` |
| `stamp` | 판독의 sim 시각 |
| `wall`, `age_wall_s` | 서버가 받은 wall 시각과 그 뒤 초 |

**허용·거부 판정은 없다.** 팔이 `/orchestrator/check_container` 에 묻고 받은 답은 토픽에 실리지 않는다.
이벤트에도 실리지 않는다. 팔의 `/rosout` 줄에만 있다. 새 토픽은 만들지 않는다.

#### `dispenser.last_refill` — 마지막 보충 한 장

현재 **epoch** 의 마지막 `REFILL_DONE` 요약이다. 보충 이력이 없으면 `null`.

> **리셋하면 `null` 로 돌아간다.** 이벤트를 `epoch` 으로 거르기 때문이다. 화면은 세대가
> 바뀌면 이 칸을 비워야 한다.

| 필드 | 뜻 |
|---|---|
| `stamp` | 그 `REFILL_DONE` 의 sim 시각 |
| **`parsed`** | **구조 파싱이 됐는가.** `false` 면 아래 필드가 전부 `null` |
| `item` | `drug-amox` 등 |
| `slot` | **`"A"` / `"B"`** — `slots[].slot_name` 과 **같은 형태**다 |
| `kind` | `cylinder` \| `module`. 모르는 값이면 `null` |
| `target` | `round` \| `module`. 모르는 값이면 `null` |
| `cell` | 선반 칸 (`floor_left/r0c1` 등) |
| `seed`·`draw` | 선반 랜덤 파지 **재현용** 정수. 화면에 안 그려도 된다 |
| `clearance` | m 단위 |

**`parsed` 는 장면 버전이 아니다.** 서버는 장면 버전을 모른다 — `detail` 이 JSON 으로 읽혔는지
만 말한다. 이 값으로 장면 버전을 판단하지 마라.

#### `dispenser.stock` — 재고 한눈에(재범 9/29 N3)

"현재 알약통 N개·모듈 N개·지금 조제기에 N개". 선반은 스테이지 재고 JSON(`/m0609/shelf/inventory` 의 `cells[].present`),
조제기는 `DispenserSlot`, 보충 횟수는 이 세대의 `REFILL_DONE` 이다.

```json
"stock": {
  "shelf": { "cylinder": { "present": 8, "total": 9 }, "module": { "present": 9, "total": 9 } },
  "canisters_loaded": 2,
  "pouches_by_item": { "drug-amox": 2, "drug-ibu": 5 },
  "refills": { "cylinder": 1, "module": 0 }
}
```

| 필드 | 뜻 |
|---|---|
| `shelf` | 약통 종류마다 선반에 남은 칸(`present`)과 칸 수(`total`). 재고 JSON 을 받은 적 없으면 `null` |
| `canisters_loaded` | 조제기 슬롯 중 `count > 0` 인 수(약통이 든 슬롯) |
| `pouches_by_item` | 약품마다 조제기 슬롯 `count` 합(낼 수 있는 봉투 수) |
| `refills` | 이 세대의 `REFILL_DONE` 수, 약통 종류별(`last_refill.kind` 와 같은 값). 종류를 못 읽은 보충은 안 센다 |

- 병원(preset `hospital`)은 선반을 가득(18/18) 채우고 **조제기에 넣은 약통은 선반으로 안 돌아온다**(스테이지
  `--workcell-consume`). 그래서 `shelf.*.present` 는 보충마다 하나씩 준다. 리셋하면 다시 가득이다.
- 잡고 있는 약통도 그 순간 `present: false` 다(들린 칸). 놓인 뒤 되돌아오지 않으면 그대로 빈 칸이다.

**`DispenserSlot` 에 `capacity` 는 없다 — 넣지 않는다.** `item_id`, `slot`, `lot_id`, `expiry`,
`count`, `active` 가 전부다. msg 확장도 하지 않는다(보호 경로·계약 변경이고 시연 전 가치가 없다).
재고는 **숫자 `count` 로 표시**한다. 기준치를 가정한 막대는 만들지 않는다.

---

## 7. 명령 API (2단계, 기본 403)

`--allow-commands` 없이 뜨면 두 엔드포인트 모두 **403 `commands_disabled`**.

### 7.1 POST /api/reset

`{}` → **202 Accepted**

```json
{ "ok": true, "accepted": true }
```

**동기 응답에 `epoch` 이 없다.** 리셋은 서버 탐색을 포함해 **30 s 이상** 걸릴 수 있어서
HTTP 를 붙들지 않는다. 프론트는 202 를 받으면 "리셋 요청됨"만 표시하고,
**새 epoch 은 WS 로 오는 `snapshot`(`reset_in_progress: true`)에서 읽는다.**

호출하는 서비스:

```
ros2 service call /orchestrator/reset rokey_p3_interfaces/srv/Reset "{epoch: 0}"
→ Reset_Response(ok=True, message='epoch=2')
```

- 타입은 `rokey_p3_interfaces/srv/Reset`. **새 srv 를 만들지 않는다.**
- **요청의 `epoch` 값은 무시된다** — orchestrator 가 항상 현재 epoch + 1 을 쓴다(관측).
  그래서 웹은 epoch 을 고를 수 없고, 서버는 `{epoch: 0}` 으로 보낸다.
- **응답의 `message` 를 파싱하지 마라.** `'epoch=2'` 는 사람이 읽는 문자열이다.
  새 epoch 은 뒤따르는 **`RESET_BEGIN` 이벤트의 `epoch`** 로 채운다 — 그게 정본이다.

서비스 호출 자체가 실패하면(서버 없음·타임아웃) `503 no_ros`.

### 7.2 POST /api/requests

```json
{
  "request_id": "web-0001",
  "mode": 1,
  "destination_id": "bed_a1",
  "orders": [
    { "order_id": "ord-31", "patient_id": "p-7", "item_id": "drug-ibu" }
  ]
}
```
→
```json
{ "ok": true, "request_id": "web-0001", "mode_source": "web_request",
  "destination_id": "bed_a1", "destination_source": "order_pool", "order_ids": ["ord-31"] }
```

`destination_id`·`destination_source` 는 아래 "1인·긴급은 목적지를 풀에서 자동으로 채운다" 를 본다. `order_ids` 는 보낸 주문 순서 그대로다.

기존 `/deliver` 액션 경로로만 보낸다. orchestrator 수락 조건은 그대로다:
`request_id` 가 새 것, `orders` 가 비지 않음, `destination_id` 가 `zones.yaml` 에 있음,
모든 `order_id` 가 주문 풀에 있고 미사용, **진행 중 트립이 없음**.

`orders` 에 **여러 건을 넣으면 묶음 요청**이 된다. 지금 order_pool 은 주문 1건 = 요청 1건
구조라 묶음을 만드는 발행기가 없다 — **웹이 묶음을 만드는 첫 경로다.** 프론트는 §7.3 의 풀에서
여러 주문을 골라 한 요청으로 묶을 수 있어야 한다.

거부되면 goal 거부이고 **Event 가 안 나온다**. 서버는 `409 rejected` 로 돌려주고,
`message` 에 어느 조건에서 걸렸는지 적는다.

#### 검사 순서

`orchestrator_node._on_deliver_goal`(:303-325) 원문과 **같은 순서**로 검사한다.
여러 조건이 한꺼번에 걸려도 실물과 같은 코드가 나오게 하려는 것이다.

| # | 검사 | `code` |
|---|---|---|
| 0 | 본문 형식 (`request_id` 없음, `order_id` 없음) | 400 `bad_request` — 우리 입력 검사다 |
| 0.5 | **모드와 주문 수** | 400 `bad_mode_for_orders` |
| 0.6 | **병실 묶음에 두 병실** | 400 `mixed_rooms` — 우리 검사다(orchestrator 는 병실을 모른다) |
| 1 | 리셋 barrier 중 | `barrier_running` |
| 2 | `RESET_DONE` 뒤 3.5 s 안 (§1.4) | `barrier_running` |
| 3 | `orders` 가 비었다 | `empty_orders` |
| 4 | `request_id` 중복 | `duplicate_request_id` |
| 5 | 구역 ID 정규식 | `bad_destination` |
| 6 | 주문 풀에 없다 | `unknown_or_used_order` |
| 7 | 이미 쓴 주문 | `unknown_or_used_order` |
| 7.5 | **그 약품이 재고 0·PAUSED** | `refill_in_progress` |
| 7.6 | **요청 개수 > 가용 재고** | `insufficient_stock` |
| 8 | 진행 중 트립 | `trip_in_progress` |

예: 트립이 열려 있고 주문도 이미 쓰였다면 **`unknown_or_used_order`** 가 나온다(7이 8보다 앞).

**모드·주문 수를 맨 앞에 두는 이유**: 입력이 **스스로 모순**이라 서버 상태를 보기 전에 답할 수
있다. 그래야 사람이 "기다리면 되나?" 로 헷갈리지 않는다 — 기다려도 안 풀린다.

#### `refill_in_progress` — 무엇을 보고 막나

요청한 주문의 `item_id` 가 지금 낼 수 없는 약품이면 **보내기 전에** 막는다. 판정은
snapshot 의 `dispenser` 만 본다:

- `paused_item_ids` 에 있거나
- 그 약품을 담은 슬롯이 **전부** `count == 0` 이거나 `active == false`

**슬롯에 그 약품이 아예 없으면 막지 않는다** — 모르는 것으로 거부하지 않는다.

> **왜 막나**: orchestrator 는 이 요청을 **수락한 뒤** 적재에서 `ABORT`(reason `out_of_stock`)로
> 끝낸다. 실습8 에서 `web-0002`(`ord-0003` amox)가 201.767 → 202.950, **1.2 s 만에** 그렇게
> 죽었다. 사람이 보기엔 "넣었는데 갑자기 죽었다" 다. 미리 막으면 그 자리에서 이유를 말할 수 있다.

#### `insufficient_stock` — 묶음 안에서 서로 잡아먹는 것

`refill_in_progress` 는 **요청 시점에 이미 재고 0** 인 품목만 막는다. **묶음 안에서 주문들이
서로 잡아먹는 것은 못 막는다.**

> 실습9: amox 재고가 **1** 인데 묶음에 amox 주문이 **2개** 들어갔다. 앞의 것이 마지막 1개를 쓰고
> `REFILL_REQUESTED` 가 나갔고, 뒤의 `ord-0003` 은 `ABORT`(reason `out_of_stock`)로 끝났다.
> 시연 화면에 `주문 중단 — ord-0003 (사유: out_of_stock)` **error 알람이 남는다.**

요청한 주문들을 **품목별로 세서**, 그 품목의 **활성 슬롯 `count` 합**보다 많으면 거부한다.
판단 근거는 snapshot 의 `dispenser` 뿐이고, **슬롯에 아예 없는 품목은 막지 않는다**(§7.2 의
`refill_in_progress` 와 같은 원칙 — 모르는 것으로 거부하지 않는다).

**모자란 것을 전부 싣는다.** 한 건만 말하면, 두 품목이 모자랄 때 운영자가 하나를 빼고 다시
보내 **두 번째 거부를 받는다.**

```json
{"error": {"code": "insufficient_stock",
           "message": "재고 부족 — drug-amox 2개 필요, 1개 가능 (그 밖에 drug-ibu 2/1)",
           "detail": {"item_id": "drug-amox", "requested": 2, "available": 1,
                      "shortages": [{"item_id": "drug-amox", "requested": 2, "available": 1},
                                    {"item_id": "drug-ibu",  "requested": 2, "available": 1}]}}}
```
위 세 키는 **`shortages[0]` 과 같다**(대표 한 건). `shortages` 는 **품목 이름 순**이라 같은 요청이
매번 같은 순서를 낸다.

| | |
|---|---|
| `requested` 의 단위 | **주문 수**다. **지금은 1주문 = 1개**다 — `order_pool.yaml` 의 주문에 수량 필드가 없다(§7.3). 수량이 생기면 이 문장을 같이 고쳐야 한다 |
| `available` 의 시점 | **거부를 만든 그 순간**의 `dispenser` 값. 보충이 돌고 있으면 읽는 사이에 바뀐다 |

> **기본 풀로는 이 거부를 만들 수 없다.** `order_pool.yaml` 은 주문이 4건인데 시작 재고가
> 그보다 많아서 모자랄 수가 없고, 재고가 0 으로 떨어지면 `refill_in_progress` 가 먼저 잡는다.
> 실물에서는 **재고가 줄어든 뒤에** 난다(실습9 는 amox 가 1 이었다).
> **확인하려면 `--order-pool` 로 재고보다 주문이 많은 풀을 넣어라** — 그래야 조건이 만들어진다.

**`out_of_stock`(ABORT)과 같은 현상의 앞뒤다.** `insufficient_stock` 은 **넣기 전에 막은 것**,
`out_of_stock` 은 **돌다가 죽은 것**이다. 운영자가 할 일이 다르므로 이름을 나눴다 — 앞은
"주문을 빼거나 보충을 기다린다", 뒤는 "이미 실패했으니 기록을 본다".

#### `mixed_rooms` — 왜 필요한가

계약(`DeliveryRequest.msg`)의 mode 2 는 **"한 병실의 병상을 차례로"** 다. 그런데 `trip_fsm._build_stops` 는
병실을 모른다 — 주문마다 풀의 병상으로 정거장을 만들어 그대로 돈다. 그래서 C1·C2 병상을 섞은 병실
묶음이 **조용히 수락돼 두 병실을 한 트립으로 돈다.** 웹이 보내기 전에 막는다.

- 병실은 zones 의 bed `room` 이다(병원: 생성기가 낸다, §7.4). 주문 → 병상은 주문 풀의 `bed`.
- **병실을 모르는 주문은 판단에서 뺀다.** zones 에 `room` 이 없는 월드(빈월드·조제실)는 지금처럼 통과한다.
- 병동 묶음(mode 3)은 병동 보관함 하나로 가므로 병실이 섞여도 된다.
- 입력이 스스로 모순이라 0.5 바로 뒤, 서버 상태보다 먼저 답한다 — 기다려도 안 풀린다.

```json
{"error": {"code": "mixed_rooms", "message": "병실 묶음은 한 병실만 — C1 2건, C2 1건",
  "detail": {"mode": 2, "rooms": [{"room": "C1", "order_ids": ["ord-0001", "ord-0002"]},
                                  {"room": "C2", "order_ids": ["ord-0005"]}]}}}
```

#### `bad_mode_for_orders` — 왜 필요한가

`trip_fsm._build_stops` 는 **single·urgent 모드에서 주문이 1개가 아니면 정거장을 만들지 않는다.**
그러면 goal 이 **사유 없이** 거부된다. 실습8 의 묶음 거부 2회(18:20:54·18:21:54)가 이것이고,
웹에는 `409 "orchestrator 가 요청을 거부했다 (사유 없음)"` 만 떴다. 진짜 사유는 스택 로그의
`Deliver goal 거부: 진행 중 트립이 있거나 정거장을 만들 수 없다` 에만 있었다.

묶음(mode 2·3)에 주문이 **1건**인 것은 막지 않는다 — 계약에 그런 제약이 없다.

8번은 실물에서 `fsm.accepts` 실패이고, 사유가 "진행 중 트립" 말고 **"정거장을 만들 수 없다"**
(예: 묶음인데 destination 종류가 안 맞음)일 수도 있다. 밖에서 둘을 구분할 수 없어,
**트립이 실제로 열려 있을 때만 `trip_in_progress`** 이고 그렇지 않으면 `rejected` 다.

#### destination_id 는 정규식으로만 검사한다

**orchestrator 는 `zones.yaml` 을 읽지 않는다.** 구역 ID 모양만 맞으면 수락한다.

```
^(pharm|load|dock_[1-9][0-9]*|ward_[a-z]|station_[a-z]|room_[a-z][0-9]+|bed_[a-z][0-9]+)$
```

(`rokey_p3_navigation/zones.py` 의 `_ZONE` 원문과 같다 — `web/backend/app/zones.py` 의 `ZONE_ID_RE`.
dock 은 1 부터이고 앞자리 0 이 없다. §9.)

> **주의 — 수락된다고 갈 수 있는 것은 아니다.**
> `zones.yaml` 에 없는 구역도 이 검사를 통과한다. 그런 요청은 수락된 뒤 실물 fleet 의
> `GoToZone` 거부로 드러난다 → `HOLD_RETURN`(`reason: goto_rejected`).
> **`pharmacy_only` 모드에서는 아예 드러나지 않는다** — 병동에 가지 않기 때문이다.
>
> 지금 `zones.yaml` 에 있는 구역은 `load`, `dock_1`, `bed_a1`, `station_a` **넷뿐이고 좌표는 전부 0**
> (미측정)이다. 그런데 `order_pool.yaml` 은 `bed_a2`, `bed_b1`, `bed_b2` 를 쓴다 —
> **이 셋은 zones 에 없다.** 풀에서 고른 대로 보내면 실물에서 `goto_rejected` 가 난다.
> 프론트는 §7.4 의 후보 목록에 없는 목적지를 고를 때 **경고를 보여 주는 편이 좋다.**

#### 1인·긴급은 목적지를 풀에서 자동으로 채운다

> **그래서 1인·긴급에서는 위 정규식 검사가 사실상 걸리지 않는다.** 덮어쓰기가 검사보다
> 먼저 일어나므로, 모양이 틀린 `destination_id` 를 보내도 풀의 침상으로 바뀌어 **수락된다.**
> **풀에 그 주문의 침상이 없을 때만** 보낸 값이 그대로 쓰이고 검사에 걸린다.
> 이것은 **의도가 아니라 알려진 구멍**이다 — 보낸 값이 틀렸는데 아무도 말해 주지 않는다.
> 고치는 방향은 "보낸 값이 비어 있지 않으면 모양을 검사한다" 이고, 별도 PR 로 다룬다.

**1인(`mode 0`)·긴급(`mode 1`)의 실제 목적 침상은 요청의 `destination_id` 가 아니라
주문 풀의 환자→`bed` 매핑이 우선한다.** 서버가 자동으로 바꿔 넣는다.

묶음(`mode 2`·`3`)은 풀에 표현이 없으므로 **사람이 고른 `destination_id` 를 그대로 쓴다.**

응답의 `destination_source` 가 어느 쪽이 이겼는지 말해 준다.

| `destination_source` | 뜻 |
|---|---|
| `"order_pool"` | 풀의 `bed` 로 바꿔 넣었다 (1인·긴급) |
| `"request"` | 요청에 적힌 값을 그대로 썼다 |

프론트는 **응답의 `destination_id` 를 확인해서 화면에 반영**해야 한다 — 보낸 값과 다를 수 있다.

```json
{ "error": { "code": "rejected", "message": "진행 중 트립이 있다" } }
```

`destination_id` 는 `bed_a1` / `room_a1` / `station_a` 형식.

### 7.3 GET /api/order_pool

`order_id` 는 **주문 풀에 있고 미사용**이어야 수락된다. 웹에서 자유 입력을 받으면 거의 항상
거부되므로, 서버가 고를 수 있는 목록을 준다.

```json
{
  "source": "file",
  "orders": [
    { "order_id": "ord-0002", "patient_id": "1002", "item_id": "drug-ibu",
      "bed": "bed_a2", "mode": "urgent", "mode_value": 1, "used": false }
  ],
  "problems": []
}
```

| 필드 | 뜻 |
|---|---|
| `bed` | 이 환자의 침상. **1인·긴급이면 서버가 `destination_id` 를 이 값으로 덮는다**(§7.2) |
| `mode` / `mode_value` | 풀이 권하는 모드. `single`(0) 또는 `urgent`(1). 없으면 `single` |
| `used` | 이미 쓰인 주문. **`true` 는 고를 수 없다** |

`source` — `"file"`(`--order-pool` 로 준 파일) /
`"repo_default"`(기본: **저장소의 `src/rokey_p3_orchestrator/config/order_pool.yaml` 원문**.
orchestrator 가 읽는 그 파일이고 **실물·mock 이 같다**) /
`"fixture"`(저장소 밖 mock) / `"none"`(풀을 모른다).

> **풀이 비면 주문 검사가 통째로 건너뛰어진다.** 그러면 웹이 없는 주문도 수락해 버리고,
> 거부는 실물 goal 거부로만 드러난다(사유 없이). 풀을 못 읽으면 `problems` 를 봐라.

#### 파일 스키마 (하나로 고정)

```yaml
version: 1
orders:
  - {order_id: ord-0001, patient_id: "1001", item_id: drug-amox, bed: bed_a1}
  - {order_id: ord-0002, patient_id: "1002", item_id: drug-ibu, bed: bed_a2, mode: urgent}
```

> **숫자로 보이는 ID 는 따옴표가 필수다.** `patient_id: 1001` 처럼 쓰면 YAML 이 정수로 읽고
> orchestrator 가 거부한다. 서버는 이런 항목을 **조용히 고치지 않고 버린 뒤 `problems` 에 적는다** —
> 고쳐 주면 웹에서는 되는데 실물에서만 터지는, 제일 찾기 어려운 버그가 된다.

`problems` 는 버려진 항목의 이유 목록이다. 비어 있어야 정상이고, 비어 있지 않으면 **화면에 보여
주는 편이 좋다** — 풀 파일이 잘못됐다는 뜻이다.

#### 묶음은 웹이 만든다

풀에는 묶음 표현이 없다(주문 1건 = 요청 1건). **웹이 주문 여러 개를 골라 `mode` 2·3 과
`destination_id` 를 직접 정하는 것이 묶음을 만드는 첫 경로다.**

- 병실 묶음(mode 2)은 **한 병실의 주문만** 고른다. 병실은 §7.4 의 `group` 이다. 섞이면 400 `mixed_rooms`(§7.2).
  orchestrator 는 목적지를 보지 않고 주문 풀의 침상을 차례로 돈다.
- 병동 묶음(mode 3)은 `destination_id` 가 스테이션(`station_a`)이고 병실이 섞여도 된다. 스테이션 보관함 하나에 넣는다.

#### 병원 주문 풀

`order_pool.hospital.yaml`(원문은 #553 의 `src/rokey_p3_orchestrator/config/`)은 침상 10개(D1–D10)에 한 건씩,
`ord-0002`(bed_a2)만 `urgent` 다. main 에 들어오기 전에는 개발용 사본 `web/backend/fixtures/order_pool.hospital.dev.yaml`
을 쓴다(§10.6). 재고: 기본 조제기(`dispenser.yaml`)는 amox·ibu 각 10개라 10건을 보충 없이 다 낸다(§12.1).

#### 리셋하면 풀이 되살아난다

orchestrator 는 리셋 때 `_reload_stores` 로 재고·선반을 파일 값으로 되돌리고
**`_used_requests` 와 `_used_orders` 를 둘 다 비운다**(계약 6절 3).

- 시점은 `/sim/reset` 이 ok 한 뒤 — 즉 **`RESET_DONE` 이다.** `RESET_BEGIN` 만으로는 아직 아니다.
- 그래서 `RESET_DONE` 이 지나가면 `used` 가 전부 `false` 로 돌아가고, **`request_id` 도 다시 쓸 수 있다.**

그래도 웹이 만드는 `request_id` 는 **매번 새 것으로** 만드는 편이 안전하다
(예: `web-<epoch 3자리>-<seq 4자리>`). 발행기가 `r<epoch>-<seq>` 를 쓰므로 **접두를 다르게** 한다.

### 7.4 GET /api/destinations

목적지 후보 목록. **표시 전용이고 검증에 쓰지 않는다**(검증은 §7.2 의 정규식).

```json
{
  "source": "file",
  "destinations": [
    { "destination_id": "bed_a1", "kind": "bed", "group": "C1", "group_label": "C1 병실",
      "ward": "W1", "ward_label": "1병동", "label": "D1" },
    { "destination_id": "station_a", "kind": "station", "group": null, "group_label": null,
      "ward": null, "ward_label": null, "label": null }
  ]
}
```

`kind` 가 `bed`·`room`·`station` 인 구역만 나온다 — `load`·`dock` 은 배송 목적지가 아니다.
**번호 순**이다(`bed_a2` 가 `bed_a10` 앞). 화면은 받은 순서대로 그린다.

| 필드 | 뜻 | 출처 |
|---|---|---|
| `group` | 병실 ID. 화면이 칸을 나누는 키 | zones bed 의 `room` |
| `group_label` | `"C1 병실"` | 서버가 `group` 에서 만든다 |
| `ward` / `ward_label` | 병동 ID / `"1병동"`(`W<n>` → `<n>병동`) | zones bed 의 `ward` |
| `label` | 병상 이름표(병원: PDF 번호 `D1`–`D10`) | zones bed 의 `label` |

zones 에 그 필드가 없으면 **null** 이다(station, 빈월드·조제실 zones). 웹은 ID 글자로 짐작하지 않는다.
병원 값(`zones.hospital.yaml`)은 생성기 `sim/standalone/p3sim/hospital_nav.py` 가 낸다 — 9/23 에 정한 대응:
C1 = D1–D4(`bed_a1`–`a4`), C2 = D5–D10(`bed_b1`–`b6`), 병동은 W1 하나.
`source` 는 `"file"`(`--zones-file`) / `"repo_default"`(저장소 `src/rokey_p3_description/config/zones.yaml` 원문) /
`"mock"`(둘 다 못 찾을 때의 고정 목록: `bed_a1`, `station_a`). §7.5 도 같다.

**이 목록에 없는 목적지도 §7.2 는 수락한다.** 후보에 없는 것을 고르면 화면에서 경고하는 편이 좋다 —
실물에서 `goto_rejected` 로 끝날 가능성이 높다.

### 7.5 GET /api/zones

평면도용 **전 구역**(`load`·`dock` 포함)과 자세. 목적지 후보만 필요하면 §7.4 를 쓴다. 번호 순이다.

```json
{
  "source": "file",
  "frame": "map",
  "zones": [
    { "zone_id": "bed_a1", "kind": "bed", "x": 23.805, "y": 7.375, "yaw": 0.0,
      "group": "C1", "group_label": "C1 병실", "ward": "W1", "ward_label": "1병동", "label": "D1" },
    { "zone_id": "dock_1", "kind": "dock", "x": -8.238, "y": 4.169, "yaw": -1.571,
      "group": null, "group_label": null, "ward": null, "ward_label": null, "label": null }
  ]
}
```

`x`·`y`·`yaw` 는 zones 파일 값(map, m·rad)이고, 없으면 null 이다(mock 기본 목록). 화면은 그 구역을 그리지 않는다.
나머지 필드는 §7.4 와 같다. `source` 도 §7.4 와 같다.

### 7.6 GET /api/map · GET /api/map/image

`--map-file` 로 준 Nav2 지도다. 안 주면 둘 다 404 `map_unavailable` 이다. 화면은 지도 칸을 감춘다. 파일을 못 읽어도 404 다. `message` 에 이유가 있다.

```json
{
  "source": "file", "frame": "map", "image_url": "/api/map/image",
  "width": 859, "height": 534, "resolution": 0.05, "origin": [-12.25, -6.5, 0.0],
  "negate": 0, "occupied_thresh": 0.65, "free_thresh": 0.196
}
```

- `/api/map/image` 는 **PGM(P5) 원본 바이트**(`application/octet-stream`)다. 서버는 바꾸지 않는다.
- 픽셀 ↔ map: PGM **첫 행이 위(y 최대)** 다. 칸 (col, row) 의 중심은
  `x = origin[0] + (col + 0.5)·resolution`, `y = origin[1] + (height − row − 0.5)·resolution`.
  `origin[2]`(yaw)가 0 이 아니면 돌려야 한다 — 병원 지도는 0 이다.
- 값의 뜻은 map_server 규약이다. `negate`, `occupied_thresh`, `free_thresh` 다. 병원 지도는 `trinary` 다. 0 은 막힘이다. 254 는 빈 곳이다. 205 는 모름이다.

`demo_v2.sh` 의 `P3_WORLD=hospital` 이 `--map-file "$P3_HOSPITAL_MAP"` 을 넘기면 켜진다.

**AMR 위치 주기.** 실측은 9/23 이다. 스텁 한 바퀴다. TF 는 10 Hz 다. WS 는 40 s 와 70 s 다. snapshot 은 4.86–4.89 Hz 다. 그중 자세가 바뀐 것은 4.85–4.86 Hz 다. 간격 최대는 0.42 s 다. 서버가 TF 를 5 Hz 로 조회한다. WS 가 0.2 s 로 합친다. 그래서 5 Hz 가 상한이다. 화면은 두 자세 사이를 보간하면 부드럽다.

### 7.7 GET /api/queue

촬영 화면의 주문 큐. **주문 풀 순서**로 셋으로 가른다. 현재 epoch 기준이다(리셋하면 다시 전부 대기).

```json
{
  "epoch": 1,
  "waiting":     [{ "order_id": "ord-0008", "patient_id": "2008", "item_id": "drug-ibu", "bed": "bed_b4",
                    "group": "C2", "label": "D8", "mode": "single", "request_id": null, "outcome": null }],
  "in_progress": [{ "order_id": "ord-0007", "...": "…", "request_id": "r001-0007", "outcome": "in_progress" }],
  "done":        [{ "order_id": "ord-0001", "...": "…", "request_id": "r001-0002", "outcome": "delivered" }],
  "counts": { "waiting": 1, "in_progress": 1, "done": 8 }
}
```

| 칸 | 뜻 |
|---|---|
| `done` | `outcome`(§1.5)이 `delivered`·`pharmacy_done`·`held`·`aborted`·`timeout` |
| `in_progress` | 상태가 왔는데 안 끝났다. 또는 요청에 실려 쓰였는데 아직 상태가 없다 |
| `waiting` | 풀에 있고 아직 어느 요청에도 안 실렸다 |

- `done` 에는 `held`·`aborted` 도 있다 — 끝났다는 뜻이지 성공이 아니다. 화면은 `outcome` 으로 갈라 그린다.
- 풀에 없는 주문의 상태가 오면 뒤에 붙인다(`bed` 등은 null). 조용히 빼지 않는다.
- `group`·`label` 은 zones 의 `room`·`label`(§7.4). WS 로는 안 온다 — 1 Hz 정도로 불러 쓴다.

---

## 8. --mock 모드

ROS 없이 녹화 fixture(JSON)를 재생해 **위와 똑같은 API** 를 낸다. 프론트는 이 모드로 개발한다.

```
python -m app.main --mock                 # 실시간 속도
python -m app.main --mock --speed 5       # 5배속
python -m app.main --mock --loop          # 끝나면 처음부터
```

fixture 는 둘이다. `--fixture` 로 고른다(기본은 첫째).

| 파일 | 내용 | 만든 방법 |
|---|---|---|
| `fixtures/pharmacy_loop.json` | **조제실 한 바퀴(pharmacy_only) + 보충 + 리셋 1회 + 리셋 뒤 새 요청** | `make_pharmacy_loop.py`(합성) |
| `fixtures/hospital_trip.json` | **병원: 긴급 → 병실 묶음 C1(병상 셋) → 병동 묶음(스테이션) → 리셋 → 리셋 뒤 긴급** | `record_fixture.py`(스텁 스택 **녹화**) |

`hospital_trip.json` 은 실물 오케스트레이터가 낸 이벤트를 그대로 담았다 — 이름·순서·detail 이 계약 그대로다.
다시 만들 때는 스텁 스택을 띄우고 `record_fixture.py` 로 녹화한다(파일 머리 참고). 손으로 고치지 않는다.
두 fixture 모두 로봇 자세는 없다 — 평면도를 켜면(`--map-file`) mock 이 AMR 을 `dock_1` 에 세운다(§1.6).
**재생이 끝나면 `CLOCK_STOPPED`·`STATUS_STALE` 이 뜬다**(끝난 fixture 라서). 화면 개발은 `--loop` 로 띄운다.

`pharmacy_loop.json` 에 대해:

`REQUEST_ACCEPTED.detail` 은 **두 경우를 다 담았다** — `req-0001` 은 §1.3 의 JSON(파싱 성공,
`mode_source="event_detail"`), `req-0002` 는 빈 문자열(파싱 실패, `mode_source=null`).
프론트는 한 번 재생하면 두 화면을 모두 볼 수 있다.

mock 에서도 `--allow-commands` 를 주면 §7 의 두 명령이 동작한다. `POST /api/reset` 은
`RESET_BEGIN` 을 넣어 **epoch 전환 화면을 시험할 수 있게** 하고, `POST /api/requests` 는
`mode_source="web_request"` 경로를 낸다. 실물 ROS 를 부르는 게 아니라 흉내다.
이벤트 이름·순서는 `src/rokey_p3_bringup/test` 의 기대 순서와 `Event.msg` 상수를 따른다.

---

## 9. 원문 대조 결과

저장소 원문과 맞춘 것 (2026-09-17, `9b61659`):

| 항목 | 결과 |
|---|---|
| `status_view.TRIP_PHASES` 22개 | **일치.** 이제 베끼지 않고 `import` 해서 쓴다 |
| `status_view.SIGNALS` · 신선도 임계 | **일치.** 마찬가지로 `import` |
| `status_view.event_key` | **빠져 있던 것을 넣었다** — §0.3 |
| `StatusModel.note_*` dict 키 | `event`·`order`·`dispenser`·`signal`·`cabinet` 모두 맞다. 단 `note_order` 의 `state` 는 **이름 문자열**이다(우리 API 는 숫자 + `state_name`) |
| `zones.py` 구역 ID 정규식 | **고쳤다.** dock 은 `dock_[1-9][0-9]*` — `dock_0`·`dock_01` 은 구역이 아니다 |
| `CabinetObservation.msg` | **일치**(`header`·`cabinet_id`·`order_id`·`present`) |
| `BeltState.msg` | **H(5 Hz) 확인.** "unknown 이면 배출도 픽도 못 한다" |
| `DispenserSlot.msg` | **`capacity` 없음 확인.** 만들지 않은 판단이 맞다 |
| `order_pool.yaml` · `zones.yaml` | **일치.** 사본이 원문과 같다 |
| `ruff.toml` | **일치** |
| `OrderStatus.STATE_SUCCESS` | **orchestrator 가 발행하지 않는다** — §1 |

남은 것:

| # | 항목 | 상태 |
|---|---|---|
| 1 | `REQUEST_ACCEPTED.detail` 의 compact JSON | **해결됨.** #104 머지, 원문 `request_summary` 와 왕복 테스트까지 |
| 2 | 실물 ROS 브리지 | **해결됨.** `ros_bridge.py` 가 `ros_spec.py` 의 표대로 구독한다. TF 조회(§1.6)도 같은 노드다 |

### 9.1 알아 둘 불일치

`order_pool.yaml` 은 `bed_a2`·`bed_b1`·`bed_b2` 를 쓰는데 **`zones.yaml` 에는 이 셋이 없다**
(지금 있는 구역은 `load`·`dock_1`·`bed_a1`·`station_a` 넷뿐이고 좌표는 전부 0).
풀에서 고른 대로 보내면 §7.2 의 검사는 통과하지만 실물 fleet 의 `GoToZone` 이 거부한다
→ `HOLD_RETURN`(`reason: goto_rejected`). `pharmacy_only` 에서는 드러나지 않는다.

병원 월드에는 이 불일치가 없다. `order_pool.hospital.yaml` 의 침상 10개가 `zones.hospital.yaml` 에 다 있다. #553 의 생성기 시험이 지킨다. 시험 이름은 `test_hospital_order_pool_covers_every_bed_once` 다. #553 은 2026-09-23 에 main 에 들어왔다.
`v1.1.0` 의 `order_pool.hospital.yaml` 은 13건이다. 침상 10건 뒤에 테이블 3건(`ord-0011` → `station_b`, `ord-0012` → `station_c`, `ord-0013` → `station_d`)이 있다. 세 구역도 `zones.hospital.yaml` 에 있다.

---

## 10. 띄우는 방법

### 10.1 개발 (프론트·백엔드 공용)

```
python -m app.main --mock                 # ROS 없이 fixture 재생, 127.0.0.1:8000
```

ROS 도, Isaac 도, colcon 도 필요 없다. 프론트는 이것만 쓴다.

**교차 출처(CORS):** `--mock` 일 때만 `Access-Control-Allow-Origin: *` 를 붙인다.
프론트가 다른 포트에서 정적 파일을 띄워 개발할 수 있게 하려는 것이다.
**실물 모드에서는 켜지 않는다** — 그때는 같은 출처로 서빙하거나 리버스 프록시를 둔다.

**같은 출처로 쓰려면** 프론트 빌드 디렉터리를 넘긴다. 그러면 CORS 자체가 필요 없다.

```
python -m app.main --mock --static ../frontend
```

정적 서빙은 API 라우트 **뒤에** 걸리므로 `/api/*` 와 `/ws` 를 덮지 않는다.

### 10.2 ROS 실물 연결 확인

```
ROS_DOMAIN_ID=118 ros2 launch rokey_p3_bringup stub_loop.launch.py pharmacy_only:=true
ROS_DOMAIN_ID=118 python -m app.main
```

`ROS_DOMAIN_ID` 는 **118**. (115 통합, 117 master02 개발과 겹치지 않게.)

### 10.3 시연

시연·회차에서는 `tools/demo_v2.sh up` 이 웹을 tmux `p3v2-web` 으로 띄운다(`web_cmd`). 인자는 이렇다.

```
python -m app.main --host $P3_WEB_HOST --port $P3_WEB_PORT --allow-commands --static <저장소>/web/frontend
    --order-pool $P3_ORDER_POOL --zones-file $P3_ZONES --catalog $P3_CATALOG
    --dispenser-file $P3_DISPENSER_FILE     (P3_DISPENSER_FILE 이 있을 때)
    --map-file $P3_HOSPITAL_MAP             (P3_WORLD=hospital 일 때)
    --roles "<역할>" --peer <상대 주소>      (두 PC 모드일 때)
```

`tools/demo_v2.sh cmds` 가 실제로 칠 한 줄을 보여 준다.

- `P3_WEB_HOST`·`P3_WEB_PORT` 기본은 `127.0.0.1`·`8000` 이다.
- `--live-sensors` 는 `demo_v2.sh` 가 넘기지 않는다. 카메라·스캔(§1.8)을 보려면 웹을 따로 띄우거나 `P3_WEB_CMD` 로 명령을 바꾼다.
- 9/17–18 에는 master02 tmux `m2-web` 에서 `python -m app.main --host 10.10.0.2 --port 8000` 으로 손으로 띄웠다. 그 절차는 [`README.md`](README.md) 에 남아 있다.

서버는 **`python -m` 한 줄 + `requirements.txt`** 로 끝난다. 별도 설치 스크립트는 없다.

### 10.4 venv

```
python3 -m venv --system-site-packages .venv
```

`--system-site-packages` 가 **필수**다. 없으면 venv 안에서 `rclpy` 가 안 보여 실물 모드가 죽는다
(`rclpy` 는 apt 로 깔린 `/opt/ros/jazzy` 에 있고 pip 로 설치하는 물건이 아니다).
`--mock` 모드만 쓸 거면 없어도 되지만, 같은 venv 를 두 모드에 쓰므로 항상 붙인다.

### 10.5 실행 인자

| 인자 | 기본 | 뜻 |
|---|---|---|
| `--mock` | 꺼짐 | ROS 대신 fixture 재생 |
| `--fixture` | `fixtures/pharmacy_loop.json` | 재생할 fixture 경로 |
| `--host` | `127.0.0.1` | bind 주소 |
| `--port` | `8000` | bind 포트 |
| `--allow-commands` | 꺼짐 | §7 명령 API 를 연다 |
| `--refill-timeout` | `120` | `REFILL_FAILED` 임계 (sim s) |
| `--reset-timeout` | `35` | `RESET_STUCK` 임계 (**wall** s) |
| `--mock-fault` | 없음 | **개발 전용, 시연 절차에 없음** — 고장 흉내 (§11) |
| `--robot-id` | `amr_1` | 구독할 AMR 이름. 실물 모드에서 신호 토픽 접두가 된다 |
| `--order-pool` | 저장소 원문 `src/rokey_p3_orchestrator/config/order_pool.yaml`(실물·mock 같음) | `order_pool.yaml` 경로 (§7.3) |
| `--zones-file` | 저장소 원문 `src/rokey_p3_description/config/zones.yaml`, 못 찾으면 고정 목록(`source: "mock"`) | `zones.yaml` 경로. **후보 표시용**이고 검증에 안 쓴다 (§7.4) |
| `--map-file` | 없음 | Nav2 지도 yaml(`maps/hospital.yaml`). 주면 평면도 API(§7.6)와 `snapshot.robots`(§1.6)가 켜진다 |
| `--show-evaluator` | 꺼짐 | `/evaluator/cabinet` 관측을 snapshot 에 싣는다 (표시 전용) |
| `--live-sensors` | 꺼짐 | 카메라 MJPEG 스트림과 `snapshot.scan` 을 켠다(§1.8). 촬영 때만 켠다. 카메라는 보는 사람이 있을 때만 구독한다 |
| `--roles` | 없음 | 이 PC 의 역할(`P3_ROLES`, 공백 구분). 두 PC 모드에서 `demo_v2.sh` 가 넘긴다(§1.10) |
| `--peer` | 없음 | 상대 PC 주소(`P3_PEER`). 주면 `deployment.multi_pc` 가 `true` |
| `--catalog` | 없음 | 약 카탈로그 YAML(`P3_CATALOG`). QR 판독 요약의 약 이름·약통 로트(§1.12) |
| `--dispenser-file` | 없음 | 조제기 YAML(`P3_DISPENSER_FILE`). 약통 로트 → 약품·유통기한(§1.12) |
| `--static` | 없음 | 이 디렉터리를 `/` 에 서빙한다 (예: `web/frontend`) |
| `--speed` | `1.0` | mock 재생 배속 |
| `--loop` | 꺼짐 | mock fixture 반복 |


### 10.6 병원 월드로 띄우기

**mock(ROS 없이).** 녹화 fixture 를 준다(§8). 병원 주문 풀을 준다. 구역 파일을 준다. 지도 파일을 준다. `web/backend` 에서:

```
python -m app.main --mock --loop --allow-commands \
  --fixture fixtures/hospital_trip.json \
  --order-pool fixtures/order_pool.hospital.dev.yaml \
  --zones-file ../../src/rokey_p3_description/config/zones.hospital.yaml \
  --map-file ../../src/rokey_p3_navigation/config/maps/hospital.yaml
```

| 인자 | 켜지는 것 |
|---|---|
| `--zones-file zones.hospital.yaml` | 목적지 병실·병동 묶음(§7.4), `mixed_rooms`(§7.2), 평면도 구역(§7.5) |
| `--map-file maps/hospital.yaml` | `/api/map`(§7.6), `snapshot.robots`(§1.6) — mock 은 AMR 을 `dock_1` 에 세운다 |
| `--order-pool …hospital…` | 주문 풀 10건(§7.3), 큐 `/api/queue` 의 대기 목록(§7.7) |
| `--loop` | 끝나면 리셋 뒤 다시 — 없으면 재생 끝에 stale 알람이 뜬다 |

`--allow-commands` 를 주면 mock 에서도 요청·리셋 흉내가 된다(§8).
`fixtures/order_pool.hospital.dev.yaml` 은 `hospital_trip.json` 을 녹화할 때 읽은 10건 사본이다. 원문 `src/rokey_p3_orchestrator/config/order_pool.hospital.yaml` 은 main 에 있고 13건이다(§9.1). 원문 풀로 보려면 `--order-pool ../../src/rokey_p3_orchestrator/config/order_pool.hospital.yaml` 을 준다.

**실물** — `tools/demo_v2.sh` 의 `P3_WORLD=hospital` 이 `--order-pool`·`--zones-file`·`--map-file` 을 같은 파일로
넘긴다(#553). 웹을 따로 띄울 때는 위 인자에서 `--mock --loop --fixture` 만 빼면 된다.

### 10.7 스텁 한 바퀴로 확인할 때 — 스텁이 하는 것과 안 하는 것

Isaac 은 없다. 오케스트레이터는 실제다. 주행·팔·시뮬은 스텁이다. 그 조합의 런치 파일은 `stub_loop.launch.py` 다. 웹 API 를 실물 경로로 시험할 때 쓴다. #576 v1·v2 가 이것이다. 격리 도메인으로 띄운다:

```
export ROS_DOMAIN_ID=118 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
ros2 launch rokey_p3_bringup stub_loop.launch.py order_pool_file:=<병원 풀> [max_requests:=1] [dispenser_file:=…]
python -m app.main --allow-commands --order-pool <병원 풀> --zones-file <zones.hospital> --map-file <maps/hospital>
```

| 무엇 | 스텁에서 | 화면에서 보이는 것 |
|---|---|---|
| 발행기 `max_requests` | 한 epoch 에 낼 요청 수다. `1` 이 기본이다. 긴급 한 건이다. `0` 이면 풀 전부를 차례로 낸다 | `0` 이면 웹 요청이 `trip_in_progress` 로 자주 막힌다 |
| 이동·팔 | 정해진 짧은 시간(트립 한 번 약 7 sim s) | 단계(§1.7)가 빨리 넘어간다 |
| **TF** | **내지 않는다** | `snapshot.robots` 가 비어 있다 — 평면도 AMR 없음. 자세는 TF 가 있어야 온다(§1.6) |
| 보충 | 약 0.4 s. 기동 때 빈 슬롯을 먼저 채운다 | 트립 중 **"보충" 단계가 거의 안 보인다**(§12.2) |
| 병동 묶음(mode 3) | 스테이션 인식표(st-station_a)를 보인다 — #582 부터 | 스테이션 인증 1회, 보관함 여러 칸 |
| 인식표 스캔 실패 | 팔이 홈으로 돌아가고 도크로 복귀 — #582 부터 | `AUTH_FAIL` → `HOLD_RETURN`(tag_unreadable) → `DOCKED` |
| 목적지 | 구역 파일을 안 읽는다. **ID 모양만** 본다(`is_zone_id`) | 파일에 없는 구역도 스텁은 간다 — 실물 fleet 은 `goto_rejected` |

---

## 11. 고장 흉내 (`--mock-fault`)

> **개발 전용이다. 시연 절차에 없다.**

알람 대부분은 실물이 고장 났을 때만 뜬다. 그래서 화면이 그것을 제대로 그리는지 시연 전에
확인할 방법이 없다. `--mock-fault` 는 **mock 재생 데이터만** 비틀어 고장을 만든다.

```
python -m app.main --mock --mock-fault clock_stop
python -m app.main --mock --mock-fault stale:m0609_at_home,refill_fail
```

**알람 규칙과 상태 조립 코드는 손대지 않는다.** 실물이 타는 그 길을 그대로 타야 확인에
의미가 있다 — 화면에 알람을 억지로 꽂아 넣는 것이 아니다.

| 이름 | 하는 일 | 뜨는 알람 |
|---|---|---|
| `stuck_reset` | `POST /api/reset` 이 `RESET_DONE` 을 내지 않는다 | `RESET_STUCK` |
| `clock_stop` | sim 10 s 를 지나면 `/clock` 을 흘리지 않는다 | `CLOCK_STOPPED` |
| `stale:<신호키>` | 그 신호만 갱신하지 않는다 | `STATUS_STALE` |
| `refill_fail` | `REFILL_DONE`·`DISPENSER_RESUMED` 를 버린다 | `REFILL_FAILED` |
| `order_timeout` | 주문 종료 상태를 `TIMEOUT`(13)으로 바꾼다 | `TIMEOUT` |
| `late_join` | 첫 25 sim s 의 이벤트를 **작성자별로 묶어 한꺼번에** 쏟는다 | (없음 — §0.3 검증용) |

`<신호키>` 는 `arm_at_home`, `base_stopped`, `gripper_holding`, `belt`, `m0609_at_home`.

빨리 보려면 임계를 함께 줄인다: `--reset-timeout 3`, `--refill-timeout 5`.

### late_join 은 알람이 아니라 **순서**를 시험한다

`/events` 는 `transient_local` 이라 **늦게 붙으면 지난 이벤트가 작성자별로 뭉쳐서 온다**(§0.3).
평소 mock 은 한 줄로 재생하므로 **도착 순서 = 시각 순서**이고, 그 조건이 아예 생기지 않는다.
그래서 `seq` 와 `event_key` 를 다루는 코드는 **mock 으로 아무리 재도 검증되지 않는다** —
실제로 그 경로에서 버그가 둘 났다(화면의 중복 판정, 서버의 페이지 커서).

`late_join` 을 켜면 전달 순서에 **`seq` 역행**이 생긴다. 그 상태에서도
페이징이 빠짐·중복 0 이고 한 epoch 안의 stamp 가 단조인지를 본다.

**측정할 때는 "조건 재현: 예/아니오" 를 결과와 같이 남겨라.** 조건이 안 만들어진 표본에서의
통과는 아무것도 증명하지 않는다.

### 안전장치

- **`--mock` 없이 주면 기동을 거부한다**(exit 2). 실물에 고장을 주입할 길을 두지 않는다.
- 모르는 이름이면 기동을 거부한다(exit 2). 오타를 조용히 무시하면 "왜 안 뜨지" 로 시간을 버린다.
- 기동 로그에 `** 고장 흉내 중 (개발 전용): … **` 를 찍는다.
- **snapshot 의 `mock_faults` 에 켜진 목록이 실린다.** 화면은 이것으로 "고장 흉내 중" 배지를
  띄워야 한다 — 시연 때 실수로 켠 채 띄우는 사고를 막는 장치다. 평소에는 `[]` 다.

고장을 켜지 않은 정상 재생에서는 위 알람이 **하나도 뜨지 않는다**(테스트로 고정).
즉 **시연 중에 이 알람이 보이면 진짜 문제다.**

---

## 12. 실물에서 확인한 것 / 아직 못 본 것

계약이 맞다고 말할 수 있는 근거를 한자리에 둔다. **"통과했다" 보다 "그 통과가 무엇을 증명하는가"** 가
중요하다 — 조건이 안 만들어진 표본에서의 통과는 아무것도 증명하지 않는다.

> 이 절의 관측은 2026-09-23 까지의 스텁·master02 기록이다.
> 그 뒤 Isaac 병원 acceptance 회차(`v0.5.0` 회전 1–4, `v1.0.0` 회전 7)는 주문을 이 웹 API 로 넣었다(`tools/hospital_orders.py`, protocol `hospital-full-acceptance-v1`·`v4`).
> 그 회차들에서 12.2 항목을 하나씩 다시 확인한 기록은 이 문서에 없다(미확인).

### 12.1 실물 스택에서 본 것

| 무엇 | 어디서 | 관측 |
|---|---|---|
| `#104` detail 파싱 | 도메인 118 스텁 | `mode_source=event_detail`, `MODE_URGENT`, `patient_id`·`item_id` 채워짐 |
| 신호 신선도 | 도메인 118 스텁 | 30표본 `stale` **0건**. 최대 나이 arm 0.195 / gripper 0.097 / belt 0.196 — 계약 H 5 Hz·gripper 10 Hz 그대로 |
| 웹 리셋 | 도메인 118 스텁 | epoch 1→2→3, barrier·settle 창이 그대로 |
| WS keepalive | 도메인 118 스텁 | 20초에 101건, 간격 중앙값 202 ms·최대 211 ms |
| **`event_key` 정렬** | 도메인 118 스텁 | 첫 화면이 받은 seq 가 `25·26·1·2·9` 로 뒤죽박죽인데 stamp 는 단조 — `transient_local` 로 작성자별로 뭉쳐 오는 것이 재현됐다 |
| 커서 페이징 | 도메인 118 스텁 | 158건을 limit 2·3·5·7 로 돌려 **빠짐·중복 0** |
| `trip.robot_id` | 도메인 118 스텁 | 140표본 전부 `amr_1`. 버그가 나던 '벨트 이송'·'벨트 끝 픽' 구간 포함 |
| **`pharmacy_only` 알람 면제** | 도메인 118 스텁 | 한 바퀴 160표본에 `HOLD_RETURN` 경고 **0건** |
| 화면 한 바퀴 | 도메인 118 + 프론트 | 풀에서 고르기 → 침상 자동 채움 → 보내기 → 수락 → WS push → 트립 등장 |
| master02 기동 | master02 스텁 | `GET /` 200, `POST /api/reset` 403(명령 닫힘), `mock_faults []`, `clock.alive`, 신호 5개 `stale=false`, `/api/events` stamp 오름차순, 리셋 2회 epoch 1→2→3. firefox·google-chrome 둘 다 로드 |
| **`last_refill`** | master02 Isaac v2 | `parsed: true` **실데이터 확인** |
| 병원 풀 긴급·병실 묶음·`mixed_rooms` (9/23, #576 v1) | 격리 도메인 스텁 + 병원 풀 | 긴급 bed_a2 전달·복귀, mode 2 C1 이 bed_a1→a3→a4 차례로, C1+C2 섞임은 보내기 전 400 |
| 병동 묶음(mode 3) (9/23, #582 뒤) | 같은 조합 | station_a 에서 인증 1회, 보관함 두 칸, 도크 복귀(녹화 fixture `hospital_trip.json`) |
| 주문 10건 연속 (9/23, #576 v2) | 같은 조합 | 긴급 + 1인 + 묶음 셋, **10/10 `CABINET_LOCKED`**, 실패·보충 0, sim 145 s |
| **긴급 `ARRIVING` 알람** (9/23) | 같은 조합 | 긴급 트립에서 `URGENT_ARRIVING` 이 떴다. 다음 트립이 열려도 목적지가 안 바뀜(#581) |
| 일곱 단계 `stage` (9/23) | 같은 조합, WS | 6½ 트립 모두 요청→조제→집기→배송→도착→복귀→대기 |
| AMR 자세(TF) (9/23) | 같은 조합 + 10 Hz 가짜 TF | x 가 따라 움직임, WS 4.86–4.89 Hz, 발행을 끄면 stale |

### 12.2 아직 못 본 것

| 무엇 | 왜 |
|---|---|
| `/rosout` 실데이터 | 스텁이 WARN 이상을 한 줄도 안 낸다. 구독은 걸려 있고 `--mock` fixture 에 예시 6줄이 있다 |
| `REFILL_DONE` v2 **왕복** | 팔이 detail 을 만드는 함수와 왕복해 보지 않았다. `REQUEST_ACCEPTED` 는 `request_summary` 를 직접 불러 왕복했다. v2 브랜치가 오면 같은 방식으로 추가한다 |
| `SUCCESS` | orchestrator 가 발행하지 않는다(§1). 배송 완주 `DELIVERED` 는 9/23 스텁에서 봤다(§12.1) |
| **"보충" 단계**(§1.7) 실측 | 스텁 보충이 0.4 s 이고 기동 때 끝나, 트립이 보충을 기다리는 순간이 안 생겼다. 단위 시험으로만 검증 |
| **AMR 자세를 실제 TF 로** | 스텁은 TF 를 안 낸다(§10.7). 가짜 TF 로만 봤다. Isaac 병원 회차에서 본 기록은 이 문서에 없다(미확인) |
| 여러 AMR | 주문을 받는 AMR 은 `amr_1` 하나다. 여벌 AMR·더미는 `/isaac/fleet/poses` 로 자세만 보인다(§1.6, #754·#770·#775). 여러 AMR 배송은 없다 |
| **신선도를 steady clock 으로 재기** | 계약 4절·`status_monitor` 는 `time.monotonic()` 인데 이 서버는 시스템 UTC 벽시계를 쓴다(§1.1). 서버 시계가 뛰면 나이·`stale` 이 한 번 틀어진다. 고치려면 `WorldState` 가 항목마다 monotonic 을 같이 들고 `_age` 가 그것으로 재야 한다. **`v1.1.0` 에서도 고치지 않았다**(`state.py` `_age` 는 벽시계 차이다). 운영으로 막는다. 시계 동기화 뒤에 띄운다. 시계가 뛰면 웹만 재기동한다(`web/README` §1.5) |

### 12.3 mock 이 만들지 못하는 조건

**mock 으로 아무리 재도 검증되지 않는 것이 있다.** 그 목록을 아는 것이 중요하다.

| 조건 | 왜 mock 이 못 만드나 | 대신 |
|---|---|---|
| `seq` 역행(뭉쳐 오는 순서) | 한 줄로 재생하니 **도착 순서 = 시각 순서** | `--mock-fault late_join`, 또는 실물 |
| `/rosout` 실제 문구 | fixture 의 예시 6줄뿐 | 실물 |
| 고장 알람 5종 | 정상 재생에는 안 뜬다 | `--mock-fault` (§11) |

이 표 때문에 오늘 버그가 둘 났다 — 화면의 중복 판정과 서버의 페이지 커서. 둘 다 **실물을 띄워야만**
잡혔고, mock 측정은 통과했었다.
