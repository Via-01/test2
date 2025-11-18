# app.py
from flask import Flask
from databases import init_db 
# IMPORT ALL BLUEPRINTS
from main_routes import main_bp 
from donor_routes import donor_bp
from staff_routes import staff_bp

# Create the Flask application instance
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_super_secret_lifelink_key_123' 

# Register all Blueprints
app.register_blueprint(main_bp)
# Register donor_bp and set URL prefix for clarity
app.register_blueprint(donor_bp, url_prefix='/donor')
# Register staff_bp and set URL prefix for clarity (already set in staff_routes.py)
app.register_blueprint(staff_bp)

@app.before_request
def ensure_database_exists():
    with app.app_context():
        init_db()

if __name__ == '__main__':
    app.run(debug=True)