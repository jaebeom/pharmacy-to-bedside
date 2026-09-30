"""병원 바닥 표시(시각 소품, 재범 9/24 "병원 데코"). Isaac 임포트는 늦게 한다.

물류 AMR 현장과 병원 복도에 실제로 있는 것 셋을 바닥에 칠한다.

목적지는 세 갈래로 색을 나눈다(재범 9/25 03:3x): **병동 주문 → B(간호스테이션 테이블) 파랑, 병실 주문 → C(병실
테이블) 초록, 병상 주문 → D(침상 협탁) 노랑.** 목적지가 아닌 자리(적재·도크·간호사실 A)는 주황이다.

- **유도선**: 적재 → B 파랑, 적재 → C1·C2 초록, 적재 → A 병동·B 병동 첫 침상(D1·D5) 노랑. 자리는
  `routes.hospital.yaml` 의 경로다 — 몸체 중심이 장애물에서 0.56 m 떨어지게 이미 계산된 선이라 바닥 위에 있다.
  C 테이블 zone(`station_c`·`station_d`)이 zones 에 아직 없으면 그 선·칸은 까닭을 남기고 건너뛴다.
- **정차 칸**: 목적지 정차 자세(zones 의 값 그대로)에 몸체 크기 테두리, 색은 위 갈래.
- **글자 판**: 칸마다 이름(`적재`, `도크 1`, `B`, `C1`, `D1` …), 바탕은 갈래 색. 로비 바닥에 범례 판 하나
  (`B 병동 / C 병실 / D 병상`). 글자는 아틀라스 한 장(`sim/assets/decor/labels.png`).
- **테이블 윗면 색**: B 테이블은 파랑, D 협탁은 노랑(C 테이블이 생기면 초록) 시각 재질을 덮는다. 물리·기하는
  그대로다. 인식표·QR 판은 테이블 밑 prim 이 아니라 따로 선 판이라 색이 안 바뀐다(`patient_plates`).

제약(최적화 9/24 예산: rtf −0.02·기동 +3 s·VRAM +0.3 GB 이내)과 그 이유:

- **바닥에만 둔다.** RTX 라이다는 시각 메시도 본다. 스캔 높이(0.1–0.6 m)에 세운 소품은 이제 살아난 코스트맵
  장애물 층(#620)에 가짜 장애물로 찍힌다. 바닥에서 1.5 mm 안이면 스캔 평면(약 0.306 m)과 만날 수 없다.
- **두께 0 판을 들어 올린다.** 겹치는 표시끼리 깜빡이지 않게 선 1.0–1.2 mm, 칸 1.3 mm, 글자 1.4 mm.
- **물리 0.** 충돌·강체 API 가 없다. 한 번 세우고 매 틱 쓰지 않는다.
- **메시 둘, 재질 둘, 텍스처 한 장.** 색 띠 전부가 메시 하나(꼭짓점 색), 글자 판 전부가 메시 하나(아틀라스 UV).
  반투명·알파 없음.
- **조제실 워크셀 안에는 두지 않는다.** M0609 손 카메라 시야다(`PHARMACY_KEEP_OUT`).
- 글자 판 바탕은 **채도 높은 노랑**이다. 카메라 봉투 검출기는 "밝고 채도 낮은 덩어리" 를 찾는다 — 흰 판을
  깔면 봉투로 잡힐 수 있다.

Isaac 이 있어야 도는 부분(`build`)은 L3 미실행이다. 자리 계산은 순수 함수라 sim/tests 가 본다.
"""

import math
import re

from .hospital_nav import BED_ZONE, STATION_B_TABLE
from .traffic_dummies import LOOPS as DUMMY_LOOPS

#: 선·칸·글자를 바닥에서 들어 올리는 높이(m). 서로 다른 높이라 겹쳐도 깜빡이지 않는다.
LIFT_LINES = (0.0010, 0.00105, 0.0011, 0.00115, 0.0012)
LIFT_BAY = 0.0013
LIFT_LABEL = 0.0014
#: 선 폭(m). 병원 바닥 유도선 흔한 폭(5 cm).
LINE_WIDTH = 0.05
#: 모서리에서 선 폭이 부푸는 상한(미터 결합 배수). 예각에서 뾰족하게 튀지 않게 자른다.
MITER_LIMIT = 3.0
#: 정차 칸 테두리: 몸체 밖으로 띄우는 여유(m), 테두리 굵기(m).
BAY_MARGIN = 0.05
BAY_STROKE = 0.04
#: 글자 판 크기(m)와 칸 테두리에서 띄우는 틈(m). 아틀라스 칸 비율(4:1)과 같다.
LABEL_SIZE = (0.60, 0.15)
LABEL_GAP = 0.05

BLUE = (0.10, 0.35, 0.85)
GREEN = (0.10, 0.62, 0.30)
ORANGE = (0.95, 0.50, 0.08)
YELLOW = (0.98, 0.80, 0.10)

#: 목적지 갈래 색(재범 9/25 03:3x). B 병동 = 간호스테이션 테이블, C 병실 = 병실 테이블, D 병상 = 침상 협탁.
CLASS_COLORS = {"B": BLUE, "C": GREEN, "D": YELLOW}
#: 목적지가 아닌 자리(적재·도크·간호사실 A)의 색. D 노랑과 헷갈리지 않게 주황이다.
OTHER_COLOR = ORANGE
#: 글자 색. 파랑·초록 바탕에는 연노랑(흰색은 쓰지 않는다 — 봉투 검출기가 "밝고 채도 낮은 덩어리" 를 찾는다),
#: 노랑·주황 바탕에는 검정.
LIGHT_INK = (1.0, 0.92, 0.47)
DARK_INK = (0.08, 0.08, 0.08)
#: 병실 테이블 zone → 글자. zones 에 없으면 건너뛴다(C 테이블 목적지 작업이 zone 을 더한다).
ROOM_TABLE_ZONES = {"station_c": "C1", "station_d": "C2"}

