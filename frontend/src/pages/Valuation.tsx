import { useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { BadgeCheck, BrainCircuit, Coins, ShieldAlert } from "lucide-react";
import PropertyForm from "../components/PropertyForm";
import { riskService, valuationService } from "../api/services";
import { useAsync } from "../hooks/useAsync";
import type { PropertyFeatures, RiskData, ValuationData } from "../types/api";
import { Card, CardHeader, ErrorState, PageHeader } from "../components/ui";
import { CountUp } from "../components/motion";
import { fmtDateTime, fmtLacs } from "../utils/format";
import { loadLastProperty, saveLastProperty } from "../utils/storage";

export default function Valuation() {
  const [result, setResult] = useState<ValuationData | null>(null);
  const [risk, setRisk] = useState<RiskData | null>(null);
  const predict = useAsync(
    async (features: PropertyFeatures) => valuationService.predict(features),
  );

  const onSubmit = async (features: PropertyFeatures) => {
    saveLastProperty(features);
    setRisk(null);
    const out = await predict.run(features);
    setResult(out);
    if (out) {
      // Calibrated uncertainty for this price band comes from the risk API.
      riskService
        .assess(features, out.predicted_price_lacs)
        .then(setRisk)
        .catch(() => setRisk(null));
    }
  };

  return (
    <div>
      <PageHeader
        eyebrow="01 · ML Valuation"
        title="Property Valuation"
        description="Enter the property's model features. The estimate is produced by the served XGBoost model through the Flask API — nothing is simulated in the browser."
      />
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader
            title="Property features"
            subtitle="Prefilled with a sample Bengaluru listing — edit any field"
          />
          <div className="px-5 py-5">
            <PropertyForm
              initial={loadLastProperty()}
              onSubmit={onSubmit}
              submitting={predict.loading}
              submitLabel="Estimate price"
            />
          </div>
        </Card>

        <div className="space-y-4">
          <Card className={result ? "ring-conic" : ""}>
            <CardHeader title="Valuation result" subtitle="From POST /api/valuation/predict" />
            <div className="px-5 py-5">
              {predict.error && <ErrorState message={predict.error} />}
              {!predict.error && !result && (
                <p className="text-sm leading-relaxed text-slate-400">
                  Submit the form to receive the model's estimate, its
                  calibrated uncertainty for the price band, and links to the
                  full explanation, risk and tokenisation views.
                </p>
              )}
              {result && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
                >
                  <p className="eyebrow text-slate-400">Estimated price</p>
                  <p className="num mt-2 bg-gradient-to-r from-slate-50 via-accent-400 to-teal-450 bg-clip-text text-[42px] font-bold leading-none tracking-tight text-transparent">
                    <CountUp
                      value={result.predicted_price_lacs}
                      format={fmtLacs}
                      duration={1.2}
                    />
                  </p>
                  <dl className="mt-4 space-y-2 text-sm">
                    <div className="flex justify-between">
                      <dt className="text-slate-400">Model</dt>
                      <dd className="text-slate-100">{result.model_id}</dd>
                    </div>
                    <div className="flex justify-between">
                      <dt className="text-slate-400">Predicted at</dt>
                      <dd className="text-slate-100">{fmtDateTime(result.timestamp)}</dd>
                    </div>
                    <div className="flex justify-between">
                      <dt className="text-slate-400">Request ID</dt>
                      <dd className="max-w-[140px] truncate text-slate-100">
                        {result.request_id}
                      </dd>
                    </div>
                    <div className="flex items-center justify-between">
                      <dt className="text-slate-400">History</dt>
                      <dd className="flex items-center gap-1.5 text-slate-100">
                        {result.history_saved ? (
                          <>
                            <BadgeCheck className="h-4 w-4 text-emerald-400" />
                            Saved
                          </>
                        ) : (
                          "Not saved (database unavailable)"
                        )}
                      </dd>
                    </div>
                  </dl>
                  {risk?.uncertainty && (
                    <div className="mt-4 rounded-lg border border-line bg-ink-850 px-4 py-3">
                      <p className="text-xs font-medium text-slate-300">
                        Calibrated prediction uncertainty
                      </p>
                      <p className="mt-1 text-xs leading-relaxed text-slate-400">
                        For properties in this predicted price band, 80% of the
                        served model's held-out test errors were within{" "}
                        <span className="font-medium text-slate-200">
                          ±{risk.uncertainty.calibrated_ape_p80_pct.toFixed(1)}%
                        </span>{" "}
                        (calibrated on {risk.uncertainty.calibration_n} untouched
                        test properties).
                      </p>
                    </div>
                  )}
                  <div className="mt-5 grid grid-cols-1 gap-2">
                    <Link
                      to="/explainability"
                      className="group flex items-center gap-2 rounded-lg border border-line px-3 py-2.5 text-sm text-slate-200 transition hover:border-accent-500/50 hover:bg-ink-800"
                    >
                      <BrainCircuit className="h-4 w-4 text-accent-400 transition-transform duration-300 group-hover:scale-110" />
                      Explain this valuation (SHAP)
                      <span className="ml-auto text-slate-500 transition-transform duration-300 group-hover:translate-x-1">→</span>
                    </Link>
                    <Link
                      to="/risk"
                      className="group flex items-center gap-2 rounded-lg border border-line px-3 py-2.5 text-sm text-slate-200 transition hover:border-amber-500/50 hover:bg-ink-800"
                    >
                      <ShieldAlert className="h-4 w-4 text-amber-400 transition-transform duration-300 group-hover:scale-110" />
                      Assess property risk
                      <span className="ml-auto text-slate-500 transition-transform duration-300 group-hover:translate-x-1">→</span>
                    </Link>
                    <Link
                      to="/tokenisation"
                      className="group flex items-center gap-2 rounded-lg border border-line px-3 py-2.5 text-sm text-slate-200 transition hover:border-teal-500/50 hover:bg-ink-800"
                    >
                      <Coins className="h-4 w-4 text-teal-400 transition-transform duration-300 group-hover:scale-110" />
                      Calculate token supply
                      <span className="ml-auto text-slate-500 transition-transform duration-300 group-hover:translate-x-1">→</span>
                    </Link>
                  </div>
                </motion.div>
              )}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
