# reference

강의 자료, 샘플 패키지, 튜토리얼처럼 **통째로 받아서 읽기만 하는 자료**를 두는 곳이다.

**Markdown 문서만 Git 에 추적된다.** 샘플 패키지, 코드, USD 씬, PDF 처럼 통째로 받은 자료는
원본이 따로 있으므로 추적하지 않는다 — 저장소에 넣으면 지워도 Git 기록에 영구히 남고 클론만 무거워진다.

배포받은 문서가 Markdown 이면 그대로 두면 팀 전체가 GitHub 에서 읽을 수 있다.
PDF·슬라이드로 받았고 팀이 같이 봐야 한다면 필요한 부분만 Markdown 으로 옮긴다.

## 하위 폴더

| 폴더 | 내용 |
| --- | --- |
| [`tutor/`](tutor/README.md) | 강사가 배포한 자료 — [최종 발표 평가 기준·PPT 체크리스트](tutor/final-presentation-evaluation.md), [9/14 평가 자료](tutor/evaluation.md), [디지털 트윈과 Isaac Sim](tutor/digital-twin-and-isaac-sim.md) |

새 폴더를 만들면 그 안에 README 를 두고 **출처·받은 날짜·원본 위치**를 적는다.
자료 자체가 추적되지 않으므로, 이게 어디서 온 무엇인지는 README 에만 남는다.

## COLCON_IGNORE

`docs/reference/COLCON_IGNORE` 는 여기 복사된 ROS 패키지를 `colcon build` 가
빌드 대상으로 잡지 않게 막는다. 빈 파일이지만 삭제하지 않는다.

## 경로를 지정해 읽기

경로와 원하는 작업을 함께 알려준다.

```text
docs/reference/tutor/ 에서 ROS 2 브릿지 예제만 찾아서 우리 설정과 뭐가 다른지 정리해줘
```
