import importlib.util
import pathlib

import pytest

LAUNCH = pathlib.Path(__file__).resolve().parents[1] / 'launch'


def load_module(name):
    spec = importlib.util.spec_from_file_location(name.replace('.', '_'), LAUNCH / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load(name):
    return load_module(name).generate_launch_description()


def test_skeleton_launch_lists_four_nodes():
    launch_ros = pytest.importorskip('launch_ros')
    description = load('skeleton.launch.py')
    nodes = [e for e in description.entities if isinstance(e, launch_ros.actions.Node)]
    assert len(nodes) == 4


# stub_loop.launch.py 의 인자 전부와 기본값. 인자를 더하거나 기본값을 바꾸면 여기와 README 인자 표를 같이 고친다.
STUB_LOOP_ARGUMENTS = {
    'use_stub_arm': 'true',
    'use_stub_fleet': 'true',
    'use_stub_sim': 'true',
    'use_stub_detector': 'true',
    'use_stub_m0609': 'true',
    'max_requests': '1',
    'use_order_generator': 'true',
    'log_dir': '',
    'publish_clock': 'true',
    'run_host': '',
    'emulate_m0609': 'true',
    'pharmacy_only': 'false',
    'dispenser_file': '',
    'order_pool_file': '',
    'zones_file': '',
    'publish_cabinet': 'true',
    'use_ur5_arm': 'false',
    'ur5_arm_params_file': '',
    'deck_slots': '5',
    'observation_guard': 'false',
    'dispense_while_dispatching': 'false',
    'use_isaac_adapter': 'false',
    'pick_notice': 'true',
    'belt_observation': 'false',
    'belt_timeout_s': '20.0',
    'sim_pouches': 'false',
    'sim_tag_reads': 'false',
    'sim_cabinet': 'false',
    'pouch_source': 'camera',
    'scan_tag_source': 'camera',
    'deck_pick_from_frame': 'false',
    'gripper_command_seq': 'false',
    'use_pouch_detector': 'false',
    'use_m0609_detector': 'false',
    'vision_check': 'false',
    'detector_max_rate_hz': '0.0',
    'detector_save_reads_dir': '',
    'm0609_save_reads_dir': '',
    'pharmacy_db': 'false',
    'dispense_timeout_s': '2.0',
    'belt_view_frame': 'pharmacy/belt_end',
    'belt_view_standoff_m': '0.0',
    'belt_view_offset_m': '0.0',
    'detector_pouch_width_m': '0.0',
    'detector_pouch_distance_m': '0.0',
}


def test_stub_loop_launch_declares_every_argument_with_its_default():
    pytest.importorskip('launch_ros')
    launch = pytest.importorskip('launch')
    description = load('stub_loop.launch.py')
    context = launch.LaunchContext()
    declared = {e.name: launch.utilities.perform_substitutions(context, e.default_value)
                for e in description.entities
                if isinstance(e, launch.actions.DeclareLaunchArgument)}
    assert declared == STUB_LOOP_ARGUMENTS


def test_stub_loop_launch_runs_the_three_orchestration_nodes_four_stubs_and_the_isaac_adapter():
    launch_ros = pytest.importorskip('launch_ros')
    description = load('stub_loop.launch.py')
    nodes = [e for e in description.entities if isinstance(e, launch_ros.actions.Node)]
    # 오케스트레이션 셋, 스텁 넷, use_isaac_adapter 로 켜는 isaac_adapter 하나,
    # use_ur5_arm 으로 켜는 실물 UR5 팔 하나, use_pouch_detector 로 켜는 실물 pouch_detector 하나,
    # use_m0609_detector 로 켜는 M0609 손 카메라 QR 판독 하나
    assert len(nodes) == 11


@pytest.mark.parametrize('overrides,warns', [
    ({}, False),
    ({'use_isaac_adapter': 'true'}, True),
    ({'use_isaac_adapter': 'true', 'publish_clock': 'false'}, True),
    ({'use_isaac_adapter': 'true', 'publish_clock': 'false', 'emulate_m0609': 'false'}, False),
    ({'publish_clock': 'true', 'emulate_m0609': 'true'}, False),
])
def test_stub_loop_warns_when_the_isaac_adapter_runs_with_stub_clock_or_m0609(overrides, warns):
    """/clock·/m0609/* 작성자가 둘이 될 수 있는 조합에만 경고한다. 자동으로 끄지는 않는다."""
    pytest.importorskip('launch_ros')
    launch = pytest.importorskip('launch')
    description = load('stub_loop.launch.py')
    context = launch.LaunchContext()
    context.launch_configurations.update({**STUB_LOOP_ARGUMENTS, **overrides})
    logs = [e for e in description.entities if isinstance(e, launch.actions.LogInfo)]
    assert len(logs) == 1
    assert logs[0].condition.evaluate(context) is warns


# -- 실물 UR5 팔 묶음(카드 K4) ---------------------------------------------------------

#: 어긋남이 없는 묶음. 셋 중 하나만 빠져도 기동 전에 멈춘다.
UR5_BUNDLE = {'use_ur5_arm': 'true', 'use_stub_arm': 'false', 'pick_notice': 'false',
              'ur5_arm_params_file': '/m/ur5_arm.yaml'}


def test_the_order_generator_can_be_turned_off():
    """`max_requests:=0` 은 "끔" 이 아니라 "주문 풀 전부" 다. 끄는 인자가 따로 있어야 한다.

    9/21 실습29: 빈월드 회차에서 자동 트립이 먼저 떠 사람이 넣은 요청이 409 `trip_in_progress` 였다.
    그 자동 주문은 `bed_a2` 로 가는데 팔의 `cabinet_frame` 은 `bed_a1` 하나로 고정이라 서로 부딪힌다.
    """
    launch_ros = pytest.importorskip('launch_ros')
    launch = pytest.importorskip('launch')
    description = load('stub_loop.launch.py')
    nodes = [e for e in description.entities if isinstance(e, launch_ros.actions.Node)]
    context = launch.LaunchContext()
    context.launch_configurations.update(STUB_LOOP_ARGUMENTS)
    on = sum(1 for node in nodes if node.condition is None or node.condition.evaluate(context))
    context.launch_configurations.update({'use_order_generator': 'false'})
    off = sum(1 for node in nodes if node.condition is None or node.condition.evaluate(context))
    assert off == on - 1


@pytest.mark.parametrize('overrides,broken', [
    ({}, False),                                                        # 기본값(꺼짐)에서는 보지 않는다
    ({'use_stub_arm': 'false', 'pick_notice': 'false'}, False),         # 켜지 않았으면 그대로 둔다
    (UR5_BUNDLE, False),
    ({**UR5_BUNDLE, 'use_stub_arm': 'true'}, True),                     # 서버가 둘이 된다
    ({**UR5_BUNDLE, 'pick_notice': 'true'}, True),                      # Isaac 이 먼저 치운다
    ({**UR5_BUNDLE, 'use_stub_arm': '1'}, True),                        # IfCondition 이 참으로 보는 값은 다 본다
    ({**UR5_BUNDLE, 'ur5_arm_params_file': ''}, True),                  # 현장값 없이 띄우지 않는다
    ({**UR5_BUNDLE, 'ur5_arm_params_file': '  '}, True),
    # Isaac 이 gripper/holding 을 내는데 stub_sim 도 낸다 — 작성자 둘(#444 F02)
    ({**UR5_BUNDLE, 'use_isaac_adapter': 'true', 'use_stub_sim': 'true'}, True),
    ({**UR5_BUNDLE, 'use_isaac_adapter': 'true', 'use_stub_sim': 'false'}, False),
    ({**UR5_BUNDLE, 'use_isaac_adapter': 'false', 'use_stub_sim': 'true'}, False),   # 스텁만 쓰는 구성
])
def test_stub_loop_names_a_broken_ur5_arm_bundle(overrides, broken):
    """어긋난 인자를 사유에 그대로 적는다. 경고가 아니라 거부다."""
    pytest.importorskip('launch_ros')
    module = load_module('stub_loop.launch.py')
    problem = module.ur5_arm_problem({**STUB_LOOP_ARGUMENTS, **overrides})
    assert (problem is not None) is broken
    if broken:
        assert 'use_ur5_arm:=true' in problem


#: 시뮬 센서 묶음이 맞는 조합.
SIM_BUNDLE = {'sim_pouches': 'true', 'sim_tag_reads': 'true',
              'pouch_source': 'sim', 'scan_tag_source': 'sim'}


@pytest.mark.parametrize('overrides,broken', [
    ({}, False),                                                  # 기본값은 둘 다 camera 다
    (SIM_BUNDLE, False),
    ({'sim_pouches': 'true', 'sim_tag_reads': 'true'}, False),     # 어댑터만 켜는 것은 경고 거리다
    ({**SIM_BUNDLE, 'sim_pouches': 'false'}, True),                # 봉투를 아무도 안 낸다
    ({**SIM_BUNDLE, 'sim_tag_reads': 'false'}, True),
    ({'pouch_source': 'sim'}, True),
    ({**SIM_BUNDLE, 'deck_pick_from_frame': 'true'}, True),        # 둘 중 하나만
    ({'deck_pick_from_frame': 'true'}, False),                     # camera 와는 같이 켤 수 있다
    # 보관함 관측의 작성자가 둘이면 run 기록의 SUCCESS 근거가 갈린다
    ({'sim_cabinet': 'true', 'publish_cabinet': 'true'}, True),
    ({'sim_cabinet': 'true', 'publish_cabinet': 'false'}, False),
])
def test_stub_loop_names_a_broken_sim_sensor_bundle(overrides, broken):
    pytest.importorskip('launch_ros')
    module = load_module('stub_loop.launch.py')
    problem = module.sim_sensor_problem({**STUB_LOOP_ARGUMENTS, **overrides})
    assert (problem is not None) is broken


def test_stub_loop_stops_before_any_node_when_the_ur5_arm_bundle_is_broken():
    launch_ros = pytest.importorskip('launch_ros')
    launch = pytest.importorskip('launch')
    module = load_module('stub_loop.launch.py')
    description = module.generate_launch_description()
    entities = description.entities
    checks = [e for e in entities if isinstance(e, launch.actions.OpaqueFunction)]
    assert len(checks) == 1
    # 노드보다 앞에 있어야 아무것도 뜨지 않은 채로 멈춘다.
    first_node = min(i for i, e in enumerate(entities) if isinstance(e, launch_ros.actions.Node))
    assert entities.index(checks[0]) < first_node

    context = launch.LaunchContext()
    context.launch_configurations.update({**STUB_LOOP_ARGUMENTS, 'use_ur5_arm': 'true'})
    with pytest.raises(RuntimeError, match='use_ur5_arm'):
        checks[0].execute(context)

    context.launch_configurations.update(UR5_BUNDLE)
    assert checks[0].execute(context) == []

    # 같은 검사가 시뮬 센서 묶음도 본다.
    context.launch_configurations.update({**UR5_BUNDLE, 'pouch_source': 'sim'})
    with pytest.raises(RuntimeError, match='sim_pouches'):
        checks[0].execute(context)


def _enabled_nodes(description, context, launch_ros):
    return {index for index, entity in enumerate(description.entities)
            if isinstance(entity, launch_ros.actions.Node)
            and (entity.condition is None or entity.condition.evaluate(context))}


def test_stub_loop_ur5_arm_replaces_the_stub_arm_and_is_off_by_default():
    launch_ros = pytest.importorskip('launch_ros')
    launch = pytest.importorskip('launch')
    description = load('stub_loop.launch.py')

    default_context = launch.LaunchContext()
    default_context.launch_configurations.update(STUB_LOOP_ARGUMENTS)
    default = _enabled_nodes(description, default_context, launch_ros)
    assert len(default) == 7     # 오케스트레이션 셋 + 스텁 넷. isaac_adapter·UR5 팔은 꺼져 있다

    bundle_context = launch.LaunchContext()
    bundle_context.launch_configurations.update({**STUB_LOOP_ARGUMENTS, **UR5_BUNDLE})
    bundle = _enabled_nodes(description, bundle_context, launch_ros)
    assert len(bundle - default) == 1, 'UR5 팔 노드 하나가 더 떠야 한다'
    assert len(default - bundle) == 1, '스텁 팔 하나가 빠져야 한다'


@pytest.mark.parametrize(('overrides', 'broken'), [
    ({}, False),
    ({'use_pouch_detector': 'true'}, True),                                   # 스텁도 기본으로 켜져 있다
    ({'use_pouch_detector': 'true', 'use_stub_detector': 'false'}, False),
    ({'use_stub_detector': 'false'}, False),
])
def test_stub_loop_refuses_two_hand_camera_writers(overrides, broken):
    pytest.importorskip('launch_ros')
    module = load_module('stub_loop.launch.py')
    problem = module.detector_problem({**STUB_LOOP_ARGUMENTS, **overrides})
    assert (problem is not None) is broken
