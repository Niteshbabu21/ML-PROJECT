import { useState } from "react";
import { Link } from "react-router-dom";
import { Blocks, CheckCircle2 } from "lucide-react";
import { chainService } from "../api/services";
import { useAsync, useFetch } from "../hooks/useAsync";
import type { ChainRecord, PropertyFeatures } from "../types/api";
import { Card, CardHeader } from "./ui";
import { fmtINR, fmtInt } from "../utils/format";
import { ApiException } from "../api/client";

/** Steps 6–7 of the integrated workflow: register the valued property
 * on the local chain through the Flask bridge, then mint its supply.
 * Buttons call the real API; success renders only confirmed results
 * returned by the backend (which itself waits for the receipt). */
export default function ChainRegistration({
  property,
}: {
  property: PropertyFeatures | null;
}) {
  const status = useFetch(() => chainService.status());
  const [record, setRecord] = useState<ChainRecord | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const register = useAsync(async (p: PropertyFeatures) =>
    chainService.register(p),
  );
  const mint = useAsync(async (id: number) => chainService.mint(id));

  const connected = status.data?.connected;

  const onRegister = async () => {
    if (!property) return;
    setActionError(null);
    try {
      const out = await register.run(property);
      if (out) setRecord(out);
      else if (register.error) setActionError(register.error);
    } catch (err) {
      setActionError(err instanceof ApiException ? err.message : "Registration failed.");
    }
  };

  const onMint = async () => {
    if (!record) return;
    setActionError(null);
    const out = await mint.run(record.chain_property_id);
    if (out) setRecord(out);
  };

  return (
    <Card className="mt-4">
      <CardHeader
        title="Blockchain registration"
        subtitle="Steps 6–7 · via the Flask bridge (POST /api/chain/register, /api/chain/mint)"
        action={
          <span
            className={`rounded-full border px-2.5 py-0.5 text-[11px] font-medium ${
              connected
                ? "border-emerald-800 bg-emerald-950/50 text-emerald-300"
                : "border-amber-800 bg-amber-950/50 text-amber-300"
            }`}
          >
            {status.loading
              ? "checking chain…"
              : connected
                ? `chain ${status.data?.chain_id} connected`
                : "chain unavailable"}
          </span>
        }
      />
      <div className="px-5 py-4">
        {!connected && !status.loading && (
          <p className="text-sm leading-relaxed text-slate-400">
            The local Hardhat chain is not reachable
            {status.data?.connect_error ? ` (${status.data.connect_error})` : ""}.
            Start it with{" "}
            <code className="rounded bg-ink-800 px-1.5 py-0.5 text-xs text-slate-200">
              npx hardhat node
            </code>{" "}
            in the blockchain module and deploy the contract — registration
            is disabled until then, and no transaction will be simulated.
          </p>
        )}
        {connected && !record && (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="max-w-xl text-sm leading-relaxed text-slate-400">
              {property
                ? "Register the current property: the backend recomputes its valuation and risk, stores them on-chain under the property's deterministic reference (a hash of its features — re-registering the same property is rejected as a duplicate), and returns the confirmed transaction hash."
                : "Value a property first (Valuation page or the property mode above) — registration uses that exact property."}
            </p>
            <button
              onClick={onRegister}
              disabled={!property || register.loading}
              className="inline-flex items-center gap-2 rounded-md bg-accent-500 px-4 py-2 text-sm font-medium text-white transition hover:bg-accent-400 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Blocks className="h-4 w-4" />
              {register.loading ? "Registering…" : "Register on chain"}
            </button>
          </div>
        )}
        {(actionError || register.error || mint.error) && (
          <p className="mt-3 rounded-lg border border-red-900/50 bg-red-950/20 px-4 py-3 text-sm text-red-200">
            {actionError ?? register.error ?? mint.error}
          </p>
        )}
        {record && (
          <div>
            <dl className="grid grid-cols-1 gap-x-8 gap-y-2.5 text-sm sm:grid-cols-2">
              <div className="flex justify-between gap-3">
                <dt className="text-slate-400">Chain property ID</dt>
                <dd className="font-medium text-slate-100">{record.chain_property_id}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-slate-400">Valuation recorded</dt>
                <dd className="text-slate-100">{fmtINR(record.valuation_inr)}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-slate-400">Token supply (on-chain)</dt>
                <dd className="text-slate-100">{fmtInt(record.token_supply)} tokens</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-slate-400">Residual untokenised</dt>
                <dd className="text-slate-100">{fmtINR(record.residual_inr)}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-slate-400">Risk recorded</dt>
                <dd className="text-slate-100">
                  {record.risk_score} · {record.risk_category}
                </dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-slate-400">Status</dt>
                <dd className="flex items-center gap-1.5 text-slate-100">
                  {record.status === "minted" && (
                    <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                  )}
                  {record.status}
                </dd>
              </div>
            </dl>
            <div className="mt-3 space-y-1.5 text-xs text-slate-400">
              <p>
                Register tx (block {record.register_block}):{" "}
                <span className="break-all font-mono text-slate-200">{record.register_tx}</span>
              </p>
              {record.mint_tx && (
                <p>
                  Mint tx:{" "}
                  <span className="break-all font-mono text-slate-200">{record.mint_tx}</span>
                </p>
              )}
              <p className="text-slate-500">
                Property reference (database ↔ chain): {record.property_ref}
              </p>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              {record.status !== "minted" && (
                <button
                  onClick={onMint}
                  disabled={mint.loading}
                  className="rounded-md bg-teal-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-teal-500 disabled:opacity-50"
                >
                  {mint.loading ? "Minting…" : `Mint ${fmtInt(record.token_supply)} tokens`}
                </button>
              )}
              <Link
                to="/blockchain"
                className="rounded-md border border-line px-4 py-2 text-sm text-slate-200 transition hover:bg-ink-800"
              >
                Buy / transfer in Blockchain Explorer
              </Link>
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}
