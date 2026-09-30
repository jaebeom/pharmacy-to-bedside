"""이동 베이스(AMR)의 dummy 3축과 주행 규격 계산. Isaac 임포트는 늦게 한다.

K2 (작전 9/21, 재범 결정 (나)): `base_driver` 는 그대로 두고 Isaac 이 `/amr_1/base/joint_command` 를 받는다.
자산 `ridgeback_ur5.usd` 는 저장소에 없어 그래프를 고칠 수 없다 — 그래서 스테이지가 dummy 3축을 직접 만들고
속도 드라이브를 건다. 레일(scene.py 의 rail_x·rail_y)과 같은 방식이라 확실하다.

축 규약은 주행이 준 `base_driver` 규격 그대로다(9/21, main 914d23d 의 base_driver_node·base_kinematics 기준):

- 이름 셋이 **반드시** 이것: dummy_base_prismatic_x_joint, dummy_base_prismatic_y_joint, dummy_base_revolute_z_joint.
- position 은 **world 축 기준**이다. x·y 는 m, yaw 는 rad 이고 base_driver 가 odom 자세로 **그대로** 쓴다.
  그래서 x·y 는 world 축과 평행하고 revolute z 는 반시계가 양수다. yaw 는 [-pi, pi) 로 접는다.
- velocity 는 같은 순서·같은 축의 m/s·rad/s 다. **0 으로 채워 보내면 안 된다** — base/stopped 가 항상 참이 되어
  팔 인터록이 무너진다. 값이 없으면 비운다(주행이 position·stamp 로 만든다).

**odom 과 TF 는 내지 않는다.** `odom -> amr_1/base_link` 의 작성자는 base_driver 하나다(계약 3절).
"""

import math

#: 주행이 이름으로 골라 쓴다. 순서도 이대로다(position·velocity 가 같은 순서여야 한다).
JOINT_NAMES = ("dummy_base_prismatic_x_joint",
               "dummy_base_prismatic_y_joint",
               "dummy_base_revolute_z_joint")
#: 속도 드라이브(stiffness 0, damping 큼): 목표 속도를 따라가고 위치는 붙잡지 않는다. 우리 선택이고 실측 아님.
DEFAULT_DRIVE = (0.0, 1.0e6, 1.0e7)  # stiffness, damping, max force
#: 빈월드 v0 의 이동 범위(m). 복도 길이 + 병실 깊이에서 왔고 임시값이다. 가장 먼 접근 자리를 덮어야 한다
#: (layout.WARD 의 마지막 자리). 좁으면 그 침상까지 못 간다 — sim/tests 가 관계로 잡는다.
DEFAULT_LIMITS = ((-2.0, 17.0), (-4.0, 4.0))
#: 명령 주기 권장값(Hz, 계약 2.1). joint_states 도 같은 주기로 낸다.
COMMAND_HZ = 20.0
#: 합본 자산의 UR5 6관절 이름. **계약 97줄 "USD 조인트 이름 그대로"** 라 번역하지 않는다 —
#: 번역하면 실물로 갈 때 또 번역해야 한다. 받침대 UR5(`ur5_cell.UR5_JOINTS`)는 접두가 없다.
#: 탐침(맥마클2 9/21)에서 읽은 런타임 DOF 이름이고 #408 의 USD 읽기와 같다.
ARM_JOINT_NAMES = ("ur_arm_shoulder_pan_joint", "ur_arm_shoulder_lift_joint", "ur_arm_elbow_joint",
                   "ur_arm_wrist_1_joint", "ur_arm_wrist_2_joint", "ur_arm_wrist_3_joint")
#: 합본에는 `tool0`·flange 프림이 **없다**(탐침 4번). 흡착 TCP 는 이 링크 기준으로 잡는다.
TCP_PARENT_LINK = "ur_arm_wrist_3_link"
#: `wrist_3_link` → 팔 기구학의 끝점(`tool0`) 고정 변환. **항등이다 — 재서 확인했다.**
#:
#: 표준 URDF 라면 둘이 `d6 = 0.0823` 만큼 떨어져 있고 회전도 있어야 한다(비전의 예상이 그랬다).
#: 그런데 탐침 3 의 자세 **세 벌**로 역산하니 평행이동 0·회전 항등이었고, 세 벌이 서로 0.6 mm·0.015° 안에서
#: 같았다(한 벌이면 우연일 수 있어 세 벌을 받았다). 자산이 `wrist_3_link` 를 DH 끝점에 맞춰 정의해 둔 것이다.
#: **추측했으면 8.2 cm 를 틀렸다.**
#: 이것은 **이 자산·이 탐침의 값**이다. 자산이 바뀌면 다시 재야 한다.
TCP_LOCAL_OFFSET = (0.0, 0.0, 0.0)
#: UR5 DH 의 `d1`. 팔 밑동 판에서 어깨까지의 높이다(`ur5_kinematics` 와 같은 값이어야 한다).
UR5_D1 = 0.089159
#: 팔 밑동 프레임 이름(네임스페이스 뒤). 결정 47. **자산에 이 이름의 링크가 없을 수 있어** 우리가 만든다.
ARM_BASE_FRAME = "ur_arm_base_link"
#: 어깨 링크 — 밑동 프레임의 자리를 여기서 잰다.
SHOULDER_LINK = "ur_arm_shoulder_link"
#: 밑동 프레임의 축. **UR URDF `base_link` 관례는 DH `base` 에서 z 로 180° 돌아 있다**(비전 27b).
#: 탐침 3(맥마클2 9/21)에서 확인했다: 어깨 프레임 = Rz(pi + pan) 이고 세 자세 모두 1e-5 안에서 맞는다.
#: 그래서 pan = 0 일 때 밑동은 Rz(pi) 다. **이 회전을 빼면 팔이 x·y 가 뒤집힌 자리로 간다** — 27b 와 같은 사고다.
ARM_BASE_YAW = math.pi
#: 탐침 3 에서 읽은 자산 치수(참조 직후 world, base_link 원점 기준). 런타임에서 다시 재지만,
#: 재지 못했을 때의 근거이자 "자산이 바뀌었다" 를 알아채는 기준이다.
ASSET_SHOULDER_Z = 0.369159      # 어깨 원점 높이 → 밑동은 여기서 d1 내린 0.28
ASSET_BASE_TOP_Z = 0.301         # base_link 윗면. 상판을 여기에 얹는다
ASSET_BASE_BOTTOM_Z = -0.0262    # 바퀴가 링크 원점보다 아래로 내려간다
#: 팔을 `base_link` 로컬에서 이만큼 옮긴다 (dx, dy, dz). 9/21 재범 확정안.
#:
#: **x** — 팔을 몸체 뒤끝으로 보내 반대쪽 끝을 통짜 트레이에 내준다. 어느 끝인지는 기하가 정했다:
#: 적재 자리에서 벨트는 로컬 −x 쪽(−0.60)이라 팔이 +x 끝이면 봉투까지 0.95 로 사거리 밖이다.
#: 그래서 −x 다. 정차 자리는 `layout.ARM_MOUNT_SHIFT_X` 로 **같은 만큼 앞으로 민다** — 그러면
#: 팔 밑동의 월드 자리가 옮기기 전과 같아 도달·자세 계산이 전부 그대로 유지된다.
#: **z** — 재범이 그린 "낮고 넓은 받침" 0.15. 밑동이 0.28 → 0.43, 어깨가 0.369 → 0.519 다.
#: dz 가 줄어 팔이 덜 뻗는다(비전 9/21: 벨트 sin|q3| 0.967→0.999·뻗은비율 86→78 %,
#: 보관함 0.912→0.988·92→85 %). 받침을 뺀 채 x 만 옮기면 이 이득이 사라진다.
ARM_MOUNT_LOCAL = (-0.35, 0.0, 0.15)
#: 받침 판의 (가로, 세로). 높이는 몸체 윗면에서 새 밑동 높이까지라 계산해서 쓴다 —
#: 밑동이 몸체 윗면보다 **아래**(0.28 < 0.301)에 있어서 판 높이(0.129)와 올림량(0.15)이 다르다.
#: 0.30 x 0.30 은 몸체 뒤끝에서 0.034 넘어가지만 계획 footprint(1.10) 안이라 여유 규칙은 그대로다.
#: 비전이 이 치수로 네 동작을 다 확인했다(9/21) — 받침대 UR5 의 기둥과 달리 팔이 이 높이로 안 내려간다.
RISER_SIZE = (0.30, 0.30)
#: 상판을 base_link 기준 어디에 둘지 (x, y, z). z 는 윗면 + 상판 절반 두께.
#: y 를 한쪽으로 밀어 팔 밑동(로컬 원점) 아래를 비운다 — 받침대 구성에서 기둥에 팔이 걸렸던 것과 같은 이유다.
#: y 는 몸체 반폭(0.397) − 상판 반폭(0.085) = 0.312 까지 뺄 수 있다. 0.30 은 그 안에서 **팔 스윕에서
#: 제일 먼** 값이다 — lap3 에서 위팔이 3번 칸 벽에 sep 0.010 로 막혔다(목표 pan −174°, 먼 쪽으로 돌았다).
#:
#: **0.25 로 되돌리지 마라.** 비전이 경유 자세에서 다섯 칸을 다 풀어 `sin|q3|` 을 비교했다(9/21):
#:   칸 1  0.683 → 0.745 / 칸 2  0.445 → **0.544** / 칸 3  0.726 → 0.818 / 칸 4  0.813 → 0.881 / 칸 5  0.958 → 0.983
#: 칸마다 0.05–0.10 오르고, 제일 나쁜 칸이 통과선(0.35)에서 멀어진다. 경로도 둘 다 빈다.
#: 밑동 기준 수평은 0.300–0.439 로 하한 0.20 안이다.
DECK_LOCAL_CENTRE = (0.0, -0.30, ASSET_BASE_TOP_Z + 0.02)
#: 상판을 얹을 링크. 베이스 몸체다(`world`·`dummy_base_*` 는 이동 사슬이라 여기가 아니다).
DECK_PARENT_LINK = "base_link"
#: 합본의 전체 DOF(dummy 3 + UR5 6). 그리퍼는 없다(탐침 2번).
ASSET_DOF_NAMES = JOINT_NAMES + ARM_JOINT_NAMES


def asset_lift():
    """자산을 지면에서 띄우는 높이(m). `ground_lift()` 가 런타임에 재는 값의 **기대치**다.

    `GROUND_CLEARANCE` 와 **다른 값이다** — 충돌체가 링크 원점보다 아래로 내려가므로 그만큼 더 올려야
    바닥이 `GROUND_CLEARANCE` 만큼 뜬다. 9/21 에 도달 계산에서 이 둘을 섞어 써서 어깨가 2.6 cm 낮게
    잡혔다(비전이 잡았다). 높이 예산은 경계에서 자세로 그대로 넘어온다.
    """
    return GROUND_CLEARANCE - ASSET_BASE_BOTTOM_Z


def shoulder_world_z():
    """정차 상태에서 어깨의 **월드 z**. 도달 예산의 기준점이다.

    받침(`ARM_MOUNT_LOCAL[2]`)을 **포함한다** — 자산 그대로의 0.369 가 아니라 0.519 다. 9/21 에
    `GROUND_CLEARANCE` 와 `asset_lift()` 를 섞어 써서 어깨가 2.6 cm 낮게 잡혔던 것과 같은 자리라,
    높이를 더하는 항이 늘 때마다 여기 하나로 모은다.
    """
    return asset_lift() + ASSET_SHOULDER_Z + ARM_MOUNT_LOCAL[2]


def arm_base_world_z():
    """정차 상태에서 팔 밑동(`ur_arm_base_link`)의 **월드 z**. 비전 표의 "실제 기준" 이 이것이다."""
    return shoulder_world_z() - UR5_D1


