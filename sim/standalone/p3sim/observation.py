"""Parallel belt observation (contract v1 11.6, BeltObservation.msg). No Isaac imports.

Enum values are the integers of src/rokey_p3_interfaces/msg/BeltObservation.msg; 0 is always UNKNOWN. The stage
fills /isaac/pharmacy/belt_observation from the same BeltModel state as /isaac/pharmacy/belt.
"""

import math

MODE_UNKNOWN, MODE_STUB, MODE_SIM_SENSOR, MODE_PERCEPTION = 0, 1, 2, 3
OCCUPANCY_UNKNOWN, OCCUPANCY_EMPTY, OCCUPANCY_OCCUPIED = 0, 1, 2
ZONE_UNKNOWN, ZONE_ON_BELT, ZONE_END, ZONE_OFF_BELT = 0, 1, 2, 3
MOTION_UNKNOWN, MOTION_MOVING, MOTION_STOPPED = 0, 1, 2
APPLIED_UNKNOWN, APPLIED_RUN, APPLIED_STOP = 0, 1, 2

# remove_pouch reasons that free the belt without a physical pick (contract 11.1 b): the next observation is STUB.
STUB_RELEASES = ("ros_pick_notice", "ros_pick_stand_in", "selfdemo_pick")


class StepCounter:
    """Physics-step counter shared by every Isaac observation (belt, gripper): +1 only when sim time moved forward,
    so a stalled clock never makes an observation look fresh."""

    def __init__(self):
        self.seq = 0
        self._last = None

    def tick(self, sim_time):
        if self._last is None or sim_time > self._last:
            if self._last is not None:
                self.seq += 1
            self._last = sim_time
        return self.seq


class MotionTracker:
    """Pouch motion from speed samples. STOPPED only after settle_time_s of received samples at or below
    settle_speed without a gap (the at_end rule); a missing sample or no tracked pouch is UNKNOWN and restarts the
    settle time. Slow but not yet settled is MOVING: anything but STOPPED withholds a pick."""

    def __init__(self, settle_speed, settle_time_s):
        self.settle_speed = settle_speed
        self.settle_time_s = settle_time_s
        self.reset()

    def reset(self):
        self._slow_since = None
        self.motion = MOTION_UNKNOWN

    def update(self, speed, now_s):
        if speed is None:
            self.reset()
        elif speed > self.settle_speed:
            self._slow_since = None
            self.motion = MOTION_MOVING
        else:
            if self._slow_since is None:
                self._slow_since = now_s
            settled = now_s - self._slow_since >= self.settle_time_s
            self.motion = MOTION_STOPPED if settled else MOTION_MOVING
        return self.motion


def pouch_zone(model, frame_point):
    """Where the tracked pouch is now: ZONE_UNKNOWN without a pose, else OFF_BELT / END / ON_BELT (BeltModel
    geometry). Not latched."""
    if frame_point is None:
        return ZONE_UNKNOWN
    if not model.on_belt(frame_point):
        return ZONE_OFF_BELT
    return ZONE_END if model.in_end_zone(frame_point) else ZONE_ON_BELT


def occupancy(model):
    """OCCUPANCY_UNKNOWN for a lost pouch (--belt-fail-closed keeps /pharmacy/belt occupied=true then)."""
    if getattr(model, "lost", False):
        return OCCUPANCY_UNKNOWN
    return OCCUPANCY_OCCUPIED if model.occupied else OCCUPANCY_EMPTY


def command_applied(value):
    """Belt drive attribute read back (a scalar speed or a surface velocity vector): APPLIED_STOP when zero,
    APPLIED_RUN otherwise, APPLIED_UNKNOWN when it could not be read. A command state, not observed motion."""
    if value is None:
        return APPLIED_UNKNOWN
    try:
        magnitude = math.sqrt(sum(float(v) ** 2 for v in value))
    except TypeError:
        try:
            magnitude = abs(float(value))
        except (TypeError, ValueError):
            return APPLIED_UNKNOWN
    except ValueError:
        return APPLIED_UNKNOWN
    return APPLIED_STOP if magnitude == 0.0 else APPLIED_RUN


def fields(model, epoch, seq, mode, zone, motion, applied):
    """BeltObservation fields for bridge.encode (header.stamp goes in separately as 'stamp')."""
    tracked = model.occupied and not getattr(model, "lost", False)
    return {"epoch": epoch, "seq": seq, "request_id": model.request_id if model.occupied else "",
            "order_id": model.order_id, "mode": mode, "occupancy": occupancy(model),
            "pouch_zone": zone if tracked else ZONE_UNKNOWN, "pouch_motion": motion if tracked else MOTION_UNKNOWN,
            "belt_motion": MOTION_UNKNOWN, "belt_command_applied": applied}


# GripperState.msg (contract 11.6). The stage's suction is attach-by-distance plus teleport: always VIRTUAL.
STATE_UNKNOWN, STATE_RELEASED, STATE_HELD = 0, 1, 2
GRIPPER_MODE_UNKNOWN, GRIPPER_MODE_VIRTUAL, GRIPPER_MODE_PHYSICAL = 0, 1, 2


class GripperCommandGate:
    """GripperCommand (command_seq) filter. A command applies once: another epoch or a command_seq not above the last
    applied one is ignored (resends are idempotent). Applied means processed: a close with nothing in reach counts.
    reset() on RESET_DONE puts the counter back to 0 until the arm's first command (seq 1)."""

    def __init__(self):
        self.last_applied = 0

    def reset(self):
        self.last_applied = 0

    def accept(self, message, epoch):
        """(apply, reason) for a decoded command message in the stage's current epoch."""
        if message["epoch"] != epoch:
            return False, f"epoch {message['epoch']} is not current {epoch}"
        if message["command_seq"] <= self.last_applied:
            return False, f"command_seq {message['command_seq']} is not above {self.last_applied}"
        self.last_applied = message["command_seq"]
        return True, ""


def gripper_fields(epoch, seq, last_applied, holding):
    """GripperState fields for bridge.encode. holding None = no gripper to read: STATE_UNKNOWN."""
    state = STATE_UNKNOWN if holding is None else (STATE_HELD if holding else STATE_RELEASED)
    return {"epoch": epoch, "seq": seq, "last_applied_command_seq": last_applied, "state": state,
            "mode": GRIPPER_MODE_VIRTUAL if holding is not None else GRIPPER_MODE_UNKNOWN}
