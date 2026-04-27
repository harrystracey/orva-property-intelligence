"use client";

import {
  createContext,
  useContext,
  useState,
  useEffect,
  ReactNode,
} from "react";
import {
  login as apiLogin,
  setToken,
  clearToken,
  isAuthenticated,
} from "./api";

interface AuthState {
  authenticated: boolean;
  /**
   * True until we've checked localStorage for an existing token. Pages that
   * redirect on `!authenticated` MUST gate their redirect behind `!loading`
   * -- otherwise every navigation flickers `authenticated=false` for one
   * render and bounces the user back to the landing page.
   */
  loading: boolean;
  username: string | null;
  name: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState>({
  authenticated: false,
  loading: true,
  username: null,
  name: null,
  login: async () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [authenticated, setAuthenticated] = useState(false);
  const [loading, setLoading] = useState(true);
  const [username, setUsername] = useState<string | null>(null);
  const [name, setName] = useState<string | null>(null);

  useEffect(() => {
    if (isAuthenticated()) {
      setAuthenticated(true);
      setUsername(localStorage.getItem("orva_username"));
      setName(localStorage.getItem("orva_name"));
    }
    // Whatever we found (token or no token), the check is done.
    setLoading(false);

    // Sync auth state across tabs: if a user logs out in another tab
    // (orva_token cleared), reflect it here too. Without this, a tab
    // stays authenticated for the full JWT lifetime after logout elsewhere.
    const onStorage = (e: StorageEvent) => {
      if (e.key !== "orva_token") return;
      if (e.newValue) {
        setAuthenticated(true);
        setUsername(localStorage.getItem("orva_username"));
        setName(localStorage.getItem("orva_name"));
      } else {
        setAuthenticated(false);
        setUsername(null);
        setName(null);
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const login = async (user: string, pass: string) => {
    const res = await apiLogin(user, pass);
    setToken(res.token);
    localStorage.setItem("orva_username", res.username);
    localStorage.setItem("orva_name", res.name);
    setAuthenticated(true);
    setUsername(res.username);
    setName(res.name);
  };

  const logout = () => {
    clearToken();
    localStorage.removeItem("orva_username");
    localStorage.removeItem("orva_name");
    setAuthenticated(false);
    setUsername(null);
    setName(null);
  };

  return (
    <AuthContext.Provider value={{ authenticated, loading, username, name, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