#: (이름, 경로 출발, 경로 도착, 색, 들어 올림). 경로는 routes.hospital.yaml 에서 읽는다. 전부 적재에서 나간다.
GUIDE_LINES = (
    ("ward_b", "load", "station_b", BLUE, LIFT_LINES[0]),
    ("bed_d1", "load", "bed_a1", YELLOW, LIFT_LINES[1]),
    ("bed_d5", "load", "bed_b1", YELLOW, LIFT_LINES[2]),
    ("station_c", "load", "station_c", GREEN, LIFT_LINES[3]),
    ("station_d", "load", "station_d", GREEN, LIFT_LINES[4]),
)
#: 다섯 선은 적재에서 한동안 같은 복도로 나간다. 진행 방향 왼쪽(+)·오른쪽(−)으로 0.06 m 씩 나란히 띄운다
#: (선 폭 0.05 보다 넓다). 들어 올림도 선마다 달라 모서리에서 겹쳐도 깜빡이지 않는다.
LINE_OFFSETS = {"ward_b": 0.0, "bed_d1": +0.06, "bed_d5": -0.06, "station_c": +0.12, "station_d": -0.12}

#: 정차 칸과 그 글자. 글자는 아틀라스(`labels.json`)에 있어야 한다. 순서가 겹칠 때 이기는 순서다.
BAY_LABELS = {
    # load(적재, A1 컨베이어 끝)는 칸을 그리지 않는다 — 재범 9/25 컷: 충전 칸(dock_1 A1) 옆에 칸이 하나 더 있어 "A1 이
    # 둘" 로 보였다. 충전 표시가 없는 쪽을 뺀다. 정차 자세·동작은 그대로다.
    "dock_1": "도크 1", "dock_2": "도크 2", "dock_3": "도크 3", "dock_4": "도크 4",
    # station_a(간호사실 데스크 서쪽 면)는 목적지가 아니다(재범 9/25 B·C·D) — 칸을 그리지 않는다.
    # 오버헤드 컷에서 B 테이블 옆 실제 B 칸과 나란히 주황 칸이 하나 더 보여 "B 칸이 둘" 로 읽혔다(작전 9/25).
    "station_b": "B",
    **ROOM_TABLE_ZONES,
    **{zone: label for label, zone in sorted(BED_ZONE.items(), key=lambda kv: int(kv[0][1:]))},
}
#: 로비 범례 판(글자, 갈래). 판 하나가 LABEL_SIZE × LEGEND_SCALE 이고 위에서 아래로 쌓는다.
LEGEND = (("B 병동", "B"), ("C 병실", "C"), ("D 병상", "D"))
#: 재범 9/25(오버헤드 컷에 원): 복도 북쪽 계단 아래 로비 한가운데, 반듯하게(회전 없음). 판 하나 1.8 × 0.45 m.
LEGEND_SCALE = 3.0
LEGEND_GAP = 0.10
#: 판 방향. 복도 축에 맞춰 돌리지 않는다(재범 "깔끔하게").
LEGEND_YAW = 0.0
#: 범례를 찾는 상자(x0, y0, x1, y1)와 찾는 간격(m), 먼저 보는 자리. 재범이 짚은 복도 북쪽 계단 아래 로비 한가운데다.
LEGEND_SEARCH = (6.4, 6.4, 8.2, 8.0)
LEGEND_STEP = 0.1
LEGEND_PREFERRED = (7.4, 7.2)
#: 더미 루프에서 이만큼 떨어뜨린다(m). 합본 모양 차체가 판을 덮으면 안 읽힌다. 보행자 선은 피하지 않는다(재범 9/25:
#: 짚은 자리를 보행자가 지난다 — 바닥 판 위를 사람이 걷는 것은 병원에서 흔하다).
LEGEND_CLEARANCE = 0.8
#: 테이블 윗면 색(시각 재질만). D 협탁은 앵커 `bedside_tables` 의 prim 이다.
STATION_B_TABLE_PRIM = STATION_B_TABLE["prim"]


def zone_class(zone):
    """정차 칸 zone → 목적지 갈래("B"·"C"·"D"), 목적지가 아니면 None."""
    if zone == "station_b":
        return "B"
    if zone in ROOM_TABLE_ZONES:
        return "C"
    if zone in BED_ZONE.values():
        return "D"
    return None


def text_class(text):
    """글자 판 글자 → 갈래. 범례 글자도 첫 글자로 가른다."""
    for legend_text, cls in LEGEND:
        if text == legend_text:
            return cls
    if text == "B":
        return "B"
    if text in ROOM_TABLE_ZONES.values():
        return "C"
    if text in BED_ZONE:
        return "D"
    return None


def label_style(text):
    """(바탕 색, 글자 색). 아틀라스가 이 값으로 칸을 칠한다."""
    background = CLASS_COLORS.get(text_class(text), OTHER_COLOR)
    return background, (LIGHT_INK if background in (BLUE, GREEN) else DARK_INK)


def atlas_texts():
    """아틀라스에 있어야 하는 글자 전부(칸 글자 + 범례)."""
    return sorted(set(BAY_LABELS.values()) | {text for text, _cls in LEGEND})

#: 조제실 워크셀(M0609·선반·조제기)을 덮는 상자, 병원 좌표 (x0, y0, x1, y1). 약국 원점
#: `base_scene.HOSPITAL_ORIGIN_A` (0.25, 10.53) 에 layout_v2 의 선반(−1.15..−0.15, y 0.91)·레일 행정 2.8 m·
#: 투입구(0.9–1.15, 0.56–0.7)를 넉넉히 덮었다. 이 안에는 아무것도 두지 않는다.
PHARMACY_KEEP_OUT = (-2.0, 9.0, 3.5, 13.0)


_ROUTE_LINE = re.compile(r"^\s*-\s*\{from:\s*([A-Za-z0-9_]+),\s*to:\s*([A-Za-z0-9_]+),\s*waypoints:\s*\[(.*)\]\}\s*$")
_POINT = re.compile(r"\[\s*(-?[0-9.]+(?:e-?[0-9]+)?)\s*,\s*(-?[0-9.]+(?:e-?[0-9]+)?)\s*\]")


