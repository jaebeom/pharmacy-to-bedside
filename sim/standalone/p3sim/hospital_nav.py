"""병원 씬(hospital_navigationv1)의 zones·routes 를 앵커 JSON 과 occupancy map 에서 만든다. 표준 라이브러리만 쓴다.

단일 출처:
- 앵커: `sim/scenes/hospital_navigationv1.anchors.json` (`extract_hospital_anchors.py` 가 USD 에서 뽑는다)
- 지도: `src/rokey_p3_navigation/config/maps/hospital.{pgm,yaml}` (`usd_occupancy_map.py` 가 USD 에서 만든다)

만드는 것: `zones.hospital.yaml`(계약 3절 형식)·`routes.hospital.yaml`(주행 routes.py 스키마). 다시 만들기:
    python3 sim/standalone/hospital_nav_files.py --zones > src/rokey_p3_description/config/zones.hospital.yaml
    python3 sim/standalone/hospital_nav_files.py --routes > src/rokey_p3_description/config/routes.hospital.yaml

**정차 자세는 빈월드에서 연속 3바퀴로 검증된 상대 기하(팔 밑동 ↔ 목표)를 그대로 옮긴 것이다 — 병원 씬 높이로
팔 도달을 다시 푼 것이 아니다(IK 미확인).** 몸체가 지도의 막힌 칸과 겹치지 않는 것만 확인했다.

아직 사람이 정하지 않은 것(기본값으로 두고 파일 머리에 적는다):
- ① 병상 이름: PDF D1–D4 → bed_a1–a4, D5–D10 → bed_b1–b6
- ② 적재(load)는 창구 1(A1) 자리와 같다 — 도크 A1–A4 = dock_1–dock_4
- ③ 병실 입구 C1·C2 는 zone 이 아니라 경로의 경유점이다

작전이 정한 것(9/23): 병상마다 병실(room: C1·C2, PDF P3_Map 의 병실)·병동(ward: W1 하나)·PDF 번호(label: D1–D10)를
zones 에 싣는다. 웹이 이것으로 병상을 병실별로 묶고, 병실 묶음(mode 2)에 다른 병실이 섞이면 미리 거부한다.
"""
import heapq
import json
import math
import os

from . import amr_base, patient_plates

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
ANCHORS_PATH = os.path.join(REPO, "sim", "scenes", "hospital_navigationv1.anchors.json")
MAP_YAML_PATH = os.path.join(REPO, "src", "rokey_p3_navigation", "config", "maps", "hospital.yaml")

#: 몸체 치수(#408 6.5절 실측 bbox 0.93251 x 0.79320). 받침 판이 뒤끝에서 0.034 넘는다(amr_base.RISER_SIZE 주석).
BODY_LENGTH = 0.9325
BODY_WIDTH = 0.7932
RISER_OVERHANG = 0.034
#: 정차 자세에서 몸체↔고정물 최소 틈. 주행 도착 오차 0.02 + 여유(빈월드 접안 규칙과 같은 뜻).
STOP_CLEARANCE = 0.05
#: 경로 계획에서 몸체 중심이 장애물에서 떨어져야 하는 거리. waypoints 추종은 중간에 yaw 를 바꾸지 않으므로
#: 몸체가 **긴 쪽으로 문을 가로질러** 지날 수 있다 — 반길이 0.466 + 뒤끝 받침 넘침 0.034 = 0.50 이 최소다.
#: 9/23 병원 L3: 0.50 으로 계획했더니 C2 문에서 여유가 정확히 0 이었고 팔 받침(ArmRiser)이 문틀에 닿았다
#: (dock_3 → bed_b1, yaw −90°). 추종 오차 0.02 + 여유 0.04 를 더해 0.56 이다 — 문(가운데 여유 0.60)은
#: 가운데 ±0.04 로만 지나게 된다.
PATH_RADIUS = BODY_LENGTH / 2 + RISER_OVERHANG + 0.06
#: 제자리 회전에 필요한 반경(몸체 모서리 + 받침 넘침). 접근점(`approach_point`)을 고를 때 쓴다.
TURN_RADIUS = math.hypot(BODY_LENGTH / 2 + RISER_OVERHANG, BODY_WIDTH / 2)
#: 팔 밑동의 몸체 로컬 x(뒤끝). amr_base 가 단일 출처다.
ARM_X = amr_base.ARM_MOUNT_LOCAL[0]
#: 적재: 목표가 팔 밑동 기준 로컬 (-0.45, +0.05) — 빈월드 LOAD_OFFSET(0.45 + 0.35, -0.05) 의 뜻을 뒤집은 것.
LOAD_TARGET_LOCAL = (-0.45, 0.05)
#: 봉투가 **실제로 서는 자리**. 참조 탐침 02(#240, `terminal_edge_settled`)에서 잰 정착 위치다.
#: `pharmacy.belt_end`(끝 롤러 윗면의 출구 쪽 끝 중심)보다 팔에서 0.12 m 멀다 — 봉투는 가장자리까지 가지 않고
#: 그 안쪽에 선다. 참값 센서든 카메라든 팔은 **검출된 봉투**를 노리므로, 적재 정차는 이 점을 기준으로 잡는다.
#: 9/23 회차에서 `belt_end` 기준으로 잡았다가 수평이 0.779 가 되어 정차 오차가 여유를 먹으면
#: `IK 실패. 위치오차 0.0018 m` 로 깨졌다(깨지는 경계는 수평 0.88–0.93, 오프라인 측정).
A1_SETTLED_XY = (-8.295, 5.036)
#: 병원 적재(`load`): 봉투(A1_SETTLED_XY)가 팔 밑동 기준 **왼쪽(+y)** 0.45 에 오게 선다(재범 9/23:
#: 집기·내려놓기는 차체 좌우가 1순위, 앞뒤는 후순위). 0.45 는 빈월드 벨트 픽의 밑동↔목표 수평 거리(LOAD_OFFSET 의
#: 0.45, 아래 REACH_MAX_LOAD 주석)를 그대로 옆으로 돌린 것이다. 오른쪽(−y)은 트레이라 쓰지 않는다.
#: `dock_1` 은 출발·대기 자리라 그대로 둔다(demo_v2 P3_AMR_START·런북이 그 자리를 쓴다).
LOAD_SIDE_TARGET_LOCAL = (0.0, 0.45)
#: 보관함: 목표가 팔 밑동 기준 로컬 왼쪽(+y) 0.65 — 빈월드 병상 자세(팔 밑동이 보관함 x 에, 보관함은 옆)와 같은 뜻.
#: 오른쪽(−y)은 트레이(DECK_LOCAL_CENTRE y −0.30)라 쓰지 않는다.
CABINET_TARGET_LOCAL = (0.0, 0.65)
#: 인식표 높이 = 보관함 윗면 + 0.15(빈월드 zones 와 같은 간격).
TAG_ABOVE_CABINET = 0.15
ZONE_TOL = {"tol_xy": 0.15, "tol_yaw": 0.2}

