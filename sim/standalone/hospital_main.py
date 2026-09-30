#!/usr/bin/env python3
"""Open the repository hospital scene and control its four-way conveyor sorter.

Run with Isaac Sim 5.1's python.sh from the repository root. Importing this
module does not start Isaac Sim.
"""

import argparse
import json
import os
import sys
from pathlib import Path

DEFAULT_CUSTOM_ASSETS = (
    Path(os.environ["P3_HOSPITAL_CUSTOM_ASSETS"]).expanduser() if os.environ.get("P3_HOSPITAL_CUSTOM_ASSETS") else None
)
DEFAULT_ISAAC_ASSETS_ROOT = (
    os.environ.get("P3_HOSPITAL_ISAAC_ASSETS_ROOT")
    or os.environ.get("P3_ISAAC_ASSETS_ROOT")
    or "https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/5.1"
)
DEFAULT_CUSTOM_ASSETS_ZIP = Path(__file__).resolve().parents[1] / "outputs" / "hospital-custom-assets-20260918.zip"
DEFAULT_SORTER_CONFIG = Path(
    os.environ.get(
        "P3_HOSPITAL_SORTER_CONFIG",
        str(Path(__file__).resolve().parent / "conveyor_config.example.json"),
    )
)
DEFAULT_ROUTE_TOPIC = os.environ.get("P3_HOSPITAL_ROUTE_TOPIC", "/isaac/conveyor/route")


def configure_internal_ros():
    """Start with Isaac Sim's bundled ROS libraries when launched via i_py."""
    isaac_path = Path(os.environ.get("ISAAC_PATH", str(Path(sys.executable).resolve().parents[2])))
    bridge_root = isaac_path / "exts/isaacsim.ros2.bridge/jazzy"
    library_dir = bridge_root / "lib"
    python_dir = bridge_root / "rclpy"
    if not library_dir.is_dir() or not python_dir.is_dir():
        return

    if os.environ.get("P3_HOSPITAL_INTERNAL_ROS") != "1":
        environment = os.environ.copy()
        environment["P3_HOSPITAL_INTERNAL_ROS"] = "1"
        environment.setdefault("ROS_DISTRO", "jazzy")
        environment.setdefault("RMW_IMPLEMENTATION", "rmw_fastrtps_cpp")
        environment["LD_LIBRARY_PATH"] = os.pathsep.join(
            filter(None, (str(library_dir), environment.get("LD_LIBRARY_PATH")))
        )
        os.execvpe(sys.executable, [sys.executable, *sys.argv], environment)

    if str(python_dir) not in sys.path:
        sys.path.append(str(python_dir))


STANDALONE = Path(__file__).resolve().parent
sys.path.insert(0, str(STANDALONE))

from p3sim import common  # noqa: E402
from p3sim import hospital_assets  # noqa: E402

log = common.Logger("[hospital_main]")

VALID_ROUTES = frozenset((1, 2, 3, 4))


class RouteCommandBridge:
    """Receive manual conveyor outlet commands from a ROS 2 Int32 topic."""

    def __init__(self, topic, log):
        import rclpy
        from std_msgs.msg import Int32

        self._rclpy = rclpy
        self._log = log
        self._routes = []
        self._owns_context = not rclpy.ok()
        if self._owns_context:
            rclpy.init()
        self.node = rclpy.create_node("isaac_hospital_conveyor")
        self.subscription = self.node.create_subscription(Int32, topic, self._receive, 10)
        self._topic = topic
        self._log(f"route control ready topic={topic} type=std_msgs/msg/Int32")

    def _receive(self, message):
        route = int(message.data)
        if route not in VALID_ROUTES:
            self._log(f"route command ignored value={route}; expected 1..4")
            return
        self._routes.append(route)

    def spin_once(self):
        self._rclpy.spin_once(self.node, timeout_sec=0.0)

    def take(self):
        routes, self._routes = self._routes, []
        return routes

    def close(self):
        self.node.destroy_node()
        if self._owns_context and self._rclpy.ok():
            self._rclpy.shutdown()


