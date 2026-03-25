# staff_routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from databases import get_db
from models import (
    Donor, Donation, DonationStatus,
    Inventory, BloodBankUnit, BloodType,
    RequestStatus, BloodRequest,
)
from services import fulfill_blood_request, get_inventory_stock, match_to_eligible_donor
from auth import role_required
from sqlalchemy.exc import IntegrityError
from uuid import uuid4
from datetime import date

staff_bp = Blueprint('staff', __name__, url_prefix='/staff')

# All routes in this blueprint require the blood_bank_staff role.
# hospital_admin can submit requests and view history, but not record donations
# or perform fulfillment — those are staff-only actions.

STAFF_ROLES = ('blood_bank_staff',)
SHARED_ROLES = ('blood_bank_staff', 'hospital_admin')


# ---------------------------------------------------------------------------
# Donation recording  (staff only)
# ---------------------------------------------------------------------------

@staff_bp.route('/donation/new')
@role_required(*STAFF_ROLES)
def new_donation_form():
    blood_types      = [bt.name for bt in BloodType]
    donation_statuses = [ds.name for ds in DonationStatus]
    return render_template(
        'record_donation.html',
        title="Record New Donation",
        blood_types=blood_types,
        donation_statuses=donation_statuses,
    )


@staff_bp.route('/donation/record', methods=['POST'])
@role_required(*STAFF_ROLES)
def record_donation():
    db = next(get_db())
    try:
        donor_id_input = request.form.get('donor_id', '').strip()
        blood_type_str = request.form.get('blood_type', '').strip()
        status_str     = request.form.get('status', '').strip()
        unit_id        = request.form.get('unit_id', 'BBU001').strip()

        try:
            quantity = int(request.form.get('quantity', 0))
            if quantity <= 0:
                raise ValueError
        except (ValueError, TypeError):
            flash("Quantity must be a positive whole number.", 'error')
            return redirect(url_for('staff.new_donation_form'))

        try:
            donation_blood_type = BloodType[blood_type_str]
            donation_status     = DonationStatus[status_str]
        except KeyError as ke:
            flash(f"Invalid blood type or status: {ke}.", 'error')
            return redirect(url_for('staff.new_donation_form'))

        donor = db.query(Donor).filter(
            Donor.userId.startswith(donor_id_input)
        ).first()
        if not donor:
            flash(f"Donor ID '{donor_id_input}' not found.", 'error')
            return redirect(url_for('staff.new_donation_form'))

        new_donation = Donation(
            donationId = f"D{uuid4().hex[:6].upper()}",
            donorId    = donor.userId,
            date       = date.today(),
            quantity   = quantity,
            blood_type = donation_blood_type,
            status     = donation_status,
        )
        db.add(new_donation)

        if donation_status == DonationStatus.COMPLETE:
            donor.lastDonationDate = date.today()
            donor.isEligible       = False   # cooldown starts now

            inventory = db.query(Inventory).filter(
                Inventory.unitId     == unit_id,
                Inventory.blood_type == donation_blood_type,
            ).first()

            if inventory:
                inventory.unitsAvailable += quantity
                inventory.lastUpdated     = date.today()
            else:
                db.add(Inventory(
                    inventoryId    = f"I{uuid4().hex[:6].upper()}",
                    unitsAvailable = quantity,
                    lastUpdated    = date.today(),
                    minOrderAmt    = 10,
                    maxStorage     = 500.0,
                    unitId         = unit_id,
                    blood_type     = donation_blood_type,
                    component      = "WHOLE_BLOOD",
                ))

        db.commit()
        flash(f"Donation recorded for {donor.username}. Inventory updated.", 'success')
        return redirect(url_for('staff.new_donation_form'))

    except IntegrityError:
        db.rollback()
        flash("Database integrity error. Check unit ID and donor ID.", 'error')
    except Exception as e:
        db.rollback()
        flash(f"Unexpected error: {e}", 'error')
    finally:
        db.close()

    return redirect(url_for('staff.new_donation_form'))


# ---------------------------------------------------------------------------
# Blood request submission  (staff + hospital_admin)
# ---------------------------------------------------------------------------

@staff_bp.route('/request/new')
@role_required(*SHARED_ROLES)
def new_blood_request_form():
    blood_types = [bt.name for bt in BloodType]
    return render_template(
        'submit_request.html',
        title="Submit New Blood Request",
        blood_types=blood_types,
    )


@staff_bp.route('/request/submit', methods=['POST'])
@role_required(*SHARED_ROLES)
def submit_blood_request():
    db = next(get_db())
    try:
        hospital_id    = request.form.get('hospital_id', '').strip()
        requested_id   = request.form.get('requested_id', 'PATIENT_N/A').strip()
        blood_type_str = request.form.get('blood_type', '').strip()
        # HTML checkboxes send 'on' when ticked; nothing when unticked
        is_urgent      = request.form.get('is_urgent') in ('on', 'true', 'True', '1')

        try:
            quantity = int(request.form.get('quantity', 0))
            if quantity <= 0:
                raise ValueError
        except (ValueError, TypeError):
            flash("Quantity must be a positive number.", 'error')
            return redirect(url_for('staff.new_blood_request_form'))

        try:
            request_blood_type = BloodType[blood_type_str]
        except KeyError:
            flash(f"Invalid blood type: '{blood_type_str}'.", 'error')
            return redirect(url_for('staff.new_blood_request_form'))

        new_request = BloodRequest(
            requestId   = f"R{uuid4().hex[:6].upper()}",
            hospitalId  = hospital_id,
            requestedId = requested_id,
            quantity    = quantity,
            requestDate = date.today(),
            blood_type  = request_blood_type,
            isUrgent    = is_urgent,
            status      = RequestStatus.PENDING,
        )
        db.add(new_request)
        db.commit()
        flash(f"Blood request {new_request.requestId} submitted.", 'success')
        return redirect(url_for('staff.view_requests'))

    except Exception as e:
        db.rollback()
        flash(f"Error submitting request: {e}", 'error')
        return redirect(url_for('staff.new_blood_request_form'))
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Request views  (staff + hospital_admin)
# ---------------------------------------------------------------------------

