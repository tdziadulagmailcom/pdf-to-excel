import os
import pandas as pd
import pdfplumber
from flask import Flask, render_template, request, send_file, flash, redirect, url_for, session, jsonify

app = Flask(__name__)
app.secret_key = "tajny_klucz_do_flashow"
UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "outputs"
TEMP_FOLDER = "temp"

# Tworzymy foldery, jeśli ich nie ma
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(TEMP_FOLDER, exist_ok=True)

def extract_tables_from_pdf(pdf_path):
    """Ekstrakcja tabel z PDF i identyfikacja dostępnych kolumn"""
    tables = []
    log_messages = []
    all_columns = set()

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                try:
                    # Próba ekstrakcji tabel ze strony
                    extracted_tables = page.extract_tables()
                    
                    if not extracted_tables:
                        log_messages.append(f"Strona {page_num}: Nie znaleziono żadnych tabel")
                        continue
                        
                    for table_num, table in enumerate(extracted_tables, 1):
                        if not table or len(table) <= 1:  # Pusta tabela lub tylko nagłówki
                            log_messages.append(f"Strona {page_num}, Tabela {table_num}: Pusta tabela")
                            continue
                            
                        # Konwersja do DataFrame
                        df = pd.DataFrame(table)
                        
                        # Próba identyfikacji wiersza nagłówków
                        header_row = -1
                        for i, row in enumerate(df.iloc[:3].values):  # Sprawdzamy tylko pierwsze 3 wiersze
                            row_str = [str(cell).lower() if cell is not None else "" for cell in row]
                            if any(keyword in " ".join(row_str) for keyword in ["data", "kod", "kwota", "nazwa", "numer"]):
                                header_row = i
                                break
                        
                        if header_row >= 0:
                            # Ustawienie znalezionego wiersza jako nagłówki
                            headers = df.iloc[header_row]
                            df.columns = headers
                            df = df.iloc[header_row+1:].reset_index(drop=True)
                            
                            # Czyszczenie danych
                            df = df.dropna(axis=1, how="all").dropna(axis=0, how="all")
                            
                            # Normalizacja nazw kolumn (usuwanie białych znaków, etc.)
                            df.columns = [str(col).strip() if col is not None else f"Kolumna_{i}" 
                                         for i, col in enumerate(df.columns)]
                            
                            # Zapisujemy wszystkie znalezione kolumny
                            all_columns.update(df.columns)
                            
                            tables.append(df)
                            log_messages.append(f"Strona {page_num}, Tabela {table_num}: Znaleziono tabelę z kolumnami: {df.columns.tolist()}")
                        else:
                            log_messages.append(f"Strona {page_num}, Tabela {table_num}: Nie znaleziono nagłówków")
                            
                except Exception as e:
                    log_messages.append(f"Błąd przetwarzania strony {page_num}: {str(e)}")
    
        if tables:
            # Przekształcamy listę unikalnych kolumn w listę
            all_columns_list = sorted(list(all_columns))
            
            # Zapisujemy znalezione tabele do pliku tymczasowego
            temp_df = pd.concat(tables, ignore_index=True)
            temp_path = os.path.join(TEMP_FOLDER, "temp_data.pkl")
            temp_df.to_pickle(temp_path)
            
            # Zapisujemy także log
            log_path = os.path.join(TEMP_FOLDER, "log_konwersji.txt")
            with open(log_path, "w", encoding="utf-8") as log_file:
                log_file.write("\n".join(log_messages))
            
            return all_columns_list, temp_path, "\n".join(log_messages)
        
        return [], None, "\n".join(log_messages)
    
    except Exception as e:
        error_message = f"Wystąpił błąd podczas przetwarzania pliku: {str(e)}"
        return [], None, error_message

def generate_excel_from_selection(temp_path, selected_columns, filename):
    """Generuje plik Excel na podstawie wybranych kolumn"""
    try:
        # Wczytanie tymczasowego pliku
        df = pd.read_pickle(temp_path)
        
        # Filtrowanie tylko wybranych kolumn (jeśli istnieją w DataFrame)
        valid_columns = [col for col in selected_columns if col in df.columns]
        
        if not valid_columns:
            return None, "Nie wybrano żadnych prawidłowych kolumn"
        
        df_selected = df[valid_columns]
        
        # Usuwanie wierszy, które są całkowicie puste
        df_selected = df_selected.dropna(how='all')
        
        # Zapisanie do pliku Excel
        output_path = os.path.join(OUTPUT_FOLDER, filename)
        df_selected.to_excel(output_path, index=False)
        
        return output_path, None
    
    except Exception as e:
        return None, f"Wystąpił błąd podczas generowania pliku Excel: {str(e)}"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "Nie wybrano pliku"}), 400
        
    file = request.files["file"]
    
    if file.filename == "":
        return jsonify({"error": "Nie wybrano pliku"}), 400
        
    if file and file.filename.lower().endswith(".pdf"):
        file_path = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(file_path)

        available_columns, temp_path, log_messages = extract_tables_from_pdf(file_path)
        
        if available_columns and temp_path:
            # Zapisujemy informacje w sesji
            session['temp_path'] = temp_path
            session['filename'] = file.filename.replace('.pdf', '.xlsx')
            
            return jsonify({
                "success": True,
                "columns": available_columns,
                "message": f"Znaleziono {len(available_columns)} kolumn w pliku PDF"
            })
        else:
            return jsonify({
                "error": True,
                "message": "Nie znaleziono odpowiednich tabel w pliku PDF. Szczegóły błędu:\n" + log_messages
            }), 400
    else:
        return jsonify({
            "error": True,
            "message": "Wybierz prawidłowy plik PDF"
        }), 400

@app.route("/generate", methods=["POST"])
def generate_excel():
    # Sprawdzamy, czy mamy zapisane dane sesji
    if 'temp_path' not in session or 'filename' not in session:
        return jsonify({"error": "Sesja wygasła. Proszę przesłać plik ponownie."}), 400
    
    # Pobieramy wybrane kolumny
    data = request.get_json()
    if not data or 'columns' not in data or not data['columns']:
        return jsonify({"error": "Nie wybrano żadnych kolumn"}), 400
    
    selected_columns = data['columns']
    temp_path = session['temp_path']
    filename = session['filename']
    
    # Generujemy plik Excel
    excel_path, error = generate_excel_from_selection(temp_path, selected_columns, filename)
    
    if excel_path:
        # Zwracamy ścieżkę do pliku, który będzie dostępny do pobrania
        return jsonify({
            "success": True,
            "file": os.path.basename(excel_path),
            "message": "Plik Excel został wygenerowany pomyślnie"
        })
    else:
        return jsonify({
            "error": True,
            "message": error
        }), 400

@app.route("/download/<filename>")
def download_file(filename):
    return send_file(os.path.join(OUTPUT_FOLDER, filename), as_attachment=True)

@app.route("/view/<filename>")
def view_file(filename):
    # Ta funkcja tylko renderuje stronę z linkiem do pliku
    return render_template("view.html", filename=filename)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
