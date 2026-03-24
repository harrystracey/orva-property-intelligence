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
  username: string | null;
  name: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState>({
  authenticated: false,
  username: null,
  name: null,
  login: async () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [authenticated, setAuthenticated] = useState(false);
  const [username, setUsername] = useState<string | null>(null);
  const [name, setName] = useState<string | null>(null);

  useEffect(() => {
    if (isAuthenticated()) {
      setAuthenticated(true);
      setUsername(localStorage.getItem("orva_username"));
      setName(localStorage.getItem("orva_name"));
    }
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
    <AuthContext.Provider value={{ authenticated, username, name, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
