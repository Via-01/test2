# app.py
from flask import Flask
# IMPORTANT: Use the correct plural file name 'databases' for the utility file
from databases import init_db 
from routes import main_bp 

# Create the Flask application instance
app = Flask(__name__)
# The SECRET_KEY is necessary for Flask to handle sessions securely
app.config['SECRET_KEY'] = 'your_super_secret_lifelink_key_123' 

# Register the Blueprint to link the routes in routes.py to the application
app.register_blueprint(main_bp)

@app.before_request
def ensure_database_exists():
    """Initializes the database before the very first request."""
    # This ensures the tables are created if the database file is new or empty.
    with app.app_context():
        init_db()

if __name__ == '__main__':
    # Running the application
    app.run(debug=True)