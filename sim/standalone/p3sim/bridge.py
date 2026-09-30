"""JSON messages between Isaac (internal rclpy) and the system-ROS adapter, on std_msgs/String.

Why: Isaac Sim 5.1 runs Python 3.11 with internal ROS libraries for common interfaces only; our
rokey_p3_interfaces (Dispense, Reset, BeltState, Event) build against system Jazzy (Python 3.12). The 5.1 ROS
install page offers a Python 3.11 custom-package build instead; we chose not to (install work on the masters).
On master02 (9/17) Isaac's internal rclpy published std_msgs and sensor_msgs fine. std_srvs was not checked, so
request/response are topic pairs, not services. An adapter node on system ROS maps these to the contract types
and names (/pharmacy/dispense, /sim/reset, /pharmacy/belt, /events). No Isaac imports here.
"""

import json
import math

SCHEMA_VERSION = 1

DISPENSE_REQUEST = "/isaac/pharmacy/dispense_request"
DISPENSE_RESPONSE = "/isaac/pharmacy/dispense_response"
RESET_REQUEST = "/isaac/sim/reset_request"
RESET_RESPONSE = "/isaac/sim/reset_response"
BELT = "/isaac/pharmacy/belt"
EVENTS = "/isaac/events"
PICK_NOTICE = "/isaac/pharmacy/pick_notice"  # adapter -> Isaac: the arm reported POUCH_PICKED (added 9/17, v stays 1)
PICK_SOURCES = ("POUCH_PICKED",)
# Isaac -> adapter: contract 11.6 BeltObservation, opt-in (--belt-observation). Field names and enum integers are
# those of BeltObservation.msg; header.stamp is "stamp" as on the other topics.
BELT_OBSERVATION = "/isaac/pharmacy/belt_observation"
# contract 11.6 GripperState (Isaac -> adapter) and GripperCommand (adapter -> Isaac), opt-in (--gripper-command-seq).
GRIPPER_STATE = "/isaac/amr_1/gripper/state"
GRIPPER_COMMAND_SEQ = "/isaac/amr_1/gripper/command_seq"
GRIPPER_ENUMS = {"state": 2, "mode": 2}
# K4·K5 센서(비전 9/21): 스테이지가 **참값**을 JSON 으로 내고 isaac_adapter 가 PouchDetection·TagRead 로 옮긴다.
# 계약 토픽(hand_camera/*)의 작성자는 그대로 perception 하나다. Isaac 이 내는 JSON 은 예외 없이 /isaac/* 다.
POUCHES = "/isaac/amr_1/pouches"
#: K5b: 보관함 참값. 계약 145–150·341줄의 `/evaluator/cabinet`(`CabinetObservation`)로 어댑터가 옮긴다.
#: **평가 전용**이다 — 운영 노드(orchestrator·arm·fleet)는 구독하지 않고 event_logger 만 본다.
CABINET = "/isaac/evaluator/cabinet"
TAG_READS = "/isaac/amr_1/tag_reads"
#: 관제 웹 전체 보기(재범 v1.0): 여벌 AMR·가짜 AMR(더미) 자리. 주문·Nav2 가 없는 몸체라 다른 원천이 없다.
#: 백엔드가 std_msgs/String 으로 직접 구독한다(어댑터 없음). frame_id 는 "map"(병원 지도 = 월드 좌표).
FLEET_POSES = "/isaac/fleet/poses"
FLEET_POSES_HZ = 5.0
FLEET_POSE_KINDS = ("spare_amr", "dummy")
#: 관제 웹 Play/Stop(재범 v1.0, 작전 9/27 ③): Isaac 타임라인이 도는가. **JSON 이 아니라 std_msgs/Bool** 이라
#: QOS·SCHEMAS 표에 없다. RELIABLE·volatile·depth 1 로 1 Hz 와 바뀔 때마다 낸다. 끝날 때 false 한 번.
#: 3 s 넘게 안 오면 Isaac 이 없는 것이다(latched 로 두면 죽은 프로세스의 true 가 남는다).
SIM_RUNNING = "/p3/sim_running"
SIM_RUNNING_HZ = 1.0
#: 정수 대신 문자열을 쓴다 — .msg 상수가 바뀌면 정수는 조용히 다른 뜻이 된다(비전 9/21).
TAG_KINDS = ("patient", "station", "pouch")
TAG_STATUSES = ("ok", "unreadable")
#: 계약 319줄: slot_index 는 v1 에서 −1 고정. 칸 번호를 안 쓰면 0/1 기준(미결 결정 28)에 안 걸린다.
SLOT_INDEX_V1 = -1
OBSERVATION_ENUMS = {"mode": 3, "occupancy": 2, "pouch_zone": 3, "pouch_motion": 2, "belt_motion": 2,
                     "belt_command_applied": 2}  # field -> largest value

