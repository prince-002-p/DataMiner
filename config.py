# ===========================================
# SchoolMiner Configuration
# ===========================================

# ---------- Version ----------
VERSION = "6.5.0"

# ---------- Board ----------
BOARDS = ["cbse", "icse", "ib", "state-board", "pre-primary"]
BOARD = "cbse"

# ---------- State Filter ----------
STRICT_STATE = True
STATE = ""

# ---------- District ----------
DISTRICTS = []

# ---------- Export ----------
EXPORT = ["xlsx", "csv"]

# ---------- Data Selection ----------
FIELDS = []

# ---------- Browser ----------
HEADLESS = True
MAXIMIZE = True

# ---------- Delay & Speed Profiles ----------
WAIT = 4
IMPLICIT_WAIT = 10
PAGE_DELAY = 2

SPEED_PROFILES = {
    "safe": {"WAIT": 6, "IMPLICIT_WAIT": 15, "PAGE_DELAY": 4},
    "balanced": {"WAIT": 4, "IMPLICIT_WAIT": 10, "PAGE_DELAY": 2},
    "fast": {"WAIT": 2, "IMPLICIT_WAIT": 5, "PAGE_DELAY": 1}
}
SPEED_PROFILE = "balanced"

# ---------- Retry ----------
RETRY = 3

# ---------- Output Folder ----------
OUTPUT_FOLDER = "Output"
AUTO_FILENAME = True
SHOW_SUMMARY = True
LOG = True
GUI = True
REMEMBER_LAST_SELECTION = False
DEBUG = False
