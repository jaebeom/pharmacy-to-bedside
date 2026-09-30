# 문서

`docs/` 의 목차다. 2026-09-30 의 파일 목록과 대조했다.
프로젝트 소개, 지금 상태(`v1.1.0`), 실행 입구는 [루트 README](../README.md)에 있다.

## 상태 표시

각 문서 옆에 넷 중 하나를 붙인다.
문서 머리의 `상태` 줄을 먼저 봤다. 없으면 기준일과 지금 쓰이는지로 골랐다.

| 표시 | 뜻 | 고치는 법 |
| --- | --- | --- |
| **현행** | 지금 코드·절차의 기준이다 | 바뀌면 그 문서를 고친다 |
| **현황** | 어느 날 코드를 읽어 적은 사실이다. 괄호 안이 기준일이다 | 코드가 바뀌면 다시 읽어 고친다. 코드와 다르면 코드가 맞다 |
| **기록** | 그날의 관측·경위·계획이다. 지금 기준이 아니다 | 본문을 고치지 않는다. 정정은 새 문서와 `supersedes` 로 한다 |
| **제안** | 결정 전이다. 검토 대상이다 | 사실로 인용하지 않는다. 결정은 이슈·PR·ADR 에만 있다([공통 규칙](process/repository-rules.md)) |

## 처음 읽는 순서

