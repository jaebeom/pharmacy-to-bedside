"""도는 ROS 스택을 녹화해 mock fixture 를 만든다. 손으로 JSON 을 고치지 말고 다시 녹화하라.

실물 브리지(`app.ros_bridge.BridgeNode`)를 그대로 쓴다 — 구독 토픽·QoS·변환이 실물 모드와 같다.
받은 것을 `{"t": sim s(첫 프레임 0), "kind", "data"}` 로 적는다. kind 는 `app.mock.apply_frame` 이
받는 것과 같다(event·order·dispenser·belt·signal·cabinet·log).

하트비트(signal·belt·dispenser)는 **값이 바뀔 때만** 적는다. 재생기가 마지막 값을 계속 다시 실어
주므로(mock.MockPlayer) 5 Hz 를 다 적을 필요가 없다. /rosout 은 WARN 이상만(실물 모드와 같다).

    source /opt/ros/jazzy/setup.bash && source <ws>/install/setup.bash
    cd web/backend && python fixtures/record_fixture.py --out fixtures/hospital_trip.json --duration 90 \\
        --name hospital_trip --description "…"

녹화 중에 요청은 웹(`--allow-commands` 로 띄운 다른 백엔드)이나 발행기가 낸다. 이 도구는 듣기만 한다.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

#: 값이 바뀔 때만 적는 kind. 비교할 때 뺄 키(매번 바뀌는 시각).
ON_CHANGE = {"signal": (), "belt": ("stamp",), "dispenser": ("stamp",)}


def dump_fixture(fixture: dict) -> str:
    """머리는 들여 쓰고 프레임은 한 줄에 하나 — diff 가 프레임 단위로 읽히고 파일이 작다."""
    head = {k: v for k, v in fixture.items() if k != "frames"}
    lines = [json.dumps(f, ensure_ascii=False, separators=(",", ":")) for f in fixture["frames"]]
    body = json.dumps(head, ensure_ascii=False, indent=1)[:-2]
    return body + ',\n "frames": [\n  ' + ",\n  ".join(lines) + "\n ]\n}\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", required=True)
    p.add_argument("--duration", type=float, default=60.0, help="녹화할 wall 초")
    p.add_argument("--name", required=True)
    p.add_argument("--description", default="")
    p.add_argument("--note", action="append", default=[], help="notes 에 넣을 한 줄(여러 번)")
    p.add_argument("--robot-id", default="amr_1")
    args = p.parse_args(argv)

    import rclpy
    from rclpy.executors import SingleThreadedExecutor

    from app.ros_bridge import BridgeNode
    from app.ros_convert import LOG_WARN

    lock = threading.Lock()
    frames: list[dict] = []
    sim = {"now": None}
    last: dict[tuple, object] = {}

    def submit(kind: str, payload) -> None:
        with lock:
            if kind == "clock":
                sim["now"] = float(payload)
                return
            if sim["now"] is None:
                return   # /clock 을 보기 전 것은 시각을 모른다
            if kind == "log" and payload.get("level_value", 0) < LOG_WARN:
                return
            if kind in ON_CHANGE:
                key = (kind, payload.get("key") if kind == "signal" else None)
                value = {k: v for k, v in payload.items() if k not in ON_CHANGE[kind]}
                if last.get(key) == value:
                    return
                last[key] = value
            frames.append({"t": sim["now"], "kind": kind, "data": payload})

    context = rclpy.Context()
    context.init()
    node = BridgeNode(submit, robot_id=args.robot_id, context=context)
    executor = SingleThreadedExecutor(context=context)
    executor.add_node(node)
    thread = threading.Thread(target=executor.spin, daemon=True)
    thread.start()
    time.sleep(args.duration)
    executor.shutdown()
    node.destroy_node()
    context.try_shutdown()

    if not frames:
        print("받은 프레임이 없다 — ROS_DOMAIN_ID 와 스택을 확인하라", file=sys.stderr)
        return 1
    t0 = frames[0]["t"]
    for f in frames:
        f["t"] = round(f["t"] - t0, 3)
    epochs = [f["data"].get("epoch") for f in frames if f["kind"] == "event" and f["data"].get("epoch")]
    fixture = {"name": args.name, "description": args.description,
               "start_epoch": min(epochs) if epochs else 1,
               "duration_sim_s": frames[-1]["t"],
               "notes": ["web/backend/fixtures/record_fixture.py 로 녹화했다 — 손으로 고치지 않는다.", *args.note],
               "frames": frames}
    Path(args.out).write_text(dump_fixture(fixture), encoding="utf-8")
    kinds = {}
    for f in frames:
        kinds[f["kind"]] = kinds.get(f["kind"], 0) + 1
    print(f"{args.out}: 프레임 {len(frames)}개 {kinds}, sim {fixture['duration_sim_s']} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
