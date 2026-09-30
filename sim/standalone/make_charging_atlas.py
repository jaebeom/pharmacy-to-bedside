"""도크 충전 스테이션 표시 아틀라스(`sim/assets/decor/charging.png` + `charging.json`)와 가짜 AMR "DUMMY" 판
(`dummy_label.png`), M0609 셀 바닥 글자(`workcell_labels.png` + `.json`)를 만든다.

재범 채택 9/24: 도크 넷(A1–A4)에 "충전 스테이션" 표시. 칸은 여섯이다 — 표지판 넷(⚡ + A1…A4), 바닥 ⚡ 하나,
기둥 단색 하나. 글자가 ASCII 라 한글 글꼴이 필요 없다(OpenCV 만). 결과물은 Git 에 둔다(`make_decor_atlas.py` 와
같은 이유: 기동 때 만들지 않는다). 칸 순서·이름은 `hospital_decor.CHARGING_CELLS` 와 대조한다(sim/tests).

    python3 sim/standalone/make_charging_atlas.py

색: 흰색을 쓰지 않는다 — 카메라 봉투 검출기는 "밝고 채도 낮은 덩어리" 를 찾는다(`hospital_decor` 머리말).
"""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from p3sim import hospital_decor as decor  # noqa: E402

OUT_DIR = HERE.parents[0] / "assets" / "decor"
#: 칸 한 변(px). 여섯 칸 가로 한 줄 = 960 — 최적화 예산(긴 변 1024 이하, 9/24).
CELL = 160
#: BGR(OpenCV). 표지판 바탕 짙은 초록, 번개·글자 노랑, 바닥 마크 바탕 짙은 회색, 기둥 회색.
SIGN_BG = (60, 120, 30)
BOLT = (26, 204, 250)
FLOOR_BG = (60, 60, 60)
POST = (110, 110, 110)


def bolt(cx, cy, scale):
    """번개 모양 다각형(픽셀). 위가 -y(그림 위쪽)."""
    import numpy as np

    shape = [(0.10, -0.50), (-0.30, 0.05), (-0.02, 0.05), (-0.12, 0.50), (0.30, -0.08), (0.02, -0.08), (0.14, -0.50)]
    return np.int32([[cx + x * scale, cy + y * scale] for x, y in shape])


def cell_image(kind, text=""):
    import cv2
    import numpy as np

    if kind == "post":
        return np.full((CELL, CELL, 3), POST, np.uint8)
    background = SIGN_BG if kind == "sign" else FLOOR_BG
    image = np.full((CELL, CELL, 3), background, np.uint8)
    cv2.rectangle(image, (4, 4), (CELL - 5, CELL - 5), BOLT, 4)
    if kind == "sign":
        cv2.fillPoly(image, [bolt(CELL * 0.5, CELL * 0.36, CELL * 0.48)], BOLT)
        scale = CELL / 116.0
        (w, _h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_DUPLEX, scale, 3)
        cv2.putText(image, text, (int((CELL - w) / 2), int(CELL * 0.90)), cv2.FONT_HERSHEY_DUPLEX, scale, BOLT, 3,
                    cv2.LINE_AA)
    else:
        cv2.fillPoly(image, [bolt(CELL * 0.5, CELL * 0.5, CELL * 0.80)], BOLT)
    return image


def to_uv(index, count, inset=2.0):
    """칸 번호 → st (u0, v0, u1, v1). 한 줄 가로 배치라 v 는 0–1 전체."""
    width = CELL * count
    return ((index * CELL + inset) / width, inset / CELL, ((index + 1) * CELL - inset) / width, 1.0 - inset / CELL)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", default=str(OUT_DIR))
    args = parser.parse_args(argv)
    import cv2
    import numpy as np

    cells = decor.CHARGING_CELLS
    tiles = []
    for name in cells:
        kind = "post" if name == "post" else ("floor" if name == "floor" else "sign")
        tiles.append(cell_image(kind, name))
    image = np.concatenate(tiles, axis=1)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out / "charging.png"), image, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    uv = {name: [round(v, 6) for v in to_uv(i, len(cells))] for i, name in enumerate(cells)}
    (out / "charging.json").write_text(json.dumps({"image": "charging.png", "size": [image.shape[1], image.shape[0]],
                                                   "cell": [CELL, CELL], "uv": uv}, indent=1) + "\n",
                                       encoding="utf-8")
    print(f"atlas {out / 'charging.png'} size={image.shape[1]}x{image.shape[0]} cells={list(cells)}")
    # 가짜 AMR 위 "DUMMY" 판(재범 9/24 부가 장면). 노란 몸체 위라 검정 글자·검정 테두리. 4:1 = LABEL_SIZE.
    label = np.full((64, 256, 3), (26, 204, 250), np.uint8)
    cv2.rectangle(label, (3, 3), (252, 60), (20, 20, 20), 4)
    (w, _h), _ = cv2.getTextSize("DUMMY", cv2.FONT_HERSHEY_DUPLEX, 1.4, 3)
    cv2.putText(label, "DUMMY", (int((256 - w) / 2), 48), cv2.FONT_HERSHEY_DUPLEX, 1.4, (20, 20, 20), 3, cv2.LINE_AA)
    cv2.imwrite(str(out / "dummy_label.png"), label, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    print(f"label {out / 'dummy_label.png'} size=256x64")
    # M0609 셀 바닥 글자(재범 9/25 "배선이 연결된 느낌"). 검정 판 위라 노랑 글자. 두 칸 가로(256×64 씩, 4:1).
    cells = ("power", "data")
    tiles = []
    for text in cells:
        tile = np.full((64, 256, 3), (12, 10, 10), np.uint8)
        cv2.rectangle(tile, (3, 3), (252, 60), (26, 204, 250), 2)
        (w, _h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_DUPLEX, 1.3, 2)
        cv2.putText(tile, text, (int((256 - w) / 2), 45), cv2.FONT_HERSHEY_DUPLEX, 1.3, (26, 204, 250), 2, cv2.LINE_AA)
        tiles.append(tile)
    atlas = np.concatenate(tiles, axis=1)
    cv2.imwrite(str(out / "workcell_labels.png"), atlas, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    width = 256 * len(cells)
    uv = {text: [round((i * 256 + 2) / width, 6), round(2 / 64, 6), round(((i + 1) * 256 - 2) / width, 6),
                 round(1 - 2 / 64, 6)] for i, text in enumerate(cells)}
    (out / "workcell_labels.json").write_text(json.dumps({"image": "workcell_labels.png", "size": [width, 64],
                                                          "uv": uv}, indent=1) + "\n", encoding="utf-8")
    print(f"label {out / 'workcell_labels.png'} size={width}x64 cells={list(cells)}")


if __name__ == "__main__":
    main()
