"""병원 복도를 가로지르는 보행자(재범 결정 9/25 — 안전판 v0.5.0 회피 장면). Isaac 임포트는 늦게 한다.

가짜 AMR(`traffic_dummies`)과 같은 방식이되 두 가지가 다르다.

- **AMR 가까이서는 선다**(9/25 회차70 수정). 0.8 m/s 로 선분을 왕복하다가 진짜 AMR 이 1.5 m 안이면 서고, 2 s 이상
  지나 2.2 m 밖이면 다시 간다 — 더미와 같은 규칙(`traffic_dummies.step`). 회차70 에서 멈추지 않는 보행자가 로비
  x 5.5 에서 AMR 경로를 정면으로 가로질러 AMR 본체와 두 번 닿았다(sim 252·397). 1.5–3 m 에서의 회피(감속)는
  그대로 AMR 감속기 몫이다 — 보행자는 그보다 안쪽에서만 선다.
- **경로 선택**: 왕복 선은 복도의 넓은 구간에서 배송 경로를 **비스듬히**(45° 넘게) 가로지르게 골랐고, 적재·도크·
  병상 접근점·문 앞과 더미 루프에서 떨어뜨렸다(sim/tests). 왕복 주기는 AMR 통과 시각과 무관하다.

모양은 걷는 사람 크기의 캡슐(몸통) + 구(머리), 옷 색 파랑/초록. 글자 없음. 캡슐이 기구학(kinematic) 강체이자
충돌체라 라이다·접촉 로그에 보인다. 프림은 `…/Pedestrians/ped_N`.

`pose`·경로 검사는 순수 함수라 sim/tests 가 본다. `Pedestrians`(Isaac) 는 L3 미실행이다.
"""

import math

#: 걷는 속도(m/s). 멈추지 않는다.
SPEED = 0.8
#: 사람 크기(m): 몸통 캡슐 반지름·원통 높이, 머리 반지름. 서 있는 키 약 1.7 m.
BODY_RADIUS = 0.20
BODY_HEIGHT = 1.00
HEAD_RADIUS = 0.12
#: 경로 검사에 쓰는 사람 둘레(m, 몸통 + 팔 흔들림 여유).
CLEARANCE_RADIUS = 0.35
#: 옷 색(파랑, 초록)과 머리(살색).
COLORS = ((0.15, 0.35, 0.80), (0.12, 0.60, 0.30))
SKIN = (0.85, 0.68, 0.55)
#: 왕복 선(병원 좌표, 끝점 둘). 복도 넓은 구간에서 배송 경로를 가로지른다.
#: - lobby: 간호사실 북쪽 로비의 사선(5.95, 5.67)–(7.25, 7.93). A 병동 배송선을 55° 로 비스듬히 가로지르고, 교차점은
#:   경로 꺾임점에서 1 m 밖, 정차 자리에서 3.2 m 밖, 회차70 접촉 자리(5.6, 4.5)에서 2.5 m 밖이다(오프라인 탐색).
#:   9/25 까지의 x 5.5 세로선은 AMR 이 간호사실로 꺾어 드는 자리를 정면으로 막았다(회차70 접촉 2회).
#: - ward_crossing: 간호사실과 병동 사이 복도(x 16.5). B 병동 사선(y ≈ 3.9)과 A 병동 선(y ≈ 6.3)을 가로지른다.
#:   더미 복도 루프(y ≥ 8.1)보다 0.9 m 남쪽에서 돌아선다.
LINES = (
    ("lobby", ((5.95, 5.67), (7.25, 7.93))),
    ("ward_crossing", ((16.5, 3.2), (16.5, 7.2))),
)


def plan(count):
    """앞에서 `count` 개의 (이름, (a, b)). 선보다 많이 달라면 ValueError — 한 선에 둘을 겹쳐 두지 않는다."""
    if count < 0 or count > len(LINES):
        raise ValueError(f"--pedestrians 는 0-{len(LINES)} 이다: {count}")
    return list(LINES[:count])


def walk(a, b, s, dt, real_xys, stopped=False, held=0.0):
    """한 틱. (새 s, (x, y, yaw, 편도), 멈췄나, 멈춰 있은 시간). 멈춤·재개 규칙은 더미와 같다."""
    from . import traffic_dummies as T

    here = pose(a, b, s)
    near = min((math.dist(here[:2], other) for other in real_xys if other is not None), default=math.inf)
    if stopped:
        held += max(0.0, dt)
        if held < T.RESUME_WAIT or near < T.RESUME_DISTANCE:
            return s, here, True, held
    elif near < T.STOP_DISTANCE:
        return s, here, True, 0.0
    s += SPEED * max(0.0, dt)
    return s, pose(a, b, s), False, 0.0


