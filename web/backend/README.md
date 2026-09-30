# 관제 웹 서비스 — 백엔드

ROKEY_P3_A3 의 ROS 2 상태를 HTTP/WebSocket 으로 내보내는 게이트웨이.
**API 계약은 [`api.md`](../api.md) 가 유일한 기준이다.** 프론트는 그것만 보면 된다.

---

## 1. 설치

```bash
python3 -m venv --system-site-packages .venv
. .venv/bin/activate
pip install -r requirements.txt
```

### `--system-site-packages` 가 필요한 이유

`rclpy` 는 apt 로 깔린 `/opt/ros/jazzy` 에 있고 **pip 로 설치하는 물건이 아니다.**
이 옵션 없이 venv 를 만들면 venv 안에서 `rclpy` 가 안 보여 **실물 모드가 죽는다.**
`--mock` 만 쓸 거면 없어도 되지만, 같은 venv 를 두 모드에 쓰므로 항상 붙인다.

`requirements.txt` 에 `rclpy` 는 없다. 대신 **`websockets` 는 반드시 있어야 한다** —
없으면 uvicorn 이 WebSocket 업그레이드를 거절해 `/ws` 가 404 로 보인다.
(FastAPI TestClient 는 자체 구현을 써서, 이게 없어도 테스트는 통과한다. 속지 말 것.)

---

## 2. 띄우기

### 2.1 개발 (프론트·백엔드 공용) — ROS 없음

```bash
python -m app.main --mock --allow-commands --loop \
  --static ../frontend --port 8001
```

- 합성 fixture(`make_pharmacy_loop.py` — 조제실 한 바퀴 + 보충 + 리셋 + 리셋 뒤 새 요청, 85 sim s)를 재생해
  **실물과 똑같은 API** 를 낸다. ROS 도 Isaac 도 colcon 도 필요 없다.
- `--static` 을 주면 화면과 API 가 **같은 출처**가 되어 CORS 가 필요 없다.
- `--allow-commands` 가 있어야 `POST /api/reset`·`/api/requests` 가 열린다(기본 403).
- `--speed 20` 으로 빨리 감고, `--loop` 로 계속 돌린다.
- 주문 풀 기본값은 저장소 원문 `src/rokey_p3_orchestrator/config/order_pool.yaml`(4건, orchestrator 가 읽는 그 파일).
  더 많은 주문으로 묶음 UI 를 시험하려면 `--order-pool fixtures/order_pool.dev.yaml`.
- 병원 화면은 §2.4.

### 2.2 ROS 실물 연결 확인 — 이 기계에서

```bash
. /opt/ros/jazzy/setup.bash
colcon build --symlink-install
. install/setup.bash

# 터미널 1 — 스텁 루프
ROS_DOMAIN_ID=118 ros2 launch rokey_p3_bringup stub_loop.launch.py pharmacy_only:=true

# 터미널 2 — 백엔드 실물 모드
ROS_DOMAIN_ID=118 python -m app.main --port 8001
```

**`ROS_DOMAIN_ID` 는 118.** 115(통합)·117(master02 개발)과 겹치면 안 된다.

> 빌드에 없는 의존이 나오면 **설치하지 말고 이슈에 적는다.** `sudo` 는 쓰지 않는다.

### 2.3 시연 — master02

지금 시연·회차는 `tools/demo_v2.sh up` 이 웹을 tmux `p3v2-web` 으로 띄운다. 넘기는 인자는 [`api.md` §10.3](../api.md) 에 있다.
아래는 9/18 master02 tmux `m2-web` 에서 손으로 띄우던 형태다.

```bash
python -m app.main --host 10.10.0.2 --port 8000 \
  --static /path/to/web/frontend \
  --order-pool /path/to/src/rokey_p3_orchestrator/config/order_pool.yaml \
  --zones-file /path/to/src/rokey_p3_description/config/zones.yaml
```

설치 스크립트는 없다. **`python -m` 한 줄 + `requirements.txt`** 로 끝난다.

#### 시연 전 점검

