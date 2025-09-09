#!/bin/bash

# Script para instalar Chrome e Firefox no VPS Ubuntu
# Para uso com Selenium WebDriver

set -e

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
}

log "🚀 Iniciando instalação dos navegadores para WebScraping..."

# 1. Atualizar sistema
log "📦 Atualizando sistema..."
apt update && apt upgrade -y

# 2. Instalar dependências básicas
log "🔧 Instalando dependências básicas..."
apt install -y wget curl gnupg2 software-properties-common apt-transport-https ca-certificates

# 3. Instalar Google Chrome
log "🌐 Instalando Google Chrome..."
# Adicionar chave GPG do Google
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add -

# Adicionar repositório do Chrome
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list

# Atualizar e instalar Chrome
apt update
apt install -y google-chrome-stable

# Verificar instalação do Chrome
if google-chrome --version; then
    log "✅ Google Chrome instalado com sucesso!"
else
    error "❌ Falha na instalação do Google Chrome"
    exit 1
fi

# 4. Instalar Firefox
log "🦊 Instalando Firefox..."
apt install -y firefox

# Verificar instalação do Firefox
if firefox --version; then
    log "✅ Firefox instalado com sucesso!"
else
    error "❌ Falha na instalação do Firefox"
    exit 1
fi

# 5. Instalar ChromeDriver
log "🚗 Instalando ChromeDriver..."
# Obter versão do Chrome
CHROME_VERSION=$(google-chrome --version | awk '{print $3}' | cut -d. -f1)
log "📋 Versão principal do Chrome detectada: $CHROME_VERSION"

# Tentar diferentes métodos para obter ChromeDriver
CHROMEDRIVER_VERSION=""

# Método 1: Tentar versão específica
if [ "$CHROME_VERSION" -ge "115" ]; then
    # Para Chrome 115+, usar Chrome for Testing API
    log "📋 Usando Chrome for Testing API para Chrome $CHROME_VERSION+"
    CHROMEDRIVER_VERSION=$(curl -s "https://googlechromelabs.github.io/chrome-for-testing/LATEST_RELEASE_$CHROME_VERSION" 2>/dev/null || echo "")
fi

# Método 2: Fallback para versões mais antigas
if [ -z "$CHROMEDRIVER_VERSION" ]; then
    log "📋 Tentando método legacy para ChromeDriver"
    CHROMEDRIVER_VERSION=$(curl -s "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_$CHROME_VERSION" 2>/dev/null || echo "")
fi

# Método 3: Usar última versão estável como fallback
if [ -z "$CHROMEDRIVER_VERSION" ]; then
    warn "Não foi possível detectar versão específica, usando última versão estável"
    CHROMEDRIVER_VERSION=$(curl -s "https://chromedriver.storage.googleapis.com/LATEST_RELEASE" 2>/dev/null || echo "119.0.6045.105")
fi

log "📋 Versão do ChromeDriver: $CHROMEDRIVER_VERSION"

# Baixar ChromeDriver
if [ "$CHROME_VERSION" -ge "115" ] && [ -n "$CHROMEDRIVER_VERSION" ]; then
    # Para Chrome 115+
    wget -O /tmp/chromedriver.zip "https://storage.googleapis.com/chrome-for-testing-public/$CHROMEDRIVER_VERSION/linux64/chromedriver-linux64.zip" 2>/dev/null || \
    wget -O /tmp/chromedriver.zip "https://chromedriver.storage.googleapis.com/$CHROMEDRIVER_VERSION/chromedriver_linux64.zip"
else
    # Para versões mais antigas
    wget -O /tmp/chromedriver.zip "https://chromedriver.storage.googleapis.com/$CHROMEDRIVER_VERSION/chromedriver_linux64.zip"
fi

# Extrair e instalar
if [ -f "/tmp/chromedriver.zip" ]; then
    unzip /tmp/chromedriver.zip -d /tmp/
    # Procurar o executável chromedriver
    find /tmp -name "chromedriver" -type f -exec mv {} /usr/local/bin/ \;
    chmod +x /usr/local/bin/chromedriver
else
    error "Falha ao baixar ChromeDriver"
fi

# Verificar ChromeDriver
if chromedriver --version; then
    log "✅ ChromeDriver instalado com sucesso!"
else
    error "❌ Falha na instalação do ChromeDriver"
    exit 1
