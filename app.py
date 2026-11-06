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
    c.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password_hash TEXT)")
    c.execute("""
        CREATE TABLE IF NOT EXISTS preventivi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT, n_prev TEXT, cliente TEXT, indirizzo TEXT, piva TEXT, 
            descrizione TEXT, importo_prev REAL, importo_contratto REAL,
            stato TEXT DEFAULT 'Attivo'
        )
    """)
    c.execute("CREATE TABLE IF NOT EXISTS operai (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, ruolo TEXT, costo_orario REAL)")
    c.execute("CREATE TABLE IF NOT EXISTS fornitori (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, piva TEXT, contatto TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS costo_manodopera (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, cantiere_id INTEGER, operaio TEXT, ore REAL, costo_orario REAL, totale REAL)")
    c.execute("CREATE TABLE IF NOT EXISTS costo_materiali (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, cantiere_id INTEGER, fornitore TEXT, documento TEXT, imponibile REAL, iva REAL, totale REAL)")
    
    c.execute("SELECT * FROM users WHERE username = 'admin'")
    if not c.fetchone():
        hashed_pw = hashlib.sha256("Cantieri2024!".encode()).hexdigest()
        c.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", ("admin", hashed_pw))
    
    conn.commit()
    conn.close()

init_db()

# --- AUTENTICAZIONE ---
def verify_login(username, password):
    conn = get_connection()
    c = conn.cursor()
    hashed_pw = hashlib.sha256(password.encode()).hexdigest()
    c.execute("SELECT * FROM users WHERE username = ? AND password_hash = ?", (username, hashed_pw))
    user = c.fetchone()
    conn.close()
    return user is not None

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'current_page' not in st.session_state:
    st.session_state.current_page = "Home"

def login_page():
    st.markdown("<h1 style='text-align: center; color: #2C3E50;'>🏗️ Gestionale Cantieri</h1>", unsafe_allow_html=True)
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
                    st.error("Credenziali non valide.")

# --- FUNZIONI DI SUPPORTO ---
def get_cantieri():
    conn = get_connection()
    df = pd.read_sql_query("SELECT id, indirizzo FROM preventivi", conn)
    conn.close()
    return df

def get_operai():
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM operai", conn)
    conn.close()
    return df

def get_fornitori():
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM fornitori", conn)
    conn.close()
    return df

# --- PAGINE ---
def page_home():
    st.title("🏠 Home")
    st.write("Benvenuto nel Gestionale. Seleziona una sezione dal menu laterale.")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📋 Gestione Cantieri", use_container_width=True):
            st.session_state.current_page = "Cantieri"; st.rerun()
        if st.button("📉 Inserimento Costi", use_container_width=True):
            st.session_state.current_page = "Costi"; st.rerun()
    with col2:
        if st.button("👥 Anagrafiche", use_container_width=True):
            st.session_state.current_page = "Anagrafiche"; st.rerun()
        st.button("💰 Incassi (In arrivo)", disabled=True, use_container_width=True)

