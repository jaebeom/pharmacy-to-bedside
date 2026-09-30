"""진짜 uvicorn 을 띄워서 시험한다.

**왜 따로 있나:** TestClient 는 자체 WebSocket 구현을 써서, uvicorn 에 ws 라이브러리가
없어도 WS 테스트가 통과한다. 실제로 프론트는 `/ws` 404 로 막혔는데 테스트는 전부 초록이었다.
그 구멍을 막는 것이 이 파일의 유일한 목적이다 — 여기서는 프로세스를 띄워 밖에서 두드린다.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

# requirements.txt 에 들어 있으므로 없으면 **건너뛰지 말고 실패해야 한다.**
# importorskip 을 쓰면 라이브러리가 빠졌을 때 조용히 skip 되어, 막으려던 버그를 또 놓친다.
import websockets.sync.client as ws_client

ROOT = Path(__file__).resolve().parents[1]
BOOT_TIMEOUT_S = 30.0


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_server():
    port = free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.main", "--mock", "--speed", "30",
         "--allow-commands", "--port", str(port)],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + BOOT_TIMEOUT_S
    while time.time() < deadline:
        if proc.poll() is not None:
            pytest.fail(f"서버가 떠보지도 못하고 죽었다:\n{proc.stdout.read()}")
        try:
            urllib.request.urlopen(base + "/api/snapshot", timeout=2).read()
            break
        except Exception:
            time.sleep(0.2)
    else:
        proc.kill()
        pytest.fail("서버가 시간 안에 안 떴다")
    try:
        yield base, port
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def get_json(base: str, path: str):
    with urllib.request.urlopen(base + path, timeout=5) as r:
        return json.load(r)


def test_the_real_server_answers_rest(live_server):
    base, _ = live_server
    assert get_json(base, "/api/snapshot")["mode"] == "mock"


def test_websocket_actually_upgrades_on_a_real_server(live_server):
    """uvicorn 에 ws 라이브러리가 없으면 여기서 잡힌다 — TestClient 로는 못 잡는다."""
    _, port = live_server
    with ws_client.connect(f"ws://127.0.0.1:{port}/ws", open_timeout=10) as ws:
        first = json.loads(ws.recv(timeout=10))
    assert first["type"] == "hello"
    assert set(first) == {"type", "seq", "server_time", "data"}
    assert "server_run_id" in first["data"]


def test_websocket_pushes_updates_while_the_fixture_plays(live_server):
    _, port = live_server
    seen = []
    with ws_client.connect(f"ws://127.0.0.1:{port}/ws", open_timeout=10) as ws:
        deadline = time.time() + 20
        while time.time() < deadline and len(seen) < 3:
            try:
                seen.append(json.loads(ws.recv(timeout=5))["type"])
            except TimeoutError:
                break
    assert seen[0] == "hello"
    assert "snapshot" in seen[1:], f"재생 중인데 push 가 안 왔다: {seen}"


def test_cors_header_is_present_for_a_cross_origin_dev_page(live_server):
    base, _ = live_server
    req = urllib.request.Request(base + "/api/snapshot",
                                 headers={"Origin": "http://127.0.0.1:8765"})
    with urllib.request.urlopen(req, timeout=5) as r:
        assert r.headers.get("access-control-allow-origin") == "*"


def test_order_pool_is_served_by_the_real_server(live_server):
    base, _ = live_server
    body = get_json(base, "/api/order_pool")
    assert body["source"] == "repo_default"
    assert all(set(o) == {"order_id", "patient_id", "item_id", "bed", "mode",
                          "mode_value", "used"} for o in body["orders"])
    assert body["problems"] == []


def test_the_socket_keeps_talking_even_when_nothing_changes(live_server):
    """조용한 것과 죽은 것을 클라이언트가 구분할 수 있어야 한다.

    변화 때만 보내면 보충 대기처럼 조용한 구간이 10 s 넘게 이어지고,
    화면은 그것을 '갱신이 멎었다' 와 구별할 수 없다.
    """
    _, port = live_server
    got = []
    with ws_client.connect(f"ws://127.0.0.1:{port}/ws", open_timeout=10) as ws:
        deadline = time.time() + 4.0
        while time.time() < deadline:
            try:
                got.append(time.time())
                json.loads(ws.recv(timeout=2.5))
            except TimeoutError:
                break
    assert len(got) >= 3, f"4 초 동안 {len(got)}건밖에 안 왔다 — 유휴 push 가 없다"
    gaps = [b - a for a, b in zip(got, got[1:], strict=False)]
    assert max(gaps) < 2.0, f"가장 긴 침묵이 {max(gaps):.1f} s — 1 s 주기가 안 지켜졌다"


# ── late_join: 실물의 뭉쳐 오는 순서를 mock 에서 만든다 ──────────────────

@pytest.fixture(scope="module")
def late_join_server():
    """`--mock-fault late_join` 으로 띄운 진짜 서버."""
    port = free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.main", "--mock", "--speed", "30", "--loop",
         "--mock-fault", "late_join", "--port", str(port)],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + BOOT_TIMEOUT_S
    while time.time() < deadline:
        if proc.poll() is not None:
            pytest.fail(f"서버가 떠보지도 못하고 죽었다:\n{proc.stdout.read()}")
        try:
            urllib.request.urlopen(base + "/api/snapshot", timeout=2).read()
            break
        except Exception:
            time.sleep(0.2)
    else:
        proc.kill()
        pytest.fail("서버가 시간 안에 안 떴다")
    # backlog 를 쏟고 한 바퀴(85.8 sim s)를 넘겨 돌 틈. 표본이 작으면 검사가 헐거워진다.
    time.sleep(4.5)
    try:
        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def all_events(base: str, limit: int = 500):
    """커서를 끝까지 돌려 받은 (전달된 seq 목록, 페이지별 stamp 목록)."""
    seqs, stamps, cursor = [], [], 0
    for _ in range(400):
        body = get_json(base, f"/api/events?epoch=all&since={cursor}&limit={limit}")
        seqs += [e["seq"] for e in body["events"]]
        stamps.append([e["stamp"] for e in body["events"]])
        assert body["next_since"] >= cursor, "커서가 되돌아갔다"
        cursor = body["next_since"]
        if not body["has_more"]:
            break
    return seqs, stamps


def test_the_fault_is_advertised_so_nobody_mistakes_it_for_real(late_join_server):
    assert get_json(late_join_server, "/api/snapshot")["mock_faults"] == ["late_join"]


def test_late_join_actually_reproduces_the_condition(late_join_server):
    """조건 재현: 예. 이게 아니오면 아래 통과는 아무것도 증명하지 않는다.

    원래 버그는 **seq 가 낮은데 event_key 가 늦은 이벤트**에서 났다. 평소 mock 은
    한 줄 재생이라 도착 순서 = 시각 순서고, 그 조건이 아예 안 생긴다.
    """
    seqs, _stamps = all_events(late_join_server)
    regressions = sum(1 for a, b in zip(seqs, seqs[1:], strict=False) if b < a)
    assert len(seqs) > 20, f"표본이 너무 작다: {len(seqs)}"
    assert regressions >= 1, (
        f"전달 순서에 seq 역행이 {regressions}곳이다 — 이 fault 가 조건을 못 만들고 있다")


def test_paging_loses_nothing_even_when_events_arrive_grouped(late_join_server):
    seen_all = set(all_events(late_join_server, limit=500)[0])
    for limit in (2, 3, 7, 11, 23):
        seqs, _stamps = all_events(late_join_server, limit=limit)
        assert len(seqs) == len(set(seqs)), f"limit={limit}: 중복 {len(seqs) - len(set(seqs))}건"
        assert seen_all <= set(seqs), f"limit={limit}: 빠진 이벤트가 있다"


def test_each_page_is_still_in_timeline_order(late_join_server):
    """뭉쳐 와도 화면은 stamp 순으로 그릴 수 있어야 한다.

    **한 epoch 안에서만 따진다.** `event_key` 는 epoch 을 먼저 보므로 세대가 섞이면
    stamp 는 단조가 아니다 — 리셋이 sim 시각을 되감을 수 있기 때문이고, 화면도
    세대가 바뀌면 목록을 통째로 버린다.
    """
    epoch = get_json(late_join_server, "/api/snapshot")["epoch"]
    cursor, pages = 0, 0
    for _ in range(200):
        body = get_json(late_join_server, f"/api/events?epoch={epoch}&since={cursor}&limit=7")
        page = [e["stamp"] for e in body["events"]]
        assert page == sorted(page), f"페이지 안이 stamp 순이 아니다: {page}"
        assert all(e["epoch"] == epoch for e in body["events"])
        pages += 1
        cursor = body["next_since"]
        if not body["has_more"]:
            break
    assert pages >= 1


def test_a_clean_server_does_not_reproduce_the_condition(live_server):
    """대조군 — 고장을 안 켜면 조건이 안 생긴다. 그래서 이 fault 가 필요하다."""
    base, _port = live_server
    seqs, _stamps = all_events(base)
    regressions = sum(1 for a, b in zip(seqs, seqs[1:], strict=False) if b < a)
    assert regressions == 0, "평소 mock 에서 역행이 생긴다면 이 fault 의 전제가 틀렸다"
