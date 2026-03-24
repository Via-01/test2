# staff_routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from databases import get_db 
from models import Donor, Donation, DonationStatus, Inventory, BloodBankUnit, BloodType, RequestStatus, BloodRequest
# Assuming these services exist in 'services.py'
from services import fulfill_blood_request, get_inventory_stock, match_to_eligible_donor 
from uuid import uuid4
from datetime import date 
from sqlalchemy.exc import IntegrityError 

staff_bp = Blueprint('staff', __name__, url_prefix='/staff')

# --- 1. Donation Management Routes (Input) ---

@staff_bp.route('/donation/new')
def new_donation_form():
    """Renders the form for staff to record a new donation."""
    # NOTE: In a complete app, you would pass BloodType and DonationStatus enums here
    return render_template('record_donation.html', title="Record New Donation")

@staff_bp.route('/donation/record', methods=['GET','POST'])
def record_donation():
    """
    Records a new Donation, updates the Donor's last donation date, and updates Inventory.
    """
    db = next(get_db())
    try:
        donor_id_input = request.form.get('donor_id').strip()
        
        # Input validation for Quantity
        try:
            quantity = int(request.form.get('quantity'))
        except (ValueError, TypeError):
            flash("Invalid quantity value. Please enter a whole number.", 'error')
            return redirect(url_for('staff.new_donation_form'))

        blood_type_str = request.form.get('blood_type')
        status_str = request.form.get('status')
        # Placeholder Unit ID - should be dynamic in production
        unit_id = request.form.get('unit_id', 'BBU001') 

        # Enum validation
        try:
            donation_blood_type = BloodType[blood_type_str]
            donation_status = DonationStatus[status_str]
        except KeyError as ke:
            flash(f"Invalid Blood Type or Status name submitted: '{ke}'. Check capitalization and format.", 'error')
            return redirect(url_for('staff.new_donation_form'))
        
        # Find Donor by partial ID match (assuming userId is unique)
        donor = db.query(Donor).filter(Donor.userId.startswith(donor_id_input)).first()
        
        if not donor:
            flash(f"Donor ID {donor_id_input} not found.", 'error')
            return redirect(url_for('staff.new_donation_form'))

        full_donor_id = donor.userId
        
        # Create new Donation record
        new_donation = Donation(
            donationId=f"D{uuid4().hex[:6].upper()}",
            donorId=full_donor_id, 
            date=date.today(),
            quantity=quantity,
            blood_type=donation_blood_type,
            status=donation_status
        )
        db.add(new_donation)
        
        if donation_status == DonationStatus.COMPLETE:
            # 1. Update donor's last donation date and eligibility flag (start cooldown)
            donor.lastDonationDate = date.today()
            donor.isEligible = False 
            
            # 2. Update Inventory
            inventory = db.query(Inventory).filter(
                Inventory.unitId == unit_id,
                Inventory.blood_type == donation_blood_type
            ).first()

            if inventory:
                inventory.unitsAvailable += quantity
            else:
                # Create new inventory record if none exists for this type/unit
                new_inventory = Inventory(
                    inventoryId=f"I{uuid4().hex[:6].upper()}",
                    unitsAvailable=quantity,
                    lastUpdated=date.today(),
                    minOrderAmt=10, 
                    maxStorage=500.0, 
                    unitId=unit_id,
                    blood_type=donation_blood_type,
                    component="WHOLE_BLOOD" 
                )
                db.add(new_inventory)
        
        db.commit()

        flash(f"Donation recorded successfully for ID: {full_donor_id}. Inventory updated.", 'success')
        return redirect(url_for('staff.new_donation_form'))

    except IntegrityError:
        db.rollback()
        flash("Database integrity error. Check if the unit ID or donor ID is valid.", 'error')
        return redirect(url_for('staff.new_donation_form'))
    except Exception as e:
        db.rollback()
        print(f"Error recording donation: {e}")
        flash(f"An unexpected internal error occurred: {e}", 'error')
        return redirect(url_for('staff.new_donation_form'))
    finally:
        db.close()

