"""경로 위 정지 캡슐 — 감속기 정지 규칙(#721) **발동** 시험 인자 `--block-path`. Isaac 임포트는 늦게 한다.

회차127(a52aa6b, 더미 ON): 정지 규칙은 켜졌지만 더미가 AMR 1.5 m 밖에서 서서 조우 최소 1.165 m — 0.6 m 문턱에
든 적이 없어 `governor stop` 0줄(발동 미검증). 이 소품은 그 문턱을 **일부러** 넘긴다.

사람 크기 캡슐 하나가 바닥 아래(`PARK_Z`)에 숨어 있다가, 진짜 AMR(amr_1 몸체 중심)이 `trigger` m 안에 들면 배송
경로 위 한 점에 **한 번** 올라오고, `hold` s 뒤 다시 내려간다. 캡슐은 기구학 강체+충돌체라 라이다·지역 코스트맵에
보이고 정적 지도에는 없다 — 정지 규칙이 보는 바로 그 종류다. `/Amr` 밖이라 닿으면 기존 접촉 로그에 잡힌다.

- 자리 `BLOCK_XY`: load → 병동·간호사실 공통 구간(로비, y ≈ 4.2) 위. 첫 배송이 어느 병동이든 동쪽으로 지난다.
  정차 자리에서 2.9 m 밖, 경로 꺾임점에서 3.5 m 밖, 병동 문에서 16 m 밖, 보행자 선·더미 루프에서 2 m 밖
  (sim/tests/test_path_block.py 가 지도·routes 로 확인).
- 발동 거리 `TRIGGER_M` 1.5(몸체 중심 기준): 캡슐이 몸체 앞끝에서 1.0 m 에 나타나 0.6 m 문턱까지 0.4 m 다.
  Nav2 가 재계획으로 비껴갈 틈보다 규칙이 먼저 보게 가깝게 둔 값이다(고른 값, 잰 값 아님).
- 유지 `HOLD_S` 5: Nav2 progress_checker 의 movement_time_allowance 10 s 보다 짧다. 재개(0.9 m·1 s) 뒤 0.5 m 를
  그 안에 가야 회복 행동(후진·회전)이 섞이지 않는다.

기대 로그 순서: `block_path placed` → `governor stop reason=obstacle` → `block_path lifted` → `governor resume`.
접촉은 0 이어야 한다. 더미·보행자는 0 으로 두고 돈다(다른 정지 원인을 섞지 않는다).

`Blocker` 는 순수 상태 기계라 sim/tests 가 본다. `PathBlock`(Isaac) 은 L3 미실행이다.
"""

import math

#: 캡슐 자리(병원 좌표, m). load → 병동 공통 구간 위(routes.hospital.yaml 의 (-2.525, 4.175)–(8.075, 4.225) 마디).
BLOCK_XY = (4.54, 4.21)
#: amr_1 몸체 중심이 이 안에 들면 올라온다(m).
TRIGGER_M = 1.5
#: 올라와 있는 시간(sim s).
HOLD_S = 5.0
#: 숨어 있을 때의 높이(m). 바닥 아래라 라이다(2D)에 안 보이고 기구학이라 떨어지지 않는다.
PARK_Z = -3.0
#: 사람 크기 캡슐(보행자와 같은 치수). 서 있는 키 약 1.4 m.
RADIUS = 0.20
HEIGHT = 1.00
#: 빨강 — 촬영에서 보행자(파랑/초록)·더미(노랑)와 구분한다.
COLOR = (0.85, 0.15, 0.15)


