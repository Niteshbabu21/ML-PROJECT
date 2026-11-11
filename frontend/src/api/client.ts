import axios, { AxiosError } from "axios";
import type { Envelope } from "../types/api";

const baseURL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ??
  "http://127.0.0.1:5000";

export class ApiException extends Error {
  code: string;
  status: number | null;
  constructor(message: string, code = "NETWORK_ERROR", status: number | null = null) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

const http = axios.create({ baseURL, timeout: 20000 });

async function request<T>(promise: Promise<{ data: Envelope<T> }>): Promise<T> {
  try {
    const res = await promise;
    return res.data.data;
  } catch (err) {
    const ax = err as AxiosError<{ error?: { code: string; message: string } }>;
    if (ax.code === "ECONNABORTED") {
      throw new ApiException(
        "The request timed out. Check that the backend is running, then retry.",
        "TIMEOUT",
      );
    }
    const body = ax.response?.data;
    if (body?.error) {
      throw new ApiException(body.error.message, body.error.code, ax.response?.status ?? null);
    }
    throw new ApiException(
      "Cannot reach the backend API. Start the Flask server and retry.",
      "NETWORK_ERROR",
    );
  }
}

export const api = {
  get: <T>(url: string) => request<T>(http.get(url)),
  post: <T>(url: string, body: unknown) => request<T>(http.post(url, body)),
};