class PouchCommandBridge:
    """Receive {request_id, order_id, bed_id, outlet} from control as JSON."""

    def __init__(self, topic, log):
        import rclpy
        from std_msgs.msg import String

        self._rclpy, self._log, self._commands = rclpy, log, []
        self._owns_context = not rclpy.ok()
        if self._owns_context:
            rclpy.init()
        self.node = rclpy.create_node("isaac_hospital_pouch_spawner")
        self.subscription = self.node.create_subscription(String, topic, self._receive, 10)
        log(f"pouch control ready topic={topic} type=std_msgs/msg/String")

    def _receive(self, message):
        try:
            command = json.loads(message.data)
            if set(command) != {"request_id", "order_id", "bed_id", "outlet"}:
                raise ValueError("fields must be request_id, order_id, bed_id, outlet")
            if not all(isinstance(command[n], str) and command[n] for n in ("request_id", "order_id", "bed_id")):
                raise ValueError("request_id, order_id, and bed_id must be non-empty strings")
            if type(command["outlet"]) is not int or command["outlet"] not in VALID_ROUTES:
                raise ValueError("outlet must be 1..4")
            self._commands.append(command)
        except (TypeError, ValueError) as exc:
            self._log(f"pouch command ignored reason={exc} data={message.data!r}")

    def spin_once(self):
        self._rclpy.spin_once(self.node, timeout_sec=0.0)

    def take(self):
        commands, self._commands = self._commands, []
        return commands

    def close(self):
        self.node.destroy_node()
        if self._owns_context and self._rclpy.ok():
            self._rclpy.shutdown()


def _command_route(router, parcel, home_position, home_orientation, route):
    import numpy as np

    router.route_to(route)
    parcel.set_world_pose(position=home_position, orientation=home_orientation)
    parcel.set_linear_velocity(np.zeros(3))
    parcel.set_angular_velocity(np.zeros(3))


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--scene", type=Path, help="already prepared/collected hospital USD")
    source.add_argument(
        "--custom-assets",
        type=Path,
        default=DEFAULT_CUSTOM_ASSETS,
        help="extracted custom asset root; overrides the default ZIP",
    )
    source.add_argument(
        "--custom-assets-zip",
        type=Path,
        help="custom asset ZIP (default: sim/outputs/hospital-custom-assets-20260918.zip)",
    )
    parser.add_argument(
        "--isaac-assets-root",
        default=DEFAULT_ISAAC_ASSETS_ROOT,
        help="Assets/Isaac/5.1 root; defaults to the official Isaac 5.1 cloud assets",
    )
    parser.add_argument("--runtime-dir", type=Path, help="default: sim/scenes")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--play", action="store_true")
    parser.add_argument("--physics-dt", type=common.positive_float, default=1.0 / 60.0)
    parser.add_argument("--render-dt", type=common.positive_float, default=1.0 / 60.0)
    parser.add_argument(
        "--sorter-config",
        type=Path,
        default=DEFAULT_SORTER_CONFIG,
        help="JSON with conveyor 2, 4, and 9 Sorter reroute paths",
    )
    parser.add_argument("--route", type=int, choices=(1, 2, 3, 4), help="initial outlet: 1..4")
    parser.add_argument("--route-topic", default=DEFAULT_ROUTE_TOPIC, help="std_msgs/Int32 outlet command topic")
    parser.add_argument(
        "--pouch-template-prim",
        default="/World/PouchTemplate",
        help="single authored pouch template with Body collider and child QR mesh",
    )
    parser.add_argument("--spawned-pouch-root", default="/World/SpawnedPouches")
    parser.add_argument(
        "--qr-output-dir",
        type=Path,
        default=STANDALONE.parent / "outputs" / "qr_beds",
        help="generated bed QR PNG directory",
    )
    parser.add_argument(
        "--pouch-topic",
        default="/isaac/conveyor/pouch_request",
        help="std_msgs/String JSON request topic; template spawn request topic",
    )
    parser.add_argument(
        "--spawn-track-prim",
        default="/World/Conveyor/ConveyorTrack_06",
        help="conveyor prim whose world-bound top is the pouch spawn point",
    )
    parser.add_argument("--spawn-clearance", type=float, default=0.015)
    parser.add_argument("--parcel-prim", default="/World/Cube_01", help="rigid parcel reset on each route command")
    parser.add_argument("--inspect-sorters", action="store_true", help="print matching ActionGraph variables and exit")
    return parser


def parse_args(argv=None):
    args, _unknown = build_parser().parse_known_args(argv)
    if args.scene is None and args.custom_assets is None and args.custom_assets_zip is None:
        args.custom_assets_zip = DEFAULT_CUSTOM_ASSETS_ZIP
    if args.route is not None and args.sorter_config is None:
        build_parser().error("--route requires --sorter-config")
    if args.route_topic is not None and args.sorter_config is None:
        build_parser().error("--route-topic requires --sorter-config")
    return args


