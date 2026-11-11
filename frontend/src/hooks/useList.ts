import { useCallback, useMemo, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import type { Paginated } from "@/api/types";
import { useDebounce } from "./useDebounce";

export type ListParams = Record<string, string | number | boolean | undefined | null>;

export function useList<T>(
  keyBase: unknown[],
  fetcher: (params: ListParams) => Promise<Paginated<T>>,
  initialFilters: Record<string, string> = {},
  initialOrdering = "",
) {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState<Record<string, string>>(initialFilters);
  const [ordering, setOrdering] = useState(initialOrdering);
  const debouncedSearch = useDebounce(search, 350);

  const setFilter = useCallback((key: string, value: string) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
    setPage(1);
  }, []);

  const changeSearch = useCallback((value: string) => {
    setSearch(value);
    setPage(1);
  }, []);

  const changeOrdering = useCallback((value: string) => {
    setOrdering(value);
    setPage(1);
  }, []);

  const params = useMemo<ListParams>(
    () => ({
      page,
      search: debouncedSearch || undefined,
      ordering: ordering || undefined,
      ...Object.fromEntries(Object.entries(filters).filter(([, v]) => v !== "")),
    }),
    [page, debouncedSearch, ordering, filters],
  );

  const query = useQuery({
    queryKey: [...keyBase, params],
    queryFn: () => fetcher(params),
    placeholderData: keepPreviousData,
  });

  const reset = useCallback(() => {
    setPage(1);
    setSearch("");
    setFilters(initialFilters);
    setOrdering(initialOrdering);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    query,
    data: query.data,
    rows: query.data?.results ?? [],
    count: query.data?.count ?? 0,
    page,
    setPage,
    search,
    setSearch: changeSearch,
    filters,
    setFilter,
    ordering,
    setOrdering: changeOrdering,
    reset,
    pageSize: 20,
  };
}