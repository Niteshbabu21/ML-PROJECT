import { useState } from "react";
import { Blocks, RefreshCw, Wallet } from "lucide-react";
import { chainService } from "../api/services";
import { useFetch } from "../hooks/useAsync";
import type { ChainRecord } from "../types/api";
import {
  Card,
  CardHeader,
  EmptyState,
  PageHeader,
  RiskBadge,
  StatCard,
} from "../components/ui";
import { fmtINR, fmtInt } from "../utils/format";
import {
  connectWallet,
  tokenContract,
  walletAvailable,
  type WalletConnection,
} from "../utils/wallet";

function shortHash(h: string): string {
  return `${h.slice(0, 10)}…${h.slice(-6)}`;
}

export default function BlockchainExplorer() {
  const status = useFetch(() => chainService.status());
  const properties = useFetch(() => chainService.properties());
  const [wallet, setWallet] = useState<WalletConnection | null>(null);
  const [walletError, setWalletError] = useState<string | null>(null);
  const [selected, setSelected] = useState<ChainRecord | null>(null);
  const [buyAmount, setBuyAmount] = useState("10");
  const [transferTo, setTransferTo] = useState("");
  const [transferAmount, setTransferAmount] = useState("1");
  const [txState, setTxState] = useState<string | null>(null);
  const [txHash, setTxHash] = useState<string | null>(null);
  const [balance, setBalance] = useState<string | null>(null);

  const s = status.data;
  const records = properties.data?.properties ?? [];
  const totalSupply = records.reduce((sum, r) => sum + r.token_supply, 0);

  const onConnect = async () => {
    setWalletError(null);
    try {
      setWallet(await connectWallet());
    } catch (err) {
      setWalletError(err instanceof Error ? err.message : "Wallet connection failed.");
    }
  };

  const refreshBalance = async (rec: ChainRecord, w: WalletConnection) => {
    if (!s?.contract_address) return;
    const c = tokenContract(s.contract_address, w.signer);
    const bal = await c.balanceOf(w.address, rec.chain_property_id);
    setBalance(bal.toString());
  };

  const onSelect = async (rec: ChainRecord) => {
    setSelected(rec);
    setTxHash(null);
    setTxState(null);
    setBalance(null);
    if (wallet) {
      try {
        await refreshBalance(rec, wallet);
      } catch {
        setBalance(null);
      }
    }
  };

  const onBuy = async () => {
    if (!wallet || !selected || !s?.contract_address) return;
    setTxState("Awaiting wallet confirmation…");
    setTxHash(null);
    try {
      const c = tokenContract(s.contract_address, wallet.signer);
      const amount = BigInt(buyAmount);
      const price: bigint = await c.tokenPriceWei();
      const tx = await c.buyTokens(selected.chain_property_id, amount, {
        value: amount * price,
      });
      setTxState("Transaction sent — waiting for on-chain confirmation…");
      const receipt = await tx.wait();
      setTxHash(receipt.hash);
      setTxState(`Confirmed in block ${receipt.blockNumber}.`);
      await refreshBalance(selected, wallet);
      properties.reload();
    } catch (err) {
      setTxState(
        err instanceof Error
          ? `Transaction failed: ${err.message.slice(0, 220)}`
          : "Transaction failed.",
      );
    }
  };

  const onTransfer = async () => {
    if (!wallet || !selected || !s?.contract_address) return;
    setTxState("Awaiting wallet confirmation…");
    setTxHash(null);
    try {
      const c = tokenContract(s.contract_address, wallet.signer);
      const tx = await c.safeTransferFrom(
        wallet.address,
        transferTo,
        selected.chain_property_id,
        BigInt(transferAmount),
        "0x",
      );
      setTxState("Transaction sent — waiting for on-chain confirmation…");
      const receipt = await tx.wait();
      setTxHash(receipt.hash);
      setTxState(`Confirmed in block ${receipt.blockNumber}.`);
      await refreshBalance(selected, wallet);
    } catch (err) {
      setTxState(
        err instanceof Error
          ? `Transaction failed: ${err.message.slice(0, 220)}`
          : "Transaction failed.",
      );
    }
  };

  return (
    <div>
      <PageHeader
        eyebrow="06 · On-Chain · Local Network"
        title="Blockchain Explorer"
        description="On-chain state of the PropertyToken contract, read through the Flask bridge (GET /api/chain/*). Purchases and transfers are signed by your own wallet and shown only after on-chain confirmation — nothing here is simulated."
      />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Network status"
          value={status.loading ? "Checking…" : s?.connected ? "Connected" : "Unavailable"}
          hint={s ? `${s.rpc_url}${s.chain_id ? ` · chain ${s.chain_id}` : ""}` : undefined}
          icon={<Blocks className="h-4 w-4" />}
        />
        <StatCard
          label="Latest block"
          value={s?.block_number != null ? String(s.block_number) : "—"}
          hint="Reported by the bridge from the node"
        />
        <StatCard
          label="Contract"
          value={s?.contract_address ? shortHash(s.contract_address) : "Not deployed"}
          hint={s?.contract_address ?? "Deploy via the blockchain module"}
        />
        <StatCard
          label="Registered properties"
          value={String(records.length)}
          hint={`Total token supply ${fmtInt(totalSupply)}`}
          icon={<Wallet className="h-4 w-4" />}
        />
      </div>

      <Card className="mt-4">
        <CardHeader
          title="Registered properties"
          subtitle="Tokenisation records (database) enriched with live on-chain availability"
          action={
            <button
              onClick={() => {
                status.reload();
                properties.reload();
              }}
              className="inline-flex items-center gap-1.5 rounded-md border border-line px-2.5 py-1.5 text-xs text-slate-200 transition hover:bg-ink-800"
            >
              <RefreshCw className="h-3.5 w-3.5" /> Refresh
            </button>
          }
        />
        {properties.loading && (
          <p className="px-5 py-6 text-sm text-slate-500">Loading…</p>
        )}
        {properties.error && (
          <p className="px-5 py-6 text-sm text-red-300">{properties.error}</p>
        )}
        {!properties.loading && records.length === 0 && (
          <div className="px-5 py-5">
            <EmptyState
              title="No properties registered yet"
              message={
                s?.connected
                  ? "Register a valued property from the Tokenisation page — it will appear here with its transaction hash."
                  : "The chain is unavailable. Start the Hardhat node, deploy the contract, then register a property from the Tokenisation page."
              }
            />
          </div>
        )}
        {records.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[860px] text-left text-sm">
              <thead>
                <tr className="border-b border-line/70 text-[11px] uppercase tracking-wider text-slate-500">
                  <th className="px-5 py-3 font-medium">Chain ID</th>
                  <th className="px-5 py-3 font-medium">Valuation</th>
                  <th className="px-5 py-3 font-medium">Supply</th>
                  <th className="px-5 py-3 font-medium">Available</th>
                  <th className="px-5 py-3 font-medium">Risk</th>
                  <th className="px-5 py-3 font-medium">Status</th>
                  <th className="px-5 py-3 font-medium">Register tx</th>
                  <th className="px-5 py-3 font-medium" />
                </tr>
              </thead>
              <tbody>
                {records.map((r) => (
                  <tr key={r.property_ref} className="border-b border-line/40 last:border-0">
                    <td className="px-5 py-3 font-medium text-slate-100">#{r.chain_property_id}</td>
                    <td className="px-5 py-3 text-slate-200">{fmtINR(r.valuation_inr)}</td>
                    <td className="px-5 py-3 text-slate-200">{fmtInt(r.token_supply)}</td>
                    <td className="px-5 py-3 text-slate-200">
                      {r.available_supply != null ? fmtInt(r.available_supply) : "—"}
                    </td>
                    <td className="px-5 py-3">
                      <RiskBadge category={r.risk_category as "LOW" | "MEDIUM" | "HIGH"} />
                    </td>
                    <td className="px-5 py-3 text-slate-300">{r.status}</td>
                    <td className="px-5 py-3 font-mono text-xs text-slate-400">
                      {shortHash(r.register_tx)}
                    </td>
                    <td className="px-5 py-3">
                      <button
                        onClick={() => void onSelect(r)}
                        className="rounded-md border border-line px-2.5 py-1 text-xs text-slate-200 transition hover:bg-ink-800"
                      >
                        Trade
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card className="mt-4">
        <CardHeader
          title="Wallet — purchase & transfer"
          subtitle="Step 8 · signed by your wallet on the local network"
        />
        <div className="px-5 py-5">
          {!wallet ? (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="max-w-xl text-sm leading-relaxed text-slate-400">
                {walletAvailable()
                  ? "Connect your wallet to buy tokens of a registered property or transfer tokens you hold. The wallet must be on the local Hardhat network (chain 31337)."
                  : "No compatible wallet detected in this browser. Install MetaMask and add the local network (RPC http://127.0.0.1:8545, chain 31337) to trade — until then this stays in the disconnected state."}
              </p>
              <button
                onClick={onConnect}
                className="inline-flex items-center gap-2 rounded-md bg-accent-500 px-4 py-2 text-sm font-medium text-white transition hover:bg-accent-400"
              >
                <Wallet className="h-4 w-4" /> Connect wallet
              </button>
            </div>
          ) : (
            <p className="text-sm text-slate-300">
              Connected wallet:{" "}
              <span className="font-mono text-slate-100">{wallet.address}</span>
              {selected && balance != null && (
                <>
                  {" "}· balance of property #{selected.chain_property_id}:{" "}
                  <span className="font-medium text-slate-100">{balance} tokens</span>
                </>
              )}
            </p>
          )}
          {walletError && (
            <p className="mt-3 rounded-lg border border-red-900/50 bg-red-950/20 px-4 py-3 text-sm text-red-200">
              {walletError}
            </p>
          )}
          {wallet && !selected && (
            <p className="mt-3 text-sm text-slate-400">
              Select a property with the Trade button above to buy or transfer its tokens.
            </p>
          )}
          {wallet && selected && (
            <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
              <div className="rounded-lg border border-line bg-ink-850 px-4 py-4">
                <p className="text-sm font-medium text-slate-100">
                  Buy tokens — property #{selected.chain_property_id}
                </p>
                <div className="mt-3 flex gap-2">
                  <input
                    type="number"
                    min="1"
                    value={buyAmount}
                    onChange={(e) => setBuyAmount(e.target.value)}
                    className="w-28 rounded-md border border-line bg-ink-900 px-3 py-2 text-sm text-slate-100 outline-none focus:border-accent-500"
                  />
                  <button
                    onClick={onBuy}
                    disabled={selected.status !== "minted"}
                    className="rounded-md bg-accent-500 px-4 py-2 text-sm font-medium text-white transition hover:bg-accent-400 disabled:opacity-50"
                  >
                    Buy
                  </button>
                </div>
                {selected.status !== "minted" && (
                  <p className="mt-2 text-xs text-amber-300">
                    Tokens are not minted yet — mint from the Tokenisation page first.
                  </p>
                )}
                <p className="mt-2 text-xs text-slate-500">
                  Price is read from the contract (demo test-ETH price). Payment must equal amount × price.
                </p>
              </div>
              <div className="rounded-lg border border-line bg-ink-850 px-4 py-4">
                <p className="text-sm font-medium text-slate-100">Transfer tokens</p>
                <div className="mt-3 space-y-2">
                  <input
                    value={transferTo}
                    onChange={(e) => setTransferTo(e.target.value)}
                    placeholder="Recipient address 0x…"
                    className="w-full rounded-md border border-line bg-ink-900 px-3 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-500 focus:border-accent-500"
                  />
                  <div className="flex gap-2">
                    <input
                      type="number"
                      min="1"
                      value={transferAmount}
                      onChange={(e) => setTransferAmount(e.target.value)}
                      className="w-28 rounded-md border border-line bg-ink-900 px-3 py-2 text-sm text-slate-100 outline-none focus:border-accent-500"
                    />
                    <button
                      onClick={onTransfer}
                      className="rounded-md border border-line px-4 py-2 text-sm text-slate-100 transition hover:bg-ink-800"
                    >
                      Transfer
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}
          {txState && (
            <div className="mt-4 rounded-lg border border-line bg-ink-850 px-4 py-3 text-sm text-slate-300">
              <p>{txState}</p>
              {txHash && (
                <p className="mt-1 break-all font-mono text-xs text-slate-200">
                  tx: {txHash}
                </p>
              )}
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
