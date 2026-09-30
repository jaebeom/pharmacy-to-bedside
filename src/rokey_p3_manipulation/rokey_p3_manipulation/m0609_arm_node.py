"""M0609 팔 노드. `Refill` 서버, 관절·그리퍼 명령, `arm/at_home`. manipulation 담당(부 재범).

계약 [배송 한 바퀴 v1](../../../docs/architecture/delivery-contract-v1.md) 2.1·2.3·4·6·7절.
토픽 이름은 amr_1 팔과 같은 꼴이고 네임스페이스만 `m0609` 다.

- 내는 것: `/m0609/arm/joint_command` (6개, position), `/m0609/gripper/command`,
  `/m0609/arm/at_home` (5 Hz), `/m0609/arm/plan_cache` (장면 v2, inventory와 같은 latched JSON),
  `/events` (`REFILL_DONE`)
- 받는 것: `/m0609/joint_states`, `/m0609/gripper/holding`, `/events`
- 서버: `/m0609/refill` (`Refill`, 90 s sim)
- 인터락은 없다. M0609 는 조제실 고정이라 베이스가 없다(계약 5절은 amr_1 팔 것).
  활성 goal 도 홈 복귀도 없으면 관절 명령을 내지 않는다.
- 보충이 성공·실패로 끝나면 **홈에 돌아온 뒤에** 결과를 낸다. 결과를 받은 orchestrator 가 다음 goal 을 보낼 때
  팔은 홈이고 at_home 은 true 다(마클2 관측: 결과 뒤 slot_a_approach 에 멈춰 at_home=false). 취소는 결과를
  곧바로 내고 그 뒤 홈으로 간다. orchestrator 의 drain·대체 goal 이 종결을 cancel_wait_s(10 s wall)까지만 기다린다.
- 계약 6절 2 가 M0609 홈·그리퍼·캐니스터를 isaac 리셋 범위에 넣는다. 이 노드는 그와 별개로 취소된 뒤에도,
  `RESET_DONE` 뒤에도 스스로 홈으로 간다. 리셋 중 끊긴 복귀를 되살리고, 취소 뒤 리셋 전까지 홈 밖에
  머물지 않으려고다. 이미 홈이면 명령을 내지 않으므로 isaac 리셋과 겹치지 않는다.
- 결과 `lot_id` 는 지어내지 않는다. 물리에 로트가 없고 로트 데이터는 orchestrator 선반 값이다(계약 2.1절 끝).
  goal 에 lot 이 있으면 그대로, 없으면(지금 `Refill` goal) 빈 값이다.
- `RESET_BEGIN`(새 epoch)부터 같은 epoch 의 `RESET_DONE` 까지 관절·그리퍼 명령을 내지 않는다(계약 6절 0).
  실행 중 goal·홈 복귀·finally 의 복귀가 모두 멈추고 새 goal 은 거부한다. `RESET_DONE` 뒤 새 joint_states 로
  at_home 을 다시 보고, goal 로 홈을 떠났으면 기존대로 스스로 복귀한다.

v0 는 관절 공간 waypoint 티칭이다. 선반 1자리, 슬롯 a·b 의 접근·삽입 자세, 홈 자세를
파라미터로 받는다. 실행 중 FK·IK 솔버는 호출하지 않는다. USD 조인트 이름·관절 한계와
teach 값은 **마스터에서 확인**한다. Isaac `selfdemo` 의 Lula IK 는 별도 실행 경로다.
`open_loop` 이면 joint_states·holding 없이 시퀀스를 낸다(브릿지가 M0609 를 아직 안 낼 때).

`rail_enabled` 면 조제실 스테이지(`sim/standalone/pharmacy_stage.py`)의 2축 레일 위 M0609 다. 레일은
`/m0609/refill` 안에 숨긴다(계약 v1·액션 타입 불변). 레일 토픽 `/m0609/rail/joint_command`(R)·
`/m0609/rail/joint_states`(S), 관절 `rail_x`·`rail_y`(m)는 **계약 v1 밖**이고 스테이지가 제안한 이름이다.
보충 순서는 teach 파일(`rail_teach_file`, 기본 `config/m0609_rail_teach.yaml`)의 단계를 그대로 잇는다.
레일은 팔이 접힌 자세(홈·`rail_safe_phases`)에 있을 때만 움직인다. 끄면(기본) 레일 토픽을 만들지 않고
동작이 이전과 같다.
"""

import contextlib
import json
import math
import os
import threading
import time

import rclpy
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor, SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from rokey_p3_interfaces.action import Refill
from rokey_p3_interfaces.msg import Event, TagRead
from rokey_p3_interfaces.srv import CheckContainer
from sensor_msgs.msg import JointState
from std_msgs.msg import Bool, String

from rokey_p3_manipulation import container_gate as gate
from rokey_p3_manipulation import refill_sequence as seq
from rokey_p3_manipulation.reset_fence import ResetFence
from rokey_p3_manipulation.arm_node import (
    QOS_HEARTBEAT,
    QOS_LATCHED_EVENTS,
    QOS_RELIABLE,
    QOS_SENSOR,
    STALE_JOINTS_S,
    STALE_STATUS_S,
    Freshness,
)

#: Doosan M0609 의 ROS 관절 이름 관례. USD 자산 이름은 마스터에서 확인해 파라미터로 덮는다.
DEFAULT_JOINT_NAMES = ('joint_1', 'joint_2', 'joint_3', 'joint_4', 'joint_5', 'joint_6')
#: 조제실 스테이지의 레일 관절(Simu 9/18 인터페이스 표). 계약 v1 밖이다.
DEFAULT_RAIL_JOINT_NAMES = ('rail_x', 'rail_y')
DEFAULT_RAIL_TEACH = 'm0609_rail_teach.yaml'

#: 장면 v2 재고(Simu 9/18 제안): std_msgs/String JSON, reliable + transient_local, depth 1. 계약 v1 밖.
QOS_INVENTORY = QoSProfile(reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                           history=HistoryPolicy.KEEP_LAST, depth=1)


def plan_cache_payload(entries, source, computed_generation, live_generation, kinds=None):
    """Latched ready JSON. None if inventory moved on before publish.

    `kinds` 는 칸 → 종류다. 주면 종류별 집계(`by_kind`)와 **전부 풀린 종류**(`kinds_ready`)를 같이 낸다.
    병원 데모는 원통만 쓰므로 준비 조건을 종류로 본다(작전 9/23) — 모듈이 안 풀려도 원통이 다 풀리면 간다.
    """
    if computed_generation != live_generation:
        return None
    ok = [cid for cid, entry in entries.items() if entry.steps is not None]
    failed = {cid: entry.why for cid, entry in entries.items() if entry.steps is None}
    by_kind = {}
    for cid, entry in entries.items():
        kind = (kinds or {}).get(cid)
        if kind is None:
            continue
        counts = by_kind.setdefault(kind, {'solved': 0, 'total': 0})
        counts['total'] += 1
        counts['solved'] += entry.steps is not None
    ready = sorted(k for k, c in by_kind.items() if c['total'] and c['solved'] == c['total'])
    return {'solved': len(ok), 'total': len(entries), 'failed': failed, 'source': source,
            'generation': computed_generation, 'ready': True,
            'by_kind': by_kind, 'kinds_ready': ready}


def plan_cache_invalidate(source, generation):
    """Latched not-ready after the cache is cleared for a new source."""
    return {'solved': 0, 'total': 0, 'failed': {}, 'source': source, 'generation': generation, 'ready': False}
#: 장면 v2 계획의 접힌 자세 이름. 레일은 홈과 이 단계 자세에서만 움직인다(계획은 이 단계에 홈 관절값을 둔다).
V2_SAFE_PHASES = ('fold', 'fold_back')

STATUS_OK = 'ok'
STATUS_FAILED = 'failed'
STATUS_CANCELLED = 'cancelled'


def default_rail_teach_path():
    """설치된 이 패키지의 `config/m0609_rail_teach.yaml`. 레일을 켤 때만 부른다(끄면 import 도 하지 않는다)."""
    from ament_index_python.packages import get_package_share_directory
    return os.path.join(get_package_share_directory('rokey_p3_manipulation'), 'config', DEFAULT_RAIL_TEACH)


def load_rail_teach_file(path):
    """teach yaml 을 읽어 검사한다. 틀리면 기동하지 않는다(RefillPlanError)."""
    import yaml
    with open(path, encoding='utf-8') as handle:
        return seq.load_rail_teach(yaml.safe_load(handle))


def speed_profile(speed, accel, size, name, speed_required=False):
    """(속도, 가속) 파라미터 쌍 검사. [0.0] 은 안 줬다(None).

    속도를 주고 가속을 비우면 ValueError 다. 가감속 없이 속도만 올리지 않는다(실습1 약통 흔들림).
    가속만 주면 쓸 곳이 없어 역시 ValueError. `speed_required` 면 속도가 있어야 한다.
    """
    speed = _optional_limits(speed, size, f'{name}_max_speed')
    accel = _optional_limits(accel, size, f'{name}_max_accel')
    if speed is None and (speed_required or accel is not None):
        raise ValueError(f'{name}_max_speed 가 없다')
    if speed is not None and accel is None and not speed_required:
        raise ValueError(f'{name}_max_speed 를 주면 {name}_max_accel 도 줘야 한다(가감속 없이 속도만 올리지 않는다)')
    return speed, accel


def _optional_limits(values, size, name):
    """[0.0] 이면 None(안 줬다). 아니면 양수 size 개. 틀리면 ValueError."""
    values = [float(value) for value in values]
    if values == [0.0]:
        return None
    if len(values) != size or not all(value > 0.0 for value in values):
        raise ValueError(f'{name} 는 양수 {size}개여야 한다 ({values})')
    return tuple(values)


