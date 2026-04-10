#!/usr/bin/env python3
"""
weekly_email.py — FCTL Weekly Upcoming Sales Email
Sends every Monday at 8am ET with all listings having an auction
date within the next 7 days, grouped by market.
"""

import json, os, smtplib, sys
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

LISTINGS_FILE = "data/listings.json"
TRACKER_URL   = "https://rd703419.github.io/fctl/"

def load_listings():
    try:
        with open(LISTINGS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def fmt_money(v):
    if not v: return "—"
    return f"${int(v):,}"

def fmt_date(s):
    if not s: return "—"
    try:
        d = datetime.strptime(s, "%Y-%m-%d")
        return d.strftime("%b %d, %Y")
    except ValueError:
        return s

def days_until(s):
    try:
        d = datetime.strptime(s, "%Y-%m-%d")
        delta = (d - datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)).days
        if delta == 0: return "Today"
        if delta == 1: return "Tomorrow"
        return f"In {delta} days"
    except ValueError:
        return ""

def build_table_rows(listings):
    rows = []
    for r in listings:
        urgency_color = "#d93025" if days_until(r.get("auction","")) in ("Today","Tomorrow") else "#1a73e8"
        zest = fmt_money(r.get("zestimate"))
        z60  = fmt_money(r.get("zestimate_60pct"))
        rows.append(f"""
        <tr>
          <td style="padding:10px 12px;border-bottom:1px solid #e8eaed;font-size:13px;font-weight:500;color:#202124;max-width:220px">{r.get('address','—')}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #e8eaed;font-size:13px;color:#5f6368">{r.get('county','—')}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #e8eaed;font-size:13px;color:#5f6368">{r.get('stage','—')}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #e8eaed;font-size:13px;color:{urgency_color};font-weight:500;white-space:nowrap">{fmt_date(r.get('auction'))}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #e8eaed;font-size:13px;color:{urgency_color};font-size:11px">{days_until(r.get('auction',''))}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #e8eaed;font-size:13px;color:#202124;font-family:monospace">{fmt_money(r.get('est_value'))}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #e8eaed;font-size:13px;color:#202124;font-family:monospace">{zest}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #e8eaed;font-size:13px;color:#1e8e3e;font-family:monospace">{z60}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #e8eaed;font-size:12px;color:#80868b">{r.get('source','—')}</td>
        </tr>""")
    return "".join(rows)

def build_section(title, listings, accent_color):
    if not listings:
        return f"""
        <div style="margin-bottom:32px">
          <h2 style="font-size:16px;font-weight:500;color:#202124;margin:0 0 4px">{title}</h2>
          <p style="font-size:13px;color:#80868b;margin:0">No sales scheduled in the next 7 days.</p>
        </div>"""

    rows = build_table_rows(listings)
    count = len(listings)
    return f"""
    <div style="margin-bottom:36px">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">
        <div style="width:4px;height:24px;background:{accent_color};border-radius:2px"></div>
        <h2 style="font-size:16px;font-weight:500;color:#202124;margin:0">{title}</h2>
        <span style="background:{accent_color}1a;color:{accent_color};font-size:12px;font-weight:500;padding:2px 10px;border-radius:12px">{count} upcoming</span>
      </div>
      <div style="overflow-x:auto;border-radius:8px;border:1px solid #e8eaed">
        <table style="width:100%;border-collapse:collapse;font-family:'Google Sans',Roboto,sans-serif">
          <thead>
            <tr style="background:#f8f9fa">
              <th style="padding:10px 12px;text-align:left;font-size:11px;font-weight:500;color:#80868b;text-transform:uppercase;letter-spacing:.05em;white-space:nowrap">Address</th>
              <th style="padding:10px 12px;text-align:left;font-size:11px;font-weight:500;color:#80868b;text-transform:uppercase;letter-spacing:.05em">County</th>
              <th style="padding:10px 12px;text-align:left;font-size:11px;font-weight:500;color:#80868b;text-transform:uppercase;letter-spacing:.05em">Stage</th>
              <th style="padding:10px 12px;text-align:left;font-size:11px;font-weight:500;color:#80868b;text-transform:uppercase;letter-spacing:.05em">Sale Date</th>
              <th style="padding:10px 12px;text-align:left;font-size:11px;font-weight:500;color:#80868b;text-transform:uppercase;letter-spacing:.05em"></th>
              <th style="padding:10px 12px;text-align:left;font-size:11px;font-weight:500;color:#80868b;text-transform:uppercase;letter-spacing:.05em">Est. Value</th>
              <th style="padding:10px 12px;text-align:left;font-size:11px;font-weight:500;color:#80868b;text-transform:uppercase;letter-spacing:.05em">Zestimate</th>
              <th style="padding:10px 12px;text-align:left;font-size:11px;font-weight:500;color:#80868b;text-transform:uppercase;letter-spacing:.05em">60% Value</th>
              <th style="padding:10px 12px;text-align:left;font-size:11px;font-weight:500;color:#80868b;text-transform:uppercase;letter-spacing:.05em">Source</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </div>"""

