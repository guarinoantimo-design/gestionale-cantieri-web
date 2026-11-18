import streamlit as st
import pandas as pd
import sqlite3
import datetime
import hashlib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from st_supabase_connection import SupabaseConnection

st.set_page_config(page_title="Gestionale Cantieri", page_icon="🏗️", layout="wide")

# --- CONNESSIONE SUPABASE ---
conn = st.connection("supabase", type=SupabaseConnection)
supabase = conn.client

# --- FUNZIONE MIGRAZIONE DATI ---
def migra_dati(file_db):
    try:
        # Connessione al vecchio file SQLite
        sqlite_conn = sqlite3.connect(file_db)
        
        tabelle = [
            "users", "preventivi", "operai", "fornitori", 
            "costo_manodopera", "costo_materiali", "costo_amministrativo", 
            "categorie_amministrative", "incassi"
        ]
        
        # Svuota le tabelle su Supabase prima di importare (per evitare duplicati)
        for t in tabelle:
            try:
                supabase.table(t).delete().neq("id", 0).execute() # Cancella tutto tranne id 0 (workaround)
            except:
                pass
        
        report = []
        
        for t in tabelle:
            # Legge i dati dal vecchio DB
            df = pd.read_sql_query(f"SELECT * FROM {t}", sqlite_conn)
            if df.empty:
                report.append(f"Tabella {t}: 0 righe (vuota)")
                continue
                
            # Converte eventuali valori NaN in None (NULL per il database)
            df = df.where(pd.notnull(df), None)
            
            # Prepara i dati per l'inserimento
            dati = df.to_dict(orient="records")
            
            # Inserisce a blocchi per non sovraccaricare la richiesta
            for i in range(0, len(dati), 50):
                blocco = dati[i:i+50]
                supabase.table(t).insert(blocco).execute()
                
            report.append(f"Tabella {t}: {len(dati)} righe importate")
            
        sqlite_conn.close()
        return report
    except Exception as e:
        return [f"Errore durante la migrazione: {e}"]

# --- PAGINA TEMPORANEA DI MIGRAZIONE ---
st.title("🚚 Traghetto Dati (Migrazione)")
st.write("Questa pagina serve solo per caricare i tuoi vecchi dati nel nuovo database Supabase.")
st.warning("⚠️ Una volta completata la migrazione, dovrai sostituire questo codice con quello definitivo del gestionale.")

file_caricato = st.file_uploader("Carica il file di backup del database (.db)", type=["db"])

if st.button("Avvia Migrazione", type="primary"):
    if file_caricato is not None:
        # Salva temporaneamente il file
        with open("temp_backup.db", "wb") as f:
            f.write(file_caricato.getbuffer())
        
        with st.spinner("Trasferimento dati in corso..."):
            risultati = migra_dati("temp_backup.db")
            
        st.success("Migrazione completata!")
        for r in risultati:
            st.write(f"✅ {r}")
            
        st.info("Ora puoi chiedermi il codice definitivo del gestionale!")
    else:
        st.error("Devi prima caricare il file .db!")
