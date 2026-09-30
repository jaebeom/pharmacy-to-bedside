"""약통 QR 면과 M0609 손 카메라(카드 Q1, 9/23). Isaac 임포트는 늦게 한다.

QR·DB·카메라 계약 1·2절: 약통 QR 에는 ID(`cn-NNNN`)만 있다. 선반 16칸 ↔ ID 는 orchestrator 카탈로그
(`pharmacy_catalog.yaml` 의 `location: "shelf:<칸>"`)가 정본이고, 스테이지는 그 파일을 읽어 텍스처를 고른다.

- **QR 면은 약통의 자식이 아니다.** 약통은 DynamicCylinder·DynamicCuboid(gprim)라 그 아래에 Mesh 를 둘 수 없다
  (`scene.add_top_texture` 와 같은 이유). 면은 따로 된 Mesh 이고 점이 약통 로컬 좌표다. 약통이 움직일 때
  (잡혀 따라감·놓인 뒤 떨어짐·되돌려짐) 스테이지가 `CanisterFaces.follow` 로 면을 약통 자세에 맞춘다.
- 면은 몸통 앞(통로 쪽 -y)에 붙은 스티커다(재범 9/23 정정). 원통은 옆면을 감싼 곡면, 모듈은 앞면. 높이는 잡기 직전
  M0609 손 카메라 축에 맞춘다(`sticker_center_z`). 위가 열린 칸(access top)만 윗면을 더 붙인다.
- **M0609 손 카메라도 링크의 자식이 아니다.** 로봇 USD 링크가 인스턴스 프림일 수 있어 자식을 못 단다.
  카메라는 따로 두고 `link_6` 의 월드 자세 × 장착값으로 매 스텝 옮긴다.
  장착값은 #520 의 값(M0617 조립에서 추출, **M0609 에서는 미확인**)이다.

Isaac 이 있어야 도는 부분은 L3 미실행이다. 순수 함수(칸 매핑·면 기하·장착 자세)는 sim/tests 가 본다.
"""

import math
import re

#: 카탈로그 한 줄에서 (cn-ID, 칸). `[^}]` 로 다음 줄로 넘어가지 않는다.
SHELF_ROW = re.compile(r'container_id:\s*(cn-[0-9]{4})[^}]*?location:\s*"shelf:([a-z0-9_]+/r[0-9]c[0-9])"')
#: QR 면은 약통 앞면 폭(원통 지름·모듈 x)의 이 비율, 정사각형이다.
FACE_FRACTION = 0.72
#: 면을 약통 표면에서 띄우는 거리(m). z-fighting 을 피한다. 스티커 두께라 1 mm 를 넘지 않는다(재범 9/23).
FACE_LIFT = 0.0005
#: 원통 스티커의 펼친 한 변(m). 감싼 각이 크면 가장자리가 비스듬해진다 — 지름 70 mm 에서 약 65°.
CYLINDER_STICKER_SIDE = 0.04
#: 원통 스티커 곡면의 가로 조각 수.
CYLINDER_STICKER_SEGMENTS = 12
#: M0609 이 원통을 잡는 점: 윗면에서 이만큼 아래(scene_v2.DEFAULT_PARAMS.cylinder_grip).
CYLINDER_GRIP_BELOW_TOP = 0.02
#: M0609 이 모듈을 잡는 점: 중심에서 이만큼 위(scene_v2.DEFAULT_PARAMS.module_grip_up, 작전 결정 9/23).
MODULE_GRIP_ABOVE_CENTRE = 0.03
#: 스티커 가장자리와 몸통 끝 사이 최소 여유(m).
STICKER_EDGE_MARGIN = 0.003

#: M0609 손 카메라 장착값(link_6 기준, #520·#134). 컬러 카메라 q(wxyz) 는 USD 카메라(-Z 시선)를 공구 +Z 로 돌린다.
M0609_CAMERA_T = (0.0, 0.0483, 0.0185)
M0609_CAMERA_Q = (0.0, 0.0, 1.0, 0.0)
#: D455 컬러 카메라 내부값(흡착 그리퍼 자산과 같은 값, 수평 화각 90.5°).
M0609_CAMERA_FOCAL_MM = 1.93
M0609_CAMERA_H_APERTURE_MM = 3.896
M0609_CAMERA_V_APERTURE_MM = 2.453


