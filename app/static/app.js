const API = "/api/v1";
const $ = (selector) => document.querySelector(selector);
const localDate = (date = new Date()) => {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
};
const dateAtLocalNoon = (iso) => new Date(`${iso}T12:00:00`);
const state = { studentId: localStorage.getItem("daywellStudentId"), studentName: localStorage.getItem("daywellStudentName") || "", selectedDay: localDate(), weekStart: null, events: [], entries: [], mood: null };

async function api(path, options = {}) {
  const response = await fetch(`${API}${path}`, { ...options, headers: { "Content-Type": "application/json", ...(options.headers || {}) } });
  const payload = response.status === 204 ? null : await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || `Request failed (${response.status})`);
  return payload;
}
function setMessage(element, message, error = false) { element.textContent = message; element.classList.toggle("error", error); }
function mondayOf(iso) { const day = dateAtLocalNoon(iso); day.setDate(day.getDate() - ((day.getDay() + 6) % 7)); return day; }
function fmtTime(iso) { return new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }); }
function sameDay(a, b) { return localDate(new Date(a)) === localDate(new Date(b)); }
function dateLabel(iso, options = { weekday: "short", month: "short", day: "numeric" }) { return dateAtLocalNoon(iso).toLocaleDateString([], options); }

async function ensureStudent() {
  if (state.studentId) {
    try { const student = await api(`/students/${state.studentId}`); state.studentName = student.display_name; localStorage.setItem("daywellStudentName", state.studentName); return; }
    catch { localStorage.removeItem("daywellStudentId"); state.studentId = null; }
  }
  if (!localStorage.getItem("daywellOnboarded")) $("#student-dialog").showModal();
}
function setIdentity(name) {
  state.studentName = name;
  $("#profile-name").textContent = `${name}’s space`;
  $(".avatar").textContent = name.slice(0, 1).toUpperCase();
  $("#greeting").innerHTML = `A softer way to <em>stay on track.</em>`;
  $(".subheading").textContent = `School is a lot, ${name}. Let’s make space for you in it.`;
}
function setToday() {
  const now = new Date();
  $("#today-label").textContent = now.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" });
  if (state.studentName) setIdentity(state.studentName);
}
function renderWeek() {
  const monday = mondayOf(state.selectedDay);
  state.weekStart = localDate(monday);
  const wrap = $("#week-strip"); wrap.replaceChildren();
  for (let i = 0; i < 7; i++) {
    const d = new Date(monday); d.setDate(d.getDate() + i); const key = localDate(d);
    const chip = document.createElement("button"); chip.className = `day-chip${key === state.selectedDay ? " selected" : ""}${key === localDate() ? " today" : ""}${state.events.some((e) => sameDay(e.starts_at, key)) ? " has-events" : ""}`;
    chip.innerHTML = `<span>${d.toLocaleDateString([], { weekday: "short" })}</span><strong>${d.getDate()}</strong><i></i>`;
    chip.setAttribute("aria-label", dateLabel(key)); chip.addEventListener("click", () => { state.selectedDay = key; renderWeek(); renderSchedule(); }); wrap.append(chip);
  }
}
function renderSchedule() {
  const list = $("#schedule-list"); list.replaceChildren();
  const events = state.events.filter((event) => sameDay(event.starts_at, state.selectedDay)).sort((a, b) => new Date(a.starts_at) - new Date(b.starts_at));
  if (!events.length) {
    const empty = document.createElement("div"); empty.className = "empty-state";
    empty.innerHTML = `<span>✳</span><strong>${state.selectedDay === localDate() ? "Your day still has room for you." : "Nothing on this day yet."}</strong><p>${dateLabel(state.selectedDay)} · You can keep it that way, or add what’s on your mind.</p><button class="outline-button" id="empty-add-event">＋ Add an event</button>`;
    list.append(empty); $("#empty-add-event").addEventListener("click", () => $("#event-dialog").showModal()); return;
  }
  events.forEach((event) => {
    const row = document.createElement("div"); row.className = "event-row";
    const hours = Math.max(0, (new Date(event.ends_at) - new Date(event.starts_at)) / 3600000);
    row.innerHTML = `<div class="event-time">${fmtTime(event.starts_at)}</div><div class="event-marker"></div><div class="event-info"><strong></strong><small></small></div><div class="event-duration">${hours < 1 ? `${Math.round(hours * 60)} min` : `${hours.toFixed(hours % 1 ? 1 : 0)} hr`}</div>`;
    row.querySelector("strong").textContent = event.title; row.querySelector("small").textContent = event.category; list.append(row);
  });
}
function renderSummary() {
  const today = localDate(); const monday = mondayOf(today); const byDay = Array(7).fill(0); let count = 0; let hours = 0;
  state.events.forEach((event) => {
    const start = new Date(event.starts_at), end = new Date(event.ends_at); const h = Math.max(0, (end - start) / 3600000);
    if (start >= monday && start < new Date(monday.getTime() + 7 * 86400000)) { byDay[(start.getDay() + 6) % 7] += h; count++; hours += h; }
  });
  $("#week-hours").textContent = hours.toFixed(hours % 1 ? 1 : 0); $("#event-count").textContent = `${count} ${count === 1 ? "EVENT" : "EVENTS"} THIS WEEK`;
  const bars = $("#mini-bars"); bars.replaceChildren(); const max = Math.max(...byDay, 1);
  byDay.forEach((value, index) => { const bar = document.createElement("div"); const d = new Date(monday); d.setDate(d.getDate() + index); bar.className = `mini-bar${value ? " has-events" : ""}${localDate(d) === today ? " today" : ""}`; bar.style.height = `${Math.max(3, value / max * 26)}px`; bar.dataset.tip = `${d.toLocaleDateString([], { weekday: "short" })}: ${value.toFixed(value % 1 ? 1 : 0)}h`; bars.append(bar); });
  const active = state.entries.slice(0, 7).filter((e) => e.entry_date >= localDate(new Date(Date.now() - 6 * 86400000)));
  $("#checkin-days").textContent = active.length; const dots = $("#week-dots"); dots.replaceChildren();
  for (let i = 0; i < 7; i++) { const d = new Date(); d.setDate(d.getDate() - (6 - i)); const dot = document.createElement("i"); dot.className = `week-dot${state.entries.some((e) => e.entry_date === localDate(d)) ? " filled" : ""}`; dot.title = dateLabel(localDate(d)); dots.append(dot); }
  const latest = state.entries[0];
  if (latest) { const labels = ["A gentler day might help", "Taking it one step at a time", "Finding your footing", "A little more like you", "Feeling good today"];
    $("#mood-copy").textContent = latest.mood ? labels[latest.mood - 1] : "Thanks for checking in"; $("#mood-face").textContent = ["☹", "◔", "😐", "☺", "✿"][Math.max(0, (latest.mood || 3) - 1)];
    $("#mood-detail").textContent = latest.entry_date === today ? "You showed up for yourself today." : `Last check-in · ${dateLabel(latest.entry_date, { month: "short", day: "numeric" })}`;
    $("#sleep-copy").textContent = latest.sleep_hours != null ? `${latest.sleep_hours} hours of sleep logged` : "Your care counts, too";
  }
}
async function loadDashboard() {
  if (!state.studentId) { renderWeek(); renderSchedule(); renderSummary(); return; }
  try {
    const [events, entries] = await Promise.all([
      api(`/students/${state.studentId}/calendar/events?start=${encodeURIComponent(`${localDate(mondayOf(localDate()))}T00:00:00`)}&end=${encodeURIComponent(`${localDate(addDays(mondayOf(localDate()), 7))}T00:00:00`)}`),
      api(`/students/${state.studentId}/wellbeing?limit=30`),
    ]);
    state.events = events; state.entries = entries; renderWeek(); renderSchedule(); renderSummary();
    const todayEntry = entries.find((entry) => entry.entry_date === localDate());
    if (todayEntry) { selectMood(todayEntry.mood); $("#sleep-hours").value = todayEntry.sleep_hours ?? ""; $("#stress-level").value = todayEntry.stress ?? ""; $("#checkin-note").value = todayEntry.notes ?? ""; }
  } catch (error) { console.error(error); }
}
function addDays(date, days) { const d = new Date(date); d.setDate(d.getDate() + days); return d; }
function selectMood(value) { state.mood = value ? Number(value) : null; $("#mood-value").value = state.mood || ""; document.querySelectorAll(".mood-option").forEach((button) => button.classList.toggle("selected", Number(button.dataset.mood) === state.mood)); }
function appendMessage(role, text, time = "JUST NOW") {
  const wrap = $("#chat-messages"); const row = document.createElement("div"); row.className = role === "assistant" ? "day-message" : "user-message";
  if (role === "assistant") row.innerHTML = `<div class="message-avatar">✳</div><div><span class="message-author">DAY <small>${time}</small></span><div class="bubble"></div></div>`;
  else row.innerHTML = `<div><span class="message-author" style="text-align:right">YOU <small>${time}</small></span><div class="bubble"></div></div>`;
  row.querySelector(".bubble").textContent = text; wrap.append(row); wrap.scrollTop = wrap.scrollHeight; return row;
}
async function loadChatHistory() {
  if (!state.studentId) return;
  try { const history = await api(`/students/${state.studentId}/chat/history?limit=30`); if (!history.length) return; const box = $("#chat-messages"); box.replaceChildren(); history.forEach((item) => appendMessage(item.role, item.content, new Date(item.created_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }).toUpperCase())); }
  catch (error) { console.error(error); }
}
async function sendChat(message) {
  if (!message.trim() || !state.studentId) return;
  appendMessage("user", message.trim()); const button = $("#send-button"); button.disabled = true; button.textContent = "…";
  const pending = appendMessage("assistant", "Let me think that through with you…");
  try { const result = await api(`/students/${state.studentId}/chat`, { method: "POST", body: JSON.stringify({ message: message.trim() }) }); pending.remove(); appendMessage("assistant", result.reply); }
  catch (error) { pending.remove(); appendMessage("assistant", error.message.includes("OPENAI_API_KEY") ? "I’m not connected just yet. Please add OPENAI_API_KEY in the server’s .env file, then restart the app." : "I’m having a little trouble connecting right now. Your message is still here—please try again in a moment."); }
  finally { button.disabled = false; button.textContent = "↑"; }
}

