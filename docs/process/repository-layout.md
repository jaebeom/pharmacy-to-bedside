# 저장소 구조와 이관

ROS 패키지의 share 설치 경로와 Isaac 런타임 경계를 유지한다.
새 디렉토리는 책임이 있을 때만 만든다. 아직 없는 기능 패키지는 필요할 때 생성한다.

```text
ROKEY_P3_A3/
├── docs/process/repository-rules.md  # 공통 규칙
├── README.md / CONTRIBUTING.md / ruff.toml
├── .github/                # CI 워크플로·CODEOWNERS·이슈와 PR 틀
├── src/                    # colcon 패키지 7개(rokey_p3_*); 조제기 USD·zones·routes 는 rokey_p3_description
├── sim/                    # Isaac 실행 코드(standalone)·병원 씬(scenes)·자산(assets)·시험(tests)
├── config/                 # 배포 설정; local은 gitignored
├── experiments/            # protocol(동결 전 검토)·fixtures(성공 회차 입력)·templates
├── evidence/               # runs·reviews·deployments 기록
├── schemas/                # 기계가 검사할 기록 계약
├── tools/                  # 기동(demo_v2.sh)·기동 전 확인·집계·저장소 검사 도구
├── tests/                  # tools 와 저장소 규칙 시험(GPU 없음)
├── web/                    # 관제 웹(프론트·백엔드); colcon 제외
├── docs/
│   ├── architecture/       # 구현 계약
│   ├── planning/           # 목표·일정·미확정 범위
│   ├── process/ / policy/  # 작업 절차·측정 규칙
│   ├── setup/ / runbooks/  # 설치·반복 운영
│   ├── practice/           # master02 실습 기록(evidence 아님)
│   ├── reha/               # 병원 리하 회차·campaign 장부(evidence 아님)
│   ├── presentation/       # 최종 발표 자료
│   ├── images/             # 문서 이미지
│   ├── analysis/           # 해석·반증·한계
│   ├── adr/ / rfc/         # 결정 이력 / 제안
│   ├── templates/          # 작성 틀
│   └── reference/          # 외부 자료
```

| 정보 | 기준 위치 |
| --- | --- |
| 목표·범위 | planning; 상태 명시 |
| 장비·포트 역할 | setup/host-inventory.md |
| 인터페이스·실패 동작 | architecture 및 대응 소스 |
| 지표 의미·평가 규칙 | policy/metrics.md + frozen protocol |
| 회차 원문 요약·campaign 합계 | docs/reha; 원문은 이슈 #240·#771 |
| 실행 수치·환경 | evidence/runs + 외부 원본 |
| 설계 선택 이유 | ADR; run/analysis 링크 |
| 미검증 조사 | RFC 또는 analysis |

## 이번 이관
- 존재하지 않던 docs/network/ 안내 → docs/setup/.
- 기획의 isaac/, p3_interfaces/, results/ 표기 → sim/,
  src/rokey_p3_interfaces/(향후 구현), experiments/·evidence/.
- 기존 src·USD는 이동하지 않는다. CMake 설치와 자산 참조를 보존한다.
- 원본 로그는 evidence 와 외부 저장소로 간다.

비패키지 영역에는 COLCON_IGNORE를 둔다. 빌드는 저장소 루트에서
`colcon build --base-paths src --symlink-install`.
상위 workspace와 저장소 install을 함께 source하는 방법은 [배치 가이드](workspace-layout.md)를 따른다.
