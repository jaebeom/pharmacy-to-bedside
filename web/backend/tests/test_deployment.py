"""snapshot.deployment — 한 대인가 두 PC 인가(api.md §1.10, 카드 ⑤). ROS 없이 돈다."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import build_parser, create_app, deployment_info


def test_one_pc_is_the_default():
    snap = TestClient(create_app(mock=True, autostart=False)).get("/api/snapshot").json()
    assert snap["deployment"] == {"multi_pc": False, "roles": None, "peer": None, "domain_id": None}
    assert snap["mode"] == "mock"                   # mode 의 뜻·형은 그대로다


def test_two_pcs_show_roles_peer_and_domain():
    info = deployment_info(["arm", "nav", "stack", "web"], " 10.10.0.1 ", "131")
    assert info == {"multi_pc": True, "roles": ["arm", "nav", "stack", "web"], "peer": "10.10.0.1",
                    "domain_id": 131}
    assert deployment_info(None, "", "abc") == {"multi_pc": False, "roles": None, "peer": None, "domain_id": None}


def test_the_flags_reach_the_snapshot():
    args = build_parser().parse_args(["--mock", "--roles", "arm nav stack web", "--peer", "10.10.0.1"])
    app = create_app(mock=True, autostart=False, roles=args.roles.split(), peer=args.peer)
    dep = TestClient(app).get("/api/snapshot").json()["deployment"]
    assert (dep["multi_pc"], dep["roles"], dep["peer"]) == (True, ["arm", "nav", "stack", "web"], "10.10.0.1")
