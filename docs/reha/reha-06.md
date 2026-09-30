# 리하06 — 골든-3 `5a51804` 확정 · seed 23(팔이 집는 칸이 바뀐 첫 회차) · 촬영 SHA master02 캡처 회차

> 원문: #240 5798769352(master02 5a51804 · 캡처 회차), 5799586820(master01 회차28), 5799443133(seed 23). 확정: #576 5799587136.
> 원문에 없는 칸은 **보고되지 않았다**. 칸 규칙·판정 단계는 [README](README.md)에 있다.

## A — 골든-3 = `5a51804` 확정(재범 결정 ① 충족)

`5a51804` = 골든-2 `138cbac` + 감속기 "넓다" 판정(#631).

| 항목 | master02 | master01 회차28 |
| --- | --- | --- |
| #240 | 5798769352 | 5799586820 |
| 폴더 · SHA256SUMS | `~/markle_tmp/m2-hf-full-5a51804/` · `a1ca872c42fa` | `~/markle_tmp/m1-hospital-v0-5a51804-28/` · 보고되지 않았다 |
| 기동 | 01:29:06, 캐시 18/18 | 02:19:11 → up 02:19:51, 캐시 18/18, boot_check OK |
| 다섯 장면 | **5/5** | **5/5** 다. 집기는 02:21:36 이다. `DEPARTED` 는 02:22:06 다. `ARRIVED` 는 02:23:18 이다. `POUCH_PLACED` 는 02:23:50 이다. `ORDER_DONE` 도 02:23:50 이다. `DOCKED` 는 02:25:21 다 |
| DELIVERED | state 2 | DELIVERED |
| touch | /Amr/ 0 · M0609 비약통 0 · 낙하 없음 | AMR 0 |
| rtf · loop_hz · stall | 0.446 · 26.46 · 1 | **0.700** · 41.58 · 0 |
| 감속기 | `speed limit 100%` 는 **10줄**이다. 138cbac 은 2줄이다. `여유 ≥1.80 m` 는 9줄이다. `모름(창에 장애물 0)` 은 4줄이다. odom 최고는 1.000 이다 | 현황은 59줄이다. 100 % 는 **9줄**이다. 138cbac 은 1줄이다. `여유 ≥1.80 m` 는 **9줄**이다. 원문은 처음 0 으로 셌다. 9 로 고쳤다. #240 5799625628 이다. `여유 모름` 은 5줄이다. odom 최고는 1.00 이다. **중앙은 0.74** 다 |
| 복도 `DEPARTED`→`ARRIVED` | 보고되지 않았다 | **72 s**(138cbac 99 s) |
| 녹화 | `clip-1.mkv` 70,882,109 B · sha256 `f410acd7aa8e20e7…`(#240 5800810827) | `screen.mp4` 33,122,724 B · 390.1 s · sha256 `0b30b1b42f4d9c09dc448a10a62e8453d68c3155b375d2fa147a3e832fe9b9ca`(#240 5799625628) |
| 판정 단계 | **계약 합격** — 5/5 · DELIVERED · touch 0 · 녹화 | **계약 합격** — 5/5 · DELIVERED · touch 0 · 녹화 |

회차27(master01)은 boot_check record FAIL(ffmpeg 옵션 실수)로 따로 두었다 — 판정에 쓰지 않는다(원문).

## B — seed 23: 팔이 집는 칸이 바뀌어도 한 바퀴

| 항목 | 값 |
| --- | --- |
| SHA · 장비 | `138cbac`(골든-2) · master02 |
| 바꾼 것 | `v2_seed:=23` 하나 — **M0609 가 집는 칸**이 모듈 shelf_75/r0c0 · 원통 shelf_71/r0c0 으로 seed 7 과 달라졌다. **스테이지 진열 배치는 바뀌지 않았다**(아래) |
| 결과 | **5/5** 다. `/orders/status` state 는 2 다. DELIVERED 다. /Amr/ touch 는 0 이다. M0609 touch 는 0 이다. 낙하는 없다. rtf 는 0.443 이다. stall 은 1 이다. 감속기 전환이 있다. `DOCKED` 는 245.22 다 |
| 폴더 · SHA256SUMS | `~/markle_tmp/m2-hf-full-138cbac-seed23/` · `58c5e610801b` |
| 녹화 | 보고되지 않았다 |
| 판정 단계 | **L3 관측** — 증거 범위는 "팔이 집는 칸이 seed 로 달라져도 5/5" 까지다. 평가표 "물체 위치가 매번 달라져도"를 다 채우지는 않는다 |

**seed 의 범위 — 정정(#240 5801936313, 9/24 05:0x)**

- `P3_V2_SEED` 는 **팔의 칸 선택만** 바꾼다. 스테이지 진열 배치 seed 는 **0 고정**이다(`workcell_stock seed=0 cells=18 present=14 empty=[…]`). 그래서 지금 증거는 "같은 진열에서 팔이 다른 칸을 집어도 5/5"이다.
- 스테이지 진열 seed 를 연결하는 exp 뒤에 다시 잰다. 그때 진열 자체가 바뀌는지 `workcell_stock seed=` 줄로 확인한다.

| 회차 | 원문 | 결과 |
| --- | --- | --- |
| `138cbac` + seed 23 · master02 | 5799443133 | 5/5 · DELIVERED · touch 0 · rtf 0.443(위 표) |
| `aca8840` 이다. `P3_V2_SEED=23` 이다. master01 회차38 이다. `ord-0001` 이다 | 5801936313 | 5/5 다. DELIVERED 다. AMR touch 는 0 이다. ArmRiser 는 0 이다. rtf 는 0.669 다. 팔 칸이다. draw1 모듈은 shelf_75/r0c0 이다. **`container_refused cn-0217 reason=stale_epoch`** 다. 1/3 실패다. draw2 모듈 shelf_68/r0c1 은 허용이다. draw3 원통은 shelf_74/r0c1 이다. `aca8840` 에는 epoch 0 허용이 없다. `d6b88b1` 이다. RC 조합에 #636 이 필요하다. 녹화 `screen.mp4` 다. 36,249,724 B 다. `77d6491c48c2edc8…` 다 |

**스테이지 진열 seed 연결 — `68dd351` master01 회차40(#240 5802558111)**

| 항목 | 값 |
| --- | --- |
| 진열 | `workcell_stock seed=7 cells=18 present=14 empty=['shelf_68/r0c1','shelf_70/r0c1','shelf_72/r0c1','shelf_73/r0c0']` — seed 0 의 빈 칸(shelf_68/r0c0 · 72/r0c0 · 72/r0c1 · 75/r0c1)과 4칸 중 3칸이 다르다(두 목록 대조, `shelf_72/r0c1` 이 겹친다). 원문 덧붙임(5802558111)은 "빈 칸 4개 다름" 이다. 이 문서는 원문 로그 두 목록을 따른다. 계획 캐시 key 가 새로 잡혀(`d35bdd4b249f`) 18칸을 새로 계획했다 |
| 다섯 장면 | 5/5 다. 집기는 05:33:53 이다. `DEPARTED` 는 05:34:20 이다. `ARRIVED` 는 05:35:39 이다. `POUCH_PLACED` 는 05:36:12 이다. `ORDER_DONE` 은 05:36:12 이다. `DOCKED` 는 05:37:48 이다. DELIVERED 다 |
| touch · rtf | AMR 0 · ArmRiser 0 · rtf 0.712 |
| 관측(주의) | 모듈 보충 drug-ibu 가 3번째에 성공했다. ① `container_refused cn-0215 cell=shelf_74/r0c0 reason=stale_epoch` 다. `d6b88b1` 은 없다. ② `grasp: holding 이 2.0 s 안에 true 가 되지 않았다` 다. ③ shelf_70/r0c0 이다. `cn-0207` 장착은 허용이다. 원인은 오프라인에서 본다 |
| 녹화 | `screen.mp4` 37,305,547 B · 463.1 s · sha256 `d2a1d11d263f3f0a3b22965198e14bbcf66c4704ad416086aea595f6f4937e4e` |
| 판정 단계 | **계약 합격**(exp `68dd351`) — 평가표 "랜덤 스폰"의 스테이지 쪽 첫 증거. RC 조합에 `68dd351` 필요 |

## C — 촬영 SHA `f736213` master02 캡처 회차(정지 캡처 셋)

| 카메라 | 기동 | 결과 | 캡처 파일 · sha256 |
| --- | --- | --- | --- |
| `m0609_shelf` | 00:5x | DELIVERED · touch 0 · rtf 0.457 | `m2-m0609_shelf.png` · `bbcd814f060baac2`(앞 16자) |
| `m0609_dispenser` | 01:06:23 | DELIVERED · touch 0 · rtf 0.451 | `m2-m0609_dispenser.png` · `fdad2eea6b08fd81`(앞 16자) |
| `a1_pick` | 01:17:42 | DELIVERED · touch 0 · rtf 0.451 | `m2-a1_pick.png` · `33ae0fb7889aa8e6`(앞 16자) |

- 캡처 칸 출처는 #240 5803000625 다. 정정(9/24, [회차 목록](rounds-240.md) 원문 대조): 옛 칸은 셋 다 "보고되지 않았다".
- 셋 다 감속기 50 % 고정이다 — scan 수정 전 트리라서다(원문).
- master01 셋(회차21–23)과 합쳐 촬영 SHA 는 **여섯 바퀴 모두 DELIVERED · touch 0**이다. 촬영 뷰가 동작을 바꾸지 않는다.

## 곁 회차 — 데코 켬(`c35a056`, 골든-1 위, master01 회차25)

5/5 · DELIVERED · touch 0 · rtf 0.676(회차24 와 같다) · VRAM 6.90 GB. 데코 strips 17 · labels 16, WARN 0, 깜빡임 안 보임. 채택은 재범 캡처 검토와 함께(#240 5798773260).
