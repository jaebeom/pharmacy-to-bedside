# v2 모듈 경로 기본 활성화

요청: 임재범 — "기능 기본값을 활성으로 변경하는 pr을 올리자".
기준: #229가 병합된 `main` `0baef8388a1472f3487b87150e55b0ba76926dac`.
상태: 구현 검토, Isaac L3·실기 미실행. 기본값 변경은 현장 검증 완료를 뜻하지 않는다.

## 9월 19일 수정 반영

#231이 병합된 `main` `15010749016c8dc4fe72b86cecd727c4a7efedd8`을 #230에 통합했다.
기본 활성화는 초기 관측 대기·관측 시한·실제 속도·미소 dt·초 경계 변환 수정을 포함한다.
8개 제안의 적용 여부와 남은 범위는 [피드백 검토 기록](2026-09-18-jaebeom-guarded-feedback-review.md)에 있다.
피드백 단절 시 hold 진단 보완은 물리적 정지 보장을 뜻하지 않으며, 제어기 로컬 stop/watchdog는 후속 범위다.
통합 커밋의 검사 결과는 #230 본문에 기록한다.

## 변경 범위

`M0609ArmNode`가 `scene_version`, `use_sim_time`, `open_loop`의 실제 ROS 파라미터 값을 읽어
`v2_guarded_module_path`의 기본값을 정한다. ROS의 명시적인 파라미터 덮어쓰기는 그대로 적용된다.

| 설정 | 결과 |
| --- | --- |
| 기본 실행, 또는 v1 `rail_enabled:=true` | scene 1, 기존 경로 |
| v2 + sim time + closed-loop, 별도 guarded 설정 없음 | guarded 모듈 경로 활성 |
| v2 + wall-clock 또는 open-loop, 별도 guarded 설정 없음 | 기존 v2 경로, 기동 호환 유지 |
| v2 + `v2_guarded_module_path:=false` | 기존 v2 경로 |
| 명시적 guarded true + `use_sim_time:=false` 또는 `open_loop:=true` | 기동 거부 |
| scene 1 + 명시적인 guarded true | 기동 거부 |
| `tools/demo_v2.sh` 기본 실행 | false를 명시해 기존 시연 경로 유지 |
| `P3_V2_GUARDED_MODULE_PATH=true tools/demo_v2.sh up` | true를 명시해 새 경로 검증 실행 |

원통 계획과 모듈의 충돌·자세·속도·관측·리셋 검사는 바꾸지 않는다.
후보가 없거나 시한 안에 완료할 수 없으면 기존 거부 동작을 유지한다.
기본 후보 집합의 전체 계산 시간과 Isaac 완료시간은 미측정이다. 기본 90 sim s 시한도 유지한다.

## 실행과 복귀 설정

기본 활성 실행(기존 팔 노드와 중복 실행하지 않는다):

```bash
ros2 run rokey_p3_manipulation m0609_arm --ros-args \
  -p use_sim_time:=true -p scene_version:=2
```

기존 v2 경로로 실행:

```bash
ros2 run rokey_p3_manipulation m0609_arm --ros-args \
  -p use_sim_time:=true -p scene_version:=2 -p v2_guarded_module_path:=false
```

`tools/demo_v2.sh`는 `v2_guarded_module_path:=false`를 명시한다.
새 경로 검증은 `P3_V2_GUARDED_MODULE_PATH=true tools/demo_v2.sh cmds`로 명령을 확인한 뒤
같은 환경 변수로 `up`을 실행한다. 잘못된 선택값은 기동 전에 거부한다.
설치된 패키지를 실행하므로 후보 커밋 빌드와 `install/setup.bash` 적용이 필요하다.
`P3_ARM_CMD`를 별도로 설정했다면 그 명령의 파라미터가 우선한다.

## 검증

리뷰의 두 회귀를 수정했다. 시연이 노드 기본값을 상속하는 문제는 명시적 false로 차단했고,
기존 wall-clock/open-loop 기동 오류는 지원 환경에서만 기본 활성화하도록 고쳤다.
이는 사용자 요청인 기본 활성화를 지원 환경에 적용하면서 기존 시연 동선을 유지하는 결정이다.
실제 Isaac L3를 통과한 것으로 표시하거나 기존 리뷰를 사람 승인으로 바꾸지 않는다.

`test_m0609_defaults.py`는 실제 ROS 노드를 생성해 기본 v2의 Feedback·레일·명령 주기 초기화,
관측 없는 홈 상태, 명시적 false, 레일 없는 기존 모드와 v1 레일 모드,
wall-clock/open-loop의 기존 기동 유지, 명시적 guarded의 잘못된 조합 거부를 검사한다.
`tests/test_demo_v2.py`는 기본 시연 false, 새 경로의 명시적 선택, 전체 명령 덮어쓰기,
잘못된 선택값의 역할 기동 전 거부를 검사한다. 수정 전 10개 검사에서 실패 10건(subtest 포함)을 재현했고,
수정 후 10개 모두 통과했다. 이는 명령 생성 검사이며 Isaac 완주 결과는 아니다.
현재 커밋의 검사 명령·결과와 CI 링크는 PR 본문에 기록한다.

Isaac L3와 실기 순응 제어는 미실행이다.
기존 실습7·8의 성공 기록을 guarded 경로의 검증으로 사용하지 않는다.
전체 경로 모델과 남은 검증 범위는 [#229 검토 기록](2026-09-18-jaebeom-module-path-code-review.md)을 따른다.
