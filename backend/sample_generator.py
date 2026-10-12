"""Generates realistic sample Purchase Order and Invoice PDFs for testing and business demo."""
import os
from datetime import date
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle


def generate_sample_po_pdf(output_path: str, po_number: str, vendor: str, company: str, amount: float, currency: str = "USD", readiness_days: int = 60, ack_date: str = "2026-01-02", receipt_date: str = "2026-03-10", fm_days: int = 2):
    """Creates a realistic formal Purchase Order PDF."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    doc = SimpleDocTemplate(output_path, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=16, leading=20, textColor=colors.HexColor('#0F172A'))
    sub_style = ParagraphStyle('Sub', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#475569'), spaceAfter=10)
    body_bold = ParagraphStyle('BodyB', parent=styles['Normal'], fontSize=9, fontName='Helvetica-Bold', leading=13)
    body_style = ParagraphStyle('BodyN', parent=styles['Normal'], fontSize=9, leading=13)
    clause_title = ParagraphStyle('ClauseT', parent=styles['Heading3'], fontSize=10, textColor=colors.HexColor('#1E293B'), spaceBefore=8, spaceAfter=4)
    clause_body = ParagraphStyle('ClauseB', parent=styles['Normal'], fontSize=8.5, textColor=colors.HexColor('#334155'), leading=12)

    story = []

    # Company Header
    story.append(Paragraph(f"<b>{company.upper()}</b>", title_style))
    story.append(Paragraph("Commercial Procurement & Supply Chain Operations | Epicor Kinetic ERP Verified", sub_style))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#0284C7'), spaceAfter=12))

    # PO Metadata Header Table
    meta_data = [
        [Paragraph("<b>PURCHASE ORDER NUMBER:</b>", body_bold), Paragraph(f"<b>{po_number}</b>", body_bold), Paragraph("<b>PO SENT DATE:</b>", body_bold), Paragraph(f"{ack_date}", body_style)],
        [Paragraph("<b>VENDOR / CONTRACTOR:</b>", body_bold), Paragraph(f"{vendor}", body_style), Paragraph("<b>PO ACKNOWLEDGED DATE:</b>", body_bold), Paragraph(f"<b>{ack_date}</b>", body_bold)],
        [Paragraph("<b>DELIVERY SITE:</b>", body_bold), Paragraph("Port Harcourt Logistics Base", body_style), Paragraph("<b>READINESS PERIOD:</b>", body_bold), Paragraph(f"<b>{readiness_days} Days</b>", body_bold)],
        [Paragraph("<b>INVOICE REFERENCE:</b>", body_bold), Paragraph(f"INV-{po_number.replace('PO-', '')}-01", body_style), Paragraph("<b>ACTUAL RECEIPT / JCC:</b>", body_bold), Paragraph(f"<b>{receipt_date}</b>", body_bold)],
        [Paragraph("<b>FORCE MAJEURE CLAIMED:</b>", body_bold), Paragraph(f"<b>{fm_days} Days</b> (Customs Backlog)", body_style), Paragraph("<b>TOTAL PO VALUE:</b>", body_bold), Paragraph(f"<b>{currency} {amount:,.2f}</b>", body_bold)]
    ]

    t_meta = Table(meta_data, colWidths=[140, 160, 130, 110])
    t_meta.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_meta)
    story.append(Spacer(1, 10))

    # Line Items Table
    story.append(Paragraph("<b>Order Bill of Quantities (BOQ) & Deliverables</b>", clause_title))
    items_data = [
        [Paragraph("<b>Item</b>", body_bold), Paragraph("<b>Description</b>", body_bold), Paragraph("<b>Qty</b>", body_bold), Paragraph("<b>Unit Price</b>", body_bold), Paragraph("<b>Total</b>", body_bold)],
        [Paragraph("1", body_style), Paragraph("High-Pressure API 6D Forged Steel Ball Valves 6-inch 1500#", body_style), Paragraph("4 EA", body_style), Paragraph(f"{currency} {amount*0.6/4:,.2f}", body_style), Paragraph(f"{currency} {amount*0.6:,.2f}", body_style)],
        [Paragraph("2", body_style), Paragraph("Emergency Shutdown (ESD) Actuator & Pneumatic Control Panel", body_style), Paragraph("4 SET", body_style), Paragraph(f"{currency} {amount*0.4/4:,.2f}", body_style), Paragraph(f"{currency} {amount*0.4:,.2f}", body_style)],
        [Paragraph("", body_style), Paragraph("<b>TOTAL CONTRACT VALUE</b>", body_bold), Paragraph("", body_style), Paragraph("", body_style), Paragraph(f"<b>{currency} {amount:,.2f}</b>", body_bold)]
    ]
    t_items = Table(items_data, colWidths=[35, 260, 55, 95, 95])
    t_items.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E2E8F0')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_items)
    story.append(Spacer(1, 10))

    # Contract Clauses & LD Terms
    story.append(Paragraph("<b>Contractual Terms & Conditions</b>", clause_title))
    
    story.append(Paragraph("<b>Section 4.1 - Delivery & Readiness Clock:</b> The Supplier covenants that all equipment specified herein shall be completely fabricated, tested, and ready for dispatch within <b>" + str(readiness_days) + " calendar days</b> following PO Acknowledgment date (" + ack_date + ").", clause_body))
    story.append(Spacer(1, 4))
    
    story.append(Paragraph("<b>Section 4.2 - Liquidated Damages (LD) Clause:</b> If the Supplier fails to deliver the equipment within the stipulated readiness period, Liquidated Damages shall accrue at the rate of <b>1.0% (one percent) per completed week of delay</b> assessed against the total PO / Invoice Value, up to an aggregate maximum ceiling of <b>5.0% (five percent)</b> of the contract price.", clause_body))
    story.append(Spacer(1, 4))

    story.append(Paragraph("<b>Section 4.3 - Force Majeure & Excusable Delays:</b> In the event of documented sovereign port congestion, customs clearance restrictions, or state security directives, authorized days (recorded as <b>" + str(fm_days) + " days</b> for this shipment) shall be deducted from gross delay prior to LD computation.", clause_body))
    story.append(Spacer(1, 4))

    story.append(Paragraph("<b>Section 4.4 - ERP Financial Settlement (Epicor Integration):</b> All approved LD deductions shall be executed via an automated <b>AP Chargeback / Debit Note (Doc Type: LD-DR)</b> posted against Account 6050-00-LD prior to final invoice payment disbursement.", clause_body))

    doc.build(story)


def create_all_samples(base_dir: str = "/Users/akshayryali/liquidated damages/sample_docs"):
    """Generates a suite of sample PO PDFs for instant pilot demonstration."""
    os.makedirs(base_dir, exist_ok=True)
    
    # 0. British Oil & Gas / Dongying Lake Petroleum (Real Scanned Invoice matching user document)
    generate_sample_po_pdf(
        output_path=os.path.join(base_dir, "BOGEL-10608-Dongying_Lake_Petroleum.pdf"),
        po_number="BOGEL-10608-11-2025-GC000009",
        vendor="Dongying Lake Petroleum Technology Co., Ltd",
        company="British Oil & Gas Exploration Limited",
        amount=23755.27,
        currency="USD",
        readiness_days=45,
        ack_date="2026-01-21",
        receipt_date="2026-03-20",
        fm_days=2
    )

    # 1. Standard Case matching LD Format.xlsx (60 readiness days, 7 days delay, 2 days FM -> 5 days net delay)
    generate_sample_po_pdf(
        output_path=os.path.join(base_dir, "PO-2026-00109_Standard_Delay.pdf"),
        po_number="PO-2026-00109",
        vendor="Global Equipment & Engineering Ltd",
        company="BQUBE IT SOLUTION NIGERIA LIMITED",
        amount=150000.00,
        currency="USD",
        readiness_days=60,
        ack_date="2026-01-02",
        receipt_date="2026-03-10",
        fm_days=2
    )

    # 2. Heavy Delay Case hitting 5% Max Cap (45 readiness days, 50 days delay -> Capped at 5%)
    generate_sample_po_pdf(
        output_path=os.path.join(base_dir, "PO-2026-00115_Max_Capped_Delay.pdf"),
        po_number="PO-2026-00115",
        vendor="Subsea Electrical & Instrumentation Ltd",
        company="BQUBE IT SOLUTION NIGERIA LIMITED",
        amount=280000.00,
        currency="USD",
        readiness_days=45,
        ack_date="2025-12-10",
        receipt_date="2026-03-01",
        fm_days=0
    )

    # 3. High Value Local Currency with High Force Majeure
    generate_sample_po_pdf(
        output_path=os.path.join(base_dir, "PO-2026-00122_Local_Currency_NGN.pdf"),
        po_number="PO-2026-00122",
        vendor="Apex Logistics & Heavy Lift Services",
        company="BQUBE IT SOLUTION NIGERIA LIMITED",
        amount=45000000.00,
        currency="NGN",
        readiness_days=30,
        ack_date="2026-01-15",
        receipt_date="2026-03-08",
        fm_days=5
    )


if __name__ == "__main__":
    create_all_samples()
    print("Sample PO PDFs generated successfully.")
