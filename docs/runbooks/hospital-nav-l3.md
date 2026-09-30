# 병원 씬 주행 v0 — PDF 기대 경로 셋 (L3 런북)

- 상태: 병원 주행 참고 문서다. **지금도 쓰는 절은 5절(지도·앵커·구역·경로 다시 만들기)과 8절(장애물 층이 듣는 토픽)이다.**
- 2–4절과 6·7절은 9/23 주행 단독 L3 기록이다(waypoints v0, Nav2 트랙 3–6회차). 스테이지 preset 은 `hospital-nav` 다.
- 지금 한 바퀴의 주행은 `tools/demo_v2.sh` 가 띄운다. Nav2, 전 높이 `hospital.yaml`, `nav2_final_approach:=true localization:=odom` 이다(`nav_cmd`). 명령은 [hospital-full 2절](hospital-full.md#2-한-바퀴)이다.
- 기준: 2026-09-30 에 `v1.1.0`(`f316197`)의 `nav_cmd`·`sim/standalone/hospital_nav_files.py`·zones 두 벌과 대조했다. 장면: `sim/scenes/hospital_navigationv1.usda`.
- 처음 쓸 때(9/23, 브랜치 `feat/sim-hospital-nav-anchors`)는 Isaac 에서 돈 적이 없었다. 지도·앵커·구역·경로는 그 PR 에서 USD 로 만들었다.

> **한계(9/23 v0).** 지도는 USD **렌더 기하**로 만든 것이다. Isaac PhysX 충돌 기반 생성기와는 대조하지 않았다.
> 정차 자세의 팔 도달은 표준 UR5 DH로 IK만 풀었다. 경로 충돌은 안 봤다.
> 주행은 고정 경로 추종(waypoints)이다. Nav2·AMCL·라이다는 쓰지 않는다.
> 합본 자산에는 라이다·손목 카메라가 없다(#408 6.5절).

## 1. 무엇을 보나

재범 P3_Map.pdf(9/22)의 기대 경로 셋을 **한 회차에 이어서** 돈다(재범 지시: 한 바퀴 통으로).

| PDF | 목표 순서(출발 dock_1) | 지나는 곳 |
| --- | --- | --- |
| 3: A1 → B | `station_a` | 로비 |
| 2: A3 → C2 | `dock_3` → `bed_b1`(D5) | C2 병실 문 |
| 1: A4 → D4 | `dock_4` → `bed_a4`(D4) | C1 병실 북쪽 문 |
| 복귀 | `dock_1` | |

**D3(`bed_a3`)는 없다.** 협탁이 없고 그 자리에 보급 카트·의자가 있다. 씬 수정이 필요하다.
PDF와 zone 이름은 이렇게 맞춘다. A1–A4 = `dock_1`–`dock_4`. 적재 `load`는 A1 자리다.
B = `station_a`. D1–D4 = `bed_a1`–`bed_a4`. D5–D10 = `bed_b1`–`bed_b6`.
C1·C2는 zone이 아니라 경로의 경유점이다.

## 2. 기동

```bash
export ROS_DOMAIN_ID=<그날-예약한-도메인>
REPO=<repo 절대 경로>
# 1) 스테이지: 병원 씬 + AMR 합본. 우리 방·상자는 만들지 않는다(--preset hospital-nav).
~/isaacsim/python.sh $REPO/sim/standalone/pharmacy_stage.py --preset hospital-nav \
  --base-usd $REPO/sim/scenes/hospital_navigationv1.usda \
  --amr-combined "$P3_AMR_COMBINED" --amr-start -8.995 4.686 \
  --duration 1200 --kit-log-file <로그>
# 2) 주행: waypoints 백엔드, 병원 zones·routes
ros2 launch rokey_p3_navigation navigation.launch.py motion_backend:=waypoints use_nav2:=false \
  zones_file:=$REPO/src/rokey_p3_description/config/zones.hospital.yaml \
  routes_file:=$REPO/src/rokey_p3_description/config/routes.hospital.yaml
# 3) 팔 인터락 대역(팔 노드를 안 띄우므로 at_home 만 낸다 — 실습26 과 같다)
ros2 run rokey_p3_bringup stub_arm --ros-args -p use_sim_time:=true
# 4) 목표: 한 goal 이 끝난 뒤 다음을 보낸다
for z in station_a dock_3 bed_b1 dock_4 bed_a4 dock_1; do
  ros2 action send_goal /amr_1/go_to_zone rokey_p3_interfaces/action/GoToZone "{zone_id: $z}" --feedback
done
```

`--amr-start`는 `zones.hospital.yaml`의 `dock_1` (x, y)다. `dock_origin_tf`는 그 자리에 `map → amr_1/odom`을 내는 TF다.
AMR은 yaw 0으로 선다. `dock_1`의 yaw(−90°)는 첫 복귀 때 맞춘다.
병원 컨베이어와의 통합은 다음 단계다. `--no-room`이어도 스테이지 벨트는 만들어진다.
빈월드 자리, x 1.35–2.95·y 1.0·z 0.75다. 로비에 남는다. 경로에서 가장 가까운 곳은 2.0 m다.
이 숫자는 오프라인 계산값이다.

## 3. 판정선 (결과를 보기 전에 고정)

막으려는 것 → 재는 값 → 기준.

**기동**
- 병상이 빠진다 → 스테이지 `base_scene …` 줄의 `root_prims_loaded` 에 `SM_HospitalBed_02d4_02`–`_07` 여섯 →
  **여섯 다 있다**, `WARN base_scene root prims … not loaded` 줄 **0**.
- 로봇이 둘이다 → 같은 줄 `deactivated` = `['ridgeback_ur5']`, `WARN base_scene articulations …` **0**.
- 출발 자리가 어긋난다 → `amr built … start_xy=(-8.995 4.686)`, `tf2_echo map amr_1/base_link` 가 그 자리에서 **0.02 m 안**.

**goal 마다(여섯)**
- 못 간다 → result `arrived: true`, 걸린 시간(sim)을 적는다.
- 도착했다는데 거기가 아니다 → 스테이지 참값(`amr base_pose`)이 zone 자세에서 **d_xy ≤ 0.05**, yaw ±0.2.
- 몸체가 무언가를 친다 → `a=`·`b=` 에 `/Amr/` 가 든 **`touch` 0**. `near` 는 쌍·최소 `sep` 을 적는다(관측).
  특히 **도착 직전 회전 구간**(마지막 경유점 → 정차 자세)을 본다 — 정차 자세는 고정물 옆 0.05 m 에 서고
  제자리 회전 반경(0.64 m)이 나오지 않는다. 경로는 회전이 되는 접근점을 마지막 경유점으로 두었다.
- 문을 못 지난다 → #523 씬의 C1·C2 개구부를 지난다.
  벽 메시 폭은 약 1.97 m 다. 전 높이 지도에서 가운데 여유는 0.90–0.95 m 다.

**회차 전체**
- Traceback 0 · `[ERROR]` 0 · rtf(관측, 병원 씬 + AMR 합본의 첫 값) · 창 모드면 클립 파일명·크기·sha256.

## 4. 멈추는 기준

- goal 이 `rejected` 면 원문을 적고 멈춘다.
- `/Amr/` `touch` 가 찍히면 그 goal 을 취소하고 다음 goal 로 가지 않는다(경로·정차 자세 수정 대상).

## 5. 다시 만들기(Isaac 없이)

```bash
python3 sim/standalone/localize_isaac_assets.py --usd sim/scenes/hospital_navigationv1.usda --cache <캐시> --out <로컬 사본.usda>
python3 sim/standalone/extract_hospital_anchors.py --usd <로컬 사본.usda> \
  --source-sha-of sim/scenes/hospital_navigationv1.usda > sim/scenes/hospital_navigationv1.anchors.json
python3 sim/standalone/usd_occupancy_map.py --usd <로컬 사본.usda> --out-dir src/rokey_p3_navigation/config/maps \
  --source-sha-of sim/scenes/hospital_navigationv1.usda --source-name sim/scenes/hospital_navigationv1.usda \
  --skip /World/ridgeback_ur5 --skip /World/PouchTemplate
python3 sim/standalone/hospital_nav_files.py --zones  > src/rokey_p3_description/config/zones.hospital.yaml
python3 sim/standalone/hospital_nav_files.py --routes > src/rokey_p3_description/config/routes.hospital.yaml
python3 sim/standalone/hospital_nav_files.py --report    # 정차 자세·접근점·경로 여유·팔 IK
# 카메라 집기(v1.1.0 병원 기본)의 zones·routes 는 --receiver 로 만든다(dock_1 = load = 탁자 앞 적재 자리, #797)
python3 sim/standalone/hospital_nav_files.py --receiver --zones  > src/rokey_p3_description/config/zones.hospital-receiver.yaml
python3 sim/standalone/hospital_nav_files.py --receiver --routes > src/rokey_p3_description/config/routes.hospital-receiver.yaml
```

pxr 는 usd-core 또는 Isaac python 이다. 씬이 바뀌면 위를 다시 돌리고 `sim/tests/test_hospital_nav.py` 가 잡는다.

`v1.1.0` 의 두 zones 파일에서 `dock_1` 은 `load` 와 같은 자세다(#790, #797). 오케스트레이터는 그때 적재 GoToZone 없이 도크에서 바로 싣는다(`trip_fsm.load_is_dock`).

| 파일 | `dock_1` = `load` (x, y, yaw) | 쓰는 구성 |
| --- | --- | --- |
| `zones.hospital.yaml` | (−8.995, 4.686, −90°) | 참값 집기(`P3_CAMERA_POUCHES=0`, protocol v4) |
| `zones.hospital-receiver.yaml` | (−8.266, 4.102, −90°) | 카메라 집기(`v1.1.0` 병원 기본) |

dock_2–4 는 두 파일에서 같다. (−6.015, 4.686)·(−3.018, 4.686)·(−0.076, 4.686), yaw −90° 다(#795).

## 6. Nav2 트랙(같은 경로 셋을 Nav2 로)

**L3 미실행.** 5절까지(waypoints)가 선 뒤에 돈다. 바뀌는 것은 라이다와 주행 백엔드뿐이고 zones·판정선은 같다.

| 항목 | 값 |
| --- | --- |
| 라이다 | 스테이지 `--amr-lidar`. RTX 2D(`Example_Rotary_2D`). 합본 `base_link` 로컬 (0.43, 0, 0.25) = 하판·상판 사이. 토픽 `/amr_1/scan`, 프레임 `amr_1/lidar_link`. TF는 로봇 링크와 같이 나간다. LaserScan은 한 바퀴를 다 돌아야 한 번 나온다 |
| 지도 | `maps/hospital.yaml`(navigation.launch 의 `map` 기본값) |
| 위치 | AMCL이 `map → amr_1/odom`을 낸다. **`dock_origin_tf`는 뜨지 않는다.** waypoints 모드에서만 뜬다 |
| footprint | `nav2_params.yaml` 1.10 × 0.90(계획치). 내접 0.45 · 외접 0.71 · inflation 0.65 |
| 지도(Nav2) | 5회차부터 전 높이 `hospital.yaml` + `localization:=odom`(아래 '3회차 뒤'). 띠 지도 `hospital_scan.yaml`(z 0.18–0.32, 새 라이다 월드 높이 약 0.306; 기존 회차는 0.256)은 AMCL 을 쓸 때만 쓴다 — 2회차에 전 높이 지도로 AMCL 이 0.31 m 어긋났다 |
| 마지막 구간 | `nav2_final_approach:=true`. Nav2 는 마지막 waypoint(회전이 되는 접근점)까지 zone yaw 로 간다. 고정물 옆 0.05 m 정차 자리는 추종기가 곧장 간다. 2회차는 Nav2 footprint 로 정차 자리에 들어갈 궤적이 없어 0.56 m 앞에서 섰다 |

문 통과 숫자는 #523 씬 기준으로만 쓴다. 옛 씬(C1 두 문·C2 문, 가운데 여유 0.60 m, C1 남쪽 막힘)의 값은 쓰지 않는다.
#523 씬(9/23)은 문짝·문턱을 없애고 개구부를 넓혔다. 병실 입구는 C1 하나(옛 북쪽 자리)와 C2 하나다.
벽 메시를 z 1.0 에서 자른 폭은 C1 1.976 m, C2 1.973 m 다. 출처는 앵커 JSON `doors` 다.
전 높이 지도에서 개구부 가운데 여유는 C1 0.95 m, C2 0.90 m 다. 내접 0.45 와 경로 반경 0.56 보다 크다.

```bash
# 1) 스테이지: 2절 명령에 --amr-lidar 를 더한다
# 2) 주행: Nav2 백엔드(기본값). 지도는 전 높이 hospital.yaml, 위치는 odom(AMCL 없음)이다. 마지막 구간은 추종기다.
ros2 launch rokey_p3_navigation navigation.launch.py \
  zones_file:=$REPO/src/rokey_p3_description/config/zones.hospital.yaml \
  routes_file:=$REPO/src/rokey_p3_description/config/routes.hospital.yaml \
  map:=$REPO/src/rokey_p3_navigation/config/maps/hospital.yaml \
  nav2_final_approach:=true localization:=odom
# 3) 첫 초기 자세(리셋 전에는 fleet 가 안 낸다). AMR 은 dock_1 에 yaw 0 으로 선다
ros2 topic pub --once /amr_1/initialpose geometry_msgs/msg/PoseWithCovarianceStamped \
  "{header: {frame_id: map}, pose: {pose: {position: {x: -8.995, y: 4.686}, orientation: {w: 1.0}}}}"
# 4) stub_arm, 그리고 2절과 같은 goal 여섯
```

추가 판정선(결과 전에 고정):
- 라이다가 조용히 빠진다 → 스테이지 `amr lidar prim=… topic=/amr_1/scan` 줄. `WARN amr lidar disabled` **0**.
  `ros2 topic hz /amr_1/scan`이 0보다 크다(값은 기록). `tf2_echo amr_1/base_link amr_1/lidar_link` = (0.43, 0, 0.25).
- 위치 추정이 어긋난다 → 도착마다 AMCL 자세(`tf2_echo map amr_1/base_link`)와 스테이지 참값의 차를 적는다(관측).
- 자기 몸체 반사 → 라이다 뒤쪽을 포함해 `/scan` 에 차체 근거리 반환·장시간 빈 각도가 없는지 확인한다. 로컬 costmap 의 자기 발자국 안 장애물과 옆·뒤 사각을 RViz 캡처로 남긴다.

**3회차 뒤(9/23)**: 3회차는 `d0d9e20` 에서 0/6 이었다. station_a 접근점 0.25 m 앞(goal 공차 0.2 밖)에서 `Failed to make progress` 가 여섯 번 났다. 180 s 를 넘겼다. AMCL 은 참값과 0.18 m 어긋났다. 4회차부터 아래 두 가지를 더한다.

| 항목 | 값 |
| --- | --- |
| 넘김 반경 | `nav2_handoff_radius` 0.5(기본). 접근점까지 이만큼 남으면 fleet 가 Nav2 goal 을 거둔다 |
| 넘긴 뒤 | 추종기가 접근점을 거쳐 정차 자리로 간다. 반경 밖에서 Nav2 가 실패하면 그대로 실패다 |
| 위치 | `localization:=odom`(시뮬 전용). AMCL 을 띄우지 않는다. `dock_origin_tf` 가 `map → amr_1/odom` 을 낸다. waypoints 모드와 같다. 위 Nav2 기동의 initialpose 는 내도 받는 노드가 없다 |

```bash
# 2) 주행(4회차): 위 Nav2 launch 에 두 인자를 더한다
#   nav2_final_approach:=true localization:=odom
```

4회차 판정선(결과 전에 고정): `localization:=odom` 은 AMCL 판정이 아니다. 기존 2절 판정(도착 6/6, touch 0, 정차 d_xy ≤ zone 공차)을 그대로 쓴다. 더 적는 것은 목표마다 fleet 의 `Nav2 goal 을 거둔다` 줄이 나왔는지다(관측). AMCL 오차의 원인(렌더 기하 지도, 라이다 장착 위치)은 따로 본다.

**4·5회차 관측, 6회차 고침(9/23)**: 4회차(`5c31405`, 띠 지도)는 3/6 이었다. bed_b1 → dock_4 에서 C2 문 몰딩(z 0.157)에 닿았다. 5회차(같은 SHA, 전 높이 지도 `hospital.yaml`)도 3/6 이었다. bed_b1 로 가며 트레이 벽이 C2 문짝 끝(22.02, −0.19)에 닿았다. 두 물체 모두 전 높이 지도에는 있다. 로컬 costmap 은 스캔만 쓰고 있었다. 라이다 사각인 옆·뒤가 비었다. 6회차부터 로컬 costmap 에 static layer 를 더한다. 지도는 `localization:=odom` 과 함께 전 높이 `hospital.yaml` 을 쓴다.

6회차 판정선(결과 전에 고정): 2절 판정 그대로다. 도착 6/6, touch 0, 정차 d_xy ≤ zone 공차. 더 적는 것은 C2 문 통과 때 `Failed to make progress` 횟수다(관측).

**6회차 결과(9/23, `3d8e376`)**: 3/6 이다. C2 문으로 들어갈 때 touch 0, 무진전 0 이다. bed_b1 에서 나갈 때 트레이가 같은 문짝 끝(22.04, −0.18)에 닿았다. 그 문짝은 #523 씬에서 없다. **다음 회차는 7회차다.** #524 의 지도·zones·routes 로 돈다. 판정선은 도착 6/6, touch 0 이다. L3는 미실행이다.

## 7. 라이다 차체 가림과 local costmap 변경 후보

`main`의 local costmap에는 이미 2D `obstacle_layer`가 있으며 `voxel_layer`는 없다. 이 후보에서는 local `static_layer`만 빼고 `obstacle_layer + inflation_layer`를 사용한다. 전역 costmap의 `static_layer`는 유지한다. 지도 파일은 별도 수정 중이므로 이 변경에 포함하지 않는다.

Isaac 5.1 원본 `ridgeback_ur5.usd`를 읽어 `base_link/visuals/mesh_0`가 시각 전용이고 `base_link/collisions/mesh_0`는 `PhysicsCollisionAPI`가 있는 별도 프림임을 확인했다. `--amr-lidar`의 기본 장착점은 `(0.43, 0, 0.25)`이고, 기본 장착점일 때 시각 mesh만 스테이지에서 `invisible`로 오버라이드한다. 원본 USD나 충돌체는 삭제하지 않는다. 이 조치는 RTX 라이다의 렌더 메시 가림에 대한 제안이며 Isaac 실측 완료는 아니다. 충돌체를 끄면 로봇-환경 접촉 판정이 달라지므로 금지한다.

**L3 확인 전에는 완료로 보지 않는다.** 같은 지도·속도·경로로 6목표 도착 6/6, `/Amr/` touch 0을 확인한다. `/amr_1/scan`의 전·측·후방 각도와 유효 거리, RViz local costmap의 자기 반사·사각, C2 출입 및 낮은 몰딩/높은 장애물의 감지 여부를 비교한다. 단일 2D 높이 평면에 들지 않는 장애물이 보이지 않으면 local static 제거를 되돌리거나 추가 센서를 검토한다. custom `--amr-lidar-mount`는 이 기본 장착점의 가림 오버라이드를 적용하지 않으므로 별도 검증한다.

## 8. 장애물 층이 듣는 토픽 (9/23 회차18)

**증상.** `speed_governor` 가 코스트맵을 받는다. 장 수가 는다. `여유 모름` 만 찍는다. 주행은 6/6 이다. touch 는 0 이다.
멀쩡하다. 오류가 없다. 경고도 없다.

**원인.** 두 코스트맵의 장애물 층이 **아무도 안 내는 토픽**을 듣고 있었다.

    ros2 node info /amr_1/local_costmap/local_costmap   → Subscribers: /amr_1/local_costmap/scan
    ros2 topic info /amr_1/scan                          → Publisher 1 (Isaac), Subscription 0

`Costmap2DROS` 는 `/amr_1/local_costmap` 네임스페이스의 노드라, 관측원의 상대 이름 `scan` 이 한 단계 더
들어간다. `amcl.scan_topic: scan` 은 멀쩡했다 — amcl 은 `/amr_1` 에 바로 떠서 상대 이름이 맞게 풀린다.
그래서 측위는 됐고, 주행이 되던 것은 전역 코스트맵의 **정적 지도** 덕이다. 지도에 없는 것(사람·옮긴 카트·
다른 AMR)은 그동안 한 번도 비용에 들어간 적이 없다.

**고침(#620).** yaml 에 `<robot_namespace>/scan` 이 있다. `nav2.launch.py` 가 `nav2_common.ReplaceString` 으로
`/<namespace>` 를 넣는다. `/amr_1/scan` 을 박으면 `namespace` 인자가 죽는다. 시험
`test_nav2_observation_sources.py` 가 치환 **뒤**의 이름을 본다. yaml 과 launch 가 같은 자리표시를 쓰는지 본다.

**확인 한 줄.** 기동 뒤 `ros2 topic info /amr_1/scan` 의 Subscription 이 **2 이상**이다(local·global 코스트맵).
병원 회차는 `localization:=odom` 이라 AMCL 이 없다. AMCL 을 켜면 3 이다. 138cbac master02 실측은 Subscription 2 다(#240).

**같이 볼 것.** 장애물 층이 살아나면 7절의 차체 반사가 처음으로 비용에 들어간다. `여유` 가 자리와 상관없이
0.5 m 근처에 붙어 있으면 자기 몸이다. 그리고 **라이다는 시각 메시도 본다** — 스캔 높이(0.1–0.6 m)에 세운
소품은 가짜 장애물이 된다(9/24). 병원 데코는 벽에 붙인다. 1.0 m 위다. 바닥 띠는 1 mm 이하다.

**교훈.** 코스트맵 미수신·제한 미적용·관측원 미구독 셋 다 **조용히** 났다. 구독은 붙고 메시지도 오는데
내용이 비었다. 로그를 오래 읽기보다 `ros2 node info <노드>` 로 무엇을 실제로 구독하는지 먼저 본다.

