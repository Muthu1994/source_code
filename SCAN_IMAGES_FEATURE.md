# Medical Scan Images Feature

## Overview
A new **Medical Scan Images** section has been added to the Case Sheet tab (below the Patient Consent section) to allow users to upload, manage, and view multiple medical scan images associated with a case.

## Features

### 1. **Add Scan Images**
- Click **"+ Add Scan Images"** button to browse and select multiple image files
- Supported file types:
  - Images: JPG, JPEG, PNG, BMP, GIF, TIFF
  - Documents: PDF
  - All files

### 2. **Scan Type & Notes**
- **Scan Type Dropdown:** Select from predefined types:
  - X-Ray (default)
  - CT Scan
  - MRI
  - Ultrasound
  - Photograph
  - Intra-oral
  - Extra-oral
  - Other
- **Notes Field:** Add optional notes/description for the scan image

### 3. **View Scan Images List**
The scan images list displays:
- **Scan Type** - Medical imaging type
- **File Name** - Name of the uploaded image
- **Upload Date** - Date when image was added
- **Notes** - Associated notes (truncated if longer than 50 characters)

### 4. **View Selected Image**
- Select a scan image from the list
- Click **"View Selected"** to open the image file in default viewer
- Works with images, PDFs, and other viewable file types

### 5. **Delete Scan Image**
- Select a scan image from the list
- Click **"Delete Selected"** to remove the reference from the case
- **Note:** Only the database reference is deleted; the actual file remains on disk

## Database Schema

### New Table: `case_scan_images`
```sql
CREATE TABLE case_scan_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL,           -- Foreign key to cases table
    image_path TEXT NOT NULL,           -- Full file path to the image
    image_type TEXT,                    -- Type of scan (X-Ray, CT, etc.)
    upload_date TEXT,                   -- When the image was uploaded
    notes TEXT,                         -- Optional notes about the image
    created_at TEXT,                    -- Creation timestamp
    FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE CASCADE
);

CREATE INDEX idx_case_scans ON case_scan_images(case_id);
```

## Workflow

1. **Create/Load a Case** - Open a case in the Case Sheet tab
2. **Select Scan Type** - Choose the type of medical scan from dropdown
3. **Add Notes** (Optional) - Add any relevant notes
4. **Upload Images** - Click "Add Scan Images" and select file(s)
5. **View Images** - Select an image and click "View Selected" to open
6. **Remove Images** - Select an image and click "Delete Selected" to remove reference

## Technical Details

### Methods Added:
- `on_add_scan_images()` - Handle multiple file selection and insertion
- `refresh_scan_images_list()` - Load and display scans for current case
- `on_view_scan_image()` - Open selected image in default application
- `on_delete_scan_image()` - Remove image reference from database

### Auto-Refresh:
- Scan images list automatically refreshes when:
  - A case is loaded (`load_case_by_id()`)
  - A new case is created (`on_new_case()`)
  - New images are added (`on_add_scan_images()`)
  - Images are deleted (`on_delete_scan_image()`)

## File Management

### Image Storage:
- **Location:** Images are stored at user-selected paths on the system
- **Reference Storage:** Only file paths are stored in database (not the images themselves)
- **Advantages:**
  - Saves database space
  - Preserves original image quality
  - Images remain in user-accessible locations

### File Path Handling:
- Absolute file paths are stored in database
- File existence is checked before viewing
- User is notified if image file is missing

## UI Layout

```
Case Sheet Tab
├── Patient Information
├── Case Information
├── Chief Complaint
├── Medical & Dental History
├── Clinical Examination & Diagnosis
├── Patient Consent
└── Medical Scan Images ← NEW SECTION
    ├── Buttons: [+ Add Scan Images] [View Selected] [Delete Selected]
    ├── Scan Type: [Dropdown ▼]  Notes: [Text Entry]
    └── Scan Images List (Treeview)
        ├── Scan Type
        ├── File Name
        ├── Upload Date
        └── Notes
```

## Supported File Types

| Type | Extensions | Notes |
|------|-----------|-------|
| Images | .jpg, .jpeg, .png, .bmp, .gif, .tiff | Standard image formats |
| PDF | .pdf | PDF documents, scans |
| Others | .* | Any file type can be added |

## Error Handling

- **Missing Case:** Shows warning if trying to add images without saving a case
- **Invalid Files:** Only existing files are added to database
- **Missing Files:** User notified if image file no longer exists when trying to view
- **Database Errors:** User-friendly error messages for database operations

## Cross-Platform Compatibility

The **View Selected** feature uses platform-specific file opening:
- **Windows:** `os.startfile()`
- **macOS:** `open` command
- **Linux:** `xdg-open` command

## Future Enhancements

Potential features that could be added:
- Image preview thumbnails in the list
- Drag-and-drop file upload
- Image annotation/markup tools
- Batch image operations
- Image compression before storage
- Automatic image organization by type
