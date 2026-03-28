"""
define input data,
build solver model
solve it
print the result
"""

from ortools.sat.python import cp_model
from pathlib import Path
import logging

#LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
#LOG_DIR.mkdir(exist_ok=True)

#-----------------------------------------------------------------------
#Logging --> cloud run will automatically store printouts to terminal in Google Cloud Logging

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        #logging.FileHandler(LOG_DIR / "scheduler.log"),
        logging.StreamHandler() 
    ]
)
logger = logging.getLogger("scheduler")
#logger = logging.getLogger(__name__)
'''
#temp logger to bypass basicConfig conflict with uvicorn test enviro
#get logger directly
logger = logging.getLogger('scheduler')
logger.setLevel(logging.DEBUG)

#prevent duplicate handlers if module is reloaded
if not logger.handlers:
    #file handler
    fh = logging.FileHandler(LOG_DIR / "scheduler.log")
    fh.setLevel(logging.DEBUG)
    #terminal handler
    sh = logging.StreamHandler()
    sh.setLevel(logging.DEBUG)
    #Formatter
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh.setFormatter(fmt)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
'''
#------------------------------------------------------------------

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
            logger.debug(f"Warning: no equipment found for program {program}")
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
            "window_end": window_end,
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
        window_end = data["window_end"]

        #Slots must form a contiguous block within the window
        #min(start) to max(end) == total_duration
        #This combined with no_overlap prevents gaps
        for item in items:
            model.add(item["start"] >= warmup_end)
            model.add(item["end"] <= window_end)

        # No overlap within the class -- slots can't run simultaneously
        if len(items) > 1: 
            model.add_no_overlap([item["interval"] for item in items])

        #no gaps -- total equipment time must exactly fill the window
        #sum of all slot durations == window_end - warmup_end
        total_duration = sum(
            entry["block_time"]
            for entry in equip_intervals
            if (entry["program"], entry["print_col"], entry["requested_time"]) == class_key
        )

        #the block must be contiguous: span == total duration
        #use auxiliary vars for min start and max end
        starts = [item["start"] for item in items]
        ends = [item["end"] for item in items]

        min_start = model.new_int_var(warmup_end, window_end, f"min_start_{class_key}")
        max_end = model.new_int_var(warmup_end, window_end, f"max_end{class_key}")

        model.add_min_equality(min_start, starts)
        model.add_max_equality(max_end, ends)

        model.add(max_end - min_start == total_duration)

    logger.debug("=== MODEL SUMMARY ===")
    for entry in equip_intervals:
        logger.debug(
            "INTERVAL: %s | col %s | %s | window [%d - %d] duration %d",
            entry["program"],
            entry["print_col"],
            entry["equip"],
            entry["start_minutes"] + entry["warmup_time"],
            entry["start_minutes"] + entry["warmup_time"] + entry["block_time"] * len(program_equipment.get(entry["program"], [])),
            entry["block_time"]
        )
    logger.debug("=== EQUIPMENT GROUPS ===")
    for equip, intervals in equip_usage.items():
        logger.debug("EQUIP %s used by %d classes", equip, len(intervals))
    logger.debug("=== CHAIN CONSTRAINTS ===")
    for class_key, data in class_Usage_list.items():
        logger.debug(
            "CLASS %s | warmup_end=%d | %d equipment slots",
            class_key,
            data["warmup_end"],
            len(data["items"])
        )

    return solve_model(model, equip_intervals)

      


