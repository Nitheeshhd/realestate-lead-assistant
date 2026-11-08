from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from core.models import Reminder
from core.services import leads, reminders
from core.services.booking import book_visit, cancel_visit
from core.tests.helpers import make_lead, make_slot, make_world


class Dedupe(TestCase):
    def setUp(self):
        *_, self.project = make_world()

    def test_phone_is_normalised(self):
        for raw in ("+91 98250 11111", "098250 11111", "9825011111", "91-9825011111"):
            self.assertEqual(leads.normalize_phone(raw), "9825011111")

    def test_bad_numbers_rejected(self):
        for raw in ("12345", "5825011111", "", "abcdefghij"):
            with self.assertRaises(ValueError):
                leads.normalize_phone(raw)

    def test_same_number_from_other_source_is_flagged_not_dropped(self):
        first, p1 = leads.create_lead(name="A", phone="+91 98250 11111", source="portal", project=self.project)
        second, p2 = leads.create_lead(name="A", phone="9825011111", source="social", project=self.project)
        self.assertIsNone(p1)
        self.assertEqual(p2, first)
        self.assertTrue(second.is_duplicate)
        self.assertEqual(second.source, "social")  # attribution kept


class Reminders(TestCase):
    def setUp(self):
        self.head, self.exe, self.other, self.project = make_world()
        self.slot = make_slot(self.project, self.exe, hours_ahead=60)
        self.lead = make_lead(self.project)
        self.visit = book_visit(self.lead.id, self.slot.id)
        self.late = self.slot.start

    def test_sends_with_rera_number_and_map(self):
        out = reminders.dispatch_due(now=self.late)
        self.assertEqual(out["sent"], 2)
        body = Reminder.objects.filter(status="sent").first().body
        self.assertIn("RERA-TEST-1", body)
        self.assertIn("maps?q=", body)

    def test_opted_out_buyer_gets_nothing(self):
        self.lead.opt_out = True
        self.lead.save()
        out = reminders.dispatch_due(now=self.late)
        self.assertEqual(out, {"sent": 0, "skipped": 2})

    def test_cancelled_visit_reminders_are_skipped(self):
        cancel_visit(self.visit)
        out = reminders.dispatch_due(now=self.late)
        self.assertEqual(out, {"sent": 0, "skipped": 0})
        self.assertEqual(set(Reminder.objects.values_list("status", flat=True)), {"skipped"})

    def test_nothing_is_sent_before_it_is_due(self):
        self.assertEqual(reminders.dispatch_due(now=timezone.now())["sent"], 0)
