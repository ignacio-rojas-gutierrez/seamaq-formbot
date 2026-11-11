from time import sleep
from pywinauto import Application
import seamaq_formbot as seamaq_formbot
import ocr
import lista_de_planillas
import rto
import web_uia

# Entry point
def main():
    seamaq_formbot.run()




if __name__ == "__main__":
    lista = lista_de_planillas.ListaPlanillas()

    browser_win = web_uia.find_browser_window("Firefox")
    data_items_raw = web_uia.get_data_items_by_title(browser_win, "Lista de Planillas")
    data_items_raw = data_items_raw[9::1] # skip header
    
    main()