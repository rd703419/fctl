#!/usr/bin/env python3
"""
scraper.py — Foreclosure + Tax Sale Scraper
All sources confirmed working as of April 2026.

DMV Sources:
  - Washington Times classifieds (8 category pages)
  - Rosenberg & Associates — foreclosure auction table
  - TACS / taxva.com — Virginia tax deed sales
  - Auction.com — Fairfax, Loudoun, Arlington, Alexandria

Lucas County Sources:
  - Amlin Auctions — Toledo real estate auctions
  - Toledo Legal News — foreclosure notices (improved address extraction)
  - Pamela Rose Auction — Toledo auction house
  - Auction.com Toledo
  - Lucas Co. Sheriff RealAuction (fallback attempt)
"""

import json, re, os, sys, hashlib
from datetime import datetime, timedelta
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from html.parser import HTMLParser

TODAY       = datetime.utcnow().strftime("%Y-%m-%d")
OUTPUT_FILE = "data/listings.json"
YEAR        = datetime.utcnow().year

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept":     "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

WT_CATEGORIES = [
    ("http://classified.washingtontimes.com/category/354/Foreclosure-Sales-ALEX-Cty.html", "Alexandria",         "dmv"),
    ("http://classified.washingtontimes.com/category/355/Foreclosure-Sales-ARL-Cty.html",  "Arlington",          "dmv"),
    ("http://classified.washingtontimes.com/category/357/Foreclosure-Sales-DC.html",        "DC",                 "dmv"),
    ("http://classified.washingtontimes.com/category/358/Foreclosure-Sales-FFX-Cty.html",   "Fairfax",            "dmv"),
    ("http://classified.washingtontimes.com/category/359/Foreclosure-Sales-Mont-Cty.html",  "Montgomery MD",      "dmv"),
    ("http://classified.washingtontimes.com/category/360/Foreclosure-Sales-PG-Cty.html",    "Prince George's MD", "dmv"),
    ("http://classified.washingtontimes.com/category/394/Foreclosure-Sales-PW-Cty.html",    "Prince William",     "dmv"),
    ("http://classified.washingtontimes.com/category/405/Forclosure-Sales-VA.html",         "DMV Area",           "dmv"),
]

AUCTION_COM_PAGES = [
    ("https://www.auction.com/residential/VA/Fairfax_ct/active_lt/auction_date_order,resi_sort_v2_st/y_nbs",    "Fairfax",   "dmv"),
    ("https://www.auction.com/residential/VA/Loudoun-county/active_lt/auction_date_order,resi_sort_v2_st/y_nbs","Loudoun",   "dmv"),
    ("https://www.auction.com/residential/VA/Arlington_ct/active_lt/auction_date_order,resi_sort_v2_st/y_nbs",  "Arlington", "dmv"),
    ("https://www.auction.com/residential/VA/Alexandria_ct/active_lt/auction_date_order,resi_sort_v2_st/y_nbs", "Alexandria","dmv"),
    ("https://www.auction.com/residential/oh/Toledo_ct",                                                         "Lucas",     "lucas"),
]

DMV_COUNTY_MAP = {
    "alexandria":"Alexandria","arlington":"Arlington","fairfax":"Fairfax",
    "prince william":"Prince William","loudoun":"Loudoun","stafford":"Stafford",
    "montgomery":"Montgomery MD","prince george":"Prince George's MD",
    "charles":"Charles MD","manassas":"Manassas","herndon":"Fairfax",
    "reston":"Fairfax","mclean":"Fairfax","annandale":"Fairfax",
    "centreville":"Fairfax","woodbridge":"Prince William","ashburn":"Loudoun",
    "leesburg":"Loudoun","sterling":"Loudoun","falls church":"Falls Church",
    "silver spring":"Montgomery MD","rockville":"Montgomery MD",
    "bethesda":"Montgomery MD","gaithersburg":"Montgomery MD",
    "upper marlboro":"Prince George's MD","hyattsville":"Prince George's MD",
    "clinton":"Prince George's MD","fort washington":"Prince George's MD",
    "washington":"DC","district of columbia":"DC","nokesville":"Prince William",
    "gainesville":"Prince William","dumfries":"Prince William",
}

LUCAS_ZIPS   = {str(z) for z in range(43600,43620)}
LUCAS_CITIES = {"toledo","sylvania","maumee","oregon","perrysburg",
                "waterville","northwood","rossford","holland"}

