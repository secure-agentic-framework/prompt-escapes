"""Trip state and booking rules. All monetary values are integer USD cents."""

import copy
import json
import sqlite3
import uuid
from contextlib import closing, contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


CITIES = {
    "SFO": "San Francisco", "ORD": "Chicago", "JFK": "New York",
    "SEA": "Seattle", "BOS": "Boston", "LAX": "Los Angeles",
}
SCENARIOS = {
    "normal": "Smooth sailing",
    "price_change": "Price changes before booking",
    "sold_out": "Flight sells out before booking",
    "hotel_failure": "Hotel fails after flight booking",
    "timeout": "Flight times out after booking",
}


class RuleError(ValueError):
    pass


def uid():
    return uuid.uuid4().hex


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def money(cents):
    return "${:,.2f}".format(cents / 100)


def default_profile():
    start = date.today() + timedelta(days=30)
    return {"origin": "SFO", "destination": "ORD", "departure": start.isoformat(),
            "return_date": (start + timedelta(days=5)).isoformat(),
            "travelers": 1, "budget_cents": 200000, "nonstop": True, "downtown": True}


def validate_profile(profile):
    if set(profile) != set(default_profile()):
        raise RuleError("Trip details contain missing or unsupported fields.")
    for field in ("origin", "destination"):
        if profile[field] not in CITIES:
            raise RuleError("Choose a supported airport: " + ", ".join(CITIES))
    if profile["origin"] == profile["destination"]:
        raise RuleError("Choose different departure and destination airports.")
    try:
        start = date.fromisoformat(profile["departure"])
        end = date.fromisoformat(profile["return_date"])
    except (ValueError, TypeError):
        raise RuleError("Use valid dates in YYYY-MM-DD format.") from None
    nights = (end - start).days
    if start < date.today() or not 1 <= nights <= 30:
        raise RuleError("Choose a future trip lasting 1–30 nights.")
    if type(profile["travelers"]) is not int or not 1 <= profile["travelers"] <= 4:
        raise RuleError("This simulator supports 1–4 travelers, sharing one room.")
    if type(profile["budget_cents"]) is not int or not 10000 <= profile["budget_cents"] <= 10000000:
        raise RuleError("Set a total budget between $100 and $100,000 in whole cents.")
    if type(profile["nonstop"]) is not bool or type(profile["downtown"]) is not bool:
        raise RuleError("Travel requirements must be true or false.")
    return nights


def event(state, tool, result, detail):
    state["events"].append({"id": uid(), "at": timestamp(), "tool": tool,
                            "result": result, "detail": detail})


