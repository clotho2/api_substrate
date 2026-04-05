"""
Probability Engine — Model Consensus Scoring

Computes P(YES) for a weather contract by combining data from multiple sources:
1. Primary: GFS ensemble member counting (28/31 members > threshold = 90% P)
2. Fallback: Weighted average across sources
3. Optional: Gaussian error model for forecast uncertainty

Blocks entry if source_count < 2 or model_agreement < MIN_CONSENSUS.
"""

import math
import os
from typing import Dict, Any, List, Optional

MIN_CONSENSUS = float(os.environ.get("POLYMARKET_MIN_CONSENSUS", "0.65"))


def compute_consensus(
    weather_data: Dict[str, Any],
    threshold: float,
    comparison: str = "above",
    metric: str = "temperature",
) -> Dict[str, Any]:
    """
    Compute probability consensus from multiple weather data sources.

    Args:
        weather_data: Output from weather_fetcher.fetch_all_sources()
        threshold: The contract threshold (e.g., 70 for "Will temp exceed 70F?")
        comparison: "above" or "below" the threshold
        metric: The weather metric being evaluated

    Returns:
        Consensus result with probability, agreement score, and method used.
    """
    sources = weather_data.get("sources", [])
    successful_sources = [s for s in sources if s.get("confidence", 0) > 0]
    source_count = len(successful_sources)

    if source_count < 1:
        return _blocked_result("No weather data sources returned valid data", source_count)

    # Try ensemble counting first (most rigorous)
    open_meteo = weather_data.get("open_meteo", {})
    ensemble_result = _ensemble_counting(open_meteo, threshold, comparison, metric)

    if ensemble_result is not None:
        # Supplement with observation-based validation
        obs_probs = _observation_probabilities(sources, threshold, comparison, metric)
        agreement = _calculate_agreement(ensemble_result["p_yes"], obs_probs)

        return {
            "status": "OK",
            "p_yes": ensemble_result["p_yes"],
            "p_no": 1.0 - ensemble_result["p_yes"],
            "consensus_score": agreement,
            "source_count": source_count,
            "model_agreement": agreement,
            "method_used": "ensemble_counting",
            "ensemble_detail": ensemble_result,
            "meets_threshold": agreement >= MIN_CONSENSUS,
            "blocked": source_count < 2 or agreement < MIN_CONSENSUS,
            "block_reason": _get_block_reason(source_count, agreement),
        }

    # Fallback: weighted average across sources
    weighted_result = _weighted_consensus(sources, threshold, comparison, metric)
    if weighted_result is not None:
        return {
            "status": "OK",
            "p_yes": weighted_result["p_yes"],
            "p_no": 1.0 - weighted_result["p_yes"],
            "consensus_score": weighted_result["agreement"],
            "source_count": source_count,
            "model_agreement": weighted_result["agreement"],
            "method_used": "weighted_average",
            "meets_threshold": weighted_result["agreement"] >= MIN_CONSENSUS,
            "blocked": source_count < 2 or weighted_result["agreement"] < MIN_CONSENSUS,
            "block_reason": _get_block_reason(source_count, weighted_result["agreement"]),
        }

    return _blocked_result("Could not compute probability from available data", source_count)


def compute_ev(model_p: float, market_p: float) -> float:
    """
    Compute expected value per dollar.
    EV = P_true * (1 - P_market) - (1 - P_true) * P_market
    """
    return model_p * (1.0 - market_p) - (1.0 - model_p) * market_p


def gaussian_probability(
    forecast_value: float,
    threshold: float,
    comparison: str = "above",
    lead_hours: int = 24,
) -> float:
    """
    Compute probability using Gaussian error model.

    Treats forecast errors as normally distributed, with standard deviation
    varying by forecast lead time (2.5F for 0-6h, up to 7.5F for 72h+).

    Pattern from hcharper/polyBot-Weather.
    """
    # Error margins by lead time
    if lead_hours <= 6:
        sigma = 2.5
    elif lead_hours <= 24:
        sigma = 4.0
    elif lead_hours <= 48:
        sigma = 5.5
    else:
        sigma = 7.5

    # P(actual > threshold) = P(Z > (threshold - forecast) / sigma)
    z = (threshold - forecast_value) / sigma if sigma > 0 else 0.0

    if comparison == "above":
        return 1.0 - _normal_cdf(z)
    else:
        return _normal_cdf(z)


# ============================================
# PRIVATE METHODS
# ============================================

