# tutor

강사가 배포한 자료를 그대로 두는 곳이다.

**Markdown 문서는 추적되고, 나머지(패키지·코드·USD·PDF)는 추적되지 않는다**(`.gitignore` 의 `docs/reference` 규칙).
받은 자료마다 아래 표에 한 줄씩 추가한다. 추적되지 않는 자료는 이 표가 유일한 단서다.

| 받은 날짜 | 폴더·파일명 | 내용 | 원본 위치 |
| --- | --- | --- | --- |
| 2026-09-14 | [`evaluation.md`](evaluation.md) | 과제 평가 기준 (100점 만점) | 강사 배포 |
| 2026-09-14 | [`digital-twin-and-isaac-sim.md`](digital-twin-and-isaac-sim.md) | 디지털 트윈 개념, Isaac Sim 을 쓰는 이유 | 강사 배포 (이미지 미포함) |
| 2026-09-22 | [`final-presentation-evaluation.md`](final-presentation-evaluation.md) | 최종 발표 팀 평가 기준 (110점)과 PPT·영상 제작 체크리스트. 1-3절은 평가 기준, 4-8절은 작성 가이드·제안 | 사용자 제공 평가표 이미지 2장 (대화 첨부, 배포일 미확인) |

최종 PPT·발표 영상 제작 시 [최종 발표 평가 기준](final-presentation-evaluation.md)을 적용한다.
9/14 자료는 과거 자료로 보존하며, 당시 개인별 조직 역량 점수를 이번 팀 평가 110점에 합산하지 않는다.

## 쓰는 법

받은 폴더를 통째로 여기 복사한다. 이름은 바꾸지 않는다 — 강사가 다시 언급할 때
같은 이름으로 찾을 수 있어야 한다.

```bash
cp -r ~/Downloads/<받은폴더> docs/reference/tutor/
```

PDF·슬라이드로 받았고 팀이 같이 봐야 하는 문서라면 필요한 부분만 Markdown 으로 옮긴다.
그래야 GitHub 에서 바로 읽히고 갱신본과 무엇이 달라졌는지 diff 로 보인다.

내용 중 팀이 같이 논의해야 할 것이 나오면 이슈로 올린다.

원본을 수정하지 않는다. 고쳐서 쓸 일이 생기면 복사본을 만들고 어디를 왜 바꿨는지 적는다.
