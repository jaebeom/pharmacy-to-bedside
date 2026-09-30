"""UR5 `PickPouch` 실행(`_run_pick`·`_execute_pick`)의 현행 동작 고정 시험. 제품 코드는 바꾸지 않는다.

목적은 리팩터 안전망이다. 옳은 동작을 정의하지 않는다. 시험마다 첫 줄 주석에 셋 중 하나를 붙였다.
- [현행 고정]: 지금 동작을 그대로 고정한다. 계약이 확정돼도 바뀔 이유가 아직 없다.
- [계약 대기]: 지금 동작을 고정하지만 계약(#232 PR-A, INT-1)이 확정되면 기대값이 바뀔 항목이다.
- [결함 후보]: 지금 동작을 고정하지만 정적 검토에서 결함 후보로 본 동작이다. 이 시험이 통과한다고 옳은 동작이라는
  뜻이 아니다. 고치는 PR 에서 기대값을 뒤집는다.

`test_reset_fence.py` 의 대역 모듈(`nodes`)을 빌려 ROS 없이 돈다. ArmNode 메서드를 빌린 Harness 에서
IK(`move_to_pose`), TF(`frame_pose_in_base`), sim 시계(`sim_now`·`wait`), 이벤트 발행(`publish_event`),
홈 복귀 시작(`start_homing`)만 기록용 대역으로 바꾼다. 나머지(인터락, 검출 선택, 흡착 대기, 결과 조립)는 제품 코드다.
"""

import types

import numpy as np
import test_reset_fence as rf

nodes = rf.nodes

ORDER = 'ord-0001'
OTHER = 'ord-0002'
CABINET = 'bed_a1/cabinet'
OTHER_CABINET = 'bed_b1/cabinet'     # goal 의 zone_id 로 고르는 다른 침상(계약 10.1)
SLOT_PREFIX = 'amr_1/deck_slot_'

BORROWED = ('_accept_pick', '_execute_pick', '_run_pick', '_interlock', '_wait_for_pouch', '_pouch_pose_in_base',
            '_wait_for_hold', '_stopped_outcome', '_publish_feedback', '_end_goal', 'set_gripper', 'gripper_closed',
            'dropped', 'base_stopped', 'gripper_holding', 'belt_state', 'latest_pouches', 'epoch', 'set_goal_active',
            'goal_active', 'fenced', 'generation', 'fence_moved', 'stop_homing', 'homing', 'feedback_lost',
            'gripper_command_result', '_wait_for_command', '_wait_for_release', 'deck_slot_frame', 'cabinet_frame_for',
            '_source_slot', '_deck_grasp_from_frame', '_move_failed', 'move_via', '_view_plan',
            '_camera_view_pose', '_refine_view_pose', '_vision_grasp', '_deck_vision')


class _Time:
    """RclTime 대역. 시험의 stamp 는 sim 초(float)다."""

    def __init__(self, seconds):
        self.nanoseconds = int(round(seconds * 1e9))

    @classmethod
    def from_msg(cls, stamp):
        return cls(stamp)


class _Handle:
    def __init__(self, goal):
        self.request = goal
        self.is_cancel_requested = False
        self.state = None
        self.feedback = []

    def publish_feedback(self, feedback):
        self.feedback.append(feedback.phase)

    def succeed(self):
        self.state = 'succeeded'

    def abort(self):
        self.state = 'aborted'

    def canceled(self):
        self.state = 'canceled'


def _goal(arm, source='belt', slot=0, order=ORDER, zone_id=''):
    kind = arm.PickPouch.Goal.SOURCE_BELT if source == 'belt' else arm.PickPouch.Goal.SOURCE_DECK
    return types.SimpleNamespace(order_id=order, source=kind, target_slot=slot, zone_id=zone_id)


def _detections(stamp, *orders, position=(0.0, 0.0, 0.3)):
    x, y, z = position
    items = [types.SimpleNamespace(order_id=order,
                                   pose=types.SimpleNamespace(position=types.SimpleNamespace(x=x, y=y, z=z),
                                                              orientation=types.SimpleNamespace(x=0.0, y=0.0, z=0.0,
                                                                                                w=1.0)))
             for order in orders]
    return types.SimpleNamespace(header=types.SimpleNamespace(stamp=stamp, frame_id='amr_1/hand_camera_optical'),
                                 detections=items)


class Rig:
    """Harness 하나와 그 주변(가짜 흡착 plant, 스크립트 IK, 기록)."""

    def __init__(self, arm, monkeypatch):
        self.arm = arm
        monkeypatch.setattr(arm, 'RclTime', _Time)
        node = type('PickHarness', (), {n: getattr(arm.ArmNode, n) for n in BORROWED})()
        rf._common(node, arm, monkeypatch)
        node._joints = arm.Freshness(arm.STALE_JOINTS_S)
        node._holding = arm.Freshness(arm.STALE_STATUS_S)
        node._base_stopped = arm.Freshness(arm.STALE_STATUS_S)
        node._belt = arm.Freshness(arm.STALE_STATUS_S)
        node._pouches = None
        node._tag_read = None
        node._goal_generation = 0
        node._clock_watch = arm.ClockWatch(0.0)
        node._cabinet_frame = CABINET
        node._gripper_command_pub = None           # gripper_observation=bool(기본). state 경로는 별도 시험 파일
        node._placement_enabled = False             # placement_check_enabled=false(기본). 안착 확인은 별도 시험 파일
        node._deck_slot_prefix = SLOT_PREFIX
        node._deck_slot_base = 0                     # deck_slot_frame_base 기본값(지금 동작)
        node._deck_pick_from_frame = False           # deck_pick_from_frame 기본값(검출을 기다린다)
        node._pouch_height = 0.01                    # pouch_height_m 기본값
        node._pouch_source = arm.SOURCE_CAMERA       # pouch_source 기본값
        node._belt_view_frame = ''                   # belt_view_frame 기본값(관측 자세 끔)
        node._belt_view_standoff = 0.0
        node._belt_view_offset = 0.0
        node._deck_view_standoff = 0.0              # deck_view_standoff_m 기본값(끔)
        node._refine_standoff = 0.0                 # refine_view_standoff_m 기본값(끔)
        node._tool_frame = ''
        node._hand_camera_frame = 'amr_1/hand_camera_optical'
        node._pick_timeout = 60.0
        node._detection_timeout = 5.0
        node._detection_max_age = 1.0
        node._approach_height = 0.10
        node._grasp_z_offset = 0.0
        node._place_z_offset = 0.0
        node._grasp_settle = 0.5
        node._grasp_hold_timeout = 2.0     # grasp_hold_timeout_s 기본값
        node._release_settle = 0.3

        self.node = node
        self.clock = 100.0
        self.waits = []            # (sim 초, 그 직전까지 낸 그리퍼 명령 수)
        self.events = []           # (name, order_id, detail)
        self.homing_started = 0
        self.frames = {CABINET: np.eye(4), OTHER_CABINET: np.eye(4)}
        for slot in range(5):
            self.frames[f'{SLOT_PREFIX}{slot}'] = np.eye(4)
        self.frames['amr_1/hand_camera_optical'] = np.eye(4)
        self.ik = []               # move_to_pose 결과 스크립트. 비면 True
        self.poses = []            # move_to_pose 에 온 목표
        self.tool_flags = []       # 그 목표가 공구 자세(관측)인가, 흡착점 자세(파지·놓기)인가
        self.on_move = {}          # move_to_pose 호출 번호(0부터) → 호출 전에 할 일
        self.plant_follows = True  # 흡착 plant 가 그리퍼 명령을 따르나
        self.plant_on_close = True  # 닫으면 holding 이 무엇이 되나

        node.sim_now = lambda: self.clock
        node.wait = self._wait
        node.move_to_pose = self._move_to_pose
        node.frame_pose_in_base = lambda frame_id, stamp=None: self.frames.get(frame_id)
        node.publish_event = self._publish_event
        node.start_homing = self._start_homing
        node.gripper = rf._Pub(self._plant)
        node._gripper_pub = node.gripper

    # 대역 ---------------------------------------------------------------

    def _wait(self, sim_seconds, cancelled=None):
        self.waits.append((sim_seconds, len(self.node.gripper.sent)))
        if cancelled is not None and cancelled():
            return False
        self.clock += sim_seconds
        return not (cancelled is not None and cancelled())

    def _move_to_pose(self, target, cancelled=None, tool=False):
        index = len(self.poses)
        self.poses.append(np.array(target))
        self.tool_flags.append(tool)
        action = self.on_move.get(index)
        if action is not None:
            action()
        if cancelled is not None and cancelled():
            return self.arm.MoveResult(False)
        scripted = self.ik.pop(0) if self.ik else True
        # `ik` 스크립트에 `MoveResult` 를 넣으면 도달 실패(timeout)를 실제 노드처럼 흉내 낸다.
        return scripted if isinstance(scripted, self.arm.MoveResult) else self.arm.MoveResult(scripted)

    def _publish_event(self, name, request_id='', order_id='', detail=''):
        self.events.append((name, order_id, detail))

    def _start_homing(self):
        self.homing_started += 1

    def _plant(self, message):
        if not self.plant_follows:
            return
        self.hold(self.plant_on_close if message.data else False)

    # 입력 ---------------------------------------------------------------

    def hold(self, value):
        with self.node._lock:
            self.node._holding.update(value)

    def base(self, value=True):
        with self.node._lock:
            self.node._base_stopped.update(value)

    def belt(self, at_end=True, order=ORDER):
        with self.node._lock:
            self.node._belt.update(types.SimpleNamespace(at_end=at_end, order_id=order, occupied=True))

    def pouches(self, *orders, stamp=None, position=(0.0, 0.0, 0.3)):
        self.node._pouches = _detections(self.clock if stamp is None else stamp, *orders, position=position)

    def ready_for_belt_pick(self):
        self.base(True)
        self.belt(True, ORDER)
        self.hold(False)
        self.pouches(ORDER)

    # 실행 ---------------------------------------------------------------

    def execute(self, goal):
        handle = _Handle(goal)
        result = self.node._execute_pick(handle)
        return handle, result

    def names(self):
        return [name for name, _order, _detail in self.events]

    def gripper_commands(self):
        return [bool(message.data) for message in self.node.gripper.sent]


