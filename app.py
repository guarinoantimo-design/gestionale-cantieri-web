import streamlit as st
import sqlite3
import pandas as pd
import datetime
import hashlib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import os

# Librerie per il PDF con gestione testo
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Gestionale Cantieri", page_icon="🏗️", layout="wide")

DB_NAME = "gestionale_web_v2.db"

# --- FUNZIONI DATABASE ---
def get_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()
    
    c.execute("PRAGMA journal_mode=WAL")
    
    c.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password_hash TEXT, is_admin INTEGER DEFAULT 0)")
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
    c.execute("""
        CREATE TABLE IF NOT EXISTS costo_manodopera (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            data TEXT, cantiere_id INTEGER, operaio TEXT, descrizione TEXT, ore REAL, costo_orario REAL, totale REAL
        )
    """)
    c.execute("CREATE TABLE IF NOT EXISTS costo_materiali (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, cantiere_id INTEGER, fornitore TEXT, documento TEXT, imponibile REAL, iva REAL, totale REAL)")
    c.execute("CREATE TABLE IF NOT EXISTS costo_amministrativo (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, descrizione TEXT, importo REAL)")
    c.execute("CREATE TABLE IF NOT EXISTS categorie_amministrative (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE)")
    c.execute("CREATE TABLE IF NOT EXISTS incassi (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, cantiere_id INTEGER, fattura TEXT, imponibile REAL, iva REAL, totale REAL)")
    
    try:
        c.execute("ALTER TABLE preventivi ADD COLUMN stato TEXT DEFAULT 'Attivo'")
    except sqlite3.OperationalError:
        pass
    
    try:
        c.execute("ALTER TABLE costo_manodopera ADD COLUMN descrizione TEXT")
    except sqlite3.OperationalError:
        pass
    
    try:
        c.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    
    c.execute("SELECT * FROM users WHERE username = 'admin'")
    if not c.fetchone():
        hashed_pw = hashlib.sha256("Cantieri2024!".encode()).hexdigest()
        c.execute("INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)", ("admin", hashed_pw, 1))
    else:
        c.execute("UPDATE users SET is_admin = 1 WHERE username = 'admin'")
    
    conn.commit()
    conn.close()

init_db()

# --- FUNZIONE PER FORMATO DATA ITALIANO ---
def formatta_data_italiana(data_str):
    if not data_str:
        return ""
    try:
        data_obj = datetime.datetime.strptime(str(data_str)[:10], "%Y-%m-%d")
        return data_obj.strftime("%d/%m/%Y")
    except:
        return str(data_str)

# --- AUTENTICAZIONE ---
def verify_login(username, password):
    conn = get_connection()
    c = conn.cursor()
    hashed_pw = hashlib.sha256(password.encode()).hexdigest()
    c.execute("SELECT username, is_admin FROM users WHERE username = ? AND password_hash = ?", (username, hashed_pw))
    user = c.fetchone()
    conn.close()
    return user

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'current_page' not in st.session_state:
    st.session_state.current_page = "Home"
if 'is_admin' not in st.session_state:
    st.session_state.is_admin = False

def login_page():
    st.markdown("<h1 style='text-align: center; color: #2C3E50;'>🏗️ Gestionale Cantieri</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Accedi", use_container_width=True)
            if submit:
                user = verify_login(username, password)
                if user:
                    st.session_state.logged_in = True
                    st.session_state.username = user[0]
                    st.session_state.is_admin = (user[1] == 1)
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
    st.write("GESTIONE CANTIERE. Situazione attualizzata.")
    
    conn = get_connection()
    query_totali = """
        SELECT 
            (SELECT COUNT(*) FROM preventivi WHERE stato = 'Attivo') as num_cantieri,
            (SELECT SUM(imponibile) FROM incassi i JOIN preventivi p ON i.cantiere_id = p.id WHERE p.stato = 'Attivo') as tot_incassi,
            (SELECT SUM(totale) FROM costo_manodopera c JOIN preventivi p ON c.cantiere_id = p.id WHERE p.stato = 'Attivo') as tot_costi_pers,
            (SELECT SUM(imponibile) FROM costo_materiali c JOIN preventivi p ON c.cantiere_id = p.id WHERE p.stato = 'Attivo') as tot_costi_mat,
            (SELECT SUM(importo) FROM costo_amministrativo) as tot_costi_amm
    """
    res = pd.read_sql_query(query_totali, conn).iloc[0]
    conn.close()
    
    num_cantieri = res['num_cantieri'] or 0
    tot_incassi = res['tot_incassi'] or 0
    tot_costi = (res['tot_costi_pers'] or 0) + (res['tot_costi_mat'] or 0) + (res['tot_costi_amm'] or 0)
    saldo = tot_incassi - tot_costi
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(label="🏗️ Cantieri Attivi", value=num_cantieri)
    with col2:
        st.metric(label="💰 Incassi (Imponibile)", value=f"€ {tot_incassi:,.2f}")
    with col3:
        st.metric(label="📉 Costi Totali", value=f"€ {tot_costi:,.2f}", delta_color="inverse")
    with col4:
        st.metric(label="⚖️ Saldo", value=f"€ {saldo:,.2f}", delta_color="normal" if saldo >= 0 else "inverse")
    
    st.divider()
    
    st.subheader("🚀 Accessi Rapidi")
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("📋 Inserisci Cantieri", use_container_width=True, key="home_btn_cantieri"):
            st.session_state.current_page = "Cantieri"; st.rerun()
        if st.button("📉 Inserisci Costi", use_container_width=True, key="home_btn_costi"):
            st.session_state.current_page = "Costi"; st.rerun()
        if st.button("📈 Avanzamento Cantieri", use_container_width=True, key="home_btn_avanzamento"):
            st.session_state.current_page = "Avanzamento"; st.rerun()
    with col_btn2:
        if st.button("👥 Anagrafica", use_container_width=True, key="home_btn_anagrafiche"):
            st.session_state.current_page = "Anagrafiche"; st.rerun()
        if st.button("💰 Incassi", use_container_width=True, key="home_btn_incassi"):
            st.session_state.current_page = "Incassi"; st.rerun()
        if st.button("📊 Riepilogo", use_container_width=True, key="home_btn_riepilogo"):
            st.session_state.current_page = "Riepilogo"; st.rerun()

