# 증거 검토: campaign 4 master01 원본 소실(attempt 1–5 · 7 · 8 · 14 · 15)

- 상태: verified(마1검증 확인, 원문은 PR 댓글)
- 작성자 / 작성 UTC: 발표(LOQ)-P3A3/0923 / 2026-09-27T01:42Z
- 검토자 / 검토 UTC / 승인 PR: 마1검증(LOQ)-P3A3/0923 / 2026-09-27T01:46Z / 이 PR
- 대상 run ID / protocol SHA: `20260926T190122Z-master01-c43e8bab`(1) · `20260926T191125Z-master01-3c6b99c2`(2) · `20260926T192139Z-master01-c08aa37c`(3) · `20260926T193043Z-master01-edda5e0d`(4) · `20260926T193946Z-master01-05b55fba`(5) · `20260926T195812Z-master01-ea621829`(7) · `20260926T201646Z-master01-7ffc39ca`(8) · `20260926T202703Z-master01-6bce4dce`(14) / protocol `hospital-full-acceptance-v1` sha256 `6cbd564a73388ba930ba3f72a38470e16ba4cf7a65eefde0b15f4af8854b286a`. attempt 15 는 run 으로 등록하지 않았다.
- supersedes: 없음

## 확인 범위

- **소실 전 확인**: 마1검증이 병합 전에 master01 원본으로 `verify-artifacts` 를 돌려 8건 모두 artifact 6개씩 sha256 · 크기 일치를 확인했다 — #729 5849258022(attempt 1–4), #731 5849633005(attempt 5 · 7 · 8 · 14). code.commit `a4b1a4e` · outcome succeeded · seed 7 · phase 정의 일치도 그 판정에 있다.
- **소실**: 2026-09-27 09:40:44–10:02:55 KST 에 마클1의 `serial-controller.sh` 재작성 버그가 campaign 4 폴더 147–155(04:01–05:37 KST 에 정상 완료 · 유효 보고 #240 5850526866)를 다시 실행해 up.log · boot_check.txt · events 등을 덮어썼다(#240 5851662212). 재작성에서 "이미 있는 폴더는 mkdir · 복사만 건너뛴다" 로 고쳤지만, m1-chain.sh 는 목록 전체를 그대로 실행했다. 새 실행은 9개 모두 `boot_check FAIL exit=5`(record) 였다. 로봇 · 시뮬 결함이 아니라 관측자 스크립트 · 녹화기 정리 문제다(원문).
- **이후**: 위 8개 run 의 artifact 는 원본 키와 같은 바이트로 남아 있지 않다. **`verify-artifacts` 로 다시 확인할 수 없다.**

## 모집단·재현

- campaign 4 master01 등록 run 8건은 지우지도 고치지도 않는다(append-only). 소실 전 확인은 위 두 판정 댓글이 근거다.
- **master01 campaign 4 의 9건(1–5 · 7 · 8 · 14 · 15)은 재실행분으로 대체한다(작전 결정).**
- **재실행 run 의 식별 방식**(evidence.py 규칙 안):
  - 새 시행이라 **supersedes 를 걸지 않는다.** supersedes 는 같은 시행의 기록 정정 전용이고, 원본 artifact 를 유지해야 하는데 원본이 없다.
  - protocol v1 · seed 7 · host master01 · code `a4b1a4e` 는 원래 attempt 와 같다. **repetition_index 는 대체하는 attempt 번호와 같다.** created_at 은 재실행 시각이라 원래 run 보다 늦다.
  - notes 첫머리를 `campaign 4R · attempt N · 대체 대상 <원래 run_id>`(attempt 15 는 `대체 대상 없음(미등록)`)로 쓴다.
- **집계 규칙**: campaign 4 의 성공률 · 합계는 위 9개 attempt 에 대해 **4R run 만 센다.** 원래 run 8건은 "소실 전 검증, 이후 재검증 불가" 로 남기고 분모에 두 번 넣지 않는다. 재실행에서 FAIL 이 나오면 그 FAIL 을 센다. 원래 PASS 로 바꾸지 않는다.

## 판단

- 소실 전 8건은 그 시점에 원본과 일치가 확인됐다(마1검증). 그러나 지금은 원본으로 재현 · 재확인할 수 없어 **새 증거로 인용하지 않는다.** 발표 · 장부의 campaign 4 수치는 4R run 으로 채운다.
- 마1검증 스팟체크: attempt 1(\`c43e8bab\`) deployment.json 이 검증 당시 해시 \`75ca86b4…\` 와 지금 로컬 \`9e71110c…\` 로 달라, 덮어쓰기가 독립적으로 확인됐다.
- 미확인: 덮어쓴 새 실행에서 screen.mp4 등 녹화 파일도 바뀌었는지는 원문이 파일별로 적지 않았다. 필요하면 마클1이 폴더 해시를 다시 대조한다.

## 후속

- 마클1 재발 방지(원문): 완료 폴더는 실행 목록에서 뺀다. 정지 승인 요청 뒤 응답 전에 상태를 다시 확인한다.
- docs/reha/campaigns.md 의 campaign 4 행을 4R 기준으로 고친다(재실행 뒤).
