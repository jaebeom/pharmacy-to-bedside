"""Print the pharmacy scene v2 layout as the /m0609/shelf/inventory JSON, without Isaac (plain Python 3).

For the arm session's clearance model (#168 clearance.py Box(name, center, size)) and teach planning: the same
cells, targets and obstacle boxes the stage publishes, every canister present. Placeholder dimensions
(p3sim/layout_v2.py).

    python3 sim/standalone/pharmacy_layout_json.py --scene v2 > /tmp/pharmacy_v2.json
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def build(argv=None):
    import pharmacy_stage as stage  # imports no Isaac module at load time (sim/tests checks it)

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--zones", choices=("emptyworld",),
                        help="빈월드 zones.yaml(계약 3절)을 대신 낸다. 값의 단일 출처는 layout.full_loop_zones 다")
    parser.add_argument("--routes", choices=("emptyworld",),
                        help="빈월드 routes.yaml(주행 routes.py 스키마)을 대신 낸다. 단일 출처는 layout.routes 다")
    parser.add_argument("--scene", choices=("v2",), default="v2")
    known, rest = parser.parse_known_args(argv)
    if known.routes:
        return {"_zones": stage.roomlib.routes_yaml_text()}  # 본문 그대로. PyYAML 을 쓰지 않는다
    if known.zones:
        return {"_zones": stage.roomlib.zones_yaml_text()}  # 본문 그대로. PyYAML 을 쓰지 않는다
    args = stage.parse_args(["--scene", known.scene, *rest])
    layout = stage.room(args)["v2"]
    return stage.layout_v2.inventory(layout["cells"], {}, layout["targets"], layout["obstacles"],
                                     rail=stage.v2_rail_info(args))


def main(argv=None):
    built = build(argv)
    if "_zones" in built:
        print(built["_zones"], end="")
        return
    print(json.dumps(built, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
