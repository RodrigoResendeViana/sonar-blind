// Voz, vibração, tela ligada e bipper. Tudo opcional: o app funciona sem cada um deles.

interface ResultadoReconhecimento {
  results: ArrayLike<ArrayLike<{ transcript: string }>>
}

interface Reconhecimento {
  lang: string
  interimResults: boolean
  maxAlternatives: number
  continuous: boolean
  start(): void
  abort(): void
  onresult: ((evento: ResultadoReconhecimento) => void) | null
  onerror: ((evento: { error: string }) => void) | null
  onend: (() => void) | null
}

type ConstrutorReconhecimento = new () => Reconhecimento

function construtorReconhecimento(): ConstrutorReconhecimento | undefined {
  if (typeof window === 'undefined') return undefined
  const janela = window as unknown as {
    SpeechRecognition?: ConstrutorReconhecimento
    webkitSpeechRecognition?: ConstrutorReconhecimento
  }
  return janela.SpeechRecognition ?? janela.webkitSpeechRecognition
}

/** No iOS, some quando o app é instalado na tela inicial; aí o plano B é o ditado do teclado. */
export function reconhecimentoDisponivel(): boolean {
  return construtorReconhecimento() !== undefined
}

/** Ouve uma frase em português. O navegador pode mandar o áudio para o serviço do fabricante. */
export function ouvirFrase(): Promise<string> {
  const Construtor = construtorReconhecimento()
  if (!Construtor) return Promise.reject(new Error('reconhecimento de voz indisponível'))
  return new Promise((resolver, rejeitar) => {
    const reconhecimento = new Construtor()
    reconhecimento.lang = 'pt-BR'
    reconhecimento.interimResults = false
    reconhecimento.maxAlternatives = 1
    reconhecimento.continuous = false
    let entregue = false
    reconhecimento.onresult = (evento) => {
      entregue = true
      resolver(evento.results[0]?.[0]?.transcript ?? '')
    }
    reconhecimento.onerror = (evento) => {
      entregue = true
      rejeitar(new Error(evento.error))
    }
    reconhecimento.onend = () => {
      if (!entregue) resolver('')
    }
    reconhecimento.start()
  })
}

/** Só para quem não usa leitor de tela: o padrão é deixar o TalkBack ou o VoiceOver ler. */
export function falarEmVozAlta(texto: string): void {
  if (typeof window === 'undefined' || !('speechSynthesis' in window)) return
  window.speechSynthesis.cancel()
  const fala = new SpeechSynthesisUtterance(texto)
  fala.lang = 'pt-BR'
  window.speechSynthesis.speak(fala)
}

const PADROES_VIBRACAO: Record<string, number[]> = {
  longa: [700],
  curta: [150],
  dupla: [150, 120, 150],
}

/** Vibração longa = é o seu; dupla = não é o seu. */
export function vibrar(padrao: string): void {
  if (typeof navigator !== 'undefined' && 'vibrate' in navigator) {
    navigator.vibrate(PADROES_VIBRACAO[padrao] ?? [150])
  }
}

let contextoAudio: AudioContext | null = null

/** O navegador só libera som depois de um toque do usuário. */
export function prepararSom(): void {
  if (typeof AudioContext === 'undefined') return
  contextoAudio ??= new AudioContext()
  void contextoAudio.resume()
}

export function bipar(vezes = 3): void {
  if (!contextoAudio) return
  for (let i = 0; i < vezes; i++) {
    const oscilador = contextoAudio.createOscillator()
    const ganho = contextoAudio.createGain()
    const inicio = contextoAudio.currentTime + i * 0.35
    oscilador.frequency.value = 880
    oscilador.connect(ganho)
    ganho.connect(contextoAudio.destination)
    ganho.gain.setValueAtTime(0.0001, inicio)
    ganho.gain.exponentialRampToValueAtTime(0.3, inicio + 0.02)
    ganho.gain.exponentialRampToValueAtTime(0.0001, inicio + 0.25)
    oscilador.start(inicio)
    oscilador.stop(inicio + 0.3)
  }
}

/** Mantém a tela ligada durante a espera (Wake Lock API), quando o navegador deixa. */
export function manterTelaLigada(): () => void {
  if (typeof navigator === 'undefined' || !('wakeLock' in navigator)) return () => {}
  let trava: WakeLockSentinel | null = null
  let ativo = true
  const pedir = async () => {
    try {
      trava = await navigator.wakeLock.request('screen')
    } catch {
      // negado (bateria fraca, aba em segundo plano)
    }
  }
  const aoVoltar = () => {
    if (ativo && document.visibilityState === 'visible') void pedir()
  }
  void pedir()
  document.addEventListener('visibilitychange', aoVoltar)
  return () => {
    ativo = false
    document.removeEventListener('visibilitychange', aoVoltar)
    void trava?.release()
  }
}
