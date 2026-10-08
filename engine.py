# ===========================================
# SchoolMiner Enterprise v6.5 - Scraper Engine
# ===========================================

import os
import time
import re
import pandas as pd
from adapters.schoolsindia_adapter import SchoolsIndiaAdapter
import config

class ScraperEngine:
    def __init__(self, driver_provider, logger=None):
        self.driver_provider = driver_provider
        self.logger = logger
        self.adapter = SchoolsIndiaAdapter(logger=logger)
        self.seen_schools = set()
        self.stats = {
            "districts": 0,
            "pages": 0,
            "schools_found": 0,
            "exported": 0,
            "duplicates": 0,
            "wrong_state": 0,
            "errors": 0,
        }

    def log(self, msg):
        if self.logger:
            self.logger(msg)
        else:
            print(msg)

    def reset_stats(self):
        self.seen_schools.clear()
        self.stats = {
            "districts": 0,
            "pages": 0,
            "schools_found": 0,
            "exported": 0,
            "duplicates": 0,
            "wrong_state": 0,
            "errors": 0,
        }

    def scrape_district(self, driver, district, state_slug=None, stop_flag=None, pause_event=None, progress_callback=None):
        """
        Scrapes all pages for a given district. Respects stop/pause thread controls.
        """
        self.log("\n" + "=" * 60)
        self.log(f"📍 District : {district['name']}")
        self.log("=" * 60)

        page = 1
        district_data = []

        while True:
            # Check stop flag
            if stop_flag and stop_flag():
                self.log(f"[STOP] Scraper stop requested during district '{district['name']}' at page {page}.")
                break

            # Check pause event
            if pause_event and not pause_event.is_set():
                self.log(f"[PAUSE] Scraper paused during district '{district['name']}' at page {page}.")
                pause_event.wait()
                if stop_flag and stop_flag():
                    break
                self.log("[RESUME] Scraper resumed.")

            self.stats["pages"] += 1

            try:
                schools = self.adapter.fetch_school_page(driver, district["url"], page=page)
            except Exception as e:
                self.stats["errors"] += 1
                self.log(f"[ENGINE ERROR] Failed fetching page {page} for district '{district['name']}': {e}")
                break

            self.log(f"Schools found on page {page}: {len(schools)}")
            self.stats["schools_found"] += len(schools)

            if progress_callback:
                progress_callback(district["name"], page, len(schools))

            if len(schools) == 0:
                if self.stats["wrong_state"] > 0:
                    self.log(f"⚠ Skipped (Different State): {self.stats['wrong_state']}")
                self.log("[SUCCESS] District Finished")
                break

            strict_state = getattr(config, 'STRICT_STATE', True)
            target_state = state_slug if state_slug else getattr(config, 'STATE', '')

            for row in schools:
                try:
                    if strict_state and target_state:
                        scraped_state = row.get("State", "").strip().lower()
                        expected_state = target_state.replace("-", " ").lower()
                        if scraped_state and scraped_state != expected_state:
                            self.stats["wrong_state"] += 1
                            continue

                    key = (
                        row.get("School Name", "").strip().lower(),
                        row.get("Address", "").strip().lower(),
                        row.get("Email", "").strip().lower(),
                    )

                    if key not in self.seen_schools:
                        self.seen_schools.add(key)
                        district_data.append(row)
                    else:
                        self.stats["duplicates"] += 1
                        self.log(f"⚠ Duplicate Skipped : {row.get('School Name')}")

                except Exception as e:
                    self.stats["errors"] += 1
                    self.log(f"[ENGINE ROW ERROR] {e}")

            page += 1

        return district_data

    def run_job(self, state_slug, selected_districts, selected_fields, stop_flag=None, pause_event=None, progress_callback=None):
        """
        Runs complete scraping job across selected districts.
        """
        self.reset_stats()
        self.stats["districts"] = len(selected_districts)
        start_time = time.time()

        driver = self.driver_provider()
        all_data = []

        try:
            for district in selected_districts:
                if stop_flag and stop_flag():
                    break
                data = self.scrape_district(
                    driver, 
                    district, 
                    state_slug=state_slug, 
                    stop_flag=stop_flag, 
                    pause_event=pause_event, 
                    progress_callback=progress_callback
                )
                all_data.extend(data)
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

        df = pd.DataFrame(all_data)
        if not df.empty:
            existing_cols = [col for col in selected_fields if col in df.columns]
            df = df[existing_cols]

        self.stats["exported"] = len(df)
        elapsed_time = round(time.time() - start_time, 2)

        return df, elapsed_time
