// app.js — FCTL Foreclosure + Tax Sale Tracker

const STORE_KEY  = 'fctl_v2';
const DATA_URL   = 'data/listings.json';
const TAX_STAGES = new Set(['Tax Lien', 'Tax Deed', 'Land Bank']);

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
  try {
    const url = DATA_URL + '?t=' + Date.now();
    const resp = await fetch(url, { cache: 'no-store' });
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const scraped = await resp.json();

    const byId = {};
    scraped.forEach(r => { byId[r.id] = r; });

    Object.entries(userEdits).forEach(([id, edits]) => {
      if (edits._deleted) return;
      if (byId[id]) {
        byId[id] = { ...byId[id], ...edits };
      } else {
        byId[id] = edits;
      }
    });

    listings = Object.values(byId).filter(r => !userEdits[r.id]?._deleted);

    const syncEl = document.getElementById('syncStatus');
    const scraped0 = scraped[0];
    if (syncEl && scraped0?.scraped) {
      syncEl.textContent = 'Last scraped ' + scraped0.scraped;
    }
  } catch (e) {
    console.warn('Could not fetch listings.json, usin