# ── Helpers ────────────────────────────────────────────────────────────────

def fetch(url, timeout=25):
    try:
        req = Request(url, headers=HEADERS)
        with urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except (URLError, HTTPError) as e:
        print(f"  [fetch error] {url}: {e}", file=sys.stderr)
        return ""

def uid(s):
    return "sc-" + hashlib.md5(s.encode()).hexdigest()[:10]

def strip_tags(html):
    class P(HTMLParser):
        def __init__(self): super().__init__(); self.parts=[]
        def handle_data(self, d): self.parts.append(d)
    p=P(); p.feed(html); return " ".join(p.parts)

def clean(s):
    return re.sub(r'\s+',' ', s or '').strip()

def parse_date(s):
    if not s: return None
    s = re.sub(r'\s+',' ', str(s)).strip()
    for fmt in ("%m-%d-%Y","%Y-%m-%d","%m/%d/%Y","%B %d, %Y","%b %d, %Y",
                "%B %d %Y","%b %d %Y","%b. %d, %Y","%b. %d %Y"):
        try: return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError: pass
    return None

def extract_money(s):
    m = re.search(r'\$\s*([\d,]+(?:\.\d{2})?)', str(s))
    return int(float(m.group(1).replace(',',''))) if m else None

def county_from_text(text):
    low = text.lower()
    for kw, county in DMV_COUNTY_MAP.items():
        if kw in low:
            return county
    return None

def is_lucas(text):
    low = text.lower()
    zips = re.findall(r'\b(\d{5})\b', text)
    if any(z in LUCAS_ZIPS for z in zips): return True
    return any(c in low for c in LUCAS_CITIES)

