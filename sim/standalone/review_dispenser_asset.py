#!/usr/bin/env python3
"""Render standalone before/after assets from identical Z-up cameras; no ROS or physics."""
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--after', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--close', action='store_true', help='Close after capturing the review views')
    args = parser.parse_args()
    for path in (args.before, args.after):
        if not path.is_file():
            parser.error(f'missing asset: {path}')
    args.output.mkdir(parents=True, exist_ok=False)
    from isaacsim import SimulationApp
    app = SimulationApp({'headless': False, 'width': 1280, 'height': 900})
    import omni.usd
    from omni.kit.viewport.utility import capture_viewport_to_file, get_active_viewport
    from pxr import Gf, UsdGeom, UsdLux
    omni.usd.get_context().new_stage()
    stage = omni.usd.get_context().get_stage()
    UsdGeom.SetStageUpAxis(stage, 'Z')
    UsdGeom.SetStageMetersPerUnit(stage, 1.)
    roots = {}
    for name, path in [('before', args.before), ('after', args.after)]:
        root = UsdGeom.Xform.Define(stage, '/'+name)
        root.GetPrim().GetReferences().AddReference(str(path.resolve()))
        roots[name] = UsdGeom.Imageable(root)
    light = UsdLux.DomeLight.Define(stage, '/Dome')
    light.CreateIntensityAttr(850)
    sun = UsdLux.DistantLight.Define(stage, '/Key')
    sun.CreateIntensityAttr(1600)
    UsdGeom.Xformable(sun).AddRotateXYZOp().Set(Gf.Vec3f(30, -25, -20))
    floor = UsdGeom.Cube.Define(stage, '/Floor')
    floor.CreateSizeAttr(1)
    floor.CreateDisplayColorAttr([Gf.Vec3f(.22, .24, .27)])
    xf = UsdGeom.Xformable(floor)
    xf.AddTranslateOp().Set(Gf.Vec3d(0, 0, -.03))
    xf.AddScaleOp().Set(Gf.Vec3f(8, 8, .05))
    camera = UsdGeom.Camera.Define(stage, '/ReviewCamera')
    camera.CreateHorizontalApertureAttr(30.)
    camera.CreateFocalLengthAttr(28.)
    transform = UsdGeom.Xformable(camera).AddTransformOp()
    viewport = get_active_viewport()
    viewport.resolution = (1200, 900)
    viewport.camera_path = '/ReviewCamera'
    views = {'front': ((0, -4.5, 1.65), (0, -.05, 1.15)),
             'inlets': ((.75, -2.0, 1.38), (.75, -.52, .97)),
             'mounts': ((2.0, -1.8, 1.55), (.75, -.50, .95))}
    for name in ('before', 'after'):
        for key, root in roots.items():
            root.MakeVisible() if key == name else root.MakeInvisible()
        for view, (eye, target) in views.items():
            transform.Set(Gf.Matrix4d().SetLookAt(Gf.Vec3d(*eye), Gf.Vec3d(*target),
                                               Gf.Vec3d(0, 0, 1)).GetInverse())
            for _ in range(90):
                app.update()
            output = args.output/f'{name}-{view}.png'
            capture = capture_viewport_to_file(viewport, str(output))
            for _ in range(120):
                app.update()
                if output.exists() and output.stat().st_size:
                    break
            if not output.exists():
                raise RuntimeError(f'capture failed: {output}')
            print(f'CAPTURE {output}', flush=True)
            del capture
    eye, target = views['front']
    transform.Set(Gf.Matrix4d().SetLookAt(Gf.Vec3d(*eye), Gf.Vec3d(*target), Gf.Vec3d(0, 0, 1)).GetInverse())
    print('ASSET_REVIEW_READY physics=OFF robot_motion=NOT_RUN', flush=True)
    try:
        if not args.close:
            while app.is_running():
                app.update()
    finally:
        app.close()


if __name__ == '__main__':
    main()
