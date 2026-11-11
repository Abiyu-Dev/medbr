import { CHART_COLORS } from "@/lib/status";

export interface BarDatum {
  label: string;
  value: number;
  color?: string;
  onClick?: () => void;
}

export function BarChart({
  data,
  formatValue = (v) => String(v),
}: {
  data: BarDatum[];
  formatValue?: (v: number) => string;
}) {
  const max = Math.max(1, ...data.map((d) => d.value));
  if (data.length === 0) {
    return <div className="muted" style={{ padding: "20px 0", fontSize: 13 }}>No data to chart.</div>;
  }
  return (
    <div className="bar-chart">
      {data.map((d, i) => (
        <div
          key={d.label + i}
          className="bar-row"
          onClick={d.onClick}
          style={{ cursor: d.onClick ? "pointer" : "default" }}
          title={`${d.label}: ${formatValue(d.value)}`}
        >
          <span className="bar-label">{d.label}</span>
          <div className="bar-track">
            <div
              className="bar-fill"
              style={{
                width: `${(d.value / max) * 100}%`,
                background: d.color ?? CHART_COLORS[i % CHART_COLORS.length],
              }}
            />
          </div>
          <span className="bar-value">{formatValue(d.value)}</span>
        </div>
      ))}
    </div>
  );
}

export interface DonutDatum {
  label: string;
  value: number;
  color: string;
}

export function DonutChart({
  data,
  size = 160,
  centerLabel,
  centerValue,
}: {
  data: DonutDatum[];
  size?: number;
  centerLabel?: string;
  centerValue?: string | number;
}) {
  const total = data.reduce((s, d) => s + d.value, 0);
  const radius = size / 2 - 14;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;
  return (
    <div className="donut-wrap">
      <div style={{ position: "relative", width: size, height: size }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke="var(--surface-3)"
            strokeWidth={16}
          />
          {total > 0 &&
            data.map((d, i) => {
              const fraction = d.value / total;
              const dash = fraction * circumference;
              const el = (
                <circle
                  key={i}
                  cx={size / 2}
                  cy={size / 2}
                  r={radius}
                  fill="none"
                  stroke={d.color}
                  strokeWidth={16}
                  strokeDasharray={`${dash} ${circumference - dash}`}
                  strokeDashoffset={-offset}
                  transform={`rotate(-90 ${size / 2} ${size / 2})`}
                  strokeLinecap="butt"
                >
                  <title>{`${d.label}: ${d.value}`}</title>
                </circle>
              );
              offset += dash;
              return el;
            })}
        </svg>
        {(centerValue !== undefined || centerLabel) && (
          <div
            style={{
              position: "absolute",
              inset: 0,
              display: "grid",
              placeItems: "center",
              textAlign: "center",
            }}
          >
            <div>
              <div style={{ fontFamily: "var(--font-display)", fontSize: 26, fontWeight: 800 }}>
                {centerValue ?? total}
              </div>
              {centerLabel && <div className="faint" style={{ fontSize: 11.5 }}>{centerLabel}</div>}
            </div>
          </div>
        )}
      </div>
      <div className="legend">
        {data.map((d) => (
          <div key={d.label} className="legend-item">
            <span className="legend-swatch" style={{ background: d.color }} />
            <span style={{ flex: 1 }}>{d.label}</span>
            <strong style={{ color: "var(--ink)", marginLeft: 12 }}>{d.value}</strong>
          </div>
        ))}
      </div>
    </div>
  );
}