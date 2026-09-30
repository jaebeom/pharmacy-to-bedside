"""Named viewport camera poses for demo captures (pure; no Isaac imports).

실습7-a4 (9/18): the default Kit perspective camera sits outside the room (+x, +y side), so the corridor wall and the
shelf backs hid the rail, robot and shelves in the captures. Every shelf, the dispenser, the round bin and the module
hole open toward -y, so these cameras stand inside the room on the -y side, beyond the arm's reach.

Frame as in p3sim/layout.py: metres, z up, rail centre on the floor at the origin, back wall toward +y, corridor
wall at x 2.7. Values are ours (placeholders like the v2 layout); tests check each eye is inside the room, outside
every layout box and the arm's reach, and that the view's subject points fall inside the frame.
"""

import math
import os

# Kit's default perspective camera: focal length 18.147 mm over a 20.955 mm horizontal aperture (60 deg horizontal),
# viewport 16:9. The renderer keeps square pixels and derives the vertical from the horizontal aperture and the image
# aspect (Isaac Sim 5.1 isaacsim.sensors.camera docs), so a taller image (재범 9/18: Isaac on the left half of the
# screen, about 960x1040) keeps the 60 deg across and sees more up and down. Tests check both aspects; the stage logs
# the real viewport resolution and apertures (`viewport camera …`) to confirm it on master02.
HORIZONTAL_FOV_DEG = 60.0
ASPECT = 16.0 / 9.0
HALF_SCREEN_ASPECT = 960.0 / 1040.0

# name -> (eye, target) per scene. overview (the v2 preset default): where the robot works, as close as the 60 deg
# frame allows (재범 7-a4) - shelf picks up to the gripper above the top row, the robot around every rail pose the
# arm uses (실습7-a5: at the module insert, rail x 1.30, the arm left the frame), round bin and module hole; the
# floor-level track ends and plinths fall outside.
# shelves: the shelves the arm picks from. bins: the round bin and the module hole (v1: inlets A/B).
# ur5: the loading cell, which is in the corridor (x > wall_x), so its eye is the one camera outside the pharmacy.
# 실습12d-v (9/20): the UR5 run was recorded with --view none because no preset framed the cell - overview puts it
# 3.2 m off axis, past the 60 deg frame - and the arm came out a thumbnail in one corner. This eye stands beside the
# pedestal at 0.75 m, just under its 0.80 m top, and looks almost along +y (slope 0.02), so the pedestal's top face is
# seen edge-on: that is what tells "the upper arm rests on the top" apart from "it is wedged at the edge", and the
# wall face at x 2.75 separates from the elbow horizontally. Diagnostic; no preset selects it.
UR5_VIEW = ((3.10, -1.75, 0.75), (3.05, 0.55, 0.70))
VIEWS = {
    "v1": {
        "overview": ((0.05, -3.0, 2.1), (0.05, 0.75, 0.60)),
        "shelves": ((-0.55, -1.6, 1.30), (-0.55, 0.90, 0.55)),
        "bins": ((0.55, -0.90, 1.55), (1.00, 0.60, 0.90)),
        "ur5": UR5_VIEW,
    },
    "v2": {
        "overview": ((0.0, -2.53, 2.17), (0.0, 0.75, 1.10)),
        "shelves": ((-0.65, -2.3, 1.55), (-0.65, 0.90, 0.90)),
        "bins": ((0.55, -0.90, 1.60), (1.00, 0.65, 0.95)),
        "ur5": UR5_VIEW,
    },
}
# Views of the pharmacy, whose eyes stand inside the room. The corridor ones are listed apart because the room
# invariants (eye on the pharmacy side of the wall, clear of the arm's reach) do not apply to them.
VIEW_NAMES = ("overview", "shelves", "bins")
CORRIDOR_VIEW_NAMES = ("ur5",)
ALL_VIEW_NAMES = VIEW_NAMES + CORRIDOR_VIEW_NAMES