def solve_model(model, equip_intervals):

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10.0
    status = solver.Solve(model)
    logger.debug("Solver status: %s", solver.StatusName(status))

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        logger.warning("Cannot be solved: %s", solver.StatusName(status))
        # build unresolved schedule from raw requested times
        unresolved = build_unresolved_schedule(equip_intervals)
        return {
            "status": "infeasible", 
            "coaches": unresolved["coaches"],
            "conflicts": unresolved["conflicts"]
        }

    # Group equip_intervals by (print_col, requested_time) — one group per class
    from collections import defaultdict
    class_groups = defaultdict(list)
    for entry in equip_intervals:
        class_key = (entry["print_col"], entry["requested_time"])
        class_groups[class_key].append(entry)

    # Sort classes within each coach by actual solved start time
    # Then sort all classes across coaches by print_col then start time
    sorted_classes = sorted(
        class_groups.items(),
        key=lambda x: (x[0][0], solver.Value(x[1][0]["start"]))
    )

    coaches = {}

    for (print_col, requested_time), entries in sorted_classes:
        if print_col not in coaches:
            coaches[print_col] = {
                "print_col": print_col,
                "blocks": []
            }

        # Sort equipment entries within this class by solved start time
        entries_sorted = sorted(entries, key=lambda e: solver.Value(e["start"]))
        first_entry = entries_sorted[0]
        last_entry = entries_sorted[-1]

        # 1. Add warmup blocks for this class
        if first_entry["warmup_time"] > 0:
            warmup_start = first_entry["start_minutes"]
            warmup_end = warmup_start + first_entry["warmup_time"]
            for t in range(warmup_start, warmup_end, 5):
                coaches[print_col]["blocks"].append({
                    "time": to_time_str(t),
                    "label": "WARM UP",
                    "program": first_entry["program"]
                })
            logger.debug(
                "%s | col %s | WARM UP | %s --> %s",
                first_entry["program"], print_col,
                to_time_str(warmup_start), to_time_str(warmup_end)
            )

        # 2. Add equipment blocks for this class in solved order
        for entry in entries_sorted:
            start_min = solver.Value(entry["start"])
            end_min = solver.Value(entry["end"])
            logger.debug(
                "%s | col %s | %s | %s --> %s",
                entry["program"], print_col, entry["equip"],
                to_time_str(start_min), to_time_str(end_min)
            )
            for t in range(start_min, end_min, 5):
                coaches[print_col]["blocks"].append({
                    "time": to_time_str(t),
                    "label": entry["equip"],
                    "program": entry["program"]
                })

        # 3. Add cooldown blocks for this class
        if last_entry["cooldown_time"] > 0:
            cooldown_start = solver.Value(last_entry["end"])
            cooldown_end = cooldown_start + last_entry["cooldown_time"]
            for t in range(cooldown_start, cooldown_end, 5):
                coaches[print_col]["blocks"].append({
                    "time": to_time_str(t),
                    "label": "COOL DOWN",
                    "program": last_entry["program"]
                })
            logger.debug(
                "%s | col %s | COOL DOWN | %s --> %s",
                last_entry["program"], print_col,
                to_time_str(cooldown_start), to_time_str(cooldown_end)
            )

    return {"status": "ok", "coaches": list(coaches.values())}

def build_unresolved_schedule(equip_intervals):
    from collections import defaultdict

    # Group by class
    class_groups = defaultdict(list)
    for entry in equip_intervals:
        class_key = (entry["print_col"], entry["requested_time"], entry["program"])
        class_groups[class_key].append(entry)

    # Build schedule using requested start times — no solving
    coaches = {}
    equipment_time_usage = defaultdict(list)  # equip -> list of (start, end, program, print_col)

    sorted_classes = sorted(
        class_groups.items(),
        key=lambda x: (x[0][0], x[0][1])
    )

    for (print_col, requested_time, program), entries in sorted_classes:
        if print_col not in coaches:
            coaches[print_col] = {"print_col": print_col, "blocks": []}

        first_entry = entries[0]
        warmup_start = first_entry["start_minutes"]
        warmup_end = warmup_start + first_entry["warmup_time"]
        cursor = warmup_end

        # Add warmup
        if first_entry["warmup_time"] > 0:
            for t in range(warmup_start, warmup_end, 5):
                coaches[print_col]["blocks"].append({
                    "time": to_time_str(t),
                    "label": "WARM UP",
                    "program": program,
                    "conflict": False
                })

        # Add equipment blocks sequentially from warmup end
        for entry in entries:
            start = cursor
            end = cursor + entry["block_time"]

            # Check if this equipment is already used at this time
            conflict = False
            for (existing_start, existing_end, existing_program, existing_col) in equipment_time_usage[entry["equip"]]:
                if start < existing_end and existing_start < end:
                    conflict = True
                    break

            equipment_time_usage[entry["equip"]].append(
                (start, end, program, print_col)
            )

            for t in range(start, end, 5):
                coaches[print_col]["blocks"].append({
                    "time": to_time_str(t),
                    "label": entry["equip"],
                    "program": program,
                    "conflict": conflict
                })
            cursor = end

        # Add cooldown
        if first_entry["cooldown_time"] > 0:
            cooldown_end = cursor + first_entry["cooldown_time"]
            for t in range(cursor, cooldown_end, 5):
                coaches[print_col]["blocks"].append({
                    "time": to_time_str(t),
                    "label": "COOL DOWN",
                    "program": program,
                    "conflict": False
                })

    # Collect conflict descriptions
    conflicts = []
    for equip, usages in equipment_time_usage.items():
        for i in range(len(usages)):
            for j in range(i + 1, len(usages)):
                a_start, a_end, a_prog, a_col = usages[i]
                b_start, b_end, b_prog, b_col = usages[j]
                if a_start < b_end and b_start < a_end:
                    conflicts.append(
                        f"{equip}: {a_prog} (col {a_col}) and "
                        f"{b_prog} (col {b_col}) overlap"
                    )

    return {"coaches": list(coaches.values()), "conflicts": conflicts}



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

    