"""Métricas Prometheus: os quatro sinais de ouro mais os indicadores do Sonar."""

from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUISICOES = Counter(
    "sonar_http_requisicoes_total", "Requisições HTTP atendidas pela API", ["metodo", "rota", "status"]
)
HTTP_LATENCIA = Histogram(
    "sonar_http_latencia_segundos",
    "Latência das requisições HTTP (sem os streams SSE)",
    ["metodo", "rota"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
HTTP_EM_ANDAMENTO = Gauge("sonar_http_em_andamento", "Requisições HTTP em andamento")
SSE_CONEXOES = Gauge("sonar_sse_conexoes", "Conexões SSE abertas")

OLHOVIVO_CONFIGURADO = Gauge("sonar_olhovivo_configurado", "1 se o token do Olho Vivo está configurado")
OLHOVIVO_DISPONIVEL = Gauge("sonar_olhovivo_disponivel", "1 se a última consulta ao Olho Vivo deu certo")
OLHOVIVO_REQUISICOES = Counter(
    "sonar_olhovivo_requisicoes_total", "Consultas ao Olho Vivo", ["resultado"]
)
OLHOVIVO_LATENCIA = Histogram(
    "sonar_olhovivo_latencia_segundos", "Latência das consultas ao Olho Vivo", buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10)
)

MQTT_CONECTADO = Gauge("sonar_mqtt_conectado", "1 se a API está conectada ao broker MQTT")

DISPOSITIVO_ONLINE = Gauge("sonar_dispositivo_online", "1 se o dispositivo está online", ["tipo", "id"])
DISPOSITIVO_ULTIMO_SINAL = Gauge(
    "sonar_dispositivo_ultimo_sinal_timestamp_segundos", "Horário (Unix) do último sinal de vida", ["tipo", "id"]
)

ESPERAS_ATIVAS = Gauge("sonar_esperas_ativas", "Esperas em andamento")
ESPERAS_CRIADAS = Counter("sonar_esperas_criadas_total", "Esperas criadas", ["demo"])
AVISOS_ENVIADOS = Counter("sonar_avisos_enviados_total", "Avisos enviados ao Sonar Bordo")
AVISOS_CIENTES = Counter("sonar_avisos_ciente_total", "Avisos confirmados pelo motorista")
EMBARQUES = Counter("sonar_embarques_total", "Embarques confirmados", ["validado_por_camera"])
OCORRENCIAS = Counter("sonar_ocorrencias_total", "Ônibus que não pararam", ["consentimento"])

IA_LATENCIA = Histogram(
    "sonar_ia_latencia_segundos", "Latência das respostas da IA", ["modo"], buckets=(0.1, 0.5, 1, 2, 4, 8, 15, 30)
)
PEDIDOS_BOTAO = Counter("sonar_botao_pedidos_total", "Pedidos feitos pelo botão físico do Sonar Ponto")
VIAGENS_PLANEJADAS = Counter("sonar_viagens_planejadas_total", "Viagens planejadas por voz", ["rede", "resultado"])
RPA_AVISOS = Counter("sonar_rpa_avisos_total", "Avisos da API ao robô de RPA (webhook)", ["resultado"])
IA_RESPOSTAS = Counter("sonar_ia_respostas_total", "Respostas da IA por status", ["modo", "status"])