def page_cantieri():
    st.title("📋 Gestione Cantieri")
    
    with st.expander("➕ Aggiungi Nuovo Cantiere"):
        with st.form("nuovo_cantiere_form", clear_on_submit=True):
            col1, col2, col3 = st.columns(3)
            data = col1.date_input("Data", datetime.date.today())
            n_prev = col2.text_input("N. Preventivo")
            cliente = col3.text_input("Cliente")
            col4, col5, col6 = st.columns(3)
            indirizzo = col4.text_input("Indirizzo Cantiere")
            piva = col5.text_input("P.IVA")
            descrizione = col6.text_input("Descrizione")
            col7, col8 = st.columns(2)
            importo_prev = col7.number_input("Importo Prev. (€)", min_value=0.0, step=100.0)
            importo_contratto = col8.number_input("Importo Contratto (€)", min_value=0.0, step=100.0)
            
            if st.form_submit_button("Salva Cantiere"):
                if cliente and indirizzo:
                    conn = get_connection(); c = conn.cursor()
                    c.execute("INSERT INTO preventivi (data, n_prev, cliente, indirizzo, piva, descrizione, importo_prev, importo_contratto) VALUES (?,?,?,?,?,?,?,?)", 
                              (str(data), n_prev, cliente, indirizzo, piva, descrizione, importo_prev, importo_contratto))
                    conn.commit(); conn.close()
                    st.success("Cantiere inserito!"); st.rerun()
                else:
                    st.error("Cliente e Indirizzo sono obbligatori.")

    st.divider()
    conn = get_connection()
    df = pd.read_sql_query("SELECT id, data, cliente, indirizzo, importo_contratto, stato FROM preventivi", conn)
    conn.close()
    
    if not df.empty:
        st.dataframe(df, use_container_width=True)
        st.subheader("Azioni")
        cantiere_sel = st.selectbox("Seleziona Cantiere:", df['id'].tolist(), format_func=lambda x: f"ID {x} - {df[df['id']==x]['indirizzo'].values[0]}")
        col1, col2 = st.columns(2)
        if col1.button("Chiudi Cantiere", type="primary"):
            conn = get_connection(); c = conn.cursor()
            c.execute("UPDATE preventivi SET stato='Chiuso' WHERE id=?", (cantiere_sel,))
            conn.commit(); conn.close(); st.rerun()
        if col2.button("Riapri Cantiere"):
            conn = get_connection(); c = conn.cursor()
            c.execute("UPDATE preventivi SET stato='Attivo' WHERE id=?", (cantiere_sel,))
            conn.commit(); conn.close(); st.rerun()
    else:
        st.info("Nessun cantiere presente.")

def page_anagrafiche():
    st.title("👥 Anagrafiche Operai e Fornitori")
    tab1, tab2 = st.tabs(["Operai", "Fornitori"])
    
    with tab1:
        with st.expander("➕ Nuovo Operaio"):
            with st.form("nuovo_operaio", clear_on_submit=True):
                nome = st.text_input("Nome Operaio")
                ruolo = st.text_input("Ruolo")
                costo = st.number_input("Costo Orario (€)", min_value=0.0, step=1.0)
                if st.form_submit_button("Salva Operaio"):
                    if nome:
                        conn = get_connection(); c = conn.cursor()
                        c.execute("INSERT INTO operai (nome, ruolo, costo_orario) VALUES (?,?,?)", (nome, ruolo, costo))
                        conn.commit(); conn.close(); st.success("Operaio aggiunto!"); st.rerun()
        conn = get_connection()
        df_op = pd.read_sql_query("SELECT * FROM operai", conn)
        conn.close()
        st.dataframe(df_op, use_container_width=True)

    with tab2:
        with st.expander("➕ Nuovo Fornitore"):
            with st.form("nuovo_fornitore", clear_on_submit=True):
                nome_f = st.text_input("Nome Fornitore")
                piva_f = st.text_input("P.IVA")
                contatto = st.text_input("Contatto")
                if st.form_submit_button("Salva Fornitore"):
                    if nome_f:
                        conn = get_connection(); c = conn.cursor()
                        c.execute("INSERT INTO fornitori (nome, piva, contatto) VALUES (?,?,?)", (nome_f, piva_f, contatto))
                        conn.commit(); conn.close(); st.success("Fornitore aggiunto!"); st.rerun()
        conn = get_connection()
        df_forn = pd.read_sql_query("SELECT * FROM fornitori", conn)
        conn.close()
        st.dataframe(df_forn, use_container_width=True)

