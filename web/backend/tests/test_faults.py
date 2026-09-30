"""고장 흉내 — 각 fault 가 **실서버 snapshot 에 그 알람을 띄우는지** 본다.

알람 규칙 자체는 `test_alarms.py` 가 본다. 여기서 보는 것은 **배선**이다:
mock 재생 데이터를 비틀었을 때 실물과 같은 코드 경로를 타고 알람까지 도달하는가.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.faults import FaultSpecError, Faults, parse_faults
from app.main import build_parser, create_app, main


def run_until(client, wanted: str, timeout_s: float = 25.0) -> tuple[dict, dict]:
    """알람 `wanted` 가 뜰 때까지 재생을 지켜본다. **(알람, 그 알람이 있던 snapshot)**.

    snapshot 을 같이 돌려주는 이유: 알람을 찾은 뒤 snapshot 을 **다시** 받아서 검사하면,
    `--loop` 재생이 그 사이에 한 바퀴를 새로 시작해 조건이 풀릴 수 있다. 그러면 테스트가
    부하에 따라 깜빡인다 — 깜빡이는 빨간불은 사람이 빨간불을 무시하게 만든다.
    **한 관측 안에서 검사한다.**
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        snap = client.get("/api/snapshot").json()
        for alarm in snap["alarms"]:
            if alarm["kind"] == wanted:
                return alarm, snap
        time.sleep(0.1)
    raise AssertionError(f"{wanted} 가 끝내 안 떴다")


def fault_client(names, **kw):
    app = create_app(mock=True, speed=40.0, loop=True, allow_commands=True,
                     faults=Faults(names), **kw)
    return TestClient(app)


# ── 파싱 ─────────────────────────────────────────────────────────────────

def test_no_spec_means_no_faults():
    assert not parse_faults(None)
    assert not parse_faults("")
    assert parse_faults(None).active == []


def test_several_faults_can_be_given_at_once():
    faults = parse_faults("clock_stop,stale:belt")
    assert faults.clock_stop is True
    assert faults.stale_keys == {"belt"}


def test_whitespace_around_names_is_forgiven():
    assert parse_faults(" clock_stop , refill_fail ").active == ["clock_stop", "refill_fail"]


def test_an_unknown_fault_name_is_an_error_not_a_silent_skip():
    """오타를 조용히 무시하면 '왜 알람이 안 뜨지' 로 시간을 버린다."""
    with pytest.raises(FaultSpecError, match="모르는 고장 이름"):
        parse_faults("clock_stopp")


def test_an_unknown_signal_key_is_an_error():
    with pytest.raises(FaultSpecError, match="모르는 신호 키"):
        parse_faults("stale:없는신호")


def test_the_old_flag_is_gone():
    """--mock-stuck-reset 은 --mock-fault stuck_reset 으로 합쳐졌다. 별칭을 남기지 않는다."""
    assert "--mock-stuck-reset" not in build_parser().format_help()
    assert "--mock-fault" in build_parser().format_help()


# ── 안전장치 ─────────────────────────────────────────────────────────────

def test_faults_without_mock_refuse_to_start(capsys):
    """실물에 고장을 주입할 길을 아예 두지 않는다."""
    assert main(["--mock-fault", "clock_stop"]) == 2
    assert "--mock 과 함께만" in capsys.readouterr().out


def test_a_bad_fault_name_refuses_to_start(capsys):
    assert main(["--mock", "--mock-fault", "없는고장"]) == 2
    assert "모르는 고장 이름" in capsys.readouterr().out


def test_snapshot_advertises_active_faults_so_the_screen_can_warn():
    """시연 때 실수로 켠 채 띄우는 사고를 막는 배지의 근거."""
    with fault_client(["clock_stop"]) as client:
        assert client.get("/api/snapshot").json()["mock_faults"] == ["clock_stop"]


def test_a_clean_server_reports_no_faults():
    app = create_app(mock=True, autostart=False)
    with TestClient(app) as client:
        assert client.get("/api/snapshot").json()["mock_faults"] == []


# ── fault 마다 알람이 실제로 뜨는가 ──────────────────────────────────────

