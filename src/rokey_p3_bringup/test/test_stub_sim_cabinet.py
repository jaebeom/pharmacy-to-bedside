"""L2. `/evaluator/cabinet` 의 작성자는 하나다(계약 2.1절·8절).

지금은 `stub_sim` 하나가 낸다. K5 에서 Isaac 이 보관함 참값을 내기 시작하면 둘이 되므로
`publish_cabinet:=false` 로 스텁 쪽만 끈다. `publish_clock`·`publish_belt` 와 같은 모양이다.

run 기록의 SUCCESS 는 이 토픽 하나가 근거라(계약 8절), 끄면 그 회차는 관측이 없다.
그래서 **기본값은 켬**이고, Isaac 쪽 작성자가 실제로 낼 때만 끈다.
"""

import rclpy
from rclpy.parameter import Parameter

from rokey_p3_bringup.stubs.stub_sim import StubSim

CABINET = '/evaluator/cabinet'


def publishers_of(node):
    return {topic for topic, _types in
            node.get_publisher_names_and_types_by_node(node.get_name(), node.get_namespace())}


def make(**values):
    overrides = [Parameter(name, value=value) for name, value in values.items()]
    return StubSim(parameter_overrides=overrides)


def test_stub_sim_publishes_the_cabinet_observation_by_default():
    rclpy.init()
    node = None
    try:
        node = make()
        assert CABINET in publishers_of(node)
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()


def test_publish_cabinet_false_leaves_the_topic_to_isaac():
    rclpy.init()
    node = None
    try:
        node = make(publish_cabinet=False)
        assert CABINET not in publishers_of(node)
        # 상태는 그대로 둔다. 관측을 내지 않을 뿐이라 내부 사전은 비지 않는다.
        node._cabinet['ord-0001'] = 'bed_a1/cabinet'
        node._emit_cabinet('ord-0001', 'bed_a1/cabinet')      # 내지 않지만 죽지도 않는다
        assert node._cabinet == {'ord-0001': 'bed_a1/cabinet'}
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()
