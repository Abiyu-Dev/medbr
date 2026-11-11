import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";
import { Button, Field, TextInput, Icon } from "@/components/ui";
import { errorMessage, isApiError } from "@/api/client";

interface FormState {
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  phone: string;
  password: string;
  password_confirm: string;
}

const INITIAL: FormState = {
  username: "",
  email: "",
  first_name: "",
  last_name: "",
  phone: "",
  password: "",
  password_confirm: "",
};

export function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState<FormState>(INITIAL);
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const [detail, setDetail] = useState("");
  const [loading, setLoading] = useState(false);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));
  const err = (k: string) => errors[k];

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setErrors({});
    setDetail("");

    const local: Record<string, string[]> = {};
    if (!form.username.trim()) local.username = ["Choose a username."];
    if (!form.email.trim()) local.email = ["Email is required."];
    if (!form.password) local.password = ["Choose a password."];
    else if (form.password.length < 8)
      local.password = ["Password must be at least 8 characters."];
    if (form.password !== form.password_confirm)
      local.password_confirm = ["Passwords do not match."];
    if (Object.keys(local).length) {
      setErrors(local);
      return;
    }

    setLoading(true);
    try {
      await register({
        username: form.username.trim(),
        email: form.email.trim(),
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        phone: form.phone.trim(),
        password: form.password,
        password_confirm: form.password_confirm,
      });
      navigate("/", { replace: true });
    } catch (error) {
      if (isApiError(error) && error.fieldErrors) setErrors(error.fieldErrors);
      else if (isApiError(error)) setDetail(error.detail);
      else setDetail(errorMessage(error));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="public-page">
      <div className="row" style={{ gap: 12 }}>
        <div className="brand-mark">
          <Icon name="heart" size={22} />
        </div>
        <div className="brand-text">
          <strong style={{ color: "var(--ink)" }}>MedBridge</strong>
          <span>Ethiopia</span>
        </div>
      </div>

      <div className="public-card" style={{ maxWidth: 520 }}>
        <div
          className="eyebrow"
          style={{
            color: "var(--brand)",
            fontWeight: 700,
            fontSize: 12,
            letterSpacing: ".08em",
            textTransform: "uppercase",
          }}
        >
          Facility onboarding
        </div>
        <h2 style={{ fontSize: 26, margin: "4px 0 8px" }}>Create your account</h2>
        <p className="muted" style={{ marginBottom: 22 }}>
          Register first. After signing in you'll submit your facility details for central
          review — once approved, this account becomes the facility manager login.
        </p>

        {detail && (
          <div className="alert alert-danger">
            <Icon name="alert" size={17} />
            <span>{detail}</span>
          </div>
        )}

        <form onSubmit={onSubmit} noValidate>
          <div className="field-row">
            <Field label="Username" required error={err("username")} htmlFor="reg-username">
              <TextInput
                id="reg-username"
                value={form.username}
                onChange={(e) => set("username", e.target.value)}
                placeholder="e.g. abebe_t"
                autoComplete="username"
                invalid={!!err("username")}
              />
            </Field>
            <Field label="Email" required error={err("email")} htmlFor="reg-email">
              <TextInput
                id="reg-email"
                type="email"
                value={form.email}
                onChange={(e) => set("email", e.target.value)}
                placeholder="you@example.org"
                autoComplete="email"
                invalid={!!err("email")}
              />
            </Field>
          </div>
          <div className="field-row">
            <Field label="First name" error={err("first_name")}>
              <TextInput
                value={form.first_name}
                onChange={(e) => set("first_name", e.target.value)}
                autoComplete="given-name"
              />
            </Field>
            <Field label="Last name" error={err("last_name")}>
              <TextInput
                value={form.last_name}
                onChange={(e) => set("last_name", e.target.value)}
                autoComplete="family-name"
              />
            </Field>
          </div>
          <Field label="Phone" error={err("phone")} help="Optional">
            <TextInput
              value={form.phone}
              onChange={(e) => set("phone", e.target.value)}
              placeholder="+251…"
              autoComplete="tel"
            />
          </Field>
          <div className="field-row">
            <Field label="Password" required error={err("password")} htmlFor="reg-password" help="At least 8 characters">
              <TextInput
                id="reg-password"
                type="password"
                value={form.password}
                onChange={(e) => set("password", e.target.value)}
                placeholder="••••••••"
                autoComplete="new-password"
                invalid={!!err("password")}
              />
            </Field>
            <Field label="Confirm password" required error={err("password_confirm")} htmlFor="reg-password-confirm">
              <TextInput
                id="reg-password-confirm"
                type="password"
                value={form.password_confirm}
                onChange={(e) => set("password_confirm", e.target.value)}
                placeholder="••••••••"
                autoComplete="new-password"
                invalid={!!err("password_confirm")}
              />
            </Field>
          </div>

          <Button type="submit" block size="lg" loading={loading} icon="arrow-right">
            Create account
          </Button>
        </form>

        <p className="muted" style={{ textAlign: "center", marginTop: 20 }}>
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
