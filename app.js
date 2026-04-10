// app.js — FCTL Foreclosure + Tax Sale Tracker

const STORE_KEY  = 'fctl_v2';
const DATA_URL   = 'data/listings.json';
const TAX_STAGES = new Set(['Tax Lien', 'Tax Deed', 'Land Bank']);

let listings     = [];
let userEdits    = {};   // id → merged user fields
let activeMarket = 'all';
let editId       = null;

// ── Data loading ────────────────────────────────────────────────────────────
// Strategy:
//   1. Fetch data/listings.json (auto-updated by GitHub Actions every 6h)
//   2. Merge with any user-added/edited records from localStorage
//   3. Fall back to localStorage only if fetch fails (offline)

async function init() {
  loadUserEdits();
  await fetchListings();
  render();
  setupListeners();
}

function loadUserEdits() {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    userEdits = raw ? JSON.parse(raw) : {};
  } catch (e) {
    userEdits = {};
  }
}

async function fetchListings() {
  try {
    // Add cache-busting so GitHub Pages serves fresh data
    const url = DATA_URL + '?t=' + Math.floor(Date.now() / 60000);
    const resp = await fetch(url);
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const scraped = await resp.json();

    // Merge scraped data with user edits/additions
    const byId = {};
    scraped.forEach(r => { byId[r.id] = r; });

    // Apply user overrides (edits to scraped records)
    Object.entries(userEdits).forEach(([id, edits]) => {
      if (edits._deleted) return;
      if (byId[id]) {
        byId[id] = { ...byId[id], ...edits };
      } else {
        // User-added records not in scraped data
        byId[id] = edits;
      }
    });

    // Filter out user-deleted records
    listings = Object.values(byId).filter(r => !userEdits[r.id]?._deleted);

    const syncEl = document.getElementById('syncStatus');
    const scraped0 = scraped[0];
    if (syncEl && scraped0?.scraped) {
      syncEl.textContent = 'Last scraped ' + scraped0.scraped;
    }
  } catch (e) {
    console.warn('Could not fetch listings.json, using local data:', e.message);
    // Offline fallback — reconstruct from userEdits
    listings = Object.values(userEdits).filter(r => !r._deleted);
    const syncEl = document.getElementById('syncStatus');
    if (syncEl) syncEl.textContent = 'Offline — showing local data';
  }
}

function saveUserEdits() {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(userEdits));
    const el = document.getElementById('savedAt');
    if (el) el.textContent = 'Saved ' + new Date().toLocaleTimeString();
  } catch (e) {}
}

// ── Utilities ───────────────────────────────────────────────────────────────

function uid() {
  return 'u' + Date.now() + Math.random().toString(36).slice(2, 7);
}

function fmtMoney(v) {
  if (!v && v !== 0) return '—';
  return '$' + parseInt(v).toLocaleString();
}

function fmtDate(s) {
  if (!s) return '—';
  const d = new Date(s + 'T12:00:00');
  return isNaN(d) ? s : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' });
}

function stageBadge(s) {
  const map = {
    'Pre-Foreclosure': 'pre',
    'Filing':          'filing',
    'Auction':         'auction',
    'REO':             'reo',
    'Tax Lien':        'taxlien',
    'Tax Deed':        'taxdeed',
    'Land Bank':       'landbank',
  };
  return `<span class="badge b-${map[s] || 'filing'}">${s}</span>`;
}

// ── Filtering ────────────────────────────────────────────────────────────────

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
    rows.sort((a, b) => {
      if (!a.auction && !b.auction) return 0;
      if (!a.auction) return 1;
      if (!b.auction) return -1;
      return a.auction.localeCompare(b.auction);
    });
  } else if (sort === 'value') {
    rows.sort((a, b) => (b.est_value || 0) - (a.est_value || 0));
  } else if (sort === 'county') {
    rows.sort((a, b) => (a.county || '').localeCompare(b.county || ''));
  } else {
    rows.sort((a, b) => (b.filed || '').localeCompare(a.filed || ''));
  }

  return rows;
}

// ── Render ───────────────────────────────────────────────────────────────────

function renderMetrics() {
  const today  = new Date().toISOString().slice(0, 10);
  const taxR   = listings.filter(r => TAX_STAGES.has(r.stage));
  const fcR    = listings.filter(r => !TAX_STAGES.has(r.stage));
  const upcoming = listings.filter(r => r.auction && r.auction >= today);

  const cards = [
    { lbl: 'Total listings',   val: listings.length,                               cls: '',       accent: '' },
    { lbl: 'Foreclosures',     val: fcR.length,                                    cls: 'blue',   accent: 'blue' },
    { lbl: 'Tax sales',        val: taxR.length,                                   cls: 'purple', accent: 'purple' },
    { lbl: 'Upcoming sales',   val: upcoming.length,                               cls: 'amber',  accent: 'amber' },
    { lbl: 'REO / bank-owned', val: listings.filter(r => r.stage === 'REO').length, cls: 'red',   accent: 'red' },
    { lbl: 'Land bank',        val: listings.filter(r => r.stage === 'Land Bank').length, cls: 'green', accent: 'green' },
  ];

  document.getElementById('metricsRow').innerHTML = cards.map(c => `
    <div class="metric" data-accent="${c.accent}">
      <div class="metric-lbl">${c.lbl}</div>
      <div class="metric-val ${c.cls}">${c.value !== undefined ? c.value : c.val}</div>
    </div>`).join('');
}

