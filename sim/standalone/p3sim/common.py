"""Logging, loop and exit helpers shared by the standalone scripts. No Isaac imports."""

import argparse
import collections
import contextlib
import hashlib
import math


class Logger:
    """One-line logs with a fixed prefix, flushed so they interleave correctly with Kit's own log."""

    def __init__(self, prefix):
        self.prefix = prefix

    def __call__(self, text):
        print(f"{self.prefix} {text}", flush=True)


class StepError(RuntimeError):
    """A named setup step failed; the message already says which step and why."""


@contextlib.contextmanager
def step(log, name):
    """Log `step=<name> ok` or one line `step=<name> FAILED <type>: <cause>` and re-raise as StepError.

    For first runs on the master where the observer cannot change code: the failing step must be readable from one
    line without a traceback."""
    try:
        yield
    except StepError:
        raise
    except Exception as exc:
        log(f"step={name} FAILED {type(exc).__name__}: {exc}")
        raise StepError(f"{name}: {type(exc).__name__}: {exc}") from exc
    log(f"step={name} ok")


class TickTrace:
    """Names of the Isaac calls made in the last few loop ticks, dumped when something unexplained happens.

    9/17 master02: a timeline STOP came from inside Kit with no log line before it; the calls we made right before are
    the first suspects. Cheap: one short string per call, a few ticks kept."""

    def __init__(self, ticks=3, per_tick=40):
        self.ticks = collections.deque(maxlen=ticks)
        self.per_tick = per_tick
        self.current = []
        self.label = "start"
        self.index = 0

    def mark(self, name):
        if len(self.current) < self.per_tick:
            self.current.append(name)
        elif len(self.current) == self.per_tick:
            self.current.append("...")

    def next_tick(self, label):
        self.ticks.append((self.index, self.label, self.current))
        self.index += 1
        self.label = label
        self.current = []

    def dump(self):
        parts = [f"tick{index}[{label}]: {', '.join(calls) or '-'}" for index, label, calls in self.ticks]
        parts.append(f"tick{self.index}[{self.label}] (in progress): {', '.join(self.current) or '-'}")
        return " || ".join(parts)


class ThrottledLog:
    """Log the first occurrence and then every `every`-th, so a per-update condition cannot flood the log."""

    def __init__(self, every=60):
        self.every = every
        self.count = 0

    def hit(self):
        self.count += 1
        return self.count == 1 or self.count % self.every == 0


def exit_code_for(error_seen):
    """Process exit code. SimulationApp.close() ended the process with 0 even after an error on master02 (9/17),
    so error paths exit with this code before close()."""
    return 1 if error_seen else 0


def keep_running(app_running, app_exiting, headless):
    """Loop condition. Headless (and livestream) keep going while the app is not exiting, as the class example
    7_pick_place_color.py and NVIDIA 5.1.0 livestream.py do, because is_running() can be False early when headless."""
    if app_running:
        return True
    return headless and not app_exiting


def next_publish_time(scheduled, now, rate_hz):
    """Advance a wall-clock publish schedule by one period without drift; restart from now if far behind.

    `now + period` pushed each deadline past the next 60 Hz update (22.9 Hz for a 30 Hz target, master02 9/17)."""
    period = 1.0 / rate_hz
    following = scheduled + period
    return now if following < now - period else following


def format_values(values, digits=4):
    return "[" + ", ".join(f"{float(value):.{digits}f}" for value in values) + "]"


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def positive_float(text):
    value = float(text)
    if not value > 0.0:
        raise argparse.ArgumentTypeError(f"must be > 0, got {text}")
    return value


def positive_int(text):
    value = int(text)
    if not value > 0:
        raise argparse.ArgumentTypeError(f"must be > 0, got {text}")
    return value


def non_negative_float(text):
    value = float(text)
    if not value >= 0.0:
        raise argparse.ArgumentTypeError(f"must be >= 0, got {text}")
    return value


def xy(text):
    """Two numbers in one string, 'x y' or 'x,y'. Same shape as xyz, for arguments that take a footprint."""
    parts = text.replace(",", " ").split()
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"need two numbers 'x y' in ONE quoted argument, got {text!r}")
    try:
        values = tuple(float(part) for part in parts)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"not numbers: {text!r}") from error
    if not all(math.isfinite(value) and value > 0.0 for value in values):
        raise argparse.ArgumentTypeError(f"not finite positive numbers: {text!r}")
    return values


def xyz(text):
    parts = text.replace(",", " ").split()
    if len(parts) != 3:
        raise argparse.ArgumentTypeError(f"need three numbers 'x y z' in ONE quoted argument, got {text!r}")
    try:
        values = tuple(float(part) for part in parts)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"not numbers: {text!r}") from error
    if not all(math.isfinite(value) for value in values):
        raise argparse.ArgumentTypeError(f"not finite: {text!r}")
    return values


def positive_xyz(text):
    values = xyz(text)
    if not all(value > 0.0 for value in values):
        raise argparse.ArgumentTypeError(f"sizes must be > 0: {text!r}")
    return values


def pair(text):
    """'low high' with low <= high, e.g. a random range."""
    parts = text.replace(",", " ").split()
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"need two numbers 'low high', got {text!r}")
    try:
        low, high = (float(part) for part in parts)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"not numbers: {text!r}") from error
    if not (math.isfinite(low) and math.isfinite(high)) or low > high:
        raise argparse.ArgumentTypeError(f"need finite low <= high: {text!r}")
    return low, high


def quat(text):
    parts = text.replace(",", " ").split()
    if len(parts) != 4:
        raise argparse.ArgumentTypeError(f"need four numbers 'w x y z', got {text!r}")
    values = tuple(float(part) for part in parts)
    norm = math.sqrt(sum(value * value for value in values))
    if not math.isfinite(norm) or norm < 1e-9:
        raise argparse.ArgumentTypeError(f"not a quaternion: {text!r}")
    return tuple(value / norm for value in values)
