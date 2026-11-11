import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { TrendingDown, TrendingUp } from "lucide-react";
import PropertyForm from "../components/PropertyForm";
import Waterfall from "../components/Waterfall";
import { modelService, valuationService } from "../api/services";
import { useAsync, useFetch } from "../hooks/useAsync";
import type { Contribution, PropertyFeatures } from "../types/api";
import {
  Card,
  CardHeader,
  CardSkeleton,
  ErrorState,
  PageHeader,
} from "../components/ui";
import { fmtLacs } from "../utils/format";
import { loadLastProperty, saveLastProperty } from "../utils/storage";

function ContributionRow({ c }: { c: Contribution }) {
  const up = c.shap_log > 0;
  return (
    <div className="flex items-center justify-between border-b border-line/40 py-2.5 last:border-0">
      <div className="flex items-center gap-2.5">
        {up ? (
          <TrendingUp className="h-4 w-4 text-teal-400" />
        ) : (
          <TrendingDown className="h-4 w-4 text-red-400" />
        )}
        <div>
          <p className="text-sm text-slate-100">{c.feature}</p>
          <p className="text-xs text-slate-500">{String(c.value ?? "—")}</p>
        </div>
      </div>
      <div className="text-right">
        <p className={`text-sm font-medium ${up ? "text-teal-300" : "text-red-300"}`}>
          ×{c.price_factor.toFixed(2)}
        </p>
        <p className="text-xs text-slate-500">
          {up ? "+" : ""}
          {c.shap_log.toFixed(3)} log
        </p>
      </div>
    </div>
  );
}

export default function Explainability() {
  const explain = useAsync(async (f: PropertyFeatures) =>
    valuationService.explain(f),
  );
  const global = useFetch(() => modelService.shapSummary());
  const data = explain.data;

  const onSubmit = async (features: PropertyFeatures) => {
    saveLastProperty(features);
    await explain.run(features);
  };

  const chartData = (global.data?.ranking ?? []).map((r) => ({
    feature: r.feature,
    importance: r.mean_abs_shap_log,
  }));

  return (
    <div>
      <PageHeader
        eyebrow="02 · SHAP Explainability"
        title="AI Explainability"
        description="SHAP explanations for the served model. Local contributions are computed per property by the backend's TreeExplainer; the global ranking is the model's precomputed SHAP summary over a documented 2,000-property sample."
      />
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader title="Explain a property" subtitle="POST /api/valuation/explain" />
          <div className="px-5 py-5">
            <PropertyForm
              initial={loadLastProperty()}
              onSubmit={onSubmit}
              submitting={explain.loading}
              submitLabel="Generate explanation"
            />
            {explain.error && (
              <div className="mt-4">
                <ErrorState message={explain.error} />
              </div>
            )}
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Global feature importance"
            subtitle="Mean |SHAP| in log space · GET /api/models/shap-summary"
          />
          {global.loading && (
            <div className="px-5 py-4">
              <CardSkeleton rows={5} />
            </div>
          )}
          {global.error && (
            <p className="px-5 py-4 text-sm text-red-300">{global.error}</p>
          )}
          {global.data && (
            <div className="h-80 px-3 py-4">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} layout="vertical" margin={{ left: 30, right: 16 }}>
                  <CartesianGrid stroke="#22304f" strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" tick={{ fill: "#94a3b8", fontSize: 11 }} />
                  <YAxis
                    type="category"
                    dataKey="feature"
                    tick={{ fill: "#cbd5e1", fontSize: 10 }}
                    width={130}
                  />
                  <Tooltip
                    contentStyle={{
                      background: "#101a30",
                      border: "1px solid #22304f",
                      borderRadius: 8,
                      fontSize: 12,
                    }}
                    formatter={(v: number) => [v.toFixed(3), "mean |SHAP|"]}
                  />
                  <Bar dataKey="importance" radius={[0, 3, 3, 0]} animationDuration={1100}>
                    {chartData.map((_, i) => (
                      <Cell key={i} fill={i < 3 ? "#5b8def" : "#33456b"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
          {global.data && (
            <p className="border-t border-line/70 px-5 py-3 text-[11px] leading-relaxed text-slate-500">
              Baseline (SHAP base value): {global.data.base_value_log.toFixed(3)} log ≈{" "}
              {fmtLacs(global.data.baseline_price_lacs)}. {global.data.provenance}
            </p>
          )}
        </Card>
      </div>

      {data && (
        <div className="mt-4 space-y-4">
          <Card>
            <CardHeader
              title="Local explanation"
              subtitle={`${data.property.LOCALITY}, ${data.property.CITY} — predicted ${fmtLacs(data.prediction.predicted_price_lacs)} vs baseline ${fmtLacs(data.baseline_price_lacs)}`}
              action={
                <span
                  className={`rounded-full border px-2.5 py-0.5 text-[11px] font-medium ${
                    data.additivity.verified
                      ? "border-emerald-800 bg-emerald-950/50 text-emerald-300"
                      : "border-red-800 bg-red-950/50 text-red-300"
                  }`}
                >
                  Additivity {data.additivity.verified ? "verified" : "failed"} · err{" "}
                  {data.additivity.abs_error.toExponential(1)}
                </span>
              }
            />
            <div className="px-5 py-4">
              <Waterfall
                baseValueLog={data.base_value_log}
                contributions={data.contributions}
              />
              <p className="mt-2 border-t border-line/70 pt-4 text-sm leading-relaxed text-slate-300">
                {data.explanation}
              </p>
            </div>
          </Card>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader title="Raised the price" subtitle="Positive SHAP contributions" />
              <div className="px-5 py-2">
                {data.top_positive.length ? (
                  data.top_positive.map((c) => (
                    <ContributionRow key={c.feature} c={c} />
                  ))
                ) : (
                  <p className="py-4 text-sm text-slate-500">None.</p>
                )}
              </div>
            </Card>
            <Card>
              <CardHeader title="Lowered the price" subtitle="Negative SHAP contributions" />
              <div className="px-5 py-2">
                {data.top_negative.length ? (
                  data.top_negative.map((c) => (
                    <ContributionRow key={c.feature} c={c} />
                  ))
                ) : (
                  <p className="py-4 text-sm text-slate-500">None.</p>
                )}
              </div>
            </Card>
          </div>

          <Card>
            <CardHeader title="All 20 feature contributions" subtitle="Aggregated to source features from the encoded model space; price factor = exp(SHAP)" />
            <div className="grid grid-cols-1 gap-x-8 px-5 py-2 md:grid-cols-2">
              {data.contributions.map((c) => (
                <ContributionRow key={c.feature} c={c} />
              ))}
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