# Hospital demo cameras (docs/presentation/hospital-demo-shotlist.md, #567; 작전 9/23 결정 (가)): the full-lap video
# is one floor_top take plus close-ups from other runs at the same SHA. Hospital world frame as in zones.hospital.yaml
# (hospital_navigationv1), so unlike the pharmacy views they belong to no scene name and --v2-offset does not move
# them. They are not --view choices yet: the hospital-full preset (#553) wires them in once it is on main.
# test_hospital_views checks every subject is in frame, low eyes stand in free map cells, and no sight line crosses a
# blocked cell 1.0-1.8 m up. The map covers z 0.10-1.80 only, so ceilings and anything higher are not checked.
HOSPITAL_VIEWS = {
    # load 정차가 잰 정착 자리 기준으로 옮겨져(−8.995, 4.686, yaw −90도) 이 둘도 다시 골랐다.
    # 조건은 시험이 보는 것과 같다: 대상이 16:9·반쪽 둘 다에서 프레임 안, 눈이 빈 바닥 위(0.3 m 둘레),
    # 시선이 1.0–1.8 m 띠의 막힌 칸을 지나지 않음, 차체에서 1.5 m 밖. 그 중 **가장 가까운** 자리다.
    "conveyor_a1": ((-9.89, 3.44, 1.8), (-8.795, 5.436, 0.5)),  # 마지막 컨베이어 구간·A1 끝·적재 중인 AMR
    "a1_pick": ((-8.49, 2.44, 1.6), (-7.996, 4.636, 0.7)),  # 적재 자리에서 A1 끝을 집는 UR5
    # 병원 기본 뷰포트(재범 9/23: 회차 내내 Perspective 가 이 자세다). 손으로 고른 값이 아니라
    # **한 바퀴가 실제로 도는 자리**(load, dock_1-4, station_a, bed_a1 과 그 협탁, A1 끝 롤러)의 bbox 에서
    # 계산했다: 중심을 보고, 그 대각(31.7 m)의 절반 거리에서 66도 올려본 자리. 16:9 와 반쪽 화면 둘 다에서
    # 그 아홉 점이 다 들어오는 **가장 낮은** 자세다(여유 margin 0.95). 기울기 24도 — 바로 위에서 내려다보면
    # 위 벡터가 정해지지 않아 화면이 돈다. 눈이 지도 밖(y -10)인 것은 벽·천장 **위**에서 보기 때문이다.
    "floor_top": ((11.44, -10.05, 35.49), (7.35, 5.21, 0.0)),
    "bed_a1": ((25.0, 5.5, 2.2), (22.9, 7.3, 0.6)),  # bed_a1 (PDF D1) side stop (603dfc1) and its cabinet
    # 간호스테이션 B 테이블 내려놓기(작전 9/24). 테이블 SM_SideTable_02a4_01(x 9.39–10.48, y 3.34–4.16, 상판 0.587),
    # 정차 (9.584, 4.660, yaw 180°), 놓는 점 (9.934, 3.958, 0.587). bed_a1 과 같은 조건(16:9·반쪽 프레임 안,
    # 눈 아래 0.3 m 빈 바닥, 1.0–1.8 m 띠 시선 막힘 없음, 차체에서 1.5 m 밖) 중 가장 가까운 자리다(오프라인 탐색).
    # 차체 뒤 위에서 본다 — 놓는 점까지의 시선은 차체를 상판(0.8 m)보다 위, 팔 높이로만 지난다(여유 0.05 m 로 탐색).
    "station_b": ((10.83, 6.0, 1.8), (9.779, 4.178, 0.6)),
    # 조제실 안 둘(발표 #611 4절). 대상은 병원 워크셀(`experiments/fixtures/hospital-integrated-09/workcell.json`):
    # 레일 원점(-3.3, 10.75) = M0609 홈, 선반 9개(x -5.17..2.23, 앞면 y ≈ 11.43), 투입구(-7.75, 11.015)·
    # 모듈 구멍(-7.7, 11.115). 9/23 까지의 값은 빈월드 layout_v2 를 병원 원점으로 옮긴 자리를 봐서 M0609·그리퍼가
    # 화면 밖이었다(마클2 캡처, 626d69f). 주인공 M0609 을 가운데 두고, 16:9 와 반쪽 화면 둘 다에서 대상이 다
    # 들어오며 눈 아래(0.3 m 둘레)가 지도상 빈 칸인 가장 가까운 자리다(비전 9/23, 오프라인 계산).
    "m0609_shelf": ((-3.81, 9.59, 2.2), (-3.3, 11.0, 0.8)),  # 홈의 M0609 + 가까운 선반 셋(68–70) + 선반 앞 작업점
    "m0609_dispenser": ((-7.08, 10.08, 2.2), (-7.72, 10.85, 0.8)),  # 넣는 자리의 M0609 + 원통 투입구·모듈 구멍
    # 조제실 전체 공중 뷰(재범 요청 9/25, 작전 카드 ①): 레일 전 구간(x −9.0..2.4)·선반 9개·조제기·벨트 시작
    # (−9.82, 10.9)이 한 프레임. 재범 9/27 선택 "전 구간, 모서리 대각": 높이 3 m·55° 로 내려다보며 12 m 를 담는
    # 것은 방 깊이(남벽 y 6.2 ~ 선반 11.4)로 안 된다. 동쪽 앞 모서리(동벽 x 3.0·남벽 y 6.2 안쪽 0.3 m)에서 약 22° 로
    # 비스듬히 본다. 방 안에서는 기본 60° 로 서쪽 끝이 8 % 모자라 이 뷰만 초점거리를 `HOSPITAL_VIEW_FOCAL_MM` 으로
    # 넓힌다. 천장 높이·조명은 지도에 없다 — 마클 정지 캡처가 본다.
    # 16d170e 캡처(#240 5854871191): 15.5 mm·목표 (−1.0, 11.2, 0.6) 에서 동쪽 끝 선반 틀 위(x 2.52, z 2.01)가
    # 화면 오른쪽 위로 나갔다(계산 1.09–1.12). 시험 대상이 선반 **칸**뿐이고 틀 끝을 안 봤다. 틀 모서리까지 넣어
    # 목표를 (−0.5, 11.0, 0.9), 초점을 14.0 mm(약 74°)로 다시 골랐다.
    "m0609_overhead": ((2.7, 6.8, 3.0), (-0.5, 11.0, 0.9)),
}
#: 기본(18.147 mm, 60°)과 다른 초점거리(mm)를 쓰는 병원 뷰. Perspective 프림은 그대로 두고 초점거리만 바꾼다.
HOSPITAL_VIEW_FOCAL_MM = {"m0609_overhead": 14.0}
#: Kit Perspective 의 가로 조리개(mm). `HORIZONTAL_FOV_DEG` 는 이 값과 18.147 mm 에서 나온다.
HORIZONTAL_APERTURE_MM = 20.955
HOSPITAL_VIEW_NAMES = tuple(HOSPITAL_VIEWS)
#: 조제실(워크셀) 안에 서는 카메라. **지도 검사에서 뺀다** — `maps/hospital.yaml` 은 원본 병원 씬을
#: z 0.10-1.80 으로 눌러 만든 것이라, 우리가 그 자리에 세운 선반·조제기·레일을 모르고 원래 방 벽만 안다.
#: 그 지도로 "눈이 빈 칸인가·시선이 막혔나" 를 물으면 답이 틀린다(선반 앞 (-0.40, 11.44)이 막힘으로 나온다).
#: 이 둘은 프레임 검사만 하고, 실제로 보이는지는 마클2 정지 캡처가 본다. 복도 뷰(`CORRIDOR_VIEW_NAMES`)를
#: 방 불변식에서 빼는 것과 같은 이유다.
HOSPITAL_PHARMACY_VIEW_NAMES = ("m0609_shelf", "m0609_dispenser", "m0609_overhead")

