"""트립 FSM. ADR 0001 의 표를 순수 Python 으로 옮긴 것이다. ROS 를 import 하지 않는다.

노드는 액션 결과·상태 토픽·태그 판독·타이머 tick 을 입력으로 넣고, 돌려받은 **명령 목록**을
순서대로 실행한다. 상태·전이·이벤트·guard 는 전부 여기 있고 노드에는 배선만 있다.

ADR 의 입력 집합을 그대로 쓴다. 액션 goal 의 수락·거부도 `result` 로 들어오고 outcome 이
`accepted` 와 `rejected` 다. 서비스(`dispense`, `reset`)의 응답도 같은 입력으로 들어온다.

이벤트 순서는 계약 2.6절의 한 바퀴와 같아야 한다. 두 곳은 ADR 의 표를 그 순서에 맞춘 것이다.

- `LOAD_DONE` 은 `DOCKED_LOAD` 를 떠날 때 내고 팔의 `ARM_HOME` 은 그 뒤에 온다.
- `DEPARTED` 와 `RETURNED` 는 "주행 시작"이라 `GoToZone` goal 이 수락된 순간에 낸다.
  `RETURNED` 를 `NEXT_STOP` 전이에서 내면 `ORDER_DONE` 다음에 와야 할 `ARM_HOME` 을 앞지른다.

goal·서비스 호출마다 `Token(epoch, owner, seq)` 을 붙인다. `result`·`feedback` 은 token 을 받아 지금 기다리는
것과 다르면 버린다. 같은 epoch 안에서도 이전 goal 의 늦은 수락·결과가 현재 상태를 바꾸지 못한다.
시한이나 트립 제한으로 goal 을 cancel 하면 그 token 이 종결될 때까지(또는 cancel_wait_s wall) 대체 goal 을
보내지 않는다. token 을 안 주면(None) 지금 기다리는 것의 결과로 본다(ROS 없는 표 테스트용).

리셋 barrier(계약 6절, v2)는 RESETTING 안의 하위 단계다. FSM 은 시계를 갖지 않고 `tick(now_sim, now_wall)` 의
wall 로 상한을 잰다(sim 이 멈춰도 상한이 돈다).

1. 끊긴 주문을 이전 epoch·이전 request_id·같은 stamp 로 ABORT(`reset_interrupted`)·ORDER_DONE. Deliver 결과는 한 번.
2. epoch +1, `RESET_BEGIN`(새 epoch).
3. drain: 활성 goal 전부 Cancel, 종결을 기다린다(`cancel_wait_s` wall). 넘으면 진행하고 `RESET_DONE.detail` 에 남긴다.
4. reset_wait: `Call(RESET)`. `reset_timeout_s` wall 안에 ok 면 재고 다시 읽기(`ReloadStores`)·`RESET_DONE`.
   false·예외·시한 초과면 failed: Deliver 거부 유지, `RESET_DONE` 없음, 자동 재시도 없음.
   새 리셋 요청은 새 epoch 로 다시 시작한다.
진행 중 barrier(drain·reset_wait)에 온 리셋 요청은 합류한다(epoch·상한 그대로).
"""

import json
import math
from dataclasses import dataclass, field

from rokey_p3_orchestrator.order_pool import patient_tag_id, station_tag_id
from rokey_p3_orchestrator.terminal_states import ABORT, HOLD_RETURN, TIMEOUT

# 트립 상태 (ADR 0001 트립 상태 절)
IDLE = 'IDLE'
DISPATCHING = 'DISPATCHING'
DOCKED_LOAD = 'DOCKED_LOAD'
WAIT_BELT = 'WAIT_BELT'
PICKING_BELT = 'PICKING_BELT'
DEPARTING = 'DEPARTING'
TRANSIT = 'TRANSIT'
AUTHENTICATING = 'AUTHENTICATING'
DELIVERING = 'DELIVERING'
NEXT_STOP = 'NEXT_STOP'
RETURNING = 'RETURNING'
RESETTING = 'RESETTING'

#: **AMR 이 조제실을 떠나 배송 중인** 상태들. `refill_overlap` 이 "보충이 배송과 겹쳤나" 를 이걸로 답한다.
#:
#: `IDLE` 이 아닌 것과 같지 않다. `DOCKED_LOAD`·`WAIT_BELT`·`PICKING_BELT` 는 트립이 있지만 AMR 이
#: **조제실에 서 있는** 상태라 보충과 겹쳐도 배송이 늦어지지 않는다. `RETURNING`·`RESETTING` 도 배송이
#: 끝난 뒤다. 카드가 묻는 것은 "보충하는 동안 배송이 돌았나" 이므로 그 넷만 센다.
DELIVERY_STATES = (TRANSIT, AUTHENTICATING, DELIVERING, NEXT_STOP)

# 액션·서비스. 계약 2절의 이름에서 네임스페이스를 뺀 것이고 노드가 다시 붙인다.
GO_TO_ZONE = 'go_to_zone'
PICK_POUCH = 'pick_pouch'
SCAN_TAG = 'scan_tag'
DISPENSE = 'dispense'
RESET = 'reset'

# 상태 토픽 (계약 5절 guard)
AT_HOME = 'at_home'
BASE_STOPPED = 'base_stopped'
BELT = 'belt'
HOLDING = 'holding'
# 계약 11.6 관측(opt-in, TripConfig.observation_guard). 값은 dict 이고 신선도는 노드가 seq 증가로 판정한다.
BELT_OBSERVATION = 'belt_observation'
ARM_CLEARANCE = 'arm_clearance'
# 위 관측의 enum 정수값. BeltObservation.msg·ArmClearance.msg 와 같다(FSM 은 ROS 를 import 하지 않는다).
OCCUPANCY_EMPTY = 1
ZONE_END = 2
MOTION_STOPPED = 2
APPLIED_STOP = 2
CLEARANCE_CLEAR = 1

# outcome. PickPouch 일곱 개는 계약 2.3절, 나머지는 노드가 붙인다.
ACCEPTED = 'accepted'
REJECTED = 'rejected'
OK = 'ok'
ARRIVED = 'arrived'
NOT_ARRIVED = 'not_arrived'
UNREADABLE = 'unreadable'
DROPPED = 'dropped'
TIMED_OUT = 'timeout'
CANCELED = 'canceled'          # 노드가 액션 wrapper status 가 CANCELED 일 때 넣는다
FAILED = 'failed'              # 서비스 응답 false·예외·서버 없음

OWNER_TRIP = 'trip'

# 주문 상태. 앞 넷은 오케스트레이터의 주장, 뒤 셋은 종료 상태다(ADR 주문 상태 절).
ORDER_ACCEPTED = 'ACCEPTED'
ORDER_DISPENSED = 'DISPENSED'
ORDER_LOADED = 'LOADED'
ORDER_DELIVERED = 'DELIVERED'
_TERMINAL = (HOLD_RETURN, ABORT, TIMEOUT, ORDER_DELIVERED)

# 이벤트 이름. Event.msg 의 상수와 같은 문자열이다.
EVENT_REQUEST_ACCEPTED = 'REQUEST_ACCEPTED'
EVENT_AMR_DOCKED_LOAD = 'AMR_DOCKED_LOAD'
EVENT_LOAD_DONE = 'LOAD_DONE'
EVENT_DEPARTED = 'DEPARTED'
EVENT_ARRIVING = 'ARRIVING'
EVENT_ARRIVED = 'ARRIVED'
EVENT_AUTH_OK = 'AUTH_OK'
EVENT_AUTH_FAIL = 'AUTH_FAIL'
EVENT_CABINET_LOCKED = 'CABINET_LOCKED'
EVENT_ORDER_DONE = 'ORDER_DONE'
EVENT_RETURNED = 'RETURNED'
EVENT_DOCKED = 'DOCKED'
EVENT_RESET_DONE = 'RESET_DONE'
EVENT_RESET_BEGIN = 'RESET_BEGIN'

# 조제기 이벤트(DISPENSER_PAUSED·DISPENSER_RESUMED·REFILL_REQUESTED)의 Event.robot_id.
ROBOT_DISPENSER = 'dispenser'

MODE_SINGLE = 'single'
MODE_URGENT = 'urgent'
MODE_BATCH_ROOM = 'batch_room'
MODE_BATCH_WARD = 'batch_ward'
#: DeliveryRequest.msg 의 mode 상수 값. REQUEST_ACCEPTED detail 에 숫자로 싣는다.
MODE_VALUES = {MODE_SINGLE: 0, MODE_URGENT: 1, MODE_BATCH_ROOM: 2, MODE_BATCH_WARD: 3}