# QoS per topic: (reliability, durability, depth). Belt mirrors contract H, events mirror the latched /events.
QOS = {
    DISPENSE_REQUEST: ("reliable", "volatile", 10),
    DISPENSE_RESPONSE: ("reliable", "volatile", 10),
    RESET_REQUEST: ("reliable", "volatile", 10),
    RESET_RESPONSE: ("reliable", "volatile", 10),
    BELT: ("reliable", "volatile", 1),
    EVENTS: ("reliable", "transient_local", 500),
    PICK_NOTICE: ("reliable", "volatile", 10),
    BELT_OBSERVATION: ("reliable", "volatile", 1),
    GRIPPER_STATE: ("reliable", "volatile", 1),
    GRIPPER_COMMAND_SEQ: ("reliable", "volatile", 10),
    # **다른 /isaac/* 발행과 같은 RELIABLE 이다.**
    # 근거는 **코드다**: 어댑터가 이 둘을 구독할 때 쓰는 프로필이
    # `rokey_p3_orchestrator/ros_qos.py` 의 `heartbeat_qos()` 이고 그 함수가 RELIABLE·volatile·1 을 낸다
    # (계약의 H). 고칠 일이 생기면 **사람 말이 아니라 그 함수를 열어 보라.**
    # 한 번 best_effort 로 바꿨다가 실습27 이 기동 전 확인에서 멈췄다(9/21) — **호환되지 않아 한 건도 못 갔다.**
    # 증상은 WARN 한 줄과 "검출이 안 온다" 뿐이다. 버려지는 것도 아니라 `dropped` 에도 안 남는다.
    # 호환 규칙 한 줄: **구독이 RELIABLE 이면 발행도 RELIABLE 이어야 한다**(반대는 된다).
    # depth 1·volatile 은 그대로(최신 한 건만 쓰인다).
    POUCHES: ("reliable", "volatile", 1),
    # 늦게 붙은 구독자도 지난 값을 받아야 한다(stub 이 쓰던 latched 와 같은 자리).
    CABINET: ("reliable", "transient_local", 50),
    TAG_READS: ("reliable", "volatile", 1),
    FLEET_POSES: ("reliable", "volatile", 1),
}

# Field name -> accepted Python types. "v" is the schema version on every message.
SCHEMAS = {
    DISPENSE_REQUEST: {"v": int, "request_id": str, "order_id": str},
    DISPENSE_RESPONSE: {"v": int, "request_id": str, "order_id": str, "accepted": bool, "message": str},
    RESET_REQUEST: {"v": int, "epoch": int},
    RESET_RESPONSE: {"v": int, "epoch": int, "ok": bool, "message": str},
    BELT: {"v": int, "stamp": dict, "occupied": bool, "at_end": bool, "order_id": str, "epoch": int},
    EVENTS: {"v": int, "stamp": dict, "name": str, "request_id": str, "order_id": str, "robot_id": str,
             "epoch": int, "detail": str},
    PICK_NOTICE: {"v": int, "stamp": dict, "epoch": int, "order_id": str, "source": str},
    BELT_OBSERVATION: {"v": int, "stamp": dict, "epoch": int, "seq": int, "request_id": str, "order_id": str,
                       "mode": int, "occupancy": int, "pouch_zone": int, "pouch_motion": int, "belt_motion": int,
                       "belt_command_applied": int},
    GRIPPER_STATE: {"v": int, "stamp": dict, "epoch": int, "seq": int, "last_applied_command_seq": int, "state": int,
                    "mode": int},
    GRIPPER_COMMAND_SEQ: {"v": int, "stamp": dict, "epoch": int, "command_seq": int, "close": bool},
    POUCHES: {"v": int, "stamp": dict, "epoch": int, "frame_id": str, "detections": list},
    CABINET: {"v": int, "stamp": dict, "epoch": int, "cabinet_id": str, "order_id": str, "present": bool},
    TAG_READS: {"v": int, "stamp": dict, "epoch": int, "frame_id": str, "zone_id": str, "kind": str,
                "tag_id": str, "status": str},
    FLEET_POSES: {"v": int, "stamp": dict, "frame_id": str, "poses": list},
}
#: 검출 원소의 필드. 원소에는 v·stamp·frame_id 가 없다(비전 9/21).
DETECTION_SCHEMA = {"order_id": str, "confidence": float, "pose": dict, "slot_index": int}

