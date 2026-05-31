import React, { useState, useEffect } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";

const API = "http://localhost:8000";
const STORE = "ST1008";
const POLL = 5000;
const SEV_COLOR = { CRITICAL: "#ef4444", WARN: "#f59e0b", INFO: "#3b82f6" };

export default function App() {
  const [metrics, setMetrics]     = useState(null);
  const [funnel, setFunnel]       = useState(null);
  const [heatmap, setHeatmap]     = useState(null);
  const [anomalies, setAnomalies] = useState([]);
  const [health, setHealth]       = useState(null);
  const [updated, setUpdated]     = useState(null);
  const [error, setError]         = useState(null);

  const fetchAll = async () => {
    try {
      const [m, f, h, a, he] = await Promise.all([
        fetch(`${API}/stores/${STORE}/metrics`).then(r => r.json()),
        fetch(`${API}/stores/${STORE}/funnel`).then(r => r.json()),
        fetch(`${API}/stores/${STORE}/heatmap`).then(r => r.json()),
        fetch(`${API}/stores/${STORE}/anomalies`).then(r => r.json()),
        fetch(`${API}/health`).then(r => r.json()),
      ]);
      setMetrics(m); setFunnel(f); setHeatmap(h);
      setAnomalies(Array.isArray(a) ? a : []);
      setHealth(he);
      setUpdated(new Date().toLocaleTimeString());
      setError(null);
    } catch {
      setError("⚠️ Cannot connect to API. Run: uvicorn main:app --reload in app folder");
    }
  };

  useEffect(() => {
    fetchAll();
    const t = setInterval(fetchAll, POLL);
    return () => clearInterval(t);
  }, []);

  return (
    <div style={S.root}>
      <div style={S.header}>
        <div>
          <h1 style={S.title}>🏪 Brigade Bangalore — Store Intelligence</h1>
          <p style={S.sub}>Store ID: {STORE} · Purplle Tech Challenge 2026 · Live refresh every 5s</p>
        </div>
        <div style={S.badge}>
          <span style={{ ...S.dot, background: health?.status === "healthy" ? "#22c55e" : "#ef4444" }} />
          {health?.status || "connecting"}
          {updated && <span style={{ color: "#64748b" }}> · {updated}</span>}
        </div>
      </div>

      {error && <div style={S.err}>{error}</div>}

      <div style={S.g4}>
        <KPI label="Unique Visitors" value={metrics?.unique_visitors ?? "—"} icon="👥" color="#6366f1" />
        <KPI label="Conversion Rate" value={metrics ? `${metrics.conversion_rate}%` : "—"} icon="💳" color="#22c55e" />
        <KPI label="Queue Depth" value={metrics?.queue_depth ?? "—"} icon="🧾"
             color={(metrics?.queue_depth ?? 0) >= 5 ? "#ef4444" : "#f59e0b"} />
        <KPI label="Abandonment Rate" value={metrics ? `${metrics.abandonment_rate}%` : "—"} icon="🚶" color="#f59e0b" />
      </div>

      <div style={S.g2}>
        <div style={S.card}>
          <h2 style={S.ct}>🔥 Zone Heatmap</h2>
          {heatmap?.zones?.length > 0
            ? <ResponsiveContainer width="100%" height={220}>
                <BarChart data={heatmap.zones} margin={{ bottom: 40 }}>
                  <XAxis dataKey="zone_id" angle={-30} textAnchor="end" tick={{ fontSize: 11, fill: "#94a3b8" }} />
                  <YAxis tick={{ fill: "#94a3b8" }} />
                  <Tooltip contentStyle={{ background: "#1e293b", border: "none" }} />
                  <Bar dataKey="normalized_score" radius={[4,4,0,0]}>
                    {heatmap.zones.map((z, i) => (
                      <Cell key={i} fill={z.normalized_score > 70 ? "#ef4444" : z.normalized_score > 40 ? "#f59e0b" : "#6366f1"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            : <Empty />}
        </div>

        <div style={S.card}>
          <h2 style={S.ct}>📊 Conversion Funnel</h2>
          {funnel?.stages?.length > 0
            ? funnel.stages.map((s, i) => (
                <div key={i} style={S.frow}>
                  <div style={S.flabel}>{s.stage}</div>
                  <div style={{ ...S.fbar, width: `${Math.max(8, 100 - s.drop_off_pct)}%`,
                    background: ["#6366f1","#8b5cf6","#a78bfa","#22c55e"][i] }}>
                    {s.count}
                  </div>
                  {s.drop_off_pct > 0 && <div style={S.drop}>↓{s.drop_off_pct}%</div>}
                </div>))
            : <Empty />}
        </div>
      </div>

      <div style={S.card}>
        <h2 style={S.ct}>🚨 Active Anomalies</h2>
        {anomalies.length === 0
          ? <p style={{ color: "#22c55e", margin: 0 }}>✅ No active anomalies</p>
          : anomalies.map((a, i) => (
              <div key={i} style={{ ...S.acard, borderLeft: `4px solid ${SEV_COLOR[a.severity]}` }}>
                <div style={{ display: "flex", gap: 12, marginBottom: 4 }}>
                  <span style={{ fontWeight: 700, color: SEV_COLOR[a.severity] }}>{a.severity}</span>
                  <span style={{ color: "#94a3b8", fontSize: 13 }}>{a.anomaly_type}</span>
                </div>
                <p style={{ margin: "2px 0", fontSize: 14 }}>{a.description}</p>
                <p style={{ margin: 0, fontSize: 13, color: "#22c55e" }}>💡 {a.suggested_action}</p>
              </div>))}
      </div>

      {metrics?.avg_dwell_per_zone?.length > 0 && (
        <div style={S.card}>
          <h2 style={S.ct}>⏱️ Avg Dwell Per Zone</h2>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead><tr>
              {["Zone","Avg Dwell","Visits"].map(h => <th key={h} style={S.th}>{h}</th>)}
            </tr></thead>
            <tbody>{metrics.avg_dwell_per_zone.map((z, i) => (
              <tr key={i} style={{ background: i % 2 === 0 ? "#1e293b" : "#0f172a" }}>
                <td style={S.td}>{z.zone_id}</td>
                <td style={S.td}>{(z.avg_dwell_ms / 1000).toFixed(1)}s</td>
                <td style={S.td}>{z.visit_count}</td>
              </tr>))}
            </tbody>
          </table>
        </div>)}
    </div>
  );
}

const KPI = ({ label, value, icon, color }) => (
  <div style={{ ...S.card, borderTop: `3px solid ${color}`, marginBottom: 0 }}>
    <div style={{ fontSize: 28, marginBottom: 8 }}>{icon}</div>
    <div style={{ fontSize: 36, fontWeight: 800, color, lineHeight: 1 }}>{value}</div>
    <div style={{ color: "#64748b", fontSize: 13, marginTop: 6 }}>{label}</div>
  </div>
);

const Empty = () => <p style={{ color: "#64748b", margin: "20px 0" }}>No data yet — ingest events first</p>;

const S = {
  root:   { background: "#0f172a", minHeight: "100vh", padding: 24, fontFamily: "Inter, sans-serif", color: "#e2e8f0" },
  header: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 },
  title:  { margin: 0, fontSize: 24, fontWeight: 800, color: "#f1f5f9" },
  sub:    { margin: "4px 0 0", color: "#64748b", fontSize: 13 },
  badge:  { display: "flex", alignItems: "center", gap: 8, background: "#1e293b", padding: "8px 16px", borderRadius: 999, fontSize: 13 },
  dot:    { width: 8, height: 8, borderRadius: "50%", display: "inline-block" },
  err:    { background: "#7f1d1d", color: "#fca5a5", padding: "12px 16px", borderRadius: 8, marginBottom: 16 },
  g4:     { display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 16, marginBottom: 16 },
  g2:     { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 },
  card:   { background: "#1e293b", borderRadius: 12, padding: 20, marginBottom: 16 },
  ct:     { margin: "0 0 16px", fontSize: 16, fontWeight: 700, color: "#f1f5f9" },
  frow:   { display: "flex", alignItems: "center", gap: 12, marginBottom: 10 },
  flabel: { width: 110, fontSize: 13, color: "#94a3b8", flexShrink: 0 },
  fbar:   { height: 32, borderRadius: 6, display: "flex", alignItems: "center", paddingLeft: 10, fontSize: 13, fontWeight: 700, color: "white", transition: "width 0.5s" },
  drop:   { fontSize: 12, color: "#ef4444", flexShrink: 0 },
  acard:  { background: "#0f172a", borderRadius: 8, padding: 12, marginBottom: 10 },
  th:     { textAlign: "left", padding: "8px 12px", color: "#64748b", fontSize: 13, borderBottom: "1px solid #334155" },
  td:     { padding: "10px 12px", fontSize: 14 },
};
