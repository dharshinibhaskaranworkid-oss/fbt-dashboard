"""
FBT Adoption Opportunity Model
--------------------------------
Generates a synthetic dataset of FMCG sellers on TikTok Shop UK and scores each
non-FBT seller on how strong a candidate they are for Fulfilled by TikTok (FBT).

The scoring logic mirrors what the FBT Seller Growth team actually cares about:
  1. Operational pain   -> how much a seller stands to GAIN by switching
  2. Scale / volume      -> how much the switch is worth (to seller & to TikTok)
  3. Eligibility & fit   -> hard gates (UK weight/volume limits, not already on FBT)
  4. Margin headroom     -> can they absorb FBT fees and still profit?

Benchmarks are grounded in TikTok's own UK FBT launch figures (a pilot brand
reported volumes +30%, lead times -36%, late-dispatch -45% after switching) and
public FBT rate-card economics (~20-35% lower per-order cost vs typical self/3PL).

Output: sellers.csv (analysis) and sellers.json (dashboard feed).
Reproducible via a fixed random seed.
"""

import csv
import json
import random

random.seed(42)

# --- FBT hard eligibility limits (TikTok Shop UK) ---
MAX_WEIGHT_KG = 30.0
MAX_VOLUME_L = 31.5

CATEGORIES = {
    "Beverages":              {"weight": (2.0, 12.0), "aov": (8, 22),  "margin": (0.18, 0.34)},
    "Snacks & Confectionery": {"weight": (0.3, 3.5),  "aov": (7, 20),  "margin": (0.28, 0.48)},
    "Supplements & Vitamins": {"weight": (0.2, 1.5),  "aov": (14, 45), "margin": (0.45, 0.70)},
    "Personal Care":          {"weight": (0.2, 2.5),  "aov": (9, 30),  "margin": (0.40, 0.62)},
    "Household & Cleaning":   {"weight": (0.8, 8.0),  "aov": (6, 18),  "margin": (0.22, 0.40)},
    "Health Foods":           {"weight": (0.4, 5.0),  "aov": (10, 28), "margin": (0.30, 0.52)},
}

# Fictional FMCG brand name parts (all invented – no real brands)
PRE = ["Bright", "Pure", "Kova", "Nimbus", "Vale", "Orla", "Fenn", "Brisk", "Loom",
       "Wilder", "Nova", "Hale", "Dusk", "Clove", "Marlow", "Reef", "Ember", "Piper",
       "Selkie", "Frost", "Grove", "Tally", "Halcyon", "Bramble", "Quill", "Marram"]
SUF = ["& Co", "Foods", "Labs", "Botanics", "Supply", "Nutrition", "Kitchen", "Goods",
       "Wellness", "Drinks", "Craft", "Home", "Naturals", "Provisions", "Collective"]

FULFILMENT = ["Self-fulfilled", "3PL", "FBT-already"]


def make_seller(i):
    cat = random.choice(list(CATEGORIES.keys()))
    spec = CATEGORIES[cat]

    name = f"{random.choice(PRE)} {random.choice(SUF)}"
    months_active = random.randint(3, 48)

    # Fulfilment mix: most are self/3PL (our target pool), a minority already on FBT
    fulfilment = random.choices(FULFILMENT, weights=[0.5, 0.35, 0.15])[0]

    # Scale
    monthly_orders = int(random.lognormvariate(6.6, 0.9))          # ~ hundreds..thousands
    monthly_orders = max(40, min(monthly_orders, 42000))
    aov = round(random.uniform(*spec["aov"]), 2)
    monthly_gmv = round(monthly_orders * aov, 2)

    margin = round(random.uniform(*spec["margin"]), 3)
    sku_count = random.randint(3, 120)
    seller_rating = round(random.uniform(3.6, 4.9), 2)

    # Parcel size
    weight = round(random.uniform(*spec["weight"]), 2)
    # Heavy categories occasionally ship bulk multipacks that blow the FBT limit
    if cat in ("Beverages", "Household & Cleaning") and random.random() < 0.18:
        weight = round(weight * random.uniform(4.5, 9.0), 2)   # bulk multipack
    # crude volume proxy correlated with weight, in litres
    volume = round(weight * random.uniform(1.2, 2.6), 2)

    # Operational pain – self-fulfilled tends to be worse; FBT-already tends to be clean
    if fulfilment == "Self-fulfilled":
        late = random.uniform(3, 22); canc = random.uniform(1.5, 9); dely = random.uniform(2.2, 5.5)
    elif fulfilment == "3PL":
        late = random.uniform(1.5, 12); canc = random.uniform(1, 6); dely = random.uniform(1.8, 4.2)
    else:  # FBT-already
        late = random.uniform(0.3, 3); canc = random.uniform(0.3, 2.5); dely = random.uniform(1.0, 2.2)

    return {
        "seller_id": f"S{i:04d}",
        "seller_name": name,
        "category": cat,
        "months_active": months_active,
        "current_fulfilment": fulfilment,
        "monthly_orders": monthly_orders,
        "aov_gbp": aov,
        "monthly_gmv_gbp": monthly_gmv,
        "gross_margin": margin,
        "sku_count": sku_count,
        "seller_rating": seller_rating,
        "avg_parcel_weight_kg": weight,
        "avg_parcel_volume_l": volume,
        "late_dispatch_rate_pct": round(late, 2),
        "cancellation_rate_pct": round(canc, 2),
        "avg_delivery_days": round(dely, 2),
        "return_rate_pct": round(random.uniform(1, 9), 2),
    }


