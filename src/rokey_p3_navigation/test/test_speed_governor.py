"""L1. 지역 코스트맵의 여유 → Nav2 속도 제한(%). ROS 를 띄우지 않는다.

재범 9/23: 넓은 복도에서 0.8–1.0 m/s, 장애물·문 근처에서만 0.5.
값은 우리가 고른 것이다. 이 시험은 **규칙**이 뜻대로인지만 본다 — 실제 주행은 회차가 본다.
"""
import math
from pathlib import Path

import pytest
import yaml

from rokey_p3_navigation import speed_governor as G

PARAMS = yaml.safe_load(
    (Path(__file__).resolve().parents[1] / "config" / "nav2_params.yaml").read_text(encoding="utf-8"))


def grid(width, height, blocked=(), value=G.LETHAL):
    """행 우선 코스트맵. `blocked` 는 (column, row) 들이다."""
    cells = [0] * (width * height)
    for column, row in blocked:
        cells[row * width + column] = value
    return cells


# ---- 여유 재기 --------------------------------------------------------------------------------

def test_an_empty_costmap_has_no_obstacle():
    assert G.clearance(grid(11, 11), 11, 11, 0.05) is None


def test_the_distance_is_measured_from_the_middle_because_that_is_the_robot():
    # 11x11 격자의 한가운데는 (5, 5). (8, 5) 는 세 칸 = 0.15 m 다.
    assert abs(G.clearance(grid(11, 11, [(8, 5)]), 11, 11, 0.05) - 0.15) < 1e-9


def test_the_nearest_obstacle_wins():
    cells = grid(11, 11, [(10, 5), (7, 5)])
    assert abs(G.clearance(cells, 11, 11, 0.05) - 0.10) < 1e-9


def test_cells_below_the_threshold_and_unknown_cells_are_not_obstacles():
    assert G.clearance(grid(11, 11, [(8, 5)], value=G.LETHAL - 1), 11, 11, 0.05) is None
    assert G.clearance(grid(11, 11, [(8, 5)], value=G.UNKNOWN), 11, 11, 0.05) is None


def test_only_cells_inside_the_radius_are_looked_at():
    cells = grid(21, 21, [(20, 10)])                       # 10 칸 = 0.5 m
    assert G.clearance(cells, 21, 21, 0.05, radius_m=0.3) is None
    assert abs(G.clearance(cells, 21, 21, 0.05, radius_m=0.6) - 0.5) < 1e-9


def test_a_malformed_grid_reads_as_no_answer():
    assert G.clearance([], 0, 0, 0.05) is None
    assert G.clearance(grid(4, 4), 4, 4, 0.0) is None
    assert G.clearance([0, 0], 11, 11, 0.05) is None       # data 가 짧다


# ---- 제한 정하기 ------------------------------------------------------------------------------

def test_close_is_the_slow_percent_and_open_is_full_speed():
    assert G.limit_percent(0.5) == G.SLOW_PERCENT
    assert G.limit_percent(G.NEAR_M) == G.SLOW_PERCENT
    assert G.limit_percent(G.FAR_M) == 100.0
    assert G.limit_percent(5.0) == 100.0


def test_between_the_two_it_is_a_straight_line():
    middle = (G.NEAR_M + G.FAR_M) / 2.0
    assert G.limit_percent(middle) == pytest.approx((G.SLOW_PERCENT + 100.0) / 2.0)


def test_not_knowing_means_slow():
    """코스트맵이 아직 안 왔거나 못 읽은 회차가 #526 처럼 빨라지면 안 된다."""
    assert G.limit_percent(None) == G.SLOW_PERCENT


def test_the_slow_percent_keeps_todays_speed_where_it_is_tight():
    """근접 속도는 최고 속도가 얼마든 고정 m/s 다(재범 9/29 0.5 → 0.7) — 최고 속도를 올려도 가까운 곳은 안 빨라진다."""
    assert G.SLOW_SPEED_MPS == 0.7
    assert pytest.approx(0.7) == G.SLOW_PERCENT / 100.0 * G.MAX_SPEED_MPS
    # 최고 속도를 올려도 근접 속도는 그대로여야 한다. 9/23 의 #526 이 이것을 어겼다(#547).
    for maximum in (1.0, 1.5, 2.0):
        assert G.slow_percent(0.7, maximum) / 100.0 * maximum == pytest.approx(0.7)


