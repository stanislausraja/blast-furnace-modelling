/* Interactive SVG drawing of the blast furnace, built entirely from model output
 * (geometry, temperature profile, cohesive zone, zone summaries). */

const NS = "http://www.w3.org/2000/svg";

const CMAP = [
  [0, [11, 11, 38]], [150, [42, 11, 87]], [350, [92, 18, 110]], [550, [138, 34, 106]],
  [750, [183, 55, 89]], [950, [221, 81, 56]], [1150, [243, 120, 25]], [1350, [252, 165, 10]],
  [1650, [246, 215, 70]], [2100, [252, 255, 164]],
];

export function tempColor(T, a = 1) {
  let i = 0;
  while (i < CMAP.length - 2 && T > CMAP[i + 1][0]) i++;
  const [t0, c0] = CMAP[i], [t1, c1] = CMAP[i + 1];
  const f = Math.max(0, Math.min(1, (T - t0) / (t1 - t0)));
  const c = c0.map((v, k) => Math.round(v + f * (c1[k] - v)));
  return a === 1 ? `rgb(${c})` : `rgba(${c},${a})`;
}
export const CMAP_CSS = `linear-gradient(90deg, ${CMAP.map(([t]) => `${tempColor(t)} ${(t / 2100 * 100).toFixed(1)}%`).join(",")})`;

function el(tag, attrs = {}, parent) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null) e.setAttribute(k, v);
  if (parent) parent.appendChild(e);
  return e;
}
function txt(parent, x, y, s, cls, attrs = {}) {
  const t = el("text", { x, y, class: cls, ...attrs }, parent);
  t.textContent = s;
  return t;
}

