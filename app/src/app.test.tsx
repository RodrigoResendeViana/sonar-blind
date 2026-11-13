import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import axe from 'axe-core'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'

const PARADA = {
  id: 'demo',
  nome: 'Ponto de demonstração (Itaquera)',
  codigo_sptrans: null,
  lat: -23.5424,
  lon: -46.4712,
  demo: true,
  linhas: [
    { codigo: 'DEMO-10', destino: 'Terminal Exemplo' },
    { codigo: 'DEMO-20', destino: 'Centro (exemplo)' },
  ],
}

const ESPERA = {
  id: '3b5e9814-5f02-478e-ac43-a5b671adac73',
  parada_id: 'demo',
  parada_nome: PARADA.nome,
  linhas: ['DEMO-10'],
  status: 'aguardando',
  demo: false,
  criado_em: '2026-11-08T18:00:00Z',
  expira_em: '2026-11-08T18:45:00Z',
  previsao: null,
  aviso: null,
  passagem: null,
  embarque: null,
  ocorrencia: null,
}

const INDICADORES = {
  esperas: 2,
  avisos_enviados: 1,
  avisos_ciente: 1,
  taxa_ciente: 1,
  embarques: 1,
  embarques_validados_camera: 1,
  nao_parou: 1,
  nao_parou_por_100_esperas: 50,
  tempo_medio_espera_min: 4.5,
  ocorrencias_por_status: { anonima: 1 },
  por_linha: [{ linha: 'DEMO-10', esperas: 2, avisos: 1, cientes: 1, embarques: 1, nao_parou: 1 }],
  dispositivos: [{ tipo: 'ponto', id: 'demo', online: true, ultimo_sinal_em: '2026-11-08T18:00:00Z' }],
  gerado_em: '2026-11-08T18:00:00Z',
}

class EventSourceFalso {
  static abertas: EventSourceFalso[] = []
  onmessage: ((mensagem: MessageEvent<string>) => void) | null = null
  onerror: (() => void) | null = null
  fechada = false
  constructor(public url: string) {
    EventSourceFalso.abertas.push(this)
  }
  emitir(dados: unknown) {
    this.onmessage?.({ data: JSON.stringify(dados) } as MessageEvent<string>)
  }
  close() {
    this.fechada = true
  }
}

const PLANO = {
  trechos: [
    {
      linha: 'DEMO-20',
      sentido: 'Centro (exemplo)',
      embarque: { id: 'demo', nome: PARADA.nome, lat: -23.5424, lon: -46.4712 },
      desembarque: { id: 'ex-centro', nome: 'Centro (exemplo)', lat: -23.545, lon: -46.498 },
      paradas: 3,
      minutos: 9,
    },
  ],
  caminhada_inicio_m: 0,
  caminhada_fim_m: 40,
  minutos_estimados: 15,
  baldeacoes: 0,
}

function conversa(estado: string, fala: string, extra: Record<string, unknown> = {}) {
  return {
    sessao: '11111111-2222-3333-4444-555555555555',
    estado,
    fala,
    espera_id: null,
    plano: null,
    trecho: 0,
    destino: null,
    demo: true,
    acompanhar: false,
    intervalo_s: 3,
    ...extra,
  }
}

function respostaConversa(corpo: { evento: string; texto?: string }): unknown {
  if (corpo.evento === 'abrir') return conversa('inicio', 'Olá, eu sou o Sonar. Toque na tela e diga para onde você quer ir.')
  if (corpo.texto?.includes('centro')) {
    return conversa('confirmar_plano', 'Para ir até Centro: pegue o DEMO-20. Quer ir? Diga sim.', {
      plano: PLANO,
      destino: 'Centro',
    })
  }
  if (corpo.texto === 'cheguei') {
    return conversa('no_ponto', 'Estou esperando o DEMO-20 com você.', { plano: PLANO, destino: 'Centro', espera_id: ESPERA.id })
  }
  return conversa('inicio', 'Não entendi.')
}

