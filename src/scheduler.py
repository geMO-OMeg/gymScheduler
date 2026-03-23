"""
define input data,
build solver model
solve it
print the result
"""

from ortools.sat.python import cp_model
import pandas as pd
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"

"""
#Logging Function
import logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)
#replace print-debug with:
logger.debug("a message about a var: %s", some_var)
"""




def to_time_str(minutes):
    h = minutes // 60
    m = minutes % 60
    return f"{h:02d}:{m:02d}"



def load_data():

    df = pd.read_excel(DATA_DIR / "event_map.xlsx")

    program_equipment = {
        row["Program"].strip().upper():
        [str(v).strip() for v in row.drop("Program") if pd.notna(v) and str(v).strip().upper() != "EMPTY"]
        for _, row in df.iterrows()
    }

    #load time_slots spreadsheet
    df = pd.read_excel(DATA_DIR / "time_slots.xlsx")

    df["start_time"] = df["start_time"].apply(lambda t: t.hour * 60 + t.minute)

    time_Blocks = df.set_index("block_id").to_dict("index")

    return program_equipment, time_Blocks

    
def run_scheduler():

    #For testing
    user_classes = [{"program": "FUT 8-10", "block": "b11"},
                    {"program": "BBYS B", "block": "b7"},
                    {"program": "FUT 10+ B", "block": "b51"}
    ]

    program_equipment, time_Blocks = load_data()

    # create the model
    model = cp_model.CpModel()

    equip_intervals = []
    equip_usage = {}
    class_Usage_list = {}

    for entry in user_classes: 
        program = entry["program"]
        block_id = entry["block"]

        equipment_list = program_equipment[program.strip().upper()]
        n = len(equipment_list)

        info = time_Blocks[block_id]

        start = info["start_time"] + info["warmUp_time"]
        end = start + info["block_time"] * n

        for equip in equipment_list:
            duration = info["block_time"]

            start_var = model.new_int_var(
                start,
                end - duration,
                f"start_{program}_{block_id}_{equip}"
            )

            end_var = model.new_int_var(
                start + duration,
                end,
                f"end_{program}_{block_id}_{equip}"
            )

            interval = model.new_interval_var(
                start_var,
                duration,
                end_var,
                f"interval_{program}_{block_id}_{equip}"
            )

            #track for equipment conflicts
            equip_usage.setdefault(equip, []).append(interval)

            #track for intra-class conflicts
            class_key = (program, block_id)
            class_Usage_list.setdefault(class_key, []).append(interval)

            equip_intervals.append({
                "program": program,
                "block": block_id,
                "equip": equip,
                "start": start_var,
                "end": end_var,
            })

    #equipment conflict contsraint
    for equip, interv in equip_usage.items():
        if len(interv) > 1:
            model.add_no_overlap(interv)

    for class_key, intervals in class_Usage_list.items():
        if len(intervals) > 1:
            model.add_no_overlap(intervals)

    solve_model(model, equip_intervals)


def solve_model(model, equip_intervals):

    # solve

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10.0
    status = solver.Solve(model)


    #output result

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        print("Cannot be solved:\n")
        return
    
    print("Schedule:\n")
    for entry in equip_intervals:
        prog = entry["program"]
        block = entry["block"]
        equipment = entry["equip"]
        startime = solver.Value(entry["start"]) 
        endtime = solver.Value(entry["end"]) 


        print(
            f"{prog:10s} | block {block:4s}  |  {equipment:6s} | "
            f"{to_time_str(startime)} --> {to_time_str(endtime)}"
        )
  

if __name__ == "__main__":
    run_scheduler()

    #TODO: make .xlsx file paths constants at top of file or accept them as parameter to run_scheduler()
    # TODO: split load, model and print into 3 functions: load_data(), build_model(), solve_and_print() 