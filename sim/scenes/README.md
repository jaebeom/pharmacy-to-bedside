# scenes — 장면 식별·앵커·hospital_main 실측

> **상태: 지난 기록 (2026-09-22 기준).** 지금은 [sim README 현행 절](../README.md#지금-무엇이-현행인가-v110-병원-한-바퀴)을 따른다.
> 지금 병원 한 바퀴의 씬은 [`hospital_navigationv1.usda`](hospital-navigation-v1-changes.md)다. world 원점은 0 이다(`--preset hospital`, `pharmacy_origin` 0).
> 앵커는 `hospital_navigationv1.anchors.json` 이다. `../standalone/extract_hospital_anchors.py` 가 이 씬에서 뽑는다.
> 구역은 `src/rokey_p3_description/config/zones.hospital.yaml`·`zones.hospital-receiver.yaml` 이다. 아래 3절의 "`zones.yaml` 값 0" 은 9/21 시기의 사실이다.

이 폴더의 옛 병원 템플릿(`hospital_layout.usda`)과 자작 자산 해시(`hospital_assets.sha256`)의 사용법은 [sim README 병원 배치 씬](../README.md#병원-배치-씬-별도-자산)에 있다. 이 문서는 씬 파일을 고치지 않는다.

이 문서는 합성 장면을 **무엇으로 식별하고, 어떤 앵커를 누가 재야 하는지** 정리한다.
- 상태: 2026-09-21. 1-5절은 pharmacy_stage 합성 설계, 6절은 hospital_main 실행 씬 실측이다.
- 6절은 2026-09-21 현재 기준 자산에서 읽은 실측이다. 실측과 코드 기본값, 이식 전 테스트 값, 미확인을 구분한다.

## 1. 좌표계

- 합성 장면은 두 층이다. 아래는 세준 병원 씬(이 폴더 + 저장소 밖 자산), 위는 조제실 스테이지(`../standalone/pharmacy_stage.py`)다.
  - `--preset hospital-v2` 가 원점 A 에 둘을 합친다.
  - 합성 기동은 **Isaac 미실행**이다.
- **world = 조제실 스테이지 좌표 = 계약 `map`**([계약 3절](../../docs/architecture/delivery-contract-v1.md#3-프레임과-단위)). 원점은 레일 중심 바닥이고 +x 는 벨트 진행 방향이다.
- 병원 씬은 조제실 자세의 역변환으로 아래에 깔린다(`../standalone/p3sim/base_scene.py`). 그래서 **병원 USD 안의 좌표는 world 좌표가 아니다.** 병원 USD 에서 읽은 값을 `zones.yaml` 에 그대로 옮기면 틀린다.
- 원점 A: `HOSPITAL_ORIGIN_A = (0.25, 10.5285421018, 0.0, 0°)`. 조제실 원점과 +x 방향을 zero-root 병원 씬의 map 좌표로 적은 값이다. 이전 값 `y=13.3`에서 옛 `/World` Y offset `2.7714578982 m`를 뺀 값이다.

## 2. 장면 식별 (기동 로그)

장면 식별은 별도 파일로 두지 않는다. **기동 로그 첫 줄(`startup_line`)과 run 기록**에 남긴다. 파일을 따로 두면 실제 실행과 어긋날 수 있기 때문이다.

| 키 | 지금 남는 곳 | 비고 |
| --- | --- | --- |
| `preset`, `resolved_args` | 첫 로그 줄 `[pharmacy_stage] preset=… resolved_args={…}` | 기하·속도·원점·끈 prim 목록 전부 포함 |
| 코드 커밋 | run 기록 | |
| Isaac 판 | 기동 로그 `start … isaac=` | |
| 원본 병원 씬 | git(`hospital_layout.usda`) | |
| 자작 자산 ZIP | `hospital_assets.sha256` | `hospital-custom-assets-20260918.zip` |
| 준비된 씬 해시 (`base_usd_sha256`) | 둘째 로그 줄 `scene base_usd=… base_usd_sha256=…` | `--base-usd` 가 없으면 `-`, 파일을 못 읽으면 `unknown` |
| USD 단위 (`metersPerUnit`, `upAxis`) | 둘째 로그 줄 `… meters_per_unit=… up_axis=…` | 준비된 씬의 **루트 레이어 헤더만** 읽는다. 헤더에 없으면 `unset`, 텍스트 USD 가 아니면 `unknown`. 참조 자산의 단위는 알 수 없다(예: `machine` 은 자산 안에서 `scale:unitsResolve` 0.02 로 맞춘다) |
| Isaac 자산 revision | **없음** | 자산 루트 경로만 인자로 남는다. 같은 이름의 자산이 바뀌면 구분하지 못한다 |

설계 기준 로봇은 M0609 다(재범 결정 9/18). 씬의 M0617 은 `b9ba0d6`(#233)에서 레이어에서 빠졌다.

## 3. 앵커 입력 목록

값은 `origin/main` 기본 인자에서 계산했다(장면 v1·v2 같음). 단위 m.

| 앵커 | 현재 값 | 출처 | 누가 무엇을 재야 하나 |
| --- | --- | --- | --- |
| 벨트 시작(상판 표면) | (1.35, 1.0, 0.75) | 배출구 위치 + `--belt-top` | 스테이지 파생값 |
| 벨트 끝 | x 2.95 (길이 1.6, yaw 0), 폭 0.25 | `--belt-length`, `--belt-width` | 스테이지 파생값 |
| 종단 구역 | 마지막 0.15 (x 2.80–2.95) | `--end-zone` | 정지 거리 예산은 L3 측정 뒤 재검토 |
| 벽 | x 2.7 | `--wall-x` | — |
| UR5 받침대 윗면 | (3.25, 0.55, 0.45) | `--ur5-base` | 도킹한 AMR 팔의 대역이다. 도킹 자세가 정해지면 대체 |
| 상판 중심·칸 | (3.30, 0.05, 0.45), 5칸, 칸 0.14×0.11×0.04 | `--deck-center` 등 | 실제는 AMR 상판 `deck_slot_*`(isaac TF). AMR 상판 기하 필요 |
| UR5 대기 TCP | (3.05, 0.55, 1.00) | `--ur5-ready` | 이 자세가 통로 밖인지는 4절 상자와 FK 로 판정(미판정) |
| `pharmacy/belt_end` | 0 | `../../src/rokey_p3_description/config/zones.yaml` | 정의는 3.1(결정 23). 값은 최종 합성 stage 에서 잰다(미측정) |
| `pharmacy/shelf`, `dispenser_slot_a/b` | 0 | 같음 | 정의 결정 뒤 장면 v2 값에서 파생 |
| `load` 자세·공차 | 0, 공차 0 | 같음 | 주행 레인이 도킹 오차 측정 뒤 채움 |
| 병동·병실·병상·독 | 0 | 같음 | 병원 씬 합성 뒤 map 추출. 1절의 world 좌표로 |

TF 작성자는 계약 3절 그대로다. `map` 은 map_server, `pharmacy/*`·구역 프레임은 `zones_tf`, 로봇 링크·`deck_slot_*` 는 isaac TF 발행기가 낸다.

### 3.1 프레임 기준점 (결정 23, 재범 9/20)

물체를 집고 놓는 곳의 프레임 세 개는 **물체가 놓이는 윗면의 중심**을 원점으로 한다. 계약 3절 개정은 통합·정비의 #284 다. **값은 아직 미측정이다.**

| 프레임 | 원점 | 스테이지에서 |
| --- | --- | --- |
| `pharmacy/belt_end` | 벨트 상판 표면 위, 벨트 중심선의 끝점. x = 벨트 진행 방향, z = 위 | 벨트 좌표 (L, 0, 0)(`../standalone/p3sim/belt.py` `belt_frame`). 기본값이면 world (2.95, 1.0, 0.75). `zones.yaml` 값은 아직 0(비워 둔 자리) |
| `<zone>/cabinet` | 보관함 칸 바닥 윗면의 중심. z = 위 | 스테이지에 보관함이 없다. `zones.yaml` 값 0 |
| `deck_slot_N` | 상판 칸 바닥 윗면의 중심. z = 위 | `--ur5` 대역에서 `Deck/DeckSlot{N}Floor/Top` 을 TF 로 낸다(`../standalone/p3sim/ur5_cell.py`, 위치 계산은 `../standalone/p3sim/layout.py` `deck_slot_frames`) |

- 스테이지의 놓기 목표(`layout.deck_boxes` 의 `slot_centers`, 칸 바깥 상자 중심)는 `deck_slot_N` 원점보다 `칸 높이/2 − 벽` = 0.012 m 위다. 이 차이는 시험으로 고정했다.

### 3.2 그 밖의 결정과 입력

- **`ridgeback_ur5`(결정 22, 재범 9/20)**: `hospital-v2` 에서 끄지 않고 살려 둔다. 스테이지가 구동하지 않는 articulation 이라 기동 로그에 `WARN base_scene articulations this stage does not drive` 로 드러난다. 끌지 말지는 합성 stage 의 이동 베이스 담당이 정해지면 다시 정한다.
- **경로 토폴로지(주행 참고)**: 계약 3절은 경로 중간에 종단 zone 을 두지 않는다. 그래서 대기 dock 이 `load` 에만 이어져 있으면 dock 에서 병동으로 갈 수 없다. 실제 토폴로지에는 **dock → 복도 checkpoint edge** 가 있어야 한다. map 추출 때 이 edge 를 넣을 자리를 앵커 입력에 같이 잡는다.

## 4. 팔 통로 상자

계약 11.6 의 `/amr_1/arm/clear_of_belt` 는 팔이 "링크·파지물 vs 통로 상자"로 판정한다. 상자 치수는 simulation 이 준다.
벨트 좌표계(원점 = 벨트 시작 상판 표면, x = 진행 방향, `../standalone/p3sim/belt.py` 의 `belt_frame`)로 정의한다.

```text
along   : [L - end_zone - m_along,  L + m_end]
lateral : [-(W/2 + m_side),  +(W/2 + m_side)]
up      : [0,  h_clear]
```

- `L`·`W`·`end_zone` 은 스테이지 인자다(현재 1.6, 0.25, 0.15).
- 여유 `m_along`, `m_end`, `m_side`, `h_clear` 는 **결정 대기**다.
- 치수를 둘 파일은 `zones.yaml` 이 아니라 별도 파일로 한다(예: `rokey_p3_description/config/belt_aisle.yaml`). `zones.yaml` 은 `zones_tf` 가 읽는 형식이라 구역이 아닌 항목을 섞지 않는다. 값이 정해진 뒤 만든다.

## 5. 미실행·미확인

- `hospital-v2` 합성 기동. 병원 씬·자작 자산의 단위, 준비된 씬 해시, `WARN base_scene … not found` 유무를 봐야 한다(마스터 슬롯, 미실행).
- 씬 안 OmniGraph 가 경로 이동 뒤에도 도는지(미실행).
- UR5 대기 자세가 통로 밖인지(4절 값과 FK 필요, 미판정).


## 6. hospital_main 기준 실측 (2026-09-21)

### 6.1 기준본과 측정 방법

- 실행 기준은 ../standalone/hospital_main.py 가 해석하는 sim/scenes/hospital_layout.usda 이다. World0.usd 는 조제실 이식 전 테스트 환경이며 SSOT가 아니다.
- 전달 입력은 hospital_layout.usda, sim/outputs/hospital-custom-assets-20260918.zip, hospital_assets.sha256 세 가지다. 공식 병원·컨베이어·Ridgeback 자산은 Isaac Sim 5.1 Assets root에서 자동 해석한다. hospital_runtime.usda 는 이 입력에서 생성되는 호스트별 산출물이므로 전달 기준본이 아니다.
- hospital_layout.usda의 `/World` 원점은 2026-09-22부터 translate `(0, 0, 0)`을 사용한다. 아래 좌표는 이 원점 기준이다.
- 자작 ZIP: sha256 f519fb2c3f0e386f99b27e7ce707db7a14c2f2730c0959ec6f472293d2410144. 정본 값은 hospital_assets.sha256에 둔다.
- 측정은 Isaac Sim 5.1에 포함된 USD 라이브러리로 로컬 Assets root를 합성한 stage의 world bound, authored physics 속성, mesh 꼭짓점을 읽었다. 같은 입력의 hospital_main 무인 L3 기동은 scene load와 route topic 대기까지 통과했다. 이번 좌표 측정의 별도 SimulationApp 재실행은 이미 열린 GUI와 충돌해 미실행이다.

### 6.2 블로커: 조제기 투입구와 통행 폭

조제기 본체 `/World/machine`은 visual 전용이며 collision이 없다. prim 원점은 `(-10.1113256, 11.3490078, 0.1047580)`이다. 2026-09-21 실측 bound에서 이전 `/World`의 Y translate `2.7714578982 m`를 뺀 새 원점 기준 bound는 min `(-6.9012, 9.0399, 0.3824)`, max `(-3.4575, 10.3015, 2.2779)`, 크기 `3.4437 x 1.2616 x 1.8955 m`다. 이 bound 좌표는 원점 이동에 따른 산술 환산값이며, 새 씬을 다시 연 별도 bbox 실측은 미실행이다. 모듈 슬롯과 원형 수납통은 본체 옆에 별도 collision prim으로 이식한다.

World0 조제실을 붙일 때 사용하는 배치 기준은 다음과 같다.

| 대상 | hospital v2 map 기준 | 배치 규칙 |
| --- | --- | --- |
| 조제기 prim 원점 | `(-10.1113256, 11.3490078, 0.1047580)` | `/World/machine`의 authored translate |
| 보충구 1차 결합 앵커 | `(-3.4575, 9.6707, 1.3302)` | 조제기 bound의 `+X` 면 중앙. World0 보충구 중심을 이 점에 맞춘다 |
| 레일 배치 측 | `y < 9.0399` | 조제기 bound의 `-Y` 측에 두고, World0 `rail_x`를 map X축과 평행하게 둔다 |

**2026-09-22 정정:** 위 보충구·레일 숫자는 기존 hospital_main 조립 참고값이며, #484 최신 배치나 #485 조제기 투입구의 실행 좌표가 아니다. 사용자 지정 투입면은 −Y 정면이다. 원본 병원 단독 관측, 수정 에셋 앵커와 미실행 합성 측정은 [후속 정합 진단](../../docs/analysis/2026-09-22-dispenser-hospital-alignment.md)에 구분해 기록했다. 이 표를 기준으로 새 투입구를 +X 측면에 배치하지 않는다.

보충구 앵커는 전체 visual bound 면의 중앙을 사용한 1차 조립 좌표다. 조제기 메시에는 투입구 의미 prim과 collision이 없으므로 최종 간격과 높이는 합성 후 viewport 및 collision 검증으로 확정한다. 레일과 조제기 사이 clearance도 아직 결정하지 않았으므로 `y=9.0399`를 레일 중심 좌표로 사용하지 않는다.

현재 hospital_main 씬에는 그 슬롯과 수납통이 아직 없다. 테스트 World0의 의도값은 다음과 같지만 map 좌표가 아니므로 그대로 zone 값으로 쓰면 안 된다.

| 항목 | World0 테스트 좌표/치수 | collision 상태 |
| --- | --- | --- |
| 모듈 슬롯 | 입구 중심 (1.15, 0.70, 1.02), 개구 0.08 x 0.16, 깊이 0.15 m, +y 삽입 | 좌·우·상·하 및 뒤 body collision으로 둘러싼 구조 |
| 원형 수납통 | 중심 xy (0.90, 0.56), 내경 0.12, 벽 0.01, 깊이 0.12, 내부 바닥 z 0.86 m | 바닥과 16개 벽 collision |

World0로 저장된 Cube들은 extent와 xformOp:scale이 중복 적용된 상태다. 예를 들어 임시 모듈 약통의 실제 bbox는 0.0036 x 0.0100 x 0.0196 m이고 원형통 바닥도 0.0196 x 0.0196 x 0.0001 m다. 의도값 0.06 x 0.10 x 0.14 m 및 외경 0.14 m와 다르므로 #397 검증에 현재 World0 collision을 사용하면 안 된다. hospital_main 이식 시 단위 Cube 또는 한 번만 적용한 extent/scale로 다시 저작해야 한다.

북측 문틀 두 곳의 내부 collision 경계 간 개구 폭은 각각 1.2232 m다.

- Geo_M_DoorFrame51: x -1.3969 .. -0.1737
- Geo_M_DoorFrame53: x -2.7189 .. -1.4957
- 문짝 SM_Door_01b6/7 collision이 닫힌 상태로 개구를 차지하므로 현재 물리 유효 폭은 0 m다.
- 문짝을 열거나 collision을 제외한 뒤에는 보수 footprint 폭 0.90 m 대비 총 0.3232 m, 좌우 각 0.1616 m가 남는다.
- 동측 주 복도는 서측 벽 face x=3.1605, 동측 벽 face x=11.1600 사이 7.9995 m다. 이 값은 주 복도 한 구간이며 전체 주행 경로의 최소 폭을 뜻하지 않는다.

따라서 0.90 m 통과의 현재 블로커는 문틀 폭이 아니라 닫힌 문짝 collision이다. 실제 주행 경로가 정해진 뒤 해당 문만 열림 자세로 저장하거나 collision 정책을 바꾼다.

### 6.3 좌표계와 ROS 프레임

합성 stage는 metersPerUnit=1.0, Z-up, defaultPrim=/World다. stage map 원점은 `(0, 0, 0)`이고 `/World`의 translate도 `(0, 0, 0)`이다. 모든 zone 값은 prim local 좌표가 아니라 stage world 좌표로 변환해 기록한다.

| ROS 프레임 | USD 기준 |
| --- | --- |
| map | 합성 stage world 좌표 |
| zone | zones_tf가 zones.yaml의 stage world pose를 발행. 현재 0 값은 미측정 자리이며 실제 prim 자동 매핑이 아니다 |
| pharmacy/belt_end | 최종 이동 표면의 진행방향 끝단 상판 중심. 현재 zones.yaml에는 아직 반영되지 않음 |
| cabinet | 보관함 칸 바닥 윗면 중심. 현재 hospital_main 씬에 계약용 cabinet prim/매핑 없음 |
| 로봇 링크 | 추후 Isaac TF 발행기가 담당. map 또는 zone을 Isaac이 중복 발행하지 않음 |

### 6.4 조제실 자산

hospital_main 씬에는 아직 16칸 자작 선반이 없다. 병원 기본 선반 3개는 `/World/Environment/hospital` 아래에 있으며, `/World` 원점을 0으로 바꾼 뒤의 map 좌표는 다음과 같다. World0 선반을 병원 선반 위치에 맞출 때는 `SM_MedShelf_01d_67`을 행의 기준 앵커로 삼고, 필요한 경우 나머지 두 좌표를 복제 간격 검증에 사용한다.

| prim | map translate (x, y, z) m |
| --- | --- |
| `/World/Environment/hospital/SM_MedShelf_01d_67` | `(-4.9941855, 11.7461133, 0.0000405)` |
| `/World/Environment/hospital/SM_MedShelf_01d_68` | `(-4.1129012, 11.7363087, 0.0000405)` |
| `/World/Environment/hospital/SM_MedShelf_01d_69` | `(-3.2168401, 11.7266587, 0.0000405)` |

16칸 중심, 내부 치수, 판 두께, 전면 y는 이식 후 측정 항목이다. World0의 16개 테스트 중심은 조제실 로컬 좌표일 뿐 map 좌표가 아니다: x={-1.15,-0.85,-0.45,-0.15}, y=0.91, z={0.61,0.91,1.24,1.54}의 조합이다.

약통 기준은 /home/rokey/hospital_custome/assets의 centered USD다. 치수는 외형 world bbox이며 질량은 전 파일에서 명시되지 않았다.

| 자산 | 외형 치수 m | collision |
| --- | --- | --- |
| medbot_1_centered | 0.07757 x 0.07757 x 0.22018 | Mesh convexHull |
| medbot_2_centered | 0.11037 x 0.11037 x 0.16786 | body convexDecomposition + lid convexHull |
| medbot_3_centered | 0.14157 x 0.14157 x 0.15769 | 없음 |
| medbot_4_centered | 0.10211 x 5.17828 x 0.22004 | 없음, 비정상 y bbox |
| medbox_1_centered | 0.12584 x 0.13768 x 0.17643 | Mesh convexHull |
| medbox_2_centered | 0.12748 x 0.08261 x 0.13132 | Mesh convexHull |
| medbox_3_centered | 0.11979 x 0.09833 x 0.11979 | Mesh convexHull |
| medbox_4_centered | 0.11629 x 0.09833 x 0.11979 | Mesh convexHull |

medbot_3/4는 physics 기준본으로 사용할 수 없고 medbot_4는 bbox도 비정상이다. 파지 가능 면은 USD에 의미 정보로 저작되어 있지 않다. 원통형은 몸통 대향 접선면, 박스형은 가장 좁은 수평축의 대향 평면을 후보로 삼되 실제 그리퍼 clearance 시험으로 확정한다. 질량은 명시적으로 저작해야 한다.

World0 레일 관절은 rail_x X축 -1.40..1.40 m, rail_y Y축 -0.10..0.33 m, rail_z Z축 0..1.10 m다. 고정 Track은 3.20 x 0.10 x 0.05 m이며 collision=true다. YBeam 0.14 x 0.65 x 0.06, Truck 0.24 x 0.12 x 0.06 두 개, Pedestal 0.22 x 0.22 x 0.16, YCarriage 0.30 x 0.26 x 0.05, LiftPlate 0.28 x 0.28 x 0.04, LiftColumn 0.16 x 0.16 x 1.12 m는 모두 collision=false다.

hospital_main 맵의 컨베이어 이동면은 다음 규격이다.

| 형식 | 이동면 치수/높이 |
| --- | --- |
| 직선 A06 | 0.9997 x 0.4500 x 0.0195 m, top z=0.8903 |
| 직선 A09 | 1.9835 x 0.4500 x 0.0195 m, top z=0.8903 |
| 분기 A24 | 1.9988 x 0.4500 및 0.4500 x 1.0057 m, top z=0.8903 |
| 곡선 A03 | 0.9720 x 1.0228 x 0.0200 m, top z=0.8907 |
| 경사 A37 | 0.4500 x 1.9534 m, top z=0.8903에서 끝단 top z=0.3846까지 하강 |
| sorter A47 | 주 rollers 1.9913 x 0.4516 x 0.0290 m, top z=0.8847 |

최종 네 경사 벨트는 map에서 -y 방향이다. `/World` 원점을 0으로 바꾼 뒤 진행방향 끝단 상판 중심은 Track_12 `(-1.7093, 4.6488, 0.3846)`, Track_13 `(1.2231, 5.0778, 0.3846)`, Track_14 `(-5.4931, 4.6488, 0.3846)`, Track_15 `(-8.2549, 5.0661, 0.3846)` m다. 이 값은 이전 실측 Y에서 `2.7714578982 m`를 뺀 산술 환산값이다. 정지 센서/허용구역은 아직 없으므로 이 좌표를 곧바로 제어 정지점으로 쓰지 않는다.

### 6.5 Isaac Sim 5.1 Ridgeback + UR5

기준 자산은 Isaac/Robots/Clearpath/RidgebackUr/ridgeback_ur5.usd다. 단위 1 m, Z-up, defaultPrim=/ridgeback이다.

관절은 dummy_base_prismatic_x_joint, FixedJoint, dummy_base_prismatic_y_joint, dummy_base_revolute_z_joint, ur_arm_shoulder_pan_joint, ur_arm_shoulder_lift_joint, ur_arm_elbow_joint, ur_arm_wrist_1_joint, ur_arm_wrist_2_joint, ur_arm_wrist_3_joint다. 베이스는 휠 관절이 아니라 x/y prismatic + yaw revolute의 planar dummy joint 방식이다.

base_link 외형 bbox는 0.93251 x 0.79320 x 0.32717 m다. 이전 Isaac 런타임 collision union은 약 0.93256 x 0.79006 m다. 따라서 1.10 x 0.90 m는 실제 메시 치수가 아니라 안전 여유를 둔 계획 footprint다.

공식 에셋에는 다음 항목이 없다.

- 상판 5칸 prim 및 좌표
- 손목 카메라와 intrinsics
- 라이다
- OmniGraph/ROS graph 및 joint_command 토픽

그러므로 없는 값을 공식 에셋 측정값처럼 채우지 않는다. 5칸 상판, 손목 카메라, 라이다, ROS graph는 별도 합성 레이어에서 추가하고 그 레이어의 경로·파라미터·토픽을 다시 측정해야 한다.
