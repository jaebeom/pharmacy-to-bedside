#!/usr/bin/env python3
"""Validate PouchTemplate and create one QR-labelled clone on ConveyorTrack_06."""

import argparse
import sys
from pathlib import Path

STANDALONE = Path(__file__).resolve().parent
sys.path.insert(0, str(STANDALONE))
from p3sim import authored_pouches  # noqa: E402

DEFAULT_SCENE = Path("/home/rokey/hospital_custome/hopital_custome/hospital_navigationv1.usd")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", type=Path, default=DEFAULT_SCENE)
    parser.add_argument("--template-prim", default="/World/PouchTemplate")
    parser.add_argument("--track-prim", default="/World/Conveyor/ConveyorTrack_06")
    parser.add_argument("--qr-output-dir", type=Path, default=STANDALONE.parent / "outputs" / "qr_beds")
    parser.add_argument("--bed-id", choices=authored_pouches.EXPECTED_BEDS, default="bed_a1")
    args = parser.parse_args(argv)
    from isaacsim import SimulationApp

    app = SimulationApp({"headless": True})
    failed = False
    try:
        import omni.usd
        from isaacsim.core.utils.stage import open_stage

        if not open_stage(usd_path=str(args.scene.expanduser().resolve())):
            raise RuntimeError(f"cannot open {args.scene}")
        context = omni.usd.get_context()
        while context.get_stage_loading_status()[2] > 0 and app.is_running():
            app.update()
        for _ in range(10):
            app.update()
        stage = context.get_stage()
        errors = authored_pouches.validate_template(stage, args.template_prim, args.track_prim)
        if errors:
            for error in errors:
                print(f"FAIL {error}", flush=True)
            failed = True
        else:
            position = authored_pouches.track_top(stage, args.track_prim)
            spawner = authored_pouches.TemplateSpawner(stage, args.template_prim, "/World/VerificationPouches")
            path = spawner.spawn("verify-0001", args.bed_id, position, args.qr_output_dir)
            for _ in range(2):
                app.update()
            print(f"OK template={args.template_prim}", flush=True)
            print(f"OK track={args.track_prim} spawn_xyz={[float(v) for v in position]}", flush=True)
            print(f"OK clone={path} qr={args.qr_output_dir / (args.bed_id + '.png')}", flush=True)
    except Exception as exc:
        failed = True
        print(f"FAIL {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
    finally:
        app.close()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