#: 합본 AMR 을 따라가는 카메라(발표 #611 4절, 작전 9/23: 뒤 2.5 m, 위 1.6 m, 진행 방향).
#: **정해진 자세가 없어 `HOSPITAL_VIEWS` 에 넣지 않는다** — 매 틱 차체 자세에서 계산한다.
#: 그래도 카메라 **프림은 바꾸지 않는다**. Perspective 를 옮긴다(재범 9/23: 뷰포트가 프림으로 자꾸
#: 바뀌어 지저분하다). 촬영은 amr_1 기준이다(재범 확정: amr_1 배송, amr_2 도크 대기).
HOSPITAL_FOLLOW_VIEW_NAMES = ("amr_chase",)
CHASE_BACK_M = 2.5
CHASE_UP_M = 1.6
CHASE_AHEAD_M = 1.0
CHASE_LOOK_Z = 0.5


def chase_pose(x, y, yaw, back=CHASE_BACK_M, up=CHASE_UP_M, ahead=CHASE_AHEAD_M, look_z=CHASE_LOOK_Z):
    """차체 (x, y, yaw) → 따라가는 카메라의 (eye, target).

    눈은 차체 **뒤** `back` m, 바닥에서 `up` m. 보는 곳은 차체 **앞** `ahead` m 의 `look_z` 높이다 —
    차체 한가운데를 보면 화면의 절반이 상판 뚜껑이라 가는 방향이 안 보인다.

    yaw 는 차체 +x 가 향하는 방향이다(`amr_base.base_world_pose` 와 같은 뜻).
    """
    forward = (math.cos(yaw), math.sin(yaw))
    eye = (x - forward[0] * back, y - forward[1] * back, up)
    target = (x + forward[0] * ahead, y + forward[1] * ahead, look_z)
    return eye, target


