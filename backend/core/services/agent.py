"""Chat agent. Two interchangeable brains share the same tools and the same guardrails:
the Anthropic tool-use loop (when ANTHROPIC_API_KEY is set) and an offline rule agent."""
import logging
import re

from django.conf import settings
from django.utils import timezone

from core.models import ChatMessage, FactSheetEntry
from core.services import guardrails
from core.services.booking import SlotUnavailable, book_visit, free_slots
from core.services.handoff import create_handoff

log = logging.getLogger("aangan.agent")

SYSTEM = """You are Aangan, the assistant of a residential developer in Ahmedabad.
Rules you must follow:
- State facts ONLY from search_fact_sheet results. If the fact is missing, say a team member will confirm and call handoff_to_human with reason "missing_fact". Never guess.
- Never quote a final price, discount, offer or negotiate. If asked, say a team member will confirm and call handoff_to_human with reason "price_request".
- Reply in the buyer's language ({lang}: en English, hi Hindi, gu Gujarati). Keep replies to 2-3 short sentences.
- Learn the buyer's BHK need (2 or 3 BHK) and budget, one question at a time, and store them with save_lead_profile.
- To book a visit call get_free_slots, let the buyer choose, then call book_visit with a slot_id returned by get_free_slots. Never invent a slot_id.
- If the buyer wants a person, call handoff_to_human at once.
- Never give legal, loan or investment advice. Do not make claims beyond the fact sheet.
Project: {project}. Buyer name: {name}."""

TOOLS = [
    {"name": "search_fact_sheet", "description": "Search the project fact sheet. Returns matching facts.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "get_free_slots", "description": "List real free site-visit slots for this buyer's project.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "book_visit", "description": "Book a slot returned by get_free_slots.",
     "input_schema": {"type": "object", "properties": {"slot_id": {"type": "integer"}}, "required": ["slot_id"]}},
    {"name": "save_lead_profile", "description": "Save what the buyer wants.",
     "input_schema": {"type": "object", "properties": {"wants": {"type": "string", "description": "2 BHK or 3 BHK"},
                                                       "budget": {"type": "string"}, "language": {"type": "string", "enum": ["en", "hi", "gu"]}}}},
    {"name": "handoff_to_human", "description": "Hand the chat to a named sales executive.",
     "input_schema": {"type": "object", "properties": {"reason": {"type": "string"}}, "required": ["reason"]}},
]

STOPWORDS = set("the a an is are of for in on to and what whats tell me about do you have there it with how much".split())
SYNONYMS = {"price": ["price", "cost", "rate", "budget", "कीमत", "भाव", "ભાવ", "किंमत"],
            "possession": ["possession", "ready", "handover", "कब्जा", "पज़ेशन", "પઝેશન"],
            "amenit": ["amenit", "facilit", "सुविधा", "સુવિધા"],
            "location": ["location", "where", "address", "metro", "जगह", "कहाँ", "ક્યાં", "સ્થળ"],
            "bhk": ["bhk", "bedroom", "type", "configuration", "size", "area", "carpet", "sqft"],
            "parking": ["parking", "पार्किंग", "પાર્કિંગ"],
            "rera": ["rera", "registration", "रेरा", "રેરા"]}


class Ctx:
    def __init__(self, lead):
        self.lead = lead
        self.shown_slots = set()
        self.slots_ui = None
        self.quick_replies = None
        self.booking = None
        self.handoff = None
        self.fact_hits = []


def search_facts(project, query, limit=3):
    q = query.lower()
    toks = {t for t in re.findall(r"[\w₹]+", q) if t not in STOPWORDS and len(t) > 1}
    wanted = {k for k, words in SYNONYMS.items() if any(w in q for w in words)}
    scored = []
    for f in FactSheetEntry.objects.filter(project=project):
        text = f"{f.key} {f.value}".lower()
        score = sum(2 for k in wanted if k in f.key.lower())
        score += sum(1 for t in toks if t in text)
        if score:
            scored.append((score, f))
    scored.sort(key=lambda x: -x[0])
    return [{"key": f.key.replace("_", " "), "value": f.value} for _, f in scored[:limit]]


