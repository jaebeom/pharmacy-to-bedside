"""L2. isaac_adapter 하나와 대본대로 답하는 Isaac 자리(probe). 시한·다른 요청의 응답·형식 오류·stamp·epoch 옮김.

probe 가 Isaac 쪽 JSON 토픽을 직접 주고받는다. 표의 예시 문자열(test_isaac_json)을 그대로 보낸다.

fixture 는 테스트 전에 probe 와 어댑터의 모든 토픽이 양방향으로 **매칭**됐는지 본다(matching_checks).
토픽이 RELIABLE+VOLATILE 이라 매칭 전에 한 번 낸 메시지는 사라지기 때문이다.
그래프에 이름이 보이는 것(count_subscribers)은 probe 자신의 엔티티로도 참이 되어 확인이 되지 않았다
(9/18 팔 docker 4회 중 1회 dispense·belt epoch 실패).
"""

import contextlib
import json
import threading
import time

import pytest
import rclpy
from rclpy.executors import MultiThreadedExecutor
from rclpy.qos import DurabilityPolicy, ReliabilityPolicy
from rclpy.node import Node
from builtin_interfaces.msg import Time
from rclpy.parameter import Parameter
from std_msgs.msg import Header, String

from rokey_p3_bringup import isaac_json
from rokey_p3_bringup.isaac_adapter import IsaacAdapter
from rokey_p3_interfaces.msg import (BeltObservation, BeltState, CabinetObservation, Event,
                                     GripperCommand, GripperState, PouchDetectionArray, TagRead)
from rokey_p3_interfaces.srv import Dispense, Reset
from rokey_p3_orchestrator.ros_qos import heartbeat_qos, latched_qos, reliable_qos, sensor_qos
from l2_discovery import wait_for_discovery
from l2_teardown import assert_no_leftovers, teardown_nodes
from test_isaac_json import BELT_AT_END, EVENT_DISPENSED, EVENT_POUCH_AT_END, PICK_NOTICE_OK, RESET_RESPONSE_FAILED

DISPENSE_TIMEOUT_S = 0.6
RESET_TIMEOUT_S = 0.8


class IsaacProbe(Node):
    """Isaac 자리. answer(topic, request_dict) 가 돌려준 문자열(또는 None 이면 무응답)을 응답으로 낸다."""

    def __init__(self, listen=True, observation=False, gripper=False, sensors=False,
                 sensor_reliability=heartbeat_qos, cabinet=False):
        super().__init__('isaac_probe')
        self.answer = lambda topic, request: None
        self.observations = []
        self.observation_pub = self.observation_sub = None
        if observation:
            self.observation_pub = self.create_publisher(String, '/isaac/pharmacy/belt_observation', heartbeat_qos())
            self.observation_sub = self.create_subscription(
                BeltObservation, '/pharmacy/belt/observation', self.observations.append, heartbeat_qos())
        self.gripper_states, self.gripper_commands = [], []
        self.gripper_pub = self.gripper_sub = self.command_pub = self.command_sub = None
        if gripper:
            self.gripper_pub = self.create_publisher(String, '/isaac/amr_1/gripper/state', heartbeat_qos())
            self.gripper_sub = self.create_subscription(
                GripperState, '/amr_1/gripper/state', self.gripper_states.append, heartbeat_qos())
            self.command_pub = self.create_publisher(GripperCommand, '/amr_1/gripper/command_seq', reliable_qos(10))
            self.command_sub = self.create_subscription(
                String, '/isaac/amr_1/gripper/command_seq', lambda m: self.gripper_commands.append(m.data),
                reliable_qos(10))
        self.pouch_arrays, self.tag_reads = [], []
        self.pouches_pub = self.pouches_sub = self.tag_pub = self.tag_sub = None
        if sensors:
            # 스테이지가 실제로 쓰는 QoS 로 낸다. 어댑터와 같은 값으로 두면 **불일치를 못 본다** —
            # 9/21 실습27 P6 에서 스테이지가 best effort 로 내 한 건도 안 왔는데 이 시험은 초록이었다.
            self.pouches_pub = self.create_publisher(String, '/isaac/amr_1/pouches', sensor_reliability())
            self.pouches_sub = self.create_subscription(
                PouchDetectionArray, '/amr_1/sim/pouches', self.pouch_arrays.append, heartbeat_qos())
            self.tag_pub = self.create_publisher(String, '/isaac/amr_1/tag_reads', sensor_reliability())
            self.tag_sub = self.create_subscription(
                TagRead, '/amr_1/sim/tag_reads', self.tag_reads.append, heartbeat_qos())
        self.cabinets = []
        self.cabinet_pub = self.cabinet_sub = None
        if cabinet:
            self.cabinet_pub = self.create_publisher(String, '/isaac/evaluator/cabinet', latched_qos(50))
            self.cabinet_sub = self.create_subscription(
                CabinetObservation, '/evaluator/cabinet', self.cabinets.append, latched_qos(50))
        self.requests = []
        self.belts = []
        self.events = []
        self.notices = []
        self.notice_sub = self.create_subscription(String, '/isaac/pharmacy/pick_notice',
                                                   lambda m: self.notices.append(m.data), reliable_qos(10))
        self.dispense_response = self.create_publisher(String, '/isaac/pharmacy/dispense_response', reliable_qos(10))
        self.reset_response = self.create_publisher(String, '/isaac/sim/reset_response', reliable_qos(10))
        self.belt = self.create_publisher(String, '/isaac/pharmacy/belt', heartbeat_qos())
        self.isaac_events = self.create_publisher(String, '/isaac/events', latched_qos(500))
        self.request_subs = []
        if listen:
            self.request_subs = [
                self.create_subscription(String, '/isaac/pharmacy/dispense_request', self._on_dispense,
                                         reliable_qos(10)),
                self.create_subscription(String, '/isaac/sim/reset_request', self._on_reset, reliable_qos(10))]
        self.belt_sub = self.create_subscription(BeltState, '/pharmacy/belt', self.belts.append, heartbeat_qos())
        self.events_sub = self.create_subscription(Event, '/events', self.events.append, latched_qos(500))
        self.dispense = self.create_client(Dispense, '/pharmacy/dispense')
        self.reset = self.create_client(Reset, '/sim/reset')
        self.event_pub = self.create_publisher(Event, '/events', latched_qos(500))

    def _on_dispense(self, msg):
        request = isaac_json.parse_dispense_request(msg.data)
        self.requests.append(('dispense', msg.data))
        text = self.answer('dispense', request)
        if text is not None:
            self.dispense_response.publish(String(data=text))

    def _on_reset(self, msg):
        request = isaac_json.parse_reset_request(msg.data)
        self.requests.append(('reset', msg.data))
        text = self.answer('reset', request)
        if text is not None:
            self.reset_response.publish(String(data=text))

    def call(self, client, request):
        """(wall 걸린 시간, 응답)."""
        assert client.wait_for_service(timeout_sec=5.0), f'{client.srv_name} 서버가 없다'
        started = time.monotonic()
        future = client.call_async(request)
        wait_until(future.done, 10.0, f'{client.srv_name} 응답이 없다')
        return time.monotonic() - started, future.result()


