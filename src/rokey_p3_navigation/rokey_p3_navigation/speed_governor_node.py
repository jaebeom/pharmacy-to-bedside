"""speed_governor: 지역 코스트맵의 여유로 Nav2 속도 제한을 낸다.

재범 9/23: 넓은 복도에서 0.8–1.0 m/s, 장애물·문 근처에서만 0.5. 최고 속도를 올리고(`nav2_params.yaml`)
가까울 때만 다시 줄이는 방식이다 — 9/23 낮의 단순 두 배(#526)가 고정물 touch 로 되돌아간 것이 그 이유다(#547).

- 받는 것: `local_costmap/costmap` (`nav_msgs/OccupancyGrid`, rolling window라 한가운데가 로봇이다)
- 내는 것: `speed_limit` (`nav2_msgs/SpeedLimit`, `percentage=true`) — `controller_server` 의 `speed_limit_topic`

판단은 `speed_governor.py` 에 있다(ROS 없이 시험한다). 이 노드는 구독·계산·발행만 한다.
코스트맵이 아직 안 왔으면 **느린 쪽**을 먼저 보낸다 — 모르는 채로 빨라지지 않는다.
"""

import hashlib
import math

import rclpy
from nav2_msgs.msg import SpeedLimit
from nav_msgs.msg import OccupancyGrid, Odometry
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from rclpy.time import Time
from tf2_ros import Buffer, TransformException, TransformListener

from rokey_p3_navigation import speed_governor as governor


