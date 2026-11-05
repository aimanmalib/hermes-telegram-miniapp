import { afterEach, describe, expect, it } from "vitest";
import { DICTS, initLang, LANGS, langFromCode, pickLang, setLang, STORAGE_KEY, t, type Dict } from "./index";
import { DEMO_BANNER } from "./demo-banner";
import { formatRelative, formatUptime, formatWhen } from "../utils";

const placeholders = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

describe("language files", () => {
  const [base, ...others] = LANGS;
  const baseDict = DICTS[base] as Dict;

  it.each(others)("%s has exactly the same keys as the base language", (lang) => {
    expect(Object.keys(DICTS[lang]).sort()).toEqual(Object.keys(baseDict).sort());
  });

  it.each(LANGS)("%s has no empty strings", (lang) => {
    const empty = Object.entries(DICTS[lang] as Dict).filter(([, v]) => !v.trim());
    expect(empty).toEqual([]);
  });

  it.each(others)("%s uses the same {placeholders} as the base language", (lang) => {
    const dict = DICTS[lang] as Dict;
    const diff = Object.keys(baseDict).filter((k) => placeholders(dict[k]).join() !== placeholders(baseDict[k]).join());
    expect(diff).toEqual([]);
  });

  it.each(LANGS)("%s declares a short label, a name and a valid locale", (lang) => {
    const d = DICTS[lang] as Dict;
    expect(d["meta.short"]).toBeTruthy();
    expect(d["meta.name"]).toBeTruthy();
    expect(() => new Intl.NumberFormat(d["meta.locale"])).not.toThrow();
  });
});

describe("demo banner", () => {
  it("has a non-empty text for every language", () => {
    expect(Object.keys(DEMO_BANNER).sort()).toEqual([...LANGS].sort());
    for (const lang of LANGS) expect(DEMO_BANNER[lang].trim()).not.toBe("");
  });
});

describe("picking the language", () => {
  it("prefers the saved choice, then Telegram's language_code, then English", () => {
    expect(pickLang("ms", "en")).toBe("ms");
    expect(pickLang("en", "ms")).toBe("en");
    expect(pickLang(null, "ms")).toBe("ms");
    expect(pickLang(undefined, "ms-MY")).toBe("ms");
    expect(pickLang("xx", "en-GB")).toBe("en");
    expect(pickLang(null, "id")).toBe("en");
    expect(pickLang(null, undefined)).toBe("en");
  });

  it("maps BCP-47 codes to a supported language", () => {
    expect(langFromCode("MS_my")).toBe("ms");
    expect(langFromCode("fr")).toBeNull();
    expect(langFromCode("")).toBeNull();
  });
});

describe("saving the choice", () => {
  const store = new Map<string, string>();
  const fake = {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
  };

  afterEach(() => {
    store.clear();
    Reflect.deleteProperty(globalThis, "localStorage");
    initLang(null);
  });

  it("remembers the switcher choice over Telegram's language", () => {
    Object.defineProperty(globalThis, "localStorage", { value: fake, configurable: true });
    setLang("ms");
    expect(store.get(STORAGE_KEY)).toBe("ms");
    initLang("en");
    expect(t("tab.sessions")).toBe(DICTS.ms["tab.sessions"]);
  });

  it("uses an override (demo ?lang=) without saving it", () => {
    Object.defineProperty(globalThis, "localStorage", { value: fake, configurable: true });
    initLang("en", "ms");
    expect(t("tab.sessions")).toBe(DICTS.ms["tab.sessions"]);
    expect(store.has(STORAGE_KEY)).toBe(false);
  });
});

describe("t()", () => {
  afterEach(() => initLang(null));

  it("fills placeholders, formats numbers per locale and picks plural forms", () => {
    expect(t("cron.stopped", { name: "Backup" }, "en")).toBe('Stopped "Backup".');
    expect(t("status.sessionCount", { count: 1 }, "en")).toBe("1 session");
    expect(t("status.sessionCount", { count: 1200 }, "en")).toBe("1,200 sessions");
    expect(t("common.msgs", { count: 3 }, "ms")).toBe("3 mesej");
  });

  it("returns the key for a missing entry and keeps unknown placeholders", () => {
    expect(t("no.such.key", undefined, "ms")).toBe("no.such.key");
    expect(t("cron.stopped", {}, "en")).toBe('Stopped "{name}".');
  });

  it("switches the formatters' words with the language", () => {
    const now = Date.now() / 1000;
    initLang("ms");
    expect(formatRelative(now - 3 * 3600)).toBe("3 jam lalu");
    expect(formatWhen(now + 10 * 60 + 5)).toBe("10 min lagi");
    expect(formatUptime(2 * 86400 + 3 * 3600)).toBe("2h 3j");
    initLang("en");
    expect(formatRelative(now - 3 * 3600)).toBe("3h ago");
  });
});
