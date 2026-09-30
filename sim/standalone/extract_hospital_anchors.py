#!/usr/bin/env python3
"""병원 씬(hospital_navigationv1)에서 주행·전달에 쓰는 앵커(병상·협탁·간호데스크·문·컨베이어 출구)를 뽑는다.

    python3 sim/standalone/extract_hospital_anchors.py --usd <원격 접두를 로컬로 바꾼 씬 사본> \
        > sim/scenes/hospital_navigationv1.anchors.json

Isaac 을 띄우지 않는다(pxr 만 쓴다 — usd-core 또는 Isaac 의 python). 자산은 원격 URL 을 그대로 두면 풀리지 않으므로
공개 자산 서버의 레이어를 로컬에 받아 접두를 바꾼 사본을 준다(`localize_isaac_assets.py`).

**어느 프림이 PDF 의 어느 표시인가는 아래 표가 정한다**(재범 P3_Map.pdf, 9/22 — A1–A4 도크, B 간호스테이션,
C1·C2 병실, D1–D10 병상). 이름으로 추측하지 않는다. 표에 적은 프림이 없거나 비활성이면 실패한다.
"""
import argparse
import hashlib
import json
import math
import sys

#: PDF 표시 → 프림. #523(9/23) 씬에서 병상은 x 23·26·29 격자로 다시 놓였고 D5–D10 도 `/World` 안으로 들어왔다.
#: 대응은 좌표로 정했다 — 옛 앵커의 PDF 표시별 자리(행·열)와 같은 칸의 프림이다.
BEDS = {
    "D1": "/World/Environment/hospital/SM_HospitalBed_02d4_01",   # (23, 9.0)
    "D2": "/World/Environment/hospital/SM_HospitalBed_02d4",      # (26, 9.0)
    "D3": "/World/Environment/hospital/SM_HospitalBed_02d4_03",   # (23, 4.1)
    "D4": "/World/Environment/hospital/SM_HospitalBed_02d4_02",   # (26, 4.1)
    "D5": "/World/Environment/hospital/SM_HospitalBed_02d4_08",   # (23, 1.6)
    "D6": "/World/Environment/hospital/SM_HospitalBed_02d4_07",   # (26, 1.6)
    "D7": "/World/Environment/hospital/SM_HospitalBed_02d4_06",   # (29, 1.6)
    "D8": "/World/Environment/hospital/SM_HospitalBed_02d4_09",   # (23, −3.1)
    "D9": "/World/Environment/hospital/SM_HospitalBed_02d4_05",   # (26, −3.1)
    "D10": "/World/Environment/hospital/SM_HospitalBed_02d4_04",  # (29, −3.1)
}
#: 병상 발치의 협탁(보관함 후보). #523 씬에서 D3 에도 협탁이 생겼다.
TABLES = {
    "D1": "/World/Environment/hospital/SM_BedSideTable_01b3_01",
    "D2": "/World/Environment/hospital/SM_BedSideTable_01b3",
    "D3": "/World/Environment/hospital/SM_BedSideTable_01b3_03",
    "D4": "/World/Environment/hospital/SM_BedSideTable_01b3_02",
    "D5": "/World/Environment/hospital/SM_BedSideTable_01b2_04",
    "D6": "/World/Environment/hospital/SM_BedSideTable_01b2_03",
    "D7": "/World/Environment/hospital/SM_BedSideTable_01b2_02",
    "D8": "/World/Environment/hospital/SM_BedSideTable_01b_136",
    "D9": "/World/Environment/hospital/SM_BedSideTable_01b_135",
    "D10": "/World/Environment/hospital/SM_BedSideTable_01b_134",
}
#: B = 간호스테이션 데스크(두 조각을 합친 bbox).
DESK = ("/World/Environment/hospital/SM_ReceptionDesk_01a_46",
        "/World/Environment/hospital/SM_ReceptionDesk_01a2_52")
#: 병실 출입구. #523 씬은 문짝과 문턱을 없애고 벽 개구부를 넓혔다(C1 은 북쪽 하나만 남았다).
#: 개구부는 문 벽 메시를 z `DOOR_SLICE_Z` 에서 잘라 가장 긴 빈 구간으로 잰다.
DOORS = {
    "C1": "/World/Environment/hospital/Geo_M1_DoorWall24",
    "C2": "/World/Environment/hospital/Geo_O_DoorWall_918",
}
DOOR_SLICE_Z = 1.0
#: 컨베이어 창구 1–4(#476: 1번 창구 = 트랙 02 … 4번 창구 = 모두 꺼짐 → 끝 트랙 10) 와 그 앞 받침(작은 탁자).
#: PDF A1–A4 는 이 네 창구 앞이다. #523 씬에서 받침 프림 이름이 바뀌었다(x 가 같은 것끼리 짝지었다).
OUTLETS = {
    "A1": ("/World/Conveyor/ConveyorTrack_02", "/World/Environment/hospital/SM_SideTable_02a_74"),
    "A2": ("/World/Conveyor/ConveyorTrack_04", "/World/Environment/hospital/SM_SideTable_02a_77"),
    "A3": ("/World/Conveyor/ConveyorTrack_09", "/World/Environment/hospital/SM_SideTable_02a_79"),
    "A4": ("/World/Conveyor/ConveyorTrack_10", "/World/Environment/hospital/SM_SideTable_02a_78"),
}
#: 씬에 박혀 있던 합본 로봇. #523 최종본(9/23)은 이것을 뺐다 — 있으면 적고 없으면 null 이다(실패가 아니다).
#: 주행 스테이지는 있든 없든 자기 AMR 합본을 만든다.
EMBEDDED_ROBOT = "/World/ridgeback_ur5"


