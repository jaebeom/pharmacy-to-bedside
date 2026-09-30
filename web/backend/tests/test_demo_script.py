"""9/21 시연 대본을 API 수준에서 그대로 돌린다 (`docs/runbooks/demo-0921-v2.md` 3절).

**왜 따로 있나.** 대본의 조각은 `test_api.py` 가 이미 하나씩 다룬다. 여기서 보는 것은 조각이
아니라 **순서**다. 발표자가 밟는 차례대로 요청을 넣고, 각 지점에서 화면에 무엇이 보여야 하는지를
확인한다. 9/20 새벽 master01 에서 확정 대본이 끝까지 돈 것(#240 issuecomment-5744328502)을
CI 가 매번 다시 밟게 하는 것이 목적이다.

대본(기본 풀 기준):
  1. 긴급 `ord-0002` — **스택의 자동 요청**이 보낸다. 웹에서 넣지 않는다.
  2. 1인 `ord-0001` (mode 0, `bed_a1`) — 웹. 1 의 트립이 끝난 뒤.
  3. 묶음 `ord-0003`+`ord-0004` (mode 2, `bed_b1`) — 웹. 보충이 모두 끝난 뒤.
  4. 리셋 → 다시 자동 긴급 `ord-0002`.

실물에서 관측된 거부 세 가지도 같이 재현한다:
  - 자동 요청이 쓴 주문을 웹으로 또 보내면 409 `unknown_or_used_order`
  - 보충 중인 약품의 주문은 409 `refill_in_progress` (실습9)
  - `single`·`urgent` 에 주문 2건이면 400 `bad_mode_for_orders`

ROS 없이 돈다. 스택 대신 이벤트를 직접 넣어 장면을 만든다. 이 파일은 마커가 없으므로 기본
실행에 포함되고, 따라서 `-m "not ros"` 로 빠지지 않는다.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

T0 = datetime(2026, 9, 17, 8, 0, 0, tzinfo=timezone.utc)

AMOX = "drug-amox"
IBU = "drug-ibu"

#: 기본 풀 `src/rokey_p3_orchestrator/config/order_pool.yaml`.
#: 자동 요청은 긴급이 큐 맨 앞에 서므로 언제나 ord-0002 다(runbook 3절).
AUTO_ORDER = ("ord-0002", IBU)
SINGLE_ORDER = ("ord-0001", AMOX)
BATCH_ORDERS = (("ord-0003", AMOX), ("ord-0004", IBU))


# ── 장면 만들기 ───────────────────────────────────────────────────────────

def demo_server():
    """재생기를 띄우지 않은 앱. 상태를 직접 넣어 대본을 결정적으로 재현한다."""
    app = create_app(mock=True, autostart=False, allow_commands=True)
    return TestClient(app), app.state.world


@pytest.fixture
def demo():
    client, state = demo_server()
    with client:
        stock(state)
        yield client, state


def event(state, name, stamp, **kw):
    state.note_event({"name": name, "stamp": stamp, "epoch": kw.pop("epoch", 1), **kw}, T0)


def stock(state, *, amox=1, ibu=1, paused=()):
    """조제기 상태. 기본값이 대본의 출발점이다 — 약품마다 slot a 에 1개(runbook 3절).

    `paused` 는 조제기가 직접 말해 주는 `paused_item_ids` 다. 웹의 409 검사도, 화면의
    `PAUSED` 표시도 이 값을 본다.
    """
    state.note_dispenser({
        "paused_item_ids": list(paused), "queue_length": 0, "belt_occupied": False,
        "stamp": 0.0,
        "slots": [
            {"item_id": AMOX, "slot": 0, "lot_id": "", "expiry": "",
             "count": amox, "active": amox > 0},
            {"item_id": IBU, "slot": 1, "lot_id": "", "expiry": "",
             "count": ibu, "active": ibu > 0},
        ],
    }, T0)


def auto_request_accepted(state, stamp=3.0, request_id="r001-0001", epoch=1):
    """스택의 자동 요청이 수락된 장면.

    웹을 거치지 않으므로 웹 백엔드는 `REQUEST_ACCEPTED` 하나로만 이것을 안다. detail 의 모양은
    orchestrator 가 내는 #104 형식이다 — 이것을 파싱해야 묶음의 주문까지 사용 표에 들어간다.
    """
    order_id, item_id = AUTO_ORDER
    detail = json.dumps({
        "mode": 1, "destination_id": "bed_a2",
        "orders": [{"order_id": order_id, "patient_id": "1002", "item_id": item_id}],
    })
    event(state, "REQUEST_ACCEPTED", stamp, epoch=epoch,
          request_id=request_id, detail=detail, robot_id="amr_1")


def trip_finishes(state, stamp=15.0, epoch=1):
    """트립이 도크로 돌아와 닫힌다. 발표자가 "웹 트립 표시가 비었다" 로 보는 그 지점."""
    event(state, "DOCKED", stamp, epoch=epoch, robot_id="amr_1")


def refill_cycle(state, item, *, start=20.0, epoch=1):
    """재고 소진 → 보충 → 재개. 대본 3(묶음) 전에 기다리는 바로 그 구간.

    순서가 중요하다. `REFILL_DONE` 이 `DISPENSER_RESUMED` 보다 먼저 온다. 그래서 runbook 은
    `보충 중` 이 아니라 `PAUSED` 가 사라진 것을 기준으로 보라고 적는다.
    """
    stock(state, **{_slot_kw(item): 0}, paused=[item])
    event(state, "REFILL_REQUESTED", start, epoch=epoch, detail=item)
    yield  # 보충 중
    event(state, "REFILL_DONE", start + 48.0, epoch=epoch, detail=item)
    stock(state, paused=[item])          # 아직 PAUSED — 재개 전이다
    yield  # 보충은 끝났지만 아직 재개 전
    event(state, "DISPENSER_RESUMED", start + 56.0, epoch=epoch, detail=item)
    stock(state)                          # 재고가 찼고 PAUSED 도 풀렸다


def _slot_kw(item):
    return "amox" if item == AMOX else "ibu"


def reset(state, *, stamp=100.0, epoch=2):
    """리셋 한 번. `RESET_DONE` 이 사용 표를 비우는 지점이다(계약 6절 3)."""
    event(state, "RESET_BEGIN", stamp, epoch=epoch)
    event(state, "RESET_DONE", stamp + 1.0, epoch=epoch)


# ── 요청 보내기 ───────────────────────────────────────────────────────────

def order_entry(pair, patient_id="p-1"):
    order_id, item_id = pair
    return {"order_id": order_id, "patient_id": patient_id, "item_id": item_id}


def send(client, *, request_id, mode, destination_id, orders):
    return client.post("/api/requests", json={
        "request_id": request_id, "mode": mode,
        "destination_id": destination_id,
        "orders": [order_entry(o) for o in orders],
    })


def send_single(client, request_id="web-0001"):
    """대본 2 — 1인, `ord-0001`, `bed_a1`."""
    return send(client, request_id=request_id, mode=0,
                destination_id="bed_a1", orders=[SINGLE_ORDER])


def send_batch(client, request_id="web-0002"):
    """대본 3 — 묶음, `ord-0003`+`ord-0004`, `bed_b1`.

    묶음은 품목이 겹치지 않게 보낸다(runbook 3절). amox 와 ibu 하나씩이다.
    """
    return send(client, request_id=request_id, mode=2,
                destination_id="bed_b1", orders=list(BATCH_ORDERS))


def code_of(response):
    return response.json()["error"]["code"]


def used_map(client):
    """웹 화면의 주문 목록이 보는 것. 발표자는 여기서 `used=false` 인 것을 고른다."""
    return {o["order_id"]: o["used"] for o in client.get("/api/order_pool").json()["orders"]}


# ── 대본을 처음부터 끝까지 ────────────────────────────────────────────────

def test_the_whole_script_runs_in_order(demo):
    """대본 1 → 2 → 3 → 리셋 → 1 을 그대로 걷는다.

    조각마다 따로 시험이 있는데도 이걸 두는 이유는, 각 단계가 **앞 단계가 만든 상태 위에서**
    돌기 때문이다. 순서를 바꾸면 통과하지 않는다.
    """
    client, state = demo

    # 1. 긴급 — 스택이 스스로 보낸다. 웹은 넣지 않는다.
    auto_request_accepted(state)
    assert used_map(client)[AUTO_ORDER[0]] is True, "자동 요청이 수락되면 그 주문도 쓴 것이다"
    assert client.get("/api/snapshot").json()["trip"] is not None
    trip_finishes(state)

    # 2. 1인 — 1 의 트립이 끝난 뒤에만 들어간다.
    assert send_single(client).status_code == 200
    trip_finishes(state, stamp=30.0)

    # 3. 묶음 — 두 보충이 다 끝나고 재개된 뒤에만 들어간다.
    for item in (AMOX, IBU):
        cycle = refill_cycle(state, item, start=40.0)
        next(cycle)                       # 보충 중
        assert code_of(send_batch(client)) == "refill_in_progress"
        next(cycle)                       # REFILL_DONE, 아직 PAUSED
        assert code_of(send_batch(client)) == "refill_in_progress"
        next(cycle, None)                 # DISPENSER_RESUMED
    assert send_batch(client).status_code == 200, "두 보충이 끝나면 묶음이 들어간다"
    trip_finishes(state, stamp=80.0)

    # 4. 리셋 → 다시 자동 긴급.
    reset(state)
    assert used_map(client)[AUTO_ORDER[0]] is False, "RESET_DONE 이 사용 표를 비운다"
    auto_request_accepted(state, stamp=101.0, request_id="r002-0001", epoch=2)
    assert used_map(client)[AUTO_ORDER[0]] is True


# ── 1. 자동 요청 ──────────────────────────────────────────────────────────

def test_the_auto_request_marks_its_order_used_without_the_web(demo):
    """웹을 거치지 않은 요청도 사용 표에 들어간다 — `REQUEST_ACCEPTED` 하나로 안다."""
    client, state = demo
    assert used_map(client)[AUTO_ORDER[0]] is False
    auto_request_accepted(state)
    assert used_map(client)[AUTO_ORDER[0]] is True


def test_sending_the_auto_order_from_the_web_is_refused(demo):
    """실물 관측: 리셋 뒤 웹 `ord-0002` 가 409 로 거부됐다(9/20 L3-1 1회차)."""
    client, state = demo
    auto_request_accepted(state)
    trip_finishes(state)
    r = send(client, request_id="web-0009", mode=1,
             destination_id="bed_a2", orders=[AUTO_ORDER])
    assert r.status_code == 409
    assert code_of(r) == "unknown_or_used_order"


def test_the_web_single_waits_for_the_auto_trip_to_finish(demo):
    """대본 2 의 "넣기 전에 볼 것" — 1 의 트립이 끝났다(`DOCKED`)."""
    client, state = demo
    auto_request_accepted(state)
    assert code_of(send_single(client)) == "trip_in_progress"
    trip_finishes(state)
    assert send_single(client).status_code == 200


# ── 2·3. 보충과 묶음 ──────────────────────────────────────────────────────

def test_the_batch_is_refused_while_either_item_refills(demo):
    """묶음은 두 약품을 다 쓴다. 하나라도 보충 중이면 막힌다(runbook 3절)."""
    client, state = demo
    for item in (AMOX, IBU):
        stock(state, **{_slot_kw(item): 0}, paused=[item])
        r = send_batch(client)
        assert r.status_code == 409
        assert code_of(r) == "refill_in_progress"
        assert item in r.json()["error"]["message"], "어느 약품을 기다려야 하는지 말해야 한다"


def test_the_batch_goes_through_after_both_refills_resume(demo):
    client, state = demo
    for item in (AMOX, IBU):
        for _ in refill_cycle(state, item):
            pass
    assert send_batch(client).status_code == 200


def test_single_and_urgent_take_exactly_one_order(demo):
    """실습8 의 묶음 409 두 번은 주문 3건을 mode 0 으로 보낸 요청 실수였다."""
    client, _ = demo
    for mode in (0, 1):
        r = send(client, request_id=f"web-100{mode}", mode=mode,
                 destination_id="bed_a1", orders=list(BATCH_ORDERS))
        assert r.status_code == 400
        assert code_of(r) == "bad_mode_for_orders"


# ── 4. 리셋 ───────────────────────────────────────────────────────────────

def test_reset_frees_the_order_but_the_auto_request_takes_it_again(demo):
    """리셋 뒤 `ord-0002` 가 **언제** 다시 409 가 되는가.

    `RESET_DONE` 직후는 아니다. 그 시점에는 사용 표가 비어 있어 웹으로 넣을 수 있다.
    409 가 되는 것은 자동 요청이 `reset_settle_s`(3.5 s) 뒤에 나가 수락된 다음이다.
    발표자가 이 사이에 넣으면 대본 1 의 주문을 웹이 먼저 가져가 버린다.
    """
    client, state = demo
    auto_request_accepted(state)
    trip_finishes(state)
    assert code_of(send(client, request_id="web-0009", mode=1,
                        destination_id="bed_a2", orders=[AUTO_ORDER])) == "unknown_or_used_order"

    reset(state)
    assert used_map(client)[AUTO_ORDER[0]] is False, "RESET_DONE 이 사용 표를 비운다"

    auto_request_accepted(state, stamp=101.0, request_id="r002-0001", epoch=2)
    r = send(client, request_id="web-0010", mode=1,
             destination_id="bed_a2", orders=[AUTO_ORDER])
    assert r.status_code == 409
    assert code_of(r) == "unknown_or_used_order"


def test_reset_clears_the_request_id_table_too(demo):
    """같은 `request_id` 를 리셋 뒤에 다시 쓸 수 있다 — 두 표를 함께 비우기 때문이다."""
    client, state = demo
    auto_request_accepted(state)
    trip_finishes(state)
    assert send_single(client, request_id="web-0001").status_code == 200
    assert code_of(send_single(client, request_id="web-0001")) == "duplicate_request_id"

    reset(state)
    trip_finishes(state, stamp=110.0, epoch=2)
    assert send_single(client, request_id="web-0001").status_code == 200


# ── 발표자가 보는 신호 ────────────────────────────────────────────────────

def test_snapshot_paused_and_refilling_track_the_presenter_signals(demo):
    """runbook 3절 "볼 신호" 가 snapshot 의 어느 값인지 못 박는다.

    `PAUSED` 는 `dispenser.paused`, `보충 중` 은 `dispenser.refilling` 이다. 둘은 같이 켜지지만
    **같이 꺼지지 않는다** — `REFILL_DONE` 이 `DISPENSER_RESUMED` 보다 먼저 오기 때문이다.
    그래서 runbook 은 `PAUSED` 가 사라진 것을 기준으로 보라고 적는다. 이 시험이 그 순서를 지킨다.
    """
    client, state = demo

    def dispenser():
        return client.get("/api/snapshot").json()["dispenser"]

    assert dispenser()["paused"] is False
    assert dispenser()["refilling"] is False

    cycle = refill_cycle(state, AMOX, start=20.0)
    next(cycle)
    assert dispenser()["paused"] is True
    assert dispenser()["refilling"] is True
    assert dispenser()["refilling_item_ids"] == [AMOX]

    next(cycle)
    assert dispenser()["refilling"] is False, "REFILL_DONE 으로 `보충 중` 이 먼저 꺼진다"
    assert dispenser()["paused"] is True, "그래도 PAUSED 는 아직 켜져 있다"

    next(cycle, None)
    assert dispenser()["paused"] is False, "DISPENSER_RESUMED 뒤에야 PAUSED 가 꺼진다"
    assert dispenser()["refilling"] is False


def test_the_presenter_can_tell_which_orders_are_still_free(demo):
    """웹 화면의 주문 목록이 대본대로 줄어드는지 본다."""
    client, state = demo
    assert sorted(o for o, used in used_map(client).items() if not used) == \
        ["ord-0001", "ord-0002", "ord-0003", "ord-0004"]

    auto_request_accepted(state)
    trip_finishes(state)
    assert sorted(o for o, used in used_map(client).items() if not used) == \
        ["ord-0001", "ord-0003", "ord-0004"], "자동 요청 뒤 웹에 3건이 남는다"

    send_single(client)
    trip_finishes(state, stamp=30.0)
    assert sorted(o for o, used in used_map(client).items() if not used) == \
        ["ord-0003", "ord-0004"], "1인 뒤 묶음에 쓸 2건이 남는다"