| 확인 | 명령 | 기대 |
|---|---|---|
| 화면이 뜬다 | `curl -s -o /dev/null -w '%{http_code}' http://10.10.0.2:8000/` | `200` |
| API 가 산다 | `curl -s http://10.10.0.2:8000/api/snapshot \| head -c 80` | JSON |
| `/clock` 이 산다 | snapshot 의 `clock.alive` | `true` |
| 신호가 신선하다 | snapshot 의 `signals.*.stale` | 전부 `false` |
| WS 가 붙는다 | 브라우저 콘솔에 `hello` | 1건 |
| 명령이 잠겨 있다 | `curl -X POST .../api/reset` | `403` (열려면 `--allow-commands`) |

**명령 API 는 시연에서 쓸 때만 `--allow-commands` 로 연다.** 기본은 잠겨 있다.

---

### 2.4 병원 월드 — mock (ROS 없음)

병실·병동 목적지, 평면도, 촬영 화면(단계·큐)을 ROS 없이 본다. 이 디렉터리(`web/backend`)에서:

```bash
python -m app.main --mock --loop --allow-commands --static ../frontend --port 8001 \
  --fixture fixtures/hospital_trip.json \
  --order-pool fixtures/order_pool.hospital.dev.yaml \
  --zones-file ../../src/rokey_p3_description/config/zones.hospital.yaml \
  --map-file ../../src/rokey_p3_navigation/config/maps/hospital.yaml
```

- `hospital_trip.json` 은 스텁 스택을 녹화한 것이다. 합성이 아니다. 순서는 긴급, 병실 묶음 C1(병상 셋), 병동 묶음(스테이션), 리셋, 리셋 뒤 긴급이다. sim 46 s 다. 이벤트 이름, 순서, detail 이 실물 오케스트레이터 그대로다.
- `--map-file` 을 주면 `/api/map` 이 켜지고 AMR 이 `dock_1` 에 선다(`source: "mock"`). fixture 에 자세는 없다.
- `--loop` 를 빼면 재생이 끝난 뒤 `CLOCK_STOPPED`·`STATUS_STALE` 알람이 뜬다(끝난 fixture 라서).
- `order_pool.hospital.dev.yaml` 은 `hospital_trip.json` 을 녹화할 때 읽은 #553 원문의 10건 사본이다.
  원문 `src/rokey_p3_orchestrator/config/order_pool.hospital.yaml` 은 main 에 있고 13건이다(침상 10 + 테이블 3, api.md §9.1).
  원문 풀로 보려면 `--order-pool ../../src/rokey_p3_orchestrator/config/order_pool.hospital.yaml` 을 준다.
- 확인: `curl localhost:8001/api/destinations`(C1·C2 병실 묶음), `/api/map`, `/api/queue`, `/api/snapshot` 의 `stage`.

실물(ROS)은 `tools/demo_v2.sh` 의 `P3_WORLD=hospital` 이 같은 파일을 넘긴다. 스텁 스택으로 시험할 때
스텁이 무엇을 흉내 내지 **않는지**(TF 없음 → 평면도 AMR 없음 등)는 api.md §10.7.


## 3. 안전 기본값

- bind 기본은 `127.0.0.1`. 외부 노출은 `--host` 를 **명시해야만** 된다.
- **인증이 없다.** `127.0.0.1` 밖으로 열면 기동 로그에 경고를 찍는다(`host_warnings`). 교육장 유선망 안에서 쓰는 전제다.
- 명령 API 는 기본 **403**.
- `/evaluator/cabinet` 은 **평가 전용** 토픽이라 기본으로 구독·표시하지 않는다
  (`--show-evaluator` 로만 켜고, 켜도 `display_only` 로 표시된다).
- 환자 식별자(`patient_id`)는 **서버 로그에 남기지 않는다.**

---

## 4. 실행 인자