function respostaPara(url: string, init?: RequestInit): unknown {
  if (url.endsWith('/conversa')) return respostaConversa(JSON.parse(String(init?.body ?? '{}')))
  if (url.endsWith('/paradas')) return [PARADA]
  if (url.includes('/ia/perguntar')) {
    return {
      status: 'ok',
      resposta_falada: 'A linha DEMO-10 chega em 5 minutos no ponto de demonstração. Dados de demonstração.',
      acao: { tipo: 'esperar', parada_id: 'demo', linhas: ['DEMO-10'] },
      fontes: ['demonstracao:previsao'],
      confianca: 0.9,
    }
  }
  if (url.endsWith('/esperas') && init?.method === 'POST') return ESPERA
  if (url.includes('/esperas/')) return ESPERA
  if (url.includes('/painel/indicadores')) return INDICADORES
  return {}
}

async function semViolacoes(elemento: HTMLElement) {
  const resultado = await axe.run(elemento, { rules: { 'color-contrast': { enabled: false } } })
  expect(resultado.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`)).toEqual([])
}

beforeEach(() => {
  EventSourceFalso.abertas = []
  vi.stubGlobal('EventSource', EventSourceFalso)
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) =>
      new Response(JSON.stringify(respostaPara(url, init)), { status: 200, headers: { 'Content-Type': 'application/json' } }),
    ),
  )
  localStorage.clear()
  window.history.pushState({}, '', '/')
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('acessibilidade (axe)', () => {
  it('tela de consentimento', async () => {
    const { container } = render(<App />)
    expect(await screen.findByRole('heading', { level: 1, name: 'Antes de começar' })).toBeTruthy()
    await semViolacoes(container)
  })

  it.each([
    ['/', 'Sonar'],
    ['/motorista', 'Sonar Bordo (motorista simulado)'],
    ['/ponto', 'Sonar Ponto (simulado)'],
    ['/painel', 'Painel da cidade'],
    ['/privacidade', 'Privacidade'],
  ])('tela %s', async (caminho, titulo) => {
    localStorage.setItem('sonar.consentimento', '2026-11-08')
    window.history.pushState({}, '', caminho)
    const { container } = render(<App />)
    expect(await screen.findByRole('heading', { level: 1, name: titulo })).toBeTruthy()
    await act(async () => {
      await new Promise((resolver) => setTimeout(resolver, 50))
    })
    await semViolacoes(container)
  })
})

describe('jornada por voz', () => {
  it('diz o destino, recebe o plano, chega ao ponto e ouve o ônibus', async () => {
    localStorage.setItem('sonar.consentimento', '2026-11-08')
    render(<App />)
    expect(await screen.findByText(/diga para onde você quer ir/, { selector: '.status' })).toBeTruthy()
    expect(screen.getByRole('button', { name: /Toque para falar/ })).toBeTruthy()

    // sem reconhecimento de voz (como no jsdom e no iOS instalado), o campo de texto aparece
    fireEvent.change(screen.getByLabelText('Escrever em vez de falar'), { target: { value: 'quero ir para o centro' } })
    fireEvent.click(screen.getByRole('button', { name: 'Enviar' }))
    expect(await screen.findByText(/pegue o DEMO-20/, { selector: '.status' })).toBeTruthy()
    expect(await screen.findByRole('heading', { name: /Plano \(demonstração\): Centro/ })).toBeTruthy()

    fireEvent.change(screen.getByLabelText('Escrever em vez de falar'), { target: { value: 'cheguei' } })
    fireEvent.click(screen.getByRole('button', { name: 'Enviar' }))
    expect(await screen.findByText('Estou esperando o DEMO-20 com você.', { selector: '.status' })).toBeTruthy()

    await waitFor(() => expect(EventSourceFalso.abertas.at(-1)?.url).toBe(`/api/esperas/${ESPERA.id}/eventos`))
    const fonte = EventSourceFalso.abertas.at(-1)!
    act(() => {
      fonte.emitir({ id: 2, tipo: 'ponto_ativado', fala: 'Espera iniciada.', dados: {} })
      fonte.emitir({ id: 3, tipo: 'onibus_chegando', fala: 'Chegando agora: linha DEMO-20. É o seu.', dados: { vibrar: 'longa' } })
    })
    expect(await screen.findByText('Chegando agora: linha DEMO-20. É o seu.', { selector: '.status' })).toBeTruthy()
    await waitFor(() => expect(screen.getByTestId('anuncio').textContent).toBe('Chegando agora: linha DEMO-20. É o seu.'))
  })
})
