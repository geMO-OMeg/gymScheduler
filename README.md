Constraint Scheduling Engine

Project Overview
An automated scheduling system for a gymnastics facility that generates coach schedules 
by resolving scheduling conflicts. The system integrates a Google Sheets frontend with a 
cloud-based FastAPI backend running a OR-Tools CP-SAT solver.  The result is written back 
to Google Sheets, giving program managers a clear view of assignments.

Tech Stack
Python  
Google 
OR-Tools  
Google Sheets  
Apps Script  
JSON 
APIs  
Google Cloud

Current Status:
- Solver logic (layer 3) under active development
- Apps Script data pipeline (layer 2) tested and running
- Google Sheets UI is built and running. Final aesthetic touches still needed.
- Layer 4 is built and running but still requires PDF generation.

System Architecture
The system is divided into 4 layers:

Layer 1 -- Google Sheets UI
Program managers enter class assignments and coach assignments. Coaches view
printed daily schedules. Output columns D-K are written by the backend and
treated as read-only.

Layer 2 -- Apps Script
Reads input columns A and B per sheet (1 sheet per day of the week). Validates
data before sending. Packages data as JSON, sends HTTPS POST to backend.
Receives JSON response and writes schedule to output columns.

Layer 3 -- Python / FastAPI Backend (Cloud Run)
Receives JSON payload, runs OR-Tools CP-SAT solver to resolve equipment
conflicts. Returns structured JSON schedule. Implements iterative removal loop:
removes the most conflicting class and retries until a feasible solution is
found, then re-adds removed classes as red-flagged blocks.

Layer 4 -- Output Formatter
Maps solver output to per-coach, per-timeslot labels. Written back to Google
Sheets by Apps Script. Color-coded to enable quick and intuitive visual identification.
Future: attendance sheets, coach schedule PDFs.


Scheduler Logic (scheduler.py)
Key functions:
  run_scheduler()          Main entry point. Iterative removal loop -- removes
                           most conflicting class and retries until feasible.
  attempt_solve()          Builds CP-SAT model and calls solve_model(). Returns
                           full coaches response or {status: infeasible}.
  find_most_conflicting()  Counts equipment conflicts per class using time window
                           overlap detection. Uses window size as tiebreaker.
  add_flagged_classes()    Re-adds removed classes as red blocks at requested
                           times, sorted chronologically.
  solve_model()            Runs CP-SAT solver (10s timeout). Builds warmup /
                           equipment / cooldown blocks per class.
  build_unresolved_schedule()  Fallback for total infeasibility. Places all
                               classes sequentially, flags overlaps red.

Solver Constraints:
  - Equipment slots start >= warmup_end and end <= window_end for their class
  - No two slots within the same class overlap (add_no_overlap)
  - Contiguous block constraint: max_end - min_start == total_duration (no gaps)
  - No two classes use the same equipment simultaneously
  - Solver time limit: 10 seconds


Apps Script (Layer 2)
Key functions:
  generateMonday() ... generateSaturday()   Entry points per sheet button.
  generateForDay(dayName)                   Main orchestrator.
  validateClassEntries(rawValues)           Blocks submission on missing time or
                                            program.
  validateCoachOverlaps(classes, event_map) Blocks submission on same-coach
                                            overlapping classes.
  parseTimeSlot(raw, isMorning)             Parses '4:15 -- 10╇10╇5' into
                                            start_minutes, warmup, block,
                                            cooldown. Handles AM/PM.
  readInputSheet(sheet, isMorning)          Reads cols A/B up to MAX_ROW=42.
  readEventMap(ss)                          Reads event_map sheet.
  writeScheduleToSheet(sheet, result,       Clears cols D-K rows 2-201. Writes
    startHour)                              label+program, colors by equipment.
  timeToRow(timeStr, startHour)             Converts time string to sheet row.
  warmUpBackend()                           Pings /ping to prevent cold start.

Saturday is a morning schedule (9am-2pm). isMorning flag is set when
dayName === 'Saturday' and controls time parsing and row mapping.


Deployment
  Platform:   Google Cloud Run -- pay per request, scales to zero when idle
  Container:  Docker image pushed to gcr.io/[project-id]/gym-scheduler
  Redeploy:   ./deploy.sh (docker build + push + gcloud run deploy)
  Logs:       Cloud Run console (StreamHandler only, no file logging)
  Auth:       Currently open (--allow-unauthenticated) -- add auth before
              production handoff


Design Goals: Next Steps / Open Questions / Future Work
  * TEST: Iterative removal loop -- just implemented, not yet tested. Verify
    with a known infeasible configuration (e.g. KINDER+ equipment conflict).
  * Saturday schedule -- isMorning and startHour=9 implemented. Needs full
    end-to-end test after iterative removal is verified.
  * Coach overlap constraint -- currently caught by Apps Script validation only.
    Discussed adding to solver as a future constraint.
  * Infeasibility UX -- alert shows removed classes and why. Red cells show
    conflict location. Consider improving manager guidance messaging.
  * Conflict detection -- pre-solve overlap math used currently. Solver
    infeasibility core not yet implemented (future optimization).
  * Auth on backend -- open endpoint; add API key or Google Cloud IAP before
    production deployment.
  * Multi-day state -- each day solved independently. Cross-day constraints
    not designed.
  * Student rosters -- planned future input, not yet designed.
  * Attendance sheets -- planned output. Separate function from solver.
  * Code cleanup -- full optimization pass planned after all requirements met.


Error Handling (Hybrid)
  Apps Script:
    - validateClassEntries: blocks if program is missing time or vice versa
    - validateCoachOverlaps: blocks if same coach has overlapping classes
    - Conflict alert popup when backend returns removed classes
    - Cell highlighting for conflicts (red #FF4444)
    - Dropdown menus for times and class programs
  Backend:
    - Iterative removal produces a partial feasible schedule rather than failing
    - build_unresolved_schedule() handles total infeasibility as final fallback
    - Named logger 'scheduler' with DEBUG level, StreamHandler for Cloud Run
