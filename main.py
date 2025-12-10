from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import pdfplumber
import pandas as pd
import re
import io
import uvicorn

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# GLOBAL VARIABLES
GLOBAL_HEADERS_FULL = ["No.", "NIM", "Nama", "Tempat Lahir", "Tanggal Lahir", "Angkatan", "Kampus", "Jurusan", "Program Pend.", "Sistem Kuliah", "Jml. Sem", "Jml. Cuti", "Jml. Sem + Cuti", "Stat. Kuliah", "Lulusan", "Tgl. Yudisium", "No. Seri Ijazah", "Pin Ijazah", "No. SK Rektor", "Stat. TA", "Sisa SKS"]
GLOBAL_HEADERS_OLD = ["No.", "NIM", "Nama", "Tempat Lahir", "Tanggal Lahir", "Angkatan", "Kampus", "Jurusan", "Program Pend.", "Sistem Kuliah", "Jml. Sem", "Jml. Cuti", "Jml. Sem + Cuti", "Stat. Kuliah", "Lulusan", "Tgl. Yudisium", "No. Seri Ijazah", "Pin Ijazah", "No. SK Rektor"]
GLOBAL_HEADERS_SHORT = ["No.", "NIM", "Nama", "Angkatan", "Kampus", "Jurusan", "Sistem Kuliah", "Jml. Sem", "Jml. Cuti", "Jml. Sem + Cuti", "Stat. Kuliah", "Stat. Lulusan", "Stat. TA", "Sisa SKS"]

# HELPER FUNCTIONS
def normalize(text): return re.sub(r'\s+', '', str(text).lower())
def clean_text_content(text): return re.sub(r'\s+', ' ', re.sub(r'[\n\r]+', ' ', re.sub(r'-\s*[\n\r]+\s*', '', str(text) if text else ""))).strip()
def clean_serial_code(text): return re.sub(r'\s+', '', str(text).strip()) if text else ""
def gabung_teks(series): return ' '.join([str(s) for s in series if pd.notna(s) and str(s).strip() != ''])
def perbaiki_format_tanggal(text):
    clean = re.sub(r'\D', '', str(text))
    return f"{clean[:4]}-{clean[4:6]}-{clean[6:]}" if len(clean) == 8 else text

def proses_pdf_logic(file_bytes):
    rows_full, rows_old, rows_short = [], [], []
    
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                if not tables: continue
                for table in tables:
                    for row in table:
                        clean_row = [str(c).strip() if c else "" for c in row]
                        norm = [normalize(c) for c in clean_row]
                        if "nim" in norm and "nama" in norm: continue

                        cols_count = len(clean_row)
                        if cols_count == len(GLOBAL_HEADERS_FULL): rows_full.append(clean_row)
                        elif cols_count == len(GLOBAL_HEADERS_OLD): rows_old.append(clean_row)
                        elif cols_count == len(GLOBAL_HEADERS_SHORT): rows_short.append(clean_row)
    except Exception as e:
        print(f"Error PDF: {e}")
        return None

    # Format
    active_df = None
    if len(rows_full) > len(rows_old) and len(rows_full) > len(rows_short):
        active_df = pd.DataFrame(rows_full, columns=GLOBAL_HEADERS_FULL)
    elif len(rows_old) > len(rows_short):
        active_df = pd.DataFrame(rows_old, columns=GLOBAL_HEADERS_OLD)
    elif len(rows_short) > 0:
        active_df = pd.DataFrame(rows_short, columns=GLOBAL_HEADERS_SHORT)
    else:
        return None

    # Cleaning
    df = active_df.replace(r'^\s*$', pd.NA, regex=True)
    if 'No.' in df.columns: df['No.'] = df['No.'].ffill()
    if 'NIM' in df.columns: df['NIM'] = df['NIM'].ffill()
    df = df.dropna(subset=['NIM'])
    
    cols_lain = [c for c in df.columns if c not in ['No.', 'NIM']]
    df = df.groupby(['No.', 'NIM'], as_index=False).agg({c: gabung_teks for c in cols_lain})

    for c in df.columns:
        if c in ['No. Seri Ijazah', 'Pin Ijazah', 'No. SK Rektor', 'NIM']: df[c] = df[c].apply(clean_serial_code)
        elif c in ['Tanggal Lahir', 'Tgl. Yudisium']: df[c] = df[c].apply(perbaiki_format_tanggal)
        elif c == 'Angkatan': df[c] = df[c].apply(lambda x: clean_serial_code(x)[:4])
        else: df[c] = df[c].apply(clean_text_content)

    # Sorting
    if 'No.' in df.columns:
        try:
            df['__sort'] = pd.to_numeric(df['No.'], errors='coerce')
            df = df.sort_values(by='__sort').drop(columns=['__sort'])
        except: pass

    # Return as JSON-friendly list of dicts
    return df.where(pd.notnull(df), None).to_dict(orient='records')

@app.post("/process-pdf")
async def api_process_pdf(file: UploadFile = File(...)):
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="File harus PDF")
    
    content = await file.read()
    data = proses_pdf_logic(content)
    
    if data is None:
        return {"status": "error", "message": "Gagal membaca data dari PDF"}
    
    return {"status": "success", "data": data}

# Entry point lokal
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)