/**
 * Every word a user reads comes from the language files. This test parses
 * each .tsx file with the TypeScript compiler and fails on English left in:
 *  - JSX text (`<p>Hello</p>`),
 *  - user-facing attributes (`placeholder="…"`, `aria-label="…"`, …),
 *  - string literals that are the value of a JSX expression
 *    (`{busy ? "Saving…" : "Save"}`),
 *  - string literals handed to confirm() or a message setter.
 * Brand names in BRANDS may stay; text without letters (↻, ×) is ignored.
 */
import ts from "typescript";
import { describe, expect, it } from "vitest";

const SOURCES = import.meta.glob("../**/*.tsx", { query: "?raw", import: "default", eager: true }) as Record<
  string,
  string
>;

const BRANDS = ["Hermes", "Telegram"];
const TEXT_ATTRS = new Set(["placeholder", "title", "aria-label", "alt", "label", "hint"]);
const MESSAGE_CALLS = new Set(["confirm", "alert", "setError", "setErr", "setFormError", "setFeedback", "setNotice", "setTestMsg"]);

function hasWords(text: string): boolean {
  let rest = text;
  for (const b of BRANDS) rest = rest.split(b).join("");
  return /\p{L}/u.test(rest);
}

/** String or template literal text, or null for anything else. */
function literalText(node: ts.Node): string | null {
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) return node.text;
  if (ts.isTemplateExpression(node)) return [node.head.text, ...node.templateSpans.map((s) => s.literal.text)].join(" ");
  return null;
}

/** Literals that end up as the rendered value of an expression (branches of ?:, ||, ??, &&, parens). */
function renderedLiterals(node: ts.Node): ts.Node[] {
  if (ts.isParenthesizedExpression(node)) return renderedLiterals(node.expression);
  if (ts.isConditionalExpression(node)) return [...renderedLiterals(node.whenTrue), ...renderedLiterals(node.whenFalse)];
  if (ts.isBinaryExpression(node)) {
    const op = node.operatorToken.kind;
    if (op === ts.SyntaxKind.BarBarToken || op === ts.SyntaxKind.QuestionQuestionToken) {
      return [...renderedLiterals(node.left), ...renderedLiterals(node.right)];
    }
    if (op === ts.SyntaxKind.AmpersandAmpersandToken) return renderedLiterals(node.right);
    return [];
  }
  return literalText(node) !== null ? [node] : [];
}

function calleeName(call: ts.CallExpression): string | null {
  const e = call.expression;
  if (ts.isIdentifier(e)) return e.text;
  if (ts.isPropertyAccessExpression(e)) return e.name.text;
  return null;
}

export function findLiterals(fileName: string, source: string): string[] {
  const sf = ts.createSourceFile(fileName, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const hits: string[] = [];
  const report = (node: ts.Node, text: string) => {
    if (!hasWords(text)) return;
    const { line } = sf.getLineAndCharacterOfPosition(node.getStart(sf));
    hits.push(`${fileName}:${line + 1}: ${JSON.stringify(text.trim())}`);
  };
  const visit = (node: ts.Node) => {
    if (ts.isJsxText(node)) {
      report(node, node.text);
    } else if (ts.isJsxAttribute(node) && TEXT_ATTRS.has(node.name.getText(sf))) {
      const init = node.initializer;
      if (init && ts.isStringLiteral(init)) report(init, init.text);
      if (init && ts.isJsxExpression(init) && init.expression) {
        for (const lit of renderedLiterals(init.expression)) report(lit, literalText(lit)!);
      }
    } else if (ts.isJsxExpression(node) && node.expression && !ts.isJsxAttribute(node.parent)) {
      for (const lit of renderedLiterals(node.expression)) report(lit, literalText(lit)!);
    } else if (ts.isCallExpression(node) && MESSAGE_CALLS.has(calleeName(node) ?? "")) {
      for (const arg of node.arguments) for (const lit of renderedLiterals(arg)) report(lit, literalText(lit)!);
    }
    ts.forEachChild(node, visit);
  };
  visit(sf);
  return hits;
}

describe("no hard-coded UI text", () => {
  it("finds the .tsx sources", () => {
    expect(Object.keys(SOURCES).length).toBeGreaterThan(5);
  });

  it("flags each kind of literal and lets brand names and symbols through", () => {
    const sample = `
      const A = () => (
        <div title="Open menu" aria-label={x ? "Yes" : t("k")}>
          Hello
          {busy ? "Saving…" : t("save")}
          {err || "Oops"}
          <b>Hermes</b> ↻ {"×"}
          <i className="pill" style={{ display: "flex" }} />
        </div>
      );
      function f() { confirm(\`Delete \${n}?\`); setError("Bad"); setError(t("ok")); }
    `;
    const hits = findLiterals("sample.tsx", sample).map((h) => h.split(": ").slice(1).join(": "));
    expect(hits).toEqual(['"Open menu"', '"Yes"', '"Hello"', '"Saving…"', '"Oops"', '"Delete  ?"', '"Bad"']);
  });

  it("leaves no English in any component", () => {
    const hits = Object.entries(SOURCES).flatMap(([name, src]) => findLiterals(name, src));
    expect(hits).toEqual([]);
  });
});
