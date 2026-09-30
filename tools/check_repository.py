#!/usr/bin/env python3
"""Small repository boundary and local Markdown-link gate; no external requests."""
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
AREAS = {'.github', 'src', 'sim', 'config', 'docs', 'experiments',
         'evidence', 'schemas', 'tools', 'tests', 'web'}
ROOT_FILES = {'README.md', 'CONTRIBUTING.md',
              '.gitignore', '.gitattributes', '.editorconfig', 'LICENSE', 'LICENSE.md',
              'ruff.toml', 'requirements.txt'}
# colcon 이 들어가면 안 되는 영역. check() 는 이 영역 디렉토리가 있으면 COLCON_IGNORE 가 있는지만 본다
# (다른 검사를 건너뛰지 않는다). 아직 없는 영역(예: web/ 이 들어오기 전)은 요구하지 않는다.
IGNORED_AREAS = ('docs', 'sim', 'config', 'experiments', 'evidence', 'schemas', 'tools', 'tests', 'web')
RAW_SUFFIXES = {'.mcap', '.bag', '.db3', '.log', '.mp4', '.avi', '.mov', '.wav',
                '.pt', '.pth', '.onnx', '.npy', '.npz', '.zip', '.tar', '.gz'}
# NUL 검사에서 빼는 것. 이 목록 밖은 전부 텍스트로 본다(새 텍스트 확장자가 저절로 검사된다).
# 빠진 바이너리 형식이 들어오면 그 PR 이 막히므로 곧 들어올 것부터 미리 넣는다.
# `.pgm` 은 Nav2 occupancy map(P5) 이다. 점유 칸 픽셀 값이 0 이라 NUL 이 거의 반드시 있다
# (`src/rokey_p3_navigation/config/maps/README.md` 의 `hospital.pgm`).
BINARY_SUFFIXES = {'.webp', '.png', '.jpg', '.jpeg', '.gif', '.ico', '.bmp', '.svgz',
                   '.pdf', '.usd', '.usdc', '.usdz', '.woff', '.woff2', '.ttf', '.otf',
                   '.pgm', '.pcd', '.stl', '.ply', '.glb', '.gltf', '.dae',
                   '.bin', '.pkl', '.h5', '.so', '.pyc', '.mp3', '.ogg',
                   '.xlsx', '.pptx', '.docx'}
STANDARD_MD = {'README.md', 'CONTRIBUTING.md',
               'pull_request_template.md'}
LINK = re.compile(r'!?\[[^\]\n]*\]\((<[^>\n]+>|[^\s)]+)(?:\s+"[^"]*")?\)')
FENCE = re.compile(r'(?ms)^(\s*)(```|~~~)[^\n]*$.*?^\s*\2[^\n]*$')
INLINE_CODE = re.compile(r'(`+)(?:(?!\1)[\s\S])*?\1')
LINK_DESTINATION = re.compile(r'\]\([^)\n]*\)')
REFERENCE = re.compile(r'^\s*\[[^\]]+\]:\s*(<[^>]+>|\S+)', re.M)


def git_files(root):
    result = subprocess.run(['git', '-C', str(root), 'ls-files', '-z', '--cached',
                             '--others', '--exclude-standard'], capture_output=True, check=True)
    return sorted(set(result.stdout.decode().split('\0')) - {''})


def prose(text):
    # Do not interpret sample code as a document navigation link.
    text = re.sub(r'^\s*(```|~~~).*?^\s*\1[^\n]*$', '', text, flags=re.M | re.S)
    return re.sub(r'`[^`\n]*`', '', text)


def blank_out(match):
    # Keep line numbers stable while removing text that GitHub never parses as an inline delimiter.
    return re.sub(r'[^\n]', ' ', match.group(0))


