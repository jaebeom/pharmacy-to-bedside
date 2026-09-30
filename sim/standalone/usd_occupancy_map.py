#!/usr/bin/env python3
"""USD 장면의 기하에서 Nav2 용 2D occupancy map(pgm + yaml)을 만든다. Isaac 을 띄우지 않는다.

    python3 sim/standalone/usd_occupancy_map.py --usd <로컬화한 scene.usda> --out-dir <dir> --name hospital \
        --source-sha-of sim/scenes/hospital_navigationv1.usda --source-name sim/scenes/hospital_navigationv1.usda \
        --skip /World/ridgeback_ur5 --skip /World/PouchTemplate [--resolution 0.05] [--z-min 0.10] [--z-max 1.80]

원격 자산 접두는 먼저 `localize_isaac_assets.py` 로 로컬 경로로 바꾼다(usd-core 는 https 를 풀지 못한다).
pxr·numpy 가 필요하다(usd-core 또는 Isaac python).

무엇을 재는가:
- 보이는(`visibility` 가 invisible 이 아닌) 활성 `UsdGeom.Mesh` 전부의 삼각형 가운데, z 범위가 [z-min, z-max] 와
  겹치는 것을 바닥 평면에 투영해 칸을 막는다. 수직 벽은 투영하면 선이 되므로 모서리도 그린다.
- 렌더 기하다 — 충돌체가 아니다. 충돌이 꺼진 물체(예: 조제기 visual)도 막힌 칸이 된다(주행 쪽에서는 보수적이다).
- 바깥 경계에서 채워 들어간 빈칸은 건물 밖이라 unknown(205)으로 둔다.

한계(그대로 적는다): Isaac `isaacsim.asset.gen.omap` 생성기(PhysX 충돌 기반)와 대조하지 않았다. 경사진 큰 삼각형은
z 범위와 겹치기만 해도 투영 전체를 막는다(과대 추정). 문짝은 USD 에 저작된 자세 그대로다.

yaml 원점은 map 격자의 왼쪽 아래 칸 모서리다(Nav2 map_server 규약). 격자 축은 USD world 축과 같다(계약 3절).
"""
import argparse
import hashlib
import math
import os
import sys


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--usd", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--name", default="hospital")
    p.add_argument("--resolution", type=float, default=0.05)
    p.add_argument("--z-min", type=float, default=0.10, help="이보다 낮은 기하(바닥·문턱)는 막지 않는다")
    p.add_argument("--z-max", type=float, default=1.80, help="이보다 높은 기하(천장·문 위 벽)는 막지 않는다")
    p.add_argument("--margin", type=float, default=0.5, help="장면 bbox 둘레 여백 m")
    p.add_argument("--root", action="append", default=None,
                   help="이 경로 아래만 본다(여러 번 가능). 기본은 가상 루트 전체 — defaultPrim 밖 병상도 포함")
    p.add_argument("--source-name", default=None, help="yaml 에 적을 원본 이름(기본은 --usd 파일 이름)")
    p.add_argument("--source-sha-of", default=None, help="sha256 을 잴 원본(접두를 바꾸기 전 파일). 기본은 --usd")
    p.add_argument("--skip", action="append", default=[],
                   help="이 경로 아래는 막지 않는다(여러 번). 예: 움직이는 로봇 /World/ridgeback_ur5")
    return p.parse_args(argv)


def fan_triangles(counts, indices):
    """faceVertexCounts/Indices → (i0, i1, i2) 삼각형 목록(부채꼴 분할)."""
    tris = []
    k = 0
    for c in counts:
        for j in range(1, c - 1):
            tris.append((indices[k], indices[k + j], indices[k + j + 1]))
        k += c
    return tris


