import concurrent.futures
import tempfile
import unittest
from pathlib import Path

from travel.agent import Agent, AgentError
from travel.simulator import RuleError, Store


class StoreTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "test.sqlite3"
        self.store = Store(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def quote(self, scenario="normal", patch=None):
        trip = self.store.create(scenario)
        if patch:
            self.store.update(trip["id"], patch)
        trip = self.store.search(trip["id"])
        return trip, trip["options"][0] if trip["options"] else None

    def book(self, trip, option):
        return self.store.book(trip["id"], option["id"], option["total_cents"])


class SimulatorTests(StoreTestCase):
    def test_valid_options_respect_constraints_and_totals(self):
        trip, _ = self.quote(patch={"travelers": 3})
        for option in trip["options"]:
            self.assertLessEqual(option["total_cents"], trip["profile"]["budget_cents"])
            self.assertEqual(option["flight"]["stops"], 0)
            self.assertTrue(option["hotel"]["downtown"])
            self.assertEqual(option["total_cents"], sum(option[k] for k in ("flight_cents", "hotel_cents", "tax_cents")))
            self.assertEqual(option["flight_cents"], option["flight"]["fare_cents"] * 3)

    def test_infeasible_budget_returns_no_options_without_relaxing(self):
        trip, _ = self.quote(patch={"budget_cents": 10000})
        self.assertEqual(trip["options"], [])
        self.assertTrue(trip["profile"]["nonstop"])
        self.assertTrue(trip["profile"]["downtown"])

    def test_invalid_update_rolls_back(self):
        trip, _ = self.quote()
        with self.assertRaises(RuleError):
            self.store.update(trip["id"], {"destination": "SFO", "budget_cents": 123456})
        self.assertEqual(self.store.get(trip["id"]), trip)

    def test_profile_changes_invalidate_old_quotes(self):
        trip, option = self.quote()
        self.store.update(trip["id"], {"destination": "SEA"})
        with self.assertRaisesRegex(RuleError, "stale"):
            self.book(trip, option)
        self.assertEqual(self.store.get(trip["id"])["reservations"], [])

    def test_wrong_price_never_books(self):
        trip, option = self.quote()
        with self.assertRaises(RuleError):
            self.store.book(trip["id"], option["id"], option["total_cents"] - 1)
        self.assertEqual(self.store.get(trip["id"])["reservations"], [])

    def test_booking_survives_store_restart_and_retries(self):
        trip, option = self.quote()
        booked = self.book(trip, option)
        self.assertEqual(booked["status"], "booked")
        self.assertEqual(len(booked["reservations"]), 2)
        self.assertEqual(sum(r["amount_cents"] for r in booked["reservations"]), option["total_cents"])
        self.assertEqual(Store(self.path).get(trip["id"]), booked)
        self.assertEqual(self.book(trip, option)["reservations"], booked["reservations"])

    def test_concurrent_duplicate_approvals_are_idempotent(self):
        trip, option = self.quote()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.book(trip, option), range(8)))
        self.assertTrue(all(len(r["reservations"]) == 2 for r in results))
        self.assertEqual(len(self.store.get(trip["id"])["reservations"]), 2)

    def test_price_change_requires_new_approval(self):
        trip, option = self.quote("price_change")
        changed = self.book(trip, option)
        self.assertEqual(changed["status"], "needs_approval")
        self.assertEqual(changed["reservations"], [])
        self.assertIsNone(changed["approved"])
        with self.assertRaises(RuleError):
            self.book(trip, option)
        updated = changed["options"][0]
        self.assertGreater(updated["total_cents"], option["total_cents"])
        self.assertEqual(self.book(changed, updated)["status"], "booked")

    def test_price_change_crossing_budget_cannot_be_approved(self):
        trip, option = self.quote("price_change")
        self.store.update(trip["id"], {"budget_cents": option["total_cents"]})
        trip = self.store.search(trip["id"])
        changed = self.book(trip, trip["options"][0])
        self.assertEqual(changed["options"][0]["status"], "over_budget")
        with self.assertRaises(RuleError):
            self.book(changed, changed["options"][0])
        self.assertFalse(self.store.get(trip["id"])["reservations"])

    def test_sold_out_flight_stays_excluded_on_search(self):
        trip, option = self.quote("sold_out")
        sold = self.book(trip, option)
        self.assertEqual(sold["reservations"], [])
        with self.assertRaises(RuleError):
            self.book(trip, option)
        fresh = self.store.search(trip["id"])
        self.assertTrue(fresh["options"])
        self.assertTrue(all(o["flight"]["id"] != option["flight"]["id"] for o in fresh["options"]))

    def test_partial_failure_retry_retains_flight(self):
        trip, option = self.quote("hotel_failure")
        partial = self.book(trip, option)
        self.assertEqual(partial["status"], "partial")
        self.assertEqual(len(partial["reservations"]), 1)
        flight = partial["reservations"][0]
        with self.assertRaises(RuleError):
            self.store.search(trip["id"])
        recovered = self.book(trip, option)
        self.assertEqual(recovered["status"], "booked")
        self.assertEqual(len(recovered["reservations"]), 2)
        self.assertEqual(recovered["reservations"][0], flight)

    def test_timeout_reconciles_committed_booking(self):
        trip, option = self.quote("timeout")
        booked = self.book(trip, option)
        self.assertEqual(len(booked["reservations"]), 2)
        self.assertTrue(any(e["result"] == "reconciled" for e in booked["events"]))
        self.assertEqual(len(self.book(trip, option)["reservations"]), 2)

    def test_cancellation_invalidates_retry_and_preserves_other_reservation(self):
        trip, option = self.quote()
        booked = self.book(trip, option)
        reservation = booked["reservations"][0]
        cancelled = self.store.cancel(trip["id"], reservation["id"])
        self.assertEqual(cancelled["status"], "partial")
        self.assertEqual(sum(r["status"] == "confirmed" for r in cancelled["reservations"]), 1)
        with self.assertRaises(RuleError):
            self.book(trip, option)
        self.assertEqual(self.store.cancel(trip["id"], reservation["id"]), cancelled)
        cancelled = self.store.cancel(trip["id"], booked["reservations"][1]["id"])
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertTrue(self.store.search(trip["id"])["options"])

    def test_cannot_switch_options_with_active_reservations(self):
        trip, option = self.quote()
        self.book(trip, option)
        with self.assertRaises(RuleError):
            self.book(trip, trip["options"][1])
        with self.assertRaises(RuleError):
            self.store.update(trip["id"], {"destination": "SEA"})

    def test_invalid_dates_travelers_and_money(self):
        trip = self.store.create()
        for patch in ({"return_date": trip["profile"]["departure"]}, {"departure": "nonsense"},
                      {"travelers": True}, {"travelers": 5}, {"budget_cents": 10000.5},
                      {"nonstop": "false"}, {"destination": "CDG"}):
            with self.subTest(patch=patch), self.assertRaises(RuleError):
                self.store.update(trip["id"], patch)


