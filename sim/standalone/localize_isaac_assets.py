#!/usr/bin/env python3
"""씬이 참조하는 Isaac 공개 자산 USD 레이어를 로컬에 받고, 원격 접두를 로컬 경로로 바꾼 씬 사본을 만든다.

    python3 sim/standalone/localize_isaac_assets.py --usd sim/scenes/hospital_navigationv1.usda \
        --cache ~/isaac_cache --out /tmp/hospital_navigationv1.local.usda

usd-core 는 https 자산을 풀지 못한다. 이 스크립트는 **USD 레이어만**(텍스처 제외) 받아 pxr 로 좌표·기하를 읽을 수
있게 한다 — 앵커 추출(extract_hospital_anchors.py)과 지도(usd_occupancy_map.py) 용이다. 렌더에는 쓰지 않는다.
9/23 기준 병원 씬은 레이어 322개, 약 170 MB 였다. 이미 받은 파일은 다시 받지 않는다.
"""
import argparse
import os
import sys
import urllib.parse
import urllib.request
from collections import deque

BASE = "https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/5.1/"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--usd", required=True)
    p.add_argument("--cache", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--base", default=BASE)
    args = p.parse_args(argv)
    from pxr import Sdf

    cache = os.path.abspath(os.path.expanduser(args.cache))

    def local(url):
        return os.path.join(cache, urllib.parse.unquote(url[len(args.base):]))

    queue, seen, fetched, missing = deque(), set(), 0, []

    def deps(layer, base_url):
        for path in layer.GetCompositionAssetDependencies():
            if not path.lower().split("?")[0].endswith((".usd", ".usda", ".usdc")):
                continue
            url = path if path.startswith("http") else (urllib.parse.urljoin(base_url, path) if base_url else None)
            if url and url.startswith(args.base) and url not in seen:
                seen.add(url)
                queue.append(url)

    deps(Sdf.Layer.FindOrOpen(args.usd), None)
    while queue:
        url = queue.popleft()
        dst = local(url)
        if not os.path.exists(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            try:
                urllib.request.urlretrieve(url.replace(" ", "%20"), dst)
            except OSError as exc:
                missing.append(f"{url}: {exc}")
                continue
        fetched += 1
        layer = Sdf.Layer.FindOrOpen(dst)
        if layer:
            deps(layer, url)
    with open(args.usd, encoding="utf-8") as fh:
        text = fh.read()
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(text.replace(args.base, cache.rstrip("/") + "/"))
    print(f"layers={fetched} missing={len(missing)} -> {args.out}")
    for line in missing:
        print("MISSING", line, file=sys.stderr)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