| 인자 | 기본 | 뜻 |
|---|---|---|
| `--mock` | 꺼짐 | ROS 대신 fixture 재생 |
| `--fixture` | `fixtures/pharmacy_loop.json` | 재생할 fixture |
| `--host` | `127.0.0.1` | bind 주소 |
| `--port` | `8000` | bind 포트 |
| `--static` | 없음 | 이 디렉터리를 `/` 에서 서빙 (같은 출처) |
| `--allow-commands` | 꺼짐 | `POST /api/reset`·`/api/requests` 를 연다 |
| `--refill-timeout` | `120` | `REFILL_FAILED` 임계 (sim s) |
| `--reset-timeout` | `35` | `RESET_STUCK` 임계 (wall s) |
| `--mock-fault` | 없음 | **개발 전용**: 고장 흉내 (api.md §11). `--mock` 없이는 기동 거부 |
| `--robot-id` | `amr_1` | 구독할 AMR 이름 |
| `--order-pool` | 저장소 원문 `src/rokey_p3_orchestrator/config/order_pool.yaml`(실물·mock 같음) | `order_pool.yaml` 경로 |
| `--zones-file` | 저장소 원문 `src/rokey_p3_description/config/zones.yaml`, 못 찾으면 고정 목록 | `zones.yaml` 경로 (**후보 표시용**, 검증 아님). 병원이면 병실·병동 묶음과 `mixed_rooms` 가 켜진다 |
| `--map-file` | 없음 | Nav2 지도 yaml. 주면 `/api/map`·`snapshot.robots` 가 켜진다(api.md §7.6·§1.6) |
| `--show-evaluator` | 꺼짐 | `/evaluator/cabinet` 을 snapshot 에 싣는다 |
| `--live-sensors` | 꺼짐 | 카메라 MJPEG·라이다 스캔(api.md §1.8). Pillow(`python3-pil`)가 없으면 스스로 끈다 |
| `--roles` | 없음 | 이 PC 의 역할(`P3_ROLES`, 공백 구분). 두 PC 모드 표시(api.md §1.10) |
| `--peer` | 없음 | 상대 PC 주소(`P3_PEER`). 주면 `deployment.multi_pc` 가 `true` |
| `--catalog` | 없음 | 약 카탈로그 YAML. QR 판독 요약(api.md §1.12) |
| `--dispenser-file` | 없음 | 조제기 YAML. 약통 로트 → 약품·유통기한(api.md §1.12) |
| `--speed` | `1.0` | mock 재생 배속 |
| `--loop` | 꺼짐 | mock fixture 반복 |

---

## 5. 구조

| 경로 | 역할 | ROS |
|---|---|---|
| `app/alarms.py` | 알람 규칙표 | **없음 (순수)** |
| `app/request_detail.py` | `REQUEST_ACCEPTED.detail` 파서 | **없음 (순수)** |
| `app/order_pool.py` | `order_pool.yaml` | **없음 (순수)** |
| `app/zones.py` | 구역 ID 검사·후보 목록·병실 이름표 | **없음 (순수)** |
| `app/floorplan.py` | 평면도 지도(yaml + PGM 머리) | **없음 (순수)** |
| `app/film.py` | 촬영 화면의 일곱 단계·주문 큐 | **없음 (순수)** |
| `app/ros_convert.py` | ROS 메시지 → dict | **없음 (duck typing)** |
| `app/ros_spec.py` | 구독 명세(토픽·QoS·반영 자리) 표 | **없음 (순수)** |
| `app/ros_bridge.py` | 실물 ROS 2 브리지. `ros_spec.py` 표대로 구독한다 | **rclpy — 이 파일만** |
| `app/orchestrator_view.py` | `rokey_p3_orchestrator.status_view` 를 그대로 가져온다 | 없음 |
| `app/refill_detail.py` | `REFILL_DONE.detail` 파서 | **없음 (순수)** |
| `app/reject_reason.py` | goal 거부 사유를 `/rosout` 에서 찾는다 | **없음 (순수)** |
| `app/fleet_poses.py` | `/isaac/fleet/poses`(여벌 AMR·더미) 파서 | **없음 (순수)** |
| `app/live_sensors.py` | 카메라 프레임·라이다 스캔(`--live-sensors`) | 없음 |
| `app/qr_info.py` | QR 판독 ID → 사람이 읽는 요약 | 없음 |
| `app/faults.py` | `--mock-fault` 고장 흉내 | 없음 |
| `app/state.py` | snapshot 조립 | 없음 |
| `app/mock.py` | fixture 재생 | 없음 |
| `app/main.py` | FastAPI 앱 + 실행 인자 + 요청 선검사 | 없음 |
| `fixtures/` | fixture JSON + **만드는 스크립트**(합성 `make_pharmacy_loop.py`, 녹화 `record_fixture.py`) | — |
| `tests/` | pytest | 없음 |

