"""Epicor ERP Integration and AP Chargeback / Debit Note Service Simulator."""
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional
import uuid

from .models import PurchaseOrder, POLineItem, EpicorChargeback, ApprovalRequest


class EpicorERPService:
    """Emulates Epicor Kinetic / ERP v10/v11 REST Services & AP Posting."""

    def __init__(self):
        self._pos: Dict[str, PurchaseOrder] = {}
        self._chargebacks: Dict[str, EpicorChargeback] = {}
        self._audit_trails: Dict[str, List[Dict[str, Any]]] = {}

    def get_po(self, po_number: str) -> Optional[PurchaseOrder]:
        """Retrieves a PO by exact or case-insensitive partial number."""
        if po_number in self._pos:
            return self._pos[po_number]
        # Search by partial
        for k, v in self._pos.items():
            if po_number.lower() in k.lower() or k.lower() in po_number.lower():
                return v
        return None

    def list_pos(self) -> List[PurchaseOrder]:
        """Returns all POs in the session."""
        return list(self._pos.values())

    def save_po(self, po: PurchaseOrder) -> PurchaseOrder:
        """Saves or updates a PO record."""
        self._pos[po.po_number] = po
        if po.po_number not in self._audit_trails:
            self._audit_trails[po.po_number] = [
                {
                    "timestamp": datetime.now().isoformat(),
                    "action": "DOCUMENT_INGESTED",
                    "details": f"PO {po.po_number} ingested with value {po.currency} {po.total_po_value:,.2f}"
                }
            ]
        return po

    def post_ap_chargeback(self, request: ApprovalRequest, gl_account: str = "6050-00-LD") -> EpicorChargeback:
        """Posts an approved Liquidated Damages AP Debit Note to Epicor ERP."""
        debit_note_id = f"DN-LD-{datetime.now().strftime('%Y%m')}-{str(uuid.uuid4())[:4].upper()}"
        
        chargeback = EpicorChargeback(
            chargeback_id=debit_note_id,
            po_number=request.po.po_number,
            vendor_name=request.po.vendor_name,
            invoice_no=request.po.invoice_no or f"INV-{request.po.po_number.split('/')[-1]}",
            invoice_original_value=request.po.invoice_value or request.po.total_po_value,
            ld_deduction_amount=request.calculation.calculated_total_ld,
            net_payable_amount=request.calculation.net_payable_amount,
            currency=request.po.currency,
            gl_account=gl_account,
            document_type="LD-DR",
            status="POSTED",
            posted_at=datetime.now(),
            epicor_transaction_ref=f"EPICOR-GL-TX-{uuid.uuid4().hex[:8].upper()}"
        )

        self._chargebacks[debit_note_id] = chargeback
        
        if request.po.po_number in self._audit_trails:
            self._audit_trails[request.po.po_number].append({
                "timestamp": datetime.now().isoformat(),
                "action": "AP_DEBIT_NOTE_POSTED",
                "details": f"Posted Debit Note {debit_note_id} for {request.po.currency} {chargeback.ld_deduction_amount:,.2f} to GL {gl_account}"
            })

        return chargeback

    def get_chargebacks(self) -> List[EpicorChargeback]:
        """Returns all posted AP Debit Notes."""
        return list(self._chargebacks.values())

    def get_audit_trail(self, po_number: str) -> List[Dict[str, Any]]:
        """Returns ERP audit trail entries for a given PO."""
        return self._audit_trails.get(po_number, [])


# Global Singleton Service instance
epicor_erp = EpicorERPService()