def wait_until(condition, timeout_s, message):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.02)
    raise AssertionError(f'{timeout_s} s: {message}')


def matching_checks(probe, pick_notice):
    """(설명, 매칭됐는지) 목록. rclpy 의 매칭 수(get_subscription_count·get_publisher_count)는 그래프 이름이 아니라
    실제로 짝이 맞은 상대 수다. /events 는 probe 가 스스로 내고 받으므로 probe 자신 1 + 어댑터 1 = 2 를 본다."""
    matched = [
        ('probe → 어댑터 /isaac/pharmacy/dispense_response',
         lambda: probe.dispense_response.get_subscription_count() >= 1),
        ('probe → 어댑터 /isaac/sim/reset_response', lambda: probe.reset_response.get_subscription_count() >= 1),
        ('probe → 어댑터 /isaac/pharmacy/belt', lambda: probe.belt.get_subscription_count() >= 1),
        ('probe → 어댑터 /isaac/events', lambda: probe.isaac_events.get_subscription_count() >= 1),
        ('probe → 어댑터 /events(probe 자신 포함 2)', lambda: probe.event_pub.get_subscription_count() >= 2),
        ('어댑터 → probe /pharmacy/belt', lambda: probe.belt_sub.get_publisher_count() >= 1),
        ('어댑터 → probe /events(probe 자신 포함 2)', lambda: probe.events_sub.get_publisher_count() >= 2),
        ('probe → 어댑터 /pharmacy/dispense 서비스', probe.dispense.service_is_ready),
        ('probe → 어댑터 /sim/reset 서비스', probe.reset.service_is_ready),
    ]
    for sub in probe.request_subs:
        matched.append((f'어댑터 → probe {sub.topic_name}', lambda sub=sub: sub.get_publisher_count() >= 1))
    if pick_notice:
        matched.append(('어댑터 → probe /isaac/pharmacy/pick_notice',
                        lambda: probe.notice_sub.get_publisher_count() >= 1))
    if probe.observation_pub is not None:
        matched.append(('probe → 어댑터 /isaac/pharmacy/belt_observation',
                        lambda: probe.observation_pub.get_subscription_count() >= 1))
        matched.append(('어댑터 → probe /pharmacy/belt/observation',
                        lambda: probe.observation_sub.get_publisher_count() >= 1))
    if probe.cabinet_pub is not None:
        matched += [
            ('probe → 어댑터 /isaac/evaluator/cabinet', lambda: probe.cabinet_pub.get_subscription_count() >= 1),
            ('어댑터 → probe /evaluator/cabinet', lambda: probe.cabinet_sub.get_publisher_count() >= 1)]
    if probe.pouches_pub is not None:
        matched += [
            ('probe → 어댑터 /isaac/amr_1/pouches', lambda: probe.pouches_pub.get_subscription_count() >= 1),
            ('어댑터 → probe /amr_1/sim/pouches', lambda: probe.pouches_sub.get_publisher_count() >= 1),
            ('probe → 어댑터 /isaac/amr_1/tag_reads', lambda: probe.tag_pub.get_subscription_count() >= 1),
            ('어댑터 → probe /amr_1/sim/tag_reads', lambda: probe.tag_sub.get_publisher_count() >= 1)]
    if probe.gripper_pub is not None:
        matched += [
            ('probe → 어댑터 /isaac/amr_1/gripper/state', lambda: probe.gripper_pub.get_subscription_count() >= 1),
            ('어댑터 → probe /amr_1/gripper/state', lambda: probe.gripper_sub.get_publisher_count() >= 1),
            ('probe → 어댑터 /amr_1/gripper/command_seq', lambda: probe.command_pub.get_subscription_count() >= 1),
            ('어댑터 → probe /isaac/amr_1/gripper/command_seq', lambda: probe.command_sub.get_publisher_count() >= 1)]
    return matched


@contextlib.contextmanager
def adapter(listen=True, pick_notice=True, extra=(), belt_observation=False, gripper=False, sensors=False,
            sensor_reliability=heartbeat_qos, match=True, cabinet=False):
    assert_no_leftovers()
    rclpy.init()
    executor = MultiThreadedExecutor(num_threads=8)
    nodes = []
    thread = None
    try:
        nodes.append(IsaacAdapter(parameter_overrides=[
            Parameter('dispense_timeout_s', value=DISPENSE_TIMEOUT_S),
            Parameter('reset_timeout_s', value=RESET_TIMEOUT_S),
            Parameter('pick_notice', value=pick_notice),
            Parameter('belt_observation', value=belt_observation),
            Parameter('gripper_command_seq', value=gripper),
            Parameter('sim_pouches', value=sensors),
            Parameter('sim_tag_reads', value=sensors),
            Parameter('sim_cabinet', value=cabinet), *extra]))
        probe = IsaacProbe(listen=listen, observation=belt_observation, gripper=gripper, sensors=sensors,
                           sensor_reliability=sensor_reliability, cabinet=cabinet)
        probe.adapter = nodes[0]
        nodes.append(probe)
        for node in nodes:
            executor.add_node(node)
        thread = threading.Thread(target=executor.spin, daemon=True)
        thread.start()
        # QoS 가 안 맞는 회차는 매칭이 안 되는 것이 정상이라 그 확인을 건너뛴다.
        if match:
            wait_for_discovery({'probe': probe}, checks=matching_checks(probe, pick_notice))
        else:
            time.sleep(1.0)
        yield probe
    finally:
        teardown_nodes(executor, thread, nodes)


def dispense_request(request_id='r002-0001', order_id='ord-0001'):
    return Dispense.Request(request_id=request_id, order_id=order_id)


def test_dispense_passes_the_isaac_answer_through():
    with adapter() as probe:
        probe.answer = lambda topic, r: isaac_json.dispense_response(r['request_id'], r['order_id'], True)
        _, accepted = probe.call(probe.dispense, dispense_request())
        probe.answer = lambda topic, r: isaac_json.dispense_response(
            r['request_id'], r['order_id'], False, 'belt_occupied')
        _, rejected = probe.call(probe.dispense, dispense_request('r002-0002', 'ord-0002'))
        sent = [text for kind, text in probe.requests if kind == 'dispense']

    assert (accepted.accepted, accepted.message) == (True, '')
    assert (rejected.accepted, rejected.message) == (False, 'belt_occupied')
    assert sent[0] == '{"order_id":"ord-0001","request_id":"r002-0001","v":1}'     # 표의 예시와 글자까지 같다


