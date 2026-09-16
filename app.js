/* Faisal's London - app logic.
   Pin data is fetched from pins.json so the Phase 2 automation only ever rewrites that
   one file (DECISIONS.md D-003). */
'use strict';

const LONDON = [51.5074, -0.1278];
const LABEL_ZOOM = 15;      // below this, pins render icon-only - 450 labels at once is soup
const VIEWPORT_PAD = 0.25;  // render a little beyond the viewport so panning doesn't pop

const CATS = {
  'restaurant/food': { label: 'Eat & drink', varName: '--food', short: 'Food' },
  'activity':        { label: 'Things to do', varName: '--activity', short: 'Do' },
  'other':           { label: 'Other', varName: '--other', short: 'Other' },
};

const GLYPH = {
  'restaurant/food': '<path d="M6 3v18M6 3c-1.4 0-2.4 1.2-2.4 3v3.2c0 1.1.9 2 2.4 2s2.4-.9 2.4-2V6c0-1.8-1-3-2.4-3z"/><path d="M17.6 3c-1.6 1-2.6 3-2.6 5.4 0 1.9.9 3 2.6 3.2V21"/>',
  'activity':        '<path d="M3 8.5A1.5 1.5 0 0 1 4.5 7h15A1.5 1.5 0 0 1 21 8.5v1.9a2.1 2.1 0 0 0 0 4.2v1.9a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 16.5v-1.9a2.1 2.1 0 0 0 0-4.2z"/><path d="M14 7v11" stroke-dasharray="2 2.6"/>',
  'other':           '<path d="M12 21s7-6.4 7-12a7 7 0 1 0-14 0c0 5.6 7 12 7 12z"/><circle cx="12" cy="9" r="2.4"/>',
};
const I_STAR = '<path d="M12 2.6l2.85 6.05 6.4.92-4.63 4.6 1.1 6.45L12 17.56 6.28 20.6l1.1-6.44-4.63-4.61 6.4-.92z" fill="currentColor" stroke="none"/>';
const I_PLAY = '<path d="M8 5.2v13.6L19 12z" fill="currentColor" stroke="none"/>';
const I_NAV = '<path d="M3 11l18-7-7 18-2.9-8z" stroke-linejoin="round"/>';
const I_BACK = '<path d="M15 5l-7 7 7 7" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>';

let PINS = [];
let filter = 'all';
let term = '';
let openNow = false;
let showClosed = false;
let sortByDistance = false;
let me = null;          // [lat, lng] once geolocation resolves
let selectedId = null;
let sheetMode = null;   // 'detail' | 'list' | null

const map = L.map('map', { zoomControl: false, attributionControl: false, tap: false })
  .setView(LONDON, 12);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(map);

const $ = (id) => document.getElementById(id);
const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
/* esc() makes text safe inside markup, but it does nothing to a URL scheme -
   href="javascript:..." survives it untouched. Anything that becomes an href goes
   through here instead. */
const safeUrl = (u) => (/^https?:\/\//i.test(String(u || '')) ? String(u) : '');
const svg = (paths, size) =>
  `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round">${paths}</svg>`;

function haversine(a, b) {
  const R = 6371, rad = Math.PI / 180;
  const dLat = (b[0] - a[0]) * rad, dLng = (b[1] - a[1]) * rad;
  const s = Math.sin(dLat / 2) ** 2 +
    Math.cos(a[0] * rad) * Math.cos(b[0] * rad) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(s));
}
const fmtDist = (km) => km < 1 ? `${Math.round(km * 1000)}m` : `${km.toFixed(km < 10 ? 1 : 0)}km`;

/* ---------- opening hours ----------
   hours[] is 7 strings, Monday-first, e.g. "Mon: 12:00-9:00 PM". We only need to know
   whether today's line says Closed - parsing real ranges across midnight is not worth it
   for what it adds, so "open now" means "trades today". */
function todayLine(hours) {
  if (!Array.isArray(hours) || hours.length < 7) return null;
  const d = new Date().getDay();          // 0=Sun
  return hours[d === 0 ? 6 : d - 1] || null;
}
function tradingToday(p) {
  const line = todayLine(p.hours);
  return line ? !/closed/i.test(line) : null;   // null = unknown, not false
}

/* Pins run from Uxbridge to Ilford - 29km across - but 90% of them sit inside a 10km
   core. Fitting all of them puts the map at zoom 9, where London is a smudge between
   Luton and Brighton. Fit the 5th-95th percentile instead: you land on central London
   at a useful zoom and the outliers are a pan away. */
