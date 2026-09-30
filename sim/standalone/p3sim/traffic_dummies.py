"""병원 로비·복도를 도는 가짜 AMR(재범 채택 9/24 부가 장면). Isaac 임포트는 늦게 한다.

진짜 AMR(센서·Nav2)이 사람·다른 로봇이 다니는 병원에서 돈다는 장면을 만든다. 더미는 **주행 스택이 없다** —
고정 루프를 0.5 m/s 로 돌고, 진짜 AMR 이 `STOP_DISTANCE` 안이면 서고, `RESUME_WAIT` 이 지나 `RESUME_DISTANCE`
밖으로 멀어지면 다시 간다(히스테리시스, 회차69 떨림). 판단은 스테이지 안
거리 검사뿐이다(ROS 없음).

- **모양**: AMR 합본 USD 를 참조하되 **물리를 다 끈다**(강체·관절·articulation·충돌). 부품 가리지 않고 전체를
  노란 단색으로 덮는다(재범 9/24). 위에 "DUMMY" 판.
- **충돌**: 차체 크기의 기구학(kinematic) 상자 하나를 따로 옮긴다. 진짜 AMR 과 닿으면 기존 접촉 로그에 잡힌다 —
  그래서 프림은 `/Amr` 밖(`…/Traffic/dummy_N`)에 둔다. 상자는 안 보이게 두고, 라이다는 시각 메시(노란 합본)를 본다.
- **경로**: `LOOPS` 의 사각 루프. 배송 경로에서 `ROUTE_CLEARANCE` 밖으로만 돈다(회차107 접촉, 오프라인 지도·routes
  대조, sim/tests). 서도 경로를 막지 않는다.
- **예산**(최적화 9/24): rtf −0.02 안. 틱마다 더미당 자세 쓰기 둘과 거리 계산뿐이다. 회차로 판정(여기서는 못 본다).

`step` 과 경로 검사는 순수 함수라 sim/tests 가 본다. `Dummies`(Isaac) 는 L3 미실행이다.
"""

import math

#: 도는 속도(m/s)와 멈추는 거리(m, 진짜 AMR 몸체 중심까지).
SPEED = 0.5
STOP_DISTANCE = 1.5
#: 재개 거리(m)와 멈춘 뒤 최소 대기(s). 마클1 회차69: 한 경계(1.5 m)로 서고 가면 진짜 AMR 이 그 언저리에 있을 때
#: stop↔go 가 10번 번갈아 떨었다. 멈춤 1.5 m / 재개 2.2 m 히스테리시스 + 멈춘 뒤 2 s 는 그대로 선다(작전 9/25).
RESUME_DISTANCE = 2.2
RESUME_WAIT = 2.0
#: 사각 루프(시계 반대), 병원 좌표. 몸체 중심 경로다. 변 위 `hospital_nav.PATH_RADIUS`, 모서리(제자리 회전)
#: `TURN_RADIUS` 원이 지도상 비어 있다(sim/tests, `loop_problems`).
#: **루프는 배송 경로와 만나지 않는다**(`ROUTE_CLEARANCE` 밖, sim/tests). 마클1 회차107: 로비 루프 윗변(y 3.2)이
#: 적재장·도크↔간호사실 선과 0.1 m 안에서 길게 겹쳐, 규칙대로 선 더미(4.52, 3.20)가 배송 경로 위에 서 있었다.
#: 진짜 AMR 은 라이다로 보고 감속(100→54 %)했지만 감속기는 50 % 아래로 안 내리고 경로도 안 바꾼다 —
#: 트레이가 더미에 12 s 닿고 컨트롤러가 "Failed to make progress" 로 멈췄다(#240 5825869861·5825910510).
#: 그래서 더미는 경로 옆에서만 돈다. 진짜 AMR 이 지나가면(1.5 m 안) 경로 밖에서 선다.
#: - lobby: 간호사실 앞 로비 남쪽. 윗변(y 1.2)이 로비 배송선들과 1.6 m 떨어져 나란하다.
#: - corridor_a: A 병동 복도. 아랫변(y 8.5)이 A 병동 배송선과 1.3 m 떨어져 나란히 간다 — 멈춤 거리(1.5 m)보다
#:   좁아 진짜 AMR 이 지나가면 선다. 서쪽은 기둥(12.5, 9.5)을 피해 x 13.2 부터다.
LOOPS = (
    ("lobby", ((1.5, -1.2), (4.8, -1.2), (4.8, 1.2), (1.5, 1.2))),
    ("corridor_a", ((13.2, 8.5), (18.5, 8.5), (18.5, 9.5), (13.2, 9.5))),
)
#: 더미 중심과 배송 경로(진짜 AMR 중심선) 사이 최소 거리(m): 진짜 AMR 경로 반경(`hospital_nav.PATH_RADIUS`
#: 0.56, 반길이 + 받침 + 여유) + 더미 반길이(0.47) + 0.05. 이보다 가까운 자리에 서면 경로를 막는다.
ROUTE_CLEARANCE = 1.08
#: 차체 크기의 충돌 상자(m). 합본 몸체(`hospital_nav.BODY_LENGTH`·`BODY_WIDTH`)와 같은 바닥, 높이는 상판까지.
COLLIDER_HEIGHT = 0.45
#: 노란 단색(데코 노랑과 같은 값).
YELLOW = (0.98, 0.80, 0.10)
#: "DUMMY" 판 크기(m)와 몸체 윗면에서 띄우는 높이(m).
LABEL_SIZE = (0.60, 0.15)
LABEL_LIFT = 0.02


