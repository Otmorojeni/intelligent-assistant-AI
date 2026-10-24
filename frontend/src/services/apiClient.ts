import {
  ApprovalCalculateRequest,
  ApprovalCalculateResponse,
  ApprovalRuleItem,
  AuditLogItem,
  ComplianceCheckResponse,
  DocumentGenerateRequest,
  DocumentGenerateResponse,
  DocumentVersionItem,
  HealthResponse,
  ProjectCardItem,
  QueryRequest,
  QueryResponse,
  TemplateModuleInfo,
  TokenRequest,
  TokenResponse,
  UserRole,
} from "../types/api";

const API_BASE = "";

function authHeaders(token?: string | null, isJson = true): HeadersInit {
  const headers: Record<string, string> = {};
  if (isJson) {
    headers["Content-Type"] = "application/json";
  }
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  return headers;
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let errorMessage = `HTTP ${res.status}`;
    try {
      const data = await res.json();
      errorMessage = data.detail || JSON.stringify(data);
    } catch {
      const txt = await res.text();
      if (txt) errorMessage = txt;
    }
    const err = new Error(errorMessage) as Error & { status?: number };
    err.status = res.status;
    throw err;
  }
  return res.json();
}

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE}/v1/health`);
  return handleResponse<HealthResponse>(res);
}

export async function issueRoleToken(
  role: UserRole,
  username = "Демо Пользователь",
  password?: string
): Promise<TokenResponse> {
  const payload: TokenRequest = {
    username: `${username} (${role})`,
    role,
    ...(role === "admin" ? { password: password || "cdo-admin-2026" } : {}),
  };
  const res = await fetch(`${API_BASE}/v1/auth/token`, {
    method: "POST",
    headers: authHeaders(null, true),
    body: JSON.stringify(payload),
  });
  return handleResponse<TokenResponse>(res);
}

export async function sendAssistantQuery(
  request: QueryRequest,
  token?: string | null
): Promise<QueryResponse> {
  const res = await fetch(`${API_BASE}/v1/assistant/query`, {
    method: "POST",
    headers: authHeaders(token, true),
    body: JSON.stringify(request),
  });
  return handleResponse<QueryResponse>(res);
}

export async function streamAssistantQuery(
  request: QueryRequest,
  token: string | null | undefined,
  callbacks: {
    onMetadata: (meta: Partial<QueryResponse>) => void;
    onToken: (chunk: string) => void;
    onDone: (finalInfo: { latency_ms: number; zero_hallucination_triggered?: boolean }) => void;
  }
): Promise<void> {
  const res = await fetch(`${API_BASE}/v1/assistant/query/stream`, {
    method: "POST",
    headers: authHeaders(token, true),
    body: JSON.stringify(request),
  });

  if (!res.ok || !res.body) {
    await handleResponse(res);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() || "";

    for (const block of blocks) {
      const lines = block.split("\n");
      let eventType = "";
      let dataStr = "";
      for (const line of lines) {
        if (line.startsWith("event:")) eventType = line.slice(6).trim();
        if (line.startsWith("data:")) dataStr += line.slice(5).trim();
      }
      if (!dataStr) continue;
      try {
        const parsed = JSON.parse(dataStr);
        const type = eventType || parsed.type;
        if (type === "metadata") {
          callbacks.onMetadata(parsed);
        } else if (type === "token") {
          callbacks.onToken(parsed.content ?? parsed.text ?? "");
        } else if (type === "done") {
          callbacks.onDone(parsed);
        }
      } catch {
        // ignore malformed chunk
      }
    }
  }
}

export async function fetchTemplates(token?: string | null): Promise<TemplateModuleInfo[]> {
  const res = await fetch(`${API_BASE}/v1/documents/templates`, {
    headers: authHeaders(token, false),
  });
  return handleResponse<TemplateModuleInfo[]>(res);
}

export async function fetchTemplateByCode(
  moduleCode: string,
  token?: string | null
): Promise<TemplateModuleInfo> {
  const res = await fetch(`${API_BASE}/v1/documents/templates/${encodeURIComponent(moduleCode)}`, {
    headers: authHeaders(token, false),
  });
  return handleResponse<TemplateModuleInfo>(res);
}

export async function generateModularDocument(
  request: DocumentGenerateRequest,
  token?: string | null
): Promise<DocumentGenerateResponse> {
  const res = await fetch(`${API_BASE}/v1/documents/generate`, {
    method: "POST",
    headers: authHeaders(token, true),
    body: JSON.stringify(request),
  });
  return handleResponse<DocumentGenerateResponse>(res);
}

export async function fetchProjectCards(token?: string | null): Promise<ProjectCardItem[]> {
  const res = await fetch(`${API_BASE}/v1/documents/projects`, {
    headers: authHeaders(token, false),
  });
  return handleResponse<ProjectCardItem[]>(res);
}

export async function downloadGeneratedDocx(
  fileName: string,
  token?: string | null
): Promise<void> {
  const cleanName = fileName.replace(/^.*\/download\//, "");
  const res = await fetch(`${API_BASE}/v1/documents/download/${encodeURIComponent(cleanName)}`, {
    headers: authHeaders(token, false),
  });
  if (!res.ok) {
    await handleResponse(res);
  }
  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = cleanName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

export async function checkDocxCompliance(
  file: File,
  token?: string | null
): Promise<ComplianceCheckResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_BASE}/v1/documents/check-compliance`, {
    method: "POST",
    headers: authHeaders(token, false),
    body: formData,
  });
  return handleResponse<ComplianceCheckResponse>(res);
}

