"""Stage 0.5: M0609 refill scene. Empty world, M0609 + gripper USD, shelf, canister and an open dispenser slot.

Run in an Isaac shell (see sim/README.md, "0.5단계"):
    ~/isaacsim/python.sh sim/standalone/m0609_refill_stage.py --headless --robot-usd /abs/m0609_gripper.usd \
        --mode selfdemo --urdf /abs/m0609_isaac_sim.urdf --robot-description /abs/m0609_description.yaml
    ~/isaacsim/python.sh sim/standalone/m0609_refill_stage.py --headless --robot-usd /abs/m0609_gripper.usd --mode ros

--mode ros (default): ROS 2 names, types and QoS of contract v1 2.1 "M0609" so that rokey_p3_manipulation's
m0609_arm node drives this scene unchanged.
    publishes  /clock (OmniGraph, from minimal_clock.py), /m0609/joint_states (S, 30 Hz),
               /m0609/gripper/holding (H, 10 Hz)
    subscribes /m0609/arm/joint_command (R, JointState position), /m0609/gripper/command (R, Bool, true = close)
--mode selfdemo: no ROS topics besides /clock. Lula IK moves the TCP through a pick-and-insert plan once and logs
the reached joint positions as waypoint candidates for m0609_arm parameters.

Not here: conveyor, dispenser spawn, /sim/reset, AMR (simulation/navigation lanes). Stop with SIGINT only.
Importing this module does not start Isaac; Isaac/omni/pxr/rclpy imports live inside functions.

Asset facts used for defaults were read from the class asset on dev01 (2026-09-17, file inspection with usd-core,
not an Isaac run): Collected_m0609_gripper/m0609_gripper.usd has defaultPrim /World, robot /World/m0609 at the
origin, articulation root /World/m0609/root_joint, revolute joint_1..joint_6 under /World/m0609/joints, gripper
drive only on onrobot_rg2ft/joints/finger_joint (limit 0 to 67.6 deg) with five physxMimicJoint joints, and arm
drive stiffness between 11 and 1135. Whether master02 has the same file is not confirmed.
Class example 7_pick_place_color.py (same asset family, not run by us) supplied the TCP offset 0.19671 m on link_6,
the downward tool quaternion (0, 1, 0, 0), gripper open 0.0 / close 0.8 rad and drive gains 1e8 / 1e4 / 1e8.
"""

import argparse
import hashlib
import math
import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import minimal_clock as clock  # noqa: E402  (sibling script: /clock graph, SIGINT flag, env summary)
from p3sim.bridge import stamp  # noqa: E402

LOG_PREFIX = "[m0609_stage]"
NAMESPACE = "/m0609"

# Contract v1 2.1 M0609 = same as the amr_1 arm. Values mirror rokey_p3_manipulation arm_node.py QOS_*.
JOINT_STATES_HZ = 30.0  # S: best effort, volatile, depth 5
HOLDING_HZ = 10.0  # H: reliable, volatile, depth 1
COMMAND_QOS_DEPTH = 10  # R: reliable, volatile, depth 10

# From the dev01 class asset (see module docstring). 마클 확인 필요 on master02:
#   ~/isaacsim/python.sh -c "from pxr import Usd; s=Usd.Stage.Open('<usd>'); \
#   [print(p.GetPath(), p.GetTypeName()) for p in s.Traverse() if 'Joint' in p.GetTypeName()]"
DEFAULT_ROBOT_PRIM = "/World/m0609"
DEFAULT_MOUNT_PRIM = "/World"
DEFAULT_ARM_JOINTS = ("joint_1", "joint_2", "joint_3", "joint_4", "joint_5", "joint_6")
DEFAULT_GRIPPER_JOINT = "finger_joint"
DEFAULT_GRIP_LINK = "link_6"
DEFAULT_TCP_OFFSET = (0.0, 0.0, 0.19671)
DEFAULT_TOOL_QUAT = (0.0, 1.0, 0.0, 0.0)  # wxyz, tool z pointing down
DEFAULT_GRIPPER_OPEN = 0.0
DEFAULT_GRIPPER_CLOSE = 0.8
DEFAULT_DRIVE = (1e8, 1e4, 1e8)  # stiffness, damping, max force
# Gripper drive. The class example does NOT override the gripper drive (it only raises joint_1..joint_6). master02's
# first run (9/17) logged finger_joint stiffness 36.06, max effort 50 from the USD. These defaults are our choice,
# not a measured or documented value: stiff enough to hold a position target, torque capped low so the fingers do
# not shove the canister away. Tune with --gripper-drive.
DEFAULT_GRIPPER_DRIVE = (1e4, 1e2, 10.0)
DEFAULT_FINGER_LINKS = ("left_inner_finger", "right_inner_finger")
# OnRobot RG2 stroke 0 to 110 mm (manufacturer datasheet figure, not re-checked in this repo). Used only to turn the
# measured finger-link spacing into a pad gap; override with --open-width.
DEFAULT_OPEN_WIDTH = 0.110
DEFAULT_FRICTION = (1.0, 1.0)  # static, dynamic; our choice for a dry grip, not measured

# Provisional layout near the class example's pick area (x 0.30 to 0.38 m). Reach and collisions are NOT verified.
DEFAULT_SHELF_XYZ = (0.35, 0.25, 0.05)
DEFAULT_SHELF_SIZE = (0.16, 0.16, 0.10)
DEFAULT_CANISTER_SIZE = (0.04, 0.04, 0.08)
DEFAULT_CANISTER_XYZ = (0.35, 0.25, 0.14)  # bottom resting on the shelf top
DEFAULT_SLOT_XYZ = (0.35, -0.25, 0.15)  # slot A, on top of the dispenser body
DEFAULT_SLOT_B_XYZ = (0.35, -0.37, 0.15)  # slot B, next to A along y
DEFAULT_SLOT_SIZE = (0.10, 0.10, 0.10)  # outer box; the top face is open
DEFAULT_DISPENSER_HEIGHT = 0.10  # body under both slots; scenario 2: two slots A/B per drug
DEFAULT_SHELF_COUNT = 2  # dispenser.yaml shelf holds 2 per drug
DEFAULT_SHELF_PITCH = 0.06  # canisters side by side along +x behind the front one
COLORS = {"shelf": (0.55, 0.40, 0.25), "canister_front": (0.90, 0.15, 0.15), "canister_spare": (0.95, 0.60, 0.20),
          "dispenser": (0.45, 0.45, 0.50), "slot_a": (0.20, 0.35, 0.85), "slot_b": (0.20, 0.70, 0.35)}

# Remote viewing, as the class example 7_pick_place_color.py does it (LIVESTREAM=1): headless app, UI shown,
# explicit window size, then this extension. NVIDIA's 5.1.0 standalone_examples/api/isaacsim.simulation_app/
# livestream.py enables "omni.services.livestream.nvcf" instead. 마클 확인 필요:
#   ls ~/isaacsim/exts ~/isaacsim/extscache | grep -i livestream
DEFAULT_LIVESTREAM_EXTENSION = "omni.kit.livestream.webrtc"

DOF_TYPE_NAMES = {0: "rotation", 1: "translation"}  # omni.physics.tensors DofType, see log_dofs

STAGE_ROOT = "/World/P3Refill"
EE_HINTS = ("link_6", "tool0", "tcp", "flange", "gripper", "finger", "ee")
TEACH_KEYS = {"to_shelf": "shelf_approach", "descend": "shelf_grasp", "to_slot": "slot_{slot}_approach",
              "insert": "slot_{slot}_insert"}


# ---------------------------------------------------------------------------------------------------------------
# Pure helpers (no Isaac, covered by sim/tests/test_m0609_refill_stage.py)


def xyz(text):
    parts = text.replace(",", " ").split()
    if len(parts) != 3:
        raise argparse.ArgumentTypeError(f"need three numbers 'x y z', got {text!r}")
    try:
        values = tuple(float(part) for part in parts)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"not numbers: {text!r}") from error
    if not all(math.isfinite(value) for value in values):
        raise argparse.ArgumentTypeError(f"not finite: {text!r}")
    return values


def positive_xyz(text):
    values = xyz(text)
    if not all(value > 0.0 for value in values):
        raise argparse.ArgumentTypeError(f"sizes must be > 0: {text!r}")
    return values


def quat(text):
    parts = text.replace(",", " ").split()
    if len(parts) != 4:
        raise argparse.ArgumentTypeError(f"need four numbers 'w x y z', got {text!r}")
    values = tuple(float(part) for part in parts)
    norm = math.sqrt(sum(value * value for value in values))
    if not math.isfinite(norm) or norm < 1e-9:
        raise argparse.ArgumentTypeError(f"not a quaternion: {text!r}")
    return tuple(value / norm for value in values)


