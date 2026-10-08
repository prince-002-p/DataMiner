# ===========================================
# SchoolMiner Enterprise v6.5 - Base Adapter Interface
# ===========================================

from abc import ABC, abstractmethod

class BaseAdapter(ABC):

    @abstractmethod
    def build_state_url(self, board, state_slug):
        """Constructs target URL for a state."""
        pass

    @abstractmethod
    def build_district_url(self, base_url, page):
        """Constructs pagination URL for a district."""
        pass

    @abstractmethod
    def load_districts(self, driver, board, state_slug, display_name=None):
        """Loads and parses district list for a state."""
        pass

    @abstractmethod
    def check_health(self, driver, test_state_slug="himachal-pradesh", board="cbse"):
        """Performs site compatibility and parser health check."""
        pass
