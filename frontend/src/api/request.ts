import axios, {AxiosError, AxiosInstance, AxiosRequestConfig} from 'axios';

interface Result<T = unknown> {
  code: number | string;
  message: string;
  data: T;
  error?: ApiErrorDetail | null;
}

export interface ApiErrorDetail {
  type: string;
  message?: string;
  retryable: boolean;
  httpStatus?: number;
  requestId?: string | null;
  runId?: string | null;
  sessionId?: string | null;
  stage?: string | null;
}

export class ApiRequestError extends Error {
  readonly code: string;
  readonly retryable: boolean;
  readonly httpStatus?: number;
  readonly requestId?: string;
  readonly runId?: string;
  readonly sessionId?: string;
  readonly stage?: string;

  constructor(message: string, detail: Partial<ApiErrorDetail> & {type: string}) {
    super(message);
    this.name = 'ApiRequestError';
    this.code = detail.type;
    this.retryable = detail.retryable ?? false;
    this.httpStatus = detail.httpStatus;
    this.requestId = detail.requestId ?? undefined;
    this.runId = detail.runId ?? undefined;
    this.sessionId = detail.sessionId ?? undefined;
    this.stage = detail.stage ?? undefined;
  }
}

const baseURL = import.meta.env.PROD ? '' : 'http://localhost:8080';
const instance: AxiosInstance = axios.create({baseURL, timeout: 60000});
const USER_STORAGE_KEY = 'interview-agent-user-id';

export function createClientId(prefix = 'anonymous'): string {
  if (typeof globalThis.crypto?.randomUUID === 'function') return globalThis.crypto.randomUUID();
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}${Math.random().toString(16).slice(2)}`;
}

function currentUserId(): string {
  const existing = localStorage.getItem(USER_STORAGE_KEY);
  if (existing?.trim()) return existing;
  const generated = createClientId();
  localStorage.setItem(USER_STORAGE_KEY, generated);
  return generated;
}

export function getUserId(): string {
  return currentUserId();
}

instance.interceptors.request.use((config) => {
  config.headers = config.headers ?? {};
  const setHeader = (name: string, value: string) => {
    if (typeof config.headers.set === 'function') config.headers.set(name, value);
    else config.headers[name] = value;
  };
  setHeader('X-User-Id', currentUserId());
  setHeader('X-Request-Id', createClientId('web'));
  return config;
});

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function stringValue(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value : undefined;
}

function parseApiError(data: unknown, fallbackStatus?: number, responseRequestId?: string): ApiRequestError | null {
  if (!isRecord(data)) return null;
  const nested = isRecord(data.error) ? data.error : undefined;
  const resultData = isRecord(data.data) ? data.data : undefined;
  const rawCode = nested?.type ?? data.code;
  if (rawCode === undefined) return null;
  const message = stringValue(nested?.message) ?? stringValue(resultData?.message)
    ?? stringValue(data.message) ?? '请求处理失败';
  const type = stringValue(rawCode) ?? String(rawCode);
  return new ApiRequestError(message, {
    type,
    retryable: typeof nested?.retryable === 'boolean' ? nested.retryable : (fallbackStatus ?? 0) >= 500,
    httpStatus: typeof nested?.httpStatus === 'number' ? nested.httpStatus : fallbackStatus,
    requestId: stringValue(nested?.requestId) ?? responseRequestId,
    runId: stringValue(nested?.runId),
    sessionId: stringValue(nested?.sessionId),
    stage: stringValue(nested?.stage),
  });
}

async function decodeErrorData(data: unknown): Promise<unknown> {
  if (!(data instanceof Blob) || !data.type.includes('json')) return data;
  try {
    return JSON.parse(await data.text()) as unknown;
  } catch {
    return data;
  }
}

function transportError(error: AxiosError): ApiRequestError {
  const isUpload = error.config?.url?.includes('/upload')
    || String(error.config?.headers?.['Content-Type'] ?? '').includes('multipart');
  if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT') {
    return new ApiRequestError(isUpload ? '上传超时，请检查网络后重试' : '请求超时，服务可能仍在处理中', {
      type: 'NETWORK_TIMEOUT', retryable: true, stage: 'NETWORK',
    });
  }
  return new ApiRequestError(isUpload ? '上传连接中断，请检查网络后重试' : '无法连接服务器，请检查网络或服务状态', {
    type: 'NETWORK_UNAVAILABLE', retryable: true, stage: 'NETWORK',
  });
}

instance.interceptors.response.use(
  (response) => {
    const result = response.data as Result;
    if (isRecord(result) && 'code' in result) {
      if (result.code === 100 || result.code === 101 || result.code === 200
        || result.code === '100' || result.code === '101' || result.code === '200') {
        response.data = result.data;
        return response;
      }
      return Promise.reject(parseApiError(result, response.status, response.headers['x-request-id'])
        ?? new ApiRequestError('请求处理失败', {type: String(result.code), retryable: false}));
    }
    return response;
  },
  async (unknownError: unknown) => {
    if (!axios.isAxiosError(unknownError)) return Promise.reject(unknownError);
    if (!unknownError.response) return Promise.reject(transportError(unknownError));
    const response = unknownError.response;
    const responseData = await decodeErrorData(response.data);
    const parsed = parseApiError(responseData, response.status, response.headers['x-request-id']);
    if (parsed) return Promise.reject(parsed);

    const message = response.status >= 500
      ? '服务器暂时无法处理请求，请稍后重试'
      : `请求被服务器拒绝（HTTP ${response.status}）`;
    return Promise.reject(new ApiRequestError(message, {
      type: response.status >= 500 ? 'SERVER_RESPONSE_INVALID' : 'HTTP_REQUEST_FAILED',
      retryable: response.status >= 500,
      httpStatus: response.status,
      requestId: response.headers['x-request-id'],
      stage: 'HTTP',
    }));
  },
);

export const request = {
  get<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return instance.get(url, config).then(response => response.data);
  },
  post<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return instance.post(url, data, config).then(response => response.data);
  },
  put<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return instance.put(url, data, config).then(response => response.data);
  },
  patch<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return instance.patch(url, data, config).then(response => response.data);
  },
  delete<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return instance.delete(url, config).then(response => response.data);
  },
  upload<T>(url: string, formData: FormData, config?: AxiosRequestConfig): Promise<T> {
    return instance.post(url, formData, {
      timeout: 300000,
      headers: {'Content-Type': 'multipart/form-data'},
      ...config,
    }).then(response => response.data);
  },
  getInstance(): AxiosInstance {
    return instance;
  },
};

export function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : '发生未知错误';
}

/** Human-readable text which keeps diagnostics safe to show in the UI. */
export function getErrorDisplayMessage(error: unknown, prefix?: string): string {
  const message = getErrorMessage(error);
  if (!(error instanceof ApiRequestError)) return prefix ? `${prefix}：${message}` : message;
  const details = [
    `错误码：${error.code}`,
    error.stage ? `阶段：${error.stage}` : null,
    error.retryable ? '可以重试' : '请检查输入或配置后再试',
    error.requestId ? `请求编号：${error.requestId}` : null,
  ].filter(Boolean).join('；');
  return `${prefix ? `${prefix}：` : ''}${message}（${details}）`;
}

export default request;
