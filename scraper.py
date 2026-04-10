#!/usr/bin/env python3
"""
scraper.py — Foreclosure + Tax Sale Scraper
Runs on GitHub Actions every 6 hours.
Writes results to data/listings.json (loaded by the tracker on page open).

Sources:
  Lucas County, OH:
    - Lucas County Sheriff Sales
    - RealAuction (Lucas County)
    - Toledo Land Bank
  DMV Area:
    - Fannie Mae HomePath REO (VA/MD/DC)
    - HUD Homes (VA/MD/DC)
    - Fairfax County land records (lis pendens)
    - VA Lawyers Weekly public notices (trustee sales)
"""

import json
import re
import os
import sys
import hashlib
from datetime import datetime, timedelta
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode, quote
from html.parser import HTMLParser

TODAY = datetime.utcnow().strftime("%Y-%m-%d")
OUTPUT_FILE = "data/listings.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

DMV_KEYWORDS = [
    "fairfax","arlington","loudoun","leesburg","manassas","prince william",
    "stafford","alexandria","reston","herndon","mclean","vienna","annandale",
    "burke","springfield","woodbridge","ashburn","sterling","centreville",
    "chantilly","falls church","tysons","washington dc","district of columbia",
    "montgomery","prince george","rockville","bethesda","silver spring",
    "gaithersburg","takoma park","college park","greenbelt","laurel",
]

DMV_ZIPS = {
    "20120","20121","20124","20151","20152","20165","20166","20170","20171",
    "20172","20175","20176","20180","20190","20191","20194","22003","22015",
    "22027","22030","22031","22032","22033","22035","22039","22041","22042",
    "22043","22044","22046","22060","22066","22079","22101","22102","22150",
    "22151","22152","22153","22180","22181","22182","22201","22202","22203",
    "22204","22205","22206","22207","22209","22301","22302","22303","22304",
    "22305","22306","22307","22308","22309","22310","22314","22315","20109",
    "20110","20111","20112","20136","20001","20002","20003","20004","20005",
    "20006","20007","20008","20009","20010","20011","20012","20015","20016",
    "20017","20018","20019","20020","20850","20852","20853","20854","20855",
    "20877","20878","20879","20886","20895","20901","20902","20903","20904",
    "20905","20906","20910","20912","20740","20742","20743","20744","20745",
    "20746","20747","20748",
}

# ── Helpers ────────────────────────────────────────────────────────────────

def fetch(url, data=None, extra_headers=None, timeout=20):
    headers = {**HEADERS, **(extra_headers or {})}
    try:
        req = Request(url, data=data, headers=headers)
        with urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (URLError, HTTPError) as e:
        print(f"  [fetch error] {url}: {e}", file=sys.stderr)
        return ""

def uid(seed):
    return "sc-" + hashlib.md5(seed.encode()).hexdigest()[:10]

def parse_date(s):
    if not s:
        return None
    s = s.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y",
                "%m-%d-%Y", "%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None

def extract_address(text):
    pattern = r"\d{2,5}\s+[A-Za-z][A-Za-z0-9\s\.\#]{3,50}(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Court|Ct|Place|Pl|Blvd|Boulevard|Way|Circle|Cir|Terrace|Ter)\b"
    m = re.search(pattern, text, re.IGNORECASE)
    return m.group(0).strip().upper()[:80] if m else None

def extract_zip(text):
    m = re.search(r"\b(2[012]\d{3}|4360\d|4361\d|4362\d)\b", text)
    return m.group(1) if m else None

def extract_money(text):
    m = re.search(r"\$\s*([\d,]+(?:\.\d{2})?)", text)
    return int(float(m.group(1).replace(",", ""))) if m else None

