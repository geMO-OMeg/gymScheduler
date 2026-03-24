0.0.0
- initial commit of README, main.py, requirements.txt
- initial commit of .gitignore, event_map.xlsx, programs.xlsx, time_slots.xlsx

0.0.1
- software now schedules classes with similar equipment at similar times to ensure the equipment is not double booked

0.0.2
- fixed issues with scheduler not being able to schedule multiple classes

0.0.3
- cleaned up file system
- added code to access new folder instead of hardcoded paths
- updated README and .gitignore

0.0.4
- moved data loading and solver functionalities to their own functions
- switched from hardcoded file paths to project-root relative pathing using pathlib
- removed hardcoded file paths

0.0.5
- Renamed main.py to scheduler.py (FastAPI requires its entry point to be named main.py).
- Added apps_script/ folder to organize test Apps Script code for potential future use.
- Added apps_script/sheets_toJson_toDrive.ts as a test script to validate JSON data generated from Google Sheets.
- Set up FastAPI to validate data transfer between Apps Script and FastAPI via ngrok before integrating with scheduler code.

0.0.6
scheduler.py
- removed use of .xlsx file dependencies, relevant data will be part of the API payload
- using chained equality to ensure first equipment slot starts exactly at warmup end
- scheduler returns JSON dict instead of printing to console
- output grouped in blocks of 5-min increments (best for apps script parsing)
main.py
- added FastAPI endpoint POST /schedule
- SheduleRequest model accepts payload parameters
- calls run_scheduler() (in scheduler.py) and returns the result as JSON response

0.0.7
- added logging to scheduler.py.  Logs will be saved to log folder in project root
- updated .gitignore to exclude log files