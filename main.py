from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import uvicorn
from pydantic import BaseModel
import os

# Set up templates directory
templates = Jinja2Templates(directory="templates")

# Initialize FastAPI app
app = FastAPI()

# Mount static files (like CSS or JS, even if not used yet)
app.mount("/static", StaticFiles(directory="static"), name="static")

# In-memory "database" to store our donors
donors_db = []

# Donor model for data validation
class Donor(BaseModel):
    name: str
    blood_type: str

# Root endpoint to serve the UI
@app.get("/")
def serve_ui(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# Endpoint to get all donors
@app.get("/donors")
def get_donors():
    return donors_db

# Endpoint to add a new donor
@app.post("/donors")
def create_donor(donor: Donor):
    donors_db.append(donor)
    return {"message": "Donor added successfully", "donor": donor}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)