def test_slow_percent_refuses_values_that_cannot_mean_anything():
    for slow, maximum in ((0.5, 0.0), (0.0, 1.5), (2.0, 1.5), (-0.1, 1.5)):
        with pytest.raises(ValueError):
            G.slow_percent(slow, maximum)


def test_the_params_file_and_the_node_agree_on_the_top_speed():
    """`max_speed_mps` 가 `max_speed_xy` 와 어긋나면 기동 줄의 m/s 가 거짓이 된다 — 두 곳을 묶어 둔다."""
    governor = PARAMS["speed_governor"]["ros__parameters"]
    follow = PARAMS["controller_server"]["ros__parameters"]["FollowPath"]
    assert governor["max_speed_mps"] == follow["max_speed_xy"] == follow["max_vel_x"]
    assert governor["slow_speed_mps"] == G.SLOW_SPEED_MPS
    # 최고 속도만 올리고 급가속은 하지 않는다(재범 9/23: 복도 1.5, 가속 1.0).
    assert follow["acc_lim_x"] == follow["acc_lim_y"] == 1.0


def test_the_silence_warning_names_what_is_missing():
    """9/23 에는 원인을 추측으로 골랐다가 틀렸다. 다음 회차는 로그가 말하게 한다."""

    class Qos:
        reliability = "RELIABLE"
        durability = "VOLATILE"

    class Info:
        node_name = "local_costmap"
        node_namespace = "/amr_1"
        qos_profile = Qos()

    assert "발행자가 없다" in G.describe_publishers([])
    said = G.describe_publishers([Info()])
    assert "/amr_1/local_costmap" in said
    assert "RELIABLE/VOLATILE" in said


def test_far_must_be_beyond_near():
    try:
        G.limit_percent(1.0, near=1.0, far=1.0)
    except ValueError:
        return
    raise AssertionError('far <= near 는 거절해야 한다')


# ---- 다시 보낼지 ------------------------------------------------------------------------------

def test_the_first_value_is_always_sent_and_small_moves_are_not():
    assert G.changed(None, 100.0)
    assert not G.changed(100.0, 98.0)
    assert G.changed(100.0, 94.0)
    assert G.changed(50.0, 100.0)


def test_the_threshold_is_an_occupancy_grid_value_not_an_internal_costmap_one():
    """#610. `OccupancyGrid` 는 0–100 이다 — 253 을 문턱으로 두면 아무 칸도 안 걸려 늘 100 % 였다."""
    assert G.LETHAL <= 100
    # nav2 가 내보내는 실제 값들: 100 lethal, 99 inscribed, -1 unknown, 그 사이는 눌린 비용.
    assert G.clearance(grid(11, 11, [(8, 5)], value=100), 11, 11, 0.05) is not None
    assert G.clearance(grid(11, 11, [(8, 5)], value=98), 11, 11, 0.05) is None    # 눌린 비용은 안 막는다
    assert G.clearance(grid(11, 11, [(8, 5)], value=-1), 11, 11, 0.05) is None    # 모르는 칸도 안 막는다


def test_a_grid_that_is_not_an_occupancy_grid_is_called_out():
    assert G.looks_like_internal_costmap([0, 99, 100, -1]) is False
    assert G.looks_like_internal_costmap([0, 253, 254]) is True


def test_the_inflation_band_is_not_the_wall():
    """99 는 팽창 층의 "여기 오면 닿는다" 띠다. 그것까지 재면 벽 + 로봇 반지름을 재게 된다.

    0819f80 회차가 그 자리였다: 폭 2.5 m 복도 한가운데서도 0.80 m 로 나와 `speed limit 50%` 29줄,
    100 % 가 한 번도 없었다. 로봇 반지름은 `NEAR_M` 이 이미 품고 있으므로 두 번 세지 않는다.
    """
    assert G.LETHAL == 100
    assert G.clearance(grid(11, 11, [(8, 5)], value=99), 11, 11, 0.05) is None
    assert G.clearance(grid(11, 11, [(8, 5)], value=100), 11, 11, 0.05) is not None


def window_with_wall(distance_m, width=100, height=100, resolution=0.05, value=100):
    """5 × 5 m 지역 코스트맵 창. 로봇(가운데)에서 +x 로 `distance_m` 떨어진 곳에 세로 벽 하나."""
    cells = [0] * (width * height)
    column = int(round((width - 1) / 2.0 + distance_m / resolution))
    for row in range(height):
        cells[row * width + column] = value
    return cells, width, height, resolution


