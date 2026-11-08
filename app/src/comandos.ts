// Comandos de voz que o app resolve sozinho durante a espera, sem passar pela IA.

export type Comando = 'embarquei' | 'nao_parou' | 'cancelar' | 'localizar'

export function normalizar(texto: string): string {
  return texto
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9 -]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

export function interpretarComando(texto: string): Comando | null {
  const frase = normalizar(texto)
  if (!frase) return null
  if (/\b(nao|nem) (parou|para)\b|\bpassou direto\b/.test(frase)) return 'nao_parou'
  if (/\b(embarquei|entrei|subi|ja estou no onibus)\b/.test(frase)) return 'embarquei'
  if (/\b(cancelar|cancela|desisti|parar a espera)\b/.test(frase)) return 'cancelar'
  if (/\b(onde fica|onde esta|cade|apita|apitar|bip|poste)\b/.test(frase)) return 'localizar'
  return null
}
