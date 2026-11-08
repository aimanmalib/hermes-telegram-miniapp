/**
 * One-line spend chart: an SVG polyline with a soft area under it and a dot
 * on the latest value. No chart library; the geometry is sparklinePoints().
 */

export interface Point {
  x: number;
  y: number;
}

/** Drawing box of the SVG viewBox; the element itself stretches to its card. */
export const VIEW = { width: 100, height: 40, pad: 4 };

/**
 * Map values to points in VIEW. Zero sits on the baseline (spend never goes
 * below it), the largest value touches the top padding. One value is drawn
 * in the middle; no values give no points.
 */
export function sparklinePoints(values: number[], view = VIEW): Point[] {
  if (values.length === 0) return [];
  const max = Math.max(0, ...values);
  const usable = view.height - view.pad * 2;
  const y = (v: number) => view.height - view.pad - (max > 0 ? (Math.max(0, v) / max) * usable : 0);
  if (values.length === 1) return [{ x: view.width / 2, y: y(values[0]) }];
  const step = view.width / (values.length - 1);
  return values.map((v, i) => ({ x: i * step, y: y(v) }));
}

const fmt = (n: number) => Number(n.toFixed(2));

export function Sparkline({ values, label }: { values: number[]; label: string }) {
  const pts = sparklinePoints(values);
  const line = pts.map((p) => `${fmt(p.x)},${fmt(p.y)}`).join(" ");
  const base = VIEW.height - VIEW.pad;
  const area =
    pts.length > 1 ? `${fmt(pts[0].x)},${base} ${line} ${fmt(pts[pts.length - 1].x)},${base}` : "";
  const last = pts[pts.length - 1];
  return (
    <div className="sparkline" role="img" aria-label={label}>
      <svg viewBox={`0 0 ${VIEW.width} ${VIEW.height}`} preserveAspectRatio="none" aria-hidden="true">
        <line className="sparkline-base" x1={0} x2={VIEW.width} y1={base} y2={base} />
        {area && <polygon className="sparkline-area" points={area} />}
        {pts.length > 1 && <polyline className="sparkline-line" points={line} />}
      </svg>
      {last && (
        <span
          className="sparkline-dot"
          style={{ left: `${(last.x / VIEW.width) * 100}%`, top: `${(last.y / VIEW.height) * 100}%` }}
        />
      )}
    </div>
  );
}
