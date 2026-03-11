'use strict';

/* ── Helpers ───────────────────────────────────────────────── */
const $ = id => document.getElementById(id);

function setKeyword(kw) {
  $('keyword').value = kw;
  $('keyword').focus();
}

function fmt(n) {
  if (n === undefined || n === null) return '—';
  return Number(n).toLocaleString();
}

function fmtScore(s) {
  return s != null ? s.toFixed(1) : '—';
}

/* ── Snipe ─────────────────────────────────────────────────── */
let activeSource = null;

function startSnipe() {
  const keyword = $('keyword').value.trim();
  if (!keyword) { $('keyword').focus(); return; }

  if (activeSource) { activeSource.close(); activeSource = null; }

  const minPrice     = $('minPrice').value;
  const pages        = $('pages').value;
  const topN         = $('topN').value;
  const detailScrape = $('detailScrape').checked;

  // UI reset
  $('snipeBtn').disabled = true;
  $('snipeBtn').textContent = '⏳ Sniping…';
  $('progressLog').innerHTML = '';
  $('progressTitle').textContent = `Locking onto "${keyword}"…`;
  $('progressSection').classList.remove('hidden');
  $('resultsSection').classList.add('hidden');
  $('verdictBanner').classList.add('hidden');

  window.scrollTo({ top: $('progressSection').offsetTop - 80, behavior: 'smooth' });

  const url = `/api/snipe?keyword=${encodeURIComponent(keyword)}`
    + `&min_price=${minPrice}&max_pages=${pages}&top_n=${topN}&detail_scrape=${detailScrape}`;

  const es = new EventSource(url);
  activeSource = es;

  es.onmessage = e => {
    let msg;
    try { msg = JSON.parse(e.data); } catch { return; }

    if (msg.type === 'progress') {
      appendLog(msg.message);
    } else if (msg.type === 'result') {
      es.close(); activeSource = null;
      renderResult(msg.data);
      resetBtn();
    } else if (msg.type === 'error') {
      appendLog('❌ ' + msg.message, 'error');
      resetBtn();
    } else if (msg.type === 'done') {
      es.close(); activeSource = null;
      resetBtn();
    }
  };

  es.onerror = () => {
    appendLog('Connection lost — try again.', 'error');
    es.close(); activeSource = null;
    resetBtn();
  };
}

// Allow Enter key in search box
$('keyword').addEventListener('keydown', e => { if (e.key === 'Enter') startSnipe(); });

function resetBtn() {
  $('snipeBtn').disabled = false;
  $('snipeBtn').innerHTML = '<span class="btn-icon">🎯</span> SNIPE IT';
}

function appendLog(msg, cls = '') {
  const line = document.createElement('div');
  line.className = 'log-line' + (cls ? ' ' + cls : '');
  // Colour certain keywords
  if (/✅|done|score/i.test(msg))  line.classList.add('green');
  if (/⚠️|warn/i.test(msg))        line.classList.add('warn');
  if (/❌|error|block/i.test(msg)) line.classList.add('error');
  line.textContent = '› ' + msg;
  $('progressLog').appendChild(line);
  $('progressLog').scrollTop = $('progressLog').scrollHeight;
}

/* ── Render results ────────────────────────────────────────── */
function renderResult(data) {
  // Scroll to results
  $('resultsSection').classList.remove('hidden');

  // Competition KPI
  const compCount = data.competition_count;
  $('kpiCompVal').textContent   = compCount > 0 ? fmt(compCount) : '?';
  $('kpiCompCount').textContent = compCount > 0 ? 'total results on Fiverr' : 'Could not determine';
  const badge = $('kpiCompBadge');
  badge.textContent  = data.competition_label;
  badge.className    = `kpi-badge badge-${data.competition_color}`;

  // Sniper Score KPI
  const score = data.sniper_score;
  $('kpiScoreVal').textContent   = fmtScore(score);
  $('kpiScoreLabel').textContent = data.sniper_label;
  animateGauge(score);

  // Queue KPIs
  $('kpiQueue').textContent    = fmt(data.total_queue_demand);
  $('kpiAvgQueue').textContent = `avg ${data.avg_orders_in_queue} orders / seller`;
  const top = data.gigs[0];
  if (top) {
    $('kpiTopQueue').textContent  = fmt(top.orders_in_queue) || '?';
    $('kpiTopSeller').textContent = '@' + top.seller;
  }

  // Verdict banner
  renderVerdict(data);

  // Keyword tag
  $('resultsKeyword').textContent = `"${data.keyword}" · $${data.gigs[0]?.price ?? '?'}+ packages`;

  // Gig cards
  $('gigCards').innerHTML = '';
  data.gigs.forEach((gig, i) => {
    $('gigCards').appendChild(buildGigCard(gig, i + 1));
  });

  $('progressTitle').textContent = '✅ Snipe complete';

  window.scrollTo({ top: $('resultsSection').offsetTop - 80, behavior: 'smooth' });
}

