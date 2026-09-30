"""Belt, end stop sensor and dispense rules for the pharmacy stage. No Isaac imports.

Contract v1 2.1 /pharmacy/dispense and /pharmacy/belt, 2.6 (isaac emits DISPENSED, POUCH_AT_END), 7 (20 s sim
from Dispense to at_end), scenario 4 step 1 (one pouch on the belt at a time).
"""

import math
from collections import namedtuple

from .conveyor_end import item_bounds, receiver_status, terminal_status

BELT_OCCUPIED = "belt_occupied"
UNKNOWN_ORDER = "unknown_order"
NOT_READY = "not_ready"
# Rejection when every pre-built pouch is out (on the belt or on the deck). Added by the stage on 9/17 so it refuses
# instead of stopping; contract 2.1 lists it since 9/24 (hospital ten-order run hit it at the ninth order).
POOL_EXHAUSTED = "pool_exhausted"
DISPENSE_REJECTIONS = (BELT_OCCUPIED, UNKNOWN_ORDER, NOT_READY, POOL_EXHAUSTED)
FIRST_EPOCH = 1  # contract 4: epochs start at 1; 0 reaches /events as stale

DISPENSED = "DISPENSED"
POUCH_AT_END = "POUCH_AT_END"
ROBOT_ID = "dispenser"


# Measured belt speed check (9/17 master02: same commit and arguments, the pouch ran at 0.24 m/s in some runs and 0.15
# in others with --belt-speed 0.15). Sampled once per pouch while it is in the middle of the belt, past the spawn
# acceleration and before the end zone.
SPEED_WINDOW = (0.40, 0.75)  # fractions of the belt length
SPEED_TOLERANCE = 0.20  # |measured / requested - 1| above this is a mismatch


def speed_sample_due(frame_x, length, window=SPEED_WINDOW):
    return window[0] * length <= frame_x <= window[1] * length


def speed_along(velocity_xyz, yaw):
    """Velocity component along the belt direction (world yaw)."""
    return velocity_xyz[0] * math.cos(yaw) + velocity_xyz[1] * math.sin(yaw)


def speed_mismatch(measured, requested, tolerance=SPEED_TOLERANCE):
    """(ratio, mismatch). A stopped belt (requested 0) has no ratio."""
    if requested <= 0:
        return float("nan"), False
    ratio = measured / requested
    return ratio, abs(ratio - 1.0) > tolerance


def speed_mismatch_error(measured, requested, ratio):
    """ERROR log text for a belt that runs at the wrong speed (no automatic correction: the cause is not known)."""
    return (f"ERROR 벨트 속도 이상: 실측 {measured:.2f} / 설정 {requested:.2f} (ratio {ratio:.1f}). "
            "이 실행의 시간 지표는 쓰지 말 것. 재기동 권장")


def at_end_detail(ratio, mismatch):
    """POUCH_AT_END detail: a memo naming a wrong belt speed so run records can be filtered; empty when normal.

    The measurement is taken mid-belt, after DISPENSED was already sent, so it rides on POUCH_AT_END."""
    return f"belt_ratio={ratio:.3f}" if mismatch else ""


def belt_frame(point, start_xyz, yaw):
    """(along, lateral, up) of a world point in the belt frame: origin at the start, x along the belt."""
    dx, dy, dz = (point[0] - start_xyz[0], point[1] - start_xyz[1], point[2] - start_xyz[2])
    cos_yaw, sin_yaw = math.cos(yaw), math.sin(yaw)
    return (cos_yaw * dx + sin_yaw * dy, -sin_yaw * dx + cos_yaw * dy, dz)