export function renderFurnace(container, ov, opts = {}) {
  const mode = opts.mode || "process";
  container.innerHTML = "";
  if (!ov) return;
  const W = 660, H = 900, TOP = 140, BOT = 70;
  const zTop = ov.z_top;
  const k = (H - TOP - BOT) / zTop;
  const prof = ov.profile;                       // [[z, r]]
  const Rmax = Math.max(...prof.map((p) => p[1]));
  const cx = 70 + (Rmax + 2.2) * k;
  const X = (r) => cx + r * k;
  const Y = (z) => H - BOT - z * k;
  const zt = ov.z_tuyere, zs = ov.z_stockline;
  const radius = (z) => {
    if (z <= prof[0][0]) return prof[0][1];
    for (let i = 1; i < prof.length; i++) {
      if (z <= prof[i][0]) {
        const [z0, r0] = prof[i - 1], [z1, r1] = prof[i];
        return z1 === z0 ? r1 : r0 + (r1 - r0) * (z - z0) / (z1 - z0);
      }
    }
    return prof[prof.length - 1][1];
  };

  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Blast furnace cross-section" }, container);
  const defs = el("defs", {}, svg);

  // ---------------------------------------------------------- definitions
  const innerD = (() => {
    let d = `M ${X(prof[0][1])} ${Y(0)}`;
    for (const [z, r] of prof) d += ` L ${X(r)} ${Y(z)}`;
    for (const [z, r] of [...prof].reverse()) d += ` L ${X(-r)} ${Y(z)}`;
    return d + " Z";
  })();
  const clipInner = el("clipPath", { id: "clip-inner" }, defs);
  el("path", { d: innerD }, clipInner);

  const glow = el("filter", { id: "glow", x: "-50%", y: "-50%", width: "200%", height: "200%" }, defs);
  el("feGaussianBlur", { stdDeviation: 6, result: "b" }, glow);
  const m = el("feMerge", {}, glow);
  el("feMergeNode", { in: "b" }, m); el("feMergeNode", { in: "SourceGraphic" }, m);

  const rw = el("radialGradient", { id: "raceway-g" }, defs);
  [[0, "#ffffff", 1], [0.35, "#fff3a0", 0.95], [0.7, "#ff9a1f", 0.7], [1, "#ff5a1f", 0]].forEach(([o, c, a]) =>
    el("stop", { offset: o, "stop-color": c, "stop-opacity": a }, rw));
  const hmG = el("linearGradient", { id: "hm-g", x1: 0, y1: 1, x2: 0, y2: 0 }, defs);
  el("stop", { offset: 0, "stop-color": "#ff6a00" }, hmG); el("stop", { offset: 1, "stop-color": "#ffc04a" }, hmG);
  const slagG = el("linearGradient", { id: "slag-g", x1: 0, y1: 1, x2: 0, y2: 0 }, defs);
  el("stop", { offset: 0, "stop-color": "#d99a2b" }, slagG); el("stop", { offset: 1, "stop-color": "#8a6a2a" }, slagG);
  const cokeP = el("pattern", { id: "coke-p", width: 9, height: 9, patternUnits: "userSpaceOnUse" }, defs);
  el("circle", { cx: 2.5, cy: 2.5, r: 2.1, fill: "rgba(20,20,22,0.75)" }, cokeP);
  el("circle", { cx: 7, cy: 6.8, r: 1.7, fill: "rgba(35,35,38,0.7)" }, cokeP);
  const hatch = el("pattern", { id: "hatch", width: 6, height: 6, patternUnits: "userSpaceOnUse", patternTransform: "rotate(35)" }, defs);
  el("line", { x1: 0, y1: 0, x2: 0, y2: 6, stroke: "rgba(255,240,200,0.35)", "stroke-width": 2 }, hatch);
  const arrow = el("marker", { id: "arrow", viewBox: "0 0 10 10", refX: 5, refY: 5, markerWidth: 5, markerHeight: 5, orient: "auto-start-reverse" }, defs);
  el("path", { d: "M0,0 L10,5 L0,10 z", fill: "#cfd6e0" }, arrow);

  // ---------------------------------------------------------- temperature helpers
  const temp = ov.temp || [];
  const zOfT = (T) => {               // height where solid temperature drops below T
    if (!temp.length) return null;
    if (T >= temp[0][2]) return zt;
    for (let i = 1; i < temp.length; i++) {
      const [za, , ta] = temp[i - 1], [zb, , tb] = temp[i];
      if (ta >= T && tb < T) return za + (T - ta) * (zb - za) / (tb - ta);
    }
    return zs;
  };
  const s = ov.center_index || 0;
  const shift = (x, z) => {
    const r = radius(z);
    const xi = Math.min(Math.abs(x) / r, 1);
    return (s * (1 - xi * xi) - 0.25 * s) * Math.min(1, Math.max(0, (z - zt) / 3));
  };
  const isoCurve = (T, n = 48) => {
    const z1 = zOfT(T);
    if (z1 === null) return null;
    const pts = [];
    for (let i = 0; i <= n; i++) {
      const x = -Rmax + 2 * Rmax * i / n;
      const z = Math.min(Math.max(z1 + shift(x, z1), zt), zs);
      pts.push([x, z]);
    }
    return pts;
  };
  const Tsolid = (x, z) => {         // 2-D solid temperature, same formula as the Python field
    if (z <= zt) return ov.t_hm;
    const ze = Math.max(z - shift(x, z), zt);
    for (let i = 1; i < temp.length; i++) {
      if (temp[i][0] >= ze) {
        const [za, , ta] = temp[i - 1], [zb, , tb] = temp[i];
        return ta + (tb - ta) * (ze - za) / (zb - za);
      }
    }
    return temp.length ? temp[temp.length - 1][2] : 25;
  };
  const curveD = (pts) => pts.map(([x, z], i) => `${i ? "L" : "M"} ${X(x).toFixed(1)} ${Y(z).toFixed(1)}`).join(" ");

  // ---------------------------------------------------------- shell, refractory
  const shell = el("g", {}, svg);
  const outer = (off, zb) => {
    let d = `M ${X(prof[0][1] + off)} ${Y(zb)}`;
    for (const [z, r] of prof) d += ` L ${X(r + off)} ${Y(z)}`;
    for (const [z, r] of [...prof].reverse()) d += ` L ${X(-r - off)} ${Y(z)}`;
    return d + ` L ${X(-prof[0][1] - off)} ${Y(zb)} Z`;
  };
  el("path", { d: outer(1.05, -1.4), fill: "#2c323c", stroke: "#4a5260", "stroke-width": 1.5 }, shell);
  el("path", { d: outer(0.75, -1.1), fill: "#5a3a2c" }, shell);
  el("path", { d: outer(0.75, -1.1), fill: "url(#hatch)", opacity: 0.15 }, shell);
  // stave cooling marks
  for (let z = zt + 1; z < zTop - 0.5; z += 1.4) {
    const r = radius(z);
    el("line", { x1: X(r + 0.78), x2: X(r + 1.02), y1: Y(z), y2: Y(z), stroke: "#5fa8d3", "stroke-width": 2, opacity: 0.5 }, shell);
    el("line", { x1: X(-r - 0.78), x2: X(-r - 1.02), y1: Y(z), y2: Y(z), stroke: "#5fa8d3", "stroke-width": 2, opacity: 0.5 }, shell);
  }

  // ---------------------------------------------------------- top equipment
  const rt = prof[prof.length - 1][1];
  const top = el("g", {}, svg);
  el("path", { d: `M ${X(-rt - 1.05)} ${Y(zTop)} Q ${X(0)} ${Y(zTop + 3.2)} ${X(rt + 1.05)} ${Y(zTop)} Z`, fill: "#2c323c", stroke: "#4a5260", "stroke-width": 1.5 }, top);
  el("path", { d: `M ${X(-rt)} ${Y(zTop)} Q ${X(0)} ${Y(zTop + 2.6)} ${X(rt)} ${Y(zTop)} Z`, fill: "#11151b" }, top);
  // uptakes
  for (const sgn of [-1, 1]) {
    const x0 = sgn * rt * 0.55;
    el("path", { d: `M ${X(x0 - 0.55)} ${Y(zTop + 1.2)} L ${X(x0 - 0.55)} ${Y(zTop + 4.6)} L ${X(x0 + 0.55)} ${Y(zTop + 4.6)} L ${X(x0 + 0.55)} ${Y(zTop + 1.2)} Z`,
      fill: "#2c323c", stroke: "#4a5260" }, top);
    el("line", { x1: X(x0), x2: X(x0), y1: Y(zTop + 1.4), y2: Y(zTop + 4.9), stroke: "#cfd6e0", "stroke-width": 1.5,
      "stroke-dasharray": "5 7", class: "gas-line", "marker-end": "url(#arrow)" }, top);
  }
  // hopper + chute
  el("path", { d: `M ${X(-1.6)} ${Y(zTop + 5.6)} L ${X(1.6)} ${Y(zTop + 5.6)} L ${X(0.45)} ${Y(zTop + 3.6)} L ${X(-0.45)} ${Y(zTop + 3.6)} Z`,
    fill: "#3a414d", stroke: "#5b6575" }, top);
  el("rect", { x: X(-0.28), y: Y(zTop + 3.6), width: 0.56 * k, height: 2.1 * k, fill: "#3a414d", stroke: "#5b6575" }, top);
  // rotating distribution chute (swings from one side to the other)
  const chute = el("line", { x1: X(0), y1: Y(zTop + 1.4), x2: X(rt * 0.55), y2: Y(zs + 0.6), stroke: "#8a94a6", "stroke-width": 4, "stroke-linecap": "round" }, top);
  const pivot = `${X(0)} ${Y(zTop + 1.4)}`;
  const swing = -2 * Math.atan(rt * 0.55 / (zTop + 1.4 - zs - 0.6)) * 180 / Math.PI;
  el("animateTransform", { attributeName: "transform", type: "rotate", values: `0 ${pivot}; ${swing} ${pivot}; 0 ${pivot}`, dur: "4s", repeatCount: "indefinite" }, chute);
  txt(top, X(-1.8), Y(zTop + 5.9), "Burden charging (bell-less top)", "svg-small", { "text-anchor": "end" });
  const flows = ov.flows || {};
  const topZone = (ov.zone_info || []).find((z) => z.name === "Throat");
  txt(top, X(rt * 0.55 + 0.8), Y(zTop + 4.4), "Top gas", "svg-label");
  if (temp.length) txt(top, X(rt * 0.55 + 0.8), Y(zTop + 3.7), `${Math.round(temp[temp.length - 1][1])} °C · ${(flows.gas_nm3 || 0).toFixed(0)} kNm³/h`, "svg-sub");

  // ---------------------------------------------------------- furnace interior
  const inner = el("g", { "clip-path": "url(#clip-inner)" }, svg);
  el("rect", { x: 0, y: 0, width: W, height: H, fill: "#0c0f14" }, inner);
  // temperature bands (painter's algorithm, coldest first)
  const levels = [];
  for (let T = 100; T <= 2000; T += 50) levels.push(T);
  const baseOpacity = mode === "thermal" ? 1 : 0.75;
  el("rect", { x: 0, y: Y(zs), width: W, height: Y(zt) - Y(zs), fill: tempColor(25), opacity: baseOpacity }, inner);
  const Tmax = temp.length ? temp[0][2] : 1500;
  for (const T of levels) {
    if (T > Tmax + 50) break;
    const c = isoCurve(T);
    if (!c) continue;
    const d = curveD(c) + ` L ${X(Rmax)} ${Y(zt)} L ${X(-Rmax)} ${Y(zt)} Z`;
    el("path", { d, fill: tempColor(Math.min(T + 25, Tmax)), opacity: baseOpacity }, inner);
  }
  // gas space above stockline
  el("rect", { x: 0, y: 0, width: W, height: Y(zs), fill: "#10141a" }, inner);

  const curveSoft = ov.z_soft != null ? isoCurveAtZ(ov.z_soft) : null;
  const curveMelt = ov.z_melt != null ? isoCurveAtZ(ov.z_melt) : (ov.z_soft != null ? isoCurveAtZ(zt) : null);
  function isoCurveAtZ(z1, n = 48) {
    const pts = [];
    for (let i = 0; i <= n; i++) {
      const x = -Rmax + 2 * Rmax * i / n;
      pts.push([x, Math.min(Math.max(z1 + shift(x, z1), zt), zs)]);
    }
    return pts;
  }

  if (mode === "process") {
    // granular zone: alternate ore / coke layers, slowly descending
    const burdenClip = el("clipPath", { id: "clip-burden" }, defs);
    const bTop = zs, bBottom = curveSoft || isoCurveAtZ(zt + 2);
    el("path", { d: curveD(bBottom) + ` L ${X(Rmax)} ${Y(bTop)} L ${X(-Rmax)} ${Y(bTop)} Z` }, burdenClip);
    const gB = el("g", { "clip-path": "url(#clip-burden)" }, inner);
    const mover = el("g", {}, gB);
    const period = 1.25, tOre = 0.72;
    const layerPath = (zb, th) => {
      const n = 30, up = [], dn = [];
      for (let i = 0; i <= n; i++) {
        const x = -Rmax + 2 * Rmax * i / n;
        const dip = 0.55 * Math.abs(x) / Rmax;
        up.push([x, zb + dip]); dn.push([x, zb + dip + th]);
      }
      return curveD(up) + " " + curveD(dn.reverse()).replace("M", "L") + " Z";
    };
    for (let z = zt - period; z < zs + 2 * period; z += period) {
      el("path", { d: layerPath(z, tOre), fill: "rgba(140,58,26,0.42)" }, mover);
      el("path", { d: layerPath(z + tOre, period - tOre), fill: "url(#coke-p)" }, mover);
      el("path", { d: layerPath(z + tOre, period - tOre), fill: "rgba(10,10,12,0.35)" }, mover);
    }
    el("animateTransform", { attributeName: "transform", type: "translate", from: "0 0", to: `0 ${period * k}`, dur: "6s", repeatCount: "indefinite" }, mover);

    // cohesive zone
    if (curveSoft && curveMelt) {
      const d = curveD(curveSoft) + " " + curveD([...curveMelt].reverse()).replace("M", "L") + " Z";
      el("path", { d, fill: "rgba(150,60,20,0.7)" }, inner);
      el("path", { d, fill: "url(#hatch)" }, inner);
      el("path", { d: curveD(curveSoft), fill: "none", stroke: "#7CFC9A", "stroke-width": 2, "stroke-dasharray": "6 4" }, inner);
      el("path", { d: curveD(curveMelt), fill: "none", stroke: "#7CFC9A", "stroke-width": 2, "stroke-dasharray": "6 4" }, inner);
    }
    // dripping zone: active coke + droplets
    const dripTop = curveMelt || isoCurveAtZ(zt + 1.5);
    const dD = curveD(dripTop) + ` L ${X(Rmax)} ${Y(zt)} L ${X(-Rmax)} ${Y(zt)} Z`;
    el("path", { d: dD, fill: "url(#coke-p)", opacity: 0.9 }, inner);
    const drops = el("g", {}, inner);
    for (let i = 0; i < 26; i++) {
      const x = -Rmax * 0.9 + 1.8 * Rmax * ((i * 37) % 26) / 26;
      const zstart = dripTop[Math.round((x + Rmax) / (2 * Rmax) * 48)][1];
      const fall = (zstart - zt + 0.2) * k;
      if (fall <= 4) continue;
      const c = el("circle", { cx: X(x), cy: Y(zstart), r: 2.2, fill: i % 3 ? "#ffd27a" : "#d9a441", class: "droplet" }, drops);
      c.style.setProperty("--d", `${fall + 3.0 * k}px`);
      c.style.animationDelay = `${(i * 0.29) % 1.6}s`;
      c.style.animationDuration = `${1.2 + (i % 5) * 0.15}s`;
    }
  } else {
    // thermal mode: labelled isotherms
    for (const T of [200, 400, 600, 800, 1000, 1200, 1400]) {
      if (T > Tmax) break;
      const c = isoCurve(T);
      if (!c) continue;
      el("path", { d: curveD(c), fill: "none", stroke: "rgba(255,255,255,0.55)", "stroke-width": 1, "stroke-dasharray": "3 3" }, inner);
      const mid = c[Math.floor(c.length / 2)];
      txt(inner, X(mid[0]), Y(mid[1]) - 3, `${T} °C`, "svg-sub", { "text-anchor": "middle", style: "fill:#fff;font-weight:600" });
    }
  }

  // hearth: deadman, slag, hot metal
  const rh = prof[0][1];
  const zHM = Math.min(0.32 * zt, 1.8), zSlag = Math.min(zHM + 0.2 * zt, zt - 0.8);
  el("rect", { x: X(-rh), y: Y(zt), width: 2 * rh * k, height: (zt - zSlag) * k, fill: "#2a2018" }, inner);
  el("path", { d: `M ${X(-rh * 0.75)} ${Y(zSlag)} Q ${X(0)} ${Y(zt + 3.2)} ${X(rh * 0.75)} ${Y(zSlag)} Z`, fill: "url(#coke-p)" }, inner);
  el("path", { d: `M ${X(-rh * 0.75)} ${Y(zSlag)} Q ${X(0)} ${Y(zt + 3.2)} ${X(rh * 0.75)} ${Y(zSlag)} Z`, fill: "rgba(40,30,20,0.35)" }, inner);
  el("rect", { x: X(-rh), y: Y(zSlag), width: 2 * rh * k, height: (zSlag - zHM) * k, fill: "url(#slag-g)", class: "liquid" }, inner);
  el("rect", { x: X(-rh), y: Y(zHM), width: 2 * rh * k, height: zHM * k + 1, fill: "url(#hm-g)", class: "liquid" }, inner);

  // raceways
  for (const sgn of [-1, 1]) {
    el("ellipse", { cx: X(sgn * (rh - 1.0)), cy: Y(zt), rx: 1.35 * k, ry: 0.75 * k, fill: "url(#raceway-g)", class: "raceway", filter: "url(#glow)" }, inner);
  }
  // rising gas
  const gas = el("g", { opacity: 0.55 }, inner);
  [-0.7, -0.35, 0, 0.35, 0.7].forEach((f, i) => {
    const x0 = f * (rh - 1.2), x1 = f * 0.45 * rt;
    const d = `M ${X(f * (rh - 1.4))} ${Y(zt + 0.3)} C ${X(x0 * 0.6)} ${Y(zt + 4)}, ${X(x1)} ${Y(zt + 8)}, ${X(x1)} ${Y(zs - 0.4)}`;
    el("path", { d, fill: "none", stroke: "#e9eef5", "stroke-width": 1.4, "stroke-dasharray": "6 14", class: "gas-line", style: `animation-delay:${-i * 0.4}s` }, gas);
  });

  // inner outline
  el("path", { d: innerD, fill: "none", stroke: "#9aa3b2", "stroke-width": 1.2, opacity: 0.6 }, svg);
  el("line", { x1: X(-rt), x2: X(rt), y1: Y(zs), y2: Y(zs), stroke: "#8fb3d9", "stroke-dasharray": "4 4", opacity: 0.7 }, svg);
  txt(svg, X(-rt) + 4, Y(zs) - 4, "stockline", "svg-small");

  // tuyeres, blowpipes, bustle pipe
  const eq = el("g", {}, svg);
  for (const sgn of [-1, 1]) {
    const xw = sgn * rh;
    el("rect", { x: Math.min(X(xw), X(xw + sgn * 1.3)), y: Y(zt + 0.16), width: 1.3 * k, height: 0.32 * k, fill: "#9aa3b2" }, eq);
    el("path", { d: `M ${X(xw + sgn * 1.3)} ${Y(zt)} L ${X(xw + sgn * 1.9)} ${Y(zt + 1.9)}`, stroke: "#b8c0cc", "stroke-width": 5, fill: "none", "stroke-linecap": "round" }, eq);
    el("circle", { cx: X(xw + sgn * 1.9), cy: Y(zt + 2.3), r: 0.55 * k, fill: "#3a414d", stroke: "#ff7a1a", "stroke-width": 2 }, eq);
  }
  txt(eq, X(-rh - 2.6), Y(zt + 2.6), "Hot blast →", "svg-label", { "text-anchor": "end" });
  txt(eq, X(-rh - 2.6), Y(zt + 2.0), `${opts.tBlast ? Math.round(opts.tBlast) + " °C · " : ""}bustle pipe`, "svg-sub", { "text-anchor": "end" });
  txt(eq, X(-rh - 2.6), Y(zt + 1.4), "& tuyeres", "svg-sub", { "text-anchor": "end" });

  // taphole + runner
  el("path", { d: `M ${X(-rh)} ${Y(0.45)} L ${X(-rh - 1.05)} ${Y(0.2)}`, stroke: "#ffb347", "stroke-width": 4 }, eq);
  el("path", { d: `M ${X(-rh - 1.05)} ${Y(0.2)} Q ${X(-rh - 1.7)} ${Y(0)} ${X(-rh - 1.8)} ${Y(-1.6)}`, stroke: "#ff9a1f", "stroke-width": 3.5, fill: "none",
    "stroke-dasharray": "6 5", class: "gas-line", filter: "url(#glow)" }, eq);
  el("rect", { x: X(-rh - 3.2), y: Y(-1.6), width: 2.6 * k, height: 0.35 * k, rx: 3, fill: "#5a3a2c" }, eq);
  txt(eq, X(-rh - 1.2), Y(-2.3), `Tapping · HM ${(flows.hm || 0).toFixed(0)} t/h · slag ${(flows.slag || 0).toFixed(0)} t/h`, "svg-small", { "text-anchor": "middle" });

  // ---------------------------------------------------------- height axis
  const ax = el("g", {}, svg);
  const xa = X(-Rmax - 1.9);
  el("line", { x1: xa, x2: xa, y1: Y(0), y2: Y(zTop), stroke: "#4a5260" }, ax);
  for (let z = 0; z <= zTop + 0.01; z += 5) {
    el("line", { x1: xa - 4, x2: xa, y1: Y(z), y2: Y(z), stroke: "#4a5260" }, ax);
    txt(ax, xa - 7, Y(z) + 4, `${z} m`, "svg-small", { "text-anchor": "end" });
  }

  // ---------------------------------------------------------- zone labels + hit areas
  const zinfo = ov.zone_info || [];
  const lab = el("g", {}, svg);
  const xb = X(Rmax + 1.45);
  const hits = el("g", {}, svg);
  const zoneList = ov.zones.map((z) => ({ ...z }));
  for (const z of zoneList) {
    const info = zinfo.find((i) => i.name === z.name);
    const y0 = Y(z.z0), y1 = Y(z.z1);
    el("path", { d: `M ${xb} ${y0 - 2} L ${xb + 6} ${y0 - 2} L ${xb + 6} ${y1 + 2} L ${xb} ${y1 + 2}`, fill: "none", stroke: "#5b6575" }, lab);
    const ym = (y0 + y1) / 2;
    txt(lab, xb + 14, ym - 2, z.name, "svg-label");
    if (info) {
      const g = info.items.find((i) => i[0] === "Gas temperature"), so = info.items.find((i) => i[0] === "Solid temperature");
      const sub = z.name === "Hearth" ? `${Math.round(ov.t_hm)} °C liquids` : (g && so ? `Tg ${g[1]} · Ts ${so[1]} °C` : "");
      txt(lab, xb + 14, ym + 13, sub, "svg-sub");
    }
    const r = el("rect", { x: X(-Rmax - 1.1), y: y1, width: W - X(-Rmax - 1.1) - 4, height: y0 - y1, class: "zone-hit" + (opts.selected === z.name ? " sel" : "") }, hits);
    r.addEventListener("click", () => opts.onSelect && opts.onSelect(z.name));
  }
  // raceway hit band
  const rwy = el("rect", { x: X(-Rmax - 1.1), y: Y(zt + 0.55), width: W - X(-Rmax - 1.1) - 4, height: 1.1 * k, class: "zone-hit" + (opts.selected === "Raceway" ? " sel" : "") }, hits);
  rwy.addEventListener("click", (e) => { e.stopPropagation(); opts.onSelect && opts.onSelect("Raceway"); });
  if (ov.t_raft) txt(lab, X(-rh + 0.2), Y(zt) + 4, `RAFT ${Math.round(ov.t_raft)} °C`, "svg-sub", { style: "fill:#fff;font-weight:600", filter: "" });
  if (mode === "process" && curveSoft) {
    const mid = curveSoft[Math.floor(curveSoft.length * 0.5)];
    txt(lab, X(mid[0]), Y(mid[1]) - 6, "cohesive zone", "svg-small", { "text-anchor": "middle", style: "fill:#cfffd9" });
  }

  // ---------------------------------------------------------- hover read-out
  const tip = el("g", { visibility: "hidden", "pointer-events": "none" }, svg);
  const tipBg = el("rect", { rx: 6, fill: "rgba(13,16,21,0.92)", stroke: "#3a4352" }, tip);
  const tipT = el("text", { class: "svg-sub", style: "fill:#e8ebf0" }, tip);
  svg.addEventListener("mousemove", (ev) => {
    const pt = svg.createSVGPoint();
    pt.x = ev.clientX; pt.y = ev.clientY;
    const p = pt.matrixTransform(svg.getScreenCTM().inverse());
    const z = (H - BOT - p.y) / k, x = (p.x - cx) / k;
    if (z < 0 || z > zs || Math.abs(x) > radius(z)) { tip.setAttribute("visibility", "hidden"); return; }
    const T = Tsolid(x, z);
    tipT.textContent = `z ${z.toFixed(1)} m · r ${Math.abs(x).toFixed(1)} m · ${z <= zt ? "liquid" : "solid"} ${Math.round(T)} °C`;
    const bb = tipT.getBBox();
    const tx = Math.min(p.x + 12, W - bb.width - 14), ty = p.y - 14;
    tipT.setAttribute("x", tx + 6); tipT.setAttribute("y", ty);
    tipBg.setAttribute("x", tx); tipBg.setAttribute("y", ty - bb.height + 2);
    tipBg.setAttribute("width", bb.width + 12); tipBg.setAttribute("height", bb.height + 6);
    tip.setAttribute("visibility", "visible");
  });
  svg.addEventListener("mouseleave", () => tip.setAttribute("visibility", "hidden"));
  return svg;
}
