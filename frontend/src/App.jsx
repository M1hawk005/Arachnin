import { useEffect, useRef, useState } from 'react';
import { ingestionApi } from './api';
import './App.css';

const TERMINAL_STATES = new Set(['COMPLETED', 'FAILED']);

function Mark() {
  return (
    <svg viewBox="0 0 40 40" aria-hidden="true">
      <path d="M20 4 5 12.5v15L20 36l15-8.5v-15L20 4Z" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <path d="m12 25 8-14 8 14M15.5 19h9" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function StatusPill({ status }) {
  const label = status?.toLowerCase().replace('_', ' ') || 'idle';
  return <span className={`status-pill status-${label}`}>{label}</span>;
}

function formatDate(value) {
  return new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(value));
}

function App() {
  const [url, setUrl] = useState('');
  const [chunkSize, setChunkSize] = useState(500);
  const [chunkOverlap, setChunkOverlap] = useState(50);
  const [job, setJob] = useState(null);
  const [result, setResult] = useState(null);
  const [recent, setRecent] = useState([]);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [tab, setTab] = useState('content');
  const [copied, setCopied] = useState(false);
  const pollTimer = useRef(null);

  const loadRecent = async () => {
    try {
      setRecent(await ingestionApi.recent());
    } catch {
      setRecent([]);
    }
  };

  useEffect(() => {
    loadRecent();
    return () => window.clearTimeout(pollTimer.current);
  }, []);

  const poll = async (jobId) => {
    try {
      const next = await ingestionApi.status(jobId);
      setJob(next);
      if (next.status === 'COMPLETED') {
        setResult(await ingestionApi.result(jobId));
        await loadRecent();
      } else if (next.status === 'FAILED') {
        setError(next.error?.message || 'The ingestion could not be completed.');
      } else {
        pollTimer.current = window.setTimeout(() => poll(jobId), 1200);
      }
    } catch (requestError) {
      setError(requestError.message);
    }
  };

  const submit = async (event) => {
    event.preventDefault();
    window.clearTimeout(pollTimer.current);
    setSubmitting(true);
    setError(null);
    setResult(null);
    setTab('content');
    try {
      const submittedUrl = /^https?:\/\//i.test(url) ? url : `https://${url}`;
      const accepted = await ingestionApi.create({
        url: submittedUrl,
        chunk_size: Number(chunkSize),
        chunk_overlap: Number(chunkOverlap),
      });
      setJob({ ...accepted, stage: 'Queued', progress: 10 });
      poll(accepted.job_id);
    } catch (requestError) {
      setJob(null);
      setError(requestError.message);
    } finally {
      setSubmitting(false);
    }
  };

  const openJob = async (jobId) => {
    window.clearTimeout(pollTimer.current);
    setError(null);
    setResult(null);
    try {
      const selected = await ingestionApi.status(jobId);
      setJob(selected);
      if (selected.status === 'COMPLETED') setResult(await ingestionApi.result(jobId));
      else if (!TERMINAL_STATES.has(selected.status)) poll(jobId);
    } catch (requestError) {
      setError(requestError.message);
    }
  };

  const copyContent = async () => {
    await navigator.clipboard.writeText(result.content);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };

  const downloadJson = () => {
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `arachnin-${result.job_id}.json`;
    link.click();
    URL.revokeObjectURL(link.href);
  };

  return (
    <div className="shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="Arachnin home">
          <span className="brand-mark"><Mark /></span>
          <span>ARACHNIN</span>
          <span className="brand-context">/ WEB INGESTION</span>
        </a>
        <div className="topbar-links">
          <a href="/api/docs" target="_blank">API docs ↗</a>
          <a href="https://github.com/M1hawk005/Arachnin" target="_blank" rel="noreferrer">GitHub ↗</a>
          <span className="system-state"><i /> System ready</span>
        </div>
      </header>

      <main id="top">
        <section className="hero">
          <div className="eyebrow"><span>01</span> Retrieval infrastructure</div>
          <h1>From web page to<br /><em>retrieval-ready data.</em></h1>
          <p>
            Arachnin safely fetches public pages, removes boilerplate, captures provenance,
            and produces deterministic chunks your RAG pipeline can index directly.
          </p>
          <div className="proof-row">
            <div><strong>5 MB</strong><span>bounded fetch</span></div>
            <div><strong>SSRF</strong><span>network guarded</span></div>
            <div><strong>SHA-256</strong><span>content identity</span></div>
            <div><strong>Async</strong><span>worker pipeline</span></div>
          </div>
        </section>

        <section className="workspace" aria-label="Ingestion workbench">
          <div className="workspace-head">
            <div>
              <span className="section-index">02</span>
              <h2>Ingestion workbench</h2>
            </div>
            <p>Public HTML only · private networks blocked · 5 MB maximum</p>
          </div>

          <form className="ingest-form" onSubmit={submit}>
            <label className="url-field">
              <span>Source URL</span>
              <div className="input-wrap">
                <span className="protocol">https://</span>
                <input
                  type="text"
                  inputMode="url"
                  value={url}
                  onChange={(event) => setUrl(event.target.value)}
                  placeholder="docs.example.com/engineering/article"
                  required
                  aria-describedby="url-help"
                />
              </div>
            </label>
            <div className="settings-row">
              <label>
                <span>Chunk size</span>
                <select value={chunkSize} onChange={(event) => setChunkSize(event.target.value)}>
                  <option value="300">300 words · precise</option>
                  <option value="500">500 words · balanced</option>
                  <option value="800">800 words · contextual</option>
                </select>
              </label>
              <label>
                <span>Overlap</span>
                <select value={chunkOverlap} onChange={(event) => setChunkOverlap(event.target.value)}>
                  <option value="30">30 words</option>
                  <option value="50">50 words</option>
                  <option value="100">100 words</option>
                </select>
              </label>
              <button className="primary-button" disabled={submitting || !url}>
                {submitting ? 'Queueing…' : 'Ingest document'} <span>→</span>
              </button>
            </div>
            <span id="url-help" className="form-note">Redirect destinations are revalidated before every fetch.</span>
          </form>

          {error && <div className="error-banner" role="alert"><b>Request failed</b><span>{error}</span></div>}

          {job && (
            <section className="job-panel" aria-live="polite">
              <div className="job-heading">
                <div>
                  <span className="mono-label">JOB / {job.job_id?.slice(0, 8)}</span>
                  <h3>{job.stage || 'Processing document'}</h3>
                </div>
                <StatusPill status={job.status} />
              </div>
              <div className="progress-track"><span style={{ width: `${job.progress || 0}%` }} /></div>
              <div className="progress-meta"><span>{job.progress || 0}% complete</span><span>Results persist after completion</span></div>
            </section>
          )}

          {result && (
            <section className="result-panel">
              <div className="result-summary">
                <div>
                  <span className="mono-label">DOCUMENT / READY</span>
                  <h3>{result.metadata.title || 'Untitled document'}</h3>
                  <a href={result.metadata.canonical_url} target="_blank" rel="noreferrer">{result.metadata.canonical_url}</a>
                </div>
                <div className="result-stats">
                  <div><strong>{result.metadata.word_count.toLocaleString()}</strong><span>words</span></div>
                  <div><strong>{result.chunks.length}</strong><span>chunks</span></div>
                  <div><strong>{result.metadata.language || '—'}</strong><span>language</span></div>
                </div>
              </div>
              <div className="result-toolbar">
                <div className="tabs" role="tablist">
                  {['content', 'chunks', 'json'].map((name) => (
                    <button key={name} className={tab === name ? 'active' : ''} onClick={() => setTab(name)} type="button">{name}</button>
                  ))}
                </div>
                <div className="result-actions">
                  <button type="button" onClick={copyContent}>{copied ? 'Copied' : 'Copy text'}</button>
                  <button type="button" onClick={downloadJson}>Export JSON ↓</button>
                </div>
              </div>
              <div className="result-body">
                {tab === 'content' && <article>{result.content}</article>}
                {tab === 'chunks' && result.chunks.map((chunk) => (
                  <div className="chunk" key={chunk.index}>
                    <div><span>CHUNK {String(chunk.index + 1).padStart(2, '0')}</span><span>{chunk.word_count} words</span></div>
                    <p>{chunk.text}</p>
                  </div>
                ))}
                {tab === 'json' && <pre>{JSON.stringify(result, null, 2)}</pre>}
              </div>
            </section>
          )}
        </section>

        <section className="recent-section">
          <div className="section-title"><span className="section-index">03</span><h2>Recent ingestions</h2></div>
          <div className="recent-list">
            {recent.length === 0 && <p className="empty-state">Completed and queued documents will appear here.</p>}
            {recent.map((item) => (
              <button className="recent-row" key={item.job_id} onClick={() => openJob(item.job_id)}>
                <span className="recent-title"><b>{item.title || new URL(item.url).hostname}</b><small>{item.url}</small></span>
                <span>{item.word_count?.toLocaleString() || '—'} words</span>
                <span>{item.chunk_count} chunks</span>
                <span>{formatDate(item.created_at)}</span>
                <StatusPill status={item.status} />
                <i>→</i>
              </button>
            ))}
          </div>
        </section>
      </main>

      <footer><span>Arachnin / v0.2</span><span>Built as a transparent reference implementation.</span><span>MIT License</span></footer>
    </div>
  );
}

export default App;
