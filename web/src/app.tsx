import { useEffect, useState } from "react";
import { AuthUser, loginWithInitData } from "./api";
import { getTelegramWebApp, TelegramThemeParams } from "./telegram";
import { StatusTab } from "./tabs/StatusTab";
import { SessionsTab } from "./tabs/SessionsTab";
import { SessionDetail } from "./tabs/SessionDetail";
import { CronTab } from "./tabs/CronTab";
import { LogsTab } from "./tabs/LogsTab";
import { KnowledgeTab } from "./tabs/KnowledgeTab";
import { SendTab } from "./tabs/SendTab";
import { DEMO_ENABLED } from "./demo-gate";

type Tab = "status" | "sessions" | "cron" | "logs" | "knowledge" | "send";

interface View {
  tab: Tab;
  sessionId?: string;
  sessionTitle?: string;
}

/**
 * Telegram-like palettes used in demo mode (outside Telegram there are no
 * themeParams). Values follow Telegram's default day / night themes.
 */
const DEMO_THEMES: Record<"light" | "dark", TelegramThemeParams> = {
  light: {
    bg_color: "#ffffff",
    secondary_bg_color: "#f0f2f5",
    section_bg_color: "#ffffff",
    text_color: "#000000",
    hint_color: "#707579",
    link_color: "#3390ec",
    accent_text_color: "#3390ec",
    button_color: "#3390ec",
    button_text_color: "#ffffff",
    destructive_text_color: "#e53935",
  },
  dark: {
    bg_color: "#17212b",
    secondary_bg_color: "#0e1621",
    section_bg_color: "#1f2b38",
    text_color: "#f5f5f5",
    hint_color: "#708499",
    link_color: "#6ab3f3",
    accent_text_color: "#6ab3f3",
    button_color: "#5288c1",
    button_text_color: "#ffffff",
    destructive_text_color: "#ec3942",
  },
};

