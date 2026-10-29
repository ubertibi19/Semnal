#!/usr/bin/env python3
"""Free news collector for semnalnews.ro.

Reads the public RSS feeds of the listed Romanian outlets, groups headlines
about the same event, sorts them by topic/region with keyword rules, and
rewrites news.json. Standard library only; runs in GitHub Actions.
Headlines are shown as published by each outlet, with a link to the article.
"""
import email.utils, hashlib, html, json, re, sys, unicodedata
import urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

NEWS = "news.json"
KEEP_DAYS = 4
MAX_STORIES = 700
UA = "Mozilla/5.0 (compatible; SemnalNewsBot/1.0; +https://semnalnews.ro)"

# Outlet name -> candidate feed URLs (first one that works is used).
FEEDS = {
    "Agerpres": ["https://www.agerpres.ro/rss", "https://agerpres.ro/rss"],
    "Digi24": ["https://www.digi24.ro/rss"],
    "HotNews": ["https://hotnews.ro/feed", "https://www.hotnews.ro/rss"],
    "G4Media": ["https://www.g4media.ro/feed"],
    "Europa Liberă România": ["https://romania.europalibera.org/api/zrqiteuuir", "https://romania.europalibera.org/api/"],
    "Știrile ProTV": ["https://rss.stirileprotv.ro/", "https://stirileprotv.ro/rss"],
    "Libertatea": ["https://www.libertatea.ro/feed", "https://www.libertatea.ro/rss"],
    "Ziarul Financiar": ["https://www.zf.ro/rss", "https://www.zf.ro/rss/"],
    "Recorder": ["https://recorder.ro/feed/"],
    "Context": ["https://context.ro/feed/"],
    "PressOne": ["https://pressone.ro/feed", "https://pressone.ro/rss"],
    "Mediafax": ["https://www.mediafax.ro/rss", "https://www.mediafax.ro/rss/"],
    "News.ro": ["https://www.news.ro/rss", "https://www.news.ro/rss/"],
    "Gândul": ["https://www.gandul.ro/rss", "https://www.gandul.ro/feed"],
    "Capital": ["https://www.capital.ro/feed", "https://www.capital.ro/rss"],
    "B1 TV": ["https://www.b1tv.ro/feed", "https://www.b1tv.ro/rss"],
    "Știri pe surse": ["https://www.stiripesurse.ro/rss", "https://www.stiripesurse.ro/feed"],
    "TVR Info": ["https://tvrinfo.ro/feed/"],
    "Radio Romania International": ["https://www.rri.ro/ro/rss", "https://www.rri.ro/rss"],
}

SKIP = re.compile(r"horoscop|zodi|comunicat de pres|rețet|reteta|loto|pronostic|cota|meniu|vedet|cancan|insula iubirii|bancul|test iq|"
                  r"oferte|reduceri|black friday la|publicitate|advertorial|sponsorizat|live text|liveblog", re.I)

def norm(s):
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))

STOP = set(norm(w) for w in """acest aceasta aceste după despre pentru dintre între care cine unde când cum
ce mai sunt este fost avea va vor fi au din prin spre doar foarte iar sau dar nici chiar toate toți
ultima ora breaking video foto live update oficial anunț anunta anunță spune spun cere după dupa""".split())

def tokens(s):
    return {w for w in re.findall(r"[a-z0-9]+", norm(s)) if len(w) >= 4 and w not in STOP}

def kw(words):
    # Words of 4+ letters match as prefixes (ministr -> ministrul); shorter ones only as whole words.
    parts = [re.escape(norm(w).replace("_", " ")) + ("" if len(w) >= 4 else r"\b") for w in words]
    return re.compile(r"(?<![a-z0-9])(" + "|".join(parts) + r")", re.I)

