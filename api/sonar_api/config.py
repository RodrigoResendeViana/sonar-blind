from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuração lida das variáveis de ambiente com prefixo SONAR_.

    Em produção, o deploy.sh gera essas variáveis a partir do AWS Parameter Store.
    Nenhum segredo tem valor padrão aqui.
    """

    model_config = SettingsConfigDict(env_prefix="SONAR_", extra="ignore")

    database_url: str = "sqlite+pysqlite:///./sonar.db"

    olhovivo_token: str = ""
    olhovivo_url: str = "https://api.olhovivo.sptrans.com.br/v2.1"
    olhovivo_cache_s: int = 30

    mqtt_host: str = ""
    mqtt_port: int = 1883
    mqtt_usuario: str = "sonar-api"
    mqtt_senha: str = ""
    mqtt_tls: bool = False

    ia_url: str = ""
    ia_timeout_s: float = 20.0

    # gatilho do robô de RPA (n8n): avisado na hora em que o passageiro consente a reclamação
    rpa_webhook_url: str = ""

    token_servico: str = ""
    sal_hash: str = ""

    paradas_arquivo: str = ""
    simuladores: bool = True

    # planejador de viagem: GTFS da SPTrans (zip) para as linhas reais; sem ele, só a rede de demonstração
    gtfs_arquivo: str = ""
    # destino falado → coordenadas (OpenStreetMap), só para a rede real; vazio desliga
    geocodificador_url: str = "https://nominatim.openstreetmap.org"

    aviso_minutos: int = 4
    espera_minutos: int = 45
    demo_velocidade: float = 1.0
    monitor_intervalo_s: float = 5.0
    limite_por_minuto: int = 30
