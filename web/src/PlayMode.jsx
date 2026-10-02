import React, { useEffect, useState } from 'react'

async function request(path, body) {
  const response = await fetch(path, body ? {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)} : {})
  const value = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(value.detail || value.message || `请求失败：${response.status}`)
  return value
}

export default function PlayMode({ worldId, tick, eventCount, revision }) {
  const [state, setState] = useState(null)
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [partner, setPartner] = useState('')
  const [message, setMessage] = useState('')
  const [destination, setDestination] = useState('')
  const [heldId, setHeldId] = useState('')
  const [containerId, setContainerId] = useState('')
  useEffect(() => {
    setState(null); setPartner(''); setHeldId(''); setDestination(''); setContainerId('')
    setNotice('')
  }, [worldId])
  useEffect(() => {
    let active = true
    let retry
    async function refresh() {
      try {
        const value = await request('/api/play/state')
        if (active && value.world_id === worldId) setState(value)
      } catch {
        // 仅重试只读状态；NPC Tick 持锁时不会排队或重放玩家行动。
        if (active) retry = setTimeout(refresh, 1000)
      }
    }
    if (worldId) refresh()
    return () => { active = false; clearTimeout(retry) }
  }, [worldId, tick, eventCount, revision])

  async function act(action, args = {}) {
    if (!state || state.world_id !== worldId) return
    setBusy(true); setNotice('')
    try {
      const result = await request('/api/play/action', {world_id: state.world_id, action, arguments: args})
      setNotice(result.warning || result.output)
      setMessage('')
      try {
        const next = await request('/api/play/state')
        if (next.world_id === worldId) setState(next)
      } catch (error) { setNotice(`${result.output}（行动已提交，页面刷新失败：${error.message}）`) }
    } catch (error) { setNotice(error.message) }
    finally { setBusy(false) }
  }
  const actors = state?.nearby_characters || []
  const listener = actors.some(actor => actor.name === partner) ? partner : state?.conversation?.partner || actors[0]?.name || ''
  const held = state?.inventory || []
  const selectedHeld = held.find(item => item.id === heldId) || held[0]
  const containers = (state?.visible_objects || []).filter(item => item.affordances.includes('close') && item.state === 'open' && !item.portable)
  async function end() {
    setBusy(true)
    try { setState(await request('/api/play/conversation/end', {world_id: state.world_id})) }
    catch (error) { setNotice(error.message) }
    finally { setBusy(false) }
  }
  return <section className="panel play-panel">
    <h2>Play · {state?.player?.name || '读取玩家…'}</h2>
    {notice && <p className="notice">{notice}</p>}
    {state && <>
      <p>生命 {state.player.hp} · 体力 {state.player.energy} · {state.player.status} · ⌖ {state.player.location} · {state.time}</p>
      <p>{state.location_description}</p>
      <div className="control-actions">
        <select aria-label="移动地点" value={destination || state.locations[0]} onChange={event => setDestination(event.target.value)}>{state.locations.map(place => <option key={place}>{place}</option>)}</select>
        <button disabled={busy} onClick={() => act('move', {location: destination || state.locations[0]})}>移动</button>
        <button disabled={busy} onClick={() => act('inspect')}>观察地点</button>
        <button disabled={busy} onClick={() => act('rest')}>休息</button>
      </div>
      <h3>附近角色 / 当前交流</h3>
      <select aria-label="交谈或交付对象" value={listener} onChange={event => setPartner(event.target.value)}>{actors.map(actor => <option key={actor.name}>{actor.name}</option>)}</select>
      {state.conversation && <>
        <p>{state.conversation.waiting_for_player ? '等待你输入' : '等待对方下一 Tick 回应'} · {state.conversation.partner}</p>
        {state.conversation.messages.map((item, index) => <p className="memory-item" key={index}>{item.speaker}：{item.content}</p>)}
        <button disabled={busy} onClick={end}>结束交流</button>
      </>}
      <form onSubmit={event => {event.preventDefault(); act('talk', {listener, message})}} className="intervention-form">
        <input aria-label="说话内容" value={message} onChange={event => setMessage(event.target.value)} maxLength={2000} placeholder="对附近角色说…" />
        <button disabled={busy || !listener || !message.trim()}>发送</button>
      </form>
      <h3>可见对象</h3>
      <div className="play-objects">{state.visible_objects.map(item => <div className="line-item" key={item.id}>
        <strong>{item.name}</strong> [{item.state}] {' '}
        <button disabled={busy} onClick={() => act('inspect', {object_id: item.id})}>查看</button>{' '}
        {item.portable && !held.some(value => value.id === item.id) && <button disabled={busy} onClick={() => act('take', {object_id: item.id})}>拿取</button>}
        {item.affordances.filter(action => ['open', 'close'].includes(action)).map(action => <button key={action} disabled={busy} onClick={() => act('interact', {object_id: item.id, action})}>{action === 'open' ? '打开' : '关闭'}</button>)}
        {item.affordances.filter(action => ['light', 'extinguish', 'consume'].includes(action)).map(action => <button key={action} disabled={busy} onClick={() => act('use', {object_id: item.id, action})}>{({light: '点亮', extinguish: '熄灭', consume: '使用'})[action]}</button>)}
      </div>)}</div>
      <h3>持有物品</h3>
      <div className="control-actions">
        <select aria-label="持有物品" value={selectedHeld?.id || ''} onChange={event => setHeldId(event.target.value)}>{held.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
        <button disabled={busy || !selectedHeld} onClick={() => act('put', {object_id: selectedHeld.id, location: state.player.location})}>放在当前地点</button>
        <button disabled={busy || !selectedHeld || !listener} onClick={() => act('give', {object_id: selectedHeld.id, receiver: listener})}>交给所选角色</button>
        <select aria-label="打开的容器" value={containers.some(item => item.id === containerId) ? containerId : containers[0]?.id || ''} onChange={event => setContainerId(event.target.value)}>{containers.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
        <button disabled={busy || !selectedHeld || !containers.length} onClick={() => act('put', {object_id: selectedHeld.id, container_id: containers.some(item => item.id === containerId) ? containerId : containers[0].id})}>放入容器</button>
      </div>
      <h3>你感知到的事件</h3>
      {[...state.events].reverse().map(event => <p className="memory-item" key={event.id}>{event.timestamp} · {event.description}</p>)}
      <p className="muted">每次成功行动推进一个 Tick。NPC 在下一 Tick 自主回应；可使用上方运行控制继续世界。</p>
    </>}
  </section>
}
