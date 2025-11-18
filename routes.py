# routes.py
from flask import Blueprint, request, jsonify, redirect, url_for, render_template
# IMPORTANT: Use the correct plural file name 'databases' for the utility file
from databases import get_db
# Import all models needed for fetching data
from models import Donor, BloodRequest, BloodBankUnit, Address, ContactInfo, Inventory 

# Define a Blueprint to organize routes
main_bp = Blueprint('main', __name__) 

@main_bp.route('/', methods=['GET'])
def home_dashboard():
    """Renders the dashboard with the list of donors."""
    db = next(get_db())
    donor_list = []
    
    try:
        # 1. Fetch all Donors
        donors = db.query(Donor).all()

        for donor in donors:
            # 2. Fetch ContactInfo for each Donor to get the email
            contact = db.query(ContactInfo).filter_by(user_fk=donor.userId).first()
            
            donor_list.append({
                "userId": donor.userId,
                "username": donor.username,
                "isEligible": donor.isEligible,
                "lastDonation": str(donor.lastDonationDate) if donor.lastDonationDate else "N/A",
                "email": contact.email if contact else "N/A"
            })
        
        # 3. Pass the data list to the index.html template
        return render_template('index.html', 
                               title='LifeLink Donor Dashboard', 
                               donors=donor_list)

    except Exception as e:
        # Handle errors gracefully by rendering the template with an error message
        print(f"Database error in home_dashboard: {e}")
        return render_template('index.html', title='Error', error="Could not load data from database.")


@main_bp.route('/donors', methods=['GET'])
def list_donors():
    """Fetches and displays a list of all donors as JSON (API endpoint)."""
    db = next(get_db()) 
    
    try:
        donors = db.query(Donor).all()
        donor_list = []
        for donor in donors:
            contact = db.query(ContactInfo).filter_by(user_fk=donor.userId).first()
            
            donor_list.append({
                "userId": donor.userId,
                "username": donor.username,
                "isEligible": donor.isEligible,
                "lastDonation": str(donor.lastDonationDate) if donor.lastDonationDate else "N/A",
                "email": contact.email if contact else "N/A"
            })
        
        return jsonify({"donors": donor_list, "count": len(donor_list)})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@main_bp.route('/inventory', methods=['GET'])
def inventory_summary():
    """Fetches the inventory summary for all blood bank units as JSON (API endpoint)."""
    db = next(get_db())
    
    try:
        units = db.query(BloodBankUnit).all()
        
        summary = []
        for unit in units:
            inventory = db.query(Inventory).filter_by(unitId=unit.unitId).first()
            
            summary.append({
                "unitName": unit.name,
                "contact": unit.contactNumber,
                "inventoryId": inventory.inventoryId if inventory else "N/A",
                "unitsAvailable": inventory.unitsAvailable if inventory else 0
            })
            
        return jsonify({"inventorySummary": summary})
    
    except Exception as e:
        return jsonify({"error": "Failed to load inventory."}), 500