def riser_height():
    """받침 판의 높이(m). 몸체 윗면에서 **새 밑동 높이**까지다.

    올림량(0.15)과 **다른 값이다** — 자산의 밑동(0.28)이 몸체 윗면(0.301)보다 0.021 아래에 있어서
    그만큼 짧다. 둘을 같다고 쓰면 판이 밑동을 2.1 cm 뚫고 올라온다.
    """
    return ASSET_SHOULDER_Z - UR5_D1 + ARM_MOUNT_LOCAL[2] - ASSET_BASE_TOP_Z

#: 몸체 바닥과 지면 사이 틈(m). **0 이면 안 된다** — 상자 바닥이 지면에 정확히 닿으면 PhysX 가 지지 접촉을
#: 만들고 그 마찰이 prismatic 드라이브를 끈다(실습24-pre: 명령 대비 97–99 %, 띄운 뒤 100.7 %).
#: **PhysX 접촉 보고 문턱(기본 contactOffset 0.02)보다 커야 한다** — 같으면 매 스텝 `near sep=0.0200` 이
#: 찍혀 긴 회차의 접촉 로그가 그 줄로 찬다(실습24: 300 s 에 138줄). 0.02 → 0.03.
#: 위로는 상판 머리 위 여유(layout.HEADROOM)에 먹힌다 — 0.05 면 여유가 0.053 까지 줄어 문턱에 붙는다.
#: 실물은 바퀴가 몸체를 띄운다. 임시값이고 실측 아님.
GROUND_CLEARANCE = 0.03


def wrap_angle(yaw):
    """[-pi, pi) 로 접는다. base_driver 가 odom yaw 로 그대로 쓴다."""
    wrapped = (float(yaw) + math.pi) % (2.0 * math.pi) - math.pi
    return -math.pi if wrapped == math.pi else wrapped


def order_command(names, velocities):
    """받은 JointState 를 우리 축 순서로. 없는 이름은 0 이다.

    주행은 셋을 다 보내지만 순서가 다를 수 있다. 이름으로 고른다(base_driver 가 우리에게 하는 것과 같다).
    """
    if velocities is None:
        return (0.0, 0.0, 0.0)
    lookup = {}
    for name, value in zip(names or (), velocities, strict=False):
        if value is not None:
            lookup[name] = float(value)
    return tuple(lookup.get(name, 0.0) for name in JOINT_NAMES)


def state_message(positions, velocities):
    """`/amr_1/joint_states` 로 낼 (이름, 위치, 속도). yaw 는 접고, 속도는 **비우지 않는다**.

    velocities 가 None 이면 이름과 위치만 돌려준다(주행이 stamp 차이로 만든다). 0 으로 채우지 않는다 —
    그러면 base/stopped 가 항상 참이 된다(주행 9/21).
    """
    x, y, yaw = (float(v) for v in positions)
    ordered = (x, y, wrap_angle(yaw))
    if velocities is None:
        return (list(JOINT_NAMES), list(ordered), None)
    return (list(JOINT_NAMES), list(ordered), [float(v) for v in velocities])


def stale(last_seen_s, now_s, timeout_s=0.5):
    """명령이 끊겼나. 끊기면 0 을 적용한다(계약 5절). 시계는 wall 이다."""
    return last_seen_s is None or (now_s - last_seen_s) > timeout_s


def body_size(height=0.32717):
    """베이스 몸체 상자 치수. **실측 bbox 다**(ridgeback_ur5.usd 의 base_link, 박세준 #408 6.5절).

    여유 계산은 이보다 큰 **계획 footprint**(`layout.AMR_FOOTPRINT`)로 한다. 장면의 몸체는 실제 크기여야
    접촉 관측이 뜻을 갖고, 여유는 큰 쪽이어야 Nav2 로 갈아 끼울 때 통로가 모자라지 않는다(주행 9/21).

    공식 에셋 자체가 아니라 그 치수의 상자다 — 에셋에는 상판 칸·카메라·라이다·ROS 그래프가 없어
    v0 에서 쓸 것이 몸체뿐이고, 상자여야 K2b(그 에셋으로 갈아 끼우기) 전까지 치수를 한 곳에서 바꾼다.
    """
    from . import layout as layoutlib

    length, width = layoutlib.AMR_BBOX  # 여유 계산의 계획 footprint 가 아니라 실측 bbox 다
    return (length, width, height)


def build(stage, root, origin_xy, limits=None, drive=None, size=None, color=(0.25, 0.45, 0.75)):
    """dummy 3축(prismatic x -> prismatic y -> revolute z)과 그 위의 베이스 몸체를 만든다.

    반환 (articulation 경로, base_link 경로, 관절 이름들). 레일과 같은 모양이라 PhysX 가 한 articulation 으로 푼다.
    x·y 는 world 축과 평행해야 하므로 **중간 링크에 회전을 주지 않는다** — 회전은 마지막 revolute 하나뿐이다.
    """
    from pxr import Sdf, UsdGeom, UsdPhysics

    from . import scene as scenelib

    limits = limits or DEFAULT_LIMITS
    drive = drive or DEFAULT_DRIVE
    size = size or body_size()
    ox, oy = origin_xy
    UsdGeom.Xform.Define(stage, root)
    # 바닥이 지면에 닿지 않도록 띄운다(GROUND_CLEARANCE 주석 참고).
    ground = (ox, oy, GROUND_CLEARANCE + size[2] / 2.0)

    def link(name, parts=()):
        return scenelib._link(stage, f"{root}/{name}", ground, 20.0, parts)

    anchor = link("Anchor")
    slide_x = link("SlideX")
    slide_y = link("SlideY")
    body = link("Base", [("BaseBody", (0.0, 0.0, 0.0), size, color, True)])

    # 월드에 고정된 뿌리. 레일의 root_joint 와 같은 방식이다.
    root_joint = UsdPhysics.FixedJoint.Define(stage, f"{root}/root_joint")
    root_joint.CreateBody1Rel().SetTargets([Sdf.Path(str(anchor.GetPath()))])
    UsdPhysics.ArticulationRootAPI.Apply(root_joint.GetPrim())

    scenelib._prismatic(stage, f"{root}/{JOINT_NAMES[0]}", str(anchor.GetPath()), str(slide_x.GetPath()),
                        "X", limits[0][0], limits[0][1], drive)
    scenelib._prismatic(stage, f"{root}/{JOINT_NAMES[1]}", str(slide_x.GetPath()), str(slide_y.GetPath()),
                        "Y", limits[1][0], limits[1][1], drive)
    revolute = UsdPhysics.RevoluteJoint.Define(stage, f"{root}/{JOINT_NAMES[2]}")
    revolute.CreateBody0Rel().SetTargets([Sdf.Path(str(slide_y.GetPath()))])
    revolute.CreateBody1Rel().SetTargets([Sdf.Path(str(body.GetPath()))])
    revolute.CreateAxisAttr("Z")
    # 한계를 두지 않는다(제자리 회전이 여러 바퀴여도 된다). base_driver 가 yaw 를 접어 쓴다.
    api = UsdPhysics.DriveAPI.Apply(revolute.GetPrim(), "angular")
    api.CreateTypeAttr("force")
    api.CreateStiffnessAttr(float(drive[0]))
    api.CreateDampingAttr(float(drive[1]))
    api.CreateMaxForceAttr(float(drive[2]))
    api.CreateTargetVelocityAttr(0.0)
    return (f"{root}/root_joint", str(body.GetPath()), list(JOINT_NAMES))


def reference(stage, root, usd_path, origin_xy, limits=None, drive=None, log=print):
    """공식 합본(`ridgeback_ur5.usd`)을 참조해 베이스로 쓴다. 상자 대신이다(재범 지시 9/21).

    상자를 만드는 `build()` 와 **같은 계약**을 지킨다: 같은 관절 이름 셋을 같은 속도 드라이브로 몬다.
    다른 점은 링크·충돌체·팔을 우리가 만들지 않고 자산이 준다는 것뿐이다.

    반환 `build()` 와 같은 (articulation 경로, base_link 경로, 관절 이름들).

    **드라이브를 다시 건다.** 자산이 들고 온 게인이 우리 상자 때와 다르면 같은 속도 명령에 다른 응답을 낸다 —
    주행의 추종 파라미터(0.3 m/s·0.5 rad/s·감속 반경 0.5)는 **상자에서 맞춘 값**이고 추종기는 질량·관성을
    모른다(주행 9/21). 그래서 관절을 이름으로 찾아 우리 값으로 덮는다. 찾은 것과 덮기 전 값을 로그에 남긴다.
    """
    from isaacsim.core.utils.stage import add_reference_to_stage
    from pxr import Gf, UsdGeom, UsdPhysics

    limits = limits or DEFAULT_LIMITS
    drive = drive or DEFAULT_DRIVE
    add_reference_to_stage(usd_path, root)
    prim = stage.GetPrimAtPath(root)
    if not prim.IsValid():
        raise RuntimeError(f"--amr-usd did not load: {usd_path} -> {root}")
    # **이 자산은 프림 이동이 놓는 쪽이다.** 앵커(`localPos0`)도 같이 옮기지만 실제로 먹는 것은 이쪽이다 —
    # 회차 둘이 그것을 말한다(9/21): 682fb30 은 프림·앵커에 같은 (x, y) 를 줬는데 결과가 두 배가 아니라
    # 한 번만 적용됐고, 807102d 는 **앵커 z 만** 올렸더니 몸체 높이가 1 mm 도 안 변했다.
    # 받침대 UR5 자산은 반대였다(앵커가 먹었다) — **자산마다 다르므로 둘 다 같은 값으로 준다.**
    lift = ground_lift(stage, root, log)
    xform = UsdGeom.Xformable(prim)
    xform.ClearXformOpOrder()
    xform.AddTranslateOp().Set(Gf.Vec3d(float(origin_xy[0]), float(origin_xy[1]), lift))
    # **프림을 옮기는 것만으로는 로봇이 안 따라온다.** 탐침(맥마클2, 9/21): 이 자산에는 `body0` 가 빈
    # FixedJoint 가 있어 `world` 링크를 월드에 박는다(`/World/Amr/world/FixedJoint`). body0 가 비면
    # `localPos0` 가 **월드 좌표**라, 그 값을 안 옮기면 PhysX 는 프림 이동과 무관하게 원점에서 푼다.
    # 받침대 UR5 에서 겪은 것과 같은 모양이다(`ur5_cell._pin_world_joints`).
    # 앵커도 같은 값으로 옮긴다. 이 자산에서는 안 먹는 것으로 보이지만(위 주석), 받침대 UR5 자산에서는
    # 이쪽이 먹었다. **둘을 같은 값으로 두면 어느 쪽이 먹든 결과가 같다** — 다른 값을 주면 두 배가 되거나
    # 어긋난다. 자산의 충돌 메시가 링크 원점보다 아래로 내려가(탐침 3: −0.0262) z 를 0 으로 두면
    # 바퀴가 지면에 박히고, 그 마찰이 prismatic 구동을 붙잡는다(회차 682fb30: sep=-0.0259 impulse=2.19e6).
    pinned = pin_world_joints(stage, root, (float(origin_xy[0]), float(origin_xy[1]), lift), log)
    if not pinned:
        log("amr note: no world-anchored joint found; the prim translation alone places it")

    found, missing = {}, []
    for name in JOINT_NAMES:
        joint = _find_joint(stage, root, name)
        if joint is None:
            missing.append(name)
            continue
        found[name] = joint
    if missing:
        raise RuntimeError(f"--amr-usd {usd_path}: dummy joints {missing} not found under {root}; "
                           f"found {sorted(found)} (주행 규격은 이 셋을 요구한다)")

    for name, joint in found.items():
        api_name = "angular" if name.endswith("revolute_z_joint") else "linear"
        api = UsdPhysics.DriveAPI.Apply(joint.GetPrim(), api_name)
        before = (api.GetStiffnessAttr().Get(), api.GetDampingAttr().Get(), api.GetMaxForceAttr().Get())
        api.CreateTypeAttr("force")
        api.CreateStiffnessAttr(float(drive[0]))
        api.CreateDampingAttr(float(drive[1]))
        api.CreateMaxForceAttr(float(drive[2]))
        api.CreateTargetVelocityAttr(0.0)
        log(f"amr drive joint={name} kind={api_name} asset_was={before} ours={tuple(drive)}")

    roots = articulation_roots(stage, root)
    log(f"amr referenced usd={usd_path} root={root} origin_xy={tuple(origin_xy)} "
        f"articulation_roots={roots} joints={list(JOINT_NAMES)}")
    if len(roots) != 1:
        log(f"WARN amr articulation roots={len(roots)} (하나여야 베이스와 팔이 한 몸이다): {roots}")
    return (roots[0] if roots else root, root, list(JOINT_NAMES))


