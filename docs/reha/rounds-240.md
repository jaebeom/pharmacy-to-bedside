# 리하 회차 목록 — #240 원문 기준(G5-1)

> 설계 갭 계획 G5 의 첫 단계다([계획](../analysis/2026-09-24-design-gap-plan.md), #576 5806300285).
> 이 표는 **목록**이다. 적격 판정이 아니다. 적격 판정(실행 전 frozen protocol 대조)과 `evidence/runs` 등록은 따로 한다.
> 회차는 SHA 별·호스트별로 한 줄이다. 합치지 않는다. 예: rc2 `b40e133`(5804528593, 10/10 · touch 1)과 rc3 `953ff5c`(5805153340, 9/10 · touch 0)는 따로다.

- 범위: `docs/reha/README.md`·`reha-01`–`reha-08`·`night-0924.md` 가 가리키는 #240 댓글. 기준 main `66450ae`. 리하07 G(5806153204)·main 회차46(5807102321)·리하07 H(5807295653)는 이 목록을 만든 뒤 들어와 손으로 더했다.
- 값은 전부 #240 원문(`gh api repos/jaebeom/ROKEY_P3_A3/issues/comments/<ID>`, 2026-09-24 조회)에서 옮겼다. 리하 문서 값은 쓰지 않았다.
- 전체 SHA 는 `git rev-parse <sha>^{commit}` 로 풀었다. 원문에 나온 짧은 SHA 는 모두 40자로 풀렸다.
- 해시: "64자"는 원문에 전체 SHA-256 이 있는 경우다. "앞 16자만 보고"·"앞 12자만 보고"는 원문에 그만큼만 있다. **전체 SHA-256 은 지어내지 않았다.** 짧은 값뿐인 회차는 `verify-artifacts` 전에 원본에서 다시 계산해야 한다.
- 녹화 칸에 "원문 <ID>" 가 붙은 값은 같은 회차의 다른 #240 댓글에서 왔다. 그 댓글에 값이 있는지 대조했다(6건 모두 있음).
- #576 댓글 3개(5799587136·5801973227·5804528792)는 요약이라 행을 만들지 않았다.
- 표 1·2 의 녹화·SHA256SUMS 칸(55행)은 원문 문자열에 있는지 기계로 대조했다. 호스트·결과·원문 판정 칸은 수집 단계에서 옮겼고, 따로 대조한 것은 rc2·rc3·rc4 행뿐이다. 나머지 칸의 전수 대조는 **미실행**이다.

## 표 1 — 링크된 #240 댓글의 회차

| 리하 | #240 ID | 실행 SHA(40) | 도구 SHA(40) | 호스트 | 결과 | 원문 판정 | 원본 위치 | 녹화(이름·B·해시) | SHA256SUMS |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| reha-01 A | 5794286395 | 3b7603039a8882c1ea34759fd04b826db3b9c1dd | 원문에 없음 | master02 | 실패 | ①② 보충 `grasp_pose: 이동 실패` / ③ PICKED·LOADED / AUTH_OK / ④ `not_detected (검출 0건)` ×2 / ⑤ RETURNED 204.60, rtf 0.4대 | `~/markle_tmp/m2-hf-full-3b76030/` | 원문에 없음 | `ff69cbd46d44`(앞 12자만 보고) |
| reha-01 B | 5794286637 | 3b7603039a8882c1ea34759fd04b826db3b9c1dd(폴더 이름의 `289a384` = 289a384fc4cadb31ad387d0cf0b5885612ab73be, 관계는 원문에 없음) | 원문에 없음 | master01(IS14), 도메인 131 | 실패 | 카메라 집기 `not_detected` ×2, M0609 보충 `grasp_pose` 이동 실패 3/3. "조제·벨트 도착까지" | `~/markle_tmp/m1-hospital-full-289a384-01/` | `screen.mp4` 588 s, 크기·해시 원문에 없음 | "SHA256SUMS 482개"(해시 원문에 없음) |
| reha-02 C | 5794528230 | 35fb28ae38a8fd0cbc0560e0d3978eb74238a855 | 원문에 없음 | master02 | 실패(4/5) | ① 모듈 보충 실패 3/3 `reason=unreadable` / ②–⑤ 통과(DOCKED 253.22), rtf 0.367 | `~/markle_tmp/m2-hf-full-35fb28a/` | 원문에 없음 | `32476b67b3ed`(앞 12자만 보고) |
| reha-02 D | 5794764480 | 5cb6542a502cab629530f600e4565b02ad4698a3 | 원문에 없음 | master01(회차4) | 실패(4/5) | ord-0001 완주(ORDER_DONE·DOCKED), drug-ibu `container_refused unreadable` 3/3 | `~/markle_tmp/m1-hospital-v0-5cb6542-04/` | 원문에 없음 | 원문에 없음 |
| reha-02 E | 5795027810 | 94f19fbc3aeb429e55923e147778202bace7464c | 원문에 없음 | master02 | 실패(4/5) | ① 모듈 unreadable / ②–⑤ 통과, touch 0, rtf 0.354, stall 5 | `~/markle_tmp/m2-hf-full-94f19fb/` | 원문에 없음 | `5d586b5cfd39`(앞 12자만 보고) |
| reha-02 F | 5795175482 | 94f19fbc3aeb429e55923e147778202bace7464c(+`--rail-drive 1e5 1e4 5e4`) | 원문에 없음 | master02 | 실패(4/5) | ① 모듈 unreadable 그대로 / ②–⑤ 통과, loop stall 0, rtf 0.386 | `~/markle_tmp/m2-hf-full-94f19fb-rail/` | 원문에 없음 | `1a7a54ea57c7`(앞 12자만 보고) |
| reha-02 G | 5795355277 | 05339c910a6c1581f1e59f7d2fc654e037e3507a | 원문에 없음 | master02 | 실패(4/5) | ① 모듈 `reason=unreadable`(shelf_68·70) / ②–⑤ 통과, M0609 touch 0 | `~/markle_tmp/m2-hf-full-05339c9/` | 원문에 없음 | `58a5f2b60994`(앞 12자만 보고) |
| reha-02 부하 N=1 | 5795512558(값만 언급) | d3790421e488cfecf55d0df73bdbc79cb66867d9 | 원문에 없음 | master01 | 성공(완주) | "N=1·2·3·4 모두 완주", N=1 rtf 0.450·loop_hz 26.67. 시각 원문에 없음 | `~/markle_tmp/m1-hospital-n1-d379042-05/`(원문 표기 `n{1,2,3,4}-d379042-0{5,6,7,8}`) | 원문에 없음 | 원문에 없음 |
| reha-02 부하 N=2 | 5795435831 | d3790421e488cfecf55d0df73bdbc79cb66867d9 | 원문에 없음 | master01 | 성공(완주) | N=2 완주 21:41:54→21:52:05, rtf 0.299 | `~/markle_tmp/m1-hospital-n2-d379042-06/`(원문 표기 `n{2,3}-d379042-0{6,7}`) | `screen.mp4` 폴더에 있다고만, 크기·해시 원문에 없음 | 폴더에 있다고만, 값 원문에 없음 |
| reha-02 부하 N=3 | 5795435831 | d3790421e488cfecf55d0df73bdbc79cb66867d9 | 원문에 없음 | master01 | 성공(완주) | N=3 완주 21:53:22→22:02:03, rtf 0.318 | `~/markle_tmp/m1-hospital-n3-d379042-07/`(같은 중괄호 표기) | `screen.mp4` 폴더에 있다고만, 크기·해시 원문에 없음 | 폴더에 있다고만, 값 원문에 없음 |
| reha-02 부하 N=4 | 5795512558 | d3790421e488cfecf55d0df73bdbc79cb66867d9 | 원문에 없음 | master01 | 성공(완주) | N=4 완주 22:03:27→22:13:49, rtf 0.267 | `~/markle_tmp/m1-hospital-n4-d379042-08/`(같은 중괄호 표기) | 원문에 없음 | 원문에 없음 |
| reha-02 H | 5795627672 | f8eac1cee5f183809a4a1e41d98fd9172308d767(+`--rail-drive 1e5 1e4 5e4`) | 원문에 없음 | master02 | 성공(5/5) | **5/5**, DOCKED 235.05, M0609 touch 34줄(잡은 약통뿐), rtf 0.389, stall 1. /Amr/ touch·DELIVERED 줄 원문에 없음 | `~/markle_tmp/m2-hf-full-f8eac1c/` | `clip-2.mkv`(본편), 크기·해시 원문에 없음 | `04ec90cb9072`(앞 12자만 보고) |
| reha-02 I | 5795682106 | f8eac1cee5f183809a4a1e41d98fd9172308d767 | 원문에 없음 | master01(회차9) | 성공(5/5) | 5/5, AMR 본체 touch 0, rtf 0.444 | `~/markle_tmp/m1-hospital-v0-f8eac1c-09/` | 원문에 없음 | 원문에 없음 |
| reha-03 B | 5796429033 | 0819f800f8f96c11207e80c866a4c2aeeaa22f64 | 원문에 없음 | master02 | 성공(5/5) | ord-0005 bed_b1 5/5, /Amr/ touch 0, rtf 0.501. 감속기 100% 전환 없음 → "판정 미충족" | `~/markle_tmp/m2-hf-full-0819f80-b1/` | 원문에 없음 | 원문에 없음 |
| reha-03 A | 5796567522 | 0819f800f8f96c11207e80c866a4c2aeeaa22f64 | 원문에 없음 | master01(회차14) | 성공(5/5) | 5/5, "판정선 통과: rtf 0.683", /Amr/ touch 0, stall 0. /orders/status 기록 안 함 | `~/markle_tmp/m1-hospital-v0-0819f80-14-none/` | 원문에 없음 | 원문에 없음 |
| reha-04 | 5796814149 | 4d013333b50207ca06871a7c46acff1f2a276f78 | 원문에 없음 | master02(N=2) | 성공(5/5) | 5/5, /orders/status state 2(DELIVERED), /Amr/ touch 0, rtf 0.429. "감속기 판정 미충족" | `~/markle_tmp/m2-hf-full-4d01333-amr2/`(SUMMARY.txt) | `clip-1.mkv` 85,899,676 B `41c42289f1b8e8d6`(앞 16자만 보고, 원문 5798100488) | 원문에 없음 |
| reha-05 기준선 | 5796887254 | bfc8c384d65baad8ddd43c4eebe47101a637df64 | 원문에 없음 | master01(회차18) | 성공(5/5) | "판정선 통과: rtf 0.686", DELIVERED, AMR touch 0 | `~/markle_tmp/m1-hospital-v0-bfc8c38-18/` | 원문에 없음 | 원문에 없음 |
| reha-05 B(회차19, master01 쪽) | 5797973069 | 4d013333b50207ca06871a7c46acff1f2a276f78 | 원문에 없음 | 다중 PC: master01=stage(P3_PEER=10.10.0.2), master02=arm·nav·stack·web, 도메인 131 | 성공 | /orders/status 0→1→1→2 DELIVERED, AMR touch 0, rtf 0.711 | `~/markle_tmp/m1-multipc-stage-4d01333-19/` | 원문에 없음 | 원문에 없음 |
| reha-05 B(회차19, master02 쪽 — 위와 같은 회차) | 5797973429 | 4d013333b50207ca06871a7c46acff1f2a276f78 | 원문에 없음 | 다중 PC(위와 같음) | 성공(5/5) | 5/5, state 2(DELIVERED), /Amr/·M0609 touch 0, 감속기 50% 31줄 | `~/markle_tmp/m2-hf-multi-4d01333/` | `clip-1.mkv` 49,880,886 B `94d7c5fe2409ef3d`(앞 16자만 보고, master02 화면, 원문 5798100488) | `846330fe8443`(앞 12자만 보고) |
| reha-05 A master02 | 5798100488 | 138cbacd3b46a95e72efa93361c62ad9523b7599 | 원문에 없음 | master02 | 성공(5/5) | 5/5, state 2, /Amr/·M0609 touch 0, rtf 0.550, 단계 전환 29회 | `~/markle_tmp/m2-hf-full-138cbac/` | `clip-1.mkv` 66,588,800 B `58abb9574640dfab`(앞 16자만 보고) | `bae13c306beb`(앞 12자만 보고) |
| reha-05 A master01 | 5798652432 | 138cbacd3b46a95e72efa93361c62ad9523b7599 | 원문에 없음 | master01(회차24) | 성공(5/5) | "판정선 통과: rtf 0.676", DELIVERED, AMR touch 0, 제한 값 53번 바뀜 | `~/markle_tmp/m1-hospital-v0-138cbac-24/` | 원문에 없음 | 원문에 없음 |
| reha-06 A master02 | 5798769352 | 5a5180400d6cbf3b8f84adf00c3f35725e439f2d | 원문에 없음 | master02 | 성공(5/5) | 5/5, state 2, /Amr/ touch 0, rtf 0.446, 100% 10줄 | `~/markle_tmp/m2-hf-full-5a51804/` | `clip-1.mkv` 70,882,109 B `f410acd7aa8e20e7`(앞 16자만 보고, 원문 5800810827) | `a1ca872c42fa`(앞 12자만 보고) |
| reha-06 C `m0609_shelf` | 5798769352 | f736213e5924d582e22e6f1f7f763883fb4de078 | 원문에 없음 | master02 | 성공 | DELIVERED·touch 0·rtf 0.457 | 원문에 없음(still: `docs/presentation/stills/0924/m2-<view>.png`, 브랜치 docs/film-stills-0924 `3b86d9d`, 원문 5803000625) | 녹화 원문에 없음. still `bbcd814f060baac2`(앞 16자만 보고, 5803000625) | 원문에 없음 |
| reha-06 C `m0609_dispenser` | 5798769352 | f736213e5924d582e22e6f1f7f763883fb4de078 | 원문에 없음 | master02 | 성공 | DELIVERED·touch 0·rtf 0.451 | 원문에 없음(still 위와 같음) | 녹화 원문에 없음. still `fdad2eea6b08fd81`(앞 16자만 보고, 5803000625) | 원문에 없음 |
| reha-06 C `a1_pick` | 5798769352 | f736213e5924d582e22e6f1f7f763883fb4de078 | 원문에 없음 | master02 | 성공 | DELIVERED·touch 0·rtf 0.451 | 원문에 없음(still 위와 같음) | 녹화 원문에 없음. still `33ae0fb7889aa8e6`(앞 16자만 보고, 5803000625) | 원문에 없음 |
| reha-06 B seed 23 | 5799443133 | 138cbacd3b46a95e72efa93361c62ad9523b7599(`v2_seed:=23`) | 원문에 없음(10건 도구 `hospital_orders.py` 09c6f37 언급은 다음 회차 준비) | master02 | 성공(5/5) | 5/5, state 2, /Amr/·M0609 touch 0, rtf 0.443, DOCKED 245.22 | `~/markle_tmp/m2-hf-full-138cbac-seed23/` | 원문에 없음 | `58c5e610801b`(앞 12자만 보고) |
| reha-06 A master01 회차28 | 5799586820(+정정·녹화 5799625628) | 5a5180400d6cbf3b8f84adf00c3f35725e439f2d | 원문에 없음 | master01(회차28) | 성공(5/5) | "판정선: rtf 0.700", AMR touch 0, stall 0, DELIVERED. `여유 ≥1.80 m` 0줄→9줄로 정정(5799625628) | `~/markle_tmp/m1-hospital-v0-5a51804-28/` | `screen.mp4` 33122724 B, 390.1 s, sha256 `0b30b1b42f4d9c09dc448a10a62e8453d68c3155b375d2fa147a3e832fe9b9ca`(64자, 5799625628) | 원문에 없음 |
| night-0924 회차27 | 5799586820(언급만) | 원문에 없음(회차28 원문에 번호만 언급. night-0924 는 `5a51804` 로 적음) | 원문에 없음 | master01 | 중단 | "회차27은 boot_check record FAIL(내 ffmpeg 옵션 실수)로 따로 두었다" | 원문에 없음 | 원문에 없음 | 원문에 없음 |
| reha-07 A | 5800810827(+정정 5800823142) | 138cbacd3b46a95e72efa93361c62ad9523b7599 | 8df35138c8888d3f1f82f2968ba10a11e7dfebf1(처음 09c6f37252f9bf1519557623b20be466a5ed47da, 1건 뒤 교체) | master02 | 실패 | **FAIL 5/10 delivered**, ord-0003 held `transit_timeout`(정정: bed_a3 yaw 4분 초과), /Amr/ touch 57(ArmRiser↔SM_BedSideTable_01b3_03), rtf 0.413 | `~/markle_tmp/m2-hf-ten-138cbac/orders/summary.md` | `clip-1.mkv` 562,152,520 B `c189e6c65ef3ecb3`(앞 16자만 보고) | `d9c3f72cf671`(앞 12자만 보고) |
| reha-07 B / reha-08 B-1 | 5801263234 | 5a5180400d6cbf3b8f84adf00c3f35725e439f2d(N=2) | boot_check `c49c68b` = c49c68bee1a4131fc9913a4d59e89e415670dd31(record 확인 도구로 언급) | master02 | 성공(5/5) | 5/5, state 2, /Amr/·M0609 touch 0, rtf 0.397(≥0.35), 녹화 앞 약 3분 결손 | `~/markle_tmp/m2-hf-full-5a51804-amr2/` | `clip-1.mkv` 41,532,298 B `c62f38f6144c7742`(앞 16자만 보고, 03:48:26–03:51:12 결손) · `clip-0-closed-early.mkv` 1,396,642 B `ce8f55900a6a933d`(앞 16자만 보고) | 원문에 없음 |
| reha-07 C / reha-08 A 회차35 | 5801268218 | aca88409a8d79fd77601a5f118968ffe1b759675 | 원문에 없음 | master01(회차35) | 성공(5/5) | ord-0003→bed_a3 5/5, DELIVERED, "판정선: rtf 0.699, AMR touch 0, ArmRiser↔협탁 touch 0" | `~/markle_tmp/m1-hospital-v0-aca8840-35-bed_a3/` | `screen.mp4` 35555335 B, 425.1 s, sha256 `9e112596c808e5ab430ab3337fd9e3c0d0618d6585eb5a9c4cb5952caba319b8`(64자) | 원문에 없음 |
| reha-08 A 회차36 | 5801363458 | aca88409a8d79fd77601a5f118968ffe1b759675 | 원문에 없음 | master01(회차36) | 성공(5/5) | ord-0001→bed_a1 5/5, DELIVERED, "판정선: rtf 0.663, AMR touch 0, ArmRiser touch 0" | `~/markle_tmp/m1-hospital-v0-aca8840-36-bed_a1/` | `screen.mp4` 35451797 B, 417.1 s, sha256 `fcf7a7dda546a9ef85fef1895989b8fe3316c0728eb4a0878b2096baf5996223`(64자) | 원문에 없음 |
| reha-06 B 회차38 | 5801936313 | aca88409a8d79fd77601a5f118968ffe1b759675(+`P3_V2_SEED=23`) | 원문에 없음 | master01(회차38) | 성공(5/5) | 5/5, DELIVERED, rtf 0.669, AMR touch 0, ArmRiser 0. draw=1 `stale_epoch` 1/3 실패 뒤 재시도 허용 | `~/markle_tmp/m1-hospital-v0-aca8840-seed23-38/` | `screen.mp4` 36249724 B, 435.8 s, sha256 `77d6491c48c2edc850ee74b75acf2e0d93086b90930e577e641423cd1f6d0e77`(64자) | 원문에 없음 |
| reha-08 B-2 | 5801972839 | 5a5180400d6cbf3b8f84adf00c3f35725e439f2d(N=2 재현, 04:14:47) | 원문에 없음 | master02 | 성공(5/5) | 5/5·DELIVERED·/Amr/ touch 0·rtf 0.392·100% 9줄, "N=2 재현 2/2", 녹화 완전 | 원문에 없음 | `clip-1.mkv` 89,053,524 B `66f5be79b0d9260e`(앞 16자만 보고) | 원문에 없음 |
| reha-08 A master02 | 5801972839 | aca88409a8d79fd77601a5f118968ffe1b759675(ord-0001 N=1, 04:27:23) | 원문에 없음 | master02 | 성공(5/5) | 5/5·DELIVERED·touch 0·ArmRiser 접촉 0·rtf 0.444 | 원문에 없음 | `clip-1.mkv` 66,190,574 B `4f98beeb53367a62`(앞 16자만 보고) | 원문에 없음 |
| reha-06 B 회차40 | 5802558111 | 68dd3511dc330b3791d50fb6e147457cdc18510d | 원문에 없음 | master01(회차40) | 성공(5/5) | 5/5, DELIVERED, rtf 0.712, AMR touch 0, ArmRiser 0. 진열 seed=7. 모듈 보충 3번째 성공 | `~/markle_tmp/m1-hospital-v0-68dd351-40/` | `screen.mp4` 37305547 B, 463.1 s, sha256 `d2a1d11d263f3f0a3b22965198e14bbcf66c4704ad416086aea595f6f4937e4e`(64자) | 원문에 없음 |
| reha-08 C 회차41 | 5802664758 | aca88409a8d79fd77601a5f118968ffe1b759675(+`P3_AMR_COUNT=2`) | 원문에 없음 | master01(회차41) | 성공(5/5) | "촬영 2대 판정 통과: rtf 0.645(≥0.35)", AMR touch 0, ArmRiser 0, DELIVERED | `~/markle_tmp/m1-hospital-n2-aca8840-41/` | `screen.mp4` 35556693 B, 426.1 s, sha256 `ffbe9464fca6715da00070f24e77015db1ea80f9f980d77c80ea91b55db50302`(64자) | 원문에 없음 |
| reha-07 D | 5802751527 | 50b658a302aa822eaedb552fd748a990fda6fa56 | b1f018b9e14f0e2ec4dcfa9b6ece6c7f90f2ecd9 | master02 | 실패 | **FAIL 7/10 delivered**, ord-0003 `transit_not_arrived`(nav2_status_6), 0009·0010 `pool_exhausted`, ArmRiser 0, /Amr/ touch 2, rtf 0.379 | `~/markle_tmp/m2-hf-ten-50b658a/orders/summary.md` | `clip-1.mkv` 409,645,983 B `f5ffc1f19fa78e47`(앞 16자만 보고) | `8d07666f39c9`(앞 12자만 보고) |
| reha-07 E | 5804528593 | b40e133011948eeb8c13dd6001704c024058d142(rc2) | b1f018b9e14f0e2ec4dcfa9b6ece6c7f90f2ecd9 | master02 | 성공(도구 판정) | **`# 병원 주문 판정 — PASS (10/10 delivered)`**, /Amr/ touch 1(mesh_5↔SM_BedSideTable_01b2_04 impulse 310.53), rtf 0.367 | `~/markle_tmp/m2-hf-ten-b40e133/orders/summary.md` | `clip-1.mkv` 552,474,957 B `6ef91db2bd66de6a`(앞 16자만 보고) | `076158c086c3`(앞 12자만 보고) |
| reha-07 F | 5805153340 | 953ff5c653831ad8d357a34eaeef3c5fdefa87b8(rc3) | b1f018b9e14f0e2ec4dcfa9b6ece6c7f90f2ecd9 | master02 | 실패 | **FAIL 9/10 delivered**, ord-0009 held `not_detected` ×2, base↔협탁 접촉 0, /Amr/ touch 0, rtf 0.357 | `~/markle_tmp/m2-hf-ten-953ff5c/orders/summary.md` | `clip-1.mkv` 576,762,863 B `a65fa22e32467c71`(앞 16자만 보고) | `f4b8130b6e60`(앞 12자만 보고) |
| reha-07 G | 5806153204 | 090a976dc1d0cb61c506142de4d8e5e2757f09c8(rc4) | b1f018b9e14f0e2ec4dcfa9b6ece6c7f90f2ecd9 | master02 | 실패 | **FAIL 4/10**, `v2-05-room`(0005–0007) timeout `trip_limit`, `ord-0007` 벨트 끝 1405 s 대기, 0008 accepted 에서 멈춤, 0009–0010 미실행, /Amr/ touch 0, rtf 0.360 | `~/markle_tmp/m2-hf-ten-090a976/orders/summary.md` | `clip-1.mkv` 491,887,175 B `04863ec2f9d09b96`(앞 16자만 보고) | `d21618219438`(앞 12자만 보고) |
| 회차46(main) | 5807102321 | 66450ae5cb40d1216504bf11fb37f047c6939fca | 원문에 없음 | master01 | 성공 | 5/5 · DELIVERED · rtf 0.698 · AMR touch 0 · ArmRiser 0 · 낙하 0 · boot_check OK | `~/markle_tmp/m1-rc-66450ae-46/` | `screen.mp4` 37,804,616 B `d413a4d8d1dbde5772e75afbab8ba88170d582730e2899b947fb8957d2d9fcd3`(64자) | 원문에 없음 |
| reha-07 H | 5807295653 | c95e8f71200f89c079d2d2d31660195a40be4c50(rc5) | b1f018b9e14f0e2ec4dcfa9b6ece6c7f90f2ecd9 | master02 | 실패 | **FAIL 8/10**, `ord-0009` aborted `not_ready`(배출 응답 10 s 시한 초과 ×3), `ord-0010` 900 s 멈춤, /Amr/ touch 0, rtf 0.345 | `~/markle_tmp/m2-hf-ten-c95e8f7/orders/summary.md` | `clip-1.mkv` 544,666,531 B `3527a92608fa2fdf`(앞 16자만 보고) | `dcd6697a8359`(앞 12자만 보고) |
| reha-07 I | 5808852884 | af7835078290159dab9bc72adb88dcbc6d81a8aa(main + #660) | b1f018b9e14f0e2ec4dcfa9b6ece6c7f90f2ecd9 | master02 | 성공 | **`# 병원 주문 판정 — PASS (10/10 delivered)`**, /Amr/ touch 0, 배출 실패 0, rtf 0.360 | `~/markle_tmp/m2-hf-ten-af78350/orders/summary.md` | `clip-1.mkv` 405,829,580 B `aab7f2cbcf98b006`(앞 16자만 보고, 15 fps) | `bd4e3cdb2326`(앞 12자만 보고) |

## 표 2 — 링크는 없고 문서 본문에 ID 만 적힌 #240 댓글의 회차(범위 밖, 참고로 같은 방식 추출)

문서(`reha-02` J 표·`reha-06`·`night-0924`)가 링크 없이 숫자 ID 로만 가리킨 #240 댓글이다. 같은 원문 규칙으로 옮겼다.

| 리하 | #240 ID | 실행 SHA(40) | 도구 SHA(40) | 호스트 | 결과 | 원문 판정 | 원본 위치 | 녹화(이름·B·해시) | SHA256SUMS |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| reha-02 J | 5795783225 | e9b949886a1f4e039670b59bcd4fa2aead080954(+rail-drive) | 원문에 없음 | master02 | 실패 | ④ `PickPouch ord-0001: not_detected (검출 0건, 맞는 QR 없음)`, ① 모듈 보충 없음, /Amr/ touch 0, rtf 0.423 | `~/markle_tmp/m2-hf-full-e9b9498-B/` | 원문에 없음 | `1bb12fd0ced3`(앞 12자만 보고) |
| reha-02 J 회차10 | 5795827276 | f8eac1cee5f183809a4a1e41d98fd9172308d767 | 원문에 없음 | master01(회차10) | 성공(5/5) | 5/5, AMR touch 0, rtf 0.435, "f8eac1c는 2/2 완주" | `~/markle_tmp/m1-hospital-v0-f8eac1c-10/` | 원문에 없음 | 원문에 없음 |
| reha-02 J | 5795978282 | 5a10c794c6416b82825775bc3c058377539a0523(+rail-drive) | 원문에 없음 | master02 | 성공(5/5) | 5/5, /Amr/ touch 0, rtf 0.357, 감속기 "판정선 미충족", /orders/status 수집 미실행 | `~/markle_tmp/m2-hf-full-5a10c79/` | 녹화는 잠금 화면뿐(콘솔 잠김), 크기·해시 원문에 없음 | `21d844ae5b8d`(앞 12자만 보고) |
| reha-02 J 회차11 | 5796069792 | 5a10c794c6416b82825775bc3c058377539a0523(+rail-drive) | 원문에 없음 | master01(회차11) | 실패(touch) | 5/5 완주(ORDER_DONE 22:39:57), AMR 본체 touch 2. render-every 조건과 회차 번호의 짝은 원문에 없음 | 원문에 없음 | 원문에 없음 | 원문에 없음 |
| reha-02 J 회차12 | 5796069792 | 5a10c794c6416b82825775bc3c058377539a0523(+rail-drive) | 원문에 없음 | master01(회차12) | 실패(touch) | 5/5 완주(ORDER_DONE 22:47:30), AMR 본체 touch 2. 두 회차 값은 rtf 0.690(render-every 2)·0.418(없음) | 원문에 없음 | 원문에 없음 | 원문에 없음 |
| reha-02 J | 5796264039 | 5a10c794c6416b82825775bc3c058377539a0523(+`P3_AMR_COUNT=2`) | 원문에 없음 | master02 | 실패 | ④ `not_detected (검출 0건)`, rtf 0.290(판정 0.35 미달), /Amr/ touch 2 | `~/markle_tmp/m2-hf-full-5a10c79-amr2/` | 원문에 없음 | `0ff6ec484820`(앞 12자만 보고) |
| reha-06 곁 회차25 | 5798773260 | c35a0563e72edce68a8237e13a19c6de6ce96921 | 원문에 없음 | master01(회차25) | 성공(5/5) | 5/5, DELIVERED, touch 0, rtf 0.676, WARN 0 | 원문에 없음 | 원문에 없음 | 원문에 없음 |
| night-0924 회차26 | 없음 | 원문에 없음 | 원문에 없음 | master01 | 누락(결번) | 원문에 없음(night-0924: "25 → 27 로 건너뛰었다") | 원문에 없음 | 원문에 없음 | 원문에 없음 |
| night-0924 회차29 | 5799708416 | 5a5180400d6cbf3b8f84adf00c3f35725e439f2d(+`P3_V2_SEED=11`) | f60afa0247926902a132e45c77f60d4fc947b7d6(boot_check "tools f60afa0") | master01(회차29) | 성공(5/5) | "판정선: rtf 0.678", AMR touch 0, DELIVERED | `~/markle_tmp/m1-hospital-v0-5a51804-seed11-29/` | `screen.mp4` 33943338 B, 400.1 s, sha256 `ab274c1fd2a7789f01a52e880a30b53452e06240492470552bd5f607cc9c2300`(64자) | 원문에 없음 |
| night-0924 회차30 | 5799861453 | ad2aaa92237f162854e4f375918c0f15fe255c58 | 원문에 없음 | master01(회차30) | 성공(5/5) | "판정선 통과: rtf 0.672, AMR touch 0, `끊겼다` 0줄", DELIVERED | `~/markle_tmp/m1-hospital-v0-ad2aaa9-30/` | `screen.mp4` 33001323 B, 391.4 s, sha256 `00a7d51aa4ca0825a6b2140c16018ff5ca6db60a95b3b3a545157e91769d8f05`(64자) | 원문에 없음 |
| night-0924 회차31 | 5799937654 | 8e63d371c378452d7c4861edd9a8010187e205d3 | 원문에 없음 | master01(회차31) | 실패 | 카메라 집기 흡착점-봉투 0.057 m > 한도 0.04, `grasp_failed ×2 → ABORT`, touch 0, rtf 0.670 | `~/markle_tmp/m1-hospital-cam-8e63d37-31/` | `screen.mp4` 22188050 B, 268.5 s, sha256 `dc149628758f942b4f137a46252e598bdb5373d5d633d39a6a96e02e9903b585`(64자) | 원문에 없음 |
| night-0924 회차32 | 5800028169 | 5a5180400d6cbf3b8f84adf00c3f35725e439f2d(새 clone) | 원문에 없음 | master01(회차32) | 중단 | `[boot_check] FAIL window — 회차 중단`, 주문 전 멈춤, 막힌 줄 13 | `~/markle_tmp/m1-fresh-clone-5a51804-32/`(BLOCKERS.md) | 폴더에 있다고만, 크기·해시 원문에 없음 | 폴더에 있다고만, 값 원문에 없음 |
| night-0924 회차33 | 5800180626 | 5a5180400d6cbf3b8f84adf00c3f35725e439f2d(새 clone + P3_BROWSER·P3_SCREEN_SIZE) | 원문에 없음 | master01(회차33) | 실패(4/5) | "결과 4/5", 모듈 보충 3/3 `reason=stale_epoch`, DELIVERED, touch 0, rtf 0.643 | `~/markle_tmp/m1-fresh-clone-5a51804-33/` | `screen.mp4` 43335534 B, 520.0 s, sha256 `c7caa2b8aa4a7d1314f482e859e3be5cef8c385d1acd3dcd0ad91be8bd937d45`(64자) | 원문에 없음 |
| night-0924 회차34 | 5800360786 | d6b88b1d7a6a1c676d4c91e380d61ba44162735f | bd417aa6233ffcbee15fdbfc6643252df35e8537(boot_check "tools bd417aa") | master01(회차34) | 성공(5/5) | 5/5, DELIVERED, rtf 0.684, AMR touch 0, stale_epoch 0줄 | `~/markle_tmp/m1-hospital-v0-d6b88b1-34/` | `screen.mp4` 42548978 B, 515.1 s, sha256 `1641ad29cff7d6b1b29c95e68357cdf2b5233878d45a308e3cad08fae17eecf3`(64자) | 원문에 없음 |
| night-0924 회차37 | 5801755473 | aca88409a8d79fd77601a5f118968ffe1b759675(Play/Stop) | 원문에 없음 | master01(회차37) | 실패 | 첫 주문 5/5·DELIVERED, Stop 뒤 AMR physics view 멈춤, 두 번째 주문 /orders/status 0(PENDING)에서 멈춤, AMR touch 0 | `~/markle_tmp/m1-playstop-aca8840-37/` | `screen.mp4` 113981246 B, 1336.7 s, sha256 `1d368ad3ad89537c2bc51e5f576f4bde04cb53b23fff8eb7676dbdd5367f1916`(64자) | 원문에 없음 |
| night-0924 회차39 | 5802419185 | 79a0800ab1e808de24c55e180d996db6d5fe0300(Play/Stop) | 원문에 없음 | master01(회차39) | 성공 | 주문1·주문2 모두 5/5, /orders/status 0,1,1,2,0,1,1,2, AMR touch 0, ArmRiser 0, rtf 0.660 | `~/markle_tmp/m1-playstop-79a0800-39/` | `screen.mp4` 66498712 B, 791.8 s, sha256 `699ff99a0d2bf1b8a361f9d540773f61e143648f91eaadb9120a137776ea182f`(64자) | 원문에 없음 |
| night-0924 회차42 | 5802983288 | 45223b7bf12b1997ad11dcbce28233e05ca6a3d6(`--view floor_top`) | 원문에 없음 | master01(회차42) | 성공(5/5) | 5/5, DELIVERED, rtf 0.698, AMR touch 0, ArmRiser 0 | `~/markle_tmp/m1-film-45223b7-42-floor_top/` | `screen.mp4` 34479893 B, 413.3 s, sha256 `3f8f7fbe05a11c66396642fe8545ecd0984d0f9faf2448db4d497850bf28b677`(64자). still-isaac.png `731846f18eb3b14f2d5970b407400950fe9d07c77bc93872fd0bb9a43219e0e9`, still-full.png `5081a87304f231403c4ecf28bbf6c61dc29b3cd192eb1d1dc3b9756a0dfe5040`(64자, 크기 원문에 없음) | 원문에 없음 |
| night-0924 회차43 | 5803300388 | 45223b7bf12b1997ad11dcbce28233e05ca6a3d6(`amr_chase`) | 원문에 없음 | master01(회차43) | 성공(5/5) | 5/5, DELIVERED, AMR touch 0, ArmRiser 0, rtf 0.650 | `~/markle_tmp/m1-film-45223b7-4{3,4,5}-*/`(회차별 정확한 폴더 이름 원문에 없음) | 녹화 43110220 B, 425.0 s, `d6f516a319ff999c…`(앞 16자만 보고). still-isaac.png `c4448d58c397ac02023599e85b9c26f1a3ffaef9d3371a267499581fce5a435b`(64자) | 원문에 없음 |
| night-0924 회차44 | 5803300388 | 45223b7bf12b1997ad11dcbce28233e05ca6a3d6(`bed_a1`) | 원문에 없음 | master01(회차44) | 성공(5/5) | 5/5, DELIVERED, AMR touch 0, ArmRiser 0, rtf 0.668 | 위와 같음 | 녹화 40909993 B, 414.1 s, `fa00e4c21a8fb871…`(앞 16자만 보고). still `8b3b7f3591b3db7dbaf42bc77ae316fe44749f34574fadc49c50e5eb92aa4846`(64자) | 원문에 없음 |
| night-0924 회차45 | 5803300388 | 45223b7bf12b1997ad11dcbce28233e05ca6a3d6(`a1_pick`) | 원문에 없음 | master01(회차45) | 성공(5/5) | 5/5, DELIVERED, AMR touch 0, ArmRiser 0, rtf 0.676 | 위와 같음 | 녹화 38545488 B, 413.3 s, `c0169946ed9dab18…`(앞 16자만 보고). still `30fa53cd58b729b41c02ad643b28a114842ec5c0617bb0fc128f749ba18c23a9`(64자) | 원문에 없음 |

본문 ID 가운데 회차가 아닌 것: 5790278911(#527 재범 결정), 5797408402(#576 판정선·계획), 5796165837(#240 정정, 5a10c79 touch 원인), 5799625628(회차28 정정·녹화, 표 1 회차28 행에 반영), 5803000625(f736213 still 해시, 표 1 reha-06 C 행에 반영).

## 풀지 못한 SHA

- 없음. 원문에 나온 짧은 SHA 35개(실행·도구·boot_check·폴더 이름 `289a384`·문서의 `232931c`·`ae8b0b9`)가 모두 origin/main 작업 트리에서 추가 fetch 없이 40자로 풀렸다.
- SHA 자체가 원문에 없는 회차: night-0924 회차27(원문은 번호만 언급), 회차26(결번, 원문 없음).

## 원문과 리하 문서가 다른 곳

> master01 녹화 전체 SHA-256 은 [recordings-master01.md](recordings-master01.md)(master01 표, 50행)에 있다. 이 목록의 master01 녹화 짧은 해시는 모두 그 표의 앞자리와 맞는다. 그 표로 회차26 을 고쳤다. 결번이 아니다. `bfc8c38` 실패 시도다. 회차27 SHA 는 `5a51804` 다(night-0924).

> 9/24 재범 결정으로 아래 1–7 을 원문대로 정정했다. 각 자리에 "정정(9/24 …): 옛 문구" 를 남겼다(supersedes). 7 은 문서가 원문 로그와 맞다. 문구를 두었다. 덧붙임 문구를 함께 적었다.

1. **README 회차 목록 리하02 행** — "`DELIVERED` 다. AMR touch 0 전부다" 라고 적었다. 원문 5795627672(f8eac1c master02)에는 /Amr/ touch 값과 DELIVERED 줄이 없다(M0609 touch 34줄만 있다). reha-02 J 표도 이 두 값을 미보고로 적는다.
2. **README 회차 목록 리하06 행** — "master02 녹화는 대기다" 라고 적었다. 원문 5800810827 에 5a51804 녹화가 있다(`clip-1.mkv` 70,882,109 B `f410acd7aa8e20e7`). reha-06 본문에는 반영됐다.
3. **reha-06 C(f736213 master02 캡처 셋)** — 캡처 파일·sha256 을 "보고되지 않았다" 로 적었다. 원문 5803000625 에 still 세 장의 sha256 앞 16자가 있다(`bbcd814f060baac2`·`fdad2eea6b08fd81`·`33ae0fb7889aa8e6`). night-0924 는 이 ID 를 적었다.
4. **night-0924 회차27** — "주문 전에 멈췄다" 라고 적었고 SHA 를 `5a51804` 로 적었다. 원문 5799586820 은 "회차27은 boot_check record FAIL(내 ffmpeg 옵션 실수)로 따로 두었다" 뿐이다. 멈춘 시점과 SHA 는 원문에 없다.
5. **night-0924 master02 `953ff5c`(rc3) 행** — "진행 중 / 대기" 라고 적었다. 원문 5805153340 은 **FAIL 9/10 delivered** 다(reha-07 F 는 반영했다). 원문보다 먼저 쓴 문서다.
6. **reha-02 J 회차11·12** — 회차11 을 render-every 2(rtf 0.690), 회차12 를 렌더 인자 없음(rtf 0.418)으로 짝지었다. 원문 5796069792 는 두 조건의 값만 주고 회차 번호와 짝짓지 않는다.
7. **reha-06 `68dd351` 회차40** — 문서는 "빈 칸 4칸 중 3칸이 다르다" 라고 적었다. 원문 덧붙임(5802558111)은 "빈 칸 4개 다름" 이다. 원문 두 empty 목록을 대조하면 `shelf_72/r0c1` 이 겹친다. 문서 쪽이 원문 로그 줄과 맞고, 덧붙임 문구와는 다르다.

원문에 근거가 없는 문서 값(불일치로 세지 않음):
- night-0924 회차26 "결번" — 해당 원문이 없다.
- reha-06 C "master01 셋(회차21–23)과 합쳐 여섯 바퀴" — 회차21–23 원문이 범위 안 댓글에 없다.
- night-0924 master02 `138cbac` 10건 시각 "01:5x–03:5x" — 시작 시각이 원문 5800810827 에 없다.
- reha-02 D "rtf 0.45 · 기동 38 s" — 문서 스스로 "요약, 원문에는 없다" 로 표시했다.

## 원문 댓글이 없는 회차(문서·원문에 언급만)

- `232931c`(232931cfbdd636d269302aee440ff52cd8ee4da7) master02·master01 두 회차 — reha-02 A·B. 요약만 있고 #240 원문 없음.
- `ae8b0b9`(ae8b0b9e3093683669fcb48cd75feab6444d39df) master01 회차3 — 5794764480 덧붙임에 "검출 0건, P3_SIM_SENSORS=1 누락" 으로만 언급.
- `35fb28a` 재현 `-r2` — 5794528230 에 "지금 기동" 예고만 있고 결과 원문 없음.
- master01 카메라 집기 회차17·20 — 5799937654 덧붙임에 언급만.
- master01 회차21–23(f736213 캡처) — reha-06 C 에 언급만.
- reha-01 이전 회차(bb3ac33·248b80b·603dfc1·41725ff·41725ff-cam0·c482ac0·39fc30b·4ef1cb4) — 5794286395 덧붙임에 "#584 reha-01·실습44(#572) 요약" 으로만 언급. 리하 문서에는 없다.
