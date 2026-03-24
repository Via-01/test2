from flask import Flask, render_template
from databases import init_db

# Import Blueprints
from main_routes import main_bp
from donor_routes import donor_bp
from staff_routes import staff_bp
from inventory_routes import inventory_bp
from report_routes import report_bp   # Reporting blueprint

app = Flask(__name__)
app.secret_key = "your-secret-key"  # Needed for flash()

# --- Initialize Database ---
init_db()

# --- Register Blueprints with URL Prefixes ---
# Only app.py should have the url_prefix (NOT inside the blueprint definitions)

app.register_blueprint(main_bp)  # main = homepage/dashboard (“/”)

app.register_blueprint(donor_bp, url_prefix="/donor")
# Example: /donor/add, /donor/list

app.register_blueprint(staff_bp, url_prefix="/staff")
# Example: /staff/login, /staff/list

app.register_blueprint(inventory_bp, url_prefix="/inventory")
# Example: /inventory/stock, /inventory/transfer

app.register_blueprint(report_bp, url_prefix="/reports")
# Example: /reports/daily, /reports/monthly

# --- Error Handlers ---

@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template("500.html"), 500


# --- Main Entry Point ---

if __name__ == "__main__":
    app.run(debug=True)
