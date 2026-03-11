Constraint Scheduling Engine

Project Overview

An automated scheduling system for a gymnastics facility that assigns classes to equipment time slots, 
resolves equipment conflicts between classes and writes formatted daily schedules back to a Google Sheets
document.


Tech Stack

Python
Google OR-Tools
Google Sheets
Apps Script
JSON APIs
Google Cloud


Current Status:
- Solver logic (layer 3) is under active development
- Apps Script data pipeline (layer 2) is scaffolded and tested.
- Layers 1 and 4 are designed but not yet built


System Architecture

The system is divided into 4 layers:

Layer 1 -- Google Sheets UI

Program managers enter class assignments and each coach assignments.
Coaches view their printed daily schedules.
Output columns D-J are written by the backend and treated as read-only.


Layer 2 -- Apps Script

Reads input columns A and B per sheet (1 sheet per day of the week).
Packages data as JSON, sends HTTPS POST to backend.
Receives JSON response and writes schedule to output columns.


Layer 3 -- Python / FastAPI Backend

Receives JSON payload, runs OR-Tools CP-SAT solver to resolve equipment conflicts.
Returns Structured JSON schedule.
Future: more scheduling restrictions based on user requirements.


Layer 4 -- Output Formatter

Maps solver output to per-coach, per-timeslot labels.
Written back to Google Sheets by Apps Script.
Future: attendance sheets, coach schedule PDFs


Design Goals: Next Steps/ Open Questions/ Future Work

- Schedule handling: how to resolve scheduling conflicts? suggest nearest available block? identify conflicting equipment?
- Multi-day state: currently each day is solved independently.  Cross-day constraints not designed.
- Coach scheduling: solver does not yet validate coach conflicts. (does this matter to the user?)
- Student rosters: Planned future input, not yet designed.
- Attendance sheets: planned output product.  Will be generated from a separate function from the solver.
- Auth on backend: backend endpoint will be open... add API key or Google Cloud IAP before deployment?
- Other scheduling restrictions: meet with Project Manager to discuss full schedule restrictions.