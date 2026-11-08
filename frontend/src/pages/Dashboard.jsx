import { useMemo, useState } from "react";
import { dur, inr, pct, useFetch } from "../api.js";
import { Empty, ErrorState, Skeleton } from "../components/ui.jsx";

const iso = (d) => d.toISOString().slice(0, 10);

function Bars({ series }) {
  const max = Math.max(1, ...series.map((s) => s.visits));
  const peak = series.findIndex((s) => s.visits === max);
  const top = Math.ceil(max / 5) * 5 || 5;
  return (
    <>
      <div className="chart">
        <div className="yl">{[1, .8, .6, .4, .2, 0].map((f) => <span key={f}>{Math.round(top * f)}</span>)}</div>
        <div className="bars" role="img" aria-label={`Site visits per day, peak ${max}`}>
          {series.map((s, i) => (
            <i key={s.date} title={`${s.date}: ${s.visits}`} style={{ height: `${(s.visits / top) * 100}%`, background: i === peak && max > 0 ? "#0B1510" : i > series.length / 2 ? "#2DBE4E" : "#D3DCD6" }}>
              {i === peak && max > 0 && <span className="tip">{s.visits} visits</span>}
            </i>
          ))}
        </div>
      </div>
      <div className="xl"><span>{series[0]?.date.slice(5)}</span><span>{series[series.length - 1]?.date.slice(5)}</span></div>
    </>
  );
}

export default function Dashboard() {
  const [days, setDays] = useState(30);
  const [project, setProject] = useState("");
  const path = useMemo(() => {
    const to = new Date();
    const from = new Date(Date.now() - (days - 1) * 864e5);
    return `/api/dashboard?from=${iso(from)}&to=${iso(to)}${project ? `&project=${project}` : ""}`;
  }, [days, project]);
  const { data, error, loading, reload } = useFetch(path);
  const projectState = useFetch("/api/public/projects");
  const projects = projectState.data || [];

  const t = data?.totals;
  const best = data?.sources.find((s) => s.flag === "best");
  const worst = data?.sources.find((s) => s.flag === "review");

  return (
    <>
      <div className="top">
        <h1>Dashboard</h1>
        <div className="topr">
          {[7, 30, 90].map((d) => <button key={d} className={`chip ${days === d ? "on" : ""}`} aria-pressed={days === d} onClick={() => setDays(d)}>{d} days</button>)}
          <select aria-label="Project" value={project} onChange={(e) => setProject(e.target.value)}>
            <option value="">All projects</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
      </div>

      {projectState.error && <ErrorState message={projectState.error} onRetry={projectState.reload} />}
      {error && <ErrorState message={error} onRetry={reload} />}
      {loading && !data && <Skeleton h={110} n={3} />}
      {data && t.leads === 0 && <Empty title="No leads in this range">Try a longer range or another project.</Empty>}
      {data && t.leads > 0 && (
        <>
          <section className="kp" aria-label="Headline numbers">
            <div className="k dk1"><div className="kl">Median first response</div><div className="kv">{dur(t.median_response_s)}</div><div className="kd up">Target under 5 min, was 14 hours</div>
              <div className="kl" style={{ marginTop: 6 }}>Human contact: {dur(t.median_human_contact_s)}</div></div>
            <div className="k"><div className="kl">Not reached in 48 h</div><div className="kv">{pct(t.not_reached_48h_pct)}</div><div className="kd up">Target under 5%, was 35%</div></div>
            <div className="k"><div className="kl">Lead to visit</div><div className="kv">{pct(t.lead_to_visit_pct)}</div><div className="kd up">Target 8%, was 6%</div></div>
          </section>
          <div className="cols">
            <div className="left">
              <section className="c">
                <div className="ch"><h2>Site visits per day</h2></div>
                <Bars series={data.daily_visits} />
              </section>
              <section className="c">
                <div className="ch"><h2>Leads by source</h2></div>
                <div className="scroll">
                  <table>
                    <thead><tr><th>Source</th><th>Leads</th><th>Response</th><th>Booked</th><th>Visited</th><th>Show-up</th><th>Spend</th><th>Cost / visit</th></tr></thead>
                    <tbody>
                      {data.sources.map((s) => (
                        <tr key={s.source}>
                          <td data-label="Source"><b>{s.label}</b>{s.flag === "best" && <span className="tag b">Best</span>}{s.flag === "review" && <span className="tag w">Review</span>}</td>
                          <td data-label="Leads">{s.leads}</td>
                          <td data-label="Response">{dur(s.median_response_s)}</td>
                          <td data-label="Booked">{s.booked}</td>
                          <td data-label="Visited">{s.visited}</td>
                          <td data-label="Show-up">{pct(s.show_up_pct)}</td>
                          <td data-label="Spend">{inr(s.spend)}</td>
                          <td data-label="Cost / visit"><b>{inr(s.cost_per_visit)}</b></td>
                        </tr>
                      ))}
                      <tr className="tot">
                        <td data-label="Source">All sources</td><td data-label="Leads">{t.leads}</td><td data-label="Response">{dur(t.median_response_s)}</td>
                        <td data-label="Booked">{t.booked}</td><td data-label="Visited">{t.visited}</td><td data-label="Show-up">{pct(t.show_up_pct)}</td>
                        <td data-label="Spend">{inr(t.spend)}</td><td data-label="Cost / visit">{inr(t.cost_per_visit)}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </section>
            </div>
            <div className="right">
              <section className="big">
                <div className="kl">Cost per visit</div>
                <div className="bv">{inr(t.cost_per_visit)}</div>
                <div className="kd up">{inr(t.spend)} spend ÷ {t.visited} visits</div>
                {best && <div className="li"><span className="lic">1</span><div><b>{best.label}</b><small>Lowest · {inr(best.cost_per_visit)} per visit</small></div></div>}
                {worst && <div className="li"><span className="lic">2</span><div><b>{worst.label}</b><small>Highest · {inr(worst.cost_per_visit)} per visit</small></div></div>}
              </section>
              <section className="map">
                <div className="ch w"><h2>Visit slots, next 7 days</h2></div>
                <div className="mt"><b>{data.slot_utilisation.booked}</b> of {data.slot_utilisation.total} slots booked
                  {data.slot_utilisation.pct != null && <span className="hl">{data.slot_utilisation.pct}%</span>}</div>
              </section>
            </div>
          </div>
          <p className="foot">Show-up = visited ÷ (visited + no-show). Spend is pro-rated by day. Cost per visit shows – when there are no visits.</p>
        </>
      )}
    </>
  );
}
