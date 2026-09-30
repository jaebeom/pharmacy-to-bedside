# 리하 밤 일지 — 9/24 밤 – 9/25 아침(다중 PC 실습)

> 재범 지시(9/24 14:1x): 밤마다 다중 PC 실습을 한다. 아침에 보고한다. 이 파일은 그 첫 밤의 틀이다.
> 원문은 모두 #240 이다(댓글 ID). master01·master02 의 #240 원문이 오면 채운다. 회차는 **SHA·장비별 한 줄**이다. "n회 연속"으로 합치지 않는다.
> 판정 단계는 [README](README.md) 다섯 단계다. 원문에 없는 칸은 "보고되지 않았다"로 적는다. 해석은 "해석"이라고 적는다.

## 아침 요약(9/25 06:3x)

- 다중 PC 3회차(`fcec7a8`, 도메인 131: master01 stage · master02 arm · nav · stack · web)는 **모두 두 PC 통과**다. N=4 1건 · 10건 10/10 · N=2 1건. touch 0.
- 새 clone 재현(G8, main `b0691f5`)은 **주문 PASS** 다. 문서대로 막힌 줄이 2개 나왔다. 하나는 런카드 재시도로 풀렸다. 하나는 잔류다. 별도 등록 회차다.
- 보행자 접촉: RC-3 `7bf81cc` 에서 AMR 본체가 보행자와 닿았다. master01 Play/Stop 은 2회다. master02 beds-all 은 28줄이다. 그때 보행자는 멈추지 않았다(`never_stops`). **닫힘**: 보행자 양보 규칙 `0537e61`(AMR 1.5 m 안이면 선다)이 RC-4 `64e5ab7` 에 들어갔다. master01 회차82–87 · 94 에서 보행자 접촉 0 이다(5822585043 등).
- 비전 v1(목적지 봉투 카메라 판독)은 두 PC 모두 0 프레임 판독이다. 1000 ms 시한에 걸렸다. 참값으로 대신했다. 약통 QR 판독은 2/2 다.
- 관측: 다중 PC 10건에서 rtf 가 65분 동안 0.66 → 0.54 로 내려갔다(판정선 아님).
- 정정(9/25): 앞 판의 "재범 결정 필요: 보행자 접촉" 줄은 지웠다. 양보 규칙으로 닫혔다.

## 배치 — 다중 PC 회차

| 회차 | 실행 SHA | master01 역할 | master02 역할 | 도메인 | 무엇 |
| ---: | --- | --- | --- | --- | --- |
| 64 | `fcec7a8`(`fcec7a85a92ff69613ee5a54e9bc27a40f5ed10c`) | stage | arm · nav · stack · web | 131 | N=4, 1건 |
| 65 | `fcec7a8` | stage | arm · nav · stack · web | 131 | 10건(기본 계획, AMR 1) |
| 66 | `fcec7a8` | stage | arm · nav · stack · web | 131 | N=2(AMR 2), bed_a1 |

## 회차별 결과 — 다중 PC

| 회차 | 결과(원문 요약) | 판정 단계 | rtf(stage) | 녹화 파일 · B · sha256 | SHA256SUMS | #240 |
| ---: | --- | --- | ---: | --- | --- | --- |
| 64 | ORDER_DONE sim 366.0 · DOCKED 435.4 · orders_status 2. /clock 발행자 1. in_slot=True · tray drift 0 · AMR touch 0 · ArmRiser 0 | L3 관측(두 PC 통과) | 0.509(대기 5분 포함 회차 전체) | master01 `screen.mp4` 55,876,281 B `767b3d1fa81f821aec9eac3c1c9af7df224b64ddbd996fcd54313e62912a4d0b` · master02 `clip-1.mkv` `cca380ad541094dac394a517e01350e0e82bf6a871891bdfae6b17e87be54a73` | master02 `87325542…3f8`(64자는 원문) | 5816418529 · 5816379015 |
| 65 | **10/10 delivered**, 재시도 0. 1인 배송 sim 149.8–174.1 · 병실 묶음 268.6/325.8/384.6. AMR touch 0 · ArmRiser 0 · in_slot=False 0 · tray drift 최대 0.0217 m | L3 관측(두 PC 통과) | 0.585(10분 구간 0.660 → 0.542 하강) | master01 `screen.mp4` 225,369,304 B `d31909bea5c6194e…`(앞 16자) · master02 `clip-1.mkv` `b2690fe3c4f1ffdc872bab9dfcda70e84eb5fbdf55a12e53acfac4b0b78a28b0` | master02 `847c0e46…da86` | 5817495196 · 5817480171 |
| 66 | orders_status 2 · DOCKED sim 340.8 · amr_count=2. AMR touch 0 · ArmRiser 0 · drift 0 | L3 관측(두 PC 통과) | 0.603 | master01 `screen.mp4` 38,002,236 B `692813dacc47fb02…`(앞 16자) · master02 `clip-1.mkv` `8e796ac3321727ee33b36ee3c2c39c1c0412c3d291dc27beaf2986193b48dfde` | master02 `dbda0979…7e5e` | 5817667047 · 5817661164 |

