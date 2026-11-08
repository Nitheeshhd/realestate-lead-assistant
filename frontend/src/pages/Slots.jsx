import { useState } from "react";
import { api, useFetch, when } from "../api.js";
import { Empty, ErrorState, Field, Pill, Skeleton } from "../components/ui.jsx";

const HOURS = [10, 11, 12, 13, 14, 15, 16, 17, 18];
const EDIT_HOURS = Array.from({ length: 14 }, (_, i) => i + 7);

export default function Slots() {
  const projectState = useFetch("/api/public/projects");
  const executiveState = useFetch("/api/executives");
  const projects = projectState.data || [];
  const execs = executiveState.data || [];
  const [project, setProject] = useState("");
  const [exe, setExe] = useState("");
  const [date, setDate] = useState(new Date(Date.now() + 864e5).toISOString().slice(0, 10));
  const [hours, setHours] = useState([10, 11, 15]);
  const [msg, setMsg] = useState(null);
  const [rem, setRem] = useState(null);
  const [saving, setSaving] = useState(false);
  const [remBusy, setRemBusy] = useState(false);
  const [editing, setEditing] = useState(null);
  const [editSaving, setEditSaving] = useState(false);
  const pid = project || projects[0]?.id || "";
  const { data, error, loading, reload } = useFetch(`/api/slots?project=${pid || 0}`);
  const log = useFetch("/api/reminders");

  async function create(e) {
    e.preventDefault();
    setSaving(true); setMsg(null);
    try {
      const r = await api("/api/slots", { method: "POST", body: { project: Number(pid), executive: Number(exe || execs[0]?.id), date, hours } });
      setMsg({ ok: true, text: `${r.created} new slots opened.` }); reload();
    } catch (x) { setMsg({ ok: false, text: x.message }); }
    finally { setSaving(false); }
  }
  async function del(id) {
    try { await api(`/api/slots/${id}`, { method: "DELETE" }); reload(); } catch (x) { setMsg({ ok: false, text: x.message }); }
  }
  function editSlot(slot) {
    const start = new Date(slot.start);
    setMsg(null);
    setEditing({
      id: slot.id,
      project: String(slot.project_id),
      executive: String(slot.executive_id),
      date: `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, "0")}-${String(start.getDate()).padStart(2, "0")}`,
      hour: String(start.getHours()),
    });
  }
  async function saveEdit(e) {
    e.preventDefault();
    setEditSaving(true); setMsg(null);
    try {
      await api(`/api/slots/${editing.id}`, {
        method: "PATCH",
        body: { project: Number(editing.project), executive: Number(editing.executive), date: editing.date, hour: Number(editing.hour) },
      });
      setEditing(null); setMsg({ ok: true, text: "Slot updated." }); reload();
    } catch (x) { setMsg({ ok: false, text: x.message }); }
    finally { setEditSaving(false); }
  }
  async function runReminders() {
    setRemBusy(true); setRem(null);
    try {
      const r = await api("/api/reminders/run", { method: "POST" });
      setRem({ ok: true, text: `${r.sent} reminders sent, ${r.skipped} skipped (opted out or cancelled).` }); log.reload();
    } catch (x) { setRem({ ok: false, text: x.message }); }
    finally { setRemBusy(false); }
  }

  return (
    <>
      <div className="top"><h1>Visit slots</h1>
        <select aria-label="Project" value={pid} onChange={(e) => setProject(e.target.value)}>{projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></div>
      {projectState.error && <ErrorState message={projectState.error} onRetry={projectState.reload} />}
      {executiveState.error && <ErrorState message={executiveState.error} onRetry={executiveState.reload} />}
      {(projectState.loading && !projectState.data || executiveState.loading && !executiveState.data) && <Skeleton h={48} />}
      <form className="c form-row" onSubmit={create}>
        <Field label="Executive"><select value={exe || execs[0]?.id || ""} onChange={(e) => setExe(e.target.value)}>{execs.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></Field>
        <Field label="Date"><input type="date" value={date} required onChange={(e) => setDate(e.target.value)} /></Field>
        <div className="field"><span>Hours (1-hour visits)</span>
          <div className="chips">{HOURS.map((h) => <button type="button" key={h} className={`chip ${hours.includes(h) ? "on" : ""}`} aria-pressed={hours.includes(h)} onClick={() => setHours(hours.includes(h) ? hours.filter((x) => x !== h) : [...hours, h])}>{h}:00</button>)}</div></div>
        <button className="btn dark" disabled={!hours.length || !pid || !execs.length || saving || projectState.loading || executiveState.loading}>{saving ? "Opening…" : "Open slots"}</button>
        {msg && <p className={msg.ok ? "ok" : "err"} role="status">{msg.text}</p>}
      </form>
      {editing && (
        <form className="c form-row" onSubmit={saveEdit}>
          <h2>Update visit slot</h2>
          <Field label="Project"><select value={editing.project} onChange={(e) => setEditing({ ...editing, project: e.target.value })}>{projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></Field>
          <Field label="Executive"><select value={editing.executive} onChange={(e) => setEditing({ ...editing, executive: e.target.value })}>{execs.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></Field>
          <Field label="Date"><input type="date" value={editing.date} required onChange={(e) => setEditing({ ...editing, date: e.target.value })} /></Field>
          <Field label="Hour"><select value={editing.hour} onChange={(e) => setEditing({ ...editing, hour: e.target.value })}>{EDIT_HOURS.map((h) => <option key={h} value={h}>{h}:00</option>)}</select></Field>
          <div className="row-btns">
            <button className="btn dark" disabled={editSaving}>{editSaving ? "Saving…" : "Save slot"}</button>
            <button type="button" className="btn" disabled={editSaving} onClick={() => setEditing(null)}>Cancel</button>
          </div>
        </form>
      )}
      {error && <ErrorState message={error} onRetry={reload} />}
      {loading && !data && <Skeleton h={48} n={4} />}
      {data && data.length === 0 && <Empty title="No upcoming slots">Open some above so the assistant can book visits.</Empty>}
      {data && data.length > 0 && (
        <section className="c scroll"><table>
          <thead><tr><th>Start</th><th>Executive</th><th>State</th><th></th></tr></thead>
          <tbody>{data.map((s) => (
            <tr key={s.id}><td data-label="Start"><b>{when(s.start)}</b></td><td data-label="Executive">{s.executive}</td>
              <td data-label="State"><Pill tone={s.booked ? "ok" : ""}>{s.booked ? "Booked" : "Free"}</Pill></td>
              <td data-label=""><div className="row-btns">
                <button className="btn" disabled={s.booked} onClick={() => editSlot(s)}>Edit</button>
                <button className="btn" disabled={s.booked} onClick={() => del(s.id)}>Remove</button>
              </div></td></tr>
          ))}</tbody></table></section>
      )}
      <section className="c">
        <div className="ch"><h2>Reminders</h2><button className="btn dark" disabled={remBusy} onClick={runReminders}>{remBusy ? "Sending…" : "Send due reminders now"}</button></div>
        <p className="sub2">Reminders go out 1 day and 2 hours before each visit. Messages are mocked: they are stored and logged, not sent.</p>
        {rem && <p className={rem.ok ? "ok" : "err"} role="status">{rem.text}</p>}
        {log.error && <ErrorState message={log.error} onRetry={log.reload} />}
        {log.loading && !log.data && <Skeleton h={40} />}
        {(log.data || []).slice(0, 6).map((r) => <p key={r.id} className="remline"><b>{r.lead}</b> · {r.kind} · {r.status}<br /><small className="sub2">{r.body}</small></p>)}
      </section>
    </>
  );
}
