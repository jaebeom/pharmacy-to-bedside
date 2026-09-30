"""STAT S0 stub 세계: 디스펜서·탑재·기체·수납 스테이션의 가짜 물리 상태와 장치 쪽 op 기록. ROS 를 import 하지 않는다.

계약 4·5·6절(docs/architecture/stat-delivery-contract-v1.md, proposed). 센서 정확도나 물리 성공의 근거가 아니다(L1).

- 명령 수락(send), 물리 적용(_apply), 결과 전달(query)을 나눈다. 그래서 "적용됐는데 응답만 사라진" 경우를 만들 수 있다.
- 상태는 원장과 다른 JSON 파일에 원자적으로 쓴다. 오케스트레이터가 재시작해도 물리 상태는 그대로다.
- applied 는 실제로 물리 상태를 바꾼 횟수다. 시험은 반환값이 아니라 이 값과 위치를 본다.
- 고장은 faults[이름] = 남은 횟수(-1 은 계속)로 주입한다. 파일에 있으므로 다른 프로세스에서도 주입할 수 있다.
"""

import json
import os
from dataclasses import dataclass

DISPENSE = 'DISPENSE'
LOAD = 'LOAD'
FLY = 'FLY'
RELEASE = 'RELEASE'
RETURN = 'RETURN'
KINDS = (DISPENSE, LOAD, FLY, RELEASE, RETURN)

# 장치 op 상태(query 답)
DEV_ACCEPTED = 'ACCEPTED'
DEV_APPLIED = 'APPLIED'
DEV_FAILED = 'FAILED'
DEV_REJECTED = 'REJECTED'
DEV_UNKNOWN_OPERATION = 'UNKNOWN_OPERATION'
DEV_EXECUTION_UNKNOWN = 'EXECUTION_UNKNOWN'

# 물리 위치
AT_SOURCE = 'SOURCE'
AT_PICKUP = 'PICKUP_STAGE'
AT_DRONE = 'DRONE'
AT_RECEIVER = 'RECEIVER'


class ResponseLost(Exception):
    """장치는 무언가 했을 수 있지만 응답이 오지 않았다."""


@dataclass(frozen=True)
class Command:
    op_id: str
    kind: str
    pod_id: str
    target: str          # FLY·RELEASE 의 목적지 스테이션. 나머지는 빈 값
    epoch: int
    generation: int
    command_seq: int


@dataclass(frozen=True)
class Ack:
    op_id: str
    status: str
    reason: str = ''


@dataclass(frozen=True)
class Observation:
    """한 대상의 표본. location·holder 는 Pod 와 기체, occupants 는 스테이션에 쓴다."""

    subject: str
    location: str
    holder: str
    occupants: tuple
    boot_id: str
    seq: int
    stamp: float


