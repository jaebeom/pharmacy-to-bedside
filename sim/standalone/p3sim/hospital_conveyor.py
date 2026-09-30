"""병원 씬 컨베이어를 스테이지가 돌리고 세운다(#527 H2). pxr 은 늦게 가져온다 — 모듈 import 는 Isaac 없이 된다.

병원 전체 preset(`--preset hospital-full`)에서 봉투는 **씬의 컨베이어**를 타고 창구 A1 의 끝 롤러
(`ConveyorTrack_02/Rollers_01`)까지 간다. 우리 벨트는 만들지 않는다.

잰 것(master02, #240):
- 씬을 `/World/P3Base/Scene` 에 reference 하면 씬 컨베이어의 OmniGraph 가 **돌지 않는다**(표면 속도 0, 참조 탐침 01).
- 그래서 표면 속도를 직접 쓴다. 값은 `hospital_conveyor_surfaces.json`(19 몸체, 씬을 루트로 연 회차의 관측값).
  그 방식으로 0.10×0.07×0.01 m 봉투가 (-9.828, 11.1, 0.925)에서 출발해 34.58 sim s 뒤 Rollers_01 끝에
  섰다(`terminal_edge_settled`, edge_gap 0.023).
- 이 모듈은 `hospital_conveyor_probe.HospitalConveyorProbe` 의 발견·설정·정지를 **그대로** 옮긴 것이다.
  다른 점은 하나다: 탐침은 스테이지의 모든 관절·articulation·강체를 껐지만 여기서는 **컨베이어 몸체만**
  만진다(로봇이 돌아야 한다).

가정(재지 않은 것):
- 스테이지(M0609·AMR·봉투 풀이 같이 있는 장면)에서도 같은 표면 속도로 같은 경로를 탄다.
- 끝 판정에 쓰는 트랙 AABB 는 Isaac 에서 렌더 기하로 잰다. 오프라인(usd-core)에서는 원격 자산을 못 읽어 비어 있다.
"""

import json
import math
import random
from pathlib import Path

#: 씬을 루트로 열 때의 컨베이어 루트. json 의 경로가 이 기준이다.
SCENE_CONVEYOR_ROOT = "/World/Conveyor"
#: pharmacy_stage 가 씬을 `/World/P3Base/Scene` 에 reference 할 때의 컨베이어 루트(base_scene.add_base_scene).
REFERENCED_CONVEYOR_ROOT = "/World/P3Base/Scene/Conveyor"
SURFACES_JSON = Path(__file__).resolve().with_name("hospital_conveyor_surfaces.json")
#: 끝 롤러(창구 A1). 봉투가 서는 곳이다.
TERMINAL = SCENE_CONVEYOR_ROOT + "/ConveyorTrack_02/Rollers_01"
#: 끝 롤러에서 봉투가 나가는 방향(월드 축). 잰 회차의 terminal_direction 이다.
TERMINAL_DIRECTION = "-y"
#: A1 로 가려면 Track_02 분기를 켠다(잰 회차 설정). 표면 속도 직접 모드에서는 Sorter_physics 속도가 json 에서 오지만,
#: 그래프가 도는 경우에도 같은 길이 되게 탐침처럼 켜 둔다.
REROUTE = (SCENE_CONVEYOR_ROOT + "/ConveyorTrack_02/Sorter/ActionGraph/reroute.inputs:value",)
#: 봉투 출발점(ConveyorTrack_06 위, 봉투 중심). 잰 회차의 spawn 이다.
SPAWN = (-9.828, 11.1, 0.925)
#: 출발점 흔들기. **추정값이다**(재지 않았다): 잰 회차는 흔들지 않았다. 작게 둔다 — 경로 폭 안에 머물게.
SPAWN_JITTER_XY = 0.01
SPAWN_JITTER_YAW = 0.1
#: 끝 롤러가 "얇은 수평면" 인지 보는 두께 상한(탐침과 같은 값). 잰 두께는 0.029 m 다.
TERMINAL_MAX_THICKNESS = 0.05
CONVEYOR_NODE_TYPE = "isaacsim.asset.gen.conveyor.IsaacConveyor"

SURFACE_API = "PhysxSurfaceVelocityAPI"
ATTR_ENABLED = "physxSurfaceVelocity:surfaceVelocityEnabled"
ATTR_LINEAR = "physxSurfaceVelocity:surfaceVelocity"
ATTR_ANGULAR = "physxSurfaceVelocity:surfaceAngularVelocity"


