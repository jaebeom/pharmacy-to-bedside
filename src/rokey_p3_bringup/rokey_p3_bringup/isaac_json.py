"""Isaac ↔ ROS 어댑터의 JSON 형식. ROS 를 import 하지 않는다.

기준 문서는 sim/README.md "Isaac ↔ ROS 어댑터 인터페이스 (JSON, v1)" 표다(Simu 소유, 5ac8628 에서 읽음.
pick_notice 는 415e4ae 에서 더해졌고 v 는 1 그대로다).
- 모든 메시지는 JSON 객체 하나이고 "v": 1 이다. 정의에 없는 필드가 있거나 빠진 필드가 있으면 형식 오류다.
- stamp 는 {"sec": int, "nanosec": int} sim time. epoch 는 uint32.
- Isaac 은 /isaac/events 에 DISPENSED·POUCH_AT_END 만 내고 robot_id 는 dispenser 다.

파서는 형식 오류면 IsaacJsonError 를 내고, 맞으면 필드 dict 를 돌려준다. 만들기는 키를 정렬해 쓴다(Isaac 과 같다).
"""

import json

VERSION = 1
UINT32_MAX = 2 ** 32 - 1
#: 계약 2.1 의 Dispense 거부 넷. pool_exhausted(스테이지가 미리 만든 봉투가 다 나감)는 9/24 에 계약에 들어왔다.
DISPENSE_REJECT_MESSAGES = ('belt_occupied', 'unknown_order', 'not_ready', 'pool_exhausted')
EVENT_NAMES = ('DISPENSED', 'POUCH_AT_END')
EVENT_ROBOT_ID = 'dispenser'
PICK_SOURCES = ('POUCH_PICKED',)

DISPENSE_REQUEST_FIELDS = ('v', 'request_id', 'order_id')
DISPENSE_RESPONSE_FIELDS = ('v', 'request_id', 'order_id', 'accepted', 'message')
RESET_REQUEST_FIELDS = ('v', 'epoch')
RESET_RESPONSE_FIELDS = ('v', 'epoch', 'ok', 'message')
BELT_FIELDS = ('v', 'stamp', 'occupied', 'at_end', 'order_id', 'epoch')
EVENT_FIELDS = ('v', 'stamp', 'name', 'request_id', 'order_id', 'robot_id', 'epoch', 'detail')
PICK_NOTICE_FIELDS = ('v', 'stamp', 'epoch', 'order_id', 'source')
# 계약 11.6 BeltObservation(opt-in). 필드 이름과 enum 정수값은 BeltObservation.msg 와 같다. header.stamp 는 stamp 다.
BELT_OBSERVATION_FIELDS = ('v', 'stamp', 'epoch', 'seq', 'request_id', 'order_id', 'mode', 'occupancy', 'pouch_zone',
                           'pouch_motion', 'belt_motion', 'belt_command_applied')
OBSERVATION_ENUMS = {'mode': 3, 'occupancy': 2, 'pouch_zone': 3, 'pouch_motion': 2, 'belt_motion': 2,
                     'belt_command_applied': 2}  # 필드 → 가장 큰 값. 0 = UNKNOWN
# 계약 11.6 GripperState(Isaac → 어댑터)·GripperCommand(어댑터 → Isaac), opt-in. 시뮬 #278 의 JSON 표와 같다.
GRIPPER_STATE_FIELDS = ('v', 'stamp', 'epoch', 'seq', 'last_applied_command_seq', 'state', 'mode')
GRIPPER_ENUMS = {'state': 2, 'mode': 2}
GRIPPER_COMMAND_FIELDS = ('v', 'stamp', 'epoch', 'command_seq', 'close')
# 시뮬 센서(opt-in, K4·K5). 스테이지는 계약 타입을 만들 수 없어서(계약 67줄) JSON 으로 낸다.
# 어댑터가 /{ns}/sim/* 로 옮긴다. 계약 토픽(hand_camera/*)에는 내지 않는다 — 그 작성자는 perception 하나다.
POUCHES_FIELDS = ('v', 'stamp', 'epoch', 'frame_id', 'detections')
POUCH_DETECTION_FIELDS = ('order_id', 'confidence', 'pose', 'slot_index')
TAG_READ_FIELDS = ('v', 'stamp', 'epoch', 'frame_id', 'zone_id', 'kind', 'tag_id', 'status')
#: 문자열 → TagRead 상수. **모르는 값은 버린다**(정수로 받으면 상수가 바뀔 때 조용히 다른 뜻이 된다).
TAG_KINDS = {'patient': 0, 'station': 1, 'pouch': 2}
#: K5b 보관함 참값(opt-in). 계약 145-150·341줄의 `/evaluator/cabinet` 로 어댑터가 옮긴다.
#: run 기록의 SUCCESS 는 이 관측만이 근거다(계약 8절) — 팔의 주장으로 만들지 않는다.
CABINET_FIELDS = ('v', 'stamp', 'epoch', 'cabinet_id', 'order_id', 'present')
TAG_STATUSES = {'ok': 0, 'unreadable': 1}


