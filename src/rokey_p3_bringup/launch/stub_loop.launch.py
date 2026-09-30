"""스텁 한 바퀴. 계약 8절 L2 의 기동 조합이다.

실물이 되는 대로 인자를 하나씩 false 로 바꾼다. 인터페이스 이름은 그대로다.

    ros2 launch rokey_p3_bringup stub_loop.launch.py use_stub_fleet:=false

stub_sim 이 /clock 을 만든다. 그래서 stub_sim 만 use_sim_time 을 쓰지 않고
나머지는 전부 use_sim_time=true 다(계약 4절: /clock 작성자는 하나다).
브릿지가 /clock 을 내면 publish_clock:=false. stub_sim 도 /clock 을 내지 않고 sim time 을 따른다.

    ros2 launch rokey_p3_bringup stub_loop.launch.py publish_clock:=false

마스터에서 띄우면 run_host 로 run ID 의 호스트 칸을 정한다(evidence run ID 는 master01|master02).

    ros2 launch rokey_p3_bringup stub_loop.launch.py run_host:=master02

protocol pharmacy-lap-pilot-v1 조건(조제실 구간, 보충 유도 재고)도 인자로 준다. 파일 인자를 비우면
각 노드가 지금처럼 rokey_p3_orchestrator share 의 config 기본 파일을 읽는다.

    ros2 launch rokey_p3_bringup stub_loop.launch.py pharmacy_only:=true dispenser_file:=/path/dispenser.yaml

Isaac 조제실 스테이지가 JSON 토픽으로 조제기·벨트·리셋을 맡으면 use_isaac_adapter 하나로 바꾼다.
stub_sim 의 /pharmacy/dispense·/sim/reset·/pharmacy/belt 를 끄고 isaac_adapter 를 켠다. 나머지 stub_sim 기능은 그대로다.

    ros2 launch rokey_p3_bringup stub_loop.launch.py use_isaac_adapter:=true

실물 UR5 팔 노드는 `use_ur5_arm` 으로 켠다. 기본은 꺼짐(지금 동작)이다. 스텁 팔·`pick_notice` 와
한 묶음이라 어긋나면 노드를 하나도 띄우지 않고 멈춘다(아래 `ur5_arm_problem`).

    ros2 launch rokey_p3_bringup stub_loop.launch.py use_ur5_arm:=true use_stub_arm:=false \\
        pick_notice:=false ur5_arm_params_file:=/path/ur5_arm.yaml

시뮬 센서(K4·K5)는 sim_pouches·sim_tag_reads 로 켜고, 팔이 그것을 보게 하려면
pouch_source·scan_tag_source 를 sim 으로 준다. 네 인자는 한 묶음이라 어긋나면 멈춘다
(아래 sim_sensor_problem). 그 셋은 launch 가 정본이라 ur5_arm_params_file 보다 우선한다.

카메라 인식(실물 pouch_detector: color 검출 + QR)은 use_pouch_detector 로 켠다. 기본은 꺼짐이다.
같은 계약 토픽(hand_camera/*)을 내는 stub_detector 와 같이 켜면 멈춘다(아래 detector_problem).
거리 인자 둘은 현장값이다. 둘 다 0 이면 검출 자세가 0 이라 팔이 그 검출로 집지 않는다.

    ros2 launch rokey_p3_bringup stub_loop.launch.py use_stub_detector:=false use_pouch_detector:=true \\
        detector_pouch_distance_m:=0.25
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo, OpaqueFunction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, NotSubstitution, PythonExpression
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterFile, ParameterValue

STUBS = ('use_stub_arm', 'use_stub_fleet', 'use_stub_sim', 'use_stub_detector')

#: `use_ur5_arm:=true` 일 때 반드시 꺼져 있어야 하는 인자.
#: - `use_stub_arm`: 스텁 팔이 같이 살면 `PickPouch`·`ScanTag` 서버가 둘이다.
#: - `pick_notice`: 켜 두면 실물 팔이 집기 전에 Isaac 이 봉투를 치운다.
#:   `--ur5` 스테이지는 `pick_notice` 를 받아도 세기만 하고 적용하지 않는다(#244).
UR5_ARM_MUST_BE_OFF = ('use_stub_arm', 'pick_notice')

#: 시뮬 센서 묶음. 팔이 `sim` 을 보는데 어댑터가 그 센서를 안 옮기면 아무도 그 토픽을 내지 않는다.
#: 반대(어댑터만 켜짐)는 남는 토픽이라 해롭지 않아 경고로 끝낸다.
SIM_SOURCE_NEEDS = (('pouch_source', 'sim_pouches'), ('scan_tag_source', 'sim_tag_reads'))


def _is_true(value):
    """launch 인자는 문자열로 온다. 참으로 보는 값은 IfCondition 과 같다('true', '1')."""
    return str(value).strip().lower() in ('true', '1')


def ur5_arm_problem(values):
    """실물 UR5 팔 구성의 인자 묶음이 어긋났으면 사람이 읽을 사유, 맞으면 None.

    `publish_clock`·`emulate_m0609` 처럼 경고로 끝내지 않는다. 어긋난 채로 뜨면 증상이
    "봉투가 두 번 사라진다"·"안 사라진다" 로 한참 뒤에야 나타난다(비전·작전 판단, 카드 K4).
    """
    if not _is_true(values.get('use_ur5_arm')):
        return None
    wrong = [f'{name}:={values.get(name)}' for name in UR5_ARM_MUST_BE_OFF if _is_true(values.get(name))]
    if not str(values.get('ur5_arm_params_file') or '').strip():
        wrong.append('ur5_arm_params_file 이 비어 있다')
    # Isaac 이 /amr_1/gripper/holding 을 내는데 stub_sim 도 조건 없이 10 Hz 로 낸다 — 작성자가 둘이다.
    # 팔은 grasp_settle 뒤 **마지막 값 하나**를 읽어 판정하므로 스텁의 false 가 마지막이면
    # 흡착이 실제로 붙어도 grasp_failed 다(반반). 이송 중 dropped() 도 같은 값을 본다.
    if _is_true(values.get('use_isaac_adapter')) and _is_true(values.get('use_stub_sim')):
        wrong.append('use_stub_sim:=true 인데 Isaac 이 gripper/holding 을 낸다(작성자 둘). '
                     'use_stub_sim:=false 로 준다')
    if not wrong:
        return None
    return ('use_ur5_arm:=true 는 실물 UR5 팔 구성이다. 어긋난 것: ' + ', '.join(wrong) + '. '
            '묶음은 use_ur5_arm:=true · use_stub_arm:=false · pick_notice:=false 에 '
            '현장값 params 파일 하나다. 스테이지도 --ur5 와 stand-in 을 같이 받지 않는다(#244).')


def sim_sensor_problem(values):
    """시뮬 센서 묶음이 어긋났으면 사유, 맞으면 None.

    팔의 `pouch_source`·`scan_tag_source`·`deck_pick_from_frame` 은 **launch 가 정본이다.**
    `ur5_arm_params_file` 에 같은 이름을 적어도 launch 값이 이긴다(묶음을 여기서 판정하기 위해서다).
    """
    wrong = []
    for source, relay in SIM_SOURCE_NEEDS:
        if str(values.get(source) or '').strip() == 'sim' and not _is_true(values.get(relay)):
            wrong.append(f'{source}:=sim 인데 {relay} 가 꺼져 있다(그 토픽을 아무도 내지 않는다)')
    # 보관함 관측의 작성자도 하나여야 한다. 둘이면 run 기록의 SUCCESS 근거가 갈린다(계약 8절).
    if _is_true(values.get('sim_cabinet')) and _is_true(values.get('publish_cabinet')):
        wrong.append('sim_cabinet 과 stub_sim 의 publish_cabinet 이 같이 켜져 있다(작성자 둘). '
                     'publish_cabinet:=false 로 준다')
    if _is_true(values.get('deck_pick_from_frame')) and str(values.get('pouch_source') or '').strip() == 'sim':
        wrong.append('deck_pick_from_frame 와 pouch_source:=sim 은 둘 중 하나만 켠다'
                     '(검출이 칸과 자세를 주므로 프레임 파지는 그 검출을 조용히 무시한다)')
    if not wrong:
        return None
    return '시뮬 센서 묶음이 어긋났다: ' + ', '.join(wrong) + '.'


def detector_problem(values):
    """손 카메라 계약 토픽(`hand_camera/tag_reads`·`pouches`)의 작성자가 둘이면 사유, 아니면 None."""
    if _is_true(values.get('use_pouch_detector')) and _is_true(values.get('use_stub_detector')):
        return ('use_pouch_detector 와 use_stub_detector 가 같이 켜져 있다. 둘 다 hand_camera/tag_reads·pouches 를 '
                '낸다(작성자 둘). 카메라 인식이면 use_stub_detector:=false 로 준다.')
    return None


def _refuse_broken_ur5_arm_bundle(context):
    """노드보다 앞에서 돈다. 묶음이 어긋나면 아무것도 띄우지 않고 멈춘다."""
    for problem in (ur5_arm_problem(context.launch_configurations),
                    sim_sensor_problem(context.launch_configurations),
                    detector_problem(context.launch_configurations)):
        if problem is not None:
            raise RuntimeError(problem)
    return []


def generate_launch_description():
    """오케스트레이션 노드 셋 + 켜져 있는 스텁."""
    arguments = [DeclareLaunchArgument(name, default_value='true') for name in STUBS]
    arguments.append(DeclareLaunchArgument(
        'use_stub_m0609', default_value='true',
        description='stub_arm 이 /m0609/refill 을 맡는다. false 면 실물 m0609_arm 을 따로 띄운다'))
    arguments.append(DeclareLaunchArgument(
        'max_requests', default_value='1',
        description='발행기가 보낼 요청 수. 스텁 한 바퀴는 1건이다. 0 이면 주문 풀 전부'))
    arguments.append(DeclareLaunchArgument(
        'use_order_generator', default_value='true',
        description='자동 주문 발행기를 띄운다. false 면 요청은 웹·curl 로만 들어온다. '
                    '**max_requests:=0 은 "끔" 이 아니라 "주문 풀 전부" 다** — 끄려면 이 인자를 쓴다'))
    arguments.append(DeclareLaunchArgument(
        'log_dir', default_value='',
        description='run 기록 위치. 비우면 $ROS_HOME/rokey_p3/runs'))
    arguments.append(DeclareLaunchArgument(
        'publish_clock', default_value='true',
        description='브릿지가 /clock 을 낼 때 false. stub_sim 이 /clock 을 내지 않고 sim time 을 따른다'))
    arguments.append(DeclareLaunchArgument(
        'run_host', default_value='',
        description='run ID 의 호스트 칸(master01, master02). 비우면 event_logger 가 hostname 을 쓴다'))
    arguments.append(DeclareLaunchArgument(
        'emulate_m0609', default_value='true',
        description='stub_sim 이 /m0609/joint_states·gripper/holding 을 낸다. 브릿지가 낼 때 false'))
    arguments.append(DeclareLaunchArgument(
        'pharmacy_only', default_value='false',
        description='orchestrator 가 조제실 구간만 돈다. 적재 뒤 도크로 복귀하고 실은 주문은 HOLD_RETURN'))
    arguments.append(DeclareLaunchArgument(
        'dispenser_file', default_value='',
        description='orchestrator 재고 파일. 비우면 rokey_p3_orchestrator share 의 config/dispenser.yaml'))
    arguments.append(DeclareLaunchArgument(
        'zones_file', default_value='',
        description='orchestrator 구역 파일. 병실 테이블(kind station + room)이 있으면 병실 묶음을 그 테이블 한 곳에, '
                    '스테이션 자리의 주문은 st- 인식표로 인증한다(재범 9/25). 비우면 예전 동작'))
    arguments.append(DeclareLaunchArgument(
        'order_pool_file', default_value='',
        description='주문 풀 파일. orchestrator·order_generator·stub_sim·stub_arm·stub_detector 가 같이 읽는다. '
                    '비우면 share 의 config/order_pool.yaml'))

    arguments.append(DeclareLaunchArgument(
        'publish_cabinet', default_value='true',
        description='stub_sim 이 /evaluator/cabinet 을 낸다. Isaac 이 보관함 참값을 낼 때 false '
                    '(작성자 하나). 끄면 그 회차는 run 기록의 SUCCESS 근거가 없다'))
    arguments.append(DeclareLaunchArgument(
        'use_ur5_arm', default_value='false',
        description='실물 UR5 팔 노드(rokey_p3_manipulation 의 arm)를 같이 띄운다. 기본은 꺼짐. '
                    'use_stub_arm:=false · pick_notice:=false · ur5_arm_params_file 과 한 묶음이다'))
    arguments.append(DeclareLaunchArgument(
        'ur5_arm_params_file', default_value='',
        description='UR5 팔 노드의 현장값 파일(프레임 이름·홈 자세·오프셋). use_ur5_arm:=true 면 반드시 준다'))

    arguments.append(DeclareLaunchArgument(
        'deck_slots', default_value='5',
        description='AMR 상판에 실을 수 있는 봉투 수. 자리가 없으면 그 주문은 deck_full 로 닫는다. '
                    '칸막이 다섯이던 상판은 5, 통짜 트레이는 3 이다(시뮬 #445)'))
    arguments.append(DeclareLaunchArgument(
        'belt_timeout_s', default_value='20.0',
        description='조제 뒤 봉투가 벨트 끝에 닿기를 기다리는 시한(sim s). 병원 씬 컨베이어는 약 35 s 라 60 을 준다'))
    arguments.append(DeclareLaunchArgument(
        'observation_guard', default_value='false',
        description='시험용. orchestrator 가 계약 11.3·11.6 관측(BeltObservation·ArmClearance)을 피킹·다음 배출에 '
                    '더 요구한다. ArmClearance 는 L3 FK 대조 전에는 믿지 않는다'))
    arguments.append(DeclareLaunchArgument('dispense_while_dispatching', default_value='false'))
    arguments.append(DeclareLaunchArgument(
        'use_isaac_adapter', default_value='false',
        description='true 면 stub_sim 의 조제기·리셋·벨트를 끄고 isaac_adapter 가 Isaac JSON 토픽으로 맡는다'))
    arguments.append(DeclareLaunchArgument(
        'pick_notice', default_value='true',
        description='isaac_adapter 가 적재 픽 POUCH_PICKED 를 Isaac 에 알려 봉투를 치우게 한다. '
                    '진짜 UR5 가 Isaac 에서 집으면 false'))
    arguments.append(DeclareLaunchArgument(
        'belt_observation', default_value='false',
        description='isaac_adapter 가 /isaac/pharmacy/belt_observation 을 /pharmacy/belt/observation'
                    '(BeltObservation, 계약 11.6)으로 옮긴다. 스테이지를 --belt-observation 으로 띄울 때 true'))
    arguments.append(DeclareLaunchArgument(
        'sim_pouches', default_value='false',
        description='isaac_adapter 가 /isaac/amr_1/pouches(JSON)를 /amr_1/sim/pouches(PouchDetectionArray)로 '
                    '옮긴다. 계약 토픽 hand_camera/pouches 에는 내지 않는다'))
    arguments.append(DeclareLaunchArgument(
        'sim_tag_reads', default_value='false',
        description='isaac_adapter 가 /isaac/amr_1/tag_reads(JSON)를 /amr_1/sim/tag_reads(TagRead)로 옮긴다'))
    arguments.append(DeclareLaunchArgument(
        'sim_cabinet', default_value='false',
        description='isaac_adapter 가 /isaac/evaluator/cabinet(JSON)을 /evaluator/cabinet'
                    '(CabinetObservation, L)으로 옮긴다(K5b). 계약 토픽 그대로 낸다 — 그 작성자는 isaac 이다. '
                    'stub_sim 의 publish_cabinet 과 같이 켜면 작성자가 둘이다'))
    arguments.append(DeclareLaunchArgument(
        'pouch_source', default_value='camera',
        description='UR5 팔이 봉투 검출을 어디서 보나. camera(기본, 계약 토픽) 또는 sim. '
                    'sim 이면 sim_pouches 도 켜야 한다. **이 인자가 params 파일보다 우선한다**'))
    arguments.append(DeclareLaunchArgument(
        'scan_tag_source', default_value='camera',
        description='UR5 팔이 인식표를 어디서 보나. camera(기본) 또는 sim. sim 이면 sim_tag_reads 도 켜야 한다'))
    arguments.append(DeclareLaunchArgument(
        'deck_pick_from_frame', default_value='false',
        description='상판 칸에서 집을 때 검출 대신 칸 TF 로 파지 자세를 만든다(K5). '
                    'pouch_source:=sim 과 같이 켜지 않는다'))
    arguments.append(DeclareLaunchArgument(
        'gripper_command_seq', default_value='false',
        description='isaac_adapter 가 그리퍼 GripperState·GripperCommand(계약 11.6)를 Isaac JSON 과 옮긴다. '
                    '스테이지를 --gripper-command-seq 로 띄울 때 true'))

    arguments.append(DeclareLaunchArgument(
        'use_pouch_detector', default_value='false',
        description='실물 pouch_detector(color 검출 + QR)를 띄운다. use_stub_detector 와 같이 켜지 않는다'))
    arguments.append(DeclareLaunchArgument(
        'vision_check', default_value='false',
        description='UR5 팔의 비전 교차 확인(재범 9/25). pouch_source:=sim 으로 상판에서 집을 때 접근 자세에서 '
                    'hand_camera/pouches 를 1 s 기다려 참값과 0.05 m 안이면 검출 좌표로 집고, 아니면 참값 + '
                    'vision_mismatch 로그. use_pouch_detector:=true 와 같이 준다'))
    arguments.append(DeclareLaunchArgument(
        'detector_max_rate_hz', default_value='0.0',
        description='pouch_detector 추론 주기 상한, Hz(0 = 없음). 재범 9/25: 5'))
    arguments.append(DeclareLaunchArgument(
        'detector_save_reads_dir', default_value='',
        description='pouch_detector 가 상판 집기 뒤 손 카메라 프레임(초마다 한 장)을 남길 디렉토리. 비우면 안 남긴다'))
    arguments.append(DeclareLaunchArgument(
        'detector_pouch_width_m', default_value='0.0',
        description='pouch_detector 의 봉투 실제 폭, m. 현장값(0 = 안 씀)'))
    arguments.append(DeclareLaunchArgument(
        'use_m0609_detector', default_value='false',
        description='M0609 손 카메라의 QR 판독(pouch_detector, robot_id=m0609, detector=none). '
                    '/m0609/hand_camera/tag_reads 를 낸다(보충 전 약통 확인, QR·DB·카메라 계약 2.3)'))
    arguments.append(DeclareLaunchArgument(
        'm0609_save_reads_dir', default_value='',
        description='m0609_detector 가 약통 QR 을 읽은 순간 영상 한 장을 남길 디렉토리(발표 PiP). 비우면 안 남긴다'))
    arguments.append(DeclareLaunchArgument(
        'pharmacy_db', default_value='false',
        description='orchestrator 가 약 DB 를 열고 /orchestrator/check_container 를 낸다(계약 2.3)'))
    arguments.append(DeclareLaunchArgument(
        'dispense_timeout_s', default_value='2.0',
        description='어댑터가 Isaac 의 Dispense 응답을 기다리는 시한, s(wall). 계약 7절 기본 2 s. '
                    '병원은 스테이지 틱이 길어 2 s 안에 답이 안 온다(9/23: 거부 ×3) — demo_v2 가 10 s 를 준다'))
    arguments.append(DeclareLaunchArgument(
        'belt_view_frame', default_value='pharmacy/belt_end',
        description='UR5 팔이 벨트 픽 전에 손 카메라로 내려다볼 프레임(+z 위). belt_view_standoff_m 이 0 이면 안 쓴다'))
    arguments.append(DeclareLaunchArgument(
        'belt_view_standoff_m', default_value='0.0',
        description='벨트 관측 자세의 카메라-프레임 거리, m. 0 = 끔(지금 동작). pouch_source:=camera 일 때만 쓴다. '
                    '**이 인자가 params 파일보다 우선한다**'))
    arguments.append(DeclareLaunchArgument(
        'belt_view_offset_m', default_value='0.0',
        description='벨트 관측점을 belt_view_frame 의 x(진행 방향)로 옮긴다, m. 음수 = 상류'))
    arguments.append(DeclareLaunchArgument(
        'detector_pouch_distance_m', default_value='0.0',
        description='pouch_detector 의 카메라-봉투 고정 거리, m. 현장값(0 = 안 씀)'))

    sim_time = [{'use_sim_time': True}]
    use_isaac_adapter = LaunchConfiguration('use_isaac_adapter')
    stub_sim_serves = ParameterValue(NotSubstitution(use_isaac_adapter), value_type=bool)
    # Isaac 이 /clock·/m0609/* 를 낼 때 스텁도 내면 작성자가 둘이 된다(계약 4절).
    # 자동으로 끄지 않고 경고만 한다(명시가 낫다).
    clock_or_m0609_from_stub = PythonExpression([
        "'", use_isaac_adapter, "'.lower() == 'true' and ('", LaunchConfiguration('publish_clock'),
        "'.lower() == 'true' or '", LaunchConfiguration('emulate_m0609'), "'.lower() == 'true')"])
    stub = {name: IfCondition(LaunchConfiguration(name)) for name in STUBS}
    publish_clock = LaunchConfiguration('publish_clock')
    # 풀을 읽는 노드는 모두 같은 파일을 봐야 한다. 빈 값은 문자열로 넘겨 노드가 기본 파일로 간다.
    pool = {'order_pool_file': ParameterValue(LaunchConfiguration('order_pool_file'), value_type=str)}

    return LaunchDescription(arguments + [
        # 노드보다 먼저 돈다. 묶음이 어긋나면 여기서 멈춘다.
        OpaqueFunction(function=_refuse_broken_ur5_arm_bundle),
        LogInfo(msg=['경고: use_isaac_adapter:=true 인데 publish_clock:=', LaunchConfiguration('publish_clock'),
                     ' emulate_m0609:=', LaunchConfiguration('emulate_m0609'),
                     '. Isaac 이 /clock·/m0609/* 를 내면 작성자가 둘이 된다. 그 경우 둘 다 false 로 준다.'],
                condition=IfCondition(clock_or_m0609_from_stub)),
        Node(package='rokey_p3_orchestrator', executable='orchestrator',
             name='orchestrator', output='screen',
             parameters=sim_time + [{
                 **pool,
                 'pharmacy_only': ParameterValue(LaunchConfiguration('pharmacy_only'), value_type=bool),
                 'observation_guard': ParameterValue(LaunchConfiguration('observation_guard'), value_type=bool),
                 'deck_slots': ParameterValue(LaunchConfiguration('deck_slots'), value_type=int),
                 'belt_timeout_s': ParameterValue(LaunchConfiguration('belt_timeout_s'), value_type=float),
                 'dispense_while_dispatching': ParameterValue(
                     LaunchConfiguration('dispense_while_dispatching'), value_type=bool),
                 'pharmacy_db': ParameterValue(LaunchConfiguration('pharmacy_db'), value_type=bool),
                 'dispenser_file': ParameterValue(LaunchConfiguration('dispenser_file'), value_type=str),
                 'zones_file': ParameterValue(LaunchConfiguration('zones_file'), value_type=str),
             }]),
        Node(package='rokey_p3_orchestrator', executable='order_generator',
             name='order_generator', output='screen',
             condition=IfCondition(LaunchConfiguration('use_order_generator')),
             parameters=sim_time + [{**pool, 'max_requests': ParameterValue(
                 LaunchConfiguration('max_requests'), value_type=int)}]),
        Node(package='rokey_p3_orchestrator', executable='event_logger',
             name='event_logger', output='screen',
             parameters=sim_time + [{'log_dir': LaunchConfiguration('log_dir'),
                                     'run_host': ParameterValue(LaunchConfiguration('run_host'), value_type=str)}]),
        # stub_sim 은 /clock 을 내면 sim time 을 쓸 수 없고, 안 내면 다른 노드처럼 sim time 을 따른다.
        Node(package='rokey_p3_bringup', executable='stub_sim', name='stub_sim',
             parameters=[{
                 **pool,
                 'publish_clock': ParameterValue(publish_clock, value_type=bool),
                 'use_sim_time': ParameterValue(NotSubstitution(publish_clock), value_type=bool),
                 'emulate_m0609': ParameterValue(LaunchConfiguration('emulate_m0609'), value_type=bool),
                 'publish_cabinet': ParameterValue(LaunchConfiguration('publish_cabinet'), value_type=bool),
                 'serve_dispense': stub_sim_serves,
                 'serve_reset': stub_sim_serves,
                 'publish_belt': stub_sim_serves,
             }], output='screen', condition=stub['use_stub_sim']),
        Node(package='rokey_p3_bringup', executable='isaac_adapter', name='isaac_adapter',
             parameters=sim_time + [{
                 'pick_notice': ParameterValue(LaunchConfiguration('pick_notice'), value_type=bool),
                 'belt_observation': ParameterValue(LaunchConfiguration('belt_observation'), value_type=bool),
                 'gripper_command_seq': ParameterValue(LaunchConfiguration('gripper_command_seq'),
                                                       value_type=bool),
                 'sim_pouches': ParameterValue(LaunchConfiguration('sim_pouches'), value_type=bool),
                 'sim_tag_reads': ParameterValue(LaunchConfiguration('sim_tag_reads'), value_type=bool),
                 'sim_cabinet': ParameterValue(LaunchConfiguration('sim_cabinet'), value_type=bool),
                 'dispense_timeout_s': ParameterValue(LaunchConfiguration('dispense_timeout_s'),
                                                      value_type=float)}],
             output='screen', condition=IfCondition(use_isaac_adapter)),
        Node(package='rokey_p3_bringup', executable='stub_fleet', name='stub_fleet',
             parameters=sim_time, output='screen', condition=stub['use_stub_fleet']),
        Node(package='rokey_p3_bringup', executable='stub_arm', name='stub_arm',
             parameters=sim_time + [{**pool, 'serve_refill': ParameterValue(
                 LaunchConfiguration('use_stub_m0609'), value_type=bool)}],
             output='screen', condition=stub['use_stub_arm']),
        # 실물 UR5 팔. 프레임 이름·홈 자세·오프셋은 현장값이라 params 파일로만 받는다.
        Node(package='rokey_p3_manipulation', executable='arm', name='arm',
             # 묶음 인자 셋은 params 파일 **뒤에** 둔다. launch 가 정본이라야 위에서 묶음을 판정할 수 있다.
             parameters=sim_time + [ParameterFile(LaunchConfiguration('ur5_arm_params_file'), allow_substs=True), {
                 'pouch_source': ParameterValue(LaunchConfiguration('pouch_source'), value_type=str),
                 'scan_tag_source': ParameterValue(LaunchConfiguration('scan_tag_source'), value_type=str),
                 'deck_pick_from_frame': ParameterValue(LaunchConfiguration('deck_pick_from_frame'),
                                                        value_type=bool),
                 'belt_view_frame': ParameterValue(LaunchConfiguration('belt_view_frame'), value_type=str),
                 'belt_view_standoff_m': ParameterValue(LaunchConfiguration('belt_view_standoff_m'),
                                                        value_type=float),
                 'belt_view_offset_m': ParameterValue(LaunchConfiguration('belt_view_offset_m'), value_type=float),
                 'vision_check': ParameterValue(LaunchConfiguration('vision_check'), value_type=bool)}],
             output='screen', condition=IfCondition(LaunchConfiguration('use_ur5_arm'))),
        Node(package='rokey_p3_bringup', executable='stub_detector', name='stub_detector',
             parameters=sim_time + [pool], output='screen', condition=stub['use_stub_detector']),
        Node(package='rokey_p3_perception', executable='pouch_detector', name='pouch_detector',
             parameters=sim_time + [{
                 'robot_id': 'amr_1',
                 'detector': 'color',
                 'pouch_width_m': ParameterValue(LaunchConfiguration('detector_pouch_width_m'), value_type=float),
                 'pouch_distance_m': ParameterValue(LaunchConfiguration('detector_pouch_distance_m'),
                                                    value_type=float),
                 'max_rate_hz': ParameterValue(LaunchConfiguration('detector_max_rate_hz'), value_type=float),
                 'save_reads_dir': ParameterValue(LaunchConfiguration('detector_save_reads_dir'), value_type=str)}],
             output='screen', condition=IfCondition(LaunchConfiguration('use_pouch_detector'))),
        Node(package='rokey_p3_perception', executable='pouch_detector', name='m0609_detector',
             parameters=sim_time + [{'robot_id': 'm0609', 'detector': 'none', 'pouch_from_qr': False,
                                     'save_reads_dir': ParameterValue(LaunchConfiguration('m0609_save_reads_dir'),
                                                                      value_type=str),
                                     'max_rate_hz': ParameterValue(LaunchConfiguration('detector_max_rate_hz'),
                                                                   value_type=float)}],
             output='screen', condition=IfCondition(LaunchConfiguration('use_m0609_detector'))),
    ])
