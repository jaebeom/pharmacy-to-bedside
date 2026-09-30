"""Four-outlet sorter rules. No Isaac imports at module import time."""

import json
from pathlib import Path

from . import common

ROUTES = {
    1: "junction_2",
    2: "junction_4",
    3: "junction_9",
    4: None,
}

JUNCTIONS = ("junction_2", "junction_4", "junction_9")


def _usd_value(attribute, value):
    """Convert JSON vector values to the matching USD vector type."""
    if not isinstance(value, list):
        return value
    from pxr import Gf

    constructors = {
        "float2": Gf.Vec2f, "float3": Gf.Vec3f, "float4": Gf.Vec4f,
        "double2": Gf.Vec2d, "double3": Gf.Vec3d, "double4": Gf.Vec4d,
    }
    constructor = constructors.get(str(attribute.GetTypeName()))
    return constructor(*value) if constructor else value


class SorterRouter:
    """Select one of three reroutes, or the default fourth outlet."""

    def __init__(self, stage, config_path, log=None):
        self.stage = stage
        self.log = log or common.Logger("[sorter]")
        path = Path(config_path).expanduser().resolve()
        self.config = json.loads(path.read_text(encoding="utf-8"))
        self._validate()

    def _attribute(self, path):
        attribute = self.stage.GetAttributeAtPath(path)
        if not attribute or not attribute.IsValid():
            raise RuntimeError(f"sorter attribute not found: {path}; run --inspect-sorters")
        return attribute

    def _validate(self):
        for name in JUNCTIONS:
            attribute = self._attribute(self.config[name]["reroute_attribute"])
            if str(attribute.GetTypeName()) != "bool":
                raise TypeError(f"{attribute.GetPath()} must be bool, got {attribute.GetTypeName()}")

    def route_to(self, outlet):
        if outlet not in ROUTES:
            raise ValueError("outlet must be 1, 2, 3, or 4")
        writes = [
            (self._attribute(self.config[name]["reroute_attribute"]),
             name == ROUTES[outlet])
            for name in JUNCTIONS
        ]
        previous = [(attribute, attribute.Get()) for attribute, _value in writes]
        try:
            for attribute, value in writes:
                if not attribute.Set(_usd_value(attribute, value)):
                    raise RuntimeError(f"failed to set {attribute.GetPath()}")
        except Exception:
            for attribute, old_value in previous:
                attribute.Set(old_value)
            raise
        state = " ".join(f"{name}={'active' if name == ROUTES[outlet] else 'inactive'}"
                         for name in JUNCTIONS)
        self.log(f"route={outlet} {state}")


def print_candidate_attributes(stage, log=print):
    """Print graph variables under conveyor/sorter prims for configuration."""
    count = 0
    for prim in stage.Traverse():
        prim_path = str(prim.GetPath()).lower()
        if "conveyor" not in prim_path and "sorter" not in prim_path:
            continue
        for attribute in prim.GetAttributes():
            name = attribute.GetName().lower()
            reroute_value = "reroute" in prim_path and name == "inputs:value"
            if reroute_value or "graph:variable" in name or "direction" in name:
                log(f"attr={attribute.GetPath()} type={attribute.GetTypeName()} value={attribute.Get()}")
                count += 1
    if count == 0:
        log("no sorter graph variables found")
