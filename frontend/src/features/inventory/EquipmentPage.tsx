import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { EquipmentApi } from "@/api/endpoints";
import { isApiError } from "@/api/client";
import type { Equipment, EquipmentCondition } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { useList } from "@/hooks/useList";
import { canManageStock } from "@/lib/permissions";
import { formatDate, formatNumber, localInputToISO } from "@/lib/formatters";
import { Badge, Button, Card, DataTable, Field, Icon, Modal, PageHeader, SearchBox, SelectInput, StatCard, TextArea, TextInput, useToast, type Column } from "@/components/ui";
import { useInventoryScope, FacilityScopeBar } from "./InventoryScope";

const CONDITIONS: EquipmentCondition[] = ["OPERATIONAL", "NEEDS_MAINTENANCE", "OUT_OF_SERVICE"];

function EquipmentModal({ equipment, facilityId, onClose }: { equipment: Equipment | null; facilityId?: number; onClose: () => void }) {
  const toast = useToast();
  const qc = useQueryClient();
  const [name, setName] = useState(equipment?.name ?? "");
  const [category, setCategory] = useState(equipment?.category ?? "");
  const [asset, setAsset] = useState(equipment?.asset_identifier ?? "");
  const [quantity, setQuantity] = useState(String(equipment?.quantity ?? 1));
  const [condition, setCondition] = useState<EquipmentCondition>(equipment?.condition ?? "OPERATIONAL");
  const [notes, setNotes] = useState(equipment?.notes ?? "");
  const [checked, setChecked] = useState(equipment?.last_checked_at ? equipment.last_checked_at.slice(0, 16) : "");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const mutation = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = {
        name: name.trim(),
        category: category.trim(),
        asset_identifier: asset.trim(),
        quantity: Number(quantity),
        condition,
        notes: notes.trim(),
        last_checked_at: localInputToISO(checked) ?? null,
      };
      if (equipment) return EquipmentApi.update(equipment.id, body);
      if (facilityId) body.facility = facilityId;
      return EquipmentApi.create(body);
    },
    onSuccess: () => {
      toast.success(equipment ? "Equipment updated" : "Equipment added", name.trim());
      qc.invalidateQueries({ queryKey: ["equipment"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      onClose();
    },
    onError: (e) => {
      if (isApiError(e)) { setFieldErrors(e.fieldErrors ?? {}); toast.error("Could not save", e.detail); }
      else toast.error("Could not save", "Something went wrong.");
    },
  });
  const fe = (k: string) => fieldErrors[k];
  const valid = name.trim() !== "" && Number(quantity) >= 0;

  return (
    <Modal
      open
      onClose={onClose}
      title={equipment ? "Edit equipment" : "Add equipment"}
      subtitle="Cold-chain and other facility assets."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={mutation.isPending}>Cancel</Button>
          <Button loading={mutation.isPending} disabled={!valid} onClick={() => mutation.mutate()}>{equipment ? "Save" : "Add equipment"}</Button>
        </>
      }
    >
      <div className="stack" style={{ gap: 14 }}>
        <Field label="Name" required error={fe("name")}>
          <TextInput value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Vaccine refrigerator" invalid={!!fe("name")} />
        </Field>
        <div className="field-row">
          <Field label="Category" error={fe("category")}>
            <TextInput value={category} onChange={(e) => setCategory(e.target.value)} placeholder="Cold chain" />
          </Field>
          <Field label="Asset identifier" error={fe("asset_identifier")}>
            <TextInput value={asset} onChange={(e) => setAsset(e.target.value)} placeholder="FRIDGE-01" />
          </Field>
        </div>
        <div className="field-row">
          <Field label="Quantity" error={fe("quantity")}>
            <TextInput type="number" min={0} step={1} value={quantity} onChange={(e) => setQuantity(e.target.value)} />
          </Field>
          <Field label="Condition" error={fe("condition")}>
            <SelectInput value={condition} onChange={(e) => setCondition(e.target.value as EquipmentCondition)}>
              {CONDITIONS.map((c) => <option key={c} value={c}>{c.replace(/_/g, " ")}</option>)}
            </SelectInput>
          </Field>
        </div>
        <Field label="Last checked" error={fe("last_checked_at")}>
          <TextInput type="datetime-local" value={checked} onChange={(e) => setChecked(e.target.value)} />
        </Field>
        <Field label="Notes" error={fe("notes")}>
          <TextArea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Maintenance notes, capacity, etc." />
        </Field>
      </div>
    </Modal>
  );
}