def clamp(x, lo=0, hi=100):
    return max(lo, min(hi, x))


def score_seller(s):
    """Return FBT fit score 0-100 plus components and cost/benefit projection."""
    # Hard eligibility gate
    eligible = (
        s["avg_parcel_weight_kg"] <= MAX_WEIGHT_KG
        and s["avg_parcel_volume_l"] <= MAX_VOLUME_L
    )
    already_fbt = s["current_fulfilment"] == "FBT-already"

    # --- 1. Operational pain (0-100): more pain = more to gain ---
    pain = (
        clamp(s["late_dispatch_rate_pct"] / 22 * 100) * 0.45
        + clamp(s["cancellation_rate_pct"] / 9 * 100) * 0.30
        + clamp((s["avg_delivery_days"] - 1) / 4.5 * 100) * 0.25
    )

    # --- 2. Scale (0-100): log-scaled order volume ---
    import math
    scale = clamp((math.log10(max(s["monthly_orders"], 1)) - 1.6) / (4.6 - 1.6) * 100)

    # --- 3. Margin headroom (0-100): can they absorb FBT fees? ---
    headroom = clamp((s["gross_margin"] - 0.15) / (0.70 - 0.15) * 100)

    # Weighted blend
    raw = pain * 0.35 + scale * 0.30 + headroom * 0.20 + 15  # 15 base for "fit"

    if not eligible:
        raw *= 0.35   # heavily penalise out-of-spec parcels
    if already_fbt:
        raw = 0        # not a target

    fit = round(clamp(raw), 1)

    # --- Cost / benefit projection ---
    # Estimated current cost per order (self worse than 3PL), then FBT ~28% cheaper
    base_cpo = {"Self-fulfilled": 4.90, "3PL": 4.10, "FBT-already": 3.30}[s["current_fulfilment"]]
    # weight adds cost
    current_cpo = round(base_cpo + s["avg_parcel_weight_kg"] * 0.22, 2)
    fbt_cpo = round(current_cpo * 0.72, 2)  # ~28% saving, mid of 20-35% range
    saving_per_order = round(current_cpo - fbt_cpo, 2)
    monthly_saving = round(saving_per_order * s["monthly_orders"], 2)

    # Projected volume uplift, scaled by how much pain they'll relieve (cap at +30%)
    uplift_pct = round(min(30, (pain / 100) * 30 + 4), 1)  # 4%..30%
    projected_gmv = round(s["monthly_gmv_gbp"] * (1 + uplift_pct / 100), 2)
    projected_gmv_gain = round(projected_gmv - s["monthly_gmv_gbp"], 2)

    s.update({
        "eligible": eligible,
        "fbt_fit_score": fit,
        "score_pain": round(pain, 1),
        "score_scale": round(scale, 1),
        "score_headroom": round(headroom, 1),
        "est_current_cost_per_order_gbp": current_cpo,
        "est_fbt_cost_per_order_gbp": fbt_cpo,
        "est_monthly_fulfilment_saving_gbp": monthly_saving,
        "projected_volume_uplift_pct": uplift_pct,
        "projected_monthly_gmv_gain_gbp": projected_gmv_gain,
    })
    return s


def priority_band(score):
    if score >= 70: return "Hot"
    if score >= 50: return "Warm"
    if score >= 30: return "Watch"
    return "Low"


def main(n=220):
    sellers = [score_seller(make_seller(i + 1)) for i in range(n)]
    for s in sellers:
        s["priority"] = priority_band(s["fbt_fit_score"])

    # Rank the targetable pool (exclude those already on FBT)
    targets = [s for s in sellers if s["current_fulfilment"] != "FBT-already"]
    targets.sort(key=lambda x: x["fbt_fit_score"], reverse=True)
    for rank, s in enumerate(targets, 1):
        s["rank"] = rank

    # CSV (full analysis file)
    fields = list(sellers[0].keys())
    with open("sellers.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(sellers)

    # JSON feed for the dashboard
    with open("sellers.json", "w") as f:
        json.dump(sellers, f, indent=0)

    # Console summary
    hot = [s for s in targets if s["priority"] == "Hot"]
    total_saving = sum(s["est_monthly_fulfilment_saving_gbp"] for s in hot)
    total_gain = sum(s["projected_monthly_gmv_gain_gbp"] for s in hot)
    print(f"Generated {len(sellers)} sellers  ({len(targets)} targetable, "
          f"{len(sellers)-len(targets)} already on FBT)")
    print(f"Hot leads: {len(hot)}")
    print(f"Combined est. monthly fulfilment saving across Hot leads: £{total_saving:,.0f}")
    print(f"Combined projected monthly GMV gain across Hot leads:     £{total_gain:,.0f}")


if __name__ == "__main__":
    main()
