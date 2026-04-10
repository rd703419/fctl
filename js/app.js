// app.js — FCTL Foreclosure + Tax Sale Tracker

const STORE_KEY  = 'fctl_v2';
const TAX_STAGES = new Set(['Tax Lien', 'Tax Deed', 'Land Bank']);

const SEED = [
  {"id":"s1","address":"4821 Secor Rd","zip":"43623","county":"Lucas","market":"lucas","stage":"Auction","filed":"2025-10-14","auction":"2026-04-18","est_value":87000,"source":"Lucas Co. Sheriff","url":"https://www.lucascountysheriff.org/civil/sheriff-sales","notes":"","tax_owed":null,"redemption_period":"","tax_rate":null},
  {"id":"s2","address":"1143 Bancroft St","zip":"43607","county":"Lucas","market":"lucas","stage":"Filing","filed":"2026-01-22","auction":null,"est_value":63000,"source":"Lucas Co. Auditor","url":"","notes":"","tax_owed":null,"redemption_period":"","tax_rate":null},
  {"id":"s3","address":"3302 Lagrange St","zip":"43608","county":"Lucas","market":"lucas","stage":"Pre-Foreclosure","filed":"2026-03-01","auction":null,"est_value":55000,"source":"ATTOM Data","url":"","notes":"","tax_owed":null,"redemption_period":"","tax_rate":null},
  {"id":"s4","address":"710 Fulton St","zip":"43605","county":"Lucas","market":"lucas","stage":"REO","filed":"2025-09-30","auction":null,"est_value":47500,"source":"Fannie Mae HomePath","url":"https://www.homepath.com","notes":"","tax_owed":null,"redemption_period":"","tax_rate":null},
  {"id":"s5","address":"214 Oak St","zip":"43604","county":"Lucas","market":"lucas","stage":"Tax Lien","filed":"2026-01-10","auction":"2026-06-05","est_value":52000,"source":"Lucas Co. Treasurer","url":"https://co.lucas.oh.us/treasurer","notes":"Delinquent since 2023. Verify IRS liens.","tax_owed":3800,"redemption_period":"1 year","tax_rate":18},
  {"id":"s6","address":"918 Collingwood Blvd","zip":"43612","county":"Lucas","market":"lucas","stage":"Tax Deed","filed":"2025-11-15","auction":"2026-04-30","est_value":41000,"source":"Lucas Co. Treasurer","url":"","notes":"Redemption period expired.","tax_owed":7200,"redemption_period":"Expired","tax_rate":18},
  {"id":"s7","address":"3238 Van Fleet Pkwy","zip":"43617","county":"Lucas","market":"lucas","stage":"Land Bank","filed":"2026-02-01","auction":null,"est_value":68000,"source":"Toledo Land Bank","url":"https://www.toledolucascountylandbank.com","notes":"Rehabbed. Sylvania Schools district.","tax_owed":null,"redemption_period":"","tax_rate":null},
  {"id":"s8","address":"5718 Glendale Ave","zip":"43614","county":"Lucas","market":"lucas","stage":"Auction","filed":"2025-11-11","auction":"2026-04-25","est_value":101000,"source":"Lucas Co. Sheriff","url":"https://www.lucascountysheriff.org/civil/sheriff-sales","notes":"","tax_owed":null,"redemption_period":"","tax_rate":null},
  {"id":"s9","address":"8823 Gate House Rd","zip":"22079","county":"Fairfax","market":"dmv","stage":"Auction","filed":"2025-12-05","auction":"2026-04-22","est_value":498000,"source":"Fairfax Circuit Ct.","url":"https://icare.fairfaxcounty.gov","notes":"","tax_owed":null,"redemption_period":"","tax_rate":null},
  {"id":"s10","address":"1102 Lamont St NW","zip":"20010","county":"DC","market":"dmv","stage":"Filing","filed":"2026-01-30","auction":null,"est_value":785000,"source":"ATTOM Data","url":"","notes":"","tax_owed":null,"redemption_period":"","tax_rate":null},
  {"id":"s11","address":"421 N Glebe Rd #405","zip":"22203","county":"Arlington","market":"dmv","stage":"REO","filed":"2025-08-15","auction":null,"est_value":412000,"source":"Fannie Mae HomePath","url":"https://www.homepath.com","notes":"","tax_owed":null,"redemption_period":"","tax_rate":null},
  {"id":"s12","address":"9024 Liberia Ave","zip":"20110","county":"Manassas","market":"dmv","stage":"Pre-Foreclosure","filed":"2026-02-28","auction":null,"est_value":331000,"source":"ATTOM Data","url":"","notes":"","tax_owed":null,"redemption_period":"","tax_rate":null},
  {"id":"s13","address":"302 Battlefield Pkwy","zip":"20176","county":"Loudoun","market":"dmv","stage":"Auction","filed":"2025-11-20","auction":"2026-05-07","est_value":617000,"source":"Loudoun Co. Records","url":"","notes":"","tax_owed":null,"redemption_period":"","tax_rate":null},
  {"id":"s14","address":"4402 8th St NE","zip":"20017","county":"DC","market":"dmv","stage":"Tax Lien","filed":"2026-02-15","auction":"2026-07-18","est_value":620000,"source":"DC OTR","url":"https://otr.cfo.dc.gov/page/tax-sale","notes":"DC annual tax lien sale.","tax_owed":12400,"redemption_period":"6 months","tax_rate":18},
  {"id":"s15","address":"11203 Veirs Mill Rd","zip":"20902","county":"Montgomery MD","market":"dmv","stage":"Tax Deed","filed":"2025-10-20","auction":"2026-05-12","est_value":389000,"source":"Montgomery Co. Finance","url":"https://www.montgomerycountymd.gov/finance/tax-sale.html","notes":"Check IRS/municipal liens before bidding.","tax_owed":18700,"redemption_period":"Expired","tax_rate":6}
];

