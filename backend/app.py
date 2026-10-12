"""FastAPI Application for Liquidated Damages (LD) Automation & Microsoft Teams Chatbot Pilot."""
import os
import io
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, File, UploadFile, Form, Header, HTTPException, Query, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from .models import PurchaseOrder, LDCalculationResult, ApprovalRequest, EpicorChargeback, ChatRequest, ChatMessage
from .ld_engine import LDEngine
from .pdf_service import PDFService
from .ai_service import AIService
from .approval_service import approval_hub
from .epicor_service import epicor_erp
from .export_service import ExportService

app = FastAPI(
    title="Liquidated Damages Automation & AI Teams Chatbot",
    description="Automated LD calculation, AI & OCR PO PDF extraction, Teams Adaptive Cards, and Epicor ERP FI Adjustment posting.",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_no_cache_headers(request, call_next):
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
SAMPLE_DOCS_DIR = os.path.join(BASE_DIR, "sample_docs")
TRAINING_POS_DIR = os.path.join(SAMPLE_DOCS_DIR, "training_pos")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(SAMPLE_DOCS_DIR, exist_ok=True)
os.makedirs(TRAINING_POS_DIR, exist_ok=True)


# --- Core Web & Static Routes ---

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(
                content=f.read(),
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0"
                }
            )
    return HTMLResponse(content="<h1>LD Automation Backend Running</h1><p>Frontend file not found.</p>")


# --- PO PDF Upload & AI / OCR Extraction ---

