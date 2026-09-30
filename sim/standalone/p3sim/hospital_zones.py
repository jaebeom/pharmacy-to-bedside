"""zones yaml(계약 3절 형식) -> 스테이지의 `layout["zones"]`. Isaac·PyYAML 없이 돈다.

병원 전체 preset(#527 H1)용이다. 빈월드는 zone 자세를 layout.full_loop_zones 에서 만들고, 병원은
`src/rokey_p3_description/config/zones.hospital.yaml`(hospital_nav 가 만든 파일)에서 읽는다.
스테이지는 이 사전을 보관함 센서(`<zone>/cabinet`)·인식표(`<zone>` 정차 자세)·구역 프림에 쓴다.

모양은 full_loop_zones 와 같다: {이름: (x, y, z, yaw)}.
- zone 자체(`load`·`dock_N`·`bed_*`·`station_*`)는 z 0.0 이다(정차 자세는 바닥 위다).
- `cabinet`·`tag` 가 있는 zone 은 `<zone>/cabinet`·`<zone>/tag` 를 더 낸다. cabinet z 는 **윗면**이다
  (truth_sensors.in_cabinet 의 뜻).
- `pharmacy:` 고정 프레임은 zone 이 아니라서 넣지 않는다(pharmacy_frames_from_yaml 로 따로 읽는다).

PyYAML 을 쓰지 않는다: Isaac python 과 L1 의 sim 잡에 없을 수 있다(layout.zones_yaml_text 와 같은 이유).
읽는 문법은 우리 생성기(layout.zones_yaml_text·hospital_nav.zones_yaml_text)가 쓰는 만큼뿐이다 —
두 칸 들여쓰기의 사전, 값은 수·문자열, 주석은 `#`. 목록·따옴표·흐름 문법은 받지 않고 ValueError 로 멈춘다.
"""

import os

#: zone 도착 공차 키. 자세가 아니라서 layout["zones"] 에 안 들어간다.
TOLERANCE_KEYS = ("tol_xy", "tol_yaw")
SUB_POSES = ("cabinet", "tag")


def _scalar(text):
    try:
        return int(text) if text.lstrip("-").isdigit() else float(text)
    except ValueError:
        return text


def parse(text):
    """들여쓰기 사전만 있는 YAML 본문 -> 중첩 dict. 값은 int·float·str 이다."""
    root = {}
    stack = [(-1, root)]  # (들여쓰기, 그 깊이의 사전)
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        body = line.strip()
        if "\t" in raw[:indent + 1] or body.startswith(("-", "[", "{")) or ":" not in body:
            raise ValueError(f"{number}행: 들여쓰기 사전만 읽는다: {raw!r}")
        key, value = (part.strip() for part in body.split(":", 1))
        while indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if key in parent:
            raise ValueError(f"{number}행: 키가 겹친다: {key}")
        if value:
            if value[0] in "[{\"'|>&*!":
                raise ValueError(f"{number}행: 수·문자열 값만 읽는다: {raw!r}")
            parent[key] = _scalar(value)
        else:
            parent[key] = {}
            stack.append((indent, parent[key]))
    return root


def _read(text_or_path):
    """본문이거나 파일 경로. 줄바꿈이 없고 파일이 있으면 경로로 본다."""
    text_or_path = os.fspath(text_or_path)
    if "\n" not in text_or_path and os.path.isfile(text_or_path):
        with open(text_or_path, encoding="utf-8") as handle:
            return handle.read()
    return text_or_path


def load_doc(text_or_path):
    """zones yaml -> {"frame", "zones", ["pharmacy"]} 사전(파일 모양 그대로)."""
    doc = parse(_read(text_or_path))
    if not isinstance(doc.get("zones"), dict) or not doc["zones"]:
        raise ValueError("zones: 사전이 없다")
    if doc.get("frame") != "map":
        raise ValueError(f"frame 이 map 이 아니다: {doc.get('frame')!r}")
    return doc


def _pose(entry, where, z_default=None):
    try:
        z = float(entry["z"]) if z_default is None else z_default
        return (float(entry["x"]), float(entry["y"]), z, float(entry["yaw"]))
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"{where}: x·y·yaw{'' if z_default is not None else '·z'} 가 수가 아니다") from error


def zones_from_doc(doc):
    """load_doc 결과 -> layout["zones"] 모양 {이름: (x, y, z, yaw)}."""
    zones = {}
    for name, entry in doc["zones"].items():
        if not isinstance(entry, dict):
            raise ValueError(f"zones.{name}: 사전이 아니다")
        zones[name] = _pose(entry, f"zones.{name}", z_default=0.0)
        for sub in SUB_POSES:
            if sub in entry:
                zones[f"{name}/{sub}"] = _pose(entry[sub], f"zones.{name}.{sub}")
    return zones


def zones_from_yaml(text_or_path):
    """zones yaml 본문 또는 경로 -> 스테이지의 layout["zones"]. 모양은 layout.full_loop_zones 와 같다."""
    return zones_from_doc(load_doc(text_or_path))


def tolerances_from_yaml(text_or_path):
    """{zone: {"tol_xy", "tol_yaw"}}. 스테이지는 지금 layout.ZONE_TOL 을 쓴다 — 파일 값이 다르면 여기서 본다."""
    doc = load_doc(text_or_path)
    return {name: {key: float(entry[key]) for key in TOLERANCE_KEYS if key in entry}
            for name, entry in doc["zones"].items()}


def pharmacy_frames_from_yaml(text_or_path):
    """`pharmacy:` 고정 프레임 {이름: (x, y, z, yaw)}. 없으면 빈 사전(병원 파일은 아직 없다)."""
    doc = load_doc(text_or_path)
    return {name: _pose(entry, f"pharmacy.{name}") for name, entry in (doc.get("pharmacy") or {}).items()}


def station_tables(text_or_path):
    """놓는 테이블이 있는 스테이션 zone 이름들(kind station + cabinet) — station_b·station_c·station_d.

    재범 규칙(9/25 03:3x): 병동 → B, 병실 → C 테이블. 테이블에는 스테이션 인식표(`st-<zone>`)가 붙는다.
    보관함이 없는 station_a(간호사실 데스크 앞)는 빠진다.
    """
    zones = load_doc(text_or_path)["zones"]
    return sorted(name for name, entry in zones.items()
                  if isinstance(entry, dict) and entry.get("kind") == "station" and "cabinet" in entry)
