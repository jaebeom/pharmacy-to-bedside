"""Resolve the lightweight hospital scene against separately supplied assets."""

import argparse
import hashlib
from pathlib import Path


SCENE_TEMPLATE = Path(__file__).resolve().parents[1] / "scenes" / "hospital_layout.usda"
CUSTOM_TOKEN = "__P3_CUSTOM_ASSET_ROOT__"
ISAAC_TOKEN = "__P3_ISAAC_ASSET_ROOT__"
REQUIRED_CUSTOM_FILES = (
    "material/etc/Automatic+Blister+Packing+Machine+(DPB-80)/model.usd",
)


def prepare_scene(custom_assets: Path, isaac_assets_root: str, output: Path) -> str:
    custom_assets = custom_assets.expanduser().resolve()
    missing = [name for name in REQUIRED_CUSTOM_FILES if not (custom_assets / name).is_file()]
    if missing:
        raise ValueError(f"custom assets missing: {', '.join(missing)}")

    isaac_assets_root = isaac_assets_root.rstrip("/")
    if not isaac_assets_root:
        raise ValueError("--isaac-assets-root must point to Assets/Isaac/5.1")
    for value in (str(custom_assets), isaac_assets_root):
        if "@" in value or "\n" in value:
            raise ValueError("asset paths cannot contain '@' or a newline")

    template = SCENE_TEMPLATE.read_text(encoding="utf-8")
    if template.count(CUSTOM_TOKEN) != 1 or template.count(ISAAC_TOKEN) != 39:
        raise ValueError("unexpected asset references in hospital scene template")
    scene = template.replace(CUSTOM_TOKEN, custom_assets.as_posix())
    scene = scene.replace(ISAAC_TOKEN, isaac_assets_root)

    output = output.expanduser().resolve()
    if output in (SCENE_TEMPLATE, custom_assets):
        raise ValueError("output must differ from the template and asset directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(scene, encoding="utf-8")
    return hashlib.sha256(scene.encode("utf-8")).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--custom-assets", type=Path, required=True)
    parser.add_argument("--isaac-assets-root", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        digest = prepare_scene(args.custom_assets, args.isaac_assets_root, args.output)
    except ValueError as exc:
        parser.error(str(exc))
    print(f"scene={args.output.expanduser().resolve()} sha256={digest}")


if __name__ == "__main__":
    main()
