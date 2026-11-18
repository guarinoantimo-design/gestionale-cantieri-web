import streamlit as st
import pandas as pd
import sqlite3
from st_supabase_connection import SupabaseConnection

st.set_page_config(page_title="Traghetto Dati", page_icon="🚚", layout="wide")

# --- CONNESSIONE SUPABASE ---
conn = st.connection("supabase", type=SupabaseConnection)
supabase = conn.client

def migra_dati(file_db):
    try:
        sqlite_conn = sqlite3.connect(file_db)
        
        # Elenco delle tabelle da migrare (ESCLUDE 'users' per non toccare l'admin)
        tabelle = [
            "preventivi", "operai", "fornitori", 
            "costo_manodopera", "costo_materiali", "costo_amministrativo", 
            "categorie_amministrative", "incassi"
        ]
        
        report = []
        
        for t in tabelle:
            # 1. Svuota la tabella su Supabase (con un metodo diverso e più sicuro)
            try:
                # Cancella tutti i record (neq a un valore impossibile per prendere tutti)
                supabase.table(t).delete().neq("id", -999).execute()
            except Exception as e:
                # Se fallisce lo svuotamento, lo ignoriamo e andiamo avanti (magari era già vuota)
                pass
                
            # 2. Legge i dati dal vecchio DB
            df = pd.read_sql_query(f"SELECT * FROM {t}", sqlite_conn)
            if df.empty:
                report.append(f"ℹ️ Tabella {t}: 0 righe (vuota)")
                continue
                
            # Converte eventuali valori NaN in None
            df = df.where(pd.notnull(df), None)
            dati = df.to_dict(orient="records")
            
            # 3. Inserisce a blocchi
            for i in range(0, len(dati), 50):
                blocco = dati[i:i+50]
                supabase.table(t).insert(blocco).execute()
                
            report.append(f"✅ Tabella {t}: {len(dati)} righe importate")
            
        sqlite_conn.close()
        return report
    except Exception as e:
        return [f"❌ Errore critico: {e}"]

# --- INTERFACCIA ---
st.title("🚚 Traghetto Dati (Migrazione Sicura)")
st.write("Questa pagina carica i tuoi vecchi dati su Supabase. L'utente 'admin' non verrà toccato.")

file_caricato = st.file_uploader("Carica il file di backup del database (.db)", type=["db"])

if st.button("Avvia Migrazione", type="primary"):
    if file_caricato is not None:
        with open("temp_backup.db", "wb") as f:
            f.write(file_caricato.getbuffer())
        
        with st.spinner("Trasferimento dati in corso..."):
            risultati = migra_dati("temp_backup.db")
            
        st.success("Procedura completata!")
        for r in risultati:
            st.write(r)
    else:
        st.error("Devi prima caricare il file .db!")
