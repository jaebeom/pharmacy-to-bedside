# 병원 주행 2–9회차 — 실습39·40 원문 대조 보완

기록일: 2026-09-23. 문서 대조 기준: `cfc6a5301824a48d8adf168a6d61678a9bc24a63`.
PR #556의 실습39·40을 이어 받는 **문서 대조 기록**이다.
새 실습이나 현장 재실행이 아니다. 실습 번호를 새로 배정하지 않는다.

## 범위와 출처

후속 PR #556이 같은 회차를 실습39·40으로 통합했다. 이슈 #507·#515·#516·#518·#519·#525·#533은 별도 실습40–46을 요청했다.
그 기록을 중복 작성하지 않는다. 이미 다른 내용으로 쓰인 번호를 덮어쓰지 않는다.
누락된 목표별 수치·클립 크기·실패·버린 시도를 아래 GitHub 원문 발췌로 보완한다.
[실습39](practice-39.md) → [실습40](practice-40.md) → 이 보완 순서로 읽는다.

아래 인용은 #240에 게시된 master02 보고다.
관측·덧붙인 해석·당시 다음 회차 계획을 원문의 구분 그대로 보존한다.
GitHub 취소선 오독을 막기 위해 원문의 `~`가 있는 경로·범위만 코드 표기로 감쌌다. 작성·게시 표기 줄은 뺐다. 그 밖의 문자·수치는 바꾸지 않았다.
**인용 안의 계획은 현재 실행 지시가 아니다.**
이 문서 작성자는 Isaac·ROS·master02 원본 파일에 접근하거나 실험하지 않았다.
GitHub 보고와 문서의 대조만 완료했다. 원본 클립·로그·SHA256SUMS 재검증은 **미실행**이다.
해시 앞 16자는 보고값이다. 클립 크기도 보고값이다. 이 문서 작성 중 다운로드하거나 해시를 계산한 결과가 아니다.

| 원본 요청 | 당시 요청 번호 | 현재 통합 기록 | #240 근거 |
| --- | --- | --- | --- |
| #507 | 실습40 | 실습39 waypoints + 실습40 첫 Nav2 | 5787139396 |
| #515 | 실습41 | 실습40 3회차 | 5787797557 |
| #516 | 실습42 | 실습40 4회차 | 5787872606 |
| #518 | 실습43 | 실습40 5회차 | 5787953147 |
| #519 | 실습44 | 실습40 6회차 | 5788019916 |
| #525 | 실습45 | 실습40 7회차 | 5788371477 |
| #533 | 실습46 | 실습40 8·9회차 | 5788806988 |

판정선 대조: [병원 주행 런북](../../runbooks/hospital-nav-l3.md) 3·6절.
현재 런북은 여러 회차 뒤에 개정됐다. 현재 설정이나 공차를 과거 회차에 소급 적용하지 않는다.
아래 수치는 각 보고 당시 수치다. 새 합격 evidence나 성공률을 만들지 않는다.

## supersedes — 기존 문장을 대신하는 제한적 정정

supersedes 대상은 기준 SHA의 다음 문장·해석 범위뿐이다. 기존 일지와 원문은 삭제하지 않는다.

| 기존 문장 또는 누락 | 대조 결과와 적용 범위 |
| --- | --- |
| 실습39의 “참값 교차는 이 두 회차에서 미실행” | 2회차 원문은 **참값 d_xy 0.0184–0.0193, d_yaw ≤ 0.019**라고 보고했다. “2회차 보고에 참값이 없다”는 뜻으로 읽지 않는다. 반면 실습39의 “joint_states 교차”에 해당하는 수집 방법은 이 원문만으로 확인할 수 없다. 1회차나 2회차 재연에 이 값을 전용하지 않는다. |
| 실습40 머리의 “4회차부터 map은 hospital.yaml” | 4회차는 **hospital_scan 띠 지도**다. 5회차부터 **hospital.yaml 전 높이 지도**다. localization:=odom은 4회차부터다. #240 4회차에 덧붙인 해석과 맞다. 런북 6절의 4·5회차 구분과도 맞다. |
| 실습40의 8회차 참값 범위만 있는 요약 | lap1 station_a 참값은 **누락**이다. 성공 보고와 독립 참값 수집 완결성은 다르다. 3바퀴 참값 18/18로 주장하지 않는다(원문은 17/18). |
| 실습39·40의 #240 원문 대조 미실행 | 이 보완에 수록한 **2–9회차 7개 댓글의 대조만 완료**했다. 실습39 1회차·재연, 실습40 녹화·카트 제거·후속 속도 대조·e4ae5ab 회차의 전수 대조는 미실행으로 남긴다. |