BED_ZONE = {"D1": "bed_a1", "D2": "bed_a2", "D3": "bed_a3", "D4": "bed_a4",
            "D5": "bed_b1", "D6": "bed_b2", "D7": "bed_b3", "D8": "bed_b4", "D9": "bed_b5", "D10": "bed_b6"}
#: 병실 → PDF 병상 번호(작전 9/23 확정. PDF P3_Map 의 C1·C2 = 병실). 문 앵커의 이름과 같다.
ROOM_BEDS = {"C1": ("D1", "D2", "D3", "D4"), "C2": ("D5", "D6", "D7", "D8", "D9", "D10")}
#: 병동은 하나다(작전 9/23 확정. 화면 이름은 "1병동").
WARD = "W1"
DOCK_ZONE = {"A1": "dock_1", "A2": "dock_2", "A3": "dock_3", "A4": "dock_4"}
#: 적재 자리와 같은 곳에 서는 충전 도크(재범 9/29 B안). 나머지 도크도 제 모듈에 대해 같은 상대 자리다.
#: 도크의 접근점은 도크 회전 여유(DOCK_TURN_MARGIN)를 지킨다.
LOAD_DOCK = "dock_1"
LOAD_OUTLET = "A1"


#: 간호스테이션 B 의 배송 테이블(재범 9/24 13:5x·14:0x 확인). 앵커 JSON 밖이라 여기 적는다.
#: 값: 공개 자산 `SM_SideTable_02a.usd` 의 bbox(x ±0.459, y ±0.211, z 0–0.812) × 씬 변환(scale 1.185·1.950·0.7,
#: yaw 180, translate (9.934, 3.748, 0.019)). 지도의 막힌 칸(x 9.40–10.45, y 3.30–4.25)과 맞는다.
STATION_B_TABLE = {"prim": "/World/Environment/hospital/SM_SideTable_02a4_01",
                   "min": [9.390, 3.337, 0.019], "max": [10.478, 4.158, 0.587]}
#: 놓는 점은 로봇 쪽(북) 가장자리에서 이만큼 안이다. 테이블 가운데(0.41 안)보다 팔이 덜 뻗는다.
STATION_B_PLACE_INSET = 0.20
#: `station_b/cabinet` 로 볼 띠의 깊이(y). 놓는 점을 가운데로 한다. 보관함 참값·인식표 판이 이 크기를 쓴다.
#: 0.50 이면 인식표 판(0.10)이 놓는 점에서 0.18 떨어진 먼(남) 쪽에 선다. 띠의 북쪽 0.05 는 테이블 밖 허공이다.
STATION_B_STRIP = 0.50

#: 병실 테이블(C, 재범 9/25: 병실 주문 → C). 재범이 오버헤드 컷에 원으로 찍은 **병동 입구 복도 협탁 둘**이다(작전 정정
#: 9/25 03:5x). 씬에 있는 실물이라 지도에도 막혀 있다 — 세우지 않는다. zone 이름은 웹·주행 정규식(`station_[a-z]`)을
#: 지나게 station_c(C1, 위쪽 입구)·station_d(C2, 아래쪽 입구)다.
#: 상자: 공개 자산 SM_SideTable_02a.usd bbox(x ±0.459, y ±0.211, z 0–0.812) × 씬 변환(scale 1.185·1.950·0.7, yaw −90,
#: translate 는 아래). yaw −90 이라 월드 x 반폭 = 0.211 × 1.950, y 반폭 = 0.459 × 1.185. 씬 USD(9/25 main)에서 읽은 값:
#: - C1 `/World/Environment/hospital/SM_SideTable_02a4`(over) translate (20.1414, 5.8722, 0.00004)
#: - C2 `/World/Environment/hospital/SM_SideTable_02a4_02`(def) translate (20.1508, −2.0611, 0.00004)
SIDE_TABLE_SCALE = (1.1849030256271362, 1.9497179985046387, 0.7)
SIDE_TABLE_TOP = 0.812 * SIDE_TABLE_SCALE[2]
CORRIDOR_TABLES = {
    "station_c": ("C1", "/World/Environment/hospital/SM_SideTable_02a4", (20.141428075782308, 5.87218258787765)),
    "station_d": ("C2", "/World/Environment/hospital/SM_SideTable_02a4_02", (20.150828682380293, -2.061100689320967)),
}


def room_tables():
    """{zone: {"room", "prim", "centre", "min", "max"}} — 병동 입구 복도 협탁(C1·C2)의 월드 상자. 씬 prim 경로다."""
    out = {}
    hx, hy = 0.211 * SIDE_TABLE_SCALE[1], 0.459 * SIDE_TABLE_SCALE[0]      # yaw −90: 자산 y → 월드 x
    for zone, (room, prim, (cx, cy)) in CORRIDOR_TABLES.items():
        out[zone] = {"room": room, "prim": prim, "centre": (cx, cy),
                     "min": [cx - hx, cy - hy, 0.0], "max": [cx + hx, cy + hy, SIDE_TABLE_TOP]}
    return out


def corridor_table_pose(grid, table):
    """복도 협탁에 놓는 자리. station_b 처럼 놓는 점이 몸체 왼쪽이다. AMR 은 협탁 서쪽(복도)에 서고 앞이 −y(남).

    놓는 점: 복도 쪽(서) 가장자리에서 STATION_B_PLACE_INSET 안, 협탁 y 가운데, 윗면.
    """
    lo, hi = table["min"], table["max"]
    place = (lo[0] + STATION_B_PLACE_INSET, (lo[1] + hi[1]) / 2.0, hi[2])
    lateral = STATION_B_PLACE_INSET + STOP_CLEARANCE + BODY_WIDTH / 2 + 0.005
    found = None
    for yaw in (-math.pi / 2, math.pi / 2):
        local = (0.0, lateral) if yaw < 0 else (0.0, -lateral)    # +90 이면 오른쪽 — 왼쪽이 막힐 때만
        found = choose_pose(grid, place[:2], local, (yaw,), push_axis=1, reach_max=REACH_MAX_CABINET)
        if found:
            break
    side = "왼쪽" if found and found[2] < 0 else "오른쪽"
    return {"pose": found and found[:3], "reach": found and found[3], "cabinet": place,
            "note": (f"PDF {table['room']} 병동 입구 협탁 {table['prim'].rsplit('/', 1)[-1]}(재범 9/25), "
                     f"놓는 점이 몸체 {side}")}


def bed_places():
    """{bed zone: {"room", "ward", "label"}} — ROOM_BEDS·WARD·BED_ZONE 에서. 병실이 없는 병상이 있으면 멈춘다."""
    out = {BED_ZONE[label]: {"room": room, "ward": WARD, "label": label}
           for room, labels in ROOM_BEDS.items() for label in labels}
    missing = sorted(set(BED_ZONE.values()) - set(out))
    if missing:
        raise ValueError(f"병실이 정해지지 않은 병상: {missing}")
    return out


BED_PLACE = bed_places()


