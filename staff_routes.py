# staff_routes.py  — Blood Bank Staff portal (also used by admin)
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from databases import get_db
from models import (
    Donor, Donation, DonationStatus, Inventory, BloodBankUnit, BloodType,
    RequestStatus, BloodRequest, AuditLog, LogAction, ContactInfo,
    BloodBankStaff, SCOPE_BLOODBANK,
)
from services import fulfill_blood_request, find_eligible_donors
from auth import role_required, write_audit
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from uuid import uuid4
from datetime import date, datetime

staff_bp = Blueprint('staff', __name__, url_prefix='/staff')
STAFF = ('blood_bank_staff',)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _get_my_unit_id(db):
    """Admin → None (all). Staff → assigned unitId."""
    if session.get('user_type') == 'admin':
        return None
    uid   = session.get('user_id')
    staff = db.query(BloodBankStaff).filter(BloodBankStaff.userId == uid).first()
    if staff and staff.unitId:
        return staff.unitId
    first = db.query(BloodBankUnit).first()
    return first.unitId if first else None

def _inventory_query(db, unit_id):
    q = db.query(Inventory)
    if unit_id:
        q = q.filter(Inventory.unitId == unit_id)
    return q.order_by(Inventory.blood_type, Inventory.unitId)

def _audit_query(db, unit_id):
    q = (db.query(AuditLog)
           .options(joinedload(AuditLog.user))
           .filter(AuditLog.scope_type == SCOPE_BLOODBANK))
    if unit_id:
        q = q.filter(AuditLog.scope_id == unit_id)
    return q.order_by(AuditLog.timestamp.desc())

def _ser_inv(i):
    return {
        'inventoryId':    i.inventoryId,
        'bloodType':      i.blood_type.name,
        'unitId':         i.unitId,
        'unitsAvailable': i.unitsAvailable,
        'minOrderAmt':    i.minOrderAmt,
        'lastUpdated':    i.lastUpdated.strftime("%Y-%m-%d") if i.lastUpdated else "N/A",
    }

def _ser_log(l):
    return {
        'logId':     l.logId[:8],
        'username':  l.user.username  if l.user else 'system',
        'user_type': l.user.user_type if l.user else '—',
        'action':    l.type.name,
        'details':   l.details,
        'date':      l.timestamp.strftime("%Y-%m-%d %H:%M") if l.timestamp else '—',
        'scope_id':  l.scope_id or '—',
    }

def _ser_req(r, include_status=False):
    d = {'id': r.requestId, 'hospitalId': r.hospitalId,
         'bloodType': r.blood_type.name, 'quantity': r.quantity,
         'date': r.requestDate.strftime("%Y-%m-%d"), 'isUrgent': r.isUrgent}
    if include_status:
        d['status'] = r.status.name
    return d

def _db_units():
    db = next(get_db())
    try:
        return db.query(BloodBankUnit).all()
    finally:
        db.close()

def _generate_uid(db):
    from models import User as U
    users   = db.query(U.userId).all()
    max_num = max((int(u[0][1:]) for u in users if u[0].startswith('U') and u[0][1:].isdigit()), default=0)
    return f"U{max_num + 1:03d}"

