# 실습40 — 병원 Nav2 주행: 3-9회차, 녹화 회차, 카트 제거, 속도 대조

> 2026-09-23 보완: [2–9회차 원문·목표별 수치·supersedes 정정](practice-40-source-addendum.md)을 함께 읽는다.
> 아래 기존 기록은 보존한다. 4회차 지도는 띠 지도다. 8회차 lap1 station_a 참값은 누락이다.

| 항목 | 값 |
| --- | --- |
| 날짜 | 2026-09-23, master02 |
| 실행 | `master02` 원격 실행 |
| 환경 | `hospital-nav` preset + 회차 SHA 의 `sim/scenes/hospital_navigationv1.usda` + AMR 합본 `ridgeback_ur5.usd` + `--amr-lidar` |
| 주행 | `navigation.launch.py` 다. zones·routes 는 `*.hospital.yaml` 이다. 4회차부터 `map` 은 `hospital.yaml` 이고 `nav2_final_approach:=true` 이며 `localization:=odom` 이다. 3회차는 `hospital_scan.yaml` 과 AMCL 이다 |
| 목표 | `/amr_1/go_to_zone` 6개 station_a → dock_3 → bed_b1 → dock_4 → bed_a4 → dock_1, 목표당 180 s |
| 판정 | 6/6, `/Amr/` touch 0, 정차 참값 d_xy ≤ 0.15 m(8회차부터 joint_states 참값 교차) |
| 원본 | master02 `/home/rokey/markle_tmp/` 아래 회차별 디렉토리, 각 `SHA256SUMS` |

이 문서는 실습 관찰 기록이다. frozen protocol 의 합격 evidence 가 아니다. 판정선 출처인 #240 댓글(5787797557-5790442709 가운데 병원 댓글) 원문 대조는 작성 장비에서 gh 미로그인으로 **미실행**이다. 수치는 master02 로컬 로그 기준이다.

## 관측 — 회차 표

| 회차 | 트리 | 바뀐 것 | 결과 | 멈춘 곳 원문(첫 줄) |
| --- | --- | --- | --- | --- |
| Nav2 1(표 밖 번호) | `5be029c` | 첫 Nav2 | 0/6 | station_a 180 s timeout. 이 행은 제목의 3-9회차가 아니다 |
| 3 | `d0d9e20` | 띠 지도 `hospital_scan.yaml` + AMCL | 0/6 | station_a 180 s timeout, `Failed to make progress` |
| 4 | `5c31405` | `localization:=odom` + 접근점 인계 | 3/6 | dock_4 로 가며 base `mesh_0 ↔ Geo_W_TrimStrateBase1_8` impulse 728, `ArmRiser ↔ Geo_O_DoorWall`; 내림 때 fleet exit −6 |
| 5 | `5c31405` | 전 높이 `hospital.yaml` | 3/6 | `Tray/TrayWallYPlus ↔ SM_Door_02b2/SM_Door_02b impulse=239.51 at=[22.016, -0.187, 0.415]`; fleet exit −6 |
| 6 | `3d8e376` | 로컬 costmap static layer, fleet None 수정 | 3/6 | bed_b1 출발 때 `Tray/TrayFloor ↔ SM_Door_02b impulse=564.8968 at=[22.042, -0.177, 0.357]` |
| 7 | `cb6eaa5` | 새 씬(문 제거, 개구부 1.97 m), 출발 `-8.238 4.169` | **6/6**, touch 0 | — |
| 8 (3바퀴) | `cb6eaa5` | 반복, 스테이지 새로 띄움 | **3/3 바퀴**, 6/6·touch 0 | — |
| 9 | `c6160b2` | #526 속도 두 배(Nav2 1.0, 추종기 0.8 m/s) | **6/6**, touch 0 | — |
| 녹화1 | main `9186933` | 발표 후보 | 2/6 | bed_b1 로 가며 `No valid trajectories out of 3338!` 150줄 → `Controller patience exceeded` → `GoToZone bed_b1 실패: nav2_status_6` |
| 녹화2 카트 제거 (3바퀴) | `694ac9b` | #541 `SM_SupplyCart_02a_28` deactivated | 0/3 바퀴 | L1·L2 `Tray/TrayWallXPlus ↔ Geo_M_CornerTrim21 impulse=937.55 / 720.75 at=[14.1, 4.158, 0.415]`; L3 `Tray/TrayFloor ↔ SM_SideTable_02a_79 impulse=269.22` |
| 속도 대조 (3바퀴) | `f5f7657` | 694ac9b 에서 속도만 원래대로 | **3/3 바퀴**, 6/6·touch 0 | — |
| 가운데 주행 (3바퀴) | `0eab978` | 694ac9b + 전역 inflation 1.5·기울기 1.0, 속도 두 배 | 0/3 바퀴 (각 4/6) | bed_b1 → dock_4 출발 때 `ArmRiser ↔ SM_BedSideTable_01b2_04 impulse=58.29 / 123.61`, L3 base `mesh_0` 584.10 |
| main (3바퀴) | `e4ae5ab` | #541·#542·#547 머지 뒤 main | 2/3 바퀴 | L3 `GoToZone station_a 실패: nav2_unavailable`(12 s, Nav2 기동 전 goal) |

