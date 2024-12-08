import sqlite3  # Mengelola database SQLite
import requests  # Mengirim permintaan HTTP untuk mengambil data dari web
from bs4 import BeautifulSoup  # Memparsing HTML dari situs web
from playwright.sync_api import sync_playwright  # Menangani halaman web dengan konten dinamis
from Sastrawi.StopWordRemover.StopWordRemoverFactory import StopWordRemoverFactory  # Menghapus kata-kata tidak relevan (stop words)
import urllib3  # Menangani peringatan SSL
import logging  # Mencatat log aktivitas

# Menonaktifkan peringatan SSL untuk permintaan HTTP yang tidak aman
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Konfigurasi logging untuk mencatat aktivitas program
logging.basicConfig(
    level=logging.INFO,  # Tingkat logging (INFO)
    format='%(asctime)s - %(levelname)s - %(message)s',  # Format log
    handlers=[
        logging.FileHandler("scraper.log"),  # Log disimpan ke file
        logging.StreamHandler()  # Log juga ditampilkan di konsol
    ]
)

# Inisialisasi Sastrawi untuk menghapus stop words
stopword_factory = StopWordRemoverFactory()
stopword_remover = stopword_factory.create_stop_word_remover()

# Fungsi untuk membuat atau menghubungkan ke database SQLite
def setup_database():
    conn = sqlite3.connect("scraped_data.db")  # Membuat/terhubung ke file database
    cursor = conn.cursor()
    # Membuat tabel untuk menyimpan data hasil scraping jika belum ada
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scraped_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,  # ID otomatis
            source TEXT NOT NULL,  # Sumber data
            title TEXT NOT NULL,  # Judul artikel
            link TEXT NOT NULL,  # Tautan artikel
            content TEXT  # Konten artikel
        )
    """)
    conn.commit()  # Menyimpan perubahan ke database
    return conn

# Fungsi untuk menyimpan data ke dalam database SQLite
def save_to_database(conn, source, title, link, content=None):
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO scraped_data (source, title, link, content)
            VALUES (?, ?, ?, ?)
        """, (source, title, link, content))  # Menyisipkan data
        conn.commit()  # Menyimpan perubahan
        logging.info(f"Saved to DB: Source = {source}, Title = {title}, Link = {link}")
    except sqlite3.Error as e:
        logging.error(f"Failed to save to DB: {e}")

# Fungsi untuk mengambil konten dari sebuah tautan
def scrape_content_from_link(link):
    try:
        logging.info(f"Fetching content from: {link}")
        response = requests.get(link, verify=False)  # Mengambil konten halaman
        response.raise_for_status()  # Memeriksa status permintaan
        soup = BeautifulSoup(response.text, 'html.parser')  # Memparsing HTML

        # Mengambil semua paragraf sebagai konten
        paragraphs = [p.get_text(strip=True) for p in soup.find_all('p')]
        content = ' '.join(paragraphs) if paragraphs else None

        if content:
            logging.info(f"Content fetched successfully from: {link}")
            # Membersihkan konten dari stop words
            cleaned_content = stopword_remover.remove(content)
            logging.info(f"Stop words removed from content for: {link}")
            return cleaned_content
        else:
            logging.warning(f"No content found for: {link}")
            return None
    except requests.RequestException as e:
        logging.error(f"Error fetching content from {link}: {e}")
        return None

# Fungsi untuk scraping dari Autopedia
def scrape_titles_and_links_autopedia(url, conn):
    logging.info(f"Scraping Autopedia from: {url}")
    soup = fetch_url(url)  # Mengambil dan memparsing halaman web
    if not soup:
        return []

    titles_links = []  # List untuk menyimpan hasil scraping
    # Mengambil elemen dengan kelas tertentu untuk judul dan tautan
    titles = [title.get_text(strip=True) for title in soup.find_all('div', class_='title')]
    links = [a_tag['href'] for a_tag in soup.find_all('a', class_='btn btn-download fw-bold')]

    for title, link in zip(titles, links):
        if not link.startswith('http'):  # Menambahkan domain jika tautan relatif
            link = f"https://autopedia.id{link}"
        content = scrape_content_from_link(link)  # Mengambil konten dari tautan
        logging.info(f"Scraped Autopedia: Title = {title}, Link = {link}")
        titles_links.append({'source': 'Autopedia', 'title': title, 'link': link, 'content': content})
        save_to_database(conn, 'Autopedia', title, link, content)

    return titles_links

