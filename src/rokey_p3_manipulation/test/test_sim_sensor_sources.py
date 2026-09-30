"""`pouch_source`·`scan_tag_source` — 시뮬 센서 입력(K5, opt-in). 기본은 지금 동작이다.

빈월드 한 바퀴는 YOLO·QR 이 아직 없어 계약 토픽(`hand_camera/*`)에 검출·태그를 낼 주체가 없다(#417).
그래서 스테이지가 별도 토픽(`{ns}/sim/*`)으로 센서값을 내고 팔이 opt-in 으로 그쪽을 본다.
**계약 토픽의 작성자는 그대로 perception 하나다.**
"""

import types

import pytest
import test_reset_fence as rf

nodes = rf.nodes

ZONE = 'bed_a1'
TAG = 'pt-p001'

BORROWED = ('run_scan_tag', '_sensor_topic', '_sensor_source', 'latest_tag_read', 'base_stopped', 'sim_now')


class _Time:
    """`RclTime.from_msg` 대역. stamp → nanoseconds 만 있으면 된다."""

    def __init__(self, nanoseconds):
        self.nanoseconds = nanoseconds

    @classmethod
    def from_msg(cls, stamp):
        return cls(int(stamp.sec) * 10**9 + int(stamp.nanosec))


class Scan:
    """`run_scan_tag` 만 돌리는 작은 하네스. 팔이 움직이면 기록한다."""

    def __init__(self, arm, monkeypatch, source):
        self.arm = arm
        monkeypatch.setattr(arm, 'RclTime', _Time)
        node = type('ScanHarness', (), {n: getattr(arm.ArmNode, n) for n in BORROWED})()
        rf._common(node, arm, monkeypatch)
        node._base_stopped = arm.Freshness(arm.STALE_STATUS_S)
        node._base_stopped.update(True)
        node._tag_read = None
        node._scan_timeout = 5.0
        node._detection_max_age = 1.0
        node._scan_tag_source = source
        node._tag_topic = node._sensor_topic(source, '/amr_1', 'tag_reads', 'tag_reads')
        node._tag_standoff = 0.0          # camera 경로에 필요한 값이 **없다**(빈월드 기본)
        node._tool_frame = ''
        self.clock = 100.0
        self.moved = []                   # move_to_pose 호출 기록
        node.sim_now = lambda: self.clock
        node.move_to_pose = lambda pose, stop, tool=False: (self.moved.append(pose), True)[1]
        node.tag_view_pose = lambda zone: None    # camera 경로는 여기서 막힌다
        node.wait = lambda seconds, stop: setattr(self, 'clock', self.clock + seconds)
        self.node = node

    def publish(self, tag_id=TAG, kind=None, status=None):
        tags = self.arm.TagRead
        self.node._tag_read = types.SimpleNamespace(
            kind=tags.KIND_PATIENT if kind is None else kind,
            status=tags.STATUS_OK if status is None else status, tag_id=tag_id,
            header=types.SimpleNamespace(stamp=types.SimpleNamespace(sec=int(self.clock), nanosec=0)))

    def run(self):
        return self.node.run_scan_tag(self.arm.TagRead.KIND_PATIENT, ZONE)


def rig(arm, monkeypatch, source):
    return Scan(arm, monkeypatch, source)


# ---- 토픽 고르기 -------------------------------------------------------------

def test_default_sources_are_the_contract_topics(nodes):
    arm, _ = nodes
    node = type('T', (), {'_sensor_topic': arm.ArmNode._sensor_topic})()
    assert arm.SOURCE_CAMERA == 'camera' and arm.SOURCE_SIM == 'sim'
    assert node._sensor_topic(arm.SOURCE_CAMERA, '/amr_1', 'pouches', 'pouches') == '/amr_1/hand_camera/pouches'
    assert node._sensor_topic(arm.SOURCE_CAMERA, '/amr_1', 'tag_reads', 'tag_reads') == '/amr_1/hand_camera/tag_reads'


def test_sim_source_never_uses_the_contract_topic(nodes):
    """계약 토픽의 작성자는 perception 하나여야 한다. sim 은 별도 토픽을 쓴다."""
    arm, _ = nodes
    node = type('T', (), {'_sensor_topic': arm.ArmNode._sensor_topic})()
    for name in ('pouches', 'tag_reads'):
        topic = node._sensor_topic(arm.SOURCE_SIM, '/amr_1', name, name)
        assert topic == f'/amr_1/sim/{name}'
        assert 'hand_camera' not in topic


def test_unknown_source_is_refused(nodes):
    arm, _ = nodes
    node = type('T', (), {'_sensor_source': arm.ArmNode._sensor_source})()
    node.get_parameter = lambda name: types.SimpleNamespace(value='both')
    with pytest.raises(ValueError):
        node._sensor_source('pouch_source')


# ---- sim 스캔 경로 -----------------------------------------------------------

def test_camera_scan_needs_the_standoff_and_tool_frame(nodes, monkeypatch):
    """[현행 고정] 빈월드 기본값(standoff 0·tool_frame 빈 값)에서는 카메라 경로가 UNREADABLE 이다."""
    arm, _ = nodes
    r = rig(arm, monkeypatch, arm.SOURCE_CAMERA)
    r.publish()
    tag_id, status = r.run()
    assert tag_id == '' and status == arm.TagRead.STATUS_UNREADABLE
    assert r.moved == []


def test_sim_scan_reads_the_tag_without_moving_the_arm(nodes, monkeypatch):
    """sim 은 팔을 움직이지 않는다 — tag_standoff_m·tool_frame 이 없어도 된다."""
    arm, _ = nodes
    r = rig(arm, monkeypatch, arm.SOURCE_SIM)
    r.publish()
    tag_id, status = r.run()
    assert (tag_id, status) == (TAG, arm.TagRead.STATUS_OK)
    assert r.moved == []                                     # **한 번도 안 움직였다**


