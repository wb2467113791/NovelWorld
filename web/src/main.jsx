import React, {useEffect, useMemo, useRef, useState} from 'react'
import {createRoot} from 'react-dom/client'
import {request, clock} from './api.js'
import PlayMode from './PlayMode.jsx'
import WorldSetup from './WorldSetup.jsx'
import './style.css'

const labels = {
  move: '来到', activity_started: '活动开始', activity_completed: '活动结束', activity_interrupted: '停下活动',
  invitation: '邀约', invitation_declined: '婉拒', invitation_expired: '未回应',
  conversation_started: '开始交谈', conversation_ended: '交谈结束', talk: '交谈', inspect: '查看', arrival: '到来',
}

function Portrait({name, index=0, small=false}) {
  return <span className={`portrait tone-${index % 4} ${small ? 'small' : ''}`}>{name?.slice(-1) || '人'}</span>
}

function Scene({location, description, world, selected, select}) {
  const people = Object.values(world.characters || {}).filter(p => p.location === location)
  return <article className="scene">
    <div className="scene-title"><span className="location-glyph">⌂</span><h3>{location}</h3><span>{people.length} 人在这里</span></div>
    <p className="scene-description">{description}</p>
    <div className="scene-people">{people.length ? people.map(p => {
      const conversation = world.conversations?.find(s => s.participants.includes(p.name))
      const activity = p.activity
      const progress = activity ? Math.min(100, (world.minute - activity.started) / (activity.until - activity.started) * 100) : 0
      const index = Object.keys(world.characters).indexOf(p.name)
      return <button key={p.name} className={`resident ${selected === p.name ? 'chosen' : ''}`} onClick={() => select(p.name)}>
        <Portrait name={p.name} index={index} small/><span><b>{p.name}</b><small>{conversation ? `与${conversation.participants.find(n => n !== p.name)}交谈` : activity?.name || '暂时空闲'}</small>
        {activity && <span className="activity-track"><i style={{width: `${progress}%`}}/></span>}</span>
        {activity && <em>{clock(activity.until)}结束</em>}
      </button>
    }) : <p className="quiet">此刻很安静。</p>}</div>
  </article>
}

function Story({world, filter, follow, selected}) {
  const scroll = useRef(null)
  const decisions = useMemo(() => {
    const byEvent = {}
    for (const d of world.decisions || []) {
      const lastId = d.event_ids?.at(-1)
      if (lastId) byEvent[lastId] = d
    }
    return byEvent
  }, [world.decisions])
  const rows = (world.events || []).filter(e => filter === 'all' || e.actor === filter || e.target === filter || decisions[e.id]?.actor === filter)
  useEffect(() => {
    if (follow && scroll.current) scroll.current.scrollTop = scroll.current.scrollHeight
  }, [world.revision, follow, filter])
  return <div ref={scroll} className="story-scroll" tabIndex="0" aria-label="按发生顺序阅读故事">
    {!rows.length && <div className="story-empty"><span>✧</span><h3>清晨，故事还没有开始。</h3><p>让时间向前走，看看每个人会怎样度过今天。</p></div>}
    {rows.map(e => {
      const thought = decisions[e.id]
      const speech = e.type === 'talk' || e.type === 'invitation'
      return <article key={e.id} className={`story-entry ${speech ? 'speech-entry' : ''} ${selected === e.actor ? 'highlight' : ''}`}>
        <div className="story-margin"><time>{clock(e.minute)}</time><span className="story-dot"/></div>
        <div className="story-body"><div className="story-meta"><b>{e.actor}</b>{e.target && <span>与 {e.target}</span>}<span>{e.location}</span><small>{labels[e.type] || e.type}</small></div>
          {speech ? <blockquote>{e.payload.message}</blockquote> : <p>{e.description}</p>}
          {thought && <div className="thought"><span>◌ {thought.actor}的动机</span><p>{thought.reason}</p></div>}
        </div>
      </article>
    })}
  </div>
}

