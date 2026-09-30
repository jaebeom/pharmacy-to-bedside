"""L1. isaac_json 형식.

예시는 sim/README.md "Isaac ↔ ROS 어댑터 인터페이스 (JSON, v1)"(5ac8628)의 11개를 글자 그대로 옮겼다.
"""

import json
from pathlib import Path

import pytest

from rokey_p3_bringup import isaac_json

# sim/README.md 5ac8628 의 예시 11개. 바꾸지 않는다.
DISPENSE_REQUEST_OK = '{"order_id":"ord-0001","request_id":"r002-0001","v":1}'
DISPENSE_REQUEST_EMPTY_ID = '{"order_id":"ord-0001","request_id":"","v":1}'
DISPENSE_RESPONSE_ACCEPTED = '{"accepted":true,"message":"","order_id":"ord-0001","request_id":"r002-0001","v":1}'
DISPENSE_RESPONSE_REJECTED = \
    '{"accepted":false,"message":"belt_occupied","order_id":"ord-0002","request_id":"r002-0002","v":1}'
RESET_REQUEST_OK = '{"epoch":3,"v":1}'
RESET_RESPONSE_OK = '{"epoch":3,"message":"","ok":true,"v":1}'
RESET_RESPONSE_FAILED = '{"epoch":3,"message":"injected_failure","ok":false,"v":1}'
BELT_AT_END = ('{"at_end":true,"epoch":3,"occupied":true,"order_id":"ord-0001",'
               '"stamp":{"nanosec":450000000,"sec":123},"v":1}')
BELT_EMPTY = '{"at_end":false,"epoch":3,"occupied":false,"order_id":"","stamp":{"nanosec":0,"sec":130},"v":1}'
EVENT_DISPENSED = ('{"detail":"","epoch":3,"name":"DISPENSED","order_id":"ord-0001","request_id":"r002-0001",'
                   '"robot_id":"dispenser","stamp":{"nanosec":200000000,"sec":118},"v":1}')
EVENT_POUCH_AT_END = ('{"detail":"","epoch":3,"name":"POUCH_AT_END","order_id":"ord-0001","request_id":"r002-0001",'
                      '"robot_id":"dispenser","stamp":{"nanosec":450000000,"sec":123},"v":1}')


def test_builders_write_the_readme_examples_byte_for_byte():
    """어댑터와 가짜 Isaac 이 만드는 문자열이 표의 예시와 글자까지 같다(키 정렬, 공백 없음)."""
    assert isaac_json.dispense_request('r002-0001', 'ord-0001') == DISPENSE_REQUEST_OK
    assert isaac_json.reset_request(3) == RESET_REQUEST_OK
    assert isaac_json.dispense_response('r002-0001', 'ord-0001', True) == DISPENSE_RESPONSE_ACCEPTED
    assert isaac_json.dispense_response('r002-0002', 'ord-0002', False, 'belt_occupied') == DISPENSE_RESPONSE_REJECTED
    assert isaac_json.reset_response(3, True) == RESET_RESPONSE_OK
    assert isaac_json.reset_response(3, False, 'injected_failure') == RESET_RESPONSE_FAILED
    assert isaac_json.belt(123, 450000000, True, True, 'ord-0001', 3) == BELT_AT_END
    assert isaac_json.belt(130, 0, False, False, '', 3) == BELT_EMPTY
    assert isaac_json.event(118, 200000000, 'DISPENSED', 'r002-0001', 'ord-0001', 3) == EVENT_DISPENSED
    assert isaac_json.event(123, 450000000, 'POUCH_AT_END', 'r002-0001', 'ord-0001', 3) == EVENT_POUCH_AT_END


