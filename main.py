# ===========================================
# SchoolMiner v6.5 Enterprise
# Main Engine File (Backwards Compatible Facade)
# ===========================================

import json
import os
import platform
import re
import subprocess
import time
from collections import Counter

import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

try:
    import config
except Exception:
    config_path = os.path.join(os.getcwd(), "config.py")
    default_content = """# ===========================================
# SchoolMiner Configuration
# ===========================================
VERSION = "6.5.0"
BOARDS = ["cbse", "icse", "ib", "state-board", "pre-primary"]
BOARD = "cbse"
STRICT_STATE = True
STATE = ""
DISTRICTS = []
EXPORT = ["xlsx", "csv"]
FIELDS = []
HEADLESS = True
MAXIMIZE = True
WAIT = 4
IMPLICIT_WAIT = 10
PAGE_DELAY = 2
RETRY = 3
OUTPUT_FOLDER = "Output"
AUTO_FILENAME = True
SHOW_SUMMARY = True
LOG = True
GUI = True
SPEED_PROFILE = "balanced"
DEBUG = False
"""
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(default_content)
    except Exception:
        pass
    import config

# Load state registry strictly from bundled JSON file (sole source of truth)
registry_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "states_registry.json")
if not os.path.exists(registry_path):
    raise FileNotFoundError(f"Critical Error: State registry file 'states_registry.json' not found at {registry_path}. Application cannot launch.")

try:
    with open(registry_path, "r", encoding="utf-8") as f:
        STATES_MAP = json.load(f)
except Exception as e:
    raise RuntimeError(f"Critical Error: Failed to parse 'states_registry.json': {e}")

BOARD = "cbse"
STATE = ""
REMEMBER_LAST_SELECTION = False

SPEED_PROFILES = {
    "safe": {"WAIT": 6, "IMPLICIT_WAIT": 15, "PAGE_DELAY": 4},
    "balanced": {"WAIT": 4, "IMPLICIT_WAIT": 10, "PAGE_DELAY": 2},
    "fast": {"WAIT": 2, "IMPLICIT_WAIT": 5, "PAGE_DELAY": 1}
}

# Import modular layers
from adapters.schoolsindia_adapter import SchoolsIndiaAdapter
from parsers.schoolsindia_parser import SchoolsIndiaParser
from district_loader import DistrictLoader
from engine import ScraperEngine
from health_check import HealthCheckService, verify_site_compatibility

seen_schools = set()
stats = {
    "districts": 0,
    "pages": 0,
    "schools_found": 0,
    "exported": 0,
    "duplicates": 0,
    "wrong_state": 0,
    "errors": 0,
}

def sync_config():
    """Synchronizes main module variables with config.py at runtime."""
    global BOARDS, STRICT_STATE, DISTRICTS, EXPORT, FIELDS, HEADLESS, MAXIMIZE
    global WAIT, IMPLICIT_WAIT, PAGE_DELAY, RETRY, OUTPUT_FOLDER, AUTO_FILENAME, SHOW_SUMMARY, LOG, GUI, VERSION, SPEED_PROFILE, DEBUG
    import config
    import importlib
    try:
        importlib.reload(config)
    except Exception:
        pass
    BOARDS = getattr(config, "BOARDS", ["cbse", "icse", "ib", "state-board", "pre-primary"])
    STRICT_STATE = getattr(config, "STRICT_STATE", True)
    DISTRICTS = getattr(config, "DISTRICTS", [])
    EXPORT = getattr(config, "EXPORT", ["xlsx", "csv"])
    FIELDS = getattr(config, "FIELDS", [])
    HEADLESS = getattr(config, "HEADLESS", True)
    MAXIMIZE = getattr(config, "MAXIMIZE", True)
    WAIT = getattr(config, "WAIT", 4)
    IMPLICIT_WAIT = getattr(config, "IMPLICIT_WAIT", 10)
    PAGE_DELAY = getattr(config, "PAGE_DELAY", 2)
    RETRY = getattr(config, "RETRY", 3)
    OUTPUT_FOLDER = getattr(config, "OUTPUT_FOLDER", "Output")
    AUTO_FILENAME = getattr(config, "AUTO_FILENAME", True)
    SHOW_SUMMARY = getattr(config, "SHOW_SUMMARY", True)
    LOG = getattr(config, "LOG", True)
    GUI = getattr(config, "GUI", True)
    VERSION = getattr(config, "VERSION", "6.5.0")
    SPEED_PROFILE = getattr(config, "SPEED_PROFILE", "balanced")
    DEBUG = getattr(config, "DEBUG", False)

sync_config()

