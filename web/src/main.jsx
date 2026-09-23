import React, { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'

const typeLabels = {
  move: '移动', talk: '交谈', inspect: '调查', relationship: '关系',
  give_item: '物品', director: '世界事件', narration: '叙述',
}
const names = ['林默', '苏晚', '赵无极']
const initials = { 林默: '林', 苏晚: '苏', 赵无极: '赵' }

async function send(path, body) {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    throw new Error(error.detail || `请求失败：${response.status}`)
  }
}

function RelationshipMap({ characters, selected, onSelect }) {
  const positions = { 林默: [105, 75], 苏晚: [280, 64], 赵无极: [195, 198] }
  const edges = [['林默', '苏晚'], ['林默', '赵无极'], ['苏晚', '赵无极']]
  return <svg className="relationship-map" viewBox="0 0 385 260" role="img" aria-label="角色关系图">
    {edges.map(([a, b]) => {
      const [ax, ay] = positions[a], [bx, by] = positions[b]
      const score = characters?.[a]?.relationships?.[b] ?? 0
      return <g key={`${a}-${b}`}>
        <line x1={ax} y1={ay} x2={bx} y2={by} className={score < 0 ? 'edge negative' : 'edge'} />
        <rect x={(ax + bx) / 2 - 20} y={(ay + by) / 2 - 12} width="40" height="23" rx="11" className="edge-label-bg" />
        <text x={(ax + bx) / 2} y={(ay + by) / 2 + 4} textAnchor="middle" className={score < 0 ? 'edge-label negative' : 'edge-label'}>{score > 0 ? '+' : ''}{score}</text>
      </g>
    })}
    {names.map(name => {
      const [x, y] = positions[name]
      return <g key={name} onClick={() => onSelect(name)} className="map-node" tabIndex="0" role="button" aria-label={`查看${name}`}>
        <circle cx={x} cy={y} r="36" className={selected === name ? 'node-ring selected' : 'node-ring'} />
        <text x={x} y={y + 7} textAnchor="middle" className="node-initial">{initials[name]}</text>
        <text x={x} y={y + 55} textAnchor="middle" className="node-name">{name}</text>
      </g>
    })}
  </svg>
}

