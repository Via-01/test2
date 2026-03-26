# services.py
import math
from typing import List, Tuple, Optional
from sqlalchemy.orm import Session
from datetime import date
from models import (
    Inventory, BloodRequest, BloodType, RequestStatus,
    Donor, ContactInfo, BloodBankUnit, Address, HospitalUnit,
)
from donor_func import check_donor_eligibility

# ---------------------------------------------------------------------------
# Blood type compatibility  (donor type → types it can serve)
# ---------------------------------------------------------------------------
COMPATIBILITY_MAP = {
    BloodType.O_NEGATIVE:  list(BloodType),
    BloodType.O_POSITIVE:  [BloodType.O_POSITIVE, BloodType.A_POSITIVE,
                             BloodType.B_POSITIVE, BloodType.AB_POSITIVE],
    BloodType.A_NEGATIVE:  [BloodType.A_NEGATIVE, BloodType.A_POSITIVE,
                             BloodType.AB_NEGATIVE, BloodType.AB_POSITIVE],
    BloodType.A_POSITIVE:  [BloodType.A_POSITIVE, BloodType.AB_POSITIVE],
    BloodType.B_NEGATIVE:  [BloodType.B_NEGATIVE, BloodType.B_POSITIVE,
                             BloodType.AB_NEGATIVE, BloodType.AB_POSITIVE],
    BloodType.B_POSITIVE:  [BloodType.B_POSITIVE, BloodType.AB_POSITIVE],
    BloodType.AB_NEGATIVE: [BloodType.AB_NEGATIVE, BloodType.AB_POSITIVE],
    BloodType.AB_POSITIVE: [BloodType.AB_POSITIVE],
}

def get_compatible_donor_types(recipient: BloodType) -> List[BloodType]:
    types = [d for d, recipients in COMPATIBILITY_MAP.items() if recipient in recipients]
    if recipient in types:
        types.remove(recipient); types.insert(0, recipient)
    return types


# ---------------------------------------------------------------------------
# Haversine distance in km
# ---------------------------------------------------------------------------
def _haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi  = math.radians(lat2 - lat1)
    dlam  = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


# ---------------------------------------------------------------------------
# Blood bank recommendations — top-3 ranked by:
#   1. Has exact blood type match (vs compatible substitute)
#   2. Has sufficient quantity
#   3. Closest distance to the requesting hospital
# Returns list of dicts for template rendering; hospital chooses one.
# ---------------------------------------------------------------------------
def get_recommendations(
    db: Session,
    requested_type: BloodType,
    quantity: int,
    hospital_id: Optional[str] = None,
) -> List[dict]:
    """
    Find the top-3 blood bank units that can supply `quantity` units of a
    type compatible with `requested_type`, ranked by:
      - exact type match first, then substitutes
      - among ties, closest distance to the requesting hospital
      - secondary tie-break: most available stock
    """
    # Get hospital location for distance scoring
    hosp_lat = hosp_lon = None
    if hospital_id:
        hu = db.query(HospitalUnit).filter(HospitalUnit.unitId == hospital_id).first()
        if hu and hu.address:
            hosp_lat, hosp_lon = hu.address.latitude, hu.address.longitude

    compatible = get_compatible_donor_types(requested_type)
    bank_scores: dict = {}   # unitId → best score dict

    for bt in compatible:
        exact = (bt == requested_type)
        rows = db.query(Inventory).filter(
            Inventory.blood_type == bt,
            Inventory.unitsAvailable > 0,
        ).all()
        for inv in rows:
            uid = inv.unitId
            if uid not in bank_scores:
                bank = db.query(BloodBankUnit).filter(BloodBankUnit.unitId == uid).first()
                dist = None
                if hosp_lat is not None and bank and bank.address:
                    dist = _haversine(hosp_lat, hosp_lon,
                                      bank.address.latitude, bank.address.longitude)
                bank_scores[uid] = {
                    'unitId':      uid,
                    'name':        bank.name if bank else uid,
                    'total_units': 0,
                    'exact_match': False,
                    'has_enough':  False,
                    'distance_km': dist,
                    'blood_types': [],
                }
            bank_scores[uid]['total_units'] += inv.unitsAvailable
            if exact:
                bank_scores[uid]['exact_match'] = True
            if inv.unitsAvailable >= quantity and exact:
                bank_scores[uid]['has_enough'] = True
            if bt.name not in bank_scores[uid]['blood_types']:
                bank_scores[uid]['blood_types'].append(bt.name)

    def score_key(b):
        # Primary: exact match preferred → 0 beats 1
        exact_score = 0 if b['exact_match'] else 1
        # Secondary: has enough stock → 0 beats 1
        enough_score = 0 if b['has_enough'] else 1
        # Tertiary: closer is better (None = far away)
        dist_score = b['distance_km'] if b['distance_km'] is not None else 99999
        # Quaternary: more stock preferred
        stock_score = -b['total_units']
        return (exact_score, enough_score, dist_score, stock_score)

    ranked = sorted(bank_scores.values(), key=score_key)[:3]

    results = []
    for b in ranked:
        dist_str = f"{b['distance_km']:.1f} km" if b['distance_km'] is not None else "Distance unknown"
        results.append({
            'unitId':      b['unitId'],
            'name':        b['name'],
            'total_units': b['total_units'],
            'has_enough':  b['has_enough'],
            'exact_match': b['exact_match'],
            'distance':    dist_str,
            'blood_types': ', '.join(b['blood_types']),
            'note':        ('Exact match' if b['exact_match'] else 'Compatible substitute')
                           + (', sufficient stock' if b['has_enough'] else ', partial stock'),
        })
    return results


