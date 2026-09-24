import React, { useEffect, useMemo, useState } from 'react'

const STORAGE_KEY = 'novelworld-opening-templates-v1'

function readSavedTemplates() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
    return Array.isArray(saved)
      ? saved.filter(item => item && typeof item.name === 'string' && typeof item.draft === 'string')
      : []
  } catch {
    return []
  }
}

function PreviewList({ title, values }) {
  return <div className="opening-preview-list"><b>{title}</b><span>{Array.isArray(values) && values.length ? values.join('、') : '暂无'}</span></div>
}

export default function WorldSetup({ running, activeWorldId, onActivated }) {
  const [draft, setDraft] = useState('')
  const [draftName, setDraftName] = useState('')
  const [savedTemplates, setSavedTemplates] = useState(readSavedTemplates)
  const [message, setMessage] = useState('')
  const [createdId, setCreatedId] = useState('')
  const [worldIds, setWorldIds] = useState([])
  const [busy, setBusy] = useState(false)

  async function loadDefault() {
    setBusy(true)
    setMessage('')
    try {
      const response = await fetch('/api/world-template/default')
      if (!response.ok) throw new Error(`读取默认模板失败：${response.status}`)
      setDraft(JSON.stringify(await response.json(), null, 2))
      setDraftName('')
      setCreatedId('')
    } catch (error) {
      setMessage(error.message)
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => { loadDefault() }, [])

  async function refreshWorlds() {
    try {
      const response = await fetch('/api/worlds')
      if (!response.ok) throw new Error(`读取世界列表失败：${response.status}`)
      const result = await response.json()
      setWorldIds(result.world_ids || [])
    } catch (error) {
      setMessage(error.message)
    }
  }

  useEffect(() => { refreshWorlds() }, [activeWorldId])

  const preview = useMemo(() => {
    if (!draft) return { error: '正在读取默认模板' }
    try {
      const template = JSON.parse(draft)
      if (!template || typeof template.time !== 'string'
          || !Array.isArray(template.locations) || !template.locations.every(item => typeof item === 'string')
          || !template.characters || typeof template.characters !== 'object' || Array.isArray(template.characters)) {
        return { error: '模板需要 locations 和 characters；完整规则由服务器在创建时校验' }
      }
      if (Object.values(template.characters).some(character => !character || typeof character !== 'object'
          || ['role', 'background', 'personality', 'location'].some(field => typeof character[field] !== 'string')
          || typeof character.energy !== 'number')) {
        return { error: '角色身份、背景、性格和地点需要填写文字；体力需要填写数字' }
      }
      if (template.inspectables && Object.values(template.inspectables).some(value => typeof value !== 'string')) {
        return { error: '场景描述需要填写文字' }
      }
      if (Array.isArray(template.lore) && template.lore.some(entry => !entry || typeof entry !== 'object'
          || ['category', 'audience', 'text'].some(field => typeof entry[field] !== 'string'))) {
        return { error: '世界设定需要类别、可见者和文字内容' }
      }
      return { template }
    } catch (error) {
      return { error: `JSON 格式错误：${error.message}` }
    }
  }, [draft])

  function saveDraft() {
    const name = draftName.trim()
    if (!name) return setMessage('请先填写模板名称')
    if (!preview.template) return setMessage(preview.error)
    const next = [...savedTemplates.filter(item => item.name !== name), { name, draft }]
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
      setSavedTemplates(next)
      setMessage(`已在当前浏览器保存模板“${name}”`)
    } catch {
      setMessage('浏览器无法保存模板，请复制编辑框中的内容自行保留')
    }
  }

  function deleteDraft(name) {
    const next = savedTemplates.filter(item => item.name !== name)
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
      setSavedTemplates(next)
      setMessage(`已删除模板“${name}”`)
    } catch {
      setMessage('浏览器无法更新已存模板')
    }
  }

  async function createWorld() {
    if (!preview.template || running) return
    setBusy(true)
    setMessage('')
    setCreatedId('')
    try {
      const response = await fetch('/api/worlds', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(preview.template),
      })
      const result = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(result.detail || `创建失败：${response.status}`)
      setCreatedId(result.world_id)
      await refreshWorlds()
      setMessage('新世界已保存。点击下方“切换到此世界”后才会开始观看它。')
    } catch (error) {
      setMessage(error.message)
    } finally {
      setBusy(false)
    }
  }

  async function activateWorld(worldId) {
    if (running || busy || worldId === activeWorldId) return
    setBusy(true)
    setMessage('')
    try {
      const response = await fetch(`/api/worlds/${encodeURIComponent(worldId)}/activate`, { method: 'POST' })
      const result = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(result.detail || `切换失败：${response.status}`)
      await onActivated()
      setMessage(`已切换到世界 ${worldId}`)
    } catch (error) {
      setMessage(error.message)
    } finally {
      setBusy(false)
    }
  }

  const template = preview.template
  const characters = Object.entries(template?.characters || {})
  return <section className="panel opening-panel" id="setup">
    <div className="section-heading"><div><div className="panel-kicker">WORLD SETUP</div><h2>开局工坊</h2></div><span className="view-tag">创建新世界前编辑</span></div>
    <p className="opening-note">这里设置世界的起点。NPC 的秘密、已知事实与世界设定分开保存；运行后由角色自己决定如何行动。编辑和预览不会调用模型。</p>
    <div className="opening-grid">
      <div className="opening-editor">
        <label htmlFor="opening-json">开局模板 JSON</label>
        <textarea id="opening-json" spellCheck="false" value={draft} onChange={event => { setDraft(event.target.value); setCreatedId('') }} aria-invalid={Boolean(preview.error)} />
        <p className="opening-hint">可修改角色人设、目标、秘密、已知事实、关系、地点、体力、物品，以及世界时间、场景、线索和 lore 世界设定。创建时服务器会校验引用。</p>
        <div className="opening-actions">
          <button type="button" onClick={loadDefault} disabled={busy}>恢复默认模板</button>
          <input aria-label="模板名称" placeholder="模板名称" value={draftName} onChange={event => setDraftName(event.target.value)} />
          <button type="button" onClick={saveDraft} disabled={busy || !template}>保存到本浏览器</button>
        </div>
        {savedTemplates.length > 0 && <div className="opening-saved"><b>本浏览器已存模板</b>{savedTemplates.map(item => <div key={item.name}><button type="button" onClick={() => { setDraft(item.draft); setDraftName(item.name); setCreatedId(''); setMessage(`已载入模板“${item.name}”`) }}>{item.name}</button><button type="button" aria-label={`删除模板${item.name}`} onClick={() => deleteDraft(item.name)}>删除</button></div>)}</div>}
      </div>
      <div className="opening-preview">
        <h3>创建前预览</h3>
        {preview.error ? <p className="opening-error">{preview.error}</p> : <>
          <p>开局时间：{template.time} · {template.locations.length} 个地点 · {characters.length} 名 NPC</p>
          {characters.map(([name, raw]) => {
            const character = raw && typeof raw === 'object' ? raw : {}
            return <article className="opening-character" key={name}>
              <strong>{name}<small>{character.role || '未设身份'} · {character.location || '未设地点'} · 体力 {character.energy ?? '未设'}</small></strong>
              <p>{character.background || '未设背景'}</p><p>性格：{character.personality || '未设'}</p>
              <PreviewList title="目标" values={character.goals} />
              <PreviewList title="已知事实" values={character.known_facts} />
              <PreviewList title="自己的秘密（仅作者预览）" values={character.secrets} />
              <PreviewList title="关系" values={Object.entries(character.relationships || {}).map(([target, score]) => `${target} ${score}`)} />
              <PreviewList title="物品" values={character.items} />
            </article>
          })}
          <h3>场景与初始线索</h3>
          {template.locations.map(location => <article className="opening-location" key={location}>
            <strong>{location}</strong><p>{template.inspectables?.[location] || '缺少场景描述'}</p>
            <PreviewList title="可调查对象" values={Object.entries(template.inspectable_objects?.[location] || {}).map(([name, clue]) => `${name}：${clue}`)} />
          </article>)}
          <h3>世界设定与可见范围</h3>
          {(Array.isArray(template.lore) ? template.lore : []).map((raw, index) => <article className="opening-location" key={raw?.id || index}>
            <strong>{raw?.category || '未设类别'} · {raw?.audience === 'public' ? '所有角色可知' : `仅 ${raw?.audience || '未设角色'} 可知`}</strong>
            <p>{raw?.text || '未设内容'}</p>
          </article>)}
        </>}
      </div>
    </div>
    <div className="opening-footer">
      <button type="button" className="primary-button" onClick={createWorld} disabled={busy || !template || running}>创建新世界</button>
      <span>{running ? '请先暂停当前世界，再创建或切换世界。' : '创建只保存新世界；切换后才会改变当前观看的世界。'}</span>
    </div>
    {message && <p className="opening-message" role="status">{message}</p>}
    {createdId && <p className="opening-created">新世界 ID：<code>{createdId}</code></p>}
    <div className="opening-worlds"><h3>已保存的世界</h3>
      {worldIds.length ? worldIds.map(worldId => <div key={worldId}>
        <code>{worldId}</code>
        {worldId === activeWorldId ? <span>当前世界</span> : <button type="button" disabled={running || busy} onClick={() => activateWorld(worldId)}>切换到此世界</button>}
      </div>) : <p>暂无可切换的世界</p>}
    </div>
  </section>
}
