# FCTL — Foreclosure & Tax Sale Tracker

Browser-based tracker for **Lucas County, OH** and **DMV area** (Northern VA, DC, MD) foreclosures and tax sales. Runs on GitHub Pages for free. Auto-scrapes listings every 6 hours via GitHub Actions — no server, no hosting costs.

---

## Setup — step by step

### Step 1 — Create a GitHub account
1. Go to [github.com](https://github.com) → **Sign up**
2. Enter your email, create a password, choose a username
3. Verify your email

### Step 2 — Create a repository
1. Click **+** (top right) → **New repository**
2. Name it: `fctl`
3. Set to **Public**
4. Check **Add a README file**
5. Leave `.gitignore` and License as **None**
6. Click **Create repository**

### Step 3 — Upload files
1. Click **Add file** → **Upload files**
2. Drag the entire `fctl-v2` folder onto the upload area — GitHub preserves the folder structure
3. Add commit message: `initial upload`
4. Click **Commit changes**

Your repo should look like this:
```
fctl/
  index.html
  scraper.py
  css/style.css
  js/app.js
  data/listings.json
  .github/workflows/scrape.yml
  README.md
```

### Step 4 — Enable GitHub Pages
1. Click **Settings** tab → **Pages** (left sidebar)
2. Under Source: **Deploy from a branch**
3. Branch: `main`, folder: `/ (root)`
4. Click **Save**

Your tracker will be live at:
```
https://YOUR-USERNAME.github.io/fctl/
```
(takes ~2 minutes the first time)

### Step 5 — Enable GitHub Actions write permission
The scraper needs permission to commit updated listings back to your repo.

1. In your repo, click **Settings** → **Actions** → **General** (left sidebar)
2. Scroll to **Workflow permissions**
3. Select **Read and write permissions**
4. Click **Save**

### Step 6 — Run the scraper for the first time
1. Click the **Actions** tab in your repo
2. Click **Scrape foreclosure listings** (left sidebar)
3. Click **Run workflow** → **Run workflow**
4. Wait ~2 minutes for it to complete
5. Refresh your tracker — real listings will appear

After this it runs automatically every 6 hours.

---

## How it works

```
GitHub Actions (every 6 hours, free)
        ↓
scraper.py fetches:
  · Lucas Co. Sheriff sales
  · RealAuction (Lucas Co.)
  · Toledo Land Bank
  · Fannie Mae HomePath REO (VA/MD/DC)
  · HUD Homes (VA/MD/DC)
  · VA Lawyers Weekly trustee notices
        ↓
Saves → data/listings.json (committed to your repo)
        ↓
Your tracker loads listings.json when you open the page
```

Your manually added/edited listings are saved in your browser's local storage and merged with the scraped data on every page load — so your notes and additions survive scraper updates.

---

## Triggering a manual scrape

Go to **Actions** tab → **Scrape foreclosure listings** → **Run workflow** → **Run workflow**.

Takes about 2 minutes. The tracker auto-refreshes when you next open it.

---

## Adding listings manually

Click **+ Add** in the tracker. Your additions are saved locally and persist across scraper runs.

## Importing from CSV

Drag a `.csv` file onto the tracker page, or click **Import**.

Column order:
```
address, zip, county, market, stage, filed, auction, est_value, source, url, notes, tax_owed, redemption_period, tax_rate
```

`market`: `lucas` or `dmv`

`stage`: `Pre-Foreclosure`, `Filing`, `Auction`, `REO`, `Tax Lien`, `Tax Deed`, `Land Bank`

---

## Sources

### Lucas County, OH
| Source | URL |
|--------|-----|
| Sheriff sales | lucascountysheriff.org/civil/sheriff-sales |
| Online auctions | lucas.realauction.com |
| Tax delinquent list | co.lucas.oh.us/treasurer |
| Land Bank | toledolucascountylandbank.com |
| Fannie Mae REO | homepath.com |
| HUD Homes | hudhomestore.gov |

### DMV Area
| Source | URL |
|--------|-----|
| Fairfax tax sale | fairfaxcounty.gov/taxes/real-estate/tax-sale |
| Arlington tax sale | arlingtonva.us |
| DC tax lien sale | otr.cfo.dc.gov/page/tax-sale |
| Montgomery Co. | montgomerycountymd.gov/finance/tax-sale.html |
| VA Lawyers Weekly | valawyersweekly.com/public-notices |
| Fairfax land records | icare.fairfaxcounty.gov |

---

## Keyboard shortcuts
| Key | Action |
|-----|--------|
| `Ctrl/Cmd + N` | Add new listing |
| `Escape` | Close modal |

---

## Privacy
Your listing data (notes, edits, added properties) lives in your **browser's local storage** — it never touches GitHub. The scraped `listings.json` contains only public court/county data.

---

## Upgrading coverage

Add the **ATTOM Data API** for pre-foreclosure filings and early-stage lis pendens (not publicly available on county sites). Free trial available at attomdata.com.

Once you have a key:
1. Go to your repo → **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Name: `ATTOM_API_KEY`, Value: your key
4. The scraper will automatically use it on the next run
