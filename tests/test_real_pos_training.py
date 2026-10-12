"""Automated Test Suite verifying all 13 Real-World Training POs from the Downloads Dataset."""
import os
import glob
from datetime import date, timedelta

from backend.pdf_service import PDFService
from backend.ld_engine import LDEngine
from backend.models import PurchaseOrder, POLineItem
from backend.epicor_service import epicor_erp
from backend.approval_service import approval_hub
from backend.export_service import ExportService


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRAINING_POS_DIR = os.path.join(BASE_DIR, "sample_docs", "training_pos")


def test_training_pos_exist():
    """Verifies that all 13 training PDFs are in the sample_docs/training_pos directory."""
    pdf_files = sorted(glob.glob(os.path.join(TRAINING_POS_DIR, "*.pdf")))
    assert len(pdf_files) == 13, f"Expected 13 training PDFs, found {len(pdf_files)}"


def test_ocr_and_heuristic_extraction_single_po(pdf_filename, expected_short_po, expected_currency, min_value):
    """Tests that each training PO is parsed with correct OCR, currency, PO number, and financial values."""
    file_path = os.path.join(TRAINING_POS_DIR, pdf_filename)
    assert os.path.exists(file_path), f"File {file_path} does not exist"

    text, page_count, is_scanned = PDFService.extract_text_from_file(file_path, max_ocr_pages=5)
    assert page_count > 0, f"Failed to extract pages from {pdf_filename}"
    assert len(text) > 50, f"Extracted text too short for {pdf_filename}"
    
    # Parse PO
    po = PDFService.heuristic_extract_po(text, filename=pdf_filename)
    
    assert expected_short_po in po.po_number, f"Expected {expected_short_po} in PO number '{po.po_number}'"
    assert po.currency == expected_currency, f"Expected currency {expected_currency}, got {po.currency} in {pdf_filename}"
    assert po.total_po_value >= min_value, f"PO value {po.total_po_value} below minimum expected {min_value} in {pdf_filename}"
    assert po.ld_rate_per_week == 0.01 or po.ld_rate_per_week == 0.05
    assert po.max_ld_limit_percent == 0.05 or po.max_ld_limit_percent == 0.10


def test_ld_calculation_compliance_with_excel_format():
    """
    Validates LD calculation against the exact formula from LD Format.xlsx:
    - Expected readiness = PO Ack + Readiness days
    - Gross delay = Actual receipt - Expected readiness
    - Net delay = max(0, gross delay - force majeure)
    - Delay in weeks = Net delay / 7.0
    - Weekly LD = Invoice Value * 1%
    - Total LD = min(Delay Weeks * Weekly LD, Invoice Value * 5%)
    """
    po = PurchaseOrder(
        po_number="BISNL/201139/2-2026/GC000077",
        company_name="Bqube IT Solutions Nigeria Limited",
        vendor_name="Konga Online Nigeria Limited",
        po_date=date(2026, 1, 2),
        po_acknowledged_date=date(2026, 1, 2),
        readiness_period_days=60,
        total_po_value=1720000.0,
        invoice_value=1720000.0,
        currency="NGN",
        material_received_date=date(2026, 3, 10),
        force_majeure_days=2,
        ld_rate_per_week=0.01,
        max_ld_limit_percent=0.05
    )

    calc = LDEngine.calculate_ld(po)
    
    # Expected readiness date: 2026-01-02 + 60 days = 2026-03-03
    assert calc.expected_readiness_date == date(2026, 3, 3)
    # Gross delay: 2026-03-10 - 2026-03-03 = 7 days
    assert calc.delay_in_days == 7
    # Net delay excluding 2 days Force Majeure = 5 days
    assert calc.delay_excl_force_majeure_days == 5
    # Delay in weeks = 5 / 7 = 0.7143 weeks
    assert abs(calc.delay_in_weeks - (5 / 7.0)) < 1e-4
    # LD per week = 1,720,000 * 0.01 = 17,200 NGN
    assert calc.ld_per_completed_week == 17200.0
    # Total LD = 0.7142857 * 17200 = 12,285.71 NGN
    expected_total_ld = round((5 / 7.0) * 17200.0, 2)
    assert calc.calculated_total_ld == expected_total_ld
    # Net payable = 1,720,000 - 12,285.71 = 1,707,714.29 NGN
    assert calc.net_payable_amount == round(1720000.0 - expected_total_ld, 2)
    assert not calc.is_capped


def test_ld_capping_at_5_percent():
    """Tests that delays exceeding 5 weeks hit the 5% max cap."""
    po = PurchaseOrder(
        po_number="PO-2026-LONGDELAY",
        vendor_name="Global Vendor Ltd",
        po_date=date(2026, 1, 1),
        po_acknowledged_date=date(2026, 1, 1),
        readiness_period_days=30,
        total_po_value=100000.0,
        invoice_value=100000.0,
        currency="USD",
        material_received_date=date(2026, 4, 1),
        force_majeure_days=0,
        ld_rate_per_week=0.01,
        max_ld_limit_percent=0.05
    )

    calc = LDEngine.calculate_ld(po)
    
    assert calc.is_capped is True
    assert calc.calculated_total_ld == 5000.0
    assert calc.net_payable_amount == 95000.0


def test_excel_and_pdf_generation_for_all_training_pos():
    """Verifies that official Excel and PDF reports can be exported for all 13 training POs."""
    pos = epicor_erp.list_pos()
    assert len(pos) >= 13

    for po in pos[:13]:
        excel_bytes = ExportService.generate_excel_bytes(po)
        assert len(excel_bytes) > 1000, f"Excel bytes too small for {po.po_number}"

        pdf_bytes = ExportService.generate_pdf_report_bytes(po)
        assert len(pdf_bytes) > 1000, f"PDF bytes too small for {po.po_number}"


def test_doa_and_epicor_ap_chargeback_workflow():
    """Verifies end-to-end DOA workflow: Creation -> Accounts HOD -> C&P HOD -> Epicor AP Debit Note."""
    po = epicor_erp.get_po("AIFZE/BISNL/200923/10-2025/GC000203")
    assert po is not None

    calc = LDEngine.calculate_ld(po)
    req = approval_hub.create_request(po, calc, justification="End-to-end DOA test")
    
    t1 = approval_hub.approve_tier_1_accounts(req.case_id, approver_name="O. Adebayo", comments="Verified")
    assert t1.status == "Pending C&P HOD"
    
    t2 = approval_hub.approve_tier_2_cnp(req.case_id, approver_name="C. Okafor", waiver_decision="Approve Full")
    assert t2.status == "Approved"
    
    cb = epicor_erp.post_ap_chargeback(t2)
    assert cb.document_type == "LD-DR"
    assert cb.gl_account == "6050-00-LD"
    assert cb.ld_deduction_amount == calc.calculated_total_ld
    assert cb.status == "POSTED"
