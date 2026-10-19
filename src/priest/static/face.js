/* Talking face from a single photo: the jaw and lips move with the voice, the eyes
 * blink, and the head sways gently. Runs on the phone in real time (2D canvas), so it
 * animates any line, including Ayyagaru's live replies.
 *
 * Face points come from <image>.face.json when present, otherwise MediaPipe's face
 * landmarker finds them in the browser, so the photo can be swapped freely.
 */
const MEDIAPIPE = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.21";
const FACE_MODEL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";

// MediaPipe face-mesh indices.
const P = { upperInner: 13, lowerInner: 14, upperOuter: 0, lowerOuter: 17, left: 61, right: 291, chin: 152,
  lEyeTop: 159, lEyeBottom: 145, lEyeOuter: 33, lEyeInner: 133,
  rEyeTop: 386, rEyeBottom: 374, rEyeInner: 362, rEyeOuter: 263 };

export async function detectFacePoints(img) {
  const vision = await import(`${MEDIAPIPE}/vision_bundle.mjs`);
  const files = await vision.FilesetResolver.forVisionTasks(`${MEDIAPIPE}/wasm`);
  const landmarker = await vision.FaceLandmarker.createFromOptions(files, {
    baseOptions: { modelAssetPath: FACE_MODEL }, runningMode: "IMAGE", numFaces: 1 });
  const result = landmarker.detect(img);
  landmarker.close();
  const mesh = result.faceLandmarks?.[0];
  if (!mesh) throw new Error("no face found in the photo");
  return Object.fromEntries(Object.entries(P).map(([name, i]) => [name, [mesh[i].x, mesh[i].y]]));
}

// Inverse-mapped warp: skin below the lips slides down (most at the lips, fading towards the
// cheeks and below the chin) and the gap that opens between the lips is drawn as the mouth.
const WARP_FS = `
precision highp float;
uniform sampler2D img; uniform vec2 size; uniform float openPx;
uniform vec2 mouth; uniform float halfW; uniform float depth;
varying vec2 vUv;
float lipBell(float x) { return 1.0 - smoothstep(0.5, 1.0, abs(x - mouth.x) / halfW); }
float jawBell(float x) { return 1.0 - smoothstep(0.3, 1.0, abs(x - mouth.x) / (halfW * 2.3)); }
float disp(vec2 s) {
  float t = clamp((s.y - mouth.y) / depth, 0.0, 1.0);
  float wy = 1.0 - smoothstep(0.4, 1.0, t);
  float wx = mix(lipBell(s.x), jawBell(s.x), smoothstep(0.0, 0.35, t));
  return openPx * wx * wy;
}
void main() {
  vec2 p = vUv * size;
  vec4 base = texture2D(img, vUv);
  if (p.y <= mouth.y || openPx < 0.3) { gl_FragColor = base; return; }
  float gap = openPx * lipBell(p.x);
  float dy = p.y - mouth.y;
  vec2 s = p;
  for (int i = 0; i < 5; i++) { s.y = p.y - disp(vec2(p.x, s.y)); }
  s.y = max(s.y, mouth.y + 0.5);
  vec4 skin = texture2D(img, s / size);
  float f = clamp(dy / max(gap, 0.001), 0.0, 1.0);
  vec3 inside = mix(vec3(0.20, 0.07, 0.06), vec3(0.07, 0.02, 0.02), f);
  float teeth = (1.0 - smoothstep(0.1, 0.3, f)) * smoothstep(0.35, 0.8, gap / (halfW * 0.35))
              * (1.0 - smoothstep(0.35, 0.75, abs(p.x - mouth.x) / halfW));
  inside = mix(inside, vec3(0.80, 0.74, 0.66), teeth * 0.55);
  float edge = smoothstep(gap - 0.8, gap + 0.8, dy);   // anti-aliased lower-lip edge
  float topEdge = smoothstep(0.0, 1.2, dy);            // anti-aliased upper-lip edge
  gl_FragColor = vec4(mix(mix(base.rgb, inside, topEdge), skin.rgb, edge), 1.0);
}`;
const WARP_VS = `attribute vec2 pos; varying vec2 vUv;
void main() { vUv = vec2(pos.x * 0.5 + 0.5, 0.5 - pos.y * 0.5); gl_Position = vec4(pos, 0.0, 1.0); }`;