def _rot(yaw, x, y):
    c, s = math.cos(yaw), math.sin(yaw)
    return (x * c - y * s, x * s + y * c)


def _round(v):
    r = round(float(v), 3)
    return 0.0 if r == 0 else r


# ---------------------------------------------------------------- 지도

class Grid:
    """Nav2 trinary map. `blocked[r * w + c]` 는 occupied 또는 unknown. row 0 = y 최소(아래)."""

    def __init__(self, width, height, resolution, origin, blocked):
        self.w, self.h, self.res = width, height, resolution
        self.x0, self.y0 = origin
        self.blocked = blocked
        self._dist = None

    def cell(self, x, y):
        return int(math.floor((x - self.x0) / self.res)), int(math.floor((y - self.y0) / self.res))

    def centre(self, c, r):
        return self.x0 + (c + 0.5) * self.res, self.y0 + (r + 0.5) * self.res

    def inside(self, c, r):
        return 0 <= c < self.w and 0 <= r < self.h

    def is_blocked(self, x, y):
        c, r = self.cell(x, y)
        return (not self.inside(c, r)) or bool(self.blocked[r * self.w + c])

    def distance(self):
        """칸 중심에서 가장 가까운 막힌 칸 중심까지의 거리(m). 정확한 유클리드 거리 변환(Felzenszwalb)."""
        if self._dist is None:
            self._dist = _edt(self.w, self.h, self.blocked)
            self._dist = [math.sqrt(d) * self.res for d in self._dist]
        return self._dist

    def clearance(self, x, y):
        c, r = self.cell(x, y)
        if not self.inside(c, r):
            return 0.0
        return self.distance()[r * self.w + c]


def _edt_1d(f, n):
    INF = 1e20
    d = [0.0] * n
    v = [0] * n
    z = [0.0] * (n + 1)
    k = 0
    v[0] = 0
    z[0] = -INF
    z[1] = INF
    for q in range(1, n):
        while True:
            p = v[k]
            s = ((f[q] + q * q) - (f[p] + p * p)) / (2 * q - 2 * p)
            if s <= z[k]:
                k -= 1
                if k < 0:
                    k = 0
                    break
                continue
            break
        k += 1
        v[k] = q
        z[k] = s
        z[k + 1] = INF
    k = 0
    for q in range(n):
        while z[k + 1] < q:
            k += 1
        p = v[k]
        d[q] = (q - p) * (q - p) + f[p]
    return d


def _edt(w, h, blocked):
    INF = 1e20
    g = [0.0 if b else INF for b in blocked]
    for c in range(w):
        col = _edt_1d([g[r * w + c] for r in range(h)], h)
        for r in range(h):
            g[r * w + c] = col[r]
    out = [0.0] * (w * h)
    for r in range(h):
        row = _edt_1d(g[r * w:(r + 1) * w], w)
        out[r * w:(r + 1) * w] = row
    return out


def load_map(yaml_path=MAP_YAML_PATH):
    """map yaml(`image`·`resolution`·`origin`)과 P5 pgm 을 읽는다. PyYAML 을 쓰지 않는다(sim L1 잡에 없다)."""
    meta = {}
    with open(yaml_path, encoding="utf-8") as fh:
        lines = fh.readlines()
    for line in lines:
        line = line.split("#", 1)[0].strip()
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    res = float(meta["resolution"])
    origin = [float(v) for v in meta["origin"].strip("[]").split(",")][:2]
    with open(os.path.join(os.path.dirname(yaml_path), meta["image"]), "rb") as fh:
        data = fh.read()
    parts = data.split(b"\n", 3)
    if parts[0] != b"P5":
        raise ValueError("P5 pgm 이 아니다")
    width, height = (int(v) for v in parts[1].split())
    pixels = parts[3]
    blocked = bytearray(width * height)
    for r in range(height):
        src = pixels[(height - 1 - r) * width:(height - r) * width]   # pgm 첫 줄 = 위
        base = r * width
        for c in range(width):
            blocked[base + c] = 1 if src[c] != 254 else 0
    return Grid(width, height, res, origin, blocked)


def load_anchors(path=ANCHORS_PATH):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------- 정차 자세

def footprint_free(grid, x, y, yaw, clearance=STOP_CLEARANCE):
    """몸체(+ 뒤끝 받침 넘침)를 `clearance` 만큼 키운 사각형이 막힌 칸과 겹치지 않는가."""
    half_l = BODY_LENGTH / 2 + clearance
    half_w = BODY_WIDTH / 2 + clearance
    step = grid.res / 2
    nx = int(math.ceil((2 * half_l + RISER_OVERHANG) / step))
    ny = int(math.ceil(2 * half_w / step))
    for i in range(nx + 1):
        lx = -half_l - RISER_OVERHANG + i * (2 * half_l + RISER_OVERHANG) / nx
        for j in range(ny + 1):
            ly = -half_w + j * 2 * half_w / ny
            dx, dy = _rot(yaw, lx, ly)
            if grid.is_blocked(x + dx, y + dy):
                return False
    return True


def pose_for_target(target_xy, target_local, yaw):
    """목표가 팔 밑동 기준 로컬 `target_local` 에 오도록 하는 몸체 중심 (x, y)."""
    tx, ty = _rot(yaw, *target_local)
    bx, by = target_xy[0] - tx, target_xy[1] - ty            # 팔 밑동
    ax, ay = _rot(yaw, ARM_X, 0.0)
    return bx - ax, by - ay