def _generate_cid(db):
    contacts = db.query(ContactInfo.contactId).all()
    max_num  = max((int(c[0][1:]) for c in contacts if c[0].startswith('C') and c[0][1:].isdigit()), default=0)
    return f"C{max_num + 1:03d}"


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@staff_bp.route('/dashboard')
@role_required(*STAFF)
def dashboard():
    db = next(get_db())
    try:
        my_unit = _get_my_unit_id(db)
        sq = db.query(func.sum(Inventory.unitsAvailable))
        if my_unit:
            sq = sq.filter(Inventory.unitId == my_unit)
        total_units       = sq.scalar() or 0
        pending_count     = db.query(func.count(BloodRequest.requestId)).filter(BloodRequest.status == RequestStatus.PENDING).scalar() or 0
        urgent_count      = db.query(func.count(BloodRequest.requestId)).filter(BloodRequest.status == RequestStatus.PENDING, BloodRequest.isUrgent == True).scalar() or 0
        fulfilled_waiting = db.query(func.count(BloodRequest.requestId)).filter(BloodRequest.status == RequestStatus.FULFILLED).scalar() or 0
        donor_count       = db.query(func.count(Donor.userId)).scalar() or 0
        recent_pending    = (db.query(BloodRequest)
                               .filter(BloodRequest.status == RequestStatus.PENDING)
                               .order_by(BloodRequest.isUrgent.desc(), BloodRequest.requestDate.asc())
                               .limit(8).all())
        fulfilled_list    = db.query(BloodRequest).filter(BloodRequest.status == RequestStatus.FULFILLED).order_by(BloodRequest.requestDate.desc()).all()
        unit_name = None
        if my_unit:
            u = db.query(BloodBankUnit).filter(BloodBankUnit.unitId == my_unit).first()
            unit_name = u.name if u else my_unit
        return render_template('staff/dashboard.html',
                               pending=pending_count, urgent=urgent_count,
                               total_units=total_units, donor_count=donor_count,
                               fulfilled_waiting=fulfilled_waiting,
                               recent=[_ser_req(r) for r in recent_pending],
                               fulfilled_list=[_ser_req(r, True) for r in fulfilled_list],
                               my_unit=my_unit, unit_name=unit_name)
    finally:
        db.close()


# JSON endpoint for fulfilled-pending real-time refresh
@staff_bp.route('/api/fulfilled')
@role_required(*STAFF)
def api_fulfilled():
    db = next(get_db())
    try:
        rows = db.query(BloodRequest).filter(BloodRequest.status == RequestStatus.FULFILLED).order_by(BloodRequest.requestDate.desc()).all()
        return jsonify([_ser_req(r, True) for r in rows])
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Donors
# ---------------------------------------------------------------------------
@staff_bp.route('/donors')
@role_required(*STAFF)
def donor_list():
    db = next(get_db())
    try:
        my_unit = _get_my_unit_id(db)
        donors  = db.query(Donor).options(joinedload(Donor.contactInfo)).all()
        rows = []
        for d in donors:
            c = d.contactInfo
            rows.append({'userId': d.userId, 'username': d.username,
                'bloodType':   d.bloodType.name if d.bloodType else 'N/A',
                'email':       c.email if c else 'N/A',
                'phone':       c.phone if c else 'N/A',
                'lastDonation':d.lastDonationDate.isoformat() if d.lastDonationDate else 'N/A',
                'isEligible':  d.isEligible})
        return render_template('staff/donors.html', donors=rows,
                               blood_types=[bt.name for bt in BloodType], my_unit=my_unit)
    finally:
        db.close()


@staff_bp.route('/donors/register', methods=['POST'])
@role_required(*STAFF)
def register_donor():
    from sqlalchemy.exc import IntegrityError
    username = request.form.get('username','').strip()
    bt_str   = request.form.get('blood_type','').strip()
    email    = request.form.get('email','').strip()
    phone    = request.form.get('phone','').strip()
    if not all([username, bt_str, email, phone]):
        flash("All fields are required.", 'error')
        return redirect(url_for('staff.donor_list'))
    db = next(get_db())
    try:
        my_unit = _get_my_unit_id(db)
        bt      = BloodType[bt_str]
        new_uid = _generate_uid(db)
        new_cid = _generate_cid(db)
        db.add(Donor(userId=new_uid, username=username, passwordHash='donor-no-login',
                     user_type='donor', timestamp=date.today(),
                     bloodType=bt, lastDonationDate=None, isEligible=True))
        db.flush()
        db.add(ContactInfo(contactId=new_cid, user_fk=new_uid, email=email, phone=phone))
        write_audit(db, LogAction.CREATE, f"Donor '{username}' ({bt.name}) registered.", SCOPE_BLOODBANK, my_unit)
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
    return redirect(url_for('staff.donor_list'))


