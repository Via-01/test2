# hospital_routes.py  — Hospital Admin portal (also used by admin)
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from databases import get_db
from models import (
    BloodRequest, BloodType, RequestStatus, HospitalUnit,
    Inventory, LogAction, AuditLog, HospitalAdmin, SCOPE_HOSPITAL,
)
from services import get_recommendations
from auth import role_required, write_audit
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from uuid import uuid4
from datetime import date

hospital_bp = Blueprint('hospital', __name__, url_prefix='/hospital')
HOSP = ('hospital_admin',)

def _get_my_hospital_id(db):
    if session.get('user_type') == 'admin':
        return None
    uid  = session.get('user_id')
    hadm = db.query(HospitalAdmin).filter(HospitalAdmin.userId == uid).first()
    return hadm.hospitalInitId if hadm else None

def _requests_query(db, hospital_id):
    q = db.query(BloodRequest)
    if hospital_id:
        q = q.filter(BloodRequest.hospitalId == hospital_id)
    return q

def _audit_query(db, hospital_id):
    q = (db.query(AuditLog).options(joinedload(AuditLog.user))
           .filter(AuditLog.scope_type == SCOPE_HOSPITAL))
    if hospital_id:
        q = q.filter(AuditLog.scope_id == hospital_id)
    return q.order_by(AuditLog.timestamp.desc())

def _ser_req(r, include_status=False):
    d = {'id': r.requestId, 'hospitalId': r.hospitalId,
         'bloodType': r.blood_type.name, 'quantity': r.quantity,
         'date': r.requestDate.strftime("%Y-%m-%d"), 'isUrgent': r.isUrgent,
         'targetBankId': r.targetBankId or '—'}
    if include_status:
        d['status'] = r.status.name
    return d

def _ser_log(l):
    return {
        'logId':     l.logId[:8],
        'username':  l.user.username  if l.user else 'system',
        'user_type': l.user.user_type if l.user else '—',
        'action':    l.type.name, 'details': l.details,
        'date':      l.timestamp.strftime("%Y-%m-%d %H:%M") if l.timestamp else '—',
        'scope_id':  l.scope_id or '—',
    }


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@hospital_bp.route('/dashboard')
@role_required(*HOSP)
def dashboard():
    db = next(get_db())
    try:
        h_id      = _get_my_hospital_id(db)
        pending   = _requests_query(db, h_id).filter(BloodRequest.status == RequestStatus.PENDING).count()
        fulfilled = _requests_query(db, h_id).filter(BloodRequest.status == RequestStatus.FULFILLED).count()
        verified  = _requests_query(db, h_id).filter(BloodRequest.status == RequestStatus.VERIFIED).count()
        rejected  = _requests_query(db, h_id).filter(BloodRequest.status == RequestStatus.REJECTED).count()
        recent    = (_requests_query(db, h_id)
                       .order_by(BloodRequest.status, BloodRequest.requestDate.desc()).limit(8).all())
        hosp_name = None
        if h_id:
            hu = db.query(HospitalUnit).filter(HospitalUnit.unitId == h_id).first()
            hosp_name = hu.name if hu else h_id
        return render_template('hospital/dashboard.html',
                               pending=pending, fulfilled=fulfilled, verified=verified, rejected=rejected,
                               recent=[_ser_req(r, True) for r in recent],
                               h_id=h_id, hosp_name=hosp_name)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# New request — hospital restricted to own unit; recommendations by distance+stock
# ---------------------------------------------------------------------------
@hospital_bp.route('/request/new', methods=['GET', 'POST'])
@role_required(*HOSP)
def new_request():
    blood_types     = [bt.name for bt in BloodType]
    recommendations = []
    submitted       = False
    last_req_id     = None

    db = next(get_db())
    try:
        h_id      = _get_my_hospital_id(db)
        # Hospital admin sees only their hospital; admin sees all
        all_hospitals = db.query(HospitalUnit).all()
        if h_id:
            hospitals = [hu for hu in all_hospitals if hu.unitId == h_id]
        else:
            hospitals = all_hospitals

        if request.method == 'POST':
            hospital_id    = h_id if h_id else request.form.get('hospital_id','').strip()
            requested_id   = request.form.get('requested_id', 'PATIENT_N/A').strip()
            blood_type_str = request.form.get('blood_type','').strip()
            is_urgent      = request.form.get('is_urgent') in ('on','true','1')
            target_bank_id = request.form.get('target_bank_id','').strip() or None

            try:
                quantity = int(request.form.get('quantity', 0))
                if quantity <= 0: raise ValueError
            except (ValueError, TypeError):
                flash("Quantity must be a positive number.", 'error')
                return render_template('hospital/new_request.html',
                                       blood_types=blood_types, hospitals=hospitals,
                                       recommendations=recommendations, submitted=submitted, h_id=h_id)
            try:
                bt = BloodType[blood_type_str]
            except KeyError:
                flash("Invalid blood type.", 'error')
                return render_template('hospital/new_request.html',
                                       blood_types=blood_types, hospitals=hospitals,
                                       recommendations=recommendations, submitted=submitted, h_id=h_id)

            # Get recommendations BEFORE saving (so user already saw them and chose)
            recommendations = get_recommendations(db, bt, quantity, hospital_id)

            new_req = BloodRequest(
                requestId=f"R{uuid4().hex[:6].upper()}",
                hospitalId=hospital_id, requestedId=requested_id,
                quantity=quantity, requestDate=date.today(),
                blood_type=bt, isUrgent=is_urgent, status=RequestStatus.PENDING,
                targetBankId=target_bank_id,
            )
            db.add(new_req)
            write_audit(db, LogAction.CREATE,
                        f"Request {new_req.requestId}: {bt.name} x{quantity} from {hospital_id}"
                        + (f" → target bank {target_bank_id}" if target_bank_id else "."),
                        SCOPE_HOSPITAL, h_id or hospital_id)
            db.commit()
            submitted   = True
            last_req_id = new_req.requestId
            flash(f"Request {new_req.requestId} submitted.", 'success')

        return render_template('hospital/new_request.html',
                               blood_types=blood_types, hospitals=hospitals,
                               recommendations=recommendations, submitted=submitted,
                               h_id=h_id, last_req_id=last_req_id)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# My requests (scoped + status grouped)
