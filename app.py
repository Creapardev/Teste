from flask import Flask, render_template, request, Response, jsonify, send_file
import csv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService
import time
import os
import json
import threading
from queue import Queue
import pandas as pd
from io import BytesIO
from datetime import datetime
import shutil
import urllib.parse
import requests

app = Flask(__name__)

# Fila para comunicação de progresso
progress_queue = Queue()
current_progress = {'step': '', 'progress': 0, 'total': 0, 'status': 'idle'}

# Configurações de webhook
webhook_config = {
    'url': '',
    'enabled': False,
    'headers': {},
    'batch_size': 10
}

# Variáveis globais para Google Maps scraping
progresso_maps = 0
total_resultados_maps = 0
status_maps = "idle"
mensagem_maps = ""
dados_maps = []
pagina_limite = 319
numero_da_pagina = 1

# --- FUNÇÕES DE PROGRESSO ---

def update_progress(step, progress, total, status='running'):
    global current_progress
    current_progress = {
        'step': step,
        'progress': progress,
        'total': total,
        'status': status,
        'percentage': int((progress / total * 100)) if total > 0 else 0
    }
    progress_queue.put(current_progress.copy())

# --- FUNÇÕES DE SCRAPING (ATUALIZADAS COM PROGRESSO) ---

def coletar_urls(url_base, scroll_infinite=True, link_selector="a[href*='consultor-imobiliario']"):
    update_progress("Iniciando navegador...", 0, 100)
    
    # Tentar Firefox primeiro para scraping web
    try:
        firefox_service = FirefoxService(GeckoDriverManager().install())
        driver = webdriver.Firefox(service=firefox_service)
    except Exception as firefox_error:
        print(f"Erro ao iniciar Firefox: {firefox_error}")
        # Fallback para Chrome
        try:
            options = webdriver.ChromeOptions()
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            chrome_service = ChromeService(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=chrome_service, options=options)
        except Exception as chrome_error:
            raise Exception(f"Falha ao iniciar ambos navegadores. Firefox: {firefox_error}, Chrome: {chrome_error}")
    urls_corretores = set()
    
    try:
        update_progress("Carregando página...", 10, 100)
        driver.get(url_base)
        time.sleep(3)
        
        if scroll_infinite:
            update_progress("Fazendo scroll infinito...", 20, 100)
            last_height = driver.execute_script("return document.body.scrollHeight")
            scroll_count = 0
            max_scrolls = 50
            
            while scroll_count < max_scrolls:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
                scroll_count += 1
                progress = 20 + (scroll_count / max_scrolls) * 40
                update_progress(f"Rolagem {scroll_count}/{max_scrolls}...", int(progress), 100)

        update_progress("Coletando links...", 70, 100)
        links_elementos = driver.find_elements(By.CSS_SELECTOR, link_selector)
        
        for link in links_elementos:
            href = link.get_attribute('href')
            if href:
                urls_corretores.add(href)
        
        update_progress(f"Encontrados {len(urls_corretores)} links únicos", 90, 100)
        return list(urls_corretores)

    except Exception as e:
        update_progress(f"Erro ao coletar URLs: {str(e)}", 0, 100, 'error')
        print(f"Ocorreu um erro ao coletar as URLs: {e}")
        return None

    finally:
        driver.quit()

def extrair_dados(urls, name_selector='.agent-name', phone_selector="a[href^='tel:']"):
    if not urls: return []
    
    update_progress("Iniciando extração de dados...", 0, len(urls))
    driver = webdriver.Firefox()
    dados_consultores = []
    
    # Converter seletores em listas
    seletores_nome = [s.strip() for s in name_selector.split(',')]
    seletores_telefone = [s.strip() for s in phone_selector.split(',')]
    
    try:
        for i, url in enumerate(urls):
            try:
                progress = 70 + (i / len(urls)) * 25
                update_progress(f"Extraindo dados {i+1}/{len(urls)}...", int(progress), 100)
                driver.get(url)
                time.sleep(2)
                
                # Tentar diferentes seletores para o nome
                nome = None
                for seletor in seletores_nome:
                    try:
                        elemento_nome = driver.find_element(By.CSS_SELECTOR, seletor)
                        nome = elemento_nome.text.strip()
                        if nome:
                            break
                    except:
                        continue
                
                # Tentar diferentes seletores para o telefone
                telefone = None
                for seletor in seletores_telefone:
                    try:
                        elemento_telefone = driver.find_element(By.CSS_SELECTOR, seletor)

                        telefone = ''.join(str(c) for c in elemento_telefone.text.strip() if c.isdigit())
                        if not telefone and seletor.startswith('a[href^="tel:"]'):
                            telefone = elemento_telefone.get_attribute('href').replace('tel:', '')
                        if telefone:
                            break
                    except:
                        continue
                
                if nome:
                    dados_consultores.append({
                        "nome": nome, 
                        "telefone": telefone or 'Não encontrado'
                    })
                
                print(dados_consultores)

            except Exception as e:
                print(f"Erro ao extrair dados de {url}: {e}")
                continue
        
        update_progress(f"Extração concluída! {len(dados_consultores)} registros extraídos.", len(urls), len(urls))
        return dados_consultores
    except Exception as e:
        update_progress(f"Erro durante extração: {str(e)}", 0, len(urls), 'error')
        print(f"Ocorreu um erro geral durante a extração: {e}")
        return None
    finally:
        driver.quit()

