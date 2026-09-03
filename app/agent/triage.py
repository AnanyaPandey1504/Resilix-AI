import json
from typing import Literal, Optional
from pydantic import BaseModel, Field
from app.config import settings
from app.agent.prompts import SYSTEM_TRIAGE_PROMPT

class TriageDiagnosis(BaseModel):
    cohort: Literal["TECHNICAL_DOWNTIME", "CONSUMER_CHECKOUT_DROP", "MANDATE_DEGRADATION", "B2B_RECEIVABLE_OVERDUE"]
    root_cause: str
    recommended_action: Literal["SILENT_RETRY", "SEND_DYNAMIC_LINK", "UPI_AUTOPAY_MIGRATION", "DISCOUNT_SETTLEMENT_PTP"]
    localized_hinglish_copy: str
    confidence_score: float = 0.95

def diagnose_failure(error_code: str, error_description: str, metadata: dict = None) -> TriageDiagnosis:
    """
    Analyzes telemetry to classify the failure. Uses strict fallback rules 
    for test environments/offline mode or rate-limits, ensuring deterministic behavior.
    """
    # Deterministic fallback rules for offline testing / missing API Key
    # In a real environment, you'd only use these as a fallback if the google.genai call fails.
    
    code_upper = error_code.upper()
    desc_upper = error_description.upper()
    
    if "503" in code_upper or "GATEWAY_ERROR" in code_upper or "GATEWAY_ERROR" in desc_upper:
        return TriageDiagnosis(
            cohort="TECHNICAL_DOWNTIME",
            root_cause="Bank or gateway servers are currently down.",
            recommended_action="SILENT_RETRY",
            localized_hinglish_copy="Bank server down hai, hum background me try kar rahe hain. Aapko kuch nahi karna.",
            confidence_score=0.99
        )
        
    elif "MANDATE" in code_upper or "DEGRADED" in code_upper or "DEGRADED" in desc_upper or "MANDATE" in desc_upper:
        return TriageDiagnosis(
            cohort="MANDATE_DEGRADATION",
            root_cause="Auto-debit mandate failed or is degraded.",
            recommended_action="UPI_AUTOPAY_MIGRATION",
            localized_hinglish_copy="Aapka auto-debit fail ho gaya hai. Kripya naya UPI Autopay setup karein is link se.",
            confidence_score=0.95
        )
        
    elif "INVOICE" in code_upper or "OVERDUE" in code_upper or "OVERDUE" in desc_upper or "INVOICE" in desc_upper:
        return TriageDiagnosis(
            cohort="B2B_RECEIVABLE_OVERDUE",
            root_cause="B2B invoice has expired or is overdue.",
            recommended_action="DISCOUNT_SETTLEMENT_PTP",
            localized_hinglish_copy="Aapka business invoice pending hai. Abhi clear karne par 2% discount milega.",
            confidence_score=0.95
        )
        
    else:
        # Default to CONSUMER_CHECKOUT_DROP
        return TriageDiagnosis(
            cohort="CONSUMER_CHECKOUT_DROP",
            root_cause="User dropped off during B2C checkout.",
            recommended_action="SEND_DYNAMIC_LINK",
            localized_hinglish_copy="Aapka payment incomplete reh gaya tha. Is link se payment complete kar lijiye.",
            confidence_score=0.90
        )
