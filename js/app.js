// app.js — FCTL Foreclosure + Tax Sale Tracker
// Two-user sync via GitHub API — edits/deletions stored in data/user_edits.json

const STORE_KEY     = 'fctl_v2';
const DATA_URL      = 'data/listings.json';
const TAX_STAGES    = new Set(['Tax Lien', 'Tax Deed', 'Land Bank']);
const POLL_INTERVAL = 120000; // poll for remote changes every 2 minutes

// ── GitHub config ─────────────────────────────────────────────────────────────
const GITHUB_OWNER = 'rd703419';
const GITHUB_REPO  = 'fctl';
const EDITS_PATH   = 'data/user_edits.json';

let listings     = [];
let userEdits    = {};
let activeMarket = 'all';
let editId       = null;
let editsSha     = null;
let githubToken  = null;

// ── Token helpers ─────────────────────────────────────────────────────────────

function getToken() {
  return githubToken || localStorage.getItem('fctl_gh_token') || null;
}

function setSyncStatus(msg, color) {
  const el = document.getElementById('syncStatus');
  if (!el) return;
  el.textContent = msg;
  el.style.color = color === 'green' ? 'var(--green)'
                 : color === 'red'   ? 'var(--red)'
                 : color === 'amber' ? 'var(--amber)'
                 : 'var(--t3)';
}

// ── GitHub API ────────────────────────────────────────────────────────────────

async function ghGet(path) {
  try {
    const resp = await fetch(
      `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/contents/${path}`,
      { headers: { Accept: 'application/vnd.github.v3+json' } }
    );
    if (!resp.ok) return null;
    return resp.json();
  } catch (e) { return null; }
}

async function ghPut(path, content, sha, token) {
  const encoded = btoa(unescape(encodeURIComponent(JSON.stringify(content, null, 2))));
  const body = {
    message: `sync: update ${path} [${new Date().toISOString()}]`,
    content: encoded,
    sha,
  };
  const resp = await fetch(
    `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/contents/${path}`,
    {
      method:  'PUT',
      headers: {
        Authorization:  `token ${token}`,
        'Content-Type': 'application/json',
        Accept:         'application/vnd.github.v3+json',
      },
      body: JSON.stringify(body),
    }
  );
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.message || resp.statusText);
  }
  return resp.json();
}

// ── Remote edits ──────────────────────────────────────────────────────────────

async function fetchRemoteEdits() {
  const data = await ghGet(EDITS_PATH);
  if (!data) return {};
  try {
    editsSha = data.sha;
    const decoded = decodeURIComponent(escape(atob(data.content.replace(/\n/g, ''))));
    return JSON.parse(decoded);
  } catch (e) { return {}; }
}

function mergeEdits(local, remote) {
  const merged = { ...local, ...remote };
  Object.entries(remote).forEach(([id, val]) => {
    if (val._deleted) merged[id] = { _deleted: true };
  });
  return merged;
}

async function loadAndMergeRemoteEdits() {
  const remote = await fetchRemoteEdits();
  userEdits = mergeEdits(userEdits, remote);
  localStorage.setItem(STORE_KEY, JSON.stringify(userEdits));
}

async function saveEditsToGitHub() {
  const token = getToken();
  if (!token) {
    setSyncStatus('No token — local only', 'amber');
    return;
  }
  try {
    setSyncStatus('Saving...', 'amber');
    const latest = await ghGet(EDITS_PATH);
    const sha = latest ? latest.sha : editsSha;
    const result = await ghPut(EDITS_PATH, userEdits, sha, token);
    editsSha = result.content.sha;
    setSyncStatus('Synced ' + new Date().toLocaleTimeString(), 'green');
  } catch (e) {
    console.error('Sync failed:', e.message);
    setSyncStatus('Sync failed — saved locally', 'red');
  }
}

// ── Poll for remote changes every 2 minutes ───────────────────────────────────

