"""L1. 칸별 계획 캐시를 파일로 저장하고 다시 쓴다(작전 결정 6, 9/23).

장면은 `test/data/pharmacy_v2.json` 이다(test_scene_v2 와 같다). ROS 를 띄우지 않는다.
"""
import os
import tempfile
import types

import test_reset_fence as rf
import yaml

from rokey_p3_manipulation import clearance as C
from rokey_p3_manipulation import m0609_kinematics as kin
from rokey_p3_manipulation import pick_plan as P
from rokey_p3_manipulation import plan_cache_file as F
from rokey_p3_manipulation import scene_v2 as V

nodes = rf.nodes                 # pytest 픽스처(test_scene_v2 와 같은 대역 rclpy)
HERE = os.path.dirname(__file__)
HOME = (0.0, 0.0, 1.5883, 0.0, 1.5778, 0.0)


def scene():
    with open(os.path.join(HERE, 'data', 'pharmacy_v2.json'), encoding='utf-8') as handle:
        return V.parse_inventory(handle.read())


def collision():
    with open(os.path.join(HERE, '..', 'config', 'm0609_collision.yaml'), encoding='utf-8') as handle:
        return C.load_collision(yaml.safe_load(handle))


def inputs(tcp, link_boxes, seeds):
    return {'seeds': seeds, 'params': V.DEFAULT_PARAMS, 'tcp': tcp, 'link_boxes': link_boxes,
            'home': HOME, 'home_rail': (0.0, 0.0), 'module_limits': None,
            'joint_limits': ((-3.0, 3.0),) * 6}


def solve_one(built, cell, tcp, link_boxes, seeds):
    model = kin.M0609(kin.ToolTransform(tcp, (0.0, 0.0, 0.0, 1.0)))
    steps, why, clearance = V.plan_refill(model, built, cell, link_boxes, tcp, seeds,
                                          V.DEFAULT_PARAMS, HOME, place_cache={})
    return V.PlanEntry(steps, why, clearance, 0.0)


# ---- 키 --------------------------------------------------------------------------------------

def test_the_key_changes_with_anything_that_changes_the_answer():
    built = scene()
    tcp, link_boxes = collision()
    seeds = P.default_seeds(HOME, 4, seed=1)
    cells = {c.cell_id: V.cell_key(c) for c in built.cells}
    base = F.plan_key(V.scene_signature(built), V.FIRST_FEASIBLE, cells, inputs(tcp, link_boxes, seeds))
    assert base == F.plan_key(V.scene_signature(built), V.FIRST_FEASIBLE, cells,
                              inputs(tcp, link_boxes, seeds))          # 같은 입력이면 같은 키
    assert base != F.plan_key(V.scene_signature(built), V.PREFERRED_FIRST, cells,
                              inputs(tcp, link_boxes, seeds))          # 고르기 방식
    moved = dict(cells)
    first = sorted(moved)[0]
    kind, centre, size = moved[first]
    moved[first] = (kind, (centre[0] + 0.01, centre[1], centre[2]), size)
    assert base != F.plan_key(V.scene_signature(built), V.FIRST_FEASIBLE, moved,
                              inputs(tcp, link_boxes, seeds))          # 칸이 움직였다
    other = inputs(tcp, link_boxes, seeds)
    other['params'] = V.DEFAULT_PARAMS._replace(min_clearance=0.02)
    assert base != F.plan_key(V.scene_signature(built), V.FIRST_FEASIBLE, cells, other)
    assert base != F.plan_key(V.scene_signature(built), V.FIRST_FEASIBLE, cells,
                              inputs(tcp, link_boxes, seeds), code='다른 코드')   # 계획 코드가 바뀌었다


def test_the_picker_seed_is_not_part_of_the_key():
    """`v2_seed` 는 어느 칸을 고를지만 정한다. 칸의 계획은 바꾸지 않는다(요구 1)."""
    tcp, link_boxes = collision()
    seeds = P.default_seeds(HOME, 4, seed=1)
    material = inputs(tcp, link_boxes, seeds)
    assert 'v2_seed' not in material and 'picker' not in material


# ---- 저장 → 읽기 -----------------------------------------------------------------------------

def test_solve_then_save_then_load_gives_the_same_steps():
    built = scene()
    tcp, link_boxes = collision()
    seeds = P.default_seeds(HOME, 8, seed=1)      # test_scene_v2 의 계획 시험과 같은 칸·같은 씨앗 수
    cell = next(c for c in built.cells if c.cell_id == 'floor_right/r1c0')
    entry = solve_one(built, cell, tcp, link_boxes, seeds)
    assert entry.steps is not None, entry.why
    key = F.plan_key(V.scene_signature(built), V.FIRST_FEASIBLE,
                     {c.cell_id: V.cell_key(c) for c in built.cells}, inputs(tcp, link_boxes, seeds))
    assert len(key) == 64
    with tempfile.TemporaryDirectory() as directory:
        assert F.load(directory, key) is None                     # 아직 없다
        assert F.save(directory, key, {cell.cell_id: (V.cell_key(cell), entry)}) is not None
        plans = F.load(directory, key)
        assert set(plans) == {cell.cell_id}
        restored = plans[cell.cell_id][1]
        assert restored.steps == entry.steps                      # 새로 푼 것과 같다
        assert restored.clearance == entry.clearance
        cache = V.PlanCache()
        cache.refresh(built)
        assert cache.load_plans(built, plans) == (1, len(built.cells))
        assert cache.get(built, cell).steps == entry.steps
        assert [c.cell_id for c in cache.missing(built)] == [
            c.cell_id for c in built.cells if c.cell_id != cell.cell_id]


