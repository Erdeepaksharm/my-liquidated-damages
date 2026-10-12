"""Unit tests for the Liquidated Damages (LD) Calculation Engine."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import date
from backend.models import PurchaseOrder
from backend.ld_engine import LDEngine
from backend.export_service import ExportService


def test_ld_calculation_matching_excel():
    """Validates that the calculation matches the exact formulas and numbers of LD Format.xlsx."""
    po = PurchaseOrder(
        po_number="PO-2026-00109",
        company_name="BQUBE IT SOLUTION NIGERIA LIMITED",
        vendor_name="Global Equipment Ltd",
        po_date=date(2026, 1, 2),
        po_acknowledged_date=date(2026, 1, 2),
        readiness_period_days=60,
        total_po_value=150000.00,
        currency="USD",
        material_received_date=date(2026, 3, 10),
        force_majeure_days=2,
        ld_rate_per_week=0.01,
        max_ld_limit_percent=0.05,
        invoice_value=150000.00,
        invoice_no="INV-88239"
    )

    result = LDEngine.calculate_ld(po)

    # 1. Expected date = 2026-01-02 + 60 days = 2026-03-03
    assert result.expected_readiness_date == date(2026, 3, 3)

    # 2. Gross delay = 2026-03-10 - 2026-03-03 = 7 days
    assert result.delay_in_days == 7

    # 3. Force majeure deduction = 2 days -> Net delay = 5 days
    assert result.delay_excl_force_majeure_days == 5

    # 4. Delay in weeks = 5 / 7 = 0.7143
    assert abs(result.delay_in_weeks - (5 / 7)) < 0.001

    # 5. Weekly LD = 150,000 * 0.01 = 1,500.00
    assert result.ld_per_completed_week == 1500.00

    # 6. Total LD = 1,500 * (5/7) = 1,071.43
    expected_ld = round(1500.0 * (5 / 7), 2)
    assert result.calculated_total_ld == expected_ld
    assert result.is_capped is False

    # 7. Net Payable = 150,000 - 1,071.43 = 148,928.57
    assert result.net_payable_amount == round(150000.00 - expected_ld, 2)


def test_ld_max_cap_limit():
    """Validates that delay exceeding the 5% cap is strictly capped at max allowable LD."""
    po = PurchaseOrder(
        po_number="PO-2026-CAPPED",
        vendor_name="Subsea Ltd",
        po_date=date(2025, 12, 1),
        po_acknowledged_date=date(2025, 12, 1),
        readiness_period_days=30,  # Expected: 2025-12-31
        total_po_value=100000.00,
        material_received_date=date(2026, 3, 1),  # Gross delay: 60 days (~8.57 weeks)
        force_majeure_days=0,
        ld_rate_per_week=0.01,
        max_ld_limit_percent=0.05,
        invoice_value=100000.00
    )

    result = LDEngine.calculate_ld(po)

    # Capped at 5% of 100,000 = 5,000.00
    assert result.is_capped is True
    assert result.calculated_total_ld == 5000.00
    assert result.net_payable_amount == 95000.00


def test_zero_or_early_delivery():
    """Validates that on-time or early delivery results in 0 LD."""
    po = PurchaseOrder(
        po_number="PO-2026-EARLY",
        vendor_name="Fast Supplier",
        po_date=date(2026, 1, 1),
        po_acknowledged_date=date(2026, 1, 1),
        readiness_period_days=60,
        total_po_value=50000.00,
        material_received_date=date(2026, 2, 1),  # Arrived early
        force_majeure_days=0,
        invoice_value=50000.00
    )

    result = LDEngine.calculate_ld(po)
    assert result.delay_excl_force_majeure_days == 0
    assert result.calculated_total_ld == 0.0
    assert result.net_payable_amount == 50000.00


def test_excel_export_structure():
    """Validates that Excel export produces valid binary workbook with non-empty content."""
    po = PurchaseOrder(
        po_number="PO-2026-TEST",
        vendor_name="Test Vendor",
        po_date=date(2026, 1, 2),
        po_acknowledged_date=date(2026, 1, 2),
        readiness_period_days=60,
        total_po_value=100000.0,
        material_received_date=date(2026, 3, 10),
        force_majeure_days=2,
        invoice_value=100000.0
    )
    excel_bytes = ExportService.generate_excel_bytes(po)
    assert len(excel_bytes) > 2000
    assert excel_bytes[:2] == b"PK"  # Zip archive / xlsx header


if __name__ == "__main__":
    test_ld_calculation_matching_excel()
    test_ld_max_cap_limit()
    test_zero_or_early_delivery()
    test_excel_export_structure()
    print("All LD engine unit tests passed successfully!")
