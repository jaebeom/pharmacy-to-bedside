"""가까운 것이 있으면 느리게, 트인 복도에서는 빠르게. ROS 를 import 하지 않는다.

재범 9/23: "AMR 이동이 너무 느리다. 넓은 복도에서 0.8–1.0 m/s, 장애물·문 근처에서만 0.5 로."
9/23 낮에 최고 속도를 그냥 두 배로 올렸다가(#526) 고정물 touch 로 되돌렸다(#547). 그래서 **근접 감속이 먼저**다.

방식은 Nav2 의 속도 제한 창구다(`controller_server` 의 `speed_limit_topic`). 지역 코스트맵을 읽어
로봇 둘레의 여유를 재고, 그 여유로 **최고 속도의 몇 %** 를 쓸지 정해 보낸다. 컨트롤러 종류나 critic
가중치를 바꾸지 않는다 — 되돌리기 쉬운 자리 하나만 건드린다.

여유는 **지역 코스트맵 한가운데에서** 잰다. 지역 코스트맵은 로봇을 따라다니는 rolling window 라
한가운데가 곧 로봇이다. TF 를 보지 않아도 되고, 시험에서 격자 하나로 다 확인할 수 있다.

값(`NEAR_M`·`FAR_M`·`SLOW_PERCENT`)은 **우리가 고른 값이다. 잰 값이 아니다.**
`SLOW_PERCENT` 를 50 으로 둔 것은 최고 속도를 1.0 으로 올렸을 때 **가까운 곳에서는 지금 쓰던 0.5 가
그대로 나오게** 하려는 것이다. 즉 이 변경으로 빨라지는 구간은 여유가 `FAR_M` 이상인 곳뿐이다.
"""

import math

#: 이보다 가까우면 `SLOW_PERCENT`. 로봇 외접 반지름 0.64 m(#553)에 여유를 더한 값이다.
NEAR_M = 1.0
#: 이보다 멀면 100 %. 그 사이는 직선으로 잇는다.
FAR_M = 1.8
#: 가까운 곳에서 낼 **절대 속도**(m/s). 0.5 는 6/6 목표·touch 0 으로 잰 값이었다(#240).
#: 재범 9/29 "속도 올리기": 병원 복도·로비는 벽·테이블이 늘 1 m 안이라 대부분 이 속도로 달렸다
#: (`speed limit 50% (여유 0.53–0.68 m)`). 0.7 로 올린다 — **L3 미확인**(마스터 랩에서 touch 0 을 본다).
#: 비율이 아니라 속도로 둔다 — 최고 속도를 올릴 때 근접 속도가 따라 올라가지 않게 한다(9/23).
SLOW_SPEED_MPS = 0.7
#: `nav2_params.yaml` 의 `max_speed_xy`. 둘이 어긋나면 비율이 틀리므로 기동 줄에 m/s 로 찍는다.
MAX_SPEED_MPS = 1.0
#: 가까운 곳에서 쓸 비율(%). 위 두 값에서 나온다 — 직접 고치지 않는다.
SLOW_PERCENT = 100.0 * SLOW_SPEED_MPS / MAX_SPEED_MPS
#: 코스트맵 값이 이 이상이면 막힌 칸으로 본다.
#:
#: **`nav_msgs/OccupancyGrid` 의 값이지 nav2 내부 값이 아니다.** `Costmap2DPublisher` 가 내부 0–255 를
#: 0–100 으로 옮겨 낸다: 254(LETHAL_OBSTACLE)→100, 253(INSCRIBED_INFLATED_OBSTACLE)→99,
#: 255(NO_INFORMATION)→-1, 나머지는 1–98 로 눌린다. 253 을 문턱으로 두면 **어떤 칸도 걸리지 않아**
#:
#: **99 는 이번엔 반대로 너무 낮다.** 99 는 팽창 층이 칠한 "로봇 중심이 여기 오면 닿는다" 띠
#: (내접 반지름 0.45 m)다. 그 띠까지의 거리는 **벽까지의 거리가 아니라 벽 + 0.45 m** 다. 그래서
#: 폭 2.5 m 복도 한가운데서도 0.80 m 로 나와 늘 `NEAR_M`(1.0) 아래였다 — 0819f80 회차에서
#: `speed limit 50%` 가 29줄이고 100 % 로 올라간 적이 한 번도 없다(작전 9/23).
#: 100(LETHAL_OBSTACLE)만 막힌 칸으로 본다. 그러면 여유가 **실제 벽까지의 거리**이고, 로봇 반지름은
#: 아래 `NEAR_M` 이 이미 품고 있다(외접 0.64 m + 여유). 두 번 세지 않는다.
LETHAL = 100
#: 값이 없는 칸(-1)은 막힌 것으로 보지 않는다 — 지역 코스트맵 가장자리가 대부분 그렇다.
UNKNOWN = -1


