// Fails if the production bundle (../dist) contains demo-mode code or data.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const root = new URL("../../dist/", import.meta.url).pathname;
// Banner text and sample data. (src/demo-stub.ts may appear: it holds no data.)
const needles = ["Demo data", "Backup restore drill", "Fix flaky checkout test", "not available in demo mode"];

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}

let files;
try {
  files = walk(root).filter((f) => /\.(js|html|css)$/.test(f));
} catch {
  console.error(`check-no-demo: ${root} not found, run \`npm run build\` first`);
  process.exit(2);
}
const hits = files.flatMap((f) => {
  const text = readFileSync(f, "utf8");
  return needles.filter((n) => text.includes(n)).map((n) => `${f}: "${n}"`);
});
if (hits.length) {
  console.error("Demo code leaked into the production bundle:\n" + hits.join("\n"));
  process.exit(1);
}
console.log(`check-no-demo: ok (${files.length} files, no demo code)`);
