"""UR5 팔 노드. `PickPouch` 서버, 관절·그리퍼 명령, `arm/at_home`. manipulation 담당.

계약 [배송 한 바퀴 v1](../../../docs/architecture/delivery-contract-v1.md) 2.1·2.3·2.4·3·4·5·6절.

- 내는 것: `/<robot>/arm/joint_command` (UR5 6개만, position), `/<robot>/gripper/command`,
  `/<robot>/arm/at_home` (5 Hz), `/events`
- 받는 것: `/<robot>/joint_states`, `/<robot>/gripper/holding`, `/<robot>/base/stopped`,
  `/<robot>/hand_camera/pouches`, `/pharmacy/belt`, `/events`, TF
- 서버: `/<robot>/pick_pouch` (`PickPouch`, 60 s sim)
- 선택(opt-in, 기본 `bool`): `gripper_observation: state` 이면 흡착 판정을 `GripperState`(seq 규칙)로 하고, 명령을
  기존 `gripper/command`(Bool)와 `gripper/command_seq`(`GripperCommand`)에 같은 값으로 낸다(계약 11.6).
- 선택(opt-in, 기본 끔): `placement_check_enabled` 이면 해제 확인 뒤 칸을 다시 보고 안착을 확인한 뒤에만
  `POUCH_LOADED/PLACED` 를 낸다(계약 11.4 제안). `gripper_observation: state` 가 필요하다.
- 선택(opt-in, 기본 끔): `arm_clearance_enabled` 이면 `/<robot>/arm/clear_of_belt` (`ArmClearance`, 계약 11.6)를
  내고 `/<robot>/gripper/state` (`GripperState`)를 받는다. 끄면 토픽도 구독도 만들지 않는다.
- stale 판정은 수신 노드의 steady clock(wall), 이벤트·액션 시한은 sim time (계약 4절).
- 활성 goal 이 없으면 관절 명령을 내지 않는다 (계약 5절 "정지 보장").
- `RESET_BEGIN`(새 epoch)부터 같은 epoch 의 `RESET_DONE` 까지 관절·그리퍼 명령을 내지 않는다(계약 6절 0).
  실행 중 goal 은 멈추고, 홈 복귀는 접고, 새 goal 은 거부한다. 초기 자세는 isaac 리셋이 되돌린다.
  명시적 cancel 이면 원래부터 홈 복귀를 시작하지 않는다(M0609 는 시작한다).

관절 이름·관절 한계·홈 자세·속도·접근 높이는 파라미터다. IK 의 DH 는 현재
`ur5_kinematics.UR5_DH` 기본값을 쓴다(노드 파라미터 없음). 실제 USD 자산과
흡착면 오프셋은 **마스터에서 확인**한다. DH 가 다르면 노드에서 솔버로 전달하는
코드 변경이 필요하다.
"""

import contextlib
import math
import threading
import time

import numpy as np
import rclpy
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.duration import Duration
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from rclpy.time import Time as RclTime
from rokey_p3_interfaces.action import PickPouch, ScanTag
from rokey_p3_interfaces.msg import (ArmClearance, BeltState, Event, GripperCommand, GripperState,
                                     PouchDetectionArray, TagRead)
from sensor_msgs.msg import JointState
from std_msgs.msg import Bool
from tf2_ros import Buffer, TransformException, TransformListener

from rokey_p3_manipulation import arm_clearance_state as clear_state
from rokey_p3_manipulation import belt_lane_clearance as lane
from rokey_p3_manipulation import pick_permission as perm
from rokey_p3_manipulation import placement_check as placement
from rokey_p3_manipulation import ur5_kinematics as kin
from rokey_p3_manipulation.reset_fence import ClockWatch, ResetFence

# 계약 4절: 상태 토픽(H) 1.0 s, joint_command 0.5 s. 전부 wall 로 잰다.
STALE_STATUS_S = 1.0
STALE_JOINTS_S = 1.0

# QoS (계약 2절 약어)
QOS_RELIABLE = QoSProfile(reliability=ReliabilityPolicy.RELIABLE,
                          durability=DurabilityPolicy.VOLATILE,
                          history=HistoryPolicy.KEEP_LAST, depth=10)
QOS_HEARTBEAT = QoSProfile(reliability=ReliabilityPolicy.RELIABLE,
                           durability=DurabilityPolicy.VOLATILE,
                           history=HistoryPolicy.KEEP_LAST, depth=1)
def _xyz(pose):
    """4x4 의 위치를 로그용 (x, y, z) 문자열로."""
    return '({:.3f}, {:.3f}, {:.3f})'.format(*(float(v) for v in pose[:3, 3]))


def default_arm_base_frame(robot_id):
    """`arm_base_frame` 이 비었을 때 쓰는 이름(결정 47).

    `{robot_id}/base_link` 가 아니다 — 계약 420-434 절에서 그 이름은 **이동 베이스**의 프레임이고
    (부모 `odom`, 작성자 `base_driver`), UR5 밑동은 그 아래의 다른 링크다. 같은 이름을 쓰면
    한 child 에 부모가 둘이 된다.
    """
    return f'{robot_id}/ur_arm_base_link'


#: 봉투 검출·태그 판독의 출처. `camera` 는 계약 토픽(`hand_camera/*`, perception 이 쓴다),
#: `sim` 은 스테이지 시뮬 센서(`{ns}/sim/*`, isaac_adapter 가 옮긴다). 기본은 `camera` 다.
SOURCE_CAMERA = 'camera'
SOURCE_SIM = 'sim'
SENSOR_SOURCES = (SOURCE_CAMERA, SOURCE_SIM)

#: `arm_base_frame` 의 축이 팔 기구학(DH 표)의 기준축에 대해 어떻게 놓여 있나. 값은 그 사이의 z 축 회전이다.
#:
#: - `base`: 같다. **기본값이고 지금까지의 동작이다.**
#: - `base_link`: UR URDF 의 루트 링크. `ur_description` 에서 `base_link` 는 DH 표의 기준인
#:   `base` 에서 z 축으로 180° 돌아 있다. 표준 UR5 DH 표(`ur5_kinematics.UR5_DH`)는 `base` 기준이다.
#:
#: **왜 파라미터인가**: 프레임 *이름*은 축 방향을 말해 주지 않는다. Isaac 자산은 링크를 `base_link`
#: 로 내고(결정 47 로 그 TF 이름이 `amr_1/ur_arm_base_link` 가 되었다) 그 축은 UR 관례를 따르는데,
#: 팔은 자기 DH 가 `base` 기준이라는 것만 안다. 둘의 관계는 **어디에도 적혀 있지 않았다**.
#: 실습27b 에서 팔이 봉투에서 1.25 m 떨어진 곳(x·y 부호가 뒤집힌 자리)으로 간 원인이 이것이다.
#: 맞을 때까지 값을 흔드는 knob 이 **아니다** — 자산이 어느 관례를 쓰는지 고르는 두 갈래다.
BASE_FRAME_CONVENTIONS = {'base': 0.0, 'base_link': math.pi}


def base_to_kinematic(convention):
    """`arm_base_frame` 에서 본 자세 → 기구학 기준에서 본 자세로 옮기는 4x4."""
    matrix = np.eye(4)
    matrix[:3, :3] = kin.rotation_z(BASE_FRAME_CONVENTIONS[convention])
    return matrix


#: 관례 자가 확인의 판정선. 맞는 관례면 FK 와 TF 가 손목↔DH끝 고정 오프셋(≤0.1 m 급)만큼만
#: 남고, 틀린 관례면 팔 길이의 두 배 급으로 벌어진다. 그 사이가 이만큼 갈려야 판정한다.
CONVENTION_NEAR_M = 0.15
CONVENTION_FAR_M = 0.50


def matching_convention(fk_position, tf_position):
    """FK 와 TF 를 대조해 어느 관례가 맞는지 고른다. 못 가르면 `(None, 설명)`.

    **위치만 본다.** 손목 링크 프레임과 DH 끝점 사이의 고정 변환은 자산마다 다르고
    미리 알 수 없는데(AMR 합본에서는 항등이었지만 그것도 재서 안 값이다), 그 크기가
    관례를 틀렸을 때의 어긋남보다 한참 작아서 가르는 데는 지장이 없다.
    """
    distances = {}
    for name in BASE_FRAME_CONVENTIONS:
        rotated = base_to_kinematic(name)[:3, :3] @ np.asarray(fk_position, dtype=float)
        distances[name] = float(np.linalg.norm(rotated - np.asarray(tf_position, dtype=float)))
    text = ' '.join(f'{name}={distances[name]:.3f}m' for name in sorted(distances))
    best = min(distances, key=distances.get)
    worst = max(distances, key=distances.get)
    if distances[best] > CONVENTION_NEAR_M or distances[worst] < CONVENTION_FAR_M:
        return None, text
    return best, text


def wrist_link_frame(robot_id, joint_names):
    """마지막 관절 이름에서 손목 링크 TF 이름을 만든다(`*_joint` → `*_link`).

    자산마다 접두가 다르다(받침대 `wrist_3_joint`, AMR 합본 `ur_arm_wrist_3_joint`).
    `joint_names` 는 이미 자산에 맞춰 넣는 값이라 여기서 파생하면 따로 맞출 값이 안 는다.
    """
    name = joint_names[-1]
    return f'{robot_id}/{name[:-len("_joint")] if name.endswith("_joint") else name}_link'


class MoveResult:
    """이동의 결과. 거짓이면 실패고, `outcome`·`detail` 이 **왜인지**를 말한다.

    거짓/참으로만 쓰던 기존 호출부는 그대로 둬도 된다(`__bool__`). `outcome` 이 비어 있으면
    "호출부가 알아서 정하라"는 뜻이고(지금까지의 IK 실패·취소가 그렇다), 채워져 있으면
    그 값으로 닫아야 한다.
    """

    __slots__ = ('ok', 'outcome', 'detail')

    def __init__(self, ok, outcome=None, detail=''):
        self.ok, self.outcome, self.detail = bool(ok), outcome, detail

    def __bool__(self):
        return self.ok


def arrival_problem(joint_names, target, actual, tolerance):
    """도달 못 한 관절 중 제일 많이 남은 것을 한 줄로. 다 들어왔으면 None.

    한 줄로 갈리는 것이 목적이다 — 실습29b 에서 팔이 벽에 막혀 절반만 갔는데 노드가
    "이동 성공" 으로 넘어가 흡착을 켰고, 결과가 `grasp_failed` 로 닫혔다. **움직임 실패가
    흡착 실패로 보고되어** 원인 규명이 엉뚱한 곳을 봤다.
    """
    gaps = [(abs(float(a) - float(t)), name, float(t), float(a))
            for name, t, a in zip(joint_names, target, actual, strict=False)]
    gap, name, want, got = max(gaps)
    if gap <= tolerance:
        return None
    return f'이동 미도달: {name} 목표 {want:+.4f} 실제 {got:+.4f} (남음 {gap:.4f} rad)'

QOS_SENSOR = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT,
                        durability=DurabilityPolicy.VOLATILE,
                        history=HistoryPolicy.KEEP_LAST, depth=5)
QOS_DETECTIONS = QoSProfile(reliability=ReliabilityPolicy.RELIABLE,
                            durability=DurabilityPolicy.VOLATILE,
                            history=HistoryPolicy.KEEP_LAST, depth=5)
QOS_LATCHED_EVENTS = QoSProfile(reliability=ReliabilityPolicy.RELIABLE,
                                durability=DurabilityPolicy.TRANSIENT_LOCAL,
                                history=HistoryPolicy.KEEP_LAST, depth=500)

# 계약 11.6 `arm_clear_of_belt` 파라미터와 기본값. 기본은 끔이고, 기하는 전부 "미설정" 표지다
# (빈 목록 대신 길이가 틀린 [0.0], 음수 길이). 값을 지어내지 않는다. 측정값만 덮어쓴다.
CLEARANCE_PARAMETERS = (
    ('arm_clearance_enabled', False),
    ('arm_clearance_rate_hz', 10.0),
    ('arm_clearance_region', ''),
    ('arm_clearance_lane_frame', ''),          # 통로 프레임(x along, y lateral, z up)
    ('arm_clearance_lane_lower', [0.0]),       # [along, lateral, up] m. 3개가 아니면 미설정
    ('arm_clearance_lane_upper', [0.0]),
    ('arm_clearance_link_radii', [0.0]),       # DH 선분 6개. 6개가 아니면 미설정
    ('arm_clearance_tool_length_m', -1.0),     # 음수 = 미설정
    ('arm_clearance_tool_radius_m', -1.0),
    ('arm_clearance_payload_size', [0.0]),     # TCP 축 [x, y, z] m
    ('arm_clearance_payload_center', [0.0]),
)

# 계약 11.4(제안) 칸 안착 확인. 기본 끔 = 해제 뒤 시간 대기(현행). 치수·거리·시한은 전부 "미설정" 표지다.
# **관측 자세 이동은 충돌 검증이 없다. L3 에서 촬영 자세를 확인하기 전에는 켜지 않는다.**
PLACEMENT_PARAMETERS = (
    ('placement_check_enabled', False),
    ('placement_view_standoff_m', -1.0),      # 손 카메라를 놓을 곳 프레임 +z 로 이만큼 띄워 내려다본다. 음수 = 미설정
    ('placement_slot_box_m', [0.0]),          # 상판 칸 상자 [sx, sy, sz] m(deck_slot_N 프레임). 3개가 아니면 미설정
    ('placement_cabinet_box_m', [0.0]),       # 보관함 상자 [sx, sy, sz] m(<zone>/cabinet 프레임)
    ('placement_timeout_s', -1.0),            # 관측 자세에서 검출을 기다리는 시한(sim). 음수 = 미설정
)

CANCELLED = None  # outcome 자리의 None 은 "취소됨"이다. 계약의 outcome 목록에는 없다.
SHUTDOWN = 'shutdown'  # 노드 종료(close)로 멈췄다. 계약 outcome 이 아니다. 결과에는 timeout 으로 싣고 abort 한다.


class Freshness:
    """마지막 수신 값과 그 시각(wall). 계약 4절의 stale 판정 하나를 담는다."""

    def __init__(self, stale_after_s):
        self._stale_after_s = stale_after_s
        self._value = None
        self._received_at = None

    def update(self, value):
        self._value = value
        self._received_at = time.monotonic()

    def clear(self):
        self._value = None
        self._received_at = None

    def age(self):
        """마지막 수신 뒤 경과(wall, s). 받은 적이 없으면 None."""
        if self._received_at is None:
            return None
        return time.monotonic() - self._received_at

    def get(self):
        """살아 있으면 값, 한 번도 못 받았거나 오래됐으면 None(unknown)."""
        if self._received_at is None:
            return None
        if time.monotonic() - self._received_at > self._stale_after_s:
            return None
        return self._value


