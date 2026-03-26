# seed.py  — Run once: python seed.py
import random, hashlib
from datetime import date, timedelta, datetime
from databases import SessionLocal, init_db
from models import (
    Address, BloodBankUnit, BloodBankStaff, Admin, BloodComponent, BloodRequest,
    BloodType, ContactInfo, Donation, DonationStatus, Donor, HospitalAdmin,
    HospitalUnit, Inventory, LogAction, AuditLog, RequestStatus, User,
    SCOPE_BLOODBANK, SCOPE_HOSPITAL, SCOPE_SYSTEM,
)

def hp(p): return hashlib.sha256(p.encode()).hexdigest()
def rdate(n=365): return date.today() - timedelta(days=random.randint(0, n))
def rdatetime(n=365):
    d = rdate(n)
    return datetime(d.year, d.month, d.day, random.randint(0,23), random.randint(0,59))

CITIES = [
    ("Los Angeles","CA",34.05,-118.24), ("San Francisco","CA",37.77,-122.42),
    ("Sacramento","CA",38.58,-121.49),  ("San Diego","CA",32.72,-117.15),
    ("Fresno","CA",36.74,-119.77),      ("Long Beach","CA",33.77,-118.19),
    ("Oakland","CA",37.80,-122.27),     ("Bakersfield","CA",35.37,-119.01),
    ("Anaheim","CA",33.84,-117.91),     ("Santa Ana","CA",33.75,-117.87),
]
BTS   = list(BloodType)
RSTS  = list(RequestStatus)
DSS   = list(DonationStatus)
LACTS = list(LogAction)

