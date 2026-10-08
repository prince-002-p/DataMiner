# ===========================================
# SchoolMiner Enterprise v6.5 - Selector Registry
# ===========================================

from selenium.webdriver.common.by import By

SELECTORS = {
    "schoolsindia": {
        "district_items": {
            "primary": ".filter-item a",
            "fallbacks": [
                ".filter-list a",
                "ul.filter-item a",
                "div.filter-item a",
                "a[href*='-schools-in-']"
            ],
            "by": By.CSS_SELECTOR
        },
        "school_card": {
            "primary": "article.entry",
            "fallbacks": [
                ".entry-title",
                "article[class*='entry']",
                ".school-card",
                "div.entry"
            ],
            "by": By.CSS_SELECTOR
        },
        "school_title": {
            "primary": ".entry-title",
            "fallbacks": [
                "h2.entry-title",
                "h3.entry-title",
                ".entry-title a",
                "header.entry-header h2"
            ],
            "by": By.CSS_SELECTOR
        },
        "school_title_relative": {
            "primary": ".//h2[contains(@class,'entry-title')] | .//h3[contains(@class,'entry-title')] | .//*[contains(@class,'entry-title')]",
            "fallbacks": [
                ".//a[contains(@href,'school')]",
                ".//h2 | .//h3"
            ],
            "by": By.XPATH
        },
        "school_container_relative": {
            "primary": "./ancestor::article[contains(@class,'entry')]",
            "fallbacks": [
                "./ancestor::div[contains(@class,'entry')]",
                "./ancestor::article",
                ".."
            ],
            "by": By.XPATH
        },
        "pagination": {
            "primary": ".pagination",
            "fallbacks": [
                ".page-numbers",
                "ul.pagination",
                "div.pagination"
            ],
            "by": By.CSS_SELECTOR
        },
        "body": {
            "primary": "body",
            "fallbacks": [],
            "by": By.TAG_NAME
        }
    }
}

def smart_find_elements(parent, selector_key, site="schoolsindia", logger=None):
    """
    Attempts to locate elements using primary selector, cascading to fallbacks if empty.
    Returns list of WebElements found or empty list.
    """
    site_selectors = SELECTORS.get(site, {})
    config_entry = site_selectors.get(selector_key)
    
    if not config_entry:
        if logger:
            logger(f"[SELECTORS] Warning: Unknown selector key '{selector_key}' for site '{site}'")
        return []

    by_type = config_entry.get("by", By.CSS_SELECTOR)
    primary = config_entry.get("primary")
    fallbacks = config_entry.get("fallbacks", [])

    candidates = [primary] + fallbacks
    for idx, sel in enumerate(candidates):
        try:
            elements = parent.find_elements(by_type, sel)
            if elements:
                if idx > 0 and logger:
                    logger(f"[SMART FALLBACK] Primary selector '{primary}' missed, but fallback #{idx} '{sel}' matched {len(elements)} items.")
                return elements
        except Exception as e:
            if logger:
                logger(f"[SELECTORS] Query failed for '{sel}': {e}")
                
    if logger:
        logger(f"[SELECTORS ERROR] All selector attempts failed for key '{selector_key}'. Tried: {candidates}")
    return []

def smart_find_element(parent, selector_key, site="schoolsindia", logger=None):
    """
    Finds a single element using primary or fallback selectors.
    Returns WebElement or None.
    """
    elements = smart_find_elements(parent, selector_key, site=site, logger=logger)
    return elements[0] if elements else None
