"""Seed realistic sample data. Everything here is invented for the demo (see TDD assumptions)."""
import random
from datetime import datetime, time, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.models import (ChatMessage, FactSheetEntry, Handoff, Lead, Profile, Project, SourceSpend,
                         Visit, VisitSlot)
from core.services import booking
from core.services.handoff import build_summary

NAMES = ["Hardik Patel", "Nidhi Shah", "Kavita Joshi", "Jignesh Desai", "Pooja Mehta", "Rakesh Parmar",
         "Hetal Trivedi", "Chirag Amin", "Bhavna Solanki", "Dipen Vyas", "Mansi Thakkar", "Yash Gandhi",
         "Krunal Rana", "Sapna Bhatt", "Nilesh Chauhan", "Riddhi Pandya", "Ketan Modi", "Anjali Dave",
         "Harsh Raval", "Minal Suthar", "Parth Kapadia", "Foram Joshi", "Tejas Brahmbhatt", "Rina Zaveri",
         "Vivek Dalal", "Komal Barot", "Sagar Prajapati", "Urvi Nayak", "Mehul Shukla", "Disha Oza"]
SOURCE_WEIGHTS = [("portal", 37), ("social", 41), ("website", 13), ("hoarding", 9)]
BOOK_P = {"portal": .22, "social": .12, "website": .35, "hoarding": .30}
SHOW_P = {"portal": .82, "social": .66, "website": .87, "hoarding": .85}
HOURS = [10, 11, 12, 15, 16, 17]

FACTS = {
    "Project 1": {
        "configuration": "Sample configurations: 2 BHK and 3 BHK apartments.",
        "price_range": "Sample indicative price range across the demo projects: ₹65 lakh to ₹1.2 crore. Not a final quote.",
        "possession": "Possession is planned for December 2027 (sample date).",
        "amenities": "Clubhouse, gym, children's play area and landscaped garden (sample).",
        "location": "Sample address, Ahmedabad. Our executive shares the exact location pin on booking.",
        "parking": "One covered car parking space per apartment (sample).",
    },
    "Project 2": {
        "configuration": "Sample configurations: 2 BHK and 3 BHK apartments.",
        "price_range": "Sample indicative price range across the demo projects: ₹65 lakh to ₹1.2 crore. Not a final quote.",
        "possession": "Possession is planned for June 2028 (sample date).",
        "amenities": "Swimming pool, yoga deck, indoor games room and 24x7 security (sample).",
        "location": "Sample address, Ahmedabad. Our executive shares the exact location pin on booking.",
        "parking": "One covered and one open parking space per 3 BHK (sample).",
    },
}