def rig(nodes, monkeypatch):
    arm, _ = nodes
    return Rig(arm, monkeypatch), arm


# 정상 경로 -------------------------------------------------------------------

def test_belt_pick_ok_publishes_attempt_picked_loaded_in_order_then_starts_homing(nodes, monkeypatch):
    # [현행 고정] 이벤트 순서 PICK_ATTEMPT → POUCH_PICKED → POUCH_LOADED.
    # 스텁·L2(test_stub_loop, test_lap_order)와 같은 순서다.
    r, arm = rig(nodes, monkeypatch)
    r.ready_for_belt_pick()
    handle, result = r.execute(_goal(arm, 'belt', 2))
    assert result.success is True and result.outcome == 'ok'
    assert handle.state == 'succeeded'
    assert r.names() == [arm.Event.PICK_ATTEMPT, arm.Event.POUCH_PICKED, arm.Event.POUCH_LOADED]
    assert r.events[0] == (arm.Event.PICK_ATTEMPT, ORDER, 'belt')
    assert r.events[2] == (arm.Event.POUCH_LOADED, ORDER, f'{SLOT_PREFIX}2')
    assert handle.feedback == ['detect', 'approach', 'grasp', 'transfer', 'place']
    assert r.gripper_commands() == [False, True, False]
    # 접근 → 파지 → 들어 올리기 → 놓을 곳 위 → 놓기 → 후퇴. 여섯 번 IK 목표를 낸다.
    assert len(r.poses) == 6
    assert r.homing_started == 1                                 # 결과 뒤 홈 복귀는 _execute_pick finally 가 시작한다
    assert not r.node.goal_active()


def test_deck_pick_places_on_the_fixed_cabinet_frame_parameter(nodes, monkeypatch):
    # goal 의 zone_id 가 비면 지금처럼 노드 파라미터 cabinet_frame 을 쓴다(계약 10.1 의 기본).
    # 침상이 하나인 빈월드·조제실 회차가 그대로 돌게 하려는 것이다.
    r, arm = rig(nodes, monkeypatch)
    r.base(True)
    r.hold(False)
    r.pouches(OTHER, ORDER)                                     # 상판의 여러 봉투 중 QR 이 같은 것을 고른다
    handle, result = r.execute(_goal(arm, 'deck', -1))
    assert result.outcome == 'ok'
    assert r.events[0] == (arm.Event.PICK_ATTEMPT, ORDER, 'deck')
    assert r.events[-1] == (arm.Event.POUCH_PLACED, ORDER, CABINET)
    assert r.homing_started == 1


# 결함 후보 -------------------------------------------------------------------

def test_loaded_follows_a_fixed_release_wait_without_observing_the_release(nodes, monkeypatch):
    # [결함 후보] 해제 명령 뒤 release_settle_s(0.3 s) 를 기다리기만 하고 POUCH_LOADED 와 ok 를 낸다.
    # holding 이 true 로 남아도(해제 실패), 칸 안착을 보지 않아도 성공이다.
    # 계약 확정 뒤 기대: 해제 관측 + 칸 안착 관측 없이는 POUCH_LOADED 없음, outcome placement_unconfirmed.
    r, arm = rig(nodes, monkeypatch)
    r.ready_for_belt_pick()
    r.on_move[4] = lambda: setattr(r, 'plant_follows', False)   # 놓기 자세부터 plant 가 해제 명령을 무시한다
    handle, result = r.execute(_goal(arm, 'belt', 0))
    assert r.node.gripper_holding() is True                      # 해제는 안 됐다
    assert result.outcome == 'ok' and handle.state == 'succeeded'
    assert r.names()[-1] == arm.Event.POUCH_LOADED
    # 마지막 그리퍼 명령(해제) 직후의 대기가 0.3 s 다. 그 뒤에 LOADED 가 나간다.
    release_waits = [seconds for seconds, sent in r.waits if sent == 3]
    assert release_waits == [0.3]


def test_retreat_ik_failure_still_returns_ok_and_starts_homing(nodes, monkeypatch):
    # [결함 후보] 놓은 뒤 후퇴 IK 가 실패해도 ok 로 닫고, finally 가 홈 복귀를 시작한다(검증 안 된 관절 직선 경로).
    # 계약 확정 뒤 기대: 자동 홈 금지, at_home=false 유지, detail 에 후퇴 실패 기록(opt-in 파라미터로 시작).
    r, arm = rig(nodes, monkeypatch)
    r.ready_for_belt_pick()
    r.ik = [True, True, True, True, True, False]                 # 여섯 번째 = 후퇴
    handle, result = r.execute(_goal(arm, 'belt', 0))
    assert result.outcome == 'ok' and handle.state == 'succeeded'
    assert r.names()[-1] == arm.Event.POUCH_LOADED
    assert r.homing_started == 1


def test_holding_true_from_before_the_close_command_passes_the_grasp_check(nodes, monkeypatch):
    # [결함 후보] 흡착 명령 전부터 holding=true 였고 plant 가 명령에 반응하지 않아도 _wait_for_hold 를 통과한다.
    # Bool 에는 명령 상관(seq)이 없어 이전 값과 이번 파지를 가를 수 없다(T05, VA V05).
    # 계약 확정 뒤 기대: last_applied_command_seq ≥ 이번 close seq 인 HELD 만 파지로 인정.
    r, arm = rig(nodes, monkeypatch)
    r.ready_for_belt_pick()
    r.hold(True)
    r.plant_follows = False
    _handle, result = r.execute(_goal(arm, 'belt', 0))
    assert arm.Event.POUCH_PICKED in r.names()
    assert result.outcome == 'ok'


