# ===========================================
# SchoolMiner Enterprise v6.5 - Startup Health Check
# ===========================================

import sys
from adapters.schoolsindia_adapter import SchoolsIndiaAdapter

class HealthCheckService:
    def __init__(self, driver_provider, logger=None):
        self.driver_provider = driver_provider
        self.logger = logger

    def log(self, msg):
        if self.logger:
            self.logger(msg)
        else:
            print(msg)

    def run_startup_check(self, test_state_slug="himachal-pradesh", board="cbse"):
        """
        Executes startup compatibility check against target website.
        """
        self.log("[HEALTH CHECK] Checking SchoolsIndia website reachability & parser compatibility...")
        driver = None
        try:
            driver = self.driver_provider()
            adapter = SchoolsIndiaAdapter(logger=self.logger)
            is_ok, message = adapter.check_health(driver, test_state_slug=test_state_slug, board=board)

            if is_ok:
                self.log(f"[HEALTH CHECK] SUCCESS: {message}")
                return True, message
            else:
                diag = (
                    f"⚠️ Website Health Check Failed!\n"
                    f"Message: {message}\n"
                    f"Diagnostics: Website structure has changed. Parser update required."
                )
                self.log(f"[HEALTH CHECK] FAILURE: {diag}")
                return False, diag
        except Exception as e:
            err_msg = f"Website structure has changed or network offline. Parser update required. Details: {e}"
            self.log(f"[HEALTH CHECK] EXCEPTION: {err_msg}")
            return False, err_msg
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

def verify_site_compatibility(driver_provider, logger=None):
    """Utility helper running health check."""
    service = HealthCheckService(driver_provider, logger=logger)
    return service.run_startup_check()