def parse_routes_text(text):
    """`routes.hospital.yaml`(생성물, 한 줄에 한 쌍) → [{from, to, waypoints}]. PyYAML 없이 읽는다.

    CI 의 Evidence 잡에는 PyYAML 이 없다(#669 런 35962201106, `import yaml` 에서 멈췄다). 파일은 생성기
    `hospital_nav.routes_yaml_text` 가 쓰는 모양 그대로라 그 모양만 읽는다. `routes:` 아래 다른 모양의 줄이 있으면
    ValueError — 조용히 건너뛰지 않는다.
    """
    out, inside = [], False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped == "routes:":
            inside = True
            continue
        if not inside:
            continue
        match = _ROUTE_LINE.match(line)
        if not match:
            raise ValueError(f"routes 줄을 못 읽었다: {line!r}")
        points = [[float(x), float(y)] for x, y in _POINT.findall(match.group(3))]
        out.append({"from": match.group(1), "to": match.group(2), "waypoints": points})
    return out


def full_route(routes, zones, start, end):
    """경로 파일의 중간 점 앞뒤로 출발·도착 자세를 붙인 (x, y) 목록. 길이 0 인 마디는 뺀다."""
    for route in routes:
        if route["from"] == start and route["to"] == end:
            points = [tuple(zones[start][:2])] + [tuple(p) for p in route["waypoints"]] + [tuple(zones[end][:2])]
            out = [points[0]]
            for point in points[1:]:
                if math.dist(point, out[-1]) > 1e-6:
                    out.append(point)
            return out
    raise KeyError(f"routes 에 {start} → {end} 가 없다")