def test_holding_going_unknown_mid_transfer_is_not_treated_as_a_drop(nodes, monkeypatch):
    # [결함 후보] 이송 중 holding heartbeat 가 끊겨 unknown(None)이 되면 dropped() 는 False 라 이송을 계속한다.
    # 계약 확정 뒤 기대: 이송 중 UNKNOWN 이면 즉시 멈추고 해제·홈 없이 feedback_lost(또는 HOLD) (VA V06).
    r, arm = rig(nodes, monkeypatch)
    r.ready_for_belt_pick()

    def lose_heartbeat():
        r.plant_follows = False
        with r.node._lock:
            r.node._holding.clear()

    r.on_move[3] = lose_heartbeat                                # 놓을 곳 위로 가는 중
    _handle, result = r.execute(_goal(arm, 'belt', 0))
    assert r.node.gripper_holding() is None
    assert result.outcome == 'ok'
    assert r.names()[-1] == arm.Event.POUCH_LOADED


def test_drop_is_seen_only_at_segment_boundaries(nodes, monkeypatch):
    # [현행 고정] holding 이 false 가 되면 다음 구간 경계(들어 올린 뒤·이송 뒤·놓기 직전)에서 dropped 로 닫는다.
    # 구간 안(move_to 도중)에서는 보지 않는다. 이 시험은 경계 판정만 고정한다.
    r, arm = rig(nodes, monkeypatch)
    r.ready_for_belt_pick()
    r.on_move[3] = lambda: r.hold(False)                         # 놓을 곳 위로 가는 중에 떨어졌다
    handle, result = r.execute(_goal(arm, 'belt', 0))
    assert result.outcome == 'dropped' and handle.state == 'aborted'
    assert r.names() == [arm.Event.PICK_ATTEMPT, arm.Event.POUCH_PICKED]
    assert len(r.poses) == 4
    assert r.homing_started == 1                                 # [계약 대기] custody 불명에서의 홈 복귀는 바뀔 항목


# 실패 경로 -------------------------------------------------------------------

def test_holding_false_after_close_is_grasp_failed(nodes, monkeypatch):
    # [현행 고정] 흡착 뒤 holding=false 면 grasp_failed. POUCH_PICKED 는 없다.
    r, arm = rig(nodes, monkeypatch)
    r.ready_for_belt_pick()
    r.plant_on_close = False
    handle, result = r.execute(_goal(arm, 'belt', 0))
    assert result.outcome == 'grasp_failed' and result.success is False
    assert handle.state == 'aborted'
    assert r.names() == [arm.Event.PICK_ATTEMPT]
    assert r.homing_started == 1                                 # [계약 대기] 실패 뒤 무조건 홈 복귀


def test_interlock_rejections_send_no_motion_and_no_event(nodes, monkeypatch):
    # [현행 고정] 계약 5절 guard. unknown 은 허가가 아니다. at_end 하나가 벨트·봉투 정지를 같이 말한다.
    # [계약 대기] at_end 를 벨트 운동·봉투 운동으로 나누는 관측이 생기면 사례가 는다(VA V01).
    cases = {
        'base unknown': lambda r: (r.belt(True, ORDER),),
        'base moving': lambda r: (r.base(False), r.belt(True, ORDER)),
        'belt unknown': lambda r: (r.base(True),),
        'not at end': lambda r: (r.base(True), r.belt(False, ORDER)),
        'other order on belt': lambda r: (r.base(True), r.belt(True, OTHER)),
    }
    for name, arrange in cases.items():
        r, arm = rig(nodes, monkeypatch)
        arrange(r)
        handle, result = r.execute(_goal(arm, 'belt', 0))
        assert result.outcome == 'rejected_interlock', name
        assert handle.state == 'aborted', name
        assert r.events == [] and r.poses == [] and r.gripper_commands() == [], name
        assert r.homing_started == 1, name                       # 움직이지 않았어도 finally 는 홈 복귀를 시작한다


def test_missing_place_frame_closes_as_not_detected_before_any_event(nodes, monkeypatch):
    # [현행 고정] 놓을 곳 TF 가 없으면 검출 전에 not_detected. PICK_ATTEMPT 도 없다.
    r, arm = rig(nodes, monkeypatch)
    r.ready_for_belt_pick()
    del r.frames[f'{SLOT_PREFIX}3']
    _handle, result = r.execute(_goal(arm, 'belt', 3))
    assert result.outcome == 'not_detected'
    assert r.events == [] and r.poses == []


def test_detection_outcomes(nodes, monkeypatch):
    # [현행 고정] 검출 선택. 맞는 QR 없음 → qr_mismatch, 검출 없음·오래된 검출·거리 0 → not_detected.
    # 모두 PICK_ATTEMPT 는 낸 뒤이고 팔은 움직이지 않는다. 대기 상한은 detection_timeout_s(sim).
    cases = {
        'qr mismatch': (lambda r: r.pouches(OTHER), 'qr_mismatch'),
        'no message': (lambda r: None, 'not_detected'),
        'no qr read': (lambda r: r.pouches(''), 'not_detected'),
        'stale message': (lambda r: r.pouches(ORDER, stamp=r.clock - 1.5), 'not_detected'),
        'zero pose': (lambda r: r.pouches(ORDER, position=(0.0, 0.0, 0.0)), 'not_detected'),
    }
    for name, (arrange, outcome) in cases.items():
        r, arm = rig(nodes, monkeypatch)
        r.base(True)
        r.belt(True, ORDER)
        r.hold(False)
        arrange(r)
        start = r.clock
        _handle, result = r.execute(_goal(arm, 'belt', 0))
        assert result.outcome == outcome, name
        assert r.names() == [arm.Event.PICK_ATTEMPT], name
        assert r.poses == [] and r.gripper_commands() == [], name
        assert 5.0 <= r.clock - start < 5.2, name


def test_detection_within_max_age_before_the_request_is_accepted(nodes, monkeypatch):
    # [현행 고정] 요청 시각보다 detection_max_age_s(1.0 s) 이내로 오래된 검출은 쓴다(계약 2.4절).
    # [계약 대기] "벨트 정지 뒤 새 QR·pose" 조건이 들어오면 정지 시각 이전 검출은 거부로 바뀐다.
    r, arm = rig(nodes, monkeypatch)
    r.base(True)
    r.belt(True, ORDER)
    r.hold(False)
    r.pouches(ORDER, stamp=r.clock - 0.9)
    _handle, result = r.execute(_goal(arm, 'belt', 0))
    assert result.outcome == 'ok'


def test_cancel_is_reported_as_timeout_and_does_not_start_homing(nodes, monkeypatch):
    # [계약 대기] 계약 outcome 목록에 취소가 없어 timeout 으로 싣는다. goal 상태는 canceled.
    # 계약에 cancelled 가 들어오면 이 값이 바뀐다. orchestrator 는 지금 timeout 을 재시도 경로로 보낸다.
    r, arm = rig(nodes, monkeypatch)
    r.base(True)
    r.belt(True, ORDER)
    r.hold(False)
    handle = _Handle(_goal(arm, 'belt', 0))
    r.on_move[0] = lambda: setattr(handle, 'is_cancel_requested', True)
    r.pouches(ORDER)
    result = r.node._execute_pick(handle)
    assert result.outcome == 'timeout' and result.success is False
    assert handle.state == 'canceled'
    assert r.homing_started == 0
    assert arm.Event.POUCH_PICKED not in r.names()


