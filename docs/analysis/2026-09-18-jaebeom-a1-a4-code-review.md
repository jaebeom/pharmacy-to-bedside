# 2026-09-18 기술 검토 — A1-A4

상태: **unreviewed**. 검토 요청: 임재범(jaebeom). 검토자: 미배정.
범위: 원인 가설 검토·소스 대조·실험 제안. 현장 검증이나 운영 변경 승인이 아니다.

저장소 기준: main `39f53516fcb2549525bceae4e7a882e3d4cba958`.
A2의 측정 기준 `52a13fc`도 관련 생성자를 별도로 대조했다.
작성 중 main `525a9e895e6ce28737370942d37a5ba504e8ecdd`에 병합된 PR #181의
`l2_teardown.py`와 관련 테스트를 추가 확인했다. 아래 A3의 후속 의견에 반영했다.
나머지 정적 판단과 로컬 저장소 검증 기준은 첫 번째 고정 커밋이다.
현장 수치는 사용자가 제공한 2026-09-18 15:00 KST 요청서의 보고다.
master02 원본 로그·설치 패키지·GPU에는 접근하지 않았고 Isaac/ROS L2/L3는 미실행이다.

## 요청서에서 먼저 정정할 것

| 항목 | 소스에서 확인한 것 | 결정에 주는 영향 |
| --- | --- | --- |
| A1 빌드 | 공식 `v5.1.0` 태그의 VERSION도 `5.1.0-rc.19`다 | rc 문자열만으로 개발판 판정·재설치를 처방하지 않는다 |
| A1 종료 상태 | `SimulationApp.is_exiting()`은 Python 객체의 `_exiting`을 반환한다 | Kit running=false와 래퍼 exiting=false는 함께 나올 수 있다 |
| A1 대조 | 우리 `keep_running`은 headless에서 app_running=false를 무시한다 | 프로세스 생존만으로 headless가 같은 고장을 안 겪었다고 말할 수 없다 |
| A2 그룹 | main과 `52a13fc` 모두 상태 구독은 기본 그룹, 액션·타이머는 지정 Reentrant 그룹 | “모든 엔티티가 Reentrant”라는 설명을 정정한다 |
| A2 대안 | Jazzy rclpy 7.1.4에 EventsExecutor backport가 있다 | “Jazzy rclpy에는 없다”도 틀리다. 설치판을 확인한다 |
| A3 ready | 그래프 요청/응답 개수끼리, 실제 매칭 요청/응답 개수끼리 검사 | 그래프 개수와 실제 매칭 개수까지 같아야 한다는 설명은 틀리다 |
| A4 이전 | 병원 USD의 `/World/Conveyor`에 scale 0.5가 있다 | 자식 rigid body의 로컬 scale=1만으로 부족하다 |

우선순위 **A1 > A4 > A2 > A3**에 동의한다.
현재 증거에서는 9/21 시연은 **(가) 창 모드 유지**를 잠정 권고한다.
9/20까지 동일 시연의 headless+WebRTC 완주·reset을 검증하면 (나)를 대안으로 채택할 수 있다.
자동 재기동만으로 주문·재고·epoch 복구가 보장되지는 않는다.

## 출처와 버전 범위

다음은 열어 읽은 공식 자료다. Jazzy 브랜치와 master02/docker의 설치 패키지가 동일하다고 가정하지 않는다.

