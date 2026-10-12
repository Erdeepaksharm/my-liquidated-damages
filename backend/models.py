"""Data models for Liquidated Damages (LD) Automation System."""
from datetime import date, datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class POLineItem(BaseModel):
    line_no: int
    item_code: str
    description: str
    quantity: float
    unit_price: float
    line_total: float
    unit_of_measure: str = "EA"


class PurchaseOrder(BaseModel):
    po_number: str
    company_name: str = "BQUBE IT SOLUTION NIGERIA LIMITED"
    vendor_name: str
    vendor_code: Optional[str] = None
    site: Optional[str] = "Port Harcourt Site 1"
    po_date: date
    po_acknowledged_date: date
    readiness_period_days: int = 60
    total_po_value: float
    currency: str = "USD"
    
    # Delivery tracking
    waybill_no: Optional[str] = None
    waybill_date: Optional[date] = None
    material_received_date: Optional[date] = None  # JCC Date / Site Receipt Date
    force_majeure_days: int = 0
    force_majeure_reason: Optional[str] = None
    
    # Contract terms
    ld_rate_per_week: float = 0.01  # 1% per completed week
    max_ld_limit_percent: float = 0.05  # 5% max cap
    rounding_mode: str = "exact"  # 'exact' (fractional weeks) or 'completed' (floor)
    
    # Invoicing
    invoice_no: Optional[str] = None
    invoice_date: Optional[date] = None
    invoice_value: Optional[float] = None
    
    # Items
    line_items: List[POLineItem] = []
    
    # Status
    status: str = "Open"  # 'Open', 'In Review', 'LD Approved', 'Waived', 'Posted to Epicor'
    
    # Source metadata
    source_pdf_filename: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)


class LDCalculationResult(BaseModel):
    po_number: str
    company_name: str
    vendor_name: str
    po_date: date
    po_acknowledged_date: date
    readiness_period_days: int
    expected_readiness_date: date
    waybill_date: Optional[date] = None
    material_received_date: Optional[date] = None
    
    # Delays
    delay_in_days: int  # Gross delay
    force_majeure_days: int
    delay_excl_force_majeure_days: int  # Net delay
    delay_in_weeks: float
    completed_delayed_weeks: float
    
    # Values & Rates
    total_po_value: float
    invoice_value: float
    ld_rate_per_week: float
    max_ld_limit_percent: float
    
    # Damages
    ld_per_completed_week: float
    calculated_total_ld: float
    ld_as_per_po: float
    max_allowable_ld: float
    is_capped: bool = False
    
    # Financial summary
    net_payable_amount: float
    currency: str = "USD"
    invoice_no: Optional[str] = None
    
    # Calculation notes & formula explanation
    explanation: List[str] = []


class ApprovalRequest(BaseModel):
    case_id: str
    po_number: str
    vendor_name: str
    invoice_no: str
    invoice_value: float
    calculated_ld_amount: float
    proposed_ld_amount: float
    waiver_amount: float = 0.0
    waiver_type: str = "None"  # 'None', 'Partial', 'Full'
    justification: str
    
    # Routing
    current_tier: int = 1  # Tier 1: Accounts HOD, Tier 2: C&P HOD / Management
    accounts_hod_approval: Optional[Dict[str, Any]] = None
    cnp_hod_approval: Optional[Dict[str, Any]] = None
    status: str = "Pending Accounts HOD"  # 'Pending Accounts HOD', 'Pending C&P HOD', 'Approved', 'Partially Waived', 'Waived', 'Rejected'
    epicor_posted: bool = False
    epicor_chargeback_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)


class EpicorChargeback(BaseModel):
    chargeback_id: str  # e.g., "CB-2026-0089"
    document_type: str = "LD-DR"  # Liquidated Damages Debit Note
    po_number: str
    vendor_name: str
    vendor_code: Optional[str] = None
    invoice_no: str
    original_invoice_amount: float
    ld_deduction_amount: float
    net_invoice_payable: float
    currency: str = "USD"
    gl_account: str = "6050-00-LD"  # Liquidated Damages Recoveries / AP Adjustment
    approval_case_id: str
    approved_by_accounts: str
    approved_by_cnp: str
    posted_date: datetime = Field(default_factory=datetime.now)
    status: str = "POSTED"
    audit_log: List[str] = []


class ChatMessage(BaseModel):
    role: str  # 'user', 'assistant', 'system'
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)
    adaptive_card: Optional[Dict[str, Any]] = None
    suggestions: Optional[List[str]] = None


class ChatRequest(BaseModel):
    message: str
    po_context: Optional[Dict[str, Any]] = None
    gemini_api_key: Optional[str] = None
    conversation_history: List[Dict[str, str]] = []


class PDFExtractResponse(BaseModel):
    filename: str
    text_content: str
    page_count: int
    extracted_po: Optional[PurchaseOrder] = None
    calculation: Optional[LDCalculationResult] = None
    extraction_confidence: float = 0.95
    warnings: List[str] = []
    gemini_summary: Optional[str] = None