#: 자리 원소의 필드. yaw 는 rad(지도 +x 에서 반시계).
FLEET_POSE_SCHEMA = {"id": str, "kind": str, "x": float, "y": float, "yaw": float}

UINT32_MAX = 2**32 - 1


def stamp(sim_time):
    """Sim time seconds -> builtin_interfaces/Time fields."""
    sec = int(math.floor(sim_time))
    nanosec = int(round((sim_time - sec) * 1e9))
    if nanosec >= 1_000_000_000:
        sec, nanosec = sec + 1, nanosec - 1_000_000_000
    return {"sec": sec, "nanosec": nanosec}


def fleet_pose_items(spares=(), dummies=()):
    """[(id, x, y, yaw)] 둘 → FLEET_POSES 의 `poses`. id 순서는 받은 그대로(여벌 먼저)."""
    return ([{"id": who, "kind": "spare_amr", "x": float(x), "y": float(y), "yaw": float(yaw)}
             for who, x, y, yaw in spares]
            + [{"id": who, "kind": "dummy", "x": float(x), "y": float(y), "yaw": float(yaw)}
               for who, x, y, yaw in dummies])


def _fleet_pose_problems(poses):
    problems = []
    for index, item in enumerate(poses):
        if not isinstance(item, dict):
            problems.append(f"poses[{index}] is not an object")
            continue
        if set(item) != set(FLEET_POSE_SCHEMA):
            problems.append(f"poses[{index}] fields must be {sorted(FLEET_POSE_SCHEMA)}")
            continue
        if not isinstance(item["id"], str) or not item["id"]:
            problems.append(f"poses[{index}].id is empty")
        if item["kind"] not in FLEET_POSE_KINDS:
            problems.append(f"poses[{index}].kind must be one of {list(FLEET_POSE_KINDS)}")
        for field in ("x", "y", "yaw"):
            value = item[field]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                problems.append(f"poses[{index}].{field} must be a finite number")
    return problems


def _detection_problems(detections):
    """검출 배열의 문제 목록. 빈 배열은 정상이다 — "검출 0건" 을 내는 것이 안 내는 것보다 낫다(비전 9/21)."""
    problems = []
    for index, item in enumerate(detections):
        if not isinstance(item, dict):
            problems.append(f"detections[{index}] is not an object")
            continue
        for field, kind in DETECTION_SCHEMA.items():
            if field not in item:
                problems.append(f"detections[{index}] missing {field}")
            elif kind is int and (isinstance(item[field], bool) or not isinstance(item[field], int)):
                problems.append(f"detections[{index}].{field} must be an integer")
            elif kind is float and not isinstance(item[field], (int, float)):
                problems.append(f"detections[{index}].{field} must be a number")
            elif kind not in (int, float) and not isinstance(item[field], kind):
                problems.append(f"detections[{index}].{field} must be {kind.__name__}")
        extra = sorted(set(item) - set(DETECTION_SCHEMA))
        if extra:
            problems.append(f"detections[{index}] unexpected fields {extra}")
        if "slot_index" in item and item["slot_index"] != SLOT_INDEX_V1:
            problems.append(f"detections[{index}].slot_index must be {SLOT_INDEX_V1} (계약 319줄)")
        pose = item.get("pose")
        if isinstance(pose, dict):
            problems += _pose_problems(index, pose)
    return problems


def _pose_problems(index, pose):
    """자세의 문제 목록. **0 자세는 거부한다** — 팔이 "거리를 못 정했다" 로 닫는 값이다(비전 9/21)."""
    problems = []
    position, orientation = pose.get("position"), pose.get("orientation")
    if set(pose) != {"position", "orientation"} or not isinstance(position, dict) \
            or not isinstance(orientation, dict):
        return [f"detections[{index}].pose must be {{position, orientation}}"]
    if set(position) != {"x", "y", "z"}:
        problems.append(f"detections[{index}].pose.position must be {{x, y, z}}")
    elif sum(abs(float(position[k])) for k in "xyz") < 1e-6:
        problems.append(f"detections[{index}].pose.position is zero (팔이 거부한다)")
    if set(orientation) != {"x", "y", "z", "w"}:
        problems.append(f"detections[{index}].pose.orientation must be {{x, y, z, w}}")
    return problems


