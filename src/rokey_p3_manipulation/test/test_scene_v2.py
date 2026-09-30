"""L1. 레일 보충 v2(scene_version 2): 칸 랜덤, IK 해 고르기, 여유 부족 칸 건너뛰기, 레일 z 안전 순서, 연속 구동기.

장면은 `test/data/pharmacy_v2.json` 이다. Simu `feat/sim-v2-round-bin-012` 3f20086
(받침 0.55, 원형 수납통 안지름 0.12)에서 `python3 sim/standalone/pharmacy_layout_json.py --scene v2` 로 뽑았다
(치수 임시).
"""
import json
import math
import os
import threading
import types

import pytest
import test_reset_fence as rf
import yaml

from rokey_p3_manipulation import clearance as C
from rokey_p3_manipulation import m0609_kinematics as kin
from rokey_p3_manipulation import pick_plan as P
from rokey_p3_manipulation import refill_sequence as seq
from rokey_p3_manipulation import soak_report as soak
from rokey_p3_manipulation import scene_v2 as V

nodes = rf.nodes
HERE = os.path.dirname(__file__)
HOME = (0.0, 0.0, 1.5883, 0.0, 1.5778, 0.0)


def scene():
    with open(os.path.join(HERE, 'data', 'pharmacy_v2.json'), encoding='utf-8') as handle:
        return V.parse_inventory(handle.read())


def collision():
    with open(os.path.join(HERE, '..', 'config', 'm0609_collision.yaml'), encoding='utf-8') as handle:
        return C.load_collision(yaml.safe_load(handle))


# ---- 칸 랜덤 --------------------------------------------------------------------------------------

def test_same_seed_same_order_and_only_matching_kind():
    cells = scene().cells
    first = P.CellPicker(7)
    second = P.CellPicker(7)
    a = [first.choose(cells, 'cylinder', 'drug-amox')[0].cell_id for _ in range(10)]
    b = [second.choose(cells, 'cylinder', 'drug-amox')[0].cell_id for _ in range(10)]
    assert a == b
    assert all(cid.startswith('floor_') for cid in a)
    assert first.history[0].seed == 7 and first.history[-1].draw == 10 and first.history[0].candidates == 8
    third = P.CellPicker(8)
    assert [third.choose(cells, 'cylinder')[0].cell_id for _ in range(10)] != a    # 다른 시드는 다른 순서


def test_exclusions_and_empty_choice_are_recorded():
    cells = scene().cells
    picker = P.CellPicker(1)
    modules = [c.cell_id for c in cells if c.kind == 'module']
    cell, choice = picker.choose(cells, 'module', exclude=modules[:-1])
    assert cell.cell_id == modules[-1] and choice.candidates == 1
    cell, choice = picker.choose(cells, 'module', exclude=modules)
    assert cell is None and choice.cell_id is None and choice.candidates == 0 and choice.draw == 2


def test_absent_cells_are_not_chosen():
    gone = [c._replace(present=False) if c.kind == 'cylinder' else c for c in scene().cells]
    cell, choice = P.CellPicker(0).choose(gone, 'cylinder')
    assert cell is None and choice.candidates == 0
    assert P.CellPicker(0).choose(gone, 'module')[0].kind == 'module'


# ---- IK 해 고르기 -----------------------------------------------------------------------------------

def model():
    return kin.M0609(kin.ToolTransform((0.0, 0.0, 0.19671), (0.0, 0.0, 0.0, 1.0)))


def test_select_takes_the_largest_clearance_and_refuses_below_the_minimum():
    m = model()
    goal = m.fk(HOME)
    targets = [P.Target('t', (0.0, 0.0, 0.0), goal)]
    seeds = [HOME, tuple(q + 0.05 for q in HOME), tuple(q - 0.05 for q in HOME)]
    scores = iter([0.02, 0.05, 0.03])
    sel = P.select(m, targets, seeds, lambda path, floor: (next(scores), 'x'), 0.01)
    # 세 시드가 같은 해로 모이면 한 번만 잰다. 그래도 고른 해의 여유는 잰 값 중 최대다.
    assert sel.candidate is not None and sel.candidate.clearance == 0.02
    sel = P.select(m, targets, seeds, lambda path, floor: (0.004, 'link_6-Board'), 0.01)
    assert sel.candidate is None and '0.004' in sel.reason and 'link_6-Board' in sel.reason