def build_parser():
    parser = argparse.ArgumentParser(description="Isaac Sim 5.1 M0609 refill stage (stage 0.5).")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--livestream", action="store_true",
                        help="WebRTC stream for remote viewing; implies headless with the UI shown (default off)")
    parser.add_argument("--livestream-extension", default=DEFAULT_LIVESTREAM_EXTENSION)
    parser.add_argument("--stream-width", type=int, default=1920, help="app window width for the stream")
    parser.add_argument("--stream-height", type=int, default=1080, help="app window height for the stream")
    parser.add_argument("--mode", choices=("ros", "selfdemo"), default="ros")
    parser.add_argument("--robot-usd", required=True, help="absolute path of the M0609 + gripper USD (not in Git)")
    parser.add_argument("--mount-prim", default=DEFAULT_MOUNT_PRIM, help="prim that references the USD defaultPrim")
    parser.add_argument("--robot-prim", default=DEFAULT_ROBOT_PRIM, help="articulation prim after referencing")
    parser.add_argument("--arm-joints", nargs=6, default=list(DEFAULT_ARM_JOINTS), metavar="NAME")
    parser.add_argument("--gripper-joint", default=DEFAULT_GRIPPER_JOINT)
    parser.add_argument("--gripper-open", type=float, default=DEFAULT_GRIPPER_OPEN, help="rad")
    parser.add_argument("--gripper-close", type=float, default=None,
                        help="rad; default derives it from --canister-size via the startup gripper sweep "
                             f"(fallback {DEFAULT_GRIPPER_CLOSE})")
    parser.add_argument("--gripper-drive", type=float, nargs=3, default=list(DEFAULT_GRIPPER_DRIVE),
                        metavar=("STIFFNESS", "DAMPING", "MAX_FORCE"), help="gripper (--gripper-joint) drive override")
    parser.add_argument("--keep-usd-gripper-drive", action="store_true", help="do not override the gripper drive")
    parser.add_argument("--finger-links", nargs=2, default=list(DEFAULT_FINGER_LINKS), metavar="LINK",
                        help="two finger pad links: spacing sweep and friction material")
    parser.add_argument("--open-width", type=clock.positive_float, default=DEFAULT_OPEN_WIDTH,
                        help="pad gap at gripper-open, m (RG2 datasheet stroke)")
    parser.add_argument("--grip-squeeze", type=clock.non_negative_float, default=0.004,
                        help="close target aims this much narrower than the canister width, m")
    parser.add_argument("--sweep-updates", type=int, default=30, help="updates per angle in the startup sweep")
    parser.add_argument("--no-gripper-sweep", action="store_true", help="skip the startup open/close sweep")
    parser.add_argument("--friction", type=clock.non_negative_float, nargs=2, default=list(DEFAULT_FRICTION),
                        metavar=("STATIC", "DYNAMIC"), help="physics material on canister and finger links")
    parser.add_argument("--grasp-settle", type=clock.non_negative_float, default=1.0,
                        help="selfdemo: sim seconds to hold still after closing")
    parser.add_argument("--lift-verify", type=clock.positive_float, default=0.01,
                        help="grasp_verified needs the canister this much above its z at grasp, m")
    parser.add_argument("--grip-link", default=DEFAULT_GRIP_LINK, help="link name under --robot-prim carrying the TCP")
    parser.add_argument("--tcp-offset", type=xyz, default=DEFAULT_TCP_OFFSET, help="TCP in --grip-link frame, m")
    parser.add_argument("--tool-quat", type=quat, default=DEFAULT_TOOL_QUAT, help="selfdemo TCP orientation w x y z")
    parser.add_argument("--drive", type=float, nargs=3, default=list(DEFAULT_DRIVE),
                        metavar=("STIFFNESS", "DAMPING", "MAX_FORCE"), help="arm joint drive override")
    parser.add_argument("--keep-usd-drives", action="store_true", help="do not override arm joint drives")
    parser.add_argument("--shelf-xyz", type=xyz, default=DEFAULT_SHELF_XYZ, help="shelf box center, m")
    parser.add_argument("--shelf-size", type=positive_xyz, default=DEFAULT_SHELF_SIZE)
    parser.add_argument("--canister-xyz", type=xyz, default=DEFAULT_CANISTER_XYZ, help="canister box center, m")
    parser.add_argument("--canister-size", type=positive_xyz, default=DEFAULT_CANISTER_SIZE)
    parser.add_argument("--canister-mass", type=clock.positive_float, default=0.05, help="kg")
    parser.add_argument("--slot-xyz", type=xyz, default=DEFAULT_SLOT_XYZ, help="slot outer box center, m")
    parser.add_argument("--slot-b-xyz", type=xyz, default=DEFAULT_SLOT_B_XYZ, help="slot B outer box center, m")
    parser.add_argument("--slot-size", type=positive_xyz, default=DEFAULT_SLOT_SIZE, help="slot outer box, open top")
    parser.add_argument("--dispenser-height", type=clock.non_negative_float, default=DEFAULT_DISPENSER_HEIGHT,
                        help="dispenser body under slots A and B, m; 0 = no body")
    parser.add_argument("--shelf-count", type=int, default=DEFAULT_SHELF_COUNT,
                        help="canisters on the shelf; the front one (--canister-xyz) is picked and respawned")
    parser.add_argument("--shelf-pitch", type=clock.positive_float, default=DEFAULT_SHELF_PITCH,
                        help="spacing of spare canisters along +x behind the front one, m")
    parser.add_argument("--loop-slots", choices=("a", "b", "ab"), default=None,
                        help="selfdemo slot per cycle; ab alternates A, B, A, ... (default: --slot-letter)")
    parser.add_argument("--slot-wall", type=clock.positive_float, default=0.01, help="slot wall and floor, m")
    parser.add_argument("--slot-letter", choices=("a", "b"), default="a", help="names teach lines slot_<a|b>_*")
    parser.add_argument("--hold-distance", type=clock.positive_float, default=0.05,
                        help="holding is true when closed and TCP to canister center is below this, m")
    parser.add_argument("--attach", action="store_true",
                        help="on close within --hold-distance, fix the canister to --grip-link; release on open")
    parser.add_argument("--urdf", help="selfdemo: URDF for Lula IK (class asset doosan-robot2/urdf)")
    parser.add_argument("--robot-description", help="selfdemo: Lula robot description yaml (class asset rmpflow/)")
    parser.add_argument("--clearance", type=clock.positive_float, default=0.06, help="selfdemo vertical clearance, m")
    parser.add_argument("--grip-depth", type=clock.non_negative_float, default=0.04,
                        help="selfdemo: TCP this far below the canister top when grasping, m")
    parser.add_argument("--tcp-speed", type=clock.positive_float, default=0.0007,
                        help="selfdemo m per update; 0.0007 at 60 Hz is about 4 cm/s, slow enough to follow by eye "
                             "(was 0.002)")
    parser.add_argument("--joint-space-phases", nargs="*", default=["to_shelf"],
                        help="selfdemo phases moved by interpolating joints to the IK solution at the goal instead "
                             "of a straight TCP line (9/17: to_shelf from home failed IK at 7 midpoints)")
    parser.add_argument("--tool-yaw", choices=("fixed", "radial"), default="fixed",
                        help="selfdemo tool yaw: fixed world orientation (--tool-quat), or turned about world z to "
                             "face the target from the robot base, which keeps joint_6 from counter-rotating")
    parser.add_argument("--joint-speed", type=clock.positive_float, default=0.5,
                        help="selfdemo return-home joint speed, rad per sim s (m0609_arm max_joint_speed default)")
    parser.add_argument("--phase-pause-s", type=clock.non_negative_float, default=0.5,
                        help="selfdemo: sim seconds to hold still between phases")
    parser.add_argument("--loop", type=int, default=1,
                        help="selfdemo cycles; after each the arm goes home and the canister returns to the shelf. "
                             "0 = forever")
    parser.add_argument("--respawn-delay-s", type=clock.non_negative_float, default=3.0,
                        help="ros: once the canister has sat in the slot with the gripper open for this long (sim s), "
                             "put it back on the shelf so the next Refill has one")
    parser.add_argument("--warmup-updates", type=int, default=10,
                        help="world steps after reset before reading joints and starting ROS publishing")
    parser.add_argument("--rate", type=clock.positive_float, default=clock.DEFAULT_RATE_HZ)
    parser.add_argument("--duration", type=clock.non_negative_float, default=0.0, help="wall s, 0 = until SIGINT")
    parser.add_argument("--physics-dt", type=clock.positive_float, default=1.0 / 60.0)
    parser.add_argument("--render-dt", type=clock.positive_float, default=1.0 / 60.0)
    return parser


def parse_args(argv=None):
    args, _unknown = build_parser().parse_known_args(argv)
    return args


def simulation_app_config(args):
    """SimulationApp launch config. --livestream follows 7_pick_place_color.py: headless, hide_ui False, size."""
    if not args.livestream:
        return {"headless": args.headless}
    return {"headless": True, "hide_ui": False, "width": args.stream_width, "height": args.stream_height}


def keep_running(app_running, app_exiting, headless):
    """Loop condition. Headless (and livestream) keep going while the app is not exiting, as 7_pick_place_color.py
    (`is_running() or args.headless or LIVESTREAM`) and NVIDIA 5.1.0 livestream.py (`_app.is_running() and not
    is_exiting()`) do, because is_running() can be False early when headless."""
    if app_running:
        return True
    return headless and not app_exiting


def aabb(center, size):
    low = tuple(c - s / 2.0 for c, s in zip(center, size, strict=True))
    high = tuple(c + s / 2.0 for c, s in zip(center, size, strict=True))
    return low, high


def aabbs_overlap(first, second, margin=0.0):
    (low_a, high_a), (low_b, high_b) = first, second
    return all(low_a[i] < high_b[i] - margin and low_b[i] < high_a[i] - margin for i in range(3))


def point_in_aabb(point, box):
    low, high = box
    return all(low[i] <= point[i] <= high[i] for i in range(3))


def slot_cavity(slot_xyz, slot_size, wall):
    """Inner box of the open-top slot: walls on four sides and a floor, open above."""
    inner = (slot_size[0] - 2.0 * wall, slot_size[1] - 2.0 * wall, slot_size[2] - wall)
    center = (slot_xyz[0], slot_xyz[1], slot_xyz[2] + wall / 2.0)
    return center, inner


def slot_center(args, letter):
    return args.slot_xyz if letter == "a" else args.slot_b_xyz


def slot_for_cycle(pattern, cycle):
    """Slot letter for a 1-based cycle: 'a', 'b', or 'ab' alternating starting with A."""
    if pattern == "ab":
        return "a" if cycle % 2 == 1 else "b"
    return pattern


