"""Stage 0 skeleton: empty world (ground plane only) that publishes /clock from Isaac Sim 5.1.

Run in an Isaac shell (see sim/README.md for the environment):
    ~/isaacsim/python.sh sim/standalone/minimal_clock.py --headless

Scope: one writer of /clock (rosgraph_msgs/Clock), RELIABLE, sim time, monotonic across Stop/Play.
No robot, sensor, conveyor, hospital scene, /sim/reset or Dispense. Stop with SIGINT only.

Importing this module does not start Isaac: every Isaac/omni/pxr import lives inside run().
Sources checked 2026-09-17 against the NVIDIA IsaacSim repository tag v5.1.0:
- source/standalone_examples/api/isaacsim.ros2.bridge/clock.py (graph shape, SimulationContext use)
- source/extensions/isaacsim.ros2.bridge/nodes/OgnROS2PublishClock.{ogn,cpp} and include/.../Ros2QoS.h
- source/extensions/isaacsim.core.nodes/nodes/OgnIsaacReadSimulationTime.{ogn,cpp}
- source/extensions/isaacsim.simulation_app/isaacsim/simulation_app/simulation_app.py (SIGINT handler)
"""

import argparse
import os
import signal
import sys
import threading
import time

LOG_PREFIX = "[minimal_clock]"

# Bridge extension named by the 5.1 ROS install page and present in master02 ~/isaacsim/exts (observed 2026-09-17).
ROS2_BRIDGE_EXTENSION = "isaacsim.ros2.bridge"

# OmniGraph node type ids as used by the 5.1.0 clock.py sample.
# 마클 확인 필요: grep -rl 'ROS2PublishClock\|IsaacReadSimulationTime\|OnPlaybackTick' \
#   ~/isaacsim/exts/isaacsim.ros2.bridge ~/isaacsim/exts/isaacsim.core.nodes ~/isaacsim/extscache | head
NODE_ON_PLAYBACK_TICK = "omni.graph.action.OnPlaybackTick"
NODE_READ_SIM_TIME = "isaacsim.core.nodes.IsaacReadSimulationTime"
NODE_PUBLISH_CLOCK = "isaacsim.ros2.bridge.ROS2PublishClock"

GRAPH_PATH = "/P3ClockGraph"
GROUND_PLANE_PATH = "/World/GroundPlane"

# Contract v1 2.1: /clock is written by isaac alone. 5.1.0 Ros2Node.h addTopicPrefix() returns namespace + "/" + name;
# the graph prim carries no isaac:namespace and nodeNamespace stays empty, so "clock" becomes /clock.
CLOCK_TOPIC = "clock"

# Contract v1 2 "R" = reliable, volatile, depth 10. OgnROS2PublishClock.cpp: an empty qosProfile keeps the
# Ros2QoSProfile() defaults (rmw_qos_profile_default: keep last, reliable, volatile) with depth = queueSize.
CLOCK_QOS_PROFILE = ""
CLOCK_QUEUE_SIZE = 10

# Contract v1 4: sim time must not rewind on Stop/Play. OgnIsaacReadSimulationTime.ogn: resetOnStop default False,
# "If True the simulation time will reset when stop is pressed"; the .cpp reads getSimulationTimeMonotonic() when
# False. The C++ state member defaults to true, so the input is set explicitly rather than trusting the default.
READ_SIM_TIME_RESET_ON_STOP = False

DEFAULT_RATE_HZ = 60.0


def positive_float(text):
    value = float(text)
    if not value > 0.0:
        raise argparse.ArgumentTypeError(f"must be > 0, got {text}")
    return value


def non_negative_float(text):
    value = float(text)
    if not value >= 0.0:
        raise argparse.ArgumentTypeError(f"must be >= 0, got {text}")
    return value


def build_parser():
    parser = argparse.ArgumentParser(description="Isaac Sim 5.1 empty world that publishes /clock (stage 0).")
    parser.add_argument("--headless", action="store_true", help="run without a window")
    parser.add_argument(
        "--rate", type=positive_float, default=DEFAULT_RATE_HZ,
        help="target app updates per wall second; /clock is published once per update (default 60)",
    )
    parser.add_argument(
        "--duration", type=non_negative_float, default=0.0,
        help="wall seconds to run before closing; 0 runs until SIGINT (default 0)",
    )
    parser.add_argument(
        "--physics-dt", type=positive_float, default=None,
        help="physics step in sim seconds; omitted keeps the Isaac default (logged at start)",
    )
    parser.add_argument(
        "--render-dt", type=positive_float, default=None,
        help="sim seconds per app update; omitted keeps the Isaac default (logged at start)",
    )
    parser.add_argument(
        "--stop-play-after", type=non_negative_float, default=0.0,
        help="wall seconds after start to do one timeline Stop then Play, to observe that /clock does not "
             "rewind; 0 disables (default 0)",
    )
    return parser


