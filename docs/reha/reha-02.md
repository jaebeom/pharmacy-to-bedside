# 리하02 — 병원 전 구간 v0, `232931c` … `f8eac1c` — **v0 통과(두 장비)**

> 원문은 아직 #240 에 없다. 이 기록은 요약(2026-09-23 21:04 KST 수신)만 옮겼다. 원문이 올라오면 그 줄로 채우고 댓글 ID 를 적는다.
> 요약에 없는 칸은 **보고되지 않았다**. 칸 규칙은 [README](README.md)에 있다.

| 항목 | A — master02 | B — master01 |
| --- | --- | --- |
| 회차 폴더 | 보고되지 않았다 | 보고되지 않았다 |
| 단계 · SHA | v0 · `232931c`(선반 충돌체를 잰 판 두께 상자 + 모서리 기둥으로) | v0 · `232931c` |
| 구성 | 보고되지 않았다 | 보고되지 않았다 |
| 도메인 | 보고되지 않았다 | 보고되지 않았다 |
| 판정선 | 보고되지 않았다 | 보고되지 않았다 |
| 결과 | **불통과** — 조제 시한 초과 | **불통과** — 검출 0, QR 판독 불가. 선반 안정은 OK |
| rtf · GPU | 보고되지 않았다 | 보고되지 않았다 |
| 녹화 · SHA256SUMS | 보고되지 않았다 | 보고되지 않았다 |

## 다섯 장면 도달표

| 장면 | A — master02 | B — master01 |
| --- | --- | --- |
| ② 보충·약통 QR | 보고되지 않았다 | 보고되지 않았다(선반 위 약통이 안정했다는 요약만 있다) |
| ③ A1 적재 | **아니오** — 조제 시한 초과(요약) | **아니오** — 검출 0, QR 판독 불가(요약) |
| ④ 이동 | 미실행 | 미실행 |
| ⑤ 내려놓기 | 미실행 | 미실행 |
| ⑥ 복귀 | 보고되지 않았다 | 보고되지 않았다 |

"조제 시한 초과"가 ②(보충 대기) 쪽인지 ③(조제·벨트) 쪽인지는 원문 전이라 **미확인**이다. 위 표는 ③ 에 두었다.

## 회차 전체

| 항목 | A | B |
| --- | --- | --- |
| 한 바퀴 sim 시간 | 보고되지 않았다 | 보고되지 않았다 |
| `/Amr/` touch · Traceback · `[ERROR]` | 보고되지 않았다 | 보고되지 않았다 |

## 문제

| 번호 | 문제 | 장면 | 상태 |
| --- | --- | --- | --- |
| r02-P1 | 조제 시한 초과 | ③(또는 ②) | 원인 보고되지 않았다 |
| r02-P2 | A1 봉투 검출 0 · QR 판독 불가 | ③ | #553 `429ac27`(못 읽은 QR 을 네 점으로 펴서 다시 읽기)은 이 회차 뒤 커밋이다 |
| — | 선반 약통이 기울어 떨어지던 것(reha-01) | ② | B 에서 안정 OK(`232931c`) |

## C — `35fb28a` master02: 다섯 장면 중 넷

원문: #240 5794528230(2026-09-23 21:09 KST 게시). `35fb28a` 는 waypoint 시한이 `joint_states` 공백을 빼고 세게 고친 커밋이다(아래 원인 ②).

| 항목 | 값 |
| --- | --- |
| 회차 폴더 | `~/markle_tmp/m2-hf-full-35fb28a/`, SHA256SUMS `32476b67b3ed` |
| rtf | 0.367 |
| 판정선 · touch · `/orders/status` · 녹화 | 보고되지 않았다 |
| 결과 | **v0 판정 보류.** 모듈 보충이 실패했다. DELIVERED·touch 0·녹화 여부가 원문에 없다 |

