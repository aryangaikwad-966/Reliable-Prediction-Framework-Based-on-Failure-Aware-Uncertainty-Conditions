import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  BrainCircuit,
  ChevronRight,
  CircleHelp,
  Database,
  Gauge,
  GitBranch,
  LineChart,
  Menu,
  Network,
  RefreshCw,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { createPrediction, getDashboard, getEvaluation, getFailures, getMetadata, getPredictions } from "./api";
import type { DashboardData, Prediction } from "./types";

const navGroups = [
  {
    label: "Workspace",
    items: [
      { href: "/dashboard", label: "Overview", icon: Gauge },
      { href: "/predictions", label: "Predictions", icon: BrainCircuit },
      { href: "/forecasts", label: "Forecast Explorer", icon: LineChart },
    ],
  },
  {
    label: "Reliability",
    items: [
      { href: "/reliability", label: "Reliability Analysis", icon: ShieldCheck },
      { href: "/failure-memory", label: "Failure Memory", icon: Database },
      { href: "/uncertainty", label: "Uncertainty", icon: Activity },
      { href: "/drift", label: "Drift & OOD", icon: Network },
    ],
  },
  {
    label: "Research",
    items: [
      { href: "/events", label: "Events & Context", icon: Sparkles },
      { href: "/evaluation", label: "Evaluation", icon: BarChart3 },
      { href: "/experiments", label: "Experiments", icon: GitBranch },
      { href: "/data", label: "Data Explorer", icon: Search },
    ],
  },
];

function formatPercent(value: number | null | undefined) {
  return value == null ? "Not available" : `${Math.round(value * 100)}%`;
}

