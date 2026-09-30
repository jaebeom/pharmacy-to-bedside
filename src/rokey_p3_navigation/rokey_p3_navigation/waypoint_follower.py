"""고정 경로 추종 v0. ROS 를 import 하지 않는다. 계약 v1 2.2절.

빈월드에서 "AMR 이 가는 것이 보이는" 것까지만 한다. **장애물 회피도 재계획도 없다.**
심월드에서는 이 추종기를 Nav2 로 갈아 끼운다. 갈아 끼우는 자리는 `fleet` 의 backend 파라미터 한 곳이다.

- 베이스는 전방향이다(world 축 prismatic x·y + revolute z). 그래서 **목표를 향해 돌지 않고 그대로 간다.**
- 중간 waypoint 에서는 yaw 를 바꾸지 않는다. 마지막 구간에서만 목표 yaw 로 맞춘다.
  `turn_first` 면 마지막 구간의 **시작점에서 먼저 제자리로** 맞추고, 그 뒤 yaw 를 고정한 채 옮긴다.
- 내는 속도는 `amr_1/base_link` 기준이다(`cmd_vel` 규약). 그래서 world 속도를 현재 yaw 로 되돌린다.
- 도착은 **중심 가까이**(`arrive_xy`·`arrive_yaw`)까지 들어간 뒤에 낸다. zone 공차는 그보다 느슨한 **판정**의 선이라
  공차 원에 들어서자마자 멈추면 도착 정밀도가 곧 공차가 된다(K3 L3 관측: 목표에서 0.14 m 에 섰다).
  실제 기준은 `min(zone 공차, arrive_*)` 이고, 정지 확인은 `fleet` 이 한다.

값이 없거나 이상하면 **움직이지 않는다**(0 속도 + `reason`). 추측해서 가지 않는다.
"""

import math
from collections import namedtuple

from rokey_p3_navigation.base_kinematics import body_to_world_velocity, wrap_angle, world_to_body_velocity

#: 속도 상한·감속 반경과 **도착으로 볼 반경**. 전부 부르는 쪽이 넣는다(빈월드에서 튜닝할 값이다).
#: `arrive_xy`·`arrive_yaw` 는 zone 공차와 다른 것이다 — 공차는 **판정**의 선이고, 추종의 **목표는 중심**이다.
#: 실제로 쓰는 값은 `min(zone 공차, arrive_*)` 라 공차보다 느슨해지지 않는다.
#: `max_accel`·`max_angular_accel` 은 **명령이 한 주기에 바뀔 수 있는 폭**이다. 스테이지의 속도 드라이브는
#: damping 이 커서(`sim/standalone/p3sim/amr_base.py` 의 `DEFAULT_DRIVE`) 명령 계단을 거의 그대로
#: 따라간다 — 자르지 않으면 상판의 봉투가 미끄러진다. 사슬 어디에도 다른 가속 상한이 없다.
FollowerConfig = namedtuple(
    'FollowerConfig', ('max_linear', 'max_angular', 'slow_radius', 'waypoint_tolerance',
                       'arrive_xy', 'arrive_yaw', 'max_accel', 'max_angular_accel'))

#: `vx`·`vy`·`wz` 는 base_link 기준. `index` 는 다음에 향할 waypoint, `arrived` 는 목표 도착.
#: `reason` 은 움직이지 않는 까닭(움직이면 None).
#: `world` 는 같은 명령의 `map` 기준 `(vx, vy)` 다. 가속 상한은 **회전과 섞이지 않게** world 에서 잘라야
#: 해서(몸이 돌면 같은 속도도 body 성분이 바뀐다), 다음 호출에 `previous` 로 돌려주려고 함께 낸다.
Command = namedtuple('Command', ('vx', 'vy', 'wz', 'index', 'arrived', 'reason', 'world'))
Command.__new__.__defaults__ = ((0.0, 0.0),)

STOP = (0.0, 0.0, 0.0)


def _finite(*values):
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
               for v in values)