$("#student-form").addEventListener("submit", async (event) => {
  event.preventDefault(); const name = $("#student-name").value.trim(); if (!name) return;
  try { const student = state.studentId ? await api(`/students/${state.studentId}`, { method: "PATCH", body: JSON.stringify({ display_name: name }) }) : await api("/students", { method: "POST", body: JSON.stringify({ display_name: name }) }); state.studentId = String(student.id); localStorage.setItem("daywellStudentId", state.studentId); localStorage.setItem("daywellStudentName", name); localStorage.setItem("daywellOnboarded", "1"); $("#student-dialog").close(); setIdentity(name); await loadDashboard(); await loadChatHistory(); }
  catch (error) { alert(error.message); }
});
$("#profile-button").addEventListener("click", () => { $("#student-name").value = state.studentName; $("#student-dialog").showModal(); });
$("#add-event-button").addEventListener("click", () => $("#event-dialog").showModal());
$("#empty-add-event").addEventListener("click", () => $("#event-dialog").showModal());
$("#event-form").addEventListener("submit", async (event) => {
  event.preventDefault(); if (!state.studentId) return;
  const start = new Date($("#event-start").value), end = new Date($("#event-end").value);
  try { await api(`/students/${state.studentId}/calendar/events`, { method: "POST", body: JSON.stringify({ title: $("#event-title").value.trim(), starts_at: start.toISOString(), ends_at: end.toISOString(), category: $("#event-category").value, provider: "manual", external_id: "" }) }); $("#event-dialog").close(); $("#event-form").reset(); await loadDashboard(); }
  catch (error) { alert(error.message); }
});
$("#sync-button").addEventListener("click", () => $("#sync-dialog").showModal());
$("#sync-form").addEventListener("submit", async (event) => {
  event.preventDefault(); if (!state.studentId) return;
  try { const events = JSON.parse($("#sync-json").value); if (!Array.isArray(events)) throw new Error("Paste a JSON array of events."); const result = await api(`/students/${state.studentId}/calendar/sync`, { method: "POST", body: JSON.stringify({ provider: $("#sync-provider").value, events: events.map((item) => ({ ...item, provider: $("#sync-provider").value })) }) }); $("#sync-dialog").close(); $("#sync-form").reset(); await loadDashboard(); alert(`Imported ${result.imported} and updated ${result.updated} events.`); }
  catch (error) { alert(error instanceof SyntaxError ? "That JSON does not look valid. Please check it and try again." : error.message); }
});
document.querySelectorAll(".mood-option").forEach((button) => button.addEventListener("click", () => selectMood(button.dataset.mood)));
$("#checkin-form").addEventListener("submit", async (event) => {
  event.preventDefault(); if (!state.studentId) return; const message = $("#checkin-message");
  const body = { entry_date: localDate(), sleep_hours: $("#sleep-hours").value === "" ? null : Number($("#sleep-hours").value), mood: state.mood, stress: $("#stress-level").value === "" ? null : Number($("#stress-level").value), notes: $("#checkin-note").value.trim() || null };
  try { await api(`/students/${state.studentId}/wellbeing`, { method: "PUT", body: JSON.stringify(body) }); setMessage(message, "Saved. Thank you for checking in with yourself."); await loadDashboard(); }
  catch (error) { setMessage(message, error.message, true); }
});
$("#chat-form").addEventListener("submit", async (event) => { event.preventDefault(); const input = $("#chat-input"); const value = input.value; if (!value.trim()) return; input.value = ""; input.style.height = "auto"; await sendChat(value); });
$("#chat-input").addEventListener("input", (event) => { event.target.style.height = "auto"; event.target.style.height = `${Math.min(event.target.scrollHeight, 95)}px`; });
$("#chat-input").addEventListener("keydown", (event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); $("#chat-form").requestSubmit(); } });
document.querySelectorAll(".suggestion").forEach((button) => button.addEventListener("click", () => sendChat(button.dataset.prompt)));

setToday(); renderWeek(); renderSchedule(); renderSummary(); ensureStudent().then(async () => { if (state.studentId) { setIdentity(state.studentName || "there"); await loadDashboard(); await loadChatHistory(); } });
