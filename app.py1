import httpx
import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template_string, request, url_for, session, redirect, jsonify
import copy
import re
import random
import os
import threading
import time
import string
import rarfile
from urllib.parse import unquote, quote
import subprocess
import sys
import shutil
import shlex
import libtorrent as lt

app = Flask(__name__)
app.secret_key = "fit_downloader_secret_key"

# --- GLOBALNY MENEDŻER POBIERANIA ---
# Przechowuje statusy pobierania dla poszczególnych URLi gier
DOWNLOAD_TASKS = {}
DOWNLOAD_DIR = "FitDownloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# --- LISTA POPULARNYCH GIER ---
POPULAR_GAMES = [
    "The Witcher 3", "Cyberpunk 2077", "Elden Ring", "Hollow Knight", 
    "God of War", "Red Dead Redemption 2", "Grand Theft Auto V", "Minecraft", 
    "Spider-Man", "Stardew Valley", "Baldur's Gate 3", "Alan Wake 2", 
    "The Last of Us Part I", "Horizon Forbidden West", "Doom Eternal"
]

# --- LOGIKA TŁUMACZENIA I JĘZYKÓW ---

def translate_text(text, target_lang):
    if target_lang == 'en' or not text:
        return text
    try:
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl={target_lang}&dt=t&q={text}"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            translated = "".join([part[0] for part in res.json()[0]])
            return translated
    except:
        pass
    return text

def get_labels(lang):
    labels = {
        'pl': {
            'genres': 'Gatunek/Tagi', 'company': 'Producent', 'languages': 'Języki',
            'original_size': 'Oryginalny rozmiar', 'repack_size': 'Rozmiar po kompresji',
            'description': 'OPIS GRY', 'search_placeholder': 'Wyszukaj grę...',
            'details_btn': 'Sprawdź detale', 'back_btn': 'Wróć', 'external_btn': 'Strona FitGirl',
            'results_for': 'Wyniki dla', 'welcome': 'Polecane gry', 'loading': 'Ładowanie gier...',
            'no_results': 'Nie znaleziono wyników.', 'download_btn': 'Pobierz Grę',
            'dl_searching': 'Wyszukiwanie linków...', 'dl_paused': 'Wstrzymano',
            'dl_extracting': 'Rozpakowywanie archiwów...', 'dl_finished': 'Zakończono pobieranie!',
            'btn_pause': 'Pauza', 'btn_resume': 'Wznów', 'btn_stop': 'Anuluj', 'btn_install': 'Zainstaluj (setup.exe)',
            'dl_error': 'Wystąpił błąd', 'dl_part': 'Część',
            'btn_dl_unavailable': 'Brak linków do pobrania', 'dl_method_torrent': 'Pobieranie przez Torrent...',
            'updates_title': 'Dodatkowa zawartość (Updates / DLC)',
            'comments_title': 'Dyskusja / Komentarze', 'load_comments': 'Pokaż komentarze', 'load_more': 'Załaduj starsze komentarze'
        },
        'en': {
            'genres': 'Genres/Tags', 'company': 'Company', 'languages': 'Languages',
            'original_size': 'Original Size', 'repack_size': 'Repack Size',
            'description': 'GAME DESCRIPTION', 'search_placeholder': 'Search for a game...',
            'details_btn': 'Check details', 'back_btn': 'Back', 'external_btn': 'FitGirl Page',
            'results_for': 'Results for', 'welcome': 'Featured Games', 'loading': 'Loading games...',
            'no_results': 'No results found.', 'download_btn': 'Download Game',
            'dl_searching': 'Searching for links...', 'dl_paused': 'Paused',
            'dl_extracting': 'Extracting archives...', 'dl_finished': 'Download Finished!',
            'btn_pause': 'Pause', 'btn_resume': 'Resume', 'btn_stop': 'Cancel', 'btn_install': 'Install (setup.exe)',
            'dl_error': 'Error occurred', 'dl_part': 'Part',
            'btn_dl_unavailable': 'No download links', 'dl_method_torrent': 'Downloading via Torrent...',
            'updates_title': 'Additional Content (Updates / DLC)',
            'comments_title': 'Discussion / Comments', 'load_comments': 'Show comments', 'load_more': 'Load older comments'
        }
    }
    return labels.get(lang, labels['pl'])

# --- SKRYPTY POBIERANIA ---

