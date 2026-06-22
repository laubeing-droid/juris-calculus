"""Damage estimator — calculate statutory damage ranges."""
import yaml


def estimate_damages(loss_type: str, amount: float, jurisdiction: str = "CN") -> dict:
    """Estimate statutory damage range."""
    if jurisdiction == "CN":
        if loss_type == "contract_breach":
            return {
                "type": "违约赔偿",
                "direct_loss": amount,
                "foreseeable_loss_max": amount * 1.3,
                "penalty_cap": amount * 0.3,
                "legal_basis": "民法典第584条",
                "note": "赔偿范围包括实际损失和可得利益，但不超过违约方订立合同时预见到或应当预见到的损失",
            }
        elif loss_type == "tort":
            return {
                "type": "侵权赔偿",
                "medical_expenses": amount,
                "lost_income_estimated": amount * 0.5,
                "pain_suffering_range": [amount * 0.1, amount * 0.5],
                "legal_basis": "民法典第1179-1182条",
            }
        elif loss_type == "ip_infringement":
            return {
                "type": "知识产权侵权赔偿",
                "actual_loss": amount,
                "infringer_profit": amount * 2,
                "statutory_damages_range": [500, 5000000],
                "punitive_damages_range": [amount * 1, amount * 5],
                "legal_basis": "著作权法/专利法/商标法相关条款",
            }
    return {"type": loss_type, "amount": amount, "note": "No specific formula available"}
