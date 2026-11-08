import logging

from django.utils import timezone

from core.models import Reminder

log = logging.getLogger("aangan.reminders")

TEXT = {
    "en": "Reminder: your site visit at {project} is on {when}. Location: {map}. RERA: {rera}. Reply STOP to opt out.",
    "hi": "याद दिलाना: {project} में आपकी साइट विज़िट {when} को है। लोकेशन: {map}। RERA: {rera}। बंद करने के लिए STOP लिखें।",
    "gu": "યાદ અપાવવા: {project} ખાતે તમારી સાઇટ વિઝિટ {when} એ છે. લોકેશન: {map}. RERA: {rera}. બંધ કરવા STOP લખો.",
}


def render(reminder):
    visit = reminder.visit
    project = visit.slot.project
    local = timezone.localtime(visit.slot.start)
    tpl = TEXT.get(visit.lead.language, TEXT["en"])
    return tpl.format(project=project.name, when=local.strftime("%a %d %b, %I:%M %p"),
                      map=project.map_url or project.address or "shared by your executive",
                      rera=project.rera_no)


def dispatch_due(now=None):
    """Mock sender: logs and stores the message. Honours consent, opt-out and cancellations."""
    now = now or timezone.now()
    sent = skipped = 0
    due = Reminder.objects.filter(status="pending", send_at__lte=now).select_related(
        "visit__lead", "visit__slot__project")
    for r in due:
        lead = r.visit.lead
        if r.visit.status != "booked" or lead.opt_out or not lead.consent:
            r.status = "skipped"
            skipped += 1
        else:
            r.body = render(r)
            r.status = "sent"
            r.sent_at = now
            sent += 1
            log.info("MOCK SEND to %s: %s", lead.phone_norm, r.body)
        r.save()
    return {"sent": sent, "skipped": skipped}