let listings     = [];
let userEdits    = {};
let activeMarket = 'all';
let editId       = null;

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
  let scraped = SEED;

  try {
    const resp = await fetch('data/listings.json?t=' + Date.now(), { cache: 'no-store' });
    if (resp.ok) {
      const json = await resp.json();
      if (Array.isArray(json) && json.length > 0) {
        scraped = json;
        const syncEl = document.getElementById('syncStatus');
        if (syncEl && json[0]?.scraped) syncEl.textContent = 'Last scraped ' + json[0].scraped;
      }
    }
  } catch (e) {
    console.warn('Using seed data:', e.message);
  }

  const byId = {};
  scraped.forEach(r => { byId[r.id] = r; });
  Object.entries(userEdits).forEach(([id, edits]) => {
    if (edits._deleted) return;
    if (byId[id]) byId[id] = { ...byId[id], ...edits };
    else byId[id] = edits;
  });
  listings = Object.values(byId).filter(r => !userEdits[r.id]?._deleted);
}

function saveUserEdits() {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(userEdits));
    const el = document.getElementById('savedAt');
    if (el) el.textContent = 'Saved ' + new Date().toLocaleTimeString();
  } catch (e) {}
}

function uid() { return 'u' + Date.now() + Math.random().toString(36).slice(2, 7); }
function fmtMoney(v) { if (!v && v !== 0) return '—'; return '$' + parseInt(v).toLocaleString(); }
function fmtDate(s) {
  if (!s) return '—';
  const d = new Date(s + 'T12:00:00');
  return isNaN(d) ? s : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' });
}
function stageBadge(s) {
  const map = {'Pre-Foreclosure':'pre','Filing':'filing','Auction':'auction','REO':'reo','Tax Lien':'taxlien','Tax Deed':'taxdeed','Land Bank':'landbank'};
  return `<span class="badge b-${map[s]||'filing'}">${s}</span>`;
}

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
  if (sort === 'auction') rows.sort((a,b) => { if (!a.auction&&!b.auction) return 0; if (!a.auction) return 1; if (!b.auction) return -1; return a.auction.localeCompare(b.auction); });
  else if (sort === 'value') rows.sort((a,b) => (b.est_value||0)-(a.est_value||0));
  else if (sort === 'county') rows.sort((a,b) => (a.county||'').localeCompare(b.county||''));
  else rows.sort((a,b) => (b.filed||'').localeCompare(a.filed||''));
  return rows;
}

