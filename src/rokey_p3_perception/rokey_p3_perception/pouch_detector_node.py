"""손 카메라 이미지 → 봉투 검출과 QR 판독. manipulation 담당 소유, master02 에서 돈다.

계약 [배송 한 바퀴 v1](../../../docs/architecture/delivery-contract-v1.md) 2.1·2.4·3절.

- 받는 것: `/<robot>/hand_camera/image_raw`, `/<robot>/hand_camera/camera_info`, `/events`
- 내는 것: `/<robot>/hand_camera/tag_reads` (`TagRead`), `/<robot>/hand_camera/pouches`
  (`PouchDetectionArray`, **검출 0건이어도 빈 배열**), `/events` 의 `POUCH_DETECTED`
- `TagRead.kind` 는 QR 내용 접두로 정한다. 해석은 `qr_payload.py` 순수 함수다.
- `detector` 파라미터는 `yolo` 또는 `color`(폴백). YOLO 가중치는 경로 파라미터만 받는다.
  학습은 이 노드 밖(Replicator 합성 데이터)이다.

봉투까지의 거리는 봉투 실제 크기(`pouch_width_m`) 또는 고정 거리(`pouch_distance_m`)
파라미터로만 정한다. 둘 다 없으면 `pose` 를 0 으로 두고 팔이 그 검출을 쓰지 않는다.
두 값과 카메라 해상도·판독 거리는 **마스터에서 확인**한다.
"""

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge, CvBridgeError
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from rokey_p3_interfaces.msg import Event, PouchDetection, PouchDetectionArray, TagRead
from sensor_msgs.msg import CameraInfo, Image

from rokey_p3_perception import pouch_geometry as geom
from rokey_p3_perception import qr_overlay
from rokey_p3_perception import qr_payload
from rokey_p3_perception import qr_rectify
from rokey_p3_perception import read_snapshot
from rokey_p3_perception import yolo_classes

KIND_TO_MSG = {
    qr_payload.KIND_PATIENT: TagRead.KIND_PATIENT,
    qr_payload.KIND_STATION: TagRead.KIND_STATION,
    qr_payload.KIND_POUCH: TagRead.KIND_POUCH,
    qr_payload.KIND_CONTAINER: TagRead.KIND_CONTAINER,
    qr_payload.KIND_MODULE: TagRead.KIND_MODULE,
}

QOS_RELIABLE = QoSProfile(reliability=ReliabilityPolicy.RELIABLE,
                          durability=DurabilityPolicy.VOLATILE,
                          history=HistoryPolicy.KEEP_LAST, depth=10)
QOS_DETECTIONS = QoSProfile(reliability=ReliabilityPolicy.RELIABLE,
                            durability=DurabilityPolicy.VOLATILE,
                            history=HistoryPolicy.KEEP_LAST, depth=5)
QOS_SENSOR = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT,
                        durability=DurabilityPolicy.VOLATILE,
                        history=HistoryPolicy.KEEP_LAST, depth=2)
QOS_LATCHED_EVENTS = QoSProfile(reliability=ReliabilityPolicy.RELIABLE,
                                durability=DurabilityPolicy.TRANSIENT_LOCAL,
                                history=HistoryPolicy.KEEP_LAST, depth=500)