def page_cantieri():
    st.title("📋 Gestione Cantieri")
    
    with st.expander("➕ Aggiungi Nuovo Cantiere"):
        with st.form("nuovo_cantiere_form", clear_on_submit=True):
            col1, col2, col3 = st.columns(3)
            data = col1.date_input("Data", datetime.date.today(), format="DD/MM/YYYY")
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
    df = pd.read_sql_query("SELECT id, data, n_prev, cliente, indirizzo, descrizione, importo_prev, importo_contratto, stato FROM preventivi", conn)
    conn.close()
    
    if not df.empty:
        df['data'] = df['data'].apply(formatta_data_italiana)
        st.dataframe(df, use_container_width=True)
        
        st.subheader("Gestisci Cantiere Selezionato")
        cantiere_sel = st.selectbox("Seleziona Cantiere:", df['id'].tolist(), format_func=lambda x: f"ID {x} - {df[df['id']==x]['indirizzo'].values[0]}", key="sel_cantiere")
        
        cantiere_data = df[df['id'] == cantiere_sel].iloc[0]
        
        col_az1, col_az2 = st.columns(2)
        
        if cantiere_data['stato'] == 'Attivo':
            if col_az1.button("🔴 Chiudi Cantiere", use_container_width=True, key="btn_chiudi_cant"):
                conn = get_connection(); c = conn.cursor()
                c.execute("UPDATE preventivi SET stato='Chiuso' WHERE id=?", (cantiere_sel,))
                conn.commit(); conn.close(); st.rerun()
        else:
            if col_az1.button("🟢 Riapri Cantiere", use_container_width=True, key="btn_riapri_cant"):
                conn = get_connection(); c = conn.cursor()
                c.execute("UPDATE preventivi SET stato='Attivo' WHERE id=?", (cantiere_sel,))
                conn.commit(); conn.close(); st.rerun()
        
        with col_az2:
            if st.button("🗑️ Elimina Cantiere", type="primary", use_container_width=True, key="btn_elimina_cant"):
                st.session_state.confirm_delete_cantiere = True
        
        if st.session_state.get('confirm_delete_cantiere'):
            st.warning("Sei sicuro? Questa azione è irreversibile.")
            if st.button("Sì, elimina definitivamente", key="btn_conferma_elimina_cant"):
                conn = get_connection(); c = conn.cursor()
                c.execute("DELETE FROM preventivi WHERE id=?", (cantiere_sel,))
                conn.commit(); conn.close()
                st.session_state.confirm_delete_cantiere = False
                st.success("Cantiere eliminato."); st.rerun()

        with st.expander("✏️ Modifica Dati Cantiere"):
            with st.form("modifica_cantiere_form"):
                m_cliente = st.text_input("Cliente", value=cantiere_data['cliente'])
                m_indirizzo = st.text_input("Indirizzo", value=cantiere_data['indirizzo'])
                m_descrizione = st.text_input("Descrizione", value=cantiere_data['descrizione'])
                m_importo_prev = st.number_input("Importo Preventivo (€)", value=float(cantiere_data['importo_prev']))
                m_importo = st.number_input("Importo Contratto (€)", value=float(cantiere_data['importo_contratto']))
                
                if st.form_submit_button("Salva Modifiche"):
                    conn = get_connection(); c = conn.cursor()
                    c.execute("UPDATE preventivi SET cliente=?, indirizzo=?, descrizione=?, importo_prev=?, importo_contratto=? WHERE id=?", 
                              (m_cliente, m_indirizzo, m_descrizione, m_importo_prev, m_importo, cantiere_sel))
                    conn.commit(); conn.close(); st.success("Modifiche salvate!"); st.rerun()
    else:
        st.info("Nessun cantiere presente.")

def page_anagrafiche():
    st.title("👥 Anagrafiche Operai, Fornitori e Categorie Spese")
    tab1, tab2, tab3 = st.tabs(["Operai", "Fornitori", "Categorie Amministrative"])
    
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
        
        if not df_op.empty:
            st.subheader("Gestisci Operaio")
            op_sel = st.selectbox("Seleziona Operaio", df_op['nome'].tolist(), key="sel_operaio")
            op_data = df_op[df_op['nome'] == op_sel].iloc[0]
            
            col1, col2 = st.columns(2)
            with col1:
                with st.form("modifica_operaio"):
                    new_ruolo = st.text_input("Ruolo", value=op_data['ruolo'])
                    new_costo = st.number_input("Costo Orario (€)", value=float(op_data['costo_orario']))
                    if st.form_submit_button("Salva Modifiche"):
                        conn = get_connection(); c = conn.cursor()
                        c.execute("UPDATE operai SET ruolo=?, costo_orario=? WHERE nome=?", (new_ruolo, new_costo, op_sel))
                        conn.commit(); conn.close(); st.success("Modifiche salvate!"); st.rerun()
            with col2:
                if st.button("Elimina Operaio", type="primary", key="btn_elimina_operaio"):
                    conn = get_connection(); c = conn.cursor()
                    c.execute("DELETE FROM operai WHERE nome=?", (op_sel,))
                    conn.commit(); conn.close(); st.success("Operaio eliminato!"); st.rerun()

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
        
        if not df_forn.empty:
            st.subheader("Gestisci Fornitore")
            forn_sel = st.selectbox("Seleziona Fornitore", df_forn['nome'].tolist(), key="sel_fornitore")
            forn_data = df_forn[df_forn['nome'] == forn_sel].iloc[0]
            
            col1, col2 = st.columns(2)
            with col1:
                with st.form("modifica_fornitore"):
                    new_piva = st.text_input("P.IVA", value=forn_data['piva'])
                    new_contatto = st.text_input("Contatto", value=forn_data['contatto'])
                    if st.form_submit_button("Salva Modifiche"):
                        conn = get_connection(); c = conn.cursor()
                        c.execute("UPDATE fornitori SET piva=?, contatto=? WHERE nome=?", (new_piva, new_contatto, forn_sel))
                        conn.commit(); conn.close(); st.success("Modifiche salvate!"); st.rerun()
            with col2:
                if st.button("Elimina Fornitore", type="primary", key="btn_elimina_fornitore"):
                    conn = get_connection(); c = conn.cursor()
                    c.execute("DELETE FROM fornitori WHERE nome=?", (forn_sel,))
                    conn.commit(); conn.close(); st.success("Fornitore eliminato!"); st.rerun()

    with tab3:
        with st.expander("➕ Nuova Categoria di Spesa"):
            with st.form("nuova_categoria", clear_on_submit=True):
                nome_cat = st.text_input("Nome Categoria (es. Commercialista, Elettricità)")
                if st.form_submit_button("Salva Categoria"):
                    if nome_cat:
                        conn = get_connection(); c = conn.cursor()
                        try:
                            c.execute("INSERT INTO categorie_amministrative (nome) VALUES (?)", (nome_cat,))
                            conn.commit(); st.success("Categoria aggiunta!")
                        except sqlite3.IntegrityError:
                            st.error("Questa categoria esiste già.")
                        conn.close(); st.rerun()
        
        conn = get_connection()
        df_cat = pd.read_sql_query("SELECT * FROM categorie_amministrative", conn)
        conn.close()
        st.dataframe(df_cat, use_container_width=True)
        
        if not df_cat.empty:
            st.subheader("Gestisci Categoria")
            cat_sel = st.selectbox("Seleziona Categoria", df_cat['nome'].tolist(), key="sel_categoria")
            
            col1, col2 = st.columns(2)
            with col1:
                with st.form("modifica_categoria"):
                    new_nome = st.text_input("Nuovo Nome", value=cat_sel)
                    if st.form_submit_button("Rinomina"):
                        conn = get_connection(); c = conn.cursor()
                        c.execute("UPDATE categorie_amministrative SET nome=? WHERE nome=?", (new_nome, cat_sel))
                        conn.commit(); conn.close(); st.success("Categoria rinominata!"); st.rerun()
            with col2:
                if st.button("Elimina Categoria", type="primary", key="btn_elimina_categoria"):
                    conn = get_connection(); c = conn.cursor()
                    c.execute("DELETE FROM categorie_amministrative WHERE nome=?", (cat_sel,))
                    conn.commit(); conn.close(); st.success("Categoria eliminata!"); st.rerun()