def _config_reason(config):
    if not isinstance(config, FollowerConfig):
        return f'config 가 FollowerConfig 가 아니다: {config!r}'
    for name, value in config._asdict().items():
        if not _finite(value) or value <= 0.0:
            return f'config.{name} 이 양의 유한값이 아니다: {value!r}'
    return None


#: 정지에서 시작할 때의 `previous`.
REST = ((0.0, 0.0), 0.0)


def moving_start(twist, pose):
    """지금 **실제로** 움직이는 속도를 `follow` 의 `previous` 형식 `((vx, vy), wz)`(world)로. 모르면 정지.

    `twist` 는 odom 의 base_link 기준 `(vx, vy, wz)`, `pose` 는 `map` 기준 `(x, y, yaw)` 다.
    Nav2 를 넘김 반경에서 거두면 베이스는 아직 Nav2 속도(최고 1.0 m/s)로 간다. 추종기가 정지에서 시작한다고
    가정하면 첫 명령이 `max_accel * dt`(0.04 m/s)라 한 주기에 급정거한다 — 가속 상한이 막으려던 바로 그것이다.
    9/24 953ff5c 10건 ord-0009: bed_b5 접근점에 선 뒤 봉투가 트레이 자리에서 0.15–0.24 m 밀려 있었다.
    """
    if twist is None or pose is None or len(twist) != 3 or len(pose) != 3:
        return REST
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (*twist, pose[2])):
        return REST
    wx, wy, wz = body_to_world_velocity(twist[0], twist[1], twist[2], pose[2])
    return ((wx, wy), wz)


def _towards(pose, target, config):
    """목표를 향한 world 속도. 감속 반경 안에서는 거리에 비례해 줄인다."""
    dx, dy = target[0] - pose[0], target[1] - pose[1]
    distance = math.hypot(dx, dy)
    if distance <= 0.0:
        return (0.0, 0.0), 0.0
    speed = config.max_linear * min(1.0, distance / config.slow_radius)
    return (speed * dx / distance, speed * dy / distance), distance


def _turn(pose_yaw, target_yaw, config):
    """목표 yaw 로 도는 각속도(world = base_link, z 축은 같다)."""
    error = wrap_angle(target_yaw - pose_yaw)
    return max(-config.max_angular, min(config.max_angular, error)), abs(error)


def _ramp(desired, previous, max_delta):
    """`previous` 에서 `desired` 로 가되 한 주기에 `max_delta` 만큼만 바꾼다(2차원은 벡터 크기).

    감속도 같은 상한을 받는다. 급정거도 봉투를 미끄러뜨리기는 마찬가지다.
    """
    dx, dy = desired[0] - previous[0], desired[1] - previous[1]
    change = math.hypot(dx, dy)
    if change <= max_delta or change <= 0.0:
        return desired
    scale = max_delta / change
    return (previous[0] + dx * scale, previous[1] + dy * scale)


def _ramp_scalar(desired, previous, max_delta):
    return max(previous - max_delta, min(previous + max_delta, desired))


