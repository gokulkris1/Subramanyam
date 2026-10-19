/* Ayyagaru live pooja call.
 * Flow per step: Ayyagaru says the instruction -> the step's chant: Ayyagaru's own recording
 * (lip-synced on his face) when it exists, otherwise the source video's segment for that step
 * (?fallback=pause gives a soft mangala vadyam pause instead) -> live camera watching ->
 * Ayyagaru checks the camera / waits for "done". */
"use strict";

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);

const TEXT = {
  te: {
    calling: "కాల్ చేస్తున్నాం…", ringing: "రింగ్ అవుతోంది…", connecting: "కనెక్ట్ అవుతోంది…",
    step: (i, n) => `దశ ${i}/${n}`,
    sayDone: "పూర్తయ్యాక 'అయిపోయింది' అని చెప్పండి, లేదా అయింది బటన్ నొక్కండి.",
    moveOn: "సరే, ముందుకు వెళ్దాం.", paused: "సరే, ఆగుతున్నాను. సిద్ధమైనప్పుడు 'కొనసాగించండి' అనండి.",
    resumed: "సరే, కొనసాగిద్దాం.", pause: "ఆగు", resume: "కొనసాగు",
    noCamera: "కెమెరా అందుబాటులో లేదు — వాయిస్/బటన్‌తో కొనసాగుతాం.",
    noMic: "ఈ ఫోన్‌లో మాట గుర్తింపు లేదు — కింది బటన్లు వాడండి.",
    noVoice: "ఫోన్‌లో తెలుగు వాయిస్ లేదు — సూచనలు తెరపై చూపిస్తాం.",
    noVision: "అయ్యగారు ఇంకా కెమెరా చూడలేరు — ప్రతి దశ తర్వాత 'అయిపోయింది' అనండి.",
    eyeOn: "చూస్తున్నారు", eyeOff: "కెమెరా ఆఫ్", looking: "చూస్తున్నారు…",
    endConfirm: "కాల్ ముగించాలా?", endedTitle: "పూజ పూర్తయింది", endedEarly: "కాల్ ముగిసింది",
    you: "మీరు", today: "ఈరోజు పూజ", items: "కావలసిన సామగ్రి", voiceLabel: "అయ్యగారు స్వరం",
    voiceSample: "నమస్కారం. నేను మీ అయ్యగారిని. ఈరోజు మహానవమి పూజ కలిసి చేద్దాం.", music: "మంగళ వాద్యం",
    callHint: "అయ్యగారికి వీడియో కాల్ చేయండి",
    fine: "ఫోన్‌ను మీరు, పూజా స్థలం కనిపించేలా నిలబెట్టండి. కెమెరా, మైక్ అనుమతి అడిగినప్పుడు \"అనుమతించు\" నొక్కండి.",
  },
  en: {
    calling: "Calling…", ringing: "Ringing…", connecting: "Connecting…",
    step: (i, n) => `Step ${i}/${n}`,
    sayDone: "When you have finished, say 'done' or tap the Done button.",
    moveOn: "Alright, let us move on.", paused: "Okay, I will wait. Say 'continue' when you are ready.",
    resumed: "Okay, let us continue.", pause: "Pause", resume: "Resume",
    noCamera: "Camera unavailable — continuing with voice and buttons.",
    noMic: "Voice recognition isn't supported here — use the buttons (Android Chrome works best).",
    noVoice: "No voice found for this language — instructions are shown on screen.",
    noVision: "Ayyagaru's camera vision is off (no API key on the server).",
    eyeOn: "watching", eyeOff: "camera off", looking: "looking…",
    endConfirm: "End the call?", endedTitle: "Pooja complete", endedEarly: "Call ended",
    you: "You", today: "Today's pooja", items: "Items to keep ready", voiceLabel: "Ayyagaru's voice",
    voiceSample: "Namaskaram. I am your Ayyagaru. Let us do the Mahanavami pooja together.", music: "Mangala vadyam",
    callHint: "Video call Ayyagaru",
    fine: "Prop the phone so it sees you and the pooja place. Allow camera and microphone when asked.",
  },
};

