# sim — Isaac Sim 실행 코드

Isaac Sim 5.1 전용 Python 으로 도는 스테이지와 준비 도구를 둔다.
Isaac 없이 도는 시험도 둔다([sim/tests](tests/README.md)).

## 지금 무엇이 현행인가 (v1.1.0 병원 한 바퀴)

기준은 태그 `v1.1.0` 이다. 커밋은 `f316197`(#797)이다.
이 절 밖의 절 대부분은 9/17–9/23 개발 기록이다. 그런 절은 첫 줄에 "지난 기록" 이라고 적었다.

- **한 바퀴 명령**: `P3_WORLD=hospital tools/demo_v2.sh up`. 절차는 [병원 전 구간 런카드](../docs/runbooks/hospital-full.md)다.
- **스테이지**: `standalone/pharmacy_stage.py --preset hospital`. `demo_v2.sh` 가 씬·워크셀·합본 AMR 인자를 채운다.
- **씬**: [`scenes/hospital_navigationv1.usda`](scenes/hospital-navigation-v1-changes.md)(박세준 병원 씬).
  조제실 입력(`base.usda`·`workcell.json`)은 `standalone/prepare_workcell_integration.py` 가 이 씬과 조제기 에셋으로 만든다.
- **preset `hospital` 이 켜는 기본값**(코드 `PRESETS["hospital"]`):

  | 항목 | 값 | 되돌리는 인자 |
  | --- | --- | --- |
  | 조제실 약통 | 18칸 가득(`--workcell-empty-cells 0`) | `--workcell-empty-cells N` |
  | 쓴 약통 | 선반으로 안 돌아온다(`--workcell-consume`, #791) | 끄는 인자가 없다 |
  | 씬 컨베이어 속도 | 잰 표면 속도 × 2.0(`HOSPITAL_CONVEYOR_SPEED_SCALE`, #789) | `--conveyor-speed-scale 1` |
  | 도크 벽 | 불투명도 0.35(`HOSPITAL_DOCK_WALL_OPACITY`, #792) | `--dock-wall-opacity 1` |
  | 바닥 안내선·표지 | 켬(`--hospital-decor`) | `--no-hospital-decor` |
  | 가짜 AMR·보행자 | 2대·2명 | `--traffic-dummies 0`·`--pedestrians 0` |
  | 봉투 풀 | 15개 | `--pouch-pool N` |
  | 레일 드라이브 | (1e5, 1e4, 5e4) | `--rail-drive …` |
  | 렌더 | 2틱에 한 번(`--render-every 2`) | `--render-every 1` |
  | 뷰포트 | 건물 조망 `floor_top` | `--view <병원 뷰 이름>` |

- **`demo_v2.sh` 의 병원 기본값**(`P3_WORLD=hospital`):
  - 카메라 집기가 기본이다(`P3_CAMERA_POUCHES=1`, #796·#797). 인식표도 손 카메라 QR 로 읽는다(`P3_CAMERA_TAGS`).
  - 봉투는 A1 모듈 탁자 `SM_SideTable_02a_74` 위에 선다(`--hospital-receiver-prim`).
  - AMR 출발 자리는 dock_1 = 적재 자리 `-8.266 4.102` 다(`zones.hospital-receiver.yaml`, #790). 도크에서 바로 집는다.
  - 합본 손목에 흡착 그리퍼+D455 를 붙인다(`--amr-hand-camera --camera-resolution 1280 800`). 자산은 [amr_gripper](assets/amr_gripper/README.md)다.
  - 봉투 QR(`--qr-dir`)과 약통 QR(`P3_CONTAINER_QR=1`)을 붙인다.
  - M0609 레일 후보 순서는 `preferred_first` 다(`P3_V2_RAIL_SELECT`). #797 에서 기본으로 켰다. 9/21 #391 에서는 opt-in 이었다.
- **main 에 없는 것**: M0609 모듈 집기 레일 순서 수정. 쓴 약통 물리 끄기. 박세준 로컬 커밋은 `8f106f6` 이다. push 되지 않았다.
- 감속기 근접 속도 0.7 m/s(#788)는 주행 쪽 설정이다. 이 폴더 밖이다.

```text
sim/
├── assets/         # amr_gripper/(흡착 그리퍼+D455 USD), decor/(병원 표지·라벨 텍스처)
├── scenes/         # hospital_navigationv1.usda(현행 병원 씬)·anchors.json, hospital_layout.usda(hospital_main.py·hospital-v2 용 옛 템플릿)
├── tests/          # Isaac 없는 unittest 파일 65개(usd-core 있으면 USD 시험 포함), Isaac 씬 로드 smoke 1개
└── standalone/     # pharmacy_stage.py(스테이지, 모든 preset), prepare_workcell_integration.py(병원 조제실 입력),
    │               # hospital_main.py(병원 씬 단독·컨베이어 분기), minimal_clock.py(0단계), m0609_refill_stage.py(0.5단계) 등
    └── p3sim/      # 공용 부품 48개. 병원 쪽은 hospital_*·workcell_*·amr_base·glass_wall 등
```

## 목차

- 현행: [지금 무엇이 현행인가](#지금-무엇이-현행인가-v110-병원-한-바퀴), [`src/`와의 경계](#src와의-경계), [빌드 셸과 실행 셸 분리](#빌드-셸과-실행-셸-분리), [Isaac ↔ ROS 어댑터 인터페이스](#isaac--ros-어댑터-인터페이스-json-v1), [병원 조제실 자동 인수 검토](#병원-조제실-자동-인수-검토)
- 병원 씬 자산: [병원 배치 씬](#병원-배치-씬-별도-자산)
- 지난 기록: [병원 씬 위에 조제실 얹기(hospital-v2)](#병원-씬-위에-조제실-얹기-이식-준비-isaac-미실행), [단계 요약](#단계-요약), [알려진 문제·미확인(9/18)](#알려진-문제미확인), [0단계](#0단계-빈-월드--clock), [0.5단계](#05단계-m0609-보충-스테이지), [0.7단계](#07단계-조제실-스테이지), [AMR 합본(9/21)](#amr-합본---amr-combined--오늘-회차로-알게-된-것)

## 병원 배치 씬 (별도 자산)

이 절의 팀 자작 자산 ZIP 은 현행 한 바퀴에도 필요하다. 조제기(DPB-80) 모델이 그 안에 있다.
현행 한 바퀴 씬은 `scenes/hospital_navigationv1.usda` 다. `pharmacy_stage.py --preset hospital` 이 그 씬을 쓴다.

`scenes/hospital_layout.usda` 는 병원·기존 컨베이어·조제기 배치와 참조만 담은 텍스트 USD 다.
`hospital_main.py`(병원 씬 단독 실행)와 옛 `--preset hospital-v2` 준비(`prepare_hospital_scene.py`)가 이 파일을 쓴다.
Isaac Collect Asset 이 복사한 NVIDIA 자산은 저장소에 넣지 않는다.
독립 실행 병원 씬에는 M0617 과 ROS `/clock` 그래프가 없으며, 맵의 기존 컨베이어와
제어 그래프를 그대로 사용한다.

팀 자작 자산은 GitHub Release 태그 `assets/hospital-20260918` 의 비공개 첨부로 받는다.
파일은 `hospital-custom-assets-20260918.zip` 이다.
저장소는 private 다. 익명 `curl` 은 404 다.
저장소 읽기 권한이 있는 `gh` 로 받는다.

```bash
# 저장소 루트. gh 가 이 저장소에 로그인돼 있어야 한다.
gh release download assets/hospital-20260918 -R jaebeom/ROKEY_P3_A3 -D sim/outputs
(cd sim/outputs && sha256sum -c ../scenes/hospital_assets.sha256)
```

전체 SHA-256 은 `f519fb2c3f0e386f99b27e7ce707db7a14c2f2730c0959ec6f472293d2410144` 다.
같은 값이 [`scenes/hospital_assets.sha256`](scenes/hospital_assets.sha256) 에 있다.
해시가 다르면 그 ZIP 으로 기동하지 않는다.

`hospital_main.py` 는 ZIP 을 `sim/outputs/hospital-custom-assets-20260918.zip` 에 둔다. 무시 대상인 `sim/outputs/hospital_runtime/` 아래에 자동으로 푼다.
`pharmacy_stage.py` 병원 한 바퀴는 그 자리를 보지 않는다. 런카드는 [hospital-full.md](../docs/runbooks/hospital-full.md) 다.
씬이 조제기를 `sim/material/etc/Automatic+Blister+Packing+Machine+(DPB-80)/model.usd` 에서 찾는다.
ZIP 안의 `material/` 을 `sim/material/` 로 푼다. 틀리면 조제기가 빠진 채 기동한다. master01 새 clone 회차32(`5a51804`, #240)에서 드러났다.

```bash
unzip -q -o sim/outputs/hospital-custom-assets-20260918.zip material/etc/* -d sim
```

ZIP 은 브랜치에 중복으로 넣지 않는다.

```text
<custom-assets>/
└── material/etc/Automatic+Blister+Packing+Machine+(DPB-80)/model.usd
```

기본 실행은 NVIDIA의 공식 Isaac Sim 5.1 자산 서버를 사용한다. 첫 실행에서 필요한
병원·컨베이어 자산을 자동으로 받고 Kit 캐시에 보관하므로 두 PC에 별도 collected USD
경로를 맞출 필요가 없다.

```bash
i_py sim/standalone/hospital_main.py
```

`i_py` 는 저장소에 정의가 없는 현장 셸 alias 다. Isaac `python.sh` 를 가리키는 것으로 본다(미확인).
`~/isaacsim/python.sh` 로 띄워도 스크립트가 내부 Jazzy 환경으로 스스로 다시 뜬다(`configure_internal_ros`).

인터넷이 없는 PC만 Complete Assets Pack의 `Assets/Isaac/5.1` 경로를
`P3_HOSPITAL_ISAAC_ASSETS_ROOT`로 지정한다. 준비 과정과 선택 인자는
[`standalone/hospital-standalone.md`](standalone/hospital-standalone.md)에 있다.

## 병원 씬 위에 조제실 얹기 (이식 준비, Isaac 미실행)

> **상태: 지난 기록 (2026-09-18 기준).** 지금은 [현행 절](#지금-무엇이-현행인가-v110-병원-한-바퀴)의 `--preset hospital` 을 따른다.
> `hospital-v2` preset 은 코드에 남아 있다. 지금 코드의 끄기 목록은 끔 47(씬 벨트 그래프 19)·강체 끔 19 다(`p3sim/base_scene.py`).
> 아래의 50·22 는 9/18 씬 기준 수다.

재범 계획 6단계 준비(9/18). 위 세준 씬 파일(`scenes/*`)은 고치지 않는다. 우리 스테이지가 그 씬을 **아래에 깔고** 조제실을 얹는다.

- `pharmacy_stage.py --base-usd <준비된 씬> --pharmacy-origin X Y Z YAW_DEG [--base-deactivate 경로…] [--base-rigid-off 경로…]`. 결정된 값은 `--preset hospital-v2`(아래).
  - 인자가 없으면 전과 같다(테스트).
  - 경로를 채우지 않은 씬(`__P3_…__` 남음)은 기동 전에 거절한다. 먼저 위 `prepare_hospital_scene.py` 를 돌린다.
- **방식**: 씬을 `/World/P3Base/Scene` 에 참조하고, 감싼 prim `/World/P3Base` 에 조제실 자세의 역변환을 건다(`p3sim/base_scene.py`).
  - 그래서 우리 좌표가 그대로 월드 좌표다. 텔레포트·IK 목표·겹침 질의·카메라·재고 JSON 을 고치지 않는다.
  - `--pharmacy-origin` 은 우리 원점(레일 중심 바닥)과 +x 방향을 **씬의 월드 좌표**로 준 것이다. 현재 병원 씬은 `/World` translate가 `(0, 0, 0)`이므로 map 좌표와 같다.
  - 씬 안의 절대 경로 relationship(예: 벨트 그래프의 `inputs:conveyorPrim`)은 USD 합성이 새 경로로 옮긴다(usd-core 테스트). OmniGraph 가 Isaac 에서 그대로 도는지는 미실행이다.
- **바닥**: 우리 GroundPlane 은 충돌만 남기고 숨긴다. 씬 바닥(z 0)과 같은 평면이라 겹쳐 그려지기 때문이다.
- **끌 prim**: `--base-deactivate`(prim 비활성)·`--base-rigid-off`(강체만 끔, 모양·정적 충돌은 남김)는 씬 기본 prim 기준 상대 경로다. 마지막 이름에 `*` 패턴을 쓸 수 있다(예: `Environment/hospital/SM_PillBottleSet_*`). 없는 경로는 `WARN base_scene deactivate paths not found` 로 알린다.
- **점검 도구(읽기만, usd-core)**: `python3 sim/standalone/hospital_scene_check.py <씬> [--hospital-v2 | --pharmacy-origin … --deactivate … --rigid-off …]`. 시점별 시선을 막는 씬 prim 도 알려 준다.
  - 씬 레이어만 봐도 /clock·ROS 2 그래프 노드, PhysicsScene, 벨트 그래프와 대상, 로봇 참조, 최상위 배치를 알려 준다.
  - 경로를 채운 씬이면 벨트 몸체의 합성 scale·kinematic·surface velocity, articulation root 를 더 본다.
  - 원점을 주면 우리 v2 상자와 로봇 범위(레일 x ±1.9, y −0.25..1.0, 높이 2.3)가 씬의 어느 prim 과 겹치는지도 알려 준다.

### 세준 씬 점검 결과 (9/18, usd-core)

자산 읽기: NVIDIA 공개 자산 서버의 `Assets/Isaac/5.1`(병원·소품·컨베이어, ridgeback 제외)과 팀 릴리스 zip(sha256 이 `scenes/hospital_assets.sha256` 과 같음). 둘 다 읽기용으로 받았고, `prepare_hospital_scene.py` 로 경로를 채운 씬을 scratchpad 에만 만들었다.

| 항목 | 관측 | 근거(prim 경로·좌표, 씬 월드) |
| --- | --- | --- |
| (a) /clock | 씬에 /clock·ROS 2 그래프 노드 없음, PhysicsScene 없음. /clock 은 우리 스테이지 그래프 하나뿐이 된다 | 레이어의 OmniGraph 노드 종류는 벨트 노드(`isaacsim.asset.gen.conveyor.IsaacConveyor`) 22개와 그 틱·변수 읽기 노드(`omni.graph.action.OnPlaybackTick`·`omni.graph.core.ReadVariable`)뿐이다(테스트는 ROS·clock 노드 0 과 벨트 노드 22 를 본다) |
| (b) 벨트 | 벨트 트랙 13개, 강체 22개. 전부 kinematic 이고 합성 scale 이 **0.5 균등**이다. surface velocity 는 0.5·−0.25·1.0 등 트랙마다 다르고, 트랙마다 `ConveyorBeltGraph`(OnPlaybackTick → IsaacConveyor, 변수 Velocity 0.5)가 매 틱 건다 | `/World/Conveyor` scale (0.5, 0.5, 0.5), 트랙 `ConveyorTrack*`(`ConveyorBelt_A03·A06·A09·A24`). 범위 x −8.54..1.51, y 7.42..12.91, z ≤ 1.16 |
| (c) 조제실 자리 | 세준 조제실 방은 x −10.68..3.03, y 8.28..14.96(바닥 z 0). 서쪽 벽에 약 선반 3개, 가운데에 세준 배치(M0617·조제기·테이블·벨트), 동쪽 벽 너머는 큰 홀(x 3.16..11.2, 계단 x 7.66) | 벽 `Geo_M2_BaseWallCorner3_0x`(서), `Geo_M2_BaseWallSide3_01`·`Geo_M2_WallDoorCorner5_01`(동, y 11.62..15.12), `Geo_M2_BaseWallCorner*`(북 y 14.96), 창벽(남 y 8.12..8.28) |
| (d) 로봇 | 씬 로봇은 **M0617**(팀 자산). articulation root 는 이것 하나다. 1 m 큐브 받침 위에 있고, 범위 x −8.29..−8.09, y 12.46..13.12, z 0.96..3.05. AMR 은 `ridgeback_ur5`(1.36, 6.99, 방 남쪽 밖, 자산 안 받음) | `/World/manipulator/m0617/m0617/m0617/root_joint`, `/World/Cube`, `/World/ridgeback_ur5` |

조제실 자리 후보(`hospital_scene_check.py` 로 겹침 계산):

| 후보 | `--pharmacy-origin` | 끌 것 | 겹침 | 특징 |
| --- | --- | --- | --- | --- |
| **A 동쪽 끝(추천, 판단)** | `0.25 10.5285421018 0 0` | 의약품 캐비닛 2(`Environment/hospital/SM_MedicalCabinet_01a*`), 약병 24(`…/SM_PillBottleSet_*`), 동쪽 벽 2(`…/Geo_M2_BaseWallSide3_01`, `…/Geo_M2_WallDoorCorner5_01`) | 0 | 선반 뒤가 북쪽 벽 앞(y 11.87), 우리 복도 벽이 x 2.95. 벨트가 병원 동쪽 벽 자리를 지나 홀(복도)로 나간다(시나리오 1절과 같음). 세준 배치는 그대로 둘 수 있다. overview 카메라는 (0.25, 8.00, 2.17)로 방 안 |
| B 세준 배치 자리 | `-7.2 10.5285421018 0 0` | 세준 M0617(`manipulator`)·받침(`Cube`)·조제기(`machine`)·테이블(`Cube_02`)·벨트(`Conveyor`) | 5(위 다섯) | 세준 배치를 우리 것으로 바꾼다. 벨트가 방 안에서 끝난다(복도 없음) |

### 재범 결정(9/18, #215 코멘트)과 `--preset hospital-v2`

| 결정 | 내용 |
| --- | --- |
| 로봇 기종 | **M0609 기준**으로 모든 것을 설계한다. 씬 M0617(`manipulator`)은 끈다 — 9/19 `b9ba0d6`(#233)에서 씬에서 빠져 씬 쪽에서 충족됐고, 끄기 목록에서도 뺐다 |
| 조제실 원점 | **후보 A** `0.25 10.5285421018 0 0`. 캐비닛 2·약병 24·동쪽 벽 2 를 끈다 |
| 벨트 | **우리 벨트**를 쓴다. 씬 벨트 강체 22개는 끄고(모양·정적 충돌은 남음), 씬 벨트 그래프 22개(ConveyorBeltGraph 20·Sorter ActionGraph 2)는 끈다 |
| /clock | 우리 스테이지 하나 |

`--preset hospital-v2` 가 이 결정을 한 번에 켠다: `demo-ros-refill-v2` + `--pharmacy-origin 0.25 10.5285421018 0 0` + `--base-deactivate`(9/18 50, 지금 코드 47)·`--base-rigid-off`(9/18 22, 지금 코드 19) 목록. 준비된 씬 경로 `--base-usd` 는 현장 값이라 따로 준다(없으면 기동 전에 거절). 목록은 점검 도구가 경로를 채운 씬에서 낸 prim 경로로 고정했다(`p3sim/base_scene.py` `HOSPITAL_DEACTIVATE`·`HOSPITAL_RIGID_OFF`, 씬 기본 prim `/World` 기준).

| 묶음 | 수 | 경로 |
| --- | --- | --- |
| 끔: M0617 | 0 | 씬에서 제거됨(`b9ba0d6`). 목록에서 뺐다 |
| 끔: 의약품 캐비닛 | 2 | `Environment/hospital/SM_MedicalCabinet_01a2`, `…/SM_MedicalCabinet_01a_40` |
| 끔: 약병 | 24 | `Environment/hospital/SM_PillBottleSet_01a*`·`…_01e*` 24개(코드 목록) |
| 끔: 동쪽 벽(우리 벨트 자리) | 2 | `Environment/hospital/Geo_M2_BaseWallSide3_01`, `…/Geo_M2_WallDoorCorner5_01` |
| 끔: 씬 벨트 그래프 | 22 | `Conveyor/<트랙>/ConveyorBeltGraph`·`ConveyorBeltGraph_01`(20), `Conveyor/ConveyorTrack_02·03/Sorter/ActionGraph`(2) |
| 강체 끔: 씬 벨트 몸체 | 22 | `Conveyor/<트랙>/Belt`·`Belt_01`·`BeltRamp`·`Rollers`·`Rollers_01`·`Sorter/Sorter_physics` |

오프라인 확인(usd-core, 경로를 채운 씬, `hospital_scene_check.py --hospital-v2`, Isaac 미실행):
- 끈 51·강체 끈 22 모두 찾음(없는 경로 0). 남은 articulation root 0, 켜진 OmniGraph 0, 켜진 씬 벨트 강체 0.
- 우리 v2 상자·로봇 범위·**우리 벨트**와 씬 prim 겹침 0.
- 세 시점(overview·shelves·bins)의 눈이 세준 조제실 방 안(x −10.68..3.03, y 8.28..14.96, 천장 z 3.0 아래)에 있다. 눈에서 약통 16·수납 목표·캐리지 끝·윗단 위 그리퍼까지의 시선을 막는 씬 prim(벽·천장 포함, 축 정렬 상자 기준)은 0.
- 우리 벨트는 씬 좌표 (1.6, 14.3, 0.75) 에서 (3.2, 14.3, 0.75) 로 끈 동쪽 벽 자리(x 3.00..3.16)를 지나 홀로 나간다. 끝과 적재 자리(중심 (3.55, 14.3), 윗면 z 0.01) 아래 바닥은 z 0.0(`Geo_Floor_Costum14_5`)으로 평평하다.
- 재고 JSON·팔 계획 좌표는 병원 유무와 같다(테스트: `room()`·레일 정보·`pharmacy_layout_json.py` 출력이 `demo-ros-refill-v2` 와 같음).

```bash
python3 sim/standalone/prepare_hospital_scene.py --custom-assets <custom-assets> --isaac-assets-root <Assets/Isaac/5.1> --output /tmp/p3-hospital.usda
python3 sim/standalone/hospital_scene_check.py /tmp/p3-hospital.usda --hospital-v2   # usd-core 있으면: 겹침·시선 0 확인
"${P3_ISAAC_ENV[@]}" ~/isaacsim/python.sh sim/standalone/pharmacy_stage.py --preset hospital-v2 --base-usd /tmp/p3-hospital.usda \
  --order-pool "$P3_REPO/src/rokey_p3_orchestrator/config/order_pool.yaml" "${P3_ASSETS[@]}" 2>&1 | tee -i /tmp/p3-hospital-stage.log
grep -m1 "base_scene usd=" /tmp/p3-hospital-stage.log   # "missing": [], "rigid_off": 22, deactivated 50개, "articulations": 스테이지가 구동하지 않는 씬 articulation
```
병원 배치만 비교하는 첫 L3에서는 팔 명령에 `-p v2_guarded_module_path:=false`를 명시한다.
#230 이후 지원 환경의 팔 노드는 guarded가 기본 true이므로, 기존 실습7·8과 같은 팔 경로를 비교하려면 이 설정이 필요하다.
`tools/demo_v2.sh`는 이미 false를 명시한다. 새 guarded 경로 검증은 별도로 구분해 기록한다.

## 단계 요약

> **상태: 지난 기록 (2026-09-18 기준).** 지금은 [현행 절](#지금-무엇이-현행인가-v110-병원-한-바퀴)을 따른다.

"Isaac 실행 확인" 은 마스터에서 언제 어떤 커밋으로 돌려 무엇을 봤는지다. 출처는 전달받은 마스터 관측 보고와 [실습 기록](../docs/practice/README.md)이다. 이 문서 작성자가 직접 본 것은 없다.

| 단계 | 스크립트 | 모드 | 무엇을 보여주나 | Isaac 실행 확인 |
| --- | --- | --- | --- | --- |
| 0 | `minimal_clock.py` | 창·headless | 빈 월드 + `/clock` 하나 | 9/17 master02, 창 모드·도메인 117: 714 s, `loop_hz=59.42 rtf=0.990`, `/clock` 발행자 1 RELIABLE 59.999 Hz, exit 0. headless(#94)·Stop/Play 단조성은 미실행 |
| 0.5 | `m0609_refill_stage.py` | `selfdemo` | 고정 받침 M0609 가 선반 캐니스터를 조제기 슬롯 A·B 에 넣기 반복, `teach` 줄 | 9/17 master02: `--attach` 넣기 성공(`5d6a10b`), 슬롯 A·B 와 `teach` 값 추출(`38b08eb`). 물리 파지는 미확인 |
| 0.5 | `m0609_refill_stage.py` | `ros` | 계약 `/m0609/*` 로 `m0609_arm` 이 이 씬을 움직임 | 9/17 master02: `--attach` 에서 `/m0609/refill` SUCCEEDED(feedback 6단계, 29 s), `joint_states` 22.9 Hz(목표 30, `38b08eb` 에서 주기 수정, 수정 후 미측정) |
| 0.7 v1 | `pharmacy_stage.py --preset selfdemo-refill` | `selfdemo` | 약품 선반 랙, 2축 레일 위 M0609 보충 반복, 조제기(투입구·출구), 컨베이어, 벽 | 9/17 `f796210` 보충 3/3. 9/18 실습3-A(4바퀴, 한 바퀴 64 s → 28 s, 재범 "속도·레일 모양 괜찮다", exit 0). `--physics-grasp` 는 미확인 |
| 0.7 v1 | `pharmacy_stage.py --preset demo-ros` | `ros` | JSON 어댑터 토픽 6개 + `/m0609/*` + 레일 토픽(계약 밖), 스테이지가 보충을 스스로 돎 | 9/17 `ed91f0b`·`9d0a441`: 어댑터와 `HOLD_RETURN`, pick_notice 로 봉투 치움, 리셋 30회 ABORT 0(자세한 값은 [0.7단계](#07단계-조제실-스테이지)). 9/18 실습1: 37분, 보충 28/28, 트립 완주, 벨트 xform `ratio=1.000`, 타임라인 STOP 5회(재범이 누름) 5/5 복구 |
| 0.7 v1 | `pharmacy_stage.py --preset demo-ros-refill` | `ros` | 오케스트레이터 `/m0609/refill` → 팔 노드가 레일+M0609 를 토픽으로 구동 | 9/18 실습3-B 보충 2/2(79분, exit 0), 실습4 3/3(68분, 조제기 touch 0), 실습5 2/2(60분). 셋 모두 `app_stopped` 0 |
| 0.7 v2 | `pharmacy_stage.py --preset demo-ros-refill-v2` | `ros` | 3축 레일(승강 기둥), 선반 4개, 원통·모듈 약통 16개, 원형 수납통·모듈 구멍, 재고 토픽, 시연 카메라 | 9/18 실습6(스테이지 단독, 재고·3축 레일 토픽), 실습7-a-a5(팔 v2, 7-a4 부터 16칸 계획 16/16·`rail_overlap` 0·"레일이 밀려" 0), 7-b 5분 연속 `refill_soak` 7/7, 실습8 오케스트레이터 + 웹 보충 3/3([실습8](../docs/practice/practice-08.md)) |
| 0.7 | `pharmacy_stage.py --ur5` | `selfdemo` | 벨트 끝 받침대 UR5 가 봉투를 흡착해 상판 칸 5개에 차례로 놓기 | 9/17 `7ae2879`: 준비·손 카메라(2.855 Hz)·TF 는 떴지만 집기 `ik_failed` 62줄. 수정(`f796210`, 640×480)은 **미실행**. 시연에 쓰지 않는다 |

### preset 과 기본값

preset 은 **인자 기본값만** 바꾸고, 명령줄에 적은 인자가 이긴다. 첫 로그 줄 `[pharmacy_stage] preset=<이름|-> resolved_args={…}` 로 어떤 값으로 떴는지 본다. 자세한 설명은 [시연 때 띄우는 명령](#시연-때-띄우는-명령---preset).

| preset | 장면 | 모드·보충 | 레일 드라이브(stiffness, damping, max_force) | 그 밖에 바뀌는 기본 |
| --- | --- | --- | --- | --- |
| `demo-ros` | v1 | ros, 스테이지 보충 반복(`--ros-refill-selfdemo`, 무한), pick_notice 없으면 5 sim s 뒤 봉투 치움 | 1e5, 1e4, 5e4(9/17 `f796210` 검증값) | — |
| `demo-ros-refill` | v1 | ros, 팔 노드가 구동(스테이지 보충 끔), 봉투 치움 5 s | 1e5, 1e4, 5e4 | — |
| `demo-ros-refill-v2` | v2 | ros, 팔 노드가 구동, 봉투 치움 5 s | 1e7, 1e5, 1e8(우리 선택값, 실습7-a2 부터 레일 밀림 0) | `--view overview`, v2 파생 기본 `--rail-x-stroke 2.8`·`--carriage-height 0.25`·`--rail-z-limits 0 1.10` |
| `selfdemo-refill` | v1 | selfdemo, 배출·보충 무한 | 1e5, 1e4, 5e4 | — |
| (없음) | v1 | selfdemo, 배출 무한(`--loop 0`), 로봇 인자가 있으면 보충도 무한 | 1e7, 1e5, 1e8(`2b846f2` 기본, v1 비교 G-1 미실행) | — |
| `emptyworld-loop` | v2 + 복도·병상·도크 | ros, 전 구간 한 바퀴(9/21 빈월드), 받침대 UR5 | 1e7, 1e5, 1e8 | `--ur5`, UR5 받침·대기 자세. `demo_v2.sh` `P3_WORLD=emptyworld` 가 쓴다 |
| `hospital-v2` | v2 + `hospital_layout.usda` | ros, 팔 노드가 구동 | 1e7, 1e5, 1e8 | 원점 A, 끄기 목록(지금 코드 47·19). 지난 기록 |
| `hospital-nav` | 병원 씬만(`--no-room`) | ros, AMR 합본 주행 | 1e7, 1e5, 1e8(기본값) | 9/23 병원 주행 v0 |
| `hospital-full` | 병원 씬 + v2 조제실 평행이동 | ros, 전 구간 | 1e5, 1e4, 5e4 | 9/23 #527. `demo_v2.sh` 는 쓰지 않는다 |
| `hospital` | 병원 씬 + 워크셀 JSON(`--workcell-layout`) | ros, 전 구간 | 1e5, 1e4, 5e4 | **현행**. 위 [현행 절](#지금-무엇이-현행인가-v110-병원-한-바퀴) |

모든 preset 공통 기본: 벨트 몸체 `--belt-body xform`, 접촉 기록 켬(`--no-contact-log` 로 끔, 같은 쌍은 `--contact-log-every-s`(기본 2.0 sim s)마다 한 줄 — 진단 때만 0.05–0.1 로 줄인다. 부하 관측 1회(실습13c, 창 모드·녹화 동시, `0.05`): 접촉 줄 약 1,100 줄/s, 로그 합계 분당 약 33 MB, Isaac RSS 분당 약 27 MB(기동 구간 제외), **rtf 0.902·loop_hz 54.12**. 같은 창 모드·녹화라도 인자 없이 돈 13b 는 평평했고(0.9 MB/분, 7분 표본) rtf 0.991·loop_hz 59.44 였다 — 물리 루프가 약 9% 느려진다. 찍는 줄은 **두 번 남는다**: Kit 이 파이썬 stdout 을 제 로그에도 받아 적는다(13c 에서 `stage.log` 와 Kit 로그의 `contact ` 줄이 1,118,184 로 같고, Kit 쪽에 `[py stdout]` 접두사가 붙는다). 로그량의 절반 이상이 이 중복이다. 메모리를 무엇이 들고 있는지는 아직 안 갈렸다 — 접촉 기록 쪽 파이썬 코드에는 쌓이는 것이 없다(쌍 수만큼의 dict 둘). 진단 회차는 `0.1` 과 20분 안쪽으로 잡는다), `rail_overlap` 기록 12 업데이트마다(`--rail-overlap-every`), 놓은 약통 되돌림 `--respawn-delay-s 2.0`, 잡기 거리 `--hold-distance 0.08`, 물리·렌더 1/60 s. 시연 카메라는 v2 계열 preset 이 켠다(`--view none` 으로 끔). 병원 preset 의 뷰포트 기본은 `floor_top` 이다. 발표 반반 화면은 `--window-half left`(#212, 창을 화면 절반으로, master02 내장 패널은 `--screen-size 2048 1152`). 렌더 해상도는 창 비율을 유지한 채 1280×720 상자 안으로 줄인다. 9/23 결정 5 다. master02 창 1024×1152 는 렌더 640×720 이 된다. `P3_RENDER_MAX=WxH` 로 상자를 바꾼다. `P3_RENDER_MAX=` 처럼 빈 값이면 상한이 없다. 그때 렌더는 창과 같다. 최종 데모 촬영 회차는 빈 값으로 찍는다.

### 실습별 확인 (스테이지 쪽 요지)

실습 기록 원문은 [docs/practice](../docs/practice/README.md). 문제 번호 P1-P22 는 그 기록의 번호다.

| 실습 | 트리·preset | 스테이지 쪽 결과 | 여기서 고친 것 |
| --- | --- | --- | --- |
| 1 | `174bb6a` `demo-ros` | 37분, 보충 28/28, 벨트 ratio 1.000, STOP 5/5 복구. 재범 문제 P1 흔들림·P2 기둥에 밀림·P3 느림·P4 1축으로 보임, 로그 P5 Ctrl-C exit 1 | 실습1 대응(아래 절): 잡은 약통을 물리 스텝 뒤 따라가기, 접촉 기록, 80% 속도·사다리꼴, 2축 색 구분, rclpy SIGINT 처리기 끔 |
| 2 | — | 준비만(실습3 에 흡수) | — |
| 3 | `7cd4b90` `selfdemo-refill`(A)·`demo-ros-refill`(B) | P3·P4·P5 해소. B 보충 2/2. 새 문제 P6 로봇 가운데 안 그려짐, P7 조제기 앞면 충돌, P8 `above_inlet` 미달 | #162(link_2 visuals, 투입구 0.07 m 띄움) |
| 4 | `0f5b090` `demo-ros-refill` | 보충 3/3, 조제기 touch 0 → P7·P8 로그상 해소. P6 경고 2줄 남음 | #167(visuals 해제를 첫 앱 업데이트 전으로) |
| 5 | `main` `7453b3d` 같은 구성 | 60분, 보충 2/2, P6 경고 남음(#167 이전 트리) | — |
| 6 | `main` `6f59377` v2 단독 | 재고·3축 레일 토픽 동작, **P6 해소**(경고 0, 재범 "이어져 보임"). 새 문제 P10 무지개 줄, P11 너클 경고, P13 선반이 하나로 보임(P9 회색은 캡처 탓) | #175(받침·승강판 겹친 면, 모든 visuals 해제, 선반 색·테두리) |
| 7-a | `affd1ee` + 팔 v2 | goal 8/8. 재범 P14 레일 z·P15 관통·P16 순서, 로그 P17 레일 밀림 | #180(v2 레일 드라이브·행정, `rail.parts`, `rail_overlap`, 받침 0.25·`rail_z` 0..1.10) |
| 7-a2 | `main` `1828bfe` | goal 4/4, "레일이 밀려" 0(P17 해소). 새 P18 공중부양 | #183(승강 기둥) |
| 7-a3 | `main` `525a9e8` | goal 6/6, 기둥 생김, `rail_overlap` 누적 129(팔이 아직 레일 부품을 안 피함) | #188(바닥 선반 받침 0.55, 팔 #186·#190 과 짝) |
| 7-a4 | `801ee52` | 16칸 계획 16/16, goal 4/4, **`rail_overlap` 0**, 팔 동작 중 레일 명령 0. 캡처에서 기본 카메라가 벽 뒤 | #195(시연 카메라 `--view`) |
| 7-a5 | `a39546f` | overview·shelves·bins 세 뷰 goal 4/4, `rail_overlap` 0. P19 모듈 넣기 때 로봇이 화면 밖, P20 회색 막대, 원통이 놓기 1.3 s 전 수납통 벽에 닿음 | #197(overview 에 로봇 외곽), #198(수납통 안지름 0.12), P20 은 자산 케이블(조치 없음) |
| 7-b | — | 5분 연속 `refill_soak` 7/7(원통 3·모듈 4, 평균 46.37 s), `rail_overlap` 0 | — |
| 8 | `a94f06e` = main + #197·#198 | v2 + 오케스트레이터 + 웹: 보충 3/3(1건은 리셋으로 취소), `target=none` 0, `rail_overlap` 0. 문제 P21 웹 UI·P22 캡처에 firefox 가 덮임(스테이지 몫 아님) | — |

## 알려진 문제·미확인

> **상태: 지난 기록 (2026-09-18 기준).** 지금은 [현행 절](#지금-무엇이-현행인가-v110-병원-한-바퀴)을 따른다.

9/18 저녁(main `c69eda9`) 기준이다. 근거는 실습 기록과 master02 보고이고, 판단은 따로 표시한다.

### 해소된 것

| 문제 | 해소 근거(실물) | PR·커밋 |
| --- | --- | --- |
| 벨트 속도가 1.6배(비균일 scale 강체에 surface velocity) | 9/17 20:43 `--belt-body xform` 5/5 `speed_measured=0.1500 ratio=1.000`. 기본값이 된 뒤 실습1(`demo-ros`)에서도 `ratio 1.000` | `021a80b`(판별), `b0d21e3`(xform 기본) |
| P6 로봇 가운데(link_2)가 안 그려짐 | 실습6 `non-existent path` 경고 0줄, 재범 "이어져 보임" | #162·#167·#175 |
| P5 Ctrl-C 가 exit 1 | 실습3(A·B)·4·5 모두 `exit=0` | rclpy SIGINT 처리기 끔(실습1 대응) |
| P3 느림, P4 1축으로 보임 | 실습3 재범 "속도는 괜찮고", "레일 모양도 괜찮음"(한 바퀴 64 s → 28 s) | 실습1 대응 |
| P7 조제기 앞면 충돌, P8 `above_inlet` 미달 | 실습4 `DispenserBody` touch 0(near 만), 보충 3/3 TIMEOUT 0 | #162·#165 |
| P17 모듈 넣기 때 레일이 밀림 | 실습7-a2 부터 "레일이 밀려" 0(7-a3·7-a4·7-a5·7-b 도 0) | #180 |
| 바닥 선반 아랫단 4칸을 못 집음 | 실습7-a4 16칸 계획 16/16, goal 에 바닥 아랫단 `floor_right/r0c1` 포함 | #188(팔 #186·#190) |
| 기본 카메라가 벽 뒤라 캡처에 로봇이 안 보임 | 실습7-a5 인자 없이 `viewport view=overview …`, 세 뷰 모두 기동·goal 성공 | #195 |
| P20 승강판 옆 비스듬한 회색 막대 | 원인 확인(자산 읽기, 조치 없음): 수업 자산 `base_link` 메시 `MF0609_0_0` 의 일부. 모양으로 케이블로 본다(판단). 아래 [시연용 카메라](#시연용-카메라---view) 절 | — |
| 타임라인 STOP 뒤 물리 핸들이 사라져 죽음(9/17 `4c07d8f`) | STOP 복구가 9/17 20:49 처음 동작, 실습1 5/5(재범이 정지 버튼), 실습3-B 2/2(누른 사람 미확인) `physics_view recovered` | STOP 복구(0.7단계) |

### 로그로는 해소, 재범 화면 확인 대기

실습 기록 규칙대로 재범이 화면(녹화 포함)으로 확인해야 해소로 옮긴다.

| 문제 | 로그 근거 | PR |
| --- | --- | --- |
| P15 로봇이 제 레일을 관통 | 레일 캐리지 부품은 충돌 없는 시각 부품이라 물리로는 막지 않는다(코드). 겹침 기록 `rail_overlap` 이 7-a3 129줄 → 7-a4·7-a5·7-b·실습8 **0**(팔이 `rail.parts` 를 피함) | #180(기록·`rail.parts`), 팔 #186 |
| P18 로봇이 공중에 떠 보임 | 승강 기둥이 7-a3 부터 있다. 기둥 윗면 = 승강판 아랫면이 `rail_z` 0·0.55·1.10 에서 틈 0(테스트) | #183 |
| P14 레일 z 가 따로 놂, P16 레일·팔 동작 순서 | 팔 몫. 7-a4 부터 팔 동작 중 레일 명령 0, 레일 이동을 z 와 x·y 단계로 나눔 | 팔 #186 |
| P10 무지개 줄 | #175 는 받침·승강판이 겹친 윗면(z 0.60) 한 곳만 설명한다. 나머지 면의 줄이 v1 에도 있는지 재범 확인 대기(렌더·표시 쪽일 수 있다는 판단) | #175 |
| P13 선반 넷이 하나로 보임 | 선반마다 색과 앞면 테두리 | #175 |
| P19 overview 에서 모듈 넣기 때 로봇이 화면 밖 | 테스트가 팔 레일 자세마다 로봇 외곽을 본다. 실습8 트리(#197 포함)에서 떴다는 보고만 있고, 모듈 넣기 장면 확인은 없다 | #197 |
| 원통이 놓기 1.3 s 전부터 수납통 벽에 닿음(7-a5) | 안지름 0.10 → 0.12. 실습8(#198 포함 트리) `target=none` 0 | #198 |

### 열린 문제

- **창 모드 `app_stopped`(원인 미확인, 외부 검토 A1).** 9/17 창 모드 실행 몇 개가 wall 9.7-788 s 에 STOP 없이 `kit_running=False` 로 끝났다(자세한 기록은 아래 [9/17 상세](#917-상세-기록)). 9/18 실습에서는 긴 창 모드 실행(실습1 37분, 3-B 79분, 4 68분, 5 60분)에서 `app_stopped` 0 이었다. #187 의 `a1_probe`(종료 원인 계측)는 아직 `app_stopped` 를 만나지 못했다. 9/21 시연은 창 모드로 간다.
- **로봇↔레일 물리 충돌은 꺼져 있다.** `rail_overlap` 기록과 팔 계획의 회피로만 막는다. 켜면 articulation self-collision 이 같이 켜져 로봇 링크끼리도 부딪친다(판단). 팔과 맞춘 뒤에 정한다.
- **P11 그리퍼 너클 `non-existent` 경고.** #175 에서 로봇 아래 모든 instanceable `visuals` 를 첫 앱 업데이트 전에 푼다. 그 뒤 경고 줄 수 집계 보고는 없다.
- **P1 약통 흔들림.** 실습1 대응(물리 스텝 뒤 따라가기) 뒤 재범·master02 보고에 다시 나오지 않았다. 확인한 것은 아니다.
- **물리 파지 미확인.** 데모는 닫을 때 붙이는 방식(`--attach`, v2 는 `--hold-distance`)이다. 그리퍼 드라이브 기본값 (1e4, 1e2, 10)은 근거 없는 선택값이다.
- **`--ur5`(벨트 끝 UR5) 미완.** 9/17 집기 실패. 수정은 미실행이고 시연에 쓰지 않는다.
- **headless(#94)와 livestream 접속은 실행하지 않았다.**
- **0.5단계 `m0609_refill_stage.py` 에는 종료 뒤 OmniGraph traceback 이 날 콜백 패턴이 남아 있다**(0.7단계만 고침).
- **장면 v2 치수는 전부 임시값**이다. 세준 병원 씬으로 옮길 때 바뀐다.

### 외부 검토 정정 (#185)

- `~/isaacsim/VERSION` 의 `5.1.0-rc.19` 는 공식 v5.1.0 태그의 값이다. "RC 라서 불안정하다" 는 추정은 철회한다.
- "headless 는 330 s 까지 무사" 는 증거가 아니다. 우리 `keep_running()` 은 headless 에서 `app_running=False` 를 무시하고 계속 돈다. 이제 `a1_probe` 가 headless 에서도 raw Kit 상태를 찍는다.
- 화면 유휴·잠금 가설은 "상당히 약화" 다(9/17 19:38 잠금을 막은 채로도 287.7 s 에 끝남). 다른 표시 사건까지 배제한 것은 아니다.
- 벨트 scale 전제(A4): 비균일 scale 강체 대신 xform 몸체를 쓴다(위 해소). `belt_surface <시점> {json}`(#187)은 surface velocity 속성과 합성 월드 축을 읽기만 한다. PhysX 내부 유효 속도는 읽지 않는다.

### 9/17 미실행 항목의 그 뒤

9/17 저녁 `fix/sim-pharmacy-stage-followup` 기준 "Isaac 에서 돌지 않은 커밋" 표를 9/18 실습 결과로 갱신했다.

| 커밋 | 무엇 | 그 뒤 |
| --- | --- | --- |
| `b0d21e3` | 벨트 기본 몸체 `xform` | 실습1 `ratio 1.000` → **확인** |
| `a086c4d` | timeline STOP 때 `timeline_stop_context …`, `--kit-log-verbose` | STOP 은 실습1·3-B 에 있었고 `--kit-log-verbose` 는 실습마다 썼다. `timeline_stop_context` 줄 내용 보고는 없다 |
| `021a80b` 일부 | `kit_shutdown_event POST_QUIT …`, `kit_log settings=…`, `physx_query belt_after_reset …` | 뒤 둘은 9/17 확인. `kit_shutdown_event` 는 아직 `app_stopped` 를 못 만남 |
| `1b9cfc4` | 종료 뒤 OmniGraph traceback 제거 | 실습3·4·5 `exit=0`, 실습5 `STOP … (closing)` 줄 → **확인**(traceback 유무를 따로 센 보고는 없다) |
| `2b846f2` | 레일 드라이브 (1e7 1e5 1e8), `applied_rail_target`·`arm` 줄 | v2 preset 이 이 값을 쓰고 7-a2 부터 레일 밀림 0. v1 preset 은 옛 값 그대로이고 G-1·G-2 비교는 돌지 않았다 |
| `f796210` | `--ur5` 받침대 월드 고정 관절, 640×480 손 카메라 | 미실행(G-3 대기, 시연 제외) |
| `feat/sim-pharmacy-ros-refill` | `--preset demo-ros-refill`(팔 노드가 토픽으로 구동) | 실습3-B·4·5 보충 2/2·3/3·2/2 → **확인** |

### 9/17 상세 기록

아래는 9/17 관측 원문 정리다. 상태는 위 표가 최신이다.

**원인 미확인(관측만 있음):**
- 창 모드 `app_stopped`(STOP 없이 `kit_running=False`): 15:22 빈 월드 `minimal_clock` 9.7 s, 18:37:49 wall 317, 18:56:36 wall 788, 19:43 wall 287.7(화면 잠금 막은 채). 우리 동작과 무관한 창 모드 Kit 쪽으로 본다(판단). master02 과거 로그 추출 대기.
- Kit 내부 timeline STOP: 16:50 `4c07d8f`(추정), 17:4x `3b114c4 --ur5`(STOP 뒤 앱 종료), 20:49:19 `021a80b`(복구됨). 전부 창 모드·레일 보충 중. 직전 봉투 텔레포트가 3건 중 2건(약한 단서).
- headless selfdemo 8/8 이 `scaled-cube` 에서도 벨트 1.0 이었던 이유(창 모드 selfdemo 판별 대기).
- 보충 `retreat` TIMEOUT(창 모드 cycle 2·5): 레일 드라이브 약함 대 IK 자세 분기 — G-1·G-2 대기.
- 첫 `rail_to_shelf` 가 베이스 y 0.48 에서 서는 충돌 접점(홈 자세 팔꿈치가 선반 앞이라는 판단).
- `--ur5` 집기·손 카메라 hz·QR 판독·`--physics-grasp`.

- **물리 파지 미확인.** 9/17 물리 파지(`5d6a10b`)는 약통이 들리지 않았다. 수정(`dcfe1cd`: 그리퍼 드라이브·마찰·닫힘 목표 유도·`grasp_verified`)은 Isaac 에서 돌지 않았다. 그리퍼 드라이브 기본값 (1e4, 1e2, 10)은 **근거 없는 선택값**이다. 데모는 `--attach`(닫을 때 고정)로 한다.
- **`app_stopped` 2회, 원인 미확인.** 루프가 SIGINT·`--duration` 없이 끝난 실행이 두 번 있었다(9/17 15:22 `minimal_clock.py` 창 모드 9.7 s, 15:51 5.9 s — 두 번째는 스크립트·커밋 미확인). 같은 기계에 다른 사람의 Isaac 이 떠 있던 것과 관련이 있을 수 있다(판단, 미확인). 이제 그 사유로 끝나면 `app_state kit_running=… exiting=… stage_missing=…` 을 찍는다.
- **ros 모드 첫 실행 종료와 재실행.** 9/17 첫 `--mode ros` 는 기동 직후 물리 핸들이 사라져 끝났다(타임라인 STOP 이 원인으로 보이나 누가 멈췄는지 미확인). `7049c1a` 뒤 재실행에서는 STOP 이벤트가 없었고(`timeline_event` 는 PLAY 만) 정상 동작했다. 같은 조건이 다시 오면 `timeline_event type=STOP` 줄로 본다.
- **운영 규칙: 같은 기계에 다른 사람의 Isaac 이 떠 있으면 띄우지 않는다.** GPU·도메인·스트리밍 포트를 나눠 쓰고, 위 두 문제와의 관련을 가를 수 없어서다. `pgrep -af isaacsim` 으로 먼저 본다(보기만, 끄지 않는다).
- 0.7단계 기본 배치의 도달 범위, 레일 드라이브 값(우리 선택값), 컨베이어가 봉투를 옮기는지, 레일 재배선이 하나의 articulation 으로 잡히는지는 전부 미확인이다(0.7단계 가정 표).
- **시뮬 도중 prim 생성·삭제 금지.** 9/17 0.7단계 첫 실행에서 봉투 prim 을 지우자 "prim … was deleted while being used by a shape in a tensor view class" 로 physics tensor view 가 무효화되고 다음 관절 읽기가 실패했다(exit 1). 조제실 스테이지는 봉투를 기동 때 풀(`--pouch-pool`)로 만들어 텔레포트로만 옮기고, 보충 데모의 attach 도 관절 prim 대신 매 스텝 텔레포트로 따라가게 바꿨다(`2961136`). 9/18 실습에서 이 방식으로 배출·치움·보충이 돌았다. 0.5단계 `--attach` 는 실행 중 FixedJoint prim 을 만들고 지우는데 9/17 에 문제가 없었다.
- **0.7단계 보충(9/17 `f796210` 확인, 물러나기 TIMEOUT 남음).** 이전 실행들의 투입구 미달·약통 낙하는 `f796210` 에서 재현되지 않았다(headless 3/3, 창 모드 6/6 `canister_in_inlet=True`). 남은 것: 넣은 뒤 `retreat` TIMEOUT 이 창 모드 cycle 2(투입구 B, error 0.175)·cycle 5(투입구 A, error 0.188)에 났다(headless cycle 2 도 숫자까지 같음). 그때 팔 단계 중 `rail_y` 가 목표 -0.05 에서 하한 -0.10 으로, `retreat` 에서 `rail_x` 가 0.09-0.17 m 밀렸다. `refill ik_failed phase=settle target=[x,0.55,1.10]` 은 별도 단계가 아니라 `retreat` 의 시한 연장 구간이다(라벨이 전달되지 않음). 원인 후보(판단, 미확인): 레일 드라이브가 팔 드라이브보다 약함, 바퀴 끝에 팔을 홈으로 돌리지 않아 IK 시드가 바퀴마다 달라 자세 분기. `2b846f2` 의 강한 레일 드라이브와 `applied_rail_target=`·`arm=` 줄로 가린다(미실행). 첫 `rail_to_shelf` 가 베이스 월드 y 0.48 에서 서던 것: `arm ready home=` 의 joint_3·joint_5 가 1.59·1.58 rad(팔꿈치 90° 접힘)라 홈 자세 팔이 선반 앞(y 0.75, 축에서 0.27 m)에 닿는 것으로 본다(판단, 충돌 접점은 미확인).
- **0.7단계 긴 실행 사망(9/17 4c07d8f, sim 453-456 s, exit 1).** 보충 4바퀴째 약통 넣기 실패, 5바퀴째 약통이 넘어진 채 안 들림, 그 뒤 스폰 직후 봉투가 주차 자리로 읽히고 "Physics Simulation View is not created yet" 로 관절 읽기가 실패했다. 5.1.0 에서 그 경고는 타임라인 STOP 이 물리 핸들을 지웠을 때 나오고, STOP 은 물체를 USD 에 작성된 자세(봉투의 주차 자리)로 돌린다 — 그래서 STOP 이 원인으로 보인다(판단). 그 실행에는 타임라인 로그가 없었다. 이제 `timeline_event type=…` 를 찍고, STOP 이면 `physics_view lost by timeline STOP` → 재생 → 핸들 재초기화 → 벨트·봉투·데모 사이클 초기화(`physics_view recovered`), 실패하면 exit 3. 재스폰한 약통이 넘어지거나 1 cm 넘게 어긋나면 3번까지 다시 놓는다(`refill respawn_retry`). STOP 복구는 9/17 20:49·실습1(5/5)·실습3-B(2/2)에서 동작했다. `respawn_retry` 가 찍혔다는 보고는 없다.
- **0.7단계 `--ur5`(벨트 끝 UR5) 미완 — 집기가 Isaac 에서 실패했다.** 옵션 인자라 기본 경로(`--ur5` 없음, `--preset demo-ros`·`selfdemo-refill`)에는 영향이 없다. 9/17 master02:
  - `7ae2879`: 준비·카메라·TF 는 떴지만 봉투 집기가 `ik_failed` 62줄로 실패했다. 손 카메라는 1280×720 창 모드에서 2.855 Hz 였다(목표 10 Hz).
  - `3b114c4`: `ur5 tcp_source` 에서 `tool0` 정기구학과 끝 prim 이 같은 (0.80, 0.21, 0.27) 이었다(받침대 3.25, 0.55, 0.45). `suction miss distance=2.1791`. sim 69 s 에 외부 원인으로 보이는 `app_stopped`.
  - 대응: UR5 월드 고정 관절을 받침대로 옮기는 수정(`f796210`)과 640×480 기본값(`3b114c4`)은 **미실행**이다. main 에 들어가 있지만 시연에는 쓰지 않는다.
- **창 모드 `app_stopped`(원인 미확인).** 9/17 master02 창 모드 실행이 wall 12-788 s 에 `app_state kit_running=False exiting=False stage_missing=False` 로 끝났다. timeline STOP 없음, 그 구간 다른 Isaac 없음. 19:38 실행은 `gnome-session-inhibit` 로 화면 유휴·잠금을 막은 채(Monitor On, IdleHint no, LockedHint no) wall 287.7 s 에 끝났다 — 화면 유휴 가설은 기각(9/18 외부 검토: "상당히 약화", 다른 표시 사건까지 배제한 것은 아님). "headless 는 330 s 까지 무사" 는 **정정(9/18 외부 검토 A1)**: 우리 `keep_running()` 은 headless 에서 `app_running=False` 를 무시하고 계속 돈다. 그래서 "headless 는 안 꺼졌다" 는 증거가 되지 못한다. 이제 `a1_probe` 가 headless 에서도 raw Kit 상태를 찍는다.
  - **정정(9/18 외부 검토 A1)**: `~/isaacsim/VERSION` 의 `5.1.0-rc.19` 는 공식 v5.1.0 태그의 값이다. "RC 라서 불안정하다" 는 추정은 철회한다.
  - `a1_probe`(외부 검토 "확인 실험 1", `p3sim/diag.py` `A1Probe`, #187 머지, 아직 `app_stopped` 를 만나지 못함): Kit shutdown·timeline(STOP)·app window close 스트림의 push·pop 구독(실행 내내 유지, 없으면 `unavailable`)과, 루프 조건을 평가하기 직전마다 raw 상태(`kit_running`·`wrapper_exiting`·`stage_missing`·`update_number`)가 바뀌면 `a1_probe {json}` 한 줄. 종료 조건은 바꾸지 않는다. 콜백의 Python 스택은 받는 쪽 스택이지 보낸 쪽이 아니다. `--kit-log-verbose` 는 이제 `/log/fileLogLevel` 과 `/log/level` 을 둘 다 verbose 로 둔다.
  - `belt_surface <시점> {json}`(외부 검토 A4 "확인 실험 2", 읽기만): 첫 play 전·reset 뒤·속도 측정 때·`/isaac/sim/reset` 뒤 벨트 강체의 surface velocity 속성과 합성 월드 축(길이·직교·행렬식).
  계측(`#128`. `--kit-log-file` 은 실습마다 썼다. `kit_shutdown_event` 는 아직 `app_stopped` 를 못 만났다):
  - 기동 때 `kit_log settings={'/log/file': …}` 로 Kit 자체 로그 경로를 찍는다. `--kit-log-file <경로>` 로 고정할 수 있다(`--/log/file`, `--/log/fileFlushLevel=verbose` — 뒤의 키는 5.1 에서 미확인). 끝나면 `kit_log tail this file for the reason: <경로>` 가 한 번 더 나온다.
  - `omni.kit.app` 종료 이벤트 스트림의 `POST_QUIT` 을 받으면 `kit_shutdown_event POST_QUIT payload=… python_stack=…` 을 찍는다. 누가 quit 을 요청했는지 보려는 것이다(5.1.0 `isaacsim.code_editor.jupyter` 와 같은 API). 창 닫기 이벤트 API 는 못 찾았다.
  - 끝난 직후 볼 것: `tail -n 50 <Kit 로그>` 에서 GPU device lost/removed, Vulkan swapchain 오류, OOM, quit 요청.
- **Kit 안에서 난 timeline STOP(원인 미확인).** 9/17 20:49:19 master02(`021a80b --preset demo-ros --belt-presurface`, 창 모드): 보충 `descend` 시작 0.7 s 뒤 sim 96.350 에 `timeline_event type=STOP` 이 왔다. Kit 로그(Info)에는 그 앞에 원인 줄이 없고, 다른 프로세스·quit 요청도 없었다. STOP 복구가 처음 실물에서 동작했다(`physics_view recovered updates=2`, 이어서 리셋 정상). 우리 코드에는 `world.stop()`·`timeline.stop()` 호출이 없고, `world.reset()` 은 기동 때 한 번, `world.play()` 는 STOP 복구에서만 부른다.
  계측(`a086c4d`. 실습1·3-B 의 STOP 때 이 줄 내용은 보고되지 않았다): STOP 을 받으면 `timeline_stop_context timeline={current/start/end time, looping, …} python_stack=…` 과 `timeline_stop_context recent_calls=tick…[sim=… refill=<phase>/<mode> belt_occupied=…]: <그 틱에 부른 Isaac 호출>` 을 찍는다(마지막 3틱 + 진행 중 틱). `--kit-log-verbose` 는 `--kit-log-file` 에 Verbose 줄까지 쓴다(파일이 커진다).
- **종료 중 OmniGraph traceback.** 9/17 master02 에서 `--duration`·`app_stopped` 종료 뒤 `OmniGraphError … /P3ClockGraph/ReadSimTime` traceback 이 2개 찍혔다. `simulation_app.close()` 가 타임라인을 멈출 때 `timeline_event` 콜백이 이미 없는 시계 그래프를 읽는 것으로 본다(판단). 0.7단계는 루프가 끝나면 콜백이 그래프를 읽지 않게 했다(`1b9cfc4`, 실습3·4·5 `exit=0`). **0.5단계 `m0609_refill_stage.py` 에 같은 콜백 패턴이 남아 있다**(이번에는 고치지 않음).

## `src/`와의 경계

`src/`는 ROS 패키지, `sim/`은 Isaac 런타임 코드다.
Isaac 모듈은 초기화된 Kit 런타임이 필요하므로 일반 Python·colcon 검사와 실행 경로를 분리한다.
이것은 우리 저장소의 런타임 경계이며 ROS에서 자산을 찾는 방법이 하나뿐이라는 뜻은 아니다.

## 빌드 셸과 실행 셸 분리

[환경 설정](../docs/setup/README.md)과 [DDS 프로파일](../docs/setup/ros2-wired-network.md)을 먼저 확인한다.
Isaac Sim 5.1의 내부 Python 3.11과 Ubuntu 24.04 기본 Jazzy의 Python 3.12를 섞지 않는다.
단순한 USD 파일 로드는 ROS 환경을 source할 필요가 없다.

**외부 ROS 빌드 셸**에서 description 패키지를 빌드하고 설치 경로를 확인한다.

```bash
cd /absolute/path/to/ROKEY_P3_A3
source /opt/ros/jazzy/setup.bash
colcon build --packages-select rokey_p3_description
source install/setup.bash
ros2 pkg prefix --share rokey_p3_description
```

**별도의 깨끗한 Isaac 셸**에서는 위에서 확인한 경로를 명시적으로 전달한다.
예시 경로는 현장 설치 경로로 바꾼다. 네이티브 ROS가 자동 source되는 `~/.bashrc`나 상속된
`PYTHONPATH`·`LD_LIBRARY_PATH`를 그대로 사용하지 않는다. `bash --norc`만으로 상속 환경이 지워지지는 않는다.

```bash
export P3_SCENE_PATH=/absolute/path/to/install/rokey_p3_description/share/rokey_p3_description/stages/my_first_scene.usd
/absolute/path/to/isaacsim/python.sh /absolute/path/to/ROKEY_P3_A3/sim/tests/test_stage_loads.py
```

검사는 `P3_SCENE_PATH`를 우선하고, 없으면 기존 `AMENT_PREFIX_PATH`의 설치본 탐색을 지원한다.
경로를 찾기 위해 native ROS 전체 환경을 Isaac 셸에 source하지 않는다.
입력 씬은 설치 산출물을 기준으로 하고 실제 경로·해시를 실행 기록에 남겨 오래된 설치본과 소스를 혼동하지 않는다.

## 0단계: 빈 월드 + `/clock`

> **상태: 지난 기록 (2026-09-17 기준).** 지금은 [현행 절](#지금-무엇이-현행인가-v110-병원-한-바퀴)을 따른다.

`standalone/minimal_clock.py` 는 ground plane 하나만 있는 월드를 띄우고 ROS 2 브릿지로 `/clock` 만 낸다.
[계약 v1](../docs/architecture/delivery-contract-v1.md) 2.1절(`/clock`: `rosgraph_msgs/Clock`, R, 60 Hz 목표, 작성자 isaac 하나)과
4절(stamp 는 sim time, 리셋 barrier 밖에서 되감지 않음)만 다룬다. 로봇·센서·벨트·조제기·병원 씬·`/sim/reset` 은 없다(1단계 이후, simulation 레인).

상태: 스크립트는 main 에 있다(#83, headless 루프 수정 #94).
9/17 master02 창 모드·도메인 117 에서 처음 돌렸다:
- 첫 실행(15:22)은 9.7 s 뒤 `stop reason=app_stopped` 로 끝났다. 원인 미확인. 이제 그 사유로 끝나면 `app_state kit_running=… exiting=… stage_missing=…` 줄을 찍는다.
- 두 번째(15:28-15:41): `stop reason=sigint updates=42436 wall_s=714.137 loop_hz=59.42 sim_s=707.267 rtf=0.990`, exit 0. `/clock` 발행자 1(노드 `_P3ClockGraph_PublishClock`, RELIABLE), `ros2 topic hz` 59.999.
- headless 경로(#94), Stop/Play 단조성(`--stop-play-after`), 스텁 한 바퀴 연결은 아직 실행하지 않았다.

### 구성

- OmniGraph `/P3ClockGraph`: `OnPlaybackTick` → `IsaacReadSimulationTime` → `ROS2PublishClock`.
  노드 id 와 연결은 NVIDIA `IsaacSim` 저장소 태그 `v5.1.0` 의 `standalone_examples/api/isaacsim.ros2.bridge/clock.py` 와 같다.
- QoS: `qosProfile` 을 비운다. 5.1.0 `OgnROS2PublishClock.cpp` 는 빈 값이면 `rmw_qos_profile_default`(keep last, reliable, volatile)에 `queueSize`(10)를 깊이로 쓴다.
- 되감기: `IsaacReadSimulationTime.inputs:resetOnStop` 을 `False` 로 **명시**한다. 5.1 [ROS 2 Clock 안내](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/ros2_tutorials/tutorial_ros2_clock.html)와
  [노드 문서](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/py/source/extensions/isaacsim.core.nodes/docs/ogn/OgnIsaacReadSimulationTime.html)에 따르면 `False` 는 Stop/Play 에도 단조 증가다.
  기본값이 `False` 지만 C++ 상태 초기값이 `true` 라서 기본값에 기대지 않는다.
- 주기: 앱 업데이트 한 번에 `/clock` 한 번. 루프를 `--rate` 로 wall 기준 조절한다. 업데이트가 느리면 목표보다 낮게 나오고 따라잡으려 몰아 내지 않는다.
  업데이트 한 번에 sim time 은 `render_dt` 만큼 간다. 그래서 기대 실시간 비율은 `render_dt × rate` 이고 시작 로그의 `expected_rtf` 에 찍힌다.
- 종료: `SimulationApp` 은 생성 때 SIGINT 에 `close()` 없이 `sys.exit(0)` 하는 처리기를 건다(5.1.0 `simulation_app.py`). 스크립트가 그 처리기를 플래그로 바꿔 루프를 빠져나와 `simulation_app.close()` 를 부른다.
  앱이 뜨기 전(`SimulationApp` 생성 중)의 Ctrl+C 는 NVIDIA 처리기가 받는다.
- 루프 조건: 창이 있으면 `simulation_app.is_running()` 이 False 가 될 때 멈춘다. `--headless` 면 `is_running()` 이 False 여도 `is_exiting()` 이 False 인 동안 계속 돈다.
  수업 예제 `7_pick_place_color.py`(dev01 에서 읽기만 함) 주석이 "headless 에서 `is_running()` 이 바로 False 를 돌려주는 경우가 있다" 고 적고 `is_running() or args.headless` 로 피한다. NVIDIA 5.1.0 `standalone_examples/api/isaacsim.simulation_app/livestream.py`(headless)도 `kit._app.is_running() and not kit.is_exiting()` 로 돌고 스테이지 검사를 하지 않는다. 5.1.0 `is_running()` 은 스테이지가 없을 때도 False 다. 우리 환경에서 실제로 그런지는 미관측이다.
  headless 로 띄웠는데 곧바로 `stop reason=app_stopped` 가 나오면 이 조건이 아닌 다른 종료 경로다. 그 로그를 보고한다.

인자:

| 인자 | 기본값 | 무엇 |
| --- | --- | --- |
| `--headless` | 꺼짐 | 창 없이 |
| `--rate` | `60` | 초당 앱 업데이트 목표(wall). `/clock` 발행 수와 같다 |
| `--duration` | `0` | wall 초. 0 이면 SIGINT 까지 |
| `--physics-dt` | Isaac 기본 | 물리 스텝(sim 초). 실제 값은 시작 로그 |
| `--render-dt` | Isaac 기본 | 업데이트당 sim 초. 실제 값은 시작 로그 |
| `--stop-play-after` | `0` | wall 초 뒤 timeline Stop → Play 한 번. 되감기 관측용. 0 이면 안 함 |

로그 세 종류(각 한 줄):

```text
[minimal_clock] start isaac=... RMW_IMPLEMENTATION=... ROS_DOMAIN_ID=... ROS_DISTRO=... FASTRTPS_DEFAULT_PROFILES_FILE=... ld_internal_jazzy=... ld_opt_ros=... physics_dt=... render_dt=... rate_hz=... expected_rtf=... topic=/clock qos=reliable/volatile/keep_last depth=10 reset_on_stop=False
[minimal_clock] stop_play sim_time_before=... sim_time_after=...
[minimal_clock] stop reason=sigint|duration|app_stopped updates=... wall_s=... loop_hz=... sim_s=... rtf=... sim_time=...
```

`FASTRTPS_DEFAULT_PROFILES_FILE` 은 Isaac 프로세스에 넘어온 값일 뿐 내부 Fast DDS 가 그 파일을 읽었다는 뜻이 아니다(3b 에서 확인).
`ld_internal_jazzy`·`ld_opt_ros` 는 `LD_LIBRARY_PATH` 에 Isaac 내부 Jazzy 라이브러리 경로와 `/opt/ros/` 가 있는지다. 어느 라이브러리가 실제로 로드됐는지는 아니다.
`loop_hz` 는 wall 초당 업데이트(= `/clock` 발행) 수로 계약의 60 Hz 목표와 비교한다. `rtf` 는 같은 구간의 sim 초 / wall 초다.
`ROS_DISTRO` 는 브릿지 확장이 켜진 뒤 읽는다. 비어 있으면 확장이 Ubuntu 버전으로 정해 넣는다(5.1.0 `extension.py`).

### 내부 Jazzy 라이브러리 방식과 시스템 ROS

근거(확인일 2026-09-17):
- 5.1 [ROS 설치 안내](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/install_ros.html): Isaac 을 띄우는 터미널에서는 **Isaac 내부 라이브러리만** source 하거나
  **Python 3.11 로 빌드한** ROS 2 만 source 한다. Ubuntu 24.04 의 시스템 Jazzy(Python 3.12)는 source 하지 않는다.
  ROS 를 source 하지 않으면 Ubuntu 24.04 에서 내부 Jazzy 라이브러리를 자동으로 쓴다. 명시하려면 `ROS_DISTRO=jazzy`, `RMW_IMPLEMENTATION=rmw_fastrtps_cpp`,
  `LD_LIBRARY_PATH` 에 `<isaacsim>/exts/isaacsim.ros2.bridge/jazzy/lib` 를 더한다.
- 5.1.0 브릿지 `extension.py` 는 시작할 때 별도 프로세스로 `jazzy/lib` 를 로드해 보고, 실패하면 위 환경변수 안내를 찍고 확장을 끈다.

그래서 **경우 A(내부 Jazzy, 상속 환경 없음)가 기본**이다. 경우 B(시스템 Jazzy 를 source 한 셸)는 문서상 지원 경로가 아니다.
master02 의 `~/.bashrc` 는 `ROS_DOMAIN_ID=115`, `ROS_DISTRO=jazzy`, `RMW_IMPLEMENTATION=rmw_fastrtps_cpp`, `FASTRTPS_DEFAULT_PROFILES_FILE=$HOME/.ros/fastdds_whitelist.xml` 을 export 하고
`/opt/ros` 는 자동 source 하지 않는다(master02 관측 2026-09-17, 로그인 셸 `LD_LIBRARY_PATH` 에 `/opt/ros` 항목 0).
A 가 실패했을 때 원인을 가르려고만 B 를 돌린다. B 가 되더라도 기본 절차로 삼지 않고 결과를 PR 에 적는다.

### 9/17 관측

출처는 master01·master02 에서 본 것을 전달받은 보고다. 이 문서 작성자가 직접 본 것은 없다.
시각은 보고에 적힌 그대로다(시간대 표기 없음). 이 스크립트는 아래 어느 관측에서도 실행되지 않았다.

master02 (`IsaacSim07`, Isaac 미기동 상태의 파일·환경 읽기):
- `~/isaacsim/VERSION` 은 `5.1.0-rc.19+release.26219.9c81211b.gl`.
- `~/isaacsim/exts` 에 `isaacsim.ros2.bridge`·`isaacsim.ros2.sim_control`·`isaacsim.ros2.tf_viewer`·`isaacsim.ros2.urdf` 가 있다. `isaacsim.ros2.bridge` 아래 `humble`·`jazzy` 가 있고 `jazzy` 아래 `lib`·`rclpy` 가 있다.
- `standalone_examples/api/isaacsim.ros2.bridge/clock.py` 가 이 스크립트와 같은 그래프 패턴(`OnPlaybackTick` → `ROS2PublishClock`, `IsaacReadSimulationTime` → `timeStamp`)이다. 예제의 `topicName` 은 `sim_time` 이다.
- 설치본 `docs/ogn/OgnIsaacReadSimulationTime.rst` 가 `resetOnStop` 을 기본 False, "False means time increases monotonically" 로 적는다.
- `~/.bashrc` 는 `/opt/ros` 를 자동 source 하지 않고 `ROS_DOMAIN_ID=115`·`RMW_IMPLEMENTATION=rmw_fastrtps_cpp`·`FASTRTPS_DEFAULT_PROFILES_FILE`(whitelist)을 export 한다.

master01 (`IsaacSim14`):
- `~/.bashrc` 124-147행이 `LD_LIBRARY_PATH` 에 `~/isaacsim/exts/isaacsim.ros2.bridge/jazzy/lib` 를 더한다.
- 14:29: GUI 로 뜬 Isaac kit 프로세스(`apps/isaacsim.exp.full.kit`)의 environ 에 `ROS_DOMAIN_ID=115`·`rmw_fastrtps_cpp`·whitelist 프로파일이 있었다. 그런데 그 프로세스의 **UDP 소켓이 0개**였다(DDS 참여자 없음). 같은 기계에서도 `/clock` 이 보이지 않았다.
- 14:11: 같은 기계 터미널에서 `/clock` echo 가 보였다. 그때 도메인은 116 이었다고 한다(재범 전언, master01 관측 아님).
- 14:33:23: master02 의 토픽 목록에 `/clock` 이 한 번 보였다가 사라졌다. 누가 냈는지는 미확인.

두 PC 사이:
- 14:30-14:35 에 도메인 115·유선·whitelist 로 talker/echo 가 양방향으로 확인됐다.

판단(관측 아님): "Isaac 의 `/clock` 이 다른 PC 에서 안 보인다" 의 1차 점검 대상은 네트워크가 아니라 Isaac 프로세스 쪽이다. master01 14:29 의 UDP 소켓 0개가 그 근거다.
그 kit 에서 bridge 확장이 켜져 있었는지, Play 상태였는지, 그래프가 있었는지는 보고에 없어 미확인이다.

### Isaac 이 ROS 2 에 참여하고 있는지 보는 법

앞 단계가 아니면 뒤 단계는 볼 필요가 없다. 위에서부터 순서대로 보고, 결과를 단계 번호와 함께 적는다.

1. **Play 상태인가.** `OnPlaybackTick` 은 타임라인이 재생 중일 때만 돈다. GUI 는 재생 버튼 상태를 본다. 이 스크립트는 시작 뒤 스스로 Play 한다.
2. **bridge 확장이 켜져 있는가.** GUI 는 Window → Extensions 에서 `isaacsim.ros2.bridge` 가 enabled 인지 본다. 로그에 `ROS2 Bridge startup failed` 가 있으면 여기서 멈춘 것이다.
3. **그래프가 지금 씬에 있는가.** GUI 에서 만든 Action Graph 는 씬을 저장하지 않고 다시 열면 없다. Stage 창에서 그래프 prim 과 `ROS2PublishClock` 노드를 찾는다.
   파일로 확인할 때 `.usda` 는 텍스트 검색이 되고 `.usd` 는 `strings <씬>.usd | grep -c ROS2PublishClock` 로 흔적만 본다(보조, 0 이 아니라고 그래프가 연결됐다는 뜻은 아니다).
4. **DDS 참여자가 있는가.** kit(또는 `python.sh` 의 자식 python) PID 로 UDP 소켓을 센다. **0 이면 참여자가 없다**. 이 경우 도메인·네트워크를 볼 단계가 아니다.

   ```bash
   pgrep -af 'isaacsim.exp.full.kit|minimal_clock.py'      # kit 또는 python PID 를 고른다
   ss -uanp | grep "pid=<PID>,"
   ```

5. **그 프로세스의 환경이 맞는가.**

   ```bash
   tr '\0' '\n' < /proc/<PID>/environ | grep -E 'ROS_DOMAIN_ID|RMW|FASTRTPS'
   ```

6. **같은 기계에서 보이는가.** 같은 도메인·프로파일의 ROS 셸에서 `ros2 topic info /clock -v`(발행자 수, QoS).
7. **다른 PC 에서 보이는가.** 6 이 되는데 7 이 안 될 때만 [유선망 설정](../docs/setup/ros2-wired-network.md)의 네트워크 점검으로 넘어간다.

주의: 데스크톱 아이콘·런처·다른 사용자 세션으로 GUI 를 띄우면 `~/.bashrc` 를 읽는 셸을 거치지 않아 `ROS_DOMAIN_ID`·`FASTRTPS_DEFAULT_PROFILES_FILE` 이 상속되지 않을 수 있다.
그래서 셸에 값이 있다는 것으로 판단하지 않고 5 의 `/proc/<PID>/environ` 을 본다. 환경이 맞아도 4 가 0 일 수 있다(master01 14:29).

### 도메인과 `/clock` 작성자

`ROS_DOMAIN_ID=115` 는 통합 도메인으로 쓰자는 **제안이고 아직 결정되지 않았다**. 계약 4절대로 한 도메인에서 `/clock` 작성자는 하나다.
115 에서 이 스크립트를 띄우기 전에 `ros2 topic info /clock -v` 로 발행자 수를 본다. **발행자가 이미 있으면 115 에서 띄우지 않는다.** 다른 도메인에서 띄우고, 붙일 스텁 스택(`stub_loop.launch.py`)도 같은 도메인으로 띄운다.
같은 기계에 다른 사람의 Isaac 이 돌 수 있다(9/17 master02 관측). 그 프로세스를 끄지 않는다.
개발 확인은 115 가 아닌 도메인에서 한다. 예: 9/17 데모는 `ROS_DOMAIN_ID=117` 로 돌렸다. master01 의 `/clock` 이 115 에 간헐적으로 나타났기 때문이다.

### master02 절차 (0단계)

계약 1절의 isaac 호스트는 master01 이지만 이 절차는 관측 가능한 master02 기준이다. master01 절차는 세준 확인 뒤에 적는다.
관측만 한다. 코드·설정을 고치지 않는다. 명령마다 출력 원문과 exit code 를 남긴다.
같은 기계에 다른 사람의 Isaac 프로세스가 돌 수 있다(2026-09-17 관측: `m0617_pick_place_fsm.py`, `/clock` 미발행). 끄지 않는다.

**0. 준비** — 경로 두 개는 현장 값으로 바꾼다(현장 확인 필요: 저장소 클론 위치와 `rokey_p3_bringup` 이 설치된 워크스페이스).

```bash
export P3_REPO=/absolute/path/to/ROKEY_P3_A3      # 이 브랜치를 체크아웃한 클론
export P3_WS_INSTALL=/absolute/path/to/install     # rokey_p3_bringup 이 든 colcon install
git -C "$P3_REPO" rev-parse HEAD
git -C "$P3_REPO" status --porcelain
cat ~/isaacsim/VERSION
ls ~/isaacsim/exts/isaacsim.ros2.bridge/jazzy/lib | head
ls ~/isaacsim/standalone_examples/api/isaacsim.ros2.bridge/
nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv
```

**1. `/clock` 작성자가 아직 없는지** — ROS 셸(시스템 Jazzy)에서.

```bash
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=115 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
ros2 topic info /clock -v
```

발행자가 이미 있으면 멈추고 그 출력을 보고한다. 작성자는 하나여야 한다([도메인과 `/clock` 작성자](#도메인과-clock-작성자)).

**2A. Isaac 띄우기 — 경우 A(내부 Jazzy)**: 새 터미널. `env -i` 로 상속 환경을 버리고 필요한 값만 넘긴다.
domain·RMW·DDS 프로파일 세 값은 `~/.bashrc` 에 있어도 `env -i` 가 지우므로 **명시해 넘긴다**([일정](../docs/planning/schedule.md) "교육장에서 최우선" 4번: Isaac 프로세스에 DDS 프로파일 전달).
`FASTRTPS_DEFAULT_PROFILES_FILE` 은 [유선망 설정](../docs/setup/ros2-wired-network.md)의 whitelist 파일이다(master02 에 있음, master02 관측: UDPv4 전용, `useBuiltinTransports` false, 127.0.0.1 과 10.10.0.1-10.10.0.4).
우리 ROS 스택은 이 파일로 UDP 만 쓴다. Isaac 쪽이 이 파일을 안 읽으면 기본 전송(공유 메모리 + 모든 인터페이스 UDP)이 되어 경로가 어긋날 수 있다(가설, 미관측). 읽는지는 3b 에서 본다.

```bash
cd "$P3_REPO"
env -i HOME="$HOME" USER="$USER" TERM="$TERM" PATH=/usr/local/bin:/usr/bin:/bin \
  ROS_DISTRO=jazzy RMW_IMPLEMENTATION=rmw_fastrtps_cpp ROS_DOMAIN_ID=115 \
  FASTRTPS_DEFAULT_PROFILES_FILE="$HOME/.ros/fastdds_whitelist.xml" \
  LD_LIBRARY_PATH="$HOME/isaacsim/exts/isaacsim.ros2.bridge/jazzy/lib" \
  ~/isaacsim/python.sh sim/standalone/minimal_clock.py --headless 2>&1 | tee -i /tmp/p3-minimal-clock-A.log
```

`[minimal_clock] start` 줄이 나오고 `FASTRTPS_DEFAULT_PROFILES_FILE=/home/rokey/.ros/fastdds_whitelist.xml ld_internal_jazzy=True ld_opt_ros=False` 인지 본다.
`error` 줄이나 `ROS2 Bridge startup failed` 가 나오면 그 앞뒤 로그를 보고하고 2B 로 간다.

**2B. 비교용 — 경우 B(시스템 Jazzy 를 source 한 셸)**: 2A 가 실패했을 때만. 5.1 문서상 지원 경로가 아니다.

```bash
cd "$P3_REPO"
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=115 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
~/isaacsim/python.sh sim/standalone/minimal_clock.py --headless 2>&1 | tee -i /tmp/p3-minimal-clock-B.log
```

**3. 발행 확인** — 1 의 ROS 셸에서, Isaac 이 도는 동안.

```bash
ros2 topic info /clock -v                 # 기대: Publisher count 1, Reliability RELIABLE, Durability VOLATILE
timeout -s INT 15 ros2 topic hz /clock    # wall 기준 평균 Hz. 목표 60
ros2 topic echo /clock --once; sleep 2; ros2 topic echo /clock --once   # 두 번째 sec/nanosec 가 더 크다
```

1 의 ROS 셸은 `~/.bashrc` 로 whitelist 프로파일을 이미 쓴다. `printenv FASTRTPS_DEFAULT_PROFILES_FILE` 출력도 함께 남긴다.

**3b. Isaac 의 Fast DDS 가 whitelist 프로파일을 읽는지** — 현장 확인 필요. Isaac 이 도는 동안. 한 가지 결과만으로 판정하지 않고 셋을 모두 적는다.

```bash
pgrep -af 'sim/standalone/minimal_clock.py'; PID=$(pgrep -f 'sim/standalone/minimal_clock.py' | tail -n 1); echo "$PID"
tr '\0' '\n' < /proc/$PID/environ | grep -E '^(FASTRTPS_DEFAULT_PROFILES_FILE|ROS_DOMAIN_ID|RMW_IMPLEMENTATION)='   # (a) 변수 전달
ls -l /proc/$PID/fd 2>/dev/null | grep -c /dev/shm        # (b) 공유 메모리 파일 수. 프로파일이 읽혔으면 0 이어야 한다(useBuiltinTransports false)
ss -uanp 2>/dev/null | grep "pid=$PID," | awk '{print $4}' | sort | uniq -c   # (c) UDP 소켓 주소. 0.0.0.0 과 특정 IP 중 무엇에 묶였는지
```

`python.sh` 셸과 그 자식 python 이 둘 다 잡힐 수 있다. `PID` 는 `pgrep -af` 목록에서 python 실행 파일 쪽이어야 한다. 셸이 골라졌으면 그 PID 로 바꿔 다시 본다.
비교: 3b 를 끝낸 뒤 Isaac 을 Ctrl+C 로 내리고, 2A 명령에서 `FASTRTPS_DEFAULT_PROFILES_FILE=...` 줄만 뺀 채 다시 띄워 (b)·(c) 를 한 번 더 본다. 두 결과가 같으면 내부 Fast DDS 가 변수를 안 읽는다는 쪽이다.
구독 쪽 비교(같은 기계라 둘 다 보일 수 있어 판정력은 약하다): whitelist 가 있는 셸과 없는 셸에서 각각 `ros2 topic hz /clock` 이 도는지.

```bash
env -u FASTRTPS_DEFAULT_PROFILES_FILE bash -c 'source /opt/ros/jazzy/setup.bash; ros2 daemon stop; timeout -s INT 10 ros2 topic hz /clock'
bash -c 'source /opt/ros/jazzy/setup.bash; ros2 daemon stop; timeout -s INT 10 ros2 topic hz /clock'
```

**4. Stop/Play 에 되감기지 않는지** — Isaac 을 Ctrl+C 로 내리고 옵션을 붙여 다시 띄운다(2A 또는 성공한 경우의 명령 끝에 `--stop-play-after 10`).
Isaac 로그의 `stop_play` 줄에서 `sim_time_after >= sim_time_before` 인지, 그 사이 ROS 셸에서 아래 출력의 `sec` 가 줄지 않는지 본다.

```bash
timeout -s INT 20 ros2 topic echo /clock --field clock.sec | uniq
```

**5. 스텁 한 바퀴를 Isaac `/clock` 으로** — Isaac 을 띄운 채 새 ROS 셸에서. 이 run 은 smoke 다.
[protocol](../experiments/protocols/pharmacy-lap-pilot-v1.json) 상 기동 직후 epoch 1 트립은 시행이 아니므로 evidence 시행으로 세지 않는다.

```bash
source /opt/ros/jazzy/setup.bash
source "$P3_WS_INSTALL/setup.bash"
export ROS_DOMAIN_ID=115 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
ros2 launch rokey_p3_bringup stub_loop.launch.py publish_clock:=false pharmacy_only:=true run_host:=master02
```

다른 ROS 셸에서 `ros2 topic info /clock -v` 가 여전히 발행자 1 인지 본다(`stub_sim` 이 내면 2).
`order_generator` 로그의 `Deliver` 결과가 나오면 launch 터미널에서 **Ctrl+C**(SIGINT)로 내린다([배포 runbook 중지](../docs/runbooks/deployment.md#중지)).
run 디렉토리는 `log_dir` 을 안 줬으면 `$ROS_HOME/rokey_p3/runs`(`ROS_HOME` 이 없으면 `~/.ros`) 아래 `<UTC>-master02-<hex>` 다.

```bash
RUN=$(ls -d "${ROS_HOME:-$HOME/.ros}"/rokey_p3/runs/*-master02-* | tail -n 1); echo "$RUN"
ls "$RUN"                                   # orders.jsonl, meta.json 이 있어야 run 이 닫힌 것
cat "$RUN/orders.jsonl"                     # 기대: HOLD_RETURN, reason pharmacy_only
python3 "$P3_REPO/tools/aggregate_runs.py" --run "$RUN" --protocol "$P3_REPO/experiments/protocols/pharmacy-lap-pilot-v1.json"
```

**6. 종료** — Isaac 터미널에서 Ctrl+C. `tmux` 면 `tmux send-keys -t <세션> C-c`. `kill -TERM`·`kill-session`·`docker stop` 은 쓰지 않는다.

```bash
echo "exit=${PIPESTATUS[0]}"    # tee -i 파이프의 첫 명령(Isaac) exit code. 기대 0
```

`[minimal_clock] stop reason=sigint ... loop_hz=... rtf=...` 줄과 exit code 를 보고한다.

**보고할 것**: 0 의 출력, 2A(와 2B) 로그 원문, 3·4·5 의 출력, 6 의 exit code. 관측과 판단을 나눠 적는다.

### 1단계 후보 메모

simulation 레인(세준)의 몫이다. 여기서는 구현하지 않고 후보만 적는다. 어느 것도 확인·결정되지 않았다.

- 조제실 최소 구성: 직선 벨트 1구간 + 봉투 + 끝 정지 센서.
- `/sim/reset`: 타임라인 Stop 없이 상태만 되돌리거나, Stop 을 쓰면 `resetOnStop` False 로 `/clock` 이 되감기지 않게 한다(계약 4절). 어느 쪽이 되는지는 미확인.
- `isaacsim.ros2.sim_control` 확장: master02 `~/isaacsim/exts` 에 있다(master02 관측). ROS 2 로 시뮬레이션을 제어하는 확장으로 보이며 동작은 미확인.
- 수업 자산 `~/cobot3_ws/isaacpjt/M0609/`: dev01(재범 노트북)에서 본 경로다. 292 MB, `Collected_m0609_gripper/m0609_gripper.usd` 와 `rmpflow/` 설정이 있다. master02 개발 클론의 미추적 `isaacpjt/M0609/` 는 master02 관측이고 내용이 같은지는 미확인.
  저장소에 넣지 않는다. 스크립트는 경로를 인자로 받고, 실행 기록에 쓴 파일의 sha256 을 남기는 방식을 권한다.

## Isaac ↔ ROS 어댑터 인터페이스 (JSON, v1)

조제실 스테이지(`pharmacy_stage.py`)가 계약 타입 대신 쓰는 토픽이다. **이 표가 기준 문서다.** 결정 기록은 [ADR 0002](../docs/adr/0002-isaac-json-topics-and-ros-adapter.md)(proposed)에 둔다. 시스템 ROS 쪽 어댑터(`rokey_p3_bringup` 의 `isaac_adapter`)가 이 토픽을 계약 이름·타입(`/pharmacy/dispense`, `/sim/reset`, `/pharmacy/belt`, `/events`)으로 바꾼다. 어댑터는 `sim/` 을 import 하지 않는다.

왜 JSON 인가(2026-09-17 결정): Isaac Sim 5.1 은 Python 3.11 전용이고 내부 ROS 라이브러리는 공통 인터페이스만 싣는다([5.1 ROS 설치 안내](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/install_ros.html)).
`rokey_p3_interfaces` 는 시스템 Jazzy(Python 3.12)로 빌드되므로 Isaac 안에서 import 되지 않는다고 봤다. Python 3.11 커스텀 빌드는 마스터 설치 작업이 필요해 택하지 않았다.
9/17 master02 에서 Isaac 내부 rclpy 로 `std_msgs`·`sensor_msgs` 는 실제로 돌았다. `std_srvs` 는 확인하지 않아 서비스 대신 요청·응답 토픽 쌍으로 한다.

공통 규칙:
- 타입은 전부 `std_msgs/String`, `data` 에 JSON 객체 하나. 모든 메시지에 `"v": 1`(스키마 버전). 정의에 없는 필드가 있으면 형식 오류다.
- `stamp` 는 sim time(`{"sec": int, "nanosec": int}`, `builtin_interfaces/Time` 과 같은 뜻). 어댑터가 `header.stamp` 로 옮긴다.
- `epoch` 는 uint32. Isaac 은 마지막으로 받은 `reset_request` 의 epoch 를 이후 `belt`·`events` 에 싣는다. 기동 직후 첫 리셋 전에는 **1**(계약 4절: epoch 는 1 부터. 0 이면 event_logger 가 stale 로 적는다).
- 형식 오류인 요청은 Isaac 이 응답하지 않고 로그만 남긴다(어댑터의 서비스 시한으로 실패 처리).
- Isaac 은 `RESET_BEGIN`·`RESET_DONE` 을 내지 않는다(오케스트레이터 소관). `/isaac/events` 에는 `DISPENSED`, `POUCH_AT_END` 만 낸다(`Event.msg` 상수 철자, `robot_id` 는 `dispenser`).
- `reset_response` 는 타임라인을 멈추지 않고(`/clock` 은 되감기지 않는다) 계약 6절 2 범위를 **끝낸 뒤에만** `ok: true` 로 낸다: 벨트 정지, 봉투 주차(삭제하지 않는다), UR5 흡착 끄고 시작 관절로, M0609 그리퍼 열기·홈과 레일 원점(이 스테이지에서 레일은 M0609 의 일부, `set_joint_positions` 로 위치와 목표를 같이), 캐니스터를 선반 칸으로, 보충 데모 사이클 처음으로. `epoch` 는 요청 값을 그대로 돌려준다.

| 토픽 | 방향 | QoS | 필드 | 대응 계약 |
| --- | --- | --- | --- | --- |
| `/isaac/pharmacy/dispense_request` | 어댑터 → Isaac | reliable, volatile, depth 10 | `v`, `request_id`(비어 있으면 안 됨), `order_id` | `/pharmacy/dispense` 요청 |
| `/isaac/pharmacy/dispense_response` | Isaac → 어댑터 | reliable, volatile, depth 10 | `v`, `request_id`, `order_id`(요청 값 그대로), `accepted`, `message`(수락이면 `""`, 거부면 계약 2.1 의 네 값 `belt_occupied`·`unknown_order`·`not_ready`·`pool_exhausted`) | `/pharmacy/dispense` 응답 |
| `/isaac/sim/reset_request` | 어댑터 → Isaac | reliable, volatile, depth 10 | `v`, `epoch` | `/sim/reset` 요청 |
| `/isaac/sim/reset_response` | Isaac → 어댑터 | reliable, volatile, depth 10 | `v`, `epoch`(요청 값 그대로), `ok`, `message`(성공이면 `""`) | `/sim/reset` 응답 |
| `/isaac/pharmacy/belt` | Isaac → 어댑터 | reliable, volatile, depth 1, 5 Hz(wall) | `v`, `stamp`, `occupied`, `at_end`, `order_id`(비었으면 `""`), `epoch` | `/pharmacy/belt` `BeltState` |
| `/isaac/events` | Isaac → 어댑터 | reliable, transient local, depth 500 | `v`, `stamp`, `name`, `request_id`, `order_id`, `robot_id`, `epoch`, `detail` | `/events` `Event` |
| `/isaac/pharmacy/pick_notice` | 어댑터 → Isaac | reliable, volatile, depth 10 | `v`, `stamp`(원 사건의 stamp), `epoch`, `order_id`(비어 있으면 안 됨), `source`(`POUCH_PICKED` 만) | `/events` 의 `POUCH_PICKED`(팔) — 9/17 추가, 계약 v1 변경 없음 |

예시(글자 그대로. 키 순서는 의미 없고 Isaac 은 키를 정렬해 낸다):

```text
/isaac/pharmacy/dispense_request   정상
{"order_id":"ord-0001","request_id":"r002-0001","v":1}
/isaac/pharmacy/dispense_request   형식 오류(request_id 비어 있음, Isaac 이 응답하지 않는다)
{"order_id":"ord-0001","request_id":"","v":1}

/isaac/pharmacy/dispense_response  수락
{"accepted":true,"message":"","order_id":"ord-0001","request_id":"r002-0001","v":1}
/isaac/pharmacy/dispense_response  거부
{"accepted":false,"message":"belt_occupied","order_id":"ord-0002","request_id":"r002-0002","v":1}

/isaac/sim/reset_request           정상
{"epoch":3,"v":1}

/isaac/sim/reset_response          성공
{"epoch":3,"message":"","ok":true,"v":1}
/isaac/sim/reset_response          실패(--reset-fail 주입)
{"epoch":3,"message":"injected_failure","ok":false,"v":1}

/isaac/pharmacy/belt               봉투가 끝에 섰다
{"at_end":true,"epoch":3,"occupied":true,"order_id":"ord-0001","stamp":{"nanosec":450000000,"sec":123},"v":1}
/isaac/pharmacy/belt               비어 있음
{"at_end":false,"epoch":3,"occupied":false,"order_id":"","stamp":{"nanosec":0,"sec":130},"v":1}

/isaac/events                      DISPENSED
{"detail":"","epoch":3,"name":"DISPENSED","order_id":"ord-0001","request_id":"r002-0001","robot_id":"dispenser","stamp":{"nanosec":200000000,"sec":118},"v":1}
/isaac/events                      POUCH_AT_END
{"detail":"","epoch":3,"name":"POUCH_AT_END","order_id":"ord-0001","request_id":"r002-0001","robot_id":"dispenser","stamp":{"nanosec":450000000,"sec":123},"v":1}

/isaac/pharmacy/pick_notice        정상(벨트 끝 봉투가 ord-0001, 현재 epoch 3 → 즉시 주차)
{"epoch":3,"order_id":"ord-0001","source":"POUCH_PICKED","stamp":{"nanosec":850000000,"sec":123},"v":1}
/isaac/pharmacy/pick_notice        무시(형식은 맞지만 epoch 2 는 현재 3 이 아니다)
{"epoch":2,"order_id":"ord-0001","source":"POUCH_PICKED","stamp":{"nanosec":850000000,"sec":123},"v":1}
```

배출 판정 순서(Isaac): 준비 안 됨(기동 중·리셋 처리 중) → `not_ready`, `order_id` 가 `ord-` 숫자 4자리가 아니거나 `--order-pool` 에 없음 → `unknown_order`, 벨트에 봉투가 있음 → `belt_occupied`, 미리 만든 봉투가 전부 나가 있음(벨트·상판) → `pool_exhausted`, 아니면 수락.
`pool_exhausted` 는 멈추는 대신 거부하려고 스테이지가 9/17 에 넣은 값이다. 9/24 부터 계약 2.1 의 거부 넷 가운데 하나다([계약 10.2](../docs/architecture/delivery-contract-v1.md#102-dispense-거부-pool_exhausted-924)). 어댑터는 #108 이다. `9eaf573` 이다. 네 값 밖 `message` 만 경고를 찍는다. 그대로 넘긴다. orchestrator 는 거부를 2 s 간격으로 최대 3회 다시 부른 뒤 그 주문을 `ABORT`(reason = message)로 닫는다. 수락하면 봉투를 벨트 시작에 스폰하고 벨트를 돌리고 `DISPENSED` 를 낸다.
배출·리셋 응답 시한(계약 7절: `Dispense` 2 s, `Reset` 30 s wall)은 어댑터가 잰다.

`pick_notice` 처리(Isaac): 어댑터는 `/events` 의 `POUCH_PICKED` 를 받으면 그 `order_id`·`epoch`·`stamp` 로 보낸다. Isaac 은 `epoch` 가 현재와 같고, 벨트 끝에 선 봉투가 있고(`at_end`), `order_id` 가 그 봉투와 같을 때만 즉시 봉투를 주차하고 벨트를 비운다(`ros pick_notice order_id=… delay_s=…`, delay 는 `POUCH_AT_END` 부터). 아니면 이유를 찍고 무시한다. 응답 토픽은 없다. `--ros-pick-stand-in-s` 는 폴백으로 남고 둘 중 먼저 온 쪽이 치운다. 진짜 UR5(`--ur5`)가 봉투를 집는 구성에서는 어댑터가 이 토픽을 보내지 않는다.
9/17 master02 확인: `9d0a441`(`--preset demo-ros`) + 어댑터 `b3bb789`, 도메인 117. epoch 1 에서 `POUCH_AT_END` 11.95 → `ros pick_notice order_id=ord-0002 delay_s=0.350 sim_time=12.300` → `pouch_parked … reason=ros_pick_notice`, stand-in 은 발동하지 않았다. 이어서 reset 반복 30회(epoch 2→31)에서 pick_notice 31회 모두 처리(`delay_s` 0.317-0.717), stand-in·ignored·dropped 0.

벨트 이송 시간(기본값 계산): 스폰 벨트 좌표 x 0.05-0.15(`--spawn-along`), 끝 구역 시작 x = 길이 1.6 − `--end-zone` 0.15 = 1.45, 속도 0.15 m/s → 끝 구역까지 8.7-9.3 s, 거기에 정지 판정 `--settle-time-s` 0.3 s 를 더해 약 9.0-9.7 s.

**벨트 실제 속도 1.6배(9/17 master02, 원인 확인·기본값 변경).** 같은 인자(`--belt-speed 0.15`)로 창 모드 + ros 모드 실행(`ed91f0b` 17:08, `9d0a441` 18:32, `6720679` 19:38 14/14 바퀴)은 봉투가 0.24 m/s 로 갔고(`DISPENSED`→`POUCH_AT_END` 5.85-5.88 s), 18:43 재기동(G-4)과 headless selfdemo 8회는 0.15 m/s(9.12-9.18 s)였다. 0.24 = 0.15 × 1.6 이고 1.6 은 벨트 Cube 의 x scale 이다.
- **원인: scale 이 걸린 강체에 surface velocity 를 걸면 PhysX 쪽에서 x scale 이 곱해진다.** 판별(`021a80b`, 창 모드 `--preset demo-ros` + 어댑터 + 웹, 연속 실행, 각 5바퀴): 몸체 `scaled-cube` 5/5 `ratio=1.600`, `scaled-cube --belt-presurface` 5/5 `ratio=1.600`(효과 없음), `xform` 5/5 `ratio=1.000`. 세 실행 모두 USD `physxSurfaceVelocity:surfaceVelocity=(0.15, 0, 0)`, 그래프 Velocity 0.15. 5.1.0 `OgnIsaacConveyor.cpp` 는 scale 을 곱하지 않는다(소스 확인). 한 실행 안에서는 바퀴마다 같다.
- **기본 몸체를 `xform` 으로 바꿨다**(scale 없는 Xform 강체 + scale 된 Cube 충돌 자식, 벨트 prim 경로·그래프 경로는 같다). preset 둘도 `xform` 이다. 9/17 까지의 몸체는 `--belt-body scaled-cube` 로 재현한다.
- 남은 의문(미확인): headless `--preset selfdemo-refill` 8회는 `scaled-cube` 에서도 `ratio=1.000` 이었다. 창 모드 때문인지 ros 모드 때문인지 아직 갈리지 않았다(창 모드 selfdemo 판별 대기).
- `--belt-presurface`(`PhysxSurfaceVelocityAPI` 를 첫 play 전에 붙임)는 효과가 없었다. 옵션은 남겨 둔다.
- 측정 줄은 그대로다: 봉투마다 벨트 중간(길이의 40-75%)에서 한 번 `belt speed_measured=… requested=… ratio=… mismatch=… surface_velocity_attr=… graph_velocity=… body=… body_scale=…`. 기동 직후 `physx_query belt_after_reset …`·`belt_after_reset applied_schemas=…` 도 남긴다.
- 불일치(±20% 밖)면 한 줄을 더 찍는다: `ERROR 벨트 속도 이상: 실측 0.24 / 설정 0.15 (ratio 1.6). 이 실행의 시간 지표는 쓰지 말 것. 재기동 권장`. 자동 보정은 하지 않는다(원인을 모르는 채 가리게 된다). 같은 봉투의 `POUCH_AT_END` 이벤트 `detail` 에 `belt_ratio=1.600` 을 싣는다(정상이면 빈 문자열). 측정이 `DISPENSED` 뒤라 `DISPENSED` 가 아니라 `POUCH_AT_END` 에 싣는다. `detail` 은 판정에 쓰지 않는 메모라 인터페이스 v1 안이다.
- protocol 지표 `dispense_to_end_s` 를 모을 때는 `ratio` 가 1 인 실행만 쓴다. 9/17 의 5.83-6.20 s 는 0.24 m/s 로 돈 값이다. `POUCH_AT_END` `detail` 의 `belt_ratio=` 로 걸러낸다(9/17 I-b 실행에서 실제로 찍힘).
이 표를 바꾸면 `"v"` 를 올리고 어댑터와 같은 PR 흐름으로 맞춘다.

## 0.5단계: M0609 보충 스테이지

> **상태: 지난 기록 (2026-09-17 기준).** 지금은 [현행 절](#지금-무엇이-현행인가-v110-병원-한-바퀴)을 따른다.

`standalone/m0609_refill_stage.py` 는 빈 월드에 M0609 + 그리퍼 USD, 보관 선반(캐니스터 여러 개), 조제기 몸체 위의 슬롯 A·B 를 놓는다.
M0609 가 선반 맨 앞 캐니스터를 집어 빈 슬롯에 넣는 장면을 반복해서 본다([시나리오](../docs/planning/scenario.md) 2·4절 "재고와 보충"의 조제실 쪽).
컨베이어·조제기 배출·AMR·`/sim/reset` 은 없다(simulation·navigation 레인).

### 9/17 첫 실행 (master02, Isaac 5.1.0-rc.19, 창 모드, 도메인 117)

master02 관측을 전달받은 것이다. 원본 로그는 master02 `~/markle_tmp/` 에 있다. 각 줄 뒤 괄호는 그 실행이 쓴 커밋이다.
- selfdemo 물리 파지(`5d6a10b`): 팔은 전 구간 도달(`tcp_error_m` 0.0001-0.0002). `to_shelf` 보간 중간점 7개에서 `ik_failed`.
  닫은 뒤 `holding=True` 였지만 lift 에서 `holding=False`, 약통은 거의 안 움직였고(`[0.3500, 0.2505, 0.1400]`) `canister_in_slot=False`. `holding` 은 거리 판정일 뿐 접촉 파지 증거가 아니다.
  dof 12개(팔 6 + 그리퍼 6), `finger_joint` 드라이브는 USD 값 그대로(stiffness 36.06, max effort 50), mimic 5개 stiffness 0. dof 종류가 전부 `type=invalid` 로 찍혔다. 종료 줄 `loop_hz=59.10 rtf=0.962`, exit 0. 기동 중 Ctrl+C 한 번이 섞인 오염된 실행이다.
- selfdemo `--attach`(`5d6a10b`): 15:48:23 `canister_in_slot=True`, `canister_xyz=[0.3531, -0.2586, 0.0500]`, grasp 부터 insert 까지 `holding=True`. 재범이 화면으로 확인.
- `--mode ros --attach`(`5d6a10b`): 기동 뒤 첫 관절 읽기에서 "Physics Simulation View is not created yet" 경고와 `TypeError` 로 끝났고 exit 는 0 이었다. `/m0609/*` 토픽은 하나도 안 보였다.
- 이 관측들 뒤의 수정은 `fix/sim-m0609-grasp`(#98) 커밋이다. 그 뒤 실행 확인은 [단계 요약](#단계-요약)과 [알려진 문제](#알려진-문제미확인)에 모아 둔다.

### 모드

| 모드 | 무엇 | ROS |
| --- | --- | --- |
| `--mode selfdemo` | Lula IK 로 TCP 를 선반 위 → 잡기 → 들기 → 슬롯 위 → 삽입 → 놓기 → 후퇴. `--loop` 바퀴만큼 반복하고, 바퀴 사이에 홈 복귀와 캐니스터 재스폰. 도달한 관절값을 `teach` 줄로 찍는다 | `/clock` 만 |
| `--mode ros`(기본) | 계약 v1 2.1절 M0609 항목의 이름·타입·QoS 로 브릿지. `rokey_p3_manipulation` 의 `m0609_arm` 이 이 씬을 그대로 움직인다. 넣은 캐니스터는 `--respawn-delay-s` 뒤 선반으로 돌아간다 | 아래 표 |

`--mode ros` 토픽(계약 2.1절 "amr_1 팔과 같다", QoS 는 `arm_node.py` 의 상수와 같게 두었다):

| 토픽 | 방향 | 타입 | QoS | 주기 |
| --- | --- | --- | --- | --- |
| `/clock` | 발행 | `rosgraph_msgs/Clock` | R | 업데이트마다([0단계](#0단계-빈-월드--clock)와 같은 그래프) |
| `/m0609/joint_states` | 발행 | `sensor_msgs/JointState` 팔 6개, `position`·`velocity`, stamp 는 sim time | S(best effort, depth 5) | wall 30 Hz |
| `/m0609/gripper/holding` | 발행 | `std_msgs/Bool`(거리 판정) | H(reliable, depth 1) | wall 10 Hz |
| `/m0609/arm/joint_command` | 구독 | `sensor_msgs/JointState` `position` | R(reliable, depth 10) | 받는 대로 |
| `/m0609/gripper/command` | 구독 | `std_msgs/Bool`, true = 닫기 | R | 받는 대로 |

- `joint_command` 에 팔 관절이 아닌 이름이 하나라도 섞이면 그 메시지를 통째로 버리고 로그에 이유를 남긴다(계약 2.1절). 일부 관절만 온 명령은 받는다.
- `/clock`·SIGINT 처리·시작 환경 줄은 `minimal_clock.py` 를 가져다 쓴다. `resetOnStop` False, 종료 줄에 `loop_hz`·`rtf`.
- 배치가 앞뒤가 안 맞으면 Isaac 을 띄우기 전에 `error layout:` 줄과 exit 2 로 끝난다. 실행 중 오류는 traceback 과 `exit code=1` 줄을 찍고 exit 1(`simulation_app.close()` 가 0 으로 끝내서 그 전에 나간다).

### 인자 묶음

| 묶음 | 인자(기본값) | 무엇 |
| --- | --- | --- |
| 반복·속도 | `--loop`(1, 0 = 무한), `--tcp-speed`(0.0007 m/update), `--joint-speed`(0.5 rad/s), `--phase-pause-s`(0.5) | selfdemo 바퀴 수, TCP 보간 속도(60 Hz 에서 약 4 cm/s), 홈 복귀 속도, 단계 사이 정지 |
| 재스폰 | `--respawn-delay-s`(3) | ros: 캐니스터가 A·B 칸 안 + 그리퍼 열림이 이만큼(sim s) 이어지면 선반 맨 앞 자리로. `respawn count=… reason=… from=… to=…` |
| 조제기·선반 | `--slot-xyz`(A), `--slot-b-xyz`(B), `--slot-size`, `--slot-wall`, `--dispenser-height`(0.10, 0 = 없음), `--shelf-count`(2), `--shelf-pitch`(0.06), `--loop-slots`(a/b/ab) | 슬롯 A·B 는 몸체 위. 캐니스터는 맨 앞(`--canister-xyz`)을 집고 여분은 +x 로 늘어선다. `ab` 는 바퀴마다 A, B 번갈아 |
| 파지 | `--gripper-drive`(1e4 1e2 10), `--keep-usd-gripper-drive`, `--friction`(1.0 1.0), `--finger-links`, `--open-width`(0.110), `--grip-squeeze`(0.004), `--gripper-close`(sweep 유도), `--no-gripper-sweep`, `--grasp-settle`(1.0), `--grip-depth`(0.04), `--lift-verify`(0.01), `--attach` | 아래 "물리 파지" |
| IK 경로 | `--joint-space-phases`(to_shelf), `--tool-yaw`(fixed/radial) | 아래 "IK 경로" |
| 기동 | `--warmup-updates`(10), `--livestream` | 물리 준비 확인, 원격 보기 |

### 물리 파지

`--attach` 없이 캐니스터가 실제로 들리게 하려는 설정이다. 전부 Isaac 에서 미확인이다.
- 그리퍼 드라이브: `finger_joint` 에 `--gripper-drive` 를 준다. 기본값 1e4·1e2·10 은 **우리 선택값이다**(측정·문서 근거 없음). 위치 목표를 붙잡을 만큼 강하게, 캐니스터를 밀어내지 않게 토크 상한은 낮게 잡았다. 수업 예제는 그리퍼 드라이브를 바꾸지 않는다.
- mimic 확인: 시작 때 `mimic joint=… gearing=… offset=…`, 닫은 뒤·들기·놓기에서 `gripper_state tag=after_grasp finger_spacing=… finger_joint=… left_inner_knuckle_joint=…(expected …)`. expected 는 PhysX 규약 `q + gearing * q_ref + offset = 0` 로 계산했다(규약은 로그와 대조해 확인한다).
- 마찰: 캐니스터와 `--finger-links` 의 `collisions` prim 에 물리 재질(`--friction` static·dynamic). 로그 `friction bound=…`.
- 닫힘 목표: 기동 때 `finger_joint` 를 7각도로 쓸어 손가락 링크 간격을 재고, 열림 간격을 `--open-width`(RG2 스트로크 110 mm, 제조사 수치를 옮긴 것이고 저장소에서 재확인하지 않았다)에 맞춰 패드 간격 표를 만든다. 캐니스터 폭 - `--grip-squeeze` 가 되는 각도를 닫힘 목표로 쓴다. 로그 `gripper_sweep …` 와 `gripper_close target=… source=sweep|argument|fallback`.
- 판정: `holding` 토픽은 거리 판정 그대로다. 로그는 따로 `grasp_verified`(닫힘 + 캐니스터 z 가 닫을 때보다 `--lift-verify` 넘게 오름)를 찍는다. selfdemo 바퀴 줄의 `grasp_verified_at_lift` 가 물리 파지 성공의 기준이다.

### IK 경로

- `--joint-space-phases`(기본 `to_shelf`): 목표에서 IK 를 한 번 풀어 관절 공간으로 보간한다. 9/17 에 홈에서 선반 위로 가는 TCP 직선의 중간점 7개가 IK 에 실패했다. 목표 IK 가 실패하면 TCP 직선으로 돌아간다.
- `--tool-yaw`: `fixed`(기본)는 도구 자세를 월드에 고정한다. 그러면 joint_1 이 선반 쪽에서 슬롯 쪽으로 도는 만큼 joint_6 이 반대로 돈다(9/17 teach 값 joint_1 0.61 → -0.63, joint_6 -2.54 → -3.78). `radial` 은 목표 방위만큼 도구를 z 축으로 돌려 그 역회전을 없앤다. IK 초기값은 이미 현재 관절값이다.
- dof 종류: 시작 줄 `dof … type=rotation type_raw=0`. 9/17 의 `type=invalid` 는 표시 매핑 문제였다(5.1.0 `dof_properties` 문서는 0 = invalid, tensor `DofType` 은 0 = Rotation).

### 배치 — 임시, 시나리오 자리

단위 m, 월드 프레임, 로봇 베이스는 원점. 전부 인자로 바꾼다. **도달 범위·충돌은 슬롯 z 0.05 배치에서만 관측됐고(9/17 attach 성공) 아래 기본값에서는 미확인이다.**

| 물체 | 기본값 | 색 |
| --- | --- | --- |
| 보관 선반 | 중심 (0.35, 0.25, 0.05), 크기 0.16×0.16×0.10 | 갈색 |
| 캐니스터 | 맨 앞 중심 (0.35, 0.25, 0.14), 여분 (0.41, 0.25, 0.14), 크기 0.04×0.04×0.08, 0.05 kg | 맨 앞 빨강, 여분 주황 |
| 조제기 몸체 | 슬롯 A·B 아래를 덮는 상자, 높이 0.10, 윗면 z 0.10 | 회색 |
| 슬롯 A | 바깥 상자 중심 (0.35, -0.25, 0.15), 0.10×0.10×0.10, 벽 0.01, 위가 열림 | 파랑 |
| 슬롯 B | 바깥 상자 중심 (0.35, -0.37, 0.15) | 초록 |

9/17 attach 성공 배치로 돌리려면 `--slot-xyz 0.35 -0.25 0.05 --slot-b-xyz 0.35 -0.37 0.05 --dispenser-height 0`.
비워 둔 자리(넣지 않는다): 조제기 배출구와 컨베이어는 조제기 몸체의 -x 쪽(로봇 반대편), AMR 적재 위치는 그 컨베이어 끝(세준·태규 레인). 선반·슬롯 좌표는 계약의 `zones.yaml` `pharmacy` 프레임과 아직 연결하지 않았다(계약 2.1절).

### 자산 — 저장소에 넣지 않는다

수업 자산 `~/cobot3_ws/isaacpjt/M0609/` 을 쓴다. 저장소에 커밋하지 않고 `--robot-usd` 등 절대 경로 인자로 준다. 시작 줄에 `--robot-usd` 파일의 sha256 을 찍는다(참조하는 `SubUSDs/` 는 해시에 안 들어간다).

dev01(재범 노트북)의 사본을 읽은 사실(2026-09-17, `usd-core` 로 파일만 열었다. Isaac 실행 아님):
- `Collected_m0609_gripper/m0609_gripper.usd` 는 바이너리 usdc, defaultPrim `/World`, `metersPerUnit` 1.0, upAxis Z.
- 로봇 `/World/m0609`(원점, 회전 없음). articulation root 는 `/World/m0609/root_joint`(body0 없는 fixed joint).
- 팔 관절 `/World/m0609/joints/joint_1` 부터 `joint_6`, 전부 revolute. 한계(USD, 도) `joint_3` ±150, 나머지 ±360. 드라이브 강성 11 에서 1135 로 낮다.
- 그리퍼 `onrobot_rg2ft`: 드라이브는 `finger_joint`(0 에서 67.6 도) 하나. 나머지 revolute 5개(`right_inner_finger_joint`, `left_inner_knuckle_joint`, `left_outer_knuckle_joint`, `left_inner_finger_joint`, `right_inner_knuckle_joint`)는 드라이브 없이 `physxMimicJoint:rotX` 속성(참조 `finger_joint`, gearing 은 `right_inner_knuckle_joint` 만 -1, 나머지 1, offset 0)만 있다. 손가락 충돌 메시는 instance proxy 이고 물리 재질은 파일 어디에도 없다.
  `link_6` 에 `onrobot_rg2ft/quick_changer` 가 fixed joint 로 붙는다. 파일을 열 때 `onrobot_rg2ft/world/visuals` 참조 하나가 풀리지 않는다는 경고가 났다.
- `rmpflow/m0609_description.yaml` cspace 는 `joint_1` 부터 `joint_6`, root `base_link`. URDF 는 `doosan-robot2/urdf/m0609_isaac_sim.urdf`(링크 `base_link`, `link_1` 부터 `link_6`, `tool0`).
- 수업 예제 `7_pick_place_color.py`(실행 안 함)가 쓰는 값: TCP 는 `link_6` 로컬 z 0.19671 m, 도구 자세 쿼터니언 (0, 1, 0, 0), 그리퍼 `finger_joint`·`right_inner_knuckle_joint` 열기 0.0 닫기 0.8 rad, **팔** 드라이브 1e8·1e4·1e8(그리퍼 드라이브는 바꾸지 않는다). 팔 기본값과 닫힘 fallback 0.8 은 여기서 왔다.
- 같은 예제 주석: headless 에서 `simulation_app.is_running()` 이 바로 False 가 되는 경우가 있다. 그래서 이 스크립트는 `--headless` 면 그 값으로 루프를 끝내지 않는다.

master02 의 `~/cobot3_ws/isaacpjt/M0609` 세 파일 sha256 이 dev01 과 **전부 같다**(9/17 master02 에서 비교). 기준 값(dev01 에서 `sha256sum`):

```text
b4879c8319851a23828c562dc9dc4f5018ddfcbfde9b082c6ce5547eff19ebeb  Collected_m0609_gripper/m0609_gripper.usd
a6f0bb5bd566f47041938dc2d6020975b51609c5c744e033b87047f899f0364d  rmpflow/m0609_description.yaml
979f2e5af3c0558a987f370c69de1ae976802f6825954fc5fb9be055cd00278f  doosan-robot2/urdf/m0609_isaac_sim.urdf
```

9/17 master01 Isaac 씬의 매니퓰레이터 prim 이 `/World/manipulator/m0617/…` 였다는 관측이 있다([manipulation README](../src/rokey_p3_manipulation/README.md#m0609_arm)). M0609 와 M0617 중 무엇으로 갈지는 정하지 않았다. 이 스크립트는 M0609 수업 자산 기준이다.

### master02 절차 (0.5단계)

관측만 한다. 명령마다 출력 원문과 exit code 를 남긴다. 셸 환경은 0단계 경우 A 와 같다(`env -i` + 내부 Jazzy + whitelist).
개발 확인은 **115 가 아닌 도메인**에서 한다(9/17 데모는 117. master01 의 `/clock` 이 115 에 간헐적으로 나온다). 띄우기 전에 그 도메인에서 `/clock` 발행자가 없는지 본다.
같은 기계에 다른 사람의 Isaac 이 돌 수 있다. 끄지 않는다.

**0. 자산·경로·도메인** — 경로는 현장 값으로 바꾼다(현장 확인 필요).

```bash
export P3_REPO=/absolute/path/to/ROKEY_P3_A3          # 이 브랜치를 체크아웃한 클론
export P3_WS_INSTALL=/absolute/path/to/install         # rokey_p3_manipulation 이 든 colcon install
export M0609=/absolute/path/to/isaacpjt/M0609          # 수업 자산
export P3_DOMAIN=117                                   # 호스트별 값: master01=117, master02=118 (결정 33)
git -C "$P3_REPO" rev-parse HEAD
sha256sum "$M0609/Collected_m0609_gripper/m0609_gripper.usd" "$M0609/rmpflow/m0609_description.yaml" "$M0609/doosan-robot2/urdf/m0609_isaac_sim.urdf"
# 위 "자산" 의 기준 값 세 줄과 같아야 한다
```

Isaac 실행 셸의 공통 앞부분(아래 명령들의 `…` 자리). **이 배열 방식이 정본이다.** 9/17 master02 실행은 `env -i` 를 풀어서 쳤다. 그 원문은 [master02-m0609-refill-stage.md](../docs/runbooks/master02-m0609-refill-stage.md)(#103)에 있다.

```bash
cd "$P3_REPO"
P3_ISAAC_ENV=(env -i HOME="$HOME" USER="$USER" TERM="$TERM" PATH=/usr/local/bin:/usr/bin:/bin
  ROS_DISTRO=jazzy RMW_IMPLEMENTATION=rmw_fastrtps_cpp ROS_DOMAIN_ID="$P3_DOMAIN"
  FASTRTPS_DEFAULT_PROFILES_FILE="$HOME/.ros/fastdds_whitelist.xml"
  LD_LIBRARY_PATH="$HOME/isaacsim/exts/isaacsim.ros2.bridge/jazzy/lib")
P3_ASSETS=(--robot-usd "$M0609/Collected_m0609_gripper/m0609_gripper.usd"
  --urdf "$M0609/doosan-robot2/urdf/m0609_isaac_sim.urdf"
  --robot-description "$M0609/rmpflow/m0609_description.yaml")
```

**1. selfdemo 물리 파지 한 바퀴(attach 없음)** — 이번 수정의 첫 확인.

```bash
"${P3_ISAAC_ENV[@]}" ~/isaacsim/python.sh sim/standalone/m0609_refill_stage.py --mode selfdemo --loop 1 \
  "${P3_ASSETS[@]}" 2>&1 | tee -i /tmp/p3-m0609-physics.log
echo "exit=${PIPESTATUS[0]}"
```

볼 줄(순서대로): `timeline_event`, `physics_ready`, `dof … type=rotation`, `mimic …`, `drive group=gripper …`, `friction bound=…`, `gripper_sweep …`, `gripper_close target=… source=sweep`, `selfdemo joint_space phase=to_shelf …`, `gripper_state tag=after_grasp …`, `selfdemo reached … phase=lift … grasp_verified=… lift_dz=…`, `cycle=1 slot=a canister_in_slot=… grasp_verified_at_lift=…`, `stop …`.
`grasp_verified_at_lift=False` 면 한 번에 하나씩 바꿔 다시 돌린다(판단): `--gripper-drive 1e5 1e3 50` → `--friction 1.5 1.5` → `--grip-squeeze 0.008` → `--gripper-close <gripper_sweep 표에서 고른 각도>`. 매번 로그를 남긴다.

**2. selfdemo 반복 데모** — 슬롯 A·B 번갈아, 무한 반복. 물리 파지가 안 되면 `--attach` 를 붙인다.

```bash
"${P3_ISAAC_ENV[@]}" ~/isaacsim/python.sh sim/standalone/m0609_refill_stage.py --mode selfdemo --loop 0 --loop-slots ab \
  "${P3_ASSETS[@]}" 2>&1 | tee -i /tmp/p3-m0609-loop.log
```

바퀴마다 `cycle=<k> slot=a|b canister_in_slot=… sim_s=…` 와 `respawn count=…`. 첫 두 바퀴에 `teach …` 줄이 slot_a·slot_b 로 나온다. 끝낼 때 Ctrl+C.

**3. ros 모드 기동과 토픽 확인**

```bash
"${P3_ISAAC_ENV[@]}" ~/isaacsim/python.sh sim/standalone/m0609_refill_stage.py --mode ros \
  --robot-usd "$M0609/Collected_m0609_gripper/m0609_gripper.usd" 2>&1 | tee -i /tmp/p3-m0609-ros.log
```

볼 줄: `timeline_event`, `physics_ready updates=…`, `ros topics …`. `physics_not_ready count=…` 가 나오면 몇 번·언제인지와 바로 앞의 `timeline_event` 를 보고한다.
`rclpy`·`sensor_msgs` import 에서 죽으면 수업 예제 주석대로 `PYTHONPATH=$HOME/isaacsim/exts/isaacsim.ros2.bridge/jazzy/rclpy` 를 `P3_ISAAC_ENV` 에 더해 한 번 더 돌리고 둘 다 보고한다(미확인).

다른 셸(시스템 Jazzy, `$P3_DOMAIN`, whitelist):

```bash
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=$P3_DOMAIN
ros2 topic info /m0609/joint_states -v          # 발행자 1, BEST_EFFORT
ros2 topic info /m0609/gripper/holding -v       # 발행자 1, RELIABLE
timeout -s INT 10 ros2 topic hz /m0609/joint_states
ros2 topic pub -w 1 --once /m0609/arm/joint_command sensor_msgs/msg/JointState \
  "{name: [joint_1], position: [0.3]}"
sleep 3; ros2 topic echo /m0609/joint_states --once --field position   # joint_1 이 0.3 근처인지
ros2 topic pub -w 1 --once /m0609/arm/joint_command sensor_msgs/msg/JointState \
  "{name: [joint_1, shoulder_pan_joint], position: [0.0, 0.0]}"          # Isaac 로그에 joint_command dropped
```

**4. waypoint 7개 티칭** — 아래 [teach 값 뽑기](#teach-값-뽑기). 손으로 고칠 때는 ros 모드로 띄운 채 관절 명령을 보내고 실제 값을 읽는다.

```bash
ros2 topic pub -w 1 --once /m0609/arm/joint_command sensor_msgs/msg/JointState \
  "{name: [joint_1, joint_2, joint_3, joint_4, joint_5, joint_6], position: [0.0, 0.0, 1.57, 0.0, 1.57, 0.0]}"
sleep 3; ros2 topic echo /m0609/joint_states --once --field position
```

**5. `m0609_arm` 으로 `Refill` 반복** — 3 의 Isaac(`--mode ros`)을 띄운 채 새 ROS 셸 둘. 도메인은 Isaac 과 같게(`export ROS_DOMAIN_ID=$P3_DOMAIN`).

```bash
source /opt/ros/jazzy/setup.bash && source "$P3_WS_INSTALL/setup.bash"
ros2 run rokey_p3_manipulation m0609_arm --ros-args --params-file /absolute/path/to/m0609_waypoints.yaml
```

파라미터 파일을 만드는 법은 [manipulation README](../src/rokey_p3_manipulation/README.md#m0609_arm) 를 따른다(팔 레인이 쓴다).

```bash
source /opt/ros/jazzy/setup.bash && source "$P3_WS_INSTALL/setup.bash"
ros2 action send_goal --feedback /m0609/refill rokey_p3_interfaces/action/Refill "{item_id: 'demo', slot: 0}"
```

기대: feedback `phase` 가 `to_shelf`, `grasp`, `lift`, `to_slot`, `insert`, `retreat` 순서, 결과 `success: true`, `lot_id: ''`(#99 뒤로 빈 값). `/events` 의 `REFILL_DONE` `detail` 은 `<item_id> slot <a|b>` 꼴이다(로트 없음). Isaac 로그의 `gripper close`/`gripper open`(와 `--attach` 면 `attach`/`release`).
실패 사유는 `m0609_arm` 로그에 있다([manipulation README](../src/rokey_p3_manipulation/README.md#m0609_arm) "실패"). 물리 파지로 `holding` 이 true 가 안 되면 3 을 `--attach` 로 다시 띄운다. 약통이 슬롯에 들어가고 그리퍼가 열린 뒤 `--respawn-delay-s` 가 지나면 `respawn` 줄과 함께 선반에 다시 놓이므로 같은 goal 을 반복해서 보낼 수 있다.
종료는 `m0609_arm` 과 Isaac 모두 각 터미널에서 Ctrl+C(SIGINT). 종료 줄과 `echo "exit=${PIPESTATUS[0]}"` 를 보고한다.

**보고할 것**: 0 출력, 1 로그(와 조정한 재실행), 2 의 바퀴 줄 몇 개와 `teach` 줄, 3 로그와 토픽 출력, 4 에서 쓴 값, 5 의 feedback·결과·`respawn` 줄·양쪽 로그. 관측과 판단을 나눠 적는다.

### teach 값 뽑기

`m0609_arm` 의 관절 waypoint 7개(`home_joint_positions`, `shelf_approach_joints`, `shelf_grasp_joints`, `slot_a_approach_joints`, `slot_a_insert_joints`, `slot_b_approach_joints`, `slot_b_insert_joints`, 각 6개 rad)를 selfdemo 로그에서 뽑는다.

1. **selfdemo 한 번 실행으로 7개 한 세트를 얻는다.** `--loop 2 --loop-slots ab` 로 돌리면 시작 때 `teach home_joint_positions=[…]`, 첫 바퀴에 `shelf_*`·`slot_a_*`, 둘째 바퀴에 `slot_b_*` 가 찍힌다(`--attach` 여도 값은 같다).
2. **다른 실행의 값과 섞지 않는다.** IK 는 현재 관절값에서 풀기 시작하므로 실행마다 같은 자세라도 다른 해가 나올 수 있다. 특히 **joint_6 은 2π 만큼 갈린다**(같은 손목 방향이 -3.78 과 2.50 처럼 찍힌다). 한 세트 안에서는 이어지는 값이지만, 세트를 섞으면 `m0609_arm` 이 waypoint 사이에서 손목을 한 바퀴 돌린다.
3. 배치(`--canister-xyz`, `--slot-xyz`, `--slot-b-xyz`, `--dispenser-height`)나 `--tool-yaw` 를 바꾸면 세트를 새로 뽑는다. 뽑은 실행의 커밋·인자·로그 경로를 값과 같이 남긴다.
4. `m0609_arm` 에 넘기는 법: [manipulation README](../src/rokey_p3_manipulation/README.md#m0609_arm) 참조.

### 원격으로 보기: livestream

기본은 꺼짐이다. 켜면 수업 예제 `7_pick_place_color.py` 의 `LIVESTREAM=1` 과 같게 한다: `SimulationApp` 을 headless 로 띄우되 `hide_ui` False, 창 크기 `--stream-width`×`--stream-height`(기본 1920×1080), 그 뒤 `--livestream-extension`(기본 `omni.kit.livestream.webrtc`)을 켠다.
`--livestream` 은 `--headless` 를 겸한다. 시작 줄 `livestream enabled=… extension=… size=…` 에 찍힌다. 위 명령에서 `--livestream` 을 더한다.

접속:
- 확장: master02 에 `omni.kit.livestream.webrtc-7.0.0`, `omni.kit.livestream.core-7.5.0`, `omni.kit.livestream.messaging-1.1.1`, `omni.services.livestream.nvcf-7.2.0` 넷 다 있다(9/17 master02). 수업 예제는 앞의 것, NVIDIA 5.1.0 `standalone_examples/api/isaacsim.simulation_app/livestream.py` 는 `omni.services.livestream.nvcf` 를 켠다. 어느 쪽이 붙는지는 **현장 확인 필요**.
- 클라이언트: 5.1 [livestream 클라이언트 안내](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/manual_livestream_clients.html)의 Isaac Sim WebRTC Streaming Client. 같은 네트워크에서 master02 IP 로 붙는다(같은 기계면 127.0.0.1). **현장 확인 필요**.
- 포트: 같은 안내가 UDP 47998, TCP 49100 을 연다고 적는다. Isaac 을 띄운 뒤 `ss -lunp | grep 47998; ss -ltnp | grep 49100`. **현장 확인 필요**.
- 제한(같은 안내): 인스턴스 하나에 클라이언트 하나, 스트리밍 방식도 하나. 같은 기계에 다른 사람의 Isaac 이 스트리밍 중이면 포트가 겹칠 수 있다(판단, 미관측).

### 확인할 가정

| 가정 | 상태 | 확인 방법 |
| --- | --- | --- |
| master02 자산이 dev01 과 같다 | 확인(9/17 sha256 일치) | 0 |
| dof 이름에 `joint_1` 부터 `joint_6` 과 `finger_joint` | 확인(9/17 dof count=12) | 1 의 `dof` 줄 |
| 드라이브 1e8 로 팔이 명령을 따라간다 | 확인(9/17 `tcp_error_m` 0.0002 이하, 슬롯 z 0.05 배치) | 1 의 `tcp_error_m` |
| `--attach` 로 넣기가 된다 | 확인(9/17 15:48, 슬롯 z 0.05 배치) | 2 에 `--attach` |
| mimic 이 `finger_joint` 를 따라간다 | 미확인 | 1 의 `gripper_state` 실제값과 expected |
| 그리퍼 드라이브·마찰·닫힘 목표로 물리 파지가 된다 | 미확인 | 1 의 `grasp_verified_at_lift` |
| 기본 배치(슬롯 z 0.15, 슬롯 B)가 도달 범위 안 | 미확인 | 2 에 `ik_failed` 없음, `tcp_error_m` |
| `to_shelf` 관절 공간 이동으로 `ik_failed` 가 없어진다 | 미확인 | 1 의 `selfdemo joint_space` 와 `ik_failed` 줄 |
| 재스폰(같은 prim 을 옮기고 속도 0)이 물리적으로 안정하다 | 미확인 | 2 의 다음 바퀴 `descend`·`grasp` |
| ros 모드가 기동 뒤 살아 있다 | 미확인(9/17 에는 죽었다) | 3 의 `physics_ready`·`timeline_event` |
| 오류 시 exit 코드가 1 이다 | 미확인 | 오류가 난 실행의 `exit=` |
| `/m0609/*` QoS 가 `m0609_arm` 과 맞는다 | 미확인 | 3 의 `topic info -v`, 5 |
| headless 에서 루프가 바로 끝나지 않는다 | 미확인(9/17 실행은 전부 창 모드) | `--headless` 로 1 |
| `--livestream` 확장·포트·클라이언트 접속 | 미확인 | "원격으로 보기" |

## 0.7단계: 조제실 스테이지

> **상태: 지난 기록 (2026-09-18 기준).** 지금은 [현행 절](#지금-무엇이-현행인가-v110-병원-한-바퀴)을 따른다.

`pharmacy_stage.py` 는 지금도 모든 preset 의 스테이지다. 이 절은 빈 월드 조제실(v1·v2) 시기의 기록이다.

`standalone/pharmacy_stage.py` 는 빈 월드에 조제실 한 칸을 세운다. 재범 지시(9/17): **약품 선반, 2축 레일 위 M0609, 조제기(보충 투입구·약 출구), 컨베이어**를 시나리오대로.
근거는 [시나리오](../docs/planning/scenario.md) 1절(조제실: 보관 선반·조제기·컨베이어, 문 밖 적재 위치)과 원안 그림(`docs/images/scenario-concept-v0.webp`)이다.
2축 레일은 9/17 재범 결정이고, 시나리오 문서에는 #101 에서 제안으로 반영됐다.

상태: v1 장면은 9/17 `f796210` 보충 3/3, 9/18 실습1·3·4·5 에서 돌았고, 장면 v2 는 실습6-8 에서 돌았다([단계 요약](#단계-요약), [실습별 확인](#실습별-확인-스테이지-쪽-요지)). pick_notice 는 9/17 `9d0a441` 에서 확인했다. `--ur5` 수정(`f796210`)·손 카메라 hz 는 미실행이다. dev01 에는 Isaac 이 없다.

### 배치 (기본값, 위에서 본 그림, 단위 m, 원점 = 레일 중심 바닥)

```text
        y
        ^            뒤 벽
  1.3 --+   +---------------------------+   +--------+
        |   | 약품 선반 랙 3단 x 5칸      |   | 조제기  |  출구 =>=>=>=>=>=>=>=>=>=>|벽|=> 적재 위치(복도)
  0.75 -+   | (칸마다 약통, 윗단 위 열림)  |   | 1.6 높이 |  벨트 윗면 0.75          |x=2.7|
        |   +---------------------------+   +--------+
  0.65 -+                                    [A][B] 보충 투입구(높이 0.85)
        |
   0.2 -+   ===========[ 캐리지 + M0609 ]===========   2축 레일 X ±1.2, Y -0.10..0.33(원점 y 0.30), 받침대 윗면 0.6
        |                                                                  |문| y=-0.6
        +---+-------------------------------+---------+----------------------+-----> x
          -1.3                             0.2       1.0                    2.7
```

| 부품 | 무엇 | 인자(기본) |
| --- | --- | --- |
| 약품 선반 랙 | 뒤판·옆판·선반판(윗단 위는 열림 — 위에서 집으려고), 칸마다 동적 약통 0.06×0.06×0.12. 집을 칸은 빨강 | `--shelf-origin`(-1.3 0.75 0), `--shelf-cols`(5), `--shelf-rows`(3), `--shelf-cell`(0.30 0.25), `--shelf-depth`(0.32), `--shelf-plinth`(0.30), `--room-canister-size`, `--pick-cell`(2 4, 윗단 오른쪽 끝) |
| 조제기 | 키 큰 캐비닛. 레일 쪽 면 선반에 보충 투입구 A(파랑)·B(초록, 위가 열린 칸), 복도 쪽 면에 약 출구 | `--dispenser-origin`(1.0 1.0 0), `--dispenser-size`(0.7 0.6 1.6), `--inlet-size`, `--inlet-height`(0.85) |
| 컨베이어 | 출구에서 시작해 벽 구멍을 지나 복도 적재 위치까지. Isaac 5.1 `isaacsim.asset.gen.conveyor` 의 `CreateConveyorBelt` 로 만든다(직접 물리 구현 없음) | `--belt-length`(1.6), `--belt-width`(0.25), `--belt-top`(0.75), `--belt-speed`(0.15) |
| 벽·문 | 조제실/복도 경계. 벨트 구멍과 사람용 문(AMR 은 들어오지 않는다) | `--wall-x`(2.7), `--door-y`(-0.6) |
| 2축 레일 | 바닥 X 트랙 + X 캐리지 + Y 캐리지(받침대). 직선 관절 `rail_x`·`rail_y` 와 M0609 가 한 articulation | `--rail-origin`(0 0.30 0) 또는 `--rail-origin-y`, `--retreat-back`(0.10), `--rail-x-stroke`(2.4), `--rail-y-limits`(-0.10 0.33), `--carriage-height`(0.6), `--rail-drive`(1e7 1e5 1e8, 우리 선택값), `--shelf-standoff`(= `--reach-offset`, 0.15 0.43), `--inlet-standoff`(0 0.40), `--carry-z`·`--retreat-z`(기본 계산값) |
| M0609 | `--robot-usd` 를 주면 받침대 위에 올린다. 수업 자산의 `root_joint` 를 월드 고정에서 Y 캐리지 고정으로 바꾸고 articulation root 를 레일로 옮긴다 | `--robot-usd`, `--robot-child`(m0609), `--arm-drive`(1e8 1e4 1e8) |

좌표·크기는 전부 임시다. 기본값은 두 실행을 섞은 것이다:
- 선반 쪽: 원점 y 0.30, 선반 약통에서 x 0.15·y 0.43 떨어져 선다(베이스 월드 y 0.48), 선반 높이 약통 윗면 + 여유(0.98 m). 9/17 세 실행(`4c07d8f` 원점 y 0.2 에서 `rail_y` 0.28, `7ae2879`·`3b114c4` 원점 y 0.30 에서 0.18)에서 첫 `rail_to_shelf` 가 늘 베이스 월드 y 0.48 에서 멈췄고(목표는 더 선반 쪽), 거기서 선반 단계는 전부 0.0007 m 안에 도달했다. 그래서 거기에 세운다. 멈춘 원인은 미확인이다: 레일 트랙은 원점과 함께 움직였는데 멈춘 월드 위치는 같았고, 캐리지 부품에는 충돌이 없다. `7ae2879` 2바퀴(팔이 다른 자세)는 0.09 m 더 갔다 — 홈 자세 팔이 선반에 닿는 것이 가장 그럴듯하다(판단).
- 투입구 쪽은 `d38a2c2` 값: 투입구 바로 앞 0.40 m(베이스 월드 위치가 `d38a2c2` 와 같다), 물러날 때도 운반 높이(1.10 m). 9/17 `7ae2879` 의 x 0.15·y 0.30 은 `above_inlet`·`insert` 가 6 cm 미달, `d38a2c2` 는 `insert` 0.0033 m 도달.
- `rail_y` 하한 -0.10(투입구 주차가 -0.05). 9/17 `7ae2879` 에서 하한 -0.33 일 때 캐리지가 y -0.25 까지 밀려 걸렸고 5000 N 으로 못 돌아왔다. 팔 단계 중 레일이 밀렸다: `7ae2879`(5e3) 0.12 m, `f796210`(5e4) 2바퀴에서만 `rail_y` 가 목표 -0.05 에서 하한 -0.10 까지, `retreat` 에서 `rail_x` 0.09 m(4바퀴는 안 밀림). 레일 목표는 팔 단계에서 매 스텝 다시 건다. 팔 드라이브(1e8 1e4 1e8)보다 한참 약해서 밀린 것으로 보고 기본을 1e7 1e5 1e8 로 올렸다(우리 선택값, 미확인). 2바퀴에서만 밀린 이유는 미확인 — 단계 시작 줄과 도달 줄의 `applied_rail_target=`·`arm=`(팔 6관절)로 바퀴끼리 비교한다.
- 운반 높이는 `raise` 에서만 올린다(선반 앞에서). 기본 칸과 투입구 A·B 의 모든 팔 목표가 어깨-플랜지 거리 0.85 m 안, 베이스 축에서 0.1 m 이상인지 테스트가 본다(거리 검사일 뿐 IK 아님, 어깨 높이 0.135 m 는 어림값). 윗단이라도 레일 X 끝을 넘는 칸(왼쪽 끝)은 축 가까이 서게 된다. **Isaac 에서 도달 여부는 확인하지 않았다.**

### 모드

- `--mode selfdemo`(기본): ROS 없이 배출 → 벨트 → 끝 정지 → `--pick-delay-s` 뒤 봉투 제거 → 다음 배출(`--loop`, 0 = 무한).
  `--robot-usd`·`--urdf`·`--robot-description` 이 있으면 **보충 반복**도 같이 돈다(`--refill-loop`, 0 = 무한): 레일로 선반 앞 이동 → 선반 앞 → 약통 위 → 내려가 잡기 → 들기 → 선반 앞으로 빼기 → 운반 높이로 올리기 → 레일로 투입구 앞 이동 → 투입구 위 → 넣기 → 놓기 → 물러나기 → 레일 원점 → 약통을 칸에 되돌림. 바퀴마다 투입구 A·B 번갈아.
  선반에는 앞쪽 지점(`--pull-margin`)을 거쳐 y 방향으로만 드나들고, 약통이 선반 밖일 때만 레일이 움직인다. 각 단계는 계획한 움직임 뒤 오차가 허용치 안이 되거나, `--phase-timeout-s` 에 계획 시간을 더한 만큼이 지나야 끝난다. 허용치는 레일 `--rail-tolerance`(0.01 m), 잡기·넣기 `--tcp-tolerance`(0.01 m), 지나가는 자세(위·들기·빼기·물러나기) `--via-tolerance`(0.03 m). 레일 목표는 관절 한계 0.02 m 안쪽으로 잡는다.
  `--mode ros --ros-refill-selfdemo` 면 ros 모드에서도 이 보충 반복을 스스로 돌린다(그동안 `/m0609/*` 명령은 무시). 어댑터 연결 시험에서 보충을 같은 화면에 보이려는 옵션이다. 리셋이 오면 사이클도 처음으로.
  `--mode ros --ros-pick-stand-in-s N` 이면 `POUCH_AT_END` 뒤 N sim s 에 봉투를 주차로 돌리고 벨트를 비운다(`ros pick_stand_in …`). 스텁 팔은 봉투를 실제로 집지 않으므로 이게 없으면 같은 epoch 의 두 번째 배출이 `belt_occupied` 로 거부된다. 기본은 꺼짐(진짜 UR5 가 집을 때).
  기본은 닫을 때의 상대 자세로 약통을 매 스텝 그리퍼 링크에 텔레포트한다(attach, prim 편집 없음). `--physics-grasp` 면 마찰로만 잡는다.
  줄: `rail drive joint=… stiffness=…`, `refill plan inlet=… shelf_rail=… inlet_rail=… above_canister=… above_inlet=… insert=… retreat=… rail_origin=… shelf_standoff=… inlet_standoff=… rail_y_limits=… rail_drive=…`(바퀴마다), `refill cycle=… phase=… kind=rail|tcp|hold target=… steps=… rail=… rail_target=… tcp=… tcp_target=… applied_rail_target=… arm=…`(단계 시작 때 실제값과 목표, 컨트롤러가 마지막으로 건 레일 목표, 팔 6관절), `refill reached|TIMEOUT … error_m=… extra_s=… rail=… canister=…`, `refill cycle=… canister_in_inlet=… sim_s=… next=…`, `refill respawn …`, `refill respawn_settled …`.
  봉투는 기동 때 `--pouch-pool`(8) 개를 바닥 주차 줄(`--parking-origin`)에 만들고 스폰·제거·리셋 모두 텔레포트한다(`pouch_pool …`, `spawn … pool_slot=…`, `pouch_parked …`).
- `--mode ros`: 위 [JSON 인터페이스](#isaac--ros-어댑터-인터페이스-json-v1) 6개 토픽. `--robot-usd` 가 있으면 0.5단계와 같은 `/m0609/joint_states`·`/m0609/arm/joint_command`·`/m0609/gripper/command`·`/m0609/gripper/holding`(이 스테이지에서는 항상 false) 과 레일 토픽 `/m0609/rail/joint_states`(S, `rail_x`·`rail_y`)·`/m0609/rail/joint_command`(R, position) 를 연다.
  **레일 토픽은 제안이고 계약 밖이다.** 계약 반영은 재범 결정으로 올라가 있다(추천안: 오케스트레이터는 보지 않고 팔 레인의 `m0609_arm` 이 구동).

첫 실행 실패를 한 줄로 보는 법: 준비 단계마다 `step=<이름> ok` 또는 `step=<이름> FAILED <예외>: <원인>` 이 찍힌다. 단계는 `build_room`, `build_rail_and_mount_robot`(참조한 로봇 prim, `root_joint`, ArticulationRootAPI 제거, body0 재연결, articulation root 가 하나인지까지 검사), `create_conveyor_belt`(그래프 prim·`Velocity` 변수 유무), `articulation_ready`(관절값을 못 읽으면 스테이지의 ArticulationRootAPI prim 목록), `refill_demo_ik`. 성공하면 `rail rewire robot_root=… schemas_before=… schemas_after=… body0=… articulation_roots=…` 한 줄이 함께 나온다.

### 재범 실습1 대응 (9/18)

실습1 = 9/18 10:05 master02 창 모드, sim `174bb6a` `--preset demo-ros`(보충은 스테이지 selfdemo). 재범이 본 문제 넷과 대응이다. 실습3 에서 P3·P4 는 재범 "괜찮다" 로 해소, P2 는 P7(조제기 앞면)로 이어져 실습4 에서 로그상 해소, P1 은 다시 보고되지 않았다(확인은 아님).

| | 관측 | 원인(판단 표시) | 한 것 |
| --- | --- | --- | --- |
| P1 약통이 들린 뒤 흔들림 | 재범 화면 | 잡힌 캐니스터는 동적 강체이고, 매 업데이트 **스텝 전에** 그리퍼 자세로 텔레포트하고 속도를 0 으로 둔다(코드 확인). 그 스텝 동안 중력(한 스텝에 약 2.7 mm)과 손가락 접촉이 캐니스터를 옮기고, 렌더된 프레임에는 그 자세가 한 업데이트 늦게 보인다(판단). | 무언가 잡혀 있으면 물리만 한 스텝(`update_fabric=True`) → 그리퍼의 새 자세로 텔레포트 → 렌더(`world.render()`, 물리 안 돎). 잡은 것이 없으면 전과 같다 |
| P2 기둥에 밀림 | 실습1 로그(master02): 매 바퀴 `insert`·`release` 에서 레일이 목표를 벗어났다. `insert` 는 `rail_y` 가 −0.05 에서 하한 −0.10 으로(a·b 모두), `release` 는 `rail_x` +5-15 cm(예: 553행 `rail=[1.0348, -0.1000]`, 1155행 cycle 11 `[1.1509, -0.1000]`). `retreat` 에서는 목표로 돌아왔다 | 후보(좌표): ① 투입구 테두리 — `above_inlet` 이 0.0258 m 오차(지나가는 자세 허용오차 0.03 안)로 끝난 뒤 내려가면 캐니스터(폭 0.06)가 안쪽(폭 0.08) 테두리에 닿는다 ② 투입구 벽 — `release` 에서 그리퍼가 투입구 안에서 열리며 손가락이 벽을 민다(x 밀림이 `release` 에서만 난다) ③ 선반 앞판(y 0.75) — 홈 자세 팔꿈치(첫 `rail_to_shelf` 가 베이스 y 0.48 에서 선다). 셋 모두 팔 드라이브(1e8)가 레일(1e5/5e4)보다 훨씬 세서 레일이 밀린다(판단). "기둥" 이 무엇인지는 재범에게 묻는 중 | 접촉 기록: 레일·M0609 링크와 선반 캐니스터에 `PhysxContactReportAPI`(기동 전 적용), `contact found|persist a=<prim> b=<prim> impulse=… at=[x,y,z] count=… sim_time=…`(쌍마다 처음과 이후 2 s 마다, 로봇 자기 링크끼리는 뺌). `--no-contact-log` 로 끈다 |
| P3 느림 → 최고 속도의 80% | 전 기본: TCP 0.0007 m/업데이트(≈0.04 m/s), 레일 0.2 m/s | "가능 최고 속도" 출처: 관절은 USD `maxVelocity`(실습1 로그 485-490행: 2.618, 2.618, 3.142, 3.927, 3.927, 3.927 rad/s) = 두산 M0609 사양(150/150/180/225/225/225 °/s). TCP 는 사양 1.0 m/s. 레일은 실물이 없어 USD 가 무제한이라 1.0 m/s 를 제안(2.4 m 행정 갠트리의 흔한 값, 판단) | `p3sim/motion.py`. 기본 = 80%: `--tcp-max-speed 0.8`, `--rail-speed 0.8`, `--joint-max-speed` 2.094/2.094/2.514/3.142/3.142/3.142. 단계 이동은 사다리꼴 가감속(`--tcp-accel`·`--rail-accel` 1.0 m/s², 사양 없음·우리 선택), IK 결과는 직전 명령 대비 관절 속도 상한으로 자른다. `--tcp-speed` 는 없앴다 |
| P4 1축으로 보임 | — | 코드는 처음부터 2축(`rail_x`·`rail_y`)이다. 보충 경로는 x 를 −0.10 → 0.94(a)/1.06(b) 로 1.0-1.2 m, y 를 0.18 → −0.05 로 0.23 m 쓴다(계획값). 다만 Y 쪽 부품이 바닥의 회색 판(높이 4 cm)이라 X 캐리지와 구분이 안 됐고, 두 축이 동시에 움직여 대각선 한 번으로 보였다(판단) | 보이게: X 트랙 노란색·높이 8 cm, X 와 같이 움직이는 **주황 Y 빔**(양쪽 트랙 위 트럭 포함), Y 빔 위를 움직이며 로봇을 싣는 **파란 Y 캐리지**. 전부 시각 부품(충돌 없음) |

실습1 종료 때 Ctrl-C 가 exit 1 로 끝났다("rclpy publisher context invalid", master02 관측). rclpy 가 기본으로 다는 SIGINT 처리기가 우리 루프보다 먼저 컨텍스트를 닫아, 다음 발행에서 예외가 난 것으로 본다(판단). 이제 `rclpy.init(signal_handler_options=SignalHandlerOptions.NO)` 로 우리 처리기만 쓴다(`rclpy init=no_signal_handlers` 줄, 0.5단계 스크립트도 같음). 실습3·4·5 모두 `exit=0` 이었다.

팔 노드(`--preset demo-ros-refill`)에도 같은 속도·가속을 보냈다(9/18): 관절 80% 2.094/2.094/2.513/3.142/3.142/3.142 rad/s(joint_3 은 코드 반올림이 2.514), 가속 4/4/4/6/6/6 rad/s², TCP 0.8 m/s·1.0 m/s², 레일 0.8 m/s·1.0 m/s².

### 조제실 장면 v2 (`--preset demo-ros-refill-v2`, 재범 9/18)

실제 시나리오에 가깝게 바꾼 장면이다. **치수는 전부 임시값**이고(`p3sim/layout_v2.py` `default_v2()`, 출처 "임시"), 세준 실제 USD 로 옮길 때 바뀐다. 기존 장면·preset(`demo-ros`, `demo-ros-refill`, `selfdemo-refill`)은 그대로이고 `--scene v2`(또는 새 preset)로만 켠다. v2 는 팔 노드가 구동한다(스테이지 selfdemo 보충 없음). 실습6(스테이지 단독)부터 실습8(오케스트레이터 + 웹)까지 돌았다([실습별 확인](#실습별-확인-스테이지-쪽-요지)).

- **레일 3축**: `rail_x` ±1.40, `rail_y` −0.10..0.33, **`rail_z` 0..1.10**(`--rail-z-limits`, 녹색 승강판. 팔 IK 가 위 선반 윗단 위 접근을 `rail_z` 0.40 에서만 풀어, 한계에 붙은 목표가 덜 가는 9/17 전례를 피해 0.20 m 여유를 둠). 베이스 = (`rail_x`, 0.30 + `rail_y`, 0.25 + `rail_z`)(v2 받침 0.25, 9/18 실습7-a 뒤). `/m0609/rail/*` 이름이 [`rail_x`, `rail_y`, `rail_z`] 가 된다(v1 장면에 `rail_z` 를 보내면 그 메시지는 통째로 버려진다).
- **선반 4개**(앞면 y 0.75, 깊이 0.32, 칸 0.30×0.30, 2열×2단): 바닥 `floor_left`(x −1.30..−0.70)·`floor_right`(x −0.60..0.00), 그 위에 `upper_left`·`upper_right`(바닥 z 1.15). 바닥 선반 첫 판(받침)은 z 0.55 — 약통 중심 z 0.61/0.91/1.24/1.54(9/18 재범 결정 a_plinth055, 아래). 위 선반 윗단만 위가 열려 있다(`access: top`), 나머지는 앞 접근(`front`).
- **약통 2종, 칸마다 하나(16개)**: 바닥 선반 = `cylinder`(지름 0.07, 높이 0.12, 품목 `drug-amox`), 위 선반 = `module`(x 0.06 × y 0.10 × z 0.14 세움, 품목 `drug-ibu`). 배정은 임시.
- **원형 수납통(round)**: 조제기 앞 받침판 위, 중심 (0.90, 0.56), 안지름 0.12(9/18 실습7-a5 뒤 0.10 에서 넓힘: 원통 0.07 이 놓기 1.3 s 전부터 벽에 닿았다, 팔 동의 — 한쪽 틈 1.5 → 2.5 cm, 레일 자세 불변. #198, 실습8 에서 이 값으로 돎), 안쪽 바닥 z 0.86, 테두리 z 0.98. 원통을 위에서 넣는다.
- **모듈 구멍(module)**: 조제기 앞면(y 0.70)에 입구 중심 (1.15, 0.70, 1.02), 열림 x 0.08 × z 0.16, 깊이 0.15, 넣는 방향 +y. 조제기 몸체를 구멍 둘레로 나눈 상자들(`DispenserFront*`)로 만든다.
- **팔 접근(9/18 팔 노드와 맞춤)**: 네 단 모두 **앞 접근**(공구 +y, 손가락 x 로 닫힘)으로 통일, 위 접근은 쓰지 않는다. 위에서 잡은 모듈은 닫힌 손가락 폭 ±0.053 이 구멍 ±0.04 보다 넓어 +y 로 넣을 수 없어서다. 원통은 윗면 3 cm 아래를, 모듈은 뒤쪽 절반(중심 3 cm 뒤)을 잡는다. `access` 필드는 칸이 위로 열려 있는지를 알릴 뿐이다.
- **판정**: 닫기 명령 틱에 TCP–약통 중심이 `--hold-distance`(0.08) 안인 가장 가까운 약통을 붙인다. 열 때 약통 중심이 수납통 안쪽 원기둥 안이면 `target=round`, 앞면을 넘어(절반 넘게) 구멍 단면 안이면 `module`, 아니면 `none`(`refill_ros released cell=… type=… target=…`). 놓고 `--respawn-delay-s`(2.0 sim s) 뒤 원래 칸으로 돌아간다 — 5분 연속 보충이 끊기지 않는다.
- **재고 토픽** `/m0609/shelf/inventory`(std_msgs/String JSON, reliable + transient local, depth 1): 기동·집힘·놓기·재배치 때 전체를 낸다. `items`(item_id → type), `rail`(이름·한계·베이스 원점), 칸마다 `cell`·`canister_id`·`item`·`type`·`access`·`present`·`pose.xyz`(약통 중심)·`size`, `targets`(round·module), `obstacles`(월드 축 정렬 `name`·`center`·`size` — 팔 #168 clearance 모델과 같은 꼴), `last_release`. 계약 v1 밖(팔 노드와 맞춘 제안).
- Isaac 없이 같은 JSON: `python3 sim/standalone/pharmacy_layout_json.py --scene v2`.
- 실습7-a(9/18, main `e558ee2` + 팔 v2, goal 6/6) 뒤 고친 것(#180, 실습7-a2 부터 "레일이 밀려" 0):
  - 레일이 밀림: 모듈 넣기에서 레일이 x 1.2000(한계)·z 0.4787(목표 0.576)로 튀었다가 돌아왔다(관측). 레일 드라이브(1e5/1e4/5e4)가 팔(1e8)보다 약하다고 보고(판단) v2 preset 만 (1e7, 1e5, 1e8)로 올렸다. 2b846f2 의 스테이지 기본과 같은 값이고, G-1 Isaac 비교는 없었다(우리 선택값). v1 preset 은 검증값 그대로다.
  - 한계 여유: 넣기 목표가 x 1.150(상한 1.20)·z 0.576(상한 0.60)이었다. v2 기본을 `rail_x` ±1.40(`--rail-x-stroke` 2.8, v2 에서만)으로 넓혔다. 칸·수납 좌표는 그대로다.
  - 베이스 높이: 재범 "집을 때 로봇 베이스가 약통 높이 근처·홈 자세보다 낮게, 최단 거리"(원문은 실습7-a 재관찰). 받침 0.60 으로는 베이스가 바닥 칸 약통(z 0.36)보다 낮아질 수 없어, v2 만 받침 0.25(`--carriage-height`, v2 에서만)와 `rail_z` 0..1.10(베이스 z 0.25..1.35)로 바꿨다(임시값). 재고 JSON `rail.origin` z 0.25. 레일 높이 선택은 팔 계획이 한다.
  - 로봇이 제 레일을 뚫고 지나감: 레일 캐리지 부품은 충돌이 없는 시각 부품이고, 로봇과 레일이 한 articulation 이라 self-collision 도 꺼져 있다. 그래서 물리로 막지 않고, 접촉 보고로도 안 보인다(코드 확인). 조치: (1) 재고 JSON `rail.parts` 에 레일 부품 상자(레일 0 일 때 월드 bbox, 옮기는 축 `moves`, `collision`)를 넣어 팔 계획이 피한다. (2) 스테이지가 12 업데이트마다 PhysX 겹침 질의로 레일 부품 상자와 로봇 충돌체의 겹침을 찍는다(`rail_overlap part=… robot=… rail=[x, y, z]`, 쌍마다 2 s, `--rail-overlap-every`). 물리 충돌은 켜지 않았다 — 켜면 팔이 레일에 걸려 멈출 수 있어 팔과 맞춘 뒤에 한다.
  - 정적 X 트랙(`RailXLeft`·`RailXRight`)도 `obstacles` 에 넣었다.
- 바닥 선반 받침 0.30 → 0.55(9/18 재범 결정, #188, 실습7-a4 16칸 계획 16/16): 팔 계획기 탐색(여유 1 cm, 레일 한계 5 cm, bbox 보수적)에서 바닥 선반 아랫단 4칸(약통 z 0.36)은 앞 접근 자세가 전수에서도 없었다(link_2 가 선반판·옆판·승강판에 걸림). 후보(받침 0.50·0.55, 칸 높이 0.36, 승강판 0.20, 조합) 중 받침을 올린 두 안만 16/16 이었고, 0.55 는 모든 칸이 레일 한계에서 0.10 m 넘게 떨어진다(`rail_z` 최대 0.99). 위 선반도 0.25 올라간다(바닥 z 1.15). 수납·레일·v1 은 그대로다. 선반이 떠 있거나 틈이 없는지(옆판·뒤판이 바닥부터, 위아래 선반 판·테두리가 맞닿음) 테스트로 묶었다.
- 실습7-a2(9/18, main `1828bfe`, goal 4/4, 레일 밀림 0) 뒤 고친 것(#183, 7-a3 부터 기둥이 있다. 떠 보이지 않는지는 재범 화면 확인 대기): 재범 "M0609가 공중부양을 하잖아....". 받침(높이 0.16)은 x·y 만 따라가고 rail_z 를 따라가는 것은 승강판(0.04)뿐이라, 팔이 쓴 rail_z 0.44-0.95 에서 로봇과 판이 받침 위 0.4-0.9 m 허공에 떠 보였다(master02 수치). 승강 가이드 대신 **승강 기둥**(`LiftColumn`, 0.16×0.16, 길이 = `rail_z` 상한 + 0.02)을 승강판 밑에 붙였다. 판과 함께 오르내리며 어느 `rail_z` 에서도 받침 윗면부터 판 아랫면까지 빈틈이 없다(테스트: z 0·0.55·1.10). 낮은 `rail_z` 에서는 나머지가 받침 안과 바닥 아래로 들어간다. 재고 JSON `rail.parts` 에 `LiftColumn`(moves x·y·z)이 들어가고 `LiftGuide` 는 빠졌다.
- 실습6(9/18, main `6f59377`, v2 단독 창 모드) 뒤 고친 것(#175, 실습7-a 부터 들어감. 줄무늬·선반 구분은 재범 화면 확인 대기):
  - 받침대 무지개 줄: 녹색 승강판 윗면과 회색 받침대 윗면이 `rail_z` 0 에서 둘 다 z 0.60 인 겹친 면(z-fighting)으로 봤다(판단). v2 에서만 받침대를 판 두께 0.04 만큼 짧게 했다.
  - 링크 visuals 경고: 9/17-9/18 Kit 로그를 모으니 실행마다 인스턴스 visuals 하나에 대한 경고 한 쌍이 나오고, 대상이 대개 link_2 이지만 가끔 그리퍼 `right_outer_knuckle` 이었다(같은 코드, master02 로그 집계). 너클 메시에는 GeomSubset 이 없다. 그래서 "GeomSubset 메시" 가 아니라 Fabric 의 인스턴스 채우기 경합으로 보고(판단), 로봇 아래 **모든** instanceable `visuals`(팔·그리퍼)를 첫 앱 업데이트 전에 푼다(`link_visuals made non-instanceable count=… parts=…`).
  - 재범 실습6 화면 답: 선반 네 개가 "이어진 1개의 직사각형 선반" 으로 보였다. 그래서 선반마다 색을 달리하고(바닥 왼쪽·오른쪽 회색 두 톤, 위 왼쪽·오른쪽 나무색 두 톤), 선반마다 앞면에 어두운 테두리(양옆 기둥 + 위·아래 가로대, 시각 부품, 충돌·장애물 목록 없음)를 둘렀다. 바닥 선반 윗 가로대와 위 선반 아래 가로대가 z 0.90 에서 만나 경계선이 된다. 칸 좌표·장애물은 그대로다(`pharmacy_layout_json.py` 출력이 main `6f59377` 과 바이트 단위로 같음, 팔 teach 불변). 약통 색은 정상이었고(원통 노랑, 모듈 보라), 회색 캡처는 캡처 방식 탓이었다(master02).
  - `omni.hydra … MF0609_2_1/Scene/mesh update topology/point without updating normal, fallback to smooth normal`: 인스턴스를 푼 뒤 한 번 나온다. 메시에 법선은 저작돼 있다(master02 자산 읽기). 모양은 같고 음영만 달라질 수 있는 알림으로 본다(판단, 조치 없음).

### 시연용 카메라 (`--view`)

#195·#197. 실습7-a5 에서 세 뷰 모두 떴다(첫 overview 값, 그 뒤 #197 로 바꿈). 실습7-a4(9/18) 캡처에서 Kit 기본 카메라가 방 밖(복도 벽 +x·선반 뒤 +y 쪽)에 있어 로봇·선반이 벽에 가려 거의 안 보였다. 선반·조제기·원형 수납통·모듈 구멍이 모두 −y 쪽으로 열려 있으므로 카메라를 방 안 −y 쪽, 팔이 닿지 않는 곳에 둔다. 벽 숨김은 넣지 않았다(이 시점들에서는 시선이 벽을 지나지 않는다 — 테스트).

| `--view` | 보이는 것 | v2 눈 → 바라보는 점 |
| --- | --- | --- |
| `overview`(v2 preset 기본) | 로봇이 일하는 곳: 16칸 약통과 윗단 위 그리퍼(+0.45), 팔이 쓰는 레일 자세마다 로봇 외곽(베이스 ±0.30 m, 높이 +0.80 m), 캐리지 x 이동 전 구간, 원형 수납통·모듈 구멍. 60° 화각에서 가장 가깝게(재범 7-a4 "로봇이 작업하는 것을 잘 보이는 각도와 줌"). 바닥의 트랙 끝·받침 아래는 화면 밖 | (0.0, −2.53, 2.17) → (0.0, 0.75, 1.10) |
| `shelves` | 선반 넷(집는 칸) | (−0.65, −2.3, 1.55) → (−0.65, 0.90, 0.90) |
| `bins` | 원형 수납통·모듈 구멍(v1: 투입구 A/B) | (0.55, −0.90, 1.60) → (1.00, 0.65, 0.95) |
| `none` | Kit 기본 그대로 | — |

- 기본은 `none` 이고 `--preset demo-ros-refill-v2` 만 `overview` 다. v1 값도 있다(`p3sim/views.py`). `world.reset()` 뒤 한 번 `/OmniverseKit_Persp` 에 적용하고 `viewport view=… eye=… target=…` 을 찍는다. 그 뒤로는 사람이 마우스로 돌려도 된다. 실패하면 `viewport view=… failed …` 만 찍고 계속한다.
- 값은 우리가 정한 것이다. 테스트는 기본 카메라 화각(가로 60°, 16:9)을 가정해 다음을 본다: 눈이 방 안(복도 벽 앞, 벽 높이 아래)에 있는지, 모든 상자에서 0.2 m 밖인지, 팔이 닿는 범위(레일 y 하한 − 0.9 m) 밖인지, 시선이 벽을 지나지 않는지, 각 시점의 대상 점이 화면 안에 드는지(overview: 약통·그리퍼·수납 목표·캐리지 이동 끝·팔 레일 자세(#190 표)마다 로봇 외곽 — 실습7-a5 에서 모듈 넣기(레일 x 1.30) 때 팔이 화면 밖으로 나갔다, shelves: 선반 모서리, bins: 수납 목표).
- **발표 화면 반반(재범 9/18: 왼쪽 Isaac, 오른쪽 관제 웹)**: `--window-half left`(오른쪽은 `right`, 화면 크기 `--screen-size 1920 1080`)는 Isaac 창을 화면 절반(960×1080, x 0)에 두고, 렌더 해상도도 창과 같게 해 16:9 로 잘려 작아지지 않게 한다. 근거(Isaac Sim 5.1.0 `simulation_app.py`): `window_width`·`window_height` → `--/app/window/width|height`, `width`·`height` → `--/app/renderer/resolution/*`, `extra_args` 는 그 뒤에 붙는다. 위치 `/app/window/x|y` 와 저장된 크기 `/persistent/app/window/*`(`saveSizeOnExit` 기본 켬)는 omni.appwindow 설정이다. 창 관리자가 위치를 무시할 수 있다(미실행). 그러면 GNOME 에서 Isaac 창을 누르고 `Super+←`, 웹 창은 `Super+→` 로 반씩 둔다.
- 세로로 긴 창에서의 화면(판단, 문서 근거): 렌더러는 정사각 픽셀이라 세로 aperture 를 가로 aperture 와 이미지 비율로 정한다(Isaac Sim 5.1 `isaacsim.sensors.camera` 문서). 그래서 960×1040 창에서도 가로 60° 는 그대로이고 위아래가 더 보인다. 테스트는 세 시점을 16:9 와 960:1040 두 비율에서 본다. 기동 때 `viewport camera resolution=… fill_frame=… focal=… h_aperture=… v_aperture=…` 줄로 master02 의 실제 값을 확인한다.
- 실습7-a5 캡처의 "승강판 옆 비스듬한 회색 막대"는 레일 부품이 아니라 수업 자산 `base_link` 메시(`MF0609_0_0`)의 일부다(모양으로 케이블로 본다, 판단). usd-core 로 읽은 것: 폭 2-3 cm, 베이스 중심에서 −y 로 0.34 m, x −0.11 까지, 아래로 z −0.045 까지 내려간다. 충돌 메시도 같은 범위다. 자산을 고치지 않으므로 그대로 둔다. 레일 부품은 모두 축 정렬 상자다.

### 재범 실습3 대응 (9/18)

실습3 = 9/18 master02 창 모드, sim `7cd4b90`(main `eda7cb4` 와 실행 코드 같음). A = `--preset selfdemo-refill` 4바퀴, B = `--preset demo-ros-refill` + 팔 노드. 확인된 것: 속도(한 바퀴 64 s → 28 s, 재범 "괜찮다"), 레일 모양(재범 "괜찮다"), Ctrl-C exit 0, B 에서 팔 노드가 `/m0609/refill` 보충 성공. 새 문제 셋과 대응이다(#162. 실습4 에서 조제기 touch 0·보충 3/3, P6 은 #167·#175 뒤 실습6 에서 해소).

| | 관측(master02) | 원인(판단 표시) | 한 것 |
| --- | --- | --- | --- |
| P6 로봇 중간이 잘림 | Kit(omni.fabric) 경고 `getAttributeCount/getTypes called on non-existent path …/link_2/visuals/MF0609_2_1/Scene`(9/17 부터). 자산 읽기: `link_2/visuals` 는 instanceable 이고 `MF0609_2_1/Scene/mesh` 는 **있다**. 링크 메시 중 유일하게 GeomSubset 이 둘(재질 둘)이다 | Fabric 이 instance proxy 아래 GeomSubset 메시를 못 찾아 link_2 가운데가 안 그려진다(판단) | 기동 때 링크의 `visuals` 가 instanceable 이고 GeomSubset 메시를 품으면 **우리 스테이지 레이어에서만** non-instanceable 로 바꾼다(`link_visuals link_2/visuals made non-instanceable …`). 자산 파일은 안 건드린다. 시각 gprim 이 아예 없는 링크는 다음 링크 원점까지 회색 원통을 붙인다(`link_visuals gprims=…`). usd-core 로 작은 가짜 장면에서 동작 확인(Isaac 아님) |
| P7 기둥에 밀림 | 접촉 기록: 선반판·선반 옆판 쌍은 전부 impulse 0, 접촉점이 면보다 약 0.1 m 앞. **impulse 가 난 쌍**: A 에서 `link_4`↔`DispenserBody` 최대 540.6, `link_5`↔`DispenserBody` 최대 431.3(at y 0.69-0.70 = 조제기 앞면, z 1.23-1.35, 매 바퀴 `above_inlet`·`insert`), B 에서 `link_4`↔`DispenserBody` 10.0 | "기둥" = **조제기 몸체 앞면**(키 1.6 m 캐비닛)으로 본다(판단). 투입구가 앞면에 붙어 있어(중심 y 0.65, 앞면 0.70) 손목(link_4·5)이 앞면을 친다. 선반 쪽은 contact offset 안의 근접 보고(충돌 아님)로 본다 | 투입구를 앞면에서 `--inlet-gap` 0.07 m 띄웠다(중심 y 0.65 → 0.58, 받침판은 앞면까지). 투입구 앞 베이스 거리 0.40 → 0.33 m 로 레일 주차는 그대로(`rail_y` −0.05). 접촉 줄에 `touch\|near`(impulse>0 또는 sep≤1 mm 면 touch)와 `sep=`, 기동 때 충돌체 contactOffset·restOffset 분포(자산에는 authored 값 없음 — master02) |
| TIMEOUT(`above_inlet`, 매 바퀴) | error 0.034-0.035 m(허용 0.03), 끝 자세가 매 바퀴 같고 `joint_3` 0.115-0.117 rad(팔이 거의 펴짐), TCP 가 목표보다 y 3 cm 짧다 | 도달 한계: 베이스에서 0.40 m 앞·0.5 m 위는 팔을 다 펴도 약 3 cm 모자란다(판단). 80% 속도와는 무관하게 끝 자세가 같다 | 위 P7 과 같은 수정으로 수평 거리 0.40 → 0.33 m. 허용오차는 그대로 |

선반 쪽 teach 는 그대로다. 투입구 쪽 직교 목표는 위 표(ROS 구동 절)가 새 값이고, 팔 노드 쪽에 같은 값을 보냈다.

### ROS 로 레일+M0609 구동 (`--preset demo-ros-refill`)

재범 결정(9/18): 9/21 시연의 보충 장면은 오케스트레이터 `/m0609/refill` 이 레일 위 M0609 를 구동한다. 레일은 `/m0609/refill` 안에 숨기고 계약 v1 은 바꾸지 않는다. 팔 노드(`src/` manipulation)가 아래 토픽으로 명령하고, 스테이지는 명령을 따르며 잡힘만 판정한다. 9/18 팔 노드 쪽과 맞춘 내용이다. 실습3-B·4·5 에서 보충 2/2·3/3·2/2 로 돌았다. 장면 v2 도 같은 토픽에 `rail_z` 와 재고 토픽이 더해진 꼴이다([장면 v2](#조제실-장면-v2---preset-demo-ros-refill-v2-재범-918)).

| 토픽 | 방향 | 타입 | QoS | 내용 |
| --- | --- | --- | --- | --- |
| `/m0609/joint_states` | Isaac → | `sensor_msgs/JointState` | best effort, volatile, depth 5 | 30 Hz(sim 기준 스케줄). `name` = `joint_1`..`joint_6` **팔 6개만**(그리퍼·레일 없음), `position` rad, `velocity` rad/s, `header.stamp` = sim 시간 |
| `/m0609/rail/joint_states` | Isaac → | `JointState` | 같음 | 30 Hz. `name` = `rail_x`, `rail_y`, `position` m(관절 0 = 레일 원점, 월드 (0, 0.30, 0)), `velocity` m/s. **계약 v1 밖** |
| `/m0609/arm/joint_command` | → Isaac | `JointState` | reliable, volatile, depth 10 | `name`·`position` 짝(순서 무관, 일부만 가능). 모르는 이름·길이 불일치면 통째로 버리고 `joint_command dropped reason=…`. 드라이브 목표로 **바로** 들어간다(보간 없음, 팔 드라이브 1e8/1e4/1e8) — 궤적 점을 촘촘히 보낸다 |
| `/m0609/rail/joint_command` | → Isaac | `JointState` | 같음 | `rail_x`·`rail_y`(하나만도 됨), m. 드라이브 목표 직행. 한계 `rail_x` ±1.20, `rail_y` −0.10..+0.33(USD 관절 한계). 팔 노드가 0.2 m/s·20 Hz(점 간격 1 cm)로 보간한다(팔 노드 쪽 답). **계약 v1 밖** |
| `/m0609/gripper/command` | → Isaac | `std_msgs/Bool` | reliable, depth 10 | true = 닫기(`finger_joint` 목표 0.8 rad), false = 열기(0.0) |
| `/m0609/gripper/holding` | Isaac → | `Bool` | reliable, volatile, depth 1 | 30 Hz(joint_states 와 같은 틱). 아래 잡힘 판정 |

`/m0609/arm/at_home` 은 팔 노드가 낸다. 스테이지는 명령 도착을 판정하지 않는다(판정은 팔 노드가 joint_states 로).

잡힘·들어감(스테이지 판정, 물리 파지 아님):
- **잡힘**: 닫기 명령이 들어온 틱에 TCP(`link_6` 원점 + `link_6` z 방향 0.19671 m)와 선반 캐니스터 중심의 거리가 `--hold-distance`(0.08 m) 이하면 캐니스터를 `link_6` 에 붙인다(매 스텝 텔레포트로 따라감). 붙어 있는 동안 `holding=true`. 멀면 안 붙고 `refill_ros grasp miss distance=…`.
- **들어감**: 열기 순간 캐니스터 중심이 투입구 a·b 내부 공간(바깥 0.10×0.10×0.12, 벽 0.01, 바닥 위)에 있으면 `refill_ros released inlet=a|b`, 아니면 `inlet=none`. 토픽은 없다 — 팔이 holding 과 자세로 REFILL_DONE 을 판단한다(팔 노드 쪽 답).
- **되돌림**: 열고 `--respawn-delay-s`(2.0 sim s) 뒤 캐니스터를 선반 칸으로 순간이동(`refill_ros respawn …`). 선반 캐니스터는 1개(`--pick-cell` 2 4)이고 a·b 둘 다 이것으로 보충한다.
- `/isaac/sim/reset` 때 붙은 것 해제, 팔 홈, 레일 (0, 0), 캐니스터 제자리(계약 6절 2).
- 줄: `refill_ros on canister=… home=… grip_link=… tcp_offset=… hold_distance=… respawn_delay_s=…`, `refill_ros grasp attached|miss …`, `refill_ros released inlet=… respawn_in_s=…`, `refill_ros respawn …`.

teach(직교 목표, 코드 계산값 — `plan_rail_refill` 과 인자 기본값, `f796210` 에서 보충 3/3·창 모드 6/6 이 된 기하와 같다). 좌표 월드 m. 베이스(`base_link`) 월드 = (`rail_x`, 0.30 + `rail_y`, 0.60), 회전 없음. TCP 자세는 `link_6` z 아래(wxyz (0, 1, 0, 0)). 캐니스터 선반 중심 (0.05, 0.91, 0.86), 투입구 a (0.94, **0.58**, 0.91), b (1.06, **0.58**, 0.91) — 9/18 실습3 뒤 조제기 앞면에서 0.07 m 띄웠다(아래 실습3 절, 전에는 y 0.65).

| 단계 | 레일 (`rail_x`, `rail_y`) | TCP 월드 | TCP 베이스 기준 | 그리퍼 |
| --- | --- | --- | --- | --- |
| `rail_to_shelf` | (−0.10, 0.18) | — | — | 열림 |
| `shelf_front` | 〃 | (0.05, 0.63, 0.98) | (0.15, 0.15, 0.38) | 열림 |
| `above_canister` | 〃 | (0.05, 0.91, 0.98) | (0.15, 0.43, 0.38) | 열림 |
| `descend`·`grasp` | 〃 | (0.05, 0.91, 0.87) | (0.15, 0.43, 0.27) | 닫기 |
| `lift` | 〃 | (0.05, 0.91, 0.98) | (0.15, 0.43, 0.38) | 닫힘 |
| `pull_out` | 〃 | (0.05, 0.63, 0.98) | (0.15, 0.15, 0.38) | 닫힘 |
| `raise` | 〃 | (0.05, 0.63, 1.10) | (0.15, 0.15, 0.50) | 닫힘 |
| `rail_to_inlet` a / b | (0.94, −0.05) / (1.06, −0.05) | — | — | 닫힘 |
| `above_inlet` | 〃 | (x, 0.58, 1.10), x = 0.94 / 1.06 | (0.00, 0.33, 0.50) | 닫힘 |
| `insert`·`release` | 〃 | (x, 0.58, 0.935) | (0.00, 0.33, 0.335) | 열기 |
| `retreat` | 〃 | (x, 0.48, 1.10) | (0.00, 0.23, 0.50) | 열림 |
| `rail_home` | (0.00, 0.00) | — | — | 열림 |

- selfdemo 허용오차: 레일 0.01 m, 잡기·넣기 TCP 0.01 m, 지나가는 자세 0.03 m.
관절값(실측, **투입구 쪽 행은 9/18 실습3 뒤 투입구를 옮겨 더 이상 맞지 않는다** — 선반 쪽 행만 유효): master02 9/18 10:05 창 모드, sim `174bb6a` `--preset demo-ros`(selfdemo 보충, 레일 드라이브 1e5/1e4/5e4), 로그 `master02:~/markle_tmp/demo18_stage.log` → `teach_raw_174bb6a.txt`. 각 단계 reached 줄의 `rail=`·`arm=`(joint_1..6 rad). cycle 1 = a, cycle 2 = b, 둘 다 TIMEOUT 0·`canister_in_inlet=True`.

| 단계 | 레일 실측 | joint_1..6 | 그리퍼 |
| --- | --- | --- | --- |
| 홈(`arm ready home=`) | (0, 0) | 0.0000, 0.0000, 1.5883, 0.0000, 1.5778, 0.0000 | 열림 |
| `shelf_front` | (−0.1001, 0.1800) | 0.7549, −0.2835, 1.3782, 0.0021, 2.0468, −2.3855 | 열림 |
| `above_canister` | (−0.1000, 0.1801) | 1.2216, 0.3235, 0.7561, −0.0006, 2.0612, −1.9202 | 열림 |
| `descend` | (−0.1002, 0.1799) | 1.2210, 0.2241, 1.2033, 0.0010, 1.7148, −1.9206 | 열림 |
| `grasp` | (−0.0998, 0.1799) | 1.2218, 0.2235, 1.2032, 0.0020, 1.7165, −1.9193 | 닫기 |
| `lift` | (−0.1000, 0.1801) | 1.2217, 0.3225, 0.7596, −0.0005, 2.0591, −1.9201 | 닫힘 |
| `pull_out` | (−0.1000, 0.1799) | 0.7567, −0.2835, 1.3781, −0.0011, 2.0469, −2.3859 | 닫힘 |
| `raise` | (−0.1000, 0.1800) | 0.7556, −0.0831, 0.8153, 0.0008, 2.4087, −2.3856 | 닫힘 |
| `above_inlet` a | (0.9400, −0.0497) | 1.5179, 0.5039, −0.0019, −0.0001, 2.6313, −1.6241 | 닫힘 |
| `insert` a ⚠ | (0.9444, −0.1000) | 1.5658, 0.2456, 0.9860, −0.0009, 1.9024, −1.5751 | 닫힘 |
| `release` a ⚠ | (1.0348, −0.1000) | 1.7650, 0.2740, 0.9515, 0.0003, 1.9093, −1.3760 | 열기 |
| `retreat` a | (0.9400, −0.0500) | 1.5498, 0.1378, 0.5843, 0.0006, 2.4181, −1.5915 | 열림 |
| `above_inlet` b | (1.0600, −0.0497) | 1.5178, 0.5034, −0.0007, 0.0005, 2.6307, −1.6236 | 닫힘 |
| `insert` b ⚠ | (1.0659, −0.1000) | 1.5688, 0.2457, 0.9860, −0.0013, 1.9020, −1.5728 | 닫힘 |
| `release` b ⚠ | (1.0607, −0.1000) | 1.5850, 0.2464, 0.9872, −0.0010, 1.9010, −1.5571 | 열기 |
| `retreat` b | (1.0600, −0.0500) | 1.5500, 0.1371, 0.5875, 0.0006, 2.4161, −1.5913 | 열림 |

- ⚠ `insert`·`release` 는 레일이 목표 (x, −0.05)에서 `rail_y` 하한 −0.10 까지(a 의 `release` 는 `rail_x` 1.0348 까지) 밀린 상태에서 팔이 IK 로 보상한 값이다. 레일을 목표에 두고 이 관절을 주면 TCP 가 약 5 cm(a `release` 는 x 9 cm) 어긋난다. `above_inlet` 관절에서 직교 목표로 IK 하는 것을 권한다(판단).
- 밀림 원인 후보(판단, 미확인): `above_inlet` 이 지나가는 자세 허용오차(0.03 m) 안의 0.0258 m 오차로 끝난 뒤 곧장 내려가 캐니스터(폭 0.06)가 투입구 안쪽(폭 0.08) 테두리에 닿는다. 팔 드라이브(1e8)가 레일(5e4)보다 훨씬 세서 레일이 밀린다. 팔 노드는 `above_inlet` 을 5 mm 안으로 맞춘 뒤 내려가길 권한다.
- 그 밖의 단계는 레일이 목표의 1 cm 안이다. cycle 2 의 선반 쪽 값은 cycle 1 과 소수 셋째 자리까지 같다.
- 주의(판단): 레일이 선반 주차(`rail_y` 0.18)에 있을 때 팔을 홈으로 되돌리면 선반 앞에 닿을 수 있다(그 홈 자세로 선반 쪽 레일 이동이 베이스 y 0.48 에서 막혔다). 레일을 먼저 홈으로 보내려면 팔을 `raise` 자세로 둔다.

### 봉투 QR 텍스처 (`--qr-dir`)

계약 7절: QR 내용 = 주문 ID(`ord-NNNN`), QR 이미지는 주문 풀로 만들고 생성 스크립트는 simulation 소유다.

```bash
# 시스템 Python(OpenCV 가 있는 셸). 산출물은 Git 밖(sim/outputs/ 는 무시 대상)
python3 sim/standalone/make_qr_textures.py --order-pool src/rokey_p3_orchestrator/config/order_pool.yaml --out sim/outputs/qr
```

- 인코더는 OpenCV `QRCodeEncoder`(오류 정정 M, 여백 4 모듈, 512 px), OpenCV 가 없으면 `qrcode` 패키지. 파일마다 OpenCV 로 다시 읽어 `decode=ok` 와 sha256 을 찍는다. 9/17 dev01 에서 OpenCV 5.0.0(scratch venv)으로 주문 4개 모두 `decode=ok` 를 확인했다(Isaac 아님).
- 스테이지: `--qr-dir sim/outputs/qr --order-pool …` 이면 기동 때 풀 봉투마다 윗면(+z)용 텍스처 사각형을 만든다. 사각형은 봉투 큐브의 자식이 아니라 `QrFaces/Qr_NN` 형제 prim 이고(UsdGeom 은 gprim 아래 gprim 을 지원하지 않는다) 매 스텝 봉투 자세로 옮긴다. 주문을 차례로 배정해 주문마다 여러 장이 생기고, 배출 때 그 주문 봉투를 먼저 꺼낸다. 맞는 봉투가 없으면 다른 봉투를 쓰고 `qr_mismatch …` 를 찍는다. 텍스처는 실행 전에만 만든다(실행 중 USD 편집 없음).
- 판독 거리·해상도(`qr_min_size_px`)는 manipulation 레인 실측 대상이다. 봉투 0.10×0.07 에 QR 이 0.8 비율(약 0.056 m)이다.
- **주문 풀을 바꿀 때**(9/20 정적 확인): 스테이지 `--order-pool` 에는 launch 의 `order_pool_file`(`P3_ORDER_POOL`)과 같은 파일을 준다. 다르면 새 주문이 `unknown_order` 로 거부된다. `--qr-dir` 을 쓰면 새 풀로 PNG 를 다시 만든다(라벨을 붙일 주문의 `<order_id>.png` 가 없으면 기동 때 `missing …; run make_qr_textures.py` 로 실패한다).
  - 주문 수가 `--pouch-pool`(기본 8) 이하여야 주문마다 라벨 봉투가 한 장 이상 생긴다. 넘으면 명령줄로 `--pouch-pool` 을 올린다(preset 에 없는 인자).
  - 봉투 수는 주문 수가 아니라 동시에 밖에 나가 있는 봉투 수로 정한다(스텁 경로 1개, `--ur5` 최대 6개).

### 벨트 끝 UR5 (`--ur5`)

복도 적재 위치(벨트 끝)에 **고정 받침대 위 UR5** 와 상판 칸 N 개를 둔다. 계약의 Ridgeback_UR5(도킹한 AMR 의 팔)를 대신하는 것이고 이동 베이스는 없다. 전부 라이브러리 부품이다.
- 로봇: Isaac 5.1 기본 자산 `Isaac/Robots/UniversalRobots/ur5/ur5.usd`(`get_assets_root_path()` 기준, [5.1 로봇 자산 목록](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/assets/usd_assets_robots.html)). 자산 서버에 못 닿으면 `--ur5-usd` 로 로컬 경로. 같은 목록에 `Clearpath/RidgebackUr/ridgeback_ur5.usd` 도 있다(미사용).
- IK: `isaacsim.robot_motion.motion_generation` 에 들어 있는 UR5 Lula 설정(`load_supported_lula_kinematics_solver_config("UR5")`, 끝단 프레임 `tool0`, cspace `shoulder_pan_joint` 부터 `wrist_3_joint`). Lula 프레임 이름은 USD prim 이름과 별개다.
- 끝 prim(흡착·카메라 부착): 9/17 master02 에서 5.1 `ur5.usd` 에는 `tool0` prim 이 없고 `flange`·`ft_frame` 이 있었다. 그래서 `tool0` → `flange` → `ft_frame` → `wrist_3_link` 순으로 찾고 `ur5 end_link=…` 를 찍는다. `flange` 면 ur_description 의 `tool0 = flange × rpy(π/2, 0, π/2)`(원점 같음)로 카메라 방향을 맞춘다. `ft_frame`·`wrist_3_link` 의 회전은 모르므로 항등(미확인)으로 둔다.
- 받침대 고정: 9/17 `3b114c4` 에서 `tool0` 정기구학과 끝 prim 자세가 같은 (0.80, 0.21, 0.27) 이었다(받침대 3.25, 0.55, 0.45). 자산의 월드 고정 관절(body0 비어 있음)이 작성된 월드 위치(원점)를 붙잡아 UR5 가 원점에서 시뮬레이션된 것으로 본다(판단, 미확인). 기동 때 그런 관절의 `localPos0` 에 받침대 위치를 더하고 `ur5 world_joints count=… …` 로 찍는다. 준비 때 `tool0` 이 받침대에서 1.2 m 넘거나 `base_link` 가 받침대에서 5 cm 넘게 떨어지면 `ur5 base_frame_mismatch` 를 찍는다.
- TCP 읽기: 보간 시작점과 오차는 Lula 정기구학(`compute_end_effector_pose`, `tool0`)으로 잡는다. 9/17 `7ae2879` 에서 끝 prim 자세로 잡은 시작점이 (0.30, 0.73, 0.45) 로 읽혀(받침대는 x 3.25) 모든 보간 목표가 `ik_failed` 였다. 끝 prim 이 instance proxy 라 자세가 틀리게 읽힌 것으로 본다(판단). 준비 때 `ur5 tcp_source fk_tool0=… end_prim=… difference_m=…` 로 둘을 같이 찍는다. 속도는 `--ur5-tcp-speed`(0.003 m/update, 보충 팔의 `--tcp-speed` 와 별개).
- 도구: 흡착. 계약 2.1 `/amr_1/gripper/command` 가 "true = 닫기(흡착)" 이다. 켤 때 봉투 중심이 TCP 에서 `--suck-distance`(0.04 m) 안이면 봉투가 `tool0` 을 매 스텝 텔레포트로 따라간다(prim 편집 없음).
- 배치(임시, 도달 계산만): 받침대 윗면 (3.25, 0.55, 0.45), 상판 칸 5개 중심 (3.30, 0.05, 0.45) 에서 x 로 0.16 간격, 칸 0.14×0.11×0.04. 벨트 끝 봉투까지 수평 약 0.59 m, 칸까지 약 0.5-0.62 m.
- selfdemo: 봉투가 끝에 서면 위 → 표면 접촉 → 흡착 → 들기 → 칸 위 → 내리기 → 떼기 → 물러나기 → 대기 자세, 칸 1 부터 차례로. 5칸이 차면 봉투를 주차 줄로 되돌리고 칸 1 부터 다시. 줄: `ur5 pick …`, `ur5 phase=…`, `ur5 reached|TIMEOUT …`, `ur5 suction on|miss|off …`, `pouch picked_by=ur5 …`, `ur5 placed deck_slot=… in_slot=…`, `ur5 deck full …`.
- ros(**`--mode ros` 에서만**, selfdemo 에서는 `/amr_1/*` 를 내지 않는다): `/amr_1/joint_states`(S 30 Hz), `/amr_1/arm/joint_command`(R), `/amr_1/gripper/command`(R, true = 흡착), `/amr_1/gripper/holding`(H 10 Hz). **계약과 다른 점: `joint_states` 는 UR5 6개만 싣는다**(계약은 dummy 베이스 3개 + UR5 6개, 이 스테이지에는 베이스가 없다). 계약 관절 이름이 USD 이름과 같은지는 미확인이다.
- 봉투 풀 기본은 8 개(칸 5 + 벨트 위 1 + 여유).
- **손 카메라·TF**(`--no-hand-camera` 로 끔): `tool0` 아래 USD 카메라(`--camera-offset` 0.06 0 0, `--camera-focal-mm` 18, `--camera-resolution` 640×480)와 OmniGraph 한 개. 노드는 5.1.0 기본 노드 그대로: `IsaacCreateRenderProduct` → `ROS2CameraHelper`(rgb)·`ROS2CameraInfoHelper`, `ROS2PublishTransformTree` 둘.
  - 토픽 `/amr_1/hand_camera/image_raw`·`camera_info`, 프레임 `amr_1/hand_camera_optical`(REP 103, 카메라 prim 아래 x 축 180° 회전한 자식), QoS best effort depth 2, `frameSkipCount` 로 렌더 60 Hz 에서 10 Hz(계약 "10 Hz 이하"). 해상도는 QR 판독 거리 실측 전이라 임시값이다. 9/17 `7ae2879` 창 모드에서 1280×720 은 2.855 Hz 였다(기본을 640×480 으로 내림, 미실행).
  - `/tf`: 부모 `amr_1/base_link`, 자식 UR5 링크 6개·찾은 끝 prim(`amr_1/flange` 등)·`amr_1/hand_camera_optical`. `/tf_static`: `amr_1/deck_slot_1` 부터 `amr_1/deck_slot_5`. 프레임 이름은 prim 의 `isaac:nameOverride` 속성으로 붙인다(5.1.0 `PoseTree.h`). `map`·`odom` 은 내지 않는다(계약 3절).
  - 계약과 다른 점: TF 끝 프레임은 찾은 USD prim 이름이다(5.1 `ur5.usd` 면 `amr_1/flange`). 계약 3절의 로봇 링크 이름과 맞추는 일은 이 받침대 단계에서 하지 않는다 — 세준 씬의 UR5 가 기준이 된다.
  - 계약과 다른 점: 계약은 `amr_1/base_link` 의 부모 `amr_1/odom` 을 base_driver 가 낸다. 이 스테이지에는 AMR 이 없어 `amr_1/base_link` 가 트리 뿌리로 남는다. 받침대 UR5 의 `base_link` 가 곧 `amr_1/base_link` 다.
  - 카메라·TF 준비가 실패하면(예: UR5 링크가 instance proxy 라 자식·속성을 못 붙임) `ur5 camera_and_tf disabled reason=…` 을 찍고 UR5 는 계속 돈다. UR5 자산을 못 받으면(자산 서버 시한 기본 10 s 뒤 오류, 또는 참조에 `base_link`·`tool0` 없음) `ur5 disabled reason=…` 을 찍고 UR5 없이 계속한다. 종료 줄에 `render_products=` 와 `ur5=on|off`.
  - 줄: `step=ur5_camera_and_tf ok`, `ur5 sensors camera=… resolution=… rate=10.0Hz(skip 5) topics=… frame=… tf_parent=… tf_dynamic=8 tf_static=5`.

### 시연 때 띄우는 명령 (`--preset`)

사람이 runbook 대로 띄울 때 인자 실수를 줄이려고 이름 붙인 묶음을 둔다. preset 은 **인자 기본값만** 바꾸고, 명령줄에 적은 인자가 순서와 상관없이 이긴다. 스테이지의 첫 로그 줄(Isaac 앱 시작 전)이 `[pharmacy_stage] preset=<이름|-> resolved_args={…}` 이다. 로그만 보고도 어떤 값으로 떴는지 알 수 있다.

| preset | 바뀌는 기본값 | 용도 |
| --- | --- | --- |
| `demo-ros` | `--mode ros --ros-refill-selfdemo --ros-pick-stand-in-s 5 --refill-loop 0`, `--rail-drive 1e5 1e4 5e4` | 어댑터 연결 시연. 보충 반복이 같은 화면에서 돌고, pick_notice 가 안 오면 5 sim s 뒤 봉투를 치운다 |
| `demo-ros-refill` | `--mode ros --ros-pick-stand-in-s 5`, `--ros-refill-selfdemo` **끔**, `--rail-drive 1e5 1e4 5e4` | 오케스트레이터 `/m0609/refill`(팔 노드)이 레일+M0609 를 토픽으로 구동하는 시연. 아래 [ROS 로 레일+M0609 구동](#ros-로-레일m0609-구동---preset-demo-ros-refill) |
| `selfdemo-refill` | `--mode selfdemo --loop 0 --refill-loop 0`, `--rail-drive 1e5 1e4 5e4` | ROS 없이 배출·벨트·보충 반복 무한 |
| `demo-ros-refill-v2` | `--mode ros --ros-pick-stand-in-s 5 --scene v2 --view overview`, `--rail-drive 1e7 1e5 1e8`, v2 파생 `--rail-x-stroke 2.8 --carriage-height 0.25` | 장면 v2 시연(9/18 실습6-8). 팔 노드가 구동. 아래 [장면 v2](#조제실-장면-v2---preset-demo-ros-refill-v2-재범-918) |
| `hospital-v2` | `demo-ros-refill-v2` 전부 + `--pharmacy-origin 0.25 10.5285421018 0 0`, `--base-deactivate`(지금 코드 47)·`--base-rigid-off`(지금 코드 19) 목록. `--base-usd` 는 따로 준다 | 세준 병원 씬 위 장면 v2(재범 결정 9/18). 위 [병원 씬 위에 조제실 얹기](#병원-씬-위에-조제실-얹기-이식-준비-isaac-미실행) |
| `hospital` | 위 [현행 절](#지금-무엇이-현행인가-v110-병원-한-바퀴)의 표. 그 밖의 preset 은 [preset 과 기본값](#preset-과-기본값) 표 | 병원 한 바퀴(현행). `P3_WORLD=hospital tools/demo_v2.sh up` 이 띄운다 |

기하 값(선반·투입구 standoff, 운반 높이, `rail_y` 한계)은 9/17 master02 에서 보충 3/3 을 확인한 `f796210` 의 기본값 그대로다. v1 preset 의 `--rail-drive` 는 `f796210` 값으로 고정했다. `2b846f2` 의 더 강한 값은 v1 에서 비교(G-1)가 돌지 않았다. v2 preset 은 그 강한 값을 쓰고 실습7-a2 부터 레일 밀림이 0 이다. 자산 경로·주문 풀·도메인은 현장 값이라 preset 에 넣지 않는다.

```bash
# 어댑터 시연(0.5단계 절차 0 의 P3_REPO·P3_ISAAC_ENV·P3_ASSETS)
"${P3_ISAAC_ENV[@]}" ~/isaacsim/python.sh sim/standalone/pharmacy_stage.py --preset demo-ros \
  --order-pool "$P3_REPO/src/rokey_p3_orchestrator/config/order_pool.yaml" "${P3_ASSETS[@]}" \
  2>&1 | tee -i /tmp/p3-demo-ros.log

# ROS 없는 보충 반복
"${P3_ISAAC_ENV[@]}" ~/isaacsim/python.sh sim/standalone/pharmacy_stage.py --preset selfdemo-refill "${P3_ASSETS[@]}" \
  2>&1 | tee -i /tmp/p3-selfdemo-refill.log

# 장면 v2 시연(팔 노드는 팔 레인 runbook 대로 따로 띄운다)
"${P3_ISAAC_ENV[@]}" ~/isaacsim/python.sh sim/standalone/pharmacy_stage.py --preset demo-ros-refill-v2 \
  --order-pool "$P3_REPO/src/rokey_p3_orchestrator/config/order_pool.yaml" "${P3_ASSETS[@]}" \
  --kit-log-file ~/markle_tmp/kit-v2-$(date +%H%M%S).log --kit-log-verbose \
  2>&1 | tee -i /tmp/p3-demo-ros-refill-v2.log

# 띄운 값 확인(python.sh 가 앞에 다른 줄을 찍을 수 있어 grep)
grep -m1 'preset=' /tmp/p3-demo-ros.log
```

### master02 절차 (0.7단계)

0.5단계 절차 0 의 `P3_REPO`·`M0609`·`P3_ISAAC_ENV` 를 그대로 쓴다. **도메인만 이 기계 값인 `export P3_DOMAIN=118` 로 바꾼다**(결정 33: master01=117, master02=118).

```bash
# 1. 방만(로봇 없음): 선반·조제기·벨트·벽이 보이고 봉투가 벨트를 타고 끝에 서는지
"${P3_ISAAC_ENV[@]}" ~/isaacsim/python.sh sim/standalone/pharmacy_stage.py --mode selfdemo --loop 3 \
  2>&1 | tee -i /tmp/p3-pharmacy-room.log

# 2. 레일 위 M0609 보충 반복(레일 이동 → 선반 칸 집기 → 투입구 넣기, 무한)
"${P3_ISAAC_ENV[@]}" ~/isaacsim/python.sh sim/standalone/pharmacy_stage.py --mode selfdemo --loop 0 --refill-loop 0 \
  "${P3_ASSETS[@]}" 2>&1 | tee -i /tmp/p3-pharmacy-rail.log

# 2b. 벨트 끝 UR5 가 봉투를 상판 칸에 놓기(보충 반복과 함께)
"${P3_ISAAC_ENV[@]}" ~/isaacsim/python.sh sim/standalone/pharmacy_stage.py --mode selfdemo --loop 0 --refill-loop 0 --ur5 \
  "${P3_ASSETS[@]}" 2>&1 | tee -i /tmp/p3-pharmacy-ur5.log

# 2c. 보충 기하 조합(코드 수정 없이 값만 바꿔 여러 번). 비교는 refill plan 줄과 단계 시작 줄의 rail/tcp 실제값
#   A 기본(혼합)            : 추가 인자 없음
#   B 투입구 더 뒤·더 높이   : --inlet-standoff 0 0.45 --carry-z 1.15 --rail-y-limits -0.15 0.33
#   C 7ae2879 투입구 값 재현 : --inlet-standoff 0.15 0.30 --retreat-z 1.03   (강한 레일 드라이브에서 여전히 미달인지)
"${P3_ISAAC_ENV[@]}" ~/isaacsim/python.sh sim/standalone/pharmacy_stage.py --mode selfdemo --loop 0 --refill-loop 3 \
  "${P3_ASSETS[@]}" <조합 인자> 2>&1 | tee -i /tmp/p3-pharmacy-rail-<A|B|C>.log

# 3. ros 모드(어댑터 없이 JSON 직접 확인)
"${P3_ISAAC_ENV[@]}" ~/isaacsim/python.sh sim/standalone/pharmacy_stage.py --mode ros \
  --order-pool "$P3_REPO/src/rokey_p3_orchestrator/config/order_pool.yaml" \
  --robot-usd "$M0609/Collected_m0609_gripper/m0609_gripper.usd" 2>&1 | tee -i /tmp/p3-pharmacy-ros.log
```

3 을 띄운 채 다른 셸(시스템 Jazzy, `ROS_DOMAIN_ID=$P3_DOMAIN`):

```bash
ros2 topic echo /isaac/pharmacy/belt --once
ros2 topic pub -w 1 --once /isaac/pharmacy/dispense_request std_msgs/msg/String \
  "{data: '{\"order_id\":\"ord-0001\",\"request_id\":\"r001-0001\",\"v\":1}'}"
ros2 topic echo /isaac/pharmacy/dispense_response --once
timeout -s INT 30 ros2 topic echo /isaac/events
ros2 topic pub -w 1 --once /isaac/sim/reset_request std_msgs/msg/String "{data: '{\"epoch\":2,\"v\":1}'}"
ros2 topic echo /isaac/sim/reset_response --once
ros2 topic pub -w 1 --once /m0609/rail/joint_command sensor_msgs/msg/JointState "{name: [rail_x], position: [0.8]}"
sleep 5; ros2 topic echo /m0609/rail/joint_states --once --field position
```

볼 줄: `step=… ok`(FAILED 면 그 한 줄), `room shelf_cells=15 …`, `rail built …`, `rail rewire …`, `dof … name=rail_x …`, `arm ready …`, `spawn index=… order_id=… xyz=…`, `event {"…DISPENSED…"}`, `belt note=stop_belt`, `event {"…POUCH_AT_END…"}`, `refill cycle=… canister_in_inlet=…`, `reset begin/done`, `stop … rtf=…`.

### 확인할 가정

| 가정 | 확인 방법 | 9/18 기준 |
| --- | --- | --- |
| `CreateConveyorBelt` 로 만든 벨트가 봉투를 옮긴다 | 1 의 `event … POUCH_AT_END` 와 화면 | 확인: 9/17 이송 5.85-5.88 sim s, 실습1 트립 완주 |
| 끝 구역에서 속도 0 으로 바꾸면 봉투가 벨트 위에 선다(떨어지지 않는다) | `belt note=pouch_left_belt` 가 없다 | 9/17 리셋 30회·실습1 에서 `POUCH_AT_END` 뒤 치움이 반복됐다. `pouch_left_belt` 보고 없음 |
| 레일 관절 재연결(수업 자산 `root_joint` → Y 캐리지)로 articulation 이 하나로 잡힌다 | 2 의 `dof` 줄에 `rail_x`·`rail_y` 와 `joint_1`-`joint_6` | 확인: 9/17 `f796210` 보충, v2 는 `rail_z` 까지(실습6) |
| 레일 드라이브 값으로 캐리지가 목표에 선다 | 2 의 `rail reached … actual=…` 가 target 근처 | v1 9/17 확인(밀림은 위 기록). v2 는 실습7-a2 부터 "레일이 밀려" 0 |
| 받침대 0.6 위 M0609 가 선반 윗단·투입구에 닿는다 | 2 에 `refill ik_failed` 가 없고 `refill reached … error_m` 이 작다 | 확인(v1): `f796210` 3/3, 실습3-5. v2 는 받침 0.25 + `rail_z`, 16/16(7-a4) |
| 레일이 움직이는 동안 Lula IK 가 로봇 베이스 위치를 따라간다(매 스텝 `set_robot_base_pose`) | 2 의 tcp 단계 `error_m` | 확인(v1 selfdemo): `f796210` 보충 3/3 |
| attach 로 약통이 투입구에 들어간다 | 2 의 `canister_in_inlet=True` | 확인: 9/17 `canister_in_inlet=True` 3/3, v2 는 `target=round|module`(7-a4-8, `none` 0) |
| JSON 토픽 QoS·내용이 표와 같다 | 3 의 echo 출력 | 확인: 9/17 어댑터 WARN 0 |
| `get_assets_root_path()` 로 UR5 자산을 받는다(마스터의 네트워크) | 2b 의 `step=build_ur5_cell ok`, 아니면 `--ur5-usd` | 확인: 9/17 `7ae2879` `build_ur5_cell` ok |
| UR5 자산의 dof 이름이 Lula UR5 cspace 와 같고 끝단이 `tool0` 이다 | 2b 의 `step=ur5_ready ok` 와 `dof` 줄 | 끝단은 `tool0` 이 아니라 `flange`(9/17). 준비는 ok |
| 받침대 0.45 위 UR5 가 벨트 끝과 칸 1-5 에 닿는다 | 2b 에 `ur5 ik_failed`·`ur5 TIMEOUT` 이 없고 `ur5 placed … in_slot=True` | 미확인(집기 `ik_failed`) |
| QR 텍스처가 봉투 윗면에 보이고 손 카메라 이미지에서 읽힌다 | `--qr-dir` 로 띄워 화면 확인, pouch_detector 의 `tag_reads` | 미확인 |
| 손 카메라 이미지가 10 Hz 이하 rgb8 로 나온다 | `ros2 topic hz /amr_1/hand_camera/image_raw`, `ros2 topic echo /amr_1/hand_camera/image_raw --once --field encoding` | 9/17 1280×720 에서 2.855 Hz. 640×480 은 미실행 |
| TF 프레임 이름이 `amr_1/…` 로 나온다(`isaac:nameOverride`) | `ros2 run tf2_ros tf2_echo amr_1/base_link amr_1/hand_camera_optical`, `ros2 topic echo /tf_static --once` | 확인: 9/17 `tf2_echo amr_1/base_link amr_1/hand_camera_optical` 나옴 |
| 리셋이 타임라인을 멈추지 않는다 | 3 의 로그에 `timeline_event type=STOP` 이 없다(0.5단계 진단 줄) | 9/17 리셋 30회 ABORT 0. 그동안 STOP 보고 없음 |

## 향후 ROS Bridge 실행기

센서·로봇 토픽을 더할 때도 위 내부 Jazzy 라이브러리 방식 또는 Python 3.11로 빌드한 custom package 방식 중 하나를 쓴다.
Isaac 프로세스에 domain·RMW·DDS 파일 경로를 전달하고 실제 읽힌 설정을 확인한다.
`~/.bashrc`에 값이 있다는 사실만으로 GUI·서비스·컨테이너의 환경 적용을 보장할 수 없다.

`sim/outputs/`는 추적하지 않는 로컬 산출물 자리다.
공유할 실측은 [evidence](../evidence/README.md)의 원본 보존·manifest·리뷰 흐름을 따른다.

공식 자료 확인일: **2026-09-15**(씬 로드), **2026-09-17**(0단계 `/clock`). 0단계 `/clock` 은 9/17 master02 에서 돌았다([단계 요약](#단계-요약)). 씬 로드 smoke(`tests/test_stage_loads.py`)의 현장 실행 기록은 evidence·docs 에서 찾지 못했다.

## AMR 합본 (`--amr-combined`) — 오늘 회차로 알게 된 것

> **상태: 지난 기록 (2026-09-21 기준).** 지금은 [현행 절](#지금-무엇이-현행인가-v110-병원-한-바퀴)을 따른다.

합본 구성은 지금 병원 한 바퀴에서도 쓴다. 손목 그리퍼는 [amr_gripper](assets/amr_gripper/README.md)다. 아래의 "오늘" 은 9/21 이다.

"AMR 합본" 은 공식 `ridgeback_ur5.usd`(Ridgeback + UR5 한 몸)를 쓰는 구성이다. 상자 베이스 + 받침대 UR5
구성과 대비되는 말이다(재범 9/21: 상자로 한 시험은 뜻이 없다).

```bash
~/isaacsim/python.sh sim/standalone/pharmacy_stage.py \
    --preset emptyworld-loop --amr --amr-combined <ridgeback_ur5.usd 절대경로> \
    --sim-sensors --order-pool <절대경로> --duration 300
```

경로는 기계마다 다르므로 기본값이 없다. 인자를 안 주면 상자 베이스 그대로다(기본 동작 불변).
자산 파일명은 바꾸지 않는다 — naming.md 가 외부 자산명을 유지해 출처를 추적한다.

### 1. 이 자산은 **앵커가 아니라 프림 이동**이 먹는다

로봇을 어디에 놓느냐는 방법이 셋이고 **자산마다 먹는 것이 다르다.**

| 방법 | 이 자산 | 받침대 UR5 자산 |
| --- | --- | --- |
| 프림 이동(`AddTranslateOp`) | **먹는다** | 안 먹었다 |
| 앵커 `localPos0`(`body0` 가 빈 관절) | 안 먹는다 | **먹었다** |
| 초기화 뒤 `set_world_pose` | 마지막 수단 | 마지막 수단 |

회차 둘이 이것을 갈랐다: 프림·앵커에 **같은** (x, y) 를 줬는데 결과가 두 배가 아니라 한 번만 적용됐고,
그다음 회차에서 **앵커 z 만** 올렸더니 몸체가 1 mm 도 안 올라갔다.
→ **둘 다 같은 값으로 준다.** 어느 쪽이 먹든 결과가 같고, 다른 값을 주면 두 배가 되거나 어긋난다.

### 2. 충돌 메시가 링크 원점 **아래로** 내려간다 — `ground_lift`

`base_link` 의 bbox 바닥이 **−0.0262** 다(바퀴). z 를 0 으로 두고 놓으면 지면에 박히고,
`sep=-0.0259 impulse=2.19e6` 의 마찰이 prismatic 구동을 붙잡아 **주행 명령에 전혀 안 움직인다.**
`ground_lift()` 가 런타임 bbox 로 재서 그만큼 + `GROUND_CLEARANCE` 를 올린다.

상자 베이스에는 같은 이유로 이미 `GROUND_CLEARANCE` 가 있었다 — **자산 경로에 옮기는 것을 빠뜨린 것이다.**

### 3. "한 일" 과 "결과" 를 따로 찍는다 — `amr base_pose`

```
amr ground_lift bottom=-0.0262 clearance=0.03 lift=0.0562     ← 한 일
amr base_pose pos=(4.6, 0.55, 0.0562) expected_z_at_least=0.03 ← 결과
```

앵커를 올린 회차에서 **몸체가 안 올라갔는데** 로그에는 "올렸다" 만 있었다. 둘을 따로 안 찍어서
회차를 하나 더 썼다. 놓는 방식이 자산마다 다르므로 **결과를 재서 남긴다.**

### 받침대 셀에 달려 있던 것들

합본은 받침대 UR5 셀(`ur5_cell`)을 만들지 않는다 — 합본이 자기 팔을 들고 오므로 둘 다 만들면 팔이 둘이 된다.
그런데 셀에 달려 있던 것이 같이 빠진다. 지금까지 옮긴 것:

| 셀에 있던 것 | 합본에서 | 안 옮겼을 때의 증상 |
| --- | --- | --- |
| 흡착·`gripper/holding` | `amr_base.Suction` | 팔이 봉투까지 가고 **집히지 않는다.** 터지지 않는다 |
| 로봇 링크 TF | `amr_base.publish_tf` | `놓을 곳 TF 없음: amr_1/deck_slot_1` 로 ⑤에서 닫힌다 |
| 놓을 자리 | `amr_base.build_tray_on_base` | 놓을 자리가 없다 |
| 손목 카메라 | **안 옮겼다**(v0 은 시뮬 센서를 쓴다) | — |

**두 번 같은 실수를 했다.** 새 구성을 만들 때는 "안 만드는 것에 무엇이 달려 있었나" 를 먼저 세는 편이 낫다.

### 팔은 뒤끝, 반대쪽 끝은 트레이 (9/21 재범 확정안)

상판 다섯 칸을 없애고 **칸막이 없는 트레이 하나**로 바꿨다. 팔은 몸체 뒤끝(`base_link` 로컬 x −0.35)
으로 가고 그 밑에 **0.15 올리는 낮은 받침**이 선다. `deck_slot_N` 은 트레이 **안의 고정된 놓을 자리**로
남는다 — 계약·`target_slot`·결정 28/44·zones·팔 매개변수는 하나도 안 바뀐다.

**어느 끝에 다느냐는 취향이 아니라 기하가 정했다.** 적재 자리에서 벨트는 AMR 로컬 −x 쪽(−0.60)이다.
팔을 +x 끝에 달면 봉투까지 0.95 로 사거리(0.85) 밖이고, −x 끝에 달면 0.25 로 너무 가깝다.
그래서 **팔은 −x 끝이고, 정차 자리를 그만큼 앞으로 민다**(`layout.ARM_MOUNT_SHIFT_X`).
그러면 팔 밑동의 **월드 자리가 옮기기 전과 같아져** 도달·자세 계산이 전부 그대로 살아 있다 —
`load` 는 (3.40, 0.95) → (3.75, 0.95), 침상 정차는 보관함 x + 0.35.

받침이 하는 일은 dz 를 줄이는 것이다. 9/21 검증: 벨트 `sin|q3|` 0.967 → 0.999·뻗은비율 86 → 78 %,
보관함 0.912 → 0.988·92 → 85 %. **판 높이(0.129)와 올림량(0.15)은 다른 값이다** — 자산의 밑동(0.28)이
몸체 윗면(0.301)보다 0.021 아래라 그만큼 짧다. 같다고 쓰면 판이 밑동을 뚫는다(`riser_height`).

덤으로 얻은 것: 칸막이가 없어져 **상판 자기 충돌 쌍이 사라진다** — lap3 에서 위팔이 3번 칸 벽에
sep 0.010 으로 막혔던 그 형상이다. 대신 봉투가 트레이 안에서 미끄러질 수 있고, 그건 돌려 봐야 안다.
그래서 `in_slot` 이 받는 상자도 벽이 아니라 **자리 간격**(0.18)이 정한다(`layout.TRAY["slot_accept"]`).

**미확인**: 실물 장착 자리와 문 통과 높이(받침이 서면 팔 어깨가 0.519 다). 물리 거동은 master02 회차에서 본다.

### 프레임

- `amr_1/ur_arm_base_link` — 원점은 **어깨에서 `d1`(0.089159) 내린 자리**(자산이 정한 것, 재서 넣는다),
  축은 **`Rz(pi)`**(UR URDF `base_link` 관례). 어깨 프레임이 `Rz(pi + pan)` 인 것을 세 자세로 확인했다.
- 부모는 **`amr_1/base_link`** 다. `map →` 은 계약 3절에 **받침대 조합에서만**으로 적혀 있다.
- `wrist_3_link` 와 팔 기구학 끝점(`tool0`)은 **항등**이다 — 표준 URDF 의 `d6 = 0.0823` 이 아니다.
  자세 세 벌로 역산해 확인했다. **추측했으면 8.2 cm 를 틀렸다.** 자산이 바뀌면 다시 재야 한다.

## 병원 조제실 자동 인수 검토

[병원 조제실 문서](standalone/hospital-workcell.md)는 `--workcell-layout` 입력 준비와 9/22 보충 실습 명령을 다룬다.
같은 문서의 `hospital_workcell_demo.py`(#484/#485 배치·자동 인수 데모)는 opt-in 시각 시험이며 ROS/물리 보충 경로와 별개다.
