import { useEffect, useState, type MouseEvent, type ReactNode } from 'react'

export const ROTAS = [
  { caminho: '/', nome: 'Passageiro' },
  { caminho: '/motorista', nome: 'Motorista (simulado)' },
  { caminho: '/ponto', nome: 'Ponto (simulado)' },
  { caminho: '/painel', nome: 'Painel da cidade' },
  { caminho: '/privacidade', nome: 'Privacidade' },
] as const

export type Caminho = (typeof ROTAS)[number]['caminho']

export function caminhoAtual(): Caminho {
  const caminho = window.location.pathname.replace(/\/+$/, '') || '/'
  return (ROTAS.find((rota) => rota.caminho === caminho)?.caminho ?? '/') as Caminho
}

export function navegar(para: string): void {
  window.history.pushState({}, '', para)
  window.dispatchEvent(new PopStateEvent('popstate'))
}

export function useCaminho(): Caminho {
  const [caminho, setCaminho] = useState<Caminho>(caminhoAtual)
  useEffect(() => {
    const aoMudar = () => setCaminho(caminhoAtual())
    window.addEventListener('popstate', aoMudar)
    return () => window.removeEventListener('popstate', aoMudar)
  }, [])
  return caminho
}

export function Link({ para, children, atual }: { para: string; children: ReactNode; atual?: boolean }) {
  function aoClicar(evento: MouseEvent<HTMLAnchorElement>) {
    if (evento.metaKey || evento.ctrlKey || evento.shiftKey || evento.altKey || evento.button !== 0) return
    evento.preventDefault()
    navegar(para)
  }
  return (
    <a href={para} onClick={aoClicar} aria-current={atual ? 'page' : undefined}>
      {children}
    </a>
  )
}
