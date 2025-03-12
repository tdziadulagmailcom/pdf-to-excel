import os
import pandas as pd
import pdfplumber
from flask import Flask, render_template, request, send_file, flash, redirect, url_for

app = Flask(__name__)
app.secret_key = "tajny_klucz_do_flashow"  # Klucz do obsługi flash messages
UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "outputs"

# Tworzymy foldery, jeśli ich nie ma
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def extract_tables_from_pdf(pdf_path):
    """Ekstrakcja tabel z PDF i zapis do Excela z lepszą obsługą błędów i detekcją tabel"""
    expected_columns = ["Data dokumentu", "Wn", "Ma"]
    alternative_columns = ["Data", "Debet", "Kredyt"]  # Alternatywne nazwy kolumn
    tables = []
    log_messages = []

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
                        
                        # Debugowanie pierwotnej tabeli
                        log_messages.append(f"Strona {page_num}, Tabela {table_num}: Znaleziono tabelę z kolumnami: {df.iloc[0].tolist()}")
                        
                        # Próba identyfikacji wiersza nagłówków
                        header_row = -1
                        for i, row in enumerate(df.iloc[:3].values):  # Sprawdzamy tylko pierwsze 3 wiersze
                            row_str = [str(cell).lower() if cell is not None else "" for cell in row]
                            if any("data" in cell for cell in row_str):
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
                            
                            # Sprawdzanie wymaganych kolumn z elastycznością
                            # Sprawdzamy oryginalne i alternatywne nazwy kolumn
                            if all(any(expected_col in str(col) for col in df.columns) for expected_col in ["Data", "Wn", "Ma"]) or \
                               all(any(alt_col in str(col) for col in df.columns) for alt_col in ["Data", "Debet", "Kredyt"]):
                                
                                # Mapowanie kolumn
                                column_mapping = {}
                                for col in df.columns:
                                    col_lower = str(col).lower()
                                    if "data" in col_lower:
                                        column_mapping[col] = "Data dokumentu"
                                    elif any(debit in col_lower for debit in ["wn", "debet"]):
                                        column_mapping[col] = "Wn"
                                    elif any(credit in col_lower for credit in ["ma", "kredyt"]):
                                        column_mapping[col] = "Ma"
                                
                                # Wybieramy tylko kolumny, które udało się zmapować
                                if len(column_mapping) >= 3:
                                    df = df.rename(columns=column_mapping)
                                    selected_cols = ["Data dokumentu", "Wn", "Ma"]
                                    # Sprawdzamy, czy wszystkie potrzebne kolumny są dostępne
                                    missing_cols = [col for col in selected_cols if col not in df.columns]
                                    for col in missing_cols:
                                        df[col] = None  # Dodajemy brakujące kolumny jako puste
                                    
                                    df = df[selected_cols]
                                    tables.append(df)
                                    log_messages.append(f"Strona {page_num}, Tabela {table_num}: Dodano tabelę z {len(df)} wierszami")
                                else:
                                    log_messages.append(f"Strona {page_num}, Tabela {table_num}: Nie udało się zmapować wymaganych kolumn")
                            else:
                                log_messages.append(f"Strona {page_num}, Tabela {table_num}: Brak wymaganych kolumn")
                        else:
                            log_messages.append(f"Strona {page_num}, Tabela {table_num}: Nie znaleziono nagłówków")
                            
                except Exception as e:
                    log_messages.append(f"Błąd przetwarzania strony {page_num}: {str(e)}")
    
        if tables:
            # Łączymy wszystkie znalezione tabele
            result_df = pd.concat(tables, ignore_index=True)
            
            # Czyszczenie danych
            # Usuwamy wiersze, które mogą być nieprawidłowe (np. sumy, podtytuly)
            result_df = result_df[result_df["Data dokumentu"].notna()]
            result_df = result_df[result_df["Data dokumentu"].astype(str).str.contains(r'\d')]
            
            # Zapisujemy także log
            log_path = os.path.join(OUTPUT_FOLDER, "log_konwersji.txt")
            with open(log_path, "w", encoding="utf-8") as log_file:
                log_file.write("\n".join(log_messages))
            
            # Zapisujemy wynik
            output_path = os.path.join(OUTPUT_FOLDER, "raport_kasowy.xlsx")
            result_df.to_excel(output_path, index=False)
            return output_path, log_path, "\n".join(log_messages)
        
        return None, None, "\n".join(log_messages)
    
    except Exception as e:
        error_message = f"Wystąpił błąd podczas przetwarzania pliku: {str(e)}"
        return None, None, error_message

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        flash("Nie wybrano pliku")
        return redirect(url_for("index"))
        
    file = request.files["file"]
    
    if file.filename == "":
        flash("Nie wybrano pliku")
        return redirect(url_for("index"))
        
    if file and file.filename.lower().endswith(".pdf"):
        file_path = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(file_path)

        excel_path, log_path, log_messages = extract_tables_from_pdf(file_path)
        
        if excel_path:
            # Opcjonalnie można też udostępnić log
            return send_file(excel_path, as_attachment=True)
        else:
            return render_template("index.html", error=True, error_message="Nie znaleziono odpowiednich tabel w pliku PDF. Szczegóły błędu:\n" + log_messages)
    else:
        return render_template("index.html", error=True, error_message="Wybierz prawidłowy plik PDF")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)