function renderTable() {
  const rows  = getFiltered();
  const today = new Date().toISOString().slice(0, 10);

  document.getElementById('rowCount').textContent =
    rows.length + ' listing' + (rows.length !== 1 ? 's' : '');

  if (!rows.length) {
    document.getElementById('tbody').innerHTML =
      '<tr><td colspan="9" class="empty">No listings match your filters.</td></tr>';
    return;
  }

  document.getElementById('tbody').innerHTML = rows.map(r => {
    const soonCls = r.auction && r.auction >= today ? 'date-soon' : '';
    const taxSub  = TAX_STAGES.has(r.stage) && r.tax_owed
      ? `<span class="addr-tax">Owed ${fmtMoney(r.tax_owed)}${r.redemption_period ? ' · ' + r.redemption_period : ''}</span>`
      : '';
    const linkBtn = r.url
      ? `<button class="act link" onclick="window.open(decodeURIComponent('${encodeURIComponent(r.url)}'),'_blank')">↗ Link</button>`
      : '';

    return `<tr>
      <td>
        <div class="addr-wrap">
          <span class="addr-main" title="${r.address}">${r.address}</span>
          ${taxSub}
        </div>
      </td>
      <td>${r.county || '—'}</td>
      <td>${stageBadge(r.stage)}</td>
      <td class="date-cell">${fmtDate(r.filed)}</td>
      <td class="date-cell ${soonCls}">${fmtDate(r.auction)}</td>
      <td class="mono-cell">${fmtMoney(r.est_value)}</td>
      <td class="mono-cell" style="color:var(--purple)">${r.tax_owed ? fmtMoney(r.tax_owed) : '—'}</td>
      <td><span class="src-chip" title="${r.source || ''}">${r.source || '—'}</span></td>
      <td>
        <div class="row-acts">
          ${linkBtn}
          <button class="act" onclick="editListing('${r.id}')">Edit</button>
          <button class="act del" onclick="deleteListing('${r.id}')">Del</button>
        </div>
      </td>
    </tr>`;
  }).join('');
}

function render() {
  renderMetrics();
  renderTable();
}

// ── Listeners ────────────────────────────────────────────────────────────────

function setupListeners() {
  // Market tabs
  document.getElementById('marketTabs').addEventListener('click', e => {
    const tab = e.target.closest('.mtab');
    if (!tab) return;
    document.querySelectorAll('.mtab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    activeMarket = tab.dataset.market;
    render();
  });

  // Filters
  ['fStage','fType','fSort'].forEach(id =>
    document.getElementById(id).addEventListener('change', render)
  );
  document.getElementById('fSearch').addEventListener('input', render);

  // Stage → show/hide tax fields
  document.getElementById('fStageIn').addEventListener('change', function() {
    document.getElementById('taxSection').classList.toggle('visible', TAX_STAGES.has(this.value));
  });

  // Overlay close on background click
  document.getElementById('addModal').addEventListener('click', e => {
    if (e.target.id === 'addModal') closeModal();
  });
  document.getElementById('importModal').addEventListener('click', e => {
    if (e.target.id === 'importModal') closeImport();
  });

  // Keyboard
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') { closeModal(); closeImport(); }
    if ((e.metaKey || e.ctrlKey) && e.key === 'n') { e.preventDefault(); openAdd(); }
  });

  // Drag-and-drop CSV
  document.addEventListener('dragover', e => e.preventDefault());
  document.addEventListener('drop', e => {
    e.preventDefault();
    const file = e.dataTransfer?.files?.[0];
    if (!file || !file.name.endsWith('.csv')) return;
    const reader = new FileReader();
    reader.onload = ev => {
      document.getElementById('importText').value = ev.target.result;
      openImport();
    };
    reader.readAsText(file);
  });
}

// ── Add / Edit ───────────────────────────────────────────────────────────────

function openAdd() {
  editId = null;
  document.getElementById('modalTitle').textContent = 'Add listing';
  ['fAddress','fZip','fCounty','fSource','fUrl','fNotes','fValue','fTaxOwed','fRedemption','fTaxRate']
    .forEach(id => { document.getElementById(id).value = ''; });
  document.getElementById('fFiled').value   = new Date().toISOString().slice(0, 10);
  document.getElementById('fAuction').value = '';
  document.getElementById('fStageIn').value = 'Pre-Foreclosure';
  document.getElementById('fMarket').value  = activeMarket === 'all' ? 'lucas' : activeMarket;
  document.getElementById('taxSection').classList.remove('visible');
  document.getElementById('addModal').classList.add('open');
}

