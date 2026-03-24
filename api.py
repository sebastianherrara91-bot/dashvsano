"""
INCOTEXCO Dashboard Comparativo — API Backend v1.1
FastAPI + PostgreSQL (DWH_INCO)
"""
from fastapi import FastAPI, Query, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from dotenv import load_dotenv
import psycopg2
import psycopg2.extras
import os, datetime
import concurrent.futures

from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

app = FastAPI(title="INCOTEXCO Dashboard API", version="1.1")

# Habilitar CORS (si se requiere para desarrollo externo)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Cambiar por ["https://tudominio.com"] en producción
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_SERVER"),
        port=os.getenv("DB_PORT", 5432),
        dbname=os.getenv("DB_DATABASE"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )

# ── SQL base ──────────────────────────────────────────────────────────────────
QUERY_DATA = """
WITH Valid_Marca_Tipo AS (
    SELECT
        COALESCE(MS.marca, MA.new_marca, EC.marca) AS vmt_marca,
        M.tipo AS vmt_tipo,
        M.fit AS vmt_fit
    FROM dbo.dwh_stock AS ST
    LEFT JOIN dbo.cat_sku AS EC ON ST.ean = EC.ean
    LEFT JOIN dbo.marca_subclase AS MS
        ON ST.ini_cliente = MS.ini_cliente
        AND substring(EC.categoria from 1 for 7) = MS.subcategoria
    LEFT JOIN dbo.monitoreo AS M ON EC.ref_modelo = M.modelo AND EC.marca = M.marca
    LEFT JOIN dbo.marca AS MA ON EC.marca = MA.marca_bd
    WHERE ST.ini_cliente = %(ini_cliente)s
      AND ST.fecha = (SELECT MAX(fecha) FROM dbo.dwh_stock WHERE ini_cliente = %(ini_cliente)s AND fecha <= %(fecha_fin)s)
    GROUP BY 1, 2, 3
    HAVING SUM(ST.cant) >= %(stock_threshold)s
)
SELECT
    syv.ini_cliente,
    syv.c_l,
    syv.local,
    syv.ciudad,
    syv.ean,
    syv.sku,
    syv.sku_madre,
    syv.descripcion,
    syv.modelo,
    syv.marca AS "Marca",
    syv.subclase,
    syv.tipo_programa AS "Tipo_Programa",
    syv.fit_estilo,
    syv.color,
    syv.cod_color,
    syv.color_hexa,
    syv.talla,
    syv.fecha,
    to_char(syv.fecha, 'YY') || '/' || to_char(syv.n_sem, 'FM00') || ' - ' || to_char(syv.fecha, 'MM/DD') AS "semanas",
    SUM(syv.v_cant) AS "cant_venta",
    SUM(syv.s_cant) AS "cant_stock",
    NULLIF(ROUND(SUM(syv.v_cant * syv.v_pvp) / NULLIF(SUM(syv.v_cant), 0), 0), 0) AS "pvp_prom"
FROM (
    SELECT
        ST.ini_cliente,
        ST.num_local AS "c_l",
        T.local,
        T.ciudad,
        ST.ean,
        EC.sku,
        CF.sku_madre,
        EC.descripcion_nueva AS "descripcion",
        EC.ref_modelo AS "modelo",
        VMT.vmt_marca AS "marca",
        substring(EC.categoria from 1 for 7) AS subclase,
        M.tipo AS "tipo_programa",
        M.fit AS "fit_estilo",
        CO.color AS "color",
        CO.codigo AS "cod_color",
        CO.color_hexa AS "color_hexa",
        EC.talla AS "talla",
        (date_trunc('week', ST.fecha))::date AS fecha,
        SEM.n_sem,
        SEM.ano,
        0 AS "v_cant",
        ST.cant AS "s_cant",
        0 AS "v_pvp"
    FROM dbo.dwh_stock AS ST
    LEFT JOIN dbo.cat_sku AS EC ON ST.ean = EC.ean
    LEFT JOIN dbo.ecat_fala AS CF ON ST.ean = CF.upc
    LEFT JOIN dbo.cod_color AS CO ON EC.cod_color = CO.codigo
    LEFT JOIN dbo.tiendas AS T ON ST.num_local = T.codigo AND T.ini_cliente = ST.ini_cliente
    LEFT JOIN dbo.monitoreo AS M ON EC.ref_modelo = M.modelo AND EC.marca = M.marca
    LEFT JOIN dbo.marca_subclase AS MS ON ST.ini_cliente = MS.ini_cliente AND substring(EC.categoria from 1 for 7) = MS.subcategoria
    LEFT JOIN dbo.marca AS MA ON EC.marca = MA.marca_bd
    LEFT JOIN Valid_Marca_Tipo AS VMT ON VMT.vmt_tipo = M.tipo
        AND VMT.vmt_fit IS NOT DISTINCT FROM M.fit
        AND VMT.vmt_marca = COALESCE(MS.marca, MA.new_marca, EC.marca)
    LEFT JOIN dbo.semanas AS SEM ON (date_trunc('week', ST.fecha))::date = SEM.dia_inicio
    WHERE ST.ini_cliente = %(ini_cliente)s
      AND ST.fecha BETWEEN %(fecha_inicio)s AND %(fecha_fin)s

    UNION ALL

    SELECT
        VT.ini_cliente,
        VT.num_local AS "c_l",
        T.local,
        T.ciudad,
        VT.ean,
        EC.sku,
        CF.sku_madre,
        EC.descripcion_nueva AS "descripcion",
        EC.ref_modelo AS "modelo",
        VMT.vmt_marca AS "marca",
        substring(EC.categoria from 1 for 7) AS subclase,
        M.tipo AS "tipo_programa",
        M.fit AS "fit_estilo",
        CO.color AS "color",
        EC.cod_color AS "cod_color",
        CO.color_hexa AS "color_hexa",
        EC.talla AS "talla",
        (date_trunc('week', VT.fecha))::date AS fecha,
        SEM.n_sem,
        SEM.ano,
        VT.cant AS "v_cant",
        0 AS "s_cant",
        VT.pvp_unit AS "v_pvp"
    FROM dbo.dwh_ventas AS VT
    LEFT JOIN dbo.cat_sku AS EC ON VT.ean = EC.ean
    LEFT JOIN dbo.ecat_fala AS CF ON VT.ean = CF.upc
    LEFT JOIN dbo.cod_color AS CO ON EC.cod_color = CO.codigo
    LEFT JOIN dbo.tiendas AS T ON VT.num_local = T.codigo AND T.ini_cliente = VT.ini_cliente
    LEFT JOIN dbo.monitoreo AS M ON EC.ref_modelo = M.modelo AND EC.marca = M.marca
    LEFT JOIN dbo.marca_subclase AS MS ON VT.ini_cliente = MS.ini_cliente AND substring(EC.categoria from 1 for 7) = MS.subcategoria
    LEFT JOIN dbo.marca AS MA ON EC.marca = MA.marca_bd
    LEFT JOIN Valid_Marca_Tipo AS VMT ON VMT.vmt_tipo = M.tipo
        AND VMT.vmt_fit IS NOT DISTINCT FROM M.fit
        AND VMT.vmt_marca = COALESCE(MS.marca, MA.new_marca, EC.marca)
    LEFT JOIN dbo.semanas AS SEM ON (date_trunc('week', VT.fecha))::date = SEM.dia_inicio
    WHERE VT.ini_cliente = %(ini_cliente)s
      AND VT.fecha BETWEEN %(fecha_inicio)s AND %(fecha_fin)s
) AS syv
GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19
"""

