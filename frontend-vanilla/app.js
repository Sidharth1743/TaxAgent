/**
 * TaxClarity — Main application controller.
 *
 * WebSocket audio client, ambient background particles, and UI orchestration.
 */

(() => {
  // ═══════════════════════════════════════════════════════════
  // Ambient Background Particles
  // ═══════════════════════════════════════════════════════════

  function initParticles() {
    const canvas = document.getElementById('bgParticles');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let w, h;
    const particles = [];
    const PARTICLE_COUNT = 60;

    function resize() {
      w = canvas.width = window.innerWidth;
      h = canvas.height = window.innerHeight;
    }
    resize();
    window.addEventListener('resize', resize);

    // Spawn particles
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      particles.push({
        x: Math.random() * w,
        y: Math.random() * h,
        r: Math.random() * 1.2 + 0.3,
        dx: (Math.random() - 0.5) * 0.15,
        dy: (Math.random() - 0.5) * 0.15,
        opacity: Math.random() * 0.3 + 0.05,
        hue: Math.random() * 60 + 240,  // blue-violet range
      });
    }

    function draw() {
      ctx.clearRect(0, 0, w, h);
      particles.forEach(p => {
        p.x += p.dx;
        p.y += p.dy;
        if (p.x < 0) p.x = w;
        if (p.x > w) p.x = 0;
        if (p.y < 0) p.y = h;
        if (p.y > h) p.y = 0;

        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = `hsla(${p.hue}, 60%, 70%, ${p.opacity})`;
        ctx.fill();
      });

      // Draw faint connections between nearby particles
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const dx = particles[i].x - particles[j].x;
          const dy = particles[i].y - particles[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 120) {
            ctx.beginPath();
            ctx.moveTo(particles[i].x, particles[i].y);
            ctx.lineTo(particles[j].x, particles[j].y);
            ctx.strokeStyle = `rgba(99, 115, 155, ${0.04 * (1 - dist / 120)})`;
            ctx.lineWidth = 0.5;
            ctx.stroke();
          }
        }
      }

      requestAnimationFrame(draw);
    }
    draw();
  }

  // ═══════════════════════════════════════════════════════════
  // State
  // ═══════════════════════════════════════════════════════════

  let ws = null;
  let isConnected = false;
  let isListening = false;
  let audioContext = null;
  let micStream = null;
  let micProcessor = null;
  let playbackQueue = [];
  let isPlaying = false;
  let currentAgentMsg = null;
  const userId = 'user_' + Math.random().toString(36).slice(2, 8);

  // ═══════════════════════════════════════════════════════════
  // WebSocket
  // ═══════════════════════════════════════════════════════════

  function connect() {
    if (ws && ws.readyState <= WebSocket.OPEN) return;

    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${proto}//${location.host}/ws/live`);
    ws.binaryType = 'arraybuffer';

    ws.onopen = () => {
      isConnected = true;
      updateStatus(true);
      ws.send(JSON.stringify({ type: 'config', user_id: userId }));
      VoiceOrb.setState('idle');
    };

    ws.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        handleAudioOutput(event.data);
      } else {
        try { handleServerMessage(JSON.parse(event.data)); }
        catch (e) { console.warn('Bad JSON:', e); }
      }
    };

    ws.onclose = () => {
      isConnected = false;
      updateStatus(false);
      VoiceOrb.setState('idle');
      setTimeout(connect, 3000);
    };

    ws.onerror = () => {
      VoiceOrb.setState('error');
    };
  }

  function updateStatus(online) {
    const el = document.getElementById('connectionStatus');
    if (!el) return;
    if (online) {
      el.className = 'status-badge status-badge--online';
      el.querySelector('.status-badge__text').textContent = 'Live';
    } else {
      el.className = 'status-badge status-badge--offline';
      el.querySelector('.status-badge__text').textContent = 'Offline';
    }
  }

  // ═══════════════════════════════════════════════════════════
  // Server Message Handler
  // ═══════════════════════════════════════════════════════════

  function handleServerMessage(msg) {
    switch (msg.type) {
      case 'connected':
        ChatPanel.addSystemMessage(`Connected to ${msg.model || 'Gemini Live'}`);
        break;

      case 'text':
        VoiceOrb.setState('speaking');
        currentAgentMsg = ChatPanel.addAgentMessage(msg.content, currentAgentMsg);
        break;

      case 'tool_call':
        VoiceOrb.setState('thinking');
        const argPreview = JSON.stringify(msg.args || {}).slice(0, 60);
        ChatPanel.addSystemMessage(`${msg.name}(${argPreview})`);
        break;

      case 'tool_result':
        if (msg.result) {
          SourceCards.addFromToolResult(msg.result);
          if (msg.result.claims) {
            const urls = msg.result.claims.flatMap(c => c.citations || []);
            if (urls.length && currentAgentMsg) {
              ChatPanel.addCitations(urls, currentAgentMsg);
            }
          }
          if (msg.name === 'save_to_memory' || msg.name === 'get_user_memory') {
            GraphPanel.refresh(userId);
          }
        }
        break;

      case 'turn_complete':
        currentAgentMsg = null;
        VoiceOrb.setState(isListening ? 'listening' : 'idle');
        break;

      case 'interrupted':
        currentAgentMsg = null;
        stopPlayback();
        VoiceOrb.setState('listening');
        break;

      case 'audio_level':
        VoiceOrb.setAudioLevel(msg.level || 0);
        break;

      case 'error':
        VoiceOrb.setState('error');
        ChatPanel.addSystemMessage(`Error: ${msg.message}`);
        break;
    }
  }

  // ═══════════════════════════════════════════════════════════
  // Mic Capture
  // ═══════════════════════════════════════════════════════════

  async function startMic() {
    if (micStream) return;
    try {
      micStream = await navigator.mediaDevices.getUserMedia({
        audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true }
      });

      audioContext = new AudioContext({ sampleRate: 16000 });
      const source = audioContext.createMediaStreamSource(micStream);
      micProcessor = audioContext.createScriptProcessor(4096, 1, 1);

      micProcessor.onaudioprocess = (e) => {
        if (!isListening || !ws || ws.readyState !== WebSocket.OPEN) return;
        const f32 = e.inputBuffer.getChannelData(0);
        const i16 = new Int16Array(f32.length);
        let sum = 0;
        for (let i = 0; i < f32.length; i++) {
          i16[i] = Math.max(-32768, Math.min(32767, Math.floor(f32[i] * 32767)));
          sum += f32[i] * f32[i];
        }
        ws.send(i16.buffer);
        VoiceOrb.setMicLevel(Math.min(1, Math.sqrt(sum / f32.length) * 5));
      };

      source.connect(micProcessor);
      micProcessor.connect(audioContext.destination);
      isListening = true;
      VoiceOrb.setState('listening');
    } catch (err) {
      console.error('Mic error:', err);
      VoiceOrb.setState('error');
      ChatPanel.addSystemMessage('Microphone denied. Use text input.');
    }
  }

  function stopMic() {
    isListening = false;
    if (micProcessor) { micProcessor.disconnect(); micProcessor = null; }
    if (micStream) { micStream.getTracks().forEach(t => t.stop()); micStream = null; }
    if (audioContext) { audioContext.close(); audioContext = null; }
    VoiceOrb.setState('idle');
  }

  // ═══════════════════════════════════════════════════════════
  // Audio Playback
  // ═══════════════════════════════════════════════════════════

  function handleAudioOutput(buf) {
    playbackQueue.push(buf);
    if (!isPlaying) playNext();
  }

  async function playNext() {
    if (!playbackQueue.length) { isPlaying = false; return; }
    isPlaying = true;
    VoiceOrb.setState('speaking');
    const buf = playbackQueue.shift();
    try {
      const ctx = new AudioContext({ sampleRate: 24000 });
      const i16 = new Int16Array(buf);
      const f32 = new Float32Array(i16.length);
      for (let i = 0; i < i16.length; i++) f32[i] = i16[i] / 32768.0;
      const ab = ctx.createBuffer(1, f32.length, 24000);
      ab.getChannelData(0).set(f32);
      const src = ctx.createBufferSource();
      src.buffer = ab;
      src.connect(ctx.destination);
      src.onended = () => { ctx.close(); playNext(); };
      src.start();
    } catch (err) {
      console.error('Playback error:', err);
      isPlaying = false;
      playNext();
    }
  }

  function stopPlayback() { playbackQueue = []; isPlaying = false; }

  // ═══════════════════════════════════════════════════════════
  // Events
  // ═══════════════════════════════════════════════════════════

  // Orb click
  document.getElementById('orbContainer')?.addEventListener('click', () => {
    if (!isConnected) { connect(); return; }
    if (isListening) { stopMic(); } else { startMic(); }
  });

  // Text submit
  document.getElementById('chatForm')?.addEventListener('submit', (e) => {
    e.preventDefault();
    const input = document.getElementById('chatInput');
    const text = input.value.trim();
    if (!text) return;
    ChatPanel.addUserMessage(text);
    input.value = '';
    input.style.height = 'auto'; // reset textarea height
    currentAgentMsg = null;

    if (!isConnected) {
      connect();
      const poll = setInterval(() => {
        if (ws && ws.readyState === WebSocket.OPEN) {
          clearInterval(poll);
          ws.send(JSON.stringify({ type: 'text', content: text }));
          VoiceOrb.setState('thinking');
        }
      }, 200);
      return;
    }
    ws.send(JSON.stringify({ type: 'text', content: text }));
    VoiceOrb.setState('thinking');
  });

  // Document upload
  DocScanner.init((imageData) => {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      ChatPanel.addSystemMessage('Connect first.');
      return;
    }
    ChatPanel.addSystemMessage(`Scanning: ${imageData.filename}`);
    ws.send(JSON.stringify({ type: 'image', data: imageData.data, mime_type: imageData.mime_type }));
    ws.send(JSON.stringify({ type: 'text', content: `I've uploaded a document (${imageData.filename}). Please analyze it.` }));
    VoiceOrb.setState('thinking');
  });

  // Graph refresh
  document.getElementById('refreshGraph')?.addEventListener('click', () => GraphPanel.refresh(userId));

  // Footer jurisdiction pills
  document.querySelectorAll('.footer__pill').forEach(pill => {
    pill.addEventListener('click', () => {
      document.querySelectorAll('.footer__pill').forEach(p => p.classList.remove('footer__pill--active'));
      pill.classList.add('footer__pill--active');
    });
  });

  // ═══════════════════════════════════════════════════════════
  // Init
  // ═══════════════════════════════════════════════════════════

  initParticles();
  VoiceOrb.init();
  GraphPanel.init();
  GraphPanel.refresh();
  connect();
})();
