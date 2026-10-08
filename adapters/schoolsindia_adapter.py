# ===========================================
# SchoolMiner Enterprise v6.5 - SchoolsIndia Website Adapter
# ===========================================

import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from adapters.base_adapter import BaseAdapter
from parsers.schoolsindia_parser import SchoolsIndiaParser
import config

class SchoolsIndiaAdapter(BaseAdapter):
    BASE_DOMAIN = "https://www.schoolsindia.net"

    def __init__(self, logger=None):
        self.logger = logger
        self.parser = SchoolsIndiaParser(logger=logger)

    def log(self, msg):
        if self.logger:
            self.logger(msg)
        else:
            print(msg)

    def build_state_url(self, board, state_slug):
        """Builds URL for state district overview page."""
        clean_board = str(board).strip().lower()
        clean_slug = str(state_slug).strip().lower()
        return f"{self.BASE_DOMAIN}/{clean_board}-schools-in-{clean_slug}/state"

    def build_district_url(self, base_district_url, page=1):
        """Appends pagination parameter to district base URL."""
        if page <= 1:
            return base_district_url
        if "?" in base_district_url:
            return f"{base_district_url}&page={page}"
        return f"{base_district_url}?page={page}"

    def load_districts(self, driver, board, state_slug, display_name=None):
        """
        Navigates to state URL, verifies page integrity, and parses district list.
        """
        url = self.build_state_url(board, state_slug)
        self.log(f"[ADAPTER] Navigating to State URL: {url}")

        try:
            driver.get(url)
        except Exception as e:
            raise Exception(f"Adapter navigation error for {url}: {e}")

        # Explicit wait for content
        implicit_wait = getattr(config, 'IMPLICIT_WAIT', 10)
        try:
            WebDriverWait(driver, implicit_wait).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".filter-item a, .filter-list a, a[href*='-schools-in-']"))
            )
        except Exception:
            wait_time = getattr(config, 'WAIT', 3)
            time.sleep(wait_time)

        page_title = driver.title or ""
        if "404" in page_title or "not found" in page_title.lower() or "error" in page_title.lower():
            raise Exception(f"HTTP 404 / Error Page encountered at URL: {url}. Title: '{page_title}'")

        body_text = ""
        try:
            body_text = driver.find_element(By.TAG_NAME, "body").text
        except Exception:
            pass

        if "access denied" in body_text.lower():
            raise Exception(f"Access Denied / Anti-bot restriction triggered at URL: {url}")

        districts = self.parser.parse_districts(driver)
        if not districts:
            raise Exception(f"District extraction failed on URL: {url}. No valid district links were extracted by parser.")

        self.log(f"[ADAPTER SUCCESS] Extracted {len(districts)} districts from {state_slug}")
        return districts

    def fetch_school_page(self, driver, district_url, page=1):
        """
        Navigates to a district's page N and extracts school cards.
        """
        page_url = self.build_district_url(district_url, page)
        self.log(f"[ADAPTER] Opening Page {page}: {page_url}")

        driver.get(page_url)

        # Wait for school entries
        wait_timeout = getattr(config, 'IMPLICIT_WAIT', 10)
        try:
            WebDriverWait(driver, wait_timeout).until(
                EC.presence_of_element_located((By.CLASS_NAME, "entry-title"))
            )
        except Exception:
            pass

        return self.parser.parse_school_cards(driver)

    def check_health(self, driver, test_state_slug="himachal-pradesh", board="cbse"):
        """
        Verifies website reachability and parser compatibility.
        """
        test_url = self.build_state_url(board, test_state_slug)
        self.log(f"[HEALTH CHECK] Testing reachability and schema on {test_url}...")

        try:
            driver.get(test_url)
            page_title = driver.title or ""
            if "404" in page_title or "error" in page_title.lower():
                return False, f"Target page error or 404. Title: '{page_title}'"

            districts = self.parser.parse_districts(driver)
            if not districts:
                return False, "Website structure modified. Selector/parser failed to extract district links."

            return True, f"Website reachable, parser compatible ({len(districts)} test districts parsed)."
        except Exception as e:
            return False, f"Health check failed with error: {e}"
