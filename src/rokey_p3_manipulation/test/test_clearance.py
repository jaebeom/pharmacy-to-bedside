"""L1. teach 경로 여유 거리(오프라인). ROS·Isaac 없이 돈다."""
import math
import os
import sys

import pytest
import yaml

from rokey_p3_manipulation import clearance as C
from rokey_p3_manipulation import m0609_kinematics as kin
from rokey_p3_manipulation import refill_sequence as seq

HERE = os.path.dirname(__file__)
CONFIG = os.path.join(HERE, '..', 'config')
SIM = os.path.join(HERE, '..', '..', '..', 'sim', 'standalone')
UNIT = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def load(name):
    with open(os.path.join(CONFIG, name), encoding='utf-8') as handle:
        return yaml.safe_load(handle)


def test_box_distance_axis_aligned_and_rotated_and_overlapping():
    box = C.Box('b', (0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
    distance, point = C.obb_box_distance((2.0, 0.0, 0.0), UNIT, (0.25, 0.25, 0.25), box)
    assert distance == pytest.approx(1.25, abs=1e-6) and point[0] == pytest.approx(1.75, abs=1e-6)
    # 45° 돌린 정육면체는 모서리(√2·0.25)가 먼저 닿는다.
    s = math.sqrt(0.5)
    rotated = ((s, s, 0.0), (-s, s, 0.0), (0.0, 0.0, 1.0))
    distance, _ = C.obb_box_distance((2.0, 0.0, 0.0), rotated, (0.25, 0.25, 0.25), box)
    assert distance == pytest.approx(1.5 - math.sqrt(2) * 0.25, abs=1e-6)
    # 모서리끼리: (1,1,1) 방향으로 떨어진 작은 상자.
    distance, _ = C.obb_box_distance((1.0, 1.0, 1.0), UNIT, (0.1, 0.1, 0.1), box)
    assert distance == pytest.approx(math.sqrt(3) * 0.4, abs=1e-6)
    assert C.obb_box_distance((0.4, 0.0, 0.0), UNIT, (0.25, 0.25, 0.25), box)[0] == 0.0


def test_link_frames_follow_the_kinematics_chain():
    joints = (0.3, -0.4, 1.2, 0.1, 1.9, -1.5)
    model = kin.M0609(kin.ToolTransform((0.0, 0.0, 0.19671), (0.0, 0.0, 0.0, 1.0)))
    tcp, origins, _ = model.chain(joints)
    frames = C.link_frames(joints, (0.0, 0.0, 0.19671))
    for index, origin in enumerate(origins, 1):
        assert math.dist(frames[f'link_{index}'][0], origin) < 1e-12
    assert math.dist(frames['tcp'][0], tcp.position_m) < 1e-12


def test_stage_boxes_match_the_stage_layout():
    """옮긴 값이 sim/standalone/p3sim/layout.py 와 같다(저장소 checkout 에서만)."""
    if not os.path.isdir(os.path.join(SIM, 'p3sim')):
        pytest.skip('sim/ 이 없는 설치 트리')
    sys.path.insert(0, SIM)
    try:
        from p3sim import layout as L
    finally:
        sys.path.remove(SIM)
    room = L.default_layout()
    shelf, _ = L.shelf_boxes(room['shelf_origin'], room['shelf_cols'], room['shelf_rows'], tuple(room['shelf_cell']),
                             room['shelf_depth'], room['shelf_plinth'])
    dispenser, _, _ = L.dispenser_boxes(room['dispenser_origin'], room['dispenser_size'], room['inlet_size'],
                                        room['inlet_height'], room['inlet_wall'], room['belt_top'],
                                        room['outlet_size'], inlet_gap=room['inlet_gap'])
    stage = {b.name: (b.center, b.size) for b in shelf + dispenser}
    for box in C.STAGE_BOXES:
        center, size = stage[box.name]
        assert max(abs(a - b) for a, b in zip(center + size, box.center + box.size, strict=True)) < 1e-9, box.name
    assert (room['rail_origin'][0], room['rail_origin'][1], room['carriage_height']) == C.BASE_ORIGIN


def test_path_moves_the_rail_with_the_arm_still_and_ends_home():
    teach = seq.load_rail_teach(load('m0609_rail_teach.yaml'))
    points = C.sample_path(teach, 'a')
    assert points[0][1] == teach.home_joints and points[0][2] == teach.home_rail
    assert points[-1][1] == teach.home_joints and points[-1][2] == teach.home_rail
    rail_phases = {s.phase for s in teach.slots['a'] if s.rail is not None} | {'home_rail'}
    for phase in rail_phases:
        arms = {p[1] for p in points if p[0] == phase}
        rails = {p[2] for p in points if p[0] == phase}
        assert len(arms) == 1 and len(rails) > 2, phase
    carrying = [p[0] for p in points if p[3]]
    assert carrying[0] == 'lift' and carrying[-1] == 'insert'


def test_the_model_reproduces_the_practice3_contact_and_its_fix():
    """모델 검증(9/18 실습3). 옛 teach(3e7ed77, 투입구 앞 y 0.40)에서는 link_4 가 조제기 앞면에 닿고(실습3-B impulse,
    y 0.70, z 1.23-1.38), 지금 teach(투입구 y 0.33)는 3 cm 넘게 떨어진다. 캐니스터는 빼고 팔만 본다."""
    tcp, boxes = C.load_collision(load('m0609_collision.yaml'))
    arm = [b for b in boxes if b.link == 'link_4']
    body = [b for b in C.STAGE_BOXES if b.name == 'DispenserBody']
    old_insert = (1.5552, 0.1181, 1.1488, 0.0004, 1.8734, -1.5864)       # 3e7ed77 insert a
    teach = seq.load_rail_teach(load('m0609_rail_teach.yaml'))
    new_insert = next(s.joints for s in teach.slots['a'] if s.phase == 'insert')
    rail = (0.94, -0.05)
    [before] = C.clearance_table([('insert', old_insert, rail, False)], arm, tcp, body)
    [after] = C.clearance_table([('insert', new_insert, rail, False)], arm, tcp, body)
    assert before.distance == 0.0 and 1.2 < before.point[2] < 1.4 and before.point[1] == pytest.approx(0.70)
    assert after.distance > 0.03


def test_collision_file_loads_and_rejects_bad_boxes():
    tcp, boxes = C.load_collision(load('m0609_collision.yaml'))
    assert tcp == (0.0, 0.0, 0.19671)
    assert {b.link for b in boxes} >= set(C.LINKS)
    with pytest.raises(ValueError, match='모르는 링크'):
        C.load_collision({'tcp_offset': [0, 0, 0], 'boxes': [{'link': 'link_9', 'min': [0] * 3, 'max': [1] * 3}]})
    with pytest.raises(ValueError, match='min < max'):
        C.load_collision({'tcp_offset': [0, 0, 0], 'boxes': [{'link': 'link_1', 'min': [0] * 3, 'max': [0] * 3}]})


def test_module_imports_no_ros():
    with open(C.__file__, encoding='utf-8') as handle:
        text = handle.read()
    for forbidden in ('import rclpy', 'from rclpy', 'import isaacsim', 'from isaacsim', 'import pxr'):
        assert forbidden not in text


def test_worst_clearance_matches_the_table_minimum_and_stops_early():
    tcp, boxes = C.load_collision(load('m0609_collision.yaml'))
    teach = seq.load_rail_teach(load('m0609_rail_teach.yaml'))
    points = C.sample_path(teach, 'a', joint_step=0.05, rail_step=0.05)
    table = min(C.clearance_table(points, boxes, tcp), key=lambda h: h.distance)
    worst = C.worst_clearance(points, boxes, tcp, C.STAGE_BOXES)
    assert worst.distance == pytest.approx(table.distance, abs=1e-9)
    early = C.worst_clearance(points, boxes, tcp, C.STAGE_BOXES, stop_below=0.05)
    assert early.distance < 0.05                                    # 기준보다 가까운 곳을 찾자마자 멈춘다