TOPIC_RULES = [
    ("sport", kw("fotbal superliga fcsb rapid dinamo cfr meci tenis handbal baschet olimpic campionat jucător jucator antrenor gol uefa fifa formula motogp atlet".split())),
    ("politics", kw("guvern premier ministr psd pnl usr aur udmr pot sos parlament senat deputat senator nicușor nicusor grindeanu bolojan simion "
                    "niculescu fritz kelemen georgescu dna diicot ccr curtea_constituț curtea_constitut alegeri electoral partidul partidului partide partidelor moțiun motiun cotroceni preşedint președint presedint "
                    "primar primăr consiliul_general prefect csm parchet procuror rectificar bugetul ponta șoșoacă sosoaca gavrilă ciucu iccj".split())),
    ("security", kw("atac dron armat nato sabotaj militar rachet război razboi soldat apărar aparar spionaj terori explozi bombardament front accident incendi poliți politi polițist crim arestat reținut retinut morți morti victim jandarm isu".split())),
    ("energy", kw("energi gaze gaz petrol curent electric cernavod hidroelectrica nuclear carburant motorin benzin termofic anre transgaz romgaz petrom".split())),
    ("economy", kw("bnr inflaț inflat preț pret prețuri euro leu bursa bvb profit banc credit taxe impozit anaf salari pensi economi pib investi piaț piat afaceri companii".split())),
    ("tech", kw("inteligența_artificială inteligenta_artificiala ai cibernetic hacker google apple microsoft meta tiktok aplicați aplicati startup tehnolog".split())),
    ("culture", kw("film festival muzeu concert teatru carte scriitor actor actriț artist expoziț expozit oscar cultur".split())),
]

BUC = kw("bucurești bucuresti capitala capitalei sectorul_1 sectorul_2 sectorul_3 sectorul_4 sectorul_5 sectorul_6 sector_1 sector_2 sector_3 sector_4 sector_5 sector_6 otopeni henri_coandă henri_coanda metroul metrorex stb ilfov ciucu pmb".split())
EUROPE = [("Ucraina","Ukraine"),("Rusia","Russia"),("Kremlin","Russia"),("Moscova","Russia"),("Putin","Russia"),("Zelenski","Ukraine"),("Kiev","Ukraine"),
          ("Republica Moldova","Moldova"),("Chișinău","Moldova"),("Moldova","Moldova"),("Bulgaria","Bulgaria"),("Ungaria","Hungary"),("Orban","Hungary"),
          ("Serbia","Serbia"),("Vucic","Serbia"),("Polonia","Poland"),("Germania","Germany"),("Berlin","Germany"),("Merz","Germany"),("Franța","France"),
          ("Franta","France"),("Paris","France"),("Macron","France"),("Italia","Italy"),("Meloni","Italy"),("Spania","Spain"),("Madrid","Spain"),
          ("Marea Britanie","UK"),("Londra","UK"),("Regatul Unit","UK"),("Grecia","Greece"),("Turcia","Turkey"),("Austria","Austria"),("Olanda","Netherlands"),
          ("Belgia","Belgium"),("Cehia","Czechia"),("Slovacia","Slovakia"),("Croația","Croatia"),("Albania","Albania"),("Armenia","Armenia"),("Georgia","Georgia"),
          ("Belarus","Belarus"),("Lituania","Lithuania"),("Letonia","Latvia"),("Estonia","Estonia"),("Finlanda","Finland"),("Suedia","Sweden"),("Norvegia","Norway"),
          ("Danemarca","Denmark"),("Elveția","Switzerland"),("Portugalia","Portugal"),("Irlanda","Ireland"),("Transnistria","Moldova"),
          ("Vatican","Vatican"),("Papa Leon","Vatican"),("Comisia Europeană","EU"),("Comisia Europeana","EU"),("Bruxelles","EU"),("Uniunea Europeană","EU"),("UE","EU"),("BCE","EU"),("Europa","Europe")]
