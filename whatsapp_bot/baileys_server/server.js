/**
 * ORVA Baileys WhatsApp Server
 * Lightweight Node.js/Express wrapper around @whiskeysockets/baileys.
 * Runs headlessly on Linux — no browser required.
 * Listens on http://127.0.0.1:3001 (localhost only).
 */

const express = require('express')
const {
  makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
} = require('@whiskeysockets/baileys')
const { Boom } = require('@hapi/boom')
const QRCode = require('qrcode')
const ffmpeg = require('fluent-ffmpeg')
const fs = require('fs')
const path = require('path')

const app = express()
app.use(express.json())

const PORT = parseInt(process.env.WA_PORT || '3001', 10)
const AUTH_DIR = process.env.WA_AUTH_DIR || path.join(__dirname, 'auth')

// --- State ---
let sock = null
let isConnected = false
let latestQR = null
let connectedPhone = null

// --- Connection ---
async function connectWA() {
  fs.mkdirSync(AUTH_DIR, { recursive: true })

  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR)
  const { version } = await fetchLatestBaileysVersion()

  sock = makeWASocket({
    version,
    auth: state,
    printQRInTerminal: true,
    browser: ['ORVA', 'Chrome', '1.0'],
    generateHighQualityLinkPreview: false,
  })

  sock.ev.on('creds.update', saveCreds)

  sock.ev.on('connection.update', async (update) => {
    const { connection, lastDisconnect, qr } = update

    if (qr) {
      latestQR = qr
      isConnected = false
      console.log('[QR] New QR code generated — scan in ORVA WhatsApp page')
    }

    if (connection === 'close') {
      isConnected = false
      latestQR = null
      connectedPhone = null
      const statusCode = new Boom(lastDisconnect?.error)?.output?.statusCode
      const shouldReconnect = statusCode !== DisconnectReason.loggedOut
      console.log(`[DISCONNECT] Code: ${statusCode}, reconnect: ${shouldReconnect}`)

      if (shouldReconnect) {
        console.log('[RECONNECT] Retrying in 3s...')
        setTimeout(connectWA, 3000)
      } else {
        console.log('[LOGOUT] WhatsApp logged out — clearing auth state and restarting QR flow')
        try { fs.rmSync(AUTH_DIR, { recursive: true, force: true }) } catch (_) {}
        fs.mkdirSync(AUTH_DIR, { recursive: true })
        setTimeout(connectWA, 1000)
      }
    }

    if (connection === 'open') {
      isConnected = true
      latestQR = null
      connectedPhone = sock.user?.id?.split(':')[0] || null
      console.log(`[CONNECTED] Phone: ${connectedPhone}`)
    }
  })
}

connectWA().catch((err) => {
  console.error('[FATAL] connectWA failed on startup:', err)
  process.exit(1)
})

// --- Endpoints ---

// GET /status — connection state
app.get('/status', (req, res) => {
  res.json({
    connected: isConnected,
    qr_available: latestQR !== null,
    phone: connectedPhone,
  })
})

// GET /qr — returns QR as PNG image
app.get('/qr', async (req, res) => {
  if (!latestQR) {
    return res.status(404).json({
      error: 'No QR available. Already connected, or QR not yet generated.',
    })
  }
  try {
    const pngBuffer = await QRCode.toBuffer(latestQR, { width: 300, margin: 2 })
    res.setHeader('Content-Type', 'image/png')
    res.send(pngBuffer)
  } catch (err) {
    res.status(500).json({ error: `QR render failed: ${err.message}` })
  }
})

// POST /send/text — send a text message
// Body: { phone: "971XXXXXXXXX", message: "..." }
app.post('/send/text', async (req, res) => {
  if (!isConnected || !sock) {
    return res.status(503).json({ success: false, error: 'WhatsApp not connected — scan QR first' })
  }
  const { phone, message } = req.body
  if (!phone || !message) {
    return res.status(400).json({ success: false, error: 'phone and message are required' })
  }
  try {
    const jid = `${phone}@s.whatsapp.net`
    await sock.sendMessage(jid, { text: message })
    console.log(`[SENT] Text → ${phone}`)
    res.json({ success: true })
  } catch (err) {
    const errMsg = err.message || ''
    console.error(`[FAIL] Text → ${phone}: ${errMsg}`)
    if (errMsg.includes('not registered') || errMsg.includes('not on WhatsApp')) {
      res.json({ success: false, error: 'not registered' })
    } else {
      res.status(500).json({ success: false, error: `send failed: ${errMsg}` })
    }
  }
})

// POST /send/voice — send PTT voice note (any audio format, converted to Opus OGG via ffmpeg)
// Body: { phone: "971XXXXXXXXX", audio_path: "/absolute/path/to/audio.mp3" }
app.post('/send/voice', async (req, res) => {
  if (!isConnected || !sock) {
    return res.status(503).json({ success: false, error: 'WhatsApp not connected — scan QR first' })
  }
  const { phone, audio_path } = req.body
  if (!phone || !audio_path) {
    return res.status(400).json({ success: false, error: 'phone and audio_path are required' })
  }
  if (!fs.existsSync(audio_path)) {
    return res.status(400).json({ success: false, error: `audio_path not found: ${audio_path}` })
  }

  const tmpOgg = `/tmp/wa_voice_${Date.now()}_${Math.random().toString(36).slice(2)}.ogg`

  // Step 1: Convert to Opus OGG (required format for WhatsApp PTT)
  try {
    await new Promise((resolve, reject) => {
      ffmpeg(audio_path)
        .audioCodec('libopus')
        .audioBitrate('64k')
        .format('ogg')
        .on('error', (err) => reject(new Error(`ffmpeg: ${err.message}`)))
        .on('end', resolve)
        .save(tmpOgg)
    })
  } catch (err) {
    console.error(`[FAIL] ffmpeg conversion for ${phone}: ${err.message}`)
    // HTTP 500 so Python bot.py returns 'failed' and the queue manager retries
    return res.status(500).json({
      success: false,
      error: `ffmpeg conversion failed: ${err.message}`,
    })
  }

  // Step 2: Send as PTT
  try {
    const buf = fs.readFileSync(tmpOgg)
    try { fs.unlinkSync(tmpOgg) } catch (_) {}
    const jid = `${phone}@s.whatsapp.net`
    await sock.sendMessage(jid, {
      audio: buf,
      mimetype: 'audio/ogg; codecs=opus',
      ptt: true,
    })
    console.log(`[SENT] Voice → ${phone}`)
    res.json({ success: true })
  } catch (err) {
    try { fs.unlinkSync(tmpOgg) } catch (_) {}
    console.error(`[FAIL] Voice send → ${phone}: ${err.message}`)
    res.status(500).json({ success: false, error: `send failed: ${err.message}` })
  }
})

// --- Start ---
app.listen(PORT, '127.0.0.1', () => {
  console.log(`[START] ORVA Baileys server on http://127.0.0.1:${PORT}`)
})
