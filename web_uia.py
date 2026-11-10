"""web_uia.py - list/select browser tabs and read web page input fields with pywinauto (UIA backend).

No Selenium, no debug port, no special launch: it talks to your NORMAL, already
logged-in Chrome / Edge / Firefox window through Windows UI Automation.

    python web_uia.py                      # list browser windows, tabs and fields of the active tab
    python web_uia.py --tab "GigaTest"     # select the tab whose title contains the text first

Limits to know about:
- Only the ACTIVE tab has a page tree. To read another tab, select it first.
- Chrome/Edge build the page accessibility tree lazily. If no fields show up, start the
  browser once with --force-renderer-accessibility, or open chrome://accessibility and
  turn on "Native accessibility API support". Firefox usually needs nothing.
- Rectangles come straight from UIA in SCREEN pixels (same space as WindowInfo.bounds and
  the overlay), so there is no approximation like with the Selenium version.
- Walking a big page is slow (hundreds of ms). Do it on demand, not every frame.
"""

import argparse
import re
import time
from dataclasses import dataclass, field

from pywinauto import Desktop
from pywinauto.keyboard import send_keys

BROWSER_CLASSES = {"Chrome_WidgetWin_1", "MozillaWindowClass"}   # Chrome/Edge, Firefox
BROWSER_TITLE_RE = r"(Chrome|Edge|Firefox)"
FIELD_TYPES = ("Edit",)          # add "ComboBox", "CheckBox", ... if you need them

PLANILLAS_TITLE = "Lista de Planillas"   # text that identifies the tab (matched inside the tab title)
PLANILLAS_URL = "https://rto.cent.ar/rto/RTO/listaDePlanillas"                       # TODO: URL to open when the tab is not found (empty = don't open)

NUEVA_RTO_TITLE = "RTO"
NUEVA_RTO_URL = "https://rto.cent.ar/rto/#"

@dataclass
class BrowserTabInfo:
    index: int = 0
    title: str = ""
    is_active: bool = False
    bounds: tuple = ()


@dataclass
class FieldInfo:
    index: int = 0
    name: str = ""               # accessible name = usually the label of the field
    auto_id: str = ""            # HTML id of the element (Chrome/Edge expose it as AutomationId)
    value: str = ""
    control_type: str = ""
    is_enabled: bool = False
    is_readonly: bool = False
    is_visible: bool = False
    bounds: tuple = ()           # (left, top, right, bottom) in screen pixels


@dataclass
class RowInfo:
    index: int = 0
    text: str = ""               # accessible name of the DataItem (may be empty)
    bounds: tuple = ()           # (left, top, right, bottom) in screen pixels
    cells: list = field(default_factory=list)   # texts of the direct children (only if requested)


# ---- helpers ---------------------------------------------------------------
def _rect(wrapper) -> tuple:
    r = wrapper.rectangle()
    return (r.left, r.top, r.right, r.bottom)


def _is_selected(tab) -> bool:
    try:
        return bool(tab.is_selected())
    except Exception:
        try:
            return bool(tab.iface_selection_item.CurrentIsSelected)
        except Exception:
            return False


def _is_offscreen(wrapper) -> bool:
    try:
        return bool(wrapper.element_info.element.CurrentIsOffscreen)
    except Exception:
        return False


# ---- browser windows -------------------------------------------------------
def find_browser_windows() -> list:
    """UIA wrappers of every top-level Chrome / Edge / Firefox window."""
    windows = []
    for w in Desktop(backend="uia").windows():
        try:
            if w.class_name() in BROWSER_CLASSES and re.search(BROWSER_TITLE_RE, w.window_text()):
                windows.append(w)
        except Exception:
            continue                      # window closed while enumerating
    return windows


def find_browser_window(title_contains: str | None = None):
    """First browser window (optionally whose title contains the text)."""
    for w in find_browser_windows():
        if not title_contains or title_contains.lower() in w.window_text().lower():
            return w
    return None

"""
INTERFACE  
"""
# ---- tabs ------------------------------------------------------------------
def list_tabs(win) -> list[BrowserTabInfo]:
    return [
        BrowserTabInfo(index=i, title=t.window_text(), is_active=_is_selected(t), bounds=_rect(t))
        for i, t in enumerate(win.descendants(control_type="TabItem"))
    ]