| ID | 출처 | 버전·범위 |
| --- | --- | --- |
| I1 | [VERSION](https://github.com/isaac-sim/IsaacSim/blob/v5.1.0/VERSION) | 공식 v5.1.0, 값 5.1.0-rc.19 |
| I2 | [SimulationApp](https://github.com/isaac-sim/IsaacSim/blob/v5.1.0/source/extensions/isaacsim.simulation_app/isaacsim/simulation_app/simulation_app.py) | v5.1.0, __init__·is_running·is_exiting·close |
| I3 | [livestream.py](https://github.com/isaac-sim/IsaacSim/blob/v5.1.0/source/standalone_examples/api/isaacsim.simulation_app/livestream.py) | v5.1.0 |
| I4 | [릴리스 노트](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/overview/release_notes.html), [알려진 문제](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/overview/known_issues.html) | 5.1.0, Kit 107.3.3 |
| I5 | [요구 사항](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/requirements.html), [스트리밍](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/manual_livestream_clients.html) | 5.1.0 |
| K1 | [IEventStream](https://docs.omniverse.nvidia.com/kit/docs/kit-manual/107.3.0/carb.events/carb.events.IEventStream.html), [Logging](https://docs.omniverse.nvidia.com/kit/docs/kit-manual/107.3.0/guide/logging.html) | Kit 107.3.0, 현장과 패치 버전 차이 |
| K2 | [IAppWindow](https://docs.omniverse.nvidia.com/kit/docs/omni.appwindow/1.1.9/omni.appwindow/omni.appwindow.IAppWindow.html) | 확장 1.1.9. 현장 버전/메서드 확인 필요 |
| R1 | [node.py](https://github.com/ros2/rclpy/blob/bd637294dd02b1c128422395c059fa06df8387a3/rclpy/rclpy/node.py) | Jazzy 조회 커밋 bd637294 |
| R2 | [executors.py](https://github.com/ros2/rclpy/blob/bd637294dd02b1c128422395c059fa06df8387a3/rclpy/rclpy/executors.py) | 같은 커밋, _make_handler·_take_subscription·MultiThreadedExecutor |
| R3 | [TimeSource](https://github.com/ros2/rclpy/blob/bd637294dd02b1c128422395c059fa06df8387a3/rclpy/rclpy/time_source.py) | 같은 커밋 |
| R4 | [ActionServer](https://github.com/ros2/rclpy/blob/bd637294dd02b1c128422395c059fa06df8387a3/rclpy/rclpy/action/server.py), [ActionClient](https://github.com/ros2/rclpy/blob/bd637294dd02b1c128422395c059fa06df8387a3/rclpy/rclpy/action/client.py) | 같은 커밋, destroy·server_is_ready |
| R5 | [rcl_action/action_client.c](https://github.com/ros2/rcl/blob/22c0b957140035c675f0a061daaab5fd6b2080e7/rcl_action/src/rcl_action/action_client.c) | Jazzy, rcl_action_server_is_available |
| R6 | [Fast DDS 가용 판정](https://github.com/ros2/rmw_fastrtps/blob/eb2b49a66b02c209ce836f04b3611e1ab550c134/rmw_fastrtps_shared_cpp/src/rmw_service_server_is_available.cpp) | Jazzy, __rmw_service_server_is_available |
| R7 | [changelog](https://github.com/ros2/rclpy/blob/bd637294dd02b1c128422395c059fa06df8387a3/rclpy/CHANGELOG.rst), [EventsExecutor](https://github.com/ros2/rclpy/blob/bd637294dd02b1c128422395c059fa06df8387a3/rclpy/rclpy/experimental/events_executor.py) | Jazzy backport 이력과 experimental API |
| R8 | [rclpy #1223](https://github.com/ros2/rclpy/issues/1223) | **Iron** 보고, Jazzy의 같은 원인을 확정하는 증거는 아님 |
| R9 | [공식 action server 예제](https://github.com/ros2/examples/blob/jazzy/rclpy/actions/minimal_action_server/examples_rclpy_minimal_action_server/server.py) | Jazzy, action을 명시 destroy 후 node destroy |
| P1 | [OgnIsaacConveyor.cpp](https://github.com/isaac-sim/IsaacSim/blob/v5.1.0/source/extensions/isaacsim.asset.gen.conveyor/nodes/OgnIsaacConveyor.cpp) | v5.1.0 compute |
| P2 | [PhysxSurfaceVelocityAPI schema](https://docs.omniverse.nvidia.com/kit/docs/omni_usd_schema_physics/latest/physxschema/class_physx_schema_physx_surface_velocity_a_p_i.html) | latest URL, 생성일 2025-02-04 표시. 현장 빌드 동일성 미확인 |
| P3 | [ovphysx 0.6.3 surface velocity](https://nvidia-omniverse.github.io/PhysX/ovphysx/0.6.3/population/PhysxSurfaceVelocityAPI.html) | **후대의 다른 배포 단위**, 2026-09-11 문서. 5.1 바이너리의 직접 증거는 아님 |

## A1

**결론:** 특정 종료 원인은 모른다. 종료 상태 해석·rc 판정·headless 대조 전제는 정정할 수 있다.
**확신도:** 원인 낮음, 세 가지 정정 높음.
**이유:** 실패 당시 원인 계측은 없지만 래퍼·루프 구현은 확인된다.

### Q1-1. running=false, exiting=false

**관측:** I2의 is_exiting은 self._exiting을 반환한다. 생성 시 false이며 close 안에서 true로 바뀐다.
Kit의 종료 절차 전체를 조회하는 함수가 아니다.
is_running은 Kit running·래퍼 exiting·stage 존재를 조합한다.

**판단:** Kit가 running=false가 되었지만 래퍼 close를 아직 호출하지 않았다면 요청서의 세 값은 양립한다.
stage가 남는 것도 래퍼의 stage 정리가 아직 시작되지 않았다는 것과 맞는다.
따라서 이 값 조합만으로 Kit의 비정상 내부 상태나 특정 렌더러 버그를 확정하지 않는다.

Kit post_quit/post_uncancellable_quit/shutdown과 창 닫기 요청은 조사 경로다.
공개 Python 소스만으로 native Kit의 모든 running=false 경로와 고정 로그 문구를 열거할 수는 없다.
device lost가 반드시 동일한 정상 루프 탈출로 나타난다고도 단정하지 않는다.
아래 grep은 탐색 패턴이지 반드시 찍혀야 하는 판정 규칙이 아니다.

### Q1-2. 다음 한 번의 계측

**관측:** 현재 `p3sim/diag.py::subscribe_quit`은 shutdown stream의 **모든 pop 이벤트**를 구독한다.
POST_QUIT일 때만 이름을 붙일 뿐 다른 type도 기록한다.
따라서 “POST_QUIT만 받고 있다”보다 **pop만 보고 있다**가 정확하다.

**판단:** 기존 pop을 유지하고 shutdown·window close·timeline STOP의 push를 추가한다.
push는 발행 시점에 더 가깝지만 C++ 스택이나 OS 창 종료 메시지 발신자까지 밝히지는 못한다.
수신 callback의 Python 스택을 원인 코드의 스택이라고 해석하지 않는다.
K1의 create_subscription_to_push, K2의 get_window_close_event_stream을 사용하되
현장 메서드가 없으면 unavailable을 기록한다. 구독 객체의 수명을 실행 전체에 걸쳐 유지한다.

로깅은 `/log/level=verbose`와 `/log/fileLogLevel=verbose`를 함께 설정하는 시험을 제안한다.
현재 --kit-log-verbose는 후자만 추가한다. 파일 임계값만 낮추면 전체 필터가 남을 수 있다.
`/log/file`은 K1에서 확인된다.
현재 저장소의 `/log/fileFlushLevel=verbose`가 107.3.3에서 실제로 매 줄 flush한다는 점은 확인하지 못했다.
별도 진단 줄은 print(flush=True)로 남긴다.

검색할 출처 이름은 carb.windowing-glfw.plugin, omni.appwindow, carb.graphics-vulkan.plugin,
gpu.foundation.plugin, omni.kit.app.plugin, omni.physx.plugin 및 실제 renderer 로그의 출처다.
모든 내부 사건이 이 채널의 verbose에 찍힌다는 보장은 없다.
현장에서 확인하지 않은 채널별 설정 키나 “종료 이유를 돌려주는 API”는 제시하지 않는다.

### Q1-3. rc.19와 정식 릴리스

**관측:** I1의 공식 v5.1.0 VERSION도 5.1.0-rc.19이고, I4는 Kit 107.3.3을 명시한다.
**판단:** “RC라서 불안정하니 정식 5.1로 올린다”는 처방은 근거가 없다.
다운로드 파일·Kit 빌드·확장까지 같다면 같은 빌드를 재설치할 수 있다.
읽은 5.1 알려진 문제에서 이 자동 종료와 정확히 일치하는 항목은 찾지 못했다.
관련 버그가 없다는 증명은 아니다.

### Q1-4. GPU/드라이버/하이브리드

**관측:** I5의 테스트 Linux 드라이버는 580.65.06이다. 현장의 580.173.02와 다르다.
eDP-1-1이나 Intel 무시 경고만으로 실제 PRIME 구성·Vulkan 장치·패널 배선을 확정할 수 없다.
**판단:** 정확히 이 노트북 조합의 동일 결함은 확인하지 못했다.
Xid 부재는 보고된 커널 GPU 오류가 없었다는 뜻이며,
사용자 공간 렌더러 오류·device lost·창 관리·디스플레이 재구성·VRAM 압박은 배제되지 않는다.
20:51 Xid 119가 앞선 모든 종료의 전조라는 연결도 미확정이다.

NVIDIA 고정·dGPU 직결 모니터는 표시 경로를 분리하는 실험으로 의미가 있다.
먼저 포트 배선을 확인해야 하며 prime-select 변경은 재로그인/재부팅까지 수반할 수 있다.
안정된 시연 구성을 바꾸는 즉시 처방으로 제안하지 않는다. 아래는 조회 명령만 포함한다.

### Q1-5. B형 STOP

**관측:** 사람 STOP에서도 입력 로그가 없었으므로 로그 부재는 사람 입력 부재의 증거가 아니다.
타임라인 끝·stage 재개방/교체·확장의 stop 호출은 일반적인 조사 경로다.
사람 STOP 때 looping=true와 먼 end time은 그 사례를 끝 도달로 설명하는 데 맞지 않는다.
**판단:** STOP 이벤트에 사용자/물리오류를 구별하는 공통 원인 필드가 있다고 확인하지 못했다.
물리 오류가 자동 STOP을 만드는 정확한 5.1 경로도 이 로그로 특정할 수 없다.
입력 구독은 시간 상관만 보여준다. UI 버튼 인과를 확정하려면 해당 버전 toolbar/hotkey handler까지 계측한다.
Python stop 래핑만으로 native 호출까지 포착할 수 없다.
모든 STOP의 자동 play 복구는 사람의 의도적 STOP도 되돌리므로 운영 규칙에 명시해야 한다.

### Q1-6. 시연 선택

**권고: 잠정 (가)**. 최근 같은 기계에서 보고된 장시간 창 모드 실습을 근거로 한다.
이는 원인 해결이나 실패 확률 보장이 아니라 검증된 실행 경로를 우선하는 판단이다.
**(나)**는 대안으로 검증한다. headless도 GPU 렌더러·인코더를 사용하므로 보편적인 드라이버 우회는 아니다.
I3는 omni.services.livestream.nvcf를 활성화한다.
현재 저장소 기본 omni.kit.livestream.webrtc와 달라 시험에서는 기존 override 인자로 공식 예제를 맞춘다.
클라이언트 연결·주문 완주·reset·재연결까지 검증해야 한다.
**(다)**는 단독 대책으로 채택하지 않는다. 새 주문 차단·끊긴 주문 종결·재고/epoch 동기화 없이
프로세스만 재기동하면 이전 주문이 남을 수 있다. 로그 보존 후 검증된 reset 절차로 수동 복귀한다.

### 우리 가설 판정

| 가설 | 판정 | 근거 |
| --- | --- | --- |
| 1. 창/렌더러 사건 | 모름, 우선 조사 | 직접 이벤트 기록이 없음 |
| 2. 잦은 기동·동시 GPU 앱·누적 상태 | 모름 | 날짜 간 코드와 실행 방식도 함께 변경 |
| 3. rc 고유 문제 | 모름, “rc이므로 비정식”은 틀림 | 공식 태그 VERSION 대조 |
| GPU 원인 기각 | 재검토 | Xid 부재로 사용자 공간 오류까지 배제 불가 |
| 다른 사람이 죽임 기각 | 범위를 좁혀 유지 | 직접 kill과는 맞지 않지만 UI/IPC quit는 별개 |
| 우리 코드 기각 | 범위를 좁힐 것 | 빈 월드도 공통 bootstrap·확장·루프를 사용 |
| 화면 유휴만 원인 | 상당히 약화 | inhibit 실패, 다른 표시 사건까지 배제한 것은 아님 |
| 추가 앱 관련성 없음 | 모름 | 앱 로그 부재로 자원 경합을 배제할 수 없음 |

### 확인 실험 1 — 동일 실행의 계측

마스터의 제품 소스 직접 수정은 요청하지 않는다.
아래는 Simu가 **계측 PR로 통합할 코드 제안**이며 현장 미실행이다.
SimulationApp 생성 직후 install하고, poll은 **루프 조건 평가 직전마다** 호출한다.
headless에서도 raw Kit 상태 변화를 기록하며 기존 종료 조건은 바꾸지 않는다.

~~~python
import functools
import json
import threading
import time
import traceback
import omni.kit.app
import omni.appwindow
import omni.timeline

_a1_refs = []
_a1_last = None

def a1_emit(kind, **fields):
    print("a1_probe " + json.dumps(
        dict(kind=kind, wall_ns=time.time_ns(), mono_ns=time.monotonic_ns(),
             tid=threading.get_ident(), **fields),
        default=str, ensure_ascii=False), flush=True)

def a1_event(label, event):
    if label.startswith("timeline:") and event.type != int(omni.timeline.TimelineEventType.STOP):
        return
    try:
        payload = dict(event.payload)
    except Exception:
        payload = repr(getattr(event, "payload", None))
    a1_emit(label, event_type=int(event.type), payload=payload,
            stack=traceback.format_stack(limit=10))

def a1_watch(label, stream):
    for phase in ("push", "pop"):
        subscribe = getattr(stream, "create_subscription_to_" + phase)
        _a1_refs.append(subscribe(
            functools.partial(a1_event, label + ":" + phase),
            name="p3.a1." + label + "." + phase))

def a1_install():
    kit = omni.kit.app.get_app()
    a1_emit("build", kit=kit.get_build_version())
    for label, get_stream in (
        ("shutdown", kit.get_shutdown_event_stream),
        ("timeline", lambda: omni.timeline.get_timeline_interface().get_timeline_event_stream()),
        ("window_close", lambda: omni.appwindow.get_default_app_window().get_window_close_event_stream()),
    ):
        try:
            a1_watch(label, get_stream())
        except Exception as error:
            a1_emit("unavailable", target=label, error=repr(error))

def a1_poll(simulation_app):
    global _a1_last
    kit = omni.kit.app.get_app()
    state = (kit.is_running(), simulation_app.is_exiting(),
             simulation_app.context.get_stage() is None)
    if state != _a1_last:
        a1_emit("state", kit_running=state[0], wrapper_exiting=state[1],
                stage_missing=state[2], update_number=kit.get_update_number())
        _a1_last = state
~~~

다음 명령은 현재 코드로 로그를 모을 수 있다.
`P3_REPO`와 `P3_ISAAC_ENV` 배열은 현장 runbook에서 설정된 값을 쓴다.
같은 도메인의 기존 시뮬레이터와 중복 실행하지 않는다.

~~~bash
cd "$P3_REPO"
p3_a1_dir="$HOME/markle_tmp/a1-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$p3_a1_dir"
git rev-parse HEAD > "$p3_a1_dir/revision.txt"
nvidia-smi -q > "$p3_a1_dir/gpu-before.txt"
xrandr --listproviders > "$p3_a1_dir/xrandr-providers.txt"
if command -v prime-select >/dev/null; then prime-select query > "$p3_a1_dir/prime.txt"; fi
date -u +%FT%TZ > "$p3_a1_dir/start.txt"
set -o pipefail
"${P3_ISAAC_ENV[@]}" "$HOME/isaacsim/python.sh" sim/standalone/pharmacy_stage.py \
  --preset demo-ros-refill \
  --order-pool "$P3_REPO/src/rokey_p3_orchestrator/config/order_pool.yaml" \
  --duration 1800 --kit-log-file "$p3_a1_dir/kit.log" --kit-log-verbose --/log/level=verbose \
  2>&1 | tee "$p3_a1_dir/stage.log"
p3_a1_exit=$?
printf '%s\n' "$p3_a1_exit" > "$p3_a1_dir/exit-code.txt"
journalctl -k --since "$(cat "$p3_a1_dir/start.txt")" -o short-iso-precise \
  > "$p3_a1_dir/kernel.txt"
journalctl --user --since "$(cat "$p3_a1_dir/start.txt")" -o short-iso-precise \
  > "$p3_a1_dir/user-journal.txt"
rg -n -i -C 12 'a1_probe|app_state|POST_QUIT|app_stopped|device.?lost|VK_ERROR|GLFW|Xid|NVRM|Out of memory|timeline.*STOP' "$p3_a1_dir"
~~~

a1_probe는 계측 PR 통합 뒤에만 나온다. 전체 verbose 설정은 위 명령으로 전달한다.
현재 pharmacy_stage.parse_args는 parse_known_args를 쓰고, I2의 SimulationApp._start_app도
알 수 없는 CLI 인자를 Kit에 전달한다. 시작 시 출력되는 전달 인자와 실제 설정값을 확인한다.
코드에서 설정할 경우 app_config의 extra_args로 같은 두 키를 전달할 수도 있다.

읽는 법: window_close → shutdown push → running=false면 창 종료 요청 경로가 좁혀진다.
발신자가 사람인지는 여전히 모른다. push만 있고 pop이 없으면 기존 계측 공백이다.
running=false만 있으면 native 경로가 남는다.
device-lost/Xorg 사건은 같은 wall timestamp로 맞춘다.
프로세스 생존 외에 update 번호·sim time·주문 진행을 확인한다.
별도 통제 실행에서 사람이 STOP/창 닫기를 해서 hook이 실제 사건을 기록하는지도 확인한다.

### 확인 실험 2 — 시연 후보 대조

실험 1과 같은 커밋·씬·ROS 노드·주문에서 창 모드와 아래 스트리밍을 순서대로 실행한다.
낮 시간 각 30분으로 시작한다. 빈 샘플 성공은 약국 시연 성공을 대신하지 않는다.

~~~bash
cd "$P3_REPO"
"${P3_ISAAC_ENV[@]}" "$HOME/isaacsim/python.sh" sim/standalone/pharmacy_stage.py \
  --preset demo-ros-refill \
  --order-pool "$P3_REPO/src/rokey_p3_orchestrator/config/order_pool.yaml" \
  --livestream --livestream-extension omni.services.livestream.nvcf \
  --duration 1800 --kit-log-file "$HOME/markle_tmp/a1-stream-kit.log" --kit-log-verbose --/log/level=verbose
~~~

I5의 Isaac Sim WebRTC Streaming Client로 master02에 연결한다.
기본 LAN 설정부터 검증하고 인터넷 노출 설정은 추가하지 않는다.
headless에서도 raw running·주문 완료·reset 뒤 주문·재연결을 확인한다.
headless도 running=false이면 기존 “headless만 안정” 해석을 폐기한다.
종료가 안 되면 자신이 띄운 실행만 Ctrl-C로 내린다.

### 모르는 것

다음 실패의 probe 전후 30초·Kit 로그 마지막 300줄·오류 문맥·kernel/user journal·resolved_args·확장 버전이 필요하다.
과거 자료는 `~/markle_tmp/kit-*.log`와 `pswatch18.log`의 9/17 19:43 ±120초부터 요청한다.
검색 결과가 없을 때도 0건과 잘리지 않은 마지막 구간을 함께 남긴다.

## A2

**결론:** executor 차이는 유력하지만 GIL 하나로 확정할 수 없다.
**확신도:** 중간. MT/ST 대조와 전용 executor 개선은 유력한 정황이고, 메시지 age·lock 대기가 분리되지 않았다.
**최소 변경:** 9/21 이후 상태 구독을 별도 노드와 전용 SingleThreadedExecutor로 분리하는 시험안을 권고한다.

### Q2-1. 알려진 동작과 기전

**관측:** R2는 wait-set에서 준비된 작업을 만들어 ThreadPoolExecutor로 넘긴다.
준비 작업 선택·실제 take·callback-group 진입·Python 실행·애플리케이션 lock은 다른 지점이다.
R8에는 Iron의 MT에서 빈도 저하·높은 CPU 보고가 있다. Jazzy 같은 버그의 확정 증거는 아니다.

**판단:** worker 가용성·태스크 분배·GIL·callback group·공유 lock·발행 지터가 후보다.
Event.wait/time.sleep은 worker를 점유하지만 대기 내내 GIL을 독점하는 CPU 루프와는 다르다.
8개 중 1개가 기다린다는 사실만으로 4초 지연 전체를 설명하지 못한다.
수신만 하는 최소 노드에서도 MT/ST 차이가 났다는 보고는 긴 action이 필수 조건이 아님을 시사한다.

**정정:** main과 `52a13fc` 모두 다섯 상태 구독에 callback_group을 지정하지 않는다.
R1의 기본 그룹은 MutuallyExclusive이고, R3의 /clock도 기본 그룹을 사용한다.
상태 callback 하나가 공유 `_lock`을 기다리면 같은 그룹의 /clock·다른 상태 구독도 밀릴 수 있다.

### Q2-2. 구조 선택

| 후보 | 평가 |
| --- | --- |
| a. 상태용 별도 MutuallyExclusive 그룹 | 이미 기본 ME이므로 “ME로 바꾸기”만으로 부족. /clock과 별도 ME로 나누면 그룹 연쇄 대기는 줄 수 있지만 worker·GIL·lock 공유 |
| b. 별도 노드·전용 ST executor | **이번 권고**. 유사 변경의 개선 증거가 있고 action 구조 유지 가능. 프로세스 GIL과 공유 lock은 남음 |
| c. async execute_callback | 장기적으로 타당. async def만 붙이고 Event.wait/sleep을 남기면 안 됨. rclpy Future로 양보하고 성공·취소·reset·close에서 종결해야 함. asyncio 루프 자동 존재를 가정하지 않음 |
| d. EventsExecutor | R7에서 **7.1.4 Jazzy backport**, experimental 모듈 확인. 설치판 확인 후 별도 후보. blocking action을 둔 채 시연 직전에 교체하지 않음 |

최소 변경 경계는 기존 다섯 구독의 타입·토픽·QoS·1.0초 기준 유지다.
수신 노드에서 즉시 monotonic timestamp를 얻고 짧은 lock 아래 snapshot만 교체한다.
FSM·재고·액션 부수 효과는 기존 오케스트레이터가 소유한다.
기존 _on_bool 전체를 옮겨 같은 _lock과 _push까지 실행하면 전용 executor도 다시 묶인다.

snapshot 수신 시각을 FSM 처리 시각으로 덮어쓰지 않는다.
reset 전 데이터가 reset 뒤 신선한 상태가 되지 않도록 기존 barrier·무효화도 유지한다.
Bool heartbeat처럼 원본 timestamp/epoch가 없으면 지연 도착 자체를 완벽히 구별할 수 없다.
callback receipt freshness와 source freshness는 다른 계약이다.

### Q2-3. /clock 분리

**관측:** R3의 _subscribe_to_clock_topic은 소유 노드의 create_subscription을 쓴다.
attach_clock은 다른 ROSClock을 붙이는 공개 메서드다.
rclcpp의 전용 clock thread 옵션이 rclpy Jazzy에도 그대로 있다고 가정하면 안 된다.

**판단:** 같은 Node를 두 executor에 동시에 넣지 않는다.
전용 Node/TimeSource가 단독 executor에서 수신하고, 기존 TimeSource를 detach한 뒤
기존 ROSClock을 전용 TimeSource에 attach하는 설계는 가능하다.
그러나 use_sim_time 변경·활성 상태·clock jump callback·종료 순서를 함께 관리해야 한다.
이번 최소 변경 b에 섞지 않고 별도 검토한다.
기존 TimeSource를 둔 채 /clock 구독만 추가하면 중복 clock 업데이트를 만들 수 있다.

### Q2-4. 측정 타당성

**관측:** 현재 래퍼는 callback 진입 간격을 잰다. DDS 도착→callback 시작 지연은 아니다.
5 Hz 정상 간격은 약 0.2초다. 관찰자의 “최대 0.00”을 원시 최대 간격으로 해석할 수 없다.
0.25초 초과만 남겼다면 **임계값 초과 간격 중 최대(없으면 null)**로 표 제목을 정정한다.

**판단:** 독립 관찰자도 DDS와 자기 executor를 거치므로 발행 시각의 직접 측정이 아니다.
QoS를 맞추고 seq 또는 source timestamp로 같은 메시지를 대응시켜야 한다.
비주기 /events의 긴 간격은 메시지 생성 자체가 드문 것일 수 있다.
BEST_EFFORT와 RELIABLE은 backlog·drop이 달라 단순 비교하면 안 된다.

전역 lock·무한 gaps 목록·파일 출력은 관측 부하다.
기존 wrapper는 두 인자 callback(MessageInfo) 및 async callback 의미도 보존하지 않는다.
이번 동기 callback만 대상으로 제한하거나 원래 signature/async 동작을 보존해야 한다.

R2의 _take_subscription은 MessageInfo 전달을 지원한다.
received_timestamp/source_timestamp는 RMW 지원과 clock domain부터 확인한다.
epoch 기반 timestamp에서 monotonic을 빼지 않는다.
0 또는 실제 수신이 아닌 take 시점 값이면 DDS 대기 시간으로 해석하지 않는다.

### Q2-5. 발행 타이머 지터

**관측:** 스텁 MT 지터가 ST에서 개선됐다는 보고는 동일 executor 계열 병목과 양립한다.
**판단:** 같은 원인이라고 확정하지 않는다.
타이머 기대 만료·실제 callback·publish 시각을 구분한다.
sim-time 타이머라면 느린 /clock 전달도 의심한다.

### 우리 가설 판정

| 가설 | 판정 | 근거 |
| --- | --- | --- |
| 1. executor/GIL로 구독 기아 | 모름, 유력 | MT/ST 대조는 지지, 구간별 시간 미측정 |
| 2. 전부 Reentrant라 악화 | **전제 틀림** | 측정 당시와 현재 모두 구독은 기본 ME |
| 3. 측정 부풀림 | 모름, 보정 필요 | QoS·필터된 최대·전역 lock 영향이 남음 |

### 확인 실험 1 — 설치판·그룹 확인

시스템 Jazzy 또는 기존 L2 컨테이너 **안에서** 실행한다. 설치/업그레이드는 하지 않는다.

~~~bash
source /opt/ros/jazzy/setup.bash
dpkg-query -W ros-jazzy-rclpy ros-jazzy-rcl ros-jazzy-rmw-fastrtps-cpp ros-jazzy-rmw-fastrtps-shared-cpp
python3 - <<'PY'
import importlib.util
import inspect
import rclpy
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.time_source import TimeSource
print("rclpy:", rclpy.__file__)
print(inspect.getsource(MultiThreadedExecutor.shutdown))
print(inspect.getsource(TimeSource._subscribe_to_clock_topic))
try:
    spec = importlib.util.find_spec("rclpy.experimental.events_executor")
except ModuleNotFoundError:
    spec = None
print("events_executor:", None if spec is None else spec.origin)
rclpy.init()
n = Node("a2_group_probe")
print("default_group:", type(n.default_callback_group).__name__)
n.destroy_node()
rclpy.shutdown()
PY
rg -n -A 4 'create_subscription|create_timer|ReentrantCallbackGroup' \
  "$P3_REPO/src/rokey_p3_orchestrator/rokey_p3_orchestrator/orchestrator_node.py"
~~~

R7의 7.1.12에는 ThreadPoolExecutor shutdown backport도 있다.
설치판이 오래되었다면 A3 종료 동작의 소스 대조도 달라진다.
이 조회는 업데이트 지시가 아니다.

### 확인 실험 2 — age·간격·callback 시간 분리

기존 같은 구독에 아래 두 인자 callback을 **시험 브랜치에서** 연결한다.
QoS·payload callback을 유지하고 bounded ring에만 기록한다. 파일 출력은 종료 후 한다.

~~~python
from collections import deque
from threading import Lock
import time

samples = deque(maxlen=4096)
samples_lock = Lock()

def timed_callback(msg, info):
    begin_wall = time.time_ns()
    begin_mono = time.monotonic_ns()
    original_callback(msg)
    end_mono = time.monotonic_ns()
    row = (begin_wall, begin_mono, end_mono,
           info.source_timestamp, info.received_timestamp)
    with samples_lock:
        samples.append(row)
~~~

original_callback은 기존 동기 함수다. async에 이 래퍼를 쓰지 않는다.
같은 최소 입력을 ST/MT 수신 노드로 비교하고 원시 최대 간격·개수·age를 보고한다.
`begin_wall - received_timestamp`는 같은 clock domain의 실제 수신값임이 확인된 경우만 사용한다.
callback 시간이 길면 내부 lock 대기를 별도로 재서 원인을 좁힌다.
수신 timestamp가 유효하지 않으면 시험용 발행기에 seq와 monotonic_ns를 넣고
**같은 호스트·같은 clock namespace**에서 수신 시각과 비교한다.
이것도 전체 age이며 DDS/executor 구간을 완전히 분리하지는 못한다.
확인되지 않은 tracing 이벤트나 rclpy 자동 지원을 전제로 하지 않는다.

### 모르는 것

최소 재현 전체 코드·원시 통계·실제 QoS·CPU/cgroup 제약·Debian 패키지 버전이 필요하다.
1.0초 freshness 기준은 관측 편의를 위해 늘리지 않는다.

## A3

**결론:** action 명시 정리 누락은 소스와 재현이 잘 맞는다. CI ready 실패의 최종 원인은 미확정이다.
**확신도:** 누수 경로 높음, ready 실패와의 인과 낮음.
**이유:** destroy/gc 대조는 일관되지만 ready 실패 자체를 재현하지 못했다.

### Q3-1. destroy_node의 범위

**관측:** R1 Node.destroy_node는 pub/sub/client/service/timer/guard를 정리한다.
waitables의 ActionServer/ActionClient를 destroy하는 순회는 없다.
R4 action destroy는 native handle 정리와 node.remove_waitable을 수행한다.
R9 공식 예제도 action server를 명시 정리한다.

**판단:** 현재 Jazzy에서 Node.destroy_node만으로 충분하다고 보면 안 된다.
이 동작을 API 소유권 설계로 볼지 수명 관리 결함으로 볼지와 현장 수정은 분리한다.
정확히 이 재현의 upstream issue/수정 PR·고쳐진 배포판은 확인하지 못했다.
관련성이 다른 메모리 누수 이슈를 해결 근거로 붙이지 않는다.

현재 StubArm은 만든 action server들을 멤버로 보관하지 않는다.
Orchestrator도 /deliver 서버를 보관하지 않고 destroy_node는 close 후 super만 호출한다.
스텁 하나만의 문제가 아니므로 소유 action 수명 관리가 후속 범위다.
순환 참조와 native handle 의존성의 정확한 연결은 설치판에서 더 확인해야 한다.

### Q3-2. 서버 존재와 ready의 차이

R5 rcl_action_server_is_available은 **다섯 조건의 AND**다.

1. send_goal 서비스 사용 가능.
2. cancel_goal 서비스 사용 가능.
3. get_result 서비스 사용 가능.
4. feedback 구독이 보는 publisher 수가 0이 아님.
5. status 구독이 보는 publisher 수가 0이 아님.

R6의 각 서비스 판정은, 유효한 핸들을 전제로 아래 조건을 검사한다.

~~~text
graph_request_readers > 0
graph_response_writers > 0
graph_request_readers == graph_response_writers
matched_request_readers > 0
matched_response_writers > 0
matched_request_readers == matched_response_writers
~~~

**관측:** **graph 수 == matched 수 비교는 없다.**
graph 10/10, match 1/1이면 통과할 수 있다. match 9/10이면 실패한다.
status/feedback 수와 send_goal 이름 존재만으로 전체 조건을 확인한 것은 아니다.

**판단:** 가설 2는 발견/매칭 비대칭 가능성까지는 맞지만,
“누수 서버 모두와 매칭돼야 하므로 하나만 늦어도 false”는 틀리다.
10개여도 True였다는 재현 결과와도 맞는다.
실패 순간 **기존 클라이언트 핸들**의 세 서비스 수치가 필요하다.
새 probe client는 다른 endpoint이므로 참고 자료일 뿐이다.

### Q3-3. 격리 방식

우선 명시 teardown을 공통화한다.
독립 Context 주입은 소유권을 명확히 하지만 action 정리 누락을 자동 해결하지는 않는다.
강한 격리가 필요한 통합 시나리오는 새 Python subprocess 또는 launch_testing으로 기동·종료를 확인한다.
pytest --forked는 이미 DDS/스레드가 초기화된 부모에서 fork하면 다른 문제를 만들 수 있다.
깨끗한 부모에서만 고려한다.
도메인 분리는 외부/병렬 간섭을 줄여도 같은 프로세스의 객체 누수는 고치지 못한다.

fixture 시작 검사는 프로세스 소유 action 목록과 DDS 그래프를 구분한다.
같은 도메인의 외부 노드가 보인다는 이유만으로 “이 pytest가 누수했다”고 판정하지 않는다.
반대로 gc 객체 검색만으로 native 자원이 모두 내려갔다고 판정하지도 않는다.

### Q3-4. 내림 순서

원안에는 **executor.shutdown보다 앞선 협력 종료**가 빠져 있다.
Deliver가 _closing/context 종료를 기다리는데 close를 destroy_node까지 미루면
executor가 callback 완료를 기다리며 종료가 막힐 수 있다.

권장 순서:

1. 새 요청을 차단하고 close/stop 플래그를 설정. 자체 homing/state executor·스레드도 종료 대상에 등록.
2. context가 유효한 동안 action이 abort/cancel 종결 경로에서 빠져나오도록 기다림.
3. executor shutdown 및 spin thread 종료 확인. join(timeout) 호출뿐 아니라 is_alive 검사.
4. snapshot list(node.waitables)에서 **소유 ActionServer/ActionClient**를 명시 destroy.
5. node.destroy_node로 일반 엔티티 정리.
6. context.try_shutdown, 참조 해제. gc.collect는 잔여 확인용.

R2의 현재 MT shutdown은 wait_for_threads=True이면 ThreadPoolExecutor의 thread join을 기다린다.
shutdown(timeout_sec=5)만으로 전체 함수가 반드시 5초 안에 끝난다고 가정하지 않는다.
worker 종료 실패는 fixture 격리 실패다. 살아 있는 callback 아래에서 handle을 파괴하고 다음 테스트로 진행하지 않는다.
subprocess라면 해당 프로세스 종료·회수로 격리한다.

Waitable은 확장점이므로 모든 waitable에 destroy가 있다는 범용 가정은 피한다.
action type-check 또는 소유 객체별 cleanup 등록을 사용한다.
노드와 도우미의 **중복 destroy**를 막도록 소유권을 하나로 정한다.
일반 guard/timer/service/parameter 서비스는 Node가 관리하지만,
executor 자체 guard·별도 thread/node/context는 각 소유자가 정리해야 한다.

### 우리 가설 판정

| 가설 | 판정 | 근거 |
| --- | --- | --- |
| 1. waitable 미파괴로 수명 연장 | 맞다, 높은 확신 | R1/R4와 destroy·참조 해제 대조 일치 |
| 2. graph와 match 전체 개수 일치 필요 | **틀림**, 비대칭 가능성만 유지 | R6의 실제 비교식 |
| participant당 shm 8개 | 현장 관측으로만 유지 | 일반 계산 규칙이 아님. 파일 잔재와 살아 있는 participant 구분 |

### 확인 실험 1 — 누수 회귀

요청서 원문 leak.py를 `~/markle_tmp/leak.py`에 저장한 것이 전제다.
동일 빌드 환경에서 각 모드를 새 프로세스로 실행한다.

~~~bash
source /opt/ros/jazzy/setup.bash
source "$P3_REPO/install/setup.bash"
python3 "$HOME/markle_tmp/leak.py" plain
python3 "$HOME/markle_tmp/leak.py" waitables
python3 "$HOME/markle_tmp/leak.py" drop
~~~

plain만 증가하고 명시 정리에서 0이면 수명 관리 원인을 재확인한다.
수정 후에는 gc를 끈 동일 프로세스 반복에서도 owned action/node가 baseline으로 돌아와야 한다.
graph discovery는 비동기이므로 단발 조회 대신 제한 시간 내 안정된 수를 확인한다.
전역 /dev/shm 파일을 삭제하지 않는다.

### 확인 실험 2 — ready 실패 분해

서비스 세 개의 존재와 endpoint를 함께 기록한다.

~~~bash
ros2 service list -t --include-hidden-services | rg '/m0609/refill/_action/'
ros2 topic info -v /m0609/refill/_action/status
ros2 topic info -v /m0609/refill/_action/feedback
~~~

CLI 결과는 기존 probe client 내부 match 카운터가 아니다.
정확한 판정은 **같은 Jazzy 소스의 진단 빌드**에서 R6 반환 직전에 서비스명·위 여섯 숫자를 출력하고
원래 CI 실패를 재실행해야 한다. 시연 호스트의 RMW를 교체하지 않는다.
graph 10/10, match 1/1이면 원래 가설 2는 반증된다.
한 쌍이 불균형이면 해당 endpoint의 discovery/match 시점을 추적한다.

### 모르는 것

실패한 원래 action client의 서비스별 readiness/match 수, 패키지 버전·fixture 순서·이미지 digest가 필요하다.
작성 중 정비의 공통 teardown은 PR #181로 main에 병합됐다. 중복 구현하지 않는다.
새 도우미는 action type-check와 프로세스 소유 객체 검사를 이미 반영했다.
다만 teardown_nodes 자체는 executor.shutdown부터 시작하며 join 뒤 is_alive를 검사하지 않는다.
호출 fixture가 먼저 close/stop을 보장하는지 확인하고, 실행 중 goal을 가진 종료 테스트로 보완한다.
새 test_teardown_leaves_nothing은 action 객체를 만들지만 goal을 실행하지 않으므로 이 종료 경합을 검증하지 않는다.
또 leftover_action_entities가 검사 전에 gc.collect를 하므로 자동 gc로만 정리되는 누락은 가릴 수 있다.
이 검사를 명시적 소유 자원 정리의 완전한 증명으로 사용하지 않는다.

## A4

**결론:** 로컬 surface velocity와 body의 합성 scale 경로가 1.6배의 유력 원인이다.
**확신도:** 중간. 구조 대조와 후대 공식 구현 설명은 지지하지만 5.1 native 경로와 1.0 예외는 미확정이다.
**권고:** 월드까지 scale·반사를 제거한 rigid-body 좌표계와 collider 치수를 분리한다.

### Q4-1. 좌표계·scale의 사양

**관측:** P1 compute는 direction × velocity를 surfaceVelocity에 쓴다.
자체 x scale 곱셈과 LocalSpace 명시는 없다. enabled를 false→true로 바꾸므로 파싱/속성 갱신 경로도 조사 대상이다.
P2 schema는 local/world 선택, local=true 기본값, 선속도 단위 distance/second를 설명한다.
**후대의 ovphysx 0.6.3 문서 P3**는 local=true에서 파싱 시 분해된 world scale을 성분별로 곱한다고 명시한다.

**판단:** 정확히 1.6배라는 관측을 물리 통합 계층에서 설명할 강한 단서다.
그러나 P3는 Isaac 5.1 동봉 플러그인과 동일 구현이라는 증거가 아니다.
“PhysX 5의 보편적 사양으로 언제나 이 배율이 맞다”로 승격하지 않는다.
PhysX 코어와 Omniverse USD 파서/컨택트 수정 계층을 구별한다.

### Q4-2. 1.0인 경우

**관측:** 창 유무와 ROS/selfdemo를 함께 바꿨으므로 두 요인을 분리하지 못했다.
같은 최종 USD 값만으로 native 파싱 이력을 알 수 없다.
presurface=zero는 API 적용 유무의 단순 설명을 약화하지만
첫 비제로 값·enabled 토글·reset/reparse까지 같게 하지는 않는다.

**판단:** 초기 파싱에서 scale을 접는 경로와 실행 중 속성 갱신의 차이,
합성 xform, resolved local/world 속성, 실제 graph target을 우선 조사한다.
특정 파서 버그로 확정하지 않는다.

### Q4-3. 병원 씬 권장 계층

**관측:** `sim/scenes/hospital_layout.usda`의 /World/Conveyor는 scale (0.5,0.5,0.5)다.
그 아래 local scale=1인 body도 부모 scale을 상속한다.
음수 scale은 합성 변환과 물리 pose/scale 분해를 보아야 한다.

**판단:** 시각 자산 scale과 물리 구동 좌표계를 분리한다.
가능하면 음수 scale은 mesh 정점·노멀·면 방향에 bake하고 물리 proxy는 양의 치수로 생성한다.
body부터 world까지 translation과 proper rotation만 남긴다.
아래는 구조 예시이며 병원 자산의 실제 world pose를 보존해 이식해야 한다.

~~~usda
#usda 1.0
(
    metersPerUnit = 1
    upAxis = "Z"
)
def Xform "World"
{
    def Xform "HospitalVisual"
    {
        # 시각용 축소/미러 자산. 물리 body는 이 아래에 넣지 않는다.
    }
    def Xform "ConveyorPhysics" (
        prepend apiSchemas = ["PhysicsRigidBodyAPI", "PhysxSurfaceVelocityAPI"]
    )
    {
        bool physics:rigidBodyEnabled = true
        bool physics:kinematicEnabled = true
        bool physxSurfaceVelocity:surfaceVelocityEnabled = true
        bool physxSurfaceVelocity:surfaceVelocityLocalSpace = true
        vector3f physxSurfaceVelocity:surfaceVelocity = (0.15, 0, 0)
        double3 xformOp:translate = (0, 0, 0)
        quatf xformOp:orient = (1, 0, 0, 0)
        uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:orient"]
        def Cube "Surface" (
            prepend apiSchemas = ["PhysicsCollisionAPI"]
        )
        {
            double size = 1
            float3 xformOp:scale = (1.6, 0.25, 0.1)
            uniform token[] xformOpOrder = ["xformOp:scale"]
        }
    }
}
~~~

CreateConveyorBelt target은 ConveyorPhysics다.
기존 시각 자산 collider/graph와 이중 충돌·이중 구동되지 않도록 한다.
world 변환의 세 축 길이=1, 축 직교, 오른손 좌표계를 확인한다.
음수 scale과 회전이 섞이면 단순 x 부호만으로 방향 반전을 판정할 수 없다.

속도를 1.6이나 0.5로 나누는 하드코드는 권고하지 않는다.
localSpace=false와 world 단위 방향×속도도 후보지만 yaw와 graph direction 의미를 같이 맞춰야 한다.
현행 graph에서 false만 바꾸면 회전한 벨트가 다른 방향으로 밀 수 있다.

### Q4-4. 알려진 문제·권고

**관측:** 읽은 5.1 릴리스/알려진 문제에 이 1.6배/1.0배 조합의 정확한 이슈는 확인하지 못했다.
P1의 초기 enabled 토글 외 scale 보정 권고도 찾지 못했다.
**판단:** 현재 xform 반복 성공은 프로젝트의 우회 근거다.
부모 scale까지 제거해야 병원 씬으로 일반화할 수 있다.

### 우리 가설 판정

| 가설 | 판정 | 근거 |
| --- | --- | --- |
| 1. 변환 경로에서 속도에 scale 반영 | 모름, 유력 | 관측과 P3 일치. 5.1 native 구현 미확인 |
| 2. headless보다 selfdemo 모드 차이 | 모름 | 두 요인 동시 변경 |
| presurface로 초기화 전체 기각 | 기각 불가 | API 적용과 비제로 값 파싱/갱신 시점은 별개 |

### 확인 실험 1 — 창 유무 × 모드

같은 커밋·scaled-cube로 네 실행을 순차 수행한다.
ROS 조건에는 동일한 dispense 요청을 보내는 기존 ROS 루프가 필요하다.

~~~bash
cd "$P3_REPO"
p3_a4_dir="$HOME/markle_tmp/a4-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$p3_a4_dir"
set -o pipefail
for p3_mode in selfdemo ros; do
  for p3_display in window headless; do
    p3_display_args=()
    if [ "$p3_display" = headless ]; then p3_display_args=(--headless); fi
    "${P3_ISAAC_ENV[@]}" "$HOME/isaacsim/python.sh" sim/standalone/pharmacy_stage.py \
      --mode "$p3_mode" --belt-body scaled-cube --belt-speed 0.15 \
      --order-pool "$P3_REPO/src/rokey_p3_orchestrator/config/order_pool.yaml" \
      --duration 180 "${p3_display_args[@]}" \
      2>&1 | tee "$p3_a4_dir/$p3_mode-$p3_display.log"
  done
done
rg 'resolved_args|belt speed_measured|app_state|stop reason' "$p3_a4_dir"
~~~

유효한 speed sample이 없으면 그 조건은 미측정이다.
ratio가 실행 모드를 따라가면 설정/초기화 경로, 표시 모드를 따라가면 render/update 순서를 좁힌다.
모두 1.6이면 과거 1.0의 커밋/인자/초기화 차이를 조사한다.
한 셀만으로 근본 원인을 확정하지 않는다.

### 확인 실험 2 — 합성 좌표계·재파싱

아래는 stage가 있는 Simu 계측 PR의 read-only 스냅샷이다.
첫 play 전·첫 비제로 compute 뒤·ratio 측정 순간·reset 뒤에 호출한다.
병원 씬에서는 실제 body path를 넘긴다.

~~~python
def surface_snapshot(stage, path):
    from pxr import Gf, PhysxSchema, Usd, UsdGeom
    prim = stage.GetPrimAtPath(path)
    if not prim.IsValid():
        raise ValueError("missing body: " + path)
    matrix = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    axes = [matrix.TransformDir(Gf.Vec3d(*axis))
            for axis in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]
    api = PhysxSchema.PhysxSurfaceVelocityAPI(prim)
    names = ("physxSurfaceVelocity:surfaceVelocity",
             "physxSurfaceVelocity:surfaceVelocityLocalSpace",
             "physxSurfaceVelocity:surfaceVelocityEnabled")
    return {
        "path": path,
        "meters_per_unit": UsdGeom.GetStageMetersPerUnit(stage),
        "has_surface_api": bool(api),
        "attrs": {name: prim.GetAttribute(name).Get()
                  if prim.GetAttribute(name) else None for name in names},
        "world_axis_lengths": [axis.GetLength() for axis in axes],
        "world_axis_dot": [Gf.Dot(axes[0], axes[1]),
                           Gf.Dot(axes[0], axes[2]), Gf.Dot(axes[1], axes[2])],
        "world_basis_det": Gf.Dot(axes[0], Gf.Cross(axes[1], axes[2])),
    }
~~~

동일 실행에서 graph 0.15→0.16→0.15와 reset 전후 ratio를 비교한다.
변경은 Simu 시험 코드에서 graph variable로 수행하고 ratio 분모도 실제 요청 속도와 맞춘다.
마스터에서 기록되지 않은 임의 UI 변경을 섞지 않는다.
USD 값과 합성 축이 같아도 ratio가 parse/reset 경계에서 바뀌면 native 파싱/갱신 차이가 유력해진다.
이 스냅샷은 내부 PhysX의 유효 속도를 직접 읽는 것이 아니다.

### 모르는 것

동봉 omni.physx/PhysxSchema 버전과 속성 갱신 구현, 과거 headless selfdemo의 인자·graph target,
병원 씬의 compose된 collider/body와 실측이 필요하다.

## 반영 경계와 검증

이 PR은 **검토 문서만 추가**한다.
A1 계측은 Simu, A2 구조 시험은 팔, A3 종료 도우미는 정비의 기존 작업에 반영할 제안이다.
A4는 병원 씬 합성 scale을 확인한 뒤 proxy 구성과 현장 검증이 필요하다.
freshness 완화·드라이버 변경·executor 전면 교체·자동 재기동은 이 문서로 승인된 것이 아니다.

공통 기록은 고정 커밋/이미지 digest·패키지 버전·인자·시작/종료 시각이다.
각 문제의 실험은 위 두 개 이하로 묶고 22:00 전에 로그를 닫을 수 있게 낮 시간에 예약한다.
실패 원본은 외부 run artifact로 보존하고 과거 run 기록을 덮어쓰지 않는다.
문서 검증 결과는 PR 본문에 실제 명령과 출력 요약으로 남긴다.
