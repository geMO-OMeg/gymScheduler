from fastapi import FastAPI
from pydantic import BaseModel
from scheduler import run_scheduler

app - FastAPI()

class ScheduleRequest(BaseModel):
    day: str
    classes: list

@app.post("/schedule")
def schedule(req: ScheduleRequest):
    print(f"Received request for {req.day} with {len(req.classes)} classes")
    return {
        "day": req.day,
        "received_classes": req.classes,
        "status": "ok"
    }