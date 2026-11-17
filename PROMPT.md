# Morning Brief: daily production instructions

You produce today's episode of **Morning Brief**, a ~10-minute two-host news podcast for a listener in the UK. Work from the repo root.

## 1. Research (last ~24 hours)
Use web search to find the most important stories from the past 24 hours (since ~07:00 yesterday, UK time) in each segment. Prefer primary or reputable sources (Reuters, AP, BBC, FT, Bloomberg, The Guardian, The Record, BleepingComputer, Krebs, CISA, NCSC, ESPN, BBC Sport, Sky Sports). Cross-check any figure you quote. **Never invent numbers, quotes or events.** If you can't verify something, leave it out.

Segments, in this order, with a rough word budget (~1,500 words in total):
1. **Markets (~400 words)**: overnight Asia, US close, FTSE/European futures, notable movers, rates/FX/oil/gold, and anything scheduled today (earnings, data releases, central-bank speakers).
2. **Geopolitics (~400 words)**: the 2–3 most consequential developments worldwide, with a line on why each matters.
3. **Cybersecurity (~350 words)**: major breaches, actively exploited vulnerabilities (CVE + affected product + whether a patch exists), ransomware, and policy/regulation.
4. **Sport (~300 words)**: Premier League and European football first, then the biggest results and fixtures across other sports (cricket, F1, tennis, NFL/NBA, boxing, athletics) as they come up.

## 2. Write the script
Two hosts in a natural, warm, brisk conversation (not two people reading alternate paragraphs):
- **A = Amara**: lead anchor. She opens and closes the show and drives the transitions.
- **B = James**: analyst. He adds the "why it matters", context and the occasional light aside.

Rules:
- Open: "Good morning, it's <weekday> the <date>, and this is Morning Brief…" plus a 1-sentence teaser of the top story.
- Keep turns short (1–4 sentences). Switch speakers often.
- Write for the ear: spell out symbols ("per cent", "dollars"), round numbers sensibly, no URLs, no markdown, no emoji, no stage directions.
- Say tickers and CVE IDs naturally ("Nvidia", "CVE twenty-twenty-six dash one two three four").
- Close with a one-line "one thing to watch today" and a sign-off.

Save it as `scripts/today.json`:
```json
{
  "date": "YYYY-MM-DD",
  "title": "Short headline of the top 2–3 stories",
  "summary": "2–4 sentence show notes",
  "sources": ["https://...", "..."],
  "lines": [{"speaker": "A", "text": "..."}, {"speaker": "B", "text": "..."}]
}
```
Use today's date in Europe/London.

## 3. Build and publish
```bash
pip install -q -r requirements.txt
python3 scripts/build_episode.py scripts/today.json
python3 scripts/update_feed.py
echo "$(date -u +%FT%TZ) ok $(jq -r .title scripts/today.json)" >> logs/runs.log
git add -A && git commit -m "Episode $(date +%F)" && git push
```
- If `build_episode.py` fails, read the error, fix the cause (bad JSON, an overlong line, a transient API error) and retry once.
- If it still fails, append the error to `logs/runs.log`, commit and push the log, and stop. Do not publish a broken feed.
- Don't commit `scripts/today.json`. It's gitignored.
