"""L1: YOLO class 거르기(순수). ultralytics 없이 가짜 상자로 본다."""

from types import SimpleNamespace

from rokey_p3_perception.yolo_classes import filter_boxes, resolve_allowed_ids


def box(class_id, xyxy=(1.0, 2.0, 3.0, 4.0), conf=0.9):
    """ultralytics Boxes 한 줄 흉내: cls·conf 는 길이 1 배열, xyxy[0].tolist()."""
    return SimpleNamespace(cls=[class_id], conf=[conf], xyxy=[SimpleNamespace(tolist=lambda: list(xyxy))])


def result(*boxes):
    return SimpleNamespace(boxes=list(boxes))


def test_allowed_names_resolve_to_the_model_ids():
    assert resolve_allowed_ids({0: 'person', 1: 'pouch'}, ['pouch']) == (frozenset({1}), '')
    assert resolve_allowed_ids(['pouch', 'person'], ['pouch']) == (frozenset({0}), '')      # 목록이면 인덱스가 id
    assert resolve_allowed_ids({0: 'pouch', 3: 'pouch'}, ['pouch']) == (frozenset({0, 3}), '')


def test_unusable_configurations_fail_closed():
    for names, allowed in (({0: 'pouch'}, []), ({0: 'pouch'}, ['']), ({0: 'pouch'}, None),
                           ({0: 'person'}, ['pouch']), ({0: 'pouch'}, ['pouch', 'typo']),
                           ({}, ['pouch']), (None, ['pouch'])):
        ids, problem = resolve_allowed_ids(names, allowed)
        assert ids is None and problem, (names, allowed)


def test_filter_keeps_only_allowed_classes_and_counts_the_rest():
    results = [result(box(1, (10, 20, 30, 40), 0.8), box(0)), result(box(1.0, conf=0.5), box(7))]
    kept, dropped = filter_boxes(results, frozenset({1}))
    assert kept == [((10.0, 20.0, 30.0, 40.0), 0.8), ((1.0, 2.0, 3.0, 4.0), 0.5)]
    assert dropped == 2


def test_boxes_without_a_readable_class_are_dropped():
    no_cls = SimpleNamespace(conf=[0.9], xyxy=[SimpleNamespace(tolist=lambda: [1, 2, 3, 4])])
    empty_cls = SimpleNamespace(cls=[], conf=[0.9], xyxy=[SimpleNamespace(tolist=lambda: [1, 2, 3, 4])])
    kept, dropped = filter_boxes([result(no_cls, empty_cls)], frozenset({0}))
    assert kept == [] and dropped == 2


def test_empty_allowed_set_keeps_nothing():
    kept, dropped = filter_boxes([result(box(0), box(1))], frozenset())
    assert kept == [] and dropped == 2


def test_results_without_boxes_are_empty():
    assert filter_boxes([SimpleNamespace(), SimpleNamespace(boxes=None)], frozenset({0})) == ([], 0)
