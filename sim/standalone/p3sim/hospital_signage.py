"""병원 벽 표지판·문 앞 매트(재범 9/25 "조제실이랑 병원, 병동이랑 데코 알아서 예쁘게"). Isaac 임포트는 늦게 한다.

바닥 표시(`hospital_decor`)와 같은 색 규칙이다 — B 파랑·C 초록·D 노랑, 그 밖(조제실) 주황.

- **벽 표지판**: 병동 문 옆 "C1 병실"·"C2 병실", 침상 머리맡 "D1"–"D10", B 테이블 옆 벽 "간호스테이션 B",
  조제실 문 옆 "조제실". 세운 판 하나씩, 벽 앞면 5 mm 앞, 빈 쪽을 본다. 높이 1.0–1.8 m — RTX 라이다 스캔 띠
  (0.1–0.6 m)와 충전 판 규칙(0.85 m 위) 밖이다.
- **문 앞 매트**: 병동 문 복도 쪽 초록 매트(문 폭 × 0.8 m), 조제실 문 앞 짙은 회색 매트. 바닥 판이고 유도선
  (1.0–1.2 mm)보다 낮은 0.8 mm 라 유도선이 매트 위로 그려진다.
- **벽 자리는 지도로 찾는다.** 빈 쪽 점에서 벽 쪽으로 1 cm 씩 나가 처음 막힌 곳이 벽 앞면이다. 지도 칸(0.05 m)이
  실물보다 조금 크게 잡혀(도크 벽 실측: 지도 5.30 ↔ 실측 5.350) 판이 벽에서 최대 5 cm 떠 보일 수 있다 — L3 미확인.
- 물리 API 없음. 표지판 메시 하나·재질 하나·텍스처 한 장(`sim/assets/decor/signs.png`). 매트는 새 메시 없이
  바닥 색 띠 메시(`hospital_decor.build`)에 합친다. 한 번 세우고 매 틱 쓰지 않는다.
- 조제실 워크셀(`hospital_decor.PHARMACY_KEEP_OUT`) 안에는 두지 않는다. 조제실 판은 방 바깥 벽면에 붙고 바깥을 본다 —
  방 안 M0609 카메라에서는 판 뒷면이라 안 그려진다(단면, 시험이 본다).

자리 계산은 순수 함수라 sim/tests 가 본다. Isaac 부분(`build`)은 L3 미실행이다.
"""

import math

from . import hospital_decor as D

BLUE, GREEN, YELLOW, ORANGE = D.BLUE, D.GREEN, D.YELLOW, D.ORANGE
#: 매트 색. 초록은 병동 판보다 조금 짙게(바닥에서 너무 밝지 않게), 조제실은 중립 짙은 회색.
MAT_GREEN = (0.07, 0.45, 0.22)
MAT_GRAY = (0.22, 0.22, 0.22)
#: 매트 들어 올림(m). 기존 바닥 층(선 1.0–1.2·칸 1.3·글자 1.4·충전 1.32/1.36 mm)과 다른 값, 선보다 아래.
LIFT_MAT = 0.0008
#: 벽 앞면에서 판을 띄우는 거리(m).
WALL_OFFSET = 0.005
#: 벽을 찾는 걸음(m)과 한도(m).
STEP = 0.01