def test_parsers_read_the_readme_examples():
    assert isaac_json.parse_dispense_request(DISPENSE_REQUEST_OK) == {'request_id': 'r002-0001', 'order_id': 'ord-0001'}
    assert isaac_json.parse_reset_request(RESET_REQUEST_OK) == {'epoch': 3}
    assert isaac_json.parse_dispense_response(DISPENSE_RESPONSE_ACCEPTED) == {
        'request_id': 'r002-0001', 'order_id': 'ord-0001', 'accepted': True, 'message': '', 'contract_message': True}
    assert isaac_json.parse_dispense_response(DISPENSE_RESPONSE_REJECTED) == {
        'request_id': 'r002-0002', 'order_id': 'ord-0002', 'accepted': False, 'message': 'belt_occupied',
        'contract_message': True}
    assert isaac_json.parse_reset_response(RESET_RESPONSE_OK) == {'epoch': 3, 'ok': True, 'message': ''}
    assert isaac_json.parse_reset_response(RESET_RESPONSE_FAILED) == {
        'epoch': 3, 'ok': False, 'message': 'injected_failure'}
    assert isaac_json.parse_belt(BELT_AT_END) == {
        'stamp': (123, 450000000), 'occupied': True, 'at_end': True, 'order_id': 'ord-0001', 'epoch': 3}
    assert isaac_json.parse_belt(BELT_EMPTY) == {
        'stamp': (130, 0), 'occupied': False, 'at_end': False, 'order_id': '', 'epoch': 3}
    assert isaac_json.parse_event(EVENT_DISPENSED) == {
        'stamp': (118, 200000000), 'name': 'DISPENSED', 'request_id': 'r002-0001', 'order_id': 'ord-0001',
        'robot_id': 'dispenser', 'epoch': 3, 'detail': ''}
    assert isaac_json.parse_event(EVENT_POUCH_AT_END)['stamp'] == (123, 450000000)


def test_the_malformed_example_is_not_sent():
    """표의 형식 오류 예시(request_id 비어 있음). Isaac 이 응답하지 않으므로 어댑터가 보내지 않는다."""
    with pytest.raises(isaac_json.IsaacJsonError):
        isaac_json.parse_dispense_request(DISPENSE_REQUEST_EMPTY_ID)
    with pytest.raises(isaac_json.IsaacJsonError):
        isaac_json.dispense_request('', 'ord-0001')


def mutate(text, **changes):
    data = json.loads(text)
    for key, value in changes.items():
        if value is KeyError:
            data.pop(key)
        else:
            data[key] = value
    return json.dumps(data)


@pytest.mark.parametrize('parser,text', [
    (isaac_json.parse_dispense_response, 'not json'),
    (isaac_json.parse_dispense_response, '[1, 2]'),
    (isaac_json.parse_dispense_response, mutate(DISPENSE_RESPONSE_ACCEPTED, v=2)),
    (isaac_json.parse_dispense_response, mutate(DISPENSE_RESPONSE_ACCEPTED, v=True)),
    (isaac_json.parse_dispense_response, mutate(DISPENSE_RESPONSE_ACCEPTED, extra='x')),
    (isaac_json.parse_dispense_response, mutate(DISPENSE_RESPONSE_ACCEPTED, message=KeyError)),
    (isaac_json.parse_dispense_response, mutate(DISPENSE_RESPONSE_ACCEPTED, accepted='true')),
    (isaac_json.parse_dispense_response, mutate(DISPENSE_RESPONSE_ACCEPTED, message='belt_occupied')),
    (isaac_json.parse_dispense_response, mutate(DISPENSE_RESPONSE_REJECTED, message='')),
    (isaac_json.parse_dispense_response, mutate(DISPENSE_RESPONSE_ACCEPTED, request_id='')),
    (isaac_json.parse_reset_response, mutate(RESET_RESPONSE_OK, epoch=-1)),
    (isaac_json.parse_reset_response, mutate(RESET_RESPONSE_OK, epoch=3.0)),
    (isaac_json.parse_reset_response, mutate(RESET_RESPONSE_OK, epoch=2 ** 32)),
    (isaac_json.parse_reset_response, mutate(RESET_RESPONSE_OK, message='done')),
    (isaac_json.parse_belt, mutate(BELT_AT_END, stamp=123.45)),
    (isaac_json.parse_belt, mutate(BELT_AT_END, stamp={'sec': 1})),
    (isaac_json.parse_belt, mutate(BELT_AT_END, stamp={'sec': 1, 'nanosec': 1_000_000_000})),
    (isaac_json.parse_belt, mutate(BELT_AT_END, epoch=KeyError)),
    (isaac_json.parse_event, mutate(EVENT_DISPENSED, name='RESET_DONE')),
    (isaac_json.parse_event, mutate(EVENT_DISPENSED, robot_id='isaac')),
    (isaac_json.parse_event, mutate(EVENT_DISPENSED, detail=None)),
])
def test_malformed_messages_are_rejected(parser, text):
    with pytest.raises(isaac_json.IsaacJsonError):
        parser(text)