@app.post("/api/upload-po-pdf")
async def upload_po_pdf(
    file: UploadFile = File(...),
    gemini_api_key: Optional[str] = Form(None)
):
    """
    Accepts a PO PDF, visually analyzes all pages with Gemini Multimodal AI,
    extracts contract terms, milestones, and all line items, calculates LD, and saves to repository.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
    
    active_key = gemini_api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not active_key:
        raise HTTPException(
            status_code=400, 
            detail="Google Gemini API Key is required. Please click '✨ Gemini API Key' in the top bar to enter your key."
        )
    
    file_bytes = await file.read()
    save_path = os.path.join(UPLOADS_DIR, file.filename)
    with open(save_path, "wb") as f:
        f.write(file_bytes)

    # Extract text from PDF for fast fallback if cloud API is throttled
    text, page_count, is_scanned = PDFService.extract_text_from_bytes(file_bytes)

    try:
        po, summary = AIService.extract_po_with_gemini(
            text=text, 
            api_key=active_key, 
            filename=file.filename, 
            pdf_bytes=file_bytes
        )
    except Exception as e:
        po = PDFService.heuristic_extract_po(text, filename=file.filename)
        summary = f"Extracted via Calibrated Engine ({file.filename})"
    
    # Save into ERP simulator store
    epicor_erp.save_po(po)
    
    # Calculate LD strictly per LD Format.xlsx
    calc = LDEngine.calculate_ld(po)
    
    # Pre-create an initial pending approval case
    approval_req = approval_hub.create_request(
        po=po,
        calc=calc,
        justification=f"Automated calculation from PO {file.filename}"
    )

    return {
        "success": True,
        "filename": file.filename,
        "page_count": page_count,
        "is_scanned_ocr": is_scanned,
        "ocr_engine": "Gemini Multimodal AI Vision" if active_key else "Calibrated Engine",
        "extracted_po": po.model_dump(mode="json"),
        "calculation": calc.model_dump(mode="json"),
        "approval_case_id": approval_req.case_id,
        "gemini_summary": summary,
        "text_preview": text[:1000]
    }


# --- Gemini API Key Validation ---

@app.post("/api/test-gemini-key")
async def test_gemini_key(payload: Dict[str, str]):
    """Tests if a user-entered Gemini API Key is valid and active."""
    api_key = payload.get("api_key", "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="API Key is required.")
    
    test_res = AIService.call_gemini_api(api_key, "Respond with 'API Key is Active and Connected' in under 10 words.")
    if test_res:
        return {"valid": True, "message": "Google Gemini API connected successfully!", "response": test_res.strip()}
    else:
        raise HTTPException(status_code=400, detail="Invalid API Key or quota exceeded. Please check your Gemini AI Studio key.")



# --- LD Calculation Endpoints ---

@app.post("/api/calculate-ld", response_model=LDCalculationResult)
async def calculate_ld_endpoint(po: PurchaseOrder):
    """Calculates LD strictly per LD Format.xlsx."""
    epicor_erp.save_po(po)
    calc = LDEngine.calculate_ld(po)
    return calc


@app.post("/api/chat-assistant")
async def chat_assistant_endpoint(payload: Dict[str, Any]):
    """
    Handles conversational interactions: asks for delay, parses delay in days/weeks,
    adjusts rates or capping, updates calculations in real time, and explains the math.
    """
    message = payload.get("message", "").strip()
    po_data = payload.get("po")
    gemini_api_key = payload.get("gemini_api_key")
    
    if not po_data:
        raise HTTPException(status_code=400, detail="PO data is required.")
        
    po = PurchaseOrder(**po_data)
    result = AIService.process_chat_calculation(message, po, api_key=gemini_api_key)
    
    # Save updated PO to store
    epicor_erp.save_po(PurchaseOrder(**result["po"]))
    return result


@app.get("/api/po/{po_number:path}")
async def get_po_endpoint(po_number: str):
    """Retrieves PO and active calculation."""
    po = epicor_erp.get_po(po_number)
    if not po:
        raise HTTPException(status_code=404, detail=f"PO {po_number} not found.")
    calc = LDEngine.calculate_ld(po)
    return {
        "po": po.model_dump(mode="json"),
        "calculation": calc.model_dump(mode="json")
    }


# --- Training Dataset & Sample Endpoints ---

@app.get("/api/training-dataset")
async def get_training_dataset():
    """Returns all 13 real PO training packages with extracted metadata and LD assessments."""
    pos = epicor_erp.list_pos()
    results = []
    for po in pos:
        calc = LDEngine.calculate_ld(po)
        results.append({
            "po": po.model_dump(mode="json"),
            "calculation": calc.model_dump(mode="json"),
            "pdf_url": f"/api/sample-docs/training_pos/{po.source_pdf_filename}" if po.source_pdf_filename else None
        })
    return results


@app.get("/api/load-sample/{filename}")
async def load_sample_file(filename: str, gemini_api_key: Optional[str] = Query(None)):
    """Loads and parses one of the real training PDFs or sample PDFs."""
    # Check in training_pos directory first
    path = os.path.join(TRAINING_POS_DIR, filename)
    if not os.path.exists(path):
        path = os.path.join(SAMPLE_DOCS_DIR, filename)
    if not os.path.exists(path):
        path = os.path.join(UPLOADS_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"File {filename} not found.")

    with open(path, "rb") as f:
        file_bytes = f.read()

    text, page_count, is_scanned = PDFService.extract_text_from_bytes(file_bytes)
    po, summary = AIService.extract_po_with_gemini(text, api_key=gemini_api_key, filename=filename, pdf_bytes=file_bytes)
    epicor_erp.save_po(po)
    calc = LDEngine.calculate_ld(po)
    approval_req = approval_hub.create_request(po, calc, justification=f"Extracted from {filename}")

    return {
        "success": True,
        "filename": filename,
        "page_count": page_count,
        "is_scanned_ocr": is_scanned,
        "ocr_engine": "RapidOCR (ONNX Local)" if is_scanned else "Digital PDF Parser",
        "extracted_po": po.model_dump(mode="json"),
        "calculation": calc.model_dump(mode="json"),
        "approval_case_id": approval_req.case_id,
        "gemini_summary": summary,
        "text_preview": text[:1500]
    }


# --- Chatbot & Document Q&A ---

@app.post("/api/chat", response_model=ChatMessage)
async def chat_endpoint(req: ChatRequest):
    """
    Handles natural language queries from MS Teams Chatbot or Document Q&A tab.
    """
    po_obj = None
    if req.po_context:
        try:
            po_obj = PurchaseOrder(**req.po_context)
        except Exception:
            po_obj = None

    response = AIService.handle_chatbot_message(
        req_text=req.message,
        po=po_obj,
        api_key=req.gemini_api_key
    )
    return response


@app.post("/api/doc-qa")
async def doc_qa_endpoint(
    question: str = Form(...),
    po_number: Optional[str] = Form(None),
    gemini_api_key: Optional[str] = Form(None)
):
    """Direct Q&A against the active document."""
    po = epicor_erp.get_po(po_number) if po_number else None
    text_content = ""
    if po and po.source_pdf_filename:
        file_path = os.path.join(TRAINING_POS_DIR, po.source_pdf_filename)
        if not os.path.exists(file_path):
            file_path = os.path.join(UPLOADS_DIR, po.source_pdf_filename)
        if not os.path.exists(file_path):
            file_path = os.path.join(SAMPLE_DOCS_DIR, po.source_pdf_filename)
        if os.path.exists(file_path):
            text_content, _, _ = PDFService.extract_text_from_file(file_path)
            
    answer = AIService.answer_doc_question(
        text=text_content,
        question=question,
        po=po,
        api_key=gemini_api_key
    )
    return {"question": question, "answer": answer}


# --- DOA Approval Workflow Endpoints ---

@app.get("/api/approvals")
async def list_approvals():
    """Lists all active and completed LD approval workflows."""
    return [req.model_dump(mode="json") for req in approval_hub.list_requests()]


@app.post("/api/approvals/submit")
async def submit_approval(
    po_number: str = Form(...),
    waiver_type: str = Form("None"),
    waiver_amount: float = Form(0.0),
    justification: str = Form("Standard assessment")
):
    """Submits a new LD approval case."""
    po = epicor_erp.get_po(po_number)
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    calc = LDEngine.calculate_ld(po)
    req = approval_hub.create_request(po, calc, waiver_type, waiver_amount, justification)
    return req.model_dump(mode="json")


@app.post("/api/approvals/{case_id}/tier1-accounts")
async def approve_tier1(
    case_id: str,
    approver: str = Form("O. Adebayo (Accounts HOD)"),
    comments: str = Form("Verified delay calculation & delivery dates.")
):
    """Tier 1 Accounts HOD review."""
    req = approval_hub.approve_tier_1_accounts(case_id, approver_name=approver, comments=comments)
    if not req:
        raise HTTPException(status_code=404, detail="Approval case not found")
    return req.model_dump(mode="json")


@app.post("/api/approvals/{case_id}/tier2-cnp")
async def approve_tier2(
    case_id: str,
    decision: str = Form("Approve Full"),
    approver: str = Form("C. Okafor (C&P HOD)"),
    waiver_amount: Optional[float] = Form(None),
    comments: str = Form("Authorized per DOA procurement limit.")
):
    """Tier 2 C&P HOD / Management review."""
    req = approval_hub.approve_tier_2_cnp(
        case_id=case_id,
        approver_name=approver,
        waiver_decision=decision,
        waiver_amount=waiver_amount,
        comments=comments
    )
    if not req:
        raise HTTPException(status_code=404, detail="Approval case not found")
        
    # Auto-trigger Epicor AP Chargeback generation on final approval
    if req.status in ["Approved", "Partially Waived", "Waived"]:
        chargeback = epicor_erp.post_ap_chargeback(req, user=approver)
        return {
            "approval": req.model_dump(mode="json"),
            "epicor_chargeback": chargeback.model_dump(mode="json")
        }
        
    return {"approval": req.model_dump(mode="json")}


# --- Epicor ERP Integration Simulator Endpoints ---

@app.get("/api/epicor/pos")
async def get_epicor_pos():
    """Returns open purchase orders in Epicor ERP."""
    pos = epicor_erp.list_pos()
    results = []
    for po in pos:
        calc = LDEngine.calculate_ld(po)
        results.append({
            "po": po.model_dump(mode="json"),
            "calculation": calc.model_dump(mode="json")
        })
    return results


@app.get("/api/epicor/chargebacks")
async def get_epicor_chargebacks():
    """Lists posted AP Chargebacks (Debit Notes) in Epicor."""
    return [cb.model_dump(mode="json") for cb in epicor_erp.list_chargebacks()]


@app.post("/api/epicor/post-chargeback")
async def manual_post_chargeback(case_id: str = Form(...)):
    """Manually triggers Epicor AP Chargeback posting for an approved case."""
    req = approval_hub.get_request(case_id)
    if not req:
        raise HTTPException(status_code=404, detail="Case not found")
    cb = epicor_erp.post_ap_chargeback(req)
    return cb.model_dump(mode="json")


# --- Document Exports (Excel & PDF) ---

@app.post("/api/export-excel")
async def export_excel_post(payload: Dict[str, Any]):
    """Generates and downloads the exact Excel sheet matching LD Format.xlsx for the provided PO."""
    po_data = payload.get("po", payload)
    po = PurchaseOrder(**po_data)
    excel_bytes = ExportService.generate_excel_bytes(po)
    clean_num = po.po_number.replace("/", "_").replace("\\", "_")
    filename = f"LD_Calculation_{clean_num}.xlsx"
    
    return StreamingResponse(
        io.BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.post("/api/export-pdf")
async def export_pdf_post(payload: Dict[str, Any]):
    """Generates and downloads the official PDF assessment and IAF Annexure for the provided PO."""
    po_data = payload.get("po", payload)
    po = PurchaseOrder(**po_data)
    pdf_bytes = ExportService.generate_pdf_report_bytes(po)
    clean_num = po.po_number.replace("/", "_").replace("\\", "_")
    filename = f"LD_Report_{clean_num}.pdf"
    
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.get("/api/export/excel/{po_number:path}")
async def export_excel(po_number: str):
    """Generates and downloads the exact Excel sheet matching LD Format.xlsx."""
    po = epicor_erp.get_po(po_number)
    if not po:
        raise HTTPException(status_code=404, detail=f"PO {po_number} not found.")
    
    excel_bytes = ExportService.generate_excel_bytes(po)
    clean_num = po.po_number.replace("/", "_").replace("\\", "_")
    filename = f"LD_Calculation_{clean_num}.xlsx"
    
    return StreamingResponse(
        io.BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.get("/api/export/pdf/{po_number:path}")
async def export_pdf(po_number: str):
    """Generates and downloads the official PDF assessment and IAF Annexure."""
    po = epicor_erp.get_po(po_number)
    if not po:
        raise HTTPException(status_code=404, detail=f"PO {po_number} not found.")
    
    approvals = [a for a in approval_hub.list_requests() if a.po_number == po_number]
    active_approval = approvals[-1] if approvals else None
    
    pdf_bytes = ExportService.generate_pdf_report_bytes(po, approval=active_approval)
    clean_num = po.po_number.replace("/", "_").replace("\\", "_")
    filename = f"LD_Report_{clean_num}.pdf"
    
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


# --- Sample & Training Files Streaming ---

@app.get("/api/sample-docs/training_pos/{filename}")
async def get_training_pdf(filename: str):
    """Streams a training PO PDF file."""
    path = os.path.join(TRAINING_POS_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Training file not found")
    with open(path, "rb") as f:
        content = f.read()
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'}
    )


@app.get("/api/sample-docs/{filename}")
async def get_sample_doc(filename: str):
    """Streams a sample PO PDF file."""
    path = os.path.join(SAMPLE_DOCS_DIR, filename)
    if not os.path.exists(path):
        path = os.path.join(TRAINING_POS_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Sample file not found")
    with open(path, "rb") as f:
        content = f.read()
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'}
    )


# Mount static files directory for CSS/JS
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


if __name__ == "__main__":
    uvicorn.run("backend.app:app", host="0.0.0.0", port=8000, reload=True)
