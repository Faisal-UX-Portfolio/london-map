const CATS = {
  'restaurant/food': { label: 'Food & drink', varName: '--food' },
  'activity':         { label: 'Things to do', varName: '--activity' },
  'other':            { label: 'Other',        varName: '--muted-2' }
};

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

const map = L.map('map', { zoomControl: false, attributionControl: false }).setView([51.5074, -0.1278], 12);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(map);
L.control.attribution({ position: 'bottomleft', prefix: false }).addAttribution('&copy; OpenStreetMap').addTo(map);

function escapeHtml(s) {
  return (s || '').replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
}

// ---- smart initial view: trim outliers so we open on the main cluster, not all of Greater London ----
function haversine(a, b) {
  const R = 6371;
  const dLat = (b[0]-a[0]) * Math.PI/180, dLng = (b[1]-a[1]) * Math.PI/180;
  const s = Math.sin(dLat/2)**2 + Math.cos(a[0]*Math.PI/180)*Math.cos(b[0]*Math.PI/180)*Math.sin(dLng/2)**2;
  return 2*R*Math.asin(Math.sqrt(s));
}
function smartBounds(pins) {
  if (pins.length <= 3) return L.latLngBounds(pins.map(p => [p.lat, p.lng]));
  const lats = pins.map(p => p.lat), lngs = pins.map(p => p.lng);
  const centroid = [lats.reduce((a,b)=>a+b,0)/lats.length, lngs.reduce((a,b)=>a+b,0)/lngs.length];
  const withDist = pins.map(p => ({p, d: haversine(centroid, [p.lat, p.lng])})).sort((a,b) => a.d - b.d);
  const keep = withDist.slice(0, Math.ceil(withDist.length * 0.82));
  return L.latLngBounds(keep.map(x => [x.p.lat, x.p.lng]));
}

let markers = [];
let currentFilter = 'all';
let selectedIdx = null;
let searchTerm = '';
let userMarker = null;

const CAT_ICON = {
  'restaurant/food': '<path d="M7 2v7a2 2 0 0 0 2 2h0a2 2 0 0 0 2-2V2M9 11v11M15 2c-1.5 1-2 3-2 5s.5 3 2 4v10" stroke-linecap="round" stroke-linejoin="round"/>',
  'activity': '<path d="M4 8a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v2a2 2 0 0 0 0 4v2a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-2a2 2 0 0 0 0-4z" stroke-linecap="round" stroke-linejoin="round"/><line x1="12" y1="6" x2="12" y2="18" stroke-dasharray="2 2"/>',
  'other': '<path d="M12 21s7-6.4 7-12a7 7 0 1 0-14 0c0 5.6 7 12 7 12z" stroke-linecap="round" stroke-linejoin="round"/><circle cx="12" cy="9" r="2.4"/>'
};
const ICON_PLAY = '<path d="M8 5.5v13l11-6.5z" fill="currentColor" stroke="none"/>';
const ICON_DIRECTIONS = '<path d="M3 11l18-7-7 18-3-8-8-3z" stroke-linecap="round" stroke-linejoin="round"/>';
const ICON_PIN = '<path d="M12 21s7-6.4 7-12a7 7 0 1 0-14 0c0 5.6 7 12 7 12z" stroke-linecap="round" stroke-linejoin="round"/><circle cx="12" cy="9" r="2.4"/>';
const ICON_FILM = '<rect x="3" y="4" width="18" height="16" rx="2"/><line x1="7" y1="4" x2="7" y2="20"/><line x1="17" y1="4" x2="17" y2="20"/><line x1="3" y1="9" x2="7" y2="9"/><line x1="3" y1="15" x2="7" y2="15"/><line x1="17" y1="9" x2="21" y2="9"/><line x1="17" y1="15" x2="21" y2="15"/>';

