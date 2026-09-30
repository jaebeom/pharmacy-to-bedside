"""waypoint_follower L1. 빈월드 고정 경로 추종 v0.

수치는 규칙을 확인하려는 값이다. 로봇·씬의 실측이 아니다.
"""

import math

import pytest

from rokey_p3_navigation.waypoint_follower import REST as AT_REST, FollowerConfig, follow, moving_start

CONFIG = FollowerConfig(max_linear=0.5, max_angular=1.0, slow_radius=1.0, waypoint_tolerance=0.1,
                        arrive_xy=0.02, arrive_yaw=0.02, max_accel=1.0, max_angular_accel=2.0)
GOAL = (10.0, 0.0, 0.0)
TOL = {'tol_xy': 0.05, 'tol_yaw': 0.05}


def step(pose, waypoints=(), index=0, goal=GOAL, config=CONFIG, previous=None, dt=None, **tol):
    return follow(pose, waypoints, index, goal, **{**TOL, **tol}, config=config,
                  previous=previous, dt=dt)


def test_goes_straight_at_the_speed_limit_when_far():
    command = step((0.0, 0.0, 0.0))
    assert (command.vx, command.vy, command.wz) == pytest.approx((0.5, 0.0, 0.0))
    assert not command.arrived and command.reason is None


def test_slows_down_inside_the_slow_radius():
    # 남은 거리 0.5 m, slow_radius 1.0 m → 절반 속도.
    assert step((9.5, 0.0, 0.0)).vx == pytest.approx(0.25)


def test_velocity_is_in_base_link_frame():
    # 로봇이 +y 를 보고 있으면(yaw 90°) world +x 로 가는 것은 base 기준 -y 다.
    command = step((0.0, 0.0, math.pi / 2))
    assert (command.vx, command.vy) == pytest.approx((0.0, -0.5), abs=1e-9)


def test_moves_sideways_without_turning_for_an_omni_base():
    command = step((0.0, -2.0, 0.0), waypoints=((0.0, 0.0),))
    assert command.vy > 0.0 and command.vx == pytest.approx(0.0)
    assert command.wz == 0.0


def test_middle_waypoints_do_not_change_yaw():
    command = step((0.0, 0.0, 0.3), waypoints=((5.0, 0.0),))
    assert command.wz == 0.0
    assert command.index == 0


def test_reached_waypoints_are_skipped():
    command = step((5.0, 0.0, 0.0), waypoints=((5.02, 0.0), (8.0, 0.0)))
    assert command.index == 1   # 첫 waypoint 는 waypoint_tolerance 안이라 지난 것으로 본다
    assert command.vx > 0.0


def test_v0_does_not_skip_a_waypoint_left_behind():
    # v0 의 한계다. 순서대로만 간다. 뒤에 남은 waypoint 가 있으면 되돌아간다.
    # 심월드에서 Nav2 로 갈아 끼우면 없어지는 문제라 여기서는 고치지 않는다.
    command = step((5.0, 0.0, 0.0), waypoints=((0.0, 0.0), (8.0, 0.0)))
    assert command.index == 0 and command.vx < 0.0


def test_last_segment_turns_to_the_goal_yaw():
    command = step((10.0, 0.0, -0.5))
    assert command.wz == pytest.approx(0.5)
    assert (command.vx, command.vy) == pytest.approx((0.0, 0.0))   # 자리는 잡았으니 yaw 만


def test_keeps_going_to_the_centre_inside_the_zone_tolerance():
    # K3 L3 관측: 공차 원에 들어서자마자 멈추면 도착 정밀도가 곧 공차가 된다(목표에서 0.14 m).
    # 공차(0.05) 안이지만 중심(arrive_xy 0.02)에는 못 든 자리에서는 계속 들어간다.
    command = step((10.04, 0.0, 0.0))
    assert not command.arrived
    assert command.vx < 0.0


def test_turn_is_capped_by_max_angular():
    assert step((10.0, 0.0, -3.0), goal=(10.0, 0.0, 0.0)).wz == pytest.approx(1.0)


def test_arrived_inside_the_arrive_radius():
    command = step((10.015625, 0.0, 0.015625))   # 이진수로 정확한 값만 쓴다
    assert command.arrived
    assert (command.vx, command.vy, command.wz) == (0.0, 0.0, 0.0)


def test_not_arrived_when_only_position_is_inside():
    assert not step((10.02, 0.0, 0.5)).arrived


