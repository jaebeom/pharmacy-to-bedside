"""Diagnostics for unexplained ends and belt physics. Isaac imports stay inside functions.

9/17 master02: window mode runs ended with kit_running=False after 12-788 wall s, no timeline STOP, screen not idle
or locked. These hooks record who asked Kit to quit and where Kit writes its own log.
"""

import traceback

# carb logging settings. /log/file is the Kit log path; /log/fileFlushLevel is our reading of carb's logging settings
# (flush every line at or above this level so the end of the file survives a hard exit). Not verified on 5.1.
KIT_LOG_SETTINGS = ("/log/file", "/log/fileFlushLevel", "/log/level", "/log/fileLogLevel")


def kit_log_args(path, verbose=False):
    """Extra Kit command-line arguments that fix the Kit log file path (empty path: keep Kit's default). verbose also
    writes Verbose lines to that file (large: 9/17 an Info-level file had no line before an unexplained STOP)."""
    if not path:
        return []
    args = [f"--/log/file={path}", "--/log/fileAppend=false", "--/log/fileFlushLevel=verbose"]
    if verbose:
        # Both thresholds (review A1): lowering only the file level can leave the global filter in the way.
        args += ["--/log/fileLogLevel=verbose", "--/log/level=verbose"]
    return args


def timeline_state():
    """Kit timeline times and looping at this moment, for a STOP nobody asked for. Missing methods are named."""
    import omni.timeline

    timeline = omni.timeline.get_timeline_interface()
    out = {}
    for name in ("get_current_time", "get_start_time", "get_end_time", "is_looping", "is_playing", "is_stopped",
                 "get_time_codes_per_seconds"):
        method = getattr(timeline, name, None)
        try:
            out[name] = method() if method is not None else "missing"
        except Exception as exc:  # diagnostics must not end the stage
            out[name] = f"<{type(exc).__name__}>"
    return out


def python_stack(frames=12):
    return " | ".join(line.strip().replace("\n", " ") for line in traceback.format_stack()[-frames - 1:-1])


def public_fields(obj, limit=12):
    """name=value for an object's public non-callable attributes (for binding responses whose fields we have not
    confirmed on 5.1)."""
    out = []
    for name in dir(obj):
        if name.startswith("_"):
            continue
        try:
            value = getattr(obj, name)
        except Exception as exc:  # a binding property can raise; record it instead
            value = f"<{type(exc).__name__}>"
        if callable(value):
            continue
        out.append(f"{name}={value}")
        if len(out) >= limit:
            break
    return out


def kit_log_settings():
    import carb.settings

    settings = carb.settings.get_settings()
    return {key: settings.get(key) for key in KIT_LOG_SETTINGS}


def subscribe_quit(log):
    """Log POST_QUIT (someone requested Kit to quit) with the Python stack at that moment. Returns the subscription
    (keep it alive) or None. Isaac Sim 5.1.0 uses the same stream in isaacsim.code_editor.jupyter:
    omni.kit.app.get_app().get_shutdown_event_stream() and omni.kit.app.POST_QUIT_EVENT_TYPE."""
    import omni.kit.app

    try:
        stream = omni.kit.app.get_app().get_shutdown_event_stream()
        post_quit = omni.kit.app.POST_QUIT_EVENT_TYPE
    except Exception as exc:  # diagnostics must not end the stage
        log(f"quit_watch unavailable reason={type(exc).__name__}: {exc}")
        return None

    def on_event(event):
        kind = "POST_QUIT" if event.type == post_quit else f"type={event.type}"
        try:
            payload = dict(event.payload)
        except Exception:  # payload may not be a mapping
            payload = str(getattr(event, "payload", None))
        stack = " | ".join(line.strip().replace("\n", " ") for line in traceback.format_stack()[-8:-1])
        log(f"kit_shutdown_event {kind} payload={payload} python_stack={stack}")

    try:
        subscription = stream.create_subscription_to_pop(on_event, name="p3sim.quit_watch", order=0)
    except Exception as exc:  # diagnostics must not end the stage
        log(f"quit_watch unavailable reason={type(exc).__name__}: {exc}")
        return None
    log("quit_watch on=shutdown_event_stream(POST_QUIT) window_close=못 찾음(5.1 API 미확인)")
    return subscription


