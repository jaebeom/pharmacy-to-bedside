"""손 카메라 QR 판독 → 사람이 읽는 요약(재범 9/29 "QR 에 포함된 정보를 간략하게", 개발자·간호사 화면). ROS 없음.

QR 안에는 ID 만 있다(`qr_payload.py`: `ord-` 봉투, `pt-` 환자, `st-` 스테이션, `cn-` 약통, `md-` 모듈).
그 ID 를 주문 풀(`--order-pool`)·약 카탈로그(`--catalog`)·조제기 파일(`--dispenser-file`)로 풀어 요약을 만든다.
전부 합성 데이터다(카탈로그 머리말). 파일이 없으면 요약 칸이 비고 ID 만 남는다 — 지어내지 않는다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

#: `TagRead.kind` 정수 → 이름(TagRead.msg 상수와 같다).
TAG_KINDS = {0: "patient", 1: "station", 2: "pouch", 3: "container", 4: "module"}


def _yaml(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.is_file():
        return {}
    try:
        import yaml
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - 읽을 수 없는 파일이 서버를 세우면 안 된다
        return {}
    return data if isinstance(data, dict) else {}


class QrResolver:
    """ID → 요약. 주문 풀 목록(`order_pool.PoolResult.orders`)과 카탈로그·조제기 YAML 을 한 번 읽어 둔다."""

    def __init__(self, orders: list[dict[str, Any]] | None = None, catalog: str | Path | None = None,
                 dispenser: str | Path | None = None) -> None:
        self.orders = {o.get("order_id"): o for o in (orders or []) if o.get("order_id")}
        self.by_patient: dict[str, list[dict[str, Any]]] = {}
        for order in self.orders.values():
            self.by_patient.setdefault(str(order.get("patient_id") or ""), []).append(order)
        cat = _yaml(catalog)
        self.drugs = {k: v for k, v in (cat.get("drugs") or {}).items() if isinstance(v, dict)}
        self.containers = {c.get("container_id"): c for c in (cat.get("containers") or [])
                           if isinstance(c, dict) and c.get("container_id")}
        # 로트 → (약품, 유통기한). 조제기 파일의 items(투입 칸)·shelf(선반) 둘 다다.
        self.lots: dict[str, dict[str, Any]] = {}
        disp = _yaml(dispenser)
        for section in ("items", "shelf"):
            for item_id, rows in (disp.get(section) or {}).items():
                for row in rows or []:
                    if isinstance(row, dict) and row.get("lot_id"):
                        self.lots[row["lot_id"]] = {"item_id": item_id, "expiry": row.get("expiry")}

    def drug_text(self, item_id: str | None) -> str | None:
        """`drug-amox` → "아목시실린 캡슐 500 mg". 카탈로그에 없으면 None."""
        drug = self.drugs.get(item_id or "")
        if not drug:
            return None
        return " ".join(str(v) for v in (drug.get("name"), drug.get("strength")) if v)

    def info(self, kind: str, tag_id: str) -> dict[str, Any]:
        """판독 한 건의 요약. 키는 종류마다 다르고, 모르는 값은 None 이다."""
        if kind == "pouch":
            order = self.orders.get(tag_id) or {}
            return {"order_id": tag_id, "patient_id": order.get("patient_id"), "bed": order.get("bed"),
                    "item_id": order.get("item_id"), "drug": self.drug_text(order.get("item_id"))}
        if kind == "patient":
            orders = self.by_patient.get(tag_id, [])
            beds = sorted({o.get("bed") for o in orders if o.get("bed")})
            return {"patient_id": tag_id, "bed": beds[0] if len(beds) == 1 else None,
                    "order_ids": sorted(o["order_id"] for o in orders)}
        if kind == "station":
            return {"zone": tag_id}
        if kind in ("container", "module"):
            row = self.containers.get(tag_id) or {}
            lot = self.lots.get(row.get("lot_id") or "", {})
            item_id = row.get("item_id") or lot.get("item_id")
            return {"container_id": tag_id, "lot_id": row.get("lot_id"), "item_id": item_id,
                    "drug": self.drug_text(item_id), "expiry": row.get("expiry") or lot.get("expiry")}
        return {}
