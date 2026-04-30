from fastapi import FastAPI
from scheduler import run_scheduler

app = FastAPI()

@app.post("/schedule")
def schedule(payload: dict):
    day = payload["day"]
    event_map = payload.get("event_map", [])
    sheets = payload.get("sheets")

    #Legacy single-sheet payload support (safety net...might remove later)
    if not sheets:
        classes = payload.get("classes", [])
        result = run_scheduler(day, classes, event_map)
        return result

    result_a = run_scheduler(day, sheets["A"]["classes"], event_map)
    result_b = run_scheduler(day, sheets["B"]["classes"], event_map)
    
    return { "A": result_a, "B": result_b }

@app.get("/ping")
def ping():
    return {"status": "ok"}