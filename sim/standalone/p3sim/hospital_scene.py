"""Isaac-side hospital stage loader and application loop."""

from pathlib import Path

from . import common


def load(simulation_app, scene_path, *, physics_dt, rendering_dt):
    """Open the prepared USD and return (World, Stage)."""
    import omni.usd
    from isaacsim.core.api import World
    from isaacsim.core.utils.stage import open_stage

    scene_path = Path(scene_path).expanduser().resolve()
    if not open_stage(usd_path=str(scene_path)):
        raise RuntimeError(f"Isaac Sim failed to open stage: {scene_path}")
    context = omni.usd.get_context()
    while context.get_stage_loading_status()[2] > 0 and simulation_app.is_running():
        simulation_app.update()
    for _ in range(10):
        simulation_app.update()
    stage = context.get_stage()
    if stage is None:
        raise RuntimeError("USD context returned no stage")
    world = World(stage_units_in_meters=1.0, physics_dt=physics_dt,
                  rendering_dt=rendering_dt)
    return world, stage


def run(simulation_app, world, *, start_playing, headless, log):
    """Keep Kit alive; step physics only while the timeline is playing."""
    if start_playing:
        world.reset()
        log("physics started")
    else:
        log("scene loaded; press Play when ready")

    was_playing = world.is_playing()
    step_count = 0
    while common.keep_running(simulation_app.is_running(),
                              simulation_app.is_exiting(), headless):
        is_playing = world.is_playing()
        if is_playing and not was_playing:
            step_count = 0
            log("Play detected: step_count reset")
        if is_playing:
            world.step(render=not headless)
            step_count += 1
        else:
            simulation_app.update()
        was_playing = is_playing
