# rokey_p3_navigation

v1.1.0 병원 한 바퀴에서 `tools/demo_v2.sh` 의 nav 역할이 `navigation.launch.py` 로 이 패키지를 띄운다.
`fleet` 이 `GoToZone` 을 받아 Nav2 로 접근점까지 가고, 마지막 구간은 추종기로 정차 자리에 선다(`nav2_final_approach:=true`).
`map` → `amr_1/odom` 은 AMCL 없이 `dock_origin_tf` 가 낸다(`localization:=odom`). `speed_governor` 가 근접 속도 0.7 m/s 로 줄인다(#788).

occupancy map, Nav2, 감속기, 적재 위치·도크 도킹 판정, 구역 TF. **navigation 담당**의 단독 영역이다(CODEOWNERS `@Taegyu-Lee1117`, 이태규).
사람 인식 노드는 `rokey_p3_perception` 에 작은 PR 로 넣고 manipulation 담당이 리뷰한다.

이름·QoS·프레임·인터락은 [배송 한 바퀴 계약 v1](../../docs/architecture/delivery-contract-v1.md) 이 정한다.
이 패키지는 그 이름을 바꾸지 않는다.

## 노드

| 노드 | 하는 것 | 누가 띄우나 |
| --- | --- | --- |
| `base_driver` | `cmd_vel` → dummy 조인트 속도, `joint_states` → `odom` 과 TF | `navigation.launch.py` |
| `fleet` | `GoToZone` 서버. Nav2 를 감싼다. 도킹 판정, `base/stopped`, 리셋 뒤 `initialpose`와 costmap 초기화 | `navigation.launch.py` |
| `zones_tf` | `zones_file` 의 고정 프레임을 `/tf_static` 으로 1회 | `navigation.launch.py` |
| `dock_origin_tf` | `map` → `<ns>/odom` 을 도크 자리만큼 평행이동으로 1회. AMCL 이 없을 때만 뜬다 | `navigation.launch.py`(`motion_backend:=waypoints` 또는 `localization:=odom`) |
| `speed_governor` | 지역 코스트맵의 여유 → `controller_server` 의 속도 제한(%). 지도에 없는 장애물 앞 정지 규칙 | `nav2.launch.py`(같은 네임스페이스) |
| `map_activation_guard` | `map_server` 가 20 s 안에 active 가 아니면 직접 configure·activate 한다(#743). 개입·포기는 `/p3/alerts` 로 알린다 | `nav2.launch.py` |

```bash
# v1.1.0 병원 한 바퀴의 nav 줄(tools/demo_v2.sh cmds, 경로는 줄였다)
ros2 launch rokey_p3_navigation navigation.launch.py \
  zones_file:=<repo>/src/rokey_p3_description/config/zones.hospital-receiver.yaml \
  routes_file:=<repo>/src/rokey_p3_description/config/routes.hospital-receiver.yaml \
  map:=<repo>/src/rokey_p3_navigation/config/maps/hospital.yaml nav2_final_approach:=true localization:=odom

# 맵 없이 Nav2 는 빼고 띄운다
ros2 launch rokey_p3_navigation navigation.launch.py use_nav2:=false

# Nav2 쪽만
ros2 launch rokey_p3_navigation nav2.launch.py map:=/절대/경로/hospital.yaml
```

## 현황 (v1.1.0)

> 이 절은 2026-09-20 판을 v1.1.0(`f316197`) 기준으로 고쳤다. 9/20 판은 "시연 경로에서 이 패키지가 뜨지 않는다", "L3 전부 미실행" 이었다.

- `tools/demo_v2.sh` 의 한 바퀴 월드(emptyworld·hospital)는 이 패키지로 주행한다. emptyworld 는 `motion_backend:=waypoints`, hospital 은 Nav2 다(`nav_cmd`).
- demo 월드(조제실만)는 여전히 `stub_fleet` 이 `GoToZone` 을 대신한다.
- 병원 L3 는 [병원 주행 런북](../../docs/runbooks/hospital-nav-l3.md)과 [병원 전 구간 런북](../../docs/runbooks/hospital-full.md)에 있다. v1.0.0 회전 7(`9760d9d`, #777·#778)이 이 구성으로 돌았다.
- v1.1.0 커밋으로 돌린 acceptance 회전은 없다. 근접 속도 0.7(#788)은 L3 미확인이다(`nav2_params.yaml` 주석).
- 설계와 남은 값은 [RFC 0001](../../docs/rfc/0001-navigation-ward-routing-and-reset.md)(검토 대상)에 있다.

ROS 를 import 하지 않는 모듈(L1)과 노드를 한 표로 적는다. "연결"은 `fleet_node` 가 실제로 부르는지다.

| 모듈 | 하는 일 | 연결 | 켜는 파라미터(기본값) | 값이 비어 있으면 | L2 |
| --- | --- | --- | --- | --- | --- |
| `zones.py` | 구역 ID 규칙(경유 `door_xN`·`cp_x` 포함)과 `zones.yaml` 형식 검사 | 연결 | — | 형식이 틀리면 fleet 이 goal 을 전부 거부 | — |
| `readiness.py` | 공차 양수·유한, 좌표 유한, 필수 zone, `frame=map` 검사 | `zone_reasons` 만 `docking_state` 가 씀. 파일 전체 검사는 미연결 | — | 공차 0 이면 막힘. 좌표 0 은 유효 | — |
| `docking.py` | 도킹·정지·출발 판정, 제한 시간 | 연결 | — | 공차 0 이면 `arrived=true` 가 안 나옴 | — |
| `base_kinematics.py` | `cmd_vel` ↔ 조인트 속도, 조인트 → `odom` | `base_driver` | — | — | — |
| `goal_guard.py` | Nav2 하위 goal 의 token·epoch, 늦은 수락 cancel, cancel 종결 대기 10 s(계약 7절) | 연결(#258) | — | — | `test_fleet_nav2_l2.py` 취소·리셋 4건 |
| `topology.py` | 병동 계층 경로의 로드 검증과 두 정거장 사이 경로(Dijkstra) | `is_terminal` 만 연결(경유 zone 목적지 거부, #285). 경로 계산은 미연결 | — | 폭 `null` 이면 경로 `ready=false`, manifest 없으면 `ready=false` | 경유 zone 거부 1건 |
| `passage.py` | 문·통로 통과 판정(회전 footprint + 여유 < 문 폭) | 미연결(`topology` 가 씀) | — | 치수 하나라도 없으면 UNKNOWN | — |
| `waypoint_follower.py` | 고정 경로 추종 v0(빈월드). 전방향 베이스라 돌지 않고 간다. 장애물 회피·재계획 없음. 병원에서는 `nav2_final_approach` 의 마지막 구간에 쓴다 | 연결(opt-in) | `motion_backend: waypoints` 또는 `nav2_final_approach: true` | 공차 0·pose 없음·config 이상 → 움직이지 않는다 | 빈월드 대역으로 주행·경로·리셋 3건 |
| `routes.py` | 월드별 `routes.*.yaml`(zone 쌍 → `map` 기준 waypoint) 읽기·검사. `nav2_final_approach` 의 접근점도 여기서 나온다 | 연결(opt-in) | `routes_file` | 파일이 없거나 쌍이 없으면 곧장 간다. **빈 목록(따져 봤다)과 쌍 없음(안 따져 봤다)은 다르다** — 뒤쪽이면 fleet 이 WARN 을 낸다 | 위와 같음 |
| `docking_state.py` | `/amr_1/base/docked` 판정(계약 11.6) | 연결(#300), opt-in | `publish_docking_state`(false), `amcl_max_age_s`(0.0) | 꺼 두면 토픽 없음. `amcl_max_age_s` 가 0(미정)이면 늘 UNKNOWN | 기본 끔·리셋 전이 2건 |
| `speed_governor.py` | 코스트맵 여유 → 속도 %, 정지 규칙(`StopRule`) | `speed_governor` | `stop_rule`(true) | 코스트맵이 끊기면 느린 쪽 | — |
| `map_activation.py` | `map_server` lifecycle 감시·전이 판단 | `map_activation_guard` | — | — | `test_map_activation_node.py` |
| `alerts.py` | 관제 웹 알림 `/p3/alerts` 의 JSON 형식 | `map_activation_guard` | — | — | — |

| 노드 | 스레드 | 비고 |
| --- | --- | --- |
| `fleet` | `max(2, CPU 수)`(#295) | 1 코어에서도 tick 이 돌게 하한 2. 2 스레드 취소 L2 는 #293 |
| `base_driver`, `zones_tf`, `dock_origin_tf`, `speed_governor`, `map_activation_guard` | 기본 | — |

## base_driver

Ridgeback 베이스는 바퀴 물리가 아니라 **world 축** dummy 조인트 셋(prismatic x, prismatic y, revolute z)의
속도 제어다([시나리오 1절 자산 표](../../docs/planning/scenario.md#시뮬-자산-후보)).
`cmd_vel` 은 `amr_1/base_link` 기준이므로 현재 yaw 로 돌려서 내보낸다.

| 방향 | 이름 | 타입 | QoS |
| --- | --- | --- | --- |
| 받음 | `/amr_1/cmd_vel` | `geometry_msgs/Twist` (`amr_1/base_link` 기준) | R |
| 받음 | `/amr_1/joint_states` | `sensor_msgs/JointState` (dummy 3개 + UR5 6개) | S |
| 냄 | `/amr_1/base/joint_command` | `sensor_msgs/JointState` (dummy 3개, `velocity`) | R, 20 Hz |
| 냄 | `/amr_1/odom` | `nav_msgs/Odometry` (`amr_1/odom` → `amr_1/base_link`) | R |
| 냄 | `/tf` | `amr_1/odom` → `amr_1/base_link` | |

- `odom` 은 dummy 조인트 위치 그대로다. **노이즈 없음, 공분산 0.** run 기록에 그 사실을 적는다.
- `odom` 의 `twist` 는 `child_frame_id` 기준이라 world 속도를 yaw 만큼 반대로 돌린 값이다.
- `joint_states` 의 `velocity` 가 비어 있으면 위치 차이로 속도를 만든다. 0 으로 두면
  `fleet` 의 `base/stopped` 가 항상 참이 되어 팔 인터락이 무너진다.
- stale 판정과 명령 주기는 계약 4절대로 **steady clock(wall)** 이다. `cmd_vel` 0.5 s, `joint_states` 1.0 s.
  둘 중 하나라도 끊기면 0 속도를 계속 낸다. 정지를 Isaac 의 watchdog 에만 맡기지 않는다(계약 5절 "정지 보장").
  메시지 `stamp` 는 sim time 이다.

| 파라미터 | 기본값 | 비고 |
| --- | --- | --- |
| `robot_namespace` | `amr_1` | 토픽 이름 앞부분 |
| `joint_x`, `joint_y`, `joint_yaw` | `dummy_base_prismatic_x_joint`, `dummy_base_prismatic_y_joint`, `dummy_base_revolute_z_joint` | master02 `~/test_amr` 의 `hospital_amr_nav.usd` 이름(저장소 밖, 9/20) |
| `command_rate_hz` | `20.0` | |
| `cmd_vel_timeout_s` | `0.5` | wall |
| `joint_states_timeout_s` | `1.0` | wall |
| `start_position_tolerance_m` | `0.5` | 진단용. 첫 `joint_states` 의 x·y 가 이보다 크면 WARN 한 번. 동작은 안 바뀐다 |

articulation root 는 `/World/hopital_custome/ridgeback_ur5` 다. 철자는 USD 원문이다.
이 구성(베이스 위에 UR5 가 올라간 것)을 문서·PR·로그에서 **AMR 합본**이라 부른다(재범 9/21).
"받침대 UR5" 는 팔이 따로 선 옛 구성이다. **USD 파일명과 프림 이름은 그대로 둔다.**

이름이 틀리면 노드가 `joint_states 에 dummy 조인트 ... 가 없다` 를 5 s 마다 찍고 0 만 낸다.

## fleet

| 방향 | 이름 | 타입 | QoS |
| --- | --- | --- | --- |
| 받음 | `/amr_1/go_to_zone` | action `GoToZone` | |
| 받음 | `/amr_1/odom` | `nav_msgs/Odometry` | R |
| 받음 | `/amr_1/arm/at_home` | `std_msgs/Bool` | H |
| 받음 | `/events` | `Event` (`RESET_DONE` 만 본다) | R(volatile, 아래) |
| 냄 | `/amr_1/base/stopped` | `std_msgs/Bool` | H, 5 Hz |
| 냄 | `/amr_1/initialpose` | `geometry_msgs/PoseWithCovarianceStamped` | R, 리셋 뒤 1회 |
| 보냄 | `/amr_1/navigate_to_pose` | action `NavigateToPose` (Nav2, `motion_backend: nav2`) | |
| 냄 | `/amr_1/cmd_vel` | `geometry_msgs/Twist` (`motion_backend: waypoints`, 또는 `nav2_final_approach` 의 마지막 구간) | R, 20 Hz |
| 냄 | `/amr_1/base/docked` | `DockingState` — **opt-in**(`publish_docking_state`) | H, 5 Hz |

- **수락 조건**(계약 5절): `zone_id` 가 `zones.yaml` 에 있고, 종단 zone 이고(`door_*`·`cp_*`·`room_*` 은 경유 전용, 계약 3절),
  진행 중인 goal 이 없고, `arm/at_home` 이 true 이며 1.0 s 이내 수신. 하나라도 어긋나면 goal 거부다. 이벤트는 내지 않는다.
- **취소·리셋**(계약 6·7절): 서버 대기·전송 중에 닫히면 Nav2 에 보내지 않는다. 늦게 수락된 Nav2 goal 은 곧바로 cancel 한다.
  cancel 뒤 Nav2 가 답하지 않아도 10 s(wall) 뒤에 끝내고 다음 goal 을 받는다(`goal_guard`).
- **`arrived=true`** 는 Nav2 가 성공하고, 그 뒤 `settle_timeout_s` 안에 `map` → `amr_1/base_link` 가
  `tol_xy`·`tol_yaw` 안에 들어오고 odom 이 `odom_timeout_s`(wall) 안에 있을 때만 낸다.
  수신이 끊기지 않은 동안 속도가 `stopped_hold_s` 이상 조용해야 한다.
  끊긴 odom 위에 남은 정지 누적이나 캐시 자세만으로는 도착이 아니다.
  아니면 abort + `arrived=false` 이다. `message` 는 `timeout`, `out_of_tolerance`, `not_stopped`,
  `stale_odom`(odom 이 `odom_timeout_s` 를 넘김), `no_pose`, `nav2_unavailable`, `nav2_rejected`,
  `nav2_status_<n>`, `reset`, `canceled` 중 하나다.
- 제한 시간은 계약 7절대로 구역 종류로 고른다. 적재 위치·도크 120 s, 그 밖 180 s, **sim time** 기준.
  재시도는 없다. Nav2 recovery 에 맡긴다.
- `base/stopped` 는 5 Hz(**wall**)로 낸다. `odom` 이 1.0 s 없으면 발행을 멈춰 받는 쪽에서 unknown 이 된다.
- `/events` 는 계약상 latched(L) 지만 fleet 는 **volatile** 로 구독한다. 재시작한 fleet 가 밀린
  `RESET_DONE` 을 보고 `initialpose` 를 다시 내면 안 되기 때문이다. 발행자가 transient local 이라 호환된다.
- `Event.RESET_DONE` 상수는 인터페이스 v1.1 에 들어온다(계약 10절). 그때까지 문자열로 비교한다.
- `RESET_DONE` 의 `epoch` 이 마지막으로 본 것보다 크지 않으면 버린다. 늦게 온 중복으로
  `initialpose` 를 두 번 내지 않는다. 리셋 때 진행 중인 goal 이 있으면 abort 하고 `message` 는 `reset` 이다.
- `initialpose`를 발행한 뒤 `/<ns>/global_costmap/clear_entirely_global_costmap`과
  `/<ns>/local_costmap/clear_entirely_local_costmap`을 비동기로 한 번씩 호출한다. 서비스 탐색·응답은
  `costmap_clear_wait_s` wall 시한 안에서 5 Hz tick으로 확인하며, 부재·무응답은 WARN으로 남기고 fleet을 막지 않는다.

기본값 칸은 `config/navigation_params.yaml`(launch 가 주는 값)이다. 코드 기본값이 다른 것은 비고에 적었다.

| 파라미터 | 기본값 | 비고 |
| --- | --- | --- |
| `zones_file` | 빈 문자열 | 비면 `rokey_p3_description` share 의 `config/zones.yaml` |
| `dock_zone` | `dock_1` | 리셋 뒤 `initialpose` 자리. 계약 6절 `dock_k` |
| `navigate_action` | `/amr_1/navigate_to_pose` | Nav2 액션 이름 |
| `goal_timeout_load_dock_s`, `goal_timeout_ward_s` | `120.0`, `180.0` | sim |
| `settle_timeout_s` | `5.0` | Nav2 성공 뒤 정지·허용오차를 기다리는 시간(sim) |
| `stopped_linear_tol`, `stopped_angular_tol`, `stopped_hold_s` | `0.02`, `0.02`, `0.5` | 계약 2.2절 |
| `at_home_max_age_s`, `odom_timeout_s` | `1.0`, `1.0` | wall |
| `costmap_clear_wait_s` | `10.0` | RESET_DONE 뒤 global/local costmap clear 서비스 탐색·응답 시한(wall) |
| `global_costmap_clear_service`, `local_costmap_clear_service` | `/<ns>/global_costmap/clear_entirely_global_costmap`, `/<ns>/local_costmap/clear_entirely_local_costmap` | Jazzy `nav2_msgs/srv/ClearEntireCostmap`; namespace에 맞춘 기본값 |
| `initialpose_cov_xy`, `initialpose_cov_yaw` | `0.25`, `0.0685` | RViz·AMCL 관례값 |
| `motion_backend` | `nav2` | `waypoints` 면 Nav2 대신 고정 경로 추종 v0 를 쓴다(빈월드). 갈아 끼우는 자리는 여기 하나다 |
| `routes_file` | 빈 문자열 | `waypoints` 모드와 `nav2_final_approach` 의 월드별 경로 파일 |
| `nav2_final_approach` | `false` | 켜면 Nav2 는 경로의 마지막 waypoint(접근점)까지만 가고, 정차 자리까지는 추종기가 간다. 병원 `demo_v2.sh` 가 `true` 를 준다 |
| `nav2_handoff_radius` | `0.5` | 접근점까지 이만큼 남으면 Nav2 를 거두고 추종기로 넘긴다(병원 L3 3회차, 9/23) |
| `nav2_server_wait_s`, `stopped_rate_hz` | `10.0`, `5.0` | wall |
| `follower_max_linear`, `follower_max_angular` | `0.9`, `0.9` | m/s, rad/s. **Nav2 상한(`max_vel_x/y` 1.0, `max_vel_theta` 1.0)의 90 %** 다(재범 9/24. 9/21 에는 그때 상한의 80 %). 벡터 크기를 자르므로 `max_speed_xy` 1.0 을 넘지 않는다. 코드 기본값은 `0.3`, `0.5` |
| `follower_max_accel`, `follower_max_angular_accel` | `0.9`, `1.8` | m/s², rad/s². 같은 출처(`acc_lim_x/y` 1.0, `acc_lim_theta` 2.0)의 90 %. **사슬에서 가속을 자르는 곳은 여기뿐이다** — 스테이지 속도 드라이브는 damping 이 커서 명령 계단을 그대로 따라가고, 상판에는 칸막이가 없다 |
| `follower_slow_radius`, `follower_waypoint_tolerance`, `follower_rate_hz` | `1.5`, `0.05`, `20.0` | 목표 근처 거동은 `max_linear / slow_radius`(= 0.6 /s)로 정해진다. 코드 기본 `follower_slow_radius` 는 `0.5` 다. **속도를 올리면 이 비를 지켜야 도착 정밀도가 그대로다.** 통로 여유는 `follower_waypoint_tolerance` 위에 서 있다(모서리 자르기). 키우면 시뮬 쪽 여유 시험이 깨진다 |
| `follower_arrive_xy`, `follower_arrive_yaw` | `0.02`, `0.02` | **도착으로 볼 반경.** zone 공차는 판정의 선이고 추종의 목표는 중심이다. 실제 기준은 `min(공차, 이 값)`. K3 L3 에서 공차 원에 들어서자마자 멈춰 목표에서 0.14 m 에 섰다 |
| `publish_docking_state` | `false` | 켜야 `/amr_1/base/docked` 를 만든다(계약 11.6) |
| `amcl_max_age_s` | `0.0` | AMCL 신선도 문턱(sim s). **L3 측정 전 미정.** 0 이하이면 DockingState 는 늘 UNKNOWN |

## speed_governor

넓은 곳에서는 최고 속도, 벽·문·협탁 가까이에서는 근접 속도로 `controller_server` 의 `speed_limit` 을 낸다
(재범 9/23). 판단은 `speed_governor.py`(ROS 없이 시험), 노드는 구독·계산·발행만 한다.
`nav2.launch.py` 가 `nav2_params.yaml` 의 `speed_governor` 블록(`max_speed_mps` 1.0, `slow_speed_mps` 0.7)을 준다. 나머지는 코드 기본값이다.

| 파라미터 | 기본 | 뜻 |
| --- | --- | --- |
| `max_speed_mps` | `1.0` | `nav2_params.yaml` FollowPath 의 `max_speed_xy` 와 **같아야 한다**(시험이 묶는다) |
| `slow_speed_mps` | `0.7` (9/29 #788, 전 0.5. L3 미확인) | 근접 속도. **%가 아니라 m/s** — 최고 속도를 올려도 근접 속도가 따라 오르지 않는다(#526 → #547) |
| `near_m`, `far_m` | `1.0`, `1.8` | 벽까지 `near_m` 이하면 근접 속도다. `far_m` 이상이면 최고 속도다. 사이는 직선이다. 고른 값이다. 회차의 `여유` 실측으로 다시 정한다 |
| `lethal_cost` | `100` | OccupancyGrid(0–100) 값. 100 = 실제 장애물 칸. **99 는 팽창 띠라 벽 + 내접 반지름을 잰다** |
| `publish_period_s` | `1.0` | 값이 같아도 다시 낸다. controller_server 구독이 VOLATILE 이라 먼저 낸 한 장은 못 받는다 |
| `status_period_s` | `10.0` | 현황 한 줄 주기 |
| `stale_after_s` | `2.0` | 코스트맵이 이만큼(sim s) 끊기면 마지막 값을 쓰지 않고 느린 쪽으로 둔다 |
| `report_step_percent` | `5.0` | 속도 %가 이만큼 바뀔 때 로그 |
| `costmap_topic`, `speed_limit_topic`, `odom_topic`, `map_topic` | `local_costmap/costmap`, `speed_limit`, `odom`, `map` | 네임스페이스 안 상대 이름 |
| `stop_rule` | `true` | 진행 방향 앞, 몸체 폭 띠 안에 **지도에 없는** 장애물이 `stop_m` 안이면 1 %(0.01 m/s)로 멈춘다. 정적 지도와 TF 가 없으면 규칙을 끈다 |
| `stop_m`, `resume_m`, `resume_delay_s` | `0.6`, `0.9`, `1.0` | 멈춤 거리, 재개 거리·지연. 고른 값이다 |
| `stop_diagnostics` | `false` | 상세 시계열 로그(#752). 판정에는 관여하지 않는다 |

정지 규칙이 지도에 없는 장애물을 놓친 사례는 #752 에서 진단 코드만 들어갔다. 감지 수정은 v1.1.0 에 없다(v1.1.0 릴리스 노트).

**판정은 현황 줄로 한다.**

    speed limit 100%=1.00 m/s (여유 ≥1.80 m, 받은 코스트맵 190장)
    speed limit 64%=0.64 m/s (여유 1.23 m, 받은 코스트맵 204장)
    speed limit 50%=0.50 m/s (여유 0.84 m, 받은 코스트맵 690장)
    speed limit 50%=0.50 m/s (여유 모름(창에 장애물 0), 받은 코스트맵 701장)

`여유` 는 셋 중 하나로 찍힌다. `x.xx m` 은 벽까지 거리다. `far_m` 안에서 잰다. `far_m` 은 1.8 m 다. `≥1.80 m` 은 그 안엔 없다는 뜻이다.
지역 코스트맵 창 어딘가엔 장애물이 있다. 넓다. 100 % 다. `모름(창에 장애물 0)` 은 창 전체가 빈 것이다.
격자가 깨진 것도 같다. 느린 쪽이다. 첫 줄은 5a51804 원문이다. master01 이다. 회차28 이다.
위 예는 근접 속도가 0.5 이던 때다. 0.7(#788) 뒤에는 근접 하한이 `70%=0.70 m/s` 로 찍힌다.

- `받은 코스트맵` 이 0 → 구독이 안 붙었다. 경고 줄이 발행자 수와 QoS 를 말한다.
- 장 수는 는다. `여유 모름` 만 있다. 격자가 비었다. 장애물 층의 관측 토픽을 본다. `hospital-nav-l3.md` 8절이다.
- 100 % 와 낮은 값이 **번갈아** 나오면 감속기가 실제로 도는 것이다.

## zones.yaml

구역 자세·허용오차와 고정 프레임은 `rokey_p3_description/config/` 의 구역 파일 하나에서 온다
(계약 3절, **simulation 소유**). `fleet`·`zones_tf`·`dock_origin_tf` 가 `zones_file` 로 같은 파일을 읽는다.
v1.1.0 병원 한 바퀴는 `zones.hospital-receiver.yaml` 이다(자동 생성물, `load` = `dock_1`, #790·#795). 목록은 [description README](../rokey_p3_description/README.md#config--구역경로-파일)에 있다.
`test/test_zones_skeleton.py` 가 그 파일의 키를 `zones.py` 가 전부 받는지 본다.

`zones_file` 을 비우면 기본 `zones.yaml` 을 읽는다. 그 파일의 값은 지금도 전부 0 이라 `arrived=true` 가 나오지 않는다.
기본 파일의 병동 zone 은 `bed_a1`·`station_a` 뿐이다(RFC 0001 5절). 병원 파일에는 `bed_a1`–`bed_a4`, `bed_b1`–`bed_b6`, `station_a`–`station_d`, `dock_1`–`dock_4` 가 있다.

## zones_tf

`zones.yaml` 을 읽어 `map` 아래 고정 프레임을 `/tf_static` 으로 **1회** 낸다(계약 3절).
transient local 이라 늦게 뜬 노드도 받는다.

| 프레임 | 어디서 |
| --- | --- |
| `pharmacy/belt_end`, `pharmacy/shelf`, `pharmacy/dispenser_slot_a`, `pharmacy/dispenser_slot_b` | `pharmacy:` 항목 |
| `<zone>/cabinet`, `<zone>/tag` | 구역의 `cabinet:`·`tag:` 항목 |

한 부모→자식 변환의 작성자는 하나다. 이 프레임들의 작성자는 `zones_tf` 이고,
Isaac 은 `map`·`odom` 을 내지 않으며 `amr_1/base_link` 아래만 낸다.

## launch 와 파라미터

| 파일 | 무엇 |
| --- | --- |
| `launch/navigation.launch.py` | `base_driver`, `fleet`, `zones_tf` + (AMCL 이 없을 때) `dock_origin_tf` + (선택) Nav2. 인자: `namespace`, `use_sim_time`, `use_nav2`, `zones_file`, `params_file`, `map`, `nav2_params_file`, `motion_backend`, `nav2_final_approach`, `localization`(`amcl` \| `odom`), `routes_file` |
| `launch/nav2.launch.py` | `map_server`, `amcl`(`localization:=amcl` 일 때만), `controller_server`, `planner_server`, `behavior_server`, `bt_navigator`, lifecycle manager 둘, `map_activation_guard`, `speed_governor` |
| `config/navigation_params.yaml` | `base_driver`·`fleet`·`zones_tf`·`dock_origin_tf` 의 파라미터 |
| `config/nav2_params.yaml` | Nav2 파라미터 |
| `config/maps/` | `hospital.{pgm,yaml}`(전 높이)과 `hospital_scan.{pgm,yaml}`(라이다 높이). [maps README](config/maps/README.md) |

- `motion_backend:=waypoints` 는 빈월드 v0 다. 이 모드에서는 Nav2 를 띄우지 않는다.
- AMCL 이 없는 두 경우(`waypoints`, `localization:=odom`)에는 `dock_origin_tf` 가 `map` → `<ns>/odom` 을 낸다. 항등이 아니라 도크 자리만큼 평행이동이다.
- `localization:=odom` 은 시뮬 전용이다. 병원 L3 에서 렌더 기하 지도 위 AMCL 이 0.18–0.31 m 어긋나서 넣었다(`navigation.launch.py` docstring).
- 전부 `use_sim_time: true` 다. `/clock` 작성자는 Isaac 하나다(계약 4절).
- 맵 경로는 `map` 인자다. 기본값은 설치된 `config/maps/hospital.yaml` 이다(9/23 추가).
- Nav2 노드는 `namespace`(기본 `amr_1`) 안에서 돌고 토픽은 그 안의 상대 이름(`scan`, `odom`, `cmd_vel`)이다.
  TF 는 remap 하지 않는다. `/tf` 는 전역이라야 Isaac·`base_driver`·`zones_tf` 와 한 트리가 된다.
- 레인 세 노드는 전역 네임스페이스에서 돌고 토픽 이름을 `robot_namespace` 로 만든다. 같은 이유다.
- `nav2_params.yaml` 의 footprint(1.10 × 0.90 m)·라이다 거리·`vy_samples`·goal tolerance 0.2 는
  master02 `~/test_amr`(이태규 작업, 저장소 밖, 9/20)에서 Isaac 주행이 돌던 값에서 왔다. inflation 은 지금 local 0.9·global 1.5 다(v1.1.0 파일).
  goal tolerance 는 도킹 오차 측정 뒤 `zones.yaml` 의 `tol_xy`·`tol_yaw` 와 함께 다시 정한다.
  footprint 에는 수납한 팔·상판·적재물이 아직 들어 있지 않다(RFC 0001 4절).
- 플러그인 타입 표기(`nav2_behaviors::Spin` 같은 `::` 형식)와 `progress_checker_plugins` 복수형은
  **Jazzy 기준으로 적었고 이 저장소에서 확인하지 못했다.** 마스터에서 `ros2 param dump` 로 본다.

## 마스터에서 확인할 것

> **상태: 지난 기록 (2026-09-20 기준).** 아래는 그날의 목록이다. 병원 주행 확인은 [병원 주행 런북](../../docs/runbooks/hospital-nav-l3.md)을 따른다.

- (확인됨) dummy 조인트 이름은 `dummy_base_prismatic_x_joint`·`..._y_joint`·`dummy_base_revolute_z_joint` 다(master02 `~/test_amr`).
  우리 저장소의 합성 stage 에서도 같은 이름인지는 이식 뒤 다시 본다.
- 리셋 뒤 AMR 이 놓이는 도크(`dock_k`)가 `dock_1` 이 맞는지.
- (해결됨) `rokey_p3_description` 은 `22d11d1` 부터 `config` 를 설치한다. `zones_file` 을 비우면 share 의 `config/zones.yaml` 을 읽는다.
- Nav2 costmap clear의 이름·타입은 이 호스트의 Jazzy 설치본에서 확인했고, fake 서비스 L2로 fleet의
  두 호출을 확인했다. 실제 Nav2가 같은 이름을 제공하고 reset 뒤 장애물이 비워지는지는 L3에서 확인한다.
- Nav2 Jazzy 의 플러그인 타입 표기와 파라미터 이름(`progress_checker_plugins`,
  `robot_model_type: nav2_amcl::OmniMotionModel`). 틀리면 lifecycle 이 active 로 안 간다.
- `/amr_1/scan` 이 실제로 오는지, 프레임이 `amr_1/lidar_link` 인지.
  `~/test_amr` 은 전역 이름(`/scan`, `lidar_link`)이다. 이식할 때 네임스페이스·접두를 넣는다.
- 9/17 맵 추출 시 yaml `origin` 을 Isaac world 원점·축에 맞췄는지. 9/23 병원 지도는 USD 렌더 기하에서 만들었다([maps README](config/maps/README.md)).
