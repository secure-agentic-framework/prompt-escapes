/* All provider credentials and booking rules live on the server. */
"use strict";
const $ = (id) => document.getElementById(id);
const currency = (cents) => new Intl.NumberFormat("en-US", {style: "currency", currency: "USD"}).format(cents / 100);
const escapeHTML = (value) => String(value).replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
let config, trip, working = false, pendingOption;
const statusLabels = {draft: "Ready to explore", quoted: "Options ready", no_options: "Let’s adjust the brief", needs_approval: "Price changed · review again", sold_out: "Flight sold out · search again", partial: "Partially reserved", booked: "Trip confirmed", cancelled: "Reservations cancelled"};

async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json", "X-Travel-Token": config.csrf}, body: JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "The request failed.");
  return data;
}
function notify(text, error = false) {
  $("notice").textContent = text;
  $("notice").classList.toggle("error", error);
  $("notice").hidden = !text;
}
function updateBusy() {
  document.body.classList.toggle("busy", working);
  document.querySelectorAll("button,input,select,textarea").forEach((el) => {
    if (!el.closest("dialog")) el.disabled = working || el.dataset.unavailable === "true";
  });
  $("search-button").textContent = working ? "Working on your journey…" : "Find my options →";
}
async function work(action) {
  if (working) return;
  working = true;
  notify("");
  updateBusy();
  try { await action(); }
  catch (error) {
    notify(error.message, true);
    if (trip) {
      try { trip = await api(`/api/trips/${trip.id}`); render(); } catch (_) { /* Preserve the original error. */ }
    }
  } finally { working = false; updateBusy(); }
}
function brief() {
  const budget = $("budget").value;
  if (!/^\d+(?:\.\d{1,2})?$/.test(budget)) throw new Error("Enter a USD budget with at most two decimal places.");
  const [dollars, cents = ""] = budget.split(".");
  return {origin: $("origin").value, destination: $("destination").value,
    departure: $("departure").value, return_date: $("return_date").value,
    travelers: Number($("travelers").value), budget_cents: Number(dollars) * 100 + Number(cents.padEnd(2, "0")),
    nonstop: $("nonstop").checked, downtown: $("downtown").checked};
}
function renderBrief() {
  const p = trip.profile;
  for (const name of ["origin", "destination", "departure", "return_date", "travelers"]) $(name).value = p[name];
  $("budget").value = (p.budget_cents / 100).toFixed(2);
  $("nonstop").checked = p.nonstop;
  $("downtown").checked = p.downtown;
}
function render() {
  renderBrief();
  $("trip-status").textContent = statusLabels[trip.status] || trip.status;
  $("trip-id").textContent = trip.id.slice(0, 8).toUpperCase();
  $("trip-status").title = config.scenarios[trip.scenario];
  $("messages").replaceChildren();
  for (const m of trip.messages) {
    const item = document.createElement("div");
    item.className = "message " + (m.role === "user" ? "user" : "assistant");
    const name = document.createElement("span");
    name.className = "speaker";
    name.textContent = m.role === "user" ? "YOU" : "WAYFARER";
    const content = document.createElement("span");
    content.textContent = m.content;
    item.append(name, content);
    $("messages").append(item);
  }
  $("messages").scrollTop = $("messages").scrollHeight;
  const activeOption = trip.reservations.find((r) => r.status === "confirmed")?.option_id;
  const available = trip.options.filter((o) => o.status === "available" && (!activeOption || activeOption === o.id));
  $("option-count").textContent = trip.status === "booked" ? "Your itinerary is confirmed" : trip.options.length ? `${available.length} available · USD` : trip.status === "no_options" ? "No matches within budget" : "Awaiting your brief";
  $("options").innerHTML = trip.options.length ? trip.options.map((o, index) => {
    const blockedByReservation = activeOption && activeOption !== o.id;
    const canBook = ["available", "partial"].includes(o.status) && !blockedByReservation;
    const label = blockedByReservation && o.status === "available" ? "Cancel current reservations first" : {available: "Approve & book", partial: "Retry remaining booking", booked: "Confirmed", sold_out: "Flight sold out", over_budget: "Over budget", cancelled: "Cancelled"}[o.status] || o.status;
    return `<article class="option"><div class="option-label"><span>${index === 0 ? "LOWEST TOTAL" : "ANOTHER WAY TO GO"}</span><span>0${index + 1}</span></div><div class="option-content"><div class="option-route">${escapeHTML(o.profile.origin)} <span aria-label="round trip">⇄</span> ${escapeHTML(o.profile.destination)}</div><div><div class="option-carrier">${escapeHTML(o.flight.carrier)}</div><div class="option-meta">${o.flight.stops ? "1 connection each way" : "Nonstop both ways"} · ${o.profile.travelers} traveler${o.profile.travelers === 1 ? "" : "s"}</div><div class="flight-times">Out ${escapeHTML(o.flight.outbound)}<br>Back ${escapeHTML(o.flight.inbound)}</div><div class="option-meta">Illustrative times · fictional schedule</div></div><div class="option-hotel"><h3>${escapeHTML(o.hotel.name)}</h3><div class="option-meta">${escapeHTML(o.hotel.area)} · ${escapeHTML(o.hotel.rating)} / 5</div><div class="option-meta">${o.nights} nights · 1 shared room</div></div></div><div class="option-price"><div class="cost-row"><span>Round-trip flights</span><span>${currency(o.flight_cents)}</span></div><div class="cost-row"><span>Hotel · ${o.nights} nights</span><span>${currency(o.hotel_cents)}</span></div><div class="cost-row"><span>All taxes & fees</span><span>${currency(o.tax_cents)}</span></div><div class="total-row"><strong>${currency(o.total_cents)}</strong><span>TRIP TOTAL</span></div><button data-book="${escapeHTML(o.id)}" data-unavailable="${!canBook}" ${canBook ? "" : "disabled"}>${escapeHTML(label)}</button></div></article>`;
  }).join("") : `<div class="empty-state"><span class="empty-icon" aria-hidden="true">↗</span><div><h3>${trip.status === "no_options" ? "A small change opens new doors." : "Every good trip starts here."}</h3><p>${trip.status === "no_options" ? "No options meet every requirement. Raise the budget, shorten the trip, or choose more flexible requirements, then search again." : "Tell your agent what you’re dreaming of, or search your trip brief. We’ll put the possibilities right here."}</p></div></div>`;
  const active = trip.reservations.filter((r) => r.status === "confirmed");
  $("reservation-count").textContent = `${active.length} confirmed`;
  $("reservations").innerHTML = trip.reservations.length ? trip.reservations.map((r) => `<div class="reservation"><span class="reservation-symbol" aria-hidden="true">${r.kind === "flight" ? "↗" : "⌂"}</span><div class="reservation-info"><strong>${escapeHTML(r.name)}</strong><p>${escapeHTML(r.profile.origin)} → ${escapeHTML(r.profile.destination)} · ${escapeHTML(r.profile.departure)} to ${escapeHTML(r.profile.return_date)}</p><p><span class="confirmation">${escapeHTML(r.confirmation)}</span> · ${currency(r.amount_cents)} incl. allocated tax</p></div><div class="reservation-right"><span class="badge ${r.status === "cancelled" ? "cancelled" : ""}">${escapeHTML(r.status)}</span>${r.status === "confirmed" ? `<button class="cancel-button" data-cancel="${escapeHTML(r.id)}">Cancel reservation</button>` : ""}</div></div>`).join("") : '<p class="ledger-empty">Nothing reserved yet. You’ll review the exact total before any simulated booking is made.</p>';
  $("event-count").textContent = `${trip.events.length} events`;
  $("events").innerHTML = trip.events.slice().reverse().map((e) => `<li><time class="event-time" datetime="${escapeHTML(e.at)}">${escapeHTML(new Date(e.at).toLocaleTimeString([], {hour: "2-digit", minute: "2-digit", second: "2-digit"}))}</time><div><span class="event-tool">${escapeHTML(e.tool)}</span><span class="event-result">${escapeHTML(e.result)}</span><p class="event-detail">${escapeHTML(e.detail)}</p></div></li>`).join("");
  if (!trip.events.length) $("events").innerHTML = '<li><span></span><span class="muted">Searches, bookings, and recovery steps will appear here.</span></li>';
  updateBusy();
}
function setMode() {
  const ai = $("mode").value === "ai";
  $("mode-description").textContent = ai ? `OpenAI · ${config.model}` : "Scripted demo · no model calls";
  if (ai && !config.ai_available) notify("AI mode needs OPENAI_API_KEY in the server’s launch environment. Scripted demo mode works without a key.");
  else notify("");
  localStorage.setItem("wayfarer-mode", $("mode").value);
}
async function startTrip(scenario) {
  trip = await api("/api/trips", {scenario});
  localStorage.setItem("wayfarer-trip", trip.id);
  render();
}

