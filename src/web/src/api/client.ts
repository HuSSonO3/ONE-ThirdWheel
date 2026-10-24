// Typed REST client. Paths and bodies come from schema.ts, which is generated from
// contracts/openapi.yaml by scripts/gen_client.sh; do not hand-write fetch calls.
import createClient from "openapi-fetch";
import type { components, paths } from "./schema";

export const api = createClient<paths>({
  baseUrl: import.meta.env.VITE_API_URL ?? "",
  credentials: "include",
});

export type Schemas = components["schemas"];
