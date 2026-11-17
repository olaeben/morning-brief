#!/usr/bin/env python3
"""Rebuild feed.xml from episodes/*.json and prune episodes older than KEEP_DAYS."""
import datetime as dt
import json
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent


def main():
    cfg = json.loads((ROOT / "config.json").read_text())
    tz = ZoneInfo(cfg.get("timezone", "Europe/London"))
    base = cfg["base_url"].rstrip("/")
    keep_days = cfg.get("keep_days", 14)
    today = dt.datetime.now(tz).date()

    episodes = []
    for meta_path in sorted((ROOT / "episodes").glob("*.json"), reverse=True):
        meta = json.loads(meta_path.read_text())
        mp3 = meta_path.with_suffix(".mp3")
        age = (today - dt.date.fromisoformat(meta["date"])).days
        if age > keep_days or not mp3.exists():
            meta_path.unlink(missing_ok=True)
            mp3.unlink(missing_ok=True)
            print(f"pruned {meta['date']}")
            continue
        episodes.append(meta)

    items = []
    for e in episodes:
        pub = dt.datetime.combine(dt.date.fromisoformat(e["date"]), dt.time(7, 0), tz)
        m, s = divmod(e["duration_seconds"], 60)
        notes = e["summary"]
        if e.get("sources"):
            notes += "\n\nSources:\n" + "\n".join(e["sources"])
        items.append(f"""    <item>
      <title>{escape(e['date'] + ' — ' + e['title'])}</title>
      <description>{escape(notes)}</description>
      <enclosure url="{base}/episodes/{e['date']}.mp3" length="{e['bytes']}" type="audio/mpeg"/>
      <guid isPermaLink="false">morning-brief-{e['date']}</guid>
      <pubDate>{format_datetime(pub)}</pubDate>
      <itunes:duration>{m}:{s:02d}</itunes:duration>
      <itunes:explicit>false</itunes:explicit>
    </item>""")

    feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{escape(cfg['title'])}</title>
    <link>{base}/</link>
    <atom:link href="{base}/feed.xml" rel="self" type="application/rss+xml"/>
    <description>{escape(cfg['description'])}</description>
    <language>en-gb</language>
    <itunes:author>{escape(cfg['author'])}</itunes:author>
    <itunes:image href="{base}/cover.jpg"/>
    <itunes:category text="News"><itunes:category text="Daily News"/></itunes:category>
    <itunes:explicit>false</itunes:explicit>
    <itunes:block>Yes</itunes:block>
    <lastBuildDate>{format_datetime(dt.datetime.now(tz))}</lastBuildDate>
{chr(10).join(items)}
  </channel>
</rss>
"""
    (ROOT / "feed.xml").write_text(feed)
    print(f"feed.xml: {len(episodes)} episode(s)")


if __name__ == "__main__":
    main()
