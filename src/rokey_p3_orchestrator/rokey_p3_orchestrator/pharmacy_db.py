"""약 DB. sqlite3 파일 하나. ROS 를 import 하지 않는다.

계약: docs/architecture/qr-db-camera-contract-v1.md 2절 (proposed).

- QR 에는 ID 만 있고, 정보는 여기서 찾는다. 쓰는 쪽은 orchestrator 프로세스 하나다.
- 시드는 pharmacy_catalog.yaml·dispenser.yaml·order_pool.yaml 이다. 약통의 약품·유통기한·수량·위치는
  dispenser.yaml 이 원본이고, 카탈로그는 cn- ID 와 입고일만 붙인다.
- 리셋(reseed)은 약통·모듈·봉투 표를 시드로 되돌린다. 스캔 기록은 지우지 않는다(epoch 열로 구분).
- 만료 기준일은 today 다. 벽시계를 쓰지 않는다.
- 재고 판단(FEFO·임계값)은 dispenser_inventory 가 한다. 여기는 조회와 기록만 한다.
  런타임 재고 변화(배출·보충)를 이 표에 옮기는 것은 노드 배선 PR 에서 한다.
"""

import re
import sqlite3
import threading
from datetime import date

from rokey_p3_orchestrator import order_pool
from rokey_p3_orchestrator.dispenser_inventory import InventoryError, load_inventory

SCHEMA = """
CREATE TABLE IF NOT EXISTS drug (
  item_id TEXT PRIMARY KEY, name TEXT, ingredient TEXT, strength TEXT, form TEXT, storage TEXT,
  high_risk INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS container (
  container_id TEXT PRIMARY KEY, item_id TEXT NOT NULL REFERENCES drug(item_id), lot_id TEXT UNIQUE NOT NULL,
  expiry TEXT NOT NULL, count INTEGER NOT NULL, location TEXT NOT NULL, status TEXT NOT NULL, received TEXT);
CREATE TABLE IF NOT EXISTS module (
  module_id TEXT PRIMARY KEY, item_id TEXT NOT NULL REFERENCES drug(item_id), count INTEGER NOT NULL,
  source_container TEXT REFERENCES container(container_id), location TEXT, status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pouch (
  order_id TEXT PRIMARY KEY, item_id TEXT NOT NULL REFERENCES drug(item_id), quantity INTEGER NOT NULL,
  container_id TEXT, lot_id TEXT, patient_id TEXT NOT NULL, bed TEXT NOT NULL, urgent INTEGER NOT NULL,
  prescription_id TEXT, dose_timing TEXT, due TEXT, issued_stamp REAL, picker TEXT, received_by TEXT);
CREATE TABLE IF NOT EXISTS pouch_status (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT NOT NULL REFERENCES pouch(order_id), status TEXT NOT NULL,
  stamp REAL,
  epoch INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS scan (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, robot TEXT NOT NULL, zone_id TEXT, stamp REAL, epoch INTEGER NOT NULL,
  payload TEXT NOT NULL, kind TEXT, expected TEXT, result TEXT NOT NULL);
"""

# 리셋 때 시드로 되돌리는 표. 스캔 기록은 들어가지 않는다.
SEED_TABLES = ('pouch_status', 'pouch', 'module', 'container', 'drug')

# 계약 1절. 형식 판정의 원본은 rokey_p3_perception/qr_payload.py 다(order_pool 과 같은 이유로 다시 쓴다).
_ID = re.compile(r'^[a-z0-9][a-z0-9_-]{0,63}$')
CONTAINER_ID = re.compile(r'^cn-[0-9]{4}$')
MODULE_ID = re.compile(r'^md-[0-9]{4}$')

KIND_POUCH = 'pouch'
KIND_PATIENT = 'patient'
KIND_STATION = 'station'
KIND_CONTAINER = 'container'
KIND_MODULE = 'module'

STATUS_IN_USE = 'in_use'
STATUS_STANDBY = 'standby'
STATUS_EXPIRED = 'expired'
STATUS_RECALLED = 'recalled'
_SEED_STATUSES = (STATUS_STANDBY, STATUS_RECALLED)

