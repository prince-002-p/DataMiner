# ===========================================
# SchoolMiner Enterprise v6.5 - SchoolsIndia Parser
# ===========================================

import re
from selenium.webdriver.common.by import By
from parsers.base_parser import BaseParser
from selectors import smart_find_elements, smart_find_element

class SchoolsIndiaParser(BaseParser):
    def __init__(self, logger=None):
        self.logger = logger

    def log(self, msg):
        if self.logger:
            self.logger(msg)
        else:
            print(msg)

    def parse_districts(self, driver):
        """
        Extracts district dicts (name, url) from loaded state page using smart selector fallback.
        """
        links = smart_find_elements(driver, "district_items", site="schoolsindia", logger=self.logger)
        if not links:
            # Fallback to tag name 'a' check if filter-item class changed completely
            self.log("[PARSER DEBUG] Primary/Fallback district selectors returned 0 links. Scanning all <a> tags...")
            all_a = driver.find_elements(By.TAG_NAME, "a")
            links = [a for a in all_a if "-schools-in-" in (a.get_attribute("href") or "")]

        districts = []
        parsing_errors = []

        for idx, link in enumerate(links):
            try:
                name = link.get_attribute("textContent").strip()
                url = link.get_attribute("href")
                if name and url:
                    districts.append({"name": name, "url": url})
                else:
                    parsing_errors.append(f"Link index {idx}: Name or URL was empty.")
            except Exception as e:
                parsing_errors.append(f"Link index {idx} parse exception: {e}")

        if not districts and parsing_errors:
            self.log(f"[PARSER ERROR] Parsing failures: {'; '.join(parsing_errors[:5])}")

        return districts

    def parse_school_cards(self, driver):
        """
        Extracts school details from the current district page.
        Uses smart fallbacks for school titles and parent card containers.
        """
        titles = smart_find_elements(driver, "school_title", site="schoolsindia", logger=self.logger)
        school_list = []

        for title_elem in titles:
            try:
                # Resolve parent container element using XPath relative selector fallback
                parent = None
                try:
                    parent = title_elem.find_element(By.XPATH, "./ancestor::article[contains(@class,'entry')]")
                except Exception:
                    try:
                        parent = title_elem.find_element(By.XPATH, "./ancestor::div[contains(@class,'entry')]")
                    except Exception:
                        try:
                            parent = title_elem.find_element(By.XPATH, "..")
                        except Exception:
                            parent = None

                school_name = title_elem.text.strip()
                if not school_name and parent:
                    school_name = parent.text.split("\n")[0].strip()

                row = {
                    "School Name": school_name,
                    "Address": "",
                    "District": "",
                    "State": "",
                    "Landline": "",
                    "Mobile": "",
                    "Email": "",
                    "Website": "",
                }

                if parent:
                    text_lines = parent.text.split("\n")
                    for i in range(len(text_lines) - 1):
                        label = text_lines[i].strip()
                        val = text_lines[i + 1].strip()

                        if label == "Address":
                            row["Address"] = val
                        elif label == "District":
                            row["District"] = val
                        elif label == "State":
                            row["State"] = val
                        elif label == "Phone":
                            phone_text = val
                            if i + 2 < len(text_lines):
                                next_line = text_lines[i + 2].strip()
                                clean_next = re.sub(r"[\s,\-]", "", next_line)
                                if clean_next.isdigit():
                                    phone_text += "," + next_line
                            landline, mobile = self.split_phone_numbers(phone_text)
                            row["Landline"] = landline
                            row["Mobile"] = mobile
                        elif label == "Email":
                            row["Email"] = val
                        elif label == "Website":
                            row["Website"] = val

                school_list.append(row)
            except Exception as e:
                self.log(f"[PARSER WARNING] Exception extracting school card: {e}")

        return school_list

    def split_phone_numbers(self, phone_text):
        """
        Parses landline and mobile numbers from raw string.
        """
        if not phone_text:
            return "", ""

        landline = []
        mobile = []

        phone_text = phone_text.replace("\n", ",")
        numbers = phone_text.split(",")

        for num in numbers:
            num = num.strip()
            digits = "".join(ch for ch in num if ch.isdigit())

            if len(digits) == 10:
                mobile.append(num)
            elif digits:
                landline.append(num)

        return ", ".join(landline), ", ".join(mobile)
