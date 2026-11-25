/* Web Worker: hosts the Python runtime (Pyodide) and the bf_model package,
 * so model runs never block the user interface. */
const PYODIDE_VERSION = "0.26.4";
importScripts(`https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/pyodide.js`);

const SITE_ROOT = new URL("../../", self.location.href);   // /public/
let pyodide = null;

async function loadModelFiles() {
  const base = new URL("bf_model/", SITE_ROOT);
  const manifest = await (await fetch(new URL("manifest.json", base), { cache: "no-cache" })).json();
  const root = "/home/pyodide/bf_model";
  const mkdirs = (path) => {
    let cur = "";
    for (const part of path.split("/").filter(Boolean)) {
      cur += "/" + part;
      try { pyodide.FS.mkdir(cur); } catch (_) { /* exists */ }
    }
  };
  mkdirs(root);
  await Promise.all(manifest.files.map(async (f) => {
    const res = await fetch(new URL(f, base) + `?v=${manifest.version}`, { cache: "no-cache" });
    if (!res.ok) throw new Error(`Cannot load ${f} (${res.status})`);
    const text = await res.text();
    const dir = (root + "/" + f).split("/").slice(0, -1).join("/");
    mkdirs(dir);
    pyodide.FS.writeFile(`${root}/${f}`, text);
  }));
  return manifest.version;
}

async function init() {
  postMessage({ type: "progress", text: "Downloading Python runtime…" });
  pyodide = await loadPyodide();
  postMessage({ type: "progress", text: "Loading blast furnace model…" });
  const version = await loadModelFiles();
  pyodide.runPython(`
import sys
sys.path.insert(0, "/home/pyodide")
import bf_model
`);
  const schema = JSON.parse(pyodide.runPython("bf_model.schema_json()"));
  return { schema, version };
}

const ready = init();
ready.catch((err) => postMessage({ type: "progress", text: `Failed to load: ${err && err.message || err}` }));

self.onmessage = async (e) => {
  const { id, type, payload } = e.data;
  try {
    if (type === "init") {
      const r = await ready;
      postMessage({ id, ok: true, result: r });
    } else if (type === "run") {
      await ready;
      const t0 = performance.now();
      pyodide.globals.set("_inputs_json", JSON.stringify(payload || {}));
      const out = JSON.parse(pyodide.runPython("bf_model.run_json(_inputs_json)"));
      postMessage({ id, ok: true, result: out, ms: performance.now() - t0 });
    }
  } catch (err) {
    postMessage({ id, ok: false, error: String(err && err.message || err) });
  }
};
