"""병원 M0609 셀 바닥 꾸밈(재범 9/25 "M0609 있는 부분 간지나게 — 검정 베이스에 배선이 연결된 느낌").

`hospital_decor` 와 같은 방식이다: 시각 전용, 물리 없음, 바닥에서 1.5 mm 안(라이다 스캔 평면과 못 만난다),
병원 preset 에서 켜지고 `--no-hospital-decor` 로 같이 꺼진다. 자리는 **워크셀 JSON**(`--workcell-layout`)에서 온다.

- **베이스 판**: 레일·조제기·선반 앞·벨트 시작 구간을 덮는 무광 검정 판.
- **경계 띠**: 판 둘레 노랑/검정 사선 띠(산업 현장 안전 구역 표시).
- **배선 트렌치**: 제어반(바닥 정션 박스)에서 조제기·레일·벨트로 가는 짙은 회색 띠와 이음쇠 사각.
- **글자**: `power`·`data` 둘. 조제실 촬영 뷰(`m0609_shelf`·`m0609_dispenser`)와 `a1_pick` 프레임 밖에 둔다.

벨트 끝(A1 롤러)·AMR 집기 자리는 워크셀 밖(y ≈ 5)이라 닿지 않는다(시험이 본다). 조제실 워크셀 안에 아무것도
두지 않던 `hospital_decor.PHARMACY_KEEP_OUT` 과 달리 이것은 **워크셀 자체를 꾸미는 것**이다. M0609 손 카메라는
잡기 직전 선반(0.88 m)을 수평으로 보므로 바닥이 시야에 들지 않는다.

메시 둘(꼭짓점 색 판 하나, 글자 판 하나), 재질 둘, 텍스처 한 장(`sim/assets/decor/workcell_labels.png`).
Isaac 이 있어야 도는 `build` 는 L3 미실행이다. 자리 계산(`plan`)은 순수 함수라 sim/tests 가 본다.
"""

import math

#: 들어 올림(m). 서로 다른 높이라 겹쳐도 깜빡이지 않는다. 모두 `hospital_decor` 의 유도선(1.0 mm)보다 아래다.
LIFT_BASE = 0.0003
LIFT_BORDER = 0.0005
LIFT_TRENCH = 0.0007
LIFT_BOX = 0.0008
LIFT_LABEL = 0.0009
#: 판을 설비 둘레보다 넓히는 여유(m), 경계 띠 폭(m)·사선 한 칸 길이(m), 트렌치 폭(m), 이음쇠 한 변(m).
MARGIN = 0.15
BORDER_WIDTH = 0.10
STRIPE = 0.12
TRENCH_WIDTH = 0.12
BOX_SIDE = 0.24
PANEL_SIZE = (0.50, 0.34)
#: 글자 판(m), 아틀라스 칸 비율 4:1.
LABEL_SIZE = (0.40, 0.10)

BLACK = (0.035, 0.035, 0.04)
YELLOW = (0.98, 0.80, 0.10)
STRIPE_BLACK = (0.06, 0.06, 0.06)
TRENCH_GREY = (0.20, 0.20, 0.22)
BOX_GREY = (0.34, 0.34, 0.37)

#: 글자 판이 들면 안 되는 촬영 뷰.
PROTECTED_VIEWS = ("m0609_shelf", "m0609_dispenser", "a1_pick")


def _bbox(obstacles, prefix, contains=""):
    """이름이 `prefix` 로 시작하고 `contains` 를 품은 장애물들의 (x0, y0, x1, y1). 선반 판은 `Shelf68Board2` 꼴이다."""
    boxes = [o for o in obstacles if o["name"].startswith(prefix) and contains in o["name"]]
    if not boxes:
        raise KeyError(f"workcell obstacles 에 {prefix}*{contains}* 가 없다")
    xs = [o["center"][0] + s * o["size"][0] / 2.0 for o in boxes for s in (-1, 1)]
    ys = [o["center"][1] + s * o["size"][1] / 2.0 for o in boxes for s in (-1, 1)]
    return min(xs), min(ys), max(xs), max(ys)


