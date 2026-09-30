"""hospital-full-acceptance-v1 metrics from one or more attempt-folder roots (aggregate_runs.py calls this).

No ROS import. One root is what the master observer keeps per attempt (마클1 campaign1 attempt 1,
#240 5824106296·5824117929): `logs/<stamp>-{stage,arm,nav,stack}.log`,
`event_run/{events,order_status,orders,cabinet}.jsonl` + `meta.json`, `boot_check.txt`, `record_qa*.txt` or
`SUMMARY.txt`, `speed.csv` (wall,stamp,…), `up.log`, `demo_v2-env.txt`, optional `phase.log`·`film.log`, a
hospital_orders `summary.md` and, for phase F, `STEPS.md` + `step-assets.log`. `logs/*-kit.log` repeats the stage
lines and is not read.

Phase E (다중 PC, attempt 12·13) splits one attempt across two roots — master01 (stage) and master02
(arm·nav·stack·web·event_run) — because P3_ROLES puts them on different hosts. `--run` may be given more than once
(작전 9/27 카드); `Folder` then merges: each log type (`*-stage.log` etc.) comes from whichever root has it (there is
normally one), `event_run/*` comes from the first root that has `event_run/meta.json`, `record_qa` lines are summed
across every root's files (each host records its own screen), and `up.log`/`speed.csv` use the earliest-starting
root and the first root that has `speed.csv`, respectively — with a note when more than one root offered a
`speed.csv` (host clocks are not reconciled beyond that). Single-root callers pass one path, unchanged.

master02's own observer wrapper names things differently from master01's (마클1·마클2, #240 5851309536,
campaign2 attempt 12·13 real evidence: `boot_check.log` not `boot_check.txt`, `up.console` not `up.log`,
`demo_env.txt` not `demo_v2-env.txt`, `event_logger/<run_id>/` not `event_run/`). A given root that has an
`agg/` subfolder gets that subfolder added right after itself as a second search location — `agg/` is the
team's own symlink-adapter convention for exactly this mismatch (`agg/boot_check.txt -> ../boot_check.log`
etc.). A root without `agg/` is searched exactly as before (no behaviour change for master01-style folders).

`agg/`'s symlinks are absolute-path (`agg/event_run -> /home/rokey/markle_tmp/<folder>/event_logger/<run_id>`)
and only resolve if the evidence tarball is extracted to that exact literal path — campaign3 attempt12
(#240, 마클1·마클2) broke this by extracting one level deeper (`~/markle_tmp/m2-received/<folder>/`), leaving
every `agg/*` entry dangling and every metric that reads through it `record_missing` even though the raw
files were sitting right there on the root. So `FILE_ALIASES` and `_event_dirs()` below read `boot_check.log`
/`up.console`/`demo_env.txt`/`event_logger/*/meta.json` directly off the given root as well, independent of
whether `agg/` exists or its symlinks resolve — `agg/` still gets searched (harmless, and still needed for
files that have no raw-name fallback here, e.g. `speed.csv`), but no metric depends on it resolving anymore.

`boot_check.txt` is judged per root (마클2 9/27, #240 5848373269, campaign2 attempt 12·13): `window` can be skipped
on any root — a role-split run has no single screen with both Isaac and the browser, the same reason the protocol
already excuses it for an all-window capture rig. `viewport` can be skipped on a root that did not supply the stage
log (it has nothing to check), but not on the stage root itself, and at least one given root must have actually
passed `viewport` — a run where every root skipped it was never checked at all. Any other skip, or a `FAIL` line on
any root, fails the gate.

Rules are the protocol purpose 4 lines read literally. A source file that is absent gives null (record_missing) and a
note; a present file without the judged line gives 0 for a pass line. Values that need a person (fresh clone step
times) stay null with a note. The protocol text wins over this code; a mismatch is a bug here.
"""

import calendar
import json
import math
import re
import statistics
import time
from pathlib import Path