const COMMANDS = [
  ["done", /(అయిపోయింది|ఐపోయింది|అయ్యింది|అయింది|పూర్తయింది|పూర్తి అయింది|అయిపోయిందండి|\bdone\b|finished|\bnext\b)/i],
  ["repeat", /(మళ్ళీ|మళ్లీ|మరలా|\brepeat\b|\bagain\b)/i],
  ["pause", /(ఆగండి|ఆగు|ఒక్క నిమిషం|ఒక నిమిషం|\bwait\b|\bpause\b|\bhold on\b)/i],
  ["resume", /(కొనసాగించండి|కొనసాగండి|కొనసాగు|మొదలుపెట్టండి|\bcontinue\b|\bresume\b|\bgo on\b)/i],
];

const S = {
  pooja: null, lang: params.get("lang") === "en" ? "en" : "te", vision: false,
  index: 0, token: 0, paused: false, ended: false,
  history: [], waiters: new Set(), stream: null, facing: "user",
  chantEl: null, chanting: false, interlude: false, recognition: null,
  playing: false, player: null, playerReady: null, fallback: params.get("fallback") === "pause" ? "pause" : "video", micOn: true, speaking: false,
  callStart: 0, timer: null, wakeLock: null, audio: null, ring: null, voices: [],
  voice: "ayyagaru", music: null, musicGain: null, musicVol: 0.5, musicTimer: null, festive: false,
};
const t = () => TEXT[S.lang];

/* ---------- small utilities ---------- */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function toast(msg, ms = 4000) {
  const el = $("toast"); el.textContent = msg; el.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => (el.hidden = true), ms);
}
function show(screen) {
  document.querySelectorAll(".screen").forEach((s) => s.classList.toggle("active", s.id === screen));
}
class Interrupted extends Error {}
function guard(token) { if (token !== S.token || S.ended) throw new Interrupted(); }

/* Event bus: waitFor(["done"], ms) resolves with the event name, or "timeout". */
function emit(name, data) { for (const w of [...S.waiters]) if (w.names.includes(name)) w.resolve(name, data); }
function waitFor(names, ms = 0) {
  let w;
  const p = new Promise((resolve) => {
    w = { names, resolve: (n) => { S.waiters.delete(w); clearTimeout(w.timer); resolve(n); } };
    if (ms > 0) w.timer = setTimeout(() => w.resolve("timeout"), ms);
    S.waiters.add(w);
  });
  p.cancel = () => w.resolve("cancelled");
  return p;
}
async function whileUnpaused(token) {
  while (S.paused) { await waitFor(["resume", "abort"]); guard(token); }
}