### 수치

- 7회차 d_xy(fleet 피드백) 0.0191-0.0204, 한 바퀴 약 6분(rtf 1.000).
- 8회차 참값 d_xy 0.0185-0.0198, |d_yaw| ≤ 0.019. 한 바퀴 sim 약 346-365 s. rtf 0.491 / 0.543 / 0.978.
- 9회차 참값 d_xy ≤ 0.0198, odom 최고 |v| 1.000 m/s, 한 바퀴 sim 237 s(7회차 대비 약 34% 짧음).
- 속도 대조 f5f7657: 참값 d_xy 0.0181-0.0197, CornerTrim21·SideTable 은 near 줄도 없음. bed_b1 yaw 마무리 ≤ 8 s.
- main e4ae5ab L1·L2: 391 s·401 s, rtf 0.953·0.933, 참값 d_xy ≤ 0.0196.
- 694ac9b L1 은 bed_b1 자리(참값 d_xy 0.0190)에서 `yaw 만 맞춘다` 뒤 180 s timeout(rc 124).

### 녹화

Isaac 창만 gst `ximagesrc`로 잡았다. 전체 해시는 각 디렉토리 `SHA256SUMS`에 있다.

| 파일(`markle_tmp/` 아래) | SHA-256 앞 16자 |
| --- | --- |
| `m2-hospital-nav-l3b/nav2/clip-nav2.mkv` | `3979653c24d87611` |
| `m2-hospital-nav2-r3/clip-r3.mkv` | `6e6ebc1113f62d66` |
| `m2-hospital-nav2-r4/clip-r4.mkv` | `45d2aaa72a1a8ece` |
| `m2-hospital-nav2-r5/clip-r5.mkv` | `4ec272013a17c28c` |
| `m2-hospital-nav2-r6/clip-r6.mkv` | `33a19114e87b4411` |
| `m2-hospital-nav2-r7/clip-r7.mkv` | `ec59aca69fa6bd3d` |
| `m2-hospital-nav2-r8/lap1/clip-lap1.mkv` | `9c1b154db1689068` |
| `m2-demo-hosp-9186933/lap1/clip-lap1.mkv` | `98944684fcf81ba3` |
| `m2-hosp-694ac9b/lap{1,2,3}/clip-lap*.mkv` | `0aa4d3ce93a47687` / `0eafe49e62848b0d` / `203be5e74e4251a0` |
| `m2-hosp-f5f7657/lap{1,2,3}/clip-lap*.mkv` | `7ebd0d9d84f5d341` / `7a8eccf8be862609` / `fc858c83f88c3532` |
| `m2-hosp-0eab978/lap{1,2,3}/clip-lap*.mkv` | `5bdd042fa9f3a35c` / `071a4793b50619aa` / `5693abe16d08eb37` |
| `m2-hosp-main-e4ae5ab/lap{1,2,3}/clip-lap*.mkv` | `4022b856027c2263` / `df414349b85d251f` / `2775721c2094dfa6` |

- 8회차 lap2·lap3, 9회차는 콘솔 잠김(12:31:07 부터)으로 녹화가 0 B 이거나 검은 화면이다(9회차 `clip-lap1-root.mkv` `cd94f1abe3300d61`).
- 녹화1 abort 자리는 재범이 14:44 캡처로 알렸다: AMR 이 약품 카트와 벽 사이에 멈춤. 사본 `m2-demo-hosp-9186933/lap1/shots/user-stuck-1444.webp`(`e24a857b920297aa`).

## 해석

- 4-6회차 실패는 트레이·받침처럼 본체 밖으로 나온 부분이 문짝·몰딩에 닿은 것이다. 문을 없앤 새 씬(7회차)부터 원래 속도에서 6/6 이 반복됐다(7·8회차, 속도 대조).
- 녹화1 abort 는 복도 카트(폭 약 1.2 m 복도 vs footprint 0.9 m, 해석)로 보이며, 카트를 뺀 694ac9b 에서 `No valid trajectories` 는 0 이 됐다.
- 속도 두 배(#526)에서만 고정물 touch 가 났고, 같은 씬에서 속도만 되돌린 f5f7657 은 3/3 이다. inflation(0eab978)은 복도 touch 를 없앴지만 bed_b1 출발 회전에서 협탁 touch 가 새로 생겼다.
- rtf 가 같은 조건에서 0.47-1.0 으로 흔들렸다. 원인은 확인하지 않았다(**미실행**). 목표별 벽시계 시간은 rtf 에 따라 달라지므로 비교는 sim 시간으로 한다.
- main e4ae5ab L3 의 `nav2_unavailable` 은 실행 절차(Nav2 활성 전 goal)로 보이며 주행 결함으로 판정하지 않는다. 재실행은 **미실행**이다.

## 미실행

- #240 판정선 원문 대조, rtf 변동 원인, 0eab978 복도 가운데 주행 여부(뷰포트가 로봇을 비추지 않아 캡처로 판정 못 함), e4ae5ab L3 재실행.
