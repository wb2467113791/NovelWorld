import React, {useEffect, useState} from 'react'
import {request} from './api.js'

export default function WorldSetup({running, activeWorldId, command, busy}) {
  const [worlds, setWorlds] = useState([])
  const [draft, setDraft] = useState('')
  const [error, setError] = useState('')
  const [title, setTitle] = useState('')
  const [localBusy, setLocalBusy] = useState(false)
  useEffect(() => {
    let active = true
    request('/api/worlds').then(v => {if (active) setWorlds(v.worlds)}).catch(e => {if (active) setError(e.message)})
    request('/api/world-template/default').then(v => {if (active) setDraft(JSON.stringify(v, null, 2))}).catch(e => {if (active) setError(e.message)})
    return () => {active = false}
  }, [activeWorldId])
  async function create() {
    setLocalBusy(true); setError('')
    try {
      const template = JSON.parse(draft)
      if (title.trim()) template.title = title.trim()
      const result = await request('/api/worlds', template)
      await command(`/api/worlds/${result.world_id}/activate`)
    } catch(e) {setError(e.message)}
    finally {setLocalBusy(false)}
  }
  async function download(id) {
    try {
      const data = await request(`/api/worlds/${id}/export`)
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'}))
      const a = document.createElement('a'); a.href = url; a.download = `novelworld-${id}.json`; a.click(); URL.revokeObjectURL(url)
    } catch(e) {setError(e.message)}
  }
  return <section className="setup-panel"><span className="eyebrow">新的开篇</span><h2>世界与开局</h2><p>创建一个独立世界。修改人物、地点和活动条件，让他们自己写出之后的故事。</p>
    <div className="form-row"><input aria-label="新世界标题" placeholder="给这个世界起个名字（可选）" value={title} onChange={e => setTitle(e.target.value)} maxLength="80"/><button className="primary" disabled={running || busy || localBusy || !draft} onClick={create}>{localBusy ? '正在打开新世界…' : '创建并进入新世界'}</button></div>
    <details><summary>编辑开局设定</summary><textarea aria-label="世界开局JSON" className="template-editor" value={draft} onChange={e => setDraft(e.target.value)}/></details>
    {error && <p role="alert" className="error-text">{error}</p>}
    <div className="saved-worlds">{worlds.map(w => <div key={w.world_id}><span><b>{w.title}</b><small>{w.version === 3 ? '社会沙盒' : '旧版存档 · 保留供导出'}</small></span><button onClick={() => download(w.world_id)}>导出</button><button disabled={running || busy || localBusy || w.version !== 3 || w.world_id === activeWorldId} onClick={() => command(`/api/worlds/${w.world_id}/activate`).catch(() => {})}>{w.world_id === activeWorldId ? '当前世界' : '进入'}</button></div>)}</div>
  </section>
}
