"""Hand camera and TF naming rules for the contract (pure; no Isaac imports).

Contract v1 2.1 hand camera: /amr_1/hand_camera/image_raw (rgb8) and camera_info, frame amr_1/hand_camera_optical,
QoS S depth 2, at most 10 Hz. Contract 3: isaac publishes robot links, camera optical and deck_slot_* under
amr_1/base_link (UR5 links on /tf, the rest on /tf_static); never map or odom. Optical frames follow REP 103.
Isaac 5.1.0 ROS2PublishTransformTree names frames by prim name unless the prim has an isaac:nameOverride attribute
(isaacsim.core.includes PoseTree.h), which is how the amr_1/ prefix gets in.
"""

import json
import math

# ROS2 QoS JSON as built by the 5.1.0 ROS2QoSProfile node (keys history, depth, reliability, durability, deadline,
# lifespan, liveliness, leaseDuration).
SENSOR_QOS_DEPTH2 = json.dumps({"history": "keepLast", "depth": 2, "reliability": "bestEffort",
                                "durability": "volatile", "deadline": 0.0, "lifespan": 0.0,
                                "liveliness": "systemDefault", "leaseDuration": 0.0})

UR5_LINKS = ("shoulder_link", "upper_arm_link", "forearm_link", "wrist_1_link", "wrist_2_link", "wrist_3_link")

# End prim candidates in the USD, in order. 9/17 master02: Isaac 5.1 ur5.usd has no tool0 prim but has flange and
# ft_frame. The Lula IK frame stays "tool0" (a URDF frame in the UR5 Lula config), independent of USD prim names.
END_LINK_CANDIDATES = ("tool0", "flange", "ft_frame", "wrist_3_link")
# Rotation from the end prim frame to a tool0-like frame (tool z out of the flange). ur_description: tool0 = flange
# rotated rpy (pi/2, 0, pi/2) = quaternion (0.5, 0.5, 0.5, 0.5); same origin. ft_frame and wrist_3_link are not
# known here and use identity (logged as unconfirmed).
END_TO_TOOL = {"tool0": (1.0, 0.0, 0.0, 0.0), "flange": (0.5, 0.5, 0.5, 0.5)}


def pick_end_link(names):
    """First END_LINK_CANDIDATES name present in `names`, or None."""
    for candidate in END_LINK_CANDIDATES:
        if candidate in names:
            return candidate
    return None


def frame(namespace, name):
    return f"{namespace.strip('/')}/{name}"


def frame_skip(render_hz, max_hz):
    """ROS2CameraHelper frameSkipCount so the topic rate stays at or below max_hz."""
    if max_hz <= 0 or render_hz <= 0:
        raise ValueError("rates must be positive")
    return max(0, math.ceil(render_hz / max_hz - 1e-9) - 1)


def published_rate(render_hz, skip):
    return render_hz / (skip + 1)


def deck_frames(namespace, count):
    return [frame(namespace, f"deck_slot_{i + 1}") for i in range(count)]
