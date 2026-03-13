import streamlit as st
import pandas as pd
import sqlite3
import math
from datetime import datetime, timedelta

# --------------------------
# CONFIGURACIÓN
# --------------------------

DISTANCIA = 0.30  # 30 cm
FACTOR_CORRECCION = 2
NIVEL_DISPENSA = 74  # Bq/g

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
    serie TEXT PRIMARY KEY,
    eff_gamma REAL,
    eff_beta REAL,
    eff_alpha REAL,
    area REAL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS registros (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bulto TEXT,
    radionuclido TEXT,
    detector TEXT,
    masa REAL,
    cps REAL,
    eficiencia_usada REAL,
    tipo_eficiencia TEXT,
    area REAL,
    actividad REAL,
    tiempo_resguardo REAL,
    fecha_medicion TEXT,
    fecha_dispensa TEXT,
    estado TEXT
)
""")

conn.commit()

# --------------------------
# SESSION STATE
# --------------------------

if "resultado_calculo" not in st.session_state:
    st.session_state.resultado_calculo = None

# --------------------------
# FUNCIONES
# --------------------------

def calcular_actividad(cps, eficiencia, area, masa):
    """
    Basado en Apéndice C.1:
    CA = (N * 4 * pi * d^2 * Fc) / (AD * e * MB)
    """
    actividad = (cps * 4 * math.pi * DISTANCIA**2 * FACTOR_CORRECCION) / (eficiencia * area * masa)
    return actividad

def calcular_tiempo(A0, T12):
    if A0 <= NIVEL_DISPENSA:
        return 0.0
    return (T12 / math.log(2)) * math.log(A0 / NIVEL_DISPENSA)

def obtener_eficiencia_por_radionuclido(radionuclido, detector_row):
    if radionuclido in ["I-131", "F-18", "Tc-99m"]:
        return detector_row["eff_gamma"], "gamma"
    elif radionuclido == "Ra-223":
        return detector_row["eff_alpha"], "alpha"
    elif radionuclido == "Lu-177":
        return detector_row["eff_beta"], "beta"
    else:
        return detector_row["eff_gamma"], "gamma"

# --------------------------
# INTERFAZ
# --------------------------

st.title("Gestión de Desechos Radiactivos")

menu = st.sidebar.selectbox(
    "Menú",
    ["Nuevo registro", "Detectores", "Historial"]
)

# --------------------------
# NUEVO REGISTRO
# --------------------------

if menu == "Nuevo registro":
    st.header("Registrar bulto")

    bulto = st.text_input("Número de bulto")
    radionuclido = st.selectbox("Radionúclido", list(HALF_LIFE.keys()))
    masa = st.number_input("Masa del bulto (g)", min_value=0.0, format="%.4f")
    cps = st.number_input("Conteos por segundo (CPS)", min_value=0.0, format="%.4f")
    fecha_medicion = st.date_input("Fecha de medición")

    detectores = pd.read_sql("SELECT * FROM detectores", conn)

    if detectores.empty:
        st.warning("Debe registrar al menos un detector en la sección Detectores.")
    else:
        detector = st.selectbox("Detector utilizado", detectores["serie"].tolist())
        datos_detector = detectores[detectores["serie"] == detector].iloc[0]

        eficiencia, tipo_eficiencia = obtener_eficiencia_por_radionuclido(radionuclido, datos_detector)
        area = float(datos_detector["area"])

        st.info(
            f"Para {radionuclido} se usará la eficiencia **{tipo_eficiencia}** "
            f"del detector seleccionado: **{eficiencia}**"
        )

        col1, col2 = st.columns(2)

        with col1:
            if st.button("Calcular actividad"):
                if not bulto.strip():
                    st.error("Debe ingresar el número de bulto.")
                elif masa <= 0:
                    st.error("La masa debe ser mayor que 0.")
                elif cps < 0:
                    st.error("El CPS no puede ser negativo.")
                elif eficiencia <= 0:
                    st.error("La eficiencia del detector debe ser mayor que 0.")
                elif area <= 0:
                    st.error("El área del detector debe ser mayor que 0.")
                else:
                    actividad = calcular_actividad(cps, eficiencia, area, masa)
                    T12 = HALF_LIFE[radionuclido]
                    tiempo = calcular_tiempo(actividad, T12)
                    fecha_dispensa = fecha_medicion + timedelta(days=float(tiempo))
                    estado = "Liberable" if actividad <= NIVEL_DISPENSA else "En resguardo"

                    st.session_state.resultado_calculo = {
                        "bulto": bulto,
                        "radionuclido": radionuclido,
                        "detector": detector,
                        "masa": float(masa),
                        "cps": float(cps),
                        "eficiencia_usada": float(eficiencia),
                        "tipo_eficiencia": tipo_eficiencia,
                        "area": float(area),
                        "actividad": float(actividad),
                        "tiempo_resguardo": float(tiempo),
                        "fecha_medicion": str(fecha_medicion),
                        "fecha_dispensa": str(fecha_dispensa),
                        "estado": estado
                    }

        resultado = st.session_state.resultado_calculo

        if resultado is not None:
            st.subheader("Resultado del cálculo")
            st.write(f"**Bulto:** {resultado['bulto']}")
            st.write(f"**Radionúclido:** {resultado['radionuclido']}")
            st.write(f"**Detector:** {resultado['detector']}")
            st.write(f"**Tipo de eficiencia usada:** {resultado['tipo_eficiencia']}")
            st.write(f"**Eficiencia usada:** {resultado['eficiencia_usada']}")
            st.write(f"**Área del detector:** {resultado['area']}")
            st.write(f"**Actividad estimada:** {resultado['actividad']:.2f} Bq/g")
            st.write(f"**Tiempo de resguardo:** {resultado['tiempo_resguardo']:.2f} días")
            st.write(f"**Fecha de medición:** {resultado['fecha_medicion']}")
            st.write(f"**Fecha probable de dispensa:** {resultado['fecha_dispensa']}")

            if resultado["estado"] == "Liberable":
                st.success("Bulto liberable")
            else:
                st.warning("Bulto en resguardo")

            with col2:
                if st.button("Guardar registro"):
                    cursor.execute("""
                        INSERT INTO registros (
                            bulto, radionuclido, detector, masa, cps,
                            eficiencia_usada, tipo_eficiencia, area,
                            actividad, tiempo_resguardo,
                            fecha_medicion, fecha_dispensa, estado
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        resultado["bulto"],
                        resultado["radionuclido"],
                        resultado["detector"],
                        resultado["masa"],
                        resultado["cps"],
                        resultado["eficiencia_usada"],
                        resultado["tipo_eficiencia"],
                        resultado["area"],
                        resultado["actividad"],
                        resultado["tiempo_resguardo"],
                        resultado["fecha_medicion"],
                        resultado["fecha_dispensa"],
                        resultado["estado"]
                    ))
                    conn.commit()
                    st.success("Registro guardado correctamente.")
                    st.session_state.resultado_calculo = None