class BeltModel:
    """Belt state that the Isaac script drives with pouch observations.

    Geometry is in the belt frame: the belt top surface spans along 0..length, lateral +-width/2, and its top is
    at up = 0 (start_xyz is the top-surface point at the start). The end zone is the last end_zone_length."""

    #: The stage samples the belt speed mid-belt (speed_sample_due on frame[0]); RouteBeltModel has no such axis.
    speed_sampling = True

    def __init__(self, length, width, end_zone_length, settle_speed=0.01, settle_time_s=0.3, at_end_timeout_s=20.0,
                 on_belt_height=0.05, fail_closed=False):
        """fail_closed (opt-in, contract 11.1 proposal): a pouch that leaves the belt or loses its pose keeps the belt
        occupied until reset instead of freeing it."""
        if not (length > 0 and width > 0 and 0 < end_zone_length <= length):
            raise ValueError("need length > 0, width > 0 and 0 < end_zone_length <= length")
        self.length = length
        self.width = width
        self.end_zone_length = end_zone_length
        self.settle_speed = settle_speed
        self.settle_time_s = settle_time_s
        self.at_end_timeout_s = at_end_timeout_s
        self.on_belt_height = on_belt_height
        self.fail_closed = fail_closed
        self.reset()

    def reset(self):
        self.occupied = False
        self.at_end = False
        self.order_id = ""
        self.request_id = ""
        self.running = False
        self.dispensed_at = None
        self.slow_since = None
        self.timeout_reported = False
        self.lost = False  # fail_closed only: the pouch was lost; hold until reset

    def decide_dispense(self, order_id, ready, known_order, pouch_available=True):
        """Message for a Dispense call: '' when accepted, else one of DISPENSE_REJECTIONS or POOL_EXHAUSTED."""
        if not ready:
            return NOT_READY
        if not known_order:
            return UNKNOWN_ORDER
        if self.occupied:
            return BELT_OCCUPIED
        if not pouch_available:
            return POOL_EXHAUSTED
        return ""

    def is_resend(self, request_id, order_id):
        """A Dispense resend for the pouch still tracked on the belt (contract 11.2): answer accepted again, without a
        new spawn or DISPENSED. Not for a lost pouch (fail_closed keeps it occupied) and not after release."""
        return self.occupied and not self.lost and (request_id, order_id) == (self.request_id, self.order_id)

    def accept(self, request_id, order_id, now_s):
        self.occupied = True
        self.at_end = False
        self.order_id = order_id
        self.request_id = request_id
        self.running = True
        self.dispensed_at = now_s
        self.slow_since = None
        self.timeout_reported = False
        return [DISPENSED]

    def on_belt(self, frame_point):
        along, lateral, up = frame_point
        return (-0.02 <= along <= self.length + 0.02 and abs(lateral) <= self.width / 2.0 + 0.02
                and -0.02 <= up <= self.on_belt_height)

    def in_end_zone(self, frame_point):
        return frame_point[0] >= self.length - self.end_zone_length

    def observe(self, frame_point, speed, now_s):
        """Update with the pouch position (belt frame) and speed. Returns events and notes as lists of str.

        speed None = no sample received: it resets the settle timer instead of counting as stopped (contract 11.1).

        Events: POUCH_AT_END once per pouch. Notes (log only): 'stop_belt', 'pouch_left_belt', 'pouch_lost',
        'at_end_timeout'."""
        events, notes = [], []
        if not self.occupied or self.lost:
            return events, notes
        if (frame_point is None or not self.on_belt(frame_point)) and self.fail_closed:
            notes.append("pouch_lost")  # occupied and order_id stay; no pick on a pouch that is not there
            self.lost = True
            self.at_end = False
            self.running = False
            self.slow_since = None
            return events, notes
        if frame_point is None or not self.on_belt(frame_point):
            notes.append("pouch_left_belt")
            self.occupied = False
            self.at_end = False
            self.order_id = ""
            self.running = False
            self.slow_since = None
            return events, notes
        if self.running and self.in_end_zone(frame_point):
            self.running = False
            notes.append("stop_belt")
        if not self.running and not self.at_end and self.in_end_zone(frame_point):
            if speed is not None and speed <= self.settle_speed:
                if self.slow_since is None:
                    self.slow_since = now_s
                if now_s - self.slow_since >= self.settle_time_s:
                    self.at_end = True
                    events.append(POUCH_AT_END)
            else:
                self.slow_since = None
        elif not self.at_end:
            self.slow_since = None      # 끝 구역을 벗어나면 "끊김 없이" 가 깨진다. 다시 들어오면 새로 잰다
        if (not self.at_end and not self.timeout_reported and self.dispensed_at is not None
                and now_s - self.dispensed_at > self.at_end_timeout_s):
            self.timeout_reported = True
            notes.append("at_end_timeout")
        return events, notes

    def observe_held(self, frame_point):
        """The real arm holds the belt pouch. True (and the belt is freed) only once the pouch is outside the belt
        volume; while it is still over the belt, or its pose is unknown, the belt stays occupied (contract 11.1 a).

        With the stage's virtual attach the pose follows the TCP by teleport, so this is a geometric check of the
        attach, not an observed physical lift: mode sim_sensor."""
        if not self.occupied or self.lost or frame_point is None or self.on_belt(frame_point):
            return False
        self.reset()
        return True

    def state(self):
        return {"occupied": self.occupied, "at_end": self.at_end, "order_id": self.order_id}


