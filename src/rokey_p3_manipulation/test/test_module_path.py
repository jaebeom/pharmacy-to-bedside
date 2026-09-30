"""Guarded module planning: geometry, full rail sweep, LIN and time bounds (no ROS)."""

import math
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from rokey_p3_manipulation import clearance as C
from rokey_p3_manipulation import m0609_kinematics as K
from rokey_p3_manipulation import module_path as M
from rokey_p3_manipulation import pick_plan as P
from rokey_p3_manipulation import scene_v2 as V

ROOT = Path(__file__).parents[1]
HOME = (0., 0., 1.5883, 0., 1.5778, 0.)


@pytest.fixture
def geometry():
    scene = V.parse_inventory((ROOT / 'test/data/pharmacy_v2.json').read_text())
    tcp, boxes = C.load_collision(yaml.safe_load((ROOT / 'config/m0609_collision.yaml').read_text()))
    model = K.M0609(K.ToolTransform(tcp, (0., 0., 0., 1.)))
    cell = next(c for c in scene.cells if c.cell_id == 'upper_right/r0c0')
    return scene, tcp, boxes, model, cell


@pytest.mark.parametrize('field,value', [('period', 0.), ('period', math.nan), ('micro_speed', .051),
                                        ('payload_clearance', 0.), ('rail_speed', (1., math.inf, 1.))])
def test_invalid_limits_are_refused(field, value):
    with pytest.raises(K.PlanError):
        replace(M.Limits(), **{field: value})


def test_projection_gap_does_not_accept_overlapping_rotated_boxes():
    axes = tuple(K.rotate(K.axis_angle((0., 0., 1.), math.pi / 4), a) for a in M.AXES)
    a = ((0., 0., 0.), M.AXES, (1., 1., 1.))
    assert M.separating_gap(a, ((1.5, 0., 0.), axes, (1., 1., 1.))) == 0.
    gap = M.separating_gap(a, ((3., 0., 0.), axes, (1., 1., 1.)))
    assert gap == pytest.approx(2 - math.sqrt(2))


def test_payload_is_attached_at_actual_front_grasp_offset(geometry):
    _, _, _, _, cell = geometry
    _, grip = V.pick_points(cell, V.DEFAULT_PARAMS)
    box = M.payload_box(cell, grip)
    center = K.scale(K.add(box.low, box.high), .5)
    assert K.add(grip, K.rotate(V.FRONT, center)) == pytest.approx(cell.center)
    assert K.sub(box.high, box.low) == pytest.approx((cell.size[0], cell.size[2], cell.size[1]))


def test_lin_keeps_tcp_orientation_while_wrist_joints_change(geometry):
    _, _, _, model, _ = geometry
    start = model.inverse(K.Pose((.15, .45, .4), V.FRONT), HOME)
    path = M.linear_path(model, start, (.15, .50, .4), M.Limits())
    assert len(path) > 10
    for q in path:
        p = model.fk(q)
        assert p.position_m[0] == pytest.approx(.15, abs=3e-5)
        assert p.position_m[2] == pytest.approx(.4, abs=3e-5)
        assert math.hypot(*K.rotation_error(V.FRONT, p.orientation_xyzw)) < .0001
    assert max(abs(b - a) for a, b in zip(path[0][3:], path[-1][3:], strict=True)) > .01


def test_retiming_limits_velocity_and_acceleration_including_stops():
    speed, accel, period = (.2, .3), (.4, .5), .02
    points = M.retime(((0., 0.), (.5, .05), (.55, .4)), speed, accel, period)
    velocities = [K.scale(K.sub(b, a), 1 / period) for a, b in zip(points, points[1:], strict=False)]
    padded = [(0., 0.), *velocities, (0., 0.)]
    for v in velocities:
        assert all(abs(x) <= limit + 1e-9 for x, limit in zip(v, speed, strict=True))
    for a, b in zip(padded, padded[1:], strict=False):
        assert all(abs(y - x) / period <= limit + 1e-9 for x, y, limit in zip(a, b, accel, strict=True))
    assert points[0] == (0., 0.) and points[-1] == (.55, .4)


