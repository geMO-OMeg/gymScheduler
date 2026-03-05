"""
define input data,
build solver model
solve it
print the result
"""

from ortools.sat.python import cp_model
import pandas as pd

def test_scheduler():

    programs = ["A", "B", "C"]
    coaches = ["Coach1", "Coach2"]
    times = ["T1", "T2", "T3"]

    #load event_map spreadsheet
    import pandas as pd

    df = pd.read_excel("event_map.xlsx")

    program_equipment = {
        row["Program"].strip().upper():
        [str(v).strip() for v in row.drop("Program") if pd.notna(v) and str(v).strip().upper() != "EMPTY"]
        for _, row in df.iterrows()
    }

    print(program_equipment)

    #load time_slots spreadsheet
    df = pd.read_excel("time_slots.xlsx")

    df["start_time"] = df["start_time"].apply(lambda t: t.hour * 60 + t.minute)

    blocks = df.set_index("block_id").to_dict("index")

    print(blocks)
        
    # create the model
    model = cp_model.CpModel()

    
    # is program P assigned to coach C at time T?
    # assign[(program, coach, time)] = 1 if assigned, else 0

    assign = {}

    for p in programs:
        for c in coaches:
            for t in times:
                assign[(p, c, t)] = model.new_bool_var(f"{p}_{c}_{t}")

    # rule: each program is assigned to 1 coach 1 time
   
    for p in programs:
        model.add(
            sum(assign[(p, c, t)] for c in coaches for t in times) == 1
        )
    
    # rule: a coach can only teach on program per time slot

    for c in coaches:
        for t in times:
            model.add(
                sum(assign[(p, c, t)] for p in programs) <= 1
            )
    
    # rule: max programs per coach

    for c in coaches:
        model.add(
            sum(assign[(p, c, t)] for p in programs for t in times) <= 2
        )

    # solve

    solver = cp_model.CpSolver()
    status = solver.Solve(model)


    #output result

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        print("Solution found:\n")
        for p in programs:
            for c in coaches:
                for t in times:
                    if solver.Value(assign[(p, c, t)]) == 1:
                        print(f"Program {p} -> {c} -> at {t}")
    else:
        print("No solution found")


if __name__ == "__main__":
    test_scheduler()