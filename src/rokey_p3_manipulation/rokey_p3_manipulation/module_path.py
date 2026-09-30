"""Bounded, sampled module-refill planning for the v2 XYZ simulator.

No DRL/MoveIt or force-control emulation. A returned plan is a simulator candidate,
not a continuous collision certificate or a hardware safety permission.
"""

import copy
import math
from dataclasses import dataclass
from itertools import product

from rokey_p3_manipulation import clearance as C
from rokey_p3_manipulation import m0609_kinematics as K
from rokey_p3_manipulation import refill_sequence as S
from rokey_p3_manipulation import scene_v2 as V


@dataclass(frozen=True)
class Limits:
    joint_speed: tuple = (2.356, 2.356, 2.827, 3.534, 3.534, 3.534)   # M0609 두산 사양의 90%(재범 9/24)
    joint_accel: tuple = (4., 4., 4., 6., 6., 6.)
    rail_speed: tuple = (0.8, 0.8, 0.8)
    rail_accel: tuple = (1., 1., 1.)
    period: float = 0.02
    micro_speed: float = 0.05
    clearance: float = 0.01
    payload_clearance: float = 0.001
    joint_sample: float = 0.02
    linear_sample: float = 0.004
    rail_sample: float = 0.01

    def __post_init__(self):
        for name, size in (('joint_speed', 6), ('joint_accel', 6), ('rail_speed', 3), ('rail_accel', 3)):
            values = K.finite(getattr(self, name), size)
            if min(values) <= 0:
                raise K.PlanError(f'{name}: positive limits required')
            object.__setattr__(self, name, values)
        values = K.finite((self.period, self.micro_speed, self.clearance, self.payload_clearance,
                           self.joint_sample, self.linear_sample, self.rail_sample), 7)
        if min(values) <= 0 or self.micro_speed > 0.05:
            raise K.PlanError('positive limits and micro_speed <= 0.05 m/s required')


@dataclass(frozen=True)
class Segment:
    phase: str
    actor: str                     # arm / rail / close / open
    points: tuple                  # includes start and final point
    carrying: bool
    seconds: float


@dataclass(frozen=True)
class Plan:
    segments: tuple
    seconds: float                 # motion time; sensor waits are not predicted
    clearance: float
    evaluated: int
    feasible: int
    scene_signature: str
    cell_id: str


AXES = ((1., 0., 0.), (0., 1., 0.), (0., 0., 1.))


def separating_gap(a, b, stop_at=None):
    """Conservative OBB distance lower bound from all 15 separating axes.

    OBB = (center, unit axes, half sizes). A positive projection gap certifies
    separation; zero means touching/overlap. Unlike an unfinished closest-point
    iteration, this cannot overestimate clearance and accept a collision.
    """
    ac, aa, ah = a
    bc, ba, bh = b
    delta = K.sub(ac, bc)
    best = 0.
    for axis in (*aa, *ba, *(K.cross(x, y) for x in aa for y in ba)):
        length = math.hypot(*axis)
        if length < 1e-10:
            continue
        axis = K.scale(axis, 1 / length)
        radius = sum(h * abs(K.dot(axis, u)) for h, u in zip(ah, aa, strict=True))
        radius += sum(h * abs(K.dot(axis, u)) for h, u in zip(bh, ba, strict=True))
        best = max(best, abs(K.dot(delta, axis)) - radius)
        if stop_at is not None and best >= stop_at:
            return best
    return best


def payload_box(cell, grip):
    """Actual module dimensions and TCP-to-object offset, expressed in TCP axes."""
    corners = [K.rotate(K.conjugate(V.FRONT), K.sub(K.add(cell.center, offset), grip))
               for offset in product(*((-size / 2, size / 2) for size in cell.size))]
    return C.LinkBox('canister', 'module_payload', tuple(min(p[i] for p in corners) for i in range(3)),
                     tuple(max(p[i] for p in corners) for i in range(3)))


def _check_linear_chord(model, q0, q1, first, point, limits):
    distance = math.dist(first.position_m, point)
    axis = K.scale(K.sub(point, first.position_m), 1 / distance) if distance > 1e-12 else (0., 0., 0.)
    for q in (q0, *S.interpolate(q0, q1, limits.joint_sample)):
        pose = model.fk(q)
        along = K.sub(pose.position_m, first.position_m)
        nearest = K.add(first.position_m, K.scale(axis, min(distance, max(0., K.dot(along, axis)))))
        if math.dist(pose.position_m, nearest) > 0.0005:
            raise K.PlanError('joint chord departs from Cartesian line')
        if math.hypot(*K.rotation_error(V.FRONT, pose.orientation_xyzw)) > 0.005:
            raise K.PlanError('joint chord tilts payload')


