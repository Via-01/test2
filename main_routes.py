# main_routes.py
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from databases import get_db
from models import Donor, ContactInfo, User
from auth import login_required, verify_password

main_bp = Blueprint('main', __name__)


# ---------------------------------------------------------------------------
# Login / Logout
# ---------------------------------------------------------------------------

@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Authenticate any user type and store role in session."""
    if session.get("user_id"):
        return redirect(url_for('main.home_dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            flash("Username and password are required.", 'error')
            return render_template('login.html', title='Login')

        db = next(get_db())
        try:
            user = db.query(User).filter(User.username == username).first()
            if user and verify_password(password, user.passwordHash):
                session.clear()
                session['user_id']   = user.userId
                session['username']  = user.username
                session['user_type'] = user.user_type
                flash(f"Welcome back, {user.username}!", 'success')
                next_url = request.form.get('next') or url_for('main.home_dashboard')
                return redirect(next_url)
            else:
                flash("Invalid username or password.", 'error')
        finally:
            db.close()

    return render_template('login.html', title='Login')


@main_bp.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", 'info')
    return redirect(url_for('main.login'))


# ---------------------------------------------------------------------------
# Dashboard (requires login — any role)
# ---------------------------------------------------------------------------

@main_bp.route('/')
@login_required
def home_dashboard():
    db = next(get_db())
    try:
        donors = db.query(Donor).all()
        donor_list = []
        for donor in donors:
            contact = db.query(ContactInfo).filter(
                ContactInfo.user_fk == donor.userId
            ).first()
            donor_list.append({
                "username":     donor.username,
                "userId":       donor.userId[:7],
                "bloodType":    donor.bloodType.name if donor.bloodType else "N/A",
                "email":        contact.email if contact else "N/A",
                "phone":        contact.phone if contact else "N/A",
                "lastDonation": donor.lastDonationDate.strftime("%Y-%m-%d")
                                if donor.lastDonationDate else "N/A",
                "isEligible":   "Eligible" if donor.isEligible else "Ineligible",
            })

        return render_template(
            'index.html',
            title='LifeLink Dashboard',
            donors=donor_list,
            current_user_type=session.get('user_type'),
            success=request.args.get('success'),
            error=request.args.get('error'),
        )
    finally:
        db.close()
