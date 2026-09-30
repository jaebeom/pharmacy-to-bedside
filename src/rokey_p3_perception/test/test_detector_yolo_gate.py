"""L1: pouch_detector 의 검출기 선택. ROS 없이 노드 메서드를 빌려 돈다.

- 기본값 color 경로와 YOLO 가 없을 때의 color 폴백은 이 PR 전과 같다(고정).
- detector=yolo 인데 허용 class 를 못 정하면 모델을 쓰지 않는다(fail-closed → color 폴백, 로그).
- 실제로 쓴 검출기는 기동 시 한 줄(`effective_detector=… (requested=…, reason=…)`)과 속성으로 남는다.
- `yolo_fallback_to_color=false` 면 YOLO 를 못 쓸 때 color 로 넘어가지 않고 봉투 상자를 내지 않는다.
ultralytics 는 설치하지 않는다. 필요한 곳은 가짜 모듈·가짜 모델로 대신한다.
cv2·cv_bridge 가 없는 곳에서는 그 이름으로 대역을 넣고, 이 모듈의 시험이 끝나면 뺀다(실제 모듈이 있으면 넣지 않는다).
검출기 선택 시험은 `_detect_color` 를 표지 대역으로 바꿔 cv2 없이 돈다. 실제 색 검출 결과를 보는 시험 하나는
실제 cv2 가 필요하다. skip 하지 않는다 — cv2 가 없는 환경에서는 실패로 드러난다.
"""

import importlib
import importlib.util
import sys
import types

import numpy as np
import pytest

BORROWED = ('_detect_pouches', '_detect_yolo', '_detect_color', '_load_yolo', '_accept_model', '_refuse',
            '_choose_detector')


class _StubType(type):
    def __getattr__(cls, name):
        if name.startswith('__'):
            raise AttributeError(name)
        if name.isupper():
            return f'{cls.__name__}.{name}'
        nested = _StubType(name, (), {'__init__': lambda self, *a, **k: None})
        setattr(cls, name, nested)
        return nested


def _types(name):
    module = types.ModuleType(name)

    def make(attr):
        if attr.startswith('__'):
            raise AttributeError(attr)
        stub = _StubType(attr, (), {'__init__': lambda self, *a, **k: None})
        setattr(module, attr, stub)
        return stub

    module.__getattr__ = make
    return module


def _fakes():
    fakes = {}

    def missing(name):
        return importlib.util.find_spec(name) is None

    if missing('rclpy'):
        fakes['rclpy'] = types.ModuleType('rclpy')
        fakes['rclpy.node'] = _types('rclpy.node')
        fakes['rclpy.qos'] = _types('rclpy.qos')
    if missing('cv2'):
        fakes['cv2'] = _types('cv2')
    if missing('cv_bridge'):
        fakes['cv_bridge'] = _types('cv_bridge')
    if missing('rokey_p3_interfaces'):
        fakes['rokey_p3_interfaces'] = types.ModuleType('rokey_p3_interfaces')
        fakes['rokey_p3_interfaces.msg'] = _types('rokey_p3_interfaces.msg')
    if missing('sensor_msgs'):
        fakes['sensor_msgs'] = types.ModuleType('sensor_msgs')
        fakes['sensor_msgs.msg'] = _types('sensor_msgs.msg')
    return fakes


@pytest.fixture(scope='module')
def detector_module():
    fakes = _fakes()
    added = [name for name in fakes if name not in sys.modules]
    for name in added:
        sys.modules[name] = fakes[name]
    try:
        yield importlib.import_module('rokey_p3_perception.pouch_detector_node')
    finally:
        if added:
            for name in added + ['rokey_p3_perception.pouch_detector_node']:
                sys.modules.pop(name, None)


class _Logger:
    def __init__(self):
        self.lines = []

    def __getattr__(self, level):
        return lambda text, **kwargs: self.lines.append((level, text))


def harness(module, detector='color', weights='', allowed=(), fallback=True):
    node = type('DetectorHarness', (), {n: getattr(module.PouchDetectorNode, n) for n in BORROWED})()
    node.logger = _Logger()
    node.get_logger = lambda: node.logger
    node._detector = detector
    node._yolo = None
    node._yolo_weights = weights
    node._yolo_confidence = 0.25
    node._yolo_allowed_names = list(allowed)
    node._yolo_allowed_ids = None
    node._yolo_fallback = fallback
    node._yolo_problem = ''
    node._pouch_from_qr = True
    node._saturation_max = 60
    node._value_min = 120
    node._min_area = 400.0
    return node


COLOR = [((1.0, 2.0, 3.0, 4.0), 0.5)]              # color 경로가 불렸다는 표지


def color_marked(node):
    """`_detect_color` 를 표지 대역으로. 불린 횟수를 센다."""
    node.color_calls = 0

    def detect_color(image):
        node.color_calls += 1
        return list(COLOR)

    node._detect_color = detect_color
    return node


def white_pouch_image():
    """어두운 바탕에 밝고 채도 낮은 사각형 하나(color 폴백이 찾는 모양)."""
    image = np.zeros((120, 160, 3), dtype=np.uint8)
    image[30:70, 40:100] = (230, 230, 230)
    return image


class _Box:
    def __init__(self, class_id, xyxy, conf):
        self.cls, self.conf = [class_id], [conf]
        self.xyxy = [types.SimpleNamespace(tolist=lambda: list(xyxy))]


class _Model:
    def __init__(self, names, boxes=()):
        self.names = names
        self._boxes = list(boxes)
        self.calls = 0

    def predict(self, image, conf, verbose):
        self.calls += 1
        return [types.SimpleNamespace(boxes=self._boxes)]


# 기본 경로 고정 -----------------------------------------------------------------

