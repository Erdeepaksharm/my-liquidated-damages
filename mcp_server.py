"""
MCP (Model Context Protocol) Server for the Liquidated Damages Automation System.

Exposes the LD system's core capabilities as MCP tools and resources:
- Calculate liquidated damages from PO parameters
- Upload and extract PO data from PDFs
- Manage approval workflows
- Generate Excel/PDF exports
- Query PO data and training datasets
- Chat-based LD assistant

Usage:
    python mcp_server.py                  # stdio transport (default)
    python mcp_server.py --sse            # SSE transport on port 8080
    python mcp_server.py --sse --port 9000  # SSE on custom port
"""

import sys
import os
import json
import base64
import asyncio
import argparse
from datetime import date, datetime
from typing import Optional, Any

# Ensure the parent package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
    Resource,
    ResourceTemplate,
)

# --- Import backend services ---
from backend.models import PurchaseOrder, POLineItem
from backend.ld_engine import LDEngine
from backend.pdf_service import PDFService
from backend.ai_service import AIService
from backend.approval_service import ApprovalService
from backend.epicor_service import EpicorERPService
from backend.export_service import ExportService

# --- Service Singletons ---
approval_hub = ApprovalService()
epicor_erp = EpicorERPService()

# --- MCP Server Setup ---
server = Server("liquidated-damages-mcp")


# ============================================================
# TOOLS
# ============================================================

