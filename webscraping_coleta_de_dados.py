# -*- coding: utf-8 -*-
import time
import re
import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, ElementClickInterceptedException, StaleElementReferenceException
from webdriver_manager.chrome import ChromeDriverManager
import datetime
import logging

# --- Configurações ---
BASE_URL = "https://www.flograppling.com"
RESULTS_URL = f"{BASE_URL}/results"
# Nomes base dos eventos para buscar ano a ano
BASE_EVENT_KEYWORDS = [
    "IBJJF World Jiu-Jitsu Championship",
    "World Jiu-Jitsu IBJJF Championship",
    "World Jiu-Jitsu Championship",
    "IBJJF Pan Jiu-Jitsu Championship",
    "Brazilian National Jiu-Jitsu Championship",
    "European Jiu-Jitsu IBJJF Championship",
]

# Intervalo de anos para buscar
START_YEAR = 2014 
END_YEAR = 2024
EXCLUDE_EVENT_KEYWORDS = ["no-gi", "no gi", "nogi", "abu dhabi", "adcc"] # Palavras a excluir
OUTPUT_CSV_FILE = 'bjj_dado_cru.csv'# Nome do arquivo de saída
MAX_EVENTS_TO_PROCESS = 1
WAIT_TIMEOUT = 25
SHORT_WAIT = 7
SEARCH_PAUSE = 6 # Pausa entre buscas
EXTRA_LOAD_PAUSE = 5 # Pausa após filtros/clicks
TARGET_STAGE_KEYWORDS = {'final', 'semi', 'quarter'}# Define quais fases da competição serão extraídas

# Função para configurar o WebDriver
def setup_driver():
    print("Configurando o WebDriver...")
    options = webdriver.ChromeOptions()
    # options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--ignore-certificate-errors')
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    logging.getLogger('WDM').setLevel(logging.WARNING)
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        print("WebDriver iniciado.")
        return driver
    except Exception as e:
        print(f"Erro ao configurar o WebDriver: {e}")
        import traceback; traceback.print_exc()
        return None

# Função para aceitar cookies
def accept_cookies(driver):
    try:
        cookie_selectors = [
            "#onetrust-accept-btn-handler",
            "button[aria-label='Accept Cookies']",
            "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'accept')]",
            "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'agree')]"
        ]
        for selector in cookie_selectors:
            locator_type = By.XPATH if selector.startswith('//') else By.CSS_SELECTOR
            try:
                cookie_button = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((locator_type, selector))
                )
                driver.execute_script("arguments[0].click();", cookie_button)
                time.sleep(0.5)
                return True
            except (NoSuchElementException, TimeoutException): continue
            except ElementClickInterceptedException:
                time.sleep(1)
                try:
                    driver.execute_script("arguments[0].click();", cookie_button)
                    time.sleep(0.5)
                    return True
                except Exception: continue
            except Exception: continue
        return False
    except Exception: return False