# ---------------------------------------------------------------------------
@hospital_bp.route('/requests')
@role_required(*HOSP)
def my_requests():
    status_filter = request.args.get('status', 'ALL')
    db = next(get_db())
    try:
        h_id = _get_my_hospital_id(db)
        # Admin: support ?hospital= filter
        filter_hosp = request.args.get('hospital', None) if not h_id else h_id
        q = _requests_query(db, filter_hosp)
        if status_filter != 'ALL':
            try:
                q = q.filter(BloodRequest.status == RequestStatus[status_filter])
            except KeyError:
                pass
        status_order = {RequestStatus.PENDING: 0, RequestStatus.FULFILLED: 1,
                        RequestStatus.VERIFIED: 2, RequestStatus.ACCEPTED: 3, RequestStatus.REJECTED: 4}
        reqs = q.order_by(BloodRequest.requestDate.desc()).all()
        reqs.sort(key=lambda r: (status_order.get(r.status, 9), not r.isUrgent))

        all_hospitals = None
        if not h_id:
            all_hospitals = [hu.unitId for hu in db.query(HospitalUnit).order_by(HospitalUnit.unitId).all()]

        return render_template('hospital/my_requests.html',
                               requests=[_ser_req(r, True) for r in reqs],
                               statuses=[s.name for s in RequestStatus],
                               current_status=status_filter,
                               h_id=h_id, filter_hosp=filter_hosp,
                               all_hospitals=all_hospitals)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Verify delivery
# ---------------------------------------------------------------------------
@hospital_bp.route('/request/verify/<req_id>')
@role_required(*HOSP)
def verify_request(req_id):
    db = next(get_db())
    try:
        h_id = _get_my_hospital_id(db)
        item = db.query(BloodRequest).filter(BloodRequest.requestId == req_id).first()
        if not item:
            flash(f"Request '{req_id}' not found.", 'error')
        elif h_id and item.hospitalId != h_id:
            flash("You can only verify your own hospital's requests.", 'error')
        elif item.status == RequestStatus.FULFILLED:
            item.status = RequestStatus.VERIFIED
            write_audit(db, LogAction.VERIFY, f"Delivery confirmed for {req_id}.",
                        SCOPE_HOSPITAL, h_id or item.hospitalId)
            db.commit()
            flash(f"Request '{req_id}' verified.", 'success')
        elif item.status == RequestStatus.VERIFIED:
            flash(f"Request '{req_id}' is already verified.", 'info')
        else:
            flash(f"Request '{req_id}' is {item.status.name} — cannot verify yet.", 'warning')
    except Exception as e:
        db.rollback(); flash(f"Error: {e}", 'error')
    finally:
        db.close()
    return redirect(url_for('hospital.my_requests'))


# ---------------------------------------------------------------------------
# Stock (read-only)
# ---------------------------------------------------------------------------
@hospital_bp.route('/stock')
@role_required(*HOSP)
def view_stock():
    db = next(get_db())
    try:
        items = (db.query(Inventory.blood_type,
                          func.sum(Inventory.unitsAvailable).label("totalUnits"),
                          func.max(Inventory.lastUpdated).label("lastUpdated"))
                   .group_by(Inventory.blood_type).all())
        stock = [{'bloodType': i.blood_type.name, 'unitsAvailable': i.totalUnits,
                  'lastUpdated': i.lastUpdated.strftime("%Y-%m-%d") if i.lastUpdated else "N/A"}
                 for i in items]
        return render_template('hospital/stock.html', inventory=stock)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Audit (scoped; admin can toggle by hospital)