@server.list_tools()
async def list_tools() -> list[Tool]:
    """Advertise all available LD tools."""
    return [
        Tool(
            name="calculate_ld",
            description=(
                "Calculate Liquidated Damages for a Purchase Order. "
                "Takes PO parameters (dates, values, delay info) and returns "
                "the full LD calculation with step-by-step formula explanation. "
                "Uses the formula: LD = min(delay_weeks * rate * invoice_value, cap% * invoice_value). "
                "Default rate is 1%/week, default cap is 5%."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "po_number": {"type": "string", "description": "Purchase Order number"},
                    "vendor_name": {"type": "string", "description": "Vendor/supplier name"},
                    "company_name": {"type": "string", "description": "Buyer company name", "default": "BQUBE IT SOLUTION NIGERIA LIMITED"},
                    "po_date": {"type": "string", "description": "PO issue date (YYYY-MM-DD)"},
                    "po_acknowledged_date": {"type": "string", "description": "Date vendor acknowledged the PO (YYYY-MM-DD)"},
                    "readiness_period_days": {"type": "integer", "description": "Contract readiness/delivery period in days", "default": 60},
                    "total_po_value": {"type": "number", "description": "Total purchase order value"},
                    "currency": {"type": "string", "description": "Currency code (USD, NGN, EUR, GBP)", "default": "USD"},
                    "material_received_date": {"type": "string", "description": "Actual material receipt date (YYYY-MM-DD). If omitted, uses today."},
                    "force_majeure_days": {"type": "integer", "description": "Days to deduct for force majeure/restrictions", "default": 0},
                    "invoice_value": {"type": "number", "description": "Invoice value (defaults to total_po_value if omitted)"},
                    "ld_rate_per_week": {"type": "number", "description": "LD rate per week as decimal (0.01 = 1%)", "default": 0.01},
                    "max_ld_limit_percent": {"type": "number", "description": "Maximum LD cap as decimal (0.05 = 5%)", "default": 0.05},
                    "rounding_mode": {"type": "string", "enum": ["exact", "completed"], "description": "Week rounding: 'exact' (fractional) or 'completed' (floor)", "default": "exact"},
                },
                "required": ["po_number", "vendor_name", "po_date", "po_acknowledged_date", "total_po_value"],
            },
        ),
        Tool(
            name="extract_po_from_pdf",
            description=(
                "Extract Purchase Order data from a PDF file. "
                "Uses Gemini AI multimodal vision (if API key provided) or local OCR/heuristic engine. "
                "Returns structured PO data with line items, contract terms, and milestones."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pdf_path": {"type": "string", "description": "Absolute file path to the PO PDF"},
                    "gemini_api_key": {"type": "string", "description": "Google Gemini API key (optional, enables AI extraction)"},
                },
                "required": ["pdf_path"],
            },
        ),
        Tool(
            name="extract_po_from_text",
            description=(
                "Extract Purchase Order data from raw text content (e.g., pasted or pre-extracted text). "
                "Uses heuristic pattern matching to identify PO number, vendor, dates, values, and line items."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Raw text content from a PO document"},
                    "filename": {"type": "string", "description": "Original filename (helps with PO number detection)"},
                },
                "required": ["text"],
            },
        ),
        Tool(
            name="list_purchase_orders",
            description="List all purchase orders currently stored in the system.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="get_purchase_order",
            description="Retrieve a specific purchase order and its LD calculation by PO number.",
            inputSchema={
                "type": "object",
                "properties": {
                    "po_number": {"type": "string", "description": "Full or partial PO number to search for"},
                },
                "required": ["po_number"],
            },
        ),
        Tool(
            name="create_approval_request",
            description=(
                "Create a new LD approval case for a purchase order. "
                "Initiates the 2-tier DOA workflow: Tier 1 (Accounts HOD) → Tier 2 (C&P HOD)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "po_number": {"type": "string", "description": "PO number to create approval for"},
                    "justification": {"type": "string", "description": "Justification text for the LD assessment", "default": "Standard contractual LD assessment"},
                    "waiver_type": {"type": "string", "enum": ["None", "Partial", "Full"], "description": "Waiver type", "default": "None"},
                    "waiver_amount": {"type": "number", "description": "Waiver amount to deduct from LD", "default": 0.0},
                },
                "required": ["po_number"],
            },
        ),
        Tool(
            name="approve_tier1",
            description="Approve an LD case at Tier 1 (Accounts HOD verification).",
            inputSchema={
                "type": "object",
                "properties": {
                    "case_id": {"type": "string", "description": "Approval case ID"},
                    "approver_name": {"type": "string", "description": "Approver's name", "default": "O. Adebayo (Accounts HOD)"},
                    "comments": {"type": "string", "description": "Approval comments", "default": "Verified delay calculation & delivery dates."},
                },
                "required": ["case_id"],
            },
        ),
        Tool(
            name="approve_tier2",
            description="Approve an LD case at Tier 2 (C&P HOD / Management). This is the final approval step.",
            inputSchema={
                "type": "object",
                "properties": {
                    "case_id": {"type": "string", "description": "Approval case ID"},
                    "decision": {"type": "string", "enum": ["Approve Full", "Approve Partial Waiver", "Approve Full Waiver", "Reject"], "description": "Approval decision", "default": "Approve Full"},
                    "approver_name": {"type": "string", "description": "Approver's name", "default": "C. Okafor (C&P HOD)"},
                    "waiver_amount": {"type": "number", "description": "Waiver amount (for partial waiver)"},
                    "comments": {"type": "string", "description": "Approval comments", "default": "Authorized per DOA procurement limit."},
                },
                "required": ["case_id"],
            },
        ),
        Tool(
            name="list_approvals",
            description="List all LD approval cases (pending, approved, waived, rejected).",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="post_epicor_chargeback",
            description=(
                "Post an AP Chargeback / Debit Note to Epicor ERP for an approved LD case. "
                "Creates document type LD-DR debiting GL account 6050-00-LD."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "case_id": {"type": "string", "description": "Approved case ID to post"},
                },
                "required": ["case_id"],
            },
        ),
        Tool(
            name="list_chargebacks",
            description="List all posted Epicor AP Chargebacks / Debit Notes.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="export_excel",
            description=(
                "Generate an Excel file matching the LD Format.xlsx template for a PO. "
                "Returns the file as base64-encoded content."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "po_number": {"type": "string", "description": "PO number to generate Excel for"},
                },
                "required": ["po_number"],
            },
        ),
        Tool(
            name="export_pdf_report",
            description=(
                "Generate an official PDF LD Assessment & IAF Annexure report for a PO. "
                "Returns the file as base64-encoded content."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "po_number": {"type": "string", "description": "PO number to generate PDF for"},
                },
                "required": ["po_number"],
            },
        ),
        Tool(
            name="chat_ld_assistant",
            description=(
                "Interactive LD calculation assistant. Accepts natural language messages like "
                "'The delivery was 3 weeks late' or 'Set force majeure to 5 days' and "
                "updates the LD calculation in real-time. Understands delay in days/weeks, "
                "rate changes, cap adjustments, and force majeure."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Natural language message about the PO delay/calculation"},
                    "po_number": {"type": "string", "description": "PO number to apply the chat action to"},
                    "gemini_api_key": {"type": "string", "description": "Gemini API key for AI-powered responses"},
                },
                "required": ["message", "po_number"],
            },
        ),
        Tool(
            name="document_qa",
            description=(
                "Ask a question about a specific PO document. "
                "Answers questions about penalty rates, force majeure, vendor info, "
                "readiness periods, net payable amounts, and contract clauses."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "Natural language question about the PO"},
                    "po_number": {"type": "string", "description": "PO number to query against"},
                    "gemini_api_key": {"type": "string", "description": "Gemini API key for AI-powered answers"},
                },
                "required": ["question"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""

    def _serialize(obj: Any) -> str:
        """Serialize pydantic models and dates to JSON string."""
        if hasattr(obj, "model_dump"):
            return json.dumps(obj.model_dump(mode="json"), indent=2, default=str)
        return json.dumps(obj, indent=2, default=str)

    try:
        # ── calculate_ld ──
        if name == "calculate_ld":
            po = PurchaseOrder(
                po_number=arguments["po_number"],
                vendor_name=arguments["vendor_name"],
                company_name=arguments.get("company_name", "BQUBE IT SOLUTION NIGERIA LIMITED"),
                po_date=date.fromisoformat(arguments["po_date"]),
                po_acknowledged_date=date.fromisoformat(arguments["po_acknowledged_date"]),
                readiness_period_days=arguments.get("readiness_period_days", 60),
                total_po_value=arguments["total_po_value"],
                currency=arguments.get("currency", "USD"),
                material_received_date=date.fromisoformat(arguments["material_received_date"]) if arguments.get("material_received_date") else None,
                force_majeure_days=arguments.get("force_majeure_days", 0),
                invoice_value=arguments.get("invoice_value"),
                ld_rate_per_week=arguments.get("ld_rate_per_week", 0.01),
                max_ld_limit_percent=arguments.get("max_ld_limit_percent", 0.05),
                rounding_mode=arguments.get("rounding_mode", "exact"),
            )
            epicor_erp.save_po(po)
            calc = LDEngine.calculate_ld(po)
            return [TextContent(type="text", text=_serialize(calc))]

        # ── extract_po_from_pdf ──
        elif name == "extract_po_from_pdf":
            pdf_path = arguments["pdf_path"]
            if not os.path.exists(pdf_path):
                return [TextContent(type="text", text=json.dumps({"error": f"File not found: {pdf_path}"}))]

            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()

            text, page_count, is_scanned = PDFService.extract_text_from_bytes(pdf_bytes)
            api_key = arguments.get("gemini_api_key") or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

            try:
                po, summary = AIService.extract_po_with_gemini(
                    text=text, api_key=api_key,
                    filename=os.path.basename(pdf_path), pdf_bytes=pdf_bytes
                )
            except Exception:
                po = PDFService.heuristic_extract_po(text, filename=os.path.basename(pdf_path), pdf_bytes=pdf_bytes)
                summary = f"Extracted via heuristic engine from {os.path.basename(pdf_path)}"

            epicor_erp.save_po(po)
            calc = LDEngine.calculate_ld(po)

            result = {
                "po": po.model_dump(mode="json"),
                "calculation": calc.model_dump(mode="json"),
                "page_count": page_count,
                "is_scanned": is_scanned,
                "extraction_method": "Gemini AI" if api_key else "Heuristic Engine",
                "summary": summary,
            }
            return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

        # ── extract_po_from_text ──
        elif name == "extract_po_from_text":
            text = arguments["text"]
            filename = arguments.get("filename", "pasted_text.pdf")
            po = PDFService.heuristic_extract_po(text, filename=filename)
            epicor_erp.save_po(po)
            calc = LDEngine.calculate_ld(po)
            result = {
                "po": po.model_dump(mode="json"),
                "calculation": calc.model_dump(mode="json"),
            }
            return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

        # ── list_purchase_orders ──
        elif name == "list_purchase_orders":
            pos = epicor_erp.list_pos()
            results = []
            for po in pos:
                calc = LDEngine.calculate_ld(po)
                results.append({
                    "po_number": po.po_number,
                    "vendor_name": po.vendor_name,
                    "total_po_value": po.total_po_value,
                    "currency": po.currency,
                    "calculated_ld": calc.calculated_total_ld,
                    "net_payable": calc.net_payable_amount,
                    "delay_days": calc.delay_excl_force_majeure_days,
                    "status": po.status,
                })
            return [TextContent(type="text", text=json.dumps(results, indent=2, default=str))]

        # ── get_purchase_order ──
        elif name == "get_purchase_order":
            po = epicor_erp.get_po(arguments["po_number"])
            if not po:
                return [TextContent(type="text", text=json.dumps({"error": f"PO '{arguments['po_number']}' not found"}))]
            calc = LDEngine.calculate_ld(po)
            result = {
                "po": po.model_dump(mode="json"),
                "calculation": calc.model_dump(mode="json"),
            }
            return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

        # ── create_approval_request ──
        elif name == "create_approval_request":
            po = epicor_erp.get_po(arguments["po_number"])
            if not po:
                return [TextContent(type="text", text=json.dumps({"error": f"PO '{arguments['po_number']}' not found. Upload or calculate first."}))]
            calc = LDEngine.calculate_ld(po)
            req = approval_hub.create_request(
                po=po, calc=calc,
                waiver_type=arguments.get("waiver_type", "None"),
                waiver_amount=arguments.get("waiver_amount", 0.0),
                justification=arguments.get("justification", "Standard contractual LD assessment"),
            )
            return [TextContent(type="text", text=_serialize(req))]

        # ── approve_tier1 ──
        elif name == "approve_tier1":
            req = approval_hub.approve_tier_1_accounts(
                case_id=arguments["case_id"],
                approver_name=arguments.get("approver_name", "O. Adebayo (Accounts HOD)"),
                comments=arguments.get("comments", "Verified delay calculation & delivery dates."),
            )
            if not req:
                return [TextContent(type="text", text=json.dumps({"error": f"Case '{arguments['case_id']}' not found"}))]
            return [TextContent(type="text", text=_serialize(req))]

        # ── approve_tier2 ──
        elif name == "approve_tier2":
            req = approval_hub.approve_tier_2_cnp(
                case_id=arguments["case_id"],
                approver_name=arguments.get("approver_name", "C. Okafor (C&P HOD)"),
                waiver_decision=arguments.get("decision", "Approve Full"),
                waiver_amount=arguments.get("waiver_amount"),
                comments=arguments.get("comments", "Authorized per DOA procurement limit."),
            )
            if not req:
                return [TextContent(type="text", text=json.dumps({"error": f"Case '{arguments['case_id']}' not found"}))]
            return [TextContent(type="text", text=_serialize(req))]

        # ── list_approvals ──
        elif name == "list_approvals":
            reqs = approval_hub.list_requests()
            results = [r.model_dump(mode="json") for r in reqs]
            return [TextContent(type="text", text=json.dumps(results, indent=2, default=str))]

        # ── post_epicor_chargeback ──
        elif name == "post_epicor_chargeback":
            req = approval_hub.get_request(arguments["case_id"])
            if not req:
                return [TextContent(type="text", text=json.dumps({"error": f"Case '{arguments['case_id']}' not found"}))]
            po = epicor_erp.get_po(req.po_number)
            if not po:
                return [TextContent(type="text", text=json.dumps({"error": f"PO '{req.po_number}' not found in ERP"}))]
            calc = LDEngine.calculate_ld(po)
            # The epicor_service expects an object with .po and .calculation attributes
            # Create a simple namespace for it
            class ApprovalWithPO:
                pass
            arwp = ApprovalWithPO()
            arwp.po = po
            arwp.calculation = calc
            arwp.po_number = req.po_number
            cb = epicor_erp.post_ap_chargeback(arwp)
            return [TextContent(type="text", text=_serialize(cb))]

        # ── list_chargebacks ──
        elif name == "list_chargebacks":
            cbs = epicor_erp.get_chargebacks()
            results = [cb.model_dump(mode="json") for cb in cbs]
            return [TextContent(type="text", text=json.dumps(results, indent=2, default=str))]

        # ── export_excel ──
        elif name == "export_excel":
            po = epicor_erp.get_po(arguments["po_number"])
            if not po:
                return [TextContent(type="text", text=json.dumps({"error": f"PO '{arguments['po_number']}' not found"}))]
            excel_bytes = ExportService.generate_excel_bytes(po)
            clean_num = po.po_number.replace("/", "_").replace("\\", "_")
            filename = f"LD_Calculation_{clean_num}.xlsx"
            output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "exports")
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, filename)
            with open(output_path, "wb") as f:
                f.write(excel_bytes)
            return [TextContent(type="text", text=json.dumps({
                "success": True,
                "filename": filename,
                "path": output_path,
                "size_bytes": len(excel_bytes),
                "base64": base64.b64encode(excel_bytes).decode("utf-8")[:200] + "... (truncated)",
            }, indent=2))]

        # ── export_pdf_report ──
        elif name == "export_pdf_report":
            po = epicor_erp.get_po(arguments["po_number"])
            if not po:
                return [TextContent(type="text", text=json.dumps({"error": f"PO '{arguments['po_number']}' not found"}))]
            approvals = [a for a in approval_hub.list_requests() if a.po_number == po.po_number]
            active_approval = approvals[-1] if approvals else None
            pdf_bytes = ExportService.generate_pdf_report_bytes(po, approval=active_approval)
            clean_num = po.po_number.replace("/", "_").replace("\\", "_")
            filename = f"LD_Report_{clean_num}.pdf"
            output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "exports")
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, filename)
            with open(output_path, "wb") as f:
                f.write(pdf_bytes)
            return [TextContent(type="text", text=json.dumps({
                "success": True,
                "filename": filename,
                "path": output_path,
                "size_bytes": len(pdf_bytes),
            }, indent=2))]

        # ── chat_ld_assistant ──
        elif name == "chat_ld_assistant":
            po = epicor_erp.get_po(arguments["po_number"])
            if not po:
                return [TextContent(type="text", text=json.dumps({"error": f"PO '{arguments['po_number']}' not found. Calculate or extract first."}))]
            result = AIService.process_chat_calculation(
                message=arguments["message"],
                po=po,
                api_key=arguments.get("gemini_api_key"),
            )
            # Update saved PO
            epicor_erp.save_po(PurchaseOrder(**result["po"]))
            return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

        # ── document_qa ──
        elif name == "document_qa":
            po = None
            if arguments.get("po_number"):
                po = epicor_erp.get_po(arguments["po_number"])
            text_content = ""
            if po and po.source_pdf_filename:
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                for subdir in ["sample_docs/training_pos", "uploads", "sample_docs"]:
                    fpath = os.path.join(base_dir, subdir, po.source_pdf_filename)
                    if os.path.exists(fpath):
                        text_content, _, _ = PDFService.extract_text_from_file(fpath)
                        break
            answer = AIService.answer_doc_question(
                text=text_content,
                question=arguments["question"],
                po=po,
                api_key=arguments.get("gemini_api_key"),
            )
            return [TextContent(type="text", text=json.dumps({"question": arguments["question"], "answer": answer}, indent=2))]

        else:
            return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}, indent=2))]