def extract_address_from_notice(text):
    patterns = [
        r'(?:TRUSTEE.?S?\s+SALE\s+OF|SALE\s+OF\s+PROPERTY|SALE\s+OF)\s+([^,\n]{5,80}(?:VA|DC|MD)\s+\d{5})',
        r'(?:offer\s+for\s+sale|sold\s+at\s+auction)\s+[^.]{0,60}?(\d{3,5}\s+[A-Za-z][A-Za-z\s#\.]{3,50}(?:VA|DC|MD)\s+\d{5})',
        r'(\d{3,5}\s+[A-Za-z][A-Za-z0-9\s#\.]{3,60}(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Court|Ct|Place|Pl|Blvd|Boulevard|Way|Circle|Cir|Terrace|Ter|NW|NE|SE|SW)\b[^,\n]{0,40}(?:VA|DC|MD|Virginia|Maryland)\s*[\d,]*)',
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            addr = clean(m.group(1))
            if len(addr) > 8:
                return addr.upper()
    return None

def extract_sale_date_from_notice(text):
    patterns = [
        r'(?:sale\s+date|auction\s+date|will\s+be\s+(?:held|conducted|sold))\s*[:\-]?\s*([A-Za-z]+\s+\d{1,2},?\s+\d{4})',
        r'(?:on|at\s+auction\s+on)\s+([A-Za-z]+\s+\d{1,2},?\s+\d{4})',
        r'(\d{1,2}/\d{1,2}/\d{4})',
        r'([A-Za-z]+\s+\d{1,2},\s+\d{4})',
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            d = parse_date(m.group(1))
            if d and d >= TODAY:
                return d
    return None


# ── Source 1: Washington Times Classifieds ────────────────────────────────

def scrape_washington_times():
    results = []
    total   = 0

    for url, default_county, market in WT_CATEGORIES:
        print(f"[Washington Times] {default_county}...", flush=True)
        html = fetch(url)
        if not html:
            continue

        # Each listing: <h2><a href="LISTING_URL">TITLE</a></h2>
        # followed by: <a href="LISTING_URL">FULL NOTICE TEXT...</a>
        # The notice text IS the link text of the second anchor
        listing_links = re.findall(
            r'href="(http://classified\.washingtontimes\.com/category/\d+/[^/]+/listings/[^"]+)"[^>]*>([^<]{30,})</a>',
            html, re.IGNORECASE
        )

        count = 0
        seen_links = set()
        for link, notice_text in listing_links:
            if link in seen_links:
                continue
            # Skip short navigation text
            if len(notice_text) < 50:
                continue
            seen_links.add(link)
            notice_text = clean(notice_text)

            addr = extract_address_from_notice(notice_text)
            if not addr:
                continue

            county = county_from_text(notice_text + " " + addr) or default_county

            loan_amount = None
            loan_m = re.search(r'principal\s+amount\s+of\s+\$?([\d,\.]+)', notice_text, re.IGNORECASE)
            if loan_m:
                loan_amount = extract_money("$" + loan_m.group(1))

            auction_date = extract_sale_date_from_notice(notice_text)
            zip_m = re.search(r'\b(2[012]\d{3})\b', addr + " " + notice_text)

            results.append({
                "id":       uid(f"wt-{link}"),
                "address":  addr[:80],
                "zip":      zip_m.group(1) if zip_m else "",
                "county":   county,
                "market":   market,
                "stage":    "Auction",
                "filed":    TODAY,
                "auction":  auction_date,
                "est_value": loan_amount,
                "source":   f"Washington Times ({default_county})",
                "url":      link,
                "notes":    notice_text[:300],
                "tax_owed": None, "redemption_period": "", "tax_rate": None,
                "scraped":  TODAY,
            })
            count += 1

        print(f"  -> {count} listings", flush=True)
        total += count

    print(f"[Washington Times] Total: {total}", flush=True)
    return results

# ── Source 2: Rosenberg & Associates ──────────────────────────────────────

def scrape_rosenberg():
    url = "https://rosenberg-assoc.com/foreclosure-sales/"
    print("[Rosenberg] fetching...", flush=True)
    html = fetch(url)
    if not html:
        return []

    results = []
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL | re.IGNORECASE)

    for row in rows:
        if re.search(r'<th', row, re.IGNORECASE): continue
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL | re.IGNORECASE)
        if len(cells) < 8: continue

        texts     = [clean(strip_tags(c)) for c in cells]
        case_no   = texts[0] if len(texts) > 0 else ""
        sale_date = texts[1] if len(texts) > 1 else ""
        address   = texts[3] if len(texts) > 3 else ""
        city      = texts[4] if len(texts) > 4 else ""
        juris     = texts[5] if len(texts) > 5 else ""
        state     = texts[6] if len(texts) > 6 else ""
        zip_c     = texts[7] if len(texts) > 7 else ""
        deposit   = texts[8] if len(texts) > 8 else ""

        if not address or len(address) < 5: continue
        if state.upper() not in ("VA","DC","MD"): continue

        cancelled_m = re.search(r'cancelled["\s:=]+([YN])', row, re.IGNORECASE)
        if cancelled_m and cancelled_m.group(1).upper() == 'Y': continue

        full   = f"{address} {city} {juris} {state}"
        county = county_from_text(full) or clean(juris) or city
        auction = parse_date(sale_date)
        dep_val = extract_money(deposit)

        results.append({
            "id":       uid(f"rosenberg-{case_no}-{address}"),
            "address":  f"{address.upper()}, {city.upper()}, {state.upper()} {zip_c}".strip(", "),
            "zip":      zip_c[:5],
            "county":   county, "market": "dmv", "stage": "Auction",
            "filed":    TODAY, "auction": auction,
            "est_value": dep_val * 10 if dep_val else None,
            "source":   "Rosenberg & Assoc.",
            "url":      url,
            "notes":    f"Case: {case_no}. Deposit: {deposit}",
            "tax_owed": None, "redemption_period": "", "tax_rate": None,
            "scraped":  TODAY,
        })

    print(f"[Rosenberg] {len(results)} listings", flush=True)
    return results


# ── Source 3: TACS / taxva.com ─────────────────────────────────────────────

