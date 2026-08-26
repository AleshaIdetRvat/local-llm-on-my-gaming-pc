/**
 * Список локальных моделей берём прямо у llama-swap (GET /v1/models), а не держим
 * руками в models.json: добавил модель в config.yaml на стенде — она сама появилась в /model.
 *
 * Из ответа сервера используем: id, name, description, context_length (или meta.n_ctx),
 * architecture.input_modalities. Всё это llama-swap отдаёт из своего config.yaml
 * (поля name/description + блок capabilities:), т.е. стенд — единственный источник правды.
 *
 * В ~/.pi/agent/models.json остаётся только подключение (baseUrl, apiKey, compat)
 * и точечные правки через modelOverrides — они применяются поверх этого списка.
 *
 * Стенд недоступен (спит/выключен) — берём последний удачный список из кэша,
 * а если и его нет, молча ничего не регистрируем.
 */
import { readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const PROVIDER = "rig"; // имя провайдера как в ~/.pi/agent/models.json
const AGENT_DIR = join(homedir(), ".pi", "agent");
const MODELS_JSON = join(AGENT_DIR, "models.json");
const CACHE = join(AGENT_DIR, `${PROVIDER}-models.cache.json`);
const TIMEOUT_MS = 2500;
const FALLBACK_CONTEXT = 32768; // если на стенде у модели не прописан capabilities.context
const MAX_OUTPUT = 16384;

interface SwapModel {
  id: string;
  name?: string;
  description?: string;
  context_length?: number;
  meta?: { n_ctx?: number };
  architecture?: { input_modalities?: string[] };
}

export default async function (pi: ExtensionAPI) {
  const provider = JSON.parse(readFileSync(MODELS_JSON, "utf8")).providers?.[PROVIDER] ?? {};
  const baseUrl: string | undefined = process.env.GAMINGPC_BASE_URL ?? provider.baseUrl;
  if (!baseUrl) return;

  const models = (await fetchModels(baseUrl)) ?? readCache();
  if (!models?.length) return;

  pi.registerProvider(PROVIDER, {
    baseUrl,
    api: provider.api ?? "openai-completions",
    models: models.map((model) => {
      const contextWindow = model.context_length || model.meta?.n_ctx || FALLBACK_CONTEXT;
      const modalities = model.architecture?.input_modalities;
      return {
        id: model.id,
        name: model.name?.trim() || model.id,
        reasoning: false,
        input: modalities?.includes("image") ? ["text", "image"] : ["text"],
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
        contextWindow,
        maxTokens: Math.min(contextWindow, MAX_OUTPUT),
        compat: provider.compat,
      };
    }),
  });
}

async function fetchModels(baseUrl: string): Promise<SwapModel[] | undefined> {
  try {
    const response = await fetch(`${baseUrl.replace(/\/$/, "")}/models`, {
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    if (!response.ok) return undefined;
    const models = ((await response.json()) as { data?: SwapModel[] }).data;
    if (!models?.length) return undefined;
    writeFileSync(CACHE, JSON.stringify(models, null, 2));
    return models;
  } catch {
    return undefined; // стенд не отвечает — не роняем запуск pi
  }
}

function readCache(): SwapModel[] | undefined {
  try {
    return JSON.parse(readFileSync(CACHE, "utf8")) as SwapModel[];
  } catch {
    return undefined;
  }
}
