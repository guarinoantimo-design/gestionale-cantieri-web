import streamlit as st
import pandas as pd
import datetime
import hashlib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import io

# Librerie per il PDF con gestione testo
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# Nuova libreria per Supabase
from st_supabase_connection import SupabaseConnection

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Gestionale Cantieri", page_icon="🏗️", layout="wide")

# --- CONNESSIONE DATABASE (SUPABASE) ---
conn = st.connection("supabase", type=SupabaseConnection)
supabase = conn.client

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
    try:
        response = supabase.table("users").select("password_hash, is_admin").eq("username", username).execute()
        if response.data:
            user = response.data[0]
            hashed_pw = hashlib.sha256(password.encode()).hexdigest()
            if user['password_hash'] == hashed_pw:
                return (username, user['is_admin'])
        return None
    except Exception as e:
        st.error(f"Errore di connessione: {e}")
        return None

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
                    st.session_state.is_admin = user[1]
                    st.rerun()
                else:
                    st.error("Credenziali non valide.")

# --- FUNZIONI DI SUPPORTO ---
def get_cantieri():
    response = supabase.table("preventivi").select("id, indirizzo").execute()
    return pd.DataFrame(response.data)

def get_operai():
    response = supabase.table("operai").select("*").execute()
    return pd.DataFrame(response.data)

def get_fornitori():
    response = supabase.table("fornitori").select("*").execute()
    return pd.DataFrame(response.data)

def calcola_quote_amministrative(data_inizio, data_fine, includi_esterne=True):
    res_amm = supabase.table("costo_amministrativo").select("importo").gte("data", str(data_inizio)).lte("data", str(data_fine)).execute()
    tot_amm = sum(float(item['importo'] or 0) for item in res_amm.data)
    
    res_man = supabase.table("costo_manodopera").select("cantiere_id, ore, operaio").gte("data", str(data_inizio)).lte("data", str(data_fine)).execute()
    df_ore = pd.DataFrame(res_man.data)
    
    if df_ore.empty:
        return {'quote': {}, 'tot_amm': tot_amm, 'tot_amm_ripartito': 0, 'tot_ore': 0, 'ore_per_cantiere': {}}

    if not includi_esterne:
        res_operai = supabase.table("operai").select("nome").eq("tipo", "Interno").execute()
        operai_interni = [o['nome'] for o in res_operai.data]
        df_ore = df_ore[df_ore['operaio'].isin(operai_interni)]
    
    if df_ore.empty:
         return {'quote': {}, 'tot_amm': tot_amm, 'tot_amm_ripartito': 0, 'tot_ore': 0, 'ore_per_cantiere': {}}

    df_ore['ore'] = pd.to_numeric(df_ore['ore'], errors='coerce').fillna(0)
    ore_grouped = df_ore.groupby('cantiere_id')['ore'].sum().to_dict()
    ore_per_cantiere = {int(k): float(v) for k, v in ore_grouped.items()}
    tot_ore = sum(ore_per_cantiere.values())
    
    quote = {}
    if tot_ore > 0 and tot_amm > 0:
        somma_quote = 0.0
        lista_items = list(ore_per_cantiere.items())
        for i, (cid, ore) in enumerate(lista_items):
            if i < len(lista_items) - 1:
                quota = round(tot_amm * (ore / tot_ore), 2)
                quote[cid] = quota
                somma_quote += quota
            else:
                quote[cid] = round(tot_amm - somma_quote, 2)
                
    return {
        'quote': quote,
        'tot_amm': tot_amm,
        'tot_amm_ripartito': sum(quote.values()),
        'tot_ore': tot_ore,
        'ore_per_cantiere': ore_per_cantiere
    }

# --- PAGINE ---
def page_home():
    st.title("🏠 Home")
    st.write("GESTIONE CANTIERE. Situazione attualizzata.")
    try:
        res_cant = supabase.table("preventivi").select("id", count="exact").eq("stato", "Attivo").execute()
        num_cantieri = res_cant.count if res_cant.count else 0
        
        res_inc = supabase.table("incassi").select("imponibile, cantiere_id").execute()
        res_man = supabase.table("costo_manodopera").select("totale, cantiere_id").execute()
        res_mat = supabase.table("costo_materiali").select("imponibile, cantiere_id").execute()
        res_amm = supabase.table("costo_amministrativo").select("importo").execute()
        res_prev = supabase.table("preventivi").select("id").eq("stato", "Attivo").execute()
        
        attivi = [p['id'] for p in res_prev.data]
        
        tot_incassi = sum(float(i['imponibile'] or 0) for i in res_inc.data if i['cantiere_id'] in attivi)
        tot_costi_pers = sum(float(c['totale'] or 0) for c in res_man.data if c['cantiere_id'] in attivi)
        tot_costi_mat = sum(float(c['imponibile'] or 0) for c in res_mat.data if c['cantiere_id'] in attivi)
        tot_costi_amm = sum(float(c['importo'] or 0) for c in res_amm.data)
        
        tot_costi = tot_costi_pers + tot_costi_mat + tot_costi_amm
        saldo = tot_incassi - tot_costi
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric(label="🏗️ Cantieri Attivi", value=num_cantieri)
        col2.metric(label="💰 Incassi (Imponibile)", value=f"€ {tot_incassi:,.2f}")
        col3.metric(label="📉 Costi Totali", value=f"€ {tot_costi:,.2f}", delta_color="inverse")
        col4.metric(label="⚖️ Saldo", value=f"€ {saldo:,.2f}", delta_color="normal" if saldo >= 0 else "inverse")
    except Exception as e:
        st.error(f"Errore caricamento dati: {e}")

    st.divider()
    st.subheader("🚀 Accessi Rapidi")
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("📋 Inserisci Cantieri", use_container_width=True, key="home_btn_cantieri"): st.session_state.current_page = "Cantieri"; st.rerun()
        if st.button("📉 Inserisci Costi", use_container_width=True, key="home_btn_costi"): st.session_state.current_page = "Costi"; st.rerun()
        if st.button("📈 Avanzamento Cantieri", use_container_width=True, key="home_btn_avanzamento"): st.session_state.current_page = "Avanzamento"; st.rerun()
    with col_btn2:
        if st.button("👥 Anagrafica", use_container_width=True, key="home_btn_anagrafiche"): st.session_state.current_page = "Anagrafiche"; st.rerun()
        if st.button("💰 Incassi", use_container_width=True, key="home_btn_incassi"): st.session_state.current_page = "Incassi"; st.rerun()
        if st.button("📊 Riepilogo", use_container_width=True, key="home_btn_riepilogo"): st.session_state.current_page = "Riepilogo"; st.rerun()

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
                    data_dict = {"data": str(data), "n_prev": n_prev, "cliente": cliente, "indirizzo": indirizzo, "piva": piva, "descrizione": descrizione, "importo_prev": importo_prev, "importo_contratto": importo_contratto, "stato": "Attivo"}
                    supabase.table("preventivi").insert(data_dict).execute()
                    st.success("Cantiere inserito!"); st.rerun()
                else:
                    st.error("Cliente e Indirizzo sono obbligatori.")

    st.divider()
    try:
        res = supabase.table("preventivi").select("*").execute()
        df = pd.DataFrame(res.data)
    except Exception as e:
        st.error(f"Errore: {e}")
        return
    
    if not df.empty:
        df_display = df.copy()
        if 'data' in df_display.columns:
            df_display['data'] = df_display['data'].apply(formatta_data_italiana)
        st.dataframe(df_display, use_container_width=True)
        
        st.subheader("Gestisci Cantiere Selezionato")
        cantiere_sel = st.selectbox("Seleziona Cantiere:", df['id'].tolist(), format_func=lambda x: f"ID {x} - {df[df['id']==x]['indirizzo'].values[0]}", key="sel_cantiere")
        cantiere_data = df[df['id'] == cantiere_sel].iloc[0]
        
        col_az1, col_az2 = st.columns(2)
        if cantiere_data.get('stato', 'Attivo') == 'Attivo':
            if col_az1.button("🔴 Chiudi Cantiere", use_container_width=True, key="btn_chiudi_cant"):
                supabase.table("preventivi").update({"stato": "Chiuso"}).eq("id", cantiere_sel).execute(); st.rerun()
        else:
            if col_az1.button("🟢 Riapri Cantiere", use_container_width=True, key="btn_riapri_cant"):
                supabase.table("preventivi").update({"stato": "Attivo"}).eq("id", cantiere_sel).execute(); st.rerun()
        
        with col_az2:
            if st.button("🗑️ Elimina Cantiere", type="primary", use_container_width=True, key="btn_elimina_cant"):
                st.session_state.confirm_delete_cantiere = True
        
        if st.session_state.get('confirm_delete_cantiere'):
            st.warning("Sei sicuro? Questa azione è irreversibile.")
            if st.button("Sì, elimina definitivamente", key="btn_conferma_elimina_cant"):
                supabase.table("preventivi").delete().eq("id", cantiere_sel).execute()
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
                    update_dict = {"cliente": m_cliente, "indirizzo": m_indirizzo, "descrizione": m_descrizione, "importo_prev": m_importo_prev, "importo_contratto": m_importo}
                    supabase.table("preventivi").update(update_dict).eq("id", cantiere_sel).execute()
                    st.success("Modifiche salvate!"); st.rerun()
    else:
        st.info("Nessun cantiere presente.")

