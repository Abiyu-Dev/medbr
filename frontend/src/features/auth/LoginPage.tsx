import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";
import { Button, Field, TextInput, Icon } from "@/components/ui";
import { errorMessage, isApiError } from "@/api/client";

const DEMO_PASSWORD = "Demo_Pass_123!";
const DEMO_ACCOUNTS = [
  { username: "demo_admin", role: "System Admin", icon: "shield" as const },
  { username: "demo_coord", role: "Central Coordinator", icon: "globe" as const },
  { username: "mgr_bole", role: "Facility Manager · Bole", icon: "building" as const },
  { username: "pharm_bole", role: "Pharmacist · Bole", icon: "pill" as const },
  { username: "hw_bole", role: "Health Worker · Bole", icon: "syringe" as const },
];

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function doLogin(u: string, p: string) {
    setError("");
    setLoading(true);
    try {
      await login(u, p);
      navigate("/", { replace: true });
    } catch (err) {
      setError(
        isApiError(err) && err.status === 401
          ? "Incorrect username or password."
          : errorMessage(err),
      );
    } finally {
      setLoading(false);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!username || !password) {
      setError("Enter your username and password.");
      return;
    }
    doLogin(username, password);
  }

  return (
    <div className="auth-page">
      <div className="auth-hero">
        <div className="row" style={{ gap: 12, position: "relative", zIndex: 1 }}>
          <div className="brand-mark">
            <Icon name="heart" size={22} />
          </div>
          <div className="brand-text">
            <strong>MedBridge</strong>
            <span>Ethiopia</span>
          </div>
        </div>

        <div className="hero-content">
          <h1>Keep every facility stocked. Keep every dose counted.</h1>
          <p>
            A shared coordination layer for Ethiopia's clinics, hospitals, health centers and
            pharmacies — match safe surplus to real need, track vaccination follow-ups, and
            escalate the shortages that redistribution can't solve.
          </p>

          <div className="hero-feature">
            <span className="hf-icon"><Icon name="snowflake" size={18} /></span>
            <div>
              <strong>Cold-chain &amp; expiry aware</strong>
              <span>Batch-level ledger with usable-stock, near-expiry and storage rules.</span>
            </div>
          </div>
          <div className="hero-feature">
            <span className="hf-icon"><Icon name="transfer" size={18} /></span>
            <div>
              <strong>Human-approved transfers</strong>
              <span>Request, review, dispatch and verify receipt — phone-coordinated delivery.</span>
            </div>
          </div>
          <div className="hero-feature">
            <span className="hf-icon"><Icon name="sparkles" size={18} /></span>
            <div>
              <strong>Advisory AI, never autonomous</strong>
              <span>Gemini explains and ranks; people approve every stock decision.</span>
            </div>
          </div>
        </div>

        <div className="hero-stats">
          <div className="hero-stat">
            <strong>7</strong>
            <span>Role-based workspaces</span>
          </div>
          <div className="hero-stat">
            <strong>1</strong>
            <span>Source of truth</span>
          </div>
          <div className="hero-stat">
            <strong>0</strong>
            <span>Autonomous stock moves</span>
          </div>
        </div>
      </div>

      <div className="auth-form-side">
        <div className="auth-card rise-in">
          <h2>Welcome back</h2>
          <p className="auth-sub">Sign in to your MedBridge workspace.</p>

          {error && (
            <div className="alert alert-danger">
              <Icon name="alert" size={17} />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={onSubmit}>
            <Field label="Username" required htmlFor="username">
              <TextInput
                id="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="e.g. pharm_bole"
                autoComplete="username"
                autoFocus
              />
            </Field>
            <Field label="Password" required htmlFor="password">
              <TextInput
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••"
                autoComplete="current-password"
              />
            </Field>
            <Button type="submit" block size="lg" loading={loading} icon="arrow-right">
              Sign in
            </Button>
          </form>

          <p className="muted" style={{ textAlign: "center", marginTop: 16 }}>
            New facility? <Link to="/register">Create an account</Link>
          </p>

          <div className="demo-accounts">
            <div className="da-title">Demo accounts · password {DEMO_PASSWORD}</div>
            {DEMO_ACCOUNTS.map((a) => (
              <button
                key={a.username}
                className="demo-account-btn"
                disabled={loading}
                onClick={() => doLogin(a.username, DEMO_PASSWORD)}
              >
                <Icon name={a.icon} size={16} style={{ color: "var(--brand)" }} />
                <span className="da-role">{a.role}</span>
                <span className="da-user">{a.username}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}