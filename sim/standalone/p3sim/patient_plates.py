"""침상 협탁의 환자 인식표 판(시각 소품, 작전 9/23 선택 카드). Isaac 임포트는 늦게 한다.

- 판은 물리·충돌 없는 시각 자산이다. camera 인증은 이 QR 을 읽고, sim 인증은 참값 센서를 쓴다.
- 판은 협탁 윗면에 눕힌 흰 판 + 그 위 `pt-<환자 ID>` QR 이다. 환자 ID 는 주문 풀의 침상 ↔ 환자(한 침상에 한 명)다.
- 병실 판은 로봇에 가까운 가장자리의 `<zone>/tag` 위치를 따른다. 스테이션은 기존 먼 가장자리다.
"""

#: 판 한 변·두께(m), QR 한 변(m), 판과 협탁 가장자리 사이 여유(m).
PLATE_SIDE = 0.10
PLATE_THICKNESS = 0.004
QR_SIDE = 0.08
EDGE_MARGIN = 0.02
#: 판 색(흰색).
PLATE_COLOR = (0.97, 0.97, 0.97)
QR_LIFT = 0.0005


def near_tag_pose(base_xy, cabinet_xyz, width):
    """탁자 안쪽 여유를 유지한 채 로봇에 가까운 가장자리의 QR 표면 좌표."""
    cx, cy, top = cabinet_xyz
    delta = (base_xy[0] - cx, base_xy[1] - cy)
    axis = 0 if abs(delta[0]) >= abs(delta[1]) else 1
    reach = max(0.0, width[axis] / 2.0 - PLATE_SIDE / 2.0 - EDGE_MARGIN)
    center = [cx, cy]
    center[axis] += (1.0 if delta[axis] >= 0 else -1.0) * reach
    return (*center, top + PLATE_THICKNESS + QR_LIFT)


def plates(zones, cabinet_sizes, bed_patients, stations=()):
    """[{bed, tag_id, center(판 중심), top(판 윗면 z)}]. 환자가 없거나 둘 이상인 침상은 뺀다.

    `stations` 의 테이블(station_b·station_c·station_d)은 환자와 상관없이 `st-<zone>` 판이다
    (재범 9/25: 테이블에는 스테이션 표가 붙는다 — 참값 센서 truth_sensors.tag_for_zone 과 같은 규칙).

    zones: `hospital_zones.zones_from_yaml` 의 {이름: (x, y, z, yaw)}. cabinet z 는 협탁 윗면이다.
    cabinet_sizes: {`<침상>/cabinet`: (x 폭, y 폭)}(월드 축). bed_patients: {침상: {환자 ID}}.
    """
    out = []
    for bed in sorted(name for name in zones if "/" not in name and f"{name}/cabinet" in zones):
        patients = bed_patients.get(bed, set())
        if bed in stations:
            tag_id = f"st-{bed}"
        elif len(patients) == 1:
            tag_id = f"pt-{next(iter(patients))}"
        else:
            continue
        bx, by = zones[bed][:2]
        cx, cy, top = zones[f"{bed}/cabinet"][:3]
        width = cabinet_sizes.get(f"{bed}/cabinet")
        if width is None:
            continue
        # 로봇 → 협탁 방향의 큰 축으로, 먼 가장자리 안쪽에 둔다.
        axis = 0 if abs(cx - bx) >= abs(cy - by) else 1
        sign = 1.0 if (cx - bx, cy - by)[axis] >= 0.0 else -1.0
        reach = max(0.0, width[axis] / 2.0 - PLATE_SIDE / 2.0 - EDGE_MARGIN)
        centre = [cx, cy]
        centre[axis] += sign * reach
        if bed.startswith('bed_') and f'{bed}/tag' in zones:
            # TF 목표와 눈에 보이는 QR 면을 같은 좌표로 만든다.
            tx, ty, tz = zones[f'{bed}/tag'][:3]
            centre = [tx, ty]
            top = tz - PLATE_THICKNESS - QR_LIFT
        out.append({"bed": bed, "tag_id": tag_id,
                    "center": (centre[0], centre[1], top + PLATE_THICKNESS / 2.0),
                    "top": top + PLATE_THICKNESS})
    return out


def build(stage, root, items, qr_dir, log=print):
    """판(VisualCuboid)과 QR 면을 세운다. QR 이미지가 없는 판은 판만 세우고 경고 한 줄. 반환은 세운 판 수."""
    from pathlib import Path

    from pxr import Gf, UsdGeom

    from . import layout as L
    from . import scene

    boxes = [L.Box(f"Plate_{item['bed']}", item["center"], (PLATE_SIDE, PLATE_SIDE, PLATE_THICKNESS),
                   PLATE_COLOR, "visual") for item in items]
    scene.build_boxes(root, boxes)
    missing = []
    for item in items:
        image = Path(qr_dir) / f"{item['tag_id']}.png"
        if not image.is_file():
            missing.append(item["tag_id"])
            continue
        face = f"{root}/Qr_{item['bed']}"
        scene.add_top_texture(stage, face, image, (QR_SIDE, QR_SIDE), QR_LIFT)
        x, y, _z = item["center"]
        UsdGeom.XformCommonAPI(stage.GetPrimAtPath(face)).SetTranslate(Gf.Vec3d(x, y, item["top"]))
    if missing:
        log(f"WARN patient_plates qr missing={missing} dir={qr_dir}; run make_qr_textures.py --order-pool")
    log(f"patient_plates plates={len(items)} beds={[item['bed'] for item in items]} visual_only=true")
    return len(items)