def shelf_containers(catalog_text):
    """카탈로그 본문 → {칸: cn-ID}. PyYAML 없이 읽는다(Isaac python 에 없을 수 있다)."""
    return {cell: cid for cid, cell in SHELF_ROW.findall(catalog_text)}


def face_width(cell):
    """앞면 폭(m). 원통은 지름, 모듈은 x."""
    size = cell["size"]
    return float(size["diameter"] if cell["type"] == "cylinder" else size["x"])


def sticker_center_z(cell):
    """앞면 스티커 중심 높이(약통 로컬 z). 잡기 직전(grasp_pose) M0609 손 카메라 축의 높이에 둔다.

    앞 접근에서 공구 +z 는 월드 +y, link_6 +y 는 월드 -z 다(scene_v2.FRONT). 그래서 카메라 축은 잡는 점보다
    `M0609_CAMERA_T[1]` 아래에 있다. 잡는 점: 원통은 윗면 - `CYLINDER_GRIP_BELOW_TOP`, 모듈은 중심 +
    `MODULE_GRIP_ABOVE_CENTRE`(scene_v2.DEFAULT_PARAMS). 스티커가 몸통을 벗어나면 가장자리
    `STICKER_EDGE_MARGIN` 안으로 당긴다.
    """
    height = float(cell["height"])
    grip = height / 2.0 - CYLINDER_GRIP_BELOW_TOP if cell["type"] == "cylinder" else MODULE_GRIP_ABOVE_CENTRE
    axis = grip - M0609_CAMERA_T[1]
    limit = height / 2.0 - sticker_side(cell) / 2.0 - STICKER_EDGE_MARGIN
    return max(-limit, min(limit, axis))


def sticker_side(cell):
    """스티커 한 변(m). 원통은 펼친 길이, 모듈은 앞면 폭의 `FACE_FRACTION`."""
    if cell["type"] == "cylinder":
        return CYLINDER_STICKER_SIDE
    return FACE_FRACTION * face_width(cell)


def sticker_mesh(cell):
    """앞면(통로 쪽 -y) 스티커 Mesh (points, normals, st, counts, indices). 약통 로컬 좌표.

    - 원통: 옆면을 감싼 곡면. 반지름 + `FACE_LIFT`, -y 를 가운데로 펼친 길이 `CYLINDER_STICKER_SIDE`.
    - 모듈: 앞면 y = -(깊이/2) - `FACE_LIFT` 의 평면.
    둘 다 따로 된 판이 아니다(두께 `FACE_LIFT` ≤ 1 mm). -y 에서 +y 를 보면 오른쪽이 +x, 위가 +z 다.
    """
    side = sticker_side(cell)
    z0 = sticker_center_z(cell) - side / 2.0
    size = cell["size"]
    columns = CYLINDER_STICKER_SEGMENTS if cell["type"] == "cylinder" else 1
    points, normals, st = [], [], []
    for row, z in enumerate((z0, z0 + side)):
        for column in range(columns + 1):
            u = column / columns
            if cell["type"] == "cylinder":
                radius = float(size["diameter"]) / 2.0 + FACE_LIFT
                angle = (u - 0.5) * side / (radius - FACE_LIFT)       # 0 이 -y 방향
                normal = (math.sin(angle), -math.cos(angle), 0.0)
                points.append((radius * normal[0], radius * normal[1], z))
            else:
                normal = (0.0, -1.0, 0.0)
                points.append(((u - 0.5) * side, -float(size["y"]) / 2.0 - FACE_LIFT, z))
            normals.append(normal)
            st.append((u, float(row)))
    counts, indices = [], []
    for column in range(columns):
        counts.append(4)
        indices += [column, column + 1, columns + 2 + column, columns + 1 + column]
    return points, normals, st, counts, indices


