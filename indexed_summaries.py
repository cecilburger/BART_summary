import sqlite3
import json
from transformers import BartTokenizer, BartForConditionalGeneration
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import os

# Load BART model and tokenizer
tokenizer = BartTokenizer.from_pretrained("facebook/bart-large-cnn")
model = BartForConditionalGeneration.from_pretrained("facebook/bart-large-cnn")

# Load fine-tuned BART model and tokenizer
#tokenizer = BartTokenizer.from_pretrained("fine_tuned_BART")
#model = BartForConditionalGeneration.from_pretrained("fine_tuned_BART")

# Cache for summaries
summary_cache = {}

# Fungsi untuk memuat cache dari file
def load_summary_cache(filename='summaries.txt'):
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

# Fungsi untuk menyimpan cache ke file
def save_summary_cache(cache, filename='summaries.txt'):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=4)

# Load cache at start
summary_cache = load_summary_cache()

# Fungsi untuk menyambungkan ke database SQLite
def connect_database(db_name="scraped_data.db"):
    return sqlite3.connect(db_name)

# Fungsi untuk mengambil data dari database
def load_data_from_db(conn):
    titles, links, paragraphs = [], [], []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT title, link, content FROM scraped_data")
        rows = cursor.fetchall()
        for row in rows:
            title, link, content = row
            if content:  # Pastikan konten tidak kosong
                titles.append(title)
                links.append(link)
                paragraphs.append(content)
    except sqlite3.Error as e:
        print(f"Error loading data from database: {e}")
    return titles, links, paragraphs

# Fungsi untuk menyimpan ringkasan ke database
def save_summary_to_db(conn, title, summary):
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE scraped_data
            SET content = ?
            WHERE title = ?
        """, (summary, title))
        conn.commit()
    except sqlite3.Error as e:
        print(f"Error saving summary to database: {e}")

# Fungsi untuk merangkum paragraf
def summarize_paragraph(paragraph):
    if paragraph in summary_cache:
        return summary_cache[paragraph]
    
    # Encode paragraph
    inputs = tokenizer(paragraph, max_length=1024, return_tensors="pt", truncation=True)
    
    # Generate summary
    summary_ids = model.generate(
        inputs["input_ids"], 
        max_length=300,
        min_length=80,
        length_penalty=1.0,
        num_beams=4,
        early_stopping=True
    )
    
    # Decode and cache the summary
    summary = tokenizer.decode(summary_ids[0], skip_special_tokens=True)
    summary_cache[paragraph] = summary
    
    # Save summary to file for future use
    save_summary_cache(summary_cache)
    
    return summary

# Fungsi untuk membuat indeks pencarian
def create_search_index(titles):
    vectorizer = TfidfVectorizer(stop_words='english', min_df=1, max_df=0.9)
    X = vectorizer.fit_transform(titles)
    return vectorizer, X

# Fungsi pencarian dengan indeks
def search(query, vectorizer, X, titles, links, paragraphs, conn):
    query_vec = vectorizer.transform([query])
    similarities = cosine_similarity(query_vec, X)

    top_results_idx = similarities[0].argsort()[-10:][::-1]

    results = []
    for idx in top_results_idx:
        if similarities[0][idx] > 0.45:
            summary = summarize_paragraph(paragraphs[idx])
            save_summary_to_db(conn, titles[idx], summary)  # Simpan ringkasan ke database
            results.append({
                'title': titles[idx],
                'link': links[idx],
                'summary': summary,
                'similarity': similarities[0][idx]
            })

    return results

# Fungsi utama
def main():
    conn = connect_database()  # Koneksi ke database
    try:
        # Muat data dari database
        titles, links, paragraphs = load_data_from_db(conn)
        
        # Buat indeks pencarian
        vectorizer, X = create_search_index(titles)
        
        # Query untuk pencarian
        query = input("Masukkan kata kunci pencarian: ")
        results = search(query, vectorizer, X, titles, links, paragraphs, conn)
        
        for result in results:
            print(f"Title: {result['title']}")
            print(f"Link: {result['link']}")
            print(f"Summary: {result['summary']}")
            print(f"Similarity: {result['similarity']}")
            print("-" * 80)
    finally:
        conn.close()  # Tutup koneksi database

if __name__ == "__main__":
    main()
