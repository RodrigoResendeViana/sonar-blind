// Cliente da API Sonar. Mesma origem: o Caddy publica a API em /api.

export type StatusEspera = 'aguardando' | 'embarcou' | 'nao_parou' | 'cancelada' | 'expirada'

export interface Linha {
  codigo: string
  destino: string
}

export interface Parada {
  id: string
  nome: string
  codigo_sptrans: number | null
  lat: number | null
  lon: number | null
  demo: boolean
  linhas: Linha[]
}

export interface Espera {
  id: string
  parada_id: string
  parada_nome: string
  linhas: string[]
  status: StatusEspera
  demo: boolean
  criado_em: string
  expira_em: string
  previsao: { linha: string; destino: string; prefixo: string; minutos: number } | null
  aviso: { enviado_em: string; prefixo: string; linha: string; ciente_em: string | null } | null
  passagem: { em: string; linha: string; confianca: number; tempo_parado_s: number; parou: boolean } | null
  embarque: { em: string; origem: string; validado_por_camera: boolean } | null
  ocorrencia: { id: number; status: string; protocolo: string | null; consentimento: boolean } | null
}

export interface EventoEspera {
  id?: number
  tipo: string
  fala?: string | null
  dados?: Record<string, unknown>
  em?: string
}

export interface RespostaIA {
  status: 'ok' | 'nao_consta'
  resposta_falada: string
  acao: { tipo: string; parada_id?: string; linhas?: string[] } | null
  fontes: string[]
  confianca: number
}

export interface TrechoPlano {
  linha: string
  sentido: string
  embarque: { id: string; nome: string; lat: number; lon: number }
  desembarque: { id: string; nome: string; lat: number; lon: number }
  paradas: number
  minutos: number
}

export interface PlanoViagem {
  trechos: TrechoPlano[]
  caminhada_inicio_m: number
  caminhada_fim_m: number
  minutos_estimados: number
  baldeacoes: number
}

export type EstadoConversa =
  | 'inicio'
  | 'confirmar_plano'
  | 'indo_ao_ponto'
  | 'no_ponto'
  | 'apos_ocorrencia'
  | 'a_bordo'
  | 'chegou'

export interface RespostaConversa {
  sessao: string
  estado: EstadoConversa
  fala: string
  espera_id: string | null
  plano: PlanoViagem | null
  trecho: number
  destino: string | null
  demo: boolean
  acompanhar: boolean
  intervalo_s: number
  pedir_localizacao?: boolean
  repetir_texto?: string
}

export type CenarioDemo = 'auto' | 'embarque' | 'nao_parou' | 'maquete'

export interface PedidoConversa {
  sessao: string | null
  evento: 'abrir' | 'fala' | 'posicao' | 'tick'
  texto?: string
  lat?: number
  lon?: number
  cenario_demo?: CenarioDemo
}

export interface Indicadores {
  esperas: number
  avisos_enviados: number
  avisos_ciente: number
  taxa_ciente: number | null
  embarques: number
  embarques_validados_camera: number
  nao_parou: number
  nao_parou_por_100_esperas: number | null
  tempo_medio_espera_min: number | null
  ocorrencias_por_status: Record<string, number>
  por_linha: { linha: string; esperas?: number; avisos?: number; cientes?: number; embarques?: number; nao_parou?: number }[]
  dispositivos: { tipo: string; id: string; online: boolean; ultimo_sinal_em: string }[]
  gerado_em: string
}

export class ErroApi extends Error {
  constructor(
    public readonly status: number,
    mensagem: string,
  ) {
    super(mensagem)
  }
}

const BASE: string = import.meta.env.VITE_API_BASE ?? '/api'
const CHAVE_USUARIO = 'sonar.usuario'

/** Identificador anônimo deste aparelho. A API guarda só o hash dele. */
export function idUsuario(): string {
  try {
    let id = localStorage.getItem(CHAVE_USUARIO)
    if (!id) {
      id = crypto.randomUUID()
      localStorage.setItem(CHAVE_USUARIO, id)
    }
    return id
  } catch {
    return 'sem-armazenamento'
  }
}