def _shift_prim(stage, path, offset):
    """프림의 로컬 평행이동에 `offset` 을 더한다. 반환 (before, after) 또는 None.

    자산이 어떤 xform op 를 쓰는지 모르므로 **있는 translate op 를 찾아 더하고**, 없으면 만든다.
    통째로 다시 쓰지 않는 이유는 op 순서를 모른 채 덮으면 회전이 날아가기 때문이다.
    """
    from pxr import Gf, UsdGeom

    prim = stage.GetPrimAtPath(path)
    if not prim.IsValid():
        return None
    xformable = UsdGeom.Xformable(prim)
    for op in xformable.GetOrderedXformOps():
        if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
            before = op.Get()
            before = (0.0, 0.0, 0.0) if before is None else tuple(float(v) for v in before)
            after = tuple(b + o for b, o in zip(before, offset, strict=True))
            op.Set(Gf.Vec3d(*after) if op.GetPrecision() == UsdGeom.XformOp.PrecisionDouble
                   else Gf.Vec3f(*after))
            return (before, after)
    UsdGeom.XformCommonAPI(xformable).SetTranslate(Gf.Vec3d(*offset))
    return ((0.0, 0.0, 0.0), tuple(float(v) for v in offset))


def _joint_for_child(stage, root, link_name):
    """`body1` 이 `link_name` 링크인 관절. 관절 **이름**을 모를 때 자식 링크로 찾는다."""
    from pxr import Usd, UsdPhysics

    for prim in Usd.PrimRange(stage.GetPrimAtPath(root), Usd.TraverseInstanceProxies()):
        if not prim.IsA(UsdPhysics.Joint):
            continue
        joint = UsdPhysics.Joint(prim)
        targets = [str(t) for t in joint.GetBody1Rel().GetTargets()]
        if any(t.rsplit("/", 1)[-1] == link_name for t in targets):
            return joint
    return None


def move_arm_mount(stage, root, offset=None, log=print):
    """팔을 `base_link` 안에서 `offset` 만큼 통째로 옮기고, 그 밑에 받침 판을 세운다.

    9/21 재범 확정안이다 — 팔은 뒤끝, 반대쪽 끝은 통짜 트레이. **`build_arm_base_frame` 보다 먼저**
    불러야 한다. 밑동 프레임은 어깨 프림의 자리를 **재서** 만드는데, 옮기기 전에 재면 옛 자리에 박힌다.

    **두 군데를 같은 값으로 옮긴다**(자산 참조 때와 같은 이유):
      1. 어깨 관절의 `localPos0` — PhysX 가 실제로 푸는 값
      2. `ur_arm_*` 링크 프림 전부 — 물리가 돌기 전의 자세와, 우리가 재서 쓰는 값
    하나만 옮기면 **조용히 어긋난다**: 1 만 옮기면 밑동 프레임이 옛 자리에 서고, 2 만 옮기면 물리가
    첫 스텝에서 팔을 원점으로 되돌린다. 실제로 맞았는지는 맥마클2 의 어깨 월드 자세 탐침이 본다.

    반환 (옮긴 링크 수, 관절 경로 또는 None).
    """
    from pxr import Gf, UsdGeom, UsdPhysics

    offset = tuple(float(v) for v in (offset or ARM_MOUNT_LOCAL))
    parent = f"{root}/{DECK_PARENT_LINK}"
    if not stage.GetPrimAtPath(parent).IsValid():
        log(f"WARN amr arm_mount not moved: {parent} is missing")
        return (0, None)

    joint = _joint_for_child(stage, root, SHOULDER_LINK)
    joint_path = None
    if joint is None:
        log(f"WARN amr arm_mount joint not found for child={SHOULDER_LINK}; "
            "프림만 옮기면 물리가 첫 스텝에서 되돌린다")
    else:
        joint_path = str(joint.GetPrim().GetPath())
        before = joint.GetLocalPos0Attr().Get()
        before = (0.0, 0.0, 0.0) if before is None else tuple(float(v) for v in before)
        after = tuple(b + o for b, o in zip(before, offset, strict=True))
        joint.GetLocalPos0Attr().Set(Gf.Vec3f(*after))   # pin_world_joints 와 같은 정밀도로 쓴다
        log(f"amr arm_mount joint={joint_path} local_pos0={tuple(round(v, 6) for v in before)}"
            f"->{tuple(round(v, 6) for v in after)}")

    # 링크 프림 전부. **root 바로 아래 것만** 옮긴다 — 부모와 자식을 둘 다 옮기면 두 번 밀린다.
    moved = []
    for prim in stage.GetPrimAtPath(root).GetChildren():
        name = prim.GetName()
        if not name.startswith("ur_arm_"):
            continue
        shifted = _shift_prim(stage, str(prim.GetPath()), offset)
        if shifted is not None:
            moved.append((name, shifted[1]))
    if not moved:
        log(f"WARN amr arm_mount moved 0 links under {root} (이름이 ur_arm_* 가 아니거나 계층이 다르다)")

    # 받침 판. 몸체 윗면에서 새 밑동 높이까지다(riser_height: 올림량과 다른 값이다).
    height = riser_height()
    cube = UsdGeom.Cube.Define(stage, f"{parent}/ArmRiser")
    cube.CreateSizeAttr(1.0)
    xform = UsdGeom.Xformable(cube)
    xform.AddTranslateOp().Set((offset[0], offset[1], ASSET_BASE_TOP_Z + height / 2.0))
    xform.AddScaleOp().Set((float(RISER_SIZE[0]), float(RISER_SIZE[1]), float(height)))
    cube.CreateDisplayColorAttr([(0.45, 0.45, 0.50)])
    UsdPhysics.CollisionAPI.Apply(cube.GetPrim())

    log(f"amr arm_mount offset={tuple(round(v, 4) for v in offset)} links={len(moved)} "
        f"names={[m[0] for m in moved]} riser={RISER_SIZE}x{round(height, 4)} "
        f"shoulder_local_z={round(ASSET_SHOULDER_Z + offset[2], 6)} "
        f"arm_base_local_z={round(ASSET_SHOULDER_Z + offset[2] - UR5_D1, 6)} "
        f"(정차 자리는 layout.ARM_MOUNT_SHIFT_X 로 같은 만큼 앞으로 밀려 있다)")
    return (len(moved), joint_path)


def build_arm_base_frame(stage, root, log=print):
    """팔 밑동 프레임 프림을 만든다. **원점은 재서 넣고, 축만 우리가 고른다**(비전 9/21).

    자산에 `ur_arm_base_link` 라는 링크가 **없다**(탐침: 어깨 관절의 `body0` 가 `base_link` 다 — 팔이 AMR
    몸체에 바로 붙어 있다). 그래서 프레임을 우리가 만드는데, 여기에 함정이 있다:

    **AMR 몸체 원점에 그냥 얹고 싶어진다.** 그러면 장착 오프셋만큼 전부 어긋나고, 증상은 27b(z 축 180°)와
    같이 **조용하다** — 팔은 자기 계산상 목표에 정확히 가고 거기가 봉투에서 그만큼 떨어져 있을 뿐이다.
    부호가 뒤집히지도 않아 27b 보다 **알아보기 더 어렵다.**

    원점은 자산이 이미 정해 놓았다: **shoulder_pan 축 위, 밑동 판.** 팔의 DH 첫 행이 `d1` 이라
    "루트에서 z 로 d1 올라가면 어깨" 가 전제다. 그래서 **어깨 원점에서 z 로 `UR5_D1` 내린 자리**다.
    축은 UR URDF `base_link` 관례를 따른다(팔 노드의 `arm_base_frame_convention` 과 같은 것).
    지금은 부모(`base_link`)의 축을 그대로 쓴다 — 관례가 다르면 여기서 회전을 준다.

    반환 (프림 경로, 부모 기준 위치). 어깨 링크를 못 찾으면 None 을 돌려주고 **만들지 않는다** —
    자리를 모르는 채 만드는 것이 이 함수가 막으려는 바로 그 실수다.
    """
    from pxr import Gf, Sdf, UsdGeom

    parent = f"{root}/{DECK_PARENT_LINK}"
    shoulder = f"{root}/{SHOULDER_LINK}"
    if not stage.GetPrimAtPath(parent).IsValid() or not stage.GetPrimAtPath(shoulder).IsValid():
        log(f"WARN amr arm_base_frame not built: need {parent} and {shoulder}; "
            "자리를 모르는 채 만들면 장착 오프셋만큼 조용히 어긋난다")
        return None
    local = _local_translation(stage, parent, shoulder)
    if local is None:
        log(f"WARN amr arm_base_frame not built: cannot read {shoulder} relative to {parent}")
        return None
    origin = (local[0], local[1], local[2] - UR5_D1)
    path = f"{parent}/{ARM_BASE_FRAME}"
    xform = UsdGeom.Xform.Define(stage, path)
    api = UsdGeom.XformCommonAPI(xform)
    api.SetTranslate(Gf.Vec3d(*origin))
    api.SetRotate(Gf.Vec3f(0.0, 0.0, math.degrees(ARM_BASE_YAW)))
    xform.GetPrim().CreateAttribute("isaac:nameOverride", Sdf.ValueTypeNames.String).Set(ARM_BASE_FRAME)
    log(f"amr arm_base_frame path={path} parent={DECK_PARENT_LINK} "
        f"shoulder_local={tuple(round(v, 6) for v in local)} d1={UR5_D1} "
        f"origin={tuple(round(v, 6) for v in origin)} yaw_deg={math.degrees(ARM_BASE_YAW):.1f} "
        f"(원점은 쟀고 축은 UR URDF base_link 관례다)")
    return (path, origin)


#: 트레이 면의 마찰(고무 매트). 봉투(20 g)가 PhysX 기본 마찰 0.5 위에서 회전·넘김 때 밀렸다 — RC-1 회차55·56
#: 칸 이탈 11–13 cm, 회전 반감(aedc735) 회차57 에서도 최대 8.2 cm(칸 한도 9 cm). 고른 값이다.
#: 결합은 max — 봉투 쪽 재질(기본)과 상관없이 트레이 값이 쓰인다.
TRAY_GRIP = {"static": 1.0, "dynamic": 0.9, "restitution": 0.0, "combine": "max"}


def bind_tray_grip(stage, prim, material_path, grip=TRAY_GRIP):
    """트레이 충돌체에 마찰 재질을 붙인다(physics purpose). 같은 경로면 재질은 한 번만 만든다."""
    from pxr import Sdf, UsdPhysics, UsdShade

    material_prim = stage.GetPrimAtPath(material_path)
    if not material_prim.IsValid():
        material = UsdShade.Material.Define(stage, material_path)
        physics = UsdPhysics.MaterialAPI.Apply(material.GetPrim())
        physics.CreateStaticFrictionAttr(float(grip["static"]))
        physics.CreateDynamicFrictionAttr(float(grip["dynamic"]))
        physics.CreateRestitutionAttr(float(grip["restitution"]))
        # PhysxSchema 는 Isaac 에만 있다(usd-core 에 없다). 스키마 이름과 속성을 직접 써서 둘 다 같게 만든다.
        material_prim = material.GetPrim()
        material_prim.AddAppliedSchema("PhysxMaterialAPI")
        material_prim.CreateAttribute("physxMaterial:frictionCombineMode", Sdf.ValueTypeNames.Token).Set(
            grip["combine"])
    UsdShade.MaterialBindingAPI.Apply(prim).Bind(
        UsdShade.Material(material_prim), bindingStrength=UsdShade.Tokens.weakerThanDescendants,
        materialPurpose="physics")


