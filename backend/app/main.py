import os
import json
import datetime
import threading
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from .database import engine, Base, get_db
from .models import User, Job, SchoolRecord, AuditLog
from .security import get_password_hash, verify_password, create_access_token, get_current_user
from .schemas import (
    UserCreate, UserResponse, Token, JobCreate, JobResponse,
    AuditLogResponse, SystemStats, PresetSave, PresetResponse
)
from .services.scraper_worker import (
    THREADS, PAUSE_EVENTS, STOP_FLAGS, scrape_worker_thread,
    get_districts_list, write_audit_log
)

# Initialize FastAPI App
app = FastAPI(title="SchoolMiner Enterprise v5.0 API")

# Configure CORS for React local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins for local networking simplicity
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create Database Tables
Base.metadata.create_all(bind=engine)

# Create Default Admin User
db = SessionLocal = engine.raw_connection()
# Initialize default admin if not present
def init_admin():
    db = next(get_db())
    admin_user = db.query(User).filter(User.username == "admin").first()
    if not admin_user:
        hashed = get_password_hash("admin123")
        admin = User(username="admin", hashed_password=hashed, role="admin")
        db.add(admin)
        db.commit()
        print("★ Created default admin account: admin / admin123")
    db.close()

init_admin()

# Memory cache for district lists to optimize loading speeds
DISTRICTS_CACHE = {}

# File path for field presets
PRESETS_FILE = "presets.json"

def load_presets_from_file() -> dict:
    if os.path.exists(PRESETS_FILE):
        try:
            with open(PRESETS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "Default Contact": ["School Name", "Address", "District", "State", "PIN Code", "Phone", "Mobile", "Email", "Website"],
        "All Parameters": ["School Name", "UDISE", "Affiliation Number", "Address", "Village", "City", "District", "State", "PIN Code", "Phone", "Mobile", "Email", "Website", "Principal", "Category", "Management", "School Type", "Medium", "Latitude", "Longitude", "Established Year"]
    }

def save_presets_to_file(presets: dict):
    with open(PRESETS_FILE, "w") as f:
        json.dump(presets, f, indent=4)

# =====================================================================
# AUTH ROUTERS
# =====================================================================

