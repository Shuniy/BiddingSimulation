export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:5000")
  .replace(/\/+$/, "");

export class ApiError extends Error {
  constructor(message: string, public readonly status?: number) {
    super(message);
    this.name = "ApiError";
  }
}

type JsonOptions = Omit<RequestInit, "body"> & { body?: unknown };
type Validator<T> = (value: unknown) => value is T;

export async function apiJson<T>(
  path: string,
  { body, ...options }: JsonOptions = {},
  validate?: Validator<T>,
): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (body !== undefined) headers.set("Content-Type", "application/json");
  const timeout = AbortSignal.timeout(10_000);
  const signal = options.signal ? AbortSignal.any([options.signal, timeout]) : timeout;
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers,
      signal,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(timeout.aborted ? "The auction backend took too long to respond."
      : "Could not connect to the auction backend.");
  }

  let result: unknown;
  try {
    result = await response.json();
  } catch {
    throw new ApiError(response.ok ? "The backend returned invalid JSON."
      : `Request failed (HTTP ${response.status}).`, response.status);
  }
  if (!response.ok) {
    const message = result && typeof result === "object" && "error" in result
      && typeof result.error === "string" ? result.error : `Request failed (HTTP ${response.status}).`;
    throw new ApiError(message, response.status);
  }
  if (result === null || typeof result !== "object" || (validate && !validate(result))) {
    throw new ApiError("The backend returned an unexpected response.", response.status);
  }
  return result as T;
}