def test_pool_exhausted_is_a_contract_rejection():
    """9/24 계약 2.1: 풀 고갈(pool_exhausted)은 계약 거부다. 병원 10건 회차에서 아홉째 주문이 여기에 닿았다.

    그 전에는 계약 밖이라 어댑터가 warn 했다.
    """
    parsed = isaac_json.parse_dispense_response(mutate(DISPENSE_RESPONSE_REJECTED, message='pool_exhausted'))
    assert (parsed['accepted'], parsed['message'], parsed['contract_message']) == (False, 'pool_exhausted', True)


def test_a_reject_message_outside_the_contract_is_not_a_format_error():
    """계약 네 값 밖의 거부는 형식 오류가 아니고 계약 밖 표시만 붙는다(어댑터가 그대로 넘기고 warn)."""
    parsed = isaac_json.parse_dispense_response(mutate(DISPENSE_RESPONSE_REJECTED, message='belt_jammed'))
    assert (parsed['accepted'], parsed['message'], parsed['contract_message']) == (False, 'belt_jammed', False)


# sim/README.md 415e4ae 의 pick_notice 예시 두 개. 바꾸지 않는다.
PICK_NOTICE_OK = \
    '{"epoch":3,"order_id":"ord-0001","source":"POUCH_PICKED","stamp":{"nanosec":850000000,"sec":123},"v":1}'
PICK_NOTICE_OLD_EPOCH = \
    '{"epoch":2,"order_id":"ord-0001","source":"POUCH_PICKED","stamp":{"nanosec":850000000,"sec":123},"v":1}'


def test_pick_notice_examples():
    """형식은 둘 다 맞다(epoch 2 를 무시하는 것은 Isaac 판단). 만들기는 예시와 바이트까지 같다."""
    assert isaac_json.pick_notice(123, 850000000, 3, 'ord-0001') == PICK_NOTICE_OK
    assert isaac_json.pick_notice(123, 850000000, 2, 'ord-0001') == PICK_NOTICE_OLD_EPOCH
    assert isaac_json.parse_pick_notice(PICK_NOTICE_OK) == {
        'stamp': (123, 850000000), 'epoch': 3, 'order_id': 'ord-0001', 'source': 'POUCH_PICKED'}
    assert isaac_json.parse_pick_notice(PICK_NOTICE_OLD_EPOCH)['epoch'] == 2
    with pytest.raises(isaac_json.IsaacJsonError):
        isaac_json.pick_notice(123, 0, 3, '')                                   # order_id 가 비면 보내지 않는다
    for text in (mutate(PICK_NOTICE_OK, source='POUCH_PLACED'), mutate(PICK_NOTICE_OK, order_id=''),
                 mutate(PICK_NOTICE_OK, extra=1), mutate(PICK_NOTICE_OK, stamp=KeyError)):
        with pytest.raises(isaac_json.IsaacJsonError):
            isaac_json.parse_pick_notice(text)


# 계약 11.6 BeltObservation(opt-in). 시뮬 #276 의 JSON 표와 같은 필드·정수값이다.
BELT_OBSERVATION_AT_END = (
    '{"belt_command_applied":2,"belt_motion":0,"epoch":3,"mode":2,"occupancy":2,"order_id":"ord-0001",'
    '"pouch_motion":2,"pouch_zone":2,"request_id":"r003-0001","seq":4120,'
    '"stamp":{"nanosec":450000000,"sec":123},"v":1}')
MSG_DIR = Path(__file__).resolve().parents[2] / 'rokey_p3_interfaces' / 'msg'


def msg_fields_and_enums(name='BeltObservation'):
    """msg 파일의 필드 이름과, 상수 접두마다 가장 큰 값."""
    fields, largest = [], {}
    for line in (MSG_DIR / f'{name}.msg').read_text().splitlines():
        code = line.split('#', 1)[0].strip()
        if not code:
            continue
        kind, rest = code.split(None, 1)
        if '=' in rest:
            prefix, value = rest.split('=')[0].split('_', 1)[0], int(rest.split('=')[1])
            largest[prefix] = max(largest.get(prefix, 0), value)
        else:
            fields.append(rest)
    return fields, largest


def test_belt_observation_example_round_trips():
    built = isaac_json.belt_observation(123, 450000000, 3, 4120, 'r003-0001', 'ord-0001', mode=2, occupancy=2,
                                        pouch_zone=2, pouch_motion=2, belt_command_applied=2)
    assert built == BELT_OBSERVATION_AT_END
    assert isaac_json.parse_belt_observation(BELT_OBSERVATION_AT_END) == {
        'stamp': (123, 450000000), 'epoch': 3, 'seq': 4120, 'request_id': 'r003-0001', 'order_id': 'ord-0001',
        'mode': 2, 'occupancy': 2, 'pouch_zone': 2, 'pouch_motion': 2, 'belt_motion': 0, 'belt_command_applied': 2}


