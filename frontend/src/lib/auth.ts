import { API_BASE, clearSession, fetchWithSession, getToken, storeSession } from "./api";
import type { User } from "./types";

// Real auth against POST /auth/login (Supabase-backed). Tokens live in localStorage;
// client-side writes attach the access token via api.ts. Server reads use dev-bypass.

interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user_id: string;
}

export async function login(email: string, password: string): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ email, password }),
      // Bounded like every other call — a hung backend must not spin the sign-in button forever.
      signal: AbortSignal.timeout(8000),
    });
  } catch {
    throw new Error("Sign-in timed out — backend unreachable.");
  }
  if (!res.ok) throw new Error(res.status === 401 ? "Invalid email or password." : `Sign-in failed (${res.status}).`);
  const data = (await res.json()) as LoginResponse;
  storeSession(data.access_token, data.refresh_token);
  
  const { flushQueue } = await import("./idb");
  await flushQueue().catch(() => {});
}

export async function getMe(): Promise<User | null> {
  const token = getToken();
  if (!token) return null;
  try {
    const res = await fetchWithSession("/auth/me", { method: "GET" });
    if (!res.ok) return null;
    return (await res.json()) as User;
  } catch {
    return null;
  }
}

export function logout(): void {
  clearSession();
}