def test_answers_do_not_queue_behind_the_other_isaac_inputs():
    """Dispense·Reset 응답 구독은 벨트·이벤트·센서 구독과 다른 콜백 그룹이다.

    9/24 c95e8f7 10건 #6: 스테이지가 곧바로 답했는데 어댑터가 10 s 안에 못 받아 not_ready 가 세 번 났다.
    서비스 콜백이 기다리는 응답이 한 상호배타 그룹의 다른 입력 뒤에 줄을 섰다고 본다.
    """
    with adapter(sensors=True) as probe:
        groups = {sub.topic_name: sub.callback_group for sub in probe.adapter.subscriptions}
    answers = {groups['/isaac/pharmacy/dispense_response'], groups['/isaac/sim/reset_response']}
    others = {group for topic, group in groups.items()
              if topic not in ('/isaac/pharmacy/dispense_response', '/isaac/sim/reset_response')}
    assert answers.isdisjoint(others)


@pytest.mark.parametrize('message', ['pool_exhausted', 'belt_jammed'])
def test_a_reject_message_is_passed_through_at_once(message):
    """거부 message 를 not_ready 로 바꾸거나 시한까지 기다리지 않고 그대로 넘긴다.

    pool_exhausted 는 9/24 부터 계약 2.1 이다(warn 없음). 계약 밖 값(belt_jammed)은 warn 하고 넘긴다.
    """
    with adapter() as probe:
        probe.answer = lambda topic, r: isaac_json.dispense_response(
            r['request_id'], r['order_id'], False, message)
        elapsed, response = probe.call(probe.dispense, dispense_request())

    assert (response.accepted, response.message) == (False, message)
    assert elapsed < DISPENSE_TIMEOUT_S, f'{elapsed:.2f} s'


@pytest.mark.parametrize('case', ['silent', 'malformed', 'other_order', 'other_request', 'no_isaac'])
def test_dispense_failures_become_a_rejection_within_the_timeout(case):
    answers = {
        'silent': lambda r: None,
        'malformed': lambda r: '{"accepted":true,"request_id":"' + r['request_id'] + '"}',
        'other_order': lambda r: isaac_json.dispense_response(r['request_id'], 'ord-0009', True),
        'other_request': lambda r: isaac_json.dispense_response('r999-0001', r['order_id'], True),
    }
    with adapter(listen=case != 'no_isaac') as probe:
        if case in answers:
            probe.answer = lambda topic, r: answers[case](r)
        elapsed, response = probe.call(probe.dispense, dispense_request())

    # other_order 도 기다리는 요청이 없는 응답이라 버리고 시한까지 기다린다. 앞 주문의 늦은 응답일 수 있어서다.
    assert (response.accepted, response.message) == (False, 'not_ready')
    assert DISPENSE_TIMEOUT_S * 0.8 <= elapsed <= DISPENSE_TIMEOUT_S + 1.0, f'{elapsed:.2f} s'


def test_a_late_answer_for_the_previous_order_does_not_answer_the_next():
    """request_id 는 트립 ID 라 한 트립의 주문이 같은 값을 쓴다. 앞 주문의 늦은 응답이 다음 주문을 거부로 채우면
    Isaac 이 실제로 받은 다음 주문의 응답은 버려진다(orchestrator 는 재호출하고 벨트는 이미 점유)."""
    with adapter() as probe:
        probe.answer = lambda topic, r: None
        _, first = probe.call(probe.dispense, dispense_request('r002-0001', 'ord-0001'))

        def late_then_right(topic, r):
            probe.dispense_response.publish(String(data=isaac_json.dispense_response('r002-0001', 'ord-0001', True)))
            return isaac_json.dispense_response(r['request_id'], r['order_id'], True)

        probe.answer = late_then_right
        elapsed, second = probe.call(probe.dispense, dispense_request('r002-0001', 'ord-0002'))

    assert (first.accepted, first.message) == (False, 'not_ready')
    assert (second.accepted, second.message) == (True, '')
    assert elapsed < DISPENSE_TIMEOUT_S, f'{elapsed:.2f} s'


def test_empty_request_id_is_not_sent():
    with adapter() as probe:
        probe.answer = lambda topic, r: isaac_json.dispense_response(r['request_id'], r['order_id'], True)
        elapsed, response = probe.call(probe.dispense, dispense_request(request_id=''))
        time.sleep(0.3)
        sent = list(probe.requests)

    assert (response.accepted, response.message) == (False, 'not_ready')
    assert elapsed < DISPENSE_TIMEOUT_S and not sent


@pytest.mark.parametrize('case', ['ok', 'failed', 'other_epoch', 'silent'])
def test_reset_answers(case):
    answers = {
        'ok': lambda r: isaac_json.reset_response(r['epoch'], True),
        'failed': lambda r: RESET_RESPONSE_FAILED,                   # 표의 예시(epoch 3)
        'other_epoch': lambda r: isaac_json.reset_response(r['epoch'] + 1, True),
        'silent': lambda r: None,
    }
    with adapter() as probe:
        probe.answer = lambda topic, r: answers[case](r)
        elapsed, response = probe.call(probe.reset, Reset.Request(epoch=3))

    if case == 'ok':
        assert (response.ok, response.message) == (True, '')
    elif case == 'failed':
        assert (response.ok, response.message) == (False, 'injected_failure')
    else:
        assert not response.ok and response.message.startswith('isaac_adapter:'), response.message
        assert RESET_TIMEOUT_S * 0.8 <= elapsed <= RESET_TIMEOUT_S + 1.0, f'{elapsed:.2f} s'


def test_belt_and_events_carry_the_json_stamp_and_epoch():
    with adapter() as probe:
        wait_until(lambda: probe.count_subscribers('/isaac/events') >= 1, 5.0, '어댑터가 /isaac/events 를 안 본다')
        probe.belt.publish(String(data='{"at_end":true}'))                           # 형식 오류: 버린다
        probe.belt.publish(String(data=BELT_AT_END))
        wait_until(lambda: probe.belts, 5.0, '/pharmacy/belt 가 없다')
        probe.isaac_events.publish(String(data=EVENT_DISPENSED))
        probe.isaac_events.publish(String(data=isaac_json.event(5, 0, 'POUCH_AT_END', 'r001-0001', 'ord-0001', 3)))
        probe.isaac_events.publish(String(data=isaac_json.event(6, 0, 'RESET_DONE', '', '', 3)))   # 표 밖 이름: 버린다
        wait_until(lambda: len([e for e in probe.events if e.robot_id == 'dispenser']) >= 2, 5.0, '/events 가 없다')
        time.sleep(0.5)
        belts = list(probe.belts)
        events = [e for e in probe.events if e.robot_id == 'dispenser']

    belt = belts[0]
    assert len(belts) == 1
    assert (belt.header.stamp.sec, belt.header.stamp.nanosec) == (123, 450000000)
    assert (belt.occupied, belt.at_end, belt.order_id) == (True, True, 'ord-0001')
    assert [(e.name, e.epoch, e.header.stamp.sec, e.header.stamp.nanosec, e.request_id, e.order_id)
            for e in events] == [('DISPENSED', 3, 118, 200000000, 'r002-0001', 'ord-0001'),
                                 ('POUCH_AT_END', 3, 5, 0, 'r001-0001', 'ord-0001')]


