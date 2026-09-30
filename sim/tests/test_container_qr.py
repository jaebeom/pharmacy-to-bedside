"""약통 QR(Q1, 9/23): 카탈로그의 선반 약통이 스테이지 v2 의 16칸과 1:1 인가, QR 생성이 그 ID 를 모두 만드는가.

Isaac·YAML 없이 돈다. 카탈로그는 orchestrator 가 DB 시드로 읽는 파일이다(QR·DB·카메라 계약 2절).
"""
import re
import sys
import unittest
from pathlib import Path

STANDALONE = Path(__file__).resolve().parents[1] / "standalone"
REPO = STANDALONE.parents[1]
sys.path.insert(0, str(STANDALONE))
import make_qr_textures  # noqa: E402
from p3sim import layout_v2  # noqa: E402

CATALOG = (REPO / "src" / "rokey_p3_orchestrator" / "config" / "pharmacy_catalog.yaml").read_text(encoding="utf-8")
# 한 줄 = `{...}` 하나. `[^}]` 로 다음 약통 줄까지 넘어가지 않게 한다.
SHELF_ROW = re.compile(r'container_id:\s*(cn-[0-9]{4})[^}]*?item_id:\s*([a-z-]+)[^}]*?expiry:\s*"([0-9-]+)"[^}]*?'
                       r'location:\s*"shelf:([a-z0-9_]+/r[0-9]c[0-9])"')


#: 병원 M0609 워크셀 칸(prepare_workcell_integration.py: 선반 67–75, r0c0 원통·r0c1 모듈). 그 스크립트는 USD 가 있어야
#: 돌아 여기서는 이름 규칙만 맞댄다.
WORKCELL_CELLS = {f"shelf_{n}/r0c{c}": ("cylinder" if c == 0 else "module") for n in range(67, 76) for c in (0, 1)}


class ShelfContainers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        params = layout_v2.default_v2()
        _boxes, cls.cells = layout_v2.shelves(params)
        cls.items = params["items"]
        cls.rows = {cell: (cid, item, expiry) for cid, item, expiry, cell in SHELF_ROW.findall(CATALOG)}
        cls.kinds = {**{c: v["type"] for c, v in cls.cells.items()}, **WORKCELL_CELLS}

    def test_every_stage_cell_has_exactly_one_container(self):
        """빈월드 scene v2 16칸과 병원 워크셀 18칸, 합쳐 34칸이 카탈로그와 1:1 이다."""
        self.assertEqual(set(self.rows), set(self.kinds))
        ids = [cid for cid, _item, _expiry in self.rows.values()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_item_follows_the_canister_kind(self):
        for cell, (cid, item, _expiry) in self.rows.items():
            self.assertEqual(item, self.items[self.kinds[cell]], cid)

    def test_one_amox_cell_per_scene_is_expired_for_the_refusal_scene(self):
        """시드 7 의 첫 원통 칸이 만료다: 빈월드 floor_right/r0c1, 병원 shelf_72/r0c0."""
        expired = sorted(cell for cell, (_cid, _item, expiry) in self.rows.items() if expiry < "2026-09-23")
        self.assertEqual(expired, ["floor_right/r0c1", "shelf_72/r0c0"])
        for cells, first in ((sorted(c for c, k in self.kinds.items() if k == "cylinder" and "/" in c
                                     and not c.startswith("shelf_")), "floor_right/r0c1"),
                             (sorted(c for c, k in WORKCELL_CELLS.items() if k == "cylinder"), "shelf_72/r0c0")):
            import random
            self.assertEqual(random.Random(7).choice(cells), first)


class QrIds(unittest.TestCase):
    def test_catalog_ids_cover_containers_and_modules(self):
        ids = make_qr_textures.catalog_ids(CATALOG)
        self.assertTrue({f"cn-{n:04d}" for n in range(101, 117)} <= ids)
        self.assertIn("md-0001", ids)
        self.assertTrue(all(re.fullmatch(r"(cn|md)-[0-9]{4}", i) for i in ids))

    def test_either_source_is_enough(self):
        parser = make_qr_textures.build_parser()
        args = parser.parse_args(["--catalog", "c.yaml", "--out", "o"])
        self.assertIsNone(args.order_pool)


if __name__ == "__main__":
    unittest.main()
