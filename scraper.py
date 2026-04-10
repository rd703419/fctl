#!/usr/bin/env python3
"""
scraper.py — Foreclosure + Tax Sale Scraper
Updated URLs for 2026.
"""

import json
import re
import os
import sys
import hashlib
from datetime import datetime, timedelta
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

TODAY = datetime.utcnow().strftime("%Y-%m-%d")
OUTPUT_FILE = "data/listings.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

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

DMV_KEYWORDS = [
    "fairfax","arlington","loudoun","leesburg","manassas","prince william",
    "stafford","alexandria","reston","herndon","mclean","vienna","annandale",
    "burke","springfield","woodbridge","ashburn","sterling","centreville",
    "chantilly","falls church","tysons","washington dc","district of columbia",
    "montgomery","prince george","rockville","bethesda","silver spring",
    "gaithersburg","takoma park","college park","greenbelt","laurel",
]

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
    s = str(s).strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None

def strip_tags(html):
    return re.sub(r'<[^>]+>', ' ', html)

def extract_money(text):
    m = re.search(r'\$\s*([\d,]+)', text)
    return int(m.group(1).replace(',','')) if m else None

def extract_zip(text):
    m = re.search(r'\b(2[012]\d{3}|4360\d|4361\d|4362\d)\b', text)
    return m.group(1) if m else None

def county_from_text(text):
    low = text.lower()
    if "fairfax" in low:          return "Fairfax"
    if "arlington" in low:        return "Arlington"
    if "loudoun" in low or "leesburg" in low: return "Loudoun"
    if "manassas" in low or "prince william" in low: return "Prince William"
    if "stafford" in low:         return "Stafford"
    if "alexandria" in low:       return "Alexandria"
    if "montgomery" in low:       return "Montgomery MD"
    if "prince george" in low:    return "Prince George's MD"
    if "district of columbia" in low or ", dc" in low: return "DC"
    return "DMV Area"

def is_dmv(text):
    low = text.lower()
    if any(kw in low for kw in DMV_KEYWORDS):
        return True
    zips = re.findall(r'\b(\d{5})\b', text)
    return any(z in DMV_ZIPS for z in zips)

# ── Source 1: Lucas County Sheriff Sale Auction (new platform) ────────────

def scrape_lucas_sheriff():
    results = []
    url = "https://lucas.sheriffsaleauction.ohio.gov/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDATE="
    print("[Lucas Sheriff] fetching new platform...", flush=True)
    html = fetch(url)
    if not html:
        # Try the main page
        html = fetch("https://lucas.sheriffsaleauction.ohio.gov/")
    if not html:
        print("[Lucas Sheriff] no response", flush=True)
        return results

    # Parse property cards from the auction site
    # The RealAuction platform renders property cards with class "AUCTION_ITEM"
    cards = re.findall(r'<div[^>]*class="[^"]*AUCTION_ITEM[^"]*"[^>]*>(.*?)</div>\s*</div>', html, re.DOTALL | re.IGNORECASE)
    if not cards:
        # Try table rows
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL | re.IGNORECASE)
        for row in rows:
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL | re.IGNORECASE)
            if len(cells) < 3:
                continue
            texts = [strip_tags(c).strip() for c in cells]
            addr = next((t for t in texts if re.search(r'\d{3,5}\s+\w', t)), None)
            if not addr or len(addr) < 8:
                continue
            date_vals = [parse_date(t) for t in texts if parse_date(t)]
            money_vals = [extract_money(t) for t in texts if extract_money(t)]
            results.append({
                "id": uid(f"lucas-sheriff-{addr}"),
                "address": addr.upper()[:80],
                "zip": extract_zip(addr) or "43600",
                "county": "Lucas", "market": "lucas", "stage": "Auction",
                "filed": None, "auction": date_vals[0] if date_vals else None,
                "est_value": money_vals[0] if money_vals else None,
                "source": "Lucas Co. Sheriff",
                "url": "https://lucas.sheriffsaleauction.ohio.gov/",
                "notes": "", "tax_owed": None, "redemption_period": "", "tax_rate": None,
                "scraped": TODAY,
            })

    print(f"[Lucas Sheriff] {len(results)} listings", flush=True)
    return results

