# 증거 검토: campaign 4R 호스트 재배정 · attempt 4 · 5 의 FAIL 뒤 재시도

- 상태: verified(마1검증 확인, 원문은 PR 댓글)
- 작성자 / 작성 UTC: 발표(LOQ)-P3A3/0923 / 2026-09-27T05:32Z
- 검토자 / 검토 UTC / 승인 PR: 마1검증(LOQ)-P3A3/0923 / 2026-09-27T05:33Z / 이 PR
- 대상 run ID / protocol SHA: 4R run 은 아직 등록 전이다(이 기록이 식별 규칙을 정한다). protocol `hospital-full-acceptance-v1` sha256 `6cbd564a73388ba930ba3f72a38470e16ba4cf7a65eefde0b15f4af8854b286a`
- supersedes: [2026-09-27-jaebeom-c4-artifact-loss.md](2026-09-27-jaebeom-c4-artifact-loss.md) 의 "모집단·재현" 중 호스트와 집계 규칙. 소실 경위 · 소실 전 검증 · 재검증 불가 판단은 그대로 둔다.

## 확인 범위

- **재배정**: 2026-09-27 05:08Z(14:08 KST) 작전이 마클1 · 마클2 세션에 attempt 4 · 5 를 master02 로 옮기라고 지시했다. 근거는 작전 세션의 메시지 기록이고, #240 에 있는 근거는 마클2 첫 대체 회차 보고 5852938384(05:20:12Z)다. 사유는 부하 분산이다(마클1 GPU 과부하 보고 #240 5852682982, 04:39:54Z). 마클1 재실행 큐 취소 보고는 #240 에서 찾지 못했다(미확인).
- **재배정 전에 이미 끝난 master01 회차**(원문 대조):
  - attempt 4(폴더 150): #240 5852722207(04:47:21Z) **FAIL** — attempt_success 0, "전력 15W 구간 포함, 64분(GPU 전력 회복 중 실행)".
  - attempt 5(폴더 151): #240 5852728369(04:48:28Z) **record FAIL** — screen.mp4 104304→104304 B(60 s 동안 그대로).
- master01 4R 중 PASS 보고: attempt 1 5852242930 · 2 5852297565 · 3 5852356999 · 7 5852842255 · 8 5852962683. 14 · 15 는 아직 보고 없음.

## 모집단·재현

- **4R 호스트**: attempt 1 · 2 · 3 · 7 · 8 · 14 · 15 는 master01. attempt 4 · 5 는 master01 첫 4R 시행(FAIL) 뒤 master02 가 다시 돈다.
- **실패를 지우지 않는다**: master01 의 attempt 4 · 5 4R FAIL 도 run 으로 등록하고 분모에 넣는다. master02 의 attempt 4 · 5 는 그 FAIL 뒤의 새 시행(재시도)으로 따로 등록하고 역시 분모에 넣는다. attempt 5 의 master01 FAIL 은 aggregate --json 이 나오면 등록하고, 안 나오면 장부만 둔다.
- **식별**(앞 기록의 규칙에 호스트 · 재시도 표시를 더한다): repetition_index 는 attempt 번호, seed 7, supersedes 없음. notes 첫머리:
  - master01 4R: `campaign 4R · attempt N · host master01 · 대체 대상 <소실 run_id>`
  - master02 재시도: `campaign 4R 재시도 · attempt N · host master02 · 앞선 4R FAIL <master01 4R run_id 또는 #240 댓글 ID>`
- **attempt 16 은 대체분이 아니다.** campaign 4 에서 아직 돌지 않은 새 attempt 이고 host master02 다. notes 는 `campaign 4 · attempt 16`.
- **집계**: campaign 4 의 attempt 4 · 5 는 등록된 시행을 모두 센다(FAIL 1 + 재시도 1). 앞 기록의 "9개 attempt 는 4R 만 센다" 는 소실 원래 run 을 빼는 규칙으로 유지한다.

## 판단

- 재시도 결과를 보기 전에 정한 규칙이 없었으므로, 실패를 빼지 않고 시행을 모두 세는 쪽으로 정한다. 성공률 분모가 커지는 방향이라 결과를 좋게 보이게 하지 않는다.
- 미확인: 마클1 재실행 큐 취소 보고의 원문 ID.

## 후속

- 마클1 보충(ls -l · deployment.json · SHA256SUMS 자체 해시, 151 은 aggregate --json)을 받아 4R run 을 등록한다.
- docs/reha/campaigns.md 의 campaign 4 행을 이 기록 기준으로 고친다.
