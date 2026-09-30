"""저장소로 옮긴 UR5 팔 현장값 파일(lap14–16, 카메라 판). ROS 없이 돈다.

두 파일은 카메라 판의 관측·파지 설정만 다르다. 나머지가 갈리면 "카메라 때문에 바뀐 것"과
"현장값이 바뀐 것"이 섞인다.
"""

import re
from pathlib import Path

import yaml

CONFIG = Path(__file__).resolve().parents[1] / 'config'


def _params(name):
    return yaml.safe_load((CONFIG / name).read_text(encoding='utf-8'))['/**']['ros__parameters']


def test_camera_file_differs_only_in_source_and_tool_frame():
    base = _params('ur5_arm.amr-combined.yaml')
    camera = _params('ur5_arm.amr-combined.camera.yaml')
    changed = {key for key in base.keys() | camera.keys() if base.get(key) != camera.get(key)}
    # tag_standoff_m: 인식표도 손 카메라로 읽는다(재범 9/29 병상 QR → 약 QR → 매칭). 0 이면 ScanTag 가 곧바로 실패.
    assert changed == {'pouch_source', 'tool_frame', 'tcp_offset_m', 'deck_view_standoff_m', 'refine_view_standoff_m',
                       'tag_standoff_m', 'belt_pick_lock_wrist'}
    assert camera['belt_pick_lock_wrist'] is True
    assert camera['tag_standoff_m'] > 0.0
    assert camera['pouch_source'] == 'camera'
    assert camera['tool_frame'] == 'amr_1/ur_arm_wrist_3_link'
    assert camera['tcp_offset_m'] == [0.0, 0.0, 0.1555]


def test_camera_tcp_offset_is_the_sim_gripper_suction_point():
    """팔의 흡착점과 스테이지 가상 흡착의 흡착점이 같은 값이어야 한다(한쪽만 바뀌면 조용히 빗나간다)."""
    source = (Path(__file__).resolve().parents[3] / 'sim' / 'standalone' / 'p3sim' / 'amr_base.py').read_text(
        encoding='utf-8')
    found = re.search(r'^GRIPPER_TCP_OFFSET = \(([^)]*)\)', source, re.M)
    assert found is not None
    offset = [float(v) for v in found.group(1).split(',')]
    assert offset == _params('ur5_arm.amr-combined.camera.yaml')['tcp_offset_m']


def test_files_carry_what_demo_v2_checks_for_the_combined_amr():
    for name in ('ur5_arm.amr-combined.yaml', 'ur5_arm.amr-combined.camera.yaml'):
        params = _params(name)
        assert all(joint.startswith('ur_arm_') for joint in params['joint_names'])
        assert len(params['joint_names']) == len(params['home_joint_positions']) == 6
        assert params['arm_base_frame_convention'] == 'base'
