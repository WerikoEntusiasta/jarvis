// Testes dos builders de card do J.A.R.V.I.S. (roda: node tests/test_cards.js)
// Valida text/news/weather/chart sem depender de browser.
"use strict";
const path = require("path");
const assert = require("assert");

// O engine e UMD; em Node ele exporta via module.exports
const engine = require(path.join(__dirname, "..", "web", "jarvis_presentation_engine.js"));
const T = engine._test;
assert.ok(T, "engine._test ausente - builders nao expostos");

let pass = 0, fail = 0;
function check(nome, fn) {
  try { fn(); pass++; console.log("  OK  " + nome); }
  catch (e) { fail++; console.log("FAIL  " + nome + " -> " + e.message); }
}

// ---------------------------------------------------------------- text card
check("text: renderiza resposta + botao copiar", () => {
  const b = T.buildTextCard(
    { copy_text: "A Selic esta em 12,75%.", content: "A Selic esta em 12,75%." }, "");
  assert.ok(b, "builder retornou null");
  assert.ok(b.html.includes("spatial-copy-btn"), "sem botao copiar");
  assert.ok(b.html.includes("12,75%"), "texto ausente");
  assert.strictEqual(b.mount(), null);
});

check("text: sem conteudo retorna null", () => {
  assert.strictEqual(T.buildTextCard({ content: "" }, ""), null);
  assert.strictEqual(T.buildTextCard({}, undefined), null);
});

check("text: escapa HTML perigoso", () => {
  const b = T.buildTextCard({ content: '<script>alert(1)</script>' }, "");
  assert.ok(!b.html.includes("<script>"), "HTML nao escapado");
  assert.ok(b.html.includes("&lt;script&gt;"), "escape ausente");
});

// -------------------------------------------------------------- news card
const newsItems = [
  { title: "IA brasileira avanca", link: "https://x.com/a", source: "G1",
    published: "Thu, 13 Nov 2026 10:00:00 GMT", summary: "Resumo da manchete.", image: "https://img/1.jpg" },
  { title: "Segunda manchete", link: "https://x.com/b", source: "UOL", summary: "" },
  { title: "Terceira manchete", link: "https://x.com/c", source: "Folha", summary: "" },
];

check("news: lead com imagem + lista", () => {
  const b = T.buildNewsCard({ items: newsItems }, "");
  assert.ok(b, "builder retornou null");
  assert.ok(b.html.includes("spatial-news-lead"), "sem lead");
  assert.ok(b.html.includes("spatial-news-lead-cover"), "sem capa fallback");
  assert.ok(b.html.includes("https://img/1.jpg"), "sem imagem");
  assert.ok(b.html.includes("Segunda manchete"), "sem lista");
  assert.ok(b.html.includes("Terceira manchete"), "lista incompleta");
  assert.ok(b.html.includes('target="_blank"'), "links nao abrem em nova aba");
});

check("news: SEM imagem no lead -> capa 📰 visivel", () => {
  const semImg = newsItems.map(i => ({ ...i, image: "" }));
  const b = T.buildNewsCard({ items: semImg }, "");
  assert.ok(b.html.includes("spatial-news-lead-cover"), "capa ausente");
  assert.ok(b.html.includes("📰"), "glyph ausente");
  // nao pode haver <img> vazio apontando pra ''
  assert.ok(!b.html.includes('class="spatial-news-lead-img" src=""'),
            "img vazia renderizada");
  // lead-texto continua presente
  assert.ok(b.html.includes("IA brasileira avanca"), "titulo lead sumiu");
});

check("news: sem itens retorna null", () => {
  assert.strictEqual(T.buildNewsCard({ items: [] }, ""), null);
  assert.strictEqual(T.buildNewsCard({}, {}), null);
});

check("news: le items do content dict (validador cru)", () => {
  const b = T.buildNewsCard({}, { items: newsItems.slice(0, 1) });
  assert.ok(b && b.html.includes("IA brasileira"), "nao leu content.items");
});