def linear_path(model, start, point, limits):
    """Base-frame LIN, constant TCP quaternion, seeded IK, checked joint chords."""
    first = model.fk(start)
    if math.hypot(*K.rotation_error(V.FRONT, first.orientation_xyzw)) > 0.001:
        raise K.PlanError('LIN start orientation is not the module carry orientation')
    path = [tuple(start)]
    distance = math.dist(first.position_m, point)
    count = max(1, math.ceil(distance / limits.linear_sample))

    def solve_interval(q0, p0, p1, depth=0):
        try:
            q1 = model.inverse(K.Pose(p1, V.FRONT), q0)
            K.check_joint_segment(q0, q1)
            _check_linear_chord(model, q0, q1, first, point, limits)
            return [q1]
        except K.PlanError:
            if depth >= 6:
                raise
            middle = K.scale(K.add(p0, p1), .5)
            left = solve_interval(q0, p0, middle, depth + 1)
            return left + solve_interval(left[-1], middle, p1, depth + 1)

    for i in range(1, count + 1):
        p = K.add(first.position_m, K.scale(K.sub(point, first.position_m), i / count))
        previous_p = model.fk(path[-1]).position_m
        path.extend(solve_interval(path[-1], previous_p, p))
    return tuple(path)


def retime(path, speed, accel, period, model=None, tcp_speed=None, check_chord=None):
    """Rest-to-rest quintic progress over a polyline; check sampled v/a limits.

    The finite differences include zero velocity before/after the segment.
    Controller dynamics and jerk are not certified by this time estimate.
    """
    path = tuple(tuple(p) for p in path)
    if len(path) < 2:
        raise K.PlanError('a path needs both endpoints')
    distances = [math.dist(a, b) for a, b in zip(path, path[1:], strict=False)]
    total = sum(distances)
    if total < 1e-12:
        return (path[0], path[-1])
    cumulative = [0.]
    for d in distances:
        cumulative.append(cumulative[-1] + d / total)
    variation = [sum(abs(b[j] - a[j]) for a, b in zip(path, path[1:], strict=False)) for j in range(len(speed))]
    duration = max(period, *(2 * d / v for d, v in zip(variation, speed, strict=True)),
                   *(math.sqrt(6 * d / a) for d, a in zip(variation, accel, strict=True)))
    if model is not None:
        tcp_distance = sum(math.dist(model.fk(a).position_m, model.fk(b).position_m)
                           for a, b in zip(path, path[1:], strict=False))
        duration = max(duration, 2 * tcp_distance / tcp_speed)
    for _ in range(10):
        count = math.ceil(duration / period)
        if count > 100000:
            raise K.PlanError('trajectory sample budget exceeded')
        points, sources, index = [], [], 0
        for i in range(count + 1):
            t = i / count
            u = t**3 * (10 + t * (-15 + 6 * t))
            while index < len(path) - 2 and cumulative[index + 1] < u:
                index += 1
            span = cumulative[index + 1] - cumulative[index]
            f = 0. if span < 1e-12 else min(1., max(0., (u - cumulative[index]) / span))
            points.append(K.add(path[index], K.scale(K.sub(path[index + 1], path[index]), f)))
            sources.append(index)
        points[0], points[-1] = path[0], path[-1]
        velocities = [K.scale(K.sub(b, a), 1 / period) for a, b in zip(points, points[1:], strict=False)]
        zero = (0.,) * len(speed)
        padded = [zero, *velocities, zero]
        accelerations = [K.scale(K.sub(b, a), 1 / period) for a, b in zip(padded, padded[1:], strict=False)]
        ratio = max(1., *(abs(v) / cap for vel in velocities for v, cap in zip(vel, speed, strict=True)),
                    *(math.sqrt(abs(a) / cap) for acc in accelerations for a, cap in zip(acc, accel, strict=True)))
        if model is not None:
            ratio = max(ratio, S.peak_speed(points, period, lambda q: model.fk(q).position_m) / tcp_speed)
        if ratio <= 1 + 1e-9:
            if check_chord is not None:
                for i in range(1, len(points)):
                    # Within one source edge the geometry is unchanged. Crossing
                    # a vertex creates a new chord that must be checked as sent.
                    if sources[i - 1] != sources[i]:
                        check_chord(points[i - 1], points[i])
            return tuple(points)
        duration = count * period * ratio * 1.05
    raise K.PlanError('could not satisfy sampled velocity/acceleration bounds')


