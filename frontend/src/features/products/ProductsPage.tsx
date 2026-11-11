import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ProductsApi } from "@/api/endpoints";
import { isApiError } from "@/api/client";
import type { Product, ProductCategory } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { useList } from "@/hooks/useList";
import { canCreateProduct } from "@/lib/permissions";
import { Badge, Button, Card, Checkbox, DataTable, Field, Icon, Modal, PageHeader, SearchBox, SelectInput, TextArea, TextInput, useToast, type Column } from "@/components/ui";

function ProductModal({ product, onClose }: { product: Product | null; onClose: () => void }) {
  const toast = useToast();
  const qc = useQueryClient();
  const [name, setName] = useState(product?.name ?? "");
  const [category, setCategory] = useState<ProductCategory>(product?.category ?? "MEDICINE");
  const [generic, setGeneric] = useState(product?.generic_name ?? "");
  const [strength, setStrength] = useState(product?.strength ?? "");
  const [form, setForm] = useState(product?.dosage_form ?? "");
  const [unit, setUnit] = useState(product?.unit_of_measure ?? "");
  const [description, setDescription] = useState(product?.description ?? "");
  const [coldChain, setColdChain] = useState(product?.requires_cold_chain ?? false);
  const [minTemp, setMinTemp] = useState(product?.storage_min_temperature ?? "");
  const [maxTemp, setMaxTemp] = useState(product?.storage_max_temperature ?? "");
  const [active, setActive] = useState(product?.active ?? true);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const mutation = useMutation({
    mutationFn: () => {
      const body = {
        name: name.trim(),
        category,
        generic_name: generic.trim(),
        strength: strength.trim(),
        dosage_form: form.trim(),
        unit_of_measure: unit.trim(),
        description: description.trim(),
        requires_cold_chain: coldChain,
        storage_min_temperature: coldChain && minTemp !== "" ? minTemp : null,
        storage_max_temperature: coldChain && maxTemp !== "" ? maxTemp : null,
        active,
      };
      return product ? ProductsApi.update(product.id, body) : ProductsApi.create(body);
    },
    onSuccess: () => {
      toast.success(product ? "Product updated" : "Product created", name.trim());
      qc.invalidateQueries({ queryKey: ["products"] });
      onClose();
    },
    onError: (e) => {
      if (isApiError(e)) { setFieldErrors(e.fieldErrors ?? {}); toast.error("Could not save", e.detail); }
      else toast.error("Could not save", "Something went wrong.");
    },
  });
  const fe = (k: string) => fieldErrors[k];
  const valid = name.trim() !== "" && unit.trim() !== "";

  return (
    <Modal
      open
      onClose={onClose}
      wide
      title={product ? "Edit product" : "New product"}
      subtitle="Catalogue entries are shared across the network."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={mutation.isPending}>Cancel</Button>
          <Button loading={mutation.isPending} disabled={!valid} onClick={() => mutation.mutate()}>{product ? "Save" : "Create product"}</Button>
        </>
      }
    >
      <div className="stack" style={{ gap: 14 }}>
        <div className="field-row">
          <Field label="Name" required error={fe("name")}>
            <TextInput value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Paracetamol" invalid={!!fe("name")} />
          </Field>
          <Field label="Category" required error={fe("category")}>
            <SelectInput value={category} onChange={(e) => setCategory(e.target.value as ProductCategory)}>
              <option value="MEDICINE">Medicine</option>
              <option value="VACCINE">Vaccine</option>
            </SelectInput>
          </Field>
        </div>
        <div className="field-row-3">
          <Field label="Generic name" error={fe("generic_name")}>
            <TextInput value={generic} onChange={(e) => setGeneric(e.target.value)} />
          </Field>
          <Field label="Strength" error={fe("strength")}>
            <TextInput value={strength} onChange={(e) => setStrength(e.target.value)} placeholder="500 mg" />
          </Field>
          <Field label="Dosage form" error={fe("dosage_form")}>
            <TextInput value={form} onChange={(e) => setForm(e.target.value)} placeholder="Tablet" />
          </Field>
        </div>
        <div className="field-row">
          <Field label="Unit of measure" required error={fe("unit_of_measure")}>
            <TextInput value={unit} onChange={(e) => setUnit(e.target.value)} placeholder="tablets / doses / vials" invalid={!!fe("unit_of_measure")} />
          </Field>
          <Field label="Status">
            <div style={{ paddingTop: 6 }}>
              <Checkbox label="Active in catalogue" checked={active} onChange={(e) => setActive(e.target.checked)} />
            </div>
          </Field>
        </div>
        <Field label="Description" error={fe("description")}>
          <TextArea rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
        </Field>
        <div className="divider" />
        <Checkbox label="Requires cold chain" checked={coldChain} onChange={(e) => setColdChain(e.target.checked)} />
        {coldChain && (
          <div className="field-row">
            <Field label="Min storage temperature (°C)" error={fe("storage_min_temperature")}>
              <TextInput type="number" step="0.01" value={minTemp} onChange={(e) => setMinTemp(e.target.value)} placeholder="2" />
            </Field>
            <Field label="Max storage temperature (°C)" error={fe("storage_max_temperature")}>
              <TextInput type="number" step="0.01" value={maxTemp} onChange={(e) => setMaxTemp(e.target.value)} placeholder="8" />
            </Field>
          </div>
        )}
      </div>
    </Modal>
  );
}

