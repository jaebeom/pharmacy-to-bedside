# `test_amr` 인수 — 무엇을 들였고 무엇이 남았나

| 항목 | 내용 |
| --- | --- |
| 상태 | **unreviewed** — 인수 기록이다. 결정·합격선이 아니다 |
| 검토자 | 미정 (navigation 담당) |
| 기준 | `main` @ `50d887c`. 반영 PR #383(머지 `5d1c46f`, README 문장 분리 `76fd685`) |
| 원본 | master02 `~/test_amr`, 이태규님 작업, **저장소 밖**, 2026-09-20 |
| run | 없음. 이 저장소에서 Isaac 을 돌린 적이 없다 |

이 저장소에는 그 작업의 사본이 없다. 아래 "관측"은 **원본을 읽은 쪽의 정리를 전달받은 것**이고, 이 문서를 쓸 때 master02 파일을 직접 읽지 않았다. 대조용 해시·mtime 은 #383 댓글로 요청해 두었고 아직 받지 못했다.

## 1. 반영한 값 (#383)

세 파일에 들어갔다. 값과 자리표시자만 바꿨고 노드 구조·토픽·계약은 그대로다.

| 파일 | 전 | 후 | 출처 |
| --- | --- | --- | --- |
| `config/navigation_params.yaml`, `rokey_p3_navigation/base_driver_node.py` | `dummy_base_x`·`_y`·`_yaw`(자리표시자) | `dummy_base_prismatic_x_joint`, `dummy_base_prismatic_y_joint`, `dummy_base_revolute_z_joint` | `~/test_amr/first_file/hospital_amr_nav.usd`(또는 그 씬 생성 스크립트) |
| `config/nav2_params.yaml` local·global costmap | `robot_radius: 0.6` | `footprint` 1.10 × 0.90 m 폴리곤 | `~/test_amr/ros2_ws/src/ridgeback_nav/config/nav2_params.yaml` |
| 같은 파일 | `inflation_radius: 0.7` | `0.65` | 같음 |
| 같은 파일 | raytrace 12.0 / obstacle 10.0 | `10.0` / `8.0` | 같음 |
| 같은 파일 local costmap | 6 × 6 | 5 × 5 rolling | 같음 |
| 같은 파일 DWB | `vy_samples: 5` | `20` | 같음 |
| 같은 파일 goal checker | 0.25 / 0.25 | `0.2` / `0.2` | 같음 |

**이미 같아서 바꾸지 않은 것**(대조 자체가 검산이다): AMCL(`nav2_amcl::OmniMotionModel`, `max_beams` 60, 입자 500/2000, alpha 0.2, `set_initial_pose: false`), planner(`NavfnPlanner`, tolerance 0.5, `allow_unknown`), 속도·가속도(±0.5 m/s, 1.0 rad/s, acc 1.0 / 2.0), `track_unknown_space`.

articulation root 는 `/World/hopital_custome/ridgeback_ur5` 다(철자는 USD 원문). LiDAR 는 `base_link/lidar_link/Lidar`, translate (0.35, 0.0, 0.45), `Example_Rotary_2D`, `laser_scan`.

## 2. 반영하지 않은 것과 이유

| 대상 | 이유 |
| --- | --- |
| `velocity_smoother`, `collision_monitor` 파라미터 | 우리 launch 에 그 노드가 없다. 값만 넣으면 돌지 않는다. 노드 추가는 별도 PR 이다 |
| local costmap 의 `voxel_layer` | 우리는 `obstacle_layer` 다. 플러그인 교체라 값 반영과 분리한다 |
| `station_dispatcher.py` | 채택하지 않는다. 계약 v1 2.2·5절상 이동 명령 경로는 `GoToZone` → `fleet` → Nav2 하나다. 선점·취소·타임아웃·복구는 `fleet` 과 orchestrator 에 있다 |
| `config/stations.yaml`(`station_1`·`station_2`·`home`) | 세 값이 자리표시자라 옮길 좌표가 없다. 이름도 zone id 규칙(`station_[a-z]`)과 다르다. 좌표의 자리는 `zones.yaml` 하나다(계약 3절) |
| `maps/hospital_map.{yaml,png}` | 3절의 지도 출처가 갈리기 전에는 들이지 않는다 |
| `navigation.launch.py`, `ridgeback_nav.rviz` | 우리 launch 와 역할이 겹친다. 네임스페이스·프레임 접두를 맞춘 뒤에 본다 |
| `hospital_amr_nav.usd`, `tools/create_hospital_amr_nav.py` | `sim/` 소유(simulation 레인)다. 주행이 들이지 않는다 |

