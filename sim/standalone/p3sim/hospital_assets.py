"""Resolve the hospital scene and optional custom-asset ZIP. No Isaac imports."""

import hashlib
import os
import shutil
import zipfile


def _safe_extract(archive, destination):
    root = destination.resolve()
    for member in archive.infolist():
        target = (destination / member.filename).resolve()
        if target != root and root not in target.parents:
            raise RuntimeError(f"unsafe path in asset ZIP: {member.filename}")
    archive.extractall(destination)


def _extract_once(zip_path, runtime_dir):
    zip_path = zip_path.expanduser().resolve()
    if not zip_path.is_file():
        raise FileNotFoundError(f"custom asset ZIP not found: {zip_path}")
    key = hashlib.sha256(str(zip_path).encode()).hexdigest()[:12]
    output = runtime_dir / "custom_assets" / f"{zip_path.stem}_{key}"
    marker = output / ".source"
    signature = f"{zip_path.stat().st_size}:{zip_path.stat().st_mtime_ns}"
    if marker.is_file() and marker.read_text(encoding="utf-8") == signature:
        return output
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    with zipfile.ZipFile(zip_path) as archive:
        _safe_extract(archive, output)
    marker.write_text(signature, encoding="utf-8")
    return output


def _custom_root(candidate, required_files):
    candidate = candidate.expanduser().resolve()
    if all((candidate / relative).is_file() for relative in required_files):
        return candidate
    matches = [
        directory for directory in candidate.rglob("*")
        if directory.is_dir() and all((directory / relative).is_file() for relative in required_files)
    ]
    if len(matches) != 1:
        raise RuntimeError(f"expected one nested custom asset root, found {len(matches)} under {candidate}")
    return matches[0]


def resolve_scene(*, standalone_dir, scene, custom_assets, custom_assets_zip,
                  isaac_assets_root, runtime_dir):
    """Return (runtime_scene, USD search paths), using the repository preparer."""
    standalone_dir = standalone_dir.resolve()
    repo_root = standalone_dir.parents[1]
    requested_runtime_dir = runtime_dir
    runtime_dir = (runtime_dir.expanduser().resolve() if runtime_dir else
                   repo_root / "sim" / "scenes")
    archive_runtime_dir = (runtime_dir if requested_runtime_dir else
                           repo_root / "sim" / "outputs" / "hospital_runtime")
    runtime_dir.mkdir(parents=True, exist_ok=True)

    if scene is not None:
        scene = scene.expanduser().resolve()
        if not scene.is_file() or scene.suffix.lower() not in {".usd", ".usda", ".usdc"}:
            raise FileNotFoundError(f"hospital USD not found: {scene}")
        return scene, _search_paths(scene.parent)

    from prepare_hospital_scene import REQUIRED_CUSTOM_FILES, prepare_scene

    candidate = (_extract_once(custom_assets_zip, archive_runtime_dir)
                 if custom_assets_zip is not None else custom_assets)
    root = _custom_root(candidate, REQUIRED_CUSTOM_FILES)
    output = runtime_dir / "hospital_runtime.usda"
    digest = prepare_scene(root, isaac_assets_root, output)
    print(f"[hospital_assets] scene_sha256={digest}", flush=True)
    return output, _search_paths(output.parent, root)


def _search_paths(*paths):
    items = [str(path.resolve()) for path in paths]
    items.extend(value for value in os.environ.get("PXR_AR_DEFAULT_SEARCH_PATH", "").split(os.pathsep) if value)
    return list(dict.fromkeys(items))
