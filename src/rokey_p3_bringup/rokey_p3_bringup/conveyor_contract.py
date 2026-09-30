"""컨베이어↔팔 경계의 기준 판정기. 배송 계약 v1 11절(@ dc172d1)을 코드로 옮긴 것이다. ROS 를 import 하지 않는다.

운영 노드가 아니다. 계약 문장을 한 가지로 읽는 참조 구현이다.
- 시험 벡터(`rokey_p3_interfaces/contract_vectors/conveyor_arm/v1/`)의 기대값은 이 판정기와 같아야 한다.
- 각 구현(Isaac 스테이지·stub_sim·trip_fsm)은 같은 벡터를 자기 러너로 돌린다.
  아직 못 맞추는 벡터는 그 러너에 expected failure 로 표시하고, 고치는 PR 에서 표시를 뗀다.

opt-in 두 가지는 계약 11.1 의 (제안·미확정) 항목이다. 기본값은 계약의 "현재" 동작이다.
- `fail_closed`: frame 누락·벨트 밖 이탈(`held` 아님)에서 `occupied=true` 를 유지한다.
- `speed_missing_resets_settle`: 속도 미수신(None)은 정착 표본이 아니고 정착 타이머를 초기화한다.
"""

import json
from pathlib import Path

BELT_OCCUPIED = 'belt_occupied'
POSITIONS = ('mid', 'end', 'off', 'lost')   # 벨트 중간, 종단 구역, 벨트 부피 밖, frame 없음
OPTIONS = ('fail_closed', 'speed_missing_resets_settle')
STEP_INPUTS = ('dispense', 'pouch', 'pick_notice', 'reset')
EXPECT_KEYS = ('accepted', 'message', 'dispensed', 'occupied', 'at_end', 'order_id')


class BeltReference:
    """벨트 backend 하나(계약 11.1·11.2). 입력은 벡터의 step 이고 출력은 그 step 뒤의 관측값이다."""

    def __init__(self, settle_speed, settle_time_s, epoch=1, **options):
        unknown = sorted(set(options) - set(OPTIONS))
        if unknown:
            raise ValueError(f'모르는 옵션 {unknown}. 있는 것: {OPTIONS}')
        self.settle_speed = settle_speed
        self.settle_time_s = settle_time_s
        self.fail_closed = bool(options.get('fail_closed', False))
        self.speed_missing_resets_settle = bool(options.get('speed_missing_resets_settle', False))
        self.epoch = epoch
        self._clear()

    def _clear(self):
        self.occupied = False
        self.at_end = False
        self.order_id = ''
        self.request_id = ''
        self.tracking = False       # 봉투를 지금 관측하고 있나(소실되면 false)
        self.running = False        # STOP 명령 전이면 true. 관측이 아니라 명령 상태다
        self._settle_since = None

    def state(self):
        return {'occupied': self.occupied, 'at_end': self.at_end, 'order_id': self.order_id}

    def step(self, t, step):
        """step 하나를 적용하고 관측값을 돌려준다. dispense 이면 응답(accepted, message, dispensed)이 붙는다."""
        kinds = [k for k in STEP_INPUTS if k in step]
        if len(kinds) != 1:
            raise ValueError(f'step 에는 입력이 하나만 있어야 한다: {sorted(step)}')
        kind = kinds[0]
        out = getattr(self, '_' + kind)(t, step[kind]) or {}
        return {**self.state(), **out}

    def _dispense(self, t, request):
        same = (request['request_id'], request['order_id']) == (self.request_id, self.order_id)
        if self.occupied:
            if same and self.tracking:
                # 11.2 목표: 추적 중인 같은 요청의 재전송은 같은 결과. DISPENSED 는 다시 내지 않는다.
                return {'accepted': True, 'message': '', 'dispensed': 0}
            return {'accepted': False, 'message': BELT_OCCUPIED, 'dispensed': 0}
        self._clear()
        self.occupied = self.tracking = self.running = True
        self.order_id = request['order_id']
        self.request_id = request['request_id']
        return {'accepted': True, 'message': '', 'dispensed': 1}

    def _pouch(self, t, obs):
        at, speed, held = obs['at'], obs.get('speed'), bool(obs.get('held', False))
        if at not in POSITIONS:
            raise ValueError(f'at={at!r} 는 {POSITIONS} 가 아니다')
        if not self.occupied:
            return
        if held:
            # 11.1 (a): 쥐고 있고 벨트 부피 밖이어야 해제. 파지 첫 순간(아직 벨트 위)은 해제가 아니다.
            if at == 'off':
                self._clear()
            else:
                self.tracking = True
            return
        if at in ('lost', 'off'):
            # 해제 조건이 아닌 것. 현재 동작은 해제, fail_closed 면 점유 유지.
            self.tracking = False
            self.at_end = False
            self.running = False
            self._settle_since = None
            if not self.fail_closed:
                self.occupied = False
                self.order_id = ''
            return
        self.tracking = True
        if at == 'mid':
            self._settle_since = None
            return
        if self.running:
            self.running = False        # 종단 구역 진입 = STOP 명령
        if self.at_end:
            return                      # 래치
        if speed is None:
            if self.speed_missing_resets_settle:
                self._settle_since = None
                return
            speed = 0.0                 # 현재 stage: 미수신을 0 으로 센다
        if speed <= self.settle_speed:
            if self._settle_since is None:
                self._settle_since = t
            if t - self._settle_since >= self.settle_time_s:
                self.at_end = True
        else:
            self._settle_since = None

    def _pick_notice(self, t, notice):
        # 11.1 (b) 스텁 회수. 계약 epoch·벨트 끝 봉투·같은 주문일 때만(bridge.pick_notice_applies 와 같은 규칙).
        if notice['epoch'] == self.epoch and self.at_end and notice['order_id'] == self.order_id:
            self._clear()

    def _reset(self, t, reset):
        # 11.1 (c) 리셋 barrier 의 회수.
        self.epoch = reset['epoch']
        self._clear()