function createWarp(img) {
  const c = document.createElement("canvas");
  c.width = img.naturalWidth; c.height = img.naturalHeight;
  const gl = c.getContext("webgl", { preserveDrawingBuffer: true, premultipliedAlpha: false });
  if (!gl) return null;
  const shader = (type, src) => {
    const sh = gl.createShader(type); gl.shaderSource(sh, src); gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(sh));
    return sh;
  };
  const prog = gl.createProgram();
  gl.attachShader(prog, shader(gl.VERTEX_SHADER, WARP_VS));
  gl.attachShader(prog, shader(gl.FRAGMENT_SHADER, WARP_FS));
  gl.linkProgram(prog); gl.useProgram(prog);
  gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
  const loc = gl.getAttribLocation(prog, "pos");
  gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
  gl.bindTexture(gl.TEXTURE_2D, gl.createTexture());
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, img);
  gl.viewport(0, 0, c.width, c.height);
  const u = (name) => gl.getUniformLocation(prog, name);
  gl.uniform2f(u("size"), c.width, c.height);
  return {
    canvas: c,
    configure(m) {
      gl.uniform2f(u("mouth"), m.cx, m.lipY); gl.uniform1f(u("halfW"), m.mouthW / 2); gl.uniform1f(u("depth"), m.depth);
    },
    render(openPx) { gl.uniform1f(u("openPx"), openPx); gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4); },
  };
}

async function loadImage(src) {
  const img = new Image(); img.crossOrigin = "anonymous"; img.src = src;
  await img.decode(); return img;
}

function featheredPatch(img, x, y, w, h, { sides = 0.25, bottom = 0.35, top = 0 } = {}) {
  const c = document.createElement("canvas"); c.width = Math.ceil(w); c.height = Math.ceil(h);
  const g = c.getContext("2d");
  g.drawImage(img, x, y, w, h, 0, 0, w, h);
  g.globalCompositeOperation = "destination-in";
  const horiz = g.createLinearGradient(0, 0, w, 0);
  horiz.addColorStop(0, "rgba(0,0,0,0)"); horiz.addColorStop(sides, "#000");
  horiz.addColorStop(1 - sides, "#000"); horiz.addColorStop(1, "rgba(0,0,0,0)");
  g.fillStyle = horiz; g.fillRect(0, 0, w, h);
  const vert = g.createLinearGradient(0, 0, 0, h);
  vert.addColorStop(0, top ? "rgba(0,0,0,0)" : "#000"); vert.addColorStop(Math.max(top, 0.001), "#000");
  vert.addColorStop(1 - bottom, "#000"); vert.addColorStop(1, "rgba(0,0,0,0)");
  g.fillStyle = vert; g.fillRect(0, 0, w, h);
  return c;
}

export class TalkingFace {
  constructor(canvas) {
    this.canvas = canvas; this.ctx = canvas.getContext("2d");
    this.level = 0; this.open = 0; this.blinkUntil = 0; this.nextBlink = 0; this.running = false;
  }

  async load(src) {
    const img = await loadImage(src);
    let pts = null;
    try { const r = await fetch(`${src}.face.json`); if (r.ok) pts = await r.json(); } catch {}
    if (!pts) pts = await detectFacePoints(img);
    this.setup(img, pts);
    return this;
  }