def _slot_label(s):
    return timezone.localtime(s.start).strftime("%a %d %b, %I:%M %p")


def run_tool(ctx, name, args):
    lead = ctx.lead
    if name == "search_fact_sheet":
        hits = search_facts(lead.project, args.get("query", ""))
        ctx.fact_hits += hits
        return {"facts": hits} if hits else {"facts": [], "note": "No matching fact. Hand off."}
    if name == "get_free_slots":
        slots = list(free_slots(lead.project))
        ctx.shown_slots = {s.id for s in slots}
        ctx.slots_ui = [
            {"slot_id": s.id, "label": f"{_slot_label(s)} · {s.executive.get_full_name() or s.executive.username}",
             "start": s.start.isoformat()}
            for s in slots
        ]
        return {"slots": ctx.slots_ui}
    if name == "book_visit":
        sid = args.get("slot_id")
        if sid not in ctx.shown_slots:  # the model may only book what it was shown
            return {"ok": False, "reason": "slot_id was not returned by get_free_slots"}
        try:
            visit = book_visit(lead.id, sid)
        except SlotUnavailable as e:
            return {"ok": False, "reason": e.reason}
        p = lead.project
        ctx.booking = {"visit_id": visit.id, "when": _slot_label(visit.slot), "project": p.name,
                       "executive": visit.slot.executive.get_full_name() or visit.slot.executive.username,
                       "map_url": p.map_url, "address": p.address, "rera_no": p.rera_no}
        ctx.slots_ui = None
        return {"ok": True, **ctx.booking}
    if name == "save_lead_profile":
        for f in ("wants", "budget", "language"):
            if args.get(f):
                setattr(lead, f, str(args[f])[:60])
        lead.save()
        return {"ok": True}
    if name == "handoff_to_human":
        flagged = args.get("reason", "") in ("missing_fact", "price_request", "discount_request", "refused_reply")
        ctx.handoff = create_handoff(lead, str(args.get("reason", "requested"))[:60], flagged=flagged)
        return {"ok": True, "executive": ctx.handoff.executive.get_full_name() or ctx.handoff.executive.username}
    return {"error": "unknown tool"}


