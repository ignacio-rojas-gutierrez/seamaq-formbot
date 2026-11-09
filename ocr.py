import ctypes
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import overload
import itertools

import pytesseract
import win32gui
import cv2
import numpy as np
#from PIL import Image, ImageGrab, ImageOps
import PIL.Image, PIL.ImageGrab, PIL.ImageOps, PIL.ImageStat, PIL.ImageDraw

from pytesseract import Output


# Same reason as overlay.py: without this, display scaling shifts coordinates.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
TESSERACT = ROOT / "Tesseract-OCR" / "tesseract.exe"
TESSDATA = ROOT / "Tesseract-OCR" / "tessdata"
TEMP_PATH = ROOT / "temp"
RAW_PATH = TEMP_PATH / "screenshot_raw.png"

pytesseract.pytesseract.tesseract_cmd = str(TESSERACT)
if TESSDATA.is_dir():
    os.environ["TESSDATA_PREFIX"] = str(TESSDATA)   # must point at the tessdata folder itself

# Uncomment to use a different Tesseract installation (e.g. system-wide) instead of the one bundled with this project.
TESSERACT = Path(r"C:/Program Files/Tesseract-OCR/tesseract.exe")
TESSDATA = Path(r"C:/Program Files/Tesseract-OCR/tessdata")


pytesseract.pytesseract.tesseract_cmd = str(TESSERACT)
#pytesseract.pytesseract.tessdata_dir = str(TESSDATA)
os.environ["TESSDATA_PREFIX"] = str(TESSDATA)   # must point at the tessdata folder itself


SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77


@dataclass
class Screenshot:
    image: PIL.Image.Image
    origin: tuple[int, int]          # screen coords of the image's top-left pixel

    def __init__(self, image: PIL.Image.Image, origin: tuple[int, int] | None = None):
        self.image = image
        self.origin = origin if origin is not None else (0, 0)

    def crop(self, bounds: tuple) -> "Screenshot":
        """Crop to (left, top, right, bottom) given in SCREEN coordinates."""
        ox, oy = self.origin
        left, top, right, bottom = bounds
        box = (
            max(left - ox, 0), max(top - oy, 0),
            min(right - ox, self.image.width), min(bottom - oy, self.image.height),
        )
        return Screenshot(self.image.crop(box), (ox + box[0], oy + box[1]))



# decimals per box index (None = skip, e.g. empty-by-design or extras)
DECIMALS = (
    [None, None, 2]            # Fecha, Hora, Deriva
    + [2] * 6                  # Suspensión: adherencia izq/der, diferencia
    + [0] * 6                  # Peso
    + [2] * 12                 # Fuerza izq / der
    + [2]                      # Eficiencia total
    + [2] * 12                 # Diferencia / Eficiencia frenos
    + [0, 2, 2, 1]             # HC, Humo, CO, Ruido
    # + [None, None]
)   

def normalize(text: str, decimals: int | None) -> str:
    if decimals is None or not text:
        return text
    digits = text.replace(".", "").replace(",", "")
    if decimals == 0:
        return digits
    digits = digits.rjust(decimals + 1, "0")
    return f"{digits[:-decimals]},{digits[-decimals:]}"

# ---- stage 1: raw capture (no processing, no filtering) ----------------------
def capture_raw(save: bool = True) -> Screenshot:
    """Full virtual screen (all monitors), untouched."""
    user32 = ctypes.windll.user32
    origin = (user32.GetSystemMetrics(SM_XVIRTUALSCREEN),
              user32.GetSystemMetrics(SM_YVIRTUALSCREEN))
    image = PIL.ImageGrab.grab(all_screens=True)
    if save:
        TEMP_PATH.mkdir(exist_ok=True)
        image.save(RAW_PATH)         # PNG = lossless
    return Screenshot(image, origin)


def screenshot() -> Screenshot:      # keeps main.py working
    return capture_raw()


# ---- stage 2: filter (crop -> preprocess -> OCR -> filter words) -------------
def _preprocess(image: PIL.Image.Image, scale: int) -> PIL.Image.Image:
    image = PIL.ImageOps.grayscale(image)
    image = PIL.ImageOps.autocontrast(image)
    if scale > 1:
        image = image.resize((image.width * scale, image.height * scale), PIL.Image.Resampling.LANCZOS)
    return image