def test_not_arrived_when_only_yaw_is_inside():
    assert not step((9.0, 0.0, 0.0)).arrived


def test_arrival_is_still_capped_by_the_zone_tolerance():
    # 공차가 도착 반경보다 작으면 공차가 이긴다.
    assert not step((10.015625, 0.0, 0.0), tol_xy=0.01).arrived


def test_arrive_radius_boundary_is_inside():
    # 도착 반경과 같은 오차는 안이다(<=). 0.015625 는 이진수로 정확하다.
    exact = FollowerConfig(max_linear=0.5, max_angular=1.0, slow_radius=1.0,
                           waypoint_tolerance=0.1, arrive_xy=0.015625, arrive_yaw=0.015625,
                           max_accel=1.0, max_angular_accel=2.0)
    assert step((10.015625, 0.0, 0.015625), config=exact).arrived


def test_arrival_needs_every_waypoint_to_be_passed():
    # 목표 위에 있어도 남은 waypoint 가 멀면 그쪽으로 간다.
    command = step((10.0, 0.0, 0.0), waypoints=((3.0, 0.0),))
    assert not command.arrived and command.vx < 0.0


# -- 값이 없거나 이상하면 움직이지 않는다 -------------------------------------------

@pytest.mark.parametrize('bad', [
    FollowerConfig(0.0, 1.0, 1.0, 0.1, 0.02, 0.02, 1.0, 2.0),
    FollowerConfig(0.5, -1.0, 1.0, 0.1, 0.02, 0.02, 1.0, 2.0),
    FollowerConfig(0.5, 1.0, float('nan'), 0.1, 0.02, 0.02, 1.0, 2.0),
    FollowerConfig(0.5, 1.0, 1.0, float('inf'), 0.02, 0.02, 1.0, 2.0),
    FollowerConfig(0.5, 1.0, 1.0, 0.1, 0.0, 0.02, 1.0, 2.0),
    FollowerConfig(0.5, 1.0, 1.0, 0.1, 0.02, -0.02, 1.0, 2.0),
    FollowerConfig(0.5, 1.0, 1.0, 0.1, 0.02, 0.02, 0.0, 2.0),
    FollowerConfig(0.5, 1.0, 1.0, 0.1, 0.02, 0.02, 1.0, float('nan')),
    None,
])
def test_bad_config_stops(bad):
    command = step((0.0, 0.0, 0.0), config=bad)
    assert (command.vx, command.vy, command.wz) == (0.0, 0.0, 0.0)
    assert not command.arrived and 'config' in command.reason


@pytest.mark.parametrize('tol', [{'tol_xy': 0.0}, {'tol_yaw': 0.0}, {'tol_xy': float('nan')},
                                 {'tol_xy': -0.1}, {'tol_yaw': None}])
def test_zero_or_missing_tolerance_stops(tol):
    command = step((0.0, 0.0, 0.0), **tol)
    assert (command.vx, command.vy, command.wz) == (0.0, 0.0, 0.0)
    assert '공차' in command.reason


@pytest.mark.parametrize('pose', [None, (0.0, 0.0), (0.0, float('nan'), 0.0)])
def test_bad_pose_stops(pose):
    assert 'pose' in step(pose).reason


@pytest.mark.parametrize('goal', [None, (1.0, 2.0), (float('inf'), 0.0, 0.0)])
def test_bad_goal_stops(goal):
    assert 'goal' in step((0.0, 0.0, 0.0), goal=goal).reason


@pytest.mark.parametrize('waypoints', [((0.0,),), ((0.0, float('nan')),), ((0.0, 0.0, 0.0),)])
def test_bad_waypoint_stops(waypoints):
    assert 'waypoint' in step((0.0, 0.0, 0.0), waypoints=waypoints).reason


@pytest.mark.parametrize('index', [-1, 1.5, True, None])
def test_bad_index_stops(index):
    assert 'index' in step((0.0, 0.0, 0.0), index=index).reason


def wrap(angle):
    from rokey_p3_navigation.base_kinematics import wrap_angle

    return wrap_angle(angle)