# ── Source 2: Lucas Sheriff Sale Auction JSON API ─────────────────────────

def scrape_lucas_auction_api():
    results = []
    print("[Lucas Auction API] fetching...", flush=True)

    # The sheriffsaleauction.ohio.gov platform (RealAuction) has a search API
    url = "https://lucas.sheriffsaleauction.ohio.gov/index.cfm?zaction=AUCTION&Zmethod=PREVIEW"
    extra = {"X-Requested-With": "XMLHttpRequest", "Referer": "https://lucas.sheriffsaleauction.ohio.gov/"}
    html = fetch(url, extra_headers=extra)
    if not html:
        return results

    # Extract addresses and values from the page
    addr_pattern = r'\b\d{3,5}\s+[A-Z][A-Za-z\s]+(?:ST|AVE|RD|DR|LN|CT|PL|BLVD|WAY|CIR)\b'
    addrs = re.findall(addr_pattern, html.upper())
    prices = re.findall(r'\$[\d,]+', html)

    seen = set()
    for i, addr in enumerate(addrs):
        addr = addr.strip()
        if addr in seen or len(addr) < 8:
            continue
        seen.add(addr)
        val = extract_money(prices[i]) if i < len(prices) else None
        results.append({
            "id": uid(f"lucas-api-{addr}"),
            "address": addr[:80],
            "zip": extract_zip(addr) or "43600",
            "county": "Lucas", "market": "lucas", "stage": "Auction",
            "filed": None, "auction": None,
            "est_value": val,
            "source": "Lucas Co. Sheriff",
            "url": "https://lucas.sheriffsaleauction.ohio.gov/",
            "notes": "", "tax_owed": None, "redemption_period": "", "tax_rate": None,
            "scraped": TODAY,
        })

    print(f"[Lucas Auction API] {len(results)} listings", flush=True)
    return results

# ── Source 3: Toledo Legal News (public foreclosure notices) ──────────────

def scrape_toledo_legal_news():
    results = []
    url = "https://www.toledolegalnews.com/legal_notices/foreclosure_sherrif_sales_lucas/"
    print("[Toledo Legal News] fetching...", flush=True)
    html = fetch(url)
    if not html:
        return results

    # Extract notice blocks
    text = strip_tags(html)
    blocks = re.split(r'(?=\d{3,5}\s+[A-Z])', text)
    seen = set()
    for block in blocks[:50]:
        block = block.strip()
        if len(block) < 20:
            continue
        addr_m = re.match(r'(\d{3,5}\s+[A-Za-z\s]{3,40})', block)
        if not addr_m:
            continue
        addr = addr_m.group(1).strip().upper()
        if addr in seen:
            continue
        seen.add(addr)
        zip_c = extract_zip(block) or "43600"
        val = extract_money(block)
        results.append({
            "id": uid(f"tln-{addr}"),
            "address": addr[:80],
            "zip": zip_c,
            "county": "Lucas", "market": "lucas", "stage": "Auction",
            "filed": TODAY, "auction": None,
            "est_value": val,
            "source": "Toledo Legal News",
            "url": url,
            "notes": block[:200],
            "tax_owed": None, "redemption_period": "", "tax_rate": None,
            "scraped": TODAY,
        })

    print(f"[Toledo Legal News] {len(results)} listings", flush=True)
    return results

# ── Source 4: Fannie Mae HomePath (updated domain) ────────────────────────

