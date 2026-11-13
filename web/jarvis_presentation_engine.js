/**
 * J.A.R.V.I.S. Mark VII - Organic Spatial Canvas Intelligence Engine
 * Kuro Black Luxury Glassmorphism - Mesa de Trabalho de Inteligência Contínua.
 * Cards são exibidos livremente sobre a tela padrão, sem janelas artificiais,
 * acumulando-se e encaixando-se organicamente conforme o JARVIS narra cada tópico.
 */
(function (root, factory) {
  if (typeof define === 'function' && define.amd) define([], factory);
  else if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.JarvisPresentationEngine = factory();
}(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const state = {
    workspace: null,
    title: 'SPATIAL INTELLIGENCE',
    components: new Map(),
    activeInstances: new Map(),
    sceneQueue: [],
    sceneIndex: 0,
    seq: 0,
    autoTimer: null,
    paused: false,
    currentScene: null
  };

  const esc = value => String(value == null ? '' : value).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
  })[c]);

  function injectStyles() {
    const existing = document.getElementById('jarvis-spatial-canvas-style');
    if (existing) existing.remove();
    const tag = document.createElement('style');
    tag.id = 'jarvis-spatial-canvas-style';
    tag.textContent = `
      #jarvis-spatial-canvas {
        position: fixed;
        left: 80px;
        right: 24px;
        top: 56px;
        bottom: 96px;
        z-index: 35;
        pointer-events: none;
        overflow: hidden;
      }
      .spatial-card-wrapper {
        position: absolute;
        box-sizing: border-box;
        pointer-events: auto;
        transition: left 0.6s cubic-bezier(0.16, 1, 0.3, 1),
                    top 0.6s cubic-bezier(0.16, 1, 0.3, 1),
                    width 0.6s cubic-bezier(0.16, 1, 0.3, 1),
                    height 0.6s cubic-bezier(0.16, 1, 0.3, 1),
                    opacity 0.5s cubic-bezier(0.16, 1, 0.3, 1),
                    transform 0.6s cubic-bezier(0.16, 1, 0.3, 1),
                    box-shadow 0.4s ease,
                    border-color 0.4s ease;
      }
      .spatial-card-wrapper.entering {
        opacity: 0;
        transform: translateY(32px) scale(0.92);
        filter: blur(8px);
      }
      .spatial-card-wrapper.leaving {
        opacity: 0;
        transform: translateY(-20px) scale(0.90);
        filter: blur(6px);
        pointer-events: none;
      }
      .spatial-card-wrapper.highlighted .spatial-card-surface {
        border-color: rgba(255, 255, 255, 0.65);
        box-shadow: 0 0 50px rgba(255, 255, 255, 0.28), 0 25px 60px rgba(0, 0, 0, 0.95);
        animation: cardSpeakingPulse 1.8s cubic-bezier(0.4, 0, 0.6, 1) infinite;
      }
      @keyframes cardSpeakingPulse {
        0%, 100% { border-color: rgba(255, 255, 255, 0.45); }
        50% { border-color: rgba(255, 255, 255, 0.9); box-shadow: 0 0 65px rgba(255, 255, 255, 0.4); }
      }
      .spatial-card-surface {
        position: relative;
        width: 100%;
        height: 100%;
        border-radius: 18px;
        background: rgba(9, 9, 11, 0.93);
        border: 1px solid rgba(255, 255, 255, 0.10);
        box-shadow: 0 25px 65px rgba(0, 0, 0, 0.95), inset 0 1px 0 rgba(255, 255, 255, 0.06);
        backdrop-filter: blur(28px);
        -webkit-backdrop-filter: blur(28px);
        padding: 20px 24px;
        color: #f4f4f5;
        display: flex;
        flex-direction: column;
        overflow: hidden;
      }
      .spatial-card-wrapper[data-type="network"] .spatial-card-dot,
      .spatial-card-wrapper[data-type="graph"] .spatial-card-dot { background: #a78bfa; box-shadow: 0 0 8px #a78bfa; }
      .spatial-card-wrapper[data-type="chart"] .spatial-card-dot { background: #34d399; box-shadow: 0 0 8px #34d399; }
      .spatial-card-wrapper[data-type="table"] .spatial-card-dot { background: #facc15; box-shadow: 0 0 8px #facc15; }
      .spatial-card-wrapper[data-type="diagram"] .spatial-card-dot { background: #fb923c; box-shadow: 0 0 8px #fb923c; }
      .spatial-card-wrapper[data-type="comparison"] .spatial-card-dot { background: #f472b6; box-shadow: 0 0 8px #f472b6; }
      .spatial-card-wrapper[data-type="conclusion"] .spatial-card-dot { background: #38bdf8; box-shadow: 0 0 8px #38bdf8; }
      .spatial-card-wrapper[data-type="metric_grid"] .spatial-card-dot { background: #22d3ee; box-shadow: 0 0 8px #22d3ee; }
      .spatial-badges { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
      .spatial-badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 999px;
        border: 1px solid rgba(34, 211, 238, 0.45);
        background: rgba(34, 211, 238, 0.10);
        color: #67e8f9;
        font-size: 10px;
        font-family: monospace;
        letter-spacing: 0.06em;
        text-transform: uppercase;
      }
      .spatial-card-surface::before {
        content: '';
        position: absolute;
        top: 0; left: 12%; right: 12%; height: 1.5px;
        background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.28), transparent);
      }
      .spatial-card-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding-bottom: 12px;
        margin-bottom: 14px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        user-select: none;
        flex-shrink: 0;
      }
      .spatial-card-title-group {
        display: flex;
        align-items: center;
        gap: 10px;
      }
      .spatial-card-dot {
        width: 8px;
        height: 8px;
        border-radius: 9999px;
        background: #ffffff;
        box-shadow: 0 0 10px rgba(255, 255, 255, 0.85);
        animation: spatialDotPulse 2.2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
      }
      @keyframes spatialDotPulse {
        0%, 100% { opacity: 1; transform: scale(1); }
        50% { opacity: 0.35; transform: scale(0.85); }
      }
      .spatial-card-kicker {
        font-family: 'JetBrains Mono', monospace;
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 2px;
        color: #71717a;
        text-transform: uppercase;
      }
      .spatial-card-title {
        font-family: 'Space Grotesk', 'Segoe UI', sans-serif;
        font-size: 14px;
        font-weight: 700;
        color: #ffffff;
        letter-spacing: 0.3px;
      }
      .spatial-card-close-btn {
        width: 24px;
        height: 24px;
        border-radius: 9999px;
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(255, 255, 255, 0.10);
        color: #a1a1aa;
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px;
        font-weight: 700;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        transition: all 0.2s ease;
      }
      .spatial-card-close-btn:hover {
        background: rgba(239, 68, 68, 0.25);
        border-color: rgba(248, 113, 113, 0.45);
        color: #ffffff;
        transform: scale(1.08);
      }
      .spatial-card-body {
        flex: 1;
        overflow-y: auto;
        display: flex;
        flex-direction: column;
      }
      .spatial-card-body::-webkit-scrollbar {
        width: 4px;
      }
      .spatial-card-body::-webkit-scrollbar-thumb {
        background: rgba(255, 255, 255, 0.12);
        border-radius: 4px;
      }
      .spatial-scene-copy {
        font-size: 13px;
        color: #a1a1aa;
        line-height: 1.65;
        margin-bottom: 12px;
      }
      .spatial-tags {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        margin-bottom: 12px;
      }
      .spatial-tag {
        display: inline-block;
        padding: 3px 9px;
        border-radius: 9999px;
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(255, 255, 255, 0.08);
        font-family: 'JetBrains Mono', monospace;
        font-size: 9.5px;
        font-weight: 600;
        color: #d4d4d8;
      }
      .spatial-bullets {
        margin-top: 6px;
        display: flex;
        flex-direction: column;
        gap: 6px;
      }
      .spatial-bullet {
        display: flex;
        align-items: flex-start;
        gap: 8px;
        font-size: 12px;
        color: #e4e4e7;
        line-height: 1.45;
      }
      .spatial-bullet-dot {
        color: #71717a;
        font-weight: bold;
      }
      .spatial-metrics-grid {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 10px;
        margin-top: 12px;
      }
      .spatial-metric-box {
        padding: 10px 12px;
        border-radius: 12px;
        background: #121214;
        border: 1px solid rgba(255, 255, 255, 0.07);
        display: flex;
        flex-direction: column;
        justify-content: space-between;
      }
      .spatial-metric-label {
        font-family: 'JetBrains Mono', monospace;
        font-size: 8.5px;
        font-weight: 700;
        color: #71717a;
        letter-spacing: 1.2px;
        text-transform: uppercase;
      }
      .spatial-metric-val {
        font-family: 'JetBrains Mono', monospace;
        font-size: clamp(18px, 1.8vw, 24px);
        font-weight: 800;
        color: #ffffff;
        margin: 2px 0;
      }
      .spatial-metric-trend {
        font-family: 'JetBrains Mono', monospace;
        font-size: 9px;
        color: #a1a1aa;
        font-weight: 600;
      }
      .spatial-table-wrap {
        width: 100%;
        overflow-x: auto;
        margin-top: 8px;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
      }
      .spatial-table {
        width: 100%;
        border-collapse: collapse;
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px;
      }
      .spatial-table thead th {
        background: rgba(34, 211, 238, 0.07);
        color: #67e8f9;
        font-size: 9px;
        letter-spacing: 1px;
        text-transform: uppercase;
        padding: 9px 12px;
        text-align: left;
        border-bottom: 1px solid rgba(255, 255, 255, 0.10);
        white-space: nowrap;
      }
      .spatial-table tbody td {
        padding: 8px 12px;
        color: #e4e4e7;
        border-bottom: 1px solid rgba(255, 255, 255, 0.05);
      }
      .spatial-table tbody tr:nth-child(even) td { background: rgba(255, 255, 255, 0.02); }
      .spatial-table tbody tr:hover td { background: rgba(34, 211, 238, 0.06); }
      .spatial-table tbody tr:last-child td { border-bottom: none; }
      .spatial-compare-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 10px;
        margin-top: 8px;
      }
      .spatial-compare-item {
        background: #121214;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 12px 14px;
        display: flex;
        flex-direction: column;
        gap: 7px;
      }
      .spatial-compare-title {
        font-family: 'Space Grotesk', 'Segoe UI', sans-serif;
        font-size: 12.5px;
        font-weight: 700;
        color: #ffffff;
        letter-spacing: 0.3px;
      }
      .spatial-compare-row {
        display: flex;
        gap: 7px;
        font-size: 11px;
        line-height: 1.45;
        color: #a1a1aa;
      }
      .spatial-compare-row.pro span:first-child { color: #34d399; }
      .spatial-compare-row.con span:first-child { color: #f87171; }
      .spatial-chart-empty {
        display: flex;
        align-items: center;
        justify-content: center;
        min-height: 140px;
        border: 1px dashed rgba(255, 255, 255, 0.14);
        border-radius: 12px;
        background: rgba(255, 255, 255, 0.02);
        color: #71717a;
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px;
        text-align: center;
        padding: 16px;
        margin-top: 8px;
      }
      .spatial-empty-fallback {
        color: #71717a;
        font-style: italic;
      }
      /* ---- Card de TEXTO simples (resposta da IA + copiar) ---- */
      .spatial-text-block {
        background: #121214;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 14px 16px;
        font-size: 13px;
        line-height: 1.7;
        color: #e4e4e7;
        white-space: pre-wrap;
        word-break: break-word;
        position: relative;
        margin-top: 4px;
      }
      .spatial-copy-btn {
        position: absolute;
        top: 8px;
        right: 8px;
        padding: 4px 10px;
        border-radius: 8px;
        background: rgba(34, 211, 238, 0.10);
        border: 1px solid rgba(34, 211, 238, 0.35);
        color: #67e8f9;
        font-family: 'JetBrains Mono', monospace;
        font-size: 9px;
        font-weight: 700;
        letter-spacing: 1px;
        cursor: pointer;
        transition: all 0.18s ease;
      }
      .spatial-copy-btn:hover { background: rgba(34, 211, 238, 0.25); color: #ffffff; }
      /* ---- Card de NOTICIAS ---- */
      .spatial-news-lead {
        display: flex;
        gap: 12px;
        background: #121214;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        overflow: hidden;
        margin-bottom: 10px;
        position: relative;
      }
      .spatial-news-lead-cover {
        width: 42%;
        min-height: 110px;
        flex-shrink: 0;
        display: flex;
        align-items: center;
        justify-content: center;
        background: linear-gradient(135deg, #1c1c1f 0%, #0e0e11 100%);
        font-size: 34px;
        opacity: 0.85;
      }
      .spatial-news-lead-img {
        position: absolute;
        left: 0;
        top: 0;
        width: 42%;
        height: 100%;
        object-fit: cover;
        z-index: 1;
      }
      .spatial-news-lead-body { padding: 11px 13px 11px 0; display: flex; flex-direction: column; gap: 6px; }
      .spatial-news-title {
        font-family: 'Space Grotesk', 'Segoe UI', sans-serif;
        font-size: 13px;
        font-weight: 700;
        color: #ffffff;
        line-height: 1.35;
        text-decoration: none;
      }
      a.spatial-news-title:hover { color: #67e8f9; }
      .spatial-news-meta {
        font-family: 'JetBrains Mono', monospace;
        font-size: 9px;
        color: #71717a;
        letter-spacing: 0.5px;
        text-transform: uppercase;
      }
      .spatial-news-sum {
        font-size: 11.5px;
        color: #a1a1aa;
        line-height: 1.5;
      }
      .spatial-news-item {
        display: flex;
        align-items: baseline;
        gap: 9px;
        padding: 8px 4px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        text-decoration: none;
      }
      .spatial-news-item:last-child { border-bottom: none; }
      a.spatial-news-item:hover .spatial-news-item-title { color: #67e8f9; }
      .spatial-news-item-dot { color: #22d3ee; font-size: 11px; flex-shrink: 0; }
      .spatial-news-item-title { font-size: 12px; color: #e4e4e7; line-height: 1.4; flex: 1; }
      .spatial-news-item-src {
        font-family: 'JetBrains Mono', monospace;
        font-size: 8.5px;
        color: #52525b;
        text-transform: uppercase;
        flex-shrink: 0;
      }
      /* ---- Card de PREVISAO DO TEMPO ---- */
      .spatial-weather-hero {
        display: flex;
        align-items: center;
        gap: 14px;
        background: linear-gradient(135deg, rgba(34, 211, 238, 0.08), rgba(59, 130, 246, 0.06));
        border: 1px solid rgba(34, 211, 238, 0.20);
        border-radius: 14px;
        padding: 14px 16px;
        margin-bottom: 12px;
      }
      .spatial-weather-hero-emoji { font-size: 40px; line-height: 1; }
      .spatial-weather-hero-temps { display: flex; flex-direction: column; gap: 2px; }
      .spatial-weather-hero-max { font-family: 'JetBrains Mono', monospace; font-size: 26px; font-weight: 800; color: #ffffff; }
      .spatial-weather-hero-min { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #71717a; }
      .spatial-weather-hero-desc { font-size: 12.5px; color: #a1a1aa; margin-top: 3px; }
      .spatial-weather-strip {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(64px, 1fr));
        gap: 7px;
        margin-top: 4px;
      }
      .spatial-weather-day {
        background: #121214;
        border: 1px solid rgba(255, 255, 255, 0.07);
        border-radius: 10px;
        padding: 9px 5px;
        text-align: center;
        display: flex;
        flex-direction: column;
        gap: 3px;
      }
      .spatial-weather-dow { font-family: 'JetBrains Mono', monospace; font-size: 9px; color: #71717a; text-transform: uppercase; letter-spacing: 1px; }
      .spatial-weather-icon { font-size: 19px; line-height: 1.2; }
      .spatial-weather-maxmin { font-family: 'JetBrains Mono', monospace; font-size: 10.5px; color: #e4e4e7; }
      .spatial-weather-maxmin b { color: #ffffff; font-weight: 700; }
      .spatial-weather-rain { font-family: 'JetBrains Mono', monospace; font-size: 9px; color: #38bdf8; }
      /* ---- Card de WHATSAPP (mensagens nao lidas) ---- */
      .spatial-wa-header {
        display: flex;
        align-items: center;
        gap: 9px;
        background: linear-gradient(135deg, rgba(37, 211, 102, 0.10), rgba(37, 211, 102, 0.04));
        border: 1px solid rgba(37, 211, 102, 0.25);
        border-radius: 12px;
        padding: 10px 13px;
        margin-bottom: 10px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px;
        color: #86efac;
      }
      .spatial-wa-unread-pill {
        margin-left: auto;
        background: #25d366;
        color: #04301a;
        font-weight: 800;
        border-radius: 999px;
        padding: 2px 9px;
        font-size: 10px;
      }
      .spatial-wa-msg {
        background: #121214;
        border: 1px solid rgba(255, 255, 255, 0.07);
        border-left: 3px solid #25d366;
        border-radius: 10px;
        padding: 10px 12px;
        margin-bottom: 8px;
        display: flex;
        flex-direction: column;
        gap: 5px;
      }
      .spatial-wa-msg-top {
        display: flex;
        align-items: baseline;
        gap: 8px;
      }
      .spatial-wa-name {
        font-size: 12.5px;
        font-weight: 700;
        color: #ffffff;
      }
      .spatial-wa-badge {
        background: rgba(37, 211, 102, 0.18);
        color: #86efac;
        border-radius: 999px;
        font-size: 9px;
        font-weight: 800;
        padding: 1px 7px;
        font-family: 'JetBrains Mono', monospace;
      }
      .spatial-wa-ts {
        margin-left: auto;
        font-family: 'JetBrains Mono', monospace;
        font-size: 9px;
        color: #52525b;
      }
      .spatial-wa-text { font-size: 12px; color: #d4d4d8; line-height: 1.5; word-break: break-word; }
      .spatial-wa-role {
        font-family: 'JetBrains Mono', monospace;
        font-size: 8.5px;
        color: #71717a;
        text-transform: uppercase;
        letter-spacing: 1px;
      }
      .spatial-wa-reply-row { display: flex; gap: 7px; margin-top: 3px; }
      .spatial-wa-reply-input {
        flex: 1;
        background: #1c1c1f;
        border: 1px solid rgba(255, 255, 255, 0.10);
        border-radius: 8px;
        padding: 7px 10px;
        color: #e4e4e7;
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px;
        outline: none;
        min-width: 0;
      }
      .spatial-wa-reply-input:focus { border-color: rgba(37, 211, 102, 0.55); }
      .spatial-wa-reply-btn {
        background: #25d366;
        color: #04301a;
        border: none;
        border-radius: 8px;
        padding: 7px 13px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 10px;
        font-weight: 800;
        cursor: pointer;
        transition: filter 0.15s ease;
      }
      .spatial-wa-reply-btn:hover { filter: brightness(1.12); }
      .spatial-wa-reply-btn:disabled { opacity: 0.5; cursor: wait; }
      .spatial-wa-empty {
        color: #71717a;
        font-size: 12px;
        text-align: center;
        padding: 14px;
        border: 1px dashed rgba(37, 211, 102, 0.25);
        border-radius: 10px;
      }
    `;
    document.head.appendChild(tag);
  }

  function hideLegacyDeck() {
    const deck = document.getElementById('jarvis-presentation-deck');
    if (deck) {
      deck.classList.add('hidden', 'opacity-0');
      deck.innerHTML = '';
    }
    const oldStage = document.getElementById('presentation-stage');
    if (oldStage) {
      oldStage.className = 'hidden pointer-events-none opacity-0 select-none';
    }
  }

  function getCanvas() {
    hideLegacyDeck();
    let canvas = document.getElementById('jarvis-spatial-canvas');
    if (!canvas) {
      canvas = document.createElement('div');
      canvas.id = 'jarvis-spatial-canvas';
      canvas.className = 'fixed left-20 right-6 top-14 bottom-24 z-30 pointer-events-none select-none';
      document.body.appendChild(canvas);
    }
    return canvas;
  }

  function updateGlobalActionsBadge() {
    let badge = document.getElementById('spatial-canvas-actions');
    const canvas = getCanvas();
    if (!badge && canvas) {
      badge = document.createElement('div');
      badge.id = 'spatial-canvas-actions';
      badge.className = 'absolute right-4 top-2 pointer-events-auto transition-opacity duration-300';
      badge.innerHTML = `
        <button onclick="window.JarvisPresentationEngine && window.JarvisPresentationEngine.clearSpatialWorkspace()" class="px-3.5 py-1 rounded-full bg-zinc-950/85 hover:bg-zinc-900 border border-zinc-700/80 hover:border-zinc-500 text-zinc-300 hover:text-white text-[10px] font-mono-code font-bold transition-all flex items-center space-x-1.5 cursor-pointer shadow-lg active:scale-95">
          <span>✕</span>
          <span>LIMPAR PALCO (ESC)</span>
        </button>
      `;
      canvas.appendChild(badge);
    }
    if (badge) {
      if (state.components.size > 0) {
        badge.classList.remove('hidden');
        badge.style.opacity = '1';
      } else {
        badge.classList.add('hidden');
        badge.style.opacity = '0';
      }
    }
  }

  // ALGORITMO ORGÂNICO DE ENCAIXE DE CARDS (SPATIAL AUTO-SLOTTING)
  function resolvePosition(position, index) {
    const pos = position || {};
    
    // Coordenadas explícitas informadas pelo script
    if (pos.left !== undefined || pos.x !== undefined) {
      const left = pos.left !== undefined ? pos.left : (typeof pos.x === 'string' ? pos.x : `${pos.x}%`);
      const top = pos.top !== undefined ? pos.top : (typeof pos.y === 'string' ? pos.y : `${pos.y}%`);
      const width = pos.width !== undefined ? (typeof pos.width === 'string' ? pos.width : `${pos.width}%`) : '38%';
      const height = pos.height !== undefined ? (typeof pos.height === 'string' ? pos.height : `${pos.height}%`) : 'auto';
      return { left, top, width, height, maxHeight: pos.maxHeight || '580px' };
    }

    // Slots orgânicos contornando o Arc Reactor central
    // Slot 0 (Asa Esquerda): Card 1 (ex: Impostos)
    // Slot 1 (Asa Direita): Card 2 (ex: STF - surge ao lado sem remover o primeiro!)
    // Slot 2 (Inferior Esquerdo): Card 3
    // Slot 3 (Inferior Direito): Card 4
    const slots = [
      { left: '3%',  top: '6%',  width: '38%', height: 'auto', maxHeight: '580px' },
      { left: '59%', top: '6%',  width: '38%', height: 'auto', maxHeight: '580px' },
      { left: '3%',  top: '52%', width: '38%', height: 'auto', maxHeight: '420px' },
      { left: '59%', top: '52%', width: '38%', height: 'auto', maxHeight: '420px' }
    ];

    const slot = slots[index % slots.length];
    return {
      left: slot.left,
      top: slot.top,
      width: pos.width ? (typeof pos.width === 'string' ? pos.width : `${pos.width}%`) : slot.width,
      height: pos.height ? (typeof pos.height === 'string' ? pos.height : `${pos.height}%`) : slot.height,
      maxHeight: slot.maxHeight
    };
  }

  // Normaliza opcoes de grafico vindas do modelo no formato amigavel
  // {chart_type, categories, series[]} para opcoes validas do ECharts.
  // O ECharts exige series[].type e xAxis/yAxis - sem isto o chart fica vazio.
  function normalizeChartOptions(raw) {
    if (!raw || typeof raw !== 'object') return null;

    const hasChartType = typeof raw.chart_type === 'string';
    const hasCategories = Array.isArray(raw.categories);
    const rawSeries = Array.isArray(raw.series) ? raw.series
      : (Array.isArray(raw.values) ? [{ name: raw.name || 'Série', data: raw.values }] : null);

    // Sem cabecalho amigavel: so passa adiante se ja for opcao ECharts valida.
    if (!hasChartType && !hasCategories) {
      if (raw.xAxis || raw.yAxis) return raw;
      if (rawSeries && rawSeries.length &&
          rawSeries.every(s => s && typeof s === 'object' && s.type && Array.isArray(s.data))) {
        return raw;
      }
      return null;
    }
    if (!rawSeries || !rawSeries.length) return null;

    const ctype = String(raw.chart_type || 'bar').toLowerCase();
    const categories = hasCategories ? raw.categories : [];
    const isPie = ['pie', 'doughnut', 'donut', 'rosca'].includes(ctype);
    const isArea = ctype === 'area';
    const baseType = isPie ? 'pie'
      : (ctype === 'line' || isArea) ? 'line'
      : ctype === 'scatter' ? 'scatter'
      : 'bar';

    const out = {
      backgroundColor: 'transparent',
      textStyle: { color: '#94a3b8', fontFamily: 'JetBrains Mono', fontSize: 10 },
      tooltip: {
        trigger: isPie ? 'item' : 'axis',
        backgroundColor: '#09090b',
        borderColor: 'rgba(255, 255, 255, 0.12)',
        textStyle: { color: '#f4f4f5', fontFamily: 'JetBrains Mono', fontSize: 11 }
      }
    };

    if (isPie) {
      // series [{name, data:[...]}] + categories -> [{name, value}]
      let pieData = [];
      if (rawSeries.length === 1 && Array.isArray(rawSeries[0].data)) {
        const s0 = rawSeries[0];
        pieData = s0.data.map((v, i) => {
          if (v && typeof v === 'object') return { name: String(v.name || categories[i] || s0.name || `Item ${i + 1}`), value: Number(v.value) || 0 };
          return { name: String(categories[i] || s0.name || `Item ${i + 1}`), value: Number(v) || 0 };
        });
      } else {
        rawSeries.forEach(s => {
          if (s && typeof s === 'object' && !Array.isArray(s) && 'value' in s) pieData.push(s);
          else if (s && Array.isArray(s.data)) {
            s.data.forEach((v, i) => pieData.push({ name: String(categories[i] || s.name || `Item ${i + 1}`), value: Number(v) || 0 }));
          }
        });
      }
      if (!pieData.length) return null;
      out.legend = { bottom: '0%', textStyle: { color: '#71717a', fontFamily: 'JetBrains Mono', fontSize: 9 } };
      out.series = [{
        type: 'pie',
        radius: ctype === 'pie' ? ['0%', '62%'] : ['45%', '70%'],
        center: ['50%', '48%'],
        itemStyle: { borderRadius: 6, borderColor: '#09090b', borderWidth: 2 },
        label: { color: '#a1a1aa', fontFamily: 'JetBrains Mono', fontSize: 10, formatter: '{b}: {c}' },
        labelLine: { lineStyle: { color: '#3f3f46' } },
        data: pieData
      }];
      return out;
    }

    // Cartesiano: line / bar / area / scatter
    const normSeries = rawSeries.map(s => {
      if (Array.isArray(s)) return { type: baseType, data: s };
      if (s && typeof s === 'object' && Array.isArray(s.data)) {
        const item = {
          type: (typeof s.type === 'string' && s.type) ? s.type : baseType,
          data: s.data
        };
        if (s.name) item.name = String(s.name);
        if (isArea) item.areaStyle = { opacity: 0.3 };
        if (item.type === 'line') item.smooth = true;
        return item;
      }
      return null;
    }).filter(Boolean);
    if (!normSeries.length) return null;

    const xData = categories.length ? categories
      : (Array.isArray(normSeries[0].data) ? normSeries[0].data.map((_, i) => String(i + 1)) : []);

    out.grid = { left: 24, right: 16, top: 24, bottom: 24, containLabel: true };
    out.xAxis = {
      type: 'category',
      data: xData,
      axisLabel: { color: '#71717a', fontFamily: 'JetBrains Mono', fontSize: 9 },
      axisLine: { lineStyle: { color: 'rgba(255, 255, 255, 0.15)' } },
      splitLine: { show: false }
    };
    out.yAxis = {
      type: 'value',
      axisLabel: { color: '#71717a', fontFamily: 'JetBrains Mono', fontSize: 9 },
      splitLine: { lineStyle: { color: 'rgba(255, 255, 255, 0.07)' } }
    };
    if (raw.x_label) out.xAxis.name = String(raw.x_label);
    if (raw.y_label) out.yAxis.name = String(raw.y_label);
    if (normSeries.length > 1 || normSeries[0].name) {
      out.legend = { top: 0, textStyle: { color: '#71717a', fontFamily: 'JetBrains Mono', fontSize: 9 } };
    }
    out.series = normSeries;
    return out;
  }

  // BUILDER: ECHARTS
  function buildECharts(opts, minHeight = 220) {
    const defaultOpts = {
      backgroundColor: 'transparent',
      textStyle: { color: '#94a3b8', fontFamily: 'JetBrains Mono', fontSize: 10 },
      grid: { left: 20, right: 14, top: 18, bottom: 20, containLabel: true },
      tooltip: {
        trigger: 'item',
        backgroundColor: '#09090b',
        borderColor: 'rgba(255, 255, 255, 0.12)',
        textStyle: { color: '#f4f4f5', fontFamily: 'JetBrains Mono', fontSize: 11 }
      },
      series: [{
        type: 'pie',
        radius: ['45%', '70%'],
        center: ['50%', '50%'],
        avoidLabelOverlap: false,
        itemStyle: { borderRadius: 6, borderColor: '#09090b', borderWidth: 2 },
        label: { show: false },
        data: [
          { value: 40, name: 'Cérebro Soberano (40%)', itemStyle: { color: '#ffffff' } },
          { value: 25, name: 'Automação Windows (25%)', itemStyle: { color: '#a1a1aa' } },
          { value: 18, name: 'ZimaOS Gateway (18%)', itemStyle: { color: '#71717a' } },
          { value: 10, name: 'Smart TV LG (10%)', itemStyle: { color: '#52525b' } },
          { value: 7, name: 'Esfera ESP32 (7%)', itemStyle: { color: '#3f3f46' } }
        ]
      }],
      legend: {
        bottom: '0%',
        textStyle: { color: '#71717a', fontFamily: 'JetBrains Mono', fontSize: 9 }
      }
    };
    const finalOpts = Object.assign({}, defaultOpts, opts || {});
    return {
      html: `<div data-spatial-echart style="width:100%;min-height:${minHeight}px;flex:1"></div>`,
      mount(dom) {
        const target = dom.querySelector('[data-spatial-echart]');
        if (!target || !window.echarts) return null;
        const inst = window.echarts.init(target, null, { renderer: 'canvas' });
        inst.setOption(finalOpts);
        const resize = () => inst.resize();
        window.addEventListener('resize', resize);
        setTimeout(resize, 60);
        setTimeout(resize, 200);
        return {
          instance: inst,
          cleanup: () => {
            window.removeEventListener('resize', resize);
            inst.dispose();
          }
        };
      }
    };
  }

  // BUILDER: THREE.JS 3D HOLOGRAM
  function buildThreeView(minHeight = 220) {
    return {
      html: `<div data-spatial-three style="width:100%;min-height:${minHeight}px;position:relative;flex:1"></div>`,
      mount(dom) {
        const host = dom.querySelector('[data-spatial-three]');
        if (!host || !window.THREE) return null;

        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
        camera.position.set(0, 0, 5.0);

        const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
        host.appendChild(renderer.domElement);

        const group = new THREE.Group();
        const coreGeo = new THREE.IcosahedronGeometry(1.15, 2);
        const coreMat = new THREE.MeshBasicMaterial({ color: 0xffffff, wireframe: true, transparent: true, opacity: 0.85 });
        const coreMesh = new THREE.Mesh(coreGeo, coreMat);
        group.add(coreMesh);

        const ringGeo = new THREE.TorusGeometry(1.65, 0.02, 16, 100);
        const ringMat = new THREE.MeshBasicMaterial({ color: 0xa1a1aa, transparent: true, opacity: 0.65 });
        const ringMesh = new THREE.Mesh(ringGeo, ringMat);
        ringMesh.rotation.x = Math.PI * 0.45;
        group.add(ringMesh);

        scene.add(group);

        let isRunning = true;
        let reqId;

        const resize = () => {
          const w = host.clientWidth || 300;
          const h = host.clientHeight || 200;
          renderer.setSize(w, h, false);
          camera.aspect = w / h;
          camera.updateProjectionMatrix();
        };

        const animate = () => {
          if (!isRunning) return;
          group.rotation.y += 0.005;
          coreMesh.rotation.x += 0.003;
          ringMesh.rotation.z += 0.004;
          renderer.render(scene, camera);
          reqId = requestAnimationFrame(animate);
        };

        resize();
        animate();
        window.addEventListener('resize', resize);
        setTimeout(resize, 80);

        return {
          cleanup: () => {
            isRunning = false;
            cancelAnimationFrame(reqId);
            window.removeEventListener('resize', resize);
            renderer.dispose();
            if (renderer.domElement) renderer.domElement.remove();
          }
        };
      }
    };
  }

  // BUILDER: CARD CONTENT (Sem duplicar o título no corpo)
  // IDs unicos: cada card e criado na hora e NUNCA reaproveitado.
  let _cardSeq = 0;
  function uniqueId(base) {
    _cardSeq += 1;
    return (base || 'card') + '_' + Date.now() + '_' + _cardSeq;
  }

  // Grafo de relacoes (Cytoscape.js): nodes + edges
  function buildCytoscapeNetwork(p, minHeight) {
    const nodes = (p.nodes || p.vertices || []).map((n, i) => {
      if (typeof n === 'string') return { data: { id: 'n' + i, label: n } };
      return { data: { id: n.id || n.label || ('n' + i), label: n.label || n.id || ('n' + i), group: n.group || n.type || '' } };
    });
    const edges = (p.edges || p.links || p.connections || []).map((e, i) => {
      if (typeof e === 'string') {
        const parts = e.split('->');
        return { data: { id: 'e' + i, source: (parts[0] || '').trim(), target: (parts[1] || '').trim() } };
      }
      return { data: { id: e.id || ('e' + i), source: e.source || e.from, target: e.target || e.to, label: e.label || e.relation || '' } };
    });
    const divId = 'cy_' + Date.now() + '_' + Math.floor(Math.random() * 1e6);
    return {
      html: `<div id="${divId}" style="width:100%;height:${minHeight}px;"></div>`,
      mount(dom) {
        if (!window.cytoscape) return null;
        const el = dom.querySelector('#' + divId);
        if (!el) return null;
        const cy = window.cytoscape({
          container: el,
          elements: { nodes, edges },
          style: [
            { selector: 'node', style: { 'label': 'data(label)', 'color': '#e4e4e7', 'text-valign': 'bottom', 'text-margin-y': 6, 'text-wrap': 'wrap', 'text-max-width': 110, 'background-color': '#0ea5e9', 'border-color': '#22d3ee', 'border-width': 2, 'width': 32, 'height': 32, 'font-size': 11, 'font-family': 'monospace' } },
            { selector: 'node:selected', style: { 'background-color': '#f472b6' } },
            { selector: 'edge', style: { 'width': 2, 'line-color': '#38bdf8', 'target-arrow-color': '#38bdf8', 'target-arrow-shape': 'triangle', 'curve-style': 'bezier', 'label': 'data(label)', 'font-size': 9, 'color': '#a1a1aa', 'text-rotation': 'autorotate' } }
          ],
          layout: { name: 'cose', animate: true, animationDuration: 700, padding: 20 },
          wheelSensitivity: 0.25
        });
        return { cleanup() { try { cy.destroy(); } catch (e) {} } };
      }
    };
  }

  // BUILDER: TEXTO simples - resposta pura da IA com botao copiar
  function buildTextCard(p, cRaw) {
    const candidatos = [
      p.copy_text, p.answer, p.text,
      typeof cRaw === 'string' ? cRaw : (cRaw && (cRaw.text || cRaw.answer)),
      typeof p.content === 'string' ? p.content : ''
    ];
    const texto = String(candidatos.find(v => v && String(v).trim()) || '').trim();
    if (!texto) return null;
    const cid = 'txt_' + Date.now() + '_' + Math.floor(Math.random() * 1e6);
    return {
      html: `
        <div class="spatial-text-block" id="${cid}">
          <button class="spatial-copy-btn" onclick="navigator.clipboard.writeText(document.getElementById('${cid}').querySelector('code').innerText).then(()=>{this.textContent='COPIADO ✓';setTimeout(()=>this.textContent='COPIAR',1500)})">COPIAR</button>
          <code style="font-family:'JetBrains Mono',monospace;font-size:12.5px;white-space:pre-wrap;color:inherit;background:none;">${esc(texto)}</code>
        </div>`,
      mount() { return null; }
    };
  }

  // BUILDER: NOTICIAS - manchete com imagem + lista clicavel
  function buildNewsCard(p, cRaw) {
    const isObj = cRaw && typeof cRaw === 'object';
    const items = (Array.isArray(p.items) && p.items.length) ? p.items
      : (isObj && Array.isArray(cRaw.items) && cRaw.items.length) ? cRaw.items : [];
    if (!items.length) return null;

    const lead = items[0];
    const rest = items.slice(1, 7);
    // Capa: fundo com icone SEMPRE por tras; a imagem (quando houver)
    // cobre - se falhar ao carregar (hotlink bloqueado), onerror revela a capa.
    const coverGlyph = "📰";
    const leadHtml = `
      <div class="spatial-news-lead">
        <div class="spatial-news-lead-cover" aria-hidden="true">${coverGlyph}</div>
        ${lead.image ? `<img class="spatial-news-lead-img" src="${esc(lead.image)}" alt="" loading="lazy" onerror="this.style.display='none'">` : ''}
        <div class="spatial-news-lead-body">
          <a class="spatial-news-title" href="${esc(lead.link || '#')}" target="_blank" rel="noopener">${esc(lead.title || '')}</a>
          <span class="spatial-news-meta">${esc(lead.source || 'Notícias')}${lead.published ? ' · ' + esc(String(lead.published).slice(0, 16)) : ''}</span>
          ${lead.summary ? `<span class="spatial-news-sum">${esc(lead.summary)}</span>` : ''}
        </div>
      </div>`;
    const restHtml = rest.filter(i => i && i.title).map(i => `
      <a class="spatial-news-item" href="${esc(i.link || '#')}" target="_blank" rel="noopener">
        <span class="spatial-news-item-dot">◆</span>
        <span class="spatial-news-item-title">${esc(i.title)}</span>
        <span class="spatial-news-item-src">${esc(i.source || '')}</span>
      </a>`).join('');
    return {
      html: `${leadHtml}${restHtml ? `<div class="spatial-news-list">${restHtml}</div>` : ''}`,
      mount() { return null; }
    };
  }

  // BUILDER: PREVISAO DO TEMPO - hoje em destaque + faixa de 7 dias
  function buildWeatherCard(p, cRaw) {
    const isObj = cRaw && typeof cRaw === 'object';
    const days = (Array.isArray(p.days) && p.days.length) ? p.days
      : (isObj && Array.isArray(cRaw.days) && cRaw.days.length) ? cRaw.days : [];
    if (!days.length) return null;
    const today = days[0];
    const fmt = v => (v == null || v === '') ? '--' : Math.round(Number(v));
    const hero = `
      <div class="spatial-weather-hero">
        <span class="spatial-weather-hero-emoji">${esc(today.emoji || '🌡️')}</span>
        <div class="spatial-weather-hero-temps">
          <span class="spatial-weather-hero-max">${fmt(today.temp_max)}°</span>
          <span class="spatial-weather-hero-min">mín ${fmt(today.temp_min)}°</span>
        </div>
        <div>
          <div style="font-size:13px;font-weight:700;color:#fff;">${esc(p.city || p.title || 'Hoje')}</div>
          <div class="spatial-weather-hero-desc">${esc(today.description || '')}${today.rain_prob != null ? ` · ${fmt(today.rain_prob)}% chuva` : ''}</div>
        </div>
      </div>`;
    const strip = `<div class="spatial-weather-strip">${days.slice(0, 7).map(d => `
      <div class="spatial-weather-day">
        <span class="spatial-weather-dow">${esc(d.weekday || (d.date || '').slice(8, 10))}</span>
        <span class="spatial-weather-icon">${esc(d.emoji || '🌡️')}</span>
        <span class="spatial-weather-maxmin"><b>${fmt(d.temp_max)}°</b> ${fmt(d.temp_min)}°</span>
        ${d.rain_prob != null ? `<span class="spatial-weather-rain">💧${fmt(d.rain_prob)}%</span>` : ''}
      </div>`).join('')}</div>`;
    return { html: hero + strip, mount() { return null; } };
  }

  // BUILDER: WHATSAPP - mensagens nao lidas com resposta direta pelo card
  function buildWhatsappCard(p, cRaw) {
    const isObj = cRaw && typeof cRaw === 'object';
    const msgs = (Array.isArray(p.messages) && p.messages.length) ? p.messages
      : (isObj && Array.isArray(cRaw.messages) && cRaw.messages.length) ? cRaw.messages : [];
    const total = Number(p.total_unread || (isObj ? cRaw.total_unread : 0) || 0) ||
      msgs.reduce((s, m) => s + (Number(m.unread) || 0), 0);

    const header = `
      <div class="spatial-wa-header">
        <span>💬 WhatsApp</span>
        <span>${esc(p.role || (msgs[0] && msgs[0].role) || 'conectado')}</span>
        <span class="spatial-wa-unread-pill">${total} não lida${total === 1 ? '' : 's'}</span>
      </div>`;

    if (!msgs.length) {
      return { html: `${header}<div class="spatial-wa-empty">✅ Nenhuma mensagem não lida.</div>`,
               mount() { return null; } };
    }

    const body = msgs.slice(0, 6).map((m, i) => {
      const safeId = String(m.chat_id || '').replace(/[^\w@.\-:]/g, '');
      const sess = String(m.session || 'Businees').replace(/[^\w]/g, '');
      return `
      <div class="spatial-wa-msg">
        <div class="spatial-wa-msg-top">
          <span class="spatial-wa-name">${esc(m.name || 'Contato')}</span>
          <span class="spatial-wa-badge">${Number(m.unread) || 1}</span>
          <span class="spatial-wa-ts">${esc(m.ts || '')}</span>
        </div>
        ${m.role ? `<span class="spatial-wa-role">${esc(m.role)}</span>` : ''}
        <span class="spatial-wa-text">${esc(m.label || '(sem conteúdo)')}</span>
        ${safeId ? `
        <div class="spatial-wa-reply-row">
          <input class="spatial-wa-reply-input" id="wa_reply_${i}" type="text"
                 placeholder="Responder ${esc((m.name || '').split(' ')[0])}..."
                 onkeydown="if(event.key==='Enter')window.JarvisWhatsApp&&window.JarvisWhatsApp.send('${safeId}','${sess}',${i})">
          <button class="spatial-wa-reply-btn"
                  onclick="window.JarvisWhatsApp&&window.JarvisWhatsApp.send('${safeId}','${sess}',${i})">ENVIAR</button>
        </div>` : ''}
      </div>`;
    }).join('');

    return { html: header + body, mount() { return null; } };
  }

  function buildCardContent(type, p) {
    const cRaw = p.content;
    const isObj = cRaw && typeof cRaw === 'object';
    const summary = p.summary || (isObj ? (cRaw.text || cRaw.summary || cRaw.heading || '') : (cRaw || ''));
    const tags = (p.tags || []).map(t => `<span class="spatial-tag">${esc(t)}</span>`).join('');
    const bullets = (p.bullets || []).map(b => `
      <div class="spatial-bullet">
        <span class="spatial-bullet-dot">▸</span>
        <span>${esc(b)}</span>
      </div>
    `).join('');

    const metrics = (p.metrics || []).slice(0, 4);
    const metricsHtml = metrics.length ? `
      <div class="spatial-metrics-grid">
        ${metrics.map(m => `
          <div class="spatial-metric-box">
            <span class="spatial-metric-label">${esc(m.label || 'KPI')}</span>
            <span class="spatial-metric-val">${esc(m.value || '--')}</span>
            <span class="spatial-metric-trend">${esc(m.trend || '● Nominal')}</span>
          </div>
        `).join('')}
      </div>
    ` : '';

    // Tabela (table): headers/columns + rows - tambem lidos do content dict
    const tableHeaders = (p.headers && p.headers.length) ? p.headers
      : (isObj && Array.isArray(cRaw.headers) && cRaw.headers.length) ? cRaw.headers
      : (isObj && Array.isArray(cRaw.columns) && cRaw.columns.length) ? cRaw.columns : [];
    const tableRows = (p.rows && p.rows.length) ? p.rows
      : (isObj && Array.isArray(cRaw.rows) && cRaw.rows.length) ? cRaw.rows : [];
    let tableHtml = '';
    if (type === 'table' && (tableHeaders.length || tableRows.length)) {
      const head = tableHeaders.map(h => `<th>${esc(typeof h === 'object' ? (h.label || h.title || h.key || '') : h)}</th>`).join('');
      const body = tableRows.map(r => {
        const cells = Array.isArray(r) ? r : tableHeaders.map(h => {
          const key = typeof h === 'object' ? (h.key || h.label || h.title) : h;
          return (r && typeof r === 'object') ? r[key] : '';
        });
        return `<tr>${cells.map(c => `<td>${esc(c == null ? '' : c)}</td>`).join('')}</tr>`;
      }).join('');
      tableHtml = `<div class="spatial-table-wrap"><table class="spatial-table">${head ? `<thead><tr>${head}</tr></thead>` : ''}<tbody>${body}</tbody></table></div>`;
    }

    // Comparacao (comparison): items [{title, pro, con}] - tambem do content dict
    const compareItems = (Array.isArray(p.items) && p.items.length) ? p.items
      : (isObj && Array.isArray(cRaw.items) && cRaw.items.length) ? cRaw.items : [];
    let compareHtml = '';
    if (type === 'comparison' && compareItems.length) {
      compareHtml = `<div class="spatial-compare-grid">${compareItems.slice(0, 6).map(it => {
        if (!it || typeof it !== 'object') return '';
        const pro = it.pro || it.positive || it.advantage || '';
        const con = it.con || it.negative || it.disadvantage || '';
        return `<div class="spatial-compare-item">
          <div class="spatial-compare-title">${esc(it.title || it.name || it.label || '')}</div>
          ${pro ? `<div class="spatial-compare-row pro"><span>▲</span><span>${esc(pro)}</span></div>` : ''}
          ${con ? `<div class="spatial-compare-row con"><span>▼</span><span>${esc(con)}</span></div>` : ''}
        </div>`;
      }).join('')}</div>`;
    }

    let visualBuilder = null;
    if (type === 'network' || type === 'graph' || type === 'cytoscape') {
      visualBuilder = buildCytoscapeNetwork(p, 220);
    } else if (type === 'text' || type === 'answer' || type === 'response') {
      visualBuilder = buildTextCard(p, cRaw);
    } else if (type === 'news' || type === 'noticia') {
      visualBuilder = buildNewsCard(p, cRaw);
    } else if (type === 'weather' || type === 'tempo' || type === 'clima') {
      visualBuilder = buildWeatherCard(p, cRaw);
    } else if (type === 'whatsapp' || type === 'zap') {
      visualBuilder = buildWhatsappCard(p, cRaw);
    } else if (type === 'chart' || type === 'echarts' || p.options || p.option || (p.data && Object.keys(p.data).length)) {
      const rawOpts = p.options || p.option || (p.data && (p.data.options || p.data.option)) || p.data
        || (isObj && (cRaw.chart_type || cRaw.series || cRaw.xAxis) ? cRaw : null);
      const opts = normalizeChartOptions(rawOpts);
      if (opts) {
        visualBuilder = buildECharts(opts, 200);
      } else if (type === 'chart' || type === 'echarts') {
        // Chart sem dados validos: placeholder em vez de card vazio
        visualBuilder = {
          html: '<div class="spatial-chart-empty">📊 Séries temporais em preparação — dados numéricos serão exibidos aqui.</div>',
          mount() { return null; }
        };
      }
    } else if (type === 'three_view' || type === '3d') {
      visualBuilder = buildThreeView(200);
    }

    const badgeList = (p.badges || (isObj ? cRaw.badges : null) || []);
    const badgesHtml = badgeList.length ? `<div class="spatial-badges">${badgeList.map(b => `<span class="spatial-badge">${esc(b)}</span>`).join('')}</div>` : '';
    const visualHtml = visualBuilder ? visualBuilder.html : '';

    // Anti-card-vazio: se nada de conteudo foi gerado, mostra placeholder legivel
    const hasBody = summary || badgesHtml || tags || bullets || tableHtml || compareHtml || visualHtml || metricsHtml;
    const placeholder = hasBody ? '' : `<p class="spatial-scene-copy spatial-empty-fallback">${esc(
      p.subtitle || p.caption || p.conclusion ||
      'Conteúdo em processamento — o J.A.R.V.I.S. está estruturando os dados deste tópico.'
    )}</p>`;

    const html = `
      ${summary ? `<p class="spatial-scene-copy">${esc(summary)}</p>` : ''}
      ${badgesHtml}
      ${tags ? `<div class="spatial-tags">${tags}</div>` : ''}
      ${bullets ? `<div class="spatial-bullets">${bullets}</div>` : ''}
      ${tableHtml}
      ${compareHtml}
      ${visualHtml}
      ${metricsHtml}
      ${placeholder}
    `;

    return {
      html,
      mount(dom) {
        if (visualBuilder && typeof visualBuilder.mount === 'function') {
          return visualBuilder.mount(dom);
        }
        return null;
      }
    };
  }

  const engine = {
    // Adiciona um card novo sobre o canvas preservando integralmente os existentes
    addSpatialComponent(arg1, arg2, arg3, arg4) {
      injectStyles();
      const canvas = getCanvas();
      if (!canvas) return false;

      let id, type, position, props;
      if (typeof arg1 === 'object' && arg1 !== null) {
        id = arg1.id || arg1.component_id || ('card_' + Date.now() + '_' + state.components.size);
        type = (arg1.type || 'narrative').toLowerCase();
        position = arg1.position || {};
        props = arg1.props || arg1;
      } else {
        id = arg1 || ('card_' + Date.now() + '_' + state.components.size);
        type = (arg2 || 'narrative').toLowerCase();
        position = arg3 || {};
        props = arg4 || {};
      }

      // Se o componente já existe, atualiza suavemente sem duplicar
      if (state.components.has(id)) {
        return this.updateSpatialComponent(id, { props, position });
      }

      const index = state.seq++;
      // Canvas vivo: maximo 4 cards - remove o mais antigo (nunca reaproveita)
      while (state.components.size >= 4) {
        const oldest = state.components.keys().next().value;
        if (oldest === id) break;
        this.removeSpatialComponent(oldest);
      }
      const geom = resolvePosition(position, index);

      const wrapper = document.createElement('div');
      wrapper.className = 'spatial-card-wrapper entering';
      wrapper.dataset.type = type;
      wrapper.id = `spatial-comp-${id}`;
      wrapper.style.left = geom.left;
      wrapper.style.top = geom.top;
      wrapper.style.width = geom.width;
      if (geom.height !== 'auto') wrapper.style.height = geom.height;
      if (geom.maxHeight) wrapper.style.maxHeight = geom.maxHeight;

      const built = buildCardContent(type, props);

      const cardKicker = props.kicker || props.subtitle || 'INTELIGÊNCIA // SPATIAL HUD';
      const cardTitle = props.title || 'CARD DE ANÁLISE';

      wrapper.innerHTML = `
        <div class="spatial-card-surface">
          <div class="spatial-card-header">
            <div class="spatial-card-title-group">
              <span class="spatial-card-dot"></span>
              <div>
                <div class="spatial-card-kicker">${esc(cardKicker)}</div>
                <div class="spatial-card-title">${esc(cardTitle)}</div>
              </div>
            </div>
            <button onclick="window.JarvisPresentationEngine && window.JarvisPresentationEngine.removeSpatialComponent('${esc(id)}')" class="spatial-card-close-btn" title="Fechar este card (Esc fecha todos)">
              ✕
            </button>
          </div>
          <div class="spatial-card-body">
            ${built.html}
          </div>
        </div>
      `;

      canvas.appendChild(wrapper);

      // Mount de gráficos interativos ou WebGL
      // try/catch: se o mount lançar erro (ex.: ECharts com opções ruins),
      // o card continua visível com o conteúdo estático em vez de sumir.
      let mountResult = null;
      if (typeof built.mount === 'function') {
        try {
          mountResult = built.mount(wrapper);
        } catch (err) {
          console.warn('[Spatial] mount falhou (card segue sem visual interativo):', err);
          mountResult = null;
        }
        if (mountResult) state.activeInstances.set(id, mountResult);
      }

      state.components.set(id, { dom: wrapper, type, position, props, mountResult });

      // Animação de entrada fluida (spring entrance)
      // Animacao de entrada - GSAP quando disponivel (fallback CSS acima)
      if (window.gsap) {
        wrapper.classList.remove('entering');
        try {
          window.gsap.fromTo(wrapper, { opacity: 0, y: 34, scale: 0.90, filter: 'blur(8px)' },
            { opacity: 1, y: 0, scale: 1, filter: 'blur(0px)', duration: 0.6, ease: 'back.out(1.5)' });
        } catch (e) {}
      } else {
        requestAnimationFrame(() => {
          wrapper.classList.remove('entering');
        });
      }

      updateGlobalActionsBadge();
      window.isPresentationActive = true;
      return true;
    },

    // Destaque luminoso quando o JARVIS estiver narrando sobre esse card
    highlightSpatialComponent(id, duration = 3.0) {
      const record = state.components.get(id);
      if (!record || !record.dom) return false;

      record.dom.classList.add('highlighted');
      setTimeout(() => {
        if (record.dom) record.dom.classList.remove('highlighted');
      }, duration * 1000);
      return true;
    },

    // Atualização pontual do conteúdo ou dados de um card existente
    updateSpatialComponent(id, updates, animate = true) {
      const record = state.components.get(id);
      if (!record || !record.dom) return false;

      if (updates.props) {
        Object.assign(record.props, updates.props);
      }
      if (updates.position) {
        const geom = resolvePosition(updates.position, 0);
        record.dom.style.left = geom.left;
        record.dom.style.top = geom.top;
        if (geom.width) record.dom.style.width = geom.width;
      }

      // Re-renderiza o corpo do card mantendo o DOM base
      const bodyEl = record.dom.querySelector('.spatial-card-body');
      if (bodyEl) {
        if (record.mountResult && typeof record.mountResult.cleanup === 'function') {
          record.mountResult.cleanup();
        }
        const built = buildCardContent(record.type, record.props);
        bodyEl.innerHTML = built.html;
        if (typeof built.mount === 'function') {
          try {
            const res = built.mount(record.dom);
            if (res) state.activeInstances.set(id, res);
          } catch (err) {
            console.warn('[Spatial] re-mount falhou (conteudo estatico mantido):', err);
          }
        }
      }

      if (animate) {
        this.highlightSpatialComponent(id, 1.5);
      }
      return true;
    },

    // Remove um card específico individualmente com animação suave
    removeSpatialComponent(id) {
      const record = state.components.get(id);
      if (!record) return false;

      if (record.mountResult && typeof record.mountResult.cleanup === 'function') {
        record.mountResult.cleanup();
      }
      state.activeInstances.delete(id);

      if (record.dom) {
        const dom = record.dom;
        if (window.gsap) {
          try {
            window.gsap.to(dom, { opacity: 0, scale: 0.9, y: -18, duration: 0.4, ease: 'power2.in', onComplete: () => dom.remove() });
          } catch (e) { dom.classList.add('leaving'); setTimeout(() => dom.remove(), 500); }
        } else {
          dom.classList.add('leaving');
          setTimeout(() => {
            if (dom) dom.remove();
          }, 500);
        }
      }

      state.components.delete(id);
      updateGlobalActionsBadge();
      if (state.components.size === 0) {
        window.isPresentationActive = false;
      }
      return true;
    },

    // Limpa todos os cards do canvas de forma orquestrada
    clearSpatialWorkspace() {
      this.cancelAutoAdvance();
      state.activeInstances.forEach(inst => {
        try {
          if (typeof inst.cleanup === 'function') inst.cleanup();
        } catch (e) {}
      });
      state.activeInstances.clear();

      state.components.forEach(record => {
        if (record.dom) {
          record.dom.classList.add('leaving');
          setTimeout(() => {
            if (record.dom) record.dom.remove();
          }, 450);
        }
      });
      state.components.clear();

      updateGlobalActionsBadge();
      window.isPresentationActive = false;
      return true;
    },

    close() {
      this.clearSpatialWorkspace();
    },

    // Inicia ou compõe um conjunto de cards
    compose(payload) {
      this.clearSpatialWorkspace();
      const comps = payload.components || [];
      comps.forEach((c, idx) => {
        this.addSpatialComponent(c.id || ('card_' + idx), c.type || 'narrative', c.position, c.props || c);
      });
      return true;
    },

    initSpatialWorkspace(payload) {
      return this.compose(payload || {});
    },

    createWorkspace(title = 'Spatial Workspace') {
      this.clearSpatialWorkspace();
      state.title = title;
      return true;
    },

    // Suporte ao start de apresentações progressivas ou sequenciais
    start(script) {
      this.clearSpatialWorkspace();
      const scenes = script.scenes || [];
      if (scenes.length === 0) {
        this.addSpatialComponent({
          id: 'card_main',
          type: 'narrative',
          props: {
            title: script.title || 'Apresentação Executiva',
            subtitle: script.subtitle || 'STARK HUD',
            content: script.content || 'Inteligência visual ativada.'
          }
        });
        return true;
      }

      // Adiciona a primeira cena como Card 1
      const sc1 = scenes[0];
      this.addSpatialComponent({
        id: uniqueId(sc1.scene_id || 'scene'),
        type: sc1.component_type || 'narrative',
        props: sc1
      });

      // Se houver cena 2, adiciona ao lado após um breve intervalo ou sincronizado
      state.currentScene = scenes[0];
      if (scenes.length > 1) {
        state.sceneQueue = scenes.slice(1);
        state.sceneIndex = 1;
        this.scheduleNextScene(scenes[0]);
      }
      return true;
    },

    next() {
      if (state.sceneQueue && state.sceneQueue.length > 0) {
        const nextScene = state.sceneQueue.shift();
        this.addSpatialComponent({
          id: uniqueId(nextScene.scene_id || 'scene'),
          type: nextScene.component_type || 'narrative',
          props: nextScene
        });
        state.currentScene = nextScene;
        this.scheduleNextScene(nextScene);
      }
    },

    // Cada cena recebida vira um card NOVO e unico no canvas.
    // Nunca reaproveita card anterior - cada assunto tem seu proprio card.
    renderCurrentScene(scene) {
      if (!scene || typeof scene !== 'object') return false;
      return this.addSpatialComponent({
        id: uniqueId(scene.scene_id || 'scene'),
        type: (scene.component_type || scene.type || 'narrative').toLowerCase(),
        props: scene
      });
    },

    // Controles de apresentacao (usados pelos eventos SSE do narrador)
    togglePlayPause() {
      state.paused = !state.paused;
      if (state.paused) {
        this.cancelAutoAdvance();
      } else {
        this.scheduleNextScene(state.currentScene);
      }
      return !state.paused;
    },

    prev() {
      const ids = Array.from(state.components.keys());
      if (ids.length) this.highlightSpatialComponent(ids[ids.length - 1], 2.5);
      return true;
    },

    jumpTo(index) {
      const ids = Array.from(state.components.keys());
      const id = ids[Math.max(0, Math.min(index, ids.length - 1))];
      if (id) this.highlightSpatialComponent(id, 3.0);
      return !!id;
    },

    close() {
      this.clearSpatialWorkspace();
      return true;
    },

    // Auto-avanço de cenas: cada cena fica na tela pelo seu duration_sec
    // (padrao 8s) e a proxima e criada como card NOVO. Garante que todas as
    // cenas da explicacao aparecam mesmo sem eventos de narracao.
    scheduleNextScene(scene) {
      this.cancelAutoAdvance();
      if (!state.sceneQueue || state.sceneQueue.length === 0) return;
      if (state.paused) return;
      const secs = (scene && parseFloat(scene.duration_sec)) || 8;
      const delay = Math.max(3, Math.min(30, secs)) * 1000;
      state.autoTimer = setTimeout(() => {
        state.autoTimer = null;
        if (!state.paused) this.next();
      }, delay);
    },

    cancelAutoAdvance() {
      if (state.autoTimer) {
        clearTimeout(state.autoTimer);
        state.autoTimer = null;
      }
    },

    isOpen() {
      return state.components.size > 0;
    }
  };

  // Resposta a mensagens DIRETO do card (POST p/ local_server -> WAHA)
  // A API key fica no backend - o browser nunca a vê.
  if (typeof window !== 'undefined') {
  window.JarvisWhatsApp = {
    send(chatId, session, idx) {
      const input = document.getElementById('wa_reply_' + idx);
      const btn = input && input.parentElement &&
                  input.parentElement.querySelector('.spatial-wa-reply-btn');
      const texto = (input ? input.value : '').trim();
      if (!texto || !input) return;
      if (btn) { btn.disabled = true; btn.textContent = '...'; }
      fetch('/api/whatsapp/reply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chat_id: chatId, text: texto, session: session })
      })
        .then(r => r.json())
        .then(res => {
          if (res && res.ok) {
            input.value = '';
            if (btn) btn.textContent = '✓ ENVIADO';
            if (window.showHudAlert) {
              window.showHudAlert('WHATSAPP', 'Mensagem enviada com sucesso.', 'sucesso');
            }
          } else {
            if (btn) btn.textContent = 'ERRO';
            if (window.showHudAlert) {
              window.showHudAlert('WHATSAPP',
                (res && res.error) || 'Falha ao enviar.', 'erro');
            }
          }
        })
        .catch(() => {
          if (btn) btn.textContent = 'ERRO';
          if (window.showHudAlert) {
            window.showHudAlert('WHATSAPP', 'Sem conexão com o servidor.', 'erro');
          }
        })
        .finally(() => {
          setTimeout(() => {
            if (btn) { btn.disabled = false; btn.textContent = 'ENVIAR'; }
          }, 2500);
        });
    }
  };
  }

  // Exposto apenas para testes automatizados (Node) - nao afeta o runtime
  engine._test = {
    normalizeChartOptions,
    buildCardContent,
    buildTextCard,
    buildNewsCard,
    buildWeatherCard,
    buildWhatsappCard,
    esc
  };

  if (typeof window !== 'undefined') {
    window.addEventListener('keydown', e => {
      if (e.key === 'Escape' && engine.isOpen()) {
        engine.clearSpatialWorkspace();
      }
    });
    window.JarvisPresentationEngine = engine;
  }

  return engine;
}));
