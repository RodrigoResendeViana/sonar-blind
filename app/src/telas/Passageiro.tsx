import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'

import { useAnuncio } from '../anuncio'
import { api, mensagemDeErro, ouvirEventos, type Espera, type EventoEspera, type Parada, type RespostaIA } from '../api'
import { interpretarComando, type Comando } from '../comandos'
import { manterTelaLigada, ouvirFrase, reconhecimentoDisponivel, vibrar } from '../voz'

type Origem = 'voz' | 'toque'

const TERMINAIS = new Set(['embarcou', 'nao_parou', 'cancelada', 'expirada'])
const OCORRENCIA_FECHADA = new Set(['enviada', 'inconclusiva', 'duplicada', 'erro', 'anonima', 'descartada'])
const PEDEM_CONSENTIMENTO = new Set(['onibus_passou_direto', 'perguntar_parou'])
const ATUALIZAM_ESPERA = new Set([
  'embarque_confirmado',
  'ocorrencia_registrada',
  'ocorrencia_protocolo',
  'ocorrencia_inconclusiva',
  'cancelada',
  'expirada',
  'aviso_enviado',
  'motorista_ciente',
  'onibus_chegando',
  'onibus_passou_direto',
])

const RESUMO_FINAL: Record<string, string> = {
  embarcou: 'Embarque registrado. Boa viagem!',
  nao_parou: 'Você registrou que o ônibus não parou.',
  cancelada: 'Espera cancelada.',
  expirada: 'A espera terminou por tempo.',
}

function streamEncerrado(espera: Espera): boolean {
  if (!TERMINAIS.has(espera.status)) return false
  if (espera.status !== 'nao_parou') return true
  return !espera.ocorrencia || OCORRENCIA_FECHADA.has(espera.ocorrencia.status)
}

function hora(iso?: string): string {
  return iso ? new Date(iso).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }) : ''
}

