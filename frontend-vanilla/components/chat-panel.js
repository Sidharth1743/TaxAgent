/**
 * Chat panel — scrolling transcript with citation chips and shimmer loading.
 */

const ChatPanel = (() => {
  const container = () => document.getElementById('chatMessages');

  function clearPlaceholder() {
    const c = container();
    if (!c) return;
    const empty = c.querySelector('.chat-empty');
    if (empty) empty.remove();
  }

  function addUserMessage(text) {
    clearPlaceholder();
    const div = document.createElement('div');
    div.className = 'chat-msg chat-msg--user';
    div.textContent = text;
    container().appendChild(div);
    scrollToBottom();
  }

  function addAgentMessage(text, existingEl) {
    clearPlaceholder();
    if (existingEl) {
      // Append to existing streaming message
      const contentEl = existingEl.querySelector('.agent-content') || existingEl;
      contentEl.innerHTML += escapeHtml(text);
      scrollToBottom();
      return existingEl;
    }
    const div = document.createElement('div');
    div.className = 'chat-msg chat-msg--agent';
    div.innerHTML = `<div class="agent-content">${escapeHtml(text)}</div>`;
    container().appendChild(div);
    scrollToBottom();
    return div;
  }

  function addSystemMessage(text) {
    clearPlaceholder();
    const div = document.createElement('div');
    div.className = 'chat-msg chat-msg--tool';
    div.innerHTML = `<span class="spinner"></span>${escapeHtml(text)}`;
    container().appendChild(div);
    scrollToBottom();

    // Auto-remove spinner after 10s
    setTimeout(() => {
      const spinner = div.querySelector('.spinner');
      if (spinner) spinner.remove();
    }, 10000);
  }

  function addCitations(citations, agentEl) {
    if (!citations || !citations.length) return;
    const target = agentEl || container().querySelector('.chat-msg--agent:last-child');
    if (!target) return;

    // Deduplicate
    const unique = [...new Set(citations)];
    const wrap = document.createElement('div');
    wrap.className = 'citation-wrap';
    unique.forEach(url => {
      const a = document.createElement('a');
      a.className = 'citation-chip';
      a.href = url;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      try {
        const u = new URL(url);
        a.textContent = u.hostname.replace('www.', '').split('.')[0];
      } catch {
        a.textContent = url.slice(0, 24);
      }
      wrap.appendChild(a);
    });
    target.appendChild(wrap);
    scrollToBottom();
  }

  function scrollToBottom() {
    const c = container();
    if (c) {
      requestAnimationFrame(() => { c.scrollTop = c.scrollHeight; });
    }
  }

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  return { addUserMessage, addAgentMessage, addSystemMessage, addCitations, scrollToBottom };
})();