def _normal(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    return -dy / length, dx / length          # 진행 방향 왼쪽


def offset_polyline(points, offset):
    """진행 방향 왼쪽으로 `offset` 만큼 옮긴 선. 모서리는 미터로 잇고 `MITER_LIMIT` 에서 자른다."""
    if offset == 0.0:
        return list(points)
    out = []
    for i, point in enumerate(points):
        normals = []
        if i > 0:
            normals.append(_normal(points[i - 1], point))
        if i + 1 < len(points):
            normals.append(_normal(point, points[i + 1]))
        nx = sum(n[0] for n in normals) / len(normals)
        ny = sum(n[1] for n in normals) / len(normals)
        length = math.hypot(nx, ny)
        if length < 1e-9:                     # 되돌아가는 모서리: 앞 마디 법선을 쓴다
            nx, ny, length = normals[0][0], normals[0][1], 1.0
        scale = min(MITER_LIMIT, 1.0 / length) / length
        out.append((point[0] + nx * scale * offset, point[1] + ny * scale * offset))
    return out


def strip(points, width, lift):
    """선 → 띠 메시 (점들, 면 꼭짓점 수, 면 꼭짓점 번호). 위에서 보면 반시계(법선 +z)."""
    half = width / 2.0
    left = offset_polyline(points, +half)
    right = offset_polyline(points, -half)
    vertices = []
    for l_pt, r_pt in zip(left, right, strict=True):
        vertices += [(r_pt[0], r_pt[1], lift), (l_pt[0], l_pt[1], lift)]
    counts, indices = [], []
    for i in range(len(points) - 1):
        r0, l0, r1, l1 = 2 * i, 2 * i + 1, 2 * i + 2, 2 * i + 3
        counts.append(4)
        indices += [r0, r1, l1, l0]
    return vertices, counts, indices


def _body_axes(yaw):
    return (math.cos(yaw), math.sin(yaw)), (-math.sin(yaw), math.cos(yaw))


def charging_bay_rect(pose, body_length, body_width):
    """도크 충전 칸 (x0, y0, x1, y1): 벽 밑선(`FLOOR_WALL_Y`)에서 차체 앞 끝(+`BAY_MARGIN`)까지, 차체 폭 + 여유.

    도크는 차체가 벽 반대(−y)를 보고 선다(yaw −90°). 칸 안에 도크 모듈(보조 테이블·컨베이어 끝)이 든다.
    """
    x, y, yaw = pose
    tip_y = y + math.sin(yaw) * (body_length / 2.0 + BAY_MARGIN)
    half_w = body_width / 2.0 + BAY_MARGIN
    y0, y1 = sorted((tip_y, FLOOR_WALL_Y))
    return x - half_w, y0, x + half_w, y1


def rect_ring(rect, lift=LIFT_BAY):
    """축에 나란한 사각 (x0, y0, x1, y1) 둘레 테두리. `bay_ring` 과 같은 굵기·순서(위에서 보면 반시계)."""
    x0, y0, x1, y1 = rect
    s = BAY_STROKE
    outer = [(x1 + s, y1 + s, lift), (x0 - s, y1 + s, lift), (x0 - s, y0 - s, lift), (x1 + s, y0 - s, lift)]
    inner = [(x1, y1, lift), (x0, y1, lift), (x0, y0, lift), (x1, y0, lift)]
    vertices = outer + inner
    counts, indices = [], []
    for k in range(4):
        o0, o1, i0, i1 = k, (k + 1) % 4, 4 + k, 4 + (k + 1) % 4
        counts.append(4)
        indices += [o0, o1, i1, i0]
    return vertices, counts, indices


def bay_ring(pose, body_length, body_width, lift=LIFT_BAY):
    """정차 자세 둘레 테두리(네 변을 한 고리로). 몸체 밖으로 `BAY_MARGIN` 띄운다."""
    x, y, yaw = pose
    forward, left = _body_axes(yaw)
    half_l = body_length / 2.0 + BAY_MARGIN
    half_w = body_width / 2.0 + BAY_MARGIN

    def at(a, b):
        return (x + forward[0] * a + left[0] * b, y + forward[1] * a + left[1] * b, lift)

    outer = [at(+half_l + BAY_STROKE, +half_w + BAY_STROKE), at(-half_l - BAY_STROKE, +half_w + BAY_STROKE),
             at(-half_l - BAY_STROKE, -half_w - BAY_STROKE), at(+half_l + BAY_STROKE, -half_w - BAY_STROKE)]
    inner = [at(+half_l, +half_w), at(-half_l, +half_w), at(-half_l, -half_w), at(+half_l, -half_w)]
    vertices = outer + inner
    counts, indices = [], []
    for k in range(4):
        o0, o1, i0, i1 = k, (k + 1) % 4, 4 + k, 4 + (k + 1) % 4
        counts.append(4)
        # 고리를 반시계로 돌므로 바깥 k → 바깥 k+1 → 안 k+1 → 안 k 가 위에서 보면 반시계다(법선 +z).
        # 반대로 돌면 법선이 아래를 봐 한쪽 면만 그리는 판이 통째로 안 보인다(시험이 잡았다).
        indices += [o0, o1, i1, i0]
    return vertices, counts, indices


def label_centres(pose, body_length, body_width):
    """글자 판을 둘 후보 자리(앞, 뒤, 왼쪽, 오른쪽 순). 테두리 밖으로 `LABEL_GAP` 띄운다."""
    x, y, yaw = pose
    forward, left = _body_axes(yaw)
    out_l = body_length / 2.0 + BAY_MARGIN + BAY_STROKE + LABEL_GAP + LABEL_SIZE[1] / 2.0
    out_w = body_width / 2.0 + BAY_MARGIN + BAY_STROKE + LABEL_GAP + LABEL_SIZE[1] / 2.0
    return [(x + forward[0] * out_l, y + forward[1] * out_l), (x - forward[0] * out_l, y - forward[1] * out_l),
            (x + left[0] * out_w, y + left[1] * out_w), (x - left[0] * out_w, y - left[1] * out_w)]


def label_quad(centre, lift=LIFT_LABEL):
    """글자 판 네 점. **월드 +y 가 글자 위쪽**이다 — floor_top 카메라가 남쪽에서 북쪽을 본다.
    점 순서는 st (0,0),(1,0),(1,1),(0,1) 이고 위에서 보면 반시계다."""
    cx, cy = centre
    hx, hy = LABEL_SIZE[0] / 2.0, LABEL_SIZE[1] / 2.0
    return [(cx - hx, cy - hy, lift), (cx + hx, cy - hy, lift), (cx + hx, cy + hy, lift), (cx - hx, cy + hy, lift)]


def overlaps(poly_a, poly_b):
    """볼록 다각형 둘이 겹치는가(분리축 정리). 닿기만 한 것은 겹침이 아니다."""
    for poly in (poly_a, poly_b):
        for i in range(len(poly)):
            ax, ay = poly[i][:2]
            bx, by = poly[(i + 1) % len(poly)][:2]
            nx, ny = -(by - ay), bx - ax
            a_proj = [nx * q[0] + ny * q[1] for q in poly_a]
            b_proj = [nx * q[0] + ny * q[1] for q in poly_b]
            if max(a_proj) <= min(b_proj) + 1e-9 or max(b_proj) <= min(a_proj) + 1e-9:
                return False
    return True


def in_keep_out(x, y, box=PHARMACY_KEEP_OUT):
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


def on_free_floor(grid, points):
    """모든 점이 지도의 빈 칸 위인가. 가구 밑에 깔린 표시는 안 보이고, 벽 속이면 틀린 것이다."""
    return all(not grid.is_blocked(p[0], p[1]) for p in points)


def plan(routes, zones, grid, body_length, body_width, atlas):
    """세울 것 전부. 순수 함수다.

    반환 {"strips": [(이름, 점들, 면 수, 번호, 색)], "labels": [(구역, 글자, 네 점, 아틀라스 uv)],
    "skipped": [(무엇, 까닭)], "merged": [(구역, 이긴 구역)]}. 빠진 것은 조용히 버리지 않고 까닭을 남긴다.

    **겹치는 정차 칸은 먼저 선 칸이 이긴다**(`BAY_LABELS` 순서). 같은 높이 판이 겹치면 깜빡이고, 두 테두리가
    엇갈려 그려지면 어느 칸인지 읽히지 않는다. 적재↔도크 1, A2↔A4, B3↔B6 이 그렇다 — 같이 서는 일이 없는
    다른 침상·자리라 테두리 하나로 충분하다. 진 칸도 **글자는 남긴다**(`merged` 는 경고가 아니라 설계다).
    """
    strips, labels, skipped, merged = [], [], [], []
    rings = []          # (구역, 바깥 네 점)
    placed_labels = []
    for name, start, end, color, lift in GUIDE_LINES:
        try:
            route = full_route(routes, zones, start, end)
        except KeyError as error:
            skipped.append((f"line:{name}", str(error)))
            continue
        line = offset_polyline(route, LINE_OFFSETS[name])
        points, counts, indices = strip(line, LINE_WIDTH, lift)
        if any(in_keep_out(p[0], p[1]) for p in points):
            skipped.append((f"line:{name}", "조제실 워크셀 안을 지난다"))
            continue
        strips.append((name, points, counts, indices, color))
    for zone, text in BAY_LABELS.items():
        if zone not in zones:
            skipped.append((f"bay:{zone}", "zones 에 없다"))
            continue
        x, y, _z, yaw = zones[zone]
        if zone in CHARGING_ZONES:
            # 도크 넷은 충전 칸 하나로 통일(재범 9/25): 벽 밑선부터 차체 앞 끝까지(`charging_bay_rect`).
            points, counts, indices = rect_ring(charging_bay_rect((x, y, yaw), body_length, body_width))
        else:
            points, counts, indices = bay_ring((x, y, yaw), body_length, body_width)
        if any(in_keep_out(p[0], p[1]) for p in points):
            skipped.append((f"bay:{zone}", "조제실 워크셀 안이다"))
            continue
        outer = points[:4]
        # 충전 칸은 네 도크가 같은 모양이어야 해서 겹쳐도 늘 그린다(적재 칸과 dock_1 이 모서리를 조금 나눈다).
        winner = None if zone in CHARGING_ZONES else next(
            (other for other, ring in rings if overlaps(outer, ring)), None)
        if winner is None:
            strips.append((f"bay_{zone}", points, counts, indices,
                           CLASS_COLORS.get(zone_class(zone), OTHER_COLOR)))
            rings.append((zone, outer))
        else:
            merged.append((zone, winner))
        uv = atlas.get(text)
        if uv is None:
            skipped.append((f"label:{zone}", f"아틀라스에 '{text}' 가 없다"))
            continue
        for centre in label_centres((x, y, yaw), body_length, body_width):
            quad = label_quad(centre)
            if (on_free_floor(grid, quad) and not any(in_keep_out(p[0], p[1]) for p in quad)
                    and not any(overlaps(quad, other) for other in placed_labels)):
                labels.append((zone, text, quad, uv))
                placed_labels.append(quad)
                break
        else:
            skipped.append((f"label:{zone}", "칸 네 옆이 다 막혔거나 다른 글자와 겹친다"))
    legend = legend_plan(grid, strips, placed_labels, atlas)
    if legend is None:
        skipped.append(("legend", "로비에 빈 자리가 없다"))
    else:
        labels += legend
    return {"strips": strips, "labels": labels, "skipped": skipped, "merged": merged}


def _segment_distance(p, a, b):
    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(p[0] - ax - t * dx, p[1] - ay - t * dy)


def dummy_segments():
    """더미 루프 변 [(a, b)]. 범례가 피한다(보행자 선은 피하지 않는다)."""
    out = []
    for _name, points in DUMMY_LOOPS:
        out += [(points[i], points[(i + 1) % len(points)]) for i in range(len(points))]
    return out


def _inside(point, polygon):
    """점이 볼록 다각형 안인가(더미 루프 안쪽 — 가짜 AMR 이 도는 자리)."""
    signs = []
    for i in range(len(polygon)):
        ax, ay = polygon[i]
        bx, by = polygon[(i + 1) % len(polygon)]
        signs.append((bx - ax) * (point[1] - ay) - (by - ay) * (point[0] - ax) > 0)
    return all(signs) or not any(signs)


def legend_quads(centre, yaw=LEGEND_YAW):
    """범례 판 셋의 네 점(위에서 아래로 LEGEND 순서). 판 크기는 LABEL_SIZE × LEGEND_SCALE.

    가운데를 축으로 `yaw` 돌린다(오버헤드 뷰 정방향)."""
    w, h = LABEL_SIZE[0] * LEGEND_SCALE, LABEL_SIZE[1] * LEGEND_SCALE
    total = len(LEGEND) * h + (len(LEGEND) - 1) * LEGEND_GAP
    top = total / 2.0
    c, s = math.cos(yaw), math.sin(yaw)

    def at(lx, ly):
        return (centre[0] + c * lx - s * ly, centre[1] + s * lx + c * ly, LIFT_LABEL)

    quads = []
    for i in range(len(LEGEND)):
        cy = top - h / 2.0 - i * (h + LEGEND_GAP)
        quads.append([at(-w / 2.0, cy - h / 2.0), at(w / 2.0, cy - h / 2.0),
                      at(w / 2.0, cy + h / 2.0), at(-w / 2.0, cy + h / 2.0)])
    return quads


def _quad_point(quad, u, v):
    """네 점(0→1 이 x, 0→3 이 y) 판 안의 (u, v) ∈ [0, 1]² 점."""
    a, b, _c, d = quad
    return (a[0] + (b[0] - a[0]) * u + (d[0] - a[0]) * v, a[1] + (b[1] - a[1]) * u + (d[1] - a[1]) * v, a[2])


def legend_plan(grid, strips, placed_labels, atlas):
    """로비 바닥 범례 판 [("legend", 글자, 네 점, uv)] 또는 None. 순수 함수다.

    `LEGEND_SEARCH` 상자를 `LEGEND_STEP` 격자로 훑어 `LEGEND_PREFERRED` 에 가까운 자리부터 본다. 조건: 네 점이
    다 빈 바닥, 조제실 밖, 선·칸·다른 글자와 안 겹침, 더미 루프 변에서 `LEGEND_CLEARANCE` 이상, 더미 루프
    안쪽이 아님. 첫 자리가 이긴다(같은 입력이면 같은 자리).
    """
    if any(text not in atlas for text, _cls in LEGEND):
        return None
    faces = []
    for _name, points, counts, indices, _color in strips:
        k = 0
        for n in counts:
            faces.append([points[i] for i in indices[k:k + n]])
            k += n
    loops = [points for _name, points in DUMMY_LOOPS]
    x0, y0, x1, y1 = LEGEND_SEARCH
    candidates = [(x0 + i * LEGEND_STEP, y0 + j * LEGEND_STEP)
                  for i in range(int(round((x1 - x0) / LEGEND_STEP)) + 1)
                  for j in range(int(round((y1 - y0) / LEGEND_STEP)) + 1)]
    candidates.sort(key=lambda c: (math.dist(c, LEGEND_PREFERRED), c))
    for centre in candidates:
        quads = legend_quads(centre)
        corners = [p for q in quads for p in q]
        # 판이 커서(2.4 m) 네 모서리만 보면 데스크 같은 가구 위로 걸칠 수 있다 — 판 안을 0.1 m 격자로 본다.
        inner = [_quad_point(q, u / 24.0, v / 6.0) for q in quads for u in range(25) for v in range(7)]
        if not on_free_floor(grid, inner) or any(in_keep_out(p[0], p[1]) for p in corners):
            continue
        if any(overlaps(q, f) for q in quads for f in faces):
            continue
        if any(overlaps(q, o) for q in quads for o in placed_labels):
            continue
        probe = corners + [centre]
        if any(_segment_distance(p[:2], a, b) < LEGEND_CLEARANCE for p in probe for a, b in dummy_segments()):
            continue
        if any(_inside(p[:2], loop) for p in probe for loop in loops):
            continue
        return [("legend", text, quad, atlas[text]) for (text, _cls), quad in zip(LEGEND, quads, strict=True)]
    return None


def table_tints(bedside_tables, room_table_prims=()):
    """[(테이블 prim, 색)] — B 테이블 파랑, C 테이블 초록, D 협탁 노랑. 시각 재질만 덮는다(순수 함수).

    bedside_tables: 앵커 JSON 의 `bedside_tables`({D1: {prim, …}}). room_table_prims: C 테이블 prim 목록(없으면 빈 값).
    """
    out = [(STATION_B_TABLE_PRIM, CLASS_COLORS["B"])]
    out += [(prim, CLASS_COLORS["C"]) for prim in room_table_prims]
    out += [(bedside_tables[label]["prim"], CLASS_COLORS["D"])
            for label in sorted(bedside_tables, key=lambda k: int(k[1:]))]
    return out


def build_table_tints(stage, root, tints, log=print):
    """테이블 prim 에 단색 재질을 **더 강하게**(strongerThanDescendants) 묶는다. 물리·기하·USD 파일은 안 건드린다.

    갈래마다 재질 하나(최대 셋). 없는 prim 은 건너뛰고 한 줄 남긴다. 반환은 칠한 prim 수.
    """
    from pxr import Gf, Sdf, UsdShade

    looks, painted, missing = {}, 0, []
    for prim_path, color in tints:
        prim = stage.GetPrimAtPath(prim_path)
        if not prim.IsValid():
            missing.append(prim_path)
            continue
        if color not in looks:
            name = {BLUE: "TableB", GREEN: "TableC", YELLOW: "TableD"}.get(color, f"Table{len(looks)}")
            material = UsdShade.Material.Define(stage, f"{root}/Looks/{name}")
            shader = UsdShade.Shader.Define(stage, f"{root}/Looks/{name}/Surface")
            shader.CreateIdAttr("UsdPreviewSurface")
            shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
            shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.6)
            material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
            looks[color] = material
        UsdShade.MaterialBindingAPI.Apply(prim).Bind(looks[color], UsdShade.Tokens.strongerThanDescendants)
        painted += 1
    if missing:
        log(f"WARN hospital_decor table tint missing prims={missing}")
    log(f"hospital_decor table_tints painted={painted} missing={len(missing)} materials={len(looks)} "
        f"visual_only=true")
    return painted