| 장면 | 도달 | 원문 |
| --- | --- | --- |
| ② 보충·약통 QR | **부분** — 원통 예, 모듈 아니오 | 원통: `약통 확인 'cn-0208' cell=shelf_70/r0c1 → 장착 허용`, released target=round, `REFILL_DONE` 43.30. 모듈 3/3 실패: `container_refused - cell=shelf_68/r0c1 reason=unreadable` |
| ③ A1 적재 | **예** | `POUCH_PICKED` 63.53 |
| ④ 이동 | **예** | bed_a1 도착(`ARRIVED` 시각 보고되지 않았다) |
| ⑤ 내려놓기 | **예** | `AUTH_OK` · `POUCH_PLACED` 172.32 · `CABINET_LOCKED` |
| ⑥ 복귀 | **예** | `DOCKED` 253.22 |

원문의 번호(① 모듈 보충, ② 원통 보충 …)는 다섯 장면 번호와 다르다. 위 표는 [README](README.md) 번호로 옮겼다.
**원통 보충(약통 QR 확인 포함)부터 복귀까지 한 회차에서 처음 이어졌다**. ⑤ 가 통과한 것은 원인 ③(참값 센서 세계 속도)의 수정 없이다 — 이 회차에서 왜 보류되지 않았는지는 원문에 없다(**미확인**).

| 번호 | 문제 | 장면 | 상태 |
| --- | --- | --- | --- |
| r02-P3 | 모듈 약통 QR 판독 불가(`unreadable`) 3/3 | ② | QR 면 위치 수정 `2276027`(feat/hospital-full-2)로 다음 회차에서 본다 |

다음(원문): 같은 SHA 재현 `-r2`, 그다음 `5cb6542`.

## D — `5cb6542` master01(회차4, 참값 센서): 다섯 장면 중 넷

원문: #240 5794764480(2026-09-23 21:25 KST). 폴더 `~/markle_tmp/m1-hospital-v0-5cb6542-04/`(SHA256SUMS 보고되지 않았다).

| 장면 | 도달 | 원문(벽시계 KST) |
| --- | --- | --- |
| ② 보충·약통 QR | **부분** | drug-amox 슬롯 B 성공(`cn-0216` shelf_74/r0c1). drug-ibu `container_refused unreadable` 3/3 으로 멈춤 |
| ③ A1 적재 | **예** | `POUCH_AT_END` 21:13:28 → 벨트 집기 21:13:52 → deck_slot_1, `in_slot=True` offset 1.1 mm |
| ④ 이동 | **예** | 도착 · `AUTH_OK pt-2001` 21:17:20 |
| ⑤ 내려놓기 | **예** | `POUCH_PLACED` · `CABINET_LOCKED` 21:18:09 |
| ⑥ 복귀 | **예** | `DOCKED` 21:21:17 |

- 한 바퀴: 수락 21:11:57 → `ORDER_DONE` 21:18:09 → `DOCKED` 21:21:17, **9분 20초(벽시계)**. sim 시간 보고되지 않았다.
- rtf 0.45 · 기동 38 s(요약, N=1). 원문에는 없다.
- 뷰포트 Perspective `floor_top`. 녹화·touch·`/orders/status` 보고되지 않았다.
- 같은 날 회차3(`ae8b0b9`)의 검출 0 은 실행 명령에 `P3_SIM_SENSORS=1` 이 빠진 탓이었다.

## E — `94f19fb` master02(feat/hospital-full-2): 넷 통과, 주행 속도 제어 첫 회차

원문: #240 5795027810(2026-09-23 21:43 KST). 폴더 `~/markle_tmp/m2-hf-full-94f19fb/`, SHA256SUMS `5d586b5cfd39`.

| 장면 | 도달 | 원문(sim s) |
| --- | --- | --- |
| ② 보충·약통 QR | **부분** | 원통 `REFILL_DONE` 41.47. 모듈 `container_refused … shelf_68/r0c1 reason=unreadable`, 이어서 shelf_70/r0c0 도 unreadable |
| ③ A1 적재 | **예** | `POUCH_PICKED` 57.43 |
| ④ 이동 | **예** | `DEPARTED`→`ARRIVED` **40.3 s**(35fb28a 70.3 s) |
| ⑤ 내려놓기 | **예** | `AUTH_OK` · `POUCH_PLACED` 134.47 · `CABINET_LOCKED` |
| ⑥ 복귀 | **예** | `DOCKED` 184.77 |