# ---------- offline rule agent ----------
T = {
 "hello": {"en": "Hello {name}, I'm Aangan. I can answer questions about {project} and book a site visit. Are you looking for a 2 or 3 BHK?",
           "hi": "नमस्ते {name}, मैं आँगन हूँ। मैं {project} के बारे में बता सकता हूँ और साइट विज़िट बुक कर सकता हूँ। आपको 2 या 3 BHK चाहिए?",
           "gu": "નમસ્તે {name}, હું આંગણ છું. હું {project} વિશે જણાવી શકું અને સાઇટ વિઝિટ બુક કરી શકું. તમને 2 કે 3 BHK જોઈએ છે?"},
 "ask_bhk": {"en": "Are you looking for a 2 or 3 BHK?", "hi": "आपको 2 या 3 BHK चाहिए?", "gu": "તમને 2 કે 3 BHK જોઈએ છે?"},
 "ask_budget": {"en": "Noted. What budget range are you comfortable with?", "hi": "ठीक है। आपका बजट कितना है?", "gu": "સરસ. તમારું બજેટ કેટલું છે?"},
 "offer_visit": {"en": "Thanks. Would you like to see the site? I can show free visit slots.", "hi": "धन्यवाद। क्या आप साइट देखना चाहेंगे? मैं खाली स्लॉट दिखा सकता हूँ।", "gu": "આભાર. શું તમે સાઇટ જોવા માંગો છો? હું ખાલી સ્લોટ બતાવી શકું."},
 "slots": {"en": "Here are the free slots. Pick one and I'll book it.", "hi": "ये खाली स्लॉट हैं। एक चुनें, मैं बुक कर दूँगा।", "gu": "આ ખાલી સ્લોટ છે. એક પસંદ કરો, હું બુક કરી દઈશ."},
 "no_slots": {"en": "There are no free slots in the next 7 days. A team member will contact you.", "hi": "अगले 7 दिनों में कोई खाली स्लॉट नहीं है। हमारी टीम आपसे संपर्क करेगी।", "gu": "આગામી 7 દિવસમાં કોઈ ખાલી સ્લોટ નથી. અમારી ટીમ તમારો સંપર્ક કરશે."},
 "booked": {"en": "Your visit is booked for {when} at {project} with {executive}. I'll send reminders 1 day and 2 hours before.", "hi": "आपकी विज़िट {when} को {project} में {executive} के साथ बुक हो गई है। मैं 1 दिन और 2 घंटे पहले याद दिलाऊँगा।", "gu": "તમારી વિઝિટ {when} એ {project} ખાતે {executive} સાથે બુક થઈ ગઈ છે. હું 1 દિવસ અને 2 કલાક પહેલાં યાદ અપાવીશ."},
 "taken": {"en": "Sorry, that slot was just taken. Please pick another.", "hi": "क्षमा करें, वह स्लॉट अभी भर गया। कृपया दूसरा चुनें।", "gu": "માફ કરશો, તે સ્લોટ હમણાં જ ભરાઈ ગયો. કૃપા કરી બીજો પસંદ કરો."},
 "has_visit": {"en": "You already have a visit booked. A team member can change it for you.", "hi": "आपकी एक विज़िट पहले से बुक है। हमारी टीम उसे बदल सकती है।", "gu": "તમારી એક વિઝિટ પહેલેથી બુક છે. અમારી ટીમ તેને બદલી શકે છે."},
 "fact": {"en": "From our fact sheet: {facts}", "hi": "हमारी फैक्ट शीट के अनुसार: {facts}", "gu": "અમારી ફેક્ટ શીટ મુજબ: {facts}"},
 "no_fact": {"en": "I don't have that detail, so a team member will confirm it. {exe} will reach out to you.", "hi": "मेरे पास यह जानकारी नहीं है, इसलिए हमारी टीम इसकी पुष्टि करेगी। {exe} आपसे संपर्क करेंगे।", "gu": "મારી પાસે આ માહિતી નથી, તેથી અમારી ટીમ પુષ્ટિ કરશે. {exe} તમારો સંપર્ક કરશે."},
 "price": {"en": "Final prices and offers are confirmed by our team, not by me. {exe} will reach out to you.", "hi": "अंतिम कीमत और ऑफ़र हमारी टीम बताती है, मैं नहीं। {exe} आपसे संपर्क करेंगे।", "gu": "અંતિમ ભાવ અને ઓફર અમારી ટીમ જણાવે છે, હું નહીં. {exe} તમારો સંપર્ક કરશે."},
 "person": {"en": "Of course. {exe} will contact you shortly with this chat in hand.", "hi": "ज़रूर। {exe} इस चैट के साथ जल्द आपसे संपर्क करेंगे।", "gu": "ચોક્કસ. {exe} આ ચેટ સાથે ટૂંક સમયમાં તમારો સંપર્ક કરશે."},
 "optout": {"en": "Done. We will not send you any more messages.", "hi": "ठीक है। अब आपको संदेश नहीं भेजे जाएँगे।", "gu": "થઈ ગયું. હવે તમને સંદેશા મોકલાશે નહીં."},
 "blocked": {"en": "A team member will confirm pricing and offers. {exe} will reach out to you.", "hi": "कीमत और ऑफ़र की पुष्टि हमारी टीम करेगी। {exe} आपसे संपर्क करेंगे।", "gu": "ભાવ અને ઓફરની પુષ્ટિ અમારી ટીમ કરશે. {exe} તમારો સંપર્ક કરશે."},
}


def t(key, lang, **kw):
    return T[key].get(lang, T[key]["en"]).format(**kw)


def detect_language(text, fallback):
    if re.search(r"[\u0A80-\u0AFF]", text):
        return "gu"
    if re.search(r"[\u0900-\u097F]", text):
        return "hi"
    return fallback


