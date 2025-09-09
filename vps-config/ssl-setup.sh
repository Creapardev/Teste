#!/bin/bash
# Script para Configuração SSL - Let's Encrypt
# Domínio: maxsell.creapost.com.br

set -e

# Cores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[WARNING] $1${NC}"
}

error() {
    echo -e "${RED}[ERROR] $1${NC}"
    exit 1
}

# Verificar se é root
if [[ $EUID -ne 0 ]]; then
   error "Este script deve ser executado como root (use sudo)"
fi

log "🔐 Configurando SSL para maxsell.creapost.com.br"

# 1. Verificar se o domínio está apontando corretamente
log "🔍 Verificando DNS..."
DOMAIN_IP=$(dig +short maxsell.creapost.com.br)
SERVER_IP=$(curl -s ifconfig.me)

if [ "$DOMAIN_IP" != "$SERVER_IP" ]; then
    warn "⚠️  DNS pode não estar propagado ainda"
    echo "   Domínio aponta para: $DOMAIN_IP"
    echo "   Servidor IP: $SERVER_IP"
    read -p "Continuar mesmo assim? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    log "✅ DNS configurado corretamente"
fi

# 2. Instalar Certbot se não estiver instalado
if ! command -v certbot &> /dev/null; then
    log "📦 Instalando Certbot..."
    apt update
    apt install -y certbot python3-certbot-nginx
fi

# 3. Parar nginx temporariamente para standalone
log "⏸️  Parando Nginx temporariamente..."
systemctl stop nginx

# 4. Obter certificado SSL
log "🔐 Obtendo certificado SSL..."
certbot certonly \
    --standalone \
    --non-interactive \
    --agree-tos \
    --email admin@creapost.com.br \
    -d maxsell.creapost.com.br \
    -d www.maxsell.creapost.com.br

# 5. Criar configuração Nginx com SSL
log "⚙️  Configurando Nginx com SSL..."
cat > /etc/nginx/sites-available/maxsell << 'EOF'
# Redirecionamento HTTP para HTTPS
server {
    listen 80;
    server_name maxsell.creapost.com.br www.maxsell.creapost.com.br;
    return 301 https://$server_name$request_uri;
}

# Configuração HTTPS
server {
    listen 443 ssl http2;
    server_name maxsell.creapost.com.br www.maxsell.creapost.com.br;

    # Certificados SSL
    ssl_certificate /etc/letsencrypt/live/maxsell.creapost.com.br/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/maxsell.creapost.com.br/privkey.pem;
    
    # Configurações SSL modernas
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    
    # HSTS
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    
    # Logs
    access_log /var/log/nginx/maxsell_ssl_access.log;
    error_log /var/log/nginx/maxsell_ssl_error.log;

    # Headers de segurança
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;
    add_header Content-Security-Policy "default-src 'self' http: https: data: blob: 'unsafe-inline'" always;

    # Proxy para aplicação Flask
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Servir arquivos estáticos
    location /static/ {
        alias /opt/webscraping-app/static/;
        expires 30d;
        add_header Cache-Control "public, no-transform";
    }

    # Favicon e robots
    location = /favicon.ico {
        log_not_found off;
        access_log off;
    }

    location = /robots.txt {
        log_not_found off;
        access_log off;
    }

    # Bloquear arquivos sensíveis
    location ~ /\. {
        deny all;
    }

    client_max_body_size 10M;
}
EOF

# 6. Testar configuração e reiniciar Nginx
log "🔧 Testando configuração Nginx..."
nginx -t

log "🔄 Reiniciando Nginx..."
systemctl start nginx
systemctl reload nginx

# 7. Configurar renovação automática
log "🔄 Configurando renovação automática..."
# Criar script de renovação
cat > /etc/cron.daily/certbot-renew << 'EOF'
#!/bin/bash
/usr/bin/certbot renew --quiet --nginx
EOF

chmod +x /etc/cron.daily/certbot-renew

# Adicionar ao crontab também
(crontab -l 2>/dev/null | grep -v certbot; echo "0 12 * * * /usr/bin/certbot renew --quiet --nginx") | crontab -

# 8. Verificar certificado
log "✅ Verificando certificado..."
certbot certificates

# 9. Testar renovação
log "🧪 Testando renovação..."
certbot renew --dry-run

log "🎉 SSL configurado com sucesso!"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}🔒 HTTPS ativo em:${NC}"
echo -e "   🌐 https://maxsell.creapost.com.br"
echo -e "   🌐 https://www.maxsell.creapost.com.br"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}📋 Informações importantes:${NC}"
echo -e "   • Certificado válido por 90 dias"
echo -e "   • Renovação automática configurada"
echo -e "   • HTTP redireciona automaticamente para HTTPS"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

log "🔐 SSL configurado e funcionando!"