"""계약 3절의 구역 프레임 프림과, **장면 단독 회차용** 진단 TF 발행. Isaac 임포트는 늦게 한다.

**구역 TF 의 단일 작성자는 스테이지가 아니다.** 계약 v1 59줄·436–442줄: `pharmacy/*`·`<zone>/cabinet`·
`<zone>/tag` 를 `/tf_static` 으로 내는 것은 주행 launch 의 `zones_tf` 하나이고 부모는 `map` 이다.
한 부모→자식 변환의 작성자가 둘이면 계약 위반이다(3절).

그래서 여기 `publish` 는 **기본으로 돌지 않는다**(`--zones-tf` 로만 켠다). 켜는 곳은 ROS 스택 없이 장면만
띄우는 회차다 — 그때는 `zones_tf` 가 없어 구역 프레임을 눈으로 볼 방법이 없다.

이름은 계약 표기 그대로 `bed_a1/cabinet`(슬래시)로 나간다. 프림 이름에는 `/` 를 못 쓰지만
**`isaac:nameOverride` 속성이 프레임 이름을 정한다** — `ur5_cell.add_camera_and_tf` 가 `amr_1/base_link`
같은 이름을 이미 그렇게 낸다. (9/21 에 내가 "이름을 바꿀 입력이 없다" 고 잘못 보고했다. 정정한다.)
→ 그래도 한 바퀴 조합에서는 **끈다.** 작성자가 둘이 되는 것은 이름과 무관한 문제다.

값의 단일 출처는 layout.full_loop_zones 이고 같은 값이 zones.emptyworld.yaml 로도 나간다 — 둘이 어긋나면 L1 이 잡는다.
프림 자체는 언제나 만든다(장면 배치의 근거이고 TF 와 무관하다).
"""

import math

#: tf_static 으로 낼 때의 부모 프레임. 계약 3절이 `map` 이다. 프림 이름이 곧 프레임 이름이라
#: 그 이름의 프림을 만들어 부모로 쓴다(빈월드에서 map 원점 = Isaac world 원점).
PARENT_FRAME = "map"
#: 프레임 이름에서 zone 의 하위 자세를 구분하는 글자. `bed_a1/cabinet` -> `bed_a1_cabinet`.
SEPARATOR = "_"


def prim_name(zone_name):
    """`bed_a1/cabinet` -> `bed_a1_cabinet`. **프림 이름**이다 — 프림 경로에는 `/` 를 못 쓴다.

    TF 프레임 이름은 이것이 아니라 `isaac:nameOverride` 가 정한다(`frame_name` 참고).
    """
    return zone_name.replace("/", SEPARATOR)


def frame_name(zone_name):
    """TF 프레임 이름. 계약 표기 그대로다 — `bed_a1/cabinet`(슬래시)."""
    return zone_name


def yaw_quat(yaw):
    """z 축 yaw(rad) -> (w, x, y, z). 반시계가 양수다(계약 3절)."""
    half = yaw / 2.0
    return (math.cos(half), 0.0, 0.0, math.sin(half))


def zone_prims(zones):
    """[(프림 이름, 프레임 이름, (x, y, z), (w, x, y, z))] — 프림으로 만들 자리와 자세."""
    out = []
    for name in sorted(zones):
        x, y, z, yaw = zones[name]
        out.append((prim_name(name), frame_name(name), (float(x), float(y), float(z)), yaw_quat(float(yaw))))
    return out


def build(stage, root, zones, log=print):
    """구역마다 빈 Xform 을 두고 그 경로를 돌려준다. 프림 이름이 곧 TF 프레임 이름이다.

    Isaac 5.1 의 ROS2PublishTransformTree 는 prim 이름으로 프레임을 짓는다(sensors.py 의 주석과 같다).
    """
    from pxr import Gf, Sdf, UsdGeom

    paths, frames = [], []
    for name, frame, xyz, quat in zone_prims(zones):
        path = f"{root}/{name}"
        xform = UsdGeom.Xform.Define(stage, path)
        api = UsdGeom.XformCommonAPI(xform)
        api.SetTranslate(Gf.Vec3d(*xyz))
        api.SetRotate(Gf.Vec3f(0.0, 0.0, math.degrees(2.0 * math.atan2(quat[3], quat[0]))))
        # 프레임 이름은 프림 이름이 아니라 이 속성이 정한다 — 그래서 계약의 슬래시 표기를 그대로 낼 수 있다.
        xform.GetPrim().CreateAttribute("isaac:nameOverride", Sdf.ValueTypeNames.String).Set(frame)
        paths.append(path)
        frames.append(frame)
    log(f"zones built count={len(paths)} parent={PARENT_FRAME} frames={frames}")
    return paths


def parent_prim(stage, root):
    """부모로 쓸 `map` 이름의 프림 경로. 없으면 만든다(월드 원점, 항등).

    프림 이름이 곧 TF 프레임 이름이라 부모 프레임을 `map` 으로 내려면 그 이름의 프림이 있어야 한다.
    전에는 스테이지 루트(`P3Pharmacy`)를 그대로 부모로 줘서 `frame_id` 가 `P3Pharmacy` 로 나갔다
    (실습23a 에서 드러났다) — TF 트리에 없는 이름이다.
    """
    from pxr import UsdGeom

    path = f"{root}/{PARENT_FRAME}"
    UsdGeom.Xform.Define(stage, path)
    return path


def publish(stage, graph_path, parent_path, zone_paths, log=print):
    """zone 프림을 tf_static 으로 낸다. **진단용이고 기본으로 돌지 않는다** — 모듈 문서를 보라."""
    import usdrt
    from isaacsim.core.utils import extensions  # noqa: F401  (그래프 확장을 끌어온다)
    from omni.isaac.core.utils.prims import is_prim_path_valid  # noqa: F401
    import omni.graph.core as og

    keys = og.Controller.Keys
    og.Controller.edit(
        {"graph_path": graph_path, "evaluator_name": "execution"},
        {
            keys.CREATE_NODES: [
                ("OnTick", "omni.graph.action.OnPlaybackTick"),
                ("SimTime", "isaacsim.core.nodes.IsaacReadSimulationTime"),
                ("TfZones", "isaacsim.ros2.bridge.ROS2PublishTransformTree"),
            ],
            keys.CONNECT: [
                ("OnTick.outputs:tick", "TfZones.inputs:execIn"),
                ("SimTime.outputs:simulationTime", "TfZones.inputs:timeStamp"),
            ],
            keys.SET_VALUES: [
                ("SimTime.inputs:resetOnStop", False),
                ("TfZones.inputs:parentPrim", [usdrt.Sdf.Path(parent_path)]),
                ("TfZones.inputs:targetPrims", [usdrt.Sdf.Path(path) for path in zone_paths]),
                ("TfZones.inputs:topicName", "tf_static"),
                ("TfZones.inputs:staticPublisher", True),
            ],
        },
    )
    log(f"zones tf_static parent={parent_path} parent_frame={parent_path.rsplit('/', 1)[-1]} "
        f"count={len(zone_paths)} topic=tf_static DIAGNOSTIC: 계약 단일 작성자는 주행의 zones_tf 다. "
        f"이름은 계약 표기(bed_a1/cabinet) 그대로지만, 그래서 더더욱 한 바퀴 조합에서는 끈다")
