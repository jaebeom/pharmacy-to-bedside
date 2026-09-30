# 리하09 — acceptance 회전 1–4(protocol v1 · v2) · protocol v1 → v4 · v0.5.0 `a4b1a4e`

> 기간 2026-09-25 – 09-27 KST.
> 원문: `evidence/runs/` 의 run 기록, [v0.5.0 배포 기록](../../evidence/deployments/2026-09-27-jaebeom-v0-5-0.md)(#750), [campaign 장부](campaigns.md), protocol 파일, #240 댓글(아래 표마다 ID).
> 원문에 없는 칸은 **보고되지 않았다**. 칸 규칙·판정 단계는 [README](README.md)에 있다. 리하08 까지의 골든 회차와 달리 이 회차부터는 **acceptance protocol 회전**이 단위다 — 회전 하나 = attempt 16개(seed 7 한 블록, 14 · 15 는 seed 11 · 23).

## A — 회전 1–4 결과

| 회전 | 코드 | protocol | run(master01 · master02) | PASS | FAIL | 끝난 attempt | 미실행 | rtf 중앙(최소–최대) | AMR touch | 판정 단계 |
| --- | --- | --- | --- | ---: | ---: | --- | --- | --- | ---: | --- |
| 1 | `64e5ab7`(RC-4) | v1 | 14(10 · 4) | 12 | 2 | 14/16 | 12 · 13(취소) | 0.528(0.395–0.627) | 0 | L3 관측 — 계약 합격 아님(16/16 무실패 미충족) |
| 2 | `0b1319b`(main) | v1 | 15(9 · 6) | 12 | 3 | 15/16 | 16 | 0.541(0.403–0.643) | 0 | L3 관측 — 계약 합격 아님 |
| 3 | `a4b1a4e`(더미 ON) | v1 · v2(12 · 13) | 16(8 · 8) | 13 | 3 | 15/16 | 16 | 0.524(0.382–0.618) | 0 | L3 관측 — 계약 합격 아님 |
| 4 | `a4b1a4e` | v1 | 16(9 · 7) | 14 | 2 | 14/16 | 12 · 13(취소) | 0.518(0.383–0.707) | 0 | L3 관측 — 계약 합격 아님 |

- 합계는 61 run · 51 PASS · 10 FAIL 이다(회전 5 의 2 run 은 [리하10](reha-10.md)). run 수 · PASS · FAIL 은 v0.5.0 기록 "회전 결과" 표와 같다. rtf · touch 는 run 기록의 `rtf` · `amr_touch_count` 를 이 문서에서 모았다(회전 4 는 4R 로 대체된 원래 run 8 을 뺐다).
- v1 · v2 의 판정선은 회전마다 16/16 무실패였다. 네 회전 모두 넘지 못했다. 이 판정선은 9/27 재범 결정으로 완화됐다(C).
- 회전 4 의 원래 run 8(attempt 1–5 · 7 · 8 · 14)은 원본 소실로 셈에서 뺐다([#735 검토](../../evidence/reviews/2026-09-27-jaebeom-c4-artifact-loss.md)). 같은 attempt 를 "4R" 로 다시 돌려 `supersedes` 로 등록했다(#740 · #741).
- 셈 밖(run 없음) attempt 와 사유는 [campaign 장부](campaigns.md) 2절과 v0.5.0 기록 "셈 밖" 표에 있다.

## B — 실패 10 run

| 회전 · attempt | host | failure_class | 원인 1줄 | 근거 #240 | 재시도 |
| --- | --- | --- | --- | --- | --- |
| 1 · 3 | master01 | infra | 회차 관측 스크립트가 ORDER_DONE 뒤 120 s 에 내려 DOCKED 전 종료 | 5824183133 | 없음 |
| 1 · 6 | master02 | **robot** | 시뮬 보관함 기록이 보관함마다 첫 주문에서 멈춰 병실 묶음 2 · 3번째 present 누락(배송 10/10 · touch 0) | 5824830092 · #711 | 없음 |
| 2 · 10 | master02 | infra | Isaac 스테이지 세그폴트 | 5828600444 | 없음 |
| 2 · 12 | master02 | infra | protocol v1 (c) 가 phase E 비-stage host 의 viewport SKIP 을 예외로 두지 않음(배송 · 도크 복귀는 됨) | 5828957109 · 5848373269 | 없음(결정 (C)) |
| 2 · 13 | master02 | infra | 2 · 12 와 같다 | 5833920864 · 5848373269 | 없음(결정 (C)) |
| 3 · 12 | master02 | operator | stage 를 맡은 master01 에서 boot_check 미실행 | 5854056297 | 없음(취소) |
| 3 · 13 | master02 | operator | ord-0010 완료 전 stage 를 수동으로 내림 | 5853814806 | 없음(취소) |
| 3 · 15 | master02 | operator | preclean 이 진행 중 stage 를 강제 종료 | 5853199580 | `20260927T081600Z-master02-569a44d4` PASS |
| 4 · 4 | master01 | infra | GPU 전력 15 W 구간에서 실행, 64분 | 5852722207 | `20260927T051900Z-master02-e3599c98` PASS |
| 4 · 5 | master01 | infra | 녹화기 버퍼 정지(screen.mp4 60 s 동안 104304 B) | 5852728369 | `20260927T053000Z-master02-7a6fe8a2` PASS |

- failure_class 는 v0.5.0 기록이 붙인 것이다. v1 · v2 run 파일에는 `failure_class` 칸이 없다(v4 부터 의무).
- robot 원인은 1건(1 · 6)이다. 수정 fed2373 = main `71b534e`(9/25)가 회전 2 · 3 · 4 코드에 들어 있다.

## C — protocol v1 → v4

| protocol | frozen(UTC) | 무엇이 달라졌나 | PR | 인용 run |
| --- | --- | --- | --- | --- |
| v1 | 2026-09-24T23:14:44Z | 첫 동결. 회전마다 16/16 무실패 | — | 회전 1 · 2 · 3 · 4 |
| v2 | 2026-09-27T02:56:34Z | boot_check (c) 를 phase E(다중 PC)의 비-stage host 로 넓혔다 | #733 | 회전 3 attempt 12 · 13 · 회전 5 |
| v3 | 2026-09-27T09:56:06Z | §7 판정선 완화 — 회전마다 ≥15/16(90 % 이상), 실패마다 failure_class · 원인 기록 | #751 · #756 | 없음(v4 로 대체) |
| v4 | 2026-09-27T10:55:54Z | v3 의 purpose 문장 불일치 5곳 수정(자기 참조 · "proposed" 잔존 문장 · 15/16 신뢰 하한 0.736 · §8 판정선 명시 · 봉투 풀 15)으로 v3 를 대체. `requires_failure_classification: true` · `tools/round_summary.py` 추가 | #773 | 회전 6 · 7 |

- 완화 근거는 재범 결정 "목표를 성공률 90% 정도로 완화하고, 실패 상황을 명확하게 기록할것"(#240 5854486187)이다. 게시 원문대로 회전 1–4 판정은 v1 · v2 그대로 둔다.
- v3 는 #756 검토(5855093172)가 문장 불일치를 짚었을 때 이미 동결돼 제자리에서 고칠 수 없었다. 어느 run 도 v3 를 인용하지 않았다.

## D — v0.5.0 = `a4b1a4e`

| 항목 | 값 |
| --- | --- |
| 태그 대상 | `a4b1a4e8f1b27dfb8c107967c138942f1b1e6dc6`(= `v0.5.0-rc.1`, 회전 3 · 4 · 5 코드) |
| 기록 | [2026-09-27-jaebeom-v0-5-0.md](../../evidence/deployments/2026-09-27-jaebeom-v0-5-0.md)(#750, 병합 2026-09-27T09:18:10Z) |
| 무실패 회전 | 없음(회전 1–4 모두 16/16 미충족) |
| 새 clone 재현(phase F, attempt 16) | 회전 1 PASS(503.087 s) · 회전 4 PASS(태그 `v0.5.0-rc.1` clone, 503.786 s) · 회전 2 · 3 미실행 |
| 판정 단계 | L3 관측. 계약 합격은 v1 · v2 판정선으로는 없다 |
