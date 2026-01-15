# Calendar Tab - Revisit Case Tracking Feature

## Overview
The Calendar tab has been enhanced to track and display cases with revisit/follow-up dates. This allows clinicians to see at a glance which patients need to be revisited on any given day.

## Features

### 1. **Visual Calendar with Revisit Indicators**
- Interactive calendar widget that displays all dates
- Dates with pending revisit cases are highlighted in red (#ffcccc background with red text)
- Click any date to view cases with follow-ups on that day

### 2. **Revisit Cases List**
- When you select a date on the calendar, a table shows all cases with follow-up appointments on that date
- Displays:
  - **Patient Name**: Full name of the patient
  - **Phone**: Patient contact number
  - **Case ID**: Unique case identifier
  - **Status**: Current case status (Open, In Progress, Closed, etc.)
  - **Chief Complaint**: Brief summary of chief complaint
  - **Diagnosis**: Clinical diagnosis

### 3. **Case Management Actions**
Two action buttons allow quick access:
- **Load Selected Case**: Opens the selected case in the "Case Sheet + Treatment Plan" tab for editing
- **Open Selected Patient**: Navigates to the "Patients" tab and selects the corresponding patient

### 4. **Automatic Calendar Updates**
- Calendar is automatically refreshed when a new case is saved
- Only shows active cases (excludes closed cases)
- Displays only cases with valid follow-up dates

## How to Use

### View Upcoming Revisits
1. Go to the "Calendar (Revisit Cases)" tab
2. Red-highlighted dates indicate days with pending revisit cases
3. Click on any red date to see the list of cases with follow-ups that day

### Schedule a Revisit
1. Load a case in the "Case Sheet + Treatment Plan" tab
2. Scroll down to the "Follow-up Date" field
3. Set the follow-up date using the date picker
4. Click "Save Case + Plan"
5. The calendar will automatically update with the new revisit date

### Open a Case from Calendar
1. Select a date with revisits from the calendar
2. Click on a case in the list below
3. Click "Load Selected Case" to open it in edit mode
4. Or click "Open Selected Patient" to view the patient's details

### Follow-up Date Format
- All follow-up dates use the format: **YYYY-MM-DD** (e.g., 2026-01-15)
- Empty follow-up dates are automatically excluded from the calendar

## Database Schema
The feature uses the existing `follow_up_date` field in the `cases` table:

```sql
CREATE TABLE cases (
    ...
    follow_up_date TEXT,  -- YYYY-MM-DD format
    ...
)
```

## Implementation Details

### New Methods Added
1. **`refresh_calendar()`**
   - Loads all cases with follow-up dates from the database
   - Tags dates in the calendar with visual markers
   - Stores case data for quick retrieval

2. **`on_calendar_selected(event=None)`**
   - Handles calendar date selection
   - Populates the case list with matching cases for the selected date

3. **`on_load_selected_case_from_calendar()`**
   - Loads the selected case from the tree view
   - Switches to the Case Sheet tab

4. **`on_open_selected_patient_from_calendar()`**
   - Loads the selected patient from the tree view
   - Switches to the Patients tab
   - Highlights the selected patient

### Modified Methods
- **`on_save_case()`**: Now calls `refresh_calendar()` after saving to update the calendar display

## Color Coding
- **Red background (#ffcccc)**: Dates with pending revisit cases
- **Red text (#cc0000)**: Enhanced visibility for revisit dates

## Query Performance
The calendar uses an indexed query on `follow_up_date` for optimal performance:

```sql
SELECT c.id, c.follow_up_date, p.first_name, p.last_name, p.phone,
       c.chief_complaint, c.diagnosis, c.case_status
FROM cases c
JOIN patients p ON p.id = c.patient_id
WHERE c.follow_up_date IS NOT NULL 
  AND c.follow_up_date != ''
  AND c.case_status != 'Closed'
ORDER BY c.follow_up_date
```

## Future Enhancements
Possible improvements to consider:
- Color-code cases by status (different colors for different urgency levels)
- Show visit count or history
- Generate reminder notifications for upcoming visits
- Export calendar view for printing
- Filter by case status, diagnosis, or patient
- Monthly/weekly view options