def loop_length(points):
    return sum(math.dist(points[i], points[(i + 1) % len(points)]) for i in range(len(points)))


def pose_at(points, s):
    """루프 위 호 길이 `s` 의 (x, y, yaw). yaw 는 그 변의 진행 방향."""
    total = loop_length(points)
    s %= total
    for i in range(len(points)):
        a, b = points[i], points[(i + 1) % len(points)]
        length = math.dist(a, b)
        if s <= length:
            t = s / length
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, math.atan2(b[1] - a[1], b[0] - a[0]))
        s -= length
    a, b = points[0], points[1]
    return (a[0], a[1], math.atan2(b[1] - a[1], b[0] - a[0]))


def step(points, s, dt, real_xys, stopped=False, held=0.0, speed=SPEED, stop_distance=STOP_DISTANCE,
         resume_distance=RESUME_DISTANCE, resume_wait=RESUME_WAIT):
    """한 틱. (새 s, (x, y, yaw), 멈췄나, 멈춰 있은 시간 s).

    가는 중이면 가장 가까운 진짜 AMR 이 `stop_distance` 안일 때 선다. 서 있으면 `resume_wait` 이상 지났고
    가장 가까운 AMR 이 `resume_distance` 밖일 때 다시 간다(그 틱부터 움직인다). 위치를 모르는 AMR(None)은 뺀다.
    """
    here = pose_at(points, s)
    near = [math.dist(here[:2], other) for other in real_xys if other is not None]
    nearest = min(near, default=math.inf)
    if stopped:
        held += max(0.0, dt)
        if held < resume_wait or nearest < resume_distance:
            return s, here, True, held
    elif nearest < stop_distance:
        return s, here, True, 0.0
    s = (s + speed * max(0.0, dt)) % loop_length(points)
    return s, pose_at(points, s), False, 0.0


def plan(count):
    """앞에서 `count` 개의 (이름, 루프). 루프보다 많이 달라면 ValueError — 같은 루프에 둘을 겹쳐 두지 않는다."""
    if count < 0 or count > len(LOOPS):
        raise ValueError(f"--traffic-dummies 는 0-{len(LOOPS)} 이다: {count}")
    return list(LOOPS[:count])


