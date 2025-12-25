#!/usr/bin/env python3
"""
Quick test script to verify PDF export functionality
"""

import sqlite3
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.units import inch
from datetime import datetime

DB_FILE = "clinic.db"

def test_pdf_export():
    """Test if PDF export works with sample data"""
    print("Testing PDF export functionality...")
    
    # Check if database exists and has data
    try:
        conn = sqlite3.connect(DB_FILE)
        
        # Check for patients
        patients = conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
        print(f"Found {patients} patient(s)")
        
        # Check for cases
        cases = conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
        print(f"Found {cases} case(s)")
        
        # Get first case if available
        case = conn.execute(
            "SELECT c.id, c.patient_id, c.op_number FROM cases c LIMIT 1"
        ).fetchone()
        
        if case:
            case_id, patient_id, op_num = case
            print(f"\nFound case: ID={case_id}, OP Number={op_num}")
            
            # Try creating a simple PDF
            test_pdf_path = "test_export.pdf"
            from clinic_app_v1 import export_case_to_pdf
            
            if export_case_to_pdf(case_id, patient_id, test_pdf_path):
                print(f"SUCCESS: PDF created at {test_pdf_path}")
                import os
                if os.path.exists(test_pdf_path):
                    size = os.path.getsize(test_pdf_path)
                    print(f"PDF file size: {size} bytes")
            else:
                print("FAILED: Could not create PDF")
        else:
            print("\nNo cases found in database. Please create a case first to test export.")
            
        conn.close()
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_pdf_export()