def scrape_fannie_mae():
    results = []
    print("[Fannie Mae] fetching...", flush=True)

    # Updated domain: homepath.fanniemae.com
    for state in ["VA", "DC", "MD"]:
        url = "https://homepath.fanniemae.com/lossprevention/api/search"
        payload = json.dumps({
            "stateCode": state,
            "pageNumber": 1,
            "itemsPerPage": 200,
        }).encode("utf-8")
        extra = {
            "Content-Type": "application/json",
            "Referer": "https://homepath.fanniemae.com/",
            "Origin": "https://homepath.fanniemae.com",
        }
        raw = fetch(url, data=payload, extra_headers=extra)
        if not raw:
            # Try alternate endpoint
            alt = f"https://homepath.fanniemae.com/api/search?stateCode={state}&pageSize=200"
            raw = fetch(alt, extra_headers={"Referer": "https://homepath.fanniemae.com/"})
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
                p.get("streetAddress") or p.get("address", ""),
                p.get("city", ""), state
            ])).strip().upper()
            val = p.get("listPrice") or p.get("price")
            detail = p.get("detailUrl", "")
            results.append({
                "id": uid(f"fannie-{state}-{i}-{addr}"),
                "address": addr or "See listing",
                "zip": zip_c,
                "county": county_from_text(addr),
                "market": "dmv", "stage": "REO",
                "filed": parse_date(str(p.get("listDate") or "")),
                "auction": None,
                "est_value": int(val) if val else None,
                "source": "Fannie Mae HomePath",
                "url": f"https://homepath.fanniemae.com{detail}" if detail else "https://homepath.fanniemae.com",
                "notes": "", "tax_owed": None, "redemption_period": "", "tax_rate": None,
                "scraped": TODAY,
            })

    print(f"[Fannie Mae] {len(results)} DMV listings", flush=True)
    return results

# ── Source 5: HUD Homes (updated endpoint) ────────────────────────────────

def scrape_hud():
    results = []
    print("[HUD Homes] fetching...", flush=True)

    for state in ["VA", "DC", "MD"]:
        # Try updated HUD endpoint
        urls = [
            f"https://www.hudhomestore.gov/Home/PropertySearch.aspx?sState={state}",
            f"https://hudgov-answers.force.com/homesales/services/apexrest/HUDHomeAPI/v2/getPropertiesForList?stateCode={state}&pageNumber=1&numRowsPerPage=200",
        ]
        raw = ""
        for url in urls:
            raw = fetch(url)
            if raw:
                break
        if not raw:
            continue

        # Try JSON parse first
        try:
            data = json.loads(raw)
            for i, p in enumerate(data.get("lstPropDetail") or data.get("properties") or []):
                zip_c = str(p.get("prop_zip") or p.get("zip") or "")[:5]
                if zip_c not in DMV_ZIPS:
                    continue
                addr = f"{p.get('prop_addr','') or p.get('address','')} {p.get('prop_city','') or p.get('city','')} {state}".strip().upper()
                val = p.get("list_price") or p.get("listPrice")
                results.append({
                    "id": uid(f"hud-{state}-{i}-{addr}"),
                    "address": addr, "zip": zip_c,
                    "county": county_from_text(addr),
                    "market": "dmv", "stage": "REO",
                    "filed": parse_date(str(p.get("list_date") or p.get("listDate") or "")),
                    "auction": None,
                    "est_value": int(val) if val else None,
                    "source": "HUD Homes",
                    "url": "https://www.hudhomestore.gov",
                    "notes": f"Case: {p.get('case_num','')}",
                    "tax_owed": None, "redemption_period": "", "tax_rate": None,
                    "scraped": TODAY,
                })
        except json.JSONDecodeError:
            # HTML fallback — scrape the page
            addrs = re.findall(r'\d{3,5}\s+[A-Z][A-Za-z\s]+,\s*[A-Z]{2}\s+\d{5}', raw.upper())
            for i, addr in enumerate(addrs[:50]):
                zip_c = extract_zip(addr) or ""
                if zip_c not in DMV_ZIPS:
                    continue
                results.append({
                    "id": uid(f"hud-html-{state}-{i}"),
                    "address": addr[:80], "zip": zip_c,
                    "county": county_from_text(addr),
                    "market": "dmv", "stage": "REO",
                    "filed": TODAY, "auction": None, "est_value": None,
                    "source": "HUD Homes",
                    "url": "https://www.hudhomestore.gov",
                    "notes": "", "tax_owed": None, "redemption_period": "", "tax_rate": None,
                    "scraped": TODAY,
                })

    print(f"[HUD Homes] {len(results)} DMV listings", flush=True)
    return results