def merge(parts):
    """[(점들, 면 수, 번호)] → 한 메시. 번호를 이어 붙인다."""
    vertices, counts, indices = [], [], []
    for points, part_counts, part_indices in parts:
        base = len(vertices)
        vertices += list(points)
        counts += list(part_counts)
        indices += [base + i for i in part_indices]
    return vertices, counts, indices


def build(stage, root, decor, atlas_image, log=print):
    """색 띠 메시 하나(꼭짓점 색) + 글자 판 메시 하나(아틀라스). 물리 API 없음. 반환 (띠 수, 글자 수)."""
    from pxr import Gf, Sdf, UsdGeom, UsdShade, Vt

    UsdGeom.Xform.Define(stage, root)

    # 색 띠: 면마다 색을 하나씩(uniform) 준다. 재질은 displayColor 를 읽는 PreviewSurface 하나.
    parts, face_colors = [], []
    for _name, points, counts, indices, color in decor["strips"]:
        parts.append((points, counts, indices))
        face_colors += [color] * len(counts)
    if parts:
        vertices, counts, indices = merge(parts)
        mesh = UsdGeom.Mesh.Define(stage, f"{root}/FloorStrips")
        mesh.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(*p) for p in vertices]))
        mesh.CreateFaceVertexCountsAttr(counts)
        mesh.CreateFaceVertexIndicesAttr(indices)
        mesh.CreateNormalsAttr(Vt.Vec3fArray([Gf.Vec3f(0.0, 0.0, 1.0)] * len(vertices)))
        mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
        mesh.CreateDoubleSidedAttr(False)
        colors = UsdGeom.PrimvarsAPI(mesh).CreatePrimvar("displayColor", Sdf.ValueTypeNames.Color3fArray,
                                                          UsdGeom.Tokens.uniform)
        colors.Set(Vt.Vec3fArray([Gf.Vec3f(*c) for c in face_colors]))
        material = UsdShade.Material.Define(stage, f"{root}/Looks/Strips")
        shader = UsdShade.Shader.Define(stage, f"{root}/Looks/Strips/Surface")
        shader.CreateIdAttr("UsdPreviewSurface")
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.6)
        reader = UsdShade.Shader.Define(stage, f"{root}/Looks/Strips/Color")
        reader.CreateIdAttr("UsdPrimvarReader_float3")
        reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("displayColor")
        reader.CreateOutput("result", Sdf.ValueTypeNames.Float3)
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(
            reader.ConnectableAPI(), "result")
        material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
        UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)

    # 글자 판: 판마다 네 점, st 는 아틀라스 칸. 재질 하나, 텍스처 한 장.
    if decor["labels"]:
        vertices, counts, indices, st = [], [], [], []
        for _zone, _text, quad, (u0, v0, u1, v1) in decor["labels"]:
            base = len(vertices)
            vertices += quad
            counts.append(4)
            indices += [base, base + 1, base + 2, base + 3]
            st += [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
        mesh = UsdGeom.Mesh.Define(stage, f"{root}/FloorLabels")
        mesh.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(*p) for p in vertices]))
        mesh.CreateFaceVertexCountsAttr(counts)
        mesh.CreateFaceVertexIndicesAttr(indices)
        mesh.CreateNormalsAttr(Vt.Vec3fArray([Gf.Vec3f(0.0, 0.0, 1.0)] * len(vertices)))
        mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
        mesh.CreateDoubleSidedAttr(False)
        primvar = UsdGeom.PrimvarsAPI(mesh).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray,
                                                           UsdGeom.Tokens.vertex)
        primvar.Set(Vt.Vec2fArray([Gf.Vec2f(*uv) for uv in st]))
        material = UsdShade.Material.Define(stage, f"{root}/Looks/Labels")
        shader = UsdShade.Shader.Define(stage, f"{root}/Looks/Labels/Surface")
        shader.CreateIdAttr("UsdPreviewSurface")
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.6)
        reader = UsdShade.Shader.Define(stage, f"{root}/Looks/Labels/St")
        reader.CreateIdAttr("UsdPrimvarReader_float2")
        reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
        texture = UsdShade.Shader.Define(stage, f"{root}/Looks/Labels/Atlas")
        texture.CreateIdAttr("UsdUVTexture")
        texture.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(str(atlas_image))
        texture.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(reader.ConnectableAPI(), "result")
        texture.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(
            texture.ConnectableAPI(), "rgb")
        material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
        UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)

    for what, why in decor["skipped"]:
        log(f"WARN hospital_decor skipped {what}: {why}")
    log(f"hospital_decor strips={len(decor['strips'])} labels={len(decor['labels'])} "
        f"skipped={len(decor['skipped'])} merged={[f'{a}<{b}' for a, b in decor.get('merged', [])]} "
        f"meshes=2 materials=2 atlas={atlas_image} "
        f"lift_mm={LIFT_LINES[0] * 1000:.1f}-{LIFT_LABEL * 1000:.1f} visual_only=true")
    return len(decor["strips"]), len(decor["labels"])


