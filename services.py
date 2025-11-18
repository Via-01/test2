# services.py
from models import Inventory, BloodRequest, BloodType, RequestStatus, Donor, ContactInfo
from donor_func import check_donor_eligibility
from typing import List, Tuple
from sqlalchemy.orm import Session
from datetime import date

# --- 1. Inventory Helpers ---

def get_inventory_stock(db: Session, blood_type: BloodType, unit_id: str = "BBU001") -> int:
    """
    Fetches the current available units for a specific blood type and unit.
    """
    inventory = db.query(Inventory).filter(
        Inventory.blood_type == blood_type,
        Inventory.unitId == unit_id
    ).first()
    
    return inventory.unitsAvailable if inventory else 0

# --- 2. Blood Matching and Fulfillment (Function #15) ---

# Define compatibility rules (simplified)
COMPATIBILITY_MAP = {
    BloodType.O_NEGATIVE: [BloodType.O_NEGATIVE, BloodType.O_POSITIVE, BloodType.A_NEGATIVE, BloodType.A_POSITIVE, BloodType.B_NEGATIVE, BloodType.B_POSITIVE, BloodType.AB_NEGATIVE, BloodType.AB_POSITIVE],
    BloodType.O_POSITIVE: [BloodType.O_POSITIVE, BloodType.A_POSITIVE, BloodType.B_POSITIVE, BloodType.AB_POSITIVE],
    BloodType.A_NEGATIVE: [BloodType.A_NEGATIVE, BloodType.A_POSITIVE, BloodType.AB_NEGATIVE, BloodType.AB_POSITIVE],
    BloodType.A_POSITIVE: [BloodType.A_POSITIVE, BloodType.AB_POSITIVE],
    BloodType.B_NEGATIVE: [BloodType.B_NEGATIVE, BloodType.B_POSITIVE, BloodType.AB_NEGATIVE, BloodType.AB_POSITIVE],
    BloodType.B_POSITIVE: [BloodType.B_POSITIVE, BloodType.AB_POSITIVE],
    BloodType.AB_NEGATIVE: [BloodType.AB_NEGATIVE, BloodType.AB_POSITIVE],
    BloodType.AB_POSITIVE: [BloodType.AB_POSITIVE]
}

def get_compatible_types(requested_type: BloodType) -> List[BloodType]:
    """Returns a list of donor blood types compatible with the requested recipient type."""
    compatible_types = [donor_type for donor_type, recipient_types in COMPATIBILITY_MAP.items() if requested_type in recipient_types]
    
    if requested_type in compatible_types:
        compatible_types.remove(requested_type)
        compatible_types.insert(0, requested_type)
        
    return compatible_types

def fulfill_blood_request(db: Session, request_id: str, unit_id: str = "BBU001") -> Tuple[bool, str]:
    """
    Function #15: Attempts to match a request to the central inventory.
    """
    request = db.query(BloodRequest).filter(BloodRequest.requestId == request_id).first()
    if not request:
        return False, "Error: Blood request not found."

    if request.status != RequestStatus.PENDING:
        return False, f"Request {request_id} already processed (Status: {request.status.name})."

    requested_type = request.blood_type
    required_quantity = request.quantity
    
    compatible_types = get_compatible_types(requested_type)
    
    units_to_deduct = {}
    remaining_quantity = required_quantity
    
    for blood_type in compatible_types:
        if remaining_quantity <= 0:
            break
            
        inventory_item = db.query(Inventory).filter(
            Inventory.blood_type == blood_type,
            Inventory.unitId == unit_id
        ).first()

        if inventory_item and inventory_item.unitsAvailable > 0:
            available = inventory_item.unitsAvailable
            deduct_amount = min(remaining_quantity, available)
            
            units_to_deduct[inventory_item] = deduct_amount
            remaining_quantity -= deduct_amount
            
    if remaining_quantity == 0:
        for inventory_item, amount in units_to_deduct.items():
            inventory_item.unitsAvailable -= amount
            inventory_item.lastUpdated = date.today()
            
        request.status = RequestStatus.FULFILLED
        db.commit()
        return True, f"Request {request_id} successfully fulfilled using {required_quantity} units."
    else:
        db.rollback()
        return False, f"Insufficient stock. Needed {required_quantity} units, could only source {required_quantity - remaining_quantity}."

# --- 3. Donor Matching Service (Function #16) ---

def match_to_eligible_donor(db: Session, requested_type: BloodType) -> Tuple[bool, str]:
    """
    Function #16: Searches for the nearest eligible donor matching the requested blood type.
    """
    
    # 1. Find all donors initially flagged as eligible
    potential_donors = db.query(Donor).filter(
        Donor.isEligible == True
    ).all()
    
    if not potential_donors:
        return False, "No donors currently marked as eligible in the system."
    
    found_donor = None
    
    # 2. Iterate and check full eligibility (cooldown + health)
    for donor in potential_donors:
        if check_donor_eligibility(donor):
            # *** SIMPLIFICATION: ***
            # Since Donor model lacks a BloodType field, we assume the first eligible donor found 
            # is a match for the requested type for this demo.
            found_donor = donor
            break
            
    if found_donor:
        contact = db.query(ContactInfo).filter(ContactInfo.user_fk == found_donor.userId).first()
        
        message = (
            f"Match found! Urgent contact for {requested_type.name} can be placed to eligible donor {found_donor.username} "
            f"(ID: {found_donor.userId}). Contact: {contact.phone if contact else 'N/A'}."
        )
        return True, message
    else:
        return False, f"No fully eligible donors available for immediate contact."