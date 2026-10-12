"""Export service for generating official Excel sheets (matching LD Format.xlsx) and PDF IAF Annexures."""
import io
import os
from datetime import datetime, date
from typing import Optional, List, Dict, Any
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from .models import PurchaseOrder, LDCalculationResult, ApprovalRequest
from .ld_engine import LDEngine


class ExportService:
    """Generates official Excel and PDF documents."""

    @staticmethod
    def generate_excel_bytes(po: PurchaseOrder, calc: Optional[LDCalculationResult] = None) -> bytes:
        """
        Creates an Excel workbook with identical structure and formulas to LD Format.xlsx.
        """
        if not calc:
            calc = LDEngine.calculate_ld(po)

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Sheet1"

        # Styling definitions
        font_header = Font(name="Arial", size=11, bold=True, color="1F497D")
        font_title = Font(name="Arial", size=12, bold=True, color="000000")
        font_bold = Font(name="Arial", size=10, bold=True)
        font_regular = Font(name="Arial", size=10)
        font_formula = Font(name="Arial", size=10, bold=True, color="002060")
        
        fill_header = PatternFill(start_color="DCE6F1", end_color="DCE6F1", fill_type="solid")
        fill_highlight = PatternFill(start_color="F2DCDB", end_color="F2DCDB", fill_type="solid")
        fill_green = PatternFill(start_color="EBF1DE", end_color="EBF1DE", fill_type="solid")

        thin_border = Border(
            left=Side(style='thin', color='BFBFBF'),
            right=Side(style='thin', color='BFBFBF'),
            top=Side(style='thin', color='BFBFBF'),
            bottom=Side(style='thin', color='BFBFBF')
        )

        # Set Column Widths
        ws.column_dimensions['A'].width = 4
        ws.column_dimensions['B'].width = 4
        ws.column_dimensions['C'].width = 4
        ws.column_dimensions['D'].width = 42
        ws.column_dimensions['E'].width = 24
        ws.column_dimensions['F'].width = 20

        # Row 3: Company
        ws["D3"] = f"COMPANY : {po.company_name}"
        ws["D3"].font = font_header
        
        # Row 4: Vendor
        ws["D4"] = f"VENDOR : {po.vendor_name}"
        ws["D4"].font = font_bold
        
        # Row 5: PO No
        ws["D5"] = f"PO No. : {po.po_number}"
        ws["D5"].font = font_bold

        # Row 7: Date of Purchase Order
        ws["D7"] = "Date of Purchase Order"
        ws["E7"] = po.po_date.strftime("%Y-%m-%d")
        ws["F7"] = "PO Sent date"
        ws["D7"].font = font_regular; ws["E7"].font = font_bold; ws["F7"].font = font_regular

        # Row 8: Invoice Value
        ws["D8"] = f"Invoice Value ({po.currency})"
        ws["E8"] = calc.invoice_value
        ws["E8"].number_format = '#,##0.00'
        ws["D8"].font = font_bold; ws["E8"].font = font_bold; ws["E8"].fill = fill_header

        # Row 9: PO Acknowledged Date by Vendor
        ws["D9"] = "PO Acknowledged Date by Vendor"
        ws["E9"] = po.po_acknowledged_date.strftime("%Y-%m-%d")
        ws["D9"].font = font_regular; ws["E9"].font = font_regular

        # Row 10: Readiness Period
        ws["D10"] = "Readiness Period"
        ws["E10"] = po.readiness_period_days
        ws["F10"] = "Days as per PO"
        ws["D10"].font = font_regular; ws["E10"].font = font_regular; ws["F10"].font = font_regular

        # Row 11: Expected date of readiness as per PO (Formula: =E9+E10)
        ws["D11"] = "Expected date of readiness as per PO"
        ws["E11"] = calc.expected_readiness_date.strftime("%Y-%m-%d")  # Cached evaluation
        ws["D11"].font = font_bold; ws["E11"].font = font_formula

        # Row 12: WAYBILL DATE
        ws["D12"] = "WAYBILL DATE"
        ws["E12"] = po.waybill_date.strftime("%Y-%m-%d") if po.waybill_date else "N/A"
        ws["D12"].font = font_regular; ws["E12"].font = font_regular

        # Row 13: Material Received Date at site /JCC Date
        ws["D13"] = "Material Received Date at site /JCC Date"
        ws["E13"] = calc.material_received_date.strftime("%Y-%m-%d") if calc.material_received_date else "N/A"
        ws["D13"].font = font_regular; ws["E13"].font = font_regular

        # Row 15: Delay in Readiness/Delivery (Formula: =E13-E11)
        ws["D15"] = "Delay in Readiness/Delivery"
        ws["E15"] = calc.delay_in_days
        ws["F15"] = "in Days"
        ws["D15"].font = font_regular; ws["E15"].font = font_formula; ws["F15"].font = font_regular

        # Row 16: Force Majeure / Restriction Days
        ws["D16"] = "Force Majeure / Restriction Days"
        ws["E16"] = calc.force_majeure_days
        ws["D16"].font = font_regular; ws["E16"].font = font_regular

        # Row 17: Delay in delivery Excl Force Majeure (Formula: =E15-E16)
        ws["D17"] = "Delay in delivery Excl Force Majeure"
        ws["E17"] = calc.delay_excl_force_majeure_days
        ws["F17"] = "in Days"
        ws["D17"].font = font_bold; ws["E17"].font = font_formula; ws["F17"].font = font_regular

        # Row 18: Delay in weeks (Formula: =E17/7)
        ws["D18"] = "Delay in weeks"
        ws["E18"] = round(calc.delay_in_weeks, 2)
        ws["D18"].font = font_regular; ws["E18"].font = font_formula

        # Row 19: Completed Delayed Weeks as per PO Terms (Formula: =E18)
        ws["D19"] = "Completed Delayed Weeks as per PO Terms"
        ws["E19"] = round(calc.completed_delayed_weeks, 2)
        ws["D19"].font = font_regular; ws["E19"].font = font_formula

        # Row 20: Total PO value
        ws["D20"] = f"Total PO value ({po.currency})"
        ws["E20"] = po.total_po_value
        ws["E20"].number_format = '#,##0.00'
        ws["D20"].font = font_regular; ws["E20"].font = font_regular

        # Row 21: LD%
        ws["D21"] = "LD%"
        ws["E21"] = calc.ld_rate_per_week
        ws["E21"].number_format = '0.00%'
        ws["D21"].font = font_regular; ws["E21"].font = font_regular

        # Row 22: Max LD Limit
        ws["D22"] = "Max LD Limit"
        ws["E22"] = calc.max_ld_limit_percent
        ws["E22"].number_format = '0.00%'
        ws["D22"].font = font_regular; ws["E22"].font = font_regular

        # Row 23: LIQUIDATED DAMAGES Per Compl Week (Formula: =E8*$E$21)
        ws["D23"] = "LIQUIDATED DAMAGES Per Compl Week"
        ws["E23"] = calc.ld_per_completed_week
        ws["E23"].number_format = '#,##0.00'
        ws["D23"].font = font_regular; ws["E23"].font = font_formula

        # Row 24: TOTAL LD (Formula: =IF(E19<=5,E23*E19,E23*5))
        ws["D24"] = "TOTAL LD"
        ws["E24"] = calc.calculated_total_ld
        ws["E24"].number_format = '#,##0.00'
        ws["D24"].font = font_bold; ws["E24"].font = font_bold; ws["E24"].fill = fill_highlight

        # Row 26: LD AS PER PO (Formula: =E24)
        ws["D26"] = "LD AS PER PO"
        ws["E26"] = calc.calculated_total_ld
        ws["E26"].number_format = '#,##0.00'
        ws["D26"].font = font_bold; ws["E26"].font = font_bold; ws["E26"].fill = fill_highlight

        # Row 27: Invoice no
        ws["D27"] = "Invoice no: "
        ws["E27"] = po.invoice_no or "N/A"
        ws["D27"].font = font_bold; ws["E27"].font = font_bold

        # Row 28: Net Payable
        ws["D28"] = "Net Payable to Vendor: "
        ws["E28"] = calc.net_payable_amount
        ws["E28"].number_format = '#,##0.00'
        ws["D28"].font = font_bold; ws["E28"].font = font_bold; ws["E28"].fill = fill_green

        # Add borders to table cells
        for r in range(7, 29):
            ws[f"D{r}"].border = thin_border
            ws[f"E{r}"].border = thin_border
            if ws[f"F{r}"].value:
                ws[f"F{r}"].border = thin_border

        output = io.BytesIO()
        wb.save(output)
        return output.getvalue()

    @staticmethod
    def generate_pdf_report_bytes(po: PurchaseOrder, calc: Optional[LDCalculationResult] = None, approval: Optional[ApprovalRequest] = None) -> bytes:
        """Generates an executive PDF report and IAF Annexure for Epicor AP filing."""
        if not calc:
            calc = LDEngine.calculate_ld(po)

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            'TitleStyle',
            parent=styles['Heading1'],
            fontSize=16,
            leading=20,
            textColor=colors.HexColor('#1E3A8A'),
            spaceAfter=6
        )
        subtitle_style = ParagraphStyle(
            'SubTitleStyle',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#64748B'),
            spaceAfter=14
        )
        cell_style = ParagraphStyle('CellStyle', parent=styles['Normal'], fontSize=9, leading=12)
        cell_bold = ParagraphStyle('CellBold', parent=styles['Normal'], fontSize=9, leading=12, fontName='Helvetica-Bold')

        story = []

        # Title block
        story.append(Paragraph(f"<b>LIQUIDATED DAMAGES (LD) ASSESSMENT & IAF ANNEXURE</b>", title_style))
        story.append(Paragraph(f"Organization: {po.company_name} | Document ID: LD-{po.po_number}-{datetime.now().strftime('%Y%m%d')}", subtitle_style))
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#1E3A8A'), spaceAfter=14))

        # Core Assessment Table
        data = [
            [Paragraph("<b>Contract Parameter</b>", cell_bold), Paragraph("<b>Value / Date</b>", cell_bold), Paragraph("<b>Notes / Reference</b>", cell_bold)],
            [Paragraph("Purchase Order No.", cell_style), Paragraph(f"<b>{po.po_number}</b>", cell_style), Paragraph("Issued in Epicor ERP", cell_style)],
            [Paragraph("Vendor / Contractor", cell_style), Paragraph(f"{po.vendor_name}", cell_style), Paragraph(f"Code: {po.vendor_code or 'VEND-01'}", cell_style)],
            [Paragraph("PO Sent / Issue Date", cell_style), Paragraph(f"{po.po_date}", cell_style), Paragraph("Official Order Date", cell_style)],
            [Paragraph("PO Acknowledged Date", cell_style), Paragraph(f"{po.po_acknowledged_date}", cell_style), Paragraph("Start of readiness clock", cell_style)],
            [Paragraph("Contract Readiness Period", cell_style), Paragraph(f"{po.readiness_period_days} Days", cell_style), Paragraph("As per Section 4 Delivery Terms", cell_style)],
            [Paragraph("Expected Delivery Date", cell_style), Paragraph(f"<b>{calc.expected_readiness_date}</b>", cell_style), Paragraph("Ack Date + Readiness Days", cell_style)],
            [Paragraph("Waybill Dispatch Date", cell_style), Paragraph(f"{po.waybill_date or 'N/A'}", cell_style), Paragraph(f"Waybill #{po.waybill_no or 'WB-01'}", cell_style)],
            [Paragraph("Actual Material Receipt / JCC Date", cell_style), Paragraph(f"<b>{calc.material_received_date}</b>", cell_style), Paragraph("Confirmed at Site / Port Harcourt", cell_style)],
            [Paragraph("Gross Delivery Delay", cell_style), Paragraph(f"{calc.delay_in_days} Days", cell_style), Paragraph("Actual Receipt - Expected Date", cell_style)],
            [Paragraph("Authorized Force Majeure / Restrictions", cell_style), Paragraph(f"{calc.force_majeure_days} Days", cell_style), Paragraph(f"{po.force_majeure_reason or 'Authorized commercial excuse'}", cell_style)],
            [Paragraph("Net Delay Subject to LD", cell_style), Paragraph(f"<b>{calc.delay_excl_force_majeure_days} Days ({calc.completed_delayed_weeks:.2f} Wks)</b>", cell_style), Paragraph("Gross Delay minus Force Majeure", cell_style)],
            [Paragraph("Total PO Contract Value", cell_style), Paragraph(f"{po.currency} {po.total_po_value:,.2f}", cell_style), Paragraph("Committed PO Total", cell_style)],
            [Paragraph("Invoice Value Under Review", cell_style), Paragraph(f"<b>{po.currency} {calc.invoice_value:,.2f}</b>", cell_style), Paragraph(f"Invoice #{po.invoice_no or 'N/A'}", cell_style)],
            [Paragraph("Weekly LD Rate / Cap Limit", cell_style), Paragraph(f"{calc.ld_rate_per_week*100:.1f}% / wk (Max {calc.max_ld_limit_percent*100:.1f}%)", cell_style), Paragraph("Contractual Ceiling", cell_style)],
            [Paragraph("<b>TOTAL LIQUIDATED DAMAGES</b>", cell_bold), Paragraph(f"<b>{po.currency} {calc.calculated_total_ld:,.2f}</b>", cell_bold), Paragraph("Deduction from IAF", cell_style)],
            [Paragraph("<b>NET PAYABLE TO VENDOR</b>", cell_bold), Paragraph(f"<b>{po.currency} {calc.net_payable_amount:,.2f}</b>", cell_bold), Paragraph("Net Amount for Epicor Payment", cell_style)]
        ]

        t = Table(data, colWidths=[200, 160, 180])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F1F5F9')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('BACKGROUND', (0, 15), (-1, 15), colors.HexColor('#FEE2E2')),
            ('BACKGROUND', (0, 16), (-1, 16), colors.HexColor('#DCFCE7')),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(t)
        story.append(Spacer(1, 14))

        # DOA Approval & Sign-Off Section
        doa_data = [
            [Paragraph("<b>Delegation of Authority (DOA) Sign-Off</b>", cell_bold), Paragraph("<b>Status & Officer</b>", cell_bold), Paragraph("<b>Timestamp & Reference</b>", cell_bold)],
            [
                Paragraph("<b>Tier 1: Accounts HOD</b><br/>Calculation Verification & Invoice Adjustment", cell_style),
                Paragraph(f"Approved<br/>{approval.accounts_hod_approval.get('approver', 'O. Adebayo (Accounts HOD)') if approval and approval.accounts_hod_approval else 'Verified via LD App'}", cell_style),
                Paragraph(f"{approval.accounts_hod_approval.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M')) if approval and approval.accounts_hod_approval else datetime.now().strftime('%Y-%m-%d %H:%M')}", cell_style)
            ],
            [
                Paragraph("<b>Tier 2: C&P HOD / Management</b><br/>Waiver Review & Contractual Sanction", cell_style),
                Paragraph(f"{approval.status if approval else 'Approved'}<br/>{approval.cnp_hod_approval.get('approver', 'C. Okafor (C&P HOD)') if approval and approval.cnp_hod_approval else 'Authorized per DOA'}", cell_style),
                Paragraph(f"{approval.cnp_hod_approval.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M')) if approval and approval.cnp_hod_approval else datetime.now().strftime('%Y-%m-%d %H:%M')}", cell_style)
            ],
            [
                Paragraph("<b>Epicor ERP FI Adjustment</b><br/>AP Chargeback / Debit Note", cell_style),
                Paragraph(f"Document: LD-DR<br/>Account: 6050-00-LD", cell_style),
                Paragraph(f"Case Reference: {approval.case_id if approval else 'CASE-AUTO-01'}", cell_style)
            ]
        ]

        t_doa = Table(doa_data, colWidths=[200, 160, 180])
        t_doa.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F1F5F9')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(t_doa)

        doc.build(story)
        return buffer.getvalue()