@staff_bp.route('/requests')
@role_required(*SHARED_ROLES)
def view_requests():
    db = next(get_db())
    try:
        pending = db.query(BloodRequest).filter(
            BloodRequest.status == RequestStatus.PENDING
        ).order_by(BloodRequest.requestDate.desc()).all()

        request_list = [_serialize_request(r) for r in pending]
        return render_template(
            'view_requests.html',
            requests=request_list,
            title="Pending Blood Requests",
        )
    finally:
        db.close()


@staff_bp.route('/requests/all')
@role_required(*SHARED_ROLES)
def view_all_requests():
    db = next(get_db())
    try:
        all_requests = db.query(BloodRequest).order_by(
            BloodRequest.requestDate.desc()
        ).all()
        request_list = [_serialize_request(r, include_status=True) for r in all_requests]
        return render_template(
            'view_all_requests.html',
            requests=request_list,
            title="All Blood Request History",
        )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Request actions  (staff only)
# ---------------------------------------------------------------------------

@staff_bp.route('/request/fulfill/<req_id>')
@role_required(*STAFF_ROLES)
def handle_fulfill_request(req_id):
    db = next(get_db())
    try:
        success, message = fulfill_blood_request(db, req_id)
        flash(message, 'success' if success else 'error')
    except Exception as e:
        db.rollback()
        flash(f"Unexpected error during fulfillment: {e}", 'error')
    finally:
        db.close()
    return redirect(url_for('staff.view_requests'))


@staff_bp.route('/request/reject/<req_id>')
@role_required(*STAFF_ROLES)
def handle_reject_request(req_id):
    db = next(get_db())
    try:
        item = db.query(BloodRequest).filter(BloodRequest.requestId == req_id).first()
        if not item:
            flash(f"Request '{req_id}' not found.", 'error')
        elif item.status != RequestStatus.PENDING:
            flash(f"Request '{req_id}' is already {item.status.name}.", 'warning')
        else:
            item.status = RequestStatus.REJECTED
            db.commit()
            flash(f"Request '{req_id}' rejected.", 'success')
    except Exception as e:
        db.rollback()
        flash(f"Error rejecting request: {e}", 'error')
    finally:
        db.close()
    return redirect(url_for('staff.view_requests'))


@staff_bp.route('/request/verify/<req_id>')
@role_required(*STAFF_ROLES)
def handle_verify_fulfillment(req_id):
    db = next(get_db())
    try:
        item = db.query(BloodRequest).filter(BloodRequest.requestId == req_id).first()
        if not item:
            flash(f"Request '{req_id}' not found.", 'error')
            return redirect(url_for('staff.view_all_requests'))

        if item.status == RequestStatus.FULFILLED:

            from services import get_compatible_donor_types

            compatible_types = get_compatible_donor_types(item.blood_type)
            remaining = item.quantity

            for blood_type in compatible_types:
                if remaining <= 0:
                    break

                # 🔥 FIX: fetch ALL rows instead of one
                inventories = db.query(Inventory).filter(
                    Inventory.blood_type == blood_type
                ).all()

                for inv in inventories:
                    if remaining <= 0:
                        break

                    if inv.unitsAvailable > 0:
                        deduct = min(remaining, inv.unitsAvailable)
                        inv.unitsAvailable -= deduct
                        inv.lastUpdated = date.today()
                        remaining -= deduct

            item.status = RequestStatus.VERIFIED
            db.commit()
            flash(f"Request '{req_id}' verified and stock updated.", 'success')

        elif item.status == RequestStatus.PENDING:
            flash(f"Request '{req_id}' is still PENDING — fulfil it first.", 'warning')

        else:
            flash(f"Request '{req_id}' has status {item.status.name}. Cannot verify.", 'error')

    except Exception as e:
        db.rollback()
        flash(f"Error verifying request: {e}", 'error')
    finally:
        db.close()

    return redirect(url_for('staff.view_all_requests'))


@staff_bp.route('/request/match_donor/<request_id>')
@role_required(*STAFF_ROLES)
def match_donor_for_request(request_id):
    db = next(get_db())
    try:
        item = db.query(BloodRequest).filter(
            BloodRequest.requestId == request_id
        ).first()
        if not item:
            flash(f"Request '{request_id}' not found.", 'error')
            return redirect(url_for('staff.view_requests'))

        success, message = match_to_eligible_donor(db, item.blood_type)
        flash(message, 'success' if success else 'error')
    except Exception as e:
        flash(f"Internal error during donor matching: {e}", 'error')
    finally:
        db.close()
    return redirect(url_for('staff.view_requests'))


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _serialize_request(req, include_status: bool = False) -> dict:
    data = {
        "id":        req.requestId,
        "hospitalId":req.hospitalId,
        "bloodType": req.blood_type.name,
        "quantity":  req.quantity,
        "date":      req.requestDate.strftime("%Y-%m-%d"),
        "isUrgent":  "Yes" if req.isUrgent else "No",
    }
    if include_status:
        data["status"] = req.status.name
    return data