# ---------------------------------------------------------------------------
# Fulfill a blood request — DEDUCTS INVENTORY IMMEDIATELY
# If targetBankId is set on the request, pull from that bank first.
# ---------------------------------------------------------------------------
def fulfill_blood_request(db: Session, request_id: str) -> Tuple[bool, str]:
    req = db.query(BloodRequest).filter(BloodRequest.requestId == request_id).first()
    if not req:
        return False, f"Request '{request_id}' not found."
    if req.status != RequestStatus.PENDING:
        return False, f"Request '{request_id}' is already {req.status.name}."

    compatible    = get_compatible_donor_types(req.blood_type)
    required      = req.quantity
    units_to_take = {}
    remaining     = required

    for bt in compatible:
        if remaining <= 0:
            break
        inv_q = db.query(Inventory).filter(
            Inventory.blood_type == bt, Inventory.unitsAvailable > 0)
        # Prefer target bank if specified
        if req.targetBankId:
            target_rows = inv_q.filter(
                Inventory.unitId == req.targetBankId
            ).order_by(Inventory.unitsAvailable.desc()).all()
            other_rows  = inv_q.filter(
                Inventory.unitId != req.targetBankId
            ).order_by(Inventory.unitsAvailable.desc()).all()
            rows = target_rows + other_rows
        else:
            rows = inv_q.order_by(Inventory.unitsAvailable.desc()).all()

        for inv in rows:
            if remaining <= 0:
                break
            take = min(remaining, inv.unitsAvailable)
            units_to_take[inv] = units_to_take.get(inv, 0) + take
            remaining -= take

    if remaining > 0:
        sourced = required - remaining
        return False, (
            f"Insufficient stock. Needed {required}, sourced {sourced}. "
            f"Request stays PENDING."
        )

    for inv, amount in units_to_take.items():
        inv.unitsAvailable -= amount
        inv.lastUpdated     = date.today()

    req.status = RequestStatus.FULFILLED
    db.commit()
    return True, (
        f"Request '{request_id}' fulfilled — {required} units dispatched. "
        f"Awaiting hospital verification."
    )


# ---------------------------------------------------------------------------
# Find eligible donors for a blood type
# ---------------------------------------------------------------------------
def find_eligible_donors(db: Session, requested_type: BloodType) -> List[dict]:
    compatible = get_compatible_donor_types(requested_type)
    candidates = db.query(Donor).filter(
        Donor.isEligible == True, Donor.bloodType.in_(compatible)).all()
    priority = {bt: i for i, bt in enumerate(compatible)}
    candidates.sort(key=lambda d: priority.get(d.bloodType, 999))
    results = []
    for donor in candidates:
        if not check_donor_eligibility(donor):
            continue
        contact = db.query(ContactInfo).filter(
            ContactInfo.user_fk == donor.userId).first()
        results.append({
            'username':   donor.username,
            'userId':     donor.userId[:12],
            'blood_type': donor.bloodType.name,
            'phone':      contact.phone if contact else 'N/A',
            'email':      contact.email if contact else 'N/A',
            'compatible': donor.bloodType == requested_type,
        })
    return results
