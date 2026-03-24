"""
define input data,
build solver model
solve it
print the result
"""

from ortools.sat.python import cp_model
import pandas as pd
from pathlib import Path
import logging

LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
LOG_DIR.mkdir(exist_ok=True)

#Logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "scheduler.log")
    ]
)
logger = logging.getLogger(__name__)



def to_time_str(minutes):
    h = minutes // 60
    m = minutes % 60
    return f"{h:02d}:{m:02d}"

    
def run_scheduler(day, classes, event_map):

    #build program_equipment lookup from event_map sent by Apps Script
    #ex payload: { "TOTS": ["Beam", "Floor", "Bars"], "BOYS B": [...], ...}
    logger.debug("run_scheduler called: day=%s, %d classes", day, len(classes))

    program_equipment = {
        entry["program"].strip().upper(): entry["events"]
        for entry in event_map
    }
    logger.debug("program_equipment loaded: %s", list(program_equipment.keys()))

    # create the model
    model = cp_model.CpModel()
    equip_intervals = []
    equip_usage = {}
    class_Usage_list = {}

    for entry in classes: 
        program = entry["program"].strip().upper()
        print_col = entry["print_col"]
        start_minutes = entry["start_minutes"]
        warmup_time = entry["warmup_time"]
        block_time = entry["block_time"]
        cooldown_time = entry["cooldown_time"]
        requested_time = entry["requested_time"]

        equipment_list = program_equipment.get(program, [])
        if not equipment_list:
            print(f"Warning: no equipment found for program {program}")
            continue
        logger.debug(
            "Processing %s | col %s | start=%d | warmup=%d | block=%d | cooldown=%d",
            program, entry["print_col"], entry["start_minutes"],
            entry["warmup_time"], entry["block_time"], entry["cooldown_time"]
        )

        n = len(equipment_list)

        # Equipment usage window: starts after warmup, ends before cooldown
        window_start = start_minutes + warmup_time
        window_end = window_start + block_time * n

        class_key = (program, print_col, requested_time)
        class_Usage_list[class_key] = {
            "warmup_end": window_start,
            "items": []
        }

        for equip in equipment_list:
            duration = block_time
            start_var = model.new_int_var(
                window_start,
                window_end - duration,
                f"start_{program}_{print_col}_{equip}"
            )

            end_var = model.new_int_var(
                window_start + duration,
                window_end,
                f"end_{program}_{print_col}_{equip}"
            )

            interval = model.new_interval_var(
                start_var,
                duration,
                end_var,
                f"interval_{program}_{print_col}_{equip}"
            )

            #track for cross-class conflicts
            equip_usage.setdefault(equip, []).append(interval)

            #track for intra-class chaining constraint
            class_Usage_list[class_key]["items"].append({
                "start": start_var,
                "end": end_var,
                "interval": interval
            })

            equip_intervals.append({
                "program": program,
                "print_col": print_col,
                "requested_time": requested_time,
                "start_minutes": start_minutes,
                "warmup_time": warmup_time,
                "block_time": block_time,
                "cooldown_time": cooldown_time,
                "equip": equip,
                "start": start_var,
                "end": end_var,
            })

    #cross-class equipment conflict constraint
    for equip, intervals in equip_usage.items():
        if len(intervals) > 1:
            model.add_no_overlap(intervals)

    #intra-class constraints: pin first slot to warmup end, chain the rest
    for class_key, data in class_Usage_list.items():
        items = data["items"]
        warmup_end = data["warmup_end"]

        #pin first equipment slot to start exactly at warmup end
        model.add(items[0]["start"] == warmup_end)

        # Chain remaining slots: end of slot i == start of slot i+1
        for i in range(len(items) - 1):
            model.add(items[i]["end"] == items[i+1]["start"])

    return solve_model(model, equip_intervals)

      


def solve_model(model, equip_intervals):

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10.0
    status = solver.Solve(model)
    logger.debug("Solver status: %s", solver.StatusName(status))

    #output result
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        logger.debug("Cannot be solved: %s \n", solver.StatusName(status))
        return {"status": "infeasible", "coaches": []}
    
    coaches = {}
        
    print("Schedule:\n")
    for entry in equip_intervals:
        print_col = entry["print_col"]
        start_min = solver.Value(entry["start"])
        end_min = solver.Value(entry["end"])
        logger.debug(
            "%s | col %s | %s --> %s",
            entry["program"], print_col, entry["equip"],
            to_time_str(start_min), to_time_str(end_min)
        )

        if print_col not in coaches:
            coaches[print_col] = {
                "print_col": print_col,
                "blocks": []
            }

            if entry["warmup_time"] > 0:
                warmup_start = entry["start_minutes"]
                warmup_end = warmup_start + entry["warmup_time"]
                for t in range(warmup_start, warmup_end, 5):
                    coaches[print_col]["blocks"].append({
                        "time": to_time_str(t),
                        "label": "WARM UP"
                    })

        # Add equipment blocks in 5-min increments
        for t in range(start_min, end_min, 5):
            coaches[print_col]["blocks"].append({
                "time": to_time_str(t),
                "label": entry["equip"]
            })

    # Add cooldown after last equipment block for each coach
    for print_col, data in coaches.items():
        last_entry = next(
            e for e in reversed(equip_intervals)
            if e["print_col"] == print_col
        )
        last_end = solver.Value(last_entry["end"])
        cooldown_time = last_entry["cooldown_time"]
        for t in range(last_end, last_end + cooldown_time, 5):
            data["blocks"].append({
                "time": to_time_str(t),
                "label": "COOL DOWN"
            })

    return {"status": "ok", "coaches": list(coaches.values())}

if __name__ == "__main__":
    
    #local test - mirrors what apps script would send

    test_classes = [
        {
            "print_col": "D",
            "program": "TOTS",
            "requested_time": "4:15",
            "start_minutes": 255,
            "warmup_time": 10,
            "block_time": 10,
            "cooldown_time": 5
        },
        {
            "print_col": "E",
            "program": "BOYS B",
            "requested_time": "5:00",
            "start_minutes": 300,
            "warmup_time": 25,
            "block_time": 15,
            "cooldown_time": 10 
        }
    ]
    test_event_map = [
        {"program": "TOTS", "events": ["Beam", "Floor", "Bars"]},
        {"program": "BOYS B", "events": ["Floor", "Bars", "Rings"]},
    ]
    
    result = run_scheduler("TUESDAY", test_classes, test_event_map)
    print(result)

    