export function ProductsPage() {
  const { user } = useAuth();
  const admin = canCreateProduct(user?.role);
  const list = useList<Product>(["products"], ProductsApi.list, { category: "" }, "name");
  const [modal, setModal] = useState<{ product: Product | null } | null>(null);

  const columns: Column<Product>[] = [
    {
      key: "name",
      header: "Product",
      render: (p) => (
        <div className="stack" style={{ gap: 2 }}>
          <span className="cell-title">{p.name} {p.strength && <span className="muted" style={{ fontWeight: 400 }}>· {p.strength}</span>}</span>
          <span className="cell-sub">{p.generic_name || p.dosage_form || "—"}</span>
        </div>
      ),
    },
    { key: "category", header: "Category", render: (p) => <Badge value={p.category} dot={false} /> },
    { key: "form", header: "Form", render: (p) => p.dosage_form || "—" },
    { key: "unit", header: "Unit", render: (p) => p.unit_of_measure },
    {
      key: "cold",
      header: "Cold chain",
      render: (p) => {
        if (!p.requires_cold_chain) return <span className="muted">No</span>;
        const hasRange = p.storage_min_temperature != null && p.storage_max_temperature != null;
        return (
          <span className="row" style={{ gap: 5, color: "var(--blue)" }}>
            <Icon name="snowflake" size={15} />
            {hasRange ? `${p.storage_min_temperature}–${p.storage_max_temperature}°C` : "Cold chain"}
          </span>
        );
      },
    },
    { key: "active", header: "Status", render: (p) => <Badge tone={p.active ? "green" : "slate"} dot={false}>{p.active ? "Active" : "Inactive"}</Badge> },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (p) => admin ? <Button variant="ghost" size="sm" icon="edit" title="Edit" onClick={() => setModal({ product: p })} /> : null,
    },
  ];

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Network"
        title="Product catalogue"
        description="Medicines and vaccines shared across all facilities, with storage requirements."
        actions={admin && <Button icon="plus" onClick={() => setModal({ product: null })}>New product</Button>}
      />
      <Card>
        <div className="toolbar">
          <SearchBox value={list.search} onChange={list.setSearch} placeholder="Search products…" />
          <SelectInput value={list.filters.category ?? ""} onChange={(e) => list.setFilter("category", e.target.value)} style={{ width: "auto" }}>
            <option value="">All categories</option>
            <option value="MEDICINE">Medicines</option>
            <option value="VACCINE">Vaccines</option>
          </SelectInput>
        </div>
        <DataTable
          columns={columns}
          rows={list.rows}
          rowKey={(p) => p.id}
          isLoading={list.query.isLoading}
          error={list.query.error}
          onRetry={() => list.query.refetch()}
          ordering={list.ordering}
          onSort={list.setOrdering}
          empty={{ icon: "pill", title: "No products", message: "The catalogue is empty.", action: admin ? <Button icon="plus" onClick={() => setModal({ product: null })}>New product</Button> : undefined }}
          pagination={{ page: list.page, count: list.count, pageSize: list.pageSize, onPageChange: list.setPage }}
        />
      </Card>
      {modal && <ProductModal product={modal.product} onClose={() => setModal(null)} />}
    </div>
  );
}