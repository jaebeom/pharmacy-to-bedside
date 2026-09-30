"""베이스 변환 두 개. ROS 를 import 하지 않는다.

dummy 조인트 셋(prismatic x, prismatic y, revolute z)은 **world 축**이다.

- `cmd_vel` 은 `amr_1/base_link` 기준이므로 현재 yaw 로 돌려 world 속도로 바꾼다.
- `nav_msgs/Odometry` 의 `twist` 는 `child_frame_id`(`amr_1/base_link`) 기준이므로 반대로 돌린다.

계약 v1 2.2절·3절. 노이즈는 넣지 않는다.
"""

import math

TWO_PI = 2.0 * math.pi


def wrap_angle(angle):
    """각을 [-pi, pi) 로 접는다."""
    return (angle + math.pi) % TWO_PI - math.pi


def body_to_world_velocity(vx, vy, wz, yaw):
    """base_link 기준 속도 → world 축 dummy 조인트 속도 (m/s, m/s, rad/s).

    cmd_vel → base/joint_command 변환이다. yaw 는 현재 dummy revolute 조인트 값이다.
    """
    cos_yaw = math.cos(yaw)
    sin_yaw = math.sin(yaw)
    return (vx * cos_yaw - vy * sin_yaw,
            vx * sin_yaw + vy * cos_yaw,
            wz)


def world_to_body_velocity(dx, dy, dyaw, yaw):
    """world 축 속도 → base_link 기준 속도. `body_to_world_velocity` 의 역변환이다."""
    cos_yaw = math.cos(yaw)
    sin_yaw = math.sin(yaw)
    return (dx * cos_yaw + dy * sin_yaw,
            -dx * sin_yaw + dy * cos_yaw,
            dyaw)


def odom_from_joints(x, y, yaw, dx, dy, dyaw):
    """dummy 조인트 위치·속도 → odom 자세(world)와 twist(base_link 기준).

    joint_states → odom 변환이다. 위치는 조인트 값 그대로 쓴다(계약 2.2절).
    반환: `((x, y, yaw), (vx, vy, wz))`.
    """
    wrapped = wrap_angle(yaw)
    return (x, y, wrapped), world_to_body_velocity(dx, dy, dyaw, wrapped)


def difference_velocity(previous, current, dt):
    """위치 두 개의 차이로 world 속도를 만든다.

    `joint_states` 에 `velocity` 가 비어 있을 때만 쓴다. 속도를 0 으로 가정하면
    `base/stopped` 가 항상 참이 되어 인터락이 무너진다(계약 5절).
    `dt` 가 0 이하면 속도를 모르는 것이므로 0 을 낸다.
    """
    if dt <= 0.0:
        return (0.0, 0.0, 0.0)
    return ((current[0] - previous[0]) / dt,
            (current[1] - previous[1]) / dt,
            wrap_angle(current[2] - previous[2]) / dt)


def yaw_to_quaternion(yaw):
    """z 축 회전만 있는 쿼터니언 `(x, y, z, w)`."""
    half = 0.5 * wrap_angle(yaw)
    return (0.0, 0.0, math.sin(half), math.cos(half))


def quaternion_to_yaw(x, y, z, w):
    """쿼터니언에서 z 축 회전만 꺼낸다. TF 로 받은 자세를 판정에 쓸 때 필요하다."""
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
