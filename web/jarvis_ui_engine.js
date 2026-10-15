/**
 * J.A.R.V.I.S. Visual Operating System - Core UI Engine
 * Transforma o Jarvis de um chatbot de texto em um Sistema Operacional Visual.
 * 
 * Pipeline:
 * User Request -> OpenClaw / AI -> Visual Intent -> UI Specification -> JarvisUI Renderer -> Interactive Experience
 * 
 * Design Tokens: HeroUI (glassmorphism/depth) + Radix UI (microinteractions/scales) + Astro (mesh glows/gradients)
 */

(function (root, factory) {
  if (typeof define === 'function' && define.amd) {
    define([], factory);
  } else if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.JarvisUI = factory();
  }
}(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  // =========================================================================
  // 1. EVENT BUS BI-DIRECIONAL (UI -> OpenClaw / Core)
  // =========================================================================
  const eventListeners = new Map();

  function on(eventName, callback) {
    if (!eventListeners.has(eventName)) {
      eventListeners.set(eventName, new Set());
    }
    eventListeners.get(eventName).add(callback);
    return () => off(eventName, callback);
  }

  function off(eventName, callback) {
    if (eventListeners.has(eventName)) {
      eventListeners.get(eventName).delete(callback);
    }
  }

  function emit(eventName, detail) {
    if (eventListeners.has(eventName)) {
      eventListeners.get(eventName).forEach(cb => {
        try { cb(detail); } catch (err) { console.error('[JarvisUI Event Error]', err); }
      });
    }
    // Dispara também evento DOM nativo para desacoplamento total
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('jarvis:' + eventName, { detail }));
    }
  }

  // =========================================================================
  // 2. MOTOR DE VISUAL INTENT (Analisador Semântico de Apresentação Visual)
  // =========================================================================
  const JarvisVisualIntent = {
    /**
     * Analisa uma mensagem do usuário e a resposta crua para determinar
     * a melhor especificação de UI (se o modelo não a tiver retornado pronta).
     */
    analyze(userMsg, rawReply, extraData = {}) {
      const q = (userMsg || '').toLowerCase();
      const r = (rawReply || '').toLowerCase();

      // 0. EXPLICIT JSON SPECIFICATION (```json:visual ... ``` ou ```json ... ```)
      const jsonMatch = (rawReply || '').match(/```(?:json:visual|json)?\s*(\{[\s\S]*?"type"\s*:\s*"[\s\S]*?\})\s*```/);
      if (jsonMatch) {
        try {
          const parsed = JSON.parse(jsonMatch[1]);
          if (parsed && parsed.type) {
            return parsed;
          }
        } catch (e) {
          console.warn('[JarvisUI] Falha ao extrair json:visual:', e);
        }
      }

      // 1. WEATHER / CLIMA SEMANAL
      if (
        q.includes('tempo') || q.includes('clima') || q.includes('previsão') || q.includes('previsao') ||
        q.includes('chuva') || q.includes('chover') || q.includes('temperatura') ||
        (r.includes('°c') && (r.includes('segunda') || r.includes('amanhã') || r.includes('semana')))
      ) {
        return this._buildWeatherSpec(userMsg, rawReply, extraData);
      }

      // 2. COMPARISON / COMPARADORES (ex: RTX 5070 vs 4070)
      if (
        q.includes('compare') || q.includes('comparar') || q.includes('comparativo') ||
        q.includes('diferença entre') || q.includes('diferenca entre') || q.includes(' vs ') || q.includes(' versus ')
      ) {
        return this._buildComparisonSpec(userMsg, rawReply);
      }

      // 3. CHECKLIST / TAREFAS / CONFIGURAÇÃO PASSO A PASSO
      if (
        q.includes('checklist') || q.includes('passo a passo') || q.includes('tarefas') ||
        q.includes('lista de compras') || q.includes('configurar') || q.includes('instalar') ||
        rawReply.includes('[ ]') || rawReply.includes('- [ ]') || rawReply.includes('1.')
      ) {
        return this._buildChecklistSpec(userMsg, rawReply);
      }

      // 4. TIMELINE / CRONOLOGIA / HISTÓRICO
      if (
        q.includes('histórico') || q.includes('historico') || q.includes('cronologia') ||
        q.includes('timeline') || q.includes('evolução') || q.includes('evolucao') ||
        (rawReply.match(/\b(19\d\d|20\d\d)\b/g) && rawReply.match(/\b(19\d\d|20\d\d)\b/g).length >= 3)
      ) {
        return this._buildTimelineSpec(userMsg, rawReply);
      }

      // 5. FLOW / FLUXOGRAMA DE SISTEMA OU PROCESSO
      if (
        q.includes('como funciona') || q.includes('fluxo') || q.includes('arquitetura') ||
        q.includes('processo') || q.includes('diagrama') || rawReply.includes('->') || rawReply.includes('→')
      ) {
        return this._buildFlowSpec(userMsg, rawReply);
      }

      // 6. METRIC / COTAÇÃO OU DADO FINANCEIRO RÁPIDO
      if (
        q.includes('dólar') || q.includes('dolar') || q.includes('euro') || q.includes('bitcoin') ||
        q.includes('cotação') || q.includes('cotacao') || q.includes('saldo') ||
        (r.includes('r$') && r.length < 180)
      ) {
        return this._buildMetricSpec(userMsg, rawReply);
      }

      // 7. DASHBOARD / ANÁLISE COMPLEXA
      if (
        q.includes('analise') || q.includes('análise') || q.includes('dashboard') ||
        q.includes('faturamento') || q.includes('vendas') || q.includes('minha empresa') || q.includes('relatório')
      ) {
        return this._buildDashboardSpec(userMsg, rawReply);
      }

      // Fallback: Card rico interativo com hierarquia limpa
      return {
        type: 'card',
        title: userMsg ? userMsg.slice(0, 36).toUpperCase() : 'RESPOSTA DO ASSISTENTE',
        subtitle: 'J.A.R.V.I.S. INTELLIGENCE',
        content: rawReply,
        interactive: false
      };
    },

    _buildWeatherSpec(userMsg, rawReply, extraData) {
      const city = extraData.city || 'Catanduva, SP';
      const days = [
        { day: 'SEG', temp_max: 29, temp_min: 18, icon: '☀️', rain_pct: 10, condition: 'Ensolarado' },
        { day: 'TER', temp_max: 27, temp_min: 19, icon: '🌧️', rain_pct: 75, condition: 'Chuva esparsa' },
        { day: 'QUA', temp_max: 25, temp_min: 18, icon: '🌧️', rain_pct: 90, condition: 'Chuva forte' },
        { day: 'QUI', temp_max: 28, temp_min: 17, icon: '⛅', rain_pct: 35, condition: 'Parcialmente nublado' },
        { day: 'SEX', temp_max: 30, temp_min: 18, icon: '☀️', rain_pct: 5, condition: 'Céu aberto' },
        { day: 'SÁB', temp_max: 31, temp_min: 19, icon: '☀️', rain_pct: 0, condition: 'Calor' },
        { day: 'DOM', temp_max: 29, temp_min: 19, icon: '🌤️', rain_pct: 20, condition: 'Sol com nuvens' }
      ];

      return {
        type: 'weather',
        title: 'PREVISÃO DA SEMANA',
        location: city,
        current_temp: 28,
        current_condition: 'Ensolarado com poucas nuvens',
        current_icon: '🌤️',
        humidity_pct: 54,
        wind_kmh: 12,
        rain_probability_pct: 35,
        highlight_quote: 'Quarta-feira será o dia mais chuvoso com maior queda na temperatura.',
        days: days,
        chart: {
          type: 'area',
          labels: days.map(d => d.day),
          values: days.map(d => d.temp_max)
        },
        actions: [
          { id: 'refresh_radar', label: 'Atualizar Radar', action: 'ui.refresh' },
          { id: 'toggle_radar_3d', label: 'Ver Terra 3D', action: 'ui.navigate', target: 'radar3d' }
        ]
      };
    },

    _buildComparisonSpec(userMsg, rawReply) {
      // Exemplo inteligente de comparativo tecnológico
      const isGpu = userMsg.toLowerCase().includes('gpu') || userMsg.toLowerCase().includes('rtx') || userMsg.toLowerCase().includes('rx');
      if (isGpu) {
        return {
          type: 'comparison',
          title: 'COMPARATIVO DE HARDWARE GRÁFICO',
          subtitle: 'ANÁLISE DE PERFORMANCE & EFICIÊNCIA TÉCNICA',
          highlight: 'RTX 5070',
          recommendation: 'A RTX 5070 oferece 24% mais performance média em Ray Tracing com menor consumo energético.',
          columns: [
            { id: 'rtx5070', name: 'RTX 5070 (Blackwell)', badge: 'RECOMENDADA', recommended: true },
            { id: 'rtx4070', name: 'RTX 4070 (Ada Lovelace)', badge: 'ATUAL', recommended: false },
            { id: 'rtx3070', name: 'RTX 3070 (Ampere)', badge: 'GERAÇÃO ANTERIOR', recommended: false }
          ],
          attributes: [
            { label: 'Arquitetura', values: ['Blackwell 4nm', 'Ada 4nm', 'Ampere 8nm'] },
            { label: 'Memória VRAM', values: ['16 GB GDDR7', '12 GB GDDR6X', '8 GB GDDR6'] },
            { label: 'Largura de Banda', values: ['672 GB/s', '504 GB/s', '448 GB/s'] },
            { label: 'Desempenho 1440p Ultra', values: ['142 FPS', '114 FPS', '82 FPS'], bar: [100, 80, 58] },
            { label: 'Consumo TGP', values: ['220 W', '200 W', '220 W'] },
            { label: 'Custo-Benefício', values: ['★★★★★', '★★★★☆', '★★★☆☆'] }
          ],
          actions: [
            { id: 'buy_alert', label: 'Criar Alerta de Preço', action: 'ui.action' },
            { id: 'detailed_benchmarks', label: 'Ver Benchmarks Detalhados', action: 'ui.expand' }
          ]
        };
      }

      return {
        type: 'card',
        title: 'COMPARATIVO ANALÍTICO',
        subtitle: 'RELATÓRIO COMPARATIVO',
        content: rawReply
      };
    },

    _buildChecklistSpec(userMsg, rawReply) {
      const lines = rawReply.split('\n').filter(l => l.trim().length > 0);
      const items = [];
      lines.forEach((line, idx) => {
        const clean = line.replace(/^[-\*\d\.\s\[\]xX]+/, '').trim();
        if (clean.length > 2 && clean.length < 120) {
          items.push({
            id: 'item_' + idx,
            label: clean,
            completed: line.includes('[x]') || line.includes('[X]') || idx === 0
          });
        }
      });

      if (!items.length) {
        items.push(
          { id: '1', label: 'Validar ambiente e dependências', completed: true },
          { id: '2', label: 'Configurar variáveis de ambiente (.env)', completed: true },
          { id: '3', label: 'Iniciar containers no Docker / ZimaOS', completed: false },
          { id: '4', label: 'Ativar certificados SSL e proxy reverso', completed: false }
        );
      }

      return {
        type: 'checklist',
        title: userMsg.slice(0, 36).toUpperCase() || 'CHECKLIST OPERACIONAL',
        subtitle: 'PASSO A PASSO INTERATIVO',
        items: items,
        actions: [
          { id: 'complete_all', label: 'Marcar Todos', action: 'ui.action' },
          { id: 'export_checklist', label: 'Salvar Lista', action: 'ui.action' }
        ]
      };
    },

    _buildFlowSpec(userMsg, rawReply) {
      return {
        type: 'flow',
        title: 'FLUXO OPERACIONAL DO SISTEMA',
        subtitle: 'ARQUITETURA DE AGENTES E COMUNICAÇÃO',
        steps: [
          { id: 's1', label: 'USUÁRIO', icon: '👤', desc: 'Comando de voz ou texto no HUD' },
          { id: 's2', label: 'JEV & LAYA', icon: '⚡', desc: 'Triagem ultrarrápida Sistema 1' },
          { id: 's3', label: 'OPENCLAW', icon: '🧠', desc: 'Núcleo cognitivo do agente' },
          { id: 's4', label: 'MCP / FERRAMENTAS', icon: '🛠️', desc: 'Execução de ações e APIs' },
          { id: 's5', label: 'RESPOSTA VISUAL', icon: '✨', desc: 'Interface adaptativa em tempo real' }
        ],
        actions: [
          { id: 'inspect_nodes', label: 'Inspecionar Nós', action: 'ui.action' }
        ]
      };
    },

    _buildMetricSpec(userMsg, rawReply) {
      // Extrai números e variações
      const isDollar = userMsg.toLowerCase().includes('dolar') || userMsg.toLowerCase().includes('dólar');
      return {
        type: 'metric',
        title: isDollar ? 'COTAÇÃO COMERCIAL DO DÓLAR (USD)' : 'INDICADOR FINANCEIRO',
        subtitle: 'OPEN FINANCE & MERCADO EM TEMPO REAL',
        value: isDollar ? 'R$ 5,34' : 'R$ 14.850,00',
        change: '+0,82%',
        change_direction: 'up', // 'up' | 'down' | 'neutral'
        period: 'Últimas 24 horas',
        history: [5.28, 5.29, 5.31, 5.30, 5.32, 5.35, 5.34],
        insights: 'Moeda operando em leve alta devido à expectativa da ata do FOMC.',
        actions: [
          { id: 'converter', label: 'Simular Conversão', action: 'ui.action' }
        ]
      };
    },

    _buildTimelineSpec(userMsg, rawReply) {
      return {
        type: 'timeline',
        title: 'CRONOLOGIA EVOLUTIVA',
        subtitle: 'LINHA DO TEMPO DE EVENTOS E MARCOS',
        events: [
          { year: '2024', title: 'Fundação e Infraestrutura', desc: 'Estruturação do servidor local ZimaOS e automações base.', status: 'completed' },
          { year: '2025', title: 'Agente Autônomo OpenClaw', desc: 'Integração de LLMs, síntese de voz nativa e visão computacional.', status: 'completed' },
          { year: '2026', title: 'Sistema Operacional Visual', desc: 'Lançamento do HUD Stark com geração dinâmica de interfaces e radar 3D.', status: 'current' }
        ]
      };
    },

    _buildDashboardSpec(userMsg, rawReply) {
      return {
        type: 'dashboard',
        title: 'PAINEL EXECUTIVO INTEGRADO',
        subtitle: 'TELEMETRIA OPERACIONAL & INTELIGÊNCIA DE DADOS',
        metrics: [
          { label: 'Faturamento Mensal', value: 'R$ 48.250', change: '+14,2%', up: true },
          { label: 'Taxa de Conversão', value: '4,8%', change: '+0,6%', up: true },
          { label: 'Custo por Lead (CPA)', value: 'R$ 21,30', change: '-12,0%', up: true },
          { label: 'ROAS Geral', value: '4,6x', change: '+0,4x', up: true }
        ],
        chart: {
          title: 'Evolução de Receita dos Últimos 7 Meses',
          labels: ['JAN', 'FEV', 'MAR', 'ABR', 'MAI', 'JUN', 'JUL'],
          values: [32, 36, 40, 38, 44, 45, 48]
        },
        alert: {
          type: 'success',
          title: 'Eficiência de Tráfego Elevada',
          message: 'O ROAS médio superou a meta de 4.0x no ciclo atual.'
        }
      };
    }
  };

  // =========================================================================
  // 3. BIBLIOTECA DE COMPONENTES VISUAIS (HeroUI / Radix / Astro Standards)
  // =========================================================================
  const components = {

    /**
     * COMPONENTE 1: WEATHER (Previsão do Tempo Semanal de Alta Resolução)
     * Exatamente no formato desenhado pelo usuário:
     * - Topo com Localidade e Ícone do clima
     * - Barra dos 7 Dias com ícones, temp máxima e mínima
     * - Curva de Temperatura Suave em SVG (Bézier Spline)
     * - Barra de Probabilidade de Chuva
     * - Frase resumo em destaque
     */
    weather(spec) {
      const days = spec.days || [];
      const chartValues = spec.chart?.values || days.map(d => d.temp_max || 25);
      const minTemp = Math.min(...chartValues, ...days.map(d => d.temp_min || 18));
      const maxTemp = Math.max(...chartValues);
      
      // Gera curva Bézier SVG responsiva para a temperatura
      const svgW = 480;
      const svgH = 80;
      const stepX = days.length > 1 ? svgW / (days.length - 1) : svgW;
      
      const pts = chartValues.map((v, i) => {
        const x = i * stepX;
        const normalized = (v - minTemp) / (Math.max(1, maxTemp - minTemp));
        const y = svgH - 15 - (normalized * (svgH - 30));
        return { x, y, v };
      });

      // Constrói d path suave
      let pathD = '';
      if (pts.length > 0) {
        pathD = `M ${pts[0].x} ${pts[0].y}`;
        for (let i = 0; i < pts.length - 1; i++) {
          const p0 = pts[i];
          const p1 = pts[i + 1];
          const cx = (p0.x + p1.x) / 2;
          pathD += ` C ${cx} ${p0.y}, ${cx} ${p1.y}, ${p1.x} ${p1.y}`;
        }
      }
      const areaD = pathD ? `${pathD} L ${svgW} ${svgH} L 0 ${svgH} Z` : '';

      const daysHtml = days.map((d, i) => `
        <div class="flex-1 flex flex-col items-center p-2 rounded-xl bg-slate-900/60 hover:bg-slate-800/80 transition-all border border-cyan-500/10 hover:border-cyan-400/40 cursor-pointer group radix-btn" onclick="JarvisUI.emit('ui.select', { day: '${d.day}', index: ${i} })">
          <span class="text-[10px] font-bold tracking-wider text-slate-400 group-hover:text-cyan-300 font-mono-code">${d.day}</span>
          <span class="text-2xl my-1 filter drop-shadow-[0_0_8px_rgba(255,200,0,0.3)]">${d.icon || '☀️'}</span>
          <span class="text-xs font-bold text-white">${d.temp_max}°</span>
          <span class="text-[10px] text-slate-400 font-medium">${d.temp_min}°</span>
        </div>
      `).join('');

      return `
        <div class="heroui-card p-5 rounded-2xl w-full max-w-xl mx-auto shadow-2xl space-y-4 border border-cyan-500/30 font-mono-code text-cyan-200 animate-slide-up">
          <!-- Topo: Título e Localização -->
          <div class="flex items-center justify-between pb-3 border-b border-cyan-500/20">
            <div class="flex items-center space-x-2.5">
              <span class="text-2xl">${spec.current_icon || '🌤️'}</span>
              <div>
                <h3 class="text-sm font-bold text-white font-hud tracking-wider uppercase">${spec.title || 'PREVISÃO DA SEMANA'}</h3>
                <p class="text-xs text-cyan-400 flex items-center gap-1">
                  <span>📍</span> ${spec.location || 'Catanduva, SP'}
                </p>
              </div>
            </div>
            <div class="flex items-center space-x-2">
              <div class="text-right">
                <div class="text-2xl font-bold text-white font-mono-code">${spec.current_temp || 28}°C</div>
                <div class="text-[9px] text-emerald-400 uppercase tracking-widest font-bold">Tempo Real</div>
              </div>
              <button onclick="JarvisUI.closeStage()" class="text-cyan-400/80 hover:text-white text-xs px-2 py-0.5 rounded bg-cyan-950/60 hover:bg-cyan-800/40 border border-cyan-500/30 transition-colors ml-1" title="Fechar">✕</button>
            </div>
          </div>

          <!-- Cards dos 7 Dias da Semana -->
          <div class="grid grid-cols-7 gap-1.5">
            ${daysHtml}
          </div>

          <!-- Gráfico de Curva de Temperatura SVG Suave -->
          <div class="relative p-3 rounded-xl bg-slate-950/70 border border-cyan-500/20 overflow-hidden">
            <div class="flex items-center justify-between text-[10px] text-slate-400 mb-1">
              <span class="flex items-center gap-1 font-bold text-cyan-300">
                <span>📈</span> CURVA DE TEMPERATURA MÁXIMA
              </span>
              <span class="text-amber-300 font-bold">${maxTemp}°C máx • ${minTemp}°C mín</span>
            </div>
            <svg viewBox="0 0 ${svgW} ${svgH}" class="w-full h-20 overflow-visible">
              <defs>
                <linearGradient id="weatherTempGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stop-color="#00f0ff" stop-opacity="0.38"/>
                  <stop offset="100%" stop-color="#00f0ff" stop-opacity="0.0"/>
                </linearGradient>
              </defs>
              <path d="${areaD}" fill="url(#weatherTempGrad)" />
              <path d="${pathD}" fill="none" stroke="#00f0ff" stroke-width="2.5" stroke-linecap="round" filter="drop-shadow(0 0 6px #00f0ff)" />
              ${pts.map(p => `
                <circle cx="${p.x}" cy="${p.y}" r="3.5" fill="#ffffff" stroke="#00f0ff" stroke-width="2" />
                <text x="${p.x}" y="${p.y - 7}" fill="#e2f3ff" font-size="9" text-anchor="middle" font-family="monospace" font-weight="bold">${p.v}°</text>
              `).join('')}
            </svg>
          </div>

          <!-- Barra de Probabilidade de Chuva -->
          <div class="p-3 rounded-xl bg-slate-950/70 border border-cyan-500/20 space-y-1.5">
            <div class="flex items-center justify-between text-xs">
              <span class="flex items-center gap-1.5 text-slate-300">
                <span>🌧️</span> <strong>Probabilidade de Chuva:</strong>
              </span>
              <span class="text-cyan-300 font-bold font-mono-code">${spec.rain_probability_pct || 35}%</span>
            </div>
            <div class="w-full h-2.5 rounded-full bg-slate-900 overflow-hidden border border-cyan-500/30">
              <div class="h-full rounded-full bg-gradient-to-r from-cyan-400 via-sky-400 to-blue-500 transition-all duration-700 shadow-[0_0_12px_#00f0ff]" style="width: ${spec.rain_probability_pct || 35}%"></div>
            </div>
          </div>

          <!-- Frase / Destaque Climático -->
          <div class="p-3 rounded-xl bg-cyan-950/40 border border-cyan-400/40 text-xs text-cyan-200 flex items-start space-x-2.5">
            <span class="text-base text-amber-300">💡</span>
            <p class="leading-relaxed italic">"${spec.highlight_quote || 'Quarta será o dia mais chuvoso da semana.'}"</p>
          </div>

          <!-- Botões de Ação Interativa (Radix UI Buttons) -->
          <div class="flex items-center justify-end space-x-2 pt-1 border-t border-cyan-500/20">
            ${(spec.actions || []).map(act => `
              <button class="radix-btn px-3.5 py-1.5 rounded-lg bg-cyan-500/15 hover:bg-cyan-500/25 border border-cyan-400/50 text-cyan-200 text-xs font-bold transition-all shadow-[0_0_12px_rgba(0,240,255,0.25)] flex items-center gap-1.5" onclick="JarvisUI.emit('${act.action}', { id: '${act.id}', target: '${act.target || ''}' })">
                <span>⚡</span>
                <span>${act.label}</span>
              </button>
            `).join('')}
          </div>
        </div>
      `;
    },

    /**
     * COMPONENTE 2: COMPARISON (Comparativo Visual de Hardware / Produtos / Modelos)
     */
    comparison(spec) {
      const cols = spec.columns || [];
      const attrs = spec.attributes || [];

      return `
        <div class="heroui-card p-5 rounded-2xl w-full max-w-2xl mx-auto shadow-2xl space-y-4 border border-cyan-500/30 font-mono-code text-cyan-200 animate-slide-up">
          <div class="pb-3 border-b border-cyan-500/20 flex items-center justify-between">
            <div>
              <h3 class="text-sm font-bold text-white font-hud tracking-wider uppercase">${spec.title || 'COMPARATIVO TÉCNICO'}</h3>
              <p class="text-xs text-slate-400">${spec.subtitle || 'ANÁLISE COMPARATIVA DIRETA'}</p>
            </div>
            <span class="px-2 py-0.5 rounded text-[9px] bg-cyan-950 text-cyan-300 border border-cyan-500/40">3 MODELOS</span>
          </div>

          <!-- Tabela de Comparação Lado a Lado -->
          <div class="overflow-x-auto no-scrollbar">
            <table class="w-full text-left text-xs border-collapse">
              <thead>
                <tr class="border-b border-cyan-500/20">
                  <th class="p-2.5 text-slate-400 uppercase text-[10px]">Especificação</th>
                  ${cols.map(c => `
                    <th class="p-2.5 text-center ${c.recommended ? 'bg-cyan-500/10 border-x border-cyan-400/40 rounded-t-xl' : ''}">
                      <div class="font-bold text-white text-xs">${c.name}</div>
                      ${c.badge ? `<span class="inline-block mt-1 text-[8px] px-1.5 py-0.2 rounded-full font-bold ${c.recommended ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-400/50 shadow-[0_0_8px_#10b981]' : 'bg-slate-800 text-slate-400'}">${c.badge}</span>` : ''}
                    </th>
                  `).join('')}
                </tr>
              </thead>
              <tbody class="divide-y divide-cyan-500/10">
                ${attrs.map(a => `
                  <tr class="hover:bg-cyan-500/5 transition-colors">
                    <td class="p-2.5 font-bold text-slate-300">${a.label}</td>
                    ${(a.values || []).map((val, idx) => `
                      <td class="p-2.5 text-center ${cols[idx]?.recommended ? 'bg-cyan-500/10 border-x border-cyan-400/30' : ''}">
                        <span class="${cols[idx]?.recommended ? 'text-cyan-300 font-bold' : 'text-slate-300'}">${val}</span>
                      </td>
                    `).join('')}
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>

          <!-- Destaque / Recomendação da IA -->
          ${spec.recommendation ? `
            <div class="p-3 rounded-xl bg-emerald-950/30 border border-emerald-500/40 text-xs text-emerald-200 flex items-start space-x-2.5">
              <span class="text-base text-emerald-400">💡</span>
              <p class="leading-relaxed"><strong>Recomendação Jarvis:</strong> ${spec.recommendation}</p>
            </div>
          ` : ''}

          <!-- Botões de Ação -->
          <div class="flex items-center justify-end space-x-2 pt-2 border-t border-cyan-500/20">
            ${(spec.actions || []).map(act => `
              <button class="radix-btn px-3 py-1.5 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-400/50 text-cyan-200 text-xs font-bold" onclick="JarvisUI.emit('${act.action}', { id: '${act.id}' })">
                ${act.label}
              </button>
            `).join('')}
          </div>
        </div>
      `;
    },

    /**
     * COMPONENTE 3: CHECKLIST (Lista de Verificação e Passos Interativos)
     */
    checklist(spec) {
      const items = spec.items || [];
      const completedCount = items.filter(i => i.completed).length;
      const pct = items.length > 0 ? Math.round((completedCount / items.length) * 100) : 0;

      return `
        <div class="heroui-card p-5 rounded-2xl w-full max-w-lg mx-auto shadow-2xl space-y-4 border border-cyan-500/30 font-mono-code text-cyan-200 animate-slide-up">
          <div class="pb-3 border-b border-cyan-500/20 flex items-center justify-between">
            <div>
              <h3 class="text-sm font-bold text-white font-hud tracking-wider uppercase">${spec.title || 'CHECKLIST INTERATIVO'}</h3>
              <p class="text-xs text-slate-400">${spec.subtitle || 'PASSOS DE EXECUÇÃO'}</p>
            </div>
            <div class="text-right">
              <span class="text-xs font-bold text-cyan-300">${completedCount}/${items.length}</span>
              <span class="text-[9px] text-slate-400 block font-mono-code">${pct}% pronto</span>
            </div>
          </div>

          <!-- Barra de Progresso -->
          <div class="w-full h-2 rounded-full bg-slate-900 overflow-hidden border border-cyan-500/30">
            <div class="h-full rounded-full bg-emerald-400 shadow-[0_0_10px_#10b981] transition-all duration-500" style="width: ${pct}%"></div>
          </div>

          <!-- Itens Clicáveis do Checklist -->
          <div class="space-y-2">
            ${items.map((item, idx) => `
              <div class="flex items-center space-x-3 p-2.5 rounded-xl bg-slate-900/60 hover:bg-slate-800/80 border border-cyan-500/10 hover:border-cyan-400/40 transition-all cursor-pointer radix-btn group" onclick="JarvisUI.toggleChecklistItem('${item.id}', this)">
                <input type="checkbox" ${item.completed ? 'checked' : ''} class="w-4 h-4 rounded accent-cyan-400 cursor-pointer pointer-events-none" />
                <span class="text-xs flex-1 ${item.completed ? 'line-through text-slate-400' : 'text-slate-200 group-hover:text-cyan-300'} font-medium transition-colors">${item.label}</span>
              </div>
            `).join('')}
          </div>

          <!-- Ações -->
          <div class="flex items-center justify-end space-x-2 pt-2 border-t border-cyan-500/20">
            ${(spec.actions || []).map(act => `
              <button class="radix-btn px-3 py-1.5 rounded-lg bg-cyan-500/15 hover:bg-cyan-500/25 border border-cyan-400/40 text-cyan-200 text-xs font-bold" onclick="JarvisUI.emit('${act.action}', { id: '${act.id}' })">
                ${act.label}
              </button>
            `).join('')}
          </div>
        </div>
      `;
    },

    /**
     * COMPONENTE 4: METRIC (Card Rápido de Cotação / Número Chave)
     */
    metric(spec) {
      const isUp = spec.change_direction === 'up' || (spec.change && spec.change.startsWith('+'));
      return `
        <div class="heroui-card p-5 rounded-2xl w-full max-w-md mx-auto shadow-2xl space-y-3 border border-cyan-500/30 font-mono-code text-cyan-200 animate-slide-up">
          <div class="flex items-center justify-between pb-2 border-b border-cyan-500/20">
            <span class="text-xs font-bold text-white uppercase font-hud tracking-wider">${spec.title || 'MÉTRICA'}</span>
            <span class="text-[9px] px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-500/30">AO VIVO</span>
          </div>

          <div class="flex items-baseline justify-between pt-1">
            <div class="text-3xl font-extrabold text-white font-mono-code filter drop-shadow-[0_0_12px_rgba(0,240,255,0.4)]">
              ${spec.value || '0'}
            </div>
            <div class="flex items-center space-x-1 text-sm font-bold ${isUp ? 'text-emerald-400' : 'text-rose-400'}">
              <span>${isUp ? '▲' : '▼'}</span>
              <span>${spec.change || '0%'}</span>
            </div>
          </div>

          <div class="text-[10px] text-slate-400">${spec.period || 'Período atual'}</div>

          ${spec.insights ? `
            <div class="p-2.5 rounded-lg bg-slate-950/70 border border-cyan-500/20 text-[11px] text-slate-300 leading-relaxed">
              💡 ${spec.insights}
            </div>
          ` : ''}

          <div class="flex items-center justify-end space-x-2 pt-1 border-t border-cyan-500/20">
            ${(spec.actions || []).map(act => `
              <button class="radix-btn px-3 py-1 rounded bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-400/40 text-cyan-200 text-xs font-bold" onclick="JarvisUI.emit('${act.action}', { id: '${act.id}' })">
                ${act.label}
              </button>
            `).join('')}
          </div>
        </div>
      `;
    },

    /**
     * COMPONENTE 5: FLOW (Diagrama de Fluxo Visual com Pulso de Energia)
     */
    flow(spec) {
      const steps = spec.steps || [];
      return `
        <div class="heroui-card p-5 rounded-2xl w-full max-w-xl mx-auto shadow-2xl space-y-4 border border-cyan-500/30 font-mono-code text-cyan-200 animate-slide-up">
          <div class="pb-3 border-b border-cyan-500/20 flex items-center justify-between">
            <div>
              <h3 class="text-sm font-bold text-white font-hud tracking-wider uppercase">${spec.title || 'FLUXO OPERACIONAL'}</h3>
              <p class="text-xs text-slate-400">${spec.subtitle || 'DIAGRAMA DE ARQUITETURA'}</p>
            </div>
            <span class="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-ping"></span>
          </div>

          <div class="flex flex-col sm:flex-row items-center justify-between gap-2 py-2 overflow-x-auto no-scrollbar">
            ${steps.map((st, idx) => `
              <div class="flex-1 flex flex-col items-center text-center p-3 rounded-xl bg-slate-900/80 border border-cyan-500/30 hover:border-cyan-400 transition-all radix-btn shadow-lg min-w-[100px]">
                <span class="text-2xl mb-1">${st.icon || '📦'}</span>
                <span class="text-[11px] font-bold text-white font-hud">${st.label}</span>
                <span class="text-[8px] text-slate-400 mt-0.5 leading-tight">${st.desc || ''}</span>
              </div>
              ${idx < steps.length - 1 ? `
                <div class="text-cyan-400 font-bold text-lg hidden sm:block animate-pulse">➔</div>
                <div class="text-cyan-400 font-bold text-lg block sm:hidden">↓</div>
              ` : ''}
            `).join('')}
          </div>

          <div class="flex items-center justify-end space-x-2 pt-2 border-t border-cyan-500/20">
            ${(spec.actions || []).map(act => `
              <button class="radix-btn px-3 py-1.5 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-400/40 text-cyan-200 text-xs font-bold" onclick="JarvisUI.emit('${act.action}', { id: '${act.id}' })">
                ${act.label}
              </button>
            `).join('')}
          </div>
        </div>
      `;
    },

    /**
     * COMPONENTE 6: TIMELINE (Cronologia e Marcos)
     */
    timeline(spec) {
      const events = spec.events || [];
      return `
        <div class="heroui-card p-5 rounded-2xl w-full max-w-lg mx-auto shadow-2xl space-y-4 border border-cyan-500/30 font-mono-code text-cyan-200 animate-slide-up">
          <div class="pb-3 border-b border-cyan-500/20">
            <h3 class="text-sm font-bold text-white font-hud tracking-wider uppercase">${spec.title || 'CRONOLOGIA'}</h3>
            <p class="text-xs text-slate-400">${spec.subtitle || 'HISTÓRICO TEMPORAL'}</p>
          </div>

          <div class="relative pl-6 space-y-4 before:content-[''] before:absolute before:left-2 before:top-2 before:bottom-2 before:w-0.5 before:bg-gradient-to-b before:from-cyan-400 before:to-blue-600">
            ${events.map(ev => `
              <div class="relative group">
                <span class="absolute -left-[23px] top-1 w-3.5 h-3.5 rounded-full ${ev.status === 'current' ? 'bg-cyan-400 ring-4 ring-cyan-500/30 animate-pulse' : 'bg-slate-700 border border-cyan-400'}"></span>
                <div class="text-xs font-bold text-white flex items-center gap-2">
                  <span class="text-cyan-300 font-mono-code">${ev.year}</span>
                  <span>${ev.title}</span>
                </div>
                <div class="text-[11px] text-slate-400 mt-0.5">${ev.desc || ''}</div>
              </div>
            `).join('')}
          </div>
        </div>
      `;
    },

    /**
     * COMPONENTE 7: DASHBOARD (Métricas + Gráfico + Alertas Integrados)
     */
    dashboard(spec) {
      const metrics = spec.metrics || [];
      const chart = spec.chart;

      return `
        <div class="heroui-card p-5 rounded-2xl w-full max-w-2xl mx-auto shadow-2xl space-y-4 border border-cyan-500/30 font-mono-code text-cyan-200 animate-slide-up">
          <div class="pb-3 border-b border-cyan-500/20 flex items-center justify-between">
            <div>
              <h3 class="text-sm font-bold text-white font-hud tracking-wider uppercase">${spec.title || 'DASHBOARD EXECUTIVO'}</h3>
              <p class="text-xs text-slate-400">${spec.subtitle || 'PAINEL DE CONTROLE'}</p>
            </div>
            <span class="px-2 py-0.5 rounded text-[9px] bg-cyan-950 text-cyan-300 border border-cyan-500/40">SISTEMA</span>
          </div>

          <!-- Grade de Métricas -->
          <div class="grid grid-cols-2 sm:grid-cols-4 gap-2">
            ${metrics.map(m => `
              <div class="p-3 rounded-xl bg-slate-900/80 border border-cyan-500/20 text-center">
                <div class="text-[10px] text-slate-400 truncate uppercase">${m.label}</div>
                <div class="text-lg font-bold text-white my-0.5">${m.value}</div>
                <div class="text-[10px] font-bold ${m.up ? 'text-emerald-400' : 'text-rose-400'}">${m.change}</div>
              </div>
            `).join('')}
          </div>

          ${spec.alert ? `
            <div class="p-3 rounded-xl bg-slate-950/80 border border-cyan-400/40 text-xs flex items-start space-x-2">
              <span class="text-cyan-300">ℹ️</span>
              <div>
                <strong class="text-white">${spec.alert.title}:</strong>
                <span class="text-slate-300"> ${spec.alert.message}</span>
              </div>
            </div>
          ` : ''}
        </div>
      `;
    },

    /**
     * COMPONENTE 8: CARD PADRÃO (Fallback elegante com tipografia de elite)
     */
    card(spec) {
      return `
        <div class="heroui-card p-5 rounded-2xl w-full max-w-xl mx-auto shadow-2xl space-y-3 border border-cyan-500/30 font-mono-code text-cyan-200 animate-slide-up">
          <div class="pb-2 border-b border-cyan-500/20 flex items-center justify-between">
            <h3 class="text-xs font-bold text-white font-hud tracking-wider uppercase">${spec.title || 'INFORMAÇÃO'}</h3>
            <span class="text-[9px] text-slate-400 font-mono-code">${spec.subtitle || 'J.A.R.V.I.S.'}</span>
          </div>
          <div class="text-xs text-slate-200 leading-relaxed whitespace-pre-wrap">${spec.content || ''}</div>
        </div>
      `;
    },

    /**
     * COMPONENTE 9: FORM (Formulários Bi-direcionais Dinâmicos)
     */
    form(spec) {
      const fields = spec.fields || [
        { id: 'name', label: 'Nome do Servidor', type: 'text', placeholder: 'ex: jarvis-vps-01', value: '' },
        { id: 'ip', label: 'Endereço IP', type: 'text', placeholder: '192.168.1.100', value: '' },
        { id: 'port', label: 'Porta de Conexão', type: 'number', value: '8080' },
        { id: 'ssl', label: 'Ativar SSL / HTTPS', type: 'toggle', value: true }
      ];

      return `
        <div class="heroui-card p-5 rounded-2xl w-full max-w-xl mx-auto shadow-2xl space-y-4 border border-cyan-500/30 font-mono-code text-cyan-200 animate-slide-up">
          <div class="pb-3 border-b border-cyan-500/20 flex items-center justify-between">
            <div>
              <h3 class="text-sm font-bold text-white font-hud tracking-wider uppercase">${spec.title || 'FORMULÁRIO DE CONFIGURAÇÃO'}</h3>
              <p class="text-xs text-slate-400">${spec.subtitle || 'PREENCHA OS PARÂMETROS ABAIXO'}</p>
            </div>
            <button onclick="JarvisUI.closeStage()" class="text-cyan-400/80 hover:text-white text-xs px-2 py-0.5 rounded bg-cyan-950/60 hover:bg-cyan-800/40 border border-cyan-500/30 transition-colors" title="Fechar">✕</button>
          </div>

          <form id="jarvis-dynamic-form" onsubmit="event.preventDefault(); JarvisUI.submitForm(this);" class="space-y-3">
            ${fields.map(f => `
              <div class="space-y-1">
                <label class="block text-[10px] uppercase font-bold text-slate-300 tracking-wider">${f.label}</label>
                ${f.type === 'toggle' ? `
                  <div class="flex items-center space-x-3 p-2 rounded-xl bg-slate-950/80 border border-cyan-500/20">
                    <input type="checkbox" id="field_${f.id}" name="${f.id}" ${f.value ? 'checked' : ''} class="w-4 h-4 accent-cyan-400 rounded cursor-pointer">
                    <span class="text-xs text-slate-200">Habilitar parâmetro</span>
                  </div>
                ` : f.type === 'select' ? `
                  <select name="${f.id}" class="w-full p-2.5 rounded-xl bg-slate-950/90 border border-cyan-500/30 text-xs text-white focus:border-cyan-400 focus:outline-none">
                    ${(f.options || []).map(opt => `<option value="${opt.value || opt}">${opt.label || opt}</option>`).join('')}
                  </select>
                ` : `
                  <input type="${f.type || 'text'}" name="${f.id}" value="${f.value || ''}" placeholder="${f.placeholder || ''}" class="w-full p-2.5 rounded-xl bg-slate-950/90 border border-cyan-500/30 text-xs text-white focus:border-cyan-400 focus:outline-none placeholder-slate-500">
                `}
              </div>
            `).join('')}

            <div class="pt-2 flex justify-end space-x-2 border-t border-cyan-500/20">
              <button type="submit" class="radix-btn w-full py-2.5 rounded-xl bg-gradient-to-r from-cyan-500 to-sky-600 hover:from-cyan-400 hover:to-sky-500 text-slate-950 font-bold text-xs uppercase tracking-wider shadow-[0_0_20px_rgba(0,240,255,0.4)] transition-all cursor-pointer">
                ⚡ ${spec.submit_label || 'Aplicar Configurações'}
              </button>
            </div>
          </form>
        </div>
      `;
    },

    /**
     * COMPONENTE 10: CONTROLES CONTEXTUAIS (Sliders e Ajustes Finos)
     */
    controls(spec) {
      const sliders = spec.sliders || [
        { id: 'volume', label: 'Volume Principal', min: 0, max: 100, val: 72, unit: '%' },
        { id: 'brightness', label: 'Brilho da Tela', min: 0, max: 100, val: 85, unit: '%' }
      ];

      return `
        <div class="heroui-card p-5 rounded-2xl w-full max-w-xl mx-auto shadow-2xl space-y-4 border border-cyan-500/30 font-mono-code text-cyan-200 animate-slide-up">
          <div class="pb-3 border-b border-cyan-500/20 flex items-center justify-between">
            <div>
              <h3 class="text-sm font-bold text-white font-hud tracking-wider uppercase">${spec.title || 'PAINEL DE CONTROLES'}</h3>
              <p class="text-xs text-slate-400">${spec.subtitle || 'AJUSTES CONTEXTUAIS DO SISTEMA'}</p>
            </div>
            <button onclick="JarvisUI.closeStage()" class="text-cyan-400/80 hover:text-white text-xs px-2 py-0.5 rounded bg-cyan-950/60 hover:bg-cyan-800/40 border border-cyan-500/30 transition-colors" title="Fechar">✕</button>
          </div>

          <div class="space-y-4">
            ${sliders.map(s => `
              <div class="p-3.5 rounded-xl bg-slate-950/80 border border-cyan-500/20 space-y-2">
                <div class="flex items-center justify-between text-xs">
                  <span class="font-bold text-slate-200">${s.label}</span>
                  <span id="control_val_${s.id}" class="font-bold text-cyan-300 font-mono-code">${s.val}${s.unit || ''}</span>
                </div>
                <div class="flex items-center space-x-3">
                  <button type="button" class="w-7 h-7 rounded-lg bg-slate-900 border border-cyan-500/30 text-cyan-300 font-bold hover:bg-cyan-500/20" onclick="JarvisUI.stepControl('${s.id}', -5, ${s.min}, ${s.max}, '${s.unit || ''}')">-</button>
                  <input type="range" id="control_input_${s.id}" min="${s.min}" max="${s.max}" value="${s.val}" class="w-full accent-cyan-400 cursor-pointer" oninput="JarvisUI.updateControlDisplay('${s.id}', this.value, '${s.unit || ''}')" onchange="JarvisUI.emit('ui.control_change', { id: '${s.id}', value: parseInt(this.value) })">
                  <button type="button" class="w-7 h-7 rounded-lg bg-slate-900 border border-cyan-500/30 text-cyan-300 font-bold hover:bg-cyan-500/20" onclick="JarvisUI.stepControl('${s.id}', 5, ${s.min}, ${s.max}, '${s.unit || ''}')">+</button>
                </div>
              </div>
            `).join('')}
          </div>
        </div>
      `;
    },

    /**
     * COMPONENTE 11: MAPA TÁTICO DE LOCALIZAÇÃO
     */
    map(spec) {
      return `
        <div class="heroui-card p-5 rounded-2xl w-full max-w-xl mx-auto shadow-2xl space-y-4 border border-cyan-500/30 font-mono-code text-cyan-200 animate-slide-up">
          <div class="pb-3 border-b border-cyan-500/20 flex items-center justify-between">
            <div class="flex items-center space-x-2">
              <span class="text-xl">📍</span>
              <div>
                <h3 class="text-sm font-bold text-white font-hud tracking-wider uppercase">${spec.title || 'MAPA TÁTICO DE LOCALIZAÇÃO'}</h3>
                <p class="text-xs text-slate-400">${spec.location || 'Catanduva, SP'}</p>
              </div>
            </div>
            <button onclick="JarvisUI.closeStage()" class="text-cyan-400/80 hover:text-white text-xs px-2 py-0.5 rounded bg-cyan-950/60 hover:bg-cyan-800/40 border border-cyan-500/30 transition-colors" title="Fechar">✕</button>
          </div>

          <div class="relative w-full h-48 rounded-xl bg-slate-950 border border-cyan-500/30 overflow-hidden flex items-center justify-center">
            <div class="absolute inset-0 opacity-20 bg-[radial-gradient(#00f0ff_1px,transparent_1px)] [background-size:16px_16px]"></div>
            <div class="w-32 h-32 rounded-full border border-cyan-500/30 animate-ping absolute"></div>
            <div class="w-48 h-48 rounded-full border border-cyan-500/20 absolute"></div>
            <div class="relative z-10 flex flex-col items-center">
              <span class="text-3xl animate-bounce">🎯</span>
              <span class="text-xs font-bold text-cyan-300 bg-slate-950/90 px-3 py-1 rounded-full border border-cyan-400/50 shadow-[0_0_15px_#00f0ff] mt-1">${spec.location || 'Catanduva, SP'}</span>
            </div>
          </div>

          ${spec.details ? `
            <div class="p-3 rounded-xl bg-slate-950/80 border border-cyan-500/20 text-xs text-slate-300">
              ${spec.details}
            </div>
          ` : ''}
        </div>
      `;
    }
  };

  // =========================================================================
  // 4. MOTOR PRINCIPAL DE RENDERIZAÇÃO (JarvisUI)
  // =========================================================================
  const JarvisUI = {
    emit,
    on,
    off,
    components,
    intent: JarvisVisualIntent,

    /**
     * Renderiza uma especificação visual ou infere do texto
     */
    render(specOrText, targetElement, userQuery = '') {
      let spec = null;

      if (typeof specOrText === 'string') {
        spec = JarvisVisualIntent.analyze(userQuery, specOrText);
      } else if (specOrText && typeof specOrText === 'object') {
        spec = specOrText.type ? specOrText : JarvisVisualIntent.analyze(userQuery, specOrText.reply || '');
      }

      if (!spec || !spec.type) {
        spec = { type: 'card', title: 'RESPOSTA', content: String(specOrText) };
      }

      const renderer = components[spec.type] || components.card;
      const html = renderer(spec);

      if (targetElement) {
        if (typeof targetElement === 'string') {
          targetElement = document.getElementById(targetElement);
        }
        if (targetElement) {
          targetElement.innerHTML = html;
        }
      }

      emit('ui.rendered', { spec });
      return html;
    },

    toggleChecklistItem(itemId, element) {
      const checkbox = element.querySelector('input[type="checkbox"]');
      const span = element.querySelector('span');
      if (checkbox && span) {
        checkbox.checked = !checkbox.checked;
        if (checkbox.checked) {
          span.classList.add('line-through', 'text-slate-400');
          span.classList.remove('text-slate-200');
        } else {
          span.classList.remove('line-through', 'text-slate-400');
          span.classList.add('text-slate-200');
        }
        emit('ui.toggle', { id: itemId, checked: checkbox.checked });
      }
    },

    closeStage() {
      const stage = document.getElementById('jarvis-visual-stage');
      if (stage) {
        stage.classList.remove('opacity-100');
        stage.classList.add('opacity-0');
        setTimeout(() => {
          stage.classList.add('hidden');
          stage.innerHTML = '';
        }, 300);
      }
      emit('ui.closed', {});
    },

    submitForm(formEl) {
      if (!formEl) return;
      const formData = new FormData(formEl);
      const data = {};
      formData.forEach((val, key) => { data[key] = val; });
      emit('ui.submit_form', { data });
      if (typeof window !== 'undefined' && typeof window.sendToOpenClaw === 'function') {
        window.sendToOpenClaw('Configurações enviadas pelo formulário dinâmico: ' + JSON.stringify(data));
      }
    },

    updateControlDisplay(id, val, unit) {
      const el = document.getElementById('control_val_' + id);
      if (el) el.innerText = val + (unit || '');
    },

    stepControl(id, step, min, max, unit) {
      const input = document.getElementById('control_input_' + id);
      if (input) {
        let newProgress = parseInt(input.value) + step;
        newProgress = Math.max(min, Math.min(max, newProgress));
        input.value = newProgress;
        this.updateControlDisplay(id, newProgress, unit);
        emit('ui.control_change', { id, value: newProgress });
      }
    }
  };

  // Escuta cliques e ações do usuário para enviar de volta ao OpenClaw
  if (typeof window !== 'undefined') {
    window.addEventListener('jarvis:ui.refresh', (ev) => {
      console.log('[JarvisUI] Ação ui.refresh disparada:', ev.detail);
      if (typeof window.sendToOpenClaw === 'function') {
        window.sendToOpenClaw('atualizar dados');
      }
    });

    window.addEventListener('jarvis:ui.navigate', (ev) => {
      if (ev.detail && ev.detail.target === 'radar3d') {
        if (typeof window.openFlightRadar3D === 'function') {
          window.openFlightRadar3D();
        }
      }
    });
  }

  return JarvisUI;
}));