# ---------------------------------------------------------------------------
@hospital_bp.route('/audit')
@role_required(*HOSP)
def audit_log():
    db = next(get_db())
    try:
        h_id        = _get_my_hospital_id(db)
        filter_hosp = request.args.get('hospital', None) if not h_id else h_id
        all_hospitals = None
        if not h_id:
            all_hospitals = [hu.unitId for hu in db.query(HospitalUnit).order_by(HospitalUnit.unitId).all()]
        logs = _audit_query(db, filter_hosp).limit(300).all()
        return render_template('hospital/audit.html', logs=[_ser_log(l) for l in logs],
                               h_id=h_id, filter_hosp=filter_hosp, all_hospitals=all_hospitals)
    finally:
        db.close()


@hospital_bp.route('/api/audit')
@role_required(*HOSP)
def api_audit():
    db = next(get_db())
    try:
        h_id        = _get_my_hospital_id(db)
        filter_hosp = request.args.get('hospital', None) if not h_id else h_id
        return jsonify([_ser_log(l) for l in _audit_query(db, filter_hosp).limit(100).all()])
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Report (scoped; admin can toggle by hospital)
# ---------------------------------------------------------------------------
@hospital_bp.route('/report')
@role_required(*HOSP)
def report():
    db = next(get_db())
    try:
        h_id        = _get_my_hospital_id(db)
        filter_hosp = request.args.get('hospital', None) if not h_id else h_id
        q = _requests_query(db, filter_hosp)

        by_status   = (q.with_entities(BloodRequest.status, func.count(BloodRequest.requestId).label('cnt'))
                        .group_by(BloodRequest.status).all())
        t_closed    = _requests_query(db, filter_hosp).filter(BloodRequest.status.in_([
            RequestStatus.FULFILLED, RequestStatus.VERIFIED, RequestStatus.REJECTED])).count()
        t_fulfilled = _requests_query(db, filter_hosp).filter(BloodRequest.status.in_([
            RequestStatus.FULFILLED, RequestStatus.VERIFIED])).count()
        rate = f"{t_fulfilled/t_closed*100:.1f}%" if t_closed else "N/A"

        by_urgency = (q.with_entities(BloodRequest.isUrgent, func.count(BloodRequest.requestId).label('cnt'))
                       .group_by(BloodRequest.isUrgent).all())
        by_blood   = (q.with_entities(BloodRequest.blood_type, func.count(BloodRequest.requestId).label('cnt'))
                       .group_by(BloodRequest.blood_type)
                       .order_by(func.count(BloodRequest.requestId).desc()).all())

        all_hospitals = None
        if not h_id:
            all_hospitals = [hu.unitId for hu in db.query(HospitalUnit).order_by(HospitalUnit.unitId).all()]

        hosp_label = filter_hosp or 'All Hospitals'
        data = {
            'report_date':      date.today().strftime("%Y-%m-%d"),
            'total_requests':   _requests_query(db, filter_hosp).count(),
            'fulfillment_rate': rate,
            'by_status':        [{'status': r.status.name, 'count': r.cnt} for r in by_status],
            'by_urgency':       [{'type': 'Urgent' if r.isUrgent else 'Normal', 'count': r.cnt} for r in by_urgency],
            'by_blood':         [{'blood_type': r.blood_type.name, 'count': r.cnt} for r in by_blood],
            'hosp_name':        hosp_label,
        }
        return render_template('hospital/report.html', data=data, h_id=h_id,
                               filter_hosp=filter_hosp, all_hospitals=all_hospitals)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Summary (scoped; admin can toggle)
# ---------------------------------------------------------------------------
@hospital_bp.route('/summary')
@role_required(*HOSP)
def summary():
    db = next(get_db())
    try:
        h_id        = _get_my_hospital_id(db)
        filter_hosp = request.args.get('hospital', None) if not h_id else h_id
        pending   = _requests_query(db, filter_hosp).filter(BloodRequest.status == RequestStatus.PENDING).count()
        fulfilled = _requests_query(db, filter_hosp).filter(BloodRequest.status == RequestStatus.FULFILLED).count()
        verified  = _requests_query(db, filter_hosp).filter(BloodRequest.status == RequestStatus.VERIFIED).count()
        rejected  = _requests_query(db, filter_hosp).filter(BloodRequest.status == RequestStatus.REJECTED).count()

        all_hospitals = None
        if not h_id:
            all_hospitals = [hu.unitId for hu in db.query(HospitalUnit).order_by(HospitalUnit.unitId).all()]

        return render_template('hospital/summary.html',
                               pending=pending, fulfilled=fulfilled, verified=verified,
                               rejected=rejected, total=pending+fulfilled+verified+rejected,
                               h_id=h_id, filter_hosp=filter_hosp, all_hospitals=all_hospitals,
                               hosp_label=filter_hosp or 'All Hospitals')
    finally:
        db.close()
