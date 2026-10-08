import os
import sys
import time
import queue
import logging
import threading
import datetime
import json
import platform
import re
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

import tkinter as tk
from tkinter import filedialog
import tkinter.messagebox as messagebox
import customtkinter

# Import config constants with recovery validation and main functions
import os
import json

try:
    import config
except Exception:
    config_path = os.path.join(os.getcwd(), "config.py")
    default_content = """# ===========================================
# SchoolMiner Configuration
# ===========================================
BOARD = "cbse"
BOARDS = ["cbse", "icse", "ib", "state-board", "pre-primary"]
STRICT_STATE = True
STATE = "himachal-pradesh"
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
VERSION = "6.0.1"
DEBUG = False
"""
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(default_content)
    except Exception:
        pass
    import config

def validate_and_recover_config():
    """Validates configuration parameters and restores defaults if corrupted or missing."""
    defaults = {
        "BOARDS": ["cbse", "icse", "ib", "state-board", "pre-primary"],
        "STRICT_STATE": True,
        "DISTRICTS": [],
        "EXPORT": ["xlsx", "csv"],
        "FIELDS": [],
        "HEADLESS": True,
        "MAXIMIZE": True,
        "WAIT": 4,
        "IMPLICIT_WAIT": 10,
        "PAGE_DELAY": 2,
        "RETRY": 3,
        "OUTPUT_FOLDER": "Output",
        "AUTO_FILENAME": True,
        "SHOW_SUMMARY": True,
        "LOG": True,
        "GUI": True,
        "VERSION": "6.0.1",
        "SPEED_PROFILE": "balanced",
        "DEBUG": False
    }
    
    modified = False
    for key, val in defaults.items():
        if not hasattr(config, key):
            setattr(config, key, val)
            modified = True
        else:
            curr_val = getattr(config, key)
            if type(curr_val) != type(val) and curr_val is not None:
                setattr(config, key, val)
                modified = True
            elif key == "VERSION" and not curr_val:
                setattr(config, key, val)
                modified = True
                
    if modified:
        try:
            config_path = os.path.join(os.getcwd(), "config.py")
            content = f"""# ===========================================
# SchoolMiner Configuration
# ===========================================

# ---------- Board ----------
BOARDS = {config.BOARDS}

# ---------- State Filter ----------
STRICT_STATE = {config.STRICT_STATE}

# ---------- District ----------
DISTRICTS = {config.DISTRICTS}

# ---------- Export ----------
EXPORT = {config.EXPORT}

# ---------- Data Selection ----------
FIELDS = {config.FIELDS}

# ---------- Browser ----------
HEADLESS = {config.HEADLESS}
MAXIMIZE = {config.MAXIMIZE}

# ---------- Delay ----------
WAIT = {config.WAIT}
IMPLICIT_WAIT = {config.IMPLICIT_WAIT}
PAGE_DELAY = {config.PAGE_DELAY}

# ---------- Retry ----------
RETRY = {config.RETRY}

# ---------- Output Folder ----------
OUTPUT_FOLDER = "{config.OUTPUT_FOLDER}"
AUTO_FILENAME = {config.AUTO_FILENAME}
SHOW_SUMMARY = {config.SHOW_SUMMARY}
LOG = {config.LOG}
GUI = {config.GUI}
VERSION = "{config.VERSION}"
SPEED_PROFILE = "{getattr(config, 'SPEED_PROFILE', 'balanced')}"
DEBUG = {config.DEBUG}
"""
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception:
            pass

validate_and_recover_config()

import main

# Theme configurations
customtkinter.set_appearance_mode("dark")
customtkinter.set_default_color_theme("blue")

FIELD_MAP = {
    "School Name": "School Name",
    "UDISE": "UDISE",
    "Affiliation Number": "Affiliation Number",
    "Address": "Address",
    "Village": "Village",
    "City": "City",
    "District": "District",
    "State": "State",
    "PIN Code": "PIN Code",
    "Phone": "Landline",
    "Mobile": "Mobile",
    "Email": "Email",
    "Website": "Website",
    "Principal": "Principal",
    "Category": "Category",
    "Management": "Management",
    "School Type": "School Type",
    "Medium": "Medium",
    "Latitude": "Latitude",
    "Longitude": "Longitude",
    "Established Year": "Established Year"
}

# Load state registry strictly from bundled JSON file (sole source of truth)
registry_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "states_registry.json")
if not os.path.exists(registry_path):
    raise FileNotFoundError(f"Critical Error: State registry file 'states_registry.json' not found at {registry_path}. Application cannot launch.")

try:
    with open(registry_path, "r", encoding="utf-8") as f:
        STATES_MAP = json.load(f)
except Exception as e:
    raise RuntimeError(f"Critical Error: Failed to parse 'states_registry.json': {e}")

class QueueHandler(logging.Handler):
    """Thread-safe logging handler routing logs to a queue."""
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue
        
    def emit(self, record):
        log_entry = self.format(record)
        self.log_queue.put(log_entry)

class StdoutRedirector:
    """Redirects stdout prints to a thread-safe queue."""
    def __init__(self, log_queue):
        self.log_queue = log_queue
        
    def write(self, string):
        if string.strip():
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            self.log_queue.put(f"[{timestamp}] [INFO] {string.strip()}")
            
    def flush(self):
        pass