PROTOCOL_ID = "hospital-full-acceptance-v1"
#: v2(9/27, 재범 승인, #576 5851279552)는 purpose 4(c) boot_check 를 phase E(다중 PC)로 확장한 것뿐,
#: metrics·attempt 구조는 v1 과 같아 같은 규칙을 쓴다(experiments/protocols/hospital-full-acceptance-v2.json).
PROTOCOL_ID_V2 = "hospital-full-acceptance-v2"
#: v3(9/27, 재범 결정 #240 5854486187)는 §7(실패 처리) 판정선만 바꿨다(16/16 → 15/16 + 실패 기록 의무화) —
#: metrics·attempt 계산은 여기서 protocol_id 를 안 보므로 바뀔 게 없었다. 동결 뒤 커서 통합검증(#756
#: 5855093172)이 purpose 문장 불일치를 지적했지만 frozen protocol 은 못 고쳐 v4 로 대체했다(어느 run 도
#: v3 를 인용하지 않아 PROTOCOL_IDS 에는 넣지 않는다 — v4 만 추가).
PROTOCOL_ID_V4 = "hospital-full-acceptance-v4"
PROTOCOL_IDS = (PROTOCOL_ID, PROTOCOL_ID_V2, PROTOCOL_ID_V4)
#: master02 관측 래퍼의 원본 파일명(#240 5851309536) — `agg/` 심볼릭 링크가 (마스터 추출 경로가 심볼릭
#: 링크의 절대경로 기대와 다를 때, 예: campaign3 attempt12 `m2-received/` 한 단계 더 들어간 경우처럼) 깨져도
#: 이 이름들로 root 에 직접 있으면 찾는다 — `agg/` 는 그대로 두되(예: speed.csv 등 다른 파일은 여전히 덕을
#: 본다) 이 세 파일만큼은 심볼릭 링크에 의존하지 않는다.
FILE_ALIASES = {
    "boot_check.txt": ("boot_check.log",),
    "up.log": ("up.console",),
    "demo_v2-env.txt": ("demo_env.txt",),
}
TARGET_FPS = 30.0
POUCH_END_LIMIT_S = 60.0
SETTLE_LIMIT_M = 0.005
STOCK_CELLS = 18
REQUIRED_KINDS = ("cylinder", "module")
ORDERS10 = 10

# purpose 2: attempt index → phase. Phase-only metrics are null outside their attempts.
PHASES = {1: "A", 2: "A", 3: "A", 4: "A", 5: "A", 6: "B", 7: "C", 8: "C", 9: "D", 10: "D", 11: "B'",
          12: "E", 13: "E", 14: "seed", 15: "seed", 16: "F"}
PHASE_METRICS = {
    "orders10_delivered": {6},
    "orders_beds_all_delivered": {11},
    "orders10_multipc_delivered": {13},
    "reset_dock_pose_error_m": {7, 8},
    "reset_arm_park_error_rad": {7, 8},
    "fresh_clone_step_wall_s": {16},
    "fresh_clone_asset_sha_ok": {16},
}

ROS_STAMP = re.compile(r"\[(?:INFO|WARN|ERROR|DEBUG)\] \[(\d+\.\d+)\]")
UP_CLOCK = re.compile(r"^\[demo_v2 (\d\d):(\d\d):(\d\d)\]")
LOG_STAMP = re.compile(r"(\d{8})-(\d{6})-stage\.log$")
SPEED_LIMIT = re.compile(r"speed limit (\d+)%=[\d.]+ m/s \(여유 ([^,]*), 받은 코스트맵 (\d+)장\)")
CONTACT_TOUCH = re.compile(r"contact \w+ touch a=(\S+) b=(\S+)")
RECORD_QA = re.compile(r"record_qa: fps=([\d.]+) frames=\d+ dur=([\d.]+)s wall=[\d.]+s drop=(\d+) corrupt=(\d+)")
ENCOUNTER = re.compile(r"encounter (start|end) who=(\S+) dist_min=[\d.]+ sim=([\d.]+)")
VISION = re.compile(r"vision pouch (\S+): (\S+) 지연 (\d+) ms")
STEP_HEAD = re.compile(r"^### (\S+) (\d\d):(\d\d):(\d\d)")
STEP_END = re.compile(r"^끝 (\d\d):(\d\d):(\d\d) exit=(-?\d+)")
#: purpose 2 phase F: the one asset check is `sha256sum -c ../scenes/hospital_assets.sha256`. That file holds
#: f519fb2c… for hospital-custom-assets-20260918.zip — the protocol calls it the dispenser model.usd SHA-256, but
#: the repository keeps it only as the ZIP's (sim/scenes/hospital_assets.sha256, runbook 0절).
ASSET_CHECK = "sha256sum -c ../scenes/hospital_assets.sha256"
ASSET_OK = "hospital-custom-assets-20260918.zip: OK"
RESET_POSE = re.compile(r"reset pose epoch=\d+ .*?amr_dxy=([\d.]+|-) .*?amr_arm_max_rad=([\d.]+|-) "
                        r"m0609_max_rad=([\d.]+|-)")


