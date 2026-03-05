"""
define input data,
build solver model
solve it
print the result
"""

from ortools.sat.python import cp_model
import pandas as pd


def to_time_str(min):
    h = min // 60
    m = min % 60
    return f"{h:02d}:{m:02d}"


def test_scheduler():

    user_classes = [{"program": "FUT 8-10", "block": "b11"},
                    {"program": "BBYS B", "block": "b7"}
    ]

    #load event_map spreadsheet-----------------------------------------------------------------
    import pandas as pd

    df = pd.read_excel("event_map.xlsx")

    program_equipment = {
        row["Program"].strip().upper():
        [str(v).strip() for v in row.drop("Program") if pd.notna(v) and str(v).strip().upper() != "EMPTY"]
        for _, row in df.iterrows()
    }

    #print(program_equipment)

    #load time_slots spreadsheet
    df = pd.read_excel("time_slots.xlsx")

    df["start_time"] = df["start_time"].apply(lambda t: t.hour * 60 + t.minute)

    timeBlocks = df.set_index("block_id").to_dict("index")

    #print(timeBlocks)
    #------------------------------------------------------------------------------------------
    
    # create the model
    model = cp_model.CpModel()

    equip_intervals = []
    equip_usage = {}
    classUsage_list = {}

    for entry in user_classes: 
        program = entry["program"]
        block_id = entry["block"]

        equipment_list = program_equipment[program]
        n = len(equipment_list)

        info = timeBlocks[block_id]

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
            classUsage_list.setdefault(class_key, []).append(interval)

            equip_usage.setdefault(equip, []).append(interval)
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

    for class_key, intervals in classUsage_list.items():
        if len(intervals) > 1:
            model.add_no_overlap(intervals)




    # solve

    solver = cp_model.CpSolver()
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
    test_scheduler()