def choose_pose(grid, target_xy, base_local, yaws, push_axis, reach_max=None):
    """`yaws` 마다 목표를 팔 밑동 로컬 `base_local` 에 두는 자세에서 시작해, 몸체가 빌 때까지 조금씩 민다.

    `push_axis` 는 목표에서 멀어지는 로컬 축(0 = x, 1 = y)이다. 그 축으로 0–0.25 m 멀어지고, 다른 축으로 ±0.30 m
    옆걸음한다. 밑동↔목표 수평이 `reach_max` 를 넘으면 버린다. 반환 (x, y, yaw, 밑동↔목표 수평) 또는 None.
    """
    best = None
    for yaw in yaws:
        for k in range(6):
            extra = 0.05 * k
            for m in range(13):
                shift = 0.05 * ((m + 1) // 2) * (1 if m % 2 else -1)
                lx, ly = base_local
                if push_axis == 0:
                    lx += math.copysign(extra, lx or -1.0)
                    ly += shift
                else:
                    ly += math.copysign(extra, ly or 1.0)
                    lx += shift
                reach = math.hypot(lx, ly)
                if reach_max is not None and reach > reach_max:
                    continue
                x, y = pose_for_target(target_xy, (lx, ly), yaw)
                cost = extra + abs(shift)
                if (best is None or cost < best[0]) and footprint_free(grid, x, y, yaw):
                    best = (cost, (x, y, yaw, reach))
            if best is not None and best[0] <= extra:
                break
        if best is not None:
            return best[1]
    return None


def virtual_table(anchors, bed="D3", like="D4"):
    """협탁이 없는 병상의 가상 협탁: `like` 병상과 같은 상대 자리·크기. 시뮬이 실제 협탁을 둘 때까지 쓴다."""
    ref_bed, ref_tab = anchors["beds"][like], anchors["bedside_tables"][like]
    dx = ref_tab["center"][0] - ref_bed["min"][0]
    dy = ref_tab["center"][1] - ref_bed["center"][1]
    b = anchors["beds"][bed]
    cx = b["min"][0] + dx if dx < 0 else b["max"][0] + dx
    cy = b["center"][1] + dy
    hx = (ref_tab["max"][0] - ref_tab["min"][0]) / 2
    hy = (ref_tab["max"][1] - ref_tab["min"][1]) / 2
    return {"center": [cx, cy, ref_tab["center"][2]], "min": [cx - hx, cy - hy, 0.0],
            "max": [cx + hx, cy + hy, ref_tab["max"][2]], "virtual_of": like}


#: 보관함에 닿는 팔 밑동↔목표 수평 상한. 비전 9/21 계산(보관함 0.70 에서 창 0.68–0.77)의 위 끝.
REACH_MAX_CABINET = 0.77
#: 창구 받침에 닿는 상한. 빈월드 벨트 픽(0.45)에서 0.25 까지만 멀어지게 둔다.
REACH_MAX_LOAD = 0.70


def zone_poses(grid, anchors):
    """{zone: {"pose": (x, y, yaw)|None, "reach": m, "cabinet": (x, y, z)|None, "note": str}}."""
    out = {}
    all_yaws = (0.0, math.pi / 2, math.pi, -math.pi / 2)
    for label, zone in DOCK_ZONE.items():
        out[zone] = dock_at_wall_pose(grid, anchors, label)
    # **잰 정착 자리**에서 잡는다(작전 결정 9/23). `belt_end` 는 계약 프레임이고 봉투는 그보다 0.12 m 안쪽에 선다.
    found = choose_pose(grid, A1_SETTLED_XY, LOAD_SIDE_TARGET_LOCAL, (0.0, math.pi, math.pi / 2, -math.pi / 2),
                        push_axis=1, reach_max=REACH_MAX_LOAD)
    out["load"] = {"pose": found and found[:3], "reach": found and found[3], "cabinet": None,
                   "note": f"창구 1(PDF {LOAD_OUTLET}) 끝 롤러 — 잰 정착 자리가 팔 밑동 왼쪽(차체 옆)에 온다"}
    if found is not None:
        # A1 충전 도크 = 적재 자리(재범 9/29 B안: "도크에서 AMR 이 이동하지 않고 그 자리에서 바로 파지").
        # 도크에서 봉투까지 팔 밑동 수평 1.03 m 라 UR5(설계 한도 0.70) 가 안 닿았다. 도크를 적재 자리로 옮긴다.
        # 떠날 때는 도크 회전 규칙(모듈까지 TURN_RADIUS + DOCK_TURN_MARGIN)을 지키게 접근점을 더 멀리 잡는다
        # (routes 의 LOAD_DOCK). 오케스트레이터는 두 zone 자세가 같으면 적재 GoToZone 을 보내지 않는다.
        out[LOAD_DOCK] = {"pose": found[:3], "reach": found[3], "cabinet": None,
                          "note": f"PDF A1 충전 도크 = 적재 자리(재범 9/29 B안), 팔 밑동↔봉투 {found[3]:.3f} m"}
        # 나머지 도크도 같은 자리로(재범 9/29 "도킹 스테이션 옮길꺼면 다 옮겨야지"): 제 모듈에 대해 A1 도크와
        # 같은 상대 자리(모듈 왼쪽). 막히면 9/25 벽 앞 자리를 그대로 쓴다.
        for label, zone in DOCK_ZONE.items():
            if zone != LOAD_DOCK:
                out[zone] = dock_like_load_pose(grid, anchors, label, found[:3]) or out[zone]
    for label, zone in BED_ZONE.items():
        table = anchors["bedside_tables"][label] or virtual_table(anchors, label)
        target = (table["center"][0], table["center"][1])
        found = None
        side = None   # (가) 옆 후보가 하나라도 있으면 (나) 뒤 후보는 쓰지 않는다(재범 9/23: 좌우 1순위, 앞뒤 후순위)
        for yaw in all_yaws:
            # (가) 협탁을 몸체 왼쪽(+y 로컬)에 둔다 — 빈월드 병상 자세와 같은 뜻.
            half = _table_half_extent(table, yaw, lateral=True)
            lateral = half + STOP_CLEARANCE + BODY_WIDTH / 2 + 0.005
            cands = [choose_pose(grid, target, (0.0, lateral), (yaw,), push_axis=1, reach_max=REACH_MAX_CABINET)]
            if cands[0]:
                key = (approach_point(grid, cands[0][:3]) is None, cands[0][3])
                if side is None or key < side[0]:
                    side = (key, cands[0])
            # (나) 협탁을 몸체 뒤(−x 로컬, 팔 쪽)에 둔다 — 빈월드 적재 자세와 같은 뜻.
            #     병상 사이 좁은 틈에 뒤로 들어간다.
            half = _table_half_extent(table, yaw, lateral=False)
            behind = half + STOP_CLEARANCE + BODY_LENGTH / 2 + RISER_OVERHANG + ARM_X + 0.005
            cands.append(choose_pose(grid, target, (-behind, 0.0), (yaw,), push_axis=0, reach_max=REACH_MAX_CABINET))
            for cand in cands:
                if not cand:
                    continue
                # 접근점(제자리 회전이 되는 곳)이 없는 자세는 들어갈 길이 없는 구석일 수 있다 — 뒤로 미룬다.
                key = (approach_point(grid, cand[:3]) is None, cand[3])
                if found is None or key < found[0]:
                    found = (key, cand)
        found = side[1] if side else (found and found[1])
        note = f"PDF {label}"
        if "virtual_of" in table:
            note += (f", 협탁 없음 → {table['virtual_of']} 와 같은 상대 자리의 가상 보관함"
                     " (그 자리에 SM_SupplyCart_01e15·SM_Chair_01a15 가 있어 씬 수정 전에는 정차 자세가 없다)")
        out[zone] = {"pose": found and found[:3], "reach": found and found[3],
                     "cabinet": (target[0], target[1], table["max"][2]), "note": note}
    desk = anchors["nursing_desk"]
    best = None
    # PDF 의 B 는 데스크 위(북)쪽 끝이다. 북 → 서 → 남 → 동 면 순서로, 앞이 데스크를 보게 선다.
    lo, hi = desk["min"], desk["max"]
    gap = STOP_CLEARANCE + BODY_LENGTH / 2 + 0.01
    sides = (("북", -math.pi / 2, lambda t: (lo[0] + t, hi[1] + gap), hi[0] - lo[0]),
             ("서", 0.0, lambda t: (lo[0] - gap, hi[1] - t), hi[1] - lo[1]),
             ("남", math.pi / 2, lambda t: (lo[0] + t, lo[1] - gap), hi[0] - lo[0]),
             ("동", math.pi, lambda t: (hi[0] + gap, hi[1] - t), hi[1] - lo[1]))
    side_used = None
    for side, yaw, at, span in sides:
        t = BODY_WIDTH / 2
        while best is None and t <= span - BODY_WIDTH / 2 + 1e-9:
            x, y = at(t)
            if footprint_free(grid, x, y, yaw):
                best, side_used = (x, y, yaw), side
            t += 0.05
        if best:
            break
    out["station_a"] = {"pose": best, "reach": None, "cabinet": None,
                        "note": f"PDF B, 간호스테이션 데스크 {side_used}쪽 면(앞이 데스크를 본다)"}
    out["station_b"] = station_b_pose(grid)
    for zone, table in room_tables().items():
        out[zone] = corridor_table_pose(grid, table)
    return out


#: 도크를 벽에 붙인다(재범 9/25 "전부 벽에 붙이고 깔끔하게", 비전 산출). 도크 모듈(앵커 outlets `shelf`) 오른쪽(+x)
#: 옆 벽 앞에 yaw −90(앞이 −y, 팔 뒤끝이 벽)으로 선다.
#: - y: 걸레받이 앞면 5.335(마클1 실측 9/25, 판 5.330 과 같은 뜻으로 비전은 5.33) − 0.08 − 몸체 반길이.
#:   받침 넘침 0.034 까지 넣은 뒤끝은 실측 벽 앞면 5.350 에서 0.066 m 다.
#: - x: 모듈 받침 오른쪽 끝 + 0.12 + 몸체 반폭. 지도 칸(0.05 m)이 받침을 넓게 잡아 몸체가 그 칸에 닿으면 +x 로
#:   0.005 m 씩 민다(dock_1 +0.040, dock_2 +0.010, dock_3 +0.015, dock_4 0).
#: 여유: 지도의 벽 칸(y ≥ 5.30)은 실측 벽(5.350)보다 5 cm 안쪽이라, 이 자세만 STOP_CLEARANCE 0.05 대신 0 으로 지도와
#: 겹치지 않는 것을 본다. 실측 기준 틈은 벽 0.066·모듈 0.12–0.16 이다.
DOCK_TRIM_Y = 5.33
DOCK_WALL_GAP = 0.08
DOCK_MODULE_GAP = 0.12
#: 도크를 떠날 때 접근점까지 곧게 물러난 뒤 거기서 돈다(navigation routes.DEPART_BY_SLIDE_KINDS, 9/25 회차77).
#: 그 접근점에서 회전 반경(받침 포함) TURN_RADIUS 바깥으로 모듈 상자(앵커)까지 이만큼 남게 도크를 +x 로 민다.
DOCK_TURN_MARGIN = 0.10


def _box_distance(box, x, y):
    dx = max(box["min"][0] - x, 0.0, x - box["max"][0])
    dy = max(box["min"][1] - y, 0.0, y - box["max"][1])
    return math.hypot(dx, dy)


def dock_at_wall_pose(grid, anchors, label):
    """도크 `label`(A1–A4)의 벽 앞 정차 자세. 몸체가 지도 막힌 칸에 닿지 않을 때까지 모듈 반대쪽(+x)으로 민다."""
    shelf = anchors["outlets"][label]["shelf"]
    yaw = -math.pi / 2
    x = shelf["max"][0] + DOCK_MODULE_GAP + BODY_WIDTH / 2
    y = DOCK_TRIM_Y - DOCK_WALL_GAP - BODY_LENGTH / 2
    pushed = 0.0

    def turn_clear(px):
        near = approach_point(grid, (px, y, yaw))
        return near is not None and _box_distance(shelf, *near) >= TURN_RADIUS + DOCK_TURN_MARGIN

    while not (footprint_free(grid, x + pushed, y, yaw, clearance=0.0) and turn_clear(x + pushed)):
        pushed += 0.005
        if pushed > 0.4:
            return {"pose": None, "reach": None, "cabinet": None, "note": f"PDF {label}: 벽 앞 자리가 막혔다"}
    return {"pose": (_round(x + pushed), _round(y), yaw), "reach": None, "cabinet": None,
            "note": f"PDF {label}, 모듈 {shelf['prim'].rsplit('/', 1)[-1]} 오른쪽 벽 앞(재범 9/25), x +{pushed:.3f}"}


def dock_like_load_pose(grid, anchors, label, load_pose):
    """도크 `label` 을 제 모듈에 대해 A1 적재 자리(`load_pose`)와 같은 상대 자리에 둔다. 몸체가 막히거나
    접근점에서 모듈까지 회전 여유(TURN_RADIUS + DOCK_TURN_MARGIN)가 없으면 None."""
    ref = anchors["outlets"][LOAD_OUTLET]["shelf"]
    shelf = anchors["outlets"][label]["shelf"]
    x = load_pose[0] + shelf["min"][0] - ref["min"][0]
    y = load_pose[1] + shelf["min"][1] - ref["min"][1]
    pose = (_round(x), _round(y), load_pose[2])
    if not footprint_free(grid, *pose):
        return None
    near = approach_point(grid, pose, margin=DOCK_TURN_MARGIN)
    if near is None or _box_distance(shelf, *near) < TURN_RADIUS + DOCK_TURN_MARGIN:
        return None
    return {"pose": pose, "reach": None, "cabinet": None,
            "note": f"PDF {label} 충전 도크, 모듈 {shelf['prim'].rsplit('/', 1)[-1]} 왼쪽 — A1 적재 자리와 같은 "
                    "상대 자리(재범 9/29)"}


def station_b_pose(grid, table=STATION_B_TABLE):
    """간호스테이션 B 테이블에 올려놓는 자리. 병상 (가)와 같이 **놓는 점을 몸체 왼쪽**에 둔다.

    9/24 회차48(b45ad5d): 테이블을 몸체 뒤(팔 쪽)에 두었더니 UR5 가 어깨 높이로 뒤로 뻗다 위팔이 테이블 북쪽
    모서리(z 0.588)에 걸렸다(`shoulder_lift` 0.21 rad 미도달). 병상 열 곳은 협탁을 왼쪽에 둔 자세(팔 밑동↔목표
    0.702 m)로 통과했다 — 같은 상대 기하를 쓴다. 왼쪽 자세가 없을 때만 뒤 자세로 간다.
    """
    lo, hi = table["min"], table["max"]
    place = ((lo[0] + hi[0]) / 2.0, hi[1] - STATION_B_PLACE_INSET, hi[2])
    found = None
    lateral = STATION_B_PLACE_INSET + STOP_CLEARANCE + BODY_WIDTH / 2 + 0.005
    for yaw in (math.pi, 0.0, math.pi / 2, -math.pi / 2):
        found = choose_pose(grid, place[:2], (0.0, lateral), (yaw,), push_axis=1, reach_max=REACH_MAX_CABINET)
        if found:
            break
    side = "왼쪽"
    if not found:
        side = "뒤"
        box = {"min": lo, "max": hi, "center": [(lo[i] + hi[i]) / 2.0 for i in range(3)]}
        for yaw in (math.pi / 2, 0.0, math.pi, -math.pi / 2):
            half = _table_half_extent(box, yaw, lateral=False)
            behind = half + STOP_CLEARANCE + BODY_LENGTH / 2 + RISER_OVERHANG + ARM_X + 0.005
            found = choose_pose(grid, box["center"][:2], (-behind, 0.0), (yaw,), push_axis=0,
                                reach_max=REACH_MAX_CABINET)
            if found:
                break
    return {"pose": found and found[:3], "reach": found and found[3], "cabinet": place,
            "note": f"PDF B 테이블 {table['prim'].rsplit('/', 1)[-1]}(재범 9/24), 놓는 점이 몸체 {side}"}


def _table_half_extent(table, yaw, lateral=True):
    """몸체 옆(로컬 +y) 또는 앞뒤(로컬 x) 방향의 world 축으로 본 협탁 반폭."""
    lx, ly = _rot(yaw, 0.0, 1.0) if lateral else _rot(yaw, 1.0, 0.0)
    hx = (table["max"][0] - table["min"][0]) / 2
    hy = (table["max"][1] - table["min"][1]) / 2
    return abs(lx) * hx + abs(ly) * hy


# ---------------------------------------------------------------- 경로

def _neighbours():
    s = math.sqrt(2.0)
    return ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0), (1, 1, s), (1, -1, s), (-1, 1, s), (-1, -1, s))


