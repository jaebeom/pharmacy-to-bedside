#!/usr/bin/env python3
"""Open prepared #484 + #485 workcell; --intake-demo runs synthetic intake cases.

Default preview and intake fixture do not start physics or ROS. The opt-in
conveyor probe runs physical belt transport with robot bodies fixed. Neither
mode claims robot transport or publishes REFILL_DONE / production inventory.
"""
import argparse
import json
import math
from pathlib import Path
import signal
import threading


def run_review_loop(app, demo=None, probe=None):
    """Save an incomplete probe before Kit tears down its USD/physics plugins."""
    from minimal_clock import install_sigint_handler

    stop_event = threading.Event()
    previous = install_sigint_handler(stop_event)
    try:
        while not stop_event.is_set() and app.is_running():
            if probe:
                probe.step()
            else:
                app.update()
            if demo:
                demo.tick()
    finally:
        try:
            if probe:
                try:
                    probe.abort()
                finally:
                    probe.log.close()
        finally:
            try:
                app.close()
            finally:
                signal.signal(signal.SIGINT, previous)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-usd', type=Path, required=True, help='Resolved #484 hospital_navigationv1 layer')
    parser.add_argument('--robot-usd', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='New external run directory')
    parser.add_argument('--intake-demo', action='store_true')
    parser.add_argument('--view', choices=('overview', 'dispenser', 'loading', 'conveyor'), default='overview')
    parser.add_argument('--amr-combined', type=Path, help='The Ridgeback+UR5 asset used by pharmacy_stage')
    parser.add_argument('--amr-start', type=float, nargs=2, metavar=('X', 'Y'))
    parser.add_argument('--conveyor-probe', type=Path, help='Local measured physical conveyor probe inputs')
    args = parser.parse_args()
    if bool(args.amr_combined) != bool(args.amr_start):
        parser.error('--amr-combined and --amr-start must be supplied together')
    if args.amr_start and not all(math.isfinite(v) for v in args.amr_start):
        parser.error('--amr-start must be finite')
    if args.view == 'loading' and not args.amr_combined:
        parser.error('--view loading requires --amr-combined')
    if args.conveyor_probe and args.intake_demo:
        parser.error('physical conveyor probe and synthetic intake demo cannot run together')
    if args.view == 'conveyor' and not args.conveyor_probe:
        parser.error('--view conveyor requires --conveyor-probe')
    for file in (args.base_usd, args.robot_usd):
        if not file.is_file():
            parser.error(f'missing asset: {file}')
    if args.amr_combined and not args.amr_combined.is_file():
        parser.error(f'missing asset: {args.amr_combined}')
    if args.output.exists():
        parser.error('--output must not exist; preserve earlier trials')
    from isaacsim import SimulationApp
    app = SimulationApp({'headless': False, 'width': 1440, 'height': 900})
    import omni.usd
    if args.conveyor_probe:
        from isaacsim.core.utils.extensions import enable_extension
        enable_extension('isaacsim.asset.gen.conveyor')
    from omni.kit.viewport.utility import get_active_viewport
    from pxr import Gf, Sdf, UsdGeom
    from p3sim.workcell_preview import IntakeDemo, build_layout
    from p3sim.dispenser_reference import check_hospital_dispenser
    asset = Path(__file__).resolve().parents[2]/'src/rokey_p3_description/models/dispenser/dispenser.usdc'
    omni.usd.get_context().open_stage(str(args.base_usd.resolve()))
    for _ in range(60):
        app.update()
    stage = omni.usd.get_context().get_stage()
    if stage is None:
        raise RuntimeError('base stage did not open')
    try:
        build_layout(stage, asset, args.robot_usd.resolve())
        placement = check_hospital_dispenser(stage, '/World/ReviewedDispenser')
        if args.amr_combined:
            from p3sim import amr_base, layout
            # Use the same asset, mount, base frame and tray as the prior ROS practice.
            previous = stage.GetPrimAtPath('/World/ridgeback_ur5')
            if previous:
                previous.SetActive(False)
            amr_root = '/World/ReviewAmr'
            amr_base.reference(stage, amr_root, str(args.amr_combined.resolve()), args.amr_start)
            amr_base.move_arm_mount(stage, amr_root)
            amr_base.build_arm_base_frame(stage, amr_root)
            amr_base.build_tray_on_base(stage, amr_root, layout)
    except Exception:
        app.close()
        raise
    camera = UsdGeom.Camera.Define(stage, '/WorkcellReviewCamera')
    camera.CreateFocalLengthAttr(20)
    camera.CreateHorizontalApertureAttr(24)
    matrix = Gf.Matrix4d().SetLookAt(Gf.Vec3d(-3.3, 0, 6.5), Gf.Vec3d(-3.3, 11.2, .9), Gf.Vec3d(0, 0, 1))
    if args.view == 'dispenser':
        centre = placement['anchors_world']['PillOpening']
        eye = Gf.Vec3d(centre[0]-.5, centre[1]-3.5, 2.0)
        target = Gf.Vec3d(centre[0]-.5, centre[1]+.4, 1.2)
        matrix = Gf.Matrix4d().SetLookAt(eye, target, Gf.Vec3d(0, 0, 1))
    if args.view == 'loading':
        x, y = args.amr_start
        matrix = Gf.Matrix4d().SetLookAt(Gf.Vec3d(x+1, y-2.5, 2.0),
                                        Gf.Vec3d(x-.8, y+.5, .45), Gf.Vec3d(0, 0, 1))
    if args.view == 'conveyor':
        probe_config = json.loads(args.conveyor_probe.read_text())
        start, end = probe_config['spawn'], probe_config['end']
        centre = [(a+b)/2 for a, b in zip(start, end, strict=True)]
        camera.CreateFocalLengthAttr(14)
        matrix = Gf.Matrix4d().SetLookAt(Gf.Vec3d(centre[0]+4, centre[1]-5, 8),
                                        Gf.Vec3d(*centre), Gf.Vec3d(0, 0, 1))
    UsdGeom.Xformable(camera).AddTransformOp().Set(matrix.GetInverse())
    get_active_viewport().camera_path = '/WorkcellReviewCamera'
    args.output.mkdir(parents=True)
    (args.output/'dispenser-placement.json').write_text(json.dumps(placement, indent=2)+'\n')
    print('DISPENSER_REFERENCE '+json.dumps(placement), flush=True)
    if args.amr_combined:
        import hashlib
        amr = {'asset_sha256': hashlib.sha256(args.amr_combined.read_bytes()).hexdigest(),
               'prim': '/World/ReviewAmr', 'start_xy': args.amr_start, 'count': 1,
               'mount_local': amr_base.ARM_MOUNT_LOCAL, 'physics': 'OFF', 'ros': 'OFF'}
        (args.output/'amr-placement.json').write_text(json.dumps(amr, indent=2)+'\n')
        print('AMR_REFERENCE '+json.dumps(amr), flush=True)
    override = args.output/'layout-overrides.usda'
    stage.GetSessionLayer().Export(str(override.resolve()))
    review = Sdf.Layer.CreateNew(str((args.output/'review.usda').resolve()))
    review.defaultPrim = 'World'
    review.subLayerPaths = [str(override.resolve()), str(args.base_usd.resolve())]
    review.Save()
    demo = IntakeDemo(stage, args.output) if args.intake_demo else None
    probe = None
    if args.conveyor_probe:
        from p3sim.hospital_conveyor_probe import HospitalConveyorProbe
        try:
            probe = HospitalConveyorProbe(stage, args.conveyor_probe, args.output)
        except Exception:
            app.close()
            raise
    # Reproducible inspection lighting; the hospital stage lights overexpose this review camera.
    import omni.kit.actions.core
    lighting = omni.kit.actions.core.get_action_registry().execute_action(
        'omni.kit.viewport.menubar.lighting', 'set_lighting_mode_rig', lighting_mode=-1)
    print('REVIEW_LIGHTING '+str(lighting), flush=True)
    if probe:
        # Preserve the prepared stock/chute, which do not exist in the earlier layout-only export.
        prepared = args.output/'probe-overrides.usda'
        stage.GetSessionLayer().Export(str(prepared.resolve()))
        prepared_review = Sdf.Layer.CreateNew(str((args.output/'probe-review.usda').resolve()))
        prepared_review.defaultPrim = 'World'
        prepared_review.subLayerPaths = [str(prepared.resolve()), str(args.base_usd.resolve())]
        prepared_review.Save()
    print('WORKCELL_READY mode='+('PHYSICAL_CONVEYOR_PROBE' if probe else 'KINEMATIC_FIXTURE'), flush=True)
    run_review_loop(app, demo, probe)


if __name__ == '__main__':
    main()