# ── Source 6: Fairfax County land records (lis pendens) ───────────────────

def scrape_fairfax():
    results = []
    url = "https://www.fairfaxcounty.gov/taxes/real-estate/tax-sale"
    print("[Fairfax Tax Sale] fetching...", flush=True)
    html = fetch(url)
    if not html:
        return results

    text = strip_tags(html)
    addrs = re.findall(r'\d{3,5}\s+[A-Za-z][A-Za-z\s]+(?:St|Ave|Rd|Dr|Ln|Ct|Pl|Blvd|Way)\b[^\n]{0,30}', text, re.IGNORECASE)
    seen = set()
    for i, addr in enumerate(addrs[:30]):
        addr_clean = addr.strip().upper()
        if addr_clean in seen or len(addr_clean) < 8:
            continue
        seen.add(addr_clean)
        zip_c = extract_zip(addr_clean) or ""
        results.append({
            "id": uid(f"fairfax-{addr_clean}"),
            "address": addr_clean[:80],
            "zip": zip_c,
            "county": "Fairfax", "market": "dmv", "stage": "Tax Deed",
            "filed": TODAY, "auction": None, "est_value": None,
            "source": "Fairfax Co. Tax Sale",
            "url": url,
            "notes": "", "tax_owed": None, "redemption_period": "", "tax_rate": None,
            "scraped": TODAY,
        })

    print(f"[Fairfax Tax Sale] {len(results)} listings", flush=True)
    return results

# ── Source 7: DC OTR Tax Sale ─────────────────────────────────────────────

def scrape_dc_tax_sale():
    results = []
    url = "https://otr.cfo.dc.gov/page/tax-sale"
    print("[DC Tax Sale] fetching...", flush=True)
    html = fetch(url)
    if not html:
        return results

    text = strip_tags(html)
    addrs = re.findall(r'\d{3,5}\s+[A-Za-z][A-Za-z\s]+(?:St|Ave|Rd|Dr|Ln|NW|NE|SE|SW)\b[^\n]{0,20}', text, re.IGNORECASE)
    seen = set()
    for i, addr in enumerate(addrs[:30]):
        addr_clean = addr.strip().upper()
        if addr_clean in seen or len(addr_clean) < 8:
            continue
        seen.add(addr_clean)
        results.append({
            "id": uid(f"dc-tax-{addr_clean}"),
            "address": addr_clean[:80],
            "zip": extract_zip(addr_clean) or "",
            "county": "DC", "market": "dmv", "stage": "Tax Lien",
            "filed": TODAY, "auction": None, "est_value": None,
            "source": "DC OTR Tax Sale",
            "url": url,
            "notes": "", "tax_owed": None, "redemption_period": "6 months", "tax_rate": 18,
            "scraped": TODAY,
        })

    print(f"[DC Tax Sale] {len(results)} listings", flush=True)
    return results

# ── Dedup + merge ──────────────────────────────────────────────────────────

def deduplicate(listings):
    seen = {}
    out = []
    for r in listings:
        key = (r["address"].strip().upper(), r.get("auction") or r.get("filed") or "")
        if key not in seen:
            seen[key] = True
            out.append(r)
    return out

def load_existing():
    try:
        with open(OUTPUT_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def merge(existing, incoming):
    cutoff = (datetime.utcnow() - timedelta(days=90)).strftime("%Y-%m-%d")
    by_id = {r["id"]: r for r in existing}
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
        scrape_lucas_sheriff,
        scrape_lucas_auction_api,
        scrape_toledo_legal_news,
        scrape_fannie_mae,
        scrape_hud,
        scrape_fairfax,
        scrape_dc_tax_sale,
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
    merged = merge(existing, incoming)
    merged.sort(key=lambda r: r.get("filed") or "", reverse=True)

    with open(OUTPUT_FILE, "w") as f:
        json.dump(merged, f, indent=2)

    print(f"\nDone — {len(merged)} total listings saved to {OUTPUT_FILE}", flush=True)
    print(f"  New/updated from this run: {len(incoming)}", flush=True)

if __name__ == "__main__":
    main()
