# GitHub 적용 상태와 팀 검토

검사 파일과 규약을 저장소에 넣는다고 GitHub 설정·팀 권한·호스트 권한이 바뀌지 않는다.

## 조회한 상태
2026-09-30 00:17 KST(`2026-09-29T15:17Z`) API 조회 기준이다. 조회 명령은 둘이다.

```bash
gh api repos/jaebeom/ROKEY_P3_A3/rulesets/23257828
gh api repos/jaebeom/ROKEY_P3_A3/branches/main/protection
```

- 옛 방식의 branch protection 은 없다(`Branch not protected`, 404).
- ruleset `protect-main`(id 23257828)이 active 다. 대상은 기본 브랜치(`~DEFAULT_BRANCH`)다.
- 그 ruleset 의 마지막 수정은 2026-09-18 02:19 KST 다. bypass 대상은 없다.
- 브랜치 삭제와 force push(non fast-forward)를 막는다.
- PR 이 필요하다. 필수 승인은 0 이다. 새 push 뒤 옛 승인은 해제된다.
- Code Owners 리뷰는 **필수가 아니다**(`require_code_owner_review: false`).
- 병합 방식은 merge commit 하나만 허용한다(`allowed_merge_methods: [merge]`).
- 필수 검사는 셋이다: `Repository and evidence checks`, `Python lint (ruff)`, `CI gate`.
- "main 최신 포함" 조건(strict)은 **꺼져 있다**.
- 저장소 설정은 병합 뒤 head 브랜치를 자동으로 지운다(`delete_branch_on_merge: true`).