SCAN_OK = 'ok'
SCAN_UNKNOWN_ID = 'unknown_id'
SCAN_BAD_FORMAT = 'bad_format'
SCAN_EXPIRED = 'expired'
SCAN_MISMATCH = 'mismatch'
SCAN_RECALLED = 'recalled'

_CONTAINER_OWN = ('item_id', 'expiry', 'count', 'location', 'status')


class CatalogError(ValueError):
    """시드가 계약 2절의 규칙을 어겼다. 노드는 기동을 거부한다."""


def classify(payload):
    """QR 내용 → (종류, ID). 형식이 틀리면 (None, None). ID 는 DB 키와 같은 문자열이다."""
    text = (payload or '').strip()
    if not _ID.match(text):
        return None, None
    if order_pool.is_order_id(text):
        return KIND_POUCH, text
    if CONTAINER_ID.match(text):
        return KIND_CONTAINER, text
    if MODULE_ID.match(text):
        return KIND_MODULE, text
    for prefix, kind in ((order_pool.PATIENT_PREFIX, KIND_PATIENT), (order_pool.STATION_PREFIX, KIND_STATION)):
        if text.startswith(prefix) and len(text) > len(prefix):
            return kind, text[len(prefix):]
    return None, None


def _rows(catalog, key):
    """카탈로그의 목록 항목. 없으면 빈 목록. 원소가 mapping 이 아니면 CatalogError."""
    rows = catalog.get(key) or []
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise CatalogError(f'{key} 는 mapping 의 목록이어야 한다')
    return rows


def _count(value, label):
    try:
        count = int(value)
    except (TypeError, ValueError):
        raise CatalogError(f'{label}: count 는 정수여야 한다. 받은 값 {value!r}') from None
    if count < 0:
        raise CatalogError(f'{label}: count 는 0 이상이어야 한다')
    return count


def _iso_date(value, label):
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError:
        raise CatalogError(f'{label}: 날짜는 YYYY-MM-DD 여야 한다. 받은 값 {value!r}') from None


def _dispenser_lots(dispenser):
    """dispenser.yaml 의 로트 → (약품, 유통기한, 수량, 위치). 재고 규칙 검사는 load_inventory 가 한다."""
    try:
        load_inventory(dispenser)
    except InventoryError as exc:
        raise CatalogError(f'dispenser.yaml: {exc}') from None
    lots = {}
    for item_id, rows in dispenser['items'].items():
        for row in rows:
            lots[str(row['lot_id'])] = (item_id, str(row['expiry']), int(row['count']),
                                        f'slot_{str(row["slot"]).lower()}')
    for item_id, rows in (dispenser.get('shelf') or {}).items():
        for row in rows:
            lots[str(row['lot_id'])] = (item_id, str(row['expiry']), int(row['count']), 'shelf')
    return lots


