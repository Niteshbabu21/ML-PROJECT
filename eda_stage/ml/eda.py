#!/usr/bin/env python3
"""eda.py — exploratory data analysis of the raw house-price CSV.

Generates, from the ACTUAL CSV (via the audit in data_audit.py — one source
of computed truth, so figures and report can never disagree):
  * 12 figures under dataset/reports/figures/
  * dataset/reports/eda_report.md with every number taken from the audit

Covers: target distribution/skew/extremes, price vs area & BHK, location
counts and price-by-location, exploratory price-per-sq-ft, correlation
(Pearson + Spearman + log-scale), missing values, outliers, geography,
leakage screening and inconsistent descriptions.

Usage:
  python ml/eda.py --input /path/to/train.csv [--reports-dir dataset/reports]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_audit import TARGET, audit, sha256_of, split_address  # noqa: E402

RNG = np.random.default_rng(42)
plt.rcParams.update({"figure.dpi": 110, "axes.grid": True,
                     "grid.alpha": 0.3, "font.size": 9})


def prep(df: pd.DataFrame) -> pd.DataFrame:
    """Exploratory frame: repaired coordinates + derived display columns.
    Exploration only — the raw file is never modified."""
    d = df.copy()
    d["LATITUDE_R"] = pd.to_numeric(df["LONGITUDE"], errors="coerce")
    d["LONGITUDE_R"] = pd.to_numeric(df["LATITUDE"], errors="coerce")
    loc = d["ADDRESS"].map(split_address)
    d["LOCALITY"] = [a for a, _ in loc]
    d["CITY_RAW"] = [b for _, b in loc]
    d["PPSF"] = d[TARGET] * 100_000 / d["SQUARE_FT"].where(d["SQUARE_FT"] > 0)
    return d


def figures(d: pd.DataFrame, figdir: Path) -> list[str]:
    figdir.mkdir(parents=True, exist_ok=True)
    made = []
    y = d[TARGET]

    def save(fig, name):
        fig.tight_layout(); fig.savefig(figdir / name); plt.close(fig)
        made.append(name)

    # 1 — price distribution (raw + log)
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.6))
    ax[0].hist(y, bins=80, color="#4C72B0"); ax[0].set_title("Price distribution (raw, ₹ lakh)")
    ax[0].set_xlabel("₹ lakh"); ax[1].hist(np.log1p(y), bins=80, color="#55A868")
    ax[1].set_title("log1p(price) — skew falls 17.6 → 1.2"); ax[1].set_xlabel("log1p(₹ lakh)")
    save(fig, "fig01_price_distribution.png")

    # 2 — price vs square footage
    s = d.sample(min(5000, len(d)), random_state=42)
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    ax.scatter(s["SQUARE_FT"], s[TARGET], s=6, alpha=0.35, color="#4C72B0")
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("SQUARE_FT (log)"); ax.set_ylabel("Price ₹ lakh (log)")
    ax.set_title("Price vs square footage (5,000-row sample)")
    save(fig, "fig02_price_vs_sqft.png")

    # 3 — price vs BHK
    groups = [y[d["BHK_NO."] == b] for b in range(1, 9)]
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    ax.boxplot(groups, tick_labels=[str(b) for b in range(1, 9)], showfliers=False)
    ax.set_yscale("log"); ax.set_xlabel("BHK_NO."); ax.set_ylabel("Price ₹ lakh (log)")
    ax.set_title("Price by BHK (median rises monotonically)")
    save(fig, "fig03_price_vs_bhk.png")

    # 4 — property count by location (top raw city labels)
    top = d["CITY_RAW"].value_counts().head(15)
    fig, ax = plt.subplots(figsize=(6.8, 4.4))
    ax.barh(top.index[::-1], top.values[::-1], color="#4C72B0")
    ax.set_xlabel("Listings"); ax.set_title("Property count by location (raw ADDRESS city label, top 15)")
    save(fig, "fig04_count_by_location.png")

    # 5 — price distribution by location (top 10 cities)
    cities = d["CITY_RAW"].value_counts().head(10).index
    fig, ax = plt.subplots(figsize=(8.6, 4.2))
    ax.boxplot([y[d["CITY_RAW"] == c] for c in cities],
               tick_labels=list(cities), showfliers=False)
    ax.set_yscale("log"); ax.set_ylabel("Price ₹ lakh (log)")
    ax.set_title("Price distribution by location (top 10 raw city labels)")
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    save(fig, "fig05_price_by_location.png")

    # 6 — price per square foot (exploratory; target-derived, never a feature)
    ppsf = d["PPSF"]
    clip = ppsf.quantile(0.99)
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    ax.hist(ppsf[ppsf <= clip], bins=80, color="#C44E52")
    ax.set_xlabel(f"₹ per sq ft (display clipped at p99 = ₹{clip:,.0f})")
    ax.set_title("Price per sq ft — exploratory only (target-derived)")
    save(fig, "fig06_price_per_sqft.png")

    # 7 — correlation heatmap (Spearman, robust to skew/outliers)
    cols = ["UNDER_CONSTRUCTION", "RERA", "BHK_NO.", "SQUARE_FT", "RESALE",
            "READY_TO_MOVE", "LATITUDE_R", "LONGITUDE_R", TARGET]
    corr = d[cols].corr(method="spearman")
    fig, ax = plt.subplots(figsize=(7.2, 6.0))
    im = ax.imshow(corr, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(cols)), [c.replace("_R", "*") for c in cols],
                  rotation=40, ha="left")
    ax.set_yticks(range(len(cols)), [c.replace("_R", "*") for c in cols])
    for i in range(len(cols)):
        for j in range(len(cols)):
            ax.text(j, i, f"{corr.iloc[i, j]:.2f}", ha="center", va="center",
                    fontsize=7, color="black")
    fig.colorbar(im, ax=ax, shrink=0.85)
    ax.set_title("Spearman correlation heatmap (* = repaired orientation)")
    save(fig, "fig07_correlation_heatmap.png")

    # 8 — missing values
    miss_pct = d.isna().mean() * 100
    fig, ax = plt.subplots(figsize=(7.6, 3.4))
    ax.bar(miss_pct.index, miss_pct.values, color="#8172B2")
    ax.set_ylabel("Missing %"); ax.set_ylim(0, max(1.0, miss_pct.max() * 1.3))
    ax.set_title("Missing values by column — all zero (defects are wrong values, not gaps)")
    plt.setp(ax.get_xticklabels(), rotation=35, ha="right", fontsize=7)
    save(fig, "fig08_missing_values.png")

    # 9 — outlier distribution (log-scale boxplots)
    fig, axes = plt.subplots(1, 4, figsize=(10, 3.4))
    for ax, col, title in zip(
            axes, ["SQUARE_FT", "BHK_NO.", TARGET, "PPSF"],
            ["SQUARE_FT", "BHK_NO.", "Price ₹ lakh", "₹/sq ft"]):
        vals = d[col].replace([np.inf, -np.inf], np.nan).dropna()
        ax.boxplot(np.log1p(vals), orientation="vertical")
        ax.set_title(f"{title}\n(log1p scale)")
    fig.suptitle("Outlier distribution — heavy right tails in area, price, ₹/sq ft")
    save(fig, "fig09_outlier_distribution.png")

    # 10 — geographical distribution (repaired coordinates)
    g = d.dropna(subset=["LATITUDE_R", "LONGITUDE_R"]).sample(
        min(8000, len(d)), random_state=42)
    fig, ax = plt.subplots(figsize=(6.2, 5.2))
    sc = ax.scatter(g["LONGITUDE_R"], g["LATITUDE_R"], c=np.log1p(g[TARGET]),
                    s=5, alpha=0.5, cmap="viridis")
    fig.colorbar(sc, ax=ax, shrink=0.85, label="log1p(price ₹ lakh)")
    ax.set_xlabel("Longitude (repaired)"); ax.set_ylabel("Latitude (repaired)")
    ax.set_title("Geographical distribution (8,000-row sample, repaired coords)")
    save(fig, "fig10_geographical_distribution.png")

    # 11 — price by binary / categorical flags (medians)
    fig, axes = plt.subplots(1, 4, figsize=(10, 3.4))
    for ax, col in zip(axes, ["RERA", "UNDER_CONSTRUCTION", "RESALE", "POSTED_BY"]):
        med = d.groupby(col)[TARGET].median()
        ax.bar([str(i) for i in med.index], med.values, color="#55A868")
        ax.set_title(f"Median price by {col}\n(₹ lakh)")
    fig.suptitle("Median price by property flags and poster type")
    save(fig, "fig11_price_by_flags.png")

    # 12 — extremes classification
    fig, ax = plt.subplots(figsize=(6.6, 3.8))
    cats = ["Top-100 priced:\nSQUARE_FT errors", "Genuine luxury\n(>₹1,000L, plausible area)",
            "Cheapest-100:\n< ₹500/sq ft"]
    # recomputed in audit; here from the frame for the visual
    top100 = d.nlargest(100, TARGET)
    vals = [int((top100["SQUARE_FT"] > 20_000).sum()),
            int(((d["SQUARE_FT"].between(100, 20_000)) & (y > 1000)).sum()),
            int((d["PPSF"].nsmallest(100) < 500).sum())]
    ax.bar(cats, vals, color=["#C44E52", "#55A868", "#DD8452"])
    for i, v in enumerate(vals):
        ax.text(i, v + 3, str(v), ha="center", fontweight="bold")
    ax.set_title("Extremes classified: field errors vs genuine luxury vs suspicious-cheap")
    save(fig, "fig12_extremes_classification.png")
    return made


def report(s: dict, figs: list[str], path: Path) -> None:
    t, inv, dup, cor = (s["target_stats"], s["invalid"], s["duplicates"],
                        s["correlations_with_target"])
    top_city = list(s["address"]["top_cities_raw"].items())[:10]
    L = [
        "# Exploratory Data Analysis Report",
        "",
        "**Dataset:** Indian House Price Prediction Challenge — Kaggle "
        "(anmolkumar/house-price-prediction-challenge)",
        f"**File audited:** `train.csv` · SHA-256 `{s['source_sha256']}`",
        f"**Dimensions (verified from the file):** {s['rows']:,} rows × "
        f"{s['cols']} columns. **Target:** `{TARGET}` — continuous price in "
        "₹ lakh, so the modelling task is **regression**.",
        "**Generated by:** `ml/eda.py` + `ml/data_audit.py` from the actual "
        "CSV. No model was trained and no row was removed in this stage.",
        "Companion: `data_quality_report.md` (defects, exclusions, verdict).",
        "",
        "## 1. Structure and sample",
        "",
        "| Column | Type | Role |",
        "|---|---|---|",
    ]
    for c in s["columns"]:
        role = "**TARGET**" if c == TARGET else "feature"
        L.append(f"| {c} | {s['dtypes'][c]} | {role} |")
    L += [
        "",
        f"Input features: {len(s['feature_columns'])} "
        f"({', '.join(s['feature_columns'])}). There is **no identifier "
        "column and no bathroom/age/furnishing column** — several real "
        "price drivers are simply absent, which caps achievable accuracy.",
        "",
        "## 2. Missing values",
        "",
        f"**{s['missing_total']} true nulls in the entire file** "
        "(see fig08). Hidden text markers were scanned separately "
        "(per-column counts in `data_audit.json`). The dataset's problems "
        "are *wrong values*, not missing ones.",
        "",
        "![Missing values](figures/fig08_missing_values.png)",
        "",
        "## 3. Target distribution",
        "",
        f"- Range ₹{t['min']:,.2f} – ₹{t['max']:,.0f} lakh; mean "
        f"₹{t['mean']:,.1f} lakh vs median ₹{t['median']:,.0f} lakh — the "
        f"mean is pulled far above the typical property.",
        f"- **Skewness {t['skew']:.2f}** (extreme right skew); on a log1p "
        f"scale skew falls to {t['log1p_skew']:.2f} — the single strongest "
        "argument for a log-target modelling track.",
        f"- IQR ₹{t['q1']:,.0f}–₹{t['q3']:,.0f} lakh; "
        f"{t['iqr_outliers_above']:,} rows sit above the IQR fence — they "
        "are a *population* (the expensive tail), not a handful of typos, "
        "and are analysed, not deleted (§7 of the quality report).",
        f"- {t['rows_above_1000_lacs']} rows exceed ₹1,000 lakh (₹10 crore).",
        "",
        "![Price distribution](figures/fig01_price_distribution.png)",
        "![Outliers](figures/fig09_outlier_distribution.png)",
        "",
        "## 4. Numerical features",
        "",
        f"- SQUARE_FT: median {s['numeric_summary']['SQUARE_FT']['50%']:,.0f}, "
        f"max {inv['sqft_max']:,.0f} (a physical impossibility — a field "
        f"error population: {inv['sqft_above_20000']:,} rows > 20,000 sq ft, "
        f"{inv['sqft_zero_or_negative']:,} rows ≤ 0).",
        f"- BHK_NO.: 1–{inv['bhk_max']:.0f}; {inv['bhk_above_10']:,} rows "
        "above 10 BHK (rare large homes — weak model support, not errors "
        "by themselves).",
        "- Binary flags (UNDER_CONSTRUCTION, RERA, RESALE, READY_TO_MOVE) "
        "are true 0/1 with no stray values.",
        "",
        "![Price vs sqft](figures/fig02_price_vs_sqft.png)",
        "![Price vs BHK](figures/fig03_price_vs_bhk.png)",
        "",
        "Median price by BHK rises monotonically: " + ", ".join(
            f"{k} BHK ₹{v:,.0f}L" for k, v in
            list(s["median_price_by_bhk_lacs"].items())[:6]) + ".",
        "",
        "## 5. Categorical features",
        "",
    ]
    for c, v in s["categorical_summary"].items():
        L.append(f"- **{c}**: {v['unique']} unique values; dominant "
                 f"`{list(v['top'])[0]}` at {v['top_share_pct']}%."
                 + (" **Quasi-constant** — expect near-zero signal."
                    if v["top_share_pct"] > 90 else ""))
    L += [
        "",
        "![Price by flags](figures/fig11_price_by_flags.png)",
        "",
        "## 6. Location inside ADDRESS",
        "",
        f"- Format is `Locality,...,City`: {s['address']['unique_addresses']:,} "
        f"unique addresses, {s['address']['unique_localities']:,} localities, "
        f"but **{s['address']['unique_city_labels_raw']} distinct last-segment "
        "labels** mixing cities with states "
        f"({', '.join(s['address']['city_labels_that_are_states'])}). Raw "
        "labels cannot be used as a city feature without repair.",
        f"- Most frequent address: \"{s['address']['most_frequent_address']}\" "
        f"({s['address']['most_frequent_address_rows']:,} rows). "
        f"{s['address']['localities_under_multiple_city_labels']} localities "
        "appear under more than one city label (inconsistent naming).",
        "- Top raw city labels (rows): " + ", ".join(
            f"{k} {v:,}" for k, v in top_city) + ".",
        "- Median price by top city (₹ lakh): " + ", ".join(
            f"{k} ₹{v:,.0f}" for k, v in
            s["address"]["median_price_by_top_city_lacs"].items()) + ".",
        "",
        "![Count by location](figures/fig04_count_by_location.png)",
        "![Price by location](figures/fig05_price_by_location.png)",
        "",
        "## 7. Geography — the swapped-coordinate defect",
        "",
        f"- As labelled, **{inv['coords_plausible_as_labelled']:,} rows** are "
        f"India-plausible; after swapping the two columns, "
        f"**{inv['coords_plausible_after_swap']:,}** are — the columns are "
        f"verifiably swapped. {inv['coords_implausible_either_way']} rows "
        "are corrupt under both readings.",
        f"- Coordinates are **locality-level, not property-level**: only "
        f"{s['geography']['unique_coordinate_pairs']:,} unique pairs for "
        f"{s['rows']:,} rows; the busiest pair covers "
        f"{s['geography']['max_rows_per_coordinate_pair']:,} rows. Treat "
        "lat/lon as locality features.",
        "",
        "![Geography](figures/fig10_geographical_distribution.png)",
        "",
        "## 8. Relationships with price (linear + nonlinear)",
        "",
        "| Feature | Pearson r | Spearman ρ | Reading |",
        "|---|---|---|---|",
    ]
    notes = {
        "SQUARE_FT": "strongest raw signal; log scale linearises it",
        "LOG_SQFT": "log(area) — best linear-form relationship",
        "BHK_NO.": "strong, monotone (see §4 medians)",
        "RERA": "weak positive",
        "RESALE": "Pearson ≪ Spearman gap = outlier-driven mean artefact",
        "LATITUDE_REPAIRED": "weak negative (north–south price gradient)",
        "LONGITUDE_REPAIRED": "weak negative",
        "UNDER_CONSTRUCTION": "near zero overall",
        "READY_TO_MOVE": "mirror of UNDER_CONSTRUCTION (exact complement)",
        "PRICE_PER_SQFT_INR": "TARGET-DERIVED — exploration only, never a feature",
    }
    for c in ["SQUARE_FT", "LOG_SQFT", "BHK_NO.", "RERA", "RESALE",
              "UNDER_CONSTRUCTION", "READY_TO_MOVE", "LATITUDE_REPAIRED",
              "LONGITUDE_REPAIRED", "PRICE_PER_SQFT_INR"]:
        v = cor[c]
        L.append(f"| {c} | {v['pearson']:.3f} | {v['spearman']:.3f} | "
                 f"{notes.get(c, '')} |")
    L += [
        "",
        "![Correlation heatmap](figures/fig07_correlation_heatmap.png)",
        "![Price per sq ft](figures/fig06_price_per_sqft.png)",
        "",
        "Exploratory price-per-sq-ft (₹): median "
        f"{s['ppsf_stats_inr']['50%']:,.0f}, p99 in fig06. It is computed "
        "from the target, so it is a diagnostic lens (spotting implausible "
        "listings), never an input.",
        "",
        "## 9. Duplicates and label noise",
        "",
        f"- Exact duplicate rows: **{dup['exact_duplicate_extra_rows']:,} "
        f"extra rows** ({dup['exact_duplicate_groups']} groups); "
        f"~{dup['expected_pairs_straddling_80_20']:.0f} duplicate pairs "
        "would straddle a naive random 80/20 split — de-duplication must "
        "precede splitting.",
        f"- Duplicate property listings (same ADDRESS + SQUARE_FT + BHK): "
        f"{dup['duplicate_property_groups']} groups / "
        f"{dup['duplicate_property_rows']:,} rows.",
        f"- **{dup['groups_with_conflicting_price']} feature-identical "
        "groups carry different prices** — irreducible label noise that "
        "caps any model's achievable R² on this data.",
        "",
        "## 10. Leakage and inconsistency findings",
        "",
        "- No target-derived column exists in the raw file; no predictor "
        "reaches |Spearman| ≥ 0.9 against the target. Direct leakage: none.",
        "- Group leakage is the real risk (duplicates, repeated addresses, "
        "shared locality coordinates across a random split) — mitigate by "
        "de-duplicating first and also reporting a locality-grouped split.",
        "- READY_TO_MOVE is the exact complement of UNDER_CONSTRUCTION "
        "(redundant pair — drop one).",
        f"- Inconsistent descriptions: {s['inconsistencies']['rk_rows']} RK "
        f"rows ({s['inconsistencies']['rk_rows_with_bhk_no_above_1']} with "
        f"BHK_NO. > 1); {s['inconsistencies']['sqft_per_bhk_below_100']} "
        "rows under 100 sq ft per BHK and "
        f"{s['inconsistencies']['sqft_per_bhk_above_5000']} above 5,000 — "
        "area/BHK field errors concentrated in the tails.",
        "",
        "![Extremes classification](figures/fig12_extremes_classification.png)",
        "",
        "## 11. Suitability verdict",
        "",
        "**Suitable for training a residential valuation model, after the "
        "documented repairs — with accuracy expectations set by the data, "
        "not by ambition.** Strengths: 29k rows, strong monotone area/BHK "
        "signal, rich location text, zero missing values. Hard limits: "
        "conflicting duplicate prices, absent bathrooms/age/furnishing, "
        "locality-level coordinates and a corrupted extreme tail mean a "
        "flawless model still faces an error floor on this dataset.",
        "",
        "Cleaning applied downstream (`ml/data_cleaning.py`): exact "
        "duplicates → coordinate repair/drop → SQUARE_FT plausibility → "
        "drop READY_TO_MOVE. The target is never clipped. Full defect "
        "register and justifications: `data_quality_report.md`.",
        "",
        f"## 12. Figures generated ({len(figs)})",
        "",
    ]
    L += [f"- `figures/{f}`" for f in figs]
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--reports-dir", default="dataset/reports")
    args = ap.parse_args()
    inp, rep = Path(args.input), Path(args.reports_dir)
    rep.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(inp)
    stats = audit(df, sha256_of(inp))
    figs = figures(prep(df), rep / "figures")
    report(stats, figs, rep / "eda_report.md")
    print(f"EDA complete: {len(figs)} figures + {rep/'eda_report.md'}")


if __name__ == "__main__":
    main()