async function chamar<T>(caminho: string, init: RequestInit = {}): Promise<T> {
  const resposta = await fetch(BASE + caminho, {
    ...init,
    headers: { 'Content-Type': 'application/json', 'X-Sonar-Usuario': idUsuario(), ...(init.headers ?? {}) },
  })
  if (!resposta.ok) {
    let detalhe = `Erro ${resposta.status}`
    try {
      const corpo: unknown = await resposta.json()
      if (corpo && typeof corpo === 'object' && 'detail' in corpo && typeof corpo.detail === 'string') {
        detalhe = corpo.detail
      }
    } catch {
      // resposta sem corpo JSON
    }
    throw new ErroApi(resposta.status, detalhe)
  }
  return (await resposta.json()) as T
}

const post = <T>(caminho: string, corpo: unknown = {}) =>
  chamar<T>(caminho, { method: 'POST', body: JSON.stringify(corpo) })

export const api = {
  conversar: (pedido: PedidoConversa) => post<RespostaConversa>('/conversa', pedido),
  botao: (paradaId: string) => post<{ espera: Espera | null }>(`/simulador/paradas/${paradaId}/botao`),
  paradas: () => chamar<Parada[]>('/paradas'),
  paradaProxima: (lat: number, lon: number) =>
    chamar<{ parada: Parada; distancia_m: number }>(`/paradas/proxima?lat=${lat}&lon=${lon}`),
  perguntar: (texto: string, parada_id: string | null) => post<RespostaIA>('/ia/perguntar', { texto, parada_id }),
  criarEspera: (corpo: { parada_id: string; linhas: string[]; origem: 'voz' | 'toque'; lat?: number; lon?: number }) =>
    post<Espera>('/esperas', corpo),
  iniciarDemo: (cenario: 'embarque' | 'nao_parou' | 'maquete') => post<Espera>('/demo/esperas', { cenario }),
  espera: (id: string) => chamar<Espera>(`/esperas/${id}`),
  embarque: (id: string, origem: 'voz' | 'toque') => post<Espera>(`/esperas/${id}/embarque`, { origem }),
  naoParou: (id: string, consentimento: boolean) => post<Espera>(`/esperas/${id}/nao-parou`, { consentimento }),
  cancelar: (id: string) => post<Espera>(`/esperas/${id}/cancelar`),
  localizar: (id: string) => post<Espera>(`/esperas/${id}/localizar`),
  indicadores: (incluirDemo: boolean) => chamar<Indicadores>(`/painel/indicadores?incluir_demo=${incluirDemo}`),
  deteccao: (
    paradaId: string,
    corpo: { linha_lida: string | null; confianca?: number; tempo_parado_s?: number; parou?: boolean; camera_ok?: boolean },
  ) => post<{ esperas_afetadas: number }>(`/simulador/paradas/${paradaId}/deteccao`, corpo),
  ciente: (prefixo: string, esperaId: string) =>
    post<{ registrado: boolean }>(`/simulador/onibus/${prefixo}/ciente`, { espera_id: esperaId }),
}

/** Abre um stream SSE. O navegador reconecta sozinho e manda o Last-Event-ID. */
export function ouvirEventos<T = EventoEspera>(caminho: string, aoReceber: (evento: T) => void, aoErro?: () => void) {
  const fonte = new EventSource(BASE + caminho)
  fonte.onmessage = (mensagem: MessageEvent<string>) => {
    try {
      aoReceber(JSON.parse(mensagem.data) as T)
    } catch {
      // mensagem fora do formato: ignora
    }
  }
  fonte.onerror = () => aoErro?.()
  return () => fonte.close()
}

export function mensagemDeErro(erro: unknown): string {
  if (erro instanceof ErroApi) {
    return erro.status === 429 ? 'Muitas tentativas seguidas. Espere um minuto e tente de novo.' : erro.message
  }
  return 'Sem conexão com o Sonar. Confira a internet e tente de novo.'
}
