#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Clinic App: Patient management + Case sheet with Treatment Plan + Search & History
Built with tkinter clinic_app.py
Requires: Python 3.9 (tkinter, sqlite3 included in standard library)
"""

import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, timedelta

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
            address TEXT,
            UNIQUE(phone) ON CONFLICT IGNORE
        );
        
        CREATE TABLE IF NOT EXISTS cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            op_number INTEGER UNIQUE,  -- Outpatient number (manually entered)
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
        CREATE INDEX IF NOT EXISTS idx_cases_op_number ON cases(op_number);
        """
    )

    conn.commit()
    conn.close()

# ---------------------- Main App ----------------------

class ClinicApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Clinic App: Patient & Case Management")
        self.geometry("1200x800")
        self.minsize(1050, 740)
        
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
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
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
        bottom = ttk.Frame(self, padding=(8, 4))
        bottom.pack(fill="x")
        ttk.Button(bottom, text="Save Patient", command=self.on_save_patient).pack(side="right")
        
        # Right side buttons
        ttk.Button(bottom, text="Close Case", command=self.on_close_case).pack(side="right", padx=(6, 0))
        ttk.Button(bottom, text="Save Case + Plan", command=self.on_save_case).pack(side="right")
        ttk.Button(bottom, text="New Case", command=self.on_new_case).pack(side="right", padx=(0, 6))

    # --------- Patients Tab ---------

    def build_patients_tab(self):
        f = self.tab_patients
        for i in range(0, 4):
            f.columnconfigure(i, weight=1)
        
        # Search filters
        self.var_p_name = tk.StringVar()
        self.var_p_phone = tk.StringVar()
        row = 0
        ttk.Label(f, text="Name (contains)").grid(row=row, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.var_p_name).grid(row=row, column=1, sticky="ew", padx=4, pady=4)
        ttk.Label(f, text="Phone").grid(row=row, column=2, sticky="w")
        ttk.Entry(f, textvariable=self.var_p_phone).grid(row=row, column=3, sticky="ew", padx=4, pady=4)
        row += 1        
        btns = ttk.Frame(f)
        btns.grid(row=row, column=0, columnspan=4, sticky="e")
        ttk.Button(btns, text="Search", command=self.on_patients_search).grid(row=0, column=0, padx=4)
        ttk.Button(btns, text="Clear", command=self.on_patients_clear).grid(row=0, column=1, padx=4)
        ttk.Button(btns, text="New Patient", command=self.on_new_patient).grid(row=0, column=2, padx=4)
        ttk.Button(btns, text="Delete Patient", command=self.on_delete_patient).grid(row=0, column=3, padx=4)
        
        # Patient form
        row += 1
        form = ttk.LabelFrame(f, text="Patient Details")
        form.grid(row=row, column=0, columnspan=4, sticky="ew", padx=4, pady=8)
        for i in range(0, 4):
            form.columnconfigure(i, weight=1)
        
        self.var_first = tk.StringVar()
        self.var_last = tk.StringVar()
        self.var_gender = tk.StringVar()
        self.var_dob = tk.StringVar(value="")
        self.var_phone = tk.StringVar()
        self.var_email = tk.StringVar()
        self.var_address = tk.StringVar()
        
        ttk.Label(form, text="First Name *").grid(row=0, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.var_first).grid(row=0, column=1, sticky="ew", padx=4, pady=4)
        ttk.Label(form, text="Last Name *").grid(row=0, column=2, sticky="w")
        ttk.Entry(form, textvariable=self.var_last).grid(row=0, column=3, sticky="ew", padx=4, pady=4)
        
        ttk.Label(form, text="Gender").grid(row=1, column=0, sticky="w")
        ttk.Combobox(form, textvariable=self.var_gender, values=("Male", "Female", "Other"), state="readonly") \
            .grid(row=1, column=1, sticky="ew", padx=4, pady=4)
        
        ttk.Label(form, text="Date of Birth (YYYY-MM-DD)").grid(row=1, column=2, sticky="w")
        ttk.Entry(form, textvariable=self.var_dob).grid(row=1, column=3, sticky="ew", padx=4, pady=4)
        
        ttk.Label(form, text="Phone").grid(row=2, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.var_phone).grid(row=2, column=1, sticky="ew", padx=4, pady=4)
        ttk.Label(form, text="Email").grid(row=2, column=2, sticky="w")
        ttk.Entry(form, textvariable=self.var_email).grid(row=2, column=3, sticky="ew", padx=4, pady=4)        
        ttk.Label(form, text="Address").grid(row=3, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.var_address).grid(row=3, column=1, columnspan=3, sticky="ew", padx=4, pady=4)
        
        # Patient list + Case history
        row += 1
        split = ttk.Frame(f)
        split.grid(row=row, column=0, columnspan=4, sticky="nsew")
        f.rowconfigure(row, weight=1)
        split.columnconfigure(0, weight=1)
        split.columnconfigure(1, weight=1)
        
        # Patients tree
        p_cols = ("id", "first_name", "last_name", "phone", "email", "dob")
        self.p_tree = ttk.Treeview(split, columns=p_cols, show="headings", height=12)
        headers = {
            "id": "ID", "first_name": "First", "last_name": "Last",
            "phone": "Phone", "email": "Email", "dob": "DOB"
        }
        widths = (60, 120, 120, 120, 160, 100)
        for (c, w) in zip(p_cols, widths):
            self.p_tree.heading(c, text=headers[c])
            self.p_tree.column(c, width=w, anchor="center")
        self.p_tree.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self.p_tree.bind("<<TreeviewSelect>>", self.on_patient_selected)
        yscroll_p = ttk.Scrollbar(split, orient="vertical", command=self.p_tree.yview)
        yscroll_p.grid(row=0, column=1, sticky="nse")
        self.p_tree.configure(yscrollcommand=yscroll_p.set)
        
        # Case history tree (for selected patient)
        c_cols = ("case_id", "date", "follow_up", "chief", "diagnosis", "status", "items")
        self.c_tree = ttk.Treeview(split, columns=c_cols, show="headings", height=12)
        c_headers = {
            "case_id": "Case ID", "date": "Date", "follow_up": "Follow-up",
            "chief": "Chief Complaint", "diagnosis": "Diagnosis", "status": "Status", "items": "Plan Items"
        }
        c_widths = (80, 100, 110, 200, 80)
        for (c, w) in zip(c_cols, c_widths):
            self.c_tree.heading(c, text=c_headers[c])
            self.c_tree.column(c, width=w, anchor="center")
        self.c_tree.grid(row=0, column=1, sticky="nsew", padx=4, pady=4)
        yscroll_c = ttk.Scrollbar(split, orient="vertical", command=self.c_tree.yview)
        yscroll_c.grid(row=0, column=1, sticky="nse")
        self.c_tree.configure(yscrollcommand=yscroll_c.set)
        
        # Case history actions
        act = ttk.Frame(f)
        act.grid(row=row+1, column=0, columnspan=4, sticky="ew")
        ttk.Button(act, text="Open Selected Case", command=self.on_open_selected_history_case).grid(row=0, column=0, padx=4)
        ttk.Button(act, text="New Case for Selected Patient", command=self.on_new_case_for_selected_patient).grid(row=0, column=1, padx=4)
        
        # Initial load
        self.on_patients_search()
    
    def on_patients_search(self):
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
            SELECT id, first_name, last_name, phone, email, dob
            FROM patients
            WHERE {' AND '.join(where)}
            ORDER BY last_name, first_name
            LIMIT 500
        """
        
        print(f"Debug - SQL: {sql}")  # Debug line
        print(f"Debug - Params: {params}")  # Debug line
        
        conn = sqlite3.connect(DB_FILE)
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        
        print(f"Debug - Found {len(rows)} results")  # Debug line
        
        for r in rows:
            self.p_tree.insert("", "end", values=r)

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
        
        self.load_case_history_for_patient(self.current_patient_id)

    def load_case_history_for_patient(self, patient_id: int):
        self.clear_case_history()
        sql = (
            "SELECT c.id, c.op_number, c.case_date, c.follow_up_date, c.chief_complaint, c.diagnosis, c.case_status, "
            "'(select count(*) from treatment_plans tp where tp.case_id = c.id) AS items' "
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
            
            dob = safe_str(self.var_dob.get())
            if dob:
                parse_date(dob)
            
            conn = sqlite3.connect(DB_FILE)
            with conn:
                if self.current_patient_id is None:
                    conn.execute(
                        """
                        INSERT INTO patients(first_name, last_name, gender, dob, phone, email, address)
                        VALUES(?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            safe_str(self.var_first.get()), safe_str(self.var_last.get()),
                            safe_str(self.var_gender.get()), dob,
                            safe_str(self.var_phone.get()), safe_str(self.var_email.get()),
                            safe_str(self.var_address.get())
                        )
                    )
                    self.current_patient_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                else:
                    conn.execute(
                        """
                        UPDATE patients
                        SET first_name=?, last_name=?, gender=?, dob=?, phone=?, email=?, address=?
                        WHERE id=?
                        """,
                        (
                            safe_str(self.var_first.get()), safe_str(self.var_last.get()),
                            safe_str(self.var_gender.get()), dob,
                            safe_str(self.var_phone.get()), safe_str(self.var_email.get()),
                            safe_str(self.var_address.get()), self.current_patient_id
                        )
                    )
            
            conn.close()
            messagebox.showinfo("Saved", "Patient saved.")
            self.on_patients_search()
            # Auto-select the saved patient in the tree
            for iid in self.p_tree.get_children():
                vals = self.p_tree.item(iid, "values")
                if int(vals[0]) == self.current_patient_id:
                    self.p_tree.selection_set(iid)
                    self.p_tree.see(iid)
                    break
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
        for i in range(4):
            content_frame.columnconfigure(i, weight=1)
        
        row = 0
        
        # === CASE INFORMATION SECTION ===
        case_info_frame = ttk.LabelFrame(content_frame, text="Case Information", padding=10)
        case_info_frame.grid(row=row, column=0, columnspan=4, sticky="ew", padx=8, pady=5)
        for i in range(4):
            case_info_frame.columnconfigure(i, weight=1)
        
        self.var_case_date = tk.StringVar(value=iso_today())
        self.var_followup_date = tk.StringVar(value="")
        self.var_case_status = tk.StringVar(value="Open")
        self.var_op_number = tk.StringVar(value="")
        
        # First row: OP Number and Case Date
        ttk.Label(case_info_frame, text="OP Number *").grid(row=0, column=0, sticky="w")
        ttk.Entry(case_info_frame, textvariable=self.var_op_number, width=20).grid(row=0, column=1, sticky="w", padx=4, pady=4)
        
        ttk.Label(case_info_frame, text="Case Date (YYYY-MM-DD)").grid(row=0, column=2, sticky="w")
        ttk.Entry(case_info_frame, textvariable=self.var_case_date, width=20).grid(row=0, column=3, sticky="w", padx=4, pady=4)
        
        # Second row: Follow-up Date and Case Status
        ttk.Label(case_info_frame, text="Follow-up Date (YYYY-MM-DD)").grid(row=1, column=0, sticky="w")
        ttk.Entry(case_info_frame, textvariable=self.var_followup_date, width=20).grid(row=1, column=1, sticky="w", padx=4, pady=4)
        
        ttk.Label(case_info_frame, text="Case Status").grid(row=1, column=2, sticky="w")
        ttk.Combobox(case_info_frame, textvariable=self.var_case_status,
            values=("Open", "In Progress", "Closed", "Cancelled"),
            state="readonly", width=15).grid(row=1, column=3, sticky="w", padx=4, pady=4)
        
        # Third row: Chief Complaint
        ttk.Label(case_info_frame, text="Chief Complaint *").grid(row=2, column=0, sticky="w")
        self.entry_cc = ttk.Entry(case_info_frame)
        self.entry_cc.grid(row=2, column=1, columnspan=3, sticky="ew", padx=4, pady=4)
        
        row += 1
        
        # === MEDICAL & DENTAL HISTORY SECTION ===
        history_frame = ttk.LabelFrame(content_frame, text="Medical & Dental History", padding=10)
        history_frame.grid(row=row, column=0, columnspan=4, sticky="nsew", padx=5, pady=5)
        for i in range(2):
            history_frame.columnconfigure(i, weight=1)
        
        ttk.Label(history_frame, text="Past Medical History").grid(row=0, column=0, sticky="w")
        self.txt_medical_history = tk.Text(history_frame, height=4, wrap="word")
        self.txt_medical_history.grid(row=1, column=0, sticky="nsew", padx=(0, 5), pady=4)
        
        ttk.Label(history_frame, text="Past Dental History").grid(row=0, column=1, sticky="w")
        self.txt_dental_history = tk.Text(history_frame, height=4, wrap="word")
        self.txt_dental_history.grid(row=1, column=1, sticky="nsew", padx=(5, 0), pady=4)
        
        history_frame.rowconfigure(1, weight=1)
        
        row += 1
        
        # === CLINICAL EXAMINATION SECTION ===
        exam_frame = ttk.LabelFrame(content_frame, text="Clinical Examination & Diagnosis", padding=10)
        exam_frame.grid(row=row, column=0, columnspan=4, sticky="nsew", padx=5, pady=5)
        for i in range(2):
            exam_frame.columnconfigure(i, weight=1)
        
        ttk.Label(exam_frame, text="Extra & Intra Oral Examinations").grid(row=0, column=0, sticky="w")
        self.txt_exam = tk.Text(exam_frame, height=5, wrap="word")
        self.txt_exam.grid(row=1, column=0, sticky="nsew", padx=(0, 5), pady=4)
        
        ttk.Label(exam_frame, text="Diagnosis").grid(row=0, column=1, sticky="w")
        self.txt_dx = tk.Text(exam_frame, height=5, wrap="word")
        self.txt_dx.grid(row=1, column=1, sticky="nsew", padx=(5, 0), pady=4)
        
        exam_frame.rowconfigure(1, weight=1)
        
        row += 1
        
        # === CONSENT FORM SECTION ===
        consent_frame = ttk.LabelFrame(content_frame, text="Patient Consent", padding=10)
        consent_frame.grid(row=row, column=0, columnspan=4, sticky="ew", padx=5, pady=5)
        for i in range(4):
            consent_frame.columnconfigure(i, weight=1)
        
        self.var_consent_obtained = tk.BooleanVar(value=False)
        self.var_consent_date = tk.StringVar(value="")
        self.var_consent_file = tk.StringVar(value="")
        
        ttk.Checkbutton(consent_frame, text="Consent Obtained",
            variable=self.var_consent_obtained).grid(row=0, column=0, sticky="w", padx=4)
        
        ttk.Label(consent_frame, text="Consent Date").grid(row=0, column=1, sticky="w")
        ttk.Entry(consent_frame, textvariable=self.var_consent_date, width=20).grid(row=0, column=2, sticky="w", padx=4, pady=4)
        
        ttk.Label(consent_frame, text="Consent Form").grid(row=1, column=0, sticky="w")
        consent_file_frame = ttk.Frame(consent_frame)
        consent_file_frame.grid(row=1, column=1, columnspan=3, sticky="ew", padx=4, pady=4)
        consent_file_frame.columnconfigure(0, weight=1)
        
        ttk.Entry(consent_file_frame, textvariable=self.var_consent_file, state="readonly").grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ttk.Button(consent_file_frame, text="Browse", command=self.on_browse_consent_file).grid(row=0, column=1)
        ttk.Button(consent_file_frame, text="View", command=self.on_view_consent_file).grid(row=0, column=2, padx=(5, 0))
        
        row += 1
        
        # === VITALS SECTION ===
        vitals_frame = ttk.LabelFrame(content_frame, text="Vital Signs", padding=10)
        vitals_frame.grid(row=row, column=0, columnspan=4, sticky="ew", padx=5, pady=5)
        for i in range(8):
            vitals_frame.columnconfigure(i, weight=1)
        
        self.var_bp = tk.StringVar()
        self.var_hr = tk.StringVar()
        self.var_temp = tk.StringVar()
        self.var_weight = tk.StringVar()
        
        ttk.Label(vitals_frame, text="BP (e.g., 120/80)").grid(row=0, column=0, sticky="w")
        ttk.Entry(vitals_frame, textvariable=self.var_bp, width=15).grid(row=0, column=1, sticky="w", padx=4, pady=4)
        ttk.Label(vitals_frame, text="HR (bpm)").grid(row=0, column=2, sticky="w")
        ttk.Entry(vitals_frame, textvariable=self.var_hr, width=10).grid(row=0, column=3, sticky="w", padx=4, pady=4)
        ttk.Label(vitals_frame, text="Temp (°C)").grid(row=0, column=4, sticky="w")
        ttk.Entry(vitals_frame, textvariable=self.var_temp, width=10).grid(row=0, column=5, sticky="w", padx=4, pady=4)
        ttk.Label(vitals_frame, text="Weight (kg)").grid(row=0, column=6, sticky="w")
        ttk.Entry(vitals_frame, textvariable=self.var_weight, width=10).grid(row=0, column=7, sticky="w", padx=4, pady=4)
        
        row += 1
        
        # === TREATMENT PLAN SECTION ===
        treatment_frame = ttk.LabelFrame(content_frame, text="Treatment Plan", padding=10)
        treatment_frame.grid(row=row, column=0, columnspan=4, sticky="nsew", padx=5, pady=5)
        for i in range(4):
            treatment_frame.columnconfigure(i, weight=1)
        
        # Treatment plan input fields
        plan_input_frame = ttk.Frame(treatment_frame)
        plan_input_frame.grid(row=0, column=0, columnspan=4, sticky="ew", padx=(0, 10))
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
        
        ttk.Label(plan_input_frame, text="Type").grid(row=0, column=0, sticky="w")
        ttk.Combobox(plan_input_frame, textvariable=self.var_item_type,
            values=("Medication", "Procedure", "Test", "Advice"), state="readonly") \
            .grid(row=0, column=1, sticky="ew", padx=4, pady=4)
        
        ttk.Label(plan_input_frame, text="Name *").grid(row=0, column=2, sticky="w")
        ttk.Entry(plan_input_frame, textvariable=self.var_name).grid(row=0, column=3, sticky="ew", padx=4, pady=4)
        
        ttk.Label(plan_input_frame, text="Dosage").grid(row=1, column=0, sticky="w")
        ttk.Entry(plan_input_frame, textvariable=self.var_dosage).grid(row=1, column=1, sticky="ew", padx=4, pady=4)
        
        ttk.Label(plan_input_frame, text="Frequency").grid(row=1, column=2, sticky="w")
        ttk.Entry(plan_input_frame, textvariable=self.var_frequency).grid(row=1, column=3, sticky="ew", padx=4, pady=4)
        
        ttk.Label(plan_input_frame, text="Duration (days)").grid(row=2, column=0, sticky="w")
        ttk.Entry(plan_input_frame, textvariable=self.var_duration).grid(row=2, column=1, sticky="ew", padx=4, pady=4)
        
        ttk.Label(plan_input_frame, text="Start Date").grid(row=2, column=2, sticky="w")
        ttk.Entry(plan_input_frame, textvariable=self.var_start).grid(row=2, column=3, sticky="ew", padx=4, pady=4)
        
        ttk.Label(plan_input_frame, text="Status").grid(row=3, column=0, sticky="w")
        ttk.Combobox(plan_input_frame, textvariable=self.var_status,
            values=("Planned", "Ongoing", "Completed"), state="readonly") \
            .grid(row=3, column=1, sticky="ew", padx=4, pady=4)
        
        ttk.Label(plan_input_frame, text="Notes").grid(row=3, column=2, sticky="w")
        ttk.Entry(plan_input_frame, textvariable=self.var_notes).grid(row=3, column=3, sticky="ew", padx=4, pady=4)

        # Treatment plan buttons
        plan_btn_frame = ttk.Frame(treatment_frame)
        plan_btn_frame.grid(row=1, column=0, columnspan=4, sticky="ew", padx=(0, 10))
        ttk.Button(plan_btn_frame, text="Add Item", command=self.on_add_plan).pack(side="left", padx=2)
        ttk.Button(plan_btn_frame, text="Edit Selected", command=self.on_edit_plan).pack(side="left", padx=2)
        ttk.Button(plan_btn_frame, text="Save Changes", command=self.on_save_plan_changes).pack(side="left", padx=2)
        ttk.Button(plan_btn_frame, text="Delete Selected", command=self.on_delete_plan).pack(side="left", padx=2)
        ttk.Button(plan_btn_frame, text="Clear Form", command=self.clear_plan_inputs).pack(side="left", padx=2)
        
        # Treatment plan tree
        tree_frame = ttk.Frame(treatment_frame)
        tree_frame.grid(row=2, column=0, columnspan=4, sticky="nsew", pady=0)
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)
        
        cols = ("type", "name", "dosage", "frequency", "duration", "start", "end", "status", "notes")
        self.plan_tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=8)
        for c, w in zip(cols, (100, 160, 100, 100, 80, 100, 100, 100, 180)):
            self.plan_tree.heading(c, text=c.title())
            self.plan_tree.column(c, width=100, anchor="center")
        self.plan_tree.grid(row=0, column=0, sticky="nsew")
        
        plan_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.plan_tree.yview)
        plan_scroll.grid(row=0, column=1, sticky="ns")
        self.plan_tree.configure(yscrollcommand=plan_scroll.set)
        
        treatment_frame.rowconfigure(2, weight=1)
        
        # Configure main content frame row weights
        content_frame.rowconfigure(1, weight=1)  # Medical & Dental history
        content_frame.rowconfigure(2, weight=1)  # Clinical examination
        content_frame.rowconfigure(5, weight=1)  # Treatment plan
        
        # Enable mouse wheel scrolling
        def on_mousewheel(event):            
            main_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        main_canvas.bind_all("<MouseWheel>", on_mousewheel)

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
        
        f.rowconfigure(row+1, weight=1)

    # ---------------------- Treatment Plan Actions ----------------------

    def on_add_plan(self):
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

    def on_new_case(self):
        self.current_case_id = None
        self.var_case_date.set(iso_today())
        self.var_followup_date.set("")
        self.var_case_status.set("Open")
        self.var_op_number.set("")  # Leave empty for manual entry
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

# ---------------------- Run ----------------------

if __name__ == "__main__":
    init_db()
    app = ClinicApp()
    app.mainloop()