원인·기준에 관한 새 해석은 더하지 않는다.
예를 들어 2회차 Nav2 정지의 두 원인 후보와 4회차 몰딩 가림 설명은 게시 때 덧붙인 해석이다.
5회차 bed_b1에는 원문상 끝 자세·yaw만 있으므로 d_xy를 새로 계산해 채우지 않는다.
7회차 d_xy는 fleet 피드백이다. 참값 교차는 미실행이다.
8·9회차 wall 시간·rtf·sim 시간은 원문값을 그대로 옮긴다. 반올림·합산·재환산하지 않는다.
버린 시도 두 건과 녹화 0 B·검은 화면도 아래 원문에 남긴다.

## 요청 식별 기록

아래 ID와 updated_at은 읽은 요청 버전이다. 이 표 자체는 병합·작업 완료 마커가 아니다.

- #507: updated_at `2026-09-23T00:58:55Z`, 요청 댓글 ID `5787139710`.
- #515: updated_at `2026-09-23T02:16:50Z`.
- #516: updated_at `2026-09-23T02:25:24Z`.
- #518: updated_at `2026-09-23T02:34:13Z`.
- #519: updated_at `2026-09-23T02:40:10Z`.
- #525: updated_at `2026-09-23T03:17:05Z`.
- #533: updated_at `2026-09-23T04:03:47Z`.

## 회차별 원문 발췌

### 2회차 — 요청 #507

출처: #240 댓글 5787139396, updated_at `null`.