def drive(pose, waypoints=(), goal=GOAL, steps=2000, dt=0.05, turn_first=False, trace=None, **tol):
    """`follow` 를 반복해 자세를 적분한다. 물리는 없다(완전 추종). 도착하면 걸린 걸음 수를 돌려준다.

    `trace` 에 목록을 주면 걸음마다 자세를 담는다.
    """
    from rokey_p3_navigation.base_kinematics import body_to_world_velocity

    pose = list(pose)
    index = 0
    for step in range(steps):
        if trace is not None:
            trace.append(tuple(pose))
        command = follow(tuple(pose), waypoints, index, goal, **{**TOL, **tol}, config=CONFIG,
                         turn_first=turn_first)
        index = command.index
        if command.arrived:
            return step, tuple(pose)
        dx, dy, dyaw = body_to_world_velocity(command.vx, command.vy, command.wz, pose[2])
        pose[0] += dx * dt
        pose[1] += dy * dt
        pose[2] += dyaw * dt
    return None, tuple(pose)


def test_a_yaw_only_goal_converges():
    # xy 는 이미 공차 안이고 yaw 만 반대인 목표(예: 같은 자리에서 yaw 만 다른 침상 접근 자세).
    steps, pose = drive((10.0, 0.0, math.pi / 2), goal=(10.0, 0.0, -math.pi / 2))
    assert steps is not None
    assert abs(wrap(pose[2] - (-math.pi / 2))) <= TOL['tol_yaw']
    assert abs(pose[0] - 10.0) <= TOL['tol_xy']


def test_a_route_with_waypoints_converges():
    steps, pose = drive((0.0, 0.0, 0.0), waypoints=((3.0, 2.0), (7.0, 2.0)))
    assert steps is not None
    assert abs(pose[0] - 10.0) <= TOL['tol_xy'] and abs(pose[1]) <= TOL['tol_xy']



# -- turn_first: 접근점에서 돌고 옆걸음으로 든다 -------------------------------------------
# 9/24 병원 10건: 접근점 0.3 m 앞에서 옮기며 113° 를 돌다 팔 받침이 D3 협탁에 닿았다.

def test_turn_first_turns_in_place_while_the_yaw_is_off():
    command = follow((10.3, 0.0, 1.97), (), 0, GOAL, **TOL, config=CONFIG, turn_first=True)
    assert (command.vx, command.vy) == pytest.approx((0.0, 0.0))
    assert command.wz < 0.0


def test_turn_first_slides_once_the_yaw_is_aligned():
    command = follow((10.3, 0.0, 0.01), (), 0, GOAL, **TOL, config=CONFIG, turn_first=True)
    assert command.vx < 0.0   # 목표(-x 쪽)로 옮긴다
    assert not command.arrived


def test_without_turn_first_the_last_segment_still_moves_and_turns_together():
    # 빈월드 waypoints backend 는 그대로다. turn_first 는 nav2 final approach 만 켠다.
    command = follow((10.3, 0.0, 1.97), (), 0, GOAL, **TOL, config=CONFIG)
    assert command.vx != 0.0 or command.vy != 0.0
    assert command.wz < 0.0


def test_turn_first_finishes_the_turn_at_the_approach_point():
    # 접근점을 거쳐 들어간다. 접근점에 닿은 뒤 yaw 가 맞을 때까지 접근점 곁을 떠나지 않는다.
    approach = (10.0, 0.3)
    trace = []
    steps, pose = drive((10.0, 0.8, 1.97), waypoints=(approach,), turn_first=True, trace=trace)
    assert steps is not None
    assert abs(wrap(pose[2])) <= TOL['tol_yaw'] and math.hypot(pose[0] - 10.0, pose[1]) <= TOL['tol_xy']
    for x, y, yaw in trace:
        if abs(wrap(yaw)) > CONFIG.arrive_yaw:
            # 돌고 있는 동안은 접근점(추종기가 지난 것으로 보는 반경) 밖 정차 자리 쪽으로 나가지 않는다.
            assert y >= approach[1] - CONFIG.waypoint_tolerance, (x, y, yaw)


# -- 가속 상한 ---------------------------------------------------------------------
# 상판이 칸막이 없는 한 칸이라 봉투가 미끄러질 수 있다(재범 9/21). 스테이지의 속도 드라이브는
# damping 이 커서 명령 계단을 거의 그대로 따라가므로, 사슬에서 가속을 자르는 곳은 여기뿐이다.

REST = ((0.0, 0.0), 0.0)
DT = 0.05