def page_costi():
    st.title("📉 Inserimento Costi")
    
    cantieri = get_cantieri()
    operai = get_operai()
    fornitori = get_fornitori()
    
    if cantieri.empty:
        st.warning("Devi prima creare un cantiere!")
        return

    tab1, tab2 = st.tabs(["Costo Manodopera", "Costo Materiale"])
    
    with tab1:
        # Usciamo dal form per permettere l'aggiornamento dinamico del costo orario
        st.subheader("Registra Ore Lavorate")
        col1, col2 = st.columns(2)
        data_m = col1.date_input("Data", datetime.date.today())
        cantiere_m = col2.selectbox("Cantiere", cantieri['id'].tolist(), format_func=lambda x: cantieri[cantieri['id']==x]['indirizzo'].values[0])
        
        if not operai.empty:
            col3, col4 = st.columns(2)
            operaio_sel = col3.selectbox("Operaio", operai['nome'].tolist())
            
            # Logica di auto-compilazione: cerchiamo il costo orario dell'operaio selezionato
            costo_standard = operai[operai['nome'] == operaio_sel]['costo_orario'].values[0]
            
            costo_orario = col4.number_input("Costo Orario (€)", min_value=0.0, step=1.0, value=float(costo_standard))
            ore = st.number_input("Ore Lavorate", min_value=0.0, step=0.5)
            
            if st.button("Salva Costo Manodopera", type="primary"):
                totale = ore * costo_orario
                conn = get_connection(); c = conn.cursor()
                c.execute("INSERT INTO costo_manodopera (data, cantiere_id, operaio, ore, costo_orario, totale) VALUES (?,?,?,?,?,?)", 
                          (str(data_m), cantiere_m, operaio_sel, ore, costo_orario, totale))
                conn.commit(); conn.close(); st.success("Costo manodopera registrato!"); st.rerun()
        else:
            st.info("Nessun operaio in anagrafica. Aggiungine uno nella sezione Anagrafiche.")

    with tab2:
        with st.form("form_materiali", clear_on_submit=True):
            st.subheader("Registra Acquisto Materiale")
            col1, col2 = st.columns(2)
            data_mat = col1.date_input("Data", datetime.date.today())
            cantiere_mat = col2.selectbox("Cantiere", cantieri['id'].tolist(), format_func=lambda x: cantieri[cantieri['id']==x]['indirizzo'].values[0])
            
            if not fornitori.empty:
                col3, col4 = st.columns(2)
                fornitore_sel = col3.selectbox("Fornitore", fornitori['nome'].tolist())
                documento = col4.text_input("N. Documento / Fattura")
                
                col5, col6 = st.columns(2)
                imponibile = col5.number_input("Imponibile (€)", min_value=0.0, step=10.0)
                iva = col6.number_input("Aliquota IVA (%)", min_value=0.0, value=22.0, step=1.0)
                
                if st.form_submit_button("Salva Costo Materiale"):
                    totale = imponibile + (imponibile * iva / 100)
                    conn = get_connection(); c = conn.cursor()
                    c.execute("INSERT INTO costo_materiali (data, cantiere_id, fornitore, documento, imponibile, iva, totale) VALUES (?,?,?,?,?,?,?)", 
                              (str(data_mat), cantiere_mat, fornitore_sel, documento, imponibile, iva, totale))
                    conn.commit(); conn.close(); st.success("Costo materiale registrato!"); st.rerun()
            else:
                st.info("Nessun fornitore in anagrafica. Aggiungine uno nella sezione Anagrafiche.")

    st.divider()
    st.subheader("Elenco Costi Registrati")
    
    conn = get_connection()
    query = """
        SELECT 'Manodopera' as Tipo, data, (SELECT indirizzo FROM preventivi WHERE id = cantiere_id) as Cantiere, operaio as Descrizione, totale as Totale
        FROM costo_manodopera
        UNION ALL
        SELECT 'Materiale' as Tipo, data, (SELECT indirizzo FROM preventivi WHERE id = cantiere_id) as Cantiere, fornitore as Descrizione, totale as Totale
        FROM costo_materiali
        ORDER BY data DESC
    """
    df_costi = pd.read_sql_query(query, conn)
    conn.close()
    st.dataframe(df_costi, use_container_width=True)

# --- NAVIGAZIONE ---
if not st.session_state.logged_in:
    login_page()
else:
    with st.sidebar:
        st.markdown(f"### 👤 Utente: {st.session_state.username}")
        st.divider()
        if st.button("🏠 Home", use_container_width=True):
            st.session_state.current_page = "Home"; st.rerun()
        if st.button("📋 Cantieri", use_container_width=True):
            st.session_state.current_page = "Cantieri"; st.rerun()
        if st.button("👥 Anagrafiche", use_container_width=True):
            st.session_state.current_page = "Anagrafiche"; st.rerun()
        if st.button("📉 Costi", use_container_width=True):
            st.session_state.current_page = "Costi"; st.rerun()
        
        st.divider()
        if st.button("🚪 Logout", type="primary", use_container_width=True):
            st.session_state.logged_in = False; st.rerun()

    if st.session_state.current_page == "Home": page_home()
    elif st.session_state.current_page == "Cantieri": page_cantieri()
    elif st.session_state.current_page == "Anagrafiche": page_anagrafiche()
    elif st.session_state.current_page == "Costi": page_costi()
