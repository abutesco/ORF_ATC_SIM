import cors from "cors";
import express from "express";
import multer from "multer";

const app = express();
const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 12 * 1024 * 1024 } });
const port = process.env.PORT || 10000;
const openAiBaseUrl = process.env.OPENAI_API_BASE || "https://api.openai.com/v1";
const frontendOrigin = process.env.FRONTEND_ORIGIN || "*";

app.use(cors({
  origin: frontendOrigin === "*" ? true : frontendOrigin.split(",").map((origin) => origin.trim()).filter(Boolean)
}));
app.use(express.json({ limit: "1mb" }));

function openAiKey() {
  return String(process.env.OPENAI_API_KEY || "").trim();
}

function requireOpenAiKey(res) {
  const key = openAiKey();
  if (!key) {
    res.status(500).json({
      ok: false,
      error: "OPENAI_API_KEY is not configured on the backend."
    });
    return "";
  }
  return key;
}

async function readOpenAiError(response) {
  const text = await response.text().catch(() => "");
  if (!text) return `OpenAI API error ${response.status}`;
  try {
    const parsed = JSON.parse(text);
    return parsed?.error?.message || text;
  } catch {
    return text;
  }
}

app.get("/health", (_req, res) => {
  res.json({ ok: true, openai_configured: Boolean(openAiKey()) });
});

app.post("/api/openai-key", (_req, res) => {
  res.status(403).json({
    ok: false,
    error: "For hosted deploys, set OPENAI_API_KEY in Render environment variables instead of sending it from the browser."
  });
});

app.post("/api/transcribe", upload.single("audio"), async (req, res) => {
  try {
    const key = requireOpenAiKey(res);
    if (!key) return;
    if (!req.file) {
      res.status(400).json({ ok: false, error: "Audio file is required." });
      return;
    }

    const form = new FormData();
    form.append("model", process.env.OPENAI_TRANSCRIBE_MODEL || "gpt-4o-mini-transcribe");
    form.append("language", "en");
    form.append("response_format", "json");
    form.append("prompt", [
      "Norfolk Approach ATC simulator command.",
      "Expect aircraft callsigns, fixes, airports, headings, altitudes, speeds, ILS and RNAV clearances.",
      "Preserve aviation identifiers such as AAL123, JBU1712, KORF, NGU, LFI, PHF, KOHLS, OUTLA, NUTIY."
    ].join(" "));
    form.append(
      "file",
      new Blob([req.file.buffer], { type: req.file.mimetype || "audio/webm" }),
      req.file.originalname || "controller.webm"
    );

    const response = await fetch(`${openAiBaseUrl}/audio/transcriptions`, {
      method: "POST",
      headers: { Authorization: `Bearer ${key}` },
      body: form
    });

    if (!response.ok) {
      res.status(response.status).json({ ok: false, error: await readOpenAiError(response) });
      return;
    }

    const result = await response.json();
    res.json({ ok: true, text: result.text || "" });
  } catch (error) {
    res.status(500).json({ ok: false, error: error.message || String(error) });
  }
});

app.post("/api/tts", async (req, res) => {
  try {
    const key = requireOpenAiKey(res);
    if (!key) return;
    const text = String(req.body?.text || "").trim();
    if (!text) {
      res.status(400).json({ ok: false, error: "Text is required." });
      return;
    }

    const response = await fetch(`${openAiBaseUrl}/audio/speech`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${key}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        model: process.env.OPENAI_TTS_MODEL || "gpt-4o-mini-tts",
        voice: req.body?.voice || "alloy",
        input: text,
        instructions: "Read like a calm aviation pilot on VHF radio. Keep the delivery natural, brief, and professional.",
        response_format: "mp3"
      })
    });

    if (!response.ok) {
      res.status(response.status).json({ ok: false, error: await readOpenAiError(response) });
      return;
    }

    const audio = Buffer.from(await response.arrayBuffer());
    res.setHeader("Content-Type", response.headers.get("content-type") || "audio/mpeg");
    res.send(audio);
  } catch (error) {
    res.status(500).json({ ok: false, error: error.message || String(error) });
  }
});

app.listen(port, () => {
  console.log(`ORF ATC sim API listening on ${port}`);
});