def page_anagrafiche():
    st.title("👥 Anagrafiche Operai, Fornitori e Categorie Spese")
    tab1, tab2, tab3 = st.tabs(["Operai", "Fornitori", "Categorie Amministrative"])
    
    with tab1:
        filtro_tipo_operaio = st.radio("Filtra per tipo:", ["Tutti", "Interno", "Esterno"], horizontal=True, key="filtro_tipo_operaio")
        with st.expander("➕ Nuovo Operaio"):
            with st.form("nuovo_operaio", clear_on_submit=True):
                nome = st.text_input("Nome Operaio")
                ruolo = st.text_input("Ruolo")
                tipo = st.selectbox("Tipo", ["Interno", "Esterno"])
                costo = st.number_input("Costo Orario (€)", min_value=0.0, step=1.0)
                if st.form_submit_button("Salva Operaio"):
                    if nome:
                        supabase.table("operai").insert({"nome": nome, "ruolo": ruolo, "costo_orario": costo, "tipo": tipo}).execute()
                        st.success("Operaio aggiunto!"); st.rerun()
        
        try:
            res = supabase.table("operai").select("*").execute()
            df_op = pd.DataFrame(res.data)
            if not df_op.empty and filtro_tipo_operaio != "Tutti":
                df_op = df_op[df_op['tipo'] == filtro_tipo_operaio]
        except: df_op = pd.DataFrame()
            
        if not df_op.empty:
            st.dataframe(df_op.rename(columns={'id': 'ID', 'nome': 'Nome', 'ruolo': 'Ruolo', 'costo_orario': 'Costo Orario', 'tipo': 'Tipo'}), use_container_width=True)
            st.subheader("Gestisci Operaio")
            op_sel = st.selectbox("Seleziona Operaio", df_op['nome'].tolist(), key="sel_operaio")
            op_data = df_op[df_op['nome'] == op_sel].iloc[0]
            col1, col2 = st.columns(2)
            with col1:
                with st.form("modifica_operaio"):
                    new_nome = st.text_input("Nome", value=op_data['nome'])
                    new_ruolo = st.text_input("Ruolo", value=op_data['ruolo'])
                    new_tipo = st.selectbox("Tipo", ["Interno", "Esterno"], index=0 if op_data['tipo'] == "Interno" else 1)
                    new_costo = st.number_input("Costo Orario (€)", value=float(op_data['costo_orario']))
                    if st.form_submit_button("Salva Modifiche"):
                        supabase.table("operai").update({"nome": new_nome, "ruolo": new_ruolo, "costo_orario": new_costo, "tipo": new_tipo}).eq("nome", op_sel).execute()
                        st.success("Modifiche salvate!"); st.rerun()
            with col2:
                if st.button("Elimina Operaio", type="primary", key="btn_elimina_operaio"):
                    supabase.table("operai").delete().eq("nome", op_sel).execute()
                    st.success("Operaio eliminato!"); st.rerun()
        else:
            st.info("Nessun operaio trovato.")

    with tab2:
        with st.expander("➕ Nuovo Fornitore"):
            with st.form("nuovo_fornitore", clear_on_submit=True):
                nome_f = st.text_input("Nome Fornitore")
                piva_f = st.text_input("P.IVA")
                contatto = st.text_input("Contatto")
                if st.form_submit_button("Salva Fornitore"):
                    if nome_f:
                        supabase.table("fornitori").insert({"nome": nome_f, "piva": piva_f, "contatto": contatto}).execute()
                        st.success("Fornitore aggiunto!"); st.rerun()
        
        try:
            res = supabase.table("fornitori").select("*").execute()
            df_forn = pd.DataFrame(res.data)
        except: df_forn = pd.DataFrame()
            
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
                        supabase.table("fornitori").update({"piva": new_piva, "contatto": new_contatto}).eq("nome", forn_sel).execute()
                        st.success("Modifiche salvate!"); st.rerun()
            with col2:
                if st.button("Elimina Fornitore", type="primary", key="btn_elimina_fornitore"):
                    supabase.table("fornitori").delete().eq("nome", forn_sel).execute()
                    st.success("Fornitore eliminato!"); st.rerun()

    with tab3:
        with st.expander("➕ Nuova Categoria di Spesa"):
            with st.form("nuova_categoria", clear_on_submit=True):
                nome_cat = st.text_input("Nome Categoria (es. Commercialista, Elettricità)")
                if st.form_submit_button("Salva Categoria"):
                    if nome_cat:
                        try:
                            supabase.table("categorie_amministrative").insert({"nome": nome_cat}).execute()
                            st.success("Categoria aggiunta!")
                        except: st.error("Questa categoria esiste già.")
                        st.rerun()
        
        try:
            res = supabase.table("categorie_amministrative").select("*").execute()
            df_cat = pd.DataFrame(res.data)
        except: df_cat = pd.DataFrame()
            
        st.dataframe(df_cat, use_container_width=True)
        if not df_cat.empty:
            st.subheader("Gestisci Categoria")
            cat_sel = st.selectbox("Seleziona Categoria", df_cat['nome'].tolist(), key="sel_categoria")
            col1, col2 = st.columns(2)
            with col1:
                with st.form("modifica_categoria"):
                    new_nome = st.text_input("Nuovo Nome", value=cat_sel)
                    if st.form_submit_button("Rinomina"):
                        supabase.table("categorie_amministrative").update({"nome": new_nome}).eq("nome", cat_sel).execute()
                        st.success("Categoria rinominata!"); st.rerun()
            with col2:
                if st.button("Elimina Categoria", type="primary", key="btn_elimina_categoria"):
                    supabase.table("categorie_amministrative").delete().eq("nome", cat_sel).execute()
                    st.success("Categoria eliminata!"); st.rerun()

def page_utenti():
    st.title("👤 Gestione Utenti")
    with st.expander("➕ Nuovo Utente"):
        with st.form("nuovo_utente", clear_on_submit=True):
            col1, col2 = st.columns(2)
            new_user = col1.text_input("Username")
            new_pass = col2.text_input("Password", type="password")
            is_admin_new = st.checkbox("Rendi questo utente Amministratore")
            if st.form_submit_button("Crea Utente"):
                if new_user and new_pass:
                    hashed_pw = hashlib.sha256(new_pass.encode()).hexdigest()
                    try:
                        supabase.table("users").insert({"username": new_user, "password_hash": hashed_pw, "is_admin": is_admin_new}).execute()
                        st.success(f"Utente '{new_user}' creato con successo!")
                    except: st.error("Questo username esiste già.")
                else: st.error("Username e Password sono obbligatori.")
    
    st.subheader("👥 Utenti Registrati")
    try:
        res = supabase.table("users").select("username, is_admin").execute()
        df_users = pd.DataFrame(res.data)
    except: df_users = pd.DataFrame()
    
    if not df_users.empty:
        df_users_disp = df_users.copy()
        df_users_disp['is_admin'] = df_users_disp['is_admin'].apply(lambda x: "Sì" if x else "No")
        st.dataframe(df_users_disp.rename(columns={'username': 'Username', 'is_admin': 'Amministratore'}), use_container_width=True)
        
        st.subheader("Gestisci Utente")
        user_sel = st.selectbox("Seleziona Utente", df_users['username'].tolist(), key="sel_user_gest")
        
        if user_sel == "admin":
            st.info("L'utente 'admin' è l'amministratore principale e non può essere modificato o eliminato.")
        else:
            col1, col2 = st.columns(2)
            with col1:
                with st.form("modifica_utente"):
                    new_password = st.text_input("Nuova Password (lascia vuoto per non cambiare)", type="password")
                    new_admin_status = st.checkbox("Amministratore")
                    if st.form_submit_button("Aggiorna Utente"):
                        update_data = {"is_admin": new_admin_status}
                        if new_password: update_data["password_hash"] = hashlib.sha256(new_password.encode()).hexdigest()
                        supabase.table("users").update(update_data).eq("username", user_sel).execute()
                        st.success("Utente aggiornato!"); st.rerun()
            with col2:
                if st.button("Elimina Utente", type="primary", key="btn_elimina_utente"):
                    supabase.table("users").delete().eq("username", user_sel).execute()
                    st.success("Utente eliminato!"); st.rerun()

