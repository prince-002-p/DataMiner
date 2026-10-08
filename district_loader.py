# ===========================================
# SchoolMiner Enterprise v6.5 - District Loader Service
# ===========================================

import time
import threading
from adapters.schoolsindia_adapter import SchoolsIndiaAdapter
import config

class DistrictLoader:
    _cache = {}  # Class-level cache: (board, state_slug) -> [district_dicts]

    def __init__(self, driver_provider, logger=None):
        self.driver_provider = driver_provider
        self.logger = logger
        self.adapter = SchoolsIndiaAdapter(logger=logger)

    def log(self, msg):
        if self.logger:
            self.logger(msg)
        else:
            print(msg)

    def load_districts(self, board, state_obj, force_refresh=False):
        """
        Loads district data for state with caching, retry, and diagnostics.
        """
        state_slug = state_obj.get("slug") if isinstance(state_obj, dict) else str(state_obj)
        display_name = state_obj.get("display_name") if isinstance(state_obj, dict) else state_slug
        cache_key = (board.lower(), state_slug.lower())

        if not force_refresh and cache_key in self._cache:
            cached_data = self._cache[cache_key]
            self.log(f"[DISTRICT LOADER] Cache hit: {len(cached_data)} districts loaded for {display_name}.")
            return cached_data

        max_retries = getattr(config, 'RETRY', 3)
        last_error = None
        driver = None

        for attempt in range(1, max_retries + 1):
            try:
                self.log(f"[DISTRICT LOADER] Loading districts for '{display_name}' (Attempt {attempt}/{max_retries})...")
                if not driver:
                    driver = self.driver_provider()

                districts = self.adapter.load_districts(driver, board, state_slug, display_name=display_name)
                if districts:
                    self._cache[cache_key] = districts
                    self.log(f"[DISTRICT LOADER SUCCESS] Successfully loaded {len(districts)} districts.")
                    return districts
                else:
                    raise Exception("Adapter returned empty district list.")
            except Exception as e:
                last_error = e
                self.log(f"[DISTRICT LOADER WARNING] Attempt {attempt} failed: {e}")
                if driver:
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    driver = None
                if attempt < max_retries:
                    time.sleep(2)

        if driver:
            try:
                driver.quit()
            except Exception:
                pass

        diag_msg = (
            f"Failed to load districts for state '{display_name}' (slug: '{state_slug}') "
            f"after {max_retries} attempts. Last error: {last_error}"
        )
        self.log(f"[DISTRICT LOADER ERROR] {diag_msg}")
        raise RuntimeError(diag_msg)

    @classmethod
    def clear_cache(cls):
        """Clears district cache memory."""
        cls._cache.clear()

    @staticmethod
    def filter_districts(district_list, search_term=""):
        """Utility method to search/filter district list by term."""
        if not search_term:
            return district_list
        term = search_term.strip().lower()
        return [d for d in district_list if term in d["name"].lower()]