class Blocker:
    """순수 상태 기계: armed → placed(한 번) → lifted. `update` 가 (사건, 로그 한 줄) 또는 None 을 돌려준다."""

    def __init__(self, xy=BLOCK_XY, trigger_m=TRIGGER_M, hold_s=HOLD_S):
        if not trigger_m > 0.0:
            raise ValueError(f"--block-path-trigger 는 0 보다 커야 한다: {trigger_m}")
        if not hold_s > 0.0:
            raise ValueError(f"--block-path-hold 는 0 보다 커야 한다: {hold_s}")
        self.xy = (float(xy[0]), float(xy[1]))
        self.trigger_m, self.hold_s = float(trigger_m), float(hold_s)
        self.state = "armed"
        self.placed_at = None

    @property
    def placed(self):
        return self.state == "placed"

    def positions(self):
        """{block_1: (x, y)} — 올라와 있는 동안만(`encounters` 가 쓴다)."""
        return {"block_1": self.xy} if self.placed else {}

    def update(self, now_s, amr_xy):
        """한 틱. amr_xy 는 amr_1 몸체 중심 (x, y) 또는 None(아직 못 읽음)."""
        if self.state == "armed":
            if amr_xy is None:
                return None
            distance = math.dist(amr_xy, self.xy)
            if distance <= self.trigger_m:
                self.state, self.placed_at = "placed", now_s
                return "placed", (f"block_path placed at=({self.xy[0]:.2f}, {self.xy[1]:.2f}) sim={now_s:.2f} "
                                  f"amr_dist={distance:.2f}")
        elif self.state == "placed" and now_s - self.placed_at >= self.hold_s:
            self.state = "lifted"
            return "lifted", f"block_path lifted sim={now_s:.2f} held={now_s - self.placed_at:.2f}"
        return None


class PathBlock:
    """Isaac 쪽. 캡슐 하나를 바닥 아래에 세우고 `update` 로 올렸다 내린다. 실패해도 회차를 세우지 않는다(경고 한 번)."""

    def __init__(self, stage, root, xy=BLOCK_XY, trigger_m=TRIGGER_M, hold_s=HOLD_S, log=print):
        from isaacsim.core.prims import SingleRigidPrim
        from pxr import Gf, Sdf, UsdGeom, UsdPhysics, UsdShade

        self._log = log
        self._warned = False
        self.rule = Blocker(xy, trigger_m, hold_s)
        UsdGeom.Xform.Define(stage, root)
        path = f"{root}/block_1"
        block = UsdGeom.Xform.Define(stage, path)
        block.AddTranslateOp().Set(Gf.Vec3d(self.rule.xy[0], self.rule.xy[1], PARK_Z))
        rigid = UsdPhysics.RigidBodyAPI.Apply(block.GetPrim())
        rigid.CreateKinematicEnabledAttr(True)
        body = UsdGeom.Capsule.Define(stage, f"{path}/Body")
        body.CreateRadiusAttr(RADIUS)
        body.CreateHeightAttr(HEIGHT)
        body.CreateAxisAttr(UsdGeom.Tokens.z)
        body.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, RADIUS + HEIGHT / 2.0))
        UsdPhysics.CollisionAPI.Apply(body.GetPrim())
        mat = UsdShade.Material.Define(stage, f"{root}/Looks/Block")
        shader = UsdShade.Shader.Define(stage, f"{root}/Looks/Block/Surface")
        shader.CreateIdAttr("UsdPreviewSurface")
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*COLOR))
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.8)
        mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
        UsdShade.MaterialBindingAPI.Apply(body.GetPrim()).Bind(mat)
        self._prim = SingleRigidPrim(prim_path=path, name="path_block_1")
        log(f"block_path armed at=({self.rule.xy[0]:.2f}, {self.rule.xy[1]:.2f}) trigger={self.rule.trigger_m:g} m "
            f"hold={self.rule.hold_s:g} s capsule r={RADIUS:g} h={2 * RADIUS + HEIGHT:.2f} m "
            f"collider=kinematic parked_z={PARK_Z:g}")

    def positions(self):
        return self.rule.positions()

    def update(self, now_s, amr_xy):
        """매 틱. 올라오거나 내려갈 때 한 줄 로그."""
        import numpy as np

        try:
            change = self.rule.update(now_s, amr_xy)
            if change is None:
                return
            event, line = change
            z = 0.0 if event == "placed" else PARK_Z
            self._prim.set_world_pose(position=np.array((self.rule.xy[0], self.rule.xy[1], z)),
                                      orientation=np.array((1.0, 0.0, 0.0, 0.0)))
            self._log(line)
        except Exception as error:  # 시험 소품이다 — 한 바퀴를 세우지 않는다
            if not self._warned:
                self._warned = True
                self._log(f"WARN path block update failed {type(error).__name__}: {error}")
