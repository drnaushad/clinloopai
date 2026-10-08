import logging

logger = logging.getLogger("clinloop.sdoh_monitor")

def compute_disparity_ratio(outcomes: list) -> float:
    """
    Computes the disparity impact ratio.
    outcomes: list of dicts with 'sdoh_flag' (bool) and 'detected' (bool).
    Ratio = (Detection Rate in SDOH population) / (Detection Rate in Non-SDOH population).
    A ratio < 1.0 means vulnerable patients are being caught less often.
    """
    sdoh_total = sum(1 for o in outcomes if o.get('sdoh_flag'))
    sdoh_detected = sum(1 for o in outcomes if o.get('sdoh_flag') and o.get('detected'))
    
    non_sdoh_total = sum(1 for o in outcomes if not o.get('sdoh_flag'))
    non_sdoh_detected = sum(1 for o in outcomes if not o.get('sdoh_flag') and o.get('detected'))
    
    rate_sdoh = (sdoh_detected / sdoh_total) if sdoh_total > 0 else 0.0
    rate_non_sdoh = (non_sdoh_detected / non_sdoh_total) if non_sdoh_total > 0 else 0.0
    
    if rate_non_sdoh == 0:
        return 1.0
        
    return rate_sdoh / rate_non_sdoh

def run_sdoh_monitor(outcomes: list, hir_log: list, threshold: float = 0.80) -> dict:
    """
    Evaluates the disparity ratio. If below threshold, appends an alert to the HIR.
    """
    ratio = compute_disparity_ratio(outcomes)
    alert = ratio < threshold
    
    msg = f"Equity Check: Disparity Ratio = {ratio:.2f}"
    
    if alert:
        msg = f"⚠ EQUITY ALERT: Disparity Ratio {ratio:.2f} fell below safe threshold {threshold}. " \
              "SDOH/Vulnerable patients are disproportionately falling through the safety net."
        hir_log.append({
            "type": "SDOH_EQUITY_VIOLATION",
            "message": msg,
            "ratio": ratio
        })
        logger.warning(msg)
    else:
        logger.info(msg)
        
    return {
        "disparity_ratio": ratio,
        "alert_triggered": alert,
        "message": msg
    }
