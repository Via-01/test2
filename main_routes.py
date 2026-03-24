# main_routes.py
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
            
            # --- FIX: Use the stored donor.isEligible status for display ---
            # This status is directly updated by the 'Record Donation' and 'Health Update' routes.
            stored_is_eligible = donor.isEligible 
            
            # Truncate ID to 7 characters for display
            display_id = donor.userId[:7] 
            
            donor_list.append({
                "username": donor.username,
                "userId": display_id, 
                "email": contact.email if contact else "N/A",
                "phone": contact.phone if contact else "N/A",
                "lastDonation": donor.lastDonationDate.strftime("%Y-%m-%d") if donor.lastDonationDate else "N/A",
                # Display the stored status
                "isEligible": "Eligible" if stored_is_eligible else "Ineligible" 
            })
        
        success_message = request.args.get('success')
        error_message = request.args.get('error')

        return render_template(
            'index.html', 
            title='LifeLink Dashboard', 
            donors=donor_list,
            success=success_message,
            error=error_message
        )
    finally:
        db.close()