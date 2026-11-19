"use strict";
// Numerical integration only: no browser, fixtures or clinical output.
const fs = require("node:fs");
const zlib = require("node:zlib");
const vm = require("node:vm");
const {performance} = require("node:perf_hooks");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const raw = fs.readFileSync(input.artifact);
const release = JSON.parse(input.artifact.endsWith(".gz") ? zlib.gunzipSync(raw).toString("utf8") : raw.toString("utf8"));
let response;
const self = {postMessage: value => { response = value; }};
vm.runInNewContext(fs.readFileSync("static/js/offline-worker.js", "utf8"), {self, performance});
self.onmessage({data:{type:"initialize",release}});
let checks = 0;
for (const item of input.queries) {
  self.onmessage({data:{type:"query",params:item.params}});
  if (!response.ok) throw new Error("El worker rechazó una consulta real válida.");
  const actual = new Map(response.rows.map(row => [row.label,row]));
  if (actual.size !== item.rows.length) throw new Error("No coinciden las categorías online/offline.");
  for (const expected of item.rows) {
    const row = actual.get(expected.label);
    if (!row) throw new Error("Falta una categoría en el worker.");
    for (const key of ["tumors","persons","population","relative_frequency","crude_rate","adjusted_rate","value"]) {
      const a = row[key], b = expected[key];
      if (a === null || b === null ? a !== b : Math.abs(a-b) > .011) throw new Error("Discrepancia online/offline en " + key);
      checks++;
    }
  }
}
console.log("Comprobaciones online/offline aprobadas: " + checks + ".");