# Fungsi untuk scraping dari Carsome
def scrape_titles_and_links_carsome(url, conn):
    logging.info(f"Scraping Carsome from: {url}")
    titles_links = []
    while url:
        soup = fetch_url(url)  # Mengambil halaman web
        if not soup:
            break

        # Mengambil elemen dengan kelas tertentu untuk judul dan tautan
        for h3_tag in soup.find_all('h3', class_='elementor-post__title'):
            a_tag = h3_tag.find('a')
            if a_tag:
                title = a_tag.get_text(strip=True)
                link = a_tag['href'].strip()
                if not link.startswith('http'):
                    link = f"https://www.carsome.id{link}"
                content = scrape_content_from_link(link)
                logging.info(f"Scraped Carsome: Title = {title}, Link = {link}")
                titles_links.append({'source': 'Carsome', 'title': title, 'link': link, 'content': content})
                save_to_database(conn, 'Carsome', title, link, content)

        next_page = soup.find('a', class_='next')  # Paginasi untuk halaman berikutnya
        if next_page:
            url = next_page['href']
            if not url.startswith('http'):
                url = f"https://www.carsome.id{url}"
        else:
            url = None

    return titles_links

# Fungsi untuk scraping dari Oto
def scrape_titles_and_links_oto(url, conn):
    logging.info(f"Scraping Oto from: {url}")
    titles_links = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)  # Menjalankan browser tanpa antarmuka
        page = browser.new_page()
        page.goto(url)

        # Scroll otomatis untuk memuat lebih banyak konten
        max_scrolls = 10
        scroll_count = 0
        last_height = page.evaluate("document.body.scrollHeight")

        while scroll_count < max_scrolls:
            logging.info(f"Scrolling... (Scroll #{scroll_count + 1})")
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(5000)  # Menunggu konten dimuat
            new_height = page.evaluate("document.body.scrollHeight")

            if new_height == last_height:  # Jika tidak ada konten baru
                logging.info("Reached the end of the page. No more content to load.")
                break

            last_height = new_height
            scroll_count += 1

        content = page.content()  # Mendapatkan konten halaman
        browser.close()

    soup = BeautifulSoup(content, 'html.parser')
    articles = soup.find_all('a', class_='heading-h2 m-sm-b line-clamp line-clamp-2')

    if not articles:
        logging.warning("No articles found. Selector might need to be updated.")

    for a_tag in articles:
        title = a_tag.get('title', '').strip()
        link = a_tag.get('href', '').strip()
        if not link.startswith('http'):
            link = f"https://www.oto.com{link}"
        content = scrape_content_from_link(link)
        logging.info(f"Scraped Oto: Title = {title}, Link = {link}")
        titles_links.append({'source': 'Oto', 'title': title, 'link': link, 'content': content})
        save_to_database(conn, 'Oto', title, link, content)

    return titles_links

# Fungsi umum untuk mengambil URL dan memparsingnya
def fetch_url(url):
    try:
        response = requests.get(url, verify=False)  # Mengambil halaman dengan SSL dimatikan
        response.raise_for_status()
        return BeautifulSoup(response.text, 'html.parser')  # Parsing HTML
    except requests.RequestException as e:
        logging.error(f"Error fetching {url}: {e}")
        return None

# Fungsi utama untuk menjalankan semua scraping
def main():
    autopedia_url = 'https://autopedia.id/id/search?_token=4iaewApv2Alq3Q8GNbvP4zl8ULZ3ZEssoCV6N9fS&query=mobil#'
    carsome_url = 'https://www.carsome.id/news/'
    oto_url = 'https://www.oto.com/berita'

    conn = setup_database()  # Membuat koneksi database

    try:
        # Scraping setiap sumber
        scrape_titles_and_links_autopedia(autopedia_url, conn)
        scrape_titles_and_links_carsome(carsome_url, conn)
        scrape_titles_and_links_oto(oto_url, conn)

        logging.info("All scraping tasks completed.")
    except Exception as e:
        logging.error(f"Error during scraping: {e}")
    finally:
        conn.close()  # Menutup koneksi database
        logging.info("Database connection closed.")

if __name__ == "__main__":
    logging.info("Program started.")
    main()
    logging.info("Program finished.")
