import { api } from "./client";
import type {
  ChainPropertiesData,
  ChainRecord,
  ChainStatusData,
  CompareData,
  ExplanationData,
  HealthData,
  HistoryData,
  ModelMetricsData,
  PropertyFeatures,
  RiskData,
  SchemaData,
  ShapSummaryData,
  SummaryData,
  TokenData,
  ValuationData,
} from "../types/api";

export const healthService = {
  get: () => api.get<HealthData>("/api/health"),
};

export const valuationService = {
  predict: (property: PropertyFeatures) =>
    api.post<ValuationData>("/api/valuation/predict", { property }),
  explain: (property: PropertyFeatures) =>
    api.post<ExplanationData>("/api/valuation/explain", { property }),
};

export const riskService = {
  assess: (property: PropertyFeatures, predictedPriceLacs?: number) =>
    api.post<RiskData>("/api/risk/assess", {
      property,
      ...(predictedPriceLacs != null
        ? { predicted_price_lacs: predictedPriceLacs }
        : {}),
    }),
};

export const tokenService = {
  calculateFromValuation: (valuationLacs: number) =>
    api.post<TokenData>("/api/token/calculate", { valuation_lacs: valuationLacs }),
  calculateFromProperty: (property: PropertyFeatures) =>
    api.post<TokenData>("/api/token/calculate", { property }),
};

export const modelService = {
  metrics: () => api.get<ModelMetricsData>("/api/models/metrics"),
  compare: () => api.get<CompareData>("/api/models/compare"),
  schema: () => api.get<SchemaData>("/api/models/schema"),
  shapSummary: () => api.get<ShapSummaryData>("/api/models/shap-summary"),
};

export const chainService = {
  status: () => api.get<ChainStatusData>("/api/chain/status"),
  register: (property: PropertyFeatures) =>
    api.post<ChainRecord>("/api/chain/register", { property }),
  mint: (chainPropertyId: number) =>
    api.post<ChainRecord>("/api/chain/mint", {
      chain_property_id: chainPropertyId,
    }),
  properties: () => api.get<ChainPropertiesData>("/api/chain/properties"),
};

export const dashboardService = {
  summary: () => api.get<SummaryData>("/api/dashboard/summary"),
  history: (page = 1, pageSize = 20) =>
    api.get<HistoryData>(`/api/dashboard/history?page=${page}&page_size=${pageSize}`),
};