# ============================================================
# RESOURCES
# ============================================================

@server.list_resources()
async def list_resources() -> list[Resource]:
    """Expose key system resources."""
    return [
        Resource(
            uri="ld://formula",
            name="LD Calculation Formula",
            description="The official Liquidated Damages calculation formula and rules.",
            mimeType="text/plain",
        ),
        Resource(
            uri="ld://rates",
            name="Default LD Rates & Caps",
            description="Default LD rates, caps, and contract terms.",
            mimeType="application/json",
        ),
    ]


@server.read_resource()
async def read_resource(uri: str) -> str:
    """Read resource content."""
    if uri == "ld://formula":
        return (
            "LIQUIDATED DAMAGES CALCULATION FORMULA (per LD Format.xlsx)\n"
            "=============================================================\n\n"
            "1. Expected Readiness Date = PO Acknowledged Date + Readiness Period (days)\n"
            "2. Gross Delay (days) = Material Received Date - Expected Readiness Date\n"
            "3. Net Delay (days) = max(0, Gross Delay - Force Majeure Days)\n"
            "4. Delay in Weeks = Net Delay / 7.0\n"
            "5. LD Per Week = Invoice Value × LD Rate (default 1%)\n"
            "6. Total LD = min(Delay Weeks × LD Per Week, Max Cap% × Invoice Value)\n"
            "   - Default cap: 5% of Invoice/Contract Value\n"
            "7. Net Payable = Invoice Value - Total LD\n\n"
            "Rounding Modes:\n"
            "  - 'exact': fractional weeks (default)\n"
            "  - 'completed': floor to completed weeks only\n"
        )
    elif uri == "ld://rates":
        return json.dumps({
            "ld_rate_per_week": 0.01,
            "ld_rate_description": "1% of invoice value per week of delay",
            "max_ld_limit_percent": 0.05,
            "max_ld_limit_description": "5% of contract/invoice value maximum cap",
            "force_majeure_default": 0,
            "rounding_mode_default": "exact",
            "supported_currencies": ["USD", "NGN", "EUR", "GBP"],
            "gl_account": "6050-00-LD",
            "document_type": "LD-DR (Liquidated Damages Debit Note)",
        }, indent=2)
    return json.dumps({"error": f"Unknown resource: {uri}"})


# ============================================================
# MAIN
# ============================================================

async def run_stdio():
    """Run the MCP server over stdio transport."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


async def run_sse(port: int = 8080):
    """Run the MCP server over SSE transport."""
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Route, Mount
    import uvicorn

    sse = SseServerTransport("/messages/")

    async def handle_sse(request):
        async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
            await server.run(streams[0], streams[1], server.create_initialization_options())

    app = Starlette(
        debug=True,
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ],
    )

    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    uv_server = uvicorn.Server(config)
    await uv_server.serve()


def main():
    parser = argparse.ArgumentParser(description="Liquidated Damages MCP Server")
    parser.add_argument("--sse", action="store_true", help="Use SSE transport instead of stdio")
    parser.add_argument("--port", type=int, default=8080, help="Port for SSE transport (default: 8080)")
    args = parser.parse_args()

    if args.sse:
        asyncio.run(run_sse(args.port))
    else:
        asyncio.run(run_stdio())


if __name__ == "__main__":
    main()
