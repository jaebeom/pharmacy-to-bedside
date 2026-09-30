"""STAT S0 CLI L1: 실제 프로세스를 crash 로 끝내고 새 프로세스가 같은 파일을 다시 열어 복구한다.

같은 프로세스 안의 재열기(test_stat_dispatch)와 달리 메모리 캐시·열린 핸들·정리 코드가 전혀 넘어가지 않는다.
판정은 새 프로세스가 읽은 stub 세계의 applied 와 원장 상태다.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from rokey_p3_orchestrator.stat_cli import CRASH_EXIT

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
KINDS = ('DISPENSE', 'LOAD', 'FLY', 'RELEASE', 'RETURN')


def cli(folder, *args, expect=0):
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(PACKAGE_ROOT), os.environ.get('PYTHONPATH', '')]))
    done = subprocess.run([sys.executable, '-m', 'rokey_p3_orchestrator.stat_cli', '--dir', str(folder), *args],
                          capture_output=True, text=True, env=env, timeout=60, check=False)
    assert done.returncode == expect, done.stderr
    return json.loads(done.stdout)


@pytest.fixture
def folder(tmp_path):
    cli(tmp_path, 'init')
    demo = cli(tmp_path, 'demo')
    assert demo['first']['disposition'] == 'ACCEPTED'
    assert (demo['resend']['disposition'], demo['resend']['ticket']) == ('REPLAY', demo['first']['ticket'])
    return tmp_path


def test_normal_round_trip_from_the_command_line(folder):
    status = cli(folder, 'run')
    assert [(o['state'], o['mission']) for o in status['orders']] == [('DELIVERED', 'CLOSED')]
    assert status['world_applied'] == dict.fromkeys(KINDS, 1)
    assert cli(folder, 'init')['seeded'] is False                   # 다시 init 해도 재고를 덮지 않는다


@pytest.mark.parametrize('crash_at', ['after_intent:DISPENSE', 'after_send:DISPENSE', 'before_commit:DISPENSE',
                                      'after_send:RELEASE'])
def test_process_crash_then_restart_does_not_repeat_a_physical_step(folder, crash_at):
    cli(folder, 'run', '--crash-at', crash_at, expect=CRASH_EXIT)
    kind = crash_at.split(':')[1]
    between = cli(folder, 'status')
    assert between['orders'][0]['current_op'].endswith(kind)       # 미결 op 가 원장에 남았다
    status = cli(folder, 'run')
    assert status['generation'] == 2
    assert [o['state'] for o in status['orders']] == ['DELIVERED']
    assert status['world_applied'] == dict.fromkeys(KINDS, 1)
    assert [p['custody'] for p in status['pods']] == ['RECEIVER', 'SOURCE']
