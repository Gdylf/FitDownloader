# FitDownloader - Web-Based Repack Manager

FitDownloader is a Python Flask web application designed as a Proof of Concept (PoC) for web scraping, asynchronous file downloading, and local torrent management. It provides a web interface to search for specific game repacks, view translated details, and download them automatically via HTTP or Torrent.

⚠️ **Disclaimer:** This project is created strictly for **educational purposes** to demonstrate web scraping, parsing HTML, interacting with APIs, and handling network streams in Python. The author does not condone piracy. Users are responsible for their own actions and ensuring they comply with local laws and copyrights.

## ✨ Features

* **Web Interface:** Built with Flask for easy interaction.
* **Automated Scraping:** Fetches game metadata (title, cover, genres, size, description) using `BeautifulSoup4`.
* **On-the-Fly Translation:** Translates game descriptions and metadata between English and Polish using the Google Translate API.
* **Smart Downloading System:**
    * **HTTP Mode:** Extracts and downloads multi-part direct links, with support for resuming paused/interrupted downloads.
    * **Torrent Mode:** Fallback mechanism using `libtorrent` to handle P2P downloads directly within the app.
* **Auto-Extraction:** Automatically extracts multi-part `.rar` archives upon successful download and cleans up residual files.
* **Threaded Task Manager:** Downloads run in background threads, keeping the UI responsive.

## 🛠️ Requirements

* Python 3.8+
* Internet connection (for scraping and downloading)

**Dependencies:**
* `Flask`
* `requests`
* `beautifulsoup4`
* `rarfile`
* `libtorrent` (may require specific installation depending on your OS)

## 🚀 Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/YourUsername/FitDownloader.git](https://github.com/YourUsername/FitDownloader.git)
   cd FitDownloader