def check_decimals(text: str, decimals: int | None) -> bool:
    """True if the raw OCR text is consistent with the expected decimals."""
    if decimals is None or not text:
        return True
    m = re.search(r"[.,](\d+)$", text)
    if not m:
        return True            # separator lost: can't verify, trust the table
    return len(m.group(1)) == decimals

def read_words(
    shot: Screenshot,
    region: tuple | None = None,      # screen-coords rect to keep; None = whole capture
    lang: str = "eng",
    min_conf: float = 40,
    psm: int = 11,
    scale: int = 4,
    pattern: str | None = None,       # e.g. r"\d+([.,]\d+)?" keeps only numbers
    extra_config: str = "",              # NEW
) -> list[dict]:
    if region:
        shot = shot.crop(region)
    if shot.image.width == 0 or shot.image.height == 0:
        return []

    data = pytesseract.image_to_data(
        _preprocess(shot.image, scale),
        lang=lang,
        #config=f'--tessdata-dir "{TESSDATA}" --psm {psm}',
        config=f' --psm {psm} {extra_config}',
        output_type=Output.DICT,
    )

    ox, oy = shot.origin
    words = []
    for i, text in enumerate(data["text"]):
        text = text.strip()
        conf = float(data["conf"][i])
        if not text or conf < min_conf:
            continue
        if pattern and not re.fullmatch(pattern, text):
            continue
        x, y = data["left"][i] / scale, data["top"][i] / scale
        w, h = data["width"][i] / scale, data["height"][i] / scale
        words.append({
            "text": text,
            "confidence": conf,
            # mapped back to SCREEN coordinates, same space as WindowInfo.bounds
            "bounds": (int(ox + x), int(oy + y), int(ox + x + w), int(oy + y + h)),
        })
    return words


def read_window_words(hwnd: int, shot: Screenshot | None = None, **kwargs) -> list[dict]:
    """Capture (or reuse a raw capture) and read only the given window."""
    shot = shot or capture_raw(save=False)
    return read_words(shot, region=win32gui.GetWindowRect(hwnd), **kwargs)


