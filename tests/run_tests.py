import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.test_real_pos_training import (
    test_training_pos_exist,
    test_ocr_and_heuristic_extraction_single_po,
    test_ld_calculation_compliance_with_excel_format,
    test_ld_capping_at_5_percent,
    test_excel_and_pdf_generation_for_all_training_pos,
    test_doa_and_epicor_ap_chargeback_workflow
)

test_cases = [
    ("PO 200923.pdf", "200923", "USD", 20000.0),
    ("PO 201030.pdf", "201030", "NGN", 4000000.0),
    ("PO 201139.pdf", "201139", "NGN", 1500000.0),
    ("PO 201208.pdf", "201208", "NGN", 1500000.0),
    ("PO 201317.pdf", "201317", "NGN", 900000.0),
    ("PO 201337.pdf", "201337", "NGN", 3000000.0),
    ("PO 201354.pdf", "201354", "NGN", 5000000.0),
    ("PO 201355.pdf", "201355", "NGN", 5000000.0),
    ("PO 201357.pdf", "201357", "NGN", 10000000.0),
    ("PO 201361.pdf", "201361", "NGN", 15000000.0),
    ("PO 201384.pdf", "201384", "NGN", 3000000.0),
    ("PO 201385.pdf", "201385", "NGN", 100000000.0),
    ("PO 201402.pdf", "201402", "NGN", 4000000.0),
]

print("=" * 70, flush=True)
print("RUNNING LIQUIDATED DAMAGES AUTOMATION VERIFICATION SUITE", flush=True)
print("=" * 70, flush=True)

passed = 0
failed = 0

def run_test(name, fn, *args):
    global passed, failed
    try:
        fn(*args)
        print(f"  [PASS] {name}", flush=True)
        passed += 1
    except Exception as e:
        print(f"  [FAIL] {name}: {e}", flush=True)
        traceback.print_exc()
        failed += 1

# 1. Check training PDFs exist
run_test("test_training_pos_exist", test_training_pos_exist)

# 2. Check each PO extraction
for fname, short_po, curr, min_val in test_cases:
    run_test(f"test_ocr_extract_{fname}", test_ocr_and_heuristic_extraction_single_po, fname, short_po, curr, min_val)

# 3. Check calculation compliance
run_test("test_ld_calculation_compliance_with_excel_format", test_ld_calculation_compliance_with_excel_format)

# 4. Check 5% cap
run_test("test_ld_capping_at_5_percent", test_ld_capping_at_5_percent)

# 5. Check Excel & PDF exports
run_test("test_excel_and_pdf_generation_for_all_training_pos", test_excel_and_pdf_generation_for_all_training_pos)

# 6. Check DOA & Epicor posting
run_test("test_doa_and_epicor_ap_chargeback_workflow", test_doa_and_epicor_ap_chargeback_workflow)

print("=" * 70, flush=True)
print(f"TEST RESULTS: {passed} PASSED, {failed} FAILED (TOTAL: {passed + failed})", flush=True)
print("=" * 70, flush=True)

if failed > 0:
    sys.exit(1)