def tilde_errors(relative, text):
    """GitHub renders one or two tildes as strikethrough, so a range like D1~D10 can
    silently strike out everything up to the next tilde in the same block."""
    masked = text.replace('\\~', '  ')
    for pattern in (FENCE, INLINE_CODE, LINK_DESTINATION):
        masked = pattern.sub(blank_out, masked)
    return [f'{relative}:{number}: tilde in prose renders as strikethrough on GitHub; '
            f'write the range with a hyphen (D1-D10), spell it out, or keep the tilde inside a code span'
            for number, line in enumerate(masked.split('\n'), 1) if '~' in line]


def local_link_errors(root, relative, text):
    errors = []
    content = prose(text)
    targets = [match.group(1) for pattern in (LINK, REFERENCE) for match in pattern.finditer(content)]
    for target in targets:
        target = target.strip('<>')
        try:
            parsed = urlsplit(target)
        except ValueError:
            errors.append(f'{relative}: malformed link {target}')
            continue
        if parsed.scheme or target.startswith(('#', '//')):
            continue
        path = unquote(parsed.path)
        if not path:
            continue
        resolved = (root / relative).parent.joinpath(path).resolve()
        if not resolved.is_relative_to(root.resolve()):
            errors.append(f'{relative}: link escapes repository: {target}')
        elif not resolved.exists():
            errors.append(f'{relative}: missing link target: {target}')
    return errors


def nul_errors(relative, data):
    """텍스트 파일에 NUL 이 하나라도 있으면 git 이 파일 전체를 binary 로 보고
    diff 가 사라진다. 셸 예시에서 ``\\0`` 을 쓰려다 진짜 NUL 을 넣는 경우가 그렇다."""
    position = data.find(b'\x00')
    if position < 0:
        return []
    line = data[:position].count(b'\n') + 1
    total = data.count(b'\x00')  # f-string 안에 백슬래시를 두지 않는다(3.10·3.11)
    return [f'{relative}:{line}: NUL byte in a text file ({total} total); '
            'git treats the whole file as binary and diffs stop working. '
            'write the escape (backslash zero) instead of a literal NUL']


def check(root):
    errors = []
    for area in IGNORED_AREAS:
        if (root / area).is_dir() and not (root / area / 'COLCON_IGNORE').is_file():
            errors.append(f'{area}/COLCON_IGNORE is required')
    for relative in git_files(root):
        path = root / relative
        if not path.exists() and not path.is_symlink():
            continue  # staged or unstaged removal is handled by the history gate where needed
        parts = Path(relative).parts
        if (len(parts) == 1 and relative not in ROOT_FILES) or (len(parts) > 1 and parts[0] not in AREAS):
            errors.append(f'{relative}: undeclared top-level responsibility')
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            errors.append(f'{relative}: symlinks are not permitted in the foundation tree')
            continue
        if path.stat().st_size > 10 * 1024 * 1024:
            errors.append(f'{relative}: exceeds 10 MiB; use external artifacts or review asset storage policy')
        if path.suffix.lower() in RAW_SUFFIXES:
            errors.append(f'{relative}: raw data/model/log/archive belongs outside Git')
        if path.name == 'package.xml' and parts[0] != 'src':
            errors.append(f'{relative}: ROS packages must live under src/')
        if path.suffix.lower() not in BINARY_SUFFIXES and path.suffix.lower() not in RAW_SUFFIXES:
            errors.extend(nul_errors(relative, path.read_bytes()))
        if path.suffix == '.md':
            if path.name not in STANDARD_MD and not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*\.md', path.name):
                errors.append(f'{relative}: use ASCII kebab-case Markdown names')
            markdown = path.read_text(encoding='utf-8')
            errors.extend(local_link_errors(root, relative, markdown))
            errors.extend(tilde_errors(relative, markdown))
    return errors


def main():
    try:
        errors = check(ROOT)
    except (OSError, UnicodeError, subprocess.CalledProcessError) as exc:
        print(f'Repository check failed: {exc}', file=sys.stderr)
        return 1
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        return 1
    print('PASS: repository boundaries, size policy, NUL bytes, Markdown file targets and tildes (anchors not checked)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