첫 조회(2026-09-15)는 달랐다. 그때 ruleset 의 대상 브랜치가 비어 있었다. 필수 검사도 없었다.
조회 이후 설정이 바뀔 수 있다. 위 명령으로 다시 확인한다.
2026-09-17: 9/16-9/17 에 봇이 PR 대부분을 병합했고 9/16 저녁엔 일괄 병합으로 main 이 30분 빨갰다(#43 이 고침). 그래서 [봇 머지 조건](#봇-머지-조건)을 정했다.

## 첫 적용 체크
1. 팀원이 실제 사용하는 GitHub handle과 담당/리뷰 대체자를 확인한다.
2. main에 적용되는 ruleset 대상으로 기본 브랜치를 명시한다.
3. PR 필요, 필수 승인 0, Code Owners 리뷰 필수, 새 변경 후 오래된 승인 해제, 대화 해결을 선택한다.
   봇 병합을 허용하려면 필수 승인이 0 이어야 한다(봇은 GitHub 리뷰를 못 낸다). 사람 승인은 CODEOWNERS 경로에만 붙는다.
4. required check 셋: `Repository and evidence checks`, `Python lint (ruff)`, `CI gate`.
5. `CI gate` 는 항상 끝나는 job 이다. colcon 이 보지 않는 경로(문서, `sim/`)만 바뀐 PR 에서는
   colcon 을 건너뛰고 통과하고, `src/`·`config/`·workflow 가 바뀌면 colcon L1·L2 가 성공해야 통과한다.
   **Draft에서는 colcon을 돌리지 않는다.** Ready(`ready_for_review`)와 main push에서만 태운다. 문서·Draft가 pending에 머물지 않는다.
   `sim/tests/`는 `sim/` 또는 `harness.yml`이 바뀐 때만 돈다. Ready·main은 usd-core 한 패스, Draft는 일반 python3 한 패스다(USD 4개는 skip).
   `tools/`·`experiments/`·`schemas/`는 Ready에서 colcon을 태운다. 판정은 `tools/ci_changed_paths.py`다.
   colcon 밖 경로의 전체 목록은 그 파일 머리 주석에 있다. `web/`·`tests/`·이슈와 PR 틀·`ruff.toml` 도 colcon 밖이다.
   예외로 `sim/standalone/p3sim/` 의 `bridge`·`belt`·`conveyor_end` 는 colcon 을 태운다. bringup L2 가 읽기 때문이다.
   실습 글·스크린샷만 바뀐 PR은 `tests/` unittest와 ruff도 생략한다. `check_repository.py`는 링크·물결표·이미지 형식을 본다.
   ruff 는 Python·`src/`·`sim/`·`web/`·`tests/`·`tools/`·`ruff.toml` 이 안 바뀌면 생략한다.
   `web/` 이 바뀌면 `web/backend tests (pytest)` job 이 따로 돈다(`web-backend.yml`). 필수 검사는 아니다.
6. force push/삭제 방지와 bypass 범위를 확인한다. 실제 설정은 팀 합의와 권한에 맞춰 적용한다.
7. 검사기·schema·정책·agent 규칙 자체의 변경도 사람의 리뷰 대상이다.

`.github/CODEOWNERS` 는 collaborator 목록에서 확인한 handle 로 적었다(2026-09-17). 보호 경로와 다른 사람 레인만 있다.
패키지 코드 본문은 적지 않는다. 그건 아래 봇 머지 조건 안에서 들어가고 다음 날 스크럼에서 사람이 사후 검토한다.
GitHub 설정 일부는 ruleset 으로 적용돼 있다(위 [조회한 상태](#조회한-상태)). Code Owners 리뷰 필수는 켜져 있지 않다.
설정은 저장소 관리(재범, admin)가 UI에서 바꾼다.

## 봇 머지 조건

2026-09-17 결정(재범, 저장소 관리). 사람 넷이 PR 을 전부 승인하기엔 PR 이 하루 30개를 넘는다.
그래서 봇의 병합을 허용하되 아래를 **전부** 채운 PR 에만 허용한다. 하나라도 빠지면 사람이 본다.
[CONTRIBUTING 6](../../CONTRIBUTING.md) 이 이 절을 가리킨다.

| # | 조건 | 어디서 강제하나 |
| --- | --- | --- |
| 1 | 검사 초록: `Repository and evidence checks`, `Python lint (ruff)`, `CI gate`(src 변경이면 colcon L1·L2 포함) | GitHub required checks |
| 2 | 브랜치가 main 최신을 포함한다 | 봇 규칙. GitHub "up to date" 필수는 꺼져 있다(2026-09-30 조회) |
| 3 | 보호 경로(`.github/CODEOWNERS`)를 바꾸면 그 담당 사람의 승인 | 10번(봇 규칙). GitHub Code Owners 리뷰 필수는 꺼져 있다(2026-09-30 조회) |
| 4 | 교차 검증: 작성자가 아닌 쪽이 검토한다. 봇이 쓴 PR 은 봇이 아닌 쪽의 "검증" 코멘트나 사람 승인이 있어야 한다 | 봇 규칙, 사후 검토 |
| 5 | 검토 코멘트에 넷이 있어야 한다: 대조한 계약 절, PR 본문의 검증 명령과 결과 인용, 스텁 한 바퀴 L2 상태, 배선(인터페이스·launch·스텁·계약) 변경 여부 | 봇 규칙, 사후 검토 |
| 6 | 크기: 파일 10개, 400줄 이하. 넘으면 사람 | 봇 규칙 |
| 7 | merge commit 만. main 이 빨강이면 고치는 PR 이 들어갈 때까지 봇 병합 정지 | ruleset 이 merge 만 허용한다(2026-09-30 조회). 빨강 정지는 봇 규칙 |
| 8 | 사후 검토: 다음 날 스크럼 "어제 달라진 것"에서 사람이 훑는다. 문제면 24시간 안에 토론 없이 revert PR | 스크럼 틀 |
| 9 | **본문이 스스로 보류를 말하면 넣지 않는다.** 본문·최신 작성자 코멘트에 "병합 보류", "머지 보류", "Draft 유지", "L3 미검증"(합격 조건일 때), "교차검토 대기" 가 있으면 CI 가 초록이어도 넣지 않는다. 작성자나 재범이 그 문구를 거둔다는 코멘트를 달아야 한다 | 봇 규칙 |
| 10 | **보호 경로는 사람 한 마디가 있어야 넣는다.** 3번이 GitHub 설정으로 아직 강제되지 않으므로, 보호 경로를 바꾸는 PR 은 담당 사람의 APPROVE 나 재범의 머지 코멘트("머지", "전결" 등)가 있을 때만 넣는다 | 봇 규칙(설정 적용 전까지) |

9·10번은 2026-09-23 추가(재범 지시). 그날 봇이 본문에 "병합 보류(Draft)·원통 3회 L3 미검증" 이라 적힌 #490 을 CI 재실행이
초록이 되자 곧바로 넣었고(M0609 계획 미리 계산 결함, #512 로 되돌림), 판정 코멘트 없이 #501 을 넣었다(봉투 QR 이 계약과 다름, #509).

### PR 흐름: Draft 로 열고 Ready 는 한 번

2026-09-23 재범 결정. PR 에는 거의 늘 검토 댓글이 붙고 수정 커밋이 따른다. Ready 로 열면 수정마다 colcon(10분 안팎)이 다시 돈다.
Draft 에서는 무거운 검사를 건너뛴다(#497). 그래서 **Draft 로 열고 → 검토(봇·TW) → 수정 → Ready 로 한 번 바꾼다.**
Ready 에서 전체 CI 가 한 번 돌고, 봇은 Ready·초록·위 조건을 다 채운 PR 만 넣는다. 작성자는 **자기 PR 을 검토 반영 뒤 Ready 로 바꿔도 된다.**

"검토" 는 CI 초록을 옮겨 적는 것이 아니다. 5번의 넷이 없는 승인 코멘트는 검토가 아니고, 그 PR 은 사람이 본다.

#### 실제로 돈 모양 (9/24–9/30 관측)

#762 가 이 흐름을 끝까지 탄 예다. 댓글 번호는 모두 #762 의 것이다.

| 단계 | 누가 | 근거 |
| --- | --- | --- |
| 1. Draft 로 연다 | 작성자 | 타임라인에 `ready_for_review`(2026-09-27 19:52 KST)가 있다 |
| 2. 격리 검사 결과를 적는다 | 작성자 외 검사 | 5855034322 |
| 3. 문장 검토 `### [Docs Readability]` | 봇 | 5855108559 |
| 4. 반영 커밋을 올리고 SHA 를 댓글로 남긴다 | 작성자 | 5855160914(`6dc3d31`) |
| 5. Ready 로 바꾼다. 전체 CI 가 돈다 | 작성자 | 1번의 `ready_for_review` |
| 6. 기술 판정 `[검증 결과]` | 봇 | 5855229654 |
| 7. 병합하고 병합 댓글을 단다 | 봇 | 5855672756 |

- #762 는 보호 경로(`/sim/`·`/docs/architecture/`)를 바꿨다. 그 PR 에는 10번이 요구하는 담당 APPROVE 나 재범 머지 댓글이 없다. 다른 곳에 근거가 있는지는 미확인이다.
- Docs Readability 의 남은 지적(leftover)은 게이트가 아니다. 채택은 작성자가 한다. 그 댓글이 스스로 그렇게 적는다(#762 5855285859).
- 봇의 기술 판정 댓글은 사람 승인이 아니라고 스스로 적는다(#790 5884383674).
- 재범이 병합하기도 한다. #790 은 재범이 "바로 머지." 라고 쓴 뒤 병합됐다(#790 5884437467).
- 9/24 카드는 기술 판정과 병합을 봇에 맡겼다. 레인별 PR 은 파일 25개 이하로 잡았다(#576 5806300285).
  - 25개는 위 6번(파일 10개·400줄)과 다르다. 둘을 맞춘 결정은 찾지 못했다(미확인).
- 같은 날 인계 댓글은 "병합 범위 승인은 재범만 한다"고 적었다(#576 5805003612).
  9/25 인계는 머지 지시를 재범이 각 PR 에 직접 쓴다고 적었다(#576 5824235551).
- 모든 PR 이 이 모양은 아니다. #797·#798 은 Draft 를 거치지 않았다. #797 은 재범이 병합했다. #798 은 봇이 병합했다.

### 적용할 GitHub 설정 (재범, admin)

- Rules → Rulesets → `main`: Require a pull request (required approvals 0, Require review from Code Owners, Dismiss stale approvals),
  Require status checks to pass(`Repository and evidence checks`, `Python lint (ruff)`, `CI gate`), Require branches to be up to date,
  Block force pushes, Restrict deletions.
- Settings → General → Pull Requests: merge commit 만 허용(squash·rebase 해제). Automatically delete head branches.
- 확인 필요: 필수 승인 0 과 Code Owners 리뷰 필수의 조합이 UI 에서 되는지. 안 되면 이 절을 고친다.

2026-09-30 조회로 본 적용 여부다([조회한 상태](#조회한-상태)).

| 설정 | 상태 |
| --- | --- |
| PR 필수, 필수 승인 0, 옛 승인 해제 | 적용됨 |
| Code Owners 리뷰 필수 | 적용 안 됨 |
| 필수 검사 셋 | 적용됨 |
| main 최신 포함(up to date) | 적용 안 됨 |
| force push·삭제 막기 | 적용됨 |
| merge commit 만 | ruleset 으로 적용됨. 저장소 설정에는 squash·rebase 도 켜져 있다 |
| head 브랜치 자동 삭제 | 적용됨 |

공식 근거:
[GitHub 보호 브랜치](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches),
[필수 검사 문제 해결](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks).