def extract_sale_date(text):
    patterns = [
        r"sale\s+date[:\s]+([A-Za-z]+\s+\d{1,2},?\s+\d{4})",
        r"(?:will\s+be\s+sold|sold\s+at\s+auction)\s+on\s+([A-Za-z]+\s+\d{1,2},?\s+\d{4})",
        r"(?:auction|sale)\s+(?:date|on)[:\s]+(\d{1,2}/\d{1,2}/\d{4})",
        r"(\d{1,2}/\d{1,2}/\d{4})",
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            d = parse_date(m.group(1))
            if d and d >= TODAY:
                return d
    return None

def is_dmv(text):
    low = text.lower()
    if any(kw in low for kw in DMV_KEYWORDS):
        return True
    zips = re.findall(r"\b(\d{5})\b", low)
    return any(z in DMV_ZIPS for z in zips)

def county_from_text(text):
    low = text.lower()
    if "fairfax" in low:            return "Fairfax"
    if "arlington" in low:          return "Arlington"
    if "loudoun" in low or "leesburg" in low: return "Loudoun"
    if "manassas" in low or "prince william" in low: return "Prince William"
    if "stafford" in low:           return "Stafford"
    if "alexandria" in low:         return "Alexandria"
    if "montgomery" in low:         return "Montgomery MD"
    if "prince george" in low:      return "Prince George's MD"
    if "district of columbia" in low or ", dc" in low: return "DC"
    return "DMV Area"

def strip_tags(html):
    class S(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []
        def handle_data(self, d):
            self.parts.append(d)
    p = S()
    p.feed(html)
    return " ".join(p.parts)

# ── Source 1: Lucas County Sheriff ────────────────────────────────────────

def scrape_lucas_sheriff():
    results = []
    url = "https://www.lucascountysheriff.org/civil/sheriff-sales"
    print("[Lucas Sheriff] fetching...")
    html = fetch(url)
    if not html:
        return results

    # Find table rows — sheriff site lists case#, date, address, appraised
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL | re.IGNORECASE)
    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL | re.IGNORECASE)
        if len(cells) < 3:
            continue
        texts = [strip_tags(c).strip() for c in cells]
        case_no    = texts[0] if len(texts) > 0 else ""
        date_raw   = texts[1] if len(texts) > 1 else ""
        addr_raw   = texts[2] if len(texts) > 2 else ""
        appraised  = texts[3] if len(texts) > 3 else ""

        addr = addr_raw.strip().upper()
        if not addr or len(addr) < 5 or "address" in addr.lower():
            continue

        zip_m = re.search(r"\b(4360\d|4361\d|4362\d)\b", addr)
        zip_c = zip_m.group(1) if zip_m else "43600"
        val   = extract_money(appraised)
        auction = parse_date(date_raw)

        results.append({
            "id":       uid(f"lucas-sheriff-{case_no}-{addr}"),
            "address":  addr,
            "zip":      zip_c,
            "county":   "Lucas",
            "market":   "lucas",
            "stage":    "Auction",
            "filed":    None,
            "auction":  auction,
            "est_value": val,
            "source":   "Lucas Co. Sheriff",
            "url":      url,
            "notes":    f"Case: {case_no}" if case_no else "",
            "tax_owed": None,
            "redemption_period": "",
            "tax_rate": None,
            "scraped":  TODAY,
        })

    print(f"[Lucas Sheriff] {len(results)} listings")
    return results

# ── Source 2: RealAuction Lucas County ────────────────────────────────────

def scrape_realauction():
    results = []
    url = "https://lucas.realauction.com/Assets/Search"
    print("[RealAuction] fetching...")

    payload = json.dumps({
        "pageNumber": 1,
        "pageSize": 200,
        "sortColumn": "AuctionStartDate",
        "sortDirection": "ASC",
    }).encode("utf-8")

    extra = {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://lucas.realauction.com/",
    }

    raw = fetch(url, data=payload, extra_headers=extra)
    if not raw:
        return results

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print("  [RealAuction] JSON parse error", file=sys.stderr)
        return results

    items = data.get("Items") or data.get("items") or data.get("results") or []
    for i, item in enumerate(items):
        addr = " ".join(filter(None, [
            item.get("StreetAddress") or item.get("streetAddress") or item.get("address",""),
            item.get("City") or "Toledo",
        ])).strip().upper()

        zip_c   = str(item.get("Zip") or item.get("zip") or "43600")[:5]
        val     = item.get("AppraisedValue") or item.get("appraisedValue") or item.get("StartingBid")
        auction = parse_date(str(item.get("AuctionStartDate") or item.get("auctionStartDate") or ""))
        asset_id = item.get("AssetId") or item.get("assetId") or i

        results.append({
            "id":       uid(f"realauction-{asset_id}"),
            "address":  addr or "See listing",
            "zip":      zip_c,
            "county":   "Lucas",
            "market":   "lucas",
            "stage":    "Auction",
            "filed":    parse_date(str(item.get("FiledDate") or "")),
            "auction":  auction,
            "est_value": int(val) if val else None,
            "source":   "RealAuction (Lucas Co.)",
            "url":      f"https://lucas.realauction.com/Assets/Details/{asset_id}",
            "notes":    "",
            "tax_owed": None,
            "redemption_period": "",
            "tax_rate": None,
            "scraped":  TODAY,
        })

    print(f"[RealAuction] {len(results)} listings")
    return results

# ── Source 3: Toledo Land Bank ─────────────────────────────────────────────

