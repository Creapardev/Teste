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

def buscar_google_maps(termo_busca, max_resultados=50):
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
        
        # Scroll para carregar mais resultados
        for scroll in range(10):  # Máximo 10 scrolls
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
            
            for estabelecimento in estabelecimentos[resultados_coletados:]:
                if resultados_coletados >= max_resultados:
                    break
                    
                try:
                    # Primeiro, clicar no estabelecimento para abrir os detalhes
                    try:
                        # Tentar encontrar o elemento clicável com a classe hfpxzc
                        # elemento_clicavel = estabelecimento.find_element(By.CSS_SELECTOR, ".Nv2PK .hfpxzc")
                        driver.execute_script("arguments[0].click();", estabelecimento)
                        time.sleep(2)  # Aguardar os detalhes carregarem
                        print("Clicou no estabelecimento para abrir detalhes")
                    except Exception as click_error:
                        print(f"Erro ao clicar no estabelecimento: {click_error}")
                        # Tentar clicar no próprio elemento estabelecimento
                        try:
                            driver.execute_script("arguments[0].click();", estabelecimento)
                            time.sleep(2)
                            print("Clicou no estabelecimento (fallback)")
                        except:
                            print("Não foi possível clicar no estabelecimento")
                    
                    # Extrair dados do estabelecimento
                    dados_estabelecimento = extrair_dados_estabelecimento(driver, estabelecimento)
                    if dados_estabelecimento:
                        dados_maps.append(dados_estabelecimento)
                        resultados_coletados += 1
                        progresso_maps = int((resultados_coletados / max_resultados) * 100)
                        mensagem_maps = f"Coletados {resultados_coletados} de {max_resultados} estabelecimentos"
                        
                except Exception as e:
                    print(f"Erro ao extrair dados do estabelecimento: {e}")
                    continue
            
            # Scroll para carregar mais
            if resultados_coletados < max_resultados:
                try:
                    scroll_container = driver.find_element(By.CSS_SELECTOR, "[role='main'], .m6QErb, .Nv2PK")
                    driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", scroll_container)
                except:
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(3)
        
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
        
        # Nome do estabelecimento - buscar no painel lateral primeiro com classes atualizadas
        try:
            # Tentar no painel lateral com as classes específicas
            nome_elem = driver.find_element(By.CSS_SELECTOR, "[role='main'] .Io6YTe.fontBodyMedium.kR99db.fdkmkc, [role='main'] h1, .x3AX1-LfntMc-header-title-title, .qBF1Pd, .DUwDvf")
            print(f"1 - {nome_elem.text.strip()}")
            dados['nome'] = nome_elem.text.strip()
        except:
            try:
                # Fallback: buscar no elemento original
                nome_elem = elemento.find_element(By.CSS_SELECTOR, ".Io6YTe.fontBodyMedium.kR99db.fdkmkc, .qBF1Pd, .fontHeadlineSmall, [data-value='Título'], .DUwDvf")
                dados['nome'] = nome_elem.text.strip()
            except:
                try:
                    # Último fallback: buscar por qualquer texto que pareça um nome
                    nome_elems = driver.find_elements(By.CSS_SELECTOR, ".Io6YTe, .fontBodyMedium, .kR99db, .fdkmkc, a[href*='/maps/place/'], h3, .NrDZNb, .DUwDvf")
                    for elem in nome_elems:
                        text = elem.text.strip()
                        if text and len(text) > 2 and len(text) < 100 and not text.isdigit() and not any(char in text for char in ['★', '·', '(', ')']):
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
    """Salva os dados do Google Maps em arquivo CSV"""
    if not dados_maps:
        return
    
    # Nome do arquivo baseado no termo de busca
    nome_arquivo = f"google_maps_{termo_busca.replace(' ', '_').replace('/', '_')}.csv"
    
    # Salvar em CSV
    with open(nome_arquivo, 'w', newline='', encoding='utf-8') as arquivo:
        fieldnames = ['nome', 'avaliacao', 'endereco', 'telefone', 'tipo', 'horario']
        writer = csv.DictWriter(arquivo, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(dados_maps)

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

# --- ROTAS GOOGLE MAPS ---

@app.route('/scrape_maps', methods=['POST'])
def scrape_maps():
    """Inicia o scraping do Google Maps"""
    global status_maps
    
    if status_maps == "running":
        return jsonify({'success': False, 'message': 'Já existe uma busca em andamento'})
    
    data = request.get_json()
    termo_busca = data.get('termo_busca', '').strip()
    max_resultados = int(data.get('max_resultados', 50))
    
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
    if not dados_maps:
        return jsonify({'error': 'Nenhum dado disponível para download'}), 404
    
    try:
        if formato == 'csv':
            # Criar CSV em memória
            output = BytesIO()
            df = pd.DataFrame(dados_maps)
            df.to_csv(output, index=False, encoding='utf-8')
            output.seek(0)
            
            return send_file(
                output,
                mimetype='text/csv',
                as_attachment=True,
                download_name='google_maps_resultados.csv'
            )
            
        elif formato == 'json':
            # Criar JSON em memória
            output = BytesIO()
            json_data = json.dumps(dados_maps, ensure_ascii=False, indent=2)
            output.write(json_data.encode('utf-8'))
            output.seek(0)
            
            return send_file(
                output,
                mimetype='application/json',
                as_attachment=True,
                download_name='google_maps_resultados.json'
            )
            
        elif formato == 'excel':
            # Criar Excel em memória
            output = BytesIO()
            df = pd.DataFrame(dados_maps)
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Google Maps', index=False)
            output.seek(0)
            
            return send_file(
                output,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name='google_maps_resultados.xlsx'
            )
            
    except Exception as e:
        return jsonify({'error': f'Erro ao gerar arquivo: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True)