PICK_RESULTS = ('ok', 'failed', 'pending')
ARM_CLEAR = ('CLEAR', 'INTRUDING', 'UNKNOWN')
PLACEMENT = ('confirmed', 'unconfirmed')


def pick_allowed(case):
    """계약 5절 `source=BELT` 피킹 허가(11.1 의 `at_end` 뜻). None 은 unknown·stale 이고 허가가 아니다."""
    belt = case['belt']
    if case['base_stopped'] is not True or belt is None:
        return False
    return belt['at_end'] is True and bool(case['goal_order_id']) and belt['order_id'] == case['goal_order_id']


def next_dispense_allowed(case, next_dispense_guard=False):
    """계약 11.3 다음 배출 허가. None 은 unknown·stale·토픽 없음이고 허가가 아니다.

    현재(기본): 벨트가 비었고(신선) 이전 PickPouch 가 종결됐다(ok 든 실패든). 트립 FSM 은 픽 결과 전에 배출하지 않는다.
    `next_dispense_guard`(11.3 opt-in, 기본 적용 시점 미확정): 픽 `ok` + 칸 안착 확인 + `arm_clear_of_belt=CLEAR` 도 참.
    """
    if case['belt_occupied'] is not False:
        return False
    if not next_dispense_guard:
        return case['pick'] in ('ok', 'failed')
    return case['pick'] == 'ok' and case['placement'] == 'confirmed' and case['arm_clear'] == 'CLEAR'


def load_vectors(directory, boundary):
    """허가 경계 하나의 벡터 파일(dispense·pick·next_dispense)을 읽는다.

    위치는 부르는 쪽이 준다. 설치본의 이 모듈 위치로는 소스 트리의 벡터를 찾을 수 없다.
    """
    path = Path(directory) / f'{boundary}.json'
    return json.loads(path.read_text(encoding='utf-8'))


def run_belt_vector(params, vector):
    """벡터 하나를 판정기에 돌린다. [(step 번호, 기대, 실제)] 중 어긋난 것만 돌려준다."""
    belt = BeltReference(params['settle_speed'], params['settle_time_s'], **vector.get('options', {}))
    mismatches = []
    for index, step in enumerate(vector['steps']):
        expect = step.get('expect', {})
        actual = belt.step(step['t'], {k: v for k, v in step.items() if k in STEP_INPUTS})
        got = {key: actual.get(key) for key in expect}
        if got != expect:
            mismatches.append((index, expect, got))
    return mismatches
