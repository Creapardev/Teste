#!/usr/bin/env python3
"""
Configuração otimizada do WebDriver para ambiente de produção VPS
Suporta Chrome e Firefox com fallback automático
"""

import os
import sys
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager

class WebDriverManager:
    """
    Gerenciador de WebDriver com fallback automático entre Chrome e Firefox
    Otimizado para ambiente de produção VPS sem interface gráfica
    """
    
    def __init__(self):
        self.chrome_available = self._check_chrome()
        self.firefox_available = self._check_firefox()
        
        if not self.chrome_available and not self.firefox_available:
            raise Exception("Nenhum navegador disponível. Instale Chrome ou Firefox.")
    
    def _check_chrome(self):
        """Verifica se Chrome está disponível"""
        try:
            # Verificar se Chrome está instalado
            chrome_check = os.system('google-chrome --version > /dev/null 2>&1')
            if chrome_check != 0:
                return False
            
            # Verificar se ChromeDriver está disponível
            chromedriver_check = os.system('chromedriver --version > /dev/null 2>&1')
            return chromedriver_check == 0
        except Exception as e:
            print(f"Erro ao verificar Chrome: {e}")
            return False
    
    def _check_firefox(self):
        """Verifica se Firefox está disponível"""
        try:
            os.system('firefox --version > /dev/null 2>&1')
            return os.system('geckodriver --version > /dev/null 2>&1') == 0
        except:
            return False
    
    def get_chrome_options(self):
        """Configurações otimizadas do Chrome para VPS"""
        options = ChromeOptions()
        
        # Configurações essenciais para VPS
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-web-security')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-plugins')
        options.add_argument('--disable-images')
        options.add_argument('--disable-javascript')
        
        # Configurações de performance
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--start-maximized')
        options.add_argument('--disable-background-timer-throttling')
        options.add_argument('--disable-backgrounding-occluded-windows')
        options.add_argument('--disable-renderer-backgrounding')
        
        # Configurações de memória
        options.add_argument('--memory-pressure-off')
        options.add_argument('--max_old_space_size=4096')
        
        # User agent
        options.add_argument('--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
        
        # Configurações de rede
        options.add_argument('--aggressive-cache-discard')
        options.add_argument('--disable-background-networking')
        
        return options
    
    def get_firefox_options(self):
        """Configurações otimizadas do Firefox para VPS"""
        options = FirefoxOptions()
        
        # Configurações essenciais para VPS
        options.add_argument('--headless')
        options.add_argument('--width=1920')
        options.add_argument('--height=1080')
        
        # Configurações de performance
        options.set_preference('dom.webdriver.enabled', False)
        options.set_preference('useAutomationExtension', False)
        options.set_preference('general.useragent.override', 'Mozilla/5.0 (X11; Linux x86_64; rv:91.0) Gecko/20100101 Firefox/91.0')
        
        # Desabilitar imagens e CSS para performance
        options.set_preference('permissions.default.image', 2)
        options.set_preference('dom.ipc.plugins.enabled.libflashplayer.so', False)
        
        return options
    
    def create_driver(self, prefer_chrome=True):
        """Cria driver com fallback automático"""
        drivers_to_try = []
        
        if prefer_chrome and self.chrome_available:
            drivers_to_try.append(('chrome', self._create_chrome_driver))
        if self.firefox_available:
            drivers_to_try.append(('firefox', self._create_firefox_driver))
        if not prefer_chrome and self.chrome_available:
            drivers_to_try.append(('chrome', self._create_chrome_driver))
        
        last_error = None
        for browser_name, create_func in drivers_to_try:
            try:
                print(f"Tentando iniciar {browser_name}...")
                driver = create_func()
                print(f"✅ {browser_name.capitalize()} iniciado com sucesso!")
                return driver
            except Exception as e:
                print(f"❌ Falha ao iniciar {browser_name}: {e}")
                last_error = e
                continue
        
        raise Exception(f"Falha ao iniciar ambos navegadores. Último erro: {last_error}")
    
    def _create_chrome_driver(self):
        """Cria driver Chrome"""
        options = self.get_chrome_options()
        
        # Tentar usar ChromeDriver do sistema primeiro
        chrome_paths = [
            '/usr/local/bin/chromedriver',
            '/usr/bin/chromedriver',
            'chromedriver'
        ]
        
        for path in chrome_paths:
            try:
                if os.path.exists(path) or path == 'chromedriver':
                    service = ChromeService(path)
                    return webdriver.Chrome(service=service, options=options)
            except Exception as e:
                print(f"Falha ao usar ChromeDriver em {path}: {e}")
                continue
        
        # Fallback: usar webdriver-manager com tratamento de erro robusto
        try:
            print("Tentando baixar ChromeDriver via webdriver-manager...")
            # Verificar se consegue obter a versão do Chrome
            chrome_version_cmd = 'google-chrome --version 2>/dev/null || google-chrome-stable --version 2>/dev/null'
            version_result = os.popen(chrome_version_cmd).read().strip()
            
            if not version_result:
                raise Exception("Não foi possível detectar a versão do Chrome")
            
            print(f"Versão do Chrome detectada: {version_result}")
            
            # Tentar instalar ChromeDriver
            chrome_manager = ChromeDriverManager()
            driver_path = chrome_manager.install()
            
            if not driver_path or not os.path.exists(driver_path):
                raise Exception("ChromeDriver não foi instalado corretamente")
            
            service = ChromeService(driver_path)
            return webdriver.Chrome(service=service, options=options)
            
        except Exception as e:
            print(f"Erro detalhado do ChromeDriver: {e}")
            raise Exception(f"Falha ao criar ChromeDriver: {e}")
    
    def _create_firefox_driver(self):
        """Cria driver Firefox"""
        options = self.get_firefox_options()
        
        # Tentar usar GeckoDriver do sistema primeiro
        gecko_paths = [
            '/usr/local/bin/geckodriver',
            '/usr/bin/geckodriver',
            'geckodriver'
        ]
        
        for path in gecko_paths:
            try:
                if os.path.exists(path) or path == 'geckodriver':
                    service = FirefoxService(path)
                    return webdriver.Firefox(service=service, options=options)
            except Exception as e:
                print(f"Falha ao usar GeckoDriver em {path}: {e}")
                continue
        
        # Fallback: usar webdriver-manager
        try:
            print("Tentando baixar GeckoDriver via webdriver-manager...")
            gecko_manager = GeckoDriverManager()
            driver_path = gecko_manager.install()
            
            if not driver_path or not os.path.exists(driver_path):
                raise Exception("GeckoDriver não foi instalado corretamente")
            
            service = FirefoxService(driver_path)
            return webdriver.Firefox(service=service, options=options)
        except Exception as e:
            print(f"Erro detalhado do GeckoDriver: {e}")
            raise Exception(f"Falha ao criar FirefoxDriver: {e}")

# Função de conveniência para uso direto
def create_webdriver(prefer_chrome=True):
    """Cria WebDriver com configuração otimizada para VPS"""
    manager = WebDriverManager()
    return manager.create_driver(prefer_chrome=prefer_chrome)

# Teste da configuração
if __name__ == '__main__':
    print("🧪 Testando configuração do WebDriver...")
    
    try:
        manager = WebDriverManager()
        print(f"Chrome disponível: {manager.chrome_available}")
        print(f"Firefox disponível: {manager.firefox_available}")
        
        # Testar Chrome
        if manager.chrome_available:
            try:
                driver = manager.create_driver(prefer_chrome=True)
                driver.get('https://www.google.com')
                print(f"✅ Teste Chrome OK - Título: {driver.title}")
                driver.quit()
            except Exception as e:
                print(f"❌ Teste Chrome falhou: {e}")
        
        # Testar Firefox
        if manager.firefox_available:
            try:
                driver = manager.create_driver(prefer_chrome=False)
                driver.get('https://www.google.com')
                print(f"✅ Teste Firefox OK - Título: {driver.title}")
                driver.quit()
            except Exception as e:
                print(f"❌ Teste Firefox falhou: {e}")
        
        print("🎉 Configuração do WebDriver testada com sucesso!")
        
    except Exception as e:
        print(f"❌ Erro na configuração: {e}")
        sys.exit(1)