# ---- 도크 충전 스테이션 표시(재범 채택 9/24, 벽 부착 9/25) ---------------------------------------------------------
#
# 도크 넷(A1–A4)에 "충전 스테이션" 을 보인다(재범 9/25 02:5x 질책 반영: **벽에 붙인다**).
# - **벽 판**: 각 도크 모듈(보조 테이블, 앵커 `outlets` A1–A4 `shelf`) **오른쪽 옆 벽면**, 중심 높이 1.1 m, 0.5 m 판
#   (⚡ + A1…A4), 방 쪽(도크 차체가 보는 쪽)을 향한다. **벽 앞면 실측(마클1 9/25, Isaac pxr BBoxCache, 원문
#   master01 ~/markle_tmp/m1-bbox-0925.txt)**: 도크 뒤는 창벽 `Geo_M2_WindowWallRight2`·`WindowWallLeft2`·
#   `WindowWallRight_559`·`WindowWallLeft_562` 앞면 **y 5.3500**(x −9.95…2.54), 위 벽 `Geo_W_WallBase2_11` 5.3518,
#   걸레받이 `TrimStrate*` 앞면 5.335(z 0–0.16). 판 앞면을 `WALL_FRONT_Y`(5.345, 벽 앞 5 mm)에 두고 옆 테두리를
#   `WALL_INSIDE_Y`(5.40)까지 벽 속으로 넣어 박혀 보이게 한다. 9/24 판은 "벽이 없다" 고 잘못 읽어 테이블 위
#   기둥에 달았고, 9/25 첫 수정(5.295)은 지도 칸(0.05 m)으로 추정해 5.5 cm 떴다.
# - **바닥 칸**: 벽 밑선(걸레받이 앞면, `FLOOR_WALL_Y`)에서 도크 차체 앞 끝까지 차체 폭의 짙은 회색 칸 + 정차 중심에 ⚡.
#   유도선(1.0 mm)은 칸(1.32 mm) 아래로 들어가 칸에서 끝난다.
# 벽 판은 0.85 m 위라 스캔 띠(0.1–0.6 m) 밖이다. 물리 없음. 메시 하나·재질 하나·텍스처 한 장(charging.png).