- 주행 속도 제어(최고 1.0 m/s, 근접 시 50%): `speed_governor` 줄은 `speed limit 50% (여유 모름)` 1개, **touch 0**.
- rtf 0.354 · loop_hz 20.96 · loop stall 5.
- 녹화·`/orders/status` 보고되지 않았다.

## F — `94f19fb` + `--rail-drive 1e5 1e4 5e4` master02: 레일 드라이브 대조

원문: #240 5795175482(2026-09-23 21:51 KST). 폴더 `~/markle_tmp/m2-hf-full-94f19fb-rail/`, SHA256SUMS `1a7a54ea57c7`. E 와 같은 SHA 에 M0609 레일 드라이브 값만 바꿨다(`rail drive joint=rail_x stiffness=1e+05 damping=1e+04 max_force=5e+04`).

| 장면 | 도달 | 원문(sim s) |
| --- | --- | --- |
| ② 보충·약통 QR | **부분** | 원통 `REFILL_DONE` 42.07. 모듈 unreadable 그대로 |
| ③ A1 적재 | **예** | `POUCH_PICKED` 58.45 |
| ④ 이동 | **예** | 원문에 도착 시각 없음 |
| ⑤ 내려놓기 | **예** | `AUTH_OK` · `POUCH_PLACED` 134.42 · `CABINET_LOCKED` |
| ⑥ 복귀 | **예** | `DOCKED` 184.77 |

| 지표 | E(`94f19fb`) | F(+ rail-drive) |
| --- | ---: | ---: |
| loop stall | 5 | **0** |
| rtf | 0.354 | 0.386 |
| loop_hz | 20.96 | 22.84 |

- rail 목표 대비 위치·`rail_overlap` 줄은 로그에 없다(**미측정**).
- 해석: M0609 레일 드라이브 강성이 물리 스텝을 멈추게 한다는 앞선 단서가 맞았다. 9/17 검증 값으로 stall 0. 병원 preset 기본으로 바꾼다(PR, SHA 대기).

## G — `05339c9` master02(feat/hospital-full-2): 넷 통과, 모듈 QR 확대 재판독은 효과 없음

원문: #240 5795355277(2026-09-23 22:04 KST). 폴더 `~/markle_tmp/m2-hf-full-05339c9/`, SHA256SUMS `58a5f2b60994`(모듈 때 손 카메라 캡처 포함).

| 장면 | 도달 | 원문(sim s) |
| --- | --- | --- |
| ② 보충·약통 QR | **부분** | 원통 `cn-0208` 장착 허용 · `REFILL_DONE` 41.40. 모듈 `container_refused - cell=shelf_68/r0c1 reason=unreadable`, shelf_70/r0c0 도 같음. `'키워서 읽었다'` 줄 없음. 모듈 `REFILL_DONE` 없음, M0609 touch 0 |
| ③ A1 적재 | **예** | `POUCH_PICKED` 56.87, suction 0.0152(참값 기준 0.01 을 넘는다 — "붙었지만 걸림" 구간) |
| ④ 이동 | **예** | 원문에 도착 시각 없음 |
| ⑤ 내려놓기 | **예** | `AUTH_OK` · `POUCH_PLACED` 164.92 · `CABINET_LOCKED` |
| ⑥ 복귀 | **예** | `DOCKED` 245.73 |

- `speed_governor` 줄 1개 — 코스트맵 미수신 의심(확인 중).

## H — `f8eac1c` + `--rail-drive 1e5 1e4 5e4` master02: **다섯 장면 5/5 첫 완주**

원문: #240 5795627672(2026-09-23 22:22 KST). 폴더 `~/markle_tmp/m2-hf-full-f8eac1c/`, SHA256SUMS `04ec90cb9072`. **본편 클립 `clip-2.mkv`**(크기·sha256 은 SHA256SUMS 안, 앞자리 보고되지 않았다).
`f8eac1c` 는 모듈을 잡는 높이를 +0.03 m 올린 커밋이다(가로보 가림, 아래 절).

