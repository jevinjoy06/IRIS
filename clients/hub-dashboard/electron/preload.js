const { contextBridge } = require('electron')
const fs = require('fs')
const path = require('path')

function loadConfig() {
  const configPath = path.join(__dirname, '..', 'config.json')
  if (fs.existsSync(configPath)) {
    try {
      return JSON.parse(fs.readFileSync(configPath, 'utf8'))
    } catch {
      return {}
    }
  }
  return {}
}

const config = loadConfig()

contextBridge.exposeInMainWorld('irisConfig', {
  hubWs: config.hub_ws || 'ws://localhost:7865/ws',
  hubHttp: config.hub_http || 'http://localhost:7865',
  pollIntervalMs: config.poll_interval_ms || 2000,
})
