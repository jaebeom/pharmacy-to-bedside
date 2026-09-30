# 개발 프로세스 — Agile V-Model

## 왜 V-Model 인가

평가 기준 두 항목이 이 방식을 그대로 요구한다.

| 평가 기준 | V-Model 에서 |
| --- | --- |
| 「설계-구현 일치」 — 문서화된 설계가 코드에서 그대로 동작 | 좌측(설계)과 우측(검증)이 1:1 로 대응 |
| 「검증 및 분석」 — **사전 정의한** 정량 지표로 검증 | 합격 조건을 코드보다 먼저 쓴다 |

핵심은 한 문장이다. **구현 전에 합격 판정 조건을 먼저 정한다.**
결과를 보고 지표를 맞추면 "사전 정의" 가 아니고, 채점에서 그대로 걸린다.

2주짜리 일정이므로 V 전체를 정석대로 돌지 않는다. 가져오는 것은 두 가지다 —
**추적성**(요구사항 ↔ 검증이 PR 에서 연결됨)과 **Shift-Left**(실기기 전에 시뮬레이터에서 먼저 잡음).

## 대응 관계

| 좌측 (설계) | 우측 (검증) | 어디서 |
| --- | --- | --- |
| 요구사항 정의 | 인수 테스트 (acceptance) | frozen protocol `hospital-full-acceptance-v1`–`v4`, 회전 1–7 (9/25–9/28 KST) |
| 시스템 요구사항 | 시스템 테스트 (**L3**) | Isaac Sim — 마스터에서 창 모드 전 구간 한 바퀴([병원 런카드](../runbooks/hospital-full.md)) |
| 상위 설계 | 통합 테스트 (**L2**) | ROS 2 토픽·서비스·액션 — 패키지의 `test/` |
| 상세 설계 | 단위 테스트 (**L1**) | 순수 로직·좌표 변환 — 패키지의 `test/` |

## 테스트 계층

| 계층 | 대상 | 실행 | CI |
| --- | --- | --- | --- |
| **저장소 검사** | 링크, 파일 경계, 기록 형식, 옛 기록 변조 | `tools/`·`tests/` (일반 Python) | **모든 PR** 에서 돈다. 몇 초 |
| **Python 정적 검사** | 문법 오류, 미사용 이름, 흔한 잔버그, 줄 길이 | `ruff check .` ([설정](../../ruff.toml)) | **모든 PR** 에서 돈다. 몇 초 |
| **L1 단위** | 물리 엔진 없는 순수 로직 — 좌표 변환, 파라미터 검증, 상태 전이 | `colcon test` | Ready·main, 코드 변경 시. Draft 는 생략 |
| **L2 통합** | 노드 간 인터페이스 — 액션/서비스가 규격대로 응답하는지 | `colcon test` (`launch_testing`) | Ready·main, 코드 변경 시. Draft 는 생략 |
| **L3 시스템** | Isaac Sim 시나리오 — 실제로 집어서 옮기는지 | 마스터에서 `tools/demo_v2.sh up`([병원 런카드](../runbooks/hospital-full.md)). Isaac 씬 로드 smoke 는 `python.sh` ([`sim/tests/`](../../sim/tests/README.md)) | **안 돈다** |

ROS CI(colcon L1·L2)는 colcon이 읽지 않는 경로만 바뀐 PR과 Draft에서는 건너뛴다. 판정은 [`tools/ci_changed_paths.py`](../../tools/ci_changed_paths.py)다.
Ready로 바꾸면 `ready_for_review`로 colcon이 다시 돈다. 저장소 검사와 ruff는 문서·Draft에서도 돈다. `sim/tests/`는 `sim/`이 바뀐 때만 한 패스다. Ready·main은 usd-core를 포함한다.
실습 글·사진만 바뀐 변경은 ruff 단계와 `tests/` unittest를 생략하고 `check_repository.py`만 돌린다.
현재 `sim/tests/` 의 씬 로드 smoke 는 "USD 가 열린다"만 확인한다. 피킹·배송·물리 검증이 아니다.