def build_seed(catalog, dispenser, pool, today=None, require_dispenser_lots=True):
    """세 시드를 읽어 표에 넣을 행으로 바꾼다. 규칙을 어기면 CatalogError. DB 를 건드리지 않는다.

    `require_dispenser_lots=False` 면 재고 파일과 카탈로그의 로트가 어긋나도 받는다. 현장 재고 파일
    (시연용 dispenser_refill.yaml 등)이 카탈로그와 다른 로트를 쓸 때 노드가 쓴다.
    - 재고 파일의 로트에 cn- ID 가 없으면: 그 로트는 약통 표에 없다(`missing_lots`).
    - 카탈로그가 재고 파일에 없는 로트를 **이름만** 가리키면(약품·유통기한 등을 안 적은 줄): 그 줄을 건너뛴다
      (`unmatched_catalog`). 제 값을 다 적은 줄(선반 약통·회수품)은 그대로 들어간다.
    """
    if not isinstance(catalog, dict):
        raise CatalogError('카탈로그 최상위는 mapping 이어야 한다')
    today = _iso_date(today if today is not None else catalog.get('today'), 'today')

    drugs = catalog.get('drugs')
    if not isinstance(drugs, dict) or not drugs:
        raise CatalogError('drugs 는 비어 있지 않은 mapping 이어야 한다')
    drug_rows = []
    for item_id, row in drugs.items():
        if not order_pool.is_bare_id(item_id) or not isinstance(row, dict):
            raise CatalogError(f'drugs.{item_id}: 접두 없는 약품 ID → mapping 이어야 한다')
        if 'high_risk' not in row:
            raise CatalogError(f'drugs.{item_id}: high_risk 가 없다')
        drug_rows.append((item_id, row.get('name'), row.get('ingredient'), row.get('strength'),
                          row.get('form'), row.get('storage'), int(bool(row['high_risk']))))

    lots = _dispenser_lots(dispenser)
    unknown_items = sorted({item for item, *_ in lots.values()} - set(drugs))
    if unknown_items:
        raise CatalogError(f'dispenser.yaml 의 약품이 drugs 에 없다: {unknown_items}')

    container_rows = []
    unmatched = []
    seen_ids, seen_lots = set(), set()
    items_of = {}
    for row in _rows(catalog, 'containers'):
        container_id, lot_id = row.get('container_id'), row.get('lot_id')
        if not isinstance(container_id, str) or not CONTAINER_ID.match(container_id):
            raise CatalogError(f'약통 ID 는 cn-0000 형식이어야 한다. 받은 값 {container_id!r}')
        if not isinstance(lot_id, str) or not lot_id.strip():
            raise CatalogError(f'{container_id}: lot_id 가 비어 있다')
        if container_id in seen_ids or lot_id in seen_lots:
            raise CatalogError(f'{container_id}: 약통 ID 나 로트가 두 번 나온다')
        seen_ids.add(container_id)
        seen_lots.add(lot_id)
        received = _iso_date(row['received'], container_id) if row.get('received') else None
        if lot_id in lots:
            # 회수 표시는 재고 파일에 없는 정보라 여기서만 붙인다. 나머지는 dispenser.yaml 이 정한다.
            doubled = [field for field in _CONTAINER_OWN if field in row
                       and not (field == 'status' and row['status'] == STATUS_RECALLED)]
            if doubled:
                raise CatalogError(f'{container_id}: {doubled} 는 dispenser.yaml 이 정한다. 여기 적지 않는다'
                                   f'(status 는 recalled 만 적을 수 있다)')
            item_id, expiry, count, location = lots[lot_id]
            status = row.get('status') or (STATUS_IN_USE if location.startswith('slot_') else STATUS_STANDBY)
        elif not require_dispenser_lots and not any(field in row for field in _CONTAINER_OWN):
            unmatched.append(container_id)          # 재고 파일 로트를 가리키던 줄. 현장 재고 파일에는 그 로트가 없다
            continue
        else:
            missing = [field for field in _CONTAINER_OWN if field not in row]
            if missing:
                raise CatalogError(f'{container_id}: dispenser.yaml 에 없는 로트라 {missing} 를 적어야 한다')
            item_id, location, status = row['item_id'], row['location'], row['status']
            count = _count(row['count'], container_id)
            expiry = row['expiry']
            if item_id not in drugs:
                raise CatalogError(f'{container_id}: 모르는 약품 {item_id!r}')
            if status not in _SEED_STATUSES:
                raise CatalogError(f'{container_id}: status 는 {list(_SEED_STATUSES)} 중 하나다')
        expiry = _iso_date(expiry, container_id)
        if status != STATUS_RECALLED and expiry < today:
            status = STATUS_EXPIRED
        items_of[container_id] = item_id
        container_rows.append((container_id, item_id, lot_id, expiry, count, location, status, received))
    missing_lots = sorted(set(lots) - seen_lots)
    if missing_lots and require_dispenser_lots:
        raise CatalogError(f'dispenser.yaml 의 로트에 cn- ID 가 없다: {missing_lots}')

    module_rows = []
    seen_modules = set()
    for row in _rows(catalog, 'modules'):
        module_id = row.get('module_id')
        if not isinstance(module_id, str) or not MODULE_ID.match(module_id):
            raise CatalogError(f'모듈 ID 는 md-0000 형식이어야 한다. 받은 값 {module_id!r}')
        if module_id in seen_modules:
            raise CatalogError(f'{module_id}: 모듈 ID 가 두 번 나온다')
        seen_modules.add(module_id)
        if row.get('item_id') not in drugs:
            raise CatalogError(f'{module_id}: 모르는 약품 {row.get("item_id")!r}')
        source = row.get('source_container')
        if source is not None and source not in seen_ids:
            raise CatalogError(f'{module_id}: 모르는 약통 {source!r}')
        if source in unmatched:
            source = None                         # 현장 재고 파일에서 빠진 약통이다. 출처 연결만 비운다
        if source is not None and items_of[source] != row['item_id']:
            raise CatalogError(f'{module_id}: 약품 {row["item_id"]} 와 출처 약통 {source} 의 약품 '
                               f'{items_of[source]} 가 다르다')
        module_rows.append((module_id, row['item_id'], _count(row.get('count', 0), module_id), source,
                            row.get('location'), STATUS_STANDBY))

    try:
        orders = order_pool.load_pool(pool)
    except order_pool.PoolError as exc:
        raise CatalogError(f'order_pool.yaml: {exc}') from None
    pouch_rows = []
    for order in orders:
        if order.item_id not in drugs:
            raise CatalogError(f'{order.order_id}: 모르는 약품 {order.item_id!r}')
        # 봉투 하나 = 한 알. 약통·로트·발행 시각은 배출할 때 채운다.
        pouch_rows.append((order.order_id, order.item_id, 1, None, None, order.patient_id, order.bed,
                           int(order.mode == 'urgent'), None, None, None, None, None, None))

    return {'today': today, 'drug': drug_rows, 'container': container_rows, 'module': module_rows,
            'pouch': pouch_rows, 'missing_lots': missing_lots, 'unmatched_catalog': unmatched}