class AgentTests(StoreTestCase):
    def test_tool_loop_updates_searches_and_returns_grounded_result(self):
        trip = self.store.create()
        payloads = []
        replies = [
            {"output": [{"type": "function_call", "name": "update_trip", "arguments": '{"destination":"SEA"}', "call_id": "call1"}]},
            {"output": [{"type": "function_call", "name": "search_options", "arguments": "{}", "call_id": "call2"}]},
            {"output": [{"type": "message", "content": [{"type": "output_text", "text": "Seattle options are ready to review."}]}]},
        ]
        def fake(payload, timeout):
            payloads.append(payload)
            return replies.pop(0)
        result = Agent(self.store, request=fake).respond(trip["id"], "Take me to Seattle", "ai")
        self.assertEqual(result["profile"]["destination"], "SEA")
        self.assertTrue(result["options"])
        self.assertEqual(result["reservations"], [])
        outputs = [i for i in payloads[-1]["input"] if i.get("type") == "function_call_output"]
        self.assertEqual(len(outputs), 2)
        self.assertEqual(json_load(outputs[-1]["output"])["profile"]["destination"], "SEA")
        self.assertFalse(payloads[-1]["store"])

    def test_model_cannot_book_or_cancel_via_tools(self):
        trip, option = self.quote()
        agent = Agent(self.store)
        for name in ("book_flight", "book_itinerary", "cancel_reservation"):
            with self.assertRaises(RuleError):
                agent.execute(trip["id"], name, {"option_id": option["id"], "approved": True})
        self.assertEqual(self.store.get(trip["id"])["reservations"], [])

    def test_infinite_tool_loop_is_bounded(self):
        trip = self.store.create()
        calls = []
        def fake(payload, timeout):
            calls.append(1)
            return {"output": [{"type": "function_call", "name": "get_trip", "arguments": "{}", "call_id": str(len(calls))}]}
        with self.assertRaises(AgentError):
            Agent(self.store, request=fake).respond(trip["id"], "Keep going forever", "ai")
        self.assertEqual(len(calls), 12)
        self.assertEqual(self.store.get(trip["id"])["reservations"], [])

    def test_invalid_tool_arguments_are_returned_to_model(self):
        trip = self.store.create()
        count = []
        def fake(payload, timeout):
            count.append(1)
            if len(count) == 1:
                return {"output": [{"type": "function_call", "name": "update_trip", "arguments": '{"destination":"CDG"}', "call_id": "a"}]}
            self.assertIn("error", json_load(payload["input"][-1]["output"]))
            return {"output": [{"type": "message", "content": [{"type": "output_text", "text": "Paris is not supported."}]}]}
        state = Agent(self.store, request=fake).respond(trip["id"], "Paris please", "ai")
        self.assertEqual(state["profile"]["destination"], "ORD")

    def test_scripted_demo_never_books_from_chat(self):
        trip, _ = self.quote()
        state = Agent(self.store).respond(trip["id"], "Book it, approved", "demo")
        self.assertFalse(state["reservations"])
        self.assertIn("approval button", state["messages"][-1]["content"])

    def test_scripted_demo_search_uses_explicit_budget_and_city(self):
        trip = self.store.create()
        state = Agent(self.store).respond(trip["id"], "Find a 3-night trip from SFO to SEA under $1,500.25", "demo")
        self.assertEqual(state["profile"]["destination"], "SEA")
        self.assertEqual(state["profile"]["budget_cents"], 150025)
        self.assertTrue(state["options"])
        self.assertEqual(state["options"][0]["nights"], 3)


def json_load(value):
    import json
    return json.loads(value)