async function pollRemoteChanges() {
  const data = await ghGet(EDITS_PATH);
  if (!data || data.sha === editsSha) return;
  editsSha = data.sha;
  try {
    const decoded = decodeURIComponent(escape(atob(data.content.replace(/\n/g, ''))));
    const remote  = JSON.parse(decoded);
    userEdits = mergeEdits(userEdits, remote);
    localStorage.setItem(STORE_KEY, JSON.stringify(userEdits));
    await fetchListings();
    render();
    setSyncStatus('Updated ' + new Date().toLocaleTimeString(), 'green');
  } catch (e) { /* silent */ }
}

// ── Init ──────────────────────────────────────────────────────────────────────

async function init() {
  githubToken = localStorage.getItem('fctl_gh_token') || null;

  try {
    const raw = localStorage.getItem(STORE_KEY);
    userEdits = raw ? JSON.parse(raw) : {};
  } catch (e) { userEdits = {}; }

  await loadAndMergeRemoteEdits();
  await fetchListings();
  render();
  setupListeners();

  if (!githubToken) {
    setSyncStatus('No token — read-only sync', 'amber');
  } else {
    setSyncStatus('Sync ready', 'green');
  }

  setInterval(pollRemoteChanges, POLL_INTERVAL);
}

// ── Fetch scraped listings ────────────────────────────────────────────────────

async function fetchListings() {
  try {
    const url  = DATA_URL + '?t=' + Math.floor(Date.now() / 60000);
    const resp = await fetch(url);
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const scraped = await resp.json();

    const byId = {};
    scraped.forEach(r => { byId[r.id] = r; });

    Object.entries(userEdits).forEach(([id, edits]) => {
      if (edits._deleted) return;
      if (byId[id]) byId[id] = { ...byId[id], ...edits };
      else byId[id] = edits;
    });

    listings = Object.values(byId).filter(r => !userEdits[r.id]?._deleted);

    const el = document.getElementById('lastScraped');
    if (el && scraped[0]?.scraped) el.textContent = 'Last scraped ' + scraped[0].scraped;
  } catch (e) {
    console.warn('listings.json unavailable:', e.message);
    listings = Object.values(userEdits).filter(r => !r._deleted);
    setSyncStatus('Offline — local data only', 'amber');
  }
}

// ── Save (local + GitHub) ─────────────────────────────────────────────────────

async function saveUserEdits() {
  localStorage.setItem(STORE_KEY, JSON.stringify(userEdits));
  const el = document.getElementById('savedAt');
  if (el) el.textContent = 'Saving...';
  await saveEditsToGitHub();
  if (el) el.textContent = 'Saved ' + new Date().toLocaleTimeString();
}

// ── Utilities ─────────────────────────────────────────────────────────────────

function uid() { return 'u' + Date.now() + Math.random().toString(36).slice(2,7); }

function fmtMoney(v) {
  if (!v && v !== 0) return '—';
  return '$' + parseInt(v).toLocaleString();
}

function fmtDate(s) {
  if (!s) return '—';
  const d = new Date(s + 'T12:00:00');
  return isNaN(d) ? s : d.toLocaleDateString('en-US', { month:'short', day:'numeric', year:'2-digit' });
}

function stageBadge(s) {
  const map = {
    'Pre-Foreclosure':'pre','Filing':'filing','Auction':'auction','REO':'reo',
    'Tax Lien':'taxlien','Tax Deed':'taxdeed','Land Bank':'landbank',
  };
  return `<span class="badge b-${map[s]||'filing'}">${s}</span>`;
}

// ── Filtering ─────────────────────────────────────────────────────────────────

