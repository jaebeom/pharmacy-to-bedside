import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'tools/ci_changed_paths.py'
spec = importlib.util.spec_from_file_location('ci_changed_paths', SCRIPT)
paths = importlib.util.module_from_spec(spec)
spec.loader.exec_module(paths)

# ci.yml 에서 이 스크립트로 옮기기 전의 grep 식. 새 판정이 옛 판정과 다른 곳은 web/·tests/ 뿐이어야 한다.
OLD = (r'(^|/)[^/]*\.md$|^docs/|^inbox/|^sim/'
       r'|^\.github/ISSUE_TEMPLATE/|^\.github/pull_request_template\.md$|^\.github/CODEOWNERS$')


def old_needs_colcon(changed):
    import re
    return any(not re.search(OLD, path) for path in changed if path)


class CiChangedPathsTests(unittest.TestCase):
    def test_web_and_tests_only_skip_colcon(self):
        self.assertFalse(paths.needs_colcon(['web/frontend/js/main.js', 'web/frontend/css/app.css',
                                             'web/backend/app.py', 'web/backend/requirements.txt',
                                             'web/COLCON_IGNORE']))
        self.assertFalse(paths.needs_colcon(['tests/test_repository.py', 'tests/fixtures/runs/a/events.jsonl']))

    def test_docs_and_templates_still_skip(self):
        self.assertFalse(paths.needs_colcon(['docs/x.md', 'inbox/a.txt', 'sim/standalone/pharmacy_stage.py',
                                             'src/rokey_p3_bringup/README.md', '.github/CODEOWNERS',
                                             '.github/pull_request_template.md', '.github/ISSUE_TEMPLATE/bug.yml']))

    def test_paths_read_by_colcon_tests_still_run(self):
        # test_reset_barrier_loop 가 tools/aggregate_runs.py·experiments/protocols 를, 집계기가 schemas/ 를 읽는다.
        for changed in (['tools/aggregate_runs.py'], ['experiments/protocols/pharmacy-lap-pilot-v1.json'],
                        ['schemas/run.schema.json'], ['src/rokey_p3_bringup/setup.py'], ['.github/workflows/ci.yml'],
                        ['config/local/x.yaml'], ['evidence/runs/a.json'], ['setup.cfg']):
            self.assertTrue(paths.needs_colcon(changed), changed)

    def test_sim_files_read_by_bringup_tests_run_colcon(self):
        for path in ('sim/standalone/p3sim/belt.py', 'sim/standalone/p3sim/bridge.py',
                     'sim/standalone/p3sim/conveyor_end.py'):
            self.assertTrue(paths.needs_colcon([path]), path)
        self.assertFalse(paths.needs_colcon(['sim/standalone/p3sim/amr_base.py']))

    def test_root_configs_colcon_does_not_read_skip(self):
        """#543(9/23): ruff 제외 한 줄에 L1·L2 가 통째로 돌았다. lint 는 따로 돈다."""
        for path in ('ruff.toml', '.gitignore', '.gitattributes', '.editorconfig', 'LICENSE', 'LICENSE.md'):
            self.assertFalse(paths.needs_colcon([path]), path)
        self.assertTrue(paths.needs_colcon(['ruff.toml', 'src/rokey_p3_bringup/x.py']))

    def test_one_colcon_path_among_many_runs(self):
        self.assertTrue(paths.needs_colcon(['web/frontend/index.html', 'docs/a.md', 'src/rokey_p3_bringup/x.py']))

    def test_empty_change_list_skips_like_before(self):
        self.assertFalse(paths.needs_colcon([]))
        self.assertFalse(paths.needs_colcon(['', '  ']))
        self.assertEqual(old_needs_colcon([]), paths.needs_colcon([]))

    def test_same_as_the_old_grep_outside_web_and_tests(self):
        sample = ['README.md', 'docs/a/b.md', 'inbox/x.png', 'sim/tests/t.py', 'src/a/b.py', 'src/a/README.md',
                  'tools/check_repository.py', 'experiments/p.json', 'schemas/s.json', '.github/workflows/ci.yml',
                  '.github/CODEOWNERS', '.github/ISSUE_TEMPLATE/task.yml', '.github/pull_request_template.md',
                  'config/README.md', 'config/x.yaml', 'CONTRIBUTING.md', 'evidence/runs/r.json',
                  'docsx/a.py', 'simulator/a.py', 'webapp/a.js', 'testsuite/a.py']
        for path in sample:
            self.assertEqual(old_needs_colcon([path]), paths.needs_colcon([path]), path)
        for path in ('web/a.js', 'tests/a.py', 'ruff.toml'):
            self.assertTrue(old_needs_colcon([path]))
            self.assertFalse(paths.needs_colcon([path]))

    def test_command_line(self):
        run = subprocess.run([sys.executable, str(SCRIPT)], input='web/a.js\ntests/b.py\n', capture_output=True,
                             text=True, check=True)
        self.assertEqual('ros=false\nsim=false\nusd=false\nunit=true\nlint=true\n', run.stdout)
        run = subprocess.run([sys.executable, str(SCRIPT)], input='web/a.js\nsrc/b.py\n', capture_output=True,
                             text=True, check=True)
        self.assertEqual('ros=true\nsim=false\nusd=false\nunit=true\nlint=true\n', run.stdout)
        run = subprocess.run([sys.executable, str(SCRIPT)], input='sim/tests/t.py\n', capture_output=True,
                             text=True, check=True)
        self.assertEqual('ros=false\nsim=true\nusd=true\nunit=true\nlint=true\n', run.stdout)
        run = subprocess.run(
            [sys.executable, str(SCRIPT)],
            input='docs/practice/simworld/practice-37.md\ndocs/images/practice/a.png\n',
            capture_output=True, text=True, check=True)
        self.assertEqual('ros=false\nsim=false\nusd=false\nunit=false\nlint=false\n', run.stdout)

    def test_sim_and_usd_follow_sim_tree_not_src_or_docs(self):
        self.assertFalse(paths.needs_sim(['src/rokey_p3_bringup/x.py', 'docs/a.md', 'web/a.js']))
        self.assertFalse(paths.needs_usd(['src/a.py']))
        self.assertTrue(paths.needs_sim(['sim/standalone/pharmacy_stage.py']))
        self.assertTrue(paths.needs_usd(['.github/workflows/harness.yml']))
        self.assertEqual({'ros': False, 'sim': True, 'usd': True, 'unit': True, 'lint': True},
                         paths.classify(['sim/tests/t.py', 'docs/a.md']))
        self.assertEqual({'ros': True, 'sim': False, 'usd': False, 'unit': True, 'lint': True},
                         paths.classify(['src/a.py']))

    def test_practice_photo_skips_unit_and_lint(self):
        photo = [
            'docs/practice/simworld/practice-37.md',
            'docs/images/practice/practice-37-cylinder-inlet-trial-01.png',
        ]
        self.assertFalse(paths.needs_unit(photo))
        self.assertFalse(paths.needs_lint(photo))
        self.assertFalse(paths.needs_colcon(photo))
        self.assertFalse(paths.needs_sim(photo))


