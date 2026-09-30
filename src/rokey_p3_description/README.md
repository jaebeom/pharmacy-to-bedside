# rokey_p3_description

v1.1.0 병원 한 바퀴에서 이 패키지는 구역·경로 파일 둘을 낸다: `config/zones.hospital-receiver.yaml`·`config/routes.hospital-receiver.yaml`(`tools/demo_v2.sh` 병원 카메라 기본).
주행(`fleet`·`zones_tf`·`dock_origin_tf`), orchestrator, 관제 웹, Isaac 스테이지가 같은 구역 파일(`P3_ZONES`)을 읽는다. 조제기 자산 `models/dispenser/dispenser.usdc` 는 병원 워크셀 준비기(`sim/standalone/prepare_workcell_integration.py`)가 참조한다.
병원 씬 USD 자체는 이 패키지가 아니라 `sim/scenes/hospital_navigationv1.usda` 다.

Isaac Sim 이 읽는 자산과 구역 설정을 담은 ROS 2 패키지. CODEOWNERS 는 `@parksejun12`(박세준)다.

| 폴더 | 내용 |
| --- | --- |
| `config/` | 구역(`zones.*.yaml`)·경로(`routes.*.yaml`) 파일. 아래 [config](#config--구역경로-파일) 절 |
| `stages/` | 씬(스테이지). 지금은 `my_first_scene.usd` 하나뿐이고 한 바퀴에는 쓰지 않는다 |
| `models/` | 씬이 참조하는 개별 자산. 지금은 [조제기](models/dispenser/README.md) 하나다 |

## config — 구역·경로 파일

형식은 [계약 v1 3절](../../docs/architecture/delivery-contract-v1.md#3-프레임과-단위)이다. `zones_file`·`routes_file` 인자(또는 `P3_ZONES`·`P3_ROUTES`)로 고른다.
`zones_file` 을 비우면 `fleet`·`zones_tf` 는 share 의 `zones.yaml` 을 읽는다. orchestrator 는 구역 파일 없이 예전 동작으로 돈다.

| 파일 | 무엇 | 누가 쓰나 |
| --- | --- | --- |
| `zones.yaml` | 기본 파일. 값이 전부 0 이다(아무것도 재지 않았다) | 인자를 비울 때 |
| `zones.emptyworld.yaml`, `routes.emptyworld.yaml` | 빈월드. 자동 생성물(`sim/standalone/pharmacy_layout_json.py`), 값은 임시 | `P3_WORLD=emptyworld` |
| `zones.hospital.yaml`, `routes.hospital.yaml` | 병원, 봉투가 롤러 끝에 서는 구성. 자동 생성물(`sim/standalone/hospital_nav_files.py`) | `P3_WORLD=hospital` 에서 `P3_CAMERA_POUCHES=0` 일 때. receiver 를 끄면(`P3_HOSPITAL_RECEIVER_PRIM=`) `P3_ZONES` 로 직접 준다 |
| `zones.hospital-receiver.yaml`, `routes.hospital-receiver.yaml` | 병원, 봉투가 A1 모듈 탁자에 정착하는 구성(#796). `load` 와 `dock_1` 이 같은 자리 (−8.266, 4.102)다(#790). `dock_2`–`dock_4` 도 모듈 왼쪽이다(#795) | v1.1.0 병원 기본(`P3_CAMERA_POUCHES=1`) |

- 자동 생성물은 손으로 고치지 않는다. 파일 머리에 다시 만드는 명령이 있다.
- 병원 파일의 정차 자세는 빈월드에서 검증한 팔 밑동↔목표 상대 기하를 옮긴 것이다. 병원 높이로 IK 를 다시 풀지 않았다(파일 머리 주석).

## 왜 패키지 안에 두는가

ROS 2 에서 실행 시점에 파일을 찾는 방법은 share 디렉토리 하나뿐이다.
`CMakeLists.txt` 의 `install(DIRECTORY ...)` 가 이 폴더들을
`install/rokey_p3_description/share/rokey_p3_description/` 로 복사하고,
런치 파일과 노드는 거기서 찾는다.

저장소 루트에 두면 `colcon build` 이후 실행되는 코드가 찾지 못한다.
*"파일은 있는데 `ros2 launch` 가 못 찾는다"* 는 대부분 install 을 빠뜨린 경우다.

```bash
colcon build --packages-select rokey_p3_description
source install/setup.bash
ros2 pkg prefix --share rokey_p3_description   # 설치 경로 확인
```

`stages/` 나 `models/` 아래에 새 하위 폴더를 만들어도 `install(DIRECTORY ...)` 가
통째로 복사하므로 `CMakeLists.txt` 를 고칠 필요는 없다. **새 최상위 폴더를 만들면**
그때는 `install` 목록에 추가한다.

## 경로는 반드시 상대 경로로

**씬을 커밋해도 참조 경로가 절대 경로면 다른 PC 에서 열리지 않는다.**

Isaac Sim 에서 자산을 끌어다 놓으면 참조가 `/home/<내계정>/Dev/...` 로 박힌다.
그 씬을 다른 조원이 열면 자산을 찾지 못하고 빈 씬이 뜬다. 파일이 저장소에 있어도
재현이 안 되는 것이다 — 계정 이름과 경로가 사람마다 다르기 때문이다.

- 자산은 이 패키지 안에 두고, 씬에서 `../models/…` 같은 **상대 경로**로 참조한다.
  share 로 설치될 때 폴더 구조가 그대로 유지되므로 상대 경로는 설치본에서도 살아 있다.
- Isaac Sim 기본 제공 자산(원격 경로)은 그대로 참조해도 된다. 복사해 오지 않는다.
- 커밋 전에 확인한다:

  ```bash
  # USDA 는 바로 보인다
  grep -n "/home/\|/media/\|C:" stages/*.usda

  # USDC(바이너리)는 변환해서 본다
  usdcat stages/my_first_scene.usd | grep -n "/home/\|/media/\|C:"
  ```

  걸리는 줄이 있으면 그 참조를 상대 경로로 다시 걸고 저장한다.

## USDA 와 USDC

같은 내용을 두 형식으로 저장할 수 있다. NVIDIA 의 권고는 **사람이 읽고 고치는 가벼운
레이어는 USDA, 무거운 데이터는 USDC** 다.

| 확장자 | 형식 | 쓰는 곳 |
| --- | --- | --- |
| `.usda` | ASCII | 씬 구성, 배치, 물리 설정 — diff 가 보이고 충돌을 손으로 풀 수 있다 |
| `.usd` `.usdc` | 바이너리 | 메시·텍스처 같은 큰 데이터 |

씬을 여러 명이 건드릴 예정이면 Save As 에서 `.usda` 로 저장한다.
바이너리 씬은 diff 가 안 되므로, 두 사람이 같은 파일을 고치면 한쪽 작업을 버려야 한다.

## 레이어를 나눈다

한 씬 파일에 전부 넣으면 한 명이 열어 고치는 동안 나머지가 손을 못 댄다.
지오메트리·머티리얼·물리처럼 성격이 다른 것을 별도 레이어로 두고 씬에서 합치면
각자 자기 레이어만 고칠 수 있다. NVIDIA 가 자산 구조 원칙에서 말하는 모듈성이 이것이다.

## 쓰는 쪽

- 런치 파일·노드 — `get_package_share_directory("rokey_p3_description")`
- [Isaac Sim standalone 스크립트](../../sim/README.md) — `AMENT_PREFIX_PATH` 로 share 를 찾는다

## 개별 자산

- [조제기와 정면 투입구](models/dispenser/README.md): 외부 참조 없는 시각 에셋. 물리·보충 동작 검증 전.