// ------------------------------------------------------------ weather card
const days = [
  { date: "2026-11-13", weekday: "sex", description: "Tempestade", emoji: "⛈️",
    temp_max: 26, temp_min: 17, rain_prob: 100 },
  { date: "2026-11-14", weekday: "sáb", description: "Encoberto", emoji: "☁️",
    temp_max: 27, temp_min: 18, rain_prob: 24 },
];

check("weather: hero + faixa de dias", () => {
  const b = T.buildWeatherCard({ city: "Catanduva", days }, "");
  assert.ok(b, "builder retornou null");
  assert.ok(b.html.includes("spatial-weather-hero"), "sem hero");
  assert.ok(b.html.includes("spatial-weather-strip"), "sem faixa");
  assert.ok(b.html.includes("Catanduva"), "sem cidade");
  assert.ok(b.html.includes("100%") || b.html.includes("💧"), "sem chuva");
  assert.ok(b.html.includes("26"), "sem temperatura");
});

check("weather: sem dias retorna null", () => {
  assert.strictEqual(T.buildWeatherCard({ days: [] }, ""), null);
});

check("weather: tolera dias sem campos (null)", () => {
  const b = T.buildWeatherCard({ days: [{ date: "2026-11-13" }] }, "");
  assert.ok(b, "nao tolerou campos ausentes");
  assert.ok(b.html.includes("--"), "sem placeholder de temp");
});

// -------------------------------------------------- buildCardContent (tipos)
check("content: type=text monta corpo", () => {
  const b = T.buildCardContent("text", { title: "T", content: "Resposta aqui.", copy_text: "Resposta aqui." });
  assert.ok(b.html.includes("spatial-copy-btn"), "sem copiar");
});

check("content: type=news monta lead", () => {
  const b = T.buildCardContent("news", { title: "T", items: newsItems });
  assert.ok(b.html.includes("spatial-news-lead"), "sem lead");
});

check("content: type=weather monta hero", () => {
  const b = T.buildCardContent("weather", { title: "T", city: "SP", days });
  assert.ok(b.html.includes("spatial-weather-hero"), "sem hero");
});

check("content: chart sem dado invalido -> placeholder (sem card vazio)", () => {
  const b = T.buildCardContent("chart", { title: "T", data: { lixo: 1 } });
  assert.ok(b.html.includes("spatial-chart-empty") || b.html.includes("spatial-empty-fallback"),
    "sem placeholder");
});

check("content: card sem NADA cai no placeholder anti-vazio", () => {
  const b = T.buildCardContent("hologram_card", { title: "T" });
  assert.ok(b.html.includes("spatial-empty-fallback"), "card vazio sem placeholder");
});

// ------------------------------------------------------- normalizador chart
check("chart: line real do log -> ECharts valido", () => {
  const r = T.normalizeChartOptions({
    chart_type: "line",
    categories: ["06h", "09h"],
    series: [{ name: "T", data: [22, 25] }],
  });
  assert.ok(r, "normalizador retornou null");
  assert.strictEqual(r.series[0].type, "line");
  assert.strictEqual(r.xAxis.data.length, 2);
});

check("chart: opcao invalida -> null", () => {
  assert.strictEqual(T.normalizeChartOptions({}), null);
  assert.strictEqual(T.normalizeChartOptions(null), null);
});

// ------------------------------------------------------------ whatsapp card
const waMsgs = [
  { name: "Werik ( Pessoal )", unread: 2, label: "Bom dia, JARVIS!",
    ts: "13/11 10:00", session: "Businees", role: "comercial",
    chat_id: "5517991951381@c.us" },
  { name: "Thiago", unread: 1, label: "🎤 áudio", ts: "13/11 09:30",
    session: "jarvis", role: "pessoal", chat_id: "551199999@c.us" },
];