def top_mesh(cell):
    """윗면 QR(위가 열린 칸만, access "top"). 평면 z = 높이/2 + `FACE_LIFT`, 위에서 보면 오른쪽 +x, 위쪽 +y."""
    half = FACE_FRACTION * face_width(cell) / 2.0
    z = float(cell["height"]) / 2.0 + FACE_LIFT
    points = [(-half, -half, z), (half, -half, z), (half, half, z), (-half, half, z)]
    return points, [(0.0, 0.0, 1.0)] * 4, [(0, 0), (1, 0), (1, 1), (0, 1)], [4], [0, 1, 2, 3]


def cell_faces(cell):
    """이 칸 약통에 붙는 QR 면 [(이름, mesh)]. 몸통 앞면 스티커는 늘, 윗면은 위가 열린 칸(access top)만."""
    faces = [("front", sticker_mesh(cell))]
    if cell.get("access") == "top":
        faces.append(("top", top_mesh(cell)))
    return faces


def _quat_multiply(a, b):
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (aw * bw - ax * bx - ay * by - az * bz,
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw)


def _quat_rotate(q, v):
    w, x, y, z = q
    _w, rx, ry, rz = _quat_multiply(_quat_multiply(q, (0.0, *v)), (w, -x, -y, -z))
    return rx, ry, rz


def camera_world_pose(link_xyz, link_quat_wxyz):
    """link_6 월드 자세 → 손 카메라 월드 자세 (xyz, wxyz)."""
    offset = _quat_rotate(link_quat_wxyz, M0609_CAMERA_T)
    position = tuple(float(p) + o for p, o in zip(link_xyz, offset, strict=True))
    return position, _quat_multiply(link_quat_wxyz, M0609_CAMERA_Q)


#: 화면에 보이는 RealSense 몸체(재범 9/23: 카메라 프림은 형체가 없어 확인할 수 없다). 흡착 그리퍼 자산(#538)의
#: D455 서브트리를 쓴다. 물리(충돌·강체)가 없는 서브트리다(usd-core 로 확인, sim/tests).
D455_ASSET_PRIM = "/World/short_gripper_01/suction_cup/realsense_d455"
#: 그 서브트리 안 컬러 카메라(모델 루트 기준 상대 경로). 이 카메라가 우리 카메라와 겹치게 모델을 놓는다.
D455_COLOR_CAMERA = "RSD455/Camera_OmniVision_OV9782_Color"
#: 카메라 근접 클립(m). 렌즈 유리 메시가 카메라 프림보다 조금 앞에 있을 수 있어 몸체가 제 이미지를 가리지 않게 둔다.
M0609_CAMERA_NEAR_CLIP = 0.03


def attach_d455_model(stage, camera_path, asset_path, name="d455"):
    """카메라 프림 아래에 D455 모델을 reference 한다. 모델의 컬러 카메라가 이 카메라와 겹친다. 반환은 모델 경로.

    카메라가 움직이면 자식이라 같이 움직인다. 시각만이다 — 서브트리에 물리가 없다.
    모델 안 카메라는 넷 다 끈다(컬러 포함). 찍는 것은 우리 카메라 하나다(재범 9/23: 카메라 목록에 컬러만).
    """
    from pxr import Sdf, UsdGeom

    from .amr_base import D455_EXTRA_PRIMS

    model = stage.DefinePrim(Sdf.Path(camera_path).AppendChild(name), "Xform")
    model.GetReferences().AddReference(str(asset_path), Sdf.Path(D455_ASSET_PRIM))
    color = model.GetPrimAtPath(D455_COLOR_CAMERA)
    if not color.IsValid():
        raise RuntimeError(f"{asset_path}: {D455_ASSET_PRIM}/{D455_COLOR_CAMERA} not found")
    cache = UsdGeom.XformCache()
    color_in_model = cache.GetLocalToWorldTransform(color) * cache.GetLocalToWorldTransform(model).GetInverse()
    xform = UsdGeom.Xformable(model)
    xform.ClearXformOpOrder()
    xform.AddTransformOp().Set(color_in_model.GetInverse())
    for name in (*D455_EXTRA_PRIMS, D455_COLOR_CAMERA):
        prim = model.GetPrimAtPath(name)
        if prim.IsValid():
            prim.SetActive(False)
    return str(model.GetPath())


