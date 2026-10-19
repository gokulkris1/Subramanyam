# Telugu-Subramanyam MCP Server

A local, citation-first Hindu ritual **reference assistant for Telugu and
Andhra/Telangana traditions**. MCP supplies tools, resources and prompts to an
agent; it is not itself a trained model or an initiated priest.

## Current coverage (important)

- Four existing Telugu **unreviewed drafts**: Ganapati nityapuja, Sudarshana
  homa, upanayanam and Varalakshmi vratam.
- **No verified scripture passages or chant recordings are bundled.** Source
  names in drafts are not verified citations.
- [data/source_manifest.json](data/source_manifest.json) is an unverified
  **discovery wishlist** containing catalogue/search links and proposed editions,
  not a downloaded library. URLs, titles and availability need verification.
- No exhaustive Hindu corpus, all-Indian-language translation, panchanga
  calculation, pronunciation teaching or Vedic svara verification is provided.
- Ritual procedures vary by sampradaya, sutra/shakha, region and family custom.
  Qualified lineage-specific priests must review procedures and chanting.

The server reports these limits through `knowledge_status`. Imported source
review and rights status are **curator declarations**, not independent certification.
Do not treat ritual descriptions as guarantees of health, wealth or other outcomes.

## Install and connect in VS Code (macOS/Linux)

Python 3.11+ is required.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
```

[.vscode/mcp.json](.vscode/mcp.json) launches the installed stdio server and uses
`data/library.sqlite3` as the persistent library. In VS Code run **MCP: List
Servers**, choose **telugu-subramanyam**, and start/approve it. Enable its tools
in your agent chat. The client owns the subprocess: it starts on demand and
stops when disconnected. No network port, hosted service or API key is required.

For another MCP client, configure the **absolute path** to
`.venv/bin/telugu-mcp-server` as the command. Set `TELUGU_MCP_DATABASE` to an
absolute database path. With no variable, the default is
`~/.subramanyam/library.sqlite3`. Do not run stdio as an HTTP daemon.

Windows users should change the command to the corresponding
`.venv/Scripts/telugu-mcp-server.exe`.

## Import real source editions

Obtain public-domain or appropriately licensed/permissioned editions first.
Free-to-read does not mean permission to redistribute. Check the rights to
modern translations, commentaries, recordings and scans independently.
The server never automatically scrapes the discovery wishlist.

Create a local manifest outside version control pointing at UTF-8 text or
Markdown files you are authorized to use. Example **schema only**, not an
assertion that any particular edition is licensed:

```json
[
  {
    "id": "your_reviewed_paddhati",
    "title": "Actual title of your source",
    "layer": "core_rituals_smarta",
    "tradition": "స్మార్త",
    "region": ["ఆంధ్ర", "తెలంగాణ"],
    "language": "te",
    "edition": "Publisher, editor, year, volume",
    "source_url": "https://example.org/actual-edition",
    "format": "text",
    "local_path": "texts/your-edition.txt",
    "rights_basis": "permission",
    "rights_note": "Document the actual permission and permitted use here",
    "review_status": "unreviewed",
    "reviewer": "",
    "chunk_size": 1800
  }
]
```

```bash
.venv/bin/telugu-corpus-import \
  --manifest /absolute/path/to/your-manifest.json \
  --database "$PWD/data/library.sqlite3"
