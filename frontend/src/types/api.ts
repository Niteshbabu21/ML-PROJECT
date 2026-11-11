/* API types — mirror the Flask backend's response envelopes exactly. */

export interface Envelope<T> {
  success: boolean;
  request_id: string;
  timestamp: string;
  data: T;
}

export interface ApiErrorBody {
  success: false;
  request_id: string;
  timestamp: string;
  error: { code: string; message: string };
}

/** The 20 model-ready features (backend/ml/feature_schema.json order). */
export interface PropertyFeatures {
  POSTED_BY: string;
  UNDER_CONSTRUCTION: number;
  RERA: number;
  "BHK_NO.": number;
  BHK_OR_RK: string;
  SQUARE_FT: number;
  RESALE: number;
  CITY: string;
  LOCALITY: string;
  LATITUDE: number;
  LONGITUDE: number;
  SQUARE_FT_PER_BHK: number;
  LOG_SQUARE_FT: number;
  DIST_TO_CITY_CENTROID: number | null;
  CITY_FREQ: number;
  LOCALITY_FREQ: number;
  SQFT_BAND: string;
  BHK_CONFIG: string;
  GEO_CLUSTER: string;
  LAT_LON_INTERACTION: number;
}

export interface ValuationData {
  request_id: string;
  property: PropertyFeatures;
  predicted_price_lacs: number;
  currency: string;
  model_id: string;
  model_name: string;
  timestamp: string;
  history_saved: boolean;
}

export interface Contribution {
  feature: string;
  value: unknown;
  shap_log: number;
  price_factor: number;
  direction: "increases_price" | "decreases_price" | "neutral";
}

export interface ExplanationData {
  request_id: string;
  property: PropertyFeatures;
  prediction: {
    predicted_price_lacs: number;
    currency: string;
    model_id: string;
    model_name: string;
  };
  base_value_log: number;
  baseline_price_lacs: number;
  model_output_log: number;
  contributions: Contribution[];
  top_influential: Contribution[];
  top_positive: Contribution[];
  top_negative: Contribution[];
  additivity: {
    base_plus_contributions_log: number;
    model_output_log: number;
    abs_error: number;
    tolerance: number;
    verified: boolean;
  };
  explanation: string;
  history_saved: boolean;
}

export interface RiskFactor {
  id: string;
  name: string;
  domain: string;
  score: number;
  max_score: number;
  status: string;
  detail: string;
  explanation: string;
  recommended_action: string;
}

export interface RiskData {
  request_id: string;
  property: PropertyFeatures;
  predicted_price_lacs: number | null;
  predicted_price_source: string;
  risk_score: number;
  risk_category: "LOW" | "MEDIUM" | "HIGH";
  domains: Record<string, { score: number; max_score: number }>;
  factors: RiskFactor[];
  warnings: string[];
  recommended_actions: string[];
  uncertainty: {
    predicted_price_band_lacs: [number, number | null];
    calibrated_ape_p80_pct: number;
    calibration_n: number;
  } | null;
  narrative: string;
  methodology: { version: string; bands: Record<string, string>; disclaimer: string };
}

export interface TokenData {
  request_id: string;
  valuation_lacs: number;
  valuation_inr: number;
  valuation_source: string;
  currency: string;
  token_denomination_inr: number;
  token_supply: number;
  exact_token_amount: number;
  rounding: { method: string; remainder_inr: number; note: string };
  prototype_note: string;
}

export interface ModelMetricsData {
  model_id: string;
  model_name: string;
  hyperparameters: Record<string, number>;
  training: Record<string, string>;
  metrics: {
    validation: { r2: number; mae_lacs: number; rmse_lacs: number; note: string };
    grouped_cv: { r2_mean: number; r2_std: number; folds_r2: number[]; note: string };
    test: {
      r2: number; mae_lacs: number; mse: number; rmse_lacs: number;
      mape_pct: number; smape_pct: number; explained_variance: number;
      median_ae_lacs: number; n: number; note: string;
    };
  };
  environment: Record<string, string>;
  provenance: Record<string, string>;
}

export interface CompareEntry {
  model: string;
  stage: string;
  tuned?: boolean;
  validation_r2?: number;
  validation_mae_lacs?: number;
  validation_rmse_lacs?: number;
  validation_mape_pct?: number;
  baseline_train_time_s?: number;
  cv_r2_mean?: number;
  cv_r2_std?: number;
  test_r2?: number;
  test_mae_lacs?: number;
  test_rmse_lacs?: number;
  selected: boolean;
}

export interface CompareData {
  served_model_id: string;
  comparison: CompareEntry[];
  note: string;
}

export interface HistoryItem {
  request_id: string;
  timestamp: string;
  endpoint: string;
  property: PropertyFeatures;
  predicted_price_lacs: number;
  currency: string;
  model_id: string;
}

export interface HistoryData {
  items: HistoryItem[];
  pagination: { page: number; page_size: number; total: number; pages: number };
}

export interface SummaryData {
  total_valuations: number;
  average_price_lacs: number | null;
  min_price_lacs: number | null;
  max_price_lacs: number | null;
  database_connected: boolean;
  model_id: string;
  model_name: string;
  model_loaded: boolean;
  generated_at: string;
}

export interface HealthData {
  status: string;
  model_loaded: boolean;
  model_id: string;
  model_name: string;
  model_load_error: string | null;
  database_connected: boolean;
  timestamp: string;
  api_version: string;
}

export interface SchemaFeature {
  position: number;
  name: string;
  kind: string;
  origin: string;
  required: boolean;
  known_levels?: string[];
  unseen_levels?: string;
  nullable?: boolean;
}

export interface SchemaData {
  schema_version: string;
  feature_order: string[];
  features: SchemaFeature[];
  target: {
    name: string; unit: string; transform: string;
    inverse_transform: string; log_clip_upper: number;
  };
  input_contract_note: string;
}

export interface ChainStatusData {
  rpc_url: string;
  connected: boolean;
  contract_address: string | null;
  chain_id: number | null;
  block_number: number | null;
  admin_address: string | null;
  network: string | null;
  connect_error: string | null;
}

export interface ChainRecord {
  property_ref: string;
  chain_property_id: number;
  valuation_inr: number;
  valuation_lacs?: number;
  risk_score: number;
  risk_category: string;
  token_supply: number;
  residual_inr: number;
  register_tx: string;
  register_block: number;
  mint_tx: string | null;
  mint_block?: number;
  status: string;
  admin_address: string;
  created_at: string;
  updated_at: string;
  record_saved?: boolean;
  contract_inventory?: number;
  available_supply?: number | null;
}

export interface ChainPropertiesData {
  connected: boolean;
  properties: ChainRecord[];
}

export interface ShapSummaryData {
  base_value_log: number;
  baseline_price_lacs: number;
  sample_size: number;
  ranking: { feature: string; mean_abs_shap_log: number }[];
  provenance: string;
}