def parse_args(argv=None):
    # Kit may append its own arguments; ignore unknown ones instead of failing inside python.sh.
    args, _unknown = build_parser().parse_known_args(argv)
    return args


def environment_summary(env):
    """Return the ROS-related environment as key=value pairs, for the start log."""
    library_path = env.get("LD_LIBRARY_PATH", "")
    entries = [entry for entry in library_path.split(os.pathsep) if entry]
    return {
        "RMW_IMPLEMENTATION": env.get("RMW_IMPLEMENTATION", "<unset>"),
        "ROS_DOMAIN_ID": env.get("ROS_DOMAIN_ID", "<unset>"),
        "ROS_DISTRO": env.get("ROS_DISTRO", "<unset>"),
        # Wired whitelist profile. Whether Isaac's internal Fast DDS reads it is checked on master02, not assumed.
        "FASTRTPS_DEFAULT_PROFILES_FILE": env.get("FASTRTPS_DEFAULT_PROFILES_FILE", "<unset>"),
        # Which ROS libraries the bridge can load: Isaac's internal Jazzy or a sourced system install.
        "ld_internal_jazzy": any(f"{ROS2_BRIDGE_EXTENSION}/jazzy/lib" in entry for entry in entries),
        "ld_opt_ros": any(entry.startswith("/opt/ros/") for entry in entries),
    }


def format_start_line(isaac_version, env_summary, physics_dt, render_dt, rate_hz):
    fields = [f"isaac={isaac_version}"]
    fields += [f"{key}={value}" for key, value in env_summary.items()]
    fields += [
        f"physics_dt={physics_dt}",
        f"render_dt={render_dt}",
        f"rate_hz={rate_hz}",
        f"expected_rtf={render_dt * rate_hz:.3f}",
        f"topic=/{CLOCK_TOPIC}",
        "qos=reliable/volatile/keep_last",
        f"depth={CLOCK_QUEUE_SIZE}",
        f"reset_on_stop={READ_SIM_TIME_RESET_ON_STOP}",
    ]
    return f"{LOG_PREFIX} start " + " ".join(fields)


def keep_running(app_running, app_exiting, headless):
    """Whether the main loop should continue, given SimulationApp.is_running() and is_exiting().

    5.1.0 simulation_app.py: is_running() is `app.is_running() and not is_exiting() and stage is not None`.
    The class example 7_pick_place_color.py (M0609 asset, read on dev01, not run by us) notes that headless
    is_running() can be False right away and loops on `is_running() or args.headless`. We do the same for
    headless but still stop once close/exit has begun, so a real shutdown is not spun forever.
    NVIDIA's own 5.1.0 standalone_examples/api/isaacsim.simulation_app/livestream.py (headless) likewise loops on
    `kit._app.is_running() and not kit.is_exiting()`, without the stage check.
    """
    if app_running:
        return True
    return headless and not app_exiting


def install_sigint_handler(stop_event):
    """Replace SimulationApp's SIGINT handler with a flag.

    SimulationApp.__init__ (5.1.0) installs a handler that shuts Kit down and calls sys.exit(0) without
    close(). The main loop instead sees the flag, leaves, and calls simulation_app.close() itself.
    """

    def handle(_signum, _frame):
        stop_event.set()

    return signal.signal(signal.SIGINT, handle)


def isaac_version_string():
    from isaacsim.core.version import get_version

    version = get_version()  # (core, prerelease tag and build, major, minor, patch, pretag, prebuild, buildtag)
    if not version[0]:
        return "<unknown>"
    return f"{version[0]}-{version[1]}" if version[1] else version[0]


def build_clock_graph():
    import omni.graph.core as og

    keys = og.Controller.Keys
    og.Controller.edit(
        {"graph_path": GRAPH_PATH, "evaluator_name": "execution"},
        {
            keys.CREATE_NODES: [
                ("OnPlaybackTick", NODE_ON_PLAYBACK_TICK),
                ("ReadSimTime", NODE_READ_SIM_TIME),
                ("PublishClock", NODE_PUBLISH_CLOCK),
            ],
            keys.CONNECT: [
                ("OnPlaybackTick.outputs:tick", "PublishClock.inputs:execIn"),
                ("ReadSimTime.outputs:simulationTime", "PublishClock.inputs:timeStamp"),
            ],
            keys.SET_VALUES: [
                ("ReadSimTime.inputs:resetOnStop", READ_SIM_TIME_RESET_ON_STOP),
                ("PublishClock.inputs:topicName", CLOCK_TOPIC),
                ("PublishClock.inputs:qosProfile", CLOCK_QOS_PROFILE),
                ("PublishClock.inputs:queueSize", CLOCK_QUEUE_SIZE),
            ],
        },
    )


