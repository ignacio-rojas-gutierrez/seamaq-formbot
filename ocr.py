from pathlib import Path

import pytesseract
import win32gui
import pyautogui
from PIL import ImageGrab, ImageOps
from pytesseract import Output

ROOT = Path(__file__).resolve().parent
TESSERACT = ROOT / "Tesseract-OCR" / "tesseract.exe"
TESSDATA = ROOT / "Tesseract-OCR" / "tessdata"

pytesseract.pytesseract.tesseract_cmd = str(TESSERACT)


def read_window_words(hwnd: int, lang: str = "spa") -> list[dict]:
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    image = ImageGrab.grab(bbox=(left, top, right, bottom))
    image = ImageOps.grayscale(image)

    data = pytesseract.image_to_data(
        image,
        lang=lang,
        config=f'--tessdata-dir "{TESSDATA}" --psm 6',
        output_type=Output.DICT,
    )

    words = []
    for i, text in enumerate(data["text"]):
        confidence = float(data["conf"][i])
        if text.strip() and confidence >= 40:
            x, y = data["left"][i], data["top"][i]
            width, height = data["width"][i], data["height"][i]
            words.append({
                "text": text.strip(),
                "confidence": confidence,
                "bounds": (left + x, top + y, left + x + width, top + y + height),
            })
    return words

def screenshot():
    return pyautogui.screenshot()