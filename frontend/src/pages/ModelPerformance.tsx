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
import { modelService } from "../api/services";
import { useFetch } from "../hooks/useAsync";
import {
  Card,
  CardHeader,
  CardSkeleton,
  ErrorState,
  PageHeader,
} from "../components/ui";
import { fmtLacs, fmtNum } from "../utils/format";

export default function ModelPerformance() {
  const compare = useFetch(() => modelService.compare());
  const metrics = useFetch(() => modelService.metrics());

  if (compare.loading) {
    return (
      <div className="space-y-4">
        <CardSkeleton rows={6} />
        <CardSkeleton rows={4} />
      </div>
    );
  }
  if (compare.error) {
    return <ErrorState message={compare.error} onRetry={compare.reload} />;
  }

  const entries = compare.data?.comparison ?? [];
  const five = entries.filter((e) => e.stage === "training_stage");
  const served = entries.find((e) => e.selected);
  const extras = entries.filter(
    (e) => e.stage !== "training_stage" && !e.selected,
  );
  const r2Chart = five.map((e) => ({
    model: e.model,
    r2: e.validation_r2 ?? 0,
  }));
  const rmseChart = five.map((e) => ({
    model: e.model,
    rmse: e.validation_rmse_lacs ?? 0,
  }));
  const m = metrics.data;

  return (
    <div>
      <PageHeader
        eyebrow="05 · Measured Results"
        title="Model Performance"
        description="Measured results from the training and optimisation stages — grouped 70/15/15 split, log-target, test partition scored once per selected model. Served model: the optimisation-stage XGBoost (E01)."
      />

      {served && (
        <Card className="mb-4 border-accent-500/40">
          <CardHeader
            title={`${served.model}`}
            subtitle="Selected and served by the API — chosen in the optimisation stage"
            action={
              <span className="rounded-full border border-accent-500/50 bg-accent-500/15 px-2.5 py-0.5 text-[11px] font-semibold text-accent-400">
                SERVED
              </span>
            }
          />
          <div className="grid grid-cols-2 gap-4 px-5 py-4 sm:grid-cols-4">
            {[
              ["Validation R²", served.validation_r2?.toFixed(4)],
              ["Test R² (once)", served.test_r2?.toFixed(4)],
              ["Test MAE", served.test_mae_lacs != null ? fmtLacs(served.test_mae_lacs) : undefined],
              ["Test RMSE", served.test_rmse_lacs != null ? fmtLacs(served.test_rmse_lacs) : undefined],
            ].map(([label, value]) => (
              <div key={label}>
                <p className="text-[11px] uppercase tracking-[0.14em] text-slate-400">{label}</p>
                <p className="mt-1 text-xl font-semibold text-slate-50">{value ?? "—"}</p>
              </div>
            ))}
          </div>
          {m && (
            <p className="border-t border-line/70 px-5 py-3 text-xs leading-relaxed text-slate-400">
              Grouped cross-validation R² {m.metrics.grouped_cv.r2_mean.toFixed(4)} ±{" "}
              {m.metrics.grouped_cv.r2_std.toFixed(4)} · test MAPE{" "}
              {fmtNum(m.metrics.test.mape_pct, 1)}% · median absolute error{" "}
              {fmtLacs(m.metrics.test.median_ae_lacs)} · hyperparameters: depth{" "}
              {m.hyperparameters.max_depth}, learning rate{" "}
              {fmtNum(m.hyperparameters.learning_rate, 3)}, 1,154 trees.
            </p>
          )}
        </Card>
      )}

      <Card>
        <CardHeader
          title="Candidate models — training stage"
          subtitle="Validation metrics after tuning (or baseline where untuned); MAPE and training time are the measured baseline values"
        />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead>
              <tr className="border-b border-line/70 text-[11px] uppercase tracking-wider text-slate-500">
                <th className="px-5 py-3 font-medium">Model</th>
                <th className="px-5 py-3 font-medium">Status</th>
                <th className="px-5 py-3 font-medium">Val R²</th>
                <th className="px-5 py-3 font-medium">Val MAE</th>
                <th className="px-5 py-3 font-medium">Val RMSE</th>
                <th className="px-5 py-3 font-medium">Baseline MAPE</th>
                <th className="px-5 py-3 font-medium">CV R²</th>
                <th className="px-5 py-3 font-medium">Train time</th>
              </tr>
            </thead>
            <tbody>
              {five.map((e) => (
                <tr key={e.model} className="border-b border-line/40 last:border-0">
                  <td className="px-5 py-3 font-medium capitalize text-slate-100">
                    {e.model.replace("_regression", "").replace("_forest", " forest")}
                  </td>
                  <td className="px-5 py-3 text-slate-400">
                    {e.tuned ? "Tuned candidate" : "Baseline only"}
                  </td>
                  <td className="px-5 py-3 text-slate-200">{e.validation_r2?.toFixed(4) ?? "—"}</td>
                  <td className="px-5 py-3 text-slate-200">{fmtLacs(e.validation_mae_lacs)}</td>
                  <td className="px-5 py-3 text-slate-200">{fmtLacs(e.validation_rmse_lacs)}</td>
                  <td className="px-5 py-3 text-slate-200">
                    {e.validation_mape_pct != null ? `${e.validation_mape_pct.toFixed(1)}%` : "—"}
                  </td>
                  <td className="px-5 py-3 text-slate-200">
                    {e.cv_r2_mean != null
                      ? `${e.cv_r2_mean.toFixed(3)} ± ${e.cv_r2_std?.toFixed(3)}`
                      : "—"}
                  </td>
                  <td className="px-5 py-3 text-slate-200">
                    {e.baseline_train_time_s != null
                      ? `${e.baseline_train_time_s.toFixed(1)}s`
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="border-t border-line/70 px-5 py-3 text-[11px] leading-relaxed text-slate-500">
          {compare.data?.note} The training-stage winner (tuned XGBoost) was
          superseded by the optimisation-stage champion above on validation
          RMSE under the same grouped protocol.
        </p>
      </Card>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Validation R² by model" />
          <div className="h-64 px-3 py-4">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={r2Chart}>
                <CartesianGrid stroke="#22304f" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="model" tick={{ fill: "#94a3b8", fontSize: 11 }} />
                <YAxis domain={[0, 1]} tick={{ fill: "#94a3b8", fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ background: "#101a30", border: "1px solid #22304f", borderRadius: 8, fontSize: 12 }}
                  formatter={(v: number) => [v.toFixed(4), "Validation R²"]}
                />
                <Bar dataKey="r2" radius={[3, 3, 0, 0]}>
                  {r2Chart.map((_, i) => (
                    <Cell key={i} fill="#5b8def" />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card>
          <CardHeader title="Validation RMSE by model (₹ lakh — lower is better)" />
          <div className="h-64 px-3 py-4">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={rmseChart}>
                <CartesianGrid stroke="#22304f" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="model" tick={{ fill: "#94a3b8", fontSize: 11 }} />
                <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ background: "#101a30", border: "1px solid #22304f", borderRadius: 8, fontSize: 12 }}
                  formatter={(v: number) => [`₹${v.toFixed(2)} L`, "Validation RMSE"]}
                />
                <Bar dataKey="rmse" radius={[3, 3, 0, 0]}>
                  {rmseChart.map((_, i) => (
                    <Cell key={i} fill="#1fbfa8" />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      {extras.length > 0 && (
        <Card className="mt-4">
          <CardHeader title="Additional measured evaluations" subtitle="Other real evaluations recorded during the stages" />
          <div className="divide-y divide-line/50">
            {extras.map((e) => (
              <div key={e.model} className="flex flex-wrap items-center justify-between gap-2 px-5 py-3 text-sm">
                <span className="text-slate-200">{e.model}</span>
                <span className="text-slate-400">
                  {e.test_r2 != null
                    ? `R² ${e.test_r2.toFixed(4)} · RMSE ${fmtLacs(e.test_rmse_lacs)}`
                    : `Validation R² ${e.validation_r2?.toFixed(4)}`}
                </span>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
