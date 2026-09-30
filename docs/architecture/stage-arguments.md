# 스테이지 인자·기본값 (병원 preset, v1.1.0)

- 상태: 현황 기록. 계약을 바꾸지 않는다. 값이 바뀌면 이 표와 근거 회차를 같이 고친다
- 기준: main `f316197` = 태그 `v1.1.0`. 표의 값은 이 커밋의 `sim/standalone/pharmacy_stage.py`(`PRESETS["hospital"]`, 138–216행)와 `tools/demo_v2.sh` 에서 옮겼다
- 대상: `sim/standalone/pharmacy_stage.py` 의 `--preset hospital`(병원 전 구간)과 그것을 띄우는 `tools/demo_v2.sh`
- 이웃: Isaac 쪽 토픽 형식과 어댑터는 [ADR 0002](../adr/0002-isaac-json-topics-and-ros-adapter.md), 이름·QoS 는 [계약 v1](delivery-contract-v1.md), 지금 구성 그림은 [시스템 그림](system-overview.md)

스테이지 인자는 계약의 이름이 아니다. 그러나 회차 결과를 바꾸는 값이라 **값·근거 회차·바꾸는 법**을 한곳에 적는다.
근거 열은 실행 조합 SHA 와 #240 댓글 ID 다(main SHA 가 아니다). "고른 값"은 잰 값이 아니라는 뜻이다.
v1.1.0 에서 새로 기본이 된 값(아래 **v1.1.0** 표시)은 L3 acceptance 미실행이다(v1.1.0 릴리스, #772 5891599172).

## 1. 값

| 인자 | 병원 값 | 인자 기본(preset 밖) | 근거 | 바꾸는 법 |
| --- | --- | --- | --- | --- |
| `--pouch-pool` | **15**(`HOSPITAL_POUCH_POOL`, 9/25) | 8 | 배달한 봉투는 보관함에 남아 풀로 돌아오지 않는다. QR 라벨은 풀 크기만큼만 주문 id 를 돌려 붙인다(`pouch.pool_labels`). 풀 8 에서 ord-0009·0010 은 라벨 봉투가 없었고 `pool_exhausted` 로 거부됐다(50b658a · 5802751527). 12 = 병원 주문 풀 10 + 여벌 2. 12 뒤 `pool_exhausted` 0(b40e133 · 5804528593). #643. 9/25: 주문 풀에 테이블 주문 셋(ord-0011 B·0012 C1·0013 C2)이 더해져 15 = 13 + 여벌 2 | 주문 풀이 늘면 같이 늘린다. 주차 줄(x −8.5, y 7.0 + 0.15 i)이 빈 자리인지 `sim/tests/test_hospital_full.py` 가 본다 |
| `--seed` | `P3_V2_SEED`(기본 **7**) | 0 | 진열(`workcell_stock`)·봉투 스폰의 랜덤. 전에는 팔 `v2_seed` 에만 가고 스테이지는 0 에 고정이었다(회차38). seed 7 진열에서 빈 칸 4개가 seed 0 과 달랐고 5/5(68dd351 · 5802558111). #642. v1.1.0 병원 preset 은 빈 칸이 0 이다(#791). seed 가 비우는 칸은 없다(`--workcell-empty-cells` 도움말: 비울 칸을 seed 로 고른다) | `P3_V2_SEED=<n>`. 예전 진열은 `P3_STAGE_ARGS="--seed 0"`(뒤 값이 이긴다) |
| `--render-every` | **2** | 1 | 아래 2절 | `P3_STAGE_ARGS="--render-every 1"`. 촬영처럼 화면이 중요하면 |
| `rail_drive` | **[1e5, 1e4, 5e4]**(`VERIFIED_RAIL_DRIVE`) | [1e7, 1e5, 1e8] | 아래 2절. 병원 preset 이 정한다 | `--rail-drive a b c`. 밀림은 `rail_follow … worst_m` 줄(문턱 `--rail-follow-warn-m` 0.02 m, 판정선 아님) |
| `--canister-contact-threshold-n` | **5.0** N | 5.0 | 0 이면 선반에 얹힌 약통 쌍이 매 스텝 보고돼 PhysX 재질 경고 419,292줄, rtf 0.32(9/23 병원 한 바퀴). 5 N 은 약통 무게 위·밀린 접촉 아래로 **고른 값**이다(396958e). 런카드 4절 | 인자로 준다. 낮추면 경고가 는다 |
| `--tray-clip` | **켬** | 끔 | **실물 트레이 봉투 홀더(칸 클립)의 대응물**이다. 칸에 놓여 멈춘 봉투를 트레이에 붙인다(`tray clip on`). 팔이 그 봉투를 잡으면 푼다(`tray clip off … reason=picked`). 리셋·STOP 이면 모두 푼다. 트레이 고무 매트(μ 1.0)로도 1.0 m/s 곡선에서 3.4 cm 밀렸다(737fee9 Play/Stop). 마찰로 설명이 안 되는 크기다. 그래서 붙인다(재범 9/24 20:5x). 조인트 프림을 실행 중에 만들지 않는다. 흡착과 같은 텔레포트 추종이다 | `--no-tray-clip` |
| `P3_DISPENSE_TIMEOUT_S`(`demo_v2.sh`, 어댑터 `dispense_timeout_s`) | **30** s | 계약 기본 2 | 어댑터가 Isaac 조제 응답을 기다리는 wall 시한이다. 10 에서 ord-0009 가 `not_ready` 로 3회 거부됐다. 30 은 #660(afc1135) 뒤 `tools/demo_v2.sh` 기본값이다(v1.1.0 146행) | `P3_DISPENSE_TIMEOUT_S=<s>`. 병원(`P3_WORLD=hospital`)에만 붙는다 |
| `--hospital-decor` | **켬** | 끔 | 바닥 안내선·자리 표시·충전 표시(#669). RC-3 은 M0609 셀 바닥(`0cfdb93`, 재범 9/25)을 더한다. 천장 방향 안내판 4장·로비 벽 안내 3장은 #781 이 더했다. 충돌체가 없어 라이다·접촉에 안 보인다 | `--no-hospital-decor` |
| 병실 테이블 C1·C2 | 씬 실물 | — | 재범 9/25(병실 주문 → C, 오버헤드 컷의 원): 병동 입구 복도 협탁 둘. C1 = `station_c` → `/World/Environment/hospital/SM_SideTable_02a4`(씬 over) translate (20.1414, 5.8722), C2 = `station_d` → `/World/Environment/hospital/SM_SideTable_02a4_02`(씬 def) translate (20.1508, −2.0611). 둘 다 scale 1.185·1.950·0.7, yaw −90 → 상자 0.823(x) × 1.088(y), 윗면 0.568 m. 상자 C1 x 19.730–20.553 y 5.328–6.416, C2 x 19.739–20.562 y −2.605–−1.517 — 지도의 막힌 칸과 맞다(시험). 스테이지가 세우지 않는다. 윗면 색(초록)은 스테이지 경로 `/World/P3Base/Scene/Environment/hospital/…` 에 입힌다 | zone 이름·자리는 `hospital_nav.CORRIDOR_TABLES` 에서 바꾸고 zones·routes 를 다시 만든다 |
| `--traffic-dummies` | **2**(`HOSPITAL_TRAFFIC_DUMMIES`, RC-3) | 0 | 회피 장면(재범 9/25 00:2x, 안전판 v0.5.0). 합본 모양 가짜 AMR 이 로비·복도 고정 루프를 0.5 m/s 로 돌고 진짜 AMR 이 1.5 m 안이면 선다. 판정선이 실패하면 0 으로 되돌린다(정해 둔 규칙). 병원 acceptance 회전 1–7 은 이 preset 기본으로 돌았다(회전 7 코드 `9760d9d` 도 2) | `--traffic-dummies 0` |
| `--pedestrians` | **2**(`HOSPITAL_PEDESTRIANS`, RC-3) | 0 | 회피 장면(재범 9/25). 로비(x 5.5)·병동 앞 복도(x 16.5) 왕복 선에 한 명씩, 0.8 m/s 로 멈추지 않는다. 충돌체가 있어 라이다·접촉 로그에 보인다(`63eeb29`). 판정선이 실패하면 0 으로 되돌린다. 회전 7 코드 `9760d9d` 도 2 다 | `--pedestrians 0` |
| `--lidar-debug` | 끔 | 끔 | 촬영용이다(재범 9/25). amr_1 라이다 스캔 점을 뷰포트에 그린다. 회피 장면에서 보행자·더미가 스캔에 잡히는 것을 보이려는 것이다. `--amr-lidar` 가 있어야 한다. 렌더 프로덕트를 하나 더 만든다. rtf 를 먹는다. 판정·토픽과 무관하다. 못 그리면 경고만 남긴다(`amr lidar debug draw writer=…` / `WARN … disabled`). writer 이름은 Isaac 버전마다 다르다. 두 이름을 차례로 찾는다. **L3 미달이다.** writer 는 등록된다. 점이 안 보인다(#240 5855007892). NVIDIA 예제도 이 PC 에서 점이 뚜렷하지 않다(#240 5855053269). 촬영에서는 쓰지 않는다. 회피 장면의 스캔은 웹 live-sensors 로 보인다(9/27) | `P3_STAGE_ARGS="--lidar-debug"` |
| `--block-path` | 끔 | 끔 | 정지 규칙(#721) **발동** 시험 소품. 사람 크기 빨간 캡슐이 바닥 아래 숨어 있다가 amr_1 이 1.5 m 안에 들면 load → 병동 공통 구간(로비 (4.54, 4.21)) 에 한 번 올라오고 5 s 뒤 내려간다(고른 값, `p3sim/path_block.py`). 기대 로그 `block_path placed` → `governor stop reason=obstacle` → `block_path lifted` → `governor resume`, 접촉 0. 회차127 은 더미가 1.5 m 밖에서 서서 0.6 m 문턱에 든 적이 없었다. 시험 회차에만 켜고 더미·보행자는 0 으로 둔다. L3 미실행 | `P3_STAGE_ARGS='--block-path --traffic-dummies 0 --pedestrians 0'`, 자리·거리·시간은 `--block-path-at X Y`·`--block-path-trigger M`·`--block-path-hold S` |
| `--workcell-empty-cells` / `--workcell-consume` | **0 / 켬**(**v1.1.0**, #791) | 4 / 끔 | 재범 9/29 N3 "쓴 만큼 줄게". 조제실 18칸을 가득 채운다. 조제기에 넣은 약통은 `--respawn-delay-s`(2 s) 뒤 바닥 아래(z −5 m)로 치우고 그 칸은 빈 칸이 된다. 리셋하면 다시 찬다. 웹이 재고를 보인다(`dispenser.stock`). L3 미실행 | `--workcell-empty-cells 4`, `--workcell-consume` 는 preset 에서만 켜진다(끄는 인자 없음, `P3_STAGE_ARGS` 로 되돌릴 수 없다) |
| `--conveyor-speed-scale` | **2.0**(`HOSPITAL_CONVEYOR_SPEED_SCALE`, **v1.1.0**, #789) | 1.0 | 재범 9/29 "속도 올리기". 잰 표면 속도(롤러 0.5 m/s)에서 봉투는 출발→A1 에 34.58 sim s 걸렸다. 봉투가 롤러에서 미끄러져 실효 약 0.15 m/s 였다. 방향·분기·끝 롤러 잡기는 그대로다. **L3 미확인**: 끝 롤러 튐·분기 낙하·A1 정착을 마스터 랩에서 본다(`pharmacy_stage.py` 100–105행 주석) | `--conveyor-speed-scale 1` |
| `--dock-wall-opacity` | **0.35**(`HOSPITAL_DOCK_WALL_OPACITY`, **v1.1.0**, #792) | 1.0 | 재범 9/29 "반투명으로 약이 오는 것". 조제실 남쪽 도크 벽(y 5.35)의 재질만 바꾼다. 환경 USD 는 그대로다. 라이다 통과 여부·rtf 는 L3 미확인(#772 5891599172) | `--dock-wall-opacity 1` |
| `--hospital-receiver-prim` | `P3_HOSPITAL_RECEIVER_PRIM`. 카메라 기본에서 **`/World/P3Base/Scene/Environment/hospital/SM_SideTable_02a_74`**(**v1.1.0**, #796·#797) | 없음 | A1 모듈 탁자(receiver) 경계에서 봉투의 롤러 통과·정착을 본다. 끝 롤러 강제 정지는 하지 않는다. 합본은 그 탁자 앞 적재 자리(= dock_1)에서 집는다. 9/29 master02 탐색 실습 1건(`05b8e28`, `bed_a1` DELIVERED, [실습 45](../practice/simworld/practice-45.md))이 근거다. v1.1.0 통합본 L3 는 미실행 | `P3_HOSPITAL_RECEIVER_PRIM=`(빈 값)이면 끈다. 그때는 `P3_ZONES` 도 `zones.hospital.yaml` 로 준다(`tools/demo_v2.sh` 47–48행) |

## 1.1 병원 기동 기본값 (`tools/demo_v2.sh`, v1.1.0)

스테이지 밖에서 회차를 바꾸는 기동 변수다. `P3_WORLD=hospital` 일 때의 기본값이다.
**v1.1.0** 표시는 #797(`2c08bef`)에서 기본이 된 값이다. L3 acceptance 미실행이다.

| 변수 | 병원 기본 | 뜻 | 근거 |
| --- | --- | --- | --- |
| `P3_CAMERA_POUCHES` | **1**(**v1.1.0**) | 봉투를 손 카메라 QR 로 찾는다. QR 이 주문과 맞아야 집는다 | 재범 9/29 "QR 반드시 찍고"(#784). `tools/demo_v2.sh` 126·162행 |
| `P3_CAMERA_TAGS` | `P3_CAMERA_POUCHES` 를 따른다(= 1) | 병상·스테이션 인식표(`pt-`·`st-`)도 손 카메라 QR 로 읽는다(`scan_tag_source:=camera`) | #784. 163행 |
| `P3_ZONES` / `P3_ROUTES` | 카메라 기본: **`zones.hospital-receiver.yaml` / `routes.hospital-receiver.yaml`**(**v1.1.0**). 참값(`P3_CAMERA_POUCHES=0`): `zones.hospital.yaml` / `routes.hospital.yaml` | 주행·웹·스택·스테이지가 같은 파일을 받는다 | 131–139행 |
| `P3_AMR_START` | 카메라 기본: **`-8.266 4.102`**(= receiver zones 의 dock_1 = load). 참값: `-8.995 4.686`(= zones.hospital 의 dock_1 = load) | A1 도크가 적재 자리다. 도크에서 이동 없이 바로 집는다(재범 9/29 B안, #790). dock_2–4 도 모듈 왼쪽이다(#795) | 133·143행, `zones.hospital*.yaml` 의 `load`·`dock_1` |
| `P3_UR5_ARM_PARAMS` | 카메라: `ur5_arm.amr-combined.camera-receiver.yaml`. 참값: `ur5_arm.amr-combined.gripper.yaml` | 카메라 파일은 손목 고정 + 실측 추가 하강 0.05 m 다. 근본 수정이 아니다(#796) | 165–171행 |
| `P3_BELT_VIEW_OFFSET` | 카메라 기본 **0**(그 밖 −0.075) | 벨트 관측점을 끝에서 옮기는 양(m) | 135·186행 |
| `P3_DISPENSE_WHILE_DISPATCHING` | 카메라 기본 **true**(그 밖 false) | AMR 이 적재 자리로 가는 동안 첫 봉투를 먼저 낸다. 집기는 AMR 도착과 봉투 정착 뒤에만 한다. v1.1.0 병원 zones 는 dock_1 = load 라 orchestrator 가 `load_at_dock` 으로 이동 없이 적재한다. 그때는 이 값이 쓰이지 않는다(`trip_fsm.py` 931–946행) | 136·469행, [실습 45](../practice/simworld/practice-45.md) |
| `P3_CONTAINER_QR` | **1** | 보충 전에 M0609 손 카메라로 약통 QR 을 읽고 약 DB 로 확인한다 | 191행 |
| `P3_CAMERA_RESOLUTION` | `1280 800` | 손 카메라 해상도(D455 컬러 기본값) | 193행 |
| `P3_V2_RAIL_SELECT` | **`preferred_first`**(**v1.1.0**) | M0609 보충 레일 후보 순서. `first_feasible` 로 되돌린다 | 재범 9/29 "디폴트로 켜서". 207행. 9/21 #391 에서는 opt-in 이었다. 팔 노드 자체의 기본은 `first_feasible` 이다(`m0609_arm_node.py` 230행). `demo_v2.sh` 가 값을 늘 넘긴다 |
| `P3_V2_GUARDED_MODULE_PATH` | `false` | 가드 모듈 경로. 새 경로 L3 는 `true` 로 명시한다 | 206행 |
| `P3_BELT_TIMEOUT_S` | 60 | 오케스트레이터 `belt_timeout_s`. 배율 1 컨베이어의 34.58 s 를 덮는다 | 144행 |
| `P3_AMR_COUNT` | 1 | 합본 AMR 대수(1–4). 부하 측정용이고 배송은 첫 대만 한다 | 145행 |
| `P3_V2_SEED` | 7 | 팔 `v2_seed` 와 스테이지 `--seed` | 205행 |

- main 에 없는 것: M0609 모듈 집기 레일 순서 수정과 쓴 약통 물리 끄기(박세준 로컬 커밋 `8f106f6`)는 push 되지 않았다. 이 표에 없다.
- M0609 팔 링크끼리의 충돌 검사는 플래너에 없다(`scene_v2.py` 57·131행, #772 5891599172). 자기 충돌 수정 PR 은 main 에 없다.

## 1.2 주행 기본값 (병원)

스테이지 인자는 아니다. 회차 결과를 바꾸는 값이라 같이 적는다.

| 값 | 기본 | 근거 |
| --- | --- | --- |
| 감속기 근접 속도 `slow_speed_mps` | **0.7 m/s**(**v1.1.0**, #788. 전에는 0.5) | `speed_governor.py` 28행 `SLOW_SPEED_MPS`, `nav2_params.yaml` 139행. 재범 9/29 "속도 올리기". L3 미확인 |
| 최고 속도 `max_speed_mps` | 1.0 m/s | `speed_governor.py` 30행, `nav2_params.yaml` 138행 |
| 근접·원거리 문턱 `NEAR_M`·`FAR_M` | 1.0 m · 1.8 m | `speed_governor.py` 21·23행. 고른 값이다 |
| 정지·재개 문턱 | 0.6 m · 0.9 m · 1 s | 아래 5절 표. 바꾸지 않았다 |
| Nav2 → 추종기 넘김 `nav2_handoff_radius` | 0.5 m | `navigation_params.yaml` 31행 |

## 2. 성능 기본값의 근거

**성능 기본값의 근거.** 병원 preset 은 `--render-every 2` 가 기본이다. 물리는 1/60 s 그대로 매 틱 돌리고, 그리기와 Kit 갱신(OmniGraph·ROS 발행 포함)만 두 틱에 한 번 한다. 같은 장비·같은 인자에서 render 만 바꾼 대조(master01 `5a10c79` 회차 11·12, #240 댓글 5796069792)에서 rtf 0.418 → 0.690, loop_hz 24.8 → 40.9 였다. 다섯 장면은 통과했고 TF·/clock 경고는 0 이었다. 물리 1/30 은 집기·레일 동역학의 전제를 깨서 쓰지 않는다(`--render-dt 1/30` 시험은 rtf 0.273 으로 기각). 레일 드라이브 기본은 `[1e5, 1e4, 5e4]`(VERIFIED_RAIL_DRIVE)다. 1e7 에서는 보충 중 0.6-0.8 s 루프 멈춤이 5 번 났고, 이 값에서 0 번, 보충 성공이었다(master02 `94f19fb`, #240 댓글 5795175482). 모듈 넣기 때 레일 밀림은 `rail_follow … worst_m` 줄로 본다. GPU 는 노트북 RTX 5080 이라 80 W 에 묶여 있다(`nvidia-smi -pl` not supported). 그래서 rtf 목표는 0.7 이다(9/24 결정). 측정 순서와 기각한 것은 #587(docs/analysis/hospital-perf-0923.md)·#622, 10건 연속에서 30분 뒤 rtf 가 0.34-0.35 로 내려앉는 것은 #647 에 있다. 장비마다 기준이 달라(같은 설정에서 master01 0.69, master02 0.45-0.50) 비교는 같은 장비끼리만 한다.

## 3. 화면·브라우저 변수 (`tools/demo_v2.sh`)

스테이지 인자로 바뀌어 들어가거나 기동 모양만 바꾸는 변수다. 판정선에는 영향이 없다.

| 변수 | 기본 | 뜻 |
| --- | --- | --- |
| `P3_SCREEN_SIZE` | `"2048 1152"`(master02 패널) | Isaac 은 `--window-half left --screen-size W H`(스테이지가 그 인자를 알 때만), 브라우저는 오른쪽 반 |
| `P3_BROWSER` | 비움(안 띄움) | 예: `firefox`. **비우면 웹 창이 안 떠 `boot_check` 의 창 점검이 걸린다**([런카드 2절](../runbooks/hospital-full.md#2-한-바퀴)) |
| `P3_BROWSER_WIDTH` / `P3_BROWSER_HEIGHT` | 화면의 W/2, H | firefox `-width/-height`. 창 위치는 스크립트가 못 정한다 |
| `P3_HEADLESS` | 0 | 1 이면 스테이지 `--headless`, 창 인자·브라우저·주기 캡처를 끈다 |
| `P3_STAGE_ARGS` | 비움 | 스테이지에 더 넘길 인자. **골든 회차에서는 비운다**(촬영 뷰 `--view` 만 예외, 런카드 3.2) |

## 4. 한계

- 5 N 접촉 문턱과 `--rail-follow-warn-m` 은 고른 값이다. 잰 값으로 바꾸지 않았다.
- rtf 는 장비마다 절대값이 다르다. 이 문서의 rtf 는 그 장비·그 회차의 값이다.
- 1.0 m/s·감속 1.0 m/s² 에서 제동 거리는 0.5 m 다. 정지 문턱 0.6 m 의 마진은 0.1 m 다. 센서 지연은 이 계산에 없다.
- 근접 속도를 0.7 m/s 로 올린 뒤(#788) touch 0·정차 지나침 0 은 마스터 랩에서 보지 않았다(L3 미확인).
- `--block-path` 는 나타난 뒤 0.4 s 안에 재계획이 진행 방향 띠 밖으로 빠지면 `governor stop` 이 없다. 그 우회는 이 소품이 막지 못한다. L3 는 `governor stop reason=obstacle` 줄이 있는지로 발동을 본다.

## 5. 정지 감지 실패 조사 (9/27)

> 이 절은 9/27 조사 기록이다. v1.1.0 에도 정지 규칙 수정은 없다. 감속기 긴급정지는 #752 진단만 있다(v1.1.0 릴리스).
> 진단 스위치 `stop_diagnostics` 는 지금도 기본 false 다(`speed_governor_node.py` 83행).

**시각을 맞춘 진단 랩에서는 배치 구간의 전방 lethal 후보가 없었다. 감지 실패의 구체 원인은 미확인이다.**
`main 05297e6` 위에 `0456afe`의 진단과 회귀시험을 포함했다. 이번 보강은 좌표·시각 진단이다.
정지 판정·문턱·발행 주기는 변경하지 않았다. 동작 수정은 미완료다. 시험 통과를 현장 수정 완료로 읽지 않는다.
캠페인 `a4b1a4e`의 판정선·기록, 지도 서버 감시 #743, 도킹 재시도 #749는 이 조사 범위 밖이다.

### 확인한 것과 아직 없는 것

- master01 `m1-gap3-blockpath-a4b1a4e-r163014`: `placed` → `lifted`는 있다. `stop/resume`은 없다.
  접촉은 6건이다(#240 원문).
- 여유 0.65 m가 유지됐다는 로그만으로 캡슐 미관측을 확정할 수 없다
  (발췌).
  `free_space`는 전방이 아니라 전체 방향의 최솟값이다. 옆 장애물이 0.65 m, 전방 캡슐 표면이 0.8 m이면
  캡슐 유무와 무관하게 여유는 0.65 m다. 전방 정지 판정만 달라진다. 추가 시험이 이 반례를 고정한다.
- `0456afe` 진단 랩 `m1-diag-stoprule-0456afe-r175825`은 접촉 5건이다. stop/resume은 0줄이다
  (master01 원문).
  nav 458–493의 `any=0.77→0.02`, `dist=none`, `static_skipped>0`은 후보 전부가 제외됐다는 뜻이다.
  다만 nav 벽시계와 stage 배치 sim 177.02–182.02는 아직 맞추지 못했다.
- 판독 댓글의
  좌표 변환 오류는 조사 가설이다. 제외 칸이 캡슐인지 기존 벽인지는 아직 모른다.
  `origin + width*res/2 + (col-(width-1)/2)*res = origin + (col+0.5)*res`이므로,
  `rx+dx` 자체는 칸 중심 식과 같다. TF 방향·실제 메시지 원점·지도 데이터는 다음 관측으로 대조한다.
- 순수 함수에 캡슐의 lethal 셀을 주면 현재 코드도 정지한다. 5 m, 0.05 m 해상도의 짝수 크기 격자에서
  전진·대각·옆걸음·후진 다섯 방향과 실제 `blocked_near` → `forward_scan` → `StopRule` 연결을 시험했다.
  같은 셀이 정적 지도에 있으면 정지하지 않는다. 동적 셀이 사라지면 1 s 뒤 재개한다.
  진행 띠 밖 더미·보행자 위치의 합성 입력도 정지하지 않는다. **센서·DDS·마스터 캠페인 검증은 아니다.**
- 노드의 좌표 변환과 `blocked_near` 호출을 그대로 `StaticMapFilter`로 옮겨 시험한다.
  실제 병원 지도와 도크 평행이동 `(-7.272, 4.784)`에서 캡슐 자리 `(4.54, 4.21)`는 제외되지 않는다. stop이 발생한다.
  항등·90도 회전 TF도 시험한다. 실제 지도 벽은 제외된다. stop은 없다.
  빈 지도 + 몸체 앞 0.3 m의 셀도 stop이다. 즉 오프라인 입력에서는 좌표 오류 가설이 재현되지 않았다.

### 랩 1-b 판독 정정 (0ac6659)

master01 원문 5854823464의
`tf=(-7.272,4.784,0)` 고정은 `map ← amr_1/odom` 관계다.
`localization:=odom`의 `dock_origin_tf`가 의도적으로 내는 고정 변환이다.
로봇 이동은 코스트맵 원점에 들어 있다. 이 값만으로 TF 캐시 고장을 주장할 수 없다.

| sim | 코스트맵 원점 + 창 절반(2.5 m) + 고정 TF = 로봇 map 중심 |
| --- | --- |
| 165.350 | `(8.450,-3.400) + (2.5,2.5) + (-7.272,4.784) = (3.678,3.884)` |
| 170.217 | `(9.100,-3.150) + (2.5,2.5) + (-7.272,4.784) = (4.328,4.134)` |

같은 고정 TF와 두 실측 원점에 합성 캡슐 관측을 넣는 반증 시험을 추가했다.
실제 지도 조회 좌표는 캡슐 `(4.54,4.21)` 표면이다. stop이 발생한다. 도크에 묶이지 않는다.
둘째 자세는 lifted 뒤다. 시험에 캡슐을 남긴 것은 반사실 입력이다. 원본 costmap 재생은 아니다.
앞선 오프라인 시험도 고정 도크 TF를 썼다. 동적 TF를 넣어서 실패를 가린 것이 아니다.

배치 구간 발췌 5854836569는
sim 164.817–169.717의 10줄 모두 `any=none static_skipped=0`이다.
placed=164.68, lifted=169.68이다. 이는 각 표본의 **진행 띠 안**에 lethal 후보가 없었다는 뜻이다.
sim165.350은 캡슐 중심까지 약 0.92 m다. 방향은 약 21도다. heading은 20도다. 접근 중인 표본이다.
이후 heading은 접촉 구간에서 달라진다. 모든 시각에 캡슐이 진행 띠 안이었다고 단정하지 않는다.
전역/지역 격자 전체가 비었다거나 스캔 자체가 없었다는 뜻도 아니다.

지도 수신 데이터 해시는 저장소 정적 지도의 기대값과 일치한다.
이 수신 메시지가 동적 장애물을 포함한 다른 지도였다는 가설을 지지하지 않는다.
정정 댓글 5854834399도
이전의 “지도로 걸러짐” 판독을 철회했다. 앞선 any>0 구간을 캡슐 배치 시각의 증거로 쓰지 않는다.

다음 확인 대상은 배치 전후 `/scan`, local costmap, odom의 시각·좌표다.
원본 관측 없이 TF를 동적 변환으로 바꾸거나 정지 문턱을 넓히지 않는다.
배치 직후 센서 미관측·코스트맵 반영 지연·진행 띠 밖 셀을 아직 구분하지 못했다.

### 좌표 진단 필드

상세 `governor ahead` 로그는 **`stop_diagnostics=false`가 기본**이다. 평상시에는 출력하지 않는다.
진단 랩에서만 아래 명령으로 켠다. ROS 환경·도메인을 맞춘다. 기동 뒤, 주문을 보내기 전에 실행한다.

```bash
ros2 param set /amr_1/speed_governor stop_diagnostics true
ros2 param get /amr_1/speed_governor stop_diagnostics
```

켜져 있을 때 `dist / any / static_skipped / heading` 뒤에 아래 필드를 붙인다.
정적 지도 필터를 사용할 수 있으면 빈 띠도 `any=none`으로 찍는다. 진단 중에는 한 코스트맵당 한 줄이다.
진단이 끝나면 `ros2 param set /amr_1/speed_governor stop_diagnostics false`로 끈다.
토글은 로그 출력만 바꾼다. 정지 판정·속도 발행·stop/resume 사건 로그는 계속 동작한다.
예전 진단 SHA의 상시 출력과 달리, 이 옵션을 켜지 않은 회차에서 ahead 줄이 없는 것은 미관측 근거가 아니다.
`speed limit … (여유 …, 받은 코스트맵 N장)` 형식은 바꾸지 않는다.

| 필드 | 확인할 것 |
| --- | --- |
| `sim`, `stamp` | 노드 sim 수신 시각과 코스트맵 stamp. stage의 placed/lifted sim과 맞춘다 |
| `skipped_cell`, `skipped_map`, `skipped_gap` | 진행 방향으로 가장 가까운 제외 칸의 중심 상대 좌표·실제 판정 map 좌표·몸체 앞 간격. 제외 칸이 없으면 none |
| `cost_frame`, `map_frame`, `origin`, `cost_quaternion`, `size`, `res`, `tf` | 코스트맵 원점·회전·크기·해상도와 실제 lookup한 map ← costmap 변환 `(x,y,yaw rad)` |
| `map_origin`, `map_size`, `map_res` | 필터가 구독한 지도의 원점·크기·해상도 |
| `static_topic`, 지도 수신 줄의 `topic` | Subscription의 실제 이름. namespace와 런타임 remap을 반영한 필터 입력 토픽 |
| `static_value`, `static_match=(col,row,value)` | 최근접 제외 칸의 원래 지도 값과 0.15 m 이웃 탐색에서 실제로 ≥65가 나온 칸. 중심 값 0만으로 오분류라고 판단하지 않는다 |
| 지도 수신 줄의 `data_sha256` | `OccupancyGrid.data` 각 값에 1을 더한 바이트의 SHA-256. 파일 바이트의 해시와 다르다. 구독 지도와 파일을 trinary 변환한 데이터를 대조한다 |

배치 시각에 제외된 좌표가 캡슐 표면이고 실제 지도는 비었다면 필터 오분류를 조사한다.
좌표가 다른 곳이라고만 해서 변환 오류를 확정하지 않는다. 올바르게 감지한 기존 벽일 수도 있다.
코스트맵 원점·TF·odom으로 그 칸을 역산하고, 캡슐 관측이 별도로 있었는지 원본 격자와 비교한다.

### 정적 지도 대신 전역 코스트맵을 받는다는 가설 (9/27)

저장소 기본 경로는 `map_topic='map'` → `nav2.launch.py`의 `PushRosNamespace('amr_1')` →
`/amr_1/map`이다. `nav2_params.yaml`의 speed_governor 블록은 이 값을 덮어쓰지 않는다.
`navigation.launch.py`·`demo_v2.sh`의 기본 기동 경로에도 전역 코스트맵으로 remap하는 설정은 없다.
`global_costmap`은 별도 토픽이다. static/obstacle/inflation 레이어를 합친다.
지도 크기 859×534만으로 두 입력을 구분할 수는 없다.

동적 셀(65/99/100)이 지도 입력에도 들어 있으면 필터가 그 셀을 제외하는 반례를 시험으로 재현했다.
이는 **가설의 가능성**이다. 실제 구독 소스가 잘못됐다는 증거는 아니다.
별도 ROS 연결 시험은 기본 namespace, map_topic 덮어쓰기, 런타임 remap 세 경우에
실제 발행·구독으로 입력을 구분한다. ROS 없는 로컬에서는 이 세 시험을 생략한다. L2 통과로 세지 않는다.
판정식·문턱·구독 기본값은 바꾸지 않았다. 지도 수신 때 실제 토픽의 발행 노드와 QoS도 남긴다.
0ac6659에서 추가한 지도 데이터 해시와 함께 토픽·발행자·값을 대조한다.
저장소 hospital.pgm을 trinary 변환한 데이터의 기대 해시는
`bb191d2a9f6e924687cfa92bbd1d6d3805068efeabc2247bda8de0db3b20ac5c`이다.
해시 불일치만으로 전역 코스트맵이라고 단정하지 않는다. 다른 지도 파일이나 복수 발행자도 확인한다.

재검증은 **보강 후 새 SHA**를 대상으로 한다. 0ac6659 초록을 새 head 검증으로 재사용하지 않는다.
재랩은 슬롯을 배정한 뒤 시행하며, 같은 ROS 환경·도메인에서 다음 관측을 함께 남긴다.

```bash
ros2 param get /amr_1/speed_governor map_topic
ros2 node info /amr_1/speed_governor
ros2 topic info -v /amr_1/map
ros2 topic info -v /amr_1/global_costmap/costmap
```

파라미터는 상대 이름일 수 있고 remap은 반영하지 않으므로 `node info`와 로그의 실제 토픽도 확인한다.
`static_topic`이 위 둘과 다르면 그 토픽에도 `ros2 topic info -v`를 실행한다.

### 남은 후보를 가르는 기준

| 관측 | 확인할 원인 | 아직 확정할 수 없는 것 |
| --- | --- | --- |
| 배치 구간에 `ahead` 줄 없음 | 코스트맵 미관측·지연 또는 진행 띠 밖 관측. 원본 격자와 odom을 함께 본다 | `ahead`는 띠 안에 lethal 셀이 있을 때만 찍으므로, 줄이 없다는 것만으로 둘을 구분하지 못한다 |
| `any`가 있고 `dist=none`, `static_skipped>0` | 실제 좌표·TF·정적 지도 제외 결과를 대조한다 | 제외된 칸이 캡슐인지 기존 벽인지 로그만으로 모른다 |
| `dist`가 0.6 m 미만인데 첫 `stop`이 없음 | 실행 소스·stop 파라미터·직전 정지 상태와 `StopRule.update` 경로를 대조한다 | 이미 정지 중이면 반복 `stop`은 나오지 않는다 |
| 첫 `dist`가 아주 가까워진 뒤 나타남 | 스캔·5 Hz 갱신·2 Hz 발행·수신 시각과 제동 지연을 대조한다 | 문턱 확대만으로 해결된다고 단정하지 않는다 |
| `stop`은 생기지만 접촉함 | 실제 speed_limit 수신, cmd_vel, odom 속도와 제동 거리를 본다 | 감지 성공은 접촉 0의 증거가 아니다 |

기하 계산도 주의한다. 4절의 0.4 s는 캡슐 **중심**을 점으로 본 값이다.
반지름 0.2 m 표면을 정면으로 보면 첫 간격은 약 `1.5 - 0.5 - 0.2 = 0.8 m`다.
0.6 m 문턱까지는 약 0.2 m다. 1 m/s에서 0.2 s로, 2 Hz 발행 간격 0.5 s보다 짧다.
이는 지연 후보를 조사할 근거이지 회차163014의 속도·원인을 실측한 값은 아니다.

| 항목 | 기존 → 현재 | 이유 |
| --- | --- | --- |
| stop / resume / delay | 0.6 m / 0.9 m / 1 s → 동일 | 시각·좌표를 대조하기 전에 판정값을 바꾸지 않는다 |
| 진행 띠 반길이 / 반폭 | 0.5 m / 0.42 m → 동일 | 띠 밖 관측인지 현장 확인 필요 |
| 코스트맵 갱신 / 발행 | 5 Hz / 2 Hz → 동일 | 배치부터 감속기 수신까지의 지연은 미측정 |
| 정지 속도 제한 | 1% → 동일 | 0%는 Nav2의 제한 해제값이다 |

### 재검증 인계

먼저 후보 **정확한 SHA**의 별도 체크아웃에서 아래를 실행한다. 캠페인 체크아웃은 바꾸지 않는다.

```bash
python3 tools/check_repository.py
python3 tools/evidence.py validate --base origin/main
python3 -m unittest discover -s tests
ruff check .
source /opt/ros/jazzy/setup.bash
colcon build --packages-up-to rokey_p3_navigation --symlink-install
source install/setup.bash
colcon test --packages-select rokey_p3_navigation --event-handlers console_direct+
colcon test-result --verbose
```

마스터 실행은 슬롯·시각·도메인을 배정받은 뒤 한다.
회차163014와 같은 자산·주문·기동 설정, **새 로그 폴더**, 후보 SHA의 `P3_REPO`·`P3_INSTALL`을 사용한다.
[병원 런카드](../runbooks/hospital-full.md)의 녹화·기동·boot_check를 통과한 뒤
웹에서 `ord-0001 → bed_a1` 한 건을 보낸다. 기동 때 추가할 인자는 다음과 같다.

```bash
export P3_STAGE_ARGS='--block-path --traffic-dummies 0 --pedestrians 0'
P3_WORLD=hospital tools/demo_v2.sh up
```

`P3_LOG_DIR`는 **이번 회차 폴더**여야 한다. 아래 결과와 원본 로그 해시를 #240에 남긴다.
다른 회차 파일을 함께 검색하지 않는다. stage와 nav의 줄 번호를 시간순으로 합치지 않는다.

```bash
rg -n 'block_path (placed|lifted)|governor (ahead|stop|resume)|정지 규칙|speed limit|contact .*touch' "$P3_LOG_DIR"
find "$P3_LOG_DIR" -type f -name '*nav.log' -exec sha256sum {} +
find "$P3_LOG_DIR" -type f -name '*stage.log' -exec sha256sum {} +
```

`ahead`가 없으면 같은 슬롯에서 ROS 환경·도메인을 맞춘 별도 관측 터미널로
`ros2 topic info -v /amr_1/local_costmap/costmap`,
`ros2 topic hz /amr_1/local_costmap/costmap`을 확인한다.
다음 진단 회차가 필요하면 슬롯 배정 뒤 `/clock`, `/amr_1/scan`, `/amr_1/odom`,
`/amr_1/local_costmap/costmap`, `/amr_1/map`, `/amr_1/speed_limit`, `/amr_1/cmd_vel`, `/tf`, `/tf_static`을
배치 전부터 함께 기록한다. map·tf_static의 transient-local QoS와 실제 토픽 이름은 `topic info -v`로 확인한다.
원본 bag은 Git에 넣지 않는다.

완료 판정은 **placed → stop → lifted → resume, 접촉 0**이다.
더미·보행자 ON 회귀도 별도로 보고한다. 마스터 결과 댓글 ID·실행 SHA·로그 해시가 오면 PR에 연결한다.
그 전에는 원인 확정·접촉 0·수정 완료로 보고하지 않는다.