# ── Endpoint: marcas disponibles ──────────────────────────────────────────────
@app.get("/api/marcas")
def get_marcas(ini_cliente: str = Query(default="FL")):
    """Devuelve marcas con stock >= 800 en la fecha más reciente."""
    sql = """
    SELECT DISTINCT COALESCE(MS.marca, MA.new_marca, EC.marca) AS marca
    FROM dbo.dwh_stock AS ST
    LEFT JOIN dbo.cat_sku AS EC ON ST.ean = EC.ean
    LEFT JOIN dbo.marca_subclase AS MS
        ON ST.ini_cliente = MS.ini_cliente
        AND substring(EC.categoria from 1 for 7) = MS.subcategoria
    LEFT JOIN dbo.marca AS MA ON EC.marca = MA.marca_bd
    WHERE ST.ini_cliente = %(ini_cliente)s
      AND ST.fecha = (SELECT MAX(fecha) FROM dbo.dwh_stock WHERE ini_cliente = %(ini_cliente)s)
    GROUP BY 1
    HAVING SUM(ST.cant) >= 800
    ORDER BY 1
    """
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {"ini_cliente": ini_cliente})
                rows = cur.fetchall()
        return {"marcas": [r[0] for r in rows if r[0]]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Endpoint: tipos de programa ───────────────────────────────────────────────
@app.get("/api/tipos_programa")
def get_tipos_programa(marca: str = Query(...), ini_cliente: str = Query(default="FL")):
    """Devuelve los tipos de programa disponibles para una marca en la fecha más reciente."""
    sql = """
    SELECT DISTINCT M.tipo AS tipo
    FROM dbo.monitoreo M
    WHERE M.tipo IS NOT NULL
      AND EXISTS (
          SELECT 1 
          FROM dbo.cat_sku EC
          LEFT JOIN dbo.marca_subclase MS ON substring(EC.categoria from 1 for 7) = MS.subcategoria AND MS.ini_cliente = %(ini_cliente)s
          LEFT JOIN dbo.marca MA ON EC.marca = MA.marca_bd
          WHERE EC.ref_modelo = M.modelo 
            AND EC.marca = M.marca
            AND COALESCE(MS.marca, MA.new_marca, EC.marca) = %(marca)s
      )
    ORDER BY 1
    """
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {"ini_cliente": ini_cliente, "marca": marca})
                rows = cur.fetchall()
        return {"tipos": [r[0] for r in rows if r[0]]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Endpoint: consultar datos ─────────────────────────────────────────────────
@app.get("/api/consultar")
def consultar(
    marca: str = Query(..., description="Nombre de la marca"),
    tipo_programa: str = Query(default="PROGRAMA", description="Tipo de programa (o TODOS)"),
    fecha_inicio_prev: str = Query(..., description="YYYY-MM-DD inicio año anterior"),
    fecha_fin_prev: str = Query(..., description="YYYY-MM-DD fin año anterior"),
    fecha_inicio_curr: str = Query(..., description="YYYY-MM-DD inicio año actual"),
    fecha_fin_curr: str = Query(..., description="YYYY-MM-DD fin año actual"),
    ini_cliente: str = Query(default="FL"),
    stock_threshold: int = Query(default=800),
):
    """Retorna dos arrays de filas (año anterior y año actual) para el dashboard."""
    try:
        fi_prev = datetime.date.fromisoformat(fecha_inicio_prev)
        ff_prev = datetime.date.fromisoformat(fecha_fin_prev)
        fi_curr = datetime.date.fromisoformat(fecha_inicio_curr)
        ff_curr = datetime.date.fromisoformat(fecha_fin_curr)
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de fecha inválido. Usar YYYY-MM-DD")

    def run_query(fecha_inicio, fecha_fin):
        params = {
            "ini_cliente": ini_cliente,
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin,
            "stock_threshold": stock_threshold,
            "marca": marca,
            "tipo_programa": tipo_programa
        }
        
        # Inyectar filtros en la consulta SQL dinámicamente para lograr máxima velocidad
        sql = QUERY_DATA
        marca_filter = " AND COALESCE(MS.marca, MA.new_marca, EC.marca) = %(marca)s "
        tipo_filter = "" if tipo_programa == "TODOS" else " AND M.tipo = %(tipo_programa)s "
        
        sql = sql.replace(
            "AND ST.fecha = (SELECT MAX(fecha) FROM dbo.dwh_stock WHERE ini_cliente = %(ini_cliente)s AND fecha <= %(fecha_fin)s)",
            "AND ST.fecha = (SELECT MAX(fecha) FROM dbo.dwh_stock WHERE ini_cliente = %(ini_cliente)s AND fecha <= %(fecha_fin)s)\n      " + marca_filter
        )
        sql = sql.replace(
            "AND ST.fecha BETWEEN %(fecha_inicio)s AND %(fecha_fin)s",
            "AND ST.fecha BETWEEN %(fecha_inicio)s AND %(fecha_fin)s\n      " + marca_filter + tipo_filter
        )
        sql = sql.replace(
            "AND VT.fecha BETWEEN %(fecha_inicio)s AND %(fecha_fin)s",
            "AND VT.fecha BETWEEN %(fecha_inicio)s AND %(fecha_fin)s\n      " + marca_filter + tipo_filter
        )

        final_sql = f"""
        WITH raw_data AS (
            {sql}
        )
        SELECT COALESCE(json_agg(row_to_json(raw_data))::text, '[]') FROM raw_data
        """

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(final_sql, params)
                json_str = cur.fetchone()[0]

        return json_str

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_prev = executor.submit(run_query, fi_prev, ff_prev)
            future_curr = executor.submit(run_query, fi_curr, ff_curr)
            
            data_prev = future_prev.result()
            data_curr = future_curr.result()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error de consulta: {str(e)}")

    # Build direct JSON response bypassing Python serialization overhead completely
    return Response(
        content='{"prev":' + data_prev + ',"curr":' + data_curr + ',"marca":"' + marca + '"}',
        media_type="application/json"
    )


# ── Servir index.html ─────────────────────────────────────────────────────────
@app.get("/")
def root():
    return FileResponse("index.html")

# Archivos estáticos (si los hay)
if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# Trigger reload
