# seed.py
from datetime import date, timedelta
from databases import SessionLocal, init_db
from models import *
import random
from uuid import uuid4

blood_types = list(BloodType)
request_statuses = list(RequestStatus)
donation_statuses = list(DonationStatus)
log_actions = list(LogAction)

def random_date():
    return date.today() - timedelta(days=random.randint(0, 365))

def populate_database():
    init_db()
    db = SessionLocal()

    try:
        print("Starting database population...")

        # ---------------------------
        # 1. ADDRESSES
        # ---------------------------
        addresses = []
        for i in range(80):
            addr = Address(
                addressId=f"A{i:03}",
                street=f"{i} Main Street",
                city="Metropolis",
                state="CA",
                zipCode=f"900{i:02}",
                latitude=34.0 + random.random(),
                longitude=-118.0 + random.random()
            )
            addresses.append(addr)
        db.add_all(addresses)

        # ---------------------------
        # 2. BLOOD BANK UNITS
        # ---------------------------
        bank_units = []
        for i in range(10):
            unit = BloodBankUnit(
                unitId=f"BBU{i:03}",
                name=f"Blood Bank {i}",
                contactNumber=f"555-{1000+i}"
            )
            bank_units.append(unit)
        db.add_all(bank_units)

        # ---------------------------
        # 3. INVENTORY
        # ---------------------------
        inventories = []
        for i in range(80):
            inv = Inventory(
                inventoryId=f"I{i:03}",
                unitsAvailable=random.randint(10, 300),
                lastUpdated=random_date(),
                minOrderAmt=random.randint(5, 20),
                maxStorage=random.randint(200, 800),
                unitId=random.choice(bank_units).unitId,
                blood_type=random.choice(blood_types),
                component=random.choice(["WHOLE_BLOOD", "PLASMA", "PLATELETS"])
            )
            inventories.append(inv)
        db.add_all(inventories)

        # ---------------------------
        # 4. BLOOD COMPONENTS
        # ---------------------------
        components = []
        comp_names = ["Plasma", "Platelets", "Red Cells"]
        for i in range(120):
            comp = BloodComponent(
                componentId=f"BC{i:03}",
                name=random.choice(comp_names),
                storageConditions="Standard Storage",
                inventory_fk=random.choice(inventories).inventoryId
            )
            components.append(comp)
        db.add_all(components)

        # ---------------------------
        # 5. HOSPITAL UNITS
        # ---------------------------
        hospitals = []
        for i in range(25):
            hosp = HospitalUnit(
                unitId=f"HU{i:03}",
                name=f"Hospital {i}",
                contactNumber=f"444-{2000+i}",
                addressId=random.choice(addresses).addressId
            )
            hospitals.append(hosp)
        db.add_all(hospitals)

        # ---------------------------
        # 6. USERS
        # ---------------------------
        users = []
        donors = []
        admins = []
        staff_members = []
        contacts = []

        for i in range(150):
            uid = f"U{i:03}"
            role = random.choice(["donor", "hospital_admin", "blood_bank_staff"])

            if role == "donor":
                user = Donor(
                    userId=uid,
                    username=f"donor{i}",
                    passwordHash="hash",
                    timestamp=date.today(),
                    bloodType=random.choice(blood_types),
                    lastDonationDate=random_date(),
                    isEligible=random.choice([True, False]),
                    user_type='donor'
                )
                donors.append(user)

            elif role == "hospital_admin":
                user = HospitalAdmin(
                    userId=uid,
                    username=f"admin{i}",
                    passwordHash="hash",
                    timestamp=date.today(),
                    hospitalInitId=random.choice(hospitals).unitId,
                    user_type='hospital_admin'
                )
                admins.append(user)

            else:
                user = BloodBankStaff(
                    userId=uid,
                    username=f"staff{i}",
                    passwordHash="hash",
                    timestamp=date.today(),
                    user_type='blood_bank_staff'
                )
                staff_members.append(user)

            users.append(user)

            contacts.append(ContactInfo(
                contactId=f"C{i:03}",
                phone=f"999-{3000+i}",
                email=f"user{i}@mail.com",
                user_fk=uid
            ))

        db.add_all(users + contacts)

        # ---------------------------
        # 7. DONATIONS
        # ---------------------------
        donations = []
        for i in range(120):
            donor = random.choice(donors)
            donation = Donation(
                donationId=f"D{i:03}",
                donorId=donor.userId,
                date=random_date(),
                quantity=random.randint(300, 500),
                status=random.choice(donation_statuses),
                blood_type=donor.bloodType
            )
            donations.append(donation)
        db.add_all(donations)

        # ---------------------------
        # 8. BLOOD REQUESTS
        # ---------------------------
        requests = []
        for i in range(90):
            req = BloodRequest(
                requestId=f"R{i:03}",
                hospitalId=random.choice(hospitals).unitId,
                requestedId=f"P{i:03}",
                requestDate=random_date(),
                quantity=random.randint(1, 50),
                blood_type=random.choice(blood_types),
                isUrgent=random.choice([True, False]),
                status=random.choice(request_statuses)
            )
            requests.append(req)
        db.add_all(requests)

        # ---------------------------
        # 9. AUDIT LOGS
        # ---------------------------
        logs = []
        for i in range(200):
            log = AuditLog(
                logId=f"L{i:03}",
                userId=random.choice(users).userId,
                timestamp=random_date(),
                type=random.choice(log_actions),
                details="System generated log"
            )
            logs.append(log)
        db.add_all(logs)

        db.commit()
        print("Database populated with ~800 rows successfully!")

    except Exception as e:
        db.rollback()
        print("Error:", e)
    finally:
        db.close()

if __name__ == "__main__":
    populate_database()