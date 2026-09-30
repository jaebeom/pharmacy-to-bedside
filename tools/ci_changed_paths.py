#!/usr/bin/env python3
"""CI 가 어떤 무거운 시험을 돌릴지 정한다. 바뀐 경로를 한 줄에 하나씩 stdin 으로 받아
`ros=`·`sim=`·`usd=`·`unit=`·`lint=` 를 true|false 로 낸다.

.github/workflows/ci.yml 의 changes job 과 harness.yml 이
`git diff --name-only BASE HEAD | python3 tools/ci_changed_paths.py` 로 부른다.

- ros: colcon L1·L2. 바뀐 파일이 전부 colcon 이 읽지 않는 경로면 false.
- sim: Isaac 없는 `sim/tests/` unittest. `sim/` 또는 harness 워크플로가 바뀌면 true.
- usd: 같은 시험에 usd-core 24.5 를 깔고 USD 4개를 포함. sim 과 같다. 워크플로가
  Draft 에서는 설치를 건너뛰고 일반 python3 한 번만 돌린다.
- unit: `tests/` 하네스 unittest. 문서·실습 사진만이면 false. 링크·물결표는
  `check_repository.py` 가 저장소를 직접 본다.
- lint: ruff. Python·도구·sim·web 이 없으면 false. job 이름은 유지하고 단계만 생략한다.

바뀐 파일이 없으면 전부 false. BASE 는 같은 스크립트
`python3 tools/ci_changed_paths.py --base EVENT HEAD PR_BASE PUSH_BEFORE` 로 고른다.
- pull_request: HEAD(GitHub 의 merge ref)가 merge 커밋이면 첫 부모(merge ref 를 만든 시점의 base 브랜치 끝)다.
  `github.event.pull_request.base.sha` 는 PR 을 열거나 push 한 시점의 값이라 그 뒤 main 이 움직이면 옛 커밋이다.
  그것과 merge ref 를 비교하면 그 사이 main 변경이 섞여 sim/ 만 바꾼 PR 도 colcon 을 탔다(9/17 #128).
  merge 커밋이 아니면(부모 1개) PR_BASE 로 돌아간다.
- push: `github.event.before`.
기준이 없으면(빈 값·0 40개) 아무것도 내지 않고, job 은 무거운 시험을 돈다.

colcon 이 읽지 않는 경로:
- 어디든 `*.md`, `docs/`, 그리고 없어진 `inbox/` 접두: 코드가 아니다.
- `.github/ISSUE_TEMPLATE/`, `.github/pull_request_template.md`, `.github/CODEOWNERS`: 이슈·PR 틀과 소유자 표.
- `sim/`: COLCON_IGNORE. `sim/tests/` 는 Evidence harness 가 ROS 없이 돈다.
- `web/`: 관제 웹. COLCON_IGNORE. colcon 패키지도 테스트도 이 아래를 읽지 않는다.
- `tests/`: 저장소 하네스 unittest. COLCON_IGNORE. Evidence harness 가 돈다.
- 루트 설정 `ruff.toml`·`.gitignore`·`.gitattributes`·`.editorconfig`·`LICENSE`: colcon 패키지가 읽지 않는다(9/23 확인).
  ruff 설정은 lint job 이 본다. 9/23 #543 에서 ruff 제외 한 줄에 L1·L2 가 통째로 돈 것을 재범이 지적했다.

일부러 colcon 을 태우는 경로(COLCON_IGNORE 여도):
- `tools/`: bringup L2(test_reset_barrier_loop)가 `tools/aggregate_runs.py` 를 읽는다.
- `experiments/`: 같은 테스트가 `experiments/protocols/pharmacy-lap-pilot-v1.json` 을 읽는다.
- `schemas/`: `aggregate_runs.py` 가 `tools/evidence.py` 로 run schema 를 읽는다.
- `sim/standalone/p3sim/` 의 bridge·belt 와 belt 가 import 하는 conveyor_end: bringup L2(test_isaac_adapter)가
  스테이지 상수를 코드끼리 맞대려고 읽는다. 9/23 #549 가 belt 에 상대 import 를 넣었는데
  colcon 을 건너뛰어 main 이 깨졌다.
- 그 밖(`src/`, `config/`, `evidence/`, `.github/workflows/`, 위에 없는 루트 파일)은 판단 없이 태운다.
"""

