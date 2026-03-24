# donor_func.py
from datetime import date, timedelta
from models import Donor
from sqlalchemy.orm import Session

# --- 1. Eligibility Check (Function #3) ---

def check_donor_eligibility(donor: Donor) -> bool:
    """
    Function #3: Checks if a donor is eligible based on the last donation date and health status.
    """
    # 1. Check if the eligibility flag is False (due to a failed screening or recent donation)
    if not donor.isEligible:
        return False
        
    # 2. Check cooldown period (assuming a 56-day cooldown)
    if donor.lastDonationDate:
        cooldown_period = timedelta(days=56)
        next_eligible_date = donor.lastDonationDate + cooldown_period
        
        if date.today() < next_eligible_date:
            return False # Still in cooldown
            
    return True # Passed health flag check and cooldown check

# --- 2. Health Metrics Update (Function #2) ---

def update_health_metrics(db: Session, donor_id_input: str, failed_screening: bool) -> tuple[bool, str]:
    """
    Function #2: Updates a donor's eligibility status based on a health screening result.
    If the screening failed, the donor is immediately marked as ineligible (isEligible=False).
    
    Returns a tuple: (success: bool, message: str)
    """
    # Use the same partial matching logic as record_donation
    donor = db.query(Donor).filter(Donor.userId.startswith(donor_id_input)).first()
    
    if not donor:
        return False, f"Donor ID {donor_id_input} not found."
    
    if failed_screening:
        # Override cooldown—set eligibility to False due to health
        donor.isEligible = False
        message = f"Health screening failed. Donor {donor.username} (ID: {donor_id_input}) marked INELIGIBLE."
    else:
        # If the screening passed, re-calculate eligibility based on cooldown and update the flag
        donor.isEligible = check_donor_eligibility(donor)
        message = f"Health screening passed for Donor {donor.username} (ID: {donor_id_input}). Eligibility updated based on cooldown."
    
    db.commit()
    return True, message