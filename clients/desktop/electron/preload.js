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
  hubUrl: config.hub_url || 'ws://localhost:7865/ws',
})