def anchors(workcell):
    """설비 자리(병원 좌표). 판·트렌치·이음쇠가 여기서 나온다."""
    rail = workcell["rail"]
    ox, oy, _oz = rail["origin"]
    half = rail["x_stroke"] / 2.0 + 0.2                         # 레일 궤도는 행정 + 0.4
    track_south = oy + rail["y_limits"][0] - 0.05 - 0.03        # layout.rail_boxes 의 왼쪽 궤도 남쪽 면
    belt = workcell["belt"]
    bx, by, _bz = belt["start"]
    ex = bx + belt["length"] * math.cos(belt["yaw"])
    ey = by + belt["length"] * math.sin(belt["yaw"])
    dispenser = _bbox(workcell["obstacles"], "Dispenser_Machine")
    shelves = _bbox(workcell["obstacles"], "Shelf", "Board")
    tray_y = track_south - 0.12                                  # 레일 케이블 트레이(궤도 남쪽)
    panel = (min(bx, ex) + 0.47, min(by, ey) + 0.15)            # 제어반: 벨트 시작 구간 옆 바닥
    return {
        "rail_west": (ox - half, tray_y), "rail_mid": (ox, tray_y), "rail_east": (ox + half, tray_y),
        "belt_start": (bx, by), "belt_end": (ex, ey), "belt_tap": (min(bx, ex) + 0.27, panel[1]),
        "dispenser_front": ((dispenser[0] + dispenser[2]) / 2.0 - 0.3, dispenser[1] - 0.15),
        "dispenser": dispenser, "shelves": shelves, "panel": panel,
        "plate": (min(bx, ex) - MARGIN, min(by, ey) - MARGIN, ox + half + MARGIN, shelves[1]),
    }


def _quad(x0, y0, x1, y1, lift):
    """축에 나란한 사각, 위에서 보면 반시계(법선 +z)."""
    return [(x0, y0, lift), (x1, y0, lift), (x1, y1, lift), (x0, y1, lift)]