def view(scene, name):
    """(eye, target) for a named view of scene 'v1' or 'v2'."""
    return VIEWS[scene][name]


def hospital_view(name):
    """(eye, target) for a named hospital demo camera, hospital world frame."""
    return HOSPITAL_VIEWS[name]


def hospital_view_fov_deg(name):
    """병원 뷰의 가로 화각(도). `HOSPITAL_VIEW_FOCAL_MM` 에 없으면 기본 60°."""
    focal = HOSPITAL_VIEW_FOCAL_MM.get(name)
    if focal is None:
        return HORIZONTAL_FOV_DEG
    return math.degrees(2.0 * math.atan(HORIZONTAL_APERTURE_MM / 2.0 / focal))


def frame_coords(eye, target, point):
    """(forward distance, horizontal tan, vertical tan) of `point` seen from `eye` looking at `target`, z up."""
    fwd = [t - e for t, e in zip(target, eye, strict=True)]
    norm = math.sqrt(sum(v * v for v in fwd))
    fwd = [v / norm for v in fwd]
    right = (fwd[1], -fwd[0], 0.0)
    rnorm = math.hypot(right[0], right[1])
    right = (right[0] / rnorm, right[1] / rnorm, 0.0)
    up = (right[1] * fwd[2] - right[2] * fwd[1], right[2] * fwd[0] - right[0] * fwd[2],
          right[0] * fwd[1] - right[1] * fwd[0])
    rel = [p - e for p, e in zip(point, eye, strict=True)]
    depth = sum(a * b for a, b in zip(rel, fwd, strict=True))
    if depth <= 0.0:
        return depth, math.inf, math.inf
    return (depth, sum(a * b for a, b in zip(rel, right, strict=True)) / depth,
            sum(a * b for a, b in zip(rel, up, strict=True)) / depth)


