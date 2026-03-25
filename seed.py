# seed.py
# Populates the database with realistic test data.
# Also creates a guaranteed staff login account so you can always log in.
#
# Usage:  python seed.py
# Login:  username=admin  password=admin123

import random
import hashlib
from datetime import date, timedelta
from databases import SessionLocal, init_db
from models import (
    Address, BloodBankUnit, BloodBankStaff, BloodComponent, BloodRequest,
    BloodType, ContactInfo, Donation, DonationStatus, Donor, HospitalAdmin,
    HospitalUnit, Inventory, LogAction, AuditLog, Notification, Report,
    RequestStatus, User,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    """SHA-256 — matches auth.py's verify_password()."""
    return hashlib.sha256(plain.encode()).hexdigest()

def rdate(days_back: int = 365) -> date:
    return date.today() - timedelta(days=random.randint(0, days_back))

blood_types       = list(BloodType)
request_statuses  = list(RequestStatus)
donation_statuses = list(DonationStatus)
log_actions       = list(LogAction)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def populate_database():
    init_db()
    db = SessionLocal()

    try:
        print("Starting database population...")

        # ── 1. Addresses ────────────────────────────────────────────────────
        addresses = [
            Address(
                addressId=f"A{i:03}", street=f"{i*10} Main Street",
                city="Metropolis", state="CA", zipCode=f"900{i:02}",
                latitude=34.0 + random.random(),
                longitude=-118.0 + random.random(),
            )
            for i in range(80)
        ]
        db.add_all(addresses)
        db.flush()

        # ── 2. Blood bank units ─────────────────────────────────────────────
        bank_units = [
            BloodBankUnit(unitId=f"BBU{i:03}", name=f"Blood Bank {i}", contactNumber=f"555-{1000+i}")
            for i in range(10)
        ]
        db.add_all(bank_units)
        db.flush()

        # ── 3. Inventory ────────────────────────────────────────────────────
        inventories = [
            Inventory(
                inventoryId=f"I{i:03}",
                unitsAvailable=random.randint(10, 300),
                lastUpdated=rdate(),
                minOrderAmt=random.randint(5, 20),
                maxStorage=float(random.randint(200, 800)),
                unitId=random.choice(bank_units).unitId,
                blood_type=random.choice(blood_types),
                component=random.choice(["WHOLE_BLOOD", "PLASMA", "PLATELETS"]),
            )
            for i in range(80)
        ]
        db.add_all(inventories)
        db.flush()

        # ── 4. Blood components ─────────────────────────────────────────────
        comp_names = ["Plasma", "Platelets", "Red Cells"]
        db.add_all([
            BloodComponent(
                componentId=f"BC{i:03}",
                name=random.choice(comp_names),
                storageConditions="Standard Storage",
                inventory_fk=random.choice(inventories).inventoryId,
            )
            for i in range(120)
        ])
        db.flush()

        # ── 5. Hospital units ───────────────────────────────────────────────
        hospitals = [
            HospitalUnit(
                unitId=f"HU{i:03}", name=f"Hospital {i}",
                contactNumber=f"444-{2000+i}",
                addressId=random.choice(addresses).addressId,
            )
            for i in range(25)
        ]
        db.add_all(hospitals)
        db.flush()

        # ── 6. Users ────────────────────────────────────────────────────────
        # FIX: all seeded users get a real SHA-256 hash so login works.
        # Seeded users share the password "password123" for test convenience.
        SEEDED_HASH = hash_password("password123")

        users   = []
        donors  = []
        admins  = []
        contacts = []

        for i in range(150):
            uid  = f"U{i:03}"
            role = random.choice(["donor", "hospital_admin", "blood_bank_staff"])

            if role == "donor":
                u = Donor(
                    userId=uid, username=f"donor{i}",
                    passwordHash=SEEDED_HASH, timestamp=date.today(),
                    bloodType=random.choice(blood_types),
                    lastDonationDate=rdate(),
                    isEligible=random.choice([True, False]),
                    user_type="donor",
                )
                donors.append(u)

            elif role == "hospital_admin":
                u = HospitalAdmin(
                    userId=uid, username=f"hadmin{i}",
                    passwordHash=SEEDED_HASH, timestamp=date.today(),
                    hospitalInitId=random.choice(hospitals).unitId,
                    user_type="hospital_admin",
                )
                admins.append(u)

            else:
                u = BloodBankStaff(
                    userId=uid, username=f"staff{i}",
                    passwordHash=SEEDED_HASH, timestamp=date.today(),
                    user_type="blood_bank_staff",
                )

            users.append(u)
            contacts.append(ContactInfo(
                contactId=f"C{i:03}", phone=f"999-{3000+i}",
                email=f"user{i}@mail.com", user_fk=uid,
            ))

        db.add_all(users)
        db.flush()
        db.add_all(contacts)
        db.flush()

        # ── 7. GUARANTEED admin account ─────────────────────────────────────
        # Always present regardless of random role distribution above.
        if not db.query(User).filter(User.username == "admin").first():
            admin_staff = BloodBankStaff(
                userId="ADMIN001", username="admin",
                passwordHash=hash_password("admin123"),
                timestamp=date.today(), user_type="blood_bank_staff",
            )
            db.add(admin_staff)
            db.flush()
            db.add(ContactInfo(
                contactId="CADMIN001", phone="0000000000",
                email="admin@lifelink.local", user_fk="ADMIN001",
            ))
            db.flush()
            print("  [seed] Created guaranteed staff account: admin / admin123")

        # ── 8. Donations ────────────────────────────────────────────────────
        if donors:
            db.add_all([
                Donation(
                    donationId=f"D{i:03}",
                    donorId=random.choice(donors).userId,
                    date=rdate(),
                    quantity=random.randint(300, 500),
                    status=random.choice(donation_statuses),
                    blood_type=random.choice(blood_types),
                )
                for i in range(120)
            ])
            db.flush()

        # ── 9. Blood requests ───────────────────────────────────────────────
        db.add_all([
            BloodRequest(
                requestId=f"R{i:03}",
                hospitalId=random.choice(hospitals).unitId,
                requestedId=f"P{i:03}",
                requestDate=rdate(),
                quantity=random.randint(1, 50),
                blood_type=random.choice(blood_types),
                isUrgent=random.choice([True, False]),
                status=random.choice(request_statuses),
            )
            for i in range(90)
        ])
        db.flush()

        # ── 10. Audit logs ──────────────────────────────────────────────────
        db.add_all([
            AuditLog(
                logId=f"L{i:03}",
                userId=random.choice(users).userId,
                timestamp=rdate(),
                type=random.choice(log_actions),
                details="System generated log",
            )
            for i in range(200)
        ])
        db.flush()

        db.commit()
        print("Database populated successfully (~850 rows).")
        print("\n✓ Ready to run.")
        print("  Login URL : http://127.0.0.1:5000/login")
        print("  Username  : admin")
        print("  Password  : admin123")
        print("\n  All seeded users share password: password123")

    except Exception as e:
        db.rollback()
        print(f"[seed] ERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    populate_database()