class StubWorld:
    """S0 stub 장치 묶음. 기체 1대, 도크 1곳, 픽업 스테이지 1칸, 스테이션마다 수납 1칸."""

    def __init__(self, path, clock, drone_id='DRONE-1', dock_id='DOCK-1'):
        self.path = str(path)
        self.clock = clock
        self.drone_id = drone_id
        self.dock_id = dock_id
        self._cache = {}                     # 반복 표본 주입용 마지막 표본
        with open(self.path, encoding='utf-8') as f:
            self.state = json.load(f)

    @classmethod
    def create(cls, path, clock, pods, stations, boot_id='world-1', **kwargs):
        """새 세계 파일을 만든다. pods = {pod_id: kit_id}. 이미 있으면 덮지 않고 연다."""
        if not os.path.exists(path):
            state = {
                'boot_id': boot_id, 'seq': 0, 'max_generation': 0, 'records_lost': False,
                'pods': {p: {'location': AT_SOURCE, 'holder': AT_SOURCE, 'kit_id': k} for p, k in pods.items()},
                'drone': kwargs.get('dock_id', 'DOCK-1'), 'stations': list(stations),
                'ops': {}, 'applied': dict.fromkeys(KINDS, 0), 'faults': {},
            }
            _write(path, state)
        return cls(path, clock, **kwargs)

    def save(self):
        _write(self.path, self.state)

    def inject(self, name, times=1):
        self.state['faults'][name] = times
        self.save()

    def _fault(self, name):
        left = self.state['faults'].get(name, 0)
        if left == 0:
            return False
        if left > 0:
            self.state['faults'][name] = left - 1
        return True

    # 명령
    def send(self, cmd):
        """수락한다. 같은 op_id 는 다시 적용하지 않는다. 오래된 generation 은 거부한다."""
        if cmd.generation < self.state['max_generation']:
            return Ack(cmd.op_id, DEV_REJECTED, 'stale_generation')
        self.state['max_generation'] = cmd.generation
        op = self.state['ops'].get(cmd.op_id)
        if op is None:
            op = self.state['ops'][cmd.op_id] = {'kind': cmd.kind, 'status': DEV_ACCEPTED, 'pod_id': cmd.pod_id,
                                                 'target': cmd.target}
            if not self._fault(f'hold:{cmd.kind}'):
                self._apply(op)
        lost = self._fault(f'drop_ack:{cmd.kind}')
        self.save()
        if lost:
            raise ResponseLost(cmd.op_id)
        return Ack(cmd.op_id, op['status'])

    def apply_pending(self):
        """hold 로 미뤄 둔 op 를 적용한다(늦은 적용)."""
        for op in self.state['ops'].values():
            if op['status'] == DEV_ACCEPTED:
                self._apply(op)
        self.save()

    def query(self, op_id):
        op = self.state['ops'].get(op_id)
        lost = op is not None and self._fault(f'drop_result:{op["kind"]}')
        self.save()
        if lost:
            raise ResponseLost(op_id)
        if op is None:
            return DEV_EXECUTION_UNKNOWN if self.state['records_lost'] else DEV_UNKNOWN_OPERATION
        return op['status']

    def forget_records(self):
        """장치 실행기가 재시작해 op 기록을 잃은 경우. 물리 상태는 그대로다."""
        self.state['ops'] = {}
        self.state['records_lost'] = True
        self.save()

    def _apply(self, op):
        pods, kind = self.state['pods'], op['kind']
        pod = pods.get(op['pod_id'])
        ok = not self._fault(f'fail:{kind}')
        if ok and kind == DISPENSE:
            wrong = [p for p in sorted(pods) if p != op['pod_id'] and pods[p]['location'] == AT_SOURCE]
            if self._fault('wrong_pod') and wrong:
                pod = pods[wrong[0]]
            ok = pod['location'] == AT_SOURCE and not self._at(AT_PICKUP)
            if ok:
                pod.update(location=AT_PICKUP, holder=AT_PICKUP)
        elif ok and kind == LOAD:
            ok = pod['location'] == AT_PICKUP and self.state['drone'] == self.dock_id
            if ok:
                pod.update(location=AT_DRONE, holder=self.drone_id)
        elif ok and kind == FLY:
            others = [s for s in self.state['stations'] if s != op['target']]
            self.state['drone'] = others[0] if self._fault('wrong_station') and others else op['target']
        elif ok and kind == RELEASE:
            here = self.state['drone']
            ok = (pod['holder'] == self.drone_id and here in self.state['stations']
                  and not self._at(AT_RECEIVER, here))
            if ok:
                pod.update(location=AT_RECEIVER, holder=here)
        elif ok and kind == RETURN:
            self.state['drone'] = self.dock_id
        op['status'] = DEV_APPLIED if ok else DEV_FAILED
        if ok:
            self.state['applied'][kind] += 1

    def _at(self, location, holder=None):
        return [p for p, v in sorted(self.state['pods'].items())
                if v['location'] == location and (holder is None or v['holder'] == holder)]

    # 관측
    def observe(self, subject):
        """Pod id, 기체 id, 스테이션 id 또는 PICKUP_STAGE 의 표본. 호출마다 seq 가 오른다."""
        if self._fault('no_obs'):
            self.save()
            return None
        if self._fault('stale_obs') and subject in self._cache:
            self.save()
            return self._cache[subject]
        self.state['seq'] += 1
        pods = self.state['pods']
        if subject in pods:
            location, holder, occupants = pods[subject]['location'], pods[subject]['holder'], ()
        elif subject == self.drone_id:
            location = holder = self.state['drone']
            occupants = tuple(self._at(AT_DRONE))
        else:
            where = AT_PICKUP if subject == AT_PICKUP else AT_RECEIVER
            location = subject
            holder = self.drone_id if self.state['drone'] == subject else ''
            occupants = tuple(self._at(where, None if subject == AT_PICKUP else subject))
        sample = Observation(subject, location, holder, occupants, self.state['boot_id'], self.state['seq'],
                             self.clock())
        self._cache[subject] = sample
        self.save()
        return sample


def _write(path, state):
    tmp = f'{path}.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(state, f, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
