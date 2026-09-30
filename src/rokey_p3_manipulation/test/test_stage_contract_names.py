"""팔이 스테이지 정의를 읽어 대조한다 — 세션 사이에서 "말로 정한" 이름들(#435).

받는 쪽이 보내는 쪽 정의를 읽는다. 여기 있는 값은 전부 두 벌로 존재하고, 둘이 어긋나도
**아무도 실패하지 않고 조용히 안 되는** 것들이다. 실습27a 의 QoS 사고가 같은 종류였다.

`sim/` 이 없는 설치 트리에서는 건너뛴다(선례: `test_clearance.py`).
"""

import os
import sys

import pytest
import test_reset_fence as rf

nodes = rf.nodes

HERE = os.path.dirname(__file__)
SIM = os.path.join(HERE, '..', '..', '..', 'sim', 'standalone')


@pytest.fixture
def stage():
    """`sim/standalone/p3sim` 을 임포트한다. 없으면 건너뛴다."""
    if not os.path.isdir(os.path.join(SIM, 'p3sim')):
        pytest.skip('sim/ 이 없는 설치 트리')
    sys.path.insert(0, SIM)
    try:
        from p3sim import sensors, ur5_cell
        yield sensors, ur5_cell
    finally:
        sys.path.remove(SIM)


def test_joint_names_match_the_stage(nodes, stage):
    """관절 이름이 어긋나면 스테이지가 명령을 통째로 버린다(`filter_joint_command`).

    팔은 `arm/joint_command` 를 계속 내고 UR5 는 서 있는다 — 실패로 닫히지 않는다.

    대조하는 것은 팔의 **기본값**이다. `joint_names` 는 파라미터라 기동에서 덮을 수 있으니,
    합본 자산(`ridgeback_ur5.usd`, 이름이 `ur_arm_*` 로 바뀐다)으로 가면 이 시험이 터진다.
    **그게 의도다** — 터지면 기본값과 기동 설정을 같이 고치라는 신호지, 팔이 못 따라간다는 뜻이 아니다.
    """
    arm, _ = nodes
    _sensors, ur5_cell = stage
    assert tuple(arm.kin.UR5_JOINT_NAMES) == tuple(ur5_cell.UR5_JOINTS)


def test_arm_base_frame_matches_the_stage_link_name(nodes, stage):
    """밑동 프레임 이름이 어긋나면 모든 TF 조회가 실패한다(놓을 곳·칸·검출 자세 전부).

    결정 47 로 정한 이름이라 계약 문서에는 없다 — 두 파일에만 있다.
    """
    arm, _ = nodes
    _sensors, ur5_cell = stage
    assert arm.default_arm_base_frame('amr_1') == f'amr_1/{ur5_cell.UR5_BASE_LINK}'


def test_deck_slot_frame_base_one_matches_the_stage_frames(nodes, stage):
    """`deck_slot_frame_base: 1` 의 근거. 스테이지는 1 부터, `target_slot` 은 0 부터다.

    어긋나면 한 칸 옆에 놓거나(번호가 있으면) `not_detected` 로 닫힌다(없으면).
    결정 28 이 정해지면 기본값이 바뀌므로, 그때 이 시험이 먼저 터져야 한다.
    """
    arm, _ = nodes
    sensors, _ur5_cell = stage
    count = 5
    node = type('Deck', (), {'deck_slot_frame': arm.ArmNode.deck_slot_frame})()
    node._deck_slot_prefix = 'amr_1/deck_slot_'
    node._deck_slot_base = 1
    assert [node.deck_slot_frame(slot) for slot in range(count)] == sensors.deck_frames('amr_1', count)
