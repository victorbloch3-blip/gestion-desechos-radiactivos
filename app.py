import streamlit as st
import pandas as pd
import sqlite3
import math
from datetime import datetime, timedelta

# --------------------------
# CONFIGURACIÓN
# --------------------------

DISTANCIA = 0.30
FACTOR_CORRECCION = 2
NIVEL_DISPENSA = 74

HALF_LIFE = {
    "I-131": 8.02,
    "Tc-99m": 0.25,
    "Ra-223": 11.43,
    "Lu-177": 6.65,
    "F-18": 0.076
}

# --------------------------
# BASE DE DATOS
# --------------------------

conn = sqlite3.connect("datos.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS detectores (
serie TEXT,
eff_gamma REAL,
eff_beta REAL,
eff_alpha REAL,
area REAL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS registros (
bulto TEXT,
radionuclido TEXT,
detector TEXT,
masa REAL,
cps REAL,
actividad REAL,
fecha_medicion TEXT,
fecha_dispensa TEXT
)
""")

conn.commit()

# --------------------------
# FUNCIONES
# --------------------------

def calcular_actividad(cps, eficiencia, area, masa):

    actividad = (cps * 4 * math.pi * DISTANCIA**2 * FACTOR_CORRECCION) / (eficiencia * area * masa)

    return actividad


def calcular_tiempo(A0, T12):

    if A0 <= NIVEL_DISPENSA:
        return 0

    t = (T12 / math.log(2)) * math.log(A0 / NIVEL_DISPENSA)

    return t

# --------------------------
# INTERFAZ
# --------------------------

st.title("Gestión de Desechos Radiactivos")

menu = st.sidebar.selectbox(
    "Menú",
    ["Nuevo registro", "Detectores", "Historial"]
)

# --------------------------
# REGISTRO DE BULTOS
# --------------------------

if menu == "Nuevo registro":

    st.header("Registrar bulto")

    bulto = st.text_input("Número de bulto")

    radionuclido = st.selectbox(
        "Radionúclido",
        list(HALF_LIFE.keys())
    )

    masa = st.number_input("Masa (g)", min_value=0.0)

    cps = st.number_input("Conteos por segundo (CPS)", min_value=0.0)

    fecha = st.date_input("Fecha de medición")

    detectores = pd.read_sql("SELECT * FROM detectores", conn)

    if detectores.empty:

        st.warning("Debe registrar un detector primero")

    else:

        detector = st.selectbox(
            "Detector",
            detectores["serie"]
        )

        datos_detector = detectores[detectores["serie"] == detector].iloc[0]

        eficiencia = datos_detector["eff_gamma"]
        area = datos_detector["area"]

        if st.button("Calcular"):

            actividad = calcular_actividad(cps, eficiencia, area, masa)

            T12 = HALF_LIFE[radionuclido]

            tiempo = calcular_tiempo(actividad, T12)

            fecha_dispensa = fecha + timedelta(days=tiempo)

            st.write("Actividad estimada:", round(actividad,2),"Bq/g")

            st.write("Tiempo de resguardo:", round(tiempo,2),"días")

            st.write("Fecha probable de dispensa:", fecha_dispensa)

            if actividad <= NIVEL_DISPENSA:

                st.success("Bulto liberable")

            else:

                st.warning("Debe permanecer en almacenamiento")

            if st.button("Guardar registro"):

                cursor.execute("""
                INSERT INTO registros VALUES (?,?,?,?,?,?,?,?)
                """,(bulto,radionuclido,detector,masa,cps,actividad,str(fecha),str(fecha_dispensa)))

                conn.commit()

                st.success("Registro guardado")

# --------------------------
# DETECTORES
# --------------------------

if menu == "Detectores":

    st.header("Agregar detector")

    serie = st.text_input("Número de serie")

    eff_gamma = st.number_input("Eficiencia gamma")

    eff_beta = st.number_input("Eficiencia beta")

    eff_alpha = st.number_input("Eficiencia alpha")

    area = st.number_input("Área ventana detector")

    if st.button("Guardar detector"):

        cursor.execute("""
        INSERT INTO detectores VALUES (?,?,?,?,?)
        """,(serie,eff_gamma,eff_beta,eff_alpha,area))

        conn.commit()

        st.success("Detector agregado")

    df = pd.read_sql("SELECT * FROM detectores", conn)

    st.dataframe(df)

# --------------------------
# HISTORIAL
# --------------------------

if menu == "Historial":

    st.header("Registros")

    df = pd.read_sql("SELECT * FROM registros", conn)

    st.dataframe(df)

    hoy = datetime.today().date()

    df["fecha_dispensa"] = pd.to_datetime(df["fecha_dispensa"])

    liberables = df[df["fecha_dispensa"].dt.date <= hoy]

    st.subheader("Bultos liberables")

    st.dataframe(liberables)