def test_belt_observation_fields_and_enum_ranges_match_the_msg():
    """JSON 필드 = msg 필드(header.stamp 는 stamp), enum 가장 큰 값 = msg 상수의 가장 큰 값."""
    fields, largest = msg_fields_and_enums()
    json_fields = [f for f in isaac_json.BELT_OBSERVATION_FIELDS if f not in ('v', 'stamp')]
    assert fields == ['header', *json_fields]
    by_field = {'mode': 'MODE', 'occupancy': 'OCCUPANCY', 'pouch_zone': 'ZONE', 'pouch_motion': 'MOTION',
                'belt_motion': 'MOTION', 'belt_command_applied': 'APPLIED'}
    assert {f: largest[p] for f, p in by_field.items()} == isaac_json.OBSERVATION_ENUMS


@pytest.mark.parametrize('change', [
    {'mode': 4}, {'occupancy': -1}, {'pouch_zone': 4}, {'pouch_motion': 3}, {'belt_motion': 3},
    {'belt_command_applied': 3}, {'mode': True}, {'occupancy': 1.0}, {'seq': 2 ** 32}, {'seq': -1},
    {'epoch': '3'}, {'request_id': None}, {'pouch_zone': KeyError}, {'extra': 1}, {'v': 2},
])
def test_belt_observation_rejects_bad_fields(change):
    with pytest.raises(isaac_json.IsaacJsonError):
        isaac_json.parse_belt_observation(mutate(BELT_OBSERVATION_AT_END, **change))


# 계약 11.6 GripperState·GripperCommand(opt-in). 시뮬 #278 의 JSON 표와 같은 필드·정수값이다.
GRIPPER_STATE_HELD = ('{"epoch":3,"last_applied_command_seq":7,"mode":1,"seq":4121,"stamp":{"nanosec":0,"sec":124},'
                      '"state":2,"v":1}')
GRIPPER_COMMAND_CLOSE = '{"close":true,"command_seq":7,"epoch":3,"stamp":{"nanosec":0,"sec":124},"v":1}'


def test_gripper_examples_round_trip():
    assert isaac_json.gripper_state(124, 0, 3, 4121, 7, state=2, mode=1) == GRIPPER_STATE_HELD
    assert isaac_json.parse_gripper_state(GRIPPER_STATE_HELD) == {
        'stamp': (124, 0), 'epoch': 3, 'seq': 4121, 'last_applied_command_seq': 7, 'state': 2, 'mode': 1}
    assert isaac_json.gripper_command(124, 0, 3, 7, True) == GRIPPER_COMMAND_CLOSE
    assert isaac_json.parse_gripper_command(GRIPPER_COMMAND_CLOSE) == {
        'stamp': (124, 0), 'epoch': 3, 'command_seq': 7, 'close': True}


def test_gripper_fields_and_enum_ranges_match_the_msgs():
    state_fields, state_largest = msg_fields_and_enums('GripperState')
    assert state_fields == ['header', *(f for f in isaac_json.GRIPPER_STATE_FIELDS if f not in ('v', 'stamp'))]
    assert {'state': state_largest['STATE'], 'mode': state_largest['MODE']} == isaac_json.GRIPPER_ENUMS
    command_fields, _ = msg_fields_and_enums('GripperCommand')
    assert command_fields == ['header', *(f for f in isaac_json.GRIPPER_COMMAND_FIELDS if f not in ('v', 'stamp'))]


@pytest.mark.parametrize('change', [
    {'state': 3}, {'mode': -1}, {'state': True}, {'seq': 2 ** 32}, {'last_applied_command_seq': -1},
    {'mode': KeyError}, {'extra': 1},
])
def test_gripper_state_rejects_bad_fields(change):
    with pytest.raises(isaac_json.IsaacJsonError):
        isaac_json.parse_gripper_state(mutate(GRIPPER_STATE_HELD, **change))


@pytest.mark.parametrize('change', [{'close': 1}, {'command_seq': -1}, {'epoch': KeyError}, {'extra': 1}])
def test_gripper_command_rejects_bad_fields(change):
    with pytest.raises(isaac_json.IsaacJsonError):
        isaac_json.parse_gripper_command(mutate(GRIPPER_COMMAND_CLOSE, **change))


# -- 시뮬 센서(비전 규격 v2, 2026-09-21) ------------------------------------------------

