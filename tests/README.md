# 저장소 하네스 테스트

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

GPU·ROS·네트워크·제3자 Python 패키지가 필요 없다. 실패 기록 덮어쓰기/삭제, freeze 변조,
pilot/acceptance 혼합, NaN/Infinity, 누락값 은폐, 분모·단위·clock 오류, 임의 필드,
경로 탈출·symlink, 서명 URI, artifact hash/크기 불일치를 거부하는지 검사한다.

`fixtures/evidence/`의 2000년 날짜·합성 버전·숫자는 **검사기 테스트 전용**이다.
실제 실행이나 측정이 아니며 `evidence/runs/`에 복사하지 않는다. 실제 프로토콜 작성에는
[proposed template](../experiments/templates/pilot-smoke-v1.json)을 사용한다.
`fixtures/runs/` 의 run 디렉토리도 집계기 테스트용 합성 출력이다.

## 파일

| 파일 | 케이스 | 검사하는 것 |
| --- | --- | --- |
| `test_evidence.py` | 37 | `tools/evidence.py` 가 잘못된 기록·protocol 을 거부하는지(위 목록). 임시 git 저장소는 자동 gc·maintenance 를 끈다(#141) |
| `test_aggregate_runs.py` | 17 | `tools/aggregate_runs.py` 가 합성 event_logger run 디렉토리를 protocol 지표로 집계하는지 |
| `test_repository.py` | 15 | `tools/check_repository.py` 가 깨진·저장소 밖 링크, 본문 물결표, 원본 로그·패키지 복사, `COLCON_IGNORE` 경계(영역 디렉토리가 있을 때만), Markdown 파일 이름, symlink 를 잡는지, `web/` 이 선언된 영역이고 그 아래도 같은 검사를 받는지, 텍스트 파일의 NUL 바이트를 줄 번호와 함께 잡고 이미지·Nav2 맵(`.pgm`) 같은 바이너리는 통과시키는지(#131) |
| `test_interface_contract.py` | 9 | `src/rokey_p3_interfaces/` 파일이 [계약 10절](../docs/architecture/delivery-contract-v1.md#10-인터페이스-v11-변경-목록)의 v1.1 목록과 같은지, CMakeLists 목록이 빠짐없는지, 주석이 ASCII 인지. 글자로만 보고 ROS 빌드는 하지 않는다 |
| `test_node_attributes.py` | 3 | ROS 노드 파일이 rclpy `Node` 의 내부 속성 이름(`self._clients` 등)을 덮어쓰지 않는지. `ast` 로만 본다 |
| `test_demo_window_layout.py` | 22 | `tools/demo_window_layout.py`(시연 창 배치)의 작업 영역 반분(master01·master02 값, 홀수 폭), 제목·WM_CLASS 로 Isaac·웹 창 고르기(브라우저 대화상자 제외), X 가 없을 때 이유와 Super+←/→ 안내를 내고 3 으로 끝나는지. 배치 판정(`verdict`: 중심이 맡은 반쪽 안, 위치 ±80 px·크기 ±120 px)이 9/20 master01 관측(요청 993,32 → 실제 116,69 = 실패)과 Wnck 배치(통과)·창 관리자 밀림(통과)을 가르는지. 창 관리자에게 보내는 요청의 순수 부분(좌표 비트·보낸 쪽 표시, 빼야 할 창 상태 고르기). 창을 실제로 옮기는 것은 L3 이라 여기 없다 |
| `test_demo_v2.py` | 64 | `tools/demo_v2.sh`(시연 한 명령)의 문법, 사용법·필수 환경 변수 안내, `cmds` 가 보여 주는 네 명령이 실습 절차와 같은지(stage `env -i`·preset·자산, arm `scene_version:=2 v2_seed:=7`, stack 인자, web `--allow-commands`), 화면 크기로 Isaac 왼쪽 반·브라우저 오른쪽 반 크기가 정해지는지, 웹 주소 기본이 시연 모드(`?demo=1`)인지, `status` 가 띄울 때와 지금의 트리 sha 를 찍는지, 월드별 인자와 두 PC 모드 기동 전 확인(`TwoMasterTests`). tmux·ROS 없이 bash 만 |
| `test_ci_changed_paths.py` | 17 | `ci_changed_paths.py`가 `web/`·`tests/`만이면 colcon을 건너뛰는지, `sim/`이 아니면 sim·usd도 건너뛰는지, 실습 글·사진은 unit·lint도 건너뛰는지, `tools/`는 colcon을 태우는지. `--base`가 merge ref 첫 부모인지(#128, #148). required check 이름과 Draft·경로 게이트가 워크플로에 있는지 |
| `test_aggregate_hospital_full.py` | 23 | `aggregate_runs.py`·`hospital_full_metrics.py` 가 병원 attempt 폴더(`fixtures/runs/hospital-full-a01`, 합성)에서 `hospital-full-acceptance-v1` 규칙을 모두 태우는지 |
| `test_hospital_full_metrics_governor_line.py` | 1 | 감속기 현황 줄이 지표 도구의 `SPEED_LIMIT` 정규식에 잡히는지 |
| `test_round_summary.py` | 7 | `round_summary.py` 가 `attempt_success` 로만 성공을 세고 실패를 `failure_class` 로 나누는지 |
| `test_judge_run.py` | 41 | `judge_run.py` 가 9/21 회차 로그 원문 줄로 보충·거부·낙하·WARN 을 바르게 세는지 |
| `test_boot_check.py` | 47 | `boot_check.py` 의 파서와 판정(잔류·창·잠금·viewport·clock·record·tree). X·ROS·Isaac 없이 |
| `test_record_qa.py` | 9 | `record_qa.py` 의 패킷 읽기와 판정. ffmpeg 가 있으면 짧은 실제 영상으로도 본다 |
| `test_hw_watch.py` | 44 | `hw_watch.py` 를 nvidia-smi 흉내 러너로 돌린다. 실제 GPU 없음 |
| `test_hospital_orders.py` | 17 | `hospital_orders.py` 의 주문 10건 계획·확인·판정, 가짜 웹으로 한 바퀴 |
| `test_ci_test_counts.py` | 10 | `ci_test_counts.py` 가 실행 0 개 패키지를 실패시키고 skip·xfail 수를 허용 표와 대조하는지. 가짜 junit 결과만 |
| `test_git_hooks.py` | 7 | `tools/git-hooks/pre-push` 를 가짜 `gh` 로 네 경우에 돌린다 |
| `test_description_install.py` | 2 | `rokey_p3_description` 이 싣는 데이터 디렉토리를 모두 install 하는지. colcon 없이 |
| `test_tag_read_end_to_end.py` | 6 | 스테이지가 내는 인식표 본문이 어댑터를 지나 계약 값(`pt-` 접두, `KIND_PATIENT`)으로 나오는지 |

케이스 수는 2026-09-30 main `3b0b40b`(`v1.1.0` 뒤 문서 커밋만 더한 것)에서 파일별로 센 값이다. 20개 파일, 모두 398개다.
macOS(python 3.11)에서 위 명령은 394개 통과, `test_demo_v2.TwoMasterTests` 4개 실패였다. 실패는 `127.0.0.2` ping 과 `ip route` 가 없는 환경 탓이다. Linux CI 결과가 기준이다.

## 세 곳의 테스트와 명령

테스트는 세 곳에 있고, 도는 명령이 서로 다르다. 한 명령이 다른 곳을 수집하지 않는다.

| 위치 | 무엇 | 명령 | 필요한 것 | CI |
| --- | --- | --- | --- | --- |
| `tests/`(여기) | 저장소 하네스. 검사기·집계기·계약 글자·노드 속성 | `python3 -m unittest discover -s tests -p 'test_*.py'` | 표준 라이브러리만 | `harness.yml`(모든 PR·main push) |
| `src/<package>/test/` | ROS 패키지의 L1(순수 모듈)·L2(노드를 띄우는 한 바퀴) | `colcon build --symlink-install` 뒤 `colcon test` 와 `colcon test-result --verbose` | ROS 2 Jazzy | `ci.yml`(문서만 바뀐 변경과 Draft 는 건너뛴다) |
| `sim/tests/` | Isaac 쪽. 인자·배치·루프 조건 검사는 일반 python3, `test_stage_loads.py`(씬 로드)는 Isaac `python.sh` 로 마스터에서 | `python3 -m unittest discover -s sim/tests -p 'test_*.py'`. 씬 로드는 [sim/tests/README](../sim/tests/README.md) | 앞의 것은 python3, 뒤의 것은 Isaac Sim | `harness.yml` 이 `sim/` 변경에서 앞의 것을 한 패스 돈다(Isaac 없는 러너) |

- 루트 `python3 -m unittest discover -s tests` 는 `sim/tests/` 를 수집하지 않는다.
  main edde51f 에서 `-v` 출력에 `minimal_clock` 이 0건이었고, `sim/tests` 명령은 따로 `Ran 201 tests`, OK(skipped=1, usd-core 가 없어 `test_link_visuals_deinstance_meshes_with_subsets`) 였다. 씬 로드 `test_stage_loads.py` 는 unittest 케이스가 없는 스크립트라 수집되지 않는다(Isaac `python.sh` 로 직접 돌린다).
- `tests/`·`tools/`·`sim/` 에는 `COLCON_IGNORE` 가 있어서 `colcon test` 도 이 디렉토리들을 돌지 않는다.
  `colcon test` 는 `src/<package>/test/` 만 pytest 로 돈다.
- `ruff check .` 는 세 곳을 모두 린트한다(`harness.yml` 의 lint job, 설정은 루트 `ruff.toml`).
- PR 전 명령 전체는 [공통 규칙](../docs/process/repository-rules.md) 에 있다. ROS 없는 세션에서 `colcon` 을 돌리는 방법은 [bringup README 검증 방법](../src/rokey_p3_bringup/README.md#검증-방법)에 있다.