> master02 보고 요약(원문 master02 `~/markle_tmp/m2-hospital-nav-l3b/`, SHA256SUMS `3b7c506d60cc2b5c…`)
>
> ## 병원 씬 주행 L3 2회차 (`5be029c` = #504, 도메인 121, **창 모드**)
> **① waypoints: goal 6/6 완주** — PDF 기대 경로 셋(A1→B, A3→C2 병실, A4→D4) + 복귀.
> - 참값 d_xy 0.0184–0.0193, d_yaw ≤ 0.019. `/Amr/` touch **0**(C2 문 통과 — #504 가 1회차 끊김을 닫았다). 최소 near: DoorFloor sep 0.0091.
> - 기동 확인 전부 성립(병상 6, ridgeback 끔, 출발 자리). Traceback·ERROR 0, **rtf 1.002**.
> - 클립 `wp/clip-wp.mkv` 133,761,997 B sha256 `7872fae846d3e094…` 8:52.
>
> **② Nav2(`--amr-lidar`): goal 0/6**
> - 라이다는 섰다: `amr lidar prim=…/lidar_link config=Example_Rotary_2D mount_local=(0.48, 0.0, 0.2) topic=/amr_1/scan`, disabled WARN 0, scan 16.0 Hz, tf base→lidar (0.480, 0, 0.200). initialpose 뒤 AMCL (−8.233, 3.860), Nav2 active.
> - station_a 로 약 15 m 가서 참값 (6.768, 2.717)에서 멈춤 — 목표 (7.322, 2.801)까지 0.56 m. 그때 AMCL (7.076, 2.823) = 참값보다 x +0.31 m. fleet distance_remaining 0.222. controller_server `Failed to make progress` → `[follow_path] Aborting handle` ×4, local costmap clear 반복. touch 0. 3분 무진전으로 취소.
> - down 때 fleet 가 SIGINT·SIGTERM 에 안 내려가 SIGKILL(Nav2 goal 이 걸린 채). rtf 0.523(Nav2+라이다+창).
> - 클립 `nav2/clip-nav2.mkv` 40,939,271 B sha256 `3979653c24d87611…` 2:43, 캡처 `nav2/stuck-095717.png`.
>
> 덧붙임(해석): 병원 주행은 **waypoints 로 성립**했다. Nav2 가 선 원인 후보 둘 — (1) station_a 정차 자세는 데스크에서 몸체 기준 0.05 m 인데 Nav2 footprint(1.10×0.90, 반길이 0.55)로는 앞끝이 데스크에 닿는 자리라 목표에 들어갈 궤적이 없다 (2) AMCL 이 0.31 m 어긋났다 — 지도는 z 0.10–1.80 을 모두 투영했는데 라이다는 0.25 m 한 높이만 본다(탁자·데스크 윗면은 지도에 있고 스캔에는 없다). 고침은 다음 PR.

### 3회차 — 요청 #515

출처: #240 댓글 5787797557, updated_at `null`.

> master02 보고 (2026-09-23 11:16 KST)
>
> ### 병원 씬 주행 L3 3회차 (Nav2)
>
> 원문:
> > 병원 Nav2 3회차 결과입니다(d0d9e20, porcelain 0, 도메인 121, 창 모드).
> > - 도달 **0/6**. station_a 에서 180 s 초과로 멈췄습니다.
> > - 기동: lidar 줄 있음, scan 16.8 Hz, map `maps/hospital_scan.yaml`, initialpose 뒤 AMCL (−8.234, 3.860), Nav2 active.
> > - 끊긴 곳: `[controller_server] Failed to make progress` ×6(첫 번째 sim ≈68). 참값 (6.633, 2.956) 에서 멈췄고, station_a (7.322, 2.801) 까지 d_xy **0.706** 남았습니다. yaw −0.027.
> >   - AMCL (6.796, 2.888). 참값과 0.18 m 차이로, 2회차의 0.31 에서 줄었습니다. fleet distance_remaining 0.252.
> >   - `final approach` 관련 로그 줄은 nav.log 에 **0** 입니다. nav2_final_approach:=true 가 먹었는지 로그로는 확인하지 못했습니다.
> > - touch 0.
> > - down(#511): `[fleet-2]: process has finished cleanly` — **SIGKILL 0, Traceback 0**. 고쳐졌습니다.
> > - rtf 0.550. 잔여 0.
> > - 클립 `~/markle_tmp/m2-hospital-nav2-r3/clip-r3.mkv` 48,275,053 B sha256 6e6ebc1113f62d66… 3:12. 단계 캡처 shots/station_a-start·end. SHA256SUMS 4c14495b678e194e….
>
> 덧붙임(해석):
> - `d0d9e20` 의 fleet 는 접근점 **도착 뒤에만** 로그를 낸다. 도착하지 못했으니 로그 0 은 인자 미적용의 근거가 아니다. station_a 행 경로의 접근점은 (7.022, 2.801)이고, AMCL 자세에서 그 점까지 0.24 m 가 fleet distance_remaining 0.252 와 맞는다. 목표가 접근점이었다는 쪽이다.
> - 정지 자리는 접근점 0.25 m 앞으로 goal 공차 0.2 밖이다. 대응은 #514(넘김 반경 0.5, `localization:=odom`). 4회차는 시험 SHA `5c31405`.

### 4회차 — 요청 #516

출처: #240 댓글 5787872606, updated_at `null`.

> master02 보고 (2026-09-23 11:24 KST)
>
> ### 병원 씬 주행 L3 4회차 (Nav2 + 넘김 반경 + localization:=odom)
>
> 원문:
> > 병원 Nav2 4회차 결과입니다(5c31405, porcelain 0, 도메인 121, 창 모드, localization:=odom). 도달 **3/6**.
> > - station_a: d_xy 0.0185 / yaw 0.000. 인계 줄 있음(`접근점 (7.022, 2.801) 0.50 m 안이다. Nav2 goal 을 거둔다` → `status 5 로 끝났다. 접근점부터 추종기로 간다`).
> > - dock_3: d_xy 0.0192 / yaw 0.018. 인계 줄 있음(접근점 (−2.256, 3.602)).
> > - bed_b1: d_xy 0.0193 / yaw −0.002. C2 문 앞에서 `Failed to make progress` ×8 이 나왔지만 복구했고, 인계 줄 있음(접근점 (21.729, 1.412)). 180 s 안에 도착했습니다.
> > - **끊김 — dock_4 로 가는 길**: `Failed to make progress` ×2 뒤 `touch a=/World/P3Pharmacy/Amr/base_link/collisions/mesh_0 b=…/hospital/Geo_W_TrimStrateBase1_18/Geo_W_TrimStrateBase1_8/Geo_W_TrimStrateBase1_8 impulse=728.11 sep=-0.0016 at=[20.884, 0.609, 0.157] sim=317.9`.
> >   - 이어서 `ArmRiser ↔ Geo_O_DoorWall_918/…/Section1 impulse=174.97 sim=338.85` 도 있었습니다. C2 문을 되돌아 나오면서 몸체와 받침이 벽 하단 몰딩과 문 벽에 닿았습니다.
> >   - 멈춘 자리 (21.368, 0.354). goal 을 취소했습니다.
> > - down: fleet 가 SIGKILL 없이 내려갔지만 `[fleet-2]: process has died … exit code -6`(abort) 입니다. Traceback 0. 3회차의 finished cleanly 와 다릅니다.
> > - rtf 0.978. 잔여 0.
> > - 클립 `~/markle_tmp/m2-hospital-nav2-r4/clip-r4.mkv` 75,683,035 B sha256 45d2aaa72a1a8ece… 5:05. 단계 캡처 shots/(goal 시작·끝 + dock_4-touch). SHA256SUMS 5f4055840d480cd8….
>
> 덧붙임(해석):
> - 넘김(#514)은 도착한 셋 모두에서 나왔고, 정차 오차 0.019 m 안팎은 waypoints 2회차와 같은 수준이다.
> - 닿은 몰딩은 z 0.157 이다. 4회차 지도 `hospital_scan`(z 0.18–0.32 띠)에는 없고, 라이다(0.256)에도 안 보인다. Nav2 가 스스로 짠 경로가 벽에 붙어도 costmap 이 막지 못했다는 쪽이다. `localization:=odom` 에서는 AMCL 용 띠 지도가 필요 없으므로, 5회차는 전 높이 지도 `hospital.yaml`(z 0.10–1.80)로 같은 SHA 를 돈다.
> - fleet exit -6 은 원인 미확인. 5회차에서 죽기 직전 줄을 받는다.

### 5회차 — 요청 #518

출처: #240 댓글 5787953147, updated_at `null`.

> master02 보고 (2026-09-23 11:33 KST)
>
> ### 병원 씬 주행 L3 5회차 (Nav2, 전 높이 지도)
>
> 원문:
> > 병원 Nav2 5회차 결과입니다(5c31405, map:=maps/hospital.yaml, porcelain 0, 도메인 121, 창 모드).
> > - **3/6** 도착:
> >   - station_a: d_xy 0.0190 / yaw −0.001
> >   - dock_3: d_xy 0.0194 / yaw 0.013
> >   - bed_b1: 도착 SUCCEEDED 11:29:13(끝 자세 (21.754, 1.640), yaw −2.967)
> >   - 인계 줄("Nav2 goal 을 거둔다 … 추종기로")은 3번 모두 있습니다.
> > - **C2 문 통과 중 Failed to make progress 0회**(4회차 8회).
> > - **touch(bed_b1 로 가며 C2 문 통과 중)**:
> >   - `a=/World/P3Pharmacy/Amr/base_link/Tray/TrayWallYPlus b=…/hospital/SM_Door_02b2/SM_Door_02b impulse=239.51 sep=0.0059 at=[22.016, -0.187, 0.415] sim=170.95`
> >   - 같은 자리에서 TrayWallXPlus ↔ 문짝 impulse 0.66.
> >   - 트레이 벽이 문짝(열린 문)에 닿았습니다. goal 이 곧 도착으로 끝나서, 다음 dock_4 를 보낸 직후 제가 취소했습니다.
> > - **down fleet exit −6 원인**(fleet 마지막 줄 원문):
> > ```
> > [fleet] Nav2 가 cancel 뒤 종결을 알리지 않았다. 결과 없이 끝낸다.
> > [fleet] GoToZone dock_4 실패: None
> > python3: …/rosidl_generator_py/rokey_p3_interfaces/action/_go_to_zone_s.c:182: rokey_p3_interfaces__action__go_to_zone__result__convert_from_py: Assertion `PyUnicode_Check(field)' failed.
> > [ERROR] [fleet-2]: process has died [pid 595216, exit code -6, …]
> > ```
> >   → 취소된 goal 의 결과 `message` 에 None 을 넣어 rosidl 변환이 assert 로 죽습니다(해석). 4회차 −6 도 같은 경로일 것으로 봅니다. 전체 30줄은 `~/markle_tmp/m2-hospital-nav2-r5/fleet_last30.txt` 에 있습니다.
> > - Traceback 0, SIGKILL 0. rtf 1.002.
> > - 클립 clip-r5.mkv 37,748,617 B sha256 4ec272013a17c28c… 2:32. shots/(goal 시작·끝 + bed_b1-touch). SHA256SUMS f713b5d2b6722362….
>
> 덧붙임(해석):
> - 닿은 자리 (22.016, −0.187)는 C2 병실 안으로 열린 문짝의 끝이다. 전 높이 지도에는 그 칸이 막혀 있다. 4회차 몰딩도 전 높이 지도에는 있다. `nav2_params` 의 로컬 costmap 이 static layer 없이 스캔만 쓰고 있었고, 라이다(앞 범퍼)의 옆·뒤 사각이 비어 있었다는 쪽이다.
> - 고침: 로컬 static layer(#514 `2e602fd`), 종료 None message(#511 `1323cf6`·`e2d9f5f`). 6회차 시험 SHA `3d8e376`.
> - #517 캡처 2 는 bed_b1(D5) 정차 자리다 — 이 문짝과 벽·협탁 사이 공간.

### 6회차 — 요청 #519

출처: #240 댓글 5788019916, updated_at `null`.

> master02 보고 (2026-09-23 11:40 KST)
>
> ### 병원 씬 주행 L3 6회차 (Nav2, 로컬 static layer)
>
> 원문:
> > 병원 Nav2 6회차 결과입니다(3d8e376, porcelain 0, colcon 7/7 다시 빌드, 5회차와 같은 인자, 창 모드).
> > - **3/6**: station_a·dock_3·bed_b1 SUCCEEDED(11:35:43 / 11:36:15 / 11:37:41). 인계 줄 3번.
> > - **C2 문 통과(bed_b1 가는 길) Failed to make progress 0회**, touch 없음 → 5회차의 bed_b1 접근 touch 는 이번엔 없었습니다.
> > - **bed_b1 출발(→dock_4, 11:37:44) 때 touch**. 무진전·recovery 줄은 0입니다:
> >   `Tray/TrayFloor ↔ SM_Door_02b2/SM_Door_02b impulse=564.90 at=[22.042,-0.177,0.357] sim=184.90`(+TrayWallXPlus 3.78). 5회차와 같은 문짝 끝이고, 이번엔 트레이 바닥이 닿았습니다.
> > - 바로 앞에 `Begin navigating from (21.73, 1.94) to (0.68, 3.59)`, 이어서 `mesh_2~4` ↔ Geo_M_DoorFloor23 near 줄이 있습니다.
> > - **down fleet**: `[INFO] [fleet-2]: process has finished cleanly [pid 600706]` → exit -6 은 재현되지 않았습니다.
> > - Traceback 0, rtf 0.962. 남은 프로세스 0(stub_arm 1개는 손으로 정리).
> > - 클립 `~/markle_tmp/m2-hospital-nav2-r6/clip-r6.mkv` 50,936,191 B sha256 33a19114e87b4411… 3:23. shots 8장(+dock_4-touch). SHA256SUMS 6445c191264bf733….
> > - 제안(관측 근거): 로컬 static layer 로 들어갈 때는 피했지만, 나올 때(22,−0.18 문짝 끝) 회전하면서 트레이가 문짝을 쓸고 지나갑니다. footprint 가 트레이 돌출을 덮는지 확인이 필요해 보입니다.
>
> 덧붙임(해석):
> - 트레이는 base_link 로컬 x −0.18…0.44, y ±0.33 이고 Nav2 footprint(±0.55, ±0.45) 안이다. 돌출이 footprint 밖으로 나가지는 않는다. 얇은 문짝 끝(지도 칸 한두 개)을 회전하며 스치는 쪽으로 본다(미확인).
> - 이 문짝은 @parksejun12 의 새 씬(#517 5787970639: 문 제거·틈 확대)에서 사라진다. 병원 주행은 새 씬 + 지도·zones·routes 재생성 뒤 7회차로 간다. footprint padding 은 모든 정차 자리가 고정물 옆 0.05 m 라 출발이 막힐 수 있어 지금은 넣지 않는다.
> - #511 종료 고침은 이 회차에서 `finished cleanly` 로 확인.

### 7회차 — 요청 #525

출처: #240 댓글 5788371477, updated_at `null`.

> master02 보고 (2026-09-23 12:16 KST)
>
> ### 병원 씬 주행 L3 7회차 (#523 새 씬 + #524 재생성, Nav2) — 판정선 통과
>
> 원문:
> > 병원 Nav2 7회차(새 씬) 결과입니다(cb6eaa5, porcelain 0, colcon 7/7, --amr-start -8.238 4.169, 창 모드). 판정선 모두 통과했습니다.
> > - **도착 6/6** SUCCEEDED, 12:09:36 → 12:15:33 ALL DONE. goal 마다 약 `30~80` s.
> > - **정차 d_xy**(fleet 피드백의 마지막 distance_remaining):
> >   - station_a 0.0204, dock_3 0.0192, bed_b1 0.0204
> >   - dock_4 0.0191, bed_a4 0.0191, dock_1 0.0195
> >   - 모두 ≤ 0.15 입니다. 시뮬 참값(joint_states)으로 교차 확인은 미실행입니다.
> > - **touch 0**(`/Amr/` touch 줄 없음). Failed to make progress 0, Traceback 0.
> > - **스테이지 로그**: `"deactivated": ["ridgeback_ur5", "Graph", "gripper"]`, `"missing": []`.
> > - **WARN 줄 수**: "WARN" 문자열 0줄. 대소문자 무시 warn 120줄(그중 `[Warning]` 119줄, Kit 경고).
> > - **down**: `[INFO] [fleet-2]: process has finished cleanly [pid 609075]`. rtf 1.000, 남은 프로세스 0.
> > - **녹화·캡처**: 클립 `~/markle_tmp/m2-hospital-nav2-r7/clip-r7.mkv` 97,835,292 B sha256 ec59aca69fa6bd3d…(약 6분). shots 13장. SHA256SUMS aca10ac16131e928….
>
> 덧붙임(해석):
> - 런북 6절 판정선(도착 6/6, touch 0, d_xy ≤ 0.15)을 처음 모두 넘었다. d_xy 는 fleet 가 본 값(map TF = odom)이고 참값 교차 확인은 미실행이다.
> - 설정: Nav2 + 접근점 0.5 m 넘김 + 로컬 static layer(#514), 전 높이 지도 + `localization:=odom`, 새 씬(문 없음, #523·#524).
> - 다음(8회차): 같은 SHA 로 **스테이지를 새로 띄워 한 바퀴씩 3번** 돈다 — 반복 재현과 소요 시간 분포. 판정선(결과 전 고정): 바퀴마다 6/6, touch 0, d_xy ≤ 0.15, 참값(joint_states 또는 스테이지 자세) 교차 확인 포함.

### 8·9회차 — 요청 #533

출처: #240 댓글 5788806988, updated_at `null`.

> master02 보고 (2026-09-23 13:03 KST)
>
> ### 병원 씬 주행 L3 8회차(반복 재현 3바퀴)·9회차(속도 두 배) — 둘 다 판정선 통과
>
> 원문:
> > 8·9회차를 묶어 보고합니다. 참값은 joint_states dummy x·y·yaw + 출발 자리(−8.238, 4.169)와 zones.hospital.yaml 의 차이입니다.
> >
> > **8회차(cb6eaa5), 바퀴마다 스테이지 새로 띄움: 3/3 바퀴 통과.** 바퀴마다 6/6, touch 0, 무진전 0.
> > - 참값 d_xy `0.0185~0.0198,` d_yaw |≤0.019|.
> > - lap1 station_a 는 참값 누락입니다(스크립트 구독 실패, fleet 피드백으로는 도착).
> > - 한 바퀴 wall 시간: 723 s / 638 s / 373 s. rtf 는 0.491 / 0.543 / 0.978 입니다. sim 시간으로 환산하면 약 355 / 346 / 365 s 로 7회차(약 357 s)와 같습니다.
> > - 앞 두 바퀴 rtf 가 절반인 원인은 미확인입니다.
> > - 절차 사고: lap1 뒤 제 내림 스크립트가 nav 를 못 내린 상태로 lap2 스테이지가 뜨려 했습니다. 즉시 모두 내리고 lap2 부터 다시 돌렸습니다(버린 폴더 lap2-aborted-leftover-nav). 이후 프로세스 그룹 단위로 내리게 고쳤고, 남은 프로세스는 매 바퀴 0 입니다.
> > - Traceback 바퀴마다 3줄. 모두 내림 뒤 ExternalShutdownException(zones_tf·base_driver·dock_origin_tf)으로, 제 이중 SIGINT 때문입니다.
> > - fleet 은 매 바퀴 "process has finished cleanly".
> > - 녹화: lap1 만 있습니다(clip-lap1.mkv 181,817,846 B sha 9c1b154db1689068…).
> >   - **12:31:07 부터 콘솔이 잠김(LockedHint=yes, 모니터 Off)** 이라 lap2·3 녹화는 X 오류(BadMatch X_ShmGetImage)로 0 B 입니다.
> >   - 단계 캡처는 있지만 검은 화면입니다.
> >
> > | 목표 | L1 s / d_xy | L2 s / d_xy | L3 s / d_xy | 9회차 s / d_xy |
> > |---|---|---|---|---|
> > | station_a | 97 / (누락) | 72 / 0.0194 | 42 / 0.0188 | 48 / 0.0189 |
> > | dock_3 | 57 / 0.0195 | 52 / 0.0191 | 33 / 0.0191 | 38 / 0.0196 |
> > | bed_b1 | 133 / 0.0190 | 121 / 0.0189 | 69 / 0.0194 | 78 / 0.0191 |
> > | dock_4 | 125 / 0.0192 | 113 / 0.0188 | 64 / 0.0185 | 74 / 0.0198 |
> > | bed_a4 | 130 / 0.0194 | 115 / 0.0196 | 65 / 0.0191 | 74 / 0.0196 |
> > | dock_1 | 162 / 0.0193 | 147 / 0.0194 | 82 / 0.0196 | 93 / 0.0191 |
> > | 합(wall) / rtf | 723 / 0.49 | 638 / 0.54 | 373 / 0.98 | 426 / 0.51 |
> >
> > **9회차(c6160b2, 속도 두 배): 통과.** 6/6, touch 0, 무진전 0, 참값 d_xy ≤ 0.0198.
> > - odom 최고 속도 |v| = **1.000 m/s**(1.0 에 닿음), |wz| 최대 1.501. 표본 8,380개.
> > - 한 바퀴 426 s wall, rtf 0.507. sim 시간 237 s 로 7회차 약 357 s 대비 약 34% 짧습니다.
> > - 첫 시도는 제 대기 조건 실수로 버렸습니다. localization 쪽 "active" 줄을 보고 Nav2 가 뜨기 전에 goal 을 보내 nav2_rejected 가 났습니다. 대기를 navigation 쪽으로 고쳐 다시 돌린 것이 위 결과입니다.
> > - 녹화는 잠김 때문에 검은 화면뿐입니다(clip-lap1-root.mkv sha cd94f1abe3300d61…). SHA256SUMS 9395fc26f0740463….
> > - 잠금 해제는 사람 손이 필요합니다. 영상이 필요하면 잠금 해제 뒤 9회차를 다시 돌리겠습니다.
>
> 덧붙임(해석):
> - 반복 재현: 스테이지를 새로 띄운 3바퀴 모두 6/6·touch 0, 참값 d_xy 0.0185–0.0198(17/18 목표 참값, 1 누락). sim 시간 한 바퀴 346–365 s 로 흩어짐이 작다. wall 시간은 rtf 에 묶여 있고 rtf 가 절반으로 떨어진 원인은 미확인이다(해석하지 않는다).
> - 속도 두 배(#526): odom 이 1.0 m/s 에 닿았고 판정선 그대로 통과, sim 시간 −34%.
> - 버린 시도 둘(8회차 lap2 첫 기동, 9회차 첫 시도)은 절차 사고로 판정에서 뺐고 폴더를 남겼다. 영상은 콘솔 잠금 해제 뒤 다시 찍는다.
