#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Clinic App: Patient management + Case sheet with Treatment Plan + Search & History
Built with tkinter clinic_app.py
Requires: Python 3.9 (tkinter, sqlite3 included in standard library)
"""

import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime, timedelta
import os
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

DB_FILE = "clinic.db"
PAGE_SIZE = 50

# ---------------------- Utilities ----------------------

def iso_today():
    return datetime.now().strftime("%Y-%m-%d")

def parse_date(s: str) -> datetime:
    """Return datetime from YYYY-MM-DD or raise ValueError."""
    return datetime.strptime(s, "%Y-%m-%d")

def safe_str(v):
    return (v or "").strip()

def calc_end_date(start_str, duration_days):
    if not start_str or not duration_days:
        return ""
    try:
        start_dt = parse_date(start_str)
        end_dt = start_dt + timedelta(days=int(duration_days))
        return end_dt.strftime("%Y-%m-%d")
    except Exception:
        return ""

# ---------------------- Database Setup ----------------------

def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.executescript(
        """
        PRAGMA foreign_keys = ON;
        
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            gender TEXT,
            dob TEXT,  -- YYYY-MM-DD
            phone TEXT,
            email TEXT,
            address TEXT
        );
        
        CREATE TABLE IF NOT EXISTS cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            op_number INTEGER UNIQUE,  -- Outpatient number (globally unique)
            case_date TEXT NOT NULL DEFAULT (date('now')),  -- YYYY-MM-DD
            follow_up_date TEXT,  -- YYYY-MM-DD
            case_status TEXT DEFAULT 'Open',  -- Open, In Progress, Closed, Cancelled
            chief_complaint TEXT NOT NULL,
            medical_history TEXT,  -- Past Medical History
            dental_history TEXT,  -- Past Dental History
            examination TEXT,  -- Extra & Intra Oral Examinations
            diagnosis TEXT,
            consent_obtained BOOLEAN DEFAULT 0,  -- Whether consent was obtained
            consent_date TEXT,  -- Date consent was obtained
            consent_file_path TEXT,  -- Path to consent form file
            vitals_bp TEXT,  -- e.g., 120/80
            vitals_hr TEXT,  -- bpm
            vitals_temp TEXT,  -- °C
            vitals_weight TEXT,  -- kg
            closed_date TEXT,  -- Date when case was closed
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(patient_id) REFERENCES patients(id) ON DELETE CASCADE
            );
    
        CREATE TABLE IF NOT EXISTS treatment_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL,
            item_type TEXT NOT NULL,  -- Medication / Procedure / Test / Advice
            name TEXT NOT NULL,
            dosage TEXT,
            frequency TEXT,
            duration_days INTEGER,
            start_date TEXT,  -- YYYY-MM-DD
            end_date TEXT,  -- YYYY-MM-DD
            status TEXT,  -- Planned / Ongoing / Completed
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE CASCADE
        );
    
        CREATE INDEX IF NOT EXISTS idx_patients_phone ON patients(phone);
        CREATE INDEX IF NOT EXISTS idx_patients_name ON patients(last_name, first_name);
        CREATE INDEX IF NOT EXISTS idx_cases_patient_date ON cases(patient_id, case_date);
        CREATE INDEX IF NOT EXISTS idx_cases_followup ON cases(follow_up_date);
        CREATE INDEX IF NOT EXISTS idx_cases_status ON cases(case_status);
        """
    )

    conn.commit()
    conn.close()

def migrate_remove_unique_phone():
    """Migration to remove UNIQUE constraint from phone column in existing databases"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        # Check if migration has already been applied by looking at table schema
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='patients'")
        schema = cursor.fetchone()
        
        # If schema contains UNIQUE constraint, migration is needed
        if not schema or "UNIQUE" not in schema[0]:
            # Migration already applied or new database
            return True
        
        print("Running migration: Removing UNIQUE constraint from phone...")
        
        # Create new table without UNIQUE constraint
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS patients_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                gender TEXT,
                dob TEXT,
                phone TEXT,
                email TEXT,
                address TEXT
            )
        """)
        
        # Copy data from old table to new table
        cursor.execute("""
            INSERT INTO patients_new (id, first_name, last_name, gender, dob, phone, email, address)
            SELECT id, first_name, last_name, gender, dob, phone, email, address FROM patients
        """)
        
        # Drop old table
        cursor.execute("DROP TABLE IF EXISTS patients")
        
        # Rename new table to patients
        cursor.execute("ALTER TABLE patients_new RENAME TO patients")
        
        # Recreate indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_patients_phone ON patients(phone)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_patients_name ON patients(last_name, first_name)")
        
        conn.commit()
        print("✓ Migration completed: UNIQUE constraint removed from phone column")
        return True
    except Exception as e:
        print(f"✗ Migration error: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

# ---------------------- PDF Export ----------------------
def my_header(canvas, doc):
    canvas.saveState()
    #Page Dimensions
    page_width, page_height = A4
    header_height = 1.0 * inch
    # Path to your image, x-coordinate, y-coordinate, width, height
    logo_path = "clinic_logo.png"
    canvas.drawImage(logo_path, 0, page_height - header_height, width=page_width, height=header_height, preserveAspectRatio=False)
    canvas.restoreState()

def export_case_to_pdf(case_id, patient_id, output_path):
    """
    Export case details and treatment plan to PDF
    
    Args:
        case_id: ID of the case to export
        patient_id: ID of the patient
        output_path: Full path where PDF should be saved
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # Fetch patient data
        conn = sqlite3.connect(DB_FILE)
        patient = conn.execute(
            "SELECT first_name, last_name, gender, dob, phone, email, address FROM patients WHERE id = ?",
            (patient_id,)
        ).fetchone()
        
        # Fetch case data
        case = conn.execute(
            """SELECT id, op_number, case_date, follow_up_date, case_status, chief_complaint, 
                      medical_history, dental_history, examination, diagnosis,
                      consent_obtained, consent_date, vitals_bp, vitals_hr, vitals_temp, vitals_weight,
                      closed_date
               FROM cases WHERE id = ?""",
            (case_id,)
        ).fetchone()
        
        # Fetch treatment plans
        plans = conn.execute(
            """SELECT item_type, name, dosage, frequency, duration_days, start_date, end_date, status, notes
               FROM treatment_plans WHERE case_id = ? ORDER BY id""",
            (case_id,)
        ).fetchall()
        
        conn.close()
        
        if not patient or not case:
            return False
        
        # Create PDF
        doc = SimpleDocTemplate(output_path, pagesize=A4,
                                rightMargin=0.75*inch, leftMargin=0.75*inch,
                                topMargin=1*inch, bottomMargin=0.75*inch)
        
        # Styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            textColor=colors.HexColor('#1f4788'),
            spaceAfter=6,
            alignment=TA_CENTER
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=12,
            textColor=colors.HexColor('#1f4788'),
            spaceAfter=6,
            spaceBefore=12,
            borderBottom=1,
            borderColor=colors.HexColor('#1f4788')
        )
        
        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontSize=10,
            leading=14
        )

        styleN = styles["BodyText"]
        
        # Extract data
        first_name, last_name, gender, dob, phone, email, address = patient
        op_num, case_date, follow_up, status, chief_complaint, med_hist, dental_hist, exam, diagnosis, \
        consent_obtained, consent_date, bp, hr, temp, weight, closed_date = case[1:]
        
        # Build content
        story = []
        
        # Title
        story.append(Spacer(1, 0.15*inch))
        story.append(Paragraph("CASE SHEET", title_style))
        
        
        # Patient Information
        story.append(Paragraph("PATIENT INFORMATION", heading_style))
        patient_data = [
            ['First Name:', first_name or ''],
            ['Last Name:', last_name or ''],
            ['Gender:', gender or ''],
            ['Date of Birth:', dob or ''],
            ['Phone:', phone or ''],
            ['Email:', email or ''],
            ['Address:', address or '']
        ]
        
        patient_table = Table(patient_data, colWidths=[2*inch, 4.5*inch])
        patient_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e8f0f8')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey)
        ]))
        story.append(patient_table)
        story.append(Spacer(1, 0.15*inch))
        
        # Case Information
        story.append(Paragraph("CASE INFORMATION", heading_style))
        case_data = [
            ['OP Number:', str(op_num) if op_num else ''],
            ['Case Date:', case_date or ''],
            ['Follow-up Date:', follow_up or 'N/A'],
            ['Status:', status or ''],
            ['Closed Date:', closed_date or 'N/A']
        ]
        
        case_table = Table(case_data, colWidths=[2*inch, 4.5*inch])
        case_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e8f0f8')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey)
        ]))
        story.append(case_table)
        story.append(Spacer(1, 0.2*inch))
        
        # Chief Complaint
        story.append(Paragraph("CHIEF COMPLAINT", heading_style))
        story.append(Paragraph(chief_complaint or 'Not specified', normal_style))
        story.append(Spacer(1, 0.15*inch))
        
        # Medical & Dental History
        story.append(Paragraph("MEDICAL & DENTAL HISTORY", heading_style))
        history_data = [
            ['Past Medical History:', med_hist or 'Not specified'],
            ['Past Dental History:', dental_hist or 'Not specified']
        ]
        
        history_table = Table(history_data, colWidths=[2*inch, 4.5*inch])
        history_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e8f0f8')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey)
        ]))
        story.append(history_table)
        story.append(Spacer(1, 0.2*inch))
        
        # Clinical Examination
        story.append(Paragraph("CLINICAL EXAMINATION & DIAGNOSIS", heading_style))
        exam_data = [
            ['Examination:', exam or 'Not specified'],
            ['Diagnosis:', diagnosis or 'Not specified']
        ]
        
        exam_table = Table(exam_data, colWidths=[2*inch, 4.5*inch])
        exam_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e8f0f8')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey)
        ]))
        story.append(exam_table)
        story.append(Spacer(1, 0.2*inch))
        
        # Vital Signs
        if bp or hr or temp or weight:
            story.append(Paragraph("VITAL SIGNS", heading_style))
            vitals_data = [
                ['BP (mmHg):', bp or ''],
                ['HR (bpm):', hr or ''],
                ['Temperature (°C):', temp or ''],
                ['Weight (kg):', weight or '']
            ]
            
            vitals_table = Table(vitals_data, colWidths=[2*inch, 4.5*inch])
            vitals_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e8f0f8')),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey)
            ]))
            story.append(vitals_table)
            story.append(Spacer(1, 0.2*inch))
        
        # Treatment Plan
        if plans:
            story.append(PageBreak())
            story.append(Paragraph("TREATMENT PLAN", heading_style))
            
            plan_data = [['Type', 'Name', 'Dosage', 'Frequency', 'Duration', 'Start Date', 'End Date', 'Status']]
            for plan in plans:
                plan_data.append([
                    plan[0] or '',  # type
                    Paragraph(plan[1] or '', styleN),  # name
                    plan[2] or '',  # dosage
                    plan[3] or '',  # frequency
                    str(plan[4]) if plan[4] else '',  # duration
                    plan[5] or '',  # start_date
                    plan[6] or '',  # end_date
                    plan[7] or ''   # status
                ])
            
            plan_table = Table(plan_data, colWidths=[0.6*inch, 1.2*inch, 0.8*inch, 0.8*inch, 0.6*inch, 0.9*inch, 0.9*inch, 0.7*inch])
            plan_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f0f0')])
            ]))
            story.append(plan_table)
        
        # Consent Information
        if consent_obtained:
            story.append(Spacer(1, 0.2*inch))
            story.append(Paragraph("PATIENT CONSENT", heading_style))
            consent_data = [
                ['Consent Obtained:', 'Yes'],
                ['Consent Date:', consent_date or '']
            ]
            
            consent_table = Table(consent_data, colWidths=[2*inch, 4.5*inch])
            consent_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e8f0f8')),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey)
            ]))
            story.append(consent_table)
        
        # Footer with timestamp
        story.append(Spacer(1, 0.3*inch))
        footer_text = f"<b>Generated on:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        story.append(Paragraph(footer_text, normal_style))
        
        # Build PDF
        doc.build(story, onFirstPage=my_header, onLaterPages=my_header)
        return True
        
    except Exception as e:
        print(f"PDF Export Error: {e}")
        import traceback
        traceback.print_exc()
        return False