def _ensemble_counting(
    open_meteo_data: Dict[str, Any],
    threshold: float,
    comparison: str,
    metric: str,
) -> Optional[Dict[str, Any]]:
    """
    Count ensemble members above/below threshold.

    e.g., 28/31 members predict > 70F = 90.3% probability.
    This is the most rigorous method when ensemble data is available.
    """
    ensemble_members = open_meteo_data.get("ensemble_members")
    if not ensemble_members:
        return None

    total_counts = 0
    above_counts = 0

    for step in ensemble_members:
        values = step.get("values", [])
        for v in values:
            total_counts += 1
            if comparison == "above" and v > threshold:
                above_counts += 1
            elif comparison == "below" and v < threshold:
                above_counts += 1

    if total_counts == 0:
        return None

    p_yes = above_counts / total_counts

    return {
        "p_yes": round(p_yes, 4),
        "members_favorable": above_counts,
        "members_total": total_counts,
        "threshold": threshold,
        "comparison": comparison,
    }


def _observation_probabilities(
    sources: List[Dict[str, Any]],
    threshold: float,
    comparison: str,
    metric: str,
) -> List[float]:
    """Extract implied probabilities from observation sources (NOAA, METAR)."""
    probs = []

    for source in sources:
        source_name = source.get("source", "")
        if source_name in ("noaa", "metar"):
            # For observations, use Gaussian model centered on observed value
            value = None
            if source_name == "noaa":
                value = source.get("value")
            elif source_name == "metar":
                if metric == "temperature":
                    value = source.get("temperature_f")
                elif metric == "wind_speed":
                    value = source.get("wind_speed_mph")

            if value is not None:
                # Observations have tighter error bounds (lead_hours=0)
                p = gaussian_probability(value, threshold, comparison, lead_hours=0)
                probs.append(p)

    return probs


def _weighted_consensus(
    sources: List[Dict[str, Any]],
    threshold: float,
    comparison: str,
    metric: str,
) -> Optional[Dict[str, Any]]:
    """
    Fallback: weighted average when ensemble data isn't available.
    Weights: Open-Meteo (0.5), NOAA (0.3), METAR (0.2)
    """
    weights = {"open_meteo": 0.5, "open_meteo_ensemble": 0.5, "noaa": 0.3, "metar": 0.2}
    total_weight = 0.0
    weighted_p = 0.0
    individual_ps = []

    for source in sources:
        source_name = source.get("source", "")
        weight = weights.get(source_name, 0.1)

        value = None
        if source_name in ("noaa",):
            value = source.get("value")
        elif source_name in ("open_meteo", "open_meteo_ensemble"):
            value = source.get("value")
        elif source_name == "metar":
            if metric == "temperature":
                value = source.get("temperature_f")
            elif metric == "wind_speed":
                value = source.get("wind_speed_mph")

        if value is not None:
            # Use Gaussian model for each source
            lead_hours = 0 if source_name in ("noaa", "metar") else 24
            p = gaussian_probability(value, threshold, comparison, lead_hours)
            weighted_p += weight * p
            total_weight += weight
            individual_ps.append(p)

    if total_weight == 0:
        return None

    p_yes = weighted_p / total_weight
    agreement = _calculate_agreement(p_yes, individual_ps) if individual_ps else 0.0

    return {
        "p_yes": round(p_yes, 4),
        "agreement": round(agreement, 4),
        "individual_probabilities": individual_ps,
    }


def _calculate_agreement(consensus_p: float, individual_ps: List[float]) -> float:
    """
    Calculate agreement score (0-1) based on how close individual
    source probabilities are to the consensus.
    """
    if not individual_ps:
        return 0.5  # Neutral if only one source

    deviations = [abs(p - consensus_p) for p in individual_ps]
    avg_deviation = sum(deviations) / len(deviations)

    # Agreement = 1 - avg_deviation (clamped to 0-1)
    # Low deviation = high agreement
    agreement = max(0.0, min(1.0, 1.0 - avg_deviation))
    return round(agreement, 4)


def _get_block_reason(source_count: int, agreement: float) -> Optional[str]:
    """Return the reason for blocking a trade, or None if not blocked."""
    reasons = []
    if source_count < 2:
        reasons.append(f"Insufficient sources ({source_count}/2 minimum)")
    if agreement < MIN_CONSENSUS:
        reasons.append(f"Low model agreement ({agreement:.2f} < {MIN_CONSENSUS} threshold)")
    return "; ".join(reasons) if reasons else None


def _blocked_result(reason: str, source_count: int) -> Dict[str, Any]:
    """Return a blocked consensus result."""
    return {
        "status": "blocked",
        "p_yes": None,
        "p_no": None,
        "consensus_score": 0.0,
        "source_count": source_count,
        "model_agreement": 0.0,
        "method_used": None,
        "meets_threshold": False,
        "blocked": True,
        "block_reason": reason,
    }


def _normal_cdf(z: float) -> float:
    """Approximate the standard normal CDF using the error function."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2)))
