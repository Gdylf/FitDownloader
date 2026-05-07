# FitDownloader - Web-Based Repack Manager
FitDownloader is a Python Flask web application designed as a Proof of Concept (PoC) for web scraping, asynchronous file downloading, and local torrent management. It provides a web interface to search for specific game repacks, view translated details, and download them automatically via HTTP or Torrent.
⚠️ **Disclaimer:** This project is created strictly for **educational purposes** to demonstrate web scraping, parsing HTML, interacting with APIs, and handling network streams in Python. The author does not condone piracy. Users are responsible for their own actions and ensuring they comply with local laws and copyrights.
## ✨ Features
 * **Web Interface:** Built with Flask for easy interaction.
 * **Automated Scraping:** Fetches game metadata (title, cover, genres, size, description) using BeautifulSoup4.
 * **On-the-Fly Translation:** Translates game descriptions and metadata between English and Polish using the Google Translate API.
 * **Smart Downloading System:**
   * **HTTP Mode:** Extracts and downloads multi-part direct links, with support for resuming paused/interrupted downloads.
   * **Torrent Mode:** Fallback mechanism using libtorrent to handle P2P downloads directly within the app.
 * **Auto-Extraction:** Automatically extracts multi-part .rar archives upon successful download and cleans up residual files.
 * **Threaded Task Manager:** Downloads run in background threads, keeping the UI responsive.
## 🚀 Installation & Usage
There are two ways to run FitDownloader: using the pre-built executable (easiest for Windows users) or running it from the source code.
### Option 1: Quick Start (Windows .exe)
We use GitHub Actions to automatically build executable files. You don't need to install Python or any dependencies!
 1. Go to the Releases page of this repository.
 2. Download the latest .exe file.
 3. Run the application (a terminal window will open and start the local server).
 4. Access the web interface at http://127.0.0.1:5000 in your browser.
### Option 2: Run from Source (For Developers)
**Requirements:**
 * Python 3.8+
 * Internet connection
 1. **Clone the repository:**
   ```bash
   git clone https://github.com/YourUsername/FitDownloader.git
   cd FitDownloader
   
   ```
 2. **Install dependencies:**
   It is recommended to use a virtual environment.
   ```bash
   pip install -r requirements.txt
   
   ```
   *(Note: For rarfile to work, you may need to have WinRAR or unrar installed on your system PATH).*

  
 3. **Run the server:**
   ```bash
   python app.py
   
   ```
 4. **Access the application:**
   Open your browser and navigate to http://127.0.0.1:5000.
## 📂 Directory Structure
Downloaded files and extracted contents are automatically saved to the FitDownloads directory in the root folder.
 * FitDownloads/<Game_Name>/ - Contains the downloaded .rar parts or .torrent file.
 * FitDownloads/<Game_Name>/Game_Files/ - Contains the final, extracted setup files and game cover.
## 📄 License
This project is open-sourced under the MIT License. See the LICENSE file for details.
