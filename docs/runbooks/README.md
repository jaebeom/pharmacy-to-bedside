# 런북 색인

마스터에서 무엇을 어떤 순서로 돌리는지 적은 문서들이다. 지금 쓰는 것과 지난 기록을 나눴다.

- 지금 기준은 릴리스 `v1.1.0` = main `f316197`(#797)이다. 목록은 `gh release list`, 상세는 `gh release view v1.1.0` 이다.
- 장비는 `master01` = `IsaacSim14`, `master02` = `IsaacSim07` 이다([장비 목록](../setup/host-inventory.md)).
- 마스터 PC 에서 작업하기 전에 [배포 런북](deployment.md)부터 읽는다([공통 규칙](../process/repository-rules.md)). 처음 돌리면 [병원 한 바퀴 런카드](hospital-full.md) 0절 → 1절 → 2절 순서다.

## 현행

"마지막 확인"은 그 커밋의 코드·스크립트와 문서를 대조한 날이다. Isaac 에서 돌려 본 날이 아니다.

| 런북 | 무엇을 하나 | 마지막 확인 |
| --- | --- | --- |
| [deployment.md](deployment.md) | 마스터에서 릴리스를 따로 받아 빌드·실행·중지·롤백한다 | `f316197` · 2026-09-30 |
| [hospital-full.md](hospital-full.md) | 병원 전 구간 한 바퀴의 준비·명령·주문 전 점검·판정·기준 구성·촬영 테이크 | `f316197` · 2026-09-30 |
| [hospital-demo.md](hospital-demo.md) | 병원 데모의 환경 변수·웹 요청·관찰 지점·촬영 화면 점검·두 PC 기동 | `f316197` · 2026-09-30 |
| [hospital-nav-l3.md](hospital-nav-l3.md) | 병원 주행 참고. 지도·앵커·구역·경로 재생성과 장애물 층 토픽. 9/23 주행 단독 L3 기록이 같이 있다 | `f316197` · 2026-09-30 |
| [stat-s0-stub.md](stat-s0-stub.md) | STAT S0(제안 계약) 스텁을 ROS·Isaac 없이 손으로 재현한다(L1). 병원 시연과 따로다 | `f316197` · 2026-09-30(1절 정상 한 바퀴를 개발 PC 에서 재현) |

`v1.1.0` 트리로 돈 한 바퀴 L3 는 이 색인을 쓴 시각에 없었다. acceptance 회전도 없었다(릴리스 노트, #797).
동결 protocol v4 를 넘은 것은 `v1.0.0` 회전 7(`9760d9d`, 참값 집기)이다([회전 장부](../reha/campaigns.md)).

## 지난 기록

첫머리에 "상태: 지난 기록" 줄이 있다. 본문은 그때 기록이라 고치지 않는다. 명령·값을 지금 트리에 그대로 쓰지 않는다.
"마지막 확인"은 그 파일을 마지막으로 고친 커밋이다(이 색인의 상태 줄 추가는 빼고).

| 런북 | 무엇이었나 | 마지막 확인 | 지금은 |
| --- | --- | --- | --- |
| [demo-0921-v2.md](demo-0921-v2.md) | 9/21 1차 시연. `master02` 한 대에서 조제실 장면 v2·M0609 v2·어댑터 스택·웹 | `cff4083` · 2026-09-21 | [hospital-demo](hospital-demo.md) |
| [demo-rehearsal-buttons.md](demo-rehearsal-buttons.md) | 9/21 시연 대본을 웹 버튼으로 도는 리허설(실습14, v0.3.0 후보) | `d909882` · 2026-09-23 | [hospital-demo](hospital-demo.md) 4절 |
| [emptyworld-lap-navigation-waits.md](emptyworld-lap-navigation-waits.md) | 빈월드 한 바퀴에서 주행 구간이 기다리는 자리(코드 읽기, L3 미실행) | `e92dd0d` · 2026-09-21 | [hospital-full](hospital-full.md) |
| [emptyworld-lap-stack.md](emptyworld-lap-stack.md) | 빈월드 한 바퀴(lap14)의 기동 조합 | `5c29788` · 2026-09-24 | [hospital-full](hospital-full.md) |
| [evidence-run-pharmacy-lap.md](evidence-run-pharmacy-lap.md) | 조제실 한 바퀴를 `pharmacy-lap-pilot-v1` 증거 run 으로 남기는 순서 | `24853de` · 2026-09-20 | [hospital-full](hospital-full.md), [evidence README](../../evidence/README.md) |
| [l3-arm-perception.md](l3-arm-perception.md) | UR5 팔·손 카메라 인식 런카드 VA-1–VA-7 | `03c7b84` · 2026-09-20 | [hospital-full](hospital-full.md) |
| [l3-sim-conveyor.md](l3-sim-conveyor.md) | 조제실 벨트·UR5·관측 opt-in·병원 씬 런카드 RC-1–RC-6 | `24b8eb5` · 2026-09-23 | [hospital-full](hospital-full.md) |
| [l3-stack-combos.md](l3-stack-combos.md) | 스택 기동 조합과 opt-in 짝(`demo_v2.sh` 시연 경로) | `24853de` · 2026-09-20 | [hospital-demo](hospital-demo.md) 2절 |
| [master02-m0609-refill-stage.md](master02-m0609-refill-stage.md) | `master02` 에서 M0609 보충 스테이지(레일 없음)와 ROS 스택 | `89c363d` · 2026-09-20 | [hospital-full](hospital-full.md) |
| [master02-pharmacy-stack.md](master02-pharmacy-stack.md) | `master02` 스텁 없는 조제실 한 바퀴(9/17) | `0d3668e` · 2026-09-20 | [hospital-full](hospital-full.md) |
| [practice38-handoff.md](practice38-handoff.md) | 실습38 인계. 1350개 진열 장면 복원과 ROS 통합의 구분 | `626cb5c` · 2026-09-23 | [hospital-full](hospital-full.md) 1절 |

[배포 런북](deployment.md)의 "부록 — 스텁 루프 절차"도 9/17 기록이다.