# Função para buscar links dos eventos
def find_event_links(driver):
    print("Buscando eventos ano a ano (com múltiplos formatos de busca)...")
    all_found_links = {}
    processed_urls_in_session = set()
    try:
        driver.get(RESULTS_URL)
        print(f"Acessando: {RESULTS_URL}")
        time.sleep(SHORT_WAIT)
        accept_cookies(driver)

        search_input_selector = 'input[data-test="search-input"]'
        try:
            search_input = WebDriverWait(driver, WAIT_TIMEOUT).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, search_input_selector))
            )
            print("Campo de busca encontrado.")
        except TimeoutException:
             print("ERRO CRÍTICO: Campo de busca não encontrado. Abortando busca de eventos.")
             return []

        event_item_selector = "div.py-3.py-lg-4.border-bottom"
        link_selector_within_item = 'a[data-test="event-card-item-link"]'
        title_selector_within_item = 'h4.bold-font.apply-text-hover'

        for year in range(START_YEAR, END_YEAR + 1):
            print(f"\n--- Buscando eventos para o ano: {year} ---")
            # Verifica limite GERAL antes de iniciar o ano
            if MAX_EVENTS_TO_PROCESS is not None and len(all_found_links) >= MAX_EVENTS_TO_PROCESS:
                print(f"Limite GERAL de {MAX_EVENTS_TO_PROCESS} eventos atingido. Interrompendo busca de links.")
                break # Sai do loop de anos

            for base_keyword in BASE_EVENT_KEYWORDS:
                # Verifica limite GERAL antes de processar keyword
                if MAX_EVENTS_TO_PROCESS is not None and len(all_found_links) >= MAX_EVENTS_TO_PROCESS: break

                print(f"--> Verificando keyword base: '{base_keyword}'")
                search_queries_to_try = []
                kw_lower = base_keyword.lower()
                search_queries_to_try.append(f"{year} {base_keyword}") # Formato Padrão

                # Variações para Mundial IBJJF
                if all(k in kw_lower for k in ["ibjjf", "world", "jiu-jitsu", "championship"]):
                    search_queries_to_try.append(f"{year} World Jiu-Jitsu IBJJF Championship")
                    search_queries_to_try.append(f"World {year} Jiu-Jitsu Championship")
                    search_queries_to_try.append(f"World IBJJF {year} Jiu-Jitsu Championship")
                    search_queries_to_try.append(f"{year} World IBJJF Jiu-Jitsu Championship")
                # Variações para Pan IBJJF
                elif all(k in kw_lower for k in ["ibjjf", "pan", "jiu-jitsu", "championship"]):
                   search_queries_to_try.append(f"{year} Pan IBJJF Jiu-Jitsu Championship")
                   search_queries_to_try.append(f"Pan {year} Jiu-Jitsu Championship")
                   search_queries_to_try.append(f"Pan IBJJF {year} Jiu-Jitsu Championship")

                # Variações para European IBJJF
                elif all(k in kw_lower for k in ["ibjjf", "european", "jiu-jitsu", "championship"]):
                   search_queries_to_try.append(f"{year} European IBJJF Jiu-Jitsu Championship")
                   search_queries_to_try.append(f"European {year} Jiu-Jitsu Championship")
                   search_queries_to_try.append(f"European IBJJF {year} Jiu-Jitsu Championship")

                # Variações para Brazilian National IBJJF
                elif all(k in kw_lower for k in ["ibjjf", "brazilian national", "jiu-jitsu", "championship"]):
                   search_queries_to_try.append(f"{year} Brazilian National IBJJF Jiu-Jitsu Championship")
                   search_queries_to_try.append(f"Brazilian National {year} Jiu-Jitsu Championship")
                   search_queries_to_try.append(f"Brazilian National IBJJF {year} Jiu-Jitsu Championship")
                   
                
                search_queries_to_try = list(dict.fromkeys(search_queries_to_try)) # Remove duplicatas
                # print(f"   -> Formatos de busca a tentar: {search_queries_to_try}") # Log verboso

                for search_query in search_queries_to_try:
                    # Verifica limite GERAL antes de fazer a busca
                    if MAX_EVENTS_TO_PROCESS is not None and len(all_found_links) >= MAX_EVENTS_TO_PROCESS: break

                    print(f"      Tentando busca: '{search_query}'...")
                    try:
                        search_input.clear()
                        search_input.send_keys(search_query)
                        time.sleep(SEARCH_PAUSE)

                        try:
                            WebDriverWait(driver, WAIT_TIMEOUT).until(
                                EC.any_of(
                                    EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-test='search-results-container']")),
                                    EC.presence_of_element_located((By.CSS_SELECTOR, event_item_selector)) ))
                            time.sleep(1)
                        except TimeoutException:
                            continue # Pula para o próximo formato

                        soup = BeautifulSoup(driver.page_source, 'html.parser')
                        event_items = soup.select(event_item_selector)
                        found_in_this_attempt = 0

                        for item in event_items:
                             # Verifica limite GERAL dentro do loop de itens
                            if MAX_EVENTS_TO_PROCESS is not None and len(all_found_links) >= MAX_EVENTS_TO_PROCESS: break

                            link_tag = item.select_one(link_selector_within_item)
                            title_tag = item.select_one(title_selector_within_item)
                            title = title_tag.get_text(strip=True) if title_tag else "N/A"

                            if link_tag and title != "N/A":
                                href = link_tag.get('href')
                                if href:
                                    full_url = href if href.startswith('http') else f"{BASE_URL}{href}"
                                    title_lower = title.lower()
                                    keyword_parts = [p for p in base_keyword.lower().split() if p != "jiu-jitsu"]
                                    match_criteria = str(year) in title and all(part in title_lower for part in keyword_parts)

                                    if match_criteria:
                                        if full_url not in processed_urls_in_session:
                                            print(f"         >>> Evento correspondente ENCONTRADO via '{search_query}': {title} ({full_url})")
                                            all_found_links[full_url] = {'title': title, 'url': full_url}
                                            processed_urls_in_session.add(full_url)
                                            found_in_this_attempt += 1

                    except StaleElementReferenceException:
                        print("      AVISO: Elemento (campo de busca?) ficou obsoleto. Tentando continuar...")
                        # Tenta relocalizar o campo de busca
                        try:
                           search_input = WebDriverWait(driver, WAIT_TIMEOUT).until(
                               EC.presence_of_element_located((By.CSS_SELECTOR, search_input_selector)) )
                        except:
                           print("      ERRO: Não foi possível relocalizar campo de busca. Interrompendo busca.")
                           break # Interrompe loop de formatos
                    except Exception as e_search:
                        print(f"      ERRO durante a tentativa de busca '{search_query}': {e_search}")

            # Sai do loop de keywords base se já atingiu o limite
            if MAX_EVENTS_TO_PROCESS is not None and len(all_found_links) >= MAX_EVENTS_TO_PROCESS: break

    except Exception as e:
        print(f"Erro fatal durante a busca de links de eventos: {e}")
        import traceback; traceback.print_exc()

    final_list = list(all_found_links.values())
    print(f"\nBusca inicial encontrou {len(final_list)} eventos únicos potenciais de {START_YEAR} a {END_YEAR}.")
    return final_list