# --- 여러 트랙 경로 벨트(병원 전체 preset, #527 H1) --------------------------------
# 병원 씬은 자체 컨베이어(트랙 여럿)로 봉투를 창구 A1 끝 롤러까지 보낸다. 직선 하나가 아니라서 belt_frame 의
# (along, lateral, up) 이 없다. 그래서 봉투의 **월드 자세**를 그대로 받는다. 관측 규칙(observe·observe_held·
# 점유·fail_closed)은 BeltModel 것을 그대로 쓰고, on_belt 와 in_end_zone 만 바꾼다.

#: RouteBeltModel 이 받는 봉투 자세. 위치(x, y, z)는 봉투 중심, 자세는 Isaac 순서 (w, x, y, z) 다.
#: 숫자만 담은 튜플이라 스테이지 로그(`frame=...`, common.format_values)가 그대로 찍힌다.
RoutePoint = namedtuple("RoutePoint", ("x", "y", "z", "qw", "qx", "qy", "qz"))


def route_point(position, orientation=(1.0, 0.0, 0.0, 0.0)):
    """봉투 월드 자세 -> RoutePoint. 자세를 모르면 똑바로 놓인 것으로 본다."""
    return RoutePoint(*(float(v) for v in position), *(float(q) for q in orientation))


def _check_box(box, what):
    lo, hi = box["min"], box["max"]
    if len(lo) != 3 or len(hi) != 3 or not all(math.isfinite(v) for v in (*lo, *hi)):
        raise ValueError(f"{what}: min·max 가 유한한 xyz 가 아니다")
    if not all(a < b for a, b in zip(lo, hi, strict=True)):
        raise ValueError(f"{what}: min < max 가 아니다")


