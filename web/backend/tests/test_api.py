"""HTTP·WS 계약 테스트 (FastAPI TestClient). ROS 없이 돈다."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.mock import apply_frame, load_fixture

T0 = datetime(2026, 9, 17, 8, 0, 0, tzinfo=timezone.utc)


def make_client(**kw):
    """재생기를 띄우지 않은 앱 — 상태를 직접 넣어 결정적으로 시험한다."""
    app = create_app(mock=True, autostart=False, **kw)
    return TestClient(app), app.state.world


def client_state_pair():
    """fixture 를 못 쓰는 자리에서 같은 쌍을 만든다."""
    return make_client()


@pytest.fixture
def client_state():
    client, state = make_client()
    with client:
        yield client, state


def seed(state, name, stamp, **kw):
    state.note_event({"name": name, "stamp": stamp, "epoch": kw.pop("epoch", 1), **kw}, T0)


# ── snapshot ─────────────────────────────────────────────────────────────

def test_snapshot_is_served_on_an_empty_server(client_state):
    client, _ = client_state
    body = client.get("/api/snapshot").json()
    assert body["trip"] is None
    assert body["epoch"] == 0
    assert body["mode"] == "mock"
    assert body["commands_enabled"] is False


def test_snapshot_reports_the_run_id_so_clients_can_detect_a_restart(client_state):
    client, state = client_state
    assert client.get("/api/snapshot").json()["server_run_id"] == state.server_run_id


# ── events ───────────────────────────────────────────────────────────────

def test_events_defaults_to_the_current_epoch(client_state):
    client, state = client_state
    seed(state, "DEPARTED", 1.0, epoch=1)
    seed(state, "RESET_BEGIN", 2.0, epoch=2)
    body = client.get("/api/events").json()
    assert body["epoch"] == 2
    assert [e["name"] for e in body["events"]] == ["RESET_BEGIN"]


def test_events_all_crosses_epochs(client_state):
    client, state = client_state
    seed(state, "DEPARTED", 1.0, epoch=1)
    seed(state, "RESET_BEGIN", 2.0, epoch=2)
    assert len(client.get("/api/events?epoch=all").json()["events"]) == 2


def test_events_since_cursor_walks_forward_without_gaps(client_state):
    client, state = client_state
    for i in range(5):
        seed(state, "DEPARTED", float(i))
    first = client.get("/api/events?limit=2").json()
    assert len(first["events"]) == 2 and first["has_more"] is True
    second = client.get(f"/api/events?limit=10&since={first['next_since']}").json()
    assert [e["seq"] for e in second["events"]] == [3, 4, 5]
    assert second["has_more"] is False


def test_next_since_holds_when_there_is_nothing_new(client_state):
    client, _ = client_state
    assert client.get("/api/events?since=7").json()["next_since"] == 7


def test_bad_epoch_is_a_400_not_a_crash(client_state):
    client, _ = client_state
    r = client.get("/api/events?epoch=어제")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "bad_request"


@pytest.mark.parametrize("q", ["limit=0", "limit=501", "since=-1"])
def test_out_of_range_query_params_are_rejected(client_state, q):
    client, _ = client_state
    assert client.get(f"/api/events?{q}").status_code == 422


# ── alarms ───────────────────────────────────────────────────────────────

def test_alarms_endpoint_matches_the_snapshot(client_state):
    client, state = client_state
    seed(state, "AUTH_FAIL", 10.0, request_id="req-1", order_id="ord-1")
    assert client.get("/api/alarms").json()["alarms"] == client.get("/api/snapshot").json()["alarms"]


def test_alarm_objects_carry_the_documented_fields(client_state):
    client, state = client_state
    seed(state, "AUTH_FAIL", 10.0, request_id="req-1", order_id="ord-1")
    alarm = client.get("/api/alarms").json()["alarms"][0]
    assert set(alarm) == {"id", "level", "kind", "message",
                          "request_id", "order_id", "stamp", "epoch"}


# ── logs ─────────────────────────────────────────────────────────────────

def test_logs_is_empty_until_rosout_is_wired(client_state):
    client, _ = client_state
    assert client.get("/api/logs").json() == {"logs": []}


def test_unknown_log_level_is_a_400(client_state):
    client, _ = client_state
    r = client.get("/api/logs?level=debug")
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_request"


# ── 명령 API 는 기본으로 잠겨 있다 ────────────────────────────────────────

@pytest.mark.parametrize("path", ["/api/reset", "/api/requests"])
def test_commands_are_403_by_default(client_state, path):
    client, _ = client_state
    r = client.post(path, json={})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "commands_disabled"


def test_snapshot_advertises_that_commands_are_locked(client_state):
    client, _ = client_state
    assert client.get("/api/snapshot").json()["commands_enabled"] is False


def test_reset_is_accepted_without_an_epoch_in_the_body():
    """리셋은 30 s 이상 걸릴 수 있다. 즉시 202 로 돌려주고 epoch 은 WS 로 알린다."""
    client, _state = make_client(allow_commands=True)
    with client:
        r = client.post("/api/reset", json={})
        assert r.status_code == 202
        assert r.json() == {"ok": True, "accepted": True}
        assert "epoch" not in r.json(), "동기 응답에 epoch 을 실으면 안 된다"
        assert client.get("/api/snapshot").json()["reset_in_progress"] is True


POOL_ORDER = "ord-0001"  # fixtures/order_pool.yaml (origin/main 원문 사본)의 첫 건


def request_body(**kw):
    body = {"request_id": "web-0001", "mode": 1, "destination_id": "bed_a1",
            "orders": [{"order_id": POOL_ORDER, "patient_id": "p-7", "item_id": "drug-ibu"}]}
    body.update(kw)
    return body


def test_a_web_request_knows_its_own_mode():
    client, _state = make_client(allow_commands=True)
    with client:
        r = client.post("/api/requests", json=request_body())
        assert r.status_code == 200, r.text
        assert r.json()["mode_source"] == "web_request"
        trip = client.get("/api/snapshot").json()["trip"]
        assert trip["mode"] == 1 and trip["mode_source"] == "web_request"


def test_a_second_request_while_one_is_open_is_409():
    client, _ = make_client(allow_commands=True)
    with client:
        assert client.post("/api/requests", json=request_body()).status_code == 200
        r = client.post("/api/requests", json=request_body(
            request_id="web-2", orders=[{"order_id": "ord-0003"}]))
        assert r.status_code == 409 and r.json()["error"]["code"] == "trip_in_progress"


def test_a_request_without_an_id_is_400():
    client, _ = make_client(allow_commands=True)
    with client:
        assert client.post("/api/requests", json={"mode": 0}).status_code == 400


def test_an_empty_order_list_is_rejected():
    client, _ = make_client(allow_commands=True)
    with client:
        r = client.post("/api/requests", json=request_body(orders=[]))
        assert r.status_code == 409 and "orders" in r.json()["error"]["message"]


def test_an_order_outside_the_pool_is_rejected():
    client, _ = make_client(allow_commands=True)
    with client:
        r = client.post("/api/requests", json=request_body(
            orders=[{"order_id": "ord-does-not-exist"}]))
        assert r.status_code == 409
        assert "주문 풀" in r.json()["error"]["message"]


@pytest.mark.parametrize("destination", ["침대", "bed_", "bed_A1", "bed a1", "", "bed_a1x"])
def test_a_malformed_destination_is_rejected(destination):
    # mode 2(묶음)로 보낸다 — 1인·긴급은 풀의 bed 가 destination 을 덮어써서
    # 잘못된 값이 검사에 닿지 않는다.
    client, _ = make_client(allow_commands=True)
    with client:
        r = client.post("/api/requests",
                        json=request_body(mode=2, destination_id=destination))
        assert r.status_code == 409
        assert "구역 ID 모양" in r.json()["error"]["message"]


@pytest.mark.parametrize("destination",
                         ["bed_z9", "bed_b2", "room_a1", "station_b", "ward_c", "dock_2", "pharm"])
def test_any_well_formed_zone_id_is_accepted_even_if_zones_yaml_lacks_it(destination):
    """orchestrator 는 zones.yaml 을 읽지 않는다 — 구역 ID 정규식만 본다.

    zones.yaml 에 없는 구역은 수락된 뒤 실물 fleet 의 GoToZone 거부로 드러난다.
    """
    client, _ = make_client(allow_commands=True)
    with client:
        r = client.post("/api/requests", json=request_body(mode=2, destination_id=destination))
        assert r.status_code == 200, r.text
        assert r.json()["destination_id"] == destination


def test_a_reused_request_id_is_rejected():
    client, state = make_client(allow_commands=True)
    with client:
        assert client.post("/api/requests", json=request_body()).status_code == 200
        state.trip_open = False  # 트립은 닫혔지만 request_id 는 이미 쓰였다
        r = client.post("/api/requests", json=request_body())
        assert r.status_code == 409 and "이미 쓰였다" in r.json()["error"]["message"]


def test_a_reused_order_id_is_rejected():
    client, state = make_client(allow_commands=True)
    with client:
        assert client.post("/api/requests", json=request_body()).status_code == 200
        state.trip_open = False
        r = client.post("/api/requests", json=request_body(request_id="web-2"))
        assert r.status_code == 409 and "이미 쓰인" in r.json()["error"]["message"]


def test_a_batch_request_carries_every_order(tmp_path):
    """묶음 요청을 만드는 첫 경로가 웹이다. 여러 주문이 한 요청에 들어가야 한다."""
    pool = tmp_path / "order_pool.yaml"
    pool.write_text(
        "version: 1\n"
        "orders:\n"
        '  - {order_id: ord-201, patient_id: "1001", item_id: drug-amox, bed: bed_a1}\n'
        '  - {order_id: ord-202, patient_id: "1002", item_id: drug-ibu, bed: bed_a1}\n'
        '  - {order_id: ord-203, patient_id: "1003", item_id: drug-amox, bed: bed_a1}\n',
        encoding="utf-8")
    client, _ = make_client(allow_commands=True, order_pool=str(pool))
    with client:
        assert [o["order_id"] for o in client.get("/api/order_pool").json()["orders"]] == \
            ["ord-201", "ord-202", "ord-203"]
        orders = [{"order_id": f"ord-20{i}"} for i in (1, 2, 3)]
        r = client.post("/api/requests", json=request_body(
            mode=3, destination_id="bed_a1", orders=orders))
        assert r.status_code == 200, r.text
        assert r.json()["order_ids"] == ["ord-201", "ord-202", "ord-203"]
        trip = client.get("/api/snapshot").json()["trip"]
        assert trip["mode"] == 3 and trip["mode_name"] == "MODE_BATCH_WARD"
        assert len(trip["orders"]) == 3, "묶음의 주문이 전부 트립에 들어가야 한다"
        after = {o["order_id"]: o["used"] for o in client.get("/api/order_pool").json()["orders"]}
        assert all(after.values()), "쓴 주문은 풀에서 used 로 표시돼야 한다"


def test_a_malformed_body_is_400_not_500():
    client, _ = make_client(allow_commands=True)
    with client:
        r = client.post("/api/requests", content=b"not json",
                        headers={"content-type": "application/json"})
        assert r.status_code == 400


# ── 주문 풀 (§7.3) ───────────────────────────────────────────────────────

def test_mock_serves_the_real_order_pool_by_default(client_state):
    client, _ = client_state
    body = client.get("/api/order_pool").json()
    assert body["source"] == "repo_default"
    assert [o["order_id"] for o in body["orders"]] == \
        ["ord-0001", "ord-0002", "ord-0003", "ord-0004"]
    assert all(o["used"] is False for o in body["orders"])
    assert body["problems"] == []


def test_order_pool_marks_orders_used_once_they_are_seen(client_state):
    client, state = client_state
    state.note_order({"request_id": "req-1", "order_id": POOL_ORDER, "state": 0, "stamp": 1.0})
    assert client.get("/api/order_pool").json()["orders"][0]["used"] is True


def test_order_pool_carries_what_the_picker_needs(client_state):
    client, _ = client_state
    order = client.get("/api/order_pool").json()["orders"][0]
    assert set(order) == {"order_id", "patient_id", "item_id", "bed",
                          "mode", "mode_value", "used"}


def test_a_healthy_pool_reports_no_problems(client_state):
    client, _ = client_state
    assert client.get("/api/order_pool").json()["problems"] == []


# ── 풀 스키마는 한 모양으로 좁혀졌다 ─────────────────────────────────────

def pool_client(tmp_path, text):
    pool = tmp_path / "order_pool.yaml"
    pool.write_text(text, encoding="utf-8")
    return make_client(allow_commands=True, order_pool=str(pool))


def test_the_real_pool_shape_is_read(tmp_path):
    client, _ = pool_client(tmp_path,
        'version: 1\norders:\n'
        '  - {order_id: ord-0002, patient_id: "1002", item_id: drug-ibu, bed: bed_a2, '
        'mode: urgent}\n')
    with client:
        body = client.get("/api/order_pool").json()
        assert body["source"] == "file" and body["problems"] == []
        order = body["orders"][0]
        assert order["patient_id"] == "1002" and order["bed"] == "bed_a2"
        assert (order["mode"], order["mode_value"]) == ("urgent", 1)


def test_mode_defaults_to_single_when_absent(tmp_path):
    client, _ = pool_client(tmp_path,
        'version: 1\norders:\n  - {order_id: ord-0001, patient_id: "1001"}\n')
    with client:
        order = client.get("/api/order_pool").json()["orders"][0]
        assert (order["mode"], order["mode_value"]) == ("single", 0)


def test_an_unquoted_numeric_patient_id_is_dropped_not_silently_fixed(tmp_path):
    """따옴표가 빠지면 orchestrator 가 거부한다. 웹이 조용히 고치면 실물에서만 터진다."""
    client, _ = pool_client(tmp_path,
        "version: 1\norders:\n  - {order_id: ord-0001, patient_id: 1001}\n")
    with client:
        body = client.get("/api/order_pool").json()
        assert body["orders"] == []
        assert any("따옴표" in p for p in body["problems"])


def test_a_wrong_version_is_reported(tmp_path):
    client, _ = pool_client(tmp_path,
        'version: 9\norders:\n  - {order_id: ord-1, patient_id: "1"}\n')
    with client:
        assert any("version" in p for p in client.get("/api/order_pool").json()["problems"])


def test_a_bare_list_is_no_longer_accepted(tmp_path):
    """예전에는 세 모양을 받았다. 이제 {version, orders} 하나만 받는다."""
    client, _ = pool_client(tmp_path, '- {order_id: ord-1, patient_id: "1"}\n')
    with client:
        body = client.get("/api/order_pool").json()
        assert body["orders"] == [] and body["problems"]


def test_a_missing_pool_file_says_so(tmp_path):
    client, _ = make_client(allow_commands=True, order_pool=str(tmp_path / "없다.yaml"))
    with client:
        assert any("파일이 없다" in p for p in client.get("/api/order_pool").json()["problems"])


# ── 목적지 (zones.yaml) ──────────────────────────────────────────────────

def test_destinations_come_from_the_repo_zones_file(client_state):
    """`--zones-file` 을 안 줘도 저장소 원문을 읽는다 — 손으로 적은 목록이 아니다."""
    client, _ = client_state
    body = client.get("/api/destinations").json()
    assert body["source"] == "repo_default"
    # 지금 main 의 zones.yaml 은 load·dock_1·bed_a1·station_a 넷이고,
    # 그중 배송 목적지가 될 수 있는 kind 는 bed·station 둘뿐이다.
    assert [d["destination_id"] for d in body["destinations"]] == ["bed_a1", "station_a"]


def test_room_a1_is_not_a_destination_because_main_has_no_such_zone(client_state):
    client, _ = client_state
    ids = [d["destination_id"] for d in client.get("/api/destinations").json()["destinations"]]
    assert "room_a1" not in ids


def test_a_zones_file_replaces_the_mock_list(tmp_path):
    zones = tmp_path / "zones.yaml"
    zones.write_text(
        "frame: map\n"
        "zones:\n"
        "  load: {kind: load}\n"
        "  dock_1: {kind: dock}\n"
        "  bed_b2: {kind: bed}\n"
        "  room_a1: {kind: room}\n"
        "  station_a: {kind: station}\n", encoding="utf-8")
    client, _ = make_client(allow_commands=True, zones_file=str(zones))
    with client:
        body = client.get("/api/destinations").json()
        assert body["source"] == "file"
        # load 와 dock 은 배송 목적지가 아니다
        assert [d["destination_id"] for d in body["destinations"]] == \
            ["bed_b2", "room_a1", "station_a"]


def test_the_zones_file_is_a_candidate_list_only_and_does_not_validate(tmp_path):
    """--zones-file 은 후보 표시용이다. 검증에 쓰면 실물보다 엄격해져서 거짓 거부가 난다."""
    zones = tmp_path / "zones.yaml"
    zones.write_text("frame: map\nzones:\n  bed_a1: {kind: bed}\n", encoding="utf-8")
    client, _ = make_client(allow_commands=True, zones_file=str(zones))
    with client:
        ids = [d["destination_id"] for d in client.get("/api/destinations").json()["destinations"]]
        assert ids == ["bed_a1"], "후보 목록은 파일대로여야 한다"
        r = client.post("/api/requests", json=request_body(mode=2, destination_id="station_a"))
        assert r.status_code == 200, "후보에 없어도 모양이 맞으면 수락돼야 한다"


# ── 1인·긴급은 목적지를 풀의 bed 로 자동으로 채운다 ──────────────────────

def bedded_pool(tmp_path):
    pool = tmp_path / "order_pool.yaml"
    pool.write_text(
        "version: 1\n"
        "orders:\n"
        '  - {order_id: ord-0001, patient_id: "1001", item_id: drug-amox, bed: bed_a1}\n'
        '  - {order_id: ord-0002, patient_id: "1002", item_id: drug-ibu, bed: bed_b2}\n',
        encoding="utf-8")
    return str(pool)


@pytest.mark.parametrize("mode", [0, 1])
def test_single_and_urgent_take_the_bed_from_the_order_pool(tmp_path, mode):
    """실제 목적 침상은 요청의 destination_id 가 아니라 환자→bed 매핑이 우선한다."""
    client, _ = make_client(allow_commands=True, order_pool=bedded_pool(tmp_path))
    with client:
        r = client.post("/api/requests", json=request_body(
            mode=mode, destination_id="station_a",
            orders=[{"order_id": "ord-0002"}]))
        assert r.status_code == 200, r.text
        assert r.json()["destination_id"] == "bed_b2", "풀의 bed 가 이겨야 한다"
        assert r.json()["destination_source"] == "order_pool"
        assert client.get("/api/snapshot").json()["trip"]["destination_id"] == "bed_b2"


@pytest.mark.parametrize("mode", [2, 3])
def test_batch_modes_keep_the_destination_the_operator_chose(tmp_path, mode):
    """묶음은 풀에 표현이 없다 — 사람이 고른 destination 을 그대로 쓴다."""
    client, _ = make_client(allow_commands=True, order_pool=bedded_pool(tmp_path))
    with client:
        r = client.post("/api/requests", json=request_body(
            mode=mode, destination_id="room_a1",
            orders=[{"order_id": "ord-0001"}, {"order_id": "ord-0002"}]))
        assert r.status_code == 200, r.text
        assert r.json()["destination_id"] == "room_a1"
        assert r.json()["destination_source"] == "request"


def test_single_falls_back_to_the_request_when_the_pool_has_no_bed(tmp_path):
    """풀에 bed 가 없으면 덮어쓸 것이 없다 — 사람이 고른 값을 그대로 쓴다."""
    pool = tmp_path / "order_pool.yaml"
    pool.write_text('version: 1\norders:\n  - {order_id: ord-0001, patient_id: "1001"}\n',
                    encoding="utf-8")
    client, _ = make_client(allow_commands=True, order_pool=str(pool))
    with client:
        r = client.post("/api/requests", json=request_body(
            mode=0, destination_id="bed_a1", orders=[{"order_id": "ord-0001"}]))
        assert r.status_code == 200, r.text
        assert r.json()["destination_id"] == "bed_a1"
        assert r.json()["destination_source"] == "request"


# ── /evaluator/cabinet 은 기본으로 감춘다 ────────────────────────────────

def test_evaluator_cabinet_is_hidden_by_default(client_state):
    client, state = client_state
    state.note_cabinet("ord-1", "bed_a1", True, T0)
    assert client.get("/api/snapshot").json()["cabinet"] is None


def test_evaluator_cabinet_is_shown_when_asked_and_marked_display_only():
    client, state = make_client(show_evaluator=True)
    with client:
        state.note_cabinet("ord-1", "bed_a1", True, T0)
        cabinet = client.get("/api/snapshot").json()["cabinet"]
        assert cabinet["cabinet_id"] == "bed_a1"
        assert cabinet["source"] == "evaluator"
        assert cabinet["display_only"] is True


# ── CORS·정적 서빙 (프론트 개발 편의) ────────────────────────────────────

def test_mock_allows_cross_origin_so_the_frontend_can_dev_on_another_port(client_state):
    client, _ = client_state
    r = client.get("/api/snapshot", headers={"Origin": "http://127.0.0.1:8765"})
    assert r.headers.get("access-control-allow-origin") == "*"


def test_static_dir_is_served_at_root_without_shadowing_the_api(tmp_path):
    (tmp_path / "index.html").write_text("<h1>화면</h1>", encoding="utf-8")
    app = create_app(mock=True, autostart=False, static_dir=str(tmp_path))
    with TestClient(app) as client:
        assert "화면" in client.get("/").text
        assert client.get("/api/snapshot").status_code == 200, "정적 mount 가 API 를 덮었다"


def test_a_missing_static_dir_is_ignored_not_fatal():
    app = create_app(mock=True, autostart=False, static_dir="/tmp/없는디렉터리-p3web")
    with TestClient(app) as client:
        assert client.get("/api/snapshot").status_code == 200


# ── WS ───────────────────────────────────────────────────────────────────

def test_ws_sends_a_full_snapshot_first(client_state):
    client, state = client_state
    seed(state, "REQUEST_ACCEPTED", 2.0, request_id="req-1")
    with client.websocket_connect("/ws") as ws:
        msg = ws.receive_json()
    assert msg["type"] == "hello"
    assert msg["data"]["trip"]["request_id"] == "req-1"
    assert msg["data"]["server_run_id"] == state.server_run_id


def test_ws_envelope_has_the_documented_keys(client_state):
    client, _ = client_state
    with client.websocket_connect("/ws") as ws:
        msg = ws.receive_json()
    assert set(msg) == {"type", "seq", "server_time", "data"}


# ── fixture 재생 ─────────────────────────────────────────────────────────

def test_fixture_covers_both_detail_cases():
    """작전 지시: mock fixture 에 detail 이 있는 경우와 빈 경우를 다 넣는다."""
    accepted = [f["data"] for f in load_fixture()["frames"]
                if f["kind"] == "event" and f["data"]["name"] == "REQUEST_ACCEPTED"]
    details = [a["detail"] for a in accepted]
    assert any(d == "" for d in details), "머지 전 빌드(빈 detail) 경우가 없다"
    assert any(d and json.loads(d).get("mode") is not None for d in details), \
        "#104 형식 detail 경우가 없다"


def test_replaying_the_whole_fixture_ends_docked_and_idle():
    from app.state import WorldState
    state = WorldState()
    for frame in load_fixture()["frames"]:
        apply_frame(state, frame, T0)
        state.note_clock(frame["t"], T0)
    snap = state.snapshot(T0)
    assert snap["epoch"] == 2, "리셋 1회가 들어 있어야 한다"
    assert snap["trip"] is None, "마지막 DOCKED 로 트립이 닫혀야 한다"
    assert snap["reset_in_progress"] is False


def test_fixture_refill_completes_well_inside_the_threshold():
    from app.alarms import REFILL_TIMEOUT_SIM_S
    frames = load_fixture()["frames"]
    req = next(f["t"] for f in frames
               if f["kind"] == "event" and f["data"]["name"] == "REFILL_REQUESTED")
    done = next(f["t"] for f in frames
                if f["kind"] == "event" and f["data"]["name"] == "REFILL_DONE")
    assert 20.0 < done - req < REFILL_TIMEOUT_SIM_S


def test_the_player_actually_advances_the_clock():
    from app.mock import MockPlayer
    from app.state import WorldState

    async def run():
        state = WorldState()
        player = MockPlayer(state, load_fixture(), speed=500.0)
        player.start()
        await asyncio.sleep(0.6)
        await player.stop()
        return state

    state = asyncio.run(run())
    assert state.seq > 0, "재생기가 이벤트를 하나도 넣지 못했다"
    assert (state.clock_sim_s or 0.0) > 0.0, "/clock 이 흐르지 않았다"


# ── /rosout 로그 (mock fixture 에 예시 줄이 들어 있다) ────────────────────

def test_logs_are_empty_before_anything_is_logged(client_state):
    client, _ = client_state
    assert client.get("/api/logs").json() == {"logs": []}


def test_the_fixture_carries_rosout_lines_so_the_log_tab_can_be_checked():
    from app.mock import load_fixture
    logs = [f["data"] for f in load_fixture()["frames"] if f["kind"] == "log"]
    assert len(logs) >= 4, "에러 로그 탭을 실데이터로 볼 수 있을 만큼은 있어야 한다"
    assert {log["level"] for log in logs} >= {"warn", "error"}
    assert all(log["level_value"] >= 30 for log in logs), "WARN 미만은 넣지 않는다"
    assert all(log["node"] and log["message"] for log in logs)


def test_logs_are_filtered_by_minimum_level(client_state):
    client, state = client_state
    state.note_log({"level": "warn", "level_value": 30, "node": "orchestrator",
                    "message": "느리다", "stamp": 1.0}, T0)
    state.note_log({"level": "error", "level_value": 40, "node": "fleet",
                    "message": "거부됐다", "stamp": 2.0}, T0)
    assert len(client.get("/api/logs?level=warn").json()["logs"]) == 2
    assert len(client.get("/api/logs?level=error").json()["logs"]) == 1
    assert client.get("/api/logs?level=fatal").json()["logs"] == []


def test_logs_carry_the_node_name_and_a_wall_time(client_state):
    client, state = client_state
    state.note_log({"level": "error", "level_value": 40, "node": "fleet",
                    "message": "GoToZone rejected", "stamp": 2.0}, T0)
    log = client.get("/api/logs").json()["logs"][0]
    assert log["node"] == "fleet" and log["wall"].endswith("Z")


def test_logs_return_the_most_recent_within_the_limit(client_state):
    client, state = client_state
    for i in range(10):
        state.note_log({"level": "warn", "level_value": 30, "node": "n",
                        "message": f"{i}", "stamp": float(i)}, T0)
    got = client.get("/api/logs?limit=3").json()["logs"]
    assert [log["message"] for log in got] == ["7", "8", "9"]


# ── 리셋은 주문 풀을 되살린다 (orchestrator 의 ReloadStores) ──────────────

def test_a_reset_makes_used_orders_selectable_again(client_state):
    client, state = client_state
    state.note_order({"request_id": "req-1", "order_id": "ord-0001",
                      "state": 0, "stamp": 1.0})
    used = {o["order_id"]: o["used"] for o in client.get("/api/order_pool").json()["orders"]}
    assert used["ord-0001"] is True

    # RESET_BEGIN 만으로는 아직 아니다 — _reload_stores 는 /sim/reset 이 ok 한 뒤에 돈다.
    state.note_event({"name": "RESET_BEGIN", "epoch": 2, "stamp": 60.0}, T0)
    mid = {o["order_id"]: o["used"] for o in client.get("/api/order_pool").json()["orders"]}
    assert mid["ord-0001"] is True, "RESET_DONE 전에는 아직 되살아나지 않는다"

    state.note_event({"name": "RESET_DONE", "epoch": 2, "stamp": 64.0}, T0)
    after = {o["order_id"]: o["used"] for o in client.get("/api/order_pool").json()["orders"]}
    assert after["ord-0001"] is False, "ReloadStores 로 풀이 되살아나야 한다"


def test_a_reset_also_frees_request_ids(client_state):
    """orchestrator_node._reload_stores 는 _used_requests 와 _used_orders 를 둘 다 비운다."""
    client, state = client_state
    state.note_event({"name": "REQUEST_ACCEPTED", "epoch": 1, "request_id": "req-1",
                      "stamp": 2.0, "detail": ""}, T0)
    assert "req-1" in state.used_request_ids

    state.note_event({"name": "RESET_BEGIN", "epoch": 2, "stamp": 60.0}, T0)
    assert "req-1" in state.used_request_ids, "RESET_DONE 전에는 아직 남아 있다"

    state.note_event({"name": "RESET_DONE", "epoch": 2, "stamp": 64.0}, T0)
    assert state.used_request_ids == set()


def test_only_one_order_is_used_per_lap_of_the_fixture():
    """작전 지시: 한 바퀴에 1건만 used. 나머지 3건으로 묶음을 시험할 수 있어야 한다."""
    from app.mock import apply_frame, load_fixture
    from app.state import WorldState

    state = WorldState()
    peak = 0
    for frame in load_fixture()["frames"]:
        apply_frame(state, frame, T0)
        peak = max(peak, len(state.used_order_ids))
    assert peak == 1, f"한 바퀴에 최대 {peak} 건이 쓰였다 — 1 이어야 한다"


# ── 거부 사유 코드 (화면 분기는 message 가 아니라 이것으로) ──────────────

def test_a_duplicate_request_id_has_its_own_code():
    client, state = make_client(allow_commands=True)
    with client:
        assert client.post("/api/requests", json=request_body()).status_code == 200
        state.trip_open = False
        r = client.post("/api/requests", json=request_body())
        assert r.json()["error"]["code"] == "duplicate_request_id"


def test_an_empty_order_list_has_its_own_code():
    client, _ = make_client(allow_commands=True)
    with client:
        r = client.post("/api/requests", json=request_body(orders=[]))
        assert r.json()["error"]["code"] == "empty_orders"


def test_a_malformed_destination_has_its_own_code():
    client, _ = make_client(allow_commands=True)
    with client:
        r = client.post("/api/requests", json=request_body(mode=2, destination_id="침대"))
        assert r.json()["error"]["code"] == "bad_destination"


def test_an_unknown_order_has_its_own_code():
    client, _ = make_client(allow_commands=True)
    with client:
        r = client.post("/api/requests", json=request_body(orders=[{"order_id": "없는주문"}]))
        assert r.json()["error"]["code"] == "unknown_or_used_order"


def test_a_used_order_shares_the_unknown_order_code():
    client, state = make_client(allow_commands=True)
    with client:
        assert client.post("/api/requests", json=request_body()).status_code == 200
        state.trip_open = False
        r = client.post("/api/requests", json=request_body(request_id="web-2"))
        assert r.json()["error"]["code"] == "unknown_or_used_order"


def test_an_open_trip_has_its_own_code_because_waiting_is_the_fix():
    """사람이 '잠깐 기다렸다 다시' 하면 되는 유일한 거부라 따로 구분한다."""
    client, _ = make_client(allow_commands=True)
    with client:
        assert client.post("/api/requests", json=request_body()).status_code == 200
        r = client.post("/api/requests", json=request_body(request_id="web-2",
                                                           orders=[{"order_id": "ord-0003"}]))
        assert r.json()["error"]["code"] == "trip_in_progress"


def test_a_request_during_a_reset_is_barrier_running():
    client, state = make_client(allow_commands=True)
    with client:
        state.note_event({"name": "RESET_BEGIN", "epoch": 2, "stamp": 60.0}, T0)
        r = client.post("/api/requests", json=request_body())
        assert r.status_code == 409 and r.json()["error"]["code"] == "barrier_running"


def test_the_reset_barrier_lifts_on_reset_done():
    client, state = make_client(allow_commands=True)
    with client:
        state.note_event({"name": "RESET_BEGIN", "epoch": 2, "stamp": 60.0}, T0)
        state.note_event({"name": "RESET_DONE", "epoch": 2, "stamp": 64.0}, T0)
        assert client.post("/api/requests", json=request_body()).status_code == 200


def test_every_reject_code_is_one_of_the_documented_ones():
    from app.main import REJECT_CODES
    client, _ = make_client(allow_commands=True)
    bodies = [request_body(orders=[]),
              request_body(mode=2, destination_id="침대"),
              request_body(orders=[{"order_id": "없는주문"}])]
    with client:
        for body in bodies:
            code = client.post("/api/requests", json=body).json()["error"]["code"]
            assert code in REJECT_CODES, f"문서에 없는 코드: {code}"


# ── --loop 의 바퀴 경계 ──────────────────────────────────────────────────

def test_looping_does_not_leave_the_server_stuck_in_a_reset():
    """바퀴 끝에 RESET_BEGIN 만 내면 reset_in_progress 가 계속 true 로 남는다.

    그러면 화면의 보내기 버튼이 거의 항상 잠기고 요청이 barrier_running 으로 거부된다.
    바퀴 경계의 리셋은 BEGIN·DONE 을 짝으로 내야 한다.
    """
    import asyncio

    from app.mock import MockPlayer, load_fixture
    from app.state import WorldState

    async def run():
        state = WorldState()
        player = MockPlayer(state, load_fixture(), speed=400.0, loop=True)
        player.start()
        samples = []
        for _ in range(40):
            await asyncio.sleep(0.05)
            samples.append(state.snapshot_reset_in_progress())
        await player.stop()
        return samples, state

    samples, state = asyncio.run(run())
    assert state.epoch >= 3, "여러 바퀴를 돌았어야 뜻이 있는 검사다"
    stuck = sum(samples)
    assert stuck <= len(samples) // 4, \
        f"{len(samples)}개 표본 중 {stuck}개가 리셋 중 — 바퀴 경계에 RESET_DONE 이 빠졌다"


# ── 검사 순서는 orchestrator._on_deliver_goal 원문과 같아야 한다 ──────────

def test_a_used_order_outranks_an_open_trip():
    """둘 다 걸리면 주문 검사가 먼저다 — 실물의 순서가 그렇다."""
    client, _ = make_client(allow_commands=True)
    with client:
        assert client.post("/api/requests", json=request_body()).status_code == 200
        # 트립이 열려 있고 + 주문도 이미 쓰였다
        r = client.post("/api/requests", json=request_body(request_id="web-2"))
        assert r.json()["error"]["code"] == "unknown_or_used_order"


def test_empty_orders_outranks_a_duplicate_request_id():
    client, state = make_client(allow_commands=True)
    with client:
        assert client.post("/api/requests", json=request_body()).status_code == 200
        state.trip_open = False
        r = client.post("/api/requests", json=request_body(orders=[]))
        assert r.json()["error"]["code"] == "empty_orders"


def test_the_reset_barrier_outranks_everything_else():
    client, state = make_client(allow_commands=True)
    with client:
        state.note_event({"name": "RESET_BEGIN", "epoch": 2, "stamp": 60.0}, T0)
        r = client.post("/api/requests", json=request_body(orders=[], destination_id="침대"))
        assert r.json()["error"]["code"] == "barrier_running"


# ── RESET_DONE 뒤 3.5 s settle 창 ────────────────────────────────────────

def just_now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


def test_requests_are_still_refused_right_after_reset_done():
    """orchestrator 는 RESET_DONE 뒤에도 _accept_after 까지 약 3 s 거부한다 (계약 6절 5)."""
    client, state = make_client(allow_commands=True)
    with client:
        state.note_event({"name": "RESET_BEGIN", "epoch": 2, "stamp": 60.0}, just_now())
        state.note_event({"name": "RESET_DONE", "epoch": 2, "stamp": 64.0}, just_now())
        r = client.post("/api/requests", json=request_body())
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "barrier_running"
        assert "아직 안 끝났다" in r.json()["error"]["message"]


def test_snapshot_says_when_requests_will_be_accepted_again():
    client, state = make_client(allow_commands=True)
    with client:
        state.note_event({"name": "RESET_BEGIN", "epoch": 2, "stamp": 60.0}, just_now())
        state.note_event({"name": "RESET_DONE", "epoch": 2, "stamp": 64.0}, just_now())
        snap = client.get("/api/snapshot").json()
        assert snap["accepting_requests"] is False
        assert snap["accept_after_wall"] is not None, "언제 풀리는지 알려 줘야 버튼을 잠근다"
        assert snap["accept_after_wall"].endswith("Z")


def test_during_the_barrier_there_is_no_known_accept_time():
    client, state = make_client(allow_commands=True)
    with client:
        state.note_event({"name": "RESET_BEGIN", "epoch": 2, "stamp": 60.0}, just_now())
        snap = client.get("/api/snapshot").json()
        assert snap["accepting_requests"] is False
        assert snap["accept_after_wall"] is None, "RESET_DONE 전에는 언제 풀릴지 모른다"


def test_the_settle_window_expires(client_state):
    client, state = client_state
    # T0 는 한참 전이므로 settle 창은 이미 지났다
    state.note_event({"name": "RESET_BEGIN", "epoch": 2, "stamp": 60.0}, T0)
    state.note_event({"name": "RESET_DONE", "epoch": 2, "stamp": 64.0}, T0)
    assert client.get("/api/snapshot").json()["accepting_requests"] is True


def test_a_fresh_server_accepts_requests(client_state):
    client, _ = client_state
    snap = client.get("/api/snapshot").json()
    assert snap["accepting_requests"] is True
    assert snap["accept_after_wall"] is None


def test_an_expired_accept_time_is_reported_as_null(client_state):
    """지난 시각을 계속 들고 있으면 화면이 '아직 기다려야 하나' 를 헷갈린다."""
    client, state = client_state
    state.note_event({"name": "RESET_BEGIN", "epoch": 2, "stamp": 60.0}, T0)
    state.note_event({"name": "RESET_DONE", "epoch": 2, "stamp": 64.0}, T0)
    snap = client.get("/api/snapshot").json()
    assert snap["accepting_requests"] is True
    assert snap["accept_after_wall"] is None


def test_a_mock_reset_finishes_on_its_own():
    """mock 의 리셋이 RESET_BEGIN 만 내면 barrier 가 영영 안 풀린다."""
    import time

    client, state = make_client(allow_commands=True)
    with client:
        assert client.post("/api/reset", json={}).status_code == 202
        assert client.get("/api/snapshot").json()["reset_in_progress"] is True

        from app.main import MOCK_RESET_SECONDS
        deadline = time.time() + MOCK_RESET_SECONDS + 5.0
        while time.time() < deadline:
            if not client.get("/api/snapshot").json()["reset_in_progress"]:
                break
            time.sleep(0.1)
        snap = client.get("/api/snapshot").json()
        assert snap["reset_in_progress"] is False, "RESET_DONE 이 끝내 안 왔다"
        assert snap["epoch"] == 1
        # 그래도 settle 창은 남아 있어야 한다
        assert snap["accepting_requests"] is False
        assert snap["accept_after_wall"] is not None


def test_reset_stuck_actually_reaches_the_snapshot():
    """알람 규칙이 맞아도 배선이 빠지면 화면에 안 뜬다 — 규칙과 따로 배선을 본다."""
    from datetime import datetime, timedelta, timezone

    from app.state import WorldState

    now = datetime.now(timezone.utc)
    state = WorldState()
    state.note_clock(200.0, now)
    state.note_event({"name": "RESET_BEGIN", "epoch": 2, "stamp": 200.0},
                     now - timedelta(seconds=40))
    snap = state.snapshot(now)
    stuck = next(a for a in snap["alarms"] if a["kind"] == "RESET_STUCK")
    assert stuck["level"] == "error"
    assert snap["accepting_requests"] is False


def test_a_reset_that_finishes_in_time_never_looks_stuck():
    from datetime import datetime, timedelta, timezone

    from app.state import WorldState

    now = datetime.now(timezone.utc)
    state = WorldState()
    state.note_clock(200.0, now)
    state.note_event({"name": "RESET_BEGIN", "epoch": 2, "stamp": 200.0},
                     now - timedelta(seconds=40))
    state.note_event({"name": "RESET_DONE", "epoch": 2, "stamp": 203.0}, now)
    kinds = {a["kind"] for a in state.snapshot(now)["alarms"]}
    assert "RESET_STUCK" not in kinds


def test_the_stuck_threshold_can_be_shortened_so_it_can_be_seen_live():
    """35 s 를 기다리며 화면을 확인할 수는 없다. 줄여서 띄울 수 있어야 한다."""
    from datetime import datetime, timedelta, timezone

    client, state = make_client(allow_commands=True, reset_timeout=2.0)
    with client:
        now = datetime.now(timezone.utc)
        state.note_clock(200.0, now)
        state.note_event({"name": "RESET_BEGIN", "epoch": 2, "stamp": 200.0},
                         now - timedelta(seconds=3))
        kinds = {a["kind"] for a in client.get("/api/alarms").json()["alarms"]}
        assert "RESET_STUCK" in kinds


def test_a_stuck_reset_can_be_simulated_so_the_alarm_can_be_seen():
    """정상 mock 리셋은 늘 완결된다 — 그러면 RESET_STUCK 화면을 실서버에서 볼 수 없다."""
    import time

    from app.faults import Faults
    client, _ = make_client(allow_commands=True, faults=Faults(["stuck_reset"]),
                            reset_timeout=0.5)
    with client:
        assert client.post("/api/reset", json={}).status_code == 202
        deadline = time.time() + 5.0
        while time.time() < deadline:
            kinds = {a["kind"] for a in client.get("/api/alarms").json()["alarms"]}
            if "RESET_STUCK" in kinds:
                break
            time.sleep(0.1)
        else:
            raise AssertionError("RESET_STUCK 이 끝내 안 떴다")
        snap = client.get("/api/snapshot").json()
        assert snap["reset_in_progress"] is True
        assert snap["accepting_requests"] is False


def test_the_normal_mock_reset_never_looks_stuck():
    import time

    client, _ = make_client(allow_commands=True, reset_timeout=0.5)
    with client:
        client.post("/api/reset", json={})
        from app.main import MOCK_RESET_SECONDS
        time.sleep(MOCK_RESET_SECONDS + 0.8)
        kinds = {a["kind"] for a in client.get("/api/alarms").json()["alarms"]}
        assert "RESET_STUCK" not in kinds, "정상 리셋인데 멈춘 것으로 보인다"


def test_an_idle_server_still_pushes_on_the_socket(client_state):
    """재생이 멎어 있어도(autostart=False) 소켓은 계속 말해야 한다."""
    import time

    from app.main import WS_IDLE_PUSH_S

    client, _ = client_state
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "hello"
        start = time.time()
        second = ws.receive_json()
        waited = time.time() - start
    assert second["type"] == "snapshot"
    assert waited < WS_IDLE_PUSH_S * 3, f"{waited:.1f} s 나 기다렸다"


# ── 보충 중 거부 (실습8: ABORT out_of_stock 을 미리 막는다) ──────────────

def stocked(state, item="drug-amox", count=5, active=True, paused=()):
    state.note_dispenser({"paused_item_ids": list(paused), "queue_length": 0,
                          "belt_occupied": False, "stamp": 0.0,
                          "slots": [{"item_id": item, "slot": 0, "lot_id": "", "expiry": "",
                                     "count": count, "active": active}]}, T0)


def test_a_request_for_a_paused_item_is_refused_before_it_is_sent():
    """실습8: web-0002(ord-0003 amox)가 수락됐다가 적재에서 ABORT out_of_stock 으로
    1.2 s 만에 끝났다. 사람이 보기엔 "넣었는데 갑자기 죽었다" 다."""
    client, state = make_client(allow_commands=True)
    with client:
        stocked(state, paused=["drug-amox"])
        r = client.post("/api/requests", json=request_body(orders=[{"order_id": "ord-0001"}]))
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "refill_in_progress"
        assert "drug-amox" in r.json()["error"]["message"]


def test_a_request_for_an_empty_item_is_refused():
    client, state = make_client(allow_commands=True)
    with client:
        stocked(state, count=0, active=False)
        r = client.post("/api/requests", json=request_body(orders=[{"order_id": "ord-0001"}]))
        assert r.json()["error"]["code"] == "refill_in_progress"


def test_a_request_for_a_stocked_item_goes_through():
    client, state = make_client(allow_commands=True)
    with client:
        stocked(state)
        assert client.post("/api/requests",
                           json=request_body(orders=[{"order_id": "ord-0001"}])).status_code == 200


def test_an_item_the_dispenser_never_mentions_is_not_blocked():
    """모르는 것으로 거부하지 않는다."""
    client, state = make_client(allow_commands=True)
    with client:
        stocked(state, item="drug-ibu")          # ord-0001 은 drug-amox 다
        assert client.post("/api/requests",
                           json=request_body(orders=[{"order_id": "ord-0001"}])).status_code == 200


def test_the_used_order_check_still_comes_first():
    """검사 순서: 풀에 없음·이미 쓴 주문 → 보충 중. 겹치면 앞의 것이 나온다."""
    client, state = make_client(allow_commands=True)
    with client:
        stocked(state, paused=["drug-amox"])
        r = client.post("/api/requests", json=request_body(orders=[{"order_id": "없는주문"}]))
        assert r.json()["error"]["code"] == "unknown_or_used_order"


# ── 모드와 주문 수 (실습8: 묶음을 mode 0 으로 보내 사유 없이 거부됐다) ───

@pytest.mark.parametrize(("mode", "label"), [(0, "1인"), (1, "긴급")])
def test_single_modes_refuse_more_than_one_order(mode, label):
    """실습8 의 묶음 거부 2회가 이것이다 — mode 0 에 주문 3개.

    `trip_fsm._build_stops` 가 정거장을 못 만들어 **사유 없이** goal 거부로 끝났다.
    """
    client, _ = make_client(allow_commands=True)
    with client:
        r = client.post("/api/requests", json=request_body(
            mode=mode, orders=[{"order_id": "ord-0001"}, {"order_id": "ord-0002"},
                               {"order_id": "ord-0003"}]))
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "bad_mode_for_orders"
        assert label in r.json()["error"]["message"]
        assert "3건" in r.json()["error"]["message"]


@pytest.mark.parametrize("mode", [0, 1])
def test_single_modes_accept_exactly_one_order(mode):
    client, state = make_client(allow_commands=True)
    with client:
        stocked(state)
        assert client.post("/api/requests", json=request_body(
            mode=mode, orders=[{"order_id": "ord-0001"}])).status_code == 200


@pytest.mark.parametrize("mode", [2, 3])
def test_batch_modes_accept_several_orders(mode):
    client, state = make_client(allow_commands=True)
    with client:
        stocked(state)
        r = client.post("/api/requests", json=request_body(
            mode=mode, destination_id="bed_a1",
            orders=[{"order_id": "ord-0001"}, {"order_id": "ord-0002"}]))
        assert r.status_code == 200, r.text


@pytest.mark.parametrize("mode", [2, 3])
def test_a_batch_mode_with_one_order_is_allowed(mode):
    """계약에 그런 제약이 없다. 실제로 가능한 요청이다."""
    client, state = make_client(allow_commands=True)
    with client:
        stocked(state)
        assert client.post("/api/requests", json=request_body(
            mode=mode, orders=[{"order_id": "ord-0001"}])).status_code == 200


def test_the_mode_check_comes_before_any_state_check():
    """입력이 스스로 모순인 것은 서버 상태를 보기 전에 답한다 —
    그래야 사람이 "기다리면 되나?" 로 헷갈리지 않는다."""
    client, state = make_client(allow_commands=True)
    with client:
        state.note_event({"name": "RESET_BEGIN", "epoch": 2, "stamp": 60.0}, T0)
        r = client.post("/api/requests", json=request_body(
            mode=0, orders=[{"order_id": "ord-0001"}, {"order_id": "ord-0002"}]))
        assert r.json()["error"]["code"] == "bad_mode_for_orders", \
            "리셋 중이어도 모순된 입력이 먼저다"


# ── error.detail — 막힌 대상을 구조로 싣는다 ────────────────────────────

def refuse(client, **kw):
    return client.post("/api/requests", json=request_body(**kw)).json()["error"]


def test_refill_in_progress_says_which_item_is_blocked():
    """화면이 "무엇을 기다려야 하는지" 를 알려면 약 이름이 필요하다.

    `message` 안의 한글 문장에서 뽑게 하면, 계약이 "`message` 로 분기하지 마라" 라고 하면서
    파싱을 강요하는 셈이 된다. 문구를 다듬으면 조용히 깨진다.
    """
    client, state = make_client(allow_commands=True)
    with client:
        stocked(state, paused=["drug-amox"])
        e = refuse(client, orders=[{"order_id": "ord-0001"}])
        assert e["code"] == "refill_in_progress"
        assert e["detail"]["item_id"] == "drug-amox"
        assert e["detail"]["order_id"] == "ord-0001"


def test_bad_mode_for_orders_says_the_mode_and_the_count():
    client, _ = make_client(allow_commands=True)
    with client:
        e = refuse(client, mode=0, orders=[{"order_id": "ord-0001"},
                                           {"order_id": "ord-0002"},
                                           {"order_id": "ord-0003"}])
        assert e["detail"] == {"mode": 0, "order_count": 3}


def test_unknown_order_says_which_order():
    client, _ = make_client(allow_commands=True)
    with client:
        e = refuse(client, orders=[{"order_id": "없는주문"}])
        assert e["detail"]["order_id"] == "없는주문"


def test_a_used_order_says_which_order():
    client, state = make_client(allow_commands=True)
    with client:
        stocked(state)
        assert client.post("/api/requests",
                           json=request_body(orders=[{"order_id": "ord-0001"}])).status_code == 200
        state.trip_open = False
        e = refuse(client, request_id="web-2", orders=[{"order_id": "ord-0001"}])
        assert e["detail"]["order_id"] == "ord-0001"


def test_bad_destination_says_which_destination():
    client, _ = make_client(allow_commands=True)
    with client:
        e = refuse(client, mode=2, destination_id="침대")
        assert e["detail"]["destination_id"] == "침대"


def test_duplicate_request_id_says_which_id():
    client, state = make_client(allow_commands=True)
    with client:
        stocked(state)
        assert client.post("/api/requests",
                           json=request_body(orders=[{"order_id": "ord-0001"}])).status_code == 200
        state.trip_open = False
        e = refuse(client, orders=[{"order_id": "ord-0002"}])
        assert e["detail"]["request_id"] == "web-0001"


def test_trip_in_progress_says_which_trip_holds_it():
    client, state = make_client(allow_commands=True)
    with client:
        stocked(state)
        assert client.post("/api/requests",
                           json=request_body(orders=[{"order_id": "ord-0001"}])).status_code == 200
        e = refuse(client, request_id="web-2", orders=[{"order_id": "ord-0002"}])
        assert e["code"] == "trip_in_progress"
        assert e["detail"]["request_id"] == "web-0001", "무엇이 끝나기를 기다리는지 알려야 한다"


def test_the_barrier_says_when_it_lifts():
    from datetime import datetime, timezone

    client, state = make_client(allow_commands=True)
    with client:
        now = datetime.now(timezone.utc)
        state.note_event({"name": "RESET_BEGIN", "epoch": 2, "stamp": 60.0}, now)
        state.note_event({"name": "RESET_DONE", "epoch": 2, "stamp": 64.0}, now)
        e = refuse(client, mode=2)
        assert e["code"] == "barrier_running"
        assert e["detail"]["accept_after_wall"].endswith("Z")


def test_a_refusal_without_a_subject_has_no_detail():
    """`detail` 은 있을 때만 싣는다. 빈 객체를 보내면 화면이 있는 줄 알고 들여다본다."""
    client, _ = make_client(allow_commands=True)
    with client:
        e = refuse(client, orders=[])
        assert e["code"] == "empty_orders"
        assert "detail" not in e


def test_every_detail_value_is_json_safe():
    import json as _json

    client, state = make_client(allow_commands=True)
    with client:
        stocked(state, paused=["drug-amox"])
        e = refuse(client, orders=[{"order_id": "ord-0001"}])
        _json.dumps(e)   # 던지면 실패


# ── 남은 시간은 서버가 센다 (브라우저 시계를 믿지 않는다) ───────────────

def test_the_snapshot_says_how_many_seconds_remain():
    """`accept_after_wall` 은 절대 시각이라 화면이 제 시계와 빼야 한다.

    **브라우저 시계가 서버와 같다는 보장이 없다** — 30 s 틀어져 있으면 "33초 뒤" 라고 쓴다.
    신선도를 `age_wall_s` 로 주는 것과 같은 이유로 남은 초도 서버가 낸다.
    """
    from datetime import datetime, timedelta, timezone

    _client, state = make_client(allow_commands=True)
    now = datetime.now(timezone.utc)
    state.note_event({"name": "RESET_BEGIN", "epoch": 2, "stamp": 60.0}, now)
    state.note_event({"name": "RESET_DONE", "epoch": 2, "stamp": 64.0}, now)

    at_once = state.snapshot(now)["accept_in_s"]
    assert at_once is not None and 3.0 < at_once <= 3.5

    later = state.snapshot(now + timedelta(seconds=2))["accept_in_s"]
    assert later is not None and later < at_once, "시간이 지나면 줄어야 한다"


def test_the_remaining_seconds_go_null_together_with_the_deadline():
    """`accept_after_wall` 이 null 인데 `accept_in_s` 가 0.0 이면 화면이 아직 기다린다고 읽는다."""
    from datetime import datetime, timedelta, timezone

    _client, state = make_client(allow_commands=True)
    now = datetime.now(timezone.utc)
    state.note_event({"name": "RESET_BEGIN", "epoch": 2, "stamp": 60.0}, now)
    state.note_event({"name": "RESET_DONE", "epoch": 2, "stamp": 64.0}, now)

    snap = state.snapshot(now + timedelta(seconds=5))
    assert snap["accepting_requests"] is True
    assert snap["accept_after_wall"] is None
    assert snap["accept_in_s"] is None, "둘이 짝으로 null 이어야 한다"


def test_during_the_barrier_the_remaining_time_is_unknown():
    """`RESET_DONE` 전에는 언제 풀릴지 모른다. 숫자를 지어내지 않는다."""
    client, state = client_state_pair()
    with client:
        state.note_event({"name": "RESET_BEGIN", "epoch": 2, "stamp": 60.0}, T0)
        snap = client.get("/api/snapshot").json()
        assert snap["accepting_requests"] is False
        assert snap["accept_in_s"] is None
        assert snap["accept_after_wall"] is None


def test_the_barrier_refusal_carries_the_remaining_seconds():
    from datetime import datetime, timezone

    client, state = make_client(allow_commands=True)
    with client:
        now = datetime.now(timezone.utc)
        state.note_event({"name": "RESET_BEGIN", "epoch": 2, "stamp": 60.0}, now)
        state.note_event({"name": "RESET_DONE", "epoch": 2, "stamp": 64.0}, now)
        e = refuse(client, mode=2)
        assert e["code"] == "barrier_running"
        assert 0.0 < e["detail"]["accept_in_s"] <= 3.5


# ── 묶음 안에서 재고가 서로 잡아먹는 것 (실습9) ─────────────────────────

def stock_of(state, amox=5, ibu=5):
    state.note_dispenser({"paused_item_ids": [], "queue_length": 0, "belt_occupied": False,
                          "stamp": 0.0,
                          "slots": [{"item_id": "drug-amox", "slot": 0, "lot_id": "",
                                     "expiry": "", "count": amox, "active": True},
                                    {"item_id": "drug-ibu", "slot": 1, "lot_id": "",
                                     "expiry": "", "count": ibu, "active": True}]}, T0)


BOTH_AMOX = [{"order_id": "ord-0001"}, {"order_id": "ord-0003"}]   # 풀에서 둘 다 drug-amox


def test_a_batch_that_outruns_the_stock_is_refused():
    """실습9: amox 재고 1 에 묶음으로 amox 2개가 들어가 뒤의 것이 ABORT out_of_stock 으로 끝났다.

    `refill_in_progress` 는 **요청 시점에 이미 0** 인 것만 막는다 — 묶음 안에서 서로
    잡아먹는 것은 못 막는다.
    """
    client, state = make_client(allow_commands=True)
    with client:
        stock_of(state, amox=1)
        r = client.post("/api/requests", json=request_body(mode=2, orders=BOTH_AMOX))
        assert r.status_code == 409
        e = r.json()["error"]
        assert e["code"] == "insufficient_stock"
        assert e["detail"]["item_id"] == "drug-amox"
        assert e["detail"]["requested"] == 2
        assert e["detail"]["available"] == 1


def test_the_same_batch_passes_when_the_stock_covers_it():
    client, state = make_client(allow_commands=True)
    with client:
        stock_of(state, amox=2)
        assert client.post("/api/requests",
                           json=request_body(mode=2, orders=BOTH_AMOX)).status_code == 200


def test_items_are_counted_separately():
    """amox 1개 + ibu 1개는 amox 재고가 1 이어도 통과한다 — 품목별로 센다."""
    client, state = make_client(allow_commands=True)
    with client:
        stock_of(state, amox=1)
        mixed = [{"order_id": "ord-0001"}, {"order_id": "ord-0002"}]   # amox + ibu
        assert client.post("/api/requests",
                           json=request_body(mode=2, orders=mixed)).status_code == 200


def test_an_item_the_dispenser_never_mentions_is_not_counted():
    client, state = make_client(allow_commands=True)
    with client:
        state.note_dispenser({"paused_item_ids": [], "queue_length": 0, "belt_occupied": False,
                              "stamp": 0.0,
                              "slots": [{"item_id": "drug-ibu", "slot": 0, "lot_id": "",
                                         "expiry": "", "count": 1, "active": True}]}, T0)
        assert client.post("/api/requests",
                           json=request_body(mode=2, orders=BOTH_AMOX)).status_code == 200


def test_a_zero_stock_item_reports_refill_not_insufficient():
    """검사 순서: 이미 0 인 것은 `refill_in_progress` 가 먼저 잡는다."""
    client, state = make_client(allow_commands=True)
    with client:
        stock_of(state, amox=0)
        e = refuse(client, mode=2, orders=BOTH_AMOX)
        assert e["code"] == "refill_in_progress"


def test_a_single_order_is_unaffected_by_this_check():
    client, state = make_client(allow_commands=True)
    with client:
        stock_of(state, amox=1)
        assert client.post("/api/requests",
                           json=request_body(orders=[{"order_id": "ord-0001"}])).status_code == 200


def test_every_shortage_is_reported_not_just_the_first():
    """한 건만 말하면, 두 품목이 모자랄 때 운영자가 하나를 빼고 다시 보내 두 번째 거부를 받는다.

    시연 중에 그게 두 번 뜨면 화면이 운영자를 놀리는 것처럼 보인다.
    """
    client, state = make_client(allow_commands=True)
    with client:
        stock_of(state, amox=1, ibu=1)
        e = refuse(client, mode=3, orders=[{"order_id": "ord-0001"}, {"order_id": "ord-0003"},
                                           {"order_id": "ord-0002"}, {"order_id": "ord-0004"}])
        assert e["code"] == "insufficient_stock"
        assert e["detail"]["shortages"] == [
            {"item_id": "drug-amox", "requested": 2, "available": 1},
            {"item_id": "drug-ibu", "requested": 2, "available": 1},
        ]
        assert "drug-ibu" in e["message"], "문구에도 나머지를 알려야 한다"


def test_the_representative_keys_stay_beside_shortages():
    """옛 클라이언트는 위 세 키만 읽는다. 그대로 둬야 안 깨진다."""
    client, state = make_client(allow_commands=True)
    with client:
        stock_of(state, amox=1)
        d = refuse(client, mode=2, orders=BOTH_AMOX)["detail"]
        assert d["item_id"] == d["shortages"][0]["item_id"]
        assert d["requested"] == d["shortages"][0]["requested"]
        assert d["available"] == d["shortages"][0]["available"]


def test_shortages_are_in_a_stable_order():
    """품목 이름 순이다. 같은 요청이 매번 다른 순서를 내면 화면이 흔들린다."""
    client, state = make_client(allow_commands=True)
    with client:
        stock_of(state, amox=0, ibu=1)
        state.note_dispenser({"paused_item_ids": [], "queue_length": 0, "belt_occupied": False,
                              "stamp": 0.0,
                              "slots": [{"item_id": "drug-ibu", "slot": 1, "lot_id": "",
                                         "expiry": "", "count": 1, "active": True},
                                        {"item_id": "drug-amox", "slot": 0, "lot_id": "",
                                         "expiry": "", "count": 1, "active": True}]}, T0)
        d = refuse(client, mode=3, orders=[{"order_id": "ord-0002"}, {"order_id": "ord-0004"},
                                           {"order_id": "ord-0001"},
                                           {"order_id": "ord-0003"}])["detail"]
        names = [s["item_id"] for s in d["shortages"]]
        assert names == sorted(names)


def test_one_shortage_keeps_the_message_simple():
    client, state = make_client(allow_commands=True)
    with client:
        stock_of(state, amox=1)
        e = refuse(client, mode=2, orders=BOTH_AMOX)
        assert "그 밖에" not in e["message"]
        assert len(e["detail"]["shortages"]) == 1