def edge_clearance(grid, x, y, reach=1.0):
    """(x, y) 에서 가장 가까운 막힌 칸의 **가장자리**까지 거리(m). `reach` 안에 없으면 `reach`.

    `Grid.clearance` 는 칸 중심끼리 잰 값이라 실제보다 칸 하나 가까이까지 길게 나온다. 9/24 병원 10건:
    bed_a3 접근점 (23.702, 6.110) 이 `clearance` 로 0.673 m 였지만 막힌 칸 가장자리까지는 0.578 m,
    D3 협탁 상자까지는 0.594 m 였고, 거기서 돈 팔 받침이 협탁에 닿았다. 회전처럼 여유가 몇 cm 인 판정은 이것으로 잰다.
    """
    c0, r0 = grid.cell(x, y)
    k = int(math.ceil(reach / grid.res)) + 1
    best = reach
    for r in range(r0 - k, r0 + k + 1):
        for c in range(c0 - k, c0 + k + 1):
            if grid.inside(c, r) and not grid.blocked[r * grid.w + c]:
                continue
            left, bottom = grid.x0 + c * grid.res, grid.y0 + r * grid.res
            dx = max(left - x, 0.0, x - (left + grid.res))
            dy = max(bottom - y, 0.0, y - (bottom + grid.res))
            best = min(best, math.hypot(dx, dy))
    return best