### L3 를 CI 에서 돌리지 않는 이유

GPU 가 필요하고, 그 GPU 는 폐쇄망 안의 마스터 PC 에 있다.
self-hosted 러너를 붙이면 러너 등록과 헤드리스 디버깅에 며칠이 들고,
시연 중 CI 가 GPU 를 점유하면 그날 작업이 막힌다.

**L3 는 마스터에서 돌리고 결과를 PR 에 붙인다.** 커밋·run ID·성공률을 본문에 적는다.

## CI 가드 — 초록의 뜻

**skip 은 통과가 아니다.** 초록이 "무엇을 몇 개 돌렸다"를 뜻하도록 CI 가 수를 확인한다. 9/19–20 에 "초록인데 시험이 0개"가 세 번 나와서 생긴 규칙이다.

| 규칙 | 어디서 | 계기 |
| --- | --- | --- |
| 시험 파일(`test/test_*.py`)이 있는 패키지가 실행한 시험이 0 이면 colcon job 실패. 패키지마다 `tests·skip·xfail·executed` 한 줄을 찍는다 | [`tools/ci_test_counts.py`](../../tools/ci_test_counts.py), `ci.yml` 의 colcon test 다음 단계 | #258 첫 CI: navigation "collected 0 items / 1 skipped" 인데 초록 (#280) |
| 패키지별 skip 수와 xfail 수는 스크립트의 `ALLOWED` 표와 **정확히 같아야** 한다. 표에 없는 패키지는 둘 다 0. xfail 은 skip 과 따로 센다(junit 은 xfail 도 `skipped` 로 쓴다) | 같은 스크립트 | #289 |
| **skip·xfail 수를 바꾸는 PR 이 같은 PR 에서 `ALLOWED` 를 고친다.** 늘면 사유를 적고, 줄면(고쳤으면) 표를 내린다 | 같은 스크립트의 실패 메시지 | #289 |
| 모듈 수준 `pytest.importorskip` 을 쓰지 않는다. 필요하면 `pytestmark = pytest.mark.skipif(...)` 와 조건부 import 로 시험마다 건너뛴다 | 시험 코드 | 모듈 하나의 Skipped 가 파일·패키지 수집 전체를 skip 으로 만들었다(#258 navigation). 같은 패턴을 #267(bringup `test_stub_loop`)·#292(웹 ROS 통합 시험)에서 걷어냈다 |
| CI 이미지에 없는 선언된 의존성은 CI 가 설치한다. 없어서 시험이 skip·error 가 되게 두지 않는다 | `ci.yml` colcon job(nav2_msgs·opencv·cv_bridge, #260), `harness.yml` usd-core 단계(#265, usd-core 가 없으면 USD 시험이 skip 되던 것) | #260, #265 |
| 웹 백엔드 job: 수집 0 이면 실패, skip 이 1개라도 있으면 실패(제외는 `-m` 표현식으로만), 실서버(uvicorn) 시험이 한 개도 안 돌면 실패 | `web-backend.yml` 의 "Assert counts" 단계 | #292. TestClient 만으로는 `/ws` 404 를 못 잡았다 |
| usd-core 단계는 Ready·main 에서 `sim/` 이 바뀐 때만 돌고, `skipped 'usd-core not installed'` 가 로그에 있으면 실패 | `harness.yml` | #265. 문서 PR 과 Draft 에서는 설치하지 않는다 |

### 두 PR 이 같은 수를 건드릴 때

- CI 는 PR 을 올린 시점의 main 과 합친 결과로 돈다. 다른 PR 이 먼저 머지되면 그 초록은 **낡은 초록**이다.
- 예: #289(허용 표 orchestrator skip 6)와 #290(orchestrator 를 skip 1·xfail 1 로)이 둘 다 초록이었다. #290 이 먼저 들어가자 #289 의 표가 main 과 어긋났다. 그대로 머지했다면 머지 직후 main 이 가드에서 빨개졌다.
- 규칙: **둘째로 머지되는 PR 이 main 을 합치고 표를 맞춘 뒤 새 초록을 받는다.** 그 사이에는 Draft 로 둔다. Ready 로 바꾸기 직전에 main 의 최신 수치를 한 번 더 본다.

## 한 변경의 순서

1. 이슈에 범위·재현·**완료 조건**·담당을 쓴다. 인터페이스가 바뀌면 [계약](../architecture/README.md)도.
2. 실패를 구분할 테스트를 먼저 쓴다. 문구 수정에 의미 없는 테스트는 만들지 않는다.
3. 브랜치에서 구현하고 L1/L2 와 저장소 검사를 통과시킨다.
4. 동작에 영향이 있으면 마스터에 후보 커밋 배포를 요청하고 L3 를 측정한다.
5. PR 을 Draft 로 연다. 요구사항·테스트 결과·run·실패와 한계를 연결한다.
6. 작성자 외 검토를 받는다. 사람이거나 [봇 머지 조건](github-governance.md#봇-머지-조건)을 채운 봇이다.
   검토를 반영한 뒤 Ready 로 바꾼다([PR 흐름](github-governance.md#pr-흐름-draft-로-열고-ready-는-한-번)).
7. 머지된 커밋을 배포하고 [배포 기록](../runbooks/deployment.md)을 남긴다.

## pilot 과 acceptance

측정에는 두 단계가 있다 — [지표 정책](../policy/metrics.md).

- **pilot** (D4-D5): 측정 방법이 말이 되는지, 목표가 현실적인지 본다. 결과는 최종 평가에 안 들어간다.
- **acceptance** (D7, 9/23): D6 (9/22)에 고정(frozen)한 protocol로 반복 실행한다. 결과를 보고 기준을 낮추지 않는다. 추석 중 원격 반복은 선택이다. 같은 protocol일 때만 같은 집합이다.

pilot 결과로 기준을 바꿨으면 새 protocol 파일을 만든다. 옛 파일은 그대로 둔다.

실제로 돈 것(2026-09-30 기준)은 이렇다. 위 D6·D7 날짜는 계획이었다.

- pilot protocol 은 `pharmacy-lap-pilot-v1`(동결 9/20 KST)과 `hospital-refill-integration-pilot-v1`(동결 9/22 KST)이다.
- 처음 동결된 병원 acceptance protocol 은 `hospital-full-acceptance-v1` 이다. 동결은 2026-09-24T23:14:44Z 다.
- 그 뒤 v2·v3·v4 를 새 파일로 동결했다. 옛 파일은 그대로다([`experiments/protocols/`](../../experiments/protocols/README.md)).
- 판정선은 v1·v2 가 16/16 무실패였다. v3·v4 는 회전마다 15/16(90 %) 이상이다. 재범 결정이다(#240 5854486187).
- 회전 1–4 는 `v0.5.0` 에 묶였다. 회전 7(`9760d9d`, v4)은 14/14 로 `v1.0.0` 의 근거다([campaign 장부](../reha/campaigns.md)).
- `v1.1.0`(`f316197`) 커밋으로 돌린 acceptance 회전은 없다. `evidence/runs/` 에도 그 커밋의 run 이 없다.

## DevOps — 무엇이 들어왔고 다음은 무엇인가

이 절은 2026-09-16 기준 기록이다. 그 뒤 들어온 CI 가드는 위 [CI 가드](#ci-가드--초록의-뜻) 표에 있다.
브랜치 보호의 지금 상태는 [GitHub 적용 상태](github-governance.md#조회한-상태)에 있다.

자동화는 **인터페이스를 고정하는 행위**다. 토픽 이름과 액션 규격이 정해지기 전에 자동화를 만들면,
그것들이 바뀔 때 자동화도 같이 버려진다. 착수 순서는 **계약에 얼마나 묶여 있는지**로 정한다.
계약을 모르는 자동화부터 넣는다. 계약을 아는 자동화는 계약이 닫힌 뒤에 넣는다.

원래 세워 둔 착수 조건과 2026-09-16 기준 상태는 이렇다.

원래 조건의 첫 항목은 두 가지를 한 줄에 묶어 두었다. 빌드되는 것과 명세가 닫힌 것은 다르므로 나눠서 본다.

| 조건 | 상태 |
| --- | --- |
| `rokey_p3_interfaces` 가 빌드된다 | 충족. CI 의 `colcon build` 통과 |
| 프레임·인터페이스 **명세가 고정**된다 | **부분 충족.** [배송 계약 v1](../architecture/delivery-contract-v1.md) 이 이름을 한곳에 모았지만 상태가 `proposed` 이고, 문서 안에 v1.1 변경 목록이 남아 있다 |
| 시나리오가 확정 상태다 | 충족. [시나리오](../planning/scenario.md) 2026-09-16 팀 확정 |
| 팔 + AMR 1대 사이클이 실제로 한 바퀴 돈다 | **미충족.** D4(9/18) 기준 |

넷 중 둘이 아직 열려 있다. 그래서 **계약을 모르는 자동화만** 먼저 넣었다.

### 들어온 것

| 항목 | 무엇을 막는가 | 계약 결합 |
| --- | --- | --- |
| 저장소 검사 (`tools/check_repository.py`) | 깨진 링크, 원본 데이터 커밋, 취소선 오식 | 없음 |
| 기록 검사 (`tools/evidence.py`) | frozen protocol 변조, run 기록 덮어쓰기 | 없음 |
| **Python 정적 검사 (`ruff check .`)** | 4명이 병렬로 쓰는 동안의 스타일 드리프트와 잔버그 | 없음 |
| ROS 빌드·테스트 (`colcon build` / `test`) | 빌드 깨짐, L1·L2 회귀 | 패키지 이름까지만 |

`ruff` 는 버전을 `0.15.8` 로 고정한다. 새 규칙이 늘어나 어제 통과한 PR 이 오늘 빨개지지 않게 한다.
**포맷 강제(`ruff format`)는 넣지 않았다.** 지금 넣으면 29개 파일이 한꺼번에 바뀌어 열린 브랜치가 전부 충돌한다.
열린 브랜치가 없는 시점에 별도 PR 로 판단한다.

### 다음 후보

| 항목 | 착수 조건 | 비용 |
| --- | --- | --- |
| 브랜치 보호 — PR 필수, 승인 1명, 필수 검사 지정 | 지금 가능. **팀장이 GitHub UI 에서** ([절차](github-governance.md)). 9/18 에 ruleset 으로 PR 필수·필수 검사가 적용됐다. 필수 승인은 0 이다([조회한 상태](github-governance.md#조회한-상태)) | 15분 |
| L3 self-hosted runner (마스터 1) | 사이클 한 바퀴가 돈 뒤. 시연 중 GPU 점유 위험을 먼저 정리 | 반나절에서 하루 |
| L2 launch_testing 확대 | 계약의 액션·서비스가 실제로 구현된 뒤 | 패키지마다 반나절 |

필수 검사로는 `Repository and evidence checks`, `Python lint (ruff)`, `CI gate` **셋**을 건다. 모든 PR 에서 끝까지 돌기 때문이다.
`L1 · L2 (colcon build + test)` 자체는 걸지 않는다. colcon 이 보지 않는 경로(문서, `sim/`, `web/`, `tests/`)만 바뀐 PR 에서는
경로 필터로 생략되므로, 필수로 걸면 그런 PR 이 pending 에 머문다. `CI gate` 가 그 경우를 대신 통과시킨다(#89).

## 추적과 진단

GitHub 이슈에 요구사항, PR 에 구현과 검증, `evidence/` 에 관측, ADR 에 결정 이유를 둔다.
해결한 이슈는 `Closes #N` 으로 연결한다.

시뮬레이션과 실기기가 다르면 제어·환경·센서·설정·모델 오차를 경쟁 가설로 검토한다.
원인을 먼저 물성치로 단정하지 않는다. 차이를 재현한 뒤 수정한다.
마스터 현장 대응은 [에이전트 역할](agent-workflow.md)을 따른다.
