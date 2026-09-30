"""UR5 `PickPouch` 의 `placement_check_enabled` 경로(계약 11.4 제안, 칸 안착 확인). 실제 안착은 L3(미실행)다.

#246 의 결함 후보("해제 뒤 시간 대기만으로 POUCH_LOADED")는 기본 경로에서 그대로 고정돼 있다. 여기서는 opt-in 경로에서
해제 확인(#291) 뒤 칸을 다시 보고, 해제 명령 뒤 stamp·같은 주문·칸 상자 안인 검출이 있어야만
LOADED/PLACED 를 내는지 본다.
안착을 확인하지 못하면 재시도를 부르지 않는 기존 outcome `dropped` 로 닫는다(trip_fsm 즉시 ABORT, 결정 16번 전 임시).
상자·거리·시한은 시험용 값이다(실제 값 미측정).
"""

import numpy as np
import test_reset_fence as rf
import test_ur5_pick_characterization as ch
import test_ur5_pick_gripper_state as gs

nodes = rf.nodes
ORDER = ch.ORDER
SLOT_BOX = (0.14, 0.11, 0.04)
CABINET_BOX = (0.30, 0.20, 0.10)
VIEW = 5                    # move_to_pose 순서: 접근·파지·들기·놓을 곳 위·놓기·관측·후퇴


class PlacementRig(gs.StateRig):
    def __init__(self, arm, monkeypatch):
        super().__init__(arm, monkeypatch)
        node = self.node
        for name in ('_confirm_placement', '_placement_view_pose', '_placement_config_problem',
                     '_placement_candidates'):
            setattr(node, name, getattr(arm.ArmNode, name).__get__(node))
        node._placement_enabled = True
        node._placement_standoff = 0.30
        node._placement_timeout = 2.0
        node._placement_slot_box = SLOT_BOX
        node._placement_cabinet_box = CABINET_BOX
        node._tool_frame = 'amr_1/tool0'
        node._hand_camera_frame = 'amr_1/hand_camera_optical'
        node.lookup_pose = lambda parent, child, stamp=None: np.eye(4)

    def show_after_release(self, *orders, position=(0.0, 0.0, 0.005)):
        """관측 자세에 도착하면 그 시각 stamp 로 검출을 낸다(해제 명령 뒤)."""
        self.on_move[VIEW] = lambda: self.pouches(*orders, position=position)


def rig(nodes, monkeypatch):
    arm, _ = nodes
    return PlacementRig(arm, monkeypatch), arm


def test_loaded_only_after_the_pouch_is_seen_inside_the_slot(nodes, monkeypatch):
    r, arm = rig(nodes, monkeypatch)
    r.ready()
    r.show_after_release(ORDER)
    handle, result = r.execute(ch._goal(arm, 'belt', 2))
    assert result.outcome == 'ok' and handle.state == 'succeeded'
    assert r.names() == [arm.Event.PICK_ATTEMPT, arm.Event.POUCH_PICKED, arm.Event.POUCH_LOADED]
    assert len(r.poses) == 7                                     # 관측 자세가 하나 늘었다
    # 관측 자세 = 놓을 곳 프레임(여기서는 단위행렬) +z 로 standoff 만큼 띄워 내려다본다.
    assert np.allclose(r.poses[VIEW][:3, 3], (0.0, 0.0, 0.30))


def test_no_detection_after_release_is_dropped_placement_unconfirmed(nodes, monkeypatch):
    r, arm = rig(nodes, monkeypatch)
    r.ready()                                                    # 해제 전 검출만 있다(ready 가 낸 것)
    start = r.clock
    handle, result = r.execute(ch._goal(arm, 'belt', 0))
    assert result.outcome == 'dropped' and handle.state == 'aborted'
    assert arm.Event.POUCH_LOADED not in r.names()
    assert r.clock - start < 60.0                               # placement_timeout_s 안에서 끝난다(액션 시한 전)


def test_detection_of_another_order_or_outside_the_slot_is_not_placement(nodes, monkeypatch):
    for orders, position in ((('ord-0002',), (0.0, 0.0, 0.005)), ((ORDER,), (0.2, 0.0, 0.005))):
        r, arm = rig(nodes, monkeypatch)
        r.ready()
        r.show_after_release(*orders, position=position)
        _handle, result = r.execute(ch._goal(arm, 'belt', 0))
        assert result.outcome == 'dropped', (orders, position)
        assert arm.Event.POUCH_LOADED not in r.names()


def test_missing_configuration_fails_closed_without_moving_to_view(nodes, monkeypatch):
    for attribute, value in (('_placement_slot_box', None), ('_placement_standoff', -1.0),
                             ('_placement_timeout', -1.0), ('_tool_frame', '')):
        r, arm = rig(nodes, monkeypatch)
        setattr(r.node, attribute, value)
        r.ready()
        r.show_after_release(ORDER)
        _handle, result = r.execute(ch._goal(arm, 'belt', 0))
        assert result.outcome == 'dropped', attribute
        assert len(r.poses) == 5, attribute                      # 관측 자세로 가지 않았다(실패는 후퇴 전에 돌아간다)
        assert arm.Event.POUCH_LOADED not in r.names()


def test_view_pose_ik_failure_is_unconfirmed(nodes, monkeypatch):
    r, arm = rig(nodes, monkeypatch)
    r.ready()
    r.ik = [True, True, True, True, True, False]                 # 여섯 번째 = 관측 자세
    _handle, result = r.execute(ch._goal(arm, 'belt', 0))
    assert result.outcome == 'dropped'


def test_cabinet_place_uses_the_cabinet_box_and_publishes_placed(nodes, monkeypatch):
    r, arm = rig(nodes, monkeypatch)
    r.base(True)
    r.pouches(ORDER)
    r.plant.tick()
    r.show_after_release(ORDER, position=(0.12, 0.0, 0.005))    # 칸 상자(0.14)는 넘고 보관함 상자(0.30) 안
    handle, result = r.execute(ch._goal(arm, 'deck', -1))
    assert result.outcome == 'ok'
    assert r.names()[-1] == arm.Event.POUCH_PLACED


def test_release_failure_still_comes_first(nodes, monkeypatch):
    # 해제 확인(#291)이 안 되면 칸을 보러 가지 않는다.
    r, arm = rig(nodes, monkeypatch)
    r.plant.opens = False
    r.ready()
    r.show_after_release(ORDER)
    _handle, result = r.execute(ch._goal(arm, 'belt', 0))
    assert result.outcome == 'timeout'
    assert len(r.poses) == 5 and arm.Event.POUCH_LOADED not in r.names()


def test_default_off_keeps_the_state_path(nodes, monkeypatch):
    r, arm = rig(nodes, monkeypatch)
    r.node._placement_enabled = False
    r.ready()
    _handle, result = r.execute(ch._goal(arm, 'belt', 0))
    assert result.outcome == 'ok' and len(r.poses) == 6          # 관측 자세 없이 #291 과 같다
    assert r.names()[-1] == arm.Event.POUCH_LOADED