def main(argv=None):
    args = parse_args(argv)
    configure_internal_ros()
    with common.step(log, "prepare_scene"):
        scene_path, search_paths = hospital_assets.resolve_scene(
            standalone_dir=STANDALONE,
            scene=args.scene,
            custom_assets=args.custom_assets,
            custom_assets_zip=args.custom_assets_zip,
            isaac_assets_root=args.isaac_assets_root,
            runtime_dir=args.runtime_dir,
        )
        os.environ["PXR_AR_DEFAULT_SEARCH_PATH"] = os.pathsep.join(search_paths)

    # Keep every Isaac/Omni import after SimulationApp construction.
    from isaacsim import SimulationApp

    simulation_app = SimulationApp({"headless": args.headless})
    error_seen = False
    route_bridge = None
    pouch_bridge = None
    try:
        from isaacsim.core.utils.extensions import enable_extension

        for extension in ("isaacsim.asset.gen.conveyor", "isaacsim.ros2.bridge"):
            enable_extension(extension)
        simulation_app.update()

        from p3sim import authored_pouches, hospital_scene, sorter

        with common.step(log, "load_scene"):
            world, stage = hospital_scene.load(
                simulation_app,
                scene_path,
                physics_dt=args.physics_dt,
                rendering_dt=args.render_dt,
            )
        log(f"scene={scene_path}")

        if args.inspect_sorters:
            sorter.print_candidate_attributes(stage, log)
            return 0

        router = None
        if args.sorter_config is not None:
            with common.step(log, "sorter_config"):
                router = sorter.SorterRouter(stage, args.sorter_config, log=log)

        spawner = None
        spawn_position = None
        template_errors = authored_pouches.validate_template(stage, args.pouch_template_prim, args.spawn_track_prim)
        if not template_errors:
            spawner = authored_pouches.TemplateSpawner(stage, args.pouch_template_prim, args.spawned_pouch_root)
            spawn_position = authored_pouches.track_top(stage, args.spawn_track_prim, args.spawn_clearance)
            log(
                f"pouch template={args.pouch_template_prim} track={args.spawn_track_prim} "
                f"spawn_xyz={[float(v) for v in spawn_position]}"
            )
        else:
            raise RuntimeError("; ".join(template_errors))

        if spawner is not None:
            pouch_bridge = PouchCommandBridge(args.pouch_topic, log)
            log("waiting for pouch JSON command")
            while common.keep_running(simulation_app.is_running(), simulation_app.is_exiting(), args.headless):
                pouch_bridge.spin_once()
                for command in pouch_bridge.take():
                    try:
                        world.pause()
                        router.route_to(command["outlet"])
                        path = spawner.spawn(command["order_id"], command["bed_id"], spawn_position, args.qr_output_dir)
                        for _ in range(2):
                            simulation_app.update()
                        world.play()
                    except (RuntimeError, ValueError) as exc:
                        log(f"pouch command rejected request_id={command['request_id']} reason={exc}")
                        continue
                    log(
                        f"pouch spawned path={path} request_id={command['request_id']} "
                        f"order_id={command['order_id']} bed_id={command['bed_id']} "
                        f"outlet={command['outlet']}"
                    )
                if world.is_playing():
                    world.step(render=not args.headless)
                else:
                    simulation_app.update()
        elif args.route_topic is None:
            if args.route is not None:
                router.route_to(args.route)
            hospital_scene.run(simulation_app, world, start_playing=args.play, headless=args.headless, log=log)
        else:
            from isaacsim.core.prims import SingleRigidPrim

            if not stage.GetPrimAtPath(args.parcel_prim).IsValid():
                raise RuntimeError(f"parcel prim not found: {args.parcel_prim}")
            parcel = world.scene.add(
                SingleRigidPrim(
                    prim_path=args.parcel_prim,
                    name="hospital_conveyor_parcel",
                    reset_xform_properties=False,
                )
            )
            world.reset()
            home_position, home_orientation = parcel.get_world_pose()
            home_position = home_position.copy()
            home_orientation = home_orientation.copy()
            world.pause()

            route_bridge = RouteCommandBridge(args.route_topic, log)
            log(f"parcel home prim={args.parcel_prim} xyz={list(map(float, home_position))}")
            log("waiting for route command 1..4")
            if args.route is not None:
                _command_route(router, parcel, home_position, home_orientation, args.route)
                world.play()

            while common.keep_running(simulation_app.is_running(), simulation_app.is_exiting(), args.headless):
                route_bridge.spin_once()
                for route in route_bridge.take():
                    _command_route(router, parcel, home_position, home_orientation, route)
                    if not world.is_playing():
                        world.play()
                    log(f"route command applied outlet={route} parcel_reset={args.parcel_prim}")
                if world.is_playing():
                    world.step(render=not args.headless)
                else:
                    simulation_app.update()
    except Exception as exc:
        error_seen = True
        log(f"ERROR {type(exc).__name__}: {exc}")
    finally:
        if pouch_bridge is not None:
            pouch_bridge.close()
        if route_bridge is not None:
            route_bridge.close()
        simulation_app.close()
    return common.exit_code_for(error_seen)


if __name__ == "__main__":
    sys.exit(main())
