"""평면도 — Nav2 지도(`maps/<월드>.yaml` + `.pgm`)를 읽어 화면에 넘긴다. 순수(ROS import 없음).

`--map-file` 을 준 실행에서만 켜진다. 안 주면 `/api/map` 은 404 `map_unavailable` 이고 나머지 동작은
그대로다(병원 월드가 아닌 실행). 원문(**주행 레인 소유 — 읽기만 한다**):

    image: hospital.pgm
    resolution: 0.05
    origin: [-12.250, -6.500, 0.0]
    negate: 0
    occupied_thresh: 0.65
    free_thresh: 0.196

**픽셀 ↔ map 좌표.** PGM 첫 행이 지도의 **위(y 최대)** 다(map_server 규약). 칸 (col, row) 의 중심은
    x = origin_x + (col + 0.5) · resolution
    y = origin_y + (height − row − 0.5) · resolution
origin 의 yaw 는 0 이 아니면 화면이 돌려야 한다 — 병원 지도는 0 이다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

#: 화면에 옮기는 map yaml 키. 모르는 키는 싣지 않는다.
MAP_KEYS = ("resolution", "origin", "negate", "occupied_thresh", "free_thresh")


class MapError(ValueError):
    """지도를 못 읽었다. 메시지가 그대로 사람에게 간다."""


def pgm_size(path: Path) -> tuple[int, int]:
    """P5(binary) PGM 의 (width, height). 머리만 읽는다. 주석 줄(`#`)을 건너뛴다."""
    with path.open("rb") as fh:
        head = fh.read(1024)
    tokens: list[bytes] = []
    for line in head.split(b"\n"):
        line = line.split(b"#", 1)[0]
        tokens += line.split()
        if len(tokens) >= 4:
            break
    if len(tokens) < 4 or tokens[0] != b"P5":
        raise MapError(f"P5 PGM 이 아니다: {path.name}")
    try:
        return int(tokens[1]), int(tokens[2])
    except ValueError as exc:
        raise MapError(f"PGM 크기를 못 읽었다: {path.name}") from exc


def load_map(yaml_path: str | Path) -> dict[str, Any]:
    """map yaml → `{"image_path", "width", "height", resolution, origin, ...}`. 못 읽으면 MapError."""
    p = Path(yaml_path)
    if not p.is_file():
        raise MapError(f"지도 파일이 없다: {p}")
    try:
        import yaml
        doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - 남의 레인 파일이 깨졌다고 우리가 죽지 않는다
        raise MapError(f"지도 yaml 을 못 읽었다: {exc}") from exc
    if not isinstance(doc, dict) or not doc.get("image"):
        raise MapError("지도 yaml 에 image 가 없다")
    missing = [k for k in ("resolution", "origin") if k not in doc]
    if missing:
        raise MapError(f"지도 yaml 에 {', '.join(missing)} 가 없다")
    image = (p.parent / str(doc["image"])).resolve()
    if not image.is_file():
        raise MapError(f"지도 이미지가 없다: {image}")
    width, height = pgm_size(image)
    out: dict[str, Any] = {"image_path": image, "width": width, "height": height}
    for key in MAP_KEYS:
        if key in doc:
            out[key] = [float(v) for v in doc[key]] if key == "origin" else doc[key]
    return out


def map_meta(loaded: dict[str, Any], source: str) -> dict[str, Any]:
    """`GET /api/map` 본문. 이미지는 경로가 아니라 URL 로 준다."""
    return {"source": source, "frame": "map", "image_url": "/api/map/image",
            "width": loaded["width"], "height": loaded["height"],
            **{k: loaded[k] for k in MAP_KEYS if k in loaded}}