def select_tab(win, text: str, settle: float = 0.3) -> BrowserTabInfo | None:
    """Select the first tab whose title contains the text (case-insensitive).
    Returns its info, or None if nothing matches."""
    text = text.lower()
    for i, tab in enumerate(win.descendants(control_type="TabItem")):
        if text not in tab.window_text().lower():
            continue
        try:
            tab.select()                  # UIA SelectionItem: no real mouse movement
        except Exception:
            pass
        time.sleep(settle)                # let the browser swap the page tree
        if not _is_selected(tab):         # select() can "succeed" without switching (seen in Firefox)
            tab.click_input()             # fallback: real click on the tab
            time.sleep(settle)
        return BrowserTabInfo(index=i, title=tab.window_text(), is_active=_is_selected(tab), bounds=_rect(tab))
    return None


def _escape_keys(text: str) -> str:
    """Escape the characters that pywinauto's send_keys treats as commands."""
    return "".join("{" + c + "}" if c in "{}+^%~()[]" else c for c in text)


def open_url_in_new_tab(win, url: str) -> None:
    """Ctrl+T, focus the address bar (Ctrl+L), type the URL, Enter. Uses the real keyboard."""
    win.set_focus()
    send_keys("^t")
    time.sleep(0.4)
    send_keys("^l")
    time.sleep(0.1)
    send_keys(_escape_keys(url) + "{ENTER}", with_spaces=True, pause=0.01)


def ensure_tab(win, title: str, url: str | None = None, timeout: float = 15.0) -> BrowserTabInfo | None:
    """Select the tab whose title contains `title`. If it doesn't exist and a URL is given,
    open the URL in a new tab and wait until a tab with that title appears.
    Returns the tab, or None (not found / timed out)."""
    tab = select_tab(win, title)
    if tab or not url:
        return tab
    open_url_in_new_tab(win, url)
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(0.5)
        tab = select_tab(win, title)
        if tab:
            return tab
    return None


# ---- page fields -----------------------------------------------------------
def get_document(win, title: str | None = None):
    """The page of the active tab (UIA 'Document' control), or None.
    Documents of background tabs (offscreen) are ignored. If `title` is given, only
    documents whose name (= page title) contains it are considered, when any match."""
    docs = []
    for d in win.descendants(control_type="Document"):
        if _is_offscreen(d):
            continue
        left, top, right, bottom = _rect(d)
        area = (right - left) * (bottom - top)
        if area > 0:
            docs.append((d, area))
    if title:
        named = [(d, a) for d, a in docs if title.lower() in (d.element_info.name or "").lower()]
        if named:
            docs = named
    return max(docs, key=lambda x: x[1])[0] if docs else None


def get_page_document(win, title: str | None = None):
    """The Document of the page whose name (= page title) contains `title`.
    Falls back to the largest visible Document if none matches or no title is given."""
    return get_document(win, title)


def get_data_items(doc, with_cells: bool = False) -> list[RowInfo]:
    """Every 'DataItem' (table / grid row) inside a page document, with screen bounds.
    with_cells=True also reads the text of each row's direct children (slower)."""
    rows = []
    for i, el in enumerate(doc.descendants(control_type="DataItem")):
        cells = [c.window_text() for c in el.children()] if with_cells else []
        rows.append(RowInfo(index=i, text=el.window_text(), bounds=_rect(el), cells=cells))
    return rows


def get_fields(win, control_types: tuple = FIELD_TYPES, title: str | None = None) -> list[FieldInfo]:
    """Input fields of the active tab, with screen bounds.
    title: page title text, to pick the right document if several are exposed."""
    doc = get_document(win, title)
    if doc is None:
        return []
    fields = []
    for ct in control_types:
        for el in doc.descendants(control_type=ct):
            try:
                value = el.iface_value.CurrentValue
                readonly = bool(el.iface_value.CurrentIsReadOnly)
            except Exception:
                value, readonly = el.window_text(), False
            bounds = _rect(el)
            fields.append(FieldInfo(
                index=len(fields),
                name=el.element_info.name or "",
                auto_id=el.element_info.automation_id or "",
                value=value or "",
                control_type=ct,
                is_enabled=el.is_enabled(),
                is_readonly=readonly,
                is_visible=(bounds[2] > bounds[0] and bounds[3] > bounds[1] and not _is_offscreen(el)),
                bounds=bounds,
            ))
    fields.sort(key=lambda f: (round(f.bounds[1] / 8), f.bounds[0]))     # rows, then columns
    for i, f in enumerate(fields):
        f.index = i
    return fields