# 실습25(master02, 84f82ac)에서 `ros2 topic echo /isaac/amr_1/pouches` 로 받은 **원문 그대로**.
# 규격대로 만든 문자열이 아니라 스테이지가 실제로 낸 줄이다(맥마클2 제공, 2026-09-21).
STAGE_EMPTY = ('{"detections":[],"epoch":1,"frame_id":"amr_1/ur_arm_base_link",'
               '"stamp":{"nanosec":500001017,"sec":19},"v":1}')
STAGE_ONE = ('{"detections":[{"confidence":1.0,"order_id":"ord-0001","pose":{"orientation":'
             '{"w":0.9989315867424011,"x":-5.6220277322438506e-09,"y":-4.6744816906141295e-09,'
             '"z":-0.04621347039937973},"position":{"x":-0.44496941566467285,"y":0.44248111248016353,'
             '"z":-0.14499994516372683}},"slot_index":-1}],"epoch":1,'
             '"frame_id":"amr_1/ur_arm_base_link","stamp":{"nanosec":66669539,"sec":55},"v":1}')

# 인식표는 실습25 에서 한 건도 안 나왔다 — 그 회차는 `--amr` 이 없어 "서 있는 침상" 이 없다(시뮬).
# 그래서 이 줄만 **스테이지의 인코더를 통과한 문자열**이고 회차에서 받은 것이 아니다.
STAGE_TAG = ('{"epoch":1,"frame_id":"amr_1/ur_arm_base_link","kind":"patient",'
             '"stamp":{"nanosec":340000000,"sec":12},"status":"ok","tag_id":"pt-1001","v":1,'
             '"zone_id":"bed_a1"}')

POUCHES_ONE = isaac_json.pouches(12, 500000000, 3, 'amr_1/base_link',
                                 [isaac_json.detection('ord-0001', 0.91, (0.1, 0.2, 0.3))])
POUCHES_EMPTY = isaac_json.pouches(12, 500000000, 3, 'amr_1/base_link')
TAG_READ_OK = isaac_json.tag_read(12, 0, 3, 'amr_1/base_link', 'bed_a1', 'patient', 'pt-1001', 'ok')


def test_the_real_stage_lines_parse():
    """실습25 의 원문 두 줄. 규격대로 만든 값과 기계가 내는 값이 다를 수 있어서 원문을 박아 둔다.

    **진짜인 것**(바꾸면 안 된다): 키 순서(알파벳), 공백 없는 구분자, 필드 이름·타입,
    `slot_index: -1`, `v: 1`, `stamp` 가 `{sec, nanosec}` 중첩, 검출 원소에 `v`·`stamp`·`frame_id` 가
    없다는 것, `frame_id` 값.
    **예시일 뿐인 것**: `pose` 수치·`stamp`·`epoch`·`order_id`. 실제 자세는 L3 에서 처음 본다.
    그래서 **값으로 비교하고 문자열로 비교하지 않는다**(`-0.30` 이 `-0.3` 으로 나간다, 시뮬).
    """
    empty = isaac_json.parse_pouches(STAGE_EMPTY)
    assert (empty['detections'], empty['epoch']) == ([], 1)
    assert empty['frame_id'] == 'amr_1/ur_arm_base_link'      # 결정 47 뒤의 이름이다
    assert empty['stamp'] == (19, 500001017)

    one = isaac_json.parse_pouches(STAGE_ONE)
    [detection] = one['detections']
    assert (detection['order_id'], detection['confidence'], detection['slot_index']) == ('ord-0001', 1.0, -1)
    # 자세는 지수 표기(-5.6e-09)로 온다. 그대로 실수로 읽는다.
    assert detection['pose']['orientation'][0] == -5.6220277322438506e-09
    assert detection['pose']['position'][2] == -0.14499994516372683


def test_the_real_stage_tag_line_parses():
    """키 순서·구분자·필드 이름은 진짜다. 값(zone·환자·stamp)은 예시다 — L3 에서 처음 본다."""
    parsed = isaac_json.parse_tag_read(STAGE_TAG)
    constants = msg_constants('TagRead')
    assert (parsed['kind'], parsed['status']) == (constants['KIND_PATIENT'], constants['STATUS_OK'])
    assert (parsed['tag_id'], parsed['zone_id']) == ('pt-1001', 'bed_a1')
    assert parsed['frame_id'] == 'amr_1/ur_arm_base_link'