class SchoolMinerGUI(customtkinter.CTk):
    def __init__(self):
        super().__init__()

        # Setup main window
        self.title("SchoolMiner Enterprise v6.5")
        self.geometry("1280x870")
        self.minsize(1024, 768)

        # Threading state variables
        self.log_queue = queue.Queue()
        self.scraper_thread = None
        self.districts_loading_thread = None
        self.stop_requested = False
        self.pause_event = threading.Event()
        self.pause_event.set()  # Initialized as set = running, clear = paused
        self.is_paused = False
        self.scraped_data_list = []
        self.districts_list = []  # Loaded raw districts
        self.district_cache = {}  # Cache: (board, slug) -> [district_dicts]
        self.elapsed_time_str = "0s"
        self.eta_str = "Estimating..."
        self.current_scrape_page = 0
        self.current_scrape_district = "None"
        
        # Workspace settings
        self.current_project_name = "Untitled Project"
        self.current_project_file = None
        self.recent_projects_file = os.path.join(os.getcwd(), ".smp_recent.json")
        self.recent_projects = self.load_recent_projects()
        self.user_settings_file = os.path.join(os.getcwd(), "user_settings.json")
        self.user_settings = self.load_user_settings()
        
        remember = self.user_settings.get("remember_last_selection", False)
        self.selected_board = self.user_settings.get("last_board", "cbse") if remember else "cbse"
        self.selected_state_slug = self.user_settings.get("last_state", "") if remember else ""
        
        self.workspace_history = []
        self.recent_activities = ["System initialized."]
        self.validation_results = {}
        self.last_export_path = "None"
        
        # Log management cache
        self.all_log_messages = []
        
        # Preset selection presets
        self.presets = {
            "Default Contact": ["School Name", "Address", "District", "State", "PIN Code", "Phone", "Mobile", "Email", "Website"],
            "All Parameters": list(FIELD_MAP.keys())
        }

        # Grid configuration: Left Navigation Sidebar, Right Content, Bottom Status Bar
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0) # Status bar
        self.grid_columnconfigure(0, weight=0) # Sidebar
        self.grid_columnconfigure(1, weight=1) # Main content panel

        # Initialize UI Components
        self.create_sidebar()
        self.create_content_panels()
        self.create_status_bar()

        # Keyboard shortcuts bindings
        self.bind("<Control-s>", lambda e: self.save_settings_action())
        self.bind("<Control-S>", lambda e: self.save_settings_action())
        self.bind("<F5>", lambda e: self.dispatch_load_districts())
        self.bind("<Escape>", lambda e: self.on_escape_pressed())

        # Redirect stdout and start log polling
        sys.stdout = StdoutRedirector(self.log_queue)
        self.check_log_queue()

        # Show Scraper initially as the primary entry point
        self.show_page("Scraper")
        
        # Log and set initial status
        self.log_queue.put("[SYSTEM] Loading application...")
        self.set_status("Loading application...", "🟡")
        
        self.after(500, self.load_registry_step)

    def on_escape_pressed(self):
        if self.scraper_thread and self.scraper_thread.is_alive():
            confirm = messagebox.askyesno("Stop Scraper", "Stop the currently running scraper execution?")
            if confirm:
                self.stop_scraping()

    def load_registry_step(self):
        self.log_queue.put("[SYSTEM] Loading state registry...")
        self.set_status("Loading state registry...", "🟡")
        self.after(500, self.validate_states_step)
        
    def validate_states_step(self):
        self.log_queue.put("[SYSTEM] Validating state mappings...")
        self.set_status("Validating state mappings...", "🟡")
        try:
            main.validate_all_states()
            self.log_queue.put("[SYSTEM] [SUCCESS] All state validations passed.")
            self.after(300, self.health_check_step)
        except Exception as e:
            self.log_queue.put(f"[SYSTEM] [ERROR] State validation failed: {e}")
            messagebox.showerror("Validation Mismatch Error", f"State mappings validation failed:\n{e}\n\nAborting application startup.")
            self.destroy()

    def health_check_step(self):
        self.log_queue.put("[SYSTEM] Running SchoolsIndia compatibility check...")
        self.set_status("Checking site compatibility...", "🟡")
        def run_check():
            try:
                from health_check import HealthCheckService
                service = HealthCheckService(main.start_browser, logger=lambda m: self.log_queue.put(f"[SYSTEM] {m}"))
                is_ok, msg = service.run_startup_check()
                if is_ok:
                    self.log_queue.put("[SYSTEM] [SUCCESS] Website health check passed. Ready.")
                else:
                    self.log_queue.put(f"[SYSTEM] [WARNING] {msg}")
            except Exception as e:
                self.log_queue.put(f"[SYSTEM] [WARNING] Health check exception: {e}")
            finally:
                self.after(0, self.ready_step)
        
        threading.Thread(target=run_check, daemon=True).start()

    def ready_step(self):
        self.log_queue.put("[SYSTEM] Ready.")
        self.set_status("Ready.", "🟢")
        
        # Trigger default districts loading at startup (only if Remember Last Selection is enabled and we have a valid state)
        if self.user_settings.get("remember_last_selection", False) and self.selected_state_slug:
            self.dispatch_load_districts()
        else:
            self.clear_districts_checklist_disabled()

    # ----------------------------
    # SIDEBAR NAVIGATION
    # ----------------------------
    def create_sidebar(self):
        self.sidebar_frame = customtkinter.CTkFrame(self, width=240, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        self.sidebar_frame.grid_rowconfigure(10, weight=1) # Push workspace card to bottom

        # Brand Logo
        self.logo_label = customtkinter.CTkLabel(
            self.sidebar_frame, 
            text="🚀 SchoolMiner", 
            font=customtkinter.CTkFont(size=22, weight="bold")
        )
        self.logo_label.grid(row=0, column=0, padx=20, pady=(24, 2))
        
        self.version_label = customtkinter.CTkLabel(
            self.sidebar_frame, 
            text="v6.5 Enterprise", 
            font=customtkinter.CTkFont(size=12, slant="italic"),
            text_color="#94a3b8"
        )
        self.version_label.grid(row=1, column=0, padx=20, pady=(0, 20))

        # Navigation menu title
        self.nav_title = customtkinter.CTkLabel(
            self.sidebar_frame, 
            text="NAVIGATION", 
            font=customtkinter.CTkFont(size=10, weight="bold"), 
            text_color="#64748b"
        )
        self.nav_title.grid(row=2, column=0, padx=20, pady=(10, 5), sticky="w")

        # Navigation Buttons
        self.nav_buttons = {}
        pages_meta = [
            ("Scraper", "🔍  Scraper"),
            ("Dashboard", "📊  Dashboard"),
            # ("Projects", "📁  Projects"), # Hidden to simplify first-time user workflow
            ("Export", "📤  Export"),
            ("Analytics", "📈  Analytics"),
            ("Logs", "📋  Logs"),
            ("Settings", "⚙  Settings"),
            ("About", "ℹ  About")
        ]

        for idx, (name, label) in enumerate(pages_meta, start=3):
            btn = customtkinter.CTkButton(
                self.sidebar_frame,
                text=label,
                font=customtkinter.CTkFont(size=13, weight="bold"),
                anchor="w",
                fg_color="transparent",
                text_color=("#0f172a", "#94a3b8"),
                hover_color=("#e2e8f0", "#1e293b"),
                height=38,
                corner_radius=8,
                command=lambda n=name: self.show_page(n)
            )
            btn.grid(row=idx, column=0, padx=15, pady=3, sticky="ew")
            self.nav_buttons[name] = btn

        # Bottom Workspace Active Card
        self.workspace_card = customtkinter.CTkFrame(self.sidebar_frame, fg_color=("#e2e8f0", "#131a2e"), border_width=1, border_color=("#cbd5e1", "#1e293b"), corner_radius=10)
        # self.workspace_card.grid(row=11, column=0, padx=15, pady=20, sticky="ew") # Hidden to simplify workspace concepts
        self.workspace_card.columnconfigure(0, weight=1)

        self.ws_title = customtkinter.CTkLabel(self.workspace_card, text="ACTIVE WORKSPACE", font=customtkinter.CTkFont(size=9, weight="bold"), text_color="#64748b")
        self.ws_title.grid(row=0, column=0, padx=10, pady=(8, 2), sticky="w")

        self.ws_name = customtkinter.CTkLabel(self.workspace_card, text=self.current_project_name, font=customtkinter.CTkFont(size=12, weight="bold"), text_color=("#0f172a", "#3b82f6"), anchor="w")
        self.ws_name.grid(row=1, column=0, padx=10, pady=(0, 2), sticky="w")

        state_display = self.selected_state_slug.replace("-", " ").title() if self.selected_state_slug else "None"
        self.ws_state = customtkinter.CTkLabel(self.workspace_card, text=f"State: {state_display}", font=customtkinter.CTkFont(size=10), text_color="#94a3b8", anchor="w")
        self.ws_state.grid(row=2, column=0, padx=10, pady=(0, 8), sticky="w")

    # ----------------------------
    # PERSISTENT STATUS BAR
    # ----------------------------
    def create_status_bar(self):
        self.status_bar = customtkinter.CTkFrame(self, height=28, corner_radius=0, border_width=1, border_color=("#cbd5e1", "#1e293b"))
        self.status_bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.status_bar.columnconfigure(1, weight=1)

        self.status_lbl = customtkinter.CTkLabel(self.status_bar, text="🟢 Ready", font=customtkinter.CTkFont(size=11, weight="bold"))
        self.status_lbl.grid(row=0, column=0, padx=15, pady=2, sticky="w")

        self.status_project_lbl = customtkinter.CTkLabel(self.status_bar, text=f"Workspace: {self.current_project_name}", font=customtkinter.CTkFont(size=11), text_color="#64748b")
        # self.status_project_lbl.grid(row=0, column=1, padx=15, pady=2, sticky="w") # Hidden to simplify workspace concepts

        self.status_stats_lbl = customtkinter.CTkLabel(self.status_bar, text="Schools: 0 | Pages: 0 | ETA: None", font=customtkinter.CTkFont(size=11))
        self.status_stats_lbl.grid(row=0, column=2, padx=15, pady=2, sticky="e")

    def set_status(self, text, indicator="🟢"):
        self.status_lbl.configure(text=f"{indicator} {text}")

    # ----------------------------
    # VIEW FRAMES INITIALIZATION
    # ----------------------------
    def create_content_panels(self):
        # Container frame for views
        self.content_container = customtkinter.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.content_container.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.content_container.grid_rowconfigure(0, weight=1)
        self.content_container.grid_columnconfigure(0, weight=1)

        self.pages = {}
        
        # Instantiate frames
        self.create_dashboard_view()
        self.create_projects_view()
        self.create_scraper_view()
        self.create_export_view()
        self.create_analytics_view()
        self.create_logs_view()
        self.create_settings_view()
        self.create_about_view()

    def show_page(self, name):
        # Trigger auto-save of active project parameters when user shifts tabs
        self.auto_save_project()
        
        # Refresh dynamic screens
        if name == "Export":
            self.update_export_explorer()
        elif name == "Projects":
            self.update_recent_projects_listbox()
            self.update_workspace_history_display()
        elif name == "Analytics":
            self.update_analytics_display()
        elif name == "Dashboard":
            self.update_project_displays()
            self.update_activity_displays()
            
        # Switch frames
        for page_name, frame in self.pages.items():
            if page_name == name:
                frame.grid(row=0, column=0, sticky="nsew")
            else:
                frame.grid_forget()

        # Update sidebar buttons style
        for btn_name, btn in self.nav_buttons.items():
            if btn_name == name:
                btn.configure(fg_color=("#3b82f6", "#1e3a8a"), text_color="#ffffff")
            else:
                btn.configure(fg_color="transparent", text_color=("#0f172a", "#94a3b8"))

    # ----------------------------
    # 1. DASHBOARD VIEW
    # ----------------------------
    def create_dashboard_view(self):
        page = customtkinter.CTkFrame(self.content_container, fg_color="transparent")
        self.pages["Dashboard"] = page
        page.columnconfigure(0, weight=1)
        page.rowconfigure(2, weight=1)

        # Welcome Section
        welcome_frame = customtkinter.CTkFrame(page, fg_color="transparent")
        welcome_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        welcome_frame.columnconfigure(0, weight=1)

        self.dash_welcome_lbl = customtkinter.CTkLabel(
            welcome_frame, 
            text="Welcome to SchoolMiner Workspace", 
            font=customtkinter.CTkFont(size=24, weight="bold"),
            anchor="w"
        )
        self.dash_welcome_lbl.grid(row=0, column=0, sticky="w")

        self.dash_sub_lbl = customtkinter.CTkLabel(
            welcome_frame, 
            text="Enterprise intelligence mining dashboard and scraping control tower.", 
            font=customtkinter.CTkFont(size=13),
            text_color="#64748b",
            anchor="w"
        )
        self.dash_sub_lbl.grid(row=1, column=0, sticky="w")

        # Quick Statistics Cards Grid (Row 1: 4 columns, Row 2: 3 columns)
        stats_frame = customtkinter.CTkFrame(page, fg_color="transparent")
        stats_frame.grid(row=1, column=0, sticky="ew", pady=(0, 15))
        stats_frame.columnconfigure((0, 1, 2, 3), weight=1)

        # Row 1 cards
        self.dash_stat_schools = self.create_dashboard_stat_card(stats_frame, "SCHOOLS FOUND", "0", "🏫", "#3b82f6", 0, 0)
        self.dash_stat_pages = self.create_dashboard_stat_card(stats_frame, "PAGES VISITED", "0", "📄", "#10b981", 0, 1)
        self.dash_stat_time = self.create_dashboard_stat_card(stats_frame, "ELAPSED TIME", "0s", "⏱", "#8b5cf6", 0, 2)
        self.dash_stat_errors = self.create_dashboard_stat_card(stats_frame, "ERRORS", "0", "🚨", "#ef4444", 0, 3)

        # Row 2 cards
        stats_frame_2 = customtkinter.CTkFrame(page, fg_color="transparent")
        stats_frame_2.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        stats_frame_2.columnconfigure((0, 1, 2), weight=1)

        self.dash_stat_duplicates = self.create_dashboard_stat_card(stats_frame_2, "DUPLICATES", "0", "👥", "#f59e0b", 0, 0)
        self.dash_stat_wrong_state = self.create_dashboard_stat_card(stats_frame_2, "WRONG STATE", "0", "🗺️", "#64748b", 0, 1)
        self.dash_stat_rows_exported = self.create_dashboard_stat_card(stats_frame_2, "ROWS EXPORTED", "0", "📥", "#10b981", 0, 2)

        # Lower grid section: Context Card and Recent Activity Feed side-by-side
        self.lower_grid = customtkinter.CTkFrame(page, fg_color="transparent")
        self.lower_grid.grid(row=3, column=0, sticky="nsew", pady=10)
        self.lower_grid.columnconfigure(0, weight=1)
        self.lower_grid.columnconfigure(1, weight=1)

        # Lower Col 0: Active Scraper Context details
        context_card = customtkinter.CTkFrame(self.lower_grid, corner_radius=12, border_width=1, border_color=("#cbd5e1", "#1e293b"))
        context_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        context_card.columnconfigure(0, weight=1)

        self.context_title = customtkinter.CTkLabel(
            context_card, 
            text="Active Scraper & Workspace Details", 
            font=customtkinter.CTkFont(size=14, weight="bold"),
            anchor="w"
        )
        self.context_title.grid(row=0, column=0, padx=20, pady=(15, 8), sticky="w")

        self.context_details_frame = customtkinter.CTkFrame(context_card, fg_color="transparent")
        self.context_details_frame.grid(row=1, column=0, padx=20, pady=(0, 15), sticky="ew")
        self.context_details_frame.columnconfigure(1, weight=1)

        details = [
            ("Current Project", lambda: self.current_project_name),
            ("Board Target", lambda: self.selected_board.upper()),
            ("State Focus", lambda: self.selected_state_slug.replace("-", " ").title() if self.selected_state_slug else "None"),
            ("Districts Setup", lambda: ", ".join(config.DISTRICTS) if config.DISTRICTS else "ALL Districts"),
            ("Export Formats", lambda: ", ".join(config.EXPORT).upper()),
            ("Last Export File", lambda: self.last_export_path),
            ("Engine Version", lambda: f"v{config.VERSION}")
        ]

        self.context_labels = {}
        for r_idx, (label, val_func) in enumerate(details):
            lbl_key = customtkinter.CTkLabel(self.context_details_frame, text=f"{label}:", font=customtkinter.CTkFont(size=11, weight="bold"), width=130, anchor="w")
            lbl_key.grid(row=r_idx, column=0, pady=3, sticky="w")
            
            lbl_val = customtkinter.CTkLabel(self.context_details_frame, text=val_func(), font=customtkinter.CTkFont(size=11), text_color="#94a3b8", anchor="w")
            lbl_val.grid(row=r_idx, column=1, pady=3, sticky="w")
            
            self.context_labels[label] = (lbl_val, val_func)

        # Lower Col 1: Recent Workspace Activity Log Panel
        activity_card = customtkinter.CTkFrame(self.lower_grid, corner_radius=12, border_width=1, border_color=("#cbd5e1", "#1e293b"))
        activity_card.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        activity_card.columnconfigure(0, weight=1)
        activity_card.rowconfigure(1, weight=1)

        act_title = customtkinter.CTkLabel(activity_card, text="Recent Activity Feed", font=customtkinter.CTkFont(size=14, weight="bold"), anchor="w")
        act_title.grid(row=0, column=0, padx=20, pady=(15, 8), sticky="w")

        self.activity_scroll = customtkinter.CTkScrollableFrame(activity_card, fg_color="transparent")
        self.activity_scroll.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 15))

    def create_dashboard_stat_card(self, parent, title, value, icon, color, row, col):
        card = customtkinter.CTkFrame(parent, fg_color=("#ffffff", "#1e293b"), border_width=1, border_color=("#e2e8f0", "#334155"), corner_radius=12)
        card.grid(row=row, column=col, padx=8, pady=0, sticky="nsew")
        card.columnconfigure(0, weight=1)
        
        header_frame = customtkinter.CTkFrame(card, fg_color="transparent")
        header_frame.pack(fill="x", padx=15, pady=(10, 3))
        
        title_lbl = customtkinter.CTkLabel(header_frame, text=title, font=customtkinter.CTkFont(size=9, weight="bold"), text_color=("#64748b", "#94a3b8"))
        title_lbl.pack(side="left")
        
        icon_lbl = customtkinter.CTkLabel(header_frame, text=icon, font=customtkinter.CTkFont(size=14), text_color=color)
        icon_lbl.pack(side="right")
        
        val_lbl = customtkinter.CTkLabel(card, text=value, font=customtkinter.CTkFont(size=24, weight="bold"), text_color=color)
        val_lbl.pack(fill="x", padx=15, pady=(2, 10), anchor="w")
        
        return val_lbl

    def update_activity_displays(self):
        for widget in self.activity_scroll.winfo_children():
            widget.destroy()

        if not self.recent_activities:
            lbl = customtkinter.CTkLabel(self.activity_scroll, text="No activities logged in this workspace.", font=customtkinter.CTkFont(slant="italic"))
            lbl.pack(pady=30)
            return

        for act in self.recent_activities:
            lbl_row = customtkinter.CTkLabel(self.activity_scroll, text=act, font=customtkinter.CTkFont(family="Courier", size=10), text_color="#94a3b8", anchor="w", justify="left")
            lbl_row.pack(fill="x", pady=2, padx=5)

    # ----------------------------
    # 2. PROJECTS VIEW
    # ----------------------------
    def update_project_displays(self):
        # Update sidebar
        self.ws_name.configure(text=self.current_project_name)
        state_display = self.selected_state_slug.replace("-", " ").title() if self.selected_state_slug else "None"
        self.ws_state.configure(text=f"State: {state_display}")
        
        # Update status bar
        self.status_project_lbl.configure(text=f"Workspace: {self.current_project_name}")
        
        # Update dashboard context
        for key, (lbl_widget, val_func) in self.context_labels.items():
            lbl_widget.configure(text=val_func())

    def create_projects_view(self):
        page = customtkinter.CTkFrame(self.content_container, fg_color="transparent")
        self.pages["Projects"] = page
        page.columnconfigure(0, weight=3)
        page.columnconfigure(1, weight=8)
        page.rowconfigure(0, weight=1)

        # Left Column: Workspace Operations
        ops_frame = customtkinter.CTkFrame(page, corner_radius=12, border_width=1, border_color=("#cbd5e1", "#1e293b"))
        ops_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=0)
        ops_frame.columnconfigure(0, weight=1)

        ops_title = customtkinter.CTkLabel(ops_frame, text="Workspace Operations", font=customtkinter.CTkFont(size=16, weight="bold"))
        ops_title.grid(row=0, column=0, padx=20, pady=(20, 15), sticky="w")

        btn_new = customtkinter.CTkButton(ops_frame, text="➕ Create Project", height=40, font=customtkinter.CTkFont(weight="bold"), command=self.create_project)
        btn_new.grid(row=1, column=0, padx=20, pady=8, sticky="ew")

        btn_open = customtkinter.CTkButton(ops_frame, text="📂 Open Project", height=40, font=customtkinter.CTkFont(weight="bold"), fg_color=("#475569", "#334155"), hover_color=("#334155", "#475569"), command=self.open_project)
        btn_open.grid(row=2, column=0, padx=20, pady=8, sticky="ew")

        btn_save = customtkinter.CTkButton(ops_frame, text="💾 Save Project", height=40, font=customtkinter.CTkFont(weight="bold"), command=self.save_project)
        btn_save.grid(row=3, column=0, padx=20, pady=8, sticky="ew")

        btn_save_as = customtkinter.CTkButton(ops_frame, text="💾 Save Project As...", height=40, font=customtkinter.CTkFont(weight="bold"), fg_color="transparent", border_width=1, border_color=("#3b82f6", "#2563eb"), command=self.save_project_as)
        btn_save_as.grid(row=4, column=0, padx=20, pady=8, sticky="ew")

        btn_duplicate = customtkinter.CTkButton(ops_frame, text="👥 Duplicate Workspace", height=40, font=customtkinter.CTkFont(weight="bold"), fg_color="#8b5cf6", hover_color="#7c3aed", command=self.duplicate_project)
        btn_duplicate.grid(row=5, column=0, padx=20, pady=8, sticky="ew")

        btn_delete = customtkinter.CTkButton(ops_frame, text="🗑️ Delete Workspace File", height=40, font=customtkinter.CTkFont(weight="bold"), fg_color="#ef4444", hover_color="#dc2626", command=self.delete_project)
        btn_delete.grid(row=6, column=0, padx=20, pady=8, sticky="ew")

        # Right Column Split: Recents list (left) and Workspace History Log (right)
        recents_container = customtkinter.CTkFrame(page, fg_color="transparent")
        recents_container.grid(row=0, column=1, sticky="nsew", padx=(10, 0), pady=0)
        recents_container.columnconfigure(0, weight=1)
        recents_container.columnconfigure(1, weight=1)
        recents_container.rowconfigure(0, weight=1)

        # Recent Projects block
        recents_frame = customtkinter.CTkFrame(recents_container, corner_radius=12, border_width=1, border_color=("#cbd5e1", "#1e293b"))
        recents_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        recents_frame.columnconfigure(0, weight=1)
        recents_frame.rowconfigure(1, weight=1)

        recents_title = customtkinter.CTkLabel(recents_frame, text="Recent Projects", font=customtkinter.CTkFont(size=14, weight="bold"))
        recents_title.grid(row=0, column=0, padx=15, pady=(15, 10), sticky="w")

        self.recents_scroll = customtkinter.CTkScrollableFrame(recents_frame, fg_color="transparent")
        self.recents_scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 15))

        # Persistent execution History log block
        history_frame = customtkinter.CTkFrame(recents_container, corner_radius=12, border_width=1, border_color=("#cbd5e1", "#1e293b"))
        history_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        history_frame.columnconfigure(0, weight=1)
        history_frame.rowconfigure(1, weight=1)

        history_title = customtkinter.CTkLabel(history_frame, text="Workspace Execution History", font=customtkinter.CTkFont(size=14, weight="bold"))
        history_title.grid(row=0, column=0, padx=15, pady=(15, 10), sticky="w")

        self.history_scroll = customtkinter.CTkScrollableFrame(history_frame, fg_color="transparent")
        self.history_scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 15))

    def update_workspace_history_display(self):
        for widget in self.history_scroll.winfo_children():
            widget.destroy()

        if not self.workspace_history:
            lbl = customtkinter.CTkLabel(self.history_scroll, text="No persistent execution runs recorded.", font=customtkinter.CTkFont(slant="italic"))
            lbl.pack(pady=40)
            return

        for entry in self.workspace_history:
            lbl_row = customtkinter.CTkLabel(self.history_scroll, text=entry, font=customtkinter.CTkFont(family="Courier", size=10), text_color="#94a3b8", anchor="w", justify="left")
            lbl_row.pack(fill="x", pady=3, padx=5)

    def duplicate_project(self):
        if not self.current_project_file:
            self.log_queue.put("[SYSTEM] [WARNING] Cannot duplicate an unsaved project. Save it first.")
            return
        dialog = customtkinter.CTkInputDialog(text="Enter name for duplicate project workspace:", title="Duplicate Workspace")
        new_name = dialog.get_input()
        if new_name:
            new_name = new_name.strip()
            if new_name:
                dir_name = os.path.dirname(self.current_project_file)
                new_file_path = os.path.join(dir_name, f"{new_name}.smp")
                
                self.current_project_name = new_name
                self.current_project_file = new_file_path
                
                # Write current variables to the cloned filepath
                self.write_project_to_file(new_file_path)
                self.add_recent_project(new_file_path)
                self.update_project_displays()
                self.log_activity(f"Duplicated workspace profile to: {new_name}")
                self.log_queue.put(f"[SYSTEM] [SUCCESS] Duplicated active project to: {new_name}")

    def delete_project(self):
        if not self.current_project_file:
            self.log_queue.put("[SYSTEM] [WARNING] Cannot delete an unsaved workspace project.")
            return
            
        confirm = messagebox.askyesno("Delete Workspace", f"Are you sure you want to delete the project file:\n{self.current_project_file}?\n\nThis action cannot be undone.")
        if confirm:
            try:
                path_to_delete = self.current_project_file
                if os.path.exists(path_to_delete):
                    os.remove(path_to_delete)
                
                # Remove from history lists
                recent = self.load_recent_projects()
                if path_to_delete in recent:
                    recent.remove(path_to_delete)
                self.save_recent_projects(recent)
                self.recent_projects = recent
                
                self.log_queue.put(f"[SYSTEM] [SUCCESS] Deleted workspace file: {self.current_project_name}")
                
                # Reset project state variables
                self.current_project_name = "Untitled Project"
                self.current_project_file = None
                self.workspace_history.clear()
                self.recent_activities = ["Active workspace was deleted. Started new session."]
                
                self.update_project_displays()
                self.update_recent_projects_listbox()
                self.update_workspace_history_display()
                self.update_activity_displays()
            except Exception as e:
                self.log_queue.put(f"[SYSTEM] [ERROR] Workspace deletion failed: {e}")

    # ----------------------------
    # 3. SCRAPER VIEW (RUNNING VIEW)
    # ----------------------------
    def create_scraper_view(self):
        page = customtkinter.CTkFrame(self.content_container, fg_color="transparent")
        self.pages["Scraper"] = page
        
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=0) # Config frame
        page.grid_rowconfigure(1, weight=1) # Scrollers frame
        page.grid_rowconfigure(2, weight=0) # Controls & mini Console

        # --- Sub-Frame 1: Data Configuration ---
        self.config_frame = customtkinter.CTkFrame(page, corner_radius=12, border_width=1, border_color=("#cbd5e1", "#1e293b"))
        self.config_frame.grid(row=0, column=0, sticky="ew", pady=(0, 15), padx=0)
        self.config_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        # Board select
        self.lbl_board = customtkinter.CTkLabel(self.config_frame, text="Select Board", anchor="w")
        self.lbl_board.grid(row=0, column=0, padx=15, pady=(10, 2), sticky="w")
        self.board_menu = customtkinter.CTkOptionMenu(
            self.config_frame, 
            values=["cbse", "icse", "ib", "state-board", "pre-primary"],
            command=self.on_board_selected
        )
        self.board_menu.grid(row=1, column=0, padx=15, pady=(2, 15), sticky="ew")
        self.board_menu.set(self.selected_board)

        # State entry (searchable CTkComboBox)
        self.lbl_state = customtkinter.CTkLabel(self.config_frame, text="Select State (Searchable)", anchor="w")
        self.lbl_state.grid(row=0, column=1, padx=15, pady=(10, 2), sticky="w")
        
        self.state_frame = customtkinter.CTkFrame(self.config_frame, fg_color="transparent")
        self.state_frame.grid(row=1, column=1, padx=15, pady=(2, 15), sticky="ew")
        self.state_frame.grid_columnconfigure(0, weight=1)
        
        combo_values = ["Select State..."] + sorted(list(STATES_MAP.keys()))
        self.state_combo = customtkinter.CTkComboBox(
            self.state_frame, 
            values=combo_values,
            command=self.on_state_selected,
            state="readonly"
        )
        self.state_combo.grid(row=0, column=0, sticky="ew")
        
        self.btn_load_districts = customtkinter.CTkButton(
            self.state_frame, 
            text="Load", 
            width=50, 
            command=self.dispatch_load_districts
        )
        # self.btn_load_districts is kept instantiated to prevent reference errors, but not gridded so it remains hidden.
        
        # Resolve default selected state based on Remember Last Selection
        initial_name = "Select State..."
        remember = self.user_settings.get("remember_last_selection", False)
        if remember and self.selected_state_slug:
            for k, v in STATES_MAP.items():
                if v == self.selected_state_slug:
                    initial_name = k
                    break
        else:
            self.selected_state_slug = ""
            config.DISTRICTS = []
                
        self.state_combo.set(initial_name)

        # Output path selection
        self.lbl_output = customtkinter.CTkLabel(self.config_frame, text="Output Directory", anchor="w")
        self.lbl_output.grid(row=0, column=2, padx=15, pady=(10, 2), sticky="w")
        
        self.folder_frame = customtkinter.CTkFrame(self.config_frame, fg_color="transparent")
        self.folder_frame.grid(row=1, column=2, padx=15, pady=(2, 15), sticky="ew")
        self.folder_frame.grid_columnconfigure(0, weight=1)
        
        self.folder_entry = customtkinter.CTkEntry(self.folder_frame)
        self.folder_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.folder_entry.insert(0, config.OUTPUT_FOLDER)
        
        self.btn_browse = customtkinter.CTkButton(
            self.folder_frame, 
            text="Browse", 
            width=60, 
            command=self.browse_folder
        )
        self.btn_browse.grid(row=0, column=1)

        # Output format
        self.lbl_format = customtkinter.CTkLabel(self.config_frame, text="Format", anchor="w")
        self.lbl_format.grid(row=0, column=3, padx=15, pady=(10, 2), sticky="w")
        self.format_menu = customtkinter.CTkOptionMenu(
            self.config_frame, 
            values=["Excel (xlsx)", "CSV only", "Both (Excel + CSV)"]
        )
        self.format_menu.grid(row=1, column=3, padx=15, pady=(2, 15), sticky="ew")
        self.format_menu.set("Excel (xlsx)")

        # --- Sub-Frame 2: Dual Checklist Panels ---
        self.scrollers_frame = customtkinter.CTkFrame(page, fg_color="transparent")
        self.scrollers_frame.grid(row=1, column=0, sticky="nsew", pady=0, padx=0)
        self.scrollers_frame.grid_columnconfigure(0, weight=1)
        self.scrollers_frame.grid_columnconfigure(1, weight=1)
        self.scrollers_frame.grid_rowconfigure(0, weight=1)

        # Col 0: Districts Checklist
        self.dist_panel = customtkinter.CTkFrame(self.scrollers_frame, corner_radius=12, border_width=1, border_color=("#cbd5e1", "#1e293b"))
        self.dist_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=0)
        self.dist_panel.grid_rowconfigure(2, weight=1)
        self.dist_panel.grid_columnconfigure(0, weight=1)

        self.dist_header = customtkinter.CTkFrame(self.dist_panel, fg_color="transparent")
        self.dist_header.grid(row=0, column=0, padx=15, pady=(12, 5), sticky="ew")
        self.dist_header.grid_columnconfigure(0, weight=1)
        
        self.dist_title = customtkinter.CTkLabel(self.dist_header, text="Districts Checklist", font=customtkinter.CTkFont(size=14, weight="bold"))
        self.dist_title.grid(row=0, column=0, sticky="w")
        
        self.btn_all_dist = customtkinter.CTkButton(self.dist_header, text="Select All", width=65, height=24, command=self.select_all_districts)
        self.btn_all_dist.grid(row=0, column=1, padx=(0, 5))
        self.btn_clear_dist = customtkinter.CTkButton(self.dist_header, text="Clear", width=55, height=24, command=self.clear_all_districts)
        self.btn_clear_dist.grid(row=0, column=2)

        self.dist_search = customtkinter.CTkEntry(self.dist_panel, placeholder_text="Search district name...")
        self.dist_search.grid(row=1, column=0, sticky="ew", padx=15, pady=5)
        self.dist_search.bind("<KeyRelease>", self.filter_districts_checkboxes)

        self.dist_scroll = customtkinter.CTkScrollableFrame(self.dist_panel, fg_color="transparent")
        self.dist_scroll.grid(row=2, column=0, sticky="nsew", padx=15, pady=(5, 15))
        
        self.district_checkboxes = []  # List of CTkCheckBox

        # Col 1: Fields Checklist
        self.field_panel = customtkinter.CTkFrame(self.scrollers_frame, corner_radius=12, border_width=1, border_color=("#cbd5e1", "#1e293b"))
        self.field_panel.grid(row=0, column=1, sticky="nsew", padx=(10, 0), pady=0)
        self.field_panel.grid_rowconfigure(1, weight=1)
        self.field_panel.grid_columnconfigure(0, weight=1)

        self.field_header = customtkinter.CTkFrame(self.field_panel, fg_color="transparent")
        self.field_header.grid(row=0, column=0, padx=15, pady=(12, 5), sticky="ew")
        self.field_header.grid_columnconfigure(0, weight=1)

        self.field_title = customtkinter.CTkLabel(self.field_header, text="Export Fields Selection", font=customtkinter.CTkFont(size=14, weight="bold"))
        self.field_title.grid(row=0, column=0, sticky="w")

        self.btn_all_fields = customtkinter.CTkButton(self.field_header, text="Select All", width=65, command=self.select_all_fields)
        self.btn_all_fields.grid(row=0, column=1, padx=(0, 5))
        self.btn_clear_fields = customtkinter.CTkButton(self.field_header, text="Clear", width=55, command=self.clear_all_fields)
        self.field_header.columnconfigure(0, weight=1)
        self.btn_clear_fields.grid(row=0, column=2)

        self.field_scroll = customtkinter.CTkScrollableFrame(self.field_panel, fg_color="transparent")
        self.field_scroll.grid(row=1, column=0, sticky="nsew", padx=15, pady=5)
        
        self.field_checkboxes = {}  # Map of field -> CTkCheckBox
        self.populate_field_selection()

        # Custom Presets layout inside fields panel bottom
        self.presets_frame = customtkinter.CTkFrame(self.field_panel, fg_color="transparent")
        self.presets_frame.grid(row=2, column=0, sticky="ew", padx=15, pady=(5, 15))
        self.presets_frame.grid_columnconfigure((0, 1), weight=1)

        self.preset_combo = customtkinter.CTkOptionMenu(
            self.presets_frame, 
            values=list(self.presets.keys()),
            command=self.load_preset_selection
        )
        self.preset_combo.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        self.preset_entry = customtkinter.CTkEntry(self.presets_frame, placeholder_text="New preset name...")
        self.preset_entry.grid(row=1, column=0, padx=(0, 5), pady=(5, 0), sticky="ew")
        
        self.btn_save_preset = customtkinter.CTkButton(
            self.presets_frame, 
            text="Save Preset", 
            command=self.save_custom_preset
        )
        self.btn_save_preset.grid(row=1, column=1, pady=(5, 0), sticky="ew")

        # --- Sub-Frame 3: Scraper Control Toolbar & Live Logs Console ---
        self.controls_panel = customtkinter.CTkFrame(page, corner_radius=12, border_width=1, border_color=("#cbd5e1", "#1e293b"))
        self.controls_panel.grid(row=2, column=0, sticky="ew", pady=(15, 0), padx=0)
        self.controls_panel.grid_columnconfigure(0, weight=1)

        # Controls Buttons Frame
        self.toolbar_frame = customtkinter.CTkFrame(self.controls_panel, fg_color="transparent")
        self.toolbar_frame.grid(row=0, column=0, sticky="ew", padx=15, pady=10)
        self.toolbar_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.btn_start = customtkinter.CTkButton(
            self.toolbar_frame, 
            text="\u25b6  Start Scraper", 
            fg_color="#10b981", 
            hover_color="#059669",
            font=customtkinter.CTkFont(weight="bold"),
            command=self.dispatch_scraper_worker
        )
        self.btn_start.grid(row=0, column=0, padx=5, pady=5, sticky="ew")

        self.btn_pause = customtkinter.CTkButton(
            self.toolbar_frame, 
            text="\u23f8  Pause", 
            fg_color="#f59e0b", 
            text_color="#000000",
            hover_color="#d97706",
            font=customtkinter.CTkFont(weight="bold"),
            state="disabled",
            command=self.pause_scraping
        )
        self.btn_pause.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        self.btn_resume = customtkinter.CTkButton(
            self.toolbar_frame, 
            text="\u25b6  Resume", 
            fg_color="#3b82f6", 
            hover_color="#2563eb",
            font=customtkinter.CTkFont(weight="bold"),
            state="disabled",
            command=self.resume_scraping
        )
        self.btn_resume.grid(row=0, column=2, padx=5, pady=5, sticky="ew")

        self.btn_stop = customtkinter.CTkButton(
            self.toolbar_frame, 
            text="\u23f9  Stop", 
            fg_color="#ef4444", 
            hover_color="#dc2626",
            font=customtkinter.CTkFont(weight="bold"),
            state="disabled",
            command=self.stop_scraping
        )
        self.btn_stop.grid(row=0, column=3, padx=5, pady=5, sticky="ew")

        # Progress bar
        self.progress_frame = customtkinter.CTkFrame(self.controls_panel, fg_color="transparent")
        self.progress_frame.grid(row=1, column=0, sticky="ew", padx=15, pady=(0, 5))
        self.progress_frame.grid_columnconfigure(0, weight=1)

        self.progress_bar = customtkinter.CTkProgressBar(self.progress_frame)
        self.progress_bar.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        self.progress_bar.set(0.0)

        self.progress_lbl = customtkinter.CTkLabel(
            self.progress_frame, 
            text="Status: Ready | Scraped: 0 | Current Target: None | ETA: None",
            font=customtkinter.CTkFont(size=12, weight="bold")
        )
        self.progress_lbl.grid(row=1, column=0, sticky="w")

        # Mini Logs Viewer inside scraper
        self.mini_logs_box = customtkinter.CTkTextbox(
            self.controls_panel, 
            height=100, 
            font=customtkinter.CTkFont(family="Courier", size=11)
        )
        self.mini_logs_box.grid(row=2, column=0, sticky="ew", padx=15, pady=(5, 10))
        self.mini_logs_box.configure(state="disabled")

    # ----------------------------
    # 4. EXPORT HUB VIEW
    # ----------------------------
    def create_export_view(self):
        page = customtkinter.CTkFrame(self.content_container, fg_color="transparent")
        self.pages["Export"] = page
        page.columnconfigure(0, weight=1)
        page.rowconfigure(1, weight=1)

        # Card 1: Output Destination settings
        config_card = customtkinter.CTkFrame(page, corner_radius=12, border_width=1, border_color=("#cbd5e1", "#1e293b"))
        config_card.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        config_card.columnconfigure(1, weight=1)

        lbl_title = customtkinter.CTkLabel(config_card, text="Export Settings & Formats", font=customtkinter.CTkFont(size=15, weight="bold"))
        lbl_title.grid(row=0, column=0, columnspan=3, padx=15, pady=10, sticky="w")

        # Format picker
        lbl_fmt = customtkinter.CTkLabel(config_card, text="Output Format:")
        lbl_fmt.grid(row=1, column=0, padx=15, pady=10, sticky="w")
        
        self.export_format_combo = customtkinter.CTkOptionMenu(
            config_card, 
            values=["Excel (xlsx)", "CSV only", "Both (Excel + CSV)"],
            command=lambda v: self.format_menu.set(v)
        )
        self.export_format_combo.grid(row=1, column=1, padx=10, pady=10, sticky="w")
        self.export_format_combo.set(self.format_menu.get())

        # Folder picker
        lbl_dir = customtkinter.CTkLabel(config_card, text="Destination Directory:")
        lbl_dir.grid(row=2, column=0, padx=15, pady=10, sticky="w")

        self.export_dir_entry = customtkinter.CTkEntry(config_card)
        self.export_dir_entry.grid(row=2, column=1, padx=10, pady=10, sticky="ew")
        self.export_dir_entry.insert(0, self.folder_entry.get())
        self.export_dir_entry.bind("<KeyRelease>", lambda e: self.sync_folder_path(self.export_dir_entry.get()))

        btn_browse_exp = customtkinter.CTkButton(
            config_card, 
            text="Browse", 
            width=80, 
            command=self.browse_folder
        )
        btn_browse_exp.grid(row=2, column=2, padx=15, pady=10)

        # Open Out Directory button
        btn_open_dir = customtkinter.CTkButton(
            config_card, 
            text="📁 Open Folder in Explorer", 
            command=self.open_output_folder,
            fg_color=("#10b981", "#059669"),
            hover_color=("#059669", "#10b981")
        )
        btn_open_dir.grid(row=3, column=1, columnspan=2, padx=10, pady=(5, 15), sticky="e")

        # Card 2: Export Explorer (List spreadsheets in Output directory)
        explorer_card = customtkinter.CTkFrame(page, corner_radius=12, border_width=1, border_color=("#cbd5e1", "#1e293b"))
        explorer_card.grid(row=1, column=0, sticky="nsew")
        explorer_card.columnconfigure(0, weight=1)
        explorer_card.rowconfigure(1, weight=1)

        exp_title = customtkinter.CTkLabel(explorer_card, text="Export Explorer (Generated Spreadsheets)", font=customtkinter.CTkFont(size=15, weight="bold"))
        exp_title.grid(row=0, column=0, padx=15, pady=12, sticky="w")

        self.export_rows_frame = customtkinter.CTkScrollableFrame(explorer_card, fg_color="transparent")
        self.export_rows_frame.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 15))

    # ----------------------------
    # 5. DATA HARVESTING ANALYTICS VIEW
    # ----------------------------
    def create_analytics_view(self):
        page = customtkinter.CTkScrollableFrame(self.content_container, fg_color="transparent")
        self.pages["Analytics"] = page
        page.columnconfigure(0, weight=1)

        # Header
        lbl_title = customtkinter.CTkLabel(page, text="Data Harvesting & Quality Analytics", font=customtkinter.CTkFont(size=20, weight="bold"))
        lbl_title.pack(padx=20, pady=(10, 15), anchor="w")

        # Card 1: Quality Score
        self.score_card = customtkinter.CTkFrame(page, corner_radius=12, border_width=1, border_color=("#cbd5e1", "#1e293b"))
        self.score_card.pack(fill="x", pady=10)
        
        score_header = customtkinter.CTkLabel(self.score_card, text="Data Completeness Quality Score", font=customtkinter.CTkFont(size=14, weight="bold"))
        score_header.pack(padx=20, pady=(15, 5), anchor="w")
        
        self.score_val_lbl = customtkinter.CTkLabel(self.score_card, text="0.0%", font=customtkinter.CTkFont(size=36, weight="bold"), text_color="#10b981")
        self.score_val_lbl.pack(padx=20, pady=5, anchor="w")
        
        self.score_progress = customtkinter.CTkProgressBar(self.score_card, height=12)
        self.score_progress.pack(fill="x", padx=20, pady=(5, 15))
        self.score_progress.set(0.0)

        # Card 2: Contact Coverage Rates
        self.coverage_card = customtkinter.CTkFrame(page, corner_radius=12, border_width=1, border_color=("#cbd5e1", "#1e293b"))
        self.coverage_card.pack(fill="x", pady=10)
        self.coverage_card.columnconfigure(1, weight=1)

        cov_header = customtkinter.CTkLabel(self.coverage_card, text="Field Coverage and Capture Rates", font=customtkinter.CTkFont(size=14, weight="bold"))
        cov_header.grid(row=0, column=0, columnspan=3, padx=20, pady=(15, 10), sticky="w")

        # Emails
        lbl_em = customtkinter.CTkLabel(self.coverage_card, text="Email Coverage:")
        lbl_em.grid(row=1, column=0, padx=20, pady=6, sticky="w")
        self.em_progress = customtkinter.CTkProgressBar(self.coverage_card, height=10)
        self.em_progress.grid(row=1, column=1, padx=10, pady=6, sticky="ew")
        self.em_progress.set(0.0)
        self.em_pct_lbl = customtkinter.CTkLabel(self.coverage_card, text="0% (0 / 0)")
        self.em_pct_lbl.grid(row=1, column=2, padx=20, pady=6, sticky="e")

        # Phones
        lbl_ph = customtkinter.CTkLabel(self.coverage_card, text="Phone Coverage:")
        lbl_ph.grid(row=2, column=0, padx=20, pady=6, sticky="w")
        self.ph_progress = customtkinter.CTkProgressBar(self.coverage_card, height=10)
        self.ph_progress.grid(row=2, column=1, padx=10, pady=6, sticky="ew")
        self.ph_progress.set(0.0)
        self.ph_pct_lbl = customtkinter.CTkLabel(self.coverage_card, text="0% (0 / 0)")
        self.ph_pct_lbl.grid(row=2, column=2, padx=20, pady=6, sticky="e")

        # Websites
        lbl_web = customtkinter.CTkLabel(self.coverage_card, text="Website Coverage:")
        lbl_web.grid(row=3, column=0, padx=20, pady=6, sticky="w")
        self.web_progress = customtkinter.CTkProgressBar(self.coverage_card, height=10)
        self.web_progress.grid(row=3, column=1, padx=10, pady=6, sticky="ew")
        self.web_progress.set(0.0)
        self.web_pct_lbl = customtkinter.CTkLabel(self.coverage_card, text="0% (0 / 0)")
        self.web_pct_lbl.grid(row=3, column=2, padx=20, pady=6, sticky="e")

        # Card 3: Harvest Metrics Details
        self.metrics_card = customtkinter.CTkFrame(page, corner_radius=12, border_width=1, border_color=("#cbd5e1", "#1e293b"))
        self.metrics_card.pack(fill="x", pady=10)
        self.metrics_card.columnconfigure(1, weight=1)

        met_header = customtkinter.CTkLabel(self.metrics_card, text="Session Extraction Statistics", font=customtkinter.CTkFont(size=14, weight="bold"))
        met_header.grid(row=0, column=0, columnspan=2, padx=20, pady=(15, 10), sticky="w")

        metrics_list = [
            ("Total Records Scraped", "0"),
            ("Duplicate Records Screened", "0"),
            ("Wrong State Records Skipped", "0"),
            ("District Processing Completion", "0 / 0"),
            ("Total Web Pages Visited", "0"),
            ("Database Quality State", "Clean (Validated)")
        ]
        
        self.analytics_labels = {}
        for r_idx, (m_title, m_val) in enumerate(metrics_list, start=1):
            lbl_key = customtkinter.CTkLabel(self.metrics_card, text=m_title, font=customtkinter.CTkFont(weight="bold"), width=220, anchor="w")
            lbl_key.grid(row=r_idx, column=0, padx=20, pady=4, sticky="w")
            
            lbl_val = customtkinter.CTkLabel(self.metrics_card, text=m_val, text_color="#94a3b8", anchor="w")
            lbl_val.grid(row=r_idx, column=1, padx=20, pady=4, sticky="w")
            
            self.analytics_labels[m_title] = lbl_val

    def validate_data(self, data_list):
        """Validates scraped school datasets and returns validation details."""
        total = len(data_list)
        if total == 0:
            return {}
            
        valid_emails = 0
        valid_phones = 0
        valid_urls = 0
        missing_address = 0
        missing_email = 0
        missing_phone = 0
        missing_website = 0
        duplicates = 0
        wrong_state = 0
        
        seen = set()
        
        email_regex = r"^[\w\.-]+@[\w\.-]+\.\w+$"
        phone_regex = r"\d{8,}"
        url_regex = r"^(https?:\/\/)?(www\.)?[\w\.-]+\.\w+"
        
        for r in data_list:
            school_name = r.get("School Name", "").strip()
            email = r.get("Email", "").strip()
            phone = (r.get("Mobile", "") or r.get("Landline", "")).strip()
            website = r.get("Website", "").strip()
            address = r.get("Address", "").strip()
            state = r.get("State", "").strip()
            
            if not email:
                missing_email += 1
            elif re.match(email_regex, email, re.IGNORECASE):
                valid_emails += 1
            
            if not phone:
                missing_phone += 1
            elif re.search(phone_regex, phone):
                valid_phones += 1
                
            if not website:
                missing_website += 1
            elif re.match(url_regex, website, re.IGNORECASE):
                valid_urls += 1
                
            if not address:
                missing_address += 1
                
            # Duplicate check
            key = (school_name.lower(), address.lower())
            if key in seen:
                duplicates += 1
            else:
                seen.add(key)
                
            # Wrong state verification
            target_state_name = self.selected_state_slug.replace("-", " ").lower()
            if state and target_state_name not in state.lower():
                wrong_state += 1
                
        email_pct = round((valid_emails / total) * 100, 1)
        phone_pct = round((valid_phones / total) * 100, 1)
        web_pct = round((valid_urls / total) * 100, 1)
        
        # Deduct score for flaws
        possible_points = total * 4
        flaw_deductions = missing_email + missing_phone + missing_address + duplicates + wrong_state
        quality_score = max(0.0, round(((possible_points - flaw_deductions) / possible_points) * 100, 1))
        
        return {
            "total": total,
            "valid_emails": valid_emails,
            "valid_phones": valid_phones,
            "valid_urls": valid_urls,
            "missing_email": missing_email,
            "missing_phone": missing_phone,
            "missing_website": missing_website,
            "missing_address": missing_address,
            "duplicates": duplicates,
            "wrong_state": wrong_state,
            "email_pct": email_pct,
            "phone_pct": phone_pct,
            "web_pct": web_pct,
            "quality_score": quality_score
        }

    def update_analytics_display(self):
        res = self.validate_data(self.scraped_data_list)
        if not res:
            self.score_val_lbl.configure(text="0.0%")
            self.score_progress.set(0.0)
            self.em_progress.set(0.0)
            self.em_pct_lbl.configure(text="0% (0 / 0)")
            self.ph_progress.set(0.0)
            self.ph_pct_lbl.configure(text="0% (0 / 0)")
            self.web_progress.set(0.0)
            self.web_pct_lbl.configure(text="0% (0 / 0)")
            for lbl in self.analytics_labels.values():
                lbl.configure(text="0")
            self.analytics_labels["Database Quality State"].configure(text="No Data")
            return
            
        self.score_val_lbl.configure(text=f"{res['quality_score']}%")
        self.score_progress.set(res["quality_score"] / 100)
        
        self.em_progress.set(res["email_pct"] / 100)
        self.em_pct_lbl.configure(text=f"{res['email_pct']}% ({res['valid_emails']} / {res['total']})")
        
        self.ph_progress.set(res["phone_pct"] / 100)
        self.ph_pct_lbl.configure(text=f"{res['phone_pct']}% ({res['valid_phones']} / {res['total']})")
        
        self.web_progress.set(res["web_pct"] / 100)
        self.web_pct_lbl.configure(text=f"{res['web_pct']}% ({res['valid_urls']} / {res['total']})")
        
        self.analytics_labels["Total Records Scraped"].configure(text=str(res["total"]))
        self.analytics_labels["Duplicate Records Screened"].configure(text=str(res["duplicates"]))
        self.analytics_labels["Wrong State Records Skipped"].configure(text=str(res["wrong_state"]))
        
        active_dists = main.stats["districts"]
        total_dists = len(self.district_checkboxes)
        self.analytics_labels["District Processing Completion"].configure(text=f"{active_dists} / {total_dists}")
        self.analytics_labels["Total Web Pages Visited"].configure(text=str(main.stats["pages"]))
        
        quality_txt = "Clean (Excellent)" if res["quality_score"] > 85 else "Clean (Good)" if res["quality_score"] > 60 else "Corrupted (Review Needed)"
        self.analytics_labels["Database Quality State"].configure(text=quality_txt)

    # ----------------------------
    # 6. DIAGNOSTICS LOGS VIEW
    # ----------------------------
    def create_logs_view(self):
        page = customtkinter.CTkFrame(self.content_container, fg_color="transparent")
        self.pages["Logs"] = page
        
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)

        # Toolbar containing clear, export, search, and filtering
        toolbar = customtkinter.CTkFrame(page, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        toolbar.grid_columnconfigure(0, weight=1)

        title = customtkinter.CTkLabel(toolbar, text="Diagnostics Logs Console", font=customtkinter.CTkFont(size=15, weight="bold"))
        title.grid(row=0, column=0, sticky="w")

        # Log Search Entry
        lbl_search = customtkinter.CTkLabel(toolbar, text="🔍 Search:")
        lbl_search.grid(row=0, column=1, padx=(10, 2))
        
        self.log_search_entry = customtkinter.CTkEntry(toolbar, placeholder_text="Search log keyword...", width=140)
        self.log_search_entry.grid(row=0, column=2, padx=5)
        self.log_search_entry.bind("<KeyRelease>", self.apply_log_filters)

        # Level Filter OptionMenu
        lbl_lvl = customtkinter.CTkLabel(toolbar, text="Level:")
        lbl_lvl.grid(row=0, column=3, padx=(10, 2))
        
        self.log_filter_menu = customtkinter.CTkOptionMenu(
            toolbar, 
            values=["All", "INFO", "WARNING", "ERROR", "SUCCESS"],
            command=self.apply_log_filters,
            width=95
        )
        self.log_filter_menu.grid(row=0, column=4, padx=5)
        self.log_filter_menu.set("All")

        btn_clear = customtkinter.CTkButton(toolbar, text="Clear Console", width=95, fg_color=("#ef4444", "#dc2626"), hover_color=("#dc2626", "#ef4444"), command=self.clear_logs)
        btn_clear.grid(row=0, column=5, padx=5)

        btn_export = customtkinter.CTkButton(toolbar, text="Export Logs", width=95, command=self.export_logs_to_file)
        btn_export.grid(row=0, column=6, padx=5)

        # Large logs text box
        self.logs_textbox = customtkinter.CTkTextbox(
            page, 
            font=customtkinter.CTkFont(family="Courier", size=12)
        )
        self.logs_textbox.grid(row=1, column=0, sticky="nsew")
        self.logs_textbox.configure(state="disabled")

    def clear_logs(self):
        self.all_log_messages.clear()
        self.logs_textbox.configure(state="normal")
        self.logs_textbox.delete("1.0", tk.END)
        self.logs_textbox.configure(state="disabled")
        
        self.mini_logs_box.configure(state="normal")
        self.mini_logs_box.delete("1.0", tk.END)
        self.mini_logs_box.configure(state="disabled")

    def matches_log_filter(self, log_entry):
        search_query = self.log_search_entry.get().lower().strip()
        filter_level = self.log_filter_menu.get()
        
        if filter_level != "All":
            if log_entry["level"].upper() != filter_level.upper():
                return False
                
        if search_query:
            if search_query not in log_entry["raw"].lower():
                return False
                
        return True

    def apply_log_filters(self, event=None):
        self.logs_textbox.configure(state="normal")
        self.logs_textbox.delete("1.0", tk.END)
        
        for entry in self.all_log_messages:
            if self.matches_log_filter(entry):
                self.logs_textbox.insert(tk.END, entry["raw"] + "\n")
                
        self.logs_textbox.see(tk.END)
        self.logs_textbox.configure(state="disabled")

    # ----------------------------
    # 7. SETTINGS VIEW
    # ----------------------------
    def create_settings_view(self):
        page = customtkinter.CTkScrollableFrame(self.content_container, fg_color="transparent")
        self.pages["Settings"] = page
        page.columnconfigure(0, weight=1)

        # Card 1: Browser configurations
        browser_card = customtkinter.CTkFrame(page, corner_radius=12, border_width=1, border_color=("#cbd5e1", "#1e293b"))
        browser_card.pack(fill="x", pady=(0, 15))
        browser_card.columnconfigure(0, weight=1)

        lbl_br = customtkinter.CTkLabel(browser_card, text="Browser Settings (Selenium)", font=customtkinter.CTkFont(size=14, weight="bold"))
        lbl_br.pack(padx=20, pady=(15, 5), anchor="w")

        self.headless_switch = customtkinter.CTkSwitch(browser_card, text="Run Headless (Hidden Browser window)")
        self.headless_switch.pack(padx=20, pady=10, anchor="w")
        if config.HEADLESS:
            self.headless_switch.select()

        self.max_switch = customtkinter.CTkSwitch(browser_card, text="Maximize browser window on start")
        self.max_switch.pack(padx=20, pady=10, anchor="w")
        if config.MAXIMIZE:
            self.max_switch.select()

        self.remember_switch = customtkinter.CTkSwitch(browser_card, text="Remember Last Selection")
        self.remember_switch.pack(padx=20, pady=10, anchor="w")
        if self.user_settings.get("remember_last_selection", False):
            self.remember_switch.select()

        # Card 2: Delays & Wait Settings
        delays_card = customtkinter.CTkFrame(page, corner_radius=12, border_width=1, border_color=("#cbd5e1", "#1e293b"))
        delays_card.pack(fill="x", pady=15)
        delays_card.columnconfigure(1, weight=1)

        lbl_del = customtkinter.CTkLabel(delays_card, text="Concurrency & Delay settings", font=customtkinter.CTkFont(size=14, weight="bold"))
        lbl_del.grid(row=0, column=0, columnspan=2, padx=20, pady=(15, 5), sticky="w")

        # Wait Delay
        lbl_wait = customtkinter.CTkLabel(delays_card, text="Delay Wait (Sec):")
        lbl_wait.grid(row=1, column=0, padx=20, pady=8, sticky="w")
        self.wait_entry = customtkinter.CTkEntry(delays_card, width=80)
        self.wait_entry.grid(row=1, column=1, padx=20, pady=8, sticky="w")
        self.wait_entry.insert(0, str(config.WAIT))

        # Implicit Wait
        lbl_imp = customtkinter.CTkLabel(delays_card, text="Implicit Wait Timeout (Sec):")
        lbl_imp.grid(row=2, column=0, padx=20, pady=8, sticky="w")
        self.imp_entry = customtkinter.CTkEntry(delays_card, width=80)
        self.imp_entry.grid(row=2, column=1, padx=20, pady=8, sticky="w")
        self.imp_entry.insert(0, str(config.IMPLICIT_WAIT))

        # Retry Attempts
        lbl_retry = customtkinter.CTkLabel(delays_card, text="Retry Attempts:")
        lbl_retry.grid(row=3, column=0, padx=20, pady=8, sticky="w")
        self.retry_entry = customtkinter.CTkEntry(delays_card, width=80)
        self.retry_entry.grid(row=3, column=1, padx=20, pady=8, sticky="w")
        self.retry_entry.insert(0, str(config.RETRY))

        # Strict State Filter Switch
        self.strict_switch = customtkinter.CTkSwitch(delays_card, text="Strict State geographical validation filter")
        self.strict_switch.grid(row=4, column=0, columnspan=2, padx=20, pady=10, sticky="w")
        if config.STRICT_STATE:
            self.strict_switch.select()

        # Speed Profile dropdown
        lbl_speed = customtkinter.CTkLabel(delays_card, text="Speed Profile:")
        lbl_speed.grid(row=5, column=0, padx=20, pady=8, sticky="w")
        self.speed_profile_menu = customtkinter.CTkOptionMenu(
            delays_card, 
            values=["Safe", "Balanced", "Fast"],
            command=self.on_speed_profile_changed
        )
        self.speed_profile_menu.grid(row=5, column=1, padx=20, pady=8, sticky="w")
        current_profile = getattr(config, "SPEED_PROFILE", "balanced").capitalize()
        if current_profile not in ["Safe", "Balanced", "Fast"]:
            current_profile = "Balanced"
        self.speed_profile_menu.set(current_profile)

        # Card 3: Theme and UI scaling
        theme_card = customtkinter.CTkFrame(page, corner_radius=12, border_width=1, border_color=("#cbd5e1", "#1e293b"))
        theme_card.pack(fill="x", pady=15)
        theme_card.columnconfigure(1, weight=1)

        lbl_th = customtkinter.CTkLabel(theme_card, text="Interface Customization", font=customtkinter.CTkFont(size=14, weight="bold"))
        lbl_th.grid(row=0, column=0, columnspan=2, padx=20, pady=(15, 5), sticky="w")

        lbl_mode = customtkinter.CTkLabel(theme_card, text="Theme Mode:")
        lbl_mode.grid(row=1, column=0, padx=20, pady=8, sticky="w")
        
        self.app_theme_combo = customtkinter.CTkOptionMenu(
            theme_card, 
            values=["Dark", "Light", "System"],
            command=self.change_appearance_mode
        )
        self.app_theme_combo.grid(row=1, column=1, padx=20, pady=8, sticky="w")
        self.app_theme_combo.set("Dark")

        lbl_scale = customtkinter.CTkLabel(theme_card, text="UI Scaling:")
        lbl_scale.grid(row=2, column=0, padx=20, pady=8, sticky="w")

        self.app_scale_combo = customtkinter.CTkOptionMenu(
            theme_card, 
            values=["80%", "90%", "100%", "110%", "120%"],
            command=self.change_scaling
        )
        self.app_scale_combo.grid(row=2, column=1, padx=20, pady=8, sticky="w")
        self.app_scale_combo.set("100%")

        # Card 4: System Health Check & Diagnostics
        diag_card = customtkinter.CTkFrame(page, corner_radius=12, border_width=1, border_color=("#cbd5e1", "#1e293b"))
        diag_card.pack(fill="x", pady=15)
        
        lbl_diag = customtkinter.CTkLabel(diag_card, text="System Diagnostics & Diagnostics Report", font=customtkinter.CTkFont(size=14, weight="bold"))
        lbl_diag.pack(padx=20, pady=(15, 5), anchor="w")

        diag_btns_frame = customtkinter.CTkFrame(diag_card, fg_color="transparent")
        diag_btns_frame.pack(fill="x", padx=20, pady=(5, 15))
        diag_btns_frame.columnconfigure((0, 1), weight=1)

        btn_run_diag = customtkinter.CTkButton(
            diag_btns_frame,
            text="🩺 Run System Health Check",
            fg_color=("#10b981", "#059669"),
            hover_color=("#059669", "#10b981"),
            font=customtkinter.CTkFont(weight="bold"),
            command=self.show_diagnostics_window
        )
        btn_run_diag.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        btn_gen_rep = customtkinter.CTkButton(
            diag_btns_frame,
            text="📄 Generate Diagnostics Report",
            fg_color=("#3b82f6", "#2563eb"),
            hover_color=("#2563eb", "#3b82f6"),
            font=customtkinter.CTkFont(weight="bold"),
            command=self.generate_diagnostics_report
        )
        btn_gen_rep.grid(row=0, column=1, padx=(5, 0), sticky="ew")

        # Card 5: Factory Reset Actions
        reset_card = customtkinter.CTkFrame(page, corner_radius=12, border_width=1, border_color=("#cbd5e1", "#1e293b"))
        reset_card.pack(fill="x", pady=15)
        
        lbl_rst = customtkinter.CTkLabel(reset_card, text="Factory Reset Configurations", font=customtkinter.CTkFont(size=14, weight="bold"))
        lbl_rst.pack(padx=20, pady=(15, 5), anchor="w")

        btn_reset = customtkinter.CTkButton(
            reset_card, 
            text="⚠️ Factory Reset Application Settings", 
            fg_color=("#ef4444", "#dc2626"), 
            hover_color=("#dc2626", "#ef4444"),
            font=customtkinter.CTkFont(weight="bold"),
            command=self.reset_settings
        )
        btn_reset.pack(fill="x", padx=20, pady=(5, 15))

        # Save Settings button
        btn_save_config = customtkinter.CTkButton(
            page, 
            text="💾 Save & Apply Configurations", 
            height=40,
            font=customtkinter.CTkFont(weight="bold"),
            command=self.save_settings_action
        )
        btn_save_config.pack(fill="x", pady=10)

    def generate_diagnostics_report(self):
        """Generates a JSON diagnostic report file containing environment specs and recent logs."""
        try:
            report_data = {
                "version": getattr(config, "VERSION", "6.5.0"),
                "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "system": {
                    "os": f"{platform.system()} {platform.release()} ({platform.machine()})",
                    "python": sys.version.split(" ")[0],
                    "cwd": os.getcwd()
                },
                "config": {
                    "board": self.selected_board,
                    "state": self.selected_state_slug,
                    "headless": getattr(config, "HEADLESS", True),
                    "speed_profile": getattr(config, "SPEED_PROFILE", "balanced"),
                    "output_folder": getattr(config, "OUTPUT_FOLDER", "Output"),
                    "strict_state": getattr(config, "STRICT_STATE", True)
                },
                "stats": main.stats,
                "recent_activities": self.recent_activities,
                "recent_logs": [entry["raw"] for entry in self.all_log_messages[-50:]]
            }
            
            file_path = filedialog.asksaveasfilename(
                defaultextension=".json",
                filetypes=[("JSON Diagnostics File", "*.json"), ("All Files", "*.*")],
                initialfile=f"schoolminer_diagnostics_{int(time.time())}.json"
            )
            if file_path:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(report_data, f, indent=4)
                self.log_queue.put(f"[SYSTEM] [SUCCESS] Diagnostic report saved to: {file_path}")
                messagebox.showinfo("Diagnostics Saved", f"Diagnostic report file saved successfully:\n{file_path}")
        except Exception as e:
            self.log_queue.put(f"[SYSTEM] [ERROR] Failed to generate diagnostic report: {e}")

    def show_diagnostics_window(self):
        """Displays a modal dialog running live health checks on system components."""
        diag_win = customtkinter.CTkToplevel(self)
        diag_win.title("System Health Check & Diagnostics")
        diag_win.geometry("560x520")
        diag_win.resizable(False, False)
        diag_win.grab_set()  # Make modal
        
        lbl_title = customtkinter.CTkLabel(diag_win, text="🩺 System Health & Diagnostics", font=customtkinter.CTkFont(size=18, weight="bold"))
        lbl_title.pack(padx=20, pady=(20, 10))
        
        scroll_frame = customtkinter.CTkScrollableFrame(diag_win, height=360)
        scroll_frame.pack(fill="both", expand=True, padx=20, pady=10)
        scroll_frame.columnconfigure(1, weight=1)
        
        # Diagnostics Execution
        checks = []
        
        # 1. State Registry
        reg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "states_registry.json")
        if os.path.exists(reg_path):
            try:
                with open(reg_path, "r", encoding="utf-8") as f:
                    reg_data = json.load(f)
                checks.append(("State Registry File", f"Passed ({len(reg_data)} states mapped)", True))
            except Exception as e:
                checks.append(("State Registry File", f"Failed: {e}", False))
        else:
            checks.append(("State Registry File", "Failed: File missing", False))
            
        # 2. Output Directory Write Access
        try:
            out_folder = getattr(config, "OUTPUT_FOLDER", "Output")
            os.makedirs(out_folder, exist_ok=True)
            test_file = os.path.join(out_folder, ".sm_perm_test.tmp")
            with open(test_file, "w") as f:
                f.write("test")
            if os.path.exists(test_file):
                os.remove(test_file)
            checks.append(("Output Directory Access", f"Passed (Writable: {out_folder})", True))
        except Exception as e:
            checks.append(("Output Directory Access", f"Failed: {e}", False))
            
        # 3. Python Environment & Core Dependencies
        try:
            import pandas
            import openpyxl
            import selenium
            checks.append(("Python Dependencies", "Passed (pandas, openpyxl, selenium loaded)", True))
        except Exception as e:
            checks.append(("Python Dependencies", f"Failed: {e}", False))
            
        # 4. Chrome WebDriver Availability
        try:
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager
            checks.append(("WebDriver Chrome Engine", "Passed (DriverManager Service Ready)", True))
        except Exception as e:
            checks.append(("WebDriver Chrome Engine", f"Warning: {e}", False))

        # 5. Config Persistence Access
        try:
            cfg_path = os.path.join(os.getcwd(), "config.py")
            if os.access(cfg_path, os.W_OK):
                checks.append(("Config Persistence Access", "Passed (Writable: config.py)", True))
            else:
                checks.append(("Config Persistence Access", "Warning: config.py read-only", False))
        except Exception as e:
            checks.append(("Config Persistence Access", f"Error: {e}", False))
            
        # Render Check Items
        for r_idx, (name, status_str, is_pass) in enumerate(checks):
            lbl_name = customtkinter.CTkLabel(scroll_frame, text=name, font=customtkinter.CTkFont(weight="bold"), anchor="w")
            lbl_name.grid(row=r_idx, column=0, padx=10, pady=8, sticky="w")
            
            badge_color = "#10b981" if is_pass else "#ef4444"
            icon = "🟢 PASS" if is_pass else "🔴 FAIL"
            
            lbl_status = customtkinter.CTkLabel(
                scroll_frame, 
                text=f"{icon} - {status_str}", 
                text_color=badge_color, 
                font=customtkinter.CTkFont(size=11), 
                anchor="w",
                justify="left"
            )
            lbl_status.grid(row=r_idx, column=1, padx=10, pady=8, sticky="w")
            
        btn_close = customtkinter.CTkButton(diag_win, text="Close Diagnostics", command=diag_win.destroy)
        btn_close.pack(pady=(5, 15))

    def save_settings_action(self):
        try:
            config.HEADLESS = bool(self.headless_switch.get())
            config.MAXIMIZE = bool(self.max_switch.get())
            config.STRICT_STATE = bool(self.strict_switch.get())
            
            config.WAIT = int(self.wait_entry.get().strip())
            config.IMPLICIT_WAIT = int(self.imp_entry.get().strip())
            config.RETRY = int(self.retry_entry.get().strip())
            
            self.save_config_to_file()
            self.save_user_settings()
            self.log_activity("Saved application parameters.")
            self.log_queue.put("[SYSTEM] [SUCCESS] System parameters updated and saved successfully.")
        except ValueError:
            self.log_queue.put("[SYSTEM] [ERROR] Settings update failed. Please enter valid numbers for wait parameters.")

    def on_speed_profile_changed(self, choice):
        try:
            profile_name = choice.strip().lower()
            if profile_name in main.SPEED_PROFILES:
                profile = main.SPEED_PROFILES[profile_name]
                config.WAIT = profile["WAIT"]
                config.IMPLICIT_WAIT = profile["IMPLICIT_WAIT"]
                config.PAGE_DELAY = profile["PAGE_DELAY"]
                config.SPEED_PROFILE = profile_name
                
                # Update text fields in settings page
                self.wait_entry.delete(0, tk.END)
                self.wait_entry.insert(0, str(config.WAIT))
                self.imp_entry.delete(0, tk.END)
                self.imp_entry.insert(0, str(config.IMPLICIT_WAIT))
                
                self.save_config_to_file()
                self.log_activity(f"Changed speed profile to: {choice}")
                self.log_queue.put(f"[SYSTEM] [SUCCESS] Speed profile changed to {choice}. Delays automatically updated.")
        except Exception as e:
            self.log_queue.put(f"[SYSTEM] [ERROR] Failed to update speed profile: {e}")

    def save_config_to_file(self):
        try:
            config_path = os.path.join(os.getcwd(), "config.py")
            content = f"""# ===========================================
# SchoolMiner Configuration
# ===========================================

# ---------- Board ----------
BOARDS = ["cbse", "icse", "ib", "state-board", "pre-primary"]

# ---------- State Filter ----------
STRICT_STATE = {config.STRICT_STATE}

# ---------- District ----------
DISTRICTS = {config.DISTRICTS}

# ---------- Export ----------
EXPORT = {config.EXPORT}

# ---------- Data Selection ----------
FIELDS = {config.FIELDS}

# ---------- Browser ----------
HEADLESS = {config.HEADLESS}
MAXIMIZE = {config.MAXIMIZE}

# ---------- Delay ----------
WAIT = {config.WAIT}
IMPLICIT_WAIT = {config.IMPLICIT_WAIT}
PAGE_DELAY = {config.PAGE_DELAY}

# ---------- Retry ----------
RETRY = {config.RETRY}

# ---------- Output Folder ----------
OUTPUT_FOLDER = "{config.OUTPUT_FOLDER}"
AUTO_FILENAME = {config.AUTO_FILENAME}
SHOW_SUMMARY = {config.SHOW_SUMMARY}
LOG = {config.LOG}
GUI = {config.GUI}
VERSION = "{config.VERSION}"
SPEED_PROFILE = "{getattr(config, 'SPEED_PROFILE', 'balanced')}"
DEBUG = {config.DEBUG}
"""
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            self.log_queue.put(f"[SYSTEM] [ERROR] Failed to persist config: {e}")

    def reset_settings(self):
        confirm = messagebox.askyesno("Reset Settings", "Are you sure you want to reset all configurations to factory defaults?")
        if confirm:
            self.selected_board = "cbse"
            self.selected_state_slug = ""
            config.STRICT_STATE = True
            config.EXPORT = ["xlsx", "csv"]
            config.FIELDS = []
            config.HEADLESS = True
            config.MAXIMIZE = True
            self.save_user_settings()
            config.WAIT = 4
            config.IMPLICIT_WAIT = 10
            config.PAGE_DELAY = 2
            config.RETRY = 3
            config.OUTPUT_FOLDER = "Output"
            config.SPEED_PROFILE = "balanced"
            
            # Reset UI switches
            self.headless_switch.select() # Default is True
            self.max_switch.select()
            self.strict_switch.select()
            self.remember_switch.deselect()
            self.speed_profile_menu.set("Balanced")
            
            self.wait_entry.delete(0, tk.END)
            self.wait_entry.insert(0, "4")
            self.imp_entry.delete(0, tk.END)
            self.imp_entry.insert(0, "10")
            self.retry_entry.delete(0, tk.END)
            self.retry_entry.insert(0, "3")
            
            self.state_combo.set("Select State...")
            self.board_menu.set("cbse")
            self.folder_entry.delete(0, tk.END)
            self.folder_entry.insert(0, "Output")
            self.format_menu.set("Excel (xlsx)")
            
            self.save_config_to_file()
            self.log_activity("Reset settings to defaults.")
            self.log_queue.put("[SYSTEM] [SUCCESS] All application configurations have been reset to factory defaults.")

    # ----------------------------
    # 8. ABOUT VIEW
    # ----------------------------
    def create_about_view(self):
        page = customtkinter.CTkFrame(self.content_container, fg_color="transparent")
        self.pages["About"] = page
        page.columnconfigure(0, weight=1)

        # Centered branding panel
        brand_card = customtkinter.CTkFrame(page, corner_radius=12, border_width=1, border_color=("#cbd5e1", "#1e293b"))
        brand_card.pack(fill="both", expand=True, padx=20, pady=20)
        brand_card.columnconfigure(0, weight=1)

        logo_lbl = customtkinter.CTkLabel(brand_card, text="🚀", font=customtkinter.CTkFont(size=72))
        logo_lbl.pack(pady=(40, 10))

        title_lbl = customtkinter.CTkLabel(brand_card, text="SchoolMiner Enterprise", font=customtkinter.CTkFont(size=28, weight="bold"))
        title_lbl.pack(pady=5)

        ver_lbl = customtkinter.CTkLabel(brand_card, text=f"Version {config.VERSION} (Production)", font=customtkinter.CTkFont(size=14, weight="bold"), text_color="#3b82f6")
        ver_lbl.pack(pady=2)

        desc_lbl = customtkinter.CTkLabel(
            brand_card, 
            text="Commercial-Grade Academic Directory Extraction & Pipeline Harvesting Suite.\nDesigned for research institutions, enterprise operations, and school metrics aggregators.", 
            font=customtkinter.CTkFont(size=13),
            text_color="#94a3b8",
            justify="center"
        )
        desc_lbl.pack(pady=15)

        # System Information Table
        info_frame = customtkinter.CTkFrame(brand_card, fg_color=("#f1f5f9", "#131a2e"), border_width=1, border_color=("#cbd5e1", "#1e293b"), corner_radius=8)
        info_frame.pack(fill="x", padx=40, pady=(20, 40))
        info_frame.columnconfigure(1, weight=1)

        sys_details = [
            ("Operating System", f"{platform.system()} {platform.release()} ({platform.machine()})"),
            ("Python Runtime", sys.version.split(" ")[0]),
            ("Platform Node", platform.node()),
            ("Working Directory", os.getcwd()),
            ("Active Driver Suite", "WebDriver Chrome (Auto-Managed)"),
            ("Licensing Status", "Enterprise Commercial License (Active)")
        ]

        for idx, (lbl_key, lbl_val) in enumerate(sys_details):
            key = customtkinter.CTkLabel(info_frame, text=lbl_key, font=customtkinter.CTkFont(weight="bold"), width=150, anchor="w")
            key.grid(row=idx, column=0, padx=15, pady=4, sticky="w")

            val = customtkinter.CTkLabel(info_frame, text=lbl_val, text_color="#94a3b8", anchor="w")
            val.grid(row=idx, column=1, padx=15, pady=4, sticky="w")

    # ----------------------------
    # WIDGET CREATORS & ACTIONS
    # ----------------------------
    def populate_field_selection(self):
        """Build export checklist variables and widget frames."""
        for field in FIELD_MAP.keys():
            cb = customtkinter.CTkCheckBox(self.field_scroll, text=field)
            cb.pack(anchor="w", pady=4, padx=10)
            if field in self.presets["Default Contact"]:
                cb.select()
            self.field_checkboxes[field] = cb

    def filter_districts_checkboxes(self, event=None):
        """Filter visual checklist elements based on user typing."""
        search_query = self.dist_search.get().lower().strip()
        for cb in self.district_checkboxes:
            district_name = cb.cget("text")
            if not search_query or search_query in district_name.lower():
                cb.pack(anchor="w", pady=4, padx=10)
            else:
                cb.pack_forget()

    def select_all_districts(self):
        for cb in self.district_checkboxes:
            cb.select()
        self.update_district_count_label()
        self.update_start_button_state()

    def clear_all_districts(self):
        for cb in self.district_checkboxes:
            cb.deselect()
        self.update_district_count_label()
        self.update_start_button_state()

    def select_all_fields(self):
        for cb in self.field_checkboxes.values():
            cb.select()

    def clear_all_fields(self):
        for cb in self.field_checkboxes.values():
            cb.deselect()

    def load_preset_selection(self, preset_name):
        fields = self.presets.get(preset_name, [])
        if not fields:
            return
        self.clear_all_fields()
        for f in fields:
            if f in self.field_checkboxes:
                self.field_checkboxes[f].select()
        self.log_queue.put(f"[SYSTEM] Loaded field selection preset: {preset_name}")

    def save_custom_preset(self):
        name = self.preset_entry.get().strip()
        if not name:
            self.log_queue.put("[SYSTEM] [WARNING] Please enter a valid preset name.")
            return
        selected = [f for f, cb in self.field_checkboxes.items() if cb.get()]
        if not selected:
            self.log_queue.put("[SYSTEM] [WARNING] Cannot save preset with zero fields selected.")
            return
        self.presets[name] = selected
        
        current_values = self.preset_combo.cget("values")
        if name not in current_values:
            self.preset_combo.configure(values=list(self.presets.keys()))
        self.preset_combo.set(name)
        self.preset_entry.delete(0, tk.END)
        self.log_queue.put(f"[SYSTEM] [SUCCESS] Saved field selection preset: {name}")

    def browse_folder(self):
        folder = filedialog.askdirectory(initialdir=".")
        if folder:
            self.folder_entry.delete(0, tk.END)
            self.folder_entry.insert(0, folder)
            
            if hasattr(self, "export_dir_entry"):
                self.export_dir_entry.delete(0, tk.END)
                self.export_dir_entry.insert(0, folder)

    # ----------------------------
    # DISTRICTS BACKGROUND THREAD
    # ----------------------------
    def on_board_selected(self, choice):
        self.selected_board = choice.strip().lower()
        self.save_user_settings()
        self.log_activity(f"Selected board: {choice}")
        if self.selected_state_slug and self.state_combo.get() != "Select State...":
            self.dispatch_load_districts()
        else:
            self.clear_districts_checklist_disabled()

    def on_state_selected(self, choice):
        if choice == "Select State...":
            self.selected_state_slug = ""
            config.DISTRICTS = []
            self.save_user_settings()
            self.clear_districts_checklist_disabled()
            self.update_project_displays()
            return
            
        slug = STATES_MAP.get(choice, choice.lower().strip().replace(" ", "-"))
        self.selected_state_slug = slug
        self.save_user_settings()
        self.update_project_displays()
        self.log_activity(f"Selected state: {choice}")
        
        # Load districts automatically
        self.dispatch_load_districts()

    def clear_districts_checklist_disabled(self):
        # Clear existing checklist
        for cb in self.district_checkboxes:
            cb.destroy()
        self.district_checkboxes.clear()
        
        # Destroy any existing retry/error frames
        if hasattr(self, "error_frame") and self.error_frame:
            try:
                self.error_frame.destroy()
            except Exception:
                pass
            self.error_frame = None
            
        # Reset districts title
        self.dist_title.configure(text="Districts Checklist")
        
        # Disable controls
        self.btn_all_dist.configure(state="disabled")
        self.btn_clear_dist.configure(state="disabled")
        self.dist_search.configure(state="disabled")
        self.btn_start.configure(state="disabled")

    def update_start_button_state(self):
        board = self.board_menu.get().strip().lower()
        state = self.selected_state_slug
        selected_dists = [cb.cget("text") for cb in self.district_checkboxes if cb.get()]
        
        has_board = bool(board)
        has_state = bool(state) and self.state_combo.get() != "Select State..."
        has_dists = len(selected_dists) > 0
        
        is_busy = (self.scraper_thread and self.scraper_thread.is_alive()) or \
                  (self.districts_loading_thread and self.districts_loading_thread.is_alive()) or \
                  (hasattr(self, "dist_loading_pb") and self.dist_loading_pb is not None)
                  
        if has_board and has_state and has_dists and not is_busy:
            self.btn_start.configure(state="normal")
        else:
            self.btn_start.configure(state="disabled")

    def on_district_checkbox_changed(self):
        self.update_district_count_label()
        self.update_start_button_state()

    def update_district_count_label(self):
        """Updates the district panel header with selected/total count."""
        total = len(self.district_checkboxes)
        selected = sum(1 for cb in self.district_checkboxes if cb.get())
        if total > 0:
            self.dist_title.configure(text=f"Districts Checklist ({selected}/{total} selected)")
        else:
            self.dist_title.configure(text="Districts Checklist")

    def dispatch_load_districts(self):
        """Starts district loading thread."""
        state = self.selected_state_slug
        board = self.board_menu.get().strip().lower()
        if not state or self.state_combo.get() == "Select State...":
            self.clear_districts_checklist_disabled()
            return
        
        # Check cache first — serve instantly if available
        cache_key = (board, state)
        if cache_key in self.district_cache:
            cached = self.district_cache[cache_key]
            self.districts_list = cached
            names = [d["name"] for d in cached]
            self.log_queue.put(f"[SYSTEM] [SUCCESS] Loaded {len(names)} districts from cache (instant).")
            self.update_districts_checklist(names)
            self.set_status("Ready.", "\ud83d\udfe2")
            self.log_activity(f"Loaded {len(names)} districts (cached).")
            return
            
        # Disable controls during loading
        self.btn_all_dist.configure(state="disabled")
        self.btn_clear_dist.configure(state="disabled")
        self.dist_search.configure(state="disabled")
        self.btn_start.configure(state="disabled")
        
        # Clear existing checklist
        for cb in self.district_checkboxes:
            cb.destroy()
        self.district_checkboxes.clear()
        
        # Destroy any existing retry/error frames
        if hasattr(self, "error_frame") and self.error_frame:
            try:
                self.error_frame.destroy()
            except Exception:
                pass
            self.error_frame = None

        # Show loading indicator in checklist frame (loading text + progress bar)
        if hasattr(self, "dist_loading_lbl") and self.dist_loading_lbl:
            try:
                self.dist_loading_lbl.destroy()
            except Exception:
                pass
        self.dist_loading_lbl = customtkinter.CTkLabel(
            self.dist_scroll, 
            text="⏳ Loading districts... Please wait.", 
            font=customtkinter.CTkFont(slant="italic"),
            text_color="#3b82f6"
        )
        self.dist_loading_lbl.pack(pady=(40, 10))

        if hasattr(self, "dist_loading_pb") and self.dist_loading_pb:
            try:
                self.dist_loading_pb.destroy()
            except Exception:
                pass
        self.dist_loading_pb = customtkinter.CTkProgressBar(
            self.dist_scroll,
            mode="indeterminate",
            width=180,
            progress_color="#3b82f6"
        )
        self.dist_loading_pb.pack(pady=(0, 40))
        self.dist_loading_pb.start()
        
        # Reset districts title
        self.dist_title.configure(text="Districts Checklist")
        
        self.log_queue.put(f"[SYSTEM] Loading districts list for board '{board.upper()}' and state '{state}' in background...")
        self.set_status("Loading districts...", "🟡")
        
        state_obj = {
            "display_name": self.state_combo.get(),
            "slug": state
        }
        self.districts_loading_thread = threading.Thread(
            target=self.load_districts_worker,
            args=(board, state_obj),
            daemon=True
        )
        self.districts_loading_thread.start()

    def load_districts_worker(self, board, state_obj):
        """Thread worker fetching district lists via DistrictLoader."""
        try:
            from district_loader import DistrictLoader
            loader = DistrictLoader(main.start_browser, logger=lambda m: self.log_queue.put(f"[SYSTEM] {m}"))
            raw_districts = loader.load_districts(board, state_obj)
            
            self.districts_list = raw_districts
            names = [d["name"] for d in raw_districts]
            
            # Store in cache for instant reloads
            cache_key = (board, state_obj.get("slug", ""))
            self.district_cache[cache_key] = raw_districts
            
            self.after(0, lambda: self.update_districts_checklist(names))
            self.log_queue.put(f"[SYSTEM] [SUCCESS] Loaded {len(names)} districts list. Check checklist panel.")
            self.after(0, lambda: self.set_status("Ready.", "🟢"))
            self.after(0, lambda: self.log_activity(f"Loaded {len(names)} districts list."))
        except Exception as e:
            self.log_queue.put(f"[SYSTEM] [ERROR] Loading districts failed: {e}")
            self.after(0, lambda: self.handle_district_load_failure(str(e)))

    def handle_district_load_failure(self, error_msg):
        """Executes in main thread: handles district loading failure with a user-friendly message."""
        if hasattr(self, "dist_loading_lbl") and self.dist_loading_lbl:
            try:
                self.dist_loading_lbl.destroy()
            except Exception:
                pass
            self.dist_loading_lbl = None
            
        if hasattr(self, "dist_loading_pb") and self.dist_loading_pb:
            try:
                self.dist_loading_pb.stop()
                self.dist_loading_pb.destroy()
            except Exception:
                pass
            self.dist_loading_pb = None
            
        self.dist_title.configure(text="Districts Checklist (Failed)")
                
        # Show error frame with retry button
        self.error_frame = customtkinter.CTkFrame(self.dist_scroll, fg_color="transparent")
        self.error_frame.pack(pady=30, fill="both", expand=True)
        
        self.dist_error_lbl = customtkinter.CTkLabel(
            self.error_frame, 
            text=f"❌ Failed to load districts:\n{error_msg}\n\nPlease check your internet connection.", 
            font=customtkinter.CTkFont(size=12, slant="italic"),
            text_color="#ef4444"
        )
        self.dist_error_lbl.pack(pady=10)
        
        self.btn_retry_districts = customtkinter.CTkButton(
            self.error_frame,
            text="🔄 Retry Loading Districts",
            width=180,
            command=self.dispatch_load_districts
        )
        self.btn_retry_districts.pack(pady=10)
        
        # Reset control states: keep checklist and scrape actions disabled
        self.btn_all_dist.configure(state="disabled")
        self.btn_clear_dist.configure(state="disabled")
        self.dist_search.configure(state="disabled")
        self.btn_start.configure(state="disabled")
        
        self.set_status("Error loading districts", "🔴")

    def update_districts_checklist(self, names):
        """Executes in main thread: updates GUI checkboxes."""
        if hasattr(self, "dist_loading_lbl") and self.dist_loading_lbl:
            try:
                self.dist_loading_lbl.destroy()
            except Exception:
                pass
            self.dist_loading_lbl = None
            
        if hasattr(self, "dist_loading_pb") and self.dist_loading_pb:
            try:
                self.dist_loading_pb.stop()
                self.dist_loading_pb.destroy()
            except Exception:
                pass
            self.dist_loading_pb = None
            
        # Update title with count
        self.dist_title.configure(text=f"Districts Checklist ({len(names)} loaded)")
            
        # Re-enable all controls
        self.btn_all_dist.configure(state="normal")
        self.btn_clear_dist.configure(state="normal")
        self.dist_search.configure(state="normal")
        
        for cb in self.district_checkboxes:
            cb.destroy()
        self.district_checkboxes.clear()
        
        for name in names:
            cb = customtkinter.CTkCheckBox(
                self.dist_scroll, 
                text=name, 
                command=self.on_district_checkbox_changed
            )
            cb.pack(anchor="w", pady=6, padx=10)
            self.district_checkboxes.append(cb)
            # Districts start unselected by default
            
        self.update_district_count_label()
        self.update_project_displays()
        self.update_start_button_state()

    # ----------------------------
    # SCRAPER BACKGROUND THREAD
    # ----------------------------
    def _set_controls_state(self, mode):
        """Consolidated control button state manager.
        Modes: idle, running, paused, stopping
        """
        states = {
            "idle":     ("normal",   "disabled", "disabled", "disabled"),
            "running":  ("disabled", "normal",   "disabled", "normal"),
            "paused":   ("disabled", "disabled", "normal",   "normal"),
            "stopping": ("disabled", "disabled", "disabled", "disabled"),
        }
        s_start, s_pause, s_resume, s_stop = states.get(mode, states["idle"])
        self.btn_start.configure(state=s_start)
        self.btn_pause.configure(state=s_pause)
        self.btn_resume.configure(state=s_resume)
        self.btn_stop.configure(state=s_stop)

    def dispatch_scraper_worker(self):
        """Starts worker threads."""
        board = self.board_menu.get().strip().lower()
        state = self.selected_state_slug
        output_folder = self.folder_entry.get().strip()
        format_val = self.format_menu.get()
        
        selected_fields = [f for f, cb in self.field_checkboxes.items() if cb.get()]
        selected_dists = [cb.cget("text") for cb in self.district_checkboxes if cb.get()]
        
        if not selected_fields:
            messagebox.showwarning("Selection Required", "Please select at least one field to export.")
            self.log_queue.put("[SYSTEM] [WARNING] Please select at least one field to export.")
            return
        if not selected_dists:
            messagebox.showwarning("No Districts Selected", "Please check at least one district from the checklist before starting the scraper.")
            self.log_queue.put("[SYSTEM] [WARNING] No districts selected. Check at least one district to scrape.")
            return
            
        # Set output config (NOT district selection — that's passed directly)
        config.OUTPUT_FOLDER = output_folder
        
        if format_val == "Excel (xlsx)":
            config.EXPORT = ["xlsx"]
        elif format_val == "CSV only":
            config.EXPORT = ["csv"]
        else:
            config.EXPORT = ["xlsx", "csv"]
            
        config.FIELDS = [FIELD_MAP[f] for f in selected_fields]
        
        # Reset thread controls
        self.stop_requested = False
        self.pause_event.set()
        self.is_paused = False
        self.scraped_data_list.clear()
        self.elapsed_time_str = "0s"
        self.eta_str = "Estimating..."
        self.current_scrape_page = 0
        self.current_scrape_district = "None"
        
        # Reset global metrics
        main.stats = {
            "districts": 0,
            "pages": 0,
            "schools_found": 0,
            "exported": 0,
            "duplicates": 0,
            "wrong_state": 0,
            "errors": 0,
        }
        main.seen_schools.clear()
        
        # Toggle GUI states
        self._set_controls_state("running")
        
        self.set_status("Scraping...", "\ud83d\udfe1")
        self.update_project_displays()
        self.log_activity("Started scraper execution.")
        
        # Spawn thread
        self.scraper_thread = threading.Thread(
            target=self.scraper_worker,
            args=(selected_dists, selected_fields),
            daemon=True
        )
        self.scraper_thread.start()

    def scraper_worker(self, selected_dists, selected_fields):
        """Background scraper thread calling main.py scraping helpers."""
        driver = None
        start_time = time.time()
        try:
            self.log_queue.put("[SYSTEM] Starting Chrome headless scraping engine...")
            driver = main.start_browser()
            self.after(0, self.lift) # Bring GUI to front / focus!
            
            districts_list = self.districts_list
            if not districts_list:
                state_obj = {
                    "display_name": self.state_combo.get(),
                    "slug": self.selected_state_slug
                }
                districts_list = main.get_districts(driver, state_obj=state_obj, board=self.selected_board)
                self.districts_list = districts_list
                
            # CRITICAL FIX: Pass selected district names directly instead of using global DISTRICTS
            filtered_districts = main.filter_districts(districts_list, selected_names=selected_dists)
            main.stats["districts"] = len(filtered_districts)
            
            total_districts = len(filtered_districts)
            self.log_queue.put(f"[SYSTEM] Targets filtered: {total_districts} districts to scrape.")
            
            # Page-level progress callback for live status
            def on_page_progress(dist_name, page_num, schools_on_page):
                self.current_scrape_page = page_num
                self.current_scrape_district = dist_name
            
            for idx, district in enumerate(filtered_districts):
                if self.stop_requested:
                    break
                    
                if not self.pause_event.is_set():
                    self.log_queue.put("[SYSTEM] Scraper Paused.")
                    self.after(0, lambda: self.set_status("Paused", "\ud83d\udfe1"))
                    self.after(0, lambda: self._set_controls_state("paused"))
                    self.pause_event.wait()
                    if self.stop_requested:
                        break
                    self.log_queue.put("[SYSTEM] Scraper Resumed.")
                    self.after(0, lambda: self.set_status("Scraping...", "\ud83d\udfe1"))
                    self.after(0, lambda: self._set_controls_state("running"))
                    
                dist_name = district["name"]
                self.log_queue.put(f"[SYSTEM] Scraping District [{idx+1}/{total_districts}]: {dist_name}")
                self.after(0, lambda d=dist_name, i=idx, t=total_districts: self.update_running_progress(d, i, t, start_time))
                
                district_data = main.scrape_district(
                    driver, district, 
                    state_slug=self.selected_state_slug,
                    stop_flag=lambda: self.stop_requested,
                    pause_event=self.pause_event,
                    progress_callback=on_page_progress
                )
                self.scraped_data_list.extend(district_data)
                
                # Update progress after each district completes
                self.after(0, lambda d=dist_name, i=idx, t=total_districts: self.update_running_progress(d, i+1, t, start_time))
                
            if self.scraped_data_list and not self.stop_requested:
                self.log_queue.put("[SYSTEM] Scrape loop completed. Generating reports...")
                self.after(0, lambda: self.set_status("Exporting...", "\ud83d\udfe1"))
                self.export_report_files(selected_fields)
            elif self.stop_requested:
                self.log_queue.put("[SYSTEM] [WARNING] Scraping halted by Stop request.")
                if self.scraped_data_list:
                    self.log_queue.put("[SYSTEM] Saving partial data captured so far...")
                    self.after(0, lambda: self.set_status("Exporting...", "\ud83d\udfe1"))
                    self.export_report_files(selected_fields)
            else:
                self.log_queue.put("[SYSTEM] [WARNING] No school records scraped.")
                
            self.after(0, self.scraper_finished_callback)
            
        except Exception as e:
            self.log_queue.put(f"[SYSTEM] [ERROR] Scraper thread crashed: {e}")
            self.after(0, lambda: self.set_status("Error", "\ud83d\udd34"))
            self.after(0, self.scraper_finished_callback)
        finally:
            if driver:
                driver.quit()

    def update_running_progress(self, dist_name, index, total, start_time):
        """Update metrics labels in Tkinter thread loop with comprehensive live status."""
        elapsed = time.time() - start_time
        records = main.stats["schools_found"]
        pages = main.stats["pages"]
        speed = round(records / (elapsed / 60.0), 1) if elapsed > 0 else 0.0
        
        # Format elapsed time
        if elapsed < 60:
            self.elapsed_time_str = f"{round(elapsed)}s"
        else:
            self.elapsed_time_str = f"{int(elapsed//60)}m {int(elapsed%60)}s"

        # ETA calculation
        completed = min(index + 1, total)
        remaining_dists = total - completed
        if completed > 0 and elapsed > 0:
            avg_time_per_dist = elapsed / completed
            est_remaining_sec = avg_time_per_dist * remaining_dists
            if est_remaining_sec < 60:
                self.eta_str = f"{round(est_remaining_sec)}s"
            else:
                self.eta_str = f"{int(est_remaining_sec//60)}m {int(est_remaining_sec%60)}s"
        else:
            self.eta_str = "Estimating..."

        # Progress percentage
        progress_val = completed / total if total > 0 else 0.0
        progress_pct = round(progress_val * 100, 1)

        # State name display
        state_display = self.selected_state_slug.replace("-", " ").title() if self.selected_state_slug else "N/A"

        # Update Dashboard metrics
        self.dash_stat_schools.configure(text=str(records))
        self.dash_stat_pages.configure(text=str(pages))
        self.dash_stat_errors.configure(text=str(main.stats["errors"]))
        self.dash_stat_time.configure(text=self.elapsed_time_str)
        self.dash_stat_duplicates.configure(text=str(main.stats["duplicates"]))
        self.dash_stat_wrong_state.configure(text=str(main.stats["wrong_state"]))

        # Update Status bar with comprehensive metrics
        self.status_stats_lbl.configure(
            text=f"Schools: {records} | Pages: {pages} | {speed} RPM | {progress_pct}% | ETA: {self.eta_str}"
        )
        
        # Scraper View: Rich two-line progress label
        self.progress_bar.set(progress_val)
        
        line1 = f"State: {state_display}  |  District: {dist_name} [{completed}/{total}]  |  Page: {self.current_scrape_page}"
        line2 = f"Schools: {records}  |  {speed} RPM  |  Elapsed: {self.elapsed_time_str}  |  ETA: {self.eta_str}  |  {progress_pct}%"
        self.progress_lbl.configure(text=f"{line1}\n{line2}")

    def scraper_finished_callback(self):
        """Thread cleanups and control widgets toggle."""
        self._set_controls_state("idle")
        self.update_start_button_state()
        
        status_lbl = "Completed." if not self.stop_requested else "Stopped"
        color_lbl = "🟢" if not self.stop_requested else "🔴"
        self.set_status(status_lbl, color_lbl)
        
        records = len(self.scraped_data_list)
        self.progress_bar.set(1.0)
        self.progress_lbl.configure(text=f"Status: {status_lbl} | Total Scraped: {records} | Process Finished.")
        
        # Update Dashboard and Status Bar metrics
        self.dash_stat_schools.configure(text=str(records))
        self.dash_stat_rows_exported.configure(text=str(records))
        self.status_stats_lbl.configure(text=f"Schools: {records} | Pages: {main.stats['pages']} | ETA: None")
        
        self.log_activity(f"Scrape job finished. Extracted {records} entries.")
        self.update_project_displays()

        if not self.stop_requested and records > 0:
            prompt = messagebox.askyesno(
                "Export Completed",
                f"🎉 Scraping and Export completed successfully!\n\nTotal school records scraped: {records}\nSaved to: {config.OUTPUT_FOLDER}\n\nWould you like to open the output folder now?"
            )
            if prompt:
                self.open_output_folder()

    # ----------------------------
    # CONTROLS TRIGGER API
    # ----------------------------
    def pause_scraping(self):
        self.pause_event.clear()
        self.is_paused = True
        self._set_controls_state("paused")
        self.set_status("Pausing...", "\ud83d\udfe1")
        self.log_activity("Scraper execution paused.")

    def resume_scraping(self):
        self.pause_event.set()
        self.is_paused = False
        self._set_controls_state("running")
        self.set_status("Scraping...", "\ud83d\udfe1")
        self.log_activity("Scraper execution resumed.")

    def stop_scraping(self):
        self.stop_requested = True
        self.pause_event.set()  # Unblock thread if paused so it can check stop_requested
        self._set_controls_state("stopping")
        self.set_status("Stopping...", "\ud83d\udfe1")
        self.log_activity("Scraper execution terminated.")

    # ----------------------------
    # EXCEL EXPORT WRITER
    # ----------------------------
    def export_report_files(self, selected_fields):
        """Export scraped records using pandas and openpyxl formatting."""
        out_dir = config.OUTPUT_FOLDER
        os.makedirs(out_dir, exist_ok=True)
        
        # Build clean smart filenames
        selected_dists = [cb.cget("text") for cb in self.district_checkboxes if cb.get()]
        total_available = len(self.district_checkboxes)
        filename_base = main.generate_export_filename(
            self.selected_state_slug,
            selected_dists,
            total_available_count=total_available
        )
        excel_path = os.path.join(out_dir, f"{filename_base}.xlsx")
        csv_path = os.path.join(out_dir, f"{filename_base}.csv")
        
        # Map list of school rows to selected fields
        mapped_records = []
        for r in self.scraped_data_list:
            row = {}
            address = r.get("Address", "") or ""
            
            # Extract PIN Code
            pin_match = re.search(r"\b\d{6}\b", address)
            pin_code = pin_match.group(0) if pin_match else ""
            
            # Clean address for city/village parsing
            clean_address = address
            if pin_code:
                clean_address = clean_address.replace(pin_code, "").replace(" - ", "").replace("-", "")
            
            addr_parts = [p.strip() for p in clean_address.split(",") if p.strip()]
            city = addr_parts[-1] if len(addr_parts) >= 1 else ""
            village = addr_parts[-2] if len(addr_parts) >= 2 else ""
            
            for field in selected_fields:
                if field == "PIN Code":
                    row[field] = pin_code
                elif field == "City":
                    row[field] = city
                elif field == "Village":
                    row[field] = village
                else:
                    db_col = FIELD_MAP.get(field, field)
                    row[field] = r.get(db_col, "") or ""
            mapped_records.append(row)
            
        df = pd.DataFrame(mapped_records)
        
        # Write CSV if requested
        if config.EXPORT == ["csv"] or "csv" in config.EXPORT:
            df.to_csv(csv_path, index=False, encoding="utf-8")
            self.log_queue.put(f"[SYSTEM] [SUCCESS] CSV Saved : {csv_path}")
            self.last_export_path = csv_path
            
        # Write Excel if requested
        if "xlsx" in config.EXPORT:
            wb = Workbook()
            
            # --- Sheet 1: Summary Sheet ---
            ws_summary = wb.active
            ws_summary.title = "Summary"
            ws_summary.views.sheetView[0].showGridLines = True
            
            # Styles
            title_font = Font(name="Calibri", size=16, bold=True, color="FFFFFF")
            title_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
            bold_font = Font(name="Calibri", size=11, bold=True)
            regular_font = Font(name="Calibri", size=11)
            header_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
            thin_border = Border(
                left=Side(style='thin', color='D9D9D9'),
                right=Side(style='thin', color='D9D9D9'),
                top=Side(style='thin', color='D9D9D9'),
                bottom=Side(style='thin', color='D9D9D9')
            )
            
            # Write Title Banner
            ws_summary.merge_cells("A1:C1")
            title_cell = ws_summary["A1"]
            title_cell.value = "SchoolMiner Scraper Execution Summary"
            title_cell.font = title_font
            title_cell.fill = title_fill
            title_cell.alignment = Alignment(horizontal="center", vertical="center")
            ws_summary.row_dimensions[1].height = 40
            
            # Summary Details
            summary_info = [
                ("Execution Metric", "Value", "Description"),
                ("Export Timestamp", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Local date and time of file generation"),
                ("Target Board", self.selected_board.upper(), "Scope of educational board directory"),
                ("Target State", self.selected_state_slug.title(), "Scope of state geographical filter"),
                ("Target Districts", ", ".join(config.DISTRICTS), "Scraped districts"),
                ("Total Records Exported", len(self.scraped_data_list), "Count of unique school directories"),
                ("Errors Count", main.stats["errors"], "Resolved scraper execution warning counts"),
                ("Software Version", "v6.0-Enterprise", "Application version code")
            ]
            
            for r_idx, (m, v, d) in enumerate(summary_info, start=3):
                ws_summary.cell(row=r_idx, column=1, value=m)
                ws_summary.cell(row=r_idx, column=2, value=v)
                ws_summary.cell(row=r_idx, column=3, value=d)
                
                # Styles
                c1 = ws_summary.cell(row=r_idx, column=1)
                c2 = ws_summary.cell(row=r_idx, column=2)
                c3 = ws_summary.cell(row=r_idx, column=3)
                
                c1.border = thin_border
                c2.border = thin_border
                c3.border = thin_border
                
                if r_idx == 3:
                    c1.font = bold_font
                    c2.font = bold_font
                    c3.font = bold_font
                    c1.fill = header_fill
                    c2.fill = header_fill
                    c3.fill = header_fill
                else:
                    c1.font = bold_font
                    c2.font = regular_font
                    c3.font = regular_font
                    
            ws_summary.column_dimensions["A"].width = 25
            ws_summary.column_dimensions["B"].width = 30
            ws_summary.column_dimensions["C"].width = 40
            
            # --- Sheet 2: Data Sheet ---
            ws_data = wb.create_sheet(title="Schools Data")
            ws_data.views.sheetView[0].showGridLines = True
            
            headers = df.columns.tolist()
            ws_data.append(headers)
            
            header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
            data_header_fill = PatternFill(start_color="2D3748", end_color="2D3748", fill_type="solid")
            
            for col_idx, h in enumerate(headers, start=1):
                cell = ws_data.cell(row=1, column=col_idx)
                cell.font = header_font
                cell.fill = data_header_fill
                cell.alignment = Alignment(horizontal="left", vertical="center")
                
            ws_data.row_dimensions[1].height = 28
            
            # Write rows
            for row_idx, row_data in enumerate(mapped_records, start=2):
                ws_data.append([row_data[h] for h in headers])
                ws_data.row_dimensions[row_idx].height = 20
                for c_idx in range(1, len(headers) + 1):
                    cell = ws_data.cell(row=row_idx, column=c_idx)
                    cell.font = regular_font
                    cell.border = thin_border
                    if headers[c_idx-1] in ("PIN Code", "Phone", "Mobile", "Established Year", "UDISE", "Affiliation Number"):
                        cell.alignment = Alignment(horizontal="center")
                        
            # Auto width
            for col in ws_data.columns:
                max_len = 0
                col_letter = get_column_letter(col[0].column)
                for cell in col:
                    if cell.value:
                        max_len = max(max_len, len(str(cell.value)))
                ws_data.column_dimensions[col_letter].width = max(max_len + 3, 12)
                
            # Filters and Freeze row 1
            max_col_letter = get_column_letter(len(headers))
            ws_data.auto_filter.ref = f"A1:{max_col_letter}{len(mapped_records) + 1}"
            ws_data.freeze_panes = "A2"
            
            wb.save(excel_path)
            self.log_queue.put(f"[SYSTEM] [SUCCESS] Excel Saved : {excel_path}")
            self.last_export_path = excel_path
            
        self.log_activity("Exported parsed records to Output folder.")

    # ----------------------------
    # UTILITIES
    # ----------------------------
    def check_log_queue(self):
        """Poll log messages queue and write them to the CTkTextbox views."""
        while not self.log_queue.empty():
            try:
                msg = self.log_queue.get_nowait()
                
                # Parse timestamp and logger level thread-safely
                level = "INFO"
                text = msg
                match = re.match(r"^\[(\d{2}:\d{2}:\d{2})\]\s+\[(\w+)\]\s+(.*)$", msg)
                if match:
                    timestamp = match.group(1)
                    level = match.group(2)
                    text = match.group(3)
                else:
                    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
                    if "[ERROR]" in msg:
                        level = "ERROR"
                    elif "[WARNING]" in msg:
                        level = "WARNING"
                    elif "[SUCCESS]" in msg:
                        level = "SUCCESS"
                    text = msg
                    
                log_entry = {
                    "timestamp": timestamp,
                    "level": level,
                    "text": text,
                    "raw": f"[{timestamp}] [{level.upper()}] {text.replace('[SYSTEM]', '').replace('[SUCCESS]', '').replace('[ERROR]', '').replace('[WARNING]', '').strip()}"
                }
                
                self.all_log_messages.append(log_entry)
                
                # Render to active textboxes if matching search filter
                if self.matches_log_filter(log_entry):
                    self.append_log(log_entry["raw"])
            except queue.Empty:
                break
        self.after(100, self.check_log_queue)

    def _get_log_tag_color(self, text):
        """Returns a tag name and color for color-coded log output."""
        if "[ERROR]" in text:
            return "error", "#ef4444"
        elif "[WARNING]" in text:
            return "warning", "#f59e0b"
        elif "[SUCCESS]" in text:
            return "success", "#10b981"
        else:
            return "info", "#94a3b8"

    def append_log(self, text):
        tag_name, tag_color = self._get_log_tag_color(text)
        
        if hasattr(self, "logs_textbox"):
            self.logs_textbox.configure(state="normal")
            self.logs_textbox.tag_config(tag_name, foreground=tag_color)
            self.logs_textbox.insert(tk.END, text + "\n", tag_name)
            self.logs_textbox.see(tk.END)
            self.logs_textbox.configure(state="disabled")

        if hasattr(self, "mini_logs_box"):
            self.mini_logs_box.configure(state="normal")
            self.mini_logs_box.tag_config(tag_name, foreground=tag_color)
            self.mini_logs_box.insert(tk.END, text + "\n", tag_name)
            self.mini_logs_box.see(tk.END)
            self.mini_logs_box.configure(state="disabled")

    def log_activity(self, text):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        activity_str = f"[{timestamp}] {text}"
        self.recent_activities.insert(0, activity_str)
        self.recent_activities = self.recent_activities[:8] # Keep last 8 items
        
        date_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        history_entry = f"[{date_str}] {text}"
        if history_entry not in self.workspace_history:
            self.workspace_history.insert(0, history_entry)
            self.workspace_history = self.workspace_history[:20] # Limit history list to 20
            
        # Trigger auto save project updates
        if self.current_project_file:
            self.auto_save_project()
            
        self.update_activity_displays()
        self.update_workspace_history_display()

    def export_logs_to_file(self):
        content = "\n".join([entry["raw"] for entry in self.all_log_messages if self.matches_log_filter(entry)])
        if not content:
            return
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
            initialfile="schoolminer_execution_log.txt"
        )
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                self.log_queue.put(f"[SYSTEM] [SUCCESS] Exported log console file to: {file_path}")
            except Exception as e:
                self.log_queue.put(f"[SYSTEM] [ERROR] Failed to save log file: {e}")

    def change_appearance_mode(self, new_appearance_mode: str):
        customtkinter.set_appearance_mode(new_appearance_mode)

    def change_scaling(self, new_scaling: str):
        new_scaling_float = int(new_scaling.replace("%", "")) / 100
        customtkinter.set_widget_scaling(new_scaling_float)

    # ----------------------------
    # WORKSPACE PERSISTENCE LOADS
    # ----------------------------
    def load_recent_projects(self):
        if os.path.exists(self.recent_projects_file):
            try:
                with open(self.recent_projects_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def save_recent_projects(self, recent_list):
        try:
            with open(self.recent_projects_file, "w", encoding="utf-8") as f:
                json.dump(recent_list, f, indent=4)
        except Exception:
            pass

    def add_recent_project(self, file_path):
        recent = self.load_recent_projects()
        if file_path in recent:
            recent.remove(file_path)
        recent.insert(0, file_path)
        recent = recent[:5]
        self.save_recent_projects(recent)
        self.recent_projects = recent
        self.update_recent_projects_listbox()

    def update_recent_projects_listbox(self):
        for widget in self.recents_scroll.winfo_children():
            widget.destroy()

        if not self.recent_projects:
            lbl = customtkinter.CTkLabel(self.recents_scroll, text="No recent workspace projects loaded.", font=customtkinter.CTkFont(slant="italic"))
            lbl.pack(pady=40)
            return

        for p_path in self.recent_projects:
            if not os.path.exists(p_path):
                continue
            p_name = os.path.splitext(os.path.basename(p_path))[0]
            
            card = customtkinter.CTkFrame(self.recents_scroll, fg_color=("#f1f5f9", "#1e293b"), height=50, corner_radius=8)
            card.pack(fill="x", pady=5, padx=2)
            
            # Text block
            text_frame = customtkinter.CTkFrame(card, fg_color="transparent")
            text_frame.pack(side="left", fill="both", expand=True, padx=15, pady=8)
            
            name_lbl = customtkinter.CTkLabel(text_frame, text=p_name, font=customtkinter.CTkFont(weight="bold"), anchor="w")
            name_lbl.pack(fill="x", anchor="w")
            
            path_lbl = customtkinter.CTkLabel(text_frame, text=p_path, font=customtkinter.CTkFont(size=10), text_color="#64748b", anchor="w")
            path_lbl.pack(fill="x", anchor="w")
            
            # Action button
            btn_load = customtkinter.CTkButton(
                card, 
                text="Load", 
                width=60, 
                height=26,
                command=lambda path=p_path: self.load_project_from_file(path)
            )
            btn_load.pack(side="right", padx=15)

    def load_user_settings(self):
        """Loads optional session preferences from user_settings.json."""
        defaults = {
            "last_board": "cbse",
            "last_state": "",
            "remember_last_selection": False
        }
        if os.path.exists(self.user_settings_file):
            try:
                with open(self.user_settings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for k, v in defaults.items():
                        if k not in data:
                            data[k] = v
                    return data
            except Exception:
                pass
        
        try:
            with open(self.user_settings_file, "w", encoding="utf-8") as f:
                json.dump(defaults, f, indent=4)
        except Exception:
            pass
        return defaults

    def save_user_settings(self):
        """Saves session preferences to user_settings.json."""
        try:
            remember = False
            if hasattr(self, "remember_switch") and self.remember_switch:
                remember = bool(self.remember_switch.get())
            else:
                remember = self.user_settings.get("remember_last_selection", False)
                
            if remember:
                state_name = self.state_combo.get() if hasattr(self, "state_combo") else "Select State..."
                last_state = STATES_MAP.get(state_name, "") if state_name != "Select State..." else ""
                last_board = self.board_menu.get().strip().lower() if hasattr(self, "board_menu") else "cbse"
            else:
                last_state = ""
                last_board = "cbse"
                
            data = {
                "last_board": last_board,
                "last_state": last_state,
                "remember_last_selection": remember
            }
            with open(self.user_settings_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            self.log_queue.put(f"[SYSTEM] [ERROR] Failed to save user settings: {e}")

    def sync_folder_path(self, val):
        self.folder_entry.delete(0, tk.END)
        self.folder_entry.insert(0, val)

    def open_output_folder(self):
        out_dir = self.folder_entry.get().strip()
        if os.path.exists(out_dir):
            try:
                os.startfile(out_dir)
            except Exception as e:
                self.log_queue.put(f"[SYSTEM] [ERROR] Failed to open folder: {e}")
        else:
            self.log_queue.put("[SYSTEM] [WARNING] Output folder does not exist yet.")

    def open_file_path(self, path):
        try:
            os.startfile(path)
            self.log_queue.put(f"[SYSTEM] Opened file: {path}")
        except Exception as e:
            self.log_queue.put(f"[SYSTEM] [ERROR] Failed to open file: {e}")

    def update_export_explorer(self):
        # Sync widget values first
        self.export_format_combo.set(self.format_menu.get())
        self.export_dir_entry.delete(0, tk.END)
        self.export_dir_entry.insert(0, self.folder_entry.get())

        for widget in self.export_rows_frame.winfo_children():
            widget.destroy()

        out_dir = self.folder_entry.get().strip()
        if not os.path.exists(out_dir):
            lbl = customtkinter.CTkLabel(self.export_rows_frame, text="No output files found (directory does not exist).", font=customtkinter.CTkFont(slant="italic"))
            lbl.pack(pady=40)
            return

        files = []
        for f in os.listdir(out_dir):
            if f.endswith((".xlsx", ".csv")):
                path = os.path.join(out_dir, f)
                stat = os.stat(path)
                files.append({
                    "name": f,
                    "path": path,
                    "size": stat.st_size,
                    "mtime": stat.st_mtime
                })

        # Sort by last modified time (newest first)
        files.sort(key=lambda x: x["mtime"], reverse=True)

        if not files:
            lbl = customtkinter.CTkLabel(self.export_rows_frame, text="No spreadsheets found in Output folder.", font=customtkinter.CTkFont(slant="italic"))
            lbl.pack(pady=40)
            return

        # Render rows
        for file_info in files[:15]:
            row = customtkinter.CTkFrame(self.export_rows_frame, fg_color=("#f1f5f9", "#1e293b"), height=48, corner_radius=8)
            row.pack(fill="x", pady=4, padx=2)
            
            # File Icon & Name
            icon_lbl = customtkinter.CTkLabel(row, text="📊" if file_info["name"].endswith(".xlsx") else "📄", font=customtkinter.CTkFont(size=14), width=30)
            icon_lbl.pack(side="left", padx=(10, 5))

            name_lbl = customtkinter.CTkLabel(row, text=file_info["name"], font=customtkinter.CTkFont(weight="bold"), anchor="w")
            name_lbl.pack(side="left", padx=10, fill="x", expand=True)

            # Metadata (Size / Date)
            size_kb = round(file_info["size"] / 1024, 1)
            size_lbl = customtkinter.CTkLabel(row, text=f"{size_kb} KB", font=customtkinter.CTkFont(size=11), text_color="#64748b", width=80, anchor="e")
            size_lbl.pack(side="left", padx=10)

            date_str = datetime.datetime.fromtimestamp(file_info["mtime"]).strftime("%Y-%m-%d %H:%M")
            date_lbl = customtkinter.CTkLabel(row, text=date_str, font=customtkinter.CTkFont(size=11), text_color="#64748b", width=120)
            date_lbl.pack(side="left", padx=10)

            # Open Button
            btn_open = customtkinter.CTkButton(
                row, 
                text="Open File", 
                width=75, 
                height=26,
                command=lambda p=file_info["path"]: self.open_file_path(p)
            )
            btn_open.pack(side="right", padx=10)


    def create_project(self):
        dialog = customtkinter.CTkInputDialog(text="Enter name for new workspace project:", title="Create Project")
        name = dialog.get_input()
        if name:
            name = name.strip()
            if name:
                self.current_project_name = name
                self.current_project_file = None
                self.workspace_history = ["Workspace initialized."]
                self.recent_activities = [f"Workspace '{name}' created."]
                
                self.selected_board = "cbse"
                self.selected_state_slug = ""
                self.board_menu.set("cbse")
                self.state_combo.set("Select State...")
                self.folder_entry.delete(0, tk.END)
                self.folder_entry.insert(0, "Output")
                self.format_menu.set("Excel (xlsx)")
                
                self.clear_all_districts()
                self.load_preset_selection("Default Contact")
                
                self.update_project_displays()
                self.update_workspace_history_display()
                self.update_activity_displays()
                self.log_queue.put(f"[SYSTEM] Created new workspace project: {name}")

    def save_project(self):
        if not self.current_project_file:
            self.save_project_as()
        else:
            self.write_project_to_file(self.current_project_file)

    def save_project_as(self):
        file_path = filedialog.asksaveasfilename(
            defaultextension=".smp",
            filetypes=[("SchoolMiner Project", "*.smp"), ("All Files", "*.*")],
            initialfile=f"{self.current_project_name}.smp"
        )
        if file_path:
            self.current_project_file = file_path
            self.current_project_name = os.path.splitext(os.path.basename(file_path))[0]
            self.write_project_to_file(file_path)
            self.add_recent_project(file_path)
            self.update_project_displays()

    def open_project(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("SchoolMiner Project", "*.smp"), ("All Files", "*.*")]
        )
        if file_path:
            self.load_project_from_file(file_path)

    def write_project_to_file(self, file_path):
        try:
            selected_fields = [f for f, cb in self.field_checkboxes.items() if cb.get()]
            selected_dists = [cb.cget("text") for cb in self.district_checkboxes if cb.get()]
            data = {
                "name": self.current_project_name,
                "board": self.board_menu.get(),
                "state": self.selected_state_slug,
                "districts": selected_dists,
                "available_districts": self.districts_list,
                "fields": selected_fields,
                "output_dir": self.folder_entry.get(),
                "format": self.format_menu.get(),
                "history": self.workspace_history
            }
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            self.log_queue.put(f"[SYSTEM] [SUCCESS] Saved project configuration to: {file_path}")
        except Exception as e:
            self.log_queue.put(f"[SYSTEM] [ERROR] Failed to save project: {e}")

    def load_project_from_file(self, file_path):
        if not os.path.exists(file_path):
            self.log_queue.put(f"[SYSTEM] [ERROR] Project file not found: {file_path}")
            return
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            self.current_project_file = file_path
            self.current_project_name = os.path.splitext(os.path.basename(file_path))[0]
            
            board = data.get("board", "cbse")
            state = data.get("state", "himachal-pradesh")
            districts = data.get("districts", [])
            fields = data.get("fields", [])
            output_dir = data.get("output_dir", "Output")
            fmt = data.get("format", "Excel (xlsx)")
            self.workspace_history = data.get("history", ["Workspace loaded."])
            
            self.selected_board = board
            self.selected_state_slug = state
            self.board_menu.set(board)
            
            # Resolve State human readable selection
            clean_name = state
            for k, v in STATES_MAP.items():
                if v == state:
                    clean_name = k
                    break
            self.state_combo.set(clean_name)
            
            self.folder_entry.delete(0, tk.END)
            self.folder_entry.insert(0, output_dir)
            self.format_menu.set(fmt)
            
            available = data.get("available_districts", [])
            if available:
                self.districts_list = available
                self.update_districts_checklist([d["name"] for d in available])
                for cb in self.district_checkboxes:
                    name = cb.cget("text")
                    if name in districts:
                        cb.select()
                    else:
                        cb.deselect()
            else:
                for cb in self.district_checkboxes:
                    cb.destroy()
                self.district_checkboxes.clear()
                self.districts_list.clear()

            self.clear_all_fields()
            for f in fields:
                if f in self.field_checkboxes:
                    self.field_checkboxes[f].select()
                    
            self.add_recent_project(file_path)
            self.update_project_displays()
            self.update_workspace_history_display()
            
            self.log_activity("Workspace loaded.")
            self.log_queue.put(f"[SYSTEM] [SUCCESS] Loaded workspace: {self.current_project_name}")
            self.show_page("Scraper")
        except Exception as e:
            self.log_queue.put(f"[SYSTEM] [ERROR] Failed to load project: {e}")

    def auto_save_project(self):
        if self.current_project_file:
            try:
                selected_fields = [f for f, cb in self.field_checkboxes.items() if cb.get()]
                selected_dists = [cb.cget("text") for cb in self.district_checkboxes if cb.get()]
                data = {
                    "name": self.current_project_name,
                    "board": self.board_menu.get(),
                    "state": self.selected_state_slug,
                    "districts": selected_dists,
                    "available_districts": self.districts_list,
                    "fields": selected_fields,
                    "output_dir": self.folder_entry.get(),
                    "format": self.format_menu.get(),
                    "history": self.workspace_history
                }
                with open(self.current_project_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4)
            except Exception:
                pass

if __name__ == "__main__":
    app = SchoolMinerGUI()
    app.mainloop()