def follow(pose, waypoints, index, goal, tol_xy, tol_yaw, config, previous=None, dt=None,
           turn_first=False):
    """다음 `Command` 를 만든다.

    `pose` 는 `map` 기준 `(x, y, yaw)`, `waypoints` 는 `map` 기준 `(x, y)` 목록,
    `index` 는 다음에 향할 waypoint 번호, `goal` 은 목표 zone 의 `(x, y, yaw)` 다.
    `index` 가 waypoint 를 다 지나면 목표로 간다.

    `previous` 는 **직전 명령의 `world` 와 `wz`** 인 `((vx, vy), wz)` 다. `dt` 와 함께 주면
    가속 상한을 적용한다. 정지 상태에서 시작하면 `previous=((0.0, 0.0), 0.0)` 이다.
    둘 중 하나만 주면 움직이지 않는다 — 가속을 적용하는지 아닌지를 추측하지 않는다.

    `turn_first` 면 마지막 구간에서 yaw 오차가 도착 기준(`arrive_yaw`)보다 큰 동안 옮기지 않고 돌기만 한다.
    옮기면서 돌면 몸체가 정차 자리 옆 고정물을 쓸고 지나간다 — 9/24 병원 10건에서 bed_a3 로 113° 를 돌며
    팔 받침이 D3 협탁에 닿았다. 그래서 회전은 여유가 트인 마지막 waypoint(접근점)에서 끝내고 옆걸음으로 들어간다.
    """
    reason = _config_reason(config)
    if reason is None and not (isinstance(index, int) and not isinstance(index, bool) and index >= 0):
        reason = f'index 가 0 이상의 정수가 아니다: {index!r}'
    if reason is None and not (pose is not None and len(pose) == 3 and _finite(*pose)):
        reason = f'pose 가 유한한 (x, y, yaw) 가 아니다: {pose!r}'
    if reason is None and not (goal is not None and len(goal) == 3 and _finite(*goal)):
        reason = f'goal 이 유한한 (x, y, yaw) 가 아니다: {goal!r}'
    if reason is None and not (_finite(tol_xy, tol_yaw) and tol_xy > 0.0 and tol_yaw > 0.0):
        reason = f'공차가 양의 유한값이 아니다: tol_xy={tol_xy!r}, tol_yaw={tol_yaw!r}'
    if reason is None and any(not (len(point) == 2 and _finite(*point)) for point in waypoints):
        reason = f'waypoint 가 유한한 (x, y) 가 아니다: {list(waypoints)!r}'
    if reason is None and (previous is None) != (dt is None):
        reason = (f'가속 상한은 previous 와 dt 를 함께 받는다: '
                  f'previous={previous!r}, dt={dt!r}')
    if reason is None and dt is not None and not (_finite(dt) and dt > 0.0):
        reason = f'dt 가 양의 유한값이 아니다: {dt!r}'
    if reason is None and previous is not None and not (
            len(previous) == 2 and len(previous[0]) == 2
            and _finite(previous[0][0], previous[0][1], previous[1])):
        reason = f'previous 가 ((vx, vy), wz) 가 아니다: {previous!r}'
    if reason is not None:
        # 값이 이상하면 곧바로 0 이다. 여기서는 가속 상한을 쓰지 않는다 — 멈추는 쪽은 늦추지 않는다.
        return Command(*STOP, index, False, reason)

    # 지나간 waypoint 는 건너뛴다. 가까이 스친 것도 지난 것으로 본다.
    while index < len(waypoints):
        dx = waypoints[index][0] - pose[0]
        dy = waypoints[index][1] - pose[1]
        if math.hypot(dx, dy) > config.waypoint_tolerance:
            break
        index += 1

    def emit(world, turn, arrived):
        """world 속도를 가속 상한으로 자른 뒤 base_link 기준으로 바꾼다."""
        if dt is not None:
            world = _ramp(world, previous[0], config.max_accel * dt)
            turn = _ramp_scalar(turn, previous[1], config.max_angular_accel * dt)
        vx, vy, wz = world_to_body_velocity(world[0], world[1], turn, pose[2])
        return Command(vx, vy, wz, index, arrived, None, world)

    if index < len(waypoints):
        # 중간 구간: yaw 는 그대로 두고 그대로 간다(전방향 베이스).
        world, _ = _towards(pose, waypoints[index], config)
        return emit(world, 0.0, False)

    world, distance = _towards(pose, goal, config)
    turn, angle = _turn(pose[2], goal[2], config)
    # 공차는 판정의 선이고 목표는 중심이다. 공차보다 느슨해지지는 않는다.
    arrive_xy = min(tol_xy, config.arrive_xy)
    arrive_yaw = min(tol_yaw, config.arrive_yaw)
    if distance <= arrive_xy and angle <= arrive_yaw:
        # 도착 속도는 `max_linear * arrive_xy / slow_radius` 라 한 주기의 가속 상한보다 작다.
        # 그래도 같은 길로 보낸다 — 0 을 내는 자리가 두 곳이면 한쪽만 고치게 된다.
        return emit((0.0, 0.0), 0.0, True)
    if distance <= arrive_xy or (turn_first and angle > arrive_yaw):
        world = (0.0, 0.0)   # 자리를 잡았거나(turn_first 면 아직 접근점이면) yaw 만 맞춘다
    return emit(world, turn, False)