def page_costi():
    st.title("📉 Inserimento Costi")
    try:
        df_cantieri = get_cantieri()
        df_operai = get_operai()
        df_fornitori = get_fornitori()
    except:
        st.error("Errore di connessione al database.")
        return
    if df_cantieri.empty:
        st.warning("Devi prima creare un cantiere!")
        return

    if "modifica_costo_attiva" not in st.session_state: st.session_state.modifica_costo_attiva = False
    if "costo_da_modificare" not in st.session_state: st.session_state.costo_da_modificare = None

    tab1, tab2, tab3 = st.tabs(["Costo Personale", "Costo Materiale", "Costo Amministrativo"])
    
    with tab1:
        st.subheader("Registra Ore Lavorate")
        col1, col2 = st.columns(2)
        data_m = col1.date_input("Data", datetime.date.today(), format="DD/MM/YYYY", key="data_manodopera")
        cantiere_m = col2.selectbox("Cantiere", df_cantieri['id'].tolist(), format_func=lambda x: df_cantieri[df_cantieri['id']==x]['indirizzo'].values[0], key="cant_manodopera")
        
        if not df_operai.empty:
            col3, col4 = st.columns(2)
            lista_nomi_operai = df_operai['nome'].tolist()
            operaio_sel = col3.selectbox("Operaio", lista_nomi_operai, key="op_manodopera")
            
            if operaio_sel:
                match_operaio = df_operai[df_operai['nome'] == operaio_sel]
                if not match_operaio.empty:
                    costo_standard = match_operaio['costo_orario'].values[0]
                    costo_orario = col4.number_input("Costo Orario (€)", min_value=0.0, step=1.0, value=float(costo_standard), key=f"costo_orario_{operaio_sel}")
                else:
                    costo_orario = col4.number_input("Costo Orario (€)", min_value=0.0, step=1.0, value=0.0, key="costo_orario_vuoto")
                    
                ore = st.number_input("Ore Lavorate", min_value=0.0, step=0.5, key="ore_lavorate")
                descrizione_lavori = st.text_input("Descrizione Lavori Eseguiti", key="desc_lavori")
                
                if st.button("Salva Costo Personale", type="primary", key="btn_salva_manodopera"):
                    if ore > 0:
                        totale = float(ore) * float(costo_orario)
                        data_formattata = data_m.strftime('%Y-%m-%d')
                        
                        dati_da_salvare = {
                            "data": data_formattata, 
                            "cantiere_id": int(cantiere_m), 
                            "operaio": str(operaio_sel), 
                            "descrizione": str(descrizione_lavori) if descrizione_lavori else "", 
                            "ore": round(float(ore), 2), 
                            "costo_orario": round(float(costo_orario), 2), 
                            "totale": round(totale, 2)
                        }
                        try:
                            supabase.table("costo_manodopera").insert(dati_da_salvare).execute()
                            st.success("Costo personale registrato!"); st.rerun()
                        except Exception as e:
                            st.error(f"Errore durante il salvataggio: {e}")
                            st.write("Dati inviati al database:", dati_da_salvare)
                    else:
                        st.error("Inserisci almeno un'ora.")
        else: 
            st.info("Nessun operaio in anagrafica. Aggiungine uno dalla pagina 'Anagrafiche'.")

    with tab2:
        with st.form("form_materiali", clear_on_submit=True):
            st.subheader("Registra Acquisto Materiale")
            col1, col2 = st.columns(2)
            data_mat = col1.date_input("Data", datetime.date.today(), format="DD/MM/YYYY", key="data_materiale")
            cantiere_mat = col2.selectbox("Cantiere", df_cantieri['id'].tolist(), format_func=lambda x: df_cantieri[df_cantieri['id']==x]['indirizzo'].values[0], key="cant_materiale")
            if not df_fornitori.empty:
                col3, col4 = st.columns(2)
                fornitore_sel = col3.selectbox("Fornitore", df_fornitori['nome'].tolist(), key="fornitore_materiale")
                documento = col4.text_input("N. Documento / Fattura", key="documento_materiale")
                col5, col6 = st.columns(2)
                imponibile = col5.number_input("Imponibile (€)", min_value=0.0, step=10.0, key="imponibile")
                iva = col6.number_input("Aliquota IVA (%)", min_value=0.0, value=22.0, step=1.0, key="iva_materiale")
            else:
                st.info("Nessun fornitore in anagrafica.")
                fornitore_sel = None
            if st.form_submit_button("Salva Costo Materiale"):
                if fornitore_sel:
                    totale = imponibile + (imponibile * iva / 100)
                    data_formattata = data_mat.strftime('%Y-%m-%d')
                    supabase.table("costo_materiali").insert({"data": data_formattata, "cantiere_id": cantiere_mat, "fornitore": fornitore_sel, "documento": documento, "imponibile": imponibile, "iva": iva, "totale": totale}).execute()
                    st.success("Costo materiale registrato!"); st.rerun()

    with tab3:
        st.subheader("Registra Costo Amministrativo")
        try:
            res_cat = supabase.table("categorie_amministrative").select("nome").execute()
            df_cat = pd.DataFrame(res_cat.data)
        except: df_cat = pd.DataFrame()
        with st.form("form_amministrativo", clear_on_submit=True):
            col1, col2 = st.columns(2)
            data_amm = col1.date_input("Data", datetime.date.today(), format="DD/MM/YYYY", key="data_amm")
            if not df_cat.empty:
                desc_amm = col2.selectbox("Categoria Spesa", df_cat['nome'].tolist(), key="desc_amm")
            else:
                st.warning("Nessuna categoria disponibile.")
                desc_amm = None
            importo_amm = st.number_input("Importo (€)", min_value=0.0, step=10.0, key="importo_amm")
            if st.form_submit_button("Salva Costo Amministrativo"):
                if desc_amm and importo_amm > 0:
                    data_formattata = data_amm.strftime('%Y-%m-%d')
                    supabase.table("costo_amministrativo").insert({"data": data_formattata, "descrizione": desc_amm, "importo": importo_amm}).execute()
                    st.success("Costo amministrativo registrato!"); st.rerun()

    st.divider()

    if st.session_state.modifica_costo_attiva and st.session_state.costo_da_modificare:
        id_unico = st.session_state.costo_da_modificare
        tipo_costo = id_unico.split("-")[0]
        real_id = int(id_unico.split("-")[1])
        with st.container():
            st.subheader(f"✏️ Modifica Costo ID: {real_id}")
            if tipo_costo == "M":
                res = supabase.table("costo_manodopera").select("*").eq("id", real_id).execute()
                if res.data:
                    row = res.data[0]
                    with st.form("mod_man"):
                        m_ore = st.number_input("Ore", value=float(row['ore']))
                        m_costo = st.number_input("Costo Orario", value=float(row['costo_orario']))
                        m_desc = st.text_input("Descrizione", value=row['descrizione'] or "")
                        if st.form_submit_button("Salva"):
                            supabase.table("costo_manodopera").update({"ore": m_ore, "costo_orario": m_costo, "descrizione": m_desc, "totale": m_ore*m_costo}).eq("id", real_id).execute()
                            st.session_state.modifica_costo_attiva = False; st.rerun()
                        if st.form_submit_button("Elimina"):
                            supabase.table("costo_manodopera").delete().eq("id", real_id).execute()
                            st.session_state.modifica_costo_attiva = False; st.rerun()
            elif tipo_costo == "Mat":
                res = supabase.table("costo_materiali").select("*").eq("id", real_id).execute()
                if res.data:
                    row = res.data[0]
                    with st.form("mod_mat"):
                        m_imp = st.number_input("Imponibile", value=float(row['imponibile']))
                        m_iva = st.number_input("IVA %", value=float(row['iva']))
                        if st.form_submit_button("Salva"):
                            tot = m_imp + (m_imp*m_iva/100)
                            supabase.table("costo_materiali").update({"imponibile": m_imp, "iva": m_iva, "totale": tot}).eq("id", real_id).execute()
                            st.session_state.modifica_costo_attiva = False; st.rerun()
                        if st.form_submit_button("Elimina"):
                            supabase.table("costo_materiali").delete().eq("id", real_id).execute()
                            st.session_state.modifica_costo_attiva = False; st.rerun()
            elif tipo_costo == "Amm":
                res = supabase.table("costo_amministrativo").select("*").eq("id", real_id).execute()
                if res.data:
                    row = res.data[0]
                    with st.form("mod_amm"):
                        m_imp = st.number_input("Importo", value=float(row['importo']))
                        if st.form_submit_button("Salva"):
                            supabase.table("costo_amministrativo").update({"importo": m_imp}).eq("id", real_id).execute()
                            st.session_state.modifica_costo_attiva = False; st.rerun()
                        if st.form_submit_button("Elimina"):
                            supabase.table("costo_amministrativo").delete().eq("id", real_id).execute()
                            st.session_state.modifica_costo_attiva = False; st.rerun()
            if st.button("Annulla Modifica"): st.session_state.modifica_costo_attiva = False; st.session_state.costo_da_modificare = None; st.rerun()
        st.divider()

    st.subheader("📋 Elenco Costi Registrati")
    with st.expander("🔍 Filtra i costi", expanded=True):
        col_f1, col_f2, col_f3, col_f4 = st.columns(4)
        filtro_testo = col_f1.text_input("Cerca", placeholder="Scrivi qui...")
        filtro_tipo = col_f2.selectbox("Tipo", ["Tutti", "Personale", "Materiale", "Amministrativo"])
        data_inizio = col_f3.date_input("Dal", value=datetime.date.today().replace(month=1, day=1), format="DD/MM/YYYY")
        data_fine = col_f4.date_input("Al", value=datetime.date.today(), format="DD/MM/YYYY")

    costi_list = []
    try:
        if filtro_tipo in ["Tutti", "Personale"]:
            res = supabase.table("costo_manodopera").select("*").gte("data", str(data_inizio)).lte("data", str(data_fine)).execute()
            for r in res.data: costi_list.append({"ID_Unico": f"M-{r['id']}", "Tipo": "Personale", "Data": r['data'], "Cantiere": r['cantiere_id'], "Descrizione": r['operaio'] + " " + (r['descrizione'] or ""), "Totale": r['totale']})
        if filtro_tipo in ["Tutti", "Materiale"]:
            res = supabase.table("costo_materiali").select("*").gte("data", str(data_inizio)).lte("data", str(data_fine)).execute()
            for r in res.data: costi_list.append({"ID_Unico": f"Mat-{r['id']}", "Tipo": "Materiale", "Data": r['data'], "Cantiere": r['cantiere_id'], "Descrizione": r['fornitore'], "Totale": r['imponibile']})
        if filtro_tipo in ["Tutti", "Amministrativo"]:
            res = supabase.table("costo_amministrativo").select("*").gte("data", str(data_inizio)).lte("data", str(data_fine)).execute()
            for r in res.data: costi_list.append({"ID_Unico": f"Amm-{r['id']}", "Tipo": "Amministrativo", "Data": r['data'], "Cantiere": "Generale", "Descrizione": r['descrizione'], "Totale": r['importo']})
    except Exception as e:
        st.error(f"Errore caricamento costi: {e}")

    if not costi_list:
        st.info("Nessun costo trovato.")
    else:
        df_costi = pd.DataFrame(costi_list).sort_values("Data", ascending=False)
        cant_map = {r['id']: r['indirizzo'] for r in df_cantieri.to_dict('records')}
        df_costi['Cantiere'] = df_costi['Cantiere'].apply(lambda x: cant_map.get(x, x) if isinstance(x, int) else x)
        
        if filtro_testo:
            mask = (df_costi['Cantiere'].astype(str).str.contains(filtro_testo, case=False, na=False) | df_costi['Descrizione'].astype(str).str.contains(filtro_testo, case=False, na=False))
            df_costi = df_costi[mask]

        if df_costi.empty:
            st.info("Nessun costo trovato con questi filtri.")
        else:
            for index, row in df_costi.iterrows():
                col_dati, col_btn = st.columns([8, 2])
                with col_dati: st.markdown(f"**{row['Tipo']}** | {formatta_data_italiana(row['Data'])} | {row['Cantiere']} | {row['Descrizione']} | **€ {row['Totale']:,.2f}**")
                with col_btn:
                    if st.button("✏️ Modifica", key=f"mod_{row['ID_Unico']}"):
                        st.session_state.modifica_costo_attiva = True; st.session_state.costo_da_modificare = row['ID_Unico']; st.rerun()
            
            st.divider()
            totale_filtrato = df_costi['Totale'].sum()
            st.markdown(f"### Totale dei costi filtrati: **€ {totale_filtrato:,.2f}**")
            
            if st.button("📄 Esporta Risultati in PDF", type="primary", key="btn_export_pdf_costi"):
                try:
                    filename = f"Riepilogo_Costi_{datetime.date.today()}.pdf"
                    doc = SimpleDocTemplate(filename, pagesize=landscape(A4))
                    elements = []
                    styles = getSampleStyleSheet()
                    style_cell = ParagraphStyle('cell_style', parent=styles['Normal'], fontSize=8, leading=10, alignment=0)
                    
                    elements.append(Paragraph(f"Report Personalizzato dal {formatta_data_italiana(s_data_ini)} al {formatta_data_italiana(s_data_fin)}", styles['Title']))
                    elements.append(Paragraph(f"<b>Cantiere:</b> {s_cantiere}", styles['Heading3']))
                    elements.append(Paragraph(f"<b>Tipologia Costo:</b> {s_tipo}", styles['Normal']))
                    elements.append(Spacer(1, 12))
                    
                    data_rows = [["Tipo", "Data", "Cantiere", "Descrizione", "Totale (€)"]]
                    for _, row in df_costi.iterrows():
                        data_rows.append([row['Tipo'], formatta_data_italiana(row['Data']), Paragraph(row['Cantiere'], style_cell), Paragraph(row['Descrizione'], style_cell), f"{row['Totale']:,.2f}"])
                    data_rows.append(["", "", "", "TOTALE GENERALE", f"{totale_filtrato:,.2f}"])
                    
                    t = Table(data_rows, colWidths=[80, 70, 180, 200, 80], repeatRows=1)
                    t.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('BACKGROUND', (0, 1), (-1, -2), colors.HexColor("#F4F6F7")),
                        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor("#BDC3C7")),
                        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                    ]))
                    elements.append(t)
                    doc.build(elements)
                    st.success(f"PDF generato con successo: {filename}")
                    with open(filename, "rb") as f: st.download_button("⬇️ Scarica il PDF", data=f, file_name=filename, mime="application/pdf")
                except Exception as e: st.error(f"Errore PDF: {e}")