- 녹화는 두 PC 모두 record_qa `fps=30.00 … drop=0 corrupt=0 — OK` 다(원문). master02 녹화는 웹 화면이다.
- 판정 단계를 "계약 합격" 으로 쓰지 않았다. protocol 동결 전 회차다. 관측이다.

## rtf 비교

| SHA | 다중 PC rtf | 같은 SHA 단일 PC rtf | 차 | 출처 |
| --- | ---: | ---: | ---: | --- |
| `fcec7a8` | N=2 0.603 · 10건 0.585 · 1건 0.509(대기 포함) | 같은 조건 회차 없음(회차67 은 1920×1080 렌더 · station_b 라 조건이 다르다: 0.581) | 비교하지 않음 | 5817667047 · 5817811811 |

- 원문 해석: N=2 rtf 0.603 은 단일 PC N=2 골든(0.43) 보다 높다. SHA 와 구성이 다르다. 이 일지에서는 차를 계산하지 않는다.

## 같은 밤 단일 PC 회차(요약)

| 회차 · 호스트 | SHA | 무엇 | 결과 | #240 |
| --- | --- | --- | --- | --- |
| 67 · master01 | `fcec7a8` | 촬영 station_b 1인(1920×1080) | PASS · rtf 0.581 · 녹화 30 fps drop 0 | 5817811811 |
| master02 ① | `0cfdb93` | 셀 데코, bed_a1 | PASS 5/5 | 5817823526 |
| 68 · master01 | `fcec7a8` + 더미 2 | 촬영 station_b | PASS(더미 정지 규칙 발동 0회 — 미검증) | 5817940576 |
| master02 ② | `63eeb29` + 보행자 2 | station_b | PASS · 보행자 touch 0 | 5817975682 |
| 69 · master01 | RC-3 `7bf81cc` | 촬영 station_b | PASS | 5818123171 |
| 70 · master01 | RC-3 `7bf81cc` | Play/Stop bed_a1 | **FAIL** — AMR ↔ 보행자 ped_1 2회 접촉(주문 2건 DELIVERED). reset pose amr_dxy 0.0000 | 5818398649 |
| master02 ③ | RC-3 `7bf81cc` | beds-all(더미 · 보행자 ON) | 10/10 · **보행자 접촉 28줄** · 더미 touch 0 | 5819467061 |
| 71 · master01 | `8addf47` | 비전 v1 station_b | 주문 PASS · vision FAIL(0/1, 1000 ms) | 5818543913 |
| master02 ③.5 | `8addf47` | 비전 v1 bed_a1 | 5/5 · vision FAIL(0/3 프레임) · 약통 vision 2/2 | 5819633998 |
| 72 · master01 | `05ba1a2` | 충전 벽 촬영 | PASS | 5818663862 |
| master02 ③.6 | `05ba1a2` | 충전 벽 bed_a1 | 5/5 · vision FAIL | 5819817987 |
| **73 · master01** | main `b0691f5` | **G8 새 clone 재현** bed_a1 1건 | **주문 PASS** · 문서대로 막힌 줄 2(1 풀림 · 1 잔류) | 5818833284 |
| 74 · master01 | RC-4 `50b8769` | table_c1 | FAIL(웹 주문 거부 `bad_destination`) | 5819484248 |
| 76 · master01 | RC-4 `50b8769` | station_b | PASS | 5819628887 |
| 77 · 78 · master01 | `6812ee5` | station_c · station_d | FAIL — 언도킹 중 ArmRiser ↔ dock_1 모듈 테이블(주문 DELIVERED) | 5820319699 · 5820449735 |
| 82–87 · master01 | `64e5ab7` | station_c · d · b · 병실 묶음 · Play/Stop · N=2 | 여섯 회차 PASS(77 · 78 재발 없음) | 5820758425 … 5821695136 |
| master02 | `6812ee5` | beds-all 13건 + 긴급 | 13/13 · 도크 옆 접촉 빨강 | 5822258560 |

- 정정(원문 5819464108): master01 1인 주문 스크립트가 mode 1(긴급)으로 보냈다. 결과는 유효하다. 주문 종류는 "긴급" 으로 읽는다.

## 실패 · 중단 · 결번

| 회차 | 무엇 | 원문 | 다음 |
| ---: | --- | --- | --- |
| 70 · master02 ③ | 보행자 접촉 | 5818398649 · 5819467061 | 닫힘 — 양보 규칙 `0537e61`(RC-4 `64e5ab7`), 회차82–87 · 94 접촉 0 |
| 71 · ③.5 · ③.6 | 비전 v1 판독 0 | 5818543913 · 5819633998 | 비전 — 9/26 저녁 결정 규칙 |
| 74 | 웹 목적지 ID 거부 | 5819484248 | sim · 웹 |
| 77 · 78 | 언도킹 ArmRiser 접촉 | 5820319699 | `64e5ab7` 에서 재발 없음 |
| 75 · 79–81 | 이 일지 범위의 #240 에 없다 | — | 결번 여부는 master01 확인 전(보고되지 않았다) |
