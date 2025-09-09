#!/bin/bash
# Script de Configuração de Logs e Monitoramento
# Sistema: WebScraping Consultores - maxsell.creapost.com.br

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

log "📊 Configurando sistema de logs e monitoramento"

# 1. Criar diretórios de logs
log "📁 Criando estrutura de diretórios..."
mkdir -p /var/log/webscraping
mkdir -p /var/log/nginx
mkdir -p /opt/webscraping-app/logs

# Definir permissões
chown -R webscraping:webscraping /var/log/webscraping
chown -R webscraping:webscraping /opt/webscraping-app/logs
chmod 755 /var/log/webscraping
chmod 755 /opt/webscraping-app/logs

# 2. Configurar logrotate para aplicação
log "🔄 Configurando rotação de logs..."
cat > /etc/logrotate.d/webscraping << 'EOF'
/var/log/webscraping/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 webscraping webscraping
    postrotate
        systemctl reload webscraping || true
    endscript
}

/opt/webscraping-app/logs/*.log {
    daily
    missingok
    rotate 15
    compress
    delaycompress
    notifempty
    create 644 webscraping webscraping
}
EOF

# 3. Configurar logrotate para Nginx
cat > /etc/logrotate.d/nginx-webscraping << 'EOF'
/var/log/nginx/maxsell_*.log {
    daily
    missingok
    rotate 52
    compress
    delaycompress
    notifempty
    create 644 www-data adm
    postrotate
        if [ -f /var/run/nginx.pid ]; then
            kill -USR1 `cat /var/run/nginx.pid`
        fi
    endscript
}
EOF

# 4. Criar script de monitoramento
log "📈 Criando scripts de monitoramento..."
cat > /opt/webscraping-app/monitor.sh << 'EOF'
#!/bin/bash
# Script de Monitoramento - WebScraping App

LOG_FILE="/var/log/webscraping/monitor.log"
APP_LOG="/var/log/webscraping/app.log"
ERROR_LOG="/var/log/webscraping/error.log"

# Função de log
log_message() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

# Verificar se a aplicação está rodando
check_app() {
    if systemctl is-active --quiet webscraping; then
        log_message "✅ Aplicação webscraping está ativa"
        return 0
    else
        log_message "❌ Aplicação webscraping não está rodando"
        return 1
    fi
}

# Verificar se o Nginx está rodando
check_nginx() {
    if systemctl is-active --quiet nginx; then
        log_message "✅ Nginx está ativo"
        return 0
    else
        log_message "❌ Nginx não está rodando"
        return 1
    fi
}

# Verificar conectividade HTTP
check_http() {
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:5000 | grep -q "200\|302"; then
        log_message "✅ Aplicação Flask respondendo na porta 5000"
        return 0
    else
        log_message "❌ Aplicação Flask não está respondendo"
        return 1
    fi
}

# Verificar HTTPS
check_https() {
    if curl -s -o /dev/null -w "%{http_code}" https://maxsell.creapost.com.br | grep -q "200\|302"; then
        log_message "✅ HTTPS funcionando corretamente"
        return 0
    else
        log_message "❌ HTTPS não está funcionando"
        return 1
    fi
}

# Verificar uso de memória
check_memory() {
    MEMORY_USAGE=$(free | grep Mem | awk '{printf "%.1f", $3/$2 * 100.0}')
    log_message "📊 Uso de memória: ${MEMORY_USAGE}%"
    
    if (( $(echo "$MEMORY_USAGE > 90" | bc -l) )); then
        log_message "⚠️  Uso de memória alto: ${MEMORY_USAGE}%"
    fi
}

# Verificar uso de disco
check_disk() {
    DISK_USAGE=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')
    log_message "💾 Uso de disco: ${DISK_USAGE}%"
    
    if [ "$DISK_USAGE" -gt 85 ]; then
        log_message "⚠️  Uso de disco alto: ${DISK_USAGE}%"
    fi
}

# Verificar logs de erro recentes
check_errors() {
    ERROR_COUNT=$(journalctl -u webscraping --since "1 hour ago" --no-pager | grep -i error | wc -l)
    if [ "$ERROR_COUNT" -gt 0 ]; then
        log_message "⚠️  $ERROR_COUNT erros encontrados na última hora"
    else
        log_message "✅ Nenhum erro na última hora"
    fi
}

# Executar verificações
log_message "🔍 Iniciando verificações de monitoramento"
check_app
check_nginx
check_http
check_https
check_memory
check_disk
check_errors
log_message "✅ Verificações concluídas"
EOF

chmod +x /opt/webscraping-app/monitor.sh
chown webscraping:webscraping /opt/webscraping-app/monitor.sh

# 5. Criar script de status detalhado
cat > /opt/webscraping-app/status.sh << 'EOF'
#!/bin/bash
# Script de Status Detalhado

# Cores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}           📊 STATUS DO SISTEMA WEBSCRAPING           ${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Status dos serviços
echo -e "\n${YELLOW}🔧 SERVIÇOS:${NC}"
if systemctl is-active --quiet webscraping; then
    echo -e "   ✅ WebScraping App: ${GREEN}ATIVO${NC}"
else
    echo -e "   ❌ WebScraping App: ${RED}INATIVO${NC}"
fi

if systemctl is-active --quiet nginx; then
    echo -e "   ✅ Nginx: ${GREEN}ATIVO${NC}"
else
    echo -e "   ❌ Nginx: ${RED}INATIVO${NC}"
fi

# Status da aplicação
echo -e "\n${YELLOW}🌐 CONECTIVIDADE:${NC}"
if curl -s -o /dev/null -w "%{http_code}" http://localhost:5000 | grep -q "200\|302"; then
    echo -e "   ✅ Flask (5000): ${GREEN}RESPONDENDO${NC}"
else
    echo -e "   ❌ Flask (5000): ${RED}NÃO RESPONDE${NC}"
fi

if curl -s -o /dev/null -w "%{http_code}" https://maxsell.creapost.com.br | grep -q "200\|302"; then
    echo -e "   ✅ HTTPS: ${GREEN}FUNCIONANDO${NC}"
else
    echo -e "   ❌ HTTPS: ${RED}PROBLEMA${NC}"
fi

# Recursos do sistema
echo -e "\n${YELLOW}💻 RECURSOS:${NC}"
MEMORY_USAGE=$(free | grep Mem | awk '{printf "%.1f", $3/$2 * 100.0}')
DISK_USAGE=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')
CPU_LOAD=$(uptime | awk -F'load average:' '{print $2}' | awk '{print $1}' | sed 's/,//')

echo -e "   📊 Memória: ${MEMORY_USAGE}%"
echo -e "   💾 Disco: ${DISK_USAGE}%"
echo -e "   ⚡ Load: ${CPU_LOAD}"

# Logs recentes
echo -e "\n${YELLOW}📋 LOGS RECENTES:${NC}"
ERROR_COUNT=$(journalctl -u webscraping --since "1 hour ago" --no-pager | grep -i error | wc -l)
echo -e "   🔍 Erros (1h): $ERROR_COUNT"

# Certificado SSL
echo -e "\n${YELLOW}🔒 CERTIFICADO SSL:${NC}"
if [ -f "/etc/letsencrypt/live/maxsell.creapost.com.br/fullchain.pem" ]; then
    CERT_EXPIRY=$(openssl x509 -enddate -noout -in /etc/letsencrypt/live/maxsell.creapost.com.br/fullchain.pem | cut -d= -f2)
    echo -e "   📅 Expira em: $CERT_EXPIRY"
else
    echo -e "   ❌ Certificado não encontrado"
fi

# URLs de acesso
echo -e "\n${YELLOW}🌐 ACESSO:${NC}"
echo -e "   🔗 https://maxsell.creapost.com.br"
echo -e "   🔗 https://www.maxsell.creapost.com.br"

echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
EOF

chmod +x /opt/webscraping-app/status.sh
chown webscraping:webscraping /opt/webscraping-app/status.sh

# 6. Configurar cron para monitoramento
log "⏰ Configurando monitoramento automático..."
# Adicionar ao crontab do usuário webscraping
sudo -u webscraping crontab -l 2>/dev/null | { cat; echo "*/15 * * * * /opt/webscraping-app/monitor.sh"; } | sudo -u webscraping crontab -

