
"""master_detail.py - tabs on top, list of elements on the left, properties of the
selected element on the right (Dear PyGui).

    ┌Tab 1┐ ┌Tab 2┐ ┌Tab 3┐
    ├──────┬─────────────────────
    │ elem │ property: value
    │ elem │ property: value
    │ elem │ property: value

Usage inside your existing StateWindow:

    with dpg.tab(label="Planillas"):
        self._planillas = MasterDetail(dpg.last_container(), label_fn=lambda r: r.dominio)
    ...
    # once per frame (or whenever the data changes):
    self._planillas.update(list_of_dataclasses)

Elements can be dataclasses, dicts or plain objects: every field becomes a property
row automatically, same idea as the State tab.
"""

import dataclasses

import dearpygui.dearpygui as dpg

NAME_COLOR = (150, 190, 255, 255)
GRAY = (150, 150, 150, 255)
VALUE_COLORS = {"True": (90, 200, 90, 255), "False": (230, 90, 90, 255), "None": GRAY}
DEFAULT_VALUE_COLOR = (230, 230, 230, 255)
SKIP_FIELDS = {"children"}            # nested trees are shown elsewhere


def _props_of(obj) -> list[tuple[str, object]]:
    if isinstance(obj, dict):
        return list(obj.items())
    if dataclasses.is_dataclass(obj):
        return [(f.name, getattr(obj, f.name, None)) for f in dataclasses.fields(obj)
                if f.name not in SKIP_FIELDS]
    return [(k, v) for k, v in vars(obj).items() if not k.startswith("_") and k not in SKIP_FIELDS]


def _fmt(value) -> str:
    return repr(value) if isinstance(value, str) else str(value)