def _textured_mesh(stage, path, image_path, face):
    """(points, normals, st, counts, indices) 의 텍스처 Mesh. 재질은 `scene.add_top_texture` 와 같다
    (UsdPreviewSurface + UsdUVTexture). 법선·st 는 점마다(varying)다."""
    from pxr import Gf, Sdf, UsdGeom, UsdShade, Vt

    points, normals, uv, counts, indices = face
    mesh = UsdGeom.Mesh.Define(stage, path)
    mesh.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(*p) for p in points]))
    mesh.CreateFaceVertexCountsAttr(list(counts))
    mesh.CreateFaceVertexIndicesAttr(list(indices))
    mesh.CreateNormalsAttr(Vt.Vec3fArray([Gf.Vec3f(*n) for n in normals]))
    mesh.SetNormalsInterpolation(UsdGeom.Tokens.varying)
    mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    st = UsdGeom.PrimvarsAPI(mesh).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.varying)
    st.Set(Vt.Vec2fArray([Gf.Vec2f(*t) for t in uv]))
    root = f"{path}_Looks"
    material = UsdShade.Material.Define(stage, f"{root}/QrMaterial")
    shader = UsdShade.Shader.Define(stage, f"{root}/QrMaterial/Surface")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.8)
    reader = UsdShade.Shader.Define(stage, f"{root}/QrMaterial/StReader")
    reader.CreateIdAttr("UsdPrimvarReader_float2")
    reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
    texture = UsdShade.Shader.Define(stage, f"{root}/QrMaterial/Texture")
    texture.CreateIdAttr("UsdUVTexture")
    texture.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(str(image_path))
    texture.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(reader.ConnectableAPI(), "result")
    texture.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(texture.ConnectableAPI(), "rgb")
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)
    return mesh


class CanisterFaces:
    """선반 약통의 QR 면. 만들 때 약통 자리에 놓고, 약통이 움직이면 `follow` 로 맞춘다."""

    def __init__(self, stage, root, cells, containers, qr_dir, log=print):
        from pathlib import Path

        from isaacsim.core.prims import SingleXFormPrim

        self._faces = {}
        missing = []
        for cell_id, cell in sorted(cells.items()):
            cid = containers.get(cell_id)
            image = Path(qr_dir) / f"{cid}.png" if cid else None
            if image is None or not image.is_file():
                missing.append(f"{cell_id}:{cid or '-'}")
                continue
            prims = []
            for face, mesh in cell_faces(cell):
                path = f"{root}/{cell_id.replace('/', '_')}_{face}"
                _textured_mesh(stage, path, image, mesh)
                prims.append(SingleXFormPrim(prim_path=path, name=f"canister_qr_{cell_id.replace('/', '_')}_{face}"))
            self._faces[cell_id] = prims
        if missing:
            raise RuntimeError(f"canister QR images missing for {missing}; run make_qr_textures.py --catalog")
        log(f"canister_qr faces={sum(map(len, self._faces.values()))} cells={len(self._faces)} dir={qr_dir} "
            f"ids={sorted(containers[c] for c in self._faces)}")

    def follow(self, cell_id, position, orientation_wxyz):
        """그 칸 약통의 두 면을 약통 자세로. 모르는 칸이면 아무것도 안 한다."""
        import numpy as np

        for prim in self._faces.get(cell_id, ()):
            prim.set_world_pose(position=np.array(position), orientation=np.array(orientation_wxyz))


