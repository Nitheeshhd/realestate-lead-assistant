from django.test import TestCase
from rest_framework.test import APIClient

from core.models import ChatMessage, FactSheetEntry, Handoff
from core.services import agent, guardrails
from core.services.booking import free_slots
from core.tests.helpers import make_lead, make_slot, make_world

FACT = "Apartments range from ₹65 lakh to ₹1.2 crore (indicative)."


class OutputFilter(TestCase):
    def test_blocks_discount_language_in_three_languages(self):
        for text in ("We can offer a discount of 5%.", "आपको छूट मिलेगी", "તમને ડિસ્કાઉન્ટ મળશે"):
            self.assertFalse(guardrails.check_reply(text, [FACT])[0], text)

    def test_blocks_invented_price(self):
        ok, why = guardrails.check_reply("The 3 BHK costs ₹85 lakh.", [FACT])
        self.assertFalse(ok)
        self.assertEqual(why, "price_not_in_fact_sheet")

    def test_allows_a_figure_that_is_verbatim_in_the_fact_sheet(self):
        self.assertTrue(guardrails.check_reply("Our range is ₹65 lakh to ₹1.2 crore.", [FACT])[0])

    def test_normal_booking_confirmation_is_not_mistaken_for_a_price(self):
        text = "Your visit is booked for Wed 04 Nov, 04:00 PM at Project 1 with Rahul Mehta. I'll send reminders 1 day and 2 hours before."
        self.assertTrue(guardrails.check_reply(text, [FACT])[0])
        self.assertFalse(guardrails.check_reply("Price is Rs 85 lakh", [FACT])[0])

    def test_intents(self):
        self.assertTrue(guardrails.wants_person("Can I talk to a person?"))
        self.assertTrue(guardrails.wants_opt_out("STOP"))
        self.assertTrue(guardrails.asks_discount("what is your best price? any discount"))
        self.assertFalse(guardrails.wants_person("What are the amenities?"))