def shelf_canister_positions(args):
    """Front canister first (the one picked), spares behind it along +x."""
    x, y, z = args.canister_xyz
    return [(x + i * args.shelf_pitch, y, z) for i in range(max(1, args.shelf_count))]


def dispenser_body(args):
    """(center, size) of the body under both slots, or None. Top face meets the lower slot bottom."""
    if args.dispenser_height <= 0.0:
        return None
    centers = (args.slot_xyz, args.slot_b_xyz)
    half = (args.slot_size[0] / 2.0, args.slot_size[1] / 2.0)
    low_x = min(c[0] for c in centers) - half[0] - 0.02
    high_x = max(c[0] for c in centers) + half[0] + 0.02
    low_y = min(c[1] for c in centers) - half[1] - 0.02
    high_y = max(c[1] for c in centers) + half[1] + 0.02
    top = min(c[2] for c in centers) - args.slot_size[2] / 2.0
    center = ((low_x + high_x) / 2.0, (low_y + high_y) / 2.0, top - args.dispenser_height / 2.0)
    return center, (high_x - low_x, high_y - low_y, args.dispenser_height)


def validate_layout(args, fit_margin=0.005, rest_tolerance=0.01):
    """Return a list of problems; empty means the boxes are consistent. Reach is not checked here."""
    problems = []
    shelf = aabb(args.shelf_xyz, args.shelf_size)
    slots = {letter: aabb(slot_center(args, letter), args.slot_size) for letter in ("a", "b")}
    _cavity_center, inner = slot_cavity(args.slot_xyz, args.slot_size, args.slot_wall)
    if inner[0] <= 0.0 or inner[1] <= 0.0 or inner[2] <= 0.0:
        problems.append(f"slot wall {args.slot_wall} leaves no cavity in slot size {args.slot_size}")
    for axis, label in ((0, "x"), (1, "y")):
        if inner[axis] < args.canister_size[axis] + 2.0 * fit_margin:
            problems.append(f"slot cavity {label} {inner[axis]:.3f} m does not fit canister "
                            f"{args.canister_size[axis]:.3f} m with {fit_margin} m margin each side")
    if args.shelf_count < 1:
        problems.append("--shelf-count must be at least 1")
    if args.shelf_count > 1 and args.shelf_pitch < args.canister_size[0] + fit_margin:
        problems.append(f"--shelf-pitch {args.shelf_pitch} m is narrower than a canister plus margin")
    shelf_top = shelf[1][2]
    canisters = [aabb(position, args.canister_size) for position in shelf_canister_positions(args)]
    for number, (position, box) in enumerate(zip(shelf_canister_positions(args), canisters, strict=True), 1):
        name = "canister" if number == 1 else f"shelf canister {number}"
        if abs(box[0][2] - shelf_top) > rest_tolerance:
            problems.append(f"{name} bottom z {box[0][2]:.3f} is not on shelf top z {shelf_top:.3f} "
                            f"(tolerance {rest_tolerance} m)")
        for axis, label in ((0, "x"), (1, "y")):
            if not shelf[0][axis] <= position[axis] <= shelf[1][axis]:
                problems.append(f"{name} center {label} is outside the shelf footprint")
        for letter, slot in slots.items():
            if aabbs_overlap(box, slot):
                problems.append(f"{name} starts inside slot {letter.upper()}")
    for letter, slot in slots.items():
        if aabbs_overlap(shelf, slot):
            problems.append(f"shelf and slot {letter.upper()} boxes overlap")
    if aabbs_overlap(slots["a"], slots["b"]):
        problems.append("slot A and slot B boxes overlap")
    body = dispenser_body(args)
    if body is not None:
        body_box = aabb(*body)
        if aabbs_overlap(body_box, shelf):
            problems.append("dispenser body and shelf overlap")
        if body_box[0][2] < -rest_tolerance:
            problems.append(f"dispenser body bottom z {body_box[0][2]:.3f} is below the ground; raise the slots")
        for letter in ("a", "b"):
            bottom = slot_center(args, letter)[2] - args.slot_size[2] / 2.0
            if abs(bottom - body_box[1][2]) > rest_tolerance:
                problems.append(f"slot {letter.upper()} bottom z {bottom:.3f} is not on the dispenser top "
                                f"z {body_box[1][2]:.3f}")
    return problems


def init_rclpy(rclpy):
    """rclpy.init without rclpy's own SIGINT/SIGTERM handlers, once per process. Returns how it was initialised.

    Our minimal_clock SIGINT handler sets a stop flag and the loop ends cleanly. rclpy's default handler shut the
    context down first, so the next publish raised and Ctrl-C ended with exit 1 ("publisher context invalid",
    9/18 master02 practice 1, pharmacy_stage)."""
    if rclpy.ok():
        return "already"
    try:
        from rclpy.signals import SignalHandlerOptions

        rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
        return "no_signal_handlers"
    except (ImportError, TypeError, AttributeError):
        rclpy.init()
        return "default_signal_handlers"


def holding_state(gripper_closed, tcp_xyz, canister_xyz, threshold):
    """Contract holding, simplified: gripper closed and canister center within threshold of the TCP."""
    if not gripper_closed or tcp_xyz is None or canister_xyz is None:
        return False
    return math.dist(tcp_xyz, canister_xyz) < threshold


def filter_joint_command(arm_joint_names, names, positions):
    """Map a JointState command to {name: position}. Returns (targets, reason); reason is None when accepted.

    Contract v1 2.1: only this arm's joint names; a command mixing other names is dropped whole.
    """
    names = list(names)
    positions = list(positions)
    if not names:
        return {}, "empty name list"
    if len(names) != len(positions):
        return {}, f"{len(names)} names but {len(positions)} positions"
    foreign = [name for name in names if name not in arm_joint_names]
    if foreign:
        return {}, f"unknown joint names {foreign}"
    if len(set(names)) != len(names):
        return {}, "duplicate joint names"
    if not all(math.isfinite(float(value)) for value in positions):
        return {}, "non-finite position"
    return {name: float(value) for name, value in zip(names, positions, strict=True)}, None


