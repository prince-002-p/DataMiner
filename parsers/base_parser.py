# ===========================================
# SchoolMiner Enterprise v6.5 - Base Parser Interface
# ===========================================

from abc import ABC, abstractmethod

class BaseParser(ABC):

    @abstractmethod
    def parse_districts(self, driver):
        """Extracts district list from loaded state page."""
        pass

    @abstractmethod
    def parse_school_cards(self, driver):
        """Extracts list of school data dictionaries from current page."""
        pass

    @abstractmethod
    def split_phone_numbers(self, phone_text):
        """Separates landline and mobile phone numbers."""
        pass
