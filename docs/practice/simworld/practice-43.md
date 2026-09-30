# 실습43 — 병원 컨베이어를 씬 참조 아래서 돌리기(참조 탐침 01·02)

| 항목 | 값 |
| --- | --- |
| 날짜 | 2026-09-23, master02 |
| 실행 | `master02` 원격 실행 |
| 환경 | `sim/scenes/hospital_navigationv1.usda` 를 새 stage 의 `/World/P3Base/Scene` 에 reference(pharmacy_stage 와 같은 방식) |
| 실행 코드 | 01 `a412882`, 02 `955e14b`(`feat/conveyor-reference-probe`) |
| 명령 | `conveyor_reference_probe.py --base-usd hospital_navigationv1.usda --config <probe06> --output <폴더>` 다. 02 는 `--surface-velocities hospital_conveyor_surfaces.json` 을 더한다 |
| 판정선 | #240 5790417409(01), 5790514889(02). 결과 전에 고정 |
| 원본 | master02 `markle_tmp/m2-conveyor-ref-probe-*`, 각 `SHA256SUMS` |

이 문서는 실습 관찰 기록이다. frozen protocol 의 합격 evidence 가 아니다. 결과 원문은 #240 5790540704 에 있다.

## 왜 했나

재범은 봉투를 병원 씬 컨베이어로 A1 롤러 끝까지 보내라고 결정했다(#527). [실습38](practice-38.md) 탐침은 씬을 stage 루트로 열었고, 그때는 컨베이어가 돌았다.
pharmacy_stage 는 씬을 `/World/P3Base/Scene` 아래에 reference 한다. 그 자리에서 씬의 컨베이어 OmniGraph 가 도는지는 이 실습 전에 확인한 기록이 없다.

## 관측

| 회차 | 바뀐 것 | 결과 | 원문·수치 |
| --- | --- | --- | --- |
| 01 `a412882` | 참조 아래 그대로 | **불통과**(90 s timeout) | 봉투가 스폰 자리에서 z 3 cm 내려앉은 뒤 x·y 로 움직이지 않았다. 트랙 19개의 선속도는 0 이었다. Track_05·07 각속도 ±18.5 만 저작된 정적 값이었다. 결과 json sha256 은 `db9971d2…` 다 |
| 02 `955e14b` | 표면 속도 19개를 직접 씀 | **통과** | ready 는 `conveyor_bodies` 19, `direct_surfaces` 19 다. reason 은 `terminal_edge_settled` 다. `elapsed_sim_s` 는 34.583 이다. probe06 은 34.567 이다 |

02 의 멈춘 자리는 (−8.295, 5.036, 0.389) 이다. 끝 롤러 Rollers_01 위에서 edge_gap 0.0234 m, bottom_gap −0.0007 m 였다.

02 에서 관측 위치로 본 경로다. 트랙 이름은 위치로 짐작한 것이다.

| sim s | 위치 | 움직임 |
| --- | --- | --- |
| 0.05 | (−9.828, 11.10, 0.917) | 스폰 자리에서 떨어짐 |
| 9.15 | (−9.828, 9.34, 0.88) | y−·z− 로 내려감(Track_12 경사로 추정) |
| 22.75 | (−9.763, 6.62) | x+ 로 돌기 시작(Track_05·07 곡선 추정) |
| 29.35 | (−8.314, 6.17) | 다시 y− 로(Track_02 분류기 추정) |
| 33.65 | (−8.295, 5.04) | 정착 |

표면 속도 값은 probe06(씬을 루트로 연 회차)의 sim 11.25 s 줄에서 뽑았다. 추출 파일 sha256 은 `363dd0fa…` 이다. 예: Track_06/Belt linear (−0.5, 0, 0), Track_05·07 Rollers angular (0, 0, ±18.5), Track_02·09 Sorter (≈0, 1.0, 0), Track_04 Sorter (−1.0, 0, 0).

녹화: `m2-conveyor-ref-probe-02-run/clip-probe.mkv` 8,054,383 B, sha256 `729708d2785b4224…`. 결과 json `a6dfee5498ee031d…`, SHA256SUMS `424a4cff80148eb7…`.

## 해석

- 씬을 reference 로 넣으면 씬 안의 컨베이어 OmniGraph 가 표면 속도를 쓰지 않는다. 01 의 선속도 0 이 그 관측이다. 그래프가 왜 멈추는지는 확인하지 않았다(**미실행**).
- 그래프 대신 표면 속도를 직접 쓰면 루트로 열었을 때와 같은 시간(0.02 s 차이)에 같은 끝 롤러에 선다.
- #553 의 `hospital-full` preset 은 이 방식(씬 그래프 대신 `p3sim/hospital_conveyor.py` 로 표면 속도를 직접 씀)을 썼다.

## 미실행

- 봉투 여러 개, 연속 조제, 다른 창구(A2–A4) 경로.
- 조제기에서 실제로 나온 주문 봉투. 탐침은 시험 봉투 하나를 Track_06 위에 놓았다.
- 스테이지 전체에서 같은 결과가 나오는지. #553 I1(`bbedd65`)은 불통과였다. DISPENSED 뒤 봉투가 출발 자리에서 움직이지 않았고 `hospital_conveyor running=False` 줄이 있었다. 원인은 확인하지 않았다. 원본은 master02 `m2-hf-i1-bbedd65/` 다.
