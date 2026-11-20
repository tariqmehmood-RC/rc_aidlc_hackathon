// Minimal stdio JSON-RPC client for @playwright/mcp (newline-delimited JSON).
import { spawn } from 'node:child_process'

export function startServer(args) {
  const proc = spawn('npx', ['-y', '@playwright/mcp@0.0.86', ...args], {
    stdio: ['pipe', 'pipe', 'inherit'],
  })
  let buffer = ''
  let nextId = 1
  const pending = new Map()
  proc.stdout.on('data', (chunk) => {
    buffer += chunk
    let nl
    while ((nl = buffer.indexOf('\n')) >= 0) {
      const line = buffer.slice(0, nl).trim()
      buffer = buffer.slice(nl + 1)
      if (!line) continue
      const msg = JSON.parse(line)
      if (msg.id !== undefined && pending.has(msg.id)) {
        pending.get(msg.id)(msg)
        pending.delete(msg.id)
      }
    }
  })
  function request(method, params) {
    const id = nextId++
    proc.stdin.write(JSON.stringify({ jsonrpc: '2.0', id, method, params }) + '\n')
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error(`timeout: ${method}`)), 60000)
      pending.set(id, (msg) => {
        clearTimeout(timer)
        if (msg.error) reject(new Error(JSON.stringify(msg.error)))
        else resolve(msg.result)
      })
    })
  }
  function notify(method, params) {
    proc.stdin.write(JSON.stringify({ jsonrpc: '2.0', method, params }) + '\n')
  }
  async function init() {
    await request('initialize', {
      protocolVersion: '2025-06-18',
      capabilities: {},
      clientInfo: { name: 'lab2-check', version: '1.0.0' },
    })
    notify('notifications/initialized', {})
  }
  async function call(name, args = {}) {
    const result = await request('tools/call', { name, arguments: args })
    const text = (result.content ?? [])
      .filter((c) => c.type === 'text')
      .map((c) => c.text)
      .join('\n')
    return { text, isError: result.isError === true }
  }
  return { proc, request, init, call }
}