def test_blocked_move_closes_as_timeout_not_grasp_failed(nodes, monkeypatch):
    # [실습29b] 경로가 벽에 막혀 팔이 절반만 갔다. 예전에는 개루프라 "이동 성공" 으로 넘어가
    # 흡착을 켜고 grasp_failed 로 닫혔다 — 움직임 실패가 흡착 실패로 보고된 것이다.
    # 이제는 도달 실패를 제 이름(timeout)으로 닫고, detail 이 어느 관절이 얼마나 남았는지 말한다.
    r, arm = rig(nodes, monkeypatch)
    r.base(True)
    r.belt(True, ORDER)
    r.pouches(ORDER)
    stuck = '이동 미도달: shoulder_pan_joint 목표 -4.0725 실제 -2.7577 (남음 1.3148 rad)'
    r.ik = [arm.MoveResult(False, arm.perm.OUTCOME_TIMEOUT, stuck)]
    lines = []
    r.node.get_logger = lambda: types.SimpleNamespace(
        info=lines.append, warn=lines.append, error=lines.append, debug=lines.append)
    _handle, result = r.execute(_goal(arm, 'belt', 0))
    assert result.outcome == 'timeout'
    # 결과에는 detail 칸이 없다(계약 액션). 사람이 읽는 줄에 남아야 한 줄로 갈린다.
    assert any(stuck in line for line in lines), lines
    # 도달하지 못했으면 흡착을 켜지 않는다.
    assert True not in [msg.data for msg in r.node.gripper.sent]
    assert arm.Event.POUCH_PICKED not in r.names()


def test_failed_grasp_turns_the_suction_command_back_off(nodes, monkeypatch):
    # [실습27b·29b] 못 잡았는데 흡착 명령이 on 으로 남아 스테이지가 60 s·1,666줄 계속 시도했다.
    # 잡은 뒤의 실패 경로에서는 놓지 않는다(들고 복귀가 낫다) — 여기는 잡은 것이 없는 자리다.
    r, arm = rig(nodes, monkeypatch)
    r.base(True)
    r.belt(True, ORDER)
    r.pouches(ORDER)
    r.plant_on_close = False            # 흡착을 켜도 붙지 않는다(29b 의 suction miss)
    _handle, result = r.execute(_goal(arm, 'belt', 0))
    assert result.outcome == 'grasp_failed'
    assert [msg.data for msg in r.node.gripper.sent][-1] is False


# goal 수락 -------------------------------------------------------------------

def test_deck_slot_frame_name_uses_the_goal_index_as_is(nodes, monkeypatch):
    # [결함 후보] 놓을 곳 프레임 이름은 goal 의 칸 번호를 그대로 붙인다(0부터). Isaac 은 deck_slot_1..N 로 낸다
    # (sim/standalone/p3sim/sensors.py deck_frames, i+1). 계약 3절은 N 의 시작을 적지 않았다.
    # 그래서 첫 픽(target_slot=0)은 deck_slot_0 을 찾고 TF 가 없어 팔이 움직이기 전에 not_detected 로 닫힌다.
    # 계약 결정 뒤 기대값을 뒤집는다(+1 로 찾거나, TF 이름을 0부터로 바꾸거나).
    r, arm = rig(nodes, monkeypatch)
    r.frames = {name: pose for name, pose in r.frames.items() if not name.startswith(SLOT_PREFIX)}
    for slot in range(1, 6):                                     # Isaac 이 내는 이름: deck_slot_1..5
        r.frames[f'{SLOT_PREFIX}{slot}'] = np.eye(4)
    r.ready_for_belt_pick()
    handle, result = r.execute(_goal(arm, 'belt', 0))
    assert result.outcome == 'not_detected' and handle.state == 'aborted'
    assert r.poses == [] and r.gripper_commands() == []           # 움직이지 않는다
    assert r.events == []                                         # PICK_ATTEMPT 도 없다
    # 같은 봉투를 1번 칸으로 보내면(= goal 번호를 +1 한 것과 같다) 그대로 돈다.
    r2, _arm = rig(nodes, monkeypatch)
    r2.frames = dict(r.frames)
    r2.ready_for_belt_pick()
    _handle2, result2 = r2.execute(_goal(arm, 'belt', 1))
    assert result2.outcome == 'ok'
    assert r2.events[-1] == (arm.Event.POUCH_LOADED, ORDER, f'{SLOT_PREFIX}1')


def test_accept_pick_checks_only_the_goal_shape(nodes, monkeypatch):
    # [현행 고정] 수락은 형식만 본다. 인터락은 실행에서 본다(거부하면 outcome 을 못 돌려주기 때문).
    r, arm = rig(nodes, monkeypatch)
    accept, reject = arm.GoalResponse.ACCEPT, arm.GoalResponse.REJECT
    assert r.node._accept_pick(_goal(arm, 'belt', 0)) == accept      # base·belt 가 unknown 이어도 수락
    assert r.node._accept_pick(_goal(arm, 'belt', 0, order='')) == reject
    assert r.node._accept_pick(_goal(arm, 'belt', -1)) == reject     # 벨트 픽은 상판 칸 번호가 있어야 한다
    assert r.node._accept_pick(_goal(arm, 'deck', -1)) == accept
    r.node._cabinet_frame = ''
    # zone_id 와 cabinet_frame 이 둘 다 비면 거부(계약 10.1)
    assert r.node._accept_pick(_goal(arm, 'deck', -1)) == reject
    r.node.set_goal_active(True)
    assert r.node._accept_pick(_goal(arm, 'belt', 0)) == reject


# 칸 프레임 번호(deck_slot_frame_base) ------------------------------------------------

def test_slot_frame_base_defaults_to_zero_so_the_frame_name_is_unchanged(nodes, monkeypatch):
    """[현행 고정] 기본값 0 에서는 `target_slot` 을 그대로 쓴다. #332 가 고정한 동작이다."""
    r, arm = rig(nodes, monkeypatch)
    assert r.node._deck_slot_base == 0
    assert r.node.deck_slot_frame(0) == f'{SLOT_PREFIX}0'
    assert r.node.deck_slot_frame(4) == f'{SLOT_PREFIX}4'


def test_slot_frame_base_one_maps_slot_zero_to_the_first_stage_frame(nodes, monkeypatch):
    """Isaac 스테이지는 `deck_slot_1..N` 를 낸다. base 1 이 0 기반 `target_slot` 을 거기에 맞춘다."""
    r, arm = rig(nodes, monkeypatch)
    r.node._deck_slot_base = 1
    assert r.node.deck_slot_frame(0) == f'{SLOT_PREFIX}1'
    assert r.node.deck_slot_frame(4) == f'{SLOT_PREFIX}5'


def test_slot_frame_base_one_places_into_the_shifted_frame(nodes, monkeypatch):
    """base 1 에서 `target_slot=0` 픽이 `deck_slot_1` 에 놓고 그 이름으로 POUCH_LOADED 를 낸다."""
    r, arm = rig(nodes, monkeypatch)
    r.node._deck_slot_base = 1
    r.ready_for_belt_pick()
    handle, result = r.execute(_goal(arm, 'belt', 0))
    assert result.success is True and result.outcome == 'ok'
    assert r.events[-1] == (arm.Event.POUCH_LOADED, ORDER, f'{SLOT_PREFIX}1')


def test_slot_frame_base_one_refuses_the_last_slot_when_the_stage_has_no_such_frame(nodes, monkeypatch):
    """base 1 이면 마지막 칸이 범위를 넘을 수 있다. 조용히 다른 칸에 놓지 않고 TF 없음으로 거부한다."""
    r, arm = rig(nodes, monkeypatch)
    r.node._deck_slot_base = 1
    r.ready_for_belt_pick()
    _handle, result = r.execute(_goal(arm, 'belt', 4))    # → deck_slot_5, 픽스처에는 0..4 뿐이다
    assert result.success is False and result.outcome == 'not_detected'
    assert r.events == [] and r.poses == []               # 조용히 다른 칸에 놓지 않는다


