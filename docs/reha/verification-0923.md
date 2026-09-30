# 9/23 격리 검증 — 병원 전체 브랜치 SHA 별 build·test

> 원문 표는 2026-09-23 밤에 기록했다. 아래 "원문" 절은 고치지 않고 옮겼다.
> 이 문서는 격리 환경의 L1·L2 결과다. Isaac L3 가 아니다.

## 원문

| SHA | build | colcon test | 실패 | sim/tests |
|---|---|---|---|---|
| 289a384(hospital-full 최초 HEAD) | 7/7 | 1467, 0 fail, 2 skip | 없음 | 833 passed 44 skip |
| 8fd2492 | 7/7 | 1477, 4 fail, 2 skip | plan_cache_dir/_write_plan_cache_file 4건(아래) | 833 passed 44 skip |
| 232931c(hospital-full 당시 HEAD) | 7/7 | 1479, 4 fail, 2 skip | 8fd2492와 동일 4건, 미수정 | 834 passed 44 skip |
| 3ad7c5e | 7/7 | 진행중(부분: 1212/… , 1 error, 11 failures) — 완료 시 정정본 다시 보냄 | — | 미실행(진행중) |

실패 4건(rokey_p3_manipulation, 8fd2492부터 지속): test_module_node.py::test_guarded_retiming_uses_the_actual_stream_period[0.5]·[50.0], test_preferred_safety.py::test_preferred_mode_refuses_open_loop_before_planning → KeyError: 'plan_cache_dir'; test_reset_fence.py::test_m0609_precompute_keeps_going_when_the_inventory_moves → AttributeError: 'Precompute' object has no attribute '_write_plan_cache_file'.

workcell.json sha256 대조: master01·master02 동일 51d1177de39c2380d7623b7d18ac625787ba8eebfec7a167426afff506956e56. base.usda는 경로 임베드로 상이(m1 b8c25ad0…, m2 997786d6…).
ruff: 이 머신 미설치, 전 구간 미실행.
환경: colcon build/test는 ROS_DOMAIN_ID=77 ROS_LOCALHOST_ONLY=1 격리 worktree, sim/tests는 Isaac 비의존 50파일(python3 -m pytest, test_stage_loads.py 제외).

## 덧붙임(해석)

- 실패 4건은 `8fd2492`(계획 캐시 파일)에서 생겼다. #553 `35fb28a` 커밋 본문은 이 넷을 스텁 대역에 `plan_cache_dir` 와 캐시 파일 메서드를 더해 고쳤다고 적는다. 그 SHA 의 격리 검증은 이 표에 없다(**미실행**).
- `3ad7c5e` 행은 진행 중이다. 정정본이 오면 이 문서에 새 절로 더한다(원문 절은 고치지 않는다).