def test_more_room_is_never_slower():
    """138cbac 회차의 결함. 벽 2.2 m 면 50 %, 1.2 m 면 64 % 였다 — 넓을수록 느렸다.

    far 안에서만 찾고 못 찾으면 '모름' 으로 돌려준 탓이다. 여유가 늘면 제한은 줄지 않아야 한다.
    """
    previous = None
    for distance in (0.8, 1.0, 1.2, 1.5, 1.79, 1.9, 2.2):
        free, _kind = G.free_space(*window_with_wall(distance), far=G.FAR_M)
        percent = G.limit_percent(free)
        if previous is not None:
            assert percent >= previous, (distance, percent, previous)
        previous = percent
    assert previous == 100.0


def test_a_wall_beyond_far_reads_as_open_not_unknown():
    free, kind = G.free_space(*window_with_wall(2.2), far=G.FAR_M)
    assert kind == G.OPEN
    assert free == G.FAR_M
    assert G.limit_percent(free) == 100.0


def test_a_wall_inside_far_is_measured():
    free, kind = G.free_space(*window_with_wall(1.2), far=G.FAR_M)
    assert kind == G.MEASURED
    assert abs(free - 1.2) < 0.06


def test_an_empty_window_stays_blind_and_slow():
    """장애물 층이 눈을 감으면 창이 통째로 빈다(9/23 스캔 토픽). 그걸 넓다고 읽으면 최고 속도가 된다."""
    cells = [0] * (100 * 100)
    free, kind = G.free_space(cells, 100, 100, 0.05, far=G.FAR_M)
    assert kind == G.BLIND
    assert free is None
    assert G.limit_percent(free) == G.SLOW_PERCENT


def test_unknown_cells_are_not_evidence_of_sight():
    """-1(모르는 칸)만 있는 창도 눈을 감은 것이다. 모르는 칸은 벽이 아니다."""
    cells = [G.UNKNOWN] * (100 * 100)
    assert G.free_space(cells, 100, 100, 0.05, far=G.FAR_M) == (None, G.BLIND)


def test_a_broken_grid_is_never_read_as_open():
    """깨진 격자는 모름이다. 전에는 data 가 짧아도·해상도가 0 이어도 장애물 값 하나로 OPEN(100 %)이 됐다(커서 #631)."""
    short = [0] * 50 + [100] * 50                              # 100 × 100 이라면서 100 칸뿐
    assert G.free_space(short, 100, 100, 0.05) == (None, G.BLIND)
    assert G.free_space([100] * 10000, 100, 100, 0.0) == (None, G.BLIND)
    assert G.free_space([100] * 10000, 0, 100, 0.05) == (None, G.BLIND)
    assert G.limit_percent(G.free_space(short, 100, 100, 0.05)[0]) == G.SLOW_PERCENT
def test_a_costmap_that_stops_is_not_trusted_forever():
    """#613 N3. 받다가 끊기면 재발행 타이머가 마지막 제한을 계속 냈다 — 100 % 였으면 눈 감은 채 최고 속도."""
    assert not G.is_stale(100.0, 99.0)                     # 1 s 전에 받았다
    assert G.is_stale(100.0, 100.0 - G.STALE_AFTER_S - 0.1)
    assert not G.is_stale(100.0, None)                     # 한 번도 안 왔으면 끊김이 아니라 '아직'(이미 느린 쪽)


def test_the_stale_limit_is_the_slow_one():
    """끊겼을 때 노드는 여유를 None 으로 둔다. None 은 늘 느린 쪽이다 — 이 두 줄이 묶여 있어야 한다."""
    assert G.limit_percent(None) == G.SLOW_PERCENT
    assert G.STALE_AFTER_S > 1.0 / 2.0 * 2                 # 2 Hz 발행에서 한두 장 늦는 것으로는 안 걸린다


# ---- 정지 규칙(작전 9/25 exp/gov-stop, 회차107 더미를 밀고 감) ----------------------------------------

def _grid_with(cells_m, size=101, resolution=0.05):
    """가운데가 로봇인 size×size 격자. `cells_m` 의 (dx, dy)(m) 칸을 LETHAL 로 칠한다."""
    grid = [0] * (size * size)
    centre = (size - 1) // 2
    for dx, dy in cells_m:
        column = centre + int(round(dx / resolution))
        row = centre + int(round(dy / resolution))
        grid[row * size + column] = G.LETHAL
    return grid, size, size, resolution