def loop_problems(grid, points, radius, turn_radius, step_m=0.05):
    """루프가 지도 빈 곳에 있는가. 변 위는 `radius`, 모서리(제자리 회전)는 `turn_radius` 원 안이 비어야 한다.

    원은 8 방향 + 중심만 본다(지도 칸 0.05 m 보다 촘촘히는 안 본다). 문제 목록을 돌려준다(비면 통과).
    """
    problems = []

    def disk_free(x, y, r):
        for k in range(8):
            a = k * math.pi / 4
            if grid.is_blocked(x + r * math.cos(a), y + r * math.sin(a)):
                return False
        return not grid.is_blocked(x, y)

    for i in range(len(points)):
        a, b = points[i], points[(i + 1) % len(points)]
        n = max(1, int(math.dist(a, b) / step_m))
        for k in range(n + 1):
            x = a[0] + (b[0] - a[0]) * k / n
            y = a[1] + (b[1] - a[1]) * k / n
            if not disk_free(x, y, radius):
                problems.append(f"edge {i} at ({x:.2f}, {y:.2f})")
                break
        if not disk_free(a[0], a[1], turn_radius):
            problems.append(f"corner {i} at {a}")
    return problems


class Dummies:
    """Isaac 쪽. 더미 N 대를 세우고 `update` 로 매 틱 옮긴다. 실패해도 회차를 세우지 않는다(경고 한 번)."""

    def __init__(self, stage, root, count, amr_usd, body_length, body_width, label_image, log=print):
        from isaacsim.core.prims import SingleRigidPrim, SingleXFormPrim
        from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade

        from . import scene

        self._log = log
        self._warned = False
        self._items = []
        UsdGeom.Xform.Define(stage, root)
        material = UsdShade.Material.Define(stage, f"{root}/Looks/Yellow")
        shader = UsdShade.Shader.Define(stage, f"{root}/Looks/Yellow/Surface")
        shader.CreateIdAttr("UsdPreviewSurface")
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*YELLOW))
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.6)
        material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
        for index, (name, points) in enumerate(plan(count), start=1):
            base = f"{root}/dummy_{index}"
            visual = f"{base}_visual"
            model = stage.DefinePrim(visual, "Xform")
            model.GetReferences().AddReference(str(amr_usd))
            stripped = strip_physics(stage, model)
            UsdShade.MaterialBindingAPI.Apply(model).Bind(material, UsdShade.Tokens.strongerThanDescendants)
            box = UsdGeom.Cube.Define(stage, f"{base}_collider")
            box.CreateSizeAttr(1.0)
            box.AddScaleOp().Set(Gf.Vec3f(body_length, body_width, COLLIDER_HEIGHT))
            box.CreateVisibilityAttr(UsdGeom.Tokens.invisible)
            UsdPhysics.CollisionAPI.Apply(box.GetPrim())
            rigid = UsdPhysics.RigidBodyAPI.Apply(box.GetPrim())
            rigid.CreateKinematicEnabledAttr(True)
            bounds = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"]).ComputeWorldBound(
                model).ComputeAlignedRange()
            lift = -float(bounds.GetMin()[2])        # 자산 원점이 바닥보다 위·아래일 수 있다 — 바닥에 맞춘다
            top = float(bounds.GetMax()[2])
            label = f"{visual}/DummyLabel"
            scene.add_top_texture(stage, label, label_image, LABEL_SIZE, top + LABEL_LIFT)
            x, y, yaw = pose_at(points, 0.0)
            self._items.append({"name": name, "points": points, "s": 0.0, "stopped": False,
                                "who": f"dummy_{index}", "xy": (x, y), "yaw": yaw,
                                "visual": SingleXFormPrim(prim_path=visual, name=f"traffic_{index}_visual"),
                                "collider": SingleRigidPrim(prim_path=f"{base}_collider",
                                                            name=f"traffic_{index}_collider"),
                                "z": COLLIDER_HEIGHT / 2.0, "lift": lift})
            log(f"traffic dummy_{index} loop={name} start=({x:.2f}, {y:.2f}, {math.degrees(yaw):.0f}°) "
                f"speed={SPEED} stop_within={STOP_DISTANCE} m resume_beyond={RESUME_DISTANCE} m after {RESUME_WAIT} s "
                f"stripped={stripped} top_z={top:.2f} lift={lift:.3f} "
                f"collider={base}_collider (kinematic, invisible)")

    def positions(self):
        """{dummy_i: (x, y)} — 마지막으로 옮긴 자리(`encounters` 가 쓴다)."""
        return {item["who"]: item["xy"] for item in self._items}

    def poses(self):
        """[(dummy_i, x, y, yaw)] — 마지막으로 옮긴 자리(관제 웹 `/isaac/fleet/poses`)."""
        return [(item["who"], *item["xy"], item["yaw"]) for item in self._items]

    def update(self, dt, real_xys):
        """매 틱. 진짜 AMR (x, y) 목록을 받아 더미를 옮긴다. 멈춤·재개가 바뀔 때만 로그 한 줄."""
        import numpy as np

        try:
            for item in self._items:
                item["s"], (x, y, yaw), stopped, item["held"] = step(item["points"], item["s"], dt, real_xys,
                                                                     item["stopped"], item.get("held", 0.0))
                item["xy"], item["yaw"] = (x, y), yaw
                if stopped != item["stopped"]:
                    item["stopped"] = stopped
                    self._log(f"traffic {item['name']} {'stop' if stopped else 'go'} at ({x:.2f}, {y:.2f})")
                quat = np.array((math.cos(yaw / 2.0), 0.0, 0.0, math.sin(yaw / 2.0)))
                item["visual"].set_world_pose(position=np.array((x, y, item["lift"])), orientation=quat)
                item["collider"].set_world_pose(position=np.array((x, y, item["z"])), orientation=quat)
        except Exception as error:  # 촬영 소품이다 — 한 바퀴를 세우지 않는다
            if not self._warned:
                self._warned = True
                self._log(f"WARN traffic dummies update failed {type(error).__name__}: {error}")


