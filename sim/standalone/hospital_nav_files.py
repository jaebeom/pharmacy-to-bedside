#!/usr/bin/env python3
"""병원 씬 zones·routes 파일을 앵커 JSON 과 occupancy map 에서 만든다(표준 라이브러리만).

    python3 sim/standalone/hospital_nav_files.py --zones  > src/rokey_p3_description/config/zones.hospital.yaml
    python3 sim/standalone/hospital_nav_files.py --routes > src/rokey_p3_description/config/routes.hospital.yaml
    python3 sim/standalone/hospital_nav_files.py --report   # 정차 자세·경로 여유·못 이은 쌍·팔 IK
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from p3sim import hospital_nav as hn  # noqa: E402


# 원본 실행: docs/practice/simworld/practice-45.md.
# 측정한 탁자 정착점과 접근 자세다. 기본 병원/다른 자산의 보정값으로 쓰지 않는다.
RECEIVER_LOAD = (-8.26605892, 4.10165615, -math.pi / 2)
RECEIVER_BELT_END = {"x": -8.26605892, "y": 4.90165615, "z": 0.36554548, "yaw": -1.5708}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--zones", action="store_true")
    g.add_argument("--routes", action="store_true")
    g.add_argument("--report", action="store_true")
    p.add_argument("--receiver", action="store_true",
                   help="9/29 master02 카메라 배송의 탁자 정착 좌표를 사용한다")
    args = p.parse_args(argv)
    grid = hn.load_map()
    anchors = hn.load_anchors()
    poses = hn.zone_poses(grid, anchors)
    if args.receiver:
        poses["load"]["pose"] = RECEIVER_LOAD
        poses["load"]["note"] = "9/29 master02 탁자 정착 카메라 배송"
        # 재범 9/29 B안 "그 자리에서 바로": A1 충전 도크 = 적재 자리. dock_1 에서 탁자 정착점까지 팔 밑동 수평이
        # 0.741 m 라 적재 한도(REACH_MAX_LOAD 0.70)를 넘는다 — 도크를 성공 회차의 적재 자리로 옮긴다.
        poses[hn.LOAD_DOCK] = dict(poses["load"], note="PDF A1 충전 도크 = 적재 자리(탁자 정착, 재범 9/29 B안)")
    if args.zones:
        doc = hn.zones_doc(poses)
        if args.receiver:
            for zone in ("load", hn.LOAD_DOCK):   # 도크 = 적재(오케스트레이터 load_is_dock 이 같은 자세로 본다)
                doc["zones"][zone].update(zip(("x", "y", "yaw"), RECEIVER_LOAD, strict=True))
            doc["pharmacy"]["belt_end"] = RECEIVER_BELT_END
        sys.stdout.write(hn.zones_yaml_text(doc))
        return
    pairs, clear, missing = hn.routes(grid, poses)
    if args.routes:
        if missing:
            sys.exit(f"경로를 못 이은 쌍: {missing}")
        sys.stdout.write(hn.routes_yaml_text(pairs))
        return
    for name, e in poses.items():
        pose = e["pose"]
        if pose is None:
            print(f"{name:10s} 정차 자세 없음 — {e['note']}")
            continue
        x, y, yaw = pose
        reach = f"밑동↔목표 {e['reach']:.2f} " if e.get("reach") else ""
        print(f"{name:10s} ({x:7.3f},{y:7.3f}, yaw {math.degrees(yaw):6.1f}) {reach}여유 {grid.clearance(x, y):.2f} m "
              f"회전반경 {hn.TURN_RADIUS:.2f} {'OK' if grid.clearance(x, y) >= hn.TURN_RADIUS else '제자리 회전 불가'}"
              f" — {e['note']}")
    for name, e in poses.items():
        if e["pose"] is not None:
            print(f"  {name:10s} 접근점 {hn.approach_point(grid, e['pose'])}")
    ik_report(grid, poses)
    worst = sorted(clear.items(), key=lambda kv: kv[1])[:8]
    print("가장 좁은 경로:", ", ".join(f"{a}→{b} {c:.2f}" for (a, b), c in worst))
    print("못 이은 쌍:", missing or "없음")


def ik_report(grid, poses):
    """정차 자세에서 목표(창구 받침·보관함 윗면)를 위에서 누르는 자세로 UR5 IK 가 풀리는가(표준 DH, 수치해).

    밑동 높이는 amr_base.arm_base_world_z()(받침 0.15 포함). 목표 = 윗면 + 0.02(놓기), 접근 = 윗면 + 0.10.
    밑동 yaw 는 도달에 영향이 없다(어깨 pan 이 ±2π) — 수평 거리와 높이만 본다. numpy 가 없으면 건너뛴다.
    """
    try:
        import numpy as np
        sys.path.insert(0, os.path.join(hn.REPO, "src", "rokey_p3_manipulation"))
        from rokey_p3_manipulation import ur5_kinematics as uk
    except ImportError as exc:
        print(f"IK 미실행: {exc}")
        return
    base_z = hn.amr_base.arm_base_world_z()
    home = np.array([0.0, -1.2, 1.6, -1.97, -1.57, 0.0])
    print(f"IK: 팔 밑동 월드 z {base_z:.3f} (표준 UR5 DH, 한계 {uk.UR5_ASSET_LIMITS[2]} elbow)")
    for name, e in poses.items():
        if e["pose"] is None or name == "station_a":
            continue
        x, y, yaw = e["pose"]
        bx, by = hn._rot(yaw, hn.ARM_X, 0.0)
        bx, by = x + bx, y + by
        if e["cabinet"]:
            tx, ty, tz = e["cabinet"]
        else:
            shelf = hn.load_anchors()["outlets"][{v: k for k, v in hn.DOCK_ZONE.items()}.get(name, "A1")]["shelf"]
            tx, ty, tz = shelf["center"][0], shelf["center"][1], shelf["max"][2]
        r = math.hypot(tx - bx, ty - by)
        rows = []
        for label, lift in (("놓기", 0.02), ("접근", 0.10)):
            target = np.eye(4)
            target[:3, :3] = np.diag([1.0, -1.0, -1.0])   # 도구 z 가 아래를 본다
            target[:3, 3] = (r, 0.0, tz + lift - base_z)
            res = uk.solve_ik(target, home, limits=uk.UR5_ASSET_LIMITS)
            q3 = abs(math.sin(res.joints[2]))
            rows.append(f"{label} {'OK' if res.ok else 'X'} sin|q3| {q3:.2f}")
        print(f"  {name:10s} 수평 {r:.2f} 높이차 {tz - base_z:+.2f} — " + ", ".join(rows))


if __name__ == "__main__":
    main()
