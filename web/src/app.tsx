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
import { AppHeader } from "./AppHeader";
import { Icon } from "./icons";
import { initLang, t } from "./i18n";
import { useLang } from "./i18n/useLang";
import { errorText } from "./errors";

type Tab = "status" | "sessions" | "cron" | "logs" | "knowledge" | "send";

/** Tab bar order. Each name is also its icon (icons.tsx) and its `tab.*` label key. */
const TABS: Tab[] = ["status", "sessions", "cron", "logs", "knowledge", "send"];

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
  useLang();

  // ---- Mount: init Telegram + login -------------------------------------
  useEffect(() => {
    const tg = getTelegramWebApp();
    initLang(
      tg?.initDataUnsafe?.user?.language_code,
      DEMO_ENABLED ? new URLSearchParams(window.location.search).get("lang") : null,
    );
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
        setAuthReason(errorText(e));
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
        <p>{t("app.connecting")}</p>
      </div>
    );
  }

  if (authState === "fail") {
    return (
      <div className="auth-gate">
        <h2>{t("app.notAuthenticated")}</h2>
        {authReason === "no_init_data" ? (
          <p>{t("app.openFromBot")}</p>
        ) : (
          <p>{authReason}</p>
        )}
      </div>
    );
  }

  const inDetail = view.tab === "sessions" && !!view.sessionId;

  return (
    <div className="app">
      <AppHeader user={user} />
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
            title={view.sessionTitle ?? t("sessions.fallbackTitle")}
            onBack={() => setView({ tab: "sessions" })}
          />
        )}
        {view.tab === "cron" && <CronTab />}
        {view.tab === "logs" && <LogsTab />}
        {view.tab === "knowledge" && <KnowledgeTab />}
        {view.tab === "send" && <SendTab />}
      </main>
      <nav className="tab-bar">
        {TABS.map((tab) => (
          <TabButton
            key={tab}
            tab={tab}
            active={view.tab === tab}
            onClick={() => setView({ tab })}
          />
        ))}
      </nav>
    </div>
  );
}

function TabButton({
  tab,
  active,
  onClick,
}: {
  tab: Tab;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button data-active={active} aria-current={active ? "page" : undefined} onClick={onClick}>
      <Icon name={tab} />
      <span className="tab-label">{t(`tab.${tab}`)}</span>
    </button>
  );
}