def scrape_taxva():
    url  = "https://taxva.com/real-estate-tax-sales/"
    print("[TACS/taxva] fetching...", flush=True)
    html = fetch(url)
    if not html: return []

    results = []
    dmv_kw = ["manassas","falls church","fairfax","alexandria","prince william",
              "arlington","loudoun","stafford","dumfries","herndon","reston",
              "leesburg","ashburn","manassas park"]

    items = re.findall(
        r'<a\s+href="(https://taxva\.com/rs-tax-sales/[^"]+)"[^>]*>(.*?)</a>',
        html, re.DOTALL | re.IGNORECASE
    )

    for link, raw in items:
        text = clean(strip_tags(raw))
        if not any(kw in text.lower() for kw in dmv_kw): continue

        date_m   = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', text)
        date_str = date_m.group(1) if date_m else None
        auction  = parse_date(date_str)
        locality = re.sub(r'\s*[<br>–\-].*','',text).replace("City of","").replace("County of","").strip()
        county   = county_from_text(locality) or locality

        detail = fetch(link)
        addrs  = []
        if detail:
            dt    = strip_tags(detail)
            addrs = re.findall(
                r'\d{3,5}\s+[A-Za-z][A-Za-z0-9\s\.#]{3,50}(?:St|Ave|Rd|Dr|Ln|Ct|Pl|Blvd|Way|Ter|Cir)\b[^\n<]{0,30}',
                dt, re.IGNORECASE
            )

        if addrs:
            for addr in addrs[:20]:
                results.append({
                    "id":       uid(f"taxva-{clean(addr).upper()}"),
                    "address":  clean(addr).upper()[:80],
                    "zip":      "",
                    "county":   county, "market": "dmv", "stage": "Tax Deed",
                    "filed":    TODAY, "auction": auction, "est_value": None,
                    "source":   "TACS (taxva.com)", "url": link,
                    "notes":    f"VA tax deed sale — {locality}",
                    "tax_owed": None, "redemption_period": "", "tax_rate": None,
                    "scraped":  TODAY,
                })
        else:
            results.append({
                "id":       uid(f"taxva-{locality}-{date_str or TODAY}"),
                "address":  f"Multiple properties — {locality}",
                "zip":      "", "county": county, "market": "dmv", "stage": "Tax Deed",
                "filed":    TODAY, "auction": auction, "est_value": None,
                "source":   "TACS (taxva.com)", "url": link,
                "notes":    f"VA tax deed sale — {locality}. See link for properties.",
                "tax_owed": None, "redemption_period": "", "tax_rate": None,
                "scraped":  TODAY,
            })

    print(f"[TACS/taxva] {len(results)} listings", flush=True)
    return results


# ── Source 4: Auction.com ──────────────────────────────────────────────────

def scrape_auction_com():
    results = []

    for url, default_county, market in AUCTION_COM_PAGES:
        print(f"[Auction.com] {default_county}...", flush=True)
        html = fetch(url)
        if not html: continue

        text  = strip_tags(html)
        count = 0

        json_blocks = re.findall(
            r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
            html, re.DOTALL | re.IGNORECASE
        )
        for jb in json_blocks:
            try:
                data  = json.loads(jb)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get("@type") not in ("RealEstateListing","Product","Offer","House"):
                        continue
                    addr = item.get("address",{})
                    full = f"{addr.get('streetAddress','')} {addr.get('addressLocality','')} {addr.get('addressRegion','')} {addr.get('postalCode','')}".strip() if isinstance(addr, dict) else str(addr)
                    if market == "lucas" and not is_lucas(full): continue
                    val   = item.get("price") or item.get("offers",{}).get("price")
                    zip_m = re.search(r'\b(\d{5})\b', full)
                    results.append({
                        "id":       uid(f"auctioncom-{full}"),
                        "address":  full.upper()[:80],
                        "zip":      zip_m.group(1) if zip_m else "",
                        "county":   county_from_text(full) or default_county,
                        "market":   market, "stage": "Auction",
                        "filed":    TODAY, "auction": None,
                        "est_value": int(float(str(val).replace(",",""))) if val else None,
                        "source":   "Auction.com", "url": url, "notes": "",
                        "tax_owed": None, "redemption_period": "", "tax_rate": None,
                        "scraped":  TODAY,
                    })
                    count += 1
            except (json.JSONDecodeError, KeyError, ValueError, AttributeError):
                pass

        if count == 0:
            addrs  = re.findall(r'\d{3,5}\s+[A-Za-z][A-Za-z\s]+(?:St|Ave|Rd|Dr|Ln|Blvd|Ct|Way)\b[^\n<]{0,30}', text, re.IGNORECASE)
            prices = re.findall(r'\$[\d,]+', text)
            seen   = set()
            for i, addr in enumerate(addrs[:30]):
                addr_c = clean(addr).upper()
                if addr_c in seen: continue
                if market == "lucas" and not is_lucas(addr_c): continue
                seen.add(addr_c)
                zip_m = re.search(r'\b(4360\d|4361\d|4362\d|2[012]\d{3})\b', addr_c)
                results.append({
                    "id":       uid(f"auctioncom-{addr_c}"),
                    "address":  addr_c[:80],
                    "zip":      zip_m.group(1) if zip_m else "",
                    "county":   county_from_text(addr_c) or default_county,
                    "market":   market, "stage": "Auction",
                    "filed":    TODAY, "auction": None,
                    "est_value": extract_money(prices[i]) if i < len(prices) else None,
                    "source":   "Auction.com", "url": url, "notes": "",
                    "tax_owed": None, "redemption_period": "", "tax_rate": None,
                    "scraped":  TODAY,
                })
                count += 1

        print(f"  -> {count} listings", flush=True)

    print(f"[Auction.com] Total: {len(results)}", flush=True)
    return results


