"""web_elements.py - find input fields on a web page in Firefox (with your profile)
and read their positions. Disabled / readonly / hidden fields are included: they
stay in the DOM, so they can be found and (if rendered) measured.

    pip install selenium        # Selenium 4.6+ downloads geckodriver by itself

    python web_elements.py https://example.com
    python web_elements.py https://example.com --copy-profile      # safer: uses a copy
    python web_elements.py https://example.com --profile "C:\\path\\to\\profile"

Close Firefox before running: a profile can only be used by one instance.
"""


import argparse
import configparser
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
 
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options as FirefoxOptions
 
FIREFOX_DIR = Path(os.environ.get("APPDATA", "")) / "Mozilla" / "Firefox"
CHROME_USER_DATA = Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data"
 



@dataclass
class ElementInfo:
    index: int = 0
    tag: str = ""
    type: str = ""
    id: str = ""
    name: str = ""
    placeholder: str = ""
    value: str = ""
    is_visible: bool = False
    is_enabled: bool = False
    is_readonly: bool = False
    bounds: tuple = ()          # (left, top, right, bottom) relative to the viewport
    screen_bounds: tuple = ()   # approximate screen coordinates (for an overlay)


# Runs in the browser: reads everything in one round trip per element.
_JS_INFO = """
el => {
  const r = el.getBoundingClientRect();
  const cs = getComputedStyle(el);
  const dpr = window.devicePixelRatio || 1;
  const chromeTop = window.outerHeight - window.innerHeight;   // tabs + address bar (approx.)
  const sx = window.screenX, sy = window.screenY + chromeTop;
  return {
    tag: el.tagName.toLowerCase(),
    type: el.type || "",
    id: el.id || "",
    name: el.name || "",
    placeholder: el.placeholder || "",
    value: el.value || "",
    visible: r.width > 0 && r.height > 0 && cs.visibility !== "hidden" && cs.display !== "none",
    enabled: !el.disabled,
    readonly: !!el.readOnly,
    rect: [r.left, r.top, r.right, r.bottom],
    screen: [(r.left + sx) * dpr, (r.top + sy) * dpr, (r.right + sx) * dpr, (r.bottom + sy) * dpr],
  };
}
"""


# ---- Firefoxprofile ---------------------------------------------------------------
def find_default_firefox_profile() -> Path | None:
    """Default profile folder, read from Firefox's profiles.ini."""
    ini = FIREFOX_DIR / "profiles.ini"
    if not ini.exists():
        return None
    cfg = configparser.ConfigParser()
    cfg.read(ini, encoding="utf-8")

    def resolve(section):
        path = cfg[section].get("Path")
        if not path:
            return None
        return (FIREFOX_DIR / path) if cfg[section].get("IsRelative", "1") == "1" else Path(path)

    for section in cfg.sections():                      # newer Firefox: [Install...] Default=
        if section.startswith("Install") and cfg[section].get("Default"):
            return FIREFOX_DIR / cfg[section]["Default"]
    for section in cfg.sections():                      # older: [ProfileN] Default=1
        if section.startswith("Profile") and cfg[section].get("Default") == "1":
            return resolve(section)
    return None


def copy_firefox_profile(src: Path) -> Path:
    """Copy a profile to a temp folder (without locks and caches) so the original stays untouched."""
    dst = Path(tempfile.mkdtemp(prefix="ff_profile_")) / src.name
    shutil.copytree(
        src, dst,
        ignore=shutil.ignore_patterns("parent.lock", "lock", ".parentlock", "cache2", "startupCache", "storage"),
    )
    return dst

# ---- Chrome profile ---------------------------------------------------------------
def copy_chrome_profile(user_data_dir: Path, profile_name: str) -> Path:
    """Copy one Chrome profile (+ Local State) into a temp 'User Data' folder; returns that folder."""
    dst = Path(tempfile.mkdtemp(prefix="chrome_profile_")) / "User Data"
    dst.mkdir(parents=True)
    local_state = user_data_dir / "Local State"
    if local_state.exists():
        shutil.copy2(local_state, dst / "Local State")
    shutil.copytree(
        user_data_dir / profile_name, dst / profile_name,
        ignore=shutil.ignore_patterns(
            "Cache", "Code Cache", "GPUCache", "DawnCache", "Service Worker", "Crashpad",
            "SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile"),
    )
    return dst


