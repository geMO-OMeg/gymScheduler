"""
define input data,
build solver model
solve it
print the result
"""

from ortools.sat.python import cp_model
from pathlib import Path
import logging
from collections import defaultdict

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

#Helper method to  
def to_time_str(minutes):
    h = minutes // 60
    m = minutes % 60
    return f"{h:02d}:{m:02d}"

#Helper method for attempt_solve() to identify room constraint
def get_room(equip_name):
    name = equip_name.strip().upper()
    if name.startswith("MINI"):
        return "mini_room"
    if name.startswith("FR"):
        return "fr_room"
    return "main_gym"

#Helper method for attempt_solve() to identify grouping constraint for young classes
MINI_ROOM_PROGRAMS = {"TOTS", "KINDER", "KINDER +", "BBYS", "TOD"}

def is_mini_room_program(program):
    name = program.strip().upper()
    if name.endswith(" B"):
        name = name[:-2].strip()
    return name in MINI_ROOM_PROGRAMS

#Helper method for attempt_solve() to identify competitive classes 
COMPETITIVE_PROGRAMS = {
    "16 HR JO", "12 HR JO", "9 HR JO", "12 HR XCEL",
    "10 HR XCEL", "8 HR XCEL", "LAURELETTES"
}

def is_competitive_program(program):
    name = program.strip().upper()
#    logger.debug("is_competitive check: input='%s' | cleaned='%s' | result=%s",
#                 program, name, name in COMPETITIVE_PROGRAMS)
    return program.strip().upper() in COMPETITIVE_PROGRAMS


def run_scheduler(day, classes, event_map):
    logger.debug("run_scheduler called: day=%s, %d classes", day, len(classes))

    program_equipment = {
        entry["program"].strip().upper(): entry["events"]
        for entry in event_map
    }
    #logger.debug("program_equipment loaded: %s", list(program_equipment.keys()))

    remaining = list(classes)
    flagged = []

    while remaining:
        result = attempt_solve(remaining, program_equipment)

        if result["status"] == "ok":
            if flagged:
                result = add_flagged_classes(result, flagged, program_equipment)
                conflict_msgs = []
                for coach in result["coaches"]:
                    for block in coach["blocks"]:
                        if block.get("conflict") and block.get("conflict_with"):
                            msg = (
                                f"{block['program']} (col {coach['print_col']}): "
                                f"{block['label']} conflicts with {block['conflict_with']}"
                            )
                            if msg not in conflict_msgs:
                                conflict_msgs.append(msg)
                result["conflicts"] = conflict_msgs or [
                    f"{c['program']} (col {c['print_col']}) could not be scheduled — equipment conflict"
                    for c in flagged
                ]
            return result

        # Infeasible — find and remove most conflicting class
        problem_class = find_most_conflicting(remaining, program_equipment)
        logger.warning(
            "Removing conflicting class: %s col %s",
            problem_class["program"], problem_class["print_col"]
        )
        flagged.append(problem_class)
        remaining = [c for c in remaining if c != problem_class]

    # Nothing could be solved at all
    return {
        "status": "infeasible",
        "coaches": [],
        "conflicts": [
            f"{c['program']} (col {c['print_col']}) could not be scheduled"
            for c in flagged
        ]
    }



def find_most_conflicting(classes, program_equipment):
    conflict_counts = {}

    for i, a in enumerate(classes):
        prog_a = a["program"].strip().upper()
        equip_a = set(program_equipment.get(prog_a, []))
        a_start = a["start_minutes"] + a["warmup_time"]
        a_end = a_start + a["block_time"] * len(equip_a)
        count = 0

        for j, b in enumerate(classes):
            if i == j:
                continue
            prog_b = b["program"].strip().upper()
            equip_b = set(program_equipment.get(prog_b, []))
            shared = equip_a & equip_b
            if not shared:
                continue
            b_start = b["start_minutes"] + b["warmup_time"]
            b_end = b_start + b["block_time"] * len(equip_b)
            if a_start < b_end and b_start < a_end:
                count += 1

        # Use window size as tiebreaker — smaller window = more constrained
        window_size = a_end - a_start
        conflict_counts[i] = (count, -window_size)

    # Return class with highest conflict count, smallest window as tiebreaker
    most_conflicting_index = max(conflict_counts, key=lambda i: conflict_counts[i])
    return classes[most_conflicting_index]






