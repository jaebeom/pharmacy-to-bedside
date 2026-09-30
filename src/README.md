# src

ROS 2 패키지를 두는 colcon 워크스페이스의 소스 디렉토리다.
v1.1.0(`f316197`) 병원 한 바퀴의 ROS 쪽 노드는 전부 여기 여섯 패키지에서 나온다.
저장소 루트에서 `colcon build` 를 실행하면 여기 있는 패키지를 빌드한다.

```bash
colcon build --symlink-install
source install/setup.bash
```

`build/`, `install/`, `log/` 는 빌드 산출물이라 추적하지 않는다.

## v1.1.0 병원 한 바퀴에서 뜨는 노드

`P3_WORLD=hospital tools/demo_v2.sh up` 이 띄우는 ROS 노드다(`tools/demo_v2.sh` 의 `arm_cmd`·`nav_cmd`·`stack_cmd`).
실제 명령은 `tools/demo_v2.sh cmds` 로 본다. 절차는 [병원 전 구간 런북](../docs/runbooks/hospital-full.md)이다.

| 역할(`P3_ROLES`) | 명령 | 뜨는 노드 |
| --- | --- | --- |
| `arm` | `ros2 run rokey_p3_manipulation m0609_arm`(`scene_version:=2`, `v2_rail_select:=preferred_first`, `container_check:=true`) | `m0609_arm` |
| `nav` | `ros2 launch rokey_p3_navigation navigation.launch.py`(`map:=…/hospital.yaml`, `localization:=odom`, `nav2_final_approach:=true`) | `base_driver`, `fleet`, `zones_tf`, `dock_origin_tf`, Nav2(`map_server`·`controller_server`·`planner_server`·`behavior_server`·`bt_navigator`), `map_activation_guard`, `speed_governor` |
| `stack` | `ros2 launch rokey_p3_bringup stub_loop.launch.py`(`use_isaac_adapter:=true`, 스텁 넷 끔, `use_ur5_arm:=true`, `use_pouch_detector:=true`, `use_m0609_detector:=true`, `pharmacy_db:=true`) | `orchestrator`, `event_logger`, `isaac_adapter`, `arm`(UR5), `pouch_detector`, `m0609_detector` |

- 스텁 넷(`stub_sim`·`stub_arm`·`stub_fleet`·`stub_detector`)과 `order_generator` 는 이 구성에서 뜨지 않는다.
- 주문은 관제 웹(`web/`)에서 넣는다.
- 인자 전체는 [bringup README](rokey_p3_bringup/README.md#v110-병원-한-바퀴의-stack-인자)에 있다.

## 패키지 만들기

```bash
cd src
ros2 pkg create --build-type ament_python <패키지명>
```

## 현재 패키지

담당은 역할 이름이다([Git 가이드](../docs/process/git-start-guide.md#담당-다섯-자리--내-폴더만-고친다)). 코드 소유자는 `.github/CODEOWNERS` 다.

| 패키지 | 내용 | 담당 | CODEOWNERS |
| --- | --- | --- | --- |
| [`rokey_p3_description`](rokey_p3_description/README.md) | 구역·경로 파일(`config/`), 조제기 USD 자산, 씬 | simulation | `@parksejun12`(박세준) |
| [`rokey_p3_interfaces`](rokey_p3_interfaces/README.md) | 메시지·서비스·액션(계약 v1, 파일 v1.1). 공용 | orchestration | `@jaebeom`(임재범) |
| [`rokey_p3_orchestrator`](rokey_p3_orchestrator/README.md) | 요청·배차·조제기 재고·약 DB·종료 상태·run 기록 | orchestration | 없음 |
| [`rokey_p3_bringup`](rokey_p3_bringup/README.md) | 기동 조합(launch), 스텁 넷, Isaac JSON 어댑터. 공용 | orchestration | 없음 |
| [`rokey_p3_manipulation`](rokey_p3_manipulation/README.md) | M0609 보충, UR5 픽·플레이스 | manipulation | 없음 |
| [`rokey_p3_perception`](rokey_p3_perception/README.md) | 손 카메라 봉투 검출·QR 판독 | manipulation | 없음 |
| [`rokey_p3_navigation`](rokey_p3_navigation/README.md) | 맵·Nav2·감속기·도킹 판정·구역 TF | navigation | `@Taegyu-Lee1117`(이태규) |

실행 파일은 각 패키지 `setup.py` 의 `console_scripts` 다. `ros2 run <패키지> <실행 파일>` 로 띄운다.

| 패키지 | 실행 파일 | launch |
| --- | --- | --- |
| `rokey_p3_orchestrator` | `orchestrator`, `order_generator`, `event_logger`, `status_monitor` | 없음 |
| `rokey_p3_bringup` | `stub_sim`, `stub_arm`, `stub_fleet`, `stub_detector`, `isaac_adapter`, `bringup_check`(뼈대, 로그 한 줄) | `stub_loop.launch.py`, `skeleton.launch.py`(뼈대 네 노드) |
| `rokey_p3_manipulation` | `arm`(UR5), `m0609_arm`(M0609 보충, 레일·v2), `refill_soak`(보충 연속 구동기) | 없음 |
| `rokey_p3_perception` | `pouch_detector`. `stub_loop.launch.py` 가 `pouch_detector`(amr_1)·`m0609_detector`(m0609) 두 이름으로 띄운다 | 없음 |
| `rokey_p3_navigation` | `fleet`, `base_driver`, `zones_tf`, `dock_origin_tf`, `map_activation_guard`, `speed_governor` | `navigation.launch.py`, `nav2.launch.py` |

`rokey_p3_description` 은 설정·자산, `rokey_p3_interfaces` 는 인터페이스만 있다. 각 노드가 무엇을 하고 어디까지 확인됐는지는 패키지 README 에 있다.
담당과 공용 패키지 변경 절차는 [Git 가이드](../docs/process/git-start-guide.md#병렬-작업에서-충돌-줄이기).

역할이 다르면 패키지를 나눈다. 인터페이스(msg/srv)는 별도 패키지로 두어야
다른 패키지에서 순환 의존 없이 참조할 수 있다.

런치 파일·설정·모델 파일은 **패키지 안에 두고 install 로 share 에 설치한다.**
설치하지 않으면 `ros2 launch` 가 찾지 못한다 — 파일이 `src/` 에 있어도 마찬가지다.
실행 시점에는 `get_package_share_directory()` 로 경로를 얻는다.

## 여기 두지 않는 것

| 대상 | 위치 |
| --- | --- |
| Isaac Sim standalone 스크립트 | [`sim/`](../sim/README.md) — Isaac 의 `python.sh` 로 실행되므로 colcon 빌드 대상과 섞지 않는다 |
| 강사 배포 자료 | [`docs/reference/tutor/`](../docs/reference/tutor/README.md) |
