import { useState } from "react";
import { Link } from "react-router-dom";
import { api, dur, session, useFetch, when } from "../api.js";
import { Empty, ErrorState, Field, Pill, Skeleton } from "../components/ui.jsx";

const SOURCES = [["portal", "Property portal"], ["social", "Social media ad"], ["website", "Website"], ["hoarding", "Hoarding call"]];

function AddLead({ projects, onDone }) {
  const [f, setF] = useState({ name: "", phone: "", source: "portal", project_id: "", wants: "" });
  const [msg, setMsg] = useState(null);
  async function submit(e) {
    e.preventDefault();
    try {
      const r = await api("/api/leads", { method: "POST", body: { ...f, project_id: Number(f.project_id) } });
      setMsg({ ok: true, text: r.duplicate ? "Saved. This number already exists, so it is flagged as a duplicate." : "Lead saved." });
      setF({ ...f, name: "", phone: "" }); onDone();
    } catch (x) { setMsg({ ok: false, text: x.message }); }
  }
  return (
    <form className="c form-row" onSubmit={submit}>
      <Field label="Name"><input value={f.name} required onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
      <Field label="Mobile number"><input value={f.phone} required inputMode="tel" onChange={(e) => setF({ ...f, phone: e.target.value })} /></Field>
      <Field label="Source"><select value={f.source} onChange={(e) => setF({ ...f, source: e.target.value })}>{SOURCES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
      <Field label="Project"><select value={f.project_id} required onChange={(e) => setF({ ...f, project_id: e.target.value })}><option value="">Choose</option>{projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></Field>
      <button className="btn dark">Add lead</button>
      {msg && <p className={msg.ok ? "ok" : "err"} role="status">{msg.text}</p>}
    </form>
  );
}

export default function Leads() {
  const head = session.get()?.role === "sales_head";
  const [q, setQ] = useState("");
  const [source, setSource] = useState("");
  const [dups, setDups] = useState(false);
  const [adding, setAdding] = useState(false);
  const [importMsg, setImportMsg] = useState(null);
  const [importing, setImporting] = useState(false);
  const qs = new URLSearchParams({ ...(q && { q }), ...(source && { source }), ...(dups && { duplicates: "1" }) }).toString();
  const { data, error, loading, reload } = useFetch(`/api/leads?${qs}`);
  const projectState = useFetch("/api/public/projects");
  const projects = projectState.data || [];

  async function importCsv(e) {
    const file = e.target.files[0];
    if (!file) return;
    const form = new FormData(); form.append("file", file);
    setImporting(true); setImportMsg(null);
    try {
      const r = await api("/api/leads/import", { method: "POST", form });
      setImportMsg({ ok: true, text: `Imported ${r.created} leads (${r.duplicates} duplicates).${r.errors.length ? " " + r.errors.length + " rows skipped: " + r.errors[0] : ""}` });
      reload();
    } catch (x) { setImportMsg({ ok: false, text: x.message }); }
    finally { setImporting(false); e.target.value = ""; }
  }

  return (
    <>
      <div className="top">
        <h1>Leads</h1>
        <div className="topr">
          {head && <label className="btn">{importing ? "Importing…" : "Import CSV"}<input type="file" accept=".csv" hidden disabled={importing} onChange={importCsv} /></label>}
          <button className="dk" onClick={() => setAdding(!adding)}>{adding ? "Close" : "Add lead"}</button>
        </div>
      </div>
      {importMsg && <p className={importMsg.ok ? "ok" : "err"} role={importMsg.ok ? "status" : "alert"}>{importMsg.text} {importMsg.ok && "CSV columns: name, phone, source, project, wants."}</p>}
      {adding && projectState.error && <ErrorState message={projectState.error} onRetry={projectState.reload} />}
      {adding && projectState.loading && !projectState.data && <Skeleton h={48} />}
      {adding && <AddLead projects={projects} onDone={reload} />}
      <div className="filters">
        <input type="search" placeholder="Search name, code or number" aria-label="Search leads" value={q} onChange={(e) => setQ(e.target.value)} />
        <select aria-label="Source" value={source} onChange={(e) => setSource(e.target.value)}><option value="">All sources</option>{SOURCES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
        <label className="chk"><input type="checkbox" checked={dups} onChange={(e) => setDups(e.target.checked)} /> Duplicates only</label>
      </div>
      {error && <ErrorState message={error} onRetry={reload} />}
      {loading && !data && <Skeleton h={48} n={6} />}
      {data && data.length === 0 && <Empty title="No leads match">Clear the filters or add a lead.</Empty>}
      {data && data.length > 0 && (
        <section className="c scroll">
          <table>
            <thead><tr><th>Lead</th><th>Source</th><th>Project</th><th>Wants</th><th>Status</th><th>First reply</th><th>Executive</th><th>Created</th></tr></thead>
            <tbody>
              {data.map((l) => (
                <tr key={l.id}>
                  <td data-label="Lead"><Link to={`/leads/${l.id}`}><b>{l.name}</b></Link><small className="sub2">{l.code}</small>{l.is_duplicate && <Pill tone="warn">Duplicate of {l.duplicate_of}</Pill>}{l.opt_out && <Pill tone="warn">Opted out</Pill>}</td>
                  <td data-label="Source"><Pill>{l.source_label}</Pill></td>
                  <td data-label="Project">{l.project}</td>
                  <td data-label="Wants">{l.wants || "–"}</td>
                  <td data-label="Status">{l.status_label}</td>
                  <td data-label="First reply">{dur(l.response_seconds)}</td>
                  <td data-label="Executive">{l.assigned_to || "–"}</td>
                  <td data-label="Created">{when(l.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </>
  );
}