def message(state, role, text):
    state["messages"].append({"role": role, "content": text, "at": timestamp()})


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as conn, conn:
            conn.execute("CREATE TABLE IF NOT EXISTS trips (id TEXT PRIMARY KEY, state TEXT NOT NULL)")

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def edit(self, trip_id):
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT state FROM trips WHERE id = ?", (trip_id,)).fetchone()
            if row is None:
                raise RuleError("Trip not found. Start a new trip.")
            state = json.loads(row["state"])
            yield state
            conn.execute("UPDATE trips SET state = ? WHERE id = ?", (json.dumps(state), trip_id))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get(self, trip_id):
        with closing(self.connect()) as conn:
            row = conn.execute("SELECT state FROM trips WHERE id = ?", (trip_id,)).fetchone()
        if row is None:
            raise RuleError("Trip not found. Start a new trip.")
        return json.loads(row["state"])

    def create(self, scenario="normal"):
        if scenario not in SCENARIOS:
            raise RuleError("Unknown simulation scenario.")
        state = {"id": uid(), "created_at": timestamp(), "profile": default_profile(),
                 "scenario": scenario, "injected": False, "inventory_revision": 0,
                 "options": [], "reservations": [], "events": [], "messages": [],
                 "status": "draft", "blocked_flights": [], "approved": None}
        message(state, "assistant", "Where would you like to go? Your trip brief has editable example details. "
                "Tell me what to change, or search the brief to compare fictional flights and hotels.")
        with closing(self.connect()) as conn, conn:
            conn.execute("INSERT INTO trips VALUES (?, ?)", (state["id"], json.dumps(state)))
        return state

    def update(self, trip_id, patch):
        if not isinstance(patch, dict) or not patch or set(patch) - set(default_profile()):
            raise RuleError("Provide supported trip details to update.")
        with self.edit(trip_id) as state:
            if any(r["status"] == "confirmed" for r in state["reservations"]):
                raise RuleError("Cancel existing reservations before changing trip details.")
            profile = {**state["profile"], **patch}
            validate_profile(profile)
            state["profile"] = profile
            state["options"] = []
            state["approved"] = None
            state["status"] = "draft"
            event(state, "update_trip", "ok", "Trip brief updated; previous quotes invalidated.")
        return self.get(trip_id)

    def add_message(self, trip_id, role, text):
        with self.edit(trip_id) as state:
            message(state, role, text)

    def search(self, trip_id):
        with self.edit(trip_id) as state:
            profile = state["profile"]
            nights = validate_profile(profile)
            if any(r["status"] == "confirmed" for r in state["reservations"]):
                raise RuleError("This trip has reservations. Retry its booking or cancel before searching again.")
            # Fictional round-trip fares; a deterministic route factor makes routes distinct.
            factor = sum(ord(c) for c in profile["origin"] + profile["destination"]) % 9 * 1200
            surcharge = state["inventory_revision"] * 7500
            flights = [
                {"id": "F1", "carrier": "Juniper Air", "number": "JP 204 / JP 205",
                 "outbound": "09:20 → 15:30", "inbound": "16:10 → 18:30", "stops": 0, "fare_cents": 28500 + factor},
                {"id": "F2", "carrier": "Northstar", "number": "NS 108 / NS 109",
                 "outbound": "11:40 → 17:50", "inbound": "13:00 → 15:20", "stops": 0, "fare_cents": 35500 + factor},
                {"id": "F3", "carrier": "Daybreak", "number": "DB 310 / DB 311",
                 "outbound": "07:00 → 16:40", "inbound": "10:30 → 16:10", "stops": 1, "fare_cents": 22500 + factor},
            ]
            hotels = [
                {"id": "H1", "name": "The Linden House", "area": "Downtown", "downtown": True,
                 "rating": "4.4", "nightly_cents": 14800},
                {"id": "H2", "name": "Atelier Hotel", "area": "Downtown", "downtown": True,
                 "rating": "4.8", "nightly_cents": 19800},
                {"id": "H3", "name": "Parkside Inn", "area": "Airport district", "downtown": False,
                 "rating": "4.1", "nightly_cents": 9800},
            ]
            options = []
            for flight in flights:
                if flight["id"] in state["blocked_flights"] or (profile["nonstop"] and flight["stops"]):
                    continue
                for hotel in hotels:
                    if profile["downtown"] and not hotel["downtown"]:
                        continue
                    air = (flight["fare_cents"] + surcharge) * profile["travelers"]
                    room = hotel["nightly_cents"] * nights
                    tax = (air * 8 + room * 14 + 50) // 100
                    total = air + room + tax
                    if total > profile["budget_cents"]:
                        continue
                    options.append({"id": uid(), "flight": flight, "hotel": hotel,
                                    "flight_cents": air, "hotel_cents": room, "tax_cents": tax,
                                    "total_cents": total, "nights": nights,
                                    "profile": copy.deepcopy(profile), "status": "available"})
            options.sort(key=lambda item: item["total_cents"])
            state["options"] = options[:3]
            state["approved"] = None
            state["status"] = "quoted" if options else "no_options"
            event(state, "search_flights", "ok", "Searched fictional round-trip inventory for " + profile["origin"] + " → " + profile["destination"] + ".")
            event(state, "search_hotels", "ok", "Searched one room for {} nights and {} traveler(s).".format(nights, profile["travelers"]))
            event(state, "price_itinerary", "ok", "{} valid options within budget; all taxes included.".format(len(state["options"])))
        return self.get(trip_id)

    def book(self, trip_id, option_id, expected_total):
        """Only the explicit approval HTTP route calls this, never the model tool dispatcher.

        The ID and exact total bind consent to one persisted quote. A transaction
        serializes retries, and an option/item key prevents duplicate reservations.
        """
        with self.edit(trip_id) as state:
            option = next((o for o in state["options"] if o["id"] == option_id), None)
            if option is None or option["profile"] != state["profile"]:
                raise RuleError("This quote is stale. Search and approve a current option.")
            if type(expected_total) is not int or expected_total != option["total_cents"]:
                raise RuleError("The price has changed. Review and approve the current quote.")
            if option["status"] not in ("available", "partial", "booked"):
                raise RuleError("This option is no longer available. Search for alternatives.")
            active = [r for r in state["reservations"] if r["status"] == "confirmed"]
            if any(r["option_id"] != option_id for r in active):
                raise RuleError("Cancel current reservations before booking another option.")
            if option["status"] == "booked":
                return self.get(trip_id)
            if option["total_cents"] > state["profile"]["budget_cents"]:
                raise RuleError("This itinerary exceeds your budget. Update the brief and search again.")
            scenario = state["scenario"] if not state["injected"] else "normal"
            state["injected"] = True
            if scenario == "price_change":
                state["inventory_revision"] += 1
                for quote in state["options"]:
                    increment = 7500 * state["profile"]["travelers"]
                    quote["flight_cents"] += increment
                    quote["tax_cents"] = (quote["flight_cents"] * 8 + quote["hotel_cents"] * 14 + 50) // 100
                    quote["total_cents"] = quote["flight_cents"] + quote["hotel_cents"] + quote["tax_cents"]
                    if quote["total_cents"] > state["profile"]["budget_cents"]:
                        quote["status"] = "over_budget"
                state["approved"] = None
                state["status"] = "needs_approval"
                event(state, "price_itinerary", "changed", "Flight price increased. No reservations made; new approval required.")
                message(state, "assistant", "The fare changed before booking. I haven’t reserved anything. Review the updated totals and approve again, or search for another option.")
            elif scenario == "sold_out":
                flight_id = option["flight"]["id"]
                state["blocked_flights"].append(flight_id)
                for quote in state["options"]:
                    if quote["flight"]["id"] == flight_id:
                        quote["status"] = "sold_out"
                state["approved"] = None
                state["status"] = "sold_out"
                event(state, "book_flight", "sold_out", "Selected flight sold out. No reservations made.")
                message(state, "assistant", "That flight sold out before booking. Nothing was reserved. Search again to find an available alternative.")
            else:
                state["approved"] = {"option_id": option_id, "total_cents": expected_total, "at": timestamp()}
                for kind in ("flight", "hotel"):
                    existing = next((r for r in active if r["option_id"] == option_id and r["kind"] == kind), None)
                    if existing:
                        event(state, "book_" + kind, "reused", "Existing confirmation retained: " + existing["confirmation"])
                        continue
                    if kind == "hotel" and scenario == "hotel_failure":
                        option["status"] = "partial"
                        state["status"] = "partial"
                        event(state, "book_hotel", "failed", "Simulated hotel provider failure. Flight remains confirmed.")
                        message(state, "assistant", "Your flight is confirmed, but the hotel reservation failed. Retry this same option to book the hotel without duplicating the flight, or cancel the flight below.")
                        break
                    flight_tax = (option["flight_cents"] * 8 + 50) // 100
                    allocated_tax = flight_tax if kind == "flight" else option["tax_cents"] - flight_tax
                    reservation = {"id": uid(), "option_id": option_id, "kind": kind,
                                   "confirmation": "SIM-" + uuid.uuid4().hex[:8].upper(),
                                   "status": "confirmed", "at": timestamp(),
                                   "name": option[kind]["carrier" if kind == "flight" else "name"],
                                   "amount_cents": option[kind + "_cents"] + allocated_tax,
                                   "profile": copy.deepcopy(state["profile"])}
                    state["reservations"].append(reservation)
                    event(state, "book_" + kind, "confirmed", reservation["confirmation"] + " saved to the reservation ledger.")
                    if kind == "flight" and scenario == "timeout":
                        event(state, "book_flight", "timeout", "Provider response lost after commit. Checking the reservation ledger before retrying.")
                        event(state, "get_reservations", "reconciled", "Found " + reservation["confirmation"] + "; no duplicate booking attempted.")
                else:
                    option["status"] = "booked"
                    state["status"] = "booked"
                    message(state, "assistant", "Your simulated trip is confirmed. Both reservations are saved below. Total: " + money(option["total_cents"]) + ". No real tickets, rooms, or payments were created.")
        return self.get(trip_id)

    def cancel(self, trip_id, reservation_id):
        with self.edit(trip_id) as state:
            reservation = next((r for r in state["reservations"] if r["id"] == reservation_id), None)
            if reservation is None:
                raise RuleError("Reservation not found.")
            if reservation["status"] == "confirmed":
                reservation["status"] = "cancelled"
                reservation["cancelled_at"] = timestamp()
                event(state, "cancel_reservation", "cancelled", reservation["confirmation"] + "; full simulated refund.")
                # A cancelled itinerary is never silently completed on a retry.
                for option in state["options"]:
                    if option["id"] == reservation["option_id"]:
                        option["status"] = "cancelled"
                state["approved"] = None
                state["status"] = "partial" if any(r["status"] == "confirmed" for r in state["reservations"]) else "cancelled"
                message(state, "assistant", reservation["confirmation"] + " has been cancelled in the simulation. "
                        + ("Other confirmed reservations remain active below." if state["status"] == "partial" else "No active reservations remain. You can update the brief and search again."))
        return self.get(trip_id)