**fixture JSON 을 손으로 고치지 마라.** 합성본은 `fixtures/make_pharmacy_loop.py` 를 고치고 다시 돌리고,
녹화본(`hospital_trip.json`)은 스텁 스택을 띄워 다시 녹화한다(`record_fixture.py` 머리에 절차).

```bash
python fixtures/make_pharmacy_loop.py
python fixtures/record_fixture.py --out fixtures/hospital_trip.json --duration 75 --name hospital_trip   # ROS source 뒤
```

`rokey_p3_orchestrator/status_view.py`의 `event_key`·단계표·신선도 임계를 import 한다.
웹 snapshot과 이벤트 버퍼는 자체 `WorldState`가 관리한다. `StatusModel`은 터미널 상태 화면의 모델이며 웹 상태 저장소로 쓰지 않는다. 메시지는 `rokey_p3_interfaces` 만 쓰고
**새 msg/srv 는 만들지 않는다.**

---

## 6. 고장 흉내 (`--mock-fault`)

> **개발 전용이다. 시연 절차에 없다.** `--mock` 없이 주면 기동을 거부한다(exit 2).

정상 재생으로는 볼 수 없는 화면을 시연 전에 확인한다. 자세한 것은 [`api.md` §11](../api.md).

| 이름 | 하는 일 | 보이는 것 |
|---|---|---|
| `stuck_reset` | `POST /api/reset` 이 `RESET_DONE` 을 안 낸다 | `RESET_STUCK` |
| `clock_stop` | sim 10 s 뒤 `/clock` 을 멈춘다 | `CLOCK_STOPPED` |
| `stale:<신호키>` | 그 신호만 갱신하지 않는다 | `STATUS_STALE` |
| `refill_fail` | `REFILL_DONE`·`DISPENSER_RESUMED` 를 버린다 | `REFILL_FAILED` |
| `order_timeout` | 주문을 `TIMEOUT` 으로 닫는다 | `TIMEOUT` |
| `late_join` | 첫 25 sim s 를 **작성자별로 묶어** 쏟는다 | (알람 아님 — 이벤트 순서 검증) |

```bash
python -m app.main --mock --mock-fault clock_stop --reset-timeout 3
python -m app.main --mock --mock-fault stale:m0609_at_home,refill_fail
```

**켜지면 `snapshot.mock_faults` 에 실린다.** 화면이 "고장 흉내 중" 배지를 띄우므로, 시연 때
실수로 켠 채 띄우면 바로 보인다. 평소에는 `[]` 다.

## 7. 테스트

```bash
python -m pytest tests/ -q          # 기본 — ROS 없이 도는 것만
python -m pytest tests/ -q -m ros   # ROS 통합 (워크스페이스 source 필요)
ruff check .
```

**ROS 통합 테스트는 기본 실행에서 빠져 있다**(`pytest.ini` 의 `-m "not ros"`). skip 으로 두면
없는 환경에서 조용히 넘어가 "안 돌았는데 초록" 이 된다.

`tests/test_live_server.py` 는 **진짜 uvicorn 을 서브프로세스로 띄워** 밖에서 두드린다.
TestClient 만으로는 WebSocket 이 실제로 되는지 알 수 없어서 따로 둔 것이다 — 지우지 마라.
(실제로 `/ws` 가 404 인데 TestClient 테스트는 전부 초록이었던 적이 있다.)

`tests/test_contract_doc.py` 는 **`api.md` 와 서버가 갈라지면 실패**시킨다. 프론트는 문서만
보므로, 필드를 더하고 문서를 안 고치면 화면에서만 깨진다.
