import ctypes
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import overload

import pytesseract
import win32gui
import cv2
import numpy as np
#from PIL import Image, ImageGrab, ImageOps
import PIL.Image, PIL.ImageGrab, PIL.ImageOps, PIL.ImageStat
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
pytesseract.pytesseract.tessdata_dir = str(TESSDATA)

SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77


@dataclass
class Screenshot:
    image: PIL.Image.Image
    origin: tuple[int, int]          # screen coords of the image's top-left pixel

    def __init__(self, image_path_or_image, origin: tuple[int, int] | None = None):
        if isinstance(image_path_or_image, PIL.Image.Image):
            self.image = image_path_or_image
        else:
            self.image = PIL.Image.open(image_path_or_image)
        self.origin = origin if origin is not None else (0, 0)

    def __init__(self, image: PIL.Image.Image, origin: tuple[int, int]):
        self.image = image
        self.origin = origin

    def crop(self, bounds: tuple) -> "Screenshot":
        """Crop to (left, top, right, bottom) given in SCREEN coordinates."""
        ox, oy = self.origin
        left, top, right, bottom = bounds
        box = (
            max(left - ox, 0), max(top - oy, 0),
            min(right - ox, self.image.width), min(bottom - oy, self.image.height),
        )
        return Screenshot(self.image.crop(box), (ox + box[0], oy + box[1]))


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
        config=f'"{TESSDATA}" --psm {psm} {extra_config}',
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

def _ocr_box(crop: Screenshot) -> str:
    img = PIL.ImageOps.expand(crop.image.convert("RGB"), border=6, fill="white")
    padded = Screenshot(img, crop.origin)
    for psm in (7, 8, 13):                       # line, word, raw line
        words = read_words(
            padded, psm=psm, scale=6, min_conf=0,
            pattern=r"[\d/:.,]+",
            extra_config="-c tessedit_char_whitelist=0123456789,.",

        )
        if words:
            return "".join(w["text"] for w in words)
    return ""


def read_boxes(shot: Screenshot, region: tuple | None = None) -> list[dict]:
    out = []
    for b in find_boxes(shot, region or (0, 0, shot.image.width, shot.image.height)):
        inner = (b[0] + 2, b[1] + 2, b[2] - 2, b[3] - 2)
        crop = shot.crop(inner)

        # white-on-dark boxes (Fecha / Hora): invert
        gray = PIL.ImageOps.grayscale(crop.image)
        if PIL.ImageStat.Stat(gray).mean[0] < 128:
            crop = Screenshot(PIL.ImageOps.invert(crop.image.convert("RGB")), crop.origin)

        # out.append({"bounds": b, "text": _ocr_box(crop)})     # CHANGED
        out.append({"text": _ocr_box(crop), "bounds": b})     # CHANGED
    return out