def enviar_webhook(dados):
    """Envia dados para webhook configurado"""
    if not webhook_config['enabled'] or not webhook_config['url'] or not dados:
        return
    
    try:
        # Enviar em lotes
        batch_size = webhook_config.get('batch_size', 10)
        headers = {'Content-Type': 'application/json'}
        headers.update(webhook_config.get('headers', {}))
        
        for i in range(0, len(dados), batch_size):
            lote = dados[i:i + batch_size]
            payload = {
                'timestamp': datetime.now().isoformat(),
                'total_records': len(lote),
                'batch_number': (i // batch_size) + 1,
                'data': lote
            }
            
            response = requests.post(
                webhook_config['url'],
                json=payload,
                headers=headers,
                timeout=30
            )
            
            if response.status_code != 200:
                print(f"Erro no webhook: {response.status_code} - {response.text}")
            else:
                print(f"Lote {(i // batch_size) + 1} enviado com sucesso para webhook")
                
    except Exception as e:
        print(f"Erro ao enviar webhook: {str(e)}")

def salvar_csv(dados):
    if not dados: return
    telefones_existentes = set()
    if os.path.exists('consultores.csv'):
        with open('consultores.csv', 'r', newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                telefones_existentes.add(row.get('telefone', '').strip())
    
    novos_registros = []
    for consultor in dados:
        telefone = consultor.get('telefone', '').strip()
        if telefone and telefone not in telefones_existentes:
            novos_registros.append(consultor)
            
    if not novos_registros: return
        
    modo = 'a' if os.path.exists('consultores.csv') else 'w'
    with open('consultores.csv', modo, newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=['nome', 'telefone'])
        if modo == 'w': writer.writeheader()
        writer.writerows(novos_registros)
    
    # Enviar para webhook após salvar
    enviar_webhook(novos_registros)

# --- FUNÇÕES ASSÍNCRONAS ---

def scraping_worker(url_base, scroll_infinite, remove_duplicates, link_selector=None, name_selector=None, phone_selector=None):
    """Função que executa o scraping em uma thread separada"""

    global numero_da_pagina, pagina_limite

    try:
        update_progress("Iniciando processo de scraping...", 0, 100)
        
        # Usar seletores padrão se não fornecidos
        if not link_selector:
            link_selector = "a[href*='/consultor/']"
        if not name_selector:
            name_selector = "h1.nome-consultor, .nome-consultor, h1"
        if not phone_selector:
            phone_selector = ".telefone, .phone, [href^='tel:'], .contato-telefone"
        
        urls = coletar_urls(url_base, scroll_infinite, link_selector)
        if urls:
            dados_finais = extrair_dados(urls, name_selector, phone_selector)
            if dados_finais:
                update_progress("Salvando dados...", 95, 100)
                salvar_csv(dados_finais)
                update_progress(f"Processo concluído! {len(dados_finais)} registros processados.", 100, 100, 'completed')
            else:
                update_progress("Nenhum dado foi extraído.", 0, 100, 'error')
        else:
            update_progress("Erro na coleta de URLs.", 0, 100, 'error')
        

        if url_base == "https://www.oportaldaconstrucao.com/diretorio/0/1" or url_base == f"https://www.oportaldaconstrucao.com/diretorio/0/{numero_da_pagina}" or url_base == "https://www.oportaldaconstrucao.com/diretorio/0/1/":
            nova_url = f"https://www.oportaldaconstrucao.com/diretorio/0/{numero_da_pagina + 1}"
            resposta = requests.get(nova_url)
            print(nova_url)
            print(resposta.status_code)

            numero_da_pagina += 1
            url_base = nova_url
            scraping_worker(url_base, scroll_infinite, remove_duplicates, link_selector, name_selector, phone_selector)

                


    except Exception as e:
        update_progress(f"Erro: {str(e)}", 0, 100, 'error')

# --- FUNÇÕES GOOGLE MAPS ---

def buscar_google_maps(termo_busca, max_resultados=200):
    """Busca estabelecimentos no Google Maps por termo de pesquisa"""
    global progresso_maps, total_resultados_maps, status_maps, mensagem_maps, dados_maps
    
    try:
        status_maps = "running"
        mensagem_maps = "Iniciando busca no Google Maps..."
        dados_maps = []
        
        # Configurar Firefox como navegador principal
        driver = None
        try:
            firefox_options = webdriver.FirefoxOptions()
            # Remover headless para ver o navegador funcionando
            # firefox_options.add_argument('--headless')
            firefox_service = FirefoxService(GeckoDriverManager().install())
            driver = webdriver.Firefox(service=firefox_service, options=firefox_options)
            mensagem_maps = "Firefox iniciado com sucesso!"
        except Exception as firefox_error:
            print(f"Erro ao iniciar Firefox: {firefox_error}")
            mensagem_maps = "Firefox falhou, tentando Chrome..."
            try:
                # Configurar Chrome como fallback
                options = webdriver.ChromeOptions()
                options.add_argument('--no-sandbox')
                options.add_argument('--disable-dev-shm-usage')
                options.add_argument('--disable-gpu')
                options.add_argument('--disable-web-security')
                options.add_argument('--allow-running-insecure-content')
                options.add_argument('--disable-extensions')
                options.add_argument('--disable-plugins')
                options.add_argument('--disable-images')
                options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
                chrome_service = ChromeService(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=chrome_service, options=options)
            except Exception as chrome_error:
                raise Exception(f"Falha ao iniciar ambos navegadores. Firefox: {firefox_error}, Chrome: {chrome_error}")
        
        # Acessar Google Maps
        mensagem_maps = "Acessando Google Maps..."
        driver.get("https://www.google.com/maps")
        time.sleep(3)
        
        # Buscar pelo termo
        mensagem_maps = f"Buscando por: {termo_busca}"
        try:
            search_box = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.ID, "searchboxinput"))
            )
            search_box.clear()
            search_box.send_keys(termo_busca)
            search_box.send_keys(Keys.ENTER)
            time.sleep(5)
        except TimeoutException:
            # Fallback: tentar outros seletores para a caixa de busca
            try:
                search_box = driver.find_element(By.CSS_SELECTOR, "input[placeholder*='Pesquisar'], input[placeholder*='Search'], #searchboxinput")
                search_box.clear()
                search_box.send_keys(termo_busca)
                search_box.send_keys(Keys.ENTER)
                time.sleep(5)
            except Exception as e:
                raise Exception(f"Não foi possível encontrar a caixa de busca: {e}")
        
        # Aguardar resultados aparecerem - seletores atualizados 2024
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".bfdHYd, .Nv2PK, .hfpxzc .hH0dDd"))
            )
            print("Resultados carregados com sucesso!")
        except TimeoutException:
            print("Timeout aguardando resultados. Tentando continuar...")
            # Tentar aguardar um pouco mais com seletores alternativos
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "[role='article'], div[jsaction*='mouseover'], a[data-cid]"))
                )
                print("Resultados encontrados com seletores alternativos!")
            except TimeoutException:
                print("Nenhum resultado encontrado após timeout. Continuando mesmo assim...")
            time.sleep(5)
        
        mensagem_maps = "Coletando dados dos estabelecimentos..."
        resultados_coletados = 0
        total_resultados_maps = max_resultados
        
        # Set para evitar duplicações baseado no nome do estabelecimento
        nomes_processados = set()
        elementos_processados = set()
        
        # Scroll para carregar mais resultados
        for scroll in range(50):  # Aumentado para 50 scrolls para mais coleta
            if resultados_coletados >= max_resultados:
                break

            # Encontrar elementos de estabelecimentos usando seletores atualizados 2024
            estabelecimentos = driver.find_elements(By.CSS_SELECTOR, ".bfdHYd, .Nv2PK, .hfpxzc, .hH0dDd, [data-result-index]")

            # Se não encontrou com os seletores principais, tentar seletores alternativos
            if not estabelecimentos:
                print(f"Tentativa {scroll + 1}: Nenhum estabelecimento encontrado com seletores principais. Tentando seletores alternativos...")
                estabelecimentos = driver.find_elements(By.CSS_SELECTOR, "[role='article'], div[jsaction*='mouseover'], a[data-cid], .lI9IFe")
                
            # Último fallback: tentar seletores mais genéricos
            if not estabelecimentos:
                print(f"Tentativa {scroll + 1}: Tentando seletores genéricos...")
                estabelecimentos = driver.find_elements(By.CSS_SELECTOR, "div[data-result-index], div[jsaction], a[href*='/maps/place/']")
                
            if not estabelecimentos:
                print(f"Tentativa {scroll + 1}: Nenhum estabelecimento encontrado. Aguardando mais tempo...")
                time.sleep(3)
                continue
                
            print(f"Tentativa {scroll + 1}: Encontrados {len(estabelecimentos)} estabelecimentos")
            
            # Processar apenas novos estabelecimentos
            novos_estabelecimentos = 0
            for i, estabelecimento in enumerate(estabelecimentos):
                if resultados_coletados >= max_resultados:
                    break
                
                # Criar identificador único para o elemento (mais flexível)
                try:
                    elemento_id = estabelecimento.get_attribute('data-cid') or estabelecimento.get_attribute('data-result-index')
                    if not elemento_id:
                        # Usar texto do elemento como ID se não tiver atributos únicos
                        try:
                            texto_elemento = estabelecimento.text[:50] if estabelecimento.text else f"elemento_{scroll}_{i}"
                            elemento_id = f"{scroll}_{i}_{hash(texto_elemento)}"
                        except:
                            elemento_id = f"elemento_{scroll}_{i}"
                    
                    if elemento_id in elementos_processados:
                        continue  # Pular elementos já processados
                    
                    elementos_processados.add(elemento_id)
                except Exception as e:
                    # Fallback: usar posição única baseada em scroll e índice
                    elemento_id = f"fallback_{scroll}_{i}"
                    if elemento_id in elementos_processados:
                        continue
                    elementos_processados.add(elemento_id)
                    
                try:
                    # Primeiro, verificar se o driver ainda está conectado
                    try:
                        driver.current_url  # Teste de conectividade
                    except Exception as conn_error:
                        print(f"Erro de conexão detectado: {conn_error}")
                        # Tentar reconectar ou pular este elemento
                        continue
                    
                    # Clicar no estabelecimento para abrir os detalhes
                    click_success = False
                    try:
                        # Método 1: JavaScript click
                        driver.execute_script("arguments[0].scrollIntoView(true);", estabelecimento)
                        time.sleep(0.5)
                        driver.execute_script("arguments[0].click();", estabelecimento)
                        time.sleep(2)
                        click_success = True
                        print(f"Clicou no estabelecimento {i+1} para abrir detalhes")
                    except Exception as click_error:
                        print(f"Erro ao clicar no estabelecimento {i+1}: {click_error}")
                        # Método 2: Selenium click direto
                        try:
                            estabelecimento.click()
                            time.sleep(2)
                            click_success = True
                            print(f"Clicou no estabelecimento {i+1} (método direto)")
                        except Exception as direct_click_error:
                            print(f"Erro no clique direto: {direct_click_error}")
                            # Método 3: ActionChains
                            try:
                                from selenium.webdriver.common.action_chains import ActionChains
                                actions = ActionChains(driver)
                                actions.move_to_element(estabelecimento).click().perform()
                                time.sleep(2)
                                click_success = True
                                print(f"Clicou no estabelecimento {i+1} (ActionChains)")
                            except Exception as action_error:
                                print(f"Erro com ActionChains: {action_error}")
                                print(f"Não foi possível clicar no estabelecimento {i+1}")
                    
                    # Se não conseguiu clicar, tentar extrair dados sem clicar
                    if not click_success:
                        print(f"Tentando extrair dados sem clicar no estabelecimento {i+1}")
                    
                    # Extrair dados do estabelecimento
                    dados_estabelecimento = extrair_dados_estabelecimento(driver, estabelecimento)
                    if dados_estabelecimento and dados_estabelecimento.get('nome'):
                        nome = dados_estabelecimento['nome'].strip()
                        nome_normalizado = nome.lower()
                        
                        # Filtrar nomes inválidos ANTES de processar
                        nomes_invalidos = ['resultados', 'maps', 'google', 'pesquisar', 'resultado', 'estabelecimentos', 'nome não encontrado']
                        if nome_normalizado in nomes_invalidos or len(nome) < 3:
                            print(f"✗ Nome inválido rejeitado: {nome}")
                            continue
                        
                        # Verificar duplicação por nome (normalizado)
                        if nome_normalizado not in nomes_processados:
                            nomes_processados.add(nome_normalizado)
                            dados_maps.append(dados_estabelecimento)
                            resultados_coletados += 1
                            novos_estabelecimentos += 1
                            progresso_maps = int((resultados_coletados / max_resultados) * 100)
                            mensagem_maps = f"Coletados {resultados_coletados} de {max_resultados} estabelecimentos únicos"
                            print(f"✓ Adicionado: {nome} (Total: {resultados_coletados})")
                        else:
                            print(f"✗ Duplicado ignorado: {nome}")
                        
                except Exception as e:
                    print(f"Erro ao extrair dados do estabelecimento {i+1}: {e}")
                    continue
            
            print(f"Scroll {scroll + 1}: {novos_estabelecimentos} novos estabelecimentos adicionados")
            
            # Verificar se há mais estabelecimentos disponíveis na página
            try:
                # Contar total de estabelecimentos visíveis na página
                todos_estabelecimentos_visiveis = driver.find_elements(By.CSS_SELECTOR, 
                    "[data-result-index], .hfpxzc, .Nv2PK .TFQHme, .bfdHYd .fontBodyMedium, .lI9IFe, .yuRUbf")
                total_visiveis = len(todos_estabelecimentos_visiveis)
                print(f"Total de estabelecimentos visíveis na página: {total_visiveis}")
                
                # Verificar se há indicação de mais resultados
                mais_resultados_disponiveis = False
                try:
                    # Procurar por indicadores de que há mais resultados
                    indicadores_mais = driver.find_elements(By.CSS_SELECTOR, 
                        "[data-value='Mostrar mais resultados'], .HlvSq, .n7lv7yjyC35__root, [aria-label*='mais'], [aria-label*='more']")
                    if indicadores_mais:
                        mais_resultados_disponiveis = True
                        print("Detectados indicadores de mais resultados disponíveis")
                except:
                    pass
                    
                # Verificar se a página ainda está carregando
                try:
                    loading_elements = driver.find_elements(By.CSS_SELECTOR, 
                        ".loading, [aria-label*='Carregando'], [aria-label*='Loading'], .spinner")
                    if loading_elements:
                        print("Página ainda carregando, aguardando...")
                        time.sleep(2)
                except:
                    pass
                    
            except Exception as check_error:
                print(f"Erro ao verificar estabelecimentos disponíveis: {check_error}")
                total_visiveis = 0
                mais_resultados_disponiveis = False
            
            # Se não encontrou novos estabelecimentos, contar scrolls consecutivos
            if novos_estabelecimentos == 0:
                if not hasattr(buscar_google_maps, 'scrolls_sem_novos'):
                    buscar_google_maps.scrolls_sem_novos = 0
                buscar_google_maps.scrolls_sem_novos += 1
                
                # Lógica mais inteligente para determinar quando parar
                if total_visiveis > resultados_coletados and mais_resultados_disponiveis:
                    # Há mais estabelecimentos visíveis que não foram coletados
                    limite_scrolls = 30  # Mais tentativas quando há elementos não coletados
                    print(f"Há {total_visiveis - resultados_coletados} estabelecimentos não coletados, continuando...")
                elif resultados_coletados < 15:
                    limite_scrolls = 25  # Mais tentativas quando poucos resultados
                else:
                    limite_scrolls = 15  # Limite normal
                    
                print(f"Scroll sem novos estabelecimentos: {buscar_google_maps.scrolls_sem_novos}/{limite_scrolls}")
                
                if buscar_google_maps.scrolls_sem_novos >= limite_scrolls:
                    print(f"Parando: {buscar_google_maps.scrolls_sem_novos} scrolls consecutivos sem novos estabelecimentos")
                    print(f"Coletados: {resultados_coletados}, Visíveis: {total_visiveis}, Mais disponíveis: {mais_resultados_disponiveis}")
                    break
            else:
                buscar_google_maps.scrolls_sem_novos = 0
                print(f"Reset contador: encontrados {novos_estabelecimentos} novos estabelecimentos")
            
            # Scroll para carregar mais com estratégias diferentes
            if resultados_coletados < max_resultados:
                try:
                    # Tentar diferentes estratégias de scroll
                    scroll_container = driver.find_element(By.CSS_SELECTOR, "[role='main'], .m6QErb, .Nv2PK")
                    
                    # Estratégias mais agressivas quando há poucos resultados
                    if resultados_coletados < 15:
                        # Estratégia agressiva: múltiplos scrolls pequenos
                        if scroll % 4 == 0:
                            for i in range(3):
                                current_scroll = driver.execute_script("return arguments[0].scrollTop", scroll_container)
                                driver.execute_script("arguments[0].scrollTop = arguments[1] + 400", scroll_container, current_scroll)
                                time.sleep(0.5)
                        # Estratégia agressiva: scroll até o final múltiplas vezes
                        elif scroll % 4 == 1:
                            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", scroll_container)
                            time.sleep(1)
                            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollTop - 300", scroll_container)
                            time.sleep(0.5)
                            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", scroll_container)
                        # Estratégia agressiva: scroll com Page Down
                        elif scroll % 4 == 2:
                            scroll_container.send_keys(Keys.PAGE_DOWN)
                            time.sleep(0.5)
                            scroll_container.send_keys(Keys.PAGE_DOWN)
                        # Estratégia agressiva: scroll gradual rápido
                        else:
                            current_scroll = driver.execute_script("return arguments[0].scrollTop", scroll_container)
                            driver.execute_script("arguments[0].scrollTop = arguments[1] + 1200", scroll_container, current_scroll)
                    else:
                        # Estratégias normais quando já tem resultados suficientes
                        if scroll % 3 == 0:
                            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", scroll_container)
                        elif scroll % 3 == 1:
                            current_scroll = driver.execute_script("return arguments[0].scrollTop", scroll_container)
                            driver.execute_script("arguments[0].scrollTop = arguments[1] + 800", scroll_container, current_scroll)
                        else:
                            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", scroll_container)
                            time.sleep(1)
                            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollTop - 200", scroll_container)
                        
                except Exception as scroll_error:
                    print(f"Erro no scroll principal: {scroll_error}")
                    # Fallback: scroll da página
                    try:
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    except:
                        # Último fallback: usar teclas
                        try:
                            driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.END)
                        except:
                            pass
                            
                # Tempo de espera variável: menor quando há poucos resultados
                if resultados_coletados < 15:
                    wait_time = min(4, 2 + (scroll // 15))  # Mais rápido quando poucos resultados
                else:
                    wait_time = min(6, 3 + (scroll // 10))  # Normal quando já tem resultados
                time.sleep(wait_time)
        
        driver.quit()
        
        # Salvar dados
        salvar_dados_maps(termo_busca)
        
        status_maps = "completed"
        mensagem_maps = f"Busca concluída! {len(dados_maps)} estabelecimentos encontrados."
        
    except Exception as e:
        status_maps = "error"
        mensagem_maps = f"Erro durante a busca: {str(e)}"
        if 'driver' in locals():
            driver.quit()

def extrair_dados_estabelecimento(driver, elemento):
    """Extrai dados de um estabelecimento do Google Maps"""
    try:
        dados = {}
        
        # Tentar extrair dados do painel lateral (após clique)
        try:
            # Aguardar o painel lateral carregar
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "[role='main'], .m6QErb, .TIHn2"))
            )
        except:
            pass
        
        # Nome do estabelecimento - buscar com seletores atualizados do Google Maps 2024
        try:
            # Tentar no painel lateral com seletores mais específicos e atualizados
            nome_elem = driver.find_element(By.CSS_SELECTOR, "[role='main'] h1[data-attrid='title'], [role='main'] h1.x3AX1-LfntMc-header-title-title, [role='main'] .x3AX1-LfntMc-header-title-title, [role='main'] h1.DUwDvf.lfPIob, [role='main'] .DUwDvf.lfPIob, [role='main'] h1")
            nome_text = nome_elem.text.strip()
            print(f"1 - {nome_text}")
            # Filtrar nomes inválidos com validação mais rigorosa
            nomes_invalidos = ['resultados', 'maps', 'google', 'pesquisar', 'resultado', 'estabelecimentos', 'pesquisa', 'buscar']
            if (nome_text and len(nome_text) >= 3 and len(nome_text) <= 100 and 
                nome_text.lower() not in nomes_invalidos and
                not nome_text.lower().startswith('resultado') and
                not nome_text.lower().startswith('pesquis') and
                not nome_text.isdigit() and
                not nome_text.startswith('http')):
                dados['nome'] = nome_text
            else:
                raise Exception("Nome inválido encontrado")
        except:
            try:
                # Fallback: buscar no elemento original da lista com seletores atualizados
                nome_elem = elemento.find_element(By.CSS_SELECTOR, ".qBF1Pd.fontHeadlineSmall, .hfpxzc, .NrDZNb, .qBF1Pd, [data-value='Título'], .fontHeadlineSmall")
                nome_text = nome_elem.text.strip()
                print(f"2 - {nome_text}")
                # Aplicar mesma validação rigorosa
                nomes_invalidos = ['resultados', 'maps', 'google', 'pesquisar', 'resultado', 'estabelecimentos', 'pesquisa', 'buscar']
                if (nome_text and len(nome_text) >= 3 and len(nome_text) <= 100 and 
                    nome_text.lower() not in nomes_invalidos and
                    not nome_text.lower().startswith('resultado') and
                    not nome_text.lower().startswith('pesquis') and
                    not nome_text.isdigit() and
                    not nome_text.startswith('http')):
                    dados['nome'] = nome_text
                else:
                    raise Exception("Nome inválido encontrado")
            except:
                try:
                    # Terceiro fallback: buscar por aria-label ou title
                    nome_elem = elemento.find_element(By.CSS_SELECTOR, "[aria-label]:not([aria-label*='Resultado']):not([aria-label*='resultado']), [title]:not([title*='Resultado']):not([title*='resultado'])")
                    nome_text = nome_elem.get_attribute('aria-label') or nome_elem.get_attribute('title') or nome_elem.text.strip()
                    print(f"3 - {nome_text}")
                    # Aplicar validação rigorosa
                    nomes_invalidos = ['resultados', 'maps', 'google', 'pesquisar', 'resultado', 'estabelecimentos', 'pesquisa', 'buscar']
                    if (nome_text and len(nome_text) >= 3 and len(nome_text) <= 100 and 
                        nome_text.lower() not in nomes_invalidos and
                        not nome_text.lower().startswith('resultado') and
                        not nome_text.lower().startswith('pesquis') and
                        not nome_text.startswith('http') and not nome_text.isdigit() and
                        not any(char in nome_text for char in ['★', '·'])):
                        dados['nome'] = nome_text
                    else:
                        raise Exception("Nome inválido encontrado")
                except:
                    try:
                        # Último fallback: buscar por qualquer texto que pareça um nome válido
                        nome_elems = driver.find_elements(By.CSS_SELECTOR, "h1, h2, h3, .DUwDvf, .lfPIob, .hfpxzc, .qBF1Pd, .NrDZNb, a[href*='/maps/place/']")
                        for elem in nome_elems:
                            text = elem.text.strip()
                            print(f"4 - {text}")
                            # Aplicar validação rigorosa e consistente
                            nomes_invalidos = ['resultados', 'maps', 'google', 'pesquisar', 'resultado', 'estabelecimentos', 'pesquisa', 'buscar']
                            if (text and len(text) >= 3 and len(text) <= 100 and 
                                text.lower() not in nomes_invalidos and
                                not text.lower().startswith('resultado') and
                                not text.lower().startswith('pesquis') and
                                not text.startswith('http') and not text.isdigit() and
                                not any(char in text for char in ['★', '·'])):
                                dados['nome'] = text
                                break
                        else:
                            dados['nome'] = "Nome não encontrado"
                    except:
                        dados['nome'] = "Nome não encontrado"
        
        # Avaliação - buscar no painel lateral primeiro com classes atualizadas
        try:
            # Tentar no painel lateral com as classes específicas
            avaliacao_elem = driver.find_element(By.CSS_SELECTOR, "[role='main'] .Io6YTe.fontBodyMedium.kR99db.fdkmkc, [role='main'] .MW4etd, [role='main'] span[aria-label*='estrela']")
            avaliacao_text = avaliacao_elem.text.strip() or avaliacao_elem.get_attribute('aria-label')
            
            # Extrair apenas o número da avaliação
            import re
            avaliacao_match = re.search(r'(\d+[,.]\d+)', avaliacao_text)
            if avaliacao_match:
                dados['avaliacao'] = avaliacao_match.group(1).replace(',', '.')
            else:
                dados['avaliacao'] = avaliacao_text if avaliacao_text else "N/A"
        except:
            try:
                # Fallback: buscar no elemento original
                avaliacao_elem = elemento.find_element(By.CSS_SELECTOR, ".Io6YTe.fontBodyMedium.kR99db.fdkmkc, .MW4etd")
                avaliacao_text = avaliacao_elem.text.strip()
                
                # Extrair número da avaliação
                import re
                avaliacao_match = re.search(r'(\d+[,.]\d+)', avaliacao_text)
                dados['avaliacao'] = avaliacao_match.group(1).replace(',', '.') if avaliacao_match else "N/A"
            except:
                try:
                    # Último fallback: procurar por padrões de avaliação usando as classes específicas
                    avaliacao_elems = driver.find_elements(By.CSS_SELECTOR, ".Io6YTe, .fontBodyMedium, .kR99db, .fdkmkc, span[aria-label*='estrela'], span[aria-label*='star'], [data-value='Classificação']")
                    for elem in avaliacao_elems:
                        text = elem.text.strip() or elem.get_attribute('aria-label')
                        import re
                        if re.search(r'\d+[,.]\d+', text) and ('★' in text or len(text) < 10):
                            rating_match = re.search(r'(\d+[,.]\d+)', text)
                            if rating_match:
                                dados['avaliacao'] = rating_match.group(1).replace(',', '.')
                                break
                    else:
                        dados['avaliacao'] = "N/A"
                except:
                    dados['avaliacao'] = "N/A"
        
        # Endereço - buscar no painel lateral primeiro com classes atualizadas
        try:
            # Tentar no painel lateral com as classes específicas
            endereco_elem = driver.find_element(By.CSS_SELECTOR, "[role='main'] .Io6YTe.fontBodyMedium.kR99db.fdkmkc, [role='main'] [data-item-id='address'], [role='main'] .Io6YTe")
            dados['endereco'] = endereco_elem.text.strip().replace('·', '').strip()
        except:
            try:
                # Fallback: buscar no elemento original
                endereco_elem = elemento.find_element(By.CSS_SELECTOR, ".Io6YTe.fontBodyMedium.kR99db.fdkmkc, .W4Efsd:last-child > .W4Efsd:nth-of-type(1) > span:last-child")
                dados['endereco'] = endereco_elem.text.strip().replace('·', '').strip()
            except:
                try:
                    # Último fallback: procurar por elementos que contenham endereços
                    endereco_elems = driver.find_elements(By.CSS_SELECTOR, ".Io6YTe, .fontBodyMedium, .kR99db, .fdkmkc, .W4Efsd, [data-value='Endereço'], [role='main'] .fontBodyMedium")
                    for elem in endereco_elems:
                        text = elem.text.strip().replace('·', '').strip()
                        if text and any(word in text.lower() for word in ['rua', 'av', 'avenida', 'street', 'road', 'br-', 'km', 'r.', 'alameda']):
                            dados['endereco'] = text
                            break
                    else:
                        dados['endereco'] = "Endereço não encontrado"
                except:
                    dados['endereco'] = "Endereço não encontrado"
        
        # Telefone - buscar no painel lateral primeiro com classes atualizadas
        try:
            # Tentar no painel lateral com as classes específicas
            telefone_elem = driver.find_element(By.CSS_SELECTOR, "[role='main'] .Io6YTe.fontBodyMedium.kR99db.fdkmkc, [role='main'] [data-item-id='phone'], [role='main'] .UsdlK, [role='main'] [aria-label*='telefone']")
            telefone_text = telefone_elem.text.strip() or telefone_elem.get_attribute('aria-label')
            
            # Usar regex para extrair números de telefone
            import re
            telefone_match = re.search(r'\(?\d{2}\)?\s?\d{4,5}-?\d{4}', telefone_text)
            if telefone_match:
                dados['telefone'] = telefone_match.group()
            else:
                dados['telefone'] = telefone_text if telefone_text else "N/A"
        except:
            try:
                # Fallback: buscar no elemento original
                telefone_elem = elemento.find_element(By.CSS_SELECTOR, ".Io6YTe.fontBodyMedium.kR99db.fdkmkc, [data-value='Número de telefone'], [href^='tel:'], .UsdlK")
                telefone_text = telefone_elem.text.strip() or telefone_elem.get_attribute('href').replace('tel:', '')
                dados['telefone'] = telefone_text
            except:
                try:
                    # Último fallback: procurar por padrões de telefone no texto
                    telefone_elems = driver.find_elements(By.CSS_SELECTOR, ".Io6YTe, .fontBodyMedium, .kR99db, .fdkmkc")
                    for elem in telefone_elems:
                        text = elem.text.strip()
                        import re
                        if re.search(r'\(?\d{2}\)?\s?\d{4,5}-?\d{4}', text):
                            dados['telefone'] = text
                            break
                    else:
                        dados['telefone'] = "N/A"
                except:
                    dados['telefone'] = "N/A"
        
        # Tipo de estabelecimento - buscar no painel lateral primeiro com classes atualizadas
        try:
            # Tentar no painel lateral com as classes específicas
            tipo_elem = driver.find_element(By.CSS_SELECTOR, "[role='main'] .Io6YTe.fontBodyMedium.kR99db.fdkmkc, [role='main'] .DkEaL, [role='main'] [data-value='Categoria']")
            tipo_text = tipo_elem.text.strip()
            
            # Verificar se não é um endereço (evitar confusão)
            if not any(word in tipo_text.lower() for word in ['rua', 'av', 'avenida', 'street', 'road', 'br-', 'km']):
                dados['tipo'] = tipo_text
            else:
                dados['tipo'] = "N/A"
        except:
            try:
                # Fallback: buscar no elemento original
                tipo_elem = elemento.find_element(By.CSS_SELECTOR, ".Io6YTe.fontBodyMedium.kR99db.fdkmkc, .W4Efsd:first-child, [data-value='Categoria'], .W4Efsd.VkLyEb:first-child")
                dados['tipo'] = tipo_elem.text.strip()
            except:
                try:
                    # Último fallback: pegar elementos que não sejam endereço
                    tipo_elems = driver.find_elements(By.CSS_SELECTOR, ".Io6YTe, .fontBodyMedium, .kR99db, .fdkmkc, .W4Efsd")
                    for elem in tipo_elems:
                        text = elem.text.strip()
                        if text and len(text) < 50 and not any(word in text.lower() for word in ['rua', 'av', 'avenida', 'street', 'road', 'br-', 'km', '·']):
                            dados['tipo'] = text
                            break
                    else:
                        dados['tipo'] = "N/A"
                except:
                    dados['tipo'] = "N/A"
        
        # Horário de funcionamento (se disponível)
        try:
            horario_elem = elemento.find_element(By.CSS_SELECTOR, ".hH0dDd, [data-value='Horários'], .hH0dDd")
            dados['horario'] = horario_elem.text.strip()
            print(f"hora - {horario_elem.text.strip()}")
        except:
            dados['horario'] = "N/A"
        
        return dados if dados.get('nome') and dados['nome'] != "Nome não encontrado" else None
        
    except Exception as e:
        print(f"Erro ao extrair dados: {e}")
        return None

def salvar_dados_maps(termo_busca):
    """Salva os dados do Google Maps em arquivo CSV com deduplicação final"""
    global dados_maps
    
    if not dados_maps:
        return
    
    # Deduplicação final baseada no nome (case-insensitive)
    dados_unicos = []
    nomes_vistos = set()
    
    for estabelecimento in dados_maps:
        nome_normalizado = estabelecimento.get('nome', '').strip().lower()
        if nome_normalizado and nome_normalizado not in nomes_vistos and nome_normalizado != "nome não encontrado":
            nomes_vistos.add(nome_normalizado)
            dados_unicos.append(estabelecimento)
        else:
            print(f"Duplicata removida na gravação: {estabelecimento.get('nome', 'Nome não encontrado')}")
    
    # Atualizar dados_maps com dados únicos
    dados_maps = dados_unicos
    
    # Nome do arquivo baseado no termo de busca
    nome_arquivo = f"google_maps_{termo_busca.replace(' ', '_').replace('/', '_')}.csv"
    
    # Salvar em CSV
    with open(nome_arquivo, 'w', newline='', encoding='utf-8') as arquivo:
        fieldnames = ['nome', 'avaliacao', 'endereco', 'telefone', 'tipo', 'horario']
        writer = csv.DictWriter(arquivo, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(dados_unicos)
    
    print(f"Dados salvos: {len(dados_unicos)} estabelecimentos únicos em {nome_arquivo}")
    
    # Enviar via webhook se configurado
    if dados_unicos:
        enviar_webhook(dados_unicos)

# --- ROTAS DA INTERFACE WEB ---

@app.route('/')
def index():
    # Contar registros existentes
    total_registros = 0
    if os.path.exists('consultores.csv'):
        with open('consultores.csv', 'r', newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            total_registros = sum(1 for row in reader)
    
    return render_template('index.html', total_registros=total_registros, novos_registros=0)

@app.route('/scrape', methods=['POST'])
def scrape():
    url_base = request.form['url']
    scroll_infinite = 'scroll_infinite' in request.form
    remove_duplicates = 'remove_duplicates' in request.form
    
    # Obter seletores CSS personalizados
    link_selector = request.form.get('link_selector', '').strip()
    name_selector = request.form.get('name_selector', '').strip()
    phone_selector = request.form.get('phone_selector', '').strip()
    
    # Limpar progresso anterior
    global current_progress
    current_progress = {'step': '', 'progress': 0, 'total': 0, 'status': 'idle'}
    
    # Iniciar scraping em thread separada
    thread = threading.Thread(target=scraping_worker, args=(url_base, scroll_infinite, remove_duplicates, link_selector, name_selector, phone_selector))
    thread.daemon = True
    thread.start()
    
    return jsonify({'status': 'started', 'message': 'Scraping iniciado com sucesso!'})

@app.route('/progress')
def progress():
    """Endpoint para Server-Sent Events"""
    def generate():
        while True:
            try:
                # Pegar progresso da fila (com timeout)
                progress_data = progress_queue.get(timeout=1)
                yield f"data: {json.dumps(progress_data)}\n\n"
                
                # Se o processo foi concluído ou teve erro, parar
                if progress_data['status'] in ['completed', 'error']:
                    break
                    
            except:
                # Se não há dados na fila, enviar o progresso atual
                yield f"data: {json.dumps(current_progress)}\n\n"
                time.sleep(1)
    
    return Response(generate(), mimetype='text/event-stream')

@app.route('/status')
def status():
    """Endpoint para verificar status atual"""
    # Contar registros atuais
    total_registros = 0
    if os.path.exists('consultores.csv'):
        with open('consultores.csv', 'r', newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            total_registros = sum(1 for row in reader)
    
    return jsonify({
         'current_progress': current_progress,
         'total_registros': total_registros
     })

@app.route('/download/<format_type>')
def download_data(format_type):
    """Endpoint para download dos dados em diferentes formatos"""
    if not os.path.exists('consultores.csv'):
        return jsonify({'error': 'Nenhum dado disponível para download'}), 404
    
    try:
        # Ler dados do CSV
        dados = []
        with open('consultores.csv', 'r', newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            dados = list(reader)
        
        if not dados:
            return jsonify({'error': 'Nenhum dado encontrado'}), 404
        
        if format_type == 'csv':
            return send_file('consultores.csv', as_attachment=True, download_name='consultores.csv')
        
        elif format_type == 'json':
            # Criar arquivo JSON temporário
            json_data = json.dumps(dados, ensure_ascii=False, indent=2)
            json_buffer = BytesIO(json_data.encode('utf-8'))
            json_buffer.seek(0)
            
            return send_file(
                json_buffer,
                as_attachment=True,
                download_name='consultores.json',
                mimetype='application/json'
            )
        
        elif format_type == 'excel':
            # Criar arquivo Excel temporário
            df = pd.DataFrame(dados)
            excel_buffer = BytesIO()
            
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Consultores', index=False)
            
            excel_buffer.seek(0)
            
            return send_file(
                excel_buffer,
                as_attachment=True,
                download_name='consultores.xlsx',
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
        
        else:
            return jsonify({'error': 'Formato não suportado'}), 400
    
    except Exception as e:
        return jsonify({'error': f'Erro ao gerar arquivo: {str(e)}'}), 500

@app.route('/search_data')
def search_data():
    """Endpoint para pesquisar dados no arquivo CSV"""
    query = request.args.get('q', '').lower().strip()
    
    if not os.path.exists('consultores.csv'):
        return jsonify({'error': 'Nenhum arquivo de dados encontrado', 'data': []})
    
    try:
        dados = []
        with open('consultores.csv', 'r', newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                if not query or query in row.get('nome', '').lower() or query in row.get('telefone', '').lower():
                    dados.append(row)
        
        return jsonify({
            'data': dados,
            'total': len(dados),
            'query': query
        })
    
    except Exception as e:
        return jsonify({'error': f'Erro ao pesquisar dados: {str(e)}', 'data': []})

@app.route('/clean_duplicates', methods=['POST'])
def clean_duplicates():
    """Endpoint para limpar registros duplicados"""
    if not os.path.exists('consultores.csv'):
        return jsonify({'error': 'Nenhum arquivo de dados encontrado'}), 404
    
    try:
        # Ler dados existentes
        dados_originais = []
        with open('consultores.csv', 'r', newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            dados_originais = list(reader)
        
        if not dados_originais:
            return jsonify({'error': 'Nenhum dado encontrado no arquivo'}), 404
        
        # Remover duplicatas baseado no nome (case-insensitive)
        dados_unicos = []
        nomes_vistos = set()
        
        for registro in dados_originais:
            nome_normalizado = registro.get('nome', '').strip().lower()
            if nome_normalizado and nome_normalizado not in nomes_vistos:
                nomes_vistos.add(nome_normalizado)
                dados_unicos.append(registro)
        
        # Criar backup do arquivo original
        backup_filename = f'consultores_backup_{int(time.time())}.csv'
        os.rename('consultores.csv', backup_filename)
        
        # Salvar dados limpos
        with open('consultores.csv', 'w', newline='', encoding='utf-8') as file:
            if dados_unicos:
                fieldnames = dados_unicos[0].keys()
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(dados_unicos)
        
        duplicatas_removidas = len(dados_originais) - len(dados_unicos)
        
        return jsonify({
            'success': True,
            'message': f'Limpeza concluída! {duplicatas_removidas} duplicatas removidas.',
            'registros_originais': len(dados_originais),
            'registros_finais': len(dados_unicos),
            'duplicatas_removidas': duplicatas_removidas,
            'backup_file': backup_filename
        })
    
    except Exception as e:
        return jsonify({'error': f'Erro ao limpar duplicatas: {str(e)}'}), 500

@app.route('/clean_duplicates_maps', methods=['POST'])
def clean_duplicates_maps():
    """Endpoint para limpar registros duplicados do Google Maps"""
    # Buscar arquivos do Google Maps
    arquivos_maps = [f for f in os.listdir('.') if f.startswith('google_maps_') and f.endswith('.csv')]
    
    if not arquivos_maps:
        return jsonify({'error': 'Nenhum arquivo do Google Maps encontrado'}), 404
    
    try:
        resultados = []
        
        for arquivo in arquivos_maps:
            # Ler dados existentes
            dados_originais = []
            with open(arquivo, 'r', newline='', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                dados_originais = list(reader)
            
            if not dados_originais:
                continue
            
            # Remover duplicatas baseado no nome (case-insensitive)
            dados_unicos = []
            nomes_vistos = set()
            
            for registro in dados_originais:
                nome_normalizado = registro.get('nome', '').strip().lower()
                if nome_normalizado and nome_normalizado not in nomes_vistos and nome_normalizado != "nome não encontrado":
                    nomes_vistos.add(nome_normalizado)
                    dados_unicos.append(registro)
            
            # Criar backup do arquivo original
            backup_filename = f'{arquivo.replace(".csv", "")}_backup_{int(time.time())}.csv'
            os.rename(arquivo, backup_filename)
            
            # Salvar dados limpos
            with open(arquivo, 'w', newline='', encoding='utf-8') as file:
                if dados_unicos:
                    fieldnames = dados_unicos[0].keys()
                    writer = csv.DictWriter(file, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(dados_unicos)
            
            resultados.append({
                'arquivo': arquivo,
                'original_count': len(dados_originais),
                'duplicates_removed': len(dados_originais) - len(dados_unicos),
                'final_count': len(dados_unicos),
                'backup_file': backup_filename
            })
        
        return jsonify({
            'success': True,
            'message': f'Duplicatas removidas de {len(resultados)} arquivo(s) do Google Maps!',
            'results': resultados
        })
        
    except Exception as e:
        return jsonify({'error': f'Erro ao processar arquivos: {str(e)}'}), 500

# --- ROTAS GOOGLE MAPS ---

@app.route('/scrape_maps', methods=['POST'])
def scrape_maps():
    """Inicia o scraping do Google Maps"""
    global status_maps
    
    if status_maps == "running":
        return jsonify({'success': False, 'message': 'Já existe uma busca em andamento'})
    
    data = request.get_json()
    termo_busca = data.get('termo_busca', '').strip()
    max_resultados = int(data.get('max_resultados', 200))
    
    if not termo_busca:
        return jsonify({'success': False, 'message': 'Termo de busca é obrigatório'})
    
    # Iniciar scraping em thread separada
    thread = threading.Thread(target=buscar_google_maps, args=(termo_busca, max_resultados))
    thread.daemon = True
    thread.start()
    
    return jsonify({'success': True, 'message': 'Busca no Google Maps iniciada'})

@app.route('/progress_maps')
def progress_maps():
    """Retorna o progresso da busca no Google Maps"""
    return jsonify({
        'progress': progresso_maps,
        'total': total_resultados_maps,
        'status': status_maps,
        'message': mensagem_maps,
        'results_count': len(dados_maps)
    })

@app.route('/results_maps')
def results_maps():
    """Retorna os resultados da busca no Google Maps"""
    return jsonify({
        'results': dados_maps,
        'count': len(dados_maps)
    })

@app.route('/download_maps/<formato>')
def download_maps(formato):
    """Download dos dados do Google Maps em diferentes formatos"""
    global dados_maps
    
    if not dados_maps:
        return jsonify({'error': 'Nenhum dado disponível'}), 404
    
    try:
        if formato == 'csv':
            # Criar CSV temporário
            output = BytesIO()
            output.write('\ufeff'.encode('utf-8'))  # BOM para UTF-8
            
            fieldnames = ['nome', 'endereco', 'telefone', 'avaliacao', 'total_avaliacoes', 'categoria', 'website']
            
            csv_content = 'nome,endereco,telefone,avaliacao,total_avaliacoes,categoria,website\n'
            for item in dados_maps:
                linha = f"\"{item.get('nome', '')}\",\"{item.get('endereco', '')}\",\"{item.get('telefone', '')}\",\"{item.get('avaliacao', '')}\",\"{item.get('total_avaliacoes', '')}\",\"{item.get('categoria', '')}\",\"{item.get('website', '')}\"\n"
                csv_content += linha
            
            output.write(csv_content.encode('utf-8'))
            output.seek(0)
            
            return send_file(
                output,
                as_attachment=True,
                download_name=f'google_maps_resultados_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv',
                mimetype='text/csv'
            )
            
        elif formato == 'json':
            json_data = json.dumps(dados_maps, ensure_ascii=False, indent=2)
            output = BytesIO(json_data.encode('utf-8'))
            output.seek(0)
            
            return send_file(
                output,
                as_attachment=True,
                download_name=f'google_maps_resultados_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json',
                mimetype='application/json'
            )
            
        elif formato == 'excel':
            df = pd.DataFrame(dados_maps)
            output = BytesIO()
            
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Google Maps', index=False)
            
            output.seek(0)
            
            return send_file(
                output,
                as_attachment=True,
                download_name=f'google_maps_resultados_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx',
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            
    except Exception as e:
        return jsonify({'error': f'Erro ao gerar arquivo: {str(e)}'}), 500
    
    return jsonify({'error': 'Formato não suportado'}), 400

# --- ROTAS DE WEBHOOK ---

@app.route('/webhook/config', methods=['GET', 'POST'])
def webhook_config_route():
    """Configurar webhook"""
    global webhook_config
    
    if request.method == 'GET':
        return jsonify(webhook_config)
    
    try:
        data = request.get_json()
        webhook_config.update({
            'url': data.get('url', ''),
            'enabled': data.get('enabled', False),
            'headers': data.get('headers', {}),
            'batch_size': data.get('batch_size', 10)
        })
        return jsonify({'success': True, 'message': 'Webhook configurado com sucesso'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/webhook/test', methods=['POST'])
def test_webhook():
    """Testar webhook com dados de exemplo"""
    if not webhook_config['enabled'] or not webhook_config['url']:
        return jsonify({'success': False, 'error': 'Webhook não configurado'}), 400
    
    dados_teste = [
        {'nome': 'João Silva', 'telefone': '(11) 99999-9999'},
        {'nome': 'Maria Santos', 'telefone': '(11) 88888-8888'}
    ]
    
    try:
        enviar_webhook(dados_teste)
        return jsonify({'success': True, 'message': 'Webhook testado com sucesso'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/export/advanced', methods=['POST'])
def advanced_export():
    """Exportação avançada com filtros"""
    try:
        data = request.get_json()
        format_type = data.get('format', 'csv')
        filters = data.get('filters', {})
        
        if not os.path.exists('consultores.csv'):
            return jsonify({'error': 'Nenhum dado disponível'}), 404
        
        # Ler dados
        dados = []
        with open('consultores.csv', 'r', newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            dados = list(reader)
        
        # Aplicar filtros
        if filters.get('search'):
            search_term = filters['search'].lower()
            dados = [d for d in dados if search_term in d.get('nome', '').lower() or search_term in d.get('telefone', '').lower()]
        
        if filters.get('date_from') or filters.get('date_to'):
            # Implementar filtro de data se necessário
            pass
        
        if not dados:
            return jsonify({'error': 'Nenhum dado encontrado com os filtros aplicados'}), 404
        
        # Gerar arquivo
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        if format_type == 'csv':
            output = BytesIO()
            output.write('\ufeff'.encode('utf-8'))  # BOM para UTF-8
            
            csv_content = 'nome,telefone,data_coleta\n'
            for item in dados:
                csv_content += f"\"{item.get('nome', '')}\",\"{item.get('telefone', '')}\",\"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\"\n"
            
            output.write(csv_content.encode('utf-8'))
            output.seek(0)
            
            return send_file(
                output,
                as_attachment=True,
                download_name=f'consultores_filtrado_{timestamp}.csv',
                mimetype='text/csv'
            )
        
        elif format_type == 'json':
            # Adicionar metadados
            export_data = {
                'metadata': {
                    'export_date': datetime.now().isoformat(),
                    'total_records': len(dados),
                    'filters_applied': filters
                },
                'data': dados
            }
            
            json_data = json.dumps(export_data, ensure_ascii=False, indent=2)
            output = BytesIO(json_data.encode('utf-8'))
            output.seek(0)
            
            return send_file(
                output,
                as_attachment=True,
                download_name=f'consultores_filtrado_{timestamp}.json',
                mimetype='application/json'
            )
        
        elif format_type == 'excel':
            df = pd.DataFrame(dados)
            df['data_coleta'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Consultores', index=False)
                
                # Adicionar planilha de metadados
                metadata_df = pd.DataFrame([
                    ['Data da Exportação', datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
                    ['Total de Registros', len(dados)],
                    ['Filtros Aplicados', str(filters)]
                ], columns=['Campo', 'Valor'])
                metadata_df.to_excel(writer, sheet_name='Metadados', index=False)
            
            output.seek(0)
            
            return send_file(
                output,
                as_attachment=True,
                download_name=f'consultores_filtrado_{timestamp}.xlsx',
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
        
    except Exception as e:
        return jsonify({'error': f'Erro na exportação: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True)