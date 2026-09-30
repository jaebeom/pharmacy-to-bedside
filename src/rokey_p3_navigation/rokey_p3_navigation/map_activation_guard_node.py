"""map_activation_guard: map_server 가 active 가 될 때까지 보고, 안 되면 직접 올린다(`map_activation.py`).

- 부르는 것: `map_server/get_state`, `map_server/change_state` (lifecycle_msgs). 같은 네임스페이스(amr_1).
- 정상 회차에서는 한 줄(`map_guard map_server active … 개입 없음`)만 남기고 끝난다.
- 직접 전이를 보낼 때·포기할 때 관제 웹 알림(`/p3/alerts`, MAP_GUARD_INTERVENE·MAP_GUARD_GIVEUP)도 낸다.
"""

import time

import rclpy
from lifecycle_msgs.msg import Transition
from lifecycle_msgs.srv import ChangeState, GetState
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String

from rokey_p3_navigation import alerts
from rokey_p3_navigation import map_activation as guard

_NAMES = {guard.UNCONFIGURED: 'unconfigured', guard.INACTIVE: 'inactive', guard.ACTIVE: 'active'}


class MapActivationGuard(Node):
    def __init__(self):
        super().__init__('map_activation_guard')
        target = str(self.declare_parameter('target', 'map_server').value)
        self._wait = float(self.declare_parameter('wait_s', guard.WAIT_S).value)
        self._max = int(self.declare_parameter('max_transitions', guard.MAX_TRANSITIONS).value)
        self._get = self.create_client(GetState, f'{target}/get_state')
        self._change = self.create_client(ChangeState, f'{target}/change_state')
        self._target = self.resolve_topic_name(target)
        self._robot = self.get_namespace().strip('/') or 'amr_1'
        self._alert_pub = self.create_publisher(String, alerts.TOPIC, QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST, depth=alerts.QOS_DEPTH))
        self._started_at = time.monotonic()        # 벽시계 — 기동 중에는 /clock 이 아직 없을 수 있다
        self._pending = None
        self._pending_since = None
        self._timeouts = 0
        self._sent = 0
        self._timer = self.create_timer(1.0, self._tick)
        self.get_logger().info(f'map_guard up: {self._target} 가 {self._wait:g} s 안에 active 가 아니면 직접 올린다')

    def _alert(self, kind, detail):
        msg = String()
        msg.data = alerts.encode(kind, self._robot, detail, self.get_clock().now().nanoseconds * 1e-9, time.time())
        self._alert_pub.publish(msg)

    def _elapsed(self):
        return time.monotonic() - self._started_at

    def _tick(self):
        if self._pending is not None:
            if not guard.pending_expired(self._pending_since, self._elapsed()):
                return
            # 응답이 안 온다 — 이 호출을 버리고 다시 본다(버린 호출의 늦은 응답은 _current 가 걸러낸다).
            self._timeouts += 1
            self._pending.cancel()
            self._pending = None
            if self._timeouts >= guard.MAX_TIMEOUTS:
                self.get_logger().error(f'map_guard 포기: {self._target} 서비스 응답이 {self._timeouts}번 '
                                        f'{guard.PENDING_TIMEOUT_S:g} s 안에 안 왔다')
                self._alert(alerts.MAP_GUARD_GIVEUP, f'{self._target} 서비스 응답 없음 {self._timeouts}번')
                self._timer.cancel()
                return
            self.get_logger().warn(f'map_guard {self._target} 응답 {guard.PENDING_TIMEOUT_S:g} s 넘게 없음 '
                                   f'({self._timeouts}/{guard.MAX_TIMEOUTS}) — 버리고 상태를 다시 본다')
        if not self._get.service_is_ready():
            return
        self._await(self._get.call_async(GetState.Request()), self._on_state)

    def _await(self, future, callback):
        self._pending = future
        self._pending_since = self._elapsed()
        future.add_done_callback(lambda done: callback(done) if done is self._pending else None)

    def _on_state(self, future):
        self._pending = None
        if future.cancelled():
            return
        result = future.result()
        if result is None:
            return
        state = result.current_state.id
        elapsed = self._elapsed()
        if state == guard.ACTIVE:
            how = '관리자가 올렸다, 개입 없음' if self._sent == 0 else f'직접 전이 {self._sent}번 뒤'
            self.get_logger().info(f'map_guard {self._target} active after {elapsed:.1f} s ({how})')
            self._timer.cancel()
            return
        transition = guard.next_transition(state, elapsed, self._wait)
        if transition is None:
            return
        if self._sent >= self._max:
            self.get_logger().error(f'map_guard 포기: {self._target} 가 {elapsed:.1f} s 뒤에도 '
                                    f'{_NAMES.get(state, state)} — 직접 전이 {self._sent}번. 지도가 안 나온다')
            self._alert(alerts.MAP_GUARD_GIVEUP, f'{self._target} {_NAMES.get(state, state)} after {elapsed:.1f} s, '
                                                 f'직접 전이 {self._sent}번')
            self._timer.cancel()
            return
        self._sent += 1
        self.get_logger().warn(f'map_guard {self._target} {_NAMES.get(state, state)} after {elapsed:.1f} s — '
                               f'lifecycle_manager 가 못 올렸다(회차133). 직접 '
                               f'{"configure" if transition == guard.CONFIGURE else "activate"} 를 보낸다')
        self._alert(alerts.MAP_GUARD_INTERVENE,
                    f'{self._target} {_NAMES.get(state, state)} after {elapsed:.1f} s — 직접 '
                    f'{"configure" if transition == guard.CONFIGURE else "activate"}')
        request = ChangeState.Request()
        request.transition = Transition(id=transition)
        self._await(self._change.call_async(request), self._on_changed)

    def _on_changed(self, future):
        self._pending = None
        if future.cancelled():
            return
        result = future.result()
        if result is not None and not result.success:
            self.get_logger().warn(f'map_guard {self._target} 전이 거부됨 — 다음 틱에 상태를 다시 본다')


def main(args=None):
    rclpy.init(args=args)
    node = MapActivationGuard()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
