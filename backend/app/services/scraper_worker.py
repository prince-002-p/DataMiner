import datetime
import os
import re
import json
import time
import threading
import logging
from typing import List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

from ..database import SessionLocal
from ..models import Job, SchoolRecord, AuditLog
from .export_service import generate_export_files

# Configure standard logger
logger = logging.getLogger("schoolminer.scraper")

# Control dicts for job execution threads
PAUSE_EVENTS: Dict[int, threading.Event] = {}
STOP_FLAGS: Dict[int, bool] = {}
THREADS: Dict[int, threading.Thread] = {}

def write_audit_log(level: str, message: str, job_id: int = None):
    """Write log to stdout, python logger, and SQLite audit_logs table."""
    timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] Job {job_id}: {message}")
    
    # Write to standard logger
    if level == "INFO":
        logger.info(message)
    elif level == "SUCCESS":
        logger.info(f"SUCCESS: {message}")
    elif level == "WARNING":
        logger.warning(message)
    elif level in ("ERROR", "FAILED"):
        logger.error(message)
    elif level == "DEBUG":
        logger.debug(message)

    # Write to database
    db = SessionLocal()
    try:
        log_entry = AuditLog(
            level=level,
            message=message,
            job_id=job_id
        )
        db.add(log_entry)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to save log to DB: {e}")
    finally:
        db.close()

def split_phone(phone_text: str) -> Tuple[str, str]:
    """Split contact numbers into landline and mobile numbers."""
    if not phone_text:
        return "", ""
    phone_text = phone_text.replace("\n", ",").replace("\r", ",")
    numbers = [n.strip() for n in phone_text.split(",") if n.strip()]
    
    landline = []
    mobile = []
    
    for num in numbers:
        digits = "".join(ch for ch in num if ch.isdigit())
        # Standard Indian mobile number is 10 digits
        if len(digits) == 10 or (len(digits) == 12 and digits.startswith("91")):
            mobile.append(num)
        elif digits:
            landline.append(num)
            
    return ", ".join(landline), ", ".join(mobile)

def parse_address_components(address: str) -> Tuple[str, str, str]:
    """Extract PIN Code, City, and Village from address string using heuristics."""
    if not address:
        return "", "", ""
        
    # Extract 6-digit PIN code
    pin_match = re.search(r"\b\d{6}\b", address)
    pin_code = pin_match.group(0) if pin_match else ""
    
    # Clean the pin part from address for city/village parsing
    clean_address = address
    if pin_code:
        clean_address = clean_address.replace(pin_code, "").replace(" - ", "").replace("-", "")
        
    parts = [p.strip() for p in clean_address.split(",") if p.strip()]
    
    # Heuristics for City and Village
    city = ""
    village = ""
    
    if len(parts) >= 1:
        # Last element before pin is usually city or district town
        city = parts[-1]
    if len(parts) >= 2:
        # Element before city is usually village or area
        village = parts[-2]
        
    return pin_code, city, village

def get_districts_list(board: str, state: str) -> List[Dict[str, str]]:
    """Fetch the list of districts for a given board and state from schoolsindia.net."""
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )
    districts = []
    try:
        url = f"https://www.schoolsindia.net/{board}-schools-in-{state}/state"
        driver.get(url)
        # Wait up to 10 seconds for district filter items to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".filter-item a"))
        )
        links = driver.find_elements(By.CSS_SELECTOR, ".filter-item a")
        for link in links:
            name = link.text.strip()
            url = link.get_attribute("href")
            if name:
                districts.append({"name": name, "url": url})
    except Exception as e:
        logger.error(f"Error loading districts: {e}")
    finally:
        driver.quit()
    return districts

