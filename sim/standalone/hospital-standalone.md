# Hospital Standalone overlay

> **상태: 지난 기록 (2026-09-19 기준).** 지금 병원 한 바퀴는 [sim README 현행 절](../README.md#지금-무엇이-현행인가-v110-병원-한-바퀴)을 따른다.
> 이 문서는 `hospital_main.py`(병원 씬 단독 실행·컨베이어 분기 제어, #233) 경로다. v1.1.0 한 바퀴(`pharmacy_stage.py --preset hospital`)는 이 스크립트를 쓰지 않는다.

These files are part of the repository (merged in #233). They reuse
`p3sim/common.py`, `prepare_hospital_scene.py`, and `sim/scenes/hospital_layout.usda`.
`i_py` below is a site shell alias that is not defined in this repository.
`~/isaacsim/python.sh` also works: `hospital_main.py` re-executes itself with
Isaac's bundled Jazzy libraries (`configure_internal_ros`).

## Inspect sorter variables

```bash
~/isaacsim/python.sh sim/standalone/hospital_main.py \
  --scene /path/to/collected/hospital.usd \
  --inspect-sorters
```

Copy `conveyor_config.example.json` to `conveyor_config.json` and replace the
paths with the printed node-input paths.

Conveyor 7 does not use a graph variable for its branch. Its actual node input
is `/World/Conveyor/ConveyorTrack_07/ConveyorBeltGraph/ConveyorNode.inputs:direction`:

- left: `[-1, 0, 0]`
- right: `[1, 0, 0]`

Junctions 2 and 3 use the Constant Bool node named `reroute` inside each Sorter
ActionGraph. Their attributes are:

- `/World/Conveyor/ConveyorTrack_02/Sorter/ActionGraph/reroute.inputs:value`
- `/World/Conveyor/ConveyorTrack_03/Sorter/ActionGraph/reroute.inputs:value`

The direction is selected by setting that Boolean to `True` or `False`.

## Direct collected-scene run

```bash
~/isaacsim/python.sh sim/standalone/hospital_main.py \
  --scene /path/to/collected/hospital.usd \
  --sorter-config sim/standalone/conveyor_config.json \
  --route 3 --play
```

## Repository template run

Download the project custom-asset archive to the ignored local path below. Do
not extract or commit it:

```text
sim/outputs/hospital-custom-assets-20260918.zip
```

Then start the scene without host-specific asset arguments:

```bash
i_py sim/standalone/hospital_main.py
```

The launcher extracts that ZIP under ignored `sim/outputs/hospital_runtime/`,
generates ignored `sim/scenes/hospital_runtime.usda`, and resolves NVIDIA Isaac
assets from the official Isaac Sim 5.1 cloud root. Kit downloads and caches
those base assets automatically on first use.

Routes are fixed as follows:

- 1: junction 7 left, junction 3 left
- 2: junction 7 left, junction 3 down
- 3: junction 7 right, junction 2 down
- 4: junction 7 right, junction 2 right

## Conveyor route test

Run all four routes in the Isaac Sim GUI. The script verifies the written USD
attributes automatically, then keeps each route active for 8 seconds so one
parcel can be observed physically:

```bash
~/isaacsim/python.sh sim/standalone/test_conveyor_routes.py \
  --routes 1 2 3 4 --hold-seconds 8
```

Test one route for longer:

```bash
~/isaacsim/python.sh sim/standalone/test_conveyor_routes.py \
  --routes 3 --hold-seconds 20
```

`RESULT: PASS (attribute readback)` means the graph inputs retained the command.
The final physical outlet must still be checked in the viewport because the
script cannot infer whether the Sorter Constant Bool's `True` and `False`
directions are physically reversed. If route 1/2 or 3/4 is swapped, reverse the
corresponding Boolean values in `conveyor_config.example.json`.


## Persistent route control

Keep the hospital scene running in terminal 1 and accept repeated outlet commands
on `/isaac/conveyor/route` as `std_msgs/msg/Int32`. The scene waits paused for
the first command. Every accepted command selects the sorter route, restores
`/World/Cube_01` to its startup world pose, clears both velocities, and starts
or resumes physics.

Terminal 1 (the conveyor and ROS extensions are enabled automatically):

```bash
i_py sim/standalone/hospital_main.py
```

The sorter config, parcel prim, route topic, custom ZIP location, and NVIDIA
Isaac 5.1 cloud root have repository defaults. Each computer only needs the
project ZIP at `sim/outputs/hospital-custom-assets-20260918.zip`.

For an offline PC with the Isaac Sim Complete Assets Pack, override only the
Isaac root. An already-extracted custom ZIP can also be selected explicitly:

```bash
export P3_HOSPITAL_ISAAC_ASSETS_ROOT=/path/to/Assets/Isaac/5.1
export P3_HOSPITAL_CUSTOM_ASSETS=/path/to/unpacked/hospital-custom-assets
i_py sim/standalone/hospital_main.py
```

`P3_HOSPITAL_ISAAC_ASSETS_ROOT` may also point to a reachable Nucleus asset
root. `--custom-assets-zip`, `--isaac-assets-root`,
`P3_HOSPITAL_SORTER_CONFIG`, and `P3_HOSPITAL_ROUTE_TOPIC` remain optional
overrides. `--scene` is only for opening an already prepared USD and is not
part of the normal startup command.

Terminal 2 must use the same `ROS_DOMAIN_ID` as terminal 1:

```bash
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=0
ros2 topic pub --once /isaac/conveyor/route std_msgs/msg/Int32 "{data: 1}"
```

Replace `1` with `2`, `3`, or `4` for another outlet. A later command
interrupts the current trip by resetting the same parcel and starting the new
route.

## Scene ownership

`hospital_layout.usda` keeps the conveyors authored by the hospital map. The
standalone controller only writes the existing sorter graph inputs; it does not
create a replacement belt network. The scene template does not contain an
M0617 prim or a ROS `/clock` graph. `/clock`, when needed by a larger stage, is
owned by that stage so the scene cannot create a second clock publisher.
