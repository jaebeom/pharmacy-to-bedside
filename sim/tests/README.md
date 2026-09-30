# sim/tests — 씬 로드 smoke 검사

이 디렉토리에는 Isaac 에서 도는 파일과 일반 Python 으로 도는 파일이 섞여 있다.
`test_*.py` 는 66개다. Isaac 이 필요한 것은 `test_stage_loads.py` 하나다. 나머지 65개는 Isaac·ROS 없이 돈다.
아래 표는 대표 파일만 적는다. 병원 쪽 시험은 `test_hospital_*.py`·`test_workcell_*.py` 등이다.

| 파일 | 실행 | 검사하는 것 |
| --- | --- | --- |
| `test_stage_loads.py` | Isaac `python.sh`, 마스터 | 아래 본문의 씬 로드 smoke |
| `test_minimal_clock_args.py` | 일반 `python3`, Isaac 없음 | [`minimal_clock.py`](../standalone/minimal_clock.py) 의 인자 파싱·계약 상수·import 가드·SIGINT 플래그. `/clock` 발행은 검사하지 않는다 |
| `test_m0609_refill_stage.py` | 일반 `python3`, Isaac 없음 | [`m0609_refill_stage.py`](../standalone/m0609_refill_stage.py) 의 인자 파싱·배치 검증(슬롯 A·B, 몸체, 선반 캐니스터)·holding·grasp_verified 판정·관절 명령 필터·자세·도구 yaw 계산·selfdemo 경로·반복 상태 기계·재스폰 타이머·그리퍼 닫힘 목표 유도·발행 주기·종료 코드. 물리·ROS·파지는 검사하지 않는다 |
| `test_pharmacy_stage.py` | 일반 `python3`, Isaac 없음 | [`pharmacy_stage.py`](../standalone/pharmacy_stage.py) 와 [`p3sim`](../standalone/p3sim/__init__.py) 순수 모듈: JSON 스키마(README 예시 대조), 벨트·끝 센서·배출 규칙, seed 재현성, 리셋 주입. 물리·ROS 는 검사하지 않는다 |

```bash
python3 -m unittest discover -s sim/tests -p 'test_*.py'
```

저장소 루트의 `python3 -m unittest discover -s tests` 는 이 파일들을 수집하지 않는다. 위 명령을 따로 돌린다.
CI 는 `.github/workflows/harness.yml` 에서 같은 명령을 돌린다. Draft 가 아닌 PR 과 main push 에서 USD 관련 변경이 있으면 usd-core 24.5(Python 3.11)를 깔고 돌린다. 그때 USD 시험이 skip 되면 실패다.

현재 `test_stage_loads.py`는 **USD를 열고 짧은 앱 업데이트를 수행하는 사전 검사**다.
이 폴더에는 물리·ROS 통신·작업 시나리오를 검증하는 L3 시스템 테스트가 없다. L3 는 마스터의 한 바퀴 회차로 한다([병원 전 구간 런카드](../../docs/runbooks/hospital-full.md)).
이 파일의 PASS를 작업 성공률이나 시뮬레이션 안정성의 증거로 사용하지 않는다.

## 현재 판정 범위

- 입력 USD 파일 존재와 동기 `open_stage()` 성공
- 120회 앱 업데이트 동안 실행 유지
- 마지막 확인 시 대기 중인 파일 로드 없음
- 스테이지와 탐색 가능한 prim 존재

120회는 앱 프레임 수이며 물리 스텝 수나 2초 실행을 뜻하지 않는다.
검사는 timeline을 재생하지 않고 물체 상태 변화·물리 시간 증가를 관측하지 않는다.
모든 참조·텍스처의 정상 로딩, 센서 값, ROS, RTF, 작업 완수도 검증하지 않는다.
리소스가 늦게 로드되면 실패할 수 있으므로 원본 로그와 실제 환경을 함께 확인한다.

NVIDIA 5.1의 [stage API](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/py/source/extensions/isaacsim.core.utils/docs/index.html)는
동기 `open_stage()`의 반환값을 bool로 정의한다. async 결과처럼 tuple로 풀지 않는다.
[SimulationApp API](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/py/source/extensions/isaacsim.simulation_app/docs/index.html)의
`update()`는 앱을 진행한다. 물리를 검증하려면 재생·물리 step과 상태 관측을 별도 구현해야 한다.

## 실행

[sim 실행 안내](../README.md)에서 별도의 ROS 셸로 description 패키지를 빌드하고 설치 경로를 확인한다.
그다음 ROS native 환경이 섞이지 않은 Isaac 셸에서 **매 검사마다 새 프로세스**로 실행한다.

```bash
export P3_SCENE_PATH=/absolute/path/to/install/rokey_p3_description/share/rokey_p3_description/stages/my_first_scene.usd
/absolute/path/to/isaacsim/python.sh /absolute/path/to/ROKEY_P3_A3/sim/tests/test_stage_loads.py
```

파일 이름은 유지하지만 일반 `pytest` 수집용 테스트 함수는 제공하지 않는다.
지원하는 실행 경로는 위의 standalone 명령이며 파일을 import하는 것만으로 앱을 띄우지 않는다.
초기화 이후의 실패에도 `finally`에서 앱을 닫고, 실패는 nonzero exit로 남긴다.

현재 일반 CI에서 GPU 검사를 수행했다고 간주하지 않는다.
현장 실행 시 명령·exit code·stdout/stderr·Git SHA·정확한 Isaac/드라이버 버전·씬 해시를
[evidence 기록](../../evidence/README.md)에 남긴다. PR에는 그 실행 기록을 연결한다.
GPU 미실행은 미검증으로 표시하고 성공 기록을 생성하지 않는다.

## 시스템 검사를 추가할 때

[메트릭 정책](../../docs/policy/metrics.md)에 맞춰 protocol·측정값·합격선을 먼저 정한다.
물리 진행·센서·ROS·시나리오 성공 여부마다 검증 항목을 구현하고 그 범위만 보고한다.
실패·중단·무효 실행도 보존한다. 시나리오별 앱 lifecycle을 일반 pytest로 통합하는 것은 별도 검증 대상이다.

공식 자료 확인일: **2026-09-15**. 현장 smoke 실행: **미실시**.
