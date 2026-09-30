#!/usr/bin/env python3
"""Exercise and verify the four hospital conveyor routes in Isaac Sim.

This checks that the requested USD/OmniGraph inputs accept and retain the
expected values. Keep the GUI visible to confirm the physical parcel path.
"""

import argparse
import json
import os
import sys
from pathlib import Path


STANDALONE = Path(__file__).resolve().parent
sys.path.insert(0, str(STANDALONE))

from p3sim import common  # noqa: E402
from p3sim import hospital_assets  # noqa: E402
from p3sim import sorter  # noqa: E402


log = common.Logger("[conveyor_test]")

DEFAULT_CUSTOM_ASSETS_ZIP = (
    STANDALONE.parent / "outputs" / "hospital-custom-assets-20260918.zip"
)
DEFAULT_ISAAC_ASSETS_ROOT = (
    os.environ.get("P3_HOSPITAL_ISAAC_ASSETS_ROOT")
    or os.environ.get("P3_ISAAC_ASSETS_ROOT")
    or "https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/5.1"
)


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--scene", type=Path,
                        help="prepared/collected hospital USD")
    source.add_argument("--custom-assets", type=Path,
                        help="custom asset root used by hospital_layout.usda")
    source.add_argument("--custom-assets-zip", type=Path,
                        help="custom asset ZIP (default: sim/outputs/hospital-custom-assets-20260918.zip)")
    parser.add_argument("--isaac-assets-root", default=DEFAULT_ISAAC_ASSETS_ROOT,
                        help="Assets/Isaac/5.1 root; defaults to the official Isaac 5.1 cloud assets")
    parser.add_argument("--runtime-dir", type=Path)
    parser.add_argument(
        "--sorter-config", type=Path,
        default=STANDALONE / "conveyor_config.example.json",
        help="sorter JSON (default: conveyor_config.example.json)",
    )
    parser.add_argument(
        "--routes", type=int, nargs="+", choices=(1, 2, 3, 4),
        default=[1, 2, 3, 4],
        help="routes to test in order (default: 1 2 3 4)",
    )
    parser.add_argument(
        "--hold-seconds", type=common.positive_float, default=8.0,
        help="physics time to hold each route (default: 8)",
    )
    parser.add_argument(
        "--settle-frames", type=int, default=3,
        help="frames before attribute readback (default: 3)",
    )
    parser.add_argument("--physics-dt", type=common.positive_float,
                        default=1.0 / 60.0)
    parser.add_argument("--render-dt", type=common.positive_float,
                        default=1.0 / 60.0)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument(
        "--manual", action="store_true",
        help="wait for Enter before advancing to the next route",
    )
    parser.add_argument(
        "--parcel-prim", default="/World/Cube_01",
        help="rigid parcel prim reset before each route (default: /World/Cube_01)",
    )
    return parser


def parse_args(argv=None):
    parser = build_parser()
    args, _unknown = parser.parse_known_args(argv)
    if args.scene is None and args.custom_assets is None and args.custom_assets_zip is None:
        args.custom_assets_zip = DEFAULT_CUSTOM_ASSETS_ZIP
    if args.settle_frames < 0:
        parser.error("--settle-frames must be zero or greater")
    return args


def _plain(value):
    """Convert USD vector/scalar values into comparison-friendly Python data."""
    if isinstance(value, bool):
        return value
    try:
        return [float(component) for component in value]
    except TypeError:
        return value


def _expected(config, route, routes):
    active_junction = routes[route]
    return {
        config[name]["reroute_attribute"]: name == active_junction
        for name in sorter.JUNCTIONS
    }


def _verify(stage, expected):
    failures = []
    for path, wanted in expected.items():
        attribute = stage.GetAttributeAtPath(path)
        actual = _plain(attribute.Get()) if attribute and attribute.IsValid() else None
        wanted = _plain(wanted)
        passed = actual == wanted
        log(f"{'PASS' if passed else 'FAIL'} {path} expected={wanted} actual={actual}")
        if not passed:
            failures.append((path, wanted, actual))
    return failures


def _step(world, frames, *, render):
    for _ in range(frames):
        world.step(render=render)


def main(argv=None):
    args = parse_args(argv)
    scene_path, search_paths = hospital_assets.resolve_scene(
        standalone_dir=STANDALONE,
        scene=args.scene,
        custom_assets=args.custom_assets,
        custom_assets_zip=args.custom_assets_zip,
        isaac_assets_root=args.isaac_assets_root,
        runtime_dir=args.runtime_dir,
    )
    os.environ["PXR_AR_DEFAULT_SEARCH_PATH"] = os.pathsep.join(search_paths)

    # Isaac/Omni modules must be imported only after SimulationApp starts.
    from isaacsim import SimulationApp

    simulation_app = SimulationApp({"headless": args.headless})
    failed = False
    try:
        import numpy as np
        from isaacsim.core.prims import SingleRigidPrim
        from p3sim import hospital_scene

        world, stage = hospital_scene.load(
            simulation_app,
            scene_path,
            physics_dt=args.physics_dt,
            rendering_dt=args.render_dt,
        )
        router = sorter.SorterRouter(stage, args.sorter_config, log=log)
        config = json.loads(
            Path(args.sorter_config).expanduser().resolve().read_text(encoding="utf-8")
        )

        if not stage.GetPrimAtPath(args.parcel_prim).IsValid():
            raise RuntimeError(f"parcel prim not found: {args.parcel_prim}")
        parcel = world.scene.add(SingleRigidPrim(
            prim_path=args.parcel_prim,
            name="conveyor_test_parcel",
            reset_xform_properties=False,
        ))
        world.reset()
        parcel_position, parcel_orientation = parcel.get_world_pose()
        parcel_position = parcel_position.copy()
        parcel_orientation = parcel_orientation.copy()

        render = not args.headless
        hold_frames = max(1, round(args.hold_seconds / args.physics_dt))
        log(f"scene={scene_path}")
        log(f"routes={args.routes} hold={args.hold_seconds:.2f}s ({hold_frames} frames)")

        for index, route in enumerate(args.routes, start=1):
            if not simulation_app.is_running() or simulation_app.is_exiting():
                log("Isaac Sim closed before the test completed")
                failed = True
                break

            log(f"--- route {route} ({index}/{len(args.routes)}) ---")
            router.route_to(route)
            parcel.set_world_pose(position=parcel_position, orientation=parcel_orientation)
            parcel.set_linear_velocity(np.zeros(3))
            parcel.set_angular_velocity(np.zeros(3))
            log(f"parcel reset {args.parcel_prim} xyz={_plain(parcel_position)}")
            _step(world, args.settle_frames, render=render)
            failures = _verify(stage, _expected(config, route, sorter.ROUTES))
            if failures:
                failed = True
                continue

            log(f"OBSERVE route {route}: insert/watch one parcel now")
            _step(world, hold_frames, render=render)
            if args.manual and index < len(args.routes):
                input("Press Enter for the next route...")

        log("RESULT: FAIL" if failed else "RESULT: PASS (attribute readback)")
        if not failed:
            log("Confirm the physical outlet visually; readback cannot detect reversed True/False mapping.")
    except Exception as exc:
        failed = True
        log(f"ERROR {type(exc).__name__}: {exc}")
    finally:
        simulation_app.close()
    return common.exit_code_for(failed)


if __name__ == "__main__":
    sys.exit(main())