def approach_point(grid, pose, max_d=2.0, margin=0.02):
    """정차 자세에서 몸체 축 네 방향으로 나가 제자리 회전 반경(`TURN_RADIUS`)이 나오는 가장 가까운 점.

    추종기는 마지막 구간(마지막 waypoint → 목표)에서 **이 점에서 먼저 제자리로 목표 yaw 를 맞추고**, 그 뒤 yaw 를
    고정한 채 정차 자리로 옮긴다(fleet 의 nav2 final approach, waypoint_follower.follow 의 turn_first).
    회전 여유는 막힌 칸 가장자리까지(`edge_clearance`) 잰다. 없으면 None.
    """
    x, y, yaw = pose
    need = TURN_RADIUS + margin
    best = None
    for ax, ay in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        dx, dy = _rot(yaw, ax, ay)
        d = 0.3
        while d <= max_d:
            px, py = x + dx * d, y + dy * d
            # 칸 중심 거리는 가장자리 거리보다 칸 하나(res) 넘게 짧지 않다. 먼저 싸게 거른다.
            if grid.clearance(px, py) + grid.res >= need and edge_clearance(grid, px, py) >= need:
                wide = segment_min_clearance(grid, (x, y), (px, py)) >= BODY_WIDTH / 2 + 0.01
                if wide and (best is None or d < best[0]):
                    best = (d, (_round(px), _round(py)))
                break
            d += 0.05
    return best and best[1]


def passable(grid, stops, radius=PATH_RADIUS, near=1.2, floor=BODY_WIDTH / 2 + 0.01):
    """몸체 중심이 갈 수 있는 칸(bytearray). 기본은 장애물에서 `radius` 이상 떨어진 칸이다.

    정차 자세는 고정물 옆 `STOP_CLEARANCE` 에 서므로 그 주변(`near` m 안)만은 정차 자세의 여유까지 풀어 준다
    (단 몸체 반폭 `floor` 아래로는 안 푼다). 풀어 준 구간의 실제 여유는 경로마다 보고한다.
    """
    dist_field = grid.distance()
    ok = bytearray(1 if d >= radius else 0 for d in dist_field)
    for sx, sy in stops:
        need = max(floor, min(radius, grid.clearance(sx, sy)) - 0.02)
        c0, r0 = grid.cell(sx, sy)
        k = int(math.ceil(near / grid.res))
        for r in range(max(0, r0 - k), min(grid.h, r0 + k + 1)):
            for c in range(max(0, c0 - k), min(grid.w, c0 + k + 1)):
                j = r * grid.w + c
                if not ok[j] and dist_field[j] >= need and math.hypot(c - c0, r - r0) * grid.res <= near:
                    ok[j] = 1
    return ok


def dijkstra(grid, ok, start_xy):
    """`start_xy` 에서 `ok` 칸만 밟아 도달 가능한 칸까지의 (거리, 부모) 표. 8-이웃."""
    w, h = grid.w, grid.h
    c0, r0 = grid.cell(*start_xy)
    start = r0 * w + c0
    best = {start: 0.0}
    parent = {start: -1}
    heap = [(0.0, start)]
    nbrs = _neighbours()
    while heap:
        d, i = heapq.heappop(heap)
        if d > best.get(i, math.inf):
            continue
        r, c = divmod(i, w)
        for dc, dr, cost in nbrs:
            cc, rr = c + dc, r + dr
            if not (0 <= cc < w and 0 <= rr < h):
                continue
            j = rr * w + cc
            if not ok[j]:
                continue
            nd = d + cost
            if nd < best.get(j, math.inf):
                best[j] = nd
                parent[j] = i
                heapq.heappush(heap, (nd, j))
    return best, parent


def _segment_ok(grid, ok, a, b):
    # 칸 모서리만 스치는 선분도 잡히게 칸 크기의 1/5 간격으로 본다(1/2 이면 모서리를 깎아 0.53 이 새었다).
    n = max(1, int(math.ceil(math.hypot(b[0] - a[0], b[1] - a[1]) / (grid.res / 5))))
    for k in range(n + 1):
        c, r = grid.cell(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n)
        if not grid.inside(c, r) or not ok[r * grid.w + c]:
            return False
    return True


