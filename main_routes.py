# main_routes.py
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from databases import get_db
from models import User, Donor, ContactInfo, BloodType, LogAction, SCOPE_SYSTEM
from auth import login_required, verify_password, hash_password, write_audit
from sqlalchemy.exc import IntegrityError
from datetime import date
import uuid

main_bp = Blueprint('main', __name__)


@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get("user_id"):
        return redirect(url_for('main.home_dashboard'))

    blood_types = [bt.name for bt in BloodType]

    if request.method == 'POST':
        action = request.form.get('action', 'login')

        # ── Donor self-registration ─────────────────────────────────────
        if action == 'donor_register':
            username       = request.form.get('dr_username', '').strip()
            blood_type_str = request.form.get('dr_blood_type', '').strip()
            email          = request.form.get('dr_email', '').strip()
            phone          = request.form.get('dr_phone', '').strip()

            if not all([username, blood_type_str, email, phone]):
                flash("Name, blood type, email and phone are required.", 'error')
                return render_template('login.html', blood_types=blood_types, show_donor_form=True)

            db = next(get_db())
            try:
                bt = BloodType[blood_type_str]

                users   = db.query(User.userId).all()
                max_num = max((int(u[0][1:]) for u in users
                               if u[0].startswith('U') and u[0][1:].isdigit()), default=0)
                new_uid = f"U{max_num + 1:03d}"

                contacts = db.query(ContactInfo.contactId).all()
                max_cnum = max((int(c[0][1:]) for c in contacts
                                if c[0].startswith('C') and c[0][1:].isdigit()), default=0)
                new_cid  = f"C{max_cnum + 1:03d}"

                db.add(Donor(
                    userId=new_uid, username=username,
                    passwordHash='donor-no-login', user_type='donor',
                    timestamp=date.today(), bloodType=bt,
                    lastDonationDate=None, isEligible=True,
                ))
                db.flush()
                db.add(ContactInfo(contactId=new_cid, user_fk=new_uid, email=email, phone=phone))
                db.commit()
                flash(f"Thank you, {username}! Registered as donor (ID: {new_uid}).", 'success')
                return render_template('login.html', blood_types=blood_types)

            except KeyError:
                db.rollback(); flash("Invalid blood type.", 'error')
            except IntegrityError:
                db.rollback(); flash("Username already taken — please choose another.", 'error')
            except Exception as e:
                db.rollback(); flash(f"Registration error: {e}", 'error')
            finally:
                db.close()

            return render_template('login.html', blood_types=blood_types, show_donor_form=True)

        # ── Staff / hospital / admin login ──────────────────────────────
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not username or not password:
            flash("Username and password are required.", 'error')
            return render_template('login.html', blood_types=blood_types)

        db = next(get_db())
        try:
            user = db.query(User).filter(User.username == username).first()

            if user and user.user_type == 'donor':
                flash("Donors do not have system access. Use the registration panel →", 'warning')
                return render_template('login.html', blood_types=blood_types)

            if user and verify_password(password, user.passwordHash):
                session.clear()
                session['user_id']   = user.userId
                session['username']  = user.username
                session['user_type'] = user.user_type

                write_audit(db, LogAction.LOGIN,
                            f"{user.username} logged in from {request.remote_addr}.",
                            SCOPE_SYSTEM, None)
                db.commit()

                flash(f"Welcome back, {user.username}!", 'success')
                next_url = request.form.get('next') or url_for('main.home_dashboard')
                return redirect(next_url)
            else:
                flash("Invalid username or password.", 'error')
        finally:
            db.close()

    return render_template('login.html', blood_types=blood_types)


@main_bp.route('/logout')
def logout():
    db = next(get_db())
    try:
        if session.get("user_id"):
            write_audit(db, LogAction.LOGOUT,
                        f"{session.get('username')} logged out.",
                        SCOPE_SYSTEM, None)
            db.commit()
    finally:
        db.close()
    session.clear()
    flash("You have been logged out.", 'info')
    return redirect(url_for('main.login'))


@main_bp.route('/')
@login_required
def home_dashboard():
    role = session.get('user_type')
    if role in ('blood_bank_staff', 'admin'):
        return redirect(url_for('staff.dashboard'))
    elif role == 'hospital_admin':
        return redirect(url_for('hospital.dashboard'))
    return redirect(url_for('main.login'))
