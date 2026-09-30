"""YOLO 검출의 class 거르기. ROS·ultralytics 를 import 하지 않는다.

허용 class 는 이름으로만 받는다(`yolo_allowed_classes` 파라미터). 이름·ID 를 코드에 박지 않는다.
ID 는 모델이 가진 `names`({id: 이름})에서 찾는다. 모델이 바뀌면 ID 도 바뀔 수 있기 때문이다.

fail-closed: 허용 class 가 비었거나, 모델에 없는 이름이 하나라도 있으면 그 모델을 쓰지 않는다.
노드는 그때 YOLO 를 올리지 않고 color 폴백으로 돈다. 그래서 그 검출은 YOLO 검출로 나가지 않는다.
"""


def resolve_allowed_ids(names, allowed):
    """모델 `names` 와 허용 이름 목록 → (허용 ID frozenset, 문제 설명). 쓸 수 없으면 ID 는 None.

    names 는 {id: 이름} 사전이나 이름 목록(인덱스 = id) 둘 다 받는다(ultralytics 는 사전).
    """
    wanted = [name for name in (allowed or ()) if name]
    if not wanted:
        return None, 'yolo_allowed_classes 가 비어 있다'
    if isinstance(names, dict):
        table = {int(key): str(value) for key, value in names.items()}
    elif names:
        table = dict(enumerate(str(value) for value in names))
    else:
        return None, '모델에 class 이름(names)이 없다'
    by_name = {}
    for class_id, name in table.items():
        by_name.setdefault(name, set()).add(class_id)
    missing = [name for name in wanted if name not in by_name]
    if missing:
        return None, f'모델에 없는 class: {missing}. 모델 names={sorted(set(table.values()))}'
    return frozenset(class_id for name in wanted for class_id in by_name[name]), ''


def filter_boxes(results, allowed_ids):
    """ultralytics 결과 → ([((x0, y0, x1, y1), confidence)], 버린 상자 수). 허용 class 만 남긴다.

    `box.cls` 가 없거나 읽을 수 없는 상자도 버린다(모르는 것은 허용이 아니다).
    """
    kept, dropped = [], 0
    for result in results:
        for box in getattr(result, 'boxes', None) or []:
            class_id = _class_of(box)
            if class_id is None or class_id not in allowed_ids:
                dropped += 1
                continue
            x0, y0, x1, y1 = (float(value) for value in box.xyxy[0].tolist())
            kept.append(((x0, y0, x1, y1), float(box.conf[0])))
    return kept, dropped


def _class_of(box):
    try:
        return int(box.cls[0])
    except (AttributeError, IndexError, TypeError, ValueError):
        return None