def get_rutor_link(url):
    """Zwraca bezpośredni link do pliku .torrent na podstawie linku RuTor"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        rutor_tag = soup.find('a', href=re.compile(r'rutor\.info'))
        if rutor_tag:
            original_link = rutor_tag['href']
            match = re.search(r'/torrent/(\d+)', original_link)
            if match:
                return f"https://d.rutor.info/download/{match.group(1)}"
    except Exception:
        pass
    return None

def extract_fuckingfast_links(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        ff_links = soup.find_all('a', href=re.compile(r'fuckingfast\.co', re.I))
        results = [link.get('href') for link in ff_links if link.get('href')]
        return list(dict.fromkeys(results))
    except: return []

def extract_direct_link(html_content):
    pattern = r'window\.open\("(https://dl\.fuckingfast\.co/dl/[^"]+)"\)'
    match = re.search(pattern, html_content)
    if match: return match.group(1)
    fallback_pattern = r'https://dl\.fuckingfast\.co/dl/[a-zA-Z0-9\-_]+'
    links = re.findall(fallback_pattern, html_content)
    return links[0] if links else None

def get_page_source(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Referer': 'https://fuckingfast.co/'
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.text
    except: return None

def get_original_filename(url, response):
    cd = response.headers.get('content-disposition')
    if cd:
        fname = re.findall('filename=(.+)', cd)
        if len(fname) > 0: return fname[0].strip('"')
    return unquote(os.path.basename(url.split('?')[0]))

def download_worker(game_url, game_title, game_image=None):
    """Główny wątek pobierania dla konkretnej gry (HTTP lub Torrent)"""
    task = DOWNLOAD_TASKS[game_url]
    target_folder = os.path.join(DOWNLOAD_DIR, re.sub(r'[^a-zA-Z0-9]', '_', game_title))
    game_files_dir = os.path.join(target_folder, "Game_Files")
    os.makedirs(target_folder, exist_ok=True)
    
    try:
        task['status'] = 'searching'
        ff_links = extract_fuckingfast_links(game_url)
        
        # Opcja 1: Pobieranie przez FuckingFast (HTTP)
        if ff_links:
            task['method'] = 'http'
            direct_links = []
            for fl in ff_links:
                if task['cancel_flag']: return
                html = get_page_source(fl)
                if html:
                    dl = extract_direct_link(html)
                    if dl: direct_links.append(dl)
                    
            if not direct_links: raise Exception("Nie udało się obejść FuckingFast.")
            
            task['total_parts'] = len(direct_links)
            downloaded_paths = []
            
            # Pobieranie partów 
            for index, dlink in enumerate(direct_links):
                if task['cancel_flag']: return
                task['current_part'] = index + 1
                task['status'] = 'downloading'
                task['speed'] = '0.0 MB/s'
                
                with requests.get(dlink, stream=True, allow_redirects=True, timeout=10) as r:
                    orig_name = get_original_filename(dlink, r)
                    if "-selective-" in orig_name.lower(): 
                        continue
                    ext = os.path.splitext(orig_name)[1]
                    if not ext or len(ext) > 5: ext = ".rar"
                    file_path = os.path.join(target_folder, f"part_{index+1}{ext}")
                    total_size = int(r.headers.get('content-length', 0))
                
                headers = {}
                downloaded_bytes = 0
                if os.path.exists(file_path):
                    downloaded_bytes = os.path.getsize(file_path)
                    if total_size and downloaded_bytes >= total_size:
                        downloaded_paths.append(file_path)
                        task['progress'] = int(((index + 1) / task['total_parts']) * 100)
                        continue
                    else:
                        headers['Range'] = f'bytes={downloaded_bytes}-'
                        
                with requests.get(dlink, headers=headers, stream=True, timeout=15) as r:
                    mode = 'ab' if 'Range' in headers else 'wb'
                    if r.status_code == 200: 
                        mode = 'wb'
                        downloaded_bytes = 0
                    
                    current_file_total = int(r.headers.get('content-length', 0)) + downloaded_bytes
                    start_time = time.time()
                    bytes_since_start = 0
                    
                    with open(file_path, mode) as f:
                        for chunk in r.iter_content(chunk_size=65536):
                            if task['cancel_flag']: return
                            
                            while task['pause_flag']:
                                task['status'] = 'paused'
                                task['speed'] = '0.0 MB/s'
                                time.sleep(1)
                                if task['cancel_flag']: return
                                start_time = time.time()
                                bytes_since_start = 0
                                
                            task['status'] = 'downloading'
                            
                            if chunk:
                                f.write(chunk)
                                downloaded_bytes += len(chunk)
                                bytes_since_start += len(chunk)
                                
                                if current_file_total > 0:
                                    part_progress = downloaded_bytes / current_file_total
                                    task['progress'] = int(((index + part_progress) / task['total_parts']) * 100)
                                
                                elapsed = time.time() - start_time
                                if elapsed > 1.0:
                                    speed = bytes_since_start / elapsed / (1024 * 1024)
                                    task['speed'] = f"{speed:.1f} MB/s"
                                    start_time = time.time()
                                    bytes_since_start = 0
                                    
                downloaded_paths.append(file_path)

            if task['cancel_flag']: return

            # Ekstrakcja dla HTTP
            task['status'] = 'extracting'
            task['progress'] = 100
            task['speed'] = 'Rozpakowywanie...'
            
            part1 = next((f for f in downloaded_paths if "part_1.rar" in f), None)
            
            if part1:
                os.makedirs(game_files_dir, exist_ok=True)
                try:
                    with rarfile.RarFile(part1) as rf:
                        rf.extractall(path=game_files_dir)
                    
                    # Czyszczenie archiwów
                    task['speed'] = 'Czyszczenie...'
                    for file_path in downloaded_paths:
                        try:
                            if os.path.exists(file_path):
                                os.remove(file_path)
                        except Exception as e:
                            print(f"Nie udało się usunąć {file_path}: {e}")
                            
                except Exception as e:
                    pass

        # Opcja 2: Pobieranie przez Torrent (Fallback, gdy brakuje FF)
        else:
            rutor_link = get_rutor_link(game_url)
            if not rutor_link:
                raise Exception("Brak dostępnych linków FuckingFast oraz RuTor.")
                
            task['method'] = 'torrent'
            task['status'] = 'downloading'
            task['speed'] = '0.0 MB/s'
            
            torrent_path = os.path.join(target_folder, "game.torrent")
            tr = requests.get(rutor_link, headers={'User-Agent': 'Mozilla/5.0'})
            tr.raise_for_status()
            with open(torrent_path, 'wb') as f:
                f.write(tr.content)
                
            ses = lt.session({'listen_interfaces': '0.0.0.0:6881'})
            info = lt.torrent_info(torrent_path)
            
            params = {
                'save_path': target_folder,
                'storage_mode': lt.storage_mode_t(2),
                'ti': info
            }
            handle = ses.add_torrent(params)
            
            was_paused = False
            
            while not handle.status().is_seeding:
                if task['cancel_flag']:
                    ses.remove_torrent(handle)
                    return
                
                while task['pause_flag']:
                    task['status'] = 'paused'
                    task['speed'] = '0.0 MB/s'
                    if not was_paused:
                        handle.pause()
                        was_paused = True
                    time.sleep(1)
                    if task['cancel_flag']:
                        ses.remove_torrent(handle)
                        return
                        
                if was_paused:
                    handle.resume()
                    was_paused = False
                    
                task['status'] = 'downloading'
                s = handle.status()
                
                task['progress'] = int(s.progress * 100)
                speed_mb = s.download_rate / (1024 * 1024)
                task['speed'] = f"{speed_mb:.1f} MB/s"
                
                time.sleep(1)
                
            ses.remove_torrent(handle)
            torrent_root_dir = os.path.join(target_folder, info.name())
            
            if os.path.exists(torrent_root_dir):
                if os.path.isfile(torrent_root_dir):
                    os.makedirs(game_files_dir, exist_ok=True)
                    shutil.move(torrent_root_dir, os.path.join(game_files_dir, info.name()))
                elif os.path.isdir(torrent_root_dir) and os.path.abspath(torrent_root_dir) != os.path.abspath(game_files_dir):
                    if os.path.exists(game_files_dir):
                        shutil.rmtree(game_files_dir)
                    shutil.move(torrent_root_dir, game_files_dir)
                    
        # --- WSPÓLNE ZAKOŃCZENIE (HTTP i Torrent) ---
        task['progress'] = 100
        task['extract_path'] = game_files_dir
        
        # Pobieranie okładki do folderu Game_Files
        if game_image:
            try:
                os.makedirs(game_files_dir, exist_ok=True)
                img_resp = requests.get(game_image, timeout=10)
                if img_resp.status_code == 200:
                    with open(os.path.join(game_files_dir, "cover.png"), "wb") as f:
                        f.write(img_resp.content)
            except Exception as e:
                print(f"Nie udało się pobrać okładki: {e}")

        task['status'] = 'finished'

    except Exception as e:
        task['status'] = 'error'
        task['speed'] = str(e)


# --- LOGIKA APLIKACJI FLASK ---

def clean_spam(val):
    stop_words = [" [Selective", " Download Mirrors", " Mirrors", " Filehoster", " Direct Links"]
    for stop in stop_words:
        if stop in val: val = val.split(stop)[0]
    return val.strip()

def get_fast_links(query):
    query = query.strip()
    url = "https://fitgirl-repacks.site/"
    try:
        with httpx.Client(http2=True, timeout=10.0) as client:
            response = client.get(url, params={'s': query})
            soup = BeautifulSoup(response.text, 'html.parser')
            links = []
            for article in soup.find_all('article')[:8]:
                title_tag = article.find('h1', class_='entry-title')
                if title_tag and title_tag.find('a'):
                    title = title_tag.get_text(strip=True)
                    if not any(x in title for x in ["Updates Digest", "Updates List", "Monthly"]):
                        links.append({"title": title, "url": title_tag.find('a')['href']})
            return links
    except: return []

def get_game_details(url, target_lang):
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        full_title = soup.find("meta", property="og:title")["content"]
        title_parts = full_title.split(' - ')
        title = title_parts[0]
        title_sub = " - ".join(title_parts[1:]) if len(title_parts) > 1 else ""
        if title_sub.lower().endswith("fitgirl repacks"):
            title_sub = title_sub[:-15].strip(" -")
            
        image_url = soup.find("meta", property="og:image")["content"]

        info_parts = []
        labels = get_labels(target_lang)
        entry_content = soup.find("div", class_="entry-content")
        
        has_ff = bool(soup.find('a', href=re.compile(r'fuckingfast\.co', re.I)))
        has_torrent = False
        rutor_tag = soup.find('a', href=re.compile(r'rutor\.info'))
        if rutor_tag and re.search(r'/torrent/(\d+)', rutor_tag['href']):
            has_torrent = True
            
        dl_method = 'none'
        if has_ff: dl_method = 'http'
        elif has_torrent: dl_method = 'torrent'
        
        if entry_content:
            for p in entry_content.find_all("p"):
                if "Genres/Tags" in p.text or "Company" in p.text:
                    p_copy = copy.copy(p)
                    for br in p_copy.find_all("br"): br.replace_with("\n")
                    keywords = {"Genres/Tags": labels['genres'], "Company": labels['company'], "Language": labels['languages'], "Original Size": labels['original_size'], "Repack Size": labels['repack_size']}
                    for line in p_copy.get_text().split("\n"):
                        for key_en, label_pl in keywords.items():
                            if key_en in line and ":" in line:
                                v = clean_spam(line.split(":", 1)[1])
                                if v:
                                    if key_en == "Genres/Tags" and target_lang != 'en': v = translate_text(v, target_lang)
                                    info_parts.append({"key": label_pl, "val": v})
                    break

        description = "Brak opisu."
        for spoiler in soup.find_all("div", class_="su-spoiler"):
            title_div = spoiler.find("div", class_="su-spoiler-title")
            if title_div and "Game Description" in title_div.get_text():
                content = spoiler.find("div", class_="su-spoiler-content").get_text(separator=" ", strip=True)
                description = translate_text(content.split("Game Features")[0].strip(), target_lang)
                break
                
        updates = []
        update_header = soup.find(string=re.compile(r'Game Updates', re.I))
        if update_header:
            container = update_header.find_parent(['h3', 'div', 'p'])
            if container:
                next_div = container.find_next('div')
                if next_div:
                    for link in next_div.find_all('a', href=True):
                        u_url = link['href']
                        u_text = link.get_text(strip=True)
                        if 'filecrypt' in u_url.lower() or 'update' in u_text.lower():
                            updates.append({'name': u_text, 'url': u_url})

        return {
            "title": title, "title_sub": title_sub, "image": image_url, "info": info_parts, 
            "desc": description, "url": url, "dl_method": dl_method,
            "updates": updates
        }
    except: return None

# --- API KOMENTARZY (TOLSTOY) ---
def get_current_ticks():
    return (int(time.time()) * 10000000) + 621355968000000000

@app.route('/api/comments')
def api_comments():
    target_url = request.args.get('url')
    page_marker = request.args.get('page')
    
    if not page_marker or page_marker == 'null':
        page_marker = str(get_current_ticks())
        
    app_id = "6289"
    base_api = "https://web.tolstoycomments.com/api/chatpage/page"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": f"https://web.tolstoycomments.com/widget/index.html?x={app_id}&p={quote(target_url)}",
        "Accept": "*/*",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin"
    }
    
    params = {
        "siteid": app_id, "hash": "null", "url": target_url,
        "down": "true", "sort": "1", "format": "1", "page": page_marker
    }
    
    try:
        resp = requests.get(base_api, params=params, headers=headers, timeout=10)
        if resp.status_code == 404:
            return jsonify({"comments": [], "next_page": None})
        resp.raise_for_status()
        
        data = resp.json().get("data", {})
        comments_out = []
        
        fixed = data.get("chat", {}).get("fixed_comment")
        if fixed and not request.args.get('page'):
            comments_out.append({
                "user": fixed.get("user", {}).get("name", "ADMIN/PIN"),
                "date": "",
                "text": fixed.get("text_template", ""),
                "is_pinned": True,
                "reply": None
            })
            
        for c in data.get("comments", []):
            c_out = {
                "user": c.get("user", {}).get("name", "Anonim"),
                "date": c.get("data_create", ""),
                "text": c.get("text_template", ""),
                "is_pinned": False,
                "reply": None
            }
            reply = c.get("answer_comment")
            if reply:
                c_out["reply"] = {
                    "user": reply.get("user", {}).get("name", "Anonim"),
                    "text": reply.get("text_template", "")
                }
            comments_out.append(c_out)
            
        next_page = None
        if data.get("comments"):
            next_page = data.get("comments")[-1].get("sort")
            
        return jsonify({"comments": comments_out, "next_page": next_page})
    except Exception as e:
        return jsonify({"error": str(e), "comments": []})


# --- API POBIERANIA ---

@app.route('/api/dl/start', methods=['POST'])
def dl_start():
    data = request.json
    game_url = data.get('url')
    game_title = data.get('title')
    game_image = data.get('image')
    
    if game_url not in DOWNLOAD_TASKS or DOWNLOAD_TASKS[game_url]['status'] in ['canceled', 'error']:
        DOWNLOAD_TASKS[game_url] = {
            'status': 'starting', 'progress': 0, 'speed': '0 MB/s',
            'current_part': 0, 'total_parts': 0, 'extract_path': '',
            'cancel_flag': False, 'pause_flag': False, 'method': ''
        }
        thread = threading.Thread(target=download_worker, args=(game_url, game_title, game_image))
        thread.start()
        
    return jsonify({"success": True})

@app.route('/api/dl/pause', methods=['POST'])
def dl_pause():
    url = request.json.get('url')
    if url in DOWNLOAD_TASKS:
        DOWNLOAD_TASKS[url]['pause_flag'] = True
    return jsonify({"success": True})

@app.route('/api/dl/resume', methods=['POST'])
def dl_resume():
    url = request.json.get('url')
    if url in DOWNLOAD_TASKS:
        DOWNLOAD_TASKS[url]['pause_flag'] = False
    return jsonify({"success": True})

@app.route('/api/dl/stop', methods=['POST'])
def dl_stop():
    url = request.json.get('url')
    if url in DOWNLOAD_TASKS:
        DOWNLOAD_TASKS[url]['cancel_flag'] = True
        DOWNLOAD_TASKS[url]['status'] = 'canceled'
    return jsonify({"success": True})

@app.route('/api/dl/status')
def dl_status():
    url = request.args.get('url')
    title = request.args.get('title')

    if url in DOWNLOAD_TASKS:
        return jsonify(DOWNLOAD_TASKS[url])
    
    if title:
        target_folder = os.path.join(DOWNLOAD_DIR, re.sub(r'[^a-zA-Z0-9]', '_', title))
        game_files_dir = os.path.join(target_folder, "Game_Files")
        
        if os.path.exists(game_files_dir):
            setup_found = False
            extract_path = game_files_dir
            
            for root, dirs, files in os.walk(game_files_dir):
                for file in files:
                    if file.lower() == 'setup.exe':
                        setup_found = True
                        extract_path = root
                        break
                if setup_found: break
            
            if setup_found:
                DOWNLOAD_TASKS[url] = {
                    'status': 'finished', 'progress': 100, 'speed': '',
                    'current_part': 0, 'total_parts': 0, 'extract_path': extract_path,
                    'cancel_flag': False, 'pause_flag': False, 'method': ''
                }
                return jsonify(DOWNLOAD_TASKS[url])

    return jsonify({"status": "none"})

@app.route('/api/dl/install', methods=['POST'])
def dl_install():
    url = request.json.get('url')
    if url in DOWNLOAD_TASKS and DOWNLOAD_TASKS[url]['extract_path']:
        extract_dir = DOWNLOAD_TASKS[url]['extract_path']
        setup_path = None
        
        for root, dirs, files in os.walk(extract_dir):
            for file in files:
                if file.lower() == 'setup.exe':
                    setup_path = os.path.join(root, file)
                    break
            if setup_path: break
            
        if setup_path:
            try:
                setup_path_abs = os.path.abspath(setup_path)
                setup_dir_abs = os.path.dirname(setup_path_abs)
                
                if sys.platform == 'win32':
                    os.startfile(setup_path_abs)
                    return jsonify({"success": True, "msg": "Instalator uruchomiony (Windows)!"})
                elif sys.platform.startswith('linux'):
                    safe_path = shlex.quote(setup_path_abs)
                    wine_exec = shutil.which('wine') or shutil.which('wine64')
                    if wine_exec:
                        subprocess.Popen([wine_exec, setup_path_abs], cwd=setup_dir_abs)
                    else:
                        cmd = f'wine {safe_path} || xdg-open {safe_path}'
                        subprocess.Popen(cmd, shell=True, cwd=setup_dir_abs)
                    return jsonify({"success": True, "msg": "Zlecono uruchomienie instalatora (Linux)!"})
                else:
                    return jsonify({"success": False, "msg": f"Nieobsługiwany system operacyjny: {sys.platform}"})
            except Exception as e:
                return jsonify({"success": False, "msg": str(e)})
        
        extract_dir_abs = os.path.abspath(extract_dir)
        if sys.platform == 'win32':
            os.startfile(extract_dir_abs)
        elif sys.platform.startswith('linux'):
            subprocess.Popen(['xdg-open', extract_dir_abs])
            
        return jsonify({"success": True, "msg": "Nie znaleziono setup.exe. Otwieram folder z plikami."})
        
    return jsonify({"success": False})

# --- SZABLON HTML ---

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="{{ lang }}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FitDownloader</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Lexend:wght@300;400;600;800&display=swap" rel="stylesheet">
    <style>
        :root { --dark: #0d0d0f; --card: #16161a; --accent: #00a2ff; --text-main: #ffffff; --text-muted: #94a3b8; }
        body { background-color: var(--dark); color: var(--text-main); font-family: 'Lexend', sans-serif; margin: 0; }
        .navbar { background: rgba(13, 13, 15, 0.95); backdrop-filter: blur(12px); border-bottom: 1px solid #222; padding: 15px 0; }
        .navbar-brand { font-weight: 800; font-size: 1.6rem; letter-spacing: -1px; text-decoration: none; color: white !important; }
        .brand-blue { color: var(--accent); }
        .lang-btn { background: #1e1e24; border: 1px solid #333; color: #777; padding: 4px 10px; border-radius: 8px; text-decoration: none; font-size: 0.8rem; font-weight: 600; transition: 0.2s; }
        .lang-btn.active { background: var(--accent); color: white; border-color: var(--accent); }
        .search-box { background: #1e1e24; border-radius: 12px; border: 1px solid #333; overflow: hidden; display: flex; width: 100%; max-width: 400px; }
        .search-input { background: transparent; border: none; color: white; padding: 10px 15px; flex-grow: 1; }
        .search-input:focus { outline: none; }
        .search-btn { background: var(--accent); border: none; color: white; padding: 0 20px; font-weight: 600; cursor: pointer; }
        
        .game-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 25px; margin-top: 30px; }
        .game-card { background: var(--card); border-radius: 16px; border: 1px solid #222; overflow: hidden; transition: 0.3s; height: 100%; display: flex; flex-direction: column; opacity: 0; transform: translateY(10px); animation: fadeInUp 0.4s forwards; }
        @keyframes fadeInUp { to { opacity: 1; transform: translateY(0); } }
        .card-img-wrapper { width: 100%; height: 400px; background: #111; overflow: hidden; position: relative; }
        .card-img { width: 100%; height: 100%; object-fit: cover; }
        .card-content { padding: 15px; flex-grow: 1; display: flex; flex-direction: column; justify-content: space-between; }
        .card-title { font-weight: 600; font-size: 0.9rem; margin-bottom: 15px; color: #fff; line-height: 1.4; min-height: 2.8rem; }
        .btn-view { background: var(--accent); color: white; text-align: center; padding: 10px; border-radius: 10px; text-decoration: none; font-weight: 600; }
        
        .info-row { background: #1a1a20; padding: 12px 18px; border-radius: 12px; margin-bottom: 10px; border-left: 4px solid var(--accent); }
        .info-key { color: var(--accent); font-weight: 600; font-size: 0.8rem; text-transform: uppercase; }
        .info-val { display: block; color: #eee; margin-top: 2px; font-size: 0.95rem; }
        .desc-box { background: #111114; padding: 25px; border-radius: 18px; border: 1px solid #222; color: #ced4da; line-height: 1.7; }
        
        /* DOWNLOADER STYLES */
        .dl-panel { background: #1a1a20; border-radius: 16px; border: 1px solid #333; padding: 25px; margin-top: 25px; }
        .progress { height: 25px; background-color: #2d2d35; border-radius: 12px; overflow: hidden; margin: 15px 0; }
        .progress-bar { background: linear-gradient(90deg, #00a2ff, #0055ff); transition: width 0.3s ease; font-weight: bold; }
        .btn-dl { background: linear-gradient(135deg, #22c55e, #16a34a); color: white; border: none; padding: 12px 30px; border-radius: 12px; font-weight: 800; font-size: 1.1rem; width: 100%; transition: 0.3s; }
        .btn-dl:hover { transform: scale(1.02); color: white; }
        .btn-ctrl { background: #333; border: none; color: white; padding: 8px 20px; border-radius: 8px; font-weight: 600; margin-right: 10px; flex: 1; }
        .btn-ctrl:hover { background: #444; }
        .btn-danger { background: #ef4444; } .btn-danger:hover { background: #dc2626; }
        .btn-warning { background: #f59e0b; color: black; } .btn-warning:hover { background: #d97706; }
        .btn-install { background: #8b5cf6; border:none; padding: 12px 30px; border-radius: 12px; font-weight: 800; font-size: 1.1rem; width: 100%; color: white; }
        .btn-install:hover { background: #7c3aed; color:white;}
        
        /* COMMENTS STYLES */
        .comment-box { background: #1a1a20; border-radius: 12px; border: 1px solid #333; padding: 15px; margin-bottom: 12px; font-size: 0.95rem; line-height: 1.5; color: #ced4da; }
        .pinned-comment { border-color: #d32f2f; background: rgba(211, 47, 47, 0.05); }
        .comment-reply { margin-top: 10px; padding-left: 15px; border-left: 3px solid #444; background: #111; padding: 10px; border-radius: 6px; font-size: 0.85rem; color: #aaa; }
        .text-accent { color: var(--accent); }

        /* --- RESPONSIVE MOBILE STYLES --- */
        @media (max-width: 768px) {
            .navbar .container { flex-wrap: wrap; gap: 10px; }
            .navbar-brand { font-size: 1.4rem; flex: 1; }
            .lang-switcher { flex: 0; white-space: nowrap; }
            .search-box { order: 3; max-width: 100%; margin: 5px 0 0 0 !important; }
            
            .card-img-wrapper { height: 250px; }
            .display-5 { font-size: 2rem; }
            .desc-box { padding: 15px; font-size: 0.9rem; }
            .info-row { padding: 10px 15px; }
            
            .btn-dl, .btn-install { font-size: 1rem; padding: 10px 20px; }
            .dl-panel { padding: 15px; margin-top: 15px; }
            .row.g-5 { --bs-gutter-y: 2rem; --bs-gutter-x: 1rem; }
            
            .comment-box { padding: 12px; font-size: 0.9rem; }
        }
    </style>
</head>
<body>

<nav class="navbar sticky-top">
    <div class="container d-flex justify-content-between align-items-center">
        <a class="navbar-brand" href="/">FIT<span class="brand-blue">DOWNLOADER</span></a>
        <!-- Wyszukiwarka z dostosowanymi klasami margin dla responsywności -->
        <form class="search-box mx-md-3 my-2 my-md-0" action="/search" method="get">
            <input class="search-input" type="search" name="q" placeholder="{{ labels.search_placeholder }}" required value="{{ query or '' }}">
            <button class="search-btn" type="submit">🔍</button>
        </form>
        <div class="lang-switcher">
            <a href="/set_lang/pl" class="lang-btn {{ 'active' if lang == 'pl' else '' }}">PL</a>
            <a href="/set_lang/en" class="lang-btn {{ 'active' if lang == 'en' else '' }}">EN</a>
        </div>
    </div>
</nav>

<div class="container pb-5">
    {% if query or not game %}
        <h4 class="mt-4 mb-3 fw-bold text-muted">
            {% if query %}{{ labels.results_for }}: <span class="text-white">{{ query }}</span>
            {% else %}{{ labels.welcome }}{% endif %}
        </h4>
        <div id="game-container" class="game-grid"></div>
        <div id="loading-indicator" class="text-center py-5">
            <div class="spinner-border text-primary" role="status"></div>
            <p class="mt-2 text-muted">{{ labels.loading }}</p>
        </div>
    {% elif game %}
        <div class="mt-4 mt-md-5">
            <!-- Dostosowane gap dla urządzeń mobilnych vs desktop -->
            <div class="row g-4 g-lg-5">
                <div class="col-lg-4">
                    <img src="{{ game.image }}" class="w-100 rounded-4 shadow" alt="Poster" onerror="this.src='https://placehold.co/300x450/111111/FFFFFF/png?text=Błąd'">
                    
                    <!-- DOWNLOADER PANEL -->
                    <div class="dl-panel shadow" id="dl-panel">
                        {% if game.dl_method == 'none' %}
                            <button class="btn-dl" id="btn-start" disabled style="background: #3f3f46; color: #a1a1aa; cursor: not-allowed;">🚫 {{ labels.btn_dl_unavailable }}</button>
                        {% else %}
                            <button class="btn-dl" id="btn-start" onclick="startDownload()">⬇ {{ labels.download_btn }}</button>
                        {% endif %}
                        
                        <div id="dl-ui" style="display: none;">
                            <div class="d-flex justify-content-between align-items-end">
                                <span id="dl-status-text" class="fw-bold text-accent">Status...</span>
                                <span id="dl-speed" class="text-muted small">0.0 MB/s</span>
                            </div>
                            
                            <div class="progress" id="dl-progress-container">
                                <div id="dl-bar" class="progress-bar progress-bar-striped progress-bar-animated" role="progressbar" style="width: 0%">0%</div>
                            </div>
                            
                            <div class="d-flex justify-content-between mt-3 gap-2" id="dl-controls">
                                <button class="btn-ctrl btn-warning m-0" id="btn-pause" onclick="pauseDownload()">{{ labels.btn_pause }}</button>
                                <button class="btn-ctrl btn-danger m-0" id="btn-stop" onclick="stopDownload()">{{ labels.btn_stop }}</button>
                            </div>
                            
                            <button class="btn-install mt-3" id="btn-install" style="display: none;" onclick="installGame()">🎮 {{ labels.btn_install }}</button>
                        </div>
                    </div>

                    <div class="mt-3 d-grid gap-2">
                        <a href="{{ game.url }}" target="_blank" class="btn btn-outline-success fw-bold py-2 rounded-3">{{ labels.external_btn }}</a>
                        <a href="javascript:history.back()" class="btn btn-outline-secondary py-2 rounded-3">{{ labels.back_btn }}</a>
                    </div>
                </div>
                
                <div class="col-lg-8">
                    <h1 class="display-5 fw-800 mb-1">{{ game.title }}</h1>
                    {% if game.title_sub %}
                    <h5 class="fw-bold mb-4" style="color: #d1d5db;">{{ game.title_sub }}</h5>
                    {% else %}
                    <div class="mb-4"></div>
                    {% endif %}
                    <div class="row mb-4">
                        {% for item in game.info %}
                        <div class="col-md-6 mb-2">
                            <div class="info-row"><span class="info-key">{{ item.key }}</span><span class="info-val">{{ item.val }}</span></div>
                        </div>
                        {% endfor %}
                    </div>
                    <h5 class="brand-blue fw-bold mb-3">{{ labels.description }}</h5>
                    <div class="desc-box">{{ game.desc | safe }}</div>
                    
                    <!-- UPDATES (ADDITIONAL CONTENT) -->
                    {% if game.updates %}
                    <div class="mt-4">
                        <button class="btn btn-outline-info w-100 text-start fw-bold p-3 rounded-3" onclick="toggleUpdates()">
                            📦 {{ labels.updates_title }} ({{ game.updates|length }}) <span style="float:right;">▼</span>
                        </button>
                        <div id="updates-list" style="display: none;" class="mt-2 p-3 border border-secondary rounded-3" style="background: #111;">
                            <ul class="list-unstyled mb-0">
                                {% for upd in game.updates %}
                                <li class="mb-2"><a href="{{ upd.url }}" target="_blank" class="text-info text-decoration-none fw-bold" style="word-break: break-all;">⯈ {{ upd.name }}</a></li>
                                {% endfor %}
                            </ul>
                        </div>
                    </div>
                    {% endif %}
                    
                    <!-- COMMENTS SECTION -->
                    <div class="mt-5 pt-3 border-top border-secondary">
                        <h5 class="brand-blue fw-bold mb-3">💬 {{ labels.comments_title }}</h5>
                        <div id="pinned-comments-container"></div>
                        <div id="standard-comments-container" style="display: none;" class="mb-3"></div>
                        <button id="btn-load-comments" class="btn btn-outline-light w-100 fw-bold py-2 rounded-3" onclick="handleCommentsClick()">{{ labels.load_comments }}</button>
                    </div>
                    
                </div>
            </div>
        </div>
    {% endif %}
</div>

<script>
    {% if not game %}
    /* --- Main Page Grid Loading --- */
    const container = document.getElementById('game-container');
    const loader = document.getElementById('loading-indicator');

    async function loadGamePreview(item) {
        try {
            const res = await fetch(`/api/game_preview?url=${encodeURIComponent(item.url)}`);
            const data = await res.json();
            if (data && data.image) {
                const card = document.createElement('div');
                card.className = 'game-card';
                card.innerHTML = `
                    <div class="card-img-wrapper"><img src="${data.image}" class="card-img" alt="Okładka" onerror="this.src='https://placehold.co/300x450/111111/FFFFFF/png?text=Błąd'"></div>
                    <div class="card-content">
                        <h5 class="card-title">${item.title}</h5>
                        <a href="/details?url=${encodeURIComponent(item.url)}" class="btn-view">{{ labels.details_btn }}</a>
                    </div>`;
                container.appendChild(card);
            }
        } catch (e) { console.error(e); }
    }

    async function init() {
        if (!container) return;
        let seeds = [];
        {% if query %}
            const res = await fetch(`/api/search_links?q={{ query }}`); seeds = await res.json();
        {% else %}
            const res = await fetch(`/api/featured_seeds`); seeds = await res.json();
        {% endif %}

        if (seeds.length === 0) {
            loader.innerHTML = '<p class="text-muted">{{ labels.no_results }}</p>'; return;
        }
        loader.style.display = 'none';
        for (const item of seeds) await loadGamePreview(item);
    }
    init();

    {% else %}
    /* --- Details Page Logic --- */
    const GAME_URL = "{{ game.url }}";
    const GAME_TITLE = "{{ game.title }}";
    
    // Updates Toggle
    function toggleUpdates() {
        const list = document.getElementById('updates-list');
        list.style.display = list.style.display === 'none' ? 'block' : 'none';
    }
    
    // Comments Logic
    let commentsPage = null;
    let commentsLoading = false;
    let standardCommentsVisible = false;

    async function initComments() {
        try {
            const res = await fetch(`/api/comments?url=${encodeURIComponent(GAME_URL)}`);
            const data = await res.json();
            const pinnedContainer = document.getElementById('pinned-comments-container');
            const stdContainer = document.getElementById('standard-comments-container');
            
            if (data.comments && data.comments.length > 0) {
                data.comments.forEach(c => {
                    let div = document.createElement('div');
                    div.className = c.is_pinned ? 'comment-box pinned-comment' : 'comment-box';
                    
                    let replyHtml = '';
                    if (c.reply) {
                        replyHtml = `<div class="comment-reply"><strong class="text-light">${c.reply.user}:</strong> ${c.reply.text}</div>`;
                    }
                    
                    div.innerHTML = `
                        <div class="d-flex justify-content-between mb-2">
                            <strong class="${c.is_pinned ? 'text-danger' : 'text-accent'}">${c.user}</strong>
                            <small class="text-muted">${c.date}</small>
                        </div>
                        <div class="comment-text">${c.text}</div>
                        ${replyHtml}
                    `;
                    
                    if (c.is_pinned) {
                        pinnedContainer.appendChild(div);
                    } else {
                        stdContainer.appendChild(div);
                    }
                });
                
                if (data.next_page) {
                    commentsPage = data.next_page;
                } else {
                    document.getElementById('btn-load-comments').style.display = 'none';
                }
            } else {
                document.getElementById('btn-load-comments').style.display = 'none';
                pinnedContainer.innerHTML = "<p class='text-muted'>Brak komentarzy na stronie gry.</p>";
            }
        } catch (e) {
            console.error(e);
        }
    }
    
    initComments();

    async function handleCommentsClick() {
        const stdContainer = document.getElementById('standard-comments-container');
        const btn = document.getElementById('btn-load-comments');
        
        if (!standardCommentsVisible) {
            stdContainer.style.display = 'block';
            standardCommentsVisible = true;
            if (commentsPage) {
                btn.innerText = "{{ labels.load_more }}";
            } else {
                btn.style.display = 'none';
            }
            return;
        }
        
        if (commentsLoading || !commentsPage) return;
        commentsLoading = true;
        btn.innerText = "{{ labels.loading }}";
        
        try {
            const res = await fetch(`/api/comments?url=${encodeURIComponent(GAME_URL)}&page=${commentsPage}`);
            const data = await res.json();
            
            if (data.comments && data.comments.length > 0) {
                data.comments.forEach(c => {
                    let div = document.createElement('div');
                    div.className = 'comment-box';
                    
                    let replyHtml = '';
                    if (c.reply) {
                        replyHtml = `<div class="comment-reply"><strong class="text-light">${c.reply.user}:</strong> ${c.reply.text}</div>`;
                    }
                    
                    div.innerHTML = `
                        <div class="d-flex justify-content-between mb-2">
                            <strong class="text-accent">${c.user}</strong>
                            <small class="text-muted">${c.date}</small>
                        </div>
                        <div class="comment-text">${c.text}</div>
                        ${replyHtml}
                    `;
                    stdContainer.appendChild(div);
                });
                
                if (data.next_page) {
                    commentsPage = data.next_page;
                    btn.innerText = "{{ labels.load_more }}";
                } else {
                    btn.style.display = 'none';
                }
            } else {
                btn.style.display = 'none';
            }
        } catch (e) {
            console.error(e);
            btn.innerText = "Błąd pobierania";
        }
        commentsLoading = false;
    }

    // Downloader Logic
    const uiBtnStart = document.getElementById('btn-start');
    const uiPanel = document.getElementById('dl-ui');
    const uiStatusText = document.getElementById('dl-status-text');
    const uiSpeed = document.getElementById('dl-speed');
    const uiBar = document.getElementById('dl-bar');
    const uiBtnPause = document.getElementById('btn-pause');
    const uiBtnStop = document.getElementById('btn-stop');
    const uiBtnInstall = document.getElementById('btn-install');
    const uiControls = document.getElementById('dl-controls');
    const uiProgressContainer = document.getElementById('dl-progress-container');
    let dlInterval;

    function startDownload() {
        fetch('/api/dl/start', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({url: GAME_URL, title: GAME_TITLE, image: "{{ game.image }}"})
        }).then(() => {
            if(uiBtnStart) uiBtnStart.style.display = 'none';
            uiPanel.style.display = 'block';
            uiControls.style.display = 'flex';
            uiBtnPause.style.display = 'block';
            uiBtnStop.style.display = 'block';
            uiBtnInstall.style.display = 'none';
            dlInterval = setInterval(pollStatus, 1000);
        });
    }

    function pauseDownload() {
        const isPaused = uiBtnPause.innerText === '{{ labels.btn_resume }}';
        const endpoint = isPaused ? '/api/dl/resume' : '/api/dl/pause';
        fetch(endpoint, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({url: GAME_URL})
        });
    }

    function stopDownload() {
        fetch('/api/dl/stop', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({url: GAME_URL})
        });
    }

    function installGame() {
        fetch('/api/dl/install', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({url: GAME_URL})
        }).then(r => r.json()).then(d => {
            if(!d.success) alert(d.msg);
        });
    }

    function pollStatus() {
        fetch(`/api/dl/status?url=${encodeURIComponent(GAME_URL)}&title=${encodeURIComponent(GAME_TITLE)}`)
        .then(r => r.json())
        .then(data => {
            if (data.status === 'none' || !data.status) return;

            if (data.status !== 'canceled' && data.status !== 'error' && data.status !== 'finished') {
                if(uiBtnStart) uiBtnStart.style.display = 'none';
                uiPanel.style.display = 'block';
                uiControls.style.display = 'flex';
                uiBtnPause.style.display = 'block';
                uiBtnStop.style.display = 'block';
            }

            if (data.status === 'searching') uiStatusText.innerText = "{{ labels.dl_searching }}";
            if (data.status === 'extracting') uiStatusText.innerText = "{{ labels.dl_extracting }}";
            if (data.status === 'paused') {
                uiStatusText.innerText = "{{ labels.dl_paused }}";
                uiBtnPause.innerText = "{{ labels.btn_resume }}";
                uiBtnPause.classList.replace('btn-warning', 'btn-success');
                uiBar.classList.remove('progress-bar-animated');
            } else {
                uiBtnPause.innerText = "{{ labels.btn_pause }}";
                uiBtnPause.classList.replace('btn-success', 'btn-warning');
                uiBar.classList.add('progress-bar-animated');
            }
            
            if (data.status === 'downloading') {
                if (data.method === 'torrent') {
                    uiStatusText.innerText = "{{ labels.dl_method_torrent }}";
                } else {
                    uiStatusText.innerText = `{{ labels.dl_part }} ${data.current_part}/${data.total_parts}`;
                }
            }

            uiSpeed.innerText = data.speed;
            uiBar.style.width = `${data.progress}%`;
            uiBar.innerText = `${data.progress}%`;

            if (data.status === 'finished') {
                clearInterval(dlInterval);
                uiStatusText.innerText = "{{ labels.dl_finished }}";
                uiSpeed.innerText = "";
                if (uiProgressContainer) uiProgressContainer.style.display = 'none';
                
                uiControls.style.display = 'none';
                uiBtnPause.style.display = 'none';
                uiBtnStop.style.display = 'none';
                
                uiBtnInstall.style.display = 'block';
                if(uiBtnStart) uiBtnStart.style.display = 'none';
                uiPanel.style.display = 'block';
            } else {
                if (uiProgressContainer) uiProgressContainer.style.display = '';
            }

            if (data.status === 'canceled' || data.status === 'error') {
                clearInterval(dlInterval);
                uiStatusText.innerText = data.status === 'canceled' ? "Anulowano" : "{{ labels.dl_error }}";
                uiControls.style.display = 'none';
                uiBtnPause.style.display = 'none';
                uiBtnStop.style.display = 'none';
                
                if(uiBtnStart) {
                    uiBtnStart.style.display = 'block';
                    uiBtnStart.innerText = "Wznów Pobieranie";
                }
            }
        });
    }
    
    pollStatus();
    dlInterval = setInterval(pollStatus, 1500);
    {% endif %}
</script>

</body>
</html>
"""

