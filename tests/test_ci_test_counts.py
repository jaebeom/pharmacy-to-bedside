"""tools/ci_test_counts.py: a package with test files and no executed test fails the colcon job, and skip / xfail
counts must match the allowance table. Fake junit results only."""

import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'tools/ci_test_counts.py'
spec = importlib.util.spec_from_file_location('ci_test_counts', SCRIPT)
counts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(counts)

SUITE = '<testsuite name="pytest" tests="{t}" skipped="{s}" failures="0" errors="0"></testsuite>'


def cases_xml(passed=0, skip=0, xfail=0, failed=0):
    """pytest-style junit with one testcase per result (xfail is <skipped type="pytest.xfail">)."""
    body = ['<testcase name="p"/>'] * passed
    body += ['<testcase name="s"><skipped type="pytest.skip" message="x"/></testcase>'] * skip
    body += ['<testcase name="x"><skipped type="pytest.xfail" message="y"/></testcase>'] * xfail
    body += ['<testcase name="f"><failure message="z"/></testcase>'] * failed
    total = passed + skip + xfail + failed
    return (f'<testsuites><testsuite name="pytest" tests="{total}" skipped="{skip + xfail}" '
            f'failures="{failed}" errors="0">{"".join(body)}</testsuite></testsuites>')


def package(root, name, test_files=(), result=None, wrap=False, xml=None):
    src = root / 'src' / name
    (src / 'test').mkdir(parents=True)
    (src / 'package.xml').write_text('<package/>')
    for f in test_files:
        (src / 'test' / f).parent.mkdir(parents=True, exist_ok=True)
        (src / 'test' / f).write_text('')
    if result is not None or xml is not None:
        (root / 'build' / name).mkdir(parents=True)
        if xml is None:
            suite = SUITE.format(t=result[0], s=result[1])
            xml = f'<testsuites>{suite}</testsuites>' if wrap else suite
        (root / 'build' / name / 'pytest.xml').write_text(xml)


def run(root):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = counts.main(['--src', str(root / 'src'), '--build', str(root / 'build')])
    return code, out.getvalue()


class CiTestCountsTests(unittest.TestCase):
    def test_normal_packages_pass_and_print_one_line_each(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package(root, 'pkg_a', ['test_a.py'], (12, 0))
            package(root, 'pkg_b', ['sub/test_b.py'], (3, 0), wrap=True)
            package(root, 'pkg_msgs')
            code, out = run(root)
        self.assertEqual(0, code)
        self.assertIn('pkg_a: test_files=1 tests=12 skip=0 xfail=0 failures=0 errors=0 executed=12 ok', out)
        self.assertIn('pkg_b: test_files=1 tests=3 skip=0 xfail=0 failures=0 errors=0 executed=3 ok', out)
        self.assertIn('pkg_msgs: no python tests', out)

    def test_everything_skipped_fails(self):
        # 9/20 #258: "collected 0 items / 1 skipped" — module-level importorskip skipped the whole package
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package(root, 'nav', ['test_fleet.py'], (1, 1))
            package(root, 'ok', ['test_x.py'], (5, 0))
            code, out = run(root)
        self.assertEqual(1, code)
        self.assertIn('nav: test_files=1 tests=1 skip=1 xfail=0 failures=0 errors=0 executed=0 FAIL no test executed',
                      out)

    def test_zero_collected_or_missing_result_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package(root, 'empty', ['test_a.py'], (0, 0))
            package(root, 'lost', ['test_b.py'])
            code, out = run(root)
        self.assertEqual(1, code)
        self.assertIn('empty: test_files=1 tests=0 skip=0 xfail=0 failures=0 errors=0 executed=0 FAIL', out)
        self.assertIn('lost: test_files=1 FAIL no ', out)

    def test_no_packages_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'src').mkdir()
            self.assertEqual(1, run(Path(tmp))[0])

    def test_xfail_is_counted_apart_from_skip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'r.xml'
            path.write_text(cases_xml(passed=4, skip=2, xfail=1, failed=1))
            self.assertEqual((8, 2, 1, 1, 0), counts.junit_counts(path))  # the suite says skipped=3

    def test_skips_and_xfails_must_match_the_allowance(self):
        skip = counts.allowance('rokey_p3_orchestrator', 'skip')[0]
        xfail = counts.allowance('rokey_p3_orchestrator', 'xfail')[0]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package(root, 'rokey_p3_orchestrator', ['test_o.py'], xml=cases_xml(passed=10, skip=skip, xfail=xfail))
            package(root, 'rokey_p3_navigation', ['test_n.py'], xml=cases_xml(passed=10))
            self.assertEqual(0, run(root)[0])
        cases = (('rokey_p3_navigation', {'skip': 1}, 'skip 1 > allowed 0: change ALLOWED'),
                 ('rokey_p3_navigation', {'xfail': 1}, 'xfail 1 > allowed 0'),
                 ('rokey_p3_orchestrator', {'skip': skip + 1, 'xfail': xfail}, f'skip {skip + 1} > allowed {skip}'),
                 ('rokey_p3_orchestrator', {'skip': skip - 1, 'xfail': xfail},
                  f'skip {skip - 1} < allowed {skip}: lower'),
                 ('rokey_p3_orchestrator', {'skip': skip, 'xfail': xfail + 1}, f'xfail {xfail + 1} > allowed {xfail}'),
                 ('rokey_p3_orchestrator', {'skip': skip, 'xfail': xfail - 1}, f'xfail {xfail - 1} < allowed {xfail}'))
        for name, results, text in cases:
            with self.subTest(name=name, results=results), tempfile.TemporaryDirectory() as tmp:
                package(Path(tmp), name, ['test_x.py'], xml=cases_xml(passed=10, **results))
                code, out = run(Path(tmp))
                self.assertEqual(1, code)
                self.assertIn(text, out)

    def test_orchestrator_allowance_is_main_after_290(self):
        self.assertEqual((1, 1), (counts.allowance('rokey_p3_orchestrator', 'skip')[0],
                                  counts.allowance('rokey_p3_orchestrator', 'xfail')[0]))

    def test_every_allowance_has_a_reason(self):
        for name, kinds in counts.ALLOWED.items():
            for kind, (allowed, reason) in kinds.items():
                self.assertTrue(name.startswith('rokey_p3_') and kind in ('skip', 'xfail') and allowed > 0 and reason,
                                (name, kind))

    def test_ci_runs_it_after_colcon_test(self):
        ci = (Path(__file__).resolve().parents[1] / '.github/workflows/ci.yml').read_text()
        job = ci[ci.index('name: colcon test'):ci.index('  gate:')]
        self.assertLess(job.index('colcon test-result --verbose'), job.index('python3 tools/ci_test_counts.py'))

    def test_draft_skips_colcon_until_ready(self):
        ci = (Path(__file__).resolve().parents[1] / '.github/workflows/ci.yml').read_text()
        self.assertIn('ready_for_review', ci)
        self.assertIn('github.event.pull_request.draft != true', ci)
        self.assertIn('Draft 라 colcon 을 생략했다', ci)


if __name__ == '__main__':
    unittest.main()
