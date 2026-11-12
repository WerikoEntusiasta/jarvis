/**
 * qwen_live_voice.js — CONVERSA AO VIVO do J.A.R.V.I.S. (fala -> fala, pt-BR).
 *
 * Microfone aberto → PCM 16 kHz → qwen_live_bridge (ws://127.0.0.1:8087/ws/voice)
 * → Qwen-Audio-3.0-Realtime-Plus responde falando (PCM 24 kHz) quando o usuario
 * para de falar (VAD no servidor). Raciocínio/execução vão para o agente MiMo
 * via function calling.
 *
 * Sem ponte disponível ou sem chave, o HUD cai automaticamente para o fluxo
 * clássico (gravar → STT → texto). Nada aqui quebra o caminho existente.
 */
(function () {
  'use strict';

  var WS_URL = (location.protocol === 'https:' ? 'wss://' : 'ws://') +
    (location.hostname || '127.0.0.1') + ':8087/ws/voice';

  var ws = null;
  var micStream = null;
  var micCtx = null;
  var procNode = null;
  var outCtx = null;
  var nextPlayTime = 0;
  var playQueue = [];
  var active = false;
  var starting = false;
  var replaySources = [];

  function log() {
    try { console.log.apply(console, ['[QwenLive]'].concat([].slice.call(arguments))); } catch (e) {}
  }

  function uiState(state) {
    // Mapeia estados para o HUD existente (setVoiceStatus vive no index.html).
    var mapa = {
      listening: ['listening', 'Pode falar. Estou ouvindo você.'],
      thinking: ['thinking', 'Processando com o agente MiMo...'],
      speaking: ['success', 'Respondendo, Senhor Werik.'],
      interrupt: ['listening', 'Ouvindo você...'],
      idle: ['standby', '']
    };
    var alvo = mapa[state];
    if (alvo && typeof window.setVoiceStatus === 'function') {
      try { window.setVoiceStatus(alvo[0], alvo[1]); } catch (e) {}
    }
    var stateText = document.getElementById('jarvis-state-text');
    if (stateText) {
      stateText.innerText = state === 'speaking' ? 'F A L A N D O' :
        state === 'thinking' ? 'P E N S A N D O' :
        state === 'listening' || state === 'interrupt' ? 'O U V I N D O' : 'O N L I N E';
    }
  }

  function subtitle(texto) {
    var el = document.getElementById('live-subtitle');
    if (el && texto) {
      try { el.innerText = '"' + texto + '"'; } catch (e) {}
    }
  }

  function playPcm24(pcm) {
    try {
      if (!outCtx) outCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 });
      if (outCtx.state === 'suspended') outCtx.resume();
      var n = pcm.length >> 1;
      if (n < 1) return;
      var buf = outCtx.createBuffer(1, n, 24000);
      var canal = buf.getChannelData(0);
      for (var i = 0; i < n; i++) {
        var s = (pcm[i * 2] | (pcm[i * 2 + 1] << 8));
        if (s & 0x8000) s = s - 0x10000;
        canal[i] = s / 32768;
      }
      var agora = outCtx.currentTime;
      if (nextPlayTime < agora + 0.03) nextPlayTime = agora + 0.06; // pequeno buffer anti-gap
      var src = outCtx.createBufferSource();
      src.buffer = buf;
      src.connect(outCtx.destination);
      src.start(nextPlayTime);
      nextPlayTime += buf.duration;
      replaySources.push(src);
      src.onended = function () {
        var idx = replaySources.indexOf(src);
        if (idx >= 0) replaySources.splice(idx, 1);
      };
    } catch (e) {
      log('erro playback:', e);
    }
  }

  function clearPlayback() {
    playQueue = [];
    nextPlayTime = 0;
    try { replaySources.forEach(function (s) { try { s.stop(); } catch (e) {} }); } catch (e) {}
    replaySources = [];
  }

  function stopMic() {
    try { if (procNode) procNode.disconnect(); } catch (e) {}
    try { if (micStream) micStream.getTracks().forEach(function (t) { t.stop(); }); } catch (e) {}
    try { if (micCtx) micCtx.close(); } catch (e) {}
    procNode = null;
    micStream = null;
    micCtx = null;
    try {
      var btn = document.getElementById('mic-btn');
      if (btn) btn.classList.remove('bg-rose-950', 'border-rose-400');
      var halo = document.getElementById('mic-halo');
      if (halo) halo.className = 'absolute -inset-1.5 rounded-full bg-cyan-400/30 blur-md animate-pulse';
    } catch (e) {}
    if (window.isSpeakingOrListening !== undefined) window.isSpeakingOrListening = false;
    if (window.liveMicLevel !== undefined) window.liveMicLevel = 0.0;
  }

  async function startMic() {
    micStream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, sampleRate: 16000, echoCancellation: true, noiseSuppression: true }
    });
    micCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
    var fonte = micCtx.createMediaStreamSource(micStream);
    // ScriptProcessorNode: amplamente suportado (QtWebEngine/Chromium) e sem worklet extra.
    procNode = micCtx.createScriptProcessor(4096, 1, 1);
    procNode.onaudioprocess = function (ev) {
      if (!ws || ws.readyState !== 1) return;
      var entrada = ev.inputBuffer.getChannelData(0);
      var n = entrada.length;
      var pcm = new ArrayBuffer(n * 2);
      var view = new DataView(pcm);
      var soma = 0;
      for (var i = 0; i < n; i++) {
        var s = Math.max(-1, Math.min(1, entrada[i]));
        view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
        soma += Math.abs(s);
      }
      if (window.liveMicLevel !== undefined) window.liveMicLevel = Math.min(1, (soma / n) * 4);
      ws.send(pcm);
    };
    fonte.connect(procNode);
    // Conecta ao destination via gain zero: o Chromium exige a conexao para
    // processar, mas o microfone NUNCA vaza para os alto-falantes (anti-eco).
    var mute = micCtx.createGain();
    mute.gain.value = 0;
    procNode.connect(mute);
    mute.connect(micCtx.destination);
    try {
      var btn = document.getElementById('mic-btn');
      if (btn) btn.classList.add('bg-rose-950', 'border-rose-400');
      var halo = document.getElementById('mic-halo');
      if (halo) halo.className = 'absolute -inset-2 rounded-full bg-rose-500/50 blur-lg animate-ping';
    } catch (e) {}
    if (window.isSpeakingOrListening !== undefined) window.isSpeakingOrListening = true;
  }

  function handleJson(dados) {
    if (!dados || typeof dados !== 'object') return;
    if (dados.type === 'state') {
      uiState(dados.state);
      if (dados.state === 'interrupt') clearPlayback();
    } else if (dados.type === 'transcript') {
      if (dados.role === 'user') subtitle('Você: ' + (dados.text || ''));
      else subtitle(dados.text || '');
      // Ecologa no campo de texto para histórico/chat continuar funcionando.
      if (dados.role === 'user' && window.userEchoEnabled) {
        var inp = document.getElementById('user-input');
        if (inp) inp.value = dados.text || '';
      }
    } else if (dados.type === 'tool') {
      try { log('tool MiMo:', dados.name, dados.arguments); } catch (e) {}
      if (typeof window.setVoiceStatus === 'function') {
        try { window.setVoiceStatus('thinking', 'Executando ' + (dados.name || 'ação') + ' via agente MiMo...'); } catch (e) {}
      }
    } else if (dados.type === 'error') {
      log('erro do bridge:', dados.message);
      if (typeof window.setVoiceStatus === 'function') {
        try { window.setVoiceStatus('error', 'Conversa ao vivo indisponível: ' + (dados.message || '')); } catch (e) {}
      }
      encerrar(false);
    } else if (dados.type === 'hello') {
      log('sessão pronta:', dados.model, dados.voice);
    }
  }

  function conectar() {
    return new Promise(function (resolve, reject) {
      var tentativas = 0;
      function abrir() {
        tentativas++;
        var sock = new WebSocket(WS_URL);
        sock.binaryType = 'arraybuffer';
        var timer = setTimeout(function () {
          try { sock.close(); } catch (e) {}
          if (tentativas < 2) abrir(); else reject(new Error('timeout'));
        }, 2500);
        sock.onopen = function () {
          clearTimeout(timer);
          ws = sock;
          resolve();
        };
        sock.onerror = function () {
          clearTimeout(timer);
          if (tentativas < 2) abrir(); else reject(new Error('bridge indisponível'));
        };
        sock.onmessage = function (ev) {
          if (typeof ev.data === 'string') {
            try { handleJson(JSON.parse(ev.data)); } catch (e) {}
          } else {
            playPcm24(new Uint8Array(ev.data));
          }
        };
        sock.onclose = function () {
          if (ws === sock) {
            ws = null;
            if (active) encerrar(false);
          }
        };
      }
      abrir();
    });
  }

  async function iniciar() {
    if (active || starting) return true;
    starting = true;
    try {
      await conectar();
      await startMic();
      active = true;
      uiState('listening');
      log('conversa ao vivo ativa');
      return true;
    } catch (e) {
      log('indisponível:', e && e.message);
      encerrar(false);
      return false;
    } finally {
      starting = false;
    }
  }

  function encerrar(notificar) {
    active = false;
    clearPlayback();
    stopMic();
    if (ws) {
      try { if (notificar && ws.readyState === 1) ws.send(JSON.stringify({ type: 'close' })); } catch (e) {}
      try { ws.close(); } catch (e) {}
      ws = null;
    }
    if (notificar !== false) uiState('idle');
    log('conversa ao vivo encerrada');
  }

  function alternar() {
    if (active) { encerrar(true); return Promise.resolve(false); }
    return iniciar();
  }

  window.QwenLiveVoice = {
    start: iniciar,
    stop: function () { encerrar(true); },
    toggle: alternar,
    isActive: function () { return active; },
    isAvailable: function () { return ws !== null && ws.readyState === 1; }
  };
})();
