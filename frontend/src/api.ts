import type { AnalysisResult, DataPage, Message, Project, User } from './types'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { credentials: 'include', ...init })
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(error.detail ?? 'Request failed')
  }
  return response.json()
}

export const api = {
  me: () => request<{ authenticated: boolean; user: User | null }>('/auth/me'),
  login: () => { window.location.href = `${API_URL}/auth/login` },
  logout: () => request<{ ok: boolean }>('/auth/logout', { method: 'POST' }),
  projects: () => request<Project[]>('/projects'),
  createProject: (name: string) => request<Project>('/projects', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) }),
  project: (id: string) => request<Project & { datasets: import('./types').Dataset[] }>(`/projects/${id}`),
  upload: (id: string, files: File[]) => { const data = new FormData(); files.forEach((file) => data.append('files', file)); return request<{ uploaded: Array<{ filename: string }>; failed: Array<{ filename: string; error: string }> }>(`/projects/${id}/datasets`, { method: 'POST', body: data }) },
  ask: (projectId: string, datasetId: string, question: string, datasetIds?: string[]) => request<AnalysisResult>(`/projects/${projectId}/datasets/${datasetId}/ask`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question, dataset_ids: datasetIds }) }),
  rows: (projectId: string, datasetId: string, offset = 0, limit = 50) => request<DataPage>(`/projects/${projectId}/datasets/${datasetId}/rows?offset=${offset}&limit=${limit}`),
  messages: (projectId: string) => request<Message[]>(`/projects/${projectId}/messages`),
}