function App() {
  const [world, setWorld] = useState(null)
  const [connected, setConnected] = useState(false)
  const [selected, setSelected] = useState('林默')
  const [view, setView] = useState(null)
  const [filter, setFilter] = useState('all')
  const [speed, setSpeed] = useState(1)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')

  useEffect(() => {
    fetch('/api/world').then(response => response.json()).then(setWorld).catch(error => setNotice(error.message))
    const stream = new EventSource('/api/events')
    stream.addEventListener('state', event => { setWorld(JSON.parse(event.data)); setConnected(true) })
    stream.onerror = () => setConnected(false)
    return () => stream.close()
  }, [])

  useEffect(() => {
    fetch(`/api/characters/${encodeURIComponent(selected)}/view`)
      .then(response => response.json()).then(setView).catch(() => setView(null))
  }, [selected, world?.tick_count, world?.events?.length])

  const events = useMemo(() => {
    const all = [...(world?.events || [])].reverse()
    return filter === 'all' ? all : all.filter(event => event.type === filter)
  }, [world?.events, filter])

  async function command(path, body) {
    setBusy(true); setNotice('')
    try { await send(path, body) }
    catch (error) { setNotice(error.message) }
    finally { setBusy(false) }
  }

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark">✦</span><div><strong>NOVELWORLD</strong><small>动态叙事引擎 · V3</small></div></div>
      <div className="side-label">世界导航</div>
      <a className="nav-link active" href="#overview"><span>◫</span> 世界总览</a>
      <a className="nav-link" href="#timeline"><span>◷</span> 事件时间线</a>
      <a className="nav-link" href="#characters"><span>◇</span> 角色视角</a>
      <div className="sidebar-spacer" />
      <div className="world-id">世界 ID <span>{world?.world_id?.slice(0, 10) || '连接中'}…</span></div>
      <div className="connection"><i className={connected ? 'dot online' : 'dot'} />{connected ? '实时连接中' : '正在重连'}</div>
    </aside>

    <main className="main-content" id="overview">
      <header className="topbar"><div><div className="eyebrow">WORLD OBSERVATORY / 世界观测台</div><h1>每个选择，都让世界继续生长。</h1></div><div className="version-pill">● LIVE WORLD <span>V3.0</span></div></header>

      {notice && <div className="notice">{notice}<button onClick={() => setNotice('')}>×</button></div>}
      {world?.error && <div className="notice">运行中断：{world.error}</div>}

      <section className="stats-grid">
        <div className="stat-card"><div className="stat-icon blue">◷</div><div><span>世界时间</span><strong>{world?.time || '--:--'}</strong></div></div>
        <div className="stat-card"><div className="stat-icon gold">◇</div><div><span>已运行 Tick</span><strong>{world?.tick_count ?? '—'}</strong></div></div>
        <div className="stat-card"><div className="stat-icon green">✧</div><div><span>世界事件</span><strong>{world?.event_count ?? '—'}</strong></div></div>
        <div className="stat-card"><div className="stat-icon red">◉</div><div><span>世界状态</span><strong className="state-text">{world?.running ? '运行中' : '已暂停'}</strong></div></div>
      </section>

      <section className="control-panel">
        <div><div className="panel-kicker">WORLD CONTROL</div><h2>让故事继续</h2><p>每个 Tick 由一位角色自行决定行动；Director 只在需要时改变环境。</p></div>
        <div className="control-actions">
          <button className="primary-button" disabled={busy || world?.running} onClick={() => command('/api/control/next')}>▶ 下一 Tick</button>
          <button className="secondary-button" disabled={busy || world?.running} onClick={() => command('/api/control/run', {count: 10, delay_seconds: Number(speed)})}>运行 10 Tick</button>
          <button className="secondary-button" disabled={busy || world?.running} onClick={() => command('/api/control/run', {count: 20, delay_seconds: Number(speed)})}>运行 20 Tick</button>
          <button className="pause-button" disabled={!world?.running} onClick={() => command('/api/control/pause')}>Ⅱ 暂停</button>
          <label className="speed-control">间隔 <input type="range" min="0" max="5" step="0.5" value={speed} onChange={event => setSpeed(event.target.value)} /><b>{speed}s</b></label>
        </div>
      </section>

      <div className="two-column">
        <section className="panel timeline-panel" id="timeline">
          <div className="section-heading"><div><div className="panel-kicker">CHRONICLE</div><h2>事件时间线</h2></div><select value={filter} onChange={event => setFilter(event.target.value)} aria-label="筛选事件"><option value="all">全部事件</option>{Object.entries(typeLabels).map(([type, label]) => <option key={type} value={type}>{label}</option>)}</select></div>
          <div className="timeline-list">{events.length ? events.map(event => <article className="event-row" key={event.id}><div className={`event-marker ${event.type}`} /> <div className="event-content"><div className="event-meta"><span>{event.timestamp}</span><b>{typeLabels[event.type] || event.type}</b><em>{event.location}</em></div><p>{event.description}</p></div></article>) : <div className="empty">还没有事件。运行一轮，让故事开始。</div>}</div>
        </section>

        <div className="right-stack">
          <section className="panel" id="characters"><div className="section-heading"><div><div className="panel-kicker">CHARACTERS</div><h2>角色状态</h2></div><span className="count-badge">{names.length} NPC</span></div><div className="character-list">{names.map(name => { const person = world?.characters?.[name]; return <button key={name} className={selected === name ? 'character-card selected' : 'character-card'} onClick={() => setSelected(name)}><span className={`avatar avatar-${name}`}>{initials[name]}</span><span className="character-main"><strong>{name}<small>{person?.role || '加载中'}</small></strong><span>⌖ {person?.location || '—'} · 体力 {person?.energy ?? '—'}</span></span><span className="card-arrow">›</span></button> })}</div></section>
          <section className="panel relationship-panel"><div className="section-heading"><div><div className="panel-kicker">RELATIONSHIPS</div><h2>角色关系</h2></div></div><RelationshipMap characters={world?.characters} selected={selected} onSelect={setSelected} /><p className="graph-note">连线数字表示前者对后者的关系值</p></section>
        </div>
      </div>

      <section className="panel perspective-panel"><div className="section-heading"><div><div className="panel-kicker">PERSPECTIVE</div><h2>{selected}的视角</h2></div><span className="view-tag">独立知识与记忆</span></div><div className="perspective-grid"><div><h3>当前目标</h3>{view?.goals?.map(goal => <p className="line-item" key={goal}>{goal}</p>) || <p className="muted">加载中</p>}<h3>已知事实</h3>{view?.known_facts?.map(fact => <p className="line-item" key={fact}>{fact}</p>) || <p className="muted">暂无</p>}</div><div><h3>近期记忆</h3>{view?.recent_memories?.length ? view.recent_memories.map((memory, index) => <p className="memory-item" key={index}>{memory}</p>) : <p className="muted">暂无近期记忆</p>}</div><div><h3>长期记忆与调查事实</h3>{[...(view?.semantic_facts || []), ...(view?.archived_memories || [])].length ? [...(view?.semantic_facts || []), ...(view?.archived_memories || [])].slice(-8).map((memory, index) => <p className="memory-item" key={index}>{memory}</p>) : <p className="muted">暂无长期记忆</p>}</div></div></section>
      <footer>NovelWorld · Agent 决策由模型完成，世界状态由程序执行和保存。自动运行会产生模型 API 费用。</footer>
    </main>
  </div>
}

createRoot(document.getElementById('root')).render(<App />)