#: 표지판 글자 → 갈래(색). 아틀라스(`make_signage_atlas.py`)가 이 순서로 칸을 만든다.
SIGN_TEXTS = {
    "C1 병실": "C", "C2 병실": "C",
    **{f"D{i}": "D" for i in range(1, 11)},
    "간호스테이션 B": "B",
    "조제실": "P",
    # 2차(재범 9/28 "릴리즈 1.0 찍었는데 데코"): 천장 방향 안내판(W)과 로비 벽 안내(I·주의 !).
    "↑ 병동 A·B": "W", "↑ 로비·조제실": "W", "병동 A": "W", "병동 B": "W",
    "손 위생": "I", "낙상 주의": "!", "정숙": "I",
}
#: 안내판 남색, 안내 포스터 청록, 주의 노랑. 흰 바탕은 쓰지 않는다(아래 `sign_style`).
NAVY = (0.10, 0.20, 0.50)
TEAL = (0.05, 0.50, 0.50)
SIGN_COLORS = {"B": BLUE, "C": GREEN, "D": YELLOW, "P": ORANGE, "W": NAVY, "I": TEAL, "!": YELLOW}
#: 판 크기(폭, 높이, 아래 끝 z) — 아틀라스 칸과 같은 4:1.
SIZE_WARD = (0.80, 0.20, 1.45)
SIZE_BED = (0.60, 0.15, 1.20)
SIZE_STATION = (1.20, 0.30, 1.40)
SIZE_PHARMACY = (0.80, 0.20, 1.45)
SIZE_POSTER = (1.00, 0.25, 1.40)
#: 천장 안내판(폭, 높이, 아래 끝 z). 로봇(팔 포함 1.4 m 안팎)·보행자(1.64 m) 머리 위다.
SIZE_HANG = (1.20, 0.30, 2.05)
#: 판 높이 띠(m) — 라이다 스캔 띠·충전 판 규칙 밖. 천장 안내판은 따로(`Z_HANG_MIN`–`Z_HANG_MAX`).
Z_MIN, Z_MAX = 1.0, 1.8
Z_HANG_MIN, Z_HANG_MAX = 2.0, 2.5
#: 두 면 안내판의 앞뒤 판 간격(m). 단면 판 둘을 등지게 붙인다(메시·재질은 그대로 하나).
HANG_GAP = 0.01
#: 천장 안내판 둘레에서 빈 바닥이어야 하는 반폭·앞뒤(m) — 기둥·벽을 뚫지 않게.
HANG_CLEAR = 0.20
#: 로비 → 동쪽 복도 갈림길(코어 북쪽, 복도 y 4.2–10.15). 앞(−x, 로비)·뒤(+x, 병동 쪽) 글자.
HANG_LOBBY = {"centre": (12.5, 7.2), "front": "↑ 병동 A·B", "back": "↑ 로비·조제실"}
#: 병동 문 앞에서 복도 쪽으로 띄우는 거리(m).
HANG_DOOR_BACK = 1.50
#: 로비 남쪽 벽 안내(빈 쪽 y 에서 −y 로 벽을 찾는다). 로비 폭에 고르게 — 벽 앞면이 판 폭 내내 같은 자리만
#: (지도로 훑어 판이 서는 x: −11…−6.5, −4.5…−3.5, −2…−0.5, 1…2, 4.5).
POSTERS = (("poster_hands", "손 위생", (-9.0, -1.8)), ("poster_fall", "낙상 주의", (-4.0, -1.8)),
           ("poster_quiet", "정숙", (1.5, -1.8)))

#: 병동 문 판은 문 북쪽 끝에서 이만큼 띄운다(m) — 앞의 값부터 시도해 벽이 판 전체 뒤에 고르게 있는 첫 자리.
#: 문 남쪽에는 C 협탁(station_c/d)이 있다. C2 문 북쪽 (20.4–20.6, 0.9–1.1)에는 작은 물체가 있어 더 띄운다.
DOOR_SIGN_GAPS = (0.05, 0.30, 0.55, 0.80, 1.05)
#: 문 앞 매트는 문틀 칸을 피해 문 폭 양끝에서 이만큼 줄인다(m).
MAT_INSET = 0.10
#: 판 양끝·가운데의 벽 앞면 깊이 차 한도(m). 넘으면 판 한쪽이 벽에서 뜬다.
FACE_TOLERANCE = 0.03
#: 판 뒤 "벽이 있다" 를 보는 깊이(m). 조제실 벽은 속이 빈 이중 벽(지도 x 3.0·3.2)이라 앞면 바로 뒤를 본다.
BEHIND = 0.03
#: 판 앞이 비었는지 보는 깊이(m). 작은 물체 바로 뒤(판을 가림)에는 두지 않는다. 침상 판은 따로 본다(침상 윗면 아래).
FRONT = 0.40
#: 병동 문 앞 매트 깊이(m, 복도 쪽).
MAT_DEPTH = 0.80