/* ---------- loading ---------- */
async function boot() {
  const list = await (await fetch("/api/poojas")).json();
  const id = params.get("pooja") || list[0]?.id;
  S.pooja = await (await fetch(`/api/poojas/${encodeURIComponent(id)}`)).json();
  S.vision = !!S.pooja.vision;
  renderHome();
  const needsVideo = S.fallback === "video" && S.pooja.video?.youtube_id &&
    S.pooja.steps.some((st) => st.segment && !S.pooja.chants?.[st.id]);
  S.playerReady = needsVideo ? loadYouTube() : null;
  $("call-btn").disabled = false;
  loadFace();
  S.musicVol = Math.min(1, Math.max(0, Number(params.get("music") ?? loadPref("musicVol", 0.5)) || 0));
  $("music-vol").value = Math.round(S.musicVol * 100);
  if (S.musicVol === 0) $("music-btn").textContent = "🔇";
  loadVoices().catch((e) => console.warn("voices", e));
  if ("speechSynthesis" in window) {
    const load = () => (S.voices = speechSynthesis.getVoices());
    load(); speechSynthesis.onvoiceschanged = load;
  }
  setLang(S.lang);
}
function escapeHtml(s) { return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
function renderHome() {
  const en = S.lang === "en";
  $("pooja-title").textContent = en ? S.pooja.title_en : S.pooja.title;
  $("pooja-title-en").textContent = "";
  $("items-list").innerHTML = S.pooja.items.map((it) => `<li>${escapeHtml(en ? it.en : it.te)}</li>`).join("");
  $("today-label").textContent = t().today; $("items-label").textContent = t().items;
  $("call-hint").textContent = t().callHint; $("fine").textContent = t().fine;
  $("voice-label").textContent = t().voiceLabel; $("music-label").textContent = t().music;
  document.documentElement.lang = S.lang;
}
function setLang(lang) {
  S.lang = lang;
  $("veil-text").textContent = lang === "te" ? "🙏 అయ్యగారు మిమ్మల్ని చూస్తున్నారు" : "🙏 Ayyagaru is with you";
  document.querySelectorAll(".lang-btn").forEach((b) => {
    const on = b.dataset.lang === lang; b.classList.toggle("active", on); b.setAttribute("aria-checked", on);
  });
}

/* Source-video fallback for steps Ayyagaru hasn't recorded yet. */
function loadYouTube() {
  return new Promise((resolve) => {
    window.onYouTubeIframeAPIReady = () => {
      S.player = new YT.Player("player", {
        videoId: S.pooja.video.youtube_id,
        playerVars: { playsinline: 1, controls: 0, rel: 0, modestbranding: 1, disablekb: 1, fs: 0, iv_load_policy: 3 },
        events: { onReady: () => resolve(S.player), onStateChange: (e) => {
          const playing = e.data === YT.PlayerState.PLAYING || e.data === YT.PlayerState.BUFFERING;
          document.querySelector(".remote").classList.toggle("playing", playing && S.playing);
        } },
      });
    };
    const s = document.createElement("script"); s.src = "https://www.youtube.com/iframe_api"; document.head.appendChild(s);
  });
}

/* ---------- ring tone (Indian double ring) ---------- */
function startRing() {
  try {
    S.audio = S.audio || new (window.AudioContext || window.webkitAudioContext)();
    const ctx = S.audio, gain = ctx.createGain(); gain.gain.value = 0; gain.connect(ctx.destination);
    [400, 450].forEach((f) => { const o = ctx.createOscillator(); o.frequency.value = f; o.connect(gain); o.start(); });
    let on = true;
    const pattern = () => {
      if (!on) return;
      const n = ctx.currentTime;
      [[0, .4], [.6, 1.0]].forEach(([a, b]) => { gain.gain.setValueAtTime(0.12, n + a); gain.gain.setValueAtTime(0, n + b); });
      S.ring.timer = setTimeout(pattern, 3000);
    };
    S.ring = { stop: () => { on = false; clearTimeout(S.ring.timer); gain.gain.cancelScheduledValues(0); gain.gain.value = 0; gain.disconnect(); } };
    pattern();
  } catch { S.ring = { stop() {} }; }
}

/* ---------- camera ---------- */
async function startCamera() {
  try {
    S.stream?.getTracks().forEach((tr) => tr.stop());
    S.stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: S.facing, width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false,
    });
    $("self").srcObject = S.stream;
    $("self").classList.toggle("rear", S.facing !== "user");
    return true;
  } catch (e) {
    console.warn("camera", e); toast(t().noCamera); return false;
  }
}
function captureFrame() {
  const v = $("self");
  if (!S.stream || !v.videoWidth) return null;
  const w = 640, h = Math.round((v.videoHeight / v.videoWidth) * w);
  const c = captureFrame.c || (captureFrame.c = document.createElement("canvas"));
  c.width = w; c.height = h; c.getContext("2d").drawImage(v, 0, 0, w, h);
  return c.toDataURL("image/jpeg", 0.72).split(",")[1];
}

/* ---------- speech out ---------- */
function pickVoice(lang) {
  const want = lang === "te" ? "te" : "en";
  const vs = S.voices.filter((v) => v.lang.toLowerCase().replace("_", "-").startsWith(want));
  return vs.find((v) => /india|-in/i.test(v.lang + v.name)) || vs[0] || null;
}
function setCaption(text) { $("cap-priest").textContent = text || ""; }
function setUserCaption(text) {
  $("cap-user").textContent = text ? `${t().you}: ${text}` : "";
  clearTimeout(setUserCaption._t); setUserCaption._t = setTimeout(() => ($("cap-user").textContent = ""), 5000);
}
/* ---------- per-device preferences ---------- */
function loadPref(key, fallback) { try { return localStorage.getItem(`ayyagaru.${key}`) ?? fallback; } catch { return fallback; } }
function savePref(key, value) { try { localStorage.setItem(`ayyagaru.${key}`, value); } catch {} }