def page_utenti():
    st.title("👤 Gestione Utenti")
    st.write("Crea e gestisci gli account che possono accedere al gestionale.")
    
    conn = get_connection()
    
    with st.expander("➕ Nuovo Utente"):
        with st.form("nuovo_utente", clear_on_submit=True):
            col1, col2 = st.columns(2)
            new_user = col1.text_input("Username")
            new_pass = col2.text_input("Password", type="password")
            
            is_admin_new = st.checkbox("Rendi questo utente Amministratore (può gestire altri utenti)")
            
            if st.form_submit_button("Crea Utente"):
                if new_user and new_pass:
                    hashed_pw = hashlib.sha256(new_pass.encode()).hexdigest()
                    try:
                        c = conn.cursor()
                        c.execute("INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)", 
                                  (new_user, hashed_pw, 1 if is_admin_new else 0))
                        conn.commit()
                        st.success(f"Utente '{new_user}' creato con successo!")
                    except sqlite3.IntegrityError:
                        st.error("Questo username esiste già.")
                else:
                    st.error("Username e Password sono obbligatori.")
    
    st.subheader("👥 Utenti Registrati")
    df_users = pd.read_sql_query("SELECT username, is_admin FROM users", conn)
    
    if not df_users.empty:
        df_users['is_admin'] = df_users['is_admin'].apply(lambda x: "Sì" if x == 1 else "No")
        df_users = df_users.rename(columns={'username': 'Username', 'is_admin': 'Amministratore'})
        st.dataframe(df_users, use_container_width=True)
        
        st.subheader("Gestisci Utente")
        user_sel = st.selectbox("Seleziona Utente", df_users['Username'].tolist(), key="sel_user_gest")
        
        if user_sel == "admin":
            st.info("L'utente 'admin' è l'amministratore principale e non può essere modificato o eliminato.")
        else:
            col1, col2 = st.columns(2)
            with col1:
                with st.form("modifica_utente"):
                    new_password = st.text_input("Nuova Password (lascia vuoto per non cambiare)", type="password")
                    new_admin_status = st.checkbox("Amministratore")
                    
                    if st.form_submit_button("Aggiorna Utente"):
                        c = conn.cursor()
                        if new_password:
                            hashed_pw = hashlib.sha256(new_password.encode()).hexdigest()
                            c.execute("UPDATE users SET password_hash=?, is_admin=? WHERE username=?", 
                                      (hashed_pw, 1 if new_admin_status else 0, user_sel))
                        else:
                            c.execute("UPDATE users SET is_admin=? WHERE username=?", 
                                      (1 if new_admin_status else 0, user_sel))
                        conn.commit()
                        st.success("Utente aggiornato!"); st.rerun()
            with col2:
                if st.button("Elimina Utente", type="primary", key="btn_elimina_utente"):
                    c = conn.cursor()
                    c.execute("DELETE FROM users WHERE username=?", (user_sel,))
                    conn.commit()
                    st.success("Utente eliminato!"); st.rerun()
    else:
        st.info("Nessun utente registrato (a parte admin).")
    
    conn.close()

