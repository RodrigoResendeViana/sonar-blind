import { useEffect, useState, type MouseEvent, type ReactNode } from 'react'

export const ROTAS = [
  { caminho: '/', nome: 'Início' },
  { caminho: '/passageiro', nome: 'Passageiro' },
  { caminho: '/motorista', nome: 'Motorista' },
  { caminho: '/ponto', nome: 'Ponto de ônibus' },
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

export function Link({
  para,
  children,
  atual,
  className,
}: {
  para: string
  children: ReactNode
  atual?: boolean
  className?: string
}) {
  function aoClicar(evento: MouseEvent<HTMLAnchorElement>) {
    if (evento.metaKey || evento.ctrlKey || evento.shiftKey || evento.altKey || evento.button !== 0) return
    evento.preventDefault()
    navegar(para)
  }
  return (
    <a href={para} onClick={aoClicar} aria-current={atual ? 'page' : undefined} className={className}>
      {children}
    </a>
  )
}
