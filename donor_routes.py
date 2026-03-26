# donor_routes.py
# Backup staff registration for walk-in donors.
# Donor self-registration is handled on the login page (main_routes.py).
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from databases import get_db
from models import Donor, ContactInfo, BloodType, LogAction, BloodBankStaff, SCOPE_BLOODBANK
from auth import role_required, write_audit
from sqlalchemy.exc import IntegrityError
from datetime import date

donor_bp = Blueprint('donor', __name__, url_prefix='/donor')


@donor_bp.route('/register', methods=['GET', 'POST'])
@role_required('blood_bank_staff')
def register():
    blood_types = [bt.name for bt in BloodType]

    if request.method == 'POST':
        username       = request.form.get('username', '').strip()
        blood_type_str = request.form.get('blood_type', '').strip()
        email          = request.form.get('email', '').strip()
        phone          = request.form.get('phone', '').strip()

        if not all([username, blood_type_str, email, phone]):
            flash("All fields are required.", 'error')
            return render_template('donor_register.html', blood_types=blood_types)

        db = next(get_db())
        try:
            # resolve staff's unit for audit scope
            uid = session.get('user_id')
            staff = db.query(BloodBankStaff).filter(BloodBankStaff.userId == uid).first()
            my_unit = staff.unitId if staff else None

            from models import User
            users    = db.query(User.userId).all()
            max_num  = max((int(u[0][1:]) for u in users if u[0].startswith('U') and u[0][1:].isdigit()), default=0)
            new_uid  = f"U{max_num + 1:03d}"

            contacts = db.query(ContactInfo.contactId).all()
            max_cnum = max((int(c[0][1:]) for c in contacts if c[0].startswith('C') and c[0][1:].isdigit()), default=0)
            new_cid  = f"C{max_cnum + 1:03d}"

            bt = BloodType[blood_type_str]
            db.add(Donor(userId=new_uid, username=username, passwordHash='donor-no-login',
                         user_type='donor', timestamp=date.today(),
                         bloodType=bt, lastDonationDate=None, isEligible=True))
            db.flush()
            db.add(ContactInfo(contactId=new_cid, user_fk=new_uid, email=email, phone=phone))
            write_audit(db, LogAction.CREATE,
                        f"Donor '{username}' ({bt.name}) registered via staff backup route.",
                        SCOPE_BLOODBANK, my_unit)
            db.commit()
            flash(f"Donor '{username}' registered (ID: {new_uid}).", 'success')

        except KeyError:
            db.rollback(); flash("Invalid blood type.", 'error')
        except IntegrityError:
            db.rollback(); flash("Username already exists.", 'error')
        except Exception as e:
            db.rollback(); flash(f"Error: {e}", 'error')
        finally:
            db.close()

    return render_template('donor_register.html', blood_types=blood_types)
