import React, { useEffect, useState } from 'react'

// Production API base URL comes from VITE_API_URL (set in Vercel to the
// deployed backend URL, e.g. https://campusguide-api.onrender.com).
// Local dev falls back to '/api', served by the Vite proxy in vite.config.js.
const API = import.meta.env.VITE_API_URL || '/api'

export default function App() {
  const [token, setToken] = useState(localStorage.getItem('cg_token') || '')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState('')
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState([])
  const [docs, setDocs] = useState([])
  const [stats, setStats] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const authHeaders = () => ({ 'Content-Type': 'application/json', Authorization: `Bearer ${token}` })

  async function api(path, opts = {}) {
    const res = await fetch(`${API}${path}`, opts)
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data.detail || data.message || `Request failed (${res.status})`)
    return data
  }

  async function login(e) {
    e.preventDefault()
    setError('')
    try {
      const data = await api('/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password }) })
      setToken(data.token); setRole(data.role); localStorage.setItem('cg_token', data.token)
      loadDocs(); loadStats()
    } catch (err) { setError(err.message) }
  }

  async function register() {
    setError('')
    try {
      const data = await api('/auth/register', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password, role: 'student' }) })
      setToken(data.token); setRole(data.role); localStorage.setItem('cg_token', data.token)
      loadDocs(); loadStats()
    } catch (err) { setError(err.message) }
  }

  function loadDocs() { api('/documents', { headers: authHeaders() }).then(setDocs).catch(() => {}) }
  function loadStats() { api('/stats', { headers: authHeaders() }).then(setStats).catch(() => {}) }
  useEffect(() => { if (token) { loadDocs(); loadStats() } }, [token])

  async function ask(e) {
    e.preventDefault()
    if (!question.trim()) return
    setLoading(true); setError('')
    const q = question; setQuestion('')
    setMessages((m) => [...m, { from: 'you', text: q }])
    try {
      const data = await api('/chat', { method: 'POST', headers: authHeaders(), body: JSON.stringify({ question: q }) })
      setMessages((m) => [...m, { from: 'bot', text: data.answer, citations: data.citations, route: data.route, draft: data.draft_pending_approval }])
    } catch (err) { setError(err.message) }
    setLoading(false)
  }

  async function sendFeedback(msg, vote) {
    try {
      await api('/feedback', { method: 'POST', headers: authHeaders(), body: JSON.stringify({ question: messages[messages.indexOf(msg) - 1]?.text || '', answer: msg.text, vote }) })
      setMessages((m) => m.map((x) => (x === msg ? { ...x, voted: vote } : x)))
    } catch (err) { setError(err.message) }
  }

  async function upload(e) {
    const file = e.target.files[0]
    if (!file) return
    const form = new FormData(); form.append('file', file)
    try {
      await api('/documents', { method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: form })
      await api('/ingest', { method: 'POST', headers: authHeaders() })
      loadDocs()
    } catch (err) { setError(err.message) }
  }

  if (!token) {
    return (
      <div className="wrap">
        <div className="banner">Real KIET documents — answers come from official KIET ordinances, fee structure, hostel rules and placement records (fetched 11 Nov 2026). Placement figures in the stats table are still sample data.</div>
        <h1>CampusGuide Agent</h1>
        <p>Ask about attendance, exams, placements, library, fees and hostel rules.</p>
        <form onSubmit={login} className="card">
          <input placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
          <input placeholder="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
          <button type="submit">Log in</button>
          <button type="button" onClick={register}>Register as student</button>
        </form>
        <p className="hint">Demo admin: admin@campus.local / admin123 (change on deploy).</p>
        {error && <p className="err">{error}</p>}
      </div>
    )
  }

  return (
    <div className="wrap">
      <div className="banner">Real KIET documents — answers come from official KIET ordinances, fee structure, hostel rules and placement records. Placement figures in the stats table are still sample data.</div>
      <header><h1>CampusGuide Agent</h1><span>Role: {role}</span><button onClick={() => { setToken(''); localStorage.removeItem('cg_token') }}>Log out</button></header>
      {error && <p className="err">{error}</p>}
      <div className="grid">
        <section className="card chat">
          <h2>Ask a question</h2>
          <div className="messages">
            {messages.map((m, i) => (
              <div key={i} className={`msg ${m.from}`}>
                <p style={{ whiteSpace: 'pre-wrap' }}>{m.text}</p>
                {m.citations && m.citations.length > 0 && (
                  <p className="cites">Sources: {m.citations.join('; ')}</p>
                )}
                {m.route && <p className="route">Agent: {m.route}{m.draft ? ' — draft saved, pending admin approval' : ''}</p>}
                {m.from === 'bot' && (
                  <div className="fb">
                    <button disabled={m.voted} onClick={() => sendFeedback(m, 'up')}>👍 {m.voted === 'up' ? 'Thanks!' : ''}</button>
                    <button disabled={m.voted} onClick={() => sendFeedback(m, 'down')}>👎 {m.voted === 'down' ? 'Thanks!' : ''}</button>
                  </div>
                )}
              </div>
            ))}
          </div>
          <form onSubmit={ask}>
            <input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="e.g. What is the minimum attendance required?" />
            <button type="submit" disabled={loading}>{loading ? 'Thinking…' : 'Ask'}</button>
          </form>
        </section>
        <aside>
          <section className="card">
            <h2>Documents (official KIET)</h2>
            <ul>{docs.map((d) => <li key={d.slug}>{d.title} — {d.chunks} chunks {d.is_sample ? '(sample)' : ''}</li>)}</ul>
            {role === 'admin' && (
              <label>Upload document (admin): <input type="file" accept=".md,.txt" onChange={upload} /></label>
            )}
          </section>
          <section className="card">
            <h2>Placement stats (sample)</h2>
            <table><thead><tr><th>Company</th><th>Year</th><th>Role</th><th>Offers</th><th>CTC</th></tr></thead>
            <tbody>{stats.map((s, i) => <tr key={i}><td>{s.company}</td><td>{s.year}</td><td>{s.role}</td><td>{s.offers}</td><td>{s.ctc_lpa}</td></tr>)}</tbody></table>
          </section>
        </aside>
      </div>
    </div>
  )
}
