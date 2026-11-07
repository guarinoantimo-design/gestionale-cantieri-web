import streamlit as st
import sqlite3
import pandas as pd
import datetime
import hashlib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

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
    c.execute("CREATE TABLE IF NOT EXISTS incassi (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, cantiere_id INTEGER, fattura TEXT, imponibile REAL, iva REAL, totale REAL)")
    c.execute("CREATE TABLE IF NOT EXISTS avanzamento (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, cantiere_id INTEGER, descrizione TEXT, importo REAL)")
    
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
    st.write("Benvenuto nel Gestionale. Seleziona una sezione.")
    
    col1, col2 = st.columns(2)
    with col1:
        # Aggiunto 'key' univoco per evitare conflitti
        if st.button("📋 Gestione Cantieri", use_container_width=True, key="home_btn_cantieri"):
            st.session_state.current_page = "Cantieri"; st.rerun()
        if st.button("📉 Inserimento Costi", use_container_width=True, key="home_btn_costi"):
            st.session_state.current_page = "Costi"; st.rerun()
    with col2:
        if st.button("👥 Anagrafiche", use_container_width=True, key="home_btn_anagrafiche"):
            st.session_state.current_page = "Anagrafiche"; st.rerun()
        if st.button("💰 Incassi", use_container_width=True, key="home_btn_incassi"):
            st.session_state.current_page = "Incassi"; st.rerun()
        if st.button("📈 Avanzamento", use_container_width=True, key="home_btn_avanzamento"):
            st.session_state.current_page = "Avanzamento"; st.rerun()
        if st.button("📊 Riepilogo", use_container_width=True, key="home_btn_riepilogo"):
            st.session_state.current_page = "Riepilogo"; st.rerun()

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
                m_importo = st.number_input("Importo Contratto (€)", value=float(cantiere_data['importo_contratto']))
                
                if st.form_submit_button("Salva Modifiche"):
                    conn = get_connection(); c = conn.cursor()
                    c.execute("UPDATE preventivi SET cliente=?, indirizzo=?, importo_contratto=? WHERE id=?", 
                              (m_cliente, m_indirizzo, m_importo, cantiere_sel))
                    conn.commit(); conn.close(); st.success("Modifiche salvate!"); st.rerun()
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
        st.subheader("Registra Ore Lavorate")
        col1, col2 = st.columns(2)
        data_m = col1.date_input("Data", datetime.date.today(), key="data_manodopera")
        cantiere_m = col2.selectbox("Cantiere", cantieri['id'].tolist(), format_func=lambda x: cantieri[cantieri['id']==x]['indirizzo'].values[0], key="cant_manodopera")
        
        if not operai.empty:
            col3, col4 = st.columns(2)
            operaio_sel = col3.selectbox("Operaio", operai['nome'].tolist(), key="op_manodopera")
            costo_standard = operai[operai['nome'] == operaio_sel]['costo_orario'].values[0]
            
            costo_orario = col4.number_input("Costo Orario (€)", min_value=0.0, step=1.0, value=float(costo_standard), key="costo_orario")
            ore = st.number_input("Ore Lavorate", min_value=0.0, step=0.5, key="ore_lavorate")
            
            if st.button("Salva Costo Manodopera", type="primary", key="btn_salva_manodopera"):
                totale = ore * costo_orario
                conn = get_connection(); c = conn.cursor()
                c.execute("INSERT INTO costo_manodopera (data, cantiere_id, operaio, ore, costo_orario, totale) VALUES (?,?,?,?,?,?)", 
                          (str(data_m), cantiere_m, operaio_sel, ore, costo_orario, totale))
                conn.commit(); conn.close(); st.success("Costo manodopera registrato!"); st.rerun()
        else:
            st.info("Nessun operaio in anagrafica.")

    with tab2:
        with st.form("form_materiali", clear_on_submit=True):
            st.subheader("Registra Acquisto Materiale")
            col1, col2 = st.columns(2)
            data_mat = col1.date_input("Data", datetime.date.today(), key="data_materiale")
            cantiere_mat = col2.selectbox("Cantiere", cantieri['id'].tolist(), format_func=lambda x: cantieri[cantieri['id']==x]['indirizzo'].values[0], key="cant_materiale")
            
            if not fornitori.empty:
                col3, col4 = st.columns(2)
                fornitore_sel = col3.selectbox("Fornitore", fornitori['nome'].tolist(), key="fornitore_materiale")
                documento = col4.text_input("N. Documento / Fattura", key="documento_materiale")
                
                col5, col6 = st.columns(2)
                imponibile = col5.number_input("Imponibile (€)", min_value=0.0, step=10.0, key="imponibile")
                iva = col6.number_input("Aliquota IVA (%)", min_value=0.0, value=22.0, step=1.0, key="iva_materiale")
                
                if st.form_submit_button("Salva Costo Materiale"):
                    totale = imponibile + (imponibile * iva / 100)
                    conn = get_connection(); c = conn.cursor()
                    c.execute("INSERT INTO costo_materiali (data, cantiere_id, fornitore, documento, imponibile, iva, totale) VALUES (?,?,?,?,?,?,?)", 
                              (str(data_mat), cantiere_mat, fornitore_sel, documento, imponibile, iva, totale))
                    conn.commit(); conn.close(); st.success("Costo materiale registrato!"); st.rerun()
            else:
                st.info("Nessun fornitore in anagrafica.")

    st.divider()
    st.subheader("🛠️ Gestisci Costo Selezionato")
    
    conn = get_connection()
    query = """
        SELECT 'M-' || id as ID_Unico, 'Manodopera' as Tipo, data, (SELECT indirizzo FROM preventivi WHERE id = cantiere_id) as Cantiere, operaio as Descrizione, totale as Totale
        FROM costo_manodopera
        UNION ALL
        SELECT 'Mat-' || id as ID_Unico, 'Materiale' as Tipo, data, (SELECT indirizzo FROM preventivi WHERE id = cantiere_id) as Cantiere, fornitore as Descrizione, totale as Totale
        FROM costo_materiali
        ORDER BY data DESC
    """
    df_costi = pd.read_sql_query(query, conn)
    conn.close()
    
    df_costi.columns = [c.capitalize() for c in df_costi.columns]
    
    if not df_costi.empty:
        costi_list = [f"{row['Id_unico']} - {row['Data']} - {row['Descrizione']} - €{row['Totale']}" for _, row in df_costi.iterrows()]
        costo_sel_str = st.selectbox("Seleziona un costo da gestire:", costi_list, key="sel_costo_da_gestire")
        
        id_unico = costo_sel_str.split(" - ")[0]
        
        if id_unico.startswith("M-"):
            real_id = id_unico.replace("M-", "")
            conn = get_connection()
            df_specifico = pd.read_sql_query(f"SELECT * FROM costo_manodopera WHERE id={real_id}", conn)
            conn.close()
            row = df_specifico.iloc[0]
            
            with st.form("modifica_manodopera"):
                st.write("Dettagli Manodopera")
                col1, col2 = st.columns(2)
                m_data = col1.date_input("Data", pd.to_datetime(row['data']).date(), key="mod_data_man")
                m_ore = col2.number_input("Ore Lavorate", value=float(row['ore']), step=0.5, key="mod_ore_man")
                m_costo = st.number_input("Costo Orario (€)", value=float(row['costo_orario']), step=1.0, key="mod_costo_man")
                
                col_btn1, col_btn2 = st.columns(2)
                if col_btn1.form_submit_button("Salva Modifiche"):
                    tot = m_ore * m_costo
                    conn = get_connection(); c = conn.cursor()
                    c.execute("UPDATE costo_manodopera SET data=?, ore=?, costo_orario=?, totale=? WHERE id=?", 
                              (str(m_data), m_ore, m_costo, tot, real_id))
                    conn.commit(); conn.close(); st.success("Costo aggiornato!"); st.rerun()
                
                if col_btn2.form_submit_button("Elimina Costo", type="primary"):
                    conn = get_connection(); c = conn.cursor()
                    c.execute("DELETE FROM costo_manodopera WHERE id=?", (real_id,))
                    conn.commit(); conn.close(); st.success("Costo eliminato!"); st.rerun()

        else:
            real_id = id_unico.replace("Mat-", "")
            conn = get_connection()
            df_specifico = pd.read_sql_query(f"SELECT * FROM costo_materiali WHERE id={real_id}", conn)
            conn.close()
            row = df_specifico.iloc[0]
            
            with st.form("modifica_materiali"):
                st.write("Dettagli Materiale")
                col1, col2 = st.columns(2)
                m_data = col1.date_input("Data", pd.to_datetime(row['data']).date(), key="mod_data_mat")
                m_doc = col2.text_input("N. Documento", value=row['documento'], key="mod_doc_mat")
                
                col3, col4 = st.columns(2)
                m_imp = col3.number_input("Imponibile (€)", value=float(row['imponibile']), step=10.0, key="mod_imp_mat")
                m_iva = col4.number_input("Aliquota IVA (%)", value=float(row['iva']), step=1.0, key="mod_iva_mat")
                
                col_btn1, col_btn2 = st.columns(2)
                if col_btn1.form_submit_button("Salva Modifiche"):
                    tot = m_imp + (m_imp * m_iva / 100)
                    conn = get_connection(); c = conn.cursor()
                    c.execute("UPDATE costo_materiali SET data=?, documento=?, imponibile=?, iva=?, totale=? WHERE id=?", 
                              (str(m_data), m_doc, m_imp, m_iva, tot, real_id))
                    conn.commit(); conn.close(); st.success("Costo aggiornato!"); st.rerun()
                
                if col_btn2.form_submit_button("Elimina Costo", type="primary"):
                    conn = get_connection(); c = conn.cursor()
                    c.execute("DELETE FROM costo_materiali WHERE id=?", (real_id,))
                    conn.commit(); conn.close(); st.success("Costo eliminato!"); st.rerun()
    else:
        st.info("Nessun costo registrato finora.")

    st.divider()
    st.subheader("📋 Elenco Costi Registrati")
    st.dataframe(df_costi, use_container_width=True)

