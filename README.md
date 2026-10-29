# Semnal

News site for semnalnews.ro, hosted on Cloudflare Pages.

- `index.html` – the site (RO/EN, region feed, trending, alerts).
- `news.json` – the latest stories. Rewritten every hour by the GitHub Action in `.github/workflows/collect.yml`; Cloudflare Pages redeploys on each push.
- `scripts/collect.py` – the collector: reads the outlets' RSS feeds, groups headlines about the same event, sorts them by topic and region with keyword rules, and drops stories older than 4 days. Standard library only. Edit the `FEEDS` list to add or remove outlets.
- `_headers` – stops browsers caching `news.json`.

To run it by hand: GitHub → Actions → "Collect news" → Run workflow.
