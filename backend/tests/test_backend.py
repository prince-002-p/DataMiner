import os
import sys
import json
import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add app directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import Base
from app.models import User, Job, SchoolRecord, AuditLog
from app.security import get_password_hash, verify_password, create_access_token
from app.services.scraper_worker import split_phone, parse_address_components

def test_database_and_models():
    print("[TEST] Running DB and Models Tests...")
    # Use in-memory SQLite for testing
    engine = create_engine("sqlite:///:memory:")
    Session = sessionmaker(bind=engine)
    session = Session()
    Base.metadata.create_all(bind=engine)
    
    # 1. Test User creation
    hashed = get_password_hash("testpass")
    user = User(username="testuser", hashed_password=hashed, role="user")
    session.add(user)
    session.commit()
    
    retrieved_user = session.query(User).filter(User.username == "testuser").first()
    assert retrieved_user is not None
    assert verify_password("testpass", retrieved_user.hashed_password) is True
    assert verify_password("wrongpass", retrieved_user.hashed_password) is False
    print("SUCCESS: User auth and password hashing verified.")
    
    # 2. Test Job creation
    job = Job(
        board="cbse",
        state="punjab",
        districts="amritsar,jalandhar",
        fields=json.dumps(["School Name", "Email"]),
        status="PENDING"
    )
    session.add(job)
    session.commit()
    
    retrieved_job = session.query(Job).filter(Job.state == "punjab").first()
    assert retrieved_job is not None
    assert retrieved_job.status == "PENDING"
    assert "amritsar" in retrieved_job.districts
    print("SUCCESS: Job model verified.")
    
    # 3. Test SchoolRecord relation
    record = SchoolRecord(
        job_id=job.id,
        school_name="Dav Public School",
        district="Amritsar",
        state="Punjab",
        email="dav@amritsar.com"
    )
    session.add(record)
    session.commit()
    
    assert len(retrieved_job.records) == 1
    assert retrieved_job.records[0].school_name == "Dav Public School"
    print("SUCCESS: School Record relationships verified.")
    
    session.close()

def test_security_jwt():
    print("[TEST] Running Security JWT Tests...")
    data = {"sub": "admin"}
    token = create_access_token(data=data)
    assert token is not None
    assert isinstance(token, str)
    print("SUCCESS: JWT Access Token generation verified.")

def test_scraper_helpers():
    print("[TEST] Running Scraper Helper Parsing Tests...")
    
    # 1. Test split phone number
    landline, mobile = split_phone("01772624321, 9876543210, 918765432101")
    assert "9876543210" in mobile
    assert "01772624321" in landline
    print("SUCCESS: Split phone helper verified.")
    
    # 2. Test address components parser
    pin, city, village = parse_address_components("Behind Block Office, Koni Town, Bilaspur - 495009")
    assert pin == "495009"
    assert city == "Bilaspur"
    assert village == "Koni Town"
    print("SUCCESS: Address parser helper verified.")

if __name__ == "__main__":
    try:
        test_database_and_models()
        test_security_jwt()
        test_scraper_helpers()
        print("\nALL TESTS PASSED SUCCESSFULLY!\n")
        sys.exit(0)
    except AssertionError as ae:
        print(f"\nTest Assertion Failed: {ae}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected Error during testing: {e}\n")
        sys.exit(1)
