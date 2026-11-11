from time import sleep
from pywinauto import Application
import seamaq_formbot as seamaq_formbot
import ocr
import rto.rto_forms_list as rto_forms_list
import rto.entry as entry
import web_uia
import tests.master_detail
import dearpygui as dpg

from pywinauto.uia_defines import IUIA
from pywinauto.uia_defines import get_elem_interface, NoPatternInterfaceError
    
# RTOEntry point
def main():
    seamaq_formbot.run()

if __name__ == "__main__":
    forms_list = rto_forms_list.RTOFormsList()
    forms_list.refresh("Firefox")


    
    main()