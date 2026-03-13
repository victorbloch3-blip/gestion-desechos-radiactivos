import math
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Gestión de desechos versión 3", layout="wide")

# --------------------------------------------------
# CONFIGURACIÓN
# --------------------------------------------------
DISTANCIA_M = 0.30
FACTOR_CORRECCION = 2.0
NIVEL_DISPENSA = 74.0

HALF_LIFE_DAYS = {
    "I-131": 8.02,
    "Tc-99m": 0.25,
    "Ra-223": 11.43,
    "Lu-177": 6.65,
    "F-18": 0.076,
}

EFFICIENCY_TYPE = {
    "I-131": "gamma",
    "Tc-99m": "gamma",
    "F-18": "gamma",
    "Ra-223": "alpha",
    "Lu-177": "beta",
}

DB_PATH = Path("gestion_desechos_v3.db")

# --------------------------------------------------
# BASE DE DATOS
# --------------------------------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS detectores (
                serie TEXT PRIMARY KEY,
                eff_gamma REAL NOT NULL,
                eff_beta REAL NOT NULL,
                eff_alpha REAL NOT NULL,
                area_cm2 REAL NOT NULL,
                fecha_actualizacion TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS registros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bulto TEXT NOT NULL,
                radionuclido TEXT NOT NULL,
                detector_serie TEXT NOT NULL,
                masa_g REAL NOT NULL,
                cps REAL NOT NULL,
                eficiencia_tipo TEXT NOT NULL,
                eficiencia_valor REAL NOT NULL,
                area_cm2 REAL NOT NULL,
                actividad_bq_g REAL NOT NULL,
                tiempo_resguardo_d REAL NOT NULL,
                fecha_medicion TEXT NOT NULL,
                fecha_dispensa TEXT NOT NULL,
                estado TEXT NOT NULL,
                bulto_libre_liberacion TEXT NOT NULL,
                creado_en TEXT NOT NULL,
                FOREIGN KEY(detector_serie) REFERENCES detectores(serie)
            )
        """)

init_db()

# --------------------------------------------------
# UTILIDADES
# --------------------------------------------------
def fmt_num(value, decimals=6):
    if value is None:
        return ""
    try:
        value = float(value)
        text = f"{value:.{decimals}f}".rstrip("0").rstrip(".")
        return text
    except Exception:
        return str(value)

def query_df(sql: str, params=None) -> pd.DataFrame:
    with get_conn() as conn:
        return pd.read_sql_query(sql, conn, params=params or ())

def upsert_detector(serie, eff_gamma, eff_beta, eff_alpha, area_cm2):
    fecha_actualizacion = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO detectores (
                serie, eff_gamma, eff_beta, eff_alpha, area_cm2, fecha_actualizacion
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(serie) DO UPDATE SET
                eff_gamma = excluded.eff_gamma,
                eff_beta = excluded.eff_beta,
                eff_alpha = excluded.eff_alpha,
                area_cm2 = excluded.area_cm2,
                fecha_actualizacion = excluded.fecha_actualizacion
        """, (serie, eff_gamma, eff_beta, eff_alpha, area_cm2, fecha_actualizacion))

def get_detector_by_serie(serie):
    df = query_df("SELECT * FROM detectores WHERE serie = ?", (serie,))
    if df.empty:
        return None
    return df.iloc[0].to_dict()

def get_efficiency_for_isotope(radionuclido, detector):
    eff_type = EFFICIENCY_TYPE[radionuclido]
    if eff_type == "gamma":
        return float(detector["eff_gamma"]), eff_type
    elif eff_type == "beta":
        return float(detector["eff_beta"]), eff_type
    else:
        return float(detector["eff_alpha"]), eff_type

def calcular_actividad_bq_g(cps, eficiencia, area_cm2, masa_g):
    area_m2 = area_cm2 / 10000.0
    return (cps * 4 * math.pi * (DISTANCIA_M ** 2) * FACTOR_CORRECCION) / (area_m2 * eficiencia * masa_g)

def calcular_tiempo_resguardo_dias(actividad_bq_g, radionuclido):
    if actividad_bq_g <= NIVEL_DISPENSA:
        return 0.0
    t12 = HALF_LIFE_DAYS[radionuclido]
    return (t12 / math.log(2)) * math.log(actividad_bq_g / NIVEL_DISPENSA)

