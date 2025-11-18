# staff_routes.py
from flask import Blueprint, render_template, request, redirect, url_for
from databases import get_db 
from models import Donor, Donation, DonationStatus, Inventory, BloodBankUnit, BloodType, RequestStatus, BloodRequest
from services import fulfill_blood_request, get_inventory_stock, match_to_eligible_donor
from donor_func import update_donor_eligibility_status
from uuid import uuid4
from datetime import date 

staff_bp = Blueprint('staff', __name__, url_prefix='/staff')

# --- 1. Donation Management Routes (Input) ---

@staff_bp.route('/donation/new')
def new_donation_form():
    """Renders the form for staff to record a new donation."""
    return render_template('record_donation.html', title="Record New Donation")

@staff_bp.route('/donation/record', methods=['POST'])
def record_donation():
    """
    Records a new Donation, updates the Donor's last donation date, and updates Inventory.
    Uses a partial match (startswith) for the Donor ID lookup.
    """
    db = next(get_db())
    try:
        # 1. Get Form Data
        # Get the short ID input by staff (e.g., 'UA46ACC')
        donor_id_input = request.form.get('donor_id').strip()
        
        try:
            quantity = int(request.form.get('quantity'))
        except ValueError:
            return render_template('record_donation.html', error="Invalid quantity.", title="Record Donation")
            
        blood_type_str = request.form.get('blood_type')
        status_str = request.form.get('status')
        unit_id = request.form.get('unit_id', 'BBU001')

        # 2. Find Donor using a partial match (startswith)
        # This allows the use of the 7-character ID to find the full UUID in the database.
        donor = db.query(Donor).filter(Donor.userId.startswith(donor_id_input)).first()
        
        if not donor:
            # Report the error with the ID used in the search
            return render_template('record_donation.html', error=f"Donor ID {donor_id_input} not found.", title="Record Donation")

        # Use the FULL donor ID from the database for the Donation record
        full_donor_id = donor.userId
        
        donation_blood_type = BloodType[blood_type_str]
        donation_status = DonationStatus[status_str]

        # 3. Create New Donation Record
        new_donation = Donation(
            donationId=f"D{uuid4().hex[:6].upper()}",
            donorId=full_donor_id, # Use the full ID here
            date=date.today(),
            quantity=quantity,
            blood_type=donation_blood_type,
            status=donation_status
        )
        db.add(new_donation)
        
        # 4. Update Donor and Inventory (ONLY if status is COMPLETE)
        if donation_status == DonationStatus.COMPLETE:
            donor.lastDonationDate = date.today()
            donor.isEligible = False 
            
            # 5. Update Inventory 
            inventory = db.query(Inventory).filter(
                Inventory.unitId == unit_id,
                Inventory.blood_type == donation_blood_type
            ).first()

            if inventory:
                inventory.unitsAvailable += quantity
            else:
                # Add new inventory record if none exists
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

        return redirect(url_for('staff.new_donation_form', success=f"Donation recorded successfully for ID: {donor_id_input} and donor eligibility updated."))

    except Exception as e:
        db.rollback()
        print(f"Error recording donation: {e}")
        return render_template('record_donation.html', error=f"An error occurred: {e}", title="Record Donation")
    finally:
        db.close()

# --- 2. Request Management Routes (Distribution) ---

@staff_bp.route('/request/new')
def new_blood_request_form():
    """Renders the form for staff/hospital admin to submit a blood request."""
    return render_template('submit_request.html', title="Submit New Request")


@staff_bp.route('/request/submit', methods=['POST'])
def submit_blood_request():
    """Creates a new BloodRequest record with PENDING status."""
    db = next(get_db())
    try:
        # Get Form Data
        hospital_id = request.form.get('hospital_id')
        requested_id = request.form.get('requested_id', 'PATIENT_N/A')
        quantity = int(request.form.get('quantity'))
        blood_type_str = request.form.get('blood_type')
        is_urgent = request.form.get('is_urgent') == 'True'

        # Create New BloodRequest Record
        new_request = BloodRequest(
            requestId=f"R{uuid4().hex[:6].upper()}",
            hospitalId=hospital_id,
            requestedId=requested_id,
            quantity=quantity,
            requestDate=date.today(),
            blood_type=BloodType[blood_type_str],
            isUrgent=is_urgent,
            status=RequestStatus.PENDING
        )
        db.add(new_request)
        db.commit()

        return redirect(url_for('staff.new_blood_request_form', success="Blood request submitted successfully!"))

    except Exception as e:
        db.rollback()
        print(f"Error submitting request: {e}")
        return render_template('submit_request.html', error=f"An error occurred: {e}", title="Submit New Request")
    finally:
        db.close()


@staff_bp.route('/requests')
def view_requests():
    """Renders the dashboard showing all PENDING blood requests."""
    db = next(get_db())
    try:
        # Fetch all PENDING requests
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


@staff_bp.route('/request/fulfill/<id>')
def handle_fulfill_request(id):
    """Triggers the matching service to attempt fulfilling the request."""
    db = next(get_db())
    try:
        # Call the core business logic from services.py
        success, message = fulfill_blood_request(db, id)

        if success:
            return redirect(url_for('staff.view_requests', success=message))
        else:
            return redirect(url_for('staff.view_requests', error=message))

    except Exception as e:
        db.rollback()
        print(f"Error fulfilling request {id}: {e}")
        return redirect(url_for('staff.view_requests', error=f"An error occurred fulfilling request: {e}"))
    finally:
        db.close()

# --- 3. Donor Matching Route (Function #16) ---

@staff_bp.route('/request/match_donor/<request_id>')
def match_donor_for_request(request_id):
    """
    Function #16: Finds an eligible donor for a specific request, typically for urgent/rare types.
    """
    db = next(get_db())
    try:
        request_item = db.query(BloodRequest).filter(BloodRequest.requestId == request_id).first()
        
        if not request_item:
            return redirect(url_for('staff.view_requests', error=f"Request {request_id} not found."))
            
        requested_type = request_item.blood_type
        
        # Call the donor matching service
        success, message = match_to_eligible_donor(db, requested_type)
        
        if success:
            return redirect(url_for('staff.view_requests', success=message))
        else:
            return redirect(url_for('staff.view_requests', error=f"Donor Match Failed: {message}"))
            
    except Exception as e:
        print(f"Error matching donor for request {request_id}: {e}")
        return redirect(url_for('staff.view_requests', error="An internal error occurred during donor matching."))
    finally:
        db.close()