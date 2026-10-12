"""Multi-tier Delegation of Authority (DOA) Approval Workflow Service."""
from datetime import datetime
from typing import Dict, Any, List, Optional
import uuid

from .models import ApprovalRequest, PurchaseOrder, LDCalculationResult


class ApprovalService:
    """Manages the lifecycle of LD approval requests across Accounts HOD and C&P HOD / Management."""

    def __init__(self):
        self._requests: Dict[str, ApprovalRequest] = {}

    def create_request(
        self,
        po: PurchaseOrder,
        calc: LDCalculationResult,
        waiver_type: str = "None",
        waiver_amount: float = 0.0,
        justification: str = "Standard contractual LD assessment per PO terms"
    ) -> ApprovalRequest:
        """Initializes a new LD approval case."""
        case_id = f"CASE-{po.po_number}-{uuid.uuid4().hex[:6].upper()}"
        proposed_ld = max(0.0, calc.calculated_total_ld - waiver_amount)
        
        req = ApprovalRequest(
            case_id=case_id,
            po_number=po.po_number,
            vendor_name=po.vendor_name,
            invoice_no=po.invoice_no or "INV-PENDING",
            invoice_value=calc.invoice_value,
            calculated_ld_amount=calc.calculated_total_ld,
            proposed_ld_amount=proposed_ld,
            waiver_amount=waiver_amount,
            waiver_type=waiver_type,
            justification=justification,
            current_tier=1,
            status="Pending Accounts HOD",
            created_at=datetime.now()
        )
        self._requests[case_id] = req
        return req

    def get_request(self, case_id: str) -> Optional[ApprovalRequest]:
        return self._requests.get(case_id)

    def list_requests(self) -> List[ApprovalRequest]:
        return list(self._requests.values())

    def approve_tier_1_accounts(
        self,
        case_id: str,
        approver_name: str = "Accounts HOD (O. Adebayo)",
        comments: str = "Verified delay calculations and invoice figures against delivery milestones."
    ) -> Optional[ApprovalRequest]:
        """Accounts HOD approval step (Tier 1)."""
        req = self._requests.get(case_id)
        if not req:
            return None
            
        req.accounts_hod_approval = {
            "approver": approver_name,
            "timestamp": datetime.now().isoformat(),
            "decision": "Approved",
            "comments": comments
        }
        req.current_tier = 2
        req.status = "Pending C&P HOD"
        return req

    def approve_tier_2_cnp(
        self,
        case_id: str,
        approver_name: str = "C&P HOD (C. Okafor)",
        waiver_decision: str = "Approve Full",  # 'Approve Full', 'Approve Partial Waiver', 'Approve Full Waiver', 'Reject'
        waiver_amount: Optional[float] = None,
        comments: str = "Approved in accordance with procurement terms and DOA limit."
    ) -> Optional[ApprovalRequest]:
        """C&P HOD / Management approval step (Tier 2)."""
        req = self._requests.get(case_id)
        if not req:
            return None
            
        if waiver_amount is not None:
            req.waiver_amount = waiver_amount
            req.proposed_ld_amount = max(0.0, req.calculated_ld_amount - waiver_amount)
            
        if waiver_decision == "Approve Full Waiver":
            req.waiver_type = "Full"
            req.proposed_ld_amount = 0.0
            req.waiver_amount = req.calculated_ld_amount
            req.status = "Waived"
        elif waiver_decision == "Approve Partial Waiver":
            req.waiver_type = "Partial"
            req.status = "Partially Waived"
        elif waiver_decision == "Reject":
            req.status = "Rejected"
        else:
            req.waiver_type = "None"
            req.status = "Approved"
            
        req.cnp_hod_approval = {
            "approver": approver_name,
            "timestamp": datetime.now().isoformat(),
            "decision": req.status,
            "comments": comments
        }
        req.current_tier = 3  # Completed
        return req


# Global singleton instance
approval_hub = ApprovalService()
