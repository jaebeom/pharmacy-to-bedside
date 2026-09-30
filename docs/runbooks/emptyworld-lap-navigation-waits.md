# 빈월드 한 바퀴 — 주행 구간이 기다리는 것과 답하는 것

> **상태: 지난 기록 (2026-09-21 기준).** 지금은 [병원 한 바퀴 런카드](hospital-full.md)를 따른다.

| 항목 | 내용 |
| --- | --- |
| 무엇 | 빈월드 조합에서 **주행 구간이 멈출 수 있는 자리**를 전부 적는다. 인증 구간에서 나온 "이 조합에서 답할 주체가 없다"와 같은 구멍이 주행에도 있는지 본다 |
| 기준 | `main` + PR #400(K3a)·#407(K3b). 계약 v1 2.2·3·5·6·7절 |
| 조합 | `use_stub_fleet:=false` + `navigation.launch.py motion_backend:=waypoints zones_file:=… routes_file:=…` + 스테이지 `--amr`. **Nav2·AMCL 없음** |
| 상태 | **읽기만 했다.** 이 조합을 돌린 적이 없다(Isaac L3 미실행). 아래는 코드에서 읽은 사실과 그것에서 나온 예상이다 |

## 0. 먼저 — 이름이 같은 둘을 가른다

- **`DOCKED` 이벤트**: orchestrator 가 낸다. 복귀 `GoToZone`(목적지 `dock_1`)이 `arrived=true` 로 끝나면 그 자리에서 낸다(`trip_fsm.py:1047`). 주행은 이벤트를 내지 않는다(계약 2.6절).
- **`DockingState` 토픽**(`/amr_1/base/docked`): 주행이 내는 **관측**이다(계약 11.6). opt-in 이고 기본은 꺼져 있다. 한 바퀴가 도는 것과 무관하다.
둘은 다른 것이다. 한 바퀴 판정은 앞의 것만 본다.

## 1. 주행이 답하는 것 (기다리는 쪽 → 주는 쪽)

| # | 기다리는 것 | 이 조합에서 주는 주체 | 안 오면 | 실물/스텁 |
| --- | --- | --- | --- | --- |
| 1 | `/amr_1/go_to_zone` 서버 | `fleet`(`fleet_node.py`) | orchestrator 가 `server_wait_s`(10 s wall) 뒤 거부로 본다 | 실물 |
| 2 | `GoToZone` 수락 | `fleet._on_goal` — zone 이 파일에 있고, 종단이고, 진행 중 goal 이 없고, `arm/at_home` 이 1.0 s 이내 true | 거부. orchestrator 가 5 s 뒤 1회 재시도, 그래도 거부면 트립을 닫는다(계약 5절) | 실물 |
| 3 | `/amr_1/arm/at_home` | **arm 노드**(주행 아님). 스텁이든 실물이든 이 조합에 반드시 있어야 한다 | 2번이 영원히 거부된다. **주행 구간의 첫 멈춤 자리다** | 조합에 따라 다름 |
| 4 | `GoToZone` 결과 `arrived` | `fleet._follow_waypoints` — 추종기가 zone 공차 안에 들고 `odom` 속도가 `stopped_hold_s`(0.5 s) 이상 조용하면 | 제한 시간(load·dock 120 s, 병동 180 s, sim)으로 `timeout` | 실물 |
| 5 | `GoToZone` 피드백(`distance_remaining`) | 같은 함수가 매 주기 낸다(목표까지 직선 거리) | `ARRIVING` 이 안 나온다(아래 3절) | 실물 |
| 6 | `/amr_1/base/stopped` | `fleet` 5 Hz. `odom` 이 1.0 s 없으면 **발행을 멈춘다**(받는 쪽에서 unknown) | 팔이 동작을 시작하지 않는다(계약 5절) | 실물 |
| 7 | `/amr_1/odom`, TF `odom→base_link` | `base_driver`. **`navigation.launch.py` 가 띄운다**(`lane_node('base_driver')`) | 4·6 이 성립하지 않는다 | 실물 |
| 8 | `/amr_1/joint_states` | **스테이지**(`--amr`). dummy 3축 이름이 `base_driver` 파라미터와 같아야 한다 | `base_driver` 가 5 s 마다 경고하고 0 만 낸다 → 로봇이 안 움직인다 | 실물(Isaac) |
| 9 | `/amr_1/base/joint_command` 소비 | 스테이지 | 명령이 버려진다. 위와 같은 증상 | 실물(Isaac) |
| 10 | TF `map→amr_1/base_link` | `map→odom` 은 **launch 가 띄우는 항등 static TF**(`waypoints` 모드에서만), `odom→base_link` 는 `base_driver` | 추종기가 pose 를 못 읽어 0 을 내고 WARN 을 남긴다 → 제한 시간으로 끝난다 | 실물 |
| 11 | zone 자세·공차 | **`zones.yaml` 파일**(`zones_file`). TF 가 아니다 | 파일이 없으면 goal 을 전부 거부한다 | 파일 |
| 12 | waypoint | **`routes.*.yaml` 파일**(`routes_file`). 없으면 곧장 간다 | 벽을 통과하는 직선이 된다(빈월드에서는 충돌) | 파일 |

## 2. 확인 요청에 대한 답