function svg(paths, size) {
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${paths}</svg>`;
}

function shortLabel(name) {
  const words = name.split(' ');
  return words.length <= 2 ? name : words.slice(0, 2).join(' ');
}

function makeIcon(cat, selected, placeName) {
  const colorHex = cssVar(CATS[cat] ? CATS[cat].varName : '--muted-2');
  const glyph = CAT_ICON[cat] || CAT_ICON['other'];
  const label = shortLabel(placeName);
  const badgeWidth = Math.min(170, 24 + label.length * 6.6);
  return L.divIcon({
    className: '',
    html: `<div class="pin-wrap ${selected ? 'selected' : ''}" style="--pin-color:${colorHex}; position:relative; display:flex; align-items:center; justify-content:center; width:30px; height:30px;">
             <div class="pin-badge" style="width:${badgeWidth}px;">${escapeHtml(label)}</div>
             <div class="map-pin" style="background:${colorHex}; color:#fff;">${svg(glyph, 14)}</div>
           </div>`,
    iconSize: [30, 30],
    iconAnchor: [15, 30]
  });
}

function todayHoursLine(hours) {
  if (!hours || !hours.length) return null;
  // JS getDay(): 0=Sun..6=Sat; our array is Mon..Sun (index 0=Mon)
  const jsDay = new Date().getDay();
  const idx = jsDay === 0 ? 6 : jsDay - 1;
  const line = hours[idx] || '';
  return line.replace(/^(Mon|Tue|Wed|Thu|Fri|Sat|Sun):\s*/, '');
}

const ICON_STAR = '<path d="M12 2l2.9 6.9L22 9.3l-5.3 4.8L18.2 21 12 17.3 5.8 21l1.5-6.9L2 9.3l7.1-.4z" fill="currentColor" stroke="none"/>';
const ICON_CLOCK = '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3" stroke-linecap="round"/>';

function openSheet(p, idx) {
  selectedIdx = idx;
  renderMarkers();
  const cat = CATS[p.category] || CATS['other'];
  const colorHex = cssVar(cat.varName);
  const mapsUrl = `https://maps.apple.com/?daddr=${encodeURIComponent(p.address)}&ll=${p.lat},${p.lng}`;
  const ratingHtml = p.rating != null
    ? `<span class="sheet-rating">${svg(ICON_STAR, 13)}${p.rating.toFixed(1)}<span class="sheet-rating-count">(${p.rating_count})</span></span>`
    : '';
  const todayLine = todayHoursLine(p.hours);
  document.getElementById('sheetContent').innerHTML = `
    <div class="sheet-top-row">
      <span class="sheet-cat" style="background:${colorHex}"><span class="dot"></span>${cat.label}</span>
      ${ratingHtml}
    </div>
    <div class="sheet-title">${escapeHtml(p.place_name)}</div>
    <div class="action-row">
      <a class="action-btn" href="${mapsUrl}" target="_blank" rel="noopener">
        <div class="action-btn-circle" style="background:${colorHex}">${svg(ICON_DIRECTIONS, 17)}</div>
        <span>Directions</span>
      </a>
      <a class="action-btn" href="${p.reel_url}" target="_blank" rel="noopener">
        <div class="action-btn-circle" style="background:${colorHex}">${svg(ICON_PLAY, 17)}</div>
        <span>Reel</span>
      </a>
    </div>
    <div class="sheet-caption">${escapeHtml(p.caption)}</div>
    <div class="info-rows">
      <div class="info-row">
        <div class="info-row-icon" style="color:${colorHex}">${svg(ICON_PIN, 16)}</div>
        <div class="info-row-text"><div class="info-row-label">Address</div>${escapeHtml(p.address)}</div>
      </div>
      ${todayLine ? `<div class="info-row">
        <div class="info-row-icon" style="color:${colorHex}">${svg(ICON_CLOCK, 16)}</div>
        <div class="info-row-text"><div class="info-row-label">Today</div>${escapeHtml(todayLine)}</div>
      </div>` : ''}
      <div class="info-row">
        <div class="info-row-icon" style="color:${colorHex}">${svg(ICON_FILM, 16)}</div>
        <div class="info-row-text"><div class="info-row-label">Spotted via</div>@${escapeHtml(p.owner)}</div>
      </div>
    </div>`;
  document.getElementById('sheet').classList.add('show');
  document.getElementById('overlay').classList.add('show');
}

