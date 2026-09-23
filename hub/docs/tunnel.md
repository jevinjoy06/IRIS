# Cloudflare Tunnel Setup

Exposes the IRIS Hub to your other devices (phone, laptops) without port forwarding or a VPN.

---

## 1. Install cloudflared

**Windows (winget):**
```powershell
winget install Cloudflare.cloudflared
```

**macOS:**
```bash
brew install cloudflare/cloudflare/cloudflared
```

---

## 2. Authenticate

```bash
cloudflared tunnel login
```

This opens a browser window. Authorize your Cloudflare account. A certificate is saved to `~/.cloudflared/cert.pem`.

---

## 3. Create a named tunnel

```bash
cloudflared tunnel create iris-hub
```

Note the **Tunnel ID** printed (e.g. `a1b2c3d4-...`). A credentials file is saved to `~/.cloudflared/<tunnel-id>.json`.

---

## 4. Configure the tunnel

Create `~/.cloudflared/config.yml`:

```yaml
tunnel: <TUNNEL_ID>
credentials-file: /Users/<you>/.cloudflared/<TUNNEL_ID>.json

ingress:
  - hostname: iris.<your-domain>.com
    service: http://localhost:7865
  - service: http_status:404
```

Replace `<TUNNEL_ID>` with the ID from step 3, and `iris.<your-domain>.com` with a hostname on a domain you control in Cloudflare DNS.

---

## 5. Route DNS

```bash
cloudflared tunnel route dns iris-hub iris.<your-domain>.com
```

This creates a CNAME record pointing to your tunnel.

---

## 6. Run the tunnel

```bash
cloudflared tunnel run iris-hub
```

Your hub is now reachable at `https://iris.<your-domain>.com` from any device.

---

## 7. Run as a Windows service (optional)

```powershell
# Run as Administrator
cloudflared service install
```

This installs cloudflared as a Windows service that starts automatically on boot. It reads `C:\Windows\System32\config\systemprofile\.cloudflared\config.yml` — copy your config there.

---

## Security notes

- The tunnel is authenticated by Cloudflare — no credentials are exposed.
- The WebSocket endpoint (`/ws`) carries your full conversation stream. Consider adding Cloudflare Access in front of the hostname to require login before any device can connect.
- Cloudflare Access: zero-trust → Applications → Add → Self-hosted → configure your hostname → require email/OTP or GitHub OAuth.