# Função para aplicar filtro de gênero
def apply_gender_filter(driver, gender):
    filter_button_selectors = [
        "//button[@data-test='dropdown-button' and contains(., 'Gender')]",
        "//button[contains(., 'Gender') and contains(@class, 'dropdown')]",
        "//div[contains(text(), 'Gender')]/following-sibling::button",
    ]
    filter_button = None
    for selector in filter_button_selectors:
        try:
            filter_button = WebDriverWait(driver, SHORT_WAIT).until(
                EC.element_to_be_clickable((By.XPATH, selector))
            )
            break
        except TimeoutException: continue

    if not filter_button:
        print(f"  -> AVISO: Botão de filtro de Gênero ('{gender}') não encontrado.")
        return False

    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", filter_button); time.sleep(0.5)
        driver.execute_script("arguments[0].click();", filter_button); time.sleep(1)

        option_xpath = f"//button[@data-test='dropdown-option'][normalize-space()='{gender}']"
        option_button = WebDriverWait(driver, SHORT_WAIT).until(
            EC.element_to_be_clickable((By.XPATH, option_xpath))
        )
        driver.execute_script("arguments[0].click();", option_button); time.sleep(EXTRA_LOAD_PAUSE)
        print(f"  -> Filtro '{gender}' aplicado.")
        return True
    except Exception as e:
        print(f"  -> ERRO ao tentar aplicar filtro '{gender}': {e}")
        try: # Tenta fechar dropdown
            if filter_button and filter_button.is_displayed(): filter_button.click()
        except: pass
        return False

# Função para clicar no botão "View All"
def click_load_more(driver):
      load_more_selectors = [
          "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'view all')]",
          "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'load more')]",
          "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'view all')]",
          "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'load more')]",
          "//a[@data-test='link-title' and contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'view all')]",
          'a[data-test="link-title"]',
      ]
      clicked_any = False; attempts = 0; max_attempts = 3

      while attempts < max_attempts:
            button_found_this_loop = False
            for selector in load_more_selectors:
                try:
                    locator_type = By.XPATH if selector.startswith('//') else By.CSS_SELECTOR
                    load_more_elements = WebDriverWait(driver, SHORT_WAIT).until(
                        EC.presence_of_all_elements_located((locator_type, selector)) )
                    if not load_more_elements: continue
                    for element in load_more_elements:
                        try:
                           if element.is_displayed() and element.is_enabled():
                              button_text = element.text.strip().lower()
                              if "view all" in button_text or "load more" in button_text:
                                  print(f"   -> Botão/Link '{element.text.strip()}' encontrado. Clicando...")
                                  driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element); time.sleep(0.5)
                                  driver.execute_script("arguments[0].click();", element)
                                  time.sleep(EXTRA_LOAD_PAUSE)
                                  clicked_any = True; button_found_this_loop = True
                                  break
                        except StaleElementReferenceException: continue
                        except Exception: pass # Ignora erro no clique e tenta próximo
                    if button_found_this_loop: break
                except (NoSuchElementException, TimeoutException): continue
                except Exception: pass # Ignora erro na busca e tenta próximo
            if button_found_this_loop: attempts += 1
            else: break # Sai do while se não achou nada

      if clicked_any: print("   -> Ação 'View All' / 'Load More' concluída.")
      # else: print("   -> Botão 'View All' / 'Load More' não encontrado.") # Log opcional
      return clicked_any