@staff_bp.route('/donors/update_health', methods=['POST'])
@role_required(*STAFF)
def update_donor_health():
    from donor_func import check_donor_eligibility
    donor_id        = request.form.get('donor_id','').strip()
    new_date        = request.form.get('last_donation_date','').strip()
    manual_override = request.form.get('manual_override') == 'on'
    set_ineligible  = request.form.get('set_ineligible') == 'on'
    db = next(get_db())
    try:
        my_unit = _get_my_unit_id(db)
        donor   = db.query(Donor).filter(Donor.userId == donor_id).first()
        if not donor:
            flash(f"Donor '{donor_id}' not found.", 'error')
        else:
            if new_date:
                donor.lastDonationDate = date.fromisoformat(new_date)
            if manual_override:
                donor.isEligible = True
                write_audit(db, LogAction.UPDATE,
                            f"Manual override: donor {donor_id} set ELIGIBLE.", SCOPE_BLOODBANK, my_unit)
            elif set_ineligible:
                donor.isEligible = False
                write_audit(db, LogAction.UPDATE,
                            f"Manual override: donor {donor_id} set INELIGIBLE.", SCOPE_BLOODBANK, my_unit)
            else:
                donor.isEligible = check_donor_eligibility(donor)
                write_audit(db, LogAction.UPDATE,
                            f"Health updated donor {donor_id}. Eligible={donor.isEligible}", SCOPE_BLOODBANK, my_unit)
            db.commit()
            label = "ELIGIBLE (manual)" if manual_override else ("INELIGIBLE (manual)" if set_ineligible else str(donor.isEligible))
            flash(f"Updated {donor.username} → {label}", 'success')
    except ValueError:
        db.rollback(); flash("Invalid date format. Use YYYY-MM-DD.", 'error')
    except Exception as e:
        db.rollback(); flash(f"Error: {e}", 'error')
    finally:
        db.close()
    return redirect(url_for('staff.donor_list'))


# ---------------------------------------------------------------------------
# Record donation — unit restricted to staff's own unit (admin sees all)
# ---------------------------------------------------------------------------
@staff_bp.route('/donation/new', methods=['GET', 'POST'])
@role_required(*STAFF)
def record_donation():
    blood_types       = [bt.name for bt in BloodType]
    donation_statuses = [ds.name for ds in DonationStatus]
    db = next(get_db())
    try:
        my_unit  = _get_my_unit_id(db)
        # Staff only see their own unit; admin sees all
        if my_unit:
            db_units = [my_unit]
        else:
            db_units = [u.unitId for u in db.query(BloodBankUnit).all()]
    finally:
        db.close()

    if request.method == 'POST':
        donor_id_input = request.form.get('donor_id','').strip()
        bt_str         = request.form.get('blood_type','').strip()
        status_str     = request.form.get('status','').strip()
        unit_id        = request.form.get('unit_id','').strip()

        try:
            quantity = int(request.form.get('quantity', 0))
            if quantity <= 0: raise ValueError
        except (ValueError, TypeError):
            flash("Quantity must be a positive number.", 'error')
            return render_template('staff/record_donation.html',
                                   blood_types=blood_types, donation_statuses=donation_statuses,
                                   units=db_units, my_unit=my_unit)

        db = next(get_db())
        try:
            my_unit_db = _get_my_unit_id(db)
            # Enforce unit restriction for non-admin
            if my_unit_db and unit_id != my_unit_db:
                unit_id = my_unit_db
            if not unit_id:
                unit_id = my_unit_db or 'BBU000'

            bt     = BloodType[bt_str]
            status = DonationStatus[status_str]
            donor  = db.query(Donor).filter(Donor.userId.startswith(donor_id_input)).first()
            if not donor:
                flash(f"Donor '{donor_id_input}' not found.", 'error')
                return render_template('staff/record_donation.html',
                                       blood_types=blood_types, donation_statuses=donation_statuses,
                                       units=db_units, my_unit=my_unit)

            db.add(Donation(donationId=f"D{uuid4().hex[:6].upper()}", donorId=donor.userId,
                            date=date.today(), quantity=quantity, blood_type=bt, status=status))

            if status == DonationStatus.COMPLETE:
                donor.lastDonationDate = date.today()
                donor.isEligible       = False
                inv = db.query(Inventory).filter(Inventory.unitId == unit_id, Inventory.blood_type == bt).first()
                if inv:
                    inv.unitsAvailable += quantity; inv.lastUpdated = date.today()
                else:
                    db.add(Inventory(inventoryId=f"I{uuid4().hex[:6].upper()}",
                                     unitsAvailable=quantity, lastUpdated=date.today(),
                                     minOrderAmt=10, maxStorage=500.0,
                                     unitId=unit_id, blood_type=bt, component="WHOLE_BLOOD"))

            write_audit(db, LogAction.CREATE,
                        f"Donation: {donor.userId}, {quantity}u {bt_str} ({status_str}) → {unit_id}.",
                        SCOPE_BLOODBANK, my_unit_db)
            db.commit()
            flash(f"Donation recorded for {donor.username}.", 'success')
            return redirect(url_for('staff.record_donation'))
        except KeyError as e:
            db.rollback(); flash(f"Invalid selection: {e}", 'error')
        except Exception as e:
            db.rollback(); flash(f"Error: {e}", 'error')
        finally:
            db.close()

    return render_template('staff/record_donation.html',
                           blood_types=blood_types, donation_statuses=donation_statuses,
                           units=db_units, my_unit=my_unit)


