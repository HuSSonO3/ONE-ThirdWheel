import { api } from '../api/client'

export class ApiError extends Error {
  status: number
  code: string
  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

let onUnauthenticated: () => void = () => {}
export const setUnauthenticatedHandler = (fn: () => void) => { onUnauthenticated = fn }

api.use({
  onResponse({ response, schemaPath }) {
    if (response.status === 401 && !schemaPath.startsWith('/auth/')) onUnauthenticated()
    return undefined
  },
})

type Result<T> = { data?: T; error?: unknown; response: Response }

/** Unwraps an openapi-fetch result, turning the API's `{code, message}` error body into an ApiError. */
export async function call<T>(request: Promise<Result<T>>): Promise<T> {
  const { data, error, response } = await request
  if (!response.ok) {
    const e = (error ?? {}) as { code?: string; message?: string }
    throw new ApiError(response.status, e.code ?? 'error', e.message ?? `Request failed (${response.status})`)
  }
  return data as T
}

export { api }