/* ---------- voice choice ---------- */
const ttsUrl = (text) => `/api/tts?lang=${S.lang}&voice=${S.voice}&text=${encodeURIComponent(text)}`;
async function loadVoices() {
  const data = await (await fetch("/api/voices")).json();
  const ids = data.voices.map((v) => v.id);
  S.voice = [params.get("voice"), loadPref("voice", null), data.default].find((v) => ids.includes(v));
  $("voice-list").innerHTML = data.voices.map((v) => `<div class="voice-row">
      <button class="voice-btn" data-voice="${v.id}" role="radio" aria-checked="false">${escapeHtml(S.lang === "en" ? v.label_en : v.label_te)}</button>
      <button class="voice-play" data-voice="${v.id}" aria-label="Preview voice">▶</button></div>`).join("");
  const mark = () => document.querySelectorAll(".voice-btn").forEach((b) => b.setAttribute("aria-checked", b.dataset.voice === S.voice));
  const preview = () => { const a = S.previewEl || (S.previewEl = new Audio()); a.src = ttsUrl(t().voiceSample); a.play().catch(() => {}); };
  document.querySelectorAll(".voice-btn").forEach((b) => b.addEventListener("click", () => { S.voice = b.dataset.voice; savePref("voice", S.voice); mark(); preview(); }));
  document.querySelectorAll(".voice-play").forEach((b) => b.addEventListener("click", () => { S.voice = b.dataset.voice; savePref("voice", S.voice); mark(); preview(); }));
  mark();
}

/* ---------- gentle mangala vadyam in the background ---------- */
const MUSIC_MAX = 0.3;   // even 100% on the slider stays soft
function setupMusic() {
  if (S.musicGain) return;
  try {
    S.audio = S.audio || new (window.AudioContext || window.webkitAudioContext)();
    S.music = new Audio("/static/music/mangala_vadyam.mp3"); S.music.loop = true;
    S.musicGain = S.audio.createGain(); S.musicGain.gain.value = 0;   // GainNode: iOS ignores element.volume
    S.audio.createMediaElementSource(S.music).connect(S.musicGain).connect(S.audio.destination);
  } catch (e) { console.warn("music", e); S.musicGain = null; }
}
function musicDuck() {
  if (S.speaking) return 0.35;                  // under Ayyagaru's voice
  if (S.chanting || S.playing) return S.festive ? 0.6 : 0.25; // under the chant; fuller at harati
  if (S.interlude) return 1.6;                   // a gentle swell while the family does the step
  return 1;
}
function updateMusic() {
  if (!S.musicGain) return;
  const target = S.ended ? 0 : S.musicVol * MUSIC_MAX * musicDuck();
  S.musicGain.gain.setTargetAtTime(target, S.audio.currentTime, 0.5);
  if (target > 0 && S.music.paused && !S.ended) S.music.play().catch(() => {});
}

/* ---------- Ayyagaru's face ---------- */
// His photo talks: face.js moves the jaw and lips with his voice, blinks and sways gently.
// Swap the photo by replacing static/img/ayyagaru.jpg (or ?avatar=<image url> to try one).
async function loadFace() {
  const src = params.get("avatar") || "/static/img/ayyagaru.jpg";
  const portrait = params.get("avatar") || "/static/img/ayyagaru_portrait.jpg";
  const home = $("home-face");
  home.onload = () => { home.hidden = false; $("home-om").hidden = true; $("ring-thumb").src = portrait; };
  home.src = portrait;
  try {
    const { TalkingFace } = await import("/static/face.js");
    S.face = await new TalkingFace($("face")).load(src);
    $("face").hidden = false; document.querySelector(".veil").classList.add("has-face");
  } catch (e) { console.warn("talking face unavailable", e); S.face = null; }
}
function setupVoiceMeter() {
  if (S.voiceMeter || !S.audio || !S.voiceEl) return;
  try {
    const analyser = S.audio.createAnalyser(); analyser.fftSize = 512;
    S.audio.createMediaElementSource(S.voiceEl).connect(analyser);
    S.audio.createMediaElementSource(S.chantEl).connect(analyser);   // his chanting drives the face too
    analyser.connect(S.audio.destination);
    const data = new Uint8Array(analyser.fftSize); const avatar = $("avatar"); let smooth = 0;
    const tick = () => {
      analyser.getByteTimeDomainData(data);
      let sum = 0; for (const v of data) sum += (v - 128) * (v - 128);
      const level = Math.min(1, Math.sqrt(sum / data.length) / 40);
      smooth = smooth * 0.7 + level * 0.3;
      avatar.style.setProperty("--level", smooth.toFixed(3));
      S.face?.setLevel(level);
      S.voiceMeter = requestAnimationFrame(tick);
    };
    tick();
  } catch (e) { console.warn("voice meter", e); S.voiceMeter = -1; }
}