def test_epoch_zero_from_isaac_becomes_the_current_epoch():
    """Isaac 은 첫 리셋 전 epoch 0 을 싣는다. 계약 epoch 는 1 부터라 어댑터가 본 epoch 로 바꾼다."""
    with adapter() as probe:
        wait_until(lambda: probe.count_subscribers('/isaac/events') >= 1, 5.0, '어댑터가 /isaac/events 를 안 본다')
        probe.isaac_events.publish(String(data=isaac_json.event(1, 0, 'DISPENSED', 'r001-0001', 'ord-0001', 0)))
        wait_until(lambda: [e for e in probe.events if e.robot_id == 'dispenser'], 5.0, '/events 가 없다')
        first = [e for e in probe.events if e.robot_id == 'dispenser'][0].epoch
        marker = Event(name='RESET_BEGIN', robot_id='orchestrator', epoch=4)
        probe.event_pub.publish(marker)
        time.sleep(0.5)
        probe.isaac_events.publish(String(data=isaac_json.event(2, 0, 'DISPENSED', 'r004-0001', 'ord-0001', 0)))
        wait_until(lambda: len([e for e in probe.events if e.robot_id == 'dispenser']) >= 2, 5.0, '/events 가 없다')
        second = [e for e in probe.events if e.robot_id == 'dispenser'][1].epoch

    assert (first, second) == (1, 4)


def stamps(messages):
    return [(m.header.stamp.sec, m.header.stamp.nanosec) for m in messages]


def test_belt_from_an_earlier_epoch_is_dropped():
    """BeltState 에 epoch 칸이 없어 어댑터가 계약 4절의 "이전 epoch BeltState 버림"을 대신 지킨다."""
    with adapter() as probe:
        wait_until(lambda: probe.count_subscribers('/isaac/pharmacy/belt') >= 1, 5.0, '어댑터가 belt 를 안 본다')
        probe.event_pub.publish(Event(name='RESET_BEGIN', robot_id='orchestrator', epoch=3))
        wait_until(lambda: probe.adapter._epoch == 3, 5.0, '어댑터가 epoch 3 을 못 봤다')
        # belt 는 depth 1(최신값 하나)이라 앞의 것이 처리되기 전에 다음을 보내면 덮인다. 하나씩 결과를 보고 보낸다.
        # 고정 0.2 s 간격은 부하에서 덮여 9/18 반복 30회 중 1회 셋이 안 됐다.
        for sec, epoch, done in ((1, 2, lambda: probe.adapter.dropped['stale_belt'] == 1),
                                 (2, 3, lambda: len(probe.belts) == 1),
                                 (3, 0, lambda: len(probe.belts) == 2),
                                 (4, 4, lambda: len(probe.belts) == 3)):
            probe.belt.publish(String(data=isaac_json.belt(sec, 0, False, False, '', epoch)))
            wait_until(done, 5.0, f'belt sec={sec} epoch={epoch} 의 결과가 없다(버림 {dict(probe.adapter.dropped)}, '
                                  f'옮김 {stamps(probe.belts)})')
        time.sleep(0.3)
        forwarded = stamps(probe.belts)
        dropped = dict(probe.adapter.dropped)

    assert forwarded == [(2, 0), (3, 0), (4, 0)], forwarded       # epoch 2 는 버림, 0 은 현재 epoch 로 봄
    assert dropped['stale_belt'] == 1


def test_isaac_events_received_again_are_not_republished():
    """transient local 재수신. 같은 (epoch, name, stamp, order_id, request_id) 는 한 번만 /events 로 간다."""
    with adapter() as probe:
        wait_until(lambda: probe.count_subscribers('/isaac/events') >= 1, 5.0, '어댑터가 /isaac/events 를 안 본다')
        # 어댑터가 다시 뜬 경우: 이미 /events 에 있는 dispenser 이벤트(POUCH_AT_END, 표 예시와 같은 키)
        probe.event_pub.publish(Event(name='POUCH_AT_END', robot_id='dispenser', epoch=3, request_id='r002-0001',
                                      order_id='ord-0001', header=Header(stamp=Time(sec=123, nanosec=450000000))))
        time.sleep(0.5)
        probe.isaac_events.publish(String(data=EVENT_DISPENSED))
        probe.isaac_events.publish(String(data=EVENT_DISPENSED))                   # 같은 것 한 번 더
        probe.isaac_events.publish(String(data=EVENT_POUCH_AT_END))                # /events 에 이미 있던 것
        probe.isaac_events.publish(String(data=isaac_json.event(119, 0, 'DISPENSED', 'r002-0001', 'ord-0001', 3)))
        wait_until(lambda: len([e for e in probe.events if e.robot_id == 'dispenser']) >= 3, 5.0, '/events 가 없다')
        time.sleep(0.5)
        events = [(e.name, e.header.stamp.sec) for e in probe.events if e.robot_id == 'dispenser']
        dropped = dict(probe.adapter.dropped)

    assert events == [('POUCH_AT_END', 123), ('DISPENSED', 118), ('DISPENSED', 119)], events
    assert dropped['duplicate_event'] == 2


def picked(order_id='ord-0001', epoch=3, robot_id='amr_1', sec=123, nanosec=850000000):
    return Event(name='POUCH_PICKED', robot_id=robot_id, epoch=epoch, order_id=order_id,
                 header=Header(stamp=Time(sec=sec, nanosec=nanosec)))


@pytest.mark.parametrize('enabled', [True, False])
def test_pick_notice_only_for_the_loading_pick(enabled):
    """amr_* 의 POUCH_PICKED 중 현재 epoch 이고 마지막 belt 가 at_end·같은 order_id 인 것만.

    (epoch, order_id) 당 한 번.
    """
    with adapter(pick_notice=enabled) as probe:
        wait_until(lambda: probe.count_subscribers('/isaac/pharmacy/belt') >= 1, 5.0, '어댑터가 belt 를 안 본다')
        if enabled:
            wait_until(lambda: probe.count_publishers('/isaac/pharmacy/pick_notice') >= 1, 5.0,
                       'pick_notice 발행자 없음')
        probe.event_pub.publish(Event(name='RESET_BEGIN', robot_id='orchestrator', epoch=3))
        wait_until(lambda: probe.adapter._epoch == 3, 5.0, '어댑터가 epoch 3 을 못 봤다')
        probe.event_pub.publish(picked())                          # belt 를 아직 못 봤다: 안 보냄
        time.sleep(0.3)
        probe.belt.publish(String(data=BELT_AT_END))               # epoch 3, at_end, ord-0001
        wait_until(lambda: probe.belts, 5.0, '/pharmacy/belt 가 없다')
        for event in (picked(robot_id='dispenser'),                # 팔이 아니다
                      picked(order_id='ord-0002'),                 # 벨트 끝 봉투가 아니다
                      picked(epoch=2),                             # 현재 epoch 가 아니다
                      picked(),                                    # 보낸다
                      picked(sec=124)):                            # 같은 (epoch, order_id): 한 번만
            probe.event_pub.publish(event)
            time.sleep(0.2)
        time.sleep(0.5)
        notices = list(probe.notices)
        count = probe.adapter.pick_notices

    if enabled:
        assert notices == [PICK_NOTICE_OK] and count == 1, notices          # 표의 예시와 글자까지 같다
    else:
        assert notices == [] and count == 0, notices


