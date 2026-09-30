# 2026-09-30 코드·리하 기준 문서 점검

- 상태: unreviewed. 문서 정합성 점검이며 배포 승인·L3 검증 결과가 아니다.
- 작성: jaebeom 계정의 문서 점검 작업. 검토자: 미정.
- 기준: main `d2ff8eb5cebcdc45536403dcd63148aaad0917bd`, 릴리스 `v1.1.0`(`f316197`).
- 범위: 기준 트리의 Markdown 230개와 `docs/` 발표 HTML 4개. 전체 목록은 아래에 있다.
- supersedes: 없음. 과거 분석·run·frozen protocol·배포 기록을 덮어쓰지 않는다.

## 판단 기준

현행 동작은 실행 코드와 설정으로, 리하 결과는 해당 SHA의 run·회전 장부로 확인했다.
문서 전부에 파일 목록·로컬 링크·Markdown 앵커·표 구조 검사를 적용했다.
실행 안내·패키지/API 설명은 현재 코드와 대조했다. 날짜가 붙은 실습·분석·발표 자료는 당시 기록으로 읽었다.
모든 과거 서술을 현재 동작으로 다시 검증했다는 뜻은 아니다. 외부 링크의 전체 생존 여부와 원본 영상은 검사하지 않았다.

## 현재 코드와 리하

| 항목 | 확인한 사실 | 근거 |
| --- | --- | --- |
| 회전 7 | protocol v4, 참값 집기, `9760d9d` 트리. 실행한 attempt 1–11·14–16은 14/14 PASS. 12·13은 미실행 확정이다 | [리하10](../reha/reha-10.md), [v1.0.0 배포](../../evidence/deployments/2026-09-28-jaebeom-v1-0-0.md), 최종 보고 |
| 판정 범위 | 초기 6·16의 이벤트 로그 누락, 7·8의 트리 메타데이터 오류, 11의 13건 입력은 정정·재실행과 구분한다. 14/14를 전체 시도나 카메라 신뢰성의 분모로 쓰지 않는다 | [회전 장부](../reha/campaigns.md), 리하10 |
| 현재 카메라 구성 | 병원은 `P3_CAMERA_POUCHES=1`, 인식표 카메라는 그 값을 따른다. 도크=적재 위치·근접 속도 0.7 m/s·컨베이어 변경이 포함된다 | [실행 스크립트](../../tools/demo_v2.sh), 릴리스 |
| 카메라 증거 | 후보 `05b8e28`에서 `bed_a1` 한 건의 집기·AUTH_OK·DELIVERED·도크 복귀를 확인했다. 통합 릴리스 전체의 acceptance나 반복 신뢰성 결과는 아니다 | [실습45](../practice/simworld/practice-45.md) |
| 다음 실습 | #806은 master01 stage, master02 arm/nav/stack/web, 유선 DDS와 휴대폰 Tailscale HTTP 계획이다. 조회 시 결과 댓글은 0개였다 | 실습 카드 #806 |
| 미해결 | 정지 규칙 #752의 현장 발동은 해결·검증되지 않았다. 자기 충돌 gate #805는 미병합 종료다. `preferred_first`를 gate 구현으로 해석하지 않는다 | #752, #805 |

## 코드 대조와 보완

| 항목 | 코드 기준과 처리 |
| --- | --- |
| README 실행 예제 | `P3_REPO`·경로·환경변수를 같은 셸에 export한다. `env`·`cmds`는 명령 확인이고 기동은 `up`이다. worktree로 이동한 뒤 빌드한다 |
| 평가 관측 | `P3_SIM_SENSORS`의 스크립트 기본은 0, 카메라 프로필은 1이다. 보관함 평가 관측에는 1이 필요하다. 프로필은 zones·routes·팔 설정도 고정한다 |
| 종료 | `demo_v2.sh`의 `DOWN_ALL`은 월드·역할 설정과 관계없이 해당 PC의 자체 nav 세션까지 정리한다. README의 과거 nav 잔류 설명을 고쳤다 |
| launch | 선언 45개(STUBS 4개 포함). 누락된 `belt_timeout_s`·`dispense_timeout_s`·`vision_check`·검출 rate/save 인자 셋은 #813이 추가한다 |
| 주행·팔·인식 | 병원 Nav2 마지막 접근은 직접 추종이다. 감속기의 1% 제한은 물리적 정지 보증이 아니다. `pouch_detector` 실행 파일 하나가 AMR·M0609 두 인스턴스로 뜬다. 관련 갱신은 #804·#808·#813에 있다 |
| 웹 signals | 기본 Bool 신호 5개와 선택적인 `speed_limit`을 구분했다. 선택 키는 수신 전 생략되며 `value` 대신 별도 필드가 있다. 근접 기본값은 70%, 신선도는 3 s다 |
| 웹 카메라·구독 | 카메라 목록 예제에 `amr_qr`·`m0609_qr`를 더했다. 영상 구독은 카메라별로 열린다. AMR tag_reads·rosout 구독, 병원 약통 QR 기본값을 보완했다 |
| 웹 상태 모델 | `status_view`의 함수·상수를 재사용하지만 웹 저장소는 `WorldState`다. `StatusModel`을 웹이 직접 채운다는 설명을 고쳤다 |
| 약통 스캔 기록 | `_on_check_container → PharmacyDb.check_container → record_scan` 경로가 있다. `bad_format`·`stale_epoch`도 기록한다. AMR 봉투·인식표 판독의 DB 저장과 구분했다 |
| 증거와 발표 | JSON manifest 95개, protocol 7개(6 frozen·1 proposed)를 확인했다. 파일 수를 성공률 분모로 쓰지 않는다. 발표 색인에 통합본 acceptance 부재와 #805 종료를 반영했다 |
| 링크·표 | 이전 README 스텁 실행 앵커를 호환 유지했다. orchestrator 표의 불필요한 열을 제거했다. architecture 표와 웹 도메인 앵커는 #804에서 고친다 |