/* Telugu voice from the server (works on phones without a Telugu voice installed).
 * Resolves true when played (or interrupted), false to fall back to the device voice. */
async function speakAudio(text) {
  const el = S.voiceEl;
  if (!el || S.serverVoiceBroken) return false;
  S.speaking = true; pauseListening();
  const interrupt = waitFor(["skip", "abort"]);
  try {
    return await new Promise((resolve) => {
      let finished = false; const finish = (ok) => { if (!finished) { finished = true; resolve(ok); } };
      el.onended = () => finish(true);
      el.onerror = () => { S.serverVoiceBroken = true; finish(false); };
      el.muted = false;
      el.src = ttsUrl(text);
      el.play().catch(() => finish(false));
      setTimeout(() => finish(true), Math.max(8000, text.length * 200));
      interrupt.then((ev) => { if (ev !== "cancelled") { el.pause(); finish(true); } });
    });
  } finally { interrupt.cancel(); S.speaking = false; resumeListening(); }
}

async function speak(text, token) {
  if (!text) return;
  setCaption(text);
  S.history.push({ who: "Ayyagaru", text });
  const minRead = Math.max(1800, text.length * 75);
  if (await speakAudio(text)) { if (token !== undefined) guard(token); return; }
  if (!("speechSynthesis" in window)) {
    const w = waitFor(["skip", "abort"], minRead); await w; if (token !== undefined) guard(token); return;
  }
  const voice = pickVoice(S.lang);
  if (!voice && !speak.warned) { speak.warned = true; toast(t().noVoice, 6000); }
  S.speaking = true; pauseListening();
  const interrupt = waitFor(["skip", "abort"]);
  try {
    await new Promise((resolve) => {
      const u = new SpeechSynthesisUtterance(text);
      u.lang = S.lang === "te" ? "te-IN" : "en-IN"; if (voice) u.voice = voice;
      u.rate = S.lang === "te" ? 0.92 : 0.95;
      let finished = false; const finish = () => { if (!finished) { finished = true; resolve(); } };
      u.onend = finish; u.onerror = finish;
      speechSynthesis.cancel(); speechSynthesis.speak(u);
      // Safety nets: engines without a voice may never fire onend; "skip" cancels.
      setTimeout(finish, minRead * 3 + 4000);
      interrupt.then((ev) => { if (ev !== "cancelled") speechSynthesis.cancel(); finish(); });
      if (!voice) setTimeout(() => { if (!speechSynthesis.speaking) finish(); }, minRead);
    });
  } finally { interrupt.cancel(); S.speaking = false; resumeListening(); }
  if (token !== undefined) guard(token);
}

/* ---------- speech in ---------- */
function setupRecognition() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { toast(t().noMic, 6000); $("mic-btn").classList.add("off"); S.micOn = false; return; }
  const r = new SR();
  r.lang = S.lang === "te" ? "te-IN" : "en-IN"; r.continuous = true; r.interimResults = false;
  r.onresult = (e) => {
    for (let i = e.resultIndex; i < e.results.length; i++) if (e.results[i].isFinal) onHeard(e.results[i][0].transcript.trim());
  };
  r.onerror = (e) => { if (e.error === "not-allowed") { S.micOn = false; $("mic-btn").classList.add("off"); } };
  r.onend = () => { r.running = false; setTimeout(resumeListening, 250); };
  S.recognition = r; resumeListening();
}
function resumeListening() {
  const r = S.recognition;
  if (!r || r.running || !S.micOn || S.speaking || S.ended) return;
  try { r.start(); r.running = true; } catch { /* already started */ }
}
function pauseListening() { const r = S.recognition; if (r?.running) { try { r.stop(); } catch {} } }