1. **`fleet`·추종기는 zone 자세를 파일에서 읽는다.** `zones.yaml` 의 `x`·`y`·`yaw`·`tol_xy`·`tol_yaw` 다(`fleet_node._load_zones` → `self._zones.zones[zone_id]`). TF 에서 읽는 것은 **현재 로봇 자세**(`map`→`base_link`) 하나뿐이다.
   → 스테이지가 zone TF 를 `P3Pharmacy` 아래에 내는 것은 **도착 판정에 닿지 않는다.** 남는 것은 TF 트리에 같은 child 이름이 둘 생기는 것이다.
2. **`zones_tf` 는 하위 프레임도 낸다.** `zones.yaml` 의 `pharmacy/*` 와 각 zone 의 `cabinet`·`tag` 를 `map` 아래 `/tf_static` 으로 1회 낸다(`zones_tf_node.py:56-65`). **zone 자체(`load`·`bed_a1` …)는 내지 않는다.**
   → 계약 59줄이 말하는 "`<zone>/cabinet`·`<zone>/tag` 의 단일 작성자 = `zones_tf`" 는 코드와 같다. 스테이지가 그 둘을 함께 내면 작성자가 둘이 된다(계약 3절 위반).
   → 제안("구역 여섯은 `zones_tf` 하나가 낸다")에 대해 정정할 것이 있다: **지금 `zones_tf` 는 구역 여섯을 내지 않는다.** 스테이지가 `load`·`dock_1`·침상 넷을 내고 싶다면 부모만 `map` 으로 맞추면 충돌이 없다. 겹치는 것은 `*_cabinet`·`*_tag` 여덟이다.

## 3. 멈출 수 있는 자리 (이 조합에서 답할 주체가 없는 것)

| 자리 | 사실 | 판단 |
| --- | --- | --- |
| `arm/at_home` | 주행은 이것 없이 goal 을 받지 않는다(계약 5절). 빈월드 조합에 arm 노드가 없으면 **모든 `GoToZone` 이 거부**된다 | **확인 필요.** 인증 구간의 `scan_tag` 와 같은 종류다 |
| `ARRIVING` | orchestrator 가 낸다. 조건은 **긴급 모드**이고 `distance_remaining ≤ 3.0 m` 이다(`trip_fsm.py:425-436`). 추종기는 피드백을 매 주기 낸다 | 긴급이 아니면 원래 안 나온다. 주행 쪽 구멍은 아니다 |
| `nav2_server_wait_s` 10 s | `waypoints` 모드는 `_execute` 에서 갈라져 `wait_for_server` 를 **부르지 않는다**. 이 대기는 `nav2` 모드에만 있다 | 문제 없음 |
| `DockingState` 가 `DOCKED` 를 안 냄 | `amcl_max_age_s` 기본 0 = 미정이라 **늘 UNKNOWN** 이다. 빈월드에는 AMCL 도 없다 | 한 바퀴 판정과 무관(0절). 값을 정하는 것은 L3 뒤 |
| 공차 0 | zones 공차가 0 이면 추종기가 0 을 내고 `arrived` 가 영원히 안 난다 → 제한 시간 | 빈월드 zones 는 양수(확인됨) |

## 4. 리셋에서 무엇이 어떻게 되나

| 대상 | 리셋에서 | 근거 |
| --- | --- | --- |
| 스테이지 베이스 | AMR 을 도크 자세로 되돌린다(합의) | 계약 6절 2 |
| `base_driver` | `joint_states` 를 그대로 따라간다. **`odom` 이 순간이동한다**(위치는 조인트 값 그대로) | `odom_from_joints` |
| 추종기 | 진행 중 goal 은 `RESET_DONE` 에서 `reset` 으로 끝난다. 끝낼 때 **0 속도를 먼저 낸다** | `fleet._follow_waypoints`, `_close_nav` |
| 경로 출발점 | `RESET_DONE` 에서 `_here` 를 `dock_zone` 으로 되돌린다. **옛 위치를 출발점으로 잡지 않는다** | `fleet._on_event` |
| 실제 출발 위치 | 경로 선택만 `_here` 로 하고, 움직임은 TF 의 **현재 자세**에서 시작한다. 그래서 스테이지가 되돌린 자리에서 출발한다 | `follow(pose, …)` |
| `initialpose` | 리셋마다 1회 낸다. 빈월드에는 AMCL 이 없어 받는 쪽이 없다(무해) | 계약 6절 4 |

**연속 3바퀴에서 볼 것:** 두 번째 바퀴의 첫 `GoToZone` 이 `dock_1 → load` 경로를 고르는가(=`_here` 가 도크로 돌아갔는가), 그리고 `odom` 순간이동 직후 `base/stopped` 가 잠깐 false 가 되었다가 돌아오는가(속도를 위치 차이로 만들 때 한 표본이 크게 잡힌다).

## 5. 한계

- 이 문서는 **코드를 읽어 만든 예상**이다. 빈월드 조합을 돌린 적이 없다.
- `--amr` 스테이지가 실제로 무엇을 내는지(이름·주기·stamp)는 스테이지 문서(`sim/README.md`)를 따른다. 어긋나면 8·9번이 먼저 깨진다.
- 새 L2 3건(빈월드 대역 주행·경로·리셋)은 #407 에서 처음 도는 중이다. 그 결과가 4번 항목의 첫 증거다.
