# report_routes.py
from flask import Blueprint, render_template, request, url_for
from databases import get_db 
from models import Donation, Inventory, BloodRequest, DonationStatus, RequestStatus, BloodType
from sqlalchemy import func
from datetime import date, timedelta

report_bp = Blueprint('report', __name__, url_prefix='/reports')

# --- Report Menu ---

@report_bp.route('/')
def reports_menu():
    """Renders the main menu for selecting a type of report."""
    return render_template('reports_menu.html', title="Reporting & Analytics")

# --- Blood Bank Performance Report (Inventory & Donations) ---

@report_bp.route('/blood_bank')
def blood_bank_report():
    """Generates a report focused on the Blood Bank's performance (inventory and donations)."""
    db = next(get_db())
    try:
        # --- 1. Current Inventory Summary (Total units per blood type) ---
        # Sums up unitsAvailable across all inventory records grouped by blood type.
        inventory_summary = db.query(
            Inventory.blood_type,
            func.sum(Inventory.unitsAvailable).label('total_units')
        ).group_by(Inventory.blood_type).all()

        # --- 2. Recent Donation Volume (Last 30 days) ---
        last_30_days = date.today() - timedelta(days=30)
        
        # Counts successful donations and sums the quantity donated in the last 30 days.
        donation_volume = db.query(
            Donation.blood_type,
            func.count(Donation.donationId).label('total_donations'),
            func.sum(Donation.quantity).label('total_quantity')
        ).filter(
            Donation.date >= last_30_days,
            Donation.status == DonationStatus.COMPLETE
        ).group_by(Donation.blood_type).all()
        
        # --- 3. Donation Status Breakdown (Last 30 days) ---
        # Counts the number of donations for each status (e.g., COMPLETE, SCREENING_FAILED)
        status_breakdown = db.query(
            Donation.status,
            func.count(Donation.donationId).label('count')
        ).filter(Donation.date >= last_30_days).group_by(Donation.status).all()

        report_data = {
            # Convert SQLAlchemy objects to simple dictionaries for the template
            'inventory_summary': [{'bloodType': item[0].name, 'total_units': item[1]} for item in inventory_summary],
            'donation_volume': [
                {'bloodType': item[0].name, 'count': item[1], 'quantity': item[2] if item[2] else 0} 
                for item in donation_volume
            ],
            'status_breakdown': [{'status': item[0].name, 'count': item[1]} for item in status_breakdown],
            'report_date': date.today().strftime("%Y-%m-%d"),
            'period': f"Last 30 days (since {last_30_days.strftime('%Y-%m-%d')})"
        }
        
        return render_template('blood_bank_report.html', data=report_data, title="Blood Bank Performance Report")
        
    finally:
        db.close()

# --- Hospital Request Analysis Report (Fulfillment & Usage) ---

@report_bp.route('/hospital')
def hospital_report():
    """Generates a report focused on Hospital Request metrics (fulfillment and usage)."""
    db = next(get_db())
    try:
        # --- 1. Total Requests by Status (All Time) ---
        # Counts requests by their current status (e.g., PENDING, FULFILLED, REJECTED).
        requests_by_status = db.query(
            BloodRequest.status,
            func.count(BloodRequest.requestId).label('count')
        ).group_by(BloodRequest.status).all()

        # --- 2. Fulfillment Rate ---
        # Count of all closed requests (denominator for the rate)
        total_closed_requests = db.query(func.count(BloodRequest.requestId)).filter(
            BloodRequest.status.in_([RequestStatus.FULFILLED, RequestStatus.VERIFIED, RequestStatus.REJECTED])
        ).scalar() or 0
        
        # Count of all successfully fulfilled requests (numerator for the rate)
        total_fulfilled_requests = db.query(func.count(BloodRequest.requestId)).filter(
            BloodRequest.status.in_([RequestStatus.FULFILLED, RequestStatus.VERIFIED])
        ).scalar() or 0
        
        fulfillment_rate = (total_fulfilled_requests / total_closed_requests * 100) if total_closed_requests > 0 else 0
        
        # --- 3. Requests by Urgency (All Time) ---
        # Counts requests based on the boolean flag isUrgent (True or False).
        requests_by_urgency = db.query(
            BloodRequest.isUrgent,
            func.count(BloodRequest.requestId).label('count')
        ).group_by(BloodRequest.isUrgent).all()
        
        # --- 4. Total Requests ---
        total_requests = db.query(func.count(BloodRequest.requestId)).scalar() or 0

        report_data = {
            'requests_by_status': [{'status': item[0].name, 'count': item[1]} for item in requests_by_status],
            'requests_by_urgency': [{'type': 'Urgent' if item[0] else 'Normal', 'count': item[1]} for item in requests_by_urgency],
            'fulfillment_rate': f"{fulfillment_rate:.2f}%",
            'total_requests': total_requests,
            'report_date': date.today().strftime("%Y-%m-%d")
        }
        
        return render_template('hospital_report.html', data=report_data, title="Hospital Request Analysis Report")
        
    finally:
        db.close()