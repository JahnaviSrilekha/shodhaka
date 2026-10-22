const PATHS = {
  upload: "M12 16V4m0 0L7 9m5-5 5 5M4 17v2a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-2",
  back: "M15 18l-6-6 6-6",
  doc: "M7 3h7l5 5v12a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1zm7 0v5h5",
  check: "M5 13l4 4L19 7",
  x: "M6 6l12 12M18 6L6 18",
  download: "M12 4v12m0 0l-5-5m5 5 5-5M4 20h16",
  refresh: "M4 12a8 8 0 0 1 14-5.3L20 9M20 4v5h-5M20 12a8 8 0 0 1-14 5.3L4 15m0 5v-5h5",
  edit: "M4 20h4L19 9l-4-4L4 16v4zM14 6l4 4",
  undo: "M9 14L4 9l5-5M4 9h11a5 5 0 0 1 0 10h-3",
  shield: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6l8-3z",
  search: "M11 18a7 7 0 1 1 0-14 7 7 0 0 1 0 14zm5-2l4 4",
} as const;

export function Icon({ name, size = 16 }: { name: keyof typeof PATHS; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}
      strokeLinecap="round" strokeLinejoin="round" aria-hidden focusable="false">
      <path d={PATHS[name]} />
    </svg>
  );
}