function smartBounds(pins) {
  if (pins.length < 12) return L.latLngBounds(pins.map((p) => [p.lat, p.lng]));
  const at = (arr, q) => arr[Math.min(arr.length - 1, Math.floor(arr.length * q))];
  const lats = pins.map((p) => p.lat).sort((a, b) => a - b);
  const lngs = pins.map((p) => p.lng).sort((a, b) => a - b);
  return L.latLngBounds(
    [at(lats, 0.05), at(lngs, 0.05)],
    [at(lats, 0.95), at(lngs, 0.95)]
  );
}

/* ---------- markers ---------- */
let layer = L.layerGroup().addTo(map);
let meMarker = null;

function makeIcon(p, selected, withLabel) {
  const cat = CATS[p.category] || CATS.other;
  const colour = p.status === 'closed' ? cssVar('--closed') : cssVar(cat.varName);
  const glyph = GLYPH[p.category] || GLYPH.other;
  const label = withLabel
    ? `<div class="pin-label">${esc(p.name)}</div>` : '';
  return L.divIcon({
    className: '',
    iconSize: [30, 38],
    iconAnchor: [15, 38],
    html: `<div class="pin-wrap ${selected ? 'selected' : ''} ${p.status === 'closed' ? 'is-closed' : ''}">
      <svg class="map-pin" viewBox="0 0 30 38">
        <path d="M15 37.2C15 37.2 28 23.6 28 14A13 13 0 1 0 2 14c0 9.6 13 23.2 13 23.2z" fill="${colour}"/>
        <g transform="translate(7.5 6.5) scale(0.625)" stroke="#fff" fill="none"
           stroke-width="2.6" stroke-linecap="round">${glyph}</g>
      </svg>${label}</div>`,
  });
}

function matches(p) {
  if (filter !== 'all' && p.category !== filter) return false;
  if (!showClosed && p.status === 'closed') return false;
  if (openNow && tradingToday(p) === false) return false;
  if (term) {
    const hay = (p.name + ' ' + (p.address || '') + ' ' +
      p.reels.map((r) => (r.caption || '') + ' ' + (r.owner || '')).join(' ')).toLowerCase();
    if (!term.split(/\s+/).every((w) => hay.includes(w))) return false;
  }
  return true;
}

function visible() {
  const out = PINS.filter(matches);
  if (me) {
    out.forEach((p) => { p._d = haversine(me, [p.lat, p.lng]); });
    if (sortByDistance) out.sort((a, b) => a._d - b._d);
  }
  return out;
}

/* Below LABEL_ZOOM there are no labels, so an individual teardrop carries no information
   you can act on - 150 of them overlapping is just noise. Cluster there and let the real
   custom pins take over at the zoom where they start being readable. A pixel grid is
   enough; a clustering library would cost a dependency and fight the pin design. */
const CLUSTER_PX = 66;   // must exceed the largest bubble or neighbours collide

function clusterIcon(n, dominant) {
  const size = n > 60 ? 48 : n > 15 ? 43 : 37;
  return L.divIcon({
    className: '',
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    html: `<div class="cluster" style="--c:${cssVar(dominant)};width:${size}px;height:${size}px">
             <span>${n}</span></div>`,
  });
}

function renderClusters(pins) {
  const buckets = new Map();
  for (const p of pins) {
    const pt = map.latLngToContainerPoint([p.lat, p.lng]);
    const key = `${Math.floor(pt.x / CLUSTER_PX)}:${Math.floor(pt.y / CLUSTER_PX)}`;
    let b = buckets.get(key);
    if (!b) buckets.set(key, (b = { items: [], x: 0, y: 0 }));
    b.items.push(p);
    b.x += p.lat;
    b.y += p.lng;
  }
  for (const b of buckets.values()) {
    const n = b.items.length;
    const centre = [b.x / n, b.y / n];
    if (n === 1) {
      const p = b.items[0];
      L.marker([p.lat, p.lng], { icon: makeIcon(p, p.id === selectedId, false), keyboard: false })
        .on('click', () => openDetail(p.id)).addTo(layer);
      continue;
    }
    const counts = {};
    for (const p of b.items) counts[p.category] = (counts[p.category] || 0) + 1;
    const top = Object.entries(counts).sort((a, b2) => b2[1] - a[1])[0][0];
    const cat = CATS[top] || CATS.other;
    L.marker(centre, { icon: clusterIcon(n, cat.varName), keyboard: false })
      .on('click', () => map.setView(centre, Math.min(map.getZoom() + 3, LABEL_ZOOM + 1),
                                    { animate: true }))
      .addTo(layer);
  }
}