def find_boxes(shot: Screenshot, region: tuple,
               min_w=25, max_w=80, min_h=10, max_h=24) -> list[tuple]:
    """Screen-coord rects of the small outlined value boxes inside region."""
    crop = shot.crop(region)
    gray = cv2.cvtColor(np.array(crop.image), cv2.COLOR_RGB2GRAY)
    _, bw = cv2.threshold(gray, 160, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(bw, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    ox, oy = crop.origin
    boxes = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if min_w <= w <= max_w and min_h <= h <= max_h and len(cv2.approxPolyDP(c, 3, True)) == 4:
            boxes.append((ox + x, oy + y, ox + x + w, oy + y + h))
    boxes = sorted(set(boxes), key=lambda b: (round(b[1] / 8), b[0]))   # rows, then columns
    return boxes

def _ocr_box(img: PIL.Image.Image, lang: str = "spa", scale: int = 4) -> str:
    """img: the trimmed (and inverted if dark) box crop, as a PIL image."""
    img = PIL.ImageOps.expand(img.convert("RGB"), border=6, fill="white")
    img = PIL.ImageOps.autocontrast(PIL.ImageOps.grayscale(img))
    img = img.resize((img.width * scale, img.height * scale), PIL.Image.BICUBIC)
    data = pytesseract.image_to_data(img, lang=lang, config="--psm 7",
                                     output_type=Output.DICT)
    text = "".join(t.strip() for t in data["text"] if t.strip())
    return re.sub(r"[^\d,.]", "", text)   # keep only digits and separators


def read_boxes(shot: Screenshot, region: tuple) -> list[dict]:
    out = []
    for i, bounds in enumerate(find_boxes(shot, region)):
        img = _make_crop(shot, bounds, trim=2)          # trims, inverts dark boxes
        text = _ocr_box(img)
        dec = DECIMALS[i] if i < len(DECIMALS) else None
        out.append({"bounds": bounds, "text": text, "value": normalize(text, dec), "suspect": not check_decimals(text, dec)})
    return out


# ---- DEBUGGING / TESTING ---------------------------------------------------------

def dump_crops(shot: Screenshot, results: list[dict], indices: list[int],
               trim: int = 2, scale: int = 6, view_scale: int = 6) -> Path:
    """For each index, save a row of 4 stages to temp/boxes/ plus one contact sheet:
       1. context : the box with 4 px of surroundings (is the box where we think?)
       2. raw     : the exact crop after the trim
       3. inverted: after the dark-background check
       4. final   : what Tesseract receives (padding + grayscale + contrast + upscale)"""
    out_dir = TEMP_PATH / "boxes"
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for i in indices:
        l, t, r, b = results[i]["bounds"]
        context = shot.crop((l - 4, t - 4, r + 4, b + 4)).image.convert("RGB")
        raw = shot.crop((l + trim, t + trim, r - trim, b - trim)).image.convert("RGB")

        brightness = PIL.ImageStat.Stat(PIL.ImageOps.grayscale(raw)).mean[0]
        inverted = PIL.ImageOps.invert(raw) if brightness < 128 else raw
        final = _preprocess(PIL.ImageOps.expand(inverted, border=6, fill="white"), scale)

        print(f"[{i:02d}] box={r - l}x{b - t}  crop={raw.width}x{raw.height}  "
              f"brightness={brightness:.0f}  inverted={brightness < 128}  "
              f"text={results[i]['text']!r}")

        stages = [context, raw, inverted, final.convert("RGB")]
        for name, img in zip(("context", "raw", "inverted", "final"), stages):
            img.save(out_dir / f"{i:02d}_{name}.png")
        rows.append((i, stages))

    # contact sheet: every stage scaled to the same height, NEAREST so pixels stay visible
    row_h = 40 * view_scale // 3
    sheet_rows = []
    for i, stages in rows:
        tiles = []
        for img in stages:
            w = max(1, round(img.width * row_h / img.height))
            tiles.append(img.resize((w, row_h), PIL.Image.NEAREST))
        sheet_rows.append((i, tiles))

    width = max(sum(t.width + 8 for t in tiles) for _, tiles in sheet_rows) + 50
    sheet = PIL.Image.new("RGB", (width, len(sheet_rows) * (row_h + 8)), (60, 60, 60))
    draw = PIL.ImageDraw.Draw(sheet)
    for n, (i, tiles) in enumerate(sheet_rows):
        y, x = n * (row_h + 8), 4
        draw.text((x, y + 2), f"{i:02d}", fill="yellow")
        x += 30
        for tile in tiles:
            sheet.paste(tile, (x, y))
            x += tile.width + 8

    path = out_dir / "contact_sheet.png"
    sheet.save(path)
    print(f"saved -> {path}")
    return path

def debug_boxes(shot: Screenshot, region: tuple, results: list[dict] | None = None,
                scale: int = 3, name: str = "debug_boxes.png") -> Path:
    """Draw every detected box with its index over the region and save it to temp/.
    Without results: all boxes are green.
    With results (output of read_boxes): green = text read, red = empty,
    and the text is drawn next to the index."""
    crop = shot.crop(region)
    img = crop.image.convert("RGB").resize(
        (crop.image.width * scale, crop.image.height * scale), PIL.Image.NEAREST)
    draw = PIL.ImageDraw.Draw(img)
    ox, oy = crop.origin

    boxes = [r["bounds"] for r in results] if results else find_boxes(shot, region)
    for i, (l, t, r, b) in enumerate(boxes):
        text = results[i]["text"] if results else ""
        color = "red" if results and not text else "lime"

        # screen coords -> position in the upscaled debug image
        x0, y0 = (l - ox) * scale, (t - oy) * scale
        x1, y1 = (r - ox) * scale, (b - oy) * scale
        draw.rectangle((x0, y0, x1, y1), outline=color, width=2)

        label = f"{i}" + (f":{text}" if text else "")
        # label sits above the box on a dark background so it stays readable
        tw = draw.textlength(label)
        draw.rectangle((x0, y0 - 12, x0 + tw + 4, y0), fill="black")
        draw.text((x0 + 2, y0 - 12), label, fill=color)

    TEMP_PATH.mkdir(exist_ok=True)
    path = TEMP_PATH / name
    img.save(path)
    print(f"{len(boxes)} boxes detected -> {path}")
    return path

def diagnose(shot: Screenshot, results: list[dict], indices: list[int],
             trim: int = 2, scale: int = 6):
    """Run Tesseract on the final image of each box and print the raw output,
    with no pattern or confidence filtering, across lang / psm / whitelist."""
    WL = "-c tessedit_char_whitelist=0123456789,./:"
    for i in indices:
        l, t, r, b = results[i]["bounds"]
        raw = shot.crop((l + trim, t + trim, r - trim, b - trim)).image.convert("RGB")
        if PIL.ImageStat.Stat(PIL.ImageOps.grayscale(raw)).mean[0] < 128:
            raw = PIL.ImageOps.invert(raw)
        img = _preprocess(PIL.ImageOps.expand(raw, border=6, fill="white"), scale)

        print(f"\n[{i:02d}] expected-ish: {results[i]['text']!r}")
        for lang in ("spa", "eng"):
            for psm in (7, 8, 13):
                for use_wl in (False, True):
                    cfg = f'--psm {psm}' + (f" {WL}" if use_wl else "")
                    d = pytesseract.image_to_data(img, lang=lang, config=cfg,
                                                  output_type=Output.DICT)
                    found = [(t_, round(float(c))) for t_, c in zip(d["text"], d["conf"])
                             if t_.strip()]
                    print(f"  {lang} psm={psm:<2} wl={'Y' if use_wl else 'N'} -> {found}")



# index -> expected text (Fecha/Hora skipped; "" = must stay empty)
EXPECTED = {
    2: "0,36",
    3: "71,09", 4: "53,23", 5: "65,94", 6: "46,05", 7: "7,24", 8: "13,49",
    9: "648", 10: "405", 11: "0", 12: "0", 13: "1053", 14: "1053",
    15: "1,82", 16: "1,02", 17: "0,00", 18: "0,00", 19: "1,02", 20: "0,00",
    21: "1,72", 22: "1,13", 23: "0,00", 24: "0,00", 25: "0,98", 26: "0,00",
    27: "55,28",
    28: "5,53", 29: "9,97", 30: "", 31: "", 32: "3,61", 33: "",
    34: "55,81", 35: "54,31", 36: "0,00", 37: "0,00", 38: "19,40", 39: "0,00",
    40: "6", 41: "0,00", 42: "0,19", 43: "0,0",
}

def _make_crop(shot, bounds, trim):
    l, t, r, b = bounds
    img = shot.crop((l + trim, t + trim, r - trim, b - trim)).image.convert("RGB")
    if PIL.ImageStat.Stat(PIL.ImageOps.grayscale(img)).mean[0] < 128:
        img = PIL.ImageOps.invert(img)
    return img

def _ocr_variant(img, lang, scale, resample, thr):
    img = PIL.ImageOps.expand(img, border=6, fill="white")
    img = PIL.ImageOps.autocontrast(PIL.ImageOps.grayscale(img))
    img = img.resize((img.width * scale, img.height * scale), resample)
    if thr is not None:
        img = img.point(lambda p: 255 if p > thr else 0)
    data = pytesseract.image_to_data(img, lang=lang, config="--psm 7",
                                     output_type=Output.DICT)
    text = "".join(t.strip() for t in data["text"] if t.strip())
    return re.sub(r"[^\d,.]", "", text)

def benchmark(shot, boxes):
    """boxes = output of read_boxes (we only use the bounds)."""
    grid = itertools.product(
        ("eng", "spa"), (3, 4, 6), (PIL.Image.NEAREST, PIL.Image.BICUBIC), (None, 140), (2, 3))
    scores = []
    for lang, scale, res, thr, trim in grid:
        wrong = []
        for i, exp in EXPECTED.items():
            img = _make_crop(shot, boxes[i]["bounds"], trim)
            got = normalize(_ocr_variant(img, lang, scale, res, thr), DECIMALS[i])
            if got != exp:
                wrong.append((i, exp, got))
        cfg = f"{lang} x{scale} {'NEAREST' if res == PIL.Image.NEAREST else 'BICUBIC'} thr={thr} trim={trim}"
        scores.append((len(wrong), cfg, wrong))
        print(f"{len(EXPECTED) - len(wrong)}/{len(EXPECTED)}  {cfg}")

    scores.sort(key=lambda s: s[0])
    best = scores[0]
    print(f"\nBEST: {best[1]}  ({len(EXPECTED) - best[0]}/{len(EXPECTED)})")
    for i, exp, got in best[2]:
        print(f"  [{i:02d}] expected {exp!r}, got {got!r}")