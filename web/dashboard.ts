#!/usr/bin/env node
/**
 * Builds a single-file result dashboard from the audiokey manifest.
 *
 * Usage: node --experimental-strip-types dashboard.ts --manifest reports/manifest.json --out reports/dashboard.html
 */

import { readFileSync, writeFileSync } from "node:fs";

type Condition = { queries: number; correct: number; accuracy: number };
type Query = {
  query: string;
  expected: string;
  predicted: string;
  condition: string;
  votes: number;
  margin: number;
  correct: boolean;
};
type Manifest = {
  summary: {
    queries: number;
    correct: number;
    accuracy: number;
    tracks: number;
    indexed_hashes: number;
    build_s: number;
    median_latency_ms: number;
    median_margin: number;
  };
  per_condition: Record<string, Condition>;
  per_query: Query[];
};

function arg(name: string, fallback: string): string {
  const index = process.argv.indexOf(`--${name}`);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
}

const manifest: Manifest = JSON.parse(readFileSync(arg("manifest", "reports/manifest.json"), "utf8"));
const out = arg("out", "reports/dashboard.html");

const html = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>audiokey dashboard</title>
<style>
  :root { --bg:#0b1020; --panel:#121a2c; --line:#26314a; --text:#e6ecf6; --muted:#8fa0b8;
          --good:#22c55e; --bad:#ef4444; --accent:#60a5fa; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font:14px/1.55 ui-sans-serif, system-ui, "Segoe UI", sans-serif; }
  header { padding:18px 22px; border-bottom:1px solid var(--line); display:flex; gap:26px; flex-wrap:wrap; align-items:baseline; }
  h1 { font-size:16px; margin:0; }
  .metric { color:var(--muted); } .metric b { color:var(--text); font-variant-numeric:tabular-nums; }
  main { padding:20px 22px; display:grid; gap:22px; }
  h2 { font-size:13px; text-transform:uppercase; letter-spacing:.08em; color:var(--muted); margin:0 0 10px; }
  .bars { display:grid; gap:8px; max-width:640px; }
  .bar { display:grid; grid-template-columns:90px 1fr 60px; align-items:center; gap:10px; }
  .track { height:10px; background:#1b2440; border-radius:999px; overflow:hidden; }
  .fill { height:100%; background:linear-gradient(90deg,#3b82f6,#22c55e); }
  table { border-collapse:collapse; width:100%; }
  td, th { padding:6px 10px; border-bottom:1px solid var(--line); text-align:left; }
  th { color:var(--muted); font-weight:500; }
  tr.miss td { color:#fca5a5; }
  .ok { color:var(--good); } .no { color:var(--bad); }
</style>
</head>
<body>
<header>
  <h1>audiokey · retrieval</h1>
  <span class="metric">accuracy <b id="a"></b></span>
  <span class="metric">queries <b id="q"></b></span>
  <span class="metric">tracks <b id="t"></b></span>
  <span class="metric">hashes <b id="h"></b></span>
  <span class="metric">latency <b id="l"></b></span>
</header>
<main>
  <section>
    <h2>accuracy by condition</h2>
    <div class="bars" id="bars"></div>
  </section>
  <section>
    <h2>queries</h2>
    <table>
      <thead><tr><th>query</th><th>expected</th><th>predicted</th><th>condition</th><th>votes</th><th>margin</th></tr></thead>
      <tbody id="rows"></tbody>
    </table>
  </section>
</main>
<script>
const DATA = ${JSON.stringify(manifest).replace(/</g, "\\u003c")};
document.getElementById("a").textContent = (DATA.summary.accuracy * 100).toFixed(1) + "%";
document.getElementById("q").textContent = DATA.summary.correct + "/" + DATA.summary.queries;
document.getElementById("t").textContent = DATA.summary.tracks;
document.getElementById("h").textContent = DATA.summary.indexed_hashes.toLocaleString();
document.getElementById("l").textContent = DATA.summary.median_latency_ms + " ms";

const bars = document.getElementById("bars");
for (const [name, bucket] of Object.entries(DATA.per_condition)) {
  const row = document.createElement("div");
  row.className = "bar";
  row.innerHTML = "<span>" + name + "</span><div class='track'><div class='fill' style='width:" +
    (bucket.accuracy * 100).toFixed(0) + "%'></div></div><span>" +
    (bucket.accuracy * 100).toFixed(0) + "%</span>";
  bars.appendChild(row);
}

const rows = document.getElementById("rows");
for (const query of DATA.per_query) {
  const tr = document.createElement("tr");
  if (!query.correct) tr.className = "miss";
  tr.innerHTML = "<td>" + query.query + "</td><td>" + query.expected + "</td><td>" +
    (query.predicted || "—") + "</td><td>" + query.condition + "</td><td>" +
    query.votes + "</td><td>" + query.margin + "x</td>";
  rows.appendChild(tr);
}
</script>
</body>
</html>
`;

writeFileSync(out, html, "utf8");
console.log(`wrote ${out} (${(Buffer.byteLength(html) / 1024).toFixed(0)} KB)`);
