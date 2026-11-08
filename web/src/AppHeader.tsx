import { useEffect, useState } from "react";
import { AuthUser, getHealth } from "./api";
import { DEMO_ENABLED } from "./demo-gate";
import { t } from "./i18n";
import { demoText } from "./i18n/demo-banner";

export type Link = { state: "checking" } | { state: "up"; version: string | null } | { state: "down" };

/** Header subtitle, Telegram style: "Connected · v0.23.0" under the bot name. */
export function linkText(link: Link): string {
  if (link.state === "checking") return t("app.linkChecking");
  if (link.state === "down") return t("app.linkDown");
  return link.version ? t("app.linkUpVersion", { version: link.version }) : t("app.linkUp");
}

function useLink(): Link {
  const [link, setLink] = useState<Link>({ state: "checking" });
  useEffect(() => {
    let cancelled = false;
    getHealth()
      .then((h) => {
        if (cancelled) return;
        const version = h?.hermes_version || null;
        setLink(h?.ok ? { state: "up", version } : { state: "down" });
      })
      .catch(() => {
        if (!cancelled) setLink({ state: "down" });
      });
    return () => {
      cancelled = true;
    };
  }, []);
  return link;
}

export function AppHeader({ user }: { user: AuthUser | null }) {
  const link = useLink();
  const name = user?.first_name ?? user?.username ?? t("app.userFallback");
  return (
    <header className="app-header">
      <div className="app-title">
        <h1>Hermes</h1>
        <p className="app-link" data-state={link.state} role="status">
          <span className="app-link-dot" aria-hidden="true" />
          <span className="app-link-text">{linkText(link)}</span>
        </p>
      </div>
      <div className="app-header-end">
        {DEMO_ENABLED && (
          <span className="demo-pill" title={demoText().detail} aria-label={demoText().detail}>
            {demoText().pill}
          </span>
        )}
        <span className="user-avatar" title={name} aria-label={name}>
          {Array.from(name)[0]?.toUpperCase()}
        </span>
      </div>
    </header>
  );
}
