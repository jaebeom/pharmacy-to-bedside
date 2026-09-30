"""Pouch spawn sampling and order ids. No Isaac imports.

Scenario 4 step 1: position and yaw on the belt are random within configured ranges, and the ranges are recorded.
The protocol seed is --seed: each spawn draws from random.Random(f"{seed}:{epoch}:{index}"), so the n-th pouch of an
epoch lands in the same place regardless of what happened before (string seeds are deterministic in Python 3).
"""

import math
import random
import re

ORDER_ID = re.compile(r"^ord-[0-9]{4}$")  # contract 7, same as rokey_p3_perception/qr_payload.py
POOL_LINE = re.compile(r"order_id:\s*['\"]?(ord-[0-9]{4})")


def is_order_id(text):
    return bool(ORDER_ID.match(text or ""))


def order_ids_from_pool_text(text):
    """Order ids from an order_pool.yaml body without a YAML dependency (Isaac's python may not ship PyYAML)."""
    return {match.group(1) for match in POOL_LINE.finditer(text)}


def spawn_rng(seed, epoch, index):
    return random.Random(f"{seed}:{epoch}:{index}")


def sample_spawn(rng, along_range, lateral_range, yaw_range):
    """(along, lateral, yaw) in the belt frame, uniform within the ranges (yaw in rad, relative to the belt)."""
    return (rng.uniform(*along_range), rng.uniform(*lateral_range), rng.uniform(*yaw_range))


def belt_to_world(start_xyz, belt_yaw, along, lateral, up):
    cos_yaw, sin_yaw = math.cos(belt_yaw), math.sin(belt_yaw)
    return (start_xyz[0] + cos_yaw * along - sin_yaw * lateral,
            start_xyz[1] + sin_yaw * along + cos_yaw * lateral,
            start_xyz[2] + up)


def pouch_prim_name(order_id, index):
    safe = re.sub(r"[^A-Za-z0-9_]", "_", order_id or "unknown")
    return f"Pouch_{safe}_{index:04d}"


def parking_positions(count, origin, pitch, height):
    """Floor spots for idle pouches, in a row along +y from origin (x, y). Out of the robot's and belt's way."""
    return [(origin[0], origin[1] + i * pitch, height) for i in range(count)]


class PouchPool:
    """Pouches are created once before the simulation starts and then only moved.

    9/17 master02: deleting a pouch prim during simulation invalidated the physics tensor simulationView
    ("prim ... was deleted while being used by a shape in a tensor view class"), and the next articulation read
    failed. So spawn = take a parked pouch and teleport it onto the belt; remove = teleport it back to its spot."""

    def __init__(self, count, labels=None):
        """labels[i] is the order id printed on pouch i (its QR texture), or None for a blank pouch."""
        if count < 1:
            raise ValueError("pool needs at least one pouch")
        self.free = list(range(count))
        self.in_use = {}
        self.labels = list(labels) if labels is not None else [None] * count
        if len(self.labels) != count:
            raise ValueError("labels must match the pool size")

    def acquire(self, order_id):
        """Index of a parked pouch now assigned to order_id, or None when all are out.

        Prefers a free pouch labelled with order_id, then a blank one, then any free pouch (a label mismatch the
        caller should log)."""
        if not self.free:
            return None
        for wanted in (order_id, None):
            for index in self.free:
                if self.labels[index] == wanted:
                    self.free.remove(index)
                    self.in_use[index] = order_id
                    return index
        index = self.free.pop(0)
        self.in_use[index] = order_id
        return index

    def release(self, index):
        if index in self.in_use:
            del self.in_use[index]
            self.free.append(index)
            self.free.sort()

    def release_all(self):
        for index in list(self.in_use):
            self.release(index)


#: QR 면이 봉투 윗면에서 차지하는 비율(짧은 변 기준).
QR_FACE_FRACTION = 0.8


def qr_face_size(pouch_size):
    """봉투 윗면의 QR 텍스처 크기 (x, y) m. **정사각형**이다.

    9/23 카메라 L3 전에는 (0.8·x, 0.8·y) 로 붙여 정사각 QR 이 봉투 비율(0.10×0.07)로 늘어났다. 모듈이 직사각형이 되고
    짧은 변 기준 판독 픽셀이 줄었다(58 px 판독 실패). 짧은 변의 0.8 로 정사각형을 둔다.
    """
    side = QR_FACE_FRACTION * min(float(pouch_size[0]), float(pouch_size[1]))
    return side, side


def pool_labels(order_ids, count):
    """Label pouches with the order ids in turn so each order has count // len(order_ids) or more textured copies."""
    ids = sorted(order_ids)
    if not ids:
        return [None] * count
    return [ids[i % len(ids)] for i in range(count)]
