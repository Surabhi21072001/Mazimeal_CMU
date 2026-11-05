// Calls that carry the signed-in account, and fail rather than fall back.
//
// client.js answers a failed request with a bundled fixture, which is right
// for a cook screen - better a sample recipe than a blank page. It is wrong
// for anything a person acts on: an admin reading rule counts, or a reviewer
// recording a verdict, must never be shown bundled numbers that look live. So
// these throw, and the screen says what went wrong.
//
// Every authenticated call sends the Supabase access token and nothing else
// about who is calling. The server reads the identity out of the token, so a
// browser cannot name itself.
import { supabase } from "../supabase/client";

const DEPLOYED_API = "https://mazimeal-api.onrender.com";
const CONFIGURED_API = import.meta.env.VITE_API_BASE_URL;
export const BASE = CONFIGURED_API === undefined ? DEPLOYED_API : CONFIGURED_API;

export class ApiError extends Error {
  constructor(message, { status, detail } = {}) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

async function token() {
  if (!supabase) return null;
  const { data } = await supabase.auth.getSession();
  return data?.session?.access_token || null;
}

export async function call(path, { method = "GET", body, auth = true } = {}) {
  if (!BASE) throw new ApiError("No backend is configured for this build.");
  const headers = {};
  if (body) headers["Content-Type"] = "application/json";
  if (auth) {
    const jwt = await token();
    if (!jwt) throw new ApiError("Not signed in.", { status: 401 });
    headers.Authorization = `Bearer ${jwt}`;
  }

  const response = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  // FastAPI puts our structured errors in `detail`; the object is kept, because
  // the screens show which field was refused and what was allowed instead.
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const detail = payload?.detail;
    const message =
      (typeof detail === "string" && detail) ||
      detail?.error ||
      detail?.message ||
      `${response.status} ${response.statusText}`;
    throw new ApiError(message, { status: response.status, detail });
  }
  return payload;
}
