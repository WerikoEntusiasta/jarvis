# Voz da esfera J.A.R.V.I.S.

## Segurança da conexão direta

A ponte da esfera usa WSS com TLS e uma prova HMAC-SHA256 por dispositivo. O servidor não abre a porta 8095 se faltarem o certificado TLS, a chave privada ou os tokens. O token da esfera nunca é enviado pela rede: o firmware assina um desafio aleatório de uso único. O certificado TLS precisa ser confiável para o host configurado no firmware (incluindo o IP ou domínio no SAN).

1. O certificado local fica em `sphere-tls/fullchain.pem` e a chave privada em `sphere-tls/privkey.pem`. O certificado é confiado pela CA embutida no firmware e é válido para o IP público configurado.
2. `sphere-runtime.env` guarda o token de dispositivo como JSON; mantenha-o fora do Git e restrinja a leitura no servidor.
3. `firmware_jarvis_custom/include/jarvis_sphere_secrets.h` contém o mesmo token e a CA confiável. Esse arquivo é local e ignorado pelo Git.
4. Se o IP público mudar, será necessário renovar o certificado e o host no firmware.

Sem esses quatro passos, a ponte permanece desativada. Não use `setInsecure()` nem publique o token do OpenClaw no firmware.

## Voz, wake word e processamento

- A esfera filtra silêncio localmente e envia um pré-áudio curto junto com trechos de fala; os blocos recebidos ficam em memória e não são gravados.
- O OpenWakeWord procura a palavra de ativação e o Silero VAD detecta o fim da frase com cerca de 700 ms de silêncio. Se os modelos estiverem ausentes, o wake word fecha a entrada por segurança.
- O reconhecedor local/container usa `base` e `int8` por padrão. O áudio não é encaminhado ao OpenClaw: apenas a transcrição resultante segue para o agente.
- Hora, clima, timer e alarme são atendidos por rotas determinísticas antes do OpenClaw.
- Para habilitar resposta em streaming, configure `SPHERE_OPENCLAW_STREAM_URL` para o endpoint privado `/v1` e `SPHERE_OPENCLAW_STREAM_TOKEN` no servidor. No Gateway, habilite Chat Completions antes. Esse token concede autoridade de operador do OpenClaw; mantenha o endpoint só no tráfego privado entre contêineres e nunca o coloque na esfera.
- Uma frase personalizada apenas “Jarvis” precisa de um modelo `.onnx` treinado e validado com exemplos positivos e negativos. Até existir, `hey_jarvis` é o modelo padrão e pode exigir “Hey Jarvis”. Configure o caminho com `SPHERE_WAKEWORD_MODEL`.

## Limites atuais do firmware

O envio condicionado à fala reduz tráfego ocioso, mas ainda transmite PCM durante a fala; ainda não é Opus nem detecção semântica “Jarvis” no ESP32. Interrupção com AEC também não está habilitada: o firmware atual usa Arduino e não alimenta o AFE do ESP-SR com a referência de reprodução necessária. Não remover o bloqueio do microfone durante TTS sem AEC, pois isso faria o áudio da própria resposta voltar como comando.
