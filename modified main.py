from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import uvicorn
from pydantic import BaseModel

app = FastAPI()

# Mount the 'templates' directory to serve the index.html file at the /ui URL
app.mount("/ui", StaticFiles(directory="templates", html=True), name="ui_html")

# The rest of your code for API endpoints
donors_db = []
class Donor(BaseModel):
    name: str
    blood_type: str

@app.get("/donors")
def get_donors():
    return donors_db

@app.post("/donors")
def create_donor(donor: Donor):
    donors_db.append(donor)
    return {"message": "Donor added successfully", "donor": donor}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)