import type { ReactNode } from "react";
import { Icon, type IconName } from "./Icon";
import { Button } from "./Button";
import { EmptyState, ErrorState, TableSkeleton } from "./States";

export interface Column<T> {
  key: string;
  header: ReactNode;
  render: (row: T) => ReactNode;
  align?: "left" | "right";
  sortField?: string;
  width?: string;
}

export function Pagination({
  page,
  count,
  pageSize,
  onPageChange,
}: {
  page: number;
  count: number;
  pageSize: number;
  onPageChange: (p: number) => void;
}) {
  const totalPages = Math.max(1, Math.ceil(count / pageSize));
  if (count === 0) return null;
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, count);
  return (
    <div className="pagination">
      <span className="info">
        Showing <strong>{from}–{to}</strong> of <strong>{count}</strong>
      </span>
      <div className="controls">
        <Button
          variant="secondary"
          size="sm"
          icon="chevron-left"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          Prev
        </Button>
        <span className="muted" style={{ fontSize: 12.5, padding: "0 6px" }}>
          Page {page} / {totalPages}
        </span>
        <Button
          variant="secondary"
          size="sm"
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
        >
          Next
          <Icon name="chevron-right" size={15} />
        </Button>
      </div>
    </div>
  );
}

export function SearchBox({
  value,
  onChange,
  placeholder = "Search…",
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <div className="search-box">
      <Icon name="search" size={17} />
      <input
        className="input"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        type="search"
      />
    </div>
  );
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string | number;
  isLoading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  onRowClick?: (row: T) => void;
  ordering?: string;
  onSort?: (field: string) => void;
  empty?: { icon?: IconName; title: string; message?: string; action?: ReactNode };
  pagination?: { page: number; count: number; pageSize: number; onPageChange: (p: number) => void };
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  isLoading,
  error,
  onRetry,
  onRowClick,
  ordering,
  onSort,
  empty,
  pagination,
}: DataTableProps<T>) {
  if (isLoading) return <TableSkeleton cols={columns.length} />;
  if (error) return <ErrorState error={error} onRetry={onRetry} />;
  if (rows.length === 0)
    return (
      <EmptyState
        icon={empty?.icon ?? "inbox"}
        title={empty?.title ?? "Nothing here yet"}
        message={empty?.message}
        action={empty?.action}
      />
    );

  return (
    <>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              {columns.map((col) => {
                const sortable = !!col.sortField && !!onSort;
                const isSorted = ordering === col.sortField || ordering === `-${col.sortField}`;
                const desc = ordering === `-${col.sortField}`;
                return (
                  <th
                    key={col.key}
                    className={`${sortable ? "sortable" : ""} ${col.align === "right" ? "num" : ""}`}
                    style={col.width ? { width: col.width } : undefined}
                    onClick={sortable ? () => onSort!(desc ? col.sortField! : `-${col.sortField}`) : undefined}
                  >
                    <span className="row" style={{ gap: 5, justifyContent: col.align === "right" ? "flex-end" : "flex-start" }}>
                      {col.header}
                      {sortable && (
                        <Icon
                          name={isSorted ? (desc ? "chevron-down" : "chevron-down") : "chevron-down"}
                          size={13}
                          style={{
                            opacity: isSorted ? 1 : 0.3,
                            transform: isSorted && !desc ? "rotate(180deg)" : undefined,
                            color: isSorted ? "var(--brand)" : undefined,
                          }}
                        />
                      )}
                    </span>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={rowKey(row)}
                className={onRowClick ? "clickable" : ""}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
              >
                {columns.map((col) => (
                  <td key={col.key} className={col.align === "right" ? "num" : ""}>
                    {col.render(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pagination && <Pagination {...pagination} />}
    </>
  );
}