코드 근거: [launch](../../src/rokey_p3_bringup/launch/stub_loop.launch.py),
[웹 구독](../../web/backend/app/ros_spec.py), [카메라](../../web/backend/app/live_sensors.py),
[웹 상태](../../web/backend/app/state.py), [약 DB](../../src/rokey_p3_orchestrator/rokey_p3_orchestrator/pharmacy_db.py),
[감속기](../../src/rokey_p3_navigation/rokey_p3_navigation/speed_governor.py).

## 열린 PR과 통합 범위

기존 변경을 이 PR에 복제하지 않았다. 네 파일은 같은 파일의 서로 다른 부분을 보완한다:
`config/README.md`, `web/api.md`, `web/backend/README.md`(#809), `src/rokey_p3_orchestrator/README.md`(#813).
기준 main을 공통 조상으로 둔 파일별 3-way 병합에서 이 보완분의 충돌은 0개였다.
이는 아래 head 스냅숏의 텍스트 통합 결과다. 이후 push나 실제 GitHub 병합 결과까지 보장하지 않는다.

| PR | head | 범위 |
| --- | --- | --- |
| #802 | `cab4caa0302d51600b3ed38c3871d6ced393a949` | 현행 런북 |
| #804 | `1ea8559b7c9629692d3a4a9ae21546e7742c866b` | 아키텍처·계약·정책 |
| #807 | `7e57ceaba0a1147059107d16180d6d1a17b56c40` | 문서·리하 색인 가독성 |
| #808 | `bb8fc0a4ffd957c94dea5aa571c310f4c5fb329a` | sim 실행·과거 기록 |
| #809 | `b322fcb0685ab8b55d2ddae8d0c71686475a9235` | web·tools·evidence·experiments |
| #810 | `5f52701565bac2f6f911ec29fb1c4014f9029e3f` | 실습 1–15 기록 표현 |
| #811 | `6a6a5dd4cc01a83377e343d76f702bbaa607306e` | 실습 18–44·월드 기록 표현 |
| #812 | `7abe7baa48cba2e2be9797024a2ca06aaa8e4f83` | 리하 기록 표현 |
| #813 | `e5a51346274087a52a5ee31f95977a6403802c99` | ROS 패키지 README |
| #814 | `53d775b5d07e5672cd5fc77e58d8fe9058749b9d` | 분석 기록 표현 |
| #815 | `b82bb7c0bff31a623b0eadb4a005b0b19005a12f` | planning·RFC·ADR 표현 |
| #816 | `b80c55594bfb6f4db07ecb9874e58c211920586a` | 발표 자료 표현 |
| #817 | `01c7ee0ee95358ffd6bf975c7b716b9f3dbecaee` | process·setup·reference 표현 |
| #818 | `1b9ac9c069f9ce226fecfbc3518bc4a6f8b11ffb` | agent-workflow 규칙 표현 |

### 기존 PR에서 남은 두 항목

1. **#804와 #815의 ADR 0002 첫머리 충돌.** 같은 `결정자` 줄을 각각 다르게 바꾼다.
   #804의 `결정자: 재범. 승인 전이다. 9/17 부터 코드가 이 방식을 쓴다`가 proposed 상태와 실제 구현을 구분한다.
   #815에서 이 파일의 동일 줄 수정을 제외하면 #804 내용을 유지하면서 나머지 정리를 적용할 수 있다.
2. **#813의 src/README.md에 없는 파일 링크.** `../inbox/README.md`는 기준 트리에 없다.
   해당 행을 `정리 전 메모·초안 | 로컬 작업 공간에 보관. 확정 문서는 docs/의 해당 영역으로 옮긴다`로 바꾸면 된다.
   현행 저장소 검사기는 `inbox`를 최상위 책임 영역으로 허용하지 않으므로 빈 파일을 추가해 막지 않는다.

두 항목은 기존 PR의 수정을 검토할 위치다. 다른 PR의 브랜치·승인·병합 상태는 변경하지 않았다.
#804의 `record_scan` 설명은 노드가 **직접** 호출하지 않는다는 뜻으로 읽어야 한다.
약통 서비스 내부의 간접 호출은 위 코드 경로와 패키지 README에 명시했다.

## 검증과 한계

| 검사 | 결과 |
| --- | --- |
| `git diff --check` | 통과 |
| `python3 tools/evidence.py validate --base origin/main` | 7 protocols·95 runs 통과. 측정값·원본 artifact·사람 승인 검증은 아니다 |
| `ruff check .` | 통과 |
| `python3 -m unittest discover -s tests` | 397개 중 396 통과, 1 실패. `TwoMasterTests.test_peer_checks_pass_then_the_clock_decides`: 로컬에 ping이 없고 netlink 접근이 거부돼 peer 검사를 진행하지 못했다 |
| 웹 `tests/test_contract_doc.py` | 209 passed. 기존 API 문서 정합성 검사 |
| `python3 tools/check_repository.py` | 로컬 대용량 이미지 1개를 받지 못해 링크 검사 1건 실패. 원격 트리에는 `docs/images/dispenser/dispenser-reference-mounts.png`가 있다. 통과로 기록하지 않는다 |
| 전체 로컬 링크·앵커·표 | 이 PR만 적용하면 #804 담당 기존 오류 2건이 남는다. 열린 PR을 함께 적용하면 #813의 inbox 링크 1건이 남는다. 위 ADR 충돌은 별도다 |
| 불변 기록 | run JSON·frozen protocol·배포/리뷰 본문 변경 없음. 원본 SHA와 구조 검사를 확인했다 |
| 미실행 | ROS colcon L1/L2, Isaac L3, 실제 마스터·휴대폰 실습. GitHub CI 결과는 PR에서 확인한다 |

## 문서 전수 목록

`이 PR`은 직접 보완, `#번호`는 대조한 기존 PR, `보존·점검`은 목록·링크·상태를 확인하고 본문을 유지한 문서다.
여러 표시가 있으면 같은 파일을 나눠 다룬다. 과거 기록의 숫자·실패·판정은 현재 설명으로 덮어쓰지 않는다.
추가 문서인 이 점검표와 #802 런북 색인, #804 ADR 0007은 기준 234개 분모 밖이다.

<details>
<summary>기준 트리 234개 문서와 처리 위치</summary>

| 문서 | 처리 |
| --- | --- |
| [.github/pull_request_template.md](../../.github/pull_request_template.md) | 보존·점검 |
| [docs/process/repository-rules.md](../process/repository-rules.md) | v1.1.2 에서 루트 규칙 파일을 여기로 옮김 |
| [CONTRIBUTING.md](../../CONTRIBUTING.md) | 보존·점검 |
| [README.md](../../README.md) | 이 PR |
| [config/README.md](../../config/README.md) | 이 PR, #809 |
| [config/local/README.md](../../config/local/README.md) | 보존·점검 |
| [docs/README.md](../README.md) | #807 |
| [docs/adr/0000-template.md](../adr/0000-template.md) | 보존·점검 |
| [docs/adr/0001-orchestrator-trip-fsm.md](../adr/0001-orchestrator-trip-fsm.md) | #815 |
| [docs/adr/0002-isaac-json-topics-and-ros-adapter.md](../adr/0002-isaac-json-topics-and-ros-adapter.md) | #804, #815 |
| [docs/adr/0003-ward-driving-approach-point.md](../adr/0003-ward-driving-approach-point.md) | 보존·점검 |
| [docs/adr/0004-auth-pick-v0-truth-sensors.md](../adr/0004-auth-pick-v0-truth-sensors.md) | #815 |
| [docs/adr/0005-deployment-single-master-default.md](../adr/0005-deployment-single-master-default.md) | #804, #815 |
| [docs/adr/0006-hospital-scene-and-performance-defaults.md](../adr/0006-hospital-scene-and-performance-defaults.md) | #815 |
| [docs/adr/README.md](../adr/README.md) | #804 |
| [docs/analysis/2026-09-18-jaebeom-a1-a4-code-review.md](2026-09-18-jaebeom-a1-a4-code-review.md) | 보존·점검 |
| [docs/analysis/2026-09-18-jaebeom-guarded-feedback-review.md](2026-09-18-jaebeom-guarded-feedback-review.md) | 보존·점검 |
| [docs/analysis/2026-09-18-jaebeom-module-default-code-review.md](2026-09-18-jaebeom-module-default-code-review.md) | 보존·점검 |
| [docs/analysis/2026-09-18-jaebeom-module-path-code-review.md](2026-09-18-jaebeom-module-path-code-review.md) | #814 |
| [docs/analysis/2026-09-19-jaebeom-world-integration-code-review.md](2026-09-19-jaebeom-world-integration-code-review.md) | #814 |
| [docs/analysis/2026-09-19-ur5-delivery-code-review.md](2026-09-19-ur5-delivery-code-review.md) | 보존·점검 |
| [docs/analysis/2026-09-20-jaebeom-pegasus-code-review.md](2026-09-20-jaebeom-pegasus-code-review.md) | #814 |
| [docs/analysis/2026-09-20-jaebeom-status-bottlenecks-code-review.md](2026-09-20-jaebeom-status-bottlenecks-code-review.md) | #814 |
| [docs/analysis/2026-09-21-jaebeom-acceptance-review.md](2026-09-21-jaebeom-acceptance-review.md) | #814 |
| [docs/analysis/2026-09-21-stub-hidden-truth-review.md](2026-09-21-stub-hidden-truth-review.md) | #814 |
| [docs/analysis/2026-09-21-test-amr-intake.md](2026-09-21-test-amr-intake.md) | #814 |
| [docs/analysis/2026-09-22-dispenser-hospital-alignment.md](2026-09-22-dispenser-hospital-alignment.md) | 보존·점검 |
| [docs/analysis/2026-09-23-hospital-sim-load.md](2026-09-23-hospital-sim-load.md) | #814 |
| [docs/analysis/2026-09-23-jaebeom-session-ops-code-review.md](2026-09-23-jaebeom-session-ops-code-review.md) | #814 |
| [docs/analysis/2026-09-24-design-gap-plan.md](2026-09-24-design-gap-plan.md) | #814 |
| [docs/analysis/2026-09-24-jaebeom-architecture-gap-review.md](2026-09-24-jaebeom-architecture-gap-review.md) | #814 |
| [docs/analysis/2026-09-24-open-decisions.md](2026-09-24-open-decisions.md) | #814 |
| [docs/analysis/2026-09-24-speed-90-plan.md](2026-09-24-speed-90-plan.md) | #814 |
| [docs/analysis/2026-09-24-web-order-process-coverage.md](2026-09-24-web-order-process-coverage.md) | #814 |
| [docs/analysis/2026-09-25-v050-scorecard-evidence-map.md](2026-09-25-v050-scorecard-evidence-map.md) | #814 |
| [docs/analysis/2026-09-29-master01-workcell-fixture-diff.md](2026-09-29-master01-workcell-fixture-diff.md) | #814 |
| [docs/analysis/README.md](README.md) | 이 PR |
| [docs/analysis/communication-state-inventory-v1.md](communication-state-inventory-v1.md) | 보존·점검 |
| [docs/analysis/hospital-amr-count-load.md](hospital-amr-count-load.md) | #814 |
| [docs/analysis/hospital-door-entrapment-20260923.md](hospital-door-entrapment-20260923.md) | 보존·점검 |
| [docs/analysis/hospital-integration-source-snapshot.md](hospital-integration-source-snapshot.md) | #814 |
| [docs/analysis/hospital-perf-0923.md](hospital-perf-0923.md) | #814 |
| [docs/analysis/node-topology-v1.md](node-topology-v1.md) | 보존·점검 |
| [docs/analysis/practice38-image-audit.md](practice38-image-audit.md) | #814 |
| [docs/architecture/README.md](../architecture/README.md) | #804 |
| [docs/architecture/delivery-contract-v1-status.md](../architecture/delivery-contract-v1-status.md) | #804 |
| [docs/architecture/delivery-contract-v1.md](../architecture/delivery-contract-v1.md) | #804 |
| [docs/architecture/exception-outcomes-v1.md](../architecture/exception-outcomes-v1.md) | #804 |
| [docs/architecture/k5-delivery-interface.md](../architecture/k5-delivery-interface.md) | #804 |
| [docs/architecture/qr-camera-layout.md](../architecture/qr-camera-layout.md) | #804 |
| [docs/architecture/qr-db-camera-contract-v1.md](../architecture/qr-db-camera-contract-v1.md) | #804 |
| [docs/architecture/ros2-integration-table.md](../architecture/ros2-integration-table.md) | #804 |
| [docs/architecture/stage-arguments.md](../architecture/stage-arguments.md) | #804 |
| [docs/architecture/stat-delivery-contract-v1.md](../architecture/stat-delivery-contract-v1.md) | #804 |
| [docs/architecture/system-overview.md](../architecture/system-overview.md) | #804 |
| [docs/architecture/web-console.md](../architecture/web-console.md) | #804 |
| [docs/planning/conveyor-cps-integration-plan.md](../planning/conveyor-cps-integration-plan.md) | #815 |
| [docs/planning/empty-world-lap-inventory.md](../planning/empty-world-lap-inventory.md) | 보존·점검 |
| [docs/planning/emptyworld-lap-audit-followup.md](../planning/emptyworld-lap-audit-followup.md) | #815 |
| [docs/planning/emptyworld-lap-audit-pharmacy-to-delivery.md](../planning/emptyworld-lap-audit-pharmacy-to-delivery.md) | #815 |
| [docs/planning/first-day-checks.md](../planning/first-day-checks.md) | 보존·점검 |
| [docs/planning/integration-resource-two-phase-plan.md](../planning/integration-resource-two-phase-plan.md) | #815 |
| [docs/planning/m0609-rail-arm-optimization-plan.md](../planning/m0609-rail-arm-optimization-plan.md) | #815 |
| [docs/planning/m0609-rail-select-0921-report.md](../planning/m0609-rail-select-0921-report.md) | #815 |
| [docs/planning/mock-hospital-world-integration-plan.md](../planning/mock-hospital-world-integration-plan.md) | #815 |
| [docs/planning/p3-project-plan.md](../planning/p3-project-plan.md) | 보존·점검 |
| [docs/planning/p3-stat-implementation-plan.md](../planning/p3-stat-implementation-plan.md) | #815 |
| [docs/planning/pharmacy-scene-v2-plan.md](../planning/pharmacy-scene-v2-plan.md) | #815 |
| [docs/planning/plan-review.md](../planning/plan-review.md) | 보존·점검 |
| [docs/planning/scenario.md](../planning/scenario.md) | #815 |
| [docs/planning/schedule.md](../planning/schedule.md) | #815 |
| [docs/planning/two-master-final-stage-plan.md](../planning/two-master-final-stage-plan.md) | #815 |
| [docs/planning/ur5-hospital-delivery-implementation-plan.md](../planning/ur5-hospital-delivery-implementation-plan.md) | #815 |
| [docs/planning/vision-data-and-anomaly-plan.md](../planning/vision-data-and-anomaly-plan.md) | 보존·점검 |
| [docs/policy/metrics.md](../policy/metrics.md) | #804 |
| [docs/practice/README.md](../practice/README.md) | 보존·점검 |
| [docs/practice/emptyworld/README.md](../practice/emptyworld/README.md) | 보존·점검 |
| [docs/practice/emptyworld/practice-39.md](../practice/emptyworld/practice-39.md) | #811 |
| [docs/practice/emptyworld/practice-41.md](../practice/emptyworld/practice-41.md) | #811 |
| [docs/practice/emptyworld/practice-42.md](../practice/emptyworld/practice-42.md) | #811 |
| [docs/practice/practice-01.md](../practice/practice-01.md) | #810 |
| [docs/practice/practice-02.md](../practice/practice-02.md) | #810 |
| [docs/practice/practice-03.md](../practice/practice-03.md) | #810 |
| [docs/practice/practice-04.md](../practice/practice-04.md) | #810 |
| [docs/practice/practice-05.md](../practice/practice-05.md) | #810 |
| [docs/practice/practice-06.md](../practice/practice-06.md) | #810 |
| [docs/practice/practice-07.md](../practice/practice-07.md) | #810 |
| [docs/practice/practice-08.md](../practice/practice-08.md) | #810 |
| [docs/practice/practice-09.md](../practice/practice-09.md) | #810 |
| [docs/practice/practice-10.md](../practice/practice-10.md) | #810 |
| [docs/practice/practice-11.md](../practice/practice-11.md) | #810 |
| [docs/practice/practice-12.md](../practice/practice-12.md) | #810 |
| [docs/practice/practice-13.md](../practice/practice-13.md) | #810 |
| [docs/practice/practice-14.md](../practice/practice-14.md) | #810 |
| [docs/practice/practice-14b.md](../practice/practice-14b.md) | #810 |
| [docs/practice/practice-15.md](../practice/practice-15.md) | #810 |
| [docs/practice/practice-18.md](../practice/practice-18.md) | #811 |
| [docs/practice/practice-19.md](../practice/practice-19.md) | #811 |
| [docs/practice/practice-20.md](../practice/practice-20.md) | #811 |
| [docs/practice/practice-22.md](../practice/practice-22.md) | #811 |
| [docs/practice/practice-30.md](../practice/practice-30.md) | #811 |
| [docs/practice/practice-31.md](../practice/practice-31.md) | #811 |
| [docs/practice/practice-32.md](../practice/practice-32.md) | #811 |
| [docs/practice/practice-33.md](../practice/practice-33.md) | #811 |
| [docs/practice/practice-34.md](../practice/practice-34.md) | #811 |
| [docs/practice/practice-35.md](../practice/practice-35.md) | #811 |
| [docs/practice/simworld/README.md](../practice/simworld/README.md) | 보존·점검 |
| [docs/practice/simworld/practice-37.md](../practice/simworld/practice-37.md) | #811 |
| [docs/practice/simworld/practice-38.md](../practice/simworld/practice-38.md) | #811 |
| [docs/practice/simworld/practice-39.md](../practice/simworld/practice-39.md) | #811 |
| [docs/practice/simworld/practice-40-source-addendum.md](../practice/simworld/practice-40-source-addendum.md) | #811 |
| [docs/practice/simworld/practice-40.md](../practice/simworld/practice-40.md) | #811 |
| [docs/practice/simworld/practice-43.md](../practice/simworld/practice-43.md) | #811 |
| [docs/practice/simworld/practice-44.md](../practice/simworld/practice-44.md) | #811 |
| [docs/practice/simworld/practice-45.md](../practice/simworld/practice-45.md) | 보존·점검 |
| [docs/presentation/README.md](../presentation/README.md) | 이 PR |
| [docs/presentation/challenge-exceptions.md](../presentation/challenge-exceptions.md) | #816 |
| [docs/presentation/challenge-hospital-nav2.md](../presentation/challenge-hospital-nav2.md) | #816 |
| [docs/presentation/challenge-multipc-bench.md](../presentation/challenge-multipc-bench.md) | #816 |
| [docs/presentation/challenge-report-0925.md](../presentation/challenge-report-0925.md) | 보존·점검 |
| [docs/presentation/challenge-rtf-levers.md](../presentation/challenge-rtf-levers.md) | #816 |
| [docs/presentation/edit-plan-5min.md](../presentation/edit-plan-5min.md) | #816 |
| [docs/presentation/gaps-110.md](../presentation/gaps-110.md) | #816 |
| [docs/presentation/hospital-demo-shotlist.md](../presentation/hospital-demo-shotlist.md) | #816 |
| [docs/presentation/qr-reading-rounds.md](../presentation/qr-reading-rounds.md) | #816 |
| [docs/presentation/scorecard.md](../presentation/scorecard.md) | #816 |
| [docs/presentation/slides.html](../presentation/slides.html) | 보존·점검 |
| [docs/presentation/talk-5min.md](../presentation/talk-5min.md) | #816 |
| [docs/presentation/tech-3-sources.md](../presentation/tech-3-sources.md) | 보존·점검 |
| [docs/presentation/tech-3.html](../presentation/tech-3.html) | 보존·점검 |
| [docs/presentation/tutor-main.html](../presentation/tutor-main.html) | 보존·점검 |
| [docs/presentation/tutor-response.html](../presentation/tutor-response.html) | #816 |
| [docs/presentation/tutor-response.md](../presentation/tutor-response.md) | 보존·점검 |
| [docs/process/README.md](../process/README.md) | #817 |
| [docs/process/agent-workflow.md](../process/agent-workflow.md) | #818 |
| [docs/process/development-process.md](../process/development-process.md) | 보존·점검 |
| [docs/process/foundation-research.md](../process/foundation-research.md) | #817 |
| [docs/process/git-start-guide.md](../process/git-start-guide.md) | #817 |
| [docs/process/github-governance.md](../process/github-governance.md) | #817 |
| [docs/process/naming.md](../process/naming.md) | #817 |
| [docs/process/repository-layout.md](../process/repository-layout.md) | 보존·점검 |
| [docs/process/workspace-layout.md](../process/workspace-layout.md) | 보존·점검 |
| [docs/reference/README.md](../reference/README.md) | 보존·점검 |
| [docs/reference/tutor/README.md](../reference/tutor/README.md) | 보존·점검 |
| [docs/reference/tutor/digital-twin-and-isaac-sim.md](../reference/tutor/digital-twin-and-isaac-sim.md) | 보존·점검 |
| [docs/reference/tutor/evaluation.md](../reference/tutor/evaluation.md) | #817 |
| [docs/reference/tutor/final-presentation-evaluation.md](../reference/tutor/final-presentation-evaluation.md) | 보존·점검 |
| [docs/reha/README.md](../reha/README.md) | #807 |
| [docs/reha/campaigns.md](../reha/campaigns.md) | #812 |
| [docs/reha/night-0924.md](../reha/night-0924.md) | #812 |
| [docs/reha/night-0925.md](../reha/night-0925.md) | #812 |
| [docs/reha/recordings-master01.md](../reha/recordings-master01.md) | #812 |
| [docs/reha/recordings-master02.md](../reha/recordings-master02.md) | #812 |
| [docs/reha/reha-01.md](../reha/reha-01.md) | #812 |
| [docs/reha/reha-02.md](../reha/reha-02.md) | #812 |
| [docs/reha/reha-03.md](../reha/reha-03.md) | #812 |
| [docs/reha/reha-04.md](../reha/reha-04.md) | #812 |
| [docs/reha/reha-05.md](../reha/reha-05.md) | #812 |
| [docs/reha/reha-06.md](../reha/reha-06.md) | #812 |
| [docs/reha/reha-07.md](../reha/reha-07.md) | #812 |
| [docs/reha/reha-08.md](../reha/reha-08.md) | #812 |
| [docs/reha/reha-09.md](../reha/reha-09.md) | #812 |
| [docs/reha/reha-10.md](../reha/reha-10.md) | #812 |
| [docs/reha/rounds-240.md](../reha/rounds-240.md) | #812 |
| [docs/reha/verification-0923.md](../reha/verification-0923.md) | #812 |
| [docs/rfc/0001-navigation-ward-routing-and-reset.md](../rfc/0001-navigation-ward-routing-and-reset.md) | #815 |
| [docs/rfc/README.md](../rfc/README.md) | 보존·점검 |
| [docs/runbooks/demo-0921-v2.md](../runbooks/demo-0921-v2.md) | #802 |
| [docs/runbooks/demo-rehearsal-buttons.md](../runbooks/demo-rehearsal-buttons.md) | #802 |
| [docs/runbooks/deployment.md](../runbooks/deployment.md) | #802 |
| [docs/runbooks/emptyworld-lap-navigation-waits.md](../runbooks/emptyworld-lap-navigation-waits.md) | #802 |
| [docs/runbooks/emptyworld-lap-stack.md](../runbooks/emptyworld-lap-stack.md) | #802 |
| [docs/runbooks/evidence-run-pharmacy-lap.md](../runbooks/evidence-run-pharmacy-lap.md) | #802 |
| [docs/runbooks/hospital-demo.md](../runbooks/hospital-demo.md) | #802 |
| [docs/runbooks/hospital-full.md](../runbooks/hospital-full.md) | #802 |
| [docs/runbooks/hospital-nav-l3.md](../runbooks/hospital-nav-l3.md) | #802 |
| [docs/runbooks/l3-arm-perception.md](../runbooks/l3-arm-perception.md) | #802 |
| [docs/runbooks/l3-sim-conveyor.md](../runbooks/l3-sim-conveyor.md) | #802 |
| [docs/runbooks/l3-stack-combos.md](../runbooks/l3-stack-combos.md) | #802 |
| [docs/runbooks/master02-m0609-refill-stage.md](../runbooks/master02-m0609-refill-stage.md) | #802 |
| [docs/runbooks/master02-pharmacy-stack.md](../runbooks/master02-pharmacy-stack.md) | #802 |
| [docs/runbooks/practice38-handoff.md](../runbooks/practice38-handoff.md) | #802 |
| [docs/runbooks/stat-s0-stub.md](../runbooks/stat-s0-stub.md) | 보존·점검 |
| [docs/setup/README.md](../setup/README.md) | #817 |
| [docs/setup/host-inventory.md](../setup/host-inventory.md) | #817 |
| [docs/setup/ros2-wired-network.md](../setup/ros2-wired-network.md) | #817 |
| [docs/setup/tailscale.md](../setup/tailscale.md) | 보존·점검 |
| [docs/templates/contract.md](../templates/contract.md) | 보존·점검 |
| [docs/templates/deployment.md](../templates/deployment.md) | 보존·점검 |
| [docs/templates/diagnostic.md](../templates/diagnostic.md) | 보존·점검 |
| [docs/templates/evidence-review.md](../templates/evidence-review.md) | 보존·점검 |
| [evidence/README.md](../../evidence/README.md) | #809 |
| [evidence/deployments/2026-09-27-jaebeom-v0-5-0-rc-1.md](../../evidence/deployments/2026-09-27-jaebeom-v0-5-0-rc-1.md) | 보존·점검 |
| [evidence/deployments/2026-09-27-jaebeom-v0-5-0.md](../../evidence/deployments/2026-09-27-jaebeom-v0-5-0.md) | 보존·점검 |
| [evidence/deployments/2026-09-28-jaebeom-v1-0-0.md](../../evidence/deployments/2026-09-28-jaebeom-v1-0-0.md) | 보존·점검 |
| [evidence/deployments/README.md](../../evidence/deployments/README.md) | 이 PR |
| [evidence/reviews/2026-09-27-jaebeom-c4-artifact-loss.md](../../evidence/reviews/2026-09-27-jaebeom-c4-artifact-loss.md) | 보존·점검 |
| [evidence/reviews/2026-09-27-jaebeom-c4r-host-split.md](../../evidence/reviews/2026-09-27-jaebeom-c4r-host-split.md) | 보존·점검 |
| [evidence/reviews/README.md](../../evidence/reviews/README.md) | 보존·점검 |
| [evidence/runs/README.md](../../evidence/runs/README.md) | 이 PR |
| [experiments/README.md](../../experiments/README.md) | #809 |
| [experiments/fixtures/hospital-integrated-09/README.md](../../experiments/fixtures/hospital-integrated-09/README.md) | #809 |
| [experiments/fixtures/practice38/README.md](../../experiments/fixtures/practice38/README.md) | #809 |
| [experiments/protocols/README.md](../../experiments/protocols/README.md) | #809 |
| [schemas/README.md](../../schemas/README.md) | #809 |
| [sim/README.md](../../sim/README.md) | #808 |
| [sim/assets/amr_gripper/README.md](../../sim/assets/amr_gripper/README.md) | #808 |
| [sim/scenes/README.md](../../sim/scenes/README.md) | #808 |
| [sim/scenes/hospital-navigation-v1-changes.md](../../sim/scenes/hospital-navigation-v1-changes.md) | #808 |
| [sim/standalone/hospital-standalone.md](../../sim/standalone/hospital-standalone.md) | #808 |
| [sim/standalone/hospital-workcell.md](../../sim/standalone/hospital-workcell.md) | #808 |
| [sim/standalone/refill-trial-report.md](../../sim/standalone/refill-trial-report.md) | #808 |
| [sim/standalone/workcell-integration-review.md](../../sim/standalone/workcell-integration-review.md) | #808 |
| [sim/tests/README.md](../../sim/tests/README.md) | #808 |
| [src/README.md](../../src/README.md) | #813 |
| [src/rokey_p3_bringup/README.md](../../src/rokey_p3_bringup/README.md) | #813 |
| [src/rokey_p3_description/README.md](../../src/rokey_p3_description/README.md) | #813 |
| [src/rokey_p3_description/models/dispenser/README.md](../../src/rokey_p3_description/models/dispenser/README.md) | #813 |
| [src/rokey_p3_interfaces/README.md](../../src/rokey_p3_interfaces/README.md) | #813 |
| [src/rokey_p3_interfaces/contract_vectors/conveyor_arm/v1/README.md](../../src/rokey_p3_interfaces/contract_vectors/conveyor_arm/v1/README.md) | #813 |
| [src/rokey_p3_manipulation/README.md](../../src/rokey_p3_manipulation/README.md) | #813 |
| [src/rokey_p3_navigation/README.md](../../src/rokey_p3_navigation/README.md) | #813 |
| [src/rokey_p3_navigation/config/maps/README.md](../../src/rokey_p3_navigation/config/maps/README.md) | #813 |
| [src/rokey_p3_orchestrator/README.md](../../src/rokey_p3_orchestrator/README.md) | 이 PR, #813 |
| [src/rokey_p3_perception/README.md](../../src/rokey_p3_perception/README.md) | #813 |
| [tests/README.md](../../tests/README.md) | #809 |
| [tests/fixtures/runs/README.md](../../tests/fixtures/runs/README.md) | #809 |
| [tests/fixtures/runs/hospital-full-a01/README.md](../../tests/fixtures/runs/hospital-full-a01/README.md) | 보존·점검 |
| [tools/README.md](../../tools/README.md) | #809 |
| [web/README.md](../../web/README.md) | #809 |
| [web/api.md](../../web/api.md) | 이 PR, #809 |
| [web/backend/README.md](../../web/backend/README.md) | 이 PR, #809 |
| [web/frontend/README.md](../../web/frontend/README.md) | #809 |

</details>
