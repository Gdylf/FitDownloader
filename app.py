import requests
import json
import time
import urllib.parse
import secrets
from bs4 import BeautifulSoup
from flask import Flask, render_template_string, request, url_for, session, redirect, jsonify
import copy
import re
import random
import os
import threading
import rarfile
from urllib.parse import unquote
import subprocess
import sys
import shutil
import shlex

# Graceful fallback jeśli libtorrent nie jest zainstalowany
try:
    import libtorrent as lt
    LIBTORRENT_AVAILABLE = True
except ImportError:
    LIBTORRENT_AVAILABLE = False

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

# --- GLOBALNY MENEDŻER POBIERANIA ---
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


# ===========================================================================
# 3. SYSTEM KOMENTARZY TOLSTOY
# ===========================================================================

def get_current_ticks():
    """Generator ticków (.NET standard używany przez Tolstoy API)"""
    return (int(time.time()) * 10000000) + 621355968000000000

def fetch_comments(target_url, page_marker=None):
    """
    Pobiera komentarze z Tolstoy API dla podanego URL gry.
    Zwraca: { pinned, comments, next_page_marker }
    """
    app_id = "6289"
    base_api = "https://web.tolstoycomments.com/api/chatpage/page"
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        "Referer": f"https://web.tolstoycomments.com/widget/index.html?x={app_id}&p={urllib.parse.quote(target_url)}",
        "Accept": "*/*",
        "Accept-Language": "pl-PL,pl;q=0.9",
        "Sec-Ch-Ua-Platform": '"Linux"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin"
    }

    result = {"pinned": None, "comments": [], "next_page_marker": None}
    current_marker = page_marker if page_marker else get_current_ticks()

    params = {
        "siteid": app_id,
        "hash": "null",
        "url": target_url,
        "down": "true",
        "sort": "1",
        "format": "1",
        "page": current_marker
    }

    try:
        resp = requests.get(base_api, params=params, headers=headers, timeout=15)
        if resp.status_code == 404:
            return result
        resp.raise_for_status()
        data = resp.json().get("data", {})
    except Exception:
        return result

    # Przypięta wiadomość (tylko dla pierwszej strony – brak marker)
    if not page_marker:
        chat_info = data.get("chat", {})
        fixed = chat_info.get("fixed_comment")
        if fixed:
            result["pinned"] = {
                "user": fixed.get("user", {}).get("name", "ADMIN"),
                "text": fixed.get("text_template", "")
            }

    comments = data.get("comments", [])
    for c in comments:
        comment_data = {
            "user": c.get("user", {}).get("name", "Anonim"),
            "date": c.get("data_create", ""),
            "text": c.get("text_template", ""),
            "reply": None
        }
        reply = c.get("answer_comment")
        if reply:
            comment_data["reply"] = {
                "user": reply.get("user", {}).get("name", "Anonim"),
                "text": reply.get("text_template", "")
            }
        result["comments"].append(comment_data)

    if comments:
        result["next_page_marker"] = comments[-1].get("sort")

    return result


# ===========================================================================
# 1. FALLBACK POBIERANIA PRZEZ BITTORRENT (RUTOR)
# ===========================================================================

def get_rutor_link(url):
    """Wyciąga bezpośredni link do pliku .torrent z RuTor na stronie FitGirl."""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        rutor_tag = soup.find('a', href=re.compile(r'rutor\.info'))
        if rutor_tag:
            original_link = rutor_tag['href']
            match = re.search(r'/torrent/(\d+)', original_link)
            if match:
                torrent_id = match.group(1)
                return f"https://d.rutor.info/download/{torrent_id}"
        return None
    except Exception:
        return None

def download_via_torrent(task, torrent_url, target_folder):
    """
    Pobiera grę przez BitTorrent używając libtorrent.
    Pliki lądują w target_folder/Game_Files/.
    Zwraca True przy sukcesie, False przy błędzie/anulowaniu.
    """
    if not LIBTORRENT_AVAILABLE:
        task['status'] = 'error'
        task['speed'] = 'Brak biblioteki libtorrent! Zainstaluj: pip install libtorrent'
        return False

    task['status'] = 'torrent_downloading'
    task['speed'] = 'Pobieranie pliku .torrent...'

    try:
        # Pobierz plik .torrent
        torrent_resp = requests.get(torrent_url, timeout=15)
        torrent_resp.raise_for_status()
        torrent_file_path = os.path.join(target_folder, "game.torrent")
        with open(torrent_file_path, 'wb') as f:
            f.write(torrent_resp.content)

        # Docelowy folder zgodny z ujednoliconym standardem
        game_files_dir = os.path.join(target_folder, "Game_Files")
        os.makedirs(game_files_dir, exist_ok=True)

        # Sesja libtorrent – kompatybilna z v1.x i v2.x
        ses = lt.session()
        try:
            # libtorrent 2.x
            settings = lt.default_settings()
            settings['listen_interfaces'] = '0.0.0.0:6881'
            ses.apply_settings(settings)
        except Exception:
            # libtorrent 1.x fallback
            try:
                ses.listen_on(6881, 6891)
            except Exception:
                pass

        # Tworzenie parametrów torrenta – bez storage_mode_t (crashuje na nowszych)
        try:
            atp = lt.add_torrent_params()
            atp.ti = lt.torrent_info(torrent_file_path)
            atp.save_path = game_files_dir
            handle = ses.add_torrent(atp)
        except Exception:
            # Starszy interfejs dict-based jako fallback
            info = lt.torrent_info(torrent_file_path)
            handle = ses.add_torrent({'ti': info, 'save_path': game_files_dir})

        while not handle.status().is_seeding:
            if task['cancel_flag']:
                ses.remove_torrent(handle)
                return False

            while task['pause_flag']:
                task['status'] = 'paused'
                task['speed'] = '0.0 MB/s'
                time.sleep(1)
                if task['cancel_flag']:
                    ses.remove_torrent(handle)
                    return False

            s = handle.status()
            task['status'] = 'torrent_downloading'
            task['progress'] = int(s.progress * 100)
            dl_rate = s.download_rate if s.download_rate else 0
            task['speed'] = f"{dl_rate / (1024 * 1024):.1f} MB/s"
            time.sleep(1)

        task['extract_path'] = game_files_dir
        return True

    except Exception as e:
        task['status'] = 'error'
        task['speed'] = str(e)
        return False