def test_a_different_key_is_not_read_and_the_file_stays():
    built = scene()
    cell = next(c for c in built.cells if c.kind == 'cylinder')
    entry = V.PlanEntry(('step',), '', 0.02, 1.0)
    with tempfile.TemporaryDirectory() as directory:
        path = F.save(directory, 'a' * 64, {cell.cell_id: (V.cell_key(cell), entry)})
        assert F.load(directory, 'b' * 64) is None
        assert os.path.exists(path)                               # 지우지 않는다
        assert F.load(directory, 'a' * 64) is not None


def test_unsolved_cells_are_not_saved():
    built = scene()
    cells = list(built.cells)[:2]
    plans = {cells[0].cell_id: (V.cell_key(cells[0]), V.PlanEntry(('step',), '', 0.02, 1.0)),
             cells[1].cell_id: (V.cell_key(cells[1]), V.PlanEntry(None, '여유 부족', None, 1.0))}
    assert set(F.solved_only(plans)) == {cells[0].cell_id}
    with tempfile.TemporaryDirectory() as directory:
        F.save(directory, 'c' * 64, plans)
        assert set(F.load(directory, 'c' * 64)) == {cells[0].cell_id}


def test_an_empty_directory_turns_the_file_cache_off():
    assert F.path_for('', 'a' * 64) is None
    assert F.load('', 'a' * 64) is None
    assert F.save('', 'a' * 64, {'cell': (None, V.PlanEntry(('step',), '', 0.0, 0.0))}) is None


def test_a_damaged_file_reads_as_no_cache():
    with tempfile.TemporaryDirectory() as directory:
        path = F.path_for(directory, 'd' * 64)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'not a pickle')
        assert F.load(directory, 'd' * 64) is None


def test_the_cache_loads_only_cells_whose_key_still_matches():
    built = scene()
    cell = next(c for c in built.cells if c.kind == 'cylinder')
    entry = V.PlanEntry(('step',), '', 0.02, 1.0)
    kind, centre, size = V.cell_key(cell)
    stale = {cell.cell_id: ((kind, (centre[0] + 0.05, centre[1], centre[2]), size), entry)}
    cache = V.PlanCache()
    cache.refresh(built)
    assert cache.load_plans(built, stale) == (0, len(built.cells))
    assert cache.get(built, cell) is None


# ---- 전부 적중한 기동 -------------------------------------------------------------------------

def summary_node(nodes, monkeypatch):
    """요약을 낼 수 있을 만큼만 갖춘 대역 노드. 모든 칸이 이미 캐시에 있다."""
    import threading

    import test_scene_v2 as S

    node = S.v2_node(nodes, monkeypatch, [])
    node._closing = threading.Event()
    node._inventory_generation = 1
    node._inventory_source = 'test'
    node._plan_cache_dir = ''                      # 빈 값 = 파일 캐시 끔. 저장은 여기서 일어나지 않는다
    node._plan_cache = F
    node.logged = []
    node.payloads = []
    node.get_logger = lambda: types.SimpleNamespace(
        info=lambda text, **options: node.logged.append(text),
        warn=lambda text, **options: node.logged.append(text))
    node._publish_plan_cache_payload = node.payloads.append
    for cell in node._scene.cells:
        node._v2_cache.put(node._scene, cell, V.PlanEntry(('step',), '여유 0.03', 0.03, 6.0))
    return node


def test_a_full_cache_hit_still_reports_the_summary_and_the_payload(nodes, monkeypatch):
    """파일에서 칸을 전부 읽어 **풀 것이 없어도** 요약 두 줄과 payload 가 나가야 한다(최적화 9/23).

    안 나가면 demo_v2 의 `P3_ARM_READY`(`완료 종류: .*cylinder`)가 시한까지 기다리다 up 이 멈춘다.
    """
    node = summary_node(nodes, monkeypatch)
    assert node._v2_cache.missing(node._scene) == []        # 풀 것이 없다
    node._precompute_plans()
    assert node.planned == []                               # 아무것도 새로 풀지 않았다
    assert any(text.startswith('v2 계획 캐시: ') for text in node.logged), node.logged
    kinds = [text for text in node.logged if '완료 종류: ' in text]
    assert len(kinds) == 1, node.logged
    assert 'cylinder' in kinds[0] and 'module' in kinds[0]
    [payload] = node.payloads
    assert payload['ready'] is True and payload['solved'] == payload['total'] == len(node._scene.cells)
    assert sorted(payload['kinds_ready']) == ['cylinder', 'module']


def test_an_unchanged_inventory_does_not_report_again(nodes, monkeypatch):
    """같은 장면이 다시 오면 요약을 또 내지 않는다 — 재고는 보충마다 다시 발행된다."""
    node = summary_node(nodes, monkeypatch)
    node._precompute_plans()
    before = len(node.logged)
    assert node._v2_cache.refresh(node._scene) is False     # 같은 장면: 비우지 않는다
    assert node._v2_cache.missing(node._scene) == []        # 그래서 돌릴 일도 없다
    assert len(node.logged) == before