class SpeedGovernor(Node):
    """여유를 재서 속도 제한을 낸다."""

    def __init__(self):
        super().__init__('speed_governor')
        self._near = float(self.declare_parameter('near_m', governor.NEAR_M).value)
        self._far = float(self.declare_parameter('far_m', governor.FAR_M).value)
        # 근접 속도는 **m/s 로** 받는다. `nav2_params.yaml` 의 최고 속도를 올려도 근접 속도가 따라
        # 올라가지 않게 하려는 것이다(9/23 #526 → #547). 비율은 여기서 나온다.
        self._max_mps = float(self.declare_parameter('max_speed_mps', governor.MAX_SPEED_MPS).value)
        self._slow_mps = float(self.declare_parameter('slow_speed_mps', governor.SLOW_SPEED_MPS).value)
        self._slow = governor.slow_percent(self._slow_mps, self._max_mps)
        self._lethal = int(self.declare_parameter('lethal_cost', governor.LETHAL).value)
        self._step = float(self.declare_parameter('report_step_percent', 5.0).value)
        costmap_topic = str(self.declare_parameter('costmap_topic', 'local_costmap/costmap').value)
        limit_topic = str(self.declare_parameter('speed_limit_topic', 'speed_limit').value)
        if self._far <= self._near:
            raise ValueError(f'far_m({self._far}) 은 near_m({self._near}) 보다 커야 한다')

        self._sent = None
        self._percent = governor.limit_percent(None, self._near, self._far, self._slow)
        # **한 번만 내면 안 받는다.** `controller_server` 의 speed_limit 구독은 RELIABLE·VOLATILE 이라
        # 자기가 뜨기 전에 나간 래치 값을 못 받는다. 감속기는 nav2 lifecycle 밖이라 늘 먼저 뜬다 —
        # 9/23 회차(f8eac1c)가 그 자리다. 기동 때 낸 50% 를 controller_server 가 끝까지 못 받아
        # odom 최고·중앙이 1.00 m/s 였다(마클1 회차10: `--once` 로 읽힌 50 은 **내 발행자의 래치 값**이지
        # controller_server 가 받은 값이 아니다). TRANSIENT_LOCAL 은 VOLATILE 구독자를 못 구한다.
        # 그래서 값이 안 바뀌어도 `publish_period_s` 마다 다시 낸다.
        self._limit_pub = self.create_publisher(SpeedLimit, limit_topic, QoSProfile(
            depth=1, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST))
        # 구독은 **가장 헐한 쪽**으로 건다. 요청 QoS 가 발행 QoS 보다 세면 DDS 가 조용히 안 붙이고
        # 오류도 안 낸다 — 9/23 에 코스트맵이 한 장도 안 온 자리다(#594 는 원인을 잘못 짚었다).
        # BEST_EFFORT·VOLATILE 은 RELIABLE·TRANSIENT_LOCAL 발행자에도 붙는다(반대는 안 붙는다).
        # 2 Hz 권고값이라 한 장 놓쳐도 다음 장이 곧 온다.
        self.create_subscription(OccupancyGrid, costmap_topic, self._on_costmap, QoSProfile(
            depth=1, reliability=ReliabilityPolicy.BEST_EFFORT, durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST))
        self._seen = 0
        self.get_logger().info(
            f'speed_governor up. {self.resolve_topic_name(costmap_topic)} → '
            f'{self.resolve_topic_name(limit_topic)}. '
            f'여유 {self._near:g} m 이하 {self._slow:.0f}%={self._slow_mps:.2f} m/s, '
            f'{self._far:g} m 이상 100%={self._max_mps:.2f} m/s. '
            f'(거리 문턱은 고른 값이다. 근접 {self._slow_mps:.2f} m/s 는 #240 에서 잰 값이다)')
        self._free_m = None
        self._free_kind = None
        # 코스트맵이 끊기면 마지막 값을 계속 내지 않는다(`governor.is_stale`). 노드 시계(sim)로 잰다.
        self._stale_after = float(self.declare_parameter('stale_after_s', governor.STALE_AFTER_S).value)
        self._last_costmap_s = None
        self._stale_warned = False
        self._warn_topic = self.resolve_topic_name(costmap_topic)
        # 정지 규칙(작전 9/25 exp/gov-stop): 진행 방향 앞, 몸체 폭 띠 안에 **지도에 없는** 장애물이 가까우면 멈춘다.
        # 정적 지도(`map`)와 TF(map ← 코스트맵 프레임)가 있어야 "지도에 있는 것" 을 뺄 수 있다 — 없으면 규칙을 끈다
        # (문 앞·정차 접근의 벽·테이블로 멈추면 회차가 못 끝난다). 기존 근접 감속은 그대로 돈다.
        self._stop_enabled = bool(self.declare_parameter('stop_rule', True).value)
        # 상세 시계열은 진단 랩에서만 켠다. ros2 param set으로 켜고 끌 수 있으며 판정에는 관여하지 않는다.
        self.declare_parameter('stop_diagnostics', False)
        self._rule = governor.StopRule(float(self.declare_parameter('stop_m', governor.STOP_M).value),
                                       float(self.declare_parameter('resume_m', governor.RESUME_M).value),
                                       float(self.declare_parameter('resume_delay_s', governor.RESUME_DELAY_S).value))
        self._heading = None
        self._yaw = None
        self._gap = None
        self._static = None
        self._stop_blind_warned = False
        self._tf = Buffer()
        self._tf_listener = TransformListener(self._tf, self)
        self.create_subscription(Odometry, str(self.declare_parameter('odom_topic', 'odom').value), self._on_odom,
                                 QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT,
                                            durability=DurabilityPolicy.VOLATILE, history=HistoryPolicy.KEEP_LAST))
        map_topic = str(self.declare_parameter('map_topic', 'map').value)
        self._map_sub = self.create_subscription(
            OccupancyGrid, map_topic, self._on_map,
            QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                       durability=DurabilityPolicy.TRANSIENT_LOCAL, history=HistoryPolicy.KEEP_LAST))
        # Subscription의 실제 이름은 namespace와 런타임 remap까지 반영한다.
        self._map_topic = self._map_sub.topic_name
        self.get_logger().info(f'governor static input topic={self._map_topic} parameter={map_topic}')
        self.get_logger().info(
            f'speed_governor 정지 규칙 {"켬" if self._stop_enabled else "끔"}: 진행 방향 앞 지도에 없는 장애물 '
            f'{self._rule.stop_m:g} m 안이면 {governor.STOP_PERCENT:g}%, {self._rule.resume_m:g} m·'
            f'{self._rule.delay_s:g} s 뒤 재개 (이 줄이 없으면 옛 설치본이다)')
        self._publish()              # 첫 코스트맵 전에는 느린 쪽으로 둔다
        self.create_timer(float(self.declare_parameter('publish_period_s', 1.0).value), self._publish)
        # 값이 안 바뀌면 로그가 조용해서 "잘 돌고 있음"과 "한 장도 못 받음"이 **구별이 안 됐다**(9/23).
        # 주기마다 한 줄 남긴다. 코스트맵을 못 받고 있으면 그 줄이 발행자와 QoS 까지 말한다.
        self.create_timer(float(self.declare_parameter('status_period_s', 10.0).value), self._status)

    def _on_odom(self, msg):
        q = msg.pose.pose.orientation
        self._yaw = math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))
        self._heading = governor.motion_heading(msg.twist.twist.linear.x, msg.twist.twist.linear.y, self._yaw,
                                                self._heading)

    def _on_map(self, msg):
        info = msg.info
        self._static = (list(msg.data), info.width, info.height, info.resolution,
                        info.origin.position.x, info.origin.position.y, msg.header.frame_id or 'map')
        # 파일의 지도와 런타임 구독 지도가 같은지도 대조한다. -1..100을 0..101 바이트로 옮겨 해시한다.
        digest = hashlib.sha256(bytes(value + 1 for value in msg.data)).hexdigest()
        p, q = info.origin.position, info.origin.orientation
        self.get_logger().info(
            f'speed_governor 정지 규칙: 정적 지도 {info.width}×{info.height} 받음 '
            f'topic={self._map_topic} frame={msg.header.frame_id} res={info.resolution:.3f} '
            f'origin=({p.x:.3f},{p.y:.3f}) quaternion=({q.x:g},{q.y:g},{q.z:g},{q.w:g}) '
            f'data_sha256={digest}')
        self.get_logger().info(
            f'governor static input topic={self._map_topic} '
            + governor.describe_publishers(self.get_publishers_info_by_topic(self._map_topic)))

    def _static_filter(self, msg):
        """로봇 기준 (dx, dy) → 그 자리가 정적 지도에 막혀 있나. 지도·TF 가 없으면 None(규칙을 끈다)."""
        if self._static is None:
            return None
        cells, width, height, resolution, ox, oy, map_frame = self._static
        try:
            tf = self._tf.lookup_transform(map_frame, msg.header.frame_id, Time())
        except TransformException:
            return None
        t, q = tf.transform.translation, tf.transform.rotation
        yaw = math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))
        info = msg.info
        rx = info.origin.position.x + info.width * info.resolution / 2.0
        ry = info.origin.position.y + info.height * info.resolution / 2.0

        return governor.StaticMapFilter((cells, width, height, resolution, ox, oy),
                                         (rx, ry), (t.x, t.y, yaw), self._heading)

    def _update_stop(self, msg):
        if not self._stop_enabled:
            return
        is_static = self._static_filter(msg)
        if is_static is None:
            if not self._stop_blind_warned:
                self.get_logger().warn('speed_governor 정지 규칙 꺼짐 — 정적 지도나 TF(map ← 코스트맵) 없음. '
                                       '근접 감속만 돈다')
                self._stop_blind_warned = True
            self._gap = None
            return
        self._gap, anything, skipped = governor.forward_scan(msg.data, msg.info.width, msg.info.height,
                                                             msg.info.resolution, self._heading,
                                                             is_static=is_static, lethal=self._lethal)
        # #240 5854548169: 벽시계만으로는 캡슐 배치(sim)와 제외 칸을 맞출 수 없었다.
        # 명시적으로 진단을 켰을 때만 빈 띠까지 남긴다. 판단·발행 주기는 그대로다.
        now_s = self._now_s()
        if self.get_parameter('stop_diagnostics').value:
            dyn = 'none' if self._gap is None else f'{self._gap:.2f}'
            any_text = 'none' if anything is None else f'{anything:.2f}'
            heading = 'none' if self._heading is None else f'{math.degrees(self._heading):.0f}'
            info, stamp = msg.info, msg.header.stamp
            q = info.origin.orientation
            tx, ty, yaw = is_static.transform
            _, mw, mh, mr, mx, my, map_frame = self._static
            self.get_logger().info(
                f'governor ahead dist={dyn} any={any_text} static_skipped={skipped} heading={heading} '
                f'sim={now_s:.3f} stamp={stamp.sec + stamp.nanosec * 1e-9:.3f} '
                f'{is_static.sample_text()} static_topic={self._map_topic} '
                f'cost_frame={msg.header.frame_id} map_frame={map_frame} '
                f'origin=({info.origin.position.x:.3f},{info.origin.position.y:.3f}) '
                f'cost_quaternion=({q.x:g},{q.y:g},{q.z:g},{q.w:g}) '
                f'size={info.width}x{info.height} res={info.resolution:.3f} '
                f'tf=({tx:.3f},{ty:.3f},{yaw:.6f}) map_origin=({mx:.3f},{my:.3f}) '
                f'map_size={mw}x{mh} map_res={mr:.3f}')
        event = self._rule.update(self._gap, now_s)
        if event == 'stop':
            self.get_logger().warn(f'governor stop reason=obstacle dist={self._gap:.2f} '
                                   f'(지도에 없는 장애물이 진행 방향 앞 {self._rule.stop_m:g} m 안, 제한 '
                                   f'{governor.STOP_PERCENT:g}%)')
        elif event == 'resume':
            dist = 'none' if self._gap is None else f'{self._gap:.2f}'
            self.get_logger().info(f'governor resume dist={dist} (앞이 {self._rule.resume_m:g} m 넘게 '
                                   f'{self._rule.delay_s:g} s 비었다)')

    def _status(self):
        # 판정은 이 줄로 한다: `받은 코스트맵` 이 늘고 제한이 100% 와 낮은 값을 오가야 감속기가 실제로 도는 것이다.
        stop = governor.stop_rule_text(self._stop_enabled, self._static is not None, self._heading, self._gap,
                                       self._rule.stopped)
        line = governor.status_line(self._percent, self._max_mps, self._free_text(), self._seen, stop)
        if self._seen:
            self.get_logger().info(line)
            return
        self.get_logger().warn(
            f'{line} — {self._warn_topic} 를 한 장도 못 받았다. '
            + governor.describe_publishers(self.get_publishers_info_by_topic(self._warn_topic)))

    def _free_text(self):
        """현황 줄의 여유 글자. 셋을 가른다 — 로그만 보고 무엇이 일어났는지 알 수 있게."""
        if self._free_kind == governor.OPEN:
            return f"≥{self._far:.2f} m"                 # far 안에 장애물이 없다(넓다)
        if self._free_kind == governor.STALE:
            return "모름(코스트맵 끊김)"                    # 받다가 끊겼다
        if self._free_kind == governor.BLIND:
            return "모름(창에 장애물 0)"                   # 라이다가 눈을 감았을 수 있다
        if self._free_m is None:
            return "모름"                                  # 코스트맵을 아직 못 받았다
        return f"{self._free_m:.2f} m"

    def _now_s(self):
        """노드 시계(sim, use_sim_time) 초. /clock 이 멈추면 이 값도 멈춘다 — 그때는 로봇도 안 움직인다."""
        return self.get_clock().now().nanoseconds * 1e-9

    def _on_costmap(self, msg):
        self._seen += 1
        if self._seen == 1 and governor.looks_like_internal_costmap(msg.data):
            # 값이 0-100 이 아니면 문턱(`lethal_cost`)이 틀린 것이다. 조용히 늘 100 % 를 내지 않는다(#610).
            self.get_logger().error(
                f'{self._warn_topic} 값이 100 을 넘는다 — OccupancyGrid(0-100)가 아니다. '
                f'lethal_cost={self._lethal} 이 안 맞는다. 여유를 못 잰 채 100 % 를 낼 뻔했다')
        self._last_costmap_s = self._now_s()
        if self._stale_warned:
            self.get_logger().info(f'{self._warn_topic} 다시 받는다 — 끊김 풀림(받은 코스트맵 {self._seen}장)')
            self._stale_warned = False
        # far 안에 없으면 "모름" 이 아니라 넓은 것이다 — 창 안에 장애물이 하나라도 있으면(`free_space`).
        self._free_m, self._free_kind = governor.free_space(msg.data, msg.info.width, msg.info.height,
                                                            msg.info.resolution, lethal=self._lethal, far=self._far)
        self._update_stop(msg)
        self._publish()

    def _publish(self):
        """지금 제한을 낸다. **값이 같아도 낸다** — 늦게 뜬 구독자가 받아야 한다(윗 주석).

        바뀐 값만 로그에 남긴다. 주기적인 현황은 `_status` 가 찍는다.
        """
        if governor.is_stale(self._now_s(), self._last_costmap_s, self._stale_after):
            # 받다가 끊겼다. 마지막 값을 계속 내면 눈 감은 채 그 속도로 간다 — 모르면 느린 쪽이다.
            gap = self._now_s() - self._last_costmap_s
            self._free_m, self._free_kind = None, governor.STALE
            if not self._stale_warned:
                self.get_logger().warn(
                    f'{self._warn_topic} 가 {gap:.1f} s(sim) 끊겼다. 제한을 {self._slow:.0f}% 로 내린다 '
                    f'(stale_after_s={self._stale_after:g}, 받은 코스트맵 {self._seen}장)')
                self._stale_warned = True
        self._percent = governor.limit_percent(self._free_m, self._near, self._far, self._slow)
        if self._rule.stopped:
            self._percent = governor.STOP_PERCENT   # 0 은 Nav2 에서 "제한 없음" 이다 — 1 % 로 멈춘다
        message = SpeedLimit()
        message.header.stamp = self.get_clock().now().to_msg()
        message.percentage = True
        message.speed_limit = self._percent
        self._limit_pub.publish(message)
        if governor.changed(self._sent, self._percent, self._step):
            self.get_logger().info(
                f'speed limit {self._percent:.0f}%={self._percent * self._max_mps / 100.0:.2f} m/s '
                f'(여유 {self._free_text()}, '
                f'받은 코스트맵 {self._seen}장)')
            self._sent = self._percent


def main(args=None):
    rclpy.init(args=args)
    node = SpeedGovernor()
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