function renderMarkers() {
  const zoom = map.getZoom();
  const bounds = map.getBounds().pad(VIEWPORT_PAD);
  layer.clearLayers();
  const inView = visible().filter((p) => bounds.contains([p.lat, p.lng]));

  if (zoom < LABEL_ZOOM) {
    renderClusters(inView);
    return inView.length;
  }
  for (const p of inView) {
    L.marker([p.lat, p.lng], {
      icon: makeIcon(p, p.id === selectedId, true),
      keyboard: false,
      zIndexOffset: p.id === selectedId ? 1000 : 0,
    }).on('click', () => openDetail(p.id)).addTo(layer);
  }
  return inView.length;
}

/* ---------- chrome ---------- */
function renderCount() {
  const n = visible().length;
  const reels = PINS.reduce((s, p) => s + p.reels.length, 0);
  $('count').textContent = n === PINS.length
    ? `${PINS.length} places · ${reels} reels`
    : `${n} of ${PINS.length}`;
}

function renderChips() {
  const row = $('chipRow');
  const base = PINS.filter((p) => showClosed || p.status !== 'closed');
  const defs = [{ key: 'all', label: 'All', varName: null, n: base.length }];
  for (const [key, c] of Object.entries(CATS)) {
    const n = base.filter((p) => p.category === key).length;
    if (n) defs.push({ key, label: c.label, varName: c.varName, n });
  }
  row.innerHTML = '';
  for (const d of defs) {
    const b = document.createElement('button');
    b.className = 'chip glass';
    b.setAttribute('aria-pressed', String(filter === d.key));
    b.innerHTML = (d.varName ? `<span class="dot" style="background:${cssVar(d.varName)}"></span>` : '') +
      `${esc(d.label)} <span class="n">${d.n}</span>`;
    b.onclick = () => { filter = d.key; refresh(); };
    row.appendChild(b);
  }

  const toggle = (id, on, label, handler) => {
    const b = document.createElement('button');
    b.className = 'chip glass';
    b.id = id;
    b.setAttribute('aria-pressed', String(on));
    b.innerHTML = label;
    b.onclick = handler;
    row.appendChild(b);
  };
  // Only offer "Open now" if any pin actually has hours. With no enrichment data it is
  // a control that can never change the result, which is worse than no control.
  if (PINS.some((p) => Array.isArray(p.hours))) {
    toggle('chipOpen', openNow, 'Open now', () => { openNow = !openNow; refresh(); });
  }
  toggle('chipNear', sortByDistance, 'Near me', () => {
    if (!me) { locate(true); return; }
    sortByDistance = !sortByDistance; refresh();
  });
  const nClosed = PINS.filter((p) => p.status === 'closed').length;
  if (nClosed) {
    toggle('chipClosed', showClosed, `Closed <span class="n">${nClosed}</span>`,
      () => { showClosed = !showClosed; refresh(); });
  }
}

function refresh() {
  renderChips();
  renderCount();
  measureChrome();
  renderMarkers();
  if (sheetMode === 'list') renderList();
}

/* The bottom bar's height depends on the safe-area inset and whether the closed-venues
   chip is present, so measure it rather than hardcoding a guess. */
function measureChrome() {
  const h = $('chromeBottom').offsetHeight;
  document.documentElement.style.setProperty('--chrome-h', `${h}px`);
}
addEventListener('resize', measureChrome);
addEventListener('orientationchange', () => setTimeout(measureChrome, 120));

/* ---------- sheet ---------- */
let lastFocus = null;

function openSheet(html, mode) {
  const wasOpen = sheetMode !== null;
  sheetMode = mode;
  if (!wasOpen) lastFocus = document.activeElement;
  $('sheetBody').innerHTML = html;
  $('sheetBody').scrollTop = 0;
  const sheet = $('sheet');
  sheet.style.transform = '';
  sheet.classList.add('open');
  // Below the wide breakpoint the scrim really does block the map, so say so honestly
  // instead of always claiming false.
  sheet.setAttribute('aria-modal', String(innerWidth < 840));
  $('scrim').classList.add('on');
  $('app').classList.add('panel-open');
  if (!wasOpen) sheet.focus({ preventScroll: true });
}