def add_flagged_classes(result, flagged, program_equipment):
    coaches = {c["print_col"]: c for c in result["coaches"]}

    # Build a map of already-scheduled equipment usage: equip -> list of (start_min, end_min, program)
    scheduled_usage = {}
    for coach in result["coaches"]:
        cursor = None
        for block in coach["blocks"]:
            if block["label"] in ("WARM UP", "COOL DOWN"):
                continue
            t = int(block["time"].replace(":", ""))
            # Convert HHMM back to minutes
            h, m = divmod(int(block["time"].split(":")[0]) * 60 + int(block["time"].split(":")[1]), 60)
            t_min = int(block["time"].split(":")[0]) * 60 + int(block["time"].split(":")[1])
            equip = block["label"]
            scheduled_usage.setdefault(equip, []).append((t_min, t_min + 5, block["program"]))

    for entry in flagged:
        print_col = entry["print_col"]
        program = entry["program"].strip().upper()
        equipment_list = program_equipment.get(program, [])
        start_minutes = entry["start_minutes"]
        warmup_time = entry["warmup_time"]
        block_time = entry["block_time"]
        cooldown_time = entry["cooldown_time"]

        if print_col not in coaches:
            coaches[print_col] = {"print_col": print_col, "blocks": []}

        cursor = start_minutes

        # Warmup — never flagged
        if warmup_time > 0:
            for t in range(cursor, cursor + warmup_time, 5):
                coaches[print_col]["blocks"].append({
                    "time": to_time_str(t),
                    "label": "WARM UP",
                    "program": entry["program"],
                    "conflict": False
                })
            cursor += warmup_time

        # Equipment blocks — only flag if this specific block overlaps a scheduled class
        for equip in equipment_list:
            block_start = cursor
            block_end = cursor + block_time
           
            # Check if this equipment has any overlap with already-scheduled usage
            usages = scheduled_usage.get(equip, [])
            overlapping_programs = [
                prog for (s, e, prog) in usages
                if block_start < e and s < block_end
            ]
            is_conflict = len(overlapping_programs) > 0
            conflicting_with = overlapping_programs[0] if overlapping_programs else None

            for t in range(block_start, block_end, 5):
                block = {
                    "time": to_time_str(t),
                    "label": equip,
                    "program": entry["program"],
                    "conflict": is_conflict
                }
                if conflicting_with:
                    block["conflict_with"] = conflicting_with
                coaches[print_col]["blocks"].append(block)
            cursor += block_time

        # Cooldown — never flagged
        if cooldown_time > 0:
            for t in range(cursor, cursor + cooldown_time, 5):
                coaches[print_col]["blocks"].append({
                    "time": to_time_str(t),
                    "label": "COOL DOWN",
                    "program": entry["program"],
                    "conflict": False
                })

    for print_col, coach_data in coaches.items():
        coach_data["blocks"].sort(key=lambda b: int(b["time"].replace(":", "")))

    result["coaches"] = list(coaches.values())
    return result






def attempt_solve(classes, program_equipment):
    """
    Builds and solves the CP-SAT model for a single day schedule.
    
    Args:
        classes: list of class dicts from Apps Script payload
        program_equipment: dict mapping program name -> list of equipment
    
    Returns:
        dict with status, coaches, and optional conflicts
    """
    model = cp_model.CpModel()
    equip_intervals = []
    equip_usage = {}
    room_usage = {}
    bg_floor_usage = {"restricted_comp": [], "shared_comp": [], "rec": []}
    class_usage_list = {}
    break_deviations = []
    priority_deviations = []

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
            logger.warning("No equipment found for program: %s", program)
            continue

        logger.debug(
            "ENTRY | program=%s | print_col=%s | start_minutes=%d (%s) | warmup=%d | block=%d | cooldown=%d",
            program, print_col, start_minutes, to_time_str(start_minutes),
            warmup_time, block_time, cooldown_time
        )

        n = len(equipment_list)
        window_start = start_minutes + warmup_time
        break_duration = 15 if is_competitive_program(program) else 0
        window_end = window_start + (block_time * n) + break_duration

        class_key = (program, print_col, requested_time)
        class_usage_list[class_key] = {
            "warmup_end": window_start,
            "window_end": window_end,
            "items": []
        }

        # Build interval variables for each equipment block
        _build_equipment_intervals(
            model, entry, program, print_col, requested_time,
            equipment_list, block_time, window_start, window_end,
            equip_usage, room_usage, bg_floor_usage,
            class_usage_list, class_key, equip_intervals
        )

        # Per-class constraints
        _apply_grouping_constraint(
            model, program, print_col, equipment_list,
            class_usage_list, class_key, window_start, window_end
        )

        _apply_break_constraint(
            model, program, print_col, equipment_list,
            block_time, n, window_start, window_end,
            class_usage_list, class_key,
            break_deviations, priority_deviations
        )

    # Cross-class constraints
    _apply_equipment_conflict_constraints(model, equip_usage)
    _apply_room_constraints(model, room_usage)
    _apply_bg_floor_sharing_constraints(model, bg_floor_usage)

    # Intra-class constraints
    _apply_intra_class_constraints(
        model, class_usage_list, equip_intervals
    )

    # Objective
    _apply_objective(model, break_deviations, priority_deviations)

    return solve_model(model, equip_intervals, class_usage_list)