@app.post("/api/auth/register", response_model=UserResponse)
def register_user(user_in: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.username == user_in.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already registered")
        
    hashed = get_password_hash(user_in.password)
    new_user = User(username=user_in.username, hashed_password=hashed, role="user")
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    write_audit_log("SUCCESS", f"Registered new user account: {new_user.username}")
    return new_user

@app.post("/api/auth/login", response_model=Token)
def login_user(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": user.username})
    write_audit_log("SUCCESS", f"User logged in: {user.username}")
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": user.username
    }

@app.get("/api/auth/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user

# =====================================================================
# DATA CONFIG ROUTERS
# =====================================================================

@app.get("/api/data/states")
def get_supported_states(current_user: User = Depends(get_current_user)):
    return [
        {"name": "Himachal Pradesh", "slug": "himachal-pradesh"},
        {"name": "Uttar Pradesh", "slug": "uttar-pradesh"},
        {"name": "Madhya Pradesh", "slug": "madhya-pradesh"},
        {"name": "Punjab", "slug": "punjab"},
        {"name": "Bihar", "slug": "bihar"},
        {"name": "Haryana", "slug": "haryana"}
    ]

@app.get("/api/data/districts")
def get_districts(board: str, state: str, current_user: User = Depends(get_current_user)):
    cache_key = f"{board}_{state}"
    if cache_key in DISTRICTS_CACHE:
        return DISTRICTS_CACHE[cache_key]
        
    districts = get_districts_list(board, state)
    if districts:
        district_names = [d["name"] for d in districts]
        DISTRICTS_CACHE[cache_key] = district_names
        return district_names
    else:
        raise HTTPException(status_code=500, detail="Failed to fetch districts from source site.")

# =====================================================================
# JOB CONTROL ROUTERS
# =====================================================================

@app.post("/api/jobs", response_model=JobResponse)
def create_job(job_in: JobCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Create database entry
    new_job = Job(
        board=job_in.board,
        state=job_in.state,
        districts=",".join(job_in.districts),
        fields=json.dumps(job_in.fields),
        output_format=job_in.output_format,
        output_folder=job_in.output_folder,
        status="PENDING"
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job)
    
    write_audit_log("INFO", f"Scraping Job created. ID: {new_job.id}. Target State: {new_job.state.title()}", new_job.id)
    return new_job

@app.get("/api/jobs", response_model=List[JobResponse])
def get_jobs(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Job).order_by(Job.started_at.desc()).all()

@app.get("/api/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@app.post("/api/jobs/{job_id}/start")
def start_job(job_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    if job.status in ("RUNNING", "PAUSED"):
        return {"message": "Job is already active"}
        
    # Prepare thread control events
    STOP_FLAGS[job_id] = False
    pause_evt = threading.Event()
    pause_evt.set()
    PAUSE_EVENTS[job_id] = pause_evt
    
    # Start thread
    thread = threading.Thread(target=scrape_worker_thread, args=(job_id,))
    THREADS[job_id] = thread
    thread.daemon = True
    thread.start()
    
    write_audit_log("INFO", "Dispatched background thread execution.", job_id)
    return {"message": "Job started in background"}

@app.post("/api/jobs/{job_id}/pause")
def pause_job(job_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    if job.status != "RUNNING":
        raise HTTPException(status_code=400, detail="Only running jobs can be paused")
        
    if job_id in PAUSE_EVENTS:
        PAUSE_EVENTS[job_id].clear()  # Block worker thread
        
    job.status = "PAUSED"
    db.commit()
    write_audit_log("WARNING", "Job execution paused by user.", job_id)
    return {"message": "Job paused"}

@app.post("/api/jobs/{job_id}/resume")
def resume_job(job_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    if job.status != "PAUSED":
        raise HTTPException(status_code=400, detail="Only paused jobs can be resumed")
        
    if job_id in PAUSE_EVENTS:
        PAUSE_EVENTS[job_id].set()  # Unblock worker thread
        
    job.status = "RUNNING"
    db.commit()
    write_audit_log("SUCCESS", "Job execution resumed by user.", job_id)
    return {"message": "Job resumed"}

@app.post("/api/jobs/{job_id}/stop")
def stop_job(job_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    if job.status not in ("RUNNING", "PAUSED"):
        raise HTTPException(status_code=400, detail="Only active jobs can be stopped")
        
    STOP_FLAGS[job_id] = True
    if job_id in PAUSE_EVENTS:
        PAUSE_EVENTS[job_id].set()  # Unblock thread if paused so it can detect stop flag
        
    job.status = "STOPPED"
    job.completed_at = datetime.datetime.utcnow()
    db.commit()
    write_audit_log("WARNING", "Job execution terminated by user.", job_id)
    return {"message": "Job stopped"}

@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    if job.status in ("RUNNING", "PAUSED"):
        raise HTTPException(status_code=400, detail="Cannot delete an active job. Stop it first.")
        
    db.delete(job)
    db.commit()
    write_audit_log("WARNING", f"Deleted job data for Job ID: {job_id}")
    return {"message": "Job deleted successfully"}

# =====================================================================
# REPORT EXPORT ROUTERS
# =====================================================================

@app.get("/api/exports/{job_id}/download")
def download_report(job_id: int, format: str = "xlsx", current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    if job.status != "COMPLETED" and job.total_schools_found == 0:
        raise HTTPException(status_code=400, detail="No report data generated yet for this job")
        
    # Standard format naming
    clean_state = job.state.replace(" ", "_").lower()
    clean_districts = job.districts.replace(" ", "_").replace(",", "_").lower()
    if len(clean_districts) > 50:
        clean_districts = clean_districts[:47] + "_etc"
    filename = f"schoolminer_{job_id}_{clean_state}_{clean_districts}.{format}"
    filepath = os.path.join(job.output_folder or "Output", filename)
    
    if not os.path.exists(filepath):
        # Fallback export generation in case files were deleted
        from .services.export_service import generate_export_files
        generate_export_files(job_id)
        if not os.path.exists(filepath):
            raise HTTPException(status_code=404, detail="Export file could not be generated.")
            
    media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if format == "xlsx" else "text/csv"
    return FileResponse(path=filepath, filename=filename, media_type=media_type)

# =====================================================================
# AUDIT LOGS ROUTERS
# =====================================================================

@app.get("/api/logs", response_model=List[AuditLogResponse])
def get_logs(job_id: Optional[int] = None, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(AuditLog)
    if job_id is not None:
        query = query.filter(AuditLog.job_id == job_id)
    return query.order_by(AuditLog.timestamp.desc()).limit(150).all()

@app.delete("/api/logs")
def clear_logs(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(AuditLog).delete()
    db.commit()
    write_audit_log("WARNING", "Audit Log Console cleared by administrator.")
    return {"message": "Logs cleared"}

# =====================================================================
# FIELD PRESETS ROUTERS
# =====================================================================

@app.get("/api/presets")
def get_presets(current_user: User = Depends(get_current_user)):
    presets = load_presets_from_file()
    return [{"name": k, "fields": v} for k, v in presets.items()]

@app.post("/api/presets")
def save_preset(preset: PresetSave, current_user: User = Depends(get_current_user)):
    presets = load_presets_from_file()
    presets[preset.name] = preset.fields
    save_presets_to_file(presets)
    write_audit_log("SUCCESS", f"Saved selection preset: {preset.name}")
    return {"message": "Preset saved"}

# =====================================================================
# STATISTICAL ROUTERS
# =====================================================================

@app.get("/api/stats", response_model=SystemStats)
def get_system_stats(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    total_records = db.query(SchoolRecord).count()
    completed = db.query(Job).filter(Job.status == "COMPLETED").count()
    running = db.query(Job).filter(Job.status == "RUNNING").count()
    failed = db.query(Job).filter(Job.status == "FAILED").count()
    
    # Calculate average scraper speed for completed jobs
    jobs = db.query(Job).filter(Job.status == "COMPLETED").all()
    avg_speed = 0.0
    if jobs:
        avg_speed = round(sum(j.speed_rpm for j in jobs) / len(jobs), 1)
        
    # Count generated reports today
    today_start = datetime.datetime.combine(datetime.date.today(), datetime.time.min)
    today_reports = db.query(Job).filter(
        Job.status == "COMPLETED", 
        Job.completed_at >= today_start
    ).count()
    
    return {
        "total_records": total_records,
        "completed_jobs": completed,
        "running_jobs": running,
        "failed_jobs": failed,
        "average_speed": avg_speed,
        "today_reports": today_reports
    }
