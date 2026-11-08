/**
 * J.A.R.V.I.S. Mark VII - Spatial Intelligence Workspace & Cinematic Presentation Engine
 * High-End Futuristic Glassmorphism, Apache ECharts 5.5, Three.js Holograms & Dynamic Topologies.
 */
(function (root, factory) {
  if (typeof define === 'function' && define.amd) define([], factory);
  else if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.JarvisPresentationEngine = factory();
}(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const state = {
    workspace: null,
    activeMode: 'spatial',
    components: new Map(),
    slideSession: null,
    slideIndex: 0,
    isPlaying: false
  };

  const esc = value => String(value == null ? '' : value).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
  })[c]);

  const clamp = (value, min, max) => {
    value = Number(value);
    return Number.isFinite(value) ? Math.min(max, Math.max(min, value)) : min;
  };

  function geometry(component, index) {
    const input = component.position || {};
    const width = clamp(input.width == null ? 48 : input.width, 10, 98);
    const height = clamp(input.height == null ? 46 : input.height, 10, 92);
    return {
      x: clamp(input.x == null ? (index % 2 === 0 ? 2 : 51) : input.x, 0, 100 - width),
      y: clamp(input.y == null ? (index < 2 ? 2 : 50) : input.y, 0, 100 - height),
      width, height,
      depth: clamp(input.depth == null ? 1 : input.depth, 0, 10),
      zIndex: Number(input.zIndex == null ? 5 : input.zIndex)
    };
  }

  function injectStyles() {
    const existing = document.getElementById('jarvis-spatial-cinema-style'); if (existing) existing.remove();
    const tag = document.createElement('style');
    tag.id = 'jarvis-spatial-cinema-style';
    tag.textContent = `
      #presentation-content-area.spatial-stage {
        padding: 0;
        overflow: hidden;
        display: block;
        width: 100%;
        height: 100%;
      }
      .spatial-workspace {
        position: relative;
        isolation: isolate;
        width: 100%;
        height: 100%;
        min-height: 580px;
        overflow: hidden;
        color: #f4f4f5;
        background: #000000;
        padding: 16px;
      }
      .spatial-workspace::before {
        content: '';
        position: absolute;
        inset: 0;
        pointer-events: none;
        opacity: 0.03;
        background-image: linear-gradient(rgba(255, 255, 255, 0.08) 1px, transparent 1px), linear-gradient(90deg, rgba(255, 255, 255, 0.08) 1px, transparent 1px);
        background-size: 40px 40px;
      }
      .spatial-el {
        position: absolute;
        box-sizing: border-box;
        transition: left 0.6s cubic-bezier(0.16, 1, 0.3, 1),
                    top 0.6s cubic-bezier(0.16, 1, 0.3, 1),
                    width 0.6s cubic-bezier(0.16, 1, 0.3, 1),
                    height 0.6s cubic-bezier(0.16, 1, 0.3, 1),
                    opacity 0.4s ease,
                    transform 0.6s cubic-bezier(0.16, 1, 0.3, 1);
      }
      .spatial-el.entering {
        opacity: 0;
        transform: translateY(20px) scale(0.97);
      }
      .spatial-surface {
        position: relative;
        width: 100%;
        height: 100%;
        border-radius: 18px;
        background: #09090b;
        border: 1px solid rgba(255, 255, 255, 0.08);
        box-shadow: 0 25px 60px rgba(0, 0, 0, 0.98), inset 0 1px 0 rgba(255, 255, 255, 0.04);
        backdrop-filter: blur(24px);
        padding: 20px 24px;
        display: flex;
        flex-direction: column;
        overflow: hidden;
        transition: border-color 0.3s ease, box-shadow 0.3s ease;
      }
      .spatial-surface:hover {
        border-color: rgba(255, 255, 255, 0.18);
        box-shadow: 0 30px 70px rgba(0, 0, 0, 1), inset 0 1px 0 rgba(255, 255, 255, 0.08);
      }
      .spatial-surface::before {
        content: '';
        position: absolute;
        top: 0; left: 15%; right: 15%; height: 1px;
        background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.22), transparent);
        opacity: 0.9;
      }
      /* Hero Card Typography - Kuro Black Style */
      .hero-kicker {
        font-family: 'JetBrains Mono', monospace;
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 2.5px;
        color: #71717a;
        text-transform: uppercase;
      }
      .hero-title {
        font-family: 'Space Grotesk', 'Segoe UI', sans-serif;
        font-size: clamp(20px, 1.8vw, 26px);
        font-weight: 800;
        color: #ffffff;
        letter-spacing: 0.5px;
        margin: 6px 0 10px;
        line-height: 1.15;
      }
      .hero-copy {
        font-size: 12px;
        color: #a1a1aa;
        line-height: 1.6;
        margin-bottom: 14px;
      }
      .hero-tag {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 9999px;
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(255, 255, 255, 0.10);
        font-family: 'JetBrains Mono', monospace;
        font-size: 9px;
        font-weight: 700;
        color: #e4e4e7;
        margin-right: 6px;
        margin-bottom: 6px;
      }
      .hero-bullet {
        display: flex;
        align-items: flex-start;
        gap: 8px;
        font-size: 11px;
        color: #d4d4d8;
        margin-bottom: 6px;
        line-height: 1.45;
      }
      .hero-bullet-dot {
        color: #71717a;
        font-weight: bold;
      }
      /* Metrics - Kuro Black Style */
      .metrics-grid {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 12px;
        height: 100%;
        align-items: center;
      }
      .metric-box {
        padding: 12px 14px;
        border-radius: 12px;
        background: #121214;
        border: 1px solid rgba(255, 255, 255, 0.06);
        display: flex;
        flex-direction: column;
        justify-content: space-between;
      }
      .metric-kicker {
        font-family: 'JetBrains Mono', monospace;
        font-size: 9px;
        font-weight: 700;
        color: #71717a;
        letter-spacing: 1.5px;
        text-transform: uppercase;
      }
      .metric-big {
        font-family: 'JetBrains Mono', monospace;
        font-size: clamp(22px, 2.2vw, 32px);
        font-weight: 800;
        color: #ffffff;
        margin: 4px 0;
      }
      .metric-trend {
        font-family: 'JetBrains Mono', monospace;
        font-size: 10px;
        color: #a1a1aa;
        font-weight: 600;
      }
      /* Chart Header */
      .chart-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 8px;
        flex-shrink: 0;
      }
      .chart-title {
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px;
        font-weight: 800;
        color: #ffffff;
        letter-spacing: 1.5px;
        text-transform: uppercase;
      }
      .chart-badge {
        font-family: 'JetBrains Mono', monospace;
        font-size: 9px;
        padding: 2px 8px;
        border-radius: 6px;
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.12);
        color: #a1a1aa;
        font-weight: 700;
      }
      /* Topology Graph */
      .topo-container {
        position: relative;
        width: 100%;
        height: 100%;
        overflow: hidden;
      }
      .topo-node {
        position: absolute;
        padding: 8px 14px;
        border-radius: 12px;
        background: #121214;
        border: 1px solid rgba(255, 255, 255, 0.12);
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.9);
        color: #ffffff;
        text-align: center;
        font-family: 'JetBrains Mono', monospace;
        font-size: 10px;
        font-weight: 700;
        transform: translate(-50%, -50%);
        backdrop-filter: blur(10px);
      }
      .topo-node.core {
        background: #18181b;
        border-color: rgba(255, 255, 255, 0.35);
        box-shadow: 0 0 25px rgba(255, 255, 255, 0.08);
        font-size: 11px;
        font-weight: 800;
        padding: 12px 18px;
      }
    `;
    document.head.appendChild(tag);
  }

  // BUILDER 1: HERO CARD
  function buildHeroCard(c) {
    const p = c.props || {};
    const kicker = p.kicker || p.badge || 'STARK INTELLIGENCE // SPATIAL OS';
    const title = p.title || 'Arquitetura Soberana';
    const summary = p.summary || p.subtitle || '';
    const tags = (p.tags || []).map(t => `<span class="hero-tag">${esc(t)}</span>`).join('');
    const bullets = (p.bullets || []).map(b => `
      <div class="hero-bullet">
        <span class="hero-bullet-dot">▸</span>
        <span>${esc(b)}</span>
      </div>
    `).join('');

    return {
      html: `
        <div class="spatial-surface">
          <div>
            <div class="hero-kicker">${esc(kicker)}</div>
            <h2 class="hero-title">${esc(title)}</h2>
            ${summary ? `<p class="hero-copy">${esc(summary)}</p>` : ''}
            ${tags ? `<div style="margin-bottom:12px">${tags}</div>` : ''}
          </div>
          ${bullets ? `<div style="margin-top:auto">${bullets}</div>` : ''}
        </div>
      `
    };
  }

  // BUILDER 2: METRIC DOCK
  function buildMetricDock(c) {
    const p = c.props || {};
    const title = p.title || 'TELEMETRIA DE PERFORMANCE COGNITIVA';
    const metrics = (p.metrics || []).slice(0, 4);

    const boxes = metrics.map(m => `
      <div class="metric-box">
        <span class="metric-kicker">${esc(m.label || 'MÉTRICA')}</span>
        <span class="metric-big">${esc(m.value || '--')}</span>
        <span class="metric-trend">${esc(m.trend || '● Nominal')}</span>
      </div>
    `).join('');

    return {
      html: `
        <div class="spatial-surface">
          <div class="chart-header">
            <span class="chart-title">${esc(title)}</span>
            <span class="chart-badge">● STARK SENSORS</span>
          </div>
          <div class="metrics-grid">
            ${boxes}
          </div>
        </div>
      `
    };
  }

  // BUILDER 3: APACHE ECHARTS
  function buildECharts(c) {
    const p = c.props || {};
    const title = p.title || 'ANÁLISE DE PERFORMANCE';
    const source = p.source || 'TELEMETRIA OFICIAL STARK';
    let chartOpts = p.options || p.option || {};
    if (!chartOpts.series || !chartOpts.series.length) {
      chartOpts = {
        series: [{
          type: 'pie',
          radius: ['45%', '70%'],
          center: ['50%', '50%'],
          avoidLabelOverlap: false,
          itemStyle: { borderRadius: 6, borderColor: '#020612', borderWidth: 2 },
          label: { show: false },
          data: [
            { value: 40, name: 'Cérebro & MiMo (40%)', itemStyle: { color: '#ffffff' } },
            { value: 25, name: 'Spatial Workspace (25%)', itemStyle: { color: '#a1a1aa' } },
            { value: 15, name: 'ZimaOS Cloud (15%)', itemStyle: { color: '#71717a' } },
            { value: 12, name: 'Automação Windows (12%)', itemStyle: { color: '#52525b' } },
            { value: 8, name: 'Esfera & Smart TV (8%)', itemStyle: { color: '#3f3f46' } }
          ]
        }],
        legend: {
          bottom: '2%',
          textStyle: { color: '#94a3b8', fontFamily: 'JetBrains Mono', fontSize: 10 }
        }
      };
    }

    return {
      html: `
        <div class="spatial-surface">
          <div class="chart-header">
            <span class="chart-title">${esc(title)}</span>
            <span class="chart-badge">${esc(source)}</span>
          </div>
          <div data-echart-target style="flex:1;width:100%;min-height:160px"></div>
        </div>
      `,
      mount(box) {
        const target = box.querySelector('[data-echart-target]');
        if (!target || !window.echarts) return null;
        const instance = window.echarts.init(target, null, { renderer: 'canvas' });
        
        const defaultStyle = {
          backgroundColor: 'transparent',
          textStyle: { color: '#94a3b8', fontFamily: 'JetBrains Mono', fontSize: 10 },
          grid: { left: 24, right: 14, top: 18, bottom: 24, containLabel: true },
          tooltip: {
            trigger: 'item',
            backgroundColor: '#09090b',
            borderColor: 'rgba(255, 255, 255, 0.12)',
            textStyle: { color: '#f4f4f5', fontFamily: 'JetBrains Mono', fontSize: 11 }
          }
        };

        instance.setOption(Object.assign(defaultStyle, chartOpts));
        const resize = () => instance.resize();
        window.addEventListener('resize', resize);
        setTimeout(resize, 60);
        setTimeout(resize, 250);

        return {
          instance,
          cleanup: () => {
            window.removeEventListener('resize', resize);
            instance.dispose();
          }
        };
      }
    };
  }

  // BUILDER 4: RELATIONSHIP MAP / TOPOLOGY
  function buildRelationshipMap(c) {
    const p = c.props || {};
    const title = p.title || 'TOPOLOGIA DO ECOSSISTEMA DISTRIBUÍDO';
    
    // 5 nós em formato de diamante equilibrado (nunca sobrepostos)
    const nodes = [
      { id: 'core', label: 'CÉREBRO SOBERANO', badge: 'LOCAL AI', x: 50, y: 50, isCore: true },
      { id: 'windows', label: 'HUD WINDOWS 11', badge: 'QHD 2560x1440', x: 18, y: 24 },
      { id: 'zima', label: 'ZIMAOS DOCKER', badge: '45.167.187.80', x: 82, y: 24 },
      { id: 'tv', label: 'SMART TV LG', badge: 'webOS 1080p', x: 18, y: 76 },
      { id: 'sphere', label: 'ESFERA ESP32-S3', badge: 'DevKitC-1 LCD', x: 82, y: 76 }
    ];

    const nodesHtml = nodes.map(n => `
      <div class="topo-node ${n.isCore ? 'core' : ''}" style="left:${n.x}%;top:${n.y}%">
        <div>${esc(n.label)}</div>
        <div style="font-size:8px;color:#a1a1aa;font-weight:normal;margin-top:2px">${esc(n.badge)}</div>
      </div>
    `).join('');

    return {
      html: `
        <div class="spatial-surface">
          <div class="chart-header">
            <span class="chart-title">${esc(title)}</span>
            <span class="chart-badge">● 5 NÓS ATIVOS</span>
          </div>
          <div class="topo-container">
            <svg style="position:absolute;inset:0;width:100%;height:100%;pointer-events:none">
              <!-- Conexões do Core para os Nós -->
              <line x1="50%" y1="50%" x2="18%" y2="24%" stroke="rgba(255,255,255,0.20)" stroke-width="1.5" stroke-dasharray="4 4" />
              <line x1="50%" y1="50%" x2="82%" y2="24%" stroke="rgba(255,255,255,0.20)" stroke-width="1.5" stroke-dasharray="4 4" />
              <line x1="50%" y1="50%" x2="18%" y2="76%" stroke="rgba(255,255,255,0.20)" stroke-width="1.5" stroke-dasharray="4 4" />
              <line x1="50%" y1="50%" x2="82%" y2="76%" stroke="rgba(255,255,255,0.20)" stroke-width="1.5" stroke-dasharray="4 4" />
              <circle cx="50%" cy="50%" r="48" fill="none" stroke="rgba(255,255,255,0.08)" stroke-width="1" />
            </svg>
            ${nodesHtml}
          </div>
        </div>
      `
    };
  }

  // BUILDER 5: THREE.JS 3D HOLOGRAPHIC CORE
  function buildThreeView(c) {
    const p = c.props || {};
    const title = p.title || 'MODELO ESPACIAL HOLOGRÁFICO 3D';

    return {
      html: `
        <div class="spatial-surface">
          <div class="chart-header">
            <span class="chart-title">${esc(title)}</span>
            <span class="chart-badge">WebGL THREE.JS</span>
          </div>
          <div data-three-host style="flex:1;width:100%;min-height:180px;position:relative"></div>
        </div>
      `,
      mount(box) {
        const host = box.querySelector('[data-three-host]');
        if (!host || !window.THREE) return null;

        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
        camera.position.set(0, 0, 5.2);

        const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
        host.appendChild(renderer.domElement);

        const group = new THREE.Group();
        // Núcleo Icosaedro holográfico monocromático titânio
        const coreGeo = new THREE.IcosahedronGeometry(1.2, 2);
        const coreMat = new THREE.MeshBasicMaterial({ color: 0xffffff, wireframe: true, transparent: true, opacity: 0.80 });
        const coreMesh = new THREE.Mesh(coreGeo, coreMat);
        group.add(coreMesh);

        // Anel orbital de titânio acetinado
        const ringGeo = new THREE.TorusGeometry(1.7, 0.02, 16, 100);
        const ringMat = new THREE.MeshBasicMaterial({ color: 0xa1a1aa, transparent: true, opacity: 0.65 });
        const ringMesh = new THREE.Mesh(ringGeo, ringMat);
        ringMesh.rotation.x = Math.PI * 0.45;
        group.add(ringMesh);

        // Anel grafite escuro
        const ring2Geo = new THREE.TorusGeometry(2.0, 0.015, 16, 100);
        const ring2Mat = new THREE.MeshBasicMaterial({ color: 0x52525b, transparent: true, opacity: 0.55 });
        const ring2Mesh = new THREE.Mesh(ring2Geo, ring2Mat);
        ring2Mesh.rotation.y = Math.PI * 0.35;
        group.add(ring2Mesh);

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
          ring2Mesh.rotation.x += 0.002;
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

  const COMPONENT_REGISTRY = {
    'hero_card': buildHeroCard,
    'narrative': buildHeroCard,
    'metric_dock': buildMetricDock,
    'echarts': buildECharts,
    'relationship_map': buildRelationshipMap,
    'power_triptych': buildRelationshipMap,
    'three_view': buildThreeView
  };

  const engine = {
    initSpatialWorkspace(payload) {
      injectStyles();
      state.workspace = payload || {};
      state.components.clear();

      window.isPresentationActive = true;
      const stageContainer = document.getElementById('presentation-stage');
      const mount = document.getElementById('presentation-content-area');
      const titleEl = document.getElementById('presentation-header-title');

      if (titleEl && payload.title) {
        titleEl.textContent = payload.title.toUpperCase();
      }

      if (mount) {
        mount.innerHTML = '';
        mount.className = 'spatial-stage';
        const stage = document.createElement('div');
        stage.className = 'spatial-workspace';
        mount.appendChild(stage);
      }

      if (stageContainer) {
        stageContainer.classList.remove('opacity-0', 'pointer-events-none');
        stageContainer.classList.add('opacity-100', 'pointer-events-auto');
      }

      // Oculta suavemente o vórtice central para dar lugar ao palco limpo
      const vortex = document.getElementById('plasma-core') || document.querySelector('.vortex-container') || document.getElementById('vortex-container');
      if (vortex) {
        vortex.style.transition = 'opacity 0.6s cubic-bezier(0.16, 1, 0.3, 1), transform 0.6s cubic-bezier(0.16, 1, 0.3, 1)';
        vortex.style.opacity = '0';
        vortex.style.transform = 'scale(0.85)';
        vortex.style.pointerEvents = 'none';
      }
      const visStage = document.getElementById('jarvis-visual-stage');
      if (visStage) {
        visStage.classList.add('hidden', 'opacity-0');
        visStage.innerHTML = '';
      }
      if (typeof closeRightSidebar === 'function') {
        closeRightSidebar();
      }

      let rawComps = payload.components;
      if (!rawComps && Array.isArray(payload.scenes) && payload.scenes.length > 0) {
        rawComps = payload.scenes[0].components;
        if (!payload.title && payload.scenes[0].title) {
          payload.title = payload.scenes[0].title;
        }
      }
      const comps = Array.isArray(rawComps) ? rawComps : (rawComps && typeof rawComps === 'object' ? Object.values(rawComps) : []);
      comps.forEach((c, idx) => {
        this.addSpatialComponent(c.id || ('comp_' + idx), c.type || 'hero_card', c.position, c.props || c, idx);
      });

      return true;
    },

    createWorkspace(title = 'Spatial Workspace') {
      return this.initSpatialWorkspace({ title, components: [] });
    },

    compose(payload) {
      return this.initSpatialWorkspace(payload);
    },

    addSpatialComponent(arg1, arg2, arg3, arg4, arg5 = 0) {
      let id, type, position, props, index;
      if (typeof arg1 === 'object' && arg1 !== null) {
        id = arg1.id || arg1.component_id || ('comp_' + state.components.size);
        type = arg1.type || 'hero_card';
        position = arg1.position || {};
        props = arg1.props || arg1;
        index = arg2 || state.components.size;
      } else {
        id = arg1 || ('comp_' + state.components.size);
        type = arg2 || 'hero_card';
        position = arg3 || {};
        props = arg4 || {};
        index = arg5 || state.components.size;
      }

      const stage = document.querySelector('.spatial-workspace');
      if (!stage) return false;

      const compData = { id, type, position: position || {}, props: props || {} };
      const geom = geometry(compData, index);

      const el = document.createElement('div');
      el.className = 'spatial-el entering';
      el.id = `spatial-comp-${id}`;
      el.style.left = `${geom.x}%`;
      el.style.top = `${geom.y}%`;
      el.style.width = `${geom.width}%`;
      el.style.height = `${geom.height}%`;
      el.style.zIndex = geom.zIndex;

      const builder = COMPONENT_REGISTRY[type] || buildHeroCard;
      const built = builder(compData);
      el.innerHTML = built.html;

      stage.appendChild(el);

      let mountResult = null;
      if (typeof built.mount === 'function') {
        mountResult = built.mount(el);
      }

      state.components.set(id, { dom: el, data: compData, mountResult });

      requestAnimationFrame(() => {
        el.classList.remove('entering');
      });

      return true;
    },

    clearSpatialWorkspace() {
      state.components.forEach(record => {
        if (record.mountResult && typeof record.mountResult.cleanup === 'function') {
          record.mountResult.cleanup();
        }
        if (record.dom) record.dom.remove();
      });
      state.components.clear();

      window.isPresentationActive = false;
      const stageContainer = document.getElementById('presentation-stage');
      if (stageContainer) {
        stageContainer.classList.remove('opacity-100', 'pointer-events-auto');
        stageContainer.classList.add('opacity-0', 'pointer-events-none');
      }

      // Restaura o vórtice central do J.A.R.V.I.S.
      const vortex = document.getElementById('plasma-core') || document.querySelector('.vortex-container') || document.getElementById('vortex-container');
      if (vortex) {
        vortex.style.opacity = '1';
        vortex.style.transform = 'scale(1)';
        vortex.style.pointerEvents = 'auto';
      }
    },

    close() {
      this.clearSpatialWorkspace();
    },

    start(script) {
      return this.initSpatialWorkspace(script);
    },

    isOpen() {
      return Boolean(window.isPresentationActive);
    }
  };

  if (typeof window !== 'undefined') {
    window.addEventListener('keydown', e => {
      if (e.key === 'Escape' && engine.isOpen()) {
        engine.close();
      }
    });
    window.JarvisPresentationEngine = engine;
  }

  return engine;
}));