def page_incassi():
    st.title("💰 Gestione Incassi")
    cantieri = get_cantieri()
    if cantieri.empty:
        st.warning("Devi prima creare un cantiere!")
        return

    with st.expander("➕ Registra Nuovo Incasso"):
        with st.form("nuovo_incasso", clear_on_submit=True):
            col1, col2 = st.columns(2)
            data_i = col1.date_input("Data Fattura", datetime.date.today(), key="data_incasso")
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
    st.dataframe(df, use_container_width=True)

    if not df.empty:
        st.subheader("Elimina Incasso")
        incasso_sel = st.selectbox("Seleziona Incasso", df['id'].tolist(), format_func=lambda x: f"ID {x} - {df[df['id']==x]['fattura'].values[0]} - €{df[df['id']==x]['totale'].values[0]}", key="sel_incasso")
        if st.button("Elimina Incasso Selezionato", type="primary", key="btn_elimina_incasso"):
            conn = get_connection(); c = conn.cursor()
            c.execute("DELETE FROM incassi WHERE id=?", (incasso_sel,))
            conn.commit(); conn.close(); st.success("Incasso eliminato!"); st.rerun()

def page_avanzamento():
    st.title("📈 Avanzamento Lavori (SAL)")
    cantieri = get_cantieri()
    if cantieri.empty:
        st.warning("Devi prima creare un cantiere!")
        return

    with st.expander("➕ Registra Nuovo SAL"):
        with st.form("nuovo_sal", clear_on_submit=True):
            col1, col2 = st.columns(2)
            data_s = col1.date_input("Data SAL", datetime.date.today(), key="data_sal")
            cantiere_s = col2.selectbox("Cantiere", cantieri['id'].tolist(), format_func=lambda x: cantieri[cantieri['id']==x]['indirizzo'].values[0], key="cant_sal")
            
            descrizione = st.text_input("Descrizione Lavori", key="desc_sal")
            importo = st.number_input("Importo Realizzato (€)", min_value=0.0, step=100.0, key="imp_sal")
            
            if st.form_submit_button("Salva SAL"):
                conn = get_connection(); c = conn.cursor()
                c.execute("INSERT INTO avanzamento (data, cantiere_id, descrizione, importo) VALUES (?,?,?,?)", 
                          (str(data_s), cantiere_s, descrizione, importo))
                conn.commit(); conn.close(); st.success("SAL registrato!"); st.rerun()

    st.divider()
    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT a.id, a.data, p.indirizzo as Cantiere, a.descrizione, a.importo 
        FROM avanzamento a JOIN preventivi p ON a.cantiere_id = p.id
    """, conn)
    conn.close()
    st.dataframe(df, use_container_width=True)

def page_riepilogo():
    st.title("📊 Riepilogo e Grafici")
    
    conn = get_connection()
    
    query_totali = """
        SELECT 
            (SELECT SUM(importo_contratto) FROM preventivi WHERE stato = 'Attivo') as tot_contratti,
            (SELECT SUM(totale) FROM incassi i JOIN preventivi p ON i.cantiere_id = p.id WHERE p.stato = 'Attivo') as tot_incassi,
            (SELECT SUM(totale) FROM costo_manodopera c JOIN preventivi p ON c.cantiere_id = p.id WHERE p.stato = 'Attivo') as tot_costi_man,
            (SELECT SUM(totale) FROM costo_materiali c JOIN preventivi p ON c.cantiere_id = p.id WHERE p.stato = 'Attivo') as tot_costi_mat
    """
    res = pd.read_sql_query(query_totali, conn).iloc[0]
    
    tot_contratti = res['tot_contratti'] or 0
    tot_incassi = res['tot_incassi'] or 0
    tot_costi = (res['tot_costi_man'] or 0) + (res['tot_costi_mat'] or 0)
    saldo = tot_incassi - tot_costi

    st.markdown("### 🏢 Totali Aziendali (Solo Cantieri Attivi)")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Contratti", f"€ {tot_contratti:,.2f}")
    col2.metric("Incassi", f"€ {tot_incassi:,.2f}")
    col3.metric("Costi", f"€ {tot_costi:,.2f}", delta_color="inverse")
    col4.metric("Saldo", f"€ {saldo:,.2f}", delta_color="normal")
    
    st.divider()

    st.markdown("### 🔍 Dettaglio Cantiere")
    df_cantieri = pd.read_sql_query("SELECT id, indirizzo FROM preventivi", conn)
    
    if df_cantieri.empty:
        st.info("Nessun cantiere presente.")
        conn.close()
        return
        
    opzioni = ["--- TUTTI I CANTIERI ATTIVI ---"] + [f"{row['id']} - {row['indirizzo']}" for _, row in df_cantieri.iterrows()]
    scelta = st.selectbox("Seleziona Cantiere per il grafico:", opzioni, key="sel_riepilogo")
    
    if scelta == "--- TUTTI I CANTIERI ATTIVI ---":
        query_incassi = "SELECT i.data, i.totale FROM incassi i JOIN preventivi p ON i.cantiere_id = p.id WHERE p.stato = 'Attivo'"
        query_costi_m = "SELECT c.data, c.totale FROM costo_manodopera c JOIN preventivi p ON c.cantiere_id = p.id WHERE p.stato = 'Attivo'"
        query_costi_mat = "SELECT c.data, c.totale FROM costo_materiali c JOIN preventivi p ON c.cantiere_id = p.id WHERE p.stato = 'Attivo'"
        
        df_inc = pd.read_sql_query(query_incassi, conn)
        df_man = pd.read_sql_query(query_costi_m, conn)
        df_mat = pd.read_sql_query(query_costi_mat, conn)
        
        if df_inc.empty and df_man.empty and df_mat.empty:
            st.info("Nessun dato economico disponibile per i cantieri attivi.")
        else:
            df_inc['Tipo'] = 'Incasso'; df_man['Tipo'] = 'Costo Man'; df_mat['Tipo'] = 'Costo Mat'
            all_movs = pd.concat([df_inc, df_man, df_mat]).sort_values('data')
            
            if not all_movs.empty:
                all_movs['data'] = pd.to_datetime(all_movs['data'])
                all_movs['Incassi Cum'] = all_movs.apply(lambda x: x['totale'] if x['Tipo'] == 'Incasso' else 0, axis=1).cumsum()
                all_movs['Costi Cum'] = all_movs.apply(lambda x: x['totale'] if 'Costo' in x['Tipo'] else 0, axis=1).cumsum()

                fig, ax = plt.subplots(figsize=(10, 4))
                ax.plot(all_movs['data'], all_movs['Incassi Cum'], label='Incassi', color='green', marker='o', linewidth=2)
                ax.plot(all_movs['data'], all_movs['Costi Cum'], label='Costi', color='red', marker='x', linewidth=2)
                ax.set_title("Andamento Economico Globale (Cantieri Attivi)")
                ax.legend(); ax.grid(True, linestyle='--', alpha=0.6)
                plt.xticks(rotation=45); plt.tight_layout()
                st.pyplot(fig)
            else:
                st.info("Nessun dato disponibile.")
    else:
        cid = int(scelta.split(" - ")[0])
        
        query_dati = f"""
            SELECT 
                p.importo_contratto,
                (SELECT SUM(totale) FROM incassi WHERE cantiere_id = {cid}) as incassi,
                (SELECT SUM(totale) FROM costo_manodopera WHERE cantiere_id = {cid}) as costi_man,
                (SELECT SUM(totale) FROM costo_materiali WHERE cantiere_id = {cid}) as costi_mat,
                (SELECT SUM(importo) FROM avanzamento WHERE cantiere_id = {cid}) as avanzamento
            FROM preventivi p WHERE p.id = {cid}
        """
        dati = pd.read_sql_query(query_dati, conn).iloc[0]
        
        importo_contratto = dati['importo_contratto'] or 0
        incassi_c = dati['incassi'] or 0
        costi_c = (dati['costi_man'] or 0) + (dati['costi_mat'] or 0)
        avanz = dati['avanzamento'] or 0
        perc_avanz = (avanz / importo_contratto * 100) if importo_contratto > 0 else 0
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Contratto", f"€ {importo_contratto:,.2f}")
        col2.metric("Incassato", f"€ {incassi_c:,.2f}")
        col3.metric("Costi", f"€ {costi_c:,.2f}", delta_color="inverse")
        col4.metric("Avanzamento", f"{perc_avanz:.1f}%")
        
        st.progress(min(perc_avanz / 100, 1.0))
        
        query_incassi = f"SELECT data, totale, 'Incasso' as Tipo FROM incassi WHERE cantiere_id = {cid}"
        query_costi_m = f"SELECT data, totale, 'Costo Man' as Tipo FROM costo_manodopera WHERE cantiere_id = {cid}"
        query_costi_mat = f"SELECT data, totale, 'Costo Mat' as Tipo FROM costo_materiali WHERE cantiere_id = {cid}"
        
        all_movs = pd.read_sql_query(f"{query_incassi} UNION ALL {query_costi_m} UNION ALL {query_costi_mat} ORDER BY data", conn)
        
        if not all_movs.empty:
            all_movs['data'] = pd.to_datetime(all_movs['data'])
            all_movs['Incassi Cum'] = all_movs.apply(lambda x: x['totale'] if x['Tipo'] == 'Incasso' else 0, axis=1).cumsum()
            all_movs['Costi Cum'] = all_movs.apply(lambda x: x['totale'] if 'Costo' in x['Tipo'] else 0, axis=1).cumsum()

            fig, ax = plt.subplots(figsize=(10, 4))
            ax.plot(all_movs['data'], all_movs['Incassi Cum'], label='Incassi', color='green', marker='o', linewidth=2)
            ax.plot(all_movs['data'], all_movs['Costi Cum'], label='Costi', color='red', marker='x', linewidth=2)
            ax.set_title(f"Andamento Economico: {scelta.split(' - ')[1]}")
            ax.legend(); ax.grid(True, linestyle='--', alpha=0.6)
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
        
        st.divider()
        if st.button("🚪 Logout", type="primary", use_container_width=True, key="sidebar_logout"):
            st.session_state.logged_in = False; st.rerun()

    if st.session_state.current_page == "Home": page_home()
    elif st.session_state.current_page == "Cantieri": page_cantieri()
    elif st.session_state.current_page == "Anagrafiche": page_anagrafiche()
    elif st.session_state.current_page == "Costi": page_costi()
    elif st.session_state.current_page == "Incassi": page_incassi()
    elif st.session_state.current_page == "Avanzamento": page_avanzamento()
    elif st.session_state.current_page == "Riepilogo": page_riepilogo()

