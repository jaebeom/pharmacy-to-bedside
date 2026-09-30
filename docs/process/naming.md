# 이름과 위치

이름은 사람별 코드 복사본이 아니라 책임과 계약을 나타낸다.

| 대상 | 규칙 | 예 |
| --- | --- | --- |
| ROS 패키지·Python 모듈 | snake_case, 프로젝트 패키지 rokey_p3_ 접두사 | rokey_p3_interfaces |
| Markdown·디렉토리 | ASCII kebab-case; 내용은 한국어 가능 | plan-review.md |
| Python 파일·함수 | snake_case | collect_metrics.py |
| ROS 토픽·프레임 | 소문자 snake_case; robot namespace 명시 | carter_a/odom |
| 브랜치 | feat/fix/docs/test/refactor/chore/ci + topic; ROS 코드는 topic 앞에 패키지 이름; 코딩 도구 이름 접두 두 가지 허용 | feat/manipulation-belt-pick |
| ADR·RFC | NNNN-kebab-title.md; 디렉토리 내 증가 | 0001-intersection-lease-policy.md |
| review·analysis | YYYY-MM-DD-owner-topic.md; owner는 GitHub handle | 2026-09-15-jaebeom-reset.md |
| protocol | scenario-phase-vN.json | delivery-pilot-v1.json |
| run | UTC compact + host + 8자리 hex | 20260915T010203Z-master01-a1b2c3d4.json |
| 범위 표기 | **본문에 물결표를 쓰지 않는다.** 하이픈이나 '부터/까지'로 쓴다 | D1-D10, 수십에서 수백 Mbps |

메모 날짜는 작성자 현지 날짜, 측정·배포 시각은 ISO 8601 UTC Z.
host ID와 사람의 담당은 분리한다. 번호 충돌은 PR에서 조정한다.
README.md, CONTRIBUTING.md, CMakeLists.txt, COLCON_IGNORE 등 표준명은 예외다.
외부 자료의 원제·자산명은 출처 추적을 위해 유지한다.

latest, final2, new_new를 버전 식별자로 쓰지 않는다.
코드는 Git SHA, 환경과 자산은 SHA-256, 측정 조건은 protocol 버전으로 식별한다.
물리량은 단위를 함께 쓰고 yaw는 rad 기준으로 계약에 명시한다.
clock과 frame의 단일 작성자는 [계약 가이드](../architecture/README.md)에서 확정한다.

## 실제로 쓰인 이름 (관측, 2026-09-30)

규칙이 아니라 관측이다. 위 표를 바꾼 결정은 찾지 못했다.

- **브랜치.** 최근 머지된 PR 300건의 head 브랜치 접두사를 셌다(`gh pr list --state merged -L 300`).
  - `docs/` 98, `feat/` 78, `fix/` 54, `evidence/` 28, `exp/` 17, 코딩 도구 이름 접두 11(허용 목록 밖 6, 안 5), `perf/` 5, 그 밖 9 이다.
  - 표에 없는 `evidence/`·`exp/`·`perf/` 와 허용 목록 밖의 도구 이름 접두(6건)가 쓰였다.
  - `evidence/` 는 run·배포 기록 PR 이다(예: #779 `evidence/deploy-v1-0-0`).
  - `exp/` 는 실험 브랜치와 protocol 동결 PR 이다(예: #756 `exp/hospital-full-v3-freeze`).
  - 표의 `test/`·`refactor/`·`chore/`·`ci/` 는 이 300건에 없다.
  - ROS 코드 브랜치에 패키지 이름을 앞에 두지 않은 예가 있다. #788(navigation)은 `feat/governor-slow-70` 이다.
- **태그.** 규칙은 `v<major>.<minor>.<patch>` 다([릴리즈 규칙](../planning/schedule.md#릴리즈-규칙)).
  그 밖에 pre-release `v0.5.0-rc.1` 과 자산 태그 `assets/hospital-20260918` 이 있다(`gh release list`).
  지금 최신 릴리스는 `v1.1.3`이다. 병원 동작은 `v1.1.0`(`f316197`)과 같다. `v1.1.2` 에서 D455 몸체 재질을, `v1.1.3` 에서 제출 요약(README)과 `requirements.txt` 를 더했다.

## 본문에 물결표를 쓰지 않는 이유

GitHub은 물결표 **하나 또는 둘**을 취소선 표시로 읽는다. `~~지운 글~~`뿐 아니라 `~지운 글~`도 취소선이 된다.
그래서 `D1~D10` 처럼 범위를 쓰면, 같은 문단이나 같은 표 안의 **다음 물결표까지가 통째로 취소선**이 된다.
문단 하나에 범위가 둘 있으면 그 사이 글이 전부 지워진 것처럼 보인다.
쓴 사람은 로컬 편집기에서 멀쩡해 보이고 GitHub에서만 깨지므로 알아채기 어렵다.

```text
쓴 것:      `amr_1`~`amr_5`, 구역 `pharm`, `dock_1`~`dock_5`
보이는 것:  amr_1 ̶~̶ ̶a̶m̶r̶_̶5̶,̶ ̶구̶역̶ ̶p̶h̶a̶r̶m̶,̶ ̶d̶o̶c̶k̶_̶1̶~ dock_5
```

`python3 tools/check_repository.py`가 본문의 물결표를 전부 잡는다. CI에서도 돈다.
코드 스팬·코드 블록 안(`~/.ros/fastdds_whitelist.xml`)과 링크 주소는 검사에서 제외한다.
꼭 본문에 물결표를 써야 하면 `\~`로 이스케이프한다.