def clearance(cells, width, height, resolution, lethal=LETHAL, radius_m=None):
    """격자 한가운데(=로봇)에서 가장 가까운 막힌 칸까지의 거리(m). 없으면 None.

    `cells` 는 `OccupancyGrid.data` 처럼 행 우선이다. `radius_m` 을 주면 그 거리까지만 본다(빠르다).
    """
    if width <= 0 or height <= 0 or resolution <= 0 or len(cells) < width * height:
        return None
    centre_x, centre_y = (width - 1) / 2.0, (height - 1) / 2.0
    limit = math.inf if radius_m is None else radius_m / resolution
    best = None
    for row in range(height):
        dy = row - centre_y
        if abs(dy) > limit:
            continue
        base = row * width
        for column in range(width):
            value = cells[base + column]
            if value == UNKNOWN or value < lethal:
                continue
            dx = column - centre_x
            distance = math.hypot(dx, dy)
            if distance <= limit and (best is None or distance < best):
                best = distance
    return None if best is None else best * resolution


#: `free_space` 가 돌려주는 뜻. 로그가 셋을 가른다.
MEASURED = "measured"   # far 안에 장애물이 있다 → 그 거리
OPEN = "open"           # far 안엔 없고 창 어딘가엔 있다 → 넓다(far 로 본다)
BLIND = "blind"         # 창 전체에 장애물 칸이 하나도 없다 → 모른다(느린 쪽)
STALE = "stale"         # 받다가 끊겼다 → 모른다(느린 쪽)

#: 마지막 코스트맵 뒤 이만큼(sim s) 지나면 끊긴 것으로 본다. 지역 코스트맵은 2 Hz 로 낸다 — 네 장을 놓친 셈이다.
#: 고른 값이다. 회차에서 끊김이 잦으면(`코스트맵 끊김` 경고) 다시 정한다.
STALE_AFTER_S = 2.0


def is_stale(now_s, last_s, stale_after_s=STALE_AFTER_S):
    """마지막 코스트맵이 너무 오래됐나. 한 번도 안 왔으면(last None) 끊김이 아니라 '아직 못 받음' 이다.

    **이게 없으면** 코스트맵이 끊긴 뒤에도 재발행 타이머가 마지막 제한을 1 s 마다 다시 낸다 — 마지막이 100 %
    였으면 장애물 층이 눈을 감은 채 최고 속도로 계속 간다(아스트라6 #613 N3). 모르면 느리게 간다는 원칙을
    "받다가 끊김" 에도 지킨다.
    """
    if last_s is None:
        return False
    return (now_s - last_s) > stale_after_s