def strip_physics(stage, model):
    """참조한 합본의 물리를 끈다: 강체·충돌·관절 끄기, articulation 루트 빼기. 반환 {종류: 개수}."""
    from pxr import Sdf, Usd, UsdPhysics

    counts = {"rigid": 0, "collision": 0, "joint": 0, "articulation": 0, "uninstanced": 0}
    # 인스턴스 안(프로토타입)의 물리는 덮어쓸 수 없다. 인스턴스를 먼저 풀어 끌 수 있게 한다.
    # 푼 프림 아래에 또 인스턴스가 나올 수 있어 더 없을 때까지 돈다.
    while True:
        instances = [prim for prim in Usd.PrimRange(model) if prim.IsInstance()]
        if not instances:
            break
        for prim in instances:
            prim.SetInstanceable(False)
            counts["uninstanced"] += 1
    for prim in Usd.PrimRange(model):
        if prim.HasAPI(UsdPhysics.RigidBodyAPI):
            prim.CreateAttribute("physics:rigidBodyEnabled", Sdf.ValueTypeNames.Bool).Set(False)
            counts["rigid"] += 1
        if prim.HasAPI(UsdPhysics.CollisionAPI):
            prim.CreateAttribute("physics:collisionEnabled", Sdf.ValueTypeNames.Bool).Set(False)
            counts["collision"] += 1
        if prim.IsA(UsdPhysics.Joint):
            prim.CreateAttribute("physics:jointEnabled", Sdf.ValueTypeNames.Bool).Set(False)
            counts["joint"] += 1
        if prim.HasAPI(UsdPhysics.ArticulationRootAPI):
            prim.RemoveAPI(UsdPhysics.ArticulationRootAPI)
            counts["articulation"] += 1
    return counts