def page_incassi():
    st.title("💰 Gestione Incassi")
    df_cantieri = get_cantieri()
    if df_cantieri.empty:
        st.warning("Devi prima creare un cantiere!")
        return

    if "modifica_incasso_attiva" not in st.session_state: st.session_state.modifica_incasso_attiva = False
    if "incasso_da_modificare" not in st.session_state: st.session_state.incasso_da_modificare = None

    with st.expander("➕ Registra Nuovo Incasso"):
        with st.form("nuovo_incasso", clear_on_submit=True):
            col1, col2 = st.columns(2)
            data_i = col1.date_input("Data Fattura", datetime.date.today(), format="DD/MM/YYYY", key="data_incasso")
            cantiere_i = col2.selectbox("Cantiere", df_cantieri['id'].tolist(), format_func=lambda x: df_cantieri[df_cantieri['id']==x]['indirizzo'].values[0], key="cant_incasso")
            
            col3, col4, col5 = st.columns(3)
            fattura = col3.text_input("N. Fattura", key="num_fattura")
            imponibile = col4.number_input("Imponibile (€)", min_value=0.0, step=100.0, key="imp_incasso")
            iva = col5.number_input("Aliquota IVA (%)", min_value=0.0, value=22.0, step=1.0, key="iva_incasso")
            
            if st.form_submit_button("Salva Incasso"):
                totale = imponibile + (imponibile * iva / 100)
                data_formattata = data_i.strftime('%Y-%m-%d')
                supabase.table("incassi").insert({
                    "data": data_formattata, "cantiere_id": cantiere_i, "fattura": fattura, 
                    "imponibile": imponibile, "iva": iva, "totale": totale
                }).execute()
                st.success("Incasso registrato!"); st.rerun()

    st.divider()

    with st.expander("🔍 Filtra gli incassi", expanded=True):
        col_f1, col_f2, col_f3 = st.columns(3)
        data_inizio_f = col_f1.date_input("Dal", value=datetime.date.today().replace(month=1, day=1), format="DD/MM/YYYY", key="inc_data_inizio")
        data_fine_f = col_f2.date_input("Al", value=datetime.date.today(), format="DD/MM/YYYY", key="inc_data_fine")
        
        opzioni_cantieri = ["Tutti i cantieri"] + [f"{row['id']} - {row['indirizzo']}" for _, row in df_cantieri.iterrows()]
        filtro_cantiere = col_f3.selectbox("Cantiere", opzioni_cantieri, key="inc_filtro_cantiere")

    if st.session_state.modifica_incasso_attiva and st.session_state.incasso_da_modificare:
        id_incasso = st.session_state.incasso_da_modificare
        res_inc = supabase.table("incassi").select("*").eq("id", id_incasso).execute()
        
        if not res_inc.data:
            st.warning("Questo incasso non esiste più. La modifica è stata annullata.")
            st.session_state.modifica_incasso_attiva = False
            st.session_state.incasso_da_modificare = None
        else:
            inc_data = res_inc.data[0]
            st.subheader(f"✏️ Modifica Incasso ID: {id_incasso}")
            
            with st.form("form_modifica_incasso"):
                col1, col2 = st.columns(2)
                try: default_date = datetime.datetime.strptime(str(inc_data['data'])[:10], "%Y-%m-%d").date()
                except: default_date = datetime.date.today()
                
                m_data = col1.date_input("Data Fattura", value=default_date, format="DD/MM/YYYY")
                idx_cant = df_cantieri['id'].tolist().index(inc_data['cantiere_id']) if inc_data['cantiere_id'] in df_cantieri['id'].tolist() else 0
                m_cantiere = col2.selectbox("Cantiere", df_cantieri['id'].tolist(), index=idx_cant, format_func=lambda x: df_cantieri[df_cantieri['id']==x]['indirizzo'].values[0])
                
                col3, col4, col5 = st.columns(3)
                m_fattura = col3.text_input("N. Fattura", value=inc_data['fattura'])
                m_imponibile = col4.number_input("Imponibile (€)", value=float(inc_data['imponibile']), step=100.0)
                m_iva = col5.number_input("Aliquota IVA (%)", value=float(inc_data['iva']), step=1.0)
                
                col_btn1, col_btn2, col_btn3 = st.columns(3)
                if col_btn1.form_submit_button("Salva Modifiche", type="primary"):
                    nuovo_totale = m_imponibile + (m_imponibile * m_iva / 100)
                    data_formattata = m_data.strftime('%Y-%m-%d')
                    supabase.table("incassi").update({
                        "data": data_formattata, "cantiere_id": m_cantiere, "fattura": m_fattura,
                        "imponibile": m_imponibile, "iva": m_iva, "totale": nuovo_totale
                    }).eq("id", id_incasso).execute()
                    st.session_state.modifica_incasso_attiva = False
                    st.session_state.incasso_da_modificare = None
                    st.success("Incasso aggiornato!"); st.rerun()
                    
                if col_btn2.form_submit_button("Elimina Incasso", type="secondary"):
                    supabase.table("incassi").delete().eq("id", id_incasso).execute()
                    st.session_state.modifica_incasso_attiva = False
                    st.session_state.incasso_da_modificare = None
                    st.success("Incasso eliminato!"); st.rerun()
                    
                if col_btn3.form_submit_button("Annulla"):
                    st.session_state.modifica_incasso_attiva = False
                    st.session_state.incasso_da_modificare = None
                    st.rerun()
            st.divider()

    try:
        res = supabase.table("incassi").select("*").gte("data", str(data_inizio_f)).lte("data", str(data_fine_f)).execute()
        df = pd.DataFrame(res.data)
    except Exception as e:
        st.error(f"Errore caricamento incassi: {e}")
        return

    if df.empty:
        st.info("Nessun incasso trovato nel periodo selezionato.")
    else:
        cant_map = {r['id']: r['indirizzo'] for r in df_cantieri.to_dict('records')}
        df['Cantiere'] = df['cantiere_id'].apply(lambda x: cant_map.get(x, "Sconosciuto"))
        
        if filtro_cantiere != "Tutti i cantieri":
            cid_filtro = int(filtro_cantiere.split(" - ")[0])
            df = df[df['cantiere_id'] == cid_filtro]
            
        if df.empty:
            st.info("Nessun incasso trovato con questi filtri.")
        else:
            df = df.sort_values("data", ascending=False)
            for _, row in df.iterrows():
                col_dati, col_btn = st.columns([8, 2])
                with col_dati:
                    data_it = formatta_data_italiana(row['data'])
                    st.markdown(f"**{data_it}** | {row['Cantiere']} | Fattura: **{row['fattura']}** | Imponibile: € {row['imponibile']:,.2f} | IVA: {row['iva']}% | **Totale: € {row['totale']:,.2f}**")
                with col_btn:
                    if st.button("✏️ Modifica", key=f"mod_inc_{row['id']}"):
                        st.session_state.modifica_incasso_attiva = True
                        st.session_state.incasso_da_modificare = row['id']
                        st.rerun()
            
            st.divider()
            st.markdown(f"### Totale Incassi Filtrati: **€ {df['totale'].sum():,.2f}** (Imponibile: € {df['imponibile'].sum():,.2f})")

