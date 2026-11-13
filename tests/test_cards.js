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

console.log("\n" + pass + " passaram, " + fail + " falharam");
process.exit(fail ? 1 : 0);