# 7. Criar aliases úteis
log "🔧 Criando aliases úteis..."
cat >> /home/webscraping/.bashrc << 'EOF'

# Aliases para WebScraping App
alias ws-status='/opt/webscraping-app/status.sh'
alias ws-logs='tail -f /var/log/webscraping/app.log'
alias ws-errors='tail -f /var/log/webscraping/error.log'
alias ws-restart='sudo systemctl restart webscraping'
alias ws-nginx='sudo systemctl status nginx'
alias ws-monitor='tail -f /var/log/webscraping/monitor.log'
EOF

# 8. Configurar fail2ban para proteção (opcional)
log "🛡️  Configurando proteção básica..."
if command -v fail2ban-server &> /dev/null; then
    cat > /etc/fail2ban/jail.d/nginx-webscraping.conf << 'EOF'
[nginx-http-auth]
enabled = true
filter = nginx-http-auth
logpath = /var/log/nginx/maxsell_*error.log
maxretry = 3
bantime = 3600

[nginx-noscript]
enabled = true
filter = nginx-noscript
logpath = /var/log/nginx/maxsell_*access.log
maxretry = 6
bantime = 86400
EOF
    systemctl restart fail2ban
    log "✅ Fail2ban configurado"
else
    warn "Fail2ban não instalado - considere instalar para maior segurança"
fi

# 9. Criar script de backup de logs
cat > /opt/webscraping-app/backup-logs.sh << 'EOF'
#!/bin/bash
# Backup de logs importantes

BACKUP_DIR="/opt/webscraping-app/backups"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

# Compactar logs antigos
tar -czf "$BACKUP_DIR/logs_$DATE.tar.gz" \
    /var/log/webscraping/*.log \
    /var/log/nginx/maxsell_*.log \
    2>/dev/null

# Manter apenas os últimos 7 backups
find "$BACKUP_DIR" -name "logs_*.tar.gz" -mtime +7 -delete

echo "Backup criado: logs_$DATE.tar.gz"
EOF

chmod +x /opt/webscraping-app/backup-logs.sh
chown webscraping:webscraping /opt/webscraping-app/backup-logs.sh

# Adicionar backup semanal ao cron
sudo -u webscraping crontab -l 2>/dev/null | { cat; echo "0 2 * * 0 /opt/webscraping-app/backup-logs.sh"; } | sudo -u webscraping crontab -

log "✅ Sistema de monitoramento configurado!"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}📊 MONITORAMENTO ATIVO${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}📋 Comandos úteis:${NC}"
echo -e "   🔍 ws-status     - Status completo do sistema"
echo -e "   📄 ws-logs       - Logs da aplicação em tempo real"
echo -e "   ❌ ws-errors     - Logs de erro em tempo real"
echo -e "   🔄 ws-restart    - Reiniciar aplicação"
echo -e "   📊 ws-monitor    - Logs de monitoramento"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ Monitoramento automático a cada 15 minutos${NC}"
echo -e "${GREEN}✅ Backup semanal de logs configurado${NC}"
echo -e "${GREEN}✅ Rotação de logs configurada${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

log "📊 Configuração de monitoramento concluída!"