def segment_min_clearance(grid, a, b):
    n = max(1, int(math.ceil(math.hypot(b[0] - a[0], b[1] - a[1]) / (grid.res / 2))))
    return min(grid.clearance(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n + 1))


def path_between(grid, ok, table, start_xy, goal_xy):
    """dijkstra 표(`table` = start 기준)로 goal 까지 칸 경로 → 시야가 닿는 점만 남긴 waypoint 목록.

    반환은 (waypoints, 최소 여유 m). waypoint 는 출발·도착 자세를 빼고 중간 점만 담는다. 경로가 없으면 (None, 0).
    """
    best, parent = table
    c, r = grid.cell(*goal_xy)
    j = r * grid.w + c
    if j not in best:
        return None, 0.0
    cells = []
    while j != -1:
        rr, cc = divmod(j, grid.w)
        cells.append(grid.centre(cc, rr))
        j = parent[j]
    cells.reverse()
    pts = [tuple(start_xy)] + cells[1:-1] + [tuple(goal_xy)]
    keep = [pts[0]]
    i = 0
    while i < len(pts) - 1:
        j = len(pts) - 1
        while j > i + 1 and not _segment_ok(grid, ok, pts[i], pts[j]):
            j -= 1
        keep.append(pts[j])
        i = j
    legs = list(zip(keep[:-1], keep[1:], strict=True))
    min_clear = min(segment_min_clearance(grid, a, b) for a, b in legs)
    return [(_round(x), _round(y)) for x, y in keep[1:-1]], min_clear


#: 골든 경로표 뒤에 더한 zone. 이 zone 의 정차 자리 주변 완화(`passable` 의 near)는 그 zone 이 낀 쌍에만 쓴다.
#: dock_2–4(9/29 모듈 왼쪽으로 옮김)도 여기 둔다 — 로비 복도 옆이라 공통 완화에 넣으면 배송 경로가 바뀐다.
ISOLATED_STOPS = ("station_b", "station_c", "station_d", "dock_2", "dock_3", "dock_4")


def routes(grid, poses):
    """모든 zone 쌍의 waypoint. ({(from, to): [(x, y), ...]}, {(from, to): 최소 여유 m}, 못 이은 쌍 목록)."""
    names = [n for n in poses if poses[n]["pose"] is not None]
    # 나중에 더한 zone(ISOLATED_STOPS)의 정차 자리 완화는 그 zone 이 낀 쌍에만 쓴다 — 다른 쌍의 경로가 안 바뀐다.
    base_stops = [poses[n]["pose"][:2] for n in names if n not in ISOLATED_STOPS]
    ok_base = passable(grid, base_stops)
    ok_all = passable(grid, [poses[n]["pose"][:2] for n in names])
    near = {n: approach_point(grid, poses[n]["pose"],
                              margin=DOCK_TURN_MARGIN if n in DOCK_ZONE.values() else 0.02) for n in names}
    pairs, clear, missing = {}, {}, []
    for a in names:
        pa = poses[a]["pose"][:2]
        tables = {}
        for b in names:
            if a == b:
                continue
            ok = ok_all if (a in ISOLATED_STOPS or b in ISOLATED_STOPS) else ok_base
            if id(ok) not in tables:
                tables[id(ok)] = dijkstra(grid, ok, pa)
            table = tables[id(ok)]
            pb = poses[b]["pose"][:2]
            if math.hypot(pa[0] - pb[0], pa[1] - pb[1]) < 1e-6:
                pairs[(a, b)] = []
                clear[(a, b)] = grid.clearance(*pa)
                continue
            goal = near[b] or pb
            wps, c = path_between(grid, ok, table, pa, goal)
            if wps is None:
                missing.append((a, b))
                continue
            if near[b]:
                wps = wps + [near[b]]
                c = min(c, segment_min_clearance(grid, near[b], pb))
            pairs[(a, b)] = wps
            clear[(a, b)] = c
    return pairs, clear, missing


# ---------------------------------------------------------------- YAML 본문(PyYAML 없이)

ZONES_HEADER = (
    "# 병원 씬(sim/scenes/hospital_navigationv1)의 구역과 고정 프레임. 계약 v1 3절의 형식이다.",
    "#",
    "# **이 파일은 자동 생성물이다. 손으로 고치지 않는다.**",
    "#   단일 출처: sim/scenes/hospital_navigationv1.anchors.json(USD 에서 뽑은 앵커) + maps/hospital.{pgm,yaml}",
    "#   만드는 코드: sim/standalone/p3sim/hospital_nav.py, 시험: sim/tests/test_hospital_nav.py",
    "#   다시 만들기: python3 sim/standalone/hospital_nav_files.py --zones",
    "#",
    "# **정차 자세는 빈월드에서 검증한 팔 밑동↔목표 상대 기하를 옮긴 것이다. 병원 높이로 IK 를 다시 풀지 않았다.**",
    "#   몸체가 지도의 막힌 칸과 겹치지 않는 것만 확인했다. L3 미실행.",
    "#",
    "# bed 의 room·ward·label(작전 9/23 확정): room C1 = D1–D4, C2 = D5–D10(PDF P3_Map 의 병실),",
    "#   ward 는 W1 하나(1병동), label = PDF 병상 번호. 웹 /api/destinations 가 이것으로 병실별로 묶는다.",
    "#",
    "# 사람 결정 전 기본값: ① D1–D4 → bed_a1–a4, D5–D10 → bed_b1–b6 ② load = 창구 1(A1) 자리",
    "#   ③ 병실 입구 C1·C2 는 zone 이 아니라 경로 경유점. bed_a3(D3)은 협탁이 없어 가상 보관함이다.",
    "#",
    "# pharmacy.belt_end(작전 9/23 확정): 창구 A1 끝 롤러 ConveyorTrack_02/Rollers_01 윗면의 출구 쪽 끝 중심.",
    "#   x = Rollers_01 bbox x 중심, y = bbox min y(봉투가 −y 로 나간다), z = bbox max z(윗면),",
    "#   yaw −90°(x = 진행 방향). bbox 는 master02 참조 탐침 결과의 terminal_surface(#240)다.",
    "#   잰 값이고 hospital_nav.A1_TERMINAL_SURFACE 에 있다.",
    "# 고르는 법: launch 인자나 P3_ZONES 로 이 파일의 절대 경로를 준다. 기본 zones.yaml 은 그대로다.",
    "",
)

ROUTES_HEADER = (
    "# 병원 씬(sim/scenes/hospital_navigationv1)의 경로 경유점. 주행 routes.py 스키마다.",
    "#",
    "# **이 파일은 자동 생성물이다. 손으로 고치지 않는다.**",
    "#   다시 만들기: python3 sim/standalone/hospital_nav_files.py --routes",
    "#   지도(maps/hospital.pgm, USD 렌더 기하 기반) 위에서 몸체 중심을 장애물에서 0.56 m 떼어 찾은 최단 경로를",
    "#   시야가 닿는 점만 남겨 줄인 것이다. waypoint 는 출발·도착 자세를 빼고 중간 점만 담는다.",
    "# 여유는 정지 기하로만 계산했다 — 추종 오차·위치 추정 오차는 빠져 있다. 실제 이격은 L3 에서 잰다.",
    "# `waypoints: []` 는 \"곧장 가도 된다고 따져 봤다\" 는 뜻이다(적재=창구 1 과 dock_1 은 같은 자리).",
    "",
)


