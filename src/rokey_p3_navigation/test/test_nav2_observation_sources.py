"""L1. 코스트맵 장애물 층이 **실제로 내는 스캔**을 듣는지. ROS 를 띄우지 않는다.

9/23 회차18(마클1, master01)에서 잡힌 자리다. 지역 코스트맵이 매 주기 오는데 끝까지 비어 있었고,
그래서 `speed_governor` 의 여유가 늘 `모름` 이었다. 원인은 관측원 토픽 이름이었다.

    ros2 node info /amr_1/local_costmap/local_costmap
      Subscribers: /amr_1/local_costmap/scan   ← 듣는 곳
    ros2 topic info /amr_1/scan
      Publisher 1 (Isaac), Subscription 0      ← 내는 곳

`Costmap2DROS` 는 `/amr_1/local_costmap` 네임스페이스의 노드라 상대 이름 `scan` 이 한 단계 더 들어간다.
**조용히 비어 있는다** — 구독은 붙고 오류도 경고도 없고 코스트맵도 정상으로 온다. 그래서 시험으로 묶는다.

yaml 에는 `<robot_namespace>/scan` 이 적혀 있고 `nav2.launch.py` 가 `/<namespace>` 로 바꾼다
(nav2_common `ReplaceString`). 절대 이름을 박으면 `--namespace amr_2` 가 죽는다. 그래서 이 시험은
**치환한 뒤의** 값을 본다 — 날것 그대로를 보면 실제로 나가는 이름을 못 본다.
"""
from pathlib import Path

import yaml

CONFIG = Path(__file__).resolve().parents[1] / "config" / "nav2_params.yaml"
RAW = CONFIG.read_text(encoding="utf-8")
PLACEHOLDER = "<robot_namespace>"
COSTMAPS = ("local_costmap", "global_costmap")


def params(namespace="amr_1"):
    """`nav2.launch.py` 의 ReplaceString 과 같은 치환을 하고 읽는다."""
    return yaml.safe_load(RAW.replace(PLACEHOLDER, f"/{namespace}"))


def costmap(name, namespace="amr_1"):
    return params(namespace)[name][name]["ros__parameters"]


def test_every_observation_source_names_an_absolute_topic():
    """상대 이름은 코스트맵 노드 네임스페이스 아래로 풀려 아무도 안 내는 토픽이 된다."""
    for name in COSTMAPS:
        layer = costmap(name)["obstacle_layer"]
        for source in layer["observation_sources"].split():
            topic = layer[source]["topic"]
            assert topic.startswith("/"), f"{name}.{source}.topic 이 상대 이름이다: {topic!r}"


def test_the_scan_source_matches_the_lidar_topic():
    """라이다(`p3sim/amr_base.add_lidar`)가 내는 이름과 같아야 한다. 다르면 장애물 층이 눈을 감는다."""
    for name in COSTMAPS:
        assert costmap(name)["obstacle_layer"]["scan"]["topic"] == "/amr_1/scan"


def test_the_topic_follows_the_namespace_argument():
    """`--namespace amr_2` 로 띄우면 amr_2 의 라이다를 들어야 한다. 절대 이름을 박으면 죽는 자리다."""
    for namespace in ("amr_1", "amr_2", "amr_4"):
        for name in COSTMAPS:
            assert costmap(name, namespace)["obstacle_layer"]["scan"]["topic"] == f"/{namespace}/scan"


def test_the_placeholder_is_the_one_the_launch_replaces():
    """yaml 과 launch 가 같은 글자를 써야 한다. 다르면 치환이 조용히 안 일어난다."""
    launch = (CONFIG.resolve().parents[1] / "launch" / "nav2.launch.py").read_text(encoding="utf-8")
    assert PLACEHOLDER in RAW
    assert f"'{PLACEHOLDER}'" in launch
    assert PLACEHOLDER not in yaml.dump(params())     # 치환 뒤에는 남아 있으면 안 된다


def test_the_costmaps_still_watch_the_same_robot():
    """토픽을 절대 이름으로 박았으니 프레임도 같은 로봇이어야 앞뒤가 맞는다."""
    for name in COSTMAPS:
        assert costmap(name)["robot_base_frame"] == "amr_1/base_link"