| 장면 | 도달 | 원문(sim s) |
| --- | --- | --- |
| ② 보충·약통 QR | **예**(모듈·원통 둘 다) | 모듈 `약통 확인: cn-0204 cell=shelf_68/r0c1 장착 허용` · released target=module 69.17 · `REFILL_DONE` 71.58. 원통 `cn-0208` shelf_70/r0c1 허용 · released 100.25 · `REFILL_DONE` 103.43 |
| ③ A1 적재 | **예** | `POUCH_PICKED` 104.32 |
| ④ 이동 | **예** | `DEPARTED`→`ARRIVED` 42.0 s |
| ⑤ 내려놓기 | **예** | `AUTH_OK` · `POUCH_PLACED` 179.73 · `CABINET_LOCKED` |
| ⑥ 복귀 | **예** | `DOCKED` 235.05 |

| 항목 | 값 |
| --- | --- |
| M0609 touch | 34줄 — 전부 그리퍼 손가락·너클 ↔ 잡은 약통(shelf_68/70), 최대 impulse 1.05 |
| `/Amr/` touch(봉투 외) | 보고되지 않았다 |
| `/orders/status` 종료 상태 | 보고되지 않았다(`CABINET_LOCKED`·`DOCKED` 는 있다) |
| rtf · loop_hz · stall | 0.389 · 23.13 · 1 |
| `speed_governor` | 1줄 |

