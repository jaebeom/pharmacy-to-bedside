"""STAT S0 영속 원장. sqlite3 파일 하나. ROS 를 import 하지 않는다.

계약: docs/architecture/stat-delivery-contract-v1.md (proposed).

- 상태 변경과 그 이벤트(outbox)는 한 트랜잭션이다. 쓰기가 실패하면 둘 다 남지 않는다.
- 재시작은 이 파일을 다시 연다. Pod 는 표가 비었을 때만 seed 한다. 재시작이 재고를 되돌리지 않는다.
- 쓰기 실패는 시험에서 라벨로 주입한다(fail_labels). 실패한 쓰기 뒤의 비가역 명령은 호출자가 보내지 않는다.
"""

import json
import sqlite3
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS incidents (
  incident_id TEXT PRIMARY KEY, room_id TEXT, bed_id TEXT, first_stamp REAL, last_stamp REAL,
  observation_count INTEGER, labels TEXT, degraded INTEGER, status TEXT);
CREATE TABLE IF NOT EXISTS samples_seen (
  source_id TEXT, boot_id TEXT, seq INTEGER, PRIMARY KEY (source_id, boot_id, seq));
CREATE TABLE IF NOT EXISTS approvals (
  approval_id TEXT PRIMARY KEY, revision TEXT, incident_id TEXT, approver_role TEXT, subject_ref TEXT,
  kit_id TEXT, kit_revision TEXT, quantity INTEGER, destination_id TEXT, issued_at REAL, expires_at REAL,
  revoked INTEGER);
CREATE TABLE IF NOT EXISTS requests (request_id TEXT PRIMARY KEY, content_hash TEXT, order_id TEXT);
CREATE TABLE IF NOT EXISTS orders (
  order_id TEXT PRIMARY KEY, seq INTEGER UNIQUE, request_id TEXT, incident_id TEXT,
  approval_id TEXT UNIQUE, approval_revision TEXT, subject_ref TEXT, kit_id TEXT, kit_revision TEXT,
  destination_id TEXT, state TEXT, reason TEXT, pod_id TEXT, mission TEXT, cancel_requested INTEGER,
  current_op TEXT);
CREATE TABLE IF NOT EXISTS pods (
  pod_id TEXT PRIMARY KEY, kit_id TEXT, kit_revision TEXT, quality TEXT, custody TEXT, holder TEXT,
  reserved_by TEXT, hold TEXT);
CREATE TABLE IF NOT EXISTS ops (
  op_id TEXT PRIMARY KEY, order_id TEXT, kind TEXT, status TEXT, generation INTEGER, command_seq INTEGER,
  floor_boot TEXT, floor_seq INTEGER, prior_state TEXT, sent_at REAL, reason TEXT);