def page_costi():
    st.title("📉 Inserimento Costi")
    
    cantieri = get_cantieri()
    operai = get_operai()
    fornitori = get_fornitori()
    
    if cantieri.empty:
        st.warning("Devi prima creare un cantiere!")
        return

    if "modifica_costo_attiva" not in st.session_state:
        st.session_state.modifica_costo_attiva = False
    if "costo_da_modificare" not in st.session_state:
        st.session_state.costo_da_modificare = None

    tab1, tab2, tab3 = st.tabs(["Costo Personale", "Costo Materiale", "Costo Amministrativo"])
    
    with tab1:
        st.subheader("Registra Ore Lavorate")
        col1, col2 = st.columns(2)
        data_m = col1.date_input("Data", datetime.date.today(), format="DD/MM/YYYY", key="data_manodopera")
        cantiere_m = col2.selectbox("Cantiere", cantieri['id'].tolist(), format_func=lambda x: cantieri[cantieri['id']==x]['indirizzo'].values[0], key="cant_manodopera")
        
        if not operai.empty:
            col3, col4 = st.columns(2)
            operaio_sel = col3.selectbox("Operaio", operai['nome'].tolist(), key="op_manodopera")
            costo_standard = operai[operai['nome'] == operaio_sel]['costo_orario'].values[0]
            
            costo_orario = col4.number_input("Costo Orario (€)", min_value=0.0, step=1.0, value=float(costo_standard), key="costo_orario")
            ore = st.number_input("Ore Lavorate", min_value=0.0, step=0.5, key="ore_lavorate")
            
            descrizione_lavori = st.text_input("Descrizione Lavori Eseguiti (es. Posa massetto, Getto cemento)", key="desc_lavori")
            
            if st.button("Salva Costo Personale", type="primary", key="btn_salva_manodopera"):
                totale = ore * costo_orario
                conn = get_connection(); c = conn.cursor()
                c.execute("INSERT INTO costo_manodopera (data, cantiere_id, operaio, descrizione, ore, costo_orario, totale) VALUES (?,?,?,?,?,?,?)", 
                          (str(data_m), cantiere_m, operaio_sel, descrizione_lavori, ore, costo_orario, totale))
                conn.commit(); conn.close(); st.success("Costo personale registrato!"); st.rerun()
        else:
            st.info("Nessun operaio in anagrafica.")

    with tab2:
        with st.form("form_materiali", clear_on_submit=True):
            st.subheader("Registra Acquisto Materiale")
            col1, col2 = st.columns(2)
            data_mat = col1.date_input("Data", datetime.date.today(), format="DD/MM/YYYY", key="data_materiale")
            cantiere_mat = col2.selectbox("Cantiere", cantieri['id'].tolist(), format_func=lambda x: cantieri[cantieri['id']==x]['indirizzo'].values[0], key="cant_materiale")
            
            if not fornitori.empty:
                col3, col4 = st.columns(2)
                fornitore_sel = col3.selectbox("Fornitore", fornitori['nome'].tolist(), key="fornitore_materiale")
                documento = col4.text_input("N. Documento / Fattura", key="documento_materiale")
                
                col5, col6 = st.columns(2)
                imponibile = col5.number_input("Imponibile (€)", min_value=0.0, step=10.0, key="imponibile")
                iva = col6.number_input("Aliquota IVA (%)", min_value=0.0, value=22.0, step=1.0, key="iva_materiale")
            else:
                st.info("Nessun fornitore in anagrafica. Aggiungine uno per poter registrare i materiali.")
                fornitore_sel = None
                documento = ""
                imponibile = 0.0
                iva = 0.0

            if st.form_submit_button("Salva Costo Materiale"):
                if fornitore_sel:
                    totale = imponibile + (imponibile * iva / 100)
                    conn = get_connection(); c = conn.cursor()
                    c.execute("INSERT INTO costo_materiali (data, cantiere_id, fornitore, documento, imponibile, iva, totale) VALUES (?,?,?,?,?,?,?)", 
                              (str(data_mat), cantiere_mat, fornitore_sel, documento, imponibile, iva, totale))
                    conn.commit(); conn.close(); st.success("Costo materiale registrato!"); st.rerun()
                else:
                    st.error("Devi prima selezionare un fornitore.")

    with tab3:
        st.subheader("Registra Costo Amministrativo")
        st.write("Spese generali non legate a un cantiere specifico.")
        
        conn = get_connection()
        df_cat = pd.read_sql_query("SELECT nome FROM categorie_amministrative", conn)
        conn.close()
        
        with st.form("form_amministrativo", clear_on_submit=True):
            col1, col2 = st.columns(2)
            data_amm = col1.date_input("Data", datetime.date.today(), format="DD/MM/YYYY", key="data_amm")
            
            if not df_cat.empty:
                desc_amm = col2.selectbox("Categoria Spesa", df_cat['nome'].tolist(), key="desc_amm")
            else:
                st.warning("Nessuna categoria disponibile. Aggiungine una nella sezione 'Anagrafiche'.")
                desc_amm = None
            
            importo_amm = st.number_input("Importo (€)", min_value=0.0, step=10.0, key="importo_amm")
            
            if st.form_submit_button("Salva Costo Amministrativo"):
                if desc_amm and importo_amm > 0:
                    conn = get_connection(); c = conn.cursor()
                    c.execute("INSERT INTO costo_amministrativo (data, descrizione, importo) VALUES (?,?,?)", 
                              (str(data_amm), desc_amm, importo_amm))
                    conn.commit(); conn.close(); st.success("Costo amministrativo registrato!"); st.rerun()
                else:
                    st.error("Devi selezionare una categoria e inserire un importo.")

    st.divider()

    if st.session_state.modifica_costo_attiva and st.session_state.costo_da_modificare:
        id_unico = st.session_state.costo_da_modificare
        
        esiste = False
        tipo_costo = ""
        real_id = ""
        
        if id_unico.startswith("M-"):
            real_id = id_unico.replace("M-", "")
            conn = get_connection()
            check = pd.read_sql_query(f"SELECT id FROM costo_manodopera WHERE id={real_id}", conn)
            conn.close()
            if not check.empty:
                esiste = True
                tipo_costo = "manodopera"
        elif id_unico.startswith("Mat-"):
            real_id = id_unico.replace("Mat-", "")
            conn = get_connection()
            check = pd.read_sql_query(f"SELECT id FROM costo_materiali WHERE id={real_id}", conn)
            conn.close()
            if not check.empty:
                esiste = True
                tipo_costo = "materiali"
        elif id_unico.startswith("Amm-"):
            real_id = id_unico.replace("Amm-", "")
            conn = get_connection()
            check = pd.read_sql_query(f"SELECT id FROM costo_amministrativo WHERE id={real_id}", conn)
            conn.close()
            if not check.empty:
                esiste = True
                tipo_costo = "amministrativo"
        
        if not esiste:
            st.warning("Questo costo non esiste più nel database (potrebbe essere stato eliminato o il database è stato ripristinato). La modifica è stata annullata.")
            st.session_state.modifica_costo_attiva = False
            st.session_state.costo_da_modificare = None
            st.button("Torna all'elenco", key="btn_torna_elenco_errore")
            st.stop()
        
        with st.container():
            st.subheader(f"✏️ Modifica Costo: {id_unico}")
            
            if tipo_costo == "manodopera":
                conn = get_connection()
                df_specifico = pd.read_sql_query(f"SELECT * FROM costo_manodopera WHERE id={real_id}", conn)
                conn.close()
                row = df_specifico.iloc[0]
                
                with st.form("modifica_manodopera_form"):
                    col1, col2 = st.columns(2)
                    m_data = col1.date_input("Data", pd.to_datetime(row['data']).date(), format="DD/MM/YYYY")
                    m_ore = col2.number_input("Ore Lavorate", value=float(row['ore']), step=0.5)
                    m_costo = st.number_input("Costo Orario (€)", value=float(row['costo_orario']), step=1.0)
                    m_desc = st.text_input("Descrizione Lavori", value=row['descrizione'] if row['descrizione'] else "")
                    
                    col_btn1, col_btn2 = st.columns(2)
                    if col_btn1.form_submit_button("Salva Modifiche", type="primary"):
                        tot = m_ore * m_costo
                        conn = get_connection(); c = conn.cursor()
                        c.execute("UPDATE costo_manodopera SET data=?, ore=?, costo_orario=?, descrizione=?, totale=? WHERE id=?", 
                                  (str(m_data), m_ore, m_costo, m_desc, tot, real_id))
                        conn.commit(); conn.close()
                        st.session_state.modifica_costo_attiva = False
                        st.session_state.costo_da_modificare = None
                        st.success("Costo aggiornato!"); st.rerun()
                        
                    if col_btn2.form_submit_button("Elimina Costo", type="secondary"):
                        conn = get_connection(); c = conn.cursor()
                        c.execute("DELETE FROM costo_manodopera WHERE id=?", (real_id,))
                        conn.commit(); conn.close()
                        st.session_state.modifica_costo_attiva = False
                        st.session_state.costo_da_modificare = None
                        st.success("Costo eliminato!"); st.rerun()
            
            elif tipo_costo == "materiali":
                conn = get_connection()
                df_specifico = pd.read_sql_query(f"SELECT * FROM costo_materiali WHERE id={real_id}", conn)
                conn.close()
                row = df_specifico.iloc[0]
                
                with st.form("modifica_materiali_form"):
                    col1, col2 = st.columns(2)
                    m_data = col1.date_input("Data", pd.to_datetime(row['data']).date(), format="DD/MM/YYYY")
                    m_doc = col2.text_input("N. Documento", value=row['documento'])
                    
                    col3, col4 = st.columns(2)
                    m_imp = col3.number_input("Imponibile (€)", value=float(row['imponibile']), step=10.0)
                    m_iva = col4.number_input("Aliquota IVA (%)", value=float(row['iva']), step=1.0)
                    
                    col_btn1, col_btn2 = st.columns(2)
                    if col_btn1.form_submit_button("Salva Modifiche", type="primary"):
                        tot = m_imp + (m_imp * m_iva / 100)
                        conn = get_connection(); c = conn.cursor()
                        c.execute("UPDATE costo_materiali SET data=?, documento=?, imponibile=?, iva=?, totale=? WHERE id=?", 
                                  (str(m_data), m_doc, m_imp, m_iva, tot, real_id))
                        conn.commit(); conn.close()
                        st.session_state.modifica_costo_attiva = False
                        st.session_state.costo_da_modificare = None
                        st.success("Costo aggiornato!"); st.rerun()
                        
                    if col_btn2.form_submit_button("Elimina Costo", type="secondary"):
                        conn = get_connection(); c = conn.cursor()
                        c.execute("DELETE FROM costo_materiali WHERE id=?", (real_id,))
                        conn.commit(); conn.close()
                        st.session_state.modifica_costo_attiva = False
                        st.session_state.costo_da_modificare = None
                        st.success("Costo eliminato!"); st.rerun()

            elif tipo_costo == "amministrativo":
                conn = get_connection()
                df_specifico = pd.read_sql_query(f"SELECT * FROM costo_amministrativo WHERE id={real_id}", conn)
                conn.close()
                row = df_specifico.iloc[0]
                
                with st.form("modifica_amministrativo_form"):
                    col1, col2 = st.columns(2)
                    m_data = col1.date_input("Data", pd.to_datetime(row['data']).date(), format="DD/MM/YYYY")
                    
                    conn = get_connection()
                    df_cat = pd.read_sql_query("SELECT nome FROM categorie_amministrative", conn)
                    conn.close()
                    
                    if not df_cat.empty:
                        try:
                            idx_cat = df_cat['nome'].tolist().index(row['descrizione'])
                        except ValueError:
                            idx_cat = 0
                        m_desc = col2.selectbox("Categoria", df_cat['nome'].tolist(), index=idx_cat)
                    else:
                        m_desc = col2.text_input("Descrizione", value=row['descrizione'])
                    
                    m_imp = st.number_input("Importo (€)", value=float(row['importo']), step=10.0)
                    
                    col_btn1, col_btn2 = st.columns(2)
                    if col_btn1.form_submit_button("Salva Modifiche", type="primary"):
                        conn = get_connection(); c = conn.cursor()
                        c.execute("UPDATE costo_amministrativo SET data=?, descrizione=?, importo=? WHERE id=?", 
                                  (str(m_data), m_desc, m_imp, real_id))
                        conn.commit(); conn.close()
                        st.session_state.modifica_costo_attiva = False
                        st.session_state.costo_da_modificare = None
                        st.success("Costo aggiornato!"); st.rerun()
                        
                    if col_btn2.form_submit_button("Elimina Costo", type="secondary"):
                        conn = get_connection(); c = conn.cursor()
                        c.execute("DELETE FROM costo_amministrativo WHERE id=?", (real_id,))
                        conn.commit(); conn.close()
                        st.session_state.modifica_costo_attiva = False
                        st.session_state.costo_da_modificare = None
                        st.success("Costo eliminato!"); st.rerun()
            
            if st.button("Annulla Modifica", key="btn_annulla_modifica"):
                st.session_state.modifica_costo_attiva = False
                st.session_state.costo_da_modificare = None
                st.rerun()
            
        st.divider()

    st.subheader("📋 Elenco Costi Registrati")
    
    with st.expander("🔍 Filtra i costi", expanded=True):
        col_f1, col_f2, col_f3, col_f4 = st.columns(4)
        filtro_testo = col_f1.text_input("Cerca (Operaio/Fornitore/Cantiere)", placeholder="Scrivi qui...")
        filtro_tipo = col_f2.selectbox("Tipo di costo", ["Tutti", "Personale", "Materiale", "Amministrativo"])
        data_inizio = col_f3.date_input("Dal", value=datetime.date.today().replace(month=1, day=1), format="DD/MM/YYYY")
        data_fine = col_f4.date_input("Al", value=datetime.date.today(), format="DD/MM/YYYY")
    
    query_pers = f"""
        SELECT 'M-' || id as ID_Unico, 'Personale' as Tipo, data, 
               (SELECT indirizzo FROM preventivi WHERE id = cantiere_id) as Cantiere, 
               operaio || ' - ' || COALESCE(descrizione, '') as Descrizione, totale as Totale
        FROM costo_manodopera
        WHERE data >= '{data_inizio}' AND data <= '{data_fine}'
    """
    query_mat = f"""
        SELECT 'Mat-' || id as ID_Unico, 'Materiale' as Tipo, data, 
               (SELECT indirizzo FROM preventivi WHERE id = cantiere_id) as Cantiere, 
               fornitore as Descrizione, imponibile as Totale
        FROM costo_materiali
        WHERE data >= '{data_inizio}' AND data <= '{data_fine}'
    """
    query_amm = f"""
        SELECT 'Amm-' || id as ID_Unico, 'Amministrativo' as Tipo, data, 
               'Spese Generali' as Cantiere, 
               descrizione as Descrizione, importo as Totale
        FROM costo_amministrativo
        WHERE data >= '{data_inizio}' AND data <= '{data_fine}'
    """
    
    if filtro_tipo == "Personale":
        query = query_pers
    elif filtro_tipo == "Materiale":
        query = query_mat
    elif filtro_tipo == "Amministrativo":
        query = query_amm
    else:
        query = query_pers + " UNION ALL " + query_mat + " UNION ALL " + query_amm
    
    query += " ORDER BY data DESC"
    
    conn = get_connection()
    df_costi = pd.read_sql_query(query, conn)
    conn.close()
    
    if filtro_testo and not df_costi.empty:
        mask = (
            df_costi['Cantiere'].str.contains(filtro_testo, case=False, na=False) |
            df_costi['Descrizione'].str.contains(filtro_testo, case=False, na=False)
        )
        df_costi = df_costi[mask]
    
    if df_costi.empty:
        st.info("Nessun costo trovato con i filtri selezionati.")
    else:
        df_costi.columns = [c.capitalize() for c in df_costi.columns]
        
        for index, row in df_costi.iterrows():
            col_dati, col_btn = st.columns([8, 2])
            with col_dati:
                data_it = formatta_data_italiana(row['Data'])
                st.markdown(f"**{row['Tipo']}** | {data_it} | {row['Cantiere']} | {row['Descrizione']} | **€ {row['Totale']:,.2f}**")
            with col_btn:
                if st.button("✏️ Modifica", key=f"mod_{row['Id_unico']}"):
                    st.session_state.modifica_costo_attiva = True
                    st.session_state.costo_da_modificare = row['Id_unico']
                    st.rerun()
        
        st.divider()
        totale_filtrato = df_costi['Totale'].sum()
        st.markdown(f"### Totale dei costi filtrati: **€ {totale_filtrato:,.2f}**")
        
        if st.button("📄 Esporta Risultati in PDF", type="primary", key="btn_export_pdf_costi"):
            try:
                filename = f"Riepilogo_Costi_{datetime.date.today()}.pdf"
                doc = SimpleDocTemplate(filename, pagesize=landscape(A4))
                elements = []
                styles = getSampleStyleSheet()
                
                # Stile per il testo nelle celle (per andare a capo)
                style_cell = ParagraphStyle(
                    'cell_style',
                    parent=styles['Normal'],
                    fontSize=8,
                    leading=10,
                    alignment=0
                )

                data_inizio_it = formatta_data_italiana(data_inizio)
                data_fine_it = formatta_data_italiana(data_fine)
                
                elements.append(Paragraph(f"Riepilogo Costi dal {data_inizio_it} al {data_fine_it}", styles['Title']))
                if filtro_testo:
                    elements.append(Paragraph(f"Filtro di ricerca: '{filtro_testo}'", styles['Normal']))
                if filtro_tipo != "Tutti":
                    elements.append(Paragraph(f"Tipo: {filtro_tipo}", styles['Normal']))
                elements.append(Spacer(1, 12))
                
                data_rows = [["Tipo", "Data", "Cantiere", "Descrizione", "Totale (€)"]]
                
                for _, row in df_costi.iterrows():
                    data_rows.append([
                        row['Tipo'], 
                        formatta_data_italiana(row['Data']), 
                        Paragraph(row['Cantiere'], style_cell), 
                        Paragraph(row['Descrizione'], style_cell), 
                        f"{row['Totale']:,.2f}"
                    ])
                
                data_rows.append(["", "", "", "TOTALE GENERALE", f"€ {totale_filtrato:,.2f}"])
                
                # Colonne bilanciate
                t = Table(data_rows, colWidths=[80, 70, 180, 200, 80], repeatRows=1)
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -2), colors.HexColor("#F4F6F7")),
                    ('GRID', (0, 0), (-1, -1), 1, colors.HexColor("#BDC3C7")),
                    ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ]))
                elements.append(t)
                
                doc.build(elements)
                st.success(f"PDF generato con successo: {filename}")
                
                with open(filename, "rb") as f:
                    st.download_button(
                        label="⬇️ Scarica il PDF",
                        data=f,
                        file_name=filename,
                        mime="application/pdf"
                    )
            except Exception as e:
                st.error(f"Errore durante la generazione del PDF: {e}")

