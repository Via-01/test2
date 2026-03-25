# services.py
from models import Inventory, BloodRequest, BloodType, RequestStatus, Donor, ContactInfo
from donor_func import check_donor_eligibility
from typing import List, Tuple
from sqlalchemy.orm import Session
from datetime import date

# ---------------------------------------------------------------------------
# 1. Compatibility map
#    Key   = donor blood type
#    Value = list of recipient types that donor can give to
# ---------------------------------------------------------------------------

COMPATIBILITY_MAP: dict[BloodType, List[BloodType]] = {
    BloodType.O_NEGATIVE:  [
        BloodType.O_NEGATIVE, BloodType.O_POSITIVE,
        BloodType.A_NEGATIVE, BloodType.A_POSITIVE,
        BloodType.B_NEGATIVE, BloodType.B_POSITIVE,
        BloodType.AB_NEGATIVE, BloodType.AB_POSITIVE,
    ],
    BloodType.O_POSITIVE:  [
        BloodType.O_POSITIVE,
        BloodType.A_POSITIVE,
        BloodType.B_POSITIVE,
        BloodType.AB_POSITIVE,
    ],
    BloodType.A_NEGATIVE:  [
        BloodType.A_NEGATIVE, BloodType.A_POSITIVE,
        BloodType.AB_NEGATIVE, BloodType.AB_POSITIVE,
    ],
    BloodType.A_POSITIVE:  [BloodType.A_POSITIVE, BloodType.AB_POSITIVE],
    BloodType.B_NEGATIVE:  [
        BloodType.B_NEGATIVE, BloodType.B_POSITIVE,
        BloodType.AB_NEGATIVE, BloodType.AB_POSITIVE,
    ],
    BloodType.B_POSITIVE:  [BloodType.B_POSITIVE, BloodType.AB_POSITIVE],
    BloodType.AB_NEGATIVE: [BloodType.AB_NEGATIVE, BloodType.AB_POSITIVE],
    BloodType.AB_POSITIVE: [BloodType.AB_POSITIVE],
}


def get_compatible_donor_types(recipient_type: BloodType) -> List[BloodType]:
    """Return donor blood types compatible with *recipient_type*, exact match first."""
    compatible = [
        donor_type
        for donor_type, recipients in COMPATIBILITY_MAP.items()
        if recipient_type in recipients
    ]
    # Prioritise exact match so we use the most specific type before falling back
    if recipient_type in compatible:
        compatible.remove(recipient_type)
        compatible.insert(0, recipient_type)
    return compatible


# ---------------------------------------------------------------------------
# 2. Inventory helpers
# ---------------------------------------------------------------------------

def get_inventory_stock(db: Session, blood_type: BloodType, unit_id: str = "BBU001") -> int:
    """Return current available units for a blood type at a given unit."""
    inv = db.query(Inventory).filter(
        Inventory.blood_type == blood_type,
        Inventory.unitId     == unit_id,
    ).first()
    return inv.unitsAvailable if inv else 0


# ---------------------------------------------------------------------------
# 3. Blood request fulfillment  (Function #15)
# ---------------------------------------------------------------------------

def fulfill_blood_request(db: Session, request_id: str) -> Tuple[bool, str]:

    req = db.query(BloodRequest).filter(BloodRequest.requestId == request_id).first()
    if not req:
        return False, f"Blood request '{request_id}' not found."
    if req.status != RequestStatus.PENDING:
        return False, f"Request '{request_id}' already processed (status: {req.status.name})."

    compatible_types  = get_compatible_donor_types(req.blood_type)
    required_quantity = req.quantity
    remaining         = required_quantity

    # Check total stock across all units
    for blood_type in compatible_types:
        if remaining <= 0:
            break

        inventories = db.query(Inventory).filter(
            Inventory.blood_type == blood_type
        ).all()

        total_available = sum(inv.unitsAvailable for inv in inventories)

        if total_available > 0:
            deduct = min(remaining, total_available)
            remaining -= deduct

    if remaining > 0:
        sourced = required_quantity - remaining
        return False, (
            f"Insufficient stock. Needed {required_quantity} units, "
            f"could only source {sourced}."
        )

    req.status = RequestStatus.FULFILLED
    db.commit()
    return True, f"Request '{request_id}' fulfilled — awaiting verification."


# ---------------------------------------------------------------------------
# 4. Donor matching  (Function #16) — FIXED: filters by blood type
# ---------------------------------------------------------------------------

def match_to_eligible_donor(
    db: Session, requested_type: BloodType
) -> Tuple[bool, str]:
    """Find the best eligible donor whose blood type is compatible with *requested_type*.

    Compatible donor types = those that can donate TO the requested recipient type.
    Returns the first fully eligible donor found, preferring exact type match.
    """
    compatible_donor_types = get_compatible_donor_types(requested_type)

    # Query only donors whose blood type is in the compatible set
    # AND who are flagged as eligible in the DB (quick pre-filter)
    candidates = (
        db.query(Donor)
        .filter(
            Donor.isEligible == True,
            Donor.bloodType.in_(compatible_donor_types),
        )
        .all()
    )

    if not candidates:
        return False, (
            f"No eligible donors found with a blood type compatible with "
            f"{requested_type.name}."
        )

    # Sort so exact-match donors come first, then by broadest compatibility
    type_priority = {bt: i for i, bt in enumerate(compatible_donor_types)}
    candidates.sort(key=lambda d: type_priority.get(d.bloodType, 999))

    # Full eligibility check (cooldown + isEligible flag)
    for donor in candidates:
        if check_donor_eligibility(donor):
            contact = db.query(ContactInfo).filter(
                ContactInfo.user_fk == donor.userId
            ).first()
            phone = contact.phone if contact else "N/A"
            return True, (
                f"Match found! Donor '{donor.username}' "
                f"(blood type: {donor.bloodType.name}, ID: {donor.userId[:8]}) "
                f"is eligible and compatible with {requested_type.name}. "
                f"Contact: {phone}."
            )

    return False, (
        f"No fully eligible donors are currently available for "
        f"{requested_type.name} (all compatible donors are in cooldown or ineligible)."
    )
