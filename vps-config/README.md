# 🚀 Configuração VPS - WebScraping Consultores

## 📋 Domínio: maxsell.creapost.com.br

Este diretório contém todos os arquivos necessários para configurar o sistema de webscraping no seu VPS com o domínio **maxsell.creapost.com.br**.

## 📁 Arquivos Inclusos

- `nginx-maxsell.conf` - Configuração do Nginx
- `webscraping.service` - Serviço systemd
- `deploy-vps.sh` - Script de deploy automatizado
- `ssl-setup.sh` - Configuração SSL/HTTPS
- `monitoring-setup.sh` - Sistema de logs e monitoramento

## 🔧 Pré-requisitos

1. **VPS Ubuntu/Debian** com acesso root
2. **Domínio configurado**: maxsell.creapost.com.br apontando para o IP do VPS
3. **Portas abertas**: 22 (SSH), 80 (HTTP), 443 (HTTPS)

## 🚀 Instalação Rápida

### 1. Fazer Upload dos Arquivos

```bash
# No seu VPS, criar diretório
mkdir -p /tmp/webscraping-config

# Fazer upload dos arquivos (via scp, rsync ou git)
scp vps-config/* root@SEU_IP:/tmp/webscraping-config/
```

### 2. Executar Deploy Automatizado

```bash
# Conectar no VPS
ssh root@SEU_IP

# Dar permissão e executar
cd /tmp/webscraping-config
chmod +x *.sh
./deploy-vps.sh
```

### 3. Configurar SSL (Após Deploy)

```bash
# Executar configuração SSL
./ssl-setup.sh
```

### 4. Configurar Monitoramento

```bash
# Configurar logs e monitoramento
./monitoring-setup.sh
```

## 📋 Instalação Manual (Passo a Passo)

Se preferir fazer manualmente:

### 1. Preparar Sistema

```bash
# Atualizar sistema
apt update && apt upgrade -y

# Instalar dependências
apt install -y python3 python3-pip python3-venv nginx git curl wget
```

### 2. Criar Usuário

```bash
# Criar usuário para aplicação
useradd -m -s /bin/bash webscraping
usermod -aG sudo webscraping
```

### 3. Instalar Chrome/ChromeDriver

```bash
# Chrome
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor > /usr/share/keyrings/google-chrome-keyring.gpg
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome-keyring.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list
apt update
apt install -y google-chrome-stable

# ChromeDriver
CHROME_VERSION=$(google-chrome --version | awk '{print $3}' | cut -d. -f1)
wget -O /tmp/chromedriver.zip "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_${CHROME_VERSION}/chromedriver_linux64.zip"
unzip /tmp/chromedriver.zip -d /tmp/
mv /tmp/chromedriver /usr/local/bin/
chmod +x /usr/local/bin/chromedriver
```

### 4. Configurar Aplicação

```bash
# Clonar repositório
cd /opt
git clone https://github.com/SEU_USUARIO/webscraping-consultores.git webscraping-app
chown -R webscraping:webscraping /opt/webscraping-app

# Configurar ambiente Python
sudo -u webscraping python3 -m venv /opt/webscraping-app/venv
sudo -u webscraping /opt/webscraping-app/venv/bin/pip install -r /opt/webscraping-app/requirements.txt
```

### 5. Configurar Nginx

```bash
# Copiar configuração
cp nginx-maxsell.conf /etc/nginx/sites-available/maxsell
ln -s /etc/nginx/sites-available/maxsell /etc/nginx/sites-enabled/

# Remover site padrão
rm -f /etc/nginx/sites-enabled/default

# Testar e reiniciar
nginx -t
systemctl restart nginx
```

### 6. Configurar Serviço

```bash
# Copiar serviço
cp webscraping.service /etc/systemd/system/

# Habilitar e iniciar
systemctl daemon-reload
systemctl enable webscraping
systemctl start webscraping
```

## 🔒 Configuração SSL

### Automática (Recomendado)

```bash
./ssl-setup.sh
```

### Manual

```bash
# Instalar Certbot
apt install -y certbot python3-certbot-nginx

# Obter certificado
certbot --nginx -d maxsell.creapost.com.br -d www.maxsell.creapost.com.br

# Configurar renovação automática
echo "0 12 * * * /usr/bin/certbot renew --quiet" | crontab -
```

## 📊 Monitoramento

### Comandos Úteis

```bash
# Status completo
ws-status

# Logs em tempo real
ws-logs

# Logs de erro
ws-errors

# Reiniciar aplicação
ws-restart

# Status dos serviços
systemctl status webscraping
systemctl status nginx
```

### Logs Importantes

- **Aplicação**: `/var/log/webscraping/app.log`
- **Erros**: `/var/log/webscraping/error.log`
- **Nginx**: `/var/log/nginx/maxsell_access.log`
- **Monitoramento**: `/var/log/webscraping/monitor.log`

## 🔧 Solução de Problemas

### Aplicação não inicia

```bash
# Verificar logs
journalctl -u webscraping -f

# Verificar dependências
sudo -u webscraping /opt/webscraping-app/venv/bin/python -c "import selenium, flask"

# Testar manualmente
sudo -u webscraping /opt/webscraping-app/venv/bin/python /opt/webscraping-app/app.py
```

### Nginx não funciona

```bash
# Testar configuração
nginx -t

# Verificar logs
tail -f /var/log/nginx/error.log

# Verificar portas
netstat -tlnp | grep :80
netstat -tlnp | grep :443
```

### SSL não funciona

```bash
# Verificar certificado
certbot certificates

# Testar renovação
certbot renew --dry-run

# Verificar DNS
dig maxsell.creapost.com.br
```

### Chrome/Selenium problemas

```bash
# Testar Chrome
google-chrome --version
chromedriver --version

# Testar Selenium
sudo -u webscraping /opt/webscraping-app/venv/bin/python -c "from selenium import webdriver; print('OK')"
```

## 🌐 Acesso

Após a configuração completa:

- **HTTP**: http://maxsell.creapost.com.br (redireciona para HTTPS)
- **HTTPS**: https://maxsell.creapost.com.br
- **WWW**: https://www.maxsell.creapost.com.br

## 🔄 Atualizações

Para atualizar a aplicação:

```bash
# Parar serviço
systemctl stop webscraping

# Atualizar código
cd /opt/webscraping-app
git pull origin main

# Atualizar dependências (se necessário)
sudo -u webscraping /opt/webscraping-app/venv/bin/pip install -r requirements.txt

# Reiniciar serviço
systemctl start webscraping
```

## 📞 Suporte

Em caso de problemas:

1. Verificar logs: `ws-status`
2. Verificar serviços: `systemctl status webscraping nginx`
3. Verificar conectividade: `curl -I https://maxsell.creapost.com.br`
4. Verificar recursos: `htop`, `df -h`

---

**✅ Configuração completa para maxsell.creapost.com.br**

*Sistema pronto para produção com SSL, monitoramento e backup automático.*