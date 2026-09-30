"""병원 벽 표지판 아틀라스를 만든다(`sim/assets/decor/signs.png` + `signs.json`).

바닥 글자 아틀라스(`make_decor_atlas.py`)와 같은 방식이다 — 한글 글꼴이 있는 곳에서 한 번 만들어 커밋한다.
글자를 바꾸면 이 스크립트로 다시 만들고 둘 다 커밋한다 — 시험이 `hospital_signage.SIGN_TEXTS` 와 대조한다.

    python3 sim/standalone/make_signage_atlas.py            # 기본 글꼴: Noto Sans CJK KR Bold

최적화 예산(9/24): 긴 변 1024 이하, 알파 없음(RGB), 한 장.
"""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import make_decor_atlas as base  # noqa: E402
from p3sim import hospital_signage as signage  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--font", default=base.DEFAULT_FONT)
    parser.add_argument("--font-index", type=int, default=1, help="ttc 안 글꼴 번호(Noto CJK 는 1 이 KR)")
    parser.add_argument("--out", default=str(base.OUT_DIR))
    args = parser.parse_args(argv)

    from PIL import Image, ImageDraw, ImageFont

    texts = list(signage.SIGN_TEXTS)
    boxes, size = base.layout(texts)
    image = Image.new("RGB", size, base.rgb(signage.ORANGE))
    draw = ImageDraw.Draw(image)
    for text, (x0, y0, x1, y1) in boxes.items():
        background, ink = (base.rgb(c) for c in signage.sign_style(text))
        draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill=background)
        draw.rectangle((x0 + 3, y0 + 3, x1 - 4, y1 - 4), outline=ink, width=3)
        points = 44
        while True:   # 긴 글자("간호스테이션 B")는 칸에 맞을 때까지 줄인다
            font = ImageFont.truetype(args.font, points, index=args.font_index)
            left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
            if right - left <= (x1 - x0) - 20 or points <= 20:
                break
            points -= 2
        tx = x0 + (x1 - x0 - (right - left)) / 2 - left
        ty = y0 + (y1 - y0 - (bottom - top)) / 2 - top
        draw.text((tx, ty), text, fill=ink, font=font)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    image.save(out / "signs.png", optimize=True)
    uv = {text: [round(v, 6) for v in base.to_uv(box, size)] for text, box in boxes.items()}
    (out / "signs.json").write_text(json.dumps({"image": "signs.png", "size": list(size), "cell": list(base.CELL),
                                                "font": f"{font.getname()[0]} {font.getname()[1]}",
                                                "uv": uv}, ensure_ascii=False, indent=1) + "\n",
                                    encoding="utf-8")
    print(f"atlas {out / 'signs.png'} size={size[0]}x{size[1]} signs={len(texts)} font={font.getname()}")


if __name__ == "__main__":
    main()