$("brief-form").addEventListener("submit", (e) => {
  e.preventDefault();
  work(async () => {
    trip = await api(`/api/trips/${trip.id}/profile`, brief());
    trip = await api(`/api/trips/${trip.id}/search`, {});
    render();
    notify(trip.options.length ? "Options are ready. Review the itinerary and exact total before approving." : "No matches meet this brief. Adjust the details and search again.");
  });
});
$("chat-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const text = $("chat-input").value.trim();
  if (!text) return;
  work(async () => {
    trip = await api(`/api/trips/${trip.id}/chat`, {message: text, mode: $("mode").value});
    $("chat-input").value = "";
    render();
  });
});
$("chat-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); $("chat-form").requestSubmit(); }
});
document.querySelectorAll("[data-prompt]").forEach((button) => button.addEventListener("click", () => {
  $("chat-input").value = button.dataset.prompt;
  $("chat-form").requestSubmit();
}));
$("options").addEventListener("click", (e) => {
  const button = e.target.closest("[data-book]");
  if (!button || working) return;
  pendingOption = trip.options.find((o) => o.id === button.dataset.book);
  $("approval-description").textContent = `${pendingOption.profile.origin} ⇄ ${pendingOption.profile.destination} · ${pendingOption.profile.departure} to ${pendingOption.profile.return_date}. ${pendingOption.flight.carrier} and ${pendingOption.nights} nights at ${pendingOption.hotel.name}.`;
  $("approval-total").textContent = currency(pendingOption.total_cents);
  $("approval-dialog").returnValue = "cancel";
  $("approval-dialog").showModal();
});
$("approval-dialog").addEventListener("close", () => {
  if ($("approval-dialog").returnValue !== "approve" || !pendingOption) return;
  const approved = pendingOption;
  pendingOption = null;
  work(async () => {
    trip = await api(`/api/trips/${trip.id}/book`, {approved: true, option_id: approved.id, expected_total: approved.total_cents});
    render();
    if (trip.status !== "booked") {
      $("activity").open = true;
      notify(trip.messages[trip.messages.length - 1].content);
    } else { notify("Your simulated reservations are confirmed and saved."); }
  });
});
$("reservations").addEventListener("click", (e) => {
  const button = e.target.closest("[data-cancel]");
  if (!button || working) return;
  const reservation = trip.reservations.find((r) => r.id === button.dataset.cancel);
  if (!window.confirm(`Cancel ${reservation.confirmation} (${reservation.name})? This affects only this simulated reservation.`)) return;
  work(async () => {
    trip = await api(`/api/trips/${trip.id}/cancel`, {approved: true, reservation_id: reservation.id});
    render();
    notify("Simulated reservation cancelled. Any other confirmed reservations remain active.");
  });
});
$("mode").addEventListener("change", setMode);
$("new-trip").addEventListener("click", () => {
  const scenario = $("scenario").value;
  if (trip && trip.reservations.some((r) => r.status === "confirmed") && !window.confirm("Start a new trip? Existing simulated reservations stay saved, but won’t appear in the new trip.")) return;
  work(() => startTrip(scenario));
});
async function init() {
  config = await api("/api/config");
  for (const id of ["origin", "destination"]) {
    for (const [code, name] of Object.entries(config.cities)) $(id).add(new Option(`${name} (${code})`, code));
  }
  $("departure").min = new Date().toLocaleDateString("en-CA");
  $("mode").value = localStorage.getItem("wayfarer-mode") || (config.ai_available ? "ai" : "demo");
  setMode();
  const saved = localStorage.getItem("wayfarer-trip");
  if (saved) {
    try { trip = await api(`/api/trips/${saved}`); } catch (_) { localStorage.removeItem("wayfarer-trip"); }
  }
  if (!trip) await startTrip("normal");
  else render();
}
init().catch((error) => notify(`Unable to connect: ${error.message}. Start the local server and reload.`, true));