def test_select_reports_ik_failure():
    far = kin.Pose((3.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0))
    sel = P.select(model(), [P.Target('t', (0.0, 0.0, 0.0), far)], [HOME], lambda path, floor: (1.0, ''), 0.0)
    assert sel.candidate is None and sel.rejected == [(0, 'ik')]


# ---- 장면·계획 ---------------------------------------------------------------------------------------

def test_inventory_parses_rail_items_and_targets():
    s = scene()
    assert len(s.cells) == 16 and {c.kind for c in s.cells} == {'cylinder', 'module'}
    assert s.items == {'drug-amox': 'cylinder', 'drug-ibu': 'module'}
    assert s.rail_names == ('rail_x', 'rail_y', 'rail_z') and s.base_origin == (0.0, 0.3, 0.25)
    assert s.rail_limits == ((-1.4, 1.4), (-0.1, 0.33), (0.0, 1.1))
    assert set(s.targets) == {'cylinder', 'module'} and len(s.obstacles) == 47
    parts = {p.name: p.moves for p in s.rail_parts}
    assert parts == {'Track': (), 'YBeam': ('x',), 'TruckLeft': ('x',), 'TruckRight': ('x',),
                     'Pedestal': ('x', 'y'), 'YCarriage': ('x', 'y'), 'LiftPlate': ('x', 'y', 'z'),
                     'LiftColumn': ('x', 'y', 'z')}
    with pytest.raises(V.SceneError, match='v2'):
        V.parse_inventory('{"scene": "v1"}')
    with pytest.raises(V.SceneError, match='JSON'):
        V.parse_inventory('not json')


def test_rail_targets_near_the_limits_are_dropped_not_clamped():
    s = scene()
    assert V.rail_for((5.0, -3.0, 9.0), (0.0, 0.0, 0.0), 0.0, s, 0.05) is None          # 한계 밖: 자르지 않고 뺀다
    x_hi = s.rail_limits[0][1]
    near = (x_hi - 0.04 + s.base_origin[0], 0.5, s.base_origin[2] + 0.2)               # x 한계 4 cm 안
    assert V.rail_for(near, (0.5, 0.0, 0.0), 0.0, s, 0.05) is None
    rail = V.rail_for((0.0, 0.8, 1.0), (0.5, 0.0, 0.0), 0.0, s, 0.05)
    assert rail is not None and V.rail_margin(rail, s) >= 0.05 - 1e-9


def test_rail_moves_go_up_first_and_down_last():
    up = V.rail_moves('r', (0.0, 0.0, 0.0), (0.5, 0.1, 0.3))
    assert [(x.phase, x.rail) for x in up] == [('r_z', (0.0, 0.0, 0.3)), ('r_xy', (0.5, 0.1, 0.3))]
    down = V.rail_moves('r', (0.5, 0.1, 0.3), (0.0, 0.0, 0.0))
    assert [(x.phase, x.rail) for x in down] == [('r_xy', (0.0, 0.0, 0.3)), ('r_z', (0.0, 0.0, 0.0))]
    flat = V.rail_moves('r', (0.0, 0.0, 0.2), (0.4, 0.0, 0.2))
    assert [x.phase for x in flat] == ['r_xy']
    assert [x.rail for x in V.rail_moves('r', (0.0, 0.0), (0.3, 0.1))] == [(0.3, 0.1)]      # 2축은 한 번에


def test_rail_parts_move_with_their_axes():
    s = scene()._replace(rail_parts=(V.RailPart('Track', (0.0, 0.3, 0.025), (2.8, 0.1, 0.05), ()),
                                     V.RailPart('Pedestal', (0.0, 0.3, 0.3), (0.22, 0.22, 0.5), ('x', 'y')),
                                     V.RailPart('LiftPlate', (0.0, 0.3, 0.58), (0.28, 0.28, 0.04), ('x', 'y', 'z'))))
    boxes = {b.name: b.center for b in V.obstacles_at(s, (0.5, 0.1, 0.2))}
    assert boxes['Track'] == (0.0, 0.3, 0.025)
    assert boxes['Pedestal'] == pytest.approx((0.5, 0.4, 0.3))
    assert boxes['LiftPlate'] == pytest.approx((0.5, 0.4, 0.78))
    assert len(V.obstacles_at(s, (0.0, 0.0, 0.0))) == len(s.obstacles) + 3
    assert V.scene_signature(s) != V.scene_signature(scene())                              # 부품이 바뀌면 캐시도
    column = s._replace(rail_parts=(V.RailPart('LiftColumn', (0.0, 0.3, -0.35), (0.16, 0.16, 1.12), ('x', 'y', 'z')),))
    low = {b.name: b for b in V.obstacles_at(column, (0.0, 0.0, 0.0))}['LiftColumn']
    assert low.center[2] - low.size[2] / 2 == pytest.approx(0.0)
    assert low.center[2] + low.size[2] / 2 == pytest.approx(0.21)
    high = {b.name: b for b in V.obstacles_at(column, (0.0, 0.0, 1.0))}['LiftColumn']
    assert high.center[2] + high.size[2] / 2 == pytest.approx(1.21)                         # 판 아랫면을 따라 오른다
    assert 'LiftColumn' not in {b.name for b in V.obstacles_at(column._replace(
        rail_parts=(V.RailPart('LiftColumn', (0.0, 0.3, -1.0), (0.16, 0.16, 0.5), ('z',)),)), (0.0, 0.0, 0.0))}