def test_pouches_round_trip():
    parsed = isaac_json.parse_pouches(POUCHES_ONE)
    assert (parsed['stamp'], parsed['epoch'], parsed['frame_id']) == ((12, 500000000), 3, 'amr_1/base_link')
    [one] = parsed['detections']
    assert (one['order_id'], one['confidence'], one['slot_index']) == ('ord-0001', 0.91, -1)
    assert one['pose'] == {'position': (0.1, 0.2, 0.3), 'orientation': (0.0, 0.0, 0.0, 1.0)}


def test_an_empty_detection_list_is_normal():
    """빈 목록이 와야 팔이 시한을 다 기다리지 않고 "검출 0건" 으로 닫는다."""
    assert isaac_json.parse_pouches(POUCHES_EMPTY)['detections'] == []


def test_a_zero_pose_passes_through():
    """0 은 값이다. 거리를 못 정했다는 판정은 팔이 한다 — 어댑터가 가로채지 않는다."""
    text = isaac_json.pouches(1, 0, 1, 'f', [isaac_json.detection('', 0.0, (0.0, 0.0, 0.0))])
    [one] = isaac_json.parse_pouches(text)['detections']
    assert one['pose']['position'] == (0.0, 0.0, 0.0)


@pytest.mark.parametrize('change', [
    {'frame_id': ''}, {'frame_id': KeyError}, {'epoch': -1}, {'detections': {}}, {'detections': KeyError},
    {'stamp': KeyError}, {'extra': 1},
])
def test_pouches_rejects_bad_top_level_fields(change):
    with pytest.raises(isaac_json.IsaacJsonError):
        isaac_json.parse_pouches(mutate(POUCHES_ONE, **change))


@pytest.mark.parametrize('change', [
    {'pose': None},                      # null 은 버린다. 0 으로 채우지 않는다
    {'pose': {'position': {'x': 0.0, 'y': 0.0, 'z': 0.0}}},            # orientation 이 없다
    {'pose': {'position': {'x': 0.0, 'y': 0.0}, 'orientation': {'x': 0.0, 'y': 0.0, 'z': 0.0, 'w': 1.0}}},
    {'confidence': 1.7}, {'confidence': '0.9'}, {'slot_index': 0.5}, {'order_id': 1},
    {'confidence': KeyError}, {'extra': 1},
])
def test_pouches_rejects_bad_detection_fields(change):
    data = json.loads(POUCHES_ONE)
    for key, value in change.items():
        if value is KeyError:
            data['detections'][0].pop(key)
        else:
            data['detections'][0][key] = value
    with pytest.raises(isaac_json.IsaacJsonError):
        isaac_json.parse_pouches(json.dumps(data))


def msg_constants(name):
    """msg 파일의 상수 이름 -> 값. ROS 를 import 하지 않는다(이 파일의 규칙)."""
    out = {}
    for line in (MSG_DIR / f'{name}.msg').read_text().splitlines():
        code = line.split('#', 1)[0].strip()
        if '=' in code:
            field, value = code.split(None, 1)[1].split('=')
            out[field.strip()] = int(value)
    return out


def test_tag_read_maps_strings_to_the_msg_constants():
    constants = msg_constants('TagRead')
    parsed = isaac_json.parse_tag_read(TAG_READ_OK)
    assert (parsed['kind'], parsed['status'], parsed['tag_id'], parsed['zone_id']) == (
        constants['KIND_PATIENT'], constants['STATUS_OK'], 'pt-1001', 'bed_a1')


@pytest.mark.parametrize('change', [
    {'kind': 'doctor'}, {'kind': 0}, {'status': 'OK'}, {'status': KeyError},
    {'tag_id': ''}, {'frame_id': ''}, {'extra': 1},
])
def test_tag_read_rejects_unknown_values(change):
    """모르는 값에 기본값을 조용히 넣지 않는다. 정수로 받지도 않는다(상수가 바뀌면 뜻이 달라진다)."""
    with pytest.raises(isaac_json.IsaacJsonError):
        isaac_json.parse_tag_read(mutate(TAG_READ_OK, **change))


def test_sensor_enum_tables_match_the_msg():
    """표가 msg 와 1:1 이다. msg 에 값이 늘면 여기서 걸린다."""
    constants = msg_constants('TagRead')
    assert {'patient': constants['KIND_PATIENT'], 'station': constants['KIND_STATION'],
            'pouch': constants['KIND_POUCH']} == isaac_json.TAG_KINDS
    assert {'ok': constants['STATUS_OK'],
            'unreadable': constants['STATUS_UNREADABLE']} == isaac_json.TAG_STATUSES