MISSING = (Parameter('isaac_missing_after_s', value=0.5), Parameter('isaac_missing_warn_every_s', value=2.0))


def test_warns_while_isaac_is_missing_and_says_once_when_it_is_back():
    """요청 토픽 구독자 0 이고 belt 무소식이면 warn_every_s 마다 WARN, 구독자가 생기면 INFO 한 번."""
    with adapter(listen=False, extra=MISSING) as probe:
        node = probe.adapter
        wait_until(lambda: node.missing_warnings >= 2, 6.0, '두 번째 WARN 이 없다')
        warnings_before = node.missing_warnings
        assert node.isaac_missing
        assert node.recovered_notices == 0
        probe.create_subscription(String, '/isaac/pharmacy/dispense_request', lambda m: None, reliable_qos(10))
        wait_until(lambda: not node.isaac_missing, 5.0, '구독자가 생겨도 여전히 안 보인다고 한다')
        time.sleep(2.5)                                      # 다시 보인 뒤로 WARN·INFO 가 더 나지 않는다
        after = (node.missing_warnings, node.recovered_notices, node.isaac_missing)

    assert warnings_before in (2, 3)                         # 0.5 s 뒤 첫 WARN, 2 s 마다(1 s 판정 주기)
    assert after == (warnings_before, 1, False)


def test_belt_alone_counts_as_isaac_seen_and_its_silence_warns_again():
    with adapter(listen=False, extra=MISSING) as probe:
        node = probe.adapter
        # fixture 의 매칭 확인이 isaac_missing_after_s(0.5 s)보다 길 수 있어 첫 belt 전 기동 무소식 WARN 은 날 수 있다.
        # 첫 belt 를 받고 판정 주기(1 s)가 한 번 지난 뒤부터, belt 를 계속 내는 2 s 동안 WARN 이 늘지 않는지 본다.

        def belts_for(seconds):                              # 구독자 없이 belt 만 낸다(형식은 받는 쪽이 따짐)
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                probe.belt.publish(String(data=BELT_AT_END))
                time.sleep(0.2)

        belts_for(0.4)
        wait_until(lambda: node._belt_wall is not None, 5.0, '어댑터가 belt 를 못 받았다')
        belts_for(1.2)
        before = node.missing_warnings
        belts_for(2.0)
        after_belts = node.missing_warnings
        quiet = (after_belts - before, node.isaac_missing)
        wait_until(lambda: node.missing_warnings > after_belts, 5.0, 'belt 가 끊겨도 WARN 이 없다')

    assert quiet == (0, False)


def test_no_warning_while_isaac_listens():
    with adapter(listen=True, extra=MISSING) as probe:
        time.sleep(2.5)
        seen = (probe.adapter.missing_warnings, probe.adapter.recovered_notices, probe.adapter.isaac_missing)

    assert seen == (0, 0, False)


# 계약 11.6 BeltObservation(opt-in) ------------------------------------------------------------

def observation(epoch=1, seq=10, **fields):
    values = {'request_id': 'r001-0001', 'order_id': 'ord-0001', 'mode': 2, 'occupancy': 2, 'pouch_zone': 2,
              'pouch_motion': 2, 'belt_command_applied': 2, **fields}
    return String(data=isaac_json.belt_observation(123, 450000000, epoch, seq, **values))


def send_observation(probe, message, counter):
    """하나 보내고 옮겨졌거나 버려질 때까지 기다린다(H 는 depth 1 이라 연달아 보내면 덮인다)."""
    before = counter()
    probe.observation_pub.publish(message)
    wait_until(lambda: counter() > before, 3.0, '관측이 옮겨지거나 버려지지 않았다')


def handled(probe):
    return len(probe.observations) + sum(v for k, v in probe.adapter.dropped.items() if k.startswith('observation_'))


def test_belt_observation_is_off_by_default():
    with adapter() as probe:
        time.sleep(0.3)
        subscribers = probe.count_subscribers('/isaac/pharmacy/belt_observation')
        publishers = probe.count_publishers('/pharmacy/belt/observation')
    assert (subscribers, publishers) == (0, 0)


def test_belt_observation_is_converted_field_by_field():
    with adapter(belt_observation=True) as probe:
        send_observation(probe, observation(), lambda: handled(probe))
        [out] = list(probe.observations)
    assert (out.header.stamp.sec, out.header.stamp.nanosec) == (123, 450000000)
    assert (out.epoch, out.seq, out.request_id, out.order_id) == (1, 10, 'r001-0001', 'ord-0001')
    assert (out.mode, out.occupancy, out.pouch_zone, out.pouch_motion, out.belt_motion, out.belt_command_applied) == (
        BeltObservation.MODE_SIM_SENSOR, BeltObservation.OCCUPANCY_OCCUPIED, BeltObservation.ZONE_END,
        BeltObservation.MOTION_STOPPED, BeltObservation.MOTION_UNKNOWN, BeltObservation.APPLIED_STOP)


def test_belt_observation_drops_are_counted_and_nothing_else_is_passed():
    """형식 오류·epoch 0·seq 역행·이전 epoch 는 버리고 센다. 같은 seq 반복과 다음 epoch 는 옮긴다."""
    with adapter(belt_observation=True) as probe:
        count = lambda: handled(probe)  # noqa: E731
        send_observation(probe, observation(seq=10), count)
        send_observation(probe, observation(seq=9), count)                     # 역행
        send_observation(probe, observation(seq=10), count)                    # 같은 표본 반복은 옮긴다
        send_observation(probe, observation(epoch=0, seq=11), count)           # epoch 를 추측하지 않는다
        send_observation(probe, String(data='{"v":1}'), count)                 # 형식 오류
        send_observation(probe, observation(mode=7), count)                    # enum 범위 밖
        send_observation(probe, observation(epoch=2, seq=1), count)            # 새 epoch 는 seq 가 작아도 옮긴다
        send_observation(probe, observation(epoch=1, seq=99), count)           # 이미 옮긴 epoch 2 보다 이전
        passed = [(o.epoch, o.seq) for o in probe.observations]
        dropped = {k: v for k, v in probe.adapter.dropped.items() if k.startswith('observation_')}
    assert passed == [(1, 10), (1, 10), (2, 1)]
    assert dropped == {'observation_malformed': 2, 'observation_bad_epoch': 1, 'observation_stale_epoch': 1,
                       'observation_seq_regression': 1}



# 계약 11.6 GripperState·GripperCommand(opt-in) ------------------------------------------------