function renderMetrics() {
  const today = new Date().toISOString().slice(0,10);
  const taxR  = listings.filter(r => TAX_STAGES.has(r.stage));
  const fcR   = listings.filter(r => !TAX_STAGES.has(r.stage));
  const cards = [
    {lbl:'Total listings',  val:listings.length,                                       cls:'',       accent:''},
    {lbl:'Foreclosures',    val:fcR.length,                                            cls:'blue',   accent:'blue'},
    {lbl:'Tax sales',       val:taxR.length,                                           cls:'purple', accent:'purple'},
    {lbl:'Upcoming sales',  val:listings.filter(r=>r.auction&&r.auction>=today).length,cls:'amber',  accent:'amber'},
    {lbl:'REO / bank-owned',val:listings.filter(r=>r.stage==='REO').length,            cls:'red',    accent:'red'},
    {lbl:'Land bank',       val:listings.filter(r=>r.stage==='Land Bank').length,      cls:'green',  accent:'green'},
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
  if (!rows.length) { document.getElementById('tbody').innerHTML='<tr><td colspan="9" class="empty">No listings match your filters.</td></tr>'; return; }
  document.getElementById('tbody').innerHTML = rows.map(r => {
    const soonCls = r.auction && r.auction >= today ? 'date-soon' : '';
    const taxSub  = TAX_STAGES.has(r.stage) && r.tax_owed ? `<span class="addr-tax">Owed ${fmtMoney(r.tax_owed)}${r.redemption_period?' · '+r.redemption_period:''}</span>` : '';
    const linkBtn = r.url ? `<button class="act link" onclick="window.open(decodeURIComponent('${encodeURIComponent(r.url)}'),'_blank')">↗ Link</button>` : '';
    return `<tr>
      <td><div class="addr-wrap"><span class="addr-main" title="${r.address}">${r.address}</span>${taxSub}</div></td>
      <td>${r.county||'—'}</td>
      <td>${stageBadge(r.stage)}</td>
      <td class="date-cell">${fmtDate(r.filed)}</td>
      <td class="date-cell ${soonCls}">${fmtDate(r.auction)}</td>
      <td class="mono-cell">${fmtMoney(r.est_value)}</td>
      <td class="mono-cell" style="color:var(--purple)">${r.tax_owed?fmtMoney(r.tax_owed):'—'}</td>
      <td><span class="src-chip" title="${r.source||''}">${r.source||'—'}</span></td>
      <td><div class="row-acts">${linkBtn}<button class="act" onclick="editListing('${r.id}')">Edit</button><button class="act del" onclick="deleteListing('${r.id}')">Del</button></div></td>
    </tr>`;
  }).join('');
}

function render() { renderMetrics(); renderTable(); }

function setupListeners() {
  document.getElementById('marketTabs').addEventListener('click', e => {
    const tab = e.target.closest('.mtab');
    if (!tab) return;
    document.querySelectorAll('.mtab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    activeMarket = tab.dataset.market;
    render();
  });
  ['fStage','fType','fSort'].forEach(id => document.getElementById(id).addEventListener('change', render));
  document.getElementById('fSearch').addEventListener('input', render);
  document.getElementById('fStageIn').addEventListener('change', function() {
    document.getElementById('taxSection').classList.toggle('visible', TAX_STAGES.has(this.value));
  });
  document.getElementById('addModal').addEventListener('click', e => { if (e.target.id==='addModal') closeModal(); });
  document.getElementById('importModal').addEventListener('click', e => { if (e.target.id==='importModal') closeImport(); });
  document.addEventListener('keydown', e => {
    if (e.key==='Escape') { closeModal(); closeImport(); }
    if ((e.metaKey||e.ctrlKey) && e.key==='n') { e.preventDefault(); openAdd(); }
  });
  document.addEventListener('dragover', e => e.preventDefault());
  document.addEventListener('drop', e => {
    e.preventDefault();
    const file = e.dataTransfer?.files?.[0];
    if (!file||!file.name.endsWith('.csv')) return;
    const reader = new FileReader();
    reader.onload = ev => { document.getElementById('importText').value = ev.target.result; openImport(); };
    reader.readAsText(file);
  });
}

function openAdd() {
  editId = null;
  document.getElementById('modalTitle').textContent = 'Add listing';
  ['fAddress','fZip','fCounty','fSource','fUrl','fNotes','fValue','fTaxOwed','fRedemption','fTaxRate'].forEach(id => { document.getElementById(id).value=''; });
  document.getElementById('fFiled').value   = new Date().toISOString().slice(0,10);
  document.getElementById('fAuction').value = '';
  document.getElementById('fStageIn').value = 'Pre-Foreclosure';
  document.getElementById('fMarket').value  = activeMarket==='all'?'lucas':activeMarket;
  document.getElementById('taxSection').classList.remove('visible');
  document.getElementById('addModal').classList.add('open');
}

function editListing(id) {
  const r = listings.find(l => l.id===id);
  if (!r) return;
  editId = id;
  document.getElementById('modalTitle').textContent = 'Edit listing';
  document.getElementById('fAddress').value    = r.address||'';
  document.getElementById('fZip').value        = r.zip||'';
  document.getElementById('fCounty').value     = r.county||'';
  document.getElementById('fMarket').value     = r.market||'lucas';
  document.getElementById('fStageIn').value    = r.stage||'Pre-Foreclosure';
  document.getElementById('fSource').value     = r.source||'';
  document.getElementById('fFiled').value      = r.filed||'';
  document.getElementById('fAuction').value    = r.auction||'';
  document.getElementById('fValue').value      = r.est_value||'';
  document.getElementById('fUrl').value        = r.url||'';
  document.getElementById('fNotes').value      = r.notes||'';
  document.getElementById('fTaxOwed').value    = r.tax_owed||'';
  document.getElementById('fRedemption').value = r.redemption_period||'';
  document.getElementById('fTaxRate').value    = r.tax_rate||'';
  document.getElementById('taxSection').classList.toggle('visible', TAX_STAGES.has(r.stage));
  document.getElementById('addModal').classList.add('open');
}

function saveListing() {
  const addr = document.getElementById('fAddress').value.trim();
  if (!addr) { alert('Address is required.'); return; }
  const id  = editId || uid();
  const rec = {
    id, address:addr,
    zip:              document.getElementById('fZip').value.trim(),
    county:           document.getElementById('fCounty').value.trim(),
    market:           document.getElementById('fMarket').value,
    stage:            document.getElementById('fStageIn').value,
    source:           document.getElementById('fSource').value.trim(),
    filed:            document.getElementById('fFiled').value,
    auction:          document.getElementById('fAuction').value||null,
    est_value:        parseInt(document.getElementById('fValue').value)||null,
    url:              document.getElementById('fUrl').value.trim(),
    notes:            document.getElementById('fNotes').value.trim(),
    tax_owed:         parseInt(document.getElementById('fTaxOwed').value)||null,
    redemption_period:document.getElementById('fRedemption').value.trim(),
    tax_rate:         parseFloat(document.getElementById('fTaxRate').value)||null,
    scraped:          new Date().toISOString().slice(0,10),
  };
  userEdits[id] = rec;
  saveUserEdits();
  const idx = listings.findIndex(l => l.id===id);
  if (idx>=0) listings[idx]=rec; else listings.unshift(rec);
  render();
  closeModal();
}

function deleteListing(id) {
  if (!confirm('Delete this listing?')) return;
  userEdits[id] = { _deleted: true };
  saveUserEdits();
  listings = listings.filter(l => l.id!==id);
  render();
}

function closeModal() { document.getElementById('addModal').classList.remove('open'); editId=null; }
function openImport() { document.getElementById('importText').value=''; document.getElementById('importModal').classList.add('open'); }
function closeImport() { document.getElementById('importModal').classList.remove('open'); }

function doImport() {
  const raw = document.getElementById('importText').value.trim();
  if (!raw) return;
  const lines = raw.split('\n').filter(l=>l.trim());
  let added = 0;
  lines.forEach((line,i) => {
    if (i===0 && line.toLowerCase().includes('address')) return;
    const p = line.split(',').map(x=>x.trim().replace(/^"|"$/g,''));
    if (!p[0]) return;
    const id = uid();
    const rec = {id,address:p[0],zip:p[1]||'',county:p[2]||'',market:(p[3]||'lucas').toLowerCase().includes('dmv')?'dmv':'lucas',stage:p[4]||'Filing',filed:p[5]||'',auction:p[6]||null,est_value:parseInt(p[7])||null,source:p[8]||'',url:p[9]||'',notes:p[10]||'',tax_owed:parseInt(p[11])||null,redemption_period:p[12]||'',tax_rate:parseFloat(p[13])||null,scraped:new Date().toISOString().slice(0,10)};
    userEdits[id]=rec; listings.unshift(rec); added++;
  });
  saveUserEdits(); render(); closeImport();
  if (added) alert(added+' listing'+(added!==1?'s':'')+' imported.');
}

function exportCSV() {
  const headers=['address','zip','county','market','stage','filed','auction','est_value','source','url','notes','tax_owed','redemption_period','tax_rate'];
  const rows=listings.map(r=>headers.map(h=>`"${(r[h]||'').toString().replace(/"/g,'""')}"`).join(','));
  const csv=[headers.join(','),...rows].join('\n');
  const a=document.createElement('a');
  a.href='data:text/csv;charset=utf-8,'+encodeURIComponent(csv);
  a.download='fctl-export-'+new Date().toISOString().slice(0,10)+'.csv';
  a.click();
}

init();