def read_graph_sim_time():
    import omni.graph.core as og

    return og.Controller.get(og.Controller.attribute(f"{GRAPH_PATH}/ReadSimTime.outputs:simulationTime"))


def run(args):
    from isaacsim import SimulationApp

    simulation_app = SimulationApp({"headless": args.headless})
    stop_event = threading.Event()
    install_sigint_handler(stop_event)
    exit_code = 0
    try:
        import omni.kit.app
        from isaacsim.core.utils.extensions import enable_extension

        enable_extension(ROS2_BRIDGE_EXTENSION)
        simulation_app.update()
        if not omni.kit.app.get_app().get_extension_manager().is_extension_enabled(ROS2_BRIDGE_EXTENSION):
            raise RuntimeError(f"{ROS2_BRIDGE_EXTENSION} did not stay enabled; see the bridge startup log above")

        build_clock_graph()
        simulation_app.update()

        from isaacsim.core.api import SimulationContext
        from isaacsim.core.api.objects import GroundPlane

        simulation_context = SimulationContext(
            physics_dt=args.physics_dt, rendering_dt=args.render_dt, stage_units_in_meters=1.0
        )
        GroundPlane(prim_path=GROUND_PLANE_PATH)  # PhysicsSchemaTools plane; no asset download.
        simulation_context.initialize_physics()

        render_dt = simulation_context.get_rendering_dt()
        print(
            format_start_line(
                isaac_version_string(), environment_summary(os.environ),
                simulation_context.get_physics_dt(), render_dt, args.rate,
            ),
            flush=True,
        )

        simulation_context.play()
        period = 1.0 / args.rate
        started = time.monotonic()
        sim_started = read_graph_sim_time()
        next_tick = started
        updates = 0
        stop_play_done = args.stop_play_after == 0.0
        while not stop_event.is_set() and keep_running(
            simulation_app.is_running(), simulation_app.is_exiting(), args.headless
        ):
            now = time.monotonic()
            if args.duration and now - started >= args.duration:
                break
            if not stop_play_done and now - started >= args.stop_play_after:
                before = read_graph_sim_time()
                simulation_context.stop()
                simulation_app.update()
                simulation_context.play()
                simulation_app.update()
                print(
                    f"{LOG_PREFIX} stop_play sim_time_before={before:.6f} sim_time_after={read_graph_sim_time():.6f}",
                    flush=True,
                )
                stop_play_done = True
            simulation_app.update()
            updates += 1
            next_tick += period
            delay = next_tick - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            else:
                next_tick = time.monotonic()  # Behind schedule: do not burst to catch up.

        if not stop_event.is_set() and not (args.duration and time.monotonic() - started >= args.duration):
            # 9/17 master02 GUI run ended with app_stopped after 9.7 s; record which term of is_running() was false.
            try:
                print(f"{LOG_PREFIX} app_state kit_running={simulation_app._app.is_running()} "
                      f"exiting={simulation_app.is_exiting()} "
                      f"stage_missing={simulation_app.context.get_stage() is None}", flush=True)
            except Exception as exc:  # diagnostics only
                print(f"{LOG_PREFIX} app_state unavailable {type(exc).__name__}: {exc}", flush=True)
        elapsed = time.monotonic() - started
        sim_elapsed = read_graph_sim_time() - sim_started
        reason = "sigint" if stop_event.is_set() else ("duration" if simulation_app.is_running() else "app_stopped")
        print(
            f"{LOG_PREFIX} stop reason={reason} updates={updates} wall_s={elapsed:.3f} "
            f"loop_hz={updates / elapsed if elapsed > 0 else 0.0:.2f} sim_s={sim_elapsed:.3f} "
            f"rtf={sim_elapsed / elapsed if elapsed > 0 else 0.0:.3f} sim_time={read_graph_sim_time():.6f}",
            flush=True,
        )
    except Exception as exc:  # Report, then still close the app below.
        print(f"{LOG_PREFIX} error {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        exit_code = 1
    finally:
        simulation_app.close()
    return exit_code


def main(argv=None):
    return run(parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
