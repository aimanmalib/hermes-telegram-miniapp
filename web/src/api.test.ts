import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

type FetchCall = { url: string; init: RequestInit };

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

let calls: FetchCall[];
let replies: Response[];

async function loadApi(initData = "query_id=1&hash=abc") {
  vi.resetModules();
  vi.stubGlobal("window", {
    location: { search: "" },
    Telegram: { WebApp: { initData } },
  });
  vi.stubGlobal("localStorage", { getItem: () => null });
  return import("./api");
}

beforeEach(() => {
  calls = [];
  replies = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit = {}) => {
      calls.push({ url, init });
      const next = replies.shift();
      if (!next) throw new Error(`unexpected fetch ${url}`);
      return next;
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("loginWithInitData", () => {
  it("posts initData and caches the session token", async () => {
    const api = await loadApi("query_id=1&hash=abc");
    replies.push(jsonResponse(200, { ok: true, session_token: "tok", user: { id: 7 } }));
    const res = await api.loginWithInitData();
    expect(res.ok).toBe(true);
    expect(calls[0].url).toBe("/api/plugins/telegram-app/auth/verify");
    expect(calls[0].init.method).toBe("POST");
    expect(JSON.parse(String(calls[0].init.body))).toEqual({ init_data: "query_id=1&hash=abc" });
    expect(api.getCachedToken()).toBe("tok");
    expect(api.getLastUser()).toEqual({ id: 7 });
  });

  it("reports no_init_data outside Telegram without calling the server", async () => {
    const api = await loadApi("");
    const res = await api.loginWithInitData();
    expect(res).toEqual({ ok: false, reason: "no_init_data" });
    expect(calls).toHaveLength(0);
  });

  it("throws with the status on a rejected login", async () => {
    const api = await loadApi();
    replies.push(jsonResponse(403, { detail: "Invalid Telegram initData" }));
    await expect(api.loginWithInitData()).rejects.toThrow(/auth\/verify 403/);
    expect(api.getCachedToken()).toBeNull();
  });
});

describe("api()", () => {
  it("sends the session token header", async () => {
    const api = await loadApi();
    replies.push(jsonResponse(200, { ok: true, session_token: "tok" }));
    await api.loginWithInitData();
    replies.push(jsonResponse(200, { jobs: [] }));
    await api.getCron();
    const headers = calls[1].init.headers as Record<string, string>;
    expect(calls[1].url).toBe("/api/plugins/telegram-app/cron");
    expect(headers["X-Hermes-Session-Token"]).toBe("tok");
  });

  it("re-logs in once on 401 and retries the call", async () => {
    const api = await loadApi();
    replies.push(jsonResponse(200, { ok: true, session_token: "old" }));
    await api.loginWithInitData();
    replies.push(jsonResponse(401, { detail: "Unauthorized" }));
    replies.push(jsonResponse(200, { ok: true, session_token: "new" }));
    replies.push(jsonResponse(200, { cpu_pct: 1 }));
    const status = await api.getStatus();
    expect(status).toEqual({ cpu_pct: 1 });
    expect(calls.map((c) => c.url)).toEqual([
      "/api/plugins/telegram-app/auth/verify",
      "/api/plugins/telegram-app/status",
      "/api/plugins/telegram-app/auth/verify",
      "/api/plugins/telegram-app/status",
    ]);
    expect((calls[3].init.headers as Record<string, string>)["X-Hermes-Session-Token"]).toBe("new");
  });

  it("does not loop when the retry is still unauthorized", async () => {
    const api = await loadApi();
    replies.push(jsonResponse(401, {}));
    replies.push(jsonResponse(200, { ok: true, session_token: "t" }));
    replies.push(jsonResponse(401, { detail: "Unauthorized" }));
    await expect(api.getStatus()).rejects.toThrow(/\/status 401/);
    expect(calls).toHaveLength(3);
  });

  it("encodes ids in paths", async () => {
    const api = await loadApi();
    replies.push(jsonResponse(200, { ok: true }));
    await api.cronAction("a/../b", "pause");
    expect(calls[0].url).toBe("/api/plugins/telegram-app/cron/a%2F..%2Fb/pause");
  });

  it("returns undefined for non-JSON success responses", async () => {
    const api = await loadApi();
    replies.push(new Response(null, { status: 204 }));
    await expect(api.cronDelete("x")).resolves.toBeUndefined();
  });
});

describe("demo mode is off in normal builds", () => {
  it("does not enable demo mode without a demo build or ?demo=1", async () => {
    vi.resetModules();
    vi.stubGlobal("window", { location: { search: "" } });
    const gate = await import("./demo-gate");
    expect(gate.DEMO_ENABLED).toBe(false);
  });
});