class PouchDetectorNode(Node):
    """pouch_detector 노드."""

    def __init__(self):
        super().__init__('pouch_detector')

        self.declare_parameter('robot_id', 'amr_1')
        self.declare_parameter('detector', 'color')     # 계약 2.4절: yolo 또는 color(폴백)
        self.declare_parameter('yolo_weights', '')      # 가중치 경로만 받는다. 학습은 밖에서
        self.declare_parameter('yolo_confidence', 0.25)
        # 봉투로 받을 YOLO class 이름. 비었거나 모델에 없는 이름이 있으면 YOLO 를 쓰지 않는다(fail-closed).
        self.declare_parameter('yolo_allowed_classes', [''])
        # YOLO 를 못 쓰면 color 로 넘어갈지. false 면 봉투 상자를 내지 않는다(YOLO 성능 run 에서 폴백이 섞이지 않게).
        self.declare_parameter('yolo_fallback_to_color', True)
        self.declare_parameter('qr_min_size_px', 0)     # 0 이면 거르지 않는다
        # 봉투 실제 크기와 고정 거리. 둘 다 0 이면 거리를 모른다고 본다.
        self.declare_parameter('pouch_width_m', 0.0)
        self.declare_parameter('pouch_distance_m', 0.0)
        # color 폴백의 시작값. 밝고 채도 낮은 면(흰 봉투)을 고른다. 봉투 자산 색이
        # 정해지면 마스터에서 맞춘다.
        self.declare_parameter('color_saturation_max', 60)
        self.declare_parameter('color_value_min', 120)
        self.declare_parameter('min_area_px', 400)
        # QR 하나가 봉투 하나라는 폴백. 검출기가 못 잡아도 읽힌 QR 로 봉투를 만든다.
        self.declare_parameter('pouch_from_qr', True)
        # 약통·모듈 QR 을 읽은 순간 영상 한 장을 여기에 남긴다(발표 PiP). 비우면 안 남긴다.
        self.declare_parameter('save_reads_dir', '')
        # 추론 주기 상한(Hz, 0 = 없음). 영상이 더 자주 와도 이 주기보다 가까운 프레임은 건너뛴다(재범 9/25: 5 Hz).
        # 건너뛴 프레임은 검출도 빈 배열도 내지 않는다 — 소비자는 마지막 검출의 stamp 로 신선도를 본다.
        self.declare_parameter('max_rate_hz', 0.0)
        # 상판 집기(`PICK_ATTEMPT` detail=deck) 뒤 이 시간(sim s) 동안 프레임마다 한 줄 + 초마다 한 장(save_reads_dir).
        # campaign1 a01: 상판 비전 0/13 인데 검출기 로그 0줄이라 화면 밖·반사를 가를 수 없었다. 0 이면 끈다.
        self.declare_parameter('deck_watch_s', 10.0)

        self._robot_id = self.get_parameter('robot_id').value
        self._detector = self.get_parameter('detector').value
        self._yolo_weights = self.get_parameter('yolo_weights').value
        self._yolo_confidence = float(self.get_parameter('yolo_confidence').value)
        self._yolo_allowed_names = [name for name in self.get_parameter('yolo_allowed_classes').value if name]
        self._yolo_allowed_ids = None
        self._yolo_fallback = bool(self.get_parameter('yolo_fallback_to_color').value)
        self._yolo_problem = ''
        self._qr_min_size = float(self.get_parameter('qr_min_size_px').value)
        self._pouch_width = float(self.get_parameter('pouch_width_m').value)
        self._pouch_distance = float(self.get_parameter('pouch_distance_m').value)
        self._saturation_max = int(self.get_parameter('color_saturation_max').value)
        self._value_min = int(self.get_parameter('color_value_min').value)
        self._min_area = float(self.get_parameter('min_area_px').value)
        self._pouch_from_qr = bool(self.get_parameter('pouch_from_qr').value)

        if not self.get_parameter('use_sim_time').value:
            self.get_logger().warn('use_sim_time 이 false 다. 계약 4절은 모든 노드가 sim time 이다.')

        self._bridge = CvBridge()
        self._qr = cv2.QRCodeDetector()
        self._intrinsics = None
        self._epoch = 0
        self._snapshots = read_snapshot.Snapshots(str(self.get_parameter('save_reads_dir').value))
        self._deck_watch = read_snapshot.DeckWatch(self.get_parameter('deck_watch_s').value)
        self._qr_quads = 0
        self._announced = set()
        self._yolo = None
        self.effective_detector = self._choose_detector()

        namespace = f'/{self._robot_id}'
        self._tag_pub = self.create_publisher(
            TagRead, f'{namespace}/hand_camera/tag_reads', QOS_RELIABLE)
        self._pouch_pub = self.create_publisher(
            PouchDetectionArray, f'{namespace}/hand_camera/pouches', QOS_DETECTIONS)
        self._event_pub = self.create_publisher(Event, '/events', QOS_LATCHED_EVENTS)
        # QR 추적 영상(재범 9/29, qr_overlay): 찾은 QR 마다 네 꼭짓점 사각형·판정 색. **보는 구독자가 있을 때만**
        # 그리고 낸다 — 없으면 비용 0. 웹 카메라 탭(live_sensors `*_qr`)과 촬영 창(P3_CAMERA_VIEW)이 본다.
        self._qr_view_pub = self.create_publisher(Image, f'{namespace}/hand_camera/qr_view', QOS_SENSOR)
        self._marks = []
        # 지금 집는 주문(이 로봇의 마지막 PICK_ATTEMPT). 봉투 QR 이 이것이면 초록 OK, 아니면 빨강 NOT ORDER.
        self._expected_order = ''

        self.create_subscription(Image, f'{namespace}/hand_camera/image_raw',
                                 self._on_image, QOS_SENSOR)
        self.create_subscription(CameraInfo, f'{namespace}/hand_camera/camera_info',
                                 self._on_camera_info, QOS_SENSOR)
        self.create_subscription(Event, '/events', self._on_event, QOS_LATCHED_EVENTS)

        if self._pouch_width <= 0.0 and self._pouch_distance <= 0.0:
            self.get_logger().warn(
                'pouch_width_m 과 pouch_distance_m 이 둘 다 0 이다. 거리를 모르니 '
                'pose 를 0 으로 낸다. 봉투 크기나 손 카메라 거리를 마스터에서 확인해 넣는다.')
        self.get_logger().info(f'pouch_detector up. robot={self._robot_id} detector={self._detector}')

    def _choose_detector(self):
        """실제로 쓸 검출기(`yolo`·`color`·`none`)를 정하고 기동 시 한 줄로 남긴다. 이 노드는 실행 중에 바꾸지 않는다.

        `detector=yolo` 인데 YOLO 를 못 쓰면: `yolo_fallback_to_color` 가 true 면 color(계약 2.4절 폴백),
        false 면 none(봉투 상자를 내지 않는다). 어느 쪽이든 폴백 검출이 YOLO 검출로 섞이지 않게 로그에 남긴다.
        """
        requested = self._detector
        if requested == 'yolo':
            self._yolo = self._load_yolo()
            if self._yolo is None:
                self._detector = 'color' if self._yolo_fallback else 'none'
        line = (f'effective_detector={self._detector} (requested={requested}, '
                f'reason={self._yolo_problem or "-"}, pouch_from_qr={self._pouch_from_qr})')
        if self._detector == requested:
            self.get_logger().info(line)
        elif self._detector == 'none':
            self.get_logger().error(line + ' — yolo_fallback_to_color=false 라 봉투 상자를 내지 않는다.')
        else:
            self.get_logger().warn(line + ' — color 폴백 검출은 YOLO 검출이 아니다(계약 2.4절).')
        return self._detector

    def _load_yolo(self):
        """가중치 경로를 받아 ultralytics 모델을 올린다. 못 쓰면 None 이고 이유는 `_yolo_problem`."""
        if not self._yolo_weights:
            return self._refuse('yolo_weights 가 비어 있다')
        try:
            from ultralytics import YOLO
        except ImportError as error:
            return self._refuse(f'ultralytics 가 없다: {error}')
        try:
            model = YOLO(self._yolo_weights)
        except (OSError, ValueError, RuntimeError) as error:
            return self._refuse(f'YOLO 가중치를 못 읽었다 ({self._yolo_weights}): {error}')
        return self._accept_model(model)

    def _refuse(self, problem):
        """YOLO 를 못 쓰는 이유를 남긴다. 반환이 없어 `return self._refuse(...)` 는 None 이다."""
        self._yolo_problem = problem
        self.get_logger().error(f'YOLO 를 쓰지 않는다: {problem}')

    def _accept_model(self, model):
        """허용 class 를 모델 names 에서 찾는다. 못 찾으면 None(fail-closed, color 폴백)."""
        allowed_ids, problem = yolo_classes.resolve_allowed_ids(
            getattr(model, 'names', None), self._yolo_allowed_names)
        if allowed_ids is None:
            return self._refuse(f'{problem}. 허용 class 를 모르면 검출을 봉투로 보지 않는다(fail-closed)')
        self._yolo_allowed_ids = allowed_ids
        self.get_logger().info(
            f'YOLO 허용 class {self._yolo_allowed_names} → id {sorted(allowed_ids)}')
        return model

    # ---- 수신 ----------------------------------------------------------

    def _on_camera_info(self, msg):
        """내부 파라미터. 거리 계산에 fx, fy, cx, cy 만 쓴다."""
        self._intrinsics = (msg.k[0], msg.k[4], msg.k[2], msg.k[5])

    def _on_event(self, msg):
        if msg.epoch > self._epoch:
            self._epoch = msg.epoch
        if msg.name == Event.RESET_DONE:
            self._announced.clear()
            self._expected_order = ''
        if msg.name == Event.PICK_ATTEMPT and msg.robot_id == self._robot_id:
            self._expected_order = msg.order_id
        elif (msg.name == Event.PICK_ATTEMPT and msg.detail == 'deck' and msg.robot_id == self._robot_id):
            self._deck_watch.arm(msg.order_id, msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9)

    def _on_image(self, msg):
        """이미지 한 장 → QR 판독과 봉투 검출. 검출 0건이어도 빈 배열을 낸다. `max_rate_hz` 보다 잦으면 건너뛴다."""
        stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        if geom.skip_for_rate(stamp, getattr(self, '_last_processed', None),
                              float(self.get_parameter('max_rate_hz').value)):
            return
        self._last_processed = stamp
        try:
            image = self._bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        except CvBridgeError as error:
            self.get_logger().error(f'이미지를 못 바꿨다: {error}', throttle_duration_sec=5.0)
            return

        reads = self._read_qr(image, msg.header)
        boxes = self._detect_pouches(image)
        detections = self._build_detections(msg.header, boxes, reads)

        array = PouchDetectionArray()
        array.header = msg.header
        array.detections = detections
        self._pouch_pub.publish(array)
        self._announce(detections)
        self._watch_deck(image, msg.header, stamp, reads, boxes)
        self._publish_qr_view(image, msg.header)

    def _publish_qr_view(self, image, header):
        """QR 추적 영상 한 장(`hand_camera/qr_view`). 구독자가 없으면 아무것도 안 한다. 판정에는 안 쓴다."""
        if self._qr_view_pub.get_subscription_count() == 0:
            return
        try:
            out = self._bridge.cv2_to_imgmsg(qr_overlay.draw(image, self._marks), encoding='bgr8')
        except (CvBridgeError, cv2.error, ValueError) as error:
            self.get_logger().warn(f'QR 추적 영상을 못 그렸다: {error}', throttle_duration_sec=5.0)
            return
        out.header = header
        self._qr_view_pub.publish(out)

    def _mark(self, quad, kind=None, tag_id=None):
        label, color, _state = qr_overlay.mark_for(kind, tag_id, self._expected_order)
        self._marks.append((quad, label, color))

    def _watch_deck(self, image, header, stamp, reads, boxes):
        """상판 집기 창 안이면 한 줄(찾은 QR 자리 수·읽은 봉투·상자 수·밝기) + 초마다 한 장. 판정에는 안 쓴다."""
        seen = self._deck_watch.frame(stamp)
        if seen is None:
            return
        offset, first = seen
        brightness, saturated = read_snapshot.frame_stats(image)
        order_id = self._deck_watch.order_id
        read_ids = [read_id for read_id, _quad in reads]
        self.get_logger().info(
            f'deck frame {order_id} +{offset:.2f} s sim={stamp:.2f}: QR 자리 {self._qr_quads}, '
            f'읽은 봉투 {read_ids or "-"}, 상자 {len(boxes)}, 밝기 {brightness:.0f}, 포화 {saturated:.3f}')
        if not first:
            return
        quad = next((q for read_id, q in reads if read_id == order_id), None)
        try:
            saved = self._snapshots.save(image, quad, f'deck-{order_id}-{int(offset):02d}s', header.stamp.sec,
                                         header.stamp.nanosec, self._epoch)
        except (OSError, cv2.error) as error:
            saved = None
            self.get_logger().warn(f'상판 프레임을 못 남겼다: {error}', throttle_duration_sec=5.0)
        if saved:
            self.get_logger().info(f'상판 프레임을 남겼다: {saved}')

    # ---- QR ------------------------------------------------------------

    def _read_qr(self, image, header):
        """QR 을 모두 읽어 `TagRead` 로 낸다. 반환은 봉투 QR 목록 [(order_id, 네 점)]. 추적 영상 표시는 `_marks`."""
        self._qr_quads = 0
        self._marks = []
        try:
            found, payloads, points, _ = self._qr.detectAndDecodeMulti(image)
        except cv2.error as error:
            self.get_logger().warn(f'QR 검출 실패: {error}', throttle_duration_sec=5.0)
            return []
        payloads = list(payloads) if found and points is not None else []
        points = list(points) if found and points is not None else []
        self._qr_quads = len(points)
        if not any(payloads):
            # 아무것도 못 읽었다(자리도 못 찾았을 수 있다). 키워서 한 장짜리로 한 번 더 본다(qr_rectify).
            payload, quad = qr_rectify.read_enlarged(image, self._qr)
            if payload:
                self.get_logger().info(f'QR 을 키워서 읽었다: {payload}. 한 변 {geom.quad_min_side(quad):.0f} px',
                                       throttle_duration_sec=2.0)
                payloads, points = [payload], [quad]
        if not points:
            return []

        pouches = []
        for payload, quad in zip(payloads, points, strict=False):
            size = geom.quad_min_side(quad)
            if not payload:
                # 자리는 찾았는데 못 읽었다. 네 점으로 펴서 한 번 더 읽는다(qr_rectify).
                payload = qr_rectify.reread(image, quad, self._qr)
                if payload:
                    self.get_logger().info(f'QR 을 펴서 읽었다: {payload}. 한 변 {size:.0f} px',
                                           throttle_duration_sec=2.0)
            if not payload:
                # 펴도 못 읽었다. 해상도·거리 문제의 단서라 크기를 남긴다.
                self.get_logger().warn(f'QR 을 못 읽었다(펴서 다시 읽기 포함). 한 변 {size:.0f} px',
                                       throttle_duration_sec=2.0)
                self._mark(quad)
                continue
            if self._qr_min_size > 0.0 and size < self._qr_min_size:
                continue
            kind, tag_id = qr_payload.parse_tag(payload)
            if kind is None:
                self.get_logger().warn(f'접두를 모르는 QR: {payload!r}', throttle_duration_sec=5.0)
                continue
            self._mark(quad, kind, tag_id)
            message = TagRead()
            message.header = header
            message.kind = KIND_TO_MSG[kind]
            message.tag_id = tag_id
            message.status = TagRead.STATUS_OK
            self._tag_pub.publish(message)
            if kind in (qr_payload.KIND_CONTAINER, qr_payload.KIND_MODULE):
                # 기록용 한 장. 판독 발행 **뒤**에 하고, 실패는 경고만 — 저장이 판정을 막지 않는다(#628 검토).
                try:
                    saved = self._snapshots.save(image, quad, tag_id, header.stamp.sec, header.stamp.nanosec,
                                                 self._epoch)
                except (OSError, cv2.error) as error:
                    saved = None
                    self.get_logger().warn(f'QR 판독 영상을 못 남겼다: {error}', throttle_duration_sec=5.0)
                if saved:
                    self.get_logger().info(f'QR 판독 영상을 남겼다: {saved}')
            if kind == qr_payload.KIND_POUCH:
                pouches.append((tag_id, quad))
        return pouches

    # ---- 봉투 검출 ------------------------------------------------------

    def _detect_pouches(self, image):
        """봉투 후보 사각형 [(box, confidence)]."""
        if self._detector == 'none':
            return []
        if self._detector == 'yolo' and self._yolo is not None:
            return self._detect_yolo(image)
        return self._detect_color(image)

    def _detect_yolo(self, image):
        try:
            results = self._yolo.predict(image, conf=self._yolo_confidence, verbose=False)
        except (RuntimeError, ValueError) as error:
            self.get_logger().error(f'YOLO 추론 실패: {error}', throttle_duration_sec=5.0)
            return []
        boxes, dropped = yolo_classes.filter_boxes(results, self._yolo_allowed_ids or frozenset())
        if dropped:
            self.get_logger().info(f'허용 class 밖의 YOLO 상자 {dropped}개를 버렸다.',
                                   throttle_duration_sec=5.0)
        return boxes

    def _detect_color(self, image):
        """색 폴백. 밝고 채도 낮은 덩어리를 봉투 후보로 본다."""
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array([0, 0, self._value_min], dtype=np.uint8),
                           np.array([179, self._saturation_max, 255], dtype=np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        boxes = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < self._min_area:
                continue
            x, y, width, height = cv2.boundingRect(contour)
            # 색 검출은 확률이 아니다. 면적 비를 신뢰도 자리에 넣고 1 을 넘지 않게 자른다.
            confidence = min(1.0, area / float(width * height)) if width and height else 0.0
            boxes.append(((float(x), float(y), float(x + width), float(y + height)), confidence))
        return boxes

    def _build_detections(self, header, boxes, pouch_reads):
        """검출 사각형과 봉투 QR 을 짝지어 `PouchDetection` 목록으로."""
        detections = []
        used = set()
        for box, confidence in boxes:
            order_id, yaw, matched = '', 0.0, None
            for index, (read_id, quad) in enumerate(pouch_reads):
                if index in used:
                    continue
                if geom.point_in_box(geom.box_center(geom.box_of(quad)), box):
                    order_id, yaw, matched = read_id, geom.quad_yaw(quad), quad
                    used.add(index)
                    break
            detections.append(self._detection(header, box, confidence, order_id, yaw, matched))

        if self._pouch_from_qr:
            # 검출기가 못 잡았지만 QR 은 읽힌 봉투. QR 면이 봉투 윗면이라 사각형을 그대로 쓴다.
            for index, (read_id, quad) in enumerate(pouch_reads):
                if index in used:
                    continue
                detections.append(self._detection(header, geom.box_of(quad), 1.0,
                                                  read_id, geom.quad_yaw(quad), quad))
        return detections

    def _detection(self, header, box, confidence, order_id, yaw, quad=None):
        """사각형 하나를 `PouchDetection` 으로. 거리를 모르면 pose 를 0 으로 둔다."""
        detection = PouchDetection()
        detection.header = header
        detection.order_id = order_id
        detection.confidence = float(confidence)
        detection.slot_index = -1           # 계약 2.4절: v1 은 -1 고정
        width, _ = geom.box_size(box)
        depth = geom.resolve_depth(width, self._pouch_width,
                                   self._intrinsics[0] if self._intrinsics else 0.0,
                                   self._pouch_distance)
        # 자리(영상 점)는 QR 을 읽었으면 QR 중심, 아니면 사각형 중심(`pouch_geometry.detection_pixel`).
        position = (geom.position_from_pixel(*geom.detection_pixel(box, quad), depth, self._intrinsics)
                    if self._intrinsics else None)
        if position is None:
            # 거리를 모른다. 지어내지 않는다. 팔은 0 자세를 쓰지 않는다.
            detection.pose.orientation.w = 1.0
            return detection
        detection.pose.position.x, detection.pose.position.y, detection.pose.position.z = position
        quaternion = geom.quaternion_about_z(yaw)
        (detection.pose.orientation.x, detection.pose.orientation.y,
         detection.pose.orientation.z, detection.pose.orientation.w) = quaternion
        return detection

    # ---- 이벤트 ----------------------------------------------------------

    def _announce(self, detections):
        """새로 보이기 시작한 봉투마다 `POUCH_DETECTED` 를 한 번 낸다.

        이미지마다 내면 10 Hz 로 이벤트가 쏟아진다. 계약 2.6절의 지표는 사건 하나당
        하나를 센다. 봉투가 화면에서 사라지면 다시 낼 수 있게 풀어 준다.
        """
        visible = {detection.order_id for detection in detections if detection.order_id}
        for order_id in sorted(visible - self._announced):
            message = Event()
            message.header.stamp = self.get_clock().now().to_msg()
            message.name = Event.POUCH_DETECTED
            message.order_id = order_id
            message.robot_id = self._robot_id
            message.epoch = self._epoch
            self._event_pub.publish(message)
        self._announced = visible


def main(args=None):
    """콘솔 진입점."""
    rclpy.init(args=args)
    node = PouchDetectorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