def main(argv=None):
    args = parse_args(argv)
    import numpy as np
    from pxr import Usd, UsdGeom

    stage = Usd.Stage.Open(args.usd)
    if stage is None:
        sys.exit(f"cannot open {args.usd}")
    xc = UsdGeom.XformCache(Usd.TimeCode.Default())
    roots = [stage.GetPrimAtPath(r) for r in args.root] if args.root else [stage.GetPseudoRoot()]
    skips = tuple(s.rstrip("/") for s in args.skip)
    zmin, zmax = args.z_min, args.z_max

    segs = []    # (N, 2, 2) 선분
    fills = []   # (M, 3, 2) 채울 삼각형
    lo = np.array([math.inf, math.inf])
    hi = -lo
    meshes = tris_kept = 0
    for root in roots:
        for prim in Usd.PrimRange(root, Usd.TraverseInstanceProxies(Usd.PrimAllPrimsPredicate)):
            path = prim.GetPath().pathString
            if skips and any(path == s or path.startswith(s + "/") for s in skips):
                continue
            if not prim.IsActive() or not prim.IsA(UsdGeom.Mesh):
                continue
            img = UsdGeom.Imageable(prim)
            if img.ComputeVisibility() == UsdGeom.Tokens.invisible:
                continue
            if img.ComputePurpose() in (UsdGeom.Tokens.guide, UsdGeom.Tokens.proxy):
                continue
            mesh = UsdGeom.Mesh(prim)
            pts = mesh.GetPointsAttr().Get()
            counts = mesh.GetFaceVertexCountsAttr().Get()
            idx = mesh.GetFaceVertexIndicesAttr().Get()
            if not pts or not counts or not idx:
                continue
            m = np.array(xc.GetLocalToWorldTransform(prim), dtype=float)  # row-vector 규약
            p = np.asarray(pts, dtype=float)
            w = p @ m[:3, :3] + m[3, :3]
            t = np.asarray(fan_triangles(list(counts), list(idx)), dtype=np.int64)
            if t.size == 0:
                continue
            tz = w[:, 2][t]
            keep = (tz.max(axis=1) >= zmin) & (tz.min(axis=1) <= zmax)
            if not keep.any():
                continue
            meshes += 1
            t = t[keep]
            tris_kept += len(t)
            xy = w[:, :2][t]                      # (K, 3, 2)
            lo = np.minimum(lo, xy.reshape(-1, 2).min(axis=0))
            hi = np.maximum(hi, xy.reshape(-1, 2).max(axis=0))
            segs.append(np.stack([xy[:, [0, 1]], xy[:, [1, 2]], xy[:, [2, 0]]], axis=1).reshape(-1, 2, 2))
            area = 0.5 * np.abs((xy[:, 1, 0] - xy[:, 0, 0]) * (xy[:, 2, 1] - xy[:, 0, 1])
                                - (xy[:, 2, 0] - xy[:, 0, 0]) * (xy[:, 1, 1] - xy[:, 0, 1]))
            big = area > (args.resolution ** 2) * 0.25
            if big.any():
                fills.append(xy[big])
    if not segs:
        sys.exit("no geometry in the z band")

    res = args.resolution
    x0 = math.floor((lo[0] - args.margin) / res) * res
    y0 = math.floor((lo[1] - args.margin) / res) * res
    w_cells = int(math.ceil((hi[0] + args.margin - x0) / res))
    h_cells = int(math.ceil((hi[1] + args.margin - y0) / res))
    occ = np.zeros((h_cells, w_cells), dtype=bool)   # [row=y 칸, col=x 칸], row 0 = y0 쪽

    def mark(xs, ys):
        c = np.floor((xs - x0) / res).astype(np.int64)
        r = np.floor((ys - y0) / res).astype(np.int64)
        ok = (c >= 0) & (c < w_cells) & (r >= 0) & (r < h_cells)
        occ[r[ok], c[ok]] = True

    s = np.concatenate(segs)
    length = np.hypot(s[:, 1, 0] - s[:, 0, 0], s[:, 1, 1] - s[:, 0, 1])
    n = np.maximum(1, np.ceil(length / (res * 0.5)).astype(np.int64)) + 1
    rep = np.repeat(np.arange(len(s)), n)
    frac = np.concatenate([np.linspace(0.0, 1.0, k) for k in n])
    mark(s[rep, 0, 0] + frac * (s[rep, 1, 0] - s[rep, 0, 0]), s[rep, 0, 1] + frac * (s[rep, 1, 1] - s[rep, 0, 1]))

    if fills:
        f = np.concatenate(fills)
        cx = (np.arange(w_cells) + 0.5) * res + x0
        cy = (np.arange(h_cells) + 0.5) * res + y0
        for tri in f:
            c0 = max(0, int((tri[:, 0].min() - x0) / res))
            c1 = min(w_cells - 1, int((tri[:, 0].max() - x0) / res))
            r0 = max(0, int((tri[:, 1].min() - y0) / res))
            r1 = min(h_cells - 1, int((tri[:, 1].max() - y0) / res))
            if c1 < c0 or r1 < r0:
                continue
            gx, gy = np.meshgrid(cx[c0:c1 + 1], cy[r0:r1 + 1])
            (ax, ay), (bx, by), (qx, qy) = tri
            d = (by - qy) * (ax - qx) + (qx - bx) * (ay - qy)
            if abs(d) < 1e-12:
                continue
            l1 = ((by - qy) * (gx - qx) + (qx - bx) * (gy - qy)) / d
            l2 = ((qy - ay) * (gx - qx) + (ax - qx) * (gy - qy)) / d
            inside = (l1 >= 0) & (l2 >= 0) & (l1 + l2 <= 1)
            occ[r0:r1 + 1, c0:c1 + 1] |= inside

    # 건물 밖: 경계의 빈칸에서 4-이웃으로 채운다 → unknown
    outside = np.zeros_like(occ)
    stack = [(r, c) for r in range(h_cells) for c in (0, w_cells - 1) if not occ[r, c]]
    stack += [(r, c) for c in range(w_cells) for r in (0, h_cells - 1) if not occ[r, c]]
    while stack:
        r, c = stack.pop()
        if outside[r, c] or occ[r, c]:
            continue
        outside[r, c] = True
        for rr, cc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
            if 0 <= rr < h_cells and 0 <= cc < w_cells:
                stack.append((rr, cc))

    img = np.full((h_cells, w_cells), 254, dtype=np.uint8)   # free
    img[outside] = 205                                        # unknown
    img[occ] = 0                                              # occupied
    img = img[::-1]                                           # pgm 첫 줄 = 위(y 최대)

    os.makedirs(args.out_dir, exist_ok=True)
    pgm = os.path.join(args.out_dir, f"{args.name}.pgm")
    with open(pgm, "wb") as fh:
        fh.write(f"P5\n{w_cells} {h_cells}\n255\n".encode())
        fh.write(img.tobytes())
    with open(args.source_sha_of or args.usd, "rb") as fh:
        src_sha = hashlib.sha256(fh.read()).hexdigest()
    with open(pgm, "rb") as fh:
        pgm_sha = hashlib.sha256(fh.read()).hexdigest()
    yml = os.path.join(args.out_dir, f"{args.name}.yaml")
    with open(yml, "w") as fh:
        fh.write(
            "# 자동 생성물 — 손으로 고치지 않는다. sim/standalone/usd_occupancy_map.py\n"
            f"# source_usd: {args.source_name or os.path.basename(args.usd)} sha256 {src_sha}\n"
            f"# z_band: [{zmin}, {zmax}] m, render geometry (not PhysX collision), pgm sha256 {pgm_sha}\n"
            f"# skip: {list(skips)}\n"
            f"image: {args.name}.pgm\n"
            "mode: trinary\n"
            f"resolution: {res}\n"
            f"origin: [{x0:.3f}, {y0:.3f}, 0.0]\n"
            "negate: 0\n"
            "occupied_thresh: 0.65\n"
            "free_thresh: 0.196\n")
    free = int((img == 254).sum())
    print(f"meshes={meshes} triangles={tris_kept} grid={w_cells}x{h_cells} origin=({x0:.3f},{y0:.3f}) "
          f"occupied={int(occ.sum())} free={free} unknown={int(outside.sum())} -> {pgm}")


if __name__ == "__main__":
    main()