#: 창구 A1 끝 롤러(`/World/Conveyor/ConveyorTrack_02/Rollers_01`)의 월드 상자(m). **잰 값이다**: master02 참조 탐침
#: 결과의 terminal_surface(#240 5790540704, 렌더 기하 AABB). 두께 0.029 m 의 얇은 윗면이다.
A1_TERMINAL_SURFACE = {"min": (-8.4195, 4.9644, 0.3557), "max": (-7.9679, 5.9293, 0.3847)}
#: 끝 롤러에서 봉투가 나가는 방향 −y(잰 회차의 terminal_direction). 프레임 x 가 이 방향이라 yaw = −90°.
A1_TERMINAL_YAW = -math.pi / 2
#: pharmacy 프레임은 zone 보다 한 자리 더 둔다(0.1 mm). 준 값(작전 9/23)을 그대로 남기려고.
PHARMACY_PLACES = 4


def pharmacy_frames(surface=A1_TERMINAL_SURFACE, yaw=A1_TERMINAL_YAW):
    """계약 3절 `pharmacy/*` 고정 프레임 {이름: (x, y, z, yaw)}. 병원은 `belt_end` 하나다(작전 9/23 확정).

    belt_end = 벨트 윗면·중심선의 끝점, 프레임 x = 진행 방향. 끝 롤러가 −y 로 나가므로
    x = 상자 x 중심, y = 상자 **min y**(출구 쪽 끝), z = 상자 **max z**(윗면)다. 봉투가 실제로 선 자리
    (-8.295, 5.036, 0.389, #240)와는 xy 0.124 m 떨어진다 — 참값 센서 반경(truth_sensors.BELT_END_RADIUS 0.25) 안이다.
    """
    lo, hi = surface["min"], surface["max"]
    return {"belt_end": ((lo[0] + hi[0]) / 2.0, lo[1], hi[2], yaw)}


def cabinet_sizes(anchors):
    """{`<zone>/cabinet`: (x 폭, y 폭)} — 협탁 앵커 bbox(월드 축)의 가로·세로.

    협탁이 없는 병상은 virtual_table 의 크기다.

    스테이지의 보관함 참값(truth_sensors.in_cabinet)이 월드 축 반폭으로 보므로 월드 축 폭을 그대로 준다.
    """
    out = {}
    for label, zone in BED_ZONE.items():
        table = anchors["bedside_tables"].get(label) or virtual_table(anchors, label)
        out[f"{zone}/cabinet"] = (table["max"][0] - table["min"][0], table["max"][1] - table["min"][1])
    lo, hi = STATION_B_TABLE["min"], STATION_B_TABLE["max"]
    out["station_b/cabinet"] = (hi[0] - lo[0], STATION_B_STRIP)
    for zone, table in room_tables().items():
        # 복도 협탁은 긴 변이 y 다 — 놓는 띠는 복도 쪽(x) 깊이 STATION_B_STRIP × 긴 변(y) 전체(월드 축).
        out[f"{zone}/cabinet"] = (STATION_B_STRIP, table["max"][1] - table["min"][1])
    return out


def zones_doc(poses):
    zones = {}
    table_sizes = cabinet_sizes(load_anchors())
    order = (["load"] + list(DOCK_ZONE.values()) + ["station_a", "station_b"] + list(CORRIDOR_TABLES)
             + list(BED_ZONE.values()))
    for name in order:
        entry = poses.get(name)
        if not entry or entry["pose"] is None:
            continue
        x, y, yaw = entry["pose"]
        kind = "station" if name in CORRIDOR_TABLES else name.split("_", 1)[0]
        e = {"kind": kind, "x": _round(x), "y": _round(y), "yaw": _round(yaw), **ZONE_TOL}
        if name in CORRIDOR_TABLES:
            e["room"] = CORRIDOR_TABLES[name][0]
        if name in BED_PLACE:
            e.update(BED_PLACE[name])
        if entry["cabinet"]:
            cx, cy, cz = entry["cabinet"]
            # 보관함 프레임 x 를 테이블 긴 변에 맞춘다. 한 정거장 여러 봉투의 칸 비킴(프레임 x)이 긴 변을 따라간다.
            # station_b 는 긴 변이 월드 x 라 0, 복도 협탁(C1·C2)은 긴 변이 월드 y 라 90°.
            cyaw = _round(math.pi / 2) if name in CORRIDOR_TABLES else 0.0
            e["cabinet"] = {"x": _round(cx), "y": _round(cy), "z": _round(cz), "yaw": cyaw}
            e["tag"] = {"x": _round(cx), "y": _round(cy), "z": _round(cz + TAG_ABOVE_CABINET), "yaw": cyaw}
            if name.startswith('bed_'):
                tx, ty, tz = patient_plates.near_tag_pose(
                    entry['pose'][:2], (cx, cy, cz), table_sizes[f'{name}/cabinet'])
                e['tag'] = {'x': _round(tx), 'y': _round(ty), 'z': round(tz, 4), 'yaw': cyaw}
        zones[name] = e
    fixed = {name: {"x": round(x, PHARMACY_PLACES) + 0.0, "y": round(y, PHARMACY_PLACES) + 0.0,
                    "z": round(z, PHARMACY_PLACES) + 0.0, "yaw": round(yaw, PHARMACY_PLACES) + 0.0}
             for name, (x, y, z, yaw) in pharmacy_frames().items()}
    return {"frame": "map", "zones": zones, "pharmacy": fixed}


def zones_yaml_text(doc):
    lines = [*ZONES_HEADER, f"frame: {doc['frame']}", "zones:"]
    for name, entry in doc["zones"].items():
        lines.append(f"  {name}:")
        for key, value in entry.items():
            if isinstance(value, dict):
                lines.append(f"    {key}:")
                lines += [f"      {k}: {v}" for k, v in value.items()]
            else:
                lines.append(f"    {key}: {value}")
    if doc.get("pharmacy"):
        lines.append("pharmacy:")
        for name, pose in doc["pharmacy"].items():
            lines.append(f"  {name}:")
            lines += [f"    {k}: {v}" for k, v in pose.items()]
    return "\n".join(lines) + "\n"


def routes_yaml_text(pairs):
    lines = [*ROUTES_HEADER, "schema_version: 1", "frame: map", "routes:"]
    for (source, target), wps in sorted(pairs.items()):
        points = ", ".join(f"[{x}, {y}]" for x, y in wps)
        lines.append(f"  - {{from: {source}, to: {target}, waypoints: [{points}]}}")
    return "\n".join(lines) + "\n"
