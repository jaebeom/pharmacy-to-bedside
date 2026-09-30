"""레일 보충 v2 연속 구동기. `/m0609/refill` goal 을 정한 시간 동안 연달아 보낸다(재범 9/18: 5분 연속 투입).

계약 v1·`Refill` 액션 타입은 그대로다. orchestrator 없이 팔 노드만 시험할 때 쓴다(orchestrator 와 같이 띄우지 않는다).

- goal 마다 한 줄: 시각(wall), 몇 번째, item, slot, 종류·칸(팔 feedback 의 `plan …` 줄에서), 결과, 소요 s.
- 끝에 요약: 보낸 수, 성공, 실패(이유별), 평균·최대 소요, 종류별 성공.
- item·slot 은 파라미터 목록에서 시드 랜덤으로 고른다(같은 시드면 같은 순서).
- `out_file` 을 주면 줄마다 JSON 도 남긴다.
"""

import json
import random
import time

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from rokey_p3_interfaces.action import Refill

from rokey_p3_manipulation.soak_report import parse_plan, summarize

class RefillSoak(Node):
    def __init__(self):
        super().__init__('refill_soak')
        self.declare_parameter('duration_s', 300.0)          # wall. 끝나면 진행 중 goal 결과까지 기다린다
        self.declare_parameter('item_ids', ['drug-ibu'])
        self.declare_parameter('slots', [0, 1])
        self.declare_parameter('seed', 0)
        self.declare_parameter('goal_timeout_s', 120.0)      # wall. 넘으면 cancel 하고 실패로 센다
        self.declare_parameter('server_wait_s', 30.0)
        self.declare_parameter('out_file', '')
        self._duration = float(self.get_parameter('duration_s').value)
        self._items = list(self.get_parameter('item_ids').value)
        self._slots = [int(s) for s in self.get_parameter('slots').value]
        self._seed = int(self.get_parameter('seed').value)
        self._goal_timeout = float(self.get_parameter('goal_timeout_s').value)
        self._server_wait = float(self.get_parameter('server_wait_s').value)
        self._out = self.get_parameter('out_file').value
        self._rng = random.Random(self._seed)
        self._client = ActionClient(self, Refill, '/m0609/refill')
        self._plan = None

    def _on_feedback(self, message):
        plan = parse_plan(message.feedback.phase)
        if plan is not None:
            self._plan = plan

    def _wait(self, future, limit_s):
        deadline = time.monotonic() + limit_s
        while rclpy.ok() and not future.done() and time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)
        return future.done()

    def run_once(self, index):
        item = self._rng.choice(self._items)
        slot = self._rng.choice(self._slots)
        self._plan = None
        started = time.monotonic()
        goal = Refill.Goal(item_id=item, slot=slot)
        sent = self._client.send_goal_async(goal, feedback_callback=self._on_feedback)
        row = {'index': index, 'wall': time.strftime('%H:%M:%S'), 'item': item, 'slot': slot}
        if not self._wait(sent, 10.0) or not sent.result().accepted:
            row.update(success=False, reason='rejected', seconds=round(time.monotonic() - started, 2))
            return row
        handle = sent.result()
        result = handle.get_result_async()
        if not self._wait(result, self._goal_timeout):
            handle.cancel_goal_async()
            self._wait(result, 10.0)
            reason = 'timeout'
            success = False
        else:
            success = bool(result.result().result.success)
            reason = '' if success else f'status {result.result().status}'
        plan = self._plan or {}
        row.update(kind=plan.get('kind', ''), cell=plan.get('cell', ''), seed=plan.get('seed', ''),
                   draw=plan.get('draw', ''), success=success, reason=reason,
                   seconds=round(time.monotonic() - started, 2))
        return row

    def run(self):
        if not self._client.wait_for_server(timeout_sec=self._server_wait):
            self.get_logger().error(f'/m0609/refill 서버가 {self._server_wait} s 안에 안 보인다.')
            return []
        rows = []
        end = time.monotonic() + self._duration
        self.get_logger().info(f'연속 구동 시작: {self._duration:g} s, item={self._items} slot={self._slots} '
                               f'seed={self._seed}')
        while rclpy.ok() and time.monotonic() < end:
            row = self.run_once(len(rows) + 1)
            rows.append(row)
            self.get_logger().info(
                f"#{row['index']} {row['wall']} item={row['item']} slot={row['slot']} kind={row.get('kind', '')} "
                f"cell={row.get('cell', '')} {'ok' if row['success'] else 'FAIL ' + row['reason']} "
                f"{row['seconds']:.1f} s")
            if self._out:
                with open(self._out, 'a', encoding='utf-8') as handle:
                    handle.write(json.dumps(row, ensure_ascii=False) + '\n')
        summary = summarize(rows)
        self.get_logger().info(f'요약: {json.dumps(summary, ensure_ascii=False)}')
        if self._out:
            with open(self._out, 'a', encoding='utf-8') as handle:
                handle.write(json.dumps({'summary': summary}, ensure_ascii=False) + '\n')
        return rows


def main(args=None):
    rclpy.init(args=args)
    node = RefillSoak()
    try:
        node.run()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