def build_tray_on_base(stage, root, layout_module, log=print):
    """상판 다섯 칸 대신 **통짜 트레이 하나**를 `base_link` 의 자식 충돌체로 얹는다.
    반환 (칸 중심들, 트레이 프림 경로, 프레임 경로들).

    9/21 재범 확정안. 칸막이가 없어져 상판 자기 충돌 쌍이 사라진다 — lap3 에서 위팔이 3번 칸 벽에
    sep 0.010 로 막혔던 그 형상이다. `deck_slot_N` 프레임은 트레이 **안의 고정된 놓을 자리**로 남으므로
    계약·`target_slot`·결정 28/44·zones·팔 매개변수는 하나도 안 바뀐다.

    `scene.build_boxes` 의 `FixedCuboid` 는 **월드에 고정**이라 쓸 수 없다 — AMR 이 움직여도 그 자리에
    남는다. 그래서 강체를 새로 만들지 않고 `base_link` 아래에 충돌 큐브만 붙인다.

    칸 중심은 **base_link 로컬 좌표**로 돌려준다. 세계 좌표가 필요하면 부르는 쪽이 변환한다 —
    빌드 때 세계 좌표를 굳히면 AMR 이 움직인 뒤 판정이 틀린다(`ur5_cell.slot_centres` 와 같은 이유).
    """
    from pxr import UsdGeom, UsdPhysics

    parent = f"{root}/{DECK_PARENT_LINK}"
    if not stage.GetPrimAtPath(parent).IsValid():
        log(f"WARN amr tray not built: {parent} is missing")
        return ([], None, [])
    boxes, slots = layout_module.tray_boxes(ASSET_BASE_TOP_Z)
    tray_root = f"{parent}/Tray"
    UsdGeom.Xform.Define(stage, tray_root)
    for box in boxes:
        cube = UsdGeom.Cube.Define(stage, f"{tray_root}/{box.name}")
        cube.CreateSizeAttr(1.0)
        xform = UsdGeom.Xformable(cube)
        xform.AddTranslateOp().Set(tuple(float(v) for v in box.center))
        xform.AddScaleOp().Set(tuple(float(v) for v in box.size))
        cube.CreateDisplayColorAttr([tuple(box.color)])
        if box.kind == "fixed":
            UsdPhysics.CollisionAPI.Apply(cube.GetPrim())
            bind_tray_grip(stage, cube.GetPrim(), f"{tray_root}/GripMaterial")
    # 자리마다 프레임 프림. 이름은 `deck_slot_N` 그대로다 — 트레이로 바뀐 것은 **형상**이지 계약이 아니다.
    # 원점은 결정 23 그대로 "봉투가 놓이는 면" = 트레이 **바닥 윗면**의 그 자리 중심이다.
    frames = []
    for index, slot in enumerate(slots):
        xform = UsdGeom.Xform.Define(stage, f"{tray_root}/DeckSlot{index + 1}")
        xform.AddTranslateOp().Set(tuple(float(v) for v in slot))
        frames.append(str(xform.GetPath()))
    # 밑동 축이 Rz(pi) 라 **밑동 기준으로는 x·y 부호가 뒤집힌다** — 자리 번호도 x 축에서 역순으로 보인다
    # (비전 9/21). 팔은 TF 로 받으니 저절로 맞지만 사람이 로그를 읽을 때 헷갈리는 자리라 같이 찍는다.
    shoulder_z = ASSET_SHOULDER_Z + ARM_MOUNT_LOCAL[2]
    distance = [round(((s[0] - ARM_MOUNT_LOCAL[0]) ** 2 + (s[1] - ARM_MOUNT_LOCAL[1]) ** 2
                       + (s[2] - shoulder_z) ** 2) ** 0.5, 4) for s in slots]
    log(f"amr tray parent={parent} boxes={len(boxes)} slots_local={[tuple(round(v, 4) for v in s) for s in slots]} "
        f"shoulder_distance={distance} frames={len(frames)} inner={layout_module.TRAY['inner']} "
        f"lip={layout_module.TRAY['lip']} (밑동 기준으로는 x·y 부호가 뒤집힌다)")
    return (slots, tray_root, frames)


#: 2D 라이다(Nav2 트랙, 9/23). 합본 자산에는 라이다가 없다(#408 6.5절) — 우리가 붙인다.
#: 자리: `base_link` 로컬. 하판과 상판 사이 (0.43, 0, 0.25). 원본 자산의
#: `/base_link/visuals/mesh_0` 가 이 높이의 자기 몸체 반사를 만들므로 라이다 사용 시 그 시각 메시만 숨긴다.
#: `/base_link/collisions/mesh_0` 는 별도 프림이며 PhysX 접촉을 위해 그대로 둔다.
#: 월드 스캔 높이는 약 0.306 m. 단일 2D 평면 밖 장애물은 별도 검증이 필요하다.
LIDAR_MOUNT_LOCAL = (0.43, 0.0, 0.25)
LIDAR_OCCLUDING_VISUAL = "base_link/visuals/mesh_0"
LIDAR_CHASSIS_COLLISION = "base_link/collisions/mesh_0"
#: Isaac 5.1 RTX 라이다 2D 설정(공식 튜토리얼 tutorial_ros2_rtx_lidar — LaserScan 은 2D 설정에서만,
#: **한 바퀴를 다 돌아야** 한 번 나온다). 태규님 ~/test_amr 도 RTX 2D 였다(#459).
LIDAR_CONFIG = "Example_Rotary_2D"
#: 프레임·토픽. Nav2(nav2_params.yaml)는 `amr_1` 네임스페이스 안의 상대 이름 `scan` 을 읽는다.
LIDAR_FRAME = "lidar_link"
LIDAR_TOPIC = "scan"


def lidar_prim_path(root):
    return f"{root}/{DECK_PARENT_LINK}/{LIDAR_FRAME}"


def hide_lidar_occluding_visual(stage, root, log=print):
    """RTX 2D 광선을 가리는 차체 시각 mesh_0만 숨긴다. 별도 PhysX 충돌체는 유지한다.

    기대한 Isaac 5.1 Ridgeback 구조가 아니면 조용히 진행하지 않는다. 외부 USD 파일은 수정하지 않는다.
    """
    from pxr import UsdGeom, UsdPhysics

    visual_path = f"{root}/{LIDAR_OCCLUDING_VISUAL}"
    collision_path = f"{root}/{LIDAR_CHASSIS_COLLISION}"
    visual = stage.GetPrimAtPath(visual_path)
    collision = stage.GetPrimAtPath(collision_path)
    if not visual.IsValid() or not visual.IsA(UsdGeom.Mesh) or visual.HasAPI(UsdPhysics.CollisionAPI):
        raise RuntimeError(f"lidar visual mesh mismatch: {visual_path} (must be a visual-only Mesh)")
    if not collision.IsValid() or not collision.HasAPI(UsdPhysics.CollisionAPI):
        raise RuntimeError(f"lidar chassis collider missing: {collision_path}")
    UsdGeom.Imageable(visual).MakeInvisible()
    log(f"amr lidar self-occlusion mask={visual_path} collider_preserved={collision_path}")


#: 부하 측정용 여벌 AMR 이 설 자리(zones 이름). `--amr-count N` 이면 첫 대가 `--amr-start`(도크 1)에 서고
#: 2..N 번째가 아래 순서대로 선다. 배송은 첫 대만 한다 — 나머지는 센서만 켜고 서 있는다(재범 9/23).
EXTRA_DOCK_NAMES = ("dock_2", "dock_3", "dock_4")


def extra_amr_plan(count, zones, docks=EXTRA_DOCK_NAMES):
    """2..N 번째 AMR 의 [(번호, 네임스페이스, (x, y))]. `count` 가 1 이면 빈 목록이다.

    `zones` 는 스테이지의 `layout["zones"]`(이름 → (x, y, z, yaw))다. 자리가 없으면 ValueError —
    **조용히 겹쳐 세우지 않는다.** 겹치면 두 대가 서로 밀어 부하 측정이 아니라 사고가 된다.
    """
    count = int(count)
    if count < 1:
        raise ValueError(f"--amr-count 는 1 이상이다: {count}")
    if count - 1 > len(docks):
        raise ValueError(f"--amr-count 는 최대 {len(docks) + 1} 이다(설 자리 {docks}): {count}")
    out = []
    for index, name in enumerate(docks[:count - 1], start=2):
        pose = (zones or {}).get(name)
        if pose is None:
            raise ValueError(f"--amr-count {count} 인데 zones 에 {name} 이 없다")
        out.append((index, f"/amr_{index}", (float(pose[0]), float(pose[1]))))
    return out


def add_lidar(stage, root, graph_path, mount=LIDAR_MOUNT_LOCAL, config=LIDAR_CONFIG, namespace="/amr_1",
              log=print):
    """합본 `base_link` 아래에 RTX 2D 라이다를 달고 `/<ns>/scan`(LaserScan, frame `<ns>/lidar_link`)을 낸다.

    반환은 라이다 프림 경로 — `publish_tf(extra_static=...)` 로 `base_link → lidar_link` 를 같이 낸다.
    Isaac 이 있어야 돈다. **L3 미실행**(9/23 작성, 호출·노드 이름은 Isaac 5.1 공식 튜토리얼 그대로).
    """
    import omni.kit.commands
    import omni.graph.core as og
    import usdrt
    from pxr import Gf, Sdf

    path = lidar_prim_path(root)
    if not stage.GetPrimAtPath(f"{root}/{DECK_PARENT_LINK}").IsValid():
        raise RuntimeError(f"lidar parent {root}/{DECK_PARENT_LINK} is not valid")
    if tuple(mount) == LIDAR_MOUNT_LOCAL:
        hide_lidar_occluding_visual(stage, root, log)
    _ok, sensor = omni.kit.commands.execute(
        "IsaacSensorCreateRtxLidar", path=path, parent=None, config=config,
        translation=Gf.Vec3d(*mount), orientation=Gf.Quatd(1.0, 0.0, 0.0, 0.0))
    prim = sensor if hasattr(sensor, "GetPath") else stage.GetPrimAtPath(path)
    if not prim or not prim.IsValid():
        raise RuntimeError(f"IsaacSensorCreateRtxLidar did not create {path}")
    ns = namespace.strip("/")
    prim.CreateAttribute("isaac:nameOverride", Sdf.ValueTypeNames.String).Set(f"{ns}/{LIDAR_FRAME}")
    keys = og.Controller.Keys
    og.Controller.edit(
        {"graph_path": graph_path, "evaluator_name": "execution"},
        {
            keys.CREATE_NODES: [
                ("Tick", "omni.graph.action.OnPlaybackTick"),
                ("RenderProduct", "isaacsim.core.nodes.IsaacCreateRenderProduct"),
                ("Scan", "isaacsim.ros2.bridge.ROS2RtxLidarHelper"),
            ],
            keys.CONNECT: [
                ("Tick.outputs:tick", "RenderProduct.inputs:execIn"),
                ("RenderProduct.outputs:execOut", "Scan.inputs:execIn"),
                ("RenderProduct.outputs:renderProductPath", "Scan.inputs:renderProductPath"),
            ],
            keys.SET_VALUES: [
                ("RenderProduct.inputs:cameraPrim", [usdrt.Sdf.Path(str(prim.GetPath()))]),
                ("Scan.inputs:type", "laser_scan"),
                ("Scan.inputs:nodeNamespace", ns),
                ("Scan.inputs:topicName", LIDAR_TOPIC),
                ("Scan.inputs:frameId", f"{ns}/{LIDAR_FRAME}"),
            ],
        },
    )
    log(f"amr lidar prim={prim.GetPath()} config={config} mount_local={tuple(mount)} "
        f"topic=/{ns}/{LIDAR_TOPIC} frame={ns}/{LIDAR_FRAME}")
    return str(prim.GetPath())