KIND_PATIENT = 'patient'
KIND_STATION = 'station'

SOURCE_BELT = 'BELT'
SOURCE_DECK = 'DECK'

REASON_PHARMACY_ONLY = 'pharmacy_only'
REASON_RESET_INTERRUPTED = 'reset_interrupted'
DETAIL_DRAIN_TIMEOUT = 'drain_timeout'

# 리셋 barrier 하위 단계
BARRIER_DRAIN = 'drain'
BARRIER_RESET_WAIT = 'reset_wait'
BARRIER_FAILED = 'failed'


@dataclass(frozen=True)
class TripConfig:
    """값은 계약 7절. 노드가 파라미터로 덮어쓴다."""

    load_zone: str = 'load'
    dock_zone: str = 'dock_1'
    # 적재 자리가 곧 도크다(병원, 재범 9/29 "도크에서 AMR 이 이동하지 않고 그 자리에서 바로 파지" B안).
    # 참이면 도크에 서 있을 때 적재 자리로 가는 GoToZone 을 보내지 않고 곧바로 DOCKED_LOAD 다.
    # 노드가 zones 파일에서 두 zone 자세가 같은지 보고 정한다(`load_is_dock`). 빈월드는 거짓(0.94 m 떨어져 있다).
    load_at_dock: bool = False
    dispense_while_dispatching: bool = False
    deck_slots: int = 5
    arriving_distance_m: float = 3.0
    goto_timeout_load_s: float = 120.0
    goto_timeout_ward_s: float = 180.0
    pick_timeout_s: float = 60.0
    scan_timeout_s: float = 30.0
    belt_timeout_s: float = 20.0
    goto_retry_delay_s: float = 5.0
    goto_max_rejects: int = 2
    # 도크 복귀가 **거부가 아니라 실패**(도착 못 함·시한·서버 오류)로 끝나면 다시 보낸다. 간격은 두 배씩(10·20·40 s).
    # 회차133(85b583c, #240 5848721883): 복귀 Nav2 목표가 ABORTED 로 끝나자 트립이 도크 밖에서 닫혔고, 다음 주문이
    # 없어 AMR 이 600 s 넘게 그 자리에 섰다. 고른 값이다.
    return_max_retries: int = 3
    return_retry_delay_s: float = 10.0
    dispense_retry_delay_s: float = 2.0
    dispense_max_calls: int = 3
    pick_max_attempts: int = 2
    scan_max_attempts: int = 2
    trip_limit_s: float = 600.0
    # 조제실 구간만 돈다(일정 P2, 1차 시연). 적재 뒤 정거장으로 가지 않고 도크로 복귀하고,
    # 실은 주문은 HOLD_RETURN(reason pharmacy_only) 으로 닫는다. 봉투가 상판에 남은 채 복귀한 것이 사실이다.
    pharmacy_only: bool = False
    # 계약 11.3·11.6 의 관측 guard(opt-in, 시험용). 켜면 기존 조건에 더해
    # 피킹: /pharmacy/belt/observation 이 이 주문의 봉투를 종단 구역(END)에서 정착(STOPPED)·STOP 적용으로 말할 때만,
    # 다음 배출: 같은 관측이 빈 벨트(EMPTY)이고 팔 통로 관측이 CLEAR 이고 이 트립의 앞 벨트 픽이 ok 일 때만.
    # 관측이 없거나 신선하지 않거나 다른 epoch 면 허가하지 않는다(fail-closed). 칸 안착 확인(11.4)은 아직 없다.
    observation_guard: bool = False
    # cancel 한 goal 이 종결될 때까지 대체 goal 을 보내지 않는 상한(wall). 계약 6절 1 의 cancel 대기와 같은 값이다.
    cancel_wait_s: float = 10.0
    # /sim/reset 응답을 기다리는 상한(wall). 서버 탐색 대기도 이 안이다. 계약 7절 Reset 30 s.
    reset_timeout_s: float = 30.0


#: 두 zone 이 "같은 자리" 인 한도(m·rad). zones 파일은 mm 로 적힌다.
SAME_POSE_M = 0.005
SAME_POSE_RAD = 0.01


def load_is_dock(zones_doc, load_zone, dock_zone):
    """zones 파일에서 적재 zone 과 도크 zone 이 같은 자세인가. 둘 중 하나라도 없으면 거짓(예전 동작)."""
    zones = (zones_doc or {}).get('zones') or {}
    load, dock = zones.get(load_zone), zones.get(dock_zone)
    if not (isinstance(load, dict) and isinstance(dock, dict)):
        return False
    try:
        return (math.hypot(float(load['x']) - float(dock['x']), float(load['y']) - float(dock['y'])) <= SAME_POSE_M
                and abs(math.remainder(float(load['yaw']) - float(dock['yaw']), math.tau)) <= SAME_POSE_RAD)
    except (KeyError, TypeError, ValueError):
        return False


def zone_maps(zones_doc):
    """zones 파일(계약 3절 형식) → TripFsm 키워드 {zone_rooms, room_tables, station_zones}.

    병실은 zone 의 `room` 칸이다. 병상(kind bed)과 병실 테이블(kind station 에 room 이 있는 것)이 가진다.
    테이블이 없는 병실은 room_tables 에 없다 — 그 병실 묶음은 예전처럼 침상마다 선다.
    station_zones 는 kind station 인 zone 전부다(station_a·station_b·병실 테이블). 그 자리의 인식표는 st-<zone> 이다.
    """
    zones = (zones_doc or {}).get('zones') or {}
    zone_rooms = {zone: str(body['room']) for zone, body in zones.items()
                  if isinstance(body, dict) and body.get('room')}
    room_tables = {str(body['room']): zone for zone, body in zones.items()
                   if isinstance(body, dict) and body.get('room') and body.get('kind') == 'station'}
    station_zones = frozenset(zone for zone, body in zones.items()
                              if isinstance(body, dict) and body.get('kind') == 'station')
    return {'zone_rooms': zone_rooms, 'room_tables': room_tables, 'station_zones': station_zones}


@dataclass(frozen=True)
class Token:
    """goal·서비스 호출 하나. owner 는 'trip'(FSM) 또는 'refill'(보충 클라이언트)."""

    epoch: int
    owner: str
    seq: int


@dataclass(frozen=True)
class Stop:
    """정거장 하나. ADR 정거장 절."""

    zone_id: str
    kind: str
    tag_id: str
    order_ids: tuple


@dataclass(frozen=True)
class SendGoal:
    """액션 goal 을 보낸다."""

    action: str
    goal: dict
    # 명령 표(ADR)의 같음 비교에는 넣지 않는다. 식별은 노드와 result 입력이 쓴다.
    token: Token = field(default=None, compare=False)


@dataclass(frozen=True)
class Cancel:
    """활성 goal 을 취소한다. token 이 있으면 그 goal 만."""

    action: str
    token: Token = field(default=None, compare=False)


@dataclass(frozen=True)
class Call:
    """서비스를 부른다."""

    service: str
    request: dict
    token: Token = field(default=None, compare=False)


def request_summary(request):
    """REQUEST_ACCEPTED 의 detail. 표시용 한 줄 JSON 이다(관제 화면이 모드·환자·약품을 보여 준다).

    `{"mode":1,"destination_id":"bed_a1","orders":[{"order_id":"…","patient_id":"…","item_id":"…"}]}`.
    키 순서는 이대로 고정, 공백 없음, 한글은 그대로(ensure_ascii=False). mode 는 DeliveryRequest 상수 값이다.
    계약상 detail 은 판정·지표에 쓰지 않는다. event_logger·집계기도 읽지 않는다.
    """
    summary = {
        'mode': MODE_VALUES.get(request.get('mode', MODE_SINGLE), MODE_VALUES[MODE_SINGLE]),
        'destination_id': request.get('destination_id', ''),
        'orders': [{'order_id': row.get('order_id', ''), 'patient_id': row.get('patient_id', ''),
                    'item_id': row.get('item_id', '')} for row in request.get('orders') or ()],
    }
    return json.dumps(summary, ensure_ascii=False, separators=(',', ':'))


@dataclass(frozen=True)
class Emit:
    """Event 를 발행한다."""

    event: str
    request_id: str = ''
    order_id: str = ''
    # 비우면 노드의 robot_id. 조제기 이벤트는 ROBOT_DISPENSER 다(Event.msg robot_id 주석).
    robot_id: str = ''
    detail: str = ''
    # 리셋으로 끊긴 주문을 닫을 때의 snapshot. None 이면 노드의 지금 epoch·지금 sim time 을 쓴다.
    epoch: int = field(default=None, compare=False)
    stamp: float = field(default=None, compare=False)