def find_field(win, auto_id: str | None = None, name: str | None = None,
               control_types: tuple = FIELD_TYPES, title: str | None = None) -> FieldInfo | None:
    """First field whose HTML id (auto_id) or accessible name matches exactly, or None."""
    for f in get_fields(win, control_types, title):
        if (auto_id and f.auto_id == auto_id) or (name and f.name == name):
            return f
    return None


def set_field_value(win, index: int, text: str, control_types: tuple = FIELD_TYPES,
                    title: str | None = None) -> bool:
    """Write text into the field with this index (same order as get_fields)."""
    doc = get_document(win, title)
    if doc is None:
        return False
    elements = []
    for ct in control_types:
        elements += doc.descendants(control_type=ct)
    elements.sort(key=lambda e: (round(_rect(e)[1] / 8), _rect(e)[0]))
    if not (0 <= index < len(elements)):
        return False
    el = elements[index]
    try:
        el.iface_value.SetValue(text)     # fast, no focus needed; some JS frameworks ignore it
        return True
    except Exception:
        el.click_input()                  # fallback: click and type like a person
        el.type_keys("^a" + text, with_spaces=True)
        return True


# ---- Lista de Planillas ----------------------------------------------------
def lista(win=None, url: str = PLANILLAS_URL, title: str = PLANILLAS_TITLE,
          with_cells: bool = False, print_output = False) -> list[RowInfo]:
    """Find the 'Lista de Planillas' tab (open it from `url` if missing) and read its rows."""
    win = win or find_browser_window("Firefox")
    if win is None:
        raise RuntimeError("No Firefox window found.")
    if ensure_tab(win, title, url) is None:
        raise RuntimeError(f"Tab {title!r} not found" + ("" if url else " (and no URL set to open it)."))

    doc = get_page_document(win, title)
    if doc is None:
        raise RuntimeError("The tab has no page document (accessibility tree not ready?).")

    rows = get_data_items(doc, with_cells)
    if print_output:
        for row in rows:
            print(repr(row.text), row.bounds)
            if row.text == "":
                print("/--------------------")
    return rows

# ---- RTO (Página de Consulta) ----------------------------------------------------
# TODO:


# ---- demo ------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="List browser tabs and page fields through UI Automation.")
    parser.add_argument("--window", help="only browser windows whose title contains this text")
    parser.add_argument("--tab", help="select the tab whose title contains this text")
    parser.add_argument("--lista", action="store_true", help="read the rows of the 'Lista de Planillas' tab")
    parser.add_argument("--url", default=PLANILLAS_URL, help="with --lista: URL to open if the tab is missing")
    args = parser.parse_args()

    win = find_browser_window(args.window)
    if win is None:
        raise SystemExit("No Chrome / Edge / Firefox window found.")
    print(f"Browser window: {win.window_text()!r}")

    if args.lista:
        lista(win, url=args.url)
        return

    tabs = list_tabs(win)
    print(f"\n{len(tabs)} tabs\n")
    for t in tabs:
        print(("* " if t.is_active else "  ") + f"[{t.index}] {t.title!r}")

    if args.tab:
        tab = select_tab(win, args.tab)
        if tab is None:
            raise SystemExit(f"No tab matching {args.tab!r}")
        print(f"\nSelected tab: {tab.title!r}")

    fields = get_fields(win)
    print(f"\n{len(fields)} fields found\n")
    for f in fields:
        state = "enabled" if f.is_enabled else "DISABLED"
        if f.is_readonly:
            state += ", readonly"
        if not f.is_visible:
            state += ", hidden"
        print(f"[{f.index}] <{f.control_type}> {f.name or '(no name)'} id={f.auto_id!r} = {f.value!r}  [{state}]")
        print(f"     screen={f.bounds}")


if __name__ == "__main__":
    main()