def free_space(cells, width, height, resolution, lethal=LETHAL, far=FAR_M):
    """(여유 m 또는 None, 뜻). 감속기가 쓰는 판단이다.

    `clearance(..., radius_m=far)` 는 far 안에서만 찾고 없으면 None 이다. 그 None 을 그대로 "모름" 으로
    쓰면 **넓은 바닥이 모름으로 읽혀 느린 쪽**이 된다 — 138cbac 회차에서 여유 최대가 1.79 m, 100 % 가 2줄뿐
    이던 까닭이다(벽이 2.2 m 면 50 %, 1.2 m 면 64 %: 넓을수록 느렸다).

    그렇다고 None 을 늘 "넓다" 로 읽으면 장애물 층이 눈을 감았을 때(9/23 스캔 토픽) 빈 격자가 최고 속도가 된다.
    그래서 가른다: far 안엔 없어도 **창 어딘가에 장애물 칸이 있으면** 라이다가 보고 있다는 증거이므로 넓다(far),
    **창 전체가 비었으면** 모른다(None → 느린 쪽). 복도에서는 창(5 × 5 m) 안에 늘 벽이 있다.
    """
    # 깨진 격자(크기·해상도가 0 이하, data 가 선언보다 짧음)는 **먼저** 모름으로 둔다. `clearance` 도 None 을
    # 돌려주지만, 그 None 을 "far 안엔 없다" 로 읽고 창을 훑으면 깨진 데이터 속 장애물 값 하나로 OPEN(100 %)이
    # 된다 — 깨진 입력이 빠른 쪽으로 읽히는 것이다(커서 #631).
    if width <= 0 or height <= 0 or resolution <= 0 or len(cells) < width * height:
        return None, BLIND
    near = clearance(cells, width, height, resolution, lethal=lethal, radius_m=far)
    if near is not None:
        return near, MEASURED
    if any(value != UNKNOWN and value >= lethal for value in cells[:width * height]):
        return float(far), OPEN
    return None, BLIND


def limit_percent(free_m, near=NEAR_M, far=FAR_M, slow=SLOW_PERCENT):
    """여유(m) → 최고 속도의 몇 %. 못 재면(None) 느린 쪽으로 붙인다.

    `near` 이하면 `slow`, `far` 이상이면 100, 그 사이는 직선이다. **모르면 느리게** 간다 —
    코스트맵이 아직 안 왔거나 읽지 못한 회차가 9/23 의 #526 처럼 빨라지면 안 된다.
    """
    if far <= near:
        raise ValueError('far 는 near 보다 커야 한다')
    if free_m is None:
        return float(slow)
    if free_m <= near:
        return float(slow)
    if free_m >= far:
        return 100.0
    return float(slow) + (100.0 - float(slow)) * (free_m - near) / (far - near)


def changed(previous, percent, step=5.0):
    """직전에 보낸 값과 `step`(%) 넘게 다른가. 매 틱 같은 값을 다시 보내지 않는다."""
    return previous is None or abs(percent - previous) >= step


def describe_publishers(infos):
    """토픽 발행자 목록 → 왜 안 오는지 읽을 수 있는 한 문장.

    `Node.get_publishers_info_by_topic` 이 주는 것을 그대로 받는다(`node_name`·`node_namespace`·
    `qos_profile.reliability`·`.durability`). ROS 없이 시험하려고 순수 함수로 둔다.

    9/23 의 교훈이다: 코스트맵이 안 온 이유를 추측으로 골랐다가 틀렸다(`always_send_full_costmap` 은
    이미 켜져 있었다). 다음 회차는 **로그가 원인을 말하게** 한다.
    """
    if not infos:
        return '발행자가 없다 — local_costmap 이 아직 활성화 전이거나 네임스페이스가 어긋났다'
    parts = []
    for info in infos:
        namespace = str(getattr(info, 'node_namespace', '') or '')
        name = f"{namespace.rstrip('/')}/{getattr(info, 'node_name', '?')}"
        qos = getattr(info, 'qos_profile', None)
        parts.append(f"{name}({_qos_name(qos, 'reliability')}/{_qos_name(qos, 'durability')})")
    return f"발행자 {len(infos)}개: {', '.join(parts)} — 붙었는데 안 오면 발행 주기·QoS 를 본다"


def _qos_name(qos, field):
    """QoS 정책 이름 한 낱말. enum 이든 문자열이든 숫자든 읽히게 한다."""
    value = getattr(qos, field, None)
    if value is None:
        return '?'
    return str(getattr(value, 'name', value)).rsplit('.', 1)[-1]


def slow_percent(slow_mps, max_mps):
    """근접 속도(m/s)와 최고 속도(m/s) → 최고 속도의 몇 %.

    `nav2_params.yaml` 의 `max_speed_xy` 를 올릴 때 근접 속도가 같이 올라가지 않게 한다.
    9/23 낮의 #526 이 그 실패였다 — 최고 속도만 두 배로 올려 고정물 touch 가 났다(#547).
    """
    if max_mps <= 0.0:
        raise ValueError(f'max_speed_mps({max_mps}) 는 0 보다 커야 한다')
    if not 0.0 < slow_mps <= max_mps:
        raise ValueError(f'slow_speed_mps({slow_mps}) 는 0 과 max_speed_mps({max_mps}) 사이여야 한다')
    return 100.0 * slow_mps / max_mps


