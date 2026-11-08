from calendar import monthrange
from datetime import date, datetime, time, timedelta
from statistics import median

from django.utils import timezone

from core.models import Lead, SourceSpend, Visit, VisitSlot

SOURCES = [k for k, _ in Lead.SOURCES]
LABELS = dict(Lead.SOURCES)


def _prorated_spend(source, d_from, d_to):
    total = 0.0
    for s in SourceSpend.objects.filter(source=source):
        days = monthrange(s.month.year, s.month.month)[1]
        m_start, m_end = s.month, s.month + timedelta(days=days - 1)
        overlap = (min(m_end, d_to) - max(m_start, d_from)).days + 1
        if overlap > 0:
            total += float(s.amount) * overlap / days
    return total


def _fmt_seconds(sec):
    return None if sec is None else round(sec)


def build(d_from: date, d_to: date, project_id=None, now=None):
    now = now or timezone.now()
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(d_from, time.min), tz)
    end = timezone.make_aware(datetime.combine(d_to + timedelta(days=1), time.min), tz)
    leads = Lead.objects.filter(duplicate_of__isnull=True, created_at__gte=start, created_at__lt=end)
    if project_id:
        leads = leads.filter(project_id=project_id)
    leads = list(leads)
    ids = [l.id for l in leads]
    visits = {}
    for v in Visit.objects.filter(lead_id__in=ids).exclude(status="cancelled"):
        visits.setdefault(v.lead_id, []).append(v.status)

    def stats(group, spend):
        responses = [(l.first_response_at - l.created_at).total_seconds() for l in group if l.first_response_at]
        human = [(l.human_contact_at - l.created_at).total_seconds() for l in group if l.human_contact_at]
        chatted = sum(1 for l in group if l.first_response_at)
        booked = [l for l in group if visits.get(l.id)]
        visited = [l for l in group if "visited" in visits.get(l.id, [])]
        no_show = [l for l in group if "no_show" in visits.get(l.id, []) and l not in visited]
        old = [l for l in group if now - l.created_at >= timedelta(hours=48)]
        missed = [l for l in old if not l.first_response_at
                  or l.first_response_at - l.created_at > timedelta(hours=48)]
        decided = len(visited) + len(no_show)
        return {
            "leads": len(group), "chatted": chatted, "booked": len(booked), "visited": len(visited),
            "no_show": len(no_show),
            "median_response_s": _fmt_seconds(median(responses) if responses else None),
            "median_human_contact_s": _fmt_seconds(median(human) if human else None),
            "not_reached_48h_pct": round(100 * len(missed) / len(old), 1) if old else None,
            "lead_to_visit_pct": round(100 * len(booked) / len(group), 1) if group else None,
            "show_up_pct": round(100 * len(visited) / decided, 1) if decided else None,
            "spend": round(spend),
            "cost_per_lead": round(spend / len(group)) if group else None,
            "cost_per_visit": round(spend / len(visited)) if visited else None,  # None, never a divide-by-zero
        }

    rows, total_spend = [], 0.0
    for src in SOURCES:
        group = [l for l in leads if l.source == src]
        spend = _prorated_spend(src, d_from, d_to)
        total_spend += spend
        rows.append({"source": src, "label": LABELS[src], **stats(group, spend)})
    costed = [r for r in rows if r["cost_per_visit"] is not None]
    best = min(costed, key=lambda r: r["cost_per_visit"])["source"] if costed else None
    worst = max(costed, key=lambda r: r["cost_per_visit"])["source"] if len(costed) > 1 else None
    for r in rows:
        r["flag"] = "best" if r["source"] == best else "review" if r["source"] == worst else None

    daily = {}
    qs = Visit.objects.filter(slot__start__gte=start, slot__start__lt=end).exclude(status="cancelled")
    if project_id:
        qs = qs.filter(slot__project_id=project_id)
    for v in qs.select_related("slot"):
        key = timezone.localtime(v.slot.start).date().isoformat()
        daily[key] = daily.get(key, 0) + 1
    series = [{"date": (d_from + timedelta(days=i)).isoformat(),
               "visits": daily.get((d_from + timedelta(days=i)).isoformat(), 0)}
              for i in range((d_to - d_from).days + 1)]

    week = VisitSlot.objects.filter(start__gte=now, start__lt=now + timedelta(days=7))
    if project_id:
        week = week.filter(project_id=project_id)
    total_slots = week.count()
    booked_slots = Visit.objects.filter(status="booked", slot__in=week).count()

    return {
        "range": {"from": d_from.isoformat(), "to": d_to.isoformat()},
        "totals": stats(leads, total_spend),
        "sources": rows,
        "daily_visits": series,
        "slot_utilisation": {"booked": booked_slots, "total": total_slots,
                             "pct": round(100 * booked_slots / total_slots) if total_slots else None},
        "definitions": {
            "show_up": "visited / (visited + no-show); future bookings are not counted",
            "first_response": "lead created to first assistant reply",
            "not_reached_48h": "leads older than 48 h with no reply inside 48 h",
            "cost_per_visit": "pro-rated source spend / completed visits (null when there are none)",
        },
    }