def scrape_worker_thread(job_id: int):
    """Background worker that runs the Selenium web scraper for a job."""
    db = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        db.close()
        return
        
    write_audit_log("INFO", f"Job {job_id} worker started. Preparing chrome browser...", job_id)
    
    # Initialize control events if missing
    if job_id not in PAUSE_EVENTS:
        PAUSE_EVENTS[job_id] = threading.Event()
        PAUSE_EVENTS[job_id].set()  # Initialized as unset = paused, set = running
    if job_id not in STOP_FLAGS:
        STOP_FLAGS[job_id] = False
        
    job.status = "RUNNING"
    job.started_at = datetime.datetime.utcnow()
    db.commit()
    
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )
    driver.implicitly_wait(5)
    
    try:
        # Load districts list from web
        districts_web = get_districts_list(job.board, job.state)
        if not districts_web:
            raise Exception("No districts could be retrieved from the site.")
            
        # Parse selected districts from job settings
        selected_district_names = [d.strip().lower() for d in job.districts.split(",") if d.strip()]
        
        # Filter districts to scrape
        target_districts = []
        if not selected_district_names or "all districts" in selected_district_names:
            target_districts = districts_web
            write_audit_log("INFO", "Scraping all districts in the state.", job_id)
        else:
            for d in districts_web:
                if d["name"].lower() in selected_district_names:
                    target_districts.append(d)
            write_audit_log("INFO", f"Scraping selected districts: {', '.join([d['name'] for d in target_districts])}", job_id)
            
        if not target_districts:
            raise Exception("No matching districts found to scrape.")
            
        total_districts = len(target_districts)
        
        # Check checkpoints (if resuming a job)
        start_dist_idx = 0
        start_page = 1
        if job.current_district:
            for idx, d in enumerate(target_districts):
                if d["name"].lower() == job.current_district.lower():
                    start_dist_idx = idx
                    start_page = job.current_page
                    write_audit_log("INFO", f"Resuming from Checkpoint: District {d['name']}, Page {start_page}", job_id)
                    break
                    
        # Load seen schools to avoid duplicates
        seen_schools = set()
        existing_records = db.query(SchoolRecord).filter(SchoolRecord.job_id == job_id).all()
        for r in existing_records:
            seen_schools.add((r.school_name.lower(), r.address.lower() if r.address else ""))
            
        total_records_scraped = len(existing_records)
        errors_count = job.errors_count
        start_time = time.time()
        
        for dist_idx in range(start_dist_idx, total_districts):
            current_dist = target_districts[dist_idx]
            job.current_district = current_dist["name"]
            db.commit()
            
            write_audit_log("INFO", f"Scraping District [{dist_idx+1}/{total_districts}]: {current_dist['name']}", job_id)
            
            page = start_page if dist_idx == start_dist_idx else 1
            
            while True:
                # 1. Check Stop Flag
                if STOP_FLAGS.get(job_id, False):
                    write_audit_log("WARNING", "Job Stop signal detected.", job_id)
                    job.status = "STOPPED"
                    db.commit()
                    return
                    
                # 2. Check Pause Flag
                if not PAUSE_EVENTS[job_id].is_set():
                    write_audit_log("INFO", "Job paused. Waiting for resume signal...", job_id)
                    job.status = "PAUSED"
                    db.commit()
                    # Block until the event is set
                    PAUSE_EVENTS[job_id].wait()
                    # Check stop flag again immediately after waking up
                    if STOP_FLAGS.get(job_id, False):
                        job.status = "STOPPED"
                        db.commit()
                        return
                    write_audit_log("SUCCESS", "Job resumed.", job_id)
                    job.status = "RUNNING"
                    db.commit()
                    
                # Scrape current page
                job.current_page = page
                db.commit()
                
                url = current_dist["url"] + f"?page={page}"
                write_audit_log("DEBUG", f"Opening Page {page}: {url}", job_id)
                
                try:
                    driver.get(url)
                    time.sleep(2)  # Moderate sleep to let content render
                    
                    # Find article elements
                    articles = driver.find_elements(By.CSS_SELECTOR, "article.entry")
                    if not articles:
                        write_audit_log("INFO", f"No schools found on page {page}. Finishing District {current_dist['name']}.", job_id)
                        break
                        
                    page_records_scraped = 0
                    for article in articles:
                        try:
                            # Parse School Name
                            title_el = article.find_element(By.CLASS_NAME, "entry-title")
                            school_name = title_el.text.strip()
                            if not school_name:
                                continue
                                
                            # Parse info rows dynamically using labels
                            info_rows = article.find_elements(By.CLASS_NAME, "list-row")
                            data = {
                                "Address": "",
                                "District": "",
                                "State": "",
                                "Phone": "",
                                "Email": "",
                                "Website": ""
                            }
                            for row in info_rows:
                                try:
                                    lbl_el = row.find_element(By.CLASS_NAME, "list-label")
                                    val_el = row.find_element(By.CLASS_NAME, "list-value")
                                    lbl = lbl_el.text.strip()
                                    val = val_el.text.strip()
                                    if lbl in data:
                                        data[lbl] = val
                                except Exception:
                                    pass
                                    
                            address = data["Address"]
                            district = data["District"] or current_dist["name"]
                            state = data["State"] or job.state
                            phone_raw = data["Phone"]
                            email = data["Email"]
                            website = data["Website"]
                            
                            # Deduplicate
                            key = (school_name.lower(), address.lower())
                            if key in seen_schools:
                                write_audit_log("DEBUG", f"Skipped Duplicate School: {school_name}", job_id)
                                continue
                                
                            seen_schools.add(key)
                            
                            # Format numbers, zip codes, etc.
                            pin_code, city, village = parse_address_components(address)
                            landline, mobile = split_phone(phone_raw)
                            
                            # Create record object with all 21 fields (others empty)
                            record = SchoolRecord(
                                job_id=job_id,
                                school_name=school_name,
                                address=address,
                                district=district,
                                state=state,
                                pin_code=pin_code,
                                phone=landline,
                                mobile=mobile,
                                email=email,
                                website=website,
                                city=city,
                                village=village,
                                udise="",
                                affiliation_number="",
                                principal="",
                                category="",
                                management="",
                                school_type="",
                                medium="",
                                latitude="",
                                longitude="",
                                established_year=""
                            )
                            db.add(record)
                            total_records_scraped += 1
                            page_records_scraped += 1
                            
                        except Exception as inner_e:
                            errors_count += 1
                            write_audit_log("WARNING", f"Error parsing school entry: {inner_e}", job_id)
                            
                    # Commit page additions
                    db.commit()
                    
                    # Update Job status variables
                    elapsed_mins = (time.time() - start_time) / 60.0
                    speed = round(total_records_scraped / elapsed_mins, 1) if elapsed_mins > 0 else 0.0
                    progress = round(((dist_idx + (1.0 if page_records_scraped == 0 else 0.5)) / total_districts) * 100.0, 1)
                    if progress > 100.0:
                        progress = 99.9
                        
                    job.total_schools_found = total_records_scraped
                    job.progress_percent = progress
                    job.speed_rpm = speed
                    job.errors_count = errors_count
                    db.commit()
                    
                    write_audit_log("INFO", f"Page {page} processed. Scraped {page_records_scraped} schools. Total: {total_records_scraped}", job_id)
                    
                    # If this page returned empty or less than 5 schools and we looped, it might be the end
                    if len(articles) < 5:
                        # Sometimes lists are small, but let's check page source for next link if needed.
                        # Angular pagination on schoolsindia.net usually just displays empty rows on high pages.
                        pass
                        
                    page += 1
                    
                except Exception as page_e:
                    errors_count += 1
                    job.errors_count = errors_count
                    db.commit()
                    write_audit_log("ERROR", f"Page {page} scrape failed: {page_e}", job_id)
                    # Retry page or move to next
                    time.sleep(5)
                    page += 1
                    
            # Completed a district
            start_page = 1  # Reset start page for subsequent districts
            
        # Completed entire job
        write_audit_log("SUCCESS", f"All districts scraped successfully! Total records: {total_records_scraped}", job_id)
        job.status = "COMPLETED"
        job.progress_percent = 100.0
        job.completed_at = datetime.datetime.utcnow()
        db.commit()
        
        # Trigger export generation
        generate_export_files(job_id)
        
    except Exception as e:
        write_audit_log("FAILED", f"Scraper execution crashed: {e}", job_id)
        job.status = "FAILED"
        db.commit()
        
    finally:
        driver.quit()
        # Clean up global maps
        PAUSE_EVENTS.pop(job_id, None)
        STOP_FLAGS.pop(job_id, None)
        THREADS.pop(job_id, None)
        db.close()
        write_audit_log("INFO", "Browser closed and worker thread finished.", job_id)