  setup(img, pts) {
    const W = img.naturalWidth, H = img.naturalHeight;
    this.img = img; this.canvas.width = W; this.canvas.height = H;
    const px = (name) => [pts[name][0] * W, pts[name][1] * H];
    const [lx] = px("left"), [rx] = px("right");
    const lipY = (px("upperInner")[1] + px("lowerInner")[1]) / 2;
    const chinY = px("chin")[1];
    const mouthW = rx - lx, cx = (lx + rx) / 2;
    const jaw = { x: lx - mouthW * 0.6, y: lipY, w: mouthW * 2.2, h: (chinY - lipY) * 1.45 };
    this.m = { cx, lipY, mouthW, maxOpen: mouthW * 0.2, jaw, depth: (chinY - lipY) * 1.5,
      jawPatch: featheredPatch(img, jaw.x, jaw.y, jaw.w, jaw.h, { sides: 0.28, bottom: 0.38 }) };
    try { this.warp = createWarp(img); this.warp?.configure(this.m); } catch (e) { console.warn("face warp", e); this.warp = null; }
    this.eyes = [["lEyeOuter", "lEyeInner", "lEyeTop", "lEyeBottom"], ["rEyeInner", "rEyeOuter", "rEyeTop", "rEyeBottom"]]
      .map(([a, b, top, bottom]) => {
        const x0 = Math.min(px(a)[0], px(b)[0]), x1 = Math.max(px(a)[0], px(b)[0]);
        const yTop = px(top)[1], yBottom = px(bottom)[1], eyeH = Math.max(4, yBottom - yTop);
        const pad = (x1 - x0) * 0.18, lidH = eyeH * 1.6;
        const box = { x: x0 - pad, y: yTop - lidH, w: x1 - x0 + pad * 2, h: lidH };
        return { box, eyeH, lid: featheredPatch(img, box.x, box.y, box.w, box.h, { sides: 0.22, bottom: 0.05, top: 0.3 }) };
      });
    this.draw(0);
  }

  /** Voice loudness 0..1 from an analyser; drives the jaw. */
  setLevel(level) { this.level = level; }

  start() {
    if (this.running) return; this.running = true;
    const tick = (t) => { if (!this.running) return; this.draw(t); requestAnimationFrame(tick); };
    requestAnimationFrame(tick);
  }
  stop() { this.running = false; }

  draw(t) {
    const { ctx, img, m } = this;
    if (!img) return;
    const target = Math.min(1, Math.max(0, (this.level - 0.05) * 2.4));
    this.open += (target - this.open) * (target > this.open ? 0.55 : 0.3);
    const open = this.open * m.maxOpen;

    // Gentle head sway and breathing; a small nod while speaking.
    const s = t / 1000, sway = Math.sin(s * 0.7) * 0.35 + Math.sin(s * 0.23) * 0.25;
    this.canvas.style.transform = `translateY(${(Math.sin(s * 1.6) * 0.6 + this.open * 1.6).toFixed(2)}px) ` +
      `rotate(${(sway * 0.35 + this.open * 0.25).toFixed(3)}deg) scale(${(1.004 + Math.sin(s * 1.6) * 0.003).toFixed(4)})`;

    if (this.warp) {
      this.warp.render(open);
      ctx.drawImage(this.warp.canvas, 0, 0);
    } else ctx.drawImage(img, 0, 0);
    if (!this.warp && open > 0.5) {  // 2D fallback without WebGL
      // Mouth opening: dark interior with a hint of upper teeth, then the jaw lowered over it.
      const rxM = m.mouthW * (0.4 - this.open * 0.05), ryM = open * 0.6 + 1;
      ctx.save();
      ctx.beginPath(); ctx.ellipse(m.cx, m.lipY + open * 0.45, rxM, ryM, 0, 0, Math.PI * 2); ctx.clip();
      const inside = ctx.createLinearGradient(0, m.lipY, 0, m.lipY + open);
      inside.addColorStop(0, "#2b0d0b"); inside.addColorStop(1, "#140504");
      ctx.fillStyle = inside; ctx.fillRect(m.cx - rxM, m.lipY - ryM, rxM * 2, ryM * 3);
      if (this.open > 0.25) {
        ctx.fillStyle = "rgba(232,224,210,0.85)";
        ctx.fillRect(m.cx - rxM * 0.55, m.lipY - 1, rxM * 1.1, Math.min(open * 0.22, m.mouthW * 0.05));
      }
      ctx.restore();
      const j = m.jaw;
      ctx.drawImage(m.jawPatch, j.x, j.y + open, j.w, j.h + open * 0.25);
    }

    // Blink every few seconds: slide the eyelid skin down over the eye.
    if (t > this.nextBlink) { this.blinkUntil = t + 150; this.nextBlink = t + 2500 + Math.random() * 3500; }
    if (t < this.blinkUntil) {
      for (const e of this.eyes) {
        const b = e.box;
        ctx.drawImage(e.lid, b.x, b.y + e.eyeH * 0.9, b.w, b.h);
      }
    }
  }
}
