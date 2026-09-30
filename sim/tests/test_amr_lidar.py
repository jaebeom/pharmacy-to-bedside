"""AMR 합본 라이다(Nav2 트랙, 9/23)가 Nav2 설정과 같은 이름·자리인가. Isaac·ROS 없이 돈다.

`add_lidar` 자체는 Isaac 이 있어야 돈다(L3 미실행). 여기서는 **말로 맞춘 값**을 코드끼리 맞댄다(#435):
토픽·프레임 이름은 nav2_params.yaml 이 읽는 것과 같아야 하고, 라이다는 상·하판 사이·지도 높이 띠 안에 있어야 한다.
"""
import importlib.util
import re
import sys
import unittest
from pathlib import Path

STANDALONE = Path(__file__).resolve().parents[1] / "standalone"
REPO = STANDALONE.parents[1]
sys.path.insert(0, str(STANDALONE))
from p3sim import amr_base  # noqa: E402

NAV2 = (REPO / "src" / "rokey_p3_navigation" / "config" / "nav2_params.yaml").read_text(encoding="utf-8")
MAP_YAML = (REPO / "src" / "rokey_p3_navigation" / "config" / "maps" / "hospital.yaml").read_text(encoding="utf-8")


def _stage():
    spec = importlib.util.spec_from_file_location("pharmacy_stage_lidar", STANDALONE / "pharmacy_stage.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


NAMESPACE = "/amr_1"


def resolve(topic, node_namespace):
    """ROS 가 푸는 것처럼 이름을 푼다. `<robot_namespace>` 는 nav2.launch.py 의 ReplaceString 이 바꾼다."""
    topic = topic.replace("<robot_namespace>", NAMESPACE)
    return topic if topic.startswith("/") else f"{node_namespace.rstrip('/')}/{topic}"


class LidarMatchesNav2(unittest.TestCase):
    def test_topic_is_what_amcl_and_the_costmaps_read(self):
        """이름을 **푼 뒤** 비교한다.

        예전에는 날것끼리 비교했다: 라이다 `scan` == 코스트맵 `scan`. 그 같음이 버그였다 — 코스트맵은
        `/amr_1/local_costmap` 네임스페이스의 노드라 `scan` 이 `/amr_1/local_costmap/scan` 으로 풀려 아무도 안
        내는 토픽을 들었다(9/23 회차18: `/amr_1/scan` Subscription 0, #620). 이 시험이 그 버그를 굳혀 두고 있었다.
        """
        lidar = resolve(amr_base.LIDAR_TOPIC, NAMESPACE)            # add_lidar 는 /<ns>/scan 으로 낸다
        self.assertEqual("/amr_1/scan", lidar)
        # amcl 은 /amr_1 에 바로 뜨는 노드라 상대 이름이 맞게 풀린다(병원 회차에는 AMCL 이 없다).
        amcl = re.search(r"^\s+scan_topic:\s*(\S+)", NAV2, re.M).group(1)
        self.assertEqual(lidar, resolve(amcl, NAMESPACE))
        topics = re.findall(r"^\s+topic:\s*(\S+)", NAV2, re.M)
        self.assertTrue(topics)
        for costmap, topic in zip(("local_costmap", "global_costmap"), topics, strict=True):
            self.assertEqual(lidar, resolve(topic, f"{NAMESPACE}/{costmap}"),
                             f"{costmap} 관측 토픽이 풀고 나면 라이다 토픽과 다르다: {topic!r}")

    def test_frame_sits_under_the_namespace_like_base_link(self):
        self.assertIn('base_frame_id: "amr_1/base_link"', NAV2)
        self.assertEqual("lidar_link", amr_base.LIDAR_FRAME)

    def test_mount_is_between_chassis_panels(self):
        x, y, z = amr_base.LIDAR_MOUNT_LOCAL
        self.assertEqual((0.43, 0.0, 0.25), (x, y, z))
        self.assertLess(x, 0.9325 / 2, "라이다가 차체 앞끝 밖으로 나갔다")
        self.assertLess(z, amr_base.ASSET_BASE_TOP_Z, "윗면 위면 트레이·받침에 가린다")

    def test_only_visual_chassis_mesh_is_masked(self):
        self.assertEqual("base_link/visuals/mesh_0", amr_base.LIDAR_OCCLUDING_VISUAL)
        self.assertEqual("base_link/collisions/mesh_0", amr_base.LIDAR_CHASSIS_COLLISION)
        self.assertNotEqual(amr_base.LIDAR_OCCLUDING_VISUAL, amr_base.LIDAR_CHASSIS_COLLISION)

    def test_local_costmap_uses_2d_scan_without_static_layer(self):
        local = NAV2.split("local_costmap:", 1)[1].split("global_costmap:", 1)[0]
        self.assertIn('plugins: ["obstacle_layer", "inflation_layer"]', local)
        self.assertIn('data_type: "LaserScan"', local)
        self.assertNotIn('plugin: "nav2_costmap_2d::StaticLayer"', local)

    def test_scan_height_is_inside_the_map_band(self):
        band = re.search(r"z_band: \[([\d.]+), ([\d.]+)\]", MAP_YAML)
        self.assertIsNotNone(band)
        scan_z = amr_base.LIDAR_MOUNT_LOCAL[2] + amr_base.asset_lift()
        self.assertTrue(float(band.group(1)) < scan_z < float(band.group(2)), scan_z)

    def test_config_is_the_2d_one(self):
        # LaserScan 은 2D 설정에서만 나온다(Isaac 5.1 tutorial_ros2_rtx_lidar).
        self.assertTrue(amr_base.LIDAR_CONFIG.endswith("_2D"))


class LidarStageWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stage = _stage()
        cls.source = (STANDALONE / "pharmacy_stage.py").read_text(encoding="utf-8")

    def test_needs_the_combined_asset(self):
        args = self.stage.parse_args(["--amr-lidar"])
        self.assertIn("--amr-lidar needs --amr --amr-combined", " ".join(self.stage.validate(args)))

    def test_off_by_default(self):
        self.assertFalse(self.stage.parse_args([]).amr_lidar)

    def test_the_lidar_frame_goes_out_with_the_robot_tf(self):
        self.assertIn("extra_static=(amr_lidar_path,) if amr_lidar_path else ()", self.source)

    def test_debug_draw_is_off_by_default_and_needs_the_lidar(self):
        """`--lidar-debug`(촬영용, 재범 9/25): 기본 끔, 라이다 없이 주면 기동 전에 멈춘다."""
        self.assertFalse(self.stage.parse_args([]).lidar_debug)
        args = self.stage.parse_args(["--lidar-debug"])
        self.assertIn("--lidar-debug 는 --amr-lidar 와 같이 준다", " ".join(self.stage.validate(args)))

    def test_debug_draw_failure_does_not_stop_the_lidar(self):
        self.assertIn("WARN amr lidar debug draw disabled", self.source)
        self.assertEqual(amr_base.LIDAR_DEBUG_WRITERS[0], "RtxLidarDebugDrawPointCloudBuffer")


if __name__ == "__main__":
    unittest.main()
