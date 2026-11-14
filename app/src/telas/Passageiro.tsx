import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'

import { useAnuncio } from '../anuncio'
import {
  api,
  mensagemDeErro,
  ouvirEventos,
  type CenarioDemo,
  type EventoEspera,
  type PedidoConversa,
  type RespostaConversa,
} from '../api'
import { manterTelaLigada, ouvirFrase, prepararSom, reconhecimentoDisponivel, vibrar } from '../voz'

const CHAVE_SESSAO = 'sonar.conversa'
const CHAVE_CENARIO = 'sonar.cenario-demo'
// eventos da espera que a própria conversa já falou (não repete)
const FALADOS_PELA_CONVERSA = new Set(['ponto_ativado', 'embarque_confirmado', 'ocorrencia_registrada', 'localizar', 'cancelada'])
const RESINCRONIZAM = new Set(['expirada', 'embarque_confirmado'])

type Fase = 'parado' | 'ouvindo' | 'pensando'
type Posicao = { lat: number; lon: number }

const ROTULO_FASE: Record<Fase, string> = {
  parado: 'Toque para falar',
  ouvindo: 'Ouvindo… fale agora',
  pensando: 'Pensando…',
}

function lerArmazenado(chave: string, armazenamento: () => Storage): string | null {
  try {
    return armazenamento().getItem(chave)
  } catch {
    return null
  }
}

function gravar(chave: string, valor: string, armazenamento: () => Storage): void {
  try {
    armazenamento().setItem(chave, valor)
  } catch {
    // sem armazenamento: vale só enquanto a tela estiver aberta
  }
}

function pegarPosicao(): Promise<Posicao | null> {
  if (typeof navigator === 'undefined' || !('geolocation' in navigator)) return Promise.resolve(null)
  return new Promise((resolver) => {
    navigator.geolocation.getCurrentPosition(
      (local) => resolver({ lat: local.coords.latitude, lon: local.coords.longitude }),
      () => resolver(null),
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 20000 },
    )
  })
}

/**
 * O app inteiro é um botão: a pessoa toca, diz para onde vai, e o Sonar conduz a viagem
 * falando (pelo leitor de tela ou pela voz do navegador). A localização fica só na memória
 * do app e vai para o servidor apenas para planejar e avisar a hora de descer.
 */