@app.route('/')
def index():
    lang = session.get('lang', 'pl')
    return render_template_string(HTML_TEMPLATE, lang=lang, labels=get_labels(lang), query=None)

@app.route('/api/featured_seeds')
def featured_seeds():
    selected = random.sample(POPULAR_GAMES, 2)
    all_links = []
    for s in selected: all_links.extend(get_fast_links(s))
    random.shuffle(all_links)
    return jsonify(all_links[:8])

@app.route('/api/search_links')
def api_search_links():
    q = request.args.get('q', '').strip()
    return jsonify(get_fast_links(q))

@app.route('/api/game_preview')
def api_game_preview():
    url = request.args.get('url', '')
    try:
        res = requests.get(url, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        img = soup.find("meta", property="og:image")["content"]
        return jsonify({"image": img})
    except: return jsonify({"image": ""})

@app.route('/set_lang/<lang>')
def set_lang(lang):
    if lang in ['pl', 'en']: session['lang'] = lang
    return redirect(request.referrer or url_for('index'))

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    lang = session.get('lang', 'pl')
    return render_template_string(HTML_TEMPLATE, query=query, lang=lang, labels=get_labels(lang))

@app.route('/details')
def details():
    url = request.args.get('url')
    lang = session.get('lang', 'pl')
    if not url: return "Brak URL", 400
    game_data = get_game_details(url, lang)
    return render_template_string(HTML_TEMPLATE, game=game_data, lang=lang, labels=get_labels(lang), query=None)

if __name__ == "__main__":
    app.run(port=5000, debug=True)
