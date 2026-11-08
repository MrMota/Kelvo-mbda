import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "./api";
import type { ComponentSpec, Registry, Skill } from "./types";

type Model = { name: string; parameter_size?: string; family?: string; capabilities?: string[] | null };
type Store = {
  registry: Registry | null;
  spec: (key: string) => ComponentSpec | undefined;
  models: Model[];
  modelsError: string | null;
  refreshModels: () => Promise<void>;
  skills: Skill[];
  refreshSkills: () => Promise<void>;
  settings: { ollama_base_url: string; default_model: string; default_embed_model: string; has_ollama_api_key?: boolean };
  refreshSettings: () => Promise<void>;
};
const Ctx = createContext<Store>(null as unknown as Store);
export const useStore = () => useContext(Ctx);

export function StoreProvider({ children }: { children: ReactNode }) {
  const [registry, setRegistry] = useState<Registry | null>(null);
  const [models, setModels] = useState<Model[]>([]);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [settings, setSettings] = useState({ ollama_base_url: "", default_model: "", default_embed_model: "" });

  const refreshModels = useCallback(async () => {
    try {
      const r = await api<{ models: Model[] }>("/api/ollama/models");
      setModels(r.models);
      setModelsError(null);
    } catch (e: any) {
      setModels([]);
      setModelsError(e.message);
    }
  }, []);
  const refreshSkills = useCallback(async () => setSkills(await api<Skill[]>("/api/skills")), []);
  const refreshSettings = useCallback(async () => setSettings(await api("/api/settings")), []);

  useEffect(() => {
    api<Registry>("/api/components").then(setRegistry);
    refreshModels();
    refreshSkills();
    refreshSettings();
  }, [refreshModels, refreshSkills, refreshSettings]);

  const spec = useCallback((key: string) => registry?.components.find((c) => c.key === key), [registry]);
  return (
    <Ctx.Provider value={{ registry, spec, models, modelsError, refreshModels, skills, refreshSkills, settings, refreshSettings }}>
      {children}
    </Ctx.Provider>
  );
}