class IsaacJsonError(ValueError):
    """형식 오류. 메시지는 로그 한 줄에 그대로 쓴다."""


def dumps(fields):
    return json.dumps(fields, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def _object(text, fields):
    try:
        data = json.loads(text)
    except (TypeError, ValueError) as error:
        raise IsaacJsonError(f'JSON 이 아니다: {error}') from None
    if not isinstance(data, dict):
        raise IsaacJsonError(f'JSON 객체가 아니다: {type(data).__name__}')
    missing = [name for name in fields if name not in data]
    extra = sorted(name for name in data if name not in fields)
    if missing or extra:
        raise IsaacJsonError(f'필드가 표와 다르다. 빠짐 {missing}, 정의 밖 {extra}')
    if type(data['v']) is not int or data['v'] != VERSION:
        raise IsaacJsonError(f'v={data["v"]!r} 는 {VERSION} 이 아니다')
    return data


def _string(data, name, non_empty=False):
    value = data[name]
    if not isinstance(value, str):
        raise IsaacJsonError(f'{name} 이 문자열이 아니다: {value!r}')
    if non_empty and not value:
        raise IsaacJsonError(f'{name} 이 비어 있다')
    return value


def _bool(data, name):
    value = data[name]
    if not isinstance(value, bool):
        raise IsaacJsonError(f'{name} 이 bool 이 아니다: {value!r}')
    return value


def _uint32(data, name):
    value = data[name]
    if type(value) is not int or not 0 <= value <= UINT32_MAX:
        raise IsaacJsonError(f'{name} 이 uint32 가 아니다: {value!r}')
    return value


def _float(data, name, low=None, high=None):
    value = data[name]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise IsaacJsonError(f'{name} 이 수가 아니다: {value!r}')
    if (low is not None and value < low) or (high is not None and value > high):
        raise IsaacJsonError(f'{name} 이 범위 밖이다: {value!r}')
    return float(value)


def _int(data, name):
    value = data[name]
    if type(value) is not int or isinstance(value, bool):
        raise IsaacJsonError(f'{name} 이 정수가 아니다: {value!r}')
    return value


def _vector(data, name, axes):
    """좌표 묶음. 키가 없거나 null 이면 형식 오류다. **0 으로 채우지 않는다**(비전 규격 v2)."""
    value = data[name]
    if not isinstance(value, dict) or sorted(value) != sorted(axes):
        raise IsaacJsonError(f'{name} 이 {sorted(axes)} 가 아니다: {value!r}')
    return tuple(_float(value, axis) for axis in axes)


def _pose(data, name):
    value = data[name]
    if not isinstance(value, dict) or sorted(value) != ['orientation', 'position']:
        raise IsaacJsonError(f'{name} 이 position·orientation 이 아니다: {value!r}')
    return {'position': _vector(value, 'position', ('x', 'y', 'z')),
            'orientation': _vector(value, 'orientation', ('x', 'y', 'z', 'w'))}


def _choice(data, name, table):
    value = data[name]
    if not isinstance(value, str) or value not in table:
        raise IsaacJsonError(f'{name} 이 {sorted(table)} 중 하나가 아니다: {value!r}')
    return table[value]


def _stamp(data):
    value = data['stamp']
    if not isinstance(value, dict) or sorted(value) != ['nanosec', 'sec']:
        raise IsaacJsonError(f'stamp 가 {{"sec","nanosec"}} 가 아니다: {value!r}')
    sec, nanosec = value['sec'], value['nanosec']
    if type(sec) is not int or type(nanosec) is not int or sec < 0 or not 0 <= nanosec < 1_000_000_000:
        raise IsaacJsonError(f'stamp 값이 맞지 않다: {value!r}')
    return sec, nanosec


# 어댑터 → Isaac ---------------------------------------------------------------

def dispense_request(request_id, order_id):
    """request_id 가 비었으면 Isaac 이 응답하지 않으므로 보내기 전에 막는다."""
    if not request_id:
        raise IsaacJsonError('request_id 가 비어 있다')
    return dumps({'v': VERSION, 'request_id': request_id, 'order_id': order_id})


def reset_request(epoch):
    return dumps({'v': VERSION, 'epoch': int(epoch)})


def pick_notice(sec, nanosec, epoch, order_id, source='POUCH_PICKED'):
    """팔이 낸 POUCH_PICKED 의 stamp·epoch·order_id 를 그대로. order_id 가 비면 보내지 않는다."""
    if not order_id:
        raise IsaacJsonError('order_id 가 비어 있다')
    if source not in PICK_SOURCES:
        raise IsaacJsonError(f'source {source!r} 는 {PICK_SOURCES} 가 아니다')
    return dumps({'v': VERSION, 'stamp': _stamp_fields(sec, nanosec), 'epoch': int(epoch), 'order_id': order_id,
                  'source': source})


def parse_pick_notice(text):
    data = _object(text, PICK_NOTICE_FIELDS)
    source = _string(data, 'source')
    if source not in PICK_SOURCES:
        raise IsaacJsonError(f'source {source!r} 는 {PICK_SOURCES} 가 아니다')
    return {'stamp': _stamp(data), 'epoch': _uint32(data, 'epoch'),
            'order_id': _string(data, 'order_id', non_empty=True), 'source': source}


def parse_dispense_request(text):
    data = _object(text, DISPENSE_REQUEST_FIELDS)
    return {'request_id': _string(data, 'request_id', non_empty=True), 'order_id': _string(data, 'order_id')}


def parse_reset_request(text):
    return {'epoch': _uint32(_object(text, RESET_REQUEST_FIELDS), 'epoch')}


# Isaac → 어댑터 ---------------------------------------------------------------

def parse_dispense_response(text):
    data = _object(text, DISPENSE_RESPONSE_FIELDS)
    accepted = _bool(data, 'accepted')
    message = _string(data, 'message')
    if accepted and message:
        raise IsaacJsonError(f'수락인데 message 가 비어 있지 않다: {message!r}')
    if not accepted and not message:
        raise IsaacJsonError('거부인데 message 가 비어 있다')
    # 계약 2.1 의 네 값 밖도 형식 오류로 버리지 않는다. 어댑터가 그대로 넘기고 warn 한다.
    return {'request_id': _string(data, 'request_id', non_empty=True), 'order_id': _string(data, 'order_id'),
            'accepted': accepted, 'message': message,
            'contract_message': accepted or message in DISPENSE_REJECT_MESSAGES}


def parse_reset_response(text):
    data = _object(text, RESET_RESPONSE_FIELDS)
    ok = _bool(data, 'ok')
    message = _string(data, 'message')
    if ok and message:
        raise IsaacJsonError(f'성공인데 message 가 비어 있지 않다: {message!r}')
    return {'epoch': _uint32(data, 'epoch'), 'ok': ok, 'message': message}


def parse_belt(text):
    data = _object(text, BELT_FIELDS)
    return {'stamp': _stamp(data), 'occupied': _bool(data, 'occupied'), 'at_end': _bool(data, 'at_end'),
            'order_id': _string(data, 'order_id'), 'epoch': _uint32(data, 'epoch')}


def parse_belt_observation(text):
    """`/isaac/pharmacy/belt_observation`. seq 는 uint32, enum 은 msg 의 범위 안이어야 한다."""
    data = _object(text, BELT_OBSERVATION_FIELDS)
    return {'stamp': _stamp(data), 'epoch': _uint32(data, 'epoch'), 'seq': _uint32(data, 'seq'),
            'request_id': _string(data, 'request_id'), 'order_id': _string(data, 'order_id'),
            **_enums(data, OBSERVATION_ENUMS)}


def _enums(data, enums):
    out = {}
    for name, largest in enums.items():
        value = data[name]
        if type(value) is not int or not 0 <= value <= largest:
            raise IsaacJsonError(f'{name} 이 0..{largest} 정수가 아니다: {value!r}')
        out[name] = value
    return out


def _detection(item, index):
    """검출 하나. 원소에는 v·stamp·frame_id 가 없다(최상위 하나를 쓴다)."""
    if not isinstance(item, dict):
        raise IsaacJsonError(f'detections[{index}] 가 객체가 아니다: {item!r}')
    missing = [name for name in POUCH_DETECTION_FIELDS if name not in item]
    extra = sorted(name for name in item if name not in POUCH_DETECTION_FIELDS)
    if missing or extra:
        raise IsaacJsonError(f'detections[{index}] 필드가 표와 다르다. 빠짐 {missing}, 정의 밖 {extra}')
    return {'order_id': _string(item, 'order_id'), 'confidence': _float(item, 'confidence', 0.0, 1.0),
            'pose': _pose(item, 'pose'), 'slot_index': _int(item, 'slot_index')}


def parse_pouches(text):
    """`/isaac/amr_1/pouches`. 빈 목록도 정상이다 — 팔이 "검출 0건" 으로 빨리 닫는다."""
    data = _object(text, POUCHES_FIELDS)
    detections = data['detections']
    if not isinstance(detections, list):
        raise IsaacJsonError(f'detections 가 배열이 아니다: {detections!r}')
    return {'stamp': _stamp(data), 'epoch': _uint32(data, 'epoch'),
            'frame_id': _string(data, 'frame_id', non_empty=True),
            'detections': [_detection(item, index) for index, item in enumerate(detections)]}


def parse_tag_read(text):
    """`/isaac/amr_1/tag_reads`. kind·status 는 문자열이고 모르는 값은 형식 오류다."""
    data = _object(text, TAG_READ_FIELDS)
    return {'stamp': _stamp(data), 'epoch': _uint32(data, 'epoch'),
            'frame_id': _string(data, 'frame_id', non_empty=True),
            'zone_id': _string(data, 'zone_id'), 'kind': _choice(data, 'kind', TAG_KINDS),
            'tag_id': _string(data, 'tag_id', non_empty=True),
            'status': _choice(data, 'status', TAG_STATUSES)}


def parse_cabinet(text):
    """`/isaac/evaluator/cabinet`. `cabinet_id` 가 비면 어느 보관함인지 모른다 — 형식 오류다."""
    data = _object(text, CABINET_FIELDS)
    return {'stamp': _stamp(data), 'epoch': _uint32(data, 'epoch'),
            'cabinet_id': _string(data, 'cabinet_id', non_empty=True),
            'order_id': _string(data, 'order_id'), 'present': _bool(data, 'present')}


def cabinet(sec, nanosec, epoch, cabinet_id, order_id, present):
    return dumps({'v': VERSION, 'stamp': _stamp_fields(sec, nanosec), 'epoch': int(epoch),
                  'cabinet_id': cabinet_id, 'order_id': order_id, 'present': bool(present)})


def parse_gripper_state(text):
    """`/isaac/amr_1/gripper/state`. seq·last_applied_command_seq 는 uint32, enum 은 msg 의 범위 안."""
    data = _object(text, GRIPPER_STATE_FIELDS)
    return {'stamp': _stamp(data), 'epoch': _uint32(data, 'epoch'), 'seq': _uint32(data, 'seq'),
            'last_applied_command_seq': _uint32(data, 'last_applied_command_seq'), **_enums(data, GRIPPER_ENUMS)}


def parse_gripper_command(text):
    data = _object(text, GRIPPER_COMMAND_FIELDS)
    return {'stamp': _stamp(data), 'epoch': _uint32(data, 'epoch'), 'command_seq': _uint32(data, 'command_seq'),
            'close': _bool(data, 'close')}


def gripper_command(sec, nanosec, epoch, command_seq, close):
    return dumps({'v': VERSION, 'stamp': _stamp_fields(sec, nanosec), 'epoch': int(epoch),
                  'command_seq': int(command_seq), 'close': bool(close)})


def parse_event(text):
    data = _object(text, EVENT_FIELDS)
    name = _string(data, 'name')
    if name not in EVENT_NAMES:
        raise IsaacJsonError(f'name {name!r} 은 Isaac 이 내는 이벤트({EVENT_NAMES})가 아니다')
    robot_id = _string(data, 'robot_id')
    if robot_id != EVENT_ROBOT_ID:
        raise IsaacJsonError(f'robot_id {robot_id!r} 는 {EVENT_ROBOT_ID} 가 아니다')
    return {'stamp': _stamp(data), 'name': name, 'request_id': _string(data, 'request_id'),
            'order_id': _string(data, 'order_id'), 'robot_id': robot_id, 'epoch': _uint32(data, 'epoch'),
            'detail': _string(data, 'detail')}


# 가짜 Isaac(테스트)이 쓰는 만들기 ---------------------------------------------------

def dispense_response(request_id, order_id, accepted, message=''):
    return dumps({'v': VERSION, 'request_id': request_id, 'order_id': order_id,
                  'accepted': bool(accepted), 'message': message})


def reset_response(epoch, ok, message=''):
    return dumps({'v': VERSION, 'epoch': int(epoch), 'ok': bool(ok), 'message': message})


def _stamp_fields(sec, nanosec):
    return {'sec': int(sec), 'nanosec': int(nanosec)}


def belt(sec, nanosec, occupied, at_end, order_id, epoch):
    return dumps({'v': VERSION, 'stamp': _stamp_fields(sec, nanosec), 'occupied': bool(occupied),
                  'at_end': bool(at_end), 'order_id': order_id, 'epoch': int(epoch)})


def belt_observation(sec, nanosec, epoch, seq, request_id, order_id, mode, occupancy, pouch_zone, pouch_motion,
                     belt_motion=0, belt_command_applied=0):
    return dumps({'v': VERSION, 'stamp': _stamp_fields(sec, nanosec), 'epoch': int(epoch), 'seq': int(seq),
                  'request_id': request_id, 'order_id': order_id, 'mode': int(mode), 'occupancy': int(occupancy),
                  'pouch_zone': int(pouch_zone), 'pouch_motion': int(pouch_motion), 'belt_motion': int(belt_motion),
                  'belt_command_applied': int(belt_command_applied)})


def detection(order_id, confidence, position, orientation=(0.0, 0.0, 0.0, 1.0), slot_index=-1):
    """검출 하나. 시험과 시뮬 쪽 예시를 같은 코드로 만든다."""
    return {'order_id': order_id, 'confidence': float(confidence), 'slot_index': int(slot_index),
            'pose': {'position': dict(zip(('x', 'y', 'z'), (float(v) for v in position), strict=True)),
                     'orientation': dict(zip(('x', 'y', 'z', 'w'), (float(v) for v in orientation), strict=True))}}


def pouches(sec, nanosec, epoch, frame_id, detections=()):
    return dumps({'v': VERSION, 'stamp': _stamp_fields(sec, nanosec), 'epoch': int(epoch),
                  'frame_id': frame_id, 'detections': list(detections)})


def tag_read(sec, nanosec, epoch, frame_id, zone_id, kind, tag_id, status):
    return dumps({'v': VERSION, 'stamp': _stamp_fields(sec, nanosec), 'epoch': int(epoch), 'frame_id': frame_id,
                  'zone_id': zone_id, 'kind': kind, 'tag_id': tag_id, 'status': status})


def gripper_state(sec, nanosec, epoch, seq, last_applied_command_seq, state, mode):
    return dumps({'v': VERSION, 'stamp': _stamp_fields(sec, nanosec), 'epoch': int(epoch), 'seq': int(seq),
                  'last_applied_command_seq': int(last_applied_command_seq), 'state': int(state), 'mode': int(mode)})


def event(sec, nanosec, name, request_id, order_id, epoch, detail='', robot_id=EVENT_ROBOT_ID):
    return dumps({'v': VERSION, 'stamp': _stamp_fields(sec, nanosec), 'name': name, 'request_id': request_id,
                  'order_id': order_id, 'robot_id': robot_id, 'epoch': int(epoch), 'detail': detail})
