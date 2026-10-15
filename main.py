from time import sleep
import seamaq_formbot as seamaq_formbot

# Entry
def main():
    seamaq_formbot.initialize()
    while not seamaq_formbot.should_exit():
        seamaq_formbot.update()
        sleep(1/120) # Run at 120 FPS


if __name__ == "__main__":
    main()