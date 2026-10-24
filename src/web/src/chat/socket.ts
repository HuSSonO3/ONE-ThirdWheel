import type { components } from '../api/schema'

type S = components['schemas']

export type ServerFrame = { type: string; event_id: number | null; conversation_id: string | null; data: Record<string, unknown> }

export type ChatSocketOptions = {
  /** Latest applied persisted event per conversation, sent with `subscribe` after every (re)connect. */
  cursors: () => Record<string, number | null>
  onFrame: (frame: ServerFrame) => void
  onStatus: (online: boolean) => void
}

/** One socket per tab (contracts/ws-events.md): subscribe with cursors, reconnect with jittered backoff. */
export class ChatSocket {
  private ws?: WebSocket
  private attempt = 0
  private timer?: number
  private closed = false
  private opts: ChatSocketOptions

  constructor(opts: ChatSocketOptions) { this.opts = opts }

  connect() {
    this.closed = false
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}/ws`)
    this.ws = ws
    ws.onopen = () => { this.attempt = 0 }
    ws.onmessage = ev => {
      let frame: ServerFrame
      try { frame = JSON.parse(ev.data) as ServerFrame } catch { return }
      if (frame.type === 'hello') {
        this.opts.onStatus(true)
        ws.send(JSON.stringify({ type: 'subscribe', conversations: this.opts.cursors() }))
      }
      this.opts.onFrame(frame)
    }
    ws.onclose = ev => {
      this.opts.onStatus(false)
      if (this.closed || ev.code === 4401 || ev.code === 4403) return
      const delay = Math.min(30_000, 500 * 2 ** this.attempt++) * (0.75 + Math.random() * 0.5)
      this.timer = window.setTimeout(() => this.connect(), delay)
    }
  }

  sendTyping(conversationId: string, parentId: string | null = null) {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify({ type: 'typing', conversation_id: conversationId, parent_id: parentId }))
  }

  close() {
    this.closed = true
    window.clearTimeout(this.timer)
    this.ws?.close()
  }
}

export type MessageFrame = { message: S['Message'] }