def test_a_link_through_its_own_pedestal_blocks_the_plan():
    """재범 관찰(실습7-a): 팔이 레일·받침을 관통. 받침 부품을 두면 그 자리를 지나는 계획은 여유가 0 이 된다."""
    s = scene()
    tcp, boxes = collision()
    cell = next(c for c in s.cells if c.cell_id == 'floor_right/r1c0')
    steps, _, free = V.plan_refill(model(), s, cell, boxes, tcp, P.default_seeds(HOME, 12, seed=1),
                                   V.DEFAULT_PARAMS, HOME)
    assert steps is not None and free >= V.DEFAULT_PARAMS.min_clearance
    # 베이스 바로 아래·앞을 채우는 큰 받침(가상의 틀린 부품)이면 어떤 해도 닿는다.
    wall = V.RailPart('Pedestal', (0.0, 0.3, 0.6), (3.0, 1.2, 1.2), ('x', 'y', 'z'))
    blocked = s._replace(rail_parts=(wall,))
    steps, why, value = V.plan_refill(model(), blocked, cell, boxes, tcp, P.default_seeds(HOME, 12, seed=1),
                                      V.DEFAULT_PARAMS, HOME)
    assert steps is None and value is None and '여유' in why


def test_plan_moves_the_rail_only_from_the_folded_pose_and_is_valid():
    s = scene()
    tcp, boxes = collision()
    cell = next(c for c in s.cells if c.cell_id == 'floor_right/r1c0')
    steps, why, clearance = V.plan_refill(model(), s, cell, boxes, tcp, P.default_seeds(HOME, 8, seed=1),
                               V.DEFAULT_PARAMS._replace(min_clearance=-1.0), HOME)
    assert steps is not None, why
    checked = seq.validate_plan(steps, HOME, ('fold', 'fold_back'), 3)
    arm = 'home'
    for step in checked:
        if step.rail is not None:
            assert arm in ('home', 'fold', 'fold_back') and len(step.rail) == 3
        elif step.joints is not None:
            arm = step.phase
    assert [s.gripper for s in checked if s.gripper] == [seq.GRIP_CLOSE, seq.GRIP_OPEN]
    assert checked[-1].phase == 'fold_back' and checked[-1].joints == HOME
    # 레일은 단계로 나뉜다: 오를 땐 z 만 먼저, 그다음 x·y. 한 단계에서 z 와 x·y 가 같이 바뀌지 않는다.
    rails = [(s.phase, s.rail) for s in checked if s.rail is not None]
    previous = (0.0, 0.0, 0.0)
    for phase, rail in rails:
        z_moved = abs(rail[2] - previous[2]) > 1e-9
        xy_moved = max(abs(rail[0] - previous[0]), abs(rail[1] - previous[1])) > 1e-9
        assert not (z_moved and xy_moved), (phase, previous, rail)
        assert phase.endswith('_z') == z_moved
        previous = rail
    # 잡기 레일 자세에서 베이스가 약통보다 낮다(재범 9/18: 베이스를 약통 근처·아래로).
    grip_rail = next(r for p, r in rails if p == 'rail_to_shelf_xy')
    assert C.base_position(grip_rail, s.base_origin)[2] < cell.center[2]