class M0609ArmNode(Node):
    """m0609_arm 노드."""
    # 시험 fixture 가 __init__ 를 다 거치지 않고 만든 노드도 waypoint 시한 계산이 되게 기본을 둔다(35fb28a 회귀).
    _state_gap_grace = 0.2


    def __init__(self):
        super().__init__('m0609_arm')

        self.declare_parameter('robot_id', 'm0609')
        self.declare_parameter('joint_names', list(DEFAULT_JOINT_NAMES))
        self.declare_parameter('home_joint_positions', [0.0] * seq.DOF)
        for key in seq.POSE_KEYS:
            # 마스터에서 티칭한 관절값. 기본값 0 은 "아직 안 쟀다" 다.
            self.declare_parameter(f'{key}_joints', [0.0] * seq.DOF)
        self.declare_parameter('home_tolerance_rad', 0.05)
        self.declare_parameter('waypoint_tolerance_rad', 0.05)
        self.declare_parameter('waypoint_timeout_s', 10.0)
        # 상태 수신 공백이 이보다 크면 그만큼 waypoint 시한을 뒤로 민다(sim s). 시뮬레이터가 느린 것을
        # 팔 실패로 적지 않는다. 0 이면 예전처럼 공백도 시한에 센다.
        self.declare_parameter('state_gap_grace_s', 0.2)
        # 기본값은 M0609 자산 한계(joint_3 ±150°, 나머지 ±360°). 다른 자산이면 파라미터로 덮는다.
        self.declare_parameter('joint_limits_low', [low for low, _ in seq.M0609_JOINT_LIMITS])
        self.declare_parameter('joint_limits_high', [high for _, high in seq.M0609_JOINT_LIMITS])
        self.declare_parameter('command_rate_hz', 20.0)
        self.declare_parameter('max_joint_speed', 0.5)
        self.declare_parameter('refill_timeout_s', 90.0)      # 계약 7절
        self.declare_parameter('grasp_settle_s', 0.5)
        self.declare_parameter('release_settle_s', 0.3)
        self.declare_parameter('hold_timeout_s', 2.0)
        # true 면 joint_states·holding 이 없어도 시퀀스를 낸다. 도착 확인·낙하 판정을 건너뛴다.
        self.declare_parameter('open_loop', False)
        # 조제실 스테이지의 2축 레일. 끄면 레일 토픽을 만들지 않는다.
        self.declare_parameter('rail_enabled', False)
        self.declare_parameter('rail_teach_file', '')       # 빈 값 = 이 패키지 config/m0609_rail_teach.yaml
        self.declare_parameter('rail_joint_names', list(DEFAULT_RAIL_JOINT_NAMES))
        self.declare_parameter('rail_tolerance_m', 0.01)     # 스테이지 selfdemo 의 --rail-tolerance 기본값
        self.declare_parameter('rail_timeout_s', 10.0)       # 레일 한 단계 도착 시한(sim s). waypoint_timeout_s 와 같다
        # 레일 모드의 속도·가속(관절별 rad/s·rad/s², 레일 축별 m/s·m/s²). 가속이 있으면 동기화 사다리꼴로 낸다.
        # 속도만 주고 가속을 비우면 기동하지 않는다(실습1: 가감속 없이 속도만 올리면 약통이 흔들렸다).
        # 관절 속도가 비어 있으면 max_joint_speed 로 이전처럼 등속 보간한다.
        # 기본값 = M0609 최고 속도의 **90%**(재범 9/24 20:4x "속도 90% 바로". 9/18 실습1 뒤 80% 였다).
        # 최고 속도는 USD max_velocity 와 두산 사양이 같다(150/150/180/225/225/225 °/s, Simu 9/18).
        # 가속·레일 값은 사양 근거가 없는 Simu 제안이다(판단).
        # [0.0] 은 비어 있음이다(ROS 파라미터는 빈 배열 타입이 없다).
        self.declare_parameter('rail_joint_max_speed', [2.356, 2.356, 2.827, 3.534, 3.534, 3.534])   # rad/s
        self.declare_parameter('rail_joint_max_accel', [4.0, 4.0, 4.0, 6.0, 6.0, 6.0])               # rad/s²
        self.declare_parameter('rail_max_speed', [0.8, 0.8])   # m/s. 레일 실물 없음, USD 무제한. Simu 제안 1.0 의 80%
        self.declare_parameter('rail_max_accel', [1.0, 1.0])   # m/s²
        # TCP 직선 속도 상한(두산 사양 1.0 m/s 의 90%, 9/24). 레일은 80% 그대로다.
        # 관절 사다리꼴의 TCP 최고 속도(FK)가 넘으면 그만큼 늦춘다.
        # 0 이면 보지 않는다. TCP 는 link_6 z 0.19671 m(Simu, 스테이지 잡힘 판정과 같은 값).
        self.declare_parameter('rail_tcp_max_speed', 0.9)
        self.declare_parameter('rail_tcp_offset_m', [0.0, 0.0, 0.19671])
        # 레일 모드 명령 주기. 스테이지는 명령을 드라이브 목표로 바로 넣는다(보간 없음). 20 Hz 면 80% 속도에서
        # 점 간격이 TCP 4.3 cm 라 50 Hz(1.7 cm)로 낸다.
        self.declare_parameter('rail_command_rate_hz', 50.0)
        # 레일 모드에서 joint_states·rail/joint_states 가 stale(1.0 s, 계약 4절)이면 명령을 멈추고
        # 이만큼(wall) 기다린다.
        # Isaac 창 모드는 한 틱이 느리거나 timeline 복구 중에 셋이 같이 끊길 수 있다(Simu 9/18).
        self.declare_parameter('stale_grace_s', 3.0)
        # 레일 모드에서 수신 간격이 이보다 길면 WARN 한 줄(틱 간격 기록, L3 에서 1 s 시한 근거를 모으려고).
        self.declare_parameter('state_gap_warn_s', 0.2)
        # 장면 v2(재범 9/18: 3축 레일, 약통 2종, 칸 랜덤, 실행 중 IK). 1(기본)이면 위의 v1 동작 그대로다.
        self.declare_parameter('scene_version', 1)
        self.declare_parameter('inventory_topic', '/m0609/shelf/inventory')
        self.declare_parameter('v2_rail_joint_names', ['rail_x', 'rail_y', 'rail_z'])
        self.declare_parameter('v2_rail_max_speed', [0.8, 0.8, 0.8])      # m/s. v1 레일과 같은 80% 값(z 도 같게, 판단)
        self.declare_parameter('v2_rail_max_accel', [1.0, 1.0, 1.0])
        self.declare_parameter('v2_seed', 0)                  # 칸 랜덤 시드. 같은 시드·재고·요청이면 같은 순서다
        self.declare_parameter('v2_ik_seeds', 12)             # IK 시드 수(첫째는 홈)
        self.declare_parameter('v2_min_clearance', 0.01)      # 팔·그리퍼 여유 기준(m). 모자라면 그 칸을 건너뛴다
        # 레일 자세 고르기. 기본값은 지금 동작이다(도달이 짧은 후보부터 처음 통과한 것).
        # 'preferred_first' 는 오프라인 선호 후보부터 검사한다. 레일 이동 경로와 팔꿈치 조건도 검사한다.
        # 값은 `scene_v2.RAIL_SELECT` 다. 여기서는 scene_v2 를 아직 import 하지 않으므로 글자로 두고,
        # `_setup_v2` 에서 상수와 대조한다(기본값이 `scene_v2.FIRST_FEASIBLE` 과 같은지도 시험이 고정한다).
        self.declare_parameter('v2_rail_select', 'first_feasible')
        self.declare_parameter('v2_max_skips', 3)             # goal 하나에서 건너뛸 수 있는 칸 수
        self.declare_parameter('v2_collision_file', '')       # 빈 값 = 이 패키지 config/m0609_collision.yaml
        # 칸별 계획을 파일로 두고 다시 쓴다(작전 결정 6, 9/23: 기동 1분 52초 중 캐시가 73.6 s 였다).
        # 저장소 밖이다. **빈 값이면 끈다** — 그때 동작은 이 기능이 없던 때와 글자 그대로 같다.
        self.declare_parameter('plan_cache_dir', '~/.cache/rokey_p3/plan_cache')
        # 보충 전 약통 확인(QR·DB·카메라 계약 2.3). 기본 끔. 켜면 잡기 직전(grasp_pose 도착 뒤) 손 카메라의 약통 QR 을
        # 읽고 /orchestrator/check_container 에 묻는다. 못 읽음·시한 초과·거부면 닫지 않고 success=false 로 끝낸다.
        # 가드 모듈 경로(v2_guarded_module_path 의 module 칸)는 이 확인을 거치지 않는다(다음 PR).
        self.declare_parameter('container_check', False)
        self.declare_parameter('container_tag_topic', '/m0609/hand_camera/tag_reads')
        self.declare_parameter('container_read_timeout_s', 2.0)    # sim. 도착 뒤 판독을 기다리는 시간
        self.declare_parameter('container_check_timeout_s', 2.0)   # wall. 서비스 시한(계약 2.3)
        # 지원 환경에서 기본 활성화한다. 기존 wall-clock/open-loop 실행과 명시적 덮어쓰기는 유지한다.
        self.declare_parameter('v2_guarded_module_path',
                               int(self.get_parameter('scene_version').value) == 2
                               and bool(self.get_parameter('use_sim_time').value)
                               and not bool(self.get_parameter('open_loop').value))

        self._robot_id = self.get_parameter('robot_id').value
        self._joint_names = list(self.get_parameter('joint_names').value)
        self._home = seq.check_joints('home_joint_positions',
                                      self.get_parameter('home_joint_positions').value)
        self._poses = {key: seq.check_joints(f'{key}_joints', self.get_parameter(f'{key}_joints').value)
                       for key in seq.POSE_KEYS}
        self._home_tolerance = float(self.get_parameter('home_tolerance_rad').value)
        self._waypoint_tolerance = float(self.get_parameter('waypoint_tolerance_rad').value)
        self._waypoint_timeout = float(self.get_parameter('waypoint_timeout_s').value)
        self._state_gap_grace = float(self.get_parameter('state_gap_grace_s').value)
        self._limits = tuple(zip(self.get_parameter('joint_limits_low').value,
                                 self.get_parameter('joint_limits_high').value, strict=True))
        self._command_rate_hz = float(self.get_parameter('command_rate_hz').value)
        self._max_joint_speed = float(self.get_parameter('max_joint_speed').value)
        self._refill_timeout = float(self.get_parameter('refill_timeout_s').value)
        self._grasp_settle = float(self.get_parameter('grasp_settle_s').value)
        self._release_settle = float(self.get_parameter('release_settle_s').value)
        self._hold_timeout = float(self.get_parameter('hold_timeout_s').value)
        self._open_loop = bool(self.get_parameter('open_loop').value)

        if len(self._joint_names) != seq.DOF or len(self._limits) != seq.DOF:
            raise ValueError(f'joint_names, joint_limits 는 {seq.DOF}개여야 한다')
        self._rail_teach = None
        self._rail_joint_names = list(self.get_parameter('rail_joint_names').value)
        self._rail_tolerance = float(self.get_parameter('rail_tolerance_m').value)
        self._rail_timeout = float(self.get_parameter('rail_timeout_s').value)
        self._joint_speed_limits, self._joint_accel_limits = speed_profile(
            self.get_parameter('rail_joint_max_speed').value, self.get_parameter('rail_joint_max_accel').value,
            seq.DOF, 'rail_joint')
        self._rail_max_speed, self._rail_max_accel = speed_profile(
            self.get_parameter('rail_max_speed').value, self.get_parameter('rail_max_accel').value,
            seq.RAIL_DOF, 'rail', speed_required=True)
        self._tcp_max_speed = float(self.get_parameter('rail_tcp_max_speed').value)
        self._tcp_offset = tuple(float(v) for v in self.get_parameter('rail_tcp_offset_m').value)
        self._rail_command_rate = float(self.get_parameter('rail_command_rate_hz').value)
        self._tcp_model = None
        self._stale_grace = float(self.get_parameter('stale_grace_s').value)
        self._gap_warn = float(self.get_parameter('state_gap_warn_s').value)
        self._last_seen = {}
        if self.get_parameter('rail_enabled').value:
            if len(self._rail_joint_names) != seq.RAIL_DOF:
                raise ValueError(f'rail_joint_names 는 {seq.RAIL_DOF}개여야 한다')
            path = self.get_parameter('rail_teach_file').value or default_rail_teach_path()
            self._rail_teach = load_rail_teach_file(path)
            if self._rail_teach.home_joints != self._home:
                self.get_logger().info(f'레일 teach 의 홈 {list(self._rail_teach.home_joints)} 을 쓴다'
                                       '(home_joint_positions 는 쓰지 않는다).')
            self._home = self._rail_teach.home_joints
            self._rail_teach_path = path
            if self._tcp_max_speed > 0.0:
                from rokey_p3_manipulation import m0609_kinematics as kin
                self._tcp_model = kin.M0609(kin.ToolTransform(self._tcp_offset, (0.0, 0.0, 0.0, 1.0)))
        self._scene_v2 = int(self.get_parameter('scene_version').value) == 2
        self._module_feedback = None
        if self.get_parameter('v2_guarded_module_path').value and not self._scene_v2:
            raise ValueError('v2_guarded_module_path requires scene_version=2')
        if self._scene_v2:
            self._setup_v2()
        if not self.get_parameter('use_sim_time').value:
            self.get_logger().warn('use_sim_time 이 false 다. 계약 4절은 모든 노드가 sim time 이다.')

        self._lock = threading.Lock()
        self._joints = Freshness(STALE_JOINTS_S)
        self._holding = Freshness(STALE_STATUS_S)
        self._commanded = tuple(self._home)
        self._rail_states = Freshness(STALE_JOINTS_S)
        # 레일 보충에서 지나온 팔 자세(관절값, 접힌 자세인가). 끊기면 이것을 거꾸로 되짚어 접힌 자세로 돌아간다.
        self._arm_trail = []
        self._chained = False            # 앞 move_to 가 through 였다(다음 이동은 그 목표에서 시작)
        self._phase_marks = []           # (feedback phase, sim s). 레일 모드 단계 시간 로그용
        self._rail_commanded = None if self._rail_teach is None else self._rail_teach.home_rail
        self._epoch = 0
        self._goal_active = False
        self._homing = False
        self._homing_cancelled = False
        self._homing_thread = None
        # goal 을 받은 뒤 홈 복귀를 끝내기 전까지 true. 리셋 뒤 다시 복귀할지 정한다.
        self._left_home = False
        self._gripper_closed = False
        self._holding_seen = False       # 기동 뒤 holding 을 한 번이라도 받았나(쥔 채 시작 경고 한 번)
        self._fence = ResetFence()
        # 노드를 내리는 중. 보충·홈 복귀가 멈추고 관절·그리퍼 명령·이벤트를 더 내지 않는다.
        self._closing = threading.Event()

        self._callbacks = ReentrantCallbackGroup()
        namespace = f'/{self._robot_id}'
        self._joint_command_pub = self.create_publisher(
            JointState, f'{namespace}/arm/joint_command', QOS_RELIABLE)
        self._gripper_pub = self.create_publisher(Bool, f'{namespace}/gripper/command', QOS_RELIABLE)
        self._at_home_pub = self.create_publisher(Bool, f'{namespace}/arm/at_home', QOS_HEARTBEAT)
        self._plan_cache_pub = None
        if self._scene_v2:
            self._plan_cache_pub = self.create_publisher(String, f'{namespace}/arm/plan_cache', QOS_INVENTORY)
        self._event_pub = self.create_publisher(Event, '/events', QOS_LATCHED_EVENTS)

        # 레일 모드는 상태 구독(joint_states·rail/joint_states·gripper/holding)을 별도 노드에 두고 그 노드만
        # SingleThreadedExecutor 스레드로 돌린다. 이 노드의 MultiThreadedExecutor 는 30 Hz 구독 콜백을 0.2-2 s 씩
        # 늦게 한꺼번에 처리했다(9/18 docker 측정: 발행은 30 Hz 그대로, 최소 rclpy 노드로도 재현, 단일 스레드는 0건).
        # 그러면 stale(1.0 s)로 명령이 멈춘다. 레일 끔은 이전과 같다(이 노드에서 구독).
        self._state_node = None
        self._state_executor = None
        subscriber, group = self, self._callbacks
        if self._rail_teach is not None:
            self._state_node = rclpy.create_node(f'{self.get_name()}_states')
            subscriber, group = self._state_node, None
        subscriber.create_subscription(JointState, f'{namespace}/joint_states', self._on_joint_states,
                                       QOS_SENSOR, callback_group=group)
        subscriber.create_subscription(Bool, f'{namespace}/gripper/holding', self._on_holding,
                                       QOS_HEARTBEAT, callback_group=group)
        self.create_subscription(Event, '/events', self._on_event, QOS_LATCHED_EVENTS,
                                 callback_group=self._callbacks)
        self._container_check = bool(self.get_parameter('container_check').value)
        self._container_read_timeout = float(self.get_parameter('container_read_timeout_s').value)
        self._container_check_timeout = float(self.get_parameter('container_check_timeout_s').value)
        self._container_reads = []          # 최근 약통 판독(gate.Read). 콜백 스레드가 채운다
        self._refused_cells = gate.RefusedCells()
        self._read_container = ''           # 이번 보충에서 읽고 허용된 약통 ID. 결과 lot_id 에 싣는다(기록용)
        self._check_client = None
        if self._container_check:
            self.create_subscription(TagRead, self.get_parameter('container_tag_topic').value,
                                     self._on_tag_read, QOS_RELIABLE, callback_group=self._callbacks)
            self._check_client = self.create_client(CheckContainer, '/orchestrator/check_container',
                                                    callback_group=self._callbacks)
            self.get_logger().info(f'약통 확인 켬: 판독 {self.get_parameter("container_tag_topic").value}, '
                                   f'판독 대기 {self._container_read_timeout} s sim, 서비스 시한 '
                                   f'{self._container_check_timeout} s')
        self._rail_command_pub = None
        if self._rail_teach is not None:
            # 계약 v1 밖. 조제실 스테이지가 제안한 이름이다(Simu 9/18 표, QoS 는 팔 토픽과 같다).
            self._rail_command_pub = self.create_publisher(
                JointState, f'{namespace}/rail/joint_command', QOS_RELIABLE)
            self._state_node.create_subscription(JointState, f'{namespace}/rail/joint_states', self._on_rail_states,
                                                 QOS_SENSOR)
            if self._scene_v2:
                self._state_node.create_subscription(String, self.get_parameter('inventory_topic').value,
                                                     self._on_inventory, QOS_INVENTORY)
            self._state_executor = SingleThreadedExecutor()
            self._state_executor.add_node(self._state_node)
            threading.Thread(target=self._spin_states, daemon=True).start()
        # `arm/at_home` 는 5 Hz heartbeat 다 (계약 2.3절).
        self.create_timer(0.2, self._publish_at_home, callback_group=self._callbacks)

        self._refill_server = ActionServer(
            self, Refill, f'{namespace}/refill',
            execute_callback=self._execute_refill,
            goal_callback=self._accept_refill,
            cancel_callback=self._accept_cancel,
            callback_group=self._callbacks)

        self.get_logger().info(
            f'm0609_arm up. robot={self._robot_id} joints={self._joint_names} '
            f'open_loop={self._open_loop}')
        if self._rail_teach is not None:
            self.get_logger().info(
                f'rail on. teach={self._rail_teach_path} joints={self._rail_joint_names} '
                f'home_rail={list(self._rail_teach.home_rail)} safe={list(self._rail_teach.safe_phases)}')

    def _setup_v2(self):
        """장면 v2 준비. 레일 3축, 홈은 레일 teach 파일의 홈(스테이지 홈과 같다), 계획은 goal 마다 만든다."""
        import yaml

        from rokey_p3_manipulation import clearance
        from rokey_p3_manipulation import m0609_kinematics as kin
        from rokey_p3_manipulation import pick_plan
        from rokey_p3_manipulation import plan_cache_file
        from rokey_p3_manipulation import scene_v2
        self._v2 = scene_v2
        self._rail_joint_names = list(self.get_parameter('v2_rail_joint_names').value)
        if len(self._rail_joint_names) != 3:
            raise ValueError('v2_rail_joint_names 는 3개여야 한다')
        self._rail_max_speed, self._rail_max_accel = speed_profile(
            self.get_parameter('v2_rail_max_speed').value, self.get_parameter('v2_rail_max_accel').value,
            3, 'v2_rail', speed_required=True)
        path = self.get_parameter('rail_teach_file').value or default_rail_teach_path()
        home = load_rail_teach_file(path).home_joints
        self._home = home
        self._rail_teach = seq.RailTeach(home, (0.0, 0.0, 0.0), V2_SAFE_PHASES, {})
        self._rail_teach_path = f'scene v2 (홈: {path})'
        collision = self.get_parameter('v2_collision_file').value or os.path.join(
            os.path.dirname(default_rail_teach_path()), 'm0609_collision.yaml')
        with open(collision, encoding='utf-8') as handle:
            self._v2_tcp, self._v2_link_boxes = clearance.load_collision(yaml.safe_load(handle))
        self._tcp_model = kin.M0609(kin.ToolTransform(self._v2_tcp, (0.0, 0.0, 0.0, 1.0)))
        self._v2_seeds = pick_plan.default_seeds(home, int(self.get_parameter('v2_ik_seeds').value), seed=1)
        self._plan_cache = plan_cache_file
        self._plan_cache_dir = str(self.get_parameter('plan_cache_dir').value or '')
        self._plan_code_digest = plan_cache_file.code_digest()
        self._v2_rail_select = str(self.get_parameter('v2_rail_select').value)
        if self._v2_rail_select not in scene_v2.RAIL_SELECT:
            raise ValueError(f'v2_rail_select 는 {scene_v2.RAIL_SELECT} 중에서다({self._v2_rail_select!r})')
        if self._v2_rail_select == scene_v2.PREFERRED_FIRST and self._open_loop:
            raise ValueError('preferred_first requires closed-loop joint and rail feedback')
        self._v2_rail_fault = ''
        base = (scene_v2.DEFAULT_PARAMS if self._v2_rail_select == scene_v2.FIRST_FEASIBLE
                else scene_v2.PREFERRED_PARAMS)
        self._v2_params = base._replace(min_clearance=float(self.get_parameter('v2_min_clearance').value))
        # L3 판정선 1번: 켜진 값이 로그에 있어야 한다(작전 9/21).
        self.get_logger().info(f'scene v2 레일 고르기: v2_rail_select={self._v2_rail_select}')
        if self.get_parameter('v2_guarded_module_path').value:
            from rokey_p3_manipulation import module_execution, module_path
            if self._open_loop or not self.get_parameter('use_sim_time').value:
                raise ValueError('guarded module path requires closed-loop Isaac simulation (use_sim_time=true)')
            self._module_feedback = module_execution.Feedback()
            self._module_limits = module_path.Limits(
                joint_speed=self._joint_speed_limits, joint_accel=self._joint_accel_limits,
                rail_speed=self._rail_max_speed, rail_accel=self._rail_max_accel,
                period=self._period(), clearance=self._v2_params.min_clearance)
            self._tcp_model = kin.M0609(kin.ToolTransform(self._v2_tcp, (0., 0., 0., 1.)), self._limits)
        self._v2_picker = pick_plan.CellPicker(int(self.get_parameter('v2_seed').value))
        self._v2_max_skips = int(self.get_parameter('v2_max_skips').value)
        self._scene = None
        self._module_inventory_valid = False
        # 칸별 계획 캐시. inventory 를 받으면 뒤에서 모든 칸을 미리 푼다(칸당 수 초, 작전 9/18).
        # goal 에서는 고르기만 한다.
        self._v2_cache = scene_v2.PlanCache(self._v2_rail_select)
        self._v2_cache_lock = threading.Lock()
        self._v2_precompute = None
        # 요약(`v2 계획 캐시 …`·`완료 종류 …`)과 plan_cache payload 를 아직 안 낸 장면이 있는가.
        # 파일 캐시가 모든 칸을 채우면 **풀 것이 없어도** 그 줄들이 나가야 한다(demo_v2 가 기다린다).
        self._v2_summary_pending = False
        self._v2_done = None
        self._inventory_source = ''
        self._inventory_generation = 0

    def _on_inventory(self, msg):
        """장면 v2 재고. 틀리면 이전 것을 그대로 두고 경고한다."""
        try:
            scene = self._v2.parse_inventory(msg.data)
            source = str(json.loads(msg.data).get('source') or '')
        except (self._v2.SceneError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            if getattr(self, '_module_feedback', None) is not None:
                self._module_inventory_valid = False
                if getattr(self, '_module_request', False) and self.goal_active():
                    self._module_feedback.fault = 'invalid inventory during module execution; reset required'
            self.get_logger().warn(f'inventory 를 읽지 못했다: {error}', throttle_duration_sec=5.0)
            return
        with self._lock:
            first = self._scene is None
            self._scene = scene
            self._inventory_source = source
            self._inventory_generation += 1
            generation = self._inventory_generation
            self._module_inventory_valid = True
        with self._v2_cache_lock:
            changed = self._v2_cache.refresh(scene)
            if changed and not first:
                self.get_logger().info('inventory 장면(장애물·수납·레일)이 바뀌었다. 계획 캐시를 비우고 다시 푼다.')
                self._publish_plan_cache_payload(plan_cache_invalidate(source, generation))
            if changed:
                self._v2_summary_pending = True
            busy = self._v2_precompute is not None and self._v2_precompute.is_alive()
            if not busy and self._v2_cache.missing(scene):
                self._read_plan_cache_file(scene)
            # 풀 것이 없어도 **요약이 밀려 있으면** 돌린다. 파일에서 전부 읽은 기동이 그 경우다 —
            # 그때 안 돌리면 `완료 종류:` 줄과 payload 가 영영 안 나가고 up 이 시한까지 기다린다(최적화 9/23).
            if not busy and (self._v2_cache.missing(scene) or self._v2_summary_pending):
                self._v2_summary_pending = False
                self._v2_precompute = threading.Thread(target=self._precompute_plans, daemon=True)
                self._v2_precompute.start()
        if first:
            present = sum(c.present for c in scene.cells)
            self.get_logger().info(f'inventory: 칸 {len(scene.cells)}(있음 {present}), 수납 {sorted(scene.targets)}, '
                                   f'장애물 {len(scene.obstacles)}, 레일 {list(scene.rail_names)} '
                                   f'한계 {[list(v) for v in scene.rail_limits]}')

    def _plan_cell(self, scene, cell):
        """칸 하나의 계획. 캐시에 있으면 그것, 없으면 풀어서 넣는다. (PlanEntry, 캐시에서 왔나)."""
        with self._v2_cache_lock:
            entry = self._v2_cache.get(scene, cell)
        if getattr(self, '_module_feedback', None) is not None and cell.kind == 'module' and entry is not None:
            from rokey_p3_manipulation.module_path import signature
            if entry.steps is not None and entry.steps.scene_signature != signature(scene):
                entry = None
        if entry is not None:
            return entry, True
        started = time.monotonic()
        if getattr(self, '_module_feedback', None) is not None and cell.kind == 'module':
            from rokey_p3_manipulation import module_path
            from rokey_p3_manipulation.m0609_kinematics import PlanError
            try:
                steps = module_path.plan_module(self._tcp_model, scene, cell, self._v2_link_boxes, self._v2_tcp,
                                                self._v2_seeds, self._v2_params, self._home,
                                                self._rail_teach.home_rail, self._module_limits)
                why = (f'guarded module: motion={steps.seconds:.2f}s (sensor waits excluded), '
                       f'feasible={steps.feasible}/{steps.evaluated}, clearance={steps.clearance:.4f}m')
                clearance = steps.clearance
            except PlanError as error:
                steps, why, clearance = None, str(error), None
        else:
            steps, why, clearance = self._v2.plan_refill(
                self._tcp_model, scene, cell, self._v2_link_boxes, self._v2_tcp,
                self._v2_seeds, self._v2_params, self._home, place_cache=self._v2_cache.legs,
                rail_select=self._v2_rail_select)
        entry = self._v2.PlanEntry(steps, why, clearance, time.monotonic() - started)
        with self._v2_cache_lock:
            self._v2_cache.put(scene, cell, entry)
        return entry, False

    def _plan_cache_key(self, scene):
        """이 장면·이 입력·이 계획 코드의 캐시 키. 계획이 달라지는 값만 넣는다(작전 결정 6 요구 1)."""
        rail = getattr(self, '_rail_teach', None)
        return self._plan_cache.plan_key(
            self._v2.scene_signature(scene), self._v2_rail_select,
            {cell.cell_id: self._v2.cell_key(cell) for cell in scene.cells},
            {'seeds': self._v2_seeds, 'params': self._v2_params, 'tcp': self._v2_tcp,
             'link_boxes': self._v2_link_boxes, 'home': self._home,
             'home_rail': None if rail is None else rail.home_rail,
             'module_limits': getattr(self, '_module_limits', None),
             'joint_limits': self._limits},
            code=self._plan_code_digest)

    def _read_plan_cache_file(self, scene):
        """파일 캐시를 메모리 캐시에 넣는다. 꺼져 있거나 키가 다르면 아무것도 하지 않는다.

        부르는 쪽이 `_v2_cache_lock` 을 들고 있어야 한다.
        """
        if not getattr(self, '_plan_cache_dir', ''):
            return
        key = self._plan_cache_key(scene)
        plans = self._plan_cache.load(self._plan_cache_dir, key)
        if not plans:
            self.get_logger().info(f'v2 계획 캐시 파일: 없음 key={key[:12]}')
            return
        loaded, total = self._v2_cache.load_plans(scene, plans)
        self.get_logger().info(f'v2 계획 캐시 파일: 읽음 {loaded}/{total} key={key[:12]}')

    def _write_plan_cache_file(self, scene):
        """다 푼 뒤 푼 칸만 저장한다. 못 푼 칸은 넣지 않는다 — 다음 기동에서 다시 푼다."""
        if not getattr(self, '_plan_cache_dir', ''):
            return
        with self._v2_cache_lock:
            plans = self._v2_cache.plans()
        key = self._plan_cache_key(scene)
        kept = len(self._plan_cache.solved_only(plans))
        path = self._plan_cache.save(self._plan_cache_dir, key, plans)
        self.get_logger().info(f'v2 계획 캐시 파일: {"저장 " + str(kept) if path else "저장 안 함 " + str(kept)}칸 '
                               f'key={key[:12]}' + (f' {path}' if path else ''))

    def _precompute_plans(self):
        """inventory 를 받은 뒤 못 푼 칸을 차례로 미리 푼다. 끝나면 요약 한 줄."""
        started = time.monotonic()
        # 늘 **최신 재고**를 따라 푼다. 도중에 재고가 바뀌어도 그만두지 않는다 — `_on_inventory` 는 이 스레드가
        # 살아 있으면 새로 띄우지 않으므로, 여기서 그만두면 남은 칸을 아무도 미리 풀지 않는다(#490 이 그랬다:
        # 세대가 바뀌면 return 해서, 계산 중 집기·재생성이 한 번 있으면 요약 줄도 캐시 채우기도 멈췄다).
        while not self._closing.is_set():
            with self._lock:
                scene = self._scene
            with self._v2_cache_lock:
                missing = self._v2_cache.missing(scene)
            if not missing:
                break
            self._plan_cell(scene, missing[0])
        with self._lock, self._v2_cache_lock:
            generation = self._inventory_generation
            entries = dict(self._v2_cache.entries())
            source = self._inventory_source
            live_generation = self._inventory_generation
        kinds = {cell.cell_id: cell.kind for cell in getattr(scene, 'cells', ())}
        payload = plan_cache_payload(entries, source, generation, live_generation, kinds)
        if payload is None:
            return
        seconds = [e.seconds for e in entries.values()]
        self.get_logger().info(
            f'v2 계획 캐시: {payload["solved"]}/{payload["total"]}칸 풀림, 전체 {time.monotonic() - started:.1f} s, '
            f'칸당 {min(seconds, default=0):.1f}-{max(seconds, default=0):.1f} s. 못 푼 칸 {payload["failed"]}')
        # 준비 조건을 종류로 본다(작전 9/23). 집계를 먼저 찍고 **완료 종류**를 끝에 둔다 —
        # 하나도 완료가 아니면 `(없음)` 이라, 기다리는 쪽이 집계의 종류 이름에 걸리지 않는다.
        counts = ' '.join(f'{k}={c["solved"]}/{c["total"]}' for k, c in sorted(payload['by_kind'].items()))
        self.get_logger().info(
            f'v2 계획 캐시 종류별: {counts or "(없음)"}. 완료 종류: '
            f'{", ".join(payload["kinds_ready"]) or "(없음)"}')
        self._write_plan_cache_file(scene)
        self._publish_plan_cache_payload(payload)

    def _publish_plan_cache_payload(self, payload):
        """Latched JSON for trial clients. Does not change plan_refill or timeouts."""
        if self._plan_cache_pub is None or payload is None:
            return
        self._plan_cache_pub.publish(String(data=json.dumps(payload, separators=(',', ':'))))

    # ---- 수신 ----------------------------------------------------------

    def _on_joint_states(self, msg):
        """M0609 6개만 뽑는다. 이름이 없으면 무시한다."""
        index = dict(zip(msg.name, msg.position, strict=False))
        try:
            values = tuple(float(index[name]) for name in self._joint_names)
        except KeyError:
            self.get_logger().warn(
                f'joint_states 에 M0609 관절이 없다. 기대: {self._joint_names}, 받음: {list(msg.name)}',
                throttle_duration_sec=5.0)
            return
        with self._lock:
            self._joints.update(values)
        self._observe_module_state('arm', values, msg)
        if self._rail_teach is not None:
            self._note_gap('joint_states')

    def _on_rail_states(self, msg):
        """레일 2개만 뽑는다. 이름이 없으면 무시한다."""
        index = dict(zip(msg.name, msg.position, strict=False))
        try:
            values = tuple(float(index[name]) for name in self._rail_joint_names)
        except KeyError:
            self.get_logger().warn(
                f'rail/joint_states 에 레일 관절이 없다. 기대: {self._rail_joint_names}, 받음: {list(msg.name)}',
                throttle_duration_sec=5.0)
            return
        with self._lock:
            self._rail_states.update(values)
        self._observe_module_state('rail', values, msg)
        self._note_gap('rail/joint_states')

    def _observe_module_state(self, actor, values, msg):
        feedback = getattr(self, '_module_feedback', None)
        if feedback is not None:
            try:
                stamp = float(msg.header.stamp.sec) + float(msg.header.stamp.nanosec) * 1e-9
            except (AttributeError, TypeError, ValueError):
                stamp = float('nan')
            velocities = getattr(msg, 'velocity', ())
            if len(velocities):
                names = self._joint_names if actor == 'arm' else self._rail_joint_names
                try:
                    index = dict(zip(msg.name, velocities, strict=True))
                    velocities = tuple(index[name] for name in names)
                except (AttributeError, KeyError, TypeError, ValueError):
                    velocities = (float('nan'),)  # invalidate this actor's observation
            feedback.observe(actor, values, stamp, velocities)

    def _note_gap(self, topic):
        """레일 모드 수신 간격 기록. `state_gap_warn_s` 보다 길면 WARN 한 줄. 스테이지는 30 Hz(0.033 s)로 낸다."""
        now = time.monotonic()
        last, self._last_seen[topic] = self._last_seen.get(topic), now
        if last is not None and now - last > self._gap_warn:
            self.get_logger().warn(f'{topic} 수신 공백 {now - last:.2f} s(wall). stale 은 {STALE_JOINTS_S} s, '
                                   f'유예 {self._stale_grace} s.')

    def _on_holding(self, msg):
        if getattr(self, '_module_feedback', None) is not None:
            self._module_feedback.grip(bool(msg.data))
        with self._lock:
            self._holding.update(bool(msg.data))
            first, self._holding_seen = not self._holding_seen, True
        if first and msg.data:
            # 쥔 채 종료(#113) 뒤 재기동일 수 있다. 자동으로 열면 쥔 물체를 떨어뜨리므로 열지 않는다.
            self.get_logger().warn('쥔 채 시작했다(gripper/holding=true). 다음 보충은 그리퍼를 열고 시작한다.')

    def _on_tag_read(self, msg):
        """약통 QR 판독만 남긴다(최근 20개)."""
        if msg.kind != TagRead.KIND_CONTAINER or msg.status != TagRead.STATUS_OK:
            return
        stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        with self._lock:
            self._container_reads = (self._container_reads + [gate.Read(stamp, msg.tag_id)])[-20:]

    def _check_container(self, goal_handle, deadline, cancelled):
        """잡기 직전 약통 확인(계약 2.3). 허용이면 None, 아니면 (status, detail, lot_id). 거부 칸은 기억한다."""
        cell = (self._v2_done or {}).get('cell', '')
        arrived = self.sim_now()
        read = None
        while read is None:
            with self._lock:
                read = gate.latest_read(self._container_reads, arrived)
            if read is not None or self.sim_now() >= arrived + self._container_read_timeout:
                break
            if cancelled():
                return self._stopped(goal_handle, deadline, 'container_check: 판독 중 중단')
            if not self.wait(0.05, cancelled):
                return self._stopped(goal_handle, deadline, 'container_check: 판독 중 중단')
        answer = None
        if read is not None and self._check_client.wait_for_service(timeout_sec=self._container_check_timeout):
            with self._lock:
                epoch = self._epoch
            future = self._check_client.call_async(CheckContainer.Request(
                container_id=read.tag_id, robot_id='m0609', cell_id=cell, epoch=epoch))
            done = threading.Event()
            future.add_done_callback(lambda _future: done.set())
            if done.wait(self._container_check_timeout) and future.result() is not None:
                response = future.result()
                answer = (response.allowed, response.reason)
        allowed, reason, container_id = gate.decide(read, answer)
        # 판독 수치(재범 9/25 점수판 AI 비전): 봉투 `vision pouch` 줄과 같은 형식. 지연은 잡기 자세 도착 → 첫 판독(sim).
        with self._lock:
            reads = [r for r in self._container_reads if r.stamp >= arrived]
        latency_ms = ((read.stamp if read is not None else self.sim_now()) - arrived) * 1000.0
        self.get_logger().info(
            f'vision container {container_id or "-"}: {"ok" if allowed else reason} 지연 {latency_ms:.0f} ms, '
            f'판독 {len(reads)}건(도착 뒤), cell={cell}')
        if allowed:
            self._read_container = container_id
            self.get_logger().info(f'약통 확인: {container_id} cell={cell} 장착 허용')
            return None
        with self._lock:
            epoch = self._epoch
        self._refused_cells.add(epoch, cell)
        detail = f'container_refused {container_id or "-"} cell={cell} reason={reason}'
        self.get_logger().warn(f'약통 확인: {detail}. 잡지 않고 끝낸다. 이 칸은 epoch {epoch} 에서 다시 안 고른다.')
        return STATUS_FAILED, detail, container_id

    def _on_event(self, msg):
        """epoch 는 orchestrator 만 발급한다. 본 것 중 가장 큰 값을 따른다(계약 4절)."""
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
        """리셋 barrier 4단계: 캐시를 버리고 at_home 을 다시 계산한다(계약 6절).

        isaac 리셋(계약 6절 2)과 별개로, 1단계 cancel 뒤 시작한 복귀가 리셋 중에 끊겼을 수 있으니
        (sim time 되감기) 새 관절값으로 복귀를 다시 시작한다. 이미 홈이면 아무것도 안 내서 isaac 리셋과 겹치지 않는다.
        이 노드가 goal 로 홈을 떠난 적이 없으면(시작 직후 래치된 `RESET_DONE`) 움직이지 않는다.
        같은 RESET_DONE 은 한 번만 처리한다. 이전 goal 이 끝나기를(wall 2 s) 기다린 뒤 울타리를 연다.
        """
        with self._lock:
            if not self._fence.accepts_done(epoch):
                return
        self.stop_homing()
        self._wait_goal_idle()
        module_recovery = (getattr(self, '_module_feedback', None) is not None
                           and (bool(self._module_feedback.fault) or getattr(self, '_module_request', False)))
        with self._lock:
            self._fence.done(epoch)
            self._v2_rail_fault = ''
            if getattr(self, '_module_feedback', None) is not None:
                self._module_feedback.reset()
            self._joints.clear()
            self._holding.clear()
            self._commanded = tuple(self._home)
            self._rail_states.clear()
            self._arm_trail = []
            if self._rail_teach is not None:
                self._rail_commanded = self._rail_teach.home_rail
            left_home = self._left_home
        self.get_logger().info(f'RESET_DONE epoch={epoch}. 캐시를 버리고 at_home 을 다시 낸다.')
        if left_home and not module_recovery and not self.goal_active():
            self.start_homing()

    # ---- 상태 ----------------------------------------------------------

    def joint_positions(self):
        """살아 있는 관절값 6개. 1.0 s 안 오면 None. open_loop 면 마지막 명령값."""
        with self._lock:
            value = self._joints.get()
            if value is None and self._open_loop:
                return self._commanded
            return value

    def rail_positions(self):
        """살아 있는 레일값 2개. 1.0 s 안 오면 None. open_loop 면 마지막 명령값."""
        with self._lock:
            value = self._rail_states.get()
            if value is None and self._open_loop:
                return self._rail_commanded
            return value

    def gripper_holding(self):
        with self._lock:
            return self._holding.get()

    def epoch(self):
        with self._lock:
            return self._epoch

    def set_goal_active(self, active):
        with self._lock:
            self._goal_active = bool(active)

    def goal_active(self):
        with self._lock:
            return self._goal_active

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
        """홈 자세 이내 + 움직이는 중이 아님. 관절값이 unknown 이면 None."""
        if getattr(self, '_v2_rail_fault', ''):
            return False
        feedback = getattr(self, '_module_feedback', None)
        if feedback is not None:
            if feedback.fault or self.moving():
                return False
            now = self.sim_now()
            with feedback.lock:
                if any(feedback.latest(actor) is None for actor in ('arm', 'rail')) or feedback.held() is None:
                    return None
                return not feedback.home_reason(self._home, self._rail_teach.home_rail, now)
        joints = self.joint_positions()
        if joints is None:
            return None
        if getattr(self, '_v2_rail_select', '') == 'preferred_first':
            rail, held = self.rail_positions(), self.gripper_holding()
            if rail is None or held is None:
                return None
            if held or not seq.at_pose(rail, self._rail_teach.home_rail, self._rail_tolerance):
                return False
        return seq.at_pose(joints, self._home, self._home_tolerance) and not self.moving()

    def _publish_at_home(self):
        value = self.at_home()
        if value is None:
            return
        self._at_home_pub.publish(Bool(data=value))

    # ---- 송신 ----------------------------------------------------------

    def send_joint_command(self, joints):
        """6개만 position 으로 낸다. 움직일 이유가 없거나 관절값이 stale 이거나 리셋 barrier 중이면 내지 않는다."""
        if self._closing.is_set() or self.fenced() or not self.moving():
            return False
        if self.joint_positions() is None:
            self.get_logger().warn('joint_states 가 1.0 s 없다. 관절 명령을 멈춘다.',
                                   throttle_duration_sec=1.0)
            return False
        clamped = seq.clamp(joints, self._limits)
        message = JointState()
        message.header.stamp = self.get_clock().now().to_msg()
        message.name = list(self._joint_names)
        message.position = list(clamped)
        with self._lock:
            if (getattr(self, '_module_request', False)
                    and self._fence.generation != self._module_generation):
                return False
            self._joint_command_pub.publish(message)
            self._commanded = clamped
        return True

    def send_rail_command(self, position):
        """레일 2개를 position 으로 낸다. 관절 명령과 같은 조건(종료·barrier·움직일 이유 없음·stale)이면 내지 않는다."""
        if self._rail_command_pub is None or self._closing.is_set() or self.fenced() or not self.moving():
            return False
        if self.rail_positions() is None:
            self.get_logger().warn('rail/joint_states 가 1.0 s 없다. 레일 명령을 멈춘다.',
                                   throttle_duration_sec=1.0)
            return False
        message = JointState()
        message.header.stamp = self.get_clock().now().to_msg()
        message.name = list(self._rail_joint_names)
        message.position = [float(value) for value in position]
        with self._lock:
            if (getattr(self, '_module_request', False)
                    and self._fence.generation != self._module_generation):
                return False
            self._rail_command_pub.publish(message)
            self._rail_commanded = tuple(message.position)
        return True

    def set_gripper(self, closed):
        """그리퍼 명령. true = 닫기. Isaac 쪽 구현은 simulation 레인이다. barrier·종료 중이면 안 낸다."""
        if self._closing.is_set() or self.fenced():
            return
        with self._lock:
            if (getattr(self, '_module_request', False)
                    and self._fence.generation != self._module_generation):
                return
            self._gripper_closed = bool(closed)
            self._gripper_pub.publish(Bool(data=self._gripper_closed))

    def dropped(self):
        """쥔 채로 holding 이 false 가 됐는가. unknown(None) 은 낙하로 보지 않는다."""
        return self._gripper_closed and self.gripper_holding() is False

    def publish_event(self, name, detail=''):
        """`/events`. stamp 는 sim time, epoch 는 필수다(계약 2.5절). 종료 중이면 내지 않는다."""
        if self._closing.is_set():
            return False
        message = Event()
        message.header.stamp = self.get_clock().now().to_msg()
        message.name = name
        message.robot_id = self._robot_id
        message.epoch = self.epoch()
        message.detail = detail
        with self._lock:
            if (getattr(self, '_module_request', False)
                    and self._fence.generation != self._module_generation):
                return False
            self._event_pub.publish(message)
        return True

    # ---- 동작 ----------------------------------------------------------

    def sim_now(self):
        return self.get_clock().now().nanoseconds * 1e-9

    def wait(self, sim_seconds, cancelled=None):
        """sim time 으로 기다린다. `/clock` 이 멈추면 wall 상한(계약 4절 2.0 s 의 두 배)에서 나온다."""
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

    def _limit_text(self, name, index, value, low, high):
        joint = self._joint_names[index] if index < len(self._joint_names) else f'#{index}'
        return f'{name} {joint}={value:.4f} 가 한계 [{low:.4f}, {high:.4f}] 밖이다'

    def move_to(self, target, cancelled=None, tolerance=None, through=False):
        """관절 공간 직선 경로를 궤적 점마다 낸다. 닫힌 루프면 도착까지 기다린다. 목표가 한계 밖이면 보내지 않는다.

        tolerance(rad)를 주면 도착 판정을 그 값으로 한다. 없으면 `waypoint_tolerance_rad`.
        through=True(레일 모드, 그리퍼 없이 팔 이동이 이어질 때)면 마지막 점을 낸 뒤 도착을 기다리지 않는다.
        다음 move_to 는 실제 관절값이 아니라 이 목표에서 시작한다(명령 경로가 계획의 꺾은선 그대로다).
        """
        chained, self._chained = self._chained, False
        violation = seq.limit_violation(target, self._limits)
        if violation is not None:
            self.get_logger().error(f'관절 한계 밖 목표라 보내지 않는다. {self._limit_text("target", *violation)}')
            return False
        current = self.joint_positions()
        if current is None and self._wait_fresh(self.joint_positions, 'joint_states', cancelled):
            current = self.joint_positions()
        if current is None:
            return False
        period = self._period()
        if self._rail_teach is not None:
            start = self._commanded if chained and self._commanded is not None else current
            points = self._arm_points(start, target, period)
            if not self._stream(points, self.send_joint_command, self.joint_positions, 'joint_states', cancelled):
                return False
            if through and not self._open_loop:
                self._chained = True
                return True
            return self._open_loop or self._wait_until_reached(target, cancelled, tolerance)
        for point in self._arm_points(current, target, period):
            if cancelled is not None and cancelled():
                return False
            if not self.send_joint_command(point):
                if not self._wait_fresh(self.joint_positions, 'joint_states', cancelled):
                    return False
                if not self.send_joint_command(point):
                    return False
            if not self.wait(period, cancelled):
                return False
        if self._open_loop:
            return True
        return self._wait_until_reached(target, cancelled, tolerance)

    def _period(self):
        """명령 점 간격(s). 레일 모드는 `rail_command_rate_hz`, 아니면 `command_rate_hz`(이전과 같다)."""
        rate = self._command_rate_hz if self._rail_teach is None else self._rail_command_rate
        return 1.0 / max(1.0, rate)

    def _stream(self, points, send, positions, topic, cancelled):
        """레일 모드: 궤적 점을 흐른 sim 시간에 맞춰 낸다. 점 i 는 시작 뒤 i × period 에 낼 차례다.

        /clock 은 계단으로 오른다(Isaac physics_dt 1/60 s). 예전처럼 점마다 period(0.02 s)를 기다리면 점 하나에 2틱이
        들었다(실습7-a4 명령 stamp 간격 중앙값 0.0333 s, 마클2). 궤적이 설계의 1.67배가 되어 설정 80% 가 실제로는
        최고 속도의 약 48% 였다. 여기서는 틱마다 그때 차례인 점 중 마지막 것을 낸다(스테이지는 마지막 명령을
        드라이브 목표로 쓴다). 시계가 30·60 Hz 어느 쪽이어도 전체 시간이 설계와 같다.
        상태가 끊겨 기다렸다가 이어 가면 그 점부터 시간을 다시 센다(끊긴 동안의 점을 건너뛰어 튀지 않게).
        guarded module 은 검사한 점을 생략하지 않는다. 늦은 틱에서는 다음 점 하나만 내고 그때부터 period 를
        다시 기다린다. 실제 소요시간은 계획의 이상적인 샘플 시간보다 길어질 수 있다.
        """
        if not points:
            return True
        period = self._period()
        preserve_points = getattr(self, '_module_request', False)
        last = len(points) - 1
        sent = -1
        start = self.sim_now()
        seen_sim, seen_wall = start, time.monotonic()
        while rclpy.ok():
            if self._closing.is_set() or (cancelled is not None and cancelled()):
                return False
            now = self.sim_now()
            due = min(last, int((now - start) / period + 1e-6))
            if due > sent:
                if preserve_points:
                    due = sent + 1
                if not send(points[due]):
                    if not self._wait_fresh(positions, topic, cancelled):
                        return False
                    if not send(points[due]):
                        return False
                    now = self.sim_now()
                    start = now - due * period
                    seen_sim, seen_wall = now, time.monotonic()
                if preserve_points:
                    start = self.sim_now() - due * period
                sent = due
                if sent == last:
                    return True
            if now != seen_sim:
                seen_sim, seen_wall = now, time.monotonic()
            elif time.monotonic() - seen_wall > period + 4.0:
                self.get_logger().warn('/clock 이 멈춘 것 같다. wall 상한에서 빠져나온다.')
                return False
            time.sleep(0.002)
        return False

    def _poll(self, cancelled):
        """도착·holding 확인 사이 대기. 레일 모드는 다음 sim 틱까지(예전 0.05 s = 3틱), 레일 끔은 예전처럼 0.05 s."""
        if self._rail_teach is None:
            return self.wait(0.05, cancelled)
        start_sim, start_wall = self.sim_now(), time.monotonic()
        while rclpy.ok():
            if self._closing.is_set() or (cancelled is not None and cancelled()):
                return False
            if self.sim_now() != start_sim:
                return True
            if time.monotonic() - start_wall > 4.0:
                self.get_logger().warn('/clock 이 멈춘 것 같다. wall 상한에서 빠져나온다.')
                return False
            time.sleep(0.002)
        return False

    def _arm_points(self, current, target, period):
        """팔 궤적 점. 레일 모드에 관절 속도·가속이 있으면 동기화 사다리꼴, 아니면 max_joint_speed 등속(이전과 같다).

        사다리꼴의 TCP 최고 속도(FK)가 `rail_tcp_max_speed` 를 넘으면 속도를 f, 가속을 f² 로 줄여 한 번 다시 만든다.
        같은 길을 같은 모양으로 1/f 배 시간에 가므로 TCP 속도가 정확히 f 배가 된다.
        """
        if self._rail_teach is not None and self._joint_speed_limits is not None:
            speed, accel = self._joint_speed_limits, self._joint_accel_limits
            points = seq.trapezoid_points(current, target, speed, accel, period)
            if self._tcp_model is not None:
                peak = seq.peak_speed([tuple(current)] + points, period,
                                      lambda joints: self._tcp_model.fk(joints).position_m)
                if peak > self._tcp_max_speed:
                    scale = 0.98 * self._tcp_max_speed / peak
                    points = seq.trapezoid_points(current, target, [v * scale for v in speed],
                                                  [a * scale * scale for a in accel], period)
            return points
        step = max(1e-3, self._max_joint_speed / max(1.0, self._command_rate_hz))
        return seq.interpolate(current, target, step)

    def _rail_points(self, current, target, period):
        """레일 궤적 점. 가속이 있으면 동기화 사다리꼴, 아니면 느린 축 속도로 등속."""
        if self._rail_max_accel is not None:
            return seq.trapezoid_points(current, target, self._rail_max_speed, self._rail_max_accel, period)
        return seq.interpolate(current, target, max(1e-4, min(self._rail_max_speed) * period))

    def _wait_fresh(self, positions, topic, cancelled):
        """레일 모드: 상태가 stale 이면 명령을 멈추고 `stale_grace_s`(wall) 동안 다시 오기를 기다린다.

        레일을 안 쓰면(v0) 기다리지 않는다(이전과 같다). barrier·종료·움직일 이유 없음은 기다리지 않는다.
        이미 다시 왔으면 곧바로 True 다. 늦게 온 메시지가 한꺼번에 처리되면 stale 판정 직후 곧바로 살아난다(9/18 L2).
        """
        if self._rail_teach is None or self._closing.is_set() or self.fenced() or not self.moving():
            return False
        if positions() is not None:
            return True
        self.get_logger().warn(f'{topic} 가 끊겼다. 명령을 멈추고 {self._stale_grace} s(wall) 기다린다.')
        deadline = time.monotonic() + self._stale_grace
        while time.monotonic() < deadline:
            if self._closing.is_set() or (cancelled is not None and cancelled()):
                return False
            if positions() is not None:
                self.get_logger().info(f'{topic} 가 다시 온다. 이어서 간다.')
                return True
            time.sleep(0.01)
        self.get_logger().warn(f'{topic} 가 {self._stale_grace} s 안에 돌아오지 않았다.')
        return False

    def _wait_until_reached(self, target, cancelled, tolerance=None):
        """목표 자세에 닿을 때까지 기다린다. 시한은 **상태가 오는 동안의** sim 시간만 센다.

        9/23 병원 회차(마클1·2): `joint_states 수신 공백 0.67–1.13 s(wall)` 이 이어진 뒤
        `waypoint 도착 못 함 (10.0 s sim)` → `grasp_pose: 이동 실패` 가 모듈·원통 양쪽에서 났다.
        스테이지 틱이 길어 상태가 드문드문 오면 `_stream` 도 그 틱에만 다음 점을 내므로 동작 자체가
        늘어난다. 그 공백까지 로봇의 시한으로 세면 **시뮬레이터가 느린 것을 팔 실패로 적는 것**이다.
        그래서 공백이 `state_gap_grace_s`(sim) 를 넘으면 그만큼 시한을 뒤로 민다. 수렴을 보는 눈은
        그대로다 — 상태가 정상으로 오는 동안 못 닿으면 예전처럼 실패다.

        못 닿고 끝나면 관절별 남은 차를 큰 것부터 남긴다. 값이 작으면 허용오차·정착 문제이고,
        크면 애초에 그 자세로 가지 못한 것이다.
        """
        tolerance = self._waypoint_tolerance if tolerance is None else tolerance
        start = self.sim_now()
        deadline = start + self._waypoint_timeout
        last, stalled = start, 0.0
        while self.sim_now() < deadline:
            if cancelled is not None and cancelled():
                return False
            if seq.at_pose(self.joint_positions(), target, tolerance):
                return True
            if not self._poll(cancelled):
                return False
            now = self.sim_now()
            gap = now - last
            if gap > self._state_gap_grace:
                deadline += gap
                stalled += gap
            last = now
        self.get_logger().warn(
            f'waypoint 도착 못 함 ({self._waypoint_timeout} s sim, 상태 공백 {stalled:.2f} s 는 빼고 셌다). '
            f'남은 차 {self._joint_gap(target, tolerance)}')
        return False

    def _joint_gap(self, target, tolerance):
        """목표와 지금 관절값의 차, 큰 것부터. 허용오차를 넘은 것에는 표를 단다."""
        joints = self.joint_positions()
        if joints is None or target is None or len(joints) != len(target):
            return '관절값 없음'
        names = self._joint_names if len(self._joint_names) == len(target) else range(len(target))
        rows = sorted(((abs(float(a) - float(b)), str(n), float(a) - float(b))
                       for n, a, b in zip(names, joints, target, strict=True)), reverse=True)
        return ', '.join(f'{name} {diff:+.4f}{"*" if size > tolerance else ""}' for size, name, diff in rows)

    def _fold_tolerance(self):
        return max(self._waypoint_tolerance, self._home_tolerance)

    def move_rail_to(self, target, safe_poses, cancelled=None):
        """레일을 target 으로 보간해 낸다. 팔이 접힌 자세(safe_poses)가 아니면 한 점도 내지 않고 False.

        스테이지는 명령을 드라이브 목표로 바로 넣고 보간하지 않는다(Simu). 그래서 `rail_max_speed`·`rail_max_accel` 로
        점을 촘촘히 낸다.
        닫힌 루프면 rail/joint_states 가 `rail_tolerance_m` 안에 들 때까지 `rail_timeout_s`(sim) 기다린다.
        """
        generation = self.generation()
        preferred = getattr(self, '_v2_rail_select', '') == 'preferred_first'
        original_cancelled = cancelled

        def interrupted():
            if self.fence_moved(generation) or (original_cancelled is not None and original_cancelled()):
                return True
            if preferred and not seq.arm_folded(self.joint_positions(), safe_poses, self._fold_tolerance()):
                self._hold_preferred('rail transfer lost folded arm feedback', generation)
                return True
            rail = self.rail_positions()
            if preferred and rail is not None:
                try:
                    observed = seq.check_joints('rail feedback', rail, len(target))
                    if not all(math.isfinite(value) for value in observed):
                        raise seq.RefillPlanError('non-finite rail feedback')
                except seq.RefillPlanError:
                    self._hold_preferred('invalid rail feedback', generation)
                    return True
            return False

        if preferred:
            if getattr(self, '_v2_rail_fault', '') or interrupted():
                return False
            cancelled = interrupted
        arm = self.joint_positions()
        if not seq.arm_folded(arm, safe_poses, self._fold_tolerance()):
            self.get_logger().error(f'팔이 접힌 자세(홈·{list(self._rail_teach.safe_phases)})가 아니라 '
                                    f'레일을 움직이지 않는다. 팔={None if arm is None else [round(v, 4) for v in arm]}')
            return False
        current = self.rail_positions()
        if current is None and self._wait_fresh(self.rail_positions, 'rail/joint_states', cancelled):
            current = self.rail_positions()
        if current is None:
            self.get_logger().warn('rail/joint_states 가 없어 레일을 움직이지 않는다.')
            if preferred:
                self._hold_preferred('rail feedback unavailable', generation)
            return False
        if self._rail_commanded is not None and seq.at_pose(current, self._rail_commanded, self._rail_tolerance):
            # 앞 레일 단계가 허용오차 안에 들었으면 그 목표에서 시작한다. 실제 값에서 시작하면 남은 오차(≤ 1 cm)가
            # 다음 단계에 섞여 x·y 단계에서 z 가 같이 움직인다(9/18 L2: 마지막 점 뒤 바로 도착 판정이라 5건).
            current = self._rail_commanded
        points = self._rail_points(current, target, self._period())
        if not self._stream(points, self.send_rail_command, self.rail_positions, 'rail/joint_states', cancelled):
            if preferred:
                self._hold_preferred('rail transfer interrupted', generation)
            return False
        if self._open_loop:
            return True
        deadline = self.sim_now() + self._rail_timeout
        while self.sim_now() < deadline:
            if cancelled is not None and cancelled():
                if preferred:
                    self._hold_preferred('rail arrival interrupted', generation)
                return False
            if seq.at_pose(self.rail_positions(), target, self._rail_tolerance):
                return True
            if not self._poll(cancelled):
                if preferred:
                    self._hold_preferred('rail arrival feedback interrupted', generation)
                return False
        self.get_logger().warn(f'레일 도착 못 함 ({self._rail_timeout} s sim). 목표 {list(target)} '
                                f'현재 {self.rail_positions()}')
        if preferred:
            self._hold_preferred('rail arrival timeout', generation)
        return False

    def _hold_preferred(self, reason, generation):
        """Latch an opt-in transfer fault; keep the gripper and require a reset.

        Observed positions replace outstanding drive targets when fresh. Publishing
        and generation checks share the reset lock so old goals cannot hold after reset.
        This is a commanded hold, not proof that a physical drive has stopped.
        """
        if not rclpy.ok():
            return
        with self._lock:
            if (self._fence.generation != generation or self._fence.fenced or self._closing.is_set()
                    or getattr(self, '_v2_rail_fault', '')):
                return
            self._v2_rail_fault = reason
            for states, publisher, names, attr in (
                    (self._joints, self._joint_command_pub, self._joint_names, '_commanded'),
                    (self._rail_states, self._rail_command_pub, self._rail_joint_names, '_rail_commanded')):
                position = states.get()
                if position is None or publisher is None:
                    continue
                try:
                    position = seq.check_joints('hold feedback', position, len(names))
                except seq.RefillPlanError:
                    continue
                if not all(math.isfinite(value) for value in position):
                    continue
                msg = JointState()
                msg.header.stamp = self.get_clock().now().to_msg()
                msg.name, msg.position = list(names), list(position)
                publisher.publish(msg)
                setattr(self, attr, tuple(position))
        self.get_logger().error(f'preferred_first HOLD: {reason}; reset required (gripper unchanged)')

    def _rail_home(self, stopped):
        rail = self.rail_positions()
        home = self._rail_teach.home_rail
        if rail is not None and seq.at_pose(rail, home, self._rail_tolerance):
            return True
        if rail is not None and len(home) == 3:
            # 3축(장면 v2): 계획의 레일 단계와 같은 순서로 나눈다(내려갈 때 x·y 먼저 → z).
            # 2축(#165)은 이전 그대로 한 번에.
            for step in self._v2.rail_moves('rail_home', rail, home):
                if not self.move_rail_to(step.rail, self._all_safe_poses(), cancelled=stopped):
                    return False
            return True
        return self.move_rail_to(home, self._all_safe_poses(), cancelled=stopped)

    def _all_safe_poses(self):
        teach = self._rail_teach
        return tuple(pose for letter in teach.slots for pose in seq.rail_safe_poses(teach, letter))

    def _go_home(self, joints, stopped):
        """팔(레일을 쓰면 레일도)을 홈으로. 둘 다 도착했으면 True.

        레일을 쓰면 팔 → 레일 → 팔 순서다. 팔이 접힌 자세가 아니면(단계 중간에 끊김) 지나온 팔 자세를 거꾸로 되짚어
        가장 가까운 접힌 자세로 간다. 레일이 선반 앞에 있을 때 홈 자세로 곧장 가면 팔이 선반에 닿을 수 있어서다
        (Simu 9/18: 홈 자세로 레일이 선반 쪽에 가다 베이스 y 0.48 에서 막혔다, 판단). 온 길은 한 번 지나간 길이다.
        그 뒤 레일 홈(스테이지 selfdemo 순서: retreat 자세로 레일 홈), 마지막에 팔 홈이다.
        """
        if (getattr(self, '_v2_rail_fault', '') or getattr(self, '_module_request', False)
                or (getattr(self, '_module_feedback', None) is not None and self._module_feedback.fault)):
            return False
        if self._rail_teach is None:
            return seq.at_pose(joints, self._home, self._home_tolerance) or self.move_to(self._home, cancelled=stopped)
        if not seq.arm_folded(joints, self._all_safe_poses(), self._fold_tolerance()):
            for pose, safe in reversed(self._arm_trail[:-1]):
                if not self.move_to(pose, cancelled=stopped):
                    return False
                if safe:
                    break
            else:
                self.get_logger().error('팔이 접힌 자세가 아니고 되짚을 경로가 없다. 레일·팔 홈 복귀를 하지 않는다.')
                return False
        if not self._rail_home(stopped):
            return False
        if not (seq.at_pose(self.joint_positions(), self._home, self._home_tolerance)
                or self.move_to(self._home, cancelled=stopped)):
            return False
        self._arm_trail = []
        return True

    def start_homing(self):
        """결과를 돌려준 뒤에 홈으로 간다. 그동안 at_home 은 false 다."""
        if getattr(self, '_v2_rail_fault', ''):
            return
        if getattr(self, '_module_feedback', None) is not None and self._module_feedback.fault:
            return
        self.stop_homing()
        with self._lock:
            if self._fence.fenced or self._closing.is_set():
                return               # 리셋 barrier·종료 중에는 홈으로 가지 않는다. RESET_DONE 뒤 on_reset 이 다시 본다
            self._homing = True
            self._homing_cancelled = False
            generation = self._fence.generation
        self._homing_thread = threading.Thread(target=self._home_worker, args=(generation,), daemon=True)
        self._homing_thread.start()

    def _home_worker(self, generation=None):
        generation = self.generation() if generation is None else generation

        def stopped():
            return self._homing_stopped() or self.fence_moved(generation)

        try:
            joints = self._wait_for_joints(stopped)
            if joints is None:
                return
            if self._go_home(joints, stopped):
                with self._lock:
                    self._left_home = False
        finally:
            with self._lock:
                self._homing = False

    def _wait_for_joints(self, cancelled):
        """리셋 직후엔 캐시가 비어 있다. joint_states 한 주기를 wall 1.0 s 까지 기다린다(계약 2.1절)."""
        deadline = time.monotonic() + STALE_JOINTS_S
        while rclpy.ok() and not cancelled() and not self._closing.is_set():
            joints = self.joint_positions()
            if joints is not None or time.monotonic() > deadline:
                return joints
            time.sleep(0.01)
        return None

    def _homing_stopped(self):
        with self._lock:
            return self._homing_cancelled or self._closing.is_set()

    def stop_homing(self, limit_s=2.0):
        with self._lock:
            self._homing_cancelled = True
            thread = self._homing_thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(limit_s)

    # ---- Refill 서버 ---------------------------------------------------

    def _accept_refill(self, goal):
        """goal 형식 검사. 슬롯 값과 item_id 만 본다."""
        if getattr(self, '_v2_rail_fault', ''):
            self.get_logger().warn(f'preferred_first HOLD: {self._v2_rail_fault}; reset required')
            return GoalResponse.REJECT
        if getattr(self, '_module_feedback', None) is not None and self._module_feedback.fault:
            self.get_logger().warn(f'guarded module HOLD: {self._module_feedback.fault}')
            return GoalResponse.REJECT
        if not goal.item_id:
            self.get_logger().warn('Refill goal 에 item_id 가 없다. 거부한다.')
            return GoalResponse.REJECT
        try:
            seq.slot_letter(goal.slot)
        except seq.RefillPlanError as error:
            self.get_logger().warn(f'Refill goal 거부: {error}')
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

    def _execute_refill(self, goal_handle):
        """`Refill` 실행. 성공·실패는 홈에 돌아온 뒤 결과를 내고, 취소는 결과를 낸 뒤 홈으로 간다."""
        self.stop_homing()
        self._preferred_executing = False
        self._module_request = False  # set only when the guarded executor is entered
        self._module_preflight = getattr(self, '_module_feedback', None) is not None and self._scene_v2
        self.set_goal_active(True)
        with self._lock:
            left_home_before = self._left_home
            self._left_home = True
            generation = self._fence.generation
            self._module_generation = generation
        result = Refill.Result()
        try:
            status, detail, lot_id = self._run_refill(goal_handle, generation)
            if status != STATUS_OK and self._preferred_executing:
                self._hold_preferred(f'refill {status}: {detail}', generation)
            self._chained = False
            # Guarded preflight has sent no commands; guarded execution owns its
            # checked return/hold. Legacy requests retain their original recovery.
            if status != STATUS_CANCELLED and not self._module_preflight and not self._module_request:
                self._return_home(generation)
            self._log_phase_times(goal_handle.request.item_id, status)
            result.success = status == STATUS_OK
            result.lot_id = lot_id
            item = goal_handle.request.item_id
            if status == STATUS_CANCELLED:
                self.get_logger().info(f'Refill {item}: 취소됨. {detail}')
                self._end_goal(goal_handle, 'canceled')
            elif status == STATUS_OK:
                self._end_goal(goal_handle, 'succeed')
            else:
                if not (self._closing.is_set() or not rclpy.ok()):
                    self.get_logger().warn(f'Refill {item}: 실패. {detail}')
                self._end_goal(goal_handle, 'abort')
            return result
        finally:
            if self._module_preflight:
                with self._lock:
                    self._left_home = left_home_before
            with self._lock:
                if (getattr(self, '_module_request', False) and self._left_home
                        and self._fence.generation == generation):
                    self._module_feedback.fault = (self._module_feedback.fault
                                                   or 'module task ended away from verified home; reset required')
            self.set_goal_active(False)
            # 아직 홈이 아니면(취소, 결과 전 복귀 실패, 예외) 결과를 낸 뒤 홈으로 간다. 취소 뒤 리셋 전까지
            # 홈 밖에서 at_home=false 로 머물지 않으려고다. isaac 리셋(계약 6절 2)과는 별개다.
            # 리셋 barrier 를 지난 goal 은 여기서 복귀하지 않는다. RESET_DONE 뒤 on_reset 이 복귀한다.
            with self._lock:
                left_home = self._left_home
            if (left_home and not self._module_preflight and not self._module_request
                    and not self.fence_moved(generation)):
                self.start_homing()

    def _return_home(self, generation):
        """결과를 내기 전에 홈으로 간다. 도착했으면 True. goal 이 활성인 채라 그동안 at_home 은 false 다.

        리셋 barrier 를 지났으면 가지 않는다(RESET_DONE 뒤 on_reset 이 간다). 도착하지 못해도 보충 결과는 바꾸지 않는다
        (장착은 이미 끝났다). 로그를 남기고 결과 뒤 finally 가 한 번 더 복귀를 시도한다.
        """
        def stopped():
            return self.fence_moved(generation) or self._closing.is_set() or not rclpy.ok()

        if stopped() or self.fenced():
            return False
        joints = self._wait_for_joints(stopped)
        if joints is not None and self._go_home(joints, stopped):
            with self._lock:
                self._left_home = False
            return True
        if not stopped():
            if getattr(self, '_preferred_executing', False):
                self._hold_preferred('return home failed', generation)
            self.get_logger().warn('결과 전 홈 복귀를 못 했다. 결과를 낸 뒤 다시 복귀한다.')
        return False

    def _log_phase_times(self, item, status):
        """레일 모드: 단계별 sim 시간 한 줄(실습7-a4·7-b 에는 단계 시각 기록이 없어 시간을 나누지 못했다)."""
        marks, self._phase_marks = self._phase_marks, []
        if self._rail_teach is None or not marks:
            return
        end = self.sim_now()
        spans = [(phase, (marks[i + 1][1] if i + 1 < len(marks) else end) - at)
                 for i, (phase, at) in enumerate(marks)]
        text = ', '.join(f'{phase.split()[0]} {seconds:.2f}' for phase, seconds in spans)
        self.get_logger().info(f'Refill {item} 단계 시간(sim s, 마지막은 결과 전 복귀 포함, {status}): {text}. '
                               f'합 {end - marks[0][1]:.2f}')

    def _publish_feedback(self, goal_handle, phase):
        self._phase_marks.append((phase, self.sim_now()))
        feedback = Refill.Feedback()
        feedback.phase = phase
        goal_handle.publish_feedback(feedback)

    def _run_refill(self, goal_handle, generation=None):
        """한 번의 보충. 반환은 (status, detail, lot_id)."""
        self._phase_marks = []
        self._read_container = ''
        goal = goal_handle.request
        deadline = self.sim_now() + self._refill_timeout
        generation = self.generation() if generation is None else generation
        if self.fence_moved(generation) or self.fenced():
            return STATUS_FAILED, '리셋 barrier', ''

        def cancelled():
            return (goal_handle.is_cancel_requested or self.fence_moved(generation) or self._closing.is_set()
                    or self.sim_now() > deadline)

        letter = seq.slot_letter(goal.slot)
        if self._scene_v2:
            failure = self._run_v2(goal_handle, deadline, cancelled)
        elif self._rail_teach is None:
            failure = self._run_fixed_steps(goal_handle, deadline, cancelled)
        else:
            failure = self._run_rail_steps(goal_handle, letter, deadline, cancelled)
        if failure is not None:
            return failure

        # lot 은 지어내지 않는다. goal 에 lot 이 있으면 그대로 되돌리고 없으면 빈 값이다(계약 2.1절 끝).
        # 약통 확인을 켰으면 읽고 허용된 약통 ID 를 싣는다(계약 2.3, 기록용).
        lot_id = str(getattr(goal, 'lot_id', '') or '') or getattr(self, '_read_container', '')
        detail = f'{goal.item_id} slot {letter}' + (f' lot {lot_id}' if lot_id else '')
        if self._scene_v2 and self._v2_done is not None:
            # 장면 v2: compact JSON 한 줄(작전 9/18 결정, 계약 2.6절: detail 은 판정에 안 쓰는 메모).
            # v1 은 위 문자열 그대로.
            detail = self._v2.refill_done_detail(lot=lot_id, **self._v2_done)
        if getattr(self, '_module_request', False) and cancelled():
            return self._stopped(goal_handle, deadline, 'module completion interrupted before REFILL_DONE')
        published = self.publish_event(Event.REFILL_DONE, detail=detail)
        if getattr(self, '_module_request', False) and not published:
            return STATUS_FAILED, 'module completion event was blocked', ''
        return STATUS_OK, '', lot_id

    def _run_fixed_steps(self, goal_handle, deadline, cancelled):
        """레일 없는 고정 받침(v0): 티칭 waypoint 여섯 단계. 끝까지 가면 None, 아니면 (status, detail, lot_id)."""
        goal = goal_handle.request
        steps = seq.plan_refill(goal.slot, self._poses)
        violation = seq.plan_limit_violation(goal.slot, self._poses, self._home, self._limits)
        if violation is not None:
            # 한계 밖 waypoint 는 자르지 않고 보내기 전에 거부한다. 한 관절도 움직이지 않는다.
            detail = self._limit_text(*violation)
            self.get_logger().error(f'Refill {goal.item_id}: 관절 한계 밖이라 보내지 않는다. {detail}')
            return STATUS_FAILED, detail, ''
        # 시작에 그리퍼를 한 번 연다. 쥔 채 종료·재기동 뒤일 수 있다. 이미 열려 있으면 무해하다.
        self.set_gripper(False)
        for step in steps:
            self._publish_feedback(goal_handle, step.phase)
            if not self.move_to(step.joints, cancelled):
                return self._stopped(goal_handle, deadline, f'{step.phase}: 이동 실패')
            # 여는 단계(insert)도 이송이다. 열기 전에 봐야 떨어뜨린 채 REFILL_DONE 을 내지 않는다.
            if step.phase in seq.CARRYING_PHASES and self.dropped():
                return STATUS_FAILED, f'{step.phase}: 이송 중 holding false (낙하)', ''
            failure = self._apply_gripper(goal_handle, step, deadline, cancelled)
            if failure is not None:
                return failure
        return None

    def _run_v2(self, goal_handle, deadline, cancelled):
        """장면 v2: item → 종류 → 칸 랜덤 → IK 계획(여유 최대) → 레일 단계 실행. 모자란 칸은 건너뛴다.

        slot 은 수납 위치를 정하지 않는다(종류가 정한다, Simu 합의). 결과·로그에만 남긴다.
        """
        goal = goal_handle.request
        with self._lock:
            scene = self._scene
        if (getattr(self, '_module_feedback', None) is not None
                and not getattr(self, '_module_inventory_valid', True)):
            return STATUS_FAILED, '유효한 inventory 를 아직 못 받았다', ''
        if scene is None:
            return STATUS_FAILED, 'inventory 를 아직 못 받았다', ''
        if list(scene.rail_names) != self._rail_joint_names:
            return STATUS_FAILED, f'레일 이름이 다르다(inventory {list(scene.rail_names)})', ''
        kind = self._v2.kind_of(scene, goal.item_id)
        if kind is None:
            return STATUS_FAILED, f'{goal.item_id} 의 약통 종류를 inventory 에서 못 찾았다', ''
        # 캐시가 이미 "계획 없음" 으로 안 칸은 처음부터 고르지 않는다(건너뛰기 횟수를 쓰지 않게).
        with self._v2_cache_lock:
            known_bad = [c.cell_id for c in scene.cells
                         if (entry := self._v2_cache.get(scene, c)) is not None and entry.steps is None]
        with self._lock:
            epoch = self._epoch
        refused_cells = getattr(self, '_refused_cells', None)
        refused = [c for c in (refused_cells.of(epoch) if refused_cells else []) if c not in known_bad]
        skipped = list(known_bad) + refused
        for _ in range(self._v2_max_skips + 1):
            if cancelled():
                return self._stopped(goal_handle, deadline, 'plan: 시작 전 중단')
            cell, choice = self._v2_picker.choose(scene.cells, kind, goal.item_id, skipped)
            self.get_logger().info(f'Refill {goal.item_id}: 칸 선택 seed={choice.seed} draw={choice.draw} '
                                   f'kind={kind} cell={choice.cell_id} 후보 {choice.candidates} slot={goal.slot}')
            if cell is None:
                break
            started = time.monotonic()
            entry, cached = self._plan_cell(scene, cell)
            source = '캐시' if cached else f'계산 {entry.seconds:.1f} s'
            if entry.steps is None:
                self.get_logger().warn(f'Refill {goal.item_id}: 칸 {cell.cell_id} 건너뜀 — {entry.why} ({source})')
                skipped.append(cell.cell_id)
                continue
            guarded = getattr(self, '_module_feedback', None) is not None and cell.kind == 'module'
            if guarded:
                steps = entry.steps.segments
            else:
                steps = seq.validate_plan(entry.steps, self._home, V2_SAFE_PHASES, 3)
                self._rail_teach.slots['plan'] = steps
            self.get_logger().info(f'Refill {goal.item_id}: 칸 {cell.cell_id} 계획 {len(steps)}단계, {entry.why} '
                                   f'({source}, 고르기까지 {time.monotonic() - started:.2f} s)')
            target = scene.targets[kind].kind
            self._v2_done = {'item': goal.item_id, 'slot': seq.slot_letter(goal.slot), 'kind': kind,
                             'cell': cell.cell_id, 'target': target, 'seed': choice.seed, 'draw': choice.draw,
                             'clearance': entry.clearance}
            self._publish_feedback(goal_handle, f'plan cell={cell.cell_id} kind={kind} seed={choice.seed} '
                                                f'draw={choice.draw}')
            if cancelled():
                return self._stopped(goal_handle, deadline, 'plan: 계산 중 취소·리셋·시한 초과')
            if (getattr(self, '_module_feedback', None) is not None
                    and not self._module_inventory_valid):
                return STATUS_FAILED, '계획 중 inventory 유효성이 바뀌었다', ''
            if guarded:
                from rokey_p3_manipulation.module_execution import execute, hold
                minimum = entry.steps.seconds + .2 * sum(s.actor in ('arm', 'rail') for s in steps)
                if self.sim_now() + minimum >= deadline:
                    return STATUS_FAILED, f'guarded module needs at least {minimum:.2f}s before sensor waits', ''
                generation = self._module_generation

                def superseded(generation=generation):
                    return self.fence_moved(generation)

                with self._module_feedback.lock:
                    revision = self._module_feedback.revision
                self._module_preflight, self._module_request = False, True
                failure = execute(entry.steps, self, self._module_feedback, cancelled, goal_handle, superseded)
                if failure is not None:
                    return self._stopped(goal_handle, deadline, failure)
                failure = self._module_feedback.home_reason(self._home, self._rail_teach.home_rail, self.sim_now())
                if failure:
                    return self._stopped(goal_handle, deadline,
                                         hold(self, self._module_feedback, failure, superseded, revision))
                with self._lock:
                    if self._fence.generation != generation:
                        return STATUS_FAILED, 'module execution superseded by reset', ''
                    self._left_home = False  # fresh unloaded arm AND rail home observations confirmed
                return None
            self._module_preflight = False
            return self._run_rail_steps(goal_handle, 'plan', deadline, cancelled)
        return (STATUS_FAILED, f'{kind} 칸을 찾지 못했다(건너뜀 {skipped[len(known_bad):]}, 계획 없는 칸 {known_bad})',
                '')

    def _run_rail_steps(self, goal_handle, letter, deadline, cancelled):
        """레일 위 M0609: teach 파일의 단계를 순서대로. 끝까지 가면 None, 아니면 (status, detail, lot_id).

        레일 단계는 팔이 접힌 자세일 때만 명령한다(`move_rail_to`). 레일 시한 초과·도착 실패는 팔 이동 실패와
        같이 `success=false` 다. 그리퍼가 닫혀 있는 동안(잡기 뒤, 놓기 전)은 매 단계 뒤 낙하를 본다.
        """
        teach = self._rail_teach
        self._preferred_executing = getattr(self, '_v2_rail_select', '') == 'preferred_first'
        if self._preferred_executing and (
                not seq.at_pose(self.joint_positions(), teach.home_joints, self._home_tolerance)
                or not seq.at_pose(self.rail_positions(), teach.home_rail, self._rail_tolerance)
                or self.gripper_holding() is not False):
            return STATUS_FAILED, 'preferred_first requires fresh unloaded arm and rail home', ''
        item = goal_handle.request.item_id
        for name, joints in seq.rail_arm_targets(teach, letter):
            violation = seq.limit_violation(joints, self._limits)
            if violation is not None:
                detail = self._limit_text(name, *violation)
                self.get_logger().error(f'Refill {item}: 관절 한계 밖이라 보내지 않는다. {detail}')
                return STATUS_FAILED, detail, ''
        safe = seq.rail_safe_poses(teach, letter)
        self._arm_trail = [(teach.home_joints, True)]
        rail_target = teach.home_rail
        self.set_gripper(False)
        steps = teach.slots[letter]
        for index, step in enumerate(steps):
            if cancelled():
                # 그리퍼만 바꾸는 단계(grasp·release)는 이동이 없어 취소를 못 본다. 닫기 전에 멈춘다.
                return self._stopped(goal_handle, deadline, f'{step.phase}: 시작 전 중단')
            if getattr(self, '_container_check', False) and step.gripper == seq.GRIP_CLOSE and self._scene_v2:
                # 잡기 직전(grasp_pose 도착 뒤). 거부면 닫지 않고 끝낸다(계약 2.3).
                failure = self._check_container(goal_handle, deadline, cancelled)
                if failure is not None:
                    return failure
            self._publish_feedback(goal_handle, step.phase)
            if step.rail is not None:
                if not self.move_rail_to(step.rail, safe, cancelled):
                    return self._stopped(goal_handle, deadline, f'{step.phase}: 레일 이동 실패')
                # 레일 단계 직전 팔 자세는 늘 접힌 자세다(load_rail_teach 가 검사). 되짚기는 레일 이동을 건너지 않는다.
                rail_target = step.rail
            elif step.joints is not None:
                self._arm_trail.append((step.joints, step.phase in teach.safe_phases))
                # 그리퍼 없이 팔 이동이 이어지면 중간 도착을 기다리지 않는다. 잡기·놓기·레일 앞, 단계의 마지막,
                # 자기 허용오차가 있는 점(v1 투입구 0.0025 rad)은 기다린다.
                following = steps[index + 1] if index + 1 < len(steps) else None
                through = (step.gripper is None and step.tolerance is None
                           and following is not None and following.joints is not None)
                if not self.move_to(step.joints, cancelled, step.tolerance, through=through):
                    return self._stopped(goal_handle, deadline, f'{step.phase}: 이동 실패')
                self._warn_rail_drift(step.phase, rail_target)
            if self.dropped():
                return STATUS_FAILED, f'{step.phase}: 이송 중 holding false (낙하)', ''
            failure = self._apply_gripper(goal_handle, step, deadline, cancelled)
            if failure is not None:
                return failure
        return None

    def _warn_rail_drift(self, phase, rail_target):
        """팔이 도착했을 때 레일이 목표에서 `rail_tolerance_m` 넘게 밀려 있으면 WARN 한 줄. 실패로 보지는 않는다.

        스테이지 selfdemo 에서 투입구 insert 동안 레일이 rail_y 하한까지 밀렸다(Simu 9/18, 레일 드라이브가 팔보다 약함).
        그러면 팔 관절이 맞아도 TCP 가 어긋난다. 원인을 로그로 남긴다.
        """
        rail = self.rail_positions()
        if rail is not None and not seq.at_pose(rail, rail_target, self._rail_tolerance):
            self.get_logger().warn(f'{phase}: 레일이 밀려 있다. 목표 {list(rail_target)} 현재 '
                                   f'{[round(value, 4) for value in rail]} (허용 {self._rail_tolerance} m)')

    def _apply_gripper(self, goal_handle, step, deadline, cancelled):
        """단계 끝의 그리퍼. 닫으면 settle 뒤 holding 을 기다리고, 열면 settle 만. 문제없으면 None."""
        if step.gripper == seq.GRIP_CLOSE:
            self.set_gripper(True)
            if not self.wait(self._grasp_settle, cancelled):
                return self._stopped(goal_handle, deadline, f'{step.phase}: settle 중단')
            if not self._wait_for_hold(cancelled):
                return self._stopped(goal_handle, deadline,
                                     f'{step.phase}: holding 이 {self._hold_timeout} s 안에 true 가 되지 않았다')
        elif step.gripper == seq.GRIP_OPEN:
            self.set_gripper(False)
            if not self.wait(self._release_settle, cancelled):
                return self._stopped(goal_handle, deadline, f'{step.phase}: settle 중단')
        return None

    def _wait_for_hold(self, cancelled):
        """닫은 뒤 holding 이 true 가 될 때까지. open_loop 면 묻지 않는다."""
        if self._open_loop:
            return True
        deadline = self.sim_now() + self._hold_timeout
        while self.sim_now() < deadline:
            if cancelled():
                return False
            if self.gripper_holding() is True:
                return True
            if not self._poll(cancelled):
                return False
        return False

    def _stopped(self, goal_handle, deadline, detail):
        """이동·대기가 중단된 이유를 status 로 나눈다."""
        if self._closing.is_set() or not rclpy.ok():
            # 종료는 리셋이 아니다(#111). 이벤트 없이 abort 한다. 캐니스터를 쥔 채일 수 있지만 그리퍼를 열지 않는다.
            self.get_logger().info(f'Refill {goal_handle.request.item_id}: 노드 종료(shutdown). abort 한다. '
                                   f'그리퍼는 그대로 둔다(closed={self._gripper_closed}).')
            return STATUS_FAILED, f'shutdown. {detail}', ''
        if goal_handle.is_cancel_requested:
            return STATUS_CANCELLED, detail, ''
        if self.fenced():
            return STATUS_FAILED, f'리셋 barrier. {detail}', ''
        if self.sim_now() > deadline:
            return STATUS_FAILED, f'timeout {self._refill_timeout} s sim. {detail}', ''
        return STATUS_FAILED, detail, ''

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
        """종료 경로. 보충·홈 복귀가 멈추고 관절·그리퍼 명령·이벤트를 더 내지 않는다. 여러 번 불러도 된다."""
        self._closing.set()
        # 이중 SIGINT 로 대기 중 KeyboardInterrupt 가 나도 플래그는 이미 켜져 루프가 곧 멈춘다. traceback 없이 넘긴다.
        with contextlib.suppress(KeyboardInterrupt):
            self.stop_homing()

    def _spin_states(self):
        """레일 모드 상태 구독 전용 스레드. 종료(context 내려감·executor shutdown)면 조용히 끝난다."""
        with contextlib.suppress(Exception):
            self._state_executor.spin()

    def destroy_node(self):
        self.close()
        if self._state_executor is not None:
            self._state_executor.shutdown(timeout_sec=1.0)
            self._state_node.destroy_node()
        return super().destroy_node()


def main(args=None):
    """콘솔 진입점. 액션 실행이 상태 수신을 막지 않게 멀티스레드로 돈다."""
    rclpy.init(args=args)
    node = M0609ArmNode()
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
