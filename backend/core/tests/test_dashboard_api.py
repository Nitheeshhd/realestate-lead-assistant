from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Handoff, SourceSpend, Visit
from core.services import dashboard
from core.tests.helpers import make_lead, make_slot, make_world


class DashboardMaths(TestCase):
    """Small fixed dataset, checked by hand."""

    def setUp(self):
        self.head, self.exe, self.other, self.project = make_world()
        self.now = timezone.now()
        base = self.now - timedelta(days=5)
        # portal: 4 leads, replies after 60s, 120s, 180s, none (older than 48h => not reached)
        secs = [60, 120, 180, None]
        self.portal = []
        for i, s in enumerate(secs):
            l = make_lead(self.project, phone=f"98250100{i:02d}", created_at=base)
            if s:
                from datetime import timedelta as td
                l.first_response_at = base + td(seconds=s)
                l.save()
            self.portal.append(l)
        past = self.now - timedelta(days=2)
        from core.models import VisitSlot
        for i, st in enumerate(["visited", "visited", "no_show"]):
            slot = VisitSlot.objects.create(project=self.project, executive=self.exe, start=past + timedelta(hours=i))
            Visit.objects.create(lead=self.portal[i], slot=slot, status=st)
        # website: one lead, no visits => cost per visit must be None, not an error
        self.web = make_lead(self.project, phone="9825019999", source="website", created_at=base)
        self.web.first_response_at = base + timedelta(seconds=30)
        self.web.save()
        month = base.date().replace(day=1)
        SourceSpend.objects.create(source="portal", month=month, amount=30000)
        SourceSpend.objects.create(source="website", month=month, amount=3000)

    def build(self):
        d = timezone.localdate()
        return dashboard.build(d - timedelta(days=29), d, now=self.now)

    def row(self, data, src):
        return next(r for r in data["sources"] if r["source"] == src)

    def test_portal_numbers(self):
        r = self.row(self.build(), "portal")
        self.assertEqual(r["leads"], 4)
        self.assertEqual(r["median_response_s"], 120)           # median(60,120,180)
        self.assertEqual(r["visited"], 2)
        self.assertEqual(r["no_show"], 1)
        self.assertEqual(r["show_up_pct"], 66.7)                # 2 / (2 + 1)
        self.assertEqual(r["not_reached_48h_pct"], 25.0)        # 1 of 4 older than 48h, never answered
        self.assertEqual(r["lead_to_visit_pct"], 75.0)          # 3 of 4 have a visit

    def test_cost_per_visit_and_zero_visits(self):
        data = self.build()
        portal, web = self.row(data, "portal"), self.row(data, "website")
        self.assertGreater(portal["spend"], 0)
        self.assertAlmostEqual(portal["cost_per_visit"], portal["spend"] / 2, delta=1)  # spend is pro-rated
        self.assertIsNone(web["cost_per_visit"])                # no division by zero
        self.assertEqual(portal["flag"], "best")

    def test_duplicates_do_not_inflate_counts(self):
        make_lead(self.project, phone="9825010000", created_at=self.now - timedelta(days=4), duplicate_of=self.portal[0])
        self.assertEqual(self.row(self.build(), "portal")["leads"], 4)

    def test_project_filter_excludes_other_projects(self):
        from core.models import Project

        other_project = Project.objects.create(name="Project 2", rera_no="RERA-TEST-2")
        make_lead(other_project, phone="9825099999", source="social", created_at=self.now - timedelta(days=1))
        d = timezone.localdate()
        data = dashboard.build(d - timedelta(days=29), d, project_id=other_project.id, now=self.now)
        self.assertEqual(data["totals"]["leads"], 1)
        self.assertEqual(self.row(data, "social")["leads"], 1)
        self.assertEqual(self.row(data, "portal")["leads"], 0)