# ── Source 5: Amlin Auctions ───────────────────────────────────────────────

def scrape_amlin():
    url  = "https://www.amlinauctions.com/"
    print("[Amlin Auctions] fetching...", flush=True)
    html = fetch(url)
    if not html: return []

    results = []
    cards = re.findall(
        r'<h2[^>]*>\s*<a\s+href="([^"]+)"[^>]*>([^<]+)</a>\s*</h2>(.*?)(?=<h2|\Z)',
        html, re.DOTALL | re.IGNORECASE
    )

    for link, title, body in cards:
        title = clean(title)
        if "SOLD PRIOR" in title.upper(): continue

        body_t = strip_tags(body)
        full   = f"{title} {body_t}"
        if not is_lucas(full): continue

        addr_m = re.search(
            r'(\d{3,5}\s+[A-Za-z][A-Za-z0-9\s]+(?:,\s*(?:Toledo|Sylvania|Maumee|Oregon|Perrysburg|Waterville|Northwood)[^,\n<]{0,20})?)',
            body_t, re.IGNORECASE
        )
        if not addr_m: continue
        addr = clean(addr_m.group(1)).upper()

        zip_m   = re.search(r'\b(4360\d|4361\d|4362\d)\b', full)
        date_m  = re.search(r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{1,2})', body_t, re.IGNORECASE)
        auction = parse_date(f"{date_m.group(1)} {YEAR}") if date_m else None
        min_bid = extract_money(title)

        results.append({
            "id":       uid(f"amlin-{addr}"),
            "address":  addr[:80], "zip": zip_m.group(1) if zip_m else "",
            "county":   "Lucas", "market": "lucas", "stage": "Auction",
            "filed":    TODAY, "auction": auction, "est_value": min_bid,
            "source":   "Amlin Auctions",
            "url":      link if link.startswith("http") else f"https://www.amlinauctions.com{link}",
            "notes":    title,
            "tax_owed": None, "redemption_period": "", "tax_rate": None,
            "scraped":  TODAY,
        })

    print(f"[Amlin Auctions] {len(results)} listings", flush=True)
    return results


# ── Source 6: Toledo Legal News (improved address extraction) ──────────────

