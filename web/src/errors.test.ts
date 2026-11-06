import { afterEach, describe, expect, it } from "vitest";
import { ApiError, apiErrorFrom, DETAIL_MAX, errorText } from "./errors";
import { DICTS, initLang } from "./i18n";

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

afterEach(() => initLang(null));

describe("apiErrorFrom", () => {
  it("reads a string detail", async () => {
    const e = await apiErrorFrom("/cron", json(400, { detail: "bad schedule" }));
    expect([e.status, e.detail, e.code]).toEqual([400, "bad schedule", null]);
    expect(e.message).toBe("/cron 400: bad schedule");
  });

  it("reads a {code, message} detail", async () => {
    const e = await apiErrorFrom("/cron/x/cancel", json(501, { detail: { code: "unsupported", message: "no" } }));
    expect([e.code, e.detail]).toEqual(["unsupported", "no"]);
  });

  it("keeps only the status for a non-JSON body", async () => {
    const e = await apiErrorFrom("/status", new Response("<html>Bad gateway</html>", { status: 502 }));
    expect([e.status, e.detail]).toEqual([502, null]);
  });
});

describe("errorText", () => {
  it("words each status class in the current language", () => {
    initLang("en");
    expect(errorText(new ApiError("/x", 404))).toBe(DICTS.en["error.notFound"]);
    expect(errorText(new ApiError("/x", 503))).toBe(DICTS.en["error.unavailable"]);
    expect(errorText(new ApiError("/x", 500))).toBe("Hermes ran into an error (HTTP 500).");
    expect(errorText(new ApiError("/x", 418))).toBe("Request failed (HTTP 418).");
    initLang("ms");
    expect(errorText(new ApiError("/x", 404))).toBe(DICTS.ms["error.notFound"]);
  });

  it("prefers a translated backend code over the status", () => {
    initLang("ms");
    const e = new ApiError("/cron/x/cancel", 501, "This Hermes cannot stop a running job", "unsupported");
    expect(errorText(e)).toBe(`${DICTS.ms["error.code.unsupported"]} (This Hermes cannot stop a running job)`);
    expect(errorText(new ApiError("/x", 501, null, "no_such_code"))).toBe(DICTS.ms["error.unsupported"]);
  });

  it("adds the backend detail where it helps, never on sign-in refusals", () => {
    initLang("en");
    expect(errorText(new ApiError("/cron", 400, "bad cron expression"))).toBe(
      `${DICTS.en["error.badRequest"]} (bad cron expression)`,
    );
    for (const status of [401, 403, 429]) {
      expect(errorText(new ApiError("auth/verify", status, "Invalid Telegram initData"))).not.toContain("initData");
    }
  });

  it("shortens a long detail", () => {
    const text = errorText(new ApiError("/x", 500, "y".repeat(DETAIL_MAX + 50)));
    expect(text).toContain(`${"y".repeat(DETAIL_MAX)}…)`);
    expect(text).not.toContain("y".repeat(DETAIL_MAX + 1));
  });

  it("calls a failed fetch a network problem and passes other errors through", () => {
    initLang("en");
    expect(errorText(new TypeError("Failed to fetch"))).toBe(DICTS.en["error.network"]);
    expect(errorText(new Error("boom"))).toBe("boom");
    expect(errorText("plain")).toBe("plain");
  });
});
