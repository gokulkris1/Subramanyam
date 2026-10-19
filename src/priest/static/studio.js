/* Recording studio: Ayyagaru records each step's chant (and voice samples for cloning). */
"use strict";
const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const ST = { key: "", pooja: null, chants: {}, mic: null };

function loadKey() { try { return localStorage.getItem("ayyagaru.studioKey") || ""; } catch { return ""; } }
function saveKey(k) { try { localStorage.setItem("ayyagaru.studioKey", k); } catch {} }
const api = (path, opts = {}) => fetch(path, { ...opts, headers: { ...(opts.headers || {}), "x-studio-key": ST.key } });
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

async function enter() {
  ST.key = $("key").value.trim();
  const r = await api("/api/studio/check");
  if (!r.ok) { $("login-msg").textContent = (await r.json().catch(() => ({}))).error || "Not allowed"; return; }
  saveKey(ST.key);
  $("login").hidden = true; $("studio").hidden = false;
  await loadPooja();
}

async function loadPooja() {
  const list = await (await fetch("/api/poojas")).json();
  const id = params.get("pooja") || list[0].id;
  ST.pooja = await (await fetch(`/api/poojas/${encodeURIComponent(id)}`)).json();
  ST.chants = ST.pooja.chants || {};
  $("pooja-name").textContent = ST.pooja.title;
  $("sample-text").textContent = ST.pooja.steps.slice(0, 6).map((s) => s.say).join(" ");
  renderSteps(); refreshSamples();
}

function chantSteps() { return ST.pooja.steps.filter((s) => s.segment); }

function renderSteps() {
  const steps = chantSteps();
  $("steps").innerHTML = steps.map((s, i) => `
    <div class="card" data-step="${esc(s.id)}">
      <div class="row"><span class="num">${i + 1}</span>
        <div class="title">${esc(s.title)}<small>${esc(s.title_en)} · ${fmt(s.segment[1] - s.segment[0])} in the reference</small></div>
        <span class="badge status"></span></div>
      <details><summary>మంత్రం సూచన · Chant guide (auto captions, may have errors)</summary><div class="guide">${esc(s.chant_guide || "")}</div></details>
      <div class="row">
        <button class="ref-btn">▶ రిఫరెన్స్ వినండి</button>
        <button class="rec" data-kind="chant">● రికార్డ్</button><span class="timer"></span>
        <button class="save" hidden>✓ సేవ్</button>
        <button class="del" hidden>🗑</button>
      </div>
      <audio controls hidden></audio>
      <div class="msg"></div>
    </div>`).join("");
  document.querySelectorAll("#steps .card").forEach((card) => setupCard(card, steps.find((s) => s.id === card.dataset.step)));
  updateCount();
}

function updateCount() {
  const steps = chantSteps(), done = steps.filter((s) => ST.chants[s.id]).length;
  $("count").textContent = `${done} / ${steps.length} దశలు రికార్డ్ అయ్యాయి`;
  $("bar").style.width = `${(done / steps.length) * 100}%`;
  document.querySelectorAll("#steps .card").forEach((card) => {
    const v = ST.chants[card.dataset.step];
    card.classList.toggle("done", !!v);
    const badge = card.querySelector(".status"); badge.textContent = v ? "✓ రికార్డ్ అయింది" : "ఇంకా లేదు"; badge.classList.toggle("ok", !!v);
    card.querySelector(".del").hidden = !v;
    const audio = card.querySelector("audio");
    if (v && !card.dataset.pending) { audio.src = `/api/chant/${ST.pooja.id}/${card.dataset.step}?v=${v}`; audio.hidden = false; }
  });
}

async function getMic() {
  if (ST.mic) return ST.mic;
  // Raw voice: no echo cancellation / noise suppression, which smear chanting.
  ST.mic = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false } });
  return ST.mic;
}

function attachRecorder(card, onSave) {
  const recBtn = card.querySelector(".rec"), saveBtn = card.querySelector(".save");
  const timer = card.querySelector(".timer"), audio = card.querySelector("audio"), msg = card.querySelector(".msg");
  let recorder = null, chunks = [], blob = null, started = 0, tick = null;
  recBtn.addEventListener("click", async () => {
    if (recorder?.state === "recording") { recorder.stop(); return; }
    try {
      const stream = await getMic();
      chunks = []; blob = null; saveBtn.hidden = true; msg.textContent = "";
      recorder = new MediaRecorder(stream);
      recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
      recorder.onstop = () => {
        clearInterval(tick); recBtn.classList.remove("on"); recBtn.textContent = "● మళ్ళీ రికార్డ్";
        blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
        audio.src = URL.createObjectURL(blob); audio.hidden = false; saveBtn.hidden = false;
        card.dataset.pending = "1"; msg.textContent = "వినండి, బాగుంటే సేవ్ చేయండి · Listen back, then save.";
      };
      recorder.start(); started = Date.now();
      recBtn.classList.add("on"); recBtn.textContent = "■ ఆపండి";
      tick = setInterval(() => (timer.textContent = fmt((Date.now() - started) / 1000)), 250);
    } catch (e) { msg.textContent = `మైక్ అందుబాటులో లేదు · Microphone unavailable: ${e.message}`; }
  });
  saveBtn.addEventListener("click", async () => {
    if (!blob) return;
    saveBtn.disabled = true; msg.textContent = "సేవ్ అవుతోంది…";
    try { await onSave(blob); delete card.dataset.pending; saveBtn.hidden = true; msg.textContent = "✓ సేవ్ అయింది"; }
    catch (e) { msg.textContent = `సేవ్ కాలేదు · ${e.message}`; }
    finally { saveBtn.disabled = false; }
  });
}

function setupCard(card, step) {
  attachRecorder(card, async (blob) => {
    const r = await api(`/api/studio/chant/${ST.pooja.id}/${step.id}`, { method: "PUT", body: blob });
    const data = await r.json(); if (!r.ok) throw new Error(data.error || r.status);
    ST.chants[step.id] = data.version; updateCount();
  });
  card.querySelector(".ref-btn").addEventListener("click", () => {
    const [a, b] = step.segment;
    $("ref-frame").src = `https://www.youtube-nocookie.com/embed/${ST.pooja.video.youtube_id}?start=${Math.floor(a)}&end=${Math.ceil(b)}&autoplay=1&rel=0`;
    $("ref").hidden = false;
  });
  card.querySelector(".del").addEventListener("click", async () => {
    if (!confirm("ఈ రికార్డింగ్ తొలగించాలా? Delete this recording?")) return;
    await api(`/api/studio/chant/${ST.pooja.id}/${step.id}`, { method: "DELETE" });
    delete ST.chants[step.id]; card.querySelector("audio").hidden = true; updateCount();
  });
}

async function refreshSamples() {
  const r = await api("/api/studio/voice-samples"); if (!r.ok) return;
  $("sample-count").textContent = `${(await r.json()).samples.length} samples`;
}

attachRecorder($("voice-card"), async (blob) => {
  const r = await api("/api/studio/voice-samples", { method: "POST", body: blob });
  const data = await r.json(); if (!r.ok) throw new Error(data.error || r.status);
  refreshSamples();
});
$("enter").addEventListener("click", enter);
$("key").addEventListener("keydown", (e) => e.key === "Enter" && enter());
$("ref-close").addEventListener("click", () => { $("ref").hidden = true; $("ref-frame").src = "about:blank"; });
$("key").value = params.get("key") || loadKey();
if ($("key").value) enter();