def page_avanzamento():
    st.title("📈 Avanzamento Lavori (Calcolo Automatico)")
    st.write("L'avanzamento lavori è calcolato in base agli incassi rispetto all'importo contrattuale.")
    try:
        res_cant = supabase.table("preventivi").select("*").eq("stato", "Attivo").execute()
        df = pd.DataFrame(res_cant.data)
        if df.empty: st.info("Nessun cantiere attivo presente."); return
        res_inc = supabase.table("incassi").select("cantiere_id, imponibile").execute()
        df_inc = pd.DataFrame(res_inc.data)
        incassi_dict = df_inc.groupby('cantiere_id')['imponibile'].sum().to_dict() if not df_inc.empty else {}
        df['Totale_Incassato'] = df['id'].apply(lambda x: float(incassi_dict.get(x, 0)))
        df['Percentuale'] = df.apply(lambda row: (row['Totale_Incassato'] / row['importo_contratto'] * 100) if row['importo_contratto'] > 0 else 0, axis=1)
        df_visual = df.copy()
        df_visual['importo_contratto'] = df_visual['importo_contratto'].apply(lambda x: f"€ {x:,.2f}")
        df_visual['Totale_Incassato'] = df_visual['Totale_Incassato'].apply(lambda x: f"€ {x:,.2f}")
        df_visual['Percentuale'] = df_visual['Percentuale'].apply(lambda x: f"{x:.1f}%")
        st.dataframe(df_visual[['indirizzo', 'importo_contratto', 'Totale_Incassato', 'Percentuale']].rename(columns={'indirizzo':'Cantiere', 'importo_contratto':'Importo Contratto'}), use_container_width=True)
        st.divider(); st.subheader("Dettaglio Visivo")
        for index, row in df.iterrows():
            perc = (row['Totale_Incassato'] / row['importo_contratto'] * 100) if row['importo_contratto'] > 0 else 0
            st.markdown(f"**{row['indirizzo']}** - {perc:.1f}%"); st.progress(min(perc / 100, 1.0))
    except Exception as e: st.error(f"Errore: {e}")