fi

# 6. Instalar GeckoDriver (Firefox)
log "🦎 Instalando GeckoDriver..."
# Obter última versão do GeckoDriver
GECKODRIVER_VERSION=$(curl -s "https://api.github.com/repos/mozilla/geckodriver/releases/latest" | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')
log "📋 Versão do GeckoDriver: $GECKODRIVER_VERSION"

wget -O /tmp/geckodriver.tar.gz "https://github.com/mozilla/geckodriver/releases/download/$GECKODRIVER_VERSION/geckodriver-$GECKODRIVER_VERSION-linux64.tar.gz"
tar -xzf /tmp/geckodriver.tar.gz -C /tmp/
mv /tmp/geckodriver /usr/local/bin/
chmod +x /usr/local/bin/geckodriver

# Verificar GeckoDriver
if geckodriver --version; then
    log "✅ GeckoDriver instalado com sucesso!"
else
    error "❌ Falha na instalação do GeckoDriver"
    exit 1
fi

# 7. Instalar dependências adicionais para headless
log "🖥️ Instalando dependências para modo headless..."
apt install -y xvfb x11-utils x11-xserver-utils

# 8. Configurar permissões
log "🔐 Configurando permissões..."
# Adicionar usuário webscraping aos grupos necessários
usermod -a -G audio,video webscraping

# 9. Criar script de teste
log "🧪 Criando script de teste..."
cat > /opt/webscraping-app/test-browsers.py << 'EOF'
#!/usr/bin/env python3

import sys
sys.path.insert(0, '/opt/webscraping-app')

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
import time

def test_chrome():
    print("🌐 Testando Google Chrome...")
    try:
        options = ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        
        service = ChromeService('/usr/local/bin/chromedriver')
        driver = webdriver.Chrome(service=service, options=options)
        
        driver.get('https://www.google.com')
        title = driver.title
        driver.quit()
        
        print(f"✅ Chrome OK - Título: {title}")
        return True
    except Exception as e:
        print(f"❌ Chrome ERRO: {e}")
        return False

def test_firefox():
    print("🦊 Testando Firefox...")
    try:
        options = FirefoxOptions()
        options.add_argument('--headless')
        
        service = FirefoxService('/usr/local/bin/geckodriver')
        driver = webdriver.Firefox(service=service, options=options)
        
        driver.get('https://www.google.com')
        title = driver.title
        driver.quit()
        
        print(f"✅ Firefox OK - Título: {title}")
        return True
    except Exception as e:
        print(f"❌ Firefox ERRO: {e}")
        return False

if __name__ == '__main__':
    print("🧪 Testando navegadores...")
    
    chrome_ok = test_chrome()
    firefox_ok = test_firefox()
    
    if chrome_ok and firefox_ok:
        print("\n🎉 Todos os navegadores funcionando!")
        sys.exit(0)
    elif chrome_ok or firefox_ok:
        print("\n⚠️ Pelo menos um navegador funcionando")
        sys.exit(0)
    else:
        print("\n❌ Nenhum navegador funcionando")
        sys.exit(1)
EOF

chmod +x /opt/webscraping-app/test-browsers.py
chown webscraping:webscraping /opt/webscraping-app/test-browsers.py

# 10. Limpar arquivos temporários
log "🧹 Limpando arquivos temporários..."
rm -f /tmp/chromedriver.zip /tmp/geckodriver.tar.gz

# 11. Testar instalação
log "🧪 Testando instalação..."
echo "Executando teste como usuário webscraping..."
sudo -u webscraping /opt/webscraping-app/venv/bin/python /opt/webscraping-app/test-browsers.py

if [ $? -eq 0 ]; then
    log "🎉 Instalação concluída com sucesso!"
    echo ""
    echo "📋 RESUMO DA INSTALAÇÃO:"
    echo "   ✅ Google Chrome: $(google-chrome --version)"
    echo "   ✅ ChromeDriver: $(chromedriver --version | head -n1)"
    echo "   ✅ Firefox: $(firefox --version)"
    echo "   ✅ GeckoDriver: $(geckodriver --version | head -n1)"
    echo ""
    echo "🚀 Agora você pode usar o webscraping no VPS!"
else
    error "❌ Falha nos testes. Verifique os logs acima."
    exit 1
fi

log "✅ Script de instalação concluído!"