# ── Interval building ──────────────────────────────────────────────────────────

def _build_equipment_intervals(
    model, entry, program, print_col, requested_time,
    equipment_list, block_time, window_start, window_end,
    equip_usage, room_usage, bg_floor_usage,
    class_usage_list, class_key, equip_intervals
):
    """
    Creates CP-SAT interval variables for each equipment block in a class
    and registers them in equip_usage, room_usage, bg_floor_usage,
    class_usage_list, and equip_intervals.

    Args:
        model: CP-SAT model
        entry: raw class dict from payload
        program: uppercase program name
        print_col: coach column letter
        requested_time: time string from Apps Script
        equipment_list: list of equipment names for this program
        block_time: duration in minutes per equipment block
        window_start: earliest start minute for equipment blocks
        window_end: latest end minute for equipment blocks
        equip_usage: dict mapping equipment name -> list of intervals
        room_usage: dict mapping room name -> list of intervals
        bg_floor_usage: dict with restricted_comp/shared_comp/rec interval lists
        class_usage_list: dict mapping class_key -> class data
        class_key: tuple (program, print_col, requested_time)
        equip_intervals: flat list of all interval dicts across all classes

    Returns:
        None — mutates all passed dicts/lists in place
    """
    for equip in equipment_list:
        duration = block_time

        if window_end - duration < window_start:
            logger.warning(
                "Window too small for %s | %s | window_start=%d window_end=%d duration=%d",
                program, equip, window_start, window_end, duration
            )
            continue

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

        equip_usage.setdefault(equip, []).append(interval)

        room = get_room(equip)
        room_usage.setdefault(room, []).append(interval)

        # BG Floor classification
        if equip.strip().upper() == "BG FLOOR":
            if is_competitive_program(program) and program in {"8 HR XCEL", "LAURELETTES"}:
                bg_floor_usage["shared_comp"].append(interval)
            elif is_competitive_program(program):
                bg_floor_usage["restricted_comp"].append(interval)
            else:
                bg_floor_usage["rec"].append(interval)

        class_usage_list[class_key]["items"].append({
            "start": start_var,
            "end": end_var,
            "interval": interval
        })

        equip_intervals.append({
            "program": program,
            "print_col": print_col,
            "requested_time": requested_time,
            "start_minutes": entry["start_minutes"],
            "warmup_time": entry["warmup_time"],
            "block_time": block_time,
            "cooldown_time": entry["cooldown_time"],
            "equip": equip,
            "start": start_var,
            "end": end_var,
        })


# ── Grouping constraint ────────────────────────────────────────────────────────

