# Saul Goodman Deployment (Vercel + GCE VM)

This doc reflects the **current working production setup**:

- `Taxclarity/frontend` on **Vercel**
- `Taxclarity/` backend stack on **one GCE VM**
- **GitHub Actions** auto-deploys backend on every push to `main`
- **DuckDNS + Let’s Encrypt** for free TLS

## 1. Create the VM (Final Choice)

Use Google Compute Engine:

- Region: `us-central1`
- Machine type: `e2-standard-2` (this is required; `e2-micro` was too slow)
- Boot disk: `Ubuntu 22.04 LTS`
- Disk: `30 GB standard persistent disk`
- Enable: `Allow HTTP traffic`
- Enable: `Allow HTTPS traffic`

Reserve a static external IP if you want stable DNS.

## 2. DuckDNS Hostname

We used:

- `saul-backend.duckdns.org`

Update the IP:

```bash
PUBLIC_IP=$(curl -s https://ifconfig.me)
curl "https://www.duckdns.org/update?domains=saul-backend&token=<YOUR_DUCKDNS_TOKEN>&ip=$PUBLIC_IP"
```

Auto-refresh (cron):

```bash
sudo mkdir -p /opt/duckdns
sudo tee /opt/duckdns/duck.sh > /dev/null << 'EOF'
#!/bin/sh
PUBLIC_IP=$(curl -s https://ifconfig.me)
curl -s "https://www.duckdns.org/update?domains=saul-backend&token=<YOUR_DUCKDNS_TOKEN>&ip=$PUBLIC_IP" >/opt/duckdns/duck.log
EOF
sudo chmod 700 /opt/duckdns/duck.sh
sudo bash -c '(crontab -l 2>/dev/null; echo "*/5 * * * * /opt/duckdns/duck.sh >/dev/null 2>&1") | crontab -'
```

## 3. Install Packages on the VM

```bash
sudo apt update
sudo apt install -y git nginx certbot python3-certbot-nginx python3-venv build-essential rsync lsof
```

## 4. Create App Directories

```bash
sudo useradd -m -s /bin/bash saul || true
sudo mkdir -p /opt/saulgoodman
sudo chown -R saul:saul /opt/saulgoodman
```

## 5. Clone Repo + Create Venv

```bash
sudo su - saul
cd /opt/saulgoodman
git clone <YOUR_GITHUB_REPO_URL> repo
python3 -m venv /opt/saulgoodman/venv
source /opt/saulgoodman/venv/bin/activate
pip install --upgrade pip
pip install -r /opt/saulgoodman/repo/Taxclarity/requirements.txt
```

## 6. Backend `.env`

Create:

```
/opt/saulgoodman/repo/Taxclarity/.env
```

Example:

```bash
GOOGLE_API_KEY=...
ROOT_AGENT_URL=http://localhost:8000
GRAPH_API_URL=http://localhost:8006
```

## 7. Nginx + SSL (Working Config)

We use a dedicated HTTPS vhost to ensure `/ws` is always present:

```bash
cat > /tmp/saulgoodman.conf << 'EOF'
server {
    listen 80;
    server_name saul-backend.duckdns.org;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name saul-backend.duckdns.org;

    ssl_certificate /etc/letsencrypt/live/saul-backend.duckdns.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/saul-backend.duckdns.org/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    client_max_body_size 50m;

    location /ws {
        proxy_pass http://127.0.0.1:8003/ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    location /api/graph/ {
        proxy_pass http://127.0.0.1:8006/api/graph/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/documents/ {
        proxy_pass http://127.0.0.1:8006/api/documents/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/agents/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /health {
        default_type application/json;
        return 200 '{"status":"ok"}';
    }
}
EOF

sudo cp /tmp/saulgoodman.conf /etc/nginx/sites-available/saulgoodman
sudo ln -sf /etc/nginx/sites-available/saulgoodman /etc/nginx/sites-enabled/saulgoodman
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

SSL:

```bash
sudo certbot --nginx -d saul-backend.duckdns.org -m <EMAIL> --agree-tos --non-interactive
```

## 8. Systemd Service (Final Working Version)

We run the service as **sidharth** because the repo is owned by `sidharth` (GitHub Actions deploy user).

```bash
sudo cp /opt/saulgoodman/repo/Taxclarity/deploy/systemd/saulgoodman-backend.service /etc/systemd/system/saulgoodman-backend.service
sudo sed -i 's/^User=.*/User=sidharth/' /etc/systemd/system/saulgoodman-backend.service
sudo sed -i '/^ExecStart=/i ExecStartPre=/bin/rm -f /opt/saulgoodman/repo/Taxclarity/.pids' /etc/systemd/system/saulgoodman-backend.service
sudo systemctl daemon-reload
sudo systemctl enable saulgoodman-backend
sudo systemctl restart saulgoodman-backend
sudo systemctl status saulgoodman-backend --no-pager
```

## 9. GitHub Actions Auto-Deploy

Repo workflow:

- `.github/workflows/deploy-backend-vm.yml`

Secrets:

- `VM_HOST` = `saul-backend.duckdns.org`
- `VM_USER` = `sidharth`
- `VM_SSH_KEY` = contents of `~/.ssh/saul_vm_deploy`

The workflow:

- runs `git fetch` + `git reset` on the VM
- installs deps
- restarts systemd

Known issue solved:

- `fatal: detected dubious ownership` fixed by setting `safe.directory`
- `Permission denied` fixed by repo ownership and running systemd as `sidharth`

## 10. Vercel Frontend Settings

Project root:

- `Taxclarity/frontend`

Build settings:

- Install: `npm install`
- Build: `npm run build`

Environment variables:

```bash
NEXT_PUBLIC_WS_URL=wss://saul-backend.duckdns.org/ws
NEXT_PUBLIC_API_URL=https://saul-backend.duckdns.org
```

## 11. Smoke Tests

Backend:

```bash
curl https://saul-backend.duckdns.org/health
```

WebSocket:

```bash
npm i -g wscat
wscat -c wss://saul-backend.duckdns.org/ws
```

Frontend:

- open Vercel URL
- confirm WS connects

## 12. Troubleshooting (Actual Issues Seen)

### WebSocket fails after SSL

Cause: certbot rewrote nginx and removed `/ws`.
Fix: use the explicit HTTPS vhost in this doc.

### Cloud Run timeouts

We moved to VM. Use `e2-standard-2` minimum.

### GitHub Actions deploy fails

Cause: repo ownership and `safe.directory`.
Fix:

```bash
sudo chown -R sidharth:sidharth /opt/saulgoodman/repo
git config --global --add safe.directory /opt/saulgoodman/repo
```

### systemd restart loop

Cause: stale `.pids` file not removable.
Fix: add `ExecStartPre=/bin/rm -f /opt/saulgoodman/repo/Taxclarity/.pids`.

## 13. Useful Commands

```bash
sudo journalctl -u saulgoodman-backend -f
sudo systemctl restart saulgoodman-backend
sudo systemctl reload nginx
```
