"""도크 벽 반투명(재범 9/29: "도킹스테이션이 있는 벽을 반투명으로 바꿔서 약이 오는 것을 확인").

Isaac 임포트는 늦게 한다.

병원 씬의 도크 벽(y 5.35, 조제실 남쪽 벽) 조각에 **반투명 재질 하나**를 실행 중에만 바인딩한다.
환경 USD 파일은 고치지 않는다(AGENTS "환경 USD 제출 전 확인").
충돌체·지도는 그대로다 — 몸체는 벽에 막히고 Nav2 정적 지도도 같다.
새 메시·조명 없음. `opacity >= 1` 이면 아무것도 하지 않는다(되돌리기 `--dock-wall-opacity 1`).
**L3 미확인**: RTX 라이다가 반투명 재질을 통과하는지(로컬 코스트맵은 라이다 층뿐이다), rtf 비용.
"""

#: 씬 파일 기준 prim(앵커 JSON 과 같은 모양). 조제실 남쪽 벽 y 5.35 의 조각들 — 도크 넷(x −7.3…1.6)이 이 벽 앞에 선다.
#: _12(x −9.88, 폭 1.8 배)·_14(x −3.02)가 아래 벽, _11(z 1.52, 길이 14.2 배)이 윗 띠다
#: (`sim/scenes/hospital_navigationv1.usda`).
DOCK_WALL_PRIMS = (
    "/World/Environment/hospital/Geo_W_WallBase2_12",
    "/World/Environment/hospital/Geo_W_WallBase2_14",
    "/World/Environment/hospital/Geo_W_WallBase2_11",
)
#: 유리 느낌의 옅은 청회색. 흰 바탕은 봉투 검출기가 봉투로 볼 수 있어 조금 채도를 둔다(표지판과 같은 이유).
GLASS_COLOR = (0.62, 0.78, 0.88)
#: preset hospital 의 불투명도. 0 = 안 보임, 1 = 원래 벽.
HOSPITAL_OPACITY = 0.35


def should_build(opacity):
    """반투명을 세우나. 1 이상이면 원래 벽 그대로다."""
    return 0.0 <= float(opacity) < 1.0


def build(stage, root, prims, opacity, log=print):
    """`prims`(스테이지 경로)에 반투명 재질을 강하게 바인딩한다. 반환 (칠한 수, 못 찾은 경로 목록)."""
    if not should_build(opacity):
        log(f"dock_wall_glass off opacity={opacity}")
        return 0, []
    from pxr import Gf, Sdf, UsdShade

    material = UsdShade.Material.Define(stage, f"{root}/Looks/DockWallGlass")
    shader = UsdShade.Shader.Define(stage, f"{root}/Looks/DockWallGlass/Surface")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*GLASS_COLOR))
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.15)
    shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(float(opacity))
    shader.CreateInput("opacityThreshold", Sdf.ValueTypeNames.Float).Set(0.0)
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    painted, missing = 0, []
    for path in prims:
        prim = stage.GetPrimAtPath(path)
        if not prim or not prim.IsValid():
            missing.append(path)
            continue
        UsdShade.MaterialBindingAPI.Apply(prim).Bind(material, UsdShade.Tokens.strongerThanDescendants)
        painted += 1
    log(f"dock_wall_glass painted={painted} missing={missing} opacity={opacity} visual_only=true "
        f"(충돌·지도 그대로, 라이다 영향 L3 미확인)")
    return painted, missing