def query_rigid_body(stage, path, log, label):
    """PhysX property query of a rigid body and its colliders (what PhysX parsed, not the USD attributes).
    Query API as in Isaac Sim's URDF exporter: omni.physx.get_physx_property_query_interface().query_prim with
    PhysxPropertyQueryMode.QUERY_RIGID_BODY_WITH_COLLIDERS. Response fields are dumped generically."""
    try:
        from omni.physx import get_physx_property_query_interface
        from omni.physx.bindings._physx import PhysxPropertyQueryMode
        from pxr import PhysicsSchemaTools, UsdUtils
    except ImportError as exc:
        log(f"physx_query {label} unavailable reason={exc}")
        return
    lines = []
    try:
        cache = UsdUtils.StageCache.Get()
        stage_id = cache.GetId(stage).ToLongInt()
        if not stage_id:
            cache.Insert(stage)
            stage_id = cache.GetId(stage).ToLongInt()
        get_physx_property_query_interface().query_prim(
            stage_id=stage_id,
            prim_id=PhysicsSchemaTools.sdfPathToInt(path),
            query_mode=PhysxPropertyQueryMode.QUERY_RIGID_BODY_WITH_COLLIDERS,
            rigid_body_fn=lambda info: lines.append("rigid_body " + " ".join(public_fields(info))),
            collider_fn=lambda info: lines.append("collider " + " ".join(public_fields(info))),
        )
    except Exception as exc:  # diagnostics must not end the stage
        log(f"physx_query {label} path={path} failed {type(exc).__name__}: {exc}")
        return
    if not lines:
        log(f"physx_query {label} path={path} no response")
    for line in lines:
        log(f"physx_query {label} path={path} {line}")


def contact_kind(impulse, separation, touch_gap=0.001):
    """'touch' when PhysX pushed (impulse > 0) or the shapes overlap/touch; 'near' for a pair only inside the contact
    offset. 재범 실습3 (9/18): every reported pair had impulse 0 with contact points about 0.1 m in front of the
    shelf and dispenser faces, i.e. proximity reports rather than collisions (our reading)."""
    if impulse > 0.0 or (separation is not None and separation <= touch_gap):
        return "touch"
    return "near"


class ContactPairLog:
    """Which pairs touched, throttled: first touch of a pair, then at most every `every_s` sim seconds while it lasts.
    Pure (no Isaac); ContactWatch feeds it."""

    def __init__(self, every_s=2.0):
        self.every_s = every_s
        self.last = {}
        self.counts = {}

    def add(self, a, b, now_s):
        """Returns True when this touch should be logged."""
        key = tuple(sorted((a, b)))
        self.counts[key] = self.counts.get(key, 0) + 1
        last = self.last.get(key)
        if last is None or now_s - last >= self.every_s:
            self.last[key] = now_s
            return True
        return False

    def count(self, a, b):
        return self.counts.get(tuple(sorted((a, b))), 0)


