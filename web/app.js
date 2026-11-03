/* Subsurface agent web interface. No build step and no libraries: a hash router over four views that read the
   local JSON API served by `subsurface web`. */
(() => {
  'use strict';

  // ── helpers ───────────────────────────────────────────────────────────────
  const $ = (sel, el = document) => el.querySelector(sel);
  const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));
  const view = $('[data-view]');
  const tip = $('[data-tip]');
  const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ESC[c]);
  const pct = (v, d = 1) => (v == null || Number.isNaN(v) ? '–' : `${(100 * v).toFixed(d)}%`);
  const num = (v, d = 2) => (v == null || Number.isNaN(+v) ? '–' : (+v).toFixed(d));
  const lead = (cell) => parseFloat(String(cell)) || 0;
  // Round depth ticks (every 5, 10, 20, 25, 50 or 100 ft) inside [d0, d1].
  function depthTicks(d0, d1, target = 6) {
    const step = [5, 10, 20, 25, 50, 100, 200, 500].find((s) => (d1 - d0) / s <= target) || 1000;
    const out = [];
    for (let v = Math.ceil(d0 / step) * step; v <= d1 + 1e-9; v += step) out.push(v);
    return out;
  }
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;

  async function api(path, options) {
    const res = await fetch(path, options);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `${res.status} ${res.statusText}`);
    return data;
  }
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private mode */ } },
  };

  const SYSTEM_INFO = {
    b0: ['B0 fixed pipeline', 'Fixed steps, no LLM'],
    b2: ['B2 LogACF-style', 'Planner and reviewer'],
    full: ['Proposed (full)', 'G1, G2 and G3 on'],
    no_g1: ['Without G1', 'No grounding check'],
    no_g2: ['Without G2', 'No file verifier'],
    no_g3: ['Without G3', 'No evidence gate'],
  };
  const FAMILY = {
    prediction: 'Prediction', artifact_fault: 'Faulty file', missing_unit: 'Missing unit', vague_well: 'Vague well',
    unknown_well: 'Unknown well', out_of_range: 'Out of range', unsupported: 'Unsupported',
  };
  const G1_CODES = /^(UNGROUNDED|INTERVAL_OUT_OF_RANGE)/;
  const G2_CODES = /^(ARTIFACT_|RECOMPUTE_|MISSING_ARTIFACT|NONFINITE|DUPLICATE|SCHEMA|BOUNDS|STALE)/;

  const state = { status: null, runs: null, tables: null, job: null, poll: null,
                  filters: { system: 'full', family: '', outcome: 'all', q: '', page: 0 } };

  // ── theme ─────────────────────────────────────────────────────────────────
  const themeBtn = $('[data-theme-toggle]');
  function syncThemeLabel() {
    const dark = document.documentElement.dataset.theme === 'dark';
    themeBtn.setAttribute('aria-label', dark ? 'Switch to light theme' : 'Switch to dark theme');
  }
  themeBtn.addEventListener('click', () => {
    const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    store.set('ss-theme', next);
    syncThemeLabel();
  });
  syncThemeLabel();

  // ── mobile navigation ─────────────────────────────────────────────────────
  const rail = $('[data-rail]'), scrim = $('[data-scrim]'), menuBtn = $('[data-menu]');
  function setMenu(open) {
    rail.classList.toggle('open', open);
    scrim.hidden = !open;
    menuBtn.setAttribute('aria-expanded', String(open));
  }
  menuBtn.addEventListener('click', () => setMenu(!rail.classList.contains('open')));
  scrim.addEventListener('click', () => setMenu(false));

  // ── status chip ───────────────────────────────────────────────────────────
  async function loadStatus() {
    try {
      state.status = await api('/api/status');
      const chip = $('[data-keystate]');
      chip.hidden = false;
      chip.className = 'key-state ' + (state.status.api_key ? 'on' : 'off');
      chip.textContent = state.status.api_key ? `Gemini key found` : 'No Gemini key';
      chip.title = state.status.api_key ? `Live runs use ${state.status.model}` : 'Add GEMINI_API_KEY to .env to run the LLM systems';
    } catch (e) { /* status is optional */ }
  }
  const getRuns = async () => (state.runs ||= await api('/api/runs'));
  const getTables = async () => (state.tables ||= await api('/api/tables'));

  // ── router ────────────────────────────────────────────────────────────────
  const ROUTES = { '': ['overview', 'Overview', renderOverview], runs: ['runs', 'Saved runs', renderRuns],
                   live: ['live', 'New run', renderLive], results: ['results', 'Results', renderResults],
                   about: ['about', 'How it works', renderAbout] };
  function route() {
    const parts = location.hash.replace(/^#\/?/, '').split('/').filter(Boolean).map(decodeURIComponent);
    let [key, crumb, fn] = ROUTES[parts[0] || ''] || ROUTES[''];
    let arg = null;
    if (parts[0] === 'runs' && parts[1]) { arg = parts[1]; crumb = 'Run'; fn = renderDetail; }
    $$('[data-nav]').forEach((a) => (a.dataset.nav === key ? a.setAttribute('aria-current', 'page') : a.removeAttribute('aria-current')));
    $('[data-crumb]').textContent = crumb;
    document.title = `${crumb} · Subsurface Agent`;
    setMenu(false);
    hideTip();
    window.scrollTo(0, 0);
    view.innerHTML = '<div class="loading">Loading</div>';
    Promise.resolve(fn(arg)).catch((e) => {
      view.innerHTML = `<div class="view"><p class="kicker">Something went wrong</p><h1>Could not load this page</h1><p class="lede">${esc(e.message)}</p></div>`;
    });
  }
  window.addEventListener('hashchange', route);

  function reveal(root = view) {
    const items = $$('.reveal', root);
    if (reduced || !('IntersectionObserver' in window)) { items.forEach((el) => el.classList.add('in')); return; }
    const io = new IntersectionObserver((entries) => entries.forEach((en) => {
      if (en.isIntersecting) { en.target.classList.add('in'); io.unobserve(en.target); }
    }), { rootMargin: '0px 0px -8% 0px' });
    items.forEach((el) => io.observe(el));
  }

  // ── overview ──────────────────────────────────────────────────────────────
  async function renderOverview() {
    const [runs, tables] = await Promise.all([getRuns(), getTables()]);
    const main = tables.tables.e2_e4_main_comparison.rows;
    const row = (prefix) => main.find((r) => r[0].startsWith(prefix)) || [prefix, 0, 0, 0];
    const task = row('Task success'), g1 = row('G1: must-not-answer'), g2 = row('G2: silent errors'),
          g3 = row('G3: answers above'), g3cov = row('G3: prediction requests answered');
    const bars = (r, invert = false) => ['B0 fixed pipeline', 'B2 LogACF-style', 'Proposed (full)'].map((who, i) => {
      const v = lead(r[i + 1]);
      return `<div class="bar-row ${i === 2 ? 'ours' : ''}"><span class="who">${who}</span>
        <span class="bar-track" aria-hidden="true"><span class="bar-fill" data-w="${v}"></span></span>
        <span class="val">${v.toFixed(1)}%</span></div>`;
    }).join('');

    view.innerHTML = `<div class="view">
      <section class="hero">
        <div>
          <p class="kicker">AI4015 · Project G3-03</p>
          <h1>Well-log answers you can <em>check</em>.</h1>
          <p class="lede">A Gemini agent reads well logs from the Volve field through six tools, predicts porosity,
            water saturation and shale volume with a frozen random forest, and stops to ask or refuses when the
            request or the evidence is not good enough.</p>
          <div class="hero-actions">
            <a class="act" href="#/runs">Explore the saved runs</a>
            <a class="quiet" href="#/live">Start a new run</a>
          </div>
          <div class="hero-meta">
            <span><b>${runs.length}</b>saved runs</span>
            <span><b>50</b>test requests</span>
            <span><b>${lead(task[3]).toFixed(1)}%</b>task success</span>
          </div>
        </div>
        <figure class="core" data-core aria-label="Predicted and reference logs from a saved run"></figure>
      </section>

      <div class="section-head reveal"><h2>Three gaps, three components</h2><span class="aside">Each can be switched off for the ablation</span></div>
      <div class="gaps">
        <article class="panel ruled-top gap reveal" style="--rule: rgb(var(--g1))">
          <span class="tag">G1 · Grounding</span>
          <h3>Ask before guessing</h3>
          <p>Every tool argument must come from the request. A missing unit, a vague well or an unsupported quantity
            becomes a question, not an assumption.</p>
          <div class="big"><b>${lead(g1[3]).toFixed(0)}%</b><span>of must-not-answer requests handled</span></div>
          <div class="bars">${bars(g1)}</div>
          <span class="verdict">Fully addressed</span>
        </article>
        <article class="panel ruled-top gap reveal" style="--rule: rgb(var(--g2))">
          <span class="tag">G2 · Verification</span>
          <h3>Check the file, not the story</h3>
          <p>The prediction file is checked for identity, duplicates, bad values and a full recompute, and remade up
            to twice if it is broken.</p>
          <div class="big"><b>${lead(g2[3]).toFixed(0)}%</b><span>silent errors on faulty files</span></div>
          <div class="bars">${bars(g2)}</div>
          <span class="verdict">Fully addressed</span>
        </article>
        <article class="panel ruled-top gap reveal" style="--rule: rgb(var(--g3))">
          <span class="tag">G3 · Acceptance</span>
          <h3>Answer only with evidence</h3>
          <p>The spread of the forest's trees measures how unsure the model is. Above a limit set on validation wells,
            the agent refuses.</p>
          <div class="big"><b>${lead(g3[3]).toFixed(0)}%</b><span>bad answers among those given, at ${lead(g3cov[3]).toFixed(0)}% coverage</span></div>
          <div class="bars">${bars(g3)}</div>
          <span class="verdict">Partially addressed</span>
        </article>
      </div>

      <div class="section-head reveal"><h2>Overall</h2><span class="aside">Task success on all 50 test requests</span></div>
      <div class="panel reveal" style="padding: 22px 24px; max-width: 760px">
        <div class="bars">${bars(task)}</div>
        <p class="table-note">B2 is our reproduction of the base paper's planner and reviewer roles on the same tools and data.
          B2 and the proposed system ran three times each; B0 has no randomness and ran once.</p>
      </div>
    </div>`;

    reveal();
    // Bars grow when they come into view.
    requestAnimationFrame(() => setTimeout(() => $$('.bar-fill', view).forEach((b) => (b.style.width = `${b.dataset.w}%`)), 120));
    // The hero draws real logs from the first saved full-system answer.
    const pick = runs.find((r) => r.system === 'full' && r.family === 'prediction' && r.status === 'answer');
    if (pick) {
      api(`/api/runs/${encodeURIComponent(pick.run_id)}`).then((d) => {
        const s = d.series[0];
        if (s && $('[data-core]')) drawCore($('[data-core]'), s, pick);
      }).catch(() => {});
    }
  }

  function drawCore(fig, s, run) {
    const W = 420, H = 440, top = 28, left = 46, gap = 14, tw = (W - left - gap * 2) / 3;
    const n = s.depth.length, d0 = s.depth[0], d1 = s.depth[n - 1];
    const y = (d) => top + ((d - d0) / (d1 - d0 || 1)) * (H - top - 8);
    const tracks = [['PHIF', 0, 0.35], ['SW', 0, 1], ['VSH', 0, 1]];
    let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Three log tracks for well ${s.well}">`;
    for (const dv of depthTicks(d0, d1, 5)) {
      svg += `<line class="tick major" x1="${left - 8}" x2="${left - 2}" y1="${y(dv)}" y2="${y(dv)}"/>
              <text class="lbl" x="${left - 11}" y="${y(dv) + 3}" text-anchor="end">${Math.round(dv)}</text>`;
    }
    for (let i = 0; i <= 25; i++) { const yy = top + (i * (H - top - 8)) / 25; svg += `<line class="tick" x1="${left - 5}" x2="${left - 2}" y1="${yy}" y2="${yy}"/>`; }
    tracks.forEach(([t, lo, hi], k) => {
      const x0 = left + k * (tw + gap);
      const x = (v) => x0 + 4 + ((Math.min(Math.max(v, lo), hi) - lo) / (hi - lo)) * (tw - 8);
      const path = (vals) => vals.map((v, i) => (v == null ? null : `${x(v).toFixed(1)},${y(s.depth[i]).toFixed(1)}`))
        .filter(Boolean).map((p, i) => (i ? 'L' : 'M') + p).join('');
      svg += `<rect class="frame" x="${x0}" y="${top}" width="${tw}" height="${H - top - 8}"/>
              <text class="head" x="${x0 + tw / 2}" y="${top - 10}" text-anchor="middle">${t}</text>`;
      if (s.truth) svg += `<path class="curve truth draw" pathLength="1" style="animation-delay:${0.15 + k * 0.25}s" d="${path(s.truth[t])}"/>`;
      svg += `<path class="curve pred draw" pathLength="1" style="animation-delay:${0.5 + k * 0.25}s" d="${path(s.pred[t])}"/>`;
    });
    svg += `<line class="scan" x1="${left}" x2="${W}" y1="${top}" y2="${top}" style="--scan-h:${H - top - 8}px"/></svg>`;
    fig.innerHTML = svg + `<figcaption class="caption note">Well ${s.well}, ${Math.round(d0)} to ${Math.round(d1)} ft:
      predicted logs (solid) over the reference logs (faint), from saved run
      <a href="#/runs/${encodeURIComponent(run.run_id)}">${esc(run.case_id)}</a>.</figcaption>`;
  }

  // ── saved runs ────────────────────────────────────────────────────────────
  const PAGE = 25;
  function filtered(runs) {
    const f = state.filters, q = f.q.trim().toLowerCase();
    return runs.filter((r) => (!f.system || r.system === f.system) && (!f.family || r.family === f.family)
      && (f.outcome === 'all' || (f.outcome === 'yes') === !!r.task_correct)
      && (!q || `${r.query} ${r.case_id} ${r.run_id}`.toLowerCase().includes(q)));
  }
  const checkMark = (ok) => ok
    ? '<span class="tick-mark yes"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5 10 17l9-10"/></svg>Correct</span>'
    : '<span class="tick-mark no"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>Wrong</span>';

  async function renderRuns() {
    const runs = await getRuns();
    const f = state.filters;
    const opt = (v, label, cur) => `<option value="${esc(v)}" ${v === cur ? 'selected' : ''}>${esc(label)}</option>`;
    view.innerHTML = `<div class="view">
      <p class="kicker">Evidence</p>
      <h1>Saved runs</h1>
      <p class="lede">Every run of the final evaluation, with its full trajectory. Pick one to see each tool call, what
        the safety components decided, and the predicted logs against the reference logs.</p>
      <div class="filters" role="search">
        <div class="field"><label for="f-sys">System</label>
          <select id="f-sys" class="select" data-f="system">${opt('', 'All systems', f.system)}${Object.entries(SYSTEM_INFO).map(([k, v]) => opt(k, v[0], f.system)).join('')}</select></div>
        <div class="field"><label for="f-fam">Request type</label>
          <select id="f-fam" class="select" data-f="family">${opt('', 'All types', f.family)}${Object.entries(FAMILY).map(([k, v]) => opt(k, v, f.family)).join('')}</select></div>
        <div class="field"><span class="label" id="f-out">Outcome</span>
          <div class="seg" role="group" aria-labelledby="f-out">${[['all', 'All'], ['yes', 'Correct'], ['no', 'Wrong']].map(([k, v]) => `<button type="button" data-outcome="${k}" aria-pressed="${f.outcome === k}">${v}</button>`).join('')}</div></div>
        <div class="field search"><label for="f-q">Search</label>
          <input id="f-q" class="input" type="search" placeholder="Well, depth, case id…" value="${esc(f.q)}" data-f="q"></div>
        <span class="count" data-count aria-live="polite"></span>
      </div>
      <div data-list></div>
    </div>`;
    const draw = () => {
      const rows = filtered(runs), pages = Math.max(1, Math.ceil(rows.length / PAGE));
      f.page = Math.min(f.page, pages - 1);
      const slice = rows.slice(f.page * PAGE, f.page * PAGE + PAGE);
      $('[data-count]').textContent = `${rows.length} of ${runs.length} runs`;
      $('[data-list]').innerHTML = rows.length ? `<div class="table-wrap"><table>
        <thead><tr><th>Request</th><th>System</th><th class="hide-sm">Repeat</th><th>Outcome</th><th>Scored</th>
          <th class="num hide-sm">Tool calls</th><th class="num hide-sm">Latency</th></tr></thead>
        <tbody>${slice.map((r) => `<tr class="clickable" tabindex="0" data-run="${esc(r.run_id)}">
          <td><div class="req">${esc(r.query)}</div><div class="case-id">${esc(r.case_id)} · ${esc(FAMILY[r.family] || r.family)}${r.fault ? ` · ${esc(r.fault.replace(/_/g, ' '))}` : ''}</div></td>
          <td>${esc(r.system_label)}</td><td class="hide-sm mono">r${r.repeat}</td>
          <td><span class="chip ${esc(r.status)}">${esc(r.status)}</span></td><td>${checkMark(r.task_correct)}</td>
          <td class="num hide-sm">${r.tool_calls}</td><td class="num hide-sm">${num(r.latency_seconds, 1)} s</td></tr>`).join('')}</tbody>
        </table></div>
        <div class="pager"><span>Page ${f.page + 1} of ${pages}</span>
          <div class="seg"><button type="button" data-page="-1" ${f.page ? '' : 'disabled'} aria-label="Previous page">←</button>
          <button type="button" data-page="1" ${f.page < pages - 1 ? '' : 'disabled'} aria-label="Next page">→</button></div></div>`
        : `<div class="empty"><h3>No runs match</h3><p>Try another system, request type or search.</p></div>`;
    };
    draw();
    const root = $('.view', view);
    root.addEventListener('input', (e) => {
      const key = e.target.dataset.f;
      if (key) { f[key] = e.target.value; f.page = 0; draw(); }
    });
    root.addEventListener('click', (e) => {
      const out = e.target.closest('[data-outcome]');
      if (out) { f.outcome = out.dataset.outcome; f.page = 0; $$('[data-outcome]').forEach((b) => b.setAttribute('aria-pressed', String(b === out))); draw(); return; }
      const pg = e.target.closest('[data-page]');
      if (pg) { f.page += +pg.dataset.page; draw(); $('[data-list]').scrollIntoView({ block: 'nearest' }); return; }
      const tr = e.target.closest('[data-run]');
      if (tr) location.hash = `#/runs/${encodeURIComponent(tr.dataset.run)}`;
    });
    root.addEventListener('keydown', (e) => {
      const tr = e.target.closest('[data-run]');
      if (tr && e.key === 'Enter') location.hash = `#/runs/${encodeURIComponent(tr.dataset.run)}`;
    });
  }

  // ── trajectory ────────────────────────────────────────────────────────────
  function describe(ev) {
    const r = ev.result || {}, a = ev.arguments || {};
    const flags = [];
    let body = '';
    if (!r.ok && r.error) {
      if (G1_CODES.test(r.error)) flags.push(['g1', 'G1 blocked']);
      else if (G2_CODES.test(r.error)) flags.push(['g2', 'G2 caught a fault']);
      else flags.push(['err', 'Tool error']);
      body = `<b>${esc(r.error)}</b> ${esc(r.message || '')}`;
    } else if (ev.name === 'inspect_dataset') {
      body = `Dataset <b>${esc(r.dataset || '')}</b>, ${Object.keys(r.wells || {}).length} wells listed.`;
    } else if (ev.name === 'inspect_interval') {
      body = `Well <b>${esc(r.well)}</b>, ${num(r.depth_min_ft, 0)}–${num(r.depth_max_ft, 0)} ft, ${r.rows} rows, input coverage ${pct(r.input_coverage, 0)}.`;
    } else if (ev.name === 'predict_properties') {
      const m = r.mean_prediction || {};
      body = `${r.rows} rows predicted. Mean PHIF <b>${num(m.PHIF, 3)}</b>, SW <b>${num(m.SW, 3)}</b>, VSH <b>${num(m.VSH, 3)}</b>.`;
      const ev3 = r.evidence;
      if (ev3) {
        const weak = ev3.decision === 'abstain';
        flags.push(['g3', weak ? 'G3 refused: weak evidence' : 'G3 passed']);
        body += `<br>Model uncertainty <b>${num(ev3.model_uncertainty, 4)}</b> against a limit of ${num(ev3.max_model_uncertainty, 4)}${ev3.out_of_range_share != null ? `; ${pct(ev3.out_of_range_share)} of inputs outside the training range` : ''}.`;
      }
    } else if (ev.name === 'verify_predictions') {
      body = r.verified ? `File checked: <b>${r.rows} rows</b>${r.max_abs_recompute_difference != null ? `, recompute difference ${Number(r.max_abs_recompute_difference).toExponential(1)}` : ''}.` : esc(JSON.stringify(r));
      if (r.verified && r.max_abs_recompute_difference != null) flags.push(['g2', 'G2 verified']);
    } else if (ev.name === 'plot_logs') {
      body = `Plot saved (${r.rows} rows).`;
    } else if (ev.name === 'finish') {
      body = `<span class="chip ${esc(a.status)}">${esc(a.status)}</span> ${esc(a.reason || '')}`;
    }
    return { flags, body };
  }

  function stepHTML(ev, i) {
    const delay = reduced ? 0 : Math.min(i, 12) * 45;
    if (ev.event === 'role') {
      const o = ev.output || {};
      const text = ev.role === 'planner'
        ? `Decision <b>${esc(o.decision)}</b>${o.steps ? `; plan: ${esc(o.steps.join(' → '))}` : ''}. ${esc(o.reason || '')}`
        : `Decision <b>${esc(o.decision)}</b>. ${esc(o.reason || '')}`;
      return `<li class="step role" style="animation-delay:${delay}ms"><span class="node"></span>
        <div class="step-head"><span class="step-name">${esc(ev.role)}</span><span class="step-turn">LLM role</span></div>
        <div class="step-body">${text}</div></li>`;
    }
    if (ev.event === 'provider_error') {
      return `<li class="step err" style="animation-delay:${delay}ms"><span class="node"></span>
        <div class="step-head"><span class="step-name">provider error</span></div><div class="step-body">${esc(ev.message)}</div></li>`;
    }
    const { flags, body } = describe(ev);
    const ok = ev.result ? ev.result.ok : true;
    const cls = ev.name === 'finish' ? 'finish' : ok ? 'ok' : 'err';
    const args = Object.keys(ev.arguments || {}).length && ev.name !== 'finish'
      ? `<div class="step-args">${esc(Object.entries(ev.arguments).map(([k, v]) => `${k}=${typeof v === 'object' ? JSON.stringify(v) : v}`).join(', '))}</div>` : '';
    return `<li class="step ${cls}" style="animation-delay:${delay}ms"><span class="node"></span>
      <div class="step-head"><span class="step-name">${esc(ev.name)}</span>${ev.turn ? `<span class="step-turn">turn ${ev.turn}</span>` : ''}
        ${flags.map(([c, t]) => `<span class="flag ${c}">${esc(t)}</span>`).join('')}</div>
      ${args}<div class="step-body">${body}</div>
      ${ev.result ? `<details class="raw"><summary>Raw result</summary><pre>${esc(JSON.stringify(ev.result, null, 2))}</pre></details>` : ''}</li>`;
  }

  // ── well log chart with crosshair ─────────────────────────────────────────
  function drawLogs(host, s) {
    const W = 600, H = 470, top = 30, bottom = 10, left = 54, gap = 18, tw = (W - left - gap * 2) / 3;
    const n = s.depth.length, d0 = s.depth[0], d1 = s.depth[n - 1], ph = H - top - bottom;
    const y = (d) => top + ((d - d0) / (d1 - d0 || 1)) * ph;
    const maxOf = (t) => Math.max(...s.pred[t], ...(s.truth ? s.truth[t].filter((v) => v != null) : []));
    const tracks = [['PHIF', 0, Math.max(0.3, Math.ceil(maxOf('PHIF') * 20) / 20)], ['SW', 0, 1], ['VSH', 0, 1]];
    const xs = tracks.map(([, lo, hi], k) => { const x0 = left + k * (tw + gap); return (v) => x0 + ((Math.min(Math.max(v, lo), hi) - lo) / (hi - lo)) * tw; });
    let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Predicted and reference PHIF, SW and VSH against depth"><g class="axis">`;
    for (const dv of depthTicks(d0, d1, 7)) {
      svg += `<line x1="${left - 6}" x2="${W}" y1="${y(dv)}" y2="${y(dv)}"/><text x="${left - 10}" y="${y(dv) + 3.5}" text-anchor="end">${Math.round(dv)}</text>`;
    }
    svg += `<text x="${left - 10}" y="${top - 12}" text-anchor="end">ft</text></g>`;
    tracks.forEach(([t, lo, hi], k) => {
      const x0 = left + k * (tw + gap), x = xs[k];
      const path = (vals) => { let d = '', pen = false; vals.forEach((v, i) => { if (v == null) { pen = false; return; } d += `${pen ? 'L' : 'M'}${x(v).toFixed(1)},${y(s.depth[i]).toFixed(1)}`; pen = true; }); return d; };
      svg += `<rect class="track-box" x="${x0}" y="${top}" width="${tw}" height="${ph}"/>
        <text class="track-title" x="${x0}" y="${top - 12}">${t}</text>
        <g class="axis"><text x="${x0 + tw}" y="${top - 12}" text-anchor="end">${lo}–${hi}</text></g>`;
      if (s.truth) svg += `<path class="truth" d="${path(s.truth[t])}"/>`;
      svg += `<path class="pred" d="${path(s.pred[t])}"/>`;
    });
    svg += `<g data-hover style="display:none"><line class="cross" x1="${left}" x2="${W}" y1="0" y2="0"/>
      ${tracks.map(() => '<circle class="dot t" r="4"/><circle class="dot" r="4.5"/>').join('')}</g>
      <rect data-hit x="${left}" y="${top}" width="${W - left}" height="${ph}" fill="transparent"/></svg>`;
    host.innerHTML = `<div class="legend"><span><i></i>Predicted</span>${s.truth ? '<span><i class="t"></i>Reference (labels)</span>' : ''}</div>` + svg;

    const el = $('svg', host), g = $('[data-hover]', host), hit = $('[data-hit]', host);
    const line = $('line', g), dots = $$('circle', g);
    const move = (evt) => {
      const pt = el.createSVGPoint(); pt.x = evt.clientX; pt.y = evt.clientY;
      const p = pt.matrixTransform(el.getScreenCTM().inverse());
      const depth = d0 + ((p.y - top) / ph) * (d1 - d0);
      let lo = 0, hi = n - 1;
      while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (s.depth[mid] < depth) lo = mid; else hi = mid; }
      const i = Math.abs(s.depth[lo] - depth) < Math.abs(s.depth[hi] - depth) ? lo : hi;
      const yy = y(s.depth[i]);
      g.style.display = '';
      line.setAttribute('y1', yy); line.setAttribute('y2', yy);
      tracks.forEach(([t], k) => {
        const tv = s.truth ? s.truth[t][i] : null;
        dots[2 * k].style.display = tv == null ? 'none' : '';
        if (tv != null) { dots[2 * k].setAttribute('cx', xs[k](tv)); dots[2 * k].setAttribute('cy', yy); }
        dots[2 * k + 1].setAttribute('cx', xs[k](s.pred[t][i])); dots[2 * k + 1].setAttribute('cy', yy);
      });
      showTip(evt.clientX, evt.clientY, `<div class="t-head">${num(s.depth[i], 1)} ft</div>
        <div class="t-row"><span></span><span class="p">pred</span><span>ref</span></div>
        ${tracks.map(([t]) => `<div class="t-row"><span>${t}</span><span class="p">${num(s.pred[t][i], 3)}</span><span>${s.truth ? num(s.truth[t][i], 3) : '–'}</span></div>`).join('')}`);
    };
    hit.addEventListener('pointermove', move);
    hit.addEventListener('pointerdown', move);
    hit.addEventListener('pointerleave', () => { g.style.display = 'none'; hideTip(); });
  }
  function showTip(x, y, html) {
    tip.innerHTML = html; tip.hidden = false;
    const r = tip.getBoundingClientRect();
    let left = x + 16, top = y + 16;
    if (left + r.width > innerWidth - 8) left = x - r.width - 16;
    if (top + r.height > innerHeight - 8) top = y - r.height - 16;
    tip.style.left = `${Math.max(8, left)}px`; tip.style.top = `${Math.max(8, top)}px`;
  }
  function hideTip() { tip.hidden = true; }

  // ── run detail ────────────────────────────────────────────────────────────
  function detailBody(d) {
    const r = d.result, sc = d.score, u = r.usage || {}, gen = r.generation || {}, flags = r.config_flags || {};
    const oracle = r.oracle || {};
    const series = d.series[0];
    const facts = [
      ['System', SYSTEM_INFO[r.config] ? SYSTEM_INFO[r.config][0] : r.config],
      ['Components on', ['grounding', 'verification', 'acceptance'].filter((k) => flags[k]).map((k) => ({ grounding: 'G1', verification: 'G2', acceptance: 'G3' })[k]).join(', ') || 'none'],
      ['Model', r.model_version || '–'], ['Temperature · seed', gen.temperature != null ? `${gen.temperature} · ${gen.seed ?? '–'}` : '–'],
      ['LLM requests', r.provider_requests ?? '–'], ['Prompt · output tokens', `${(u.prompt_tokens || 0).toLocaleString()} · ${u.output_tokens || 0}`],
      ['Tool calls · errors', `${r.tool_calls} · ${r.tool_errors}`], ['Active latency', `${num(r.active_latency_seconds, 1)} s`],
    ];
    if (r.fault_injection) facts.push(['Injected fault', r.fault_injection.replace(/_/g, ' ')]);
    if (r.fault_injection && oracle.fault_applied != null) facts.push(['Hidden checker', oracle.final_artifacts_valid === false ? 'final file was faulty' : 'final file valid']);
    const score = sc ? [
      ['Expected', sc.expected], ['Scored', sc.task_correct ? 'correct' : 'wrong'],
      ...(sc.interval_error != null ? [['Interval RMSE (mean of 3)', num(sc.interval_error, 4)]] : []),
      ...(sc.silent_error ? [['Silent error', 'yes, answered from a faulty file']] : []),
      ...(sc.repaired ? [['Repaired', 'yes']] : []),
    ] : [];
    return `<div class="detail-grid">
      <section><div class="section-head" style="margin-top:0"><h2>Trajectory</h2><span class="aside">${r.trace.length} events</span></div>
        <ol class="timeline">${r.trace.map(stepHTML).join('')}</ol></section>
      <aside>
        <div class="panel side-card"><h3>Predicted logs</h3>
          ${series ? `<div class="logs" data-logs></div><p class="table-note">File ${esc(series.artifact)} · well ${esc(series.well)}. Hover to read values.</p>`
            : `<div class="empty"><h3>No prediction file</h3><p>${r.status === 'failed' ? 'The run stopped before a prediction was made.' : 'This run ended before predicting, as expected when a request has to be clarified or refused.'}</p></div>`}
        </div>
        ${score.length ? `<div class="panel side-card"><h3>Score</h3><ul class="facts">${score.map(([k, v]) => `<li><span class="k">${esc(k)}</span><span class="v">${esc(v)}</span></li>`).join('')}</ul></div>` : ''}
        <div class="panel side-card"><h3>Run record</h3><ul class="facts">${facts.map(([k, v]) => `<li><span class="k">${esc(k)}</span><span class="v">${esc(v)}</span></li>`).join('')}</ul></div>
      </aside></div>`;
  }

  async function renderDetail(id) {
    const d = await api(`/api/runs/${encodeURIComponent(id)}`);
    const r = d.result, sc = d.score;
    view.innerHTML = `<div class="view">
      <a class="back" href="${d.source === 'live' ? '#/live' : '#/runs'}">← ${d.source === 'live' ? 'New run' : 'Saved runs'}</a>
      <div class="detail-head">
        <p class="kicker">${esc(r.run_id)}</p>
        <h1>${esc(r.query)}</h1>
        <div class="detail-meta"><span class="chip ${esc(r.status)}">${esc(r.status)}</span>
          ${sc ? checkMark(sc.task_correct) : ''}<span>${esc(SYSTEM_INFO[r.config] ? SYSTEM_INFO[r.config][0] : r.config)}</span>
          ${sc ? `<span class="mono">repeat ${sc.repeat}</span>` : ''}<span class="muted">${esc(new Date(r.created_utc).toLocaleString())}</span></div>
        <p class="reason">${esc(r.reason)}</p>${providerHint(r)}
      </div>
      ${detailBody(d)}</div>`;
    if (d.series[0]) drawLogs($('[data-logs]'), d.series[0]);
  }

  // ── new run ───────────────────────────────────────────────────────────────
  const EXAMPLES = [
    ['Prediction', 'Predict PHIF, SW and VSH for well 3 from 10900 to 11000 ft.'],
    ['Meters', 'Predict PHIF, SW and VSH for well 7 between 4380 and 4410 m.'],
    ['Missing unit', 'Predict PHIF, SW and VSH for well 3 from 10600 to 10700.'],
    ['Unknown well', 'Predict PHIF, SW and VSH for well 12 from 9000 to 9100 ft.'],
    ['Unsupported', 'Estimate permeability for well 7 from 14300 to 14400 ft.'],
  ];
  async function renderLive() {
    const st = state.status || (await api('/api/status'));
    const sys = store.get('ss-system') || 'full';
    view.innerHTML = `<div class="view">
      <p class="kicker">Live</p>
      <h1>Start a new run</h1>
      <p class="lede">Write a request the way an analyst would. The run uses the same code as the evaluation and is saved
        to <span class="mono">logs/runs/</span>. LLM systems need a Gemini key in <span class="mono">.env</span>; B0 runs without one.</p>
      <div class="live-grid">
        <form class="panel compose" data-compose>
          <label class="label" for="q">Request</label>
          <textarea id="q" name="q" maxlength="400" required placeholder="Predict PHIF, SW and VSH for well 3 from 10900 to 11000 ft."></textarea>
          <div class="examples">${EXAMPLES.map(([k, v]) => `<button type="button" class="example" data-example="${esc(v)}"><b>${esc(k)}</b>${esc(v)}</button>`).join('')}</div>
          <p class="label" style="margin-top:22px">System</p>
          <div class="system-pick" role="group" aria-label="System">${Object.entries(SYSTEM_INFO).map(([k, [name, small]]) =>
            `<button type="button" data-system="${k}" aria-pressed="${k === sys}"><span>${esc(name)}</span><small>${esc(small)}</small></button>`).join('')}</div>
          <div class="compose-foot"><button class="act solid" type="submit" data-go>Run the agent</button>
            <span class="form-msg" data-msg aria-live="polite"></span></div>
        </form>
        <section data-side></section>
      </div>
      <div data-result></div></div>`;

    const form = $('[data-compose]'), msg = $('[data-msg]'), go = $('[data-go]');
    let system = sys;
    const checkKey = () => {
      const needKey = system !== 'b0' && !st.api_key;
      msg.className = 'form-msg' + (needKey || !st.data_ready ? ' bad' : '');
      msg.textContent = !st.data_ready ? 'Data not prepared: run subsurface download and subsurface prepare.'
        : needKey ? 'No GEMINI_API_KEY found in .env, so only B0 can run.' : '';
      go.disabled = needKey || !st.data_ready || !!(state.job && state.job.state === 'running');
    };
    checkKey();
    form.addEventListener('click', (e) => {
      const ex = e.target.closest('[data-example]');
      if (ex) { form.q.value = ex.dataset.example; form.q.focus(); }
      const sb = e.target.closest('[data-system]');
      if (sb) { system = sb.dataset.system; store.set('ss-system', system); $$('[data-system]').forEach((b) => b.setAttribute('aria-pressed', String(b === sb))); checkKey(); }
    });
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const query = form.q.value.trim();
      if (!query) { form.q.focus(); return; }
      go.disabled = true; msg.className = 'form-msg'; msg.textContent = 'Starting…';
      try {
        state.job = await api('/api/jobs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query, system }) });
        msg.textContent = '';
        $('[data-result]').innerHTML = '';
        pollJob();
      } catch (err) { msg.className = 'form-msg bad'; msg.textContent = err.message; go.disabled = false; }
    });
    if (state.job && state.job.state === 'running') pollJob(); else drawSide();
    if (state.job && state.job.state !== 'running') drawJob(state.job);
  }

  async function drawSide() {
    const side = $('[data-side]');
    if (!side || (state.job && state.job.state === 'running')) return;
    let list = [];
    try { list = await api('/api/live'); } catch (e) { /* optional */ }
    side.innerHTML = `<div class="section-head" style="margin-top:0"><h2>Runs from this page</h2></div>` + (list.length
      ? `<div class="table-wrap"><table><tbody>${list.map((r) => `<tr class="clickable" tabindex="0" data-run="${esc(r.run_id)}">
          <td><div class="req">${esc(r.query)}</div><div class="case-id">${esc(SYSTEM_INFO[r.config] ? SYSTEM_INFO[r.config][0] : r.config)} · ${esc(new Date(r.created_utc).toLocaleString())}</div></td>
          <td><span class="chip ${esc(r.status)}">${esc(r.status)}</span></td></tr>`).join('')}</tbody></table></div>`
      : `<div class="empty"><h3>Nothing yet</h3><p>Runs you start here are listed with their full record.</p></div>`);
    $$('[data-run]', side).forEach((tr) => {
      const open = () => (location.hash = `#/runs/${encodeURIComponent(tr.dataset.run)}`);
      tr.addEventListener('click', open);
      tr.addEventListener('keydown', (e) => e.key === 'Enter' && open());
    });
  }

  function pollJob() {
    clearTimeout(state.poll);
    const tick = async () => {
      try { state.job = await api(`/api/jobs/${state.job.id}`); } catch (e) { return; }
      if (!$('[data-compose]')) { if (state.job.state === 'running') state.poll = setTimeout(tick, 1500); return; }
      drawJob(state.job);
      if (state.job.state === 'running') state.poll = setTimeout(tick, 700);
    };
    drawJob(state.job);
    state.poll = setTimeout(tick, 500);
  }

  async function drawJob(job) {
    const side = $('[data-side]');
    if (!side) return;
    const go = $('[data-go]');
    if (go) go.disabled = job.state === 'running';
    const steps = [];
    job.steps.forEach((s) => {
      if (s.kind === 'call') steps.push({ name: s.name, args: s.args, state: 'pending' });
      if (s.kind === 'result') { const open = steps.find((x) => x.name === s.name && x.state === 'pending'); if (open) Object.assign(open, { state: s.ok ? 'ok' : 'err', error: s.error, message: s.message }); }
    });
    const thinking = job.state === 'running' && (!job.steps.length || job.steps[job.steps.length - 1].kind === 'thinking');
    side.innerHTML = `<div class="section-head" style="margin-top:0"><h2>${job.state === 'running' ? 'Running' : job.state === 'error' ? 'Stopped' : job.status === 'failed' ? 'Failed' : 'Finished'}</h2>
        <span class="aside mono">${num(job.elapsed, 1)} s</span></div>
      <p class="req">${esc(job.query)}</p>
      <p class="case-id">${esc(SYSTEM_INFO[job.system][0])} · ${esc(job.run_id)}</p>
      ${job.state === 'running' ? '<div class="progress-line"><i></i></div>' : '<div style="height:18px"></div>'}
      <ol class="timeline">${steps.map((s) => `<li class="step ${s.state === 'pending' ? 'pending' : s.name === 'finish' ? 'finish' : s.state}"><span class="node"></span>
          <div class="step-head"><span class="step-name">${esc(s.name)}</span>${s.error ? `<span class="flag ${G1_CODES.test(s.error) ? 'g1' : G2_CODES.test(s.error) ? 'g2' : 'err'}">${esc(s.error)}</span>` : ''}</div>
          ${s.args && Object.keys(s.args).length ? `<div class="step-args">${esc(Object.entries(s.args).map(([k, v]) => `${k}=${typeof v === 'object' ? JSON.stringify(v) : v}`).join(', '))}</div>` : ''}
          ${s.message ? `<div class="step-body">${esc(s.message)}</div>` : ''}</li>`).join('')}
        ${thinking ? `<li class="step pending"><span class="node"></span><div class="step-head"><span class="step-name">${job.system === 'b0' ? 'running fixed steps' : 'waiting for Gemini'}</span></div></li>` : ''}
      </ol>
      ${job.state === 'error' ? `<p class="form-msg bad" style="margin-top:14px">${esc(job.error)}</p>` : ''}`;
    if (job.state === 'done' && !job.rendered) {
      job.rendered = true;
      const d = await api(`/api/runs/${encodeURIComponent(job.run_id)}`);
      const host = $('[data-result]');
      if (!host) return;
      host.innerHTML = `<div class="section-head"><h2>Result</h2><span class="aside"><a href="#/runs/${encodeURIComponent(job.run_id)}">Open as its own page →</a></span></div>
        <div class="detail-meta" style="margin-top:0"><span class="chip ${esc(d.result.status)}">${esc(d.result.status)}</span></div>
        <p class="reason">${esc(d.result.reason)}</p>${providerHint(d.result)}${detailBody(d)}`;
      if (d.series[0]) drawLogs($('[data-logs]', host), d.series[0]);
      $('[data-go]') && ($('[data-go]').disabled = false);
    }
  }

  function providerHint(r) {
    const why = String(r.reason || '');
    if (r.status !== 'failed') return '';
    if (/HTTP 429|RESOURCE_EXHAUSTED/.test(why)) {
      return `<p class="form-msg bad" style="margin-top:12px;max-width:80ch">Gemini refused the request because this key's
        free quota is used up (HTTP 429). It resets daily; until then put another key in <span class="mono">.env</span>
        and run again, or pick B0, which needs no key.</p>`;
    }
    if (/HTTP 40[13]|PERMISSION|API key/i.test(why)) {
      return `<p class="form-msg bad" style="margin-top:12px;max-width:80ch">Gemini rejected the key. Check
        <span class="mono">GEMINI_API_KEY</span> in <span class="mono">.env</span>.</p>`;
    }
    if (/connection failed/i.test(why)) {
      return '<p class="form-msg bad" style="margin-top:12px">Could not reach Gemini. Check the internet connection.</p>';
    }
    return '';
  }

  // ── results ───────────────────────────────────────────────────────────────
  const TABLES = [
    ['gap_resolution', 'Gap resolution', 'B2 is the base-paper reproduction. Addressed means the component fixed the failure the gap names on our benchmark.'],
    ['e2_e4_main_comparison', 'E2–E4 comparison', 'Mean over runs, ± standard deviation across the three repeats, and a 95% bootstrap interval over cases in brackets.'],
    ['e5_ablation', 'E5 ablation', 'Each component switched off on the cases of its own gap.'],
    ['e6_efficiency', 'E6 efficiency', 'Per run averages. Latency excludes time spent waiting on the free-tier rate limit.'],
    ['e1_numerical_baseline', 'E1 baseline', 'Frozen random forest on the two test wells, against predicting the training mean.'],
    ['failure_categories', 'Failures', 'Failed runs of each system, grouped by what went wrong.'],
  ];
  const FIGS = {
    'fig_architecture.png': 'How a request moves through the agent and its three components.',
    'fig_gapwise.png': 'The main measure of each gap, for B0, B2 and the proposed system.',
    'fig_ablation.png': 'What changes when each component is switched off.',
    'fig_g3_tradeoff.png': 'Coverage against error as the G3 limit moves, on validation windows.',
    'fig_cost.png': 'LLM requests and tokens per run, B2 against the proposed system.',
  };
  async function renderResults() {
    const t = await getTables();
    let current = store.get('ss-table') || 'gap_resolution';
    if (!t.tables[current]) current = 'gap_resolution';
    view.innerHTML = `<div class="view">
      <p class="kicker">E1–E6</p><h1>Results</h1>
      <p class="lede">The tables and figures in the paper, read straight from <span class="mono">results/final/</span>.</p>
      <div class="tabs" role="tablist">${TABLES.map(([k, label]) => `<button role="tab" type="button" data-tab="${k}" aria-selected="${k === current}">${esc(label)}</button>`).join('')}</div>
      <div data-table role="tabpanel"></div>
      <div class="section-head reveal"><h2>Figures</h2></div>
      <div class="figs">${t.figures.map((f) => `<figure class="panel fig reveal"><a href="/figures/${encodeURIComponent(f)}" target="_blank" rel="noopener"><img src="/figures/${encodeURIComponent(f)}" alt="${esc(FIGS[f] || f)}" loading="lazy"></a>
        <figcaption><b>${esc(f.replace(/^fig_|\.png$/g, '').replace(/_/g, ' '))}</b>${esc(FIGS[f] || '')}</figcaption></figure>`).join('')}</div></div>`;
    const draw = () => {
      const tb = t.tables[current], note = TABLES.find((x) => x[0] === current)[2];
      const isNum = (c) => /^-?[\d.,]+%?( ± [\d.]+)?( \[[^\]]+\])?$/.test(c.trim());
      $('[data-table]').innerHTML = `<div class="table-wrap"><table><thead><tr>${tb.columns.map((c, i) => `<th class="${i ? 'num' : ''}">${esc(c)}</th>`).join('')}</tr></thead>
        <tbody>${tb.rows.map((r) => `<tr>${r.map((c, i) => `<td class="${i && isNum(c) ? 'num' : ''}">${esc(c).replace(/`([^`]+)`/g, '<span class="mono">$1</span>')}</td>`).join('')}</tr>`).join('')}</tbody></table></div>
        <p class="table-note">${esc(note)}</p>`;
    };
    draw();
    $('.tabs').addEventListener('click', (e) => {
      const b = e.target.closest('[data-tab]');
      if (!b) return;
      current = b.dataset.tab; store.set('ss-table', current);
      $$('[data-tab]').forEach((x) => x.setAttribute('aria-selected', String(x === b)));
      draw();
    });
    reveal();
  }

  // ── how it works ──────────────────────────────────────────────────────────
  function renderAbout() {
    view.innerHTML = `<div class="view">
      <p class="kicker">Method</p><h1>How a run works</h1>
      <p class="lede">The agent plans with Gemini through native function calling and can only act through six typed
        tools. Every call, its arguments and its result are written to the run record, which can be replayed offline.</p>
      <div class="section-head reveal"><h2>The six tools</h2></div>
      <ul class="ruled-list reveal">
        <li><span class="k">inspect_dataset</span><span class="v">Lists the wells, their depth ranges and the curves in the pinned dataset.</span></li>
        <li><span class="k">inspect_interval</span><span class="v">Cuts one well between two depths, converting meters to feet, and reports coverage.</span></li>
        <li><span class="k">predict_properties</span><span class="v">Runs the frozen random forest on that slice and saves a prediction file.</span></li>
        <li><span class="k">verify_predictions</span><span class="v">Checks that file before anyone relies on it.</span></li>
        <li><span class="k">plot_logs</span><span class="v">Draws the predicted logs when the request asks for a plot.</span></li>
        <li><span class="k">finish</span><span class="v">Ends the run as answer, clarify or abstain, with a short reason.</span></li>
      </ul>
      <div class="section-head reveal"><h2>Where the gaps act</h2></div>
      <ul class="ruled-list reveal">
        <li><span class="k" style="color:rgb(var(--g1))">G1 grounding</span><span class="v">Before a tool runs: its arguments must match what the request actually says.</span></li>
        <li><span class="k" style="color:rgb(var(--g2))">G2 verification</span><span class="v">After predicting: schema, identity, duplicates, finite values, bounds and a full recompute; up to two repairs.</span></li>
        <li><span class="k" style="color:rgb(var(--g3))">G3 acceptance</span><span class="v">Before answering: the spread across the forest's trees must be under a limit set on validation wells.</span></li>
      </ul>
      <div class="section-head reveal"><h2>Budgets and settings</h2></div>
      <ul class="ruled-list reveal">
        <li><span class="k">Model</span><span class="v">${esc((state.status && state.status.model) || 'gemini-3.5-flash-lite')}, temperature 1.0, seed equal to the repeat number.</span></li>
        <li><span class="k">Limits per run</span><span class="v">10 turns, 14 tool calls, 3 tool errors.</span></li>
        <li><span class="k">Data</span><span class="v">SPWLA 2021 Volve logs. Training wells 0, 2, 4, 6, 8; validation 1 and 5; test 3 and 7.</span></li>
        <li><span class="k">Command line</span><span class="v">Everything here is also available as <span class="mono">subsurface agent "…" --config full</span>.</span></li>
      </ul></div>`;
    reveal();
  }

  loadStatus();
  route();
})();
