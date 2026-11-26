(async function () {
  const data = await (await fetch('data/index.json')).json();
  const tools = data.tools;
  const $ = (id) => document.getElementById(id);

  // Build stamp written by CI at publish time (site/data/meta.json). Absent locally -> "dev build".
  (async function showVersion() {
    try {
      const res = await fetch('data/meta.json', { cache: 'no-cache' });
      if (!res.ok) return;
      const m = await res.json();
      // Point the header links at this site's own repo (the hardcoded hrefs are the local-dev fallback).
      if (/^[\w.-]+\/[\w.-]+$/.test(m.repo || '')) {
        const repoUrl = 'https://github.com/' + m.repo;
        $('repo-link').href = repoUrl;
        const issues = document.querySelector('a[href$="/issues"]');
        if (issues) issues.href = repoUrl + '/issues';
      }
      const sha = String(m.sha || '');
      const date = String(m.date || '');
      if (!/^[0-9a-f]{7,40}$/i.test(sha) || !/^\d{4}-\d{2}-\d{2}$/.test(date)) return;
      const el = $('site-version');
      el.textContent = 'Updated ' + date + ' · ';
      el.title = 'Deployed ' + date + ', commit ' + sha;
      const a = document.createElement('a');
      a.textContent = sha.slice(0, 7);
      if (/^[\w.-]+\/[\w.-]+$/.test(m.repo || '')) {
        a.href = 'https://github.com/' + m.repo + '/commit/' + sha;
        a.target = '_blank';
        a.rel = 'noopener';
      }
      el.appendChild(a);
    } catch (e) { /* keep default text */ }
  })();

  const SORTS = {
    'name-asc': 'Name (A–Z)',
    'name-desc': 'Name (Z–A)',
    'added-desc': 'Recently added',
    'updated-desc': 'Recently updated',
    'updated-asc': 'Least recently updated',
    'type-asc': 'Type',
  };
  const PAGE_SIZES = [12, 24, 48, 96];
  const ARCHIVED_MODES = { hide: 'Hide archived', include: 'Include archived', only: 'Only archived' };
  const DEFAULTS = { view: 'cards', sort: 'name-asc', size: 12, page: 1, archived: 'hide' };

  // All view state is mirrored in the URL hash so views are shareable.
  // "starred" (the Starred-only filter) is deliberately not mirrored in the hash: stars are personal.
  const state = { q: '', product: new Set(), type: new Set(), tags: new Set(), starred: false, ...DEFAULTS };

  // Starred tool ids live in this browser only (localStorage). Ids of tools that no longer exist are dropped.
  const STARS_KEY = 'starred';
  const stars = new Set();
  try {
    const known = new Set(tools.map((t) => t.id));
    JSON.parse(localStorage.getItem(STARS_KEY) || '[]').forEach((id) => known.has(id) && stars.add(id));
  } catch (e) { /* storage unavailable or corrupt: start with no stars */ }
  function saveStars() {
    try { localStorage.setItem(STARS_KEY, JSON.stringify([...stars])); } catch (e) { /* storage unavailable */ }
  }

  function el(tag, props = {}, children = []) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (k === 'class') e.className = v;
      else if (k === 'text') e.textContent = v;
      else e.setAttribute(k, v);
    }
    children.forEach((c) => e.append(c));
    return e;
  }

  function loadHash() {
    const p = new URLSearchParams(location.hash.slice(1));
    state.q = p.get('q') || '';
    for (const k of ['product', 'type', 'tags']) {
      state[k] = new Set((p.get(k) || '').split(',').filter(Boolean));
    }
    state.archived = ARCHIVED_MODES[p.get('archived')] ? p.get('archived') : DEFAULTS.archived;
    state.view = p.get('view') === 'table' ? 'table' : 'cards';
    state.sort = SORTS[p.get('sort')] ? p.get('sort') : DEFAULTS.sort;
    const size = parseInt(p.get('size'), 10);
    state.size = PAGE_SIZES.includes(size) ? size : DEFAULTS.size;
    state.page = Math.max(1, parseInt(p.get('page'), 10) || 1);
    $('search').value = state.q;
  }

  function saveHash() {
    const p = new URLSearchParams();
    if (state.q) p.set('q', state.q);
    for (const k of ['product', 'type', 'tags']) {
      if (state[k].size) p.set(k, [...state[k]].join(','));
    }
    for (const k of ['view', 'sort', 'size', 'page', 'archived']) {
      if (state[k] !== DEFAULTS[k]) p.set(k, state[k]);
    }
    history.replaceState(null, '', p.toString() ? '#' + p : location.pathname);
  }

  // Product and type are OR within a group; tags are AND (narrowing).
  // Archived tools are hidden unless the Archived filter says otherwise.
  function matches(t, mode = state.archived) {
    if (mode === 'hide' && t.archived) return false;
    if (mode === 'only' && !t.archived) return false;
    if (state.starred && !stars.has(t.id)) return false;
    if (state.product.size && !t.product.some((p) => state.product.has(p))) return false;
    if (state.type.size && !state.type.has(t.type)) return false;
    for (const tag of state.tags) if (!t.tags.includes(tag)) return false;
    if (state.q) {
      const hay = [t.name, t.description, t.maintainer, ...t.tags].join(' ').toLowerCase();
      if (!state.q.toLowerCase().split(/\s+/).every((w) => hay.includes(w))) return false;
    }
    return true;
  }

  function sorted(list) {
    const [key, dir] = state.sort.split('-');
    const sign = dir === 'desc' ? -1 : 1;
    const byName = (a, b) => a.name.localeCompare(b.name);
    return [...list].sort((a, b) => {
      let va, vb;
      if (key === 'type') { va = data.types[a.type] || a.type; vb = data.types[b.type] || b.type; }
      else { va = a[key] || ''; vb = b[key] || ''; }
      // Entries with no value (e.g. no "updated" date) always sort last.
      if (!va && vb) return 1;
      if (va && !vb) return -1;
      const c = String(va).localeCompare(String(vb));
      return c ? c * sign : byName(a, b);
    });
  }

  // Any change to the filters or search starts again from page 1.
  function changed() { state.page = 1; render(); }

  function toggle(set, v) {
    set.has(v) ? set.delete(v) : set.add(v);
    changed();
  }

  function checkbox(group, value, label) {
    const id = `cb-${group}-${value}`;
    const input = el('input', { type: 'checkbox', id });
    input.checked = state[group].has(value);
    input.addEventListener('change', () => toggle(state[group], value));
    return el('div', { class: 'clr-checkbox-wrapper' }, [
      input, el('label', { for: id, class: 'clr-control-label', text: label }),
    ]);
  }

  function radio(group, value, label) {
    const id = `rb-${group}-${value}`;
    const input = el('input', { type: 'radio', id, name: group });
    input.checked = state[group] === value;
    input.addEventListener('change', () => { state[group] = value; changed(); });
    return el('div', { class: 'clr-radio-wrapper' }, [
      input, el('label', { for: id, class: 'clr-control-label', text: label }),
    ]);
  }

  function renderStarredFilter() {
    const input = el('input', { type: 'checkbox', id: 'cb-starred' });
    input.checked = state.starred;
    input.addEventListener('change', () => { state.starred = input.checked; changed(); });
    $('f-starred').replaceChildren(el('div', { class: 'clr-checkbox-wrapper' }, [
      input, el('label', { for: 'cb-starred', class: 'clr-control-label', text: `Starred only (${stars.size})` }),
    ]));
  }

  function renderFilters() {
    const fp = $('f-product'), ft = $('f-type'), tg = $('f-tags'), fa = $('f-archived');
    renderStarredFilter();
    fa.replaceChildren(...Object.entries(ARCHIVED_MODES).map(([k, label]) => radio('archived', k, label)));
    if (state.archived !== 'hide') $('archived-group').open = true;
    fp.replaceChildren(...Object.entries(data.products).map(([k, v]) => checkbox('product', k, v.label)));
    const usedTypes = [...new Set(tools.map((t) => t.type))];
    ft.replaceChildren(...usedTypes.map((k) => checkbox('type', k, data.types[k] || k)));

    // Tag counts reflect the current result set so users can't filter to zero.
    const pool = tools.filter((t) => matches(t));
    const counts = {};
    pool.forEach((t) => t.tags.forEach((x) => (counts[x] = (counts[x] || 0) + 1)));
    state.tags.forEach((x) => (counts[x] = counts[x] || 0));
    const names = Object.keys(counts).sort();
    tg.replaceChildren(...names.map((x) => {
      const b = el('button', { type: 'button', class: 'label label-light-blue clickable' + (state.tags.has(x) ? ' active' : '') },
        [document.createTextNode(x), el('small', { text: counts[x] })]);
      b.addEventListener('click', () => toggle(state.tags, x));
      return b;
    }));
  }

  // ---- shared bits -------------------------------------------------------
  // A tool is "new" for data.new_days days after it was added (checked in the
  // browser, so the badge expires without a rebuild).
  function isNew(t) {
    if (!t.added || t.archived) return false;
    const days = (Date.now() - new Date(t.added + 'T00:00:00').getTime()) / 86400000;
    return days <= (data.new_days || 30);
  }
  const newBadge = (t) => isNew(t)
    ? [el('span', { class: 'badge badge-danger new-badge', text: 'NEW', title: `Added ${t.added}` })]
    : [];

  const archivedBadge = (t) => t.archived
    ? [el('span', { class: 'label archived-badge', text: 'ARCHIVED', title: t.archived_reason || 'Archived' })]
    : [];

  // Shown in the main list only; inside the Featured band it would be redundant.
  const featuredBadge = (t, inBand) => t.featured && !inBand
    ? [el('span', { class: 'label featured-badge', text: 'FEATURED', title: 'Featured tool' })]
    : [];

  const STAR_SVG = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M12 2.5l2.9 6 6.6.8-4.9 4.5 1.3 6.5L12 17l-5.9 3.3 1.3-6.5L2.5 9.3l6.6-.8z"/></svg>';
  function setStarState(b, t) {
    const on = stars.has(t.id);
    b.setAttribute('aria-pressed', String(on));
    b.setAttribute('aria-label', (on ? 'Unstar ' : 'Star ') + t.name);
    b.title = on ? 'Remove star' : 'Star this tool';
  }
  function toggleStar(t) {
    stars.has(t.id) ? stars.delete(t.id) : stars.add(t.id);
    saveStars();
    if (state.starred) { render(); return; } // the list itself changes
    // Otherwise just refresh this tool's buttons (it may appear in the band and the list) and the filter count.
    document.querySelectorAll(`.star-btn[data-id="${t.id}"]`).forEach((b) => setStarState(b, t));
    renderStarredFilter();
  }
  function starButton(t) {
    const b = el('button', { type: 'button', class: 'star-btn', 'data-id': t.id });
    b.innerHTML = STAR_SVG;
    setStarState(b, t);
    b.addEventListener('click', () => toggleStar(t));
    return b;
  }

  const versionBadge = (t) => t.version
    ? [el('span', { class: 'label label-blue version', text: String(t.version) })]
    : [];

  const productLabels = (t, short = false) => t.product.map((p) => {
    const info = data.products[p] || {};
    return el('span', { class: `label label-${info.color || 'gray'}`, text: (short && info.short) || info.label || p });
  });

  const typeLabel = (t) => el('span', { class: 'label label-gray', text: data.types[t.type] || t.type });

  function tagLabels(t) {
    return t.tags.map((x) => {
      const l = el('span', { class: 'label' + (state.tags.has(x) ? ' label-info' : ''), text: x, style: 'cursor:pointer' });
      l.addEventListener('click', () => toggle(state.tags, x));
      return l;
    });
  }

  function sourceLabel(t) {
    const info = (data.sources || {})[t.source] || {};
    return el('span', { class: `label label-${info.color || 'gray'} source`, text: info.label || t.source || '' });
  }

  // Always show users where a link leads before they click it.
  function destination(t) {
    const shown = t.url.replace(/^https:\/\//i, '').replace(/\/$/, '');
    const link = el('a', {
      class: 'tool-url', href: t.url, target: '_blank', rel: 'noopener noreferrer', title: t.url, text: shown,
    });
    return { link };
  }

  // ---- cards -------------------------------------------------------------
  function card(t, inBand = false) {
    const dest = destination(t);
    const row = (label, ...content) => el('div', { class: 'info-row' }, [
      el('span', { class: 'info-label', text: label }), el('span', { class: 'info-value' }, content),
    ]);
    return el('div', { class: 'clr-col-12 clr-col-md-6 clr-col-xl-4 card-grid-item' }, [
      el('div', { class: 'card' + (t.archived ? ' archived' : '') }, [
        el('div', { class: 'card-header' }, [starButton(t), document.createTextNode(t.name), ...versionBadge(t), ...newBadge(t), ...featuredBadge(t, inBand), ...archivedBadge(t)]),
        el('div', { class: 'card-block' }, [
          el('div', { class: 'card-text' }, [...productLabels(t), typeLabel(t)]),
          el('p', { class: 'card-text', text: t.description }),
          el('div', { class: 'card-text' }, tagLabels(t)),
        ]),
        el('div', { class: 'card-footer' }, [
          row('URL', dest.link),
          row('Source', sourceLabel(t)),
          ...(t.maintainer ? [row('Maintainer', document.createTextNode(t.maintainer))] : []),
          ...(t.updated ? [row('Updated', document.createTextNode(t.updated))] : []),
        ]),
      ]),
    ]);
  }

  function cardsView(page, inBand = false) {
    return el('div', { class: 'clr-row' }, page.map((t) => card(t, inBand)));
  }

  // ---- table -------------------------------------------------------------
  function sortHeader(label, key) {
    const [curKey, curDir] = state.sort.split('-');
    const active = curKey === key;
    const th = el('th', { 'aria-sort': active ? (curDir === 'asc' ? 'ascending' : 'descending') : 'none' });
    const b = el('button', { type: 'button', class: 'sort-btn', text: label + (active ? (curDir === 'asc' ? ' ▲' : ' ▼') : '') });
    b.addEventListener('click', () => {
      // Dates are most useful newest-first; everything else starts A–Z.
      const first = key === 'updated' ? 'desc' : 'asc';
      state.sort = active ? `${key}-${curDir === 'asc' ? 'desc' : 'asc'}` : `${key}-${first}`;
      changed();
    });
    th.append(b);
    return th;
  }

  // inBand: the Featured band reuses this table but with plain headers (sorting applies to the main list only).
  function tableView(page, inBand = false) {
    const header = (label, key) => (inBand ? el('th', { text: label }) : sortHeader(label, key));
    const head = el('tr', {}, [
      header('Name', 'name'),
      el('th', { text: 'Product' }),
      header('Type', 'type'),
      el('th', { text: 'Description' }),
      el('th', { text: 'Tags' }),
      header('Updated', 'updated'),
    ]);
    const rows = page.map((t) => { const dest = destination(t); return el('tr', { class: t.archived ? 'archived' : '' }, [
      el('td', { class: 'left name-cell' }, [
        starButton(t),
        el('strong', { class: 'tool-name', text: t.name }),
        ...versionBadge(t),
        ...newBadge(t),
        ...featuredBadge(t, inBand),
        el('div', { class: 'dest' }, [dest.link]),
        el('div', { class: 'dest-source' }, [sourceLabel(t), ...archivedBadge(t)]),
      ]),
      el('td', { class: 'left', 'data-label': 'Product' }, productLabels(t, true)),
      el('td', { class: 'left', 'data-label': 'Type' }, [typeLabel(t)]),
      el('td', { class: 'left', 'data-label': 'Description' }, [el('div', { class: 'desc-clamp', title: t.description, text: t.description })]),
      el('td', { class: 'left', 'data-label': 'Tags' }, tagLabels(t)),
      el('td', { class: 'left nowrap', 'data-label': 'Updated', text: t.updated || '' }),
    ]); });
    return el('div', { class: 'table-wrap' }, [
      el('table', { class: 'table table-compact' }, [el('thead', {}, [head]), el('tbody', {}, rows)]),
    ]);
  }

  // ---- toolbar & pager -----------------------------------------------------
  function renderToolbar() {
    for (const v of ['cards', 'table']) {
      const b = $('view-' + v);
      b.className = 'btn btn-sm ' + (state.view === v ? 'btn-primary' : 'btn-outline');
      b.setAttribute('aria-pressed', state.view === v);
    }
    $('sort').value = state.sort;
    $('size').value = String(state.size);
  }

  function pageList(cur, total) {
    const keep = new Set([1, total, cur - 1, cur, cur + 1]);
    const out = [];
    let last = 0;
    for (let n = 1; n <= total; n++) {
      if (!keep.has(n)) continue;
      if (n - last > 1) out.push('…');
      out.push(n);
      last = n;
    }
    return out;
  }

  function renderPager(totalPages) {
    const pager = $('pager');
    if (totalPages <= 1) { pager.replaceChildren(); return; }
    const go = (n) => { state.page = n; render(); window.scrollTo({ top: 0 }); };
    const btn = (label, n, { disabled = false, current = false } = {}) => {
      const b = el('button', { type: 'button', class: 'btn btn-sm ' + (current ? 'btn-primary' : 'btn-outline'), text: label });
      if (disabled) b.disabled = true;
      if (current) b.setAttribute('aria-current', 'page');
      b.addEventListener('click', () => go(n));
      return b;
    };
    pager.replaceChildren(
      btn('Previous', state.page - 1, { disabled: state.page === 1 }),
      ...pageList(state.page, totalPages).map((n) =>
        n === '…' ? el('span', { class: 'pager-gap', text: '…' }) : btn(String(n), n, { current: n === state.page })),
      btn('Next', state.page + 1, { disabled: state.page === totalPages }),
    );
  }

  // ---- collapsible filter sidebar ------------------------------------------
  const FILTERS_KEY = 'filtersCollapsed';
  let filtersCollapsed;
  try { filtersCollapsed = localStorage.getItem(FILTERS_KEY); } catch (e) { filtersCollapsed = null; }
  // Remembered choice wins; otherwise start collapsed on narrow screens.
  filtersCollapsed = filtersCollapsed === null ? window.innerWidth < 768 : filtersCollapsed === 'true';
  // On phones the filters are an overlay drawer: always start closed and never persist the open state.
  const mobileMq = window.matchMedia('(max-width: 767px)');
  if (mobileMq.matches) filtersCollapsed = true;

  function renderFiltersToggle() {
    $('filters').hidden = filtersCollapsed;
    $('filters-backdrop').hidden = filtersCollapsed || !mobileMq.matches;
    const active = state.product.size + state.type.size + state.tags.size + (state.q ? 1 : 0) + (state.archived !== 'hide' ? 1 : 0) + (state.starred ? 1 : 0);
    const b = $('toggle-filters');
    b.textContent = (filtersCollapsed ? 'Show filters' : 'Hide filters') + (active ? ` (${active} active)` : '');
    b.setAttribute('aria-expanded', String(!filtersCollapsed));
  }

  // When archived tools are hidden, tell users if some would have matched.
  function archivedHint() {
    if (state.archived !== 'hide') return '';
    const n = tools.filter((t) => t.archived && matches(t, 'include')).length;
    return n ? ` ${n} archived ${n === 1 ? 'tool matches' : 'tools match'}: choose "Include archived" under Archived in the filters.` : '';
  }

  // ---- featured band -----------------------------------------------------
  // Only on the plain default view: no search or filters, archived hidden, first page.
  const FEATURED_KEY = 'featuredCollapsed';
  let featuredCollapsed = false;
  try { featuredCollapsed = localStorage.getItem(FEATURED_KEY) === 'true'; } catch (e) { /* storage unavailable */ }

  function renderFeatured() {
    const box = $('featured');
    const plain = !state.q && !state.product.size && !state.type.size && !state.tags.size
      && !state.starred && state.archived === 'hide' && state.page === 1;
    const items = plain
      ? tools.filter((t) => t.featured && !t.archived).sort((a, b) => a.name.localeCompare(b.name))
      : [];
    box.hidden = !items.length;
    if (!items.length) { box.replaceChildren(); return; }
    const body = el('div', { id: 'featured-body' }, [state.view === 'table' ? tableView(items, true) : cardsView(items, true)]);
    body.hidden = featuredCollapsed;
    const toggleBtn = el('button', {
      type: 'button', class: 'featured-toggle', 'aria-controls': 'featured-body', 'aria-expanded': String(!featuredCollapsed),
    }, [document.createTextNode(`Featured (${items.length})`)]);
    toggleBtn.addEventListener('click', () => {
      featuredCollapsed = !featuredCollapsed;
      try { localStorage.setItem(FEATURED_KEY, featuredCollapsed); } catch (e) { /* storage unavailable */ }
      body.hidden = featuredCollapsed;
      toggleBtn.setAttribute('aria-expanded', String(!featuredCollapsed));
      box.classList.toggle('collapsed', featuredCollapsed);
    });
    box.classList.toggle('collapsed', featuredCollapsed);
    box.replaceChildren(el('h2', { id: 'featured-title', class: 'featured-title' }, [toggleBtn]), body);
  }

  // ---- main render -------------------------------------------------------
  function render() {
    const list = sorted(tools.filter((t) => matches(t)));
    // "Total" is what the Archived setting alone would show, so the count isn't misleading.
    const total = tools.filter((t) => state.archived === 'include' || (state.archived === 'only') === !!t.archived).length;
    const totalPages = Math.max(1, Math.ceil(list.length / state.size));
    state.page = Math.min(state.page, totalPages);
    const start = (state.page - 1) * state.size;
    const page = list.slice(start, start + state.size);

    saveHash();
    renderFilters();
    renderToolbar();
    renderFiltersToggle();

    $('count').textContent = list.length
      ? `Showing ${start + 1}–${start + page.length} of ${list.length}` + (list.length < total ? ` (${total} total)` : '')
      : `Showing 0 of ${total}`;
    renderFeatured();
    $('results').replaceChildren(list.length
      ? (state.view === 'table' ? tableView(page) : cardsView(page))
      : el('p', { text: 'No tools match the current filters.' + archivedHint() }));
    renderPager(totalPages);
  }

  // ---- wiring ------------------------------------------------------------
  $('sort').replaceChildren(...Object.entries(SORTS).map(([k, v]) => el('option', { value: k, text: v })));
  $('size').replaceChildren(...PAGE_SIZES.map((n) => el('option', { value: String(n), text: `${n} per page` })));

  $('search').addEventListener('input', (e) => { state.q = e.target.value.trim(); changed(); });
  $('sort').addEventListener('change', (e) => { state.sort = e.target.value; changed(); });
  $('size').addEventListener('change', (e) => { state.size = parseInt(e.target.value, 10); changed(); });
  $('view-cards').addEventListener('click', () => { state.view = 'cards'; render(); });
  $('view-table').addEventListener('click', () => { state.view = 'table'; render(); });
  $('toggle-filters').addEventListener('click', () => {
    filtersCollapsed = !filtersCollapsed;
    if (!mobileMq.matches) { try { localStorage.setItem(FILTERS_KEY, filtersCollapsed); } catch (e) { /* storage unavailable */ } }
    renderFiltersToggle();
  });
  function closeDrawer() { if (mobileMq.matches && !filtersCollapsed) { filtersCollapsed = true; renderFiltersToggle(); $('toggle-filters').focus(); } }
  $('filters-backdrop').addEventListener('click', closeDrawer);
  $('filters-done').addEventListener('click', closeDrawer);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeDrawer(); });
  mobileMq.addEventListener('change', (e) => { if (e.matches) filtersCollapsed = true; renderFiltersToggle(); });
  $('clear').addEventListener('click', () => {
    state.q = ''; $('search').value = '';
    state.product.clear(); state.type.clear(); state.tags.clear(); state.starred = false; state.archived = DEFAULTS.archived;
    changed();
  });
  window.addEventListener('hashchange', () => { loadHash(); render(); });

  // Theme toggle (persisted) and header dropdown menu
  const SUN = '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
  const MOON = '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z"/></svg>';
  function applyTheme(dark) {
    const root = document.documentElement;
    if (dark) { root.setAttribute('cds-theme', 'dark'); root.dataset.theme = 'dark'; }
    else { root.removeAttribute('cds-theme'); delete root.dataset.theme; }
    const btn = $('theme-toggle');
    btn.innerHTML = dark ? SUN : MOON;
    btn.setAttribute('aria-label', dark ? 'Switch to light mode' : 'Switch to dark mode');
  }
  applyTheme(document.documentElement.dataset.theme === 'dark');
  $('theme-toggle').addEventListener('click', () => {
    const dark = document.documentElement.dataset.theme !== 'dark';
    applyTheme(dark);
    try { localStorage.setItem('theme', dark ? 'dark' : 'light'); } catch (e) { /* storage unavailable */ }
  });
  const menuBtn = $('menu-btn'), menu = $('app-menu');
  function setMenu(open) { menu.hidden = !open; menuBtn.setAttribute('aria-expanded', String(open)); }
  menuBtn.addEventListener('click', (e) => { e.stopPropagation(); setMenu(menu.hidden); });
  document.addEventListener('click', (e) => { if (!menu.contains(e.target)) setMenu(false); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') { setMenu(false); menuBtn.focus(); } });

  // Clicking the site title resets to the default view (clears the hash) and reloads.
  $('home').addEventListener('click', (e) => {
    e.preventDefault();
    history.replaceState(null, '', location.pathname + location.search);
    location.reload();
  });

  loadHash();
  render();
})();
