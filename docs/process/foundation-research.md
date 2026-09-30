# 기반 구조 조사와 선택

확인일: 2026-09-15. 1차 기술 자료를 읽고 P3의 작은 팀·짧은 일정에 적용한 설계 제안이다.
문헌 확인과 현장 실측은 구분한다. 기획·Isaac/ROS 제약의 상세 근거는
[기획 검토](../planning/plan-review.md), 네트워크 근거는 [셋업](../setup/README.md)에 있다.

| 검토 축 | 자료가 지지하는 내용 | P3 적용 판단 |
| --- | --- | --- |
| 문서 정보 구조 | Diátaxis는 학습·작업 절차·참조·설명을 구분 | 기존 setup/process는 살리고 architecture/runbooks를 구분; 목적 없는 4분류 폴더 복제는 피함 |
| 결정 기록 | Nygard는 맥락·결정·결과와 변경 이력을 작은 문서로 보존 | ADR은 비싼 결정만, RFC의 미확정 주장과 분리 |
| 데이터 출처 | W3C PROV는 entity·activity·agent와 유래 관계를 표현 | artifact·run·작성자·protocol·SHA를 연결; RDF 서버 없이 JSON으로 시작 |
| 세션 규칙 | 메모리는 공통 파일 하나, 권한은 별도 접근 제어 | 공통 규칙 파일 하나. 마스터 권한은 OS 계정과 배포 경계로 보완 |
| PR 검증 | GitHub는 required checks·review·code owner 설정을 제공 | docs-only에도 가벼운 harness, L3는 예약된 master; settings 적용은 별도 확인 |

출처:
[Diátaxis](https://diataxis.fr/),
[Diátaxis 실무 적용](https://diataxis.fr/how-to-use-diataxis/),
[Nygard ADR](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions),
[W3C PROV Overview](https://www.w3.org/TR/prov-overview/),
[GitHub 보호 규칙](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches).

## 비교한 구조
| 대안 | 이점 | 비용·오염 위험 | 선택 |
| --- | --- | --- | --- |
| docs에 로그·결론을 함께 저장 | 시작이 쉬움 | 출처·버전·신뢰 상태가 섞임, binary 누적 | 사용하지 않음 |
| Git에 작은 manifest + 외부 raw + PR review | 코드·조건·출처 추적, 운영 부담 작음 | 외부 보존/접근·사람 리뷰 필요 | 초기 제안 |
| 별도 실험 추적 서비스·데이터 버전 플랫폼 | 검색·집계·다수 실험 관리 확장 | 지금은 계정·저장소·서비스 운영 범위 추가 | 수작업 비용이 측정되면 ADR로 재검토 |

특정 도구가 불필요하다는 결론이 아니다. 우선 JSON 계약과 content-addressed artifact로
이동 가능한 출처를 남긴다. 수집/집계량이 늘어 도구를 도입해도 같은 run ID·원본 hash를 유지한다.

## 지금 고정할 것과 나중에 정할 것
목표는 잘못된 판단이 코드와 운영으로 퍼지기 전에 발견하고 되돌리는 구조다.
지금은 정보의 상태·담당·경계, 기록의 불변성, 실패 포함, 검증/승인 경로를 정한다.
토픽 세부·마스터 배치·합격 수치는 스파이크와 pilot 근거로 버전 관리한다.
초기 문서가 완벽하다고 가정하지 않는다.

실제 적용 완료는 CI 통과와 다른 상태다. 현장 계정·artifact 보존·브랜치 보호·L3 확인은
[GitHub 적용](github-governance.md)과 [배포 runbook](../runbooks/deployment.md)에서 확인한다.
