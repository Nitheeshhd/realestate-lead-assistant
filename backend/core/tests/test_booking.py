import threading

from django.db import connection
from django.test import TestCase, TransactionTestCase

from core.models import Reminder, Visit
from core.services.booking import SlotUnavailable, book_visit, free_slots
from core.tests.helpers import make_lead, make_slot, make_world


class BookingRules(TestCase):
    def setUp(self):
        self.head, self.exe, self.other, self.project = make_world()
        self.slot = make_slot(self.project, self.exe)
        self.lead = make_lead(self.project)

    def test_books_and_schedules_both_reminders(self):
        v = book_visit(self.lead.id, self.slot.id)
        self.assertEqual(v.status, "booked")
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.assigned_to, self.exe)  # named executive
        self.assertEqual(set(Reminder.objects.values_list("kind", flat=True)), {"t_minus_1d", "t_minus_2h"})

    def test_booked_slot_leaves_the_free_list(self):
        book_visit(self.lead.id, self.slot.id)
        self.assertNotIn(self.slot.id, [s.id for s in free_slots(self.project)])

    def test_second_buyer_cannot_take_a_booked_slot(self):
        book_visit(self.lead.id, self.slot.id)
        other = make_lead(self.project, phone="9825022222")
        with self.assertRaises(SlotUnavailable) as cm:
            book_visit(other.id, self.slot.id)
        self.assertEqual(cm.exception.reason, "taken")

    def test_one_open_visit_per_lead(self):
        book_visit(self.lead.id, self.slot.id)
        second = make_slot(self.project, self.other, hours_ahead=31)
        with self.assertRaises(SlotUnavailable) as cm:
            book_visit(self.lead.id, second.id)
        self.assertEqual(cm.exception.reason, "lead_has_visit")

    def test_past_and_unknown_slots_fail_safely(self):
        past = make_slot(self.project, self.exe, hours_ahead=-5)
        for sid, reason in ((past.id, "past"), (999999, "not_found")):
            with self.assertRaises(SlotUnavailable) as cm:
                book_visit(self.lead.id, sid)
            self.assertEqual(cm.exception.reason, reason)

    def test_short_notice_booking_skips_the_reminder_already_in_the_past(self):
        soon = make_slot(self.project, self.other, hours_ahead=5)
        book_visit(self.lead.id, soon.id)
        self.assertEqual(list(Reminder.objects.values_list("kind", flat=True)), ["t_minus_2h"])


class BookingConcurrency(TransactionTestCase):
    """20 buyers hit the same slot at once. Exactly one may win."""

    def test_twenty_threads_one_winner(self):
        head, exe, other, project = make_world()
        slot = make_slot(project, exe)
        leads = [make_lead(project, phone=f"98250{i:05d}") for i in range(20)]
        results, barrier = [], threading.Barrier(20)

        def worker(lead_id):
            try:
                barrier.wait()
                book_visit(lead_id, slot.id)
                results.append("ok")
            except SlotUnavailable as e:
                results.append(e.reason)
            finally:
                connection.close()

        threads = [threading.Thread(target=worker, args=(l.id,)) for l in leads]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(results.count("ok"), 1, results)
        self.assertEqual(Visit.objects.filter(slot=slot, status="booked").count(), 1)
        self.assertEqual(len(results), 20)