WORLD = [("SUA","US"),("Statele Unite","US"),("Washington","US"),("Trump","US"),("Casa Albă","US"),("China","China"),("Beijing","China"),("Israel","Israel"),
         ("Gaza","Gaza"),("Iran","Iran"),("Hormuz","Iran"),("Liban","Lebanon"),("Siria","Syria"),("Irak","Iraq"),("Arabia Saudită","Saudi Arabia"),
         ("Japonia","Japan"),("Coreea de Nord","North Korea"),("Coreea de Sud","South Korea"),("Phenian","North Korea"),("India","India"),("Pakistan","Pakistan"),
         ("Afganistan","Afghanistan"),("Brazilia","Brazil"),("Argentina","Argentina"),("Venezuela","Venezuela"),("Mexic","Mexico"),("Canada","Canada"),
         ("Australia","Australia"),("Africa","Africa"),("Egipt","Egypt"),("Sudan","Sudan"),("Etiopia","Ethiopia"),("Nigeria","Nigeria"),("Taiwan","Taiwan"),
         ("Indonezia","Indonesia"),("Yemen","Yemen"),("ONU","UN")]
PLACE_RO = {"Ukraine":"Ucraina","Russia":"Rusia","Moldova":"Republica Moldova","Bulgaria":"Bulgaria","Hungary":"Ungaria","Serbia":"Serbia","Poland":"Polonia",
            "Germany":"Germania","France":"Franța","Italy":"Italia","Spain":"Spania","UK":"Marea Britanie","Greece":"Grecia","Turkey":"Turcia","Austria":"Austria",
            "Netherlands":"Olanda","Belgium":"Belgia","Czechia":"Cehia","Slovakia":"Slovacia","Croatia":"Croația","Albania":"Albania","Armenia":"Armenia",
            "Georgia":"Georgia","Belarus":"Belarus","Lithuania":"Lituania","Latvia":"Letonia","Estonia":"Estonia","Finland":"Finlanda","Sweden":"Suedia",
            "Norway":"Norvegia","Denmark":"Danemarca","Switzerland":"Elveția","Portugal":"Portugalia","Ireland":"Irlanda","EU":"UE","Europe":"Europa","Vatican":"Vatican",
            "US":"SUA","China":"China","Israel":"Israel","Gaza":"Gaza","Iran":"Iran","Lebanon":"Liban","Syria":"Siria","Iraq":"Irak","Saudi Arabia":"Arabia Saudită",
            "Japan":"Japonia","North Korea":"Coreea de Nord","South Korea":"Coreea de Sud","India":"India","Pakistan":"Pakistan","Afghanistan":"Afganistan",
            "Brazil":"Brazilia","Argentina":"Argentina","Venezuela":"Venezuela","Mexico":"Mexic","Canada":"Canada","Australia":"Australia","Africa":"Africa",
            "Egypt":"Egipt","Sudan":"Sudan","Ethiopia":"Etiopia","Nigeria":"Nigeria","Taiwan":"Taiwan","Indonesia":"Indonezia","Yemen":"Yemen","UN":"ONU"}

def find_place(text, table):
    t = " " + norm(text) + " "
    for ro, en in table:
        if re.search(r"(?<![a-z])" + re.escape(norm(ro)), t):
            return en
    return None

