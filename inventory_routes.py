# inventory_routes.py  — Shared inventory views (staff + admin only)
from flask import Blueprint, render_template, request, redirect, url_for, flash
from databases import get_db
from models import Inventory, BloodBankUnit, BloodType, BloodRequest, RequestStatus, LogAction
from auth import role_required, write_audit
from datetime import date
from uuid import uuid4
from sqlalchemy import func

inventory_bp = Blueprint('inventory', __name__, url_prefix='/inventory')
STAFF_ROLES  = ('blood_bank_staff',)


@inventory_bp.route('/stock')
@role_required(*STAFF_ROLES)
def view_inventory_stock():
    db = next(get_db())
    try:
        items = db.query(
            Inventory.blood_type,
            func.sum(Inventory.unitsAvailable).label("totalUnits"),
            func.max(Inventory.lastUpdated).label("lastUpdated"),
        ).group_by(Inventory.blood_type).all()

        stock_list = [{
            "bloodType":      item.blood_type.name,
            "unitsAvailable": item.totalUnits,
            "minOrderAmt":    50,
            "lastUpdated":    item.lastUpdated.strftime("%Y-%m-%d") if item.lastUpdated else "N/A",
        } for item in items]

        pending_updates = db.query(BloodRequest).filter(
            BloodRequest.status == RequestStatus.FULFILLED
        ).all()

        return render_template('view_inventory.html',
                               inventory=stock_list,
                               pending_updates=pending_updates,
                               title="Blood Stock Management")
    except Exception as e:
        flash(f"Error loading inventory: {e}", 'error')
        return render_template('view_inventory.html', inventory=[], title="Blood Stock Management")
    finally:
        db.close()


@inventory_bp.route('/transfer')
@role_required(*STAFF_ROLES)
def transfer_units_form():
    db = next(get_db())
    try:
        units       = db.query(BloodBankUnit).all()
        blood_types = [bt.name for bt in BloodType]
        return render_template('transfer_units.html',
                               title="Transfer Blood Units",
                               unit_ids=[u.unitId for u in units],
                               blood_types=blood_types)
    finally:
        db.close()


@inventory_bp.route('/transfer/execute', methods=['POST'])
@role_required(*STAFF_ROLES)
def execute_transfer():
    db = next(get_db())
    try:
        source_unit    = request.form.get('source_unit', '').strip()
        dest_unit      = request.form.get('dest_unit', '').strip()
        blood_type_str = request.form.get('blood_type', '').strip()
        try:
            quantity = int(request.form.get('quantity', 0))
            if quantity <= 0: raise ValueError
        except (ValueError, TypeError):
            flash("Quantity must be a positive whole number.", 'error')
            return redirect(url_for('inventory.transfer_units_form'))

        if source_unit == dest_unit:
            flash("Source and destination cannot be the same.", 'error')
            return redirect(url_for('inventory.transfer_units_form'))

        try:
            blood_type = BloodType[blood_type_str]
        except KeyError:
            flash(f"Invalid blood type: '{blood_type_str}'.", 'error')
            return redirect(url_for('inventory.transfer_units_form'))

        source_inv = db.query(Inventory).filter(
            Inventory.unitId == source_unit, Inventory.blood_type == blood_type).first()
        if not source_inv:
            flash(f"No {blood_type_str} stock in source unit '{source_unit}'.", 'error')
            return redirect(url_for('inventory.transfer_units_form'))
        if source_inv.unitsAvailable < quantity:
            flash(f"Insufficient stock: {source_inv.unitsAvailable} available, {quantity} requested.", 'error')
            return redirect(url_for('inventory.transfer_units_form'))

        source_inv.unitsAvailable -= quantity
        source_inv.lastUpdated     = date.today()

        dest_inv = db.query(Inventory).filter(
            Inventory.unitId == dest_unit, Inventory.blood_type == blood_type).first()
        if dest_inv:
            dest_inv.unitsAvailable += quantity
            dest_inv.lastUpdated     = date.today()
        else:
            db.add(Inventory(
                inventoryId=f"I{uuid4().hex[:6].upper()}",
                unitsAvailable=quantity, lastUpdated=date.today(),
                minOrderAmt=10, maxStorage=500.0,
                unitId=dest_unit, blood_type=blood_type, component="WHOLE_BLOOD",
            ))

        write_audit(db, LogAction.UPDATE,
                    f"Transferred {quantity} units of {blood_type_str} from {source_unit} to {dest_unit}.")
        db.commit()
        flash(f"Transferred {quantity} units of {blood_type_str} from '{source_unit}' to '{dest_unit}'.", 'success')
        return redirect(url_for('inventory.view_inventory_stock'))

    except Exception as e:
        db.rollback()
        flash(f"Unexpected error: {e}", 'error')
        return redirect(url_for('inventory.transfer_units_form'))
    finally:
        db.close()