# ---------------------- Main App ----------------------

class ClinicApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Clinic App: Patient & Case Management")
        self.geometry("1200x800")
        self.minsize(1050, 740)
        
        # Initialize database and run migrations
        init_db()
        migrate_remove_unique_phone()
        
        # State
        self.current_patient_id = None
        self.current_case_id = None
        self.plan_items = []  # in-memory list of dicts for treatment plan
        self.search_page = 0  # pagination page for Browse/Search
        
        self.make_style()
        self.build_menu()
        self.build_ui()

    # ---------- UI & Menu ----------

    def make_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
    
        style.configure("TLabel", padding=(2, 2))
        style.configure("TEntry", padding=(2, 2))
        style.configure("TButton", padding=(6, 4))

    def build_menu(self):
        menubar = tk.Menu(self)        
        filem = tk.Menu(menubar, tearoff=0)
        filem.add_command(label="New Patient", command=self.on_new_patient)
        filem.add_command(label="New Case", command=self.on_new_case)
        filem.add_separator()
        filem.add_command(label="Exit", command=self.destroy)
        menubar.add_cascade(label="File", menu=filem)
        
        helpm = tk.Menu(menubar, tearoff=0)
        helpm.add_command(label="About", command=lambda: messagebox.showinfo(
            "About", "Clinic App\ntkinter + sqlite3\nManage patients, cases, treatment plans and history."))
        menubar.add_cascade(label="Help", menu=helpm)
        self.config(menu=menubar)

    def build_ui(self):

        main_continer = ttk.Frame(self)
        main_continer.pack(fill="both", expand=True, padx=8, pady=8)
        main_continer.rowconfigure(0, weight=1)
        main_continer.rowconfigure(1, weight=0)
        main_continer.columnconfigure(0, weight=1)
        
        nb = ttk.Notebook(main_continer)
        nb.grid(row=0, column=0, sticky="nsew", pady=(0,8))
        self.nb = nb
        
        self.tab_patients = ttk.Frame(nb, padding=10)
        self.tab_case = ttk.Frame(nb, padding=10)
        self.tab_browse = ttk.Frame(nb, padding=10)
        
        nb.add(self.tab_patients, text="Patients")
        nb.add(self.tab_case, text="Case Sheet + Treatment Plan")
        nb.add(self.tab_browse, text="Browse / Search")
        
        self.build_patients_tab()
        self.build_case_tab()
        self.build_browse_tab()
        
        # Bottom buttons
        bottom = ttk.Frame(main_continer, padding=(8, 4))
        bottom.grid(row=1, column=0, sticky="ew")
                
        # Right side buttons
        ttk.Button(bottom, text="Close Case", command=self.on_close_case).pack(side="right",padx=(0, 6))
        ttk.Button(bottom, text="Export to PDF", command=self.on_export_case_to_pdf).pack(side="right",padx=(0, 6))
        ttk.Button(bottom, text="Save Case + Plan", command=self.on_save_case).pack(side="right")
        ttk.Button(bottom, text="New Case", command=self.on_new_case).pack(side="right", padx=(0, 6))

    # --------- Patients Tab ---------

    def build_patients_tab(self):
        f = self.tab_patients
        f.configure(padding=0)

        # Configure main grid
        f.columnconfigure(0, weight=1)
        f.rowconfigure(2, weight=1) #Make the main content area expndable

        #Search filters
        # ===== TOP SECTION: SEARCH AND ACTIONS ===
        search_section = ttk.LabelFrame(f, text= "Search Patients", padding=15)
        search_section.grid(row=0, column=0, sticky="ew", pady=(0,10))
        search_section.columnconfigure(1, weight=1)
        search_section.columnconfigure(3, weight=1)

        self.var_p_name = tk.StringVar()
        self.var_p_phone = tk.StringVar()

        #Search inputs
        ttk.Label(search_section, text="Patient Name:", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", padx=(0,8))
        name_entry = ttk.Entry(search_section, textvariable=self.var_p_name, font=("Segoe UI", 9))
        name_entry.grid(row=0, column=1, sticky="ew", padx=(0,20))

        ttk.Label(search_section, text="Phone Number:", font=("Segoe UI", 9, "bold")).grid(row=0, column=2, sticky="w", padx=(0,8))
        phone_entry = ttk.Entry(search_section, textvariable=self.var_p_phone, font=("Segoe UI", 9))
        phone_entry.grid(row=0, column=3, sticky="ew", padx=(0,20))

        # Search Button
        btn_frame = ttk.Frame(search_section)
        btn_frame.grid(row=0, column=4, padx=(10,0))

        search_btn = ttk.Button(btn_frame, text="Search", command=self.on_patients_search)
        search_btn.grid(row=0, column=0, padx=2)

        clear_btn = ttk.Button(btn_frame, text="Clear", command=self.on_patients_clear)
        clear_btn.grid(row=0, column=1, padx=2)

        # Bind Enter key to search
        name_entry.bind('<Return>', lambda e: self.on_patients_search())
        phone_entry.bind('<Return>', lambda e: self.on_patients_search())
        
        
        # Patient form
        
        form_section = ttk.LabelFrame(f, text="Patient Information", padding=15)
        form_section.grid(row=1, column=0, sticky="ew", pady=(0, 10))

        # Configure form grid
        for i in range(0, 6):
            form_section.columnconfigure(i, weight=1)
            
        # Initialize variables
        self.var_first = tk.StringVar()
        self.var_last = tk.StringVar()
        self.var_gender = tk.StringVar()
        self.var_dob = tk.StringVar(value="")
        self.var_phone = tk.StringVar()
        self.var_email = tk.StringVar()
        self.var_address = tk.StringVar()
        
        ttk.Label(form_section, text="First Name *:", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", pady=5)
        first_entry = ttk.Entry(form_section, textvariable=self.var_first, font=("Segoe UI", 9))
        first_entry.grid(row=0, column=1, sticky="ew", padx=(5, 15), pady=5)
        
        ttk.Label(form_section, text="Last Name *", font=("Segoe UI", 9, "bold")).grid(row=0, column=2, sticky="w", pady=5)
        last_entry = ttk.Entry(form_section, textvariable=self.var_last, font=("Segoe UI", 9))
        last_entry.grid(row=0, column=3, sticky="ew", padx=(5, 15), pady=5)
        
        ttk.Label(form_section, text="Gender", font=("Segoe UI", 9, "bold")).grid(row=1, column=0, sticky="w", pady=5)
        gender_combo = ttk.Combobox(form_section, textvariable=self.var_gender, values=("Male", "Female", "Other"), state="readonly", font=("Segoe UI", 9))
        gender_combo.grid(row=1, column=1, sticky="ew", padx=(5, 15), pady=5)
        
        ttk.Label(form_section, text="Date of Birth:", font=("Segoe UI", 9, "bold")).grid(row=1, column=2, sticky="w", pady=5)
        dob_frame = ttk.Frame(form_section)
        dob_frame.grid(row=1, column=3, sticky="ew", padx=(5, 15), pady=5)
        dob_frame.columnconfigure(0, weight=1)        
        dob_entry = ttk.Entry(dob_frame, textvariable=self.var_dob, font=("Segoe UI", 9))
        dob_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ttk.Label(dob_frame, text="YYYY-MM-DD", font=("Segoe UI", 8), foreground="gray").grid(row=0, column=1, padx=(0, 5))
        
        # Age label that will be updated when DOB changes
        self.age_label = ttk.Label(dob_frame, text="", font=("Segoe UI", 9, "bold"), foreground="blue")
        self.age_label.grid(row=0, column=2, padx=(5, 0))
        
        # Bind DOB entry to calculate age on change
        dob_entry.bind("<FocusOut>", lambda e: self.update_age())
        
        #Row 3: Contact Information
        ttk.Label(form_section, text="Phone *:", font=("Segoe UI", 9, "bold")).grid(row=2, column=0, sticky="w", pady=5)
        phone_form_entry = ttk.Entry(form_section, textvariable=self.var_phone, font=("Segoe UI", 9))
        phone_form_entry.grid(row=2, column=1, sticky="ew", padx=(5, 15), pady=5)

        ttk.Label(form_section, text="Email:", font=("Segoe UI", 9, "bold")).grid(row=2, column=2, sticky="w", pady=5)
        email_entry = ttk.Entry(form_section, textvariable=self.var_email, font=("Segoe UI", 9))
        email_entry.grid(row=2, column=3, sticky="ew", padx=(5, 15), pady=5)

        ttk.Label(form_section, text="Address:", font=("Segoe UI", 9, "bold")).grid(row=3, column=0, sticky="w", pady=5)
        address_entry = ttk.Entry(form_section, textvariable=self.var_address, font=("Segoe UI", 9))
        address_entry.grid(row=3, column=1, sticky="ew", padx=(5, 15), pady=5)
        
        # Patient list + Case history
        # Action buttons for patient form
        action_frame = ttk.Frame(form_section)
        action_frame.grid(row=4, column=0, columnspan=4 , pady=(15,5))

        new_btn = ttk.Button(action_frame, text = "New Patient", command=self.on_new_patient)
        new_btn.grid(row=0, column=0,padx=5)

        save_btn = ttk.Button(action_frame, text = "Save Patient", command=self.on_save_patient)
        save_btn.grid(row=0, column=1,padx=5)

        delete_btn = ttk.Button(action_frame, text = "Delete Patient", command=self.on_delete_patient)
        delete_btn.grid(row=0, column=2,padx=5)

        # ==== MAIN CONTENT SECTION ===
        content_section = ttk.Frame(f)
        content_section.grid(row=2, column=0, sticky="nsew", pady=(0,0))
        content_section.columnconfigure(0, weight=1)
        content_section.columnconfigure(1, weight=1)
        content_section.rowconfigure(0, weight=1)

        #Left side Patients List
        patient_frame = ttk.LabelFrame(content_section, text="Patient List", padding=10)
        patient_frame.grid(row=0, column=0, sticky="nsew", pady=(0,5))
        patient_frame.columnconfigure(0, weight=1)
        patient_frame.rowconfigure(0, weight=1)        
        
        
        # Patients treeview
        p_cols = ("id", "first_name", "last_name", "phone", "email", "dob")
        self.p_tree = ttk.Treeview(patient_frame, columns=p_cols, show="headings", height=15)
        headers = {
            "id": "ID", "first_name": "First Name", "last_name": "Last Name",
            "phone": "Phone", "email": "Email", "dob": "DOB"
        }
        widths = (50, 120, 120, 120, 180, 100)
        for (col, width) in zip(p_cols, widths):
            self.p_tree.heading(col, text=headers[col], anchor="w")
            self.p_tree.column(col, width=width, anchor="w" if col in ["first_name","last_name","email"] else "center")
        #Hide ID column for clener look
        self.p_tree.column("id", width=0, stretch=False)
        self.p_tree.heading("id", text="")
        self.p_tree.grid(row=0, column=0, sticky="nsew")
        self.p_tree.bind("<<TreeviewSelect>>", self.on_patient_selected)
        p_scroll_v = ttk.Scrollbar(patient_frame, orient="vertical", command=self.p_tree.yview)
        p_scroll_v.grid(row=0, column=1, sticky="ns")
        self.p_tree.configure(yscrollcommand=p_scroll_v.set)
        p_scroll_h = ttk.Scrollbar(patient_frame, orient="horizontal", command=self.p_tree.xview)
        p_scroll_h.grid(row=1, column=0, sticky="ew")
        self.p_tree.configure(xscrollcommand=p_scroll_h.set)

        #Rightt side - Case History
        history_frame = ttk.LabelFrame(content_section, text="Case History", padding=10)
        history_frame.grid(row=0, column=1, sticky="nsew", pady=(0,5))
        history_frame.columnconfigure(0, weight=1)
        history_frame.rowconfigure(0, weight=1)
        
        # Case history tree (for selected patient)
        c_cols = ("case_id", "date", "follow_up", "chief", "diagnosis", "status", "items")
        self.c_tree = ttk.Treeview(history_frame, columns=c_cols, show="headings", height=15)
        c_headers = {
            "case_id": "Case ID", "date": "Date", "follow_up": "Follow-up",
            "chief": "Chief Complaint", "diagnosis": "Diagnosis", "status": "Status", "items": "Plan Items"
        }
        c_widths = (0, 90, 90, 100, 180, 80, 80) #Hide case_id
        for (col, width) in zip(c_cols, c_widths):
            self.c_tree.heading(col, text=c_headers[col], anchor="w")
            self.c_tree.column(col, width=width, anchor="c" if col in ["diagnosis","chief"] else "center")

        #Hide case id column
        self.c_tree.column("case_id", width=0, stretch=False)
        self.c_tree.heading("case_id", text="")
        self.c_tree.grid(row=0, column=0, sticky="nsew")
        
        # Scrollbars for case hitory
        cscroll_v = ttk.Scrollbar(history_frame, orient="vertical", command=self.c_tree.yview)
        cscroll_v.grid(row=0, column=1, sticky="ns")
        self.c_tree.configure(yscrollcommand=cscroll_v.set)
        
        cscroll_h = ttk.Scrollbar(history_frame, orient="horizontal", command=self.c_tree.xview)
        cscroll_h.grid(row=1, column=0, sticky="ew")
        self.c_tree.configure(xscrollcommand=cscroll_h.set)
        
        # Case history actions
        case_actions = ttk.Frame(history_frame)
        case_actions.grid(row=2, column=0, columnspan=2, pady=(10,0))
        ttk.Button(case_actions, text="Open Selected Case", command=self.on_open_selected_history_case).grid(row=0, column=0, padx=5)
        ttk.Button(case_actions, text="New Case for Selected Patient", command=self.on_new_case_for_selected_patient).grid(row=0, column=1, padx=5)
        
        # Initial load
        # Focus on first name field initiaally
        first_entry.focus()

        #Load ptients on startup
        self.after_idle(self.on_patients_search)
    
    def on_patients_search(self):
        # Clear existing items
        for iid in self.p_tree.get_children():
            self.p_tree.delete(iid)
        
        name = safe_str(self.var_p_name.get()).strip()
        phone = safe_str(self.var_p_phone.get()).strip()
        
        where = ["1=1"]
        params = []
        
        if name:
            where.append("(LOWER(first_name) LIKE LOWER(?) OR LOWER(last_name) LIKE LOWER(?))")
            like = f"%{name}%"
            params.extend((like, like))
        
        if phone:
            where.append("phone LIKE ?")
            params.append(f"%{phone}%")
    
        sql = f"""
            SELECT id, first_name, last_name,
            COALESCE(phone, '') as phone,
            COALESCE(email, '') as email,
            COALESCE(dob, '') as dob
            FROM patients
            WHERE {' AND '.join(where)}
            ORDER BY last_name, first_name
            LIMIT 500
        """  
       
        try:            
            conn = sqlite3.connect(DB_FILE)
            rows = conn.execute(sql, params).fetchall()
            conn.close()        
                    
            for r in rows:
                self.p_tree.insert("", "end", values=r)

            if len(rows) == 0 and not name and not phone:                
                conn = sqlite3.connect(DB_FILE)                
                total_count = conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
                print("Debug: No patients found in database")
                conn.close()
                if total_count == 0:
                    print("Debug: No patients found in database")
                else:
                    print(f"Debug : Found {total_count} total patients found but none match criteria")
            else:
                print(f"Debug : Loaded {len(rows)} patients into tree")
        except sqlite3.Error as e:
            messagebox.showerror("Database error",f"Could not search patients.\n{e}")

    def on_patients_clear(self):
        self.var_p_name.set("")
        self.var_p_phone.set("")
        self.on_patients_search()

    def on_new_patient(self):
        self.current_patient_id = None
        self.var_first.set("")
        self.var_last.set("")
        self.var_gender.set("")
        self.var_dob.set("")
        self.var_phone.set("")
        self.var_email.set("")
        self.var_address.set("")
        # Clear age label
        self.age_label.config(text="")
        #cler tree selection
        for item in self.p_tree.selection():
            self.p_tree.selection_remove(item)
        # clear case history
        self.clear_case_history()
        self.nb.select(self.tab_patients)

    def on_delete_patient(self):
        sel = self.p_tree.selection()
        if not sel:
            messagebox.showwarning("No Selection", "Please select a patient to delete.")
            return
        
        pid = self.p_tree.item(sel[0], "values")[0]
        if not messagebox.askyesno("Confirm", "Delete patient and all associated cases?"):
            return
        
        conn = sqlite3.connect(DB_FILE)
        conn.execute("PRAGMA foreign_keys = ON;")
        with conn:
            conn.execute("DELETE FROM patients WHERE id = ?", (pid,))
        conn.close()
        
        self.on_patients_search()
        self.clear_case_history()
        self.on_new_patient()

    def on_patient_selected(self, event=None):
        sel = self.p_tree.selection()
        if not sel:
            return
        
        values = self.p_tree.item(sel[0], "values")
        pid, first, last, phone, email, dob = values
        self.current_patient_id = int(pid)
        
        # Load full record
        conn = sqlite3.connect(DB_FILE)
        row = conn.execute("SELECT first_name, last_name, gender, dob, phone, email, address FROM patients WHERE id=?", (pid,)).fetchone()
        conn.close()

        if row:
            first, last, gender, dob, phone, email, address = row
            self.var_first.set(first or "")
            self.var_last.set(last or "")
            self.var_gender.set(gender or "")
            self.var_dob.set(dob or "")
            self.var_phone.set(phone or "")
            self.var_email.set(email or "")
            self.var_address.set(address or "")
            
            # Update age display
            self.update_age()
        
        self.load_case_history_for_patient(self.current_patient_id)

    def update_age(self):
        """Calculate and display patient age based on date of birth"""
        dob_str = self.var_dob.get().strip()
        
        if not dob_str:
            self.age_label.config(text="")
            return
        
        try:
            # Parse date of birth (YYYY-MM-DD format)
            from datetime import datetime
            dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
            
            # Calculate age
            today = datetime.today().date()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            
            # Display age
            self.age_label.config(text=f"Age: {age} yrs", foreground="blue")
        except ValueError:
            # Invalid date format
            self.age_label.config(text="Invalid date", foreground="red")

    def load_case_history_for_patient(self, patient_id: int):
        self.clear_case_history()
        sql = (
            "SELECT c.id, c.op_number, c.case_date, c.follow_up_date, c.chief_complaint, c.diagnosis, c.case_status, "
            "(select count(*) from treatment_plans tp where tp.case_id = c.id) AS items "
            "FROM cases c WHERE c.patient_id = ? ORDER BY c.case_date DESC, c.id DESC"
        )
        conn = sqlite3.connect(DB_FILE)
        rows = conn.execute(sql, (patient_id,)).fetchall()
        conn.close()
        
        # Clear existing items
        for iid in self.c_tree.get_children():
            self.c_tree.delete(iid)
        
        # Update columns to include op_number
        c_cols = ("case_id", "op_number", "date", "follow_up", "chief", "diagnosis", "status", "items")
        self.c_tree.configure(columns=c_cols)
        c_headers = {
            "case_id": "Case ID", "op_number": "OP Number", "date": "Date", "follow_up": "Follow-up",
            "chief": "Chief Complaint", "diagnosis": "Diagnosis", "status": "Status", "items": "Plan Items"
        }
        c_widths = (70, 90, 90, 100, 180, 180, 80, 80)
        for (c, w) in zip(c_cols, c_widths):
            self.c_tree.heading(c, text=c_headers[c])
            self.c_tree.column(c, width=w, anchor="center")
    
        for r in rows:
            # Add status color coding
            case_id, op_number, case_date, follow_up, chief, diagnosis, status, items = r
            item_id = self.c_tree.insert("", "end", values=r)
            
            # Color code based on status
            if status == "Closed":
                self.c_tree.set(item_id, "status", "🔒 Closed")
            elif status == "In Progress":
                self.c_tree.set(item_id, "status", "⏳ In Progress")
            elif status == "Cancelled":
                self.c_tree.set(item_id, "status", "❌ Cancelled")
            else:
                self.c_tree.set(item_id, "status", "📋 Open")

    def clear_case_history(self):
        for iid in self.c_tree.get_children():
            self.c_tree.delete(iid)

    def on_open_selected_history_case(self):
        sel = self.c_tree.selection()
        if not sel:
            messagebox.showwarning("No Selection", "Please select a case to open.")
            return
        
        case_id = int(self.c_tree.item(sel[0], "values")[0])
        self.load_case_by_id(case_id)
        self.nb.select(self.tab_case)

    def on_new_case_for_selected_patient(self):
        sel = self.p_tree.selection()
        if not sel:
            messagebox.showwarning("No Patient", "Select a patient first.")
            return
    
        self.on_new_case()
        self.nb.select(self.tab_case)

    def on_save_patient(self):
        try:
            if not safe_str(self.var_first.get()):
                raise ValueError("First Name is required.")
            if not safe_str(self.var_last.get()):
                raise ValueError("Last Name is required.")
            if not safe_str(self.var_phone.get()) or len(safe_str(self.var_phone.get())) != 10:
                raise ValueError("Phone Number is empty or length of the number should be equal to 10.")

            #Get all field values
            first_name = safe_str(self.var_first.get())
            last_name = safe_str(self.var_last.get())
            gender = safe_str(self.var_gender.get()) or None
            dob = safe_str(self.var_dob.get()) or None
            phone = safe_str(self.var_phone.get()) or None
            emil = safe_str(self.var_email.get()) or None
            address = safe_str(self.var_address.get()) or None
             
            if dob:
                parse_date(dob)
            
            conn = sqlite3.connect(DB_FILE)
            #with conn:
            conn.execute("PRAGMA foreign_keys = ON;")
            try:
                if self.current_patient_id is None:
                    # Insert new patient
                    cursor = conn.execute(
                        """
                        INSERT INTO patients(first_name, last_name, gender, dob, phone, email, address)
                        VALUES(?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            first_name, last_name, gender, dob, phone, emil, address 
                        )
                    )
                    #self.current_patient_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                    conn.commit() # Explicitly commit transaction
                    self.current_patient_id = cursor.lastrowid
                    message = "New patient created successfully"
                else:
                    # Update existing patient
                    conn.execute(
                        """
                        UPDATE patients
                        SET first_name=?, last_name=?, gender=?, dob=?, phone=?, email=?, address=?
                        WHERE id=?
                        """,
                        (
                            first_name, last_name, gender, dob, phone, emil, address,self.current_patient_id
                        )
                    )
                    conn.commit() # Explicitly commit transaction
                    message = "Paatient information updted successfully"    
            finally:
                conn.close()
            messagebox.showinfo("Saved", message)
            # Refresh the patient list to show new/updated patient
            self.on_patients_search()
        except ValueError as e:
            messagebox.showerror("Validation Error", str(e))
        except sqlite3.Error as e:
            messagebox.showerror("Database Error", f"Could not save patient.\n{e}")

    def build_case_tab(self):
        f = self.tab_case
        
        # Create main canvas and scrollbar for scrolling
        main_canvas = tk.Canvas(f)
        v_scrollbar = ttk.Scrollbar(f, orient="vertical", command=main_canvas.yview)
        content_frame = ttk.Frame(main_canvas)
        
        content_frame.bind(
            "<Configure>",
            lambda e: main_canvas.configure(scrollregion=main_canvas.bbox("all"))
        )
        
        main_canvas.create_window((0, 0), window=content_frame, anchor="nw")
        main_canvas.configure(yscrollcommand=v_scrollbar.set)
        
        main_canvas.pack(side="left", fill="both", expand=True)
        v_scrollbar.pack(side="right", fill="y")

        # Configure content frame
        content_frame.columnconfigure(0, weight=1)
        content_frame.columnconfigure(1, weight=1)
        
        row = 0
        
        # === CASE INFORMATION SECTION ===
        case_info_frame = ttk.LabelFrame(content_frame, text="Case Information", padding=15)
        case_info_frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=5, pady=(5,10))
        for i in range(4):
            case_info_frame.columnconfigure(i, weight=1)
        
        self.var_case_date = tk.StringVar(value=iso_today())
        self.var_followup_date = tk.StringVar(value="")
        self.var_case_status = tk.StringVar(value="Open")
        self.var_op_number = tk.StringVar(value="")
        
        # First row: OP Number and Case Date
        ttk.Label(case_info_frame, text="OP Number *", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Entry(case_info_frame, textvariable=self.var_op_number, font=("Segoe UI", 10)).grid(row=0, column=1, sticky="ew", padx=(5, 15), pady=5)
        
        ttk.Label(case_info_frame, text="Case Date (YYYY-MM-DD)", font=("Segoe UI", 9, "bold")).grid(row=0, column=2, sticky="w", pady=5)
        ttk.Entry(case_info_frame, textvariable=self.var_case_date, font=("Segoe UI", 10)).grid(row=0, column=3, sticky="ew", padx=(5, 0), pady=5)
        
        # Second row: Follow-up Date and Case Status
        ttk.Label(case_info_frame, text="Follow-up Date (YYYY-MM-DD)", font=("Segoe UI", 9, "bold")).grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(case_info_frame, textvariable=self.var_followup_date, font=("Segoe UI", 10)).grid(row=1, column=1, sticky="ew", padx=(5, 15), pady=5)
        
        ttk.Label(case_info_frame, text="Case Status", font=("Segoe UI", 9, "bold")).grid(row=1, column=2, sticky="w", pady=5)
        status_combo = ttk.Combobox(case_info_frame, textvariable=self.var_case_status,
            values=("Open", "In Progress", "Closed", "Cancelled"),
            state="readonly", font=("Segoe UI", 10))
        status_combo.grid(row=1, column=3, sticky="ew", padx=(5, 0), pady=5)
        
        # Third row: Chief Complaint
        ttk.Label(case_info_frame, text="Chief Complaint *", font=("Segoe UI", 9, "bold")).grid(row=2, column=0, sticky="w", pady=(10, 5))
        self.entry_cc = ttk.Entry(case_info_frame, font=("Segoe UI", 10))
        self.entry_cc.grid(row=2, column=1, columnspan=3, sticky="ew", padx=(5, 0), pady=5)
        
        row += 1
        
        # === MEDICAL & DENTAL HISTORY SECTION ===
        history_frame = ttk.LabelFrame(content_frame, text="Medical & Dental History", padding=15)
        history_frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=5, pady=(0,10))
        history_frame.columnconfigure(0, weight=1)
        history_frame.columnconfigure(1, weight=1)
                
        ttk.Label(history_frame, text="Past Medical History", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 5))
        ttk.Label(history_frame, text="Include previous surgeries, medications, allergies, chroic conditions", font=("Segoe UI", 8),
                  foreground="gray").grid(row=1, column=0, sticky="w", pady=(0, 5))
        med_frame = ttk.Frame(history_frame)
        med_frame.grid(row=2, column=0, sticky="nsew", padx=(0, 5))
        med_frame.columnconfigure(0, weight=1)
        med_frame.rowconfigure(0, weight=1)
        
        self.txt_medical_history = tk.Text(med_frame, height=6, wrap="word", font=("Segoe UI", 10))
        self.txt_medical_history.grid(row=0, column=0, sticky="nsew")
        med_scroll = ttk.Scrollbar(med_frame, orient="vertical", command=self.txt_medical_history.yview)
        med_scroll.grid(row=0, column=1, sticky="ns")
        self.txt_medical_history.configure(yscrollcommand=med_scroll.set)
        
        
        ttk.Label(history_frame, text="Past Dental History", font=("Segoe UI", 9, "bold")).grid(row=0, column=1, sticky="w", pady=(0, 5))
        ttk.Label(history_frame, text="Include previous dental treatments, oral hygiene, dental concerns", font=("Segoe UI", 8),
                  foreground="gray").grid(row=1, column=1, sticky="w", pady=(0, 5))
        dent_frame = ttk.Frame(history_frame)
        dent_frame.grid(row=2, column=1, sticky="nsew", padx=(5, 0))
        dent_frame.columnconfigure(0, weight=1)
        dent_frame.rowconfigure(0, weight=1)
        self.txt_dental_history = tk.Text(dent_frame, height=4, wrap="word", font=("Segoe UI", 10))
        self.txt_dental_history.grid(row=0, column=0, sticky="nsew")
        dent_scroll = ttk.Scrollbar(dent_frame, orient="vertical", command=self.txt_dental_history.yview)
        dent_scroll.grid(row=0, column=1, sticky="ns")
        self.txt_dental_history.configure(yscrollcommand=dent_scroll.set)
        
        history_frame.rowconfigure(2, weight=1)
        
        row += 1
        
        # === CLINICAL EXAMINATION SECTION ===
        
        exam_frame = ttk.LabelFrame(content_frame, text="Clinical Examination & Diagnosis", padding=15)
        exam_frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=5, pady=(0,10))
        exam_frame.columnconfigure(0, weight=1)
        exam_frame.columnconfigure(1, weight=1)
                
        ttk.Label(exam_frame, text="Clinical Examination", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 5))
        ttk.Label(exam_frame, text="Extra-oral and intra-oral exmination findings", font=("Segoe UI", 8),
                  foreground="gray").grid(row=1, column=0, sticky="w", pady=(0, 5))
        exam_text_frame = ttk.Frame(exam_frame)
        exam_text_frame.grid(row=2, column=0, sticky="nsew", padx=(0, 5))
        exam_text_frame.columnconfigure(0, weight=1)
        exam_text_frame.rowconfigure(0, weight=1)
        
        self.txt_exam = tk.Text(exam_text_frame, height=8, wrap="word", font=("Segoe UI", 10))
        self.txt_exam.grid(row=0, column=0, sticky="nsew")
        exam_scroll = ttk.Scrollbar(exam_text_frame, orient="vertical", command=self.txt_exam.yview)
        exam_scroll.grid(row=0, column=1, sticky="ns")
        self.txt_exam.configure(yscrollcommand=exam_scroll.set)
        
        
        ttk.Label(exam_frame, text="Diagnosis & Assessment", font=("Segoe UI", 9, "bold")).grid(row=0, column=1, sticky="w", pady=(0, 5))
        ttk.Label(exam_frame, text="Clinical diagnosis and treatment recommendations", font=("Segoe UI", 8),
                  foreground="gray").grid(row=1, column=1, sticky="w", pady=(0, 5))
        dx_text_frame = ttk.Frame(exam_frame)
        dx_text_frame.grid(row=2, column=1, sticky="nsew", padx=(5, 0))
        dx_text_frame.columnconfigure(0, weight=1)
        dx_text_frame.rowconfigure(0, weight=1)
        
        self.txt_dx = tk.Text(dx_text_frame, height=8, wrap="word", font=("Segoe UI", 10))
        self.txt_dx.grid(row=0, column=0, sticky="nsew")
        dx_scroll = ttk.Scrollbar(dx_text_frame, orient="vertical", command=self.txt_dx.yview)
        dx_scroll.grid(row=0, column=1, sticky="ns")
        self.txt_dx.configure(yscrollcommand=dx_scroll.set)
        
        exam_frame.rowconfigure(1, weight=1)
        
        row += 1
        
        # === CONSENT FORM SECTION ===
        consent_frame = ttk.LabelFrame(content_frame, text="Patient Consent", padding=15)
        consent_frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=5, pady=(0,10))
        consent_frame.columnconfigure(2, weight=1)
        
        self.var_consent_obtained = tk.BooleanVar(value=False)
        self.var_consent_date = tk.StringVar(value="")
        self.var_consent_file = tk.StringVar(value="")

        #Row 1 : Consent checkbox and date
        consent_check = ttk.Checkbutton(consent_frame, text="Consent Obtained",
            variable=self.var_consent_obtained, command=self.on_consent_changed)
        consent_check.grid(row=0, column=0, sticky="w", padx=(0,20), pady=5)
        
        ttk.Label(consent_frame, text="Date:", font=("Segoe UI", 9, "bold")).grid(row=0, column=1, sticky="w", padx=(0,5))
        consent_date_entry = ttk.Entry(consent_frame, textvariable=self.var_consent_date, width=15, font=("Segoe UI", 10))
        consent_date_entry.grid(row=0, column=2, sticky="w", pady=5)

        #Row 2: File selection        
        ttk.Label(consent_frame, text="Consent Form File:", font=("Segoe UI", 9, "bold")).grid(row=1, column=0, sticky="w", pady=5)
        
        consent_file_frame = ttk.Frame(consent_frame)
        consent_file_frame.grid(row=1, column=1, columnspan=2, sticky="ew", pady=5)
        consent_file_frame.columnconfigure(0, weight=1)
        
        file_entry = ttk.Entry(consent_file_frame, textvariable=self.var_consent_file, state="readonly", font=("Segoe UI", 9))
        file_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        
        ttk.Button(consent_file_frame, text="Browse", command=self.on_browse_consent_file).grid(row=0, column=1, padx=2)
        ttk.Button(consent_file_frame, text="View", command=self.on_view_consent_file).grid(row=0, column=2, padx=(2, 0))
        
        row += 1
        
        # === VITALS SECTION ===
        vitals_frame = ttk.LabelFrame(content_frame, text="Vital Signs", padding=15)
        vitals_frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=5, pady=(0,10))
        for i in range(8):
            vitals_frame.columnconfigure(i, weight=1)
        
        self.var_bp = tk.StringVar()
        self.var_hr = tk.StringVar()
        self.var_temp = tk.StringVar()
        self.var_weight = tk.StringVar()
        
        ttk.Label(vitals_frame, text="Blood Pressure:", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", pady=5)
        bp_entry = ttk.Entry(vitals_frame, textvariable=self.var_bp, width=12, font=("Segoe UI", 10))
        bp_entry.grid(row=0, column=1, sticky="w", padx=(5,15), pady=5)
        ttk.Label(vitals_frame, text="(mmHg)", font=("Segoe UI", 8),foreground="gray").grid(row=0, column=2, sticky="w")

        ttk.Label(vitals_frame, text="Heart Rate:", font=("Segoe UI", 9, "bold")).grid(row=0, column=3, sticky="w", pady=5)
        hr_entry = ttk.Entry(vitals_frame, textvariable=self.var_hr, width=12, font=("Segoe UI", 10))
        hr_entry.grid(row=0, column=4, sticky="w", padx=(5, 10), pady=5)
        ttk.Label(vitals_frame, text="bpm", font=("Segoe UI", 8),foreground="gray").grid(row=0, column=5, sticky="w")

        ttk.Label(vitals_frame, text="RBS Level:", font=("Segoe UI", 9, "bold")).grid(row=1, column=0, sticky="w", pady=5)
        temp_entry = ttk.Entry(vitals_frame, textvariable=self.var_temp, width=8, font=("Segoe UI", 10))
        temp_entry.grid(row=1, column=1, sticky="w", padx=(5, 10), pady=5)
        ttk.Label(vitals_frame, text="(mg/dl)", font=("Segoe UI", 8),foreground="gray").grid(row=1, column=2, sticky="w")

        ttk.Label(vitals_frame, text="Weight:", font=("Segoe UI", 9, "bold")).grid(row=1, column=3, sticky="w", pady=5)
        weight_entry = ttk.Entry(vitals_frame, textvariable=self.var_weight, width=8, font=("Segoe UI", 10))
        weight_entry.grid(row=1, column=4, sticky="w", padx=(5,10), pady=5)
        ttk.Label(vitals_frame, text="kg", font=("Segoe UI", 8),foreground="gray").grid(row=1, column=5, sticky="w")
                
        row += 1
        
        # === TREATMENT PLAN SECTION ===
        treatment_frame = ttk.LabelFrame(content_frame, text="Treatment Plan", padding=15)
        treatment_frame.grid(row=row, column=0, columnspan=2, sticky="nsew", padx=5, pady=(0,10))
        treatment_frame.columnconfigure(0, weight=1)
        
        # Treatment plan input fields
        plan_input_frame = ttk.Frame(treatment_frame)
        plan_input_frame.grid(row=0, column=0, sticky="ew", pady=(0, 15))
                      
        for i in range(4):
            plan_input_frame.columnconfigure(i, weight=1)
        
        self.var_item_type = tk.StringVar(value="Medication")
        self.var_name = tk.StringVar()
        self.var_dosage = tk.StringVar()
        self.var_frequency = tk.StringVar()
        self.var_duration = tk.StringVar()
        self.var_start = tk.StringVar(value=iso_today())
        self.var_status = tk.StringVar(value="Planned")
        self.var_notes = tk.StringVar()
        self.editing_plan_index = None

        #Row 1 Type and Name        
        ttk.Label(plan_input_frame, text="Type:",font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", pady=5)
        type_combo = ttk.Combobox(plan_input_frame, textvariable=self.var_item_type,
            values=("Medication", "Procedure", "Test", "Advice"), state="readonly", font=("Segoe UI", 10))
        type_combo.grid(row=0, column=1, sticky="ew", padx=(5,15), pady=5)
       
        ttk.Label(plan_input_frame, text="Name *:",font=("Segoe UI", 9, "bold")).grid(row=0, column=2, sticky="w", pady=5)
        name_entry = ttk.Entry(plan_input_frame, textvariable=self.var_name, font=("", 10))
        name_entry.grid(row=0, column=3, sticky="ew", padx=(5,0), pady=5)

        #Row 2 Dosage and Frequency
        ttk.Label(plan_input_frame, text="Dosage:",font=("Segoe UI", 9, "bold")).grid(row=1, column=0, sticky="w", pady=5)
        dosge_entry = ttk.Entry(plan_input_frame, textvariable=self.var_dosage, font=("Segoe UI", 10))
        dosge_entry.grid(row=1, column=1, sticky="ew", padx=(5,0), pady=5)

        ttk.Label(plan_input_frame, text="Frequency:",font=("Segoe UI", 9, "bold")).grid(row=1, column=2, sticky="w", pady=5)
        freq_entry = ttk.Entry(plan_input_frame, textvariable=self.var_frequency, font=("Segoe UI", 10))
        freq_entry.grid(row=1, column=3, sticky="ew", padx=(5,0), pady=5)
        
        #Row 3 Duration and Start Date
        ttk.Label(plan_input_frame, text="Duration (days):",font=("Segoe UI", 9, "bold")).grid(row=2, column=0, sticky="w", pady=5)
        duration_entry = ttk.Entry(plan_input_frame, textvariable=self.var_duration, font=("Segoe UI", 10))
        duration_entry.grid(row=2, column=1, sticky="ew", padx=(5,15), pady=5)

        ttk.Label(plan_input_frame, text="Start Date:",font=("Segoe UI", 9, "bold")).grid(row=2, column=2, sticky="w", pady=5)
        start_entry = ttk.Entry(plan_input_frame, textvariable=self.var_start, font=("Segoe UI", 10))
        start_entry.grid(row=2, column=3, sticky="ew", padx=(5,0), pady=5)

        #Row 4 status and notes
        
        ttk.Label(plan_input_frame, text="Status", font=("Segoe UI", 9, "bold")).grid(row=3, column=0, sticky="w", pady=5)
        status_combo = ttk.Combobox(plan_input_frame, textvariable=self.var_status,
            values=("Planned", "Ongoing", "Completed"), state="readonly", font=("Segoe UI", 10))
        status_combo.grid(row=3, column=1, sticky="ew", padx=(5,15), pady=5)

        ttk.Label(plan_input_frame, text="Notes:",font=("Segoe UI", 9, "bold")).grid(row=3, column=2, sticky="w", pady=5)
        notes_entry = ttk.Entry(plan_input_frame, textvariable=self.var_notes, font=("Segoe UI", 10))
        notes_entry.grid(row=3, column=3, sticky="ew", padx=(5,0), pady=5)

        # Treatment plan buttons
        plan_btn_frame = ttk.Frame(treatment_frame)
        plan_btn_frame.grid(row=1, column=0, sticky="ew", padx=(0, 15))
        add_btn = ttk.Button(plan_btn_frame, text="Add Item", command=self.on_add_plan)
        add_btn.pack(side="left", padx=(0,10))
        edit_btn = ttk.Button(plan_btn_frame, text="Edit Selected", command=self.on_edit_plan)
        edit_btn.pack(side="left", padx=(0,10))
        save_btn = ttk.Button(plan_btn_frame, text="Save Changes", command=self.on_save_plan_changes)
        save_btn.pack(side="left", padx=(0,10))
        delete_btn = ttk.Button(plan_btn_frame, text="Delete Selected", command=self.on_delete_plan)
        delete_btn.pack(side="left", padx=(0,10))
        clear_btn = ttk.Button(plan_btn_frame, text="Clear Form", command=self.clear_plan_inputs)
        clear_btn.pack(side="left", padx=(0,10))
        
        # Treatment plan tree
        list_frame = ttk.Frame(treatment_frame)
        list_frame.grid(row=2, column=0, sticky="nsew", pady=(0,0))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        
        cols = ("type", "name", "dosage", "frequency", "duration", "start", "end", "status", "notes")
        self.plan_tree = ttk.Treeview(list_frame, columns=cols, show="headings", height=8)
        # Configure headers and columns
        headers = {
            "type": "Type", "name": "Name", "dosage": "Dosage", "frequency": "Frequncy", "duration": "Days",
            "start": "Start Date", "end": "End Date", "status": "Status", "notes": "Notes"
            }
        widths = (80, 200, 100, 100, 60, 90, 90, 80, 250)  # Much wider columns for better text visibility
        for col, width in zip(cols, widths):
            self.plan_tree.heading(col, text = headers[col], anchor="w")
            self.plan_tree.column(col, width=width, anchor="center" if col in ["start","end","duration"] else "w")
        self.plan_tree.grid(row=0, column=0, sticky="nsew")
        
        # Bind hover events for tooltip on name and notes columns only
        self.plan_tree.bind("<Motion>", self.on_plan_tree_motion)
        self.plan_tree.bind("<Leave>", self.on_plan_tree_leave)
        self.tooltip_window = None
        
        plan_v_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.plan_tree.yview)
        plan_v_scroll.grid(row=0, column=1, sticky="ns")
        self.plan_tree.configure(yscrollcommand=plan_v_scroll.set)

        plan_h_scroll = ttk.Scrollbar(list_frame, orient="horizontal", command=self.plan_tree.xview)
        plan_h_scroll.grid(row=1, column=0, sticky="ew")
        self.plan_tree.configure(yscrollcommand=plan_h_scroll.set)
        
        treatment_frame.rowconfigure(2, weight=1)
        
        # Configure main content frame row weights
        content_frame.rowconfigure(1, weight=1)  # Medical & Dental history
        content_frame.rowconfigure(4, weight=1)  # Clinical examination
        content_frame.rowconfigure(6, weight=1)  # Treatment plan
        
        # Enable mouse wheel scrolling
        def on_mousewheel(event):            
            main_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        main_canvas.bind_all("<MouseWheel>", on_mousewheel)

    def on_plan_tree_motion(self, event):
        """Show tooltip on hover for name and notes columns only"""
        item = self.plan_tree.identify_row(event.y)
        column = self.plan_tree.identify_column(event.x)
        
        if not item or not column:
            self.on_plan_tree_leave(None)
            return
        
        try:
            col_index = int(column.lstrip("#")) - 1
        except (ValueError, TypeError):
            self.on_plan_tree_leave(None)
            return
        
        # Only show tooltip for name (index 1) and notes (index 8) columns
        if col_index not in [1, 8]:
            self.on_plan_tree_leave(None)
            return
        
        values = self.plan_tree.item(item, "values")
        
        if col_index < len(values):
            content = str(values[col_index])
            
            # Only show tooltip if text is not empty
            if content:
                self.show_tooltip(event, content)
            else:
                self.on_plan_tree_leave(None)
        else:
            self.on_plan_tree_leave(None)
    
    def on_plan_tree_leave(self, event):
        """Hide tooltip when leaving tree"""
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None
    
    def show_tooltip(self, event, text):
        """Display tooltip near cursor"""
        # Destroy existing tooltip
        if self.tooltip_window:
            self.tooltip_window.destroy()
        
        # Create tooltip window
        self.tooltip_window = tk.Toplevel(self.plan_tree)
        self.tooltip_window.wm_overrideredirect(True)
        
        # Position near cursor (offset by 10, 10 pixels)
        x = event.x_root + 10
        y = event.y_root + 10
        self.tooltip_window.wm_geometry(f"+{x}+{y}")
        
        # Add label with text
        label = tk.Label(
            self.tooltip_window,
            text=text,
            background="#ffffe0",
            relief="solid",
            borderwidth=1,
            wraplength=300,
            justify="left",
            padx=5,
            pady=5,
            font=("Arial", 9)
        )
        label.pack()
        
        # Ensure tooltip appears on top
        self.tooltip_window.lift()

    def on_consent_changed(self):
        """Auto-set consent date when checkbox is checked"""
        if self.var_consent_obtained.get() and not self.var_consent_date.get():
            self.var_consent_date.set(iso_today())

    # --------- Browse/Search Tab ---------

    def build_browse_tab(self):
        f = self.tab_browse
        for i in range(0, 8):
            f.columnconfigure(i, weight=1)
        
        # Filters
        self.var_s_name = tk.StringVar()
        self.var_s_phone = tk.StringVar()
        self.var_s_from = tk.StringVar()
        self.var_s_to = tk.StringVar()
        self.var_s_dx = tk.StringVar()
        
        row = 0
        ttk.Label(f, text="Name (contains)").grid(row=row, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.var_s_name).grid(row=row, column=1, sticky="ew", padx=4, pady=4)
        ttk.Label(f, text="Phone").grid(row=row, column=2, sticky="w")
        ttk.Entry(f, textvariable=self.var_s_phone).grid(row=row, column=3, sticky="ew", padx=4, pady=4)
        ttk.Label(f, text="From (YYYY-MM-DD)").grid(row=row, column=4, sticky="w")
        ttk.Entry(f, textvariable=self.var_s_from).grid(row=row, column=5, sticky="ew", padx=4, pady=4)
        ttk.Label(f, text="To (YYYY-MM-DD)").grid(row=row, column=6, sticky="w")
        ttk.Entry(f, textvariable=self.var_s_to).grid(row=row, column=7, sticky="ew", padx=4, pady=4)
        row += 1
        
        ttk.Label(f, text="Diagnosis (contains)").grid(row=row, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.var_s_dx).grid(row=row, column=1, columnspan=3, sticky="ew", padx=4, pady=4)
        btns = ttk.Frame(f)
        btns.grid(row=row, column=4, columnspan=4, sticky="e")
        ttk.Button(btns, text="Search", command=self.on_search).grid(row=0, column=0, padx=4)
        ttk.Button(btns, text="Clear", command=self.on_search_clear).grid(row=0, column=1, padx=4)
        ttk.Button(btns, text="Prev Page", command=self.on_prev_page).grid(row=0, column=2, padx=4)
        ttk.Button(btns, text="Next Page", command=self.on_next_page).grid(row=0, column=3, padx=4)
        
        cols = ("case_id", "case_date", "follow_up", "first_name", "last_name",                
        "phone", "chief", "diagnosis", "plan_items")
        self.search_tree = ttk.Treeview(f, columns=cols, show="headings", height=16)
        headers = {
            "case_id": "Case ID", "case_date": "Date", "follow_up": "Follow-up",
            "first_name": "First", "last_name": "Last", "phone": "Phone",
            "chief": "Chief Complaint", "diagnosis": "Diagnosis", "plan_items": "Plan Items"
        }
        widths = (80, 100, 110, 120, 120, 120, 220, 220, 100)
        for (c, w) in zip(cols, widths):
            self.search_tree.heading(c, text=headers[c])
            self.search_tree.column(c, width=w, anchor="center")
        self.search_tree.grid(row=row+1, column=0, columnspan=8, sticky="nsew", padx=4, pady=8)
        
        yscroll = ttk.Scrollbar(f, orient="vertical", command=self.search_tree.yview)
        yscroll.grid(row=row+1, column=8, sticky="ns")
        self.search_tree.configure(yscrollcommand=yscroll.set)
        
        act = ttk.Frame(f)
        act.grid(row=row+2, column=0, columnspan=8, sticky="e")
        ttk.Button(act, text="Load Selected Case", command=self.on_load_selected_case).grid(row=0, column=0, padx=4)
        ttk.Button(act, text="Open Selected Patient", command=self.on_open_selected_patient_from_search).grid(row=0, column=1, padx=4)
        ttk.Button(act, text="Export to PDF", command=self.on_export_case_from_search).grid(row=0, column=2, padx=4)
        
        f.rowconfigure(row+1, weight=1)

    # ---------------------- Treatment Plan Actions ----------------------

    def on_add_plan(self):
        try:
            # messagebox.showinfo("Plane name :",self.var_name.get())
            name = safe_str(self.var_name.get())
            if not name:
                raise ValueError("Plan Name is required.")
            item_type = safe_str(self.var_item_type.get() or "Medication") 
            dosage = safe_str(self.var_dosage.get())
            frequency = safe_str(self.var_frequency.get())
            duration = safe_str(self.var_duration.get())
            start = safe_str(self.var_start.get())
            status = safe_str(self.var_status.get() or "Planned")
            notes = safe_str(self.var_notes.get())
            if start:
                parse_date(start)  # validates date
            end = calc_end_date(start, int(duration)) if duration else ""
            item = {
                "type": item_type,
                "name": name,
                "dosage": dosage,
                "frequency": frequency,
                "duration": duration,
                "start": start,
                "end": end,
                "status": status,
                "notes": notes
            }
            self.plan_items.append(item)
            self.plan_tree.insert("", "end", values=(
                item["type"], item["name"], item["dosage"], item["frequency"],
                item["duration"], item["start"], item["end"], item["status"], item["notes"]
            ))
            self.clear_plan_inputs()
        except ValueError as e:
            messagebox.showerror("Invalid Input", str(e))

    def on_delete_plan(self):
        selected = self.plan_tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select a plan item to delete.")
            return
        idx = self.plan_tree.index(selected[0])
        self.plan_tree.delete(selected[0])
        del self.plan_items[idx]

    def on_edit_plan(self):
        """Load selected plan item into input fields for editing"""
        selected = self.plan_tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select a plan item to edit.")
            return
        
        idx = self.plan_tree.index(selected[0])
        self.editing_plan_index = idx
        
        # Populate input fields with selected item's data
        current_item = self.plan_items[idx]
        self.var_item_type.set(current_item.get("type", "Medication"))
        self.var_name.set(current_item.get("name", ""))
        self.var_dosage.set(current_item.get("dosage", ""))
        self.var_frequency.set(current_item.get("frequency", ""))
        self.var_duration.set(current_item.get("duration", ""))
        self.var_start.set(current_item.get("start", ""))
        self.var_status.set(current_item.get("status", "Planned"))
        self.var_notes.set(current_item.get("notes", ""))
        
        messagebox.showinfo("Edit Mode", "Item loaded for editing. Make your changes and click 'Save Changes'.")

    def on_save_plan_changes(self):
        """Save changes to the item being edited"""
        if self.editing_plan_index is None:
            messagebox.showwarning("No Edit in Progress", "No item is currently being edited. Use 'Edit Selected' first.")
            return
        
        try:
            name = safe_str(self.var_name.get())
            if not name:
                raise ValueError("Plan Name is required.")
            
            item_type = safe_str(self.var_item_type.get() or "Medication") 
            dosage = safe_str(self.var_dosage.get())
            frequency = safe_str(self.var_frequency.get())
            duration = safe_str(self.var_duration.get())
            start = safe_str(self.var_start.get())
            status = safe_str(self.var_status.get() or "Planned")
            notes = safe_str(self.var_notes.get())
            
            if start:
                parse_date(start)
            
            end = calc_end_date(start, int(duration)) if duration else ""
            item = {
                "type": item_type, "name": name, "dosage": dosage, "frequency": frequency,
                "duration": duration, "start": start, "end": end, "status": status, "notes": notes
            }
            
            # Update the item
            self.plan_items[self.editing_plan_index] = item
            
            # Update the tree view
            tree_items = list(self.plan_tree.get_children())
            if self.editing_plan_index < len(tree_items):
                self.plan_tree.item(tree_items[self.editing_plan_index], values=(
                    item["type"], item["name"], item["dosage"], item["frequency"],
                    item["duration"], item["start"], item["end"], item["status"], item["notes"]
                ))
            
            self.clear_plan_inputs()
            self.editing_plan_index = None
            messagebox.showinfo("Updated", "Plan item has been updated successfully.")
            
        except ValueError as e:
            messagebox.showerror("Invalid Input", str(e))

    def clear_plan_inputs(self):
        self.var_item_type.set("Medication")
        self.var_name.set("")
        self.var_dosage.set("")
        self.var_frequency.set("")
        self.var_duration.set("")
        self.var_start.set(iso_today())
        self.var_status.set("Planned")
        self.var_notes.set("")

    # ---------------------- Case Actions ----------------------

    def get_next_op_number(self, date_str):
        """Get the next OP number for the given date (unique per day)"""
        conn = sqlite3.connect(DB_FILE)
        try:
            # Find the maximum op_number for the given date
            result = conn.execute(
                "SELECT MAX(op_number) FROM cases WHERE case_date = ?",
                (date_str,)
            ).fetchone()
            
            max_op_num = result[0] if result and result[0] else 0
            next_op_num = max_op_num + 1
            return next_op_num
        finally:
            conn.close()

    def on_new_case(self):
        self.current_case_id = None
        self.var_case_date.set(iso_today())
        self.var_followup_date.set("")
        self.var_case_status.set("Open")
        # Auto-generate next op_number for today
        next_op_num = self.get_next_op_number(iso_today())
        self.var_op_number.set(str(next_op_num))
        self.entry_cc.delete(0, "end")
        self.txt_medical_history.delete("1.0", "end")
        self.txt_dental_history.delete("1.0", "end")
        self.txt_exam.delete("1.0", "end")
        self.txt_dx.delete("1.0", "end")
        self.var_consent_obtained.set(False)
        self.var_consent_date.set("")
        self.var_consent_file.set("")
        self.var_bp.set("")
        self.var_hr.set("")
        self.var_temp.set("")
        self.var_weight.set("")
        self.plan_items.clear()
        for iid in self.plan_tree.get_children():
            self.plan_tree.delete(iid)
        self.clear_plan_inputs()
        self.nb.select(self.tab_case)

    def on_save_case(self):
        
        try:
            # Need a selected/created patient first
            if not self.current_patient_id:
                if not safe_str(self.var_first.get()) or not safe_str(self.var_last.get()):
                    raise ValueError("Select or save a patient first.")
                # Attempt to save patient to get ID
                self.on_save_patient()
                if not self.current_patient_id:
                    raise ValueError("Could not determine patient.")
            
            # Validate required fields
            op_number_str = safe_str(self.var_op_number.get())
            if not op_number_str:
                raise ValueError("OP Number is required.")
            
            # Validate OP number is a positive integer
            try:
                op_number = int(op_number_str)
                if op_number <= 0:
                    raise ValueError("OP Number must be a positive integer.")
            except ValueError:
                raise ValueError("OP Number must be a valid positive integer.")
            
            # Check if op_number is unique for this date
            case_date = self.var_case_date.get()
            conn = sqlite3.connect(DB_FILE)
            existing = conn.execute(
                "SELECT id FROM cases WHERE op_number = ? AND case_date = ? AND id != ?",
                (op_number, case_date, self.current_case_id or -1)
            ).fetchone()
            conn.close()
            if existing:
                raise ValueError(f"OP Number {op_number} already exists for {case_date}. Please use a different number.")
            
            cc = self.entry_cc.get().strip()
            if not cc:
                raise ValueError("Chief Complaint is required.")
            
            case_date = safe_str(self.var_case_date.get() or iso_today())
            parse_date(case_date)  # validates format
            follow_up = safe_str(self.var_followup_date.get())
            if follow_up:
                parse_date(follow_up)
            
            case_status = safe_str(self.var_case_status.get() or "Open")
            closed_date = iso_today() if case_status == "Closed" else None

            # Prepare case fields
            medical_history = self.txt_medical_history.get("1.0", "end").strip()
            dental_history = self.txt_dental_history.get("1.0", "end").strip()
            exam = self.txt_exam.get("1.0", "end").strip()
            dx = self.txt_dx.get("1.0", "end").strip()
            
            # Consent fields
            consent_obtained = self.var_consent_obtained.get()
            consent_date = safe_str(self.var_consent_date.get())
            consent_file = safe_str(self.var_consent_file.get())
            
            conn = sqlite3.connect(DB_FILE)
            conn.execute("PRAGMA foreign_keys = ON;")
            with conn:
                if self.current_case_id is None:
                    conn.execute(
                        """
                        INSERT INTO cases(patient_id, op_number, case_date, follow_up_date, case_status, closed_date,
                        chief_complaint, medical_history, dental_history, examination, diagnosis,
                        consent_obtained, consent_date, consent_file_path,
                        vitals_bp, vitals_hr, vitals_temp, vitals_weight)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            self.current_patient_id, op_number, case_date, follow_up or None, case_status, closed_date,
                            cc, medical_history, dental_history, exam, dx,
                            consent_obtained, consent_date or None, consent_file or None,
                            safe_str(self.var_bp.get()), safe_str(self.var_hr.get()),
                            safe_str(self.var_temp.get()), safe_str(self.var_weight.get())
                        )
                    )
                    self.current_case_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                else:
                    conn.execute(
                        """
                    UPDATE cases
                    SET op_number=?, case_date=?, follow_up_date=?, case_status=?, closed_date=?,
                    chief_complaint=?, medical_history=?, dental_history=?, examination=?, diagnosis=?,
                    consent_obtained=?, consent_date=?, consent_file_path=?,
                    vitals_bp=?, vitals_hr=?, vitals_temp=?, vitals_weight=?
                    WHERE id=?
                    """,
                    (
                        op_number, case_date, follow_up or None, case_status, closed_date,
                        cc, medical_history, dental_history, exam, dx,
                        consent_obtained, consent_date or None, consent_file or None,
                        safe_str(self.var_bp.get()), safe_str(self.var_hr.get()),
                        safe_str(self.var_temp.get()), safe_str(self.var_weight.get()), self.current_case_id
                    )
                    )
                    
                # Replace treatment plan items for this case
                conn.execute("DELETE FROM treatment_plans WHERE case_id = ?", (self.current_case_id,))
                plan_sql = (
                    "INSERT INTO treatment_plans(case_id, item_type, name, dosage, frequency, duration_days, start_date, end_date, status, notes)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                )
                    
                for item in self.plan_items:
                    conn.execute(plan_sql, (
                        self.current_case_id, item["type"], item["name"], item["dosage"], item["frequency"],
                        int(item["duration"]) if item["duration"] else None,
                        item["start"] or None, item["end"] or None,
                        item["status"], item["notes"]
                    ))
                    
            conn.close()
            messagebox.showinfo("Saved", f"Case and treatment plan saved.\nOP Number: {op_number}")
            # Refresh case history panel if patient selected
            if self.current_patient_id:
                self.load_case_history_for_patient(self.current_patient_id)
                
            # Jump to Browse tab and show recent
            self.nb.select(self.tab_browse)
            self.search_page = 0
            self.on_search()
                
        except ValueError as e:
            messagebox.showerror("Validation Error", str(e))
        except sqlite3.Error as e:
            if "UNIQUE constraint failed" in str(e):
                messagebox.showerror("Database Error", f"OP Number '{op_number_str}' already exists. Please use a different number.")
            else:
                messagebox.showerror("Database Error", f"Could not save case.\n{e}")

    def on_browse_consent_file(self):
        """Browse and select a consent form file"""
        from tkinter import filedialog
        
        file_types = [
            ("PDF files", "*.pdf"),
            ("Image files", "*.jpg;*.jpeg;*.png;*.bmp;*.gif"),
            ("Word documents", "*.doc;*.docx"),
            ("All files", "*.*")
        ]
        
        filename = filedialog.askopenfilename(
            title="Select Consent Form",
            filetypes=file_types,
            initialdir="."
        )
        
        if filename:
            self.var_consent_file.set(filename)
            # Auto-set consent date if not already set
            if not self.var_consent_date.get():
                self.var_consent_date.set(iso_today())
            # Auto-check consent obtained
            self.var_consent_obtained.set(True)
            messagebox.showinfo("File Selected", f"Consent form file selected:\n{filename}")

    # Better file opening for older Windows versions
    def on_view_consent_file(self):
        import os
        import platform
        import subprocess
        
        file_path = self.var_consent_file.get().strip()
        if not file_path:
            messagebox.showwarning("No File", "No consent form file selected.")
            return
        
        if not os.path.exists(file_path):
            messagebox.showerror("File Not Found", f"The consent form file could not be found:\n{file_path}")
            return
        
        try:
            if platform.system() == "Windows":
                # More compatible approach for older Windows
                os.startfile(file_path)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", file_path])
            else:  # Linux
                subprocess.run(["xdg-open", file_path])
        except Exception as e:
            messagebox.showerror("Error", f"Could not open file:\n{e}")

    # ---------------------- Browse/Search Actions ----------------------

    def build_where_clause(self):
        where = ["1=1"]
        params = []
        name = safe_str(self.var_s_name.get()).strip()
        phone = safe_str(self.var_s_phone.get()).strip()
        dfrom = safe_str(self.var_s_from.get()).strip()
        dto = safe_str(self.var_s_to.get()).strip()
        dx = safe_str(self.var_s_dx.get()).strip()
        
        if name:
            where.append("(LOWER(p.first_name) LIKE LOWER(?) OR LOWER(p.last_name) LIKE LOWER(?))")
            like = f"%{name}%"
            params.extend([like, like])
        
        if phone:
            where.append("p.phone LIKE ?")
            params.append(f"%{phone}%")
        
        if dfrom:
            parse_date(dfrom)
            where.append("c.case_date >= ?")
            params.append(dfrom)
        
        if dto:
            parse_date(dto)
            where.append("c.case_date <= ?")
            params.append(dto)
        
        if dx:
            where.append("LOWER(c.diagnosis) LIKE LOWER(?)")
            params.append(f"%{dx}%")
        
        return " AND ".join(where), params

    def on_search(self):
        for iid in self.search_tree.get_children():
            self.search_tree.delete(iid)
        try:
            where, params = self.build_where_clause()
        except ValueError as e:
            messagebox.showerror("Invalid date", str(e))
            return
        offset = self.search_page * PAGE_SIZE
        sql = f"""
            SELECT c.id, c.case_date, c.follow_up_date, p.first_name, p.last_name, p.phone,
            c.chief_complaint, c.diagnosis,
            (SELECT COUNT(*) FROM treatment_plans tp WHERE tp.case_id = c.id) AS items
            FROM cases c
            JOIN patients p ON p.id = c.patient_id
            WHERE {where}
            ORDER BY c.case_date DESC, c.id DESC
            LIMIT ? OFFSET ?
        """
        
        conn = sqlite3.connect(DB_FILE)
        rows = conn.execute(sql, (*params, PAGE_SIZE, offset)).fetchall()
        conn.close()
        for r in rows:
            self.search_tree.insert("", "end", values=r)

    def on_search_clear(self):
        self.var_s_name.set("")
        self.var_s_phone.set("")
        self.var_s_from.set("")
        self.var_s_to.set("")
        self.var_s_dx.set("")
        self.search_page = 0
        self.on_search()

    def on_next_page(self):
        self.search_page += 1
        self.on_search()

    def on_prev_page(self):
        self.search_page = max(0, self.search_page - 1)
        self.on_search()

    def on_load_selected_case(self):
        sel = self.search_tree.selection()
        if not sel:
            messagebox.showwarning("No Selection", "Select a case to load.")
            return
        
        case_id = int(self.search_tree.item(sel[0], "values")[0])
        self.load_case_by_id(case_id)
        self.nb.select(self.tab_case)

    def on_open_selected_patient_from_search(self):
        sel = self.search_tree.selection()
        if not sel:
            messagebox.showwarning("No Selection", "Select a case to determine patient.")
            return
        case_id = int(self.search_tree.item(sel[0], "values")[0])
        conn = sqlite3.connect(DB_FILE)
        pid = conn.execute("SELECT patient_id FROM cases WHERE id=?", (case_id,)).fetchone()[0]
        row = conn.execute("SELECT id, first_name, last_name, phone, email, dob FROM patients WHERE id=?", (pid,)).fetchone()
        conn.close()
        if row:
            # Select this patient in patients tab
            self.nb.select(self.tab_patients)
            # Refresh patient list and try to highlight
            self.on_patients_search()
            for iid in self.p_tree.get_children():
                vals = self.p_tree.item(iid, "values")
                if int(vals[0]) == pid:
                    self.p_tree.selection_set(iid)
                    self.p_tree.see(iid)
                    self.on_patient_selected()
                    break
    def load_case_by_id(self, case_id: int):
        conn = sqlite3.connect(DB_FILE)
        conn.execute("PRAGMA foreign_keys = ON;")
        c = conn.execute(
            """
            SELECT c.id, c.op_number, c.case_date, c.follow_up_date, c.case_status, c.chief_complaint,
            c.medical_history, c.dental_history, c.examination, c.diagnosis,
            c.consent_obtained, c.consent_date, c.consent_file_path,
            c.vitals_bp, c.vitals_hr, c.vitals_temp, c.vitals_weight,
            p.id, p.first_name, p.last_name, p.gender, p.dob, p.phone, p.email, p.address
            FROM cases c
            JOIN patients p ON p.id = c.patient_id
            WHERE c.id = ?
            """,
            (case_id,)
        ).fetchone()
        if not c:
            conn.close()
            messagebox.showerror("Not Found", "Case not found.")
            return
        
        (
            case_id, op_number, case_date, follow_up, case_status, cc,
            medical_history, dental_history, exam, dx,
            consent_obtained, consent_date, consent_file,
            bp, hr, temp, weight,
            pid, first, last, gender, dob, phone, email, address
        ) = c
        # Set state
        self.current_patient_id = int(pid)
        self.current_case_id = int(case_id)
        # Fill patient data
        self.var_first.set(first or "")
        self.var_last.set(last or "")
        self.var_gender.set(gender or "")
        self.var_dob.set(dob or "")
        self.var_phone.set(phone or "")
        self.var_email.set(email or "")
        self.var_address.set(address or "")
        # Fill case data
        self.var_op_number.set(str(op_number) if op_number else "")
        self.var_case_date.set(case_date or iso_today())
        self.var_followup_date.set(follow_up or "")
        self.var_case_status.set(case_status or "Open")
        self.entry_cc.delete(0, "end")
        self.entry_cc.insert(0, cc or "")
        self.txt_medical_history.delete("1.0", "end")
        self.txt_medical_history.insert("end", medical_history or "")
        self.txt_dental_history.delete("1.0", "end")
        self.txt_dental_history.insert("end", dental_history or "")
        self.txt_exam.delete("1.0", "end")
        self.txt_exam.insert("end", exam or "")
        self.txt_dx.delete("1.0", "end")
        self.txt_dx.insert("end", dx or "")
        
        # Fill consent fields
        self.var_consent_obtained.set(bool(consent_obtained))
        self.var_consent_date.set(consent_date or "")
        self.var_consent_file.set(consent_file or "")
        
        # Fill vital signs
        self.var_bp.set(bp or "")
        self.var_hr.set(hr or "")
        self.var_temp.set(temp or "")
        self.var_weight.set(weight or "")
        # Fill plan items
        self.plan_items.clear()
        for iid in self.plan_tree.get_children():
            self.plan_tree.delete(iid)
        plans = conn.execute(
            """
            SELECT item_type, name, dosage, frequency, duration_days, start_date, end_date, status, notes
            FROM treatment_plans
            WHERE case_id = ?
        ORDER BY id
        """,
        (case_id,)
        ).fetchall()
        conn.close()
        for (item_type, name, dosage, frequency, duration_days, start_date, end_date, status, notes) in plans:
            item = {
                "type": item_type or "",
                "name": name or "",
                "dosage": dosage or "",
                "frequency": frequency or "",
                "duration": str(duration_days or "") if duration_days is not None else "",
                "start": start_date or "",
                "end": end_date or "",
                "status": status or "",
                "notes": notes or ""
            }
            self.plan_items.append(item)
            self.plan_tree.insert("", "end", values=(
                item["type"], item["name"], item["dosage"], item["frequency"],
                item["duration"], item["start"], item["end"], item["status"], item["notes"]
            ))
        
        # Refresh patient case history panel
        self.load_case_history_for_patient(self.current_patient_id)

    def on_close_case(self):
        """Close the current case"""
        if not self.current_case_id:
            messagebox.showwarning("No Case", "No case is currently loaded to close.")
            return
        
        if not messagebox.askyesno("Confirm Close Case",
                                    "Are you sure you want to close this case?\n\n"
                                    "This will set the case status to 'Closed' and record the closure date."):
            return
        
        try:
            conn = sqlite3.connect(DB_FILE)
            with conn:
                conn.execute(
                    "UPDATE cases SET case_status = 'Closed', closed_date = ? WHERE id = ?",
                    (iso_today(), self.current_case_id)
                )
            conn.close()
            
            # Update the UI
            self.var_case_status.set("Closed")
            
            messagebox.showinfo("Case Closed", "Case has been successfully closed.")
            
            # Refresh displays
            if self.current_patient_id:
                self.load_case_history_for_patient(self.current_patient_id)
        
        except sqlite3.Error as e:
            messagebox.showerror("Database Error", f"Could not close case.\n{e}")

    def on_export_case_to_pdf(self):
        """Export current case to PDF"""
        if not self.current_case_id or not self.current_patient_id:
            messagebox.showwarning("No Case", "Please load a case first to export.")
            return
        
        try:
            # Get patient name for filename
            conn = sqlite3.connect(DB_FILE)
            patient = conn.execute(
                "SELECT first_name, last_name FROM patients WHERE id = ?",
                (self.current_patient_id,)
            ).fetchone()
            case = conn.execute(
                "SELECT op_number, case_date FROM cases WHERE id = ?",
                (self.current_case_id,)
            ).fetchone()
            conn.close()
            
            if not patient or not case:
                messagebox.showerror("Error", "Could not load patient/case data.")
                return
            
            first_name, last_name = patient
            op_number, case_date = case
            
            # Default filename
            default_filename = f"Case_{op_number}_{first_name}_{last_name}_{case_date}.pdf"
            
            # File dialog to save PDF
            file_path = filedialog.asksaveasfilename(
                defaultextension=".pdf",
                initialfile=default_filename,
                filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
                title="Export Case to PDF"
            )
            
            if not file_path:
                return  # User cancelled
            
            # Export to PDF
            if export_case_to_pdf(self.current_case_id, self.current_patient_id, file_path):
                messagebox.showinfo("Success", f"Case exported successfully to:\n{file_path}")
            else:
                messagebox.showerror("Error", "Failed to export case to PDF. Check the error logs.")
                
        except Exception as e:
            messagebox.showerror("Error", f"Error exporting case:\n{str(e)}")

    def on_export_case_from_search(self):
        """Export selected case from search results to PDF"""
        sel = self.search_tree.selection()
        if not sel:
            messagebox.showwarning("No Selection", "Please select a case to export.")
            return
        
        case_id = int(self.search_tree.item(sel[0], "values")[0])
        
        try:
            conn = sqlite3.connect(DB_FILE)
            case = conn.execute(
                "SELECT patient_id, op_number, case_date FROM cases WHERE id = ?",
                (case_id,)
            ).fetchone()
            
            if not case:
                messagebox.showerror("Error", "Case not found.")
                conn.close()
                return
            
            patient_id, op_number, case_date = case
            patient = conn.execute(
                "SELECT first_name, last_name FROM patients WHERE id = ?",
                (patient_id,)
            ).fetchone()
            conn.close()
            
            if not patient:
                messagebox.showerror("Error", "Patient not found.")
                return
            
            first_name, last_name = patient
            default_filename = f"Case_{op_number}_{first_name}_{last_name}_{case_date}.pdf"
            
            # File dialog to save PDF
            file_path = filedialog.asksaveasfilename(
                defaultextension=".pdf",
                initialfile=default_filename,
                filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
                title="Export Case to PDF"
            )
            
            if not file_path:
                return
            
            # Export to PDF
            if export_case_to_pdf(case_id, patient_id, file_path):
                messagebox.showinfo("Success", f"Case exported successfully to:\n{file_path}")
            else:
                messagebox.showerror("Error", "Failed to export case to PDF. Check the error logs.")
                
        except Exception as e:
            messagebox.showerror("Error", f"Error exporting case:\n{str(e)}")

# ---------------------- Run ----------------------

if __name__ == "__main__":
    app = ClinicApp()
    app.mainloop()