function editListing(id) {
  const r = listings.find(l => l.id === id);
  if (!r) return;
  editId = id;
  document.getElementById('modalTitle').textContent = 'Edit listing';
  document.getElementById('fAddress').value    = r.address || '';
  document.getElementById('fZip').value        = r.zip || '';
  document.getElementById('fCounty').value     = r.county || '';
  document.getElementById('fMarket').value     = r.market || 'lucas';
  document.getElementById('fStageIn').value    = r.stage || 'Pre-Foreclosure';
  document.getElementById('fSource').value     = r.source || '';
  document.getElementById('fFiled').value      = r.filed || '';
  document.getElementById('fAuction').value    = r.auction || '';
  document.getElementById('fValue').value      = r.est_value || '';
  document.getElementById('fUrl').value        = r.url || '';
  document.getElementById('fNotes').value      = r.notes || '';
  document.getElementById('fTaxOwed').value    = r.tax_owed || '';
  document.getElementById('fRedemption').value = r.redemption_period || '';
  document.getElementById('fTaxRate').value    = r.tax_rate || '';
  document.getElementById('taxSection').classList.toggle('visible', TAX_STAGES.has(r.stage));
  document.getElementById('addModal').classList.add('open');
}

function saveListing() {
  const addr = document.getElementById('fAddress').value.trim();
  if (!addr) { alert('Address is required.'); return; }

  const id  = editId || uid();
  const rec = {
    id,
    address:          addr,
    zip:              document.getElementById('fZip').value.trim(),
    county:           document.getElementById('fCounty').value.trim(),
    market:           document.getElementById('fMarket').value,
    stage:            document.getElementById('fStageIn').value,
    source:           document.getElementById('fSource').value.trim(),
    filed:            document.getElementById('fFiled').value,
    auction:          document.getElementById('fAuction').value || null,
    est_value:        parseInt(document.getElementById('fValue').value) || null,
    url:              document.getElementById('fUrl').value.trim(),
    notes:            document.getElementById('fNotes').value.trim(),
    tax_owed:         parseInt(document.getElementById('fTaxOwed').value) || null,
    redemption_period: document.getElementById('fRedemption').value.trim(),
    tax_rate:         parseFloat(document.getElementById('fTaxRate').value) || null,
    scraped:          new Date().toISOString().slice(0, 10),
  };

  // Save to userEdits (persists across scraper updates)
  userEdits[id] = rec;
  saveUserEdits();

  // Update in-memory listings
  const idx = listings.findIndex(l => l.id === id);
  if (idx >= 0) listings[idx] = rec;
  else listings.unshift(rec);

  render();
  closeModal();
}

function deleteListing(id) {
  if (!confirm('Delete this listing?')) return;
  userEdits[id] = { _deleted: true };
  saveUserEdits();
  listings = listings.filter(l => l.id !== id);
  render();
}

function closeModal() {
  document.getElementById('addModal').classList.remove('open');
  editId = null;
}

// ── Import / Export ──────────────────────────────────────────────────────────

function openImport() {
  document.getElementById('importText').value = '';
  document.getElementById('importModal').classList.add('open');
}

function closeImport() {
  document.getElementById('importModal').classList.remove('open');
}

function doImport() {
  const raw = document.getElementById('importText').value.trim();
  if (!raw) return;

  const lines = raw.split('\n').filter(l => l.trim());
  let added = 0;

  lines.forEach((line, i) => {
    if (i === 0 && line.toLowerCase().includes('address')) return;
    const p = line.split(',').map(x => x.trim().replace(/^"|"$/g, ''));
    if (!p[0]) return;

    const id  = uid();
    const rec = {
      id,
      address:          p[0],
      zip:              p[1] || '',
      county:           p[2] || '',
      market:           (p[3] || 'lucas').toLowerCase().includes('dmv') ? 'dmv' : 'lucas',
      stage:            p[4] || 'Filing',
      filed:            p[5] || '',
      auction:          p[6] || null,
      est_value:        parseInt(p[7]) || null,
      source:           p[8] || '',
      url:              p[9] || '',
      notes:            p[10] || '',
      tax_owed:         parseInt(p[11]) || null,
      redemption_period: p[12] || '',
      tax_rate:         parseFloat(p[13]) || null,
      scraped:          new Date().toISOString().slice(0, 10),
    };

    userEdits[id] = rec;
    listings.unshift(rec);
    added++;
  });

  saveUserEdits();
  render();
  closeImport();
  if (added) alert(added + ' listing' + (added !== 1 ? 's' : '') + ' imported.');
}

function exportCSV() {
  const headers = [
    'address','zip','county','market','stage','filed','auction',
    'est_value','source','url','notes','tax_owed','redemption_period','tax_rate'
  ];
  const rows = listings.map(r =>
    headers.map(h => `"${(r[h] || '').toString().replace(/"/g, '""')}"`).join(',')
  );
  const csv = [headers.join(','), ...rows].join('\n');
  const a   = document.createElement('a');
  a.href    = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv);
  a.download = 'fctl-export-' + new Date().toISOString().slice(0, 10) + '.csv';
  a.click();
}

// ── Start ─────────────────────────────────────────────────────────────────────

init();
