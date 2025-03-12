from flask import Flask, render_template, request, send_file
import os
import pandas as pd
import pdfplumber

app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "outputs"

# Tworzymy foldery, jeśli ich nie ma
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def extract_tables_from_pdf(pdf_path):
    """Funkcja ekstrakcji tabel z PDF i zapisania ich do Excela"""
    selected_columns = ["Data dokumentu", "Wn", "Ma"]
    tables = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            extracted_tables = page.extract_tables()
            for table in extracted_tables:
                df = pd.DataFrame(table)
                # Sprawdzamy, czy tabela zawiera wymagane kolumny
                if not df.empty and any("Data" in str(cell) for cell in df.iloc[0]):
                    df.columns = df.iloc[0]  # Pierwszy wiersz jako nagłówki
                    df = df[1:]  # Usunięcie nagłówka z danych
                    df = df[selected_columns]  # Wybór odpowiednich kolumn
                    tables.append(df)

    if tables:
        result_df = pd.concat(tables, ignore_index=True)
        output_path = os.path.join(OUTPUT_FOLDER, "raport_kasowy.xlsx")
        result_df.to_excel(output_path, index=False)
        return output_path
    return None

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload_file():
    file = request.files["file"]
    if file:
        file_path = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(file_path)

        excel_path = extract_tables_from_pdf(file_path)
        if excel_path:
            return send_file(excel_path, as_attachment=True)
        else:
            return "Nie znaleziono odpowiednich tabel w pliku PDF.", 400

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
