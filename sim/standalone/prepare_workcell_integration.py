#!/usr/bin/env python3
"""#484 선반 + #485 조제기를 재어 pharmacy_stage 의 병원 base 와 workcell.json 을 만든다.

전재환이 실습37 에서 쓴 도구(`67be4c5`)를 저장소로 옮긴 것이다. 옮기면서 뺀 것은 `--pill-offset` 하나다.
원통 투입구를 +X 0.30 m, −Y 0.10 m 옮긴 실습37 합성 레이어는 재범 9/22 결정(#496,
`src/rokey_p3_description/models/dispenser/README.md`)으로 **쓰지 않는다**. 조제기는 루트 평행이동만 하고
투입구·받침·앵커는 기준 에셋 그대로 둔다. `base_scene.add_base_scene()` 의 조제기 검사도 같은 것을 본다 —
투입구를 옮긴 base 는 physics 시작 전에 예외로 멈춘다.

pxr 이 필요하다. usd-core 가 있으면 그대로 쓰고, 없으면(master02) Kit 앱을 headless 로 띄워서 쓴다 —
`~/isaacsim/python.sh` 는 앱 없이 pxr 을 내놓지 않는다. 팔 계획은 절대 실행하지 않는다.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import traceback

#: 선반 기둥(모서리 넷)의 한 변(m). 옆·뒤 판 두께와 같은 값이다.
SHELF_POST = .03
#: 판 충돌 상자를 잰 판 두께 위아래로 조금 키우는 양(m). 0 이면 약통이 면에 정확히 닿아 접촉이 튄다.
SHELF_BOARD_MARGIN = .001
#: 선반은 메시 충돌체를 쓰지 않는다. 9/23 에 두 번 물렸다.
#: ① 삼각 메시(`none`): `PxShape::getMaterialFromInternalFaceIndex … returning NULL` 이 419,292 줄 나고
#:    rtf 0.32 로 떨어졌다(m2-hf-full-39d1ce5). 그 호출은 삼각 메시 충돌체에만 있다 — 약통 18개가 판 위에
#:    늘 닿아 있으니 매 스텝 난다. 실습37 에서도 같은 경고가 났고 원인 미확정으로 남았다(practice-37 5항).
#: ② convexDecomposition: 경고는 멎었지만 껍질이 판을 두껍게·기울게 만들어 모듈이 미끄러져 떨어지고
#:    위층 것이 판 위에 떠 보였다(재범 화면, 3b76030 회차).
#: 그래서 **잰 판 두께 그대로의 얇은 상자**와 모서리 기둥 넷을 세운다. 잰 값(obstacles)과 같은 상자라
#: 팔이 계획하는 것과 물리가 미는 것이 같다.
#: 조제기 몸통(투입구 밖) 충돌체의 근사. 부품 메시가 288 개라 분해는 굽는 값이 비싸다. 정적 기계라
#: 부품마다 볼록 껍질이면 막이로 충분하다. 투입구(`/Inlets/`)만 오목해서 삼각 메시 그대로 둔다.
BODY_APPROXIMATION = 'convexHull'
#: 근사 이름은 UsdPhysics 값이다. 회차에서 다른 값을 시험할 수 있게 CLI 로 연다.
APPROXIMATIONS = ('none', 'convexHull', 'convexDecomposition', 'boundingCube', 'boundingSphere', 'meshSimplification')


def collider(stage, path, lo, hi):
    """월드 축 정렬 상자 하나를 충돌체로 세운다. 보이지는 않는다(그림은 선반 메시 그대로다)."""
    from pxr import Gf, UsdGeom, UsdPhysics

    size = [float(b) - float(a) for a, b in zip(lo, hi, strict=True)]
    if min(size) <= 1e-5:
        return None
    cube = UsdGeom.Cube.Define(stage, path)
    cube.CreateSizeAttr(1.)
    xform = UsdGeom.Xformable(cube)
    xform.AddTranslateOp().Set(Gf.Vec3d(*((float(a) + float(b)) / 2. for a, b in zip(lo, hi, strict=True))))
    xform.AddScaleOp().Set(Gf.Vec3f(*size))
    UsdGeom.Imageable(cube).CreateVisibilityAttr(UsdGeom.Tokens.invisible)
    UsdPhysics.CollisionAPI.Apply(cube.GetPrim())
    return path


def prepare(source, dispenser, output, body_approximation=BODY_APPROXIMATION):
    from pxr import Gf, Usd, UsdGeom, UsdPhysics
    from p3sim.workcell_preview import DISPENSER_ORIGIN, shelf_surface
    source_stage = Usd.Stage.Open(str(source.resolve()))
    if UsdGeom.GetStageUpAxis(source_stage) != 'Z' or UsdGeom.GetStageMetersPerUnit(source_stage) != 1.:
        raise ValueError('source hospital must use metres and Z-up')
    output.mkdir(parents=True, exist_ok=False)
    stage = Usd.Stage.CreateNew(str(output/'base.usda'))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.)
    stage.GetRootLayer().subLayerPaths = [str(source.resolve())]
    stage.SetDefaultPrim(stage.GetPrimAtPath('/World'))
    # 씬마다 박힌 것이 다르다(hospital_navigationv1 에는 ridgeback_ur5 가 없다). 없는 것은 적고 넘어간다.
    absent = []
    for path in ('/World/machine', '/World/ridgeback_ur5'):
        prim = stage.GetPrimAtPath(path)
        if prim:
            prim.SetActive(False)
        else:
            absent.append(path)
    asset = UsdGeom.Xform.Define(stage, '/World/IntegratedDispenser')
    asset.GetPrim().GetReferences().AddReference(str(dispenser.resolve()))
    asset.AddTranslateOp().Set(Gf.Vec3d(*DISPENSER_ORIGIN))
    obstacles, cells, measurements = [], {}, []
    cache = UsdGeom.XformCache()
    bounds = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default', 'render'])

    def obstacle(name, lo, hi):
        size = [float(b-a) for a, b in zip(lo, hi, strict=True)]
        if min(size) > 1e-5:
            obstacles.append({'name': name, 'center': [float((a+b)/2) for a, b in zip(lo, hi, strict=True)],
                              'size': size})

    for number in range(67, 76):
        shelf = stage.GetPrimAtPath('/World/Environment/hospital/SM_MedShelf_01d_'+str(number))
        x, y, top = shelf_surface(stage, shelf)
        shelf.SetInstanceable(False)
        planes = defaultdict(list)
        for prim in Usd.PrimRange(shelf):
            if not prim.IsA(UsdGeom.Mesh):
                continue
            mesh = UsdGeom.Mesh(prim)
            # 선반 메시에는 충돌을 붙이지 않는다. 층 판마다 얇은 상자와 모서리 기둥 넷을 따로 세운다
            # (재범 화면 9/23: 볼록 껍질이 판을 두껍게·기울게 만들어 모듈이 미끄러지고 위층이 떠 보였다).
            matrix = cache.GetLocalToWorldTransform(prim)
            points = [matrix.Transform(Gf.Vec3d(p)) for p in mesh.GetPointsAttr().Get()]
            indices = mesh.GetFaceVertexIndicesAttr().Get()
            offset = 0
            for n in mesh.GetFaceVertexCountsAttr().Get():
                face = [points[i] for i in indices[offset:offset+n]]
                offset += n
                if n >= 3 and max(p[2] for p in face)-min(p[2] for p in face) < .001:
                    area = sum(abs(Gf.Cross(face[j]-face[0], face[j+1]-face[0])[2])/2 for j in range(1, n-1))
                    if area > 1e-6:
                        planes[round(sum(p[2] for p in face)/n, 3)].append((area, face))
        board_levels = sorted(z for z, faces in planes.items() if sum(a for a, _ in faces) > .08)
        if len(board_levels) % 2:
            raise ValueError(f'Shelf {number}: unpaired horizontal board faces')
        for i in range(0, len(board_levels), 2):
            lower, upper = board_levels[i:i+2]
            if upper-lower > .10:
                raise ValueError(f'Shelf {number}: board thickness exceeds 10 cm')
            verts = [v for z in (lower, upper) for _, face in planes[z] for v in face]
            lo = [min(p[j] for p in verts) for j in range(3)]
            hi = [max(p[j] for p in verts) for j in range(3)]
            lo[2], hi[2] = lower - SHELF_BOARD_MARGIN, upper + SHELF_BOARD_MARGIN
            obstacle(f'Shelf{number}Board{i//2}', lo, hi)
            collider(stage, f'/World/ShelfCollision/Shelf{number}/Board{i//2}', lo, hi)
        bb = bounds.ComputeWorldBound(shelf).ComputeAlignedRange()
        lo, hi = list(bb.GetMin()), list(bb.GetMax())
        # 기둥 넷. 옆·뒤 통판을 세우면 팔이 앞에서 들어갈 때까지 막힌다 — 모서리만 세운다(작전 9/23).
        for corner, (px, py) in enumerate(((lo[0], lo[1]), (hi[0] - SHELF_POST, lo[1]),
                                           (lo[0], hi[1] - SHELF_POST), (hi[0] - SHELF_POST, hi[1] - SHELF_POST))):
            collider(stage, f'/World/ShelfCollision/Shelf{number}/Post{corner}',
                     (px, py, lo[2]), (px + SHELF_POST, py + SHELF_POST, hi[2]))
        # Conservative side/back envelopes from the measured total shelf bounds (3 cm thick).
        for suffix, low, high in [('Left', lo, [lo[0]+.03, hi[1], hi[2]]),
                                  ('Right', [hi[0]-.03, lo[1], lo[2]], hi),
                                  ('Back', [lo[0], hi[1]-.03, lo[2]], hi)]:
            obstacle(f'Shelf{number}{suffix}', low, high)
        measurements.append({'shelf': number, 'surface': [x, y, top], 'planes_z': board_levels,
                             'bounds_min': lo, 'bounds_max': hi})
        for col, kind in enumerate(('cylinder', 'module')):
            size = {'diameter': .07, 'height': .12} if kind == 'cylinder' else {'x': .06, 'y': .10, 'z': .14}
            cells[f'shelf_{number}/r0c{col}'] = {'shelf': f'shelf_{number}', 'row': 0, 'col': col,
                'type': kind, 'access': 'front', 'surface': [x+(-.17 if col == 0 else .17), y, top],
                'size': size, 'height': .12 if col == 0 else .14}
    for prim in stage.Traverse():
        path = str(prim.GetPath())
        # 씬 컨베이어는 건드리지 않는다. `p3sim.hospital_conveyor.HospitalConveyor` 가 기동 때 이 subtree 를
        # 읽어서 쓴다: OmniGraph 노드의 `inputs:conveyorPrim` 으로 19 몸체를 확인하고, 그래프 변수
        # Velocity·SorterSpeed 를 0 으로 두고, Sorter 의 reroute 를 켜고, 트랙을 운동학 강체 + 표면 속도로
        # 바꾼다. 그래프를 끄면 노드가 안 보여 `컨베이어 노드가 가리키지 않는 몸체다` 로 멈춘다(9/23 회차).
        # 표면 속도로 봉투를 A1 끝까지 보낸 참조 탐침 02(#240)도 이 subtree 를 그대로 둔 장면이었다.
        if path == '/World/Conveyor' or path.startswith('/World/Conveyor/'):
            continue
        if prim.HasAPI(UsdPhysics.RigidBodyAPI):
            UsdPhysics.RigidBodyAPI(prim).GetRigidBodyEnabledAttr().Set(False)
        if prim.IsA(UsdPhysics.Joint):
            UsdPhysics.Joint(prim).GetJointEnabledAttr().Set(False)
        if path.startswith('/World/IntegratedDispenser/') and prim.IsA(UsdGeom.Gprim):
            UsdPhysics.CollisionAPI.Apply(prim)
            if prim.IsA(UsdGeom.Mesh):
                # 투입구만 삼각 메시 그대로다 — 원통 컵과 모듈 구멍은 오목해서 볼록체로 덮으면 입구가 막힌다.
                # 나머지 몸통은 볼록 껍질이다(선반 주석 ① 의 경고가 여기서도 난다).
                approximation = 'none' if '/Inlets/' in path else body_approximation
                UsdPhysics.MeshCollisionAPI.Apply(prim).CreateApproximationAttr(approximation)
            bb = bounds.ComputeWorldBound(prim).ComputeAlignedRange()
            name = prim.GetName()
            if '/Inlets/' in path:
                name = name.replace('Pill', 'RoundBin').replace('Module', 'DispenserFront')
            else:
                name = 'Dispenser_'+path.split('/IntegratedDispenser/', 1)[1].replace('/', '_')
            obstacle(name, bb.GetMin(), bb.GetMax())
    # 기준 에셋 앵커의 월드 좌표다(#485 asset.json anchors_local + DISPENSER_ORIGIN). 옮기지 않는다.
    targets = {'round': {'center': [-8.05, 11.115, .98], 'axis': [0, 0, -1],
                         'inner_diameter': .12, 'floor_z': .86, 'depth': .12},
               'module': {'entry_center': [-7.70, 11.11546546, 1.02], 'axis': [0, 1, 0],
                          'opening': {'x': .08, 'z': .16}, 'depth': .15}}
    from p3sim.dispenser_reference import check_hospital_dispenser
    placement = check_hospital_dispenser(stage, '/World/IntegratedDispenser')
    from p3sim.workcell_layout import compact_body_obstacles
    obstacles, covered = compact_body_obstacles(obstacles)
    data = {'version': 1, 'frame': 'hospital_world_m_z_up',
            'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'dispenser_sha256': hashlib.sha256(dispenser.read_bytes()).hexdigest(),
            'cells': cells, 'targets': targets, 'obstacles': obstacles,
            'contained_body_obstacles': covered,
            'rail': {'origin': [-3.3, 10.75, 0.], 'x_stroke': 11.4, 'y_limits': [-.1, .33],
                     'z_limits': [0., 1.1], 'carriage_height': .25},
            'belt': {'start': [-9.82, 10.9, .82], 'length': 1.6, 'yaw': -1.5707963267948966},
            'amr_start': [1.995591579, 1.999799265],
            'camera': {'eye': [-3.8, 8.1, 4.5], 'target': [-3.8, 11.2, .9], 'focal_mm': 7.},
            'collision': {'shelf': 'boxes', 'shelf_board_margin': SHELF_BOARD_MARGIN, 'shelf_post': SHELF_POST,
                          'dispenser_body': body_approximation, 'dispenser_inlets': 'none'},
            'limits': 'Shelf plane and side/back box envelopes; full hospital navigation not validated.'}
    stage.GetRootLayer().Save()
    (output/'workcell.json').write_text(json.dumps(data, indent=2)+'\n')
    (output/'measurements.json').write_text(json.dumps(measurements, indent=2)+'\n')
    (output/'dispenser-placement.json').write_text(json.dumps(
        {'absent_in_source': absent, **placement}, indent=2)+'\n')
    return data


def start_app(headless):
    """pxr 을 내놓는 파이썬을 고른다.

    usd-core 가 있으면 그대로 쓴다. master02 에는 없다 — 거기서는 `~/isaacsim/python.sh` 도 Kit 앱 없이는
    `pxr` 을 내놓지 않는다(`docs/runbooks/l3-sim-conveyor.md` 2절, 9/20 관측). 그래서 headless 로 띄운다.
    Isaac/Omni import 는 SimulationApp 생성 뒤에만 한다.
    """
    try:
        import pxr  # noqa: F401
    except ModuleNotFoundError:
        from isaacsim import SimulationApp
        return SimulationApp({'headless': headless})
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-usd', type=Path, required=True)
    parser.add_argument('--dispenser-usd', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--show-window', action='store_true',
                        help='Kit 앱을 띄워야 할 때 창을 보인다(기본은 headless)')
    parser.add_argument('--dispenser-body-approximation', choices=APPROXIMATIONS, default=BODY_APPROXIMATION)
    args = parser.parse_args()
    app = start_app(not args.show_window)
    error = None
    try:
        data = prepare(args.base_usd, args.dispenser_usd, args.output,
                       args.dispenser_body_approximation)
        print(json.dumps({'cells': len(data['cells']), 'obstacles': len(data['obstacles']),
                          'round_center': data['targets']['round']['center'],
                          'collision': data['collision']}), flush=True)
        # flush 가 없으면 출력을 파일로 돌렸을 때 이 줄이 사라졌다 — 아래 app.close() 가 버퍼를 비우기 전에
        # 프로세스를 끝낸다(마클1 새 clone 회차32 의 prepare.log). 터미널에서는 줄 단위라 보였다.
    except Exception as failure:       # noqa: BLE001 — 앱을 닫기 전에 종료 코드를 정해야 한다
        traceback.print_exc()
        error = failure
    # SimulationApp.close() 는 오류 뒤에도 프로세스를 0 으로 끝냈다(master02 9/17). 먼저 코드를 정한다.
    code = 1 if error is not None else 0
    if app is not None:
        app.close()
    raise SystemExit(code)


if __name__ == '__main__':
    main()