@pytest.mark.parametrize('change', ['axis', 'depth', 'empty_geometry', 'nan', 'other_rail'])
def test_unsupported_or_incomplete_geometry_is_rejected(geometry, change):
    scene, tcp, boxes, model, cell = geometry
    target = scene.targets['module']
    if change == 'axis':
        scene = scene._replace(targets={'module': target._replace(axis=(1., 0., 0.))})
    elif change == 'depth':
        scene = scene._replace(targets={'module': target._replace(data=dict(target.data, depth=.001))})
    elif change == 'empty_geometry':
        boxes = ()
    elif change == 'nan':
        cell = cell._replace(center=(0., math.nan, 1.))
    else:
        scene = scene._replace(rail_names=('rail_x', 'rail_z', 'rail_y'))
    with pytest.raises(K.PlanError):
        M.plan_module(model, scene, cell, boxes, tcp, [HOME], V.DEFAULT_PARAMS, HOME)


def test_loaded_rail_midpoint_collision_is_rejected_even_with_clear_endpoints(geometry):
    scene, tcp, _, model, cell = geometry
    q = model.inverse(K.Pose((.15, .45, .4), V.FRONT), HOME)
    _, grip = V.pick_points(cell, V.DEFAULT_PARAMS)
    payload = M.payload_box(cell, grip)
    center = K.add(model.fk(q).position_m, K.rotate(V.FRONT, K.scale(K.add(payload.low, payload.high), .5)))
    scene = scene._replace(base_origin=(0., 0., 0.), rail_parts=(),
                           obstacles=(C.Box('midway', K.add(center, (.5, 0., 0.)), (.04, .04, .04)),))
    builder = M._Builder(model, scene, (payload,), tcp, M.Limits(), q, (0., 0., 0.))
    builder.carrying = True
    builder.check(q, (0., 0., 0.))
    builder.check(q, (1., 0., 0.))
    with pytest.raises(K.PlanError, match='midway'):
        builder.rails('transfer', (1., 0., 0.))


def test_payload_self_collision_is_not_hidden_by_environment_clearance(geometry, monkeypatch):
    scene, tcp, boxes, model, _ = geometry
    q = model.inverse(K.Pose((.15, .45, .4), V.FRONT), HOME)
    scene = scene._replace(obstacles=(), rail_parts=())
    monkeypatch.setattr(C, 'link_boxes_world', lambda *a: [
        ('canister', 'payload', (0., 0., 0.), M.AXES, (.1, .1, .1)),
        ('link_2', 'arm', (0., 0., 0.), M.AXES, (.1, .1, .1))])
    builder = M._Builder(model, scene, boxes, tcp, M.Limits(), q, (0., 0., 0.))
    builder.carrying = True
    with pytest.raises(K.PlanError, match='payload / link_2'):
        builder.check(q, (0., 0., 0.))


def test_fixture_plan_never_tucks_a_loaded_module_and_reverses_insertion(geometry):
    scene, tcp, boxes, model, cell = geometry
    # A deterministic alternative IK branch; HOME alone cannot complete this
    # scene's loaded transfer. The production search includes this seed.
    seed = P.default_seeds(HOME, 12, seed=1)[10]
    # Restrict the search, not the geometry, to one of the production candidates.
    # Whole-route candidate ranking is tested independently below.
    params = V.DEFAULT_PARAMS._replace(rail_pick=((.50, .15, .30),),
                                       rail_module=((.35, .19, .34),), max_rail_tries=1)
    plan = M.plan_module(model, scene, cell, boxes, tcp, [seed], params, HOME)
    assert plan.feasible > 0 and plan.evaluated >= plan.feasible
    assert plan.seconds == pytest.approx(sum(s.seconds for s in plan.segments))
    carrying = False
    by_name = {s.phase: s for s in plan.segments}
    for segment in plan.segments:
        if segment.actor == 'close':
            carrying = True
        elif segment.actor == 'open':
            carrying = False
        elif carrying and segment.actor == 'arm':
            assert segment.phase != 'unloaded_tuck'
            for q in segment.points[::10]:
                assert math.hypot(*K.rotation_error(V.FRONT, model.fk(q).orientation_xyzw)) < .005
            assert M.S.peak_speed(segment.points, .02, lambda q: model.fk(q).position_m) <= .05 + 1e-9
    insert, retract = by_name['insert'], by_name['retract']
    assert model.fk(insert.points[0]).position_m == pytest.approx(model.fk(retract.points[-1]).position_m, abs=5e-5)
    assert model.fk(insert.points[-1]).position_m == pytest.approx(model.fk(retract.points[0]).position_m, abs=5e-5)
    assert by_name['unloaded_tuck'].points[-1] == HOME
    assert not by_name['unloaded_fold'].carrying


