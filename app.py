# app.py
import os
from datetime import timedelta
from flask import Flask, render_template
from databases import init_db
from main_routes     import main_bp
from donor_routes    import donor_bp
from staff_routes    import staff_bp
from hospital_routes import hospital_bp

app = Flask(__name__)
app.secret_key                 = os.environ.get("SECRET_KEY", "change-me-in-production")
app.permanent_session_lifetime = timedelta(minutes=60)

init_db()

app.register_blueprint(main_bp)
app.register_blueprint(donor_bp,    url_prefix="/donor")
app.register_blueprint(staff_bp,    url_prefix="/staff")
app.register_blueprint(hospital_bp, url_prefix="/hospital")

app.jinja_env.globals['enumerate'] = enumerate

@app.errorhandler(404)
def not_found(e):    return render_template("404.html"), 404
@app.errorhandler(500)
def server_error(e): return render_template("500.html"), 500

if __name__ == "__main__":
    app.run(debug=True)