function closeSheet() {
  if (sheetMode === null) return;
  sheetMode = null;
  selectedId = null;
  const sheet = $('sheet');
  sheet.classList.remove('open');
  sheet.style.transform = '';
  $('scrim').classList.remove('on');
  $('app').classList.remove('panel-open');
  if (lastFocus && document.contains(lastFocus)) lastFocus.focus({ preventScroll: true });
  lastFocus = null;
  renderMarkers();
}

function ratingBadge(p) {
  if (p.rating == null) return '';
  const rc = p.rating_count ? `<span class="rc">(${p.rating_count.toLocaleString()})</span>` : '';
  return `<span class="badge">${svg(I_STAR, 12)} ${p.rating.toFixed(1)} ${rc}</span>`;
}
function priceBadge(p) {
  if (p.price_level == null) return '';
  return `<span class="badge">${'£'.repeat(Math.max(1, p.price_level))}</span>`;
}
function hoursBadge(p) {
  if (p.status === 'closed') return '<span class="badge permanently-closed">Permanently closed</span>';
  const t = tradingToday(p);
  if (t === null) return '';
  const line = (todayLine(p.hours) || '').replace(/^\w{3}:\s*/, '');
  return t
    ? `<span class="badge open-now">Open today · ${esc(line)}</span>`
    : '<span class="badge shut">Closed today</span>';
}

/* The caption is the whole reason a place is on this map, and for most pins it is the
   only content there is. Pull the first meaningful line up above the fold. */