def test_slot_frame_base_does_not_touch_the_cabinet_path(nodes, monkeypatch):
    """target_slot 이 음수면 보관함 프레임이다. base 는 거기 끼어들지 않는다."""
    r, arm = rig(nodes, monkeypatch)
    r.node._deck_slot_base = 1
    r.ready_for_belt_pick()
    handle, result = r.execute(_goal(arm, 'belt', -1))
    assert result.success is True
    assert r.events[-1] == (arm.Event.POUCH_PLACED, ORDER, CABINET)


# 칸 TF 로 집기(deck_pick_from_frame) -------------------------------------------------

def test_deck_pick_from_frame_is_off_by_default_so_the_detection_is_still_required(nodes, monkeypatch):
    """[현행 고정] 기본 꺼짐. 상판에서 집을 때도 검출이 없으면 not_detected 다."""
    r, arm = rig(nodes, monkeypatch)
    assert r.node._deck_pick_from_frame is False
    r.base(True)
    r.hold(False)                                        # 검출을 주지 않는다
    _handle, result = r.execute(_goal(arm, 'deck', -1))
    assert result.success is False and result.outcome == 'not_detected'


def test_deck_pick_from_frame_does_not_wait_for_a_detection(nodes, monkeypatch):
    """켜면 검출 없이도 상판에서 집는다. v0 전달은 YOLO·봉투 QR 이 아직 없어 검출을 낼 주체가 없다."""
    r, arm = rig(nodes, monkeypatch)
    r.node._deck_pick_from_frame = True
    r.base(True)
    r.hold(False)                                        # 검출을 주지 않는다
    handle, result = r.execute(_goal(arm, 'deck', -1))
    assert result.success is True and result.outcome == 'ok'
    assert r.events[-1] == (arm.Event.POUCH_PLACED, ORDER, CABINET)


def test_deck_pick_from_frame_grasps_one_pouch_height_above_the_slot_origin(nodes, monkeypatch):
    """목표 z = 칸 원점 + `pouch_height_m`. 봉투가 칸 바닥 윗면에 얹혀 있기 때문이다.

    놓을 때 쓰는 `place_z_offset_m`(= rest_gap + 봉투 두께)과 같은 기하를 되쓴다.
    """
    r, arm = rig(nodes, monkeypatch)
    r.node._deck_pick_from_frame = True
    r.node._pouch_height = 0.01
    slot = np.eye(4)
    slot[:3, 3] = [0.30, -0.10, 0.50]                    # 칸 0 원점을 옮겨 둔다
    r.frames[f'{SLOT_PREFIX}0'] = slot
    r.base(True)
    r.hold(False)
    _handle, result = r.execute(_goal(arm, 'deck', -1))
    assert result.success is True
    # 첫 IK 목표는 접근(파지 위 approach_height), 둘째가 파지다.
    grasp = r.poses[1]
    assert abs(grasp[0, 3] - 0.30) < 1e-9 and abs(grasp[1, 3] + 0.10) < 1e-9
    assert abs(grasp[2, 3] - 0.51) < 1e-9                # 0.50 + 봉투 두께 0.01


def test_deck_pick_from_frame_leaves_the_belt_path_on_the_detection(nodes, monkeypatch):
    """벨트에서 집는 것은 그대로 검출을 쓴다. 벨트 끝 봉투는 TF 가 없다."""
    r, arm = rig(nodes, monkeypatch)
    r.node._deck_pick_from_frame = True
    r.base(True)
    r.belt(True, ORDER)
    r.hold(False)                                        # 검출을 주지 않는다
    _handle, result = r.execute(_goal(arm, 'belt', 2))
    assert result.success is False and result.outcome == 'not_detected'


def test_deck_pick_from_frame_refuses_when_the_source_slot_has_no_frame(nodes, monkeypatch):
    """집을 칸 TF 가 없으면 조용히 엉뚱한 곳을 집지 않고 not_detected 로 닫는다."""
    r, arm = rig(nodes, monkeypatch)
    r.node._deck_pick_from_frame = True
    del r.frames[f'{SLOT_PREFIX}0']
    r.base(True)
    r.hold(False)
    _handle, result = r.execute(_goal(arm, 'deck', -1))
    assert result.success is False and result.outcome == 'not_detected'
    assert r.poses == []


def test_source_slot_is_zero_until_the_contract_carries_it(nodes, monkeypatch):
    """[계약 대기] `PickPouch` 에 집을 칸을 담을 필드가 없다(결정 44). v0 한 바퀴는 칸 0 이다."""
    r, arm = rig(nodes, monkeypatch)
    assert r.node._source_slot(_goal(arm, 'deck', -1)) == 0
    assert r.node._source_slot(_goal(arm, 'deck', 3)) == 0      # target_slot 은 놓을 곳이라 쓰지 않는다


def test_late_suction_is_not_a_failed_grasp(nodes, monkeypatch):
    # [실습13] 팔이 430.133 에 흡착을 켰는데 스테이지는 430.683 에야 붙였다. 그 사이
    # grasp_settle 0.5 s 가 먼저 끝나 holding=false 한 번을 보고 닫혔다 — 0.05 s 모자랐다.
    # `holding=false` 는 "못 붙였다" 가 아니라 "아직 안 붙었다" 일 수 있다.
    r, arm = rig(nodes, monkeypatch)
    r.base(True)
    r.belt(True, ORDER)
    r.pouches(ORDER)
    r.plant_follows = False                 # 그리퍼 명령으로는 안 붙는다
    r.hold(False)
    grasp_at = [None]
    plain_wait = r._wait

    def attach_late(seconds, stop=None):
        """흡착 명령 뒤 sim 으로 0.55 s 가 지나면 그때서야 붙는다(lap13 의 지연)."""
        out = plain_wait(seconds, stop)
        if grasp_at[0] is None and True in [m.data for m in r.node.gripper.sent]:
            grasp_at[0] = r.clock
        if grasp_at[0] is not None and r.clock >= grasp_at[0] + 0.55:
            r.hold(True)
        return out

    r.node.wait = attach_late
    _handle, result = r.execute(_goal(arm, 'belt', 0))
    assert result.outcome == 'ok', result.outcome
    assert arm.Event.POUCH_PICKED in r.names()


def test_grasp_failure_still_closes_after_the_hold_timeout(nodes, monkeypatch):
    # 끝내 안 붙으면 여전히 grasp_failed 다 — 기다리는 시간이 늘 뿐 판정이 약해지지 않는다.
    r, arm = rig(nodes, monkeypatch)
    r.base(True)
    r.belt(True, ORDER)
    r.pouches(ORDER)
    r.plant_on_close = False                # 켜도 안 붙는다
    _handle, result = r.execute(_goal(arm, 'belt', 0))
    assert result.outcome == 'grasp_failed'
    assert [msg.data for msg in r.node.gripper.sent][-1] is False


# ---- 벨트 관측 자세(opt-in) ------------------------------------------------

BELT_END = 'pharmacy/belt_end'


def _belt_view_rig(nodes, monkeypatch, standoff=0.25):
    r, arm = rig(nodes, monkeypatch)
    r.node._belt_view_frame = BELT_END
    r.node._belt_view_standoff = standoff
    r.node._tool_frame = 'amr_1/tool0'
    r.node.lookup_pose = lambda parent, child, stamp=None: np.eye(4)
    belt_end = np.eye(4)
    belt_end[:3, 3] = (0.5, 0.0, 0.1)
    r.frames[BELT_END] = belt_end
    # 관측 자세의 카메라: 벨트 끝 위 0.3 m 에서 아래(-z)를 본다. 검출은 평면(벨트 끝 + 봉투 두께)과의 교차로 놓인다.
    r.frames['amr_1/hand_camera_optical'] = _looking_down((0.5, 0.0, 0.4))
    return r, arm


def _looking_down(position):
    pose = np.eye(4)
    pose[:3, :3] = np.diag([1.0, -1.0, -1.0])       # optical z 가 아래
    pose[:3, 3] = position
    return pose


