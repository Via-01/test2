# main_routes.py (Focus on home_dashboard function)

from flask import Blueprint, render_template, request, redirect, url_for
from databases import get_db, SessionLocal 
from models import Donor, ContactInfo
from donor_func import check_donor_eligibility 

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def home_dashboard():
    db = next(get_db())
    try:
        donors = db.query(Donor).all()
        
        donor_list = []
        for donor in donors:
            contact = db.query(ContactInfo).filter(ContactInfo.user_fk == donor.userId).first()
            
            is_eligible = check_donor_eligibility(donor)
            
            # --- MODIFICATION HERE: Restrict displayed ID to 7 characters ---
            # If the ID starts with 'U', we keep the prefix and the next 6 chars.
            # If it's an old, long UUID, we just show the first 7 chars for display.
            display_id = donor.userId[:5]
            
            donor_list.append({
                "username": donor.username,
                "userId": display_id, # Use the restricted ID for display
                "email": contact.email if contact else "N/A",
                "phone": contact.phone if contact else "N/A",
                "lastDonation": donor.lastDonationDate.strftime("%Y-%m-%d") if donor.lastDonationDate else "N/A",
                "isEligible": "Eligible" if is_eligible else "Ineligible"
            })
        
        success_message = request.args.get('success')

        return render_template(
            'index.html', 
            title='LifeLink Dashboard', 
            donors=donor_list,
            success=success_message
        )
    finally:
        db.close()