def test_forward_gap_sees_only_what_is_ahead_within_body_width():
    grid, w, h, r = _grid_with([(1.0, 0.0)])                 # 앞(+x) 1.0 m → 몸체 앞끝에서 0.5 m
    assert G.forward_gap(grid, w, h, r, 0.0) == pytest.approx(0.5)
    assert G.forward_gap(grid, w, h, r, math.pi) is None            # 뒤로 가면 안 본다
    side, w, h, r = _grid_with([(0.3, 0.8)])                  # 옆으로 몸체 폭 밖
    assert G.forward_gap(side, w, h, r, 0.0) is None
    assert G.forward_gap(grid, w, h, r, None) is None               # 아직 안 움직였다


def test_forward_gap_skips_what_the_static_map_has():
    """문 앞·정차 접근의 벽·테이블(지도에 있다)로는 멈추지 않는다. 더미(지도에 없다)로만 멈춘다."""
    grid, w, h, r = _grid_with([(0.9, 0.0), (1.2, 0.0)])
    wall_at_0_9 = lambda dx, dy: abs(dx - 0.9) < 0.03   # noqa: E731
    assert G.forward_gap(grid, w, h, r, 0.0, is_static=wall_at_0_9) == pytest.approx(0.7)


def test_holonomic_heading_follows_the_motion_not_the_body():
    assert G.motion_heading(0.0, 0.3, 0.0) == pytest.approx(math.pi / 2)      # 옆걸음은 옆이 앞
    assert G.motion_heading(0.3, 0.0, math.pi / 2) == pytest.approx(math.pi / 2)
    assert G.motion_heading(0.0, 0.01, 0.0, previous=1.0) == 1.0              # 멈춰 있으면 마지막 방향


def test_stop_rule_stops_below_0_6_and_resumes_only_after_0_9_for_one_second():
    rule = G.StopRule()
    assert rule.update(0.8, 0.0) is None and not rule.stopped
    assert rule.update(0.55, 1.0) == 'stop' and rule.stopped
    assert rule.update(0.7, 2.0) is None and rule.stopped          # 0.6–0.9 사이는 그대로 선다
    assert rule.update(1.0, 3.0) is None and rule.stopped          # 비기 시작
    assert rule.update(0.85, 3.5) is None and rule.stopped         # 다시 가까워지면 지연을 새로 센다
    assert rule.update(None, 4.0) is None and rule.stopped
    assert rule.update(None, 5.0) == 'resume' and not rule.stopped


def test_stop_limit_is_not_zero_because_zero_means_no_limit_in_nav2():
    assert 0.0 < G.STOP_PERCENT < G.SLOW_PERCENT


def test_blocked_near_reads_the_static_map_with_tolerance():
    cells = [0] * 100
    cells[5 * 10 + 5] = 100                                        # (0.55, 0.55) 칸, 해상도 0.1
    assert G.blocked_near(cells, 10, 10, 0.1, 0.0, 0.0, 0.55, 0.55)
    assert G.blocked_near(cells, 10, 10, 0.1, 0.0, 0.0, 0.68, 0.55)          # 0.15 안
    assert not G.blocked_near(cells, 10, 10, 0.1, 0.0, 0.0, 0.95, 0.55)
    assert not G.blocked_near(cells, 10, 10, 0.1, 0.0, 0.0, 5.0, 5.0)        # 지도 밖


def test_status_says_why_the_stop_rule_did_not_fire():
    """9/27 block-path 랩: governor stop 0줄의 이유를 로그로 가를 수 없었다. 현황 줄이 상태를 말한다."""
    assert G.stop_rule_text(False, True, 0.0, None, False) == '정지 규칙 끔(인자)'
    assert '지도' in G.stop_rule_text(True, False, 0.0, None, False)
    assert '안 움직임' in G.stop_rule_text(True, True, None, None, False)
    assert G.stop_rule_text(True, True, 0.0, None, False) == '정지 규칙 감시, 앞 비었음'
    assert G.stop_rule_text(True, True, 0.0, 0.42, True) == '정지 규칙 정지 중, 앞 0.42 m'