def test_gripper_relay_is_off_by_default():
    with adapter() as probe:
        time.sleep(0.3)
        counts = (probe.count_subscribers('/isaac/amr_1/gripper/state'), probe.count_publishers('/amr_1/gripper/state'),
                  probe.count_subscribers('/amr_1/gripper/command_seq'),
                  probe.count_publishers('/isaac/amr_1/gripper/command_seq'))
    assert counts == (0, 0, 0, 0)


def test_gripper_state_is_converted_and_bad_states_are_dropped():
    def state(epoch=1, seq=10, last=0, value=2):
        return String(data=isaac_json.gripper_state(124, 0, epoch, seq, last, state=value, mode=1))

    with adapter(gripper=True) as probe:
        count = lambda: len(probe.gripper_states) + sum(  # noqa: E731
            v for k, v in probe.adapter.dropped.items() if k.startswith('gripper_state_'))
        for message in (state(seq=10, last=3), state(seq=9), state(epoch=0), String(data='{"v":1}'),
                        state(value=5), state(epoch=2, seq=1), state(epoch=1, seq=50)):
            before = count()
            probe.gripper_pub.publish(message)
            wait_until(lambda b=before: count() > b, 3.0, '그리퍼 상태가 옮겨지거나 버려지지 않았다')
        passed = [(s.epoch, s.seq, s.last_applied_command_seq, s.state, s.mode) for s in probe.gripper_states]
        dropped = {k: v for k, v in probe.adapter.dropped.items() if k.startswith('gripper_state_')}
    assert passed == [(1, 10, 3, GripperState.STATE_HELD, GripperState.MODE_VIRTUAL),
                      (2, 1, 0, GripperState.STATE_HELD, GripperState.MODE_VIRTUAL)]
    assert dropped == {'gripper_state_malformed': 2, 'gripper_state_bad_epoch': 1, 'gripper_state_stale_epoch': 1,
                       'gripper_state_seq_regression': 1}


def test_gripper_command_is_passed_to_isaac_unless_its_epoch_is_zero_or_old():
    def command(epoch, seq, close=True):
        msg = GripperCommand(epoch=epoch, command_seq=seq, close=close)
        msg.header.stamp = Time(sec=124, nanosec=0)
        return msg

    with adapter(gripper=True) as probe:
        count = lambda: len(probe.gripper_commands) + sum(  # noqa: E731
            v for k, v in probe.adapter.dropped.items() if k.startswith('gripper_command_'))
        for message in (command(1, 1), command(1, 1), command(0, 2)):         # 같은 seq 도 옮긴다(멱등은 Isaac)
            before = count()
            probe.command_pub.publish(message)
            wait_until(lambda b=before: count() > b, 3.0, '명령이 옮겨지거나 버려지지 않았다')
        probe.event_pub.publish(Event(name=Event.RESET_DONE, epoch=2, robot_id='orchestrator'))
        wait_until(lambda: probe.adapter._epoch == 2, 3.0, '어댑터 epoch 가 2 가 되지 않았다')
        before = count()
        probe.command_pub.publish(command(1, 3))                                # 이전 epoch
        wait_until(lambda: count() > before, 3.0, '이전 epoch 명령이 버려지지 않았다')
        sent = [json.loads(text) for text in probe.gripper_commands]
        dropped = {k: v for k, v in probe.adapter.dropped.items() if k.startswith('gripper_command_')}
    assert [(c['epoch'], c['command_seq'], c['close'], c['stamp']) for c in sent] == [
        (1, 1, True, {'sec': 124, 'nanosec': 0})] * 2
    assert dropped == {'gripper_command_bad_epoch': 1, 'gripper_command_stale_epoch': 1}


# -- 시뮬 센서(비전 규격 v2) ------------------------------------------------------------

#: 계약 토픽. 이 노드는 여기에 **절대 내지 않는다** — 작성자는 perception 하나다.
CAMERA_TOPICS = ('/amr_1/hand_camera/pouches', '/amr_1/hand_camera/tag_reads')


def pouches(epoch=1, detections=(), frame_id='amr_1/base_link'):
    return String(data=isaac_json.pouches(123, 450000000, epoch, frame_id, detections))


def one_detection(order_id='ord-0001', confidence=0.91, position=(0.1, 0.2, 0.3)):
    return isaac_json.detection(order_id, confidence, position)


def tag_read(epoch=1, kind='patient', status='ok', tag_id='pt-1001'):
    return String(data=isaac_json.tag_read(123, 0, epoch, 'amr_1/base_link', 'bed_a1', kind, tag_id, status))


def sensor_handled(probe, prefix, received):
    return len(received) + sum(v for k, v in probe.adapter.dropped.items() if k.startswith(f'{prefix}_'))


def send_sensor(probe, publisher, message, counter):
    before = counter()
    publisher.publish(message)
    wait_until(lambda: counter() > before, 3.0, '센서 메시지가 옮겨지거나 버려지지 않았다')


def test_sim_sensors_are_off_by_default():
    with adapter() as probe:
        time.sleep(0.3)
        listening = [probe.count_subscribers(t) for t in ('/isaac/amr_1/pouches', '/isaac/amr_1/tag_reads')]
        publishing = [probe.count_publishers(t) for t in ('/amr_1/sim/pouches', '/amr_1/sim/tag_reads')]
    assert (listening, publishing) == ([0, 0], [0, 0])


def test_the_adapter_never_publishes_on_the_contract_camera_topics():
    """`hand_camera/*` 의 작성자는 perception 하나다. 센서를 켜도 그 이름에는 내지 않는다."""
    with adapter(sensors=True) as probe:
        send_sensor(probe, probe.pouches_pub, pouches(detections=[one_detection()]),
                    lambda: sensor_handled(probe, 'pouches', probe.pouch_arrays))
        send_sensor(probe, probe.tag_pub, tag_read(), lambda: sensor_handled(probe, 'tag_read', probe.tag_reads))
        counts = [probe.count_publishers(topic) for topic in CAMERA_TOPICS]
    assert counts == [0, 0]


def test_pouches_are_converted_field_by_field():
    with adapter(sensors=True) as probe:
        send_sensor(probe, probe.pouches_pub, pouches(detections=[one_detection()]),
                    lambda: sensor_handled(probe, 'pouches', probe.pouch_arrays))
        [out] = list(probe.pouch_arrays)
    assert (out.header.stamp.sec, out.header.stamp.nanosec) == (123, 450000000)
    assert out.header.frame_id == 'amr_1/base_link'
    [one] = out.detections
    assert (one.order_id, round(one.confidence, 3), one.slot_index) == ('ord-0001', 0.91, -1)
    # 원소에는 프레임이 없다. 최상위 값을 그대로 쓴다(팔이 그 stamp 의 TF 로 base 로 옮긴다).
    assert (one.header.frame_id, one.header.stamp.sec) == ('amr_1/base_link', 123)
    assert (round(one.pose.position.x, 3), round(one.pose.position.y, 3), round(one.pose.position.z, 3)) == (
        0.1, 0.2, 0.3)
    assert round(one.pose.orientation.w, 3) == 1.0