- 판정은 아래 I 절(두 번째 장비 재현) 뒤 **v0 통과**로 확정했다.
- **촬영 대표 회차(우선)** — 이 회차의 `clip-2.mkv`(9/23). 촬영 계획 [#567](../presentation/hospital-demo-shotlist.md) 기준으로는 `floor_top` 한 회차가 본편이다 — 이 클립의 뷰는 보고되지 않았다.
- 해석: 병원에서 전 구간(웹 요청 → M0609 모듈·원통 보충(약통 QR 확인) → 컨베이어 A1 → 합본 UR5 집기 → Nav2 → bed_a1 인증·내려놓기·보관함 잠금 → dock 복귀)이 한 회차에 이어진 첫 기록이다. 다음은 `e9b9498`(rail-drive 만) 기동, 그다음 재현.

## I — `f8eac1c` master01(회차9): 다섯 장면 5/5 재현 → **v0 통과 확정**

원문: #240 5795682106(2026-09-23 22:26 KST). 폴더 `~/markle_tmp/m1-hospital-v0-f8eac1c-09/`(SHA256SUMS 보고되지 않았다). N=1.

| 장면 | 도달 | 원문(벽시계 KST) |
| --- | --- | --- |
| ② 보충·약통 QR | **예**(모듈·원통 둘 다, master01 에서 처음) | 모듈 `REFILL_DONE` 이다. drug-ibu 다. 슬롯 A 다. shelf_68/r0c1 이다. 여유는 0.012 다. 원통은 성공이다. drug-amox 다. 슬롯 B 다. shelf_70/r0c1 이다. |
| ③ A1 적재 | **예** | 벨트 집기 22:19:48 → 적재 |
| ④ 이동 | **예** | `DEPARTED`→`ARRIVED` 105 s, AMR 최고 1.00 m/s |
| ⑤ 내려놓기 | **예** | 도착·`AUTH_OK` 22:22:09 → `POUCH_PLACED` |
| ⑥ 복귀 | **예** | `DOCKED` 22:24:52 |

- 한 바퀴다. 수락은 22:17:46 이다. `ORDER_DONE` 은 22:22:49 다. `DOCKED` 는 22:24:52 다. 7분 6초다. 벽시계다. rtf 는 0.444 다. loop_hz 는 26.37 이다.
- **AMR 본체 touch 0.** `/orders/status` 종료 상태는 보고되지 않았다.
- 기동: 캐시가 새 key 라 계획을 새로 풀어 up 까지 76 s.
- `speed_governor` 는 3줄이다. 감속 변화는 0 이다. 코스트맵 수신 흔적은 없다. `5a10c79` QoS 수정 회차에서 본다. 해석이다.
- 복도는 105 s 다. master02 는 42 s 다. 장비 rtf 와 경로 차이로 보인다. 해석이다. `5a10c79` 대조에서 같이 본다.

### v0 판정 — **통과(두 장비)**

같은 SHA `f8eac1c` 가 master02(H)와 master01(I)에서 다섯 장면 5/5 로 완주했다(#576).
v0 조건과 대조한다.

| v0 조건(#576) | H master02 | I master01 |
| --- | --- | --- |
| `ORDER_DONE`=DELIVERED | `CABINET_LOCKED`·`DOCKED` 있음. 종료 상태 줄은 보고되지 않았다 | `ORDER_DONE` 22:22:49 · `POUCH_PLACED`. 종료 상태 줄은 보고되지 않았다 |
| touch 0 | AMR 쪽 보고되지 않았다(M0609 는 잡은 약통뿐) | **AMR 본체 touch 0** |
| 창 모드 녹화 | `clip-2.mkv` | 보고되지 않았다 |

## J — 같은 밤 뒤 회차(SHA·장비별로 나눠 적는다)

"n회 연속"으로 합치지 않는다. 판정 단계는 [README](README.md) 다섯 단계다.

| SHA · 장비 · 회차 | #240 | 다섯 장면 | 미보고 판정값 | 판정 단계 | 비고 |
| --- | --- | --- | --- | --- | --- |
| `f8eac1c` · master02 · 1회 | 5795627672 | 5/5 | `ORDER_DONE`=DELIVERED 줄, AMR touch | L3 관측 | 본편 후보 `clip-2.mkv`(H 절) |
| `f8eac1c` · master01 · 회차9 | 5795682106 | 5/5 | DELIVERED 줄, 녹화 | L3 관측 | AMR touch 0(I 절) |
| `f8eac1c` · master01 · 회차10 | 5795827276 | 5/5 | DELIVERED 줄, 녹화 | L3 관측 | AMR touch 0, rtf 0.435, 주행 98 s. 감속기 코스트맵 수신 0 |
| `e9b9498`+rail · master02 | 5795783225 | 넷 아님 — ④ 내려놓기 `not_detected`, ① 모듈 없음(base 차이, `f8eac1c` 미포함) | — | L3 관측(불통과) | /Amr/ touch 0, rtf 0.423 |
| `5a10c79`+rail · master02 | 5795978282 | 5/5 | `/orders/status` 최종 수집 미실행, 녹화 결손(콘솔 잠김) | L3 관측 | 감속기 판정선 미충족(50 % 고정) |
| `5a10c79`+rail · master01 · 회차11·12 중 render-every 2 회차 | 5796069792 | 5/5 | DELIVERED 줄 | L3 관측(touch 판정선 불통과) | rtf 0.690. **AMR touch 2**(컨베이어·사이드테이블). 원문은 회차 번호와 렌더 조건을 짝짓지 않는다. 정정(9/24, [회차 목록](rounds-240.md) 원문 대조): 옛 칸 "회차11(render-every 2)" |
| `5a10c79`+rail · master01 · 회차11·12 중 렌더 인자 없는 회차 | 5796069792 | 5/5 | DELIVERED 줄 | L3 관측(touch 판정선 불통과) | rtf 0.418. **AMR touch 2** |
| `5a10c79` + 합본 2대 · master02 | 5796264039 | 넷 아님 — ④ `not_detected` | — | L3 관측(불통과) | rtf 는 0.290 이다. 0.35 에 미달이다. touch 는 2 다. 1.5 m/s 다. 렌더 인자가 없다. 촬영 2대 판정에 안 쓴다 |

- `5a10c79` 의 touch 2 원인은 최고 속도 1.5 m/s 의 오버슈트다. 같은 정차 자리를 쓰는 `f8eac1c`(1.0 m/s)는 0 이었다(정정, #240 5796165837).
- **계약 합격**(v0 판정선의 모든 칸)에 닿은 회차는 아직 없다. 모든 행에서 `ORDER_DONE`=DELIVERED 종료 상태 줄이 원문에 없다.
- 골든 후보는 `0819f80` 이다. `f8eac1c` 다. rail_drive 다. render_every 2 가 기본이다. 감속기를 고쳤다. zone_id 다. QR png 다. 최고는 1.0 m/s 다. [reha-03](reha-03.md)에서 확정한다.

## 합본 AMR N대 부하 측정 — `d379042` master01(#589 규약)

원문: #240 5795435831(N=2·3, 22:09 KST), 5795512558(N=4·시리즈 종료, 22:14 KST). 폴더 `~/markle_tmp/m1-hospital-n{1,2,3,4}-d379042-0{5,6,7,8}/`(tally.txt·screen.mp4·SHA256SUMS). 표 원본은 #589/#601.
배송은 `amr_1` 한 대가 하고, 나머지 합본은 같은 씬에 세워 부하만 더한다.

| N | 배송 | 수락 → ORDER_DONE → DOCKED(KST) | rtf | loop_hz | GPU |
| ---: | --- | --- | ---: | ---: | --- |
| 1 | 완주 | 시각은 보고되지 않았다. 리하02 D 와 같은 조건인지는 미확인이다 | 0.450 | 26.67 | 보고되지 않았다 |
| 2 | **완주** | 21:41:54 → 21:49:13 → 21:52:05 | 0.299 | 17.71 | 80 W 한도에 붙는다. 중앙은 77–78 W 다 |
| 3 | **완주** | 21:53:22 → 21:59:41 → 22:02:03 | 0.318 | 18.83 | 80 W 한도에 붙음 |
| 4 | **완주** | 22:03:27 → 22:10:58 → 22:13:49 | 0.267 | 15.78 | 80 W 한도에 붙음, util 70 %, VRAM 7.5 GB |

- N=2 와 N=3 이다. VRAM 은 7.3 GB 다. `joint_states` 공백 최대는 N=2 가 0.28 s, N=3 이 0.34 s 다. stage ready 는 N=2 가 33 s, N=3 이 35 s 다.
- N=1·2·3·4 모두 배송 완주. GPU util 45 → 58 → 62 → 70 %, VRAM 6.9 → 7.5 GB, `joint_states` 공백 최대 ≤ 0.34 s, stage ready 33–41 s(N=4 원문).
- 해석: 가장 큰 하락은 N=1→2(−34 %)이고 3·4 는 완만하다. VRAM 여유가 커서 한계는 GPU 전력(80 W)이다. 결론·권고는 #589 에 있다.
- 멈춤 조건은 기동 실패 또는 rtf < 0.2 다(#589 규약).

## 모듈 약통 QR 판독 불가 — 원인과 결정

| 항목 | 값 |
| --- | --- |
| 증상 | 모듈 보충 `container_refused … reason=unreadable` — C·D·E·F·G 다섯 회차 모두. G 의 확대 재판독은 효과 없음 |
| 원인 | 손 카메라가 선반 **가로보에 가려** 모듈 QR 을 못 본다. G 의 손 카메라 이미지로 확정(#240 5795355277) |
| 결정 | 모듈을 잡는 높이 **+0.03 m**(9/23) — `f8eac1c`. H 회차에서 모듈 `cn-0204` 판독·장착 허용으로 **해결 확인**(1회) |

## 같은 밤 확정 원인

| 원인 | 근거 |
| --- | --- |
| GPU 전력 80 W 상한 | reha-01 B `gpu.csv` 평균 71 W · 최대 78.5 W / 80 W |
| `joint_states` 수신 공백 0.67–1.13 s(wall) → M0609 waypoint 시한을 공백까지 세어 `grasp_pose` 실패로 적었다 | #553 `35fb28a` 커밋 본문(공백 동안 시한을 세지 않게 고침. 공백 자체는 그대로) |
| 참값 센서가 봉투의 **세계 속도**로 정지를 본다 → AMR 트레이에 실린 채 움직이는 봉투는 병상에서 "아직 움직인다"로 검출에서 빠진다(reha-01 A ⑤ 검출 0) | reha-01 A(`3b76030`) stage 로그, bed_a1 도착 뒤 마지막 줄: `pouch detection held order_id=ord-0001 speed=0.1056 limit=0.02 (아직 움직인다)`(#240 5794286395 회차). 코드: `pharmacy_stage.py` `speed > sensorlib.POUCH_STILL_SPEED`(0.02, `truth_sensors.py` 34행). **수정 SHA 대기** |

## 다음

- 원문(#240)을 받아 위 칸을 채운다.