def _check_scene(scene, cell, params, limits):
    if cell.kind != 'module' or cell.access != 'front':
        raise K.PlanError('guarded path supports front-access modules only')
    if scene.rail_names != ('rail_x', 'rail_y', 'rail_z'):
        raise K.PlanError('guarded path requires XYZ translational rail')
    if not scene.obstacles or not scene.rail_parts:
        raise K.PlanError('complete environment and rail geometry required')
    target = scene.targets.get('module')
    if target is None or math.dist(K.finite(target.axis, 3), (0., 1., 0.)) > 1e-6:
        raise K.PlanError('module slot must face +Y in the v2 world frame')
    for values in (scene.base_origin, cell.center, cell.size, target.point):
        K.finite(values, 3)
    if min(cell.size) <= 0 or not V.fits(cell, target, limits.payload_clearance):
        raise K.PlanError('module does not fit the slot with clearance')
    depth = K.finite((target.data.get('depth', math.nan),), 1)[0]
    if depth <= params.module_push + cell.size[1] / 2 + limits.payload_clearance:
        raise K.PlanError('insertion would hit the slot back')
    for box in (*scene.obstacles, *scene.rail_parts):
        if min(K.finite(box.size, 3)) <= 0:
            raise K.PlanError('invalid obstacle dimensions')
        K.finite(box.center, 3)
    for low, high in scene.rail_limits:
        if not math.isfinite(low + high) or low >= high:
            raise K.PlanError('invalid rail limits')
    offsets = K.finite((params.approach, params.lift, params.hover, params.retreat, params.rail_limit_margin,
                        params.min_reach, params.module_grip, params.module_push), 8)
    if min(offsets) <= 0 or type(params.max_rail_tries) is not int or params.max_rail_tries < 1:
        raise K.PlanError('positive geometric offsets required')
    return target


