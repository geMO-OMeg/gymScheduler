/*
This Apps Script code exports data from a spreadsheet into a .json file saved in the user’s Google Drive. 
It was used to verify that the generated JSON file contains the correct data formatting and preserves the 
intended order.
*/

const ROWS_PER_COACH = 4;

function debugParseMonday() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName("Monday");
  
  if (!sheet) {
    SpreadsheetApp.getUi().alert("Sheet 'Monday' not found.");
    return;
  }

  const classes = readInputSheet(sheet);
  const payload = {
    day: "Monday",
    parsed_at: new Date().toISOString(),
    class_count: classes.length,
    classes: classes
  };

  const json = JSON.stringify(payload, null, 2);
  saveJsonToDrive(json, "monday_parse_debug.json");
  SpreadsheetApp.getUi().alert("Done! Saved " + classes.length + " classes to monday_parse_debug.json in your Drive.");
}

function readInputSheet(sheet) {
  const values = sheet.getDataRange().getValues();
  const classes = [];

  // Read coach names from row 1 (index 0), columns D onward (index 3+)
  const coachNames = {};
  for (let col = 3; col < values[0].length; col++) {
    const name = String(values[0][col]).trim();
    const letter = String.fromCharCode(65 + col); // col 3 → "D", col 4 → "E" etc.
    if (name) coachNames[letter] = name;
  }

  let i = 1; // start at row 2 (index 1), skip header row
  while (i < values.length) {
    const cellA = String(values[i][0]).trim();
    const cellB = String(values[i][1]).trim();

    // Detect coach block header: single column letter in col A, col B empty
    if (/^[A-J]$/.test(cellA) && !cellB) {
      const printCol = cellA;
      const coachName = coachNames[printCol] || "Unknown";

      // Read next ROWS_PER_COACH rows as class entries
      for (let j = 1; j <= ROWS_PER_COACH; j++) {
        const dataRow = values[i + j];
        if (!dataRow) break;
        const program = String(dataRow[0]).trim();
        const time    = String(dataRow[1]).trim();
        if (program && time) {
          classes.push({
            coach: coachName,
            print_col: printCol,
            program: program,
            requested_time: time
          });
        }
      }
      i += ROWS_PER_COACH + 1;
    } else {
      i++;
    }
  }
  return classes;
}

function saveJsonToDrive(jsonString, filename) {
  const folder = getDriveFolder();
  
  // Overwrite if file already exists
  const existing = folder.getFilesByName(filename);
  while (existing.hasNext()) {
    existing.next().setTrashed(true);
  }

  folder.createFile(filename, jsonString, MimeType.PLAIN_TEXT);
}

function getDriveFolder() {
  // Saves to a folder called "Scheduler Debug" next to your spreadsheet
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const ssFile = DriveApp.getFileById(ss.getId());
  const parents = ssFile.getParents();
  const parentFolder = parents.hasNext() ? parents.next() : DriveApp.getRootFolder();

  // Find or create "Scheduler Debug" subfolder
  const folderName = "Scheduler Debug";
  const existing = parentFolder.getFoldersByName(folderName);
  if (existing.hasNext()) return existing.next();
  return parentFolder.createFolder(folderName);
}
 