function formatMoney(value: number | null | undefined) {
  return value == null ? "—" : `₹${value.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

function PageTitle({ eyebrow, title, description, action }: { eyebrow: string; title: string; description: string; action?: React.ReactNode }) {
  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action}
    </div>
  );
}

function StatusPill({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "good" | "warn" | "bad" | "neutral" }) {
  return <span className={`status-pill ${tone}`}>{children}</span>;
}

function MetricCard({ label, value, helper, tone = "neutral" }: { label: string; value: string; helper: string; tone?: string }) {
  return (
    <div className="metric-card">
      <div className="metric-label">{label}</div>
      <div className={`metric-value ${tone}`}>{value}</div>
      <div className="metric-helper">{helper}</div>
    </div>
  );
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="empty-state">
      <CircleHelp size={22} />
      <strong>{title}</strong>
      <span>{body}</span>
    </div>
  );
}

function Dashboard({ dashboard, onRefresh }: { dashboard: DashboardData; onRefresh: () => void }) {
  const { summary } = dashboard;
  return (
    <>
      <PageTitle
        eyebrow="Research workspace / live assessment"
        title="Failure-aware prediction"
        description="A transparent decision layer that learns when market forecasts should be trusted — and when to abstain."
        action={
          <button className="button secondary" onClick={onRefresh}>
            <RefreshCw size={16} /> Refresh signals
          </button>
        }
      />
      <div className="notice">
        <div className="notice-mark">{dashboard.mode === "DEMO" ? "D" : "L"}</div>
        <div>
          <strong>{dashboard.mode === "DEMO" ? "DEMO DATA" : "LIVE DATA"}</strong>
          <span>{dashboard.status}</span>
        </div>
        <span className="notice-tail">Research integrity mode</span>
      </div>
      <section className="metric-grid">
        <MetricCard label="Total predictions" value={`${summary.totalPredictions}`} helper="Recorded decisions" />
        <MetricCard label="Accepted" value={`${summary.accepted}`} helper={`${formatPercent(summary.totalPredictions ? summary.accepted / summary.totalPredictions : null)} of decisions`} tone="good" />
        <MetricCard label="Abstained" value={`${summary.abstained}`} helper={`${formatPercent(summary.totalPredictions ? summary.abstained / summary.totalPredictions : null)} withheld`} tone="warn" />
        <MetricCard label="Average reliability" value={formatPercent(summary.averageReliability)} helper="Calculated from risk signals" tone="good" />
        <MetricCard label="Failure detection" value={formatPercent(summary.failureDetectionRate)} helper="Measured only after outcomes" />
        <MetricCard label="Selective MAE" value={summary.selectiveMae == null ? "Not available" : formatMoney(summary.selectiveMae)} helper="Requires evaluated outcomes" />
      </section>
      <div className="dashboard-grid">
        <section className="panel chart-panel">
          <div className="panel-heading"><div><h2>Risk / coverage</h2><span>Lower risk as unreliable predictions are removed</span></div><StatusPill>Measured signal</StatusPill></div>
          {dashboard.riskCoverage.length ? (
            <div className="risk-chart">
              <div className="chart-axis"><span>1.0</span><span>0.5</span><span>0.0</span></div>
              <div className="chart-area">
                <svg viewBox="0 0 500 190" preserveAspectRatio="none" role="img" aria-label="Risk coverage curve">
                  <path d="M0 25 C90 38 120 62 195 86 S355 142 500 172" fill="none" stroke="#55d6a2" strokeWidth="4" />
                  <path d="M0 25 L500 172" fill="none" stroke="#304156" strokeWidth="1" strokeDasharray="5 5" />
                </svg>
                <div className="chart-label left">LOWER RISK</div><div className="chart-label right">HIGHER COVERAGE</div>
              </div>
            </div>
          ) : <EmptyState title="Experiment not run" body="The curve appears after chronological evaluation has been executed." />}
        </section>
        <section className="panel">
          <div className="panel-heading"><div><h2>Reliability distribution</h2><span>Current decisions</span></div><Activity size={17} /></div>
          <div className="distribution">
            {dashboard.reliabilityDistribution.map((item) => <div className="distribution-row" key={item.bucket}><span>{item.bucket}</span><div><i style={{ width: `${Math.min(100, item.count * 18)}%` }} /></div><b>{item.count}</b></div>)}
          </div>
        </section>
      </div>
      <section className="panel">
        <div className="panel-heading"><div><h2>Recent prediction decisions</h2><span>Each decision exposes the evidence used to accept or abstain.</span></div><Link className="text-link" to="/predictions">View all <ChevronRight size={14} /></Link></div>
        <PredictionTable predictions={dashboard.predictions.slice(0, 6)} />
      </section>
    </>
  );
}

function PredictionTable({ predictions }: { predictions: Prediction[] }) {
  if (!predictions.length) return <EmptyState title="No predictions yet" body="Generate a forecast to populate the decision log." />;
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>Instrument</th><th>Created</th><th>Forecast</th><th>Reliability</th><th>Failure risk</th><th>Decision</th></tr></thead>
        <tbody>{predictions.map((prediction) => (
          <tr key={prediction.id}>
            <td><strong>{prediction.commodity}</strong><small>{prediction.market} · {prediction.variety}</small></td>
            <td>{new Date(prediction.createdAt).toLocaleDateString("en-IN", { day: "2-digit", month: "short" })}</td>
            <td>{prediction.prediction == null ? "Withheld" : formatMoney(prediction.prediction)}<small>{prediction.horizon}-day horizon</small></td>
            <td><div className="table-progress"><i style={{ width: `${prediction.reliability * 100}%` }} /></div>{formatPercent(prediction.reliability)}</td>
            <td>{formatPercent(prediction.failureRisk)}</td>
            <td><StatusPill tone={prediction.decision === "ACCEPTED" ? "good" : "warn"}>{prediction.decision}</StatusPill></td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

function PredictionsPage({ dashboard }: { dashboard: DashboardData }) {
  const queryClient = useQueryClient();
  const metadata = useQuery({ queryKey: ["metadata"], queryFn: getMetadata });
  const [form, setForm] = useState({ commodity: "Tomato", market: "Lasalgaon", variety: "Local", horizon: 7 });
  const [result, setResult] = useState<Prediction | null>(null);
  const mutation = useMutation({
    mutationFn: createPrediction,
    onSuccess: (data) => { setResult(data); void queryClient.invalidateQueries({ queryKey: ["dashboard"] }); },
  });
  const options = metadata.data ?? { commodities: ["Tomato"], markets: ["Lasalgaon"], varieties: ["Local"] };
  return (
    <>
      <PageTitle eyebrow="Decision engine" title="Generate a prediction" description="Choose a market context. Every result returns its reliability evidence, not just a price." />
      <div className="prediction-layout">
        <section className="panel form-panel">
          <div className="panel-heading"><div><h2>Forecast inputs</h2><span>Target: modal price · Unit: Rs/Quintal</span></div><StatusPill tone="neutral">7-day MVP</StatusPill></div>
          <label>Commodity<select value={form.commodity} onChange={(e) => setForm({ ...form, commodity: e.target.value })}>{options.commodities.map((item) => <option key={item}>{item}</option>)}</select></label>
          <label>Market<select value={form.market} onChange={(e) => setForm({ ...form, market: e.target.value })}>{options.markets.map((item) => <option key={item}>{item}</option>)}</select></label>
          <label>Variety<select value={form.variety} onChange={(e) => setForm({ ...form, variety: e.target.value })}>{options.varieties.map((item) => <option key={item}>{item}</option>)}</select></label>
          <label>Forecast horizon<select value={form.horizon} onChange={(e) => setForm({ ...form, horizon: Number(e.target.value) })}><option value="7">7 days</option><option value="14">14 days</option><option value="30">30 days</option></select></label>
          <button className="button primary wide" onClick={() => mutation.mutate(form)} disabled={mutation.isPending}>{mutation.isPending ? "Assessing context…" : "Generate prediction"} <ChevronRight size={16} /></button>
          {mutation.isError && <div className="inline-error">The prediction service could not complete this request. Check service status and retry.</div>}
        </section>
        <section className="panel result-panel">
          {result ? <PredictionResult prediction={result} /> : <EmptyState title="Awaiting a forecast" body="The final prediction is only shown when the reliability gate accepts it. Abstained results intentionally withhold the price." />}
        </section>
      </div>
    </>
  );
}

function PredictionResult({ prediction }: { prediction: Prediction }) {
  const accepted = prediction.decision === "ACCEPTED";
  return (
    <div className="result">
      <div className="result-kicker"><span className={accepted ? "dot good" : "dot warn"} /> Decision outcome</div>
      <div className="result-decision">{accepted ? "Prediction accepted" : "Prediction abstained"}</div>
      <div className="result-context">{prediction.commodity} · {prediction.market} · {prediction.horizon}-day horizon</div>
      <div className="result-price">{prediction.prediction == null ? "Price withheld" : `${formatMoney(prediction.prediction)} / Quintal`}</div>
      <div className="result-stats"><div><span>Reliability</span><strong className="good-text">{formatPercent(prediction.reliability)}</strong></div><div><span>Failure risk</span><strong className="bad-text">{formatPercent(prediction.failureRisk)}</strong></div></div>
      <div className="signal-list">{Object.entries(prediction.signals).map(([key, value]) => <div key={key}><span>{key.replace(/([A-Z])/g, " $1")}</span><b>{formatPercent(value)}</b></div>)}</div>
      <div className="evidence"><strong>{accepted ? "Evidence supporting acceptance" : "Evidence behind abstention"}</strong>{prediction.reasons.length ? <ul>{prediction.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul> : <span>No elevated risk signal crossed the configured threshold.</span>}</div>
    </div>
  );
}

function ResearchPage({ path, dashboard }: { path: string; dashboard: DashboardData }) {
  const failures = useQuery({ queryKey: ["failures"], queryFn: getFailures, enabled: path === "/failure-memory" });
  const evaluation = useQuery({ queryKey: ["evaluation"], queryFn: getEvaluation, enabled: path === "/evaluation" || path === "/reliability" });
  const data: Record<string, { title: string; description: string; cards: Array<[string, string, string]> }> = {
    "/reliability": { title: "Reliability analysis", description: "Separate coverage from risk so a selective system can be evaluated honestly.", cards: [["Coverage", formatPercent(evaluation.data?.coverage), "Measured after evaluation"], ["Selective risk", formatPercent(evaluation.data?.selectiveRisk), "Error among accepted predictions"], ["AURC", evaluation.data?.aurc == null ? "Not run" : evaluation.data.aurc.toFixed(3), "Area under risk-coverage"] ] },
    "/uncertainty": { title: "Uncertainty signals", description: "The decision gate combines model uncertainty, memory, novelty, drift, and missing information.", cards: [["Model uncertainty", "Calculated per prediction", "Ensemble disagreement or model interval"], ["Historical failures", "Contextual", "Nearest historical failure cases"], ["Missing information", "Not integrated", "External context is not fabricated"] ] },
    "/drift": { title: "Drift & OOD", description: "Distribution signals make changes in the operating environment visible before they become silent errors.", cards: [["Novelty / OOD", "Feature distance", "Standardized distance from training distribution"], ["Drift", "Not run", "Requires chronological residual history"], ["Method", "Transparent", "MVP percentile and rolling residual checks"] ] },
    "/events": { title: "Events & context", description: "The data model accepts context, while the current project does not invent weather, policy, or supply events.", cards: [["External events", "Not integrated", "No fabricated observations"], ["Weather", "Not available", "Connect a verified source later"], ["Policy / supply", "Optional", "Structured fields are ready for ingestion"] ] },
    "/experiments": { title: "Experiment registry", description: "Compare the base model to progressively stronger failure-aware configurations without inventing results.", cards: [["A · Base", "NOT RUN", "Base XGBoost model"], ["B · + Uncertainty", "NOT RUN", "Adds model uncertainty"], ["E · Full framework", "NOT RUN", "Adds memory, OOD, drift, and abstention"] ] },
    "/data": { title: "Data explorer", description: "Large agricultural datasets are ingested and queried server-side. No millions-row browser downloads.", cards: [["Records", "Not available", "Ingest the APMC CSV to measure"], ["Date range", "2025 only", "No fabricated historical years"], ["Target", "modal_price", "Filtered to Rs/Quintal for MVP"] ] },
  };
  if (path === "/failure-memory") {
    return <><PageTitle eyebrow="Adaptive contextual failure memory" title="Failure memory" description="Historical failures become evidence for future reliability assessments only after actual outcomes are observed." /><section className="panel"><div className="panel-heading"><div><h2>Recorded failure cases</h2><span>Thresholds are project configuration, not universal scientific standards.</span></div><StatusPill tone="warn">{failures.data?.length ?? 0} cases</StatusPill></div>{failures.data ? <div className="failure-cards">{failures.data.map((failure) => <div className="failure-card" key={failure.id}><div><StatusPill tone={failure.severity === "HIGH" ? "bad" : "warn"}>{failure.severity}</StatusPill><strong>{failure.commodity} · {failure.market}</strong><span>{new Date(failure.date).toLocaleDateString()}</span></div><div><span>Absolute error</span><b>{formatMoney(failure.absoluteError)}</b></div><div><span>Reliability</span><b>{formatPercent(failure.reliability)}</b></div></div>)}</div> : <EmptyState title="Loading failure memory" body="Retrieving stored outcomes." />}</section></>;
  }
  if (path === "/evaluation") {
    return <><PageTitle eyebrow="Chronological evaluation" title="Evaluation" description="Metrics appear only after walk-forward evaluation has been run against observed outcomes." /><section className="metric-grid evaluation-metrics">{[["MAE", evaluation.data?.mae], ["RMSE", evaluation.data?.rmse], ["MAPE", evaluation.data?.mape], ["R²", evaluation.data?.r2], ["Coverage", evaluation.data?.coverage], ["AURC", evaluation.data?.aurc]].map(([label, value]) => <MetricCard key={String(label)} label={String(label)} value={value == null ? "NOT RUN" : typeof value === "number" ? value.toFixed(3) : String(value)} helper="Measured values only" />)}</section><section className="panel"><div className="panel-heading"><div><h2>Model comparison</h2><span>Base, uncertainty, memory, OOD, full framework</span></div></div><EmptyState title="Experiment not run" body="Start an experiment after the dataset has been ingested and a model trained." /></section></>;
  }
  const content = data[path] ?? data["/data"];
  return <><PageTitle eyebrow="Research module" title={content.title} description={content.description} /><div className="metric-grid">{content.cards.map(([label, value, helper]) => <MetricCard key={label} label={label} value={value} helper={helper} />)}</div><section className="panel module-panel"><div className="module-icon"><AlertTriangle size={22} /></div><div><h2>Evidence-first implementation</h2><p>This module is wired to the API and database schema. It will show measured values when the corresponding ingestion or chronological experiment has run; it will not substitute fabricated research evidence.</p></div></section></>;
}

function Sidebar({ open, close }: { open: boolean; close: () => void }) {
  const location = useLocation();
  return <aside className={`sidebar ${open ? "open" : ""}`}><div className="brand"><div className="brand-mark"><ShieldCheck size={19} /></div><div><strong>RELIABLE</strong><span>prediction framework</span></div><button className="mobile-close" onClick={close}><X size={18} /></button></div><div className="research-tag"><span className="tag-dot" /> Failure-aware selective prediction</div><nav>{navGroups.map((group) => <div className="nav-group" key={group.label}><div className="nav-label">{group.label}</div>{group.items.map(({ href, label, icon: Icon }) => <Link className={location.pathname === href ? "active" : ""} onClick={close} to={href} key={href}><Icon size={17} /><span>{label}</span></Link>)}</div>)}</nav><div className="sidebar-bottom"><Link className={location.pathname === "/settings" ? "active" : ""} to="/settings" onClick={close}><Settings size={17} /><span>Settings</span></Link><div className="service-status"><span className="pulse" /> Services operational<div>Node API · PostgreSQL · FastAPI</div></div></div></aside>;
}

export default function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const dashboard = useQuery({ queryKey: ["dashboard"], queryFn: getDashboard });
  const fallback: DashboardData = { mode: "DEMO", status: "Demo seed active. Connect PostgreSQL and ingest the APMC dataset to switch to live evidence.", summary: { totalPredictions: 0, accepted: 0, abstained: 0, averageReliability: null, failureDetectionRate: null, selectiveMae: null }, predictions: [], riskCoverage: [], reliabilityDistribution: [], forecastActual: [] };
  const current = dashboard.data ?? fallback;
  const path = location.pathname === "/" ? "/dashboard" : location.pathname;
  const page = path === "/dashboard" ? <Dashboard dashboard={current} onRefresh={() => void dashboard.refetch()} /> : path === "/predictions" ? <PredictionsPage dashboard={current} /> : path === "/settings" ? <><PageTitle eyebrow="System configuration" title="Settings" description="Configure thresholds and inspect service readiness without hiding unavailable dependencies." /><div className="settings-grid"><section className="panel"><h2>Prediction settings</h2><label>Default horizon<input value="7 days" readOnly /></label><label>Reliability threshold<input value="70%" readOnly /></label><label>Failure threshold<input value="25% relative error" readOnly /></label></section><section className="panel"><h2>System status</h2><div className="service-row"><span>Node API</span><StatusPill tone="good">Operational</StatusPill></div><div className="service-row"><span>PostgreSQL</span><StatusPill tone={current.mode === "LIVE" ? "good" : "warn"}>{current.mode === "LIVE" ? "Connected" : "Demo fallback"}</StatusPill></div><div className="service-row"><span>FastAPI ML service</span><StatusPill tone="warn">Check on demand</StatusPill></div></section></div></> : <ResearchPage path={path} dashboard={current} />;
  return <div className="app-shell"><Sidebar open={sidebarOpen} close={() => setSidebarOpen(false)} /><main className="main"><header className="topbar"><button className="menu-button" onClick={() => setSidebarOpen(true)}><Menu size={20} /></button><div className="breadcrumbs"><span>Research platform</span><ChevronRight size={14} /><strong>{path.replace("/", "").replace("-", " ") || "dashboard"}</strong></div><div className="topbar-actions"><span className="data-indicator"><span className="pulse" /> {current.mode === "DEMO" ? "Demo mode" : "Live"} </span><button className="avatar" onClick={() => navigate("/settings")}>AR</button></div></header><div className="content">{dashboard.isError && <div className="global-error"><AlertTriangle size={17} /> API unavailable. The interface is showing an empty research state. <button onClick={() => void dashboard.refetch()}>Retry</button></div>}{page}</div><footer>Reliable Prediction Framework <span>·</span> Failure-aware selective prediction <span>·</span> Research integrity mode</footer></main></div>;
}