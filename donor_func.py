# donor_func.py
from datetime import date, timedelta
from models import Donor
from sqlalchemy.orm import Session


def check_donor_eligibility(donor: Donor) -> bool:
    """Return True if donor is currently eligible to donate."""
    if not donor.isEligible:
        return False
    if donor.lastDonationDate:
        next_eligible = donor.lastDonationDate + timedelta(days=56)
        if date.today() < next_eligible:
            return False
    return True


def update_health_metrics(db: Session, donor_id_input: str, failed_screening: bool) -> tuple:
    """Update donor eligibility based on a health screening result."""
    donor = db.query(Donor).filter(Donor.userId.startswith(donor_id_input)).first()
    if not donor:
        return False, f"Donor ID {donor_id_input} not found."

    if failed_screening:
        donor.isEligible = False
        msg = f"Screening failed — {donor.username} marked INELIGIBLE."
    else:
        donor.isEligible = check_donor_eligibility(donor)
        msg = f"Screening passed for {donor.username}. Eligibility recalculated."

    db.commit()
    return True, msg
