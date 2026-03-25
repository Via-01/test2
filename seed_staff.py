# seed_staff.py
# Run ONCE to bootstrap a staff account + BBU001 unit + starter inventory.
# Usage:  python seed_staff.py

import sys, hashlib, uuid
from datetime import date
sys.path.insert(0, '.')

from databases import init_db, SessionLocal
from models import BloodBankStaff, BloodBankUnit, ContactInfo, Inventory, BloodType, User

def hash_password(plain):
    return hashlib.sha256(plain.encode()).hexdigest()

def seed():
    init_db()
    db = SessionLocal()
    try:
        USERNAME, PASSWORD = "admin", "admin123"

        if not db.query(User).filter(User.username == USERNAME).first():
            staff = BloodBankStaff(
                userId=str(uuid.uuid4()), username=USERNAME,
                passwordHash=hash_password(PASSWORD),
                user_type="blood_bank_staff", timestamp=date.today(),
            )
            db.add(staff)
            db.flush()
            db.add(ContactInfo(
                contactId=str(uuid.uuid4()), user_fk=staff.userId,
                email="admin@lifelink.local", phone="0000000000",
            ))
            print(f"[seed] Created staff user '{USERNAME}' / '{PASSWORD}'")
        else:
            print(f"[seed] User '{USERNAME}' already exists.")

        if not db.query(BloodBankUnit).filter(BloodBankUnit.unitId == "BBU001").first():
            db.add(BloodBankUnit(unitId="BBU001", name="Main Blood Bank", contactNumber="0000000000"))
            print("[seed] Created BloodBankUnit BBU001")

        for bt in BloodType:
            if not db.query(Inventory).filter(Inventory.unitId=="BBU001", Inventory.blood_type==bt).first():
                db.add(Inventory(
                    inventoryId=f"I{uuid.uuid4().hex[:6].upper()}",
                    unitsAvailable=10, lastUpdated=date.today(),
                    minOrderAmt=5, maxStorage=500.0,
                    unitId="BBU001", blood_type=bt, component="WHOLE_BLOOD",
                ))
        print("[seed] Inventory initialised.")

        db.commit()
        print(f"\n✓ Done. Login: http://127.0.0.1:5000/login")
        print(f"  Username: {USERNAME}  Password: {PASSWORD}")
    except Exception as e:
        db.rollback(); print(f"ERROR: {e}"); raise
    finally:
        db.close()

if __name__ == "__main__":
    seed()