def scrape_toledo_legal():
    url  = "https://www.toledolegalnews.com/legal_notices/foreclosure_sherrif_sales_lucas/"
    print("[Toledo Legal News] fetching...", flush=True)
    html = fetch(url)
    if not html: return []

    results = []
    text   = strip_tags(html)
    seen   = set()

    blocks = re.split(
        r'(?=(?:SHERIFF.?S\s+SALE|NOTICE\s+OF\s+SHERIFF.?S\s+SALE|BY\s+VIRTUE\s+OF))',
        text, flags=re.IGNORECASE
    )

    for block in blocks[1:60]:
        block = clean(block)
        if len(block) < 30: continue

        addr_patterns = [
            r'(?:located\s+at|known\s+as|property\s+address[:\s]+|premises\s+known\s+as|situate\s+at|street\s+address[:\s]+)\s+(\d{3,5}\s+[A-Za-z][A-Za-z0-9\s#\.]{3,60}(?:Toledo|Sylvania|Maumee|Oregon|Perrysburg|Waterville|Northwood)[^,\n<]{0,30})',
            r'(\d{3,5}\s+[A-Za-z][A-Za-z0-9\s#\.]{3,50}(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Court|Ct|Place|Pl|Blvd|Way)\s*,?\s*(?:Toledo|Sylvania|Maumee|Oregon|Perrysburg|Waterville|Northwood)[^,\n]{0,20}(?:OH|Ohio)\s*\d{5})',
            r'(\d{3,5}\s+[A-Za-z][A-Za-z0-9\s#\.]{3,50}(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Court|Ct|Place|Pl|Blvd|Way)\b[^,\n]{0,30}(?:4360\d|4361\d|4362\d))',
        ]

        addr = None
        for pattern in addr_patterns:
            m = re.search(pattern, block, re.IGNORECASE)
            if m:
                addr = clean(m.group(1)).upper()
                break

        if not addr or addr in seen or len(addr) < 10: continue
        if re.match(r'^CI\d', addr) or re.match(r'^\d{4}-', addr): continue

        seen.add(addr)

        zip_m  = re.search(r'\b(4360\d|4361\d|4362\d)\b', block)
        val_m  = re.search(r'appraised?\s+(?:at|value[:\s]+)\s*\$?([\d,]+)', block, re.IGNORECASE)
        val    = int(val_m.group(1).replace(',','')) if val_m else extract_money(block)
        date_m = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', block)
        case_m = re.search(r'[Cc]ase\s+#?\s*(CI[\w\-]+)', block)

        results.append({
            "id":       uid(f"tln-{addr}"),
            "address":  addr[:80],
            "zip":      zip_m.group(1) if zip_m else "",
            "county":   "Lucas", "market": "lucas", "stage": "Auction",
            "filed":    TODAY,
            "auction":  parse_date(date_m.group(1)) if date_m else None,
            "est_value": val,
            "source":   "Toledo Legal News",
            "url":      url,
            "notes":    f"Case: {case_m.group(1)}" if case_m else clean(block[:150]),
            "tax_owed": None, "redemption_period": "", "tax_rate": None,
            "scraped":  TODAY,
        })

    print(f"[Toledo Legal News] {len(results)} listings", flush=True)
    return results


# ── Source 7: Pamela Rose Auction ──────────────────────────────────────────

def scrape_pamela_rose():
    url  = "https://www.pamelaroseauction.com/"
    print("[Pamela Rose] fetching...", flush=True)
    html = fetch(url)
    if not html: return []

    results = []
    text    = strip_tags(html)
    addrs   = re.findall(
        r'\d{3,5}\s+[A-Za-z][A-Za-z\s]+(?:St|Ave|Rd|Dr|Ln|Ct|Pl|Blvd|Way)\b[^,\n<]{0,40}',
        text, re.IGNORECASE
    )
    seen = set()

    for addr in addrs[:30]:
        addr_c = clean(addr).upper()
        if addr_c in seen or not is_lucas(addr_c): continue
        seen.add(addr_c)
        zip_m = re.search(r'\b(4360\d|4361\d|4362\d)\b', addr_c)
        results.append({
            "id":       uid(f"pamrose-{addr_c}"),
            "address":  addr_c[:80], "zip": zip_m.group(1) if zip_m else "",
            "county":   "Lucas", "market": "lucas", "stage": "Auction",
            "filed":    TODAY, "auction": None, "est_value": None,
            "source":   "Pamela Rose Auction", "url": url, "notes": "",
            "tax_owed": None, "redemption_period": "", "tax_rate": None,
            "scraped":  TODAY,
        })

    print(f"[Pamela Rose] {len(results)} listings", flush=True)
    return results


# ── Source 8: Lucas County Sheriff RealAuction (fallback) ─────────────────

