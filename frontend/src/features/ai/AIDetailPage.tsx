import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AIApi } from "@/api/endpoints";
import { isApiError } from "@/api/client";
import type { AIRecommendation } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { canRequestTransfer, canReviewAI, isCentral } from "@/lib/permissions";
import { Badge, Button, Card, CardBody, CardHeader, ErrorState, Field, Icon, LoadingState, Modal, PageHeader, TextArea, useToast } from "@/components/ui";
import { formatDateTime, formatNumber, humanize } from "@/lib/formatters";

const boxStyle: React.CSSProperties = {
  padding: "12px 14px", background: "var(--surface-2)",
  borderRadius: "var(--r-md)", border: "1px solid var(--border)",
};

function ReviewModal({ action, rec, onClose, onDone }: { action: "approve" | "reject"; rec: AIRecommendation; onClose: () => void; onDone: (r: AIRecommendation) => void }) {
  const toast = useToast();
  const qc = useQueryClient();
  const [note, setNote] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const inventoryAnalysis = rec.analysis_type === "INVENTORY_ANALYSIS";
  const mutation = useMutation({
    mutationFn: () => action === "approve" ? AIApi.approve(rec.id, note.trim() || undefined) : AIApi.reject(rec.id, note.trim()),
    onSuccess: (data) => {
      if (action === "approve" && inventoryAnalysis && (data.supply_requests_created ?? 0) > 0) {
        toast.success("Analysis approved", `${data.supply_requests_created} supply request(s) sent to the central system.`);
        qc.invalidateQueries({ queryKey: ["supply-requests"] });
      } else {
        toast.success(action === "approve" ? "Recommendation approved" : "Recommendation rejected", "This is a review bookmark — no stock was moved.");
      }
      qc.invalidateQueries({ queryKey: ["ai-recommendation", rec.id] });
      qc.invalidateQueries({ queryKey: ["ai-recommendations"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      onDone(data);
      onClose();
    },
    onError: (e) => {
      if (isApiError(e)) { setFieldErrors(e.fieldErrors ?? {}); toast.error("Review failed", e.detail); }
      else toast.error("Review failed", "Something went wrong.");
    },
  });
  const fe = (k: string) => fieldErrors[k];
  const valid = action === "approve" || note.trim() !== "";
  return (
    <Modal
      open
      onClose={onClose}
      title={action === "approve" ? "Approve recommendation" : "Reject recommendation"}
      subtitle={rec.analysis_type_display || humanize(rec.analysis_type)}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={mutation.isPending}>Cancel</Button>
          <Button variant={action === "approve" ? "success" : "danger"} loading={mutation.isPending} disabled={!valid} onClick={() => mutation.mutate()}>{action === "approve" ? "Approve" : "Reject"}</Button>
        </>
      }
    >
      <div className="stack" style={{ gap: 14 }}>
        <div className={`alert ${action === "approve" ? "alert-success" : "alert-warning"}`}>
          <Icon name={action === "approve" ? "check-circle" : "alert"} size={16} />
          <span>
            {action === "approve"
              ? inventoryAnalysis
                ? "Approving records this analysis as reviewed and automatically sends its transfer recommendations to the central system as supply requests. No stock moves until central and the source facility act."
                : "Approving bookmarks this recommendation as reviewed. It does not move stock or create transfers — act on any suggestions separately."
              : "Rejecting marks this recommendation as not actioned. A reason is required."}
          </span>
        </div>
        <Field label={action === "approve" ? "Review note" : "Rejection reason"} required={action === "reject"} error={fe("note")}>
          <TextArea rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder={action === "approve" ? "Optional context for the audit trail…" : "Why is this recommendation being rejected?"} invalid={!!fe("note")} />
        </Field>
      </div>
    </Modal>
  );
}

function BulletList({ items, icon }: { items: string[]; icon: "info" | "alert" }) {
  return (
    <div className="stack" style={{ gap: 8 }}>
      {items.map((s, i) => (
        <div key={i} className="row" style={{ gap: 9, alignItems: "flex-start" }}>
          <Icon name={icon} size={15} />
          <span style={{ fontSize: 13.5, lineHeight: 1.5 }}>{s}</span>
        </div>
      ))}
    </div>
  );
}

export function AIDetailPage() {
  const { id } = useParams();
  const recId = Number(id);
  const { user } = useAuth();
  const navigate = useNavigate();
  const [review, setReview] = useState<"approve" | "reject" | null>(null);
  const [lang, setLang] = useState<"en" | "am">("en");
  const q = useQuery({ queryKey: ["ai-recommendation", recId], queryFn: () => AIApi.get(recId), enabled: Number.isFinite(recId) });

  if (q.isLoading) return <LoadingState label="Loading recommendation…" />;
  if (q.error || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const r = q.data;
  const out = r.validated_output ?? {};
  const central = isCentral(user?.role);
  const canReview = canReviewAI(user?.role) && r.status === "PENDING_REVIEW" && (central || (r.scope_facility !== null && r.scope_facility === user?.facility));
  const failed = r.status === "FAILED";
  const summary = r.summary || out.summary || "";
  const errors = r.validation_errors ?? [];
  const hasAmharic = Boolean(
    out.summary_amharic ||
    out.risks?.some((x) => x.reason_amharic) ||
    out.transfer_recommendations?.some((x) => x.reason_amharic) ||
    out.ranked_gaps?.some((x) => x.reason_amharic) ||
    out.by_product?.some((x) => x.comment_amharic) ||
    out.proposals?.some((x) => x.reason_amharic) ||
    out.priorities_amharic?.length ||
    out.missing_information_amharic?.length
  );
  const tr = (en: string, am?: string) => (lang === "am" && am ? am : en);
  const translatedList = (list: string[] | undefined, amList: string[] | undefined) =>
    lang === "am" && amList?.length ? (list ?? []).map((s, i) => amList[i] || s) : list;

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Advisory AI"
        title={r.analysis_type_display || humanize(r.analysis_type)}
        description={`${r.scope_facility_name || "Nationwide scope"} · requested by ${r.requested_by_username} · ${formatDateTime(r.created_at)}`}
        actions={
          <div className="row wrap" style={{ gap: 8 }}>
            <Button variant="ghost" icon="chevron-left" onClick={() => navigate("/ai")}>All recommendations</Button>
            {canReview && <Button variant="danger" icon="x" onClick={() => setReview("reject")}>Reject</Button>}
            {canReview && <Button variant="success" icon="check" onClick={() => setReview("approve")}>Approve</Button>}
          </div>
        }
      />

      <div className="row wrap" style={{ gap: 8 }}>
        <Badge value={r.status}>{r.status_display || humanize(r.status)}</Badge>
        <span className="chip"><Icon name="sparkles" size={13} /> {r.model_name}</span>
        {r.scope_facility_name && <span className="chip"><Icon name="building" size={13} /> {r.scope_facility_name}</span>}
        {hasAmharic && (
          <div className="row" style={{ gap: 0, marginLeft: "auto", border: "1px solid var(--border)", borderRadius: 999, overflow: "hidden" }}>
            {([["en", "English"], ["am", "አማርኛ"]] as const).map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => setLang(key)}
                style={{ padding: "4px 12px", fontSize: 12.5, border: "none", cursor: "pointer", background: lang === key ? "var(--brand)" : "transparent", color: lang === key ? "#fff" : "var(--muted)", fontWeight: lang === key ? 600 : 400 }}
              >
                {label}
              </button>
            ))}
          </div>
        )}
      </div>

      {r.status === "PENDING_REVIEW" && <div className="alert alert-info"><Icon name="eye" size={16} /><span>Awaiting human review. {canReview ? (r.analysis_type === "INVENTORY_ANALYSIS" ? "Approving sends the transfer recommendations to the central system as supply requests." : "Approve to bookmark this recommendation, or reject it with a reason.") : "A coordinator or your facility manager can review this."} Approval never moves stock directly.</span></div>}
      {r.status === "APPROVED" && <div className="alert alert-success"><Icon name="check-circle" size={16} /><span>Approved by <strong>{r.reviewed_by_username}</strong> on {formatDateTime(r.reviewed_at)}. {r.analysis_type === "INVENTORY_ANALYSIS" ? "Its transfer recommendations were sent to the central system as supply requests." : "This is a review bookmark — no stock was moved."}</span></div>}
      {r.status === "REJECTED" && <div className="alert alert-danger"><Icon name="x-circle" size={16} /><span>Rejected by <strong>{r.reviewed_by_username}</strong> on {formatDateTime(r.reviewed_at)}.{r.review_note ? ` Reason: ${r.review_note}` : ""}</span></div>}
      {failed && <div className="alert alert-danger"><Icon name="alert" size={16} /><span><strong>Analysis failed.</strong> {r.error || "The AI service was unavailable or returned invalid output."} No recommendation was produced.</span></div>}
      {r.status === "INVALID" && <div className="alert alert-warning"><Icon name="alert" size={16} /><span>The model returned no validated, actionable content for this scope.</span></div>}

      {summary && (
        <Card>
          <CardHeader title="Summary" icon="sparkles" />
          <CardBody><p style={{ margin: 0, lineHeight: 1.7, fontSize: 14, whiteSpace: "pre-line" }}>{tr(summary, out.summary_amharic)}</p></CardBody>
        </Card>
      )}

      {errors.length > 0 && (
        <Card>
          <CardHeader title="Validation filters" subtitle={`${errors.length} suggestion${errors.length === 1 ? "" : "s"} removed during live-data validation`} icon="shield" />
          <CardBody>
            <div className="stack" style={{ gap: 8 }}>
              {errors.map((e, i) => (
                <div key={i} className="row wrap" style={{ gap: 8, alignItems: "center", ...boxStyle }}>
                  <Badge tone="amber" dot={false}>{humanize(String(e.code ?? "invalid"))}</Badge>
                  <span className="muted mono" style={{ fontSize: 12 }}>{Object.entries(e).filter(([k]) => k !== "code").map(([k, v]) => `${k}: ${v}`).join(" · ")}</span>
                </div>
              ))}
            </div>
          </CardBody>
        </Card>
      )}

      {!failed && (out.risks?.length ?? 0) > 0 && (
        <Card>
          <CardHeader title="Stock risks" subtitle={`${out.risks!.length} flagged`} icon="alert" />
          <CardBody>
            <div className="stack" style={{ gap: 10 }}>
              {out.risks!.map((risk, i) => (
                <div key={i} style={boxStyle}>
                  <div className="row-between wrap" style={{ gap: 8 }}>
                    <strong style={{ fontSize: 13.5 }}>{risk.facility_name || `Facility #${risk.facility_id}`}</strong>
                    <Badge value={risk.priority} dot={false}>{humanize(risk.priority)}</Badge>
                  </div>
                  <div style={{ fontSize: 13, lineHeight: 1.5, marginTop: 6 }}>{tr(risk.reason, risk.reason_amharic)}</div>
                  <div className="cell-sub" style={{ marginTop: 4 }}>Product #{risk.product_id}</div>
                </div>
              ))}
            </div>
          </CardBody>
        </Card>
      )}

      {!failed && (out.transfer_recommendations?.length ?? 0) > 0 && (
        <Card>
          <CardHeader title="Redistribution recommendations" subtitle="Advisory — create a transfer to act on a suggestion" icon="transfer" />
          <CardBody>
            <div className="stack" style={{ gap: 10 }}>
              {out.transfer_recommendations!.map((t, i) => (
                <div key={i} style={boxStyle}>
                  <div className="row-between wrap" style={{ gap: 8 }}>
                    <div className="row wrap" style={{ gap: 8 }}>
                      <Icon name="transfer" size={16} />
                      <strong style={{ fontSize: 13.5 }}>{t.product_name || `Product #${t.product_id}`}</strong>
                      <Badge tone="teal" dot={false}>{formatNumber(t.quantity)} units</Badge>
                    </div>
                    {canRequestTransfer(user?.role) && (
                      <Button size="sm" variant="secondary" icon="plus" onClick={() => navigate(`/transfers?new=1&product=${t.product_id}&source=${t.source_facility_id}&dest=${t.destination_facility_id}&quantity=${t.quantity}`)}>Create transfer</Button>
                    )}
                  </div>
                  <div className="muted" style={{ fontSize: 13, marginTop: 6 }}>{t.source_facility_name || `#${t.source_facility_id}`} → {t.destination_facility_name || `#${t.destination_facility_id}`}</div>
                  <div style={{ fontSize: 13, lineHeight: 1.5, marginTop: 4 }}>{tr(t.reason, t.reason_amharic)}</div>
                </div>
              ))}
            </div>
          </CardBody>
        </Card>
      )}

      {!failed && (out.proposals?.length ?? 0) > 0 && (
        <Card>
          <CardHeader title="Planned donor transfers" subtitle="One proposal per fillable supply request — review them under Supply Requests" icon="truck" />
          <CardBody>
            <div className="stack" style={{ gap: 10 }}>
              {out.proposals!.map((p, i) => (
                <div key={i} style={boxStyle}>
                  <div className="row-between wrap" style={{ gap: 8 }}>
                    <div className="row wrap" style={{ gap: 8 }}>
                      <Icon name="transfer" size={16} />
                      <strong style={{ fontSize: 13.5 }}>{p.product_name || `Product #${p.product_id}`}</strong>
                      <Badge tone="teal" dot={false}>{formatNumber(p.quantity)} units</Badge>
                    </div>
                    {central && <Button size="sm" variant="secondary" icon="arrow-right" onClick={() => navigate("/supply-requests")}>Review proposals</Button>}
                  </div>
                  <div className="muted" style={{ fontSize: 13, marginTop: 6 }}>{p.source_facility_name || `#${p.source_facility_id}`} → {p.requesting_facility_name || `#${p.requesting_facility_id}`}</div>
                  <div style={{ fontSize: 13, lineHeight: 1.5, marginTop: 4 }}>{tr(p.reason, p.reason_amharic)}</div>
                </div>
              ))}
            </div>
          </CardBody>
        </Card>
      )}

      {!failed && (out.ranked_gaps?.length ?? 0) > 0 && (
        <Card>
          <CardHeader title="Prioritized supply gaps" subtitle="Ranked by urgency (1 = most urgent)" icon="gap" />
          <CardBody>
            <div className="stack" style={{ gap: 10 }}>
              {out.ranked_gaps!.map((g) => (
                <div key={g.gap_id} className="row" style={{ gap: 12, alignItems: "flex-start", ...boxStyle }}>
                  <div style={{ flex: "0 0 auto", width: 30, height: 30, borderRadius: 999, background: "var(--brand)", color: "#fff", display: "grid", placeItems: "center", fontWeight: 700, fontSize: 14 }}>{g.rank}</div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="row-between wrap" style={{ gap: 8 }}>
                      <Link to="/supply-gaps" style={{ fontWeight: 600, fontSize: 13.5, color: "var(--brand)" }}>Gap #{g.gap_id}</Link>
                      <Badge value={g.priority} dot={false}>{humanize(g.priority)}</Badge>
                    </div>
                    <div style={{ fontSize: 13, lineHeight: 1.5, marginTop: 4 }}>{tr(g.reason, g.reason_amharic)}</div>
                  </div>
                </div>
              ))}
            </div>
          </CardBody>
        </Card>
      )}

      {!failed && (out.by_product?.length ?? 0) > 0 && (
        <Card>
          <CardHeader title="Vaccination demand by product" subtitle="Aggregate follow-up demand versus stock — no patient identifiers" icon="syringe" />
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Vaccine</th><th className="num">Open</th><th className="num">Due ≤7d</th><th className="num">Due in horizon</th><th className="num">Usable stock</th><th className="num">Projected gap</th>
                </tr>
              </thead>
              <tbody>
                {out.by_product!.map((p) => (
                  <tr key={p.product_id}>
                    <td>
                      <div className="stack" style={{ gap: 2 }}>
                        <span className="cell-title">{p.product_name}</span>
                        {p.comment && <span className="cell-sub" style={{ maxWidth: 320 }}>{tr(p.comment, p.comment_amharic)}</span>}
                      </div>
                    </td>
                    <td className="num">{formatNumber(p.open_follow_ups)}</td>
                    <td className="num">{formatNumber(p.due_next_7_days)}</td>
                    <td className="num">{formatNumber(p.due_next_30_days)}</td>
                    <td className="num">{formatNumber(p.usable_stock)}</td>
                    <td className="num" style={{ color: (p.projected_gap ?? 0) > 0 ? "var(--red)" : undefined, fontWeight: (p.projected_gap ?? 0) > 0 ? 700 : 400 }}>{formatNumber(p.projected_gap)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {!failed && (out.unresolved_gaps?.length ?? 0) > 0 && (
        <Card>
          <CardHeader title="Unresolved gaps" subtitle="Shortages the AI could not cover with a validated transfer" icon="gap" />
          <CardBody>
            <div className="stack" style={{ gap: 8 }}>
              {out.unresolved_gaps!.map((g, i) => (
                <div key={i} className="row-between wrap" style={{ gap: 8, ...boxStyle }}>
                  <span className="muted" style={{ fontSize: 13 }}>Facility #{g.facility_id} · Product #{g.product_id}</span>
                  <Badge tone="red" dot={false}>{formatNumber(g.quantity)} units short</Badge>
                </div>
              ))}
            </div>
          </CardBody>
        </Card>
      )}

      {!failed && (out.priorities?.length ?? 0) > 0 && (
        <Card><CardHeader title="Priorities" icon="trend-up" /><CardBody><BulletList items={translatedList(out.priorities, out.priorities_amharic)!} icon="alert" /></CardBody></Card>
      )}
      {(out.missing_information?.length ?? 0) > 0 && (
        <Card><CardHeader title="Missing information" subtitle="Gaps in the data that limited this analysis" icon="info" /><CardBody><BulletList items={translatedList(out.missing_information, out.missing_information_amharic)!} icon="info" /></CardBody></Card>
      )}

      {r.reviewed_at && (
        <Card>
          <CardHeader title="Review record" icon="audit" />
          <CardBody>
            <div className="detail-grid">
              <div className="detail-item"><div className="dt">Reviewed by</div><div className="dd">{r.reviewed_by_username || "—"}</div></div>
              <div className="detail-item"><div className="dt">Reviewed at</div><div className="dd">{formatDateTime(r.reviewed_at)}</div></div>
              <div className="detail-item"><div className="dt">Outcome</div><div className="dd">{humanize(r.status)}</div></div>
              <div className="detail-item"><div className="dt">Note</div><div className="dd" style={{ fontWeight: 400 }}>{r.review_note || "—"}</div></div>
            </div>
          </CardBody>
        </Card>
      )}

      {central && (r.input_snapshot || r.raw_output) && (
        <details className="card" style={{ padding: "0 16px" }}>
          <summary style={{ cursor: "pointer", padding: "14px 0", fontWeight: 600, fontSize: 13.5, color: "var(--muted)" }}>
            <Icon name="flask" size={15} /> Technical details (input snapshot & raw model output)
          </summary>
          <div style={{ paddingBottom: 16 }}>
            {r.input_snapshot && <pre className="code-block">{JSON.stringify(r.input_snapshot, null, 2)}</pre>}
            {r.raw_output && <pre className="code-block" style={{ marginTop: 10 }}>{JSON.stringify(r.raw_output, null, 2)}</pre>}
          </div>
        </details>
      )}

      {review && <ReviewModal action={review} rec={r} onClose={() => setReview(null)} onDone={() => q.refetch()} />}
    </div>
  );
}