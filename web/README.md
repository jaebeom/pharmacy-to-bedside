# 관제 웹 서비스

사람이 브라우저로 배송 전체 상황을 보고 조율하는 화면. 지금까지 상태 화면은 터미널용
`status_monitor` 뿐이었다.

| 경로 | 무엇 | 주인 |
|---|---|---|
| [`api.md`](api.md) | **계약.** 서버와 화면 사이의 유일한 기준 | backend |
| [`backend/`](backend/) | ROS 2 상태를 HTTP/WebSocket 으로 내보내는 게이트웨이 | backend |
| [`frontend/`](frontend/) | 브라우저 화면 | frontend |

화면은 셋이다: 개발자 `index.html`(`/`), 간호사 `nurse.html`(촬영 배치 `nurse.html?film=1`), 설정 `settings.html`.
폰 같은 좁은 폭에서는 `nurse.html` 만 쓸 만하다. `index.html` 은 1200 px 아래 배치가 없다([frontend README 6절](frontend/README.md#6-화면-크기--읽히는-것은-폭에-달려-있다)).
**웹에는 인증이 없다**(아래 "안전 기본값").

## 빨리 띄워 보기 (ROS 없이)

```bash
cd web/backend
python3 -m venv --system-site-packages .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m app.main --mock --loop --static ../frontend
# http://127.0.0.1:8000
```

녹화 fixture(조제실 한 바퀴 + 보충 + 리셋, 85 sim s)를 재생해 **실물과 똑같은 API** 를 낸다.
ROS 도 Isaac 도 colcon 도 필요 없다. `--static` 을 주면 화면과 API 가 같은 출처가 된다.

자세한 것은 [`backend/README.md`](backend/README.md) — 설치·3단계 띄우기·시연 점검표.

## master02 시연 절차

> **상태: 지난 기록 (2026-09-18 기준).** 지금 시연·회차는 [`tools/demo_v2.sh`](../tools/README.md#시연-한-명령-demo_v2sh) `up` 이 웹을 tmux `p3v2-web` 으로 띄운다(인자는 [`api.md` §10.3](api.md)).
> 아래는 웹만 손으로 띄울 때의 절차다. 설치(1)·시계(1.5)·ROS 환경(2)·점검표(4)는 지금도 같다.

**master02 에서는 이미 한 번 돌렸다.** 아래는 다시 할 때의 절차다.

> **Ubuntu 24.04 에서는 `python3.12-venv` 가 있어야 한다.** 없으면 `python3 -m venv` 가
> `ensurepip` 오류로 실패한다(시스템 pip 도 없다). master02 에는 재범이 설치해 두었다.
> **다른 기계에서 처음 돌릴 때는 `sudo apt install python3.12-venv` 가 필요하고,
> 시스템 변경이므로 사람의 결정이다.**

master02 관측값: Python 3.12.3 · firefox·google-chrome 있음 · pypi 접속 됨 · 8000-8010 비어 있음.
설치 결과: `fastapi 0.115.6`·`uvicorn 0.34.0`·`websockets 17.1`·`pydantic 2.13.5` 가 venv 안에만
들어가고, 시스템 `typing_extensions` 는 "outside environment" 로 건드리지 않았다.

### 1. 설치 (한 번)

```bash
cd <저장소>
python3 -m venv --system-site-packages web/backend/.venv
web/backend/.venv/bin/pip install -r web/backend/requirements.txt
```

`--system-site-packages` 가 **필수**다. 없으면 venv 안에서 `rclpy` 가 안 보여 실물 모드가 죽는다.

pip 가 실제로 가져오는 것은 `fastapi`·`uvicorn`·`websockets`(+ 개발용 `pytest`·`httpx`)뿐이다.
`pyyaml` 은 ROS 가 이미 들고 있어 `Requirement already satisfied` 로 넘어간다.
**시스템에는 아무것도 설치하지 않는다.**

### 1.5 시계 동기화 확인 (시연 전 필수)

```bash
timedatectl | grep 'System clock synchronized'
#   System clock synchronized: yes
```

**`yes` 가 된 뒤에 웹을 띄운다.** 이 서버는 신선도를 시스템 벽시계로 재는데(계약 4절은
steady clock 이다 — `api.md` §1.1 의 "알려진 차이"), **띄운 뒤에 시계가 뛰면 신호 나이와
`stale` 이 한 번 틀어진다.** 켜자마자 NTP 가 붙으면서 뛰는 경우가 실제로 있다.

**시연 중에 신호 5개가 한꺼번에 `stale` 이 되거나 `/clock 멈춤` 이 뜨는데 스택은 멀쩡하면,
시계가 뛴 것일 수 있다. 웹만 재기동하면 된다** — 스택은 건드리지 않는다.

### 2. ROS 환경

```bash
source /opt/ros/jazzy/setup.bash
source <워크스페이스>/install/setup.bash
```

**확인**(이게 되어야 게이트웨이가 뜬다):

```bash
web/backend/.venv/bin/python -c   "from rokey_p3_interfaces.msg import Event; from rokey_p3_orchestrator import status_view; print('OK')"
```

`ROS_DOMAIN_ID` 는 **스택과 같은 값**이어야 한다. 다르면 토픽이 하나도 안 온다 —
화면은 뜨는데 전부 `unknown` 으로 보인다.

### 3. 띄우기

tmux 세션 이름은 **`m2-web`** 이다.

```bash
tmux new-session -d -s m2-web   "cd <저장소>/web/backend && ROS_DOMAIN_ID=<스택과 같은 값>    .venv/bin/python -m app.main --host 10.10.0.2 --port 8000 --static ../frontend"
```

**먼저 보기 전용으로 한 번 띄워 보는 것이 안전하다** — 같은 기계에서만 열고 명령은 닫아 둔다:

```bash
ROS_DOMAIN_ID=<스택과 같은 값> .venv/bin/python -m app.main   --host 127.0.0.1 --port 8000 --static <프론트 경로>/web/frontend
```

**명령 API 는 기본으로 꺼져 있다.** 시연 운영자가 웹에서 리셋·요청을 넣기로 정했으면
`--allow-commands` 를 붙인다. 붙이지 않으면 화면의 그 버튼들이 403 을 받는다.

`--host` 를 `127.0.0.1` 밖으로 열면 기동 로그에 경고가 찍힌다. **이 서버에는 인증이 없다** —
교육장 유선망 안에서 쓰는 전제다. 그 밖에서는 리버스 프록시나 방화벽이 앞에 있어야 한다.

### 4. 시연 전 점검표

| 확인 | 명령 | 기대 |
|---|---|---|
| 화면이 뜬다 | `curl -s -o /dev/null -w '%{http_code}' http://10.10.0.2:8000/` | `200` |
| API 가 산다 | `curl -s http://10.10.0.2:8000/api/snapshot \| head -c 80` | JSON |
| `/clock` 이 산다 | snapshot 의 `clock.alive` | `true` |
| 신호가 신선하다 | snapshot 의 `signals.*.stale` | 전부 `false` |
| 고장 흉내가 꺼져 있다 | snapshot 의 `mock_faults` | `[]` |
| **시계가 동기화됐다** | `timedatectl \| grep synchronized` | `yes` (§1.5) |
| 명령 상태가 뜻대로다 | `curl -X POST .../api/reset` | 열었으면 `202`, 아니면 `403` |

`mock_faults` 가 비어 있지 않으면 **개발용 스위치가 켜진 채 떴다는 뜻이다.** 내리고 다시 띄운다.

### 5. 내리기

```bash
tmux send-keys -t m2-web C-c     # SIGINT. PID 로 kill 하지 않는다
tmux kill-session -t m2-web
```

## 지금까지 확인된 것

계약이 맞다고 말할 수 있는 근거는 [`api.md` §12](api.md) 에 한자리에 모았다. 요약하면:

- **도메인 118 스텁**에서 한 바퀴가 돈다 — 요청 수락, 리셋(epoch 오름), 신호 신선도 `stale` 0건,
  WS keepalive, 커서 페이징 158건 빠짐·중복 0, `pharmacy_only` 정상 완주에 알람 0건.
- **master02** 에서 기동·화면 로드·명령 잠금(403)·리셋 2회를 확인했다. firefox·google-chrome 둘 다.
- **Isaac v2** 에서 `last_refill.parsed: true` 실데이터를 봤다.
- **9/23 병원 풀 스텁**(#576 v1·v2)에서 긴급 `URGENT_ARRIVING`, 병실·병동 묶음, 주문 10건 연속 `CABINET_LOCKED` 10/10 을 봤다(`api.md` §12.1).

**아직 못 본 것도 같은 문서에 적혀 있다** — `/rosout` 실데이터, `REFILL_DONE` v2 왕복,
실제 TF 로 본 AMR 자세, 여러 AMR 배송(`api.md` §12.2).

> **mock 이 만들지 못하는 조건이 있다**(`api.md` §12.3). 한 줄로 재생하니 도착 순서가 곧
> 시각 순서라, `seq` 와 이벤트 순서를 다루는 코드는 **mock 으로 아무리 재도 검증되지 않는다.**
> 실제로 그 경로에서 버그가 둘 났고 실물에서만 잡혔다. `--mock-fault late_join` 으로 그 조건을
> 흉내 낼 수 있지만, **흉내는 회귀를 잡는 그물이지 합격 도장이 아니다.**

## 이 디렉터리의 규칙

- **`web/` 은 colcon 패키지가 아니다.** `COLCON_IGNORE` 가 있다.
- **측정에는 "조건 재현: 예/아니오" 를 같이 적는다.** 그 조건이 안 만들어진 표본에서의 통과는
  아무것도 증명하지 않는다. 실물 수치를 낼 때는 **어느 트리·어느 포트·어느 sha** 인지도 같이 적는다.
- **계약을 먼저 고친다.** 서버에 필드를 더하면 `api.md` 도 같이 고친다 — 프론트는 문서만 본다.
  `backend/tests/test_contract_doc.py` 가 둘이 갈라지면 실패시킨다.
- **원문을 베끼지 않는다.** 단계표·신호 목록·신선도 임계·이벤트 순서 키는
  `rokey_p3_orchestrator/status_view.py` 를 `import` 해서 쓴다(그 파일은 ROS 를 import 하지 않는다).
  베껴 두면 터미널 모니터와 웹이 서로 다른 말을 하게 된다.
- **새 msg/srv 를 만들지 않는다.** 메시지는 `rokey_p3_interfaces` 만 쓴다.
- **`src/` 를 웹 때문에 고치지 않는다.** 필요하면 이슈로 올린다.

## 안전 기본값

- bind 는 `127.0.0.1`. 외부 노출은 `--host` 를 **명시해야만** 된다.
- 명령 API(`POST /api/reset`·`/api/requests`)는 기본 **403**. `--allow-commands` 로만 열린다.
- `/evaluator/cabinet` 은 평가 전용이라 기본으로 구독·표시하지 않는다.
- 환자 식별자(`patient_id`)는 **서버 로그에 남기지 않는다.**
