from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

# User Auth Schemas
class UserBase(BaseModel):
    username: str

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    id: int
    role: str

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str
    username: str

class TokenData(BaseModel):
    username: Optional[str] = None

# Job Schemas
class JobCreate(BaseModel):
    board: str
    state: str
    districts: List[str]
    fields: List[str]
    output_format: str = "xlsx"  # xlsx, csv, both
    output_folder: str = "Output"

class SchoolRecordResponse(BaseModel):
    id: int
    school_name: str
    udise: Optional[str] = None
    affiliation_number: Optional[str] = None
    address: Optional[str] = None
    village: Optional[str] = None
    city: Optional[str] = None
    district: str
    state: str
    pin_code: Optional[str] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    principal: Optional[str] = None
    category: Optional[str] = None
    management: Optional[str] = None
    school_type: Optional[str] = None
    medium: Optional[str] = None
    latitude: Optional[str] = None
    longitude: Optional[str] = None
    established_year: Optional[str] = None

    class Config:
        from_attributes = True

class JobResponse(BaseModel):
    id: int
    board: str
    state: str
    districts: str
    fields: str
    output_format: str
    output_folder: str
    status: str
    total_schools_found: int
    progress_percent: float
    speed_rpm: float
    errors_count: int
    current_district: Optional[str] = None
    current_page: int
    started_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# Presets Schemas
class PresetSave(BaseModel):
    name: str
    fields: List[str]

class PresetResponse(BaseModel):
    id: int
    name: str
    fields: List[str]

# Audit Logs Schemas
class AuditLogResponse(BaseModel):
    id: int
    timestamp: datetime
    level: str
    message: str
    job_id: Optional[int] = None

    class Config:
        from_attributes = True

# Overall Stats Schemas
class SystemStats(BaseModel):
    total_records: int
    completed_jobs: int
    running_jobs: int
    failed_jobs: int
    average_speed: float
    today_reports: int
