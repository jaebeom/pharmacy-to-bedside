import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

CHECKER = Path(__file__).resolve().parents[1] / 'tools/check_repository.py'
spec = importlib.util.spec_from_file_location('repository', CHECKER)
repository = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repository)


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        for area in repository.IGNORED_AREAS:
            (self.root / area).mkdir()
            (self.root / area / 'COLCON_IGNORE').touch()

    def test_valid_local_link_and_code_example(self):
        (self.root / 'docs/README.md').write_text('hello')
        text = '[docs](docs/README.md)\n```text\n[example](absent.md)\n```\n'
        self.assertEqual([], repository.local_link_errors(self.root, 'README.md', text))

    def test_missing_and_escaping_links_fail(self):
        errors = repository.local_link_errors(self.root, 'README.md', '[x](missing.md) [x](../outside)')
        self.assertEqual(2, len(errors))

    def test_reference_link_checked(self):
        self.assertEqual(1, len(repository.local_link_errors(self.root, 'README.md', '[x]: missing.md')))

    def test_prose_tilde_fails_and_code_or_escape_passes(self):
        # A range written with a tilde silently strikes through everything up to the next tilde.
        self.assertEqual(1, len(repository.tilde_errors('docs/a.md', '기간은 D1~D10 이다.\n')))
        safe = '`D1~D10` 과 [경로](docs/~a.md) 와 \\~ 와\n```text\nrm ~/.ros/x\n```\n'
        self.assertEqual([], repository.tilde_errors('docs/a.md', safe))

    def test_tilde_error_reports_every_offending_line(self):
        errors = repository.tilde_errors('docs/a.md', 'D1~D10\nok\n1~2일\n')
        located = [':'.join(error.split(':', 2)[:2]) for error in errors]
        self.assertEqual(['docs/a.md:1', 'docs/a.md:3'], located)

    def test_nul_byte_in_a_text_file_fails_with_its_line(self):
        # 셸 예시에서 `\\0` 을 쓰려다 진짜 NUL 이 들어가면 git 이 파일 전체를 binary 로 본다.
        errors = repository.nul_errors('sim/README.md', b'first\nsecond\x00 tail\n')
        self.assertEqual(1, len(errors))
        self.assertTrue(errors[0].startswith('sim/README.md:2: NUL byte'), errors)
        self.assertIn('(1 total)', errors[0])
        self.assertIn('(2 total)', repository.nul_errors('a.md', b'\x00\x00')[0])
        self.assertEqual([], repository.nul_errors('sim/README.md', b"tr '\\0' '\\n' < x\n"))

    def test_nul_check_runs_on_the_tree_and_skips_images(self):
        (self.root / 'docs/notes.md').write_bytes(b'ok\n\x00\n')
        (self.root / 'docs/images').mkdir(parents=True, exist_ok=True)
        (self.root / 'docs/images/shot.webp').write_bytes(b'RIFF\x00\x00WEBP')
        errors = repository.check(self.root)
        self.assertTrue(any('docs/notes.md:2: NUL byte' in error for error in errors), errors)
        self.assertFalse(any('shot.webp' in error and 'NUL' in error for error in errors), errors)

    def test_nul_check_lets_an_occupancy_map_through(self):
        # Nav2 map_server 의 P5 PGM 은 점유 칸이 0 이라 NUL 이 거의 반드시 있다. 맵 PR 을 막으면 안 된다.
        maps = self.root / 'src/rokey_p3_navigation/config/maps'
        maps.mkdir(parents=True, exist_ok=True)
        (maps / 'hospital.pgm').write_bytes(b'P5\n2 3\n255\n' + bytes([0, 0, 254, 254, 205, 0]))
        (maps / 'hospital.yaml').write_text('image: hospital.pgm\nresolution: 0.05\n')
        errors = repository.check(self.root)
        self.assertFalse(any('hospital.pgm' in error for error in errors), errors)

    def test_raw_log_and_copied_package_fail(self):
        (self.root / 'docs/capture.mcap').write_bytes(b'fake')
        (self.root / 'docs/package.xml').write_text('<package/>')
        errors = repository.check(self.root)
        self.assertTrue(any('outside Git' in error for error in errors))
        self.assertTrue(any('under src/' in error for error in errors))

    def test_web_area_is_declared_and_still_checked(self):
        # web/(관제 웹)은 선언된 영역이고 COLCON_IGNORE 가 필요하다. Markdown 링크·물결표 검사는 그대로 돈다.
        (self.root / 'web/frontend').mkdir(parents=True)
        (self.root / 'web/frontend/index.html').write_text('<html></html>')
        (self.root / 'web/frontend/README.md').write_text('기간 D1~D10 [x](missing.md)\n')
        errors = repository.check(self.root)
        self.assertFalse(any('undeclared top-level responsibility' in error for error in errors), errors)
        self.assertTrue(any('web/frontend/README.md:1: tilde' in error for error in errors), errors)
        self.assertTrue(any('web/frontend/README.md: missing link target' in error for error in errors), errors)
        (self.root / 'web/COLCON_IGNORE').unlink()
        self.assertTrue(any('web/COLCON_IGNORE' in error for error in repository.check(self.root)))

    def test_absent_ignored_area_needs_no_colcon_ignore(self):
        # 아직 들어오지 않은 영역은 COLCON_IGNORE 를 요구하지 않는다(colcon 이 들어갈 디렉토리가 없다).
        (self.root / 'web/COLCON_IGNORE').unlink()
        (self.root / 'web').rmdir()
        self.assertFalse(any('COLCON_IGNORE' in error for error in repository.check(self.root)))

    def test_missing_colcon_boundary_fails(self):
        (self.root / 'docs/COLCON_IGNORE').unlink()
        self.assertTrue(any('docs/COLCON_IGNORE' in error for error in repository.check(self.root)))

    def test_nonstandard_markdown_name_fails(self):
        (self.root / 'docs/final_2.md').write_text('draft')
        self.assertTrue(any('kebab-case' in error for error in repository.check(self.root)))

    def test_symlink_fails(self):
        (self.root / 'docs/alias.md').symlink_to(self.root / 'docs/COLCON_IGNORE')
        self.assertTrue(any('symlink' in error for error in repository.check(self.root)))


if __name__ == '__main__':
    unittest.main()