def quat_multiply(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return (w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2)


def quat_conjugate(q):
    return (q[0], -q[1], -q[2], -q[3])


def quat_rotate(q, v):
    rotated = quat_multiply(quat_multiply(q, (0.0, *v)), quat_conjugate(q))
    return rotated[1:]


def relative_pose(parent_xyz, parent_quat, child_xyz, child_quat):
    """Child pose in the parent frame (unit quaternions, wxyz). Used for the attach joint's local frame."""
    inverse = quat_conjugate(parent_quat)
    delta = tuple(c - p for c, p in zip(child_xyz, parent_xyz, strict=True))
    return quat_rotate(inverse, delta), quat_multiply(inverse, child_quat)


def tcp_world(link_xyz, link_quat, tcp_offset):
    return tuple(p + r for p, r in zip(link_xyz, quat_rotate(link_quat, tcp_offset), strict=True))


def plan_selfdemo(args, letter=None):
    """TCP targets for one pick-and-insert into slot `letter` (default --slot-letter).

    Each step is (phase, tcp_xyz, gripper 'open'|'close', wait). Clearance covers both slots so A and B plans
    share the same carry height."""
    target = slot_center(args, letter or args.slot_letter)
    cx, cy, cz = args.canister_xyz
    height = args.canister_size[2]
    shelf_top = args.shelf_xyz[2] + args.shelf_size[2] / 2.0
    slot_top = max(args.slot_xyz[2], args.slot_b_xyz[2]) + args.slot_size[2] / 2.0
    slot_floor = target[2] - args.slot_size[2] / 2.0 + args.slot_wall
    canister_top = cz + height / 2.0
    below_tcp = height - args.grip_depth  # canister bottom is this far below the TCP while carried
    safe_z = max(canister_top + args.clearance, max(shelf_top, slot_top) + args.clearance + below_tcp)
    grasp = (cx, cy, canister_top - args.grip_depth)
    above_canister = (cx, cy, safe_z)
    above_slot = (target[0], target[1], safe_z)
    insert = (target[0], target[1], slot_floor + 0.005 + below_tcp)
    return [
        ("to_shelf", above_canister, "open", False),
        ("descend", grasp, "open", False),
        ("grasp", grasp, "close", True),
        ("lift", above_canister, "close", False),
        ("to_slot", above_slot, "close", False),
        ("insert", insert, "close", False),
        ("release", insert, "open", True),
        ("retreat", above_slot, "open", False),
    ]


def yaw_quat(yaw):
    return (math.cos(yaw / 2.0), 0.0, 0.0, math.sin(yaw / 2.0))


def tool_quat_for(tool_quat, target_xyz, base_xyz, mode):
    """Tool orientation for a TCP target. radial: pre-rotate about world z by the base-to-target bearing."""
    if mode != "radial":
        return tuple(tool_quat)
    bearing = math.atan2(target_xyz[1] - base_xyz[1], target_xyz[0] - base_xyz[0])
    return quat_multiply(yaw_quat(bearing), tool_quat)


def next_publish_time(scheduled, now, rate_hz):
    """Advance a wall-clock publish schedule by one period without drift.

    `now + period` (the 9/17 code) pushes each deadline past the next 60 Hz update and gave 22.9 Hz for a 30 Hz
    target on master02. Stepping from the previous deadline keeps the average rate; if we fell more than a period
    behind, restart from now instead of bursting."""
    period = 1.0 / rate_hz
    following = scheduled + period
    return now if following < now - period else following


def exit_code_for(error_seen):
    """Process exit code. SimulationApp.close() ended the process with 0 even after an error on master02 (9/17),
    so the error path exits with this code before close()."""
    return 1 if error_seen else 0


class ThrottledLog:
    """Log the first occurrence and then every `every`-th, so a per-update condition cannot flood the log."""

    def __init__(self, every=60):
        self.every = every
        self.count = 0

    def hit(self):
        self.count += 1
        return self.count == 1 or self.count % self.every == 0


class DemoSequencer:
    """Selfdemo cycle state without Isaac. Modes: start_phase, run, pause, home, finished.

    start_phase -> run (the caller moves toward plan[index]) -> phase_done() -> pause -> next phase ... after the
    last phase: cycle_end (caller logs the result, goes home, respawns, calls home_done()) or finished."""

    def __init__(self, plan_length, loops, pause_updates):
        if plan_length < 1:
            raise ValueError("empty plan")
        self.plan_length = plan_length
        self.loops = max(0, int(loops))
        self.pause_updates = max(0, int(pause_updates))
        self.cycle = 1
        self.index = 0
        self.mode = "start_phase"
        self.remaining = 0

    def phase_done(self):
        """The current phase was reached. Returns None, "cycle_end" or "finished"."""
        if self.pause_updates:
            self.mode, self.remaining = "pause", self.pause_updates
            return None
        return self._advance()

    def tick_pause(self):
        """One update of pausing. Returns None, "cycle_end" or "finished" when the pause ends."""
        if self.mode != "pause":
            return None
        self.remaining -= 1
        if self.remaining > 0:
            return None
        return self._advance()

    def home_done(self):
        self.cycle += 1
        self.index = 0
        self.mode = "start_phase"

    def _advance(self):
        if self.index + 1 < self.plan_length:
            self.index += 1
            self.mode = "start_phase"
            return None
        if self.loops and self.cycle >= self.loops:
            self.mode = "finished"
            return "finished"
        self.mode = "home"
        return "cycle_end"


class RespawnTimer:
    """ros mode: refill the shelf once the canister has sat in the slot with the gripper open for delay_s."""

    def __init__(self, delay_s):
        self.delay_s = delay_s
        self.since = None

    def update(self, in_slot, gripper_open, now_s):
        if not (in_slot and gripper_open):
            self.since = None
            return False
        if self.since is None:
            self.since = now_s
        if now_s - self.since >= self.delay_s:
            self.since = None
            return True
        return False


def joint_steps(start, goal, speed_rad_s, dt, minimum=30):
    largest = max((abs(g - s) for s, g in zip(start, goal, strict=True)), default=0.0)
    return max(minimum, math.ceil(largest / (speed_rad_s * dt)))


def pad_widths(spacings, open_width):
    """Measured finger-link spacing per sweep angle -> pad gap, anchored so the first (open) spacing is open_width.

    The RG2 inner fingers stay parallel, so link spacing and pad gap differ by a constant."""
    if not spacings:
        return []
    offset = spacings[0] - open_width
    return [spacing - offset for spacing in spacings]


def close_target_from_sweep(angles, widths, target_width):
    """Angle where the pad gap reaches target_width, by linear interpolation. Returns (angle, clamped).

    Clamped is True when the gripper never gets that narrow (returns the last angle) or starts narrower."""
    pairs = list(zip(angles, widths, strict=True))
    if len(pairs) < 2:
        raise ValueError("need at least two sweep samples")
    if target_width >= pairs[0][1]:
        return pairs[0][0], True
    for (a0, w0), (a1, w1) in zip(pairs, pairs[1:], strict=False):
        if (w0 - target_width) * (w1 - target_width) <= 0.0 and w0 != w1:
            return a0 + (a1 - a0) * (w0 - target_width) / (w0 - w1), False
    return pairs[-1][0], True


def mimic_expected(reference_position, gearing, offset):
    """PhysX mimic joint constraint q + gearing * q_ref + offset = 0 (convention to confirm against the log)."""
    return -(gearing * reference_position + offset)


def grasp_verified(gripper_closed, z_at_grasp, z_now, threshold):
    """Contact grasp evidence: closed and the canister rose above its z at grasp by more than threshold."""
    if not gripper_closed or z_at_grasp is None or z_now is None:
        return False
    return z_now - z_at_grasp > threshold


def interpolation_steps(start, goal, speed, minimum=30, maximum=6000):
    return int(min(maximum, max(minimum, math.ceil(math.dist(start, goal) / speed))))


def lerp(start, goal, alpha):
    alpha = min(1.0, max(0.0, alpha))
    return tuple(s + alpha * (g - s) for s, g in zip(start, goal, strict=True))


def teach_key(phase, slot_letter):
    key = TEACH_KEYS.get(phase)
    return key.format(slot=slot_letter) if key else None


def format_joints(values):
    return "[" + ", ".join(f"{float(value):.4f}" for value in values) + "]"


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def log(text):
    write_line(f"{LOG_PREFIX} {text}")


def write_line(text, stream=None):
    """한 줄 찍는다. **stdout 이 닫혀 있어도 예외로 끝나지 않는다.**

    실습25(9/21): 관측 세션이 종료할 때 바깥 `tee` 가 먼저 죽어 stdout 파이프가 끊겼고, `stop reason=` 뒤의
    print 둘이 `BrokenPipeError` 로 터졌다. 그 줄은 rtf 와 종료 사유를 나르는 **판정의 출처**인데 stage.log 에
    안 남았다. 종료 구간의 줄이 파이프 사정으로 사라지면 안 된다.
    끊겼으면 stderr 로 물러나고, 그마저 닫혔으면 조용히 버린다 — 로그를 못 찍는 것이 회차를 끝낼 이유는 아니다.
    """
    stream = stream or sys.stdout
    try:
        print(text, file=stream, flush=True)
        return True
    except (BrokenPipeError, ValueError, OSError):
        pass
    if stream is not sys.stderr:
        try:
            print(text, file=sys.stderr, flush=True)
            return True
        except (BrokenPipeError, ValueError, OSError):
            pass
    return False


# ---------------------------------------------------------------------------------------------------------------
# Isaac side


def load_robot(args):
    import omni.usd
    from pxr import UsdGeom

    stage = omni.usd.get_context().get_stage()
    mount = stage.GetPrimAtPath(args.mount_prim)
    if not mount.IsValid():
        mount = UsdGeom.Xform.Define(stage, args.mount_prim).GetPrim()
    mount.GetReferences().AddReference(args.robot_usd)
    return stage


def ensure_light(stage):
    from pxr import UsdLux

    light_types = {"DomeLight", "DistantLight", "SphereLight", "RectLight", "DiskLight", "CylinderLight"}
    if any(prim.GetTypeName() in light_types for prim in stage.Traverse()):
        return
    UsdLux.DomeLight.Define(stage, f"{STAGE_ROOT}/DomeLight").CreateIntensityAttr(1000.0)


def log_ee_candidates(stage, robot_prim):
    from pxr import Usd

    root = stage.GetPrimAtPath(robot_prim)
    if not root.IsValid():
        log(f"ee_candidate none: {robot_prim} is not a valid prim")
        return
    for prim in Usd.PrimRange(root):
        name = prim.GetName().lower()
        if any(hint in name for hint in EE_HINTS):
            log(f"ee_candidate path={prim.GetPath()} type={prim.GetTypeName()}")


def override_drives(stage, robot_prim, joint_names, gains, keep, group):
    from pxr import Usd, UsdPhysics

    wanted = set(joint_names)
    for prim in Usd.PrimRange(stage.GetPrimAtPath(robot_prim)):
        if prim.GetName() not in wanted:
            continue
        drive = UsdPhysics.DriveAPI.Get(prim, "angular")
        if not drive or not drive.GetStiffnessAttr().IsValid():
            log(f"drive group={group} joint={prim.GetName()} none (angular DriveAPI missing)")
            continue
        before = (drive.GetStiffnessAttr().Get(), drive.GetDampingAttr().Get(), drive.GetMaxForceAttr().Get())
        if not keep:
            drive.GetStiffnessAttr().Set(float(gains[0]))
            drive.GetDampingAttr().Set(float(gains[1]))
            drive.GetMaxForceAttr().Set(float(gains[2]))
        after = (drive.GetStiffnessAttr().Get(), drive.GetDampingAttr().Get(), drive.GetMaxForceAttr().Get())
        log(f"drive group={group} joint={prim.GetName()} path={prim.GetPath()} before={before} after={after}")


def read_mimics(stage, robot_prim, reference_joint):
    """{joint name: (gearing, offset)} for joints whose physxMimicJoint reference is reference_joint; logged."""
    from pxr import Usd

    mimics = {}
    for prim in Usd.PrimRange(stage.GetPrimAtPath(robot_prim)):
        for axis in ("rotX", "rotY", "rotZ"):
            rel = prim.GetRelationship(f"physxMimicJoint:{axis}:referenceJoint")
            targets = rel.GetTargets() if rel else []
            if not targets or targets[0].name != reference_joint:
                continue
            gearing = prim.GetAttribute(f"physxMimicJoint:{axis}:gearing").Get()
            offset = prim.GetAttribute(f"physxMimicJoint:{axis}:offset").Get()
            mimics[prim.GetName()] = (float(gearing or 0.0), float(offset or 0.0))
            log(f"mimic joint={prim.GetName()} axis={axis} reference={targets[0]} gearing={gearing} offset={offset} "
                f"api_schemas={list(prim.GetAppliedSchemas())}")
    if not mimics:
        log(f"mimic none referencing {reference_joint}")
    return mimics


def apply_friction(stage, args, canister, robot_prim):
    from isaacsim.core.api.materials import PhysicsMaterial
    from pxr import Usd, UsdShade

    material = PhysicsMaterial(prim_path=f"{STAGE_ROOT}/GripMaterial", name="grip_material",
                               static_friction=float(args.friction[0]), dynamic_friction=float(args.friction[1]),
                               restitution=0.0)
    canister.apply_physics_material(material)
    log(f"friction material={STAGE_ROOT}/GripMaterial static={args.friction[0]} dynamic={args.friction[1]} "
        f"bound={STAGE_ROOT}/Canister")
    shade = UsdShade.Material(material.prim)
    for link in args.finger_links:
        matches = [p for p in Usd.PrimRange(stage.GetPrimAtPath(robot_prim)) if p.GetName() == link]
        if not matches:
            log(f"friction finger_link={link} not found")
            continue
        # Finger collision meshes are instance proxies in the class asset; bind on the non-instanced "collisions"
        # parent (physics purpose) so the binding is inherited, else on the link itself.
        target = matches[0].GetChild("collisions")
        target = target if target.IsValid() and not target.IsInstanceProxy() else matches[0]
        UsdShade.MaterialBindingAPI.Apply(target).Bind(shade, UsdShade.Tokens.weakerThanDescendants, "physics")
        log(f"friction bound={target.GetPath()}")


def build_boxes(args):
    """Shelf, spare and front canisters, dispenser body and slots A/B. Returns the front (picked) canister."""
    import numpy as np
    from isaacsim.core.api.objects import DynamicCuboid, FixedCuboid

    FixedCuboid(prim_path=f"{STAGE_ROOT}/Shelf", name="shelf", position=np.array(args.shelf_xyz),
                scale=np.array(args.shelf_size), size=1.0, color=np.array(COLORS["shelf"]))
    body = dispenser_body(args)
    if body is not None:
        FixedCuboid(prim_path=f"{STAGE_ROOT}/Dispenser/Body", name="dispenser_body", position=np.array(body[0]),
                    scale=np.array(body[1]), size=1.0, color=np.array(COLORS["dispenser"]))
    sx, sy, sz = args.slot_size
    wall = args.slot_wall
    for letter in ("a", "b"):
        x, y, z = slot_center(args, letter)
        parts = {
            "Floor": ((x, y, z - sz / 2.0 + wall / 2.0), (sx, sy, wall)),
            "WallXMinus": ((x - sx / 2.0 + wall / 2.0, y, z), (wall, sy, sz)),
            "WallXPlus": ((x + sx / 2.0 - wall / 2.0, y, z), (wall, sy, sz)),
            "WallYMinus": ((x, y - sy / 2.0 + wall / 2.0, z), (sx, wall, sz)),
            "WallYPlus": ((x, y + sy / 2.0 - wall / 2.0, z), (sx, wall, sz)),
        }
        for name, (center, size) in parts.items():
            FixedCuboid(prim_path=f"{STAGE_ROOT}/Dispenser/Slot{letter.upper()}/{name}",
                        name=f"slot_{letter}_{name.lower()}", position=np.array(center), scale=np.array(size),
                        size=1.0, color=np.array(COLORS[f"slot_{letter}"]))
    positions = shelf_canister_positions(args)
    for number, position in enumerate(positions[1:], 2):
        DynamicCuboid(prim_path=f"{STAGE_ROOT}/ShelfCanister{number}", name=f"shelf_canister_{number}",
                      position=np.array(position), scale=np.array(args.canister_size), size=1.0,
                      mass=args.canister_mass, color=np.array(COLORS["canister_spare"]))
    return DynamicCuboid(prim_path=f"{STAGE_ROOT}/Canister", name="canister", position=np.array(positions[0]),
                         scale=np.array(args.canister_size), size=1.0, mass=args.canister_mass,
                         color=np.array(COLORS["canister_front"]))


def log_dofs(robot):
    names = list(robot.dof_names)
    properties = robot.dof_properties
    initial = robot.get_joint_positions()
    # 5.1.0 SingleArticulation.dof_properties docstring says 0 invalid / 1 rotation / 2 translation, but the tensor
    # DofType used by Articulation.get_dof_types() is Rotation 0 / Translation 1. master02 (9/17) showed "invalid"
    # for all 12 revolute dofs with the docstring mapping, so we use the tensor enum and also print the raw value.
    kinds = DOF_TYPE_NAMES
    log(f"dof count={robot.num_dof} names={names}")
    for index, name in enumerate(names):
        prop = properties[index]
        log(f"dof index={index} name={name} type={kinds.get(int(prop['type']), 'unknown')} "
            f"type_raw={int(prop['type'])} "
            f"has_limits={bool(prop['hasLimits'])} lower={float(prop['lower']):.4f} upper={float(prop['upper']):.4f} "
            f"stiffness={float(prop['stiffness']):.4g} damping={float(prop['damping']):.4g} "
            f"max_effort={float(prop['maxEffort']):.4g} max_velocity={float(prop['maxVelocity']):.4g} "
            f"initial={float(initial[index]):.4f}")


class GripAttach:
    """--attach fallback: a PhysicsFixedJoint from the grip link to the canister, removed on release."""

    def __init__(self, stage, link_path, canister_path):
        self.stage = stage
        self.link_path = link_path
        self.canister_path = canister_path
        self.joint_path = f"{STAGE_ROOT}/AttachJoint"
        self.attached = False

    def attach(self, link_pose, canister_pose):
        from pxr import Gf, Sdf, UsdPhysics

        local_xyz, local_quat = relative_pose(link_pose[0], link_pose[1], canister_pose[0], canister_pose[1])
        joint = UsdPhysics.FixedJoint.Define(self.stage, self.joint_path)
        joint.CreateBody0Rel().SetTargets([Sdf.Path(self.link_path)])
        joint.CreateBody1Rel().SetTargets([Sdf.Path(self.canister_path)])
        joint.CreateLocalPos0Attr().Set(Gf.Vec3f(*map(float, local_xyz)))
        joint.CreateLocalRot0Attr().Set(Gf.Quatf(float(local_quat[0]), *map(float, local_quat[1:])))
        joint.CreateLocalPos1Attr().Set(Gf.Vec3f(0.0, 0.0, 0.0))
        joint.CreateLocalRot1Attr().Set(Gf.Quatf(1.0, 0.0, 0.0, 0.0))
        joint.CreateExcludeFromArticulationAttr().Set(True)
        self.attached = True
        log(f"attach joint={self.joint_path} body0={self.link_path} body1={self.canister_path} "
            f"local_pos0={format_joints(local_xyz)}")

    def release(self):
        if self.attached:
            self.stage.RemovePrim(self.joint_path)
            self.attached = False
            log(f"release joint={self.joint_path}")


class RosBridge:
    """Contract v1 2.1 M0609 topics on Isaac's internal rclpy."""

    def __init__(self, arm_joint_names, namespace=NAMESPACE, node_name="isaac_m0609_stage"):
        import rclpy
        from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
        from sensor_msgs.msg import JointState
        from std_msgs.msg import Bool

        self._rclpy = rclpy
        self._joint_state_type = JointState
        self._bool_type = Bool
        self.arm_joint_names = list(arm_joint_names)
        self.targets = None
        self.gripper_closed = None
        self._lock = threading.Lock()
        log(f"rclpy init={init_rclpy(rclpy)}")
        self.namespace = namespace
        self.node = rclpy.create_node(node_name)
        sensor = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT, durability=DurabilityPolicy.VOLATILE,
                            history=HistoryPolicy.KEEP_LAST, depth=5)
        reliable = QoSProfile(reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.VOLATILE,
                              history=HistoryPolicy.KEEP_LAST, depth=COMMAND_QOS_DEPTH)
        heartbeat = QoSProfile(reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.VOLATILE,
                               history=HistoryPolicy.KEEP_LAST, depth=1)
        self.joint_states_pub = self.node.create_publisher(JointState, f"{namespace}/joint_states", sensor)
        self.holding_pub = self.node.create_publisher(Bool, f"{namespace}/gripper/holding", heartbeat)
        self.node.create_subscription(JointState, f"{namespace}/arm/joint_command", self._on_joint_command, reliable)
        self.node.create_subscription(Bool, f"{namespace}/gripper/command", self._on_gripper_command, reliable)
        self._dropped = 0

    def _on_joint_command(self, msg):
        targets, reason = filter_joint_command(self.arm_joint_names, msg.name, msg.position)
        if reason is not None:
            self._dropped += 1
            if self._dropped <= 5 or self._dropped % 100 == 0:
                log(f"joint_command dropped count={self._dropped} reason={reason}")
            return
        with self._lock:
            self.targets = targets

    def _on_gripper_command(self, msg):
        with self._lock:
            self.gripper_closed = bool(msg.data)

    def take(self):
        with self._lock:
            targets, self.targets = self.targets, None
            return targets, self.gripper_closed

    def add_rail_topics(self, rail_joint_names):
        """Rail on the pharmacy stage: /m0609/rail/joint_command (R), /m0609/rail/joint_states (S). Not contract v1."""
        from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
        from sensor_msgs.msg import JointState

        self.rail_joint_names = list(rail_joint_names)
        self.rail_targets = None
        sensor = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT, durability=DurabilityPolicy.VOLATILE,
                            history=HistoryPolicy.KEEP_LAST, depth=5)
        reliable = QoSProfile(reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.VOLATILE,
                              history=HistoryPolicy.KEEP_LAST, depth=COMMAND_QOS_DEPTH)
        self.rail_states_pub = self.node.create_publisher(JointState, f"{NAMESPACE}/rail/joint_states", sensor)

        def on_rail(msg):
            targets, reason = filter_joint_command(self.rail_joint_names, msg.name, msg.position)
            if reason is not None:
                log(f"rail joint_command dropped reason={reason}")
                return
            with self._lock:
                self.rail_targets = targets

        self.node.create_subscription(JointState, f"{NAMESPACE}/rail/joint_command", on_rail, reliable)
        log(f"ros rail topics pub={NAMESPACE}/rail/joint_states sub={NAMESPACE}/rail/joint_command "
            f"joints={self.rail_joint_names}")

    def add_inventory_topic(self, topic="/m0609/shelf/inventory"):
        """Pharmacy scene v2: shelf inventory as std_msgs/String JSON, reliable + transient local, depth 1 (the last
        state reaches late subscribers). Not contract v1 (proposed with the arm session, 9/18)."""
        from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
        from std_msgs.msg import String

        latched = QoSProfile(reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                             history=HistoryPolicy.KEEP_LAST, depth=1)
        self._string_type = String
        self.inventory_pub = self.node.create_publisher(String, topic, latched)
        log(f"ros inventory topic pub={topic} (String JSON, reliable, transient_local, depth 1)")

    def publish_inventory(self, text):
        msg = self._string_type()
        msg.data = text
        self.inventory_pub.publish(msg)

    def add_amr_topics(self, joint_names, namespace="/amr_1"):
        """K2: 이동 베이스의 dummy 3축. `<ns>/base/joint_command` 를 받고 `<ns>/joint_states` 를 낸다.

        **명령은 속도다**(팔의 `arm/joint_command` 는 위치다). 이름으로 골라 우리 축 순서로 바꾼다 —
        위치로 집으면 주행이 순서를 바꿔 보낼 때 조용히 틀린다. **odom 과 TF 는 내지 않는다**(계약 3절).
        """
        from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
        from sensor_msgs.msg import JointState

        self.amr_joint_names = list(joint_names)
        self.amr_command = None
        self.amr_command_wall_s = None
        sensor = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT, durability=DurabilityPolicy.VOLATILE,
                            history=HistoryPolicy.KEEP_LAST, depth=5)
        reliable = QoSProfile(reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.VOLATILE,
                              history=HistoryPolicy.KEEP_LAST, depth=COMMAND_QOS_DEPTH)
        self.amr_states_pub = self.node.create_publisher(JointState, f"{namespace}/joint_states", sensor)

        def on_base(msg):
            with self._lock:
                self.amr_command = (list(msg.name), list(msg.velocity))
                self.amr_command_wall_s = time.monotonic()

        self.node.create_subscription(JointState, f"{namespace}/base/joint_command", on_base, reliable)
        log(f"ros amr topics pub={namespace}/joint_states sub={namespace}/base/joint_command "
            f"joints={self.amr_joint_names} (velocity command; no odom, no TF)")

    def take_amr(self):
        """((이름들, 속도들), 마지막 수신 시각) — 소비하지 않는다. 명령이 끊겼는지는 부르는 쪽이 본다."""
        with self._lock:
            return (getattr(self, "amr_command", None), getattr(self, "amr_command_wall_s", None))

    def publish_amr_states(self, sim_time, names, positions, velocities):
        """velocities 가 None 이면 **비운 채로** 낸다. 0 으로 채우면 base/stopped 가 항상 참이 된다(주행 9/21)."""
        msg = self._joint_state_type()
        timestamp = stamp(sim_time)
        msg.header.stamp.sec = timestamp["sec"]
        msg.header.stamp.nanosec = timestamp["nanosec"]
        msg.name = list(names)
        msg.position = [float(value) for value in positions]
        if velocities is not None:
            msg.velocity = [float(value) for value in velocities]
        self.amr_states_pub.publish(msg)

    def take_rail(self):
        with self._lock:
            targets, self.rail_targets = getattr(self, "rail_targets", None), None
            return targets

    def publish_rail_states(self, sim_time, positions, velocities):
        msg = self._joint_state_type()
        timestamp = stamp(sim_time)
        msg.header.stamp.sec = timestamp["sec"]
        msg.header.stamp.nanosec = timestamp["nanosec"]
        msg.name = list(self.rail_joint_names)
        msg.position = [float(value) for value in positions]
        msg.velocity = [float(value) for value in velocities]
        self.rail_states_pub.publish(msg)

    def spin_once(self):
        self._rclpy.spin_once(self.node, timeout_sec=0.0)

    def publish_joint_states(self, sim_time, positions, velocities):
        msg = self._joint_state_type()
        timestamp = stamp(sim_time)
        msg.header.stamp.sec = timestamp["sec"]
        msg.header.stamp.nanosec = timestamp["nanosec"]
        msg.name = list(self.arm_joint_names)
        msg.position = [float(value) for value in positions]
        msg.velocity = [float(value) for value in velocities]
        self.joint_states_pub.publish(msg)

    def publish_holding(self, holding):
        msg = self._bool_type()
        msg.data = bool(holding)
        self.holding_pub.publish(msg)

    def close(self, shutdown=True):
        self.node.destroy_node()
        if shutdown and self._rclpy.ok():
            self._rclpy.shutdown()


