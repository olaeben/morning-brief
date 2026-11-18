#!/usr/bin/env python3
"""Turn a two-host script (JSON) into an MP3 using free Microsoft Edge neural voices (edge-tts).

Input JSON (default: scripts/today.json):
{
  "date": "2026-11-17",                # optional, defaults to today (Europe/London)
  "title": "Markets wobble, ...",
  "summary": "One-paragraph show notes",
  "sources": ["https://...", ...],     # optional
  "lines": [{"speaker": "A", "text": "..."}, {"speaker": "B", "text": "..."}]
}

Output: episodes/<date>.mp3 and episodes/<date>.json (metadata used by update_feed.py).
Voices: VOICE_A / VOICE_B env vars override config.json. No API key needed.
"""
import argparse
import asyncio
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

import edge_tts

# edge-tts pins certifi's CA store; behind a TLS-intercepting proxy, trust the CA bundle
# named by SSL_CERT_FILE / REQUESTS_CA_BUNDLE instead (no-op when neither is set).
_ca = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
if _ca and os.path.isfile(_ca):
    import ssl
    import edge_tts.communicate as _etc
    _etc._SSL_CTX = ssl.create_default_context(cafile=_ca)

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_RATE = 24000
PAUSE_SAME = 0.25  # seconds between lines by the same speaker
PAUSE_SWITCH = 0.45  # seconds when the speaker changes
CONCURRENCY = 4
RETRIES = 3


async def synth_line(sem, text, voice, path):
    async with sem:
        for attempt in range(1, RETRIES + 1):
            try:
                await edge_tts.Communicate(text, voice).save(str(path))
                if path.stat().st_size > 0:
                    return
                raise RuntimeError("empty audio")
            except Exception as e:  # network hiccups, rate limits
                if attempt == RETRIES:
                    raise RuntimeError(f"TTS failed after {RETRIES} tries: {e}") from e
                await asyncio.sleep(2 * attempt)


def to_pcm(mp3_path):
    """Decode an MP3 to raw 16-bit mono PCM at SAMPLE_RATE."""
    return subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", str(mp3_path),
         "-f", "s16le", "-ac", "1", "-ar", str(SAMPLE_RATE), "-"],
        check=True, capture_output=True,
    ).stdout


def silence(seconds):
    return b"\x00\x00" * int(SAMPLE_RATE * seconds)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script", nargs="?", default=str(ROOT / "scripts" / "today.json"))
    args = ap.parse_args()

    cfg = json.loads((ROOT / "config.json").read_text())
    data = json.loads(Path(args.script).read_text())
    tz = ZoneInfo(cfg.get("timezone", "Europe/London"))
    date = data.get("date") or dt.datetime.now(tz).date().isoformat()
    voices = {
        "A": os.environ.get("VOICE_A", cfg["hosts"]["A"]["voice"]),
        "B": os.environ.get("VOICE_B", cfg["hosts"]["B"]["voice"]),
    }

    lines = []
    for i, line in enumerate(data["lines"]):
        spk = line["speaker"].strip().upper()[:1]
        if spk not in voices:
            sys.exit(f"line {i}: unknown speaker {line['speaker']!r} (use A or B)")
        text = " ".join(line["text"].split())
        if text:
            lines.append((spk, text))

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        sem = asyncio.Semaphore(CONCURRENCY)
        paths = [tmp / f"{i:04d}.mp3" for i in range(len(lines))]
        await asyncio.gather(*(
            synth_line(sem, text, voices[spk], p) for (spk, text), p in zip(lines, paths)
        ))
        print(f"  synthesised {len(lines)} lines", file=sys.stderr)

        pcm = bytearray()
        prev = None
        for (spk, _), p in zip(lines, paths):
            if prev is not None:
                pcm += silence(PAUSE_SWITCH if spk != prev else PAUSE_SAME)
            pcm += to_pcm(p)
            prev = spk

        out_dir = ROOT / "episodes"
        out_dir.mkdir(exist_ok=True)
        mp3 = out_dir / f"{date}.mp3"
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error",
             "-f", "s16le", "-ar", str(SAMPLE_RATE), "-ac", "1", "-i", "-",
             "-codec:a", "libmp3lame", "-b:a", "64k",
             "-metadata", f"title={data['title']}",
             "-metadata", f"artist={cfg['title']}", str(mp3)],
            input=bytes(pcm), check=True,
        )

    duration = len(pcm) // 2 / SAMPLE_RATE
    meta = {
        "date": date,
        "title": data["title"],
        "summary": data.get("summary", ""),
        "sources": data.get("sources", []),
        "duration_seconds": round(duration),
        "bytes": mp3.stat().st_size,
    }
    (out_dir / f"{date}.json").write_text(json.dumps(meta, indent=2))
    print(f"wrote {mp3} ({duration / 60:.1f} min)")


if __name__ == "__main__":
    asyncio.run(main())