def build_html(dmv, lucas, today_str, cutoff_str, total_count):
    total_section = f"""
    <div style="background:#e8f0fe;border-radius:8px;padding:16px 20px;margin-bottom:28px;display:flex;align-items:center;gap:16px">
      <div style="font-size:32px;font-weight:500;color:#1a73e8;font-family:monospace">{total_count}</div>
      <div>
        <div style="font-size:14px;font-weight:500;color:#1a73e8">upcoming sale{'s' if total_count!=1 else ''} in the next 7 days</div>
        <div style="font-size:12px;color:#5f6368;margin-top:2px">{today_str} → {cutoff_str}</div>
      </div>
    </div>""" if total_count else f"""
    <div style="background:#f8f9fa;border-radius:8px;padding:16px 20px;margin-bottom:28px">
      <div style="font-size:14px;color:#80868b">No upcoming sales found in the next 7 days.</div>
    </div>"""

    dmv_section   = build_section("DMV Area", dmv, "#1a73e8")
    lucas_section = build_section("Lucas County, OH", lucas, "#f9ab00")

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f8f9fa;font-family:'Google Sans',Roboto,Arial,sans-serif">
<div style="max-width:900px;margin:0 auto;padding:24px 16px">

  <!-- Header -->
  <div style="background:#ffffff;border-radius:12px;padding:20px 24px;margin-bottom:20px;border:1px solid #e8eaed;display:flex;align-items:center;justify-content:space-between">
    <div style="display:flex;align-items:center;gap:12px">
      <div style="background:#1a73e8;color:#fff;font-size:13px;font-weight:600;padding:5px 12px;border-radius:6px">FCTL</div>
      <div>
        <div style="font-size:15px;font-weight:500;color:#202124">Foreclosure &amp; Tax Sale Tracker</div>
        <div style="font-size:12px;color:#80868b">Weekly Upcoming Sales Report</div>
      </div>
    </div>
    <div style="font-size:12px;color:#80868b">{today_str}</div>
  </div>

  <!-- Main card -->
  <div style="background:#ffffff;border-radius:12px;padding:24px;border:1px solid #e8eaed;margin-bottom:16px">

    {total_section}
    {dmv_section}
    {lucas_section}

    <!-- Footer CTA -->
    <div style="text-align:center;padding-top:8px;border-top:1px solid #e8eaed;margin-top:8px">
      <a href="{TRACKER_URL}" style="display:inline-block;background:#1a73e8;color:#ffffff;font-size:14px;font-weight:500;padding:10px 24px;border-radius:24px;text-decoration:none">
        Open Tracker ↗
      </a>
    </div>

  </div>

  <!-- Footer -->
  <div style="text-align:center;font-size:11px;color:#80868b;padding:8px">
    FCTL · Auto-generated by GitHub Actions · <a href="{TRACKER_URL}" style="color:#1a73e8;text-decoration:none">rd703419.github.io/fctl</a>
  </div>

</div>
</body>
</html>"""

def build_plain_text(dmv, lucas, today_str, cutoff_str, total_count):
    lines = [
        "FCTL — Weekly Upcoming Sales Report",
        f"Week of {today_str} → {cutoff_str}",
        f"{total_count} upcoming sale{'s' if total_count!=1 else ''} in the next 7 days",
        "",
    ]

    for title, group in [("DMV Area", dmv), ("Lucas County, OH", lucas)]:
        lines.append(f"── {title} ──────────────────────────")
        if not group:
            lines.append("No sales scheduled in the next 7 days.")
        else:
            for r in group:
                lines.append(
                    f"  {r.get('address','—')} | {r.get('county','—')} | "
                    f"{r.get('stage','—')} | {fmt_date(r.get('auction'))} | "
                    f"Est: {fmt_money(r.get('est_value'))} | "
                    f"Zestimate: {fmt_money(r.get('zestimate'))} | "
                    f"60%: {fmt_money(r.get('zestimate_60pct'))}"
                )
        lines.append("")

    lines += [
        f"View tracker: {TRACKER_URL}",
        "FCTL · Auto-generated by GitHub Actions",
    ]
    return "\n".join(lines)

def send_email(html_body, plain_body, subject, gmail_user, app_password, recipient):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"FCTL Tracker <{gmail_user}>"
    msg["To"]      = recipient

    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body,  "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(gmail_user, app_password)
        smtp.sendmail(gmail_user, recipient, msg.as_string())

def main():
    gmail_user   = os.environ.get("GMAIL_USER", "")
    app_password = os.environ.get("GMAIL_APP_PASSWORD", "")
    recipient    = os.environ.get("RECIPIENT", "")

    if not gmail_user or not app_password:
        print("ERROR: GMAIL_USER or GMAIL_APP_PASSWORD secret not set", file=sys.stderr)
        sys.exit(1)

    if not recipient:
        print("ERROR: RECIPIENT not set", file=sys.stderr)
        sys.exit(1)

    today  = datetime.utcnow().date()
    cutoff = today + timedelta(days=7)

    today_str  = today.strftime("%b %d, %Y")
    cutoff_str = cutoff.strftime("%b %d, %Y")

    listings = load_listings()
    print(f"Loaded {len(listings)} total listings", flush=True)

    # Filter to listings with auction dates in the next 7 days
    upcoming = []
    for r in listings:
        auction = r.get("auction")
        if not auction:
            continue
        try:
            auction_date = datetime.strptime(auction, "%Y-%m-%d").date()
            if today <= auction_date <= cutoff:
                upcoming.append(r)
        except ValueError:
            pass

    # Sort by auction date
    upcoming.sort(key=lambda r: r.get("auction",""))

    dmv   = [r for r in upcoming if r.get("market") == "dmv"]
    lucas = [r for r in upcoming if r.get("market") == "lucas"]
    total = len(upcoming)

    print(f"Upcoming sales: {total} total ({len(dmv)} DMV, {len(lucas)} Lucas)", flush=True)

    week_num   = today.isocalendar()[1]
    subject    = f"FCTL — {total} Upcoming Sale{'s' if total!=1 else ''} This Week (Week {week_num})"

    html_body  = build_html(dmv, lucas, today_str, cutoff_str, total)
    plain_body = build_plain_text(dmv, lucas, today_str, cutoff_str, total)

    print(f"Sending to {recipient}...", flush=True)
    send_email(html_body, plain_body, subject, gmail_user, app_password, recipient)
    print("Email sent successfully", flush=True)

if __name__ == "__main__":
    main()