def test_belt_view_is_off_by_default_so_the_first_move_is_the_approach(nodes, monkeypatch):
    r, arm = rig(nodes, monkeypatch)
    r.ready_for_belt_pick()
    handle, result = r.execute(_goal(arm, 'belt', 0))
    assert result.outcome == 'ok'
    assert handle.feedback[0] == 'detect' and 'view' not in handle.feedback
    assert len(r.poses) == 6


def test_belt_view_moves_the_camera_above_the_belt_end_before_waiting_for_a_detection(nodes, monkeypatch):
    r, arm = _belt_view_rig(nodes, monkeypatch)
    r.base(True)
    r.belt(True, ORDER)
    r.hold(False)
    # 검출은 관측 자세에 간 **뒤에** 온다. 그 전 검출이면 max_age 로 버려진다.
    r.on_move[0] = lambda: r.pouches(ORDER)
    handle, result = r.execute(_goal(arm, 'belt', 0))
    assert result.outcome == 'ok'
    assert handle.feedback[:2] == ['detect', 'view']
    assert len(r.poses) == 7
    view = r.poses[0]
    np.testing.assert_allclose(view[:3, 3], (0.5, 0.0, 0.35))       # 벨트 끝 +z 로 standoff
    np.testing.assert_allclose(view[:3, 2], (0.0, 0.0, -1.0))       # 카메라 +z 가 아래를 본다


def test_belt_view_offset_moves_the_view_point_along_the_belt(nodes, monkeypatch):
    r, arm = _belt_view_rig(nodes, monkeypatch)
    r.node._belt_view_offset = -0.075
    r.base(True)
    r.belt(True, ORDER)
    r.hold(False)
    r.on_move[0] = lambda: r.pouches(ORDER)
    _handle, result = r.execute(_goal(arm, 'belt', 0))
    assert result.outcome == 'ok'
    np.testing.assert_allclose(r.poses[0][:3, 3], (0.425, 0.0, 0.35))
    np.testing.assert_allclose(r.frames[BELT_END][:3, 3], (0.5, 0.0, 0.1))   # TF 원본은 건드리지 않는다


def test_belt_view_is_not_used_for_a_deck_pick(nodes, monkeypatch):
    r, arm = _belt_view_rig(nodes, monkeypatch)
    r.base(True)
    r.hold(False)
    r.pouches(ORDER)
    handle, result = r.execute(_goal(arm, 'deck', 0))
    assert result.outcome == 'ok'
    assert 'view' not in handle.feedback


def test_belt_view_is_not_used_with_the_sim_sensor(nodes, monkeypatch):
    r, arm = _belt_view_rig(nodes, monkeypatch)
    r.node._pouch_source = arm.SOURCE_SIM
    r.ready_for_belt_pick()
    handle, result = r.execute(_goal(arm, 'belt', 0))
    assert result.outcome == 'ok'
    assert 'view' not in handle.feedback


def test_belt_view_without_the_frame_closes_as_not_detected_without_moving(nodes, monkeypatch):
    r, arm = _belt_view_rig(nodes, monkeypatch)
    del r.frames[BELT_END]
    r.ready_for_belt_pick()
    handle, result = r.execute(_goal(arm, 'belt', 0))
    assert result.outcome == 'not_detected'
    assert r.poses == []


def test_belt_view_ik_failure_closes_without_waiting_for_a_detection(nodes, monkeypatch):
    r, arm = _belt_view_rig(nodes, monkeypatch)
    r.ready_for_belt_pick()
    r.ik = [False]
    handle, result = r.execute(_goal(arm, 'belt', 0))
    assert result.outcome == 'grasp_failed'
    assert len(r.poses) == 1


def _belt_pick_poses(nodes, monkeypatch, tool_frame='', standoff=0.0):
    r, arm = _belt_view_rig(nodes, monkeypatch, standoff=standoff)
    r.node._tool_frame = tool_frame
    r.base(True)
    r.belt(True, ORDER)
    r.hold(False)
    # 검출 깊이 0.29 = 카메라 0.4 − 봉투 윗면 0.11. 관측을 켜든 끄든 같은 봉투 자리가 나온다(평면 투영과 일치).
    if standoff > 0.0:
        r.on_move[0] = lambda: r.pouches(ORDER, position=(0.0, 0.0, 0.29))
    else:
        r.pouches(ORDER, position=(0.0, 0.0, 0.29))
    _handle, result = r.execute(_goal(arm, 'belt', 0))
    assert result.outcome == 'ok'
    return r.poses


def test_tool_frame_only_moves_the_view_and_never_the_grasp_tcp(nodes, monkeypatch):
    """tool_frame(합본 손목)은 관측 자세 계산에만 쓴다. 접근·파지·놓기 IK 목표는 그대로다(작전 9/23 확인 요청)."""
    plain = _belt_pick_poses(nodes, monkeypatch)
    with_tool = _belt_pick_poses(nodes, monkeypatch, tool_frame='amr_1/ur_arm_wrist_3_link')
    viewed = _belt_pick_poses(nodes, monkeypatch, tool_frame='amr_1/ur_arm_wrist_3_link', standoff=0.3)
    assert len(plain) == len(with_tool) == len(viewed) - 1
    for before, after in zip(plain, with_tool, strict=True):
        np.testing.assert_allclose(before, after)
    for before, after in zip(plain, viewed[1:], strict=True):
        np.testing.assert_allclose(before, after)



def test_only_the_view_pose_is_sent_as_a_tool_pose(nodes, monkeypatch):
    """관측 자세는 공구(손목) 자세, 접근·파지·놓기는 흡착점 자세로 넘긴다(tcp_offset_m 은 뒤쪽에만 걸린다)."""
    r, arm = _belt_view_rig(nodes, monkeypatch)
    r.base(True)
    r.belt(True, ORDER)
    r.hold(False)
    r.on_move[0] = lambda: r.pouches(ORDER)
    _handle, result = r.execute(_goal(arm, 'belt', 0))
    assert result.outcome == 'ok'
    assert r.tool_flags == [True] + [False] * 6


def test_tool_target_undoes_the_tcp_offset_along_the_tool_axis(nodes, monkeypatch):
    """흡착점 자세 → IK 공구 자세. 위에서 내려다보는 파지(공구 +Z 가 아래)면 공구가 오프셋만큼 위에 있다."""
    r, arm = rig(nodes, monkeypatch)
    r.node.tool_target = arm.ArmNode.tool_target.__get__(r.node)
    r.node._tool_from_tcp = np.eye(4)
    r.node._tool_from_tcp[:3, 3] = (0.0, 0.0, 0.1555)
    grasp = arm.kin.top_down_pose(np.array([0.5, 0.1, 0.2]), 0.3)
    tool = r.node.tool_target(grasp)
    np.testing.assert_allclose(tool[:3, 3], (0.5, 0.1, 0.2 + 0.1555), atol=1e-9)
    np.testing.assert_allclose(tool[:3, :3], grasp[:3, :3])
    np.testing.assert_allclose(r.node.tool_target(grasp, tool=True), grasp)       # 관측 자세는 그대로
    r.node._tool_from_tcp = np.eye(4)
    np.testing.assert_allclose(r.node.tool_target(grasp), grasp)                   # 기본 0 = 지금 동작



def test_view_detection_is_placed_on_the_pouch_plane_not_at_the_detector_depth(nodes, monkeypatch):
    """관측 자세에서는 검출기의 고정 거리 대신 광선 ∩ 봉투 윗면(프레임 z + 봉투 두께)으로 봉투를 놓는다."""
    r, arm = _belt_view_rig(nodes, monkeypatch)
    r.base(True)
    r.belt(True, ORDER)
    r.hold(False)
    # 검출기는 광선 위 아무 깊이(0.9 m)를 낸다. 광선은 카메라 (0.5, 0, 0.4) 에서 (0.1, 0.1, 0.9) 방향이다.
    r.on_move[0] = lambda: r.pouches(ORDER, position=(0.1, 0.1, 0.9))
    _handle, result = r.execute(_goal(arm, 'belt', 0))
    assert result.outcome == 'ok'
    grasp = r.poses[2]                                  # 관측 → 접근 → 파지
    depth = 0.4 - 0.11                                  # 카메라 높이 - (벨트 끝 0.1 + 봉투 0.01)
    np.testing.assert_allclose(grasp[:3, 3], (0.5 + 0.1 * depth / 0.9, -0.1 * depth / 0.9, 0.11), atol=1e-9)


