"""tools/demo_v2.sh 의 인자 처리와 up 이 칠 명령(cmds). tmux·ROS·Isaac 없이 bash 만으로 본다.

기동·내림 흐름(tmux 세션, 남의 Isaac 멈춤, /clock 멈춤)은 GPU 없는 docker 시험으로 봤다(PR 본문).
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'tools/demo_v2.sh'
REQUIRED = {'P3_DOMAIN': '41', 'P3_M0609': '/assets/M0609', 'P3_DISPENSER_FILE': '/cfg/dispenser_refill.yaml'}


def run(*args, env=None, repo=None):
    full = {k: v for k, v in os.environ.items() if not k.startswith('P3_')}
    full.update(env or {})
    if repo is not None:
        full['P3_REPO'] = str(repo)
    return subprocess.run(['bash', str(SCRIPT), *args], capture_output=True, text=True, env=full, timeout=30)


class DemoV2Tests(unittest.TestCase):
    def test_syntax(self):
        subprocess.run(['bash', '-n', str(SCRIPT)], check=True)

    def test_down_without_a_world_still_looks_for_the_nav_session(self):
        """마클1 회차73(#240 5818833284): P3_WORLD 없이 down 하면 DOWN_ORDER 에 nav 가 빠져 p3v2-nav 가 남았다."""
        with tempfile.TemporaryDirectory() as tmp:
            calls = Path(tmp) / 'tmux.log'
            fake = Path(tmp) / 'tmux'
            fake.write_text(f'#!/bin/sh\necho "$@" >> {calls}\nexit 1\n')
            fake.chmod(0o755)
            env = {**REQUIRED, 'P3_LOG_DIR': tmp, 'PATH': f"{tmp}:{os.environ['PATH']}"}
            result = run('down', env=env, repo=tmp)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            asked = calls.read_text()
            for role in ('camview', 'browser', 'cap', 'web', 'stack', 'nav', 'arm'):
                self.assertIn(f'p3v2-{role}', asked, role)

    def test_usage_without_a_command(self):
        result = run()
        self.assertEqual(2, result.returncode)
        self.assertIn('tools/demo_v2.sh up', result.stdout)

    def test_required_variables_are_named(self):
        result = run('cmds', env={'P3_DOMAIN': '41'})
        self.assertEqual(2, result.returncode)
        self.assertIn('P3_M0609 P3_DISPENSER_FILE', result.stdout)

    def test_commands_follow_the_practice_runbook(self):
        with tempfile.TemporaryDirectory() as repo:
            out = run('cmds', env={**REQUIRED, 'P3_INSTALL': '/ws/install', 'P3_LOG_DIR': '/logs'}, repo=repo)
        self.assertEqual(0, out.returncode, out.stdout + out.stderr)
        lines = dict(line.split(': ', 1) for line in out.stdout.splitlines() if ': ' in line)
        self.assertIn('env -i ', lines['stage'])
        self.assertIn('ROS_DOMAIN_ID=41', lines['stage'])
        self.assertIn('sim/standalone/pharmacy_stage.py --preset demo-ros-refill-v2', lines['stage'])
        self.assertIn('--robot-usd /assets/M0609/Collected_m0609_gripper/m0609_gripper.usd', lines['stage'])
        self.assertNotIn('--window-half', lines['stage'])              # 이 트리의 스테이지가 모르면 넘기지 않는다
        self.assertIn('창 인자를 넘기지 않는다', out.stderr)
        self.assertIn('m0609_arm --ros-args -p use_sim_time:=true -p scene_version:=2 -p v2_seed:=7', lines['arm'])
        self.assertIn(' --seed 7', lines['stage'])                    # 팔과 같은 seed(9/24 회차38: 스테이지는 0 이었다)
        self.assertIn('-p v2_guarded_module_path:=false', lines['arm'])
        for part in ('use_isaac_adapter:=true', 'pharmacy_only:=true', 'publish_clock:=false', 'emulate_m0609:=false',
                     'use_stub_m0609:=false', 'dispenser_file:=/cfg/dispenser_refill.yaml'):
            self.assertIn(part, lines['stack'])
        self.assertIn('--host 127.0.0.1 --port 8000 --allow-commands', lines['web'])
        for role in ('arm', 'stack', 'web'):
            self.assertIn('export ROS_DOMAIN_ID=41', lines[role])

    def test_film_take_runs_isaac_full_screen_with_the_render_cap_passed(self):
        """재범 9/24 14:4x: 촬영 테이크는 Isaac 화면 전체 + 렌더 1920x1080(hospital-full.md 6절)."""
        env = {**REQUIRED, 'P3_ISAAC_WINDOW': 'full', 'P3_RENDER_MAX': '1920x1080', 'P3_SCREEN_SIZE': '1920 1080'}
        with tempfile.TemporaryDirectory() as repo:
            stage_py = Path(repo) / 'sim' / 'standalone' / 'pharmacy_stage.py'
            stage_py.parent.mkdir(parents=True)
            stage_py.write_text('parser.add_argument("--window-half")\n')      # 이 트리의 스테이지가 인자를 안다
            out = run('cmds', env=env, repo=repo)
        self.assertEqual(0, out.returncode, out.stdout + out.stderr)
        stage = dict(line.split(': ', 1) for line in out.stdout.splitlines() if ': ' in line)['stage']
        self.assertIn('--window-half full --screen-size 1920 1080', stage)
        self.assertIn('P3_RENDER_MAX=1920x1080', stage)
        default = run('cmds', env=REQUIRED)
        self.assertNotIn('P3_RENDER_MAX=', dict(line.split(': ', 1) for line in default.stdout.splitlines()
                                                 if ': ' in line)['stage'])

    def test_the_stage_gets_the_arm_seed_and_stage_args_can_override_it(self):
        out = run('cmds', env={**REQUIRED, 'P3_V2_SEED': '23', 'P3_STAGE_ARGS': '--seed 5'})
        self.assertEqual(0, out.returncode, out.stdout + out.stderr)
        lines = dict(line.split(': ', 1) for line in out.stdout.splitlines() if ': ' in line)
        self.assertIn('v2_seed:=23', lines['arm'])
        stage = lines['stage']
        self.assertIn(' --seed 23', stage)
        self.assertLess(stage.index(' --seed 23'), stage.index(' --seed 5'))   # 뒤 값이 이긴다

    def test_guarded_demo_requires_explicit_selection(self):
        result = run('cmds', env={**REQUIRED, 'P3_V2_GUARDED_MODULE_PATH': 'true'})
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn('-p v2_guarded_module_path:=true', result.stdout)
        shown = run('env').stdout
        self.assertRegex(shown, r'P3_V2_GUARDED_MODULE_PATH +false\n')

    def test_rail_select_defaults_to_preferred_first_and_can_be_reverted(self):
        """재범 9/29 "디폴트로 켜서"(최적화 M0609 카드): 레일 후보는 선호 후보부터. first_feasible 로 되돌릴 수 있다."""
        self.assertIn('-p v2_rail_select:=preferred_first', run('cmds', env=REQUIRED).stdout)
        self.assertRegex(run('env').stdout, r'P3_V2_RAIL_SELECT +preferred_first\n')
        out = run('cmds', env={**REQUIRED, 'P3_V2_RAIL_SELECT': 'first_feasible'})
        self.assertEqual(0, out.returncode, out.stdout + out.stderr)
        self.assertIn('-p v2_rail_select:=first_feasible', out.stdout)
        for value in ('typo', ''):
            with self.subTest(value=value):
                out = run('cmds', env={**REQUIRED, 'P3_V2_RAIL_SELECT': value})
                self.assertEqual(2, out.returncode, out.stdout + out.stderr)
                self.assertIn('P3_V2_RAIL_SELECT', out.stdout)

    def test_invalid_guarded_selection_is_rejected_before_starting_any_role(self):
        with tempfile.TemporaryDirectory() as root:
            logs = Path(root) / 'not-created'
            for value in ('TRUE', '1', 'typo', ''):
                for command in ('cmds', 'up'):
                    with self.subTest(value=value, command=command):
                        result = run(command, env={**REQUIRED, 'P3_LOG_DIR': str(logs),
                                                  'P3_V2_GUARDED_MODULE_PATH': value})
                        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
                        self.assertIn('P3_V2_GUARDED_MODULE_PATH', result.stdout)
                        self.assertFalse(logs.exists())

    def test_custom_arm_command_remains_authoritative(self):
        result = run('cmds', env={**REQUIRED, 'P3_ARM_CMD': 'custom-arm --mode fixed',
                                  'P3_V2_GUARDED_MODULE_PATH': 'ignored'})
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn('arm: custom-arm --mode fixed\n', result.stdout)
        self.assertNotIn('v2_guarded_module_path:=', result.stdout)

    def test_screen_size_splits_isaac_left_and_browser_right(self):
        with tempfile.TemporaryDirectory() as repo:
            stage = Path(repo) / 'sim/standalone/pharmacy_stage.py'
            stage.parent.mkdir(parents=True)
            stage.write_text('parser.add_argument("--window-half")\n')
            out = run('cmds', env={**REQUIRED, 'P3_SCREEN_SIZE': '1920 1080'}, repo=repo)
            shown = run('env', env={'P3_SCREEN_SIZE': '1920 1080'}, repo=repo).stdout
            default = run('env', repo=repo).stdout
        self.assertIn('--window-half left --screen-size 1920 1080', out.stdout)
        self.assertRegex(shown, r'P3_BROWSER_WIDTH +960\n')
        self.assertRegex(shown, r'P3_BROWSER_HEIGHT +1080\n')
        self.assertRegex(default, r'P3_SCREEN_SIZE +2048 1152\n')      # master02 패널(리허설 값)
        self.assertRegex(default, r'P3_BROWSER_WIDTH +1024\n')

    def test_web_port_already_answering_stops_up_before_starting_web(self):
        """9/23 master02: 어제 뜬 다른 웹이 포트에 남아 있어 우리 웹이 bind 에 실패했는데 "web 준비"로 읽었다."""
        text = SCRIPT.read_text(encoding='utf-8')
        guard = text.index('이미 다른 서버가 응답한다')
        self.assertLess(guard, text.index('start_role web "$(web_cmd)"'))
        body = text[text.index('wait_http() {'):text.index('clock_publishers() {')]
        self.assertLess(body.index("grep -q '^exit='"), body.index('urllib.request.urlopen'))

    def test_web_url_opens_the_front_demo_mode_by_default(self):
        default = run('env').stdout
        plain = run('env', env={'P3_WEB_QUERY': ''}).stdout
        self.assertRegex(default, r'P3_WEB_QUERY +\?demo=1\n')         # 프론트 시연 모드(#217)
        self.assertRegex(plain, r'P3_WEB_QUERY +\(없음\)\n')           # 빈 값을 주면 일반 화면

    def test_status_shows_the_tree_at_launch_and_now(self):
        """지금 도는 것이 고친 그것인지(작전 공통 규칙 9/18): 띄울 때와 지금의 sha·install 시각을 같이 찍는다."""
        repo = Path(__file__).resolve().parents[1]
        head = subprocess.run(['git', '-C', str(repo), 'rev-parse', '--short=12', 'HEAD'],
                              capture_output=True, text=True, check=True).stdout.strip()
        with tempfile.TemporaryDirectory() as logs:
            Path(logs, '.current').write_text('20260918-120000\n')
            Path(logs, '20260918-120000-tree.txt').write_text('tree 0123456789ab(커밋 …) install 없음\n')
            Path(logs, '20260918-120000-stage.log').write_text('2026-09-18T12:00:01 $ stage\n[demo_v2] started\n')
            out = run('status', env={'P3_LOG_DIR': logs, 'P3_SESSION_PREFIX': 'p3v2-test-none'}, repo=repo).stdout
        self.assertIn('띄울 때 tree 0123456789ab', out)
        self.assertIn(f'지금    tree {head}', out)
        self.assertRegex(out, r'stage +없음')
        self.assertRegex(out, r'시계 동기화 NTPSynchronized=(yes|no|모름)')   # timedatectl 이 없는 러너면 모름


FAKE_ROS2 = """#!/usr/bin/env bash
# 가짜 ros2 — /clock 발행자 수(FAKE_CLOCK_PUBS)와 시각(FAKE_CLOCK_FROZEN 이면 멈춤)만 흉내 낸다.
case "$1 $2" in
  'topic info') echo "Type: rosgraph_msgs/msg/Clock"; echo "Publisher count: ${FAKE_CLOCK_PUBS:-0}" ;;
  'topic echo')
    n=$(cat "$FAKE_DIR/clock" 2>/dev/null || echo 10)
    [[ ${FAKE_CLOCK_FROZEN:-0} == 1 ]] || echo $((n + 1)) > "$FAKE_DIR/clock"
    echo "$n,500000000" ;;
  'node list') [[ ${FAKE_CLOCK_PUBS:-0} == 0 ]] || echo /isaac_ros2_bridge ;;
esac
"""
FAKE_TMUX = """#!/usr/bin/env bash
# 가짜 tmux — 세션은 하나도 없고, new-session 은 기록만 한다. send-keys 로 받은 줄은 그 자리에서 돌린다 —
# 안 돌리면 start_role 이 '[demo_v2] started' 를 10 s 기다려(부하 때 run() 의 30 s 시한에 닿았다, 시뮬통합 9/24).
# 명령은 가짜 ros2 라 곧 끝나고, 로그에 exit= 가 남아 wait_line 이 바로 멈춘다.
case "$1" in
  has-session) exit 1 ;;
  new-session) echo "$*" >> "$FAKE_DIR/tmux.log" ;;
  send-keys) [[ ${5:-} == Enter ]] && eval "$4" >/dev/null 2>&1 ;;
esac
exit 0
"""


class TwoMasterTests(unittest.TestCase):
    """두 마스터로 나눠 띄우기(재범 9/23): P3_ROLES 로 PC 별 역할, P3_PEER 로 DDS·/clock 공유 확인."""

    HOSPITALISH = {**REQUIRED, 'P3_WORLD': 'emptyworld', 'P3_UR5_ARM_PARAMS': '/cfg/ur5_arm.yaml'}

    def fake_env(self, root, **extra):
        root = Path(root)
        bin_dir = root / 'bin'
        bin_dir.mkdir()
        for name, body in (('ros2', FAKE_ROS2), ('tmux', FAKE_TMUX)):
            (bin_dir / name).write_text(body, encoding='utf-8')
            (bin_dir / name).chmod(0o755)
        (root / 'ros_setup.bash').write_text('', encoding='utf-8')
        (root / 'install').mkdir()
        (root / 'install/setup.bash').write_text('', encoding='utf-8')
        return {**REQUIRED, 'PATH': f'{bin_dir}:{os.environ["PATH"]}', 'FAKE_DIR': str(root),
                'P3_ROS_SETUP': str(root / 'ros_setup.bash'), 'P3_INSTALL': str(root / 'install'),
                'P3_LOG_DIR': str(root / 'logs'), 'P3_SESSION_PREFIX': 'p3v2-test-two',
                'P3_ISAAC_PATTERN': 'no-such-process-[x]yz', **extra}

    def cmds(self, env):
        out = run('cmds', env=env)
        self.assertEqual(0, out.returncode, out.stdout + out.stderr)
        return dict(line.split(': ', 1) for line in out.stdout.splitlines() if ': ' in line)

    def test_default_is_every_role_of_the_world(self):
        self.assertEqual({'stage', 'arm', 'nav', 'stack', 'web'}, set(self.cmds(self.HOSPITALISH)))
        self.assertRegex(run('env', env=self.HOSPITALISH).stdout, r'P3_ROLES +stage arm nav stack web\n')

    def test_each_master_gets_only_its_roles(self):
        self.assertEqual({'stage'}, set(self.cmds({**self.HOSPITALISH, 'P3_ROLES': 'stage'})))
        rest = self.cmds({**self.HOSPITALISH, 'P3_ROLES': 'web stack nav arm'})
        self.assertEqual(['arm', 'nav', 'stack', 'web'], list(rest), '월드 순서를 따른다')

    def test_the_web_learns_the_two_host_layout_only_with_a_peer(self):
        """관제 화면이 두 PC 모드를 안다(snapshot.deployment, 카드 ⑤). ros_env 가 env -i 라 인자로 넘긴다."""
        one = self.cmds(self.HOSPITALISH)['web']
        self.assertNotIn('--roles', one)
        self.assertNotIn('--peer', one)
        two = self.cmds({**self.HOSPITALISH, 'P3_ROLES': 'web stack nav arm', 'P3_PEER': '10.10.0.1'})['web']
        self.assertIn(r'--roles arm\ nav\ stack\ web --peer 10.10.0.1', two)

    def test_a_role_the_world_does_not_have_is_rejected(self):
        for roles in ('nav', 'stage bogus'):          # demo 월드에는 nav 가 없다
            with self.subTest(roles=roles):
                out = run('cmds', env={**REQUIRED, 'P3_ROLES': roles})
                self.assertEqual(2, out.returncode)
                self.assertIn('이 월드(demo)의 역할이 아니다', out.stderr)

    def test_two_hosts_pass_the_profile_and_subnet_discovery_to_every_ros_role(self):
        profile = '/home/m/.ros/fastdds_whitelist.xml'
        two = self.cmds({**self.HOSPITALISH, 'P3_PEER': '10.10.0.1', 'P3_FASTDDS_PROFILE': profile})
        one = self.cmds(self.HOSPITALISH)
        for role in ('arm', 'nav', 'stack', 'web'):
            self.assertIn(f'FASTRTPS_DEFAULT_PROFILES_FILE={profile} ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET', two[role])
            self.assertNotIn('ROS_AUTOMATIC_DISCOVERY_RANGE', one[role], '한 PC 는 지금 동작 그대로')

    def test_the_rest_pc_stops_before_anything_unless_one_clock_is_shared(self):
        for pubs, why in (('0', '스테이지 PC 를 먼저 up'), ('2', '다른 스택이 섞였다')):
            with self.subTest(pubs=pubs), tempfile.TemporaryDirectory() as root:
                env = self.fake_env(root, P3_ROLES='arm stack web', FAKE_CLOCK_PUBS=pubs)
                out = run('up', env=env)
                self.assertEqual(3, out.returncode, out.stdout + out.stderr)
                self.assertIn(why, out.stdout)
                self.assertFalse(Path(root, 'tmux.log').exists(), '아무 역할도 띄우지 않는다')

    def test_the_stage_pc_still_needs_an_empty_domain(self):
        with tempfile.TemporaryDirectory() as root:
            out = run('up', env=self.fake_env(root, P3_ROLES='stage', FAKE_CLOCK_PUBS='1'))
        self.assertEqual(3, out.returncode, out.stdout)
        self.assertIn('/clock 발행자가 1 이다(0 이어야 한다)', out.stdout)

    def test_a_frozen_clock_is_not_a_playing_stage(self):
        with tempfile.TemporaryDirectory() as root:
            env = self.fake_env(root, P3_ROLES='arm stack web', FAKE_CLOCK_PUBS='1', FAKE_CLOCK_FROZEN='1',
                                P3_STAGE_TIMEOUT_S='1')
            out = run('up', env=env)
            self.assertEqual(4, out.returncode, out.stdout)
            self.assertIn('/clock 이 1 s 안에 흐르지 않는다', out.stdout)
            self.assertFalse(Path(root, 'tmux.log').exists())

    def test_a_flowing_shared_clock_lets_the_rest_pc_start_its_first_role(self):
        with tempfile.TemporaryDirectory() as root:
            env = self.fake_env(root, P3_ROLES='arm stack web', FAKE_CLOCK_PUBS='1', P3_ARM_TIMEOUT_S='1')
            out = run('up', env=env)
            started = Path(root, 'tmux.log').read_text(encoding='utf-8')
        self.assertIn('/clock 공유 확인: 발행자 1', out.stdout)
        self.assertIn('-arm', started)
        self.assertNotIn('-stage', started, '스테이지는 다른 PC 다')
        self.assertIn('arm 이 준비 전에 끝났다', out.stdout)   # 가짜 ros2 라 팔이 곧 끝난다 — 10 s 기다리지 않는다
        self.assertIn('up 중단(arm)', out.stdout)

    def test_peer_checks_stop_on_a_profile_without_both_addresses(self):
        with tempfile.TemporaryDirectory() as root:
            profile = Path(root, 'fastdds.xml')
            profile.write_text('<address>127.0.0.1</address>\n', encoding='utf-8')
            env = self.fake_env(root, P3_ROLES='arm stack web', P3_PEER='127.0.0.2', P3_FASTDDS_PROFILE=str(profile))
            out = run('up', env=env)
        self.assertEqual(2, out.returncode, out.stdout)
        self.assertIn('DDS 프로필에 127.0.0.2 가 없다', out.stdout)

    def test_peer_checks_stop_when_discovery_is_limited_to_this_pc(self):
        with tempfile.TemporaryDirectory() as root:
            profile = Path(root, 'fastdds.xml')
            profile.write_text('<address>127.0.0.1</address><address>127.0.0.2</address>\n', encoding='utf-8')
            env = self.fake_env(root, P3_ROLES='arm stack web', P3_PEER='127.0.0.2', P3_FASTDDS_PROFILE=str(profile),
                                ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST')
            out = run('up', env=env)
        self.assertEqual(2, out.returncode, out.stdout)
        self.assertIn('ROS 탐색을 이 PC 로 막았다', out.stdout)

    def test_peer_checks_pass_then_the_clock_decides(self):
        with tempfile.TemporaryDirectory() as root:
            profile = Path(root, 'fastdds.xml')
            profile.write_text('<address>127.0.0.1</address><address>127.0.0.2</address>\n', encoding='utf-8')
            env = self.fake_env(root, P3_ROLES='arm stack web', P3_PEER='127.0.0.2', P3_FASTDDS_PROFILE=str(profile),
                                FAKE_CLOCK_PUBS='0')
            out = run('up', env=env)
        self.assertIn('두 PC: 이 PC 127.0.0.1 ↔ 상대 127.0.0.2 ping 됨', out.stdout)
        self.assertEqual(3, out.returncode, out.stdout)

    def test_stage_only_files_are_needed_only_where_the_stage_runs(self):
        """병원 워크셀 JSON·씬은 스테이지만 읽는다. 나머지 PC 에 깔 필요가 없다."""
        hospital = {**REQUIRED, 'P3_WORLD': 'hospital', 'P3_AMR_COMBINED': '/assets/ridgeback_ur5.usd'}
        rest = run('cmds', env={**hospital, 'P3_ROLES': 'arm nav stack web'})
        self.assertEqual(0, rest.returncode, rest.stdout + rest.stderr)
        stage = run('cmds', env={**hospital, 'P3_ROLES': 'stage'})
        self.assertEqual(2, stage.returncode)
        self.assertIn('P3_WORKCELL_LAYOUT', stage.stdout)

    def test_down_on_the_rest_pc_leaves_the_stage_alone(self):
        text = SCRIPT.read_text(encoding='utf-8')
        body = text[text.index('cmd_down() {'):text.index('cmd_status() {')]
        self.assertLess(body.index('has_role stage || return 0'), body.index('stop_role stage'))


if __name__ == '__main__':
    unittest.main()


class EmptyWorldProfileTests(unittest.TestCase):
    """P3_WORLD=emptyworld 프로필(카드 K6). 기본값(demo)은 한 글자도 바뀌지 않아야 한다."""

    def test_default_world_has_no_nav_role_and_keeps_the_demo_preset(self):
        result = run('cmds', env=REQUIRED)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertNotIn('nav:', result.stdout)
        self.assertIn('--preset demo-ros-refill-v2', result.stdout)
        self.assertNotIn('--amr', result.stdout)
        self.assertIn('pharmacy_only:=true', result.stdout)

    def test_empty_world_adds_the_nav_role_and_the_real_arm_bundle(self):
        with tempfile.TemporaryDirectory() as repo:
            out = run('cmds', env={**REQUIRED, 'P3_WORLD': 'emptyworld',
                                   'P3_UR5_ARM_PARAMS': '/cfg/ur5_arm.yaml'}, repo=repo)
            zones = f'{repo}/src/rokey_p3_description/config/zones.emptyworld.yaml'
            routes = f'{repo}/src/rokey_p3_description/config/routes.emptyworld.yaml'
            pool = f'{repo}/src/rokey_p3_orchestrator/config/order_pool.yaml'
        self.assertEqual(0, out.returncode, out.stdout + out.stderr)
        lines = dict(line.split(': ', 1) for line in out.stdout.splitlines() if ': ' in line)
        self.assertIn('--preset emptyworld-loop --amr', lines['stage'])
        # 스테이지 자산·주문 풀 인자는 월드와 무관하게 그대로다(실습23b: preset 과 충돌 없다).
        self.assertIn('--robot-usd /assets/M0609/Collected_m0609_gripper/m0609_gripper.usd', lines['stage'])
        self.assertIn(f'--order-pool {pool}', lines['stage'])
        self.assertIn('navigation.launch.py motion_backend:=waypoints', lines['nav'])
        self.assertIn(f'zones_file:={zones}', lines['nav'])
        self.assertIn(f'routes_file:={routes}', lines['nav'])
        for part in ('pharmacy_only:=false', 'use_stub_fleet:=false', 'use_stub_arm:=false',
                     'pick_notice:=false', 'use_ur5_arm:=true', 'ur5_arm_params_file:=/cfg/ur5_arm.yaml'):
            self.assertIn(part, lines['stack'])
        self.assertIn(f'--zones-file {zones}', lines['web'])

    def test_unknown_world_is_rejected(self):
        for value in ('Hospital', 'Emptyworld', ''):
            with self.subTest(value=value):
                result = run('cmds', env={**REQUIRED, 'P3_WORLD': value})
                self.assertEqual(2, result.returncode, result.stdout + result.stderr)

    def test_empty_world_up_needs_the_arm_parameter_file(self):
        with tempfile.TemporaryDirectory() as root:
            logs = Path(root) / 'not-created'
            result = run('up', env={**REQUIRED, 'P3_WORLD': 'emptyworld', 'P3_LOG_DIR': str(logs)})
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn('P3_UR5_ARM_PARAMS', result.stdout)
        self.assertFalse(logs.exists())

    def test_sim_sensors_turn_on_the_stage_flag_and_the_stack_bundle(self):
        """스테이지 --sim-sensors 와 스택의 넷은 한 묶음이다(어긋나면 launch 가 기동 전에 멈춘다)."""
        with tempfile.TemporaryDirectory() as repo:
            out = run('cmds', env={**REQUIRED, 'P3_WORLD': 'emptyworld', 'P3_SIM_SENSORS': '1',
                                   'P3_UR5_ARM_PARAMS': '/cfg/ur5_arm.yaml'}, repo=repo)
            off = run('cmds', env={**REQUIRED, 'P3_WORLD': 'emptyworld',
                                   'P3_UR5_ARM_PARAMS': '/cfg/ur5_arm.yaml'}, repo=repo)
            pool = f'{repo}/src/rokey_p3_orchestrator/config/order_pool.yaml'
        self.assertEqual(0, out.returncode, out.stdout + out.stderr)
        lines = dict(line.split(': ', 1) for line in out.stdout.splitlines() if ': ' in line)
        self.assertIn('--sim-sensors', lines['stage'])
        self.assertIn(f'--order-pool {pool}', lines['stage'])      # tag_id 가 이 파일에서 나온다
        for part in ('sim_pouches:=true', 'sim_tag_reads:=true', 'pouch_source:=sim', 'scan_tag_source:=sim'):
            self.assertIn(part, lines['stack'])
        self.assertNotIn('--sim-sensors', off.stdout)               # 기본은 꺼짐
        self.assertNotIn('pouch_source:=sim', off.stdout)

    def test_deck_vision_adds_the_detector_beside_the_truth_pick(self):
        """재범 9/25 점수판 AI 비전: 참값 집기는 그대로(pouch_source:=sim), 검출기·교차 확인만 더한다. 기본은 꺼짐."""
        with tempfile.TemporaryDirectory() as repo:
            env = {**REQUIRED, 'P3_WORLD': 'emptyworld', 'P3_SIM_SENSORS': '1',
                   'P3_UR5_ARM_PARAMS': '/cfg/ur5_arm.yaml'}
            on = run('cmds', env={**env, 'P3_DECK_VISION': '1'}, repo=repo)
            off = run('cmds', env=env, repo=repo)
        self.assertEqual(0, on.returncode, on.stdout + on.stderr)
        stack = dict(line.split(': ', 1) for line in on.stdout.splitlines() if ': ' in line)['stack']
        for part in ('pouch_source:=sim', 'use_stub_detector:=false', 'use_pouch_detector:=true',
                     'vision_check:=true', 'detector_max_rate_hz:=5.0', 'detector_pouch_distance_m:=0.30',
                     'detector_save_reads_dir:='):
            self.assertIn(part, stack)
        self.assertIn('-deck-frames', stack)
        self.assertNotIn('vision_check:=true', off.stdout)

    def test_camera_pouches_swap_only_the_pouch_source(self):
        """카메라 모드: 봉투는 pouch_detector, 인식표·보관함은 시뮬 센서 그대로. 스테이지는 봉투에 QR 을 붙인다."""
        with tempfile.TemporaryDirectory() as repo:
            env = {**REQUIRED, 'P3_WORLD': 'emptyworld', 'P3_SIM_SENSORS': '1', 'P3_CAMERA_POUCHES': '1',
                   'P3_UR5_ARM_PARAMS': '/cfg/ur5_arm.yaml'}
            out = run('cmds', env=env, repo=repo)
            alone = run('cmds', env={**env, 'P3_SIM_SENSORS': '0'}, repo=repo)
            demo = run('cmds', env={**REQUIRED, 'P3_CAMERA_POUCHES': '1'}, repo=repo)
            qr = f'{repo}/sim/outputs/qr'
        self.assertEqual(0, out.returncode, out.stdout + out.stderr)
        lines = dict(line.split(': ', 1) for line in out.stdout.splitlines() if ': ' in line)
        for part in ('use_stub_detector:=false', 'use_pouch_detector:=true', 'pouch_source:=camera',
                     'belt_view_standoff_m:=0.30', 'belt_view_offset_m:=-0.075',
                     'detector_pouch_distance_m:=0.290',
                     'sim_tag_reads:=true', 'scan_tag_source:=sim', 'sim_cabinet:=true'):
            self.assertIn(part, lines['stack'])
        for part in ('sim_pouches:=true', 'pouch_source:=sim'):
            self.assertNotIn(part, lines['stack'])
        self.assertIn(f'--qr-dir {qr}', lines['stage'])
        self.assertIn('make_qr_textures.py', lines['stage'])
        self.assertNotIn('sim_tag_reads', alone.stdout)             # 시뮬 센서 없이 카메라만
        self.assertIn('use_pouch_detector:=true', alone.stdout)
        self.assertNotIn('use_pouch_detector', demo.stdout)         # demo 월드는 영향 없음
        self.assertNotIn('--qr-dir', demo.stdout)

    def test_camera_pouches_on_the_combined_amr_add_the_wrist_camera(self):
        env = {**REQUIRED, 'P3_WORLD': 'emptyworld', 'P3_CAMERA_POUCHES': '1',
               'P3_UR5_ARM_PARAMS': '/cfg/ur5_arm.yaml', 'P3_AMR_COMBINED': '/assets/ridgeback_ur5.usd'}
        combined = run('cmds', env=env)
        pedestal = run('cmds', env={**env, 'P3_AMR_COMBINED': ''})
        without = run('cmds', env={**env, 'P3_CAMERA_POUCHES': '0'})
        self.assertIn('--amr-hand-camera --camera-resolution 1280 800', combined.stdout)
        self.assertNotIn('--amr-hand-camera', pedestal.stdout)    # 받침대 UR5 는 자기 카메라가 있다
        self.assertNotIn('--amr-hand-camera', without.stdout)

    def test_camera_view_window_is_opt_in_and_off_when_headless(self):
        env = {**REQUIRED, 'P3_WORLD': 'emptyworld', 'P3_CAMERA_POUCHES': '1', 'P3_CAMERA_VIEW': '1',
               'P3_UR5_ARM_PARAMS': '/cfg/ur5_arm.yaml'}
        shown = run('env', env=env).stdout
        self.assertIn('P3_CAMERA_VIEW       1', shown)
        headless = run('env', env={**env, 'P3_HEADLESS': '1'}).stdout
        self.assertIn('P3_CAMERA_VIEW       0', headless)
        default = run('env', env={**REQUIRED, 'P3_WORLD': 'emptyworld', 'P3_UR5_ARM_PARAMS': '/cfg/ur5_arm.yaml'})
        self.assertIn('P3_CAMERA_VIEW       0', default.stdout)

    def test_container_qr_turns_on_the_stage_stack_and_arm_parts_together(self):
        """카드 Q1: 약통 QR 면·M0609 카메라(스테이지), QR 판독·DB 서비스(스택), 약통 확인(팔)은 한 묶음이다."""
        with tempfile.TemporaryDirectory() as repo:
            on = run('cmds', env={**REQUIRED, 'P3_CONTAINER_QR': '1'}, repo=repo)
            off = run('cmds', env=REQUIRED, repo=repo)
            catalog = f'{repo}/src/rokey_p3_orchestrator/config/pharmacy_catalog.yaml'
            qr = f'{repo}/sim/outputs/qr'
        self.assertEqual(0, on.returncode, on.stdout + on.stderr)
        lines = dict(line.split(': ', 1) for line in on.stdout.splitlines() if ': ' in line)
        self.assertIn(f'--catalog {catalog} --canister-qr-dir {qr} --m0609-hand-camera', lines['stage'])
        self.assertIn('make_qr_textures.py --order-pool', lines['stage'])
        self.assertIn(f'--catalog {catalog} --out {qr}', lines['stage'])
        self.assertIn('use_m0609_detector:=true pharmacy_db:=true', lines['stack'])
        self.assertIn('-p container_check:=true', lines['arm'])
        for part in ('--canister-qr-dir', 'use_m0609_detector', 'pharmacy_db', 'container_check', 'make_qr_textures'):
            self.assertNotIn(part, off.stdout)

    def test_each_world_waits_for_its_own_ready_line(self):
        """빈월드는 `stage ready` 를 기다린다. PLAY 는 스폰·센서가 붙기 전에 나온다(시뮬 9/21)."""
        shown = run('env', env={**REQUIRED, 'P3_WORLD': 'emptyworld',
                                'P3_UR5_ARM_PARAMS': '/cfg/ur5_arm.yaml'}).stdout
        self.assertNotIn('timeline_event', shown)
        demo = run('env', env=REQUIRED).stdout
        self.assertNotIn('stage ready', demo)

    def world_files(self, repo):
        """emptyworld 가 기동 전에 있는지 보는 파일들을 만든다."""
        root = Path(repo)
        (root / 'src/rokey_p3_description/config').mkdir(parents=True)
        (root / 'src/rokey_p3_orchestrator/config').mkdir(parents=True)
        for name in ('zones.emptyworld.yaml', 'routes.emptyworld.yaml'):
            (root / 'src/rokey_p3_description/config' / name).write_text('', encoding='utf-8')
        (root / 'src/rokey_p3_orchestrator/config/order_pool.yaml').write_text('', encoding='utf-8')
        return root

    def test_the_amr_combined_usd_goes_to_the_stage(self):
        """AMR 합본(ridgeback_ur5.usd)과 받침대 UR5 는 다른 구성이다. 인자 이름은 한 곳에서만 만든다."""
        with tempfile.TemporaryDirectory() as repo:
            root = self.world_files(repo)
            usd = root / 'ridgeback_ur5.usd'
            usd.write_text('', encoding='utf-8')
            params = root / 'combined.yaml'
            params.write_text('joint_names: [ur_arm_shoulder_pan_joint]\narm_base_frame_convention: base_link\n',
                              encoding='utf-8')
            env = {**REQUIRED, 'P3_WORLD': 'emptyworld', 'P3_UR5_ARM_PARAMS': str(params),
                   'P3_AMR_COMBINED': str(usd)}
            out = run('cmds', env=env, repo=repo)
            without = run('cmds', env={k: v for k, v in env.items() if k != 'P3_AMR_COMBINED'}, repo=repo)
        self.assertEqual(0, out.returncode, out.stdout + out.stderr)
        self.assertIn(f'--amr-combined {usd}', out.stdout)
        self.assertNotIn('--amr-combined', without.stdout)      # 기본은 받침대 UR5 다

    def test_camera_pick_refuses_params_without_the_camera_keys(self):
        """카메라 집기는 tool_frame·tcp_offset_m·refine_view_standoff_m 이 있어야 한다. 없으면 기동 전에 멈춘다."""
        with tempfile.TemporaryDirectory() as repo:
            root = self.world_files(repo)
            usd = root / 'ridgeback_ur5.usd'
            usd.write_text('', encoding='utf-8')
            params = root / 'lap16.yaml'
            params.write_text('joint_names: [ur_arm_shoulder_pan_joint]\narm_base_frame_convention: base\n',
                              encoding='utf-8')
            logs = root / 'not-created'
            env = {**REQUIRED, 'P3_WORLD': 'emptyworld', 'P3_LOG_DIR': str(logs), 'P3_CAMERA_POUCHES': '1',
                   'P3_UR5_ARM_PARAMS': str(params), 'P3_AMR_COMBINED': str(usd)}
            result = run('up', env=env, repo=repo)
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        for key in ('tool_frame', 'tcp_offset_m', 'refine_view_standoff_m'):
            self.assertIn(key, result.stdout)

    def test_camera_tags_refuse_a_zero_tag_reading_distance(self):
        """인식표 카메라(P3_CAMERA_TAGS=1)는 tag_standoff_m 이 0 보다 커야 한다 — 키만 있고 0 이면 기동 전에 멈춘다
        (통합검증 5882413759: 0 이면 ScanTag 가 팔을 안 움직이고 UNREADABLE 로 닫힌다)."""
        keys = ('joint_names: [ur_arm_shoulder_pan_joint]\narm_base_frame_convention: base\n'
                'tool_frame: w\ntcp_offset_m: [0, 0, 0.1555]\nrefine_view_standoff_m: 0.2\n')
        results = {}
        for value in ('0.0', '0.25'):
            with tempfile.TemporaryDirectory() as repo:
                root = self.world_files(repo)
                usd = root / 'ridgeback_ur5.usd'
                usd.write_text('', encoding='utf-8')
                params = root / 'camera.yaml'
                params.write_text(keys + f'tag_standoff_m: {value}\n', encoding='utf-8')
                env = {**REQUIRED, 'P3_WORLD': 'emptyworld', 'P3_LOG_DIR': str(root / 'not-created'),
                       'P3_CAMERA_POUCHES': '1', 'P3_CAMERA_TAGS': '1',
                       'P3_UR5_ARM_PARAMS': str(params), 'P3_AMR_COMBINED': str(usd)}
                results[value] = run('up', env=env, repo=repo)
        self.assertEqual(2, results['0.0'].returncode)
        self.assertIn('tag_standoff_m 이 없거나 0 이하다', results['0.0'].stdout)
        self.assertNotIn('tag_standoff_m', results['0.25'].stdout)

    def test_the_combined_run_refuses_a_pedestal_params_file(self):
        """합본은 팔 params 가 다르다. 받침대용으로 띄우면 관절 이름과 밑동 기준이 조용히 어긋난다."""
        with tempfile.TemporaryDirectory() as repo:
            root = self.world_files(repo)
            usd = root / 'ridgeback_ur5.usd'
            usd.write_text('', encoding='utf-8')
            params = root / 'pedestal.yaml'
            params.write_text('deck_slot_frame_base: 1\n', encoding='utf-8')
            logs = root / 'not-created'
            result = run('up', env={**REQUIRED, 'P3_WORLD': 'emptyworld', 'P3_LOG_DIR': str(logs),
                                    'P3_UR5_ARM_PARAMS': str(params), 'P3_AMR_COMBINED': str(usd)}, repo=repo)
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn('ur_arm_', result.stdout)
        self.assertIn('arm_base_frame_convention', result.stdout)

    def test_deck_slots_matches_the_stage_tray(self):
        """자리 수의 단일 출처는 `layout.TRAY["slots"]` 다. 프로필이 그 수를 그대로 준다.

        시뮬은 "저장소가 달라 시험으로 못 묶는다" 고 했지만 같은 저장소다 — 그 표를 읽어 맞댄다.
        9/21: `TripConfig.deck_slots` 가 5 로 박혀 있어 넷째 주문이 없는 `deck_slot_4` 로 갈 뻔했다.
        """
        import importlib
        import sys
        standalone = Path(__file__).resolve().parents[1] / 'sim' / 'standalone'
        if not (standalone / 'p3sim' / 'layout.py').exists():
            self.skipTest(f'스테이지 레이아웃이 없다: {standalone}')
        sys.path.insert(0, str(standalone))          # layout 이 같은 꾸러미의 geometry 를 쓴다
        try:
            layout = importlib.import_module('p3sim.layout')
        finally:
            sys.path.remove(str(standalone))
        slots = getattr(layout, 'TRAY', {}).get('slots')
        if slots is None:
            self.skipTest('layout.TRAY["slots"] 가 아직 없다(시뮬 #445 전 트리)')

        with tempfile.TemporaryDirectory() as repo:
            out = run('cmds', env={**REQUIRED, 'P3_WORLD': 'emptyworld',
                                   'P3_UR5_ARM_PARAMS': '/cfg/ur5_arm.yaml'}, repo=repo)
        self.assertEqual(0, out.returncode, out.stdout + out.stderr)
        self.assertIn(f'deck_slots:={len(slots)}', out.stdout)

    def test_headless_drops_the_window_arguments_and_the_browser(self):
        result = run('cmds', env={**REQUIRED, 'P3_HEADLESS': '1', 'P3_BROWSER': 'firefox',
                                  'P3_CAPTURE_EVERY': '5'})
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn('--headless', result.stdout)
        self.assertNotIn('--window-half', result.stdout)
        shown = run('env', env={**REQUIRED, 'P3_HEADLESS': '1', 'P3_BROWSER': 'firefox',
                                'P3_CAPTURE_EVERY': '5'}).stdout
        self.assertRegex(shown, r'P3_BROWSER +\(없음\)\n')
        self.assertRegex(shown, r'P3_CAPTURE_EVERY +0\n')


class HospitalProfileTests(unittest.TestCase):
    """P3_WORLD=hospital(#527 H3): 병원 씬 전 구간. 빈월드와 같은 "한 바퀴" 쪽이고 다른 것만 따로 본다."""

    ENV = {**REQUIRED, 'P3_WORLD': 'hospital', 'P3_UR5_ARM_PARAMS': '/cfg/ur5_arm.yaml',
           'P3_AMR_COMBINED': '/assets/ridgeback_ur5.usd', 'P3_WORKCELL_LAYOUT': '/site/workcell.json'}

    def lines(self, out):
        return dict(line.split(': ', 1) for line in out.stdout.splitlines() if ': ' in line)

    def test_hospital_attaches_cameras_and_gripper_by_default(self):
        # 재범 9/23: 병원은 M0609 RealSense·합본 흡착 그리퍼+RealSense 를 기본으로 붙인다(끄려면 P3_CONTAINER_QR=0)
        with tempfile.TemporaryDirectory() as repo:
            out = run('cmds', env=self.ENV, repo=repo)
            off = run('cmds', env={**self.ENV, 'P3_CONTAINER_QR': '0'}, repo=repo)
        self.assertEqual(0, out.returncode, out.stdout + out.stderr)
        stage = self.lines(out)['stage']
        self.assertIn('--amr-hand-camera', stage)
        self.assertIn('--m0609-hand-camera', stage)
        self.assertNotIn('--m0609-hand-camera', self.lines(off)['stage'])

    def test_hospital_pouch_camera_reads_the_ord_qr_at_a1(self):
        """시나리오 3단계(A1 에서 봉투 QR 스캔 → 집기): 봉투에 QR, 스택은 카메라 검출·관측 자세.

        병원 기본이다(재범 9/29 "QR 반드시 찍고 가져가야함"). 참값 센서 집기는 P3_CAMERA_POUCHES=0 을 줄 때만이다.
        """
        with tempfile.TemporaryDirectory() as repo:
            on = run('cmds', env=self.ENV, repo=repo)
            off = run('cmds', env={**self.ENV, 'P3_CAMERA_POUCHES': '0'}, repo=repo)
            qr = f'{repo}/sim/outputs/qr'
        self.assertEqual(0, on.returncode, on.stdout + on.stderr)
        lines = self.lines(on)
        self.assertIn(f'--qr-dir {qr}', lines['stage'])
        for part in ('use_pouch_detector:=true', 'pouch_source:=camera', 'belt_view_standoff_m:=0.30'):
            self.assertIn(part, lines['stack'])
        self.assertIn(f'--qr-dir {qr}', self.lines(off)['stage'])        # 봉투 QR 은 병원 기본(재범 9/23)
        self.assertIn('make_qr_textures.py', self.lines(off)['stage'])
        self.assertNotIn('use_pouch_detector', self.lines(off)['stack'])

    def test_hospital_reads_the_bed_and_station_tags_with_the_camera_too(self):
        """재범 9/29: 병상 QR 을 찍고 → 약 QR 을 찍어 매칭 → 내려놓기. 인식표도 손 카메라 QR 이다(참값 인식표 없음)."""
        stack = self.lines(run('cmds', env={**self.ENV, 'P3_SIM_SENSORS': '1'}))['stack']
        self.assertIn('scan_tag_source:=camera', stack)
        self.assertNotIn('sim_tag_reads:=true', stack)
        self.assertNotIn('scan_tag_source:=sim', stack)
        self.assertIn('sim_cabinet:=true', stack)                 # 보관함 참값은 평가용이라 그대로
        # 인식표만 참값으로 되돌릴 수 있다(명시적으로 줄 때만).
        old = self.lines(run('cmds', env={**self.ENV, 'P3_SIM_SENSORS': '1', 'P3_CAMERA_TAGS': '0'}))['stack']
        self.assertIn('scan_tag_source:=sim', old)
        self.assertIn('pouch_source:=camera', old)

    def test_the_hospital_camera_arm_params_have_a_tag_reading_distance(self):
        """인식표 카메라는 판독 거리가 있어야 한다(arm_node tag_standoff_m 0 이면 ScanTag 가 곧바로 실패)."""
        params = SCRIPT.parents[1] / 'src' / 'rokey_p3_manipulation' / 'config' / 'ur5_arm.amr-combined.camera.yaml'
        self.assertRegex(params.read_text(encoding='utf-8'), r'(?m)^ +tag_standoff_m: 0\.\d+')
        self.assertIn('tag_standoff_m', SCRIPT.read_text(encoding='utf-8'))

    def test_hospital_arm_params_follow_the_pouch_source(self):
        """병원은 그리퍼+D455 가 늘 붙는다. 팔 params 를 안 주면 저장소 파일을 쓰되, 봉투를 카메라로 찾을 때만
        camera 판이고 참값 센서(기본, v0)면 gripper 판(흡착점 같고 pouch_source 만 sim)이다 — 마클1 회차2 검출 0건."""
        env = {key: value for key, value in self.ENV.items() if key != 'P3_UR5_ARM_PARAMS'}
        shown = run('env', env=env).stdout
        self.assertIn('config/ur5_arm.amr-combined.camera-receiver.yaml', shown)   # v1.0.1: #796 성공 회차 설정
        self.assertIn('P3_CAMERA_POUCHES    1', shown)          # 재범 9/29: 병원은 QR 을 반드시 찍는다
        self.assertIn('P3_CAMERA_TAGS       1', shown)
        shown = run('env', env={**env, 'P3_CAMERA_POUCHES': '0'}).stdout
        self.assertIn('config/ur5_arm.amr-combined.gripper.yaml', shown)
        self.assertIn('P3_CAMERA_TAGS       0', shown)
        self.assertIn('config/zones.hospital.yaml', shown)                # 참값 센서는 롤러 끝 적재(탁자 정착 아님)
        self.assertRegex(shown, r'P3_AMR_START +-8.995 4.686\n')
        self.assertRegex(shown, r'P3_HOSPITAL_RECEIVER_PRIM +\(없음\)\n')

    def test_hospital_camera_default_is_the_table_receiver_with_the_dock_at_load(self):
        """v1.0.1 기본 = 9/29 master02 카메라 배송 성공 설정(#796). 재범 9/29 B안: 충전 도크 = 적재 자리라
        출발 자리가 탁자 앞 적재 자리다(도크에서 이동 없이 집는다)."""
        out = run('cmds', env=self.ENV)
        self.assertEqual(0, out.returncode, out.stdout + out.stderr)
        lines = self.lines(out)
        self.assertIn('--amr-start -8.266 4.102 ', lines['stage'])
        self.assertIn('config/zones.hospital-receiver.yaml', lines['stage'])
        self.assertIn(' --hospital-receiver-prim /World/P3Base/Scene/Environment/hospital/SM_SideTable_02a_74',
                      lines['stage'])
        for part in ('belt_view_offset_m:=0 ', 'dispense_while_dispatching:=true', 'zones.hospital-receiver.yaml'):
            self.assertIn(part, lines['stack'])
        self.assertIn('routes.hospital-receiver.yaml', lines['nav'])
        zones = (SCRIPT.parents[1] / 'src' / 'rokey_p3_description' / 'config' /
                 'zones.hospital-receiver.yaml').read_text(encoding='utf-8')
        load = zones.split('  load:\n', 1)[1].split('\n  dock_2:', 1)[0]
        self.assertEqual(2, load.count('x: -8.26605892'))                 # load 와 dock_1 이 같은 자세
        self.assertEqual(2, load.count('y: 4.10165615'))
        blank = self.lines(run('cmds', env={**self.ENV, 'P3_HOSPITAL_RECEIVER_PRIM': ''}))
        self.assertNotIn('--hospital-receiver-prim', blank['stage'])

    def test_commands_for_the_hospital_run(self):
        with tempfile.TemporaryDirectory() as repo:
            out = run('cmds', env={**self.ENV, 'P3_SIM_SENSORS': '1'}, repo=repo)
            config = f'{repo}/src/rokey_p3_description/config'
            zones, routes = f'{config}/zones.hospital-receiver.yaml', f'{config}/routes.hospital-receiver.yaml'
            pool = f'{repo}/src/rokey_p3_orchestrator/config/order_pool.hospital.yaml'
            scene = f'{repo}/sim/scenes/hospital_navigationv1.usda'
            nav_map = f'{repo}/src/rokey_p3_navigation/config/maps/hospital.yaml'
        self.assertEqual(0, out.returncode, out.stdout + out.stderr)
        lines = self.lines(out)
        self.assertIn(f'sim/standalone/pharmacy_stage.py --preset hospital --workcell-layout /site/workcell.json '
                      f'--base-usd {scene} '
                      f'--amr-start -8.266 4.102 --amr --amr-combined /assets/ridgeback_ur5.usd --amr-lidar '
                      f'--zones-file {zones} --hospital-receiver-prim '
                      f'/World/P3Base/Scene/Environment/hospital/SM_SideTable_02a_74 --sim-sensors', lines['stage'])
        self.assertIn(f'--order-pool {pool}', lines['stage'])
        self.assertIn('--robot-usd /assets/M0609/Collected_m0609_gripper/m0609_gripper.usd', lines['stage'])
        self.assertNotIn('emptyworld-loop', lines['stage'])
        self.assertIn(f'navigation.launch.py zones_file:={zones} routes_file:={routes} map:={nav_map} '
                      'nav2_final_approach:=true localization:=odom', lines['nav'])
        self.assertNotIn('motion_backend:=waypoints', lines['nav'])
        for part in ('pharmacy_only:=false', 'use_stub_fleet:=false', 'use_stub_arm:=false', 'pick_notice:=false',
                     'use_ur5_arm:=true', 'ur5_arm_params_file:=/cfg/ur5_arm.yaml', 'deck_slots:=3',
                     'pouch_source:=camera', 'scan_tag_source:=camera', 'sim_cabinet:=true', 'belt_timeout_s:=60',
                     f'order_pool_file:={pool}', f'zones_file:={zones}'):
            self.assertIn(part, lines['stack'])
        self.assertIn(f'--zones-file {zones}', lines['web'])
        self.assertIn(f'--order-pool {pool}', lines['web'])
        self.assertIn(f'--map-file {nav_map}', lines['web'])
        # QR 판독 요약(웹 api.md §1.12): 약 이름·약통 로트를 스택과 같은 카탈로그·조제기 파일에서 푼다.
        self.assertIn(f'--catalog {repo}/src/rokey_p3_orchestrator/config/pharmacy_catalog.yaml', lines['web'])
        self.assertIn('--dispenser-file /cfg/', lines['web'])

    def test_hospital_waits_for_the_cylinder_cells_only(self):
        # 18칸이고 모듈 칸은 안 풀린다. 원통이 다 풀리면 간다(작전 9/23).
        out = run('env', env=self.ENV).stdout
        self.assertRegex(out, r'P3_ARM_READY +완료 종류: \.\*cylinder\n')
        self.assertNotIn('16/16', out)

    def test_hospital_gives_the_adapter_longer_for_a_dispense_answer(self):
        # 병원은 스테이지 틱이 길어 계약 기본 2 s 안에 답이 안 온다(9/23: 거부 ×3).
        self.assertIn('dispense_timeout_s:=30', self.lines(run('cmds', env=self.ENV))['stack'])

    def test_hospital_waits_longer_for_the_stage(self):
        # 병원은 충돌체를 굽느라 기동이 길다. 빈월드 기본 180 s 로는 기다리다 멈춘다(9/23).
        self.assertRegex(run('env', env=self.ENV).stdout, r'P3_STAGE_TIMEOUT_S +900\n')

    def test_site_values_can_be_given(self):
        out = run('cmds', env={**self.ENV, 'P3_AMR_START': '-8.0 4.2', 'P3_BELT_TIMEOUT_S': '75',
                               'P3_HOSPITAL_SCENE': '/site/scene.usda', 'P3_HOSPITAL_MAP': '/site/map.yaml'})
        self.assertEqual(0, out.returncode, out.stdout + out.stderr)
        lines = self.lines(out)
        self.assertIn('--base-usd /site/scene.usda --amr-start -8.0 4.2', lines['stage'])
        self.assertIn('map:=/site/map.yaml', lines['nav'])
        self.assertIn('belt_timeout_s:=75', lines['stack'])

    def test_hospital_needs_the_measured_workcell(self):
        # 빈월드 조제실(preset hospital-full)로 되돌아가지 않는다(재범 9/23). 워크셀 JSON 없이는 멈춘다.
        env = {k: v for k, v in self.ENV.items() if k != 'P3_WORKCELL_LAYOUT'}
        out = run('cmds', env=env)
        self.assertEqual(2, out.returncode, out.stdout + out.stderr)
        self.assertIn('P3_WORKCELL_LAYOUT', out.stdout)
        self.assertNotIn('hospital-full', run('cmds', env=self.ENV).stdout)

    def test_pouch_at_end_is_passed_to_the_stage(self):
        out = run('cmds', env={**self.ENV, 'P3_POUCH_AT_END': '1'})
        self.assertEqual(0, out.returncode, out.stdout + out.stderr)
        self.assertIn(' --pouch-at-end', self.lines(out)['stage'])
        self.assertRegex(run('env', env={**self.ENV, 'P3_POUCH_AT_END': '1'}).stdout, r'P3_POUCH_AT_END +1\n')

    def test_hospital_needs_the_combined_amr(self):
        out = run('cmds', env={k: v for k, v in self.ENV.items() if k != 'P3_AMR_COMBINED'})
        self.assertEqual(2, out.returncode, out.stdout + out.stderr)
        self.assertIn('P3_AMR_COMBINED', out.stdout)

    def test_hospital_waits_for_stage_ready_and_shows_its_values(self):
        shown = run('env', env=self.ENV).stdout
        self.assertRegex(shown, r'P3_STAGE_READY +stage ready\n')
        self.assertRegex(shown, r'P3_AMR_START +-8.266 4.102\n')
        self.assertRegex(shown, r'P3_BELT_TIMEOUT_S +60\n')
        self.assertNotIn('P3_AMR_START', run('env', env={**REQUIRED, 'P3_WORLD': 'emptyworld'}).stdout)

    def test_empty_world_keeps_its_belt_timeout(self):
        out = run('cmds', env={**REQUIRED, 'P3_WORLD': 'emptyworld', 'P3_UR5_ARM_PARAMS': '/cfg/ur5_arm.yaml'})
        self.assertEqual(0, out.returncode, out.stdout + out.stderr)
        self.assertNotIn('belt_timeout_s', out.stdout)
        self.assertNotIn('hospital-full', out.stdout)
        self.assertNotIn('zones.hospital', out.stdout)

    def test_up_stops_before_any_role_when_hospital_files_are_missing(self):
        with tempfile.TemporaryDirectory() as root:
            logs = Path(root) / 'not-created'
            result = run('up', env={**self.ENV, 'P3_LOG_DIR': str(logs)}, repo=root)
            self.assertEqual(2, result.returncode, result.stdout + result.stderr)
            self.assertIn('병원 씬이 없다', result.stdout)
            self.assertIn('병원 지도가 없다', result.stdout)
            self.assertFalse(logs.exists())

    def test_the_repository_ships_the_hospital_files(self):
        repo = Path(__file__).resolve().parents[1]
        for path in ('sim/scenes/hospital_navigationv1.usda',
                     'src/rokey_p3_description/config/zones.hospital.yaml',
                     'src/rokey_p3_description/config/routes.hospital.yaml',
                     'src/rokey_p3_orchestrator/config/order_pool.hospital.yaml',
                     'src/rokey_p3_navigation/config/maps/hospital.yaml'):
            self.assertTrue((repo / path).is_file(), path)