# --- 2. Request Management Routes (Distribution) ---

@staff_bp.route('/request/new')
def new_blood_request_form():
    """Renders the form for staff/hospital admin to submit a blood request. (Endpoint: staff.new_blood_request_form)"""
    return render_template('submit_request.html', title="Submit New Request")


@staff_bp.route('/request/submit', methods=['POST'])
def submit_blood_request():
    """Creates a new BloodRequest record with PENDING status. (Endpoint: staff.submit_blood_request)"""
    db = next(get_db())
    try:
        hospital_id = request.form.get('hospital_id')
        requested_id = request.form.get('requested_id', 'PATIENT_N/A')
        
        try:
            quantity = int(request.form.get('quantity'))
        except (ValueError, TypeError):
            flash("Invalid quantity value. Please enter a number.", 'error')
            return redirect(url_for('staff.new_blood_request_form'))

        blood_type_str = request.form.get('blood_type')
        # Checkbox values are typically 'on'/'True' or None/False
        is_urgent = request.form.get('is_urgent') == 'True' 
        
        try:
            request_blood_type = BloodType[blood_type_str]
        except KeyError as ke:
            flash(f"Invalid Blood Type submitted: '{ke}'.", 'error')
            return redirect(url_for('staff.new_blood_request_form'))

        new_request = BloodRequest(
            requestId=f"R{uuid4().hex[:6].upper()}",
            hospitalId=hospital_id,
            requestedId=requested_id,
            quantity=quantity,
            requestDate=date.today(),
            blood_type=request_blood_type,
            isUrgent=is_urgent,
            status=RequestStatus.PENDING
        )
        db.add(new_request)
        db.commit()

        flash(f"Blood request {new_request.requestId} submitted successfully!", 'success')
        # Redirect to the view requests page after submission
        return redirect(url_for('staff.view_requests')) 

    except Exception as e:
        db.rollback()
        print(f"Error submitting request: {e}")
        flash(f"An error occurred while submitting the request: {e}", 'error')
        return redirect(url_for('staff.new_blood_request_form'))
    finally:
        db.close()

# --- 2a. View Pending Requests (Primary Staff Dashboard View) ---

@staff_bp.route('/requests')
def view_requests():
    """Renders the dashboard showing all PENDING blood requests. (Endpoint: staff.view_requests)"""
    db = next(get_db())
    try:
        # Filter: Only show PENDING requests
        requests = db.query(BloodRequest).filter(BloodRequest.status == RequestStatus.PENDING).all()

        request_list = []
        for req in requests:
            request_list.append({
                "id": req.requestId,
                "hospitalId": req.hospitalId,
                "bloodType": req.blood_type.name,
                "quantity": req.quantity,
                "date": req.requestDate.strftime("%Y-%m-%d"),
                "isUrgent": "Yes" if req.isUrgent else "No"
            })

        return render_template('view_requests.html', requests=request_list, title="Pending Blood Requests")

    finally:
        db.close()

# --- 2b. View ALL Requests (Function #14: History) ---

@staff_bp.route('/requests/all')
def view_all_requests():
    """
    Function #14: Renders the dashboard showing ALL blood requests 
    (Pending, Fulfilled, Rejected, Verified). (Endpoint: staff.view_all_requests)
    """
    db = next(get_db())
    try:
        # Fetch ALL requests (no filter)
        requests = db.query(BloodRequest).all()

        request_list = []
        for req in requests:
            request_list.append({
                "id": req.requestId,
                "hospitalId": req.hospitalId,
                "bloodType": req.blood_type.name,
                "quantity": req.quantity,
                "date": req.requestDate.strftime("%Y-%m-%d"),
                "isUrgent": "Yes" if req.isUrgent else "No",
                "status": req.status.name 
            })

        return render_template('view_all_requests.html', requests=request_list, title="All Blood Request History")

    finally:
        db.close()


# --- 2c. Action Routes ---