def looks_like_internal_costmap(cells):
    """이 격자가 nav2 **내부** 값(0–255)처럼 보이는가. 그러면 문턱이 틀린 것이다.

    `OccupancyGrid` 는 -1..100 만 쓴다. 100 을 넘는 값이 있으면 우리가 읽는 토픽이 내부 격자이거나
    변환이 다른 것이다 — 조용히 늘 100 % 를 내는 대신 그 사실을 말한다(#610).
    """
    return any(cell > 100 for cell in cells)


# ---- 정지 규칙(작전 9/25, 1변수 exp/gov-stop) ---------------------------------------------------------------
#
# 회차107(6e6569b, 촬영 구성 10건, 비전 분석): 라이다가 경로 위에 선 더미를 봤는데(감속 54 %) 하한이 50 % 라 AMR 이
# 그대로 밀고 갔다. 재계획도 없었다. 그래서 **진행 방향 앞, 몸체 폭 띠 안에 지도에 없는 장애물**이 가까우면 멈춘다.
# 지도에 있는 것(벽·테이블·문틀)은 빼므로 문 앞·정차 접근은 기존 근접 감속 그대로다.

#: 몸체 앞끝에서 이보다 가까우면 멈춘다(m). 작전 카드 값(고른 값).
STOP_M = 0.6
#: 멈춘 뒤 이보다 멀어진 채로 `RESUME_DELAY_S` 가 지나면 다시 간다(m, s). 히스테리시스·지연은 작전 카드 값.
RESUME_M = 0.9
RESUME_DELAY_S = 1.0
#: **Nav2 에서 speed_limit 0 은 "제한 없음"이다**(nav2_costmap_2d NO_SPEED_LIMIT = 0.0). 0 % 를 보내면 최고 속도로
#: 되돌아간다. 그래서 멈춤은 1 %(0.01 m/s)로 낸다.
STOP_PERCENT = 1.0
#: 몸체 반길이(0.466 + 받침 넘침 0.034)·반폭(0.397 + 여유)(m). 전방 띠의 치수다.
BODY_HALF_LENGTH = 0.5
BODY_HALF_WIDTH = 0.42
#: 이보다 느리면 진행 방향을 새로 잡지 않고 마지막 방향을 쓴다(m/s). 멈춘 동안에도 같은 앞을 본다.
MOVING_MPS = 0.03
#: 지역 코스트맵 칸이 정적 지도의 막힌 칸에서 이 안이면 "지도에 있는 것" 으로 본다(m). 지도 칸이 실물보다 약 5 cm 크다.
STATIC_TOLERANCE_M = 0.15


def forward_scan(cells, width, height, resolution, heading, is_static=None, lethal=LETHAL,
                 half_length=BODY_HALF_LENGTH, half_width=BODY_HALF_WIDTH, reach=RESUME_M):
    """전방 띠 훑기 → (지도에 없는 것까지 gap, 지도에 있는 것 포함 gap, 지도 칸이라 뺀 칸 수).

    gap 은 몸체 앞끝에서 잰 m, `reach` 안에 없으면 None. 셋째 값은 "보였는데 걸렀다" 를 가른다(9/27 block-path).
    """
    if heading is None or width <= 0 or height <= 0 or resolution <= 0 or len(cells) < width * height:
        return None, None, 0
    c, s = math.cos(heading), math.sin(heading)
    centre_x, centre_y = (width - 1) / 2.0, (height - 1) / 2.0
    dynamic = anything = None
    skipped = 0
    for row in range(height):
        base = row * width
        dy = (row - centre_y) * resolution
        for column in range(width):
            value = cells[base + column]
            if value == UNKNOWN or value < lethal:
                continue
            dx = (column - centre_x) * resolution
            along = dx * c + dy * s
            gap = along - half_length
            if along <= 0.0 or gap > reach or abs(-dx * s + dy * c) > half_width:
                continue
            if anything is None or gap < anything:
                anything = gap
            if is_static is not None and is_static(dx, dy):
                skipped += 1
                continue
            if dynamic is None or gap < dynamic:
                dynamic = gap
    return (None if dynamic is None else max(0.0, dynamic),
            None if anything is None else max(0.0, anything), skipped)