class MasterDetail:
    def __init__(self, parent, label_fn=str, list_width: int = 220, on_select=None):
        self._label_fn = label_fn
        self._on_select = on_select          # (index, item) -> None
        self._labels: list[str] = []
        self._rows: list[int] = []           # selectable tags
        self._selected = 0
        self._prop_keys: list[str] | None = None
        self._prop_tags: list[int] = []      # value text tags
        self._items: list = []

        self._theme = self._make_selectable_theme()
        with dpg.group(horizontal=True, parent=parent, horizontal_spacing=0, ):
            self._list_box = dpg.add_child_window(width=list_width, border=False)
            self._detail_box = dpg.add_child_window(border=False,)

        dpg.add_spacer(height=1, parent=self._detail_box)
        self._detail_content = dpg.add_group(parent=self._detail_box, indent=8)


        with dpg.theme() as detail_theme:
            with dpg.theme_component(dpg.mvChildWindow):
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, DETAIL_BG)
                # dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 0, 10)   
        # with dpg.theme() as list_theme:
        #     with dpg.theme_component(dpg.mvChildWindow):
        #         dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 50, 10, )
        #         dpg.add_theme_style(dpg.mvStyleVar_SeparatorTextAlign, 50, 50)
            




        dpg.bind_item_theme(self._detail_box, detail_theme)
        #dpg.bind_item_theme(self._list_box, list_theme)


    # ---- public API --------------------------------------------------------
    @property
    def selected_item(self):
        return self._items[self._selected] if 0 <= self._selected < len(self._items) else None

    def select(self, index: int):
        if not (0 <= index < len(self._items)):
            return
        self._selected = index
        for i, tag in enumerate(self._rows):
            dpg.set_value(tag, i == index)
        self._prop_keys = None               # force the property panel to rebuild
        if self._on_select:
            self._on_select(index, self._items[index])

    def update(self, items: list):
        """Call once per frame (cheap: only rebuilds when something actually changed)."""
        self._items = items
        labels = [self._label_fn(it) for it in items]
        if labels != self._labels:
            self._rebuild_list(labels)
        if not items:
            self._clear_details()
            return
        self._draw_props(items[self._selected])

    # ---- list (left) -------------------------------------------------------
    def _rebuild_list(self, labels: list[str]):
        dpg.delete_item(self._list_box, children_only=True)
        self._rows.clear()
        self._labels = labels
        self._selected = min(self._selected, max(len(labels) - 1, 0))
        for i, label in enumerate(labels):
            tag = dpg.add_selectable(label=label, default_value=(i == self._selected),
                                     callback=self._on_click, user_data=i,
                                     parent=self._list_box, height=26)
            dpg.bind_item_theme(tag, self._theme)
            self._rows.append(tag)
        self._prop_keys = None

    def _on_click(self, _sender, _app_data, index):
        self.select(index)

    # ---- properties (right) ------------------------------------------------
    def _clear_details(self):
        if self._prop_keys != []:
            dpg.delete_item(self._detail_content, children_only=True)   # was _detail_box
            self._prop_keys, self._prop_tags = [], []

    def _draw_props(self, item):
        props = _props_of(item)
        keys = [k for k, _ in props]
        if keys != self._prop_keys:          # different element shape -> rebuild rows
            dpg.delete_item(self._detail_content, children_only=True)
            self._prop_tags = []
            # two aligned columns: property name | its value
            with dpg.table(header_row=False, parent=self._detail_content,
                           policy=dpg.mvTable_SizingFixedFit,
                           borders_innerV=False, borders_innerH=False, borders_outerH=False,
                           borders_outerV=False):
                dpg.add_table_column(width_fixed=True)      # names
                dpg.add_table_column(width_stretch=True, init_width_or_weight=1.0)   # values
                for key in keys:
                    with dpg.table_row():
                        dpg.add_text(key + ":", color=NAME_COLOR)
                        self._prop_tags.append(dpg.add_text(""))
            self._prop_keys = keys
        for tag, (_k, value) in zip(self._prop_tags, props):
            text = _fmt(value)
            if dpg.get_value(tag) != text:
                dpg.set_value(tag, text)
                dpg.configure_item(tag, color=VALUE_COLORS.get(text, DEFAULT_VALUE_COLOR))

    # ---- look --------------------------------------------------------------
    @staticmethod
    def _make_selectable_theme():
        with dpg.theme() as theme:
            with dpg.theme_component(dpg.mvSelectable):
                # dpg.add_theme_color(dpg.mvThemeCol_TableHeaderBg, (255, 130, 150, 255))

                
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, DETAIL_BG)
                dpg.add_theme_color(dpg.mvThemeCol_Header, DETAIL_BG)         # selected
                dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, (70, 190, 210, 255))
                dpg.add_theme_color(dpg.mvThemeCol_HeaderActive, (255, 90, 160, 255))
                dpg.add_theme_style(dpg.mvStyleVar_SelectableTextAlign, 0.0, 0.5)
                dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 0, 0,)
            # with dpg.theme_component(dpg.mvGroup):
            #     dpg.add_theme_color(dpg.mvThemeCol_Header, [55, 187, 25, 255])
            #     dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, [55, 217, 25, 255])

        return theme


# Demo: python master_detail.py
if __name__ == "__main__":
    import time

    @dataclasses.dataclass
    class Item:
        name: str
        enabled: bool = True
        size: tuple = (0, 0)
        note: str = ""

    data = {
        "Tab 1": [Item("alpha"), Item("beta", False)],
        "Tab 2": [Item("element 1", True, (80, 20), "first"),
                  Item("element 2", False, (120, 24)),
                  Item("element 3", True, (60, 18), "last")],
        "Tab 3": [],
    }

    dpg.create_context()

    dpg.show_documentation()
    dpg.show_style_editor()
    # dpg.show_debug()
    dpg.show_about()
    dpg.show_metrics()
    # dpg.show_font_manager()
    dpg.show_item_registry()

    dpg.create_viewport(title="MasterDetail demo", width=640, height=420)
    with dpg.window() as main:
        with dpg.tab_bar():
            views = {}
            for title in data:
                with dpg.tab(label=title) as tab:
                    views[title] = MasterDetail(tab, label_fn=lambda it: it.name)
    dpg.set_primary_window(main, True)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    while dpg.is_dearpygui_running():
        for title, view in views.items():
            view.update(data[title])
        dpg.render_dearpygui_frame()
        time.sleep(1 / 60)
    dpg.destroy_context()