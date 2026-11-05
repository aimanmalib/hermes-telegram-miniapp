/**
 * Tiny i18n: one flat JSON file per language, `t(key, vars)` with `{name}`
 * placeholders and `.one` / `.other` plural keys picked by Intl.PluralRules.
 * No package (a 2-language UI does not need i18next on a public repo).
 *
 * Language choice: saved choice → Telegram `language_code` → English.
 * Adding a language = one JSON file + one entry in DICTS.
 */

import en from "./en.json";
import ms from "./ms.json";

export type Dict = Record<string, string>;

export const DICTS = { en, ms } satisfies Record<string, Dict>;
export type Lang = keyof typeof DICTS;
export const LANGS = Object.keys(DICTS) as Lang[];
export const DEFAULT_LANG: Lang = "en";
export const STORAGE_KEY = "hermes-miniapp.lang";

export function isLang(v: unknown): v is Lang {
  return typeof v === "string" && (LANGS as string[]).includes(v);
}

/** Map a Telegram/BCP-47 code ("ms", "ms-MY", "en-GB") to a supported language. */
export function langFromCode(code: string | null | undefined): Lang | null {
  if (!code) return null;
  const base = code.toLowerCase().split(/[-_]/)[0];
  return isLang(base) ? base : null;
}

/** Saved choice wins, then the Telegram user's language, then English. */
export function pickLang(saved: string | null | undefined, telegramCode: string | null | undefined): Lang {
  if (isLang(saved)) return saved;
  return langFromCode(telegramCode) ?? DEFAULT_LANG;
}

// ---- current language + subscribers --------------------------------------

let current: Lang = DEFAULT_LANG;
const listeners = new Set<() => void>();

export function getLang(): Lang {
  return current;
}

export function subscribeLang(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function readSaved(): string | null {
  try {
    return globalThis.localStorage?.getItem(STORAGE_KEY) ?? null;
  } catch {
    return null;
  }
}

function apply(lang: Lang) {
  current = lang;
  if (typeof document !== "undefined") document.documentElement.lang = locale();
  listeners.forEach((fn) => fn());
}

/** Pick the start language. `override` (demo `?lang=`) is used but not saved. */
export function initLang(telegramCode: string | null | undefined, override?: string | null) {
  apply(isLang(override) ? override : pickLang(readSaved(), telegramCode));
}

/** User choice from the switcher: applied and remembered on this device. */
export function setLang(lang: Lang) {
  try {
    globalThis.localStorage?.setItem(STORAGE_KEY, lang);
  } catch {
    /* storage blocked: the choice still applies for this visit */
  }
  apply(lang);
}

export function locale(lang: Lang = current): string {
  return DICTS[lang]["meta.locale"];
}

// ---- lookup + formatting ---------------------------------------------------

type Vars = Record<string, string | number>;

function lookup(lang: Lang, key: string): string | undefined {
  return (DICTS[lang] as Dict)[key] ?? (DICTS[DEFAULT_LANG] as Dict)[key];
}

/** Translate `key`; a numeric `count` var selects `key.one` / `key.other`. */
export function t(key: string, vars?: Vars, lang: Lang = current): string {
  let text: string | undefined;
  if (typeof vars?.count === "number") {
    const form = new Intl.PluralRules(locale(lang)).select(vars.count);
    text = lookup(lang, `${key}.${form}`) ?? lookup(lang, `${key}.other`);
  }
  text ??= lookup(lang, key) ?? key;
  if (!vars) return text;
  return text.replace(/\{(\w+)\}/g, (whole, name: string) => {
    const v = vars[name];
    if (v === undefined) return whole;
    return typeof v === "number" ? fmtNumber(v, undefined, lang) : v;
  });
}

export function fmtNumber(n: number, opts?: Intl.NumberFormatOptions, lang: Lang = current): string {
  return new Intl.NumberFormat(locale(lang), opts).format(n);
}

export function fmtDate(ms: number, lang: Lang = current): string {
  return new Intl.DateTimeFormat(locale(lang), { dateStyle: "medium" }).format(ms);
}