def scrape_toledo_land_bank():
    results = []
    url = "https://www.toledolucascountylandbank.com/properties"
    print("[Toledo Land Bank] fetching...")
    html = fetch(url)
    if not html:
        return results

    # Land bank property cards typically have address + price
    addrs = re.findall(
        r'(?:class="[^"]*(?:address|property|title)[^"]*"[^>]*>|<h[23][^>]*>)\s*([^<]{10,80})</(?:div|h[23])',
        html, re.IGNORECASE
    )
    prices = re.findall(r"\$\s*([\d,]+)", html)

    seen = set()
    for i, raw_addr in enumerate(addrs):
        addr = raw_addr.strip().upper()
        if not addr or addr in seen or len(addr) < 8:
            continue
        if not re.search(r"\d", addr):  # must have a number
            continue
        seen.add(addr)
        zip_m = re.search(r"\b(4360\d|4361\d|4362\d)\b", addr)
        val   = int(prices[i].replace(",","")) if i < len(prices) else None

        results.append({
            "id":       uid(f"landbank-{addr}"),
            "address":  addr,
            "zip":      zip_m.group(1) if zip_m else "43600",
            "county":   "Lucas",
            "market":   "lucas",
            "stage":    "Land Bank",
            "filed":    TODAY,
            "auction":  None,
            "est_value": val,
            "source":   "Toledo Land Bank",
            "url":      url,
            "notes":    "Toledo/Lucas County Land Bank property",
            "tax_owed": None,
            "redemption_period": "",
            "tax_rate": None,
            "scraped":  TODAY,
        })

    print(f"[Toledo Land Bank] {len(results)} listings")
    return results

# ── Source 4: Fannie Mae HomePath REO ─────────────────────────────────────

def scrape_fannie_mae():
    results = []
    print("[Fannie Mae] fetching...")

    for state in ["VA", "DC", "MD"]:
        url = "https://www.homepath.com/lossprevention/api/search"
        payload = json.dumps({
            "stateCode": state,
            "pageNumber": 1,
            "itemsPerPage": 200,
        }).encode("utf-8")
        extra = {
            "Content-Type": "application/json",
            "Referer": "https://www.homepath.com/",
            "Origin": "https://www.homepath.com",
        }
        raw = fetch(url, data=payload, extra_headers=extra)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue

        props = data.get("properties") or data.get("results") or data.get("listings") or []
        for i, p in enumerate(props):
            zip_c = str(p.get("postalCode") or p.get("zip") or "")[:5]
            if zip_c not in DMV_ZIPS:
                continue
            addr = " ".join(filter(None, [
                p.get("streetAddress") or p.get("address",""),
                p.get("city",""),
                state
            ])).strip().upper()
            county = county_from_text(addr)
            val    = p.get("listPrice") or p.get("price")
            detail = p.get("detailUrl","")

            results.append({
                "id":       uid(f"fannie-{state}-{i}-{addr}"),
                "address":  addr or "See listing",
                "zip":      zip_c,
                "county":   county,
                "market":   "dmv",
                "stage":    "REO",
                "filed":    parse_date(str(p.get("listDate") or "")),
                "auction":  None,
                "est_value": int(val) if val else None,
                "source":   "Fannie Mae HomePath",
                "url":      f"https://www.homepath.com{detail}" if detail else "https://www.homepath.com",
                "notes":    "",
                "tax_owed": None,
                "redemption_period": "",
                "tax_rate": None,
                "scraped":  TODAY,
            })

    print(f"[Fannie Mae] {len(results)} DMV listings")
    return results

# ── Source 5: HUD Homes ────────────────────────────────────────────────────

def scrape_hud():
    results = []
    print("[HUD Homes] fetching...")

    for state in ["VA", "DC", "MD"]:
        url = (
            "https://hudgov-answers.force.com/homesales/services/apexrest/"
            f"HUDHomeAPI/getPropertiesForList?stateCode={state}&pageNumber=1&numRowsPerPage=200"
        )
        raw = fetch(url)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue

        for i, p in enumerate(data.get("lstPropDetail") or []):
            zip_c = str(p.get("prop_zip") or "")[:5]
            if zip_c not in DMV_ZIPS:
                continue
            addr = f"{p.get('prop_addr','')} {p.get('prop_city','')} {state}".strip().upper()
            val  = p.get("list_price")

            results.append({
                "id":       uid(f"hud-{state}-{p.get('case_num',i)}"),
                "address":  addr,
                "zip":      zip_c,
                "county":   county_from_text(addr),
                "market":   "dmv",
                "stage":    "REO",
                "filed":    parse_date(str(p.get("list_date") or "")),
                "auction":  None,
                "est_value": int(val) if val else None,
                "source":   "HUD Homes",
                "url":      "https://www.hudhomestore.gov",
                "notes":    f"Case: {p.get('case_num','')}",
                "tax_owed": None,
                "redemption_period": "",
                "tax_rate": None,
                "scraped":  TODAY,
            })

    print(f"[HUD Homes] {len(results)} DMV listings")
    return results

