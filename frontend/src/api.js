import { useCallback, useEffect, useRef, useState } from "react";

const BASE = import.meta.env.VITE_API_URL || "";
const KEY = "aangan_staff";

export const session = {
  get: () => { try { return JSON.parse(sessionStorage.getItem(KEY)); } catch { return null; } },
  set: (v) => sessionStorage.setItem(KEY, JSON.stringify(v)),
  clear: () => sessionStorage.removeItem(KEY),
};

export async function api(path, { method = "GET", body, form } = {}) {
  const headers = {};
  const s = session.get();
  if (s?.token) headers.Authorization = `Token ${s.token}`;
  if (body) headers["Content-Type"] = "application/json";
  let res;
  try {
    res = await fetch(BASE + path, { method, headers, body: form || (body ? JSON.stringify(body) : undefined) });
  } catch {
    throw new Error("Can't reach the server. Check your connection and try again.");
  }
  if (res.status === 401 && s) { session.clear(); window.location.assign("/login"); }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const first = Object.values(data).flat?.()[0];
    throw new Error(data.detail || (typeof first === "string" ? first : "Something went wrong. Try again."));
  }
  return data;
}

export function useFetch(path) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const requestId = useRef(0);
  const load = useCallback(() => {
    const id = ++requestId.current;
    setState((s) => ({ ...s, loading: true, error: null }));
    api(path).then((data) => {
      if (id === requestId.current) setState({ data, error: null, loading: false });
    }).catch((e) => {
      if (id === requestId.current) setState({ data: null, error: e.message, loading: false });
    });
  }, [path]);
  useEffect(() => {
    load();
    return () => { requestId.current += 1; };
  }, [load]);
  return { ...state, reload: load };
}

export const inr = (n) => (n == null ? "–" : "₹" + new Intl.NumberFormat("en-IN").format(Math.round(n)));
export const pct = (n) => (n == null ? "–" : `${n}%`);
export const when = (iso) => new Date(iso).toLocaleString("en-IN", { weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
export function dur(sec) {
  if (sec == null) return "–";
  if (sec < 60) return `${sec} s`;
  const m = Math.floor(sec / 60);
  if (m < 60) return sec % 60 ? `${m} min ${sec % 60} s` : `${m} min`;
  const h = Math.floor(m / 60);
  return h < 48 ? `${h} h ${m % 60} min` : `${Math.round(h / 24)} days`;
}
