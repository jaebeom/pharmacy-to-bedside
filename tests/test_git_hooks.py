"""tools/git-hooks/pre-push. 가짜 `gh` 를 PATH 에 두고 네 경우를 본다.

이 훅이 막는 것: 머지된 PR 의 브랜치에 커밋을 더 올리는 것. 그 커밋은 `main` 에 안 들어간다.
이 훅이 **막지 않아야** 하는 것: `main`, 브랜치 삭제, PR 이 없거나 열린 브랜치, `gh` 가 없는 기계.
"""

import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

BASH = shutil.which('bash') or '/bin/bash'

HOOK = Path(__file__).resolve().parents[1] / 'tools/git-hooks/pre-push'
ZERO = '0' * 40
SHA = 'a' * 40


def fake_gh(root, state):
    """`gh pr list ... --jq` 가 낼 한 줄을 그대로 찍는 가짜. state 가 빈 값이면 아무것도 안 찍는다."""
    path = Path(root) / 'gh'
    path.write_text('#!/bin/sh\nprintf %s "$GH_ROW"\n', encoding='utf-8')
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return {'PATH': f'{root}:/usr/bin:/bin', 'GH_ROW': state}


def run_hook(stdin, env):
    """bash 는 절대 경로로 부른다. PATH 에 gh 가 없는 경우까지 시험하기 위해서다."""
    return subprocess.run([BASH, str(HOOK)], input=stdin, capture_output=True, text=True,
                          env={**env, 'HOME': os.environ.get('HOME', '/tmp')}, timeout=30)


class PrePushHookTests(unittest.TestCase):
    def test_syntax(self):
        subprocess.run([BASH, '-n', str(HOOK)], check=True)

    def test_a_merged_branch_is_blocked(self):
        with tempfile.TemporaryDirectory() as root:
            env = fake_gh(root, '42 MERGED')
            result = run_hook(f'refs/heads/topic {SHA} refs/heads/topic {ZERO}\n', env)
        self.assertEqual(1, result.returncode)
        self.assertIn('#42', result.stderr)
        self.assertIn('git push --no-verify', result.stderr)

    def test_an_open_branch_passes(self):
        with tempfile.TemporaryDirectory() as root:
            env = fake_gh(root, '42 OPEN')
            result = run_hook(f'refs/heads/topic {SHA} refs/heads/topic {ZERO}\n', env)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_main_and_deletes_and_missing_prs_pass(self):
        cases = {
            'main': (f'refs/heads/main {SHA} refs/heads/main {ZERO}\n', '42 MERGED'),
            '삭제': (f'(delete) {ZERO} refs/heads/topic {SHA}\n', '42 MERGED'),
            'PR 없음': (f'refs/heads/topic {SHA} refs/heads/topic {ZERO}\n', ''),
            'null': (f'refs/heads/topic {SHA} refs/heads/topic {ZERO}\n', 'null null'),
        }
        for name, (stdin, row) in cases.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as root:
                result = run_hook(stdin, fake_gh(root, row))
                self.assertEqual(0, result.returncode, result.stderr)

    def test_a_machine_without_gh_is_not_blocked(self):
        with tempfile.TemporaryDirectory() as root:
            result = run_hook(f'refs/heads/topic {SHA} refs/heads/topic {ZERO}\n', {'PATH': root})
        self.assertEqual(0, result.returncode, result.stderr)

    def test_it_looks_at_the_pushed_ref_not_the_checked_out_branch(self):
        """`git push origin <다른-브랜치>` 도 잡는다. 표준 입력의 remote ref 로 본다."""
        with tempfile.TemporaryDirectory() as root:
            env = fake_gh(root, '7 MERGED')
            result = run_hook(f'refs/heads/local-name {SHA} refs/heads/remote-name {ZERO}\n', env)
        self.assertEqual(1, result.returncode)
        self.assertIn('remote-name', result.stderr)

    def test_every_pushed_ref_is_checked(self):
        with tempfile.TemporaryDirectory() as root:
            env = fake_gh(root, '9 MERGED')
            lines = (f'refs/heads/a {SHA} refs/heads/a {ZERO}\n'
                     f'refs/heads/b {SHA} refs/heads/b {ZERO}\n')
            result = run_hook(lines, env)
        self.assertEqual(1, result.returncode)
        self.assertIn("'a'", result.stderr)
        self.assertIn("'b'", result.stderr)


if __name__ == '__main__':
    unittest.main()
