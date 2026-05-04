Constraint Scheduling Engine

Project Overview
An automated scheduling system for a gymnastics facility that assigns classes
to equipment time slots, resolves equipment conflicts, and writes formatted
daily schedules back to Google Sheets.

Tech Stack
Python | Google OR-Tools | Google Sheets | Apps Script | JSON APIs | Google Cloud Run

Current Status
- Solver logic (layer 3): under active development
- Apps Script data pipeline (layer 2): tested and running
- Google Sheets UI (layer 1): built and running, final aesthetic touches pending
- Output formatter (layer 4): built and running, PDF generation not yet implemented

System Architecture

Layer 1 -- Google Sheets UI
Program managers enter class and coach assignments. Output columns D-K are
written by the backend and treated as read-only. Each weekday has two sheets
(e.g. Monday 1 / Monday 2) representing Week A and Week B schedules.

Layer 2 -- Apps Script
Reads input columns A/B per sheet. Validates entries and coach overlaps before
sending. Packages rec and competitive classes into a dual-sheet JSON payload,
sends HTTPS POST to backend. Receives result.A and result.B and writes each
to the corresponding sheet. Dynamic startHour ensures early-starting classes
(e.g. competitive warmups) are not clipped by the sheet grid.

Layer 3 -- Python / FastAPI Backend (Cloud Run)
Receives JSON payload, runs OR-Tools CP-SAT solver. Returns structured JSON.

Solver behaviour:
- Iterative removal loop: removes most conflicting class, retries until feasible,
  re-adds removed classes as red-flagged blocks
- Room constraints: no two classes share mini room or FR room simultaneously
- Equipment grouping: mini equipment must be contiguous (mini-mini-large or
  large-mini-mini, never mini-large-mini) for young rec classes
- Competitive breaks: 15-minute moveable break interval per competitive class,
  never first or last block, soft preference for midpoint placement
- Contiguous block constraint: equipment blocks within a class have no gaps
  (break duration explicitly accounted for in competitive class windows)
- No two classes use the same equipment simultaneously
- Solver time limit: 10 seconds with iterative removal fallback

Layer 4 -- Output Formatter
Maps solver output to per-coach, per-timeslot labels. Written to Google Sheets
by Apps Script. Color-coded by equipment for visual identification.
Future: attendance sheets, coach schedule PDFs.

Deployment
Platform:   Google Cloud Run (pay per request, scales to zero)
Container:  Docker image → gcr.io/[project-id]/gym-scheduler
Redeploy:   ./deploy.sh (docker build + push + gcloud run deploy)
Logs:       Cloud Run console (StreamHandler, DEBUG level)
Auth:       Currently open — add IAP or API key before production

Next Steps
- Comp vault / BG Floor priority for competitive classes
- 8 HR XCEL / Laurelettes BG Floor sharing with rec classes
- Tots/BBYS vs Kinder simultaneous warning in Apps Script
- Saturday 1:45pm cutoff validation
- Conditioning blocks (manager-flagged, weekly awareness)
- Cross-sheet rec class assignment swap (solver-driven Week A/B placement)
- Lock/freeze system for post-notification schedule changes
- Attendance sheet generation
- Backend auth before production handoff
- PDF generation for coach schedules
- Full code cleanup pass