CREATE TABLE IF NOT EXISTS events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, order_id TEXT, generation INTEGER, detail TEXT);
"""

# 주문 상태(계약 2절)
ACCEPTED = 'ACCEPTED'
RESERVED = 'RESERVED'
PREPARING = 'PREPARING'
LOADED = 'LOADED'
IN_TRANSIT = 'IN_TRANSIT'
HANDOVER = 'HANDOVER'
DELIVERED = 'DELIVERED'
FAILED = 'FAILED'
CANCELLED = 'CANCELLED'
EXPIRED = 'EXPIRED'
PAUSED_RECONCILE = 'PAUSED_RECONCILE'
ORDER_DONE = frozenset({DELIVERED, FAILED, CANCELLED, EXPIRED})

# Pod custody·품질·보류
SOURCE = 'SOURCE'
PICKUP_STAGE = 'PICKUP_STAGE'
DRONE = 'DRONE'
RECEIVER = 'RECEIVER'
UNKNOWN = 'UNKNOWN'
QUALIFIED = 'QUALIFIED'
HOLD_RECOVERY = 'RECOVERY_REQUIRED'
HOLD_RECONCILE = 'RECONCILE'

# 임무 축
MISSION_NOT_STARTED = 'NOT_STARTED'
MISSION_ACTIVE = 'ACTIVE'
MISSION_CLOSED = 'CLOSED'
MISSION_FAULT = 'FAULT'

INCIDENT_ACK_REQUIRED = 'ACK_REQUIRED'


class LedgerWriteError(RuntimeError):
    """원장에 쓰지 못했다. 이 쓰기에 기대는 명령은 보내지 않는다."""


def _row(row):
    return dict(row) if row is not None else None


class StatLedger:
    """STAT 주문·사건·승인·Pod·op·이벤트 원장."""

    def __init__(self, path):
        self.path = str(path)
        self.fail_labels = set()      # 시험용: 이 라벨의 쓰기를 실패시킨다
        self._db = sqlite3.connect(self.path, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute('PRAGMA journal_mode=WAL')
        self._db.execute('PRAGMA synchronous=FULL')
        self._db.executescript(SCHEMA)
        with self.tx('open') as c:
            c.execute("INSERT OR IGNORE INTO meta VALUES ('epoch', '1'), ('generation', '0'), "
                      "('order_seq', '0'), ('incident_seq', '0'), ('command_seq', '0')")

    def close(self):
        self._db.close()

    @contextmanager
    def tx(self, label):
        """한 트랜잭션. 안에서 예외가 나거나 label 이 실패 주입돼 있으면 전부 되돌린다."""
        try:
            self._db.execute('BEGIN IMMEDIATE')
        except sqlite3.Error as exc:
            raise LedgerWriteError(f'{label}: {exc}') from exc
        try:
            yield self._db
            if label in self.fail_labels:
                raise LedgerWriteError(f'{label}: 주입한 쓰기 실패')
            self._db.execute('COMMIT')
        except BaseException as exc:
            self._db.execute('ROLLBACK')
            if isinstance(exc, sqlite3.Error):
                raise LedgerWriteError(f'{label}: {exc}') from exc
            raise

    # meta
    def meta(self, key):
        return int(self._db.execute('SELECT value FROM meta WHERE key = ?', (key,)).fetchone()[0])

    @staticmethod
    def bump(c, key):
        """meta 정수를 1 올리고 새 값을 돌려준다. tx 안에서 부른다."""
        c.execute('UPDATE meta SET value = CAST(value AS INTEGER) + 1 WHERE key = ?', (key,))
        return int(c.execute('SELECT value FROM meta WHERE key = ?', (key,)).fetchone()[0])

    def emit(self, c, name, order_id='', **detail):
        """outbox 이벤트. 상태 변경과 같은 tx 안에서 부른다."""
        c.execute('INSERT INTO events (name, order_id, generation, detail) VALUES (?, ?, ?, ?)',
                  (name, order_id, self.meta('generation'), json.dumps(detail, sort_keys=True)))

    # Pod
    def seed_pods(self, pods):
        """Pod 표가 비었을 때만 채운다. 이미 있으면 아무것도 하지 않고 False."""
        with self.tx('seed') as c:
            if c.execute('SELECT COUNT(*) FROM pods').fetchone()[0]:
                return False
            for pod in pods:
                c.execute('INSERT INTO pods VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                          (pod['pod_id'], pod['kit_id'], pod['kit_revision'], pod.get('quality', QUALIFIED),
                           SOURCE, 'SOURCE', '', ''))
            self.emit(c, 'STAT_PODS_SEEDED', count=len(pods))
        return True

    def pod(self, pod_id):
        return _row(self._db.execute('SELECT * FROM pods WHERE pod_id = ?', (pod_id,)).fetchone())

    def pods(self):
        return [dict(r) for r in self._db.execute('SELECT * FROM pods ORDER BY pod_id')]

    # 조회
    def incident(self, incident_id):
        return _row(self._db.execute('SELECT * FROM incidents WHERE incident_id = ?', (incident_id,)).fetchone())

    def incidents(self):
        return [dict(r) for r in self._db.execute('SELECT * FROM incidents ORDER BY first_stamp, incident_id')]

    def approval(self, approval_id):
        return _row(self._db.execute('SELECT * FROM approvals WHERE approval_id = ?', (approval_id,)).fetchone())

    def request(self, request_id):
        return _row(self._db.execute('SELECT * FROM requests WHERE request_id = ?', (request_id,)).fetchone())

    def order(self, order_id):
        return _row(self._db.execute('SELECT * FROM orders WHERE order_id = ?', (order_id,)).fetchone())

    def orders(self):
        return [dict(r) for r in self._db.execute('SELECT * FROM orders ORDER BY seq')]

    def op(self, op_id):
        return _row(self._db.execute('SELECT * FROM ops WHERE op_id = ?', (op_id,)).fetchone())

    def ops(self, order_id):
        return [dict(r) for r in self._db.execute('SELECT * FROM ops WHERE order_id = ? ORDER BY rowid',
                                                  (order_id,))]

    def events(self, since=0):
        rows = self._db.execute('SELECT * FROM events WHERE seq > ? ORDER BY seq', (since,))
        return [dict(r, detail=json.loads(r['detail'])) for r in rows]

    def event_names(self, order_id=None):
        return [e['name'] for e in self.events() if order_id is None or e['order_id'] == order_id]