# ===========================================================================
# 2. DODATKOWA ZAWARTOŚĆ (UPDATES / DLC)
# ===========================================================================

def extract_updates(game_url):
    """Parsuje stronę FitGirl w poszukiwaniu sekcji 'Game Updates' i zwraca listę linków."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }
    try:
        response = requests.get(game_url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
    except Exception:
        return []

    update_header = soup.find(string=re.compile(r'Game Updates', re.I))
    if not update_header:
        return []

    parent = update_header.find_parent(['h3', 'h4', 'div', 'p', 'strong'])
    if not parent:
        return []

    container = parent.find_next('div') or parent.find_next('ul')
    extracted = []
    if container:
        for link in container.find_all('a', href=True):
            href = link['href']
            text = link.get_text(strip=True)
            if text and ('filecrypt' in href.lower() or re.search(r'v[\d\.]+', text, re.I)):
                extracted.append({'name': text, 'url': href})

    return extracted


# ===========================================================================
# LOGIKA TŁUMACZENIA I JĘZYKÓW
# ===========================================================================

def translate_text(text, target_lang):
    if target_lang == 'en' or not text:
        return text
    try:
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl={target_lang}&dt=t&q={text}"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            return "".join([part[0] for part in res.json()[0]])
    except Exception:
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
            'dl_searching': 'Wyszukiwanie linków FuckingFast...', 'dl_paused': 'Wstrzymano',
            'dl_extracting': 'Rozpakowywanie archiwów...', 'dl_finished': 'Zakończono pobieranie!',
            'btn_pause': 'Pauza', 'btn_resume': 'Wznów', 'btn_stop': 'Anuluj',
            'btn_install': 'Zainstaluj (setup.exe)',
            'dl_error': 'Wystąpił błąd', 'dl_part': 'Część',
            'dl_torrent': 'Pobieranie P2P (Torrent)...',
            'dl_searching_torrent': 'Brak FF – szukanie torrenta (RuTor)...',
            'no_links': 'Brak linków do pobrania',
            'updates_show': '📦 Pokaż aktualizacje / DLC', 'updates_hide': '📦 Ukryj aktualizacje',
            'updates_none': 'Brak dostępnych aktualizacji.',
            'comments_show': '💬 Pokaż komentarze', 'comments_load_older': '⬆ Załaduj starsze komentarze',
            'comments_pinned': 'PRZYPIĘTA WIADOMOŚĆ',
        },
        'en': {
            'genres': 'Genres/Tags', 'company': 'Company', 'languages': 'Languages',
            'original_size': 'Original Size', 'repack_size': 'Repack Size',
            'description': 'GAME DESCRIPTION', 'search_placeholder': 'Search for a game...',
            'details_btn': 'Check details', 'back_btn': 'Back', 'external_btn': 'FitGirl Page',
            'results_for': 'Results for', 'welcome': 'Featured Games', 'loading': 'Loading games...',
            'no_results': 'No results found.', 'download_btn': 'Download Game',
            'dl_searching': 'Searching FuckingFast links...', 'dl_paused': 'Paused',
            'dl_extracting': 'Extracting archives...', 'dl_finished': 'Download Finished!',
            'btn_pause': 'Pause', 'btn_resume': 'Resume', 'btn_stop': 'Cancel',
            'btn_install': 'Install (setup.exe)',
            'dl_error': 'Error occurred', 'dl_part': 'Part',
            'dl_torrent': 'P2P Download (Torrent)...',
            'dl_searching_torrent': 'No FF links – searching torrent (RuTor)...',
            'no_links': 'No download links available',
            'updates_show': '📦 Show Updates / DLC', 'updates_hide': '📦 Hide Updates',
            'updates_none': 'No updates available.',
            'comments_show': '💬 Show comments', 'comments_load_older': '⬆ Load older comments',
            'comments_pinned': 'PINNED MESSAGE',
        }
    }
    return labels.get(lang, labels['pl'])


# ===========================================================================
# LOGIKA POBIERANIA HTTP (FUCKINGFAST)
# ===========================================================================

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
    except Exception:
        return []

def extract_direct_link(html_content):
    pattern = r'window\.open\("(https://dl\.fuckingfast\.co/dl/[^"]+)"\)'
    match = re.search(pattern, html_content)
    if match:
        return match.group(1)
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
    except Exception:
        return None

def get_original_filename(url, response):
    cd = response.headers.get('content-disposition')
    if cd:
        fname = re.findall('filename=(.+)', cd)
        if fname:
            return fname[0].strip('"')
    return unquote(os.path.basename(url.split('?')[0]))


# ===========================================================================
# 6. POBIERANIE OKŁADKI (COVER.PNG)
# ===========================================================================

def download_cover(image_url, target_folder):
    """Pobiera okładkę gry i zapisuje jako cover.png obok plików gry."""
    try:
        resp = requests.get(image_url, timeout=10)
        resp.raise_for_status()
        cover_path = os.path.join(target_folder, "cover.png")
        with open(cover_path, 'wb') as f:
            f.write(resp.content)
    except Exception:
        pass  # Błąd okładki nie jest krytyczny


# ===========================================================================
# GŁÓWNY WĄTEK POBIERANIA
# ===========================================================================

def download_worker(game_url, game_title, image_url=None):
    """
    Główny wątek pobierania dla konkretnej gry.
    Obsługuje: FF HTTP, fallback Torrent, ekstrakcję, czyszczenie, okładkę.
    """
    task = DOWNLOAD_TASKS[game_url]
    safe_title = re.sub(r'[^a-zA-Z0-9]', '_', game_title)
    target_folder = os.path.join(DOWNLOAD_DIR, safe_title)
    os.makedirs(target_folder, exist_ok=True)

    try:
        # --- KROK 1: Szukanie linków FuckingFast ---
        task['status'] = 'searching'
        ff_links = extract_fuckingfast_links(game_url)

        # === 1. FALLBACK: Brak linków FF → próbuj Torrent ===
        if not ff_links:
            task['status'] = 'searching_torrent'
            task['speed'] = 'Brak linków FF – szukanie torrenta...'
            rutor_url = get_rutor_link(game_url)

            if not rutor_url:
                task['status'] = 'error'
                task['speed'] = 'Brak linków do pobrania (FF i RuTor niedostępne).'
                return

            success = download_via_torrent(task, rutor_url, target_folder)
            if not success:
                return

            # Okładka po pobraniu torrentem
            if image_url:
                download_cover(image_url, target_folder)

            task['status'] = 'finished'
            task['progress'] = 100
            task['speed'] = ''
            return

        # === 2. TRYB FUCKINGFAST: Rozwiązanie linków bezpośrednich ===
        direct_links = []
        for fl in ff_links:
            if task['cancel_flag']:
                return
            html = get_page_source(fl)
            if html:
                dl = extract_direct_link(html)
                if dl:
                    direct_links.append(dl)

        if not direct_links:
            raise Exception("Nie udało się obejść FuckingFast.")

        task['total_parts'] = len(direct_links)
        downloaded_paths = []

        # --- KROK 2: Pobieranie partów ---
        for index, dlink in enumerate(direct_links):
            if task['cancel_flag']:
                return
            task['current_part'] = index + 1
            task['status'] = 'downloading'
            task['speed'] = '0.0 MB/s'

            # Wstępne pobranie rozmiaru i nazwy pliku
            with requests.get(dlink, stream=True, allow_redirects=True, timeout=10) as r:
                orig_name = get_original_filename(dlink, r)
                if "-selective-" in orig_name.lower():
                    continue
                ext = os.path.splitext(orig_name)[1]
                if not ext or len(ext) > 5:
                    ext = ".rar"
                file_path = os.path.join(target_folder, f"part_{index + 1}{ext}")
                total_size = int(r.headers.get('content-length', 0))

            # Wznawianie pobierania (Range header)
            headers_dl = {}
            downloaded_bytes = 0
            if os.path.exists(file_path):
                downloaded_bytes = os.path.getsize(file_path)
                if total_size and downloaded_bytes >= total_size:
                    downloaded_paths.append(file_path)
                    task['progress'] = int(((index + 1) / task['total_parts']) * 100)
                    continue
                else:
                    headers_dl['Range'] = f'bytes={downloaded_bytes}-'

            # Właściwe pobieranie z wznawianiem
            with requests.get(dlink, headers=headers_dl, stream=True, timeout=15) as r:
                mode = 'ab' if 'Range' in headers_dl else 'wb'
                if r.status_code == 200:
                    mode = 'wb'
                    downloaded_bytes = 0

                current_file_total = int(r.headers.get('content-length', 0)) + downloaded_bytes
                start_time = time.time()
                bytes_since_start = 0

                with open(file_path, mode) as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        if task['cancel_flag']:
                            return

                        # Obsługa pauzy
                        while task['pause_flag']:
                            task['status'] = 'paused'
                            task['speed'] = '0.0 MB/s'
                            time.sleep(1)
                            if task['cancel_flag']:
                                return
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

        if task['cancel_flag']:
            return

        # --- KROK 3: Ekstrakcja do Game_Files/ (5. Ujednolicony system) ---
        task['status'] = 'extracting'
        task['progress'] = 100
        task['speed'] = 'Rozpakowywanie...'

        part1 = next((f for f in downloaded_paths if "part_1.rar" in f), None)
        extract_dir = os.path.join(target_folder, "Game_Files")

        if part1:
            os.makedirs(extract_dir, exist_ok=True)
            try:
                with rarfile.RarFile(part1) as rf:
                    rf.extractall(path=extract_dir)
                task['extract_path'] = extract_dir

                # --- 7. Automatyczne usuwanie .rar po ekstrakcji ---
                task['speed'] = 'Czyszczenie archiwów...'
                for f in downloaded_paths:
                    try:
                        if os.path.exists(f):
                            os.remove(f)
                    except Exception:
                        pass

            except Exception:
                task['extract_path'] = target_folder
        else:
            task['extract_path'] = target_folder

        # --- 6. Pobieranie okładki ---
        if image_url:
            download_cover(image_url, target_folder)

        task['status'] = 'finished'
        task['speed'] = ''

    except Exception as e:
        task['status'] = 'error'
        task['speed'] = str(e)


# ===========================================================================
# LOGIKA APLIKACJI FLASK
# ===========================================================================

def clean_spam(val):
    stop_words = [" [Selective", " Download Mirrors", " Mirrors", " Filehoster", " Direct Links"]
    for stop in stop_words:
        if stop in val:
            val = val.split(stop)[0]
    return val.strip()

def get_fast_links(query):
    """10. Naprawiona wyszukiwarka – requests zamiast httpx (fix antybot) + timeout=15"""
    query = query.strip()
    url = "https://fitgirl-repacks.site/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    try:
        response = requests.get(url, params={'s': query}, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        links = []
        for article in soup.find_all('article')[:8]:
            title_tag = article.find('h1', class_='entry-title')
            if title_tag and title_tag.find('a'):
                title = title_tag.get_text(strip=True)
                if not any(x in title for x in ["Updates Digest", "Updates List", "Monthly"]):
                    links.append({"title": title, "url": title_tag.find('a')['href']})
        return links
    except Exception:
        return []

def get_game_details(url, target_lang):
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')

        # === 4. INTELIGENTNE FORMATOWANIE TYTUŁU ===
        raw_title = soup.find("meta", property="og:title")["content"]
        # Usuń " - FitGirl Repacks" i podobny spam z końca
        raw_title = re.sub(r'\s*[-–]\s*FitGirl Repacks.*$', '', raw_title, flags=re.I).strip()
        # Podziel na główny tytuł i podtytuł (wersja/DLC oddzielone " - ")
        # np. "Cyberpunk 2077 - v2.12" → title="Cyberpunk 2077", subtitle="v2.12"
        title_parts = re.split(r'\s+[-–]\s+(?=v[\d\.]+|Update|DLC|Season|Complete|GOTY|Build)', raw_title, maxsplit=1)
        main_title = title_parts[0].strip()
        sub_title = title_parts[1].strip() if len(title_parts) > 1 else ""

        # Fallback na brak okładki zamiast krytycznego błędu UI (10.)
        try:
            image_url = soup.find("meta", property="og:image")["content"]
        except Exception:
            image_url = "https://placehold.co/300x450/111111/FFFFFF/png?text=Brak+Okładki"

        info_parts = []
        labels = get_labels(target_lang)
        entry_content = soup.find("div", class_="entry-content")

        if entry_content:
            for p in entry_content.find_all("p"):
                if "Genres/Tags" in p.text or "Company" in p.text:
                    p_copy = copy.copy(p)
                    for br in p_copy.find_all("br"):
                        br.replace_with("\n")
                    keywords = {
                        "Genres/Tags": labels['genres'], "Company": labels['company'],
                        "Language": labels['languages'], "Original Size": labels['original_size'],
                        "Repack Size": labels['repack_size']
                    }
                    for line in p_copy.get_text().split("\n"):
                        for key_en, label_pl in keywords.items():
                            if key_en in line and ":" in line:
                                v = clean_spam(line.split(":", 1)[1])
                                if v:
                                    if key_en == "Genres/Tags" and target_lang != 'en':
                                        v = translate_text(v, target_lang)
                                    info_parts.append({"key": label_pl, "val": v})
                    break

        description = "Brak opisu."
        for spoiler in soup.find_all("div", class_="su-spoiler"):
            title_div = spoiler.find("div", class_="su-spoiler-title")
            if title_div and "Game Description" in title_div.get_text():
                content = spoiler.find("div", class_="su-spoiler-content").get_text(separator=" ", strip=True)
                description = translate_text(content.split("Game Features")[0].strip(), target_lang)
                break

        # Sprawdzenie dostępności linków (FF / Rutor) dla UI przycisku
        ff_links = extract_fuckingfast_links(url)
        has_ff = len(ff_links) > 0
        has_rutor = get_rutor_link(url) is not None if not has_ff else False
        can_download = has_ff or has_rutor

        return {
            "title": main_title,
            "subtitle": sub_title,
            "image": image_url,
            "info": info_parts,
            "desc": description,
            "url": url,
            "can_download": can_download,
        }
    except Exception:
        return None


# ===========================================================================
# API POBIERANIA
# ===========================================================================

@app.route('/api/dl/start', methods=['POST'])
def dl_start():
    data = request.json
    game_url = data.get('url')
    game_title = data.get('title')
    image_url = data.get('image', None)

    if game_url not in DOWNLOAD_TASKS or DOWNLOAD_TASKS[game_url]['status'] in ['canceled', 'error']:
        DOWNLOAD_TASKS[game_url] = {
            'status': 'starting', 'progress': 0, 'speed': '0 MB/s',
            'current_part': 0, 'total_parts': 0, 'extract_path': '',
            'cancel_flag': False, 'pause_flag': False
        }
        thread = threading.Thread(target=download_worker, args=(game_url, game_title, image_url))
        thread.daemon = True
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

    # Detekcja plików na dysku po restarcie aplikacji
    if title:
        target_folder = os.path.join(DOWNLOAD_DIR, re.sub(r'[^a-zA-Z0-9]', '_', title))
        if os.path.exists(target_folder):
            setup_found = False
            extract_path = target_folder
            for root, dirs, files in os.walk(target_folder):
                for file in files:
                    if file.lower() == 'setup.exe':
                        setup_found = True
                        extract_path = root
                        break
                if setup_found:
                    break
            if setup_found:
                DOWNLOAD_TASKS[url] = {
                    'status': 'finished', 'progress': 100, 'speed': '',
                    'current_part': 0, 'total_parts': 0, 'extract_path': extract_path,
                    'cancel_flag': False, 'pause_flag': False
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
            if setup_path:
                break

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
                    return jsonify({"success": False, "msg": f"Nieobsługiwany system: {sys.platform}"})
            except Exception as e:
                return jsonify({"success": False, "msg": str(e)})

        extract_dir_abs = os.path.abspath(extract_dir)
        if sys.platform == 'win32':
            os.startfile(extract_dir_abs)
        elif sys.platform.startswith('linux'):
            subprocess.Popen(['xdg-open', extract_dir_abs])
        return jsonify({"success": True, "msg": "Nie znaleziono setup.exe. Otwieram folder z plikami."})

    return jsonify({"success": False})

# --- API: Komentarze Tolstoy ---
@app.route('/api/comments')
def api_comments():
    url = request.args.get('url', '')
    marker = request.args.get('marker', None)
    if not url:
        return jsonify({"pinned": None, "comments": [], "next_page_marker": None})
    data = fetch_comments(url, page_marker=marker)
    return jsonify(data)

# --- API: Aktualizacje / DLC ---
@app.route('/api/updates')
def api_updates():
    url = request.args.get('url', '')
    if not url:
        return jsonify([])
    return jsonify(extract_updates(url))


# ===========================================================================
# SZABLON HTML
# ===========================================================================

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

        /* NAVBAR */
        .navbar { background: rgba(13, 13, 15, 0.95); backdrop-filter: blur(12px); border-bottom: 1px solid #222; padding: 15px 0; }
        .navbar-brand { font-weight: 800; font-size: 1.6rem; letter-spacing: -1px; text-decoration: none; color: white !important; }
        .brand-blue { color: var(--accent); }
        .lang-btn { background: #1e1e24; border: 1px solid #333; color: #777; padding: 4px 10px; border-radius: 8px; text-decoration: none; font-size: 0.8rem; font-weight: 600; transition: 0.2s; }
        .lang-btn.active { background: var(--accent); color: white; border-color: var(--accent); }
        .search-box { background: #1e1e24; border-radius: 12px; border: 1px solid #333; overflow: hidden; display: flex; width: 100%; max-width: 400px; }
        .search-input { background: transparent; border: none; color: white; padding: 10px 15px; flex-grow: 1; }
        .search-input:focus { outline: none; }
        .search-btn { background: var(--accent); border: none; color: white; padding: 0 20px; font-weight: 600; cursor: pointer; }

        /* SIATKA KART */
        .game-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 25px; margin-top: 30px; }
        .game-card { background: var(--card); border-radius: 16px; border: 1px solid #222; overflow: hidden; transition: 0.3s; height: 100%; display: flex; flex-direction: column; opacity: 0; transform: translateY(10px); animation: fadeInUp 0.4s forwards; }
        @keyframes fadeInUp { to { opacity: 1; transform: translateY(0); } }
        .card-img-wrapper { width: 100%; height: 400px; background: #111; overflow: hidden; }
        .card-img { width: 100%; height: 100%; object-fit: cover; }
        .card-content { padding: 15px; flex-grow: 1; display: flex; flex-direction: column; justify-content: space-between; }
        .card-title { font-weight: 600; font-size: 0.9rem; margin-bottom: 15px; color: #fff; line-height: 1.4; min-height: 2.8rem; }
        .btn-view { background: var(--accent); color: white; text-align: center; padding: 10px; border-radius: 10px; text-decoration: none; font-weight: 600; display: block; }

        /* DETALE GRY */
        /* 4. Inteligentne formatowanie tytułu */
        .game-main-title { font-size: 2.2rem; font-weight: 800; line-height: 1.2; margin-bottom: 4px; }
        .game-subtitle { font-size: 1rem; color: var(--text-muted); margin-bottom: 24px; font-weight: 400; }

        .info-row { background: #1a1a20; padding: 12px 18px; border-radius: 12px; margin-bottom: 10px; border-left: 4px solid var(--accent); }
        .info-key { color: var(--accent); font-weight: 600; font-size: 0.8rem; text-transform: uppercase; }
        .info-val { display: block; color: #eee; margin-top: 2px; font-size: 0.95rem; }
        .desc-box { background: #111114; padding: 25px; border-radius: 18px; border: 1px solid #222; color: #ced4da; line-height: 1.7; }

        /* DOWNLOADER */
        .dl-panel { background: #1a1a20; border-radius: 16px; border: 1px solid #333; padding: 25px; margin-top: 25px; }
        .progress { height: 25px; background-color: #2d2d35; border-radius: 12px; overflow: hidden; margin: 15px 0; }
        .progress-bar { background: linear-gradient(90deg, #00a2ff, #0055ff); transition: width 0.3s ease; font-weight: bold; }
        .btn-dl { background: linear-gradient(135deg, #22c55e, #16a34a); color: white; border: none; padding: 12px 30px; border-radius: 12px; font-weight: 800; font-size: 1.1rem; width: 100%; transition: 0.3s; cursor: pointer; }
        .btn-dl:hover:not(:disabled) { transform: scale(1.02); }
        .btn-dl:disabled { background: #2a2a35; color: #555; cursor: not-allowed; }
        .btn-ctrl { background: #333; border: none; color: white; padding: 8px 20px; border-radius: 8px; font-weight: 600; cursor: pointer; transition: 0.2s; }
        .btn-ctrl:hover { background: #444; }
        .btn-ctrl.danger { background: #ef4444; } .btn-ctrl.danger:hover { background: #dc2626; }
        .btn-ctrl.warning { background: #f59e0b; color: black; } .btn-ctrl.warning:hover { background: #d97706; }
        .btn-ctrl.success-ctrl { background: #22c55e; color: black; }
        .btn-install { background: #8b5cf6; border: none; padding: 12px 30px; border-radius: 12px; font-weight: 800; font-size: 1.1rem; width: 100%; color: white; cursor: pointer; }
        .btn-install:hover { background: #7c3aed; }

        /* 2. PANEL AKTUALIZACJI/DLC */
        .section-toggle { background: #1e1e28; border: 1px solid #2a2a38; color: #aab8c8; padding: 10px 18px; border-radius: 10px; font-size: 0.85rem; font-weight: 600; cursor: pointer; width: 100%; text-align: left; margin-top: 20px; transition: 0.2s; }
        .section-toggle:hover { background: #252534; color: white; border-color: var(--accent); }
        .updates-panel { background: #0f0f14; border: 1px solid #1e1e2a; border-radius: 10px; padding: 15px; margin-top: 8px; display: none; }
        .update-link { display: block; padding: 8px 14px; background: #171722; border-radius: 8px; color: #7dd3fc; text-decoration: none; font-size: 0.85rem; margin-bottom: 6px; border-left: 3px solid var(--accent); transition: 0.2s; }
        .update-link:hover { background: #1e1e2e; color: white; }

        /* 3. KOMENTARZE TOLSTOY */
        .pinned-comment { border: 2px solid #dc2626; background: #1a0808; border-radius: 12px; padding: 18px; margin: 20px 0; }
        .pinned-label { color: #ef4444; font-weight: 800; font-size: 0.85rem; margin-bottom: 8px; letter-spacing: 0.5px; }
        .pinned-text { color: #fca5a5; font-size: 0.88rem; line-height: 1.6; }
        .comment-box { border-bottom: 1px solid #1a1a22; padding: 14px 0; }
        .comment-user { color: #7dd3fc; font-weight: 600; font-size: 0.85rem; }
        .comment-date { color: #666; font-size: 0.75rem; margin-left: 10px; }
        .comment-text { color: #ccc; margin-top: 6px; font-size: 0.87rem; line-height: 1.6; }
        .comment-reply { margin: 10px 0 0 25px; border-left: 3px solid #2a2a35; padding: 10px 15px; background: #0f0f14; border-radius: 0 8px 8px 0; }
        .comment-reply .comment-user { color: #888; }
        .comment-reply .comment-text { color: #999; }
        .btn-comments { background: #1e1e28; border: 1px solid #2a2a38; color: #aab8c8; padding: 10px 18px; border-radius: 10px; font-size: 0.85rem; font-weight: 600; cursor: pointer; width: 100%; margin-top: 15px; transition: 0.2s; }
        .btn-comments:hover { background: #252534; color: white; border-color: var(--accent); }
        .btn-comments:disabled { opacity: 0.5; cursor: default; }

        /* 9. RESPONSYWNOŚĆ MOBILNA */
        @media (max-width: 768px) {
            .navbar .container { flex-wrap: wrap; gap: 8px; padding: 0 12px; }
            .navbar-brand { font-size: 1.2rem; }
            .search-box { max-width: 100%; order: 3; }
            .lang-switcher { margin-left: auto; }
            .game-grid { grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 12px; }
            .card-img-wrapper { height: 250px; }
            .game-main-title { font-size: 1.4rem; }
            .dl-panel { padding: 15px; }
            .desc-box { padding: 16px; }
            .container { padding: 0 12px; }
        }
    </style>
</head>
<body>

<nav class="navbar sticky-top">
    <div class="container d-flex justify-content-between align-items-center flex-wrap gap-2">
        <a class="navbar-brand" href="/">FIT<span class="brand-blue">DOWNLOADER</span></a>
        <form class="search-box" action="/search" method="get">
            <input class="search-input" type="search" name="q" placeholder="{{ labels.search_placeholder }}" required value="{{ query or '' }}">
            <button class="search-btn" type="submit">🔍</button>
        </form>
        <div class="lang-switcher d-flex gap-1">
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
        <div class="mt-5">
            <div class="row g-5">
                <div class="col-lg-4">
                    <img src="{{ game.image }}" class="w-100 rounded-4 shadow" alt="Poster"
                         onerror="this.src='https://placehold.co/300x450/111111/FFFFFF/png?text=Brak+Okładki'">

                    <!-- DOWNLOADER PANEL -->
                    <div class="dl-panel shadow" id="dl-panel">
                        {% if game.can_download %}
                            <button class="btn-dl" id="btn-start" onclick="startDownload()">⬇ {{ labels.download_btn }}</button>
                        {% else %}
                            <button class="btn-dl" disabled>🚫 {{ labels.no_links }}</button>
                        {% endif %}

                        <!-- 8. UI pobierania: ukrywane elementy -->
                        <div id="dl-ui" style="display: none;">
                            <div class="d-flex justify-content-between align-items-center mt-2">
                                <span id="dl-status-text" class="fw-bold" style="color: var(--accent); font-size: 0.9rem;">...</span>
                                <span id="dl-speed" class="text-muted small">0.0 MB/s</span>
                            </div>
                            <div class="progress" id="dl-progress-wrap">
                                <div id="dl-bar" class="progress-bar progress-bar-striped progress-bar-animated" style="width: 0%">0%</div>
                            </div>
                            <div class="d-flex justify-content-between mt-2" id="dl-controls">
                                <button class="btn-ctrl warning" id="btn-pause" onclick="pauseDownload()">{{ labels.btn_pause }}</button>
                                <button class="btn-ctrl danger" id="btn-stop" onclick="stopDownload()">{{ labels.btn_stop }}</button>
                            </div>
                            <button class="btn-install mt-3" id="btn-install" style="display:none;" onclick="installGame()">
                                🎮 {{ labels.btn_install }}
                            </button>
                        </div>
                    </div>

                    <div class="mt-3 d-grid gap-2">
                        <a href="{{ game.url }}" target="_blank" class="btn btn-outline-success fw-bold py-2 rounded-3">{{ labels.external_btn }}</a>
                        <a href="javascript:history.back()" class="btn btn-outline-secondary py-2 rounded-3">{{ labels.back_btn }}</a>
                    </div>
                </div>

                <div class="col-lg-8">
                    <!-- 4. Sformatowany tytuł gry -->
                    <h1 class="game-main-title">{{ game.title }}</h1>
                    {% if game.subtitle %}
                        <p class="game-subtitle">{{ game.subtitle }}</p>
                    {% endif %}

                    <div class="row mb-4">
                        {% for item in game.info %}
                        <div class="col-md-6 mb-2">
                            <div class="info-row">
                                <span class="info-key">{{ item.key }}</span>
                                <span class="info-val">{{ item.val }}</span>
                            </div>
                        </div>
                        {% endfor %}
                    </div>

                    <h5 class="brand-blue fw-bold mb-3">{{ labels.description }}</h5>
                    <div class="desc-box">{{ game.desc | safe }}</div>

                    <!-- 2. Panel Aktualizacji / DLC -->
                    <button class="section-toggle" id="btn-updates" onclick="toggleUpdates()">{{ labels.updates_show }}</button>
                    <div class="updates-panel" id="updates-panel">
                        <div id="updates-content">
                            <div class="text-muted small d-flex align-items-center gap-2" id="updates-loading">
                                <div class="spinner-border spinner-border-sm"></div> Ładowanie...
                            </div>
                        </div>
                    </div>

                    <!-- 3. Komentarze Tolstoy: Przypięte ładowane automatycznie -->
                    <div id="pinned-area"></div>

                    <button class="btn-comments" id="btn-show-comments" onclick="loadComments()">{{ labels.comments_show }}</button>
                    <div id="comments-area" style="display:none; margin-top: 10px;"></div>
                    <button class="btn-comments" id="btn-load-older" style="display:none;" onclick="loadOlderComments()">{{ labels.comments_load_older }}</button>
                </div>
            </div>
        </div>
    {% endif %}
</div>

<script>
{% if not game %}
/* ===== STRONA GŁÓWNA / WYNIKI WYSZUKIWANIA ===== */
const container = document.getElementById('game-container');
const loader    = document.getElementById('loading-indicator');

async function loadGamePreview(item) {
    try {
        const res  = await fetch(`/api/game_preview?url=${encodeURIComponent(item.url)}`);
        const data = await res.json();
        const imgSrc = data.image || 'https://placehold.co/300x450/111111/FFFFFF/png?text=Brak+Okładki';
        // Ukryj podtytuł (wersja/DLC) na karcie – widoczny tylko w detalach
        const mainTitle = item.title
            .replace(/\s*[-–]\s*FitGirl Repacks.*$/i, '')
            .replace(/\s*[-–]\s*(v[\d\.]+|Update|DLC|Season|Complete|GOTY|Build).*$/i, '')
            .trim();
        const card = document.createElement('div');
        card.className = 'game-card';
        card.innerHTML = `
            <div class="card-img-wrapper">
                <img src="${imgSrc}" class="card-img" alt="Okładka"
                     onerror="this.src='https://placehold.co/300x450/111111/FFFFFF/png?text=Brak+Okładki'">
            </div>
            <div class="card-content">
                <h5 class="card-title">${mainTitle}</h5>
                <a href="/details?url=${encodeURIComponent(item.url)}" class="btn-view">{{ labels.details_btn }}</a>
            </div>`;
        container.appendChild(card);
    } catch(e) { console.error(e); }
}

async function init() {
    if (!container) return;
    let seeds = [];
    {% if query %}
        const res = await fetch(`/api/search_links?q={{ query }}`);
        seeds = await res.json();
    {% else %}
        const res = await fetch(`/api/featured_seeds`);
        seeds = await res.json();
    {% endif %}
    if (seeds.length === 0) {
        loader.innerHTML = '<p class="text-muted">{{ labels.no_results }}</p>'; return;
    }
    loader.style.display = 'none';
    for (const item of seeds) await loadGamePreview(item);
}
init();

{% else %}
/* ===== STRONA SZCZEGÓŁÓW GRY ===== */
const GAME_URL   = "{{ game.url }}";
const GAME_TITLE = "{{ game.title }}";
const GAME_IMAGE = "{{ game.image }}";

const uiBtnStart      = document.getElementById('btn-start');
const uiDlUi          = document.getElementById('dl-ui');
const uiStatusText    = document.getElementById('dl-status-text');
const uiSpeed         = document.getElementById('dl-speed');
const uiBar           = document.getElementById('dl-bar');
const uiProgressWrap  = document.getElementById('dl-progress-wrap');
const uiBtnPause      = document.getElementById('btn-pause');
const uiBtnInstall    = document.getElementById('btn-install');
const uiControls      = document.getElementById('dl-controls');

let dlInterval;

/* --- DOWNLOADER --- */
function startDownload() {
    fetch('/api/dl/start', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ url: GAME_URL, title: GAME_TITLE, image: GAME_IMAGE })
    }).then(() => {
        if (uiBtnStart) uiBtnStart.style.display = 'none';
        uiDlUi.style.display = 'block';
        uiControls.style.display = 'flex';
        uiBtnInstall.style.display = 'none';
        uiProgressWrap.style.display = 'block';
        dlInterval = setInterval(pollStatus, 1000);
    });
}

function pauseDownload() {
    const isPaused = uiBtnPause.innerText.trim() === '{{ labels.btn_resume }}';
    fetch(isPaused ? '/api/dl/resume' : '/api/dl/pause', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ url: GAME_URL })
    });
}

function stopDownload() {
    fetch('/api/dl/stop', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ url: GAME_URL })
    });
}

function installGame() {
    fetch('/api/dl/install', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ url: GAME_URL })
    }).then(r => r.json()).then(d => { if (!d.success) alert(d.msg); });
}

function pollStatus() {
    fetch(`/api/dl/status?url=${encodeURIComponent(GAME_URL)}&title=${encodeURIComponent(GAME_TITLE)}`)
    .then(r => r.json())
    .then(data => {
        if (!data.status || data.status === 'none') return;

        if (!['canceled', 'error'].includes(data.status)) {
            if (uiBtnStart) uiBtnStart.style.display = 'none';
            uiDlUi.style.display = 'block';
        }

        /* Teksty statusów */
        const statusMap = {
            'searching':          '{{ labels.dl_searching }}',
            'searching_torrent':  '{{ labels.dl_searching_torrent }}',
            'torrent_downloading':'{{ labels.dl_torrent }}',
            'extracting':         '{{ labels.dl_extracting }}',
        };
        if (statusMap[data.status]) uiStatusText.innerText = statusMap[data.status];
        if (data.status === 'downloading')
            uiStatusText.innerText = `{{ labels.dl_part }} ${data.current_part}/${data.total_parts}`;

        /* Pauza / wznów */
        if (data.status === 'paused') {
            uiStatusText.innerText = '{{ labels.dl_paused }}';
            uiBtnPause.innerText = '{{ labels.btn_resume }}';
            uiBtnPause.className = 'btn-ctrl success-ctrl';
            uiBar.classList.remove('progress-bar-animated');
        } else if (!['finished','canceled','error'].includes(data.status)) {
            uiBtnPause.innerText = '{{ labels.btn_pause }}';
            uiBtnPause.className = 'btn-ctrl warning';
            uiBar.classList.add('progress-bar-animated');
        }

        uiSpeed.innerText = data.speed || '';
        uiBar.style.width  = `${data.progress}%`;
        uiBar.innerText    = `${data.progress}%`;

        /* 8. Po zakończeniu: ukryj progress + kontrolki, pokaż instalator */
        if (data.status === 'finished') {
            clearInterval(dlInterval);
            uiStatusText.innerText = '{{ labels.dl_finished }}';
            uiSpeed.innerText = '';
            uiBar.classList.remove('progress-bar-animated', 'progress-bar-striped');
            uiBar.classList.add('bg-success');
            uiControls.style.display     = 'none';
            uiProgressWrap.style.display = 'none';   /* ukryj pasek */
            uiBtnInstall.style.display   = 'block';  /* pokaż instalator */
        }

        if (data.status === 'canceled' || data.status === 'error') {
            clearInterval(dlInterval);
            uiStatusText.innerText = data.status === 'canceled'
                ? 'Anulowano'
                : '{{ labels.dl_error }}: ' + (data.speed || '');
            uiControls.style.display = 'none';
            if (uiBtnStart) {
                uiBtnStart.style.display = 'block';
                uiBtnStart.innerText = '⬇ Spróbuj ponownie';
            }
        }
    });
}

/* --- 2. PANEL AKTUALIZACJI / DLC --- */
let updatesLoaded  = false;
let updatesVisible = false;

function toggleUpdates() {
    const panel = document.getElementById('updates-panel');
    const btn   = document.getElementById('btn-updates');
    updatesVisible = !updatesVisible;
    panel.style.display = updatesVisible ? 'block' : 'none';
    btn.innerText = updatesVisible ? '{{ labels.updates_hide }}' : '{{ labels.updates_show }}';

    if (updatesVisible && !updatesLoaded) {
        fetch(`/api/updates?url=${encodeURIComponent(GAME_URL)}`)
        .then(r => r.json())
        .then(data => {
            updatesLoaded = true;
            const el = document.getElementById('updates-content');
            if (!data || data.length === 0) {
                el.innerHTML = '<p class="text-muted small px-1">{{ labels.updates_none }}</p>';
                return;
            }
            el.innerHTML = data.map(u =>
                `<a href="${u.url}" target="_blank" class="update-link">📥 ${u.name}</a>`
            ).join('');
        });
    }
}

/* --- 3. KOMENTARZE TOLSTOY --- */
let nextMarker = null;

function renderComment(c) {
    const replyHtml = c.reply ? `
        <div class="comment-reply">
            <span class="comment-user">${c.reply.user}</span>
            <div class="comment-text">${c.reply.text}</div>
        </div>` : '';
    return `
        <div class="comment-box">
            <span class="comment-user">${c.user}</span>
            <span class="comment-date">${c.date}</span>
            <div class="comment-text">${c.text}</div>
            ${replyHtml}
        </div>`;
}

function loadComments() {
    const btn = document.getElementById('btn-show-comments');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Ładowanie...';

    fetch(`/api/comments?url=${encodeURIComponent(GAME_URL)}`)
    .then(r => r.json())
    .then(data => {
        renderPinned(data.pinned);
        const area = document.getElementById('comments-area');
        area.style.display = 'block';
        area.innerHTML = data.comments.map(renderComment).join('');
        nextMarker = data.next_page_marker;
        btn.style.display = 'none';
        if (nextMarker) document.getElementById('btn-load-older').style.display = 'block';
    })
    .catch(() => {
        btn.disabled = false;
        btn.innerHTML = '{{ labels.comments_show }}';
    });
}

function loadOlderComments() {
    const btn = document.getElementById('btn-load-older');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Ładowanie...';

    fetch(`/api/comments?url=${encodeURIComponent(GAME_URL)}&marker=${nextMarker}`)
    .then(r => r.json())
    .then(data => {
        document.getElementById('comments-area').innerHTML += data.comments.map(renderComment).join('');
        nextMarker = data.next_page_marker;
        btn.disabled = false;
        if (nextMarker && data.comments.length > 0) {
            btn.innerHTML = '{{ labels.comments_load_older }}';
            btn.style.display = 'block';
        } else {
            btn.style.display = 'none';
        }
    });
}

function renderPinned(pinned) {
    if (!pinned) return;
    document.getElementById('pinned-area').innerHTML = `
        <div class="pinned-comment">
            <div class="pinned-label">📌 {{ labels.comments_pinned }} – ${pinned.user}</div>
            <div class="pinned-text">${pinned.text}</div>
        </div>`;
}

/* Automatyczne ładowanie przypiętej wiadomości przy wejściu na stronę */
fetch(`/api/comments?url=${encodeURIComponent(GAME_URL)}`)
.then(r => r.json())
.then(data => renderPinned(data.pinned))
.catch(() => {});

/* Auto-sprawdzanie statusu pobierania */
pollStatus();
dlInterval = setInterval(pollStatus, 1500);
{% endif %}
</script>
</body>
</html>
"""