function CharacterDetail({world, selected, select}) {
  const people = Object.values(world.characters || {}).filter(p => p.actor_type === 'npc')
  const p = world.characters?.[selected]
  const d = [...(world.decisions || [])].reverse().find(d => d.actor === selected)
  const mind = p?.mind || {}
  const impressions = {...p?.relationships, ...mind.relationship_notes}
  return <aside className="character-panel">
    <div className="section-title"><span className="eyebrow">他们的生活</span><h2>人物手记</h2></div>
    <div className="character-tabs">{people.map((person, i) => <button className={selected === person.name ? 'selected' : ''} key={person.name} onClick={() => select(person.name)}><Portrait name={person.name} index={i} small/><span>{person.name}</span></button>)}</div>
    {p?.actor_type === 'npc' ? <>
      <div className="person-heading"><Portrait name={p.name} index={people.findIndex(v => v.name === p.name)}/><div><h3>{p.name}</h3><span>{p.role} · {p.location}</span></div></div>
      <p className="person-background">{p.background}</p>
      <div className="person-section"><h4>此刻在意</h4><p>{mind.goal || p.goals?.[0]}</p><h4>下一步打算</h4><p>{mind.intention || '还未作出选择'}</p>{d && <p className="muted">{d.reason}</p>}</div>
      <div className="person-section"><h4>一天的安排 <small>个人意图，可改变</small></h4>{mind.plan?.length ? mind.plan.map((plan, i) => <div key={i} className={`plan-item ${plan.at < world.minute ? 'past' : ''}`}><time>{clock(plan.at)}</time><div><p>{plan.purpose}</p><small>{plan.location}</small></div></div>) : <p className="muted">尚未安排，下一次思考时可形成计划。</p>}</div>
      <div className="person-section"><h4>对他人的印象</h4>{Object.entries(impressions).map(([name, note]) => <p className="impression" key={name}><b>{name}</b>{note}</p>)}</div>
      <div className="person-section"><h4>从经历中想到的</h4><p>{mind.reflection || '还没有形成新的反思。'}</p></div>
      <details className="person-section"><summary>记忆与私人设定</summary><p>{p.personality}</p>{p.secrets?.map(s => <p className="private-note" key={s}>{s}</p>)}{[...(p.memories || [])].reverse().slice(0, 10).map(m => <div className="memory" key={m.id}><small>{clock(m.minute)} · {m.kind === 'reported' ? '听到的说法' : m.kind === 'reflection' ? '主观反思' : '亲历'}</small><p>{m.content}</p></div>)}<small className="muted">这些资料只在上帝视角展示。</small></details>
    </> : <p className="muted">选择一个人物，读一读他的手记。</p>}
  </aside>
}