def log_app_state(simulation_app):
    """Why the loop saw the app stop: the three terms of SimulationApp.is_running() in 5.1.0."""
    try:
        kit_running = simulation_app._app.is_running()
        exiting = simulation_app.is_exiting()
        stage_missing = simulation_app.context.get_stage() is None
    except Exception as exc:  # diagnostics only
        log(f"app_state unavailable {type(exc).__name__}: {exc}")
        return
    log(f"app_state kit_running={kit_running} exiting={exiting} stage_missing={stage_missing}")


def run(args):
    problems = validate_layout(args)
    robot_usd = Path(args.robot_usd).expanduser()
    if not robot_usd.is_absolute() or not robot_usd.is_file():
        problems.append(f"--robot-usd must be an existing absolute file: {args.robot_usd}")
    if args.mode == "selfdemo":
        for flag, value in (("--urdf", args.urdf), ("--robot-description", args.robot_description)):
            if not value or not Path(value).expanduser().is_file():
                problems.append(f"selfdemo needs {flag} as an existing file, got {value!r}")
    if problems:
        for problem in problems:
            print(f"{LOG_PREFIX} error layout: {problem}", file=sys.stderr, flush=True)
        return 2

    from isaacsim import SimulationApp

    simulation_app = SimulationApp(simulation_app_config(args))
    stop_event = threading.Event()
    clock.install_sigint_handler(stop_event)
    exit_code = 0
    bridge = None
    try:
        import numpy as np
        import omni.kit.app
        from isaacsim.core.utils.extensions import enable_extension

        if args.livestream:
            enable_extension(args.livestream_extension)
        enable_extension(clock.ROS2_BRIDGE_EXTENSION)
        simulation_app.update()
        if not omni.kit.app.get_app().get_extension_manager().is_extension_enabled(clock.ROS2_BRIDGE_EXTENSION):
            raise RuntimeError(f"{clock.ROS2_BRIDGE_EXTENSION} did not stay enabled; see the bridge startup log")
        clock.build_clock_graph()

        import omni.timeline

        def on_timeline(event, name):
            log(f"timeline_event type={name} sim_time={clock.read_graph_sim_time():.3f}")

        timeline_events = omni.timeline.get_timeline_interface().get_timeline_event_stream()
        timeline_subscriptions = [  # kept alive for the whole run; diagnostic for the 9/17 ros-mode crash
            timeline_events.create_subscription_to_pop_by_type(
                int(getattr(omni.timeline.TimelineEventType, name)), lambda event, n=name: on_timeline(event, n))
            for name in ("PLAY", "PAUSE", "STOP")
        ]
        if args.mode == "ros":
            # 9/17 master02: --mode ros died on the first joint read after startup ("Physics Simulation View is not
            # created yet"); selfdemo did not. Start rclpy before any physics exists, like clock.py does.
            bridge = RosBridge(args.arm_joints)

        from isaacsim.core.api import World
        from isaacsim.core.api.objects import GroundPlane
        from isaacsim.core.prims import SingleArticulation, SingleXFormPrim
        from isaacsim.core.utils.types import ArticulationAction

        world = World(stage_units_in_meters=1.0, physics_dt=args.physics_dt, rendering_dt=args.render_dt)
        stage = load_robot(args)
        for _ in range(15):
            simulation_app.update()
        GroundPlane(prim_path=f"{STAGE_ROOT}/GroundPlane")
        ensure_light(stage)
        log_ee_candidates(stage, args.robot_prim)
        override_drives(stage, args.robot_prim, args.arm_joints, args.drive, args.keep_usd_drives, "arm")
        override_drives(stage, args.robot_prim, [args.gripper_joint], args.gripper_drive, args.keep_usd_gripper_drive,
                        "gripper")
        mimics = read_mimics(stage, args.robot_prim, args.gripper_joint)
        canister = build_boxes(args)
        apply_friction(stage, args, canister, args.robot_prim)
        robot = world.scene.add(SingleArticulation(prim_path=args.robot_prim, name="m0609"))
        world.scene.add(canister)
        world.reset()

        def physics_ready():
            return robot.handles_initialized and robot.get_joint_positions() is not None

        for update in range(1, max(1, args.warmup_updates) + 51):
            world.step(render=True)
            if update >= args.warmup_updates and physics_ready():
                log(f"physics_ready updates={update} playing={world.is_playing()} "
                    f"timeline_subscriptions={len(timeline_subscriptions)}")
                break
            if update >= args.warmup_updates:
                log(f"physics_not_ready update={update} playing={world.is_playing()}; re-initializing articulation")
                if not world.is_playing():
                    world.play()
                robot.initialize()
        else:
            raise RuntimeError("articulation physics view never became ready after world.reset(); see timeline_event")

        grip_link_path = f"{args.robot_prim}/{args.grip_link}"
        if not stage.GetPrimAtPath(grip_link_path).IsValid():
            from pxr import Usd

            matches = [str(p.GetPath()) for p in Usd.PrimRange(stage.GetPrimAtPath(args.robot_prim))
                       if p.GetName() == args.grip_link]
            if not matches:
                raise RuntimeError(f"grip link {args.grip_link!r} not found under {args.robot_prim}")
            grip_link_path = matches[0]
        grip_link = SingleXFormPrim(prim_path=grip_link_path, name="grip_link")

        log_dofs(robot)
        dof_names = list(robot.dof_names)
        missing = [name for name in [*args.arm_joints, args.gripper_joint] if name not in dof_names]
        if missing:
            raise RuntimeError(f"joints {missing} are not articulation dofs; see the dof lines above")
        arm_indices = np.array([robot.get_dof_index(name) for name in args.arm_joints])
        gripper_index = np.array([robot.get_dof_index(args.gripper_joint)])
        home = robot.get_joint_positions()[arm_indices]
        attach = GripAttach(stage, grip_link_path, f"{STAGE_ROOT}/Canister") if args.attach else None
        mimic_indices = {name: robot.get_dof_index(name) for name in mimics if name in dof_names}

        from pxr import Usd

        finger_prims = []
        for link in args.finger_links:
            found = [str(prim.GetPath()) for prim in Usd.PrimRange(stage.GetPrimAtPath(args.robot_prim))
                     if prim.GetName() == link]
            finger_prims.append(SingleXFormPrim(prim_path=found[0], name=f"finger_{link}") if found else None)

        def finger_spacing():
            if None in finger_prims:
                return None
            a = finger_prims[0].get_world_pose()[0]
            b = finger_prims[1].get_world_pose()[0]
            return math.dist(tuple(map(float, a)), tuple(map(float, b)))

        def log_gripper_state(tag):
            positions = robot.get_joint_positions()
            reference = float(positions[gripper_index[0]])
            parts = [f"{args.gripper_joint}={reference:.4f}"]
            for name, index in mimic_indices.items():
                gearing, offset = mimics[name]
                expected = mimic_expected(reference, gearing, offset)
                parts.append(f"{name}={float(positions[index]):.4f}(expected {expected:.4f})")
            spacing = finger_spacing()
            log(f"gripper_state tag={tag} finger_spacing={spacing if spacing is None else round(spacing, 4)} "
                + " ".join(parts))

        close_target = DEFAULT_GRIPPER_CLOSE if args.gripper_close is None else args.gripper_close
        close_source = "fallback" if args.gripper_close is None else "argument"
        if not args.no_gripper_sweep:
            upper = float(robot.dof_properties[gripper_index[0]]["upper"])
            lower = float(robot.dof_properties[gripper_index[0]]["lower"])
            if not upper > lower:
                upper, lower = 1.18, 0.0  # USD finger_joint limit 67.6 deg, if the dof reports no limit
            angles = [lower + (upper - lower) * i / 6.0 for i in range(7)]
            spacings = []
            for angle in angles:
                robot.apply_action(ArticulationAction(joint_positions=np.array([angle]), joint_indices=gripper_index))
                for _ in range(max(1, args.sweep_updates)):
                    world.step(render=True)
                spacings.append(finger_spacing())
                log_gripper_state(f"sweep_target_{angle:.3f}")
            robot.apply_action(ArticulationAction(joint_positions=np.array([args.gripper_open]),
                                                  joint_indices=gripper_index))
            for _ in range(max(1, args.sweep_updates)):
                world.step(render=True)
            if None not in spacings:
                widths = pad_widths(spacings, args.open_width)
                target_width = min(args.canister_size[0], args.canister_size[1]) - args.grip_squeeze
                derived, clamped = close_target_from_sweep(angles, widths, target_width)
                log(f"gripper_sweep angles={format_joints(angles)} spacing={format_joints(spacings)} "
                    f"pad_width={format_joints(widths)} target_width={target_width:.4f} derived={derived:.4f} "
                    f"clamped={clamped}")
                if args.gripper_close is None:
                    close_target, close_source = derived, "sweep"
            else:
                log("gripper_sweep skipped_derivation finger link prims not found")
        log(f"gripper_close target={close_target:.4f} source={close_source} open={args.gripper_open}")

        print(clock.format_start_line(clock.isaac_version_string(), clock.environment_summary(os.environ),
                                      world.get_physics_dt(), world.get_rendering_dt(), args.rate), flush=True)
        log(f"start mode={args.mode} grasp={'attach' if args.attach else 'physics'} robot_usd={robot_usd} "
            f"robot_usd_sha256={file_sha256(robot_usd)} robot_prim={args.robot_prim} grip_link={grip_link_path} "
            f"tcp_offset={args.tcp_offset} arm_joints={list(args.arm_joints)} gripper_joint={args.gripper_joint} "
            f"gripper_open={args.gripper_open} gripper_close={close_target:.4f} hold_distance={args.hold_distance} "
            f"gripper_drive={args.gripper_drive if not args.keep_usd_gripper_drive else 'usd'} "
            f"friction={args.friction} grip_depth={args.grip_depth} grasp_settle={args.grasp_settle} "
            f"lift_verify={args.lift_verify}")
        log(f"livestream enabled={args.livestream} extension={args.livestream_extension if args.livestream else '-'} "
            f"size={args.stream_width}x{args.stream_height}")
        log(f"layout shelf={args.shelf_xyz}/{args.shelf_size} canisters={shelf_canister_positions(args)}/"
            f"{args.canister_size} mass={args.canister_mass} slot_a={args.slot_xyz} slot_b={args.slot_b_xyz} "
            f"slot_size={args.slot_size} wall={args.slot_wall} dispenser_body={dispenser_body(args)}")
        log(f"teach home_joint_positions={format_joints(home)}")

        state = {"closed": False, "z_at_grasp": None, "verified": None, "holding": None}

        def poses():
            link = grip_link.get_world_pose()
            link_pose = (tuple(map(float, link[0])), tuple(map(float, link[1])))
            can = canister.get_world_pose()
            can_pose = (tuple(map(float, can[0])), tuple(map(float, can[1])))
            return link_pose, can_pose

        def set_gripper(closed):
            target = close_target if closed else args.gripper_open
            robot.apply_action(ArticulationAction(joint_positions=np.array([target]), joint_indices=gripper_index))
            if closed != state["closed"]:
                log(f"gripper {'close' if closed else 'open'} target={target:.4f}")
                state["z_at_grasp"] = poses()[1][0][2] if closed else None
            state["closed"] = closed
            if attach is None:
                return
            link_pose, can_pose = poses()
            tcp = tcp_world(link_pose[0], link_pose[1], args.tcp_offset)
            if closed and not attach.attached and holding_state(True, tcp, can_pose[0], args.hold_distance):
                attach.attach(link_pose, can_pose)
            elif not closed:
                attach.release()

        respawns = {"count": 0}

        def respawn_canister(reason):
            if attach is not None:
                attach.release()
            _link_pose, can_pose = poses()
            canister.set_world_pose(position=np.array(args.canister_xyz), orientation=np.array([1.0, 0.0, 0.0, 0.0]))
            canister.set_linear_velocity(np.zeros(3))
            canister.set_angular_velocity(np.zeros(3))
            respawns["count"] += 1
            log(f"respawn count={respawns['count']} reason={reason} from={format_joints(can_pose[0])} "
                f"to={format_joints(args.canister_xyz)} sim_time={clock.read_graph_sim_time():.3f}")

        def canister_slot():
            """'a', 'b' or None: which slot cavity holds the picked canister's center."""
            _link_pose, can_pose = poses()
            for letter in ("a", "b"):
                cavity = aabb(*slot_cavity(slot_center(args, letter), args.slot_size, args.slot_wall))
                if point_in_aabb(can_pose[0], cavity):
                    return letter
            return None

        def canister_in_slot():
            return canister_slot() is not None

        def holding_now():
            link_pose, can_pose = poses()
            tcp = tcp_world(link_pose[0], link_pose[1], args.tcp_offset)
            return holding_state(state["closed"], tcp, can_pose[0], args.hold_distance)

        def verified_now():
            _link_pose, can_pose = poses()
            return grasp_verified(state["closed"], state["z_at_grasp"], can_pose[0][2], args.lift_verify)

        def lift_dz():
            if state["z_at_grasp"] is None:
                return None
            return round(poses()[1][0][2] - state["z_at_grasp"], 4)

        demo = None
        if args.mode == "ros":
            log(f"ros topics pub={NAMESPACE}/joint_states(S {JOINT_STATES_HZ} Hz),{NAMESPACE}/gripper/holding"
                f"(H {HOLDING_HZ} Hz) sub={NAMESPACE}/arm/joint_command(R),{NAMESPACE}/gripper/command(R)")
        else:
            from isaacsim.robot_motion.motion_generation import ArticulationKinematicsSolver, LulaKinematicsSolver

            lula = LulaKinematicsSolver(robot_description_path=str(Path(args.robot_description).expanduser()),
                                        urdf_path=str(Path(args.urdf).expanduser()))
            base_xyz, base_quat = robot.get_world_pose()
            lula.set_robot_base_pose(robot_position=base_xyz, robot_orientation=base_quat)
            solver = ArticulationKinematicsSolver(robot, lula, args.grip_link)
            dt = world.get_rendering_dt()
            loop_slots = args.loop_slots or args.slot_letter
            plan = plan_selfdemo(args, slot_for_cycle(loop_slots, 1))
            demo = {"plan": plan, "seq": DemoSequencer(len(plan), args.loop, round(args.phase_pause_s / dt)),
                    "step": 0, "steps": 0, "start": None, "homing": None, "verified": None,
                    "wait_updates": max(1, int(round(args.grasp_settle / dt))),
                    "cycle_started": None, "letter": slot_for_cycle(loop_slots, 1), "taught": set()}
            log(f"selfdemo tool_yaw={args.tool_yaw} joint_space_phases={args.joint_space_phases} "
                "ik_seed=current joint positions (ArticulationKinematicsSolver warm start)")
            log(f"selfdemo loop={args.loop if args.loop else 'forever'} loop_slots={loop_slots} "
                f"tcp_speed={args.tcp_speed} "
                f"joint_speed={args.joint_speed} phase_pause_s={args.phase_pause_s}")
            for phase, tcp, gripper, _wait in demo["plan"]:
                log(f"selfdemo plan phase={phase} tcp={format_joints(tcp)} gripper={gripper}")

        def tool_orientation(tcp):
            return tool_quat_for(args.tool_quat, tcp, tuple(map(float, robot.get_world_pose()[0])), args.tool_yaw)

        def flange_target(tcp):
            offset = quat_rotate(tool_orientation(tcp), args.tcp_offset)
            return np.array([t - o for t, o in zip(tcp, offset, strict=True)])

        def selfdemo_result(event):
            seq = demo["seq"]
            _link_pose, can_pose = poses()
            log(f"cycle={seq.cycle} slot={demo['letter']} canister_in_slot={canister_slot() == demo['letter']} "
                f"canister_xyz={format_joints(can_pose[0])} "
                f"grasp={'attach' if args.attach else 'physics'} grasp_verified_at_lift={demo['verified']} "
                f"sim_s={clock.read_graph_sim_time() - demo['cycle_started']:.3f} next={event}")
            demo["verified"] = None
            if event == "cycle_end":
                start = tuple(map(float, robot.get_joint_positions()[arm_indices]))
                demo["homing"] = {"start": start, "step": 0,
                                  "steps": joint_steps(start, tuple(map(float, home)), args.joint_speed, dt)}
                set_gripper(False)
                log(f"selfdemo phase=home cycle={seq.cycle} steps={demo['homing']['steps']}")

        def selfdemo_update():
            seq = demo["seq"]
            if seq.mode == "finished":
                return
            if demo["cycle_started"] is None:
                demo["cycle_started"] = clock.read_graph_sim_time()
            if seq.mode == "home":
                homing = demo["homing"]
                if homing["step"] <= homing["steps"]:
                    alpha = homing["step"] / max(1, homing["steps"])
                    robot.apply_action(ArticulationAction(joint_positions=np.array(lerp(homing["start"], home, alpha)),
                                                          joint_indices=arm_indices))
                    homing["step"] += 1
                    return
                respawn_canister(f"selfdemo_cycle_{seq.cycle}")
                seq.home_done()
                demo["cycle_started"] = clock.read_graph_sim_time()
                demo["letter"] = slot_for_cycle(loop_slots, seq.cycle)
                demo["plan"] = plan_selfdemo(args, demo["letter"])
                return
            if seq.mode == "pause":
                event = seq.tick_pause()
                if event:
                    selfdemo_result(event)
                return
            phase, goal, gripper, wait = demo["plan"][seq.index]
            if seq.mode == "start_phase":
                link_pose, _can_pose = poses()
                demo["start"] = tcp_world(link_pose[0], link_pose[1], args.tcp_offset)
                demo["steps"] = demo["wait_updates"] if wait else interpolation_steps(demo["start"], goal,
                                                                                      args.tcp_speed)
                demo["step"] = 0
                demo["joint_path"] = None
                if phase in args.joint_space_phases and not wait:
                    solution, solved = solver.compute_inverse_kinematics(
                        target_position=flange_target(goal), target_orientation=np.array(tool_orientation(goal)))
                    if solved:
                        indices = np.array(solution.joint_indices)  # Lula cspace order, not necessarily --arm-joints
                        start_joints = tuple(map(float, robot.get_joint_positions()[indices]))
                        goal_joints = tuple(map(float, solution.joint_positions))
                        demo["joint_path"] = (start_joints, goal_joints, indices)
                        demo["steps"] = joint_steps(start_joints, goal_joints, args.joint_speed, dt)
                        log(f"selfdemo joint_space phase={phase} goal_joints={format_joints(goal_joints)}")
                    else:
                        log(f"selfdemo joint_space phase={phase} ik_failed_at_goal; falling back to TCP line")
                seq.mode = "run"
                log(f"selfdemo cycle={seq.cycle} slot={demo['letter']} phase={phase} steps={demo['steps']}")
                set_gripper(gripper == "close")
            if demo["step"] > demo["steps"]:
                joints = robot.get_joint_positions()[arm_indices]
                link_pose, _can_pose = poses()
                tcp_now = tcp_world(link_pose[0], link_pose[1], args.tcp_offset)
                log(f"selfdemo reached cycle={seq.cycle} phase={phase} tcp_error_m={math.dist(tcp_now, goal):.4f} "
                    f"holding_distance={holding_now()} grasp_verified={verified_now()} lift_dz={lift_dz()} "
                    f"canister_xyz={format_joints(poses()[1][0])} joints={format_joints(joints)}")
                if phase in ("grasp", "lift", "release"):
                    log_gripper_state(f"after_{phase}")
                if phase == "lift":
                    demo["verified"] = verified_now()
                key = teach_key(phase, demo["letter"])
                if key and key not in demo["taught"]:
                    demo["taught"].add(key)
                    log(f"teach {key}_joints={format_joints(joints)}")
                event = seq.phase_done()
                if event:
                    selfdemo_result(event)
                return
            if demo["joint_path"] is not None:
                start_joints, goal_joints, indices = demo["joint_path"]
                robot.apply_action(ArticulationAction(
                    joint_positions=np.array(lerp(start_joints, goal_joints, demo["step"] / max(1, demo["steps"]))),
                    joint_indices=indices))
                set_gripper(gripper == "close")
                demo["step"] += 1
                return
            target = goal if wait else lerp(demo["start"], goal, demo["step"] / max(1, demo["steps"]))
            action, solved = solver.compute_inverse_kinematics(target_position=flange_target(target),
                                                               target_orientation=np.array(tool_orientation(target)))
            if solved:
                robot.apply_action(action)
            elif demo["step"] % 60 == 0:
                log(f"selfdemo ik_failed phase={phase} target={format_joints(target)}")
            set_gripper(gripper == "close")
            demo["step"] += 1

        period = 1.0 / args.rate
        started = time.monotonic()
        sim_started = clock.read_graph_sim_time()
        next_tick = started
        next_joint_states = started
        next_holding = started
        updates = 0
        reason = "app_stopped"
        headless = args.headless or args.livestream
        not_ready = ThrottledLog(60)
        respawn_timer = RespawnTimer(args.respawn_delay_s)
        while not stop_event.is_set() and keep_running(simulation_app.is_running(), simulation_app.is_exiting(),
                                                       headless):
            now = time.monotonic()
            if args.duration and now - started >= args.duration:
                reason = "duration"
                break
            if bridge is not None and not physics_ready():
                # A timeline STOP drops the articulation handle (5.1.0 articulation.py). Skip this tick, recover.
                if not_ready.hit():
                    log(f"physics_not_ready count={not_ready.count} playing={world.is_playing()} "
                        f"stopped={world.is_stopped()}; skipping ROS I/O this tick")
                if world.is_stopped():
                    world.play()
                world.step(render=True)
                robot.initialize()
                updates += 1
                continue
            if bridge is not None:
                bridge.spin_once()
                targets, closed = bridge.take()
                if targets:
                    indices = np.array([robot.get_dof_index(name) for name in targets])
                    robot.apply_action(ArticulationAction(joint_positions=np.array(list(targets.values())),
                                                          joint_indices=indices))
                if closed is not None:
                    set_gripper(closed)
                elif attach is not None and state["closed"] and not attach.attached:
                    set_gripper(True)  # closed before reaching the canister: keep trying to attach
            else:
                selfdemo_update()
            world.step(render=True)
            updates += 1
            now = time.monotonic()
            if bridge is not None and now >= next_joint_states:
                bridge.publish_joint_states(clock.read_graph_sim_time(), robot.get_joint_positions()[arm_indices],
                                            robot.get_joint_velocities()[arm_indices])
                next_joint_states = next_publish_time(next_joint_states, now, JOINT_STATES_HZ)
            if bridge is not None and respawn_timer.update(canister_in_slot(), not state["closed"],
                                                           clock.read_graph_sim_time()):
                respawn_canister("ros_refill_done")
            if bridge is not None and now >= next_holding:
                holding = holding_now()
                bridge.publish_holding(holding)
                verified = verified_now()
                if (holding, verified) != (state["holding"], state["verified"]):
                    log(f"holding topic={holding} (distance only) grasp_verified={verified} lift_dz={lift_dz()}")
                    state["holding"], state["verified"] = holding, verified
                next_holding = next_publish_time(next_holding, now, HOLDING_HZ)
            next_tick += period
            delay = next_tick - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            else:
                next_tick = time.monotonic()

        elapsed = time.monotonic() - started
        sim_elapsed = clock.read_graph_sim_time() - sim_started
        if stop_event.is_set():
            reason = "sigint"
        if reason == "app_stopped":
            log_app_state(simulation_app)
        log(f"stop reason={reason} updates={updates} wall_s={elapsed:.3f} "
            f"loop_hz={updates / elapsed if elapsed > 0 else 0.0:.2f} sim_s={sim_elapsed:.3f} "
            f"rtf={sim_elapsed / elapsed if elapsed > 0 else 0.0:.3f}")
    except Exception as exc:
        import traceback

        print(f"{LOG_PREFIX} error {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        traceback.print_exc()
        exit_code = exit_code_for(True)
    finally:
        if bridge is not None:
            try:
                bridge.close()
            except Exception as exc:  # shutdown must continue
                print(f"{LOG_PREFIX} bridge close error {exc}", file=sys.stderr, flush=True)
        if exit_code:
            print(f"{LOG_PREFIX} exit code={exit_code} (skipping simulation_app.close(), which exits 0)",
                  file=sys.stderr, flush=True)
            sys.stdout.flush()
            os._exit(exit_code)
        simulation_app.close()
    return exit_code


def main(argv=None):
    return run(parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
