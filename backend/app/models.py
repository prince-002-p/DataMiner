import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from .database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="user")  # admin, user

class Job(Base):
    __tablename__ = "jobs"
    
    id = Column(Integer, primary_key=True, index=True)
    board = Column(String, nullable=False)
    state = Column(String, nullable=False)
    districts = Column(String, nullable=False)  # Comma separated district names
    fields = Column(String, nullable=False)     # JSON string of selected fields
    output_format = Column(String, default="xlsx")  # xlsx, csv, both
    output_folder = Column(String, default="Output")
    status = Column(String, default="PENDING")  # PENDING, RUNNING, PAUSED, STOPPED, COMPLETED, FAILED
    
    total_schools_found = Column(Integer, default=0)
    progress_percent = Column(Float, default=0.0)
    speed_rpm = Column(Float, default=0.0)
    errors_count = Column(Integer, default=0)
    
    current_district = Column(String, nullable=True)
    current_page = Column(Integer, default=1)
    
    started_at = Column(DateTime, default=datetime.datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    records = relationship("SchoolRecord", back_populates="job", cascade="all, delete-orphan")

class SchoolRecord(Base):
    __tablename__ = "school_records"
    
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    
    # 21 parameters requested by user
    school_name = Column(String, index=True)
    udise = Column(String, nullable=True)
    affiliation_number = Column(String, nullable=True)
    address = Column(String, nullable=True)
    village = Column(String, nullable=True)
    city = Column(String, nullable=True)
    district = Column(String, index=True)
    state = Column(String, index=True)
    pin_code = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    mobile = Column(String, nullable=True)
    email = Column(String, nullable=True)
    website = Column(String, nullable=True)
    principal = Column(String, nullable=True)
    category = Column(String, nullable=True)
    management = Column(String, nullable=True)
    school_type = Column(String, nullable=True)
    medium = Column(String, nullable=True)
    latitude = Column(String, nullable=True)
    longitude = Column(String, nullable=True)
    established_year = Column(String, nullable=True)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    job = relationship("Job", back_populates="records")

class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    level = Column(String, default="INFO")  # INFO, SUCCESS, WARNING, ERROR, DEBUG
    message = Column(String, nullable=False)
    job_id = Column(Integer, nullable=True)