class _Builder:
    def __init__(self, model, scene, boxes, tcp, limits, home, rail):
        self.model, self.scene, self.boxes, self.tcp, self.limits = model, scene, boxes, tcp, limits
        self.q, self.rail = tuple(home), tuple(rail)
        self.carrying, self.segments, self.clearance = False, [], math.inf
        self.phase = 'start'

    def check(self, q, rail, support_contact=False):
        self.model.check_limits(q)
        if K.wrist_clearance_rad(q[4]) < math.radians(5):
            raise K.PlanError('wrist singularity margin')
        if self.carrying and math.hypot(*K.rotation_error(V.FRONT, self.model.fk(q).orientation_xyzw)) > 0.005:
            raise K.PlanError('payload orientation changed')
        world = C.link_boxes_world(q, rail, self.boxes, self.tcp, self.carrying, self.scene.base_origin)
        obstacles = V.obstacles_at(self.scene, rail)
        part_names = {p.name for p in self.scene.rail_parts}
        for link, name, center, axes, half in world:
            required = self.limits.payload_clearance if link == 'canister' else self.limits.clearance
            for obstacle in obstacles:
                if link == 'base_link' and obstacle.name in part_names:
                    continue  # mechanical mounting, not an arbitrary environment exemption
                gap = separating_gap((center, axes, half),
                                     (obstacle.center, AXES, K.scale(obstacle.size, .5)), required)
                # A resting module initially touches its support board. Only a top-face
                # contact is allowed while lifting, never side/back/ceiling penetration.
                bottom = center[2] - sum(h * abs(a[2]) for h, a in zip(half, axes, strict=True))
                top = obstacle.center[2] + obstacle.size[2] / 2
                if (link == 'canister' and support_contact and 'ShelfBoard' in obstacle.name
                        and bottom >= top - 0.00005):
                    continue
                if gap + 1e-9 < required:
                    raise K.PlanError(f'{self.phase}: {link}:{name} / {obstacle.name} gap {gap:.4f} m')
                self.clearance = min(self.clearance, gap)
        payload = next((o for o in world if o[0] == 'canister'), None)
        if payload:
            # The two jaw contact surfaces may touch the payload. Other tool solids may not.
            contacts = {'rg2_right_inner_finger', 'rg2_left_inner_finger'}
            for link, name, center, axes, half in world:
                if link == 'canister' or name in contacts:
                    continue
                gap = separating_gap(payload[2:], (center, axes, half), self.limits.payload_clearance)
                if gap < self.limits.payload_clearance:
                    raise K.PlanError(f'{self.phase}: payload / {link}:{name}')

    def arm(self, phase, path, linear=False, support_contact=False):
        self.phase = phase

        def checked_chord(a, b):
            previous = a
            for q in [a, *S.interpolate(a, b, self.limits.joint_sample)]:
                K.check_joint_segment(previous, q)
                self.check(q, self.rail, support_contact)
                previous = q

        def retimed_chord(a, b):
            checked_chord(a, b)
            if linear:
                _check_linear_chord(self.model, a, b, self.model.fk(path[0]),
                                    self.model.fk(path[-1]).position_m, self.limits)

        for a, b in zip(path, path[1:], strict=False):
            checked_chord(a, b)
        points = retime(path, self.limits.joint_speed, self.limits.joint_accel, self.limits.period,
                        self.model, self.limits.micro_speed if linear or self.carrying else .8, retimed_chord)
        self.segments.append(Segment(phase, 'arm', points, self.carrying, (len(points) - 1) * self.limits.period))
        self.q = points[-1]

    def lin(self, phase, point, support_contact=False):
        try:
            self.arm(phase, linear_path(self.model, self.q, V.to_base(point, self.rail, self.scene), self.limits),
                     True, support_contact)
        except K.PlanError as error:
            raise K.PlanError(f'{phase}: {error}') from error

    def rails(self, phase, target):
        self.phase = phase
        if any(not lo <= value <= hi for value, (lo, hi) in zip(target, self.scene.rail_limits, strict=True)):
            raise K.PlanError('rail detour outside limits')
        for step in V.rail_moves(phase, self.rail, target, tolerance=0.):
            self.phase = step.phase
            for rail in [self.rail, *S.interpolate(self.rail, step.rail, self.limits.rail_sample)]:
                self.check(self.q, rail)
            points = retime((self.rail, step.rail), self.limits.rail_speed,
                            self.limits.rail_accel, self.limits.period)
            self.segments.append(Segment(step.phase, 'rail', points, self.carrying,
                                          (len(points) - 1) * self.limits.period))
            self.rail = step.rail

    def grip(self, close):
        self.segments.append(Segment('grasp' if close else 'release', 'close' if close else 'open',
                                      (), self.carrying, 0.))
        self.carrying = close


def finish_return(builder, home, home_rail, params):
    """Search empty-arm yaw locations along the front return corridor.

    Neither the slot nor rail-home X is automatically a safe place to yaw:
    dispenser walls and shelf sides can intersect the folded arm's swept volume.
    Every intermediate location, incoming sweep and outgoing sweep is checked.
    """
    start_x, end_x = builder.rail[0], home_rail[0]
    count = max(1, math.ceil(abs(end_x - start_x) / params.min_reach))
    clear_y = builder.scene.rail_limits[1][0] + params.rail_limit_margin
    best, reasons = None, []
    for i in range(count + 1):
        x = start_x + (end_x - start_x) * i / count
        candidate = copy.copy(builder)
        candidate.segments = list(builder.segments)
        try:
            candidate.rails('rail_return_clear', (x, clear_y, builder.rail[2]))
            candidate.arm('unloaded_tuck', (candidate.q, tuple(home)))
            candidate.rails('rail_home', tuple(home_rail))
        except K.PlanError as error:
            reasons.append(str(error))
            continue
        score = (sum(s.seconds for s in candidate.segments), -candidate.clearance)
        if best is None or score < best[0]:
            best = score, candidate
    if best is None:
        raise K.PlanError('no checked return yaw location: ' + '; '.join(dict.fromkeys(reasons)))
    return best[1]