# ---- browser ---------------------------------------------------------------
def open_firefox(url: str, profile: Path | None = None, headless: bool = False) -> webdriver.Firefox:
    options = FirefoxOptions()
    if headless:
        options.add_argument("-headless")
    if profile:
        options.add_argument("-profile")
        options.add_argument(str(profile))
    driver = webdriver.Firefox(options=options)
    driver.get(url)
    return driver


def open_chrome(url: str, user_data_dir: Path | None = None, profile_name: str = "Default",
                headless: bool = False) -> webdriver.Chrome:
    options = ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    if user_data_dir:
        options.add_argument(f"--user-data-dir={user_data_dir}")
        options.add_argument(f"--profile-directory={profile_name}")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    driver = webdriver.Chrome(options=options)
    driver.get(url)
    return driver


# ---- elements --------------------------------------------------------------
def get_inputs(driver, selector: str = "input, textarea, select") -> list[ElementInfo]:
    """Every matching element in the page, disabled and hidden ones included."""
    result = []
    for i, el in enumerate(driver.find_elements(By.CSS_SELECTOR, selector)):
        d = driver.execute_script(f"return ({_JS_INFO})(arguments[0]);", el)
        result.append(ElementInfo(
            index=i,
            tag=d["tag"],
            type=d["type"],
            id=d["id"],
            name=d["name"],
            placeholder=d["placeholder"],
            value=d["value"],
            is_visible=d["visible"],
            is_enabled=d["enabled"],
            is_readonly=d["readonly"],
            bounds=tuple(round(v, 1) for v in d["rect"]),
            screen_bounds=tuple(round(v) for v in d["screen"]),
        ))
    return result


def find_by_name(infos: list[ElementInfo], name: str) -> ElementInfo | None:
    """First element whose id or name matches."""
    return next((e for e in infos if name in (e.id, e.name)), None)


# ---- demo ------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="List input fields and positions in Firefox or Chrome.")
    parser.add_argument("url", nargs="?", default="https://example.com")
    parser.add_argument("--browser", choices=["firefox", "chrome"], default="firefox")
    parser.add_argument("--profile", help="Firefox: profile folder. Chrome: 'User Data' folder (default: auto-detect)")
    parser.add_argument("--chrome-profile-name", default="Default",
                        help="Chrome profile inside 'User Data' (Default, Profile 1, ...)")
    parser.add_argument("--copy-profile", action="store_true", help="use a temporary copy of the profile")
    parser.add_argument("--no-profile", action="store_true", help="start with a clean temporary profile")
    args = parser.parse_args()
 
    if args.browser == "firefox":
        profile = None
        if not args.no_profile:
            profile = Path(args.profile) if args.profile else find_default_firefox_profile()
            if profile is None:
                raise SystemExit("Could not find a Firefox profile. Pass --profile or use --no-profile.")
            if args.copy_profile:
                print(f"Copying profile {profile} ...")
                profile = copy_firefox_profile(profile)
            print(f"Using profile: {profile}")
        driver = open_firefox(args.url, profile)
    else:
        user_data = None
        if not args.no_profile:
            user_data = Path(args.profile) if args.profile else CHROME_USER_DATA
            if not (user_data / args.chrome_profile_name).exists():
                raise SystemExit(f"Chrome profile not found: {user_data / args.chrome_profile_name}")
            if args.copy_profile:
                print(f"Copying Chrome profile '{args.chrome_profile_name}' ...")
                user_data = copy_chrome_profile(user_data, args.chrome_profile_name)
            print(f"Using user data dir: {user_data}")
        driver = open_chrome(args.url, user_data, args.chrome_profile_name)
 
    try:
        inputs = get_inputs(driver)
        print(f"\n{len(inputs)} fields found\n")
        for e in inputs:
            state = "enabled" if e.is_enabled else "DISABLED"
            if e.is_readonly:
                state += ", readonly"
            if not e.is_visible:
                state += ", hidden"
            label = e.id or e.name or e.placeholder or "(no id/name)"
            print(f"[{e.index}] <{e.tag} type={e.type!r}> {label}  [{state}]")
            print(f"     viewport={e.bounds}  screen~={e.screen_bounds}")
        input("\nPress Enter to close the browser...")
    finally:
        driver.quit()







if __name__ == "__main__":
    main()