def _r(v):
    return round(float(v), 4)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--usd", required=True)
    p.add_argument("--source-name", default="sim/scenes/hospital_navigationv1.usda",
                   help="JSON 에 적을 원본 이름. sha256 은 --source-sha-of 파일로 잰다")
    p.add_argument("--source-sha-of", default=None, help="sha256 을 잴 원본(접두를 바꾸기 전 파일). 기본은 --usd")
    args = p.parse_args(argv)
    from pxr import Usd, UsdGeom

    stage = Usd.Stage.Open(args.usd)
    if stage is None:
        sys.exit(f"cannot open {args.usd}")
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
    xc = UsdGeom.XformCache(Usd.TimeCode.Default())
    default_prim = stage.GetDefaultPrim().GetPath().pathString
    problems = []

    def box(path):
        prim = stage.GetPrimAtPath(path)
        if not prim or not prim.IsActive():
            problems.append(f"missing or inactive: {path}")
            return None
        r = cache.ComputeWorldBound(prim).ComputeAlignedRange()
        if r.IsEmpty():
            problems.append(f"empty bbox: {path}")
            return None
        lo, hi = r.GetMin(), r.GetMax()
        m = xc.GetLocalToWorldTransform(prim)
        yaw = math.degrees(math.atan2(m[0][1], m[0][0]))
        return {"prim": path, "min": [_r(v) for v in lo], "max": [_r(v) for v in hi],
                "center": [_r((lo[i] + hi[i]) / 2) for i in range(3)], "yaw_deg": _r(yaw),
                "outside_default_prim": not (path == default_prim or path.startswith(default_prim + "/"))}

    def door(path):
        """문 벽을 z 에서 잘라 가장 긴 빈 y 구간. 벽이 x 축에 나란하다(두 문 벽 모두 그렇다)."""
        wall = box(path)
        if wall is None:
            return None
        spans = []
        for p in Usd.PrimRange(stage.GetPrimAtPath(path), Usd.TraverseInstanceProxies(Usd.PrimAllPrimsPredicate)):
            if not p.IsA(UsdGeom.Mesh):
                continue
            mesh = UsdGeom.Mesh(p)
            m = xc.GetLocalToWorldTransform(p)
            pts = [m.Transform(v) for v in mesh.GetPointsAttr().Get()]
            idx = mesh.GetFaceVertexIndicesAttr().Get()
            k = 0
            for c in mesh.GetFaceVertexCountsAttr().Get():
                face = [pts[i] for i in idx[k:k + c]]
                k += c
                if min(v[2] for v in face) <= DOOR_SLICE_Z <= max(v[2] for v in face):
                    spans.append((min(v[1] for v in face), max(v[1] for v in face)))
        spans.sort()
        gaps, end = [], spans[0][1]
        for a, b in spans[1:]:
            if a > end:
                gaps.append((end, a))
            end = max(end, b)
        if not gaps:
            problems.append(f"no opening at z {DOOR_SLICE_Z}: {path}")
            return None
        lo, hi = max(gaps, key=lambda g: g[1] - g[0])
        mn = [wall["min"][0], _r(lo), 0.0]
        mx = [wall["max"][0], _r(hi), 0.0]
        return {"prim": path, "min": mn, "max": mx, "center": [_r((mn[i] + mx[i]) / 2) for i in range(3)],
                "width": _r(hi - lo), "slice_z": DOOR_SLICE_Z, "outside_default_prim": False}

    beds = {k: box(v) for k, v in BEDS.items()}
    tables = {k: (box(v) if v else None) for k, v in TABLES.items()}
    desk_parts = [box(v) for v in DESK]
    doors = {k: door(v) for k, v in DOORS.items()}
    outlets = {k: {"track": box(t), "shelf": box(s)} for k, (t, s) in OUTLETS.items()}
    robot = box(EMBEDDED_ROBOT) if stage.GetPrimAtPath(EMBEDDED_ROBOT) else None
    if problems:
        sys.exit("\n".join(problems))
    lo = [min(b["min"][i] for b in desk_parts) for i in range(3)]
    hi = [max(b["max"][i] for b in desk_parts) for i in range(3)]
    desk = {"prims": list(DESK), "min": lo, "max": hi, "center": [_r((lo[i] + hi[i]) / 2) for i in range(3)]}
    with open(args.source_sha_of or args.usd, "rb") as fh:
        sha = hashlib.sha256(fh.read()).hexdigest()
    doc = {
        "schema_version": 1,
        "source": {"usd": args.source_name, "sha256": sha, "default_prim": default_prim,
                   "note": "bbox 는 렌더 기하의 world 축 정렬 상자다. 단위 m, map = USD world(계약 3절)."},
        "beds": beds, "bedside_tables": tables, "nursing_desk": desk, "doors": doors,
        "outlets": outlets, "embedded_robot": robot,
    }
    json.dump(doc, sys.stdout, ensure_ascii=False, indent=1)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