def test_forward_scan_tells_seen_filtered_and_dynamic_apart():
    """9/27 block-path: 캡슐이 안 보였는지, 보였는데 지도 칸이라 뺐는지 로그로 가른다."""
    grid, w, h, r = _grid_with([(0.9, 0.0), (1.2, 0.0)])
    wall_at_0_9 = lambda dx, dy: abs(dx - 0.9) < 0.03   # noqa: E731
    dynamic, anything, skipped = G.forward_scan(grid, w, h, r, 0.0, is_static=wall_at_0_9)
    assert dynamic == pytest.approx(0.7) and anything == pytest.approx(0.4) and skipped == 1
    assert G.forward_scan(grid, w, h, r, None) == (None, None, 0)


def _capsule_window(heading, distance=1.0, radius=0.2, size=100, resolution=0.05):
    """Synthetic occupied capsule cross-section; this does not simulate a lidar observation.

    Use the shipped even-sized 5 m / 0.05 m window, including its half-cell centre.
    """
    cells = [0] * (size * size)
    cx, cy = distance * math.cos(heading), distance * math.sin(heading)
    for row in range(size):
        dy = (row - (size - 1) / 2.0) * resolution
        for column in range(size):
            dx = (column - (size - 1) / 2.0) * resolution
            if math.hypot(dx - cx, dy - cy) <= radius:
                cells[row * size + column] = G.LETHAL
    return cells, size, size, resolution


@pytest.mark.parametrize('heading', [0.0, math.pi / 4, math.pi / 2, math.pi, -math.pi / 2])
def test_capsule_observation_stops_and_lifting_resumes_after_delay(heading):
    """#240: supplied lethal cells must reach StopRule through the real static-map filter."""
    cells, width, height, resolution = _capsule_window(heading)
    static = [0] * len(cells)

    def is_static(dx, dy):
        return G.blocked_near(static, width, height, resolution, -2.5, -2.5, dx, dy)

    gap, anything, skipped = G.forward_scan(cells, width, height, resolution, heading, is_static=is_static)
    assert gap is not None and 0.0 < gap < G.STOP_M
    assert anything == gap and skipped == 0
    rule = G.StopRule()
    assert rule.update(gap, 0.0) == 'stop'
    assert rule.update(gap, 5.0) is None and rule.stopped
    lifted = G.forward_gap([0] * len(cells), width, height, resolution, heading, is_static=is_static)
    assert lifted is None
    assert rule.update(lifted, 5.5) is None and rule.stopped
    assert rule.update(lifted, 6.0) is None and rule.stopped
    assert rule.update(lifted, 6.5) == 'resume' and not rule.stopped


@pytest.mark.parametrize('heading', [0.0, math.pi / 4, math.pi / 2, math.pi, -math.pi / 2])
def test_same_occupied_shape_on_static_map_does_not_stop(heading):
    cells, width, height, resolution = _capsule_window(heading)

    def is_static(dx, dy):
        return G.blocked_near(cells, width, height, resolution, -2.5, -2.5, dx, dy)

    gap, anything, skipped = G.forward_scan(cells, width, height, resolution, heading, is_static=is_static)
    assert gap is None and anything is not None and skipped > 0
    rule = G.StopRule()
    for now in (0.0, 0.5, 1.0, 5.0):
        assert rule.update(gap, now) is None and not rule.stopped


def test_nearby_side_obstacle_does_not_prove_capsule_was_seen():
    """The reported 0.65 m clearance can stay identical with and without a forward capsule."""
    side, width, height, resolution = _grid_with([(0.0, 0.65)])
    with_capsule, _, _, _ = _grid_with([(0.0, 0.65), (0.8, 0.0)])
    assert G.free_space(side, width, height, resolution) == G.free_space(
        with_capsule, width, height, resolution)
    for cells, expected in ((side, None), (with_capsule, 'stop')):
        gap = G.forward_gap(cells, width, height, resolution, 0.0)
        assert G.StopRule().update(gap, 0.0) == expected


def test_off_path_dynamic_observations_do_not_trigger_stop():
    """Synthetic dummy/pedestrian samples outside the band; not campaign L3 evidence."""
    rule = G.StopRule()
    for now, lateral in enumerate((1.5, 1.0, 0.8, 0.65, -0.65, -0.8, -1.5)):
        cells, width, height, resolution = _grid_with([(0.8, lateral)])
        gap = G.forward_gap(cells, width, height, resolution, 0.0)
        assert rule.update(gap, float(now)) is None and not rule.stopped


