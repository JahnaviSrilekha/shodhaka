/** The Shodhaka mark: a lens with a check, the same drawing as docs/brand/shodhaka-mark.svg. */
export function LogoMark({ size = 26 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden focusable="false">
      <rect width="64" height="64" rx="14" fill="#245b4e" />
      <circle cx="28" cy="28" r="14" fill="none" stroke="#fff" strokeWidth="4.5" />
      <path d="M38.5 38.5 L49 49" stroke="#fff" strokeWidth="5.5" strokeLinecap="round" />
      <path d="M21.5 28.5 l4.5 4.5 l8.5-10" fill="none" stroke="#9fe1cb" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
