import { AlertTriangle, ClipboardList } from "lucide-react";
import PropertyForm from "../components/PropertyForm";
import RiskGauge from "../components/RiskGauge";
import { riskService } from "../api/services";
import { useAsync } from "../hooks/useAsync";
import type { PropertyFeatures } from "../types/api";
import {
  Card,
  CardHeader,
  ErrorState,
  PageHeader,
  RiskBadge,
} from "../components/ui";
import { SpringBar } from "../components/motion";
import { fmtLacs } from "../utils/format";
import { loadLastProperty, saveLastProperty } from "../utils/storage";

const DOMAIN_LABELS: Record<string, string> = {
  regulatory_construction: "Regulatory & construction",
  data_quality: "Data quality",
  model_uncertainty: "Model uncertainty",
};

export default function RiskAssessment() {
  const assess = useAsync(async (f: PropertyFeatures) => riskService.assess(f));
  const data = assess.data;

  const onSubmit = async (features: PropertyFeatures) => {
    saveLastProperty(features);
    await assess.run(features);
  };

  return (
    <div>
      <PageHeader
        eyebrow="03 · Risk Engine"
        title="Property Risk Assessment"
        description="A documented academic-prototype methodology (v1.0.0) over measurable listing-data indicators — not a legal due-diligence service or a validated investment-risk model. Missing RERA information is never treated as proof of non-compliance."
      />
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader title="Assess a property" subtitle="POST /api/risk/assess — the price is computed by the valuation model when not supplied" />
          <div className="px-5 py-5">
            <PropertyForm
              initial={loadLastProperty()}
              onSubmit={onSubmit}
              submitting={assess.loading}
              submitLabel="Assess risk"
            />
            {assess.error && (
              <div className="mt-4">
                <ErrorState message={assess.error} />
              </div>
            )}
          </div>
        </Card>

        <Card>
          <CardHeader title="Overall risk" subtitle="Normalised to 0–100" />
          <div className="px-5 py-5">
            {!data && (
              <p className="text-sm leading-relaxed text-slate-400">
                Submit the form to receive the overall score, category,
                factor-by-factor breakdown and recommended verification
                actions.
              </p>
            )}
            {data && (
              <div>
                <RiskGauge score={data.risk_score} />
                <div className="mt-3 flex items-center justify-center gap-2">
                  <RiskBadge category={data.risk_category} />
                  <span className="text-xs text-slate-400">
                    price basis: {data.predicted_price_source === "provided" ? "provided" : "model-computed"} ·{" "}
                    {fmtLacs(data.predicted_price_lacs)}
                  </span>
                </div>
                <div className="mt-5 space-y-3">
                  {Object.entries(data.domains).map(([key, d]) => (
                    <div key={key}>
                      <div className="flex justify-between text-xs">
                        <span className="text-slate-400">{DOMAIN_LABELS[key] ?? key}</span>
                        <span className="text-slate-200">
                          {d.score.toFixed(1)} / {d.max_score}
                        </span>
                      </div>
                      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-ink-700/60">
                        <SpringBar pct={(d.score / d.max_score) * 100} className="bg-accent-400" />
                      </div>
                    </div>
                  ))}
                </div>
                {data.uncertainty && (
                  <p className="mt-4 text-xs leading-relaxed text-slate-400">
                    Uncertainty calibration: for the{" "}
                    {fmtLacs(data.uncertainty.predicted_price_band_lacs[0])}
                    {data.uncertainty.predicted_price_band_lacs[1] != null
                      ? ` – ${fmtLacs(data.uncertainty.predicted_price_band_lacs[1])}`
                      : "+"}{" "}
                    band, the model's 80th-percentile absolute error on its
                    held-out test set was{" "}
                    {data.uncertainty.calibrated_ape_p80_pct.toFixed(1)}%.
                  </p>
                )}
              </div>
            )}
          </div>
        </Card>
      </div>

      {data && (
        <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-3">
          <Card className="xl:col-span-2">
            <CardHeader title="Factor breakdown" subtitle="Each factor's score, basis and explanation" />
            <div className="divide-y divide-line/50">
              {data.factors.map((f) => (
                <div key={f.id} className="px-5 py-4">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-medium text-slate-100">{f.name}</p>
                    <p className="text-sm text-slate-300">
                      {f.score.toFixed(1)}
                      <span className="text-slate-500"> / {f.max_score}</span>
                    </p>
                  </div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-ink-700/60">
                    <SpringBar
                      pct={(f.score / f.max_score) * 100}
                      className={
                        f.score === 0
                          ? "bg-emerald-400"
                          : f.score / f.max_score > 0.6
                            ? "bg-red-400"
                            : "bg-amber-400"
                      }
                    />
                  </div>
                  <p className="mt-2 text-xs leading-relaxed text-slate-400">
                    <span className="text-slate-300">{f.detail}</span> {f.explanation}
                  </p>
                </div>
              ))}
            </div>
          </Card>

          <div className="space-y-4">
            <Card>
              <CardHeader title="Assessment summary" subtitle="Generated from the factor results" />
              <p className="px-5 py-4 text-sm leading-relaxed text-slate-300">
                {data.narrative}
              </p>
              <p className="border-t border-line/70 px-5 py-3 text-[11px] leading-relaxed text-slate-500">
                {data.methodology.disclaimer}
              </p>
            </Card>
            {data.warnings.length > 0 && (
              <Card>
                <CardHeader title="Missing information warnings" />
                <ul className="space-y-2 px-5 py-4">
                  {data.warnings.map((w, i) => (
                    <li key={i} className="flex gap-2 text-xs leading-relaxed text-amber-200">
                      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-400" />
                      {w}
                    </li>
                  ))}
                </ul>
              </Card>
            )}
            <Card>
              <CardHeader title="Recommended verification actions" />
              <ul className="space-y-2 px-5 py-4">
                {data.recommended_actions.map((a, i) => (
                  <li key={i} className="flex gap-2 text-xs leading-relaxed text-slate-300">
                    <ClipboardList className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent-400" />
                    {a}
                  </li>
                ))}
              </ul>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