```

- Required provenance: nonempty title, tradition, language, edition and
  rights note. `rights_basis`: `public_domain`, `permission` or `licensed`.
- `review_status`: `unreviewed` or `reviewed`. Only declare `reviewed` after
  source/OCR/passage validation; a nonempty named `reviewer` is required.
- Relative text paths resolve against the manifest directory.
- Import is transactional: any invalid or missing source rolls back the batch.
  Reimport replaces the same source ID. Changed content invalidates old passage IDs.
- Arbitrary scripture text is supported; ritual-specific section headings are
  not required. Line numbers refer to the imported UTF-8 text, **not PDF pages**.
  Preserve verse/page markers in the text and document them in the edition.
- PDF/HTML/audio imports are deliberately rejected by this path. Extract or
  OCR into UTF-8 text separately, manually verify Telugu/Sanskrit and svara,
  then import. The older `corpus.ingest` helper remains for structured ritual
  documents; its JSONL output is not automatically used by the MCP library.

Keep unredistributable source texts, manifests, private details and databases
out of Git. The local database is ignored. Tools do not accept imports or writes;
imports happen through this trusted local CLI.

## Tools and reusable agent prompts

| Tool | Purpose |
|------|---------|
| `knowledge_status` | Actual imported/reviewed coverage and limitations |
| `list_ceremonies` | Draft IDs, Telugu names and traditions |
| `get_ceremony` | Draft payload and explicit unreviewed warning |
| `ganapati_nityapuja`, `sudarshana_homa`, `upanayanam`, `varalakshmi_vratam` | Compatible original tool names, now with a draft envelope |
| `list_sources` | Imported edition metadata, rights, reviews and hashes |
| `search_scriptures` | Cited passages; defaults to reviewed sources only |
| `get_passage` | Exact text, edition, SHA-256, line numbers and character offsets |

Search uses NFC-normalized, case-folded **literal substrings**; all query terms
must occur in a single passage. Original text and accents are preserved in
responses. Follow `previous_passage_id` / `next_passage_id` with `get_passage`
to read adjoining context or reconstruct a source without omission.
Optional filters: `language`, `tradition`, `source_id`. Use
`reviewed_only=false` explicitly to research unreviewed sources; do not present
them as validated ritual instructions. `limit` is 1–50; follow `next_offset`
for more results. Unknown IDs and invalid inputs produce MCP tool errors.
An empty search result means **no matching evidence**, not a religious conclusion.
This baseline scans passages; it is not large-scale semantic/vector retrieval.

MCP prompts:

- `telugu_pooja_agent(ritual, tradition="", region="")`: initialize separate
  pooja agents against the same shared library.
- `telugu_scripture_study(topic)`: citation-first scripture research.
- Resource: `subramanyam://guidance-policy`.

Example chat instruction after enabling the server:

> Use Telugu-Subramanyam for a Ganapati pooja reference assistant. Check
> knowledge_status first, ask my sampradaya and family custom, search reviewed
> sources, and cite edition/passage/lines. Say when the library lacks evidence.

Prompts instruct agents not to fabricate mantras, svara, personal sankalpa
details or muhurta, and to defer fire/homa practice to qualified priests.
**Prompts are not an enforcement boundary**: the host model remains responsible
for following them, and raw imported passages may describe historical practices.
The server does not translate text or synthesize chanting.

## Live "call Ayyagaru" (అయ్యగారు) pooja (POC: Mahanavami)

This is a phone-browser video call with a priest agent who sits with the family for a
whole pooja. The user taps the green call button; it rings and connects, and
Ayyagaru appears with his talking face. Then, for every step:

1. Ayyagaru says the instruction in Telugu (or English) through the speaker,
   with on-screen captions.
2. Ayyagaru chants that step himself, from a real recording of the person whose face he
   has (see **Recording studio**), with his lips moving to it. Until a step is recorded,
   the call falls back to that step's segment of the source YouTube video (`?fallback=pause`
   gives a short mangala vadyam pause instead). Chanting is never synthesized.
3. Ayyagaru looks through the camera (Claude vision) to confirm the step:
   lamp lit, kumkuma offered, harati being waved, and so on. If needed he gives
   one gentle correction, then moves on. During long steps (16 names, kumkuma
   pooja, harati) he also watches live and speaks up about safety, for example
   flame near cloth.
4. The user can speak at any time: "అయిపోయింది / done", "మళ్ళీ / repeat",
   "ఆగండి / wait", "కొనసాగించండి / continue", or a question such as
   "కర్పూరం లేదు". Buttons do the same.

