"""보충 전 약통 확인의 팔 쪽 판단(계약 2.3). ROS 없이 돈다."""

from rokey_p3_manipulation import container_gate as gate
from rokey_p3_manipulation.pick_plan import Cell, CellPicker


def test_only_reads_after_arrival_count():
    reads = [gate.Read(9.0, 'cn-0101'), gate.Read(10.5, 'cn-0106'), gate.Read(10.2, 'cn-0105')]
    assert gate.latest_read(reads, since=10.0) == gate.Read(10.5, 'cn-0106')
    assert gate.latest_read(reads, since=11.0) is None


def test_unknown_is_refused():
    assert gate.decide(None, (True, 'ok')) == (False, 'unreadable', '')
    assert gate.decide(gate.Read(1.0, 'cn-0106'), None) == (False, 'check_timeout', 'cn-0106')
    assert gate.decide(gate.Read(1.0, 'cn-0106'), (False, 'expired')) == (False, 'expired', 'cn-0106')
    assert gate.decide(gate.Read(1.0, 'cn-0105'), (True, 'ok')) == (True, 'ok', 'cn-0105')


def test_refused_cells_are_per_epoch():
    refused = gate.RefusedCells()
    refused.add(1, 'floor_right/r0c1')
    refused.add(1, 'floor_right/r0c1')
    assert refused.of(1) == ['floor_right/r0c1']
    assert refused.of(2) == []
    refused.add(2, 'floor_left/r0c0')
    assert refused.of(1) == []


def test_after_a_refusal_the_next_draw_is_another_cell():
    """작전 9/23: 거부 뒤 다른 약통으로 보충이 이어진다. 시드 7 의 첫 원통 칸(만료)을 빼면 다른 칸이 나온다."""
    cells = [Cell(f'{shelf}/r{r}c{c}', 'cylinder', 'drug-amox', True)
             for shelf in ('floor_left', 'floor_right') for r in (0, 1) for c in (0, 1)]
    first, _ = CellPicker(7).choose(cells, 'cylinder', 'drug-amox')
    assert first.cell_id == 'floor_right/r0c1'          # 카탈로그의 만료 칸(cn-0106)
    refused = gate.RefusedCells()
    refused.add(1, first.cell_id)
    picker = CellPicker(7)
    picker.choose(cells, 'cylinder', 'drug-amox')         # 앞 goal 의 뽑기(같은 노드는 뽑기 순서가 이어진다)
    second, _ = picker.choose(cells, 'cylinder', 'drug-amox', exclude=refused.of(1))
    assert second is not None and second.cell_id != first.cell_id