def test_optimizer_considers_whole_route_instead_of_first_reachable_pick(geometry, monkeypatch):
    """Synthetic collision-free backend: the first pick needs a longer round trip."""
    scene, tcp, boxes, model, cell = geometry
    pick_a, pick_b, slot = (-.2, 0., .3), (.8, 0., .3), (1., 0., .3)
    options = iter([[(.1, pick_a), (.2, pick_b)], [(.1, slot)]])
    monkeypatch.setattr(V, 'rail_candidates', lambda *a: next(options))
    monkeypatch.setattr(K.M0609, 'inverse', lambda *a: HOME)

    class FreeSpace:
        def __init__(self, model, scene, geometry, tcp, limits, home, home_rail):
            self.q, self.rail, self.segments, self.carrying, self.clearance = home, home_rail, [], False, .1
            self.scene = scene

        def rails(self, phase, target):
            self.segments.append(M.Segment(phase, 'rail', (self.rail, target), self.carrying,
                                            math.dist(self.rail, target)))
            self.rail = target

        def arm(self, phase, path):
            self.q = path[-1]

        def lin(self, *args, **kwargs):
            pass

        def grip(self, close):
            self.carrying = close

    monkeypatch.setattr(M, '_Builder', FreeSpace)
    plan = M.plan_module(model, scene, cell, boxes, tcp, [HOME], V.DEFAULT_PARAMS, HOME)
    assert plan.feasible == plan.evaluated == 4
    assert plan.segments[0].points[-1] == pick_b
    assert plan.seconds == pytest.approx(sum(s.seconds for s in plan.segments))


def test_geometry_change_invalidates_execution_signature_but_pick_presence_does_not(geometry):
    scene, _, _, _, _ = geometry
    first = scene.cells[0]
    assert M.signature(scene) == M.signature(scene._replace(cells=(first._replace(present=False), *scene.cells[1:])))
    assert M.signature(scene) != M.signature(scene._replace(cells=(first._replace(center=(9., 9., 9.)),
                                                                   *scene.cells[1:])))


def test_retimed_chord_cannot_cut_across_a_checked_corner(geometry, monkeypatch):
    """A synthetic XY tool can follow the L, but a coarse timed chord hits its inside corner."""
    scene, tcp, boxes, model, _ = geometry
    monkeypatch.setattr(K.M0609, 'fk', lambda self, q: K.Pose((q[0], q[1], 0.), V.FRONT))
    monkeypatch.setattr(C, 'link_boxes_world', lambda q, *args: [
        ('link_2', 'tool', (q[0], q[1], 0.), M.AXES, (.001,) * 3)])
    scene = scene._replace(rail_parts=(), obstacles=(C.Box('inside_corner', (.05, .115, 0.), (.01,) * 3),))
    home = (0., 0., 0., 0., 1., 0.)
    path = (home, (.1, 0., 0., 0., 1., 0.), (.1, .23, 0., 0., 1., 0.))
    builder = M._Builder(model, scene, boxes, tcp, M.Limits(period=1.), home, (0.,) * 3)
    for a, b in zip(path, path[1:], strict=False):
        for point in (a, *M.S.interpolate(a, b, builder.limits.joint_sample)):
            builder.check(point, builder.rail)
    with pytest.raises(K.PlanError, match='inside_corner'):
        builder.arm('corner', path)


def test_retimed_lin_chord_is_rechecked_in_cartesian_space(geometry, monkeypatch):
    """A curved joint-space LIN stays within 0.5 mm until its middle sample is removed."""
    scene, tcp, _, model, _ = geometry
    monkeypatch.setattr(K.M0609, 'fk', lambda self, q: K.Pose((q[0], q[1] + q[0]**2, 0.), V.FRONT))
    scene = scene._replace(obstacles=(), rail_parts=())
    home = (0., 0., 0., 0., 1., 0.)
    path = (home, (.025, -.000625, 0., 0., 1., 0.), (.05, -.0025, 0., 0., 1., 0.))
    builder = M._Builder(model, scene, (), tcp, M.Limits(period=4., joint_sample=.002), home, (0.,) * 3)
    for a, b in zip(path, path[1:], strict=False):
        for q in (a, *M.S.interpolate(a, b, builder.limits.joint_sample)):
            assert abs(model.fk(q).position_m[1]) < .0005
    with pytest.raises(K.PlanError, match='Cartesian line'):
        builder.arm('lin', path, linear=True)