#: (도크 zone, 표지 글자). 앵커 `outlets` 의 A1–A4 와 같은 x 다.
CHARGING_DOCKS = (("dock_1", "A1"), ("dock_2", "A2"), ("dock_3", "A3"), ("dock_4", "A4"))
CHARGING_ZONES = frozenset(zone for zone, _text in CHARGING_DOCKS)
#: 아틀라스 칸 순서(`make_charging_atlas.py`). 표지 넷, 바닥 ⚡, 단색(테두리·바닥 칸).
CHARGING_CELLS = ("A1", "A2", "A3", "A4", "floor", "post")
#: 실측 벽 앞면(창벽)과 걸레받이 앞면(마클1 9/25 실측), 판 앞면·테두리 끝·바닥 칸 뒷변 y.
WALL_FACE_MEASURED_Y = 5.350
TRIM_FACE_MEASURED_Y = 5.335
WALL_FRONT_Y = WALL_FACE_MEASURED_Y - 0.005
WALL_INSIDE_Y = 5.40
FLOOR_WALL_Y = TRIM_FACE_MEASURED_Y - 0.005
#: 벽 판 한 변(m), 중심 높이(m), 모듈 오른쪽 끝과의 틈(m).
SIGN_SIZE = 0.50
SIGN_CENTRE_Z = 1.10
SIGN_GAP = 0.05
#: 바닥 ⚡ 한 변(m), 바닥 칸·⚡ 들어 올림(칸 1.3 mm·글자 1.4 mm 사이, 서로 다르게).
FLOOR_MARK_SIZE = 0.60
LIFT_FILL = 0.00132
LIFT_MARK = 0.00136


def _vertical_quad(centre, normal_xy, width, bottom, top):
    """세운 판 네 점. 앞(법선 쪽)에서 보면 반시계 — 왼아래, 오른아래, 오른위, 왼위(st (0,0)…(0,1))."""
    nx, ny = normal_xy
    rx, ry = -ny, nx                         # 오른쪽 = 위(+z) × 법선
    cx, cy = centre
    half = width / 2.0
    return [(cx - rx * half, cy - ry * half, bottom), (cx + rx * half, cy + ry * half, bottom),
            (cx + rx * half, cy + ry * half, top), (cx - rx * half, cy - ry * half, top)]


def _outward(quad, centre):
    """면이 `centre` 반대쪽(밖)을 보게 점 순서를 맞춘다."""
    a, b, c = quad[0], quad[1], quad[2]
    e1 = [b[i] - a[i] for i in range(3)]
    e2 = [c[i] - a[i] for i in range(3)]
    n = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
    mid = [sum(p[i] for p in quad) / 4.0 for i in range(3)]
    if sum(n[i] * (mid[i] - centre[i]) for i in range(3)) < 0:
        return list(reversed(quad))
    return quad


def dark_uv(uv):
    """아틀라스 `floor` 칸 왼위 모서리의 짙은 바탕(60, 60, 60) 조각 — 테두리·번개가 없는 곳. 바닥 칸 단색으로 쓴다."""
    u0, v0, u1, v1 = uv["floor"]
    du, dv = u1 - u0, v1 - v0
    return (u0 + du * 0.08, v1 - dv * 0.14, u0 + du * 0.14, v1 - dv * 0.08)


