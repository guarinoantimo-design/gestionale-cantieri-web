import streamlit as st
import sqlite3
import pandas as pd
import datetime
import hashlib
import os

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Gestionale Cantieri", page_icon="🏗️", layout="wide")

DB_NAME = "gestionale_web.db"

# --- FUNZIONI DATABASE ---
def get_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()
    # Tabella Utenti per il Login
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT
        )
    """)
    # Tabella Preventivi (Cantieri)
    c.execute("""
        CREATE TABLE IF NOT EXISTS preventivi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT, n_prev TEXT, cliente TEXT, indirizzo TEXT, piva TEXT, 
            descrizione TEXT, importo_prev REAL, importo_contratto REAL,
            stato TEXT DEFAULT 'Attivo'
        )
    """)
    # Creiamo l'utente admin di default se non esiste
    c.execute("SELECT * FROM users WHERE username = 'admin'")
    if not c.fetchone():
        hashed_pw = hashlib.sha256("Cantieri2024!".encode()).hexdigest()
        c.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", ("admin", hashed_pw))
    
    conn.commit()
    conn.close()

# Inizializza il DB al primo avvio
init_db()

# --- FUNZIONI DI AUTENTICAZIONE ---
def verify_login(username, password):
    conn = get_connection()
    c = conn.cursor()
    hashed_pw = hashlib.sha256(password.encode()).hexdigest()
    c.execute("SELECT * FROM users WHERE username = ? AND password_hash = ?", (username, hashed_pw))
    user = c.fetchone()
    conn.close()
    return user is not None

# --- GESTIONE STATO SESSIONE ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'current_page' not in st.session_state:
    st.session_state.current_page = "Home"

# --- LOGIN PAGE ---
def login_page():
    st.markdown("<h1 style='text-align: center; color: #2C3E50;'>🏗️ Gestionale Cantieri</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #7F8C8D;'>Accedi per gestire i tuoi cantieri</p>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Accedi", use_container_width=True)
            
            if submit:
                if verify_login(username, password):
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.rerun()
                else:
                    st.error("Credenziali non valide. Riprova.")

# --- FUNZIONI CRUD CANTIERI ---
def get_cantieri():
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM preventivi", conn)
    conn.close()
    return df

def inserisci_cantiere(data, n_prev, cliente, indirizzo, piva, descrizione, importo_prev, importo_contratto):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO preventivi (data, n_prev, cliente, indirizzo, piva, descrizione, importo_prev, importo_contratto)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (data, n_prev, cliente, indirizzo, piva, descrizione, importo_prev, importo_contratto))
    conn.commit()
    conn.close()

def aggiorna_stato_cantiere(id_cantiere, nuovo_stato):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE preventivi SET stato = ? WHERE id = ?", (nuovo_stato, id_cantiere))
    conn.commit()
    conn.close()

def elimina_cantiere(id_cantiere):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM preventivi WHERE id = ?", (id_cantiere,))
    conn.commit()
    conn.close()

# --- PAGINE DELL'APP ---
def page_home():
    st.title("🏠 Home")
    st.write("Benvenuto nel Gestionale Cantieri. Seleziona una sezione dal menu laterale per iniziare.")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("📋 Gestione Cantieri", use_container_width=True):
            st.session_state.current_page = "Cantieri"
            st.rerun()
    with col2:
        st.button("📉 Inserimento Costi (In arrivo)", disabled=True, use_container_width=True)
    with col3:
        st.button("💰 Incassi (In arrivo)", disabled=True, use_container_width=True)

def page_cantieri():
    st.title("📋 Gestione Cantieri e Preventivi")
    
    # Form per nuovo cantiere (in un expander per non occupare spazio)
    with st.expander("➕ Aggiungi Nuovo Cantiere"):
        with st.form("nuovo_cantiere_form", clear_on_submit=True):
            col1, col2, col3 = st.columns(3)
            data = col1.date_input("Data", datetime.date.today())
            n_prev = col2.text_input("N. Preventivo")
            cliente = col3.text_input("Cliente")
            
            col4, col5, col6 = st.columns(3)
            indirizzo = col4.text_input("Indirizzo Cantiere")
            piva = col5.text_input("P.IVA / Cod. Fiscale")
            descrizione = col6.text_input("Descrizione Lavori")
            
            col7, col8 = st.columns(2)
            importo_prev = col7.number_input("Importo Preventivo (€)", min_value=0.0, step=100.0, format="%.2f")
            importo_contratto = col8.number_input("Importo Contratto (€)", min_value=0.0, step=100.0, format="%.2f")
            
            submit = st.form_submit_button("Salva Cantiere")
            if submit:
                if cliente and indirizzo:
                    inserisci_cantiere(str(data), n_prev, cliente, indirizzo, piva, descrizione, importo_prev, importo_contratto)
                    st.success("Cantiere inserito con successo!")
                    st.rerun()
                else:
                    st.error("Cliente e Indirizzo sono obbligatori.")

    st.divider()
    
    # Visualizzazione tabella
    df = get_cantieri()
    if df.empty:
        st.info("Nessun cantiere presente. Aggiungine uno per iniziare.")
    else:
        # Formattazione per la visualizzazione
        df['importo_contratto'] = df['importo_contratto'].apply(lambda x: f"€ {x:,.2f}" if pd.notnull(x) else "€ 0.00")
        df['importo_prev'] = df['importo_prev'].apply(lambda x: f"€ {x:,.2f}" if pd.notnull(x) else "€ 0.00")
        
        # Mostriamo la tabella con Streamlit Dataframe
        st.dataframe(df[['id', 'data', 'cliente', 'indirizzo', 'importo_contratto', 'stato']], use_container_width=True)

        st.subheader("Azioni sui Cantieri")
        
        # Seleziona cantiere per azioni
        cantiere_selezionato = st.selectbox("Seleziona un cantiere per gestirlo:", df['id'].tolist(), format_func=lambda x: f"Cantiere {x} - {df[df['id']==x]['indirizzo'].values[0]}")
        
        col_az1, col_az2 = st.columns(2)
        if col_az1.button("Chiudi Cantiere", type="primary"):
            aggiorna_stato_cantiere(cantiere_selezionato, "Chiuso")
            st.success("Cantiere chiuso.")
            st.rerun()
        if col_az2.button("Riapri Cantiere"):
            aggiorna_stato_cantiere(cantiere_selezionato, "Attivo")
            st.success("Cantiere riaperto.")
            st.rerun()

# --- LOGICA DI NAVIGAZIONE ---
if not st.session_state.logged_in:
    login_page()
else:
    # Sidebar Menu
    with st.sidebar:
        st.markdown(f"### 👤 Utente: {st.session_state.username}")
        st.divider()
        
        # Bottone Home
        if st.button("🏠 Home", use_container_width=True):
            st.session_state.current_page = "Home"
            st.rerun()
            
        # Bottone Cantieri
        if st.button("📋 Cantieri", use_container_width=True):
            st.session_state.current_page = "Cantieri"
            st.rerun()
            
        st.divider()
        st.button("📉 Costi (In arrivo)", disabled=True, use_container_width=True)
        st.button("💰 Incassi (In arrivo)", disabled=True, use_container_width=True)
        
        st.divider()
        if st.button("🚪 Logout", type="primary", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.username = ""
            st.session_state.current_page = "Home"
            st.rerun()

    # Rendering della pagina selezionata
    if st.session_state.current_page == "Home":
        page_home()
    elif st.session_state.current_page == "Cantieri":
        page_cantieri()