def moved(path, root):
    """씬 루트 기준 경로(/World/Conveyor/...)를 `root` 아래로 옮긴다. 그 밖의 경로는 그대로 둔다."""
    prefix = SCENE_CONVEYOR_ROOT + "/"
    root = root.rstrip("/")
    if path == SCENE_CONVEYOR_ROOT:
        return root
    return root + "/" + path[len(prefix):] if path.startswith(prefix) else path


def _xyz(value, what):
    try:
        out = tuple(float(v) for v in value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{what}: 수 셋이 아니다") from error
    if len(out) != 3 or not all(math.isfinite(v) for v in out):
        raise ValueError(f"{what}: 유한한 xyz 가 아니다")
    return out


def load_surfaces(path=SURFACES_JSON):
    """json -> {씬 루트 기준 경로: (linear, angular)}. 경로는 모두 SCENE_CONVEYOR_ROOT 아래여야 한다."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    table = data.get("surface_velocities") if isinstance(data, dict) else None
    if not isinstance(table, dict) or not table:
        raise ValueError(f"{path}: surface_velocities 가 없다")
    out = {}
    for body, value in table.items():
        if not body.startswith(SCENE_CONVEYOR_ROOT + "/"):
            raise ValueError(f"{body}: 병원 컨베이어 몸체가 아니다")
        out[body] = (_xyz(value.get("linear", (0, 0, 0)), f"{body}.linear"),
                     _xyz(value.get("angular", (0, 0, 0)), f"{body}.angular"))
    return out


def scaled(value, scale):
    """(linear, angular) 에 같은 배율. 1.0 이면 그대로다."""
    linear, angular = value
    return (tuple(float(v) * scale for v in linear), tuple(float(v) * scale for v in angular))


def spawn_pose(seed, epoch, index, spawn=SPAWN, jitter_xy=SPAWN_JITTER_XY, jitter_yaw=SPAWN_JITTER_YAW):
    """(xyz, yaw) 봉투 출발 자세. pouch.spawn_rng 와 같은 (seed, epoch, index) 규칙이라 같은 입력이면 같은 값이다."""
    rng = random.Random(f"{seed}:{epoch}:{index}")
    dx, dy = rng.uniform(-jitter_xy, jitter_xy), rng.uniform(-jitter_xy, jitter_xy)
    yaw = rng.uniform(-jitter_yaw, jitter_yaw)
    return (spawn[0] + dx, spawn[1] + dy, spawn[2]), yaw


def _finite_box(box):
    return all(math.isfinite(v) and abs(v) < 1e30 for v in (*box["min"], *box["max"])) and all(
        a <= b for a, b in zip(box["min"], box["max"], strict=True))


class HospitalConveyor:
    """씬 컨베이어 몸체의 표면 속도를 쓰고(run) 0 으로(stop) 한다.

    stage: Isaac 또는 usd-core 스테이지. root: 컨베이어 루트(참조면 REFERENCED_CONVEYOR_ROOT).
    discover() 를 먼저 부른다 — 검사가 끝나기 전에는 스테이지를 바꾸지 않는다.
    """

    def __init__(self, stage, root=REFERENCED_CONVEYOR_ROOT, surfaces=SURFACES_JSON, terminal=TERMINAL,
                 reroute=REROUTE, speed_scale=1.0):
        self.stage = stage
        self.root = root.rstrip("/")
        table = surfaces if isinstance(surfaces, dict) else load_surfaces(surfaces)
        # 잰 표면 속도에 곱한다(재범 9/29 "속도 올리기"). 방향은 그대로다 — 분기·끝 롤러 잡기 규칙이 같이 간다.
        self.speed_scale = float(speed_scale)
        if not self.speed_scale > 0.0:
            raise ValueError(f"speed_scale 은 0 보다 커야 한다: {speed_scale}")
        self.surfaces = {moved(body, self.root): scaled(value, self.speed_scale) for body, value in table.items()}
        self.terminal_path = moved(terminal, self.root)
        self.reroute_paths = [moved(path, self.root) for path in reroute]
        self.bodies = []          # 표면 속도를 쓰는 몸체 경로(json 순서)
        self.graph_velocities = []  # (attr, 원래 값): 그래프 변수 Velocity 와 SorterSpeed
        self.graph_prims = []     # 씬 컨베이어의 OmniGraph 프림 경로(발견 때 모은다)
        self.running = False
        self.discovered = False
        # 끝 롤러만 표면 속도 0 으로 잡았나(봉투가 출구에 닿으면, 작전 결정 9/23). run() 이 놓는다.
        self.terminal_held = False

    # -- 발견과 설정 ---------------------------------------------------------------------------------------------
    def discover(self):
        """검사 → 설정. 반환: 로그용 사전. 모자라면 ValueError(스테이지는 안 바뀐다)."""
        from pxr import Usd

        root = self.stage.GetPrimAtPath(self.root)
        if not root or not root.IsValid():
            raise ValueError(f"컨베이어 루트가 없다: {self.root}")
        if self.terminal_path not in self.surfaces:
            raise ValueError(f"끝 롤러가 표면 속도 표에 없다: {self.terminal_path}")
        targets = set()
        for prim in Usd.PrimRange(root):
            attr = prim.GetAttribute("node:type")
            if not attr or attr.Get() != CONVEYOR_NODE_TYPE:
                continue
            rel = prim.GetRelationship("inputs:conveyorPrim")
            found = rel.GetTargets() if rel else []
            if len(found) != 1:
                raise ValueError(f"컨베이어 노드가 몸체 하나를 가리키지 않는다: {prim.GetPath()}")
            targets.add(str(found[0]))
        missing = [path for path in self.surfaces if not self.stage.GetPrimAtPath(path)]
        if missing:
            raise ValueError(f"표면 속도 몸체가 스테이지에 없다: {missing}")
        # 탐침과 같은 검사: json 몸체는 씬의 컨베이어 노드가 가리키는 몸체여야 한다.
        # 참조가 노드의 대상 경로를 옮겼는지도 여기서 본다.
        strays = [path for path in self.surfaces if path not in targets]
        if strays:
            raise ValueError(f"컨베이어 노드가 가리키지 않는 몸체다: {strays} (노드 대상 {len(targets)}개)")
        reroutes = []
        for path in self.reroute_paths:
            attr = self.stage.GetAttributeAtPath(path)
            if not attr or not isinstance(attr.Get(), bool):
                raise ValueError(f"분기 속성이 없다: {path}")
            reroutes.append(attr)
        terminal = self.aabb(self.terminal_path)
        thickness = terminal["max"][2] - terminal["min"][2]
        if not _finite_box(terminal) or not 0.0 < thickness < TERMINAL_MAX_THICKNESS:
            raise ValueError(f"끝 롤러가 얇은 수평면이 아니다(기하가 안 실렸을 수 있다): {terminal}")
        # ---- 여기서부터 스테이지를 바꾼다
        for prim in Usd.PrimRange(root):
            velocity = prim.GetAttribute("graph:variable:Velocity")
            if velocity and velocity.Get() is not None:
                self.graph_velocities.append((velocity, velocity.Get()))
            if prim.GetName() == "SorterSpeed":
                speed = prim.GetAttribute("inputs:value")
                if speed and speed.Get() is not None:
                    self.graph_velocities.append((speed, speed.Get()))
            if prim.GetTypeName() == "OmniGraph":
                self.graph_prims.append(str(prim.GetPath()))
        for attr in reroutes:
            attr.Set(True)
        for path in self.surfaces:
            self._make_kinematic_surface(self.stage.GetPrimAtPath(path))
            self.bodies.append(path)
        self.discovered = True
        self.stop()
        return {"root": self.root, "bodies": len(self.bodies), "node_targets": len(targets),
                "graph_velocities": len(self.graph_velocities), "graphs": len(self.graph_prims),
                "reroute": self.reroute_paths,
                "terminal": self.terminal_path, "terminal_surface": terminal,
                "direction": TERMINAL_DIRECTION}

    @staticmethod
    def _make_kinematic_surface(prim):
        """탐침과 같은 설정: 운동학 강체 + 표면 속도 API(켜짐, 0)."""
        from pxr import Gf, Sdf, UsdPhysics

        body = UsdPhysics.RigidBodyAPI.Apply(prim)
        body.CreateRigidBodyEnabledAttr(True)
        body.CreateKinematicEnabledAttr(True)
        try:  # Isaac: 잰 탐침과 같은 길(PhysxSchema)
            from pxr import PhysxSchema

            api = PhysxSchema.PhysxSurfaceVelocityAPI.Apply(prim)
            api.CreateSurfaceVelocityEnabledAttr(True)
            api.CreateSurfaceVelocityAttr(Gf.Vec3f(0))
            api.CreateSurfaceAngularVelocityAttr(Gf.Vec3f(0))
        except ImportError:  # usd-core(시험): 같은 이름의 스키마·속성을 이름으로 쓴다
            prim.AddAppliedSchema(SURFACE_API)
            prim.CreateAttribute(ATTR_ENABLED, Sdf.ValueTypeNames.Bool).Set(True)
            prim.CreateAttribute(ATTR_LINEAR, Sdf.ValueTypeNames.Vector3f).Set(Gf.Vec3f(0))
            prim.CreateAttribute(ATTR_ANGULAR, Sdf.ValueTypeNames.Vector3f).Set(Gf.Vec3f(0))

    def silence_graphs(self):
        """발견이 끝난 뒤 씬 컨베이어의 OmniGraph 를 끈다. 끈 프림 수를 돌려준다.

        **발견 뒤에만 부른다.** `discover()` 는 그래프 노드의 `inputs:conveyorPrim` 으로 19 몸체를 확인하고
        그래프 변수 자리를 모으는데, 비활성 프림은 `Usd.PrimRange` 기본 술어가 건너뛴다.

        왜 끄는가: 9/23 병원 한 바퀴에서 `belt_surface before_play … (-0.5, 0, 0)` 이었던 끝 롤러 표면 속도가
        `after_reset` 에 `(0, 0, 0)` 이 됐고 봉투가 출발점에 그대로 섰다(맥마클2, m2-hf-full-5a59776).
        그래프가 돌면 `ConveyorNode` 가 매 틱 자기 `Velocity` 변수(우리가 0 으로 둔 값)를 몸체에 쓴다 —
        우리가 Play 전에 써 둔 잰 값을 덮는다. Play 뒤 USD 쓰기는 PhysX 에 닿지 않으므로(I1 bbedd65)
        덮이면 되돌릴 길이 없다. 그래서 쓰는 손을 하나만 남긴다.

        참조 탐침 02(#240)는 그래프가 몸체를 움직이지 못한 장면이었다(탐침 01: 선속도 19개 모두 0).
        끄는 것은 그 조건을 스테이지에서도 확실히 하는 것이지, 새로 만드는 동작이 아니다.
        """
        if not self.discovered:
            raise RuntimeError("discover() 를 먼저 부른다")
        for path in self.graph_prims:
            prim = self.stage.GetPrimAtPath(path)
            if prim and prim.IsValid():
                prim.SetActive(False)
        # 끈 그래프의 속성 손잡이는 만료된다. 그대로 두면 다음 `run()`·`stop()` 이
        # `Accessed invalid attribute … on expired 'OmniGraphNode' prim` 으로 멈춘다(9/23 회차 0b65ae2).
        # 그래프가 꺼졌으니 그 값을 0 으로 둘 일도 없다 — 목록을 비우는 것이 맞다.
        self.graph_velocities = []
        return len(self.graph_prims)

    # -- 돌리기·세우기 ------------------------------------------------------------------------------------------
    def _zero_graphs(self):
        """살아 있는 그래프 변수만 0 으로. 끈 그래프의 속성은 만료돼 있어 건너뛴다."""
        for attr, _value in self.graph_velocities:
            prim = attr.GetPrim()
            if prim and prim.IsValid() and prim.IsActive():
                attr.Set(0.0)

    def _write(self, zero):
        from pxr import Gf

        for path in self.bodies:
            prim = self.stage.GetPrimAtPath(path)
            linear, angular = ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0)) if zero else self._want(path)
            prim.GetAttribute(ATTR_LINEAR).Set(Gf.Vec3f(*linear))
            prim.GetAttribute(ATTR_ANGULAR).Set(Gf.Vec3f(*angular))

    def _want(self, path):
        """이 몸체에 지금 있어야 할 (선속도, 각속도). 잡힌 끝 롤러만 0 이다."""
        if self.terminal_held and path == self.terminal_path:
            return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
        return self.surfaces[path]

    def hold_terminal(self):
        """끝 롤러만 표면 속도 0. 봉투가 출구에 닿으면 부른다. 새로 잡았으면 True."""
        from pxr import Gf

        if self.terminal_held or not (self.running and self.discovered):
            return False
        self.terminal_held = True
        prim = self.stage.GetPrimAtPath(self.terminal_path)
        for attribute in (ATTR_LINEAR, ATTR_ANGULAR):
            attr = prim.GetAttribute(attribute)
            if attr:
                attr.Set(Gf.Vec3f(0.0, 0.0, 0.0))
        return True

    def run(self):
        """잰 표면 속도를 쓴다(끝 롤러도 놓는다). 그래프 속도는 0 으로 둔다 — 같은 몸체를 두 손이 쓰지 않게."""
        if not self.discovered:
            raise RuntimeError("discover() 를 먼저 부른다")
        self.terminal_held = False
        self._zero_graphs()
        self._write(zero=False)
        self.running = True

    def stop(self):
        """그래프 속도와 표면 속도를 모두 0 으로."""
        self._zero_graphs()
        if self.discovered:
            self._write(zero=True)
        self.running = False

    def reassert(self):
        """돌고 있어야 하는데 표면 속도가 0 이 된 몸체를 다시 쓴다. 다시 쓴 몸체 수를 돌려준다.

        9/23 회차(cc55ca7): 그래프를 다 꺼도 `world.reset()` 뒤 첫 `world.step()` 에서 잰 표면 속도가
        0 으로 돌아갔다(`after_reset_rewrite` (-0.5,0,0) → `after_first_step` (0,0,0)). 무엇이 0 을 쓰는지
        아직 모른다. Play 뒤 USD 쓰기가 PhysX 에 닿는지도 모른다(I1 bbedd65 는 그래프가 켜진 회차였다).
        그래서 **매 틱 맞춰 둔다** — 닿으면 벨트가 돌고, 안 닿으면 로그에 다시 쓴 수가 계속 남아 갈린다.
        """
        from pxr import Gf

        if not (self.running and self.discovered):
            return 0
        written = 0
        for path in self.bodies:
            prim = self.stage.GetPrimAtPath(path)
            if not (prim and prim.IsValid()):
                continue
            linear, angular = self._want(path)
            for attribute, want in ((ATTR_LINEAR, linear), (ATTR_ANGULAR, angular)):
                attr = prim.GetAttribute(attribute)
                if not attr:
                    continue
                value = attr.Get()
                if value is None or any(abs(float(a) - float(b)) > 1e-6
                                        for a, b in zip(value, want, strict=True)):
                    attr.Set(Gf.Vec3f(*(float(v) for v in want)))
                    written += 1
        return written

    def readback(self):
        """끝 롤러의 표면 선속도(쓴 값이 아니라 읽은 값). 못 읽으면 None."""
        try:
            attr = self.stage.GetPrimAtPath(self.terminal_path).GetAttribute(ATTR_LINEAR)
            value = attr.Get() if attr else None
            return None if value is None else tuple(float(v) for v in value)
        except Exception:  # noqa: BLE001 - 읽기 실패는 APPLIED_UNKNOWN 이지 정지가 아니다
            return None

    # -- 기하 ---------------------------------------------------------------------------------------------------
    def aabb(self, path):
        """월드 축 정렬 상자 {"min", "max"}(렌더 기하, 탐침과 같은 목적 셋)."""
        from pxr import Usd, UsdGeom

        cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(),
                                  [UsdGeom.Tokens.default_, UsdGeom.Tokens.render, UsdGeom.Tokens.proxy])
        aligned = cache.ComputeWorldBound(self.stage.GetPrimAtPath(path)).ComputeAlignedRange()
        return {"min": [float(v) for v in aligned.GetMin()], "max": [float(v) for v in aligned.GetMax()]}

    def terminal_surface(self):
        return self.aabb(self.terminal_path)

    def tracks(self):
        """경로 몸체의 AABB 목록(끝 롤러 포함). 비어 있는 상자는 ValueError — 기하가 안 실린 것이다."""
        out = []
        for path in self.bodies or list(self.surfaces):
            box = self.aabb(path)
            if not _finite_box(box):
                raise ValueError(f"트랙 상자가 비었다(기하가 안 실렸을 수 있다): {path}")
            out.append(box)
        return out
