import React, {useState} from 'react'
import {clock} from './api.js'

export default function PlayMode({world, command, busy}) {
  const [name, setName] = useState('旅人')
  const [location, setLocation] = useState('')
  const [target, setTarget] = useState('')
  const [message, setMessage] = useState('')
  const [activity, setActivity] = useState('')
  const [object, setObject] = useState('')
  if (!world) return <p className="muted">正在打开小镇……</p>
  const player = world.characters?.[world.player_name]
  const disabled = busy || world.player_pending
  const places = Object.keys(world.locations || {})
  async function submit(action, args={}) {
    try {await command('/api/play/action', {world_id: world.world_id, action, arguments: args}); setMessage('')}
    catch (_) {}
  }
  if (!player) return <section className="play-panel"><span className="eyebrow">从一声问候开始</span><h2>成为小镇里的旅人</h2><p>你会遇见现场的人。对方怎样回应、是否接受邀请，由他们自己决定。</p><div className="form-row"><input aria-label="旅人姓名" value={name} maxLength="40" onChange={e => setName(e.target.value)}/><select aria-label="起始地点" value={location || places[0]} onChange={e => setLocation(e.target.value)}>{places.map(p => <option key={p}>{p}</option>)}</select><button className="primary" disabled={disabled || !name.trim()} onClick={() => command('/api/play/join', {world_id: world.world_id, name, location: location || places[0]}).catch(() => {})}>走进小镇</button></div></section>
  const session = world.conversations?.find(s => s.participants.includes(player.name))
  const people = Object.keys(world.characters || {}).filter(n => n !== player.name)
  const activities = Object.entries(world.activities || {}).filter(([, a]) => a.locations.includes(player.location) && (!a.roles.length || a.roles.includes(player.role)))
  const objects = Object.entries(world.objects || {})
  return <div className="play-layout"><section className="play-panel"><span className="eyebrow">在同一个世界里参与</span><h2>{player.name} · {player.location}</h2><p>{world.locations[player.location]}</p><p>附近：{people.join('、') || '暂时没有其他人'}。{player.activity ? `你正在${player.activity.name}，${clock(player.activity.until)}结束。` : '你此刻空闲。'}</p>
    {world.player_pending && <p role="status">行动已接收，等待当前轮次结束后执行。</p>}
    {player.activity && <button disabled={disabled} onClick={() => submit('stop_activity')}>停下当前活动</button>}
    {(world.invitations || []).filter(i => i.to === player.name).map(i => <div className="invitation-card" key={i.id}><b>{i.from}想与你聊聊</b><blockquote>{i.message}</blockquote><button disabled={disabled} onClick={() => submit('respond_invitation', {invitation_id: i.id, accept: true})}>接受</button><button disabled={disabled} onClick={() => submit('respond_invitation', {invitation_id: i.id, accept: false})}>婉拒</button></div>)}
    {session ? <div className="play-conversation"><h3>与{session.participants.find(n => n !== player.name)}的交谈</h3>{session.messages.map(m => <p key={m.event_id}><b>{m.speaker}</b>：{m.message}</p>)}<textarea aria-label="说给对方的话" value={message} onChange={e => setMessage(e.target.value)} maxLength="1000" placeholder={session.next_speaker === player.name ? '说说你的想法……' : world.running ? '等待对方自主回应……' : '运行下一轮，让对方回应。'}/><div className="form-row"><button className="primary" disabled={disabled || session.next_speaker !== player.name || !message.trim()} onClick={() => submit('say', {message})}>说给对方听</button><button disabled={disabled} onClick={() => submit('leave_conversation')}>结束交谈</button></div></div> : <>
      <div className="person-section"><h3>去别处走走</h3><div className="form-row"><select aria-label="前往地点" value={location || places[0]} onChange={e => setLocation(e.target.value)}>{places.map(p => <option key={p}>{p}</option>)}</select><button disabled={disabled || !!player.activity || (location || places[0]) === player.location} onClick={() => submit('move', {location: location || places[0]})}>前往</button></div></div>
      <div className="person-section"><h3>向附近的人问候</h3><select aria-label="邀请的人" value={people.includes(target) ? target : people[0] || ''} onChange={e => setTarget(e.target.value)}>{people.map(p => <option key={p}>{p}</option>)}</select><textarea aria-label="邀请内容" value={message} onChange={e => setMessage(e.target.value)} maxLength="600" placeholder="你想和他聊什么？"/><button disabled={disabled || !!player.activity || !people.length || !message.trim()} onClick={() => submit('invite', {target: people.includes(target) ? target : people[0], message})}>邀请交谈</button></div>
      <div className="person-section"><h3>在这里做些什么</h3><div className="form-row"><select aria-label="活动" value={activities.some(([id]) => id === activity) ? activity : activities[0]?.[0] || ''} onChange={e => setActivity(e.target.value)}>{activities.map(([id, a]) => <option key={id} value={id}>{a.name} · {a.duration}分钟</option>)}</select><button disabled={disabled || !!player.activity || !activities.length} onClick={() => submit('start_activity', {activity_id: activities.some(([id]) => id === activity) ? activity : activities[0][0]})}>开始</button><button disabled={disabled || !!player.activity} onClick={() => submit('wait')}>静候片刻</button></div></div>
    </>}
    {!!objects.length && <div className="person-section"><h3>看看现场的东西</h3><div className="form-row"><select aria-label="查看对象" value={objects.some(([id]) => id === object) ? object : objects[0][0]} onChange={e => setObject(e.target.value)}>{objects.map(([id, o]) => <option key={id} value={id}>{o.name}</option>)}</select><button disabled={disabled} onClick={() => submit('inspect', {object_id: objects.some(([id]) => id === object) ? object : objects[0][0]})}>查看</button></div></div>}
    {(world.invitations || []).filter(i => i.from === player.name).map(i => <p className="muted" key={i.id}>你向{i.to}发出了邀请，等待他自主回应。</p>)}
  </section><section className="play-panel"><span className="eyebrow">亲眼所见，亲耳所闻</span><h2>你的经历</h2>{[...(world.events || [])].reverse().map(e => <article className="player-event" key={e.id}><small>{clock(e.minute)} · {e.location}</small><p>{e.description}</p></article>)}{!world.events?.length && <p className="muted">先向一个人问候吧。</p>}</section></div>
}