def _apply_grouping_constraint(
    model, program, print_col, equipment_list,
    class_usage_list, class_key, window_start, window_end
):
    """
    Ensures mini equipment blocks are grouped together and not sandwiched
    between non-mini blocks. Applies only to young rec programs.
    Valid orderings: mini-mini-large or large-mini-mini.
    Invalid: mini-large-mini.

    Args:
        model: CP-SAT model
        program: uppercase program name
        print_col: coach column letter
        equipment_list: list of equipment names for this program
        class_usage_list: dict mapping class_key -> class data
        class_key: tuple (program, print_col, requested_time)
        window_start: earliest start minute for equipment blocks
        window_end: latest end minute for equipment blocks

    Returns:
        None — adds constraints to model in place
    """
    if not is_mini_room_program(program):
        return

    items = class_usage_list[class_key]["items"]
    if len(items) <= 1:
        return

    mini_items = [
        item for item, equip in zip(items, equipment_list)
        if get_room(equip) == "mini_room"
    ]
    non_mini_items = [
        item for item, equip in zip(items, equipment_list)
        if get_room(equip) != "mini_room"
    ]

    if not mini_items or not non_mini_items:
        return

    mini_first = model.new_bool_var(f"mini_first_{program}_{print_col}")

    mini_max_end = model.new_int_var(window_start, window_end, f"mini_max_end_{program}_{print_col}")
    non_mini_max_end = model.new_int_var(window_start, window_end, f"non_mini_max_end_{program}_{print_col}")
    mini_min_start = model.new_int_var(window_start, window_end, f"mini_min_start_{program}_{print_col}")
    non_mini_min_start = model.new_int_var(window_start, window_end, f"non_mini_min_start_{program}_{print_col}")

    model.add_max_equality(mini_max_end, [i["end"] for i in mini_items])
    model.add_max_equality(non_mini_max_end, [i["end"] for i in non_mini_items])
    model.add_min_equality(mini_min_start, [i["start"] for i in mini_items])
    model.add_min_equality(non_mini_min_start, [i["start"] for i in non_mini_items])

    model.add(mini_max_end <= non_mini_min_start).only_enforce_if(mini_first)
    model.add(non_mini_max_end <= mini_min_start).only_enforce_if(mini_first.Not())

    logger.debug("Grouping constraint added for %s | col %s", program, print_col)


# ── Break and priority constraint ──────────────────────────────────────────────

def _apply_break_constraint(
    model, program, print_col, equipment_list,
    block_time, n, window_start, window_end,
    class_usage_list, class_key,
    break_deviations, priority_deviations
):
    """
    For competitive classes: adds a moveable 15-minute break interval that
    cannot overlap any equipment block, must have at least one block before
    and after it, and prefers placement near the class midpoint.
    Also adds soft preference for Comp Vault and BG Floor to start early.

    Args:
        model: CP-SAT model
        program: uppercase program name
        print_col: coach column letter
        equipment_list: list of equipment names for this program
        block_time: duration in minutes per equipment block
        n: number of equipment blocks
        window_start: earliest start minute for equipment blocks
        window_end: latest end minute for equipment blocks
        class_usage_list: dict mapping class_key -> class data
        class_key: tuple (program, print_col, requested_time)
        break_deviations: list to accumulate break deviation variables
        priority_deviations: list to accumulate priority deviation variables

    Returns:
        None — adds constraints to model and mutates deviation lists in place
    """
    if not is_competitive_program(program):
        return

    break_duration = 15

    logger.debug(
        "COMP WINDOW | %s | window_start=%d (%s) | window_end=%d (%s) | "
        "block_time=%d | n=%d | total_blocks=%d | break=15 | available=%d",
        program, window_start, to_time_str(window_start),
        window_end, to_time_str(window_end),
        block_time, n, block_time * n,
        window_end - window_start - (block_time * n)
    )

    break_start = model.new_int_var(
        window_start,
        window_end - break_duration,
        f"break_start_{program}_{print_col}"
    )
    break_end = model.new_int_var(
        window_start + break_duration,
        window_end,
        f"break_end_{program}_{print_col}"
    )
    break_interval = model.new_interval_var(
        break_start,
        break_duration,
        break_end,
        f"break_interval_{program}_{print_col}"
    )

    items = class_usage_list[class_key]["items"]
    model.add_no_overlap([item["interval"] for item in items] + [break_interval])

    # Hard constraint 1 — at least one block before break
    model.add(break_start >= window_start + block_time)

    # Hard constraint 2 — at least one block after break
    model.add(break_end <= window_end - block_time)

    # Soft preference — break near midpoint
    midpoint = window_start + (block_time * n) // 2
    deviation = model.new_int_var(
        0,
        window_end - window_start,
        f"break_deviation_{program}_{print_col}"
    )
    model.add_abs_equality(deviation, break_start - midpoint)
    break_deviations.append(deviation)

    class_usage_list[class_key]["break"] = {
        "start": break_start,
        "end": break_end
    }

    logger.debug(
        "Break constraint added for %s | col %s | midpoint=%s",
        program, print_col, to_time_str(midpoint)
    )

    # Soft preference — Comp Vault and BG Floor as early as possible
    PRIORITY_EQUIPMENT = {"COMP VAULT", "BG FLOOR"}
    for item, equip in zip(items, equipment_list):
        if equip.strip().upper() in PRIORITY_EQUIPMENT:
            prio_deviation = model.new_int_var(
                0,
                window_end - window_start,
                f"prio_dev_{program}_{print_col}_{equip}"
            )
            model.add(prio_deviation == item["start"] - window_start)
            priority_deviations.append(prio_deviation)
            logger.debug(
                "Priority preference added for %s | %s | col %s",
                equip, program, print_col
            )