**이름 차이**(이식할 때 맞춰야 한다): 그쪽은 전역 이름이다(`/scan`, `/odom`, `/cmd_vel`, 프레임 `base_link`·`lidar_link`). 우리 계약은 `/amr_1/` 네임스페이스와 `amr_1/` 프레임 접두다(계약 2.1·3절).

## 3. 남은 질문 둘

### 3.1 지도가 어느 stage 에서 나왔나 — 미확인

`hospital_map.yaml` 은 `origin [-11.725, -0.125, 0.0]`, `resolution 0.05`, 460 × 452 px(23.0 × 22.6 m)다.
계약 3절은 "`map` 의 원점·축 = Isaac world 의 원점·축"이고, 우리 런타임 world 는 원점 A 변환을 끝낸 **합성 stage** 다(#215).
이 지도가 **원본 병원 USD** 에서 나왔다면 좌표계가 다르다. 그 상태로 `zones.yaml` 에 좌표를 옮기면 전부 틀어진다. 확인 방법은 4절이다.

### 3.2 실제로 지나간 문·통로의 폭 — 미측정

반영한 footprint 는 1.10 × 0.90 m 다. 문 법선으로 곧게 지나도 폭 방향 0.90 m 를 차지한다.
그래서 계획 문서가 예로 든 0.9 m 문은 `passage.check_passage` 가 `BLOCKED` 로 본다(여유를 아무리 줄여도 같다).
- **해석(가설, 미검증):** 주행이 실제로 돌았다면 그 통로가 0.9 m 보다 넓었다는 뜻이다. 셋 중 하나다 — 실제 문이 더 넓다 / 지나간 곳이 문이 아니다 / footprint 를 줄일 여지가 있다.
- 실측 전에는 가릴 수 없다. 문 폭은 `hospital_topology.yaml` 의 `clear_width_m` 이 될 값이다.

## 4. 맵 원점 확인 — 판정선과 전제

**시연 뒤**에 한다. 전제: **담당자(이태규님)가 자기 master02 구성으로 돌리고, 다른 사람은 옆에서 읽기만 한다.** 남의 작업 공간을 대신 돌리지 않는다.
도메인은 결정 33 대로 master02 = 118 이다(결정 43 — 118 을 여럿이 쓰는 문제와 119/120 권고 — 는 **대기**).

절차: 로봇을 미리 정한 세 지점에 두고, 각 지점에서 Isaac world 자세(GT)와 AMCL 자세를 같은 sim 시각에 1 s 간격 5회 읽는다.
지점은 결과를 보기 전에 정한다(한 직선 위에 두지 않고, 하나는 지도 가장자리 3 m 안, 하나는 중앙부. yaw 는 0°·90°·180°).
AMCL 수렴 조건도 미리 고정한다(초기 자세 뒤 2 m 이동 + 90° 회전, 연속 3개 메시지에서 위치 표준편차 ≤ 0.1 m, 방위 ≤ 3°. 60 s 안에 못 만족하면 "수렴 실패").

| 먼저 볼 것 | 기준 |
| --- | --- |
| 산포 | 한 지점의 x·y 산포(최대 − 최소)가 **0.05 m 를 넘으면 그 회차는 "원점 판정 불가"** 다. 추정 오차와 원점 차이를 가를 수 없다 |

산포가 기준 안일 때만 아래를 본다. Δ = (AMCL) − (GT) 의 5회 평균이다.

| 판정 | 조건 | 다음 |
| --- | --- | --- |
| 같은 기준 | 세 지점 모두 `|Δx|`, `|Δy|` ≤ 0.05 m 이고 `|Δyaw|` ≤ 2° | 지도를 그대로 쓴다 |
| 원점만 다름 | 세 지점의 (Δx, Δy) 가 서로 0.05 m 안에서 같고 `|Δyaw|` ≤ 2° | 지도 yaml 의 `origin` 만 고친다. 좌표를 손으로 보정하지 않는다 |
| 축까지 다름 | 위 둘 다 아니다 | 지도를 합성 stage 에서 다시 뽑는다 |

0.05 m 는 costmap 한 칸(해상도 0.05)이다. 2° 는 관례값이고 실측 뒤 조정할 수 있다.

## 5. 한계

- 이 문서의 "관측"은 전달받은 정리다. 원본 파일의 해시·mtime 을 받으면 1절 표에 붙인다.
- Isaac 은 이 저장소에서 미실행이다. 반영한 값이 **우리 합성 stage 에서도 같은 결과를 내는지는 확인하지 않았다.**
- 3.2 의 해석은 가설이다. 문 폭을 재기 전에는 어느 쪽인지 알 수 없다.