class ChooseBaseTests(unittest.TestCase):
    """GitHub 의 pull_request run 을 흉내 낸 임시 저장소. 9/17 #128 모양.

    A(옛 base.sha) ← M(그 뒤 main 이 src/ 를 바꿈), A ← P(PR 이 sim/ 만 바꿈), H = merge(M, P)(merge ref, 첫 부모 M).
    """

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.git('init', '-q', '-b', 'main')
        # 자동 gc·maintenance 가 뒤에서 objects 에 쓰면 cleanup rmtree 와 겹친다(#141).
        for key, value in (('gc.auto', '0'), ('gc.autoDetach', 'false'),
                           ('maintenance.auto', 'false'), ('maintenance.autoDetach', 'false'),
                           ('user.name', 'Harness Tests'), ('user.email', 'tests@example.invalid')):
            self.git('config', key, value)
        self.a = self.commit({'src/a.py': 'a\n', 'sim/s.py': 's\n'}, 'A')
        self.m = self.commit({'src/a.py': 'a2\n'}, 'M: main 이 src 를 바꿈')
        self.git('checkout', '-q', '-b', 'pr', self.a)
        self.p = self.commit({'sim/s.py': 's2\n'}, 'P: PR 은 sim 만')
        self.git('checkout', '-q', 'main')
        self.git('merge', '-q', '--no-ff', '-m', 'merge ref', 'pr')
        self.h = self.git('rev-parse', 'HEAD')

    def git(self, *args):
        return subprocess.run(['git', *args], cwd=self.root, capture_output=True, text=True,
                              check=True).stdout.strip()

    def commit(self, files, message):
        for name, text in files.items():
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            (self.root / name).write_text(text)
        self.git('add', '.')
        self.git('commit', '-qm', message)
        return self.git('rev-parse', 'HEAD')

    def changed(self, base):
        return self.git('diff', '--name-only', base, self.h).splitlines()

    def test_main_changes_after_the_old_base_do_not_leak_into_a_pull_request(self):
        base = paths.choose_base('pull_request', self.h, self.a, '', cwd=self.root)
        self.assertEqual(self.m, base)
        self.assertEqual(['sim/s.py'], self.changed(base))
        self.assertFalse(paths.needs_colcon(self.changed(base)))
        # 옛 기준(PR_BASE)이면 main 의 src/ 가 섞여 colcon 을 탄다. 고치기 전의 구멍.
        self.assertEqual(['sim/s.py', 'src/a.py'], sorted(self.changed(self.a)))
        self.assertTrue(paths.needs_colcon(self.changed(self.a)))

    def test_pull_request_head_that_is_not_a_merge_falls_back_to_pr_base(self):
        self.assertEqual(self.a, paths.choose_base('pull_request', self.p, self.a, '', cwd=self.root))
        self.assertEqual(self.a, paths.choose_base('pull_request', 'f' * 40, self.a, '', cwd=self.root))

    def test_push_uses_before_and_missing_base_is_empty(self):
        self.assertEqual(self.m, paths.choose_base('push', self.h, '', self.m, cwd=self.root))
        self.assertEqual('', paths.choose_base('push', self.h, '', '0' * 40, cwd=self.root))
        self.assertEqual('', paths.choose_base('push', self.h, '', '', cwd=self.root))
        self.assertEqual('', paths.choose_base('pull_request', self.p, '', '', cwd=self.root))

    def test_command_line_prints_the_base(self):
        run = subprocess.run([sys.executable, str(SCRIPT), '--base', 'pull_request', self.h, self.a, ''],
                             cwd=self.root, capture_output=True, text=True, check=True)
        self.assertEqual(self.m + '\n', run.stdout)
        run = subprocess.run([sys.executable, str(SCRIPT), '--base', 'push'], capture_output=True, text=True)
        self.assertEqual(2, run.returncode)


class WorkflowCostGatesTests(unittest.TestCase):
    """필수 job 이름은 유지하고, 같은 시험을 두 번 돌리거나 Draft 에 colcon 을 태우지 않는다."""

    ROOT = Path(__file__).resolve().parents[1]

    def test_required_check_names_unchanged(self):
        harness = (self.ROOT / '.github/workflows/harness.yml').read_text()
        ci = (self.ROOT / '.github/workflows/ci.yml').read_text()
        self.assertIn('name: Repository and evidence checks', harness)
        self.assertIn('name: Python lint (ruff)', harness)
        self.assertIn('name: CI gate', ci)

    def test_harness_gates_sim_and_usd_and_skips_usd_on_draft(self):
        harness = (self.ROOT / '.github/workflows/harness.yml').read_text()
        self.assertIn('ready_for_review', harness)
        self.assertIn("steps.filter.outputs.sim == 'true'", harness)
        self.assertIn("steps.filter.outputs.usd == 'true'", harness)
        self.assertIn('github.event.pull_request.draft != true', harness)
        self.assertIn("steps.filter.outputs.unit == 'true'", harness)
        self.assertIn("steps.filter.outputs.lint == 'true'", harness)
        self.assertEqual(2, harness.count('unittest discover -s sim/tests'))