def test_a_plan_below_the_clearance_minimum_is_skipped_with_the_reason():
    s = scene()
    tcp, boxes = collision()
    cell = next(c for c in s.cells if c.cell_id == 'floor_right/r1c0')
    steps, why, clearance = V.plan_refill(model(), s, cell, boxes, tcp, [HOME],
                                          V.DEFAULT_PARAMS._replace(min_clearance=5.0), HOME)
    assert steps is None and clearance is None and cell.cell_id in why


def test_validate_plan_refuses_a_rail_move_with_the_arm_out():
    steps = [seq.Step('reach', (0.5,) * 6, None), seq.Step('rail', None, None, (0.0, 0.0, 0.1)),
             seq.Step('grasp', None, seq.GRIP_CLOSE), seq.Step('release', None, seq.GRIP_OPEN)]
    with pytest.raises(seq.RefillPlanError, match='레일은'):
        seq.validate_plan(steps, HOME, ('fold',), 3)
    with pytest.raises(seq.RefillPlanError, match='숫자 3개|관절 3개'):
        seq.validate_plan([seq.Step('rail', None, None, (0.0, 0.0))] + steps[2:], HOME, ('fold',), 3)


def test_front_approach_keeps_the_tool_horizontal_and_the_module_grip_behind():
    s = scene()
    module = next(c for c in s.cells if c.kind == 'module')
    pick, grip = V.pick_points(module, V.DEFAULT_PARAMS)
    assert grip[1] < module.center[1] and pick[0][1][1] < grip[1]            # 앞(−y)에서 들어가 뒤쪽 절반을 잡는다
    assert grip[2] == pytest.approx(module.center[2] + 0.03)                 # 가운데보다 0.03 위(QR, 작전 9/23)
    for yaw in (0.0, math.pi / 4):
        direction = V.tool_direction(yaw)
        assert abs(direction[2]) < 1e-12                                     # 공구는 수평이다
    place, _ = V.place_points(module, s.targets['module'], grip, V.DEFAULT_PARAMS)
    release = place[-1][1]
    center = tuple(r - (g - c) for r, g, c in zip(release, grip, module.center, strict=True))
    assert center[1] > s.targets['module'].point[1]                          # 약통 중심이 앞면을 넘는다(판정)
    assert release[1] < s.targets['module'].point[1]                         # 손가락 끝(TCP)은 앞면 밖이다


# ---- 연속 구동기 ------------------------------------------------------------------------------------

def test_soak_reads_the_plan_feedback_and_summarizes():
    assert soak.parse_plan('plan cell=floor_left/r0c0 kind=cylinder seed=3 draw=5') == {
        'cell': 'floor_left/r0c0', 'kind': 'cylinder', 'seed': '3', 'draw': '5'}
    assert soak.parse_plan('to_shelf') is None
    rows = [{'kind': 'cylinder', 'success': True, 'seconds': 20.0, 'reason': ''},
            {'kind': 'module', 'success': False, 'seconds': 40.0, 'reason': 'timeout'},
            {'kind': 'module', 'success': True, 'seconds': 30.0, 'reason': ''}]
    summary = soak.summarize(rows)
    assert summary['sent'] == 3 and summary['succeeded'] == 2 and summary['failed'] == {'timeout': 1}
    assert summary['mean_s'] == 30.0 and summary['by_kind']['module'] == {'sent': 2, 'succeeded': 1}


# ---- 노드(대역) -------------------------------------------------------------------------------------

def v2_node(nodes, monkeypatch, plans):
    """scene_version 2 대역. plan_refill 은 plans 에서 차례로 꺼낸다(None 이면 건너뜀)."""
    node, m0609 = rf.m0609_harness(nodes, monkeypatch, start=HOME)
    node._home = HOME
    node._scene_v2 = True
    node.planned = []

    def plan_refill(model, scene_, cell, *rest, **options):
        node.planned.append(cell.cell_id)
        return plans.pop(0)

    node._v2 = types.SimpleNamespace(kind_of=V.kind_of, plan_refill=plan_refill, PlanEntry=V.PlanEntry,
                                     refill_done_detail=V.refill_done_detail)
    node._scene = scene()
    node._v2_cache = V.PlanCache()
    node._v2_cache.refresh(node._scene)
    node._v2_cache_lock = threading.Lock()
    node._v2_done = None
    node._rail_joint_names = ['rail_x', 'rail_y', 'rail_z']
    node._rail_teach = seq.RailTeach(HOME, (0.0, 0.0, 0.0), ('fold', 'fold_back'), {})
    node._v2_picker = P.CellPicker(5)
    node._v2_max_skips = 2
    node._tcp_model = node._v2_link_boxes = node._v2_tcp = node._v2_seeds = node._v2_params = None
    node._v2_rail_select = V.FIRST_FEASIBLE
    node.feedback = []
    node.ran = []
    node._run_rail_steps = lambda handle, letter, deadline, cancelled: node.ran.append(
        node._rail_teach.slots[letter]) or None
    return node