# ── Source 6: VA Lawyers Weekly (trustee sale notices) ────────────────────

def scrape_vlw():
    results = []
    print("[VA Lawyers Weekly] fetching...")

    for path in [
        "https://valawyersweekly.com/public-notices/?category=foreclosure",
        "https://valawyersweekly.com/public-notices/?category=trustee",
    ]:
        html = fetch(path)
        if not html:
            continue

        # WordPress article listings
        articles = re.findall(
            r'<article[^>]*>(.*?)</article>', html, re.DOTALL | re.IGNORECASE
        )
        for i, art in enumerate(articles):
            text = strip_tags(art)
            if not re.search(r"trustee|foreclosure|deed\s+of\s+trust", text, re.IGNORECASE):
                continue
            if not is_dmv(text):
                continue

            # Try to get a link
            link_m = re.search(r'href="(https://valawyersweekly\.com[^"]+)"', art)
            link = link_m.group(1) if link_m else path

            # Date
            date_m = re.search(r'datetime="([^"]+)"', art)
            filed  = parse_date(date_m.group(1)[:10]) if date_m else TODAY

            addr    = extract_address(text)
            auction = extract_sale_date(text)
            val     = extract_money(text)

            results.append({
                "id":       uid(f"vlw-{i}-{text[:40]}"),
                "address":  addr or "See notice (address in legal text)",
                "zip":      extract_zip(text),
                "county":   county_from_text(text),
                "market":   "dmv",
                "stage":    "Auction",
                "filed":    filed,
                "auction":  auction,
                "est_value": val,
                "source":   "VA Lawyers Weekly",
                "url":      link,
                "notes":    text[:200].strip(),
                "tax_owed": None,
                "redemption_period": "",
                "tax_rate": None,
                "scraped":  TODAY,
            })

        # Also scan raw text for trustee notice blocks
        raw_blocks = re.split(
            r"NOTICE OF TRUSTEE.?S SALE|SUBSTITUTE TRUSTEE.?S NOTICE",
            html, flags=re.IGNORECASE
        )
        for i, block in enumerate(raw_blocks[1:21]):
            text = strip_tags(block[:800])
            if not is_dmv(text):
                continue
            addr    = extract_address(text)
            auction = extract_sale_date(text)
            val     = extract_money(text)
            results.append({
                "id":       uid(f"vlw-block-{i}-{text[:30]}"),
                "address":  addr or "See notice",
                "zip":      extract_zip(text),
                "county":   county_from_text(text),
                "market":   "dmv",
                "stage":    "Auction",
                "filed":    TODAY,
                "auction":  auction,
                "est_value": val,
                "source":   "VA Lawyers Weekly",
                "url":      path,
                "notes":    text[:200].strip(),
                "tax_owed": None,
                "redemption_period": "",
                "tax_rate": None,
                "scraped":  TODAY,
            })

    print(f"[VA Lawyers Weekly] {len(results)} DMV listings")
    return results

# ── Deduplicate ────────────────────────────────────────────────────────────

def deduplicate(listings):
    seen = {}
    out  = []
    for r in listings:
        key = (r["address"].strip().upper(), r.get("auction") or r.get("filed") or "")
        if key not in seen:
            seen[key] = True
            out.append(r)
    return out

# ── Load existing + merge ──────────────────────────────────────────────────

def load_existing():
    try:
        with open(OUTPUT_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

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

    return [
        r for r in by_id.values()
        if (r.get("filed") or TODAY) >= cutoff or r.get("stage") == "REO"
    ]

# ── Main ───────────────────────────────────────────────────────────────────

def main():
    print(f"Scraper starting — {TODAY}")
    os.makedirs("data", exist_ok=True)

    scrapers = [
        scrape_lucas_sheriff,
        scrape_realauction,
        scrape_toledo_land_bank,
        scrape_fannie_mae,
        scrape_hud,
        scrape_vlw,
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

    # Sort newest first
    merged.sort(key=lambda r: r.get("filed") or "", reverse=True)

    with open(OUTPUT_FILE, "w") as f:
        json.dump(merged, f, indent=2)

    print(f"\nDone — {len(merged)} total listings saved to {OUTPUT_FILE}")
    print(f"  New/updated from this run: {len(incoming)}")

if __name__ == "__main__":
    main()