function firstLine(caption) {
  const line = String(caption).split('\n')
    .map((l) => l.trim())
    .filter((l) => l && !/^#/.test(l) && l.replace(/[^\w]/g, '').length > 12)[0] || '';
  return line.length > 150 ? line.slice(0, 149).trimEnd() + '…' : line;
}

function openDetail(id) {
  const p = PINS.find((x) => x.id === id);
  if (!p) return;
  selectedId = id;
  const cat = CATS[p.category] || CATS.other;
  const colour = p.status === 'closed' ? cssVar('--closed') : cssVar(cat.varName);
  const maps = `https://maps.apple.com/?q=${encodeURIComponent(p.name)}&ll=${p.lat},${p.lng}`;
  const dist = (me && p._d != null) ? ` · ${fmtDist(p._d)} away` : '';

  const hours = Array.isArray(p.hours) ? `
    <div class="sec-label">Opening hours</div>
    <div class="hours-list">${p.hours.map((h, i) => {
      const d = new Date().getDay(), today = (d === 0 ? 6 : d - 1) === i;
      const [day, ...rest] = h.split(':');
      return `<div class="hours-row ${today ? 'today' : ''}"><span>${esc(day)}</span><span>${esc(rest.join(':').trim())}</span></div>`;
    }).join('')}</div>` : '';

  const reels = `
    <div class="sec-label">${p.reels.length === 1 ? 'The reel' : `${p.reels.length} reels`}</div>
    ${p.reels.map((r) => `
      <a class="reel-card" href="${esc(safeUrl(r.url))}" target="_blank" rel="noopener noreferrer">
        <div class="reel-top">${svg(I_PLAY, 13)}<span class="reel-owner">${esc(r.owner || 'Watch on Instagram')}</span></div>
        ${r.caption ? `<div class="reel-cap">${esc(r.caption)}</div>` : ''}
      </a>`).join('')}`;

  openSheet(`
    <div class="v-head">
      <div class="v-glyph" style="background:${colour}">${svg(GLYPH[p.category] || GLYPH.other, 20)}</div>
      <div style="flex:1;min-width:0">
        <div class="v-name">${esc(p.name)}</div>
        <div class="v-sub">${esc(cat.label)}${dist}${p.address ? ' · ' + esc(p.address) : ''}</div>
      </div>
    </div>
    ${p.reels[0] && p.reels[0].caption
      ? `<div class="v-hook">${esc(firstLine(p.reels[0].caption))}</div>` : ''}
    <div class="v-meta">${ratingBadge(p)}${priceBadge(p)}${hoursBadge(p)}</div>
    <div class="v-actions">
      <a class="btn primary" href="${esc(maps)}" target="_blank" rel="noopener">${svg(I_NAV, 15)} Directions</a>
      ${safeUrl(p.website) ? `<a class="btn" href="${esc(safeUrl(p.website))}" target="_blank" rel="noopener">Website</a>` : ''}
      ${p.phone ? `<a class="btn" href="tel:${esc(p.phone)}">Call</a>` : ''}
    </div>
    ${hours}${reels}`, 'detail');

  // On the wide layout a 420px panel covers the left of the map, so centring on the
  // container would put the pin behind it.
  const offset = innerWidth >= 840 ? -210 : 0;
  const pt = map.project([p.lat, p.lng], map.getZoom()).subtract([offset, 0]);
  map.panTo(map.unproject(pt, map.getZoom()), { animate: true });
  renderMarkers();
}

function renderList() {
  const list = visible();
  const rows = list.slice(0, 200).map((p) => {
    const cat = CATS[p.category] || CATS.other;
    const colour = p.status === 'closed' ? cssVar('--closed') : cssVar(cat.varName);
    const bits = [];
    if (p.rating != null) bits.push(`${svg(I_STAR, 10)} ${p.rating.toFixed(1)}`);
    bits.push(`${p.reels.length} reel${p.reels.length > 1 ? 's' : ''}`);
    if (p.status === 'closed') bits.push('Permanently closed');
    return `<button class="res-item ${p.status === 'closed' ? 'is-closed' : ''}" data-id="${esc(p.id)}">
      <span class="res-glyph" style="background:${colour}">${svg(GLYPH[p.category] || GLYPH.other, 17)}</span>
      <span class="res-main">
        <span class="res-name">${esc(p.name)}</span>
        <span class="res-sub">${bits.join('<span class="sep">·</span>')}</span>
      </span>
      ${me && p._d != null ? `<span class="res-dist">${fmtDist(p._d)}</span>` : ''}
    </button>`;
  }).join('');

  const empty = `<div class="empty">
      <div class="empty-title">Nothing matches</div>
      <div class="empty-sub">Try a different search, or clear the filters.</div>
    </div>`;

  openSheet(`
    <div class="res-head">
      <span class="res-title">${list.length} place${list.length === 1 ? '' : 's'}</span>
      <button class="res-sort" id="sortBtn">${sortByDistance ? 'Nearest first' : 'A–Z'}</button>
    </div>
    ${list.length ? rows : empty}
    ${list.length > 200 ? '<div class="empty"><div class="empty-sub">Showing the first 200. Search to narrow it down.</div></div>' : ''}`,
    'list');

  $('sheetBody').querySelectorAll('.res-item').forEach((el) => {
    el.onclick = () => openDetail(el.dataset.id);
  });
  $('sortBtn').onclick = () => {
    if (!sortByDistance && !me) { locate(true); return; }
    sortByDistance = !sortByDistance;
    refresh();
    renderList();
  };
}

/* The grabber implies a swipe. Without this it is decoration that lies about what the
   sheet can do, and swiping down is the first thing an iOS user tries. */
(function enableSwipeToDismiss() {
  const sheet = $('sheet');
  const body = $('sheetBody');
  let startY = 0, dy = 0, dragging = false;

  sheet.addEventListener('touchstart', (e) => {
    if (innerWidth >= 840) return;          // side panel on wide screens, no swipe
    // Only start a drag from the top of the content, so scrolling the list still works.
    if (e.target.closest('.sheet-body') && body.scrollTop > 0) return;
    startY = e.touches[0].clientY;
    dy = 0;
    dragging = true;
    sheet.style.transition = 'none';
  }, { passive: true });

  sheet.addEventListener('touchmove', (e) => {
    if (!dragging) return;
    dy = e.touches[0].clientY - startY;
    if (dy < 0) dy = dy / 6;                // resist upward, there is no taller detent
    sheet.style.transform = `translateY(${dy}px)`;
  }, { passive: true });

  sheet.addEventListener('touchend', () => {
    if (!dragging) return;
    dragging = false;
    sheet.style.transition = '';
    sheet.style.transform = '';
    if (dy > Math.min(120, sheet.offsetHeight * 0.25)) closeSheet();
  });
})();

/* ---------- geolocation ---------- */
let toastTimer = null;
function toast(msg) {
  const t = $('toast');
  t.textContent = msg;
  t.classList.add('on');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('on'), 3200);
}