export function EquipmentPage() {
  const { user } = useAuth();
  const scope = useInventoryScope();
  const manage = canManageStock(user?.role);
  const list = useList<Equipment>(["equipment", scope.params], (p) => EquipmentApi.list({ ...p, ...scope.params }), { condition: "" });
  const [modal, setModal] = useState<{ equipment: Equipment | null } | null>(null);

  const rows = list.rows;
  const operational = rows.filter((e) => e.condition === "OPERATIONAL").length;
  const maintenance = rows.filter((e) => e.condition === "NEEDS_MAINTENANCE").length;
  const out = rows.filter((e) => e.condition === "OUT_OF_SERVICE").length;

  const columns: Column<Equipment>[] = [
    {
      key: "name",
      header: "Asset",
      render: (e) => (
        <div className="stack" style={{ gap: 2 }}>
          <span className="cell-title">{e.name}</span>
          <span className="cell-sub">{e.asset_identifier || e.category || "—"}</span>
        </div>
      ),
    },
    { key: "category", header: "Category", render: (e) => e.category || "—" },
    { key: "qty", header: "Qty", align: "right", render: (e) => formatNumber(e.quantity) },
    { key: "condition", header: "Condition", render: (e) => <Badge value={e.condition}>{e.condition_display}</Badge> },
    { key: "checked", header: "Last checked", render: (e) => formatDate(e.last_checked_at) },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (e) => manage ? <Button variant="ghost" size="sm" icon="edit" title="Edit" onClick={() => setModal({ equipment: e })} /> : null,
    },
  ];

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Inventory"
        title="Equipment"
        description="Facility assets such as cold-chain equipment, with condition and maintenance tracking."
        actions={manage && <Button icon="plus" onClick={() => setModal({ equipment: null })} disabled={scope.central && !scope.enabled}>Add equipment</Button>}
      />
      {scope.central && <FacilityScopeBar facilityId={scope.facilityId} onChange={scope.setFacilityId} />}
      <div className="stat-grid stagger">
        <StatCard label="Total assets" value={formatNumber(rows.length)} sub="tracked equipment" icon="flask" tone="teal" />
        <StatCard label="Operational" value={formatNumber(operational)} sub="ready for use" icon="check-circle" tone="green" />
        <StatCard label="Needs maintenance" value={formatNumber(maintenance)} sub="schedule service" icon="settings" tone={maintenance ? "amber" : "slate"} />
        <StatCard label="Out of service" value={formatNumber(out)} sub="not usable" icon="alert" tone={out ? "red" : "slate"} />
      </div>
      <Card>
        <div className="toolbar">
          <SearchBox value={list.search} onChange={list.setSearch} placeholder="Search equipment…" />
          <SelectInput value={list.filters.condition ?? ""} onChange={(e) => list.setFilter("condition", e.target.value)} style={{ width: "auto" }}>
            <option value="">All conditions</option>
            {CONDITIONS.map((c) => <option key={c} value={c}>{c.replace(/_/g, " ")}</option>)}
          </SelectInput>
        </div>
        <DataTable
          columns={columns}
          rows={rows}
          rowKey={(e) => e.id}
          isLoading={list.query.isLoading}
          error={list.query.error}
          onRetry={() => list.query.refetch()}
          empty={{ icon: "flask", title: "No equipment recorded", message: "Add cold-chain and other assets to track their condition.", action: manage ? <Button icon="plus" onClick={() => setModal({ equipment: null })}>Add equipment</Button> : undefined }}
          pagination={{ page: list.page, count: list.count, pageSize: list.pageSize, onPageChange: list.setPage }}
        />
      </Card>
      {modal && <EquipmentModal equipment={modal.equipment} facilityId={scope.central ? (scope.facilityId || undefined) : undefined} onClose={() => setModal(null)} />}
    </div>
  );
}