def test_clock_stop_raises_clock_stopped():
    with fault_client(["clock_stop"]) as client:
        alarm, snap = run_until(client, "CLOCK_STOPPED")
        assert alarm["level"] == "error"
        assert snap["clock"]["alive"] is False


def test_stale_raises_status_stale_for_that_signal():
    with fault_client(["stale:m0609_at_home"]) as client:
        alarm, snap = run_until(client, "STATUS_STALE")
        assert alarm["level"] == "warn"
        assert "m0609_at_home" in alarm["message"]
        assert snap["signals"]["m0609_at_home"]["stale"] is True


def test_refill_fail_raises_refill_failed():
    with fault_client(["refill_fail"], refill_timeout=5.0) as client:
        alarm, _snap = run_until(client, "REFILL_FAILED")
        assert alarm["level"] == "error"


def test_order_timeout_raises_timeout_with_a_reason():
    with fault_client(["order_timeout"]) as client:
        alarm, _snap = run_until(client, "TIMEOUT")
        assert alarm["level"] == "error"
        assert "delivery_timeout" in alarm["message"], "사유가 실려야 한다"


def test_stuck_reset_raises_reset_stuck():
    app = create_app(mock=True, autostart=False, allow_commands=True,
                     faults=Faults(["stuck_reset"]), reset_timeout=0.5)
    with TestClient(app) as client:
        assert client.post("/api/reset", json={}).status_code == 202
        alarm, snap = run_until(client, "RESET_STUCK", timeout_s=6.0)
        assert alarm["level"] == "error"
        assert snap["reset_in_progress"] is True
        assert snap["accepting_requests"] is False


# ── 고장을 안 켜면 아무것도 안 뜬다 ──────────────────────────────────────

def test_a_healthy_replay_raises_none_of_the_fault_alarms():
    """평소에 이 알람들이 보이면 진짜 문제라는 뜻이 되어야 한다."""
    fault_alarms = {"CLOCK_STOPPED", "STATUS_STALE", "REFILL_FAILED", "RESET_STUCK"}
    app = create_app(mock=True, speed=40.0, loop=True)
    seen: set[str] = set()
    with TestClient(app) as client:
        deadline = time.time() + 8.0
        while time.time() < deadline:
            seen |= {a["kind"] for a in client.get("/api/snapshot").json()["alarms"]}
            time.sleep(0.1)
    assert not (seen & fault_alarms), f"고장을 안 켰는데 떴다: {seen & fault_alarms}"


# ── 재생 배속이 신선도를 흔들면 안 된다 ─────────────────────────────────

def test_a_slow_replay_does_not_invent_stale_signals():
    """하트비트를 sim 기준으로 내면 --speed 0.05 같은 느린 재생에서 가짜 stale 이 뜬다.

    실물 하트비트는 wall 주기(H 5 Hz)로 오므로, mock 도 배속과 무관하게 내야 한다.
    """
    import asyncio
    from datetime import datetime, timezone

    from app.mock import MockPlayer, load_fixture
    from app.state import WorldState

    async def run():
        state = WorldState()
        player = MockPlayer(state, load_fixture(), speed=0.05)
        player.start()
        worst = set()
        for _ in range(25):
            await asyncio.sleep(0.1)
            snap = state.snapshot(datetime.now(timezone.utc))
            worst |= {a["kind"] for a in snap["alarms"]}
        await player.stop()
        return worst

    seen = asyncio.run(run())
    assert "STATUS_STALE" not in seen, "느린 재생이 가짜 stale 을 만들었다"
    assert "CLOCK_STOPPED" not in seen, "느린 재생이 /clock 을 멈춘 것으로 보이게 했다"


def test_a_fast_replay_is_also_clean():
    import asyncio
    from datetime import datetime, timezone

    from app.mock import MockPlayer, load_fixture
    from app.state import WorldState

    async def run():
        state = WorldState()
        player = MockPlayer(state, load_fixture(), speed=60.0, loop=True)
        player.start()
        seen = set()
        for _ in range(25):
            await asyncio.sleep(0.1)
            seen |= {a["kind"] for a in state.snapshot(datetime.now(timezone.utc))["alarms"]}
        await player.stop()
        return seen

    seen = asyncio.run(run())
    assert not (seen & {"STATUS_STALE", "CLOCK_STOPPED"})