#: 간호스테이션 B 판: B 테이블(hospital_nav.STATION_B_TABLE) 동쪽 벽(기둥)의 서쪽 면, y 가운데.
STATION_SIGN_Y = 3.20
#: 조제실 문(방 동쪽 벽, 지도 x ≈ 3.6, y 6.6–7.8 열림). 판은 문 북쪽 벽 바깥면, 매트는 문 앞 로비 바닥.
PHARMACY_DOOR = {"y0": 6.60, "y1": 7.80, "probe_x": 4.20}
PHARMACY_SIGN_Y = 8.40
PHARMACY_MAT_DEPTH = 0.80
#: 조제실 안 카메라 눈(views: m0609_shelf·m0609_dispenser). 판 뒷면이 이 눈을 봐야 한다(안 그려진다).
PHARMACY_EYES = ((-3.81, 9.59, 2.2), (-7.08, 10.08, 2.2))


def wall_face(grid, start, direction, limit=1.5):
    """`start` 에서 `direction`(단위 xy)으로 STEP 씩 나가 처음 막힌 점까지의 거리. 처음부터 막혔거나 한도 안에
    없으면 None."""
    if grid.is_blocked(*start):
        return None
    d = 0.0
    while d <= limit:
        d += STEP
        if grid.is_blocked(start[0] + direction[0] * d, start[1] + direction[1] * d):
            return d
    return None


def _sign(name, text, centre_xy, facing, size):
    width, height, bottom = size
    quad = D._vertical_quad(centre_xy, facing, width, bottom, bottom + height)
    return {"name": name, "text": text, "quad": quad, "facing": facing, "centre": centre_xy}


def _on_wall(grid, start, direction, along, size, check_front=True):
    """벽을 찾아 판 가운데 xy 를 돌려준다. 판 양 끝도 벽이 뒤에 있고(0.10 m 뒤가 막힘) 앞이 비었는지 본다.
    반환 (가운데 xy, 까닭 또는 None)."""
    d = wall_face(grid, start, direction)
    if d is None:
        return None, f"{start} 에서 {direction} 로 1.5 m 안에 벽이 없다"
    face = (start[0] + direction[0] * (d - STEP), start[1] + direction[1] * (d - STEP))
    centre = (face[0] - direction[0] * WALL_OFFSET, face[1] - direction[1] * WALL_OFFSET)
    half = size[0] / 2.0 - 0.02
    n = max(2, int(math.ceil(2 * half / 0.1)))
    for s in [-half + 2 * half * i / n for i in range(n + 1)]:   # 판 폭을 0.1 m 이하 간격으로
        px, py = centre[0] + along[0] * s, centre[1] + along[1] * s
        if not grid.is_blocked(px + direction[0] * BEHIND, py + direction[1] * BEHIND):
            return None, f"판 끝 ({px:.2f}, {py:.2f}) 뒤에 벽이 없다"
        if check_front and any(grid.is_blocked(px - direction[0] * k * 0.05, py - direction[1] * k * 0.05)
                               for k in range(1, int(FRONT / 0.05) + 1)):
            return None, f"판 끝 ({px:.2f}, {py:.2f}) 앞 {FRONT} m 안이 막혔다"
        # 그 줄에서 벽 앞면이 판 가운데 줄과 같은 깊이인가 — 다르면 판이 벽에서 뜬다.
        probe = (start[0] + along[0] * s, start[1] + along[1] * s)
        here = wall_face(grid, probe, direction)
        if here is None or abs(here - d) > FACE_TOLERANCE:
            return None, f"판 끝 ({px:.2f}, {py:.2f}) 에서 벽 앞면 깊이가 다르다"
    return centre, None