function App() {
  const [world, setWorld] = useState(null)
  const [participating, setParticipating] = useState(false)
  const [playerWorld, setPlayerWorld] = useState(null)
  const [history, setHistory] = useState([])
  const [historyBusy, setHistoryBusy] = useState(false)
  const currentWorld = useRef(null)
  currentWorld.current = world?.world_id
  const [selected, setSelected] = useState('苏晚')
  const [filter, setFilter] = useState('all')
  const [follow, setFollow] = useState(true)
  const [connected, setConnected] = useState(false)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [setup, setSetup] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [tickCount, setTickCount] = useState('12')
  const ticks = Number(tickCount)
  const validTicks = Number.isInteger(ticks) && ticks >= 1 && ticks <= 100

  useEffect(() => {
    let active = true
    request('/api/world?mode=observe').then(w => {if (active) setWorld(w)}).catch(e => {if (active) setNotice(e.message)})
    const stream = new EventSource('/api/events?mode=observe')
    stream.addEventListener('state', e => {if (active) {setWorld(JSON.parse(e.data)); setConnected(true)}})
    stream.onerror = () => {if (active) setConnected(false)}
    return () => {active = false; stream.close()}
  }, [])

  useEffect(() => {
    if (!participating || !world?.world_id) return
    let active = true
    setPlayerWorld(null)
    request('/api/world?mode=play').then(w => {if (active) setPlayerWorld(w)}).catch(e => {if (active) setNotice(e.message)})
    const stream = new EventSource('/api/events?mode=play')
    stream.addEventListener('state', e => {if (active) setPlayerWorld(JSON.parse(e.data))})
    return () => {active = false; stream.close()}
  }, [participating, world?.world_id])

  useEffect(() => {
    if (world && !world.characters?.[selected]) setSelected(Object.keys(world.characters || {})[0] || '')
  }, [world?.world_id, selected])

  useEffect(() => {setFilter('all'); setHistory([])}, [world?.world_id])
  useEffect(() => {
    if (!world) return
    setHistory(old => {
      const events = new Map(old.map(e => [e.id, e]))
      for (const e of world.events || []) events.set(e.id, e)
      return [...events.values()]
    })
  }, [world])

  const storyWorld = useMemo(() => {
    const events = new Map(history.map(e => [e.id, e]))
    for (const e of world?.events || []) events.set(e.id, e)
    return {...world, events: [...events.values()]}
  }, [world, history])

  async function earlier() {
    const id = world.world_id
    setHistoryBusy(true)
    try {
      const before = storyWorld.events[0]?.id
      const page = await request(`/api/history?mode=observe${before ? `&before=${encodeURIComponent(before)}` : ''}`)
      if (page.world_id === id && currentWorld.current === id) {
        setHistory(old => [...page.events, ...old]); setFollow(false)
      }
    } catch (error) {setNotice(error.message)}
    finally {setHistoryBusy(false)}
  }

  async function command(path, body={}) {
    setBusy(true); setNotice('')
    try {
      const result = await request(path, body)
      setWorld(await request('/api/world?mode=observe'))
      if (participating) setPlayerWorld(await request('/api/world?mode=play'))
      if (result.queued) setNotice('行动已接收；当前轮次结束后执行，无需暂停世界。')
      return result
    } catch (error) {setNotice(error.message); throw error}
    finally {setBusy(false)}
  }
  function control(path, body) {command(path, body).catch(() => {})}

  return <div className="app-shell">
    <nav className="sidebar"><a className="brand" href="#"><span>◈</span><b>NovelWorld</b><small>一座小镇，几种人生</small></a>
      <div className="mode-switch"><button className="active" onClick={() => setParticipating(false)}>旁观小镇</button><button disabled={busy} className={participating ? 'active' : ''} onClick={() => setParticipating(v => !v)}>{participating ? '收起参与' : world?.player_name ? '继续参与' : '走进小镇'}</button></div>
      <p className="sidebar-note">旁观，也能随时作为旅人加入。小镇纪事始终保留。</p>
      <button className="world-settings" onClick={() => setSetup(v => !v)}>⌂ 世界与开局</button>
      <div className="sidebar-bottom"><span className={`connection ${connected ? 'online' : ''}`}>{connected ? '世界已连接' : '连接中'}</span><small>角色自主选择<br/>每段经历，都有来处。</small></div>
    </nav>
    <main>
      <header className="page-header"><div><span className="eyebrow">小型 AI 社会沙盒</span><h1>{world?.title || '青石镇 · 一天尚未写完'}</h1><p>{world?.premise || '正在打开小镇……'}</p></div><div className="world-clock"><span>{world?.time || '—'}</span><small>{world?.running ? world.pausing ? '正在暂停' : '时间向前走' : '此刻暂停'} · {world?.tick_count ?? 0}轮</small></div></header>
      {notice && <div role="alert" className="notice">{notice}<button aria-label="关闭提示" onClick={() => setNotice('')}>×</button></div>}
      {world?.error && <div role="alert" className="notice error">运行已暂停：{world.error}</div>}
      {world?.player_error && <div role="alert" className="notice error">玩家行动未执行：{world.player_error}</div>}
      <section className="controls"><div className="run-state"><i className={world?.running ? 'pulse' : ''}/><span>{world?.acting ? `${world.acting} · ${world.phase}` : '给他们一点时间，生活会继续。'}</span></div><div className="control-buttons">
        <button disabled={busy || !world || world.running} onClick={() => control('/api/control/next')}>走过 5 分钟</button>
        <button className="primary" disabled={busy || !world || world.running} onClick={() => control('/api/control/run', {count: 12, delay_seconds: speed})}>让他们生活一小时</button>
        <form className="tick-run" onSubmit={e => {e.preventDefault(); if (validTicks && world && !world.running && !busy) control('/api/control/run', {count: ticks, delay_seconds: speed})}}>
          <label>运行 Tick <input aria-label="自定义运行 Tick 数" type="number" min="1" max="100" step="1" required value={tickCount} disabled={busy || world?.running} onChange={e => setTickCount(e.target.value)}/></label>
          <button type="submit" disabled={busy || !world || world.running || !validTicks}>运行指定轮数</button>
          <small aria-live="polite">{validTicks ? `推进 ${ticks * 5} 分钟` : '请输入 1–100 的整数'}</small>
        </form>
        <button disabled={busy || !world?.running} onClick={() => control('/api/control/pause')}>暂停</button>
        <label>阅读间隔 <select value={speed} onChange={e => setSpeed(Number(e.target.value))}><option value="0">立即</option><option value="1">1 秒</option><option value="3">3 秒</option></select></label>
      </div></section>
      <p className="cost-note">运行会调用当前配置的模型。每轮最多两名角色思考，活动过程随时间推进。</p>
      {setup && <WorldSetup running={world?.running} activeWorldId={world?.world_id} command={command} busy={busy}/>}
      {participating && <section className="participation-section"><p className="reading-note">你与镇民处在同一个世界。参与面板只使用现场可见信息；收起面板不会删除旅人或经历，离开交谈请使用“结束交谈”。</p><PlayMode key={world?.world_id} world={playerWorld?.world_id === world?.world_id ? playerWorld : null} command={command} busy={busy}/></section>}
      <>
        <section className="scene-section"><div className="section-title horizontal"><div><span className="eyebrow">此时此地</span><h2>小镇正在发生什么</h2></div><span className="muted">{Object.values(world?.characters || {}).filter(p => p.actor_type === 'npc').length} 位镇民 · {world?.event_count || 0} 段经历</span></div>
          <div className="scene-grid">{Object.entries(world?.locations || {}).map(([location, description]) => <Scene key={location} location={location} description={description} world={world} selected={selected} select={setSelected}/>)}</div>
        </section>
        <div className="reading-layout"><section className="story-panel"><div className="section-title horizontal"><div><span className="eyebrow">没有预定结局</span><h2>小镇纪事</h2></div><div className="story-tools"><select aria-label="跟随人物" value={filter} onChange={e => setFilter(e.target.value)}><option value="all">所有人物</option>{Object.keys(world?.characters || {}).map(name => <option key={name}>{name}</option>)}</select><label><input type="checkbox" checked={follow} onChange={e => setFollow(e.target.checked)}/>跟随最新</label></div></div>
          <p className="reading-note">行动与对话来自实际发生的经历；“动机”是角色对自己选择的简短说明。</p>
          {(world?.event_count || 0) > storyWorld.events.length && <button disabled={historyBusy} onClick={earlier}>{historyBusy ? '正在读取……' : '读更早的纪事'}</button>}
          <Story world={storyWorld} filter={filter} follow={follow} selected={selected}/>
        </section><CharacterDetail world={world || {}} selected={selected} select={setSelected}/></div>
      </>
      <footer>NovelWorld · 一段持续发生的生活。<span>上帝视角中的私人资料不会进入其他角色的视角。</span></footer>
    </main>
  </div>
}

createRoot(document.getElementById('root')).render(<App/> )