def page_bilanci():
    st.title("⚖️ Bilanci per Cantiere")
    with st.expander("🔍 Filtri", expanded=True):
        col1, col2, col3 = st.columns([1, 1, 1])
        data_inizio = col1.date_input("Dal", value=datetime.date.today().replace(month=1, day=1), format="DD/MM/YYYY", key="bil_data_inizio")
        data_fine = col2.date_input("Al", value=datetime.date.today(), format="DD/MM/YYYY", key="bil_data_fine")
        includi_esterne = col3.checkbox("Includi operai esterni", value=True, key="bil_includi_esterne")
    if data_inizio > data_fine: st.error("La data 'Dal' non può essere successiva alla data 'Al'."); return
    
    try:
        ripartizione = calcola_quote_amministrative(str(data_inizio), str(data_fine), includi_esterne)
        quote_amm, tot_amm, tot_amm_ripartito, tot_ore, ore_per_cantiere = ripartizione['quote'], ripartizione['tot_amm'], ripartizione['tot_amm_ripartito'], ripartizione['tot_ore'], ripartizione['ore_per_cantiere']
        res_prev = supabase.table("preventivi").select("id, indirizzo, stato").execute()
        df_cantieri = pd.DataFrame(res_prev.data)
        res_inc = supabase.table("incassi").select("cantiere_id, imponibile").gte("data", str(data_inizio)).lte("data", str(data_fine)).execute()
        inc_dict = pd.DataFrame(res_inc.data).groupby('cantiere_id')['imponibile'].sum().to_dict() if res_inc.data else {}
        res_man = supabase.table("costo_manodopera").select("cantiere_id, totale").gte("data", str(data_inizio)).lte("data", str(data_fine)).execute()
        man_dict = pd.DataFrame(res_man.data).groupby('cantiere_id')['totale'].sum().to_dict() if res_man.data else {}
        res_mat = supabase.table("costo_materiali").select("cantiere_id, imponibile").gte("data", str(data_inizio)).lte("data", str(data_fine)).execute()
        mat_dict = pd.DataFrame(res_mat.data).groupby('cantiere_id')['imponibile'].sum().to_dict() if res_mat.data else {}
        
        righe = []
        for _, cant in df_cantieri.iterrows():
            cid = int(cant['id']); inc = float(inc_dict.get(cid, 0)); pers = float(man_dict.get(cid, 0)); mat = float(mat_dict.get(cid, 0)); quota = float(quote_amm.get(cid, 0)); ore = float(ore_per_cantiere.get(cid, 0))
            if inc == 0 and pers == 0 and mat == 0 and quota == 0 and ore == 0: continue
            costi_totali = pers + mat + quota; bilancio = inc - costi_totali
            righe.append({'Cantiere': cant['indirizzo'], 'Stato': cant['stato'], 'Ore': ore, 'Incassi': inc, 'Costi Personale': pers, 'Costi Materiali': mat, 'Quota Amm.': quota, 'Costi Totali': costi_totali, 'Bilancio': bilancio, 'Margine %': (bilancio / inc * 100) if inc > 0 else 0})
        
        if not righe: st.info("Nessun cantiere con movimenti."); return
        df_bilancio = pd.DataFrame(righe).sort_values('Bilancio', ascending=False)
        
        tot_inc, tot_pers, tot_mat, tot_quota, tot_costi, tot_bilancio = df_bilancio['Incassi'].sum(), df_bilancio['Costi Personale'].sum(), df_bilancio['Costi Materiali'].sum(), df_bilancio['Quota Amm.'].sum(), df_bilancio['Costi Totali'].sum(), df_bilancio['Bilancio'].sum()
        tot_ore_tab = df_bilancio['Ore'].sum()
        
        st.markdown("### 📊 Sintesi del Periodo")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Incassi", f"€ {tot_inc:,.2f}"); k2.metric("Costi Totali", f"€ {tot_costi:,.2f}", delta_color="inverse"); k3.metric("Bilancio", f"€ {tot_bilancio:,.2f}", delta_color="normal" if tot_bilancio >= 0 else "inverse"); k4.metric("Ore Totali", f"{tot_ore_tab:,.1f} h")
        st.divider()
        
        df_visual = df_bilancio.copy()
        for col in ['Ore']: df_visual[col] = df_visual[col].apply(lambda x: f"{x:,.1f}")
        for col in ['Incassi', 'Costi Personale', 'Costi Materiali', 'Quota Amm.', 'Costi Totali', 'Bilancio']: df_visual[col] = df_visual[col].apply(lambda x: f"€ {x:,.2f}")
        df_visual['Margine %'] = df_visual['Margine %'].apply(lambda x: f"{x:.1f}%")
        
        riga_tot = pd.DataFrame([{'Cantiere': 'TOTALE', 'Stato': '', 'Ore': f"{tot_ore_tab:,.1f}", 'Incassi': f"€ {tot_inc:,.2f}", 'Costi Personale': f"€ {tot_pers:,.2f}", 'Costi Materiali': f"€ {tot_mat:,.2f}", 'Quota Amm.': f"€ {tot_quota:,.2f}", 'Costi Totali': f"€ {tot_costi:,.2f}", 'Bilancio': f"€ {tot_bilancio:,.2f}", 'Margine %': f"{(tot_bilancio / tot_inc * 100) if tot_inc > 0 else 0:.1f}%"}])
        st.dataframe(pd.concat([df_visual, riga_tot], ignore_index=True), use_container_width=True)
        
        st.info(f"💡 **Ripartizione costi amministrativi:** € {tot_amm:,.2f} totali, di cui € {tot_amm_ripartito:,.2f} ripartiti in base a {tot_ore:,.1f} ore.")
        st.divider()
        
        st.subheader("📈 Bilancio per Cantiere (grafico)")
        fig, ax = plt.subplots(figsize=(10, max(3, len(df_bilancio) * 0.5)))
        bars = ax.barh(df_bilancio['Cantiere'], df_bilancio['Bilancio'], color=['#27AE60' if b >= 0 else '#E74C3C' for b in df_bilancio['Bilancio']])
        ax.axvline(0, color='black', linewidth=0.8); ax.grid(True, axis='x', linestyle='--', alpha=0.5)
        for bar, val in zip(bars, df_bilancio['Bilancio']):
            ax.text(val + (5 if val >= 0 else -5), bar.get_y() + bar.get_height()/2, f"€ {val:,.0f}", va='center', ha='left' if val >= 0 else 'right', fontsize=8)
        max_v, min_v = max(df_bilancio['Bilancio']), min(df_bilancio['Bilancio']); margine = (max_v - min_v) * 0.15 if (max_v - min_v) > 0 else 100
        ax.set_xlim(min_v - margine, max_v + margine); plt.tight_layout(); st.pyplot(fig)
        st.divider()
        
        st.subheader("📄 Esporta Bilancio in PDF")
        if st.button("📄 Genera PDF Bilancio", type="primary", key="btn_export_bilanci_pdf"):
            try:
                img_buffer = io.BytesIO()
                fig.savefig(img_buffer, format='png', bbox_inches='tight', dpi=150)
                img_buffer.seek(0)

                filename = f"Bilancio_Cantieri_{datetime.date.today()}.pdf"
                doc = SimpleDocTemplate(filename, pagesize=landscape(A4))
                elements = []
                styles = getSampleStyleSheet()
                style_cell = ParagraphStyle('cell_bil', parent=styles['Normal'], fontSize=7, leading=9, alignment=0)
                style_num = ParagraphStyle('num_bil', parent=styles['Normal'], fontSize=7, leading=9, alignment=2)
                
                elements.append(Paragraph(f"Bilancio Cantieri dal {formatta_data_italiana(data_inizio)} al {formatta_data_italiana(data_fine)}", styles['Title']))
                elements.append(Spacer(1, 12))
                
                data_rows = [["Cantiere", "Stato", "Ore", "Incassi (€)", "Pers. (€)", "Mat. (€)", "Quota Amm. (€)", "Costi Tot. (€)", "Bilancio (€)", "Marg. %"]]
                for _, r in df_bilancio.iterrows():
                    data_rows.append([Paragraph(r['Cantiere'], style_cell), r['Stato'], f"{r['Ore']:,.1f}", Paragraph(f"{r['Incassi']:,.2f}", style_num), Paragraph(f"{r['Costi Personale']:,.2f}", style_num), Paragraph(f"{r['Costi Materiali']:,.2f}", style_num), Paragraph(f"{r['Quota Amm.']:,.2f}", style_num), Paragraph(f"{r['Costi Totali']:,.2f}", style_num), Paragraph(f"{r['Bilancio']:,.2f}", style_num), f"{r['Margine %']:.1f}%"])
                
                data_rows.append([Paragraph("<b>TOTALE</b>", style_cell), "", f"{tot_ore_tab:,.1f}", Paragraph(f"<b>{tot_inc:,.2f}</b>", style_num), Paragraph(f"<b>{tot_pers:,.2f}</b>", style_num), Paragraph(f"<b>{tot_mat:,.2f}</b>", style_num), Paragraph(f"<b>{tot_quota:,.2f}</b>", style_num), Paragraph(f"<b>{tot_costi:,.2f}</b>", style_num), Paragraph(f"<b>{tot_bilancio:,.2f}</b>", style_num), f"{(tot_bilancio / tot_inc * 100) if tot_inc > 0 else 0:.1f}%"])
                
                t = Table(data_rows, colWidths=[140, 45, 40, 65, 65, 65, 65, 65, 65, 45], repeatRows=1)
                style_cmds = [('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2C3E50")), ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke), ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, 0), 8), ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#BDC3C7")), ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'), ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#ECF0F1"))]
                for i, (_, r) in enumerate(df_bilancio.iterrows(), start=1):
                    style_cmds.append(('BACKGROUND', (8, i), (8, i), colors.HexColor("#D5F4E6") if r['Bilancio'] >= 0 else colors.HexColor("#FADBD8")))
                t.setStyle(TableStyle(style_cmds)); elements.append(t)
                elements.append(Spacer(1, 20))
                
                img = Image(img_buffer, width=700, height=280)
                elements.append(img)
                
                elements.append(Spacer(1, 12))
                elements.append(Paragraph(f"<b>Nota:</b> € {tot_amm_ripartito:,.2f} di costi amministrativi ripartiti su {tot_ore:,.1f} ore.", styles['Normal']))
                
                doc.build(elements)
                st.success(f"PDF generato: {filename}")
                with open(filename, "rb") as f: st.download_button("⬇️ Scarica il PDF", data=f, file_name=filename, mime="application/pdf")
            except Exception as e: st.error(f"Errore PDF: {e}")
    except Exception as e: st.error(f"Errore nel calcolo bilanci: {e}")

def page_riepilogo():
    st.title("📊 Riepilogo e Grafici")
    
    # --- SEZIONE 1: REPORT COSTI DETTAGLIATO ---
    st.subheader("📋 Report Costi Dettagliato")
    st.write("Filtra per periodo, Cantiere, Tipo di Costo e Descrizione per un'analisi approfondita.")

    col_d1, col_d2 = st.columns(2)
    data_inizio_report = col_d1.date_input("Dal", value=datetime.date.today().replace(day=1), format="DD/MM/YYYY", key="data_inizio_report")
    data_fine_report = col_d2.date_input("Al", value=datetime.date.today(), format="DD/MM/YYYY", key="data_fine_report")

    col_r1, col_r2 = st.columns(2)
    try:
        df_cantieri = get_cantieri()
    except:
        df_cantieri = pd.DataFrame()

    opzioni_cantieri = ["Tutti i cantieri"] + [f"{row['id']} - {row['indirizzo']}" for _, row in df_cantieri.iterrows()] if not df_cantieri.empty else ["Tutti i cantieri"]
    filtro_cantiere = col_r1.selectbox("Seleziona Cantiere", opzioni_cantieri, key="filtro_cantiere_report")
    filtro_descrizione = col_r2.text_input("Cerca nella Descrizione", placeholder="Es. massetto, fattura...", key="filtro_desc_report")
    
    costi_list = []
    try:
        res = supabase.table("costo_manodopera").select("*").gte("data", str(data_inizio_report)).lte("data", str(data_fine_report)).execute()
        for r in res.data:
            if filtro_cantiere != "Tutti i cantieri" and str(r['cantiere_id']) != filtro_cantiere.split(" - ")[0]: continue
            desc = r['operaio'] + " " + (r['descrizione'] or "")
            if filtro_descrizione and filtro_descrizione.lower() not in desc.lower(): continue
            costi_list.append({"Tipo": "Personale", "Data": r['data'], "Cantiere": r['cantiere_id'], "Descrizione": desc, "Importo": r['totale']})
            
        res = supabase.table("costo_materiali").select("*").gte("data", str(data_inizio_report)).lte("data", str(data_fine_report)).execute()
        for r in res.data:
            if filtro_cantiere != "Tutti i cantieri" and str(r['cantiere_id']) != filtro_cantiere.split(" - ")[0]: continue
            if filtro_descrizione and filtro_descrizione.lower() not in r['fornitore'].lower(): continue
            costi_list.append({"Tipo": "Materiale", "Data": r['data'], "Cantiere": r['cantiere_id'], "Descrizione": r['fornitore'], "Importo": r['imponibile']})
    except Exception as e:
        st.error(f"Errore caricamento costi: {e}")

    # Gestione Costi Amministrativi (Ripartiti se c'è un singolo cantiere)
    if filtro_cantiere == "Tutti i cantieri":
        try:
            res = supabase.table("costo_amministrativo").select("*").gte("data", str(data_inizio_report)).lte("data", str(data_fine_report)).execute()
            for r in res.data:
                if filtro_descrizione and filtro_descrizione.lower() not in r['descrizione'].lower(): continue
                costi_list.append({"Tipo": "Amministrativo", "Data": r['data'], "Cantiere": "Generale", "Descrizione": r['descrizione'], "Importo": r['importo']})
        except Exception as e:
            pass
    else:
        cid_selezionato = int(filtro_cantiere.split(" - ")[0])
        try:
            ripartizione = calcola_quote_amministrative(str(data_inizio_report), str(data_fine_report), includi_esterne=True)
            quota_amm_cantiere = ripartizione['quote'].get(cid_selezionato, 0.0)
            
            if quota_amm_cantiere > 0:
                costi_list.append({
                    "Tipo": "Amm. Ripartito", 
                    "Data": str(data_fine_report), 
                    "Cantiere": filtro_cantiere.split(" - ")[1], 
                    "Descrizione": "Quota costi amministrativi (calcolata su ore lavorate)", 
                    "Importo": quota_amm_cantiere
                })
        except Exception as e:
            st.error(f"Errore calcolo costi amministrativi: {e}")

    if not costi_list:
        st.info("Nessun costo trovato con i filtri selezionati.")
    else:
        df_report = pd.DataFrame(costi_list)
        cant_map = {r['id']: r['indirizzo'] for r in df_cantieri.to_dict('records')} if not df_cantieri.empty else {}
        df_report['Cantiere'] = df_report['Cantiere'].apply(lambda x: cant_map.get(x, x) if isinstance(x, int) else x)
        df_report['Data_Obj'] = pd.to_datetime(df_report['Data'])
        df_report = df_report.sort_values(by='Data_Obj', ascending=False)
        
        totale_importo = df_report['Importo'].sum()
        df_visual = df_report[['Tipo', 'Data', 'Cantiere', 'Descrizione', 'Importo']].copy()
        df_visual['Data'] = df_visual['Data'].apply(formatta_data_italiana)
        df_visual['Importo'] = df_visual['Importo'].apply(lambda x: f"€ {x:,.2f}")
        
        riga_totale = pd.DataFrame([{'Tipo': '', 'Data': '', 'Cantiere': '', 'Descrizione': 'TOTALE', 'Importo': f"€ {totale_importo:,.2f}"}])
        st.dataframe(pd.concat([df_visual, riga_totale], ignore_index=True), use_container_width=True)
        
        if st.button("📄 Esporta Report in PDF", type="primary", key="btn_export_report_dettagliato"):
            try:
                filename = f"Report_Costi_{datetime.date.today()}.pdf"
                doc = SimpleDocTemplate(filename, pagesize=landscape(A4))
                elements = []
                styles = getSampleStyleSheet()
                style_cell = ParagraphStyle('cell_style', parent=styles['Normal'], fontSize=8, leading=10, alignment=0)
                
                elements.append(Paragraph(f"Report Costi dal {formatta_data_italiana(data_inizio_report)} al {formatta_data_italiana(data_fine_report)}", styles['Title']))
                elements.append(Paragraph(f"Filtro: Cantiere: {filtro_cantiere} | Ricerca: {filtro_descrizione}", styles['Normal']))
                elements.append(Spacer(1, 12))
                
                data_rows = [["Tipo", "Data", "Cantiere", "Descrizione", "Importo (€)"]]
                for _, r in df_report.iterrows():
                    data_rows.append([r['Tipo'], formatta_data_italiana(r['Data']), Paragraph(str(r['Cantiere']), style_cell), Paragraph(str(r['Descrizione']), style_cell), f"{r['Importo']:,.2f}"])
                data_rows.append(["", "", "", "TOTALE GENERALE", f"{totale_importo:,.2f}"])
                
                t = Table(data_rows, colWidths=[80, 70, 180, 200, 80], repeatRows=1)
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('BACKGROUND', (0, 1), (-1, -2), colors.HexColor("#F4F6F7")),
                    ('GRID', (0, 0), (-1, -1), 1, colors.HexColor("#BDC3C7")),
                    ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ]))
                elements.append(t)
                doc.build(elements)
                st.success(f"PDF generato: {filename}")
                with open(filename, "rb") as f: st.download_button("⬇️ Scarica il PDF", data=f, file_name=filename, mime="application/pdf")
            except Exception as e: st.error(f"Errore PDF: {e}")

    st.divider()

    # --- SEZIONE 4: GRAFICO ANDAMENTO ---
    st.subheader("📈 Andamento Economico")
    try:
        res_inc = supabase.table("incassi").select("data, imponibile").execute()
        res_man = supabase.table("costo_manodopera").select("data, totale").execute()
        res_mat = supabase.table("costo_materiali").select("data, imponibile").execute()
        res_amm = supabase.table("costo_amministrativo").select("data, importo").execute()
        
        all_movs = []
        if res_inc.data: all_movs.extend([{'data': r['data'], 'totale': r['imponibile'], 'Tipo': 'Incasso'} for r in res_inc.data])
        if res_man.data: all_movs.extend([{'data': r['data'], 'totale': r['totale'], 'Tipo': 'Costo'} for r in res_man.data])
        if res_mat.data: all_movs.extend([{'data': r['data'], 'totale': r['imponibile'], 'Tipo': 'Costo'} for r in res_mat.data])
        if res_amm.data: all_movs.extend([{'data': r['data'], 'totale': r['importo'], 'Tipo': 'Costo'} for r in res_amm.data])
        
        if not all_movs:
            st.info("Nessun dato disponibile per il grafico.")
        else:
            df_mov = pd.DataFrame(all_movs)
            df_mov['data'] = pd.to_datetime(df_mov['data'])
            df_mov = df_mov.sort_values('data')
            df_mov['Incassi Cum'] = df_mov.apply(lambda x: x['totale'] if x['Tipo'] == 'Incasso' else 0, axis=1).cumsum()
            df_mov['Costi Cum'] = df_mov.apply(lambda x: x['totale'] if x['Tipo'] == 'Costo' else 0, axis=1).cumsum()
            
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.plot(df_mov['data'], df_mov['Incassi Cum'], label='Incassi', color='green', marker='o', linewidth=2)
            ax.plot(df_mov['data'], df_mov['Costi Cum'], label='Costi', color='red', marker='x', linewidth=2)
            ax.legend(); ax.grid(True, linestyle='--', alpha=0.6)
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m/%Y'))
            plt.xticks(rotation=45); plt.tight_layout()
            st.pyplot(fig)
    except Exception as e: st.error(f"Errore nel grafico: {e}")

