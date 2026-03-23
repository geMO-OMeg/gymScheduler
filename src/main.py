from fastapi import FastAPI
from pydantic import BaseModel
from scheduler import run_scheduler

app = FastAPI()

class ScheduleRequest(BaseModel):
    day: str
    classes: list
    event_map: list

@app.post("/schedule")
def schedule(req: ScheduleRequest):
    print(f"Received request for {req.day} with {len(req.classes)} classes")
    result = run_scheduler(
        day=req.day,
        classes=req.classes,
        event_map=req.event_map
    )
    return result