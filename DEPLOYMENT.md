# Deployment Guide

Complete guide for deploying the arbitrage bot to production.

## Table of Contents

1. [Local Development](#local-development)
2. [Cloud Deployment](#cloud-deployment)
3. [Docker Deployment](#docker-deployment)
4. [Monitoring & Alerts](#monitoring--alerts)
5. [Maintenance](#maintenance)

## Local Development

### Setup

1. **Install Python 3.11+**
```bash
python --version  # Verify 3.11+
```

2. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# OR
venv\Scripts\activate  # Windows
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Configure environment**
```bash
cp .env.example .env
# Edit .env with your settings
```

5. **Test the setup**
```bash
# Run tests
pytest tests/ -v

# Dry-run
ENABLE_TRADING=false python -m src.main
```

## Cloud Deployment

### Option 1: DigitalOcean Droplet

**1. Create Droplet**
- Size: 1GB RAM minimum ($6/month)
- OS: Ubuntu 22.04 LTS
- Add SSH key

**2. SSH into droplet**
```bash
ssh root@your-droplet-ip
```

**3. Setup environment**
```bash
# Update system
apt update && apt upgrade -y

# Install Python 3.11
apt install python3.11 python3.11-venv python3-pip git -y

# Create app user
adduser arbitrage
usermod -aG sudo arbitrage
su - arbitrage
```

**4. Clone and setup**
```bash
cd ~
git clone <your-repo> trader
cd trader

# Create venv
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure
nano .env  # Add your credentials
```

**5. Setup systemd service**
```bash
sudo nano /etc/systemd/system/arbitrage-bot.service
```

Add:
```ini
[Unit]
Description=Arbitrage Trading Bot
After=network.target

[Service]
Type=simple
User=arbitrage
WorkingDirectory=/home/arbitrage/trader
Environment="PATH=/home/arbitrage/trader/venv/bin"
ExecStart=/home/arbitrage/trader/venv/bin/python -m src.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**6. Start service**
```bash
sudo systemctl daemon-reload
sudo systemctl enable arbitrage-bot
sudo systemctl start arbitrage-bot

# Check status
sudo systemctl status arbitrage-bot

# View logs
sudo journalctl -u arbitrage-bot -f
```

### Option 2: AWS EC2

**1. Launch EC2 Instance**
- AMI: Ubuntu Server 22.04 LTS
- Instance type: t3.micro (free tier) or t3.small
- Storage: 8GB minimum
- Security group: Allow SSH (22) from your IP

**2. Connect and setup**
```bash
ssh -i your-key.pem ubuntu@ec2-instance-ip

# Follow same steps as DigitalOcean above
```

**3. Setup CloudWatch for monitoring** (optional)
```bash
# Install CloudWatch agent
wget https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
sudo dpkg -i amazon-cloudwatch-agent.deb

# Configure to send logs/metrics
```

### Option 3: Google Cloud Platform

**1. Create Compute Engine VM**
```bash
gcloud compute instances create arbitrage-bot \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --machine-type=e2-micro \
  --zone=us-central1-a
```

**2. SSH and setup**
```bash
gcloud compute ssh arbitrage-bot

# Follow setup steps above
```

## Docker Deployment

### Dockerfile

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY src/ src/
COPY config/ config/

# Create logs directory
RUN mkdir -p logs data

# Run as non-root user
RUN useradd -m -u 1000 trader && \
    chown -R trader:trader /app
USER trader

CMD ["python", "-m", "src.main"]
```

### Docker Compose

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  arbitrage-bot:
    build: .
    container_name: arbitrage-bot
    restart: unless-stopped
    env_file:
      - .env
    volumes:
      - ./logs:/app/logs
      - ./data:/app/data
      - ./config:/app/config
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### Build and Run

```bash
# Build image
docker-compose build

# Start container
docker-compose up -d

# View logs
docker-compose logs -f

# Stop container
docker-compose down

# Restart
docker-compose restart
```

### Production Docker Deployment

```bash
# On your server
git clone <repo> && cd trader

# Configure
cp .env.example .env
nano .env  # Add credentials

# Deploy
docker-compose up -d

# Monitor
docker-compose logs -f arbitrage-bot
```

## Monitoring & Alerts

### Log Monitoring

**1. Local log files**
```bash
# Real-time
tail -f logs/arbitrage_bot.log

# Search for errors
grep "ERROR" logs/arbitrage_bot.log

# Recent trades
grep "Trade executed" logs/arbitrage_bot.log
```

**2. Log aggregation (optional)**

Setup with Papertrail:
```bash
# Install remote_syslog2
wget https://github.com/papertrail/remote_syslog2/releases/download/v0.20/remote_syslog2_0.20_amd64.deb
sudo dpkg -i remote_syslog2_0.20_amd64.deb

# Configure
sudo nano /etc/log_files.yml
```

Add:
```yaml
files:
  - /home/arbitrage/trader/logs/arbitrage_bot.log
destination:
  host: logs.papertrailapp.com
  port: XXXXX  # Your port
  protocol: tls
```

```bash
sudo systemctl enable remote_syslog2
sudo systemctl start remote_syslog2
```

### Slack Alerts

Add to `.env`:
```bash
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
ENABLE_ALERTS=true
```

### Health Checks

Create health check script `scripts/health_check.sh`:

```bash
#!/bin/bash

# Check if process is running
if ! pgrep -f "python -m src.main" > /dev/null; then
    echo "Bot is not running!"
    # Send alert
    curl -X POST $SLACK_WEBHOOK_URL -d '{"text":"⚠️ Arbitrage bot is DOWN!"}'
    exit 1
fi

# Check recent log activity
if [ $(find logs/arbitrage_bot.log -mmin -5 | wc -l) -eq 0 ]; then
    echo "No recent log activity!"
    exit 1
fi

echo "Bot is healthy"
exit 0
```

Add to crontab:
```bash
crontab -e

# Add:
*/5 * * * * /home/arbitrage/trader/scripts/health_check.sh
```

## Maintenance

### Daily Tasks

1. **Check logs for errors**
```bash
sudo journalctl -u arbitrage-bot --since "24 hours ago" | grep ERROR
```

2. **Review P&L**
```bash
grep "Total P&L" logs/arbitrage_bot.log | tail -1
```

3. **Check balances**
- Login to Kalshi and Polymarket
- Verify balances match expectations
- Look for stuck positions

### Weekly Tasks

1. **Update market pairs**
```bash
# Add new manual mappings to config/market_pairs.json
nano config/market_pairs.json

# Restart bot
sudo systemctl restart arbitrage-bot
```

2. **Review performance**
- Analyze win rate
- Review rejected opportunities
- Adjust MIN_PROFIT_THRESHOLD if needed

3. **Update dependencies**
```bash
pip list --outdated
pip install --upgrade <package>
```

### Monthly Tasks

1. **Security updates**
```bash
sudo apt update && sudo apt upgrade -y
sudo systemctl restart arbitrage-bot
```

2. **Log rotation check**
```bash
ls -lh logs/
# Clean old archives if needed
find logs/ -name "*.zip" -mtime +90 -delete
```

3. **Backup configuration**
```bash
tar -czf backup-$(date +%Y%m%d).tar.gz .env config/ data/
```

### Emergency Procedures

**1. Stop trading immediately**
```bash
# SSH into server
sudo systemctl stop arbitrage-bot

# Or set in .env and restart
ENABLE_TRADING=false
```

**2. Cancel all open orders**
```python
# Run Python script
from src.clients import KalshiClient, PolymarketClient
import asyncio

async def cancel_all():
    async with PolymarketClient() as poly:
        await poly.cancel_all_orders()
    # Kalshi cancellation if needed

asyncio.run(cancel_all())
```

**3. Review positions**
- Login to both platforms
- Check all open positions
- Close manually if needed

## Performance Tuning

### Reduce Latency

1. **Deploy closer to exchange servers**
- Kalshi: US-based servers
- Polymarket: Use US or EU regions

2. **Use WebSocket feeds** (future enhancement)

3. **Reduce CHECK_INTERVAL**
```bash
# In .env - but be mindful of rate limits!
CHECK_INTERVAL=2.0  # Down from 5.0
```

### Optimize Resource Usage

1. **Limit concurrent connections**
2. **Use connection pooling**
3. **Cache market data appropriately**

### Scale Up

1. **Add more market pairs**
2. **Increase position sizes**
3. **Add more platforms**

## Security Best Practices

1. **Credentials**
   - Never commit `.env` to git
   - Use environment variables
   - Rotate API keys regularly

2. **Server Security**
   - Enable firewall (ufw)
   - Use SSH keys (disable password auth)
   - Keep system updated
   - Use non-root user

3. **API Keys**
   - Use separate keys for prod/dev
   - Set minimum required permissions
   - Monitor API key usage

4. **Monitoring**
   - Enable alerts for unusual activity
   - Log all trades
   - Review regularly

## Troubleshooting

### Bot Won't Start

```bash
# Check logs
sudo journalctl -u arbitrage-bot -n 50

# Check Python environment
source venv/bin/activate
python -m src.main  # Run manually to see errors

# Verify credentials
python -c "from src.utils import get_settings; print(get_settings().validate_credentials())"
```

### No Opportunities Found

- Markets may be efficient
- Lower MIN_PROFIT_THRESHOLD (carefully)
- Add more market pair mappings
- Check API connectivity

### Trade Failures

- Check account balances
- Verify API permissions
- Review platform status pages
- Check logs for specific errors

## Support

- Review logs first: `logs/arbitrage_bot.log`
- Check DESIGN.md for architecture
- Consult API documentation (Kalshi, Polymarket)
- Open GitHub issue with logs
