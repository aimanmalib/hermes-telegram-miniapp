// Dashboard tab for the telegram-app plugin. Plain IIFE, no build step:
// the Mini App itself is a separate SPA served to Telegram (see README).
(function () {
  "use strict";
  var SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK || !window.__HERMES_PLUGINS__) return;
  var React = SDK.React;
  var h = React.createElement;
  var C = SDK.components;

  function TelegramAppTab() {
    var st = SDK.hooks.useState(null);
    var health = st[0], setHealth = st[1];
    SDK.hooks.useEffect(function () {
      SDK.fetchJSON("/api/plugins/telegram-app/health")
        .then(setHealth)
        .catch(function () { setHealth({ ok: false }); });
    }, []);
    var status = health === null ? "checking…" : health.ok ? "running v" + health.version : "not reachable";
    return h(C.Card, null,
      h(C.CardHeader, null, h(C.CardTitle, null, "Telegram Mini App")),
      h(C.CardContent, null,
        h("p", { className: "text-sm" }, "Backend: " + status),
        h("p", { className: "text-sm text-muted-foreground" },
          "The Mini App opens from your Telegram bot's menu button. Configure TELEGRAM_BOT_TOKEN and " +
          "TELEGRAM_OWNER_ID (or TELEGRAM_ALLOWED_USERS) in your Hermes .env; see the project README."),
      ),
    );
  }

  window.__HERMES_PLUGINS__.register("telegram-app", TelegramAppTab);
})();