def populate_database():
    init_db()
    db = SessionLocal()
    try:
        print("Seeding database (~1100 rows)…")

        # ── Addresses (100) ──────────────────────────────────────────────────
        addresses = []
        for i in range(100):
            city, state, base_lat, base_lon = random.choice(CITIES)
            addresses.append(Address(
                addressId=f"A{i:03}", street=f"{random.randint(100,9999)} {random.choice(['Main','Oak','Park','River','Lake'])} St",
                city=city, state=state, zipCode=f"{90000+i}",
                latitude=round(base_lat + random.uniform(-0.3, 0.3), 5),
                longitude=round(base_lon + random.uniform(-0.3, 0.3), 5),
            ))
        db.add_all(addresses); db.flush()

        # ── Blood bank units (15, each with an address) ──────────────────────
        bank_units = []
        for i in range(15):
            addr = addresses[i]
            bank_units.append(BloodBankUnit(
                unitId=f"BBU{i:03}", name=f"Blood Bank {addr.city} #{i}",
                contactNumber=f"555-{1000+i}", addressId=addr.addressId,
            ))
        db.add_all(bank_units); db.flush()

        # ── Inventory (120) ──────────────────────────────────────────────────
        inventories = []
        for i in range(120):
            inventories.append(Inventory(
                inventoryId=f"I{i:03}", unitsAvailable=random.randint(5,350),
                lastUpdated=rdate(), minOrderAmt=random.randint(5,20),
                maxStorage=float(random.randint(200,1000)),
                unitId=random.choice(bank_units).unitId,
                blood_type=random.choice(BTS),
                component=random.choice(["WHOLE_BLOOD","PLASMA","PLATELETS"]),
            ))
        db.add_all(inventories); db.flush()

        db.add_all([BloodComponent(componentId=f"BC{i:03}",
            name=random.choice(["Plasma","Platelets","Red Cells"]),
            storageConditions="Standard Storage",
            inventory_fk=random.choice(inventories).inventoryId)
            for i in range(80)]); db.flush()

        # ── Hospital units (30, each with an address) ────────────────────────
        hospitals = []
        for i in range(30):
            addr = addresses[15 + i % 85]
            hospitals.append(HospitalUnit(
                unitId=f"HU{i:03}", name=f"City Hospital {addr.city} #{i}",
                contactNumber=f"444-{2000+i}", addressId=addr.addressId,
            ))
        db.add_all(hospitals); db.flush()

        # ── Seeded users (200) ───────────────────────────────────────────────
        SH = hp("password123")
        users, donors, staff_users, hosp_users = [], [], [], []
        contacts = []
        for i in range(200):
            uid  = f"U{i:03}"
            role = random.choice(["donor","hospital_admin","blood_bank_staff"])
            if role == "donor":
                u = Donor(userId=uid, username=f"donor{i}", passwordHash=SH,
                    timestamp=date.today(), bloodType=random.choice(BTS),
                    lastDonationDate=rdate(), isEligible=random.choice([True,False]),
                    user_type="donor"); donors.append(u)
            elif role == "hospital_admin":
                u = HospitalAdmin(userId=uid, username=f"hadmin{i}", passwordHash=SH,
                    timestamp=date.today(), hospitalInitId=random.choice(hospitals).unitId,
                    user_type="hospital_admin"); hosp_users.append(u)
            else:
                u = BloodBankStaff(userId=uid, username=f"staff{i}", passwordHash=SH,
                    timestamp=date.today(), unitId=random.choice(bank_units).unitId,
                    user_type="blood_bank_staff"); staff_users.append(u)
            users.append(u)
            contacts.append(ContactInfo(contactId=f"C{i:03}", phone=f"999-{3000+i}",
                email=f"user{i}@mail.com", user_fk=uid))
        db.add_all(users); db.flush()
        db.add_all(contacts); db.flush()

        # ── 3 Named test accounts ────────────────────────────────────────────
        if not db.query(User).filter(User.username=="superadmin").first():
            a = Admin(userId="ADMIN001", username="superadmin",
                passwordHash=hp("admin123"), timestamp=date.today(), user_type="admin")
            db.add(a); db.flush()
            db.add(ContactInfo(contactId="CA001", phone="0000000001",
                email="admin@lifelink.local", user_fk="ADMIN001")); db.flush()
            print("  admin    → superadmin  / admin123")

        if not db.query(User).filter(User.username=="staffdemo").first():
            s = BloodBankStaff(userId="STAFF001", username="staffdemo",
                passwordHash=hp("staff123"), timestamp=date.today(),
                unitId="BBU000", user_type="blood_bank_staff")
            db.add(s); db.flush()
            db.add(ContactInfo(contactId="CS001", phone="0000000002",
                email="staff@lifelink.local", user_fk="STAFF001")); db.flush()
            staff_users.append(s); print("  staff    → staffdemo   / staff123  (BBU000)")

        if not db.query(User).filter(User.username=="hospitaldemo").first():
            h = HospitalAdmin(userId="HOSP001", username="hospitaldemo",
                passwordHash=hp("hospital123"), timestamp=date.today(),
                hospitalInitId="HU000", user_type="hospital_admin")
            db.add(h); db.flush()
            db.add(ContactInfo(contactId="CH001", phone="0000000003",
                email="hospital@lifelink.local", user_fk="HOSP001")); db.flush()
            hosp_users.append(h); print("  hospital → hospitaldemo / hospital123  (HU000)")

        # ── Donations (200) ──────────────────────────────────────────────────
        if donors:
            db.add_all([Donation(donationId=f"D{i:03}", donorId=random.choice(donors).userId,
                date=rdate(), quantity=random.randint(300,500),
                status=random.choice(DSS), blood_type=random.choice(BTS))
                for i in range(200)]); db.flush()

        # ── Blood requests (150) ─────────────────────────────────────────────
        db.add_all([BloodRequest(requestId=f"R{i:03}",
            hospitalId=random.choice(hospitals).unitId,
            targetBankId=random.choice(bank_units).unitId if random.random()>0.5 else None,
            requestedId=f"P{i:03}", requestDate=rdate(),
            quantity=random.randint(1,50), blood_type=random.choice(BTS),
            isUrgent=random.choice([True,False]), status=random.choice(RSTS))
            for i in range(150)]); db.flush()

        # ── Audit logs (250, scoped) ──────────────────────────────────────────
        all_users = users
        for i in range(250):
            u = random.choice(all_users)
            if u.user_type == 'blood_bank_staff':
                stype = SCOPE_BLOODBANK
                sid   = getattr(u,'unitId',None) or random.choice(bank_units).unitId
            elif u.user_type == 'hospital_admin':
                stype = SCOPE_HOSPITAL
                sid   = getattr(u,'hospitalInitId',None) or random.choice(hospitals).unitId
            else:
                stype = SCOPE_SYSTEM; sid = None
            db.add(AuditLog(logId=f"L{i:03}", userId=u.userId,
                timestamp=rdatetime(), type=random.choice(LACTS),
                details="System generated log", scope_type=stype, scope_id=sid))
        db.flush()

        db.commit()
        print(f"\n✓ Database seeded (~1100 rows).")
        print("  ┌──────────┬────────────────┬────────────┬──────────┐")
        print("  │ Role     │ Username       │ Password   │ Unit     │")
        print("  ├──────────┼────────────────┼────────────┼──────────┤")
        print("  │ Admin    │ superadmin     │ admin123   │ all      │")
        print("  │ Staff    │ staffdemo      │ staff123   │ BBU000   │")
        print("  │ Hospital │ hospitaldemo   │ hospital123│ HU000    │")
        print("  └──────────┴────────────────┴────────────┴──────────┘")
        print("  200 random users: password123")
        print("  Run: python app.py → http://127.0.0.1:5000/login")
    except Exception as e:
        db.rollback(); print(f"[seed] ERROR: {e}"); raise
    finally:
        db.close()

if __name__ == "__main__":
    populate_database()
