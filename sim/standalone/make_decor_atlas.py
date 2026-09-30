"""병원 바닥 글자 판 아틀라스를 만든다(`sim/assets/decor/labels.png` + `labels.json`).

**결과물을 Git 에 둔다.** QR 텍스처는 기동 때 만들지만(`make_qr_textures.py`), 글자는 한글 글꼴이 있어야
그릴 수 있고 마스터에 그 글꼴이 있다는 보장이 없다. 그래서 글꼴이 있는 곳에서 한 번 만들어 커밋한다.
글자를 바꾸면 이 스크립트로 다시 만들고 둘 다 커밋한다 — 시험이 `hospital_decor.BAY_LABELS` 와 대조한다.

    python3 sim/standalone/make_decor_atlas.py            # 기본 글꼴: Noto Sans CJK KR Bold
    python3 sim/standalone/make_decor_atlas.py --font /path/to/font.ttc --font-index 1

최적화 예산(9/24): 긴 변 1024 이하, 알파 없음(RGB), 한 장.
"""

import argparse
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from p3sim import hospital_decor as decor  # noqa: E402

OUT_DIR = HERE.parents[0] / "assets" / "decor"
CELL = (256, 64)          # LABEL_SIZE 0.60 × 0.15 m 와 같은 4:1
COLUMNS = 4


def rgb(color):
    return tuple(int(round(c * 255)) for c in color)
DEFAULT_FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"


def layout(texts, columns=COLUMNS, cell=CELL):
    """글자 → 아틀라스 안 픽셀 상자 (x0, y0, x1, y1), 그림 크기. 순서는 받은 그대로."""
    rows = max(1, math.ceil(len(texts) / columns))
    size = (columns * cell[0], rows * cell[1])
    boxes = {}
    for i, text in enumerate(texts):
        c, r = i % columns, i // columns
        boxes[text] = (c * cell[0], r * cell[1], (c + 1) * cell[0], (r + 1) * cell[1])
    return boxes, size


def to_uv(box, size, inset=2.0):
    """픽셀 상자 → USD st (u0, v0, u1, v1). st 원점은 **왼쪽 아래**라 v 를 뒤집는다.

    가장자리를 안쪽으로 당겨 옆 칸이 번지지 않게 한다. 가로 `inset` 픽셀, 세로는 칸 비율만큼만 —
    양쪽을 같은 픽셀로 당기면 4:1 칸이 4.2:1 이 돼 글자가 옆으로 늘어난다(시험이 잡았다)."""
    x0, y0, x1, y1 = box
    w, h = size
    inset_y = inset * (y1 - y0) / (x1 - x0)
    return ((x0 + inset) / w, 1.0 - (y1 - inset_y) / h, (x1 - inset) / w, 1.0 - (y0 + inset_y) / h)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--font", default=DEFAULT_FONT)
    parser.add_argument("--font-index", type=int, default=1, help="ttc 안 글꼴 번호(Noto CJK 는 1 이 KR)")
    parser.add_argument("--out", default=str(OUT_DIR))
    args = parser.parse_args(argv)

    from PIL import Image, ImageDraw, ImageFont

    texts = decor.atlas_texts()
    boxes, size = layout(texts)
    image = Image.new("RGB", size, rgb(decor.OTHER_COLOR))
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(args.font, 44, index=args.font_index)
    for text, (x0, y0, x1, y1) in boxes.items():
        # 칸마다 갈래 색 바탕(B 파랑·C 초록·D 노랑·그 밖 주황)과 그 위에서 읽히는 글자 색(재범 9/25 03:3x).
        background, ink = (rgb(c) for c in decor.label_style(text))
        draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill=background)
        draw.rectangle((x0 + 3, y0 + 3, x1 - 4, y1 - 4), outline=ink, width=3)
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        tx = x0 + (x1 - x0 - (right - left)) / 2 - left
        ty = y0 + (y1 - y0 - (bottom - top)) / 2 - top
        draw.text((tx, ty), text, fill=ink, font=font)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    image.save(out / "labels.png", optimize=True)
    uv = {text: [round(v, 6) for v in to_uv(box, size)] for text, box in boxes.items()}
    (out / "labels.json").write_text(json.dumps({"image": "labels.png", "size": list(size), "cell": list(CELL),
                                                 "font": f"{font.getname()[0]} {font.getname()[1]}",
                                                 "uv": uv}, ensure_ascii=False, indent=1) + "\n",
                                     encoding="utf-8")
    print(f"atlas {out / 'labels.png'} size={size[0]}x{size[1]} labels={len(texts)} font={font.getname()}")


if __name__ == "__main__":
    main()