function onHeard(text) {
  if (!text || S.speaking) return;
  const cmd = COMMANDS.find(([, re]) => re.test(text))?.[0];
  if ((S.chanting || S.playing) && !cmd) return;   // ignore chanting picked up by the mic
  setUserCaption(text);
  S.history.push({ who: "User", text });
  if (cmd === "pause") return doPause();
  if (cmd === "resume") return doResume();
  if (cmd === "repeat") return doRepeat();
  if (cmd === "done") return emit("done");
  emit("question", text);
  askPriest(text);
}

/* ---------- talking to the agent ---------- */
async function turn(mode, extra = {}) {
  const step = S.pooja.steps[S.index];
  const eye = $("eye"); if (mode !== "ask" && S.vision) { eye.classList.add("looking"); $("eye-text").textContent = t().looking; }
  try {
    const res = await fetch("/api/turn", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pooja_id: S.pooja.id, step_id: step.id, mode, lang: S.lang,
        frame: captureFrame(), history: S.history.slice(-8), ...extra }),
    });
    if (!res.ok) return { done: null, say: "", available: false };
    const data = await res.json();
    if (data.available === false && S.vision) { S.vision = false; updateEye(); toast(t().noVision, 6000); }
    return data;
  } catch { return { done: null, say: "", available: false }; }
  finally { eye.classList.remove("looking"); updateEye(); }
}
function updateEye() { $("eye-text").textContent = S.vision ? t().eyeOn : t().eyeOff; }

let asking = false;
async function askPriest(text) {
  if (asking) return; asking = true;
  try {
    const r = await turn("ask", { heard: text });
    if (r.say) await speak(r.say);
    if (r.done) emit("done");
  } finally { asking = false; }
}

/* ---------- Ayyagaru chants ---------- */
async function playChant(step, token) {
  const version = S.pooja.chants?.[step.id];
  if (!version) return S.playerReady ? playSegment(step, token) : chantInterlude(token);
  const el = S.chantEl;
  let failed = false;
  el.onerror = () => { failed = true; };
  el.muted = false;
  el.src = `/api/chant/${encodeURIComponent(S.pooja.id)}/${encodeURIComponent(step.id)}?v=${version}`;
  try { await el.play(); } catch { return chantInterlude(token); }
  S.chanting = true;
  let lastLive = Date.now();
  try {
    for (;;) {
      const ev = await waitFor(["skip", "abort", "repeat"], 400);
      guard(token);
      if (ev === "skip" || el.ended || failed) break;
      if (S.paused) { el.pause(); await whileUnpaused(token); el.play().catch(() => {}); }
      if (step.live_check && S.vision && Date.now() - lastLive > 15000 && !asking) {
        lastLive = Date.now();
        turn("live").then(async (r) => {
          if (token !== S.token || !r.say) return;
          el.pause(); await speak(r.say).catch(() => {});
          if (!S.paused && token === S.token && !el.ended) el.play().catch(() => {});
        });
      }
    }
  } finally { S.chanting = false; el.pause(); }
}

async function playSegment(step, token) {
  const [start, end] = step.segment;
  const p = await S.playerReady;
  p.unMute(); p.setVolume(100); p.seekTo(start, true); p.playVideo();
  S.playing = true;
  const watchdog = setTimeout(() => {           // autoplay blocked (iOS): ask for a tap
    if (p.getPlayerState() !== YT.PlayerState.PLAYING && !S.paused) $("tap-play").hidden = false;
  }, 2500);
  let lastLive = Date.now();
  try {
    for (;;) {
      const ev = await waitFor(["skip", "abort", "repeat"], 400);
      guard(token);
      if (ev === "skip") break;
      if (S.paused) { p.pauseVideo(); await whileUnpaused(token); p.playVideo(); }
      if ((p.getCurrentTime?.() || 0) >= end - 0.25 || p.getPlayerState() === YT.PlayerState.ENDED) break;
      if (step.live_check && S.vision && Date.now() - lastLive > 15000 && !asking) {
        lastLive = Date.now();
        turn("live").then(async (r) => {
          if (token !== S.token || !r.say) return;
          if (r.urgent) p.pauseVideo(); else p.setVolume(25);
          await speak(r.say).catch(() => {});
          p.setVolume(100); if (r.urgent && !S.paused && token === S.token) p.playVideo();
        });
      }
    }
  } finally {
    clearTimeout(watchdog); $("tap-play").hidden = true;
    S.playing = false; p.pauseVideo(); document.querySelector(".remote").classList.remove("playing");
  }
}

