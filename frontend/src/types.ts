export type User = {
  id: string
  name: string
  email: string
  avatar_url?: string | null
}

export type Profile = {
  rows: number
  columns: number
  duplicate_rows: number
  column_details: Array<{ name: string; dtype: string; nulls: number; null_rate: number; unique: number; sample: string[] }>
  preview: Array<Record<string, unknown>>
}

export type Dataset = { id: string; filename: string; profile: Profile }
export type DataPage = { rows: Array<Record<string, unknown>>; columns: string[]; total: number; offset: number; limit: number }
export type Message = { id: string; question: string; answer: string; method: string; created_at: string }
export type Project = { id: string; name: string; created_at: string; datasets: number | Dataset[] }
export type Chart = { type: string; xKey: string; yKey: string; data: Array<Record<string, string | number>>; title: string }
export type SummaryReport = { overview: { rows: number; columns: number; duplicate_rows: number; missing_cells: number }; schema: Array<Record<string, unknown>>; numeric_statistics: Array<Record<string, unknown>>; categorical_statistics: Array<Record<string, unknown>>; sample_rows: Array<Record<string, unknown>> }
export type AnalysisResult = { answer: string; llm_answer?: string; method: string; evidence: Array<{ label: string; value: number }>; anomalies?: Array<{ row: number; column: string; value: number; reason: string }>; chart?: Chart | null; generated_sql?: string; sql_result?: Array<Record<string, unknown>>; sql_validation?: string; report?: SummaryReport }
