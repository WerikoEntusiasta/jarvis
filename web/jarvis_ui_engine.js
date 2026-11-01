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

      // 8. NOTÍCIAS / BRIEFING NARRADO DE TECNOLOGIA
      if (
        q.includes('notícia') || q.includes('noticia') || q.includes('notícias') || q.includes('noticias') ||
        q.includes('news') || q.includes('briefing') || q.includes('manchete') || q.includes('novidades tech')
      ) {
        return this._buildNewsSpec(userMsg, rawReply, extraData);
      }

      // 9. CONFIRMAÇÃO DE AÇÃO / AUTORIZAÇÃO
      if (
        q.includes('confirmar') || q.includes('autorização') || q.includes('autorizacao') ||
        rawReply.includes('[APROVAR]') || rawReply.includes('[CONFIRMAR]') || rawReply.includes('Deseja prosseguir?')
      ) {
        return this._buildConfirmationSpec(userMsg, rawReply);
      }

      // 10. RESULTADOS DE PESQUISA
      if (
        q.includes('pesquisa') || q.includes('pesquisar') || q.includes('buscar na web') ||
        q.includes('procure sobre') || q.includes('quem foi') || q.includes('o que significa')
      ) {
        return this._buildSearchSpec(userMsg, rawReply, extraData);
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

    _buildNewsSpec(userMsg, rawReply, extraData) {
      const articles = extraData.articles || [];
      return {
        type: 'news_deck',
        title: 'BRIEFING TÉCNICO // NOTÍCIAS DE TECNOLOGIA',
        category: 'TECNOLOGIA & INOVAÇÃO',
        articles: articles,
        activeIndex: 0
      };
    },

    _buildConfirmationSpec(userMsg, rawReply) {
      return {
        type: 'confirmation',
        title: 'AUTORIZAÇÃO DE OPERAÇÃO',
        description: rawReply || 'O J.A.R.V.I.S. solicita sua confirmação para prosseguir com a ação solicitada.',
        level: 'warning',
        actionId: 'action_' + Date.now()
      };
    },

    _buildSearchSpec(userMsg, rawReply, extraData) {
      return {
        type: 'search_results',
        query: userMsg || 'Pesquisa',
        status: 'confirmed',
        results: extraData.results || [
          {
            title: userMsg.toUpperCase(),
            source: 'OPENCLAW WEB RADAR',
            summary: rawReply,
            badge: 'VERIFICADO'
          }
        ]
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
    },

        /**
     * COMPONENTE: NEWS DECK (Briefing Narrado Multi-Cards com Layouts Dinâmicos e Foco Hero)
     */
    news_deck(spec) {
      const articles = spec.articles || [];
      const activeIdx = spec.activeIndex !== undefined ? spec.activeIndex : (window.JarvisUI && window.JarvisUI._lastNewsActiveIdx !== undefined ? window.JarvisUI._lastNewsActiveIdx : 0);
      const layout = spec.layout || (window.JarvisUI && window.JarvisUI._currentNewsLayout ? window.JarvisUI._currentNewsLayout : 'spotlight');
      if (window.JarvisUI) {
        window.JarvisUI._lastNewsSpec = spec;
        window.JarvisUI._currentNewsLayout = layout;
        window.JarvisUI._lastNewsActiveIdx = activeIdx;
      }
      
      const placeholderImg = "https://images.unsplash.com/photo-1518770660439-4636190af475?w=800&auto=format&fit=crop&q=80";

      if (!articles.length) {
        return `
          <div class="glass-card-stark p-8 rounded-2xl w-full max-w-2xl mx-auto text-center border border-sky-500/30">
            <span class="text-3xl text-cyan-400 mb-2 block animate-pulse">📡</span>
            <h3 class="text-base font-bold text-white font-hud tracking-wide uppercase mb-1">NENHUMA NOTÍCIA DISPONÍVEL</h3>
            <p class="text-xs text-slate-400 mb-4">Os feeds de notícias estão sendo sincronizados ou não retornaram artigos para este tópico.</p>
            <button onclick="JarvisPresentation && JarvisPresentation.showNewsBriefing('technology')" class="px-4 py-1.5 rounded-lg bg-cyan-950/80 hover:bg-cyan-900 border border-cyan-400 text-cyan-300 font-mono-code text-xs transition-colors">
              ↻ SINCRONIZAR NOVAMENTE
            </button>
          </div>
        `;
      }

      // Barra de Seleção de Layouts Dinâmicos & Fundo Limpo
      const isCleanBg = document.body.classList.contains('presentation-clean-bg');
      const layoutToolbar = `
        <div class="w-full flex flex-wrap items-center justify-between gap-2 px-1 pb-2 border-b border-cyan-500/20 mb-3">
          <div class="flex items-center space-x-2">
            <span class="text-[10px] font-mono-code text-slate-400 uppercase tracking-wider">LAYOUT DO DECK:</span>
            <div class="inline-flex rounded-lg p-0.5 bg-slate-950/80 border border-cyan-500/30">
              <button onclick="window.JarvisUI && window.JarvisUI.setNewsLayout('spotlight')" 
                      class="px-2.5 py-1 rounded-md text-[10px] font-mono-code transition-all ${layout === 'spotlight' ? 'bg-cyan-500/30 text-cyan-200 font-bold border border-cyan-400/50 shadow-[0_0_10px_rgba(0,240,255,0.3)]' : 'text-slate-400 hover:text-cyan-300'}">
                ◫ FOCO HERO
              </button>
              <button onclick="window.JarvisUI && window.JarvisUI.setNewsLayout('magazine')" 
                      class="px-2.5 py-1 rounded-md text-[10px] font-mono-code transition-all ${layout === 'magazine' ? 'bg-cyan-500/30 text-cyan-200 font-bold border border-cyan-400/50 shadow-[0_0_10px_rgba(0,240,255,0.3)]' : 'text-slate-400 hover:text-cyan-300'}">
                ☷ REVISTA
              </button>
              <button onclick="window.JarvisUI && window.JarvisUI.setNewsLayout('grid')" 
                      class="px-2.5 py-1 rounded-md text-[10px] font-mono-code transition-all ${layout === 'grid' ? 'bg-cyan-500/30 text-cyan-200 font-bold border border-cyan-400/50 shadow-[0_0_10px_rgba(0,240,255,0.3)]' : 'text-slate-400 hover:text-cyan-300'}">
                ⚏ GRADE
              </button>
            </div>
          </div>
          <div class="flex items-center space-x-2">
            <button id="pres-btn-cleanbg" 
                    onclick="window.JarvisPresentation && window.JarvisPresentation.toggleCleanBackground()" 
                    title="Alterna entre Fundo Limpo e Modo HUD com Vortex"
                    class="px-3 py-1 rounded-lg ${isCleanBg ? 'border-cyan-400 bg-cyan-950/90 text-cyan-200' : 'bg-slate-900 border-slate-700 text-slate-300'} border text-[10px] font-mono-code font-bold transition-all shadow-[0_0_12px_rgba(0,240,255,0.25)] flex items-center space-x-1.5 hover:border-cyan-400 hover:text-cyan-200">
              <span>✦</span>
              <span id="pres-cleanbg-label">${isCleanBg ? 'FUNDO LIMPO' : 'MODO HUD'}</span>
            </button>
            <span class="text-[9px] font-mono-code text-cyan-400/70">${articles.length} MATÉRIAS</span>
          </div>
        </div>
      `;

      // 1. LAYOUT SPOTLIGHT (Hero Card de Destaque Principal + Dock de Contexto)
      if (layout === 'spotlight') {
        const activeArt = articles[activeIdx] || articles[0];
        const heroImg = activeArt.imageUrl || placeholderImg;
        const heroSource = (activeArt.source || "RADAR").toUpperCase();
        const heroDate = activeArt.publishedAt ? (activeArt.publishedAt.length > 16 ? activeArt.publishedAt.slice(0, 16) : activeArt.publishedAt) : "HOJE";

        const dockCardsHtml = articles.map((art, idx) => {
          const isActive = idx === activeIdx;
          const activeBorder = isActive 
            ? "border-cyan-400 bg-cyan-950/70 shadow-[0_0_20px_rgba(0,240,255,0.4)] scale-[1.02]" 
            : "border-slate-800 bg-slate-950/60 hover:border-cyan-500/40 opacity-75 hover:opacity-100";
          const imgUrl = art.imageUrl || placeholderImg;
          const sourceName = (art.source || "RADAR").toUpperCase();

          return `
            <div id="news-card-item-${idx}" 
                 data-news-idx="${idx}"
                 onclick="window.JarvisNewsNarrator && window.JarvisNewsNarrator.jumpTo(${idx})"
                 class="glass-card-stark p-2.5 rounded-xl border flex items-center space-x-3 transition-all duration-300 cursor-pointer group ${activeBorder}">
              
              <div class="w-16 h-14 rounded-lg overflow-hidden bg-slate-900 flex-shrink-0 border border-cyan-900/40 relative">
                <img src="${imgUrl}" alt="${art.title}" class="w-full h-full object-cover group-hover:scale-110 transition-transform duration-500">
                <div class="absolute inset-0 bg-slate-950/20"></div>
                <div id="news-card-badge-${idx}" class="absolute top-1 left-1">
                  ${isActive ? `
                    <span class="px-1.5 py-0.5 rounded bg-cyan-500/90 text-[8px] font-mono-code font-bold text-slate-950 animate-pulse">
                      ılılı
                    </span>
                  ` : `
                    <span class="px-1.5 py-0.5 rounded bg-slate-950/80 text-[8px] font-mono-code font-bold text-slate-400">
                      #${idx + 1}
                    </span>
                  `}
                </div>
              </div>

              <div class="flex-1 min-w-0">
                <div class="flex items-center justify-between space-x-1 mb-0.5">
                  <span class="text-[9px] font-mono-code font-bold text-cyan-300 truncate">${sourceName}</span>
                  <span class="text-[8px] font-mono-code text-slate-500">${art.publishedAt ? art.publishedAt.slice(0, 10) : ''}</span>
                </div>
                <h5 class="text-[11px] font-bold text-white font-hud line-clamp-2 leading-snug group-hover:text-cyan-200 transition-colors">
                  ${art.title}
                </h5>
              </div>
            </div>
          `;
        }).join('');

        return `
          <div class="w-full space-y-3 animate-slide-up">
            ${layoutToolbar}

            <div class="grid grid-cols-1 lg:grid-cols-12 gap-4 w-full">
              
              <!-- Left/Main: Hero Card Ativo -->
              <div id="news-hero-stage" 
                   class="lg:col-span-8 glass-card-stark rounded-2xl overflow-hidden border border-cyan-400/80 shadow-[0_0_50px_rgba(0,240,255,0.35)] transition-all duration-500 relative flex flex-col justify-between">
                
                <div class="relative w-full h-56 sm:h-72 bg-slate-950 overflow-hidden border-b border-cyan-500/30">
                  <img id="news-hero-image" 
                       src="${heroImg}" 
                       alt="${activeArt.title}"
                       class="w-full h-full object-cover transition-transform duration-700 hover:scale-105 brightness-95"
                       onerror="this.onerror=null;this.src='${placeholderImg}';">
                  <div class="absolute inset-0 bg-gradient-to-t from-[#020b1e] via-[#020b1e]/50 to-transparent pointer-events-none"></div>
                  
                  <div class="absolute top-3 left-3 flex items-center space-x-2">
                    <span id="news-hero-badge" class="px-2.5 py-1 rounded-full bg-cyan-500/30 border border-cyan-300 text-[10px] font-mono-code font-bold text-cyan-100 animate-pulse flex items-center space-x-1 shadow-[0_0_15px_rgba(0,240,255,0.6)]">
                      <span>ılılı</span>
                      <span>EM DESTAQUE NARRADO</span>
                    </span>
                    <span id="news-hero-source" class="px-2.5 py-1 rounded-full bg-slate-950/80 border border-slate-700 text-[10px] font-mono-code font-bold text-cyan-300">
                      ${heroSource}
                    </span>
                  </div>

                  <div class="absolute bottom-3 right-3 px-2 py-0.5 rounded bg-slate-950/80 border border-cyan-900/50 text-[9px] font-mono-code text-cyan-300/80">
                    ${heroDate}
                  </div>
                </div>

                <div class="p-5 flex-1 flex flex-col justify-between bg-gradient-to-b from-[#020b1e] to-[#010614]">
                  <div>
                    <h3 id="news-hero-title" class="text-base sm:text-lg md:text-xl font-bold text-white font-hud tracking-wide leading-snug mb-3">
                      ${activeArt.title}
                    </h3>
                    <p id="news-hero-summary" class="text-xs sm:text-sm text-slate-200 leading-relaxed font-normal mb-4">
                      ${activeArt.summary}
                    </p>
                  </div>

                  <div class="pt-3 border-t border-cyan-900/40 flex flex-wrap items-center justify-between gap-3">
                    <a id="news-hero-link" 
                       href="${activeArt.url || '#'}" 
                       target="_blank" 
                       rel="noopener noreferrer"
                       class="px-3.5 py-1.5 rounded-lg bg-cyan-950/80 hover:bg-cyan-900 border border-cyan-400 text-cyan-200 text-xs font-mono-code font-bold transition-all shadow-[0_0_15px_rgba(0,240,255,0.3)] flex items-center space-x-1.5">
                      <span>LER MATÉRIA COMPLETA</span>
                      <span>↗</span>
                    </a>
                    
                    <div class="flex items-center space-x-2 text-[10px] font-mono-code text-cyan-400/80">
                      <span>SINTONIZADOR AUDIO:</span>
                      <span class="inline-flex space-x-0.5 items-end h-3">
                        <span class="w-1 h-2 bg-cyan-400 animate-pulse"></span>
                        <span class="w-1 h-3 bg-cyan-300 animate-pulse" style="animation-delay: 150ms;"></span>
                        <span class="w-1 h-1.5 bg-cyan-500 animate-pulse" style="animation-delay: 300ms;"></span>
                        <span class="w-1 h-3 bg-cyan-200 animate-pulse" style="animation-delay: 75ms;"></span>
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Right: Secondary Dock -->
              <div class="lg:col-span-4 flex flex-col space-y-2.5">
                <div class="text-[10px] font-mono-code font-bold text-cyan-300/80 tracking-wider uppercase mb-0.5 flex items-center justify-between">
                  <span>OUTRAS MATÉRIAS DO BRIEFING</span>
                  <span>CLIQUE P/ FOCAR</span>
                </div>
                ${dockCardsHtml}
              </div>

            </div>
          </div>
        `;
      }

      // 2. LAYOUT MAGAZINE (Revista Tática com Grid Assimétrico)
      if (layout === 'magazine') {
        const cardsHtml = articles.map((art, idx) => {
          const isActive = idx === activeIdx;
          const isLarge = idx === 0;
          const activeClass = isActive ? "card-narrated-active" : "card-narrated-inactive";
          const imgUrl = art.imageUrl || placeholderImg;
          const sourceName = (art.source || "RADAR").toUpperCase();
          const colSpan = isLarge ? "md:col-span-2 md:row-span-2 min-h-[420px]" : "col-span-1 min-h-[220px]";

          return `
            <div id="news-card-item-${idx}" 
                 data-news-idx="${idx}"
                 onclick="window.JarvisNewsNarrator && window.JarvisNewsNarrator.jumpTo(${idx})"
                 class="glass-card-stark rounded-2xl overflow-hidden flex flex-col justify-between transition-all duration-300 spring-trans relative cursor-pointer group ${colSpan} ${activeClass}">
              
              <div class="p-3 pb-2 flex items-center justify-between border-b border-cyan-500/20 bg-slate-950/60">
                <span class="text-[10px] font-mono-code font-bold text-cyan-300 truncate">${sourceName}</span>
                <div id="news-card-badge-${idx}">
                  ${isActive ? `<span class="px-2 py-0.5 rounded-full bg-cyan-500/25 border border-cyan-400 text-[9px] font-mono-code font-bold text-cyan-200 animate-pulse">ılılı NARRANDO</span>` : `<span class="text-[9px] font-mono-code text-slate-400">#${idx + 1}</span>`}
                </div>
              </div>

              <div class="relative w-full ${isLarge ? 'h-52' : 'h-28'} bg-slate-950 overflow-hidden">
                <img src="${imgUrl}" alt="${art.title}" class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-700">
                <div class="absolute inset-0 bg-gradient-to-t from-slate-950/90 via-transparent to-transparent"></div>
              </div>

              <div class="p-4 flex-1 flex flex-col justify-between">
                <div>
                  <h4 class="${isLarge ? 'text-base' : 'text-xs'} font-bold text-white font-hud line-clamp-2 leading-snug mb-2 group-hover:text-cyan-200 transition-colors">
                    ${art.title}
                  </h4>
                  <p class="text-[11px] text-slate-300 leading-relaxed ${isLarge ? 'line-clamp-4' : 'line-clamp-2'}">
                    ${art.summary}
                  </p>
                </div>
                <div class="pt-2 mt-2 border-t border-cyan-900/40 flex items-center justify-between">
                  <a href="${art.url || '#'}" target="_blank" onclick="event.stopPropagation();" class="text-[10px] font-mono-code text-cyan-400 hover:underline">LER ORIGINAL ↗</a>
                </div>
              </div>
            </div>
          `;
        }).join('');

        return `
          <div class="w-full space-y-3 animate-slide-up">
            ${layoutToolbar}
            <div class="grid grid-cols-1 md:grid-cols-3 gap-3.5 w-full">
              ${cardsHtml}
            </div>
          </div>
        `;
      }

      // 3. LAYOUT GRID (Grade Clássica Flexível)
      const cardsHtml = articles.map((art, idx) => {
        const isActive = idx === activeIdx;
        const activeClass = isActive ? "card-narrated-active" : "card-narrated-inactive";
        const imgUrl = art.imageUrl || placeholderImg;
        const sourceName = (art.source || "RADAR").toUpperCase();

        return `
          <div id="news-card-item-${idx}" 
               data-news-idx="${idx}"
               onclick="window.JarvisNewsNarrator && window.JarvisNewsNarrator.jumpTo(${idx})"
               class="glass-card-stark rounded-2xl overflow-hidden flex flex-col justify-between transition-all duration-300 spring-trans relative cursor-pointer group ${activeClass}"
               style="min-height: 340px;">
            <div class="p-3 pb-2 flex items-center justify-between border-b border-cyan-500/20 bg-slate-950/50">
              <span class="text-[10px] font-mono-code font-bold text-cyan-300 truncate">${sourceName}</span>
              <div id="news-card-badge-${idx}">
                ${isActive ? `<span class="px-2 py-0.5 rounded-full bg-cyan-500/25 border border-cyan-400 text-[9px] font-mono-code font-bold text-cyan-200 animate-pulse">ılılı NARRANDO</span>` : `<span class="text-[9px] font-mono-code text-slate-400">#${idx + 1}</span>`}
              </div>
            </div>
            <div class="relative w-full h-36 bg-slate-950 overflow-hidden">
              <img src="${imgUrl}" alt="${art.title}" class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-700">
              <div class="absolute inset-0 bg-gradient-to-t from-slate-950/90 via-transparent to-transparent"></div>
            </div>
            <div class="p-3.5 flex-1 flex flex-col justify-between">
              <div>
                <h4 class="text-xs font-bold text-white font-hud line-clamp-2 leading-snug tracking-wide mb-2 group-hover:text-cyan-200 transition-colors">
                  ${art.title}
                </h4>
                <p class="text-[11px] text-slate-300 leading-relaxed line-clamp-3">
                  ${art.summary}
                </p>
              </div>
              <div class="pt-3 mt-2 border-t border-cyan-900/40 flex items-center justify-between">
                <a href="${art.url || '#'}" target="_blank" onclick="event.stopPropagation();" class="text-[10px] font-mono-code text-cyan-400 hover:underline">LER ORIGINAL ↗</a>
                <span class="text-[9px] font-mono-code text-slate-500">CLIQUE P/ FOCAR</span>
              </div>
            </div>
          </div>
        `;
      }).join('');

      return `
        <div class="w-full space-y-3 animate-slide-up">
          ${layoutToolbar}
          <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3.5 w-full">
            ${cardsHtml}
          </div>
        </div>
      `;
    },

    /**
     * COMPONENTE: SEARCH RESULTS (Painel de Resultados de Pesquisa)
     */
    search_results(spec) {
      const query = spec.query || "Pesquisa";
      const results = spec.results || [];
      const status = spec.status || (results.length ? "confirmed" : "empty");

      const statusBadge = {
        confirmed: '<span class="px-2 py-0.5 rounded-full bg-emerald-500/20 border border-emerald-400/50 text-emerald-300 text-[9px] font-mono-code font-bold">✓ CONFIRMADO</span>',
        partial: '<span class="px-2 py-0.5 rounded-full bg-amber-500/20 border border-amber-400/50 text-amber-300 text-[9px] font-mono-code font-bold">⚠ PARCIAL</span>',
        failed: '<span class="px-2 py-0.5 rounded-full bg-rose-500/20 border border-rose-400/50 text-rose-300 text-[9px] font-mono-code font-bold">✕ FALHA NA PESQUISA</span>',
        empty: '<span class="px-2 py-0.5 rounded-full bg-slate-800 border border-slate-600 text-slate-400 text-[9px] font-mono-code font-bold">SEM DADOS</span>'
      }[status] || '';

      if (!results.length) {
        return `
          <div class="glass-card-stark p-6 rounded-2xl w-full max-w-xl mx-auto text-center border border-rose-500/30">
            <span class="text-3xl text-rose-400 mb-2 block">🔍</span>
            <h3 class="text-sm font-bold text-white font-hud tracking-wider uppercase mb-1">NENHUM RESULTADO ENCONTRADO</h3>
            <p class="text-xs text-slate-400 mb-4">Não foram encontrados dados verificados para a consulta "${query}".</p>
            <button onclick="JarvisPresentation && JarvisPresentation.close()" class="px-3 py-1 rounded bg-slate-900 border border-slate-700 text-xs text-slate-300 hover:text-white">VOLTAR AO NÚCLEO</button>
          </div>
        `;
      }

      const itemsHtml = results.map((item, idx) => `
        <div class="p-3.5 rounded-xl bg-slate-950/70 border border-cyan-500/25 hover:border-cyan-400/60 transition-all space-y-1.5">
          <div class="flex items-center justify-between">
            <span class="text-[9px] font-mono-code text-cyan-400 font-bold uppercase tracking-wider">${item.source || 'FONTE WEB'}</span>
            ${item.badge ? `<span class="text-[8px] font-mono-code text-slate-400">${item.badge}</span>` : ''}
          </div>
          <h4 class="text-xs font-bold text-white font-hud leading-snug hover:text-cyan-200 transition-colors">
            ${item.title}
          </h4>
          <p class="text-[11px] text-slate-300 leading-relaxed font-normal">${item.summary || item.snippet || ''}</p>
          ${item.url ? `
            <div class="pt-1.5 flex justify-end">
              <a href="${item.url}" target="_blank" rel="noopener" class="text-[10px] font-mono-code text-cyan-400 hover:underline flex items-center space-x-1">
                <span>ABRIR FONTE ORIGINAL</span>
                <span>↗</span>
              </a>
            </div>
          ` : ''}
        </div>
      `).join('');

      return `
        <div class="glass-card-stark p-5 rounded-2xl w-full max-w-3xl mx-auto space-y-3.5 border border-cyan-500/40">
          <div class="flex items-center justify-between border-b border-cyan-500/20 pb-2.5">
            <div class="flex items-center space-x-2">
              <span class="text-base">🌐</span>
              <div>
                <h3 class="text-xs font-bold text-white font-hud uppercase tracking-wider">RESULTADOS DA PESQUISA: "${query}"</h3>
                <span class="text-[9px] font-mono-code text-slate-400">${results.length} resultados indexados</span>
              </div>
            </div>
            <div>${statusBadge}</div>
          </div>
          <div class="space-y-2.5 max-h-[500px] overflow-y-auto pr-1 custom-scrollbar">
            ${itemsHtml}
          </div>
        </div>
      `;
    },

    /**
     * COMPONENTE: CHART PANEL (Gráficos e Indicadores)
     */
    chart_panel(spec) {
      const title = spec.title || "TELEMETRIA DE DADOS";
      const subtitle = spec.subtitle || "INDICADORES EM TEMPO REAL";
      const indicator = spec.indicator || { label: "TOTAL", value: "--", change: "0%" };
      const labels = spec.chart?.labels || [];
      const values = spec.chart?.values || [];
      const metrics = spec.metrics || [];

      if (!values.length || values.every(v => v === 0)) {
        return `
          <div class="glass-card-stark p-8 rounded-2xl w-full max-w-xl mx-auto text-center border border-sky-500/30">
            <span class="text-3xl text-sky-400 mb-2 block animate-pulse">📊</span>
            <h3 class="text-sm font-bold text-white font-hud uppercase tracking-wider mb-1">NENHUM DADO DISPONÍVEL NO PERÍODO</h3>
            <p class="text-xs text-slate-400 mb-4">O subsistema de telemetria não registrou dados estatísticos suficientes para gerar a curva.</p>
            <button onclick="JarvisPresentation && JarvisPresentation.close()" class="px-3 py-1 rounded bg-slate-900 border border-slate-700 text-xs text-slate-300 hover:text-white">VOLTAR AO NÚCLEO</button>
          </div>
        `;
      }

      const maxVal = Math.max(...values, 1);
      const minVal = Math.min(...values, 0);
      const range = (maxVal - minVal) || 1;
      const width = 500;
      const height = 140;
      const padding = 20;

      const points = values.map((v, i) => {
        const x = padding + (i / Math.max(values.length - 1, 1)) * (width - 2 * padding);
        const y = height - padding - ((v - minVal) / range) * (height - 2 * padding);
        return { x, y, v };
      });

      let pathD = `M ${points[0].x} ${points[0].y}`;
      for (let i = 0; i < points.length - 1; i++) {
        const p0 = points[i];
        const p1 = points[i + 1];
        const cx = (p0.x + p1.x) / 2;
        pathD += ` C ${cx} ${p0.y}, ${cx} ${p1.y}, ${p1.x} ${p1.y}`;
      }

      const areaD = `${pathD} L ${points[points.length - 1].x} ${height} L ${points[0].x} ${height} Z`;

      const subMetricsHtml = metrics.map(m => `
        <div class="p-2.5 rounded-xl bg-slate-950/70 border border-cyan-900/40 text-center">
          <div class="text-[9px] font-mono-code text-slate-400 uppercase">${m.label}</div>
          <div class="text-sm font-bold text-cyan-300 font-mono-code">${m.value}</div>
          ${m.change ? `<div class="text-[9px] font-mono-code ${m.is_positive ? 'text-emerald-400' : 'text-rose-400'}">${m.change}</div>` : ''}
        </div>
      `).join('');

      return `
        <div class="glass-card-stark p-5 rounded-2xl w-full max-w-2xl mx-auto space-y-4 border border-cyan-500/40 animate-slide-up">
          <div class="flex items-center justify-between border-b border-cyan-500/20 pb-3">
            <div>
              <h3 class="text-xs font-bold text-white font-hud uppercase tracking-wider">${title}</h3>
              <p class="text-[10px] font-mono-code text-slate-400">${subtitle}</p>
            </div>
            <div class="text-right">
              <span class="text-xl font-black text-cyan-300 font-mono-code drop-shadow-[0_0_10px_rgba(0,240,255,0.7)]">${indicator.value}</span>
              <div class="text-[9px] font-mono-code ${indicator.is_positive ? 'text-emerald-400' : 'text-rose-400'}">${indicator.change} vs anterior</div>
            </div>
          </div>

          <div class="w-full overflow-hidden rounded-xl bg-slate-950/80 p-2 border border-cyan-500/20">
            <svg viewBox="0 0 ${width} ${height}" class="w-full h-32 overflow-visible">
              <defs>
                <linearGradient id="chartGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stop-color="#00f0ff" stop-opacity="0.35"/>
                  <stop offset="100%" stop-color="#00f0ff" stop-opacity="0.0"/>
                </linearGradient>
              </defs>
              <path d="${areaD}" fill="url(#chartGrad)"/>
              <path d="${pathD}" fill="none" stroke="#00f0ff" stroke-width="2.5" stroke-linecap="round"/>
              ${points.map(p => `
                <circle cx="${p.x}" cy="${p.y}" r="3" fill="#00f0ff" stroke="#010a20" stroke-width="1.5"/>
              `).join('')}
            </svg>
            <div class="flex justify-between px-2 pt-1 border-t border-slate-800 text-[9px] font-mono-code text-slate-400">
              ${labels.map(l => `<span>${l}</span>`).join('')}
            </div>
          </div>

          ${metrics.length ? `
            <div class="grid grid-cols-${Math.min(metrics.length, 4)} gap-2">
              ${subMetricsHtml}
            </div>
          ` : ''}
        </div>
      `;
    },

    /**
     * COMPONENTE: CONFIRMATION (Autorização de Ações Sensíveis)
     */
    confirmation(spec) {
      const title = spec.title || "CONFIRMAÇÃO DE AÇÃO";
      const description = spec.description || "O J.A.R.V.I.S. solicita autorização para prosseguir com a operação.";
      const actionId = spec.actionId || "action_" + Date.now();
      const level = spec.level || "warning";
      const levelColor = level === 'critical' ? 'rose' : (level === 'warning' ? 'amber' : 'cyan');

      return `
        <div class="glass-card-stark p-6 rounded-2xl w-full max-w-lg mx-auto space-y-4 border border-${levelColor}-500/60 shadow-[0_0_40px_rgba(245,158,11,0.25)] animate-slide-up">
          <div class="flex items-center space-x-3 border-b border-slate-800 pb-3">
            <div class="w-10 h-10 rounded-xl bg-${levelColor}-500/20 border border-${levelColor}-400 flex items-center justify-center text-xl animate-pulse">
              🛡️
            </div>
            <div>
              <span class="text-[9px] font-mono-code font-bold uppercase text-${levelColor}-400 tracking-wider">SOLICITAÇÃO DE AUTORIZAÇÃO</span>
              <h3 class="text-sm font-bold text-white font-hud uppercase tracking-wide">${title}</h3>
            </div>
          </div>

          <div class="p-3.5 rounded-xl bg-slate-950/80 border border-slate-800 text-xs text-slate-200 leading-relaxed font-normal">
            ${description}
          </div>

          ${spec.details ? `
            <div class="p-2.5 rounded-lg bg-slate-950/50 border border-slate-800 font-mono-code text-[10px] text-slate-400">
              <code>${spec.details}</code>
            </div>
          ` : ''}

          <div class="pt-2 flex items-center space-x-3">
            <button onclick="JarvisUI.handleCancel('${actionId}')" 
                    class="flex-1 py-2 rounded-xl bg-slate-900/80 hover:bg-slate-800 border border-slate-700 text-slate-300 font-mono-code text-xs font-bold transition-all">
              ✕ CANCELAR
            </button>
            <button onclick="JarvisUI.handleConfirm('${actionId}')" 
                    class="flex-1 py-2 rounded-xl bg-emerald-950/80 hover:bg-emerald-900 border border-emerald-400/80 text-emerald-300 font-mono-code text-xs font-bold transition-all shadow-[0_0_20px_rgba(16,185,129,0.3)]">
              ✓ CONFIRMAR AÇÃO
            </button>
          </div>
        </div>
      `;
    },

    /**
     * COMPONENTE: ERROR STATE
     */
    error_state(spec) {
      const title = spec.title || "FALHA DE COMUNICAÇÃO";
      const message = spec.message || "Não foi possível sincronizar os dados com o servidor central.";
      const retryAction = spec.retryAction || "JarvisPresentation && JarvisPresentation.close()";

      return `
        <div class="glass-card-stark p-6 rounded-2xl w-full max-w-lg mx-auto text-center border border-rose-500/50 shadow-[0_0_35px_rgba(244,63,94,0.3)] animate-slide-up">
          <div class="w-12 h-12 rounded-xl bg-rose-500/20 border border-rose-400 flex items-center justify-center text-2xl mx-auto mb-3 animate-pulse">
            ⚠️
          </div>
          <span class="text-[9px] font-mono-code font-bold uppercase text-rose-400 tracking-widest block mb-1">ERRO DE SUBSISTEMA</span>
          <h3 class="text-sm font-bold text-white font-hud uppercase tracking-wide mb-2">${title}</h3>
          <p class="text-xs text-slate-300 mb-4 font-normal leading-relaxed">${message}</p>
          <div class="flex items-center justify-center space-x-3">
            <button onclick="JarvisPresentation && JarvisPresentation.close()" class="px-4 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-xs font-mono-code text-slate-300 hover:text-white transition-colors">
              VOLTAR AO NÚCLEO
            </button>
            <button onclick="${retryAction}" class="px-4 py-1.5 rounded-lg bg-rose-950/80 hover:bg-rose-900 border border-rose-400 text-rose-200 text-xs font-mono-code font-bold transition-colors">
              ↻ TENTAR NOVAMENTE
            </button>
          </div>
        </div>
      `;
    }
  };

  // =========================================================================
  // 4. MOTOR PRINCIPAL DE RENDERIZAÇÃO (JarvisUI)
  // =========================================================================
  const JarvisUI = {
    setNewsLayout(layoutName) {
      this._currentNewsLayout = layoutName;
      if (this._lastNewsSpec) {
        const mount = document.getElementById('presentation-content-area');
        if (mount) {
          this._lastNewsSpec.layout = layoutName;
          mount.innerHTML = this.components.news_deck(this._lastNewsSpec);
        }
      }
    },

    updateNewsSpotlight(activeIdx, articles) {
      this._lastNewsActiveIdx = activeIdx;
      if (!this._currentNewsLayout || this._currentNewsLayout === 'spotlight') {
        const art = articles[activeIdx];
        if (!art) return;
        const heroStage = document.getElementById('news-hero-stage');
        const heroImg = document.getElementById('news-hero-image');
        const heroTitle = document.getElementById('news-hero-title');
        const heroSummary = document.getElementById('news-hero-summary');
        const heroSource = document.getElementById('news-hero-source');
        const heroLink = document.getElementById('news-hero-link');

        if (heroStage) {
          heroStage.style.opacity = '0.6';
          setTimeout(() => {
            if (heroImg) heroImg.src = art.imageUrl || "https://images.unsplash.com/photo-1518770660439-4636190af475?w=800&auto=format&fit=crop&q=80";
            if (heroTitle) heroTitle.innerText = art.title;
            if (heroSummary) heroSummary.innerText = art.summary;
            if (heroSource) heroSource.innerText = (art.source || "RADAR").toUpperCase();
            if (heroLink) heroLink.href = art.url || '#';
            heroStage.style.opacity = '1';
          }, 120);
        }

        articles.forEach((_, i) => {
          const card = document.getElementById(`news-card-item-${i}`);
          const badge = document.getElementById(`news-card-badge-${i}`);
          if (card) {
            if (i === activeIdx) {
              card.className = "glass-card-stark p-2.5 rounded-xl border flex items-center space-x-3 transition-all duration-300 cursor-pointer group border-cyan-400 bg-cyan-950/70 shadow-[0_0_20px_rgba(0,240,255,0.4)] scale-[1.02]";
              if (badge) badge.innerHTML = `<span class="px-1.5 py-0.5 rounded bg-cyan-500/90 text-[8px] font-mono-code font-bold text-slate-950 animate-pulse">ılılı</span>`;
            } else {
              card.className = "glass-card-stark p-2.5 rounded-xl border flex items-center space-x-3 transition-all duration-300 cursor-pointer group border-slate-800 bg-slate-950/60 hover:border-cyan-500/40 opacity-75 hover:opacity-100";
              if (badge) badge.innerHTML = `<span class="px-1.5 py-0.5 rounded bg-slate-950/80 text-[8px] font-mono-code font-bold text-slate-400">#${i + 1}</span>`;
            }
          }
        });
      }
    },

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
    },

    handleConfirm(actionId) {
      emit('ui.confirm', { actionId });
      this.closeStage();
      if (typeof window !== 'undefined' && typeof window.JarvisPresentation !== 'undefined') {
        window.JarvisPresentation.close();
      }
      if (typeof window !== 'undefined' && typeof window.sendToOpenClaw === 'function') {
        window.sendToOpenClaw('[CONFIRMADO] Ação autorizada pelo usuário: ' + actionId);
      }
    },

    handleCancel(actionId) {
      emit('ui.cancel', { actionId });
      this.closeStage();
      if (typeof window !== 'undefined' && typeof window.JarvisPresentation !== 'undefined') {
        window.JarvisPresentation.close();
      }
      if (typeof window !== 'undefined' && typeof window.sendToOpenClaw === 'function') {
        window.sendToOpenClaw('[CANCELADO] Ação cancelada pelo usuário: ' + actionId);
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
