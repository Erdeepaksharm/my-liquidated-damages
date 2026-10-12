"""Core Liquidated Damages (LD) Calculation Engine strictly conforming to LD Format.xlsx."""
from datetime import date, timedelta
import math
from typing import Optional, Dict, Any, List
from .models import PurchaseOrder, LDCalculationResult


class LDEngine:
    """Enterprise LD Calculation Engine."""

    @staticmethod
    def calculate_ld(po: PurchaseOrder) -> LDCalculationResult:
        """
        Calculates Liquidated Damages based on the official formula in LD Format.xlsx:
        - Expected Readiness Date = PO Acknowledged Date + Readiness Period Days
        - Gross Delay Days = Material Received Date - Expected Readiness Date
        - Net Delay Days = max(0, Gross Delay Days - Force Majeure Days)
        - Delay in Weeks = Net Delay Days / 7.0
        - Completed Delayed Weeks = Delay in Weeks (or floor if rounding_mode == 'completed')
        - LD Per Completed Week = Invoice Value * LD Rate (e.g. 1%)
        - Total LD = min(Completed Delayed Weeks * LD Per Week, Max Limit * Invoice Value)
        - Net Payable = Invoice Value - Total LD
        """
        # Determine effective calculation value (Invoice Value preferred, PO Value fallback)
        calc_value = po.invoice_value if (po.invoice_value is not None and po.invoice_value > 0) else po.total_po_value
        
        # 1. Expected Date of Readiness as per PO (E11 = E9 + E10)
        expected_readiness_date = po.po_acknowledged_date + timedelta(days=po.readiness_period_days)
        
        # 2. Material receipt / JCC date check
        received_date = po.material_received_date or date.today()
        
        # 3. Delay in Readiness / Delivery in Days (E15 = E13 - E11)
        gross_delay_days = (received_date - expected_readiness_date).days
        
        # 4. Net Delay Excluding Force Majeure (E17 = E15 - E16)
        force_majeure = max(0, po.force_majeure_days)
        net_delay_days = max(0, gross_delay_days - force_majeure)
        
        # 5. Delay in weeks (E18 = E17 / 7)
        delay_in_weeks = net_delay_days / 7.0
        
        # 6. Completed Delayed Weeks as per PO Terms (E19)
        if po.rounding_mode == "completed":
            completed_delayed_weeks = float(math.floor(delay_in_weeks))
        else:
            # Exact fractional as in the default LD Format.xlsx (=E18)
            completed_delayed_weeks = delay_in_weeks
            
        # 7. LD Rate and Max Limit
        ld_rate = po.ld_rate_per_week if po.ld_rate_per_week > 0 else 0.01
        max_limit_pct = po.max_ld_limit_percent if po.max_ld_limit_percent > 0 else 0.05
        
        # Max allowable delay weeks before hitting cap
        max_weeks_cap = max_limit_pct / ld_rate if ld_rate > 0 else 5.0
        
        # 8. LD Per Completed Week (E23 = E8 * E21)
        ld_per_completed_week = calc_value * ld_rate
        
        # 9. Total LD & Capping (E24 = IF(E19<=5, E23*E19, E23*5))
        max_allowable_ld = calc_value * max_limit_pct
        if completed_delayed_weeks <= 0:
            calculated_total_ld = 0.0
            is_capped = False
        elif completed_delayed_weeks <= max_weeks_cap:
            calculated_total_ld = ld_per_completed_week * completed_delayed_weeks
            is_capped = False
        else:
            calculated_total_ld = max_allowable_ld
            is_capped = True
            
        # Round financial values to 2 decimal places
        calculated_total_ld = round(calculated_total_ld, 2)
        ld_per_completed_week = round(ld_per_completed_week, 2)
        max_allowable_ld = round(max_allowable_ld, 2)
        net_payable = round(calc_value - calculated_total_ld, 2)
        
        # Generate clear step-by-step formula explanation
        explanation = [
            f"1. Expected Readiness Date = {po.po_acknowledged_date.strftime('%d-%b-%Y')} + {po.readiness_period_days} days = {expected_readiness_date.strftime('%d-%b-%Y')}",
            f"2. Gross Delivery Delay = Received Date ({received_date.strftime('%d-%b-%Y')}) - Expected Date ({expected_readiness_date.strftime('%d-%b-%Y')}) = {gross_delay_days} days",
            f"3. Authorized Force Majeure / Restriction = {force_majeure} days",
            f"4. Net Delay Subject to LD = {gross_delay_days} - {force_majeure} = {net_delay_days} days ({delay_in_weeks:.2f} weeks)",
            f"5. Base Assessment Value = {po.currency} {calc_value:,.2f}",
            f"6. Weekly LD Rate = {ld_rate * 100:.1f}% per week ({po.currency} {ld_per_completed_week:,.2f}/week)",
            f"7. Max LD Cap = {max_limit_pct * 100:.1f}% ({po.currency} {max_allowable_ld:,.2f} maximum)",
        ]
        
        if is_capped:
            explanation.append(f"8. [CAPPED] Delay of {completed_delayed_weeks:.2f} weeks reached contract maximum cap of {max_weeks_cap:.1f} weeks. Total LD is capped at {po.currency} {max_allowable_ld:,.2f}.")
        else:
            explanation.append(f"8. Total LD Applied = {completed_delayed_weeks:.2f} weeks × {po.currency} {ld_per_completed_week:,.2f} = {po.currency} {calculated_total_ld:,.2f}")
            
        explanation.append(f"9. Net Payable to Vendor = {po.currency} {calc_value:,.2f} - {po.currency} {calculated_total_ld:,.2f} = {po.currency} {net_payable:,.2f}")

        return LDCalculationResult(
            po_number=po.po_number,
            company_name=po.company_name,
            vendor_name=po.vendor_name,
            po_date=po.po_date,
            po_acknowledged_date=po.po_acknowledged_date,
            readiness_period_days=po.readiness_period_days,
            expected_readiness_date=expected_readiness_date,
            waybill_date=po.waybill_date,
            material_received_date=received_date,
            delay_in_days=gross_delay_days,
            force_majeure_days=force_majeure,
            delay_excl_force_majeure_days=net_delay_days,
            delay_in_weeks=round(delay_in_weeks, 4),
            completed_delayed_weeks=round(completed_delayed_weeks, 4),
            total_po_value=po.total_po_value,
            invoice_value=calc_value,
            ld_rate_per_week=ld_rate,
            max_ld_limit_percent=max_limit_pct,
            ld_per_completed_week=ld_per_completed_week,
            calculated_total_ld=calculated_total_ld,
            ld_as_per_po=calculated_total_ld,
            max_allowable_ld=max_allowable_ld,
            is_capped=is_capped,
            net_payable_amount=net_payable,
            currency=po.currency,
            invoice_no=po.invoice_no,
            explanation=explanation
        )
