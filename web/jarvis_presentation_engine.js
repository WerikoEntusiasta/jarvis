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
    sceneIndex: 0
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
  function buildCardContent(type, p) {
    const summary = p.summary || p.content || '';
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

    let visualBuilder = null;
    if (type === 'chart' || type === 'echarts' || p.options || p.option || p.data) {
      const opts = p.options || p.option || (p.data && (p.data.options || p.data.option)) || p.data;
      visualBuilder = buildECharts(opts, 200);
    } else if (type === 'three_view' || type === '3d') {
      visualBuilder = buildThreeView(200);
    }

    const html = `
      ${summary ? `<p class="spatial-scene-copy">${esc(summary)}</p>` : ''}
      ${tags ? `<div class="spatial-tags">${tags}</div>` : ''}
      ${bullets ? `<div class="spatial-bullets">${bullets}</div>` : ''}
      ${visualBuilder ? visualBuilder.html : ''}
      ${metricsHtml}
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

      const index = state.components.size;
      const geom = resolvePosition(position, index);

      const wrapper = document.createElement('div');
      wrapper.className = 'spatial-card-wrapper entering';
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
      let mountResult = null;
      if (typeof built.mount === 'function') {
        mountResult = built.mount(wrapper);
        if (mountResult) state.activeInstances.set(id, mountResult);
      }

      state.components.set(id, { dom: wrapper, type, position, props, mountResult });

      // Animação de entrada fluida (spring entrance)
      requestAnimationFrame(() => {
        wrapper.classList.remove('entering');
      });

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
          const res = built.mount(record.dom);
          if (res) state.activeInstances.set(id, res);
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
        record.dom.classList.add('leaving');
        setTimeout(() => {
          if (record.dom) record.dom.remove();
        }, 500);
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
        id: sc1.scene_id || 'scene_1',
        type: sc1.component_type || 'narrative',
        props: sc1
      });

      // Se houver cena 2, adiciona ao lado após um breve intervalo ou sincronizado
      if (scenes.length > 1) {
        state.sceneQueue = scenes.slice(1);
        state.sceneIndex = 1;
      }
      return true;
    },

    next() {
      if (state.sceneQueue && state.sceneQueue.length > 0) {
        const nextScene = state.sceneQueue.shift();
        this.addSpatialComponent({
          id: nextScene.scene_id || ('scene_' + (++state.sceneIndex)),
          type: nextScene.component_type || 'narrative',
          props: nextScene
        });
      }
    },

    isOpen() {
      return state.components.size > 0;
    }
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
