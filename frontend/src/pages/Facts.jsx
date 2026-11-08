import { useState } from "react";
import { api, useFetch } from "../api.js";
import { Empty, ErrorState, Field, Skeleton } from "../components/ui.jsx";

export default function Facts() {
  const projects = useFetch("/api/public/projects");
  const [pid, setPid] = useState("");
  const project = pid || projects.data?.[0]?.id || "";
  const { data, error, loading, reload } = useFetch(project ? `/api/facts?project=${project}` : "/api/facts?project=0");
  const [f, setF] = useState({ key: "", value: "" });
  const [msg, setMsg] = useState(null);

  async function save(e) {
    e.preventDefault();
    try {
      await api("/api/facts", { method: "POST", body: { project: Number(project), ...f } });
      setF({ key: "", value: "" }); setMsg({ ok: true, text: "Saved. The assistant uses it from the next message." }); reload();
    } catch (x) { setMsg({ ok: false, text: x.message }); }
  }
  async function del(id) {
    setMsg(null);
    try { await api(`/api/facts/${id}`, { method: "DELETE" }); reload(); }
    catch (x) { setMsg({ ok: false, text: x.message }); }
  }

  return (
    <>
      <div className="top">
        <h1>Fact sheet</h1>
        <select aria-label="Project" value={project} disabled={projects.loading || !projects.data?.length} onChange={(e) => setPid(e.target.value)}>{(projects.data || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
      </div>
      {projects.error && <ErrorState message={projects.error} onRetry={projects.reload} />}
      {projects.loading && !projects.data && <Skeleton h={48} />}
      <p className="sub2">The assistant can only state what is written here. Anything missing is passed to a person.</p>
      <form className="c form-row" onSubmit={save}>
        <Field label="Topic (e.g. possession)"><input value={f.key} required onChange={(e) => setF({ ...f, key: e.target.value })} /></Field>
        <Field label="What the assistant may say"><textarea rows={2} value={f.value} required onChange={(e) => setF({ ...f, value: e.target.value })} /></Field>
        <button className="btn dark" disabled={!project || projects.loading || Boolean(projects.error)}>Save fact</button>
        {msg && <p className={msg.ok ? "ok" : "err"} role="status">{msg.text}</p>}
      </form>
      {error && <ErrorState message={error} onRetry={reload} />}
      {loading && !data && <Skeleton h={56} n={4} />}
      {data && data.length === 0 && <Empty title="No facts yet">Add the first one above. Typing an existing topic updates it.</Empty>}
      {data && data.map((x) => (
        <article key={x.id} className="c fact">
          <div><b>{x.key.replace(/_/g, " ")}</b><p>{x.value}</p></div>
          <button className="btn" onClick={() => del(x.id)} aria-label={`Delete ${x.key}`}>Delete</button>
        </article>
      ))}
    </>
  );
}
