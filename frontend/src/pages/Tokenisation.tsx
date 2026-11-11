import { useState } from "react";
import { motion } from "framer-motion";
import { Coins, Info } from "lucide-react";
import ChainRegistration from "../components/ChainRegistration";
import PropertyForm from "../components/PropertyForm";
import { dashboardService, tokenService } from "../api/services";
import { useAsync, useFetch } from "../hooks/useAsync";
import type { PropertyFeatures, TokenData } from "../types/api";
import {
  Card,
  CardHeader,
  ErrorState,
  PageHeader,
  StatCard,
} from "../components/ui";
import { fmtINR, fmtInt, fmtLacs } from "../utils/format";
import { loadLastProperty } from "../utils/storage";
import { SpringBar } from "../components/motion";

export default function Tokenisation() {
  const [mode, setMode] = useState<"value" | "property">("value");
  const [activeProperty, setActiveProperty] =
    useState<PropertyFeatures | null>(() => loadLastProperty());
  const [valuationInput, setValuationInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const history = useFetch(() => dashboardService.history(1, 10));
  const calcValue = useAsync(async (v: number) =>
    tokenService.calculateFromValuation(v),
  );
  const calcProperty = useAsync(async (f: PropertyFeatures) =>
    tokenService.calculateFromProperty(f),
  );
  const data: TokenData | null = calcValue.data ?? calcProperty.data;
  const loading = calcValue.loading || calcProperty.loading;

  const submitValue = async () => {
    const v = parseFloat(valuationInput);
    if (Number.isNaN(v) || v <= 0) {
      setError("Enter a valuation in lakhs greater than zero.");
      return;
    }
    setError(null);
    await calcValue.run(v);
  };

  const fractionPct =
    data && data.valuation_inr > 0
      ? ((data.token_supply * data.token_denomination_inr) / data.valuation_inr) * 100
      : 0;

  return (
    <div>
      <PageHeader
        eyebrow="04 · Fractional Tokens"
        title="Tokenisation"
        description="Fractional token supply from a valuation: supply = floor(value ÷ ₹10,000 denomination). This is the prototype calculation the smart-contract stage will mirror on-chain — no tokens are issued here."
      />
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader title="Calculate token supply" subtitle="POST /api/token/calculate" />
          <div className="px-5 py-5">
            <div className="mb-5 flex overflow-hidden rounded-md border border-line">
              {(
                [
                  ["value", "From a valuation amount"],
                  ["property", "From property features"],
                ] as const
              ).map(([m, label]) => (
                <button
                  key={m}
                  onClick={() => setMode(m)}
                  className={`flex-1 px-3 py-2 text-sm transition ${
                    mode === m
                      ? "bg-accent-500/90 font-medium text-white"
                      : "bg-ink-850 text-slate-400 hover:bg-ink-800"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>

            {mode === "value" ? (
              <div className="space-y-4">
                <label className="block">
                  <span className="mb-1.5 block text-[11px] font-medium uppercase tracking-[0.12em] text-slate-400">
                    Property valuation (₹ lakhs)
                  </span>
                  <input
                    type="number"
                    step="any"
                    value={valuationInput}
                    onChange={(e) => setValuationInput(e.target.value)}
                    placeholder="e.g. 85.37"
                    className="w-full rounded-md border border-line bg-ink-850 px-3 py-2 text-sm text-slate-100 outline-none transition placeholder:text-slate-500 focus:border-accent-500 focus:ring-1 focus:ring-accent-500/40"
                  />
                </label>
                {(history.data?.items.length ?? 0) > 0 && (
                  <div>
                    <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.12em] text-slate-400">
                      Or use a recent valuation
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {history.data!.items.slice(0, 5).map((it) => (
                        <button
                          key={it.request_id}
                          onClick={() =>
                            setValuationInput(String(it.predicted_price_lacs))
                          }
                          className="rounded-full border border-line px-3 py-1 text-xs text-slate-300 transition hover:bg-ink-800"
                        >
                          {it.property.LOCALITY}, {it.property.CITY} ·{" "}
                          {fmtLacs(it.predicted_price_lacs)}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                {(error || calcValue.error) && (
                  <ErrorState message={error ?? calcValue.error!} />
                )}
                <div className="flex justify-end">
                  <button
                    onClick={submitValue}
                    disabled={loading}
                    className="btn-shine rounded-lg bg-accent-500 px-5 py-2.5 text-sm font-medium text-white shadow-[0_8px_24px_-10px_rgba(47,111,237,0.7)] transition hover:bg-accent-400 disabled:opacity-50"
                  >
                    {loading ? "Calculating…" : "Calculate supply"}
                  </button>
                </div>
              </div>
            ) : (
              <PropertyForm
                initial={loadLastProperty()}
                onSubmit={(f) => {
                  setActiveProperty(f);
                  void calcProperty.run(f);
                }}
                submitting={loading}
                submitLabel="Value property & calculate"
              />
            )}
            {mode === "property" && calcProperty.error && (
              <div className="mt-4">
                <ErrorState message={calcProperty.error} />
              </div>
            )}
          </div>
        </Card>

        <div className="space-y-4">
          {data ? (
            <>
              <StatCard
                label="Token supply"
                value={fmtInt(data.token_supply)}
                countTo={data.token_supply}
                formatCount={fmtInt}
                hint={`tokens of ${fmtINR(data.token_denomination_inr)} each`}
                icon={<Coins className="h-4 w-4" />}
              />
              <Card className="px-5 py-4">
                <dl className="space-y-2.5 text-sm">
                  <div className="flex justify-between">
                    <dt className="text-slate-400">Valuation</dt>
                    <dd className="text-slate-100">
                      {fmtLacs(data.valuation_lacs)} ({fmtINR(data.valuation_inr)})
                    </dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-slate-400">Valuation source</dt>
                    <dd className="text-slate-100">
                      {data.valuation_source === "provided"
                        ? "Provided amount"
                        : "Valuation model"}
                    </dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-slate-400">Exact token amount</dt>
                    <dd className="text-slate-100">{data.exact_token_amount}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-slate-400">Rounding</dt>
                    <dd className="text-slate-100">
                      floor · {fmtINR(data.rounding.remainder_inr)} untokenised
                    </dd>
                  </div>
                </dl>
                <div className="mt-4">
                  <div className="flex justify-between text-xs text-slate-400">
                    <span>Fractional representation</span>
                    <span>{fractionPct.toFixed(2)}% tokenised</span>
                  </div>
                  <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-ink-700/60">
                    <SpringBar pct={fractionPct} className="bg-gradient-to-r from-accent-500 to-teal-450" />
                  </div>
                  <p className="mt-2 text-[11px] leading-relaxed text-slate-500">
                    Each token represents a {fmtINR(data.token_denomination_inr)}{" "}
                    fraction of the valuation. The remainder stays untokenised
                    so issued supply never exceeds the property's value.
                  </p>
                  <div className="mt-4 border-t border-line/60 pt-4">
                    <div className="flex flex-wrap gap-1.5">
                      {Array.from({
                        length: Math.min(48, data.token_supply),
                      }).map((_, i) => (
                        <motion.span
                          key={`${data.token_supply}-${i}`}
                          initial={{ scale: 0, rotate: -30, opacity: 0 }}
                          animate={{ scale: 1, rotate: 0, opacity: 1 }}
                          transition={{
                            delay: 0.3 + i * 0.014,
                            type: "spring",
                            stiffness: 380,
                            damping: 20,
                          }}
                          className="flex h-6 w-6 items-center justify-center rounded-full border border-teal-450/40 bg-teal-450/10 font-mono text-[8px] text-teal-300"
                        >
                          ₹
                        </motion.span>
                      ))}
                    </div>
                    <p className="mt-2.5 font-mono text-[10px] tracking-wide text-slate-500">
                      {data.token_supply > 48
                        ? `FIRST 48 OF ${fmtInt(data.token_supply)} TOKENS · 1 CHIP = 1 TOKEN OF ${fmtINR(data.token_denomination_inr)}`
                        : `1 CHIP = 1 TOKEN OF ${fmtINR(data.token_denomination_inr)}`}
                    </p>
                  </div>
                </div>
              </Card>
              <div className="flex gap-2 rounded-xl border border-line bg-ink-900 px-4 py-3 text-[11px] leading-relaxed text-slate-400">
                <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent-400" />
                {data.prototype_note} On-chain issuance happens in the
                blockchain stage (local Hardhat network); see the Blockchain
                Explorer for network status.
              </div>
            </>
          ) : (
            <Card className="px-5 py-5">
              <p className="text-sm leading-relaxed text-slate-400">
                Run a calculation to see the token supply, denomination,
                rounding remainder and the fractional representation of the
                property's value.
              </p>
            </Card>
          )}
        </div>
      </div>
      <ChainRegistration property={activeProperty} />
    </div>
  );
}
