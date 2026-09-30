# acceptance campaign 장부 — hospital-full-acceptance v1 · v2 · v4

> 기준 2026-09-29 15:00 KST, main `6928f4b`.
> protocol 은 [v1](../../experiments/protocols/hospital-full-acceptance-v1.json)(frozen 2026-09-24T23:14:44Z) · [v2](../../experiments/protocols/hospital-full-acceptance-v2.json)(frozen 2026-09-27T02:56:34Z, phase E 와 회전 5) · [v4](../../experiments/protocols/hospital-full-acceptance-v4.json)(frozen 2026-09-27T10:55:54Z, 회전 6 · 7)이다. v3(frozen 09:56:06Z)는 어느 run 도 인용하지 않고 v4 로 대체됐다(#773). attempt 는 16개다. seed 7 한 블록이다. 14 · 15 는 seed 11 · 23 이다.
> run 기록은 `evidence/runs/` 에 있다. 이 장부는 campaign 별 합계와 **등록하지 못한 attempt** 를 모은다. 9/28 부터 campaign 을 "회전"(r5 · r6 · r7)이라 부른다.
> 9/29 갱신: 회전 3 · 4 행은 뒤에 등록된 run(#737–#748)과 [v0.5.0 배포 기록](../../evidence/deployments/2026-09-27-jaebeom-v0-5-0.md)으로 다시 셌다. FAIL 은 그 기록의 failure_class(infra · robot · operator)로 나눴다 — 옛 표의 "보류"(회전 2 · 12 · 13)는 v0.5.0 기록이 infra FAIL 로 센 것이다.

## 1. campaign 별 합계

| campaign(회전) | 코드 | protocol | run | PASS | FAIL infra | FAIL robot | FAIL operator | 미실행 · 셈 밖 | run PR |
| --- | --- | --- | ---: | ---: | --- | --- | --- | --- | --- |
| 1 | `64e5ab7`(RC-4) | v1 | 14 | 12 | 1(3 — 관측 스크립트 조기 종료) | 1(6 — 병실 묶음 보관함 present 누락, fed2373) | 0 | 12 · 13 취소(재범 "빨리") | #710 · #711 · #713 · #716 |
| 2 | `0b1319b`(main) | v1 | 15 | 12 | 3(10 — Isaac 세그폴트 · 12 · 13 — v1 문구 결함, 결정 (C)) | 0 | 0 | 16 | #717 · #718 · #723 · #726 |
| 3 | `a4b1a4e`(더미 ON) | v1 · v2(12 · 13) | 16 | 13 | 0 | 0 | 3(12 · 13 · 15 첫 run) | 16 · 장부만 14 · 15 · 12 × 2 · 16 × 2(2절 · v0.5.0 기록) | #724 · #727 · #730 · #741 · #744 · #745 · #747 · #748 |
| 4 | `a4b1a4e` | v1 | 16 | 14 | 2(4R 4 — GPU 15 W · 4R 5 — 녹화기 버퍼 정지) | 0 | 0 | 12 · 13 취소 · 원래 run 8(1–5 · 7 · 8 · 14)은 원본 소실로 셈 제외, 4R 로 대체 | #729 · #731 · #737 · #740 · #741 |
| 5(r5, 중단) | `a4b1a4e` | v2 | 2 | 2 | 0 | 0 | 0 | 3–16(중단, 재범 결정 안 2) | #750 |
| 6(r6, 중단) | `9760d9d` | v4 | 3 | 0 | 0 | 0 | 3(1 · 2 · 3 — 관측 스크립트 사본 gaps 기록기 누락 → watchdog 오탐) | 4–16(중단) | #776 |
| 7(r7) | `9760d9d` | v4 | 14 | 14 | 0 | 0 | 0 | 12 · 13(두 PC) — 재범 결정 A 로 생략 · 셈 제외 3(3절) | #777 · #778 |
| 합 | — | — | 80 | 67 | 6 | 1 | 6 | — | — |

- 누적은 67/80 이다(등록 run 기준, 기준 시각 2026-09-29 15:00 KST). 회전 1–5 는 [v0.5.0 기록](../../evidence/deployments/2026-09-27-jaebeom-v0-5-0.md)의 63 run · 53 PASS · 10 FAIL 과 같다. 회전 6 · 7 은 run 기록을 직접 셌다. 누적은 protocol 이 다르고 코드가 다른 회전을 더한 값이다 — 판정선이 아니다. 판정은 회전마다 한다. 반복 수는 합의로 정한 값이다. 신뢰도 주장이 아니다(protocol 3절).
- **판정선.** v1 · v2 는 16/16 무실패였다. v3 · v4 는 회전마다 **≥15/16(90 % 이상)** 이고, 실패 run 마다 `failure_class`(robot · infra · operator) · `failure_cause` 가 있어야 한다(`requires_failure_classification`). 근거는 재범 결정 "목표를 성공률 90% 정도로 완화하고, 실패 상황을 명확하게 기록할것"(#240 5854486187)이다. v3(#751 · #756)는 동결 뒤 purpose 문장 불일치 5곳 때문에 v4(#773)로 대체됐다.
- **회전 7 판정: 14/14 = 100 %.** master01 몫(attempt 1–11 · 14–16)이다. 판정 표는 #771 5867873681(`tools/round_summary.py`)이다. attempt 12 · 13(두 PC)은 재범 결정 A 로 이 회전에서 생략했다(#772 5868396013). 두 PC 증거는 회전 1–3(#726 · #747 · #745)을 인용하고 v1.0 SHA 에서는 미검증이다([v1.0.0 기록](../../evidence/deployments/2026-09-28-jaebeom-v1-0-0.md)).
- 회전 6 은 main `9760d9d` · v4 로 시작했다(#771 5861649339). attempt 1 · 2 · 3 이 operator FAIL 로 끝나 중단 회전이 됐고 회전 7 을 같은 SHA 로 다시 시작했다(#771 5861917816).
- 회전 5 는 v2 로 attempt 1 · 2 를 PASS 로 등록한 뒤 중단했다(재범 결정 안 2 "2안 가자", 원문 시각 2026-09-27 17:28 KST, #772 5884698592 늦은 게시). 판정선 완화(v3) 결정은 그 뒤다.
- campaign 2 attempt 12 · 13 은 배송 · 도크 복귀까지 됐다. 그러나 protocol v1 FAIL(#726)로 그대로 둔다(#576 5851441169 의 (C)). 사유는 protocol 문구 결함이다. v1 (c) 가 phase E 비-stage host 의 viewport SKIP 을 예외로 두지 않았다(#726 5848434922). 병합된 run 은 고치지 않는다. v2 로 supersedes 를 걸 수 없다. correction 은 protocol 이 같아야 한다.
- campaign 3 · 4 의 12 · 13(다중 PC)은 protocol v2(#733)를 동결한 뒤에 돌린다. v2 로 등록한다. 동결은 다중 root scene 지표 null 버그 수정 뒤다.
- campaign 2 master02 attempt 6 · 9 · 10 · 11 은 더미 OFF · 보행자 ON 이다. #723 5848424289 판정은 protocol 1)절이 허용한다는 것이다. attempt 10 의 사람 개입 수는 검토 정정으로 1 이다.

## 2. 등록하지 못한 attempt

| campaign | attempt | 무엇 | 등록 안 된 사유 | 원문 #240 |
| --- | ---: | --- | --- | --- |
| 3 | 14(회차144) | bed_a1 seed 11 | 기동 전에 끝났다. master01 배경 스크립트가 워크트리에 추적 안 된 파일(mpc-agg-wait.out)을 남겼다. 트리 확인이 dirty 로 중단했다. 산출물은 deployment · SUMMARY · tally · versions 뿐이다. aggregate 는 exit 1 이다. aborted run 을 만들었다. `evidence.py validate` 가 "acceptance run requires a clean code commit" 으로 거부했다. dirty 를 false 로 바꾸지 않았다(안 (a')). 정정 재실행분을 정식 run 으로 등록한다 | 5848378839 · 정정 5848391500 · aggregate 불가 5848434901 |
| 3 | 15(회차145) | bed_a1 seed 23 | 14 와 같은 원인 · 같은 처리 | 5848381881 · 5848391500 · 5848434901 |

- 9/29 갱신: 위 3 · 14 는 `20260927T055722Z-master01-530b9208` PASS(#741)로, 3 · 15 는 `20260927T055900Z-master02-223ca0c2` FAIL(#744) → `20260927T081600Z-master02-569a44d4` PASS(#748)로 재실행분이 등록됐다(v0.5.0 기록 "장부 항목" 절).

## 3. 회전 7 — 셈 제외 3건

run 을 만들지 않았거나 등록하지 않은 실행이다. 실패로 세지 않는다. 같은 attempt 의 올바른 재실행을 등록했다(#778 notes).

| attempt | 무엇 | 셈 제외 사유 | 등록한 재실행 run | 원문 #771 |
| ---: | --- | --- | --- | --- |
| 7 | phase C(Play/Stop) 첫 실행 | 보고의 tree.txt 가 `a4b1a4e` 로 찍혔다(gr6bin/m1-playstop.sh 안 하드코딩 경로). up.log 로는 실제 트리가 `9760d9d` 였지만, 스크립트를 고친 깨끗한 재실행을 등록했다 | `20260928T040305Z-master01-1595d104` | 5862527055 · 5862636822 → 5863254976 |
| 8 | phase C(Play/Stop) 첫 실행 | 7 과 같다 | `20260928T042107Z-master01-afb2bb32` | 5862730726 · 5862636822 → 5863289629 |
| 11 | phase B'(beds-all 10건) 첫 실행 | `--profile beds-all`(13건)로 돌아 protocol 명령(`--profile default --batch ""`, 10건)과 달랐다 — r7 attempt 로 세지 않았다 | `20260928T100416Z-master01-8fd7dbc7` | 5865935443 · 5865954562 → 5867774422 |

- attempt 6 · 16 은 셈 제외가 아니다. 첫 보고가 FAIL 이었지만 원인은 `M1_WEB_REC=1` 누락으로 event_run 이 복사되지 않은 것이었다. 같은 실행의 event_logger 폴더를 복사해 다시 집계했고 attempt_success 1 로 등록했다(run notes).