def guardar_registro(resultado):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO registros (
                bulto, radionuclido, detector_serie, masa_g, cps,
                eficiencia_tipo, eficiencia_valor, area_cm2,
                actividad_bq_g, tiempo_resguardo_d,
                fecha_medicion, fecha_dispensa, estado,
                bulto_libre_liberacion, creado_en
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            resultado["bulto"],
            resultado["radionuclido"],
            resultado["detector_serie"],
            resultado["masa_g"],
            resultado["cps"],
            resultado["eficiencia_tipo"],
            resultado["eficiencia_valor"],
            resultado["area_cm2"],
            resultado["actividad_bq_g"],
            resultado["tiempo_resguardo_d"],
            resultado["fecha_medicion"],
            resultado["fecha_dispensa"],
            resultado["estado"],
            resultado["bulto_libre_liberacion"],
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ))

# --------------------------------------------------
# SESSION STATE
# --------------------------------------------------
if "resultado_actual" not in st.session_state:
    st.session_state.resultado_actual = None

# --------------------------------------------------
# INTERFAZ
# --------------------------------------------------
st.title("Gestión de desechos versión 3")

menu = st.sidebar.radio(
    "Menú",
    ["Nuevo registro", "Detectores", "Historial"]
)

# --------------------------------------------------
# NUEVO REGISTRO
# --------------------------------------------------
if menu == "Nuevo registro":
    st.subheader("Registrar bulto")

    detectores_df = query_df("SELECT * FROM detectores ORDER BY serie")

    if detectores_df.empty:
        st.warning("Primero debes agregar al menos un detector en la sección Detectores.")
    else:
        col1, col2 = st.columns(2)

        with col1:
            bulto = st.text_input("Número de bulto")
            radionuclido = st.selectbox("Radionúclido", list(HALF_LIFE_DAYS.keys()))
            masa_g = st.number_input("Masa del bulto (g)", min_value=0.0, step=1.0, format="%.6f")
            cps = st.number_input("CPS", min_value=0.0, step=1.0, format="%.6f")

        with col2:
            fecha_medicion = st.date_input("Fecha de medición")
            detector_serie = st.selectbox("Detector", detectores_df["serie"].tolist())
            st.caption("Distancia fija de medición: 30 cm")
            st.caption("Nivel de dispensa: 74 Bq/g")

        if st.button("Calcular actividad"):
            detector = get_detector_by_serie(detector_serie)

            if not bulto.strip():
                st.error("Debes ingresar el número de bulto.")
            elif masa_g <= 0:
                st.error("La masa debe ser mayor que 0.")
            elif cps < 0:
                st.error("El CPS no puede ser negativo.")
            elif detector is None:
                st.error("No se encontró el detector seleccionado.")
            else:
                eficiencia_valor, eficiencia_tipo = get_efficiency_for_isotope(radionuclido, detector)
                area_cm2 = float(detector["area_cm2"])

                if eficiencia_valor <= 0:
                    st.error("La eficiencia del detector debe ser mayor que 0.")
                elif area_cm2 <= 0:
                    st.error("El área del detector debe ser mayor que 0.")
                else:
                    actividad_bq_g = calcular_actividad_bq_g(
                        cps=float(cps),
                        eficiencia=eficiencia_valor,
                        area_cm2=area_cm2,
                        masa_g=float(masa_g),
                    )

                    tiempo_resguardo_d = calcular_tiempo_resguardo_dias(
                        actividad_bq_g=actividad_bq_g,
                        radionuclido=radionuclido,
                    )

                    dias_para_dispensa = math.ceil(tiempo_resguardo_d)
                    fecha_dispensa = fecha_medicion + timedelta(days=dias_para_dispensa)

                    libre = "Sí" if actividad_bq_g <= NIVEL_DISPENSA else "No"
                    estado = "Liberable" if libre == "Sí" else "En resguardo"

                    st.session_state.resultado_actual = {
                        "bulto": bulto.strip(),
                        "radionuclido": radionuclido,
                        "detector_serie": detector_serie,
                        "masa_g": float(masa_g),
                        "cps": float(cps),
                        "eficiencia_tipo": eficiencia_tipo,
                        "eficiencia_valor": float(eficiencia_valor),
                        "area_cm2": float(area_cm2),
                        "actividad_bq_g": float(actividad_bq_g),
                        "tiempo_resguardo_d": float(tiempo_resguardo_d),
                        "fecha_medicion": str(fecha_medicion),
                        "fecha_dispensa": str(fecha_dispensa),
                        "estado": estado,
                        "bulto_libre_liberacion": libre,
                    }

        resultado = st.session_state.resultado_actual

        if resultado is not None:
            st.markdown("### Resultado del cálculo")
            st.write(f"**Actividad estimada:** {fmt_num(resultado['actividad_bq_g'], 6)} Bq/g")
            st.write(f"**Tiempo de resguardo:** {fmt_num(resultado['tiempo_resguardo_d'], 6)} días")
            st.write(f"**Fecha probable de dispensa:** {resultado['fecha_dispensa']}")
            st.write(f"**Bulto libre para liberación:** {resultado['bulto_libre_liberacion']}")

            if resultado["estado"] == "Liberable":
                st.success("El bulto ya cumple el nivel de dispensa.")
            else:
                st.warning("El bulto debe permanecer en resguardo hasta la fecha de dispensa.")

            if st.button("Guardar registro"):
                guardar_registro(resultado)
                st.success("Registro guardado correctamente.")
                st.session_state.resultado_actual = None
                st.rerun()