#: RTX 라이다 점을 뷰포트에 그리는 replicator writer 이름. Isaac 버전마다 이름이 달라 앞에서부터 찾는다
#: (4.x 튜토리얼 `RtxLidarDebugDrawPointCloudBuffer`, 이후 `RtxLidarDebugDrawPointCloud`). 5.1 에서 어느 것이
#: 잡히는지는 기동 줄(`amr lidar debug draw writer=…`)이 말한다 — **L3 미확인**.
LIDAR_DEBUG_WRITERS = ("RtxLidarDebugDrawPointCloudBuffer", "RtxLidarDebugDrawPointCloud")


def add_lidar_debug_draw(lidar_path, writers=LIDAR_DEBUG_WRITERS, log=print):
    """라이다 스캔 점을 뷰포트에 그린다(`--lidar-debug`, 촬영용, 재범 9/25). 판정·토픽과 무관하다.

    회피 장면에서 보행자·더미가 스캔에 잡히는 것을 보이려는 것이다. 렌더 프로덕트를 하나 더 만들므로 rtf 를
    먹는다 — 기본은 끈다. 반환은 쓴 writer 이름. 어느 이름도 없으면 RuntimeError(부르는 쪽이 경고로 남긴다).
    """
    import omni.replicator.core as rep

    render_product = rep.create.render_product(lidar_path, [1, 1], name="LidarDebugDraw")
    problems = []
    for name in writers:
        try:
            writer = rep.writers.get(name)
        except Exception as error:  # 이름이 없으면 replicator 가 예외를 낸다
            problems.append(f"{name}: {type(error).__name__}")
            continue
        writer.attach([render_product])
        log(f"amr lidar debug draw writer={name} lidar={lidar_path} (촬영용, 판정 없음)")
        return name
    raise RuntimeError(f"no lidar debug draw writer ({'; '.join(problems)})")


#: 합본 손 카메라·흡착 그리퍼(9/23, 데이터비전). 받침대 UR5 는 `ur5_cell.add_camera_and_tf` 가 카메라를 달았고
#: 합본에는 없었다. 세준 자산(#506, `sim/assets/amr_gripper/short_gripper.usd`)을 손목 아래에 reference 하고 그 안의
#: D455 컬러 카메라로 낸다. 값은 오프라인(usd-core)으로 잰 것이다 — sim/assets/amr_gripper/README.md.
GRIPPER_USD = "short_gripper.usd"
#: 자산 안에서 붙일 프림(defaultPrim `/World` 에는 수집 때의 평행이동이 있어 그 아래를 직접 가리킨다).
GRIPPER_ASSET_PRIM = "/World/short_gripper_01"
#: 손목 프레임과 같은 자산 프레임. `AssemblerFixedJoint` 가 wrist_3 ↔ 이 프레임을 로컬 항등으로 묶는다.
GRIPPER_ATTACH_FRAME = "attach_frame"
#: 손목 기준 흡착점(`suction_cup`, SurfaceGripper 부착점). 자산이 바뀌면 다시 잰다.
GRIPPER_TCP_OFFSET = (0.0, 0.0, 0.1555)
#: 자산 안 컬러 카메라(손목 기준 (-0.0115, 0.07, 0.0355) m, 시선 = 공구 +Z, 수평 화각 90.5°).
GRIPPER_COLOR_CAMERA = "suction_cup/realsense_d455/RSD455/Camera_OmniVision_OV9782_Color"
#: 그 카메라의 초점거리·수평 조리개(mm, 자산 값). 판독 픽셀 계산에 쓴다.
GRIPPER_CAMERA_FOCAL_MM = 1.93
GRIPPER_CAMERA_H_APERTURE_MM = 3.896
#: 붙일 때 끄는 조인트(body0 이 이 장면에 없는 경로다)와 흡착 프림(흡착은 기존 가상 흡착이 한다).
GRIPPER_JOINTS_OFF = ("attach_frame/AssemblerFixedJoint", "suction_cup/Suction_Joint")
#: D455 안의 컬러 외 카메라(좌·우 IR, 가짜 깊이)와 그 렌더 프로덕트 틀. 카메라 목록에 컬러만 남긴다(재범 9/23).
#: 경로는 `realsense_d455` 기준이다. M0609 D455 모델(`canister_qr.attach_d455_model`)도 같은 목록을 쓴다.
D455_EXTRA_PRIMS = ("RSD455/Camera_OmniVision_OV9782_Left", "RSD455/Camera_OmniVision_OV9782_Right",
                    "RSD455/Camera_Pseudo_Depth", "RSD455/TemplateRenderProducts")
GRIPPER_PRIMS_OFF = ("SurfaceGripper", *(f"suction_cup/realsense_d455/{name}" for name in D455_EXTRA_PRIMS))
GRIPPER_NAME = "short_gripper"
#: optical(REP 103) = USD 카메라를 x 로 180° 돌린 것. 받침대 카메라와 같은 규약이다.
HAND_CAMERA_OPTICAL_QUAT = (0.0, 1.0, 0.0, 0.0)


def qr_code_pixels(face_side_m, distance_m, width_px, modules=21, border=4):
    """QR **코드 영역**(여백 뺀 것) 한 변이 영상에서 몇 px 인가. 광축이 QR 면에 수직일 때의 값이다.

    `face_side_m` 은 텍스처 한 변(여백 포함). `make_qr_textures.py` 는 여백 4 모듈, `ord-0001` 은 버전 1(21 모듈)이다.
    """
    fx = width_px * GRIPPER_CAMERA_FOCAL_MM / GRIPPER_CAMERA_H_APERTURE_MM
    code_side = face_side_m * modules / (modules + 2 * border)
    return code_side * fx / distance_m


def gripper_usd_path():
    """저장소 안 자산 경로(sim/assets/amr_gripper/short_gripper.usd)."""
    from pathlib import Path

    return str(Path(__file__).resolve().parents[2] / "assets" / "amr_gripper" / GRIPPER_USD)


def hand_camera_frames(namespace="/amr_1"):
    """(공구 프레임, optical 프레임) TF 이름. 팔 params 의 tool_frame·hand_camera_frame 과 같아야 한다."""
    ns = namespace.strip("/")
    return f"{ns}/{TCP_PARENT_LINK}", f"{ns}/hand_camera_optical"


def add_hand_camera(stage, root, graph_path, render_hz, resolution, max_hz, namespace="/amr_1", usd_path=None,
                    log=print):
    """합본 손목에 흡착 그리퍼+D455 자산을 붙이고 컬러 카메라로 `/<ns>/hand_camera/image_raw`·`camera_info` 를 낸다.

    - 자산의 `attach_frame` 이 손목과 겹치도록 reference 프림에 그 역변환을 준다.
    - 강체·조인트·SurfaceGripper·충돌은 끈다. 지금은 겉모양·카메라·TCP 만이다(진짜 흡착은 다음 단계).
    반환은 optical 프림 경로 — `publish_tf(extra_dynamic=...)` 로 손목과 같이 움직이는 TF 를 낸다.
    Isaac 이 있어야 돈다. **L3 미실행.**
    """
    import omni.graph.core as og
    import usdrt
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics

    from . import sensors as S

    usd_path = usd_path or gripper_usd_path()
    wrist = next((p for p in Usd.PrimRange(stage.GetPrimAtPath(root)) if p.GetName() == TCP_PARENT_LINK), None)
    if wrist is None:
        raise RuntimeError(f"{TCP_PARENT_LINK} not found under {root}")
    if wrist.IsInstanceProxy():
        raise RuntimeError(f"{wrist.GetPath()} is an instance proxy; cannot add the gripper")
    gripper = stage.DefinePrim(wrist.GetPath().AppendChild(GRIPPER_NAME), "Xform")
    gripper.GetReferences().AddReference(usd_path, Sdf.Path(GRIPPER_ASSET_PRIM))
    attach = gripper.GetPrimAtPath(GRIPPER_ATTACH_FRAME)
    if not attach.IsValid():
        raise RuntimeError(f"{usd_path}: {GRIPPER_ASSET_PRIM}/{GRIPPER_ATTACH_FRAME} not found")
    # 자산 루트 기준 attach_frame 자세의 역을 reference 프림에 준다 → 손목 == attach_frame.
    attach_local = UsdGeom.Xformable(attach).GetLocalTransformation()
    xform = UsdGeom.Xformable(gripper)
    xform.ClearXformOpOrder()
    xform.AddTransformOp().Set(attach_local.GetInverse())
    # 팔 링크 아래 강체를 중첩하지 않는다. 조인트·흡착 프림은 끄고, 충돌은 전부 끈다(visual).
    gripper.CreateAttribute("physics:rigidBodyEnabled", Sdf.ValueTypeNames.Bool).Set(False)
    for name in GRIPPER_JOINTS_OFF:
        joint = gripper.GetPrimAtPath(name)
        if joint.IsValid():
            joint.CreateAttribute("physics:jointEnabled", Sdf.ValueTypeNames.Bool).Set(False)
    for name in GRIPPER_PRIMS_OFF:
        prim = gripper.GetPrimAtPath(name)
        if prim.IsValid():
            prim.SetActive(False)
    colliders = 0
    for prim in Usd.PrimRange(gripper):
        if prim.HasAPI(UsdPhysics.CollisionAPI):
            prim.CreateAttribute("physics:collisionEnabled", Sdf.ValueTypeNames.Bool).Set(False)
            colliders += 1

    camera = gripper.GetPrimAtPath(GRIPPER_COLOR_CAMERA)
    if not camera.IsValid() or not camera.IsA(UsdGeom.Camera):
        raise RuntimeError(f"{usd_path}: colour camera {GRIPPER_COLOR_CAMERA} not found")
    optical = UsdGeom.Xform.Define(stage, camera.GetPath().AppendChild("optical"))
    optical.AddOrientOp().Set(Gf.Quatf(*map(float, HAND_CAMERA_OPTICAL_QUAT)))
    _tool, optical_frame = hand_camera_frames(namespace)
    optical.GetPrim().CreateAttribute("isaac:nameOverride", Sdf.ValueTypeNames.String).Set(optical_frame)

    ns = namespace.strip("/")
    skip = S.frame_skip(render_hz, max_hz)
    width, height = resolution
    keys = og.Controller.Keys
    og.Controller.edit(
        {"graph_path": graph_path, "evaluator_name": "execution"},
        {
            keys.CREATE_NODES: [
                ("OnTick", "omni.graph.action.OnPlaybackTick"),
                ("RenderProduct", "isaacsim.core.nodes.IsaacCreateRenderProduct"),
                ("CameraRgb", "isaacsim.ros2.bridge.ROS2CameraHelper"),
                ("CameraInfo", "isaacsim.ros2.bridge.ROS2CameraInfoHelper"),
            ],
            keys.CONNECT: [
                ("OnTick.outputs:tick", "RenderProduct.inputs:execIn"),
                ("RenderProduct.outputs:execOut", "CameraRgb.inputs:execIn"),
                ("RenderProduct.outputs:execOut", "CameraInfo.inputs:execIn"),
                ("RenderProduct.outputs:renderProductPath", "CameraRgb.inputs:renderProductPath"),
                ("RenderProduct.outputs:renderProductPath", "CameraInfo.inputs:renderProductPath"),
            ],
            keys.SET_VALUES: [
                ("RenderProduct.inputs:cameraPrim", [usdrt.Sdf.Path(str(camera.GetPath()))]),
                ("RenderProduct.inputs:width", int(width)),
                ("RenderProduct.inputs:height", int(height)),
                ("CameraRgb.inputs:type", "rgb"),
                ("CameraRgb.inputs:nodeNamespace", f"{ns}/hand_camera"),
                ("CameraRgb.inputs:topicName", "image_raw"),
                ("CameraRgb.inputs:frameId", optical_frame),
                ("CameraRgb.inputs:qosProfile", S.SENSOR_QOS_DEPTH2),
                ("CameraRgb.inputs:frameSkipCount", skip),
                ("CameraInfo.inputs:nodeNamespace", f"{ns}/hand_camera"),
                ("CameraInfo.inputs:topicName", "camera_info"),
                ("CameraInfo.inputs:frameId", optical_frame),
                ("CameraInfo.inputs:qosProfile", S.SENSOR_QOS_DEPTH2),
                ("CameraInfo.inputs:frameSkipCount", skip),
            ],
        },
    )
    log(f"amr gripper reference={usd_path}:{GRIPPER_ASSET_PRIM} prim={gripper.GetPath()} "
        f"tcp_offset={GRIPPER_TCP_OFFSET} rigid_body=off joints_off={list(GRIPPER_JOINTS_OFF)} "
        f"surface_gripper=off colliders_off={colliders}")
    log(f"amr hand_camera prim={camera.GetPath()} resolution={width}x{height} "
        f"rate={S.published_rate(render_hz, skip):.1f}Hz(skip {skip}) "
        f"topics=/{ns}/hand_camera/image_raw,camera_info frame={optical_frame}")
    return str(optical.GetPath())