1. [루트 README](../README.md) — 무엇을 하는 시스템인가, 지금 무엇이 되는가, 어떻게 띄우는가
2. [우리 셋업](setup/README.md)과 [장비 목록](setup/host-inventory.md) — PC 구성, 네트워크, 내 주소
3. [시나리오](planning/scenario.md) — 무엇을 만드는가. 팀 확정 문서다(#21)
4. [시스템 그림](architecture/system-overview.md) — PC·역할·노드·토픽
5. [병원 전 구간 런카드](runbooks/hospital-full.md) — 병원 한 바퀴를 띄우고 판정하는 법
6. [Git 시작 가이드](process/git-start-guide.md), [개발 프로세스](process/development-process.md), [역할](process/agent-workflow.md) — 일하는 법

## 폴더별

### `setup/` — 장비·네트워크

| 문서 | 상태 | 무엇 |
| --- | --- | --- |
| [우리 셋업](setup/README.md) | 현행 | PC 구성과 세 네트워크가 왜 이렇게 생겼나 |
| [장비 목록과 IP](setup/host-inventory.md) | 현행 | 별칭·주소·사양의 기준 표. `master01` = `IsaacSim14`, `master02` = `IsaacSim07` |
| [ROS 2 유선 폐쇄망](setup/ros2-wired-network.md) | 현행 | 고정 IP, FastDDS 화이트리스트 |
| [Tailscale](setup/tailscale.md) | 현행 | 교육장 밖에서 마스터 접속 |

### `process/` — 일하는 방식

목차는 [process/README](process/README.md)에 있다.
[CONTRIBUTING.md](../CONTRIBUTING.md)와 [공통 규칙](process/repository-rules.md)이 상위 문서다.

| 문서 | 상태 | 무엇 |
| --- | --- | --- |
| [개발 프로세스](process/development-process.md) | 현행 | 합격 조건 먼저, L1·L2·L3, 이슈에서 배포까지 |
| [역할](process/agent-workflow.md) | 현행 | observer·developer·reviewer 역할과 소통 규칙 |
| [GitHub 적용 상태](process/github-governance.md) | 현행 | 봇 머지 조건, Draft 로 열고 Ready 는 한 번. 설정 조회 결과는 2026-09-15 기준 |
| [Git 시작 가이드](process/git-start-guide.md) | 현행 | 브랜치·커밋·PR 명령, 담당 자리 |
| [이름 규칙](process/naming.md) | 현행 | 패키지·브랜치·문서·protocol·run ID |
| [저장소 구조](process/repository-layout.md) | 현행 | 어떤 정보가 어느 디렉토리로 가나 |
| [워크스페이스 배치](process/workspace-layout.md) | 현행 | 어디에 clone 하고 어디서 빌드하나 |
| [기반 구조 조사](process/foundation-research.md) | 기록 | 저장소 구조를 고른 근거와 비교한 대안 |

### `architecture/` — 계약과 현황

목차는 [architecture/README](architecture/README.md)에 있다.

| 문서 | 상태 | 무엇 |
| --- | --- | --- |
| [배송 한 바퀴 계약 v1](architecture/delivery-contract-v1.md) | 현행(proposed 계약) | 노드 배치, 토픽·서비스·액션, 프레임, 인터락, 리셋, 판정 |
| [QR·약 DB·카메라 계약 v1](architecture/qr-db-camera-contract-v1.md) | 현행(proposed 계약) | 계약 v1 에 더한 QR·약 DB·카메라 이름 |
| [시스템 그림](architecture/system-overview.md) | 현행(v1.1.0, #804) | PC ↔ 역할 ↔ 노드 ↔ 토픽 |
| [ROS2 연동 표](architecture/ros2-integration-table.md) | 현황(9/25, `e9fa2e8`) | 발행자·구독자·QoS·계약 절 |
| [예외 → 종료 상태 표](architecture/exception-outcomes-v1.md) | 현황(9/25, `874b0a3`) | 조건마다 종료 상태와 근거 줄 |
| [스테이지 인자·기본값](architecture/stage-arguments.md) | 현행(v1.1.0, #804) | 병원 preset 인자와 근거 회차 |
| [QR 배치와 카메라 구성](architecture/qr-camera-layout.md) | 현황(9/23) | QR 위치·크기, D455 장착값 |
| [계약 v1 구현 현황](architecture/delivery-contract-v1-status.md) | 현황(9/20, `d3a1fda`) | 조항별 구현 PR |
| [관제 웹 서비스](architecture/web-console.md) | 제안 | 웹 구성. API 정본은 [`web/api.md`](../web/api.md) |
| [K5 인증·전달 인터페이스](architecture/k5-delivery-interface.md) | 제안 | 팔이 필요로 하는 인터페이스 |
| [STAT S0 계약](architecture/stat-delivery-contract-v1.md) | 제안 | 응급 항공 배송 S0 stub |

### `adr/` — 결정 이력

목차와 결정 상태는 [adr/README](adr/README.md)에 있다.
0001–0006 이 있다. 2026-09-30 파일 기준으로 모두 `proposed` 다.
`0007-hospital-camera-qr-dock-at-load.md` 는 #804 로 들어온다. 상태는 `proposed` 다.
0007 은 병원 카메라 QR 집기·인증을 다룬다. 도크 = 적재 자리도 다룬다. M0609 레일 후보 `preferred_first` 도 다룬다.
결정 내용은 소급해 고치지 않는다. 바뀌면 새 ADR 로 대체한다.

### `policy/` — 측정과 판정

| 문서 | 상태 | 무엇 |
| --- | --- | --- |
| [측정과 합격 판정](policy/metrics.md) | 현행 | 측정·해석·합격 기준을 나누는 정책. 실험마다의 값은 [protocol](../experiments/README.md)에 있다 |

### `runbooks/` — 마스터에서 도는 절차

| 문서 | 상태 | 무엇 |
| --- | --- | --- |
| [병원 전 구간 런카드](runbooks/hospital-full.md) | 현행 | 새 PC 준비, 조제실 입력, 한 바퀴, 판정 다섯 장면, 촬영, 카메라 배송 설정 |
| [병원 월드 데모](runbooks/hospital-demo.md) | 현행 | 환경 변수 표, 웹 요청 순서, 관찰, 종료, 두 마스터로 나눠 띄우기. 문서 머리 표시는 "초안"이다. 환경 변수 표는 9/29(#797)에 고쳐졌다 |
| [마스터 배포·진단·롤백](runbooks/deployment.md) | 현행 | 후보 SHA 를 따로 받고 띄우고 내리는 법 |
| [병원 주행 L3](runbooks/hospital-nav-l3.md) | 기록 | 병원 Nav2 구성과 지도. 런카드 5절이 같이 보라고 가리킨다 |
| [L3 런카드 — 벨트·UR5·병원 씬](runbooks/l3-sim-conveyor.md) | 기록 | RC-1–RC-6. 런카드가 RC-6 을 가리킨다 |
| [L3 런카드 — UR5 팔·인식](runbooks/l3-arm-perception.md) | 기록 | VA-1–VA-7 |
| [L3 스택 기동 조합](runbooks/l3-stack-combos.md) | 기록(`e271081`) | 스테이지·스택·팔 opt-in 짝 |
| [실습38 인계](runbooks/practice38-handoff.md) | 기록 | 1350개 진열 장면 복원 |
| [빈월드 한 바퀴 기동 조합](runbooks/emptyworld-lap-stack.md) | 기록(`fab74be`) | 빈월드 전 구간 |
| [빈월드 주행 대기](runbooks/emptyworld-lap-navigation-waits.md) | 기록 | 빈월드 주행 구간이 기다리는 것 |
| [9/21 1차 시연](runbooks/demo-0921-v2.md) | 기록 | 조제실 장면 v2 시연 |
| [화면 버튼 리허설](runbooks/demo-rehearsal-buttons.md) | 기록 | 9/21 시연 대본을 화면 버튼으로 |
| [조제실 한 바퀴 증거 실행](runbooks/evidence-run-pharmacy-lap.md) | 기록 | `pharmacy-lap-pilot-v1` |
| [master02 M0609 보충 장면](runbooks/master02-m0609-refill-stage.md) | 기록 | 9/17 고정 받침 보충 |
| [master02 스텁 없는 조제실](runbooks/master02-pharmacy-stack.md) | 기록 | 조제실 구간 단독 |
| [STAT S0 stub 재현](runbooks/stat-s0-stub.md) | 제안 계약의 L1 | ROS·Isaac 없이 STAT S0 |

### `planning/` — 기획과 계획

이 폴더는 검토 대상이다([공통 규칙](process/repository-rules.md)).
[시나리오](planning/scenario.md)만 팀 확정 문서다(#21). 나머지는 제안이거나 그날의 계획이다.

| 문서 | 상태 | 무엇 |
| --- | --- | --- |
| [시나리오](planning/scenario.md) | 현행(팀 확정) | 무엇을 만드는가. 물품 단위, 배송 유형, 종료 상태 |
| [일정](planning/schedule.md) | 기록 | 9/15–9/30 날짜별 목표와 담당 표 |
| [첫날 확인 항목](planning/first-day-checks.md) | 기록 | 9/15 스파이크 |
| [기획서](planning/p3-project-plan.md) | 제안 | 원 기획안. 시나리오와 충돌하면 시나리오가 우선 |
| [기획 검토](planning/plan-review.md) | 제안 | 9/15 범위·측정 검토 |
| [조제실 장면 변경 계획](planning/pharmacy-scene-v2-plan.md) | 기록 | 9/18 장면 v2 |
| [M0609 레일·팔 최적화 계획](planning/m0609-rail-arm-optimization-plan.md) | 제안 | 9/20 |
| [M0609 레일 자세 고르기 경위](planning/m0609-rail-select-0921-report.md) | 기록 | 9/20 밤 `v2_rail_select` |
| [빈월드 한 바퀴 가진 것](planning/empty-world-lap-inventory.md) | 기록 | 9/21 |
| [빈월드 멈춤 감사 ⑤–⑧](planning/emptyworld-lap-audit-pharmacy-to-delivery.md) | 기록 | 9/21 정적 감사 |
| [빈월드 멈춤 감사 후속](planning/emptyworld-lap-audit-followup.md) | 기록 | 9/21 정적 감사 |
| [빈월드·병원 씬 통합 상세](planning/mock-hospital-world-integration-plan.md) | 제안 | 9/19 |
| [기능 통합·리소스 최적화 2단계](planning/integration-resource-two-phase-plan.md) | 제안 | 9/19 |
| [컨베이어 CPS 계획](planning/conveyor-cps-integration-plan.md) | 제안 | 9/19 |
| [UR5 약포지 피킹·병원 배송](planning/ur5-hospital-delivery-implementation-plan.md) | 제안 | 9/19 |
| [비전 데이터·이상 탐지](planning/vision-data-and-anomaly-plan.md) | 제안 | 9/18 |
| [마스터 2대 운영 A/B](planning/two-master-final-stage-plan.md) | 제안 | 9/18 |
| [P3-STAT 응급 항공 배송](planning/p3-stat-implementation-plan.md) | 제안 | 9/20 Future Work |

### `reha/` — 병원 회차 기록

[reha/README](reha/README.md)가 목차다. 상태는 **기록**이다. evidence 가 아니다.
병원 한 바퀴가 돈 뒤(9/23)부터의 회차다(#576).
리하01–08 은 골든 회차다. 리하09·10 은 acceptance 회전 1–7 이다.
회전 장부는 [campaigns](reha/campaigns.md)에 있다.

### `practice/` — 실습 기록

[practice/README](practice/README.md)가 목차다. 상태는 **기록**이다. evidence 가 아니다.
환경별 목차는 [빈월드](practice/emptyworld/README.md)와 [심월드](practice/simworld/README.md)다.
9/23 이후 병원 회차는 실습이 아니라 리하로 센다. 예외로 [실습45](practice/simworld/practice-45.md)(9/29 카메라 배송)가 있다.

### `analysis/` — 해석

[analysis/README](analysis/README.md)가 목차다.
날짜가 붙은 문서는 **기록**이다. 날짜 없는 문서(`node-topology-v1.md` 등)도 기준일이 본문에 있다.

### `presentation/` — 최종 발표

[presentation/README](presentation/README.md)가 목차다.
9/30 최종 발표(영상) 자료다. 발표 담당 영역이다. 결정·합격선·실행 기록이 아니다.

### `reference/` — 받은 자료

[reference/README](reference/README.md)가 목차다.
강사가 배포한 평가 기준이 [tutor/](reference/tutor/README.md)에 있다. 최종 발표는 [110점 평가 기준](reference/tutor/final-presentation-evaluation.md)을 따른다.

### `rfc/` — 제안

[rfc/README](rfc/README.md)가 목차다. 상태는 **제안**이다.

### `templates/` — 작성 틀

모두 **현행**이다.

| 틀 | 쓰는 곳 |
| --- | --- |
| [계약](templates/contract.md) | `architecture/` |
| [진단](templates/diagnostic.md) | 문제 진단 packet |
| [증거 검토](templates/evidence-review.md) | `evidence/reviews/` |
| [배포 기록](templates/deployment.md) | `evidence/deployments/` |

### `images/` — 문서 그림

문서에 넣는 그림이다. `images/practice/` 는 실습 캡처다.
그 밖에 `dispenser/`, `presentation/`, `ur5-delivery/`, `web/` 이 있다.

## 용어

문서에 자주 나오는 말이다.

| 용어 | 뜻 |
| --- | --- |
| **D1-D8** | 작업일 번호. D1 = 9/15, D5 = 9/21 1차 시연, D8 = 9/29 최종 시연. 9/30 최종 발표. [일정](planning/schedule.md) |
| **릴리스 태그** | 태그는 `main` 에서 찍는다. 마스터 배포는 태그로만 한다. 지금 최신은 `v1.1.0` 이다. [릴리즈 규칙](planning/schedule.md#릴리즈-규칙) |
| **L1 / L2 / L3** | 시험 계층. L1 순수 로직, L2 ROS 인터페이스(둘 다 `colcon test`), L3 Isaac Sim 시나리오(마스터) |
| **harness** | GPU 없이 저장소 규칙만 보는 검사. `python3 tools/check_repository.py` 등. 모든 PR 에서 돈다 |
| **Draft / Ready** | PR 은 Draft 로 연다. Draft 에서는 colcon 을 건너뛴다. 검토를 반영한 뒤 Ready 로 한 번 바꾼다. [GitHub 적용 상태](process/github-governance.md) |
| **pilot** | 측정 방법이 말이 되는지 보는 탐색 실행. 최종 평가에 안 들어간다 |
| **acceptance** | 결과 전에 고정한 protocol 로 하는 평가 실행. 병원 acceptance 는 protocol v1–v4 로 회전 1–7 을 돌았다(9/25–9/28, [리하09](reha/reha-09.md)·[리하10](reha/reha-10.md)) |
| **회전 / attempt** | acceptance protocol 을 한 번 도는 묶음이 회전이다. 회전 하나는 attempt 16개다([리하09](reha/reha-09.md)) |
| **failure_class** | 실패 run 의 원인 분류. `robot`·`infra`·`operator` 중 하나다(protocol v4) |
| **protocol** | 실험 설계 파일(`experiments/protocols/*.json`). 무엇을 몇 번 재고 합격선이 무엇인지 |
| **frozen** | protocol 을 더 안 바꾸기로 하고 머지한 상태. 바꾸려면 새 파일 |
| **run** | 실행 한 번의 기록(`evidence/runs/*.json`). 어떤 커밋·씬·설정으로 무슨 결과가 났는지 |
| **artifact / raw** | 로그·rosbag·영상 원본. Git 에 안 넣는다. 외부 저장소에 두고 해시로 잇는다 |
| **supersedes** | 잘못 적힌 기록을 지우지 않고 새 파일에서 "이것을 대체함"이라고 가리키는 것 |
| **리하** | 리얼 하스피탈. 병원 한 바퀴가 돈 뒤의 회차 이름이다(#576). [reha](reha/README.md) |
| **골든** | 판정선을 넘는 것으로 팀이 합의한 구성 한 점(SHA)이다. 마지막은 골든-4 `aca8840`(9/24)이다. 리하09 부터는 acceptance 회전이 단위다([런카드](runbooks/hospital-full.md) 3.2절, [리하09](reha/reha-09.md)) |
| **참값 센서** | 시뮬이 아는 정답 좌표로 집고 인증하는 구성(`P3_SIM_SENSORS=1`, `P3_CAMERA_POUCHES=0`). protocol v4 회차가 이 구성이다 |
| **카메라 집기** | 손 카메라로 봉투 QR 을 읽어 주문과 맞을 때만 집는 구성. `v1.1.0` 병원 기본이다 |
| **합본 AMR** | Ridgeback 차체와 UR5 팔을 한 USD(`ridgeback_ur5.usd`)로 묶은 이동 로봇 |
| **rtf** | Real-Time Factor. 시뮬 시간 ÷ 실제 시간. 1.0 이면 실시간. 장비끼리 비교하지 않는다 |
| **master01 / dev01** | 장비 별칭. 기록에서 사람 이름 대신 쓴다. [장비 목록](setup/host-inventory.md) |
| **observer** | 마스터 PC 의 역할. 배포·실행·수치 수집만 한다. 코드를 고치지 않는다([공통 규칙](process/repository-rules.md)) |
| **ADR / RFC** | ADR = 되돌리기 어려운 결정의 기록. RFC = 아직 결정 안 된 제안 |

문서를 추가하면 이 목차의 해당 폴더 표에 같이 추가한다.