check("whatsapp: header com total + mensagens + input resposta", () => {
  const b = T.buildWhatsappCard({ messages: waMsgs, total_unread: 3, role: "comercial" }, "");
  assert.ok(b, "builder retornou null");
  assert.ok(b.html.includes("spatial-wa-header"), "sem header");
  assert.ok(b.html.includes("3 não lidas"), "sem total");
  assert.ok(b.html.includes("Werik"), "sem remetente");
  assert.ok(b.html.includes("Bom dia"), "sem texto");
  assert.ok(b.html.includes("spatial-wa-reply-input"), "sem input de resposta");
  assert.ok(b.html.includes("/api/whatsapp/reply") === false, "input nao expoe endpoint inline");
  assert.ok(b.html.includes("JarvisWhatsApp.send"), "sem acao de envio");
});

check("whatsapp: sem mensagens -> estado vazio amigavel", () => {
  const b = T.buildWhatsappCard({ messages: [], total_unread: 0 }, "");
  assert.ok(b.html.includes("Nenhuma mensagem"), "sem mensagem de vazio");
});

check("whatsapp: injeta via buildCardContent", () => {
  const b = T.buildCardContent("whatsapp", { messages: waMsgs, total_unread: 3 });
  assert.ok(b.html.includes("spatial-wa-msg"), "sem itens de mensagem");
});

check("whatsapp: chat_id malicioso e sanitizado", () => {
  const b = T.buildWhatsappCard({ messages: [{
    name: "X", unread: 1, label: "y",
    chat_id: "abc'); alert(1); ('x"
  }] }, "");
  assert.ok(!b.html.includes("alert(1)"), "chat_id nao sanitizado");
});

// ------------------------------------------------------------ regressao compose
check("compose: components dict do backend nao quebra (fonte)", () => {
  // O backend manda components={} (dict). `|| []` nao protege porque objeto
  // e truthy -> "comps.forEach is not a function" no handler SSE.
  const fs = require("fs");
  const src = fs.readFileSync(
    require("path").join(__dirname, "..", "web", "jarvis_presentation_engine.js"),
    "utf8");
  assert.ok(
    /Array\.isArray\(payload\s*&&\s*payload\.components\)/.test(src),
    "compose precisa checar Array.isArray(payload.components)");
  assert.ok(!/const comps = payload\.components \|\| \[\]/.test(src),
            "guard antigo (|| []) voltou");
});

// ------------------------------------------- manipulacao de cards (DOM fake)
function fakeDom() {
  const classes = new Set();
  return {
    style: {},
    dataset: {},
    classList: {
      add: (...cs) => cs.forEach(c => classes.add(c)),
      remove: (...cs) => cs.forEach(c => classes.delete(c)),
      contains: c => classes.has(c),
      toggle: c => (classes.has(c) ? classes.delete(c) : classes.add(c))
    },
    querySelector: () => null,
    _classes: classes
  };
}

function seedRecord(id, overrides) {
  const dom = fakeDom();
  const rec = Object.assign({
    dom,
    type: "annotation",
    position: { x: 10, y: 10, width: 30, height: 30 },
    props: { title: id },
    mountResult: null,
    state: "visible",
    group: null
  }, overrides || {});
  T.state.components.set(id, rec);
  T.state.groups = {};
  return rec;
}

check("mover: aplica left/top/width/height/zIndex (geometria completa)", () => {
  T.state.components.clear();
  const rec = seedRecord("m1");
  const ok = engine.updateSpatialComponent("m1", {
    position: { x: 50, y: 25, width: 40, height: 45, zIndex: 7 }
  }, false);
  assert.ok(ok, "update retornou false");
  assert.strictEqual(rec.dom.style.left, "50%");
  assert.strictEqual(rec.dom.style.top, "25%");
  assert.strictEqual(rec.dom.style.width, "40%");
  assert.strictEqual(rec.dom.style.height, "45%",
                     "height nao aplicado (resize vertical quebrado)");
  assert.strictEqual(rec.dom.style.zIndex, 7, "zIndex nao aplicado");
});

check("z-index parcial: so zIndex, NAO teleporta o card", () => {
  T.state.components.clear();
  const rec = seedRecord("z1");
  rec.dom.style.left = "10%";
  engine.updateSpatialComponent("z1", { position: { zIndex: 9 } }, false);
  assert.strictEqual(rec.dom.style.zIndex, 9);
  assert.strictEqual(rec.dom.style.left, "10%",
                     "card teleportou ao mudar z-index");
  assert.strictEqual(rec.position.zIndex, 9, "position nao registrou zIndex");
});

