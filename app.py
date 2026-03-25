# app.py
import os
from flask import Flask, render_template
from databases import init_db

from main_routes      import main_bp
from donor_routes     import donor_bp
from staff_routes     import staff_bp
from inventory_routes import inventory_bp
from report_routes    import report_bp

app = Flask(__name__)

# Use an env var in production: export SECRET_KEY="something-random"
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")

# Keep sessions alive for 30 minutes of inactivity
from datetime import timedelta
app.permanent_session_lifetime = timedelta(minutes=30)

# --- Database ---
init_db()

# --- Blueprints ---
app.register_blueprint(main_bp)                             # /
app.register_blueprint(donor_bp,     url_prefix="/donor")   # /donor/...
app.register_blueprint(staff_bp,     url_prefix="/staff")   # /staff/...
app.register_blueprint(inventory_bp, url_prefix="/inventory")
app.register_blueprint(report_bp,    url_prefix="/reports")

# --- Error handlers ---
@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template("500.html"), 500

if __name__ == "__main__":
    app.run(debug=True)