def publish_tf(stage, root, graph_path, deck_frames, namespace="/amr_1", log=print, extra_static=(),
               extra_dynamic=()):
    """합본의 로봇 링크 TF. **받침대 경로에는 있고 합본에는 없던 것**이다(회차 lap1, 9/21).

    받침대에서는 `ur5_cell.add_camera_and_tf` 가 TF 를 냈는데, 합본은 그 셀을 안 만든다. 그래서
    `amr_1/ur_arm_base_link` 도 `amr_1/deck_slot_*` 도 TF 트리에 **한 줄도 안 나갔고**, 팔이
    `놓을 곳 TF 없음` 으로 ⑤에서 닫혔다. 흡착이 없던 것과 **같은 뿌리**다.

    부모는 `amr_1/base_link` 다 — 그 프레임의 작성자는 base_driver 이고(계약 420–434줄), 우리는 그
    **아래에** 자기 링크를 붙인다(계약 454–458줄). 부모 프레임 이름은 문자열이라 작성자가 겹치지 않는다.
    """
    import usdrt
    import omni.graph.core as og
    from pxr import Sdf, Usd, UsdGeom

    base = stage.GetPrimAtPath(f"{root}/{DECK_PARENT_LINK}")
    arm_base = stage.GetPrimAtPath(f"{root}/{DECK_PARENT_LINK}/{ARM_BASE_FRAME}")
    if not base.IsValid() or not arm_base.IsValid():
        log(f"WARN amr tf not published: need {base.GetPath()} and {ARM_BASE_FRAME}")
        return []

    def name_it(prim, frame):
        prim.CreateAttribute("isaac:nameOverride", Sdf.ValueTypeNames.String).Set(frame)

    ns = namespace.strip("/")
    name_it(base, f"{ns}/{DECK_PARENT_LINK}")        # 부모 프레임 이름만 맞춘다(작성자는 base_driver)
    name_it(arm_base, f"{ns}/{ARM_BASE_FRAME}")
    static = [str(arm_base.GetPath())] + [p for p in extra_static if stage.GetPrimAtPath(p).IsValid()]
    for index, path in enumerate(deck_frames):
        prim = stage.GetPrimAtPath(path)
        if prim.IsValid():
            name_it(prim, f"{ns}/deck_slot_{index + 1}")
            static.append(path)
    dynamic = []
    for prim in Usd.PrimRange(stage.GetPrimAtPath(root)):
        short = prim.GetName()
        if short.startswith("ur_arm_") and short.endswith("_link") and UsdGeom.Xformable(prim):
            name_it(prim, f"{ns}/{short}")
            dynamic.append(str(prim.GetPath()))
    # 손목과 같이 움직이는 프레임(손 카메라 optical). 이름은 부른 쪽이 이미 붙였다.
    dynamic += [p for p in extra_dynamic if stage.GetPrimAtPath(p).IsValid()]

    keys = og.Controller.Keys
    og.Controller.edit(
        {"graph_path": graph_path, "evaluator_name": "execution"},
        {
            keys.CREATE_NODES: [
                ("Tick", "omni.graph.action.OnPlaybackTick"),
                ("Time", "isaacsim.core.nodes.IsaacReadSimulationTime"),
                ("TfStatic", "isaacsim.ros2.bridge.ROS2PublishTransformTree"),
                ("TfDynamic", "isaacsim.ros2.bridge.ROS2PublishTransformTree"),
            ],
            keys.CONNECT: [
                ("Tick.outputs:tick", "TfStatic.inputs:execIn"),
                ("Tick.outputs:tick", "TfDynamic.inputs:execIn"),
                ("Time.outputs:simulationTime", "TfStatic.inputs:timeStamp"),
                ("Time.outputs:simulationTime", "TfDynamic.inputs:timeStamp"),
            ],
            keys.SET_VALUES: [
                ("Time.inputs:resetOnStop", False),
                ("TfStatic.inputs:parentPrim", [usdrt.Sdf.Path(str(base.GetPath()))]),
                ("TfStatic.inputs:targetPrims", [usdrt.Sdf.Path(path) for path in static]),
                ("TfStatic.inputs:topicName", "tf_static"),
                ("TfStatic.inputs:staticPublisher", True),
                ("TfDynamic.inputs:parentPrim", [usdrt.Sdf.Path(str(base.GetPath()))]),
                ("TfDynamic.inputs:targetPrims", [usdrt.Sdf.Path(path) for path in dynamic]),
                ("TfDynamic.inputs:topicName", "tf"),
            ],
        },
    )
    log(f"amr tf parent={ns}/{DECK_PARENT_LINK} static={len(static)} dynamic={len(dynamic)} "
        f"frames={[f'{ns}/{ARM_BASE_FRAME}'] + [f'{ns}/deck_slot_{i + 1}' for i in range(len(deck_frames))]} "
        f"(부모 프레임의 작성자는 base_driver 다 — 우리는 그 아래에 붙인다)")
    return static + dynamic


def _local_translation(stage, parent_path, child_path):
    """`child` 의 원점을 `parent` 기준 좌표로. 못 읽으면 None."""
    from pxr import UsdGeom

    try:
        cache = UsdGeom.XformCache()
        parent_world = cache.GetLocalToWorldTransform(stage.GetPrimAtPath(parent_path))
        child_world = cache.GetLocalToWorldTransform(stage.GetPrimAtPath(child_path))
        local = child_world * parent_world.GetInverse()
        return tuple(float(v) for v in local.ExtractTranslation())
    except Exception:  # 자산 구조를 모르는 채로 만들지 않는다
        return None


def ground_lift(stage, root, log=print):
    """자산을 지면에서 띄울 높이(m). 충돌체 맨 아래가 `GROUND_CLEARANCE` 만큼 뜨도록 한다.

    **런타임 bbox 로 잰다.** 못 재면 탐침 3 에서 읽은 `ASSET_BASE_BOTTOM_Z` 로 물러난다 — 그 값이
    이 자산의 것이라 자산이 바뀌면 틀릴 수 있고, 그래서 재는 쪽이 먼저다.
    """
    bottom = None
    try:
        from pxr import Usd, UsdGeom

        cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default"])
        box = cache.ComputeWorldBound(stage.GetPrimAtPath(root)).ComputeAlignedRange()
        if not box.IsEmpty():
            bottom = float(box.GetMin()[2])
    except Exception as error:  # 재지 못해도 기동은 계속한다
        log(f"amr ground_lift bbox unavailable {type(error).__name__}: {error}")
    if bottom is None:
        bottom = ASSET_BASE_BOTTOM_Z
        log(f"amr ground_lift fell back to the probed bottom {bottom}")
    lift = GROUND_CLEARANCE - bottom
    log(f"amr ground_lift bottom={bottom:.4f} clearance={GROUND_CLEARANCE} lift={lift:.4f} "
        f"(충돌체가 링크 원점보다 아래로 내려가면 지면에 박혀 구동이 붙잡힌다)")
    return lift


def pin_world_joints(stage, root, offset_xyz, log=print):
    """`body0` 가 빈 관절(월드에 박는 뿌리)의 `localPos0` 를 `offset_xyz` 만큼 옮긴다.

    반환 옮긴 것들의 [(경로, 옮긴 뒤 값)]. 하나도 없으면 빈 목록이다 — 그 자산은 프림 이동만으로 놓인다.
    인스턴스 프록시는 못 고치므로 로그에 남기고 건너뛴다(고칠 수 있는 것과 아닌 것을 갈라 보여야 한다).
    """
    from pxr import Gf, Usd, UsdPhysics

    moved = []
    for prim in Usd.PrimRange(stage.GetPrimAtPath(root), Usd.TraverseInstanceProxies()):
        if not prim.IsA(UsdPhysics.Joint):
            continue
        joint = UsdPhysics.Joint(prim)
        if joint.GetBody0Rel().GetTargets():
            continue
        before = joint.GetLocalPos0Attr().Get() or Gf.Vec3f(0.0, 0.0, 0.0)
        if prim.IsInstanceProxy():
            log(f"amr pin skipped {prim.GetPath()} (instance proxy, local_pos0={tuple(before)})")
            continue
        after = Gf.Vec3f(*(float(b) + float(o) for b, o in zip(before, offset_xyz, strict=True)))
        written = joint.GetLocalPos0Attr().Set(after)
        moved.append((str(prim.GetPath()), tuple(float(v) for v in after)))
        log(f"amr pin {prim.GetPath()} local_pos0={tuple(before)}->{tuple(after)} set_ok={bool(written)} "
            f"body1={[str(t) for t in joint.GetBody1Rel().GetTargets()]}")
    return moved


def _find_joint(stage, root, name):
    """이름이 `name` 인 관절 프림. 자산의 계층은 모르므로 **이름으로** 찾는다."""
    from pxr import Usd, UsdPhysics

    for prim in Usd.PrimRange(stage.GetPrimAtPath(root), Usd.TraverseInstanceProxies()):
        if prim.IsA(UsdPhysics.Joint) and prim.GetName() == name:
            return UsdPhysics.Joint(prim)
    return None


def articulation_roots(stage, root):
    """`root` 아래의 ArticulationRootAPI 프림 경로들. **하나여야** 베이스와 팔이 한 articulation 이다."""
    from pxr import Usd, UsdPhysics

    return [str(p.GetPath()) for p in Usd.PrimRange(stage.GetPrimAtPath(root), Usd.TraverseInstanceProxies())
            if p.HasAPI(UsdPhysics.ArticulationRootAPI)]


def dof_indices(dof_names):
    """articulation 의 DOF 이름 목록에서 우리 3축의 자리. 없으면 예외다.

    위치 튜플로 집지 않는다 — 자산이나 빌드 순서가 바뀌면 자리는 바뀌어도 이름은 안 바뀐다(UR5 에서 겪었다).
    """
    missing = [name for name in JOINT_NAMES if name not in dof_names]
    if missing:
        raise KeyError(f"dummy 3축이 articulation 에 없다: {missing} (있는 것: {list(dof_names)})")
    return [list(dof_names).index(name) for name in JOINT_NAMES]