# ── Cross-class equipment constraints ──────────────────────────────────────────

def _apply_equipment_conflict_constraints(model, equip_usage):
    """
    Prevents any two classes from using the same equipment simultaneously.
    BG Floor is excluded here and handled separately by
    _apply_bg_floor_sharing_constraints().

    Args:
        model: CP-SAT model
        equip_usage: dict mapping equipment name -> list of intervals

    Returns:
        None — adds constraints to model in place
    """
    for equip, intervals in equip_usage.items():
        if equip.strip().upper() == "BG FLOOR":
            continue
        if len(intervals) > 1:
            model.add_no_overlap(intervals)


# ── Room constraints ───────────────────────────────────────────────────────────

def _apply_room_constraints(model, room_usage):
    """
    Prevents any two classes from occupying the same room simultaneously.
    Rooms are derived from equipment name prefixes:
      MINI* -> mini_room, FR* -> fr_room, everything else -> main_gym.

    Args:
        model: CP-SAT model
        room_usage: dict mapping room name -> list of intervals

    Returns:
        None — adds constraints to model in place
    """
    for room, intervals in room_usage.items():
        if len(intervals) > 1:
            model.add_no_overlap(intervals)


# ── BG Floor sharing constraints ───────────────────────────────────────────────

def _apply_bg_floor_sharing_constraints(model, bg_floor_usage):
    """
    Implements BG Floor sharing rules:
      - restricted_comp (all comp except 8 HR XCEL and Laurelettes)
        cannot overlap with anyone on BG Floor
      - shared_comp (8 HR XCEL and Laurelettes) cannot overlap with
        each other but CAN overlap with rec classes
      - rec classes cannot overlap with each other on BG Floor

    Args:
        model: CP-SAT model
        bg_floor_usage: dict with keys restricted_comp, shared_comp, rec
                        each mapping to a list of intervals

    Returns:
        None — adds constraints to model in place
    """
    all_bg = (
        bg_floor_usage["restricted_comp"] +
        bg_floor_usage["shared_comp"] +
        bg_floor_usage["rec"]
    )

    # restricted_comp cannot overlap with anyone
    for restricted in bg_floor_usage["restricted_comp"]:
        others = [i for i in all_bg if i != restricted]
        for other in others:
            model.add_no_overlap([restricted, other])

    # shared_comp cannot overlap with each other
    if len(bg_floor_usage["shared_comp"]) > 1:
        model.add_no_overlap(bg_floor_usage["shared_comp"])

    # rec cannot overlap with each other
    if len(bg_floor_usage["rec"]) > 1:
        model.add_no_overlap(bg_floor_usage["rec"])

    # shared_comp vs rec — overlap allowed, no constraint added


# ── Intra-class constraints ────────────────────────────────────────────────────

def _apply_intra_class_constraints(model, class_usage_list, equip_intervals):
    """
    Enforces per-class constraints:
      - Each equipment block starts after warmup ends
      - Each equipment block ends before window ends
      - No two equipment blocks within the same class overlap
      - Equipment blocks are contiguous (no gaps), with break duration
        accounted for in competitive classes

    Args:
        model: CP-SAT model
        class_usage_list: dict mapping class_key -> class data including items and break
        equip_intervals: flat list of all interval dicts used for total_duration calculation

    Returns:
        None — adds constraints to model in place
    """
    for class_key, data in class_usage_list.items():
        items = data["items"]
        warmup_end = data["warmup_end"]
        window_end = data["window_end"]

        for item in items:
            model.add(item["start"] >= warmup_end)
            model.add(item["end"] <= window_end)

        if len(items) > 1:
            model.add_no_overlap([item["interval"] for item in items])

        total_duration = sum(
            e["block_time"]
            for e in equip_intervals
            if (e["program"], e["print_col"], e["requested_time"]) == class_key
        )

        starts = [item["start"] for item in items]
        ends = [item["end"] for item in items]

        min_start = model.new_int_var(warmup_end, window_end, f"min_start_{class_key}")
        max_end = model.new_int_var(warmup_end, window_end, f"max_end_{class_key}")

        model.add_min_equality(min_start, starts)
        model.add_max_equality(max_end, ends)

        prog_name = class_key[0]
        if is_competitive_program(prog_name) and "break" in data:
            model.add(max_end - min_start == total_duration + 15)
            break_info = data["break"]
            model.add(break_info["start"] >= min_start)
            model.add(break_info["end"] <= max_end)
        else:
            model.add(max_end - min_start == total_duration)


