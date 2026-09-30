"""Clone a USD pouch template, label it with its order QR (order_id), and spawn it on the conveyor."""

from pathlib import Path

EXPECTED_BEDS = tuple([f"bed_a{i}" for i in range(1, 5)] + [f"bed_b{i}" for i in range(1, 7)])


def generate_and_bind_qr(stage, entries, output_dir, pixels=512, border=4):
    """Generate bed QR PNGs and bind preview materials to each authored child named QR."""
    from make_qr_textures import write_png
    from pxr import Sdf, Usd, UsdShade

    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    results = []
    for bed_id, prim_path in entries:
        root = stage.GetPrimAtPath(prim_path)
        qr_prims = [prim for prim in Usd.PrimRange(root) if prim.GetName() == "QR"]
        if len(qr_prims) != 1:
            raise RuntimeError(f"{bed_id}: expected exactly one QR child below {prim_path}")
        image_path = output / f"{bed_id}.png"
        encoder, decoded = write_png(image_path, bed_id, pixels, border)
        if decoded is not None and decoded != bed_id:
            raise RuntimeError(f"{bed_id}: generated QR decoded as {decoded!r}")
        looks = f"{prim_path}/Looks"
        material = UsdShade.Material.Define(stage, f"{looks}/QrMaterial")
        shader = UsdShade.Shader.Define(stage, f"{looks}/QrMaterial/Surface")
        shader.CreateIdAttr("UsdPreviewSurface")
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.8)
        reader = UsdShade.Shader.Define(stage, f"{looks}/QrMaterial/StReader")
        reader.CreateIdAttr("UsdPrimvarReader_float2")
        reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
        texture = UsdShade.Shader.Define(stage, f"{looks}/QrMaterial/Texture")
        texture.CreateIdAttr("UsdUVTexture")
        texture.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(str(image_path))
        texture.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(reader.ConnectableAPI(), "result")
        texture.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(texture.ConnectableAPI(), "rgb")
        material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
        UsdShade.MaterialBindingAPI.Apply(qr_prims[0]).Bind(material)
        results.append((bed_id, image_path, encoder))
    return results


def track_top(stage, track_path, clearance=0.015):
    """World-space centre of the authored track's bounding-box top."""
    from pxr import Gf, Usd, UsdGeom

    prim = stage.GetPrimAtPath(track_path)
    if not prim.IsValid():
        raise RuntimeError(f"spawn track prim not found: {track_path}")
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
    bounds = cache.ComputeWorldBound(prim).ComputeAlignedRange()
    if bounds.IsEmpty():
        raise RuntimeError(f"spawn track has an empty world bound: {track_path}")
    low, high = bounds.GetMin(), bounds.GetMax()
    return Gf.Vec3d((low[0] + high[0]) / 2.0, (low[1] + high[1]) / 2.0, high[2] + clearance)


def validate_template(stage, template_path, track_path):
    """Validate the single authored template; it may have no QR material yet."""
    from pxr import Usd, UsdPhysics

    errors = []
    template = stage.GetPrimAtPath(template_path)
    if not template.IsValid():
        errors.append(f"template prim not found: {template_path}")
        return errors
    if not stage.GetPrimAtPath(track_path).IsValid():
        errors.append(f"track prim not found: {track_path}")
    if not template.HasAPI(UsdPhysics.RigidBodyAPI):
        errors.append(f"RigidBodyAPI missing on {template_path}")
    descendants = list(Usd.PrimRange(template))
    if not any(child.HasAPI(UsdPhysics.CollisionAPI) for child in descendants):
        errors.append(f"no CollisionAPI below {template_path}")
    qr_prims = [child for child in descendants if child.GetName() == "QR"]
    if len(qr_prims) != 1:
        errors.append(f"expected one child named QR below {template_path}, found {len(qr_prims)}")
    return errors


def bind_qr(stage, pouch_path, payload, output_dir, pixels=512, border=4):
    """Generate one QR (`payload` — for a pouch, its order_id) and bind it to the cloned pouch's QR mesh."""
    return generate_and_bind_qr(stage, [(payload, pouch_path)], output_dir, pixels, border)[0]


class TemplateSpawner:
    """Copy one USD pouch template per order. Spawned prims are never deleted or reset."""

    def __init__(self, stage, template_path, root_path="/World/SpawnedPouches"):
        from pxr import UsdGeom

        self.stage = stage
        self.template_path = template_path
        self.root_path = root_path
        self.sequence = 0
        UsdGeom.Xform.Define(stage, root_path)

    @staticmethod
    def _safe_name(text):
        import re

        return re.sub(r"[^A-Za-z0-9_]", "_", text)

    def spawn(self, order_id, bed_id, position, qr_output_dir):
        from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics

        self.sequence += 1
        name = f"Pouch_{self._safe_name(order_id)}_{self.sequence:04d}"
        path = f"{self.root_path}/{name}"
        layer = self.stage.GetEditTarget().GetLayer()
        if not Sdf.CopySpec(layer, self.template_path, layer, path):
            raise RuntimeError(f"failed to copy {self.template_path} to {path}")
        prim = self.stage.GetPrimAtPath(path)
        prim.SetActive(True)
        UsdGeom.Imageable(prim).MakeVisible()
        body = UsdPhysics.RigidBodyAPI(prim)
        body.CreateRigidBodyEnabledAttr().Set(True)
        qr_prims = [child for child in Usd.PrimRange(prim) if child.GetName() == "QR"]
        if len(qr_prims) != 1:
            raise RuntimeError(f"expected one QR child below {path}")
        qr_xform = UsdGeom.Xformable(qr_prims[0])
        qr_ops = qr_xform.GetOrderedXformOps()
        translate = next((op for op in qr_ops if op.GetOpType() == UsdGeom.XformOp.TypeTranslate), None)
        if translate is None:
            translate = qr_xform.AddTranslateOp()
        translate.Set(Gf.Vec3d(0.0, 0.0, 0.0055))
        orient = next((op for op in qr_ops if op.GetOpType() == UsdGeom.XformOp.TypeOrient), None)
        if orient is None:
            # 아래에서 Gf.Quatd 를 넣으므로 double 로 만든다(기본 float 이면 Type mismatch 로 죽는다 —
            # 템플릿에 orient 가 이미 있으면 안 드러나던 결함, 9/23 시험에서 잡음).
            orient = qr_xform.AddOrientOp(UsdGeom.XformOp.PrecisionDouble)
        orient.Set(Gf.Quatd(0.0, 1.0, 0.0, 0.0))  # 180 deg about X: QR normal points +Z
        xform = UsdGeom.Xformable(prim)
        xform.ClearXformOpOrder()
        xform.AddTranslateOp().Set(Gf.Vec3d(*map(float, position)))
        # 봉투 QR 내용은 **order_id** 다(계약 161·270·649줄 — 팔이 벨트 끝·상판에서 goal order_id 와 대조한다).
        # 처음(#501)에는 bed_id 를 넣었다. 같은 침상의 봉투 둘을 가를 수 없고 팔의 대조가 실패한다.
        # bed_id 는 봉투의 목적지로 프림 속성에만 남긴다.
        prim.CreateAttribute("p3:bedId", Sdf.ValueTypeNames.String).Set(bed_id)
        prim.CreateAttribute("p3:orderId", Sdf.ValueTypeNames.String).Set(order_id)
        bind_qr(self.stage, path, order_id, qr_output_dir)
        return path