class Folder:
    """Reads one or more attempt-folder roots once and merges them. Missing files are None, never an exception."""

    def __init__(self, path):
        given = [Path(p) for p in path] if isinstance(path, (list, tuple)) else [Path(path)]
        self.paths = []
        for root in given:
            self.paths.append(root)
            agg = root / "agg"
            if agg.is_dir():
                self.paths.append(agg)
        self.notes = []
        self.stage, self.stage_root = self._one_root("*-stage.log")
        self.arm = self._one("*-arm.log")
        self.nav = self._one("*-nav.log")
        self.stack = self._one("*-stack.log")
        event_hits = self._event_dirs()
        if len(event_hits) > 1:
            self.notes.append(f"event_run 이 root {len(event_hits)}개에 있다 — {event_hits[0][0]} 것만 썼다")
        run = event_hits[0][1] if event_hits else None
        self.meta = self._json(run / "meta.json") if run else None
        self.events = self._jsonl(run / "events.jsonl") if run else None
        self.orders = self._jsonl(run / "orders.jsonl") if run else None
        self.statuses = self._jsonl(run / "order_status.jsonl") if run else None
        self.cabinet = self._jsonl(run / "cabinet.jsonl") if run else None
        self.boot_check_by_root = [(root, self._text(path)) for root, path in
                                   self._dedup_hits("boot_check.txt")]
        self.up_by_root = [self._text(path) for _, path in self._dedup_hits("up.log")]
        self.up = [line for lines in self.up_by_root if lines for line in lines]
        self.env = self._first_text("demo_v2-env.txt")
        self.steps = self._first_text("STEPS.md")
        self.step_assets = self._first_text("step-assets.log")
        speed_root = next((root for root in self.paths if (root / "speed.csv").is_file()), None)
        others = [root for root in self.paths if root != speed_root and (root / "speed.csv").is_file()]
        if others:
            self.notes.append(f"speed.csv 가 root 여러 개에 있어 {speed_root} 것만 썼다(호스트 시계 대조는 안 한다)")
        self.speed = self._speed(speed_root / "speed.csv") if speed_root else None
        stamp = next((LOG_STAMP.search(p.name) for root in self.paths if (root / "logs").is_dir()
                     for p in (root / "logs").glob("*-stage.log")), None)
        self.log_date = stamp.group(1) if stamp else None

    def _one_root(self, pattern):
        """(lines, root) of the latest matching `logs/` file across all roots, or (None, None)."""
        found = sorted((p, root) for root in self.paths if (root / "logs").is_dir()
                       for p in (root / "logs").glob(pattern))
        if not found:
            return None, None
        path, root = found[-1]
        return path.read_text(encoding="utf-8", errors="replace").splitlines(), root

    def _one(self, pattern):
        return self._one_root(pattern)[0]

    def _first_text(self, name):
        """Lines of the first root (in order) that has `name` (or a FILE_ALIASES raw name); a note if
        more than one root has it."""
        hits = self._dedup_hits(name)
        if len(hits) > 1:
            self.notes.append(f"{name}: root {len(hits)}개에 있어 {hits[0][1]} 것만 썼다")
        return self._text(hits[0][1]) if hits else None

    def _dedup_hits(self, name):
        """[(root, path)] across self.paths for `name` (or a FILE_ALIASES raw alias), one entry per
        distinct *physical* file: a root and its own `agg/` subfolder often both resolve `name` to the
        same file (agg's symlink just points back at the raw one) — that is one host, not two, so
        `path.resolve()` collapses it to a single hit instead of inflating the root-count notes."""
        aliases = (name,) + FILE_ALIASES.get(name, ())
        hits, seen = [], set()
        for root in self.paths:
            path = next((root / alias for alias in aliases if (root / alias).is_file()), None)
            if path is None:
                continue
            real = path.resolve()
            if real in seen:
                continue
            seen.add(real)
            hits.append((root, path))
        return hits

    def _text_alias(self, root, name):
        """`_text(root/name)`, falling back to `root/<raw alias>` per FILE_ALIASES."""
        for alias in (name,) + FILE_ALIASES.get(name, ()):
            found = self._text(root / alias)
            if found is not None:
                return found
        return None

    def _event_dirs(self):
        """(root, event_dir) for each root that has event data, root order preserved, deduped by the
        event dir's real path (see `_dedup_hits`) so a root and its `agg/` subfolder count once when
        `agg/event_run` just symlinks back to the same run. Friendly `event_run/` first; else
        `event_logger/<run_id>/` directly (latest run_id by name sort, since run_ids are
        UTC-timestamp-prefixed) — this does not depend on `agg/` resolving at all, so it survives a
        broken `agg/event_run` symlink (master evidence extracted to the wrong absolute path)."""
        hits, seen = [], set()
        for root in self.paths:
            run = root / "event_run"
            if (run / "meta.json").is_file():
                found = run
            else:
                logger_dir = root / "event_logger"
                candidates = sorted((p for p in logger_dir.glob("*") if (p / "meta.json").is_file()),
                                     key=lambda p: p.name) if logger_dir.is_dir() else []
                found = candidates[-1] if candidates else None
            if found is None:
                continue
            real = found.resolve()
            if real in seen:
                continue
            seen.add(real)
            hits.append((root, found))
        return hits

    @staticmethod
    def _text(path):
        return path.read_text(encoding="utf-8", errors="replace").splitlines() if path.is_file() else None

    @staticmethod
    def _json(path):
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    @staticmethod
    def _jsonl(path):
        if not path.is_file():
            return None
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    @staticmethod
    def _speed(path):
        if not path.is_file():
            return None
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines()[1:]:
            parts = line.split(",")
            try:
                rows.append((float(parts[1]), float(parts[0])))  # (sim, wall)
            except (IndexError, ValueError):
                continue
        return sorted(rows) or None