@pytest.fixture(scope='module')
def hospital_static_grid():
    """Nav2 trinary 지도와 같은 행 방향·값. ROS/이미지 라이브러리 없이 실제 병원 지도를 읽는다."""
    maps = Path(__file__).resolve().parents[1] / 'config' / 'maps'
    metadata = yaml.safe_load((maps / 'hospital.yaml').read_text())
    magic, dimensions, maximum, pixels = (maps / metadata['image']).read_bytes().split(b'\n', 3)
    assert magic == b'P5' and maximum == b'255' and metadata['negate'] == 0
    width, height = map(int, dimensions.split())
    assert len(pixels) == width * height
    cells = []
    for row in range(height - 1, -1, -1):
        for pixel in pixels[row * width:(row + 1) * width]:
            occupancy = (255 - pixel) / 255.0
            cells.append(100 if occupancy > metadata['occupied_thresh'] else
                         0 if occupancy < metadata['free_thresh'] else -1)
    return cells, width, height, metadata['resolution'], *metadata['origin'][:2]


@pytest.mark.parametrize('transform', [(0.0, 0.0, 0.0), (-7.272, 4.784, 0.0),
                                       (-7.272, 4.784, math.pi / 2)])
def test_capsule_at_reported_hospital_position_survives_static_filter(hospital_static_grid, transform):
    """#240 5854548169 가설 반증: 실제 지도·도크 TF를 넣어도 빈 로비의 캡슐을 벽으로 빼면 안 된다.

    회전 TF는 추가 합성 사례이며 마스터의 실측 TF라고 주장하지 않는다.
    """
    tx, ty, yaw = transform
    c, s = math.cos(yaw), math.sin(yaw)
    # map에서 로봇 (3.54,4.21), 캡슐 중심 (4.54,4.21). 역변환으로 odom 격자 중심을 만든다.
    wx, wy = 3.54 - tx, 4.21 - ty
    centre = (c * wx + s * wy, -s * wx + c * wy)
    cells, width, height, resolution = _capsule_window(-yaw)
    # 노드가 쓰는 짝수 격자 원점→중심도 포함한다.
    origin = (centre[0] - width * resolution / 2, centre[1] - height * resolution / 2)
    centre = (origin[0] + width * resolution / 2, origin[1] + height * resolution / 2)
    predicate = G.StaticMapFilter(hospital_static_grid, centre, transform, -yaw)
    gap, anything, skipped = G.forward_scan(cells, width, height, resolution, -yaw, predicate)
    assert gap == anything and 0.0 < gap < G.STOP_M and skipped == 0
    assert predicate.nearest_skipped is None
    assert predicate.sample_text() == 'skipped_cell=none skipped_map=none'
    assert G.StopRule().update(gap, 177.5) == 'stop'


def test_real_hospital_wall_is_excluded_and_sample_identifies_map_cell(hospital_static_grid):
    cells, width, height, resolution, ox, oy = hospital_static_grid
    index = cells.index(100)
    row, column = divmod(index, width)
    x, y = ox + (column + 0.5) * resolution, oy + (row + 0.5) * resolution
    # 실제 지도 벽의 칸 중심이 몸체 앞끝에서 0.3 m인 합성 관측이다.
    transform = (-7.272, 4.784, 0.0)
    centre = (x - transform[0] - 0.8, y - transform[1])
    predicate = G.StaticMapFilter(hospital_static_grid, centre, transform, 0.0)
    local, w, h, r = _grid_with([(0.8, 0.0)])
    gap, anything, skipped = G.forward_scan(local, w, h, r, 0.0, predicate)
    assert gap is None and anything == pytest.approx(0.3) and skipped == 1
    assert predicate.nearest_skipped == pytest.approx((0.8, 0.8, 0.0, x, y))
    assert f'skipped_map=({x:.3f},{y:.3f})' in predicate.sample_text()
    assert G.StopRule().update(gap, 177.5) is None


def test_skipped_sample_uses_heading_and_resets_with_each_scan():
    static = ([100] * 400, 20, 20, 0.1, -1.0, -1.0)
    predicate = G.StaticMapFilter(static, (0.0, 0.0), (0.0, 0.0, 0.0), math.pi / 2)
    assert predicate(0.0, 0.9)
    assert predicate(0.0, 0.8)
    assert predicate(0.0, 1.0)
    assert predicate.nearest_skipped == pytest.approx((0.8, 0.0, 0.8, 0.0, 0.8))
    assert G.StaticMapFilter(static, (0.0, 0.0), (0.0, 0.0, 0.0), 0.0).nearest_skipped is None