The first pooja is [mahanavami_mahishasura_mardini.json](src/priest/poojas/mahanavami_mahishasura_mardini.json).
It has 29 steps mapped to timestamps in
[this video](https://youtu.be/Iskh_EQqvwQ): prayers, achamanam, pranayamam,
sankalpam, Ganapati shodashopachara, Mahishasura Mardini dhyanam through the
108-name kumkuma pooja, naivedyam, harati, Durga Suktam and the closing. Its
`status` is `unreviewed_draft`: a qualified priest should review the step
wording. Note that the video's sankalpam names Monday, Ashtami→Navami (19 Oct 2026).

### Run it

```bash
.venv/bin/python -m pip install -e '.[priest]'
export ANTHROPIC_API_KEY=...          # without it the call still works, but Ayyagaru cannot see
export ANTHROPIC_WORKSPACE_ID=wrkspc_...   # only for user-level keys not scoped to a workspace
.venv/bin/telugu-priest --port 8000   # PRIEST_MODEL overrides the default claude-opus-5-5
```

Optional, for the full experience:

```bash
export SARVAM_API_KEY=...       # natural Telugu voices (Sarvam Bulbul); default Ayyagaru = tarun_te_narration
export SARVAM_AYYAGARU_SPEAKER=girish_hi_devotional   # re-point any preset (SPEAKER / MODEL / PACE)
```

- **Voice picker** on the home screen, with a ▶ preview for each voice. Without a
  Sarvam key it falls back to free Microsoft voices (male "Mohan"), then Google.
  Scripted lines are pre-rendered at startup.
- **Ayyagaru's talking face.** The face is animated on the phone from one photo
  ([face.js](src/priest/static/face.js)). A WebGL warp opens the jaw and lips with the
  loudness of his voice, the eyes blink, and the head sways and nods gently. Because it
  runs in real time, live replies talk too. To use a consenting person's photo, put it
  at `src/priest/static/img/ayyagaru.jpg` (call screen, roughly 4:3, face centred) and
  `ayyagaru_portrait.jpg` (home and ringing screens). MediaPipe finds the face points
  automatically. A cached `<photo>.face.json` skips that step. Photos are git-ignored.
- **Mangala vadyam.** A soft temple nadaswaram & thavil loop ducks under speech
  and chant and swells slightly at harati. Use the 🎵 slider to lower or mute it.
  Credit: "Thakil & Nadaswaram during temple Deeparadhana" by Vis M, CC BY 4.0
  (see `static/music/CREDITS.txt`).

Camera and microphone need HTTPS on a phone. The quickest route is a tunnel:

```bash
brew install cloudflared
cloudflared tunnel --url http://localhost:8000   # open the printed https URL on the phone
```

Alternatively pass `--ssl-certfile/--ssl-keyfile` to serve HTTPS on your LAN.
Prop the phone so the camera sees the user and the pooja place, then tap the call button.
URL options: `?lang=en`, `?step=N` (start from step N), `?pooja=<id>`.

Device notes: **Android Chrome** is the best target. It has Telugu speech
recognition and Telugu text-to-speech through the Google TTS engine. iOS Safari
lacks a Telugu voice, so captions carry the instructions; voice commands may be
English-only there, and the buttons always work. Keep the phone on charge, since a
25-minute call with the camera on uses a lot of battery.

### Recording studio

Open `/studio` (set `STUDIO_KEY` on the server; share the key only with the reader). Each
chant step shows the source video's captions as a rough guide and a ▶ reference clip of
that step (studio only), and has record, listen-back and save buttons. Recordings are
converted to level-matched MP3. They're stored outside the repo in `$AYYAGARU_RECORDINGS`
(default `~/.ayyagaru/recordings`). The call uses a recording as soon as it is saved. The
studio also records 1–2 minute voice samples, used to clone his speaking voice so his
instructions and his chanting sound like the same person.

### Add another pooja from a YouTube video

Copy the JSON, set `video.youtube_id` and `duration`, and write one step per
action. Each step has a Telugu and English instruction (`say`/`say_en`), the
`segment` `[start, end]` in seconds where the video priest chants it, `action`
(`listen` or `do`), and for `do` steps a `check` sentence describing what the
camera should see. Captions are the fastest way to find timestamps:
`yt-dlp --skip-download --write-auto-subs --sub-langs te <url>`. The loader
rejects segments outside the video, duplicate step IDs and `do` steps without a check.

## Validation and distribution

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m build
```

Tests include a real installed stdio client handshake, tools, prompts, resources,
explicit errors, Unicode/accents, citation offsets, filters, import rollback
and persistent reimport behavior. Synthetic test texts are **not scriptures**.
CI also tests and builds distributions.

## Expanding responsibly

Next comes verified acquisition and priest review of specific Andhra/Telangana
paddhatis and Vedic editions. Record edition/recension, verse/page references,
rights, OCR quality and reviewer for each source. Audio needs separate recording
rights and qualified chant review. Additional languages require reviewed source
editions/translations and language-specific evaluation, not merely a language
label or a promise that the agent knows every tradition.
