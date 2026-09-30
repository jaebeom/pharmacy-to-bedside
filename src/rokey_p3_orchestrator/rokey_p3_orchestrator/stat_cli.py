"""STAT S0 합성 입력·실행 CLI. ROS 를 import 하지 않는다. 재현 절차는 docs/runbooks/stat-s0-stub.md.

    python3 -m rokey_p3_orchestrator.stat_cli --dir <작업 폴더> init
    ... demo            합성 관측 → 합성 승인 → 접수(같은 요청 재전송 포함)
    ... run [--crash-at after_send:DISPENSE]
    ... inject drop_ack:DISPENSE [--times 1]
    ... cancel STAT-0001
    ... status

원장(stat.db)과 stub 세계(world.json)는 --dir 아래에 둔다. 저장소 밖 임시 폴더를 쓴다.
--crash-at 은 그 지점에서 프로세스를 os._exit(70) 으로 끝낸다(정리 코드 없이). 다음 run 이 재시작이다.
시계: 승인 만료는 time.time, 시한·관측 나이는 time.monotonic(같은 호스트 안에서만 비교한다).
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

from rokey_p3_orchestrator import stat_stub as S
from rokey_p3_orchestrator.stat_dispatch import OPEN, StatDispatcher
from rokey_p3_orchestrator.stat_intake import (
    ApprovalRecord, EmergencyObservation, OrderRequest, ingest_observation, record_approval, submit_order)
from rokey_p3_orchestrator.stat_ledger import StatLedger

CRASH_EXIT = 70
PODS = {'POD-1': 'SIM-KIT-A', 'POD-2': 'SIM-KIT-A'}
STATIONS = ('STN-3F-A', 'STN-3F-B')


def _open(folder):
    ledger = StatLedger(folder / 'stat.db')
    world = S.StubWorld(folder / 'world.json', time.monotonic)
    return ledger, world


def cmd_init(folder, args):
    folder.mkdir(parents=True, exist_ok=True)
    S.StubWorld.create(folder / 'world.json', time.monotonic, PODS, STATIONS)
    ledger, _ = _open(folder)
    seeded = ledger.seed_pods([{'pod_id': p, 'kit_id': k, 'kit_revision': 'k1'} for p, k in PODS.items()])
    return {'seeded': seeded, 'pods': [p['pod_id'] for p in ledger.pods()]}


def cmd_demo(folder, args):
    ledger, _ = _open(folder)
    now = time.time()
    incident, _ = ingest_observation(ledger, EmergencyObservation(
        'cam-402', 'boot-1', args.seq, 'R402', 'B1', now, ('fall_suspected',)))
    approval_id = f'APR-{args.seq}'
    record_approval(ledger, ApprovalRecord(approval_id, 'r1', incident, 'synthetic_charge_nurse', 'SUBJ-SIM-01',
                                           'SIM-KIT-A', 'k1', args.dest, now, now + 600.0))
    req = OrderRequest(f'REQ-{args.seq}', incident, approval_id, 'r1', 'SUBJ-SIM-01', 'SIM-KIT-A', 'k1', args.dest)
    first = submit_order(ledger, req, now)
    again = submit_order(ledger, req, now)                          # 응답을 못 받았다고 보고 다시 보낸다
    return {'incident': incident, 'first': first._asdict(), 'resend': again._asdict()}


def cmd_run(folder, args):
    ledger, world = _open(folder)
    dispatcher = StatDispatcher(ledger, world, time.time, time.monotonic, result_timeout_s=args.result_timeout)
    point, _, kind = (args.crash_at or '').partition(':')

    def crash(where, op_id):
        if where == point and op_id.endswith(f'/{kind}'):
            sys.stdout.write(json.dumps({'crash': where, 'op_id': op_id}) + '\n')
            sys.stdout.flush()
            os._exit(CRASH_EXIT)
    dispatcher.crash = crash
    generation = dispatcher.start()
    deadline = time.monotonic() + args.max_seconds
    while time.monotonic() < deadline:
        if not dispatcher.tick():
            if not _open_ops(ledger):
                break
            time.sleep(0.05)
    return {'generation': generation, **_status(ledger, world)}


def _open_ops(ledger):
    return [o['current_op'] for o in ledger.orders()
            if o['current_op'] and ledger.op(o['current_op'])['status'] in OPEN]


def cmd_inject(folder, args):
    _, world = _open(folder)
    world.inject(args.fault, args.times)
    return {'faults': world.state['faults']}


def cmd_cancel(folder, args):
    ledger, world = _open(folder)
    reason = StatDispatcher(ledger, world, time.time, time.monotonic).cancel(args.order_id)
    return {'order_id': args.order_id, 'refused': reason}


def cmd_status(folder, args):
    ledger, world = _open(folder)
    return _status(ledger, world)


def _status(ledger, world):
    keep = ('order_id', 'state', 'reason', 'mission', 'pod_id', 'current_op')
    return {
        'orders': [{k: o[k] for k in keep} for o in ledger.orders()],
        'pods': [{k: p[k] for k in ('pod_id', 'custody', 'holder', 'hold')} for p in ledger.pods()],
        'world_applied': world.state['applied'],
        'world_pods': world.state['pods'],
        'events': [f"{e['seq']} {e['name']} {e['order_id']}" for e in ledger.events()],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description='STAT S0 stub 재현(L1, ROS 없음)')
    parser.add_argument('--dir', required=True, type=Path, help='원장·세계 파일 폴더(저장소 밖)')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('init')
    demo = sub.add_parser('demo')
    demo.add_argument('--seq', type=int, default=1)
    demo.add_argument('--dest', default=STATIONS[0], choices=STATIONS)
    run = sub.add_parser('run')
    run.add_argument('--crash-at', default='', help='after_intent|after_send|before_commit:<KIND>')
    run.add_argument('--max-seconds', type=float, default=10.0)
    run.add_argument('--result-timeout', type=float, default=5.0)
    inject = sub.add_parser('inject')
    inject.add_argument('fault')
    inject.add_argument('--times', type=int, default=1)
    cancel = sub.add_parser('cancel')
    cancel.add_argument('order_id')
    sub.add_parser('status')
    args = parser.parse_args(argv)
    handler = {'init': cmd_init, 'demo': cmd_demo, 'run': cmd_run, 'inject': cmd_inject, 'cancel': cmd_cancel,
               'status': cmd_status}[args.command]
    print(json.dumps(handler(args.dir, args), ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
