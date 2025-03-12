from flask import Flask, render_template, request, send_file
import os
import pandas as pd
import pdfplumber

app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "outputs"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def extract_tables(pdf_path):
    selected_columns = ["Data dokumentu", "Wn", "Ma"]
    all_data = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                df = pd.DataFrame(table)
                if not df.empty and selected_columns[0] in df.iloc[0].values:
                    df.columns = df.iloc[0]
                    df = df[1:]
                    df = df[selected_columns]
                    all_data.append(df)

    if all_data:
        result_df = pd.concat(all_data, ignore_index=True)
        output_path = os.path.join(OUTPUT_FOLDER, "converted.xlsx")
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

        excel_path = extract_tables(file_path)
        if excel_path:
            return send_file(excel_path, as_attachment=True)
        else:
            return "Nie znaleziono tabeli z wymaganymi kolumnami.", 400

if __name__ == "__main__":
    app.run(debug=True)
