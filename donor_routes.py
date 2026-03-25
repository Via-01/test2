# donor_routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from databases import get_db
from models import User, Donor, ContactInfo, BloodType
from donor_func import check_donor_eligibility   # single source of truth for eligibility
from auth import login_required, role_required
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload
from datetime import date
import uuid

donor_bp = Blueprint('donor', __name__, url_prefix='/donor')


def _build_donor_list(db) -> list:
    """Query all donors and return serialisable dicts."""
    donors = db.query(Donor).options(joinedload(User.contactInfo)).all()
    result = []
    for donor in donors:
        contact = donor.contactInfo
        result.append({
            'userId':       donor.userId,
            'username':     donor.username,
            'bloodType':    donor.bloodType.name if donor.bloodType else 'N/A',
            'email':        contact.email if contact else 'N/A',
            'phone':        contact.phone if contact else 'N/A',
            'lastDonation': donor.lastDonationDate.isoformat()
                            if donor.lastDonationDate else 'N/A',
            'isEligible':   donor.isEligible,
        })
    return result


# ---------------------------------------------------------------------------
# Donor dashboard — staff or hospital_admin can view; only staff can mutate
# ---------------------------------------------------------------------------

@donor_bp.route('/dashboard', methods=['GET'])
@login_required
def donor_dashboard():
    db = next(get_db())
    try:
        donor_list = _build_donor_list(db)
        blood_types = [bt.name for bt in BloodType]
        return render_template(
            'donor_dashboard.html',
            donors=donor_list,
            blood_types=blood_types,
            current_user_type=session.get('user_type'),
        )
    except Exception as e:
        flash(f"Error fetching donor list: {e}", 'error')
        return render_template('donor_dashboard.html', donors=[], blood_types=[])
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Register a new donor  (staff only)
# ---------------------------------------------------------------------------

@donor_bp.route('/register', methods=['POST'])
@role_required('blood_bank_staff')
def register_donor():
    username       = request.form.get('username', '').strip()
    blood_type_str = request.form.get('blood_type', '').strip()
    email          = request.form.get('email', '').strip()
    phone          = request.form.get('phone', '').strip()

    if not all([username, blood_type_str, email, phone]):
        flash("All registration fields are required.", 'error')
        return redirect(url_for('donor.donor_dashboard'))

    db = next(get_db())
    try:
        submitted_blood_type = BloodType[blood_type_str]

        new_donor = Donor(
            userId          = str(uuid.uuid4()),
            username        = username,
            passwordHash    = 'not-implemented',
            user_type       = 'donor',
            timestamp       = date.today(),
            bloodType       = submitted_blood_type,
            lastDonationDate= None,
            isEligible      = True,
        )
        db.add(new_donor)
        db.flush()  # make userId available before contact insert

        new_contact = ContactInfo(
            contactId = str(uuid.uuid4()),
            user_fk   = new_donor.userId,
            email     = email,
            phone     = phone,
        )
        db.add(new_contact)
        db.commit()
        flash(f"Donor '{username}' registered successfully ({submitted_blood_type.name}).", 'success')

    except KeyError:
        db.rollback()
        flash("Invalid blood type submitted.", 'error')
    except IntegrityError:
        db.rollback()
        flash("Username already exists or a database constraint was violated.", 'error')
    except Exception as e:
        db.rollback()
        flash(f"Unexpected error: {e}", 'error')
    finally:
        db.close()

    return redirect(url_for('donor.donor_dashboard'))


# ---------------------------------------------------------------------------
# Update donor health / eligibility  (staff only)
# ---------------------------------------------------------------------------

@donor_bp.route('/update_health', methods=['POST'])
@role_required('blood_bank_staff')
def update_donor_health():
    donor_id              = request.form.get('donor_id', '').strip()
    new_last_donation_str = request.form.get('last_donation_date', '').strip()

    if not donor_id:
        flash("Donor ID is required.", 'error')
        return redirect(url_for('donor.donor_dashboard'))

    db = next(get_db())
    try:
        donor_record = db.query(Donor).filter(Donor.userId == donor_id).first()
        if not donor_record:
            flash(f"Donor ID '{donor_id}' not found.", 'error')
            return redirect(url_for('donor.donor_dashboard'))

        if new_last_donation_str:
            new_date = date.fromisoformat(new_last_donation_str)
            donor_record.lastDonationDate = new_date

        # Recompute eligibility using the canonical function from donor_func
        donor_record.isEligible = check_donor_eligibility(donor_record)
        db.commit()

        status = "Eligible" if donor_record.isEligible else "Ineligible"
        flash(f"Health updated for {donor_record.username}. Status: {status}", 'success')

    except ValueError:
        db.rollback()
        flash("Invalid date format. Use YYYY-MM-DD.", 'error')
    except Exception as e:
        db.rollback()
        flash(f"Failed to update donor health: {e}", 'error')
    finally:
        db.close()

    return redirect(url_for('donor.donor_dashboard'))