def forward_gap(cells, width, height, resolution, heading, is_static=None, lethal=LETHAL,
                half_length=BODY_HALF_LENGTH, half_width=BODY_HALF_WIDTH, reach=RESUME_M):
    """진행 방향(`heading`, 격자 프레임 rad) 앞, 몸체 폭 띠 안에서 가장 가까운 막힌 칸까지 **몸체 앞끝에서** 잰 거리(m).

    `reach` 안에 없으면 None. `is_static(dx, dy)`(로봇 기준 m)가 True 인 칸은 지도에 있는 것이라 뺀다. 깨진 격자는 None.
    """
    return forward_scan(cells, width, height, resolution, heading, is_static, lethal, half_length, half_width,
                        reach)[0]


def motion_heading(vx, vy, yaw, previous=None, moving=MOVING_MPS):
    """몸체 속도(base_link 기준)와 격자 프레임 yaw → 격자 프레임 진행 방향(rad). 느리면 `previous` 를 쓴다.

    Ridgeback 은 옆으로도 간다 — 몸체가 보는 방향이 아니라 **움직이는 방향**이 앞이다.
    """
    if math.hypot(vx, vy) < moving:
        return previous
    return yaw + math.atan2(vy, vx)


class StopRule:
    """정지 규칙의 상태. `update` 가 "stop"·"resume"·None 을 돌려준다(로그용)."""

    def __init__(self, stop_m=STOP_M, resume_m=RESUME_M, delay_s=RESUME_DELAY_S):
        if resume_m <= stop_m:
            raise ValueError('resume_m 은 stop_m 보다 커야 한다')
        self.stop_m, self.resume_m, self.delay_s = stop_m, resume_m, delay_s
        self.stopped = False
        self._clear_since = None

    def update(self, gap, now_s):
        if gap is not None and gap < self.stop_m:
            self._clear_since = None
            if not self.stopped:
                self.stopped = True
                return "stop"
            return None
        if not self.stopped:
            return None
        if gap is None or gap > self.resume_m:
            if self._clear_since is None:
                self._clear_since = now_s
            if now_s - self._clear_since >= self.delay_s:
                self.stopped = False
                self._clear_since = None
                return "resume"
        else:
            self._clear_since = None
        return None


class StaticMapFilter:
    """기존 노드의 좌표 변환·지도 판정을 ROS 없이 시험하고 제외 좌표를 보존한다.

    grid: (data, width, height, resolution, origin_x, origin_y).
    centre: 지역 격자 중심(코스트맵 프레임). transform: map ← 코스트맵 (x, y, yaw).
    지도·지역 격자의 origin 회전은 기존과 같이 0인 구성을 전제한다.
    한 번의 forward_scan마다 새 인스턴스를 써서 다른 시각의 표본이 섞이지 않게 한다.
    """

    def __init__(self, grid, centre, transform, heading):
        self.grid, self.centre, self.transform = grid, centre, transform
        self._c, self._s = math.cos(transform[2]), math.sin(transform[2])
        self._direction = None if heading is None else (math.cos(heading), math.sin(heading))
        self.nearest_skipped = None
        self.nearest_skipped_value = None
        self.nearest_skipped_match = None

    def __call__(self, dx, dy):
        px, py = self.centre[0] + dx, self.centre[1] + dy
        x = self.transform[0] + self._c * px - self._s * py
        y = self.transform[1] + self._s * px + self._c * py
        match = blocking_cell_near(*self.grid, x, y)
        if match is not None and self._direction is not None:
            along = dx * self._direction[0] + dy * self._direction[1]
            if self.nearest_skipped is None or along < self.nearest_skipped[0]:
                self.nearest_skipped = (along, dx, dy, x, y)
                self.nearest_skipped_match = match
                cells, width, height, resolution, ox, oy = self.grid
                col, row = math.floor((x - ox) / resolution), math.floor((y - oy) / resolution)
                self.nearest_skipped_value = (cells[row * width + col]
                                              if 0 <= col < width and 0 <= row < height else None)
        return match is not None

    def sample_text(self):
        """판정에 실제 쓴 가장 가까운 제외 칸. 없는 표본을 (0, 0)으로 오인하지 않게 한다."""
        if self.nearest_skipped is None:
            return 'skipped_cell=none skipped_map=none'
        along, dx, dy, x, y = self.nearest_skipped
        col, row, value = self.nearest_skipped_match
        own_value = 'outside' if self.nearest_skipped_value is None else str(self.nearest_skipped_value)
        return (f'skipped_cell=({dx:.3f},{dy:.3f}) skipped_map=({x:.3f},{y:.3f}) '
                f'skipped_gap={max(0.0, along - BODY_HALF_LENGTH):.3f} '
                f'static_value={own_value} static_match=({col},{row},{value})')


