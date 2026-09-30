# 워크스페이스 배치

저장소가 colcon workspace다. 상위 폴더에서 빌드하지 않는다.

```text
<개발 위치>/ROKEY_P3_A3/
├── src/
├── sim/
├── docs/ · evidence/ · experiments/
└── build/ · install/ · log/  # 생성, Git 미추적
```

외부 ROS 노드용 셸에서:

```bash
cd <저장소 경로>
source /opt/ros/jazzy/setup.bash
colcon build --base-paths src --symlink-install
source install/setup.bash
```

위 경로 표기는 실제 경로로 치환한다. Isaac Sim은 [별도 Python 환경](../../sim/README.md)을 따른다.
**예전 코드가 실행될 수 있다.** 상위 workspace와 저장소 내부 install을 함께 source하면 그렇다.
새 셸에서 `AMENT_PREFIX_PATH`와 실제 package share 경로를 확인한다.
예전 build/install/log가 있으면 실행 중인 작업과 소유권을 확인한다. 별도 위치에 보관한다.
진단 목적으로 출처 불명의 상위 산출물을 일괄 삭제하지 않는다.

관제 웹 백엔드는 `web/backend/.venv` 의 Python 으로 뜬다. `tools/demo_v2.sh` 의 `P3_WEB_PY` 기본값이다.
이 venv 는 Git 이 추적하지 않는다. `--system-site-packages` 로 만들어야 venv 안에서 `rclpy` 가 보인다([병원 런카드 0절](../runbooks/hospital-full.md#0-새-pc-에서-처음-한-번만)).

## 배포와 개발
개발 클론과 마스터 release는 분리한다.
release마다 빌드와 install을 따로 쓴다.
어느 SHA·설정·환경을 실행했는지는 [배포 기록](../runbooks/deployment.md)으로 연결한다.
클론의 실제 위치는 사람마다 달라도 된다.

마스터에서 본 예다(관측).

- 9/20 master02 는 `$HOME/Dev/cobot3_ws/release/<날짜>-<sha>/` 워크트리에서 실행했다([장비 목록](../setup/host-inventory.md)).
- `tools/demo_v2.sh status` 는 띄울 때와 지금의 트리 SHA·install 시각을 보여 준다.

- ROS launch·노드 자산은 `get_package_share_directory()`로 찾는다.
- Isaac 실행은 씬 경로를 명시하거나, 검증된 `AMENT_PREFIX_PATH`를 쓴다.
- USD 내부 참조는 패키지 안 상대 경로다. 실제로 로딩된 외부 자산도 fingerprint에 넣는다.

## 빌드 경계
ROS 패키지는 `src`에만 만든다. 다른 영역에는 `COLCON_IGNORE`가 있다.
이 파일은 빌드 탐색만 막는다. 코드 실행 권한이나 데이터 신뢰를 보증하지 않는다.
[저장소 검사](../../tools/README.md)는 다른 영역으로 `package.xml`을 복사한 경우도 거부한다.