def page_incassi():
    st.title("💰 Gestione Incassi")
    cantieri = get_cantieri()
    if cantieri.empty:
        st.warning("Devi prima creare un cantiere!")
        return

    with st.expander("➕ Registra Nuovo Incasso"):
        with st.form("nuovo_incasso", clear_on_submit=True):
            col1, col2 = st.columns(2)
            data_i = col1.date_input("Data Fattura", datetime.date.today(), format="DD/MM/YYYY", key="data_incasso")
            cantiere_i = col2.selectbox("Cantiere", cantieri['id'].tolist(), format_func=lambda x: cantieri[cantieri['id']==x]['indirizzo'].values[0], key="cant_incasso")
            
            col3, col4, col5 = st.columns(3)
            fattura = col3.text_input("N. Fattura", key="num_fattura")
            imponibile = col4.number_input("Imponibile (€)", min_value=0.0, step=100.0, key="imp_incasso")
            iva = col5.number_input("Aliquota IVA (%)", min_value=0.0, value=22.0, step=1.0, key="iva_incasso")
            
            if st.form_submit_button("Salva Incasso"):
                totale = imponibile + (imponibile * iva / 100)
                conn = get_connection(); c = conn.cursor()
                c.execute("INSERT INTO incassi (data, cantiere_id, fattura, imponibile, iva, totale) VALUES (?,?,?,?,?,?)", 
                          (str(data_i), cantiere_i, fattura, imponibile, iva, totale))
                conn.commit(); conn.close(); st.success("Incasso registrato!"); st.rerun()

    st.divider()
    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT i.id, i.data, p.indirizzo as Cantiere, i.fattura, i.imponibile, i.iva, i.totale 
        FROM incassi i JOIN preventivi p ON i.cantiere_id = p.id
    """, conn)
    conn.close()
    
    if not df.empty:
        df['data'] = df['data'].apply(formatta_data_italiana)
    
    st.dataframe(df, use_container_width=True)

    if not df.empty:
        st.subheader("Elimina Incasso")
        incasso_sel = st.selectbox("Seleziona Incasso", df['id'].tolist(), format_func=lambda x: f"ID {x} - {df[df['id']==x]['fattura'].values[0]} - €{df[df['id']==x]['totale'].values[0]}", key="sel_incasso")
        if st.button("Elimina Incasso Selezionato", type="primary", key="btn_elimina_incasso"):
            conn = get_connection(); c = conn.cursor()
            c.execute("DELETE FROM incassi WHERE id=?", (incasso_sel,))
            conn.commit(); conn.close(); st.success("Incasso eliminato!"); st.rerun()

def page_avanzamento():
    st.title("📈 Avanzamento Lavori (Calcolo Automatico)")
    st.write("L'avanzamento lavori è calcolato automaticamente in base agli incassi registrati rispetto all'importo contrattuale.")
    
    conn = get_connection()
    
    query_avanzamento = """
        SELECT 
            p.id,
            p.indirizzo as Cantiere,
            p.importo_contratto,
            COALESCE((SELECT SUM(imponibile) FROM incassi WHERE cantiere_id = p.id), 0) as Totale_Incassato
        FROM preventivi p
        WHERE p.stato = 'Attivo'
    """
    df = pd.read_sql_query(query_avanzamento, conn)
    conn.close()
    
    if df.empty:
        st.info("Nessun cantiere attivo presente.")
    else:
        df['Percentuale'] = df.apply(lambda row: (row['Totale_Incassato'] / row['importo_contratto'] * 100) if row['importo_contratto'] > 0 else 0, axis=1)
        
        df_visual = df.copy()
        df_visual['importo_contratto'] = df_visual['importo_contratto'].apply(lambda x: f"€ {x:,.2f}")
        df_visual['Totale_Incassato'] = df_visual['Totale_Incassato'].apply(lambda x: f"€ {x:,.2f}")
        df_visual['Percentuale'] = df_visual['Percentuale'].apply(lambda x: f"{x:.1f}%")
        
        df_visual = df_visual.rename(columns={
            'Cantiere': 'Cantiere', 
            'importo_contratto': 'Importo Contratto', 
            'Totale_Incassato': 'Totale Incassato'
        })
        
        st.dataframe(df_visual[['Cantiere', 'Importo Contratto', 'Totale Incassato', 'Percentuale']], use_container_width=True)
        
        st.divider()
        st.subheader("Dettaglio Visivo")
        
        for index, row in df.iterrows():
            perc = (row['Totale_Incassato'] / row['importo_contratto'] * 100) if row['importo_contratto'] > 0 else 0
            st.markdown(f"**{row['Cantiere']}** - {perc:.1f}%")
            st.progress(min(perc / 100, 1.0))

def page_riepilogo():
    st.title("📊 Riepilogo e Grafici")
    
    conn = get_connection()
    
    query_totali = """
        SELECT 
            (SELECT SUM(importo_contratto) FROM preventivi WHERE stato = 'Attivo') as tot_contratti,
            (SELECT SUM(imponibile) FROM incassi i JOIN preventivi p ON i.cantiere_id = p.id WHERE p.stato = 'Attivo') as tot_incassi,
            (SELECT SUM(totale) FROM costo_manodopera c JOIN preventivi p ON c.cantiere_id = p.id WHERE p.stato = 'Attivo') as tot_costi_man,
            (SELECT SUM(imponibile) FROM costo_materiali c JOIN preventivi p ON c.cantiere_id = p.id WHERE p.stato = 'Attivo') as tot_costi_mat,
            (SELECT SUM(importo) FROM costo_amministrativo) as tot_costi_amm
    """
    res = pd.read_sql_query(query_totali, conn).iloc[0]
    
    tot_contratti = res['tot_contratti'] or 0
    tot_incassi = res['tot_incassi'] or 0
    tot_costi = (res['tot_costi_man'] or 0) + (res['tot_costi_mat'] or 0) + (res['tot_costi_amm'] or 0)
    saldo = tot_incassi - tot_costi

    st.markdown("### 🏢 Totali Aziendali (Solo Cantieri Attivi)")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Contratti", f"€ {tot_contratti:,.2f}")
    col2.metric("Incassi (Imponibile)", f"€ {tot_incassi:,.2f}")
    col3.metric("Costi Totali", f"€ {tot_costi:,.2f}", delta_color="inverse")
    col4.metric("Saldo", f"€ {saldo:,.2f}", delta_color="normal")
    
    st.divider()

    # --- REPORT COSTI GRANULARE CON FILTRO DATE ---
    st.subheader("📋 Report Costi Dettagliato")
    st.write("Filtra per periodo, Cantiere, Tipo di Costo e Descrizione per un'analisi approfondita.")

    col_d1, col_d2 = st.columns(2)
    data_inizio_report = col_d1.date_input("Dal", value=datetime.date.today().replace(day=1), format="DD/MM/YYYY", key="data_inizio_report")
    data_fine_report = col_d2.date_input("Al", value=datetime.date.today(), format="DD/MM/YYYY", key="data_fine_report")

    col_r1, col_r2, col_r3 = st.columns(3)
    
    cantieri = get_cantieri()
    opzioni_cantieri = ["Tutti i cantieri"] + [f"{row['id']} - {row['indirizzo']}" for _, row in cantieri.iterrows()]
    filtro_cantiere = col_r1.selectbox("Seleziona Cantiere", opzioni_cantieri, key="filtro_cantiere_report")
    
    # Opzioni tipo costo con "Personale + Materiale"
    filtro_tipo_costo = col_r2.selectbox("Tipo di Costo", ["Tutti", "Personale", "Materiale", "Amministrativo", "Personale + Materiale"], key="filtro_tipo_report")
    
    filtro_descrizione = col_r3.text_input("Cerca nella Descrizione", placeholder="Es. massetto, fattura, commercialista...", key="filtro_desc_report")
    
    dfs = []
    
    if filtro_tipo_costo in ["Tutti", "Personale", "Personale + Materiale"]:
        q_p = f"""
            SELECT 'Personale' as Tipo, c.data, p.indirizzo as Cantiere, 
                   c.operaio || ' - ' || COALESCE(c.descrizione, '') as Descrizione, c.totale as Importo
            FROM costo_manodopera c JOIN preventivi p ON c.cantiere_id = p.id
            WHERE c.data >= '{data_inizio_report}' AND c.data <= '{data_fine_report}'
        """
        if filtro_cantiere != "Tutti i cantieri":
            cid = filtro_cantiere.split(" - ")[0]
            q_p += f" AND c.cantiere_id = {cid}"
        if filtro_descrizione:
            q_p += f" AND (c.operaio LIKE '%{filtro_descrizione}%' OR c.descrizione LIKE '%{filtro_descrizione}%')"
        dfs.append(pd.read_sql_query(q_p, conn))

    if filtro_tipo_costo in ["Tutti", "Materiale", "Personale + Materiale"]:
        q_m = f"""
            SELECT 'Materiale' as Tipo, c.data, p.indirizzo as Cantiere, 
                   c.fornitore as Descrizione, c.imponibile as Importo
            FROM costo_materiali c JOIN preventivi p ON c.cantiere_id = p.id
            WHERE c.data >= '{data_inizio_report}' AND c.data <= '{data_fine_report}'
        """
        if filtro_cantiere != "Tutti i cantieri":
            cid = filtro_cantiere.split(" - ")[0]
            q_m += f" AND c.cantiere_id = {cid}"
        if filtro_descrizione:
            q_m += f" AND c.fornitore LIKE '%{filtro_descrizione}%'"
        dfs.append(pd.read_sql_query(q_m, conn))

    if filtro_tipo_costo in ["Tutti", "Amministrativo"]:
        q_a = f"""
            SELECT 'Amministrativo' as Tipo, data, 'Spese Generali' as Cantiere, 
                   descrizione as Descrizione, importo as Importo
            FROM costo_amministrativo
            WHERE data >= '{data_inizio_report}' AND data <= '{data_fine_report}'
        """
        if filtro_descrizione:
            q_a += f" AND descrizione LIKE '%{filtro_descrizione}%'"
        dfs.append(pd.read_sql_query(q_a, conn))

    if dfs:
        df_report = pd.concat(dfs, ignore_index=True)
        
        if df_report.empty:
            st.info("Nessun costo trovato con i filtri selezionati.")
        else:
            totale_importo = df_report['Importo'].sum()
            
            df_report['Data'] = df_report['data'].apply(formatta_data_italiana)
            df_visual = df_report[['Tipo', 'Data', 'Cantiere', 'Descrizione', 'Importo']].copy()
            df_visual['Importo'] = df_visual['Importo'].apply(lambda x: f"€ {x:,.2f}")
            
            riga_totale = pd.DataFrame([{'Tipo': '', 'Data': '', 'Cantiere': '', 'Descrizione': 'TOTALE', 'Importo': f"€ {totale_importo:,.2f}"}])
            df_visual = pd.concat([df_visual, riga_totale], ignore_index=True)
            
            st.dataframe(df_visual, use_container_width=True)
            
            if st.button("📄 Esporta Report in PDF", type="primary", key="btn_export_report_dettagliato"):
                try:
                    filename = f"Report_Costi_Dettagliato_{datetime.date.today()}.pdf"
                    doc = SimpleDocTemplate(filename, pagesize=landscape(A4))
                    elements = []
                    styles = getSampleStyleSheet()
                    
                    # Stile per il testo nelle celle
                    style_cell = ParagraphStyle(
                        'cell_style',
                        parent=styles['Normal'],
                        fontSize=8,
                        leading=10,
                        alignment=0
                    )

                    data_inizio_it = formatta_data_italiana(data_inizio_report)
                    data_fine_it = formatta_data_italiana(data_fine_report)
                    
                    elements.append(Paragraph(f"Report Costi dal {data_inizio_it} al {data_fine_it} - {filtro_tipo_costo} - {filtro_cantiere}", styles['Title']))
                    elements.append(Spacer(1, 12))
                    
                    # Se il filtro è "Personale + Materiale", gestiamo la doppia tabella
                    if filtro_tipo_costo == "Personale + Materiale":
                        # Dividiamo i dati
                        df_pers = df_report[df_report['Tipo'] == 'Personale']
                        df_mat = df_report[df_report['Tipo'] == 'Materiale']
                        
                        # Totale Personale
                        tot_pers = df_pers['Importo'].sum()
                        elements.append(Paragraph(f"<b>1. Costi Personale</b>", styles['Heading2']))
                        elements.append(Spacer(1, 5))
                        
                        if not df_pers.empty:
                            data_rows_p = [["Tipo", "Data", "Cantiere", "Descrizione", "Importo (€)"]]
                            for _, row in df_pers.iterrows():
                                data_rows_p.append([
                                    row['Tipo'], 
                                    formatta_data_italiana(row['data']), 
                                    Paragraph(row['Cantiere'], style_cell), 
                                    Paragraph(row['Descrizione'], style_cell), 
                                    f"{row['Importo']:,.2f}"
                                ])
                            data_rows_p.append(["", "", "", "TOTALE PERSONALE", f"€ {tot_pers:,.2f}"])
                            
                            t_p = Table(data_rows_p, colWidths=[80, 70, 180, 200, 80], repeatRows=1)
                            t_p.setStyle(TableStyle([
                                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#34495E")),
                                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                                ('BACKGROUND', (0, 1), (-1, -2), colors.HexColor("#F4F6F7")),
                                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor("#BDC3C7")),
                                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                            ]))
                            elements.append(t_p)
                        else:
                            elements.append(Paragraph("Nessun costo di personale nel periodo selezionato.", styles['Normal']))
                        
                        elements.append(Spacer(1, 20))
                        
                        # Totale Materiale
                        tot_mat = df_mat['Importo'].sum()
                        elements.append(Paragraph(f"<b>2. Costi Materiale</b>", styles['Heading2']))
                        elements.append(Spacer(1, 5))
                        
                        if not df_mat.empty:
                            data_rows_m = [["Tipo", "Data", "Cantiere", "Descrizione", "Importo (€)"]]
                            for _, row in df_mat.iterrows():
                                data_rows_m.append([
                                    row['Tipo'], 
                                    formatta_data_italiana(row['data']), 
                                    Paragraph(row['Cantiere'], style_cell), 
                                    Paragraph(row['Descrizione'], style_cell), 
                                    f"{row['Importo']:,.2f}"
                                ])
                            data_rows_m.append(["", "", "", "TOTALE MATERIALE", f"€ {tot_mat:,.2f}"])
                            
                            t_m = Table(data_rows_m, colWidths=[80, 70, 180, 200, 80], repeatRows=1)
                            t_m.setStyle(TableStyle([
                                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#34495E")),
                                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                                ('BACKGROUND', (0, 1), (-1, -2), colors.HexColor("#F4F6F7")),
                                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor("#BDC3C7")),
                                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                            ]))
                            elements.append(t_m)
                        else:
                            elements.append(Paragraph("Nessun costo di materiale nel periodo selezionato.", styles['Normal']))
                        
                        elements.append(Spacer(1, 20))
                        
                        # Totale Generale (solo Personale + Materiale)
                        totale_complessivo = tot_pers + tot_mat
                        elements.append(Paragraph(f"<b>TOTALE GENERALE (Personale + Materiale): € {totale_complessivo:,.2f}</b>", styles['Heading2']))
                    
                    else:
                        # Tabella unica per gli altri filtri
                        data_rows = [["Tipo", "Data", "Cantiere", "Descrizione", "Importo (€)"]]
                        for _, row in df_report.iterrows():
                            data_rows.append([
                                row['Tipo'], 
                                formatta_data_italiana(row['data']), 
                                Paragraph(row['Cantiere'], style_cell), 
                                Paragraph(row['Descrizione'], style_cell), 
                                f"{row['Importo']:,.2f}"
                            ])
                        data_rows.append(["", "", "", "TOTALE", f"€ {totale_importo:,.2f}"])
                        
                        t = Table(data_rows, colWidths=[80, 70, 180, 200, 80], repeatRows=1)
                        t.setStyle(TableStyle([
                            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
                            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                            ('BACKGROUND', (0, 1), (-1, -2), colors.HexColor("#F4F6F7")),
                            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor("#BDC3C7")),
                            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                        ]))
                        elements.append(t)
                    
                    doc.build(elements)
                    st.success(f"PDF generato con successo: {filename}")
                    
                    with open(filename, "rb") as f:
                        st.download_button(
                            label="⬇️ Scarica il PDF",
                            data=f,
                            file_name=filename,
                            mime="application/pdf"
                        )
                except Exception as e:
                    st.error(f"Errore durante la generazione del PDF: {e}")

    st.divider()

    # --- GRAFICI ESISTENTI ---
    st.subheader("📈 Andamento Economico")
    df_cantieri = pd.read_sql_query("SELECT id, indirizzo FROM preventivi", conn)
    
    if df_cantieri.empty:
        st.info("Nessun cantiere presente.")
        conn.close()
        return
        
    opzioni = ["--- TUTTI I CANTIERI ATTIVI ---"] + [f"{row['id']} - {row['indirizzo']}" for _, row in df_cantieri.iterrows()]
    scelta = st.selectbox("Seleziona Cantiere per il grafico:", opzioni, key="sel_riepilogo_grafico")
    
    if scelta == "--- TUTTI I CANTIERI ATTIVI ---":
        query_incassi = "SELECT i.data, i.imponibile as totale FROM incassi i JOIN preventivi p ON i.cantiere_id = p.id WHERE p.stato = 'Attivo'"
        query_costi_m = "SELECT c.data, c.totale FROM costo_manodopera c JOIN preventivi p ON c.cantiere_id = p.id WHERE p.stato = 'Attivo'"
        query_costi_mat = "SELECT c.data, c.imponibile as totale FROM costo_materiali c JOIN preventivi p ON c.cantiere_id = p.id WHERE p.stato = 'Attivo'"
        query_costi_amm = "SELECT data, importo as totale, 'Costo Amm' as Tipo FROM costo_amministrativo"
        
        df_inc = pd.read_sql_query(query_incassi, conn)
        df_man = pd.read_sql_query(query_costi_m, conn)
        df_mat = pd.read_sql_query(query_costi_mat, conn)
        df_amm = pd.read_sql_query(query_costi_amm, conn)
        
        if df_inc.empty and df_man.empty and df_mat.empty and df_amm.empty:
            st.info("Nessun dato economico disponibile.")
        else:
            df_inc['Tipo'] = 'Incasso'; df_man['Tipo'] = 'Costo Pers'; df_mat['Tipo'] = 'Costo Mat'
            all_movs = pd.concat([df_inc, df_man, df_mat, df_amm])
            
            if not all_movs.empty:
                all_movs['data'] = pd.to_datetime(all_movs['data'])
                all_movs = all_movs.sort_values('data')
                
                all_movs['Incassi Cum'] = all_movs.apply(lambda x: x['totale'] if x['Tipo'] == 'Incasso' else 0, axis=1).cumsum()
                all_movs['Costi Cum'] = all_movs.apply(lambda x: x['totale'] if 'Costo' in x['Tipo'] else 0, axis=1).cumsum()

                fig, ax = plt.subplots(figsize=(10, 4))
                ax.plot(all_movs['data'], all_movs['Incassi Cum'], label='Incassi (Imponibile)', color='green', marker='o', linewidth=2)
                ax.plot(all_movs['data'], all_movs['Costi Cum'], label='Costi', color='red', marker='x', linewidth=2)
                ax.set_title("Andamento Economico Globale")
                ax.legend(); ax.grid(True, linestyle='--', alpha=0.6)
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m/%Y'))
                plt.xticks(rotation=45); plt.tight_layout()
                st.pyplot(fig)
            else:
                st.info("Nessun dato disponibile.")
    else:
        cid = int(scelta.split(" - ")[0])
        
        query_dati = f"""
            SELECT 
                p.importo_contratto,
                (SELECT SUM(imponibile) FROM incassi WHERE cantiere_id = {cid}) as incassi,
                (SELECT SUM(totale) FROM costo_manodopera WHERE cantiere_id = {cid}) as costi_man,
                (SELECT SUM(imponibile) FROM costo_materiali WHERE cantiere_id = {cid}) as costi_mat
            FROM preventivi p WHERE p.id = {cid}
        """
        dati = pd.read_sql_query(query_dati, conn).iloc[0]
        
        importo_contratto = dati['importo_contratto'] or 0
        incassi_c = dati['incassi'] or 0
        costi_c = (dati['costi_man'] or 0) + (dati['costi_mat'] or 0)
        
        perc_avanz = (incassi_c / importo_contratto * 100) if importo_contratto > 0 else 0
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Contratto", f"€ {importo_contratto:,.2f}")
        col2.metric("Incassato (Imponibile)", f"€ {incassi_c:,.2f}")
        col3.metric("Costi", f"€ {costi_c:,.2f}", delta_color="inverse")
        col4.metric("Avanzamento", f"{perc_avanz:.1f}%")
        
        st.progress(min(perc_avanz / 100, 1.0))
        
        query_incassi = f"SELECT data, imponibile as totale, 'Incasso' as Tipo FROM incassi WHERE cantiere_id = {cid}"
        query_costi_m = f"SELECT data, totale, 'Costo Pers' as Tipo FROM costo_manodopera WHERE cantiere_id = {cid}"
        query_costi_mat = f"SELECT data, imponibile as totale, 'Costo Mat' as Tipo FROM costo_materiali WHERE cantiere_id = {cid}"
        
        all_movs = pd.read_sql_query(f"{query_incassi} UNION ALL {query_costi_m} UNION ALL {query_costi_mat}", conn)
        
        if not all_movs.empty:
            all_movs['data'] = pd.to_datetime(all_movs['data'])
            all_movs = all_movs.sort_values('data')
            
            all_movs['Incassi Cum'] = all_movs.apply(lambda x: x['totale'] if x['Tipo'] == 'Incasso' else 0, axis=1).cumsum()
            all_movs['Costi Cum'] = all_movs.apply(lambda x: x['totale'] if 'Costo' in x['Tipo'] else 0, axis=1).cumsum()

            fig, ax = plt.subplots(figsize=(10, 4))
            ax.plot(all_movs['data'], all_movs['Incassi Cum'], label='Incassi (Imponibile)', color='green', marker='o', linewidth=2)
            ax.plot(all_movs['data'], all_movs['Costi Cum'], label='Costi', color='red', marker='x', linewidth=2)
            ax.set_title(f"Andamento Economico: {scelta.split(' - ')[1]}")
            ax.legend(); ax.grid(True, linestyle='--', alpha=0.6)
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m/%Y'))
            plt.xticks(rotation=45); plt.tight_layout()
            st.pyplot(fig)
        else:
            st.info("Nessun movimento economico per questo cantiere.")

    conn.close()

# --- NAVIGAZIONE ---
if not st.session_state.logged_in:
    login_page()
else:
    with st.sidebar:
        st.markdown(f"### 👤 Utente: {st.session_state.username}")
        st.divider()
        if st.button("🏠 Home", use_container_width=True, key="sidebar_home"):
            st.session_state.current_page = "Home"; st.rerun()
        if st.button("📋 Cantieri", use_container_width=True, key="sidebar_cantieri"):
            st.session_state.current_page = "Cantieri"; st.rerun()
        if st.button("👥 Anagrafiche", use_container_width=True, key="sidebar_anagrafiche"):
            st.session_state.current_page = "Anagrafiche"; st.rerun()
        if st.button("📉 Costi", use_container_width=True, key="sidebar_costi"):
            st.session_state.current_page = "Costi"; st.rerun()
        if st.button("💰 Incassi", use_container_width=True, key="sidebar_incassi"):
            st.session_state.current_page = "Incassi"; st.rerun()
        if st.button("📈 Avanzamento", use_container_width=True, key="sidebar_avanzamento"):
            st.session_state.current_page = "Avanzamento"; st.rerun()
        if st.button("📊 Riepilogo", use_container_width=True, key="sidebar_riepilogo"):
            st.session_state.current_page = "Riepilogo"; st.rerun()
        
        if st.session_state.is_admin:
            if st.button("👤 Gestione Utenti", use_container_width=True, key="sidebar_utenti"):
                st.session_state.current_page = "Utenti"; st.rerun()
        
        st.divider()
        
        st.markdown("##### 💾 Sicurezza Dati")
        try:
            with open(DB_NAME, "rb") as f:
                st.download_button(
                    label="Scarica Backup Database",
                    data=f,
                    file_name=f"backup_gestionale_{datetime.date.today()}.db",
                    mime="application/octet-stream",
                    key="sidebar_backup_db",
                    use_container_width=True
                )
        except FileNotFoundError:
            st.caption("Nessun database da salvare.")
        
        st.divider()
        
        if st.button("🚪 Logout", type="primary", use_container_width=True, key="sidebar_logout"):
            st.session_state.logged_in = False; st.session_state.is_admin = False; st.rerun()

    if st.session_state.current_page == "Home": page_home()
    elif st.session_state.current_page == "Cantieri": page_cantieri()
    elif st.session_state.current_page == "Anagrafiche": page_anagrafiche()
    elif st.session_state.current_page == "Costi": page_costi()
    elif st.session_state.current_page == "Incassi": page_incassi()
    elif st.session_state.current_page == "Avanzamento": page_avanzamento()
    elif st.session_state.current_page == "Riepilogo": page_riepilogo()
    elif st.session_state.current_page == "Utenti" and st.session_state.is_admin: page_utenti()