// Not recorded yet and no video fallback: no fake chanting, just a short swell of mangala vadyam while they do the step.
async function chantInterlude(token) {
  S.interlude = true;
  try { await waitFor(["skip", "abort"], 10000); guard(token); await whileUnpaused(token); }
  finally { S.interlude = false; }
}

/* ---------- confirming a step ---------- */
async function confirmStep(step, token) {
  if (!S.vision) {
    const finished = waitFor(["done", "skip", "abort"]);
    try {
      if (!confirmStep.explained) { confirmStep.explained = true; await speak(t().sayDone, token); }
      await finished;
    } finally { finished.cancel(); }
    guard(token); return;
  }
  for (let attempt = 0; attempt < 3; attempt++) {
    await whileUnpaused(token);
    const r = await turn("check");
    guard(token);
    if (r.available === false) return confirmStep(step, token);   // vision went away: fall back
    if (r.say) await speak(r.say, token);
    if (r.done) return;
    const ev = await waitFor(["done", "skip", "question", "abort"], 12000);
    guard(token);
    if (ev === "done" || ev === "skip") return;
    if (ev === "question" && await waitFor(["done", "skip", "abort"], 15000) !== "timeout") { guard(token); return; }
  }
  await speak(t().moveOn, token);
}

/* ---------- the pooja loop ---------- */
async function runStep(step, token) {
  const n = S.pooja.steps.length;
  $("step-label").textContent = `${t().step(S.index + 1, n)} · ${S.lang === "te" ? step.title : step.title_en}`;
  $("progress-bar").style.width = `${(S.index / n) * 100}%`;
  S.festive = /harati|closing/.test(step.id);
  await whileUnpaused(token);
  await speak(S.lang === "te" ? step.say : step.say_en, token);
  if (step.segment) { await whileUnpaused(token); await playChant(step, token); }
  guard(token);
  if (step.action === "do") await confirmStep(step, token);
}

async function runPooja() {
  while (S.index < S.pooja.steps.length && !S.ended) {
    const token = ++S.token;
    try {
      await runStep(S.pooja.steps[S.index], token);
      S.index++;
    } catch (e) {
      if (!(e instanceof Interrupted)) { console.error(e); S.index++; }
      // Interrupted by repeat: S.index unchanged, loop replays the step.
    }
  }
  if (!S.ended) { $("progress-bar").style.width = "100%"; await sleep(1500); endCall(true); }
}

/* ---------- controls ---------- */
function doPause() {
  if (S.paused) return; S.paused = true;
  $("pause-label").textContent = t().resume; $("pause-btn").classList.add("off");
  speechSynthesis?.cancel(); S.voiceEl?.pause(); S.chantEl?.pause(); S.player?.pauseVideo?.();
  setCaption(t().paused);
}
function doResume() {
  if (!S.paused) return; S.paused = false;
  $("pause-label").textContent = t().pause; $("pause-btn").classList.remove("off");
  setCaption(t().resumed); emit("resume");
}
function doRepeat() {
  S.token++; S.paused = false; $("pause-label").textContent = t().pause; $("pause-btn").classList.remove("off");
  speechSynthesis?.cancel(); S.voiceEl?.pause(); S.chantEl?.pause(); emit("abort"); emit("repeat"); emit("resume");
}