# Função para extrair dados das lutas
def extract_match_data(driver, event_name, event_url, current_gender):
    print(f"Extraindo dados de FINAIS de: {event_url} (Gênero: {current_gender})")
    match_data = []
    try:
        time.sleep(2)
        results_container_selector = "div.grappling-result-card"
        try:
            WebDriverWait(driver, WAIT_TIMEOUT).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, results_container_selector)) )
            print("   Cards de resultado detectados.")
        except TimeoutException:
             print(f"   ERRO: Nenhum card de resultado ('{results_container_selector}') encontrado. Pulando extração.")
             return []

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        competition_tag = soup.select_one('h1.header-title, h1.page-title')
        competition_name = competition_tag.get_text(strip=True) if competition_tag else event_name
        year_match = re.search(r'\b(20\d{2})\b', competition_name + " " + event_url)
        event_year = year_match.group(1) if year_match else "N/A"
        if event_year == "N/A":
             year_match_fallback = re.search(r'\b(20\d{2})\b', event_name)
             event_year = year_match_fallback.group(1) if year_match_fallback else "N/A"

        result_cards = soup.select('div.grappling-result-card')
        extracted_count = 0

        for card_index, card in enumerate(result_cards):
            scoreboard = card.find('div', class_='scoreboard')
            if not scoreboard: continue
            headers = scoreboard.select('div.scoreboard__top > div.scoreboard__header')
            bottom_info = scoreboard.select_one('div.scoreboard__bottom > p.scoreboard__bottom--stage')
            if len(headers) == 0 or not bottom_info: continue
            bottom_text = bottom_info.get_text(strip=True)

            # Parse Stage, Weight, Gender
            stage, weight = "N/A", "N/A"; gender = current_gender
            parts = [p.strip() for p in bottom_text.split(',') if p.strip()]
            stage_candidates = []; weight_candidates = []
            for part in parts:
                part_lower = part.lower()
                if any(s in part_lower for s in ['final', 'semi','quarter','round','bronze','match']): # Simplified stage check
                     current_stage_candidate = part.title()
                     if not any(g in part_lower for g in ['male', 'female']) or stage == "N/A" or "final" not in stage.lower():
                           stage_candidates.append(current_stage_candidate)
                elif not any(g in part_lower for g in ['male', 'female']):
                     if 'kg' in part_lower or any(w in part_lower for w in ['light', 'medium', 'middle', 'heavy', 'super','ultra','rooster','feather','absolute','open','master','juvenile','adult']): # Simplified weight check
                         weight_candidates.append(part.title())
            final_stages = [s for s in stage_candidates if "final" in s.lower()]
            if final_stages: stage = final_stages[0]
            elif stage_candidates: stage = stage_candidates[0]
            if weight_candidates: weight = " / ".join(weight_candidates)
            if stage == "N/A" and "final" in bottom_text.lower() and "semi" not in bottom_text.lower() and "quarter" not in bottom_text.lower(): stage = "Final"
            if weight == "N/A":
                remaining_parts = [p.title() for p in parts if p.title() != stage and p.lower() not in ['male', 'female']]
                if remaining_parts: weight = " / ".join(remaining_parts)

            # FILTRO DE STAGE (usando a constante definida no topo)
            stage_lower = stage.lower() 

            if stage == "N/A" or not any(keyword in stage_lower for keyword in TARGET_STAGE_KEYWORDS):
                 continue # Pula se não for uma das fases alvo

            # Extração de dados da final
            competitors_info = []
            winner_index = -1; win_detail = ""; detail_tag = None; has_numeric_score = False
            for i, header in enumerate(headers):
                name_tag_a = header.select_one('a.scoreboard__header--title.headline[href*="/people/"]')
                name_tag_span = header.select_one('span.scoreboard__header--title.headline')
                name = "N/A"
                if name_tag_a: name = name_tag_a.get_text(strip=True)
                elif name_tag_span:
                    full_span_text = name_tag_span.get_text(strip=True); name = re.sub(r'\s*-\s*\d+$', '', full_span_text).strip(); name = re.sub(r'\s+\(.*\)$', '', name).strip(); name = re.sub(r'\s+[WL]$', '', name).strip()
                    if name.isdigit() or name.upper() in ['W', 'L']: name = "N/A"
                score_tag = header.select_one('span.scoreboard__header--score'); score_text = score_tag.get_text(strip=True) if score_tag else ""
                competitors_info.append({'name': name, 'score_text': score_text})
                if score_text.upper() == 'W': winner_index = i; detail_tag = header.select_one('span.scoreboard__header--title.footnote')
                if score_text.isdigit(): has_numeric_score = True

            if len(headers) == 1 and competitors_info[0]['name'] != "N/A":
                 winner_index = 0; win_detail = "Walkover"
                 if len(competitors_info) < 2: competitors_info.append({'name': 'N/A', 'score_text': 'L'})
            if detail_tag: win_detail = re.sub(r'^[\s\-()]+|[\s\-()]+$', '', detail_tag.get_text(strip=True)).strip()

            # Determina Win Type e Sub Type (lógica mantida)
            final_win_type = "N/A"; final_sub_type = "N/A"; detail_lower = win_detail.lower() if win_detail else ""
            if any(sub in detail_lower for sub in ['armbar','lock','choke','ezekiel','guillotine','katagatame','loop','rnc','rear','ankle','toe','hold','triangle','heel','hook','kneebar','omoplata','submission','footlock','wrist','americana','kimura','mata leao','clock']): final_win_type = "Submission"; final_sub_type = win_detail.title() if win_detail else "Submission"
            elif "points" in detail_lower: final_win_type = "Points"
            elif "advantage" in detail_lower: final_win_type = "Advantage"
            elif "decision" in detail_lower or "referee" in detail_lower : final_win_type = "Decision"
            elif "dq" in detail_lower or "disqualif" in detail_lower: final_win_type = "DQ"
            elif "injury" in detail_lower or "stoppage" in detail_lower: final_win_type = "Injury"
            elif "penalty" in detail_lower or "penalties" in detail_lower: final_win_type = "Penalty"
            elif "walkover" in detail_lower or "w.o." in detail_lower or win_detail == "Walkover": final_win_type = "WO"
            elif winner_index != -1:
                if has_numeric_score: final_win_type = "Points"
                elif len(competitors_info) < 2 or competitors_info[1-winner_index]['name'] == 'N/A': final_win_type = "WO"
                else: final_win_type = "Win"
            elif has_numeric_score:
                 final_win_type = "Points"
                 try:
                     if len(competitors_info) >= 2:
                         score0_str = re.sub(r'[WL]$', '', competitors_info[0]['score_text']); score1_str = re.sub(r'[WL]$', '', competitors_info[1]['score_text'])
                         score0 = int(score0_str); score1 = int(score1_str)
                         if score0 > score1: winner_index = 0
                         elif score1 > score0: winner_index = 1
                 except: pass
            else: final_win_type = "Unknown"

            # Adiciona linhas ao resultado
            opponent_added_for_wo = False
            for i, comp_info in enumerate(competitors_info):
                if comp_info['name'] == "N/A":
                    if final_win_type == "WO" and i != winner_index and not opponent_added_for_wo: pass
                    else: continue
                is_winner = (i == winner_index); row_win_type = "N/A"
                if final_win_type == "WO":
                     row_win_type = "WO" if is_winner else "Loss"
                     if not is_winner: opponent_added_for_wo = True
                elif winner_index != -1: row_win_type = final_win_type if is_winner else "Loss"
                else: row_win_type = final_win_type
                row_sub_type = final_sub_type if is_winner and final_win_type == "Submission" else "N/A"
                row_data = {'YEAR': event_year, 'COMPETITION': competition_name, 'COMPETITOR': comp_info['name'],'WIN_TYPE': row_win_type, 'SUBMISSION_TYPE': row_sub_type, 'WEIGHT': weight,'GENDER': gender, 'STAGE': stage }
                match_data.append(row_data)
                extracted_count += 1

        if extracted_count > 0:
             print(f"   Extraídos {extracted_count} registros de FINAIS para {current_gender}.")

    except StaleElementReferenceException: print("   ERRO: Stale Element Reference durante extração.")
    except Exception as e: print(f"   Erro inesperado em extract_match_data: {e}"); import traceback; traceback.print_exc()
    return match_data