def _hang_clear(grid, centre, along, width):
    """천장 안내판 밑 바닥이 비었나(판 폭 + 둘레 `HANG_CLEAR`). 막혔으면 까닭, 비었으면 None."""
    half = width / 2.0 + HANG_CLEAR
    n = int(math.ceil(2 * half / 0.05))
    for i in range(n + 1):
        s = -half + 2 * half * i / n
        for d in (-HANG_CLEAR, 0.0, HANG_CLEAR):
            x = centre[0] + along[0] * s - along[1] * d
            y = centre[1] + along[1] * s + along[0] * d
            if grid.is_blocked(x, y):
                return f"안내판 밑 ({x:.2f}, {y:.2f}) 가 막혔다(벽·기둥)"
    return None


def _mat(name, x0, y0, x1, y1, color):
    quad = [(x0, y0, LIFT_MAT), (x1, y0, LIFT_MAT), (x1, y1, LIFT_MAT), (x0, y1, LIFT_MAT)]
    return {"name": name, "quad": quad, "color": color}


def plan(grid, anchors, station_b_table, avoid=()):
    """{"signs": [...], "mats": [...], "skipped": [(무엇, 까닭)]}. 순수 함수다.

    avoid: 매트가 겹치면 안 되는 바닥 판(칸·글자·범례)의 네 점 목록. 유도선은 매트 위로 그려지므로 넣지 않는다.
    """
    signs, mats, skipped = [], [], []

    def add_sign(name, text, starts, direction, along, size, check_front=True):
        why = None
        for start in starts:
            centre, why = _on_wall(grid, start, direction, along, size, check_front)
            if centre is not None:
                signs.append(_sign(name, text, centre, (-direction[0], -direction[1]), size))
                return
        skipped.append((f"sign:{name}", why))

    # 병동 문(C1·C2): 문 벽 복도 쪽(−x) 면, 문 북쪽. 매트는 문 앞 복도.
    for room in ("C1", "C2"):
        door = anchors["doors"][room]
        starts = [(door["min"][0] - 0.25, door["max"][1] + gap + SIZE_WARD[0] / 2.0) for gap in DOOR_SIGN_GAPS]
        add_sign(f"ward_{room}", f"{room} 병실", starts, (1.0, 0.0), (0.0, 1.0), SIZE_WARD)
        x1 = door["min"][0] - 0.02   # 문틀 칸 바로 앞
        mat = _mat(f"mat_{room}", x1 - MAT_DEPTH, door["min"][1] + MAT_INSET, x1, door["max"][1] - MAT_INSET, MAT_GREEN)
        mats.append(mat)
    # 침상 머리맡(D1–D10): yaw 0 이면 머리가 +y, 180 이면 −y. 판은 침상 가운데 x, 머리 쪽 벽.
    for label, bed in sorted(anchors["beds"].items(), key=lambda kv: int(kv[0][1:])):
        head = 1.0 if abs(bed.get("yaw_deg", 0.0)) < 90.0 else -1.0
        cx = (bed["min"][0] + bed["max"][0]) / 2.0
        edge = bed["max"][1] if head > 0 else bed["min"][1]
        # 침상 자체가 지도에서 막혀 있으니 머리 끝 바로 앞(침상 안)에서가 아니라 침상 옆 빈 바닥 줄에서 벽을 찾는다.
        side_x = bed["max"][0] + 0.15
        d = wall_face(grid, (side_x, edge - head * 0.30), (0.0, head), limit=1.0)
        if d is None:
            skipped.append((f"sign:bed_{label}", "머리맡 벽을 못 찾았다"))
            continue
        face_y = edge - head * 0.30 + head * (d - STEP)
        centre = (cx, face_y - head * WALL_OFFSET)
        if bed["max"][2] >= SIZE_BED[2]:
            skipped.append((f"sign:bed_{label}", "침상이 판보다 높다"))
            continue
        # 앞(방 쪽)은 침상이지만 판 높이(1.2 m)가 침상 윗면(0.89 m)보다 위라 가리지 않는다.
        behind = [grid.is_blocked(cx + s, face_y + head * 0.10) for s in (-0.28, 0.0, 0.28)]
        if not all(behind):
            skipped.append((f"sign:bed_{label}", "머리맡 판 뒤에 벽이 없다"))
            continue
        signs.append(_sign(f"bed_{label}", label, centre, (0.0, -head), SIZE_BED))
    # 간호스테이션 B: B 테이블 동쪽 벽(기둥)의 서쪽 면.
    hi = station_b_table["max"]
    add_sign("station_b", "간호스테이션 B", [(hi[0] + 0.10, STATION_SIGN_Y)], (1.0, 0.0), (0.0, 1.0), SIZE_STATION)
    # 조제실: 방 동쪽 벽 바깥면(+x 를 본다), 문 북쪽. 매트는 문 앞 로비.
    add_sign("pharmacy", "조제실", [(PHARMACY_DOOR["probe_x"], PHARMACY_SIGN_Y)], (-1.0, 0.0), (0.0, 1.0),
             SIZE_PHARMACY)
    door_face = wall_face(grid, (PHARMACY_DOOR["probe_x"], PHARMACY_SIGN_Y), (-1.0, 0.0))
    if door_face is not None:
        x0 = PHARMACY_DOOR["probe_x"] - door_face + STEP
        mats.append(_mat("mat_pharmacy", x0, PHARMACY_DOOR["y0"], x0 + PHARMACY_MAT_DEPTH, PHARMACY_DOOR["y1"],
                         MAT_GRAY))
    # 로비 남쪽 벽 안내 포스터(+y 를 본다).
    for name, text, start in POSTERS:
        add_sign(name, text, [start, (start[0] + 0.5, start[1]), (start[0] - 0.5, start[1])], (0.0, -1.0),
                 (1.0, 0.0), SIZE_POSTER)
    # 천장 안내판: 갈림길 두 면, 병동 문 앞 한 면(복도 −x 를 본다).
    hangs = [("hang_lobby", HANG_LOBBY["centre"], HANG_LOBBY["front"], HANG_LOBBY["back"])]
    for room, text in (("C1", "병동 A"), ("C2", "병동 B")):
        door = anchors["doors"][room]
        hangs.append((f"hang_{room}", (door["center"][0] - HANG_DOOR_BACK, door["center"][1]), text, None))
    for name, centre, front, back in hangs:
        why = _hang_clear(grid, centre, (0.0, 1.0), SIZE_HANG[0])
        if why is not None:
            skipped.append((f"sign:{name}", why))
            continue
        signs.append({**_sign(name, front, (centre[0] - HANG_GAP / 2.0, centre[1]), (-1.0, 0.0), SIZE_HANG),
                      "hang": True})
        if back is not None:
            signs.append({**_sign(f"{name}_back", back, (centre[0] + HANG_GAP / 2.0, centre[1]), (1.0, 0.0),
                                  SIZE_HANG), "hang": True})
    # 매트 검사: 빈 바닥(판 안 0.1 m 격자), 워크셀 밖, 다른 바닥 판과 안 겹침.
    kept = []
    for mat in mats:
        q = mat["quad"]
        inner = [D._quad_point(q, u / 10.0, v / 10.0) for u in range(11) for v in range(11)]
        if not D.on_free_floor(grid, inner):
            skipped.append((f"mat:{mat['name']}", "빈 바닥이 아니다"))
        elif any(D.in_keep_out(p[0], p[1]) for p in q):
            skipped.append((f"mat:{mat['name']}", "조제실 워크셀 안이다"))
        elif any(D.overlaps(q, other) for other in avoid):
            skipped.append((f"mat:{mat['name']}", "다른 바닥 판과 겹친다"))
        else:
            kept.append(mat)
    for sign in signs:
        if any(D.in_keep_out(p[0], p[1]) for p in sign["quad"]):
            skipped.append((f"sign:{sign['name']}", "조제실 워크셀 안이다"))
    signs = [s for s in signs if not any(D.in_keep_out(p[0], p[1]) for p in s["quad"])]
    return {"signs": signs, "mats": kept, "skipped": skipped}


