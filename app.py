from flask import Flask, render_template, request, redirect, url_for
from indexed_summaries import connect_database, load_data_from_db, create_search_index, search

app = Flask(__name__)

# Load data and create search index at application startup
conn = connect_database()
titles, links, paragraphs = load_data_from_db(conn)
vectorizer, X = create_search_index(titles)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/loading')
def loading():
    query = request.args.get('query', '').strip()
    if query:
        return render_template('loading.html', query=query)
    return redirect(url_for('index'))

@app.route('/results')
def results():
    query = request.args.get('query', '').strip()
    if query:
        search_results = search(query, vectorizer, X, titles, links, paragraphs, conn)
        return render_template('result.html', query=query, results=search_results)
    return render_template('error.html')

@app.route('/search', methods=['POST'])
def search_route():
    query = request.form.get('query', '').strip()
    if query:
        return redirect(url_for('loading', query=query))
    return redirect(url_for('index'))

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/help')
def help():
    return render_template('help.html')

if __name__ == '__main__':
    try:
        app.run(debug=True, port=5002)
    finally:
        conn.close()  # Ensure the database connection is closed