class AgentBehaviour(TestCase):
    """Runs the offline rule agent (no API key in tests); the guardrails are shared with the LLM path."""

    def setUp(self):
        self.head, self.exe, self.other, self.project = make_world()
        FactSheetEntry.objects.create(project=self.project, key="possession", value="Possession is planned for December 2027 (sample).")
        FactSheetEntry.objects.create(project=self.project, key="price_range", value=FACT)
        self.lead = make_lead(self.project)

    def test_answers_from_fact_sheet(self):
        out = agent.respond(self.lead, "Hi")
        out = agent.respond(self.lead, "When is possession?")
        self.assertIn("December 2027", out["reply"])
        self.assertFalse(Handoff.objects.exists())

    def test_missing_fact_hands_off_instead_of_guessing(self):
        agent.respond(self.lead, "Hi")
        out = agent.respond(self.lead, "Is there a swimming pool for kids?")
        self.assertTrue(out["handoff"])
        h = Handoff.objects.get()
        self.assertTrue(h.flagged)
        self.assertEqual(h.reason, "missing_fact")

    def test_discount_request_never_quotes_and_is_flagged_for_review(self):
        agent.respond(self.lead, "Hi")
        out = agent.respond(self.lead, "Can you give me a discount on the 3 BHK?")
        self.assertNotRegex(out["reply"], r"₹|\d+\s*%")
        self.assertTrue(ChatMessage.objects.filter(lead=self.lead, flagged=True).exists())
        self.assertEqual(Handoff.objects.get().reason, "discount_request")

    def test_best_and_final_price_requests_are_handed_off(self):
        for i, question in enumerate(("what is your best price?", "final price for 3 BHK?")):
            lead = make_lead(self.project, phone=f"982501118{i}")
            out = agent.respond(lead, question)
            self.assertTrue(out["handoff"], question)
            self.assertNotRegex(out["reply"], r"₹|\d+\s*%")
            self.assertEqual(lead.handoffs.first().reason, "discount_request")

    def test_person_request_hands_off_immediately(self):
        out = agent.respond(self.lead, "I want to talk to a real person")
        self.assertTrue(out["handoff"])
        self.lead.refresh_from_db()
        self.assertIsNotNone(self.lead.assigned_to)

    def test_opt_out_is_honoured(self):
        agent.respond(self.lead, "stop")
        self.lead.refresh_from_db()
        self.assertTrue(self.lead.opt_out)

    def test_booking_only_real_free_slots(self):
        slot = make_slot(self.project, self.exe)
        agent.respond(self.lead, "Hi")
        shown = agent.respond(self.lead, "I want to book a site visit")
        self.assertEqual([s["slot_id"] for s in shown["slots"]], [slot.id])
        out = agent.respond(self.lead, f"Please book slot #{slot.id}")
        self.assertIsNotNone(out["booking"])
        self.assertIn("booked", out["reply"])  # confirmation must survive the output filter
        again = agent.respond(self.lead, "book slot #999999")
        self.assertIsNone(again["booking"])  # hallucinated or unknown id fails safely

    def test_llm_tool_cannot_book_a_slot_it_was_not_shown(self):
        slot = make_slot(self.project, self.exe)
        ctx = agent.Ctx(self.lead)
        res = agent.run_tool(ctx, "book_visit", {"slot_id": slot.id})
        self.assertFalse(res["ok"])
        agent.run_tool(ctx, "get_free_slots", {})
        self.assertTrue(agent.run_tool(ctx, "book_visit", {"slot_id": slot.id})["ok"])

    def test_language_follows_the_buyer_script(self):
        agent.respond(self.lead, "નમસ્તે")
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.language, "gu")

    def test_short_bhk_reply_budget_choices_and_yes_show_slots(self):
        slot = make_slot(self.project, self.exe)
        hello = agent.respond(self.lead, "Hi")
        self.assertEqual(hello["quick_replies"], ["2 BHK", "3 BHK"])

        budget = agent.respond(self.lead, "2")
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.wants, "2 BHK")
        self.assertEqual(budget["quick_replies"], ["₹80 lakh or less", "₹80 lakh–₹1 crore", "Above ₹1 crore"])

        offer = agent.respond(self.lead, "80 lakh")
        self.assertEqual(offer["quick_replies"], ["Show free visit slots"])
        slots = agent.respond(self.lead, "yes")
        self.assertEqual([item["slot_id"] for item in slots["slots"]], [slot.id])

    def test_native_script_quick_replies_save_bhk_and_budget(self):
        agent.respond(self.lead, "Hi")
        agent.respond(self.lead, "3 बीएचके")
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.wants, "3 BHK")
        agent.respond(self.lead, "₹80 लाख या कम")
        self.lead.refresh_from_db()
        self.assertIn("80", self.lead.budget)
        self.assertEqual(self.lead.language, "hi")

    def test_repeated_question_hands_off_instead_of_looping(self):
        agent.respond(self.lead, "Hi")
        agent.respond(self.lead, "I am not sure")
        agent.respond(self.lead, "Still not sure")
        out = agent.respond(self.lead, "Maybe later")
        self.assertTrue(out["handoff"])
        messages = ChatMessage.objects.filter(lead=self.lead, role="assistant")
        repeated = sum(message.content.count(agent.t("ask_bhk", "en")) for message in messages)
        self.assertEqual(repeated, 2)

    def test_opted_out_chat_cannot_receive_another_assistant_reply(self):
        client = APIClient()
        client.post(f"/api/chat/{self.lead.id}/message",
                    {"token": self.lead.chat_token, "message": "stop"}, format="json")
        response = client.post(f"/api/chat/{self.lead.id}/message",
                               {"token": self.lead.chat_token, "message": "Hi"}, format="json")
        self.assertEqual(response.status_code, 403)
