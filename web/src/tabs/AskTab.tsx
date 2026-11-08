import { useEffect, useRef, useState } from "react";
import { askHermes, getCron, type CronJob } from "../api";
import { ASK_TIMING, type AskPhase, askPhase, isSlow, shouldPoll, stepIndex } from "../ask";
import "../ask.css";
import { SectionTitle, tgHaptic, tgHapticImpact } from "../components";
import { errorText } from "../errors";
import { t, tList } from "../i18n";
import { formatRelative, truncate } from "../utils";
import { AskProgress } from "./AskProgress";

// Keys kept from the Send tab, so saved presets and history carry over.
const HISTORY_KEY = "hermes-tma:send-history-v1";
const PRESETS_KEY = "hermes-tma:send-presets-v1";
// The question in flight survives switching tabs (the tab unmounts).
const CURRENT_KEY = "hermes-tma:ask-current-v1";
const HISTORY_MAX = 12;

/** Starter presets in the current language (`ask.preset.N` in the language files). */
const defaultPresets = () => tList("ask.preset");

interface HistoryEntry {
  text: string;
  ts: number;
}

interface Current {
  id: string;
  prompt: string;
  /** ms since epoch, when the question was asked. */
  started: number;
}

function loadList<T>(key: string, fallback: T, store: Storage = localStorage): T {
  try {
    const raw = store.getItem(key);
    if (!raw) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

function saveList<T>(key: string, value: T, store: Storage = localStorage) {
  try {
    store.setItem(key, JSON.stringify(value));
  } catch {
    /* ignore quota / private mode */
  }
}

/** Polls the Cron list for one Ask job until it is delivered, failed, gone or too old. */
function useAskJob(current: Current | null) {
  const [job, setJob] = useState<CronJob | null>(null);
  const [phase, setPhase] = useState<AskPhase>("queued");
  const [reached, setReached] = useState(0);
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    if (!current) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let last: AskPhase = "queued";
    let first = true; // no buzz for a question that had finished before the tab opened
    setJob(null);
    setPhase("queued");
    setReached(0);
    const tick = async () => {
      try {
        const { jobs } = await getCron();
        if (!alive) return;
        const found = jobs.find((j) => j.id === current.id) ?? null;
        last = askPhase(found);
        setJob(found);
        setPhase(last);
        setReached((r) => Math.max(r, stepIndex(last, r)));
        if (!first && last === "delivered") tgHaptic("success");
        if (!first && last === "failed") tgHaptic("error");
        first = false;
      } catch {
        /* a missed poll is retried on the next tick */
      }
      if (!alive) return;
      const now = Date.now();
      setNowMs(now);
      if (shouldPoll(last, current.started, now)) timer = setTimeout(tick, ASK_TIMING.pollSec * 1000);
    };
    void tick();
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
  }, [current]);

  const stale = !!current && !shouldPoll("queued", current.started, nowMs);
  const slow = !!current && isSlow(current.started, nowMs);
  return { job, phase, reached, slow, stale };
}

export function AskTab() {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [current, setCurrent] = useState<Current | null>(() =>
    loadList<Current | null>(CURRENT_KEY, null, sessionStorage),
  );
  const progress = useAskJob(current);
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
    try {
      const { job } = await askHermes(value);
      const next: Current = { id: job.id, prompt: value, started: Date.now() };
      setCurrent(next);
      saveList(CURRENT_KEY, next, sessionStorage);
      tgHaptic("success");
      setText("");
      const newEntry: HistoryEntry = { text: value, ts: Date.now() / 1000 };
      const nextHistory = [
        newEntry,
        ...history.filter((h) => h.text !== value),
      ].slice(0, HISTORY_MAX);
      setHistory(nextHistory);
      saveList(HISTORY_KEY, nextHistory);
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
      <SectionTitle>{t("ask.title")}</SectionTitle>
      <div className="compose">
        <p
          className="label"
          style={{ margin: "0 0 8px", color: "var(--tg-hint)" }}
        >
          {t("ask.explain")}
        </p>
        <textarea
          ref={textareaRef}
          placeholder={t("ask.placeholder")}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setError(null);
          }}
          rows={4}
        />
        <div className="actions">
          <button
            className="btn-primary"
            disabled={!text.trim() || busy}
            onClick={submit}
          >
            {t(busy ? "ask.asking" : "ask.ask")}
          </button>
        </div>
        {error && (
          <p
            className="label"
            style={{ marginTop: 12, color: "var(--tg-destructive)" }}
          >
            {error}
          </p>
        )}
      </div>
      {current && (
        <AskProgress
          prompt={current.prompt}
          phase={progress.phase}
          reached={progress.reached}
          job={progress.job}
          slow={progress.slow}
          stale={progress.stale}
        />
      )}

      <div className="section-title-row">
        <SectionTitle>{t("ask.presets")}</SectionTitle>
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
          {t("ask.noPresets")}
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
                aria-label={t("ask.removePreset")}
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
            placeholder={t("ask.newPreset")}
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
              {t("ask.restoreDefaults")}
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
            <SectionTitle>{t("ask.recent")}</SectionTitle>
            <button
              type="button"
              className="ghost-btn"
              onClick={clearHistory}
              aria-label={t("ask.clearHistory")}
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