def test_sim_scan_passes_the_tag_through_and_does_not_judge_it(nodes, monkeypatch):
    """다른 침상의 태그가 와도 팔은 그대로 넘긴다. 판정은 orchestrator 다.

    팔이 거르면 "다른 침상에서 AUTH_FAIL" 이라는 음성 사례가 팔에서 묻힌다.
    """
    arm, _ = nodes
    r = rig(arm, monkeypatch, arm.SOURCE_SIM)
    r.publish(tag_id='pt-someone-else')
    tag_id, status = r.run()
    assert (tag_id, status) == ('pt-someone-else', arm.TagRead.STATUS_OK)


def test_sim_scan_waits_out_the_timeout_when_no_sensor_value_comes(nodes, monkeypatch):
    """센서값이 오기 전에는 시한까지 기다려 UNREADABLE. 스테이지가 안 내면 그 침상이 아니라는 뜻이다."""
    arm, _ = nodes
    r = rig(arm, monkeypatch, arm.SOURCE_SIM)
    tag_id, status = r.run()                                 # 아무것도 발행하지 않는다
    assert tag_id == '' and status == arm.TagRead.STATUS_UNREADABLE
    assert r.clock >= 105.0                                  # scan_timeout 5 s 를 다 기다렸다


def test_sim_scan_refuses_an_empty_tag_id(nodes, monkeypatch):
    """`tag_id` 가 비면 OK 로 닫으면 안 된다 — orchestrator 가 `detail.tag_id or _last_tag` 로 비교해
    **스텁 검출기가 낸 "언제나 맞는" 태그**로 인증이 거짓 통과한다(#417 4절)."""
    arm, _ = nodes
    r = rig(arm, monkeypatch, arm.SOURCE_SIM)
    r.publish(tag_id='')
    tag_id, status = r.run()
    assert tag_id == '' and status == arm.TagRead.STATUS_UNREADABLE


def test_sim_scan_ignores_a_read_of_another_kind(nodes, monkeypatch):
    """환자 태그를 기다리는데 스테이션 태그가 오면 쓰지 않는다."""
    arm, _ = nodes
    r = rig(arm, monkeypatch, arm.SOURCE_SIM)
    r.publish(tag_id='st-station_a', kind=arm.TagRead.KIND_STATION)
    tag_id, status = r.run()
    assert tag_id == '' and status == arm.TagRead.STATUS_UNREADABLE


def test_sim_scan_still_honours_the_base_stopped_interlock(nodes, monkeypatch):
    """팔을 안 움직여도 "그 자리에 서 있어야" 인증이다(계약 5절)."""
    arm, _ = nodes
    r = rig(arm, monkeypatch, arm.SOURCE_SIM)
    r.node._base_stopped.update(False)
    r.publish()
    tag_id, status = r.run()
    assert tag_id == '' and status == arm.TagRead.STATUS_UNREADABLE


# ---- 기준 프레임(결정 47) ------------------------------------------------------

def test_default_arm_base_frame_is_the_ur5_link_not_the_mobile_base(nodes):
    """`{robot}/base_link` 는 **이동 베이스**의 프레임이다(계약 420-434, 작성자 `base_driver`).

    UR5 밑동을 같은 이름으로 두면 한 child 에 부모가 둘이 된다. 결정 47 로 이름을 갈랐다.
    """
    arm, _ = nodes
    assert arm.default_arm_base_frame('amr_1') == 'amr_1/ur_arm_base_link'
    assert arm.default_arm_base_frame('amr_1') != 'amr_1/base_link'


def test_arm_base_frame_can_still_be_set_explicitly(nodes):
    """params 로 주면 그 값을 쓴다 — 스테이지 기본값 변경과 따로 머지돼도 맞출 수 있다."""
    arm, _ = nodes
    node = type('T', (), {})()
    node._robot_id = 'amr_1'
    given = 'amr_1/whatever_link'
    node._arm_base_frame = given or arm.default_arm_base_frame(node._robot_id)
    assert node._arm_base_frame == given


# 시한 초과 때 왜인지 남는가 (lap8: ⑦ 이 60 s 뒤 AUTH_FAIL 인데 팔에 줄이 없었다) ----

def test_scan_timeout_says_nothing_arrived(nodes, monkeypatch):
    """판독이 하나도 안 오면 그렇게 말한다 — 토픽 이름과 함께."""
    arm, _ = nodes
    scan = Scan(arm, monkeypatch, 'sim')
    lines = []
    scan.node.get_logger = lambda: types.SimpleNamespace(
        info=lines.append, warn=lines.append, error=lines.append, debug=lines.append)
    tag, status = scan.run()
    assert status == arm.TagRead.STATUS_UNREADABLE and tag == ''
    assert any('판독이 하나도 안 왔다' in line for line in lines), lines
    assert any('/amr_1/sim/tag_reads' in line for line in lines), lines


def test_scan_timeout_reports_the_last_read_that_did_not_match(nodes, monkeypatch):
    """왔는데 안 맞은 것과 안 온 것을 가른다 — 그 둘은 원인이 다르다."""
    arm, _ = nodes
    scan = Scan(arm, monkeypatch, 'sim')
    lines = []
    scan.node.get_logger = lambda: types.SimpleNamespace(
        info=lines.append, warn=lines.append, error=lines.append, debug=lines.append)
    scan.publish(kind=arm.TagRead.KIND_STATION)      # 요청한 kind 가 아니다
    tag, status = scan.run()
    assert status == arm.TagRead.STATUS_UNREADABLE and tag == ''
    assert any('마지막 판독' in line for line in lines), lines
