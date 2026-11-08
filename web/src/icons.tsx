/**
 * Tab bar icons. Path data copied from Tabler Icons v3.50.0 (outline set),
 * https://tabler.io/icons — MIT License, Copyright (c) 2020-2026 Paweł Kuna.
 * Copied rather than installed so the bundle stays free of runtime packages
 * (decision 0003). Icons draw in `currentColor`, so they follow the theme.
 */

export type IconName = "status" | "sessions" | "cron" | "logs" | "knowledge" | "send";

const PATHS: Record<IconName, string[]> = {
  // gauge
  status: [
    "M3 12a9 9 0 1 0 18 0a9 9 0 1 0 -18 0",
    "M11 12a1 1 0 1 0 2 0a1 1 0 1 0 -2 0",
    "M13.41 10.59l2.59 -2.59",
    "M7 12a5 5 0 0 1 5 -5",
  ],
  // messages
  sessions: [
    "M21 14l-3 -3h-7a1 1 0 0 1 -1 -1v-6a1 1 0 0 1 1 -1h9a1 1 0 0 1 1 1v10",
    "M14 15v2a1 1 0 0 1 -1 1h-7l-3 3v-10a1 1 0 0 1 1 -1h2",
  ],
  // clock-hour-4
  cron: ["M3 12a9 9 0 1 0 18 0a9 9 0 1 0 -18 0", "M12 12l3 2", "M12 7v5"],
  // file-text
  logs: [
    "M14 3v4a1 1 0 0 0 1 1h4",
    "M17 21h-10a2 2 0 0 1 -2 -2v-14a2 2 0 0 1 2 -2h7l5 5v11a2 2 0 0 1 -2 2",
    "M9 9l1 0",
    "M9 13l6 0",
    "M9 17l6 0",
  ],
  // brain
  knowledge: [
    "M15.5 13a3.5 3.5 0 0 0 -3.5 3.5v1a3.5 3.5 0 0 0 7 0v-1.8",
    "M8.5 13a3.5 3.5 0 0 1 3.5 3.5v1a3.5 3.5 0 0 1 -7 0v-1.8",
    "M17.5 16a3.5 3.5 0 0 0 0 -7h-.5",
    "M19 9.3v-2.8a3.5 3.5 0 0 0 -7 0",
    "M6.5 16a3.5 3.5 0 0 1 0 -7h.5",
    "M5 9.3v-2.8a3.5 3.5 0 0 1 7 0v10",
  ],
  // send
  send: ["M10 14l11 -11", "M21 3l-6.5 18a.55 .55 0 0 1 -1 0l-3.5 -7l-7 -3.5a.55 .55 0 0 1 0 -1l18 -6.5"],
};

export const ICON_NAMES = Object.keys(PATHS) as IconName[];

export function Icon({ name, size = 24 }: { name: IconName; size?: number }) {
  return (
    <svg
      className="icon"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {PATHS[name].map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
}
