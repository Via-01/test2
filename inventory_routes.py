# inventory_routes.py
from flask import Blueprint, render_template, request, redirect, url_for
from databases import get_db 
# Note: Ensure you import all necessary models and types here
from models import Inventory, BloodBankUnit, BloodType
from datetime import date # Needed for updating lastUpdated
from uuid import uuid4 # Needed for creating new Inventory IDs

inventory_bp = Blueprint('inventory', __name__, url_prefix='/inventory')

# --- 1. View Inventory Stock (Function #10: trackInventory) ---

@inventory_bp.route('/stock')
def view_inventory_stock():
    """
    Function #10: Renders a dashboard showing current blood inventory levels by type and unit.
    """
    db = next(get_db())
    try:
        inventory_data = db.query(Inventory).all() 

        stock_list = []
        for item in inventory_data:
            stock_list.append({
                "bloodType": item.blood_type.name,
                "unitId": item.unitId,
                "unitsAvailable": item.unitsAvailable,
                "minOrderAmt": item.minOrderAmt,
                "lastUpdated": item.lastUpdated.strftime("%Y-%m-%d")
            })

        success_message = request.args.get('success')
        error_message = request.args.get('error')

        return render_template(
            'view_inventory.html', 
            inventory=stock_list, 
            title="Blood Stock Management",
            success=success_message,
            error=error_message
        )
    finally:
        db.close()

# --- 2. Transfer Blood Units (Function #12: transferInventory) ---

@inventory_bp.route('/transfer')
def transfer_units_form():
    """Renders the form for staff to transfer blood units between storage units."""
    db = next(get_db())
    try:
        # Fetch available Blood Bank Unit IDs for selection fields
        units = db.query(BloodBankUnit).all()
        unit_ids = [unit.unitId for unit in units]
        
        # Capture messages passed back after a failed execution attempt
        error_message = request.args.get('error')
        
        return render_template('transfer_units.html', 
                               title="Transfer Blood Units", 
                               unit_ids=unit_ids,
                               error=error_message)
    finally:
        db.close()

@inventory_bp.route('/transfer/execute', methods=['POST'])
def execute_transfer():
    """
    Function #12: Handles the logic for transferring units from a source to a destination unit.
    """
    db = next(get_db())
    try:
        source_unit = request.form.get('source_unit')
        dest_unit = request.form.get('dest_unit')
        blood_type_str = request.form.get('blood_type')
        
        try:
            quantity = int(request.form.get('quantity'))
        except (ValueError, TypeError):
            return redirect(url_for('inventory.transfer_units_form', error="Invalid quantity. Please enter a valid number."))
            
        if source_unit == dest_unit:
            return redirect(url_for('inventory.transfer_units_form', error="Source and Destination units cannot be the same."))

        blood_type = BloodType[blood_type_str]
        
        # 1. Deduct from Source Inventory
        source_inventory = db.query(Inventory).filter(
            Inventory.unitId == source_unit,
            Inventory.blood_type == blood_type
        ).first()

        if not source_inventory or source_inventory.unitsAvailable < quantity:
            db.rollback()
            return redirect(url_for('inventory.transfer_units_form', error=f"Insufficient stock ({source_inventory.unitsAvailable}mL available) in Source Unit {source_unit} for {blood_type_str}."))

        source_inventory.unitsAvailable -= quantity
        source_inventory.lastUpdated = date.today()
        
        # 2. Add to Destination Inventory
        dest_inventory = db.query(Inventory).filter(
            Inventory.unitId == dest_unit,
            Inventory.blood_type == blood_type
        ).first()

        if dest_inventory:
            dest_inventory.unitsAvailable += quantity
            dest_inventory.lastUpdated = date.today()
        else:
            # Create a new inventory record for the destination if it doesn't exist
            new_dest_inventory = Inventory(
                inventoryId=f"I{uuid4().hex[:6].upper()}",
                unitsAvailable=quantity,
                lastUpdated=date.today(),
                minOrderAmt=10, 
                maxStorage=500.0, 
                unitId=dest_unit,
                blood_type=blood_type,
                component="WHOLE_BLOOD" 
            )
            db.add(new_dest_inventory)

        db.commit()
        return redirect(url_for('inventory.view_inventory_stock', success=f"Successfully transferred {quantity}mL of {blood_type_str} from {source_unit} to {dest_unit}."))

    except KeyError:
        db.rollback()
        return redirect(url_for('inventory.transfer_units_form', error="Invalid Blood Type selected."))
    except Exception as e:
        db.rollback()
        print(f"Error during unit transfer: {e}")
        return redirect(url_for('inventory.transfer_units_form', error=f"An unexpected error occurred during transfer: {e}"))
    finally:
        db.close()