export default function Passageiro() {
  const { anunciar, vozAlta, setVozAlta } = useAnuncio()
  const [paradas, setParadas] = useState<Parada[]>([])
  const [paradaId, setParadaId] = useState('demo')
  const [posicao, setPosicao] = useState<{ lat: number; lon: number } | null>(null)
  const [texto, setTexto] = useState('')
  const [resposta, setResposta] = useState<RespostaIA | null>(null)
  const [espera, setEspera] = useState<Espera | null>(null)
  const [historico, setHistorico] = useState<EventoEspera[]>([])
  const [status, setStatus] = useState('Diga ou digite a linha que você quer pegar.')
  const [pedirConsentimento, setPedirConsentimento] = useState(false)
  const [ocupado, setOcupado] = useState(false)
  const [ouvindo, setOuvindo] = useState(false)
  const temVoz = reconhecimentoDisponivel()
  const tituloEspera = useRef<HTMLHeadingElement>(null)
  const regiaoConsentimento = useRef<HTMLElement>(null)

  const dizer = useCallback(
    (fala: string) => {
      setStatus(fala)
      anunciar(fala)
    },
    [anunciar],
  )

  useEffect(() => {
    let ativo = true
    api
      .paradas()
      .then((lista) => {
        if (!ativo) return
        setParadas(lista)
        setParadaId((atual) => (lista.some((p) => p.id === atual) ? atual : (lista[0]?.id ?? atual)))
      })
      .catch(() => dizer('Não consegui carregar os pontos. Confira a internet.'))
    return () => {
      ativo = false
    }
  }, [dizer])

  const esperaId = espera?.id
  const aguardando = espera?.status === 'aguardando'

  // eventos da espera em tempo real (SSE)
  useEffect(() => {
    if (!esperaId) return
    let fechar = () => {}
    fechar = ouvirEventos(`/esperas/${esperaId}/eventos`, (evento) => {
      if (evento.tipo === 'estado') {
        setEspera(evento.dados as unknown as Espera)
        return
      }
      setHistorico((anterior) =>
        evento.id !== undefined && anterior.some((item) => item.id === evento.id) ? anterior : [...anterior, evento],
      )
      if (evento.fala) dizer(evento.fala)
      if (typeof evento.dados?.vibrar === 'string') vibrar(evento.dados.vibrar)
      if (PEDEM_CONSENTIMENTO.has(evento.tipo)) setPedirConsentimento(true)
      if (evento.tipo === 'previsao' && typeof evento.dados?.minutos === 'number') {
        const dados = evento.dados as unknown as NonNullable<Espera['previsao']>
        setEspera((atual) => (atual ? { ...atual, previsao: dados } : atual))
      }
      if (ATUALIZAM_ESPERA.has(evento.tipo)) {
        api
          .espera(esperaId)
          .then((atual) => {
            setEspera(atual)
            if (streamEncerrado(atual)) fechar()
          })
          .catch(() => {})
      }
    })
    return () => fechar()
  }, [esperaId, dizer])

  useEffect(() => (aguardando ? manterTelaLigada() : undefined), [aguardando])

  const statusEspera = espera?.status
  useEffect(() => {
    if (esperaId) tituloEspera.current?.focus()
  }, [esperaId, statusEspera])

  useEffect(() => {
    if (pedirConsentimento) regiaoConsentimento.current?.focus()
  }, [pedirConsentimento])

  async function executar<T>(acao: () => Promise<T>): Promise<T | undefined> {
    setOcupado(true)
    try {
      return await acao()
    } catch (erro) {
      dizer(mensagemDeErro(erro))
      return undefined
    } finally {
      setOcupado(false)
    }
  }

  async function comandar(comando: Comando, origem: Origem) {
    if (!espera) return
    if (comando === 'embarquei') {
      const atual = await executar(() => api.embarque(espera.id, origem))
      if (atual) setEspera(atual)
    } else if (comando === 'nao_parou') {
      setPedirConsentimento(true)
    } else if (comando === 'cancelar') {
      const atual = await executar(() => api.cancelar(espera.id))
      if (atual) setEspera(atual)
    } else {
      await executar(() => api.localizar(espera.id))
    }
  }

  async function perguntar(frase: string, origem: Origem) {
    const limpa = frase.trim()
    if (!limpa) return
    if (aguardando) {
      const comando = interpretarComando(limpa)
      if (comando) {
        await comandar(comando, origem)
        return
      }
    }
    const recebida = await executar(() => api.perguntar(limpa, paradaId))
    if (recebida) {
      setResposta(recebida)
      dizer(recebida.resposta_falada)
    }
  }

  async function falar() {
    setOuvindo(true)
    try {
      const frase = await ouvirFrase()
      setTexto(frase)
      if (frase) await perguntar(frase, 'voz')
      else dizer('Não ouvi nada. Tente de novo ou digite.')
    } catch {
      dizer('Não consegui ouvir. Tente de novo ou digite.')
    } finally {
      setOuvindo(false)
    }
  }

  function enviar(evento: FormEvent) {
    evento.preventDefault()
    void perguntar(texto, 'toque')
  }

  function usarLocalizacao() {
    if (!('geolocation' in navigator)) {
      dizer('Este aparelho não informa a localização. Escolha o ponto na lista.')
      return
    }
    navigator.geolocation.getCurrentPosition(
      async (local) => {
        const atual = { lat: local.coords.latitude, lon: local.coords.longitude }
        setPosicao(atual) // fica só na memória do app
        const proxima = await executar(() => api.paradaProxima(atual.lat, atual.lon))
        if (proxima) {
          setParadaId(proxima.parada.id)
          dizer(`Ponto mais perto: ${proxima.parada.nome}, a ${proxima.distancia_m} metros.`)
        }
      },
      () => dizer('Não consegui sua localização. Escolha o ponto na lista.'),
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 30000 },
    )
  }

  function comecar(nova: Espera) {
    setHistorico([])
    setPedirConsentimento(false)
    setResposta(null)
    setEspera(nova)
  }

  async function cheguei(linhas: string[], origem: Origem) {
    const nova = await executar(() =>
      api.criarEspera({ parada_id: paradaId, linhas, origem, ...(posicao ?? {}) }),
    )
    if (nova) comecar(nova)
  }

  async function demonstracao(cenario: 'embarque' | 'nao_parou' | 'maquete') {
    const nova = await executar(() => api.iniciarDemo(cenario))
    if (nova) {
      setParadaId('demo')
      comecar(nova)
    }
  }

  async function responderConsentimento(consentimento: boolean) {
    if (!espera) return
    const atual = await executar(() => api.naoParou(espera.id, consentimento))
    if (atual) {
      setEspera(atual)
      setPedirConsentimento(false)
    }
  }

  const linhasSugeridas = resposta?.acao?.tipo === 'esperar' ? (resposta.acao.linhas ?? []) : []
  const parada = paradas.find((p) => p.id === paradaId)

  return (
    <>
      <h1 className="titulo" tabIndex={-1}>
        Sonar
      </h1>
      <p className="status" data-testid="status">
        {status}
      </p>

      {espera && aguardando ? (
        <section aria-labelledby="titulo-espera">
          <h2 id="titulo-espera" ref={tituloEspera} tabIndex={-1}>
            Esperando {espera.linhas.join(' ou ')} no ponto {espera.parada_nome}
          </h2>
          {espera.demo && <p className="aviso-demo">Modo demonstração: dados de exemplo.</p>}
          <ul className="resumo">
            {espera.previsao && (
              <li>
                Linha {espera.previsao.linha}: {espera.previsao.minutos <= 0 ? 'chegando' : `${espera.previsao.minutos} min`}
              </li>
            )}
            <li>
              Motorista:{' '}
              {espera.aviso ? (espera.aviso.ciente_em ? 'avisado e confirmou' : 'sendo avisado') : 'será avisado 2 paradas antes'}
            </li>
          </ul>

          {pedirConsentimento && (
            <section className="pergunta" aria-labelledby="titulo-consentimento" ref={regiaoConsentimento} tabIndex={-1}>
              <h2 id="titulo-consentimento">O ônibus não parou?</h2>
              <p>
                Posso enviar uma reclamação ao SP156 com as evidências do ponto. Ela não leva seu nome: o Sonar não sabe
                quem você é.
              </p>
              <div className="botoes">
                <button type="button" className="primario" disabled={ocupado} onClick={() => responderConsentimento(true)}>
                  Sim, enviar a reclamação
                </button>
                <button type="button" disabled={ocupado} onClick={() => responderConsentimento(false)}>
                  Não, só registrar
                </button>
                <button type="button" disabled={ocupado} onClick={() => setPedirConsentimento(false)}>
                  Voltar
                </button>
              </div>
            </section>
          )}

          <div className="botoes">
            <button type="button" className="primario" disabled={ocupado} onClick={() => comandar('embarquei', 'toque')}>
              Embarquei
            </button>
            <button type="button" disabled={ocupado} onClick={() => comandar('nao_parou', 'toque')}>
              O ônibus não parou
            </button>
            <button type="button" disabled={ocupado} onClick={() => comandar('localizar', 'toque')}>
              Onde fica o poste? (bip)
            </button>
            {temVoz && (
              <button type="button" disabled={ocupado || ouvindo} onClick={falar}>
                {ouvindo ? 'Ouvindo…' : 'Falar um comando'}
              </button>
            )}
            <button type="button" disabled={ocupado} onClick={() => comandar('cancelar', 'toque')}>
              Cancelar espera
            </button>
          </div>

          <h2>O que aconteceu</h2>
          <ol className="historico">
            {historico
              .filter((evento) => evento.fala)
              .map((evento, indice) => (
                <li key={evento.id ?? indice}>
                  <span className="hora">{hora(evento.em)}</span> {evento.fala}
                </li>
              ))}
          </ol>
        </section>
      ) : (
        <>
          {espera && (
            <section aria-labelledby="titulo-fim" className="fim">
              <h2 id="titulo-fim" ref={tituloEspera} tabIndex={-1}>
                {RESUMO_FINAL[espera.status] ?? 'Espera encerrada.'}
              </h2>
              {espera.ocorrencia?.protocolo && <p>Protocolo da reclamação: {espera.ocorrencia.protocolo}</p>}
              {espera.ocorrencia?.status === 'pendente' && <p>Aguardando o protocolo da reclamação.</p>}
              <button type="button" disabled={ocupado} onClick={() => cheguei(espera.linhas, 'toque')}>
                Esperar de novo {espera.linhas.join(' ou ')}
              </button>
            </section>
          )}

          <section aria-labelledby="titulo-pergunta">
            <h2 id="titulo-pergunta">Para onde você vai?</h2>
            <label htmlFor="parada">Ponto de ônibus</label>
            <select id="parada" value={paradaId} onChange={(evento) => setParadaId(evento.target.value)}>
              {paradas.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.nome}
                </option>
              ))}
            </select>
            <button type="button" disabled={ocupado} onClick={usarLocalizacao}>
              Usar minha localização
            </button>

            {temVoz && (
              <button type="button" className="primario" disabled={ocupado || ouvindo} onClick={falar}>
                {ouvindo ? 'Ouvindo…' : 'Falar'}
              </button>
            )}
            <form onSubmit={enviar}>
              <label htmlFor="pergunta">Linha ou destino</label>
              <input
                id="pergunta"
                type="text"
                value={texto}
                onChange={(evento) => setTexto(evento.target.value)}
                placeholder={parada?.linhas[0] ? `Ex.: linha ${parada.linhas[0].codigo}` : 'Ex.: linha 8000-10'}
                autoComplete="off"
                enterKeyHint="send"
              />
              <button type="submit" disabled={ocupado || !texto.trim()}>
                Perguntar
              </button>
            </form>

            {linhasSugeridas.length > 0 && (
              <button type="button" className="primario" disabled={ocupado} onClick={() => cheguei(linhasSugeridas, 'toque')}>
                Cheguei ao ponto: esperar {linhasSugeridas.join(' ou ')}
              </button>
            )}
          </section>

          <section aria-labelledby="titulo-demo">
            <h2 id="titulo-demo">Modo demonstração</h2>
            <p>Roda a jornada inteira com dados de exemplo, em cerca de 2 minutos.</p>
            <div className="botoes">
              <button type="button" disabled={ocupado} onClick={() => demonstracao('embarque')}>
                Ver a jornada completa
              </button>
              <button type="button" disabled={ocupado} onClick={() => demonstracao('nao_parou')}>
                Ver um ônibus que não para
              </button>
              <button type="button" disabled={ocupado} onClick={() => demonstracao('maquete')}>
                Usar a maquete (Sonar Ponto e Sonar Bordo de verdade)
              </button>
            </div>
          </section>
        </>
      )}

      <section aria-labelledby="titulo-ajustes">
        <h2 id="titulo-ajustes">Ajustes</h2>
        <label className="opcao">
          <input type="checkbox" checked={vozAlta} onChange={(evento) => setVozAlta(evento.target.checked)} />
          Ler as respostas em voz alta (para quem não usa leitor de tela)
        </label>
      </section>
    </>
  )
}