class M0609HandCamera:
    """M0609 손 카메라. `link_6` 을 따라 매 스텝 옮기고 `/m0609/hand_camera/image_raw`·`camera_info` 를 낸다."""

    def __init__(self, stage, robot_prim, path, graph_path, render_hz, resolution, max_hz, log=print,
                 body_asset=None):
        import omni.graph.core as og
        import usdrt
        from isaacsim.core.prims import SingleXFormPrim
        from pxr import Gf, Usd, UsdGeom

        from . import sensors as S

        link = next((p for p in Usd.PrimRange(stage.GetPrimAtPath(robot_prim), Usd.TraverseInstanceProxies())
                     if p.GetName() == "link_6"), None)
        if link is None:
            raise RuntimeError(f"link_6 not found under {robot_prim}")
        self._link = SingleXFormPrim(prim_path=str(link.GetPath()), name="m0609_camera_link")
        camera = UsdGeom.Camera.Define(stage, path)
        camera.CreateFocalLengthAttr(M0609_CAMERA_FOCAL_MM)
        camera.CreateHorizontalApertureAttr(M0609_CAMERA_H_APERTURE_MM)
        camera.CreateVerticalApertureAttr(M0609_CAMERA_V_APERTURE_MM)
        camera.CreateClippingRangeAttr(Gf.Vec2f(M0609_CAMERA_NEAR_CLIP, 10.0))
        body = None
        if body_asset is not None:
            try:
                body = attach_d455_model(stage, path, body_asset)
            except Exception as error:  # 몸체는 보이기용이다. 없어도 카메라는 낸다
                log(f"WARN m0609 hand_camera body disabled reason={type(error).__name__}: {error}")
        self._camera = SingleXFormPrim(prim_path=path, name="m0609_hand_camera")
        frame = "m0609/hand_camera_optical"
        skip = S.frame_skip(render_hz, max_hz)
        width, height = resolution
        keys = og.Controller.Keys
        og.Controller.edit(
            {"graph_path": graph_path, "evaluator_name": "execution"},
            {
                keys.CREATE_NODES: [
                    ("OnTick", "omni.graph.action.OnPlaybackTick"),
                    ("RenderProduct", "isaacsim.core.nodes.IsaacCreateRenderProduct"),
                    ("CameraRgb", "isaacsim.ros2.bridge.ROS2CameraHelper"),
                    ("CameraInfo", "isaacsim.ros2.bridge.ROS2CameraInfoHelper"),
                ],
                keys.CONNECT: [
                    ("OnTick.outputs:tick", "RenderProduct.inputs:execIn"),
                    ("RenderProduct.outputs:execOut", "CameraRgb.inputs:execIn"),
                    ("RenderProduct.outputs:execOut", "CameraInfo.inputs:execIn"),
                    ("RenderProduct.outputs:renderProductPath", "CameraRgb.inputs:renderProductPath"),
                    ("RenderProduct.outputs:renderProductPath", "CameraInfo.inputs:renderProductPath"),
                ],
                keys.SET_VALUES: [
                    ("RenderProduct.inputs:cameraPrim", [usdrt.Sdf.Path(path)]),
                    ("RenderProduct.inputs:width", int(width)),
                    ("RenderProduct.inputs:height", int(height)),
                    ("CameraRgb.inputs:type", "rgb"),
                    ("CameraRgb.inputs:nodeNamespace", "m0609/hand_camera"),
                    ("CameraRgb.inputs:topicName", "image_raw"),
                    ("CameraRgb.inputs:frameId", frame),
                    ("CameraRgb.inputs:qosProfile", S.SENSOR_QOS_DEPTH2),
                    ("CameraRgb.inputs:frameSkipCount", skip),
                    ("CameraInfo.inputs:nodeNamespace", "m0609/hand_camera"),
                    ("CameraInfo.inputs:topicName", "camera_info"),
                    ("CameraInfo.inputs:frameId", frame),
                    ("CameraInfo.inputs:qosProfile", S.SENSOR_QOS_DEPTH2),
                    ("CameraInfo.inputs:frameSkipCount", skip),
                ],
            },
        )
        log(f"m0609 hand_camera prim={path} follows={link.GetPath()} mount_t={M0609_CAMERA_T} "
            f"mount_q={M0609_CAMERA_Q} (M0617 에서 추출, M0609 미확인) resolution={width}x{height} "
            f"rate={S.published_rate(render_hz, skip):.1f}Hz(skip {skip}) "
            f"topics=/m0609/hand_camera/image_raw,camera_info frame={frame} tf=none "
            f"body={body or 'none'} near_clip={M0609_CAMERA_NEAR_CLIP}")

    def follow(self):
        """link_6 의 지금 자세로 카메라를 옮긴다. 매 물리 스텝 부른다."""
        import numpy as np

        xyz, quat = self._link.get_world_pose()
        position, orientation = camera_world_pose(tuple(map(float, xyz)), tuple(map(float, quat)))
        self._camera.set_world_pose(position=np.array(position), orientation=np.array(orientation))
