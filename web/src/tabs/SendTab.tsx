import { useRef, useState } from "react";
import { sendCommand } from "../api";
import { SectionTitle, tgHaptic, tgHapticImpact } from "../components";
import { errorText } from "../errors";
import { t, tList } from "../i18n";
import { formatRelative, truncate } from "../utils";

const HISTORY_KEY = "hermes-tma:send-history-v1";
const PRESETS_KEY = "hermes-tma:send-presets-v1";
const HISTORY_MAX = 12;

/** Starter presets in the current language (`send.preset.N` in the language files). */
const defaultPresets = () => tList("send.preset");

interface HistoryEntry {
  text: string;
  ts: number;
}

function loadList<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

function saveList<T>(key: string, value: T) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* ignore quota / private mode */
  }
}

export function SendTab() {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>(() =>
    loadList<HistoryEntry[]>(HISTORY_KEY, []),
  );
  // null = the user never edited the list, so it follows the app language.
  const [custom, setCustom] = useState<string[] | null>(() =>
    loadList<string[] | null>(PRESETS_KEY, null),
  );
  const presets = custom ?? defaultPresets();
  const [editingPresets, setEditingPresets] = useState(false);
  const [newPreset, setNewPreset] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const fillFrom = (s: string) => {
    setText(s);
    tgHapticImpact("light");
    textareaRef.current?.focus();
  };

  const submit = async () => {
    const value = text.trim();
    if (!value || busy) return;
    setBusy(true);
    setError(null);
    setFeedback(null);
    try {
      await sendCommand(value);
      setFeedback(t("send.posted"));
      tgHaptic("success");
      setText("");
      const newEntry: HistoryEntry = { text: value, ts: Date.now() / 1000 };
      const next = [
        newEntry,
        ...history.filter((h) => h.text !== value),
      ].slice(0, HISTORY_MAX);
      setHistory(next);
      saveList(HISTORY_KEY, next);
    } catch (e) {
      setError(errorText(e));
      tgHaptic("error");
    } finally {
      setBusy(false);
    }
  };

  const addPreset = () => {
    const v = newPreset.trim();
    if (!v) return;
    if (presets.includes(v)) {
      setNewPreset("");
      return;
    }
    const next = [...presets, v];
    setCustom(next);
    saveList(PRESETS_KEY, next);
    setNewPreset("");
    tgHaptic("success");
  };

  const removePreset = (s: string) => {
    const next = presets.filter((p) => p !== s);
    setCustom(next);
    saveList(PRESETS_KEY, next);
    tgHapticImpact("light");
  };

  const restoreDefaults = () => {
    setCustom(null);
    try {
      localStorage.removeItem(PRESETS_KEY);
    } catch {
      /* ignore private mode */
    }
    tgHaptic("success");
  };

  const clearHistory = () => {
    setHistory([]);
    saveList(HISTORY_KEY, []);
    tgHapticImpact("medium");
  };

  return (
    <>
      <SectionTitle>{t("send.title")}</SectionTitle>
      <div className="compose">
        <p
          className="label"
          style={{ margin: "0 0 8px", color: "var(--tg-hint)" }}
        >
          {t("send.explain")}
        </p>
        <textarea
          ref={textareaRef}
          placeholder={t("send.placeholder")}
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={5}
        />
        <div className="actions">
          <button
            className="btn-primary"
            disabled={!text.trim() || busy}
            onClick={submit}
          >
            {t(busy ? "send.sending" : "send.send")}
          </button>
        </div>
        {feedback && (
          <p
            className="label"
            style={{ marginTop: 12, color: "var(--tg-accent)" }}
          >
            {feedback}
          </p>
        )}
        {error && (
          <p
            className="label"
            style={{ marginTop: 12, color: "var(--tg-destructive)" }}
          >
            {error}
          </p>
        )}
      </div>

      <div className="section-title-row">
        <SectionTitle>{t("send.presets")}</SectionTitle>
        <button
          type="button"
          className="ghost-btn"
          onClick={() => setEditingPresets((v) => !v)}
        >
          {t(editingPresets ? "common.done" : "common.edit")}
        </button>
      </div>
      {presets.length === 0 && (
        <div className="empty" style={{ paddingTop: 0 }}>
          {t("send.noPresets")}
        </div>
      )}
      <div className="chips">
        {presets.map((p) => (
          <div key={p} className="chip-wrap">
            <button
              type="button"
              className="chip"
              onClick={() => fillFrom(p)}
              title={p}
            >
              {truncate(p, 60)}
            </button>
            {editingPresets && (
              <button
                type="button"
                className="chip-x"
                aria-label={t("send.removePreset")}
                onClick={() => removePreset(p)}
              >
                ×
              </button>
            )}
          </div>
        ))}
      </div>
      {editingPresets && (
        <div className="compose" style={{ marginTop: 0 }}>
          <textarea
            placeholder={t("send.newPreset")}
            value={newPreset}
            onChange={(e) => setNewPreset(e.target.value)}
            rows={2}
          />
          <div className="actions" style={{ gap: 8 }}>
            <button
              type="button"
              className="btn-secondary"
              onClick={restoreDefaults}
            >
              {t("send.restoreDefaults")}
            </button>
            <button
              type="button"
              className="btn-primary"
              disabled={!newPreset.trim()}
              onClick={addPreset}
            >
              {t("common.add")}
            </button>
          </div>
        </div>
      )}

      {history.length > 0 && (
        <>
          <div className="section-title-row">
            <SectionTitle>{t("send.recent")}</SectionTitle>
            <button
              type="button"
              className="ghost-btn"
              onClick={clearHistory}
              aria-label={t("send.clearHistory")}
            >
              {t("common.clear")}
            </button>
          </div>
          {history.map((h, i) => (
            <button
              key={i}
              type="button"
              className="list-item tappable history-row"
              onClick={() => fillFrom(h.text)}
            >
              <div className="item-preview" style={{ whiteSpace: "normal" }}>
                {truncate(h.text, 140)}
              </div>
              <div className="item-meta">
                <span style={{ marginLeft: "auto" }}>
                  {formatRelative(h.ts)}
                </span>
              </div>
            </button>
          ))}
        </>
      )}
    </>
  );
}
