export function Logo({ size = 30 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <rect width="32" height="32" rx="9" fill="url(#lg)" />
      <defs><linearGradient id="lg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#6366f1" /><stop offset="1" stopColor="#0ea5e9" /></linearGradient></defs>
      <path d="M9 16a7 7 0 0 1 12-5M23 16a7 7 0 0 1-12 5" stroke="white" strokeWidth="3" fill="none" strokeLinecap="round" />
      <path d="M21 7v4h-4M11 25v-4h4" stroke="white" strokeWidth="2.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
