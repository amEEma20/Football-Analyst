import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import datetime

# ---------- CHIAVI (le metteremo dopo) ----------
FOOTBALL_DATA_KEY = st.secrets.get("FOOTBALL_DATA_API_KEY", "")
TAVILY_KEY = st.secrets.get("TAVILY_API_KEY", "")
DEEPSEEK_KEY = st.secrets.get("DEEPSEEK_API_KEY", "")

# ---------- FUNZIONI DATI ----------
@st.cache_data(ttl=3600)
def get_matches():
    if not FOOTBALL_DATA_KEY:
        return []
    url = "https://api.football-data.org/v4/matches"
    headers = {"X-Auth-Token": FOOTBALL_DATA_KEY}
    try:
        data = requests.get(url, headers=headers, params={"status": "SCHEDULED", "limit": 50}, timeout=15).json()
        matches = []
        for m in data.get("matches", []):
            matches.append({
                "id": m["id"],
                "home": m["homeTeam"]["name"],
                "away": m["awayTeam"]["name"],
                "date": m["utcDate"],
                "competition": m["competition"]["name"],
                "venue": m.get("venue", "?"),
                "city": m.get("city", "?")
            })
        return matches
    except:
        return []

@st.cache_data(ttl=86400)
def get_fifa():
    try:
        df = pd.read_csv("https://raw.githubusercontent.com/martj42/international-football-results/main/fifa_rankings.csv")
        latest = df["rank_date"].max()
        df = df[df["rank_date"] == latest]
        return dict(zip(df["country_full"], df["total_points"]))
    except:
        return {}

@st.cache_data(ttl=86400)
def get_economy():
    eco = {}
    for key, ind in [("pop","SP.POP.TOTL"), ("gdp","NY.GDP.MKTP.KD.ZG"), ("inf","FP.CPI.TOTL.ZG"),
                     ("unemp","SL.UEM.TOTL.ZS"), ("rate","FR.INR.LEND"), ("debt","GC.DOD.TOTL.GD.ZS")]:
        url = f"http://api.worldbank.org/v2/country/all/indicator/{ind}?format=json&per_page=20000"
        try:
            for r in requests.get(url, timeout=30).json()[1]:
                if r["value"] is not None:
                    iso = r["countryiso3code"]
                    eco.setdefault(iso, {})
                    if key not in eco[iso] or r["date"] > eco[iso].get(key+"_yr","0"):
                        eco[iso][key] = r["value"]
                        eco[iso][key+"_yr"] = r["date"]
        except:
            pass
    return eco

def get_weather(city, dt_str):
    if not city:
        return None
    try:
        geo = requests.get(f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1").json()
        if "results" not in geo: return None
        lat, lon = geo["results"][0]["latitude"], geo["results"][0]["longitude"]
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        date = dt.strftime("%Y-%m-%d")
        hour = dt.hour
        w = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,relativehumidity_2m,precipitation&start_date={date}&end_date={date}&timezone=auto").json()
        times = w["hourly"]["time"]
        target = dt.strftime("%Y-%m-%dT%H:00")
        idx = times.index(target) if target in times else min(range(len(times)), key=lambda i: abs(datetime.fromisoformat(times[i])-dt))
        return {"temp": w["hourly"]["temperature_2m"][idx], "hum": w["hourly"]["relativehumidity_2m"][idx], "prec": w["hourly"]["precipitation"][idx]}
    except:
        return None

def search_news(query, key):
    try:
        r = requests.post("https://api.tavily.com/search", json={"api_key":key, "query":query, "max_results":5, "include_answer":True}).json()
        return r.get("answer",""), r.get("results",[])
    except:
        return "",[]

def ai_forecast(prompt, key):
    try:
        r = requests.post("https://api.deepseek.com/v1/chat/completions",
            headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},
            json={"model":"deepseek-chat","messages":[{"role":"system","content":"Sei un analista calcistico esperto."},{"role":"user","content":prompt}],"temperature":0.2, "max_tokens":2000}).json()
        return r["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Errore AI: {e}"

# ---------- INTERFACCIA ----------
st.set_page_config(page_title="AI Football", layout="wide")
st.title("⚽ Assistente AI Calcistico")
st.caption("Modello 50% FIFA + 50% Economia + ricerca live + AI generativa")

with st.sidebar:
    st.header("🔑 API Keys")
    st.text_input("Football-Data Key", value=FOOTBALL_DATA_KEY, type="password", key="fd_key")
    st.text_input("Tavily Key", value=TAVILY_KEY, type="password", key="tv_key")
    st.text_input("DeepSeek Key", value=DEEPSEEK_KEY, type="password", key="ds_key")
    st.markdown("---")
    st.caption("Salva le chiavi nei Secrets di Streamlit Cloud per non reinserirle.")

matches = get_matches()
if not matches:
    st.warning("Nessuna partita o chiave Football-Data mancante.")
    st.stop()

match_strs = [f"{m['home']} vs {m['away']} | {m['competition']} | {m['date'][:10]}" for m in matches]
choice = st.selectbox("Scegli partita:", match_strs)
match = matches[match_strs.index(choice)]

st.subheader(f"{match['home']} vs {match['away']}")
st.write(f"🏟️ {match.get('venue','?')}, {match.get('city','?')} | 🕒 {match['date']}")
weather = get_weather(match.get("city"), match["date"])
if weather:
    st.write(f"🌡️ {weather['temp']}°C | 💧 {weather['hum']}% | 🌧️ {weather['prec']}mm")

if st.button("🔮 Genera previsione AI", use_container_width=True):
    tv_key = st.session_state.get("tv_key", TAVILY_KEY)
    ds_key = st.session_state.get("ds_key", DEEPSEEK_KEY)
    if not tv_key or not ds_key:
        st.error("Inserisci Tavily e DeepSeek Key nella sidebar.")
    else:
        with st.spinner("🔍 Cerco notizie..."):
            q = f"{match['home']} {match['away']} ultime notizie formazioni infortuni"
            answer, articles = search_news(q, tv_key)
        with st.spinner("🧠 L'AI analizza..."):
            prompt = f"""
Partita: {match['home']} vs {match['away']}
Competizione: {match['competition']}
Data/Ora: {match['date']}
Stadio: {match.get('venue','?')}, {match.get('city','?')}
Meteo: {weather}
Notizie: {answer}
FIFA: {get_fifa().get(match['home'],'?')} - {get_fifa().get(match['away'],'?')}

Usando il modello 50% ranking FIFA + 50% macroeconomia (popolazione, PIL, inflazione, disoccupazione, tassi, debito pubblico), integrato con le notizie e il meteo, produci:
- probabilità 1X2 (%)
- xG attesi
- giocate consigliate
- spiegazione dettagliata
"""
            result = ai_forecast(prompt, ds_key)
        st.success("✅ Previsione generata")
        st.markdown(result)