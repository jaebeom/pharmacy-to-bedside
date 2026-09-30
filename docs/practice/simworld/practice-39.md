# 실습39 — 병원 waypoints 주행 1·2회차 (#505)

> 2026-09-23 보완: [2회차 원문 대조와 제한적 정정](practice-40-source-addendum.md)을 함께 읽는다.
> 아래 기존 기록은 보존한다. 참값 보고와 joint_states 수집 방법의 확인 여부를 구분한다.

| 항목 | 값 |
| --- | --- |
| 날짜 | 2026-09-23, master02 |
| 실행 | `master02` 원격 실행 |
| 환경 | preset 은 `hospital-nav` 다. 씬은 `hospital_navigationv1.usda` 다. AMR 합본은 `ridgeback_ur5.usd` 다. `--amr-start` 는 `-8.234 3.86` 이다 |
| 주행 | `navigation.launch.py motion_backend:=waypoints use_nav2:=false`, zones·routes `*.hospital.yaml`, 팔 인터록은 `stub_arm` |
| 목표 | `/amr_1/go_to_zone` 6개 순서 station_a → dock_3 → bed_b1 → dock_4 → bed_a4 → dock_1, 목표당 180 s |
| 멈춤 기준 | `/Amr/` 링크 touch, 180 s 초과, 거부 |
| 원본 | master02 `/home/rokey/markle_tmp/` 아래 `m2-hospital-nav-l3/wp`, `m2-hospital-nav-l3b/wp`, `m2-hospital-nav-show-1020/wp` |

이 문서는 실습 관찰 기록이다. frozen protocol 의 합격 evidence 가 아니다. 판정선 출처인 #240 댓글 5787005979·5787139396 원문과의 대조는 작성 장비에서 gh 미로그인으로 **미실행**이다.

## 관측

| 회차 | 실행 트리 | 모드 | 결과 | 멈춘 곳 원문 | rtf |
| --- | --- | --- | --- | --- | --- |
| 1 | `c511c5eb96bb6e271670b29c3f6229b19e0c566e` | headless(콘솔 잠김 09:31:27) | 2/6. station_a 와 dock_3 는 SUCCEEDED 다 | bed_b1 로 가며 `a=/World/P3Pharmacy/Amr/base_link/ArmRiser b=…/hospital/Geo_M_DoorFrame26/Geo_M_DoorFrame/Geo_M_DoorFrame impulse=123.4742 sim_time=185.500` | 0.818 |
| 2 | `5be029ca3806cc31c7da02555bad063eeb580e7e` | 창 모드 + 녹화 | **6/6**, touch 0, 09:43:36 → 09:52:12 | — | 1.002 |
| 2 재연 | `5be029c`(같은 트리) | 창 모드 + 녹화(시연용) | **6/6**, touch 0, 10:20:59 → 10:31:01 | — | 0.818 |

- 2회차 목표별 벽시계: station_a 47 s, dock_3 32 s, bed_b1 108 s, dock_4 104 s, bed_a4 87 s, dock_1 120 s.
- 도착 판정은 `GoToZone` 결과 `arrived: true`다. 정차 자리의 시뮬 참값(joint_states) 교차는 이 두 회차에서 **미실행**이다.
- 1회차는 콘솔이 잠겨 headless 로 돌았고 **녹화가 없다**.

### 녹화

| 파일(`markle_tmp/` 아래) | SHA-256 앞 16자 |
| --- | --- |
| `m2-hospital-nav-l3b/wp/clip-wp.mkv` | `7872fae846d3e094` |
| `m2-hospital-nav-show-1020/wp/clip-show.mkv` | `52f23c1460757816` |

전체 해시는 각 디렉토리의 `SHA256SUMS`에 있다. 녹화는 gst `ximagesrc`로 Isaac 창만 잡았다. 창 크기가 바뀌어도 끊기지 않게 `pixel-aspect-ratio=1/1`을 고정했다.

## 해석

- 1회차(main `c511c5e`)에서 bed_b1 로 가는 길에 팔 받침(ArmRiser)이 문틀에 닿았다. 2회차(`5be029c`)는 같은 경로를 touch 0 으로 지났다. 두 트리의 어떤 변경이 차이를 만들었는지는 대조하지 않았다(**미실행**).
- waypoints 경로는 고정 경로 추종이다. 이 결과를 Nav2 주행 합격으로 쓰지 않는다. Nav2 회차는 [실습40](practice-40.md)에 있다.

## 미실행

- #240 판정선 원문 대조, 참값 d_xy 교차, 1회차 녹화.
