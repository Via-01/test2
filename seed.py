# seed.py
from datetime import date
from databases import SessionLocal, init_db
from models import (
    Address, BloodType, User, Donor, HospitalAdmin, BloodBankStaff, 
    BloodBankUnit, Inventory, BloodComponent, LogAction, AuditLog, 
    ContactInfo, RequestStatus, DonationStatus, Donation, BloodRequest, HospitalUnit
)
import random
from uuid import uuid4

def populate_database():
    """Populates the database with initial sample data."""
    init_db() # Ensure tables are created
    db = SessionLocal()

    try:
        print("Starting database population...")

        # --- 1. Create Base Users and Contact Info ---
        def create_contact(user_id, phone, email):
            return ContactInfo(
                contactId=f"C-{user_id}",
                phone=phone,
                email=email,
                user_fk=user_id
            )
        
        donor_user = Donor(userId="U001", username="john_doe_donor", passwordHash="pwhash1", timestamp=date.today(), lastDonationDate=date(2025, 10, 1), isEligible=True, user_type='donor')
        admin_user = HospitalAdmin(userId="U002", username="admin_grace", passwordHash="pwhash2", timestamp=date.today(), hospitalInitId="H-MAIN", user_type='hospital_admin')
        staff_user = BloodBankStaff(userId="U003", username="staff_mike", passwordHash="pwhash3", timestamp=date.today(), user_type='blood_bank_staff')

        db.add_all([
            donor_user, admin_user, staff_user,
            create_contact("U001", "555-1234", "john.doe@example.com"),
            create_contact("U002", "555-5678", "admin.grace@mainhosp.com"),
            create_contact("U003", "555-9012", "mike.staff@bloodbank.org")
        ])

        # --- 2. Create Addresses ---
        bank_address = Address(addressId="A001", street="123 Main St", city="Metropolis", state="CA", zipCode="90210", latitude=34.05, longitude=-118.24)
        hospital_address = Address(addressId="A002", street="456 Health Dr", city="Metropolis", state="CA", zipCode="90211", latitude=34.06, longitude=-118.25)
        db.add_all([bank_address, hospital_address])

        # --- 3. Create Blood Bank Unit and Inventory ---
        packed_red_cells = BloodComponent(componentId="BC001", name="Packed Red Cells", storageConditions="2-6°C")
        platelets = BloodComponent(componentId="BC002", name="Platelets", storageConditions="20-24°C, agitated")
        db.add_all([packed_red_cells, platelets])

        # Inventory arguments match models.py (blood_type and component)
        inventory_unit = Inventory(
            inventoryId="I001", 
            unitsAvailable=150, 
            lastUpdated=date.today(), 
            minOrderAmt=10, 
            maxStorage=500.0, 
            unitId="BBU001",
            blood_type=BloodType.O_NEGATIVE, # Matches Inventory model column
            component="WHOLE_BLOOD"          # Matches Inventory model column
        )
        bank_unit = BloodBankUnit(unitId="BBU001", name="Central Blood Storage", contactNumber="555-UNIT")
        db.add_all([inventory_unit, bank_unit])

        bank_address.inventory_fk = "I001" 

        # --- 4. Create Hospital Unit ---
        hospital_unit = HospitalUnit(unitId="HU001", name="City General Hospital", contactNumber="555-HOSP", addressId="A002")
        db.add(hospital_unit)

        # --- 5. Create Donation and Request (Test Data) ---
        donation = Donation(
            donationId="D001",
            donorId="U001",
            date=date(2025, 11, 15),
            quantity=450,
            blood_type=BloodType.O_POSITIVE,
            status=DonationStatus.COMPLETE
        )

        # BloodRequest arguments match models.py (requestDate and isUrgent)
        request = BloodRequest(
            requestId="R001",
            hospitalId="HU001",
            requestedId="P-999", 
            requestDate=date.today(), # Matches BloodRequest model column
            quantity=20,
            blood_type=BloodType.A_NEGATIVE,
            isUrgent=True, # Matches BloodRequest model column
            status=RequestStatus.PENDING
        )
        db.add_all([donation, request])

        # --- 6. Final Commit ---
        db.commit()
        print("Database successfully populated with sample data!")

    except Exception as e:
        db.rollback()
        print(f"An error occurred during population: {e}")
    finally:
        db.close()

if __name__ == '__main__':
    populate_database()