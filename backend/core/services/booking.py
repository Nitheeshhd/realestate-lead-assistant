import time

from django.db import IntegrityError, OperationalError, transaction
from django.utils import timezone

from core.models import Reminder, Visit, VisitSlot
from datetime import timedelta

MIN_LEAD_TIME = timedelta(hours=1)


class SlotUnavailable(Exception):
    """reason: past | taken | lead_has_visit | wrong_project | not_found | busy"""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def free_slots(project, now=None, limit=12, days=7):
    now = now or timezone.now()
    booked = Visit.objects.filter(status="booked").values("slot_id")
    return (VisitSlot.objects.filter(project=project, start__gte=now + MIN_LEAD_TIME,
                                     start__lte=now + timedelta(days=days))
            .exclude(id__in=booked).select_related("executive")[:limit])


def _schedule_reminders(visit, now):
    start = visit.slot.start
    for kind, delta in (("t_minus_1d", timedelta(days=1)), ("t_minus_2h", timedelta(hours=2))):
        when = start - delta
        if when > now:
            Reminder.objects.create(visit=visit, kind=kind, send_at=when)


def book_visit(lead_id, slot_id, now=None):
    """Book one slot for one lead. Safe under concurrency: the unique constraints on
    Visit are the final authority, the checks below only give friendlier reasons."""
    from core.models import Lead
    now = now or timezone.now()
    for attempt in range(4):
        try:
            with transaction.atomic():
                lead = Lead.objects.get(pk=lead_id)
                slot = VisitSlot.objects.select_related("executive").filter(pk=slot_id).first()
                if slot is None:
                    raise SlotUnavailable("not_found")
                if slot.project_id != lead.project_id:
                    raise SlotUnavailable("wrong_project")
                if slot.start < now + MIN_LEAD_TIME:
                    raise SlotUnavailable("past")
                if Visit.objects.filter(slot=slot, status="booked").exists():
                    raise SlotUnavailable("taken")
                if Visit.objects.filter(lead=lead, status="booked").exists():
                    raise SlotUnavailable("lead_has_visit")
                visit = Visit.objects.create(lead=lead, slot=slot, status="booked")
                lead.status = "booked"
                lead.assigned_to = slot.executive
                lead.save(update_fields=["status", "assigned_to"])
                _schedule_reminders(visit, now)
                return visit
        except IntegrityError:
            if Visit.objects.filter(slot_id=slot_id, status="booked").exists():
                raise SlotUnavailable("taken")
            raise SlotUnavailable("lead_has_visit")
        except OperationalError:  # SQLite "database is locked" under heavy contention
            time.sleep(0.05 * (attempt + 1))
    raise SlotUnavailable("busy")


def cancel_visit(visit):
    visit.status = "cancelled"
    visit.save(update_fields=["status"])
    visit.reminders.filter(status="pending").update(status="skipped")
    lead = visit.lead
    if not lead.visits.filter(status="booked").exists():
        lead.status = "chatting"
        lead.save(update_fields=["status"])