def test_default_color_detector_finds_the_bright_low_saturation_blob(detector_module):
    node = harness(detector_module)
    boxes = node._detect_pouches(white_pouch_image())
    assert [box for box, _conf in boxes] == [(40.0, 30.0, 100.0, 70.0)]
    assert 0.0 < boxes[0][1] <= 1.0


def test_yolo_selected_without_a_model_uses_color(detector_module):
    # 생성자가 YOLO 를 못 올리면 _yolo 는 None 이다. 그때 _detect_pouches 는 color 로 간다(이 PR 전과 같다).
    node = color_marked(harness(detector_module, detector='yolo'))
    assert node._detect_pouches(white_pouch_image()) == COLOR and node.color_calls == 1


def test_load_yolo_without_weights_returns_none(detector_module):
    node = harness(detector_module, detector='yolo', weights='', allowed=['pouch'])
    assert node._load_yolo() is None


# fail-closed -------------------------------------------------------------------

@pytest.mark.parametrize('allowed, names', [
    ([], {0: 'pouch'}),
    (['pouch'], {0: 'person', 1: 'bottle'}),
    (['pouch', 'typo'], {0: 'pouch'}),
    (['pouch'], None),
])
def test_model_without_resolvable_allowed_classes_is_refused_and_logged(detector_module, allowed, names):
    node = harness(detector_module, detector='yolo', weights='w.pt', allowed=allowed)
    assert node._accept_model(_Model(names)) is None
    assert node._yolo_allowed_ids is None
    assert any(level == 'error' and 'fail-closed' in text for level, text in node.logger.lines)


def test_load_yolo_refuses_a_loaded_model_without_allowed_classes(detector_module, monkeypatch):
    fake = types.ModuleType('ultralytics')
    fake.YOLO = lambda path: _Model({0: 'person'})
    monkeypatch.setitem(sys.modules, 'ultralytics', fake)
    node = harness(detector_module, detector='yolo', weights='w.pt', allowed=[])
    assert node._load_yolo() is None                        # 생성자는 이때 color 폴백으로 바꾼다


def test_yolo_keeps_only_allowed_class_boxes(detector_module, monkeypatch):
    model = _Model({0: 'person', 1: 'pouch'},
                   [_Box(0, (0, 0, 10, 10), 0.99), _Box(1, (5, 6, 25, 26), 0.7)])
    fake = types.ModuleType('ultralytics')
    fake.YOLO = lambda path: model
    monkeypatch.setitem(sys.modules, 'ultralytics', fake)
    node = harness(detector_module, detector='yolo', weights='w.pt', allowed=['pouch'])
    node._yolo = node._load_yolo()
    assert node._yolo is model and node._yolo_allowed_ids == frozenset({1})
    assert node._detect_pouches(white_pouch_image()) == [((5.0, 6.0, 25.0, 26.0), 0.7)]
    assert model.calls == 1


def test_yolo_without_resolved_ids_emits_nothing(detector_module):
    # 방어선: 어떤 경로로든 허용 id 없이 모델이 붙어 있으면 상자를 하나도 내지 않는다.
    node = harness(detector_module, detector='yolo')
    node._yolo = _Model({0: 'pouch'}, [_Box(0, (0, 0, 10, 10), 0.9)])
    assert node._detect_pouches(white_pouch_image()) == []


# 실제 검출기 기록과 strict 모드 ---------------------------------------------------

def effective_lines(node):
    return [(level, text) for level, text in node.logger.lines if text.startswith('effective_detector=')]


def test_color_request_reports_color_once(detector_module):
    node = color_marked(harness(detector_module))
    assert node._choose_detector() == 'color'
    assert effective_lines(node) == [('info', 'effective_detector=color (requested=color, reason=-, '
                                               'pouch_from_qr=True)')]
    for _ in range(3):
        assert node._detect_pouches(white_pouch_image()) == COLOR
    assert len(node.logger.lines) == 1                     # 매 프레임 로그 없음


def test_yolo_fallback_to_color_is_reported_with_the_reason(detector_module):
    node = color_marked(harness(detector_module, detector='yolo', weights='', allowed=['pouch']))
    assert node._choose_detector() == 'color'
    (level, text), = effective_lines(node)
    assert level == 'warn'
    assert text.startswith('effective_detector=color (requested=yolo, reason=yolo_weights 가 비어 있다')
    assert node._detect_pouches(white_pouch_image()) == COLOR


def test_strict_mode_publishes_no_boxes_when_yolo_is_unusable(detector_module, monkeypatch):
    fake = types.ModuleType('ultralytics')
    fake.YOLO = lambda path: _Model({0: 'person'})
    monkeypatch.setitem(sys.modules, 'ultralytics', fake)
    node = color_marked(harness(detector_module, detector='yolo', weights='w.pt', allowed=['pouch'], fallback=False))
    assert node._choose_detector() == 'none'
    (level, text), = effective_lines(node)
    assert level == 'error' and text.startswith('effective_detector=none (requested=yolo, reason=모델에 없는 class')
    assert node._yolo is None
    assert node._detect_pouches(white_pouch_image()) == []          # color 로 넘어가지 않는다
    assert node.color_calls == 0


def test_usable_yolo_is_reported_as_yolo(detector_module, monkeypatch):
    fake = types.ModuleType('ultralytics')
    fake.YOLO = lambda path: _Model({0: 'pouch'})
    monkeypatch.setitem(sys.modules, 'ultralytics', fake)
    for fallback in (True, False):
        node = harness(detector_module, detector='yolo', weights='w.pt', allowed=['pouch'], fallback=fallback)
        assert node._choose_detector() == 'yolo'
        assert effective_lines(node) == [('info', 'effective_detector=yolo (requested=yolo, reason=-, '
                                                   'pouch_from_qr=True)')]
