import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import axe from 'axe-core'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'
import { interpretarComando } from './comandos'

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

function respostaPara(url: string, init?: RequestInit): unknown {
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

describe('jornada do passageiro', () => {
  it('pergunta, chega ao ponto e ouve os avisos', async () => {
    localStorage.setItem('sonar.consentimento', '2026-11-08')
    render(<App />)

    fireEvent.change(await screen.findByLabelText('Linha ou destino'), { target: { value: 'linha DEMO-10' } })
    fireEvent.click(screen.getByRole('button', { name: 'Perguntar' }))
    expect(await screen.findByText(/chega em 5 minutos/, { selector: '.status' })).toBeTruthy()

    fireEvent.click(await screen.findByRole('button', { name: 'Cheguei ao ponto: esperar DEMO-10' }))
    expect(await screen.findByRole('heading', { name: /Esperando DEMO-10/ })).toBeTruthy()

    const fonte = EventSourceFalso.abertas.at(-1)!
    expect(fonte.url).toBe(`/api/esperas/${ESPERA.id}/eventos`)
    act(() => {
      fonte.emitir({ id: 3, tipo: 'onibus_chegando', fala: 'Chegando agora: linha DEMO-10. É o seu.', dados: { vibrar: 'longa' } })
    })
    expect(await screen.findByText('Chegando agora: linha DEMO-10. É o seu.', { selector: '.status' })).toBeTruthy()
    await waitFor(() => expect(screen.getByTestId('anuncio').textContent).toBe('Chegando agora: linha DEMO-10. É o seu.'))

    act(() => {
      fonte.emitir({ id: 4, tipo: 'onibus_passou_direto', fala: 'A linha DEMO-10 passou sem parar.', dados: {} })
    })
    expect(await screen.findByRole('heading', { name: 'O ônibus não parou?' })).toBeTruthy()
  })
})

describe('comandos de voz', () => {
  it.each([
    ['Embarquei', 'embarquei'],
    ['ele não parou!', 'nao_parou'],
    ['o ônibus passou direto', 'nao_parou'],
    ['quero cancelar', 'cancelar'],
    ['onde fica o ponto?', 'localizar'],
    ['linha 8000-10', null],
  ])('"%s" vira %s', (frase, esperado) => {
    expect(interpretarComando(frase)).toBe(esperado)
  })
})
