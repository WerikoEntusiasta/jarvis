// Copie para jarvis_sphere_secrets.h (ignorado pelo Git) na máquina de build.
// Use o mesmo token de dispositivo configurado no .env do servidor.
// O certificado deve ser a CA que assina o certificado TLS usado pela esfera.
#define JARVIS_SPHERE_DEVICE_TOKEN "SUBSTITUA_POR_UM_TOKEN_ALEATORIO_DE_64_HEX"
static const char kJarvisSphereTlsCaPem[] = R"JARVIS_CA(
-----BEGIN CERTIFICATE-----
COLE_AQUI_O_CERTIFICADO_CA_CONFIAVEL
-----END CERTIFICATE-----
)JARVIS_CA";
#define JARVIS_SPHERE_TLS_CA_PEM kJarvisSphereTlsCaPem
#define JARVIS_SPHERE_SERVER_HOST "SEU_IP_OU_DOMINIO"
#define JARVIS_SPHERE_WIFI_SSID "SEU_WIFI_SSID"
#define JARVIS_SPHERE_WIFI_PASS "SUA_SENHA_WIFI"
