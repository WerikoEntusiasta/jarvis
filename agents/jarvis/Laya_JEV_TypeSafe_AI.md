# Arquitetura JEV & Laya (TypeSafe AI) — Guia Técnico e Integração

## 1. Visão Geral
* **O que é o JEV:** Motor de "Sistema 1" desenvolvido pela TypeSafe AI, focado em decisões não-autorregressivas, estritamente tipadas e com pontuação de confiança calibrada.
* **O que é o Laya:** Implementação open-source compatível com a API do JEV (`/v1/systemone`), capaz de avaliar intenções e decisões tipadas em ~33 ms (CPU/GPU) sem gerar texto livre em prosa.
* **Ferramenta de Servidor:** `ollaya` (gerenciador local no estilo Ollama, servindo modelos de decisão via REST).

---

## 2. Papel no Ecossistema de Agentes
1. **Triagem Ultrarrápida (Sistema 1):** Classifica em milissegundos a intenção da mensagem (Agendamento/Lúcia, Tráfego/AdPilot, Design/Designer, Operações/JARVIS).
2. **JEV Guard (Auditoria de Saída):** Intercepta saídas de modelos generativos antes do disparo externo, conferindo fidelidade factual e parâmetros de contrato.
3. **Ponte com o 9Router (Sistema 2):** O Laya entrega a intenção estruturada e limpa ao 9Router, reduzindo o consumo de tokens de raciocínio e eliminando ambiguidades.

---

## 3. Diretrizes Técnicas no Host ZimaOS
* **Processador:** Intel Core i5-2400 (x86_64, suporte a AVX / SSE4.2).
* **Compilação Padrão do ONNX Runtime:** Binários genéricos com exigência de AVX2 apresentam erro de instrução ilegal no Core i5-2400.
* **Solução Homologada:** 
  1. Execução via build personalizada do ONNX Runtime com suporte a AVX/SSE; ou
  2. Execução da inferência acelerada na máquina física Windows (NVIDIA GTX 1660 Ti via CUDA/AVX2) com fallback transparente para o 9Router.
* **Isolamento de Disco:** Instalação e dados restritos ao volume `/DATA/AppData/ollaya`, preservando a partição raiz e os 40 containers ativos.

---

*Documento gerado por J.A.R.V.I.S. para o Senhor Werik — 03/10/2026.*
