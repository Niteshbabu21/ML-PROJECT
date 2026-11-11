import { BrowserProvider, Contract, type Signer } from "ethers";

/** Minimal PropertyToken ABI subset used by wallet actions (interface
 * definitions only — all state is read from the chain itself). */
export const PROPERTY_TOKEN_ABI = [
  "function buyTokens(uint256 propertyId, uint256 amount) payable",
  "function safeTransferFrom(address from, address to, uint256 id, uint256 amount, bytes data)",
  "function balanceOf(address account, uint256 id) view returns (uint256)",
  "function tokenPriceWei() view returns (uint256)",
] as const;

export interface WalletConnection {
  address: string;
  signer: Signer;
  provider: BrowserProvider;
}

declare global {
  interface Window {
    ethereum?: unknown;
  }
}

export function walletAvailable(): boolean {
  return typeof window !== "undefined" && !!window.ethereum;
}

/** Connect an injected wallet (e.g. MetaMask). Throws a readable error
 * when no wallet exists or the user rejects the connection — callers
 * surface it as the disconnected state, never a fake success. */
export async function connectWallet(): Promise<WalletConnection> {
  if (!walletAvailable()) {
    throw new Error(
      "No compatible wallet detected. Install MetaMask (or another injected wallet) and point it at the local Hardhat network (RPC http://127.0.0.1:8545, chain 31337).",
    );
  }
  const provider = new BrowserProvider(window.ethereum as never);
  const signer = await provider.getSigner();
  return { address: await signer.getAddress(), signer, provider };
}

export function tokenContract(
  contractAddress: string,
  signer: Signer,
): Contract {
  return new Contract(contractAddress, PROPERTY_TOKEN_ABI, signer);
}
