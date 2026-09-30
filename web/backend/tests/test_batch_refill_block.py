"""보충 중에 묶음(batch_room)을 넣으면 웹이 어디서 막는지 — 현행 동작 고정.

9/21 시연 대본은 1인 뒤에 묶음을 넣는다. 그 사이에 보충이 돌 수 있다(runbook 3절).
`unavailable_items` 는 `paused_item_ids` 와 슬롯 수량을 본다(`app/alarms.py`).
요청에 `item_id` 가 없으면 서버가 주문 풀에서 채운 값으로 검사한다.
제품 코드는 바꾸지 않는다.
"""

from app.main import create_app
from fastapi.testclient import TestClient

T0 = 0.0
BATCH = [{"order_id": "ord-0001", "patient_id": "1001", "item_id": "drug-amox"},
         {"order_id": "ord-0003", "patient_id": "1003", "item_id": "drug-amox"}]


def make_client():
    app = create_app(mock=True, autostart=False, allow_commands=True)
    return TestClient(app), app.state.world


def dispenser(state, slots, paused=()):
    state.note_dispenser({"paused_item_ids": list(paused), "queue_length": 0,
                          "belt_occupied": False, "stamp": 0.0,
                          "slots": [{"item_id": item, "slot": index, "lot_id": "", "expiry": "",
                                     "count": count, "active": True}
                                    for index, (item, count) in enumerate(slots)]}, T0)


def batch(orders=None):
    return {"request_id": "web-0001", "mode": 2, "destination_id": "bed_a1",
            "orders": BATCH if orders is None else orders}


def test_a_batch_is_refused_when_one_of_its_items_is_refilling():
    """묶음의 한 품목이라도 보충 중이면 409 다. 어느 품목·주문인지 응답에 들어간다."""
    client, state = make_client()
    with client:
        dispenser(state, [("drug-amox", 0), ("drug-ibu", 5)], paused=["drug-amox"])
        response = client.post("/api/requests", json=batch())
        assert response.status_code == 409
        error = response.json()["error"]
        assert error["code"] == "refill_in_progress"
        assert error["detail"]["item_id"] == "drug-amox"
        assert error["detail"]["order_id"] == "ord-0001"


def test_the_refused_item_is_the_first_blocked_order_in_the_batch():
    """앞 주문이 멀쩡해도 뒤 주문의 품목이 막혀 있으면 그 주문 이름으로 거부한다."""
    client, state = make_client()
    with client:
        dispenser(state, [("drug-amox", 5), ("drug-ibu", 0)], paused=["drug-ibu"])
        mixed = [{"order_id": "ord-0001", "patient_id": "1001", "item_id": "drug-amox"},
                 {"order_id": "ord-0004", "patient_id": "1004", "item_id": "drug-ibu"}]
        error = client.post("/api/requests", json=batch(mixed)).json()["error"]
        assert error["code"] == "refill_in_progress"
        assert error["detail"] == {"item_id": "drug-ibu", "order_id": "ord-0004"}


def test_a_batch_passes_once_both_items_have_stock():
    """보충이 끝나 재고가 있으면 같은 묶음이 통과한다(대본의 '재개 뒤 다시')."""
    client, state = make_client()
    with client:
        dispenser(state, [("drug-amox", 5), ("drug-ibu", 5)])
        assert client.post("/api/requests", json=batch()).status_code == 200


def test_an_order_without_item_id_is_still_checked_from_the_pool():
    """요청에 `item_id` 가 없어도 검사는 돈다. 서버가 주문 풀에서 품목을 채우기 때문이다.

    `POST /api/requests` 는 `order_id` 로 풀을 찾아 `patient_id`·`item_id` 를 채운 뒤
    검사한다(`app/main.py` `post_request`). 그래서 `curl` 로 `order_id` 만 보내도 막힌다.
    풀에 없는 주문은 이 검사 전에 409 `unknown_or_used_order` 로 걸린다.
    """
    client, state = make_client()
    with client:
        dispenser(state, [("drug-amox", 0), ("drug-ibu", 5)], paused=["drug-amox"])
        bare = [{"order_id": "ord-0001", "patient_id": "1001"},
                {"order_id": "ord-0003", "patient_id": "1003"}]
        response = client.post("/api/requests", json=batch(bare))
        assert response.status_code == 409
        error = response.json()["error"]
        assert error["code"] == "refill_in_progress"
        assert error["detail"]["item_id"] == "drug-amox"   # 풀에서 채운 값이다
