# 기여 방법

1. main에서 목적이 하나인 브랜치를 만든다. [명명 규칙](docs/process/naming.md)을 따른다.
   Git 명령이 처음이면 [Git 시작 가이드](docs/process/git-start-guide.md)를 먼저 본다.
2. issue에 요구사항·재현·완료 조건·담당과 필요한 [계약](docs/architecture/README.md)을 정한다.
3. 분석·구현은 개발 환경에서 한다. 마스터는 [측정·배포 지원](docs/process/agent-workflow.md)에 집중한다.
4. 저장소 검사와 해당 L1/L2를 실행한다. 동작 변경은 예약된 master L3 run으로 검증한다.
5. PR은 **Draft로 연다.** 본문에 요구사항·변경·검사 결과·run·한계를 연결한다. 틀은 `.github/pull_request_template.md`다.
6. 검토 댓글을 반영한 뒤 **Ready로 한 번 바꾼다.** 작성자가 자기 PR을 Ready로 바꿔도 된다.
   Draft에서는 colcon을 건너뛴다. Ready에서 전체 CI가 한 번 돈다.
   이 흐름은 2026-09-23 재범 결정이다([PR 흐름](docs/process/github-governance.md#pr-흐름-draft-로-열고-ready-는-한-번)).
7. 병합은 merge commit이다. 작성자 외 검토가 있어야 한다.
   사람이 병합한다. 봇 병합은 [봇 머지 조건](docs/process/github-governance.md#봇-머지-조건)을 다 채운 PR 에만 한다.
   - 보호 경로(`.github/CODEOWNERS`)를 바꾸면 담당 사람의 승인이나 재범의 머지 댓글이 있어야 한다(봇 머지 조건 10).
   - 본문이나 최신 작성자 댓글에 "병합 보류", "Draft 유지" 같은 말이 있으면 넣지 않는다(봇 머지 조건 9).
   - GitHub에서 강제할 설정은 [별도 안내](docs/process/github-governance.md)에 있다. 설정이 적용됐다고 주장하지 않는다.

PR 전에 저장소 루트에서 돌린다.

```bash
python3 tools/check_repository.py
python3 tools/evidence.py validate --base origin/main
python3 -m unittest discover -s tests -v
ruff check .          # pipx install ruff==0.15.8
```

- ROS 변경은 `colcon build`·`colcon test`다.
- `sim/`을 바꿨으면 `python3 -m unittest discover -s sim/tests -p 'test_*.py'`도 돌린다(CI `harness.yml`과 같다).
- Isaac 변경은 마스터에서 L3로 확인한다([sim 안내](sim/README.md)).
- 환경 USD를 바꿨으면 [공통 규칙의 환경 USD 제출 전 확인](docs/process/repository-rules.md#환경-usd-제출-전-확인)을 따른다.

CI와 실제 장비 검증은 구분해 보고한다.
못 한 검증은 "미실행"이라고 쓴다.
[측정 정책](docs/policy/metrics.md)에 따라 pilot/acceptance와 실패·누락을 분리한다.
큰 원본은 [evidence](evidence/README.md)의 외부 저장소로 보낸다.

## 변경 범위와 기록
기존 코드·표준 라이브러리·현재 의존성을 먼저 사용한다.
새 추상화·서비스·SDK는 실제 필요와 제거 비용을 PR에 적는다.
단순 구현 선택은 PR, 비용이 큰 결정은 [ADR](docs/adr/README.md)에 이유를 남긴다.
기획·RFC의 미검토 주장을 승인 사실로 인용하지 않는다.
이미 기록된 run과 frozen protocol은 고치지 않는다. 정정은 새 파일과 `supersedes`로 한다.

기여의 1차 기록은 Git author와 PR 이력이다. 공동 작성은 실제 기여에 맞춰
Co-authored-by를 사용한다. 에이전트가 사람의 기여·검토·승인을 만들어 적지 않는다.
완료는 정상/주요 실패 경로, 관련 문서, 증거 범위와 미실행 검증을 함께 설명할 수 있는 상태다.