# --------------------------
# DETECTORES
# --------------------------

if menu == "Detectores":
    st.header("Agregar detector")

    serie = st.text_input("Número de serie")
    eff_gamma = st.number_input("Eficiencia gamma", min_value=0.0, format="%.6f")
    eff_beta = st.number_input("Eficiencia beta", min_value=0.0, format="%.6f")
    eff_alpha = st.number_input("Eficiencia alpha", min_value=0.0, format="%.6f")
    area = st.number_input("Área de la ventana del detector", min_value=0.0, format="%.6f")

    if st.button("Guardar detector"):
        if not serie.strip():
            st.error("Debe ingresar el número de serie.")
        elif area <= 0:
            st.error("El área debe ser mayor que 0.")
        else:
            cursor.execute("""
                INSERT OR REPLACE INTO detectores (
                    serie, eff_gamma, eff_beta, eff_alpha, area
                ) VALUES (?, ?, ?, ?, ?)
            """, (serie, eff_gamma, eff_beta, eff_alpha, area))
            conn.commit()
            st.success("Detector guardado/actualizado correctamente.")

    st.subheader("Detectores registrados")
    df_detectores = pd.read_sql("SELECT * FROM detectores", conn)
    st.dataframe(df_detectores, use_container_width=True)

# --------------------------
# HISTORIAL
# --------------------------

if menu == "Historial":
    st.header("Registros")

    df = pd.read_sql("""
        SELECT
            bulto,
            radionuclido,
            detector,
            masa,
            cps,
            tipo_eficiencia,
            eficiencia_usada,
            area,
            actividad,
            tiempo_resguardo,
            fecha_medicion,
            fecha_dispensa,
            estado
        FROM registros
        ORDER BY id DESC
    """, conn)

    if df.empty:
        st.info("No hay registros guardados todavía.")
    else:
        st.dataframe(df, use_container_width=True)

        hoy = datetime.today().date()
        df["fecha_dispensa"] = pd.to_datetime(df["fecha_dispensa"], errors="coerce")

        liberables = df[
            (df["fecha_dispensa"].dt.date <= hoy) |
            (df["estado"] == "Liberable")
        ]

        st.subheader("Bultos liberables")

        if liberables.empty:
            st.info("No hay bultos liberables en este momento.")
        else:
            st.dataframe(liberables, use_container_width=True)