def handle_for(item='drug-amox'):
    handle = types.SimpleNamespace(request=types.SimpleNamespace(item_id=item, slot=0), is_cancel_requested=False)
    handle.publish_feedback = lambda f: handle.feedback.append(f.phase)
    handle.feedback = []
    return handle


GOOD = [seq.Step('rail_to_shelf', None, None, (0.0, 0.0, 0.1)), seq.Step('grasp', None, seq.GRIP_CLOSE),
        seq.Step('fold', HOME, None), seq.Step('rail_to_inlet', None, None, (0.5, 0.0, 0.2)),
        seq.Step('release', None, seq.GRIP_OPEN), seq.Step('fold_back', HOME, None)]


def test_node_skips_a_cell_without_a_plan_then_runs_the_next(nodes, monkeypatch):
    node = v2_node(nodes, monkeypatch, [(None, '여유 부족', None), (list(GOOD), '여유 0.03', 0.03)])
    handle = handle_for()
    node.set_goal_active(True)
    try:
        assert node._run_v2(handle, node.sim_now() + 30.0, lambda: False) is None
    finally:
        node.set_goal_active(False)
        node.plant.stop()
    first, second = node._v2_picker.history
    assert first.cell_id != second.cell_id and first.kind == second.kind == 'cylinder'
    assert handle.feedback == [f'plan cell={second.cell_id} kind=cylinder seed=5 draw=2']
    assert node.ran and node.ran[0][0].phase == 'rail_to_shelf'


def test_node_fails_when_every_cell_is_skipped_or_the_item_is_unknown(nodes, monkeypatch):
    node = v2_node(nodes, monkeypatch, [(None, 'x', None)] * 3)
    try:
        status, detail, _ = node._run_v2(handle_for(), node.sim_now() + 30.0, lambda: False)
        assert status == 'failed' and '건너뜀' in detail and len(node._v2_picker.history) == 3
        status, detail, _ = node._run_v2(handle_for('drug-none'), node.sim_now() + 30.0, lambda: False)
        assert status == 'failed' and 'drug-none' in detail
        node._scene = None
        status, detail, _ = node._run_v2(handle_for(), node.sim_now() + 30.0, lambda: False)
        assert status == 'failed' and 'inventory' in detail
    finally:
        node.plant.stop()


def test_plans_are_cached_per_cell_and_dropped_when_the_scene_changes():
    s = scene()
    cache = V.PlanCache()
    assert cache.refresh(s) is True and cache.refresh(s) is False
    cell = s.cells[0]
    entry = V.PlanEntry(list(GOOD), 'ok', 0.03, 5.0)
    cache.put(s, cell, entry)
    assert cache.get(s, cell) is entry and len(cache.missing(s)) == 15
    gone = s._replace(cells=tuple(c._replace(present=False) for c in s.cells))
    assert cache.refresh(gone) is False and cache.get(gone, gone.cells[0]) is entry        # 있음/없음은 그대로
    moved = s._replace(cells=(cell._replace(center=(0.0, 0.0, 0.0)),) + s.cells[1:])
    assert cache.get(moved, moved.cells[0]) is None                                         # 칸이 옮겨지면 그 칸만
    changed = s._replace(obstacles=s.obstacles[1:])
    assert cache.refresh(changed) is True and cache.get(changed, changed.cells[0]) is None  # 장면이 바뀌면 전부