def _exe_name(handoff):
    return handoff.executive.get_full_name() or handoff.executive.username


def rule_agent(ctx, text):
    lead = ctx.lead
    lang = lead.language
    low = text.lower()
    previous = lead.messages.filter(role="assistant").order_by("-created_at", "-id").first()
    m = re.search(r"slot\s*#?(\d+)", low)
    if m:
        # slot ids the buyer can pick are the ones currently free for this project
        ctx.shown_slots = {s.id for s in free_slots(lead.project, limit=50)}
        res = run_tool(ctx, "book_visit", {"slot_id": int(m.group(1))})
        if res.get("ok"):
            return t("booked", lang, **{k: res[k] for k in ("when", "project", "executive")})
        return t("has_visit" if res.get("reason") == "lead_has_visit" else "taken", lang)
    affirmative = re.fullmatch(r"\s*(?:yes|yeah|yep|sure|ok|okay|please|હા|હાં|हाँ|हां)\s*[.!]*", low)
    if affirmative and previous and any(
        prompt in previous.content.lower()
        for prompt in ("would you like to see the site", "show free visit slots",
                       "क्या आप साइट देख", "શું તમે સાઇટ જોવા")
    ):
        res = run_tool(ctx, "get_free_slots", {})
        return t("slots", lang) if res["slots"] else t("no_slots", lang)
    bhk = re.search(r"\b([23])\s*-?\s*(?:bhk|बीएचके)", low)
    bhk_value = bhk.group(1) if bhk else (low.strip() if low.strip() in ("2", "3") and not lead.wants else None)
    bud = re.search(r"(?:₹\s*)?(\d+(?:\.\d+)?)\s*(lakh|lac|cr|crore|l|लाख|करोड़|લાખ|કરોડ)(?![\w])", low)
    saved = {}
    if bhk_value:
        saved["wants"] = f"{bhk_value} BHK"
    if bud:
        saved["budget"] = bud.group(0)
    if saved:
        run_tool(ctx, "save_lead_profile", saved)
    if re.search(r"\b(book|visit|site|slot|see the|schedule)\b|विज़िट|मिलना|साइट|મુલાકાત|વિઝિટ|સાઇટ", low):
        res = run_tool(ctx, "get_free_slots", {})
        return t("slots", lang) if res["slots"] else t("no_slots", lang)
    facts = search_facts(lead.project, text) if re.search(r"\?|price|cost|possession|amenit|location|parking|rera|size|area|कीमत|कहाँ|ભાવ|ક્યાં|\bwhat\b|\bwhen\b|\bwhere\b", low) else []
    if facts:
        ctx.fact_hits += facts
        return t("fact", lang, facts=" ".join(f"{f['key'].capitalize()}: {f['value'].rstrip('.')}." for f in facts[:2]))
    if "?" in text or re.search(r"\b(what|when|where|which|how)\b", low):
        run_tool(ctx, "handoff_to_human", {"reason": "missing_fact"})
        return t("no_fact", lang, exe=_exe_name(ctx.handoff))
    if not lead.wants:
        ctx.quick_replies = ["2 BHK", "3 BHK"]
        return t("ask_bhk", lang)
    if not lead.budget:
        ctx.quick_replies = ["₹80 lakh or less", "₹80 lakh–₹1 crore", "Above ₹1 crore"]
        return t("ask_budget", lang)
    ctx.quick_replies = ["Show free visit slots"]
    return t("offer_visit", lang)


# ---------- Anthropic tool-use brain ----------
def llm_agent(ctx, history):
    import anthropic
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=25)
    lead = ctx.lead
    system = SYSTEM.format(lang=lead.language, project=lead.project.name, name=lead.name)
    messages = [{"role": m.role, "content": m.content} for m in history][-16:]
    for _ in range(6):
        resp = client.messages.create(model=settings.ANTHROPIC_MODEL, max_tokens=600,
                                      system=system, tools=TOOLS, messages=messages)
        if resp.stop_reason != "tool_use":
            return "".join(b.text for b in resp.content if b.type == "text").strip()
        messages.append({"role": "assistant", "content": [b.model_dump() for b in resp.content]})
        results = []
        for b in resp.content:
            if b.type == "tool_use":
                import json
                results.append({"type": "tool_result", "tool_use_id": b.id,
                                "content": json.dumps(run_tool(ctx, b.name, b.input))})
        messages.append({"role": "user", "content": results})
    return ""