check("minimizar: classe de estado aplicada/removida", () => {
  T.state.components.clear();
  const rec = seedRecord("n1");
  engine.updateSpatialComponent("n1", { state: "minimized" }, false);
  assert.ok(rec.dom.classList.contains("spatial-state-minimized"),
            "sem classe minimized");
  assert.strictEqual(rec.state, "minimized");
  // restaura
  engine.updateSpatialComponent("n1", { state: "visible" }, false);
  assert.ok(!rec.dom.classList.contains("spatial-state-minimized"),
            "classe nao removida ao restaurar");
});

check("expand: classe + zIndex do payload", () => {
  T.state.components.clear();
  const rec = seedRecord("e1");
  engine.updateSpatialComponent("e1", {
    state: "expanded",
    position: { x: 12, y: 8, width: 76, height: 78, zIndex: 20 }
  }, false);
  assert.ok(rec.dom.classList.contains("spatial-state-expanded"));
  assert.strictEqual(rec.dom.style.zIndex, 20);
  assert.strictEqual(rec.dom.style.width, "76%");
});

check("agrupar: classe visual + registro + rotulo data-group", () => {
  T.state.components.clear();
  const a = seedRecord("ga");
  engine.updateSpatialComponent("ga", { group: "marketing" }, false);
  assert.ok(a.dom.classList.contains("spatial-grouped"));
  assert.strictEqual(a.dom.dataset.group, "marketing");
  assert.deepStrictEqual(T.state.groups["marketing"], ["ga"]);
  // separar
  engine.updateSpatialComponent("ga", { group: null }, false);
  assert.ok(!a.dom.classList.contains("spatial-grouped"));
  assert.ok(!("marketing" in T.state.groups) ||
            !T.state.groups["marketing"].includes("ga"));
});

check("sincronia: mover 1 card do grupo move os pares (delta %)", () => {
  T.state.components.clear();
  const a = seedRecord("s1");
  const b = seedRecord("s2");
  engine.updateSpatialComponent("s1", { group: "g1" }, false);
  engine.updateSpatialComponent("s2", { group: "g1" }, false);
  // s1 em (10,10); s2 em (10,10). Move s1 para (40,30) -> dx=30, dy=20
  engine.updateSpatialComponent("s1", { position: { x: 40, y: 30 } }, false);
  assert.strictEqual(a.position.x, 40);
  assert.strictEqual(b.position.x, 40, "par nao acompanhou o movimento em X");
  assert.strictEqual(b.position.y, 30, "par nao acompanhou o movimento em Y");
  assert.strictEqual(b.dom.style.left, "40%");
  assert.strictEqual(b.dom.style.top, "30%");
});

check("re-render so acontece quando props mudam", () => {
  T.state.components.clear();
  const rec = seedRecord("r1", { props: { title: "antes", content: "x" } });
  engine.updateSpatialComponent("r1", { position: { x: 20, y: 20 } }, false);
  assert.strictEqual(rec.props.title, "antes");
  engine.updateSpatialComponent(
    "r1", { props: { title: "depois" } }, false);
  assert.strictEqual(rec.props.title, "depois");
});

check("fonte: CSS de estados + grupos presentes", () => {
  const fs = require("fs");
  const src = fs.readFileSync(
    require("path").join(__dirname, "..", "web", "jarvis_presentation_engine.js"),
    "utf8");
  for (const marca of [
    "spatial-state-expanded",
    "spatial-state-minimized",
    "spatial-state-focused",
    "spatial-grouped",
    "content: attr(data-group)"
  ]) {
    assert.ok(src.includes(marca), `CSS/fonte sem: ${marca}`);
  }
  // minimizado esconde o corpo
  assert.ok(/spatial-state-minimized[\s\S]{0,200}spatial-card-body\s*\{\s*display:\s*none/
    .test(src), "minimized nao esconde o body");
});

console.log("\n" + pass + " passaram, " + fail + " falharam");
process.exit(fail ? 1 : 0);
