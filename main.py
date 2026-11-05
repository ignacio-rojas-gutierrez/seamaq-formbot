from time import sleep
from pywinauto import Application
import seamaq_formbot as seamaq_formbot
import ocr

# Entry point
def main():
    seamaq_formbot.run()

if __name__ == "__main__":
    ocr.screenshot()
    main()