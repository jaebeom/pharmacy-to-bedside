"""Make one QR texture PNG per order id (pouches), patient id (pt-, bedside plates) and canister/module id (shelf).

    python3 sim/standalone/make_qr_textures.py --order-pool src/rokey_p3_orchestrator/config/order_pool.yaml \
        --out sim/outputs/qr
    python3 sim/standalone/make_qr_textures.py --catalog src/rokey_p3_orchestrator/config/pharmacy_catalog.yaml \
        --out sim/outputs/qr

QR/DB/camera contract v1 section 1: a QR holds only the id (cn-NNNN, md-NNNN, ord-NNNN); the rest is in the DB.

Contract v1 7: the order id is the QR content (ord-NNNN); QR images are generated from the order pool by the
simulation lane. Encoding uses OpenCV's QRCodeEncoder (installed on master02 for perception); if OpenCV is missing it
falls back to the `qrcode` package. Output PNGs stay out of Git (sim/outputs/ is local). Each file is checked by
decoding it back with OpenCV when OpenCV is available.
"""

import argparse
import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from p3sim import pouch  # noqa: E402


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--order-pool", help="order_pool.yaml (ord- ids)")
    parser.add_argument("--catalog", help="pharmacy_catalog.yaml (cn- and md- ids)")
    parser.add_argument("--out", required=True, help="directory for <order_id>.png")
    parser.add_argument("--pixels", type=int, default=512, help="output image side, px")
    parser.add_argument("--border", type=int, default=4, help="quiet zone in modules")
    return parser


PATIENT_LINE = re.compile(r"\bpatient_id:\s*['\"]?([A-Za-z0-9_-]+)")


def patient_ids(text):
    """주문 풀의 환자 ID → `pt-<ID>`(계약 7절 환자 인식표). 병원 협탁 인식표 판(시각 소품)에 쓴다."""
    return {f"pt-{match.group(1)}" for match in PATIENT_LINE.finditer(text)}


TABLE_LINE = re.compile(r"\bbed:\s*['\"]?(station_[a-z])\b")


def station_ids(text):
    """주문 풀의 테이블 목적지 → `st-<zone>`(계약 7절 스테이션 인식표). 재범 9/25: 테이블에는 스테이션 표가 붙는다."""
    return {f"st-{match.group(1)}" for match in TABLE_LINE.finditer(text)}


CATALOG_LINE = re.compile(r"(?:container_id|module_id):\s*['\"]?((?:cn|md)-[0-9]{4})")


def catalog_ids(text):
    """cn-·md- ids from a pharmacy_catalog.yaml body without a YAML dependency (same reason as the order pool)."""
    return {match.group(1) for match in CATALOG_LINE.finditer(text)}


def encode_opencv(text, pixels, border):
    import cv2
    import numpy as np

    params = cv2.QRCodeEncoder_Params()
    params.correction_level = cv2.QRCodeEncoder_CORRECT_LEVEL_M
    matrix = cv2.QRCodeEncoder_create(params).encode(text)  # one pixel per module
    matrix = cv2.copyMakeBorder(matrix, border, border, border, border, cv2.BORDER_CONSTANT, value=255)
    image = cv2.resize(matrix, (pixels, pixels), interpolation=cv2.INTER_NEAREST)
    return np.ascontiguousarray(image)


def write_png(path, text, pixels, border):
    try:
        import cv2

        image = encode_opencv(text, pixels, border)
        if not cv2.imwrite(str(path), image):
            raise OSError(f"cv2.imwrite failed for {path}")
        decoded, _points, _raw = cv2.QRCodeDetector().detectAndDecode(image)
        return "opencv", decoded
    except ImportError:
        import qrcode

        image = qrcode.make(text, border=border).resize((pixels, pixels))
        image.save(path)
        return "qrcode", None


def main(argv=None):
    args = build_parser().parse_args(argv)
    ids = set()
    if args.order_pool:
        text = Path(args.order_pool).read_text()
        ids |= pouch.order_ids_from_pool_text(text) | patient_ids(text) | station_ids(text)
    if args.catalog:
        ids |= catalog_ids(Path(args.catalog).read_text())
    ids = sorted(ids)
    if not ids:
        print(f"no ids found in {args.order_pool or '-'} / {args.catalog or '-'}", file=sys.stderr)
        return 2
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    failures = 0
    for order_id in ids:
        path = out / f"{order_id}.png"
        encoder, decoded = write_png(path, order_id, args.pixels, args.border)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        check = "not_checked" if decoded is None else ("ok" if decoded == order_id else f"MISMATCH({decoded!r})")
        failures += check.startswith("MISMATCH")
        print(f"qr id={order_id} file={path} encoder={encoder} decode={check} sha256={digest}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