def test_an_empty_detection_list_is_relayed_as_is():
    """빈 목록이 와야 팔이 시한을 다 기다리지 않고 "검출 0건" 으로 닫는다. 어댑터가 삼키지 않는다."""
    with adapter(sensors=True) as probe:
        send_sensor(probe, probe.pouches_pub, pouches(),
                    lambda: sensor_handled(probe, 'pouches', probe.pouch_arrays))
        [out] = list(probe.pouch_arrays)
    assert list(out.detections) == []


def test_a_zero_pose_is_relayed_not_filled_in():
    """0 은 값이다. 어댑터가 0 으로 채우지도, 0 이라고 버리지도 않는다 — 판정은 팔이 한다."""
    with adapter(sensors=True) as probe:
        send_sensor(probe, probe.pouches_pub, pouches(detections=[one_detection(position=(0.0, 0.0, 0.0))]),
                    lambda: sensor_handled(probe, 'pouches', probe.pouch_arrays))
        [out] = list(probe.pouch_arrays)
    assert (out.detections[0].pose.position.x, out.detections[0].pose.position.y) == (0.0, 0.0)


def test_sensor_drops_are_counted_like_the_other_isaac_topics():
    """형식 오류·epoch 0·지난 epoch 는 버리고 센다. 센서에는 seq 가 없어 역행 판정은 없다."""
    with adapter(sensors=True) as probe:
        count = lambda: sensor_handled(probe, 'pouches', probe.pouch_arrays)  # noqa: E731
        send_sensor(probe, probe.pouches_pub, pouches(epoch=2), count)             # 옮긴다(현재 epoch 1 이상)
        send_sensor(probe, probe.pouches_pub, pouches(epoch=0), count)             # epoch 를 추측하지 않는다
        send_sensor(probe, probe.pouches_pub, String(data='{"v":1}'), count)       # 형식 오류
        send_sensor(probe, probe.pouches_pub,
                    String(data=isaac_json.dumps({'v': 1, 'stamp': {'sec': 1, 'nanosec': 0}, 'epoch': 1,
                                                  'frame_id': '', 'detections': []})), count)   # 빈 frame_id
        dropped = {k: v for k, v in probe.adapter.dropped.items() if k.startswith('pouches_')}
        relayed = probe.adapter.relayed['pouches']
    assert relayed == 1
    assert dropped == {'pouches_malformed': 2, 'pouches_bad_epoch': 1, 'pouches_stale_epoch': 0}


def test_tag_reads_are_converted_and_unknown_values_are_dropped():
    with adapter(sensors=True) as probe:
        count = lambda: sensor_handled(probe, 'tag_read', probe.tag_reads)  # noqa: E731
        send_sensor(probe, probe.tag_pub, tag_read(), count)
        send_sensor(probe, probe.tag_pub, tag_read(kind='doctor'), count)          # 모르는 값은 버린다
        send_sensor(probe, probe.tag_pub, tag_read(tag_id=''), count)              # 비우면 안 된다
        [out] = list(probe.tag_reads)
        dropped = probe.adapter.dropped['tag_read_malformed']
    assert (out.kind, out.status, out.tag_id) == (TagRead.KIND_PATIENT, TagRead.STATUS_OK, 'pt-1001')
    assert out.header.frame_id == 'amr_1/base_link'
    assert dropped == 2


def test_the_adapter_subscribes_to_the_sensors_with_H():
    """구독 QoS 가 H(reliable·volatile·depth 1)다. **스테이지가 맞춰야 하는 값이 이것이다.**

    9/21 실습27 P6 에서 스테이지가 best effort 로 내 한 건도 안 왔다(RELIABILITY 불일치).
    말로 "둘 다 heartbeat 다" 라고 맞췄는데 `heartbeat_qos()` 는 best effort 가 아니었다.
    그래서 값을 시험에 박는다.
    """
    with adapter(sensors=True) as probe:
        profiles = {}
        for info in (probe.adapter.get_subscriptions_info_by_topic('/isaac/amr_1/pouches')
                     + probe.adapter.get_subscriptions_info_by_topic('/isaac/amr_1/tag_reads')):
            if info.node_name == 'isaac_adapter':
                profiles[info.topic_type] = info.qos_profile
        assert profiles, '어댑터의 구독을 못 찾았다'
        for profile in profiles.values():
            assert profile.reliability == ReliabilityPolicy.RELIABLE
            assert profile.durability == DurabilityPolicy.VOLATILE
            # depth 는 보지 않는다. 그래프의 endpoint 정보에는 history·depth 가 실려 오지 않아
            # 0 으로 읽힌다(CI 에서 확인). 호환을 가르는 것은 reliability·durability 다.


def test_a_best_effort_stage_publisher_does_not_reach_the_adapter():
    """규격을 지켜도 QoS 가 어긋나면 한 건도 안 온다. 실습27 P6 을 그대로 재현한다."""
    with adapter(sensors=True, sensor_reliability=sensor_qos, match=False) as probe:
        probe.pouches_pub.publish(pouches(detections=[one_detection()]))
        time.sleep(1.5)
        relayed = probe.adapter.relayed['pouches']
        dropped = sum(v for k, v in probe.adapter.dropped.items() if k.startswith('pouches_'))
        matched = probe.pouches_pub.get_subscription_count()
    # 어댑터가 버린 것도 아니다. **애초에 오지 않는다** — 그래서 로그에도 안 남는다.
    assert (relayed, dropped, matched) == (0, 0, 0)


def _stage_module(name, missing):
    """`sim/standalone/p3sim/<name>.py` 를 패키지 안 모듈로 읽는다.

    belt 가 `from .conveyor_end import` 를 쓴다(#549). 파일 경로로 읽으면 상대 import 가 깨진다.
    """
    import importlib
    import sys
    from pathlib import Path
    standalone = Path(__file__).resolve().parents[3] / 'sim' / 'standalone'
    if not (standalone / 'p3sim' / f'{name}.py').exists():
        pytest.skip(f'{missing}: {standalone}/p3sim/{name}.py')
    sys.path.insert(0, str(standalone))
    try:
        return importlib.import_module(f'p3sim.{name}')
    finally:
        sys.path.remove(str(standalone))


def stage_qos_table():
    """스테이지의 토픽별 QoS 표(`sim/standalone/p3sim/bridge.py` 의 `QOS`).

    말이 아니라 **코드끼리** 맞추려고 그 파일을 직접 읽는다(Isaac import 가 없어 그냥 읽힌다).
    설치본으로 돌 때처럼 파일이 없으면 시험을 건너뛴다.
    """
    return _stage_module('bridge', '스테이지 QoS 표가 없다')


