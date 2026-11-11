import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AuthApi } from "@/api/endpoints";
import {
  clearTokens,
  getAccessToken,
  setTokens,
  setUnauthorizedHandler,
} from "@/api/client";
import type { RegisterPayload, UserProfile } from "@/api/types";

interface AuthContextValue {
  user: UserProfile | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<UserProfile>;
  register: (payload: RegisterPayload) => Promise<UserProfile>;
  logout: () => void;
  refreshUser: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [tokenPresent, setTokenPresent] = useState<boolean>(!!getAccessToken());

  const meQuery = useQuery({
    queryKey: ["me"],
    queryFn: AuthApi.me,
    enabled: tokenPresent,
    retry: false,
    staleTime: 5 * 60_000,
  });

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setTokenPresent(false);
      queryClient.clear();
      navigate("/login", { replace: true });
    });
    return () => setUnauthorizedHandler(null);
  }, [queryClient, navigate]);

  const login = useCallback(
    async (username: string, password: string) => {
      const tokens = await AuthApi.login(username, password);
      setTokens(tokens);
      setTokenPresent(true);
      const profile = await queryClient.fetchQuery({
        queryKey: ["me"],
        queryFn: AuthApi.me,
        staleTime: 5 * 60_000,
      });
      return profile;
    },
    [queryClient],
  );

  const register = useCallback(
    async (payload: RegisterPayload) => {
      const tokens = await AuthApi.register(payload);
      setTokens(tokens);
      setTokenPresent(true);
      const profile = await queryClient.fetchQuery({
        queryKey: ["me"],
        queryFn: AuthApi.me,
        staleTime: 5 * 60_000,
      });
      return profile;
    },
    [queryClient],
  );

  const logout = useCallback(() => {
    clearTokens();
    setTokenPresent(false);
    queryClient.clear();
    navigate("/login", { replace: true });
  }, [queryClient, navigate]);

  const refreshUser = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["me"] });
  }, [queryClient]);

  const value: AuthContextValue = {
    user: meQuery.data ?? null,
    isLoading: tokenPresent && meQuery.isLoading,
    isAuthenticated: !!meQuery.data,
    login,
    register,
    logout,
    refreshUser,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}