def test_deck_view_looks_at_the_source_slot_before_waiting(nodes, monkeypatch):
    r, arm = _belt_view_rig(nodes, monkeypatch)
    r.node._deck_view_standoff = 0.25
    slot = np.eye(4)
    slot[:3, 3] = (0.2, 0.3, 0.05)
    r.frames[f'{SLOT_PREFIX}0'] = slot
    r.frames['amr_1/hand_camera_optical'] = _looking_down((0.2, 0.3, 0.3))
    r.base(True)
    r.hold(False)
    r.on_move[0] = lambda: r.pouches(ORDER)
    handle, result = r.execute(_goal(arm, 'deck', -1))
    assert result.outcome == 'ok'
    assert handle.feedback[:2] == ['detect', 'view']
    np.testing.assert_allclose(r.poses[0][:3, 3], (0.2, 0.3, 0.30))
    assert r.tool_flags[0] is True


def test_deck_view_is_skipped_when_the_slot_frame_is_used(nodes, monkeypatch):
    r, arm = _belt_view_rig(nodes, monkeypatch)
    r.node._deck_view_standoff = 0.25
    r.node._deck_pick_from_frame = True
    r.base(True)
    r.hold(False)
    handle, result = r.execute(_goal(arm, 'deck', -1))
    assert result.outcome == 'ok'
    assert 'view' not in handle.feedback


def test_refine_moves_over_the_first_detection_then_reads_the_qr(nodes, monkeypatch):
    """첫 관측은 QR 을 못 읽어도(빈 order_id) 자리를 잡고, 그 위 가까이에서 다시 본 뒤 QR 로 고른다."""
    r, arm = _belt_view_rig(nodes, monkeypatch)
    r.node._refine_standoff = 0.2
    r.base(True)
    r.belt(True, ORDER)
    r.hold(False)
    # 첫 관측: 카메라 (0.5, 0, 0.4) 아래, 광선이 (0.1, 0, 0.29) → 봉투 윗면 (0.6, 0, 0.11). QR 은 못 읽음.
    r.on_move[0] = lambda: r.pouches('', position=(0.1, 0.0, 0.29))

    def second_view():
        r.frames['amr_1/hand_camera_optical'] = _looking_down((0.6, 0.0, 0.31))
        r.pouches(ORDER, position=(0.0, 0.0, 0.2))

    r.on_move[1] = second_view
    handle, result = r.execute(_goal(arm, 'belt', 0))
    assert result.outcome == 'ok'
    assert handle.feedback[:3] == ['detect', 'view', 'refine']
    np.testing.assert_allclose(r.poses[1][:3, 3], (0.6, 0.0, 0.31), atol=1e-9)    # 봉투 윗면 + 0.2
    assert r.tool_flags[:2] == [True, True]
    np.testing.assert_allclose(r.poses[3][:3, 3], (0.6, 0.0, 0.11), atol=1e-9)    # 파지는 재관측 검출 자리


def test_refine_prefers_this_orders_qr_over_a_nearer_unread_blob(nodes, monkeypatch):
    """병원 41725ff 회차: 관측점 가까운 흰 덩어리(QR 미판독)보다 이 주문 QR 을 읽은 검출 위로 간다.

    다른 주문의 QR 은 더 가까워도 쓰지 않는다.
    """
    r, arm = _belt_view_rig(nodes, monkeypatch)
    r.node._refine_standoff = 0.2
    r.base(True)
    r.belt(True, ORDER)
    r.hold(False)

    def first_view():
        # 카메라 (0.5, 0, 0.4) 아래. 광선 → 봉투 윗면: 빈 값 (0.5, 0, 0.11), OTHER (0.51, 0, 0.11),
        # ORDER (0.6, 0, 0.11). 관측점(0.5, 0)에서 ORDER 가 가장 멀다.
        message = _detections(r.clock, '', position=(0.0, 0.0, 0.29))
        message.detections += _detections(r.clock, OTHER, position=(0.01, 0.0, 0.29)).detections
        message.detections += _detections(r.clock, ORDER, position=(0.1, 0.0, 0.29)).detections
        r.node._pouches = message

    r.on_move[0] = first_view

    def second_view():
        r.frames['amr_1/hand_camera_optical'] = _looking_down((0.6, 0.0, 0.31))
        r.pouches(ORDER, position=(0.0, 0.0, 0.2))

    r.on_move[1] = second_view
    handle, result = r.execute(_goal(arm, 'belt', 0))
    assert result.outcome == 'ok'
    assert handle.feedback[:3] == ['detect', 'view', 'refine']
    np.testing.assert_allclose(r.poses[1][:3, 3], (0.6, 0.0, 0.31), atol=1e-9)


def test_refine_without_a_first_detection_still_waits_and_closes_as_not_detected(nodes, monkeypatch):
    r, arm = _belt_view_rig(nodes, monkeypatch)
    r.node._refine_standoff = 0.2
    r.base(True)
    r.belt(True, ORDER)
    r.hold(False)
    handle, result = r.execute(_goal(arm, 'belt', 0))
    assert result.outcome == 'not_detected'
    assert 'refine' not in handle.feedback
    assert len(r.poses) == 1


def test_the_goal_zone_id_picks_the_bed_and_beats_the_parameter(nodes, monkeypatch):
    """계약 10.1. goal 이 침상을 말하면 그 침상 보관함에 놓는다 — 한 회차에 여러 침상을 돈다.

    파라미터 `cabinet_frame` 은 bed_a1 로 두고 goal 에 bed_b1 을 준다. 파라미터가 아니라 goal 이 이긴다.
    9/23 데모가 ord-0001(bed_a1) 한 건으로 피해 간 자리다.
    """
    r, arm = rig(nodes, monkeypatch)
    r.base(True)
    r.hold(False)
    r.pouches(OTHER, ORDER)
    handle, result = r.execute(_goal(arm, 'deck', -1, zone_id='bed_b1'))
    assert result.outcome == 'ok'
    assert r.events[-1] == (arm.Event.POUCH_PLACED, ORDER, 'bed_b1/cabinet')
    assert r.events[-1][2] != CABINET                 # 파라미터(bed_a1)가 아니다


def test_the_frame_name_comes_from_one_place(nodes, monkeypatch):
    """이름을 부르는 쪽이 짜지 않는다. `cabinet_frame_for` 한 곳이 만든다."""
    r, arm = rig(nodes, monkeypatch)
    r.node._cabinet_frame = 'bed_a1/cabinet'
    assert r.node.cabinet_frame_for(_goal(arm, 'deck', -1)) == 'bed_a1/cabinet'
    assert r.node.cabinet_frame_for(_goal(arm, 'deck', -1, zone_id='bed_b1')) == 'bed_b1/cabinet'
    r.node._cabinet_frame = ''
    assert r.node.cabinet_frame_for(_goal(arm, 'deck', -1)) == ''
    assert r.node.cabinet_frame_for(_goal(arm, 'deck', -1, zone_id='bed_b1')) == 'bed_b1/cabinet'


def test_a_zone_the_robot_has_no_frame_for_is_refused_by_name(nodes, monkeypatch):
    """계약 10.1 의 미결 항목: `zones.yaml` 에 없는 zone_id 는 어떤 outcome 인가.

    새 값을 넣지 않고 지금 있는 길을 쓴다 — 놓을 곳 TF 가 없으면 `not_detected` 이고 로그가 프레임
    이름을 말한다. 새 outcome 은 ADR 0001 의 종결 상태 대응까지 건드려야 해서 이 카드 밖이다.
    """
    r, arm = rig(nodes, monkeypatch)
    r.base(True)
    r.hold(False)
    r.pouches(OTHER, ORDER)
    handle, result = r.execute(_goal(arm, 'deck', -1, zone_id='bed_zzz'))
    assert result.outcome == 'not_detected'
    # 이유(프레임 이름)는 로그에 남는다. 계약이 보는 것은 outcome 이다.