# ── Objective ──────────────────────────────────────────────────────────────────

def _apply_objective(model, break_deviations, priority_deviations):
    """
    Sets the solver objective to minimize the weighted sum of:
      - Break displacement from class midpoint (weight 1)
      - Priority equipment (Comp Vault, BG Floor) displacement
        from window start (weight 2)

    Args:
        model: CP-SAT model
        break_deviations: list of deviation int vars for break placement
        priority_deviations: list of deviation int vars for priority equipment

    Returns:
        None — sets model objective in place
    """
    all_deviations = []
    if break_deviations:
        all_deviations.extend(break_deviations)
    if priority_deviations:
        all_deviations.extend([2 * d for d in priority_deviations])
    if all_deviations:
        model.minimize(sum(all_deviations))



def build_unresolved_schedule(equip_intervals):

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

def solve_model(model, equip_intervals, class_usage_list=None):

    class_usage_list = class_usage_list or {}
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

        # 2b. Add break block if competitive class
        class_key = (entries_sorted[0]["print_col"], entries_sorted[0]["requested_time"])
        #retrieve break from class_usage_list if present
        usage_key = (
            entries_sorted[0]["program"],
            entries_sorted[0]["print_col"],
            entries_sorted[0]["requested_time"]
        )

        logger.debug("looking up break | usage_key=%s | keys in class_usage_list=%s",
                     usage_key, list(class_usage_list.keys()))

        break_data = class_usage_list.get(usage_key, {}).get("break")

        logger.debug("break_data found: %s", break_data is not None)
        logger.debug("BREAK CHECK | usage_key=%s | break_data=%s",
                     usage_key, break_data is not None)

        if break_data:
            try:
                b_start = solver.Value(break_data["start"])
                b_end = solver.Value(break_data["end"])
                logger.debug("BREAK OUTPUT | %s --> %s",
                            to_time_str(b_start), to_time_str(b_end))
                for t in range(b_start, b_end, 5):
                    coaches[print_col]["blocks"].append({
                        "time": to_time_str(t),
                        "label": "BREAK",
                        "program": entries_sorted[0]["program"]
                    })
            except Exception as e:
                logger.error("BREAK VALUE ERROR | %s", str(e))

        # 3. Add cooldown blocks for this class
        if last_entry["cooldown_time"] > 0:
            if break_data:
                b_end_val = solver.Value(break_data["end"])
                cooldown_start = max(solver.Value(last_entry["end"]), b_end_val)
            else:
                cooldown_start = solver.Value(last_entry["end"])
                                     
            cooldown_end = cooldown_start + last_entry["cooldown_time"]
            for t in range(cooldown_start, cooldown_end, 5):
                coaches[print_col]["blocks"].append({
                    "time": to_time_str(t),
                    "label": "COOL DOWN",
                    "program": last_entry["program"]
                })

    for print_col, coach_data in coaches.items():
        coach_data["blocks"].sort(key=lambda b: b["time"])

    return {"status": "ok", "coaches": list(coaches.values())}




if __name__ == "__main__":
    
    #local test - mirrors what apps script would send

    test_classes = [
        {
            "print_col": "D",
            "program": "KINDER",
            "requested_time": "4:15",
            "start_minutes": 255,
            "warmup_time": 10,
            "block_time": 10,
            "cooldown_time": 5
        }
    ]
    test_event_map = [
        {"program": "KINDER", "events": ["Floor", "Mini Beam", "Mini Bar"]},
    ]

    result = run_scheduler("TUESDAY", test_classes, test_event_map)
    for coach in result["coaches"]:
        for block in coach["blocks"]:
            print(block["time"], block["label"])

    