def watch_contacts(stage, body_paths, log, now_s, ignore_inside=None, every_s=2.0, thresholds=None):
    """PhysX contact reports for body_paths (robot links, rail carriages, held canister): log who touched whom.

    재범 실습1 P2 ("the robot is pushed by some pillar"): names the prim instead of guessing from coordinates. Uses
    PhysxSchema.PhysxContactReportAPI (threshold 0) applied before the first play, and
    omni.physx get_physx_simulation_interface().subscribe_contact_report_events (as in Isaac's proximity/contact
    sensors). Pairs where both prims are under ignore_inside (the robot's own links) are skipped. Returns the
    subscription (keep it alive) or None.

    `thresholds` maps a body path to its report threshold in newtons; everything else stays at 0 (report every
    contact). A body that is **always resting on something** needs a threshold above its own weight, or PhysX
    reports the resting pair every step: 9/23 병원 한 바퀴에서 약통 18개가 선반에 얹혀 있어
    `getMaterialFromInternalFaceIndex` 경고가 419,292 줄 나고 rtf 가 0.34 로 떨어졌다."""
    try:
        from omni.physx import get_physx_simulation_interface
        from omni.physx.bindings._physx import ContactEventType
        from pxr import PhysicsSchemaTools, PhysxSchema
    except ImportError as exc:
        log(f"contact_watch unavailable reason={exc}")
        return None
    applied = 0
    for path in body_paths:
        prim = stage.GetPrimAtPath(path)
        if not prim.IsValid() or prim.IsInstanceProxy():
            continue
        PhysxSchema.PhysxContactReportAPI.Apply(prim).CreateThresholdAttr().Set(
            float((thresholds or {}).get(path, 0.0)))
        applied += 1
    offsets = {}
    try:
        from pxr import Usd, UsdPhysics

        for path in body_paths:
            for prim in Usd.PrimRange(stage.GetPrimAtPath(path), Usd.TraverseInstanceProxies()):
                if not prim.HasAPI(UsdPhysics.CollisionAPI):
                    continue
                contact = prim.GetAttribute("physxCollision:contactOffset")
                rest = prim.GetAttribute("physxCollision:restOffset")
                key = (contact.Get() if contact and contact.HasAuthoredValue() else "default",
                       rest.Get() if rest and rest.HasAuthoredValue() else "default")
                offsets[key] = offsets.get(key, 0) + 1
    except Exception as exc:  # diagnostics only
        offsets = {"error": f"{type(exc).__name__}: {exc}"}
    log(f"contact_watch collider offsets (contactOffset, restOffset) -> count: {offsets}")
    pairs = ContactPairLog(every_s)
    wanted = (ContactEventType.CONTACT_FOUND, ContactEventType.CONTACT_PERSIST)

    def on_report(headers, data):
        try:
            for header in headers:
                if header.type not in wanted:
                    continue
                a = str(PhysicsSchemaTools.intToSdfPath(header.collider0))
                b = str(PhysicsSchemaTools.intToSdfPath(header.collider1))
                if ignore_inside and a.startswith(ignore_inside) and b.startswith(ignore_inside):
                    continue
                now = now_s()
                if not pairs.add(a, b, now):
                    continue
                impulse = [0.0, 0.0, 0.0]
                position = None
                separation = None
                for i in range(header.contact_data_offset, header.contact_data_offset + header.num_contact_data):
                    point = data[i]
                    impulse = [s + float(v) for s, v in zip(impulse, point.impulse, strict=True)]
                    position = point.position
                    gap = float(point.separation)
                    separation = gap if separation is None else min(separation, gap)
                magnitude = sum(v * v for v in impulse) ** 0.5
                kind = "found" if header.type == ContactEventType.CONTACT_FOUND else "persist"
                where = "-" if position is None else "[" + ", ".join(f"{float(v):.3f}" for v in position) + "]"
                log(f"contact {kind} {contact_kind(magnitude, separation)} a={a} b={b} impulse={magnitude:.4f} "
                    f"sep={'-' if separation is None else f'{separation:.4f}'} at={where} "
                    f"count={pairs.count(a, b)} sim_time={now:.3f}")
        except Exception as exc:  # a diagnostics callback must not break the physics step
            log(f"contact_watch callback error {type(exc).__name__}: {exc}")

    try:
        subscription = get_physx_simulation_interface().subscribe_contact_report_events(on_report)
    except Exception as exc:  # diagnostics must not end the stage
        log(f"contact_watch unavailable reason={type(exc).__name__}: {exc}")
        return None
    log(f"contact_watch on bodies={applied} ignore_inside={ignore_inside or '-'} every_s={every_s}")
    return subscription


def moved_part_center(part, rail_positions):
    """World centre of a rail part (layout_v2.rail_parts entry) at the given rail joint positions {'x':, 'y':, 'z':}."""
    offset = {"x": 0, "y": 1, "z": 2}
    center = list(part["center"])
    for axis in part["moves"]:
        center[offset[axis]] += float(rail_positions.get(axis, 0.0))
    return center


def robot_rail_overlaps(parts, rail_positions, robot_prefix, skip=(("LiftPlate", "base_link"),)):
    """PhysX scene overlap of each rail part box with the robot's colliders. The rail carriages have no collision
    (the robot is in the same articulation, whose self-collision is off), so contact reports cannot see the robot
    passing through its own rail (재범 실습7-a 9/18); an overlap query can. Returns [(part name, robot body path)].
    Scene query as in Isaac's UR10 palletizing example: get_physx_scene_query_interface().overlap_box."""
    import carb
    from omni.physx import get_physx_scene_query_interface

    query = get_physx_scene_query_interface()
    found = []
    for part in parts:
        if part["name"] == "Track":
            continue
        hits = []

        def on_hit(hit, hits=hits):
            body = str(hit.rigid_body)
            if body.startswith(robot_prefix):
                hits.append(body)
            return True  # keep going

        center = moved_part_center(part, rail_positions)
        half = [s / 2.0 for s in part["size"]]
        query.overlap_box(carb.Float3(*half), carb.Float3(*center), carb.Float4(0.0, 0.0, 0.0, 1.0), on_hit, False)
        for body in sorted(set(hits)):
            if any(part["name"] == p and body.endswith("/" + link) for p, link in skip):
                continue
            found.append((part["name"], body))
    return found