function animateGauge(score) {
  const arc = document.getElementById('gaugeFill');
  if (!arc) return;
  const total = 157; // half-circle circumference for r=50
  const fill  = (score / 100) * total;
  // Colour by score
  const color = score >= 70 ? '#1DBF73' : score >= 45 ? '#00ff9d' : score >= 20 ? '#f5c518' : '#e53e3e';
  arc.style.stroke = color;
  setTimeout(() => {
    arc.style.strokeDasharray = `${fill} ${total}`;
  }, 100);
}

function renderVerdict(data) {
  const banner = $('verdictBanner');
  const score  = data.sniper_score;
  const comp   = data.competition_count;
  const demand = data.total_queue_demand;
  banner.className = 'verdict-banner';
  banner.classList.remove('hidden');

  let icon, label, detail, cls;

  if (score >= 70 && comp < 5000 && demand > 10) {
    icon   = '🎯';
    label  = 'SNIPER SHOT — Pull the trigger!';
    detail = `Low competition (${fmt(comp)} sellers) + high demand (${fmt(demand)} orders in queue across top sellers). This niche is wide open.`;
    cls    = 'shot';
  } else if (score >= 70) {
    icon   = '🎯';
    label  = 'SNIPER SHOT';
    detail = `Strong opportunity score of ${fmtScore(score)}/100 — high demand relative to competition.`;
    cls    = 'shot';
  } else if (score >= 45) {
    icon   = '✅';
    label  = 'GOOD OPPORTUNITY';
    detail = `Decent demand with manageable competition. Sniper Score ${fmtScore(score)}/100 — worth exploring with strong positioning.`;
    cls    = 'good';
  } else if (score >= 20) {
    icon   = '⚠️';
    label  = 'MODERATE OPPORTUNITY';
    detail = `Score ${fmtScore(score)}/100. Competitive market — differentiate with a strong niche angle or unique offer.`;
    cls    = 'mod';
  } else {
    icon   = '🔴';
    label  = 'HIGHLY SATURATED';
    detail = `Score ${fmtScore(score)}/100. Very high competition with relatively low visible demand. Consider a more specific keyword.`;
    cls    = 'bad';
  }

  banner.classList.add(cls);
  $('verdictIcon').textContent  = icon;
  $('verdictLabel').textContent = label;
  $('verdictDetail').textContent = detail;
}

function buildGigCard(gig, rank) {
  const card = document.createElement('a');
  card.href   = gig.gig_url;
  card.target = '_blank';
  card.rel    = 'noopener noreferrer';
  card.className = `gig-card rank-${rank <= 3 ? rank : 'rest'} fade-up`;
  card.style.animationDelay = `${(rank - 1) * 0.04}s`;

  const rankMedal = rank === 1 ? '🥇' : rank === 2 ? '🥈' : rank === 3 ? '🥉' : `#${rank}`;
  const rankCls   = rank <= 3 ? `gig-rank r${rank}` : 'gig-rank';

  const ratingStr = gig.rating
    ? `<span class="gig-rating">★ ${gig.rating.toFixed(1)}</span> <span>(${fmt(gig.review_count)})</span>`
    : '';

  const levelStr  = gig.seller_level
    ? `<span class="gig-level">${gig.seller_level}</span>`
    : '';

  const queueNum = gig.orders_in_queue || 0;
  let queueCls   = 'gig-queue-badge none';
  let queueText  = 'No queue data';
  if (queueNum > 0) {
    queueCls  = queueNum >= 10 ? 'gig-queue-badge hot' : 'gig-queue-badge';
    queueText = `🔥 ${queueNum} in queue`;
  }

  const priceStr = gig.price > 0 ? `$${Math.round(gig.price).toLocaleString()}` : '—';

  card.innerHTML = `
    <div class="${rankCls}">${rankMedal}</div>
    <div class="gig-body">
      <div class="gig-title">${escHtml(gig.title)}</div>
      <div class="gig-meta">
        <span class="gig-seller">@${escHtml(gig.seller)}</span>
        ${ratingStr}
        ${levelStr}
      </div>
      <div class="gig-link">↗ fiverr.com</div>
    </div>
    <div class="gig-stats">
      <div class="gig-price">${priceStr}</div>
      <div class="${queueCls}">${queueText}</div>
      <div class="view-btn">View Gig →</div>
    </div>
  `;

  return card;
}

function escHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
