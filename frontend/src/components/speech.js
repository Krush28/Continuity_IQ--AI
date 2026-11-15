// Browser speech: recognition (speech → text) and synthesis (text → speech) via the Web Speech API.
// Works in Chrome / Edge. No API key, no extra cost.
import { useCallback, useEffect, useRef, useState } from 'react'

const Rec = typeof window !== 'undefined' ? (window.SpeechRecognition || window.webkitSpeechRecognition) : null
export const speechSupported = !!Rec
export const ttsSupported = typeof window !== 'undefined' && 'speechSynthesis' in window

export function useRecognizer(lang = 'en-IN') {
  const [listening, setListening] = useState(false)
  const [interim, setInterim] = useState('')
  const [error, setError] = useState('')
  const rec = useRef(null)

  const stop = useCallback(() => { try { rec.current?.stop() } catch { /* ignore */ } setListening(false) }, [])

  const listen = useCallback((onFinal) => {
    if (!Rec) { setError('Voice input needs Chrome or Edge. You can type instead.'); return }
    try { rec.current?.abort() } catch { /* ignore */ }
    stopSpeaking()
    const r = new Rec()
    r.lang = lang
    r.interimResults = true
    r.continuous = false
    r.maxAlternatives = 1
    let finalText = ''
    r.onresult = (e) => {
      let t = ''
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) finalText += e.results[i][0].transcript
        else t += e.results[i][0].transcript
      }
      setInterim(finalText + t)
    }
    r.onerror = (e) => { if (e.error !== 'no-speech' && e.error !== 'aborted') setError(`Mic error: ${e.error}`) }
    r.onend = () => {
      setListening(false)
      setInterim('')
      if (finalText.trim()) onFinal(finalText.trim())
    }
    rec.current = r
    setError('')
    setListening(true)
    r.start()
  }, [lang])

  useEffect(() => () => { try { rec.current?.abort() } catch { /* ignore */ } }, [])
  return { listening, interim, error, listen, stop, supported: speechSupported }
}

export function speak(text, lang = 'en-IN', onEnd) {
  if (!ttsSupported || !text) { onEnd?.(); return }
  window.speechSynthesis.cancel()
  const u = new SpeechSynthesisUtterance(text.slice(0, 900))
  u.lang = lang
  const voices = window.speechSynthesis.getVoices()
  const v = voices.find((x) => x.lang === lang) || voices.find((x) => x.lang?.startsWith(lang.slice(0, 2)))
  if (v) u.voice = v
  u.rate = 1.03
  u.onend = () => onEnd?.()
  u.onerror = () => onEnd?.()
  window.speechSynthesis.speak(u)
}

export function stopSpeaking() {
  if (ttsSupported) window.speechSynthesis.cancel()
}