def pose(a, b, s):
    """왕복 선 위 걸은 거리 `s` 의 (x, y, yaw, 몇 번째 편도). 끝에서 돌아선다(yaw 가 반대)."""
    length = math.dist(a, b)
    lap = int(s // length)
    t = (s % length) / length
    start, end = (a, b) if lap % 2 == 0 else (b, a)
    x = start[0] + (end[0] - start[0]) * t
    y = start[1] + (end[1] - start[1]) * t
    return x, y, math.atan2(end[1] - start[1], end[0] - start[0]), lap


class Pedestrians:
    """Isaac 쪽. 보행자 N 명을 세우고 `update` 로 매 틱 옮긴다. 실패해도 회차를 세우지 않는다(경고 한 번)."""

    def __init__(self, stage, root, count, log=print):
        from isaacsim.core.prims import SingleRigidPrim
        from pxr import Gf, Sdf, UsdGeom, UsdPhysics, UsdShade

        self._log = log
        self._warned = False
        self._items = []
        UsdGeom.Xform.Define(stage, root)

        def material(name, color):
            mat = UsdShade.Material.Define(stage, f"{root}/Looks/{name}")
            shader = UsdShade.Shader.Define(stage, f"{root}/Looks/{name}/Surface")
            shader.CreateIdAttr("UsdPreviewSurface")
            shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
            shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.8)
            mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
            return mat

        skin = material("Skin", SKIN)
        for index, (name, (a, b)) in enumerate(plan(count), start=1):
            path = f"{root}/ped_{index}"
            person = UsdGeom.Xform.Define(stage, path)
            rigid = UsdPhysics.RigidBodyAPI.Apply(person.GetPrim())
            rigid.CreateKinematicEnabledAttr(True)
            body = UsdGeom.Capsule.Define(stage, f"{path}/Body")
            body.CreateRadiusAttr(BODY_RADIUS)
            body.CreateHeightAttr(BODY_HEIGHT)
            body.CreateAxisAttr(UsdGeom.Tokens.z)
            body.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, BODY_RADIUS + BODY_HEIGHT / 2.0))
            UsdPhysics.CollisionAPI.Apply(body.GetPrim())
            UsdShade.MaterialBindingAPI.Apply(body.GetPrim()).Bind(material(f"Clothes{index}",
                                                                            COLORS[(index - 1) % len(COLORS)]))
            head = UsdGeom.Sphere.Define(stage, f"{path}/Head")
            head.CreateRadiusAttr(HEAD_RADIUS)
            head.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, 2 * BODY_RADIUS + BODY_HEIGHT + HEAD_RADIUS))
            UsdShade.MaterialBindingAPI.Apply(head.GetPrim()).Bind(skin)
            self._items.append({"name": name, "a": a, "b": b, "s": 0.0, "lap": 0, "who": f"ped_{index}", "xy": a,
                                "prim": SingleRigidPrim(prim_path=path, name=f"pedestrian_{index}")})
            log(f"pedestrian ped_{index} line={name} from={a} to={b} speed={SPEED} m/s never_stops=true "
                f"height={2 * BODY_RADIUS + BODY_HEIGHT + 2 * HEAD_RADIUS:.2f} m collider=capsule(kinematic)")

    def positions(self):
        """{ped_i: (x, y)} — 마지막으로 옮긴 자리(`encounters` 가 쓴다)."""
        return {item["who"]: item["xy"] for item in self._items}

    def update(self, dt, now_s, real_xys=()):
        """매 틱. 편도가 끝날 때마다(돌아설 때) 한 줄 로그."""
        import numpy as np

        try:
            for item in self._items:
                item["s"], (x, y, yaw, lap), stopped, item["held"] = walk(
                    item["a"], item["b"], item["s"], dt, real_xys, item.get("stopped", False), item.get("held", 0.0))
                if stopped != item.get("stopped", False):
                    item["stopped"] = stopped
                    self._log(f"pedestrian {item['name']} {'stop' if stopped else 'go'} at ({x:.2f}, {y:.2f}) "
                              f"sim={now_s:.2f}")
                item["xy"] = (x, y)
                if lap != item["lap"]:
                    item["lap"] = lap
                    self._log(f"pedestrian {item['name']} turn lap={lap} at ({x:.2f}, {y:.2f}) sim={now_s:.2f}")
                quat = np.array((math.cos(yaw / 2.0), 0.0, 0.0, math.sin(yaw / 2.0)))
                item["prim"].set_world_pose(position=np.array((x, y, 0.0)), orientation=quat)
        except Exception as error:  # 촬영 소품이다 — 한 바퀴를 세우지 않는다
            if not self._warned:
                self._warned = True
                self._log(f"WARN pedestrians update failed {type(error).__name__}: {error}")
