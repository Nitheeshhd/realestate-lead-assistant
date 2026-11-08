import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, dur, useFetch, when } from "../api.js";
import { ErrorState, Pill, Skeleton } from "../components/ui.jsx";

export default function LeadDetail() {
  const { id } = useParams();
  const { data: l, error, loading, reload } = useFetch(`/api/leads/${id}`);
  const [msg, setMsg] = useState("");

  async function mark(visitId, status) {
    setMsg("");
    try { await api(`/api/visits/${visitId}/status`, { method: "POST", body: { status } }); reload(); }
    catch (x) { setMsg(x.message); }
  }
  if (loading && !l) return <Skeleton h={120} n={3} />;
  if (error) return <ErrorState message={error} onRetry={reload} />;
  return (
    <>
      <div className="top"><h1>{l.name}</h1><Link className="btn" to="/leads">Back to leads</Link></div>
      <section className="c grid2">
        <div><div className="kl">Code</div><b>{l.code}</b></div>
        <div><div className="kl">Source</div><b>{l.source_label}</b></div>
        <div><div className="kl">Project</div><b>{l.project}</b></div>
        <div><div className="kl">Wants</div><b>{l.wants || "–"}</b></div>
        <div><div className="kl">Budget</div><b>{l.budget || "–"}</b></div>
        <div><div className="kl">Language</div><b>{{ en: "English", hi: "Hindi", gu: "Gujarati" }[l.language]}</b></div>
        <div><div className="kl">Mobile</div><b>{l.phone}</b></div>
        <div><div className="kl">First reply</div><b>{dur(l.response_seconds)}</b></div>
      </section>
      {l.handoffs[0] && <section className="c"><h2>Summary for the executive</h2><p>{l.handoffs[0].summary}</p></section>}
      <div className="cols">
        <section className="c">
          <h2>Chat history</h2>
          {l.messages.length === 0 && <p className="sub2">The buyer has not chatted yet.</p>}
          <div className="log">
            {l.messages.map((m, i) => (
              <div key={i} className={`bub ${m.role} ${m.flagged ? "flag" : ""}`}>
                {m.content}
                {m.flagged && <small>Flagged: {m.flag_reason.replace(/_/g, " ")}</small>}
              </div>
            ))}
          </div>
        </section>
        <section className="c">
          <h2>Visits</h2>
          {msg && <p className="err" role="alert">{msg}</p>}
          {l.visits.length === 0 && <p className="sub2">No visit booked.</p>}
          {l.visits.map((v) => (
            <div key={v.id} className="visit">
              <b>{when(v.start)}</b> <Pill tone={v.status === "booked" ? "" : v.status === "visited" ? "ok" : "warn"}>{v.status.replace("_", " ")}</Pill>
              <small className="sub2">with {v.executive}</small>
              {v.reminders.map((r, i) => <small key={i} className="sub2">{r.kind}: {r.status}</small>)}
              {v.status === "booked" && (
                <div className="row-btns">
                  <button className="btn" onClick={() => mark(v.id, "visited")}>Mark visited</button>
                  <button className="btn" onClick={() => mark(v.id, "no_show")}>No show</button>
                  <button className="btn" onClick={() => mark(v.id, "cancelled")}>Cancel</button>
                </div>
              )}
            </div>
          ))}
        </section>
      </div>
    </>
  );
}
