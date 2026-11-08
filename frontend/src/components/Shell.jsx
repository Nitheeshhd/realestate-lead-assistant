import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { session } from "../api.js";

const ic = (d) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{d}</svg>
);
const ICONS = {
  dash: ic(<path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />),
  leads: ic(<><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20c.6-3.6 3.2-5.5 6.5-5.5s5.9 1.9 6.5 5.5" /></>),
  hand: ic(<path d="M4 5h16v11H9l-5 4z" />),
  fact: ic(<><path d="M6 3h9l4 4v14H6z" /><path d="M9 12h7M9 16h7" /></>),
  slot: ic(<><rect x="3.5" y="5" width="17" height="15" rx="2" /><path d="M3.5 10h17M8 3v4M16 3v4" /></>),
};

export default function Shell() {
  const s = session.get();
  const nav = useNavigate();
  const head = s?.role === "sales_head";
  const links = [
    head && ["/dashboard", "Dashboard", "dash"],
    ["/leads", "Leads", "leads"],
    ["/handoffs", head ? "Handoffs and review" : "My handoffs", "hand"],
    head && ["/facts", "Fact sheet", "fact"],
    head && ["/slots", "Visit slots", "slot"],
  ].filter(Boolean);
  return (
    <div className="frame">
      <div className="wm" aria-hidden="true">Aangan</div>
      <div className="win">
        <aside className="side">
          <div className="logo">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="#2DBE4E" aria-hidden="true">
              <rect x="3" y="4" width="4" height="16" rx="1.5" /><rect x="10" y="4" width="4" height="16" rx="1.5" opacity=".75" /><rect x="17" y="4" width="4" height="16" rx="1.5" opacity=".5" />
            </svg>Aangan
          </div>
          <div className="cap">NAVIGATION</div>
          <nav className="nav" aria-label="Main">
            {links.map(([to, label, i]) => (
              <NavLink key={to} to={to} className={({ isActive }) => (isActive ? "on" : "")}>
                <span className="ic">{ICONS[i]}</span>{label}
              </NavLink>
            ))}
          </nav>
          <div className="spacer" />
          <div className="usr">
            <span className="av">{(s?.name || "?").slice(0, 2).toUpperCase()}</span>
            <span>{s?.name}<small>{head ? "Sales head" : "Sales executive"}</small></span>
          </div>
          <button className="signout" onClick={() => { session.clear(); nav("/login"); }}>Sign out</button>
        </aside>
        <main className="panel"><Outlet /></main>
      </div>
    </div>
  );
}
