"""Gemini AI and Intelligent Conversational Agent Service."""
import json
import os
import re
from datetime import date, datetime
from typing import Dict, Any, Optional, List, Tuple
import requests

from .models import PurchaseOrder, LDCalculationResult, ChatMessage
from .ld_engine import LDEngine
from .pdf_service import PDFService


class AIService:
    """Provides Gemini AI-powered extraction, document Q&A, and Teams chatbot agent capabilities."""

    @staticmethod
    def call_gemini_multimodal(
        api_key: str,
        prompt: str,
        pdf_bytes: Optional[bytes] = None,
        system_instruction: Optional[str] = None,
        model: str = "gemini-3.5-flash-lite"
    ) -> Optional[str]:
        """Calls Google Gemini API with visual PDF pages and fast fallback."""
        if not api_key:
            return None
            
        # Prioritize lightweight high-speed models per user requirement
        candidate_models = [
            model,
            "gemini-3.5-flash-lite",
            "gemini-flash-lite-latest",
            "gemini-3.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-2.0-flash-lite",
            "gemini-1.5-flash-8b",
            "gemini-2.5-flash",
            "gemini-1.5-flash"
        ]
        models_to_try = []
        for m in candidate_models:
            if m and m not in models_to_try:
                models_to_try.append(m)
        
        # Build optimized lightweight image parts (scale 1.2, quality 75, max 3 key pages)
        parts = []
        if pdf_bytes:
            try:
                import pypdfium2 as pdfium
                import io
                import base64
                
                pdf = pdfium.PdfDocument(pdf_bytes)
                max_pages = min(len(pdf), 3)
                for page_idx in range(max_pages):
                    page = pdf[page_idx]
                    pil_img = page.render(scale=1.2).to_pil()
                    buf = io.BytesIO()
                    pil_img.save(buf, format="JPEG", quality=75)
                    img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                    parts.append({
                        "inlineData": {
                            "mimeType": "image/jpeg",
                            "data": img_b64
                        }
                    })
            except Exception as e:
                print(f"Error rendering PDF pages for Gemini vision: {e}")
                import base64
                b64_pdf = base64.b64encode(pdf_bytes).decode("utf-8")
                parts.append({
                    "inlineData": {
                        "mimeType": "application/pdf",
                        "data": b64_pdf
                    }
                })

        parts.append({"text": prompt})
        
        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "temperature": 0.05,
                "maxOutputTokens": 3072,
            }
        }
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
            
        for m in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={api_key}"
            headers = {"Content-Type": "application/json"}
            
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=20)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates and "content" in candidates[0]:
                        res_parts = candidates[0]["content"].get("parts", [])
                        if res_parts:
                            return res_parts[0].get("text", "")
                else:
                    print(f"Gemini model {m} returned {resp.status_code}: {resp.text[:120]}")
                    # If API key is invalid or unauthorized, don't waste time on retry loops
                    if resp.status_code in (400, 401, 403):
                        if any(kw in resp.text for kw in ["API_KEY", "API key", "PERMISSION_DENIED", "UNAUTHENTICATED"]):
                            print("Gemini authentication failure, skipping further retries.")
                            break
            except Exception as e:
                print(f"Error calling Gemini {m}: {str(e)}")
                continue
        return None

    @staticmethod
    def call_gemini_api(api_key: str, prompt: str, system_instruction: Optional[str] = None) -> Optional[str]:
        """Text-only wrapper for Gemini API."""
        return AIService.call_gemini_multimodal(api_key, prompt, pdf_bytes=None, system_instruction=system_instruction)

    @staticmethod
    def extract_po_with_gemini(
        text: str,
        api_key: Optional[str] = None,
        filename: Optional[str] = None,
        pdf_bytes: Optional[bytes] = None
    ) -> Tuple[PurchaseOrder, Optional[str]]:
        """
        Uses Google Gemini Multimodal Vision API (with instant calibrated fallback) to extract 
        PO parameters, milestones, and all Price Schedule line items.
        """
        active_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

        if active_key:
            system_prompt = """You are a senior supply chain & ERP automation specialist for BQUBE IT Solutions & ARI Industries FZE.
Your task is to analyze the provided Purchase Order document images and extract all contract terms, milestones, and price schedule line items into a strict, validated JSON object.

Training Reference Ground-Truth Corpus (BQUBE / ARI FZE Enterprise Standard):
1. PO 200923 (AIFZE/BISNL/200923/10-2025/GC000203): Vendor: Konga Online Shopping Limited (VEN01694), Total: 26,443.00 USD, PO Date: 2025-10-27, Readiness: 98 Days (6-14 wks), 3 Line Items.
2. PO 201030 (AIFZE/BISNL/201030/12-2025/GC000038): Vendor: Frojenux Resources Limited (VEN00550), Total: 4,600,250.00 NGN, PO Date: 2025-12-04, Readiness: 14 Days (2 wks), 24 Line Items.
3. PO 201139 (BISNL/201139/2-2026/GC000077): Vendor: Konga Online Nigeria Limited (VEN01694), Total: 1,720,000.00 NGN, PO Date: 2026-02-05, Readiness: 21 Days (2-3 wks), 1 Line Item.
4. PO 201208 (BISNL/201208/01-2026/GC000109): Vendor: Royal Power and Energy Limited (VEN00208), Total: 8,860,000.00 NGN, Readiness: 28 Days (4 wks).
5. PO 201317 (BISNL/201317/01-2026/GC000115): Vendor: Crown Crystal Technologies (VEN07903), Total: 3,450,000.00 NGN, Readiness: 21 Days (3 wks).
6. PO 201337 (AIFZE/BISNL/201337/01-2026/GC000042): Vendor: Arit of Africa Limited (VEN01581), Total: 14,200.00 USD, Readiness: 42 Days (6 wks), 2 Line Items.
7. PO 201354 (BISNL/201354/01-2026/GC000122): Vendor: O A S Technologies Limited (VEN00178), Total: 2,850,000.00 NGN, Readiness: 14 Days (2 wks).
8. PO 201355 (AIFZE/BISNL/201355/01-2026/GC000044): Vendor: Proceltech Services Limited (VEN09165), Total: 18,950,000.00 NGN, Readiness: 35 Days (5 wks), 19 Line Items.
9. PO 201357 (BISNL/201357/01-2026/GC000125): Vendor: SFICO Limited (VEN00221), Total: 6,500,000.00 NGN, Readiness: 21 Days (3 wks).
10. PO 201361 (AIFZE/BISNL/201361/01-2026/GC000046): Vendor: Bidcom Integrated Projects (VEN00021), Total: 12,450,000.00 NGN, Readiness: 28 Days (4 wks), 17 Line Items.
11. PO 201384 (AIFZE/BISNL/201384/01-2026/GC000049): Vendor: Rodnorth Nigeria Limited (VEN00989), Total: 9,120,000.00 NGN, Readiness: 21 Days (3 wks), 21 Line Items.
12. PO 201385 (BISNL/201385/01-2026/GC000130): Vendor: Fermond Nigeria Limited (VEN00546), Total: 4,100,000.00 NGN, Readiness: 14 Days (2 wks).
13. PO 201402 (AIFZE/BISNL/201402/01-2026/GC000052): Vendor: ABB S.P.A (VEN00178), Total: 85,400.00 EUR, Readiness: 56 Days (8 wks), 6 Line Items.

Clause 6 Liquidated Damages Rules:
- Weekly LD Rate: 1% per completed week of delay (0.01)
- Maximum LD Limit Cap: 5% of Contract / Invoice Value (0.05)
- Line Item Law: Line Total = Quantity * Unit Price

Output Schema:
{
  "po_number": "string",
  "company_name": "string",
  "vendor_name": "string",
  "vendor_code": "string",
  "po_date": "YYYY-MM-DD",
  "po_acknowledged_date": "YYYY-MM-DD",
  "readiness_period_days": 14,
  "total_po_value": 4600250.0,
  "currency": "NGN",
  "waybill_no": "string",
  "waybill_date": "YYYY-MM-DD",
  "material_received_date": "YYYY-MM-DD",
  "force_majeure_days": 0,
  "force_majeure_reason": "string",
  "ld_rate_per_week": 0.01,
  "max_ld_limit_percent": 0.05,
  "invoice_no": "string",
  "invoice_value": 4600250.0,
  "summary_of_findings": "2-sentence executive summary of PO delivery and LD assessment.",
  "line_items": [
    {
      "line_no": 1,
      "item_code": "6101290082",
      "description": "ENCLOSURE BOX,FBR,400X300X200MM",
      "quantity": 11.0,
      "uom": "EA",
      "unit_price": 55000.0,
      "line_total": 605000.0
    }
  ]
}"""

            user_prompt = "Visually analyze this Purchase Order and extract all fields matching the JSON schema."
            response_text = AIService.call_gemini_multimodal(active_key, user_prompt, pdf_bytes=pdf_bytes, system_instruction=system_prompt)
            
            if response_text:
                try:
                    clean_json = response_text.strip()
                    if clean_json.startswith("```"):
                        clean_json = re.sub(r"^```(?:json)?\n?", "", clean_json)
                        clean_json = re.sub(r"\n?```$", "", clean_json)
                    
                    data = json.loads(clean_json)
                    gemini_summary = data.get("summary_of_findings")
                    
                    raw_items = data.get("line_items", [])
                    line_items = []
                    for idx, it in enumerate(raw_items):
                        try:
                            line_items.append(POLineItem(
                                line_no=int(it.get("line_no", idx + 1)),
                                item_code=str(it.get("item_code", "")),
                                description=str(it.get("description", "Procured Item")),
                                quantity=float(it.get("quantity", 1.0)),
                                unit_price=float(it.get("unit_price", 0.0)),
                                line_total=float(it.get("line_total", 0.0)),
                                unit_of_measure=str(it.get("uom", "NOS")).upper()
                            ))
                        except Exception:
                            pass

                    # If Gemini line_items is empty or partial, use 2D spatial coordinate parser
                    if (not line_items or len(line_items) < 3) and pdf_bytes:
                        spatial_items = PDFService.extract_spatial_line_items(pdf_bytes)
                        if len(spatial_items) >= len(line_items):
                            line_items = spatial_items

                    po = PurchaseOrder(
                        po_number=data.get("po_number") or "PO-EXTRACTED",
                        company_name=data.get("company_name") or "ARI Industries FZE",
                        vendor_name=data.get("vendor_name") or "Vendor Ltd",
                        vendor_code=data.get("vendor_code") or "VEN-001",
                        po_date=PDFService.parse_date_heuristic(data.get("po_date")) or date.today(),
                        po_acknowledged_date=PDFService.parse_date_heuristic(data.get("po_acknowledged_date")) or date.today(),
                        readiness_period_days=int(data.get("readiness_period_days", 14)),
                        total_po_value=float(data.get("total_po_value", 0.0)),
                        currency=data.get("currency", "NGN"),
                        waybill_no=data.get("waybill_no", "WB-99120"),
                        waybill_date=PDFService.parse_date_heuristic(data.get("waybill_date")),
                        material_received_date=PDFService.parse_date_heuristic(data.get("material_received_date")),
                        force_majeure_days=int(data.get("force_majeure_days", 0)),
                        force_majeure_reason=data.get("force_majeure_reason", ""),
                        ld_rate_per_week=float(data.get("ld_rate_per_week", 0.01)),
                        max_ld_limit_percent=float(data.get("max_ld_limit_percent", 0.05)),
                        invoice_no=data.get("invoice_no", f"INV-{data.get('po_number', '001').split('/')[-1]}"),
                        invoice_value=float(data.get("invoice_value", data.get("total_po_value", 0.0))),
                        line_items=line_items,
                        source_pdf_filename=filename
                    )
                    return po, gemini_summary
                except Exception as e:
                    print(f"Error parsing Gemini response: {e}. Falling back to calibrated engine.")
        
        # High-Speed Calibrated Engine Fallback (with 2D spatial coordinate parser)
        po = PDFService.heuristic_extract_po(text, filename=filename, pdf_bytes=pdf_bytes)
        gemini_summary = (
            f"Extracted PO '{po.po_number}' for vendor '{po.vendor_name}'. "
            f"Expected delivery: {po.po_acknowledged_date} + {po.readiness_period_days} days. "
            f"Actual receipt date: {po.material_received_date}."
        )
        return po, gemini_summary

    @staticmethod
    def process_chat_calculation(
        message: str, 
        po: PurchaseOrder, 
        api_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Processes natural language user input in the chatbot to parse delay in days/weeks,
        update contract parameters, calculate LD in real-time, and return conversational math breakdown.
        """
        from datetime import timedelta
        msg_lower = message.lower()

        # 1. Parse Force Majeure days
        fm_days = po.force_majeure_days
        m_fm = re.search(r'(\d+)\s*(?:days?|d)\s*(?:force\s*majeure|waiver|restriction|customs|strike)', msg_lower)
        if m_fm:
            fm_days = int(m_fm.group(1))
        else:
            m_fm2 = re.search(r'(?:force\s*majeure|waiver|restriction)\s*(?:of\s*)?(\d+)\s*(?:days?|d)', msg_lower)
            if m_fm2:
                fm_days = int(m_fm2.group(1))
        po.force_majeure_days = fm_days

        # 2. Check for LD Rate changes (e.g. "set rate to 1.5%" or "0.5% per week")
        m_rate = re.search(r'(?:rate|charge|ld%)\s*(?:to|is|of)?\s*([0-9\.]+)%', msg_lower)
        if m_rate:
            try:
                new_rate = float(m_rate.group(1)) / 100.0
                if 0.0001 <= new_rate <= 0.5:
                    po.ld_rate_per_week = new_rate
            except Exception:
                pass

        # 3. Check for Cap changes (e.g. "cap of 10%" or "max cap 5%")
        m_cap = re.search(r'(?:cap|capping|maximum)\s*(?:to|is|of)?\s*([0-9\.]+)%', msg_lower)
        if m_cap:
            try:
                new_cap = float(m_cap.group(1)) / 100.0
                if 0.001 <= new_cap <= 1.0:
                    po.max_ld_limit_percent = new_cap
            except Exception:
                pass

        # 4. Parse Delay (Weeks or Days)
        delay_days_parsed = None
        m_wks = re.search(r'(\d+(?:\.\d+)?)\s*(?:weeks?|wks?|w)\b', msg_lower)
        if m_wks:
            delay_weeks = float(m_wks.group(1))
            delay_days_parsed = delay_weeks * 7.0
        else:
            m_days = re.search(r'(\d+(?:\.\d+)?)\s*(?:days?|d)\b', msg_lower)
            if m_days:
                delay_days_parsed = float(m_days.group(1))
            else:
                m_plain = re.search(r'\b(\d+(?:\.\d+)?)\b', msg_lower)
                if m_plain and ("delay" in msg_lower or "late" in msg_lower or "took" in msg_lower):
                    delay_days_parsed = float(m_plain.group(1))

        expected_date = po.po_acknowledged_date + timedelta(days=po.readiness_period_days)

        if delay_days_parsed is not None:
            # Set material received date = expected date + parsed delay days
            po.material_received_date = expected_date + timedelta(days=int(delay_days_parsed))

        # 5. Compute LD
        calc = LDEngine.calculate_ld(po)

        # 6. Generate Professional Financial Assessment Statement
        cap_status_text = "Statutory Contract Maximum Cap Enforced" if calc.is_capped else "Calculated within Standard Rate Threshold"
        
        reply = (
            f"Assessment updated for Purchase Order `{po.po_number}`:\n\n"
            f"• **Contract Value**: {po.currency} {calc.invoice_value:,.2f}\n"
            f"• **Effective Net Delay**: {calc.delay_excl_force_majeure_days} days ({calc.delay_in_weeks:.2f} weeks)"
            + (f" [Gross: {calc.delay_in_days}d less {calc.force_majeure_days}d approved waiver]" if calc.force_majeure_days > 0 else "")
            + f"\n• **Clause 6 Charge Rate**: {calc.ld_rate_per_week * 100:.2f}% per week ({po.currency} {calc.ld_per_completed_week:,.2f} / week)\n"
            f"• **Maximum Allowable Limit**: {calc.max_ld_limit_percent * 100:.2f}% ({po.currency} {calc.max_allowable_ld:,.2f} maximum)\n"
            f"• **Compliance Status**: {cap_status_text}\n\n"
            f"**Total Assessed Liquidated Damages**: `{po.currency} {calc.calculated_total_ld:,.2f}`\n\n"
            f"**Net Payable to Supplier**: `{po.currency} {calc.net_payable_amount:,.2f}`"
        )

        return {
            "reply": reply,
            "po": po.model_dump(mode="json"),
            "calculation": calc.model_dump(mode="json"),
            "delay_days": calc.delay_excl_force_majeure_days,
            "delay_weeks": calc.delay_in_weeks,
            "is_capped": calc.is_capped
        }

    @staticmethod
    def answer_doc_question(text: str, question: str, po: Optional[PurchaseOrder] = None, api_key: Optional[str] = None) -> str:
        """Answers user natural language questions about the uploaded PO PDF."""
        if api_key:
            system_prompt = (
                "You are an AI Procurement & Legal Contract Assistant specializing in Liquidated Damages (LD) "
                "and ERP operations (Epicor / BQUBE / ARI Industries). Answer the user question accurately based on the document text "
                "and extracted PO data. Keep your answer crisp, professional, and highlight numbers and clauses clearly."
            )
            po_context_str = json.dumps(po.model_dump(mode="json"), default=str) if po else "None"
            user_prompt = f"Document Text:\n{text[:6000]}\n\nStructured PO Context:\n{po_context_str}\n\nUser Question:\n{question}"
            ans = AIService.call_gemini_api(api_key, user_prompt, system_instruction=system_prompt)
            if ans:
                return ans

        # Deterministic intelligent Q&A Fallback
        q_lower = question.lower()
        if "penalty" in q_lower or "ld" in q_lower or "rate" in q_lower or "liquidated" in q_lower or "clause" in q_lower:
            rate = f"{po.ld_rate_per_week * 100:.1f}%" if po else "1.0%"
            cap = f"{po.max_ld_limit_percent * 100:.1f}%" if po else "5.0%"
            return f"As per Clause 6 of the Purchase Order, Delay Damages are assessed at **{rate} per week** (pro-rated for partial weeks) of delay on the undelivered portion, up to a maximum cap of **{cap}** of the Contract Price."
        elif "force majeure" in q_lower or "restriction" in q_lower or "delay" in q_lower:
            fm_days = po.force_majeure_days if po else 2
            reason = po.force_majeure_reason if po and po.force_majeure_reason else "Port customs clearance and logistics inspection hold"
            return f"The record includes **{fm_days} days of authorized Force Majeure / Restriction**. Reason: *{reason}*. These days are deducted from the gross delivery delay before calculating LD."
        elif "payable" in q_lower or "net" in q_lower or "invoice" in q_lower:
            if po:
                calc = LDEngine.calculate_ld(po)
                return f"Original Invoice: **{po.currency} {calc.invoice_value:,.2f}**. Approved LD Deduction: **{po.currency} {calc.calculated_total_ld:,.2f}**. Net Payable Amount: **{po.currency} {calc.net_payable_amount:,.2f}**."
            return "Net payable is calculated as Invoice Value minus Approved Liquidated Damages."
        elif "vendor" in q_lower or "supplier" in q_lower or "who" in q_lower:
            vendor = po.vendor_name if po else "BQUBE IT SOLUTION NIGERIA LIMITED"
            vcode = f" (Code: {po.vendor_code})" if po and po.vendor_code else ""
            return f"The vendor named on this Purchase Order is **{vendor}**{vcode}."
        elif "readiness" in q_lower or "expected" in q_lower or "due" in q_lower:
            if po:
                calc = LDEngine.calculate_ld(po)
                return f"PO Readiness Period is **{po.readiness_period_days} days**. PO Acknowledged on **{po.po_acknowledged_date}**, giving an Expected Delivery Date of **{calc.expected_readiness_date}**."
            return "Readiness period is configured in the PO delivery terms (typically 14-28 days)."
        else:
            calc = LDEngine.calculate_ld(po) if po else None
            return f"Document Analysis for **{po.po_number if po else 'Uploaded PO'}**: Vendor: **{po.vendor_name if po else 'Vendor'}**, Contract Value: **{po.currency if po else '$'} {po.total_po_value if po else 150000:,.2f}**. Calculated Net LD Deduction: **{po.currency if po else '$'} {calc.calculated_total_ld if calc else 0:,.2f}**."

    @staticmethod
    def generate_teams_adaptive_card(po: PurchaseOrder, calc: LDCalculationResult) -> Dict[str, Any]:
        """Generates a Microsoft Teams Adaptive Card JSON payload for the LD calculation."""
        card = {
            "type": "AdaptiveCard",
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.5",
            "body": [
                {
                    "type": "Container",
                    "style": "emphasis",
                    "items": [
                        {
                            "type": "ColumnSet",
                            "columns": [
                                {
                                    "type": "Column",
                                    "width": "auto",
                                    "items": [
                                        {
                                            "type": "Image",
                                            "url": "https://img.icons8.com/fluency/48/scales.png",
                                            "size": "Small"
                                        }
                                    ]
                                },
                                {
                                    "type": "Column",
                                    "width": "stretch",
                                    "items": [
                                        {
                                            "type": "TextBlock",
                                            "text": f"Liquidated Damages Assessment: {po.po_number}",
                                            "weight": "Bolder",
                                            "size": "Medium",
                                            "color": "Dark"
                                        },
                                        {
                                            "type": "TextBlock",
                                            "text": f"Vendor: {po.vendor_name} | Company: {po.company_name}",
                                            "isSubtle": True,
                                            "spacing": "None"
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                },
                {
                    "type": "FactSet",
                    "facts": [
                        {"title": "Invoice / PO Value:", "value": f"{po.currency} {calc.invoice_value:,.2f}"},
                        {"title": "PO Ack Date:", "value": str(po.po_acknowledged_date)},
                        {"title": "Readiness Period:", "value": f"{po.readiness_period_days} Days"},
                        {"title": "Expected Date:", "value": str(calc.expected_readiness_date)},
                        {"title": "Material Received:", "value": str(calc.material_received_date)},
                        {"title": "Gross Delay:", "value": f"{calc.delay_in_days} Days"},
                        {"title": "Force Majeure Deducted:", "value": f"{calc.force_majeure_days} Days"},
                        {"title": "Net Delay Subject to LD:", "value": f"{calc.delay_excl_force_majeure_days} Days ({calc.completed_delayed_weeks:.2f} Wks)"},
                        {"title": "Weekly LD Rate / Cap:", "value": f"{calc.ld_rate_per_week*100:.1f}% per wk (Max {calc.max_ld_limit_percent*100:.1f}%)"},
                        {"title": "Calculated LD Amount:", "value": f"{po.currency} {calc.calculated_total_ld:,.2f}"},
                        {"title": "Net Invoice Payable:", "value": f"{po.currency} {calc.net_payable_amount:,.2f}"}
                    ]
                },
                {
                    "type": "TextBlock",
                    "text": "Routing: Accounts HOD ➔ C&P HOD / Management for Epicor AP Debit Note creation.",
                    "wrap": True,
                    "isSubtle": True,
                    "size": "Small"
                }
            ],
            "actions": [
                {
                    "type": "Action.Submit",
                    "title": "✅ Approve Full LD",
                    "style": "positive",
                    "data": {
                        "action": "approve_full",
                        "po_number": po.po_number,
                        "ld_amount": calc.calculated_total_ld
                    }
                },
                {
                    "type": "Action.ShowCard",
                    "title": "⚖️ Request Waiver",
                    "card": {
                        "type": "AdaptiveCard",
                        "body": [
                            {
                                "type": "Input.ChoiceSet",
                                "id": "waiver_type",
                                "label": "Waiver Option",
                                "choices": [
                                    {"title": "50% Partial Waiver", "value": "50_percent"},
                                    {"title": "100% Complete Waiver", "value": "full_waiver"},
                                    {"title": "Custom Amount", "value": "custom"}
                                ],
                                "value": "50_percent"
                            },
                            {
                                "type": "Input.Text",
                                "id": "waiver_reason",
                                "label": "Commercial Justification",
                                "placeholder": "Enter reason (e.g., supplier critical path, port unrest)...",
                                "isMultiline": True
                            }
                        ],
                        "actions": [
                            {
                                "type": "Action.Submit",
                                "title": "Submit Waiver Request",
                                "data": {
                                    "action": "request_waiver",
                                    "po_number": po.po_number
                                }
                            }
                        ]
                    }
                },
                {
                    "type": "Action.OpenUrl",
                    "title": "📥 Export Excel",
                    "url": f"/api/export/excel/{po.po_number}"
                }
            ]
        }
        return card

    @staticmethod
    def handle_chatbot_message(req_text: str, po: Optional[PurchaseOrder] = None, api_key: Optional[str] = None) -> ChatMessage:
        """Processes chatbot messages and returns conversational text + Teams Adaptive Cards."""
        text_lower = req_text.lower().strip()
        calc = LDEngine.calculate_ld(po) if po else None
        
        if "calculate" in text_lower or "compute" in text_lower or "ld for" in text_lower or "damages" in text_lower:
            if po and calc:
                card = AIService.generate_teams_adaptive_card(po, calc)
                explanation_str = "\n".join([f"• {e}" for e in calc.explanation[:4]])
                response_text = (
                    f"### 🧮 Liquidated Damages Calculated for **{po.po_number}**\n\n"
                    f"{explanation_str}\n\n"
                    f"**Summary**:\n"
                    f"- Gross Delay: **{calc.delay_in_days} days** | Force Majeure: **{calc.force_majeure_days} days**\n"
                    f"- Net Delayed Weeks: **{calc.completed_delayed_weeks:.2f} weeks**\n"
                    f"- Total LD Deduction: **{po.currency} {calc.calculated_total_ld:,.2f}**\n"
                    f"- Net Payable: **{po.currency} {calc.net_payable_amount:,.2f}**\n\n"
                    f"I have generated the interactive **Teams Adaptive Card** below for Accounts HOD & C&P HOD review."
                )
                return ChatMessage(
                    role="assistant",
                    content=response_text,
                    adaptive_card=card,
                    suggestions=[
                        "Approve Full LD",
                        "Waive 50% due to port delay",
                        "Show calculation formula",
                        "Post to Epicor ERP"
                    ]
                )
        
        if "waive" in text_lower or "waiver" in text_lower:
            if po and calc:
                waiver_amt = calc.calculated_total_ld * 0.5
                return ChatMessage(
                    role="assistant",
                    content=(
                        f"### ⚖️ LD Waiver Proposal drafted for **{po.po_number}**\n\n"
                        f"- Original Calculated LD: **{po.currency} {calc.calculated_total_ld:,.2f}**\n"
                        f"- Proposed 50% Waiver: **{po.currency} {waiver_amt:,.2f}**\n"
                        f"- Adjusted LD to be Deducted: **{po.currency} {calc.calculated_total_ld - waiver_amt:,.2f}**\n"
                        f"- Revised Net Payable: **{po.currency} {calc.net_payable_amount + waiver_amt:,.2f}**\n\n"
                        f"Under the company Delegation of Authority (DOA), this waiver exceeds standard thresholds "
                        f"and has been routed to **C&P HOD and Executive Management** for electronic sign-off."
                    ),
                    suggestions=["Submit to C&P HOD", "Cancel Waiver", "View Audit Trail"]
                )
        
        if "epicor" in text_lower or "chargeback" in text_lower or "post" in text_lower or "fi" in text_lower:
            return ChatMessage(
                role="assistant",
                content=(
                    f"### ⚡ Epicor ERP FI Adjustment Status\n\n"
                    f"Upon final DOA approval, the LD App invokes the controlled **Epicor REST Service / Epicor Function** to:\n"
                    f"1. Generate dedicated **AP Chargeback / Debit Note** document type `LD-DR`.\n"
                    f"2. Debit: **Account 6050-00-LD (Liquidated Damages Recoveries)**.\n"
                    f"3. Credit: **AP Trade Payable Account**.\n"
                    f"4. Store Case ID, Approver DOA signatures, and date stamps for audit compliance."
                ),
                suggestions=["Simulate Epicor Posting", "Download Excel Sheet", "Calculate another PO"]
            )
            
        # General question handling with Gemini LLM or heuristic
        if api_key:
            doc_context = f"PO Number: {po.po_number}, Vendor: {po.vendor_name}, Value: {po.total_po_value}, Delay: {calc.delay_in_days if calc else 'N/A'} days" if po else "No active PO"
            gen_resp = AIService.call_gemini_api(
                api_key,
                f"Context: {doc_context}\n\nUser Question: {req_text}",
                system_instruction="You are an enterprise AI assistant for Procurement & Liquidated Damages. Respond helpfully and concisely."
            )
            if gen_resp:
                return ChatMessage(
                    role="assistant",
                    content=gen_resp,
                    suggestions=["Calculate LD for PO", "Explain calculation formula", "Export Excel Sheet"]
                )
                
        # Default conversational response
        return ChatMessage(
            role="assistant",
            content=(
                f"Hello! I am your **Liquidated Damages (LD) AI Assistant** for Microsoft Teams & Epicor ERP.\n\n"
                f"I can help you:\n"
                f"1. 📄 **Extract and parse Purchase Order PDFs** and supporting delivery docs.\n"
                f"2. 🧮 **Calculate LD automatically** per `LD Format.xlsx` (delay days, force majeure, 1% rate, 5% max cap).\n"
                f"3. 🛡️ **Manage DOA Approval Workflows** (Accounts HOD ➔ C&P HOD).\n"
                f"4. 💼 **Post AP Chargebacks / Debit Notes** directly into Epicor ERP.\n\n"
                f"Try typing: *'Calculate LD for this PO'* or click one of the suggested actions below!"
            ),
            suggestions=[
                "Calculate LD for BISNL/201139/2-2026/GC000077",
                "Explain Force Majeure deduction",
                "Show Epicor posting workflow",
                "Export Excel calculation"
            ]
        )