def test_empty_static_map_keeps_a_cell_point_three_metres_ahead():
    local, w, h, r = _grid_with([(0.8, 0.0)])
    predicate = G.StaticMapFilter(([0] * (w * h), w, h, r, -2.525, -2.525),
                                 (0.0, 0.0), (0.0, 0.0, 0.0), 0.0)
    gap, anything, skipped = G.forward_scan(local, w, h, r, 0.0, predicate)
    assert gap == pytest.approx(0.3) and anything == gap and skipped == 0
    assert G.StopRule().update(gap, 0.0) == 'stop'


@pytest.mark.parametrize('value', [65, 99, 100])
def test_dynamic_cell_in_filter_input_reproduces_exclusion_and_reports_value(value):
    """작전 가설: 동적 셀이 섞인 입력이면 같은 local 관측도 제외된다. 현장 토픽 증거는 아니다."""
    local, w, h, r = _grid_with([(0.8, 0.0)])
    static = [value if cell == G.LETHAL else 0 for cell in local]
    predicate = G.StaticMapFilter((static, w, h, r, -2.525, -2.525),
                                 (0.0, 0.0), (0.0, 0.0, 0.0), 0.0)
    gap, anything, skipped = G.forward_scan(local, w, h, r, 0.0, predicate)
    assert gap is None and anything == pytest.approx(0.3) and skipped == 1
    assert G.StopRule().update(gap, 0.0) is None
    assert predicate.nearest_skipped_value == value
    assert f'static_value={value}' in predicate.sample_text()
    assert f'static_match=(66,50,{value})' in predicate.sample_text()


def test_free_centre_and_occupied_neighbour_are_distinguished_in_diagnostic():
    local, w, h, r = _grid_with([(0.8, 0.0)])
    static, _, _, _ = _grid_with([(0.9, 0.0)])
    predicate = G.StaticMapFilter((static, w, h, r, -2.525, -2.525),
                                 (0.0, 0.0), (0.0, 0.0, 0.0), 0.0)
    assert G.forward_scan(local, w, h, r, 0.0, predicate)[2] == 1
    assert predicate.nearest_skipped_value == 0
    assert 'static_value=0 static_match=(68,50,100)' in predicate.sample_text()


@pytest.mark.parametrize(('origin', 'robot_map', 'heading'), [
    ((8.450, -3.400), (3.678, 3.884), 20.0),   # #240 5854823464, sim165.350
    ((9.100, -3.150), (4.328, 4.134), 26.0),   # sim170.217, 이미 lifted 뒤인 자세
])
def test_fixed_dock_tf_maps_observed_moving_windows_to_capsule(
        hospital_static_grid, monkeypatch, origin, robot_map, heading):
    """고정 map←odom은 정상이다. 실제 원점에 합성 캡슐 셀을 넣으면 도크가 아닌 캡슐 자리를 조회한다.

    둘째 입력은 그 자세에서도 캡슐이 남아 있다는 반사실 시험이다. 실제 costmap 재생이 아니다.
    """
    size, resolution = 100, 0.05
    local = [0] * (size * size)
    for row in range(size):
        for col in range(size):
            x = robot_map[0] + (col - 49.5) * resolution
            y = robot_map[1] + (row - 49.5) * resolution
            if math.hypot(x - 4.54, y - 4.21) <= 0.2:
                local[row * size + col] = G.LETHAL
    queried = []
    real_lookup = G.blocking_cell_near

    def record_lookup(*args):
        queried.append(args[-2:])
        return real_lookup(*args)  # 실제 병원 지도 판정은 그대로 실행한다.

    monkeypatch.setattr(G, 'blocking_cell_near', record_lookup)
    centre = (origin[0] + 2.5, origin[1] + 2.5)
    predicate = G.StaticMapFilter(hospital_static_grid, centre, (-7.272, 4.784, 0.0),
                                 math.radians(heading))
    gap, anything, skipped = G.forward_scan(local, size, size, resolution, math.radians(heading), predicate)
    assert queried and all(math.hypot(x - 4.54, y - 4.21) <= 0.2 + 1e-9 for x, y in queried)
    assert gap == anything and gap < G.STOP_M and skipped == 0
    assert G.StopRule().update(gap, 0.0) == 'stop'