# --------------------------------------------------
# DETECTORES
# --------------------------------------------------
elif menu == "Detectores":
    st.subheader("Agregar o editar detectores")

    detectores_df = query_df("SELECT * FROM detectores ORDER BY serie")
    opciones = ["Nuevo detector"] + detectores_df["serie"].tolist()

    seleccion = st.selectbox("Selecciona una opción", opciones)

    if seleccion == "Nuevo detector":
        serie_default = ""
        eff_gamma_default = 0.0
        eff_beta_default = 0.0
        eff_alpha_default = 0.0
        area_default = 0.0
    else:
        det = get_detector_by_serie(seleccion)
        serie_default = det["serie"]
        eff_gamma_default = float(det["eff_gamma"])
        eff_beta_default = float(det["eff_beta"])
        eff_alpha_default = float(det["eff_alpha"])
        area_default = float(det["area_cm2"])

    with st.form("form_detector"):
        serie = st.text_input("N° Serie", value=serie_default)

        col1, col2 = st.columns(2)
        with col1:
            eff_gamma = st.number_input("Eficiencia gamma", min_value=0.0, value=eff_gamma_default, format="%.10f")
            eff_beta = st.number_input("Eficiencia beta", min_value=0.0, value=eff_beta_default, format="%.10f")
        with col2:
            eff_alpha = st.number_input("Eficiencia alpha", min_value=0.0, value=eff_alpha_default, format="%.10f")
            area_cm2 = st.number_input("Área de la ventana del detector (cm²)", min_value=0.0, value=area_default, format="%.10f")

        submitted = st.form_submit_button("Guardar / actualizar detector")

    if submitted:
        if not serie.strip():
            st.error("Debes ingresar el N° de serie.")
        elif area_cm2 <= 0:
            st.error("El área debe ser mayor que 0.")
        else:
            upsert_detector(
                serie=serie.strip(),
                eff_gamma=float(eff_gamma),
                eff_beta=float(eff_beta),
                eff_alpha=float(eff_alpha),
                area_cm2=float(area_cm2),
            )
            st.success("Detector guardado/actualizado correctamente.")
            st.rerun()

    st.markdown("### Detectores registrados")
    detectores_df = query_df("SELECT * FROM detectores ORDER BY serie")
    if detectores_df.empty:
        st.info("No hay detectores registrados.")
    else:
        df_show = detectores_df.copy()
        for col in ["eff_gamma", "eff_beta", "eff_alpha", "area_cm2"]:
            df_show[col] = df_show[col].apply(lambda x: fmt_num(x, 10))
        st.dataframe(df_show, use_container_width=True)

# --------------------------------------------------
# HISTORIAL
# --------------------------------------------------
elif menu == "Historial":
    st.subheader("Historial de bultos")

    df = query_df("""
        SELECT
            id,
            bulto,
            radionuclido,
            detector_serie AS detector,
            masa_g AS masa,
            cps,
            actividad_bq_g AS actividad,
            tiempo_resguardo_d AS tiempo_resguardo,
            fecha_medicion,
            fecha_dispensa,
            bulto_libre_liberacion
        FROM registros
        ORDER BY id DESC
    """)

    st.write(f"**Cantidad de bultos registrados:** {len(df)}")

    if df.empty:
        st.info("No hay registros guardados todavía.")
    else:
        df_show = df.copy()
        for col in ["masa", "cps", "actividad", "tiempo_resguardo"]:
            df_show[col] = df_show[col].apply(lambda x: fmt_num(x, 6))

        st.dataframe(df_show, use_container_width=True)
