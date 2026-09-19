// shot.mjs — 通过 CDP 直连 headless Edge 截图（不依赖 puppeteer/playwright）
// 用法: node shot.mjs <url> <out.png> [w] [h] [waitMs]
const url = process.argv[2]
const out = process.argv[3]
const W = parseInt(process.argv[4] || '1600', 10)
const H = parseInt(process.argv[5] || '1000', 10)
const waitMs = parseInt(process.argv[6] || '7000', 10)

const PORT = process.env.CDP_PORT || '9222'
const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()
const page = list.find((t) => t.type === 'page')
if (!page) { console.error('no page target'); process.exit(1) }

const ws = new WebSocket(page.webSocketDebuggerUrl)
let id = 0
const pending = new Map()
const send = (method, params = {}) => new Promise((res, rej) => {
  const i = ++id
  pending.set(i, { res, rej })
  ws.send(JSON.stringify({ id: i, method, params }))
})
await new Promise((r) => ws.addEventListener('open', r))
ws.addEventListener('message', (ev) => {
  const m = JSON.parse(ev.data)
  if (m.id && pending.has(m.id)) {
    const p = pending.get(m.id); pending.delete(m.id)
    m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result)
  }
})
const logs = []
await send('Runtime.enable')
await send('Log.enable')
ws.addEventListener('message', (ev) => {
  const m = JSON.parse(ev.data)
  if (m.method === 'Runtime.consoleAPICalled') {
    logs.push('console.' + m.params.type + ': ' + m.params.args.map(a => a.value ?? a.description ?? '').join(' '))
  }
  if (m.method === 'Log.entryAdded') logs.push('log.' + m.params.entry.level + ': ' + m.params.entry.text)
})
await send('Page.enable')
await send('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: 1, mobile: false })
await send('Page.navigate', { url })
await new Promise((r) => setTimeout(r, waitMs))
const shot = await send('Page.captureScreenshot', { format: 'png' })
const fs = await import('node:fs')
fs.writeFileSync(out, Buffer.from(shot.data, 'base64'))
console.log('WROTE', out)
if (logs.length) console.log('--- browser logs ---\n' + logs.slice(-25).join('\n'))
process.exit(0)
