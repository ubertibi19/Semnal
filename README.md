# Semnal

News site for semnalnews.ro, hosted on Cloudflare Pages.

- `index.html` – the site (RO/EN, region feed, trending, alerts).
- `news.json` – the latest stories. An automatic collector rewrites this file every hour and pushes it here; Cloudflare Pages redeploys on each push.
- `_headers` – stops browsers caching `news.json`.