# ---------------------------------------------------------------------------
# Blood requests
# ---------------------------------------------------------------------------
@staff_bp.route('/requests')
@role_required(*STAFF)
def all_requests():
    status_filter = request.args.get('status', 'PENDING')
    db = next(get_db())
    try:
        q = db.query(BloodRequest)
        if status_filter != 'ALL':
            try:
                q = q.filter(BloodRequest.status == RequestStatus[status_filter])
            except KeyError:
                pass
        reqs = q.order_by(BloodRequest.status, BloodRequest.isUrgent.desc(), BloodRequest.requestDate.asc()).all()
        return render_template('staff/requests.html',
                               requests=[_ser_req(r, True) for r in reqs],
                               statuses=[s.name for s in RequestStatus], current_status=status_filter)
    finally:
        db.close()


@staff_bp.route('/request/fulfill/<req_id>')
@role_required(*STAFF)
def handle_fulfill_request(req_id):
    db = next(get_db())
    try:
        my_unit = _get_my_unit_id(db)
        success, message = fulfill_blood_request(db, req_id)
        if success:
            write_audit(db, LogAction.FULFILL, f"Fulfilled request {req_id}.", SCOPE_BLOODBANK, my_unit)
            db.commit()
        flash(message, 'success' if success else 'error')
    except Exception as e:
        db.rollback(); flash(f"Error: {e}", 'error')
    finally:
        db.close()
    return redirect(url_for('staff.all_requests'))


@staff_bp.route('/request/reject/<req_id>')
@role_required(*STAFF)
def handle_reject_request(req_id):
    db = next(get_db())
    try:
        my_unit = _get_my_unit_id(db)
        item = db.query(BloodRequest).filter(BloodRequest.requestId == req_id).first()
        if not item:
            flash(f"Request '{req_id}' not found.", 'error')
        elif item.status != RequestStatus.PENDING:
            flash(f"Cannot reject — status is {item.status.name}.", 'warning')
        else:
            item.status = RequestStatus.REJECTED
            write_audit(db, LogAction.REJECT, f"Rejected request {req_id}.", SCOPE_BLOODBANK, my_unit)
            db.commit()
            flash(f"Request '{req_id}' rejected.", 'success')
    except Exception as e:
        db.rollback(); flash(f"Error: {e}", 'error')
    finally:
        db.close()
    return redirect(url_for('staff.all_requests'))


@staff_bp.route('/request/find_donors/<req_id>')
@role_required(*STAFF)
def find_donors_for_request(req_id):
    db = next(get_db())
    try:
        my_unit = _get_my_unit_id(db)
        req = db.query(BloodRequest).filter(BloodRequest.requestId == req_id).first()
        if not req:
            flash("Request not found.", 'error')
            return redirect(url_for('staff.all_requests'))
        donors = find_eligible_donors(db, req.blood_type)
        write_audit(db, LogAction.UPDATE, f"Donor search for request {req_id}.", SCOPE_BLOODBANK, my_unit)
        db.commit()
        return render_template('staff/find_donors.html', req=_ser_req(req, True), donors=donors)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------
