#!/bin/bash
# Script de Deploy Automatizado para VPS
# Domínio: maxsell.creapost.com.br
# Autor: Assistente AI
# Data: $(date +%Y-%m-%d)

set -e  # Parar em caso de erro

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Função para log
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

log "🚀 Iniciando deploy da aplicação WebScraping"
log "📍 Domínio: maxsell.creapost.com.br"

# 1. Atualizar sistema
log "📦 Atualizando sistema..."
apt update && apt upgrade -y

# 2. Instalar dependências básicas
log "🔧 Instalando dependências básicas..."
apt install -y python3 python3-pip python3-venv git nginx ufw curl wget gnupg2 software-properties-common supervisor

# 3. Instalar navegadores para webscraping
log "🌐 Instalando navegadores..."
chmod +x /opt/webscraping-app/vps-config/install-browsers.sh
/opt/webscraping-app/vps-config/install-browsers.sh

# 5. Criar usuário para aplicação
log "👤 Criando usuário webscraping..."
if ! id "webscraping" &>/dev/null; then
    useradd -r -s /bin/false -d /opt/webscraping-app webscraping
fi

# 6. Criar diretórios
log "📁 Criando estrutura de diretórios..."
mkdir -p /opt/webscraping-app
mkdir -p /opt/webscraping-venv
mkdir -p /var/log/webscraping
chown -R webscraping:webscraping /opt/webscraping-app
chown -R webscraping:webscraping /opt/webscraping-venv
chown -R webscraping:webscraping /var/log/webscraping

# 7. Clonar repositório
log "📥 Clonando repositório..."
cd /opt
if [ -d "webscraping-app/.git" ]; then
    cd webscraping-app
    sudo -u webscraping git pull origin master
else
    rm -rf webscraping-app
    sudo -u webscraping git clone https://github.com/Creapardev/Teste.git webscraping-app
    cd webscraping-app
fi

# 8. Criar ambiente virtual
log "🐍 Configurando ambiente Python..."
sudo -u webscraping python3 -m venv /opt/webscraping-venv
sudo -u webscraping /opt/webscraping-venv/bin/pip install --upgrade pip
sudo -u webscraping /opt/webscraping-venv/bin/pip install -r requirements.txt

# 9. Configurar Nginx
log "🌐 Configurando Nginx..."
cp /opt/webscraping-app/vps-config/nginx-maxsell.conf /etc/nginx/sites-available/maxsell
ln -sf /etc/nginx/sites-available/maxsell /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable nginx
systemctl restart nginx

# 10. Configurar serviço systemd
log "⚙️ Configurando serviço systemd..."
cp /opt/webscraping-app/vps-config/webscraping.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable webscraping
systemctl start webscraping

# 11. Configurar firewall
log "🔒 Configurando firewall..."
ufw --force enable
ufw allow ssh
ufw allow 'Nginx Full'
ufw allow 80
ufw allow 443

# 12. Instalar Certbot para SSL
log "🔐 Instalando Certbot..."
apt install -y certbot python3-certbot-nginx

# 13. Verificar status dos serviços
log "✅ Verificando status dos serviços..."
systemctl status nginx --no-pager -l
systemctl status webscraping --no-pager -l

# 14. Configurar SSL (opcional - requer confirmação)
read -p "Deseja configurar SSL automaticamente? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    log "🔐 Configurando SSL com Let's Encrypt..."
    certbot --nginx -d maxsell.creapost.com.br -d www.maxsell.creapost.com.br --non-interactive --agree-tos --email admin@creapost.com.br
    
    # Configurar renovação automática
    (crontab -l 2>/dev/null; echo "0 12 * * * /usr/bin/certbot renew --quiet") | crontab -
fi

# 15. Mostrar informações finais
log "🎉 Deploy concluído com sucesso!"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ Aplicação disponível em:${NC}"
echo -e "   🌐 http://maxsell.creapost.com.br"
echo -e "   🔒 https://maxsell.creapost.com.br (se SSL configurado)"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}📋 Comandos úteis:${NC}"
echo -e "   • Reiniciar app: systemctl restart webscraping"
echo -e "   • Ver logs: journalctl -u webscraping -f"
echo -e "   • Status: systemctl status webscraping"
echo -e "   • Nginx: systemctl status nginx"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

log "🚀 Deploy finalizado! Sua aplicação está online!"