function closeSheet() {
  document.getElementById('sheet').classList.remove('show');
  document.getElementById('overlay').classList.remove('show');
  selectedIdx = null;
  renderMarkers();
}
document.getElementById('overlay').addEventListener('click', closeSheet);

function matchesSearch(p, term) {
  if (!term) return true;
  const hay = (p.place_name + ' ' + p.caption + ' ' + p.address).toLowerCase();
  return hay.includes(term);
}

function visiblePins() {
  const term = searchTerm.trim().toLowerCase();
  return PINS.map((p, i) => ({p, i})).filter(({p}) =>
    (currentFilter === 'all' || p.category === currentFilter) && matchesSearch(p, term)
  );
}

function renderMarkers() {
  markers.forEach(m => map.removeLayer(m));
  markers = [];
  const visible = visiblePins();
  visible.forEach(({p, i}) => {
    const marker = L.marker([p.lat, p.lng], { icon: makeIcon(p.category, i === selectedIdx, p.place_name) });
    marker.on('click', () => openSheet(p, i));
    marker.addTo(map);
    markers.push(marker);
  });
  document.getElementById('statRow').innerHTML = `<b>${visible.length}</b> of <b>${PINS.length}</b> spots mapped &middot; 414 saved reels total, still adding`;
}

function renderChips() {
  const container = document.getElementById('chipRow');
  const counts = { all: PINS.length };
  Object.keys(CATS).forEach(k => counts[k] = PINS.filter(p => p.category === k).length);
  const defs = [{ key: 'all', label: 'All', varName: null }].concat(
    Object.keys(CATS).filter(k => counts[k] > 0).map(k => ({ key: k, label: CATS[k].label, varName: CATS[k].varName }))
  );
  container.innerHTML = '';
  defs.forEach(d => {
    const btn = document.createElement('button');
    btn.className = 'chip glass' + (d.key === currentFilter ? ' active' : '');
    const dotHtml = d.varName ? `<span class="dot" style="background:${cssVar(d.varName)}"></span>` : '';
    btn.innerHTML = `${dotHtml}${d.label} (${counts[d.key]})`;
    btn.onclick = () => { currentFilter = d.key; closeSheet(); renderChips(); renderMarkers(); };
    container.appendChild(btn);
  });
}

document.getElementById('searchInput').addEventListener('input', (e) => {
  searchTerm = e.target.value;
  closeSheet();
  renderMarkers();
});

document.getElementById('locateBtn').addEventListener('click', () => {
  const btn = document.getElementById('locateBtn');
  if (!navigator.geolocation) { alert('Location is not available in this browser.'); return; }
  btn.style.opacity = '0.4';
  navigator.geolocation.getCurrentPosition((pos) => {
    const { latitude, longitude } = pos.coords;
    btn.classList.add('active');
    btn.style.opacity = '1';
    if (userMarker) map.removeLayer(userMarker);
    userMarker = L.marker([latitude, longitude], {
      icon: L.divIcon({ className: '', html: '<div class="user-dot"></div>', iconSize: [16,16], iconAnchor: [8,8] })
    }).addTo(map);
    map.setView([latitude, longitude], 15, { animate: true });
  }, () => {
    btn.style.opacity = '1';
    alert('Could not get your location. Check that location access is allowed for this page.');
  });
});

document.getElementById('themeToggle').onclick = () => {
  const root = document.documentElement;
  const isDark = root.getAttribute('data-theme') === 'dark';
  root.setAttribute('data-theme', isDark ? 'light' : 'dark');
  renderChips();
  renderMarkers();
  if (selectedIdx !== null) openSheet(PINS[selectedIdx], selectedIdx);
};

renderChips();
renderMarkers();

if (PINS.length) {
  map.fitBounds(smartBounds(PINS), { padding: [50, 50], maxZoom: 15 });
}