@dataclass(frozen=True)
class OrderState:
    """OrderStatus 를 발행한다."""

    order_id: str
    state: str
    reason: str = ''
    # 리셋으로 끊긴 주문을 닫을 때의 snapshot. None 이면 FSM 의 지금 request_id·지금 sim time.
    request_id: str = field(default=None, compare=False)
    stamp: float = field(default=None, compare=False)


@dataclass(frozen=True)
class Note:
    """노드가 로그로 남길 문장. 판정에는 쓰지 않는다. level 은 'info'·'warning'·'error'."""

    text: str
    level: str = 'warning'


@dataclass(frozen=True)
class Alert:
    """관제 웹 알림(`/p3/alerts`, `rokey_p3_navigation.alerts`). 판정에는 쓰지 않는다. kind 는 alerts.KINDS."""

    kind: str
    detail: str


@dataclass(frozen=True)
class ReloadStores:
    """/sim/reset 이 ok 한 뒤 재고·선반·주문 사용 표를 설정 파일 값으로 되돌린다(계약 6절 3)."""


@dataclass(frozen=True)
class Finish:
    """Deliver 결과를 돌려준다. aborted 는 리셋으로 끊긴 경우다."""

    success: bool
    aborted: bool = False


@dataclass
class _Order:
    order_id: str
    patient_id: str
    item_id: str
    state: str = ORDER_ACCEPTED
    reason: str = ''
    slot: int = -1


@dataclass
class _Trip:
    request_id: str = ''
    mode: str = MODE_SINGLE
    orders: dict = field(default_factory=dict)
    sequence: tuple = ()
    stops: tuple = ()
    stop_index: int = 0
    started_s: float = 0.0
    arriving_emitted: bool = False