def decor_faces(decor):
    """바닥 표시 계획(`hospital_decor.plan`)에서 매트가 피할 판: 정차 칸 바깥 네 점·글자·범례. 유도선은 뺀다."""
    faces = [points[:4] for name, points, _c, _i, _col in decor["strips"] if name.startswith("bay_")]
    faces += [quad for _zone, _text, quad, _uv in decor["labels"]]
    return faces


def facing_eye(sign, eye):
    """판 앞면이 `eye` 를 보는가(단면이라 뒤에서는 안 그려진다)."""
    cx, cy = sign["centre"]
    fx, fy = sign["facing"]
    return (eye[0] - cx) * fx + (eye[1] - cy) * fy > 0.0


def mat_strips(signage):
    """매트 → 바닥 색 띠(`hospital_decor.plan` 의 strips 모양).

    새 메시 없이 기존 색 띠 메시 하나에 합친다(최적화 예산, 재범 "막 무겁게 하지 말고").
    """
    return [(mat["name"], list(mat["quad"]), [4], [0, 1, 2, 3], mat["color"]) for mat in signage["mats"]]


def build(stage, root, signage, uv, image, log=print):
    """표지판 메시 하나·재질 하나·텍스처 한 장(아틀라스). 매트는 여기서 세우지 않는다(`mat_strips`).
    물리 API 없음, 판마다 prim 을 만들지 않는다, 매 틱 쓰지 않는다. 반환 (판 수, 매트 수)."""
    from pxr import Gf, Sdf, UsdGeom, UsdShade, Vt

    UsdGeom.Xform.Define(stage, root)
    signs = [s for s in signage["signs"] if s["text"] in uv]
    if signs:
        vertices, counts, indices, st = [], [], [], []
        for sign in signs:
            u0, v0, u1, v1 = uv[sign["text"]]
            base = len(vertices)
            vertices += sign["quad"]
            counts.append(4)
            indices += [base, base + 1, base + 2, base + 3]
            st += [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
        mesh = UsdGeom.Mesh.Define(stage, f"{root}/Signs")
        mesh.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(*p) for p in vertices]))
        mesh.CreateFaceVertexCountsAttr(counts)
        mesh.CreateFaceVertexIndicesAttr(indices)
        mesh.CreateDoubleSidedAttr(False)
        primvar = UsdGeom.PrimvarsAPI(mesh).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray,
                                                           UsdGeom.Tokens.vertex)
        primvar.Set(Vt.Vec2fArray([Gf.Vec2f(*p) for p in st]))
        material = UsdShade.Material.Define(stage, f"{root}/Looks/Signs")
        shader = UsdShade.Shader.Define(stage, f"{root}/Looks/Signs/Surface")
        shader.CreateIdAttr("UsdPreviewSurface")
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.6)
        reader = UsdShade.Shader.Define(stage, f"{root}/Looks/Signs/St")
        reader.CreateIdAttr("UsdPrimvarReader_float2")
        reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
        texture = UsdShade.Shader.Define(stage, f"{root}/Looks/Signs/Atlas")
        texture.CreateIdAttr("UsdUVTexture")
        texture.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(str(image))
        texture.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(reader.ConnectableAPI(), "result")
        texture.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(
            texture.ConnectableAPI(), "rgb")
        material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
        UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)
    skipped = [what for what, _why in signage["skipped"]]
    for what, why in signage["skipped"]:
        log(f"WARN hospital_decor signage skipped {what}: {why}")
    log(f"hospital_decor signs={len(signs)} mats={len(signage['mats'])} skipped={skipped} visual_only=true "
        f"(매트는 바닥 색 띠 메시에 합쳤다)")
    return len(signs), len(signage["mats"])


def sign_style(text):
    """(바탕 색, 글자 색). 바탕은 채도 높은 갈래 색이다.

    흰 바탕은 쓰지 않는다 — 카메라 봉투 검출기가 밝고 채도 낮은 덩어리를 찾는다.
    """
    background = SIGN_COLORS[SIGN_TEXTS[text]]
    return background, (D.LIGHT_INK if background in (BLUE, GREEN, NAVY, TEAL) else D.DARK_INK)