class ArmNode(Node):
    """arm 노드."""

    def __init__(self):
        super().__init__('arm')

        self.declare_parameter('robot_id', 'amr_1')
        self.declare_parameter('joint_names', list(kin.UR5_JOINT_NAMES))
        # 홈 자세: USD 영점을 기본값으로 둔다. 실제 홈 자세는 도킹 자세에서
        # 벨트 끝에 닿는 자세로 마스터에서 측정해 이 파라미터에 넣는다.
        self.declare_parameter('home_joint_positions', [0.0] * 6)
        # 홈↔작업 사이에 끼우는 경유 자세(관절 여섯). 비면 끔 = 지금 동작(직선 한 구간).
        # `move_to` 의 경로는 충돌을 모른다. 양 끝이 비어도 사이가 막힐 수 있다 — 실습29b 는
        # 조제실 벽, lap3 은 위팔이 **제 상판 3번 칸 벽**까지 0.010 m 였다.
        # 한 점을 끼우면 그 구간을 비껴간다. 부수 효과가 하나 더 있는데 lap3 에서는 그쪽이 본질이다:
        # `solve_ik` 는 **현재 자세에 가장 가까운** 해를 고르므로(`ur5_kinematics.solve_ik` 규칙 3·4)
        # 경유 자세가 다음 해의 씨앗이 되어 **어느 가지로 풀릴지**도 바꾼다.
        # 경로 계획기가 아니다. 값은 마스터에서 확인한 것만 넣는다.
        # **기본값을 주지 않고 형만 선언한다.** 빈 리스트를 기본값으로 주면 rclpy 가 그것을
        # BYTE_ARRAY 로 추론하고, `ParameterDescriptor(type=...)` 로도 그 추론을 이기지 못한다
        # (lap6 에서 노드가 죽었고, 맥마클2 가 Jazzy rclpy 최소 노드로 둘 다 확인했다).
        # 형만 선언하면 값이 없을 때 "미초기화" 가 되므로, 읽는 쪽에서 그것을 끔으로 받는다.
        self.declare_parameter('via_joint_positions', Parameter.Type.DOUBLE_ARRAY)
        self.declare_parameter('home_tolerance_rad', 0.05)
        # 기본값은 Isaac 자산 한계다(elbow 만 ±π). 제원(±2π)만 믿고 푼 해는 자산에서 잘린다.
        self.declare_parameter('joint_limits_low', [low for low, _ in kin.UR5_ASSET_LIMITS])
        self.declare_parameter('joint_limits_high', [high for _, high in kin.UR5_ASSET_LIMITS])
        self.declare_parameter('command_rate_hz', 20.0)
        self.declare_parameter('max_joint_speed', 0.5)
        # 보낸 궤적점이 실제로 도달했는지 본다. **기본 켬**(작전 결정 9/21).
        # 끄면 예전 동작(개루프: 점을 다 내보내면 성공)이다. 실습29b 에서 팔이 벽에 막혀
        # 절반만 갔는데 노드가 성공으로 넘어가 흡착을 켰고 결과가 `grasp_failed` 로 닫혔다.
        # 그 값은 **틀린 정보**였고, 없는 것보다 나빴다.
        self.declare_parameter('arrival_check_enabled', True)
        self.declare_parameter('belt_pick_lock_wrist', False)
        self.declare_parameter('belt_pick_contact_drop_m', 0.0)
        # 도달로 볼 관절 공차. `home_tolerance_rad` 와 같은 급으로 둔다(같은 종류의 판정이다).
        self.declare_parameter('arrival_tolerance_rad', 0.05)
        # 마지막 궤적점을 낸 뒤 도달을 기다리는 시간. 명령 자체가 `max_joint_speed` 로 이미
        # 속도를 맞춰 나가므로 남는 것은 드라이브 지연뿐이다. 2.0 s = 20 Hz 에서 40 주기다.
        # 막혀 있으면 이 시간이 지나야 알 수 있으니, 길게 잡으면 그만큼 늦게 안다.
        self.declare_parameter('arrival_timeout_s', 2.0)
        # 팔 기구학의 기준 프레임. 비면 `{robot_id}/ur_arm_base_link`(결정 47) 로 채운다.
        # 모든 TF 조회(`deck_slot_*`·`<zone>/cabinet`·검출 자세·`<zone>/tag`)가 이 하나를 쓴다.
        # 이름이 `base_link` 가 아닌 이유: 계약 420-434 절에서 `{robot_id}/base_link` 는
        # **이동 베이스**의 프레임(부모 `odom`, 작성자 `base_driver`)이다. UR5 밑동은 그 아래의 다른 링크다.
        self.declare_parameter('arm_base_frame', '')
        # 그 프레임의 축이 DH 기준축과 어떻게 놓였나. `BASE_FRAME_CONVENTIONS` 주석을 읽고 고른다.
        # 기본 `base` 는 지금 동작이다. Isaac UR5 자산은 `base_link` 다(실습27b 에서 확인).
        self.declare_parameter('arm_base_frame_convention', 'base')
        # 기동 때 자기 FK 와 손목 링크 TF 로 위 값을 **스스로 확인**한다(작전 지시 9/21).
        # 받침대(27b)·AMR 합본(lap4) 둘 다 ⑤ 가 프레임 180° 로 끊겼고, 값을 말로 맞추는 한
        # 또 난다. 파라미터와 다르면 기동을 거부한다. TF·관절값이 안 오면 판정하지 않는다.
        self.declare_parameter('arm_base_frame_check', True)
        self.declare_parameter('arm_base_frame_check_tries', 40)   # 0.5 s × 40 = 20 s
        # 대조에 쓸 손목 링크 TF. 비우면 `joint_names` 의 마지막 관절에서 만든다.
        self.declare_parameter('wrist_link_frame', '')
        self.declare_parameter('deck_slot_frame_prefix', '')
        # 칸 프레임 번호의 시작. 프레임 이름은 `{prefix}{target_slot + base}` 다.
        # 기본 0 은 지금 동작(`PickPouch.target_slot` 을 그대로 쓴다)이다.
        # Isaac 스테이지는 `deck_slot_1..N` 로 내므로(1 부터, `p3sim/sensors.py`) 그 경로에서는 1 로 켠다.
        # 계약 3절이 기준을 말하지 않아 결정 28 이 열려 있다 — 결정이 나오면 기본값을 바꾼다.
        self.declare_parameter('deck_slot_frame_base', 0)
        # 상판 칸에서 집을 때 검출 대신 칸 TF 로 파지 자세를 만든다(K5 전달 v0, opt-in).
        # 기본 false = 지금 동작(종류와 무관하게 `PouchDetection` 을 기다린다).
        # 켜는 이유: v0 전달은 YOLO·봉투 QR 이 아직 없어 검출을 낼 주체가 없다.
        # 봉투는 칸 바닥 윗면(= `deck_slot_*` 원점)에 얹혀 있으므로 흡착면 목표는 원점 + 봉투 두께다.
        self.declare_parameter('deck_pick_from_frame', False)
        # 봉투 두께 m. `deck_pick_from_frame` 의 파지 높이와 같은 기하를 쓴다
        # (`place_z_offset_m` = rest_gap + 이 값). 스테이지 `--pouch-size` 의 z 와 같아야 한다.
        self.declare_parameter('pouch_height_m', 0.01)
        # 봉투 검출·태그 판독을 어디서 받나. 기본 `camera` 는 지금 동작(계약 토픽 `hand_camera/*`).
        # `sim` 은 스테이지의 시뮬 센서(`{ns}/sim/*`)를 쓴다. 계약 토픽의 작성자를 둘로 만들지 않으려고
        # 토픽을 나눈다. `scan_tag_source=sim` 이면 팔을 움직이지 않으므로 `tag_standoff_m`·`tool_frame`
        # 이 필요 없다.
        self.declare_parameter('pouch_source', SOURCE_CAMERA)
        self.declare_parameter('scan_tag_source', SOURCE_CAMERA)
        # 벨트 픽 전에 손 카메라로 벨트 끝을 내려다보는 관측 자세(opt-in, 기본 끔). 홈 자세의 카메라가
        # 벨트 끝을 못 보는 구성에서 카메라 검출(`pouch_source=camera`)을 쓰려고 둔다.
        # `belt_view_frame`(예 `pharmacy/belt_end`, +z 위)의 +z 로 `belt_view_standoff_m` 떨어져 마주본다.
        # 0 이면 지금 동작(제자리에서 검출을 기다린다). `tool_frame` 이 있어야 한다. 충돌 검증은 없다.
        self.declare_parameter('belt_view_frame', '')
        # 흡착점(TCP)의 공구(IK 끝점, tool0) 기준 위치 [x, y, z] m. 기본 0 = 지금 동작(끝점이 곧 흡착면).
        # 합본에 흡착 그리퍼 자산을 붙이면 [0, 0, 0.1555] 다(sim/assets/amr_gripper/README.md, 오프라인 측정).
        # 파지·놓기 목표는 흡착점 자세로 만들고 IK 로 넘길 때 공구 자세로 바꾼다. 관측 자세는 공구 자세 그대로다.
        self.declare_parameter('tcp_offset_m', [0.0, 0.0, 0.0])
        self.declare_parameter('belt_view_standoff_m', 0.0)
        # 관측점을 프레임 x(벨트 진행 방향)로 옮긴다. 음수 = 상류. 봉투는 끝점이 아니라 끝 구역에 멈추므로
        # 끝 구역 가운데(-end_zone/2)를 보면 봉투 전체가 화면에 든다.
        self.declare_parameter('belt_view_offset_m', 0.0)
        # 상판 칸에서 집을 때(침상 전달)의 관측 자세. 집을 칸 프레임 위 이 거리에서 내려다본다. 0 = 끔(지금 동작).
        # `deck_pick_from_frame` 이 켜져 있으면 쓰지 않는다(그때는 검출을 안 기다린다).
        self.declare_parameter('deck_view_standoff_m', 0.0)
        # 재관측(9/23 카메라 L3: 첫 관측에서 QR 이 화면 구석·작게 찍혔다). 첫 관측의 검출(QR 을 못 읽어도 봉투 상자)로
        # 봉투 자리를 잡고, 그 위 이 거리에서 봉투 방향에 맞춰 다시 내려다본 뒤 QR 을 읽는다. 0 = 끔.
        self.declare_parameter('refine_view_standoff_m', 0.0)
        # 비전 교차 확인(재범 9/25, 점수판 AI 비전). 참값 센서(`pouch_source: sim`)로 상판 칸에서 집을 때 접근 자세
        # (봉투 위 `approach_height_m`)에서 손 카메라 검출을 기다려, 참값과 `vision_check_tolerance_m` 안이면 **검출
        # 좌표로** 집는다. 시한 안에 없거나 어긋나면 참값으로 집고 `vision_mismatch` 를 로그에 남긴다 — 한 바퀴를 깨지
        # 않는다. 추가 동작이 없다(접근 자세에서 손목 카메라가 봉투를 내려다본다). false = 끔(지금 동작).
        self.declare_parameter('vision_check', False)
        self.declare_parameter('vision_check_timeout_s', 1.0)
        self.declare_parameter('vision_check_tolerance_m', 0.05)
        # 도착 전 이만큼(sim s)의 검출도 쓴다. 회차71: 1 s 창에 프레임이 1장뿐이었고 QR 은 도착 2.2 s 전(접근 중)에
        # 읽혔다. 투영은 그 프레임 stamp 의 카메라 TF 로 하므로 움직이던 중의 프레임도 자리는 맞다.
        self.declare_parameter('vision_check_lookback_s', 3.0)
        # 빈 `zone_id` 일 때의 `<zone>/cabinet`. goal 에 zone 이 있으면 `cabinet_frame_for` 가
        # 그 이름을 쓴다(계약 10.1).
        self.declare_parameter('cabinet_frame', '')
        self.declare_parameter('pick_timeout_s', 60.0)          # 계약 7절
        self.declare_parameter('detection_timeout_s', 5.0)
        self.declare_parameter('detection_max_age_s', 1.0)      # 계약 2.4절
        self.declare_parameter('approach_height_m', 0.10)
        # 흡착면과 봉투 윗면·칸 바닥의 간격. Surface Gripper 구조를 보고 마스터에서 정한다.
        self.declare_parameter('grasp_z_offset_m', 0.0)
        self.declare_parameter('place_z_offset_m', 0.0)
        self.declare_parameter('grasp_settle_s', 0.5)
        # 흡착을 켠 뒤 `holding=true` 를 기다리는 시간. 첫 `false` 로 닫지 않는다 —
        # 스테이지가 붙이는 데 걸리는 지연(lap13 에서 0.55 s)이 `grasp_settle` 보다 길 수 있다.
        # 기본 2.0 s 는 그 관측의 네 배다. 액션 시한이 위를 덮으므로 여기서 늘려도 무한정은 아니다.
        self.declare_parameter('grasp_hold_timeout_s', 2.0)
        self.declare_parameter('release_settle_s', 0.3)
        self.declare_parameter('scan_timeout_s', 30.0)          # 계약 7절
        # 손 카메라를 인식표에서 얼마나 띄울지. QR 판독 거리는 **마스터에서 확인**한다.
        # 0 이면 ScanTag 를 시도하지 않고 UNREADABLE 로 닫는다.
        self.declare_parameter('tag_standoff_m', 0.0)
        # 손 카메라가 달린 UR5 링크(공구 프레임). USD 이름은 마스터에서 확인한다.
        self.declare_parameter('tool_frame', '')
        self.declare_parameter('hand_camera_frame', '')
        # 계약 11.6 `arm_clear_of_belt`. 기본 끔. 통로 상자·링크 반지름·공구·파지물 치수는 **측정값만** 넣는다.
        for name, default in CLEARANCE_PARAMETERS:
            self.declare_parameter(name, default)
        # 흡착 관측: `bool`(기존 gripper/holding, 기본) 또는 `state`(GripperState seq 규칙, 계약 11.6).
        self.declare_parameter('gripper_observation', 'bool')
        for name, default in PLACEMENT_PARAMETERS:
            self.declare_parameter(name, default)

        self._robot_id = self.get_parameter('robot_id').value
        self._joint_names = list(self.get_parameter('joint_names').value)
        self._home = np.asarray(self.get_parameter('home_joint_positions').value, dtype=float)
        # 형만 선언했으므로 값이 없으면 "미초기화" 다. `get_parameter` 는 그때 예외를 내므로
        # `get_parameter_or` 로 받고, 값이 비었으면(미초기화든 빈 배열이든) 끔으로 본다.
        via = list(self.get_parameter_or('via_joint_positions').value or [])
        if via and len(via) != 6:
            raise ValueError(f'via_joint_positions 는 비우거나 6개다: {len(via)}개')
        self._via = np.asarray(via, dtype=float) if via else None
        self._home_tolerance = float(self.get_parameter('home_tolerance_rad').value)
        # 파라미터가 자산보다 넓으면 좁힌다. 넓히는 방향으로는 덮이지 않는다(계약과 무관한 자산 사실).
        self._limits = kin.intersect_limits(
            tuple(zip(self.get_parameter('joint_limits_low').value,
                      self.get_parameter('joint_limits_high').value, strict=False)))
        self._command_rate_hz = float(self.get_parameter('command_rate_hz').value)
        self._max_joint_speed = float(self.get_parameter('max_joint_speed').value)
        self._arrival_check = bool(self.get_parameter('arrival_check_enabled').value)
        self._arrival_tolerance = float(self.get_parameter('arrival_tolerance_rad').value)
        self._arrival_timeout = float(self.get_parameter('arrival_timeout_s').value)
        self._arm_base_frame = (self.get_parameter('arm_base_frame').value
                                or default_arm_base_frame(self._robot_id))
        self._base_convention = self.get_parameter('arm_base_frame_convention').value
        if self._base_convention not in BASE_FRAME_CONVENTIONS:
            raise ValueError(f'arm_base_frame_convention 은 '
                             f'{sorted(BASE_FRAME_CONVENTIONS)} 중 하나다: {self._base_convention!r}')
        self._base_to_kinematic = base_to_kinematic(self._base_convention)
        self._convention_check = bool(self.get_parameter('arm_base_frame_check').value)
        self._convention_max_tries = int(self.get_parameter('arm_base_frame_check_tries').value)
        self._convention_tries = 0
        self._convention_timer = None
        self._wrist_frame = (self.get_parameter('wrist_link_frame').value
                             or wrist_link_frame(self._robot_id, self._joint_names))
        self._deck_slot_prefix = (self.get_parameter('deck_slot_frame_prefix').value
                                  or f'{self._robot_id}/deck_slot_')
        self._deck_slot_base = int(self.get_parameter('deck_slot_frame_base').value)
        self._deck_pick_from_frame = bool(self.get_parameter('deck_pick_from_frame').value)
        self._pouch_source = self._sensor_source('pouch_source')
        self._scan_tag_source = self._sensor_source('scan_tag_source')
        if self._deck_pick_from_frame and self._pouch_source == SOURCE_SIM:
            # 둘 다 켜면 `deck_pick_from_frame` 이 먼저 걸려 **센서를 조용히 무시한다**. 그쪽이 더 나쁘다.
            raise ValueError('deck_pick_from_frame 과 pouch_source=sim 은 둘 중 하나만 켠다. '
                             'sim 센서가 칸과 자세를 주므로 칸 TF 우회가 필요 없다')
        self._belt_view_frame = str(self.get_parameter('belt_view_frame').value)
        offset = [float(v) for v in (self.get_parameter('tcp_offset_m').value or [])]
        if len(offset) != 3:
            raise ValueError(f'tcp_offset_m 은 [x, y, z] 세 값이다: {offset}')
        self._tool_from_tcp = np.eye(4)
        self._tool_from_tcp[:3, 3] = offset
        self._belt_view_standoff = float(self.get_parameter('belt_view_standoff_m').value)
        self._belt_view_offset = float(self.get_parameter('belt_view_offset_m').value)
        self._deck_view_standoff = float(self.get_parameter('deck_view_standoff_m').value)
        self._refine_standoff = float(self.get_parameter('refine_view_standoff_m').value)
        self._belt_pick_lock_wrist = bool(self.get_parameter('belt_pick_lock_wrist').value)
        self._belt_pick_contact_drop = float(self.get_parameter('belt_pick_contact_drop_m').value)
        if not 0.0 <= self._belt_pick_contact_drop <= 0.06:
            raise ValueError('belt_pick_contact_drop_m must be between 0 and 0.06 m')
        if self._belt_view_standoff > 0.0 and not self._belt_view_frame:
            raise ValueError('belt_view_standoff_m 을 주면 belt_view_frame 도 준다(예: pharmacy/belt_end)')
        self._pouch_height = float(self.get_parameter('pouch_height_m').value)
        self._cabinet_frame = self.get_parameter('cabinet_frame').value
        self._pick_timeout = float(self.get_parameter('pick_timeout_s').value)
        self._detection_timeout = float(self.get_parameter('detection_timeout_s').value)
        self._detection_max_age = float(self.get_parameter('detection_max_age_s').value)
        self._vision_check = bool(self.get_parameter('vision_check').value)
        self._vision_timeout = float(self.get_parameter('vision_check_timeout_s').value)
        self._vision_tolerance = float(self.get_parameter('vision_check_tolerance_m').value)
        self._vision_lookback = float(self.get_parameter('vision_check_lookback_s').value)
        self._approach_height = float(self.get_parameter('approach_height_m').value)
        self._grasp_z_offset = float(self.get_parameter('grasp_z_offset_m').value)
        self._place_z_offset = float(self.get_parameter('place_z_offset_m').value)
        self._grasp_settle = float(self.get_parameter('grasp_settle_s').value)
        self._grasp_hold_timeout = float(self.get_parameter('grasp_hold_timeout_s').value)
        self._release_settle = float(self.get_parameter('release_settle_s').value)
        self._scan_timeout = float(self.get_parameter('scan_timeout_s').value)
        self._tag_standoff = float(self.get_parameter('tag_standoff_m').value)
        self._tool_frame = self.get_parameter('tool_frame').value
        self._hand_camera_frame = (self.get_parameter('hand_camera_frame').value
                                   or f'{self._robot_id}/hand_camera_optical')
        self._clearance_enabled = bool(self.get_parameter('arm_clearance_enabled').value)
        self._gripper_observation = self.get_parameter('gripper_observation').value
        if self._gripper_observation not in ('bool', 'state'):
            raise ValueError(f'gripper_observation 은 bool 또는 state 다: {self._gripper_observation!r}')
        self._placement_enabled = bool(self.get_parameter('placement_check_enabled').value)
        problem = placement.dependency_problem(self._placement_enabled, self._gripper_observation)
        if problem:
            raise ValueError(problem)
        self._placement_standoff = float(self.get_parameter('placement_view_standoff_m').value)
        self._placement_slot_box = self._vector_parameter('placement_slot_box_m', 3)
        self._placement_cabinet_box = self._vector_parameter('placement_cabinet_box_m', 3)
        self._stop_slots = placement.StopSlots()
        self._placement_timeout = float(self.get_parameter('placement_timeout_s').value)
        self._clearance_region = self.get_parameter('arm_clearance_region').value
        self._clearance_lane_frame = self.get_parameter('arm_clearance_lane_frame').value
        self._clearance_config = self._clearance_config_from_parameters()

        if len(self._joint_names) != 6 or len(self._home) != 6 or len(self._limits) != 6:
            raise ValueError('joint_names, home_joint_positions, joint_limits 는 6개여야 한다')
        if not self.get_parameter('use_sim_time').value:
            self.get_logger().warn('use_sim_time 이 false 다. 계약 4절은 모든 노드가 sim time 이다.')

        self._lock = threading.Lock()
        self._joints = Freshness(STALE_JOINTS_S)
        self._joints_stamp = None                     # 마지막 joint_states 의 header.stamp(msg)
        self._holding = Freshness(STALE_STATUS_S)
        self._base_stopped = Freshness(STALE_STATUS_S)
        self._belt = Freshness(STALE_STATUS_S)
        self._pouches = None
        self._vision_pouches = None
        self._tag_read = None
        self._epoch = 0
        self._goal_active = False
        self._homing = False
        self._homing_cancelled = False
        self._gripper_closed = False
        self._clock_watch = ClockWatch(self.sim_now())
        self._fence = ResetFence()
        # 노드를 내리는 중. 액션 실행·홈 복귀가 멈추고 관절·그리퍼 명령·이벤트를 더 내지 않는다.
        self._closing = threading.Event()
        self._goal_generation = 0

        self._callbacks = ReentrantCallbackGroup()
        self._tf_buffer = Buffer()
        self._tf_listener = TransformListener(self._tf_buffer, self)

        namespace = f'/{self._robot_id}'
        self._joint_command_pub = self.create_publisher(
            JointState, f'{namespace}/arm/joint_command', QOS_RELIABLE)
        self._gripper_pub = self.create_publisher(
            Bool, f'{namespace}/gripper/command', QOS_RELIABLE)
        self._at_home_pub = self.create_publisher(
            Bool, f'{namespace}/arm/at_home', QOS_HEARTBEAT)
        self._gripper_view = clear_state.GripperView(STALE_STATUS_S, GripperState.STATE_HELD,
                                                     GripperState.STATE_RELEASED)
        self._clearance_seq = clear_state.StampSeq()
        self._clearance_pub = None
        self._command_seq = clear_state.CommandSeq()
        self._last_command = None                     # (close, command_seq 또는 None, epoch)
        self._gripper_command_pub = None
        self._gripper_state_subscribed = False
        self._setup_clearance(namespace)
        self._setup_gripper_observation(namespace)
        if self._placement_enabled:
            problem = self._placement_config_problem()
            if problem:
                self.get_logger().error(f'placement_check 을 켰지만 설정이 없다: {problem}. '
                                        '모든 픽은 안착 미확인으로 닫힌다.')
            self.get_logger().warn('placement_check 켬. 관측 자세 이동은 충돌 검증이 없다(L3 확인 전에는 켜지 않는다).')
        self._event_pub = self.create_publisher(Event, '/events', QOS_LATCHED_EVENTS)

        self.create_subscription(JointState, f'{namespace}/joint_states',
                                 self._on_joint_states, QOS_SENSOR,
                                 callback_group=self._callbacks)
        self.create_subscription(Bool, f'{namespace}/gripper/holding',
                                 self._on_holding, QOS_HEARTBEAT,
                                 callback_group=self._callbacks)
        self.create_subscription(Bool, f'{namespace}/base/stopped',
                                 self._on_base_stopped, QOS_HEARTBEAT,
                                 callback_group=self._callbacks)
        self._pouch_topic = self._sensor_topic(self._pouch_source, namespace, 'pouches', 'pouches')
        self._tag_topic = self._sensor_topic(self._scan_tag_source, namespace, 'tag_reads', 'tag_reads')
        self.create_subscription(PouchDetectionArray, self._pouch_topic, self._on_pouches,
                                 QOS_DETECTIONS, callback_group=self._callbacks)
        self._vision_topic = ''
        if self._vision_check and self._pouch_source == SOURCE_SIM:
            # 참값으로 집으면서 카메라를 따로 듣는다. 카메라 집기(`pouch_source: camera`)면 이미 검출로 집는다.
            self._vision_topic = self._sensor_topic(SOURCE_CAMERA, namespace, 'pouches', 'pouches')
            self.create_subscription(PouchDetectionArray, self._vision_topic, self._on_vision_pouches,
                                     QOS_DETECTIONS, callback_group=self._callbacks)
        self.create_subscription(TagRead, self._tag_topic, self._on_tag_read,
                                 QOS_RELIABLE, callback_group=self._callbacks)
        self.create_subscription(Event, '/events', self._on_event, QOS_LATCHED_EVENTS,
                                 callback_group=self._callbacks)
        self.create_subscription(BeltState, '/pharmacy/belt', self._on_belt,
                                 QOS_HEARTBEAT, callback_group=self._callbacks)

        # `arm/at_home` 는 5 Hz heartbeat 다 (계약 2.3절).
        self.create_timer(0.2, self._publish_at_home, callback_group=self._callbacks)

        self._pick_server = ActionServer(
            self, PickPouch, f'{namespace}/pick_pouch',
            execute_callback=self._execute_pick,
            goal_callback=self._accept_pick,
            cancel_callback=self._accept_cancel,
            callback_group=self._callbacks)

        self._scan_server = ActionServer(
            self, ScanTag, f'{namespace}/scan_tag',
            execute_callback=self._execute_scan,
            goal_callback=self._accept_scan,
            cancel_callback=self._accept_cancel,
            callback_group=self._callbacks)

        self.get_logger().info(
            f'arm up. robot={self._robot_id} base_frame={self._arm_base_frame} '
            f'convention={self._base_convention} joints={self._joint_names}')
        # L3 판정선: **어느 토픽을 보고 있는지**가 로그에 있어야 한다. 출처가 틀리면 증상이
        # "검출이 안 온다"(= not_detected)로만 보여서 설정 문제와 센서 문제가 구별되지 않는다.
        self.get_logger().info(
            f'arm sensors. pouches={self._pouch_topic} ({self._pouch_source}) '
            f'tag_reads={self._tag_topic} ({self._scan_tag_source}) '
            f'deck_pick_from_frame={self._deck_pick_from_frame}')
        if self._convention_check:
            self._convention_timer = self.create_timer(
                0.5, self._check_convention_once, callback_group=self._callbacks)

    def _check_convention_once(self):
        """기동 때 한 번, 자기 FK 와 TF 로 `arm_base_frame_convention` 을 **스스로 확인**한다.

        받침대(실습27b)와 AMR 합본(lap4) 둘 다 ⑤ 가 프레임 180° 로 끊겼다. 값을 말로 맞추는
        한 같은 회차를 또 쓴다. 관절값과 손목 링크 TF 가 둘 다 들어오면 그 자리에서 갈린다.

        파라미터와 다르면 **기동을 거부한다**(작전 지시). 재료가 아직 없으면 판정하지 않고
        다음 주기에 다시 본다 — 못 본 것은 틀린 것과 다르다.
        """
        joints = self.joint_positions()
        pose = self.lookup_pose(self._arm_base_frame, self._wrist_frame)
        if joints is None or pose is None:
            self._convention_tries += 1
            if self._convention_tries == self._convention_max_tries:
                self.get_logger().warn(
                    f'관례 자가 확인을 못 했다(관절값={joints is not None} '
                    f'TF {self._arm_base_frame}→{self._wrist_frame}={pose is not None}). '
                    f'파라미터 {self._base_convention!r} 를 그대로 믿고 간다 — 확인된 값이 아니다.')
                self._convention_timer_done()
            return
        self._convention_timer_done()
        got, detail = matching_convention(kin.forward_kinematics(joints)[:3, 3], pose[:3, 3])
        if got is None:
            raise ValueError(f'arm_base_frame_convention 을 가릴 수 없다({detail}). '
                             f'FK 도 TF 도 맞지 않는다 — joint_names·arm_base_frame·DH·자산을 본다')
        if got != self._base_convention:
            raise ValueError(f'arm_base_frame_convention 이 {self._base_convention!r} 인데 '
                             f'자산은 {got!r} 다({detail}). 그대로 돌면 팔이 반대편을 집는다')
        self.get_logger().info(f'관례 확인. arm_base_frame_convention={got} ({detail})')

    def _convention_timer_done(self):
        """한 번 판정했으면 타이머를 멈춘다."""
        self._convention_check = False
        if self._convention_timer is not None:
            self._convention_timer.cancel()
            self._convention_timer = None

    # ---- 수신 ----------------------------------------------------------

    def _sensor_source(self, name):
        """`pouch_source`·`scan_tag_source` 를 읽고 검사한다. 모르는 값은 거부한다."""
        value = str(self.get_parameter(name).value)
        if value not in SENSOR_SOURCES:
            raise ValueError(f'{name} 은 {SENSOR_SOURCES} 중에서다: {value!r}')
        return value

    def _sensor_topic(self, source, namespace, camera_name, sim_name):
        """출처에 맞는 토픽 이름. `sim` 은 계약 토픽을 쓰지 않는다(작성자가 둘이 되면 안 된다)."""
        return (f'{namespace}/hand_camera/{camera_name}' if source == SOURCE_CAMERA
                else f'{namespace}/sim/{sim_name}')

    def _on_joint_states(self, msg):
        """UR5 6개만 뽑는다. 이름이 없으면 무시한다(dummy 조인트가 섞여 온다)."""
        index = dict(zip(msg.name, msg.position, strict=False))
        try:
            values = np.array([index[name] for name in self._joint_names], dtype=float)
        except KeyError:
            # 같은 토픽에 다른 발행자가 섞인다(베이스 3관절 20 Hz 등). 남의 메시지를 건너뛰는 것은
            # 정상이라 **조용히** 넘긴다 — WARN 으로 찍으면 한 바퀴 내내 로그를 덮어 **진짜 고장을 가린다**.
            # 진짜 문제(UR5 값이 stale)일 때만 아래에서 한 번 경고한다.
            self.get_logger().debug(
                f'joint_states 에 UR5 관절이 없어 건너뛴다. 받음: {list(msg.name)}')
            if self.joint_positions() is None:
                self.get_logger().warn(
                    f'UR5 관절값이 stale 이다(기대: {self._joint_names}, 마지막 메시지: {list(msg.name)}).',
                    throttle_duration_sec=5.0)
            return
        with self._lock:
            self._joints.update(values)
            self._joints_stamp = msg.header.stamp

    def _on_gripper_state(self, msg):
        with self._lock:
            self._gripper_view.update(msg.epoch, msg.seq, msg.state, time.monotonic(),
                                      msg.last_applied_command_seq)

    def _on_holding(self, msg):
        with self._lock:
            self._holding.update(bool(msg.data))

    def _on_base_stopped(self, msg):
        with self._lock:
            self._base_stopped.update(bool(msg.data))

    def _on_belt(self, msg):
        with self._lock:
            self._belt.update(msg)

    def _on_pouches(self, msg):
        with self._lock:
            self._pouches = msg

    def _on_vision_pouches(self, msg):
        with self._lock:
            self._vision_pouches = msg
            # 최근 검출을 몇 장 남긴다(도착 전 판독을 쓰려고, `vision_check_lookback_s`).
            self._vision_history = (list(getattr(self, '_vision_history', [])) + [msg])[-30:]

    def _on_tag_read(self, msg):
        with self._lock:
            self._tag_read = msg

    def _on_event(self, msg):
        """epoch 는 orchestrator 만 발급한다. arm 은 본 것 중 가장 큰 값을 따른다(계약 4절)."""
        with self._lock:
            if msg.epoch > self._epoch:
                self._epoch = msg.epoch
        if msg.name == Event.RESET_BEGIN:
            self.on_reset_begin(msg.epoch)
        elif msg.name == Event.RESET_DONE:
            self.on_reset(msg.epoch)

    def on_reset_begin(self, epoch):
        """계약 6절 0: 같은 epoch 의 RESET_DONE 까지 관절·그리퍼 명령을 멈추고 isaac 에 양보한다."""
        with self._lock:
            if not self._fence.begin(epoch):
                return
        self.stop_homing()
        self.get_logger().info(f'RESET_BEGIN epoch={epoch}. RESET_DONE 까지 관절·그리퍼 명령을 내지 않는다.')

    def on_reset(self, epoch):
        """리셋 barrier 4단계: 캐시를 버리고 at_home 을 다시 계산한다(계약 6절). 같은 RESET_DONE 은 한 번만."""
        with self._lock:
            if not self._fence.accepts_done(epoch):
                return
        self.stop_homing()
        self._wait_goal_idle()
        with self._lock:
            self._fence.done(epoch)
            self._clock_watch.rebase(self.sim_now())
            self._joints.clear()
            self._joints_stamp = None
            self._holding.clear()
            self._gripper_view.clear()
            self._command_seq.reset()                 # 계약 11.6: RESET_DONE 뒤 첫 명령은 command_seq=1
            self._last_command = None
            self._base_stopped.clear()
            self._belt.clear()
            self._pouches = None
            self._vision_pouches = None
            self._tag_read = None
        self._tf_buffer.clear()
        self.get_logger().info(f'RESET_DONE epoch={epoch}. 캐시를 버리고 at_home 을 다시 낸다.')

    # ---- 상태 ----------------------------------------------------------

    def joint_positions(self):
        """살아 있는 UR5 관절값 6개. 1.0 s 안 오면 None."""
        with self._lock:
            return self._joints.get()

    def base_stopped(self):
        """`base/stopped` 의 현재 값. unknown 이면 None."""
        with self._lock:
            return self._base_stopped.get()

    def gripper_holding(self):
        """`gripper/holding` 의 현재 값. unknown 이면 None."""
        with self._lock:
            return self._holding.get()

    def belt_state(self):
        """`/pharmacy/belt` 의 현재 값. unknown 이면 None."""
        with self._lock:
            return self._belt.get()

    def latest_pouches(self, not_older_than_sim_s):
        """`hand_camera/pouches` 의 마지막 메시지. 요청 시각보다 오래되면 None (계약 2.4절)."""
        with self._lock:
            message = self._pouches
        if message is None:
            return None
        stamp = RclTime.from_msg(message.header.stamp).nanoseconds * 1e-9
        return message if stamp >= not_older_than_sim_s else None

    def latest_tag_read(self, not_older_than_sim_s):
        """`hand_camera/tag_reads` 의 마지막 판독. 요청 시각보다 오래되면 None (계약 2.4절)."""
        with self._lock:
            message = self._tag_read
        if message is None:
            return None
        stamp = RclTime.from_msg(message.header.stamp).nanoseconds * 1e-9
        return message if stamp >= not_older_than_sim_s else None

    def epoch(self):
        with self._lock:
            return self._epoch

    def set_goal_active(self, active):
        """활성 goal 표시. false 면 관절 명령을 내지 않는다(계약 5절)."""
        with self._lock:
            self._goal_active = bool(active)

    def goal_active(self):
        with self._lock:
            return self._goal_active

    def homing(self):
        """goal 결과를 돌려준 뒤 홈으로 가는 중인가. 이 동안도 팔은 움직인다."""
        with self._lock:
            return self._homing

    def fenced(self):
        """리셋 barrier 중인가(RESET_BEGIN 뒤, 같은 epoch 의 RESET_DONE 전)."""
        with self._lock:
            return self._fence.fenced

    def generation(self):
        with self._lock:
            return self._fence.generation

    def fence_moved(self, generation):
        """작업을 시작한 뒤 barrier 경계를 지났나. 지났으면 그 작업은 명령을 더 내지 않는다."""
        with self._lock:
            return self._fence.generation != generation

    def _wait_goal_idle(self, limit_s=2.0):
        """RESET_DONE 에서 울타리를 열기 전에 이전 goal 이 끝나기를 기다린다(wall 상한)."""
        deadline = time.monotonic() + limit_s
        while self.goal_active() and time.monotonic() < deadline:
            time.sleep(0.01)

    def moving(self):
        """관절 명령을 내도 되는 상태. 활성 goal 이거나 그 goal 의 홈 복귀 중."""
        with self._lock:
            return self._goal_active or self._homing

    def at_home(self):
        """홈 자세 0.05 rad 이내 + 움직이는 중이 아님. 관절값이 unknown 이면 None."""
        joints = self.joint_positions()
        if joints is None:
            return None
        return kin.at_pose(joints, self._home, self._home_tolerance) and not self.moving()

    def _publish_at_home(self):
        """unknown 이면 아무것도 내지 않는다. 오래된 true 로 출발하지 않게 한다(계약 4절)."""
        value = self.at_home()
        if value is None:
            return
        self._at_home_pub.publish(Bool(data=value))

    # ---- 송신 ----------------------------------------------------------

    def send_joint_command(self, joints):
        """UR5 6개만 position 으로 낸다. 움직일 이유가 없거나, 관절값이 stale 이거나, barrier·종료 중이면 안 낸다."""
        if self._closing.is_set() or self.fenced() or not self.moving():
            return False
        if self.joint_positions() is None:
            self.get_logger().warn('joint_states 가 1.0 s 없다. 관절 명령을 멈춘다.',
                                   throttle_duration_sec=1.0)
            return False
        message = JointState()
        message.header.stamp = self.get_clock().now().to_msg()
        message.name = list(self._joint_names)
        message.position = [float(value) for value in kin.clamp_to_limits(joints, self._limits)]
        self._joint_command_pub.publish(message)
        return True

    def set_gripper(self, closed):
        """Surface Gripper 명령. true = 닫기(흡착). Isaac 쪽 구현은 simulation 레인이다. barrier·종료 중이면 안 낸다."""
        if self._closing.is_set() or self.fenced():
            return
        # L3 판정선: **누가 언제 흡착을 껐나.** lap9 에서 스테이지의 `suction on` 바로 뒤에
        # `suction off` 가 찍혔는데, 팔이 보낸 것인지 스테이지가 스스로 놓은 것인지 갈리지
        # 않았다. 값이 바뀔 때만 찍어 20 Hz 로 로그를 덮지 않는다.
        if bool(closed) != self._gripper_closed:
            self.get_logger().info(
                f'gripper {"on" if closed else "off"} sim={self.sim_now():.3f}')
        self._gripper_closed = bool(closed)
        self._gripper_pub.publish(Bool(data=self._gripper_closed))
        if self._gripper_command_pub is not None:
            self._publish_gripper_command(self._gripper_closed)

    def _publish_gripper_command(self, closed):
        """`GripperCommand`. epoch 는 마지막 RESET_DONE. 모르면 내지 않고 판정은 관측 소실(UNKNOWN)이 된다."""
        with self._lock:
            view = clear_state.publish_epoch(self._epoch, self._fence.done_epoch, self._fence.fenced)
            if view.epoch is None:
                self._last_command = (closed, None, None)
                return
            seq = self._command_seq.next(view.epoch)
            self._last_command = (closed, seq, view.epoch)
        message = GripperCommand()
        message.header.stamp = self.get_clock().now().to_msg()
        message.epoch = int(view.epoch)
        message.command_seq = int(seq)
        message.close = bool(closed)
        self._gripper_command_pub.publish(message)

    def gripper_command_result(self):
        """state 모드: 마지막 명령의 (CONFIRMED·CONTRADICTED·PENDING·UNKNOWN, 이유). 명령이 없으면 UNKNOWN."""
        with self._lock:
            command = self._last_command
            if command is None:
                return clear_state.UNKNOWN, '흡착 명령을 낸 적이 없다'
            closed, seq, epoch = command
            return self._gripper_view.command_result(epoch, time.monotonic(), seq, closed)

    def gripper_closed(self):
        """arm 이 마지막으로 낸 그리퍼 명령. holding 이 이것과 어긋나면 낙하다."""
        return self._gripper_closed

    def dropped(self):
        """이송 중 arm 이 열지 않았는데 놓쳤는가(계약 5절).

        bool: `holding` 이 false. state: 닫기 명령이 적용됐는데 GripperState 가 RELEASED(계약 11.6).
        state 에서 관측이 끊기거나 오래된 것은 낙하가 아니라 관측 소실이다(`feedback_lost`).
        """
        if self._gripper_command_pub is None:
            return self.gripper_closed() and self.gripper_holding() is False
        return self.gripper_closed() and self.gripper_command_result()[0] == clear_state.CONTRADICTED

    def feedback_lost(self):
        """state 모드에서 흡착 중인데 관측이 없거나 오래됐나. (소실인가, 이유). bool 모드는 늘 (False, '')."""
        if self._gripper_command_pub is None or not self.gripper_closed():
            return False, ''
        result, reason = self.gripper_command_result()
        return result in (clear_state.UNKNOWN, clear_state.PENDING), reason

    def publish_event(self, name, request_id='', order_id='', detail=''):
        """`/events`. stamp 는 sim time, epoch 는 필수다(계약 2.5절). 종료 중이면 내지 않는다."""
        if self._closing.is_set():
            return
        message = Event()
        message.header.stamp = self.get_clock().now().to_msg()
        message.name = name
        message.request_id = request_id
        message.order_id = order_id
        message.robot_id = self._robot_id
        message.epoch = self.epoch()
        message.detail = detail
        self._event_pub.publish(message)

    # ---- 동작 ----------------------------------------------------------

    def home_joints(self):
        return np.array(self._home, dtype=float)

    def sim_now(self):
        """sim time (초). 액션 타임아웃은 sim time 이다(계약 4절)."""
        return self.get_clock().now().nanoseconds * 1e-9

    def wait(self, sim_seconds, cancelled=None):
        """sim time 으로 기다린다. 취소되면 즉시 빠져나온다.

        `/clock` 이 멈추면 sim time 도 멈추므로 wall 상한(계약 4절 2.0 s 의 두 배)을 함께 둔다.
        """
        start_sim = self.sim_now()
        start_wall = time.monotonic()
        wall_limit = sim_seconds + 4.0
        while rclpy.ok():
            if self._closing.is_set() or (cancelled is not None and cancelled()):
                return False
            if self.sim_now() - start_sim >= sim_seconds:
                return True
            if time.monotonic() - start_wall > wall_limit:
                self.get_logger().warn('/clock 이 멈춘 것 같다. wall 상한에서 빠져나온다.')
                return False
            time.sleep(0.005)
        return False

    def move_to(self, target_joints, cancelled=None):
        """관절 공간 직선 경로를 궤적 점마다 낸다. 계약 2.1절 "궤적 점마다".

        **경로가 충돌을 피하지 않는다.** 양 끝이 비어 있어도 사이가 막혀 있을 수 있다
        (실습29b: 홈도 목표도 벽 밖인데 그 사이가 조제실 벽을 지났다). 그래서 보낸 뒤에
        도달을 확인한다 — 막힌 것을 여기서 잡지 못하면 다음 단계가 그 실패를 제 이름으로
        보고한다.
        """
        current = self.joint_positions()
        if current is None:
            return MoveResult(False, detail='관절값이 없다')
        step = max(1e-3, self._max_joint_speed / max(1.0, self._command_rate_hz))
        period = 1.0 / max(1.0, self._command_rate_hz)
        for point in kin.interpolate_joint_path(current, target_joints, step):
            if cancelled is not None and cancelled():
                return MoveResult(False)
            if not self.send_joint_command(point):
                return MoveResult(False)
            if not self.wait(period, cancelled):
                return MoveResult(False)
        return self._wait_for_arrival(target_joints, cancelled)

    def _wait_for_arrival(self, target_joints, cancelled):
        """마지막 궤적점을 낸 뒤 실제로 도달했는지 본다. 끄면 예전 동작(항상 성공)이다."""
        if not self._arrival_check:
            return MoveResult(True)
        limit = self.sim_now() + self._arrival_timeout
        problem = '관절값이 없다'
        while True:
            current = self.joint_positions()
            if current is not None:
                problem = arrival_problem(self._joint_names, target_joints, current,
                                          self._arrival_tolerance)
                if problem is None:
                    return MoveResult(True)
            if cancelled is not None and cancelled():
                return MoveResult(False)
            if self.sim_now() >= limit:
                self.get_logger().warn(f'{problem} — {self._arrival_timeout:.1f} s 기다렸다. '
                                       '경로가 막혔는지 본다(계약 7절 timeout).')
                return MoveResult(False, perm.OUTCOME_TIMEOUT, problem)
            if not self.wait(0.05, cancelled):
                return MoveResult(False)

    def move_home(self, cancelled=None):
        """홈으로. **경유 자세를 거쳐서** 간다. 도착하면 ARM_HOME 이벤트를 낸다.

        lap13 셋째 바퀴: 작업 자세에서 홈으로 가는 직선이 막혀 `at_home` 이 계속 false 였고,
        orchestrator 가 복귀를 46 s 기다리다 **트립 전체가 멈췄다.** 갈 길이 하나뿐이라
        그 하나가 막히면 회복이 없다. 경유를 거치면 "작업 자세→경유" 와 "경유→홈" 두 구간이
        되는데, 둘 다 이미 확인한 구간이다(경유를 안 켰으면 지금 동작 그대로다).
        """
        if not self.move_via(cancelled):
            self.get_logger().warn('경유 자세로 못 갔다. 홈으로 곧바로 시도한다.')
        if not self.move_to(self.home_joints(), cancelled):
            return False
        self.publish_event(Event.ARM_HOME)
        return True

    def start_homing(self):
        """**결과를 돌려준 뒤에** 홈으로 간다.

        액션 콜백 안에서 복귀를 끝내면 `ARM_HOME` 이 orchestrator 의 `LOAD_DONE`·
        `ORDER_DONE` 을 앞질러 계약 2.6절의 이벤트 순서가 어긋난다. 그래서 결과를 먼저
        보내고, 복귀는 타이머 콜백에서 마친다. 복귀가 끝날 때까지 `at_home` 은 false 다.
        """
        with self._lock:
            if self._fence.fenced or self._closing.is_set():
                return               # 리셋 barrier·종료 중에는 홈으로 가지 않는다. isaac 이 되돌린다
            self._homing = True
            self._homing_cancelled = False
            generation = self._fence.generation
        handle = {}

        def go_home():
            # 타이머 손잡이를 잡기 전에 콜백이 먼저 돌 수 있다. 그러면 다음 주기에 정리한다.
            timer = handle.get('timer')
            if timer is None:
                return
            self.destroy_timer(timer)
            try:
                self.move_home(lambda: self._homing_stopped() or self.fence_moved(generation))
            finally:
                with self._lock:
                    self._homing = False

        handle['timer'] = self.create_timer(0.01, go_home, callback_group=self._callbacks)

    def _homing_stopped(self):
        with self._lock:
            return self._homing_cancelled or self._closing.is_set() or not rclpy.ok()

    def stop_homing(self, limit_s=2.0):
        """새 goal 이나 리셋이 오면 복귀를 접는다. 복귀 콜백이 끝날 때까지 기다린다."""
        with self._lock:
            if not self._homing:
                return
            self._homing_cancelled = True
        deadline = time.monotonic() + limit_s
        while self.homing() and time.monotonic() < deadline:
            time.sleep(0.01)

    def tool_target(self, target, tool=False):
        """IK 에 넘길 공구(tool0) 자세. `tool=False` 면 `target` 은 흡착점 자세라 `tcp_offset_m` 만큼 되돌린다."""
        target = np.asarray(target, dtype=float)
        return target if tool else target @ kin.invert(self._tool_from_tcp)

    def move_to_pose(self, target, cancelled=None, tool=False):
        """목표 자세를 IK 로 풀어서 간다. 반환은 `MoveResult` 다(실패면 거짓).

        `target` 은 기본으로 **흡착점** 자세다(파지·놓기). 관측 자세처럼 공구 자세를 넘길 때는 `tool=True`.

        IK 가 못 푼 것과 풀었는데 못 간 것은 다른 실패다. 앞은 `outcome` 을 비워 호출부가
        정하게 두고(예전 그대로), 뒤는 `move_to` 가 `timeout` 으로 채워 준다.
        """
        seed = self.joint_positions()
        if seed is None:
            return MoveResult(False, detail='관절값이 없다')
        result = kin.solve_ik(self.tool_target(target, tool), seed, home=self._home, limits=self._limits)
        if not result.ok:
            self.get_logger().warn(
                f'IK 실패. 위치오차 {result.position_error:.4f} m, 회전오차 {result.rotation_error:.4f} rad')
            return MoveResult(False)
        return self.move_to(result.joints, cancelled)

    def move_suction_locked(self, target, wrist, cancelled):
        """흡착면은 아래로, 마지막 관절은 관측 직후 값으로 유지하며 이동한다."""
        seed = self.joint_positions()
        if seed is None or np.linalg.norm(self._tool_from_tcp[:2, 3]) > 1e-8:
            return MoveResult(False, detail='관절값 없음 또는 축 밖 TCP')
        result = kin.solve_suction_ik(self.tool_target(target), seed, wrist, self._limits)
        self.get_logger().info(f'손목 고정 접근: TCP 목표 {_xyz(target)}, J6 {wrist:+.4f}, '
                               f'IK={result.ok} 오차 {result.position_error:.5f} m')
        if not result.ok:
            return MoveResult(False, detail='손목 고정 IK 실패')
        return self.move_to(result.joints, cancelled)

    def lookup_pose(self, parent_frame, child_frame, stamp=None):
        """TF 로 `parent_frame` 에서 본 `child_frame` 의 4x4. 못 찾으면 None."""
        try:
            transform = self._tf_buffer.lookup_transform(
                parent_frame, child_frame,
                stamp if stamp is not None else RclTime(),
                timeout=Duration(seconds=0.5))
        except TransformException as error:
            self.get_logger().warn(f'TF {parent_frame} <- {child_frame} 없음: {error}')
            return None
        rotation = transform.transform.rotation
        translation = transform.transform.translation
        return kin.matrix_from_quaternion(
            rotation.x, rotation.y, rotation.z, rotation.w,
            (translation.x, translation.y, translation.z))

    def _source_slot(self, goal):
        """집을 상판 칸 번호. **`PickPouch` 에 그 필드가 아직 없다.**

        `source=SOURCE_DECK` 에서 `target_slot` 은 "놓을 곳"(보관함이면 -1)이라 집을 칸을 담지 못한다.
        v0 한 바퀴는 1인 주문 한 건이라 적재도 전달도 **칸 0** 이므로 0 을 쓴다.
        계약에 `source_slot` 을 넣을지는 **결정 44** 가 열려 있다 — 결정이 나면 이 함수 한 줄만 바꾼다.
        """
        return 0

    def cabinet_frame_for(self, goal):
        """`PickPouch` goal → 보관함 TF 이름. 계약 10.1.

        goal 의 `zone_id` 가 있으면 `{zone_id}/cabinet` 이다. 비었으면 파라미터 `cabinet_frame` 을 쓴다 —
        침상이 하나인 빈월드·조제실 회차가 그대로 돌게 하려는 기본값이다(계약 10.1 "빈 문자열을 기본으로
        두는 이유"). 이름을 여기 한 곳에서만 만든다.

        `target_slot >= 0`(상판 칸)이면 부르지 않는다. 그 경로는 `deck_slot_frame` 이다.
        """
        zone_id = getattr(goal, 'zone_id', '') or ''
        return f'{zone_id}/cabinet' if zone_id else self._cabinet_frame

    def deck_slot_frame(self, target_slot):
        """`PickPouch.target_slot` → 상판 칸 TF 이름. `{prefix}{target_slot + base}` 다.

        `target_slot` 은 **0 부터**인데 Isaac 스테이지는 프레임을 **1 부터** 낸다(`deck_slot_1..N`).
        그 어긋남을 `deck_slot_frame_base` 로 덮는다. 기본 0 은 지금 동작 그대로라 계약 결정(28)을
        기다리지 않아도 된다. 번호를 여기 한 곳에서만 만든다 — 부르는 쪽이 문자열을 짜지 않는다.
        """
        return f'{self._deck_slot_prefix}{target_slot + self._deck_slot_base}'

    def frame_pose_in_base(self, frame_id, stamp=None):
        """프레임 하나를 **기구학 기준**에서 본 4x4. 못 찾으면 None.

        팔이 쓰는 데카르트 자세는 전부 이 함수를 지난다(놓을 곳·상판 칸·보관함·인식표,
        그리고 `_pouch_pose_in_base` 를 거치는 검출 자세까지). 그래서 축 보정도 여기 한 곳에서 한다.
        `arm_base_frame_convention` 이 기본 `base` 면 보정은 항등이라 동작이 그대로다.
        """
        pose = self.lookup_pose(self._arm_base_frame, frame_id, stamp)
        return None if pose is None else self._base_to_kinematic @ pose

    # ---- arm_clear_of_belt (계약 11.6, opt-in) ------------------------------

    def _setup_clearance(self, namespace):
        """켰을 때만 publisher·GripperState 구독·타이머를 만든다. 끄면 아무것도 만들지 않는다(시연·스텁 경로 불변)."""
        if not self._clearance_enabled:
            return
        self._clearance_pub = self.create_publisher(
            ArmClearance, f'{namespace}/arm/clear_of_belt', QOS_HEARTBEAT)
        self._subscribe_gripper_state(namespace)
        rate = float(self.get_parameter('arm_clearance_rate_hz').value)
        self.create_timer(1.0 / max(rate, 0.1), self._publish_clearance, callback_group=self._callbacks)
        self.get_logger().info(
            f'arm_clear_of_belt 켬. region={self._clearance_region!r} lane_frame={self._clearance_lane_frame!r}. '
            'L3 FK↔TCP 대조 전에는 CLEAR 를 배출 허가 근거로 쓰지 않는다(계약 11.6).')

    def _subscribe_gripper_state(self, namespace):
        """`GripperState` 구독은 하나만 만든다(ArmClearance 와 흡착 판정이 같이 쓴다)."""
        if self._gripper_state_subscribed:
            return
        self.create_subscription(GripperState, f'{namespace}/gripper/state',
                                 self._on_gripper_state, QOS_HEARTBEAT,
                                 callback_group=self._callbacks)
        self._gripper_state_subscribed = True

    def _setup_gripper_observation(self, namespace):
        """`gripper_observation: state` 일 때만 GripperCommand 발행·GripperState 구독을 만든다. 기본(bool)은 그대로."""
        if self._gripper_observation != 'state':
            return
        self._gripper_command_pub = self.create_publisher(
            GripperCommand, f'{namespace}/gripper/command_seq', QOS_RELIABLE)
        self._subscribe_gripper_state(namespace)
        self.get_logger().info('gripper_observation=state: 흡착 판정은 GripperState seq 규칙, 명령은 Bool 과 '
                               'command_seq 에 같은 값(계약 11.6). 기존 Bool holding 으로는 판정하지 않는다.')

    def _vector_parameter(self, name, count):
        values = list(self.get_parameter(name).value or [])
        return tuple(float(v) for v in values) if len(values) == count else None

    def _clearance_config_from_parameters(self):
        """파라미터 → LaneConfig. 통로 프레임 자세는 발행할 때 TF 로 채운다. 미설정은 None 으로 둔다."""
        def vector(name, count):
            values = list(self.get_parameter(name).value or [])
            return tuple(float(v) for v in values) if len(values) == count else None

        def length(name):
            value = float(self.get_parameter(name).value)
            return value if value >= 0.0 else None

        return lane.LaneConfig(
            base_from_lane=None,
            lower=vector('arm_clearance_lane_lower', 3), upper=vector('arm_clearance_lane_upper', 3),
            link_radii=vector('arm_clearance_link_radii', 6),
            tool_length=length('arm_clearance_tool_length_m'), tool_radius=length('arm_clearance_tool_radius_m'),
            payload_size=vector('arm_clearance_payload_size', 3),
            payload_center=vector('arm_clearance_payload_center', 3))

    def _lane_pose_quiet(self, stamp):
        """팔 베이스에서 본 통로 프레임(4x4). 없으면 (None, 이유). 10 Hz 라 로그를 남기지 않는다."""
        if not self._clearance_lane_frame:
            return None, 'arm_clearance_lane_frame 미설정'
        try:
            transform = self._tf_buffer.lookup_transform(
                self._arm_base_frame, self._clearance_lane_frame, RclTime.from_msg(stamp),
                timeout=Duration(seconds=0.0))
        except TransformException as error:
            return None, f'TF {self._arm_base_frame} <- {self._clearance_lane_frame} 없음: {error}'
        rotation, translation = transform.transform.rotation, transform.transform.translation
        return kin.matrix_from_quaternion(rotation.x, rotation.y, rotation.z, rotation.w,
                                          (translation.x, translation.y, translation.z)), ''

    def clearance_judgement(self):
        """지금 발행할 (epoch, seq, stamp, Judgement). epoch 를 모르면 None."""
        with self._lock:
            view = clear_state.publish_epoch(self._epoch, self._fence.done_epoch, self._fence.fenced)
            joints, age, stamp = self._joints.get(), self._joints.age(), self._joints_stamp
            if view.epoch is None:
                return None
            holding, holding_reason = self._gripper_view.holding(view.epoch, time.monotonic())
        stamp_s = RclTime.from_msg(stamp).nanoseconds * 1e-9 if stamp is not None else None
        seq = self._clearance_seq.next(stamp_s, view.epoch)
        if view.fenced:
            return view.epoch, seq, stamp, lane.Judgement(lane.UNKNOWN, view.reason, '', None)
        if stamp is None:
            return view.epoch, seq, stamp, lane.Judgement(lane.UNKNOWN, 'joint_states 를 받은 적이 없다', '', None)
        base_from_lane, tf_reason = self._lane_pose_quiet(stamp)
        if base_from_lane is None:
            return view.epoch, seq, stamp, lane.Judgement(lane.UNKNOWN, tf_reason, '', None)
        config = self._clearance_config._replace(base_from_lane=base_from_lane)
        judgement = lane.judge(joints, age, STALE_JOINTS_S, self._limits, config, holding)
        if holding is None and judgement.state == lane.UNKNOWN and judgement.reason.startswith('파지 여부'):
            judgement = judgement._replace(reason=f'{judgement.reason} ({holding_reason})')
        return view.epoch, seq, stamp, judgement

    def _publish_clearance(self):
        """`ArmClearance` 한 번. epoch 를 모르면 내지 않는다. 종료 중이면 내지 않는다."""
        if self._closing.is_set() or self._clearance_pub is None:
            return
        result = self.clearance_judgement()
        if result is None:
            return
        epoch, seq, stamp, judgement = result
        message = ArmClearance()
        if stamp is not None:
            message.header.stamp = stamp
        message.epoch = int(epoch)
        message.seq = int(seq)
        message.clearance = {lane.CLEAR: ArmClearance.CLEARANCE_CLEAR,
                             lane.INTRUDING: ArmClearance.CLEARANCE_INTRUDING}.get(judgement.state,
                                                                                   ArmClearance.CLEARANCE_UNKNOWN)
        message.region = self._clearance_region
        message.margin_m = float(judgement.distance) if judgement.distance is not None else float('nan')
        message.detail = judgement.reason
        self._clearance_pub.publish(message)

    # ---- PickPouch ------------------------------------------------------

    def _accept_pick(self, goal):
        """goal 형식 검사. 인터락은 실행에서 본다(거부하면 outcome 을 못 돌려준다)."""
        if not goal.order_id:
            self.get_logger().warn('PickPouch goal 에 order_id 가 없다. 거부한다.')
            return GoalResponse.REJECT
        if goal.source not in (PickPouch.Goal.SOURCE_BELT, PickPouch.Goal.SOURCE_DECK):
            self.get_logger().warn(f'PickPouch source={goal.source} 를 모른다. 거부한다.')
            return GoalResponse.REJECT
        if goal.source == PickPouch.Goal.SOURCE_BELT and goal.target_slot < 0:
            self.get_logger().warn('source=BELT 는 상판 칸 번호가 있어야 한다. 거부한다.')
            return GoalResponse.REJECT
        if goal.target_slot < 0 and not self.cabinet_frame_for(goal):
            # 어느 보관함인지 알 수 없다. goal 의 `zone_id`(계약 10.1)도, 파라미터 `cabinet_frame` 도 비었다.
            self.get_logger().error(
                '보관함 플레이스인데 놓을 곳을 모른다. 거부한다. '
                'PickPouch goal 의 zone_id 가 비었고 cabinet_frame 파라미터도 비었다 — 둘 중 하나는 있어야 한다.')
            return GoalResponse.REJECT
        if self.goal_active():
            self.get_logger().warn('이미 활성 goal 이 있다. 거부한다.')
            return GoalResponse.REJECT
        if self.fenced():
            self.get_logger().warn('리셋 barrier 중이다. 거부한다.')
            return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    def _accept_cancel(self, goal_handle):
        """리셋 barrier 1단계가 cancel 을 쓴다(계약 6절)."""
        return CancelResponse.ACCEPT

    def _execute_pick(self, goal_handle):
        """`PickPouch` 실행. 결과를 돌려준 뒤에 홈으로 돌아간다(계약 2.3·2.6절)."""
        self.stop_homing()
        self.set_goal_active(True)
        generation = self.generation()
        result = PickPouch.Result()
        try:
            outcome, detail = self._run_pick(goal_handle, generation)
            if outcome == SHUTDOWN or self._closing.is_set():
                # 종료는 리셋이 아니다(#111). 이벤트 없이 abort 한다. 그리퍼는 그대로 둔다.
                self.get_logger().info(f'PickPouch {goal_handle.request.order_id}: 노드 종료(shutdown). '
                                       f'abort 한다. 관절·그리퍼 명령을 더 내지 않는다(쥐고 있으면 쥔 채).')
                result.success = False
                result.outcome = perm.OUTCOME_TIMEOUT
                self._end_goal(goal_handle, 'abort')
                return result
            if outcome is CANCELLED:
                # 계약 2.3절 outcome 목록에 취소 값이 없어 `timeout` 에 실어 보낸다.
                # 결과만 보면 시한 초과와 구분이 안 되므로 취소라는 사실은 로그로 남긴다.
                # 예외 문서(9/22)가 취소 값을 정하면 그 값으로 바꾼다.
                result.success = False
                result.outcome = perm.OUTCOME_TIMEOUT
                self.get_logger().info(
                    f'PickPouch {goal_handle.request.order_id}: 취소됨(cancel). '
                    f'결과 outcome 은 timeout 으로 나간다. detail={detail}')
                self._end_goal(goal_handle, 'canceled')
                return result
            result.success = outcome == perm.OUTCOME_OK
            result.outcome = outcome
            if result.success:
                self._end_goal(goal_handle, 'succeed')
            else:
                self.get_logger().warn(f'PickPouch {goal_handle.request.order_id}: {outcome} ({detail})')
                self._end_goal(goal_handle, 'abort')
            return result
        finally:
            self.set_goal_active(False)
            if (not goal_handle.is_cancel_requested and not self.fence_moved(generation)
                    and not self._closing.is_set()):
                # 성공이든 실패든 홈으로 간다. 취소·리셋 barrier 는 isaac 리셋이 자세를 되돌린다.
                self.start_homing()

    def _publish_feedback(self, goal_handle, phase):
        feedback = PickPouch.Feedback()
        feedback.phase = phase
        goal_handle.publish_feedback(feedback)

    def move_via(self, cancelled=None):
        """경유 자세를 거친다. 안 켰으면 아무것도 안 하고 성공이다."""
        if self._via is None:
            return MoveResult(True)
        return self.move_to(self._via, cancelled)

    def _move_failed(self, goal_handle, deadline, moved, ik_detail):
        """이동 실패를 닫는다. 도달 실패면 그렇게 말하고, 아니면 예전대로 IK 실패로 닫는다.

        `timeout` 을 쓰는 이유: 계약 2.3절의 일곱 개 밖으로 나가지 않으면서 "제 시간에 못 갔다"에
        제일 가깝다. `grasp_failed` 는 **틀린 말**이다(집은 것이 없다). orchestrator 는
        `dropped` 만 즉시 ABORT 하고 나머지는 똑같이 재시도하므로(`trip_fsm._result_*`),
        `timeout` 을 골라도 새로 생기는 동작이 없다.
        """
        outcome = moved.outcome or perm.OUTCOME_GRASP_FAILED
        return self._stopped_outcome(goal_handle, deadline, outcome, moved.detail or ik_detail)

    def _run_pick(self, goal_handle, generation=None):
        """한 번의 픽·플레이스. 반환은 (outcome, detail). outcome 이 None 이면 취소다."""
        goal = goal_handle.request
        deadline = self.sim_now() + self._pick_timeout
        from_belt = goal.source == PickPouch.Goal.SOURCE_BELT
        generation = self.generation() if generation is None else generation
        self._goal_generation = generation
        if self.fence_moved(generation) or self.fenced():
            return perm.OUTCOME_TIMEOUT, '리셋 barrier'

        self._clock_watch = ClockWatch(self.sim_now())

        def stop():
            """취소, 액션 시한(sim) 초과, 시뮬 정지, 리셋 barrier 중 하나면 동작을 멈춘다."""
            return (goal_handle.is_cancel_requested or not rclpy.ok() or self._closing.is_set()
                    or self.fence_moved(generation)
                    or self.sim_now() >= deadline
                    or self._clock_watch.stalled(self.sim_now()))

        allowed, reason = self._interlock(goal, from_belt)
        if not allowed:
            return perm.OUTCOME_REJECTED_INTERLOCK, reason

        place_frame = (self.deck_slot_frame(goal.target_slot)
                       if goal.target_slot >= 0 else self.cabinet_frame_for(goal))
        place_target = self.frame_pose_in_base(place_frame)
        if place_target is None:
            return perm.OUTCOME_NOT_DETECTED, f'놓을 곳 TF 없음: {place_frame}'
        # 한 정거장에 봉투 여럿(병실 묶음 → C 테이블)이면 칸을 프레임 x 로 비켜 겹치지 않게 놓는다(재범 9/25).
        if getattr(self, '_stop_slots', None) is None:      # 시험 하네스는 __init__ 을 건너뛴다
            self._stop_slots = placement.StopSlots()
        slot = self._stop_slots.index_for(place_frame, goal.order_id, goal.target_slot >= 0)
        if slot:
            place_target = np.array(place_target, dtype=float)
            place_target[:3, 3] += place_target[:3, 0] * placement.stop_slot_offset(slot)
            self.get_logger().info(f'정거장 칸 {slot}: {goal.order_id} 를 {place_frame} x '
                                   f'{placement.stop_slot_offset(slot):+.2f} m 에 놓는다')

        # 1. 검출. 여기부터가 파지 시도다(지표: 벨트 끝 픽 시도 → 상판 칸 안착).
        self._publish_feedback(goal_handle, 'detect')
        self.publish_event(Event.PICK_ATTEMPT, order_id=goal.order_id,
                           detail='belt' if from_belt else 'deck')
        plane_z = None
        locked_pick = (from_belt and self._pouch_source == SOURCE_CAMERA
                       and getattr(self, '_belt_pick_lock_wrist', False))
        plan = self._view_plan(goal, from_belt)
        # 참값으로 집는 비전 교차 확인의 관측은 덤이다 — 못 하면 로그만 남기고 참값 경로로 간다(한 바퀴를 깨지 않는다).
        optional = self._pouch_source != SOURCE_CAMERA
        if plan is not None:
            frame, offset, standoff = plan
            target = self.frame_pose_in_base(frame)
            view, reason = None, f'관측 프레임 TF 없음: {frame}'
            if target is not None:
                target = np.array(target, dtype=float)
                target[:3, 3] += target[:3, 0] * offset
                # 봉투 윗면. 관측 자세에서는 검출을 이 평면과 광선의 교차로 놓는다(검출기의 고정 거리를 쓰지 않는다).
                plane_z = float(target[2, 3]) + self._pouch_height
                view, reason = self._camera_view_pose(target, standoff)
                reason = f'관측 자세 없음: {reason}'
            if view is None:
                if not optional:
                    return perm.OUTCOME_NOT_DETECTED, reason
                self.get_logger().warn(f'비전 확인 관측 없이 간다 {goal.order_id}: {reason}')
            else:
                self._publish_feedback(goal_handle, 'view')
                self.get_logger().info(
                    f'관측 {goal.order_id}: {frame} + x {offset:.3f} → 목표 {_xyz(target)}, 거리 {standoff:.2f} m')
                moved = self.move_to_pose(view, stop, tool=True)
                if not moved and (not optional or stop()):
                    return self._move_failed(goal_handle, deadline, moved, '관측 자세 IK 실패')
                if not moved:
                    self.get_logger().warn(f'비전 확인 관측 자세 IK 실패 {goal.order_id} — 참값 경로로 간다')
            if self._refine_standoff > 0.0 and self._pouch_source == SOURCE_CAMERA and not locked_pick:
                refined, reason = self._refine_view_pose(target, plane_z, stop, deadline, goal.order_id)
                if refined is None:
                    self.get_logger().info(f'재관측 없이 간다: {reason}')
                else:
                    self.get_logger().info(f'재관측 {goal.order_id}: {reason}')
                    self._publish_feedback(goal_handle, 'refine')
                    moved = self.move_to_pose(refined, stop, tool=True)
                    if not moved:
                        return self._move_failed(goal_handle, deadline, moved, '재관측 자세 IK 실패')
        grasp_pose, outcome, detail = self._wait_for_pouch(goal, goal_handle, stop, deadline, plane_z)
        if outcome != perm.OUTCOME_OK:
            return outcome, detail
        pick_move = self.move_to_pose
        if locked_pick:
            joints = self.joint_positions()
            if joints is None:
                return perm.OUTCOME_TIMEOUT, '손목 고정 기준 관절값 없음'
            wrist = float(joints[-1])
            if plane_z is None:
                return perm.OUTCOME_NOT_DETECTED, '탁자 기준 파지 평면 없음'
            # belt_end TF 는 실제 탁자 상판. plane_z 는 상판 + 봉투 두께다.
            # 접촉 흡착이므로 기존 5 mm 공중 오프셋을 더하지 않는다.
            contact_drop = getattr(self, '_belt_pick_contact_drop', 0.0)
            grasp_pose[2, 3] = plane_z - contact_drop

            def pick_move(pose, stopped):
                return self.move_suction_locked(pose, wrist, stopped)
            self.get_logger().info(f'탁자 파지: 평면 z={plane_z}, TCP {_xyz(grasp_pose)}, '
                                   f'추가 하강 {contact_drop:.3f} m, J6 고정 {wrist:+.4f}; QR 방향 재관측 생략')
        deck_vision = self._deck_vision(goal)
        if deck_vision:
            # 관측 자세(칸 위 `deck_view_standoff_m`)에서 본다. 접근 자세(봉투 위 `approach_height_m`)는 너무 가까워
            # QR 이 화면을 벗어났다(campaign1 a01·회차108: 0/13·0/9, 저장 프레임에 봉투 없음).
            grasp_pose = self._vision_grasp(goal.order_id, grasp_pose, stop)

        # 2. 접근 → 파지. 접근은 위에서 내려온다(계약 3절).
        pre_grasp = kin.translate(grasp_pose, (0.0, 0.0, self._approach_height))
        self._publish_feedback(goal_handle, 'approach')
        self.set_gripper(False)
        if from_belt and self._pouch_source == SOURCE_CAMERA:
            # 카메라 관측 직후 고정 경유 자세로 접으면 IK 기준 자세도 바뀐다.
            # 현 관측 관절값을 유지한 채 봉투 위 접근점의 IK 를 푼다.
            self.get_logger().info(f'직접 접근 {goal.order_id}: 카메라 관측 → 봉투 위, 고정 경유 생략')
        else:
            moved = self.move_via(stop)
            if not moved:
                return self._move_failed(goal_handle, deadline, moved, '경유 자세 IK 실패')
        moved = pick_move(pre_grasp, stop)
        if not moved:
            return self._move_failed(goal_handle, deadline, moved, '접근 자세 IK 실패')
        self._publish_feedback(goal_handle, 'grasp')
        moved = pick_move(grasp_pose, stop)
        if not moved:
            return self._move_failed(goal_handle, deadline, moved, '파지 자세 IK 실패')
        self.set_gripper(True)
        held, outcome, detail = self._wait_for_hold(goal_handle, stop, deadline)
        if not held:
            # 못 잡았으면 흡착 명령을 되돌린다. 안 그러면 켠 채 남아 스테이지가 계속 시도한다
            # (실습27b·29b 에서 실패 뒤 `suction miss` 가 60 s·1,666줄 찍혔다).
            # **잡은 뒤의 실패 경로에서는 놓지 않는다** — 들고 있는 봉투를 그 자리에 떨어뜨리는
            # 것보다 들고 복귀하는 편이 낫다. 여기는 "잡은 것이 없다" 가 확인된 자리다.
            self.set_gripper(False)
            return outcome, detail
        self.publish_event(Event.POUCH_PICKED, order_id=goal.order_id)

        # 3. 들어 올리기 → 놓을 곳으로.
        self._publish_feedback(goal_handle, 'transfer')
        moved = pick_move(pre_grasp, stop)
        if not moved:
            return self._move_failed(goal_handle, deadline, moved, '들어 올리기 IK 실패')
        if self.dropped():
            return perm.OUTCOME_DROPPED, '들어 올리는 중 holding false'
        lost, reason = self.feedback_lost()
        if lost:
            return perm.OUTCOME_TIMEOUT, f'들어 올리는 중 흡착 관측 소실: {reason}'

        place = kin.top_down_pose(place_target[:3, 3] + np.array([0.0, 0.0, self._place_z_offset]),
                                  kin.yaw_of(place_target))
        pre_place = kin.translate(place, (0.0, 0.0, self._approach_height))
        moved = self.move_via(stop)
        if not moved:
            return self._move_failed(goal_handle, deadline, moved, '경유 자세 IK 실패(플레이스 전)')
        moved = self.move_to_pose(pre_place, stop)
        if not moved:
            return self._move_failed(goal_handle, deadline, moved, '플레이스 접근 IK 실패')
        if self.dropped():
            return perm.OUTCOME_DROPPED, '이송 중 holding false'
        lost, reason = self.feedback_lost()
        if lost:
            return perm.OUTCOME_TIMEOUT, f'이송 중 흡착 관측 소실: {reason}'

        # 4. 놓기.
        self._publish_feedback(goal_handle, 'place')
        moved = self.move_to_pose(place, stop)
        if not moved:
            return self._move_failed(goal_handle, deadline, moved, '플레이스 자세 IK 실패')
        if self.dropped():
            return perm.OUTCOME_DROPPED, '놓기 직전 holding false'
        lost, reason = self.feedback_lost()
        if lost:
            return perm.OUTCOME_TIMEOUT, f'놓기 직전 흡착 관측 소실: {reason}'
        released_at = self.sim_now()
        self.set_gripper(False)
        if not self.wait(self._release_settle, stop):
            return self._stopped_outcome(goal_handle, deadline, perm.OUTCOME_OK, '놓기 대기 중단')
        if self._gripper_command_pub is not None:
            released, outcome, detail = self._wait_for_release(goal_handle, stop, deadline)
            if not released:
                return outcome, detail
        if self._placement_enabled:
            # 안착 미확인은 기존 outcome 중 재시도를 부르지 않는 `dropped` 로 닫는다(trip_fsm: 즉시 ABORT).
            # 봉투는 이미 그리퍼를 떠났다. detail 은 기록용이다(판정에 쓰지 않는다). 결정 16번 전의 임시 매핑이다.
            confirmed, detail = self._confirm_placement(goal, stop, place_frame, place_target, released_at)
            if not confirmed:
                if stop():
                    return self._stopped_outcome(goal_handle, deadline, perm.OUTCOME_DROPPED,
                                                 f'placement_unconfirmed: {detail}')
                return perm.OUTCOME_DROPPED, f'placement_unconfirmed: {detail}'
        self.publish_event(Event.POUCH_LOADED if goal.target_slot >= 0 else Event.POUCH_PLACED,
                           order_id=goal.order_id, detail=place_frame)

        # 5. 후퇴. 홈 복귀는 결과를 돌려준 뒤에 한다(`_execute_pick` 의 `start_homing`).
        # 봉투는 이미 칸에 있다. 여기서부터 실패해도 픽 자체는 ok 이고,
        # 팔이 홈에 없다는 사실은 `arm/at_home` 이 false 로 말한다.
        if not self.move_to_pose(pre_place, stop):
            self.get_logger().warn('후퇴 IK 실패. 놓기는 끝났다. 그대로 홈으로 간다.')
        return perm.OUTCOME_OK, place_frame

    def _placement_config_problem(self):
        """안착 확인에 필요한 설정 중 없는 것. 없으면 ''."""
        if not self._placement_standoff > 0.0:
            return 'placement_view_standoff_m 미설정'
        if not self._placement_timeout > 0.0:
            return 'placement_timeout_s 미설정'
        if not self._tool_frame:
            return 'tool_frame 미설정(손 카메라 → 공구 변환이 필요하다)'
        return ''

    def _deck_vision(self, goal):
        """참값으로 집되 상판 칸 픽에서 손 카메라 검출을 교차 확인하는가(`vision_check`, 재범 9/25)."""
        return bool(getattr(self, '_vision_check', False) and getattr(self, '_vision_topic', '')
                    and goal.source == PickPouch.Goal.SOURCE_DECK)

    def _view_plan(self, goal, from_belt):
        """이 픽의 관측 자세 (프레임, x 오프셋, 거리). 안 쓰면 None.

        카메라 검출일 때 쓴다. 참값 센서여도 상판 비전 교차 확인(`_deck_vision`)이면 상판 관측 자세를 쓴다 —
        확인할 카메라가 봉투를 봐야 한다.
        """
        if self._pouch_source != SOURCE_CAMERA and (from_belt or not self._deck_vision(goal)):
            return None                     # 시뮬 센서는 팔 자세와 무관하다
        if from_belt:
            if self._belt_view_standoff > 0.0:
                return self._belt_view_frame, self._belt_view_offset, self._belt_view_standoff
            return None
        if self._deck_view_standoff > 0.0 and not self._deck_pick_from_frame:
            return self.deck_slot_frame(self._source_slot(goal)), 0.0, self._deck_view_standoff
        return None

    def _camera_view_pose(self, target, standoff):
        """`target`(팔 베이스 4x4, +z 위)을 +z `standoff` 에서 손 카메라로 내려다보는 **공구** 자세.

        충돌 검증은 없다.
        """
        if not self._tool_frame:
            return None, 'tool_frame 미설정(손 카메라 → 공구 변환이 필요하다)'
        tool_from_camera = self.lookup_pose(self._tool_frame, self._hand_camera_frame)
        if tool_from_camera is None:
            return None, f'TF {self._tool_frame} <- {self._hand_camera_frame} 없음'
        camera_pose = kin.facing_pose(target, standoff)
        return camera_pose @ kin.invert(tool_from_camera), ''

    def _refine_view_pose(self, target, plane_z, stop, deadline, order_id=''):
        """첫 관측의 검출로 봉투 바로 위·봉투 방향의 재관측 자세를 만든다. (자세, 고른 근거) 또는 (None, 이유).

        이 주문의 QR 을 읽은 검출이 있으면 그것을 쓴다. 없으면 QR 을 못 읽은 검출(order_id 빈 값) 중
        관측점에 가장 가까운 것 — 여기서는 자리만 잡는다. 다른 주문의 QR 을 읽은 검출은 쓰지 않는다.
        """
        arrived = self.sim_now()
        limit = min(deadline, arrived + self._detection_timeout)
        while True:
            message = self.latest_pouches(arrived)
            if message is not None and message.detections:
                best = None
                for detection in message.detections:
                    if detection.order_id and order_id and detection.order_id != order_id:
                        continue
                    pose, _detail = self._pouch_pose_in_base(message, detection, plane_z)
                    if pose is None:
                        continue
                    gap = float(np.hypot(*(pose[:2, 3] - target[:2, 3])))
                    key = (not detection.order_id, gap)      # QR 을 읽은 것 먼저, 그다음 가까운 것
                    if best is None or key < best[0]:
                        best = (key, pose, detection.order_id)
                if best is not None:
                    (_unread, gap), pose, read = best
                    # 봉투 방향: QR 을 읽었으면 그 네 점의 각, 아니면 관측 프레임의 각을 쓴다.
                    yaw = kin.yaw_of(pose) if read else kin.yaw_of(target)
                    spot = np.eye(4)
                    spot[:3, :3] = kin.rotation_z(yaw)
                    spot[:3, 3] = (pose[0, 3], pose[1, 3], plane_z)
                    view, reason = self._camera_view_pose(spot, self._refine_standoff)
                    if view is None:
                        return None, reason
                    return view, (f'검출 {len(message.detections)}건 중 {read or "QR 미판독"} '
                                  f'자리 {_xyz(spot)}, 관측점과 {gap:.3f} m')
            if stop() or self.sim_now() >= limit:
                return None, '첫 관측에서 자리를 잡을 검출이 없다'
            self.wait(0.05, stop)

    def _placement_view_pose(self, place_target):
        """놓을 곳 프레임을 손 카메라로 내려다보는 손끝 자세. 못 만들면 (None, 이유). 충돌 검증은 없다."""
        tool_from_camera = self.lookup_pose(self._tool_frame, self._hand_camera_frame)
        if tool_from_camera is None:
            return None, f'TF {self._tool_frame} <- {self._hand_camera_frame} 없음'
        camera_pose = kin.facing_pose(place_target, self._placement_standoff)
        return camera_pose @ kin.invert(tool_from_camera), ''

    def _confirm_placement(self, goal, stop, place_frame, place_target, released_at):
        """해제 뒤 놓을 곳을 다시 보고 안착을 확인한다(계약 11.4 제안, A1 최소안). 반환은 (확인했나, 이유).

        관측 자세로 가서, 해제 명령 뒤 stamp 이고 QR 이 goal 주문이며 위치(이미지 stamp 의 TF 로 놓을 곳 프레임에
        옮김)가 칸 상자 안인 검출을 `placement_timeout_s`(sim) 동안 기다린다.
        평가용 `/evaluator/cabinet` 은 쓰지 않는다.
        """
        problem = self._placement_config_problem()
        box = self._placement_slot_box if goal.target_slot >= 0 else self._placement_cabinet_box
        problem = problem or placement.box_problem(box)
        if problem:
            return False, problem
        view, reason = self._placement_view_pose(place_target)
        if view is None:
            return False, reason
        if not self.move_to_pose(view, stop, tool=True):
            return False, '관측 자세로 못 갔다(IK 실패 또는 중단)'
        limit = self.sim_now() + self._placement_timeout
        reason = '검출 없음'
        while True:
            message = self.latest_pouches(released_at)
            if message is not None:
                confirmed, reason = placement.placement_confirmed(
                    self._placement_candidates(message, goal.order_id, place_frame), goal.order_id, released_at, box)
                if confirmed:
                    return True, ''
            if stop() or self.sim_now() >= limit:
                return False, reason
            self.wait(0.05, stop)

    def _placement_candidates(self, message, order_id, place_frame):
        """검출 → Candidate(주문, stamp, 놓을 곳 프레임의 점). 이 주문의 검출만 TF 로 옮긴다."""
        stamp = RclTime.from_msg(message.header.stamp)
        stamp_s = stamp.nanoseconds * 1e-9
        candidates = []
        frame_from_base = None
        for detection in message.detections:
            point = None
            if detection.order_id == order_id:
                pose, _detail = self._pouch_pose_in_base(message, detection)
                if pose is not None:
                    if frame_from_base is None:
                        base_from_frame = self.frame_pose_in_base(place_frame, stamp)
                        frame_from_base = kin.invert(base_from_frame) if base_from_frame is not None else False
                    if frame_from_base is not False:
                        point = tuple((frame_from_base @ pose)[:3, 3])
            candidates.append(placement.Candidate(detection.order_id, stamp_s, point))
        return candidates

    def _interlock(self, goal, from_belt):
        """계약 5절 팔 동작 guard. unknown 은 허가가 아니다."""
        base_stopped = self.base_stopped()
        if not from_belt:
            return perm.deck_pick_allowed(base_stopped), f'base/stopped={base_stopped}'
        belt = self.belt_state()
        at_end = belt.at_end if belt is not None else None
        belt_order = belt.order_id if belt is not None else ''
        allowed = perm.belt_pick_allowed(base_stopped, at_end, belt_order, goal.order_id)
        return allowed, (f'base/stopped={base_stopped} belt.at_end={at_end} '
                         f'belt.order_id={belt_order!r} goal={goal.order_id!r}')

    def _deck_grasp_from_frame(self, goal):
        """칸 TF 로 만든 파지 자세. 못 만들면 (None, outcome, detail).

        봉투가 칸 바닥 윗면(= `deck_slot_*` 원점)에 얹혀 있으므로 흡착면 목표는 **원점 + 봉투 두께**다.
        놓을 때 쓰는 `place_z_offset_m`(= rest_gap + 봉투 두께)과 같은 기하를 되쓴다 — 두 경로가 맞는다.
        검출을 쓰지 않으므로 **봉투가 실제로 거기 있는지는 확인하지 않는다.** 그래서 opt-in 이고,
        검출이 생기면(YOLO·봉투 QR) 끈다.
        """
        frame = self.deck_slot_frame(self._source_slot(goal))
        pose = self.frame_pose_in_base(frame)
        if pose is None:
            return None, perm.OUTCOME_NOT_DETECTED, f'집을 칸 TF 없음: {frame}'
        grasp = kin.top_down_pose(pose[:3, 3] + np.array([0.0, 0.0, self._pouch_height]),
                                  kin.yaw_of(pose))
        return grasp, perm.OUTCOME_OK, f'칸 TF {frame} + 봉투 두께 {self._pouch_height:.3f} m'

    def _wait_for_pouch(self, goal, goal_handle, stop, deadline, plane_z=None):
        """검출을 기다려 파지 자세를 만든다. 반환은 (4x4 또는 None, outcome, detail).

        `deck_pick_from_frame` 이 켜져 있고 상판 칸에서 집는 것이면 검출을 기다리지 않고 칸 TF 를 쓴다.
        """
        if self._deck_pick_from_frame and goal.source == PickPouch.Goal.SOURCE_DECK:
            return self._deck_grasp_from_frame(goal)
        requested_at = self.sim_now()
        limit = min(deadline, requested_at + self._detection_timeout)
        outcome, detail = perm.OUTCOME_NOT_DETECTED, '검출 메시지 없음'
        while True:
            message = self.latest_pouches(requested_at - self._detection_max_age)
            if message is not None:
                index, outcome = perm.select_detection(
                    [detection.order_id for detection in message.detections], goal.order_id)
                if index is not None:
                    pose, detail = self._pouch_pose_in_base(message, message.detections[index], plane_z)
                    if pose is not None:
                        grasp = kin.top_down_pose(
                            pose[:3, 3] + np.array([0.0, 0.0, self._grasp_z_offset]),
                            kin.yaw_of(pose))
                        return grasp, perm.OUTCOME_OK, detail
                    outcome = perm.OUTCOME_NOT_DETECTED
                else:
                    detail = f'검출 {len(message.detections)}건, 맞는 QR 없음'
            if stop():
                stopped, stopped_detail = self._stopped_outcome(goal_handle, deadline,
                                                                outcome, detail)
                return None, stopped, stopped_detail
            if self.sim_now() >= limit:
                return None, outcome, detail
            self.wait(0.05, stop)

    def _vision_grasp(self, order_id, truth, stop):
        """접근 자세에서 손 카메라 검출로 파지 자리를 정한다. 반환은 쓸 파지 자세(검출 또는 참값).

        이 주문의 QR 을 읽은 검출을 봉투 윗면 평면(참값 파지 높이 − `grasp_z_offset_m`)에 투영한다. 참값과
        `vision_check_tolerance_m` 안이면 검출의 (x, y) 로 바꾸고(높이·방향은 참값), 아니면 참값을 그대로 쓴다.
        시도마다 한 줄: 결과·지연(ms, sim)·참값과의 차·판독률(이 주문 QR 을 읽은 프레임 / 받은 프레임).
        """
        truth = np.asarray(truth, dtype=float)
        plane_z = float(truth[2, 3]) - self._grasp_z_offset
        arrived = self.sim_now()
        since = arrived - getattr(self, '_vision_lookback', 0.0)
        seen, read = set(), 0
        result, gap, chosen = 'vision_mismatch', None, truth
        while True:
            with self._lock:
                history = list(getattr(self, '_vision_history', []))
                if self._vision_pouches is not None and (not history or history[-1] is not self._vision_pouches):
                    history.append(self._vision_pouches)
            found = False
            for message in reversed(history):                  # 새 것부터
                stamp = RclTime.from_msg(message.header.stamp).nanoseconds * 1e-9
                if stamp >= since and stamp not in seen:
                    seen.add(stamp)
                    detection = next((d for d in message.detections if d.order_id == order_id), None)
                    if detection is not None:
                        read += 1
                        pose, _detail = self._pouch_pose_in_base(message, detection, plane_z)
                        if pose is not None:
                            gap = float(np.hypot(*(pose[:2, 3] - truth[:2, 3])))
                            if gap <= self._vision_tolerance:
                                result = 'ok'
                                chosen = truth.copy()
                                chosen[:2, 3] = pose[:2, 3]
                            found = True
                            break
            if found:
                break
            # 시한 안에 이 주문 검출이 없으면 `vision_mismatch` 그대로 참값으로 간다
            if stop() or self.sim_now() >= arrived + self._vision_timeout:
                break
            self.wait(0.05, stop)
        latency_ms = (self.sim_now() - arrived) * 1000.0
        self.get_logger().info(
            f'vision pouch {order_id}: {result} 지연 {latency_ms:.0f} ms, 참값과 차 '
            f'{"-" if gap is None else f"{gap:.3f} m"}, 판독 {read}/{len(seen)} 프레임, '
            f'자리 {"검출" if chosen is not truth else "참값"}')
        return chosen

    def _pouch_pose_in_base(self, message, detection, plane_z=None):
        """검출 자세(optical frame) → 팔 베이스 프레임 4x4. 변환은 header.stamp 의 TF 로 한다.

        `plane_z`(팔 베이스 기준 봉투 윗면 높이)를 주면 위치는 카메라 광선과 그 수평면의 교차다.
        검출기의 깊이(고정 거리·폭 추정)는 광선 방향을 정하는 데만 쓴다.
        """
        position = detection.pose.position
        if abs(position.x) + abs(position.y) + abs(position.z) < 1e-6:
            return None, '검출기가 거리를 못 정했다(pose 가 0). 카메라 거리·봉투 크기 파라미터 확인'
        base_from_optical = self.frame_pose_in_base(
            message.header.frame_id, RclTime.from_msg(message.header.stamp))
        if base_from_optical is None:
            return None, f'TF 없음: {message.header.frame_id}'
        orientation = detection.pose.orientation
        try:
            in_optical = kin.matrix_from_quaternion(
                orientation.x, orientation.y, orientation.z, orientation.w,
                (position.x, position.y, position.z))
        except ValueError:  # 자세를 안 낸 검출. 위치만 쓴다.
            in_optical = np.eye(4)
            in_optical[:3, 3] = (position.x, position.y, position.z)
        pose = base_from_optical @ in_optical
        if plane_z is None:
            return pose, ''
        origin = base_from_optical[:3, 3]
        ray = pose[:3, 3] - origin
        if ray[2] >= -1e-6:
            return None, '광선이 봉투 평면으로 내려가지 않는다(관측 자세 확인)'
        pose[:3, 3] = origin + ray * ((plane_z - origin[2]) / ray[2])
        return pose, ''

    def _wait_for_hold(self, goal_handle, stop, deadline):
        """흡착을 기다린다. 반환은 (잡았나, outcome, detail)."""
        if self._gripper_command_pub is not None:
            return self._wait_for_command(goal_handle, stop, deadline, close=True)
        self.wait(self._grasp_settle, stop)
        # `holding=false` 는 "못 붙였다" 가 아니라 **"아직 안 붙었다"** 일 수 있다.
        # lap13: 팔이 430.133 에 흡착을 켰는데 스테이지는 0.55 s 뒤(430.683)에야 붙였고,
        # 그 사이 `grasp_settle` 0.5 s 가 먼저 끝나 false 한 번을 보고 닫았다 — **0.05 s 모자랐다.**
        # 도달 확인이 통과해도 공차 0.05 rad 안에서 공구가 흡착 거리 밖일 수 있어 지연은 정상이다.
        # 그래서 첫 false 로 닫지 않고 이 시간까지 기다린다. 시한(`deadline`)은 그대로 위를 덮는다.
        hold_limit = self.sim_now() + self._grasp_hold_timeout
        while True:
            holding = self.gripper_holding()
            if holding is True:
                return True, perm.OUTCOME_OK, ''
            if holding is False and self.sim_now() >= hold_limit:
                return False, perm.OUTCOME_GRASP_FAILED, (
                    f'holding=false ({self._grasp_hold_timeout:.1f}s 기다렸다)')
            if stop():
                # unknown 으로 기다리다 시한을 넘기면 timeout 이다(계약 5절).
                stopped, detail = self._stopped_outcome(goal_handle, deadline,
                                                        perm.OUTCOME_GRASP_FAILED,
                                                        f'holding={holding}')
                return False, stopped, detail
            self.wait(0.05, stop)

    def _wait_for_release(self, goal_handle, stop, deadline):
        """state 모드: 해제 확인(RELEASED ∧ last_applied ≥ 열기 seq)을 기다린다. 반환은 (놓았나, outcome, detail)."""
        return self._wait_for_command(goal_handle, stop, deadline, close=False)

    def _wait_for_command(self, goal_handle, stop, deadline, close):
        """state 모드: 마지막 흡착 명령의 결과를 기다린다(계약 11.6).

        CONFIRMED → 성공. 닫기인데 CONTRADICTED(RELEASED) → `grasp_failed`. 열기인데 CONTRADICTED(HELD) → 해제 실패.
        PENDING·UNKNOWN 은 기다리고, 시한·취소·리셋에서 멈추면 그 이유로 닫는다. 관측 소실은 `timeout` + detail 이다
        (계약 outcome 에 관측 소실 값이 아직 없다). 명령 전의 HELD 는 PENDING 이라 파지로 인정하지 않는다.
        """
        what = '흡착' if close else '해제'
        while True:
            result, reason = self.gripper_command_result()
            if result == clear_state.CONFIRMED:
                return True, perm.OUTCOME_OK, ''
            if result == clear_state.CONTRADICTED:
                if close:
                    return False, perm.OUTCOME_GRASP_FAILED, f'GripperState {reason}'
                return False, perm.OUTCOME_TIMEOUT, f'해제 실패: 열기 적용 뒤 GripperState {reason}'
            if stop():
                return (False, *self._stopped_outcome(goal_handle, deadline, perm.OUTCOME_TIMEOUT,
                                                      f'{what} 관측 소실: {reason}'))
            self.wait(0.05, stop)

    def _stopped_outcome(self, goal_handle, deadline, otherwise, detail):
        """동작이 중간에 멈춘 이유를 outcome 으로. 종료·취소·시한·시뮬 정지·낙하를 먼저 본다."""
        if self._closing.is_set():
            return SHUTDOWN, 'shutdown'
        if goal_handle.is_cancel_requested or not rclpy.ok():
            return CANCELLED, 'cancelled'
        if self.fence_moved(self._goal_generation):
            return perm.OUTCOME_TIMEOUT, f'리셋 barrier: {detail}'
        if self.sim_now() >= deadline:
            return perm.OUTCOME_TIMEOUT, detail
        if self._clock_watch.stalled(self.sim_now()):
            return perm.OUTCOME_TIMEOUT, f'/clock 이 멈췄다: {detail}'
        if self.dropped():
            return perm.OUTCOME_DROPPED, detail
        return otherwise, detail


    # ---- ScanTag -------------------------------------------------------

    def _accept_scan(self, goal):
        """goal 형식 검사. 인터락은 실행에서 본다(`PickPouch` 와 같다)."""
        if not goal.zone_id:
            self.get_logger().warn('ScanTag goal 에 zone_id 가 없다. 거부한다.')
            return GoalResponse.REJECT
        if self.goal_active():
            self.get_logger().warn('이미 활성 goal 이 있다. 거부한다.')
            return GoalResponse.REJECT
        if self.fenced():
            self.get_logger().warn('리셋 barrier 중이다. 거부한다.')
            return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    def _execute_scan(self, goal_handle):
        """`ScanTag` 실행. 스캔 다음은 상판 픽이라 **홈으로 가지 않는다**(계약 2.6절).

        인터락 위반은 abort + `STATUS_UNREADABLE`, 시한 안에 못 읽은 것은 succeed +
        `STATUS_UNREADABLE` 이다. 결과에 outcome 이 없어서 이 둘을 status 로는 못 가르고,
        스텁 팔(`rokey_p3_bringup/stubs/stub_arm.py`)도 같은 규칙이라 그쪽에 맞춘다.
        """
        self.stop_homing()
        self.set_goal_active(True)
        generation = self.generation()
        result = ScanTag.Result()
        result.tag_id = ''
        result.status = TagRead.STATUS_UNREADABLE
        try:
            if not perm.arm_motion_allowed(self.base_stopped()):
                self.get_logger().warn(
                    f'스캔 인터락: base/stopped={self.base_stopped()} 가 true 가 아니다.')
                self._end_goal(goal_handle, 'abort')
                return result
            tag_id, status = self.run_scan_tag(
                goal_handle.request.kind, goal_handle.request.zone_id,
                cancelled=lambda: (goal_handle.is_cancel_requested or self.fence_moved(generation)
                                   or self._closing.is_set()))
            result.tag_id = tag_id
            result.status = status
            if self._closing.is_set():
                self.get_logger().info(f'ScanTag {goal_handle.request.zone_id}: 노드 종료(shutdown). abort 한다.')
                self._end_goal(goal_handle, 'abort')
            elif goal_handle.is_cancel_requested:
                self._end_goal(goal_handle, 'canceled')
            else:
                self._end_goal(goal_handle, 'succeed')
            return result
        finally:
            self.set_goal_active(False)

    def run_scan_tag(self, kind, zone_id, timeout_s=None, cancelled=None):
        """태그 하나를 읽는다. `scan_tag_source` 에 따라 길이 둘이다.

        - `camera`(기본): 손 카메라를 `<zone>/tag` 에 대고 읽는다. 지금 동작이다.
        - `sim`: **팔을 움직이지 않고** 스테이지 시뮬 센서를 기다린다. 스테이지가 AMR 의 위치·yaw 로
          판정해 그 침상의 태그를 내므로, 다른 침상에 서 있으면 다른 태그가 와 orchestrator 가
          `AUTH_FAIL` 로 닫는다(판정은 팔이 아니라 orchestrator 다 — 팔이 거르면 음성 사례가 묻힌다).

        base/stopped 인터락은 둘 다 본다. `sim` 에서도 "그 자리에 서 있어야" 인증이다.

        반환은 `(tag_id, status)`. status 는 `TagRead.STATUS_OK` 또는 `STATUS_UNREADABLE`
        (계약 10절 v1.1 의 `ScanTag` result 가 `TagRead` 상수를 쓴다).

        `PickPouch` 와 달리 끝나고 홈으로 가지 않는다. 계약 2.6절 이벤트 순서에서
        `AUTH_OK` 와 `POUCH_DETECTED` 사이에 `ARM_HOME` 이 없다. 스캔 다음은 상판 픽이다.

        읽은 ID 를 요청 데이터와 대조하는 것은 orchestrator 다(계약 2.3절).
        """
        deadline = self.sim_now() + (timeout_s if timeout_s is not None else self._scan_timeout)
        self._clock_watch = ClockWatch(self.sim_now())

        def stop():
            return ((cancelled is not None and cancelled()) or not rclpy.ok() or self._closing.is_set()
                    or self.sim_now() >= deadline
                    or self._clock_watch.stalled(self.sim_now()))

        if not perm.arm_motion_allowed(self.base_stopped()):
            self.get_logger().warn('ScanTag 인터락: base/stopped 가 true 가 아니다.')
            return '', TagRead.STATUS_UNREADABLE

        requested_at = self.sim_now()
        if self._scan_tag_source == SOURCE_CAMERA:
            # 손 카메라로 읽는다: 태그를 마주보는 자세로 가서 기다린다.
            view_pose = self.tag_view_pose(zone_id)
            if view_pose is None:
                return '', TagRead.STATUS_UNREADABLE
            requested_at = self.sim_now()
            if not self.move_to_pose(view_pose, stop, tool=True):
                self.get_logger().warn(f'{zone_id}/tag 를 보는 자세로 못 갔다.')
                return '', TagRead.STATUS_UNREADABLE
        # `sim` 은 **팔을 움직이지 않는다.** 스테이지가 AMR 위치·yaw 로 판정해 내는 값을 기다릴 뿐이다.
        # 그래서 `tag_standoff_m`·`tool_frame` 이 필요 없고, flange≠tool0 회전 문제도 지나간다.

        # L3 판정선: 시한을 넘겼을 때 **왜** 인지가 로그에 있어야 한다. lap8 에서 ⑦ 이 60 s 뒤
        # `AUTH_FAIL` 로 닫혔는데 팔에 줄이 하나도 없어, "안 왔다" 와 "왔는데 안 맞았다" 가
        # 갈리지 않았다. 봉투 쪽에는 이 줄을 넣어 두고 태그 쪽을 빠뜨렸다.
        self.get_logger().info(
            f'ScanTag 시작. zone={zone_id} kind={kind} source={self._scan_tag_source} '
            f'topic={self._tag_topic} 시한={deadline - requested_at:.1f}s')
        last = None
        while not stop():
            message = self.latest_tag_read(requested_at - self._detection_max_age)
            if message is not None:
                last = message
                if (message.kind == kind and message.status == TagRead.STATUS_OK
                        and message.tag_id):
                    self.get_logger().info(f'ScanTag 읽음. zone={zone_id} tag_id={message.tag_id}')
                    return message.tag_id, TagRead.STATUS_OK
            self.wait(0.05, stop)
        if last is None:
            detail = f'{self._tag_topic} 에 판독이 하나도 안 왔다(또는 전부 낡았다)'
        else:
            detail = (f'마지막 판독 kind={last.kind}(기대 {kind}) '
                      f'status={last.status} tag_id={last.tag_id!r}')
        self.get_logger().warn(f'ScanTag 시한 초과. zone={zone_id}: {detail}')
        return '', TagRead.STATUS_UNREADABLE

    def tag_view_pose(self, zone_id):
        """`<zone>/tag` 를 손 카메라로 마주보는 손끝 자세. 못 만들면 None.

        카메라 자세를 손끝 자세로 옮기려면 공구 프레임과 손 카메라 프레임 사이의 TF 가
        필요하다. 두 프레임 이름과 판독 거리는 **마스터에서 확인**하고 파라미터로 넣는다.
        """
        if self._tag_standoff <= 0.0 or not self._tool_frame:
            self.get_logger().error(
                'tag_standoff_m 또는 tool_frame 이 비어 있다. QR 판독 거리와 공구 프레임 '
                '이름은 마스터에서 확인해 파라미터로 넣는다. ScanTag 는 UNREADABLE 로 닫는다.')
            return None
        tag = self.frame_pose_in_base(f'{zone_id}/tag')
        if tag is None:
            return None
        tool_from_camera = self.lookup_pose(self._tool_frame, self._hand_camera_frame)
        if tool_from_camera is None:
            return None
        camera_pose = kin.facing_pose(tag, self._tag_standoff)
        return camera_pose @ kin.invert(tool_from_camera)

    def _end_goal(self, goal_handle, how):
        """goal 을 succeed·abort·canceled 로 닫는다. 종료 중 발행이 실패하면 debug 한 줄로 넘긴다.

        종료 중 = close 가 불렸거나 context 가 내려갔다. SIGINT 에서는 rclpy 신호 처리기가 context 를 먼저 내려
        액션 서버 publisher 가 무효다. 그때 나는 RCLError("feedback publisher is invalid")는 고장이 아니라
        ERROR·traceback 을 남기지 않는다. 종료가 아니면 그대로 올린다.
        상태 전이를 아예 건너뛰지는 않는다. 실행 콜백이 종결 상태 없이 끝나면 rclpy 가 콜백 밖에서 다시
        abort 해서 거기서 예외가 나기 때문이다(정비 변형 시험으로 확인, 9/17).
        """
        try:
            getattr(goal_handle, how)()
        except Exception as error:
            if not (self._closing.is_set() or not rclpy.ok()):
                raise
            self.get_logger().debug(f'종료 중이라 goal {how} 를 보내지 못했다: {error}')

    def close(self):
        """종료 경로. 액션 실행·홈 복귀가 멈추고 관절·그리퍼 명령·이벤트를 더 내지 않는다. 여러 번 불러도 된다."""
        self._closing.set()
        # 이중 SIGINT 로 대기 중 KeyboardInterrupt 가 나도 플래그는 이미 켜져 루프가 곧 멈춘다. traceback 없이 넘긴다.
        with contextlib.suppress(KeyboardInterrupt):
            self.stop_homing()

    def destroy_node(self):
        self.close()
        return super().destroy_node()


def main(args=None):
    """콘솔 진입점. 액션 실행이 상태 수신을 막지 않게 멀티스레드로 돈다."""
    rclpy.init(args=args)
    node = ArmNode()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