def charging_plan(zones, uv, tables, body_length, body_width):
    """[(이름, 네 점, (u0, v0, u1, v1))] 과 [(무엇, 까닭)]. 순수 함수다.

    tables: 앵커 `outlets`({A1: {shelf: {min, max}}, …}) — 도크 모듈(보조 테이블) 자리.
    """
    items, skipped = [], []
    for zone, text in CHARGING_DOCKS:
        if zone not in zones or text not in tables:
            skipped.append((f"charging:{zone}", "zones 나 앵커 outlets 에 없다"))
            continue
        x, y, _z, yaw = zones[zone]
        if in_keep_out(x, y):
            skipped.append((f"charging:{zone}", "조제실 워크셀 안이다"))
            continue
        forward = (math.cos(yaw), math.sin(yaw))          # 도크 차체가 보는 쪽 = 벽 판이 향하는 쪽(방 쪽)
        half = SIGN_SIZE / 2.0
        table = tables[text]["shelf"]
        # 도크가 모듈 옆 벽 앞에 서면(재범 9/25 "전부 벽에 붙여") 판을 도크 정면에, 모듈 앞에 서면(옛 zones) 모듈
        # 오른쪽 옆에 둔다(벽을 보고 섰을 때 오른쪽 = +x).
        clear_of_module = x - body_width / 2.0 >= table["max"][0] or x + body_width / 2.0 <= table["min"][0]
        sign_x = x if clear_of_module else table["max"][0] + SIGN_GAP + half
        front = _vertical_quad((sign_x, WALL_FRONT_Y), forward, SIGN_SIZE, SIGN_CENTRE_Z - half,
                               SIGN_CENTRE_Z + half)
        items.append((f"sign_{zone}", front, tuple(uv[text])))
        # 옆 테두리 넷: 앞면 둘레에서 벽 속(`WALL_INSIDE_Y`)까지. 판이 벽에 박혀 두께가 보인다.
        depth = WALL_INSIDE_Y - WALL_FRONT_Y
        back = [(p[0] - forward[0] * depth, p[1] - forward[1] * depth, p[2]) for p in front]
        centre = (sign_x, (WALL_FRONT_Y + WALL_INSIDE_Y) / 2.0, SIGN_CENTRE_Z)
        for k, side in enumerate(("bottom", "right", "top", "left")):
            a, b = front[k], front[(k + 1) % 4]
            a2, b2 = back[k], back[(k + 1) % 4]
            items.append((f"edge_{side}_{zone}", _outward([a, b, b2, a2], centre), tuple(uv["post"])))
        # 바닥 칸: `charging_bay_rect` 한 장을 짙게 칠한다(병원 바닥 회색과 구분되게, 9/25 회차74: 회색이라 안 보였다).
        # 유도선(1.0–1.2 mm)은 칸(1.32 mm) 아래로 들어가 칸 앞변에서 끝나 보인다.
        x0, y0, x1, y1 = charging_bay_rect((x, y, yaw), body_length, body_width)
        items.append((f"fill_{zone}", [(x0, y0, LIFT_FILL), (x1, y0, LIFT_FILL), (x1, y1, LIFT_FILL),
                                       (x0, y1, LIFT_FILL)], dark_uv(uv)))
        # ⚡A# 판: 도크 x, 벽 밑선에 붙인다(칸의 벽 쪽 끝). 도크가 모듈 앞에 서는 옛 zones 면 모듈 앞으로 물린다
        # (모듈 윗면 0.37 m 가 위에서 가린다).
        m = FLOOR_MARK_SIZE / 2.0
        plate_y = FLOOR_WALL_Y - 0.05 - m if clear_of_module else table["min"][1] - 0.05 - m
        items.append((f"floor_{zone}", [(x - m, plate_y - m, LIFT_MARK), (x + m, plate_y - m, LIFT_MARK),
                                        (x + m, plate_y + m, LIFT_MARK), (x - m, plate_y + m, LIFT_MARK)],
                      tuple(uv[text])))
    return items, skipped


def build_charging(stage, root, items, skipped, image, log=print):
    """충전 표시 메시 하나(아틀라스). 물리 API 없음. 반환은 세운 판 수."""
    from pxr import Gf, Sdf, UsdGeom, UsdShade, Vt

    UsdGeom.Xform.Define(stage, root)
    if items:
        vertices, counts, indices, st, normals = [], [], [], [], []
        for _name, quad, (u0, v0, u1, v1) in items:
            base = len(vertices)
            vertices += quad
            counts.append(4)
            indices += [base, base + 1, base + 2, base + 3]
            st += [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
            a, b, c = quad[0], quad[1], quad[2]
            e1 = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
            e2 = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
            n = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
            length = math.sqrt(sum(v * v for v in n)) or 1.0
            normals += [tuple(v / length for v in n)] * 4
        mesh = UsdGeom.Mesh.Define(stage, f"{root}/ChargingMarks")
        mesh.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(*p) for p in vertices]))
        mesh.CreateFaceVertexCountsAttr(counts)
        mesh.CreateFaceVertexIndicesAttr(indices)
        mesh.CreateNormalsAttr(Vt.Vec3fArray([Gf.Vec3f(*n) for n in normals]))
        mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
        mesh.CreateDoubleSidedAttr(False)
        primvar = UsdGeom.PrimvarsAPI(mesh).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray,
                                                           UsdGeom.Tokens.vertex)
        primvar.Set(Vt.Vec2fArray([Gf.Vec2f(*uv) for uv in st]))
        material = UsdShade.Material.Define(stage, f"{root}/Looks/Charging")
        shader = UsdShade.Shader.Define(stage, f"{root}/Looks/Charging/Surface")
        shader.CreateIdAttr("UsdPreviewSurface")
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.6)
        reader = UsdShade.Shader.Define(stage, f"{root}/Looks/Charging/St")
        reader.CreateIdAttr("UsdPrimvarReader_float2")
        reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
        texture = UsdShade.Shader.Define(stage, f"{root}/Looks/Charging/Atlas")
        texture.CreateIdAttr("UsdUVTexture")
        texture.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(str(image))
        texture.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(reader.ConnectableAPI(), "result")
        texture.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(
            texture.ConnectableAPI(), "rgb")
        material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
        UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)
    for what, why in skipped:
        log(f"WARN hospital_decor skipped {what}: {why}")
    log(f"hospital_decor charging quads={len(items)} docks={[z for z, _t in CHARGING_DOCKS]} "
        f"sign={SIGN_SIZE} m @ z {SIGN_CENTRE_Z} on wall y {WALL_FRONT_Y} atlas={image} visual_only=true")
    return len(items)
