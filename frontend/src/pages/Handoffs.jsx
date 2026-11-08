import { useState } from "react";
import { Link } from "react-router-dom";
import { api, session, useFetch, when } from "../api.js";
import { Empty, ErrorState, Pill, Skeleton } from "../components/ui.jsx";

function Card({ h, review, onDone }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  async function act(action) {
    setBusy(true); setErr("");
    try { await api(`/api/handoffs/${h.id}/${action}`, { method: "POST" }); onDone(); }
    catch (x) { setErr(x.message); }
    finally { setBusy(false); }
  }
  return (
    <article className="c">
      <div className="ch">
        <h2><Link to={`/leads/${h.lead_id}`}>{h.lead_name}</Link> <small className="sub2">{h.lead_code} · {h.source_label} · {h.project}</small></h2>
        <Pill tone={h.flagged ? "warn" : ""}>{h.reason.replace(/_/g, " ")}</Pill>
      </div>
      <p>{h.summary}</p>
      <small className="sub2">{when(h.created_at)} · {h.executive}{h.phone ? ` · ${h.phone}` : ""}</small>
      {err && <p className="err" role="alert">{err}</p>}
      <div className="row-btns">
        {!review && !h.acknowledged_at && <button className="btn dark" disabled={busy} onClick={() => act("ack")}>I'll contact them</button>}
        {!review && h.acknowledged_at && <Pill tone="ok">Contacted {when(h.acknowledged_at)}</Pill>}
        {review && <button className="btn dark" disabled={busy} onClick={() => act("review")}>Mark reviewed</button>}
      </div>
    </article>
  );
}

export default function Handoffs() {
  const head = session.get()?.role === "sales_head";
  const [tab, setTab] = useState("inbox");
  const { data, error, loading, reload } = useFetch(tab === "review" ? "/api/handoffs?review=1" : "/api/handoffs");
  return (
    <>
      <div className="top">
        <h1>{head ? "Handoffs and review" : "My handoffs"}</h1>
        {head && (
          <div className="topr">
            <button className={`chip ${tab === "inbox" ? "on" : ""}`} aria-pressed={tab === "inbox"} onClick={() => setTab("inbox")}>All handoffs</button>
            <button className={`chip ${tab === "review" ? "on" : ""}`} aria-pressed={tab === "review"} onClick={() => setTab("review")}>Daily review queue</button>
          </div>
        )}
      </div>
      {tab === "review" && <p className="sub2">Chats where the assistant refused a price, had no fact, or was blocked by a guardrail.</p>}
      {error && <ErrorState message={error} onRetry={reload} />}
      {loading && !data && <Skeleton h={120} n={3} />}
      {data && data.length === 0 && <Empty title={tab === "review" ? "Nothing to review" : "No handoffs yet"}>{tab === "review" ? "Flagged chats appear here." : "Serious buyers appear here with the chat summary."}</Empty>}
      {data && data.map((h) => <Card key={h.id} h={h} review={tab === "review"} onDone={reload} />)}
    </>
  );
}
