# Saul Goodman Deployment

This setup deploys:

- `Taxclarity/frontend` to `Vercel`
- `Taxclarity/` backend stack to a single `Google Compute Engine VM`
- backend redeploys automatically through `GitHub Actions`

## 1. Create the VM

Use Google Compute Engine:

- Region: `us-central1`, `us-east1`, or `us-west1`
- Machine type: `e2-micro`
- Boot disk: `Ubuntu 22.04 LTS`
- Disk: `30 GB standard persistent disk`
- Enable: `Allow HTTP traffic`
- Enable: `Allow HTTPS traffic`

Reserve a static external IP if you want stable DNS.

## 2. Prepare a hostname

Free option:

- create a hostname with `DuckDNS`
- point it to the VM IP

Example:

- `saulgoodman.duckdns.org`

## 3. Install packages on the VM

```bash
sudo apt update
sudo apt install -y git nginx certbot python3-certbot-nginx python3-venv build-essential rsync lsof
```

## 4. Create app directories

```bash
sudo useradd -m -s /bin/bash saul || true
sudo mkdir -p /opt/saulgoodman
sudo chown -R saul:saul /opt/saulgoodman
```

Then switch to that user:

```bash
sudo su - saul
```

## 5. Clone the repo and create the venv

```bash
cd /opt/saulgoodman
git clone <YOUR_GITHUB_REPO_URL> repo
python3 -m venv /opt/saulgoodman/venv
source /opt/saulgoodman/venv/bin/activate
pip install --upgrade pip
pip install -r /opt/saulgoodman/repo/Taxclarity/requirements.txt
```

## 6. Create backend env file

Create:

- `/opt/saulgoodman/repo/Taxclarity/.env`

Put all required backend variables there, for example:

```bash
GOOGLE_API_KEY=...
DEMO_MODE=true
DEMO_SCENARIO_PATH=/opt/saulgoodman/repo/scenario1.txt
CLOUD_SQL_DATABASE_URL=...
CLOUD_SQL_INSTANCE_CONNECTION_NAME=...
```

Adjust variables to match your actual backend setup.

## 7. Install nginx config

Copy the provided config:

```bash
sudo cp /opt/saulgoodman/repo/Taxclarity/deploy/nginx/saulgoodman.conf /etc/nginx/sites-available/saulgoodman
sudo ln -sf /etc/nginx/sites-available/saulgoodman /etc/nginx/sites-enabled/saulgoodman
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
```

Edit `server_name` in `/etc/nginx/sites-available/saulgoodman` to your real hostname before enabling SSL.

## 8. Install SSL

```bash
sudo certbot --nginx -d <YOUR_BACKEND_HOSTNAME>
```

This gives you:

- `https://<YOUR_BACKEND_HOSTNAME>`
- `wss://<YOUR_BACKEND_HOSTNAME>/ws`

## 9. Install the backend service

Copy and edit the provided unit:

```bash
sudo cp /opt/saulgoodman/repo/Taxclarity/deploy/systemd/saulgoodman-backend.service /etc/systemd/system/saulgoodman-backend.service
```

If your VM username is not `saul`, update the `User=` field in the service file.

Then enable it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable saulgoodman-backend
sudo systemctl start saulgoodman-backend
sudo systemctl status saulgoodman-backend
```

## 10. Deploy the frontend on Vercel

Import the repo into Vercel and set the project root to:

- `Taxclarity/frontend`

Framework:

- `Next.js`

Set frontend environment variables in Vercel:

```bash
NEXT_PUBLIC_WS_URL=wss://<YOUR_BACKEND_HOSTNAME>/ws
NEXT_PUBLIC_API_URL=https://<YOUR_BACKEND_HOSTNAME>
```

Then deploy.

## 11. Configure GitHub Actions backend deploy

This repo includes:

- `.github/workflows/deploy-backend-vm.yml`

Add these GitHub repository secrets:

- `VM_HOST`
- `VM_USER`
- `VM_SSH_KEY`

The workflow:

- syncs the repo to `/opt/saulgoodman/repo`
- creates or reuses `/opt/saulgoodman/venv`
- installs backend requirements
- restarts `saulgoodman-backend`

## 12. Optional frontend automation

Simplest option:

- use Vercel Git integration

Every push to `main` will redeploy the frontend automatically.

## 13. Smoke test

Backend:

```bash
curl https://<YOUR_BACKEND_HOSTNAME>/health
```

Frontend:

- open the Vercel URL
- confirm WebSocket connects
- confirm graph API loads

## 14. Useful commands

Backend logs:

```bash
sudo journalctl -u saulgoodman-backend -f
```

Restart backend:

```bash
sudo systemctl restart saulgoodman-backend
```

Reload nginx:

```bash
sudo systemctl reload nginx
```
