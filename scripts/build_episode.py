#!/usr/bin/env python3
"""Turn a two-host script (JSON) into an MP3 using Google Cloud Text-to-Speech.

Input JSON (default: scripts/today.json):
{
  "date": "2026-11-17",                # optional, defaults to today (Europe/London)
  "title": "Markets wobble, ...",
  "summary": "One-paragraph show notes",
  "sources": ["https://...", ...],     # optional
  "lines": [{"speaker": "A", "text": "..."}, {"speaker": "B", "text": "..."}]
}

Output: episodes/<date>.mp3 and episodes/<date>.json (metadata used by update_feed.py).

Auth: GOOGLE_TTS_API_KEY (preferred), or GOOGLE_APPLICATION_CREDENTIALS (path) / GOOGLE_APPLICATION_CREDENTIALS_JSON (raw JSON).
Voices: VOICE_A / VOICE_B env vars override config.json.
"""
import argparse
import datetime as dt
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_RATE = 24000
MAX_BYTES = 4000  # Google TTS hard limit is 5000 bytes per request
PAUSE_SAME = 0.25  # seconds between lines by the same speaker
PAUSE_SWITCH = 0.45  # seconds when the speaker changes


def load_config():
    return json.loads((ROOT / "config.json").read_text())


def ensure_credentials():
    raw = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if raw and not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as f:
            f.write(raw)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = path


def chunk_text(text):
    """Split text into pieces under MAX_BYTES, breaking on sentence boundaries."""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text.encode()) <= MAX_BYTES:
        return [text]
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks, cur = [], ""
    for s in sentences:
        candidate = f"{cur} {s}".strip()
        if len(candidate.encode()) > MAX_BYTES and cur:
            chunks.append(cur)
            cur = s
        else:
            cur = candidate
    if cur:
        chunks.append(cur)
    return chunks


def synth(client, tts, text, voice_name):
    lang = "-".join(voice_name.split("-")[:2])
    resp = client.synthesize_speech(
        input=tts.SynthesisInput(text=text),
        voice=tts.VoiceSelectionParams(language_code=lang, name=voice_name),
        audio_config=tts.AudioConfig(
            audio_encoding=tts.AudioEncoding.LINEAR16, sample_rate_hertz=SAMPLE_RATE
        ),
    )
    with wave.open(io.BytesIO(resp.audio_content)) as w:
        assert w.getframerate() == SAMPLE_RATE and w.getnchannels() == 1
        return w.readframes(w.getnframes())


def silence(seconds):
    return b"\x00\x00" * int(SAMPLE_RATE * seconds)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script", nargs="?", default=str(ROOT / "scripts" / "today.json"))
    ap.add_argument("--list-voices", action="store_true", help="list en-GB voices and exit")
    args = ap.parse_args()

    from google.cloud import texttospeech as tts

    api_key = os.environ.get("GOOGLE_TTS_API_KEY")
    if api_key:
        client = tts.TextToSpeechClient(client_options={"api_key": api_key})
    else:
        ensure_credentials()
        client = tts.TextToSpeechClient()
    cfg = load_config()

    if args.list_voices:
        for v in client.list_voices(language_code="en-GB").voices:
            print(v.name, tts.SsmlVoiceGender(v.ssml_gender).name)
        return

    data = json.loads(Path(args.script).read_text())
    tz = ZoneInfo(cfg.get("timezone", "Europe/London"))
    date = data.get("date") or dt.datetime.now(tz).date().isoformat()
    voices = {
        "A": os.environ.get("VOICE_A", cfg["hosts"]["A"]["voice"]),
        "B": os.environ.get("VOICE_B", cfg["hosts"]["B"]["voice"]),
    }

    pcm = bytearray()
    prev = None
    chars = 0
    for i, line in enumerate(data["lines"]):
        spk = line["speaker"].strip().upper()[:1]
        if spk not in voices:
            sys.exit(f"line {i}: unknown speaker {line['speaker']!r} (use A or B)")
        if prev is not None:
            pcm += silence(PAUSE_SWITCH if spk != prev else PAUSE_SAME)
        for piece in chunk_text(line["text"]):
            pcm += synth(client, tts, piece, voices[spk])
            chars += len(piece)
        prev = spk
        print(f"  [{i + 1}/{len(data['lines'])}] {spk}", file=sys.stderr)

    out_dir = ROOT / "episodes"
    out_dir.mkdir(exist_ok=True)
    mp3 = out_dir / f"{date}.mp3"
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        with wave.open(tmp, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes(bytes(pcm))
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", tmp.name,
         "-codec:a", "libmp3lame", "-b:a", "64k", "-ac", "1",
         "-metadata", f"title={data['title']}",
         "-metadata", f"artist={cfg['title']}", str(mp3)],
        check=True,
    )
    os.unlink(tmp.name)

    duration = len(pcm) // 2 / SAMPLE_RATE
    meta = {
        "date": date,
        "title": data["title"],
        "summary": data.get("summary", ""),
        "sources": data.get("sources", []),
        "duration_seconds": round(duration),
        "bytes": mp3.stat().st_size,
        "tts_characters": chars,
    }
    (out_dir / f"{date}.json").write_text(json.dumps(meta, indent=2))
    print(f"wrote {mp3} ({duration / 60:.1f} min, {chars} chars)")


if __name__ == "__main__":
    main()