function locate(thenSortByDistance) {
  if (!navigator.geolocation) { toast('This browser cannot share your location.'); return; }
  const btn = $('locateBtn');
  btn.classList.add('locating');
  navigator.geolocation.getCurrentPosition((pos) => {
    btn.classList.remove('locating');
    btn.classList.add('active');
    me = [pos.coords.latitude, pos.coords.longitude];
    if (meMarker) meMarker.remove();
    meMarker = L.marker(me, {
      icon: L.divIcon({ className: '', html: '<div class="me-dot"></div>', iconSize: [18, 18], iconAnchor: [9, 9] }),
      interactive: false, zIndexOffset: 2000,
    }).addTo(map);

    const near = PINS.filter(matches).map((p) => haversine(me, [p.lat, p.lng])).sort((a, b) => a - b)[0];
    if (near == null || near > 60) {
      toast("You're outside London — showing everything.");
      map.setView(LONDON, 12);
    } else {
      map.setView(me, 14, { animate: true });
    }
    if (thenSortByDistance) sortByDistance = true;
    refresh();
    if (sheetMode === 'list') renderList();
  }, (err) => {
    btn.classList.remove('locating');
    toast(err.code === 1
      ? 'Location is blocked. Turn it on in Settings to use “Near me”.'
      : 'Could not get your location.');
  }, { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 });
}

/* ---------- wiring ---------- */
let searchTimer = null;
$('searchInput').addEventListener('input', (e) => {
  const v = e.target.value;
  $('clearBtn').classList.toggle('on', v.length > 0);
  clearTimeout(searchTimer);
  // Debounced: without this every keystroke re-renders every marker.
  searchTimer = setTimeout(() => {
    term = v.trim().toLowerCase();
    refresh();
    if (!term) return;
    // If a card is open and the new search excludes it, the card is stale - swap to the
    // results rather than leaving a venue on screen that no longer matches.
    if (sheetMode === 'detail') {
      const shown = PINS.find((x) => x.id === selectedId);
      if (!shown || !matches(shown)) renderList();
      return;
    }
    renderList();
  }, 130);
});
$('clearBtn').onclick = () => {
  $('searchInput').value = '';
  $('clearBtn').classList.remove('on');
  term = '';
  refresh();
  if (sheetMode === 'list') renderList();
};
$('searchInput').addEventListener('keydown', (e) => { if (e.key === 'Enter') e.target.blur(); });

$('listBtn').onclick = () => { sheetMode === 'list' ? closeSheet() : renderList(); };
$('locateBtn').onclick = () => locate(false);
$('scrim').onclick = closeSheet;
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeSheet(); });

// Shows the icon for what tapping will DO next: a sun while dark, a moon while light.
function setThemeIcon(theme) {
  $('themeIcon').innerHTML = theme === 'dark'
    ? '<circle cx="12" cy="12" r="4.4"/><path d="M12 1.6v2.6M12 19.8v2.6M4.2 4.2l1.9 1.9M17.9 17.9l1.9 1.9M1.6 12h2.6M19.8 12h2.6M4.2 19.8l1.9-1.9M17.9 6.1l1.9-1.9"/>'
    : '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>';
}

$('themeBtn').onclick = () => {
  const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem('theme', next); } catch (e) { /* private mode */ }
  setThemeIcon(next);
  refresh();   // pin colours are read from CSS vars, so they must be redrawn
};

let moveTimer = null;
const onMapMove = () => { clearTimeout(moveTimer); moveTimer = setTimeout(renderMarkers, 90); };
map.on('moveend', onMapMove);
map.on('zoomend', onMapMove);

/* ---------- boot ---------- */
fetch('pins.json')
  .then((r) => { if (!r.ok) throw new Error(`pins.json returned ${r.status}`); return r.json(); })
  .then((data) => {
    PINS = data;
    setThemeIcon(document.documentElement.dataset.theme);
    refresh();
    if (PINS.length) map.fitBounds(smartBounds(PINS), { padding: [40, 40], maxZoom: 14 });
  })
  .catch((err) => {
    console.error(err);
    toast('Could not load places. Check your connection.');
  });

/* Not on localhost: a cached shell during development means you spend ten minutes
   debugging code the browser isn't running. It bit us twice. The SW is for the phone. */
const IS_DEV = ['localhost', '127.0.0.1'].includes(location.hostname);
if ('serviceWorker' in navigator) {
  if (IS_DEV) {
    navigator.serviceWorker.getRegistrations().then((rs) => rs.forEach((r) => r.unregister()));
    if (window.caches) caches.keys().then((ks) => ks.forEach((k) => caches.delete(k)));
  } else {
    addEventListener('load', () => navigator.serviceWorker.register('sw.js').catch(() => {}));
  }
}