class Command(BaseCommand):
    help = "Create demo staff, projects, fact sheet, slots, leads, visits and spend."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing demo data first")

    def handle(self, *args, **opts):
        if Project.objects.exists() and not opts["reset"]:
            self.stdout.write("Already seeded. Use --reset to rebuild.")
            return
        password = settings.SEED_PASSWORD or ("demo-pass-123" if settings.DEBUG else "")
        if not password:
            raise CommandError("Set SEED_PASSWORD before seeding a non-debug environment.")
        rnd = random.Random(42)
        now = timezone.now()
        tz = timezone.get_current_timezone()
        User = get_user_model()

        if opts["reset"]:
            for m in (Handoff, ChatMessage, Visit, VisitSlot, Lead, FactSheetEntry, Project, SourceSpend):
                m.objects.all().delete()
            User.objects.filter(profile__isnull=False).delete()

        def mk_user(username, first, last, role):
            u = User.objects.create_user(username, password=password, first_name=first, last_name=last)
            Profile.objects.create(user=u, role=role)
            return u

        head = mk_user("saleshead", "Meera", "Desai", "sales_head")
        rahul = mk_user("rahul", "Rahul", "Mehta", "executive")
        pooja = mk_user("pooja", "Pooja", "Trivedi", "executive")
        karan = mk_user("karan", "Karan", "Shah", "executive")
        anita = mk_user("anita", "Anita", "Pandya", "executive")

        p1 = Project.objects.create(name="Project 1", rera_no="PRGJ/SAMPLE/0001", address="Sample address, Ahmedabad",
                                    lat="23.030000", lng="72.560000")
        p2 = Project.objects.create(name="Project 2", rera_no="PRGJ/SAMPLE/0002", address="Sample address, Ahmedabad",
                                    lat="23.050000", lng="72.510000")
        execs = {p1: [rahul, pooja], p2: [karan, anita]}  # one executive works one project (assumption)
        for p in (p1, p2):
            for k, v in FACTS[p.name].items():
                FactSheetEntry.objects.create(project=p, key=k, value=v)

        def slot_at(project, day, hour):
            for e in rnd.sample(execs[project], len(execs[project])):
                start = timezone.make_aware(datetime.combine(day, time(hour)), tz)
                s, _ = VisitSlot.objects.get_or_create(project=project, executive=e, start=start)
                if not Visit.objects.filter(slot=s, status="booked").exists() and \
                        not Visit.objects.filter(slot=s).exclude(status="cancelled").exists():
                    return s
            return None

        # future slots: next 7 days
        today = timezone.localdate()
        for d in range(0, 8):
            for p in (p1, p2):
                for e in execs[p]:
                    for h in HOURS:
                        start = timezone.make_aware(datetime.combine(today + timedelta(days=d), time(h)), tz)
                        if start > now + timedelta(hours=1):
                            VisitSlot.objects.get_or_create(project=p, executive=e, start=start)

        # the three leads from the brief
        def mk(code, name, phone, source, project, wants, created):
            l = Lead.objects.create(code=code, name=name, phone=phone, phone_norm=phone[-10:], source=source,
                                    project=project, wants=wants, consent=True, language="en",
                                    chat_token=f"seed-{code}", created_at=created)
            return l
        hardik = mk("LD-58210", "Hardik Patel", "+91 98250 11210", "portal", p1, "3 BHK", now - timedelta(days=4, hours=3))
        nidhi = mk("LD-58211", "Nidhi Shah", "+91 98250 11211", "social", p2, "2 BHK", now - timedelta(days=2, hours=5))
        kavita = mk("LD-58224", "Kavita Joshi", "+91 98250 11224", "hoarding", p2, "2 BHK", now - timedelta(days=9))
        for l, mins in ((hardik, 3), (nidhi, 5), (kavita, 6)):
            l.first_response_at = l.created_at + timedelta(minutes=mins)
            l.status = "chatting"
            l.save()
        # Hardik: booked 2026-11-01 11:00 (as in the brief)
        s = VisitSlot.objects.create(project=p1, executive=rahul, start=timezone.make_aware(datetime(2026, 11, 1, 11), tz))
        Visit.objects.create(lead=hardik, slot=s, status="booked")
        hardik.status, hardik.assigned_to = "booked", rahul
        hardik.save()
        s = VisitSlot.objects.create(project=p2, executive=karan, start=timezone.make_aware(datetime(2026, 10, 26, 15), tz))
        Visit.objects.create(lead=kavita, slot=s, status="visited")
        kavita.status, kavita.assigned_to = "visited", karan
        kavita.save()

        # synthetic history: 60 leads over the last 40 days
        sources = [s for s, w in SOURCE_WEIGHTS for _ in range(w)]
        made = []
        for i in range(60):
            src = rnd.choice(sources)
            proj = rnd.choice([p1, p2])
            created = now - timedelta(days=rnd.uniform(0.2, 40))
            phone = f"+91 9{rnd.randint(100000000, 999999999)}"
            if i in (10, 11) and made:  # two repeat enquiries to show the duplicate badge
                phone = made[i - 9].phone
            primary = Lead.objects.filter(phone_norm=phone[-10:], duplicate_of__isnull=True).first()
            lead = Lead.objects.create(
                name=rnd.choice(NAMES), phone=phone, phone_norm=phone[-10:], source=src, project=proj,
                wants=rnd.choice(["2 BHK", "3 BHK", ""]), budget=rnd.choice(["", "80 lakh", "1 crore", "1.1 crore"]),
                language=rnd.choice(["en", "en", "hi", "gu"]), consent=True, duplicate_of=primary,
                chat_token=f"seed-{i}", created_at=created)
            made.append(lead)
            if primary:
                continue
            unreached = (now - created) > timedelta(hours=48) and rnd.random() < .04
            if not unreached:
                lead.first_response_at = created + timedelta(seconds=rnd.choice([40, 75, 110, 150, 200, 260, 300, 420]))
                lead.status = "chatting"
                ChatMessage.objects.create(lead=lead, role="user", content=f"Hi, I want to know about {lead.wants or 'your apartments'}.")
                ChatMessage.objects.create(lead=lead, role="assistant",
                                           content=f"Hello {lead.name.split()[0]}, I'm Aangan. I can answer questions about {proj.name} and book a site visit.")
            lead.save()
            if lead.first_response_at and rnd.random() < BOOK_P[lead.source]:
                day = timezone.localdate(created) + timedelta(days=rnd.randint(1, 4))
                if day < today:  # past visit
                    sl = slot_at(proj, day, rnd.choice(HOURS))
                    if sl:
                        st = "visited" if rnd.random() < SHOW_P[lead.source] else "no_show"
                        Visit.objects.create(lead=lead, slot=sl, status=st)
                        lead.status = "visited" if st == "visited" else "chatting"
                        lead.assigned_to = sl.executive
                        lead.save()
            if lead.status == "chatting" and rnd.random() < .12:
                h = Handoff.objects.create(lead=lead, executive=rnd.choice(execs[proj]), reason="missing_fact",
                                           summary=build_summary(lead), flagged=rnd.random() < .6)
                lead.status, lead.assigned_to = "handed_off", h.executive
                if rnd.random() < .5:
                    h.acknowledged_at = lead.created_at + timedelta(minutes=rnd.randint(8, 90))
                    h.save()
                    lead.human_contact_at = h.acknowledged_at
                lead.save()

        # a few real future bookings through the real booking service (also creates reminders)
        future = [l for l in Lead.objects.filter(first_response_at__isnull=False, duplicate_of__isnull=True,
                                                 status="chatting") if not l.visits.exists()][:5]
        for l in future:
            sl = booking.free_slots(l.project, limit=40)
            sl = list(sl)
            if sl:
                booking.book_visit(l.id, rnd.choice(sl).id)
        # Nidhi: has not booked yet (as in the brief)

        # spend: assumption of Rs 1,000 per lead, per source per month, scaled to the seeded volume
        months = {}
        for l in Lead.objects.filter(duplicate_of__isnull=True):
            key = (l.source, timezone.localdate(l.created_at).replace(day=1))
            months[key] = months.get(key, 0) + 1
        for (src, month), n in months.items():
            SourceSpend.objects.create(source=src, month=month, amount=n * 1000)

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {Lead.objects.count()} leads, {Visit.objects.count()} visits, {VisitSlot.objects.count()} slots. "
            f"Staff logins: saleshead, rahul, pooja, karan, anita (password from SEED_PASSWORD)."))