export async function fetchApprovalRules(token?: string | null): Promise<ApprovalRuleItem[]> {
  const res = await fetch(`${API_BASE}/v1/approval/rules`, {
    headers: authHeaders(token, false),
  });
  return handleResponse<ApprovalRuleItem[]>(res);
}

export async function calculateApprovalRoute(
  request: ApprovalCalculateRequest,
  token?: string | null
): Promise<ApprovalCalculateResponse> {
  const res = await fetch(`${API_BASE}/v1/approval/calculate`, {
    method: "POST",
    headers: authHeaders(token, true),
    body: JSON.stringify(request),
  });
  return handleResponse<ApprovalCalculateResponse>(res);
}

export async function fetchDocumentVersions(token?: string | null): Promise<DocumentVersionItem[]> {
  const res = await fetch(`${API_BASE}/v1/documents/versions`, {
    headers: authHeaders(token, false),
  });
  return handleResponse<DocumentVersionItem[]>(res);
}

export async function uploadDocumentVersion(
  formPayload: {
    file: File;
    doc_code: string;
    title: string;
    version: string;
    doc_type: string;
    access_level: string;
  },
  token?: string | null
): Promise<DocumentVersionItem> {
  const formData = new FormData();
  formData.append("file", formPayload.file);
  formData.append("doc_code", formPayload.doc_code);
  formData.append("title", formPayload.title);
  formData.append("version", formPayload.version);
  formData.append("doc_type", formPayload.doc_type);
  formData.append("access_level", formPayload.access_level);

  const res = await fetch(`${API_BASE}/v1/documents/upload-version`, {
    method: "POST",
    headers: authHeaders(token, false),
    body: formData,
  });
  return handleResponse<DocumentVersionItem>(res);
}

export async function activateDocumentVersion(
  docCode: string,
  version: string,
  token?: string | null
): Promise<DocumentVersionItem> {
  const res = await fetch(
    `${API_BASE}/v1/documents/${encodeURIComponent(docCode)}/activate-version/${encodeURIComponent(version)}`,
    {
      method: "POST",
      headers: authHeaders(token, false),
    }
  );
  return handleResponse<DocumentVersionItem>(res);
}


export async function deleteDocumentVersion(
  docCode: string,
  version?: string,
  token?: string | null
): Promise<{ deleted_doc_code: string; deleted_versions: string[]; deleted_count: number }> {
  const url = version
    ? `${API_BASE}/v1/documents/${encodeURIComponent(docCode)}/versions/${encodeURIComponent(version)}`
    : `${API_BASE}/v1/documents/${encodeURIComponent(docCode)}`;
  const res = await fetch(url, {
    method: "DELETE",
    headers: authHeaders(token, false),
  });
  return handleResponse<{ deleted_doc_code: string; deleted_versions: string[]; deleted_count: number }>(res);
}

export async function fetchAuditLogs(
  params: {
    action_type?: string;
    user_role?: string;
    status_filter?: string;
    limit?: number;
  },
  token?: string | null
): Promise<AuditLogItem[]> {
  const qs = new URLSearchParams();
  if (params.action_type) qs.set("action_type", params.action_type);
  if (params.user_role) qs.set("user_role", params.user_role);
  if (params.status_filter) qs.set("status_filter", params.status_filter);
  if (params.limit) qs.set("limit", String(params.limit));

  const res = await fetch(`${API_BASE}/v1/audit/logs?${qs.toString()}`, {
    headers: authHeaders(token, false),
  });
  return handleResponse<AuditLogItem[]>(res);
}