async function startCall() {
  // Everything needing a user gesture happens here, before any await.
  S.ended = false; S.index = Number(params.get("step") || 0); S.history = [];
  startRing();
  if ("speechSynthesis" in window) speechSynthesis.speak(new SpeechSynthesisUtterance(" "));
  // Unlock audio playback on iOS: the element must first play inside this tap.
  S.voiceEl = S.voiceEl || new Audio(); S.voiceEl.muted = true;
  S.voiceEl.src = ttsUrl("నమస్కారం");
  S.voiceEl.play().catch(() => {});
  S.chantEl = S.chantEl || new Audio(); S.chantEl.muted = true;
  S.chantEl.src = "/static/music/mangala_vadyam.mp3"; S.chantEl.play().then(() => S.chantEl.pause()).catch(() => {});
  setupMusic(); setupVoiceMeter(); S.audio?.resume?.(); S.music?.play().catch(() => {});
  S.face?.start();
  show("ringing"); $("ring-status").textContent = t().calling;
  const camera = startCamera();
  S.playerReady?.then((p) => { p.mute(); p.playVideo(); setTimeout(() => { p.pauseVideo(); p.unMute(); }, 1200); });
  await sleep(1500); $("ring-status").textContent = t().ringing;
  await Promise.all([camera, sleep(2500)]);
  if (S.ended) return;
  $("ring-status").textContent = t().connecting;
  S.ring?.stop();
  try { S.wakeLock = await navigator.wakeLock?.request("screen"); } catch {}
  show("call"); updateEye();
  clearInterval(S.musicTimer); S.musicTimer = setInterval(updateMusic, 300);
  S.callStart = Date.now(); clearInterval(S.timer);
  S.timer = setInterval(() => {
    const s = Math.floor((Date.now() - S.callStart) / 1000);
    $("call-timer").textContent = `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  }, 1000);
  if (!S.vision) toast(t().noVision, 5000);
  setupRecognition();
  runPooja();
}

function endCall(completed) {
  S.ended = true; S.token++; emit("abort");
  S.ring?.stop(); clearInterval(S.timer); clearInterval(S.musicTimer);
  if (S.musicGain) S.musicGain.gain.setTargetAtTime(0, S.audio.currentTime, 0.3);
  setTimeout(() => S.music?.pause(), 1500);
  speechSynthesis?.cancel(); S.voiceEl?.pause(); S.chantEl?.pause(); pauseListening(); S.recognition = null;
  try { S.player?.pauseVideo(); } catch {}
  S.face?.setLevel(0);
  S.stream?.getTracks().forEach((tr) => tr.stop()); S.stream = null;
  S.wakeLock?.release?.(); S.wakeLock = null;
  $("ended-title").textContent = completed ? t().endedTitle : t().endedEarly;
  show("ended");
}

/* ---------- wiring ---------- */
$("call-btn").addEventListener("click", startCall);
$("music-btn").addEventListener("click", () => {
  const panel = $("music-panel"); panel.hidden = !panel.hidden; $("music-btn").setAttribute("aria-expanded", !panel.hidden);
});
$("music-vol").addEventListener("input", (e) => {
  S.musicVol = Number(e.target.value) / 100; savePref("musicVol", S.musicVol); updateMusic();
  $("music-btn").textContent = S.musicVol === 0 ? "🔇" : "🎵";
});
$("cancel-btn").addEventListener("click", () => endCall(false));
$("again-btn").addEventListener("click", () => show("home"));
$("end-btn").addEventListener("click", () => { if (confirm(t().endConfirm)) endCall(false); });
$("next-btn").addEventListener("click", () => { emit("done"); emit("skip"); });
$("repeat-btn").addEventListener("click", doRepeat);
$("tap-play").addEventListener("click", () => { S.player?.playVideo(); $("tap-play").hidden = true; });
$("pause-btn").addEventListener("click", () => (S.paused ? doResume() : doPause()));
$("mic-btn").addEventListener("click", () => {
  S.micOn = !S.micOn; $("mic-btn").classList.toggle("off", !S.micOn);
  S.micOn ? resumeListening() : pauseListening();
});
$("flip-btn").addEventListener("click", () => { S.facing = S.facing === "user" ? "environment" : "user"; startCamera(); });
document.addEventListener("visibilitychange", async () => {
  if (document.visibilityState === "visible" && S.timer && !S.ended && !S.wakeLock) {
    try { S.wakeLock = await navigator.wakeLock?.request("screen"); } catch {}
  }
});

boot().catch((e) => { console.error(e); toast("Could not load the pooja. Is the server running?", 8000); });