def blocked_near(grid_cells, width, height, resolution, origin_x, origin_y, x, y, tolerance=STATIC_TOLERANCE_M):
    """정적 지도(OccupancyGrid, 원점 회전 없음)에서 (x, y) 둘레 `tolerance` 안에 막힌 칸(≥ 65)이 있나.

    지도 밖은 False.
    """
    return blocking_cell_near(grid_cells, width, height, resolution, origin_x, origin_y, x, y, tolerance) is not None


def blocking_cell_near(grid_cells, width, height, resolution, origin_x, origin_y, x, y,
                       tolerance=STATIC_TOLERANCE_M):
    """기존 탐색 순서의 첫 ≥65 칸 (column, row, value), 없으면 None. 판정 근거를 로그에 남긴다.

    중심 칸이 0이어도 0.15 m 이웃 때문에 제외될 수 있다. 둘을 혼동하지 않도록 일치 칸도 보존한다.
    """
    r = int(math.ceil(tolerance / resolution))
    cx = int(math.floor((x - origin_x) / resolution))
    cy = int(math.floor((y - origin_y) / resolution))
    for row in range(cy - r, cy + r + 1):
        if row < 0 or row >= height:
            continue
        for column in range(cx - r, cx + r + 1):
            if 0 <= column < width and grid_cells[row * width + column] >= 65:
                return column, row, grid_cells[row * width + column]
    return None


def stop_rule_text(enabled, map_ready, heading, gap, stopped):
    """현황 줄에 붙는 정지 규칙 상태 한 조각. 안 걸렸을 때 **왜** 인지 로그로 가른다.

    9/27 block-path 확인 랩(a4b1a4e, #240 5853890018·5853906923): 캡슐 앞에서 `governor stop` 이 0줄이었는데, 규칙이
    꺼졌는지·방향을 몰랐는지·앞이 비어 보였는지 로그로 가를 수 없었다.
    """
    if not enabled:
        return '정지 규칙 끔(인자)'
    if not map_ready:
        return '정지 규칙 대기(정적 지도·TF 없음)'
    if heading is None:
        return '정지 규칙 대기(아직 안 움직임)'
    state = '정지 중' if stopped else '감시'
    ahead = '앞 비었음' if gap is None else f'앞 {gap:.2f} m'
    return f'정지 규칙 {state}, {ahead}'


def status_line(percent, max_mps, free_text, seen, stop_text=None):
    """10 s 현황 줄. **괄호 안 모양은 바꾸지 않는다** — tools/hospital_full_metrics.py 의 SPEED_LIMIT 정규식이
    `(여유 …, 받은 코스트맵 N장)` 로 닫는 괄호까지 고정해 판정선 (b) G1·G2 지표를 뽑는다(마1검증 9/27 e88b8bd 리뷰).
    정지 규칙 상태는 괄호 **밖**에 붙인다.
    """
    line = f'speed limit {percent:.0f}%={percent * max_mps / 100.0:.2f} m/s (여유 {free_text}, 받은 코스트맵 {seen}장)'
    return line if not stop_text else f'{line} {stop_text}'