def page_stampe():
    from reportlab.platypus import PageBreak
    
    st.title("🖨️ Stampe e Report Personalizzati")
    st.write("Genera un report specifico filtrando per periodo, cantiere e tipologia di costo.")
    
    try:
        df_cantieri = get_cantieri()
    except:
        df_cantieri = pd.DataFrame()

    opzioni_cantieri = ["Tutti i cantieri"] + [f"{row['id']} - {row['indirizzo']}" for _, row in df_cantieri.iterrows()] if not df_cantieri.empty else ["Tutti i cantieri"]
    cant_map = {r['id']: r['indirizzo'] for r in df_cantieri.to_dict('records')} if not df_cantieri.empty else {}
    
    with st.container():
        col_s1, col_s2 = st.columns(2)
        s_data_ini = col_s1.date_input("Periodo Dal", value=datetime.date.today().replace(day=1), format="DD/MM/YYYY", key="st_data_ini")
        s_data_fin = col_s2.date_input("Periodo Al", value=datetime.date.today(), format="DD/MM/YYYY", key="st_data_fin")
        
        col_s3, col_s4 = st.columns(2)
        s_cantiere = col_s3.selectbox("Cantiere", opzioni_cantieri, key="st_cantiere")
        
        try:
            res_cat = supabase.table("categorie_amministrative").select("nome").execute()
            lista_categorie = [c['nome'] for c in res_cat.data]
        except:
            lista_categorie = []
            
        opzioni_tipologia = [
            "Tutti", 
            "Solo Operai", 
            "Solo Materiale", 
            "Operai + Materiali", 
            "Operai + Materiali + Tutte le Categorie Amm."
        ] + [f"Solo {cat}" for cat in lista_categorie]
        
        s_tipo = col_s4.selectbox("Tipologia Costo", opzioni_tipologia, key="st_tipo")
        
        if st.button("🖨️ Genera PDF Personalizzato", type="primary"):
            try:
                report_data = []
                tot_report = 0.0
                
                res_man = supabase.table("costo_manodopera").select("*").gte("data", str(s_data_ini)).lte("data", str(s_data_fin)).execute()
                res_mat = supabase.table("costo_materiali").select("*").gte("data", str(s_data_ini)).lte("data", str(s_data_fin)).execute()
                res_amm = supabase.table("costo_amministrativo").select("*").gte("data", str(s_data_ini)).lte("data", str(s_data_fin)).execute()
                
                quota_amm_cantiere = 0.0
                if s_cantiere != "Tutti i cantieri":
                    cid_selezionato = int(s_cantiere.split(" - ")[0])
                    ripartizione = calcola_quote_amministrative(str(s_data_ini), str(s_data_fin), includi_esterne=True)
                    quota_amm_cantiere = ripartizione['quote'].get(cid_selezionato, 0.0)

                # 1. Operai
                if "Operai" in s_tipo or s_tipo == "Tutti":
                    for r in res_man.data:
                        if s_cantiere != "Tutti i cantieri" and str(r['cantiere_id']) != s_cantiere.split(" - ")[0]: continue
                        tot_report += float(r['totale'])
                        report_data.append({"Tipo": "Operai", "Data": r['data'], "Cantiere": cant_map.get(r['cantiere_id'], r['cantiere_id']), "Descrizione": f"{r['operaio']} - {r['descrizione']}", "Importo": r['totale']})

                # 2. Materiali
                if "Material" in s_tipo or s_tipo == "Tutti":
                    for r in res_mat.data:
                        if s_cantiere != "Tutti i cantieri" and str(r['cantiere_id']) != s_cantiere.split(" - ")[0]: continue
                        tot_report += float(r['imponibile'])
                        report_data.append({"Tipo": "Materiale", "Data": r['data'], "Cantiere": cant_map.get(r['cantiere_id'], r['cantiere_id']), "Descrizione": r['fornitore'], "Importo": r['imponibile']})

                # 3. Categorie Amministrative
                cat_da_cercare = []
                if s_tipo == "Operai + Materiali + Tutte le Categorie Amm." or s_tipo == "Tutti":
                    cat_da_cercare = lista_categorie
                elif s_tipo.startswith("Solo ") and s_tipo not in ["Solo Operai", "Solo Materiale"]:
                    cat_da_cercare = [s_tipo.replace("Solo ", "")]

                if cat_da_cercare:
                    for r in res_amm.data:
                        if r['descrizione'] in cat_da_cercare:
                            if s_cantiere != "Tutti i cantieri":
                                tot_costi_amm = sum(float(x['importo']) for x in res_amm.data)
                                if tot_costi_amm > 0 and quota_amm_cantiere > 0:
                                    proporzione_costo = float(r['importo']) / tot_costi_amm
                                    importo_ripartito = proporzione_costo * quota_amm_cantiere
                                    tot_report += importo_ripartito
                                    report_data.append({"Tipo": r['descrizione'], "Data": r['data'], "Cantiere": s_cantiere.split(" - ")[1], "Descrizione": r['descrizione'], "Importo": importo_ripartito})
                            else:
                                tot_report += float(r['importo'])
                                report_data.append({"Tipo": r['descrizione'], "Data": r['data'], "Cantiere": "Generale", "Descrizione": r['descrizione'], "Importo": r['importo']})
                
                if not report_data:
                    st.info("Nessun dato trovato per questa combinazione di filtri.")
                else:
                    df_rep = pd.DataFrame(report_data).sort_values("Data")
                    filename = f"Report_Personalizzato_{datetime.date.today()}.pdf"
                    doc = SimpleDocTemplate(filename, pagesize=landscape(A4))
                    elements = []
                    styles = getSampleStyleSheet()
                    style_cell = ParagraphStyle('cell_style', parent=styles['Normal'], fontSize=7, leading=9, alignment=0)
                    style_num = ParagraphStyle('num_style', parent=styles['Normal'], fontSize=7, leading=9, alignment=2)
                    
                    elements.append(Paragraph(f"Report Personalizzato dal {formatta_data_italiana(s_data_ini)} al {formatta_data_italiana(s_data_fin)}", styles['Title']))
                    elements.append(Paragraph(f"Cantiere: {s_cantiere} | Tipologia: {s_tipo}", styles['Normal']))
                    elements.append(Spacer(1, 12))
                    
                    # --- TABELLA DETTAGLIO (Pagina 1) ---
                    data_rows = [["Tipo", "Data", "Cantiere", "Descrizione", "Importo (€)"]]
                    for _, r in df_rep.iterrows():
                        data_rows.append([r['Tipo'], formatta_data_italiana(r['Data']), Paragraph(str(r['Cantiere']), style_cell), Paragraph(str(r['Descrizione']), style_cell), Paragraph(f"{r['Importo']:,.2f}", style_num)])
                    
                    data_rows.append(["", "", "", "TOTALE GENERALE", f"{tot_report:,.2f}"])
                    
                    t = Table(data_rows, colWidths=[80, 60, 160, 250, 90], repeatRows=1)
                    t.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, 0), 8),
                        ('BACKGROUND', (0, 1), (-1, -2), colors.HexColor("#F4F6F7")),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#BDC3C7")),
                        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                    ]))
                    elements.append(t)
                    
                    # Nuova pagina per il riepilogo a matrice
                    elements.append(PageBreak())
                    
                    elements.append(Paragraph("<b>Riepilogo Costi per Categoria</b>", styles['Heading2']))
                    elements.append(Spacer(1, 12))
                    
                    # Calcolo valori
                    def somma_se_contiene(df, parole):
                        mask = df['Tipo'].apply(lambda x: any(p in x.lower().replace('.', '') for p in parole))
                        return df[mask]['Importo'].sum()

                    tot_operai = df_rep[df_rep['Tipo'] == 'Operai']['Importo'].sum()
                    tot_materiali = df_rep[df_rep['Tipo'] == 'Materiale']['Importo'].sum()
                    tot_inps = somma_se_contiene(df_rep, ['inps'])
                    tot_inail = somma_se_contiene(df_rep, ['inail'])
                    tot_cassa = somma_se_contiene(df_rep, ['cassa'])
                    
                    # Recuperiamo il totale amministrativo complessivo filtrato
                    tot_tutti_amm = df_rep[~df_rep['Tipo'].isin(['Operai', 'Materiale'])]['Importo'].sum()
                    tot_altri_amm = tot_tutti_amm - (tot_inps + tot_inail + tot_cassa)

                    # Intestazione della matrice (con testo a capo e grassetto corretto)
                    matrix_data = [
                        [
                            "", 
                            Paragraph("<b>Costi Manodopera<br/>Diretti</b>", style_cell), 
                            Paragraph("<b>Costi Manodopera<br/>Indiretti</b>", style_cell), 
                            Paragraph("<b>Materiali</b>", style_cell), 
                            Paragraph("<b>Altri Amministrativi</b>", style_cell)
                        ]
                    ]
                    
                    # Righe della matrice
                    matrix_data.append(["Operai", f"€ {tot_operai:,.2f}", "", "", ""])
                    matrix_data.append(["INPS", "", f"€ {tot_inps:,.2f}", "", ""])
                    matrix_data.append(["INAIL", "", f"€ {tot_inail:,.2f}", "", ""])
                    matrix_data.append(["Cassa Edile", "", f"€ {tot_cassa:,.2f}", "", ""])
                    matrix_data.append(["Materiali", "", "", f"€ {tot_materiali:,.2f}", ""])
                    
                    categorie_rimanenti = [c for c in lista_categorie if not any(p in c.lower().replace('.', '') for p in ['inps', 'inail', 'cassa'])]
                    for cat in categorie_rimanenti:
                        val_cat = somma_se_contiene(df_rep, [cat.lower().replace('.', '')])
                        if val_cat > 0:
                            matrix_data.append([cat, "", "", "", f"€ {val_cat:,.2f}"])
                    
                    tot_mdo_diretti = tot_operai
                    tot_mdo_indiretti = tot_inps + tot_inail + tot_cassa
                    matrix_data.append(["Totali", f"€ {tot_mdo_diretti:,.2f}", f"€ {tot_mdo_indiretti:,.2f}", f"€ {tot_materiali:,.2f}", f"€ {tot_altri_amm:,.2f}"])
                    
                    matrix_data.append(["Totale Generale", f"€ {tot_report:,.2f}", "", "", ""])

                    # Creazione tabella con larghezze ottimizzate
                    t_matrix = Table(matrix_data, colWidths=[120, 130, 130, 90, 110])
                    
                    style_matrix = [
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#BDC3C7")),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                        ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
                        ('ALIGN', (0, 1), (0, -1), 'LEFT'),
                        ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('FONTNAME', (0, -2), (-1, -2), 'Helvetica-Bold'),
                        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                        ('BACKGROUND', (0, -2), (-1, -2), colors.HexColor("#ECF0F1")),
                        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#F4F6F7")),
                        ('GRID', (0, 0), (-1, -1), 1, colors.black),
                        ('TOPPADDING', (0, 0), (-1, -1), 6),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                    ]
                    
                    for i in range(1, len(matrix_data)):
                        style_matrix.append(('BACKGROUND', (0, i), (0, i), colors.HexColor("#E8F4F8")))

                    t_matrix.setStyle(TableStyle(style_matrix))
                    elements.append(t_matrix)
                    
                    doc.build(elements)
                    st.success(f"PDF generato: {filename}")
                    with open(filename, "rb") as f: st.download_button("⬇️ Scarica il PDF", data=f, file_name=filename, mime="application/pdf")
            except Exception as e:
                st.error(f"Errore generazione report: {e}")