@staff_bp.route('/inventory')
@role_required(*STAFF)
def inventory():
    db = next(get_db())
    try:
        my_unit           = _get_my_unit_id(db)
        items             = _inventory_query(db, my_unit).all()
        stock             = [_ser_inv(i) for i in items]
        fulfilled_pending = db.query(BloodRequest).filter(BloodRequest.status == RequestStatus.FULFILLED).all()
        all_units = None
        if not my_unit:  # admin: accordion by unit
            units_raw = db.query(BloodBankUnit).order_by(BloodBankUnit.unitId).all()
            all_units = []
            for u in units_raw:
                u_items = db.query(Inventory).filter(Inventory.unitId == u.unitId).all()
                all_units.append({
                    'unitId': u.unitId, 'name': u.name or u.unitId,
                    'total':  sum(i.unitsAvailable for i in u_items),
                    'rows':   [_ser_inv(i) for i in u_items],
                })
        return render_template('staff/inventory.html',
                               inventory=stock, my_unit=my_unit, all_units=all_units,
                               blood_types=[bt.name for bt in BloodType],
                               fulfilled_pending=fulfilled_pending)
    finally:
        db.close()


@staff_bp.route('/inventory/update', methods=['POST'])
@role_required(*STAFF)
def update_inventory():
    db = next(get_db())
    try:
        my_unit = _get_my_unit_id(db)
        inv_id  = request.form.get('inventory_id','').strip()
        try:
            delta = int(request.form.get('delta', 0))
        except (ValueError, TypeError):
            return jsonify({'ok': False, 'msg': 'Invalid number'}), 400
        item = db.query(Inventory).filter(Inventory.inventoryId == inv_id).first()
        if not item:
            return jsonify({'ok': False, 'msg': 'Record not found'}), 404
        # Enforce unit restriction for non-admin
        if my_unit and item.unitId != my_unit:
            return jsonify({'ok': False, 'msg': 'Not your unit'}), 403
        new_val = item.unitsAvailable + delta
        if new_val < 0:
            return jsonify({'ok': False, 'msg': f'Cannot subtract {abs(delta)} — only {item.unitsAvailable} available'}), 400
        item.unitsAvailable = new_val
        item.lastUpdated    = date.today()
        write_audit(db, LogAction.UPDATE,
                    f"Inventory {inv_id} ({item.blood_type.name} @ {item.unitId}) {delta:+d} → {new_val}.",
                    SCOPE_BLOODBANK, my_unit or item.unitId)
        db.commit()
        return jsonify({'ok': True, 'new_val': new_val, 'msg': f'Updated to {new_val} units', 'inv_id': inv_id})
    except Exception as e:
        db.rollback()
        return jsonify({'ok': False, 'msg': str(e)}), 500
    finally:
        db.close()


@staff_bp.route('/api/inventory')
@role_required(*STAFF)
def api_inventory():
    db = next(get_db())
    try:
        my_unit = _get_my_unit_id(db)
        return jsonify([_ser_inv(i) for i in _inventory_query(db, my_unit).all()])
    finally:
        db.close()


@staff_bp.route('/api/audit')
@role_required(*STAFF)
def api_audit():
    db = next(get_db())
    try:
        my_unit = _get_my_unit_id(db)
        return jsonify([_ser_log(l) for l in _audit_query(db, my_unit).limit(150).all()])
    finally:
        db.close()


@staff_bp.route('/audit')
@role_required(*STAFF)
def audit_log():
    db = next(get_db())
    try:
        my_unit = _get_my_unit_id(db)
        # Admin: support ?unit= filter
        filter_unit = request.args.get('unit', None) if not my_unit else my_unit
        all_bank_units = None
        if not my_unit:
            all_bank_units = [u.unitId for u in db.query(BloodBankUnit).order_by(BloodBankUnit.unitId).all()]
        logs = _audit_query(db, filter_unit).limit(300).all()
        return render_template('staff/audit.html', logs=[_ser_log(l) for l in logs],
                               my_unit=my_unit, filter_unit=filter_unit,
                               all_bank_units=all_bank_units)
    finally:
        db.close()


