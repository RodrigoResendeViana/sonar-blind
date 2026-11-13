import { useEffect, useState } from 'react'

import { api, mensagemDeErro, ouvirEventos, type Parada } from '../api'

interface EventoParada {
  tipo: 'estado' | 'cmd' | 'deteccao'
  parada?: Parada
  esperas_ativas?: number
  linhas_alvo?: string[]
  dispositivos?: Record<string, { online: boolean }>
  dados?: { acao?: string; linhas_alvo?: string[]; linha_lida?: string | null; tempo_parado_s?: number; parou?: boolean }
  em?: string
}

/** Gêmeo digital do Sonar Ponto: publica a detecção como se fosse a câmera e o ultrassom. */
export default function Ponto() {
  const [paradas, setParadas] = useState<Parada[]>([])
  const [paradaId, setParadaId] = useState('demo')
  const [ativo, setAtivo] = useState(false)
  const [linhasAlvo, setLinhasAlvo] = useState<string[]>([])
  const [registro, setRegistro] = useState<string[]>([])
  const [mensagem, setMensagem] = useState('')
  const [semVideo, setSemVideo] = useState(false)

  useEffect(() => {
    api
      .paradas()
      .then(setParadas)
      .catch(() => setMensagem('Não consegui carregar os pontos.'))
  }, [])

  useEffect(
    () =>
      ouvirEventos<EventoParada>(`/simulador/paradas/${paradaId}/eventos`, (evento) => {
        if (evento.tipo === 'estado') {
          setAtivo((evento.esperas_ativas ?? 0) > 0)
          setLinhasAlvo(evento.linhas_alvo ?? [])
        } else if (evento.tipo === 'cmd' && evento.dados?.acao === 'ativar') {
          setAtivo(true)
          setLinhasAlvo(evento.dados.linhas_alvo ?? [])
        } else if (evento.tipo === 'cmd' && evento.dados?.acao === 'desativar') {
          setAtivo(false)
          setLinhasAlvo([])
        } else if (evento.tipo === 'deteccao' && evento.dados) {
          const d = evento.dados
          const linha = d.linha_lida ?? 'sem leitura'
          setRegistro((atual) => [`${linha} · parado ${d.tempo_parado_s ?? 0} s${d.parou ? '' : ' (passou direto)'}`, ...atual].slice(0, 20))
        }
      }),
    [paradaId],
  )

  const parada = paradas.find((p) => p.id === paradaId)
  const linhaCerta = linhasAlvo[0] ?? parada?.linhas[0]?.codigo ?? 'DEMO-10'
  const outraLinha = parada?.linhas.find((l) => !linhasAlvo.includes(l.codigo))?.codigo ?? 'DEMO-20'

  async function detectar(corpo: Parameters<typeof api.deteccao>[1], descricao: string) {
    try {
      const resultado = await api.deteccao(paradaId, corpo)
      setMensagem(`${descricao}: ${resultado.esperas_afetadas} espera(s) avisada(s).`)
    } catch (erro) {
      setMensagem(mensagemDeErro(erro))
    }
  }

  async function apertarBotao() {
    try {
      const resultado = await api.botao(paradaId)
      setMensagem(
        resultado.espera
          ? `Botão apertado: motoristas das linhas ${resultado.espera.linhas.join(', ')} avisados por 10 minutos.`
          : 'Este ponto não tem linhas cadastradas.',
      )
    } catch (erro) {
      setMensagem(mensagemDeErro(erro))
    }
  }

  return (
    <>
      <h1 className="titulo" tabIndex={-1}>
        Sonar Ponto (simulado)
      </h1>
      <p>
        Esta tela faz o papel da câmera e do ultrassom do ponto. O Sonar Ponto de verdade publica o mesmo evento por
        MQTT; nenhuma imagem sai do ponto.
      </p>
      <label htmlFor="parada-simulada">Ponto</label>
      <select id="parada-simulada" value={paradaId} onChange={(evento) => setParadaId(evento.target.value)}>
        {paradas.map((p) => (
          <option key={p.id} value={p.id}>
            {p.nome}
          </option>
        ))}
      </select>

      <div className="painel-ponto">
        <span className={ativo ? 'led ativo' : 'led'} aria-hidden="true" />
        <p>
          {ativo
            ? `Espera ativa: LED pulsando para o motorista. Linhas esperadas: ${linhasAlvo.join(', ')}.`
            : 'Nenhuma espera ativa: LED apagado, câmera desligada.'}
        </p>
      </div>

      {semVideo ? (
        <p className="nota">
          Coloque um vídeo de ônibus chegando em <code>app/public/demo/onibus.mp4</code> para ele aparecer aqui.
        </p>
      ) : (
        <video
          className="video"
          src="/demo/onibus.mp4"
          controls
          muted
          playsInline
          onError={() => setSemVideo(true)}
          aria-label="Vídeo de ônibus chegando ao ponto"
        />
      )}

      <div className="botoes">
        <button type="button" className="primario" onClick={() => detectar({ linha_lida: linhaCerta, confianca: 0.95, tempo_parado_s: 12 }, `${linhaCerta} chegou e parou`)}>
          {linhaCerta} chegou e parou
        </button>
        <button type="button" onClick={() => detectar({ linha_lida: outraLinha, confianca: 0.9, tempo_parado_s: 8 }, `${outraLinha} chegou`)}>
          Outra linha chegou ({outraLinha})
        </button>
        <button type="button" onClick={() => detectar({ linha_lida: linhaCerta, confianca: 0.93, tempo_parado_s: 0.6, parou: false }, `${linhaCerta} passou direto`)}>
          {linhaCerta} passou direto
        </button>
        <button type="button" onClick={() => detectar({ linha_lida: null, tempo_parado_s: 9, camera_ok: false }, 'Ônibus sem leitura da câmera')}>
          Ônibus parou, câmera sem leitura
        </button>
        <button type="button" onClick={apertarBotao}>
          Botão do poste: tem passageiro com deficiência visual aqui
        </button>
      </div>
      {mensagem && <p className="status">{mensagem}</p>}

      <h2>Últimas detecções</h2>
      <ol className="historico">
        {registro.map((linha, indice) => (
          <li key={`${indice}-${linha}`}>{linha}</li>
        ))}
      </ol>
    </>
  )
}