class AccessControl(TestCase):
    def setUp(self):
        self.head, self.exe, self.other, self.project = make_world()
        self.mine = make_lead(self.project, phone="9825011111", assigned_to=self.exe)
        self.theirs = make_lead(self.project, phone="9825022222", assigned_to=self.other)
        self.c = APIClient()

    def login(self, user):
        self.c.force_authenticate(user)

    def test_anonymous_cannot_read_staff_endpoints(self):
        for url in ("/api/leads", "/api/dashboard", "/api/handoffs", "/api/facts"):
            self.assertEqual(self.c.get(url).status_code, 401, url)

    def test_executive_sees_only_own_leads(self):
        self.login(self.exe)
        ids = [l["id"] for l in self.c.get("/api/leads").json()]
        self.assertEqual(ids, [self.mine.id])
        self.assertEqual(self.c.get(f"/api/leads/{self.theirs.id}").status_code, 404)

    def test_executive_cannot_open_dashboard_or_admin(self):
        self.login(self.exe)
        for url in ("/api/dashboard", "/api/facts", "/api/slots", "/api/handoffs?review=1"):
            self.assertIn(self.c.get(url).status_code, (403,), url)

    def test_sales_head_can(self):
        self.login(self.head)
        self.assertEqual(self.c.get("/api/dashboard").status_code, 200)
        self.assertEqual(len(self.c.get("/api/leads").json()), 2)

    def test_admin_fact_upsert_and_slot_update_protection(self):
        from core.services.booking import book_visit

        self.login(self.head)
        fact = {
            "project": self.project.id,
            "key": "audit_fact",
            "value": "Initial value.",
        }
        created = self.c.post("/api/facts", fact, format="json")
        self.assertEqual(created.status_code, 201)
        fact["value"] = "Updated value."
        updated = self.c.post("/api/facts", fact, format="json")
        self.assertEqual(updated.status_code, 201)
        self.assertEqual(updated.json()["id"], created.json()["id"])
        self.assertEqual(updated.json()["value"], "Updated value.")
        facts = self.c.get(f"/api/facts?project={self.project.id}").json()
        self.assertEqual(sum(item["key"] == "audit_fact" for item in facts), 1)

        slot = make_slot(self.project, self.exe)
        new_date = (timezone.localdate() + timedelta(days=4)).isoformat()
        response = self.c.patch(f"/api/slots/{slot.id}", {
            "project": self.project.id, "executive": self.other.id,
            "date": new_date, "hour": 11,
        }, format="json")
        self.assertEqual(response.status_code, 200)
        slot.refresh_from_db()
        self.assertEqual(slot.executive, self.other)
        self.assertEqual(timezone.localtime(slot.start).hour, 11)

        lead = make_lead(self.project, phone="9825033333")
        book_visit(lead.id, slot.id)
        response = self.c.patch(f"/api/slots/{slot.id}", {
            "project": self.project.id, "executive": self.exe.id,
            "date": (timezone.localdate() + timedelta(days=5)).isoformat(), "hour": 12,
        }, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.c.delete(f"/api/slots/{slot.id}").status_code, 409)

    def test_chat_needs_the_session_token(self):
        r = self.c.post(f"/api/chat/{self.mine.id}/message", {"message": "hi", "token": "wrong"}, format="json")
        self.assertEqual(r.status_code, 404)

    def test_chat_start_requires_consent_and_valid_phone(self):
        body = {"name": "A", "phone": "9825033333", "project_id": self.project.id, "language": "en", "consent": False}
        self.assertEqual(self.c.post("/api/chat/start", body, format="json").status_code, 400)
        body.update(consent=True, phone="123")
        self.assertEqual(self.c.post("/api/chat/start", body, format="json").status_code, 400)
        body.update(phone="9825033333")
        r = self.c.post("/api/chat/start", body, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["rera_no"], "RERA-TEST-1")

    def test_executive_cannot_ack_someone_elses_handoff(self):
        h = Handoff.objects.create(lead=self.theirs, executive=self.other, reason="x", summary="s")
        self.login(self.exe)
        self.assertEqual(self.c.post(f"/api/handoffs/{h.id}/ack").status_code, 404)