class TripFsm:
    """한 AMR 에 인스턴스 하나. Deliver goal 하나가 트립 하나다."""

    def __init__(self, config=None, inventory=None, patient_beds=None, zone_rooms=None, room_tables=None,
                 station_zones=None):
        self.config = config or TripConfig()
        # 노드가 리셋 때 새 재고로 갈아 끼운다(계약 6절 3).
        self.inventory = inventory
        self._patient_beds = dict(patient_beds or {})
        # 병실 테이블(재범 9/25 03:3x: 병실 주문 → 그 방 테이블 C). zone → 병실, 병실 → 테이블 zone.
        # 비어 있으면(빈월드·시험 기본) 병실 묶음은 예전처럼 침상마다 선다.
        self._zone_rooms = dict(zone_rooms or {})
        self._room_tables = dict(room_tables or {})
        # kind station 인 zone. 그 자리에 서는 정거장은 주문 모드와 상관없이 스테이션 인식표(st-<zone>)로
        # 인증한다(재범 9/25: 시뮬 인식표 센서가 스테이션 자리에서는 st- 를, 침상에서만 pt- 를 낸다).
        self._station_zones = frozenset(station_zones or ())
        self._states = {}
        self._last_tag = ''
        self._now = 0.0
        self._wall = None
        self._version = 0
        self._epoch = 1
        self._seq = 0
        self._expected = {}          # 액션·서비스 이름 → 지금 기다리는 token
        self._draining = {}          # cancel 한 token → 종결을 기다리는 wall 상한(None 이면 상한 모름)
        self._barrier = None         # 리셋 barrier 하위 단계. RESETTING 밖에서는 None
        self._drain = set()          # barrier 가 종결을 기다리는 token
        self._drain_deadline = None
        self._reset_deadline = None
        self._drain_timed_out = False
        self.state = IDLE
        self._entered = True
        # 지난 트립이 도크에 못 돌아온 채 끝났다. 다음 트립은 적재 위치로 가기 전에 도크부터 간다.
        # 9/24 병원 10건: 협탁에 끼인 채 끝난 트립 뒤에 다음 주문이 그 자리에서 출발했다. 출발 guard 는
        # 팔 홈(arm/at_home)만 보고 AMR 이 도크인지는 모른다 — FSM 이 아는 것은 자기 복귀 결과뿐이다.
        # 시작(bringup)과 리셋 뒤에는 fleet 가 도크 자세를 내므로 거짓이다.
        self._undocked = False
        self._redocking = False
        self._trip = _Trip()
        self._clear_trip()

    # 조회 ---------------------------------------------------------------

    @property
    def request_id(self):
        """진행 중인 요청 ID. 없으면 빈 문자열."""
        return self._trip.request_id

    @property
    def busy(self):
        """트립이 진행 중인가. v1 은 한 번에 하나다(계약 2.5절)."""
        return self.state != IDLE

    @property
    def epoch(self):
        return self._epoch

    @property
    def resetting(self):
        """리셋 barrier 안인가(실패로 멈춘 경우 포함)."""
        return self.state == RESETTING

    @property
    def barrier_running(self):
        """barrier 가 진행 중인가(drain·reset_wait). 이때 온 리셋 요청은 합류한다."""
        return self.state == RESETTING and self._barrier in (BARRIER_DRAIN, BARRIER_RESET_WAIT)

    @property
    def barrier_failed(self):
        return self.state == RESETTING and self._barrier == BARRIER_FAILED

    def order_states(self):
        """주문 ID → 지금 상태. Deliver 결과를 만들 때 쓴다."""
        return {oid: order.state for oid, order in self._trip.orders.items()}

    def order_reasons(self):
        """주문 ID → 이유."""
        return {oid: order.reason for oid, order in self._trip.orders.items()}

    def stops(self):
        """이 트립의 정거장 순서."""
        return self._trip.stops

    def stops_left(self):
        """아직 안 들른 정거장 수. 트립이 없거나(IDLE) 정거장을 다 돌았으면 0 이다.

        `refill_overlap` 줄에 참고로 찍는 값이다. **겹침 판정은 이 값이 아니라 `DELIVERY_STATES` 다**
        (`overlap=`). 부르는 쪽이 `stops()` 와 `stop_index` 를 직접 빼지 않게 여기 한 곳에 둔다.
        """
        return max(0, len(self._trip.stops) - self._trip.stop_index)

    def accepts(self, request):
        """계약 2.5절 수락 조건 중 FSM 이 아는 것. 나머지(중복 ID·풀·zone)는 노드가 본다."""
        return self.refusal(request) is None

    def refusal(self, request):
        """받을 수 없으면 사람이 읽을 이유, 받을 수 있으면 None. 판정은 accepts 와 같다(이유만 붙인다)."""
        if self.busy:
            return f'진행 중 트립이 있다(상태 {self.state}, 트립 {self._trip.request_id})'
        if not request.get('orders'):
            return 'orders 가 비었다'
        if self._build_stops(request) is None:
            return f'정거장을 만들 수 없다: {self._stops_problem(request)}'
        return None

    def _stops_problem(self, request):
        """_build_stops 가 None 인 까닭(거부 로그·웹 표시용). 판정은 _build_stops 가 한다."""
        mode = request.get('mode', MODE_SINGLE)
        orders = list(request.get('orders') or ())
        if mode == MODE_BATCH_WARD:
            return 'batch_ward 인데 destination_id 가 없다'
        if mode in (MODE_SINGLE, MODE_URGENT):
            if len(orders) != 1:
                return f'{mode} 는 주문이 1개여야 한다({len(orders)}개)'
            row = orders[0]
            return f"{row.get('order_id')} 의 환자 {row.get('patient_id')!r} 침상을 모르고 destination_id 도 없다"
        if mode == MODE_BATCH_ROOM:
            missing = [f"{row.get('order_id')}(환자 {row.get('patient_id')!r})" for row in orders
                       if not self._patient_beds.get(row.get('patient_id', ''))]
            if missing:
                return f'batch_room 인데 침상을 모르는 주문이 있다: {missing}'
            rooms = sorted({self._zone_rooms.get(self._patient_beds[row.get('patient_id', '')], '?')
                            for row in orders})
            return f'batch_room 인데 병실이 하나가 아니다(병실 테이블로 가려면 한 병실이어야 한다): {rooms}'
        return f'모르는 mode {mode!r}'

    # 입력 ---------------------------------------------------------------

    def request(self, request):
        """Deliver goal 하나. 거부하면 빈 목록이다(이벤트 없음, 지표 분모에 안 들어간다)."""
        if not self.accepts(request):
            return []
        self._start_trip(request)
        out = [Emit(EVENT_REQUEST_ACCEPTED, self._trip.request_id, detail=request_summary(request))]
        out += [OrderState(oid, ORDER_ACCEPTED) for oid in self._trip.sequence]
        self._goto(DISPATCHING)
        return out + self._pump()

    def state_update(self, name, value, fresh):
        """at_home, base_stopped, belt, holding 의 최신값과 신선도. 신선도는 노드가 wall 로 잰다."""
        self._states[name] = (value, bool(fresh))
        return self._pump()

    def tag(self, tag_id, kind='', stamp=0.0):
        """tag_reads 한 건. ScanTag 결과에 tag_id 가 없을 때 쓴다."""
        self._last_tag = tag_id
        return []

    def feedback(self, action, distance_remaining, token=None):
        """GoToZone 피드백. 긴급만 ARRIVING 을 한 번 낸다. 이전 goal 의 피드백은 버린다."""
        if token is not None and self._expected.get(action) != token:
            return []
        if action != GO_TO_ZONE or self.state != TRANSIT:
            return []
        if self._trip.mode != MODE_URGENT or self._trip.arriving_emitted:
            return []
        if distance_remaining > self.config.arriving_distance_m:
            return []
        self._trip.arriving_emitted = True
        return [Emit(EVENT_ARRIVING, self._trip.request_id)]

    def tick(self, now_sim, now_wall=None):
        """타임아웃 판정. 타임아웃은 sim time 이다(계약 4절)."""
        self._now = float(now_sim)
        if now_wall is not None:
            self._wall = float(now_wall)
        if self.state == RESETTING:
            return self._barrier_step()
        if self.state == IDLE:
            return []
        out = []
        limit = self._trip.started_s + self.config.trip_limit_s
        if self._now >= limit and self.state != RETURNING:
            out += self._close_all(TIMEOUT, 'trip_limit')
            out += self._cancel_pending()
            self._goto(RETURNING)
            return out + self._pump()
        if self._pending is not None and self._deadline is not None and self._now >= self._deadline:
            pending = self._pending
            out += self._cancel_pending()
            return out + self._handle_result(pending, TIMED_OUT, {})
        return out + self._pump()

    def reset(self, epoch, now_sim=None, now_wall=None, drain=()):
        """리셋 barrier 진입(계약 6절). `drain` 은 노드가 아는 활성 goal 들 (액션 이름, token).

        진행 중 barrier 면 합류한다: 아무것도 안 내고 epoch·상한을 그대로 둔다. 실패로 멈춘 barrier 면 새로 시작한다.
        """
        if now_sim is not None:
            self._now = float(now_sim)
        if now_wall is not None:
            self._wall = float(now_wall)
        if self.barrier_running:
            return []
        stamp = self._now
        old_request = self._trip.request_id
        old_epoch = self._epoch
        out = []
        # 1. 끊긴 주문을 이전 epoch·이전 request_id·같은 stamp 로 닫는다. 이미 닫힌 주문은 덮지 않는다.
        for order_id in self._trip.sequence:
            order = self._trip.orders[order_id]
            if order.state in _TERMINAL:
                continue
            order.state = ABORT
            order.reason = REASON_RESET_INTERRUPTED
            out.append(OrderState(order_id, ABORT, REASON_RESET_INTERRUPTED, request_id=old_request, stamp=stamp))
            out.append(Emit(EVENT_ORDER_DONE, old_request, order_id, epoch=old_epoch, stamp=stamp))
        if old_request:
            out.append(Finish(success=False, aborted=True))
        # FSM 이 기다리던 goal 과 대체 goal 을 막으려고 cancel 해 둔 goal 도 종결을 기다린다.
        cancels = {token: action for action, token in drain}
        if self._pending is not None and self._expected.get(self._pending) is not None:
            cancels.setdefault(self._expected[self._pending], self._pending)
        waiting = set(cancels) | set(self._draining)
        self._clear_trip()
        # 2. 새 epoch. 이전 epoch 의 token 은 이제 기다리지 않는다(종결 확인만 drain 이 한다).
        self._epoch = int(epoch)
        self._expected.clear()
        self._draining.clear()
        self.state = RESETTING
        self._entered = True
        out.append(Emit(EVENT_RESET_BEGIN, epoch=self._epoch, stamp=stamp))
        # 3. drain
        out += [Cancel(action, token=token) for token, action in cancels.items()]
        self._barrier = BARRIER_DRAIN
        self._drain = waiting
        self._drain_timed_out = False
        self._drain_deadline = None if self._wall is None else self._wall + self.config.cancel_wait_s
        self._reset_deadline = None
        return out + self._barrier_step()

    def terminated(self, token):
        """goal 하나가 종결됐다(결과·거부·보내기 전 cancel). barrier 가 기다리던 것이면 뺀다."""
        if self._barrier != BARRIER_DRAIN or token not in self._drain:
            return []
        self._drain.discard(token)
        return self._barrier_step()

    def result(self, action, outcome, detail=None, token=None):
        """액션 수락·거부·결과 또는 서비스 응답 하나. token 이 지금 기다리는 것과 다르면 버린다."""
        detail = detail or {}
        if self.state == RESETTING:
            return self._barrier_result(action, outcome, detail, token)
        if token is not None:
            if token in self._draining:
                if outcome != ACCEPTED:
                    del self._draining[token]          # cancel 한 goal 이 끝났다. 막아 둔 대체 goal 을 보낸다
                    return self._pump()
                return []
            if self._expected.get(action) != token:
                return []          # 같은 epoch 의 이전 goal·호출이다
        return self._handle_result(action, outcome, detail)

    # 리셋 barrier ----------------------------------------------------------

    def _barrier_result(self, action, outcome, detail, token):
        if token is not None and token in self._drain and outcome != ACCEPTED:
            return self.terminated(token)
        if action != RESET or self._barrier != BARRIER_RESET_WAIT:
            return []          # 리셋 중에 들어온 이전 epoch 의 결과는 버린다(계약 4절)
        if token is not None and self._expected.get(RESET) != token:
            return []          # 실패한 barrier 의 늦은 응답이다
        self._expected.pop(RESET, None)
        if outcome != OK:
            return self._barrier_fail(f'/sim/reset 응답 {outcome} {detail.get("message", "")}'.strip())
        detail_text = DETAIL_DRAIN_TIMEOUT if self._drain_timed_out else ''
        self._barrier = None
        self._drain = set()
        self._undocked = False     # 리셋은 AMR 을 도크 자세로 되돌린다(fleet 가 RESET_DONE 에서 initialpose)
        self._redocking = False
        self._goto(IDLE)
        return [ReloadStores(), Emit(EVENT_RESET_DONE, detail=detail_text)] + self._pump()

    def _barrier_step(self):
        """drain 이 끝났거나 상한이 지났으면 /sim/reset 을 부른다. reset_wait 상한이 지났으면 실패로 닫는다."""
        if self._barrier == BARRIER_DRAIN:
            timed_out = (self._drain and self._drain_deadline is not None
                         and self._wall is not None and self._wall >= self._drain_deadline)
            if self._drain and not timed_out:
                return []
            out = []
            if self._drain:
                self._drain_timed_out = True
                out.append(Note(f'리셋 drain: goal {len(self._drain)}건이 {self.config.cancel_wait_s:g} s 안에 '
                                '종결되지 않았다. 진행하고 RESET_DONE detail 에 남긴다.'))
                self._drain = set()
            self._barrier = BARRIER_RESET_WAIT
            self._reset_deadline = None if self._wall is None else self._wall + self.config.reset_timeout_s
            out.append(Call(RESET, {'epoch': self._epoch}, token=self._issue(RESET)))
            return out
        expired = (self._reset_deadline is not None and self._wall is not None
                   and self._wall >= self._reset_deadline)
        if self._barrier == BARRIER_RESET_WAIT and expired:
            self._expected.pop(RESET, None)
            return self._barrier_fail(f'/sim/reset 이 {self.config.reset_timeout_s:g} s 안에 응답하지 않았다')
        return []

    def _barrier_fail(self, reason):
        self._barrier = BARRIER_FAILED
        return [Note(f'리셋 실패: {reason}. Deliver 를 계속 거부하고 RESET_DONE 을 내지 않는다. '
                     '자동 재시도는 없다. 새 /orchestrator/reset 으로 새 epoch barrier 를 다시 시작할 수 있다.',
                     level='error')]

    def _handle_result(self, action, outcome, detail):
        if action in (DISPENSE, RESET) or outcome != ACCEPTED:
            self._expected.pop(action, None)
        if action in (GO_TO_ZONE, PICK_POUCH, SCAN_TAG):
            if outcome == ACCEPTED:
                return self._on_accepted(action)
            self._pending = None
            self._deadline = None
        handler = self._RESULT.get((self.state, action))
        if handler is None:
            return []          # 이 상태가 기다리지 않는 결과는 버린다
        return handler(self, outcome, detail) + self._pump()

    # 명령을 만드는 내부 ----------------------------------------------------

    def _on_accepted(self, action):
        if action != GO_TO_ZONE:
            return []
        if self.state == DEPARTING:
            self._goto(TRANSIT)
            return [Emit(EVENT_DEPARTED, self._trip.request_id)] + self._pump()
        if self.state == RETURNING and not self._returned_emitted:
            self._returned_emitted = True
            return [Emit(EVENT_RETURNED, self._trip.request_id)]
        return []

    def _clear_trip(self):
        self._trip = _Trip()
        self._pending = None
        self._deadline = None
        self._belt_deadline = None
        self._retry_at = None
        self._current_order = ''
        self._goto_rejects = 0
        self._dispense_calls = 0
        self._dispatch_dispense_started = False
        self._dispatch_dispense_result = None
        self._pick_attempts = 0
        self._scan_attempts = 0
        self._taken = set()
        self._next_slot = 0
        self._last_belt_pick_ok = None   # 이 트립의 마지막 벨트 픽. None = 아직 없음
        self._returned_emitted = False
        self._return_rejects = 0
        self._return_failures = 0

    def _start_trip(self, request):
        self._clear_trip()
        orders = {}
        sequence = []
        for row in request['orders']:
            orders[row['order_id']] = _Order(order_id=row['order_id'],
                                             patient_id=row.get('patient_id', ''),
                                             item_id=row.get('item_id', ''))
            sequence.append(row['order_id'])
        self._trip = _Trip(request_id=request.get('request_id', ''),
                           mode=request.get('mode', MODE_SINGLE),
                           orders=orders, sequence=tuple(sequence),
                           stops=self._build_stops(request), started_s=self._now)

    def _build_stops(self, request):
        """ADR 정거장 절. 만들 수 없으면 None 이고 그때는 요청을 거부한다."""
        mode = request.get('mode', MODE_SINGLE)
        orders = list(request.get('orders') or ())
        destination = request.get('destination_id', '')
        if mode == MODE_BATCH_WARD:
            if not destination:
                return None
            return (Stop(destination, KIND_STATION, station_tag_id(destination),
                         tuple(row['order_id'] for row in orders)),)
        if mode in (MODE_SINGLE, MODE_URGENT):
            if len(orders) != 1:
                return None
            row = orders[0]
            zone = self._patient_beds.get(row.get('patient_id', ''), destination)
            if not zone:
                return None
            return (self._stop(zone, row.get('patient_id', ''), (row['order_id'],)),)
        if mode == MODE_BATCH_ROOM:
            table = self._room_table(orders)
            if table is False:
                return None
            if table:
                # 병실 주문 → 그 방 테이블 한 곳에 전부 놓는다(재범 9/25). 인식표는 스테이션 st-<테이블 zone>.
                return (Stop(table, KIND_STATION, station_tag_id(table),
                             tuple(row['order_id'] for row in orders)),)
            grouped = []
            index = {}
            for row in orders:
                bed = self._patient_beds.get(row.get('patient_id', ''))
                if not bed:
                    return None
                if bed not in index:
                    index[bed] = len(grouped)
                    grouped.append((bed, row.get('patient_id', ''), []))
                grouped[index[bed]][2].append(row['order_id'])
            return tuple(self._stop(bed, patient, tuple(ids)) for bed, patient, ids in grouped)
        return None

    def _stop(self, zone, patient_id, order_ids):
        """침상이면 환자 인식표(pt-), 스테이션 자리(station_zones)면 스테이션 인식표(st-<zone>) 정거장."""
        if zone in self._station_zones:
            return Stop(zone, KIND_STATION, station_tag_id(zone), order_ids)
        return Stop(zone, KIND_PATIENT, patient_tag_id(patient_id), order_ids)

    def _room_table(self, orders):
        """병실 묶음의 테이블 zone. 테이블 표가 없으면 None(침상마다 선다), 병상을 모르거나 병실이 둘 이상이면 False."""
        if not self._room_tables:
            return None
        beds = [self._patient_beds.get(row.get('patient_id', '')) for row in orders]
        if not all(beds):
            return False
        rooms = {self._zone_rooms.get(bed) for bed in beds}
        if len(rooms) != 1:
            return False
        return self._room_tables.get(rooms.pop())

    def _goto(self, state):
        # 같은 상태로 다시 들어가는 전이도 있다(다음 주문). _version 이 그것을 구분한다.
        self.state = state
        self._entered = False
        self._version += 1

    def _pump(self):
        out = []
        for _ in range(64):
            if self._entered:
                break
            version = self._version
            commands = self._ENTRY[self.state](self)
            if commands is None:
                break              # guard 미충족. 다음 입력이나 tick 에서 다시 본다
            out += commands
            if self._version == version:
                self._entered = True
        return out

    # 기다리는 이유(로그용) -------------------------------------------------

    #: 상태 → 사람이 읽는 대기 이름. 이 상태의 진입이 guard 로 멈춰 있을 때만 이유를 낸다.
    WAIT_KINDS = {
        DISPATCHING: '출발(적재 위치로)',
        DOCKED_LOAD: '배출',
        WAIT_BELT: '벨트 끝 도착',
        PICKING_BELT: '벨트 픽',
        DEPARTING: '출발(병동으로)',
        AUTHENTICATING: '인식표 스캔',
        DELIVERING: '보관함 배달',
        RETURNING: '복귀(도크로)',
    }

    def wait_reason(self, names=None):
        """지금 진입이 guard 로 멈춰 있으면 (대기 이름, 이유), 아니면 None. 로그용이고 상태를 바꾸지 않는다.

        판정은 각 _enter_* 와 같은 조건을 같은 순서로 읽기만 한다. names 는 상태 키 → 사람에게 보일 토픽 이름.
        """
        kind = self.WAIT_KINDS.get(self.state)
        if kind is None or self._entered:
            return None
        names = {AT_HOME: 'arm/at_home', BASE_STOPPED: 'base/stopped', BELT: '/pharmacy/belt', **(names or {})}

        def signal(name):
            value, fresh = self._states.get(name, (None, False))
            if not fresh:
                return f'{names[name]} unknown(1.0 s 넘게 소식 없음. 발행하는 노드·Isaac 이 떠 있는지 확인)'
            if not value:
                return f'{names[name]} false'
            return None

        draining = [until for until in self._draining.values()
                    if until is None or self._wall is None or self._wall < until]
        drain = 'cancel 한 goal 의 종결 대기' if draining else None
        retry = '거부된 요청의 재시도 대기(5 s)' if self._waiting_retry() else None

        if self.state in (DISPATCHING, DEPARTING, RETURNING):
            if self.state == DEPARTING and self.config.pharmacy_only:
                return None
            reason = drain or signal(AT_HOME) or retry
        elif self.state == DOCKED_LOAD:
            if self._next_undispensed() is None:
                return None
            value, fresh = self._states.get(BELT, (None, False))
            belt = value if fresh and isinstance(value, dict) else None
            if belt is None:
                reason = signal(BELT) or f'{names[BELT]} 값이 벨트 상태가 아니다'
            elif belt.get('occupied'):
                if self._closed(belt.get('order_id')):
                    return None                    # 벨트 막힘으로 곧바로 닫힌다. 기다림이 아니다
                reason = f'벨트에 봉투가 있다(order_id={belt.get("order_id") or "-"}). 치워지거나 픽될 때까지'
            else:
                reason = retry or drain
                if reason is None and self.config.observation_guard:
                    reason = self._dispense_guard_reason()
        elif self.state == WAIT_BELT:
            reason = signal(BELT)                  # 봉투가 굴러오는 동안은 정상이다. 벨트 소식이 끊겼을 때만
        elif self.state == PICKING_BELT:
            value, fresh = self._states.get(BELT, (None, False))
            belt = value if fresh and isinstance(value, dict) else None
            reason = drain or signal(BASE_STOPPED)
            if reason is None and (not belt or not belt.get('at_end') or belt.get('order_id') != self._current_order):
                reason = signal(BELT) or f'벨트 끝에 {self._current_order} 봉투가 없다'
            if reason is None and self.config.observation_guard:
                reason = self._pick_guard_reason()
        else:                                      # AUTHENTICATING, DELIVERING
            reason = drain or signal(BASE_STOPPED)
        return (kind, reason) if reason else None

    # 상태별 진입 ----------------------------------------------------------

    def _value(self, name):
        value, fresh = self._states.get(name, (None, False))
        return value if fresh else None

    def _observation(self, name):
        """계약 11.6 관측. 신선하고(노드가 seq 증가로 판정) 지금 epoch 일 때만 dict, 아니면 None."""
        value = self._value(name)
        return value if isinstance(value, dict) and value.get('epoch') == self._epoch else None

    def _pick_guard_reason(self):
        """observation_guard 의 피킹 조건. 허가면 None, 아니면 사람이 읽을 이유."""
        obs = self._observation(BELT_OBSERVATION)
        if obs is None:
            return '벨트 관측 없음(신선한 seq 증가·지금 epoch 가 아니다)'
        if obs.get('order_id') != self._current_order:
            return f'벨트 관측의 주문이 {obs.get("order_id") or "-"} 다({self._current_order} 아님)'
        if (obs.get('pouch_zone'), obs.get('pouch_motion'), obs.get('belt_command_applied')) != \
                (ZONE_END, MOTION_STOPPED, APPLIED_STOP):
            return (f'벨트 관측이 종단 정착이 아니다(zone {obs.get("pouch_zone")}, motion {obs.get("pouch_motion")}, '
                    f'applied {obs.get("belt_command_applied")})')
        return None

    def _dispense_guard_reason(self):
        """observation_guard 의 다음 배출 조건. 허가면 None, 아니면 사람이 읽을 이유."""
        if self._last_belt_pick_ok is False:
            return '이 트립의 앞 벨트 픽이 ok 로 끝나지 않았다'
        obs = self._observation(BELT_OBSERVATION)
        if obs is None or obs.get('occupancy') != OCCUPANCY_EMPTY:
            return '벨트 관측이 빈 벨트(EMPTY, 신선한 seq 증가)를 말하지 않는다'
        arm = self._observation(ARM_CLEARANCE)
        if arm is None or arm.get('clearance') != CLEARANCE_CLEAR:
            return '팔 통로 관측이 CLEAR(신선한 seq 증가)를 말하지 않는다'
        return None

    def _guard(self, name):
        """계약 5절: 값이 true 이고 1.0 s 안에 받은 것일 때만 허용. unknown 이면 기다린다."""
        return bool(self._value(name))

    def _belt(self):
        value = self._value(BELT)
        return value if isinstance(value, dict) else None

    def _enter_idle(self):
        return []

    def _enter_dispatching(self):
        if not self._drained() or not self._guard(AT_HOME) or self._waiting_retry():
            return None
        if self._undocked:
            # 지난 트립이 도크에 못 돌아왔다. 도크부터 간다. 못 가면 이 트립의 주문을 닫는다(_result_dispatching).
            self._redocking = True
            return [Note(f'지난 트립이 도크에 못 돌아온 채 끝났다. {self._trip.request_id} 는 '
                         f'{self.config.dock_zone} 로 먼저 간다.', level='warning'),
                    *self._send_goto(self.config.dock_zone, self.config.goto_timeout_load_s)]
        self._redocking = False
        if self.config.load_at_dock:
            # 도크 = 적재 자리(병원 B안): 이미 서 있다. 움직이지 않고 적재로 간다 — 도착한 것과 같은 결과다.
            self._goto_rejects = 0
            self._goto(DOCKED_LOAD)
            return [Note(f'{self.config.dock_zone} = 적재 자리. 이동 없이 적재한다.', level='info'),
                    Emit(EVENT_AMR_DOCKED_LOAD, self._trip.request_id)]
        out = []
        if self.config.dispense_while_dispatching and not self._dispatch_dispense_started:
            order_id = self._next_undispensed()
            stocked = (order_id is not None and (self.inventory is None or
                       self.inventory.active_slot(self._trip.orders[order_id].item_id) is not None))
            if stocked:
                out = self._enter_docked_load() or []
                self._dispatch_dispense_started = any(isinstance(c, Call) and c.service == DISPENSE for c in out)
            if self._dispatch_dispense_started:
                out.append(Note('적재 이동과 첫 파우치 조제를 함께 시작한다.', level='info'))
        return self._send_goto(self.config.load_zone, self.config.goto_timeout_load_s) + out

    def _enter_docked_load(self):
        order_id = self._next_undispensed()
        if order_id is None:
            self._goto(DEPARTING)
            return [Emit(EVENT_LOAD_DONE, self._trip.request_id)]
        belt = self._belt()
        if belt is not None and belt.get('occupied') and self._closed(belt.get('order_id')):
            # 이 트립에서 이미 끝난 주문(픽 실패 ABORT 등)의 봉투가 벨트에 남았다. 치울 주체가 없어서
            # 기다려도 안 풀린다. 성공한 픽 직후에는 그 주문이 LOADED 라 여기에 걸리지 않는다.
            return self._belt_blocked()
        if (belt is not None and belt.get('occupied') and belt.get('order_id') == order_id
                and order_id == self._current_order and self._dispense_calls > 0):
            # 우리가 부른 배출이 늦게 됐다. 응답은 시한 뒤에 와서 거부로 받았지만 봉투는 벨트에 있다.
            return self._adopt_late_dispense(order_id)
        if belt is None or belt.get('occupied') or self._waiting_retry() or not self._drained():
            return None
        if self.config.observation_guard and self._dispense_guard_reason() is not None:
            return None
        out = []
        order = self._trip.orders[order_id]
        if self.inventory is not None and order_id not in self._taken:
            take = self.inventory.take(order.item_id)
            out += [Emit(name, self._trip.request_id, order_id, ROBOT_DISPENSER) for name in take.events]
            if not take.ok:
                out += self._close_order(order_id, ABORT, take.reason)
                self._goto(DOCKED_LOAD)
                return out
            self._taken.add(order_id)
        self._current_order = order_id
        self._dispense_calls += 1
        return out + [Call(DISPENSE, {'request_id': self._trip.request_id, 'order_id': order_id},
                           token=self._issue(DISPENSE))]

    def _enter_wait_belt(self):
        belt = self._belt()
        if belt and belt.get('at_end') and belt.get('order_id') == self._current_order:
            self._goto(PICKING_BELT)
            return []
        if self._belt_deadline is not None and self._now >= self._belt_deadline:
            return self._belt_timed_out(belt)
        return None

    def _enter_picking_belt(self):
        belt = self._belt()
        if not self._drained() or not self._guard(BASE_STOPPED):
            return None
        if not belt or not belt.get('at_end') or belt.get('order_id') != self._current_order:
            return None
        if self.config.observation_guard and self._pick_guard_reason() is not None:
            return None
        order = self._trip.orders[self._current_order]
        if order.slot < 0:
            if self._next_slot >= self.config.deck_slots:
                # 상판 칸이 없다. 실을 자리가 없으면 그 주문은 여기서 끝난다.
                out = self._close_order(order.order_id, ABORT, 'deck_full')
                self._goto(DOCKED_LOAD)
                return out
            order.slot = self._next_slot
        self._pick_attempts += 1
        self._pending = PICK_POUCH
        self._deadline = self._now + self.config.pick_timeout_s
        return [SendGoal(PICK_POUCH, {'order_id': order.order_id, 'source': SOURCE_BELT,
                                      'target_slot': order.slot}, token=self._issue(PICK_POUCH))]

    def _enter_departing(self):
        if self.config.pharmacy_only:
            # 정상 적재와 벨트 막힘 둘 다 LOAD_DONE 을 낸 뒤 여기로 온다. 닫는 것을 at_home 을
            # 기다리기 전에 해야 ORDER_DONE 이 팔의 ARM_HOME 보다 앞에 온다.
            out = []
            for order_id in self._loaded():
                out += self._close_order(order_id, HOLD_RETURN, REASON_PHARMACY_ONLY)
            self._goto(RETURNING)
            return out
        self._skip_empty_stops()
        stop = self._current_stop()
        if stop is None:
            self._goto(RETURNING)
            return []
        if not self._drained() or not self._guard(AT_HOME) or self._waiting_retry():
            return None
        return self._send_goto(stop.zone_id, self.config.goto_timeout_ward_s)

    def _enter_transit(self):
        return []

    def _enter_authenticating(self):
        stop = self._current_stop()
        if stop is None or not self._orders_at_stop():
            self._goto(NEXT_STOP)
            return []
        if not self._drained() or not self._guard(BASE_STOPPED):
            # 계약 5절의 팔 동작 guard 는 PickPouch 와 ScanTag 둘 다다. ADR 표의
            # AUTHENTICATING 칸에는 안 적혀 있지만 계약이 "보내기 전에 같은 조건을 본다"고 한다.
            # 이게 없으면 도착 직후 base/stopped 가 아직 true 로 안 온 사이에 goal 이 나가고
            # 팔이 인터락으로 거절한다.
            return None
        self._scan_attempts += 1
        self._pending = SCAN_TAG
        self._deadline = self._now + self.config.scan_timeout_s
        return [SendGoal(SCAN_TAG, {'kind': stop.kind, 'zone_id': stop.zone_id}, token=self._issue(SCAN_TAG))]

    def _enter_delivering(self):
        order_id = self._next_at_stop()
        if order_id is None:
            self._goto(NEXT_STOP)
            return []
        if not self._drained() or not self._guard(BASE_STOPPED):
            return None
        self._current_order = order_id
        self._pick_attempts += 1
        self._pending = PICK_POUCH
        self._deadline = self._now + self.config.pick_timeout_s
        # 어느 침상 보관함인지 goal 에 담는다(계약 10.1). 이 값이 없으면 팔이 파라미터 `cabinet_frame`
        # 한 곳에만 놓아 **한 회차에 한 침상**밖에 못 돈다 — 9/23 데모가 ord-0001 한 건으로 피한 자리다.
        return [SendGoal(PICK_POUCH, {'order_id': order_id, 'source': SOURCE_DECK,
                                      'target_slot': -1, 'zone_id': self._current_stop().zone_id},
                         token=self._issue(PICK_POUCH))]

    def _enter_next_stop(self):
        self._trip.stop_index += 1
        self._trip.arriving_emitted = True   # ARRIVING 은 트립마다 한 번이다
        self._scan_attempts = 0
        self._pick_attempts = 0
        self._skip_empty_stops()
        self._goto(DEPARTING if self._current_stop() is not None else RETURNING)
        return []

    def _enter_returning(self):
        if not self._drained() or not self._guard(AT_HOME) or self._waiting_retry():
            return None
        return self._send_goto(self.config.dock_zone, self.config.goto_timeout_load_s)

    def _enter_resetting(self):
        return []

    _ENTRY = {
        IDLE: _enter_idle,
        DISPATCHING: _enter_dispatching,
        DOCKED_LOAD: _enter_docked_load,
        WAIT_BELT: _enter_wait_belt,
        PICKING_BELT: _enter_picking_belt,
        DEPARTING: _enter_departing,
        TRANSIT: _enter_transit,
        AUTHENTICATING: _enter_authenticating,
        DELIVERING: _enter_delivering,
        NEXT_STOP: _enter_next_stop,
        RETURNING: _enter_returning,
        RESETTING: _enter_resetting,
    }

    # 결과 처리 ------------------------------------------------------------

    def _result_dispatching(self, outcome, detail):
        if self._redocking and outcome == ARRIVED:
            self._undocked = False
            self._redocking = False
            self._goto_rejects = 0
            self._goto(DISPATCHING)
            return [Note(f'{self.config.dock_zone} 도착. 적재 위치로 간다.', level='info')]
        if outcome == ARRIVED:
            self._goto_rejects = 0
            self._goto(DOCKED_LOAD)
            out = [Emit(EVENT_AMR_DOCKED_LOAD, self._trip.request_id)]
            if self._dispatch_dispense_started:
                if self._dispatch_dispense_result is not None:
                    result = self._dispatch_dispense_result
                    self._dispatch_dispense_result = None
                    out += self._result_docked_load(*result)
                else:
                    self._entered = True  # 조제 응답 대기. 중복 배출을 보내지 않는다.
            return out
        if outcome == REJECTED:
            return self._goto_rejected(DISPATCHING)
        return self._give_up_all(('redock_' if self._redocking else 'goto_') + outcome)

    def _result_dispatch_dispense(self, outcome, detail):
        # 주행 중 조제 응답이 와도 주행 상태/시한을 덮지 않는다.
        self._dispatch_dispense_result = (outcome, detail)
        return []

    def _adopt_late_dispense(self, order_id):
        """거부로 받은 배출이 실제로는 됐다 — 벨트 관측(그 주문의 봉투)을 배출 증거로 받는다.

        9/24 090a976 10건 ord-0007: isaac_adapter 가 Dispense 응답을 10 s 안에 못 받아 거부로 답했고, 스테이지의
        응답은 3 s 늦게 와서 버려졌다. 봉투는 벨트 끝에 섰는데 FSM 은 미배출로 알고 "벨트에 봉투가 있다" 로
        1405 s 기다리다 trip_limit 로 끝났다. 그 봉투를 치울 주체가 없어서 기다림이 풀리지 않는다.
        받는 조건은 좁다: 이 트립에서 **방금 배출을 부른 그 주문**의 봉투일 때만이다.
        """
        self._dispense_calls = 0
        self._retry_at = None
        self._belt_deadline = self._now + self.config.belt_timeout_s
        self._trip.orders[order_id].state = ORDER_DISPENSED
        self._goto(WAIT_BELT)
        return [Note(f'{order_id} 배출 응답은 거부(시한)였지만 그 봉투가 벨트에 있다. 배출된 것으로 받는다.'),
                OrderState(order_id, ORDER_DISPENSED)]

    def _result_docked_load(self, outcome, detail):
        order_id = self._current_order
        if outcome == ACCEPTED:
            self._dispense_calls = 0
            self._retry_at = None
            self._belt_deadline = self._now + self.config.belt_timeout_s
            self._trip.orders[order_id].state = ORDER_DISPENSED
            self._goto(WAIT_BELT)
            return [OrderState(order_id, ORDER_DISPENSED)]
        if self._dispense_calls < self.config.dispense_max_calls:
            self._retry_at = self._now + self.config.dispense_retry_delay_s
            self._goto(DOCKED_LOAD)
            return []
        self._dispense_calls = 0
        self._retry_at = None
        out = self._close_order(order_id, ABORT, detail.get('message') or 'dispense_failed')
        self._goto(DOCKED_LOAD)
        return out

    def _result_picking_belt(self, outcome, detail):
        order_id = self._current_order
        if outcome == OK:
            self._last_belt_pick_ok = True
            self._pick_attempts = 0
            self._next_slot += 1
            self._trip.orders[order_id].state = ORDER_LOADED
            self._goto(DOCKED_LOAD)
            return [OrderState(order_id, ORDER_LOADED)]
        if outcome != DROPPED and self._pick_attempts < self.config.pick_max_attempts:
            self._goto(PICKING_BELT)
            return []
        self._pick_attempts = 0
        self._last_belt_pick_ok = False
        out = self._close_order(order_id, ABORT, outcome)
        self._goto(DOCKED_LOAD)
        return out

    def _result_departing(self, outcome, detail):
        if outcome == REJECTED:
            return self._goto_rejected(DEPARTING)
        return self._give_up_all('goto_' + outcome)

    def _result_transit(self, outcome, detail):
        if outcome == ARRIVED:
            self._goto_rejects = 0
            self._goto(AUTHENTICATING)
            return [Emit(EVENT_ARRIVED, self._trip.request_id)]
        return self._give_up_all('transit_' + outcome)

    def _result_authenticating(self, outcome, detail):
        stop = self._current_stop()
        if outcome == OK:
            tag_id = detail.get('tag_id') or self._last_tag
            # 카메라 TagRead/ScanTag 는 계약대로 pt-/st- 를 뺀 ID 를 낸다.
            # 기존 sim 센서의 QR 전체 문자열도 같은 정거장의 ID 일 때만 받는다.
            expected = stop.tag_id if stop is not None else ''
            bare = expected[3:] if expected.startswith(('pt-', 'st-')) else expected
            if stop is not None and tag_id and tag_id in (expected, bare):
                self._scan_attempts = 0
                self._goto(DELIVERING)
                return [Emit(EVENT_AUTH_OK, self._trip.request_id)]
            return self._auth_failed('auth_mismatch')
        if self._scan_attempts < self.config.scan_max_attempts:
            self._goto(AUTHENTICATING)
            return []
        return self._auth_failed('tag_unreadable')

    def _result_delivering(self, outcome, detail):
        order_id = self._current_order
        if outcome == OK:
            self._pick_attempts = 0
            out = [Emit(EVENT_CABINET_LOCKED, self._trip.request_id, order_id)]
            out += self._close_order(order_id, ORDER_DELIVERED)
            self._goto(DELIVERING)
            return out
        if outcome != DROPPED and self._pick_attempts < self.config.pick_max_attempts:
            self._goto(DELIVERING)
            return []
        self._pick_attempts = 0
        state = ABORT if outcome == DROPPED else HOLD_RETURN
        out = self._close_order(order_id, state, outcome)
        self._goto(DELIVERING)
        return out

    def _result_returning(self, outcome, detail):
        if outcome == ARRIVED:
            return [Emit(EVENT_DOCKED, self._trip.request_id)] + self._finish(docked=True)
        if outcome == REJECTED:
            # 계약 5절: 거부되면 5 s 뒤 1회 더. 끝내 거부면 DOCKED 없이 끝낸다.
            self._return_rejects += 1
            if self._return_rejects < self.config.goto_max_rejects:
                self._retry_at = self._now + self.config.goto_retry_delay_s
                self._goto(RETURNING)
                return []
            return self._finish(docked=False)
        if outcome in (NOT_ARRIVED, TIMED_OUT, FAILED):
            # 실패는 다시 보낸다(취소 CANCELED 는 리셋·정지라 다시 보내지 않는다).
            if self._return_failures < self.config.return_max_retries:
                self._return_failures += 1
                delay = self.config.return_retry_delay_s * 2 ** (self._return_failures - 1)
                self._retry_at = self._now + delay
                self._goto(RETURNING)
                why = outcome if not detail else f'{outcome} {detail}'
                return [Note(f'도크 복귀 실패({why}) — {self._return_failures}/{self.config.return_max_retries} '
                             f'번째 재시도를 {delay:g} s 뒤에 한다', level='warning'),
                        Alert('DOCK_RETRY', f'{self._return_failures}/{self.config.return_max_retries} {why}, '
                                            f'{delay:g} s 뒤 재시도')]
            return [Note(f'도크 복귀 포기: 재시도 {self.config.return_max_retries}번 뒤에도 {outcome} — '
                         f'AMR 이 도크 밖에 서 있다. 사람이 확인해야 한다', level='error'),
                    Alert('DOCK_GIVEUP',
                          f'재시도 {self.config.return_max_retries}번 뒤에도 {outcome} — 도크 밖에 섰다')] \
                + self._finish(docked=False)
        return self._finish(docked=False)

    _RESULT = {
        (DISPATCHING, GO_TO_ZONE): _result_dispatching,
        (DOCKED_LOAD, DISPENSE): _result_docked_load,
        (DISPATCHING, DISPENSE): _result_dispatch_dispense,
        (PICKING_BELT, PICK_POUCH): _result_picking_belt,
        (DEPARTING, GO_TO_ZONE): _result_departing,
        (TRANSIT, GO_TO_ZONE): _result_transit,
        (AUTHENTICATING, SCAN_TAG): _result_authenticating,
        (DELIVERING, PICK_POUCH): _result_delivering,
        (RETURNING, GO_TO_ZONE): _result_returning,
    }

    # 되풀이되는 조각 -------------------------------------------------------

    def _send_goto(self, zone_id, timeout_s):
        self._retry_at = None
        self._pending = GO_TO_ZONE
        self._deadline = self._now + timeout_s
        return [SendGoal(GO_TO_ZONE, {'zone_id': zone_id}, token=self._issue(GO_TO_ZONE))]

    def _issue(self, name):
        """새 token 을 만들고 그 이름으로 기다린다. 이전 token 은 이제 기다리지 않는다."""
        self._seq += 1
        token = Token(self._epoch, OWNER_TRIP, self._seq)
        self._expected[name] = token
        return token

    def _cancel_pending(self):
        """기다리던 goal 을 cancel 한다. 그 token 이 종결될 때까지(또는 cancel_wait_s wall) 대체 goal 을 막는다."""
        if self._pending is None:
            return []
        action = self._pending
        token = self._expected.pop(action, None)
        self._pending = None
        self._deadline = None
        if token is None:
            return [Cancel(action)]
        self._draining[token] = None if self._wall is None else self._wall + self.config.cancel_wait_s
        return [Cancel(action, token=token)]

    def _drained(self):
        """cancel 한 goal 이 모두 종결됐는가. wall 상한이 지난 것은 더 기다리지 않는다."""
        if self._wall is not None:
            for token, until in list(self._draining.items()):
                if until is not None and self._wall >= until:
                    del self._draining[token]
        return not self._draining

    def _waiting_retry(self):
        return self._retry_at is not None and self._now < self._retry_at

    def _goto_rejected(self, state):
        """계약 5절: 거부되면 5 s 뒤 1회 더. 그래도 거부면 남은 주문을 HOLD_RETURN 으로 닫는다."""
        self._goto_rejects += 1
        if self._goto_rejects >= self.config.goto_max_rejects:
            return self._give_up_all('goto_rejected')
        self._retry_at = self._now + self.config.goto_retry_delay_s
        self._goto(state)
        return []

    def _give_up_all(self, reason):
        out = self._close_all(HOLD_RETURN, reason)
        self._goto(RETURNING)
        return out

    def _auth_failed(self, reason):
        self._scan_attempts = 0
        out = [Emit(EVENT_AUTH_FAIL, self._trip.request_id)]
        for order_id in self._orders_at_stop():
            out += self._close_order(order_id, HOLD_RETURN, reason)
        self._goto(NEXT_STOP)
        return out

    def _belt_timed_out(self, belt):
        self._belt_deadline = None
        out = self._close_order(self._current_order, ABORT, 'belt_timeout')
        if belt and belt.get('occupied'):
            return out + self._belt_blocked()
        self._goto(DOCKED_LOAD)
        return out

    def _belt_blocked(self):
        """벨트가 막혔다. 남은 미배출 주문을 더 기다리지 않고 실은 것만 싣고 떠난다."""
        out = []
        for order_id in self._undispensed():
            out += self._close_order(order_id, ABORT, 'belt_blocked')
        out.append(Emit(EVENT_LOAD_DONE, self._trip.request_id))
        self._goto(DEPARTING)
        return out

    def _closed(self, order_id):
        """이 트립의 주문이고 이미 종료 상태인가. 모르는 ID 는 False 다."""
        order = self._trip.orders.get(order_id)
        return order is not None and order.state in _TERMINAL

    def _close_order(self, order_id, state, reason=''):
        """주문을 닫고 ORDER_DONE 을 낸다. DELIVERED 도 오케스트레이터에게는 끝이다."""
        order = self._trip.orders[order_id]
        order.state = state
        order.reason = reason
        return [OrderState(order_id, state, reason),
                Emit(EVENT_ORDER_DONE, self._trip.request_id, order_id)]

    def _close_all(self, state, reason):
        out = []
        for order_id in self._trip.sequence:
            current = self._trip.orders[order_id].state
            if current in _TERMINAL:
                continue
            # HOLD_RETURN 은 봉투가 상판 칸에 있는 주문만이다(ADR 주문 상태 절). 아직 안 실은
            # 주문(ACCEPTED·DISPENSED)은 같은 이유로 ABORT 다. TIMEOUT 은 그대로 둔다.
            closing = ABORT if state == HOLD_RETURN and current != ORDER_LOADED else state
            out += self._close_order(order_id, closing, reason)
        return out

    def _finish(self, docked=True):
        """Deliver 결과. 주장 success 는 모든 주문 DELIVERED 이고 도크에 돌아왔을 때만이다."""
        self._undocked = not docked
        self._redocking = False
        states = self.order_states()
        success = docked and bool(states) and all(s == ORDER_DELIVERED for s in states.values())
        self._goto(IDLE)
        return [Finish(success)]

    def _undispensed(self):
        return [oid for oid in self._trip.sequence
                if self._trip.orders[oid].state == ORDER_ACCEPTED]

    def _next_undispensed(self):
        pending = self._undispensed()
        return pending[0] if pending else None

    def _loaded(self):
        return [oid for oid in self._trip.sequence
                if self._trip.orders[oid].state == ORDER_LOADED]

    def _current_stop(self):
        """지금 정거장. 정거장을 다 돌았으면 None. 조회만 한다(stop_index 를 옮기지 않는다)."""
        if self._trip.stop_index < len(self._trip.stops):
            return self._trip.stops[self._trip.stop_index]
        return None

    def _skip_empty_stops(self):
        """실은 주문이 없는 정거장(적재 실패 등)을 건너뛴다. 출발 직전에만 부른다.

        조회 중에 건너뛰면 한 침상을 끝낸 DELIVERING 이 다음 침상 주문을 이동·인증 없이 집는다(ADR 0001 대조 1).
        """
        loaded = set(self._loaded())
        while self._trip.stop_index < len(self._trip.stops):
            if loaded.intersection(self._trip.stops[self._trip.stop_index].order_ids):
                return
            self._trip.stop_index += 1

    def _orders_at_stop(self):
        stop = self._current_stop()
        if stop is None:
            return []
        return [oid for oid in stop.order_ids if self._trip.orders[oid].state == ORDER_LOADED]

    def _next_at_stop(self):
        pending = self._orders_at_stop()
        return pending[0] if pending else None