def classify(title, url):
    path = norm(url)
    text = title + " " + re.sub(r"[-_/]", " ", path.split("/", 3)[-1])
    t = norm(text)
    region, place, place_ro = "romania", "Romania", "România"
    if BUC.search(t):
        region, place, place_ro = "bucharest", "Bucharest", "București"
    else:
        w = find_place(title, WORLD)
        e = find_place(title, EUROPE)
        if e:
            region, place = "europe", e
        elif w:
            region, place = "world", w
        elif "/externe" in path or "/international" in path or "/extern" in path:
            region, place = "world", "World"
        if region == "romania" and "extern" in path:
            region, place = "world", "World"
        if region != "romania":
            place_ro = PLACE_RO.get(place, "Lume" if place == "World" else place)
    topic = None
    if "/sport" in path: topic = "sport"
    elif "/politic" in path and region in ("romania", "bucharest"): topic = "politics"
    if not topic:
        for name, rx in TOPIC_RULES:
            if rx.search(t):
                topic = name
                break
    if not topic:
        if "/econom" in path or "/financ" in path or "/business" in path: topic = "economy"
        elif "/cultur" in path: topic = "culture"
        elif "/tech" in path or "/it-c" in path: topic = "tech"
        elif region in ("world", "europe"): topic = "world"
        else: topic = "economy"
    return topic, region, place, place_ro

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/xml, text/xml, */*"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()

def strip(s):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return re.sub(r"\s+", " ", s).strip()

def parse(data):
    root = ET.fromstring(data)
    out = []
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag not in ("item", "entry"):
            continue
        get = lambda name: next((c for c in el if c.tag.split("}")[-1] == name), None)
        t, l = get("title"), get("link")
        title = strip(t.text if t is not None else "")
        link = (l.text or l.get("href") or "").strip() if l is not None else ""
        d = next((x for x in (get("pubDate"), get("published"), get("updated"), get("date")) if x is not None), None)
        when = None
        if d is not None and d.text:
            try:
                when = email.utils.parsedate_to_datetime(d.text.strip())
            except Exception:
                try:
                    when = datetime.fromisoformat(d.text.strip().replace("Z", "+00:00"))
                except Exception:
                    when = None
        if when is not None and when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if title and link.startswith("http"):
            out.append((title, link.replace("http://", "https://", 1), when))
    return out

def same_event(a, b):
    common = len(a & b)
    return common >= 3 and common / max(1, min(len(a), len(b))) >= 0.5

def main():
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=KEEP_DAYS)
    with open(NEWS, encoding="utf-8") as f:
        data = json.load(f)
    stories = [s for s in data.get("stories", []) if s.get("publishedAt", "") >= cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")]
    known_urls = {x.get("url") for s in stories for x in s.get("sources", [])}
    toks = [tokens(s.get("title_ro") or s.get("title", "")) for s in stories]
    report, added, updated = [], 0, 0
    for outlet, urls in FEEDS.items():
        items = None
        for u in urls:
            try:
                items = parse(fetch(u))
                if items:
                    report.append(f"{outlet}: {len(items)} items from {u}")
                    break
            except Exception as e:
                report.append(f"{outlet}: {u} failed ({type(e).__name__})")
        if not items:
            continue
        for title, link, when in items:
            if link in known_urls or SKIP.search(title):
                continue
            when = when or now
            if when < cutoff or when > now + timedelta(hours=1):
                continue
            tk = tokens(title)
            match = next((i for i, t in enumerate(toks) if same_event(tk, t)), None)
            if match is not None:
                s = stories[match]
                if outlet not in {x.get("name") for x in s.get("sources", [])}:
                    s.setdefault("sources", []).append({"name": outlet, "url": link})
                    updated += 1
                known_urls.add(link)
                continue
            topic, region, place, place_ro = classify(title, link)
            sid = "auto-" + hashlib.sha1(link.encode()).hexdigest()[:12]
            stories.append({"id": sid, "title": title, "title_ro": title, "summary": "", "summary_ro": "",
                            "topic": topic, "region": region, "place": place, "place_ro": place_ro,
                            "publishedAt": when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "sources": [{"name": outlet, "url": link}]})
            toks.append(tk)
            known_urls.add(link)
            added += 1
    if added == 0 and updated == 0 and not any("items from" in r for r in report):
        print("\n".join(report))
        sys.exit("No feed could be read; news.json left unchanged.")
    stories.sort(key=lambda s: s.get("publishedAt", ""), reverse=True)
    data["stories"] = stories[:MAX_STORIES]
    data["lastRun"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(NEWS, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print("\n".join(report))
    print(f"added={added} updated={updated} total={len(data['stories'])}")

if __name__ == "__main__":
    main()
