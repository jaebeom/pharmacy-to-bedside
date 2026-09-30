"""`v2_rail_select` — 기본 모드 동일성과 새 모드의 gate 불변(카드 G2a, #388).

이 시험이 지키는 것.
1. **기본값에서 계획이 v0.3.0 과 같다.** 새 후보 필드가 있어도 읽지 않는다.
2. **guarded `module_path` 는 새 후보를 보지 않는다.**
3. **새 모드가 hard gate 를 하나도 낮추지 않는다** — 여유·레일 한계·최소 도달이 그대로다.
4. `scene_signature` 는 모드를 싣지 않는다(guarded 경로와 `steps.scene_signature` 로도 흘러간다).
"""

import os

import pytest
import yaml

from rokey_p3_manipulation import clearance as C
from rokey_p3_manipulation import m0609_kinematics as kin
from rokey_p3_manipulation import pick_plan as P
from rokey_p3_manipulation import scene_v2 as V

HERE = os.path.dirname(__file__)
HOME = (0.0, 0.0, 1.5883, 0.0, 1.5778, 0.0)


def scene():
    with open(os.path.join(HERE, 'data', 'pharmacy_v2.json'), encoding='utf-8') as handle:
        return V.parse_inventory(handle.read())


def collision():
    with open(os.path.join(HERE, '..', 'config', 'm0609_collision.yaml'), encoding='utf-8') as handle:
        return C.load_collision(yaml.safe_load(handle))


def model():
    return kin.M0609(kin.ToolTransform((0.0, 0.0, 0.19671), (0.0, 0.0, 0.0, 1.0)))


def plan(params, mode, cell, cache=None):
    tcp, boxes = collision()
    return V.plan_refill(model(), scene(), cell, boxes, tcp, P.default_seeds(HOME, 8, seed=1), params, HOME,
                         place_cache=cache, rail_select=mode)


def a_cell(kind='module'):
    for cell in scene().cells:
        if cell.kind == kind and cell.present:
            return cell
    raise AssertionError(f'{kind} 칸이 없다')


@pytest.fixture(scope='module')
def cells():
    return [a_cell('module'), a_cell('cylinder')]


# ---- 1. 기본 모드 동일성 -------------------------------------------------------------------------

def test_the_default_is_the_behaviour_that_shipped():
    assert V.FIRST_FEASIBLE == 'first_feasible'
    assert V.DEFAULT_PARAMS.rail_pick_extra == ()
    assert V.DEFAULT_PARAMS.rail_module_extra == ()
    assert V.DEFAULT_PARAMS.rail_round_extra == ()


def test_extra_candidates_are_invisible_to_the_default_mode(cells):
    """새 후보가 든 Params 로 기본 모드를 돌려도 결과가 같아야 한다 — 읽지 않기 때문이다."""
    for cell in cells:
        plain = plan(V.DEFAULT_PARAMS, V.FIRST_FEASIBLE, cell)
        loaded = plan(V.PREFERRED_PARAMS, V.FIRST_FEASIBLE, cell)
        assert plain[1] == loaded[1], cell.cell_id
        assert plain[2] == loaded[2], cell.cell_id
        assert [(s.phase, s.joints, s.rail, s.gripper) for s in plain[0]] == \
               [(s.phase, s.joints, s.rail, s.gripper) for s in loaded[0]], cell.cell_id


def test_module_path_never_reads_the_extra_candidates():
    """guarded 경로가 보는 것은 `rail_pick`·`rail_module` 뿐이다(계획 밖 후보가 새면 안 된다)."""
    import inspect

    from rokey_p3_manipulation import module_path
    source = inspect.getsource(module_path)
    for field in ('rail_pick_extra', 'rail_module_extra', 'rail_round_extra'):
        assert field not in source, f'module_path 가 {field} 를 읽는다'