export default function Passageiro() {
  const { anunciar, vozAlta, setVozAlta } = useAnuncio()
  const [resposta, setResposta] = useState<RespostaConversa | null>(null)
  const [fala, setFala] = useState('Toque no botão e diga para onde você quer ir.')
  const [fase, setFase] = useState<Fase>('parado')
  const [texto, setTexto] = useState('')
  const [cenario, setCenario] = useState<CenarioDemo>(
    () => (lerArmazenado(CHAVE_CENARIO, () => localStorage) as CenarioDemo | null) ?? 'auto',
  )
  const sessao = useRef<string | null>(lerArmazenado(CHAVE_SESSAO, () => sessionStorage))
  const posicao = useRef<Posicao | null>(null)
  const ocupado = useRef(false)
  const campoTexto = useRef<HTMLInputElement>(null)
  const temVoz = reconhecimentoDisponivel()

  const dizer = useCallback(
    (frase: string) => {
      if (!frase) return
      setFala(frase)
      anunciar(frase)
    },
    [anunciar],
  )

  const enviar = useCallback(
    async (pedido: Omit<PedidoConversa, 'sessao' | 'cenario_demo'>, tentarLocalizacao = true): Promise<void> => {
      const corpo: PedidoConversa = {
        ...pedido,
        sessao: sessao.current,
        cenario_demo: cenario,
        ...(posicao.current ?? {}),
      }
      const recebida = await api.conversar(corpo)
      sessao.current = recebida.sessao
      gravar(CHAVE_SESSAO, recebida.sessao, () => sessionStorage)
      setResposta(recebida)
      if (recebida.fala) dizer(recebida.fala)
      if (recebida.pedir_localizacao && recebida.repetir_texto && tentarLocalizacao) {
        const local = await pegarPosicao()
        if (local) {
          posicao.current = local
          await enviar({ evento: 'fala', texto: recebida.repetir_texto }, false)
        } else {
          dizer('Não consegui sua localização. Confira se ela está ligada e permitida para o Sonar.')
        }
      }
    },
    [cenario, dizer],
  )

  const enviarSeLivre = useCallback(
    async (pedido: Omit<PedidoConversa, 'sessao' | 'cenario_demo'>) => {
      if (ocupado.current) return
      ocupado.current = true
      try {
        await enviar(pedido)
      } catch (erro) {
        if (pedido.evento === 'fala' || pedido.evento === 'abrir') dizer(mensagemDeErro(erro))
      } finally {
        ocupado.current = false
      }
    },
    [enviar, dizer],
  )

  // primeira fala: saudação (ou "continuando" se a sessão já existia)
  useEffect(() => {
    void enviarSeLivre({ evento: 'abrir' })
    // só ao abrir a tela
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // a caminho do ponto e dentro do ônibus: GPS e um "tique" para os avisos (chegou, desça agora)
  const acompanhar = resposta?.acompanhar ?? false
  const intervalo = (resposta?.intervalo_s ?? 10) * 1000
  useEffect(() => {
    if (!acompanhar) return
    let observador: number | undefined
    if (typeof navigator !== 'undefined' && 'geolocation' in navigator) {
      observador = navigator.geolocation.watchPosition(
        (local) => {
          posicao.current = { lat: local.coords.latitude, lon: local.coords.longitude }
        },
        () => {},
        { enableHighAccuracy: true, maximumAge: 5000 },
      )
    }
    const relogio = window.setInterval(() => {
      void enviarSeLivre({ evento: posicao.current ? 'posicao' : 'tick' })
    }, intervalo)
    return () => {
      window.clearInterval(relogio)
      if (observador !== undefined) navigator.geolocation.clearWatch(observador)
    }
  }, [acompanhar, intervalo, enviarSeLivre])

  // no ponto: os avisos do ônibus chegam em tempo real (SSE)
  const esperaId = resposta?.espera_id ?? null
  useEffect(() => {
    if (!esperaId) return
    return ouvirEventos(`/esperas/${esperaId}/eventos`, (evento: EventoEspera) => {
      if (evento.tipo === 'estado') return
      if (evento.fala && !FALADOS_PELA_CONVERSA.has(evento.tipo)) dizer(evento.fala)
      if (typeof evento.dados?.vibrar === 'string') vibrar(evento.dados.vibrar)
      if (RESINCRONIZAM.has(evento.tipo)) void enviarSeLivre({ evento: 'tick' })
    })
  }, [esperaId, dizer, enviarSeLivre])

  const emViagem = resposta !== null && resposta.estado !== 'inicio' && resposta.estado !== 'chegou'
  useEffect(() => (emViagem ? manterTelaLigada() : undefined), [emViagem])

  async function aoTocar() {
    prepararSom()
    if (fase !== 'parado') return
    if (!temVoz) {
      dizer('Este navegador não reconhece voz. Escreva no campo abaixo do botão, ou use o ditado do teclado.')
      campoTexto.current?.focus()
      return
    }
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) window.speechSynthesis.cancel()
    vibrar('curta') // "pode falar"
    setFase('ouvindo')
    try {
      const frase = await ouvirFrase()
      if (!frase) {
        dizer('Não ouvi nada. Toque e fale de novo.')
        return
      }
      setFase('pensando')
      await enviarSeLivre({ evento: 'fala', texto: frase })
    } catch {
      dizer('Não consegui ouvir. Toque e fale de novo.')
    } finally {
      setFase('parado')
    }
  }

  async function escrever(evento: FormEvent) {
    evento.preventDefault()
    const frase = texto.trim()
    if (!frase) return
    setTexto('')
    setFase('pensando')
    await enviarSeLivre({ evento: 'fala', texto: frase })
    setFase('parado')
  }

  function mudarCenario(valor: CenarioDemo) {
    setCenario(valor)
    gravar(CHAVE_CENARIO, valor, () => localStorage)
  }

  const formulario = (
    <form onSubmit={escrever} className="escrever">
      <label htmlFor="frase">Escrever em vez de falar</label>
      <input
        id="frase"
        ref={campoTexto}
        type="text"
        value={texto}
        onChange={(evento) => setTexto(evento.target.value)}
        placeholder="Ex.: quero ir para o centro"
        autoComplete="off"
        enterKeyHint="send"
      />
      <button type="submit" disabled={fase !== 'parado' || !texto.trim()}>
        Enviar
      </button>
    </form>
  )

  const plano = resposta?.plano
  return (
    <>
      <h1 className="titulo" tabIndex={-1}>
        Sonar
      </h1>
      <p className="status" data-testid="status">
        {fala}
      </p>

      <button
        type="button"
        className={`microfone ${fase}`}
        onClick={aoTocar}
        aria-busy={fase === 'pensando'}
        aria-describedby="dica-microfone"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          <path d="M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3Zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-2.08A7 7 0 0 0 19 12h-2Z" />
        </svg>
        <span>{ROTULO_FASE[fase]}</span>
      </button>
      <p id="dica-microfone" className="nota">
        Diga para onde você quer ir. Depois: cheguei, quanto falta, embarquei, quero reclamar, repete ou ajuda.
      </p>

      {!temVoz && formulario}

      {plano && (
        <section aria-labelledby="titulo-plano" className="plano">
          <h2 id="titulo-plano">
            {resposta?.demo ? 'Plano (demonstração)' : 'Plano'}: {resposta?.destino}
          </h2>
          <ol>
            {plano.trechos.map((trecho, indice) => (
              <li key={`${trecho.linha}-${indice}`} aria-current={indice === resposta?.trecho ? 'step' : undefined}>
                <strong>{trecho.linha}</strong> de {trecho.embarque.nome} até {trecho.desembarque.nome} ({trecho.paradas}{' '}
                {trecho.paradas === 1 ? 'parada' : 'paradas'})
              </li>
            ))}
          </ol>
          <p className="nota">Uns {plano.minutos_estimados} minutos no total.</p>
        </section>
      )}

      <details className="mais">
        <summary>Mais opções</summary>
        {temVoz && formulario}
        <label className="opcao">
          <input type="checkbox" checked={vozAlta} onChange={(evento) => setVozAlta(evento.target.checked)} />
          Ler as respostas em voz alta (para quem não usa leitor de tela)
        </label>
        <label htmlFor="cenario">Demonstração: o que o ônibus faz</label>
        <select id="cenario" value={cenario} onChange={(evento) => mudarCenario(evento.target.value as CenarioDemo)}>
          <option value="auto">Automático (câmera ou maquete, se estiverem ligadas)</option>
          <option value="embarque">O ônibus para</option>
          <option value="nao_parou">O ônibus passa direto</option>
          <option value="maquete">Só a câmera e a maquete de verdade</option>
        </select>
        <button type="button" onClick={() => void enviarSeLivre({ evento: 'fala', texto: 'cancelar' })}>
          Recomeçar
        </button>
      </details>
    </>
  )
}
