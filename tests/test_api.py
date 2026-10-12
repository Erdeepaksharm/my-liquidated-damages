"""Integration tests for FastAPI application endpoints."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi.testclient import TestClient
from backend.app import app

client = TestClient(app)


def test_root_endpoint():
    resp = client.get("/")
    assert resp.status_code == 200


def test_list_pos_endpoint():
    resp = client.get("/api/epicor/pos")
    assert resp.status_code == 200
    pos = resp.json()
    assert len(pos) >= 3
    assert any(p["po"]["po_number"] == "PO-2026-00109" for p in pos)


def test_calculate_ld_endpoint():
    payload = {
        "po_number": "PO-2026-API-TEST",
        "company_name": "BQUBE IT SOLUTION NIGERIA LIMITED",
        "vendor_name": "API Test Vendor",
        "po_date": "2026-01-02",
        "po_acknowledged_date": "2026-01-02",
        "readiness_period_days": 60,
        "total_po_value": 100000.0,
        "currency": "USD",
        "material_received_date": "2026-03-10",
        "force_majeure_days": 2,
        "ld_rate_per_week": 0.01,
        "max_ld_limit_percent": 0.05,
        "invoice_value": 100000.0,
        "invoice_no": "INV-API-01"
    }
    resp = client.post("/api/calculate-ld", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["delay_in_days"] == 7
    assert data["delay_excl_force_majeure_days"] == 5
    assert data["calculated_total_ld"] == round(1000.0 * (5/7), 2)


def test_upload_sample_pdf():
    sample_path = "/Users/akshayryali/liquidated damages/sample_docs/PO-2026-00109_Standard_Delay.pdf"
    if os.path.exists(sample_path):
        with open(sample_path, "rb") as f:
            files = {"file": ("PO-2026-00109_Standard_Delay.pdf", f, "application/pdf")}
            resp = client.post("/api/upload-po-pdf", files=files)
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert "extracted_po" in data
            assert "calculation" in data
            assert data["calculation"]["delay_excl_force_majeure_days"] == 5


def test_doa_approval_and_epicor_posting():
    # 1. Create/get an approval case
    pos_resp = client.get("/api/epicor/pos")
    assert pos_resp.status_code == 200
    
    submit_resp = client.post(
        "/api/approvals/submit",
        data={
            "po_number": "PO-2026-00109",
            "waiver_type": "None",
            "waiver_amount": "0",
            "justification": "Automated test submission"
        }
    )
    assert submit_resp.status_code == 200
    case_data = submit_resp.json()
    case_id = case_data["case_id"]

    # 2. Tier 1 Accounts HOD Approval
    t1_resp = client.post(
        f"/api/approvals/{case_id}/tier1-accounts",
        data={"approver": "Test Accounts HOD", "comments": "Approved math"}
    )
    assert t1_resp.status_code == 200
    assert t1_resp.json()["status"] == "Pending C&P HOD"

    # 3. Tier 2 C&P HOD Approval (triggers Epicor AP Chargeback posting)
    t2_resp = client.post(
        f"/api/approvals/{case_id}/tier2-cnp",
        data={"decision": "Approve Full", "approver": "Test CnP HOD", "comments": "Signed off"}
    )
    assert t2_resp.status_code == 200
    res = t2_resp.json()
    assert res["approval"]["status"] == "Approved"
    assert "epicor_chargeback" in res
    assert res["epicor_chargeback"]["document_type"] == "LD-DR"


if __name__ == "__main__":
    test_root_endpoint()
    test_list_pos_endpoint()
    test_calculate_ld_endpoint()
    test_upload_sample_pdf()
    test_doa_approval_and_epicor_posting()
    print("All API integration tests passed successfully!")