# --- NAVIGAZIONE ---
if not st.session_state.logged_in:
    login_page()
else:
    with st.sidebar:
        st.markdown(f"### 👤 Utente: {st.session_state.username}")
        st.divider()
        if st.button("🏠 Home", use_container_width=True, key="sidebar_home"): st.session_state.current_page = "Home"; st.rerun()
        if st.button("📋 Cantieri", use_container_width=True, key="sidebar_cantieri"): st.session_state.current_page = "Cantieri"; st.rerun()
        if st.button("👥 Anagrafiche", use_container_width=True, key="sidebar_anagrafiche"): st.session_state.current_page = "Anagrafiche"; st.rerun()
        if st.button("📉 Costi", use_container_width=True, key="sidebar_costi"): st.session_state.current_page = "Costi"; st.rerun()
        if st.button("💰 Incassi", use_container_width=True, key="sidebar_incassi"): st.session_state.current_page = "Incassi"; st.rerun()
        if st.button("📈 Avanzamento", use_container_width=True, key="sidebar_avanzamento"): st.session_state.current_page = "Avanzamento"; st.rerun()
        if st.button("📊 Riepilogo", use_container_width=True, key="sidebar_riepilogo"): st.session_state.current_page = "Riepilogo"; st.rerun()
        if st.button("⚖️ Bilanci", use_container_width=True, key="sidebar_bilanci"): st.session_state.current_page = "Bilanci"; st.rerun()
        if st.button("🖨️ Stampe", use_container_width=True, key="sidebar_stampe"): st.session_state.current_page = "Stampe"; st.rerun()
        if st.session_state.is_admin:
            if st.button("👤 Gestione Utenti", use_container_width=True, key="sidebar_utenti"): st.session_state.current_page = "Utenti"; st.rerun()
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
    elif st.session_state.current_page == "Bilanci": page_bilanci()
    elif st.session_state.current_page == "Stampe": page_stampe()
    elif st.session_state.current_page == "Utenti" and st.session_state.is_admin: page_utenti()
