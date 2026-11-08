import { afterEach, describe, expect, it } from "vitest";
import { linkText } from "./AppHeader";
import { ICON_NAMES } from "./icons";
import { DICTS, LANGS, setLang } from "./i18n";

const TSX = import.meta.glob("./**/*.tsx", { query: "?raw", import: "default", eager: true }) as Record<string, string>;

afterEach(() => setLang("en"));

describe("header status line", () => {
  it("names each connection state", () => {
    expect(linkText({ state: "checking" })).toBe(DICTS.en["app.linkChecking"]);
    expect(linkText({ state: "down" })).toBe(DICTS.en["app.linkDown"]);
    expect(linkText({ state: "up", version: null })).toBe(DICTS.en["app.linkUp"]);
  });

  it("puts the Hermes version from /health after the state", () => {
    const text = linkText({ state: "up", version: "1.2.3" });
    expect(text).toContain("v1.2.3");
    expect(text.startsWith(DICTS.en["app.linkUp"])).toBe(true);
  });

  it("follows the language", () => {
    setLang("ms");
    expect(linkText({ state: "up", version: "1.2.3" })).toContain(DICTS.ms["app.linkUp"]);
  });
});

describe("tab icons", () => {
  it("has an icon for every tab label", () => {
    for (const lang of LANGS) {
      const tabs = Object.keys(DICTS[lang]).filter((k) => k.startsWith("tab."));
      expect(tabs.map((k) => k.slice(4)).sort()).toEqual([...ICON_NAMES].sort());
    }
  });

  it("leaves no emoji standing in for icons in the components", () => {
    const emoji = /\p{Extended_Pictographic}/u;
    const hits = Object.entries(TSX).filter(([, src]) => emoji.test(src)).map(([f]) => f);
    expect(hits).toEqual([]);
  });
});