# ---- 비전 교차 확인(재범 9/25 점수판 AI 비전) ----------------------------------------------------------------


def _vision_rig(nodes, monkeypatch):
    """접근 자세의 손 카메라: 참값 파지점 (0.51, 0, 0.11) 위 (0.5, 0, 0.4) 에서 아래를 본다."""
    r, arm = _belt_view_rig(nodes, monkeypatch)
    r.node._vision_tolerance = 0.05
    r.node._vision_timeout = 1.0
    r.node._grasp_z_offset = 0.0
    r.node._vision_pouches = None
    truth = np.eye(4)
    truth[:3, 3] = (0.51, 0.0, 0.11)
    lines = []
    r.node.get_logger = lambda: types.SimpleNamespace(info=lines.append, warn=lines.append)
    return r, truth, lines


def test_vision_check_uses_the_detection_when_it_agrees_with_the_truth(nodes, monkeypatch):
    r, truth, lines = _vision_rig(nodes, monkeypatch)
    r.node._vision_pouches = _detections(r.clock, ORDER, position=(0.02, 0.0, 0.29))    # → (0.52, 0, 0.11)
    chosen = r.node._vision_grasp(ORDER, truth, lambda: False)
    np.testing.assert_allclose(chosen[:3, 3], (0.52, 0.0, 0.11), atol=1e-9)
    assert 'ok' in lines[-1] and '자리 검출' in lines[-1] and '판독 1/1' in lines[-1]


def test_vision_check_falls_back_to_the_truth_when_they_disagree(nodes, monkeypatch):
    r, truth, lines = _vision_rig(nodes, monkeypatch)
    r.node._vision_pouches = _detections(r.clock, ORDER, position=(0.20, 0.0, 0.29))    # → (0.70, …), 0.19 m 차
    chosen = r.node._vision_grasp(ORDER, truth, lambda: False)
    np.testing.assert_allclose(chosen, truth)
    assert 'vision_mismatch' in lines[-1] and '자리 참값' in lines[-1]


def test_vision_check_falls_back_after_the_timeout_without_a_read(nodes, monkeypatch):
    """다른 주문의 QR 만 보이면(이 주문 판독 0) 1 s 뒤 참값으로 간다. 한 바퀴를 깨지 않는다."""
    r, truth, lines = _vision_rig(nodes, monkeypatch)
    r.node._vision_pouches = _detections(r.clock, OTHER, position=(0.02, 0.0, 0.29))
    start = r.clock
    chosen = r.node._vision_grasp(ORDER, truth, lambda: False)
    np.testing.assert_allclose(chosen, truth)
    assert r.clock - start >= 1.0
    assert 'vision_mismatch' in lines[-1] and '판독 0/1' in lines[-1]


def test_vision_check_ignores_frames_from_before_the_arrival(nodes, monkeypatch):
    r, truth, lines = _vision_rig(nodes, monkeypatch)
    r.node._vision_pouches = _detections(r.clock - 0.5, ORDER, position=(0.02, 0.0, 0.29))
    chosen = r.node._vision_grasp(ORDER, truth, lambda: False)
    np.testing.assert_allclose(chosen, truth)
    assert '판독 0/0' in lines[-1]


def test_vision_check_uses_a_read_from_just_before_the_arrival(nodes, monkeypatch):
    """회차71: 1 s 창에 프레임 1장(판독 0), QR 은 도착 2.2 s 전 접근 중에 읽혔다. 3 s 안의 판독을 쓴다."""
    r, truth, lines = _vision_rig(nodes, monkeypatch)
    r.node._vision_lookback = 3.0
    early = _detections(r.clock - 2.2, ORDER, position=(0.02, 0.0, 0.29))
    late = _detections(r.clock + 0.1, OTHER, position=(0.3, 0.0, 0.29))
    r.node._vision_history = [early, late]
    r.node._vision_pouches = late
    chosen = r.node._vision_grasp(ORDER, truth, lambda: False)
    np.testing.assert_allclose(chosen[:3, 3], (0.52, 0.0, 0.11), atol=1e-9)
    assert 'ok' in lines[-1] and '자리 검출' in lines[-1]


def test_vision_check_ignores_reads_older_than_the_lookback(nodes, monkeypatch):
    r, truth, lines = _vision_rig(nodes, monkeypatch)
    r.node._vision_lookback = 3.0
    r.node._vision_history = [_detections(r.clock - 4.0, ORDER, position=(0.02, 0.0, 0.29))]
    chosen = r.node._vision_grasp(ORDER, truth, lambda: False)
    np.testing.assert_allclose(chosen, truth)
    assert 'vision_mismatch' in lines[-1]


def _deck_vision_rig(nodes, monkeypatch):
    """참값 센서 + 상판 비전 교차 확인. `_vision_grasp` 는 불린 순간의 이동 수만 적고 참값을 돌려준다."""
    r, arm = _belt_view_rig(nodes, monkeypatch)
    r.node._pouch_source = arm.SOURCE_SIM
    r.node._vision_check = True
    r.node._vision_topic = '/amr_1/hand_camera/pouches'
    r.node._deck_view_standoff = 0.25
    r.node._refine_standoff = 0.20
    slot = np.eye(4)
    slot[:3, 3] = (0.2, 0.3, 0.05)
    r.frames[f'{SLOT_PREFIX}0'] = slot
    r.frames['amr_1/hand_camera_optical'] = _looking_down((0.2, 0.3, 0.3))
    moves_at_check = []
    r.node._vision_grasp = lambda order_id, truth, stop: (moves_at_check.append(len(r.poses)), truth)[1]
    r.base(True)
    r.hold(False)
    r.pouches(ORDER)
    return r, arm, moves_at_check


def test_deck_vision_looks_from_the_view_pose_before_the_approach(nodes, monkeypatch):
    """campaign1 a01·회차108: 접근 자세(봉투 위 8 cm)에서는 QR 이 화면 밖이었다. 칸 위 관측 자세에서 먼저 본다."""
    r, arm, moves_at_check = _deck_vision_rig(nodes, monkeypatch)
    handle, result = r.execute(_goal(arm, 'deck', -1))
    assert result.outcome == 'ok'
    assert handle.feedback[:2] == ['detect', 'view']
    assert 'refine' not in handle.feedback              # 재관측은 카메라 검출 집기에서만
    np.testing.assert_allclose(r.poses[0][:3, 3], (0.2, 0.3, 0.30))
    assert r.tool_flags[0] is True
    assert moves_at_check == [1]                         # 관측 자세 한 번 뒤, 접근 전에 확인한다


def test_deck_vision_without_the_slot_frame_still_picks_by_the_truth(nodes, monkeypatch):
    r, arm, moves_at_check = _deck_vision_rig(nodes, monkeypatch)
    del r.frames[f'{SLOT_PREFIX}0']
    handle, result = r.execute(_goal(arm, 'deck', -1))
    assert result.outcome == 'ok'                        # 관측은 덤이다 — 한 바퀴를 깨지 않는다
    assert 'view' not in handle.feedback
    assert moves_at_check == [0]


def test_belt_pick_with_deck_vision_does_not_add_a_view(nodes, monkeypatch):
    r, arm, moves_at_check = _deck_vision_rig(nodes, monkeypatch)
    r.node._belt_view_standoff = 0.0
    r.ready_for_belt_pick()
    handle, result = r.execute(_goal(arm, 'belt', 0))
    assert result.outcome == 'ok'
    assert 'view' not in handle.feedback
    assert moves_at_check == []