def test_node_uses_the_cached_plan_and_reports_v2_detail_json(nodes, monkeypatch):
    node = v2_node(nodes, monkeypatch, [(list(GOOD), '여유 0.03', 0.03)])
    try:
        cell_ids = [c.cell_id for c in node._scene.cells if c.kind == 'cylinder']
        for cid in cell_ids:                                                  # 미리 푼 캐시
            cell = next(c for c in node._scene.cells if c.cell_id == cid)
            node._v2_cache.put(node._scene, cell, V.PlanEntry(list(GOOD), '여유 0.03', 0.03, 6.0))
        handle = handle_for()
        handle.succeed = handle.abort = handle.canceled = lambda: None
        node.set_goal_active(True)
        status, _, _ = node._run_refill(handle, node.generation())
        assert status == 'ok' and node.planned == []                          # 계산하지 않고 캐시만 썼다
        [done] = [e for e in node._event_pub.sent if e.name.endswith('REFILL_DONE')]
        detail = json.loads(done.detail)
        assert set(detail) == {'item', 'slot', 'kind', 'cell', 'target', 'seed', 'draw', 'clearance'}
        assert detail['item'] == 'drug-amox' and detail['kind'] == 'cylinder' and detail['target'] == 'round'
        assert detail['slot'] == 'a' and detail['seed'] == 5 and detail['draw'] == 1 and detail['clearance'] == 0.03
        assert detail['cell'] in cell_ids and ' ' not in done.detail
    finally:
        node.set_goal_active(False)
        node.plant.stop()


def test_v2_detail_is_one_compact_json_line_with_the_agreed_fields():
    text = V.refill_done_detail('drug-ibu', 'b', 'module', 'upper_left/r0c0', 'module', 7, 2, 0.019999)
    assert text == ('{"item":"drug-ibu","slot":"b","kind":"module","cell":"upper_left/r0c0","target":"module",'
                    '"seed":7,"draw":2,"clearance":0.02}')
    assert tuple(json.loads(text)) == V.DETAIL_FIELDS
    assert json.loads(V.refill_done_detail('a', 'a', 'cylinder', 'c', 'round', 0, 1, 0.01, lot='L1'))['lot'] == 'L1'


def test_cells_known_to_have_no_plan_are_not_drawn(nodes, monkeypatch):
    node = v2_node(nodes, monkeypatch, [])
    try:
        cylinders = [c for c in node._scene.cells if c.kind == 'cylinder']
        for cell in cylinders[:-1]:                                            # 하나만 계획이 있다
            node._v2_cache.put(node._scene, cell, V.PlanEntry(None, '여유 부족', None, 5.0))
        node._v2_cache.put(node._scene, cylinders[-1], V.PlanEntry(list(GOOD), '여유 0.03', 0.03, 5.0))
        handle = handle_for()
        node.set_goal_active(True)
        assert node._run_v2(handle, node.sim_now() + 30.0, lambda: False) is None
        [choice] = node._v2_picker.history                                     # 한 번에 그 칸을 뽑았다
        assert choice.cell_id == cylinders[-1].cell_id and choice.candidates == 1 and node.planned == []
    finally:
        node.set_goal_active(False)
        node.plant.stop()


def test_every_cell_of_the_current_scene_has_a_plan():
    """재범 9/18 결정(받침 0.55): 16칸 모두 기본 후보로 계획이 나온다(잡기·넣기 여유 1 cm 이상, 레일 한계 5 cm 안쪽)."""
    s = scene()
    tcp, boxes = collision()
    legs = {}
    for cell in s.cells:
        steps, why, value = V.plan_refill(model(), s, cell, boxes, tcp, P.default_seeds(HOME, 12, seed=1),
                                          V.DEFAULT_PARAMS, HOME, place_cache=legs)
        assert steps is not None, why
        assert value >= V.DEFAULT_PARAMS.min_clearance
        for step in steps:
            if step.rail is not None:
                assert V.rail_margin(step.rail, s) >= V.DEFAULT_PARAMS.rail_limit_margin - 1e-9


def test_round_rail_candidates_cover_the_tool_aligned_pose():
    """병원 기준 투입구(#485 앵커)는 실습37 자리보다 −x 0.30·+y 0.10 안쪽이다.

    yaw −45° 후보 둘만으로는 원통 칸 아홉이 전부 `넣기(round)` 에서 떨어졌다(9/23 회차: 9/18칸).
    yaw 0 후보를 더해 **18/18** 이 됐다(오프라인 전수, DEFAULT_PARAMS·first_feasible, 여유 0.0108 m).
    이 넷을 빼면 병원 원통 보충이 다시 막힌다. 후보 수가 `max_rail_tries` 를 넘으면 뒤 후보는 시도조차 안 된다.
    """
    yaws = {round(yaw, 6) for yaw, _offset in V.DEFAULT_PARAMS.rail_round}
    assert 0.0 in yaws
    assert round(-math.pi / 4, 6) in yaws
    assert len(V.DEFAULT_PARAMS.rail_round) <= V.DEFAULT_PARAMS.max_rail_tries
