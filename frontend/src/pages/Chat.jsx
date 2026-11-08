import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, useFetch } from "../api.js";
import { ErrorState, Field } from "../components/ui.jsx";

const TXT = {
  en: { title: "Find your home, and see it in person", sub: "Ask about the project and pick a time to visit. Replies come in seconds.", name: "Your name", phone: "Mobile number", project: "Project", lang: "Language",
    consent: "I agree to be contacted about this project on this number. I can opt out any time.", start: "Start chat", placeholder: "Type your message", send: "Send", person: "Talk to a person", stop: "Stop messages", typing: "Aangan is typing", rera: "RERA registration" },
  hi: { title: "अपना घर खोजें और खुद आकर देखें", sub: "प्रोजेक्ट के बारे में पूछें और विज़िट का समय चुनें। जवाब कुछ सेकंड में मिलता है।", name: "आपका नाम", phone: "मोबाइल नंबर", project: "प्रोजेक्ट", lang: "भाषा",
    consent: "मैं इस नंबर पर इस प्रोजेक्ट के बारे में संपर्क किए जाने के लिए सहमत हूँ। मैं कभी भी बंद कर सकता/सकती हूँ।", start: "चैट शुरू करें", placeholder: "अपना संदेश लिखें", send: "भेजें", person: "किसी व्यक्ति से बात करें", stop: "संदेश बंद करें", typing: "आँगन लिख रहा है", rera: "RERA पंजीकरण" },
  gu: { title: "તમારું ઘર શોધો અને રૂબરૂ જુઓ", sub: "પ્રોજેક્ટ વિશે પૂછો અને મુલાકાતનો સમય પસંદ કરો. જવાબ સેકન્ડોમાં મળે છે.", name: "તમારું નામ", phone: "મોબાઇલ નંબર", project: "પ્રોજેક્ટ", lang: "ભાષા",
    consent: "હું આ નંબર પર આ પ્રોજેક્ટ વિશે સંપર્ક કરવા સંમત છું. હું ગમે ત્યારે બંધ કરી શકું છું.", start: "ચેટ શરૂ કરો", placeholder: "તમારો સંદેશ લખો", send: "મોકલો", person: "વ્યક્તિ સાથે વાત કરો", stop: "સંદેશા બંધ કરો", typing: "આંગણ લખી રહ્યું છે", rera: "RERA નોંધણી" },
};
const KEY = "aangan_chat";

function quickReplyLabel(reply, lang) {
  const labels = {
    hi: {
      "2 BHK": "2 बीएचके", "3 BHK": "3 बीएचके",
      "₹80 lakh or less": "₹80 लाख या कम", "₹80 lakh–₹1 crore": "₹80 लाख–₹1 करोड़",
      "Above ₹1 crore": "₹1 करोड़ से अधिक", "Show free visit slots": "मुफ़्त विज़िट स्लॉट दिखाएँ",
    },
    gu: {
      "2 BHK": "2 BHK", "3 BHK": "3 BHK",
      "₹80 lakh or less": "₹80 લાખ અથવા ઓછું", "₹80 lakh–₹1 crore": "₹80 લાખ–₹1 કરોડ",
      "Above ₹1 crore": "₹1 કરોડથી વધુ", "Show free visit slots": "મફત મુલાકાતના સ્લોટ બતાવો",
    },
  };
  return labels[lang]?.[reply] || reply;
}

export default function Chat() {
  const [params] = useSearchParams();
  const projects = useFetch("/api/public/projects");
  const [lang, setLang] = useState("en");
  const [form, setForm] = useState({ name: "", phone: "", project_id: "", consent: false });
  const [sess, setSess] = useState(() => { try { return JSON.parse(sessionStorage.getItem(KEY)); } catch { return null; } });
  const [log, setLog] = useState(sess?.history || []);
  const [slots, setSlots] = useState(null);
  const [quickReplies, setQuickReplies] = useState(null);
  const [booking, setBooking] = useState(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [optedOut, setOptedOut] = useState(Boolean(sess?.opt_out));
  const [err, setErr] = useState("");
  const end = useRef(null);
  const t = TXT[lang];

  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [log, slots, booking, busy]);

  async function start(e) {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      const src = ["portal", "social", "website", "hoarding"].includes(params.get("src")) ? params.get("src") : "website";
      const r = await api("/api/chat/start", { method: "POST", body: { ...form, project_id: Number(form.project_id || projects.data?.[0]?.id), language: lang, source: src } });
      const s = { lead_id: r.lead_id, token: r.token, rera_no: r.rera_no, project: r.project, history: r.history, opt_out: r.opt_out };
      sessionStorage.setItem(KEY, JSON.stringify(s));
      setSess(s); setLog(r.history); setOptedOut(Boolean(r.opt_out));
      if (r.history.length === 0) await send("Hi", s);
    } catch (x) { setErr(x.message); } finally { setBusy(false); }
  }

  async function send(message, s = sess) {
    if (!message.trim() || !s || optedOut) return;
    setErr(""); setBusy(true); setSlots(null);
    setQuickReplies(null);
    setLog((l) => [...l, { role: "user", content: message }]);
    try {
      const r = await api(`/api/chat/${s.lead_id}/message`, { method: "POST", body: { token: s.token, message } });
      setLog((l) => [...l, { role: "assistant", content: r.reply }]);
      setSlots(r.slots); setQuickReplies(r.quick_replies); setOptedOut(Boolean(r.opt_out));
      const next = { ...s, opt_out: Boolean(r.opt_out) };
      sessionStorage.setItem(KEY, JSON.stringify(next)); setSess(next);
      if (r.booking) setBooking(r.booking);
      if (r.language && r.language !== lang) setLang(r.language);
    } catch (x) { setErr(x.message); } finally { setBusy(false); }
  }

  async function optOut() {
    await send("STOP");
  }

  if (!sess) {
    return (
      <div className="chatpage">
        <div className="wm light" aria-hidden="true">Aangan</div>
        <form className="card intro" onSubmit={start}>
          <h1>{t.title}</h1>
          <p className="sub2">{t.sub}</p>
          <Field label={t.lang}>
            <select value={lang} onChange={(e) => setLang(e.target.value)}><option value="en">English</option><option value="hi">हिन्दी</option><option value="gu">ગુજરાતી</option></select>
          </Field>
          <Field label={t.name}><input value={form.name} required maxLength={120} autoComplete="name" onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
          <Field label={t.phone}><input value={form.phone} required inputMode="tel" autoComplete="tel" onChange={(e) => setForm({ ...form, phone: e.target.value })} /></Field>
          <Field label={t.project}>
            <select value={form.project_id} onChange={(e) => setForm({ ...form, project_id: e.target.value })}>{(projects.data || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
          </Field>
          {projects.loading && !projects.data && <p className="sub2" role="status">Loading projects…</p>}
          <label className="chk consent"><input type="checkbox" required checked={form.consent} onChange={(e) => setForm({ ...form, consent: e.target.checked })} /> {t.consent}</label>
          {projects.error && <ErrorState message={projects.error} onRetry={projects.reload} />}
          {err && <p className="err" role="alert">{err}</p>}
          <button className="btn dark" disabled={busy || projects.loading || Boolean(projects.error) || !projects.data?.length}>{busy ? "…" : t.start}</button>
          <Link className="stafflink" to="/login">Staff sign in</Link>
        </form>
      </div>
    );
  }

  return (
    <div className="chatpage">
      <div className="wm light" aria-hidden="true">Aangan</div>
      <div className="card chatbox">
        <header className="chathead"><b>Aangan</b><span>{sess.project}</span></header>
        <div className="log" aria-live="polite">
          {log.map((m, i) => <div key={i} className={`bub ${m.role}`}>{m.content}</div>)}
          {busy && <div className="bub assistant typing" aria-label={t.typing}><i /><i /><i /></div>}
          {quickReplies?.length > 0 && (
            <div className="slots" aria-label="Suggested replies">
              {quickReplies.map((reply) => <button key={reply} className="chip" disabled={busy} onClick={() => send(quickReplyLabel(reply, lang))}>{quickReplyLabel(reply, lang)}</button>)}
            </div>
          )}
          {slots && slots.length > 0 && (
            <div className="slots">
              {slots.map((s) => <button key={s.slot_id} className="chip" disabled={busy} onClick={() => send(`Please book slot #${s.slot_id} (${s.label})`)}>{s.label}</button>)}
            </div>
          )}
          {booking && (
            <div className="confirm">
              <b>{booking.when}</b>
              <p>{booking.project} · {booking.executive}</p>
              {booking.address && <p className="sub2">{booking.address}</p>}
              {booking.map_url && <a className="btn" href={booking.map_url} target="_blank" rel="noreferrer">Open location pin</a>}
            </div>
          )}
          <div ref={end} />
        </div>
        {err && <p className="err pad" role="alert">{err}</p>}
        {optedOut && <p className="sub2 pad" role="status">You have opted out. We will not send you any more messages.</p>}
        <form className="composer" onSubmit={(e) => { e.preventDefault(); const m = text; setText(""); send(m); }}>
          <input value={text} maxLength={600} placeholder={t.placeholder} aria-label={t.placeholder} disabled={busy || optedOut} onChange={(e) => setText(e.target.value)} />
          <button className="btn dark" disabled={busy || optedOut || !text.trim()}>{t.send}</button>
        </form>
        <footer className="chatfoot">
          <button className="linkbtn" disabled={busy || optedOut} onClick={() => send("I want to talk to a person")}>{t.person}</button>
          <button className="linkbtn" disabled={busy || optedOut} onClick={optOut}>{t.stop}</button>
          <span>{t.rera}: {sess.rera_no}</span>
        </footer>
      </div>
    </div>
  );
}
