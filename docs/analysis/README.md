# 분석

관측은 evidence의 run과 artifact에 있다. 이곳에는 자료에서 도출한 해석을 둔다.
상태(unreviewed/verified/rejected/superseded), 작성자·검토자, run/리뷰,
적용 환경·버전, 경쟁 가설·반증·한계를 적는다.

verified는 검토한 범위의 결론이다. 다른 환경 적용은 재검증한다.
설계 결정은 [ADR](../adr/README.md)로 연결하고 숫자 원장을 복사하지 않는다.
2026-09-30 파일 기준으로 상태가 verified 인 분석은 없다.

여기 문서는 모두 기준일이 있는 **기록**이다. 본문을 고치지 않는다. 정정은 새 문서와 `supersedes` 로 한다.
지금 코드·절차의 기준은 [문서 목차](../README.md)의 현행 문서를 본다.

## 날짜 붙은 분석

최신이 위다. 2026-09-30 파일 목록과 대조했다.

| 문서 | 무엇 |
| --- | --- |
| [2026-09-30-jaebeom-improvement-candidates.md](2026-09-30-jaebeom-improvement-candidates.md) | 우리 빈자리(도킹·동적 장애물·다중 AMR·인식 깊이·재전송 안전·참값 의존)별 개선안 32건과 추천 순서. unreviewed, 정적 점검이다 |
| [2026-09-30-jaebeom-documentation-audit.md](2026-09-30-jaebeom-documentation-audit.md) | 코드·리하·234개 문서와 열린 PR 14개 대조. README·API 누락 보완, 기존 PR 충돌·링크 후속 2건. unreviewed |
| [2026-09-29-master01-workcell-fixture-diff.md](2026-09-29-master01-workcell-fixture-diff.md) | master01 v1.0.0 리하 회차 workcell.json 과 integrated-09 fixture 대조(9/29). pill_offset·브래킷·RoundBin 이동·source_sha256 이 다르다. unreviewed, 파일 대조만 |
| [2026-09-25-v050-scorecard-evidence-map.md](2026-09-25-v050-scorecard-evidence-map.md) | v0.5.0 용으로 점수판 110점 항목마다 요구 증거 · protocol attempt · 있는 회차 · 빈 곳을 맞췄다(9/25). protocol 수정 제안 7건이다. 제안이다 |
| [2026-09-24-speed-90-plan.md](2026-09-24-speed-90-plan.md) | 가능 속도의 90%: M0609·UR5·레일·AMR 직진/회전·감속기·벨트·트레이의 현재값·기준·90% 목표·설정 위치·위험과 실행 순서(오프라인) |
| [2026-09-24-jaebeom-architecture-gap-review.md](2026-09-24-jaebeom-architecture-gap-review.md) | 설계 문서 전체와 코드·도구·CI 를 대조했다(9/24). 골든 값이 다르다. 증거 파이프라인이 끊긴다. 예외 문서와 ADR 이 비다. 계약 어휘가 겹친다. 웹이 상태를 추정한다. 설정 env 는 90종이다. P0-P2 로 나눠 반영안과 액션 목록을 둔다. 정적 점검이다 |
| [2026-09-24-design-gap-plan.md](2026-09-24-design-gap-plan.md) | 설계 문서(architecture·adr)와 골든-4 `aca8840` 실행의 차이를 점검하고 G 항목별 계획을 세웠다(9/24). 계획이다. 구현·통과를 선언하지 않는다 |
| [2026-09-24-open-decisions.md](2026-09-24-open-decisions.md) | 미결 설계 결정표(G6). 재범 9/24 13:30 "미결 권고대로 진행"(#576) 뒤의 결정 기록이다. 반영은 담당 문서 PR 이 한다 |
| [2026-09-24-web-order-process-coverage.md](2026-09-24-web-order-process-coverage.md) | 관제 화면이 주문 한 건의 단계를 다 보여 주는지 점검했다(main `8caa155`). 코드와 계약으로 본 오프라인 점검이다 |
| [2026-09-23-hospital-sim-load.md](2026-09-23-hospital-sim-load.md) | 병원 시뮬 부하. 회차 rtf 는 두 무리다. 약통과 선반 접촉 보고 경고는 41만 줄이다. 39d1ce5 rtf 는 0.340 이다. GPU 는 80 W 상한이다 |
| [2026-09-23-jaebeom-session-ops-code-review.md](2026-09-23-jaebeom-session-ops-code-review.md) | 9/23 현황 재검토. 네비게이션 결함, 통합 후보, 다음 실행 순서다(main `bfeb4af`). Isaac·ROS 실행은 하지 않았다 |
| [2026-09-22-dispenser-hospital-alignment.md](2026-09-22-dispenser-hospital-alignment.md) | #483/#486 후속: 준비기 실패, 조제기·투입구 좌표, #484/#485 연결, 레일 IK와 미실행 검증 |
| [2026-09-21-test-amr-intake.md](2026-09-21-test-amr-intake.md) | 이태규님 `test_amr` 인수 — #383 으로 반영한 값과 출처, 반영하지 않은 것, 남은 질문(지도 출처·문 폭), 맵 원점 판정선 |
| [2026-09-21-jaebeom-acceptance-review.md](2026-09-21-jaebeom-acceptance-review.md) | acceptance protocol 설계 검토(9/21, main `4b506c1`). 권고는 동결 보류다. 검토 제안이다 |
| [2026-09-21-stub-hidden-truth-review.md](2026-09-21-stub-hidden-truth-review.md) | 스텁이 가린 진실. 독립 감사와 acceptance 동결 판단이다(9/21, `83a2a1f`). 검토 제안이다. 현장 실행은 미실행이다 |
| [2026-09-20-jaebeom-status-bottlenecks-code-review.md](2026-09-20-jaebeom-status-bottlenecks-code-review.md) | main·시연 태그·#383 대조, P32·INT-3·주행/관측/증거 병목, 시연 및 최종 통합 진행 순서 |
| [2026-09-20-jaebeom-pegasus-code-review.md](2026-09-20-jaebeom-pegasus-code-review.md) | Pegasus 보고서 검증과 STAT 비행·Pod 인계·단계별 검증 계획 보강 |
| [2026-09-19-jaebeom-world-integration-code-review.md](2026-09-19-jaebeom-world-integration-code-review.md) | 빈월드·세준 병원 씬 통합 제안 대조, #215 좌표 결정·#233 분기 벨트·문 통과 기준 검토 |
| [2026-09-19-ur5-delivery-code-review.md](2026-09-19-ur5-delivery-code-review.md) | UR5 배송 계획 재검토 R1–R9, 목적지·물품 위치·제어권 계약, 설계 이미지 4종과 T01–T10. #232 |
| [2026-09-18-jaebeom-module-path-code-review.md](2026-09-18-jaebeom-module-path-code-review.md) | 모듈 운반 지시문 검토, 후보 전체 경로 시간 비교, LIN·파지·외축 정지 인터록. 선택형 Isaac 후보 |
| [2026-09-18-jaebeom-module-default-code-review.md](2026-09-18-jaebeom-module-default-code-review.md) | v2 모듈 경로 기본 활성화 구현 검토(main `0baef83`). Isaac L3·실기는 미실행이다 |
| [2026-09-18-jaebeom-guarded-feedback-review.md](2026-09-18-jaebeom-guarded-feedback-review.md) | Guarded 모듈 피드백 8개 항목과 기본 활성화의 연쇄 영향(main `0baef83`). unreviewed 수정 후보다. Isaac L3·실기는 미실행이다 |
| [2026-09-18-jaebeom-a1-a4-code-review.md](2026-09-18-jaebeom-a1-a4-code-review.md) | 외부 기술 검토 A1-A4(창 모드 종료, executor, ActionServer 종료, 벨트 scale). #185 |

## 날짜 없는 분석

파일 이름에 날짜가 없다. 기준일과 기준 SHA 는 본문 머리에 있다.

| 문서 | 무엇 |
| --- | --- |
| [hospital-amr-count-load.md](hospital-amr-count-load.md) | 합본 AMR 1-4대 부하. 측정 규약이다. 판정선은 결과 전에 고정한다. N별 비교표가 있다 |
| [hospital-perf-0923.md](hospital-perf-0923.md) | 병원 전 구간 성능 정리: 기동은 팔 캐시 73.6 s, rtf 0.42 는 GPU 80 W 고정과 omni.graph 35%·physx 17%. 시도한 것과 남은 후보 |
| [hospital-door-entrapment-20260923.md](hospital-door-entrapment-20260923.md) | 병원 문 주변 AMR 갇힘. 사용자 캡처 두 장 보고다(9/23). 원인·수정·L3 는 미완료다. 그림은 `images/hospital-door-entrapment/` 에 있다 |
| [practice38-image-audit.md](practice38-image-audit.md) | 실습38 이미지 감사와 화면 문제다. 그림과 해시 목록([manifest](images/practice38-handoff/manifest.json))은 `images/practice38-handoff/` 에 있다 |
| [node-topology-v1.md](node-topology-v1.md) | AMR 1대 v1 의 노드 수 추정, 작성자·제어 소유권 점검(정적, 9/17) |
| [communication-state-inventory-v1.md](communication-state-inventory-v1.md) | 토픽·서비스·액션의 노드별 연결과 운영 상태(정적 구현 목록, 9/17) |
| [hospital-integration-source-snapshot.md](hospital-integration-source-snapshot.md) | 병원 통합 임시 소스 보존. 2026-09-22 모델링·진단·실패 시도 원문이다. 완성 런타임이 아니다 |

[실습35](../practice/practice-35.md)가 쓰는 데이터 파일 둘이 있다.
[외부 원본 목록](hospital-integration-artifacts.json)은 원본 위치·크기·전체 해시다.
[소스 목록](hospital-integration-source-manifest.json)은 임시 스크립트의 해시다.