def test_from_rest_only_one_step_of_acceleration_is_commanded():
    # 멀리 있어도 첫 주기에는 max_accel * dt 까지만 나간다(예전에는 곧바로 상한이었다).
    command = step((0.0, 0.0, 0.0), previous=REST, dt=DT)
    assert command.vx == pytest.approx(CONFIG.max_accel * DT)


def test_the_speed_limit_is_reached_after_enough_steps():
    previous, speed = REST, 0.0
    for _ in range(20):
        command = step((0.0, 0.0, 0.0), previous=previous, dt=DT)
        previous, speed = (command.world, command.wz), command.vx
    assert speed == pytest.approx(CONFIG.max_linear)


def test_slowing_down_is_limited_too():
    # 급정거도 봉투를 미끄러뜨린다. 반대로 바뀔 때도 한 주기 폭만큼만 바뀐다.
    command = step((0.0, 0.0, 0.0), previous=((CONFIG.max_linear, 0.0), 0.0), dt=DT, goal=(-10.0, 0.0, 0.0))
    assert command.vx == pytest.approx(CONFIG.max_linear - CONFIG.max_accel * DT)


def test_angular_acceleration_is_limited():
    command = step((10.0, 0.0, 1.0), previous=REST, dt=DT)
    assert command.wz == pytest.approx(-CONFIG.max_angular_accel * DT)


def test_the_returned_world_velocity_is_in_map_frame():
    # 몸이 돌아 있어도 world 속도는 목표 쪽이다. 이 값을 previous 로 돌려줘야
    # 회전 때문에 없는 가속이 생기지 않는다.
    command = step((0.0, 0.0, math.pi / 2), previous=REST, dt=DT)
    assert command.world == pytest.approx((CONFIG.max_accel * DT, 0.0))
    assert command.vy == pytest.approx(-CONFIG.max_accel * DT)   # body 기준으로는 오른쪽


@pytest.mark.parametrize(('previous', 'dt'), [
    (REST, None), (None, DT), (REST, 0.0), (REST, float('nan')), (((0.0, float('nan')), 0.0), DT),
])
def test_bad_acceleration_inputs_stop(previous, dt):
    # 가속을 적용하는지 아닌지를 추측하지 않는다. 둘이 짝이 아니면 움직이지 않는다.
    command = step((0.0, 0.0, 0.0), previous=previous, dt=dt)
    assert (command.vx, command.vy, command.wz) == (0.0, 0.0, 0.0)
    assert command.reason is not None


# -- 움직이는 채로 넘겨받기(moving_start) -----------------------------------------------
# 9/24 953ff5c 10건 ord-0009: Nav2 를 넘김 반경에서 거둔 뒤 추종기가 정지에서 시작한다고 가정해 한 주기에
# 급정거했고, 봉투가 트레이 자리에서 0.15–0.24 m 밀렸다(추정 — 넘김 순간 속도는 로그에 없다).

def test_moving_start_turns_the_odom_twist_into_world_velocity():
    # +y 를 보고(yaw 90°) 앞으로 0.8 m/s 면 world 로는 +y 0.8 이다.
    (vx, vy), wz = moving_start((0.8, 0.0, 0.3), (0.0, 0.0, math.pi / 2))
    assert (vx, vy, wz) == pytest.approx((0.0, 0.8, 0.3), abs=1e-9)


@pytest.mark.parametrize('twist, pose', [(None, (0.0, 0.0, 0.0)), ((0.5, 0.0, 0.0), None),
                                         ((float('nan'), 0.0, 0.0), (0.0, 0.0, 0.0)), ((0.5, 0.0), (0.0, 0.0, 0.0))])
def test_moving_start_is_rest_when_unknown(twist, pose):
    assert moving_start(twist, pose) == AT_REST


def test_a_handoff_at_speed_slows_down_within_the_acceleration_cap():
    # 접근점 0.4 m 앞에서 0.8 m/s 로 넘겨받는다. 첫 명령은 한 주기 폭만큼만 줄어든다.
    pose = (9.6, 0.0, 0.0)
    previous = moving_start((0.8, 0.0, 0.0), pose)
    command = step(pose, previous=previous, dt=DT)
    assert command.vx == pytest.approx(0.8 - CONFIG.max_accel * DT)
    # 예전(정지 가정)에는 첫 명령이 곧바로 max_accel * dt 였다 — 한 주기에 0.8 → 0.05.
    assert step(pose, previous=AT_REST, dt=DT).vx == pytest.approx(CONFIG.max_accel * DT)