class RouteBeltModel(BeltModel):
    """여러 트랙으로 된 컨베이어 경로의 봉투 상태. BeltModel 과 같은 필드·메서드를 낸다.

    tracks: 트랙 윗면 AABB 목록 [{"min": xyz, "max": xyz}]. terminal: 끝 롤러 윗면 AABB(같은 모양).
    on_belt  = 봉투 중심 xy 가 트랙(또는 끝 롤러) 하나의 xy 안(xy_margin 여유)이고,
               z_band "top"(기본): 봉투 바닥이 그 트랙 윗면에서 -0.02 ~ on_belt_height 사이다(BeltModel 과 같은 띠).
               z_band "span": 봉투 바닥이 그 트랙 상자 아래면 -0.02 ~ 윗면 + on_belt_height 사이다. 경사로처럼
               상자가 높이로 긴 트랙에서 "윗면" 이 봉투 자리가 아닐 때 쓴다(병원 씬, #527 H2).
    in_end_zone = conveyor_end.terminal_status(...)['reached'] — 봉투 전체가 끝 롤러 위이고 앞 끝이 출구에서
               edge_margin 안이다. 값은 전부 회차 입력이다(계약 합격선이 아니다).
    속도 표본(speed_sample_due)은 없다: speed_sampling = False. 스테이지가 이것을 보고 건너뛴다.
    """

    speed_sampling = False

    def __init__(self, tracks, terminal, direction, pouch_size, edge_margin=0.03, height_tolerance=0.02,
                 settle_speed=0.01, settle_time_s=0.3, at_end_timeout_s=20.0, on_belt_height=0.05,
                 fail_closed=False, xy_margin=0.02, z_band="top", receiver=None):
        tracks = [{"min": list(t["min"]), "max": list(t["max"])} for t in tracks]
        if not tracks:
            raise ValueError("트랙이 하나 이상 있어야 한다")
        for i, track in enumerate(tracks):
            _check_box(track, f"tracks[{i}]")
        terminal = {"min": list(terminal["min"]), "max": list(terminal["max"])}
        _check_box(terminal, "terminal")
        if len(pouch_size) != 3 or not all(math.isfinite(v) and v > 0 for v in pouch_size):
            raise ValueError("pouch_size 는 양수 xyz 다")
        # 방향·공차 검사는 terminal_status 에 맡긴다. 잘못된 값은 여기서 바로 ValueError 로 멈춘다.
        terminal_status(((terminal["min"][0] + terminal["max"][0]) / 2.0,
                         (terminal["min"][1] + terminal["max"][1]) / 2.0, terminal["max"][2] + pouch_size[2] / 2.0),
                        (1.0, 0.0, 0.0, 0.0), pouch_size, terminal, direction, edge_margin, height_tolerance)
        self.tracks = tracks
        self.receiver = receiver
        if receiver is not None:
            _check_box(receiver, "receiver")
            self.tracks.append(receiver)
        self.terminal = terminal
        self.direction = direction
        self.pouch_size = tuple(float(v) for v in pouch_size)
        self.edge_margin = edge_margin
        self.height_tolerance = height_tolerance
        if z_band not in ("top", "span"):
            raise ValueError("z_band 는 top 또는 span 이다")
        self.xy_margin = xy_margin
        self.z_band = z_band
        self.settle_speed = settle_speed
        self.settle_time_s = settle_time_s
        self.at_end_timeout_s = at_end_timeout_s
        self.on_belt_height = on_belt_height
        self.fail_closed = fail_closed
        self.reset()

    def _split(self, frame_point):
        point = RoutePoint(*frame_point) if not isinstance(frame_point, RoutePoint) else frame_point
        return (point.x, point.y, point.z), (point.qw, point.qx, point.qy, point.qz)

    def on_belt(self, frame_point):
        position, orientation = self._split(frame_point)
        bottom = item_bounds(position, orientation, self.pouch_size)[0][2]
        m = self.xy_margin
        for box in (*self.tracks, self.terminal):
            lo, hi = box["min"], box["max"]
            if not (lo[0] - m <= position[0] <= hi[0] + m and lo[1] - m <= position[1] <= hi[1] + m):
                continue
            if self.z_band == "span":
                if lo[2] - 0.02 <= bottom <= hi[2] + self.on_belt_height:
                    return True
            elif -0.02 <= bottom - hi[2] <= self.on_belt_height:
                return True
        return False

    def end_status(self, frame_point):
        """terminal_status 전체(로그용): reached·supported_xy·edge_gap_m·bottom_gap_m."""
        position, orientation = self._split(frame_point)
        if self.receiver is not None:
            status = receiver_status(position, orientation, self.pouch_size,
                                     self.receiver, self.height_tolerance)
            lo, hi = item_bounds(position, orientation, self.pouch_size)
            axis = 0 if self.direction[1] == "x" else 1
            gap = (lo[axis] - self.terminal["max"][axis] if self.direction[0] == "+"
                   else self.terminal["min"][axis] - hi[axis])
            status["edge_gap_m"] = gap
            # 탁자는 롤러 끝 아래로 겹친다. 상판 지지·높이·평탄성으로 도착을
            # 판단하고, 롤러 경계와의 XY 겹침은 진단값으로만 남긴다.
            return status
        return terminal_status(position, orientation, self.pouch_size, self.terminal, self.direction,
                               self.edge_margin, self.height_tolerance)

    def in_end_zone(self, frame_point):
        return self.end_status(frame_point)["reached"]
