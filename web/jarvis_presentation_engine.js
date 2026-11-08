/**
 * J.A.R.V.I.S. SPATIAL INTELLIGENCE & PRESENTATION ENGINE
 * ============================================================================
 * Ambiente Espacial de Apresentação e Visualização Contínua em Tempo Real.
 * Suporta:
 *  - Spatial Mode (Padrão): Workspace persistente com componentes independentes
 *    (Apache ECharts, Diagramas, Hero Cards, Indicadores, Canvas Inteligente).
 *  - Slide Mode (Opcional): Apresentação convencional sequencial para compatibilidade.
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
  // 1. ESTADO GLOBAL DO SPATIAL WORKSPACE E APRESENTAÇÃO
  // =========================================================================
  const spatialState = {
    workspace: null,               // Dados do workspace ativo
    activeMode: 'spatial',         // 'spatial' ou 'slide'
    components: new Map(),         // Map<component_id, { data, dom, chartInstance }>
    slideSession: null,            // Sessão do modo slide (se ativo)
    slideIndex: 0,
    isPlaying: false,
    timer: null,
    trackedMedia: new Set(),
    trackedTimers: new Set()
  };

  // =========================================================================
  // 2. UTILITÁRIOS E CONTADORES ANIMADOS (ODÔMETRO)
  // =========================================================================
  function _animateCounter(el, targetVal, duration = 1000, unit = '') {
    if (!el) return;
    const cleanStr = String(targetVal).replace(/[^0-9.-]/g, '');
    const isNum = !isNaN(parseFloat(cleanStr)) && cleanStr !== '';
    if (!isNum) {
      el.innerText = targetVal + (unit ? ' ' + unit : '');
      return;
    }
    const target = parseFloat(cleanStr);
    const start = 0;
    const startTime = performance.now();
    const isFloat = String(targetVal).includes('.');

    function update(now) {
      const elapsed = now - startTime;
      const progress = Math.min(1, elapsed / duration);
      const ease = 1 - Math.pow(1 - progress, 3);
      const current = start + (target - start) * ease;
      el.innerText = (isFloat ? current.toFixed(1) : Math.round(current)) + (unit ? ' ' + unit : '');
      if (progress < 1) {
        requestAnimationFrame(update);
      } else {
        el.innerText = target + (unit ? ' ' + unit : '');
      }
    }
    requestAnimationFrame(update);
  }

  // =========================================================================
  // 3. RENDERIZADORES INDEPENDENTES DE COMPONENTES ESPACIAIS
  // =========================================================================
  const ComponentBuilders = {

    /**
     * COMPONENTE 1: APACHE ECHARTS (GRÁFICO PROFISSIONAL INTERATIVO)
     */
    echarts(comp) {
      const p = comp.props || {};
      const chartId = `echart-${comp.id}`;
      const title = p.title || 'Análise de Dados';
      const subtitle = p.subtitle || '';
      const height = p.height || 360;

      const html = `
        <div class="w-full h-full p-5 rounded-3xl bg-slate-950/85 backdrop-blur-xl border border-slate-800/80 hover:border-slate-700 transition-all flex flex-col shadow-2xl relative overflow-hidden group">
          <div class="flex items-center justify-between pb-3 mb-2 border-b border-slate-800/70">
            <div>
              <div class="flex items-center space-x-2">
                <span class="w-2 h-2 rounded-full bg-cyan-400 animate-ping"></span>
                <span class="text-xs font-bold text-white font-hud uppercase tracking-wider">${title}</span>
              </div>
              ${subtitle ? `<p class="text-[11px] text-slate-400 mt-0.5">${subtitle}</p>` : ''}
            </div>
            <span class="text-[9px] font-mono-code text-cyan-400 bg-cyan-950/80 px-2.5 py-0.5 rounded-full border border-cyan-500/30">ECHARTS // INTERATIVO</span>
          </div>
          <div id="${chartId}" class="w-full flex-1" style="min-height: ${height}px;"></div>
        </div>
      `;

      return {
        html,
        mount(container) {
          const dom = container.querySelector(`#${chartId}`);
          if (!dom || typeof window.echarts === 'undefined') return null;

          const chart = window.echarts.init(dom, 'dark', { renderer: 'canvas' });

          // Paleta Cyberpunk Stark de Alto Padrão
          const defaultOptions = {
            backgroundColor: 'transparent',
            textStyle: { fontFamily: "'Plus Jakarta Sans', sans-serif" },
            tooltip: {
              trigger: 'axis',
              backgroundColor: 'rgba(2, 6, 23, 0.95)',
              borderColor: 'rgba(0, 240, 255, 0.3)',
              textStyle: { color: '#e2e8f0', fontSize: 11 },
              extraCssText: 'box-shadow: 0 10px 25px rgba(0,0,0,0.5); border-radius: 12px;'
            },
            grid: { top: 35, right: 25, bottom: 30, left: 45, containLabel: true }
          };

          const mergedOptions = Object.assign({}, defaultOptions, p.options || {});
          chart.setOption(mergedOptions);

          const resizeHandler = () => chart.resize();
          window.addEventListener('resize', resizeHandler);

          return {
            instance: chart,
            cleanup() {
              window.removeEventListener('resize', resizeHandler);
              chart.dispose();
            }
          };
        }
      };
    },

    /**
     * COMPONENTE 2: HERO EDITORIAL (ANÁLISE ESTRATÉGICA & CONTEXTO)
     */
    hero_card(comp) {
      const p = comp.props || {};
      const title = p.title || 'Visão Institucional';
      const subtitle = p.subtitle || '';
      const content = p.content || '';
      const tag = p.tag || 'DIRETRIZ DE INTELIGÊNCIA';
      const bullets = (p.bullets || []).map(b => `
        <div class="flex items-start space-x-3 p-3 rounded-xl bg-slate-900/40 border border-slate-800/80">
          <div class="w-2 h-2 rounded-full bg-cyan-400 mt-1.5 shrink-0 shadow-[0_0_8px_#00f0ff]"></div>
          <div class="text-xs text-slate-200 leading-relaxed font-sans">${b}</div>
        </div>
      `).join('');

      const html = `
        <div class="w-full h-full p-6 rounded-3xl bg-slate-950/85 backdrop-blur-xl border border-slate-800/80 hover:border-slate-700 transition-all flex flex-col justify-between shadow-2xl relative overflow-hidden">
          <div class="space-y-4">
            <div class="flex items-center space-x-2">
              <span class="w-2 h-2 rounded-full bg-cyan-400 animate-ping"></span>
              <span class="text-[10px] font-mono-code font-bold uppercase tracking-widest text-cyan-400 bg-cyan-950/60 px-2.5 py-0.5 rounded border border-cyan-500/30">${tag}</span>
            </div>
            <h2 class="text-xl lg:text-3xl font-extrabold text-white font-hud tracking-tight leading-snug">${title}</h2>
            ${subtitle ? `<p class="text-xs font-medium text-cyan-200/80 leading-relaxed">${subtitle}</p>` : ''}
            ${content ? `<div class="p-4 rounded-2xl bg-slate-900/50 border border-slate-800/80 text-xs text-slate-300 leading-relaxed">${content}</div>` : ''}
            ${bullets ? `<div class="space-y-2 pt-1">${bullets}</div>` : ''}
          </div>
          ${p.footer ? `<div class="pt-4 mt-4 border-t border-slate-800 text-[10px] font-mono-code text-slate-500">${p.footer}</div>` : ''}
        </div>
      `;

      return { html, mount: () => null };
    },

    /**
     * COMPONENTE 3: METRIC DOCK (KPIS & INDICADORES NUMÉRICOS GIGANTES)
     */
    metric_dock(comp) {
      const p = comp.props || {};
      const metrics = p.metrics || [];

      const html = `
        <div class="w-full h-full p-6 rounded-3xl bg-slate-950/85 backdrop-blur-xl border border-slate-800/80 hover:border-slate-700 transition-all flex flex-col justify-between shadow-2xl">
          <div class="flex items-center justify-between pb-3 mb-4 border-b border-slate-800/80">
            <span class="text-xs font-bold font-hud uppercase tracking-wider text-white">${p.title || 'INDICADORES PRINCIPAIS'}</span>
            <span class="text-[9px] font-mono-code text-cyan-400 bg-cyan-950 px-2 py-0.5 rounded border border-cyan-500/30">TELEMETRIA VIVA</span>
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-${Math.min(metrics.length, 3)} gap-4 flex-1 items-center">
            ${metrics.map(m => `
              <div class="p-5 rounded-2xl bg-gradient-to-br from-slate-900/90 to-slate-950/90 border border-slate-800 hover:border-cyan-500/40 transition-all relative overflow-hidden group text-center">
                <div class="text-[10px] font-mono-code uppercase tracking-widest text-slate-400 mb-1.5">${m.label}</div>
                <div class="text-3xl lg:text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-white via-cyan-100 to-cyan-400 font-hud odometer-val" data-val="${m.value}" data-unit="${m.unit || ''}">
                  ${m.value}${m.unit || ''}
                </div>
                ${m.sub ? `<div class="text-[11px] text-cyan-300/80 font-sans mt-2">${m.sub}</div>` : ''}
              </div>
            `).join('')}
          </div>
        </div>
      `;

      return {
        html,
        mount(container) {
          container.querySelectorAll('.odometer-val').forEach(el => {
            _animateCounter(el, el.getAttribute('data-val'), 900, el.getAttribute('data-unit') || '');
          });
          return null;
        }
      };
    },

    /**
     * COMPONENTE 4: DIAGRAMA ESTRUTURADO NOBRE (TRÊS PODERES / ARQUITETURA)
     */
    power_triptych(comp) {
      const p = comp.props || {};
      const pillars = p.pillars || [
        { title: 'PODER EXECUTIVO', subtitle: 'Palácio do Planalto', desc: 'Coordenação e gestão das políticas públicas', icon: '🏛️', color: 'cyan', badge: 'Medidas Provisórias' },
        { title: 'PODER LEGISLATIVO', subtitle: 'Congresso Nacional', desc: '513 Deputados e 81 Senadores com protagonismo orçamentário', icon: '⚖️', color: 'amber', badge: 'Orçamento Impositivo' },
        { title: 'PODER JUDICIÁRIO', subtitle: 'Supremo Tribunal Federal', desc: '11 Ministros como guardiões da Carta Magna de 1988', icon: '🛡️', color: 'purple', badge: 'Controle Constitucional' }
      ];

      const html = `
        <div class="w-full h-full p-6 rounded-3xl bg-slate-950/85 backdrop-blur-xl border border-slate-800/80 hover:border-slate-700 transition-all flex flex-col justify-between shadow-2xl">
          <div class="flex items-center justify-between pb-3 mb-4 border-b border-slate-800">
            <div>
              <span class="text-[10px] font-mono-code font-bold uppercase tracking-widest text-cyan-400">ARQUITETURA INSTITUCIONAL // FREIOS & CONTRAPESOS</span>
              <h3 class="text-xl font-bold text-white font-hud mt-0.5">${p.title || 'Equilíbrio dos Três Poderes da República'}</h3>
            </div>
            <span class="text-[9px] font-mono-code text-cyan-400 bg-cyan-950 px-2 py-0.5 rounded border border-cyan-500/30">INTERATIVO</span>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-3 gap-5 flex-1 items-stretch">
            ${pillars.map(pil => {
              const theme = pil.color === 'amber' ? { border: 'border-amber-500/40', text: 'text-amber-400', glow: 'from-amber-950/30' }
                          : pil.color === 'purple' ? { border: 'border-purple-500/40', text: 'text-purple-400', glow: 'from-purple-950/30' }
                          : { border: 'border-cyan-500/40', text: 'text-cyan-400', glow: 'from-cyan-950/30' };

              return `
                <div class="p-5 rounded-2xl bg-gradient-to-b ${theme.glow} via-slate-950/90 to-slate-950/90 border ${theme.border} hover:border-white/50 transition-all flex flex-col justify-between shadow-lg group">
                  <div>
                    <div class="text-2xl mb-3">${pil.icon}</div>
                    <div class="text-[10px] font-mono-code font-bold uppercase tracking-wider ${theme.text}">${pil.title}</div>
                    <h4 class="text-base font-bold text-white font-hud mt-0.5 mb-2">${pil.subtitle}</h4>
                    <p class="text-xs text-slate-300 leading-relaxed font-sans">${pil.desc}</p>
                  </div>
                  <div class="pt-3 mt-4 border-t border-slate-800/80">
                    <span class="px-2 py-1 rounded bg-slate-900 text-[10px] font-mono-code font-semibold ${theme.text} border border-slate-700/60">${pil.badge}</span>
                  </div>
                </div>
              `;
            }).join('')}
          </div>

          ${p.footer ? `
            <div class="mt-4 p-3 rounded-xl bg-slate-900/60 border border-slate-800 text-xs text-slate-300 font-sans">
              ${p.footer}
            </div>
          ` : ''}
        </div>
      `;

      return { html, mount: () => null };
    },

    /**
     * COMPONENTE 5: TABELA MATRICIAL DE ALTO PADRÃO (PAUTAS & RISCOS)
     */
    data_table(comp) {
      const p = comp.props || {};
      const headers = p.headers || ['Item', 'Origem', 'Impacto', 'Status'];
      const rows = p.rows || [];

      const html = `
        <div class="w-full h-full p-6 rounded-3xl bg-slate-950/85 backdrop-blur-xl border border-slate-800/80 hover:border-slate-700 transition-all flex flex-col justify-between shadow-2xl">
          <div class="flex items-center justify-between pb-3 mb-3 border-b border-slate-800">
            <div>
              <span class="text-[10px] font-mono-code font-bold uppercase tracking-widest text-cyan-400">MATRIZ ESTRATÉGICA</span>
              <h3 class="text-xl font-bold text-white font-hud mt-0.5">${p.title || 'Pautas e Indicadores em Foco'}</h3>
            </div>
            <span class="text-[9px] font-mono-code text-cyan-400 bg-cyan-950 px-2 py-0.5 rounded border border-cyan-500/30">${rows.length} ITENS</span>
          </div>

          <div class="overflow-x-auto rounded-2xl border border-slate-800 flex-1">
            <table class="w-full text-left text-xs text-slate-200">
              <thead class="bg-slate-900/90 border-b border-slate-800 text-slate-400 font-mono-code text-[10px] uppercase tracking-wider">
                <tr>
                  ${headers.map(h => `<th class="py-3 px-5">${h}</th>`).join('')}
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-800/60 font-sans">
                ${rows.map(r => `
                  <tr class="hover:bg-slate-900/40 transition-colors">
                    ${r.map((col, idx) => {
                      let colStr = String(col);
                      let badge = '';
                      if (colStr.toLowerCase() === 'ativo' || colStr.toLowerCase() === 'online') {
                        badge = `<span class="px-2.5 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-[10px] font-mono-code font-bold">● ${colStr}</span>`;
                      } else if (colStr.toLowerCase() === 'alerta' || colStr.toLowerCase() === 'aviso') {
                        badge = `<span class="px-2.5 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/30 text-amber-300 text-[10px] font-mono-code font-bold">▲ ${colStr}</span>`;
                      }
                      return `<td class="py-3 px-5 ${idx === 0 ? 'font-bold text-white font-hud' : 'text-slate-300'}">${badge || colStr}</td>`;
                    }).join('')}
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        </div>
      `;

      return { html, mount: () => null };
    }
  };

  // =========================================================================
  // 4. MOTOR DO SPATIAL INTELLIGENCE WORKSPACE
  // =========================================================================
  const JarvisPresentationEngine = {

    /**
     * Inicializa ou atualiza o Spatial Workspace
     */
    initSpatialWorkspace(wsData) {
      spatialState.activeMode = 'spatial';
      spatialState.workspace = wsData || { title: 'Spatial Hub', components: {} };

      const overlay = document.getElementById('jarvis-presentation-overlay');
      const mount = document.getElementById('presentation-content-area');
      const headerTitle = document.getElementById('presentation-header-title');
      const audioStatusText = document.getElementById('presentation-audio-status-text');

      if (overlay) {
        overlay.classList.remove('hidden');
        setTimeout(() => {
          overlay.classList.remove('opacity-0');
          overlay.classList.add('opacity-100');
        }, 30);
      }

      if (headerTitle) {
        headerTitle.innerText = wsData.title || 'SPATIAL INTELLIGENCE WORKSPACE';
      }
      if (audioStatusText) {
        audioStatusText.innerText = 'WORKSPACE ATIVO';
      }

      if (mount) {
        mount.innerHTML = `
          <div id="spatial-workspace-grid" class="w-full h-full grid grid-cols-12 gap-6 p-2 overflow-y-auto"></div>
        `;
      }

      // Se houver componentes iniciais, monta-os
      spatialState.components.clear();
      const comps = wsData.components || {};
      Object.keys(comps).forEach(k => {
        this.addSpatialComponent(comps[k]);
      });

      return true;
    },

    /**
     * Adiciona um componente individual ao Spatial Workspace
     */
    addSpatialComponent(compData) {
      if (!compData || !compData.id) return false;
      const grid = document.getElementById('spatial-workspace-grid');
      if (!grid) {
        this.initSpatialWorkspace({ title: 'Spatial Hub', components: {} });
      }

      const gridEl = document.getElementById('spatial-workspace-grid');
      if (!gridEl) return false;

      // Determina span de colunas no grid de 12 colunas
      const colSpan = (compData.position && compData.position.col_span) ? compData.position.col_span : 6;
      const builder = ComponentBuilders[compData.type] || ComponentBuilders.hero_card;
      const { html, mount } = builder(compData);

      // Cria nó wrapper
      const compWrap = document.createElement('div');
      compWrap.id = `spatial-comp-${compData.id}`;
      compWrap.className = `col-span-12 lg:col-span-${colSpan} transition-all duration-500 transform animate-fade-in`;
      compWrap.innerHTML = html;

      gridEl.appendChild(compWrap);

      // Executa mount (ex: inicialização do Apache ECharts)
      let mountResult = null;
      if (typeof mount === 'function') {
        mountResult = mount(compWrap);
      }

      spatialState.components.set(compData.id, {
        data: compData,
        dom: compWrap,
        mountResult
      });

      return true;
    },

    /**
     * Atualiza um componente específico sem reconstruir o Workspace
     */
    updateSpatialComponent(compId, updates, animate = true) {
      const comp = spatialState.components.get(compId);
      if (!comp) return false;

      // Se for ECharts e updates tiver opções, atualiza com setOption suave
      if (comp.data.type === 'echarts' && comp.mountResult && comp.mountResult.instance) {
        if (updates.props && updates.props.options) {
          comp.mountResult.instance.setOption(updates.props.options, { notMerge: false, lazyUpdate: true });
        }
      }

      // Se for metric_dock, atualiza contadores
      if (comp.data.type === 'metric_dock' && updates.props && updates.props.metrics) {
        const wrap = comp.dom;
        updates.props.metrics.forEach(m => {
          const el = wrap.querySelector(`[data-val="${m.value}"]`);
          if (el) _animateCounter(el, m.value, 800, m.unit || '');
        });
      }

      return true;
    },

    /**
     * Aplica aura luminosa temporária a um componente para sincronização de narração
     */
    highlightSpatialComponent(compId, duration = 3.0) {
      const comp = spatialState.components.get(compId);
      if (!comp || !comp.dom) return false;

      comp.dom.classList.add('ring-2', 'ring-cyan-400', 'shadow-[0_0_40px_rgba(0,240,255,0.4)]', 'scale-[1.01]');
      setTimeout(() => {
        comp.dom.classList.remove('ring-2', 'ring-cyan-400', 'shadow-[0_0_40px_rgba(0,240,255,0.4)]', 'scale-[1.01]');
      }, duration * 1000);
      return true;
    },

    /**
     * Remove um componente individual mantendo os demais intactos
     */
    removeSpatialComponent(compId) {
      const comp = spatialState.components.get(compId);
      if (!comp) return false;

      if (comp.mountResult && typeof comp.mountResult.cleanup === 'function') {
        comp.mountResult.cleanup();
      }

      if (comp.dom && comp.dom.parentNode) {
        comp.dom.style.opacity = '0';
        comp.dom.style.transform = 'scale(0.95)';
        setTimeout(() => {
          if (comp.dom.parentNode) comp.dom.parentNode.removeChild(comp.dom);
        }, 300);
      }

      spatialState.components.delete(compId);
      return true;
    },

    /**
     * Limpa o Workspace inteiro
     */
    clearSpatialWorkspace() {
      spatialState.components.forEach(comp => {
        if (comp.mountResult && typeof comp.mountResult.cleanup === 'function') {
          comp.mountResult.cleanup();
        }
      });
      spatialState.components.clear();

      const overlay = document.getElementById('jarvis-presentation-overlay');
      if (overlay) {
        overlay.classList.remove('opacity-100');
        overlay.classList.add('opacity-0');
        setTimeout(() => overlay.classList.add('hidden'), 250);
      }
    },

    // =========================================================================
    // 5. MODO SLIDE CONVENCIONAL (COMPATIBILIDADE QUANDO SOLICITADO)
    // =========================================================================
    start(script) {
      // Se for script estruturado para Spatial Workspace, direciona para o modo espacial
      if (script.mode === 'spatial' || script.spatial) {
        return this.initSpatialWorkspace(script);
      }

      // Caso contrário, executa modo Slide convencional de compatibilidade
      spatialState.activeMode = 'slide';
      spatialState.slideSession = script;
      spatialState.slideIndex = 0;
      spatialState.isPlaying = true;

      const overlay = document.getElementById('jarvis-presentation-overlay');
      if (overlay) {
        overlay.classList.remove('hidden');
        setTimeout(() => {
          overlay.classList.remove('opacity-0');
          overlay.classList.add('opacity-100');
        }, 30);
      }

      this.renderSlideScene();
      return true;
    },

    renderSlideScene() {
      if (!spatialState.slideSession) return;
      const scenes = spatialState.slideSession.scenes || [];
      const idx = spatialState.slideIndex;
      const scene = scenes[idx];
      if (!scene) return;

      const mount = document.getElementById('presentation-content-area');
      const headerTitle = document.getElementById('presentation-header-title');
      const audioStatusText = document.getElementById('presentation-audio-status-text');

      if (headerTitle) headerTitle.innerText = `${spatialState.slideSession.title} — ${scene.title || 'SLIDE ' + (idx + 1)}`;
      if (audioStatusText) audioStatusText.innerText = `SLIDE ${idx + 1}/${scenes.length}`;

      const builder = ComponentBuilders[scene.component_type] || ComponentBuilders.hero_card;
      const { html, mount: fnMount } = builder({ id: scene.scene_id || idx, props: scene });

      if (mount) {
        mount.innerHTML = `<div class="w-full h-full p-2 flex items-center justify-center">${html}</div>`;
        if (typeof fnMount === 'function') fnMount(mount);
      }
    },

    next() {
      if (spatialState.activeMode === 'slide' && spatialState.slideSession) {
        if (spatialState.slideIndex < spatialState.slideSession.scenes.length - 1) {
          spatialState.slideIndex++;
          this.renderSlideScene();
        }
      }
    },

    prev() {
      if (spatialState.activeMode === 'slide' && spatialState.slideSession) {
        if (spatialState.slideIndex > 0) {
          spatialState.slideIndex--;
          this.renderSlideScene();
        }
      }
    },

    jumpTo(index) {
      if (spatialState.activeMode === 'slide' && spatialState.slideSession) {
        if (index >= 0 && index < spatialState.slideSession.scenes.length) {
          spatialState.slideIndex = index;
          this.renderSlideScene();
        }
      }
    },

    togglePlayPause() {
      spatialState.isPlaying = !spatialState.isPlaying;
      const label = document.getElementById('pres-playpause-label');
      if (label) label.innerText = spatialState.isPlaying ? 'PAUSAR' : 'CONTINUAR';
    },

    close() {
      this.clearSpatialWorkspace();
    },

    triggerAction(action) {
      if (action === 'close_presentation') this.close();
      else if (action === 'save_report' && window.showJarvisToast) {
        window.showJarvisToast('💾 Relatório Espacial Salvo.');
      }
    },

    isOpen() {
      const el = document.getElementById('jarvis-presentation-overlay');
      return el && !el.classList.contains('hidden');
    }
  };

  if (typeof window !== 'undefined') {
    window.addEventListener('keydown', (e) => {
      if (!JarvisPresentationEngine.isOpen()) return;
      if (e.key === 'Escape') JarvisPresentationEngine.close();
      else if (e.key === 'ArrowRight') JarvisPresentationEngine.next();
      else if (e.key === 'ArrowLeft') JarvisPresentationEngine.prev();
    });
    window.JarvisPresentationEngine = JarvisPresentationEngine;
  }

  return JarvisPresentationEngine;
}));