class A1Probe:
    """Exit-cause probe from the 9/18 external review (docs/analysis/2026-09-18-jaebeom-a1-a4-code-review.md, A1
    "확인 실험 1"): push and pop subscriptions on the Kit shutdown, timeline (STOP only) and app-window close streams,
    kept for the whole run, and the raw Kit state checked right before every evaluation of the loop condition — also
    headless, because our keep_running() ignores app_running=False there, so "headless never stopped" was no
    evidence. One JSON line per event or state change: `a1_probe {...}` (print, flush). The stop condition itself is
    not changed. A callback's Python stack is the receiver's, not the sender's."""

    def __init__(self, emit=None):
        self.refs = []  # subscriptions live as long as this object
        self.last = None
        self.emit = emit or self._print

    @staticmethod
    def _print(kind, **fields):
        import json
        import threading
        import time

        print("a1_probe " + json.dumps(dict(kind=kind, wall_ns=time.time_ns(), mono_ns=time.monotonic_ns(),
                                            tid=threading.get_ident(), **fields), default=str, ensure_ascii=False),
              flush=True)

    def _event(self, label, event):
        import omni.timeline

        if label.startswith("timeline:") and event.type != int(omni.timeline.TimelineEventType.STOP):
            return
        try:
            payload = dict(event.payload)
        except Exception:  # payload may not be a mapping
            payload = repr(getattr(event, "payload", None))
        self.emit(label, event_type=int(event.type), payload=payload, stack=traceback.format_stack(limit=10))

    def _watch(self, label, stream):
        import functools

        for phase in ("push", "pop"):
            subscribe = getattr(stream, "create_subscription_to_" + phase)
            self.refs.append(subscribe(functools.partial(self._event, label + ":" + phase),
                                       name="p3.a1." + label + "." + phase))

    def install(self):
        import omni.kit.app
        import omni.timeline

        kit = omni.kit.app.get_app()
        try:
            self.emit("build", kit=kit.get_build_version())
        except Exception as error:  # diagnostics must not end the stage
            self.emit("unavailable", target="build", error=repr(error))

        def window_close():
            import omni.appwindow

            return omni.appwindow.get_default_app_window().get_window_close_event_stream()

        for label, get_stream in (
            ("shutdown", kit.get_shutdown_event_stream),
            ("timeline", lambda: omni.timeline.get_timeline_interface().get_timeline_event_stream()),
            ("window_close", window_close),
        ):
            try:
                self._watch(label, get_stream())
            except Exception as error:  # e.g. no app window when headless
                self.emit("unavailable", target=label, error=repr(error))
        return self

    def poll(self, simulation_app):
        """Call right before the loop condition is evaluated. Emits only when the raw state changes."""
        import omni.kit.app

        kit = omni.kit.app.get_app()
        state = (kit.is_running(), simulation_app.is_exiting(), simulation_app.context.get_stage() is None)
        if state != self.last:
            self.emit("state", kit_running=state[0], wrapper_exiting=state[1], stage_missing=state[2],
                      update_number=kit.get_update_number())
            self.last = state


def surface_snapshot(stage, path):
    """Read-only view of a conveyor body (review A4 "확인 실험 2"): surface velocity attributes and the body's
    composed world axes (lengths 1, orthogonal, determinant +1 when no scale or mirror reaches the body)."""
    from pxr import Gf, PhysxSchema, Usd, UsdGeom

    prim = stage.GetPrimAtPath(path)
    if not prim.IsValid():
        raise ValueError("missing body: " + path)
    matrix = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    axes = [matrix.TransformDir(Gf.Vec3d(*axis)) for axis in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]
    api = PhysxSchema.PhysxSurfaceVelocityAPI(prim)
    names = ("physxSurfaceVelocity:surfaceVelocity", "physxSurfaceVelocity:surfaceVelocityLocalSpace",
             "physxSurfaceVelocity:surfaceVelocityEnabled")
    return {
        "path": path,
        "meters_per_unit": UsdGeom.GetStageMetersPerUnit(stage),
        "has_surface_api": bool(api),
        "attrs": {name: prim.GetAttribute(name).Get() if prim.GetAttribute(name) else None for name in names},
        "world_axis_lengths": [round(axis.GetLength(), 6) for axis in axes],
        "world_axis_dot": [round(Gf.Dot(axes[0], axes[1]), 6), round(Gf.Dot(axes[0], axes[2]), 6),
                           round(Gf.Dot(axes[1], axes[2]), 6)],
        "world_basis_det": round(Gf.Dot(axes[0], Gf.Cross(axes[1], axes[2])), 6),
    }