# ===========================================================================
# ROUTING FLASK
# ===========================================================================

@app.route('/')
def index():
    lang = session.get('lang', 'pl')
    return render_template_string(HTML_TEMPLATE, lang=lang, labels=get_labels(lang), query=None, game=None)

@app.route('/api/featured_seeds')
def featured_seeds():
    selected = random.sample(POPULAR_GAMES, 2)
    all_links = []
    for s in selected:
        all_links.extend(get_fast_links(s))
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
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        img = soup.find("meta", property="og:image")["content"]
        return jsonify({"image": img})
    except Exception:
        # 10. Fallback na domyślny obrazek zamiast krytycznego błędu
        return jsonify({"image": "https://placehold.co/300x450/111111/FFFFFF/png?text=Brak+Okładki"})

@app.route('/set_lang/<lang>')
def set_lang(lang):
    if lang in ['pl', 'en']:
        session['lang'] = lang
    return redirect(request.referrer or url_for('index'))

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    lang = session.get('lang', 'pl')
    return render_template_string(HTML_TEMPLATE, query=query, lang=lang, labels=get_labels(lang), game=None)

@app.route('/details')
def details():
    url = request.args.get('url')
    lang = session.get('lang', 'pl')
    if not url:
        return "Brak URL", 400
    game_data = get_game_details(url, lang)
    if not game_data:
        return "Nie udało się załadować danych gry.", 500
    return render_template_string(HTML_TEMPLATE, game=game_data, lang=lang, labels=get_labels(lang), query=None)

if __name__ == "__main__":
    app.run(port=5000, debug=True)