@pytest.mark.parametrize('topic', ['/isaac/amr_1/pouches', '/isaac/amr_1/tag_reads'])
def test_the_stage_publish_qos_is_compatible_with_the_adapter_subscription(topic):
    """호환 규칙 한 줄: **구독이 RELIABLE 이면 발행도 RELIABLE 이어야 한다**(반대는 된다).

    9/21 실습27 P6: 스테이지가 best_effort 로 내고 어댑터가 RELIABLE 로 받아 **한 건도 안 왔다**.
    양쪽이 각자 자기 값만 시험해서 호환성은 아무도 안 봤다. 여기서 두 표를 맞댄다.
    """
    bridge = stage_qos_table()
    publish_reliability, publish_durability, _depth = bridge.QOS[topic]
    with adapter(sensors=True) as probe:
        [info] = [row for row in probe.adapter.get_subscriptions_info_by_topic(topic)
                  if row.node_name == 'isaac_adapter']
        profile = info.qos_profile
    if profile.reliability == ReliabilityPolicy.RELIABLE:
        assert publish_reliability == 'reliable', (
            f'{topic}: 어댑터가 RELIABLE 로 받는데 스테이지가 {publish_reliability} 로 낸다. '
            '한 건도 오지 않는다(실습27 P6).')
    if profile.durability == DurabilityPolicy.TRANSIENT_LOCAL:
        assert publish_durability == 'transient_local', f'{topic}: durability 가 어긋난다'


def stage_belt_rules():
    """스테이지의 거부 문자열·이벤트 이름(`sim/standalone/p3sim/belt.py`). Isaac import 가 없다."""
    return _stage_module('belt', '스테이지 벨트 규칙이 없다')


def test_the_dispense_rejection_strings_are_the_same_on_both_sides():
    """계약 2.1 의 거부 셋. 9/21 에 사람이 `belt_busy` 로 잘못 말했고 사람이 잡았다 — 기계가 잡게 한다.

    한쪽이 문자열을 바꾸면 어댑터는 그것을 "계약 밖 message" 로 보고 warn 한 뒤 **그대로 넘긴다**.
    orchestrator 는 거부를 message 와 상관없이 같게 다루므로 회차는 그냥 돌고, 어긋난 것은
    로그 한 줄로만 남는다.
    """
    belt = stage_belt_rules()
    assert set(isaac_json.DISPENSE_REJECT_MESSAGES) == set(belt.DISPENSE_REJECTIONS)


def test_the_isaac_event_names_are_the_same_on_both_sides():
    """Isaac 이 내는 이벤트는 둘뿐이다(계약 2.6). 한쪽이 이름을 바꾸면 어댑터가 형식 오류로 버린다."""
    belt = stage_belt_rules()
    assert set(isaac_json.EVENT_NAMES) == {belt.DISPENSED, belt.POUCH_AT_END}
    assert isaac_json.EVENT_ROBOT_ID == belt.ROBOT_ID


def test_the_sensor_topic_names_are_one_value_on_both_sides():
    """토픽 이름이 두 벌이다(내 상수와 스테이지 상수). 두 벌이면 한쪽만 바뀐다."""
    bridge = stage_qos_table()
    from rokey_p3_bringup.isaac_adapter import POUCHES, TAG_READS
    assert (POUCHES, TAG_READS) == (bridge.POUCHES, bridge.TAG_READS)


@pytest.mark.parametrize('mine,theirs', [
    ('POUCHES_FIELDS', 'POUCHES'),
    ('TAG_READ_FIELDS', 'TAG_READS'),
])
def test_the_json_field_lists_are_the_same_on_both_sides(mine, theirs):
    """`isaac_json` 의 필드 목록과 스테이지 `SCHEMAS` 가 같은 집합이어야 한다.

    어댑터는 정의에 없는 필드도, 빠진 필드도 형식 오류로 버린다. 그래서 한쪽이 필드를
    더하면 그 순간부터 **모든 메시지가 버려진다** — 그때 로그에는 형식 오류만 보이고
    "누가 표를 바꿨나" 는 안 보인다.
    """
    bridge = stage_qos_table()
    assert set(getattr(isaac_json, mine)) == set(bridge.SCHEMAS[getattr(bridge, theirs)])


def test_the_detection_element_fields_are_the_same_on_both_sides():
    bridge = stage_qos_table()
    assert set(isaac_json.POUCH_DETECTION_FIELDS) == set(bridge.DETECTION_SCHEMA)


def cabinet_json(epoch=1, cabinet_id='bed_a1/cabinet', order_id='ord-0001', present=True):
    return String(data=isaac_json.cabinet(123, 450000000, epoch, cabinet_id, order_id, present))


def test_sim_cabinet_is_off_by_default():
    with adapter() as probe:
        time.sleep(0.3)
        assert (probe.count_subscribers('/isaac/evaluator/cabinet'),
                probe.count_publishers('/evaluator/cabinet')) == (0, 0)


def test_the_cabinet_observation_is_relayed_including_the_false_transition():
    """`present` 의 true→false 도 그대로 옮긴다(봉투를 꺼낸 것이다). 어댑터가 판정하지 않는다."""
    with adapter(sensors=True, cabinet=True) as probe:
        count = lambda: sensor_handled(probe, 'cabinet', probe.cabinets)  # noqa: E731
        send_sensor(probe, probe.cabinet_pub, cabinet_json(present=True), count)
        send_sensor(probe, probe.cabinet_pub, cabinet_json(present=False), count)
        seen = [(row.cabinet_id, row.order_id, row.present) for row in probe.cabinets]
    assert seen == [('bed_a1/cabinet', 'ord-0001', True), ('bed_a1/cabinet', 'ord-0001', False)]


def test_a_cabinet_observation_without_a_cabinet_id_is_dropped():
    """어느 보관함인지 모르는 관측은 버린다. run 기록의 SUCCESS 근거라 채워 넣지 않는다(계약 8절)."""
    with adapter(sensors=True, cabinet=True) as probe:
        count = lambda: sensor_handled(probe, 'cabinet', probe.cabinets)  # noqa: E731
        send_sensor(probe, probe.cabinet_pub, cabinet_json(cabinet_id=''), count)
        relayed, dropped = probe.adapter.relayed['cabinet'], probe.adapter.dropped['cabinet_malformed']
    assert (relayed, dropped) == (0, 1)


def test_the_stage_cabinet_qos_is_compatible_with_the_adapter_subscription():
    bridge = stage_qos_table()
    publish_reliability, publish_durability, _depth = bridge.QOS['/isaac/evaluator/cabinet']
    with adapter(sensors=True, cabinet=True) as probe:
        [info] = [row for row in probe.adapter.get_subscriptions_info_by_topic('/isaac/evaluator/cabinet')
                  if row.node_name == 'isaac_adapter']
        profile = info.qos_profile
    if profile.reliability == ReliabilityPolicy.RELIABLE:
        assert publish_reliability == 'reliable'
    if profile.durability == DurabilityPolicy.TRANSIENT_LOCAL:
        assert publish_durability == 'transient_local', (
            '어댑터가 latched 로 받는데 스테이지가 volatile 로 낸다 — 늦게 붙으면 지난 값을 못 받는다')


def test_the_cabinet_fields_are_the_same_on_both_sides():
    bridge = stage_qos_table()
    assert set(isaac_json.CABINET_FIELDS) == set(bridge.SCHEMAS['/isaac/evaluator/cabinet'])