def _segment_strip(a, b, width, lift):
    """선분 → 폭 `width` 의 사각(끝을 폭/2 만큼 늘려 이음매를 덮는다). 위에서 보면 반시계."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux
    h = width / 2.0
    a2 = (a[0] - ux * h, a[1] - uy * h)
    b2 = (b[0] + ux * h, b[1] + uy * h)
    return [(a2[0] - nx * h, a2[1] - ny * h, lift), (b2[0] - nx * h, b2[1] - ny * h, lift),
            (b2[0] + nx * h, b2[1] + ny * h, lift), (a2[0] + nx * h, a2[1] + ny * h, lift)]


def border_stripes(plate):
    """판 둘레 사선 띠: (네 점, 색) 목록. 변마다 `STRIPE` 길이의 평행사변형을 노랑·검정으로 번갈아."""
    x0, y0, x1, y1 = plate
    w = BORDER_WIDTH
    out = []
    # 변 넷(안쪽 선을 따라 진행 방향 왼쪽이 판 안쪽): 남·동·북·서
    edges = (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0)))
    for a, b in edges:
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        ux, uy = dx / length, dy / length
        nx, ny = -uy, ux                                         # 판 안쪽
        count = max(1, int(length / STRIPE))
        step = length / count
        for k in range(count):
            s0, s1 = k * step, (k + 1) * step
            p0 = (a[0] + ux * s0, a[1] + uy * s0)
            p1 = (a[0] + ux * s1, a[1] + uy * s1)
            skew = min(w, step) * 0.5
            quad = [(p0[0], p0[1], LIFT_BORDER), (p1[0], p1[1], LIFT_BORDER),
                    (p1[0] + nx * w + ux * skew, p1[1] + ny * w + uy * skew, LIFT_BORDER),
                    (p0[0] + nx * w + ux * skew, p0[1] + ny * w + uy * skew, LIFT_BORDER)]
            out.append((quad, YELLOW if k % 2 == 0 else STRIPE_BLACK))
    return out


#: 레일 케이블 트레이 두 줄의 간격(m). power 는 궤도 쪽, data 는 그 남쪽. 둘 사이에 power 글자가 들어간다.
TRAY_GAP = 0.30


def trench_routes(anchor):
    """(이름, 점 목록). 제어반에서 넷: 레일 트레이 power·data 두 줄, 조제기(data), 벨트(power)."""
    px, py = anchor["panel"]
    wx, wy = anchor["rail_west"]
    ex, _ey = anchor["rail_east"]
    dx, dy = anchor["dispenser_front"]
    tx, ty = anchor["belt_tap"]
    return [
        ("rail_power", [(px, py), (px, wy), (wx, wy), anchor["rail_east"]]),
        ("rail_data", [(px + 0.2, py), (px + 0.2, wy - TRAY_GAP), (ex, wy - TRAY_GAP)]),
        ("dispenser_data", [(px, py), (dx, py), (dx, dy)]),
        ("belt_power", [(px, py), (tx, ty)]),
    ]


def plan(workcell, label_uv, views=None):
    """세울 것 전부. {"faces": [(네 점, 색)], "labels": [(글자, 네 점, uv)], "anchors": …}. 순수 함수다.

    `views` 를 주면({이름: (eye, target)}) 글자 판을 `PROTECTED_VIEWS` 프레임 밖 후보 자리에 둔다.
    """
    anchor = anchors(workcell)
    faces = [(_quad(*anchor["plate"], LIFT_BASE), BLACK)]
    faces += border_stripes(anchor["plate"])
    for _name, points in trench_routes(anchor):
        for a, b in zip(points[:-1], points[1:], strict=True):
            faces.append((_segment_strip(a, b, TRENCH_WIDTH, LIFT_TRENCH), TRENCH_GREY))
    box_points = [anchor[k] for k in ("rail_west", "rail_mid", "rail_east", "dispenser_front", "belt_tap")]
    for x, y in box_points:
        faces.append((_quad(x - BOX_SIDE / 2, y - BOX_SIDE / 2, x + BOX_SIDE / 2, y + BOX_SIDE / 2, LIFT_BOX),
                      BOX_GREY))
    px, py = anchor["panel"]
    faces.append((_quad(px - PANEL_SIZE[0] / 2, py - PANEL_SIZE[1] / 2, px + PANEL_SIZE[0] / 2,
                        py + PANEL_SIZE[1] / 2, LIFT_BOX), BOX_GREY))
    labels = []
    for text, candidates in label_candidates(anchor):
        for cx, cy in candidates:
            quad = _quad(cx - LABEL_SIZE[0] / 2, cy - LABEL_SIZE[1] / 2, cx + LABEL_SIZE[0] / 2,
                         cy + LABEL_SIZE[1] / 2, LIFT_LABEL)
            if views is None or not any(_seen(views[name], p) for name in PROTECTED_VIEWS if name in views
                                        for p in quad):
                labels.append((text, quad, tuple(label_uv[text])))
                break
    return {"faces": faces, "labels": labels, "anchors": anchor}


def label_candidates(anchor):
    """글자별 후보 자리. 레일 트레이 동쪽 끝부터 서쪽으로 — 서쪽 절반은 조제실 촬영 뷰가 본다(9/25 계산:
    프레임 밖은 x ≥ −1.8 뿐). power 는 두 트레이 사이, data 는 data 트레이 남쪽."""
    _wx, wy = anchor["rail_west"]
    ex, _ey = anchor["rail_east"]
    xs = [ex - 0.6 - 0.6 * k for k in range(8)]
    power = [(x, wy - TRAY_GAP / 2.0) for x in xs]
    data = [(x, wy - TRAY_GAP - TRENCH_WIDTH / 2.0 - 0.02 - LABEL_SIZE[1] / 2.0) for x in xs]
    return [("power", power), ("data", data)]


def _seen(view, point):
    from . import views as V

    eye, target = view
    return any(V.in_frame(eye, target, point, margin=1.0, aspect=aspect) for aspect in (V.ASPECT,
                                                                                         V.HALF_SCREEN_ASPECT))


def build(stage, root, decor, label_image, log=print):
    """꼭짓점 색 메시 하나 + 글자 메시 하나. 물리 API 없음. 반환 (면 수, 글자 수)."""
    from pxr import Gf, Sdf, UsdGeom, UsdShade, Vt

    UsdGeom.Xform.Define(stage, root)
    vertices, counts, indices, colors = [], [], [], []
    for quad, color in decor["faces"]:
        base = len(vertices)
        vertices += quad
        counts.append(4)
        indices += [base, base + 1, base + 2, base + 3]
        colors.append(color)
    mesh = UsdGeom.Mesh.Define(stage, f"{root}/WorkcellFloor")
    mesh.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(*p) for p in vertices]))
    mesh.CreateFaceVertexCountsAttr(counts)
    mesh.CreateFaceVertexIndicesAttr(indices)
    mesh.CreateNormalsAttr(Vt.Vec3fArray([Gf.Vec3f(0.0, 0.0, 1.0)] * len(vertices)))
    mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
    mesh.CreateDoubleSidedAttr(False)
    UsdGeom.PrimvarsAPI(mesh).CreatePrimvar("displayColor", Sdf.ValueTypeNames.Color3fArray,
                                            UsdGeom.Tokens.uniform).Set(Vt.Vec3fArray([Gf.Vec3f(*c)
                                                                                      for c in colors]))
    material = UsdShade.Material.Define(stage, f"{root}/Looks/Floor")
    shader = UsdShade.Shader.Define(stage, f"{root}/Looks/Floor/Surface")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.9)            # 무광
    reader = UsdShade.Shader.Define(stage, f"{root}/Looks/Floor/Color")
    reader.CreateIdAttr("UsdPrimvarReader_float3")
    reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("displayColor")
    reader.CreateOutput("result", Sdf.ValueTypeNames.Float3)
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(reader.ConnectableAPI(), "result")
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)

    if decor["labels"]:
        vertices, counts, indices, st = [], [], [], []
        for _text, quad, (u0, v0, u1, v1) in decor["labels"]:
            base = len(vertices)
            vertices += quad
            counts.append(4)
            indices += [base, base + 1, base + 2, base + 3]
            st += [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
        labels = UsdGeom.Mesh.Define(stage, f"{root}/WorkcellLabels")
        labels.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(*p) for p in vertices]))
        labels.CreateFaceVertexCountsAttr(counts)
        labels.CreateFaceVertexIndicesAttr(indices)
        labels.CreateNormalsAttr(Vt.Vec3fArray([Gf.Vec3f(0.0, 0.0, 1.0)] * len(vertices)))
        labels.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
        labels.CreateDoubleSidedAttr(False)
        UsdGeom.PrimvarsAPI(labels).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray,
                                                  UsdGeom.Tokens.vertex).Set(Vt.Vec2fArray([Gf.Vec2f(*t)
                                                                                            for t in st]))
        material = UsdShade.Material.Define(stage, f"{root}/Looks/Labels")
        shader = UsdShade.Shader.Define(stage, f"{root}/Looks/Labels/Surface")
        shader.CreateIdAttr("UsdPreviewSurface")
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.9)
        reader = UsdShade.Shader.Define(stage, f"{root}/Looks/Labels/St")
        reader.CreateIdAttr("UsdPrimvarReader_float2")
        reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
        texture = UsdShade.Shader.Define(stage, f"{root}/Looks/Labels/Atlas")
        texture.CreateIdAttr("UsdUVTexture")
        texture.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(str(label_image))
        texture.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(reader.ConnectableAPI(), "result")
        texture.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(texture.ConnectableAPI(),
                                                                                       "rgb")
        material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
        UsdShade.MaterialBindingAPI.Apply(labels.GetPrim()).Bind(material)
    plate = decor["anchors"]["plate"]
    log(f"workcell_decor faces={len(decor['faces'])} labels={[t for t, _q, _uv in decor['labels']]} "
        f"plate=x[{plate[0]:.2f},{plate[2]:.2f}] y[{plate[1]:.2f},{plate[3]:.2f}] meshes=2 materials=2 "
        f"atlas={label_image} lift_mm={LIFT_BASE * 1000:.1f}-{LIFT_LABEL * 1000:.1f} visual_only=true")
    return len(decor["faces"]), len(decor["labels"])