@staff_bp.route('/report')
@role_required(*STAFF)
def report():
    from datetime import timedelta
    db = next(get_db())
    try:
        my_unit     = _get_my_unit_id(db)
        filter_unit = request.args.get('unit', None) if not my_unit else my_unit
        last30      = date.today() - timedelta(days=30)

        inv_q = db.query(Inventory.blood_type, func.sum(Inventory.unitsAvailable).label('total'))
        if filter_unit:
            inv_q = inv_q.filter(Inventory.unitId == filter_unit)
        inv_summary = inv_q.group_by(Inventory.blood_type).all()

        don_volume = (db.query(Donation.blood_type, func.count(Donation.donationId).label('cnt'),
                               func.sum(Donation.quantity).label('qty'))
                       .filter(Donation.date >= last30, Donation.status == DonationStatus.COMPLETE)
                       .group_by(Donation.blood_type).all())

        don_status = (db.query(Donation.status, func.count(Donation.donationId).label('cnt'))
                       .filter(Donation.date >= last30).group_by(Donation.status).all())

        total_q = db.query(func.sum(Inventory.unitsAvailable))
        if filter_unit:
            total_q = total_q.filter(Inventory.unitId == filter_unit)

        all_bank_units = None
        if not my_unit:
            all_bank_units = [u.unitId for u in db.query(BloodBankUnit).order_by(BloodBankUnit.unitId).all()]

        unit_label = filter_unit or 'All Blood Banks'
        data = {
            'report_date':     date.today().strftime("%Y-%m-%d"),
            'period':          f"Last 30 days (since {last30.strftime('%Y-%m-%d')})",
            'total_donors':    db.query(func.count(Donor.userId)).scalar() or 0,
            'eligible_donors': db.query(func.count(Donor.userId)).filter(Donor.isEligible == True).scalar() or 0,
            'inv_summary':     [{'bloodType': r.blood_type.name, 'total': r.total} for r in inv_summary],
            'don_volume':      [{'bloodType': r.blood_type.name, 'count': r.cnt, 'qty': r.qty or 0} for r in don_volume],
            'don_status':      [{'status': r.status.name, 'count': r.cnt} for r in don_status],
            'total_stock':     total_q.scalar() or 0,
            'unit_label':      unit_label,
        }
        return render_template('staff/report.html', data=data, my_unit=my_unit,
                               filter_unit=filter_unit, all_bank_units=all_bank_units)
    finally:
        db.close()


@staff_bp.route('/summary')
@role_required(*STAFF)
def summary():
    db = next(get_db())
    try:
        my_unit     = _get_my_unit_id(db)
        filter_unit = request.args.get('unit', None) if not my_unit else my_unit

        sq = db.query(func.sum(Inventory.unitsAvailable))
        if filter_unit:
            sq = sq.filter(Inventory.unitId == filter_unit)
        total_stock = sq.scalar() or 0

        pending     = db.query(func.count(BloodRequest.requestId)).filter(BloodRequest.status == RequestStatus.PENDING).scalar() or 0
        fulfilled_w = db.query(func.count(BloodRequest.requestId)).filter(BloodRequest.status == RequestStatus.FULFILLED).scalar() or 0
        total_donors= db.query(func.count(Donor.userId)).scalar() or 0
        eligible    = db.query(func.count(Donor.userId)).filter(Donor.isEligible == True).scalar() or 0
        lq = db.query(Inventory).filter(Inventory.unitsAvailable < Inventory.minOrderAmt)
        if filter_unit:
            lq = lq.filter(Inventory.unitId == filter_unit)
        low_stock = lq.all()

        all_bank_units = None
        if not my_unit:
            all_bank_units = [u.unitId for u in db.query(BloodBankUnit).order_by(BloodBankUnit.unitId).all()]

        return render_template('staff/summary.html',
                               total_stock=total_stock, pending=pending,
                               fulfilled_waiting=fulfilled_w, total_donors=total_donors,
                               eligible=eligible, low_stock=low_stock,
                               my_unit=my_unit, filter_unit=filter_unit,
                               all_bank_units=all_bank_units,
                               now=date.today().strftime("%Y-%m-%d"))
    finally:
        db.close()