def test_scene_signature_does_not_carry_the_mode():
    """서명은 장면만 말한다. guarded 경로와 steps.scene_signature 로도 흘러가기 때문이다(작전 9/21)."""
    s = scene()
    signature = V.scene_signature(s)
    for mode in V.RAIL_SELECT:
        cache = V.PlanCache(mode)
        cache.refresh(s)
        entry = V.PlanEntry([], 'sentinel', .02, 0.)
        cache.put(s, s.cells[0], entry)
        assert cache.get(s, s.cells[0]) is entry
        assert V.scene_signature(s) == signature
    assert V.PREFERRED_FIRST not in V.scene_signature(s)
    assert V.FIRST_FEASIBLE not in V.scene_signature(s)


def test_the_cache_is_emptied_when_the_mode_changes():
    s = scene()
    cache = V.PlanCache(V.FIRST_FEASIBLE)
    assert cache.refresh(s) is True                      # 첫 장면
    cache.put(s, s.cells[0], V.PlanEntry([], 'sentinel', .02, 0.))
    cache.legs['sentinel'] = object()
    assert cache.refresh(s) is False                     # 그대로면 유지
    assert cache.entries() and cache.legs
    assert cache.refresh(s, V.PREFERRED_FIRST) is True      # 모드가 바뀌면 버린다
    assert cache.entries() == {} and cache.legs == {}
    assert cache.rail_select == V.PREFERRED_FIRST
    assert cache.refresh(s, V.PREFERRED_FIRST) is False


# ---- 3. 새 모드가 gate 를 낮추지 않는다 -------------------------------------------------------------

def test_the_new_mode_keeps_every_hard_gate(cells):
    params = V.PREFERRED_PARAMS
    s = scene()
    for cell in cells:
        steps, why, value = plan(params, V.PREFERRED_FIRST, cell)
        assert steps is not None, f'{cell.cell_id}: {why}'
        assert value >= params.min_clearance, f'{cell.cell_id}: 여유 {value}'
        for step in steps:
            if step.rail is not None:
                # Preferred plans now include the checked return to the configured
                # home. Home Z=0 is an axis endpoint, not a work-position candidate.
                if step.rail == (0., 0., 0.):
                    assert step.phase.startswith('rail_home')
                    continue
                assert V.rail_margin(step.rail, s) >= params.rail_limit_margin - 1e-9, cell.cell_id


#: 여유 비교의 유의차 m. 여유는 관절 0.03 rad 간격 표본과 축 정렬 박스 근사로 계산되므로 해상도가 이보다
#: 훨씬 거칠다. **결과를 보고 고른 값이 아니라** 모형 해상도에서 온 값이고, 지배 비교에 쓰는 값과 같다.
#: 유의차 안이라도 낮아진 칸은 보고 표에 표시한다(작전 9/21).
CLEARANCE_TOLERANCE_M = 5e-4


def test_the_new_mode_never_lowers_the_clearance_of_a_cell(cells):
    """통과 조건(작전 9/21): 어느 칸도 임무 최소 여유가 legacy 보다 낮아지지 않는다."""
    for cell in cells:
        _, _, before = plan(V.DEFAULT_PARAMS, V.FIRST_FEASIBLE, cell)
        _, _, after = plan(V.PREFERRED_PARAMS, V.PREFERRED_FIRST, cell)
        assert after >= before - CLEARANCE_TOLERANCE_M, f'{cell.cell_id}: {before:.6f} → {after:.6f}'


def test_the_new_mode_is_deterministic(cells):
    for cell in cells:
        first = plan(V.PREFERRED_PARAMS, V.PREFERRED_FIRST, cell)
        again = plan(V.PREFERRED_PARAMS, V.PREFERRED_FIRST, cell)
        assert [(s.phase, s.joints, s.rail) for s in first[0]] == [(s.phase, s.joints, s.rail) for s in again[0]]


def test_an_unknown_mode_is_refused_rather_than_silently_ignored(cells):
    with pytest.raises(V.SceneError):
        plan(V.PREFERRED_PARAMS, 'sideways', cells[0])