@staff_bp.route('/request/fulfill/<id>')
def handle_fulfill_request(id):
    """Triggers the matching service to attempt fulfilling the request (Function #16)."""
    db = next(get_db())
    try:
        # The fulfill_blood_request service is expected to handle core logic, 
        # inventory deduction, status update, and DB commit/rollback if needed.
        success, message = fulfill_blood_request(db, id) 

        if success:
            flash(message, 'success')
        else:
            flash(message, 'error')
            
        # Redirect back to the pending requests view
        return redirect(url_for('staff.view_requests'))

    except Exception as e:
        db.rollback() 
        print(f"Error fulfilling request {id}: {e}")
        flash(f"An unexpected error occurred during fulfillment: {e}", 'error')
        return redirect(url_for('staff.view_requests'))
    finally:
        db.close()


@staff_bp.route('/request/reject/<id>')
def handle_reject_request(id):
    """
    Function #7 (Reject): Explicitly rejects a PENDING blood request.
    """
    db = next(get_db())
    try:
        request_item = db.query(BloodRequest).filter(BloodRequest.requestId == id).first()
        
        if not request_item:
            flash(f"Request {id} not found.", 'error')
            return redirect(url_for('staff.view_requests'))
            
        if request_item.status != RequestStatus.PENDING:
            flash(f"Request {id} is already {request_item.status.name}. Cannot reject.", 'warning')
            return redirect(url_for('staff.view_requests'))

        request_item.status = RequestStatus.REJECTED 
        db.commit()

        flash(f"Blood Request {id} successfully **REJECTED**.", 'success')
        return redirect(url_for('staff.view_requests'))

    except Exception as e:
        db.rollback()
        print(f"Error rejecting request {id}: {e}")
        flash(f"An error occurred rejecting request: {e}", 'error')
        return redirect(url_for('staff.view_requests'))
    finally:
        db.close()


@staff_bp.route('/request/verify/<id>')
def handle_verify_fulfillment(id):
    """
    Function #17: Marks a FULFILLED request as VERIFIED/CLOSED.
    """
    db = next(get_db())
    try:
        request_item = db.query(BloodRequest).filter(BloodRequest.requestId == id).first()
        
        if not request_item:
            flash(f"Request {id} not found.", 'error')
            return redirect(url_for('staff.view_all_requests'))
            
        if request_item.status == RequestStatus.FULFILLED:
            request_item.status = RequestStatus.VERIFIED 
            db.commit()
            flash(f"Blood Request {id} successfully **VERIFIED** and closed.", 'success')
            return redirect(url_for('staff.view_all_requests'))
        
        elif request_item.status == RequestStatus.PENDING:
            flash(f"Request {id} is PENDING. Fulfill it first.", 'warning')
            return redirect(url_for('staff.view_requests'))

        else:
            flash(f"Request {id} has status {request_item.status.name}. Cannot verify.", 'error')
            return redirect(url_for('staff.view_all_requests'))

    except Exception as e:
        db.rollback()
        print(f"Error verifying request {id}: {e}")
        flash(f"An error occurred verifying request: {e}", 'error')
        return redirect(url_for('staff.view_all_requests'))
    finally:
        db.close()


@staff_bp.route('/request/match_donor/<request_id>')
def match_donor_for_request(request_id):
    """
    Function #16: Finds an eligible donor for a specific request's blood type.
    """
    db = next(get_db())
    try:
        request_item = db.query(BloodRequest).filter(BloodRequest.requestId == request_id).first()
        
        if not request_item:
            flash(f"Request {request_id} not found.", 'error')
            return redirect(url_for('staff.view_requests'))
            
        requested_type = request_item.blood_type
        
        # Calls external service to find match
        success, message = match_to_eligible_donor(db, requested_type)
        
        if success:
            flash(message, 'success')
        else:
            flash(f"Donor Match Failed: {message}", 'error')
            
        return redirect(url_for('staff.view_requests'))
            
    except Exception as e:
        print(f"Error matching donor for request {request_id}: {e}")
        flash("An internal error occurred during donor matching.", 'error')
        return redirect(url_for('staff.view_requests'))
    finally:
        db.close()