import re
import subprocess
import sys

NO_COMMIT = {'', '0' * 40}
OUTPUT_KEYS = ('ros', 'sim', 'usd', 'unit', 'lint')

NOT_COLCON = re.compile(
    r'(^|/)[^/]*\.md$'
    r'|^docs/|^inbox/|^sim/|^web/|^tests/'
    r'|^\.github/ISSUE_TEMPLATE/|^\.github/pull_request_template\.md$|^\.github/CODEOWNERS$'
    r'|^(ruff\.toml|\.gitignore|\.gitattributes|\.editorconfig|LICENSE(\.md)?)$')

# sim/tests/ 와 usd-core 단계는 sim 코드나 그 단계를 정의한 워크플로가 바뀔 때만 돈다.
SIM_OR_USD = re.compile(r'^sim/|^\.github/workflows/harness\.yml$')

# 실습 글·스크린샷만 바뀐 PR(#495 모양). 코드 시험이 검증하는 대상이 없다.
DOCS_ONLY = re.compile(
    r'(^|/)[^/]*\.(md|png|jpe?g|webp|gif)$'
    r'|^docs/|^inbox/'
    r'|^\.github/ISSUE_TEMPLATE/|^\.github/pull_request_template\.md$')

LINT_PATH = re.compile(
    r'\.(py|pyi)$|^ruff\.toml$'
    r'|^src/|^sim/|^web/|^tests/|^tools/')


# sim/ 아래지만 colcon 시험이 읽는 파일(위 docstring).
READ_BY_COLCON = re.compile(r'^sim/standalone/p3sim/(bridge|belt|conveyor_end)\.py$')


def needs_colcon(paths):
    """바뀐 경로 목록 중 colcon 이 읽을 수 있는 것이 하나라도 있으면 True."""
    return any(READ_BY_COLCON.search(path) or not NOT_COLCON.search(path)
               for path in (p.strip() for p in paths) if path)


def needs_sim(paths):
    """Isaac 없는 sim/tests unittest 를 돌릴지."""
    return any(SIM_OR_USD.search(path) for path in (p.strip() for p in paths) if path)


def needs_usd(paths):
    """usd-core 를 깔고 같은 시험을 다시 돌릴지. 지금은 sim 과 같다(한 패스로 묶기 위해)."""
    return needs_sim(paths)


def needs_unit(paths):
    """tests/ 하네스 unittest. 문서·사진만이면 False."""
    return any(not DOCS_ONLY.search(path) for path in (p.strip() for p in paths) if path)


def needs_lint(paths):
    """ruff 가 볼 Python·패키지 트리가 바뀌었는지."""
    return any(LINT_PATH.search(path) for path in (p.strip() for p in paths) if path)


def classify(paths):
    """워크플로 GITHUB_OUTPUT 에 넣을 판정."""
    cleaned = [p.strip() for p in paths]
    sim = needs_sim(cleaned)
    return {
        'ros': needs_colcon(cleaned),
        'sim': sim,
        'usd': sim,
        'unit': needs_unit(cleaned),
        'lint': needs_lint(cleaned),
    }


def format_outputs(flags):
    return ''.join(f'{key}={"true" if flags[key] else "false"}\n' for key in OUTPUT_KEYS)


def parents(commit, cwd=None):
    """commit 의 부모 sha 목록. 모르는 커밋이면 빈 목록."""
    result = subprocess.run(['git', 'rev-list', '--parents', '-n', '1', commit], cwd=cwd,
                            capture_output=True, text=True)
    return result.stdout.split()[1:] if result.returncode == 0 else []


def choose_base(event, head, pr_base, push_before, cwd=None):
    """diff 기준 커밋(모듈 docstring). 없으면 빈 문자열."""
    if event == 'pull_request':
        merge_parents = parents(head, cwd) if head not in NO_COMMIT else []
        base = merge_parents[0] if len(merge_parents) == 2 else pr_base
    else:
        base = push_before
    return '' if base in NO_COMMIT else base


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ['--base']:
        if len(argv) != 5:
            print('사용법: ci_changed_paths.py --base EVENT HEAD PR_BASE PUSH_BEFORE', file=sys.stderr)
            return 2
        print(choose_base(*argv[1:]))
        return 0
    sys.stdout.write(format_outputs(classify(sys.stdin.read().splitlines())))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
