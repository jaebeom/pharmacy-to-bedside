"""한 바퀴의 이벤트 순서를 ROS 없이 확인한다.

여기 있는 World 는 **가짜**다. 스텁 노드의 규칙 셋을 그대로 옮겨 놓은 것이다:

1. 팔은 액션 결과를 먼저 돌려주고 홈 복귀를 그 뒤에 끝낸다. 그래서 ARM_HOME 이
   LOAD_DONE·ORDER_DONE 뒤에 온다.
2. 인식은 AUTH_OK 를 보고 나서 POUCH_DETECTED 를 낸다.
3. 팔은 상판 픽 전에 검출을 기다린다.

이 셋이 맞으면 계약 2.6절의 스물한 줄이 그대로 나온다는 것을 여기서 잡는다.
진짜 L2 는 rokey_p3_bringup/test/test_stub_loop.py 이고 ROS 가 있어야 돈다.
"""

from collections import deque

from rokey_p3_orchestrator import trip_fsm as fsm

CONTRACT_ORDER = [
    'REQUEST_ACCEPTED', 'AMR_DOCKED_LOAD', 'DISPENSED', 'POUCH_AT_END',
    'PICK_ATTEMPT', 'POUCH_PICKED', 'POUCH_LOADED', 'LOAD_DONE', 'ARM_HOME',
    'DEPARTED', 'ARRIVED', 'AUTH_OK', 'POUCH_DETECTED',
    'PICK_ATTEMPT', 'POUCH_PICKED', 'POUCH_PLACED', 'CABINET_LOCKED', 'ORDER_DONE',
    'ARM_HOME', 'RETURNED', 'DOCKED',
]

#: pharmacy_only 한 바퀴. LOAD_DONE 뒤 정거장 없이 주문을 닫고 도크로 간다.
PHARMACY_ONLY_ORDER = [
    'REQUEST_ACCEPTED', 'AMR_DOCKED_LOAD', 'DISPENSED', 'POUCH_AT_END',
    'PICK_ATTEMPT', 'POUCH_PICKED', 'POUCH_LOADED', 'LOAD_DONE', 'ORDER_DONE',
    'ARM_HOME', 'RETURNED', 'DOCKED',
]

ORDER = 'ord-0001'
REQUEST = {
    'request_id': 'r001-0001',
    'mode': fsm.MODE_SINGLE,
    'destination_id': 'bed_a1',
    'orders': [{'order_id': ORDER, 'patient_id': '1001', 'item_id': 'drug-amox'}],
}


class ArmHome:
    """팔이 홈에 닿았다. 액션 결과보다 늦게 온다."""


class World:
    """스텁 넷의 규칙만 흉내 낸 가짜. ROS 는 없다."""

    def __init__(self, config=None):
        self.machine = fsm.TripFsm(config=config, patient_beds={'1001': 'bed_a1'})
        self.machine.tick(0.0)
        self.events = []
        self.finished = None
        self._belt = {'occupied': False, 'at_end': False, 'order_id': ''}
        self.machine.state_update(fsm.AT_HOME, True, True)
        self.machine.state_update(fsm.BASE_STOPPED, True, True)
        self.machine.state_update(fsm.BELT, dict(self._belt), True)

    def run(self, commands):
        """단일 스레드 실행기처럼 명령과 그 응답을 선입선출로 처리한다."""
        queue = deque(commands)
        while queue:
            queue.extend(self._handle(queue.popleft()))

    def _belt_update(self, **changes):
        self._belt.update(changes)
        return self.machine.state_update(fsm.BELT, dict(self._belt), True)

    def _handle(self, command):
        if isinstance(command, ArmHome):
            self.events.append('ARM_HOME')
            return self.machine.state_update(fsm.AT_HOME, True, True)
        if isinstance(command, fsm.Emit):
            self.events.append(command.event)
            if command.event == fsm.EVENT_AUTH_OK:
                self.events.append('POUCH_DETECTED')      # 인식이 AUTH_OK 뒤에 낸다
            return []
        if isinstance(command, fsm.Finish):
            self.finished = command
            return []
        if isinstance(command, fsm.Call):
            return self._dispense(command)
        if isinstance(command, fsm.SendGoal):
            return self._goal(command)
        return []

    def _dispense(self, command):
        self.events.append('DISPENSED')
        out = self.machine.result(fsm.DISPENSE, fsm.ACCEPTED)
        out += self._belt_update(occupied=True, at_end=False, order_id=command.request['order_id'])
        self.events.append('POUCH_AT_END')
        return out + self._belt_update(at_end=True)

    def _goal(self, command):
        if command.action == fsm.GO_TO_ZONE:
            out = self.machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
            return out + self.machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
        if command.action == fsm.SCAN_TAG:
            # 스캔은 홈을 벗어나지만 바로 전달 픽으로 이어져서 ARM_HOME 이 없다.
            out = self.machine.state_update(fsm.AT_HOME, False, True)
            out += self.machine.result(fsm.SCAN_TAG, fsm.ACCEPTED)
            return out + self.machine.result(fsm.SCAN_TAG, fsm.OK, {'tag_id': 'pt-1001'})

        from_belt = command.goal['source'] == fsm.SOURCE_BELT
        out = self.machine.state_update(fsm.AT_HOME, False, True)
        self.events += ['PICK_ATTEMPT', 'POUCH_PICKED']
        if from_belt:
            out += self._belt_update(occupied=False, at_end=False, order_id='')
            self.events.append('POUCH_LOADED')
        else:
            self.events.append('POUCH_PLACED')
        out += self.machine.result(fsm.PICK_POUCH, fsm.ACCEPTED)
        out += self.machine.result(fsm.PICK_POUCH, fsm.OK)
        return out + [ArmHome()]        # 홈 복귀는 결과 뒤에 끝난다


def test_one_lap_prints_the_contract_2_6_sequence():
    world = World()
    world.run(world.machine.request(REQUEST))
    assert world.events == CONTRACT_ORDER


def test_one_lap_finishes_with_the_delivered_claim():
    world = World()
    world.run(world.machine.request(REQUEST))
    assert world.finished == fsm.Finish(True)
    assert world.machine.order_states() == {ORDER: 'DELIVERED'}
    assert world.machine.state == fsm.IDLE


def test_pharmacy_only_lap_order_and_hold_return():
    world = World(fsm.TripConfig(pharmacy_only=True))
    world.run(world.machine.request(REQUEST))
    assert world.events == PHARMACY_ONLY_ORDER
    assert world.finished == fsm.Finish(False)
    assert world.machine.order_states() == {ORDER: 'HOLD_RETURN'}
