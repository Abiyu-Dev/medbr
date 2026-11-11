import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FacilitiesApi } from "@/api/endpoints";
import { isApiError } from "@/api/client";
import type { Role, UserProfile } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { useList } from "@/hooks/useList";
import { canManageUsers, isAdmin, ROLE_LABELS } from "@/lib/permissions";
import { Badge, Button, Card, ConfirmDialog, DataTable, EmptyState, Field, Icon, Modal, PageHeader, SearchBox, SelectInput, TextInput, useToast, type Column } from "@/components/ui";
import { FacilitySelect } from "@/components/forms/Pickers";
import { formatDate, initials } from "@/lib/formatters";

const FACILITY_ROLES: Role[] = ["FACILITY_MANAGER", "PHARMACIST", "INVENTORY_STAFF", "PHARMACY_STAFF", "HEALTH_WORKER"];

function CreateUserModal({ facilityId, admin, onClose }: { facilityId: number; admin: boolean; onClose: () => void }) {
  const toast = useToast();
  const qc = useQueryClient();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("PHARMACIST");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [phone, setPhone] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const roles = admin ? FACILITY_ROLES : FACILITY_ROLES.filter((r) => r !== "FACILITY_MANAGER");
  const mutation = useMutation({
    mutationFn: () => FacilitiesApi.createUser(facilityId, {
      username: username.trim(),
      email: email.trim(),
      password,
      role,
      first_name: firstName.trim(),
      last_name: lastName.trim(),
      phone: phone.trim(),
    }),
    onSuccess: () => {
      toast.success("User created", `${username.trim()} can now sign in.`);
      qc.invalidateQueries({ queryKey: ["facility-users", facilityId] });
      onClose();
    },
    onError: (e) => {
      if (isApiError(e)) { setFieldErrors(e.fieldErrors ?? {}); toast.error("Could not create user", e.detail); }
      else toast.error("Could not create user", "Something went wrong.");
    },
  });
  const fe = (k: string) => fieldErrors[k];
  const valid = username.trim() !== "" && email.trim() !== "" && password.length >= 8;

  return (
    <Modal
      open
      onClose={onClose}
      title="Add staff user"
      subtitle="Create a login for a member of this facility."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={mutation.isPending}>Cancel</Button>
          <Button loading={mutation.isPending} disabled={!valid} onClick={() => mutation.mutate()}>Create user</Button>
        </>
      }
    >
      <div className="stack" style={{ gap: 14 }}>
        <div className="field-row">
          <Field label="First name" error={fe("first_name")}><TextInput value={firstName} onChange={(e) => setFirstName(e.target.value)} /></Field>
          <Field label="Last name" error={fe("last_name")}><TextInput value={lastName} onChange={(e) => setLastName(e.target.value)} /></Field>
        </div>
        <Field label="Username" required error={fe("username")}>
          <TextInput value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="off" invalid={!!fe("username")} />
        </Field>
        <Field label="Email" required error={fe("email")}>
          <TextInput type="email" value={email} onChange={(e) => setEmail(e.target.value)} invalid={!!fe("email")} />
        </Field>
        <Field label="Password" required error={fe("password")} help="Minimum 8 characters. Share securely with the staff member.">
          <TextInput type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" invalid={!!fe("password")} />
        </Field>
        <div className="field-row">
          <Field label="Role" required error={fe("role")}>
            <SelectInput value={role} onChange={(e) => setRole(e.target.value as Role)}>
              {roles.map((r) => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
            </SelectInput>
          </Field>
          <Field label="Phone" error={fe("phone")}><TextInput value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+251…" /></Field>
        </div>
        {!admin && <div className="alert alert-info"><Icon name="info" size={16} /><span>Only a system admin can create another facility manager.</span></div>}
      </div>
    </Modal>
  );
}

function UsersTable({ facilityId, admin }: { facilityId: number; admin: boolean }) {
  const { user } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const list = useList<UserProfile>(["facility-users", facilityId], (p) => FacilitiesApi.users(facilityId, p));
  const [create, setCreate] = useState(false);
  const [deactivate, setDeactivate] = useState<UserProfile | null>(null);

  const mutation = useMutation({
    mutationFn: (u: UserProfile) => FacilitiesApi.deactivateUser(facilityId, u.id),
    onSuccess: (_, u) => {
      toast.success("User deactivated", `${u.username} can no longer sign in.`);
      qc.invalidateQueries({ queryKey: ["facility-users", facilityId] });
      setDeactivate(null);
    },
    onError: (e) => toast.error("Could not deactivate", isApiError(e) ? e.detail : "Something went wrong."),
  });

  const columns: Column<UserProfile>[] = [
    {
      key: "user",
      header: "User",
      render: (u) => (
        <div className="row" style={{ gap: 10 }}>
          <div className="avatar avatar-sm">{initials(u.first_name ? `${u.first_name} ${u.last_name}` : u.username)}</div>
          <div className="stack" style={{ gap: 2 }}>
            <span className="cell-title">{u.first_name || u.last_name ? `${u.first_name} ${u.last_name}`.trim() : u.username}</span>
            <span className="cell-sub">@{u.username}</span>
          </div>
        </div>
      ),
    },
    { key: "role", header: "Role", render: (u) => <Badge tone="teal" dot={false}>{ROLE_LABELS[u.role]}</Badge> },
    { key: "email", header: "Email", render: (u) => <span className="cell-sub">{u.email || "—"}</span> },
    { key: "phone", header: "Phone", render: (u) => u.phone || "—" },
    { key: "status", header: "Status", render: (u) => <Badge tone={u.is_active ? "green" : "slate"} dot={false}>{u.is_active ? "Active" : "Inactive"}</Badge> },
    { key: "joined", header: "Joined", render: (u) => formatDate(u.date_joined) },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (u) => (
        <Button
          variant="ghost"
          size="sm"
          icon="ban"
          title="Deactivate user"
          disabled={!u.is_active || u.id === user?.id}
          onClick={() => setDeactivate(u)}
        />
      ),
    },
  ];

  return (
    <>
      <Card>
        <div className="toolbar">
          <SearchBox value={list.search} onChange={list.setSearch} placeholder="Search staff…" />
          <Button icon="plus" onClick={() => setCreate(true)}>Add user</Button>
        </div>
        <DataTable
          columns={columns}
          rows={list.rows}
          rowKey={(u) => u.id}
          isLoading={list.query.isLoading}
          error={list.query.error}
          onRetry={() => list.query.refetch()}
          empty={{ icon: "users", title: "No staff yet", message: "Add pharmacists, inventory staff and health workers.", action: <Button icon="plus" onClick={() => setCreate(true)}>Add user</Button> }}
          pagination={{ page: list.page, count: list.count, pageSize: list.pageSize, onPageChange: list.setPage }}
        />
      </Card>
      {create && <CreateUserModal facilityId={facilityId} admin={admin} onClose={() => setCreate(false)} />}
      <ConfirmDialog
        open={!!deactivate}
        onClose={() => setDeactivate(null)}
        onConfirm={() => deactivate && mutation.mutate(deactivate)}
        title="Deactivate user"
        message={<>Deactivate <strong>{deactivate?.username}</strong>? They will no longer be able to sign in. This does not delete their recorded activity.</>}
        confirmLabel="Deactivate"
        danger
        loading={mutation.isPending}
      />
    </>
  );
}

export function UsersPage() {
  const { user } = useAuth();
  const [params] = useSearchParams();
  const admin = isAdmin(user?.role);
  const paramFacility = params.get("facility");
  const [picked, setPicked] = useState<number | "">(paramFacility ? Number(paramFacility) : "");
  const facilityId = admin ? picked : (user?.facility ?? "");

  if (!canManageUsers(user?.role)) {
    return <EmptyState icon="lock" title="Not authorized" message="Only facility managers and system admins can manage staff." />;
  }

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Facility"
        title="Staff & users"
        description="Manage the logins for your facility team."
      />
      {admin && (
        <div className="alert alert-info" style={{ alignItems: "center" }}>
          <Icon name="building" size={17} />
          <span style={{ flex: 1 }}>Select a facility to manage its staff.</span>
          <div style={{ minWidth: 240 }}>
            <FacilitySelect value={picked} onChange={setPicked} onlyApproved={false} />
          </div>
        </div>
      )}
      {facilityId === "" ? (
        <Card><EmptyState icon="building" title="Select a facility" message="Choose a facility above to manage its staff." /></Card>
      ) : (
        <UsersTable facilityId={facilityId} admin={admin} />
      )}
    </div>
  );
}