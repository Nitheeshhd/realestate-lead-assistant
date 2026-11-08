import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, session } from "../api.js";
import { Field } from "../components/ui.jsx";

export default function Login() {
  const nav = useNavigate();
  const [f, setF] = useState({ username: "", password: "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      const r = await api("/api/auth/login", { method: "POST", body: f });
      session.set(r);
      nav(r.role === "sales_head" ? "/dashboard" : "/leads");
    } catch (x) { setErr(x.message); } finally { setBusy(false); }
  }
  return (
    <div className="frame center">
      <div className="wm" aria-hidden="true">Aangan</div>
      <form className="card login" onSubmit={submit}>
        <h1>Staff sign in</h1>
        <Field label="Username"><input value={f.username} autoComplete="username" required onChange={(e) => setF({ ...f, username: e.target.value })} /></Field>
        <Field label="Password"><input type="password" value={f.password} autoComplete="current-password" required onChange={(e) => setF({ ...f, password: e.target.value })} /></Field>
        {err && <p className="err" role="alert">{err}</p>}
        <button className="btn dark" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
      </form>
    </div>
  );
}
