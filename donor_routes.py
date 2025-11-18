# donor_routes.py (Focus on add_donor function)

from flask import Blueprint, request, redirect, url_for
from databases import get_db
from models import Donor, ContactInfo
from uuid import uuid4
from datetime import date
from donor_func import update_health_metrics 

donor_bp = Blueprint('donor', __name__, url_prefix='/donor')

@donor_bp.route('/add', methods=['POST'])
def add_donor():
    db = next(get_db())
    try:
        username = request.form['username'].strip()
        email = request.form['email'].strip()
        phone = request.form['phone'].strip()
        
        if db.query(Donor).filter(Donor.username == username).first():
            return redirect(url_for('main.home_dashboard', error=f"Username {username} already exists!"))

        # --- MODIFICATION HERE: Restrict to 7 characters ---
        user_id = f"U{uuid4().hex[:4].upper()}" # Retaining the 'U' prefix
        # This gives a total ID length of 7 characters (U + 6 hex digits)

        new_donor = Donor(
            userId=user_id,
            username=username,
            passwordHash="default_hash", 
            timestamp=date.today(),
            lastDonationDate=None,
            isEligible=True,
            user_type='donor'
        )
        
        new_contact = ContactInfo(
            contactId=f"C-{user_id}",
            phone=phone,
            email=email,
            user_fk=user_id
        )
        
        db.add_all([new_donor, new_contact])
        db.commit()
        
        return redirect(url_for('main.home_dashboard', success="Donor registered successfully!"))
    
    except Exception as e:
        db.rollback()
        print(f"Error adding donor: {e}")
        return redirect(url_for('main.home_dashboard', error=f"Error registering donor: {e}"))
    finally:
        db.close()