from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils import timezone

from core.models import Handoff


def pick_executive(lead):
    if lead.assigned_to_id:
        return lead.assigned_to
    User = get_user_model()
    execs = User.objects.filter(profile__role="executive").annotate(
        load=Count("handoff", filter=Q(handoff__acknowledged_at__isnull=True))).order_by("load", "id")
    return execs.first()


def build_summary(lead):
    msgs = list(lead.messages.filter(role="user").values_list("content", flat=True))[-3:]
    visit = lead.visits.filter(status="booked").select_related("slot").first()
    parts = [f"{lead.name} ({lead.get_source_display()}) is looking at {lead.project.name}"]
    parts.append(f"wants {lead.wants}" if lead.wants else "BHK not shared yet")
    parts.append(f"budget {lead.budget}" if lead.budget else "budget not shared yet")
    if visit:
        parts.append("visit booked " + timezone.localtime(visit.slot.start).strftime("%a %d %b %I:%M %p"))
    summary = "; ".join(parts) + "."
    if msgs:
        summary += " Latest messages: " + " | ".join(m[:120] for m in msgs)
    return summary


def create_handoff(lead, reason, flagged=False):
    """One open handoff per lead: repeated triggers update it instead of piling up."""
    open_h = lead.handoffs.filter(acknowledged_at__isnull=True).first()
    exe = pick_executive(lead)
    summary = build_summary(lead)
    if open_h:
        open_h.summary = summary
        open_h.flagged = open_h.flagged or flagged
        open_h.save(update_fields=["summary", "flagged"])
        return open_h
    lead.assigned_to = exe
    lead.status = "handed_off"
    lead.save(update_fields=["assigned_to", "status"])
    return Handoff.objects.create(lead=lead, executive=exe, reason=reason, summary=summary, flagged=flagged)