def clamp_to_limits(positions, limits=None):
    """x·y 를 이동 범위 안으로. yaw 는 한계가 없으니 접기만 한다. 리셋 목표를 만들 때 쓴다."""
    limits = limits or DEFAULT_LIMITS
    x, y, yaw = (float(v) for v in positions)
    (xmin, xmax), (ymin, ymax) = limits
    return (min(max(x, xmin), xmax), min(max(y, ymin), ymax), wrap_angle(yaw))


class Suction:
    """합본 팔의 흡착. 받침대 셀(`ur5_cell`)의 것과 **같은 규칙**이고, TCP 를 얻는 방법만 다르다.

    받침대는 Lula FK 로 TCP 를 구한다(IK 가 푸는 프레임과 같아야 하므로). 합본에서는 스테이지가 IK 를
    풀지 않고 **팔 노드가 푼다.** 그리고 비전이 자세 세 벌로 `wrist_3_link` 와 팔 기구학 끝점(`tool0`)이
    **항등**임을 역산했다(9/21). 그래서 **프림 자세를 그대로 TCP 기준으로 쓴다** — FK 를 다시 풀 이유가 없고,
    푸는 쪽이 둘이면 그 둘이 어긋날 수 있다.

    붙이는 것은 받침대와 같이 **가상 부착(텔레포트 추종)** 이다. 물리적 파지가 아니고, 그렇게 기록한다.
    """

    def __init__(self, stage, root, tcp_offset, suck_distance, log=print):
        self.stage = stage
        self.root = root
        self.tcp_offset = tuple(float(v) for v in tcp_offset)
        self.suck_distance = float(suck_distance)
        self.log = log
        self.held = None
        self.held_since = None   # 붙잡은 시각. off 줄에 홀드 길이를 찍는다
        self._prim = None

    def tcp(self):
        """(TCP xyz, (wrist xyz, wrist quat)) — 세계 좌표. 못 읽으면 (None, None)."""
        from . import geometry as G

        try:
            from isaacsim.core.prims import SingleXFormPrim

            if self._prim is None:
                self._prim = SingleXFormPrim(prim_path=f"{self.root}/{TCP_PARENT_LINK}", name="amr_tcp")
            position, quat = self._prim.get_world_pose()
            xyz = tuple(float(v) for v in position)
            rot = tuple(float(v) for v in quat)
            return (G.tcp_world(xyz, rot, self.tcp_offset), (xyz, rot))
        except Exception as error:
            self.log(f"amr suction tcp unavailable {type(error).__name__}: {error}")
            return (None, None)

    def holding(self):
        return self.held is not None

    def suck(self, on, pouch_obj, reason="", now=None):
        """받침대와 같은 거리 규칙. **닿지 않으면 놓치고 그 사실을 로그에 남긴다** — 조용히 붙이지 않는다.

        `reason` 은 **뗀 이유**다. lap9 에서 `suction on` 바로 다음 줄이 `suction off` 였는데(홀드
        0.3 s) 로그만 보고는 **팔이 떼라고 한 것인지 우리가 뗀 것인지 갈리지 않았다.** 한 일만 찍고
        왜는 안 찍은 것이다 — 그 자리를 이 인자가 메운다. `now` 를 주면 붙잡고 있던 시간도 찍는다.
        """
        import math

        from . import geometry as G

        if on and self.held is None and pouch_obj is not None:
            tcp, frame = self.tcp()
            if tcp is None:
                return
            xyz, quat = frame
            position, rotation = pouch_obj.get_world_pose()
            position = tuple(float(v) for v in position)
            rotation = tuple(float(v) for v in rotation)
            distance = math.dist(tcp, position)
            if distance <= self.suck_distance:
                local_xyz, local_quat = G.relative_pose(xyz, quat, position, rotation)
                self.held = (pouch_obj, local_xyz, local_quat)
                self.held_since = now
                self.log(f"amr suction on distance={distance:.4f} reason={reason or 'none'} "
                         f"t={'?' if now is None else f'{now:.3f}'}")
            else:
                self.log(f"amr suction miss distance={distance:.4f} limit={self.suck_distance}")
        elif on and self.held is None:
            self.log(f"amr suction miss target=none limit={self.suck_distance}")
        elif not on and self.held is not None:
            held_s = None if (now is None or self.held_since is None) else now - self.held_since
            self.held = None
            self.held_since = None
            self.log(f"amr suction off reason={reason or 'unknown'} "
                     f"held_s={'?' if held_s is None else f'{held_s:.3f}'} "
                     f"(reason=unknown 이면 이유를 안 넘긴 호출 경로가 남아 있다는 뜻이다)")

    def suck_nearest(self, candidates, reason="", now=None):
        """TCP 에 가장 가까운 후보 하나. 벨트 봉투와 이미 상판에 있는 것이 함께 후보다."""
        import math

        if self.held is not None:
            return
        tcp, _frame = self.tcp()
        if tcp is None:
            return
        placed = [(obj, tuple(float(v) for v in obj.get_world_pose()[0])) for obj in candidates]
        best = min(placed, key=lambda item: math.dist(tcp, item[1]), default=None)
        if best is None:
            self.log(f"amr suction miss target=none candidates=0 limit={self.suck_distance}")
            return
        distance = math.dist(tcp, best[1])
        if distance > self.suck_distance:
            self.log(f"amr suction miss target=none candidates={len(placed)} nearest={distance:.4f} "
                     f"limit={self.suck_distance} tcp={tuple(round(float(v), 5) for v in tcp)} "
                     f"pouch={tuple(round(v, 5) for v in best[1])}")
            return
        self.suck(True, best[0], reason=reason, now=now)

    def follow(self):
        """붙잡은 봉투를 TCP 에 따라 옮긴다. 속도는 0 으로 둔다 — 텔레포트라 관성이 남으면 안 된다."""
        import numpy as np

        from . import geometry as G

        if self.held is None:
            return
        obj, local_xyz, local_quat = self.held
        _tcp, frame = self.tcp()
        if frame is None:
            return
        xyz, quat = frame
        obj.set_world_pose(position=np.array(G.tcp_world(xyz, quat, local_xyz)),
                           orientation=np.array(G.quat_multiply(quat, local_quat)))
        obj.set_linear_velocity(np.zeros(3))
        obj.set_angular_velocity(np.zeros(3))


class TrayClip:
    """트레이 홀더: 칸에 놓여 멈춘 봉투를 트레이에 붙이고(클립), 팔이 그 봉투를 잡으면 푼다.

    실물 트레이의 봉투 홀더(칸 클립)에 대응한다. 재범 9/24 20:5x "밀림 확실히 끝내기". 트레이 고무 매트(μ 1.0)로도
    1.0 m/s 곡선(원심 ≈ 0.16 m/s²)에서 3.4 cm 밀렸다(737fee9 Play/Stop) — 마찰로 설명이 안 되는 크기다.

    **조인트 프림을 실행 중에 만들지 않는다**(프림 추가·삭제가 PhysX tensor view 를 깨뜨린 적이 있다, 9/17).
    흡착(`Suction.follow`)과 같은 텔레포트 추종이다: 매 틱 트레이(base_link) 자세 × 붙인 순간의 상대 자세로
    옮기고 속도를 0 으로 둔다. 벨트 끝 집기·보관함 놓기의 기하는 그대로다 — 붙이는 것은 칸 안에서 멈춘 뒤뿐이다.
    """

    def __init__(self, runtime, local_slots, slot_accept, still_speed, log=print):
        self.runtime = runtime
        self.local_slots = list(local_slots)
        self.slot_accept = slot_accept
        self.still_speed = still_speed
        self.log = log
        self.clips = {}   # id(obj) -> (obj, order_id, local_xyz, local_quat)

    def _base_frame(self):
        try:
            position, quat = self.runtime._pose_reader(
                f"{self.runtime.root}/{DECK_PARENT_LINK}", "amr_base_link_read").get_world_pose()
        except Exception:  # 센서·추종이 멈추면 안 된다
            return None
        return tuple(float(v) for v in position), tuple(float(v) for v in quat)

    def update(self, pouches, held_obj, speed_of, now=None):
        """`pouches` = [(order_id, obj)] (쓰는 중인 봉투). 붙은 것은 따라 옮기고, 새로 칸에 멈춘 것은 붙인다."""
        try:
            import numpy as np

            array, zeros = np.array, np.zeros
        except ImportError:
            # CI usd-core 잡에는 numpy 가 없다(run 36072192506). Isaac 에는 늘 있다 — 시험의 가짜 prim 은 튜플을 받는다.
            array, zeros = tuple, (lambda n: (0.0,) * n)

        from . import geometry as G
        from . import truth_sensors as sensorlib

        frame = self._base_frame()
        if frame is None:
            return
        base_xyz, base_quat = frame
        slots = None   # 한 번만 읽는다
        for order_id, obj in pouches:
            key = id(obj)
            clipped = self.clips.get(key)
            if clipped is not None:
                if held_obj is obj:
                    del self.clips[key]
                    self.log(f"tray clip off order_id={order_id} reason=picked "
                             f"t={'?' if now is None else f'{now:.3f}'}")
                    continue
                _obj, _order, local_xyz, local_quat = clipped
                obj.set_world_pose(position=array(G.tcp_world(base_xyz, base_quat, local_xyz)),
                                   orientation=array(G.quat_multiply(base_quat, local_quat)))
                obj.set_linear_velocity(zeros(3))
                obj.set_angular_velocity(zeros(3))
                continue
            if held_obj is obj:
                continue
            position, quat = obj.get_world_pose()
            world = tuple(float(v) for v in position)
            if slots is None:
                slots = self.runtime.slots_in_world(self.local_slots)
            if not any(sensorlib.in_slot(world, slot, self.slot_accept) for slot in slots):
                continue
            speed = speed_of(obj)
            if speed is not None and speed > self.still_speed:
                continue
            local_xyz, local_quat = G.relative_pose(base_xyz, base_quat, world, tuple(float(v) for v in quat))
            self.clips[key] = (obj, order_id, local_xyz, local_quat)
            self.log(f"tray clip on order_id={order_id} xyz=({world[0]:.4f}, {world[1]:.4f}, {world[2]:.4f}) "
                     f"t={'?' if now is None else f'{now:.3f}'}")

    def release_all(self, reason):
        for _obj, order_id, _xyz, _quat in self.clips.values():
            self.log(f"tray clip off order_id={order_id} reason={reason}")
        self.clips.clear()


