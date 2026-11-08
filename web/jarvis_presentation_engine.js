/**
 * J.A.R.V.I.S. DYNAMIC PRESENTATION ENGINE
 * ============================================================================
 * Transforma as respostas e explicações do J.A.R.V.I.S. em experiências visuais
 * cinematográficas, multimodais e interativas de alta fidelidade no HUD.
 * 
 * Componentes Suportados:
 * - hologram_card  : Painel holográfico Stark com métricas e detalhes
 * - video          : Player holográfico (MP4/WebM/YouTube) com fallback resiliente
 * - gallery        : Visualizador de imagens em alta resolução com ken-burns
 * - chart          : Gráficos dinâmicos animados (Linhas Bézier, Barras Neon, Doughnut, Radar)
 * - table          : Tabela dinâmica com visual cyberpunk e status badges
 * - map            : Mapa tático holográfico com radar scan e rotas em arco
 * - diagram        : Diagramas de fluxo e arquitetura com pulsos de dados SVG
 * - comparison     : Comparativo visual A vs B lado a lado com métricas
 * - metric_grid    : Gauges e contadores numéricos animados (odômetro)
 * - conclusion     : Card executivo de encerramento com síntese e ações
 * ============================================================================
 */

(function (root, factory) {
  if (typeof define === 'function' && define.amd) {
    define([], factory);
  } else if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.JarvisPresentationEngine = factory();
  }
}(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  // =========================================================================
  // 1. GERENCIADOR DE ESTADO & RECURSOS
  // =========================================================================
  const state = {
    activeSession: null,
    currentSceneIndex: 0,
    isPlaying: false,
    timer: null,
    dimBackground: true,
    trackedMedia: new Set(),
    trackedTimers: new Set()
  };

  function _clearAllTrackedResources() {
    // Para e limpa todos os timers ativos
    if (state.timer) {
      clearTimeout(state.timer);
      state.timer = null;
    }
    state.trackedTimers.forEach(t => clearTimeout(t));
    state.trackedTimers.clear();

    // Destrói elementos de vídeo e áudio para evitar vazamento de memória e som
    state.trackedMedia.forEach(mediaEl => {
      try {
        if (typeof mediaEl.pause === 'function') mediaEl.pause();
        if ('src' in mediaEl) mediaEl.src = '';
        if (typeof mediaEl.load === 'function') mediaEl.load();
        if (mediaEl.parentNode) mediaEl.parentNode.removeChild(mediaEl);
      } catch (e) {
        console.debug('[PresentationEngine] Erro ao limpar mídia:', e);
      }
    });
    state.trackedMedia.clear();
  }

  // =========================================================================
  // 2. UTILITÁRIOS VISUAIS & ANIMAÇÃO DE CONTAGEM (ODÔMETRO)
  // =========================================================================
  function _animateCounter(el, targetVal, duration = 1200, unit = '') {
    if (!el) return;
    const isNum = !isNaN(parseFloat(targetVal));
    if (!isNum) {
      el.innerText = targetVal + unit;
      return;
    }
    const target = parseFloat(targetVal);
    const start = 0;
    const startTime = performance.now();
    const isFloat = String(targetVal).includes('.');

    function update(now) {
      const elapsed = now - startTime;
      const progress = Math.min(1, elapsed / duration);
      // Easing cúbico para desaceleração suave
      const ease = 1 - Math.pow(1 - progress, 3);
      const current = start + (target - start) * ease;
      el.innerText = (isFloat ? current.toFixed(1) : Math.round(current)) + unit;
      if (progress < 1) {
        requestAnimationFrame(update);
      } else {
        el.innerText = target + unit;
      }
    }
    requestAnimationFrame(update);
  }

  // =========================================================================
  // 3. RENDERIZADORES DE COMPONENTES VISUAIS MULTIMODAIS
  // =========================================================================
  const renderers = {

    /**
     * PAINEL HOLOGRÁFICO
     */
    hologram_card(scene) {
      const tags = (scene.tags || []).map(t => 
        `<span class="px-2 py-0.5 rounded-full bg-cyan-950/80 border border-cyan-500/40 text-[9px] font-mono-code font-bold text-cyan-300">#${t}</span>`
      ).join(' ');

      const bullets = (scene.bullets || []).map((b, i) => `
        <li class="flex items-start space-x-2.5 text-xs text-slate-200 leading-relaxed group">
          <span class="w-1.5 h-1.5 rounded-full bg-cyan-400 mt-1.5 shrink-0 shadow-[0_0_8px_rgba(0,240,255,0.8)] group-hover:scale-125 transition-transform"></span>
          <span>${b}</span>
        </li>
      `).join('');

      return `
        <div class="glass-card-stark p-6 rounded-2xl w-full max-w-3xl mx-auto shadow-[0_0_35px_rgba(0,210,255,0.25)] border border-cyan-400/50 font-mono-code relative overflow-hidden animate-slide-up">
          <div class="absolute -right-16 -top-16 w-36 h-36 bg-cyan-500/10 rounded-full blur-2xl pointer-events-none"></div>
          
          <div class="flex items-center justify-between pb-3 border-b border-cyan-500/20 mb-4">
            <div class="flex items-center space-x-2">
              <span class="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-ping"></span>
              <span class="text-xs font-bold text-cyan-300 tracking-wider uppercase font-hud">${scene.title || 'PAINEL HOLOGRÁFICO'}</span>
            </div>
            <div class="flex items-center space-x-1.5">${tags}</div>
          </div>

          ${scene.subtitle ? `<p class="text-xs text-cyan-200/90 font-sans mb-3 italic">${scene.subtitle}</p>` : ''}
          
          <div class="text-xs text-slate-100 font-sans leading-relaxed mb-4">
            ${scene.content || ''}
          </div>

          ${bullets ? `<ul class="space-y-2 mb-4 p-3 rounded-xl bg-slate-950/60 border border-cyan-500/20">${bullets}</ul>` : ''}

          ${scene.metrics && scene.metrics.length ? `
            <div class="grid grid-cols-2 sm:grid-cols-3 gap-2.5 pt-3 border-t border-cyan-500/20">
              ${scene.metrics.map((m, idx) => `
                <div class="p-2.5 rounded-xl bg-slate-900/70 border border-cyan-500/20 text-center">
                  <div class="text-[9px] text-slate-400 uppercase tracking-wider">${m.label}</div>
                  <div class="text-sm font-extrabold text-cyan-300 font-mono-code mt-0.5 odometer-val" data-val="${m.value}" data-unit="${m.unit || ''}">${m.value}${m.unit || ''}</div>
                </div>
              `).join('')}
            </div>
          ` : ''}
        </div>
      `;
    },

    /**
     * VÍDEO CINEMATOGRÁFICO COM FALLBACK
     */
    video(scene) {
      const videoSrc = scene.media?.url || scene.video_url || '';
      const fallbackImg = scene.media?.fallback_image || scene.thumbnail || 'https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?w=1200&auto=format&fit=crop&q=80';
      const isYoutube = videoSrc.includes('youtube.com') || videoSrc.includes('youtu.be');
      const videoId = isYoutube ? (videoSrc.match(/(?:embed\/|v=|vi\/|youtu\.be\/|\/v\/)([^#\&\?]*).*/)?.[1] || '') : '';

      return `
        <div class="glass-card-stark p-4 rounded-2xl w-full max-w-4xl mx-auto shadow-[0_0_40px_rgba(0,210,255,0.3)] border border-cyan-400/60 relative overflow-hidden animate-slide-up">
          <div class="flex items-center justify-between pb-2 mb-3 border-b border-cyan-500/20">
            <div class="flex items-center space-x-2">
              <span class="w-2.5 h-2.5 rounded-full bg-rose-500 animate-pulse"></span>
              <span class="text-xs font-bold text-white font-hud tracking-wider uppercase">${scene.title || 'TRANSMISSÃO DE VÍDEO'}</span>
            </div>
            <span class="text-[9px] font-mono-code text-cyan-400 px-2 py-0.5 rounded bg-cyan-950/80 border border-cyan-500/40">HD FEED // STREAM</span>
          </div>

          <div class="relative w-full aspect-video rounded-xl overflow-hidden bg-slate-950 border border-cyan-500/30 flex items-center justify-center group" id="pres-video-container-${scene.scene_id || '0'}">
            ${isYoutube ? `
              <iframe 
                class="w-full h-full rounded-xl"
                src="https://www.youtube.com/embed/${videoId}?autoplay=1&mute=0&controls=1&rel=0"
                frameborder="0"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowfullscreen>
              </iframe>
            ` : `
              <video 
                id="pres-video-player-${scene.scene_id || '0'}"
                class="w-full h-full object-cover rounded-xl"
                controls 
                autoplay 
                playsinline
                onerror="JarvisPresentationEngine.handleMediaFallback('${scene.scene_id || '0'}', '${fallbackImg}')">
                <source src="${videoSrc}" type="video/mp4">
                Seu navegador não suporta este formato de vídeo.
              </video>
            `}
            
            <!-- Fallback Overlay (invisível até erro ocorrer) -->
            <div id="pres-fallback-container-${scene.scene_id || '0'}" class="absolute inset-0 bg-slate-950 hidden flex-col items-center justify-center p-6 text-center">
              <img src="${fallbackImg}" class="absolute inset-0 w-full h-full object-cover opacity-35 filter blur-xs">
              <div class="relative z-10 space-y-2 max-w-md">
                <div class="text-3xl">⚠️</div>
                <h4 class="text-sm font-bold text-white font-hud uppercase">FLUXO DE VÍDEO NÃO DISPONÍVEL</h4>
                <p class="text-xs text-slate-300">O servidor de mídia de origem está temporariamente inacessível. O J.A.R.V.I.S. ativou o modo descritivo.</p>
                <div class="p-3 rounded-lg bg-slate-900/90 border border-cyan-500/30 text-xs text-cyan-200">
                  ${scene.content || 'Transmissão alternativa de telemetria e dados.'}
                </div>
              </div>
            </div>
          </div>

          ${scene.caption ? `
            <div class="mt-3 p-2.5 rounded-xl bg-slate-950/70 border border-cyan-500/20 text-xs text-slate-200 flex items-center space-x-2">
              <span class="text-cyan-400">ℹ️</span>
              <span>${scene.caption}</span>
            </div>
          ` : ''}
        </div>
      `;
    },

    /**
     * GALERIA / IMAGEM EM ALTA DEFINIÇÃO
     */
    gallery(scene) {
      const items = scene.items || (scene.media?.images) || [{
        url: scene.media?.url || scene.image_url || 'https://images.unsplash.com/photo-1507499739999-097706ad8914?w=1200&auto=format&fit=crop&q=80',
        title: scene.title,
        caption: scene.caption || scene.content
      }];

      return `
        <div class="glass-card-stark p-5 rounded-2xl w-full max-w-4xl mx-auto shadow-[0_0_35px_rgba(0,210,255,0.25)] border border-cyan-400/50 font-mono-code animate-slide-up">
          <div class="flex items-center justify-between pb-3 mb-3 border-b border-cyan-500/20">
            <div class="flex items-center space-x-2">
              <span class="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-pulse"></span>
              <span class="text-xs font-bold text-white font-hud uppercase">${scene.title || 'EXPLORAÇÃO VISUAL'}</span>
            </div>
            <span class="text-[9px] text-cyan-300 bg-cyan-950/80 px-2 py-0.5 rounded border border-cyan-500/40">ALTA RESOLUÇÃO // 4K CINE</span>
          </div>

          <div class="grid grid-cols-1 ${items.length > 1 ? 'md:grid-cols-2' : ''} gap-3.5">
            ${items.map((item, idx) => `
              <div class="rounded-xl overflow-hidden bg-slate-950 border border-cyan-500/30 group relative">
                <div class="aspect-video overflow-hidden relative">
                  <img src="${item.url}" 
                       alt="${item.title || ''}" 
                       class="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105"
                       onerror="this.src='https://images.unsplash.com/photo-1518770660439-4636190af475?w=800&auto=format&fit=crop&q=80'">
                  <div class="absolute inset-0 bg-gradient-to-t from-slate-950 via-slate-950/30 to-transparent"></div>
                  <div class="absolute bottom-2.5 left-3 right-3">
                    <h5 class="text-xs font-bold text-white font-hud drop-shadow">${item.title || ''}</h5>
                    ${item.caption ? `<p class="text-[10px] text-cyan-200/90 font-sans line-clamp-2 mt-0.5">${item.caption}</p>` : ''}
                  </div>
                </div>
              </div>
            `).join('')}
          </div>

          ${scene.content ? `
            <div class="mt-3.5 p-3 rounded-xl bg-slate-950/60 border border-cyan-500/20 text-xs text-slate-200 font-sans leading-relaxed">
              ${scene.content}
            </div>
          ` : ''}
        </div>
      `;
    },

    /**
     * GRÁFICOS DINÂMICOS ANIMADOS (SVG Bézier / Neon Bars / Donut / Radar)
     */
    chart(scene) {
      const chartType = scene.chart_type || scene.data?.type || 'line';
      const labels = scene.data?.labels || scene.labels || ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun'];
      const values = scene.data?.values || scene.values || [35, 59, 80, 81, 56, 95];
      const maxVal = Math.max(...values, 10);
      const minVal = Math.min(...values, 0);

      const svgW = 540;
      const svgH = 180;
      const stepX = labels.length > 1 ? (svgW - 60) / (labels.length - 1) : svgW - 60;

      let chartSvg = '';

      if (chartType === 'bar') {
        const barW = Math.max(16, ((svgW - 80) / values.length) - 12);
        chartSvg = values.map((v, i) => {
          const normH = ((v - minVal) / (maxVal - minVal)) * (svgH - 50);
          const x = 40 + i * (((svgW - 80) / values.length));
          const y = svgH - 30 - normH;
          return `
            <g class="transition-all duration-500 hover:opacity-80 cursor-pointer">
              <rect x="${x}" y="${y}" width="${barW}" height="${normH}" rx="4" fill="url(#neonCyanGrad)" class="filter drop-shadow-[0_0_8px_rgba(0,240,255,0.4)]">
                <animate attributeName="height" from="0" to="${normH}" dur="0.8s" fill="freeze" />
                <animate attributeName="y" from="${svgH - 30}" to="${y}" dur="0.8s" fill="freeze" />
              </rect>
              <text x="${x + barW/2}" y="${y - 6}" text-anchor="middle" fill="#00f0ff" font-size="10" font-family="'JetBrains Mono', monospace" font-weight="bold">${v}</text>
              <text x="${x + barW/2}" y="${svgH - 12}" text-anchor="middle" fill="#94a3b8" font-size="9" font-family="'JetBrains Mono', monospace">${labels[i] || ''}</text>
            </g>
          `;
        }).join('');
      } else if (chartType === 'donut' || chartType === 'pie') {
        // Gráfico circular SVG Donut
        const cx = svgW / 2;
        const cy = svgH / 2;
        const radius = 60;
        const circ = 2 * Math.PI * radius;
        const total = values.reduce((a, b) => a + b, 0) || 1;
        let runningOffset = 0;
        const colors = ['#00f0ff', '#38bdf8', '#818cf8', '#34d399', '#fbbf24', '#f43f5e'];

        chartSvg = values.map((v, i) => {
          const pct = v / total;
          const strokeDash = pct * circ;
          const strokeOffset = runningOffset;
          runningOffset -= strokeDash;
          const color = colors[i % colors.length];
          return `
            <circle cx="${cx - 80}" cy="${cy}" r="${radius}" fill="none" stroke="${color}" stroke-width="20"
                    stroke-dasharray="${strokeDash} ${circ - strokeDash}"
                    stroke-dashoffset="${strokeOffset}"
                    class="filter drop-shadow-[0_0_6px_${color}] transition-all duration-700">
              <animate attributeName="stroke-dasharray" from="0 ${circ}" to="${strokeDash} ${circ - strokeDash}" dur="1s" fill="freeze" />
            </circle>
          `;
        }).join('');

        // Adiciona legenda lateral
        const legendSvg = values.map((v, i) => `
          <g transform="translate(${cx + 30}, ${30 + i * 22})">
            <rect width="10" height="10" rx="2" fill="${colors[i % colors.length]}" />
            <text x="18" y="9" fill="#e2e8f0" font-size="10" font-family="'JetBrains Mono', monospace">${labels[i] || ''}: <tspan fill="${colors[i % colors.length]}" font-weight="bold">${v} (${Math.round((v/total)*100)}%)</tspan></text>
          </g>
        `).join('');

        chartSvg += legendSvg;
      } else {
        // Linhas com curva Bézier Spline Suave (Default)
        const pts = values.map((v, i) => {
          const x = 30 + i * stepX;
          const normY = ((v - minVal) / (maxVal - minVal)) * (svgH - 60);
          const y = svgH - 30 - normY;
          return { x, y, v };
        });

        let pathD = `M ${pts[0].x} ${pts[0].y}`;
        for (let i = 0; i < pts.length - 1; i++) {
          const p0 = pts[i];
          const p1 = pts[i + 1];
          const cx = (p0.x + p1.x) / 2;
          pathD += ` C ${cx} ${p0.y}, ${cx} ${p1.y}, ${p1.x} ${p1.y}`;
        }
        const areaD = `${pathD} L ${pts[pts.length - 1].x} ${svgH - 25} L ${pts[0].x} ${svgH - 25} Z`;

        chartSvg = `
          <path d="${areaD}" fill="url(#neonAreaGrad)" opacity="0.6" />
          <path d="${pathD}" fill="none" stroke="#00f0ff" stroke-width="2.5" class="filter drop-shadow-[0_0_10px_rgba(0,240,255,0.7)]">
            <animate attributeName="stroke-dashoffset" from="1000" to="0" dur="1.2s" fill="freeze" />
          </path>
          ${pts.map((p, i) => `
            <g class="cursor-pointer group">
              <circle cx="${p.x}" cy="${p.y}" r="4" fill="#020617" stroke="#00f0ff" stroke-width="2" class="group-hover:r-6 transition-all filter drop-shadow-[0_0_6px_#00f0ff]" />
              <text x="${p.x}" y="${p.y - 8}" text-anchor="middle" fill="#00f0ff" font-size="9" font-family="'JetBrains Mono', monospace" font-weight="bold">${p.v}</text>
              <text x="${p.x}" y="${svgH - 10}" text-anchor="middle" fill="#94a3b8" font-size="9" font-family="'JetBrains Mono', monospace">${labels[i] || ''}</text>
            </g>
          `).join('')}
        `;
      }

      return `
        <div class="glass-card-stark p-5 rounded-2xl w-full max-w-3xl mx-auto shadow-[0_0_35px_rgba(0,210,255,0.25)] border border-cyan-400/50 font-mono-code animate-slide-up">
          <div class="flex items-center justify-between pb-3 mb-3 border-b border-cyan-500/20">
            <div class="flex items-center space-x-2">
              <span class="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-pulse"></span>
              <span class="text-xs font-bold text-white font-hud uppercase">${scene.title || 'ANÁLISE DE DADOS GRÁFICOS'}</span>
            </div>
            <span class="text-[9px] font-mono-code text-cyan-300 bg-cyan-950/80 px-2 py-0.5 rounded border border-cyan-500/40">TELEMETRIA DINÂMICA</span>
          </div>

          ${scene.subtitle ? `<p class="text-xs text-slate-300 font-sans mb-3">${scene.subtitle}</p>` : ''}

          <div class="w-full overflow-x-auto p-2 rounded-xl bg-slate-950/70 border border-cyan-500/20 flex items-center justify-center">
            <svg viewBox="0 0 ${svgW} ${svgH}" class="w-full max-w-2xl h-auto">
              <defs>
                <linearGradient id="neonCyanGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stop-color="#00f0ff" stop-opacity="1" />
                  <stop offset="100%" stop-color="#0284c7" stop-opacity="0.3" />
                </linearGradient>
                <linearGradient id="neonAreaGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stop-color="#00f0ff" stop-opacity="0.4" />
                  <stop offset="100%" stop-color="#00f0ff" stop-opacity="0.0" />
                </linearGradient>
              </defs>
              <!-- Linhas de Grade de Fundo -->
              <line x1="20" y1="${svgH - 25}" x2="${svgW - 20}" y2="${svgH - 25}" stroke="rgba(0,240,255,0.15)" stroke-width="1" />
              <line x1="20" y1="${(svgH - 25)/2}" x2="${svgW - 20}" y2="${(svgH - 25)/2}" stroke="rgba(0,240,255,0.1)" stroke-dasharray="4 4" />
              ${chartSvg}
            </svg>
          </div>

          ${scene.content ? `
            <div class="mt-3 p-3 rounded-xl bg-slate-950/50 border border-cyan-500/20 text-xs text-slate-200 font-sans leading-relaxed">
              ${scene.content}
            </div>
          ` : ''}
        </div>
      `;
    },

    /**
     * TABELA DINÂMICA CYBERPUNK
     */
    table(scene) {
      const headers = scene.headers || scene.data?.headers || ['Parâmetro', 'Status', 'Valor', 'Variação'];
      const rows = scene.rows || scene.data?.rows || [];

      return `
        <div class="glass-card-stark p-5 rounded-2xl w-full max-w-4xl mx-auto shadow-[0_0_35px_rgba(0,210,255,0.25)] border border-cyan-400/50 font-mono-code animate-slide-up">
          <div class="flex items-center justify-between pb-3 mb-3 border-b border-cyan-500/20">
            <div class="flex items-center space-x-2">
              <span class="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-pulse"></span>
              <span class="text-xs font-bold text-white font-hud uppercase">${scene.title || 'TABELA COMPARATIVA / DADOS'}</span>
            </div>
            <span class="text-[9px] text-cyan-300 bg-cyan-950/80 px-2 py-0.5 rounded border border-cyan-500/40">${rows.length} REGISTROS</span>
          </div>

          <div class="overflow-x-auto rounded-xl border border-cyan-500/30 bg-slate-950/80">
            <table class="w-full text-left text-xs text-slate-200">
              <thead class="bg-cyan-950/70 border-b border-cyan-500/30 text-cyan-300 font-bold uppercase tracking-wider text-[10px]">
                <tr>
                  ${headers.map(h => `<th class="py-2.5 px-4">${h}</th>`).join('')}
                </tr>
              </thead>
              <tbody class="divide-y divide-cyan-500/10 font-mono-code text-[11px]">
                ${rows.map((r, i) => `
                  <tr class="hover:bg-cyan-500/10 transition-colors">
                    ${r.map((col, cIdx) => {
                      let colStr = String(col);
                      let badge = '';
                      if (colStr.toLowerCase() === 'ativo' || colStr.toLowerCase() === 'online' || colStr.toLowerCase() === 'ok') {
                        badge = `<span class="px-2 py-0.5 rounded bg-emerald-500/20 border border-emerald-400/50 text-emerald-300 text-[10px] font-bold">● ${colStr}</span>`;
                      } else if (colStr.toLowerCase() === 'alerta' || colStr.toLowerCase() === 'aviso') {
                        badge = `<span class="px-2 py-0.5 rounded bg-amber-500/20 border border-amber-400/50 text-amber-300 text-[10px] font-bold">▲ ${colStr}</span>`;
                      } else if (colStr.toLowerCase() === 'erro' || colStr.toLowerCase() === 'crítico' || colStr.toLowerCase() === 'off') {
                        badge = `<span class="px-2 py-0.5 rounded bg-rose-500/20 border border-rose-400/50 text-rose-300 text-[10px] font-bold">✕ ${colStr}</span>`;
                      }
                      return `<td class="py-2.5 px-4">${badge || colStr}</td>`;
                    }).join('')}
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>

          ${scene.content ? `
            <div class="mt-3 p-3 rounded-xl bg-slate-950/60 border border-cyan-500/20 text-xs text-slate-200 font-sans leading-relaxed">
              ${scene.content}
            </div>
          ` : ''}
        </div>
      `;
    },

    /**
     * MAPA TÁTICO HOLOGRÁFICO COM RADAR
     */
    map(scene) {
      const markers = scene.markers || [
        { label: 'Centro de Operações', x: 50, y: 50, status: 'Ativo' },
        { label: 'Nó Primário', x: 75, y: 35, status: 'Conectado' },
        { label: 'Subestação Alpha', x: 28, y: 65, status: 'Standby' }
      ];

      return `
        <div class="glass-card-stark p-5 rounded-2xl w-full max-w-4xl mx-auto shadow-[0_0_35px_rgba(0,210,255,0.25)] border border-cyan-400/50 font-mono-code animate-slide-up">
          <div class="flex items-center justify-between pb-3 mb-3 border-b border-cyan-500/20">
            <div class="flex items-center space-x-2">
              <span class="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-ping"></span>
              <span class="text-xs font-bold text-white font-hud uppercase">${scene.title || 'COORDENADAS GEOPOLÍTICAS / MAPA TÁTICO'}</span>
            </div>
            <span class="text-[9px] text-cyan-300 bg-cyan-950/80 px-2 py-0.5 rounded border border-cyan-500/40">RADAR 3D ONLINE</span>
          </div>

          <!-- Palco Tático SVG -->
          <div class="relative w-full aspect-[21/9] rounded-xl overflow-hidden bg-slate-950 border border-cyan-500/40 flex items-center justify-center">
            <!-- Grid Matrix de Coordenadas -->
            <div class="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(0,240,255,0.15)_0,transparent_70%)]"></div>
            <div class="absolute inset-0 opacity-20 bg-[linear-gradient(to_right,#00f0ff_1px,transparent_1px),linear-gradient(to_bottom,#00f0ff_1px,transparent_1px)] bg-[size:40px_40px]"></div>

            <!-- Efeito de Radar Giratório -->
            <div class="absolute w-72 h-72 rounded-full border border-cyan-500/30 animate-spin" style="animation-duration: 8s;">
              <div class="w-1/2 h-1/2 bg-gradient-to-br from-cyan-400/25 to-transparent rounded-tl-full"></div>
            </div>

            <!-- Círculos concêntricos de alcance -->
            <div class="absolute w-48 h-48 rounded-full border border-cyan-500/20"></div>
            <div class="absolute w-24 h-24 rounded-full border border-cyan-500/30"></div>

            <!-- Marcadores no Mapa -->
            ${markers.map((m, idx) => `
              <div class="absolute -translate-x-1/2 -translate-y-1/2 group cursor-pointer" style="left: ${m.x}%; top: ${m.y}%;">
                <div class="relative flex items-center justify-center">
                  <span class="w-4 h-4 rounded-full bg-cyan-400/30 animate-ping absolute"></span>
                  <span class="w-2.5 h-2.5 rounded-full bg-cyan-400 border border-white shadow-[0_0_10px_#00f0ff]"></span>
                </div>
                <div class="absolute left-1/2 -translate-x-1/2 top-4 whitespace-nowrap bg-slate-950/90 border border-cyan-500/40 px-2 py-0.5 rounded text-[9px] text-cyan-200 pointer-events-none shadow">
                  ${m.label} <span class="text-emerald-400">(${m.status})</span>
                </div>
              </div>
            `).join('')}
          </div>

          ${scene.content ? `
            <div class="mt-3.5 p-3 rounded-xl bg-slate-950/60 border border-cyan-500/20 text-xs text-slate-200 font-sans leading-relaxed">
              ${scene.content}
            </div>
          ` : ''}
        </div>
      `;
    },

    /**
     * DIAGRAMA DE FLUXO / ARQUITETURA DE BLOCOS
     */
    diagram(scene) {
      const nodes = scene.nodes || [
        { id: '1', title: 'Entrada de Dados', desc: 'Sensores e Percepção', icon: '📥' },
        { id: '2', title: 'Processamento MiMo', desc: 'Raciocínio Profundo', icon: '🧠' },
        { id: '3', title: 'Ação e Síntese', desc: 'Execução e Projeção', icon: '⚡' }
      ];

      return `
        <div class="glass-card-stark p-5 rounded-2xl w-full max-w-4xl mx-auto shadow-[0_0_35px_rgba(0,210,255,0.25)] border border-cyan-400/50 font-mono-code animate-slide-up">
          <div class="flex items-center justify-between pb-3 mb-3 border-b border-cyan-500/20">
            <div class="flex items-center space-x-2">
              <span class="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-pulse"></span>
              <span class="text-xs font-bold text-white font-hud uppercase">${scene.title || 'DIAGRAMA DE ARQUITETURA / FLUXO'}</span>
            </div>
            <span class="text-[9px] text-cyan-300 bg-cyan-950/80 px-2 py-0.5 rounded border border-cyan-500/40">SISTEMA ATIVO</span>
          </div>

          <div class="flex flex-col md:flex-row items-center justify-between gap-3 p-4 rounded-xl bg-slate-950/70 border border-cyan-500/20">
            ${nodes.map((node, i) => `
              <div class="flex-1 w-full p-4 rounded-xl bg-slate-900/80 border border-cyan-500/30 hover:border-cyan-400 transition-all text-center relative group">
                <div class="text-2xl mb-1.5 filter drop-shadow-[0_0_8px_rgba(0,240,255,0.5)]">${node.icon || '📦'}</div>
                <h4 class="text-xs font-bold text-white font-hud">${node.title}</h4>
                <p class="text-[10px] text-slate-400 mt-1">${node.desc || ''}</p>
                <div class="absolute -top-2 -right-2 w-5 h-5 rounded-full bg-cyan-950 border border-cyan-400 text-[9px] font-bold text-cyan-300 flex items-center justify-center">
                  ${i + 1}
                </div>
              </div>
              ${i < nodes.length - 1 ? `
                <div class="flex items-center justify-center text-cyan-400 text-lg font-bold py-1 md:py-0">
                  <span class="hidden md:inline animate-pulse">➔</span>
                  <span class="inline md:hidden animate-pulse">⬇</span>
                </div>
              ` : ''}
            `).join('')}
          </div>

          ${scene.content ? `
            <div class="mt-3.5 p-3 rounded-xl bg-slate-950/60 border border-cyan-500/20 text-xs text-slate-200 font-sans leading-relaxed">
              ${scene.content}
            </div>
          ` : ''}
        </div>
      `;
    },

    /**
     * COMPARAÇÃO VISUAL A vs B
     */
    comparison(scene) {
      const itemA = scene.item_a || { title: 'Abordagem Alpha', points: ['Vantagem 1', 'Baixa Latência', 'Foco em Desempenho'] };
      const itemB = scene.item_b || { title: 'Abordagem Beta', points: ['Maior Resiliência', 'Custo Reduzido', 'Fácil Manutenção'] };

      return `
        <div class="glass-card-stark p-5 rounded-2xl w-full max-w-4xl mx-auto shadow-[0_0_35px_rgba(0,210,255,0.25)] border border-cyan-400/50 font-mono-code animate-slide-up">
          <div class="flex items-center justify-between pb-3 mb-4 border-b border-cyan-500/20">
            <div class="flex items-center space-x-2">
              <span class="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-pulse"></span>
              <span class="text-xs font-bold text-white font-hud uppercase">${scene.title || 'COMPARAÇÃO TÉCNICA ESTRUTURADA'}</span>
            </div>
            <span class="text-[9px] text-cyan-300 bg-cyan-950/80 px-2 py-0.5 rounded border border-cyan-500/40">SIDE-BY-SIDE</span>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <!-- Coluna A -->
            <div class="p-4 rounded-xl bg-slate-950/80 border border-sky-500/40 hover:border-sky-400 transition-colors">
              <div class="flex items-center justify-between pb-2 mb-3 border-b border-sky-500/20">
                <h4 class="text-xs font-bold text-sky-300 font-hud uppercase">${itemA.title}</h4>
                <span class="px-2 py-0.5 rounded bg-sky-950 border border-sky-500/30 text-[9px] text-sky-200">OPÇÃO A</span>
              </div>
              <ul class="space-y-2">
                ${(itemA.points || []).map(p => `
                  <li class="flex items-start space-x-2 text-xs text-slate-200">
                    <span class="text-sky-400 shrink-0">✔</span>
                    <span>${p}</span>
                  </li>
                `).join('')}
              </ul>
            </div>

            <!-- Coluna B -->
            <div class="p-4 rounded-xl bg-slate-950/80 border border-cyan-500/40 hover:border-cyan-400 transition-colors">
              <div class="flex items-center justify-between pb-2 mb-3 border-b border-cyan-500/20">
                <h4 class="text-xs font-bold text-cyan-300 font-hud uppercase">${itemB.title}</h4>
                <span class="px-2 py-0.5 rounded bg-cyan-950 border border-cyan-500/30 text-[9px] text-cyan-200">OPÇÃO B</span>
              </div>
              <ul class="space-y-2">
                ${(itemB.points || []).map(p => `
                  <li class="flex items-start space-x-2 text-xs text-slate-200">
                    <span class="text-cyan-400 shrink-0">✔</span>
                    <span>${p}</span>
                  </li>
                `).join('')}
              </ul>
            </div>
          </div>

          ${scene.conclusion ? `
            <div class="mt-4 p-3 rounded-xl bg-cyan-950/60 border border-cyan-500/30 text-xs text-cyan-100 flex items-start space-x-2.5">
              <span class="text-cyan-300 text-sm">💡</span>
              <div>
                <strong class="text-white">Parecer do J.A.R.V.I.S.:</strong> ${scene.conclusion}
              </div>
            </div>
          ` : ''}
        </div>
      `;
    },

    /**
     * GRADE DE MÉTRICAS & GAUGES COM CONTADOR ANIMADO
     */
    metric_grid(scene) {
      const metrics = scene.metrics || [
        { label: 'Eficiência de Resposta', value: '98.4', unit: '%', status: 'optimal' },
        { label: 'Carga de Processamento', value: '34', unit: '%', status: 'normal' },
        { label: 'Latência do Link', value: '18', unit: 'ms', status: 'optimal' },
        { label: 'Precisão Sintática', value: '99.8', unit: '%', status: 'optimal' }
      ];

      return `
        <div class="glass-card-stark p-5 rounded-2xl w-full max-w-4xl mx-auto shadow-[0_0_35px_rgba(0,210,255,0.25)] border border-cyan-400/50 font-mono-code animate-slide-up">
          <div class="flex items-center justify-between pb-3 mb-3 border-b border-cyan-500/20">
            <div class="flex items-center space-x-2">
              <span class="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-pulse"></span>
              <span class="text-xs font-bold text-white font-hud uppercase">${scene.title || 'PAINEL DE TELEMETRIA & INDICADORES'}</span>
            </div>
            <span class="text-[9px] text-cyan-300 bg-cyan-950/80 px-2 py-0.5 rounded border border-cyan-500/40">AMOSTRAGEM EM TEMPO REAL</span>
          </div>

          <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
            ${metrics.map(m => `
              <div class="p-3.5 rounded-xl bg-slate-950/80 border border-cyan-500/30 text-center relative overflow-hidden group hover:border-cyan-400 transition-all">
                <div class="text-[10px] text-slate-400 uppercase tracking-wider mb-1">${m.label}</div>
                <div class="text-2xl font-extrabold text-cyan-300 font-mono-code odometer-val" data-val="${m.value}" data-unit="${m.unit || ''}">
                  ${m.value}${m.unit || ''}
                </div>
                <div class="w-full bg-slate-900 h-1.5 rounded-full overflow-hidden mt-2">
                  <div class="h-full bg-gradient-to-r from-sky-500 to-cyan-300 rounded-full" style="width: ${Math.min(100, parseFloat(m.value) || 75)}%;"></div>
                </div>
              </div>
            `).join('')}
          </div>

          ${scene.content ? `
            <div class="mt-3.5 p-3 rounded-xl bg-slate-950/60 border border-cyan-500/20 text-xs text-slate-200 font-sans leading-relaxed">
              ${scene.content}
            </div>
          ` : ''}
        </div>
      `;
    },

    /**
     * CONCLUSÃO VISUAL CINEMATOGRÁFICA
     */

    /**
     * CANVAS INTELIGENTE // SPATIAL ARCHITECTURE & FREE-FORM EXPLANATION
     * Permite à IA combinar formas, circuitos, nós, chips, barramentos, textos e setas de fluxo dinâmicas.
     */
    /**
     * SPATIAL INTELLIGENCE & INTERACTIVE INFINITE CANVAS
     * Espaço visual livre de alta resolução (1600x900) para modelagem conceitual,
     * fluxos de dados em tempo real, freios e contrapesos e inteligência espacial.
     */
    smart_canvas(scene) {
      const w = scene.canvas_width || 1600;
      const h = scene.canvas_height || 900;
      const elements = scene.canvas_elements || scene.elements || [];
      const connections = scene.canvas_connections || scene.connections || [];

      // Mapeamento de nós por id para conexões curvas orgânicas
      const nodeMap = {};
      elements.forEach(el => {
        if (el.id) nodeMap[el.id] = el;
      });

      // Renderiza as Conexões Curvas com Partículas Dinâmicas Animadas
      const connSvg = connections.map((conn, cIdx) => {
        let x1 = conn.x1 || 100, y1 = conn.y1 || 100, x2 = conn.x2 || 400, y2 = conn.y2 || 400;

        if (conn.from && nodeMap[conn.from]) {
          const src = nodeMap[conn.from];
          x1 = (src.x || 100) + (src.width || 220) / 2;
          y1 = (src.y || 100) + (src.height || 110) / 2;
        }
        if (conn.to && nodeMap[conn.to]) {
          const dst = nodeMap[conn.to];
          x2 = (dst.x || 400) + (dst.width || 220) / 2;
          y2 = (dst.y || 400) + (dst.height || 110) / 2;
        }

        const color = conn.color || '#00f0ff';
        const label = conn.label || '';
        const speed = conn.speed || '2s';
        const isCurved = conn.curved !== false;

        // Ponto de curvatura orgânica suave
        const dx = x2 - x1;
        const dy = y2 - y1;
        const cx1 = x1 + dx * 0.4;
        const cy1 = y1 - 40;
        const cx2 = x1 + dx * 0.6;
        const cy2 = y2 + 40;

        const pathD = isCurved ? `M ${x1} ${y1} C ${cx1} ${cy1}, ${cx2} ${cy2}, ${x2} ${y2}` : `M ${x1} ${y1} L ${x2} ${y2}`;
        const midX = (x1 + x2) / 2;
        const midY = (y1 + y2) / 2;

        return `
          <g class="spatial-connection transition-opacity duration-300 hover:opacity-100" id="conn-${conn.id || cIdx}">
            <!-- Trilha Base Translúcida -->
            <path d="${pathD}" fill="none" stroke="${color}" stroke-opacity="0.25" stroke-width="3" />
            <!-- Partículas de Fluxo em Movimento Contínuo -->
            <path d="${pathD}" fill="none" stroke="${color}" stroke-width="4" stroke-dasharray="12 10" class="filter drop-shadow-[0_0_10px_${color}]">
              <animate attributeName="stroke-dashoffset" from="180" to="0" dur="${speed}" repeatCount="indefinite" />
            </path>
            <!-- Marcadores de Extremidade com Halo -->
            <circle cx="${x1}" cy="${y1}" r="4" fill="${color}" opacity="0.8" />
            <circle cx="${x2}" cy="${y2}" r="5" fill="${color}" class="filter drop-shadow-[0_0_8px_${color}]" />
            ${label ? `
              <g transform="translate(${midX}, ${midY})">
                <rect x="-${label.length * 4.5 + 8}" y="-13" width="${label.length * 9 + 16}" height="22" rx="6" fill="#020617" stroke="${color}" stroke-opacity="0.6" stroke-width="1.2" class="filter drop-shadow-[0_0_12px_rgba(0,0,0,0.8)]" />
                <text y="2" text-anchor="middle" fill="#ffffff" font-size="11" font-family="'JetBrains Mono', monospace" font-weight="bold" letter-spacing="0.5">${label}</text>
              </g>
            ` : ''}
          </g>
        `;
      }).join('');

      // Renderiza os Nós Espaciais Interativos
      const elemSvg = elements.map(el => {
        const x = el.x || 100;
        const y = el.y || 100;
        const width = el.width || 230;
        const height = el.height || 110;
        const shape = el.shape || 'box';
        const title = el.title || 'MÓDULO';
        const desc = el.desc || el.description || '';
        const color = el.color || '#00f0ff';
        const icon = el.icon || '⚡';
        const metric = el.metric || el.status || '';

        if (shape === 'reactor' || shape === 'circle') {
          // Nó Circular de Núcleo Soberano / Tribunal
          const r = Math.min(width, height) / 2;
          return `
            <g class="spatial-node cursor-pointer group" id="node-${el.id}" transform="translate(${x + r}, ${y + r})" onclick="JarvisPresentationEngine.focusCanvasNode('${el.id}')">
              <!-- Halo Radial Pulsante -->
              <circle r="${r + 14}" fill="none" stroke="${color}" stroke-opacity="0.2" stroke-dasharray="6 6" class="animate-spin" style="animation-duration: 20s;" />
              <circle r="${r}" fill="#050b14" stroke="${color}" stroke-width="2.5" class="filter drop-shadow-[0_0_20px_${color}] group-hover:scale-105 transition-transform" />
              <circle r="${r - 10}" fill="none" stroke="${color}" stroke-opacity="0.3" stroke-width="1.5" />
              <!-- Conteúdo Central -->
              <text y="-14" text-anchor="middle" font-size="24">${icon}</text>
              <text y="10" text-anchor="middle" fill="#ffffff" font-size="12" font-family="'Orbitron', sans-serif" font-weight="bold" letter-spacing="0.5">${title}</text>
              <text y="26" text-anchor="middle" fill="#94a3b8" font-size="10" font-family="'JetBrains Mono', monospace">${desc}</text>
              ${metric ? `<text y="${r - 8}" text-anchor="middle" fill="${color}" font-size="9" font-family="'JetBrains Mono', monospace" font-weight="bold">● ${metric}</text>` : ''}
            </g>
          `;
        } else if (shape === 'chip') {
          // Nó Institucional Executivo com Pinos de Transmissão
          return `
            <g class="spatial-node cursor-pointer group" id="node-${el.id}" transform="translate(${x}, ${y})" onclick="JarvisPresentationEngine.focusCanvasNode('${el.id}')">
              <!-- Pinos Eletrônicos Laterais -->
              <line x1="-12" y1="${height * 0.3}" x2="0" y2="${height * 0.3}" stroke="${color}" stroke-width="2.5" />
              <line x1="-12" y1="${height * 0.7}" x2="0" y2="${height * 0.7}" stroke="${color}" stroke-width="2.5" />
              <line x1="${width}" y1="${height * 0.3}" x2="${width + 12}" y2="${height * 0.3}" stroke="${color}" stroke-width="2.5" />
              <line x1="${width}" y1="${height * 0.7}" x2="${width + 12}" y2="${height * 0.7}" stroke="${color}" stroke-width="2.5" />
              <!-- Corpo Central do Módulo -->
              <rect width="${width}" height="${height}" rx="12" fill="#070e1b" stroke="${color}" stroke-width="2.2" class="filter drop-shadow-[0_0_22px_${color}] group-hover:stroke-white transition-all" />
              <rect x="6" y="6" width="${width - 12}" height="28" rx="8" fill="rgba(0,240,255,0.12)" />
              <text x="14" y="25" fill="${color}" font-size="12" font-family="'Orbitron', sans-serif" font-weight="bold">${icon} ${title}</text>
              <text x="14" y="56" fill="#e2e8f0" font-size="11" font-family="'JetBrains Mono', monospace">${desc}</text>
              ${metric ? `
                <rect x="14" y="${height - 28}" width="${width - 28}" height="18" rx="5" fill="#020617" stroke="${color}" stroke-opacity="0.4" />
                <text x="${width/2}" y="${height - 15}" text-anchor="middle" fill="#38bdf8" font-size="9" font-family="'JetBrains Mono', monospace" font-weight="bold">STATUS: ${metric}</text>
              ` : ''}
            </g>
          `;
        } else {
          // Nó Espacial Livre com Visual Minimalista Futurista
          return `
            <g class="spatial-node cursor-pointer group" id="node-${el.id}" transform="translate(${x}, ${y})" onclick="JarvisPresentationEngine.focusCanvasNode('${el.id}')">
              <rect width="${width}" height="${height}" rx="12" fill="#060c18" stroke="${color}" stroke-width="2" class="filter drop-shadow-[0_0_18px_${color}] group-hover:scale-[1.02] transition-transform" />
              <rect x="0" y="0" width="${width}" height="30" rx="12" fill="rgba(255,255,255,0.06)" />
              <text x="14" y="21" fill="#ffffff" font-size="12" font-family="'Orbitron', sans-serif" font-weight="bold">${icon} ${title}</text>
              <text x="14" y="55" fill="#cbd5e1" font-size="11" font-family="'JetBrains Mono', monospace">${desc}</text>
              ${metric ? `
                <text x="${width - 14}" y="${height - 14}" text-anchor="end" fill="${color}" font-size="10" font-family="'JetBrains Mono', monospace" font-weight="bold">${metric}</text>
              ` : ''}
            </g>
          `;
        }
      }).join('');

      return `
        <div class="w-full h-full relative overflow-hidden flex flex-col items-center justify-center select-none font-mono-code animate-fade-in">
          <!-- Palco SVG Interativo Pan/Zoom em Alta Resolução -->
          <svg id="interactive-spatial-canvas" viewBox="0 0 ${w} ${h}" class="w-full h-full max-h-[820px] transition-transform duration-300">
            <defs>
              <pattern id="spatialGrid" width="50" height="50" patternUnits="userSpaceOnUse">
                <circle cx="2" cy="2" r="1.2" fill="rgba(0,240,255,0.2)" />
                <path d="M 50 0 L 0 0 0 50" fill="none" stroke="rgba(0,240,255,0.04)" stroke-width="1" />
              </pattern>
            </defs>

            <!-- Fundo Cósmico de Coordenadas Livres -->
            <rect width="${w}" height="${h}" fill="url(#spatialGrid)" />

            <!-- Camada de Conexões e Fluxo de Poder -->
            <g id="canvas-connections-layer">${connSvg}</g>

            <!-- Camada de Nós e Entidades Institucionais -->
            <g id="canvas-elements-layer">${elemSvg}</g>
          </svg>

          <!-- Barra de Explicação Conceitual Flutuante no Rodapé -->
          <div class="absolute bottom-3 left-6 right-6 p-3 rounded-xl bg-slate-950/80 backdrop-blur-md border border-cyan-500/20 flex items-center justify-between pointer-events-auto">
            <div class="flex items-center space-x-3 text-xs text-slate-200">
              <span class="w-2 h-2 rounded-full bg-cyan-400 animate-ping"></span>
              <span class="font-bold text-white font-hud">${scene.title || 'ESPACE CONCEITUAL'}</span>
              <span class="text-slate-400">|</span>
              <span class="text-cyan-200/90 text-[11px]">${scene.content || 'Visualização dinâmica de equilíbrio institucional e fluxos operacionais.'}</span>
            </div>
            <div class="text-[10px] text-cyan-400/80 font-mono-code">
              MODO SPATIAL ACTIVO // CLIQUE NOS NÓS PARA DESTACAR
            </div>
          </div>
        </div>
      `;
    },

    canvas(scene) {
      return this.smart_canvas(scene);
    },

    focusCanvasNode(nodeId) {
      console.log('[PresentationEngine] Focando no nó:', nodeId);
      const el = document.getElementById(`node-${nodeId}`);
      if (el) {
        el.style.transform += ' scale(1.08)';
        setTimeout(() => {
          el.style.transform = el.style.transform.replace(' scale(1.08)', '');
        }, 500);
      }
    },

    conclusion(scene) {
      const actions = scene.actions || [
        { label: 'Salvar Relatório', action: 'save_report' },
        { label: 'Voltar ao Núcleo', action: 'close_presentation' }
      ];

      return `
        <div class="glass-card-stark p-6 rounded-2xl w-full max-w-3xl mx-auto shadow-[0_0_45px_rgba(0,210,255,0.35)] border border-cyan-400/70 font-mono-code text-center relative overflow-hidden animate-slide-up">
          <div class="w-12 h-12 mx-auto rounded-full bg-cyan-500/20 border border-cyan-400 flex items-center justify-center text-cyan-300 text-xl mb-3 shadow-[0_0_20px_rgba(0,240,255,0.6)]">
            ✨
          </div>

          <h3 class="text-sm font-bold text-white font-hud tracking-wide uppercase mb-2">
            ${scene.title || 'SÍNTESE EXECUTIVA // CONCLUSÃO'}
          </h3>

          <p class="text-xs text-slate-200 font-sans leading-relaxed max-w-xl mx-auto mb-5">
            ${scene.content || 'Apresentação concluída com sucesso. Todos os tópicos foram analisados e sintetizados.'}
          </p>

          ${scene.summary_points ? `
            <div class="p-3.5 rounded-xl bg-slate-950/70 border border-cyan-500/30 text-left space-y-2 mb-5 max-w-xl mx-auto">
              ${scene.summary_points.map(pt => `
                <div class="flex items-start space-x-2 text-xs text-slate-200">
                  <span class="text-cyan-400 font-bold shrink-0">●</span>
                  <span>${pt}</span>
                </div>
              `).join('')}
            </div>
          ` : ''}

          <div class="flex items-center justify-center space-x-3">
            ${actions.map(act => `
              <button onclick="JarvisPresentationEngine.triggerAction('${act.action}')" 
                      class="px-4 py-2 rounded-xl bg-cyan-950/90 hover:bg-cyan-900 border border-cyan-400 text-cyan-200 font-mono-code text-xs font-bold transition-all shadow-[0_0_15px_rgba(0,240,255,0.3)]">
                ${act.label}
              </button>
            `).join('')}
          </div>
        </div>
      `;
    }
  };

  // =========================================================================
  // 4. MOTOR PRINCIPAL DA APRESENTAÇÃO
  // =========================================================================
  const JarvisPresentationEngine = {

    /**
     * Inicia uma nova sessão de apresentação estruturada
     */
    start(script) {
      if (!script || !script.scenes || !script.scenes.length) {
        console.warn('[PresentationEngine] Roteiro inválido ou sem cenas.');
        return false;
      }

      _clearAllTrackedResources();

      state.activeSession = {
        id: script.id || 'pres_' + Date.now(),
        title: script.title || 'APRESENTAÇÃO DINÂMICA J.A.R.V.I.S.',
        scenes: script.scenes,
        speechSync: script.speech_sync !== false
      };
      state.currentSceneIndex = 0;
      state.isPlaying = true;

      this.openStage();
      this.renderCurrentScene();

      // Dispara evento DOM de início
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('jarvis:presentation_start', { detail: state.activeSession }));
      }
      return true;
    },

    /**
     * Abre a área de palco no HUD
     */
    openStage() {
      const overlay = document.getElementById('jarvis-presentation-overlay');
      if (overlay) {
        overlay.classList.remove('hidden');
        setTimeout(() => {
          overlay.classList.remove('opacity-0');
          overlay.classList.add('opacity-100');
        }, 30);
      }

      // Diminui o vortex para dar foco total à apresentação cinematográfica
      const vortex = document.getElementById('plasma-core') || document.getElementById('organicVortexCanvas') || document.querySelector('.vortex-container');
      if (vortex) {
        vortex.style.transition = 'opacity 0.6s ease';
        vortex.style.opacity = '0.15';
      }

      // Oculta cards concorrentes
      ['card-custom', 'card-news', 'jarvis-visual-stage'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.classList.add('hidden', 'opacity-0');
      });
    },

    /**
     * Renderiza a cena atual com morphing / transição suave
     */
    renderCurrentScene() {
      if (!state.activeSession) return;
      const scenes = state.activeSession.scenes;
      const idx = state.currentSceneIndex;
      const scene = scenes[idx];
      if (!scene) return;

      const mount = document.getElementById('presentation-content-area');
      const headerTitle = document.getElementById('presentation-header-title');
      const audioStatusText = document.getElementById('presentation-audio-status-text');

      if (headerTitle) {
        headerTitle.innerText = `${scene.title || 'CENA ' + (idx + 1)} (${idx + 1}/${scenes.length})`;
      }
      if (audioStatusText) {
        audioStatusText.innerText = `CENA ${idx + 1}/${scenes.length}`;
      }

      // Atualiza barra de timeline interativa
      this.updateTimelineUI();

      // Renderiza o componente adequado
      const compType = scene.component_type || scene.type || 'hologram_card';
      const renderer = renderers[compType] || renderers.hologram_card;
      const html = renderer(scene);

      if (mount) {
        mount.style.opacity = '0';
        mount.style.transform = 'scale(0.97)';
        mount.style.transition = 'all 0.35s cubic-bezier(0.16, 1, 0.3, 1)';

        setTimeout(() => {
          mount.innerHTML = html;
          mount.style.opacity = '1';
          mount.style.transform = 'scale(1)';

          // Inicializa contadores numéricos na cena renderizada
          mount.querySelectorAll('.odometer-val').forEach(el => {
            const val = el.getAttribute('data-val');
            const unit = el.getAttribute('data-unit') || '';
            _animateCounter(el, val, 1000, unit);
          });

          // Rastreia elementos de mídia inseridos para limpeza segura
          mount.querySelectorAll('video, audio').forEach(m => state.trackedMedia.add(m));
        }, 150);
      }

      // Se duração definida e em modo de reprodução automática, agenda próxima cena
      if (state.isPlaying && scene.duration_sec && scene.duration_sec > 0 && idx < scenes.length - 1) {
        if (state.timer) clearTimeout(state.timer);
        state.timer = setTimeout(() => {
          this.next();
        }, scene.duration_sec * 1000);
      }
    },

    /**
     * Atualiza os indicadores de bolinhas / timeline na barra de navegação
     */
    updateTimelineUI() {
      if (!state.activeSession) return;
      const scenes = state.activeSession.scenes;
      const current = state.currentSceneIndex;

      let timelineContainer = document.getElementById('presentation-timeline-dots');
      if (!timelineContainer) {
        const nav = document.getElementById('presentation-audio-controls');
        if (nav) {
          const div = document.createElement('div');
          div.id = 'presentation-timeline-dots';
          div.className = 'flex items-center space-x-1.5 mr-2';
          nav.insertBefore(div, nav.firstChild);
          timelineContainer = div;
        }
      }

      if (timelineContainer) {
        timelineContainer.innerHTML = scenes.map((s, i) => `
          <button onclick="JarvisPresentationEngine.jumpTo(${i})" 
                  title="Cena ${i + 1}: ${s.title || ''}" 
                  class="w-2.5 h-2.5 rounded-full transition-all cursor-pointer ${i === current ? 'bg-cyan-400 scale-125 shadow-[0_0_8px_#00f0ff]' : (i < current ? 'bg-cyan-600/70' : 'bg-slate-700/80 hover:bg-slate-500')}">
          </button>
        `).join('');
      }
    },

    /**
     * Avança para a próxima cena
     */
    next() {
      if (!state.activeSession) return;
      if (state.currentSceneIndex < state.activeSession.scenes.length - 1) {
        state.currentSceneIndex++;
        this.renderCurrentScene();
      } else {
        // Chegou ao fim da apresentação
        state.isPlaying = false;
        const icon = document.getElementById('pres-playpause-icon');
        const label = document.getElementById('pres-playpause-label');
        if (icon) icon.innerText = '▶';
        if (label) label.innerText = 'REVER';
      }
    },

    /**
     * Retorna para a cena anterior
     */
    prev() {
      if (!state.activeSession) return;
      if (state.currentSceneIndex > 0) {
        state.currentSceneIndex--;
        this.renderCurrentScene();
      }
    },

    /**
     * Pula diretamente para uma cena específica
     */
    jumpTo(index) {
      if (!state.activeSession) return;
      if (index >= 0 && index < state.activeSession.scenes.length) {
        state.currentSceneIndex = index;
        this.renderCurrentScene();
      }
    },

    /**
     * Alterna entre Pausar e Continuar
     */
    togglePlayPause() {
      state.isPlaying = !state.isPlaying;
      const icon = document.getElementById('pres-playpause-icon');
      const label = document.getElementById('pres-playpause-label');

      if (state.isPlaying) {
        if (icon) icon.innerText = '⏸';
        if (label) label.innerText = 'PAUSAR';
        this.renderCurrentScene();
      } else {
        if (icon) icon.innerText = '▶';
        if (label) label.innerText = 'CONTINUAR';
        if (state.timer) {
          clearTimeout(state.timer);
          state.timer = null;
        }
      }
    },

    /**
     * Fecha e limpa completamente a apresentação
     */
    close() {
      _clearAllTrackedResources();

      const overlay = document.getElementById('jarvis-presentation-overlay');
      if (overlay) {
        overlay.classList.remove('opacity-100');
        overlay.classList.add('opacity-0');
        setTimeout(() => {
          overlay.classList.add('hidden');
          const mount = document.getElementById('presentation-content-area');
          if (mount) mount.innerHTML = '';
        }, 300);
      }

      // Restaura o Reator Arc com opacidade normal
      const vortex = document.getElementById('plasma-core') || document.getElementById('organicVortexCanvas') || document.querySelector('.vortex-container');
      if (vortex) {
        vortex.style.opacity = '1';
      }

      state.activeSession = null;
      state.isPlaying = false;
      state.currentSceneIndex = 0;

      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('jarvis:presentation_close', {}));
      }
    },

    /**
     * Fallback gracioso para falha de mídia
     */
    handleMediaFallback(sceneId, fallbackImg) {
      console.warn(`[PresentationEngine] Vídeo da cena ${sceneId} falhou. Ativando fallback.`);
      const container = document.getElementById(`pres-video-container-${sceneId}`);
      const fallbackBox = document.getElementById(`pres-fallback-container-${sceneId}`);
      const videoEl = document.getElementById(`pres-video-player-${sceneId}`);

      if (videoEl) {
        try { videoEl.pause(); } catch(e){}
        videoEl.classList.add('hidden');
      }
      if (fallbackBox) {
        fallbackBox.classList.remove('hidden');
        fallbackBox.classList.add('flex');
      }
    },

    /**
     * Dispara ações de botões interativos
     */
    triggerAction(action) {
      console.log(`[PresentationEngine] Ação acionada: ${action}`);
      if (action === 'close_presentation') {
        this.close();
      } else if (action === 'save_report') {
        if (window.showJarvisToast) window.showJarvisToast('💾 Relatório da Apresentação Salvo no Histórico.');
      }
      if (typeof window !== 'undefined') {
        const sendFn = window.sendToJarvisCore || window.sendToOpenClaw;
        if (typeof sendFn === 'function') {
          sendFn(`[AÇÃO APRESENTAÇÃO] ${action}`);
        }
      }
    },

    isOpen() {
      const el = document.getElementById('jarvis-presentation-overlay');
      return el && !el.classList.contains('hidden');
    }
  };

  // =========================================================================
  // 5. ATALHOS GLOBAIS DE TECLADO (ESC, SETAS, ESPAÇO)
  // =========================================================================
  if (typeof window !== 'undefined') {
    window.addEventListener('keydown', (e) => {
      if (!JarvisPresentationEngine.isOpen()) return;

      if (e.key === 'Escape') {
        e.preventDefault();
        JarvisPresentationEngine.close();
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        JarvisPresentationEngine.next();
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        JarvisPresentationEngine.prev();
      } else if (e.key === ' ' && e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
        e.preventDefault();
        JarvisPresentationEngine.togglePlayPause();
      }
    });

    // Torna acessível globalmente
    window.JarvisPresentationEngine = JarvisPresentationEngine;
  }

  return JarvisPresentationEngine;
}));