class PharmacyDb:
    """약 DB. open 하면 모든 표를 비우고 시드로 채운다(run 마다 새로 만든다)."""

    def __init__(self, path, seed):
        self.path = path
        self._seed = seed
        self.today = seed['today']
        # 노드는 MultiThreadedExecutor 에서 서비스·리셋이 다른 스레드로 온다. 연결 하나를 잠금으로 나눠 쓴다.
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute('PRAGMA foreign_keys = ON')
        self._db.executescript(SCHEMA)
        with self._db:
            self._db.execute('DELETE FROM scan')
            self._fill()

    def close(self):
        self._db.close()

    def _fill(self):
        for table in SEED_TABLES:
            self._db.execute(f'DELETE FROM {table}')
        for table in reversed(SEED_TABLES[1:]):
            rows = self._seed[table]
            if rows:
                marks = ', '.join('?' * len(rows[0]))
                self._db.executemany(f'INSERT INTO {table} VALUES ({marks})', rows)

    def reseed(self):
        """리셋(계약 6절 3). 약통·모듈·봉투를 시드로 되돌린다. 스캔 기록은 남긴다."""
        with self._lock, self._db:
            self._fill()

    def check_container(self, container_id, robot, epoch, current_epoch, cell_id=None, stamp=None):
        """보충 전 장착 여부(계약 2.3, `CheckContainer`). (허용, 이유). 스캔은 결과와 함께 한 줄 남긴다.

        - 다른 epoch 의 요청은 거부한다(`stale_epoch`). 기록은 남긴다.
        - epoch 0 은 "아직 epoch 를 못 봤다" 로 보고 현재 epoch 로 받는다(`/sim/reset` 요청과 같은 규칙).
          팔은 epoch 0 으로 시작해 `/events` 를 받아야 올린다 — 기동 직후 첫 보충이 이벤트보다 먼저면 0 이다
          (회차33 5a51804: 모듈 보충 3/3 `stale_epoch`, 뒤 원통은 ok).
        - 약통 QR 형식이 아니면 `bad_format`, DB 에 없으면 `unknown_id`, 만료·회수면 그 이유다.
        """
        text = (container_id or '').strip()
        with self._lock:
            kind, _key = classify(text)
            if kind != KIND_CONTAINER:
                reason = SCAN_BAD_FORMAT
                self._insert_scan(robot, cell_id, stamp, epoch, text, kind, None, reason)
                return False, reason
            if int(epoch) not in (0, int(current_epoch)):
                self._insert_scan(robot, cell_id, stamp, epoch, text, kind, None, 'stale_epoch')
                return False, 'stale_epoch'
            allowed, reason = self.can_mount(text)
            self.record_scan(text, robot=robot, epoch=epoch, zone_id=cell_id, stamp=stamp)
            return allowed, reason

    def _insert_scan(self, robot, zone_id, stamp, epoch, payload, kind, expected, result):
        with self._db:
            self._db.execute(
                'INSERT INTO scan (robot, zone_id, stamp, epoch, payload, kind, expected, result) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                (robot, zone_id, stamp, int(epoch), payload, kind, expected, result))

    def _one(self, sql, key):
        with self._lock:
            row = self._db.execute(sql, (key,)).fetchone()
        return dict(row) if row else None

    def drug(self, item_id):
        return self._one('SELECT * FROM drug WHERE item_id = ?', item_id)

    def container(self, container_id):
        return self._one('SELECT * FROM container WHERE container_id = ?', container_id)

    def module(self, module_id):
        return self._one('SELECT * FROM module WHERE module_id = ?', module_id)

    def pouch(self, order_id):
        return self._one('SELECT * FROM pouch WHERE order_id = ?', order_id)

    def lookup(self, payload):
        """QR 내용 → (종류, 행). 형식이 틀리면 (None, None), DB 에 없으면 (종류, None).

        스테이션은 DB 표가 없어 형식만 본다. 환자는 봉투 표에 있는 환자인지 본다.
        """
        kind, key = classify(payload)
        if kind == KIND_POUCH:
            return kind, self.pouch(key)
        if kind == KIND_CONTAINER:
            return kind, self.container(key)
        if kind == KIND_MODULE:
            return kind, self.module(key)
        if kind == KIND_PATIENT:
            return kind, self._one('SELECT patient_id FROM pouch WHERE patient_id = ? LIMIT 1', key)
        if kind == KIND_STATION:
            return kind, {'zone_id': key}
        return None, None

    def can_mount(self, container_id):
        """보충 때 장착해도 되는가(계약 2.3). (허용, 이유). 만료·회수·모름이면 거부."""
        row = self.container(container_id)
        if row is None:
            return False, SCAN_UNKNOWN_ID
        if row['status'] == STATUS_RECALLED:
            return False, STATUS_RECALLED
        if row['expiry'] < self.today:
            return False, STATUS_EXPIRED
        return True, SCAN_OK

    def record_scan(self, payload, robot, epoch, zone_id=None, stamp=None, expected=None):
        """스캔 한 번을 기록하고 결과 값을 돌려준다. 기록은 판정을 바꾸지 않는다(계약 2.2)."""
        kind, row = self.lookup(payload)
        text = (payload or '').strip()
        if kind is None:
            result = SCAN_BAD_FORMAT
        elif expected is not None and text != expected:
            result = SCAN_MISMATCH
        elif row is None:
            result = SCAN_UNKNOWN_ID
        elif kind == KIND_CONTAINER and not self.can_mount(text)[0]:
            result = SCAN_RECALLED if self.can_mount(text)[1] == STATUS_RECALLED else SCAN_EXPIRED
        else:
            result = SCAN_OK
        with self._lock:
            self._insert_scan(robot, zone_id, stamp, epoch, text, kind, expected, result)
        return result

    def scans(self, epoch=None):
        sql, args = 'SELECT * FROM scan', ()
        if epoch is not None:
            sql, args = sql + ' WHERE epoch = ?', (int(epoch),)
        with self._lock:
            return [dict(row) for row in self._db.execute(sql + ' ORDER BY seq', args)]

    def add_pouch_status(self, order_id, status, epoch, stamp=None):
        """봉투 상태 이력 한 줄. 모르는 봉투면 CatalogError."""
        if self.pouch(order_id) is None:
            raise CatalogError(f'{order_id}: 모르는 봉투다')
        with self._lock, self._db:
            self._db.execute('INSERT INTO pouch_status (order_id, status, stamp, epoch) VALUES (?, ?, ?, ?)',
                             (order_id, status, stamp, int(epoch)))

    def pouch_history(self, order_id):
        with self._lock:
            return [dict(row) for row in self._db.execute(
                'SELECT * FROM pouch_status WHERE order_id = ? ORDER BY seq', (order_id,))]