def validate(topic, message):
    """Return a list of problems for a decoded message on `topic`; empty means valid."""
    schema = SCHEMAS.get(topic)
    if schema is None:
        return [f"unknown topic {topic}"]
    if not isinstance(message, dict):
        return ["message is not a JSON object"]
    problems = []
    for field, kind in schema.items():
        if field not in message:
            problems.append(f"missing {field}")
            continue
        value = message[field]
        if kind is int and (isinstance(value, bool) or not isinstance(value, int)):
            problems.append(f"{field} must be an integer")
        elif kind is not int and not isinstance(value, kind):
            problems.append(f"{field} must be {kind.__name__}")
    extra = sorted(set(message) - set(schema))
    if extra:
        problems.append(f"unexpected fields {extra}")
    if not problems:
        if message["v"] != SCHEMA_VERSION:
            problems.append(f"schema version {message['v']} is not {SCHEMA_VERSION}")
        if "epoch" in message and not 0 <= message["epoch"] <= UINT32_MAX:
            problems.append("epoch out of uint32 range")
        if "stamp" in message:
            st = message["stamp"]
            if set(st) != {"sec", "nanosec"} or not all(isinstance(st[k], int) and not isinstance(st[k], bool)
                                                          for k in ("sec", "nanosec")):
                problems.append("stamp must be {sec: int, nanosec: int}")
            elif not 0 <= st["nanosec"] < 1_000_000_000:
                problems.append("stamp.nanosec out of range")
        if topic == BELT_OBSERVATION:
            if not 0 <= message["seq"] <= UINT32_MAX:
                problems.append("seq out of uint32 range")
            for field, largest in OBSERVATION_ENUMS.items():
                if not 0 <= message[field] <= largest:
                    problems.append(f"{field} must be 0..{largest}")
        for field in ("seq", "last_applied_command_seq", "command_seq"):
            if topic in (GRIPPER_STATE, GRIPPER_COMMAND_SEQ) and field in message \
                    and not 0 <= message[field] <= UINT32_MAX:
                problems.append(f"{field} out of uint32 range")
        if topic == GRIPPER_STATE:
            for field, largest in GRIPPER_ENUMS.items():
                if not 0 <= message[field] <= largest:
                    problems.append(f"{field} must be 0..{largest}")
        if topic == POUCHES:
            problems += _detection_problems(message["detections"])
            if not message["frame_id"]:
                problems.append("frame_id is empty")
        if topic == FLEET_POSES:
            problems += _fleet_pose_problems(message["poses"])
            if not message["frame_id"]:
                problems.append("frame_id is empty")
        if topic == CABINET and not message["cabinet_id"]:
            problems.append("cabinet_id is empty")
        if topic == TAG_READS:
            if message["kind"] not in TAG_KINDS:
                problems.append(f"kind must be one of {list(TAG_KINDS)}")
            if message["status"] not in TAG_STATUSES:
                problems.append(f"status must be one of {list(TAG_STATUSES)}")
            if not message["zone_id"]:
                problems.append("zone_id is empty")
            # 비우면 orchestrator 가 스텁 태그로 비교해 인증이 거짓 통과한다(비전 #417 4절).
            if message["status"] == "ok" and not message["tag_id"]:
                problems.append("tag_id is empty on an ok read")
        if topic == DISPENSE_REQUEST and not message["request_id"]:
            problems.append("request_id is empty")
        if topic == PICK_NOTICE:
            if message["source"] not in PICK_SOURCES:
                problems.append(f"source must be one of {list(PICK_SOURCES)}")
            if not message["order_id"]:
                problems.append("order_id is empty")
    return problems


def encode(topic, **fields):
    """Build, validate and serialize a message. Raises ValueError on a schema problem."""
    message = {"v": SCHEMA_VERSION, **fields}
    problems = validate(topic, message)
    if problems:
        raise ValueError(f"{topic}: {problems}")
    return json.dumps(message, sort_keys=True, separators=(",", ":"))


def decode(topic, text):
    """Parse and validate. Returns (message, problems)."""
    try:
        message = json.loads(text)
    except (TypeError, ValueError) as error:
        return None, [f"not JSON: {error}"]
    problems = validate(topic, message)
    return (message if not problems else None), problems


def pick_notice_applies(message, current_epoch, belt_order_id, belt_at_end):
    """Whether a valid pick_notice should park the pouch at the belt end. Returns (applies, reason)."""
    if message["epoch"] != current_epoch:
        return False, f"epoch {message['epoch']} is not current {current_epoch}"
    if not belt_at_end:
        return False, "no pouch stopped at the belt end"
    if message["order_id"] != belt_order_id:
        return False, f"order_id {message['order_id']} is not the pouch at the end ({belt_order_id or '-'})"
    return True, ""
