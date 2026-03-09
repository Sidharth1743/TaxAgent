/**
 * Source Evidence Cards — glassmorphic cards with glow accents.
 */

const SourceCards = (() => {
  const container = () => document.getElementById('sourceCards');
  const countEl = () => document.getElementById('sourceCount');
  let cardCount = 0;

  const SOURCE_STYLES = {
    caclub:      { bg: '#3b82f6', label: 'CA', name: 'CAClubIndia',   accent: 'rgba(59,130,246,0.4)' },
    caclubindia: { bg: '#3b82f6', label: 'CA', name: 'CAClubIndia',   accent: 'rgba(59,130,246,0.4)' },
    taxtmi:      { bg: '#14b8a6', label: 'TM', name: 'TaxTMI',        accent: 'rgba(20,184,166,0.4)' },
    turbotax:    { bg: '#a855f7', label: 'TT', name: 'TurboTax',      accent: 'rgba(168,85,247,0.4)' },
    taxprofblog: { bg: '#f59e0b', label: 'TP', name: 'TaxProfBlog',   accent: 'rgba(245,158,11,0.4)' },
    indiankanoon:{ bg: '#ec4899', label: 'IK', name: 'Indian Kanoon', accent: 'rgba(236,72,153,0.4)' },
    casemine:    { bg: '#ef4444', label: 'CM', name: 'Casemine',      accent: 'rgba(239,68,68,0.4)' },
  };

  function inferSource(url, sourceName) {
    const text = ((url || '') + ' ' + (sourceName || '')).toLowerCase();
    if (text.includes('caclub')) return SOURCE_STYLES.caclub;
    if (text.includes('taxtmi')) return SOURCE_STYLES.taxtmi;
    if (text.includes('turbotax')) return SOURCE_STYLES.turbotax;
    if (text.includes('taxprofblog') || text.includes('taxprof')) return SOURCE_STYLES.taxprofblog;
    if (text.includes('indiankanoon') || text.includes('kanoon')) return SOURCE_STYLES.indiankanoon;
    if (text.includes('casemine')) return SOURCE_STYLES.casemine;
    return { bg: '#64748b', label: '??', name: sourceName || 'Source', accent: 'rgba(100,116,139,0.3)' };
  }

  function clearPlaceholder() {
    const c = container();
    if (!c) return;
    const empty = c.querySelector('.sources-empty');
    if (empty) empty.remove();
  }

  function updateCount() {
    const el = countEl();
    if (el) el.textContent = cardCount;
  }

  function addCard({ title, url, snippet, date, source, replyCount }) {
    clearPlaceholder();
    const c = container();
    if (!c) return;

    const style = inferSource(url, source);
    cardCount++;
    updateCount();

    const card = document.createElement('div');
    card.className = 'source-card';
    card.style.setProperty('--card-accent', style.bg);

    card.innerHTML = `
      <div class="source-card__header">
        <div class="source-card__logo" style="background:${style.bg};box-shadow:0 0 8px ${style.accent}">${style.label}</div>
        <span class="source-card__source">${style.name}</span>
        ${date ? `<span class="source-card__date">${escapeHtml(date)}</span>` : ''}
      </div>
      <div class="source-card__title">${escapeHtml(title || 'Untitled')}</div>
      ${snippet ? `<div class="source-card__snippet">${escapeHtml(snippet)}</div>` : ''}
      <div style="display:flex;align-items:center;justify-content:space-between;">
        ${url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener" class="source-card__link">${escapeHtml(shortenUrl(url))}</a>` : ''}
        ${replyCount ? `<span class="source-card__replies">${replyCount} replies</span>` : ''}
      </div>
    `;

    c.appendChild(card);
    c.scrollTop = c.scrollHeight;
  }

  function addFromToolResult(result) {
    if (!result) return;

    const claims = result.claims || [];
    claims.forEach(claim => {
      if (!claim) return;
      (claim.citations || []).forEach(url => {
        addCard({
          title: claim.claim || '',
          url,
          source: (result.sources || [])[0] || '',
        });
      });
    });

    if (!claims.length && result.bullets) {
      result.bullets.forEach(bullet => {
        const urlMatch = bullet.match(/https?:\/\/[^\s)]+/);
        addCard({
          title: bullet.replace(/^-\s*/, '').slice(0, 120),
          url: urlMatch ? urlMatch[0] : '',
          snippet: bullet,
        });
      });
    }

    if (result.legal_context) {
      const lc = result.legal_context;
      (lc.sections || []).forEach(s => {
        addCard({
          title: s.title || s.section || 'Law Section',
          url: s.url || '',
          snippet: s.text || s.snippet || '',
          source: 'indiankanoon',
        });
      });
      (lc.judgements || []).forEach(j => {
        addCard({
          title: j.title || 'Court Judgement',
          url: j.url || '',
          snippet: j.snippet || j.text || '',
          source: 'casemine',
        });
      });
    }
  }

  function clear() {
    const c = container();
    if (c) {
      c.innerHTML = `<div class="sources-empty">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" opacity="0.2"><path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 002 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0022 16z"/></svg>
        <p>Sources appear as the agent researches</p>
      </div>`;
    }
    cardCount = 0;
    updateCount();
  }

  function escapeHtml(str) {
    const d = document.createElement('div');
    d.textContent = str || '';
    return d.innerHTML;
  }

  function shortenUrl(url) {
    try {
      const u = new URL(url);
      return u.hostname.replace('www.', '') + u.pathname.slice(0, 20);
    } catch { return (url || '').slice(0, 40); }
  }

  return { addCard, addFromToolResult, clear };
})();
