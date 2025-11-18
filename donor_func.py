# donor_func.py
from datetime import date, timedelta
from models import Donor
# NOTE: Ensure databases.py exists and exports SessionLocal
from databases import SessionLocal 

# --- Configuration for Function #3 ---
DONATION_COOLDOWN_DAYS = 90

def check_donor_eligibility(donor: Donor) -> bool:
    """
    Function #3: Checks if a donor is eligible based on ALL criteria.
    
    A donor must pass both the 90-day cooldown AND the static health flag.
    """
    # 1. Check Cooldown Period
    if donor.lastDonationDate is None:
        cooldown_ok = True
    else:
        eligible_date = donor.lastDonationDate + timedelta(days=DONATION_COOLDOWN_DAYS)
        cooldown_ok = date.today() >= eligible_date
        
    # 2. Check Static Eligibility Flag (Health status controlled by Function #2)
    return cooldown_ok and donor.isEligible 

def update_donor_eligibility_status(db, donor_id: str):
    """
    Recalculates and updates the final isEligible status based on ALL criteria.
    NOTE: This is not currently used in the main routes but is available for reuse.
    """
    donor = db.query(Donor).filter(Donor.userId == donor_id).first()
    if donor:
        new_status = check_donor_eligibility(donor)
        if donor.isEligible != new_status:
            donor.isEligible = new_status
            db.commit()
            return True
    return False

def update_health_metrics(db, donor_id: str, low_hgb: bool = False) -> bool:
    """
    Function #2: Updates health data and sets the static isEligible flag based on screening results.
    
    Simulates a health screening failure (e.g., low hemoglobin) and sets the static 
    donor.isEligible flag accordingly.
    """
    donor = db.query(Donor).filter(Donor.userId == donor_id).first()
    if donor:
        if low_hgb:
            # Failed health check (e.g., low Hemoglobin)
            donor.isEligible = False
            print(f"Donor {donor_id} failed screening (Low Hgb). Eligibility set to False.")
        else:
            # Passed health check
            # This is only True if the cooldown period is also passed, but we set the static flag here.
            donor.isEligible = True 
            print(f"Donor {donor_id} passed screening. Eligibility flag set to True.")

        db.commit()
        return True
    return False