def _grep(lines, needle):
    return [line for line in lines or [] if needle in line]


def _flag(ok):
    return 1 if ok else 0


class Attempt:
    def __init__(self, folder, attempt):
        self.f = folder
        self.attempt = attempt
        self.notes = list(folder.notes)
        epoch = (folder.meta or {}).get("epoch")
        events = folder.events or []
        self.live = sorted((e for e in events if not e.get("stale") and (epoch is None or e.get("epoch") == epoch)),
                           key=lambda e: e["stamp"])
        self.order_ids = sorted({row["order_id"] for row in folder.orders or [] if row.get("order_id")}
                                | {e["order_id"] for e in self.live if e.get("name") == "REQUEST_ACCEPTED"
                                   and e.get("order_id")})

    def note(self, text):
        self.notes.append(text)

    def named(self, name, order_id=None):
        return [e for e in self.live if e["name"] == name and (order_id is None or e.get("order_id") == order_id)]

    # ---- sim ↔ wall -------------------------------------------------------------------------------------

    def wall_at(self, sim):
        """speed.csv (sim, wall) pairs, linear between neighbours; outside the table the nearest end."""
        rows = self.f.speed
        if not rows:
            return None
        if sim <= rows[0][0]:
            return rows[0][1] + (sim - rows[0][0])
        if sim >= rows[-1][0]:
            return rows[-1][1] + (sim - rows[-1][0])
        lo, hi = 0, len(rows) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            lo, hi = (mid, hi) if rows[mid][0] <= sim else (lo, mid)
        (s0, w0), (s1, w1) = rows[lo], rows[hi]
        return w0 if s1 == s0 else w0 + (sim - s0) * (w1 - w0) / (s1 - s0)

    def up_start_wall(self):
        """Earliest up.log clock (local) turned into epoch s, over every root that has one.

        Each root's offset comes from ITS OWN up.log line that carries both the demo_v2 clock and a ROS
        [INFO] [epoch] stamp — phase E (다중 PC) usually has that pairing only on the arm/nav/stack host, so a
        stage-only root without one is simply skipped, not treated as a zero. `up 시작` for a merged attempt is the
        earliest of whichever roots could be resolved (the host that started `up` first).
        """
        if self.f.log_date is None:
            return None
        midnight = calendar.timegm(time.strptime(self.f.log_date, "%Y%m%d"))
        starts = []
        for lines in self.f.up_by_root:
            lines = lines or []
            first = next((UP_CLOCK.match(line) for line in lines if UP_CLOCK.match(line)), None)
            pair = next(((UP_CLOCK.match(line), ROS_STAMP.search(line)) for line in lines
                        if UP_CLOCK.match(line) and ROS_STAMP.search(line)), None)
            if first is None or pair is None:
                continue
            clock, ros = pair
            local = int(clock.group(1)) * 3600 + int(clock.group(2)) * 60 + int(clock.group(3))
            utc = float(ros.group(1)) % 86400
            offset = round(((local - utc + 43200) % 86400 - 43200) / 900) * 900
            start = int(first.group(1)) * 3600 + int(first.group(2)) * 60 + int(first.group(3))
            starts.append(midnight + start - offset)
        return min(starts) if starts else None

    # ---- purpose 4 (a) scenes ---------------------------------------------------------------------------

    def scene_workcell_ready(self):
        if self.f.stage is None:
            return None
        # `present=…/18`: 18 칸 진열에서 seed 가 비운 칸(empty=[…])을 뺀 수가 present 다(seed 7 은 14, 회차82–95).
        stock = [re.search(r"cells=(\d+) present=(\d+) empty=\[([^\]]*)\]", line)
                 for line in _grep(self.f.stage, "workcell_stock ")]
        settle = [re.search(r"max_move_m=([\d.]+)", line) for line in _grep(self.f.stage, "canister_settle n=")]
        cache = _grep((self.f.arm or []) + (self.f.up or []), "v2 계획 캐시 종류별")
        ready = cache and all(kind in cache[-1].split("완료 종류:")[-1] for kind in REQUIRED_KINDS)
        return _flag(any(m and int(m.group(1)) == STOCK_CELLS
                         and int(m.group(2)) + len([c for c in m.group(3).split(",") if c.strip()]) == STOCK_CELLS
                         for m in stock)
                     and settle and all(m and float(m.group(1)) < SETTLE_LIMIT_M for m in settle) and ready)

    def refill_done_count(self):
        # REFILL_DONE from start-up is stale (epoch 0) but is one of the two refills the scene counts.
        return sum(1 for e in self.f.events or [] if e.get("name") == "REFILL_DONE")

    def scene_refill_both(self):
        if self.f.stage is None or self.f.events is None:
            return None
        released = _grep(self.f.stage, "refill_ros released ")
        targets = {t for line in released for t in re.findall(r"target=(\w+)", line)}
        arm_touch = [m for m in map(CONTACT_TOUCH.search, self.f.stage) if m
                     and any("/m0609/" in side for side in m.groups())
                     and any(side.startswith("/World/P3Base/") for side in m.groups())]
        if arm_touch:
            self.note(f"scene_refill_both: M0609 가 병원 prim(/World/P3Base/)에 닿은 touch {len(arm_touch)}줄")
        return _flag({"round", "module"} <= targets and self.refill_done_count() >= 2 and not arm_touch)

    def scene_container_qr(self):
        if self.f.arm is None:
            return None
        allowed = len([line for line in _grep(self.f.arm, "약통 확인: ") if "장착 허용" in line])
        refused = len(_grep(self.f.arm, "잡지 않고 끝낸다"))
        refills = self.refill_done_count()
        if allowed != refills:
            self.note(f"scene_container_qr: 장착 허용 {allowed}줄, REFILL_DONE {refills}건")
        return _flag(allowed >= max(refills, 1) and refused == 0)

    def _at_end(self):
        return [(bool(re.search(r"in_sensor_zone=True\b", line)),
                 float(m.group(1)) if (m := re.search(r"sim_s_since_dispense=([\d.]+)", line)) else math.inf)
                for line in _grep(self.f.stage, "hospital pouch_at_end ")]

    def pouch_to_end_s(self):
        if self.f.stage is None:
            return None
        spans = [span for _, span in self._at_end() if math.isfinite(span)]
        return round(max(spans), 3) if spans else None

    def scene_pouch_at_end(self):
        if self.f.stage is None:
            return None
        ends = self._at_end()
        left = _grep(self.f.stage, "belt note=pouch_left_belt")
        enough = len(ends) >= max(len(self.order_ids), 1)
        return _flag(enough and all(zone and span <= POUCH_END_LIMIT_S for zone, span in ends) and not left)

    def scene_pick_in_slot(self):
        if self.f.stage is None or self.f.events is None or not self.order_ids:
            return None
        placed = _grep(self.f.stage, "pouch placed ")
        loose = [line for line in placed if "in_slot=False" in line]
        if loose:
            self.note(f"scene_pick_in_slot: in_slot=False {len(loose)}줄(기록만)")
        return _flag(all(self.named("POUCH_PICKED", o) and self.named("POUCH_LOADED", o)
                         and any(f"order_id={o} in_slot=True" in line for line in placed) for o in self.order_ids))

    def scene_delivered_docked(self):
        if self.f.events is None or self.f.orders is None or not self.order_ids:
            return None
        claims = {row["order_id"]: row for row in self.f.orders}
        # ARRIVED·DOCKED 는 order_id 가 비어 있고 request_id 만 있다(마클1 attempt 1, #709 5824258923).
        requests = {o: claims.get(o, {}).get("request_id") for o in self.order_ids}

        def arrived(o):
            return any(e.get("order_id") == o or (requests[o] and e.get("request_id") == requests[o])
                       for e in self.named("ARRIVED"))

        present = {row.get("order_id") for row in self.f.cabinet or [] if row.get("present") and row.get("order_id")}
        if self.f.cabinet is None:
            self.note("scene_delivered_docked: event_run/cabinet.jsonl 이 없다")
        done = [e for o in self.order_ids for e in self.named("ORDER_DONE", o)]
        last_done = max((e["stamp"] for e in done), default=None)
        docked = [e for e in self.named("DOCKED") if last_done is not None and e["stamp"] >= last_done]
        return _flag(all(arrived(o) and o in present and self.named("ORDER_DONE", o)
                         and claims.get(o, {}).get("claim") == "DELIVERED" for o in self.order_ids) and docked)

    def amr_touch_count(self):
        if self.f.stage is None:
            return None
        return sum(1 for m in map(CONTACT_TOUCH.search, self.f.stage) if m
                   and any("/Amr/" in side for side in m.groups())
                   and not any("/Pouches/" in side for side in m.groups()))

    # ---- (b) governor --------------------------------------------------------------------------------------

    def governor_lines(self):
        """[(wall, percent, margin text)] from the first line whose received-costmap count is ≥ 1."""
        if self.f.nav is None:
            return None
        rows, started = [], False
        for line in self.f.nav:
            m = SPEED_LIMIT.search(line)
            if not m:
                continue
            started = started or int(m.group(3)) >= 1
            if started:
                stamp = ROS_STAMP.search(line)
                rows.append((float(stamp.group(1)) if stamp else None, int(m.group(1)), m.group(2)))
        return rows

    def governor_margin_lines(self):
        rows = self.governor_lines()
        return None if rows is None else sum(1 for _, _, text in rows if re.match(r"[0-9]|≥", text))

    def governor_full_speed_lines(self):
        rows = self.governor_lines()
        return None if rows is None else sum(1 for _, percent, _ in rows if percent == 100)

    def governor_unknown_lines(self):
        rows = self.governor_lines()
        return None if rows is None else sum(1 for _, _, text in rows if text.startswith("모름"))

    # ---- (c) boot_check, (d) orders tool, (e) recording -----------------------------------------------------

    def boot_check_pass(self):
        """root 마다 본다(모듈 docstring). `window` 는 어디서나 뺄 수 있다. `viewport` 는 stage 를 맡지 않은
        root 면 뺄 수 있지만, stage root 자신은 못 빼고, 준 root 전체에서 `viewport PASS` 가 한 번도 없으면
        (다중 PC 라도) 게이트 실패다 — 아무도 확인하지 않은 것이다."""
        per_root = [(root, lines) for root, lines in self.f.boot_check_by_root if lines is not None]
        if not per_root:
            return None
        multi = len(per_root) > 1
        any_viewport_pass = any(re.match(r"\[boot_check\] viewport PASS", line) for _, lines in per_root
                                for line in lines)
        if not any_viewport_pass:
            self.note("boot_check: 어느 root 도 viewport 를 통과하지 못했다(모두 SKIP·FAIL) — 확인된 적이 없다")
        ok = any_viewport_pass
        for root, lines in per_root:
            skipped = [line.split()[1] for line in lines if re.match(r"\[boot_check\] \w+ SKIP", line)]
            if "window" in skipped:
                self.note("boot_check: window SKIP — 전체 창 촬영 구성이거나 다중 PC(phase E, Isaac·웹이 다른 "
                          "host)면 run 기록에 적는다(purpose 4 c)")
            allowed = {"window"}
            if "viewport" in skipped and root != self.f.stage_root:
                allowed.add("viewport")
                if multi:
                    self.note(f"boot_check: {root} 는 viewport SKIP — stage 를 맡지 않은 host 다(phase E)")
            finished_ok = any(line.strip() == "[boot_check] OK" for line in lines)
            failed = any("[boot_check] FAIL" in line for line in lines)
            if not finished_ok or failed or [name for name in skipped if name not in allowed]:
                ok = False
        return _flag(ok)

    def orders_delivered(self):
        for root in self.f.paths:
            for path in sorted(root.rglob("summary.md")):
                m = re.search(r"\*\*(PASS|FAIL)\*\* \((\d+)/(\d+) delivered\)", path.read_text(encoding="utf-8"))
                if m:
                    return int(m.group(2))
        self.note("hospital_orders summary.md 가 어느 root 에도 없다")
        return None

    def record_lines(self):
        """record_qa 줄, root 마다(각 host 가 자기 화면을 녹화한다) — 여러 root 면 그 줄을 다 합친다."""
        files = []
        for root in self.f.paths:
            files += sorted(root.glob("record_qa*.txt")) or [root / "SUMMARY.txt"]
        lines = [line for path in files if path.is_file()
                 for line in path.read_text(encoding="utf-8").splitlines() if "record_qa:" in line]
        return lines or None

    def record_values(self):
        lines = self.record_lines()
        if lines is None:
            return None
        parsed = [RECORD_QA.search(line) for line in lines]
        if not all(parsed) or any("— OK" not in line for line in lines):
            self.note(f"record_qa: OK 가 아닌 줄 {sum(1 for line in lines if '— OK' not in line)}개")
        return [(float(m.group(1)), float(m.group(2)), int(m.group(3)), int(m.group(4))) for m in parsed if m], \
            all(parsed) and all("— OK" in line for line in lines)

    def record_fps_min(self):
        values = self.record_values()
        return None if not values or not values[0] else min(fps for fps, _, _, _ in values[0])

    def record_drop_ratio_max(self):
        values = self.record_values()
        return None if not values or not values[0] else round(
            max(drop / (dur * TARGET_FPS) if dur > 0 else 1.0 for _, dur, drop, _ in values[0]), 6)

    def record_corrupt_sum(self):
        values = self.record_values()
        return None if not values or not values[0] else sum(corrupt for _, _, _, corrupt in values[0])

    # ---- recorded only ---------------------------------------------------------------------------------------

    def unplanned_intervention_count(self):
        files = [root / name for root in self.f.paths for name in ("phase.log", "up.log", "film.log")]
        present = [path for path in files if path.is_file()]
        if not present:
            return None
        return sum(path.read_text(encoding="utf-8", errors="replace").count("수동 개입") for path in present)

    def avoidance_on(self):
        line = next((line for line in self.f.stage or [] if "resolved_args=" in line), None)
        if line is None:
            return None
        try:
            args = json.loads(line.split("resolved_args=", 1)[1])
        except ValueError:
            return None
        return bool(args.get("pedestrians") or args.get("traffic_dummies"))

    def encounters(self):
        """[(start sim, end sim or None)] per `who`, or None when the stage log is missing or avoidance is off."""
        if self.f.stage is None:
            return None
        if self.avoidance_on() is False:
            self.note("회피 요소 OFF(resolved_args pedestrians·traffic_dummies 0) — avoidance_* 는 record_missing")
            return None
        if _grep(self.f.stage, "WARN encounters disabled"):
            self.note("WARN encounters disabled — avoidance_* 는 record_missing")
            return None
        spans, open_ = [], {}
        for m in filter(None, map(ENCOUNTER.search, self.f.stage)):
            kind, who, sim = m.group(1), m.group(2), float(m.group(3))
            if kind == "start":
                open_[who] = sim
            elif who in open_:
                spans.append((open_.pop(who), sim))
        spans += [(start, None) for start in open_.values()]
        return spans

    def avoidance_encounters(self):
        spans = self.encounters()
        return None if spans is None else len(spans)

    def governor_limit_lines_during_encounters(self):
        spans = self.encounters()
        rows = self.governor_lines()
        if spans is None or rows is None:
            return None
        if self.f.speed is None:
            self.note("speed.csv 가 없어 조우 구간을 벽시계로 옮기지 못했다")
            return None
        end_wall = self.f.speed[-1][1]
        walls = [(self.wall_at(start), end_wall if end is None else self.wall_at(end)) for start, end in spans]
        return sum(1 for wall, percent, _ in rows if wall is not None and percent < 100
                   and any(lo <= wall <= hi for lo, hi in walls))

    def deck_vision(self):
        line = next((line for line in self.f.env or [] if line.startswith("P3_DECK_VISION ")), None)
        return None if line is None else line.split()[1] == "1"

    def vision_lines(self):
        if self.deck_vision() is False:
            self.note("P3_DECK_VISION=0 — vision_* 는 record_missing")
            return None
        lines = [m for m in map(VISION.search, self.f.stack or []) if m]
        return lines or None

    def vision_detect_rate(self):
        lines = self.vision_lines()
        return None if lines is None else round(sum(1 for m in lines if m.group(2) == "ok") / len(lines), 6)

    def vision_latency_ms(self):
        lines = self.vision_lines()
        return None if lines is None else float(statistics.median(int(m.group(3)) for m in lines))

    def clone_steps(self):
        """STEPS.md 의 `### <단계> HH:MM:SS` … `끝 HH:MM:SS exit=N` 짝 [(단계, 초, exit, 명령)], `기동` 앞까지.

        마클1 attempt 16(#240 5825043496): clone·build·venv·assets·prep 다섯이고 다음 단계가 끝난 시각에 바로 선다.
        """
        if self.f.steps is None:
            return None
        steps, current, command = [], None, []
        for line in self.f.steps:
            head = STEP_HEAD.match(line)
            if head:
                if head.group(1) == "기동":
                    break
                current, command = (head.group(1), _clock(head.group(2, 3, 4))), []
                continue
            end = STEP_END.match(line)
            if end and current:
                seconds = (_clock(end.group(1, 2, 3)) - current[1]) % 86400   # 자정을 넘으면 +24 h
                steps.append((current[0], seconds, int(end.group(4)), " ".join(command)))
                current = None
            elif current:
                command.append(line)
        return steps

    def fresh_clone_step_wall_s(self):
        """clone 부터 ORDER_DONE 까지 단계별 wall s 합: STEPS.md 의 up 전 단계 + up 시작 → 마지막 ORDER_DONE."""
        steps = self.clone_steps()
        if not steps:
            self.note("fresh_clone_step_wall_s: STEPS.md 에 `### 단계 시각` … `끝 시각 exit=` 짝이 없다")
            return None
        failed = [name for name, _, code, _ in steps if code != 0]
        if failed:
            self.note(f"fresh_clone: exit 가 0 이 아닌 단계 {failed}")
        start = self.up_start_wall()
        done = self.named("ORDER_DONE")
        if start is None or not done or self.f.speed is None:
            self.note("fresh_clone_step_wall_s: up 시작이나 ORDER_DONE 의 벽시계를 못 구했다(up.log·speed.csv·events)")
            return None
        self.note("fresh_clone 단계 s: " + ", ".join(f"{name} {seconds}" for name, seconds, _, _ in steps))
        return round(sum(seconds for _, seconds, _, _ in steps) + self.wall_at(done[-1]["stamp"]) - start, 3)

    def fresh_clone_asset_sha_ok(self):
        """assets 단계가 `sha256sum -c ../scenes/hospital_assets.sha256` 을 돌려 exit 0 이고, 그 로그가 있으면
        `…zip: OK` 줄이 있다. 대조 명령이 없으면 null(잰 적 없음), 있는데 실패면 0."""
        assets = next((step for step in self.clone_steps() or [] if ASSET_CHECK in step[3]), None)
        if assets is None:
            self.note("fresh_clone_asset_sha_ok: STEPS.md 에 hospital_assets.sha256 대조 단계가 없다")
            return None
        logged = self.f.step_assets is None or any(ASSET_OK in line for line in self.f.step_assets)
        return _flag(assets[2] == 0 and logged)

    def rtf(self):
        stop = next((m for m in (re.search(r"stop reason=\S+ .*?rtf=([\d.]+)", line) for line in self.f.stage or [])
                     if m), None)
        return None if stop is None else float(stop.group(1))

    def attempt_wall_s(self):
        start = self.up_start_wall()
        docked = self.named("DOCKED")
        if start is None or not docked or self.f.speed is None:
            if start is None:
                self.note("attempt_wall_s: up.log 첫 시각을 epoch 로 못 바꿨다(ROS 시각이 든 up.log 줄이 필요)")
            return None
        return round(self.wall_at(docked[-1]["stamp"]) - start, 3)

    def reset_values(self):
        values = [m for m in map(RESET_POSE.search, self.f.stage or []) if m]
        return values or None

    def reset_dock_pose_error_m(self):
        values = [float(m.group(1)) for m in self.reset_values() or [] if m.group(1) != "-"]
        return max(values) if values else None

    def reset_arm_park_error_rad(self):
        values = [float(v) for m in self.reset_values() or [] for v in m.group(2, 3) if v != "-"]
        return max(values) if values else None

    def pouch_spawn_records(self):
        return None if self.f.stage is None else len(_grep(self.f.stage, "spawn index="))

    # ---- (a)-(e) ---------------------------------------------------------------------------------------------

    def attempt_success(self, values):
        scenes = ("scene_workcell_ready", "scene_refill_both", "scene_pouch_at_end", "scene_pick_in_slot",
                  "scene_delivered_docked")
        checks = {
            "a": all(values.get(name) == 1 for name in scenes) and values.get("amr_touch_count") == 0,
            "b": (values.get("governor_margin_lines") or 0) >= 1
            and (values.get("governor_full_speed_lines") or 0) >= 1,
            "c": values.get("boot_check_pass") == 1,
            "e": bool(self.record_values() and self.record_values()[1]),
        }
        if self.attempt in (6, 11):
            name = "orders10_delivered" if self.attempt == 6 else "orders_beds_all_delivered"
            checks["d"] = values.get(name) == ORDERS10
        failed = [key for key, ok in checks.items() if not ok]
        if failed:
            self.note(f"attempt_success 0: purpose 4 ({', '.join(failed)}) 가 PASS 가 아니다")
        return _flag(not failed)


def _clock(parts):
    hours, minutes, seconds = map(int, parts)
    return hours * 3600 + minutes * 60 + seconds


def compute(run_dir, definitions, attempt=None):
    """{metric name: value or None} for the protocol metric list, plus notes."""
    folder = Folder(run_dir)
    state = Attempt(folder, attempt)
    if attempt is None:
        state.note("--attempt 가 없어 phase 한정 metric(orders·reset·fresh_clone)은 null 이다")
    elif attempt not in PHASES:
        state.note(f"attempt {attempt} 는 protocol 의 1-16 이 아니다")
    values = {}
    for definition in definitions:
        name = definition["name"]
        if name == "attempt_success":
            continue
        allowed = PHASE_METRICS.get(name)
        if allowed is not None and attempt not in allowed:
            values[name] = None
            continue
        if name in ("orders10_delivered", "orders_beds_all_delivered", "orders10_multipc_delivered"):
            values[name] = state.orders_delivered()
            continue
        values[name] = getattr(state, name)()
    if any(d["name"] == "attempt_success" for d in definitions):
        values["attempt_success"] = state.attempt_success(values)
    for name, value in values.items():
        if value is None and name not in PHASE_METRICS:
            state.note(f"{name}: null(원본 줄·파일 없음) — record_missing")
    return values, list(dict.fromkeys(state.notes)), {
        "attempt": attempt, "phase": PHASES.get(attempt), "orders": state.order_ids,
        "epoch": (folder.meta or {}).get("epoch"), "run_id": (folder.meta or {}).get("run_id")}