def in_frame(eye, target, point, margin=0.95, aspect=ASPECT, fov_deg=HORIZONTAL_FOV_DEG):
    """True when `point` falls inside the camera's frame (horizontal `fov_deg`, default Kit's 60) at image aspect
    width/height (margin < 1 keeps it off the edge)."""
    depth, h, v = frame_coords(eye, target, point)
    half_h = math.tan(math.radians(fov_deg / 2.0)) * margin
    return depth > 0.0 and abs(h) <= half_h and abs(v) <= half_h / aspect


# 렌더 해상도 상한(작전 결정 5, 9/23). master02 5080 Laptop 은 80 W 에서 더 못 올린다(`nvidia-smi -pl` not supported).
# 창 크기는 그대로 두고 렌더만 이 상자 안으로 줄인다(비율 유지, 뷰포트가 창에 맞춰 늘린다).
# P3_RENDER_MAX=WxH 로 바꾸고, 빈 값(P3_RENDER_MAX=)이면 상한이 없다 — 최종 데모 촬영 회차는 상한 없이 찍는다.
RENDER_MAX_ENV = "P3_RENDER_MAX"
DEFAULT_RENDER_MAX = (1280, 720)


def render_max(environ=None):
    """(W, H) 상한 또는 None(상한 없음). 변수가 없으면 기본값, 빈 값이면 None, 못 읽으면 ValueError."""
    environ = os.environ if environ is None else environ
    if RENDER_MAX_ENV not in environ:
        return DEFAULT_RENDER_MAX
    text = environ[RENDER_MAX_ENV].strip().lower()
    if not text:
        return None
    try:
        width, height = (int(v) for v in text.split("x"))
    except ValueError:
        raise ValueError(f"{RENDER_MAX_ENV} must be WxH (e.g. 1280x720) or empty, got {text!r}") from None
    if width <= 0 or height <= 0:
        raise ValueError(f"{RENDER_MAX_ENV} must be positive, got {text!r}")
    return width, height


def fit_render(width, height, cap):
    """창 (width, height) 를 비율 그대로 cap 상자 안으로. cap 이 None 이거나 이미 안이면 그대로. 짝수로 맞춘다."""
    if cap is None:
        return width, height
    scale = min(1.0, cap[0] / width, cap[1] / height)
    if scale >= 1.0:
        return width, height
    return max(2, int(width * scale) // 2 * 2), max(2, int(height * scale) // 2 * 2)


def window_half(side, screen=(1920, 1080), environ=None):
    """SimulationApp config for Isaac on one half of the screen (재범 9/18 발표 화면: Isaac left, 관제 웹 right).
    Isaac Sim 5.1 SimulationApp turns window_width/window_height into --/app/window/width|height and width/height into
    the render resolution --/app/renderer/resolution/*; extra_args are appended after them. Position is
    /app/window/x|y and the saved size /persistent/app/window/* (omni.appwindow settings; saveSizeOnExit is on by
    default, so the saved size is set too). The render resolution follows the window so the image is not letterboxed
    to 16:9. The render resolution is then fitted inside render_max() (P3_RENDER_MAX), keeping that aspect."""
    # "full" = 촬영 테이크(재범 9/24 14:4x): 창이 화면 전체라 뷰포트를 화면 해상도로 찍는다.
    width = int(screen[0]) if side == "full" else int(screen[0]) // 2
    height = int(screen[1])
    x = 0 if side in ("left", "full") else int(screen[0]) - width
    render_width, render_height = fit_render(width, height, render_max(environ))
    return {"window_width": width, "window_height": height, "width": render_width, "height": render_height,
            "extra_args": [f"--/app/window/x={x}", "--/app/window/y=0",
                           f"--/persistent/app/window/width={width}", f"--/persistent/app/window/height={height}",
                           "--/app/window/maximized=false", "--/persistent/app/window/maximized=false"]}
