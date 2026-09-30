"""Stage-load smoke check for Isaac Sim 5.1; not a physics or system test.

Run in a fresh Isaac Python process:
    P3_SCENE_PATH=/absolute/path/to/installed/scene.usd ./python.sh <repo>/sim/tests/test_stage_loads.py

This checks stage opening, pending file loads, traversable prims and application
liveness across a bounded number of app updates. It does not play the timeline,
measure physics time, validate every referenced asset, or exercise ROS/scenarios.
"""

import os
from pathlib import Path

APP_UPDATES = 120  # Application updates; neither physics steps nor a duration.


def scene_path() -> Path:
    """Prefer an explicit installed scene; retain existing AMENT-prefix lookup."""
    explicit = os.environ.get("P3_SCENE_PATH")
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_absolute():
            raise ValueError("P3_SCENE_PATH must be an absolute path")
        return path.resolve()

    for prefix in os.environ.get("AMENT_PREFIX_PATH", "").split(os.pathsep):
        if not prefix:
            continue
        candidate = (
            Path(prefix)
            / "share"
            / "rokey_p3_description"
            / "stages"
            / "my_first_scene.usd"
        )
        if candidate.is_file():
            return candidate.resolve()
    raise RuntimeError(
        "Set P3_SCENE_PATH to the installed scene's absolute path. "
        "Use a separate ROS build shell to find it; do not source native ROS "
        "into the Isaac Sim 5.1 Python environment just to locate an asset."
    )


def run_stage_smoke() -> None:
    stage_path = scene_path()
    if not stage_path.is_file():
        raise FileNotFoundError(f"Scene does not exist: {stage_path}")

    # Initialize Kit before importing omni/pxr/isaacsim submodules.
    from isaacsim import SimulationApp

    simulation_app = SimulationApp({"headless": True, "fast_shutdown": False})
    try:
        import omni.usd
        from isaacsim.core.utils.stage import is_stage_loading, open_stage

        # The synchronous 5.1 helper returns bool; async APIs have other results.
        if not open_stage(str(stage_path)):
            raise RuntimeError(f"Failed to open scene: {stage_path}")

        for update_index in range(APP_UPDATES):
            if not simulation_app.is_running():
                raise RuntimeError(f"Application stopped before update {update_index}")
            simulation_app.update()

        if not simulation_app.is_running():
            raise RuntimeError(f"Application stopped after {APP_UPDATES} updates")
        if is_stage_loading():
            raise RuntimeError(f"Files still loading after {APP_UPDATES} app updates")

        stage = omni.usd.get_context().get_stage()
        if stage is None:
            raise RuntimeError("No stage is attached")
        if not any(stage.Traverse()):
            raise RuntimeError("No traversable prims in the stage")
    finally:
        simulation_app.close()

    print(
        f"PASS (stage smoke only): {stage_path}; {APP_UPDATES} app updates; "
        "no pending file loads at final check. Physics/ROS/scenario NOT tested."
    )


if __name__ == "__main__":
    run_stage_smoke()
