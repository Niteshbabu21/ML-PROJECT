# Feature Dictionary

Every feature in the model-ready dataset and the encoded pipelines. `Fitted` = the statistic is learned from the training split only. Target-derived features are prohibited.

| Feature | Type | Source | Fitted? | Purpose |
|---|---|---|---|---|
| POSTED_BY | categorical | cleaned column, whitespace/case-normalised | no (normalisation is a fixed map) | Listing source (Owner/Dealer/Builder) — channel effects on asking price |
| UNDER_CONSTRUCTION | binary | cleaned column | no | Construction status; also carries READY_TO_MOVE information (exact complement) |
| RERA | binary | cleaned column | no | RERA registration status — regulatory/trust signal; also a risk-score input downstream |
| BHK_NO. | numeric | cleaned column | no | Bedroom count — strong monotone price relationship (Spearman ~0.50) |
| BHK_OR_RK | categorical | cleaned column, normalised | no | Configuration type (BHK vs RK). Quasi-constant (99.9% BHK) — flagged in selection |
| SQUARE_FT | numeric | cleaned column (plausibility-filtered 100–20,000 in cleaning) | no | Property area — strongest single price signal (Spearman ~0.57) |
| RESALE | binary | cleaned column | no | Resale vs new listing status |
| CITY | categorical | derived from ADDRESS last segment; state label repaired (Maharashtra→Mumbai), corrupt label (Lalitpur) reassigned by nearest fitted centroid, rare cities grouped to Other | YES — centroids and kept-city list from training split only | City-level market effect; grouping keeps cardinality bounded and unseen cities safe |
| LOCALITY | categorical | derived from ADDRESS first segment | YES — one-hot min_frequency=25 / native fallback, training split only | Micro-market effect — the strongest location granularity available; high cardinality handled by frequency grouping |
| LATITUDE | numeric | cleaned column (already repaired from the raw swap); invalid values at transform time replaced by fitted city centroid | fallback only | Geographic position (locality-level granularity — EDA finding) |
| LONGITUDE | numeric | cleaned column (already repaired); same fallback as LATITUDE | fallback only | Geographic position (locality-level) |
| SQUARE_FT_PER_BHK | numeric | derived: SQUARE_FT / BHK_NO. from prediction-time inputs | no | Spaciousness per bedroom — separates large-family homes from luxury area |
| LOG_SQUARE_FT | numeric | derived: log1p(SQUARE_FT) | no | Linearises the area–price relationship (log-area Pearson ~0.60 vs 0.57 Spearman raw) |
| DIST_TO_CITY_CENTROID | numeric | derived: Euclidean degrees from the property's coordinates to its CITY centroid | YES — centroids from training split only | Centrality within the city — prime vs peripheral location proxy |
| CITY_FREQ | numeric | derived: training-row count of the (grouped) CITY | YES — training split only | Market thickness per city; unseen city = 0 |
| LOCALITY_FREQ | numeric | derived: training-row count of the LOCALITY | YES — training split only | Evidence strength for the locality estimate; unseen locality = 0 (a confidence signal, not a price signal) |
| LAT_LON_INTERACTION | numeric | derived: LATITUDE × LONGITUDE | no | EXPERIMENTAL — diagonal geographic gradient for linear models; retained for training-stage ablation |
| SQFT_BAND | categorical | derived: fixed domain bands XS<600, S 600–1000, M 1000–1500, L 1500–2500, XL>2500 sq ft | no (fixed cut points) | Size segment — lets models price size tiers non-linearly and aids interpretability |
| BHK_CONFIG | categorical | derived: BHK_NO. + BHK_OR_RK, e.g. '3BHK', '1RK' | no | Configuration identity as a single category (captures RK vs BHK at the same bedroom count) |
| GEO_CLUSTER | categorical | derived: KMeans cluster id (k=32) of (LATITUDE, LONGITUDE) | YES — KMeans fitted on training coordinates only | EXPERIMENTAL — data-driven geographic neighbourhoods that cross administrative city boundaries; retained for training-stage ablation |

## Excluded by design

- **PRICE_PER_SQFT** — Target-derived (price ÷ area). EDA diagnostic only; using it as an input would be direct leakage.
- **READY_TO_MOVE** — Exact complement of UNDER_CONSTRUCTION in 100% of rows (EDA-verified). Its information is fully preserved by UNDER_CONSTRUCTION; keeping both adds pure collinearity, especially for linear models.
- **ADDRESS (raw)** — Free text identifier-like field; its usable content is extracted as LOCALITY + CITY inside the pipeline. Raw text would memorise listings and cannot generalise.
- **Target encoding of CITY/LOCALITY** — Would require out-of-fold fitting discipline and risks leakage; frequency counts + one-hot/native handling provide the location signal safely.
- **Target clipping / winsorising** — The expensive tail contains genuine luxury properties (EDA §Q6). Skew is handled by the log1p target transform, not by deleting or capping prices.
