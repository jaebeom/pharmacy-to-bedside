#!/usr/bin/env python3
"""colcon test 뒤 패키지별 실행된 시험 수를 한 줄씩 찍고, "시험 파일은 있는데 실행 0개"면 실패한다.

.github/workflows/ci.yml 의 build-and-test job 이 colcon test 다음에 `python3 tools/ci_test_counts.py` 로 부른다.
9/20 주행 #258 의 첫 CI 는 초록이었지만 navigation 은 "collected 0 items / 1 skipped" 였다. 모듈 수준
importorskip 하나가 패키지 수집 전체를 skip 으로 만들었고, colcon test-result 는 skip 을 실패로 보지 않는다.

판정(패키지 = src/<이름>/package.xml 이 있는 디렉터리):
- `test/` 아래(하위 포함) `test_*.py` 가 없으면 볼 것이 없다(`no python tests`).
- 있으면 `build/<이름>/pytest.xml`(colcon 의 pytest junit 결과)을 읽는다. 없거나, 실행된 시험
  (tests − skip)이 0 이면 실패다.
- skip 과 xfail 을 나눠 센다. pytest junit 은 xfail 도 `<skipped type="pytest.xfail">` 로 쓰므로 testsuite 의
  `skipped` 속성에는 둘이 섞인다. 그래서 testcase 마다 본다. xfail 은 실행된 시험이다(실패를 기대하고 돌았다).
- skip 수와 xfail 수는 아래 `ALLOWED` 표의 수와 **같아야** 한다. 표에 없는 패키지는 둘 다 0 이다.
  더 많으면 새로 생긴 것이고, 더 적으면 고친 PR 이 표를 내리지 않은 것이다(strict xfail 과 같은 뜻).
- **표와 다르면: skip·xfail 을 바꾼 그 PR 에서 `ALLOWED` 를 같이 바꾼다**(사유 칸 포함).
- "평소보다 급감"은 보지 않는다. 기준 수를 따로 관리해야 해서 범위 밖이다.
"""

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

XFAIL = 'pytest.xfail'

# 패키지 -> {'skip': (허용 수, 사유), 'xfail': (허용 수, 사유)}. 고치는 PR 이 같은 PR 에서 수를 내린다.
ALLOWED = {
    'rokey_p3_orchestrator': {  # 9/20 #290 CI: 242 passed, 1 skipped, 1 xfailed
        'skip': (1, 'K07: FSM 에서 만들 수 없는 입력'),
        'xfail': (1, 'N09: 안착 관측(계약 11.4) 없음, strict'),
    },
}


def allowance(name, kind):
    return ALLOWED.get(name, {}).get(kind, (0, ''))


def count_problem(name, kind, seen):
    """'' when the package has exactly the allowed number of `kind` ('skip' or 'xfail'), else why not."""
    allowed, reason = allowance(name, kind)
    if seen > allowed:
        return f'{kind} {seen} > allowed {allowed}: change ALLOWED in the PR that added it, with a reason'
    if seen < allowed:
        return f'{kind} {seen} < allowed {allowed}: lower ALLOWED in the PR that fixed it ({reason})'
    return ''


def junit_counts(path):
    """(tests, skip, xfail, failures, errors). Counted per testcase when the file has testcases, so an xfail is not
    a skip; from the testsuite attributes otherwise (then every skipped element counts as skip)."""
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == 'testsuite' else list(root.iter('testsuite'))
    cases = [case for suite in suites for case in suite.iter('testcase')]
    if not cases:
        total = {key: sum(int(suite.get(key, 0)) for suite in suites)
                 for key in ('tests', 'skipped', 'failures', 'errors')}
        return (total['tests'], total['skipped'], 0, total['failures'], total['errors'])
    skip = xfail = failures = errors = 0
    for case in cases:
        skipped = case.find('skipped')
        if skipped is not None:
            if skipped.get('type') == XFAIL:
                xfail += 1
            else:
                skip += 1
        failures += case.find('failure') is not None
        errors += case.find('error') is not None
    return (len(cases), skip, xfail, failures, errors)


def package_report(src, build):
    """[(name, test_files, counts or None, problems)] for every package under src."""
    rows = []
    for package_xml in sorted(Path(src).glob('*/package.xml')):
        package = package_xml.parent
        files = sorted((package / 'test').rglob('test_*.py')) if (package / 'test').is_dir() else []
        if not files:
            rows.append((package.name, 0, None, []))
            continue
        result = Path(build) / package.name / 'pytest.xml'
        if not result.is_file():
            rows.append((package.name, len(files), None, [f'no {result}']))
            continue
        counts = junit_counts(result)
        tests, skip, xfail = counts[:3]
        problems = ['no test executed'] if tests - skip <= 0 else []
        problems += [p for p in (count_problem(package.name, 'skip', skip),
                                 count_problem(package.name, 'xfail', xfail)) if p]
        rows.append((package.name, len(files), counts, problems))
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--src', default='src')
    parser.add_argument('--build', default='build')
    args = parser.parse_args(argv)
    rows = package_report(args.src, args.build)
    failed = []
    for name, files, counts, problems in rows:
        if not files:
            print(f'{name}: no python tests')
            continue
        status = f'FAIL {"; ".join(problems)}' if problems else 'ok'
        if counts is None:
            print(f'{name}: test_files={files} {status}')
        else:
            tests, skip, xfail, failures, errors = counts
            print(f'{name}: test_files={files} tests={tests} skip={skip} xfail={xfail} failures={failures} '
                  f'errors={errors} executed={tests - skip} {status}')
        if problems:
            failed.append(name)
    if not rows:
        print(f'no package.xml under {args.src}')
        return 1
    if failed:
        print(f'시험 수 가드에 걸린 패키지: {failed}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