def plan_module(model, scene, cell, boxes, tcp, seeds, params, home, home_rail=(0., 0., 0.), limits=None):
    """Choose minimum estimated motion time over the bounded, feasible candidate set.

    All candidates include outbound/loaded/return rail sweeps. Carry is the fully
    extracted pose, never unloaded tuck. No fallback to an unchecked legacy plan.
    """
    limits = Limits() if limits is None else limits
    target = _check_scene(scene, cell, params, limits)
    if (tuple(tcp) != model.flange_to_tcp.position_m
            or math.hypot(*K.rotation_error(model.flange_to_tcp.orientation_xyzw, (0., 0., 0., 1.))) > 1e-9):
        raise K.PlanError('kinematics and collision TCP transforms differ')
    K.finite(home_rail, 3)
    if any(not lo <= v <= hi for v, (lo, hi) in zip(home_rail, scene.rail_limits, strict=True)):
        raise K.PlanError('home rail outside limits')
    links = {b.link for b in boxes}
    if not set(C.LINKS) <= links or not any(b.name == 'rg2_gripper_body' for b in boxes):
        raise K.PlanError('robot and gripper collision geometry required')
    for box in boxes:
        if any(hi <= lo for lo, hi in zip(K.finite(box.low, 3), K.finite(box.high, 3), strict=True)):
            raise K.PlanError('invalid robot collision geometry')
    # A long payload needs more extraction than a fixed 100 mm. The full sweep
    # must still pass collision checks with the actual shelf geometry.
    shelf_fronts = [o.center[1] - o.size[1] / 2 for o in scene.obstacles
                    if 'Shelf' in o.name and abs(o.center[0] - cell.center[0]) <= o.size[0] / 2]
    if not shelf_fronts:
        raise K.PlanError('cannot establish shelf front for complete extraction')
    extraction = cell.center[1] + cell.size[1] / 2 - min(shelf_fronts) + params.hover
    params = params._replace(approach=max(params.approach, extraction))
    pick, grip = V.pick_points(cell, params)
    place, _ = V.place_points(cell, target, grip, params)
    # Withdraw along exactly the reverse insertion axis, out to pre-place.
    retreat = place[0][1]
    geometry = tuple(b for b in boxes if b.link != 'canister') + (payload_box(cell, grip),)
    # Keep reach after extraction too: merely optimizing reach at the grasp point
    # can pull the payload directly into the upper arm during the reverse LIN.
    offsets = []
    for back, side, dz in params.rail_pick:
        front_back = math.sqrt(max(0., params.min_reach**2 - side**2 - (dz - V.SHOULDER_HEIGHT)**2))
        offsets.append((max(back, params.approach + front_back), side, dz))
    pick_options = V.rail_candidates(grip, 0., scene, params, offsets)[:params.max_rail_tries]
    # During macro transfer the leading payload face must stay in front of the
    # dispenser until the arm aligns to the slot. Its TCP reach is fixed at carry.
    carry_forward = max((back - params.approach for back, _, _ in offsets), default=0.)
    place_back = (carry_forward + cell.size[1] / 2 + params.module_push + limits.clearance + .001)
    place_offsets = [(max(back, place_back), lateral, height)
                     for back, side, dz in params.rail_module
                     for lateral in (side, side + math.copysign(params.hover, side))
                     for height in (dz, dz - params.hover, dz + params.hover)]
    place_options = V.rail_candidates(place[-1][1], 0., scene, params, place_offsets)[:params.max_rail_tries]
    best, evaluated, feasible, errors = None, 0, 0, []
    seen = []
    for _, pick_rail in pick_options:
        for seed in seeds:
            try:
                front = model.inverse(K.Pose(V.to_base(pick[0][1], pick_rail, scene), V.FRONT), seed)
            except K.PlanError:
                continue
            if any(rail == pick_rail and max(abs(a - b) for a, b in zip(q, front, strict=True)) < .001
                   for rail, q in seen):
                continue
            seen.append((pick_rail, front))
            prefix = _Builder(model, scene, geometry, tcp, limits, home, home_rail)
            try:
                prefix.grip(False)
                prefix.rails('rail_to_shelf', pick_rail)
                prefix.arm('pre_pick', (tuple(home), front))
                prefix.lin('approach', pick[1][1])
                prefix.grip(True)
                prefix.lin('lift', pick[2][1], support_contact=True)
                prefix.lin('extract', pick[3][1])
                base_z = C.base_position(pick_rail, scene.base_origin)[2]
                carry_z = max(pick[3][1][2], base_z + params.min_reach + params.approach)
                prefix.lin('payload_carry', (*pick[3][1][:2], carry_z))
            except K.PlanError as error:
                evaluated += 2 * len(place_options)
                errors.append(str(error))
                continue
            for (_, place_rail), corridor in product(place_options, (False, True)):
                evaluated += 1
                b = copy.copy(prefix)
                b.segments = list(prefix.segments)
                try:
                    if corridor:
                        # The native rail's frontmost interior Y forms one explicit
                        # detour candidate around the round bin. Check every sweep.
                        clear_y = scene.rail_limits[1][0] + params.rail_limit_margin
                        b.rails('rail_clear', (b.rail[0], clear_y, b.rail[2]))
                        travel_z = max(b.rail[2], place_rail[2]) + params.hover
                        if travel_z > scene.rail_limits[2][1] - params.rail_limit_margin:
                            raise K.PlanError('raised transfer exceeds rail margin')
                        b.rails('rail_raise', (b.rail[0], clear_y, travel_z))
                        b.rails('rail_to_slot', (place_rail[0], clear_y, place_rail[2]))
                    b.rails('rail_align', place_rail)
                    b.lin('pre_place', place[0][1])
                    b.lin('insert', place[1][1])
                    b.grip(False)
                    b.lin('retract', retreat)
                    # Retracted TCP alone does not make a simultaneous yaw/fold
                    # safe beside the dispenser. Fold with J1 fixed, raise the
                    # empty folded arm to the checked travel height, then yaw.
                    b.arm('unloaded_fold', (b.q, (b.q[0], *tuple(home)[1:])))
                    return_z = max(pick_rail[2], place_rail[2]) + params.hover
                    if return_z > scene.rail_limits[2][1] - params.rail_limit_margin:
                        raise K.PlanError('return height exceeds rail margin')
                    b.rails('rail_return_raise', (*b.rail[:2], return_z))
                    b = finish_return(b, home, home_rail, params)
                except K.PlanError as error:
                    errors.append(str(error))
                    continue
                feasible += 1
                score = (sum(s.seconds for s in b.segments), -b.clearance)
                if best is None or score < best[0]:
                    best = score, b
    if best is None:
        reasons = '; '.join(dict.fromkeys(errors))[:1200]
        raise K.PlanError(f'no feasible module path ({evaluated} candidates): {reasons or "IK/rail bounds"}')
    score, b = best
    return Plan(tuple(b.segments), score[0], b.clearance, evaluated, feasible, signature(scene), cell.cell_id)