class Runtime:
    """스테이지가 쓰는 얇은 껍데기: articulation 을 잡고, 속도를 적용하고, 상태를 읽는다.

    판단은 전부 위의 순수 함수에 있다(L1 이 잡는다). 여기서는 Isaac 호출만 한다 — 이 클래스는 L1 미검증이다.
    """

    def __init__(self, world, root, start_xy, limits=None, drive=None, log=print, articulation_path=None,
                 start_yaw=0.0):
        self.world = world
        self.root = root
        #: articulation 뿌리의 경로. 상자는 `{root}/root_joint`, 합본은 자산이 정한 자리다 — **하드코딩하지 않는다.**
        self.articulation_path = articulation_path or f"{root}/root_joint"
        self.start = (float(start_xy[0]), float(start_xy[1]), wrap_angle(float(start_yaw)))
        self.limits = limits or DEFAULT_LIMITS
        self.drive = drive or DEFAULT_DRIVE
        self.log = log
        self.articulation = None
        self.indices = None
        self._action = None
        self._last_command_s = None
        self._pose_readers = {}

    def _pose_reader(self, path, name):
        """경로마다 `SingleXFormPrim` 을 **한 번만** 만든다.

        9/23 5a59776 py-spy: 부를 때마다 새로 만들던 `slots_in_world` 한 줄이 루프 샘플의 16%(467/2950)였다.
        만들 때마다 stage 를 다시 찾고 xform 속성을 다시 쓴다. 읽는 값은 같다."""
        reader = self._pose_readers.get(path)
        if reader is None:
            from isaacsim.core.prims import SingleXFormPrim

            reader = self._pose_readers[path] = SingleXFormPrim(prim_path=path, name=name)
        return reader

    def attach(self):
        """리셋 뒤에 부른다. DOF 이름이 생기고 나서야 자리를 알 수 있다."""
        from isaacsim.core.prims import SingleArticulation
        from isaacsim.core.utils.types import ArticulationAction

        if self.articulation is None:
            self.articulation = self.world.scene.add(SingleArticulation(prim_path=self.articulation_path,
                                                                        name="amr_base"))
        self.articulation.initialize()
        self._action = ArticulationAction
        self.indices = dof_indices(self.articulation.dof_names)
        # 합본이면 팔 6관절도 같은 articulation 에 있다. 없으면 빈 목록(상자 구성).
        names = list(self.articulation.dof_names)
        self.arm_indices = ([names.index(n) for n in ARM_JOINT_NAMES]
                            if all(n in names for n in ARM_JOINT_NAMES) else [])
        # 놓는 방법 1·2 가 안 먹었으면 여기서 마지막으로 올린다. 안 쓰면 아무 일도 안 한다.
        self.ensure_height(GROUND_CLEARANCE)
        self.log_base_pose()
        self.log(f"amr attached articulation={self.articulation_path} "
                 f"dof_names={list(self.articulation.dof_names)} "
                 f"indices={self.indices} arm_indices={self.arm_indices} "
                 f"limits={self.limits} drive={self.drive}")
        return self

    def apply(self, velocities, now_s):
        """속도 셋(x, y, yaw)을 적용한다. 명령이 끊기면 0 이다(계약 5절) — 그 판단은 부르는 쪽이 한다."""
        import numpy as np

        self._last_command_s = now_s
        self.articulation.apply_action(self._action(joint_velocities=np.array([float(v) for v in velocities]),
                                                    joint_indices=np.array(self.indices)))

    def read(self):
        """(positions, velocities) 를 우리 축 순서로. 못 읽으면 (None, None)."""
        positions = self.articulation.get_joint_positions()
        velocities = self.articulation.get_joint_velocities()
        if positions is None or velocities is None:
            return (None, None)
        return ([float(positions[i]) for i in self.indices], [float(velocities[i]) for i in self.indices])

    def base_world_pose(self):
        """몸체의 **세계** (x, y, yaw). 못 읽으면 None.

        **`read()` 와 다르다.** `read()` 가 돌려주는 것은 dummy 관절값이고 그 원점은 **출발 도크**다
        (실습24 에서 같은 모양을 한 번 겪었다). 세계 좌표로 쓰려면 출발 자리를 더해야 한다.

        lap10 (9/21) 에서 인식표 센서가 관절값을 그대로 세계로 썼다: 참값이 `bed_a1`(13.15, −0.39)
        인데 센서는 (8.55, −0.96) = **참값 − 출발 도크(4.60, 0.55)** 를 봤고, 그래서 `거리 4.6363 > 0.35`
        로 어느 구역도 못 맞혔다. ⑦ `AUTH_FAIL` 이 거기서 났다. **숫자가 그럴듯해서 조용했다** —
        자리를 못 찾은 것이지 형식이 틀린 것이 아니었다.

        yaw 관절값은 세계 방향이다. 초기 도크 yaw 를 다시 더하지 않는다.
        """
        positions, _velocities = self.read()
        if positions is None:
            return None
        return (positions[0] + self.start[0], positions[1] + self.start[1], positions[2])

    def ensure_height(self, wanted_z, log=None):
        """몸체가 안 올라갔으면 **초기화 뒤에** 직접 올린다. 올렸으면 True.

        놓는 방법이 셋이고 자산마다 먹는 것이 다르다:
        1. 프림 이동 — 합본이 먹는 쪽(회차 682fb30·807102d 로 가렸다)
        2. 앵커(`localPos0`) — 받침대 UR5 자산이 먹는 쪽
        3. **초기화 뒤 world pose 쓰기** — 여기. 1·2 는 물리가 파싱하기 **전**에 거는 방식이라,
           자산이 둘 다 무시하면 파싱 **뒤**에 옮기는 수밖에 없다.

        3번은 되도록 안 쓴다 — 물리가 이미 상태를 잡은 뒤에 건드리는 것이라 조용한 부작용이 생기기 쉽다.
        그래서 **필요할 때만** 쓰고, 썼다는 것을 로그에 남긴다.
        """
        log = log or self.log
        try:
            from isaacsim.core.prims import SingleXFormPrim

            prim = SingleXFormPrim(prim_path=f"{self.root}/{DECK_PARENT_LINK}", name="amr_height_check")
            position, _quat = prim.get_world_pose()
            current = float(position[2])
            if current >= wanted_z - 1e-6:
                return False
            import numpy as np

            self.articulation.set_world_pose(position=np.array([float(position[0]), float(position[1]),
                                                                float(position[2]) + (wanted_z - current)]))
            log(f"WARN amr height_fixed_after_init from_z={current:.4f} to_z={wanted_z:.4f} "
                "(프림 이동도 앵커도 안 먹었다 — 파싱 뒤에 직접 올렸다)")
            return True
        except Exception as error:
            log(f"WARN amr ensure_height failed {type(error).__name__}: {error}; 몸체가 지면에 박힌 채로 돈다")
            return False

    def log_base_pose(self):
        """몸체의 **실제** 세계 자세를 찍는다. 들어올림이 먹었는지 이 한 줄로 갈린다.

        회차 807102d 에서 앵커 z 를 올렸는데 몸체가 안 올라갔다 — 그때 이 줄이 있었으면 로그만 보고
        알았을 것이다. 놓는 방식이 자산마다 다르므로 **결과를 재서 남긴다.**
        """
        try:
            from isaacsim.core.prims import SingleXFormPrim

            prim = SingleXFormPrim(prim_path=f"{self.root}/{DECK_PARENT_LINK}", name="amr_base_pose_log")
            position, quat = prim.get_world_pose()
            self.log(f"amr base_pose pos={tuple(round(float(v), 4) for v in position)} "
                     f"quat_wxyz={tuple(round(float(v), 4) for v in quat)} "
                     f"expected_z_at_least={GROUND_CLEARANCE} (충돌체 바닥이 지면 위여야 구동이 안 붙잡힌다)")
        except Exception as error:  # 진단이 기동을 막으면 안 된다
            self.log(f"amr base_pose unavailable {type(error).__name__}: {error}")

    def read_all(self):
        """(이름들, 위치들, 속도들) — 베이스 3 + (있으면) 팔 6.

        계약 97줄이 `/amr_1/joint_states` 를 **한 메시지에 dummy 3 + UR5 6** 으로 정한다. 합본은 한
        articulation 이라 한 번에 읽힌다 — 상자 구성에서 발행자가 둘이던 것이 여기서 하나가 된다.
        """
        positions = self.articulation.get_joint_positions()
        velocities = self.articulation.get_joint_velocities()
        if positions is None:
            return (None, None, None)
        order = list(self.indices) + list(self.arm_indices)
        names = list(JOINT_NAMES) + (list(ARM_JOINT_NAMES) if self.arm_indices else [])
        out_positions = [float(positions[i]) for i in order]
        out_positions[2] = wrap_angle(out_positions[2])  # yaw 는 접어서 낸다(base_driver 가 그대로 쓴다)
        out_velocities = None if velocities is None else [float(velocities[i]) for i in order]
        return (names, out_positions, out_velocities)

    def slots_in_world(self, local_slots):
        """base_link 로컬 칸 중심을 **지금 자세의** 세계 좌표로. 못 읽으면 로컬 값을 그대로 돌려준다.

        빌드 때 세계 좌표를 굳히면 AMR 이 움직인 뒤 "상판 칸 안인가" 판정이 그만큼 틀린다 — 조용히.
        `ur5_cell.slot_centres` 와 같은 이유이고, 합본에서는 **실제로** 움직인다.
        """
        path = f"{self.root}/{DECK_PARENT_LINK}"
        try:
            position, quat = self._pose_reader(path, "amr_base_link_read").get_world_pose()
            origin = tuple(float(v) for v in position)
            w, x, y, z = (float(v) for v in quat)
            yaw = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
            cos, sin = math.cos(yaw), math.sin(yaw)
            out = []
            for sx, sy, sz in local_slots:
                out.append((origin[0] + sx * cos - sy * sin, origin[1] + sx * sin + sy * cos, origin[2] + sz))
            return out
        except Exception as error:  # 센서가 멈추면 안 된다
            self._pose_readers.pop(path, None)  # 다음 호출에서 새로 만든다
            self.log(f"amr slots_in_world fell back to local {type(error).__name__}: {error}")
            return list(local_slots)

    def world_to_arm_base(self, world_xyz):
        """세계 좌표를 **지금의** 팔 밑동 프레임으로. 못 읽으면 None.

        받침대에서는 밑동이 월드 고정이고 축이 월드와 나란해서 뺄셈 하나였다. 합본은 **움직이고 축도
        `Rz(pi)` 로 돌아 있다.** 뺄셈만 하면 회차 lap2 처럼 **받침대 때와 똑같은 숫자**가 나가고,
        프레임 이름만 합본 것이라 아무도 못 알아챈다 — 팔은 그 값으로 엉뚱한 데를 짚는다.
        """
        path = f"{self.root}/{DECK_PARENT_LINK}/{ARM_BASE_FRAME}"
        try:
            position, quat = self._pose_reader(path, "amr_arm_base_read").get_world_pose()
            ox, oy, oz = (float(v) for v in position)
            w, x, y, z = (float(v) for v in quat)
            yaw = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
            dx, dy, dz = (float(world_xyz[0]) - ox, float(world_xyz[1]) - oy, float(world_xyz[2]) - oz)
            cos, sin = math.cos(-yaw), math.sin(-yaw)
            return (dx * cos - dy * sin, dx * sin + dy * cos, dz)
        except Exception as error:  # 센서가 멈추면 안 된다
            self._pose_readers.pop(path, None)
            self.log(f"amr world_to_arm_base unavailable {type(error).__name__}: {error}")
            return None

    def apply_arm_positions(self, targets):
        """팔 관절 위치 목표를 적용한다. `targets` 는 {이름: 값} 이고 **이름으로** 고른다.

        계약 186줄: "자기 조인트 이름만. 다른 쪽 이름이 섞이면 isaac 이 버린다." 모르는 이름은 조용히
        버리지 않고 돌려준다 — 부르는 쪽이 셀 수 있어야 한다.
        """
        import numpy as np

        if not self.arm_indices:
            return (0, list(targets))
        names = list(self.articulation.dof_names)
        chosen, unknown = [], []
        for name, value in targets.items():
            if name in ARM_JOINT_NAMES and name in names:
                chosen.append((names.index(name), float(value)))
            else:
                unknown.append(name)
        if chosen:
            self.articulation.apply_action(self._action(
                joint_positions=np.array([v for _i, v in chosen]),
                joint_indices=np.array([i for i, _v in chosen])))
        return (len(chosen), unknown)

    def reset(self):
        """3축을 출발 자세로. 속도 드라이브라 위치를 붙잡지 않으니 위치를 직접 쓴다."""
        import numpy as np

        indices = np.array(self.indices)
        zero = np.array([0.0, 0.0, 0.0])
        self.articulation.set_joint_positions(np.array([0.0, 0.0, self.start[2]]), joint_indices=indices)
        self.articulation.set_joint_velocities(zero, joint_indices=indices)
        self.articulation.apply_action(self._action(joint_velocities=zero, joint_indices=indices))
        self._last_command_s = None
        self.log(f"amr reset joint_xy=zero start_xy={self.start[:2]} start_yaw={self.start[2]:.6f}")