def sanitize_slug(text):
    """Sanitizes text to lowercase, hyphen-separated alphanumeric slug."""
    if not text:
        return ""
    text = str(text).lower().strip()
    text = text.replace(" ", "-").replace("_", "-")
    text = re.sub(r"[^a-z0-9\-]", "", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")

def generate_export_filename(state_input, selected_districts, total_available_count=None):
    """
    Generates clean export filename base.
    """
    clean_state = sanitize_slug(state_input) or "all-states"
    
    if isinstance(selected_districts, str):
        dists = [sanitize_slug(selected_districts)] if selected_districts.strip() else []
    elif isinstance(selected_districts, (list, tuple, set)):
        dists = [sanitize_slug(d) for d in selected_districts if d]
        dists = [d for d in dists if d]
    else:
        dists = []
        
    num_selected = len(dists)
    is_all = (num_selected == 0) or (total_available_count is not None and total_available_count > 0 and num_selected >= total_available_count)
    
    if is_all:
        return f"{clean_state}_all"
    elif num_selected == 1:
        return f"{clean_state}_{dists[0]}"
    elif num_selected == 2:
        return f"{clean_state}_{dists[0]}_{dists[1]}"
    else:
        return f"{clean_state}_{num_selected}-districts"

def validate_slug_format(display_name, slug):
    """Validates that a state slug matches the display name format."""
    if not slug:
        return False, "Slug is empty."
    if slug != slug.lower():
        return False, f"Slug '{slug}' is not completely lowercase."
    if " " in slug:
        return False, f"Slug '{slug}' contains spaces."
        
    clean_display = "".join(c for c in display_name.lower().replace(" and ", " ").split() for c in c if c.isalpha())
    clean_slug = "".join(c for c in slug.lower().replace("-and-", "-").split("-") for c in c if c.isalpha())
    
    d_count = Counter(clean_display)
    s_count = Counter(clean_slug)
    
    missing_consonants = []
    for char, count in d_count.items():
        if char in "bcdfghjklmnpqrstvwxyz" and s_count[char] < count:
            missing_consonants.append(char)
            
    if missing_consonants:
        return False, f"Slug is missing expected characters from name: {missing_consonants}"
        
    return True, ""

def validate_all_states():
    """Runs internal validation of all supported state mappings."""
    print("[INFO] Starting internal validation of supported states...")
    errors = []
    for display_name, slug in STATES_MAP.items():
        is_valid, reason = validate_slug_format(display_name, slug)
        if not is_valid:
            errors.append(f"State '{display_name}' with slug '{slug}' is invalid: {reason}")
        else:
            adapter = SchoolsIndiaAdapter()
            expected_url = adapter.build_state_url(BOARD, slug)
            print(f"[VALIDATION] State: '{display_name}' -> Slug: '{slug}' -> URL: '{expected_url}'")
            
    if errors:
        raise Exception(f"State mapping validation failed with errors:\n" + "\n".join(errors))
    print("[INFO] Internal validation of all supported states: SUCCESS.")

def show_banner():
    print("=" * 60)
    print(f"[START] SchoolMiner v{VERSION}")
    print("=" * 60)
    print(f"Board      : {BOARD}")
    print(f"State      : {STATE}")

    if DISTRICTS:
        print(f"Districts  : {', '.join(DISTRICTS)}")
    else:
        print("Districts  : ALL")

    print("=" * 60)

def debug(*args):
    if DEBUG:
        print(*args)

def create_output_folder():
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    print(f"\n[FOLDER] Output Folder : {OUTPUT_FOLDER}")

def start_browser():
    sync_config()
    options = webdriver.ChromeOptions()
    
    options.add_argument("--log-level=3")
    options.add_argument("--silent")
    options.add_argument("--disable-logging")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    if getattr(config, "HEADLESS", True):
        options.add_argument("--headless=new")
    else:
        options.add_argument("--window-position=-32000,-32000")
        options.add_argument("--window-size=10,10")

    service = Service(ChromeDriverManager().install())
    if platform.system() == "Windows":
        service.creation_flags = subprocess.CREATE_NO_WINDOW

    driver = webdriver.Chrome(service=service, options=options)

    if getattr(config, "HEADLESS", True):
        if getattr(config, "MAXIMIZE", True):
            try:
                driver.maximize_window()
            except Exception:
                pass
    else:
        try:
            driver.minimize_window()
        except Exception:
            pass

    driver.implicitly_wait(getattr(config, "IMPLICIT_WAIT", 10))
    return driver

def get_districts(driver, state_obj=None, board="cbse"):
    """Backwards-compatible district loading facade delegating to SchoolsIndiaAdapter."""
    sync_config()
    
    if state_obj:
        display_name = state_obj.get("display_name")
        selected_slug = state_obj.get("slug")
    else:
        selected_slug = STATE
        display_name = "Unknown"
        for k, v in STATES_MAP.items():
            if v == selected_slug:
                display_name = k
                break
                
    expected_slug = STATES_MAP.get(display_name)
    if not expected_slug or expected_slug != selected_slug:
        raise Exception(
            f"State validation failure! Aborting loading to prevent wrong district association.\n"
            f"Selected Display Name: '{display_name}'\n"
            f"Expected Slug: '{expected_slug}'\n"
            f"Active Slug: '{selected_slug}'"
        )

    adapter = SchoolsIndiaAdapter()
    return adapter.load_districts(driver, board, selected_slug, display_name=display_name)

def filter_districts(districts, selected_names=None):
    """Filter district list by selected names."""
    target_list = selected_names if selected_names is not None else DISTRICTS
    if not target_list:
        print("\n📍 All districts selected.")
        return districts

    selected = [d.lower() for d in target_list]
    filtered = [d for d in districts if d["name"].lower() in selected]
    print(f"\n📍 Selected Districts : {len(filtered)} / {len(districts)}")
    return filtered

def select_fields():
    all_fields = [
        "School Name",
        "Address",
        "District",
        "State",
        "Landline",
        "Mobile",
        "Email",
        "Website",
    ]

    print("\n" + "=" * 60)
    print("[LIST] Select Data to Export")
    print("=" * 60)

    for i, field in enumerate(all_fields, start=1):
        print(f"{i}. {field}")

    print("9. All Fields")

    choice = input("\nEnter choice (Example: 1,6,7 or 9): ").strip()

    if choice == "9":
        return all_fields

    selected = []

    try:
        numbers = [int(x.strip()) for x in choice.split(",")]
        for n in numbers:
            if 1 <= n <= len(all_fields):
                selected.append(all_fields[n - 1])
    except (ValueError, AttributeError):
        print("⚠ Invalid choice.")
        return all_fields

    return selected if selected else all_fields

def split_phone(phone_text):
    parser = SchoolsIndiaParser()
    return parser.split_phone_numbers(phone_text)

def scrape_district(driver, district, state_slug=None, stop_flag=None, pause_event=None, progress_callback=None):
    """Backwards-compatible district scraping facade delegating to ScraperEngine."""
    engine = ScraperEngine(start_browser)
    # Synchronize stats dictionary reference
    engine.stats = stats
    engine.seen_schools = seen_schools
    result = engine.scrape_district(
        driver, 
        district, 
        state_slug=state_slug, 
        stop_flag=stop_flag, 
        pause_event=pause_event, 
        progress_callback=progress_callback
    )
    # Update global stats
    for k, v in engine.stats.items():
        stats[k] = v
    return result

def main():
    if GUI:
        print("Launching SchoolMiner Desktop GUI...")
        from gui import SchoolMinerGUI
        app = SchoolMinerGUI()
        app.mainloop()
        return

    start_time = time.time()
    show_banner()
    selected_fields = select_fields()

    print("\nSelected Fields:")
    print(selected_fields)

    create_output_folder()
    driver = start_browser()
    print("\n[SUCCESS] Browser Started Successfully!")

    districts = get_districts(driver)
    districts = filter_districts(districts)

    stats["districts"] = len(districts)
    print("\nSelected Districts:")

    all_data = []
    for district in districts:
        data = scrape_district(driver, district)
        all_data.extend(data)

    df = pd.DataFrame(all_data)
    print("\n[LIST] Columns Found:")
    print(df.columns.tolist())

    df = df[selected_fields]
    stats["exported"] = len(df)

    end_time = time.time()
    total_time = round(end_time - start_time, 2)
    formatted_time = f"{round(total_time)} sec" if total_time < 60 else f"{int(total_time // 60)} min {int(total_time % 60)} sec"

    print("\n" + "=" * 45)
    print("[STATS] SCRAPING SUMMARY")
    print("=" * 45)
    print(f"{'Board':18}: {BOARD}")
    print(f"{'State':18}: {STATE}")
    print(f"{'District(s)':18}: {', '.join(DISTRICTS) if DISTRICTS else 'ALL'}")
    print(f"{'District Count':18}: {stats['districts']}")
    print(f"{'Pages Visited':18}: {stats['pages']}")
    print(f"{'Schools Found':18}: {stats['schools_found']}")
    print(f"{'Wrong State':18}: {stats['wrong_state']}")
    print(f"{'Duplicates':18}: {stats['duplicates']}")
    print(f"{'Errors':18}: {stats['errors']}")
    print(f"{'Rows Exported':18}: {stats['exported']}")
    print(f"{'Columns':18}: {len(df.columns)}")
    print(f"{'Time Taken':18}: {formatted_time}")
    print("=" * 45)

    total_available = len(districts) if 'districts' in locals() else None
    filename = generate_export_filename(STATE, DISTRICTS, total_available_count=total_available)

    if "xlsx" in EXPORT:
        excel_file = os.path.join(OUTPUT_FOLDER, filename + ".xlsx")
        df.to_excel(excel_file, index=False)
        print(f"\n[SUCCESS] Excel Saved : {excel_file}")

    if "csv" in EXPORT:
        csv_file = os.path.join(OUTPUT_FOLDER, filename + ".csv")
        df.to_csv(csv_file, index=False)
        print(f"[SUCCESS] CSV Saved : {csv_file}")

    driver.quit()
    print("\n[SUCCESS] Browser Closed")

if __name__ == "__main__":
    main()
