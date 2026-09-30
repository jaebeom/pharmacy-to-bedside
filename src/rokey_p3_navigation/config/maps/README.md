# 맵

v1.1.0 병원 한 바퀴는 전 높이 지도 `hospital.yaml` 을 쓴다(`tools/demo_v2.sh` 의 `P3_HOSPITAL_MAP` 기본). `localization:=odom` 이라 AMCL 은 뜨지 않는다.
지도는 `map_server` 가 내고 Nav2 코스트맵의 static layer 와 `speed_governor` 정지 규칙(지도에 있는 것 빼기)이 쓴다.

`map_server` 가 읽는 occupancy map 이 여기 들어간다. 기본 이름은 `hospital.yaml` 과 `hospital.pgm` 이고
`nav2.launch.py` 의 `map` 인자로 다른 경로를 줄 수 있다.

**9/23: `hospital.{pgm,yaml}`이 들어왔다.** Isaac PhysX 점유 지도와는 **대조하지 않았다.**
병원 주행 씬(`sim/scenes/hospital_navigationv1.usda`)의 USD 렌더 기하에서 `sim/standalone/usd_occupancy_map.py`로 만들었다.
Isaac 없이, 0.05 m, z 0.10–1.80 m 띠다. 원본 sha256은 yaml 머리에 있다.
충돌이 꺼진 visual도 막힌 칸이다. #523 씬(9/23)부터 병실 문짝이 없다.
씬의 `gripper`·`PouchPool` 은 `--skip` 으로 지도에서 뺐다. 복도 카트 `SM_SupplyCart_02a_28`(dock_3 → bed_b1 사이, x≈12) 도 `--skip` 이다.
씬 파일의 카트는 그대로다. hospital-nav preset 이 스테이지에서 그 카트를 끈다.
다시 만드는 법은 [병원 주행 런북](../../../../docs/runbooks/hospital-nav-l3.md) 5절이다.
waypoints 백엔드의 경로(`routes.hospital.yaml`, `routes.hospital-receiver.yaml`)도 이 지도 위에서 계산했다
([일정 9/17](../../../../docs/planning/schedule.md), [시나리오 단계 2](../../../../docs/planning/scenario.md#단계-2-자율-이송-조제실--병동)).

뽑을 때 확인할 것:

- yaml 의 `origin` 을 Isaac world 원점·축에 맞춘다. `map` 은 유일한 world 프레임이고
  원점·축이 Isaac world 와 같아야 한다([계약 3절](../../../../docs/architecture/delivery-contract-v1.md#3-프레임과-단위)).
  이 값이 어긋나면 `zones.yaml` 의 좌표가 전부 어긋난다.
- `resolution` 은 costmap 설정(`nav2_params.yaml` 의 0.05 m)과 맞춘다.
- 조제실 앞 적재 위치, 대기 도크, 복도, 병동이 한 장에 들어가야 한다.

**`hospital_scan.{pgm,yaml}`(9/23)**: 병원 L3 2회차에서 AMCL 이 0.31 m 어긋났다. 합본 라이다(#503) 스캔 높이는 0.256 m 다. 같은 씬을 라이다 높이 띠(z 0.18–0.32)만 투영한 지도다. 전 높이 지도에는 탁자·데스크 윗면이 있고 스캔에는 없다. AMCL 로 Nav2 를 돌릴 때 `map:=` 로 준다. v1.1.0 `demo_v2.sh` 는 이 지도를 쓰지 않는다.
waypoints 경로(`routes.hospital.yaml`)는 계속 전 높이 지도 `hospital.yaml` 로 계산한다. 몸체·팔이 윗면에 닿지 않게 하려는 것이다.
