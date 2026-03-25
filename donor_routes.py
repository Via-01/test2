from flask import Blueprint, render_template, request, redirect, url_for, flash
from databases import get_db
from models import User, Donor, ContactInfo, BloodType
from sqlalchemy.exc import IntegrityError
from datetime import date, timedelta
import uuid
from sqlalchemy.orm import joinedload

donor_bp = Blueprint('donor', __name__, url_prefix='/donor')

# --- Helper Function ---
def is_eligible(last_donation_date):
    """Checks if a donor is eligible for donation (>=56 days since last donation)."""
    if last_donation_date is None:
        return True
    next_eligible = last_donation_date + timedelta(days=56)
    return date.today() >= next_eligible

# --- Donor Dashboard Route ---
@donor_bp.route('/dashboard', methods=['GET', 'POST'])
def donor_dashboard():
    db = next(get_db())

    # --- Handle New Donor Registration (FIXED LOGIC) ---
    if request.method == 'POST' and 'username' in request.form:
        username = request.form.get('username')
        blood_type_str = request.form.get('blood_type')
        email = request.form.get('email')
        phone = request.form.get('phone')
        
        if not all([username, blood_type_str, email, phone]):
             flash("Error: All registration fields are required.", 'error')
        else:
            try:
                submitted_blood_type = BloodType[blood_type_str] 
                
                # --- START: Simplified Registration Logic ---
                
                # 1. CREATE ONLY THE DONOR OBJECT
                # SQLAlchemy automatically handles creating the corresponding User parent record.
                new_donor = Donor(
                    userId=str(uuid.uuid4()), # Must set userId here
                    username=username,
                    passwordHash='not-implemented',
                    user_type='donor',
                    timestamp=date.today(),
                    # Donor-specific fields
                    bloodType=submitted_blood_type, 
                    lastDonationDate=None,
                    isEligible=True
                )
                db.add(new_donor)
                db.flush() # Forces the new_donor's userId to be available

                # 2. Create ContactInfo, linking to the new_donor's ID
                new_contact = ContactInfo(
                    contactId=str(uuid.uuid4()),
                    user_fk=new_donor.userId, # Use the ID from the new_donor object
                    email=email,
                    phone=phone
                )
                db.add(new_contact)
                
                # 3. COMMIT
                db.commit()
                flash(f"Success! Donor {username} registered with Blood Type {submitted_blood_type.name}.", 'success')
                return redirect(url_for('donor.donor_dashboard'))

            except KeyError:
                db.rollback()
                flash("Error: Invalid Blood Type submitted. Check format.", 'error')
            except IntegrityError:
                db.rollback()
                flash("Error: Username already exists or a constraint was violated.", 'error')
            except Exception as e:
                db.rollback()
                flash(f"Unexpected error during registration: {str(e)}", 'error')
                
    # --- Handle Donor Health & Eligibility (Updated with Manual Override) ---
    if request.method == 'POST' and 'donor_id' in request.form:
        donor_id = request.form.get('donor_id')
        form_type = request.form.get('form_type')
        donor_record = db.query(Donor).filter(Donor.userId == donor_id).first()

        if donor_record:
            try:
                # OPTION A: Standard Cooldown Update
                if form_type == 'update_health':
                    new_last_donation_date = request.form.get('last_donation_date')
                    if new_last_donation_date:
                        new_date = date.fromisoformat(new_last_donation_date)
                        donor_record.lastDonationDate = new_date
                        # Recalculate based on the 56-day rule
                        donor_record.isEligible = is_eligible(new_date)
                        db.commit()
                        status_str = 'Eligible' if donor_record.isEligible else 'Ineligible'
                        flash(f"Cooldown updated for {donor_record.username}. Status: {status_str}", 'success')

                # OPTION B: Manual Status Toggle (The Override)
                elif form_type == 'manual_override':
                    # Simply flip the current boolean status
                    donor_record.isEligible = not donor_record.isEligible
                    db.commit()
                    status_str = 'Eligible' if donor_record.isEligible else 'Ineligible'
                    flash(f"Manual Override successful! {donor_record.username} is now {status_str}.", 'success')

                return redirect(url_for('donor.donor_dashboard'))

            except ValueError:
                db.rollback()
                flash("Invalid date format. Use YYYY-MM-DD.", 'error')
            except Exception as e:
                db.rollback()
                flash(f"Failed to update donor health: {str(e)}", 'error')
        else:
            flash(f"Donor ID {donor_id} not found.", 'error')

    # --- GET Request: Display Donor List (Correct Query) ---
    try:
        # This query is correct for fetching data using inheritance and joinedload
        donors = (
            db.query(Donor)
              .options(joinedload(User.contactInfo))
              .all()
        )
        
        donor_list = []
        for donor in donors:
            contact = donor.contactInfo
            
            donor_list.append({
                'userId': donor.userId,
                'username': donor.username,
                # This line MUST BE CORRECT for the attribute error to disappear
                'bloodType': donor.bloodType.name if donor.bloodType else 'N/A', 
                'email': contact.email if contact else 'N/A', 
                'lastDonation': donor.lastDonationDate.isoformat() if donor.lastDonationDate else 'N/A',
                'isEligible': donor.isEligible
            })
        
        blood_types = [bt.name for bt in BloodType]

        return render_template('donor_dashboard.html', donors=donor_list, blood_types=blood_types)

    except Exception as e:
        # If the AttributeError happens here, it confirms the DB SCHEMA IS BAD.
        flash(f"Error fetching donor list: 'Donor' object has no attribute 'bloodType'. Please run database migrations.", 'error')
        
        # Fallback render
        blood_types = [bt.name for bt in BloodType]
        return render_template('donor_dashboard.html', donors=[], blood_types=blood_types)
    finally:
        db.close()