def respond(lead, text):
    """One chat turn. Returns the reply plus any UI payload (slots / booking / handoff)."""
    ChatMessage.objects.create(lead=lead, role="user", content=text)
    ctx = Ctx(lead)
    new_lang = detect_language(text, lead.language)
    if new_lang != lead.language:
        lead.language = new_lang
        lead.save(update_fields=["language"])
    lang = lead.language
    flagged, flag_reason, reply = False, "", ""

    # Server-side intents run before any model is involved.
    if guardrails.wants_opt_out(text):
        lead.opt_out = True
        lead.save(update_fields=["opt_out"])
        reply = t("optout", lang)
    elif guardrails.wants_person(text):
        run_tool(ctx, "handoff_to_human", {"reason": "buyer_requested_person"})
        reply = t("person", lang, exe=_exe_name(ctx.handoff))
    elif guardrails.asks_discount(text):
        run_tool(ctx, "handoff_to_human", {"reason": "discount_request"})
        reply, flagged, flag_reason = t("price", lang, exe=_exe_name(ctx.handoff)), True, "discount_request"
    else:
        history = list(lead.messages.all())
        if len(history) <= 1 and re.search(r"\b(hi|hello|hey)\b|नमस्ते|नमस्कार|નમસ્તે", text, re.I):
            reply = t("hello", lang, name=lead.name.split()[0], project=lead.project.name)
            ctx.quick_replies = ["2 BHK", "3 BHK"]
        elif settings.ANTHROPIC_API_KEY:
            try:
                reply = llm_agent(ctx, history)
            except Exception as exc:  # network, quota, bad output: never leave the buyer without an answer
                log.warning("LLM agent failed, using rule agent: %s", exc)
                ctx = Ctx(lead)
                reply = rule_agent(ctx, text)
        else:
            reply = rule_agent(ctx, text)

    # Output guardrail: runs on every reply, whichever brain wrote it.
    facts = list(FactSheetEntry.objects.filter(project=lead.project).values_list("value", flat=True))
    ok, why = guardrails.check_reply(reply or " ", facts)
    if not ok:
        run_tool(ctx, "handoff_to_human", {"reason": "refused_reply"})
        reply, flagged, flag_reason = t("blocked", lang, exe=_exe_name(ctx.handoff)), True, why
    if not reply:
        run_tool(ctx, "handoff_to_human", {"reason": "missing_fact"})
        reply = t("no_fact", lang, exe=_exe_name(ctx.handoff))
    repeated_question = next(
        (T[key][lang] for key in ("ask_bhk", "ask_budget", "offer_visit") if T[key][lang] in reply),
        None,
    )
    if repeated_question and lead.messages.filter(
        role="assistant", content__icontains=repeated_question
    ).count() >= 2:
        run_tool(ctx, "handoff_to_human", {"reason": "unclear_response"})
        reply = t("person", lang, exe=_exe_name(ctx.handoff))
        ctx.quick_replies = None
    if ctx.handoff and ctx.handoff.flagged:
        flagged, flag_reason = True, flag_reason or ctx.handoff.reason

    ChatMessage.objects.create(lead=lead, role="assistant", content=reply, flagged=flagged, flag_reason=flag_reason)
    if not lead.first_response_at:
        lead.first_response_at = timezone.now()
        lead.save(update_fields=["first_response_at"])
    if lead.status == "new":
        lead.status = "chatting"
        lead.save(update_fields=["status"])
    return {"reply": reply, "slots": ctx.slots_ui, "quick_replies": ctx.quick_replies,
            "booking": ctx.booking, "handoff": bool(ctx.handoff),
            "language": lead.language, "opt_out": lead.opt_out}
