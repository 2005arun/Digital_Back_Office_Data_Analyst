import { useEffect, useRef, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from 'recharts'
import { BarChart3, CheckCircle2, ChevronRight, FileChartColumn, Files, LogIn, LogOut, Plus, Send, Sparkles, UploadCloud, X } from 'lucide-react'
import { api } from './api'
import type { AnalysisResult, Chart, Dataset, DataPage, Message, Project, User } from './types'
import './App.css'

function App() {
  const [user, setUser] = useState<User | null>(null)
  const [projects, setProjects] = useState<Project[]>([])
  const [activeProject, setActiveProject] = useState<(Project & { datasets: Dataset[] }) | null>(null)
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<AnalysisResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [showNewProject, setShowNewProject] = useState(false)
  const [newProjectName, setNewProjectName] = useState('')
  const fileInput = useRef<HTMLInputElement>(null)

  useEffect(() => {
    api.me().then((result) => {
      if (result.authenticated && result.user) {
        setUser(result.user)
        return api.projects()
      }
      return []
    }).then(setProjects).catch((reason: Error) => setError(reason.message)).finally(() => setLoading(false))
  }, [])

  const openProject = async (project: Project) => {
    setError('')
    try { setActiveProject(await api.project(project.id)) } catch (reason) { setError((reason as Error).message) }
  }

  const createProject = async () => {
    if (!newProjectName.trim()) return
    setBusy(true)
    try {
      const project = await api.createProject(newProjectName.trim())
      setProjects((current) => [project, ...current])
      setNewProjectName('')
      setShowNewProject(false)
      await openProject(project)
    } catch (reason) { setError((reason as Error).message) } finally { setBusy(false) }
  }

  const uploadFiles = async (files: File[] | null) => {
    if (!files?.length || !activeProject) return
    setBusy(true)
    setError('')
    try {
      const result = await api.upload(activeProject.id, files)
      setActiveProject(await api.project(activeProject.id))
      if (result.failed.length > 0) {
        const summary = result.failed.slice(0, 2).map((item) => `${item.filename}: ${item.error}`).join('; ')
        setError(`Uploaded ${result.uploaded.length} file(s). Failed ${result.failed.length} file(s): ${summary}`)
      }
    } catch (reason) { setError((reason as Error).message) } finally { setBusy(false) }
  }

  const handleFileSelection = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.currentTarget.files ? Array.from(event.currentTarget.files) : []
    event.currentTarget.value = ''
    void uploadFiles(files)
  }

  const ask = async (value = question, datasetIds?: string[]) => {
    const dataset = activeProject?.datasets[0]
    if (!dataset || !value.trim()) return
    setBusy(true)
    setError('')
    setQuestion(value)
    setAnswer(null)
    try { setAnswer(await api.ask(activeProject.id, dataset.id, value, datasetIds)) }
    catch (reason) { setError((reason as Error).message) } finally { setBusy(false) }
  }

  if (loading) return <div className="loading-screen"><Sparkles size={22} /> Preparing your workspace...</div>
  if (!user) return <main className="auth-screen">
    <div className="auth-mark"><BarChart3 size={22} /></div>
    <p className="eyebrow">NORTHSTAR / DATA INTELLIGENCE</p>
    <h1>Ask better questions<br /><em>of your business.</em></h1>
    <p className="auth-copy">Turn raw CSVs into clear decisions with an analyst that can see the signal, show its work, and stay with the conversation.</p>
    <button className="primary-button login-button" onClick={api.login}><LogIn size={18} /> Continue with Google</button>
    <p className="fine-print">Your files stay in your private workspace.</p>
    {error && <p className="error-message">{error}</p>}
  </main>

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-icon"><BarChart3 size={16} /></span><span>northstar</span></div>
      <div className="sidebar-label">WORKSPACES</div>
      <div className="project-list">
        {projects.map((project) => <button className={`project-item ${activeProject?.id === project.id ? 'selected' : ''}`} key={project.id} onClick={() => openProject(project)}><span className="project-dot" />{project.name}<ChevronRight size={14} /></button>)}
        {projects.length === 0 && <p className="sidebar-empty">Create your first workspace.</p>}
      </div>
      {showNewProject ? <div className="new-project"><input autoFocus value={newProjectName} onChange={(event) => setNewProjectName(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && createProject()} placeholder="Workspace name" /><button onClick={createProject} disabled={busy}>Add</button></div> : <button className="new-project-button" onClick={() => setShowNewProject(true)}><Plus size={15} /> New workspace</button>}
      <div className="sidebar-bottom"><div className="profile"><div className="avatar">{user.name.slice(0, 1)}</div><div><strong>{user.name}</strong><span>{user.email}</span></div></div><button className="icon-button" title="Sign out" onClick={() => api.logout().then(() => setUser(null))}><LogOut size={16} /></button></div>
    </aside>
    <main className="main-content">
      <header className="topbar"><div><p className="eyebrow">{activeProject ? `WORKSPACE / ${activeProject.name.toUpperCase()}` : 'YOUR ANALYTICS DESK'}</p><h2>{activeProject ? 'Make sense of your data.' : 'Good analysis starts here.'}</h2></div><div className="status-chip"><span /> Private workspace</div></header>
      {!activeProject ? <Welcome onCreate={() => setShowNewProject(true)} /> : <Workspace project={activeProject} busy={busy} error={error} question={question} answer={answer} fileInput={fileInput} onFileSelection={handleFileSelection} onAsk={ask} onQuestionChange={setQuestion} />}
    </main>
  </div>
}

function Welcome({ onCreate }: { onCreate: () => void }) {
  return <section className="welcome"><div className="welcome-copy"><div className="sparkle-badge"><Sparkles size={18} /></div><h1>Your data has<br /><em>something to say.</em></h1><p>Create a workspace, upload your CSVs, and ask questions in plain English. Northstar will turn the raw rows into a clear point of view.</p><button className="primary-button" onClick={onCreate}><Plus size={17} /> Create workspace</button></div><div className="signal-card"><div className="signal-card-header"><span>LIVE SIGNAL</span><span className="pulse-dot" /></div><div className="signal-bars"><i /><i /><i /><i /><i /><i /><i /><i /><i /></div><div className="signal-caption"><strong>From rows to reasons</strong><span>Upload a dataset to begin</span></div></div></section>
}

type WorkspaceProps = { project: Project & { datasets: Dataset[] }; busy: boolean; error: string; question: string; answer: AnalysisResult | null; fileInput: React.RefObject<HTMLInputElement | null>; onFileSelection: (event: React.ChangeEvent<HTMLInputElement>) => void; onAsk: (question?: string, datasetIds?: string[]) => void; onQuestionChange: (value: string) => void }

function Workspace({ project, busy, error, question, answer, fileInput, onFileSelection, onAsk, onQuestionChange }: WorkspaceProps) {
  const dataset = project.datasets[0]
  const [showTable, setShowTable] = useState(false)
  const [history, setHistory] = useState<Message[]>([])
  const [analyzeAll, setAnalyzeAll] = useState(project.datasets.length > 1)
  const prompts = ['Which region generated the highest revenue?', 'Show me the main trends in this data.', 'Detect anomalies in this dataset.']

  useEffect(() => {
    api.messages(project.id).then(setHistory).catch(() => setHistory([]))
  }, [project.id, answer])

  if (!dataset) return <section className="workspace"><div className="upload-state"><div className="upload-icon"><UploadCloud size={26} /></div><h1>Bring your data into focus.</h1><p>Start with one or more CSV files. We’ll map the shape of your data before you ask the first question.</p><button className="upload-zone" onClick={() => fileInput.current?.click()}><Files size={19} /><span><strong>Choose CSV files</strong><small>or drag and drop them here</small></span><ChevronRight size={17} /></button><input ref={fileInput} type="file" accept=".csv,text/csv" multiple hidden onChange={onFileSelection} />{busy && <p className="muted">Profiling your files...</p>}</div></section>

  return <section className="workspace">
    <div className="dataset-strip">
      <button className={`dataset-name dataset-trigger ${showTable ? 'active' : ''}`} onClick={() => setShowTable((current) => !current)} title="Open dataset table">
        <span className="file-icon"><FileChartColumn size={17} /></span><span><strong>{dataset.filename}</strong><small>{dataset.profile.rows.toLocaleString()} rows / {dataset.profile.columns} columns</small></span><ChevronRight size={15} className="dataset-chevron" />
      </button>
      {project.datasets.length > 1 && <button className={`scope-button ${analyzeAll ? 'selected' : ''}`} onClick={() => setAnalyzeAll((current) => !current)}><Files size={14} /> {analyzeAll ? 'All files' : 'One file'}</button>}
      <button className="text-button" onClick={() => fileInput.current?.click()}><UploadCloud size={15} /> Add another</button>
      <input ref={fileInput} type="file" accept=".csv,text/csv" multiple hidden onChange={onFileSelection} />
    </div>
    {showTable && <DataTable projectId={project.id} datasetId={dataset.id} profile={dataset.profile} onClose={() => setShowTable(false)} />}
    <div className="analysis-grid"><div className="question-panel"><div className="panel-kicker"><Sparkles size={15} /> ASK NORTHSTAR</div><h1>What would you like<br />to understand?</h1>{history.length > 0 && <div className="conversation-list">{history.slice(-3).map((message) => <div className="conversation-item" key={message.id}><strong>{message.question}</strong><span>{message.answer}</span></div>)}</div>}<div className="prompt-list">{prompts.map((prompt) => <button key={prompt} onClick={() => onAsk(prompt, analyzeAll ? project.datasets.map((item) => item.id) : undefined)}>{prompt}<ChevronRight size={14} /></button>)}</div><div className="question-box"><textarea value={question} onChange={(event) => onQuestionChange(event.target.value)} placeholder="Ask anything about your data..." rows={3} /><button title="Ask question" disabled={busy || !question.trim()} onClick={() => onAsk(undefined, analyzeAll ? project.datasets.map((item) => item.id) : undefined)}><Send size={17} /></button></div>{error && <p className="error-message">{error}</p>}</div><div className="right-column"><div className="profile-panel"><div className="panel-heading"><span>DATA PULSE</span><CheckCircle2 size={16} /></div><div className="metric-row"><div><strong>{dataset.profile.rows.toLocaleString()}</strong><span>rows</span></div><div><strong>{dataset.profile.columns}</strong><span>columns</span></div><div><strong>{dataset.profile.duplicate_rows}</strong><span>duplicates</span></div></div><div className="column-list">{dataset.profile.column_details.slice(0, 5).map((column) => <div key={column.name}><span>{column.name}</span><small>{column.dtype} / {column.nulls} nulls</small></div>)}</div></div>{answer ? <ResultCard answer={answer} /> : <div className="empty-result"><BarChart3 size={20} /><span>Your answer will appear here.</span><small>Evidence, charts, and the method behind the result.</small></div>}</div></div>
  </section>
}

function DataTable({ projectId, datasetId, profile, onClose }: { projectId: string; datasetId: string; profile: Dataset['profile']; onClose: () => void }) {
  const [page, setPage] = useState<DataPage>({ rows: profile.preview, columns: profile.column_details.map((column) => column.name), total: profile.rows, offset: 0, limit: 50 })
  const [loading, setLoading] = useState(true)
  const pageSize = 50
  useEffect(() => { setLoading(true); api.rows(projectId, datasetId, page.offset, pageSize).then(setPage).finally(() => setLoading(false)) }, [projectId, datasetId, page.offset])
  const canPrevious = page.offset > 0
  const canNext = page.offset + page.rows.length < page.total
  return <section className="data-table-panel"><div className="data-table-heading"><div><span className="panel-kicker"><FileChartColumn size={14} /> DATASET VIEW</span><strong>Spreadsheet view</strong><small>Rows {page.total === 0 ? 0 : page.offset + 1}-{Math.min(page.offset + page.rows.length, page.total)} of {page.total.toLocaleString()}</small></div><button className="icon-button" title="Close dataset view" onClick={onClose}><X size={17} /></button></div><div className="table-scroll">{loading ? <p className="table-status">Loading rows...</p> : <table><thead><tr><th className="row-number">#</th>{page.columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{page.rows.map((row, index) => <tr key={index}><td className="row-number">{page.offset + index + 1}</td>{page.columns.map((column) => <td key={column}>{formatCell(row[column])}</td>)}</tr>)}</tbody></table>}</div><div className="table-footer"><span>50 rows per page</span><div><button disabled={!canPrevious || loading} onClick={() => setPage((current) => ({ ...current, offset: Math.max(0, current.offset - pageSize) }))}>Previous</button><button disabled={!canNext || loading} onClick={() => setPage((current) => ({ ...current, offset: current.offset + pageSize }))}>Next</button></div></div></section>
}

function formatCell(value: unknown) {
  if (value === null || value === undefined || value === '') return <span className="null-cell">null</span>
  return String(value)
}

function ResultCard({ answer }: { answer: AnalysisResult }) {
  const resultColumns = answer.sql_result?.length ? Object.keys(answer.sql_result[0]) : []
  return <div className="result-panel"><div className="panel-heading"><span>ANALYSIS RESULT</span><span className="result-tag">READY</span></div><h3>{answer.llm_answer ?? answer.answer}</h3>{answer.llm_answer && <p className="deterministic-answer">Verified result: {answer.answer}</p>}<p className="method"><strong>Method</strong>{answer.method}</p>{answer.report && <SummaryReportView report={answer.report} />}{answer.sql_result && resultColumns.length > 0 && <div className="verified-result"><div className="verified-result-heading"><strong>Verified rows</strong><span>{answer.sql_result.length} returned</span></div><div className="result-table-scroll"><table><thead><tr>{resultColumns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{answer.sql_result.slice(0, 10).map((row, index) => <tr key={index}>{resultColumns.map((column) => <td key={column}>{formatCell(row[column])}</td>)}</tr>)}</tbody></table></div></div>}{answer.sql_validation && <p className="sql-warning">{answer.sql_validation}</p>}{answer.anomalies && answer.anomalies.length > 0 && <div className="anomaly-list">{answer.anomalies.slice(0, 4).map((item) => <div key={`${item.column}-${item.row}`}><strong>{item.column}</strong><span>{item.value.toLocaleString()} / row {item.row + 1}</span><small>{item.reason}</small></div>)}</div>}{answer.chart && <ChartView chart={answer.chart} />}{answer.generated_sql && <details className="code-details"><summary>View generated SQL</summary><pre>{answer.generated_sql}</pre></details>}</div>
}

function SummaryReportView({ report }: { report: NonNullable<AnalysisResult['report']> }) {
  const overview = report.overview
  return <div className="summary-report"><div className="summary-metrics">{Object.entries(overview).map(([label, value]) => <div key={label}><strong>{value.toLocaleString()}</strong><span>{label.replace('_', ' ')}</span></div>)}</div><details open><summary>Processed schema ({report.schema.length} columns)</summary><div className="result-table-scroll"><table><thead><tr><th>Column</th><th>Type</th><th>Non-null</th><th>Nulls</th><th>Unique</th></tr></thead><tbody>{report.schema.map((column) => <tr key={String(column.name)}><td>{String(column.name)}</td><td>{String(column.dtype)}</td><td>{String(column.non_null)}</td><td>{String(column.nulls)}</td><td>{String(column.unique)}</td></tr>)}</tbody></table></div></details>{report.numeric_statistics.length > 0 && <details><summary>Numeric statistics ({report.numeric_statistics.length})</summary><div className="result-table-scroll"><table><thead><tr><th>Column</th><th>Mean</th><th>Median</th><th>Min</th><th>Max</th></tr></thead><tbody>{report.numeric_statistics.map((item) => <tr key={String(item.column)}><td>{String(item.column)}</td><td>{String(item.mean)}</td><td>{String(item.median)}</td><td>{String(item.min)}</td><td>{String(item.max)}</td></tr>)}</tbody></table></div></details>}</div>
}

function ChartView({ chart }: { chart: Chart }) {
  const colors = ['#d4794e', '#3f6a4e', '#8fb696', '#c8a15a', '#7c8f9e']
  return <div className="chart"><ResponsiveContainer width="100%" height={220}>{chart.type === 'line' ? <LineChart data={chart.data}><CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#dfe4df" /><XAxis dataKey={chart.xKey} tickLine={false} axisLine={false} tick={{ fill: '#6f786f', fontSize: 11 }} /><YAxis tickLine={false} axisLine={false} tick={{ fill: '#6f786f', fontSize: 11 }} /><Tooltip /><Line type="monotone" dataKey={chart.yKey} stroke="#3f6a4e" strokeWidth={2} dot={{ fill: '#d4794e', r: 3 }} /></LineChart> : chart.type === 'pie' ? <PieChart><Pie data={chart.data} dataKey={chart.yKey} nameKey={chart.xKey} cx="50%" cy="50%" outerRadius={78}>{chart.data.map((_, index) => <Cell key={index} fill={colors[index % colors.length]} />)}</Pie><Tooltip /></PieChart> : chart.type === 'scatter' ? <ScatterChart><CartesianGrid /><XAxis dataKey={chart.xKey} /><YAxis dataKey={chart.yKey} /><Tooltip /><Scatter data={chart.data} fill="#d4794e" /></ScatterChart> : <BarChart data={chart.data}><CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#dfe4df" /><XAxis dataKey={chart.xKey} tickLine={false} axisLine={false} tick={{ fill: '#6f786f', fontSize: 11 }} /><YAxis tickLine={false} axisLine={false} tick={{ fill: '#6f786f', fontSize: 11 }} /><Tooltip cursor={{ fill: '#edf1eb' }} /><Bar dataKey={chart.yKey} fill="#d4794e" radius={[3, 3, 0, 0]} /></BarChart>}</ResponsiveContainer></div>
}

export default App