def signature(scene):
    """Include geometry of stock cells; ignore presence changes caused by this pick."""
    return repr((V.scene_signature(scene), tuple(sorted((c.cell_id, c.kind, c.center, c.size, c.access)
                                                       for c in scene.cells))))


def main(argv=None):
    """Offline preview only. No ROS, command publisher, or controller connection."""
    import argparse
    import json
    from pathlib import Path

    import yaml

    from rokey_p3_manipulation.pick_plan import default_seeds

    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument('inventory', type=Path)
    parser.add_argument('collision', type=Path)
    parser.add_argument('teach', type=Path)
    parser.add_argument('--cell', required=True)
    parser.add_argument('--seeds', type=int, default=12)
    args = parser.parse_args(argv)
    try:
        scene = V.parse_inventory(args.inventory.read_text())
        tcp, boxes = C.load_collision(yaml.safe_load(args.collision.read_text()))
        home = S.load_rail_teach(yaml.safe_load(args.teach.read_text())).home_joints
        cell = next((c for c in scene.cells if c.cell_id == args.cell), None)
        if cell is None or args.seeds < 1:
            raise K.PlanError('known cell and positive seed count required')
        plan = plan_module(K.M0609(K.ToolTransform(tcp, (0., 0., 0., 1.))), scene, cell, boxes, tcp,
                           default_seeds(home, args.seeds, seed=1), V.DEFAULT_PARAMS, home)
    except (K.PlanError, V.SceneError, S.RefillPlanError, KeyError, TypeError, ValueError) as error:
        print(json.dumps({'status': 'refused', 'reason': str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps({'status': 'candidate', 'cell': plan.cell_id, 'motion_seconds': plan.seconds,
                      'clearance_lower_bound_m': plan.clearance, 'evaluated': plan.evaluated,
                      'feasible': plan.feasible,
                      'segments': [{'phase': s.phase, 'actor': s.actor, 'seconds': s.seconds,
                                    'carrying': s.carrying, 'samples': len(s.points)} for s in plan.segments]},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