# Execução Principal
if __name__ == "__main__":
    start_time = time.time()
    print(f"Iniciando script às {time.strftime('%Y-%m-%d %H:%M:%S')}")
    driver = setup_driver()
    all_results_data = []

    if driver:
        try:
            # 1. Encontra links com busca flexível
            event_links = find_event_links(driver)

            if not event_links:
                print("\nNenhum link de evento potencial encontrado. Encerrando.")
            else:
                # >>> Filtra eventos por palavras-chave indesejadas no título <<<
                print(f"\nFiltrando {len(event_links)} eventos encontrados...")
                initial_count = len(event_links)
                # Garante que as keywords de exclusão estejam em minúsculas
                exclude_keywords_lower = [kw.lower() for kw in EXCLUDE_EVENT_KEYWORDS]
                filtered_event_links = [
                    event for event in event_links
                    if not any(exclude_kw in event['title'].lower() for exclude_kw in exclude_keywords_lower)
                ]
                removed_count = initial_count - len(filtered_event_links)
                if removed_count > 0:
                    print(f"Removidos {removed_count} eventos contendo palavras-chave indesejadas ({', '.join(EXCLUDE_EVENT_KEYWORDS)}).")
                print(f"Restam {len(filtered_event_links)} eventos para processar.")
                # <<< FIM DA FILTRAGEM >>>

                if not filtered_event_links:
                     print("Nenhum evento restante após a filtragem. Encerrando.")
                else:
                    print(f"\nIniciando processamento de {len(filtered_event_links)} eventos filtrados...")
                    # 2. Processa cada evento FILTRADO
                    for i, event in enumerate(filtered_event_links):
                        print(f"\n--- Processando Evento {i+1}/{len(filtered_event_links)}: {event['title']} ---")
                        base_event_url = event['url'].split('/results')[0]
                        results_page_url = f"{base_event_url}/results"

                        # 3. Processa Gêneros
                        for gender in ["Male", "Female"]:
                            print(f"\n---> Processando gênero: {gender} <---")
                            try:
                                driver.get(results_page_url)
                                time.sleep(SHORT_WAIT)
                                accept_cookies(driver)

                                filter_applied = apply_gender_filter(driver, gender)

                                if filter_applied:
                                    click_load_more(driver)
                                    event_data = extract_match_data(driver, event['title'], results_page_url, gender) # Extrai só FINAIS
                                    if event_data: all_results_data.extend(event_data)
                                else:
                                    print(f"   AVISO: Filtro '{gender}' não aplicado/falhou. Pulando extração.")

                            except (NoSuchElementException, TimeoutException) as nav_err:
                                 print(f"   ERRO de Navegação/Timeout processando {gender}: {nav_err}")
                                 print("   Continuando...")
                            except Exception as gender_e:
                                print(f"   ERRO INESPERADO processando {gender}: {gender_e}")
                                import traceback; traceback.print_exc()
                                print("   Continuando...")

        except Exception as main_e:
            print(f"\nErro fatal no loop principal: {main_e}")
            import traceback; traceback.print_exc()
        finally:
            if driver:
                print("\nFechando WebDriver...")
                time.sleep(2); driver.quit(); print("WebDriver fechado.")

    # 4. Salva resultados
    if all_results_data:
        print(f"\nTotal de {len(all_results_data)} linhas de resultados FINAIS coletadas.")
        df = pd.DataFrame(all_results_data)
        df = df.reindex(columns=['YEAR', 'COMPETITION', 'COMPETITOR', 'WIN_TYPE', 'SUBMISSION_TYPE', 'WEIGHT', 'GENDER', 'STAGE'], fill_value='N/A')
        initial_rows = len(df)
        df = df.drop_duplicates()
        print(f"Removidas {initial_rows - len(df)} linhas duplicadas. Total de {len(df)} linhas únicas.")
        try:
            df.to_csv(OUTPUT_CSV_FILE, index=False, encoding='utf-8')
            print(f"Dados salvos com sucesso em '{OUTPUT_CSV_FILE}' (UTF-8).")
        except Exception as save_e_utf8:
            print(f"ERRO ao salvar CSV com UTF-8: {save_e_utf8}. Tentando com latin-1...")
            try:
                df.to_csv(OUTPUT_CSV_FILE, index=False, encoding='latin-1')
                print(f"Dados salvos com sucesso em '{OUTPUT_CSV_FILE}' (latin-1).")
            except Exception as save_e_latin1:
                 print(f"ERRO CRÍTICO ao salvar CSV com latin-1: {save_e_latin1}")

    else:
        print(f"\nNenhum dado de resultado final foi coletado ou extraído. O arquivo '{OUTPUT_CSV_FILE}' não foi gerado.")
        if 'driver' in locals() and driver: print("Verifique os logs de erro acima.")

    end_time = time.time()
    print(f"\nScript concluído às {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Tempo total de execução: {time.strftime('%H:%M:%S', time.gmtime(end_time - start_time))}")