def scrape_lucas_sheriff_auction():
    urls = [
        "https://lucas.sheriffsaleauction.ohio.gov/index.cfm?zaction=AUCTION&Zmethod=PREVIEW",
        "https://lucas.sheriffsaleauction.ohio.gov/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDATE=",
        "https://lucas.sheriffsaleauction.ohio.gov/index.cfm?zaction=AUCTION&Zmethod=SEARCH",
    ]
    print("[Lucas Sheriff RealAuction] fetching...", flush=True)

    for url in urls:
        html = fetch(url)
        if not html: continue

        results = []
        text    = strip_tags(html)

        addr_patterns = [
            r'(\d{3,5}\s+[A-Za-z][A-Za-z0-9\s#\.]{3,50}(?:Toledo|Sylvania|Maumee|Oregon|Perrysburg|Waterville|Northwood)[^,\n<]{0,30})',
            r'(\d{3,5}\s+[A-Za-z][A-Za-z0-9\s#\.]{3,50}(?:St|Ave|Rd|Dr|Ln|Ct|Blvd|Way)\b[^,\n<]{0,20}(?:4360\d|4361\d|4362\d))',
        ]

        all_addrs = []
        for pattern in addr_patterns:
            all_addrs.extend(re.findall(pattern, text, re.IGNORECASE))

        prices = re.findall(r'\$[\d,]+', text)
        dates  = re.findall(r'\d{1,2}/\d{1,2}/\d{4}', text)
        seen   = set()

        for i, addr in enumerate(all_addrs[:40]):
            addr_c = clean(addr).upper()
            if addr_c in seen or len(addr_c) < 8: continue
            if not is_lucas(addr_c): continue
            seen.add(addr_c)

            zip_m = re.search(r'\b(4360\d|4361\d|4362\d)\b', addr_c)
            results.append({
                "id":       uid(f"lucassheriff-{addr_c}"),
                "address":  addr_c[:80],
                "zip":      zip_m.group(1) if zip_m else "",
                "county":   "Lucas", "market": "lucas", "stage": "Auction",
                "filed":    TODAY,
                "auction":  parse_date(dates[i]) if i < len(dates) else None,
                "est_value": extract_money(prices[i]) if i < len(prices) else None,
                "source":   "Lucas Co. Sheriff (RealAuction)",
                "url":      "https://lucas.sheriffsaleauction.ohio.gov/",
                "notes":    "",
                "tax_owed": None, "redemption_period": "", "tax_rate": None,
                "scraped":  TODAY,
            })

        if results:
            print(f"[Lucas Sheriff RealAuction] {len(results)} listings", flush=True)
            return results

    print("[Lucas Sheriff RealAuction] 0 listings (blocked or no data)", flush=True)
    return []


# ── Dedup + merge ──────────────────────────────────────────────────────────

def deduplicate(listings):
    seen = {}
    out  = []
    for r in listings:
        key = (r["address"].strip().upper()[:60], r.get("auction") or r.get("filed") or "")
        if key not in seen:
            seen[key] = True
            out.append(r)
    return out

def load_existing():
    try:
        with open(OUTPUT_FILE) as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): return []

def merge(existing, incoming):
    cutoff = (datetime.utcnow() - timedelta(days=90)).strftime("%Y-%m-%d")
    by_id  = {r["id"]: r for r in existing}
    for r in incoming:
        if r["id"] in by_id:
            old = by_id[r["id"]]
            by_id[r["id"]] = {**old, "stage": r["stage"], "auction": r["auction"],
                              "est_value": r["est_value"] or old.get("est_value"),
                              "scraped": TODAY}
        else:
            by_id[r["id"]] = r
    return [r for r in by_id.values()
            if (r.get("filed") or TODAY) >= cutoff or r.get("stage") == "REO"]


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    print(f"Scraper starting — {TODAY}", flush=True)
    os.makedirs("data", exist_ok=True)

    scrapers = [
        scrape_washington_times,      # 8 WT pages — primary DMV source
        scrape_rosenberg,             # Rosenberg & Assoc. foreclosure table
        scrape_taxva,                 # Virginia tax deed sales
        scrape_auction_com,           # Auction.com — DMV + Toledo
        scrape_amlin,                 # Amlin Auctions — Toledo
        scrape_toledo_legal,          # Toledo Legal News (improved)
        scrape_pamela_rose,           # Pamela Rose — Toledo
        scrape_lucas_sheriff_auction, # Lucas Co. Sheriff RealAuction (fallback)
    ]

    incoming = []
    for scraper in scrapers:
        try:
            results = scraper()
            incoming.extend(results)
        except Exception as e:
            print(f"  [{scraper.__name__}] ERROR: {e}", file=sys.stderr)

    incoming = deduplicate(incoming)
    existing = load_existing()
    merged   = merge(existing, incoming)
    merged.sort(key=lambda r: r.get("filed") or "", reverse=True)

    with open(OUTPUT_FILE, "w") as f:
        json.dump(merged, f, indent=2)

    lucas = sum(1 for r in merged if r.get("market") == "lucas")
    dmv   = sum(1 for r in merged if r.get("market") == "dmv")

    print(f"\nDone — {len(merged)} total listings", flush=True)
    print(f"  Lucas County: {lucas}  |  DMV Area: {dmv}", flush=True)
    print(f"  New/updated this run: {len(incoming)}", flush=True)

if __name__ == "__main__":
    main()