function demoScheme(): "light" | "dark" {
  const q = new URLSearchParams(window.location.search).get("theme");
  if (q === "light" || q === "dark") return q;
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

const THEME_VARS: [keyof TelegramThemeParams, string][] = [
  ["bg_color", "--tg-bg"],
  ["secondary_bg_color", "--tg-bg-secondary"],
  ["section_bg_color", "--tg-section"],
  ["text_color", "--tg-text"],
  ["hint_color", "--tg-hint"],
  ["link_color", "--tg-link"],
  ["accent_text_color", "--tg-accent"],
  ["button_color", "--tg-button"],
  ["button_text_color", "--tg-button-text"],
  ["destructive_text_color", "--tg-destructive"],
];

function applyTelegramTheme(
  params: TelegramThemeParams,
  scheme: "light" | "dark",
) {
  document.body.dataset.scheme = scheme;
  // Set on <body> as well as <html>: body[data-scheme="light"] declares its own
  // defaults, which would otherwise override Telegram's colours.
  for (const [key, cssVar] of THEME_VARS) {
    const value = params[key];
    if (!value) continue;
    document.documentElement.style.setProperty(cssVar, value);
    document.body.style.setProperty(cssVar, value);
  }
  const meta = document.querySelector('meta[name="theme-color"]');
  const page = params.secondary_bg_color ?? params.bg_color;
  if (meta && page) meta.setAttribute("content", page);
}

/**
 * Fall back to system color-scheme when no Telegram theme is available
 * (i.e. running in a regular browser for local dev / deeplink).
 */
function applySystemColorScheme() {
  const prefersLight =
    window.matchMedia &&
    window.matchMedia("(prefers-color-scheme: light)").matches;
  document.body.dataset.scheme = prefersLight ? "light" : "dark";
}

export function App() {
  const [authState, setAuthState] = useState<"loading" | "ok" | "fail">(
    "loading",
  );
  const [authReason, setAuthReason] = useState<string>("");
  const [user, setUser] = useState<AuthUser | null>(null);
  const [view, setView] = useState<View>({ tab: "status" });

  // ---- Mount: init Telegram + login -------------------------------------
  useEffect(() => {
    const tg = getTelegramWebApp();
    if (DEMO_ENABLED) {
      const scheme = demoScheme();
      applyTelegramTheme(DEMO_THEMES[scheme], scheme);
    } else if (tg) {
      try {
        tg.ready();
        tg.expand();
        applyTelegramTheme(tg.themeParams, tg.colorScheme);
      } catch (e) {
        console.warn("telegram init err", e);
        applySystemColorScheme();
      }
    } else {
      applySystemColorScheme();
    }
    let cancelled = false;
    (async () => {
      try {
        const auth = await loginWithInitData();
        if (cancelled) return;
        if (auth.ok) {
          setUser(auth.user ?? null);
          setAuthState("ok");
        } else {
          setAuthReason(auth.reason ?? "unknown");
          setAuthState("fail");
        }
      } catch (e) {
        if (cancelled) return;
        setAuthReason(String((e as Error).message ?? e));
        setAuthState("fail");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (authState === "loading") {
    return (
      <div className="auth-gate">
        <span className="spinner" />
        <p>Connecting to Hermes…</p>
      </div>
    );
  }

  if (authState === "fail") {
    return (
      <div className="auth-gate">
        <h2>Not authenticated</h2>
        {authReason === "no_init_data" ? (
          <p>
            Open this app from the Telegram bot menu button so it can sign you
            in. Direct browser access is locked.
          </p>
        ) : (
          <p>{authReason}</p>
        )}
      </div>
    );
  }

  const inDetail = view.tab === "sessions" && !!view.sessionId;

  return (
    <div className="app">
      <header className="app-header">
        {DEMO_ENABLED && (
          <div className="demo-banner" role="status">
            Demo data · not connected to Hermes
          </div>
        )}
        <h1>⚡ Hermes</h1>
        <div className="user-chip">
          <span className="dot" />
          <span>{user?.first_name ?? user?.username ?? "you"}</span>
        </div>
      </header>
      <main className="app-content">
        {view.tab === "status" && (
          <StatusTab
            onOpenSession={(id, title) =>
              setView({ tab: "sessions", sessionId: id, sessionTitle: title })
            }
          />
        )}
        {view.tab === "sessions" && !inDetail && (
          <SessionsTab
            onOpen={(id, title) =>
              setView({ tab: "sessions", sessionId: id, sessionTitle: title })
            }
          />
        )}
        {view.tab === "sessions" && inDetail && (
          <SessionDetail
            sessionId={view.sessionId!}
            title={view.sessionTitle ?? "Session"}
            onBack={() => setView({ tab: "sessions" })}
          />
        )}
        {view.tab === "cron" && <CronTab />}
        {view.tab === "logs" && <LogsTab />}
        {view.tab === "knowledge" && <KnowledgeTab />}
        {view.tab === "send" && <SendTab />}
      </main>
      <nav className="tab-bar">
        <TabButton
          active={view.tab === "status"}
          icon="📊"
          label="Status"
          onClick={() => setView({ tab: "status" })}
        />
        <TabButton
          active={view.tab === "sessions"}
          icon="💬"
          label="Sessions"
          onClick={() => setView({ tab: "sessions" })}
        />
        <TabButton
          active={view.tab === "cron"}
          icon="⏱"
          label="Cron"
          onClick={() => setView({ tab: "cron" })}
        />
        <TabButton
          active={view.tab === "logs"}
          icon="📜"
          label="Logs"
          onClick={() => setView({ tab: "logs" })}
        />
        <TabButton
          active={view.tab === "knowledge"}
          icon="🧠"
          label="Brain"
          onClick={() => setView({ tab: "knowledge" })}
        />
        <TabButton
          active={view.tab === "send"}
          icon="✉️"
          label="Send"
          onClick={() => setView({ tab: "send" })}
        />
      </nav>
    </div>
  );
}

function TabButton({
  active,
  icon,
  label,
  onClick,
}: {
  active: boolean;
  icon: string;
  label: string;
  onClick: () => void;
}) {
  return (
    <button data-active={active} onClick={onClick}>
      <span className="tab-icon">{icon}</span>
      {label}
    </button>
  );
}