function getFiltered() {
  const stage  = document.getElementById('fStage').value;
  const type   = document.getElementById('fType').value;
  const sort   = document.getElementById('fSort').value;
  const search = document.getElementById('fSearch').value.toLowerCase();

  let rows = listings.filter(r => {
    if (activeMarket !== 'all' && r.market !== activeMarket) return false;
    if (stage && r.stage !== stage) return false;
    if (type === 'foreclosure' && TAX_STAGES.has(r.stage)) return false;
    if (type === 'tax' && !TAX_STAGES.has(r.stage)) return false;
    if (search) {
      const hay = [r.address, r.zip, r.county, r.notes, r.source].join(' ').toLowerCase();
      if (!hay.includes(search)) return false;
    }
    return true;
  });

  if (sort === 'auction') {
    rows.sort((a,b) => {
      if (!a.auction && !b.auction) return 0;
      if (!a.auction) return 1;
      if (!b.auction) return -1;
      return a.auction.localeCompare(b.auction);
    });
  } else if (sort === 'value') {
    rows.sort((a,b) => (b.est_value||0)-(a.est_value||0));
  } else if (sort === 'county') {
    rows.sort((a,b) => (a.county||'').localeCompare(b.county||''));
  } else {
    rows.sort((a,b) => (b.filed||'').localeCompare(a.filed||''));
  }
  return rows;
}

// ── Render ────────────────────────────────────────────────────────────────────

function renderMetrics() {
  const today    = new Date().toISOString().slice(0,10);
  const taxR     = listings.filter(r => TAX_STAGES.has(r.stage));
  const fcR      = listings.filter(r => !TAX_STAGES.has(r.stage));
  const upcoming = listings.filter(r => r.auction && r.auction >= today);
  const cards = [
    { lbl:'Total listings',   val:listings.length,                                     cls:'',       accent:'' },
    { lbl:'Foreclosures',     val:fcR.length,                                          cls:'blue',   accent:'blue' },
    { lbl:'Tax sales',        val:taxR.length,                                         cls:'purple', accent:'purple' },
    { lbl:'Upcoming sales',   val:upcoming.length,                                     cls:'amber',  accent:'amber' },
    { lbl:'REO / bank-owned', val:listings.filter(r=>r.stage==='REO').length,          cls:'red',    accent:'red' },
    { lbl:'Land bank',        val:listings.filter(r=>r.stage==='Land Bank').length,    cls:'green',  accent:'green' },
  ];
  document.getElementById('metricsRow').innerHTML = cards.map(c=>`
    <div class="metric" data-accent="${c.accent}">
      <div class="metric-lbl">${c.lbl}</div>
      <div class="metric-val ${c.cls}">${c.val}</div>
    </div>`).join('');
}

function renderTable() {
  const rows  = getFiltered();
  const today = new Date().toISOString().slice(0,10);
  document.getElementById('rowCount').textContent = rows.length + ' listing' + (rows.length!==1?'s':'');

  if (!rows.length) {
    document.getElementById('tbody').innerHTML =
      '<tr><td colspan="11" class="empty">No listings match your filters.</td></tr>';
    return;
  }

  document.getElementById('tbody').innerHTML = rows.map(r => {
    const soonCls = r.auction && r.auction >= today ? 'date-soon' : '';
    const taxSub  = TAX_STAGES.has(r.stage) && r.tax_owed
      ? `<span class="addr-tax">Owed ${fmtMoney(r.tax_owed)}${r.redemption_period?' · '+r.redemption_period:''}</span>`
      : '';
    const linkBtn = r.url
      ? `<button class="act link" onclick="window.open(decodeURIComponent('${encodeURIComponent(r.url)}'),'_blank')">↗ Link</button>`
      : '';
    const zest = r.zestimate       ? fmtMoney(r.zestimate)       : '—';
    const z60  = r.zestimate_60pct ? fmtMoney(r.zestimate_60pct) : '—';

    return `<tr>
      <td><div class="addr-wrap"><span class="addr-main" title="${r.address}">${r.address}</span>${taxSub}</div></td>
      <td>${r.county||'—'}</td>
      <td>${stageBadge(r.stage)}</td>
      <td class="date-cell">${fmtDate(r.filed)}</td>
      <td class="date-cell ${soonCls}">${fmtDate(r.auction)}</td>
      <td class="mono-cell">${fmtMoney(r.est_value)}</td>
      <td class="mono-cell"
