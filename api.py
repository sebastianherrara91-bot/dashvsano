"""
INCOTEXCO Dashboard Comparativo — API Backend v2.0
FastAPI + PostgreSQL (DWH_INCO)
Optimizado: SELECT 6 cols (vs 23), GROUP BY 4 (vs 20), sin JOINs a ecat_fala/cod_color, filtro TIENDA en SQL
"""
from fastapi import FastAPI, Query, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from dotenv import load_dotenv
import psycopg2
import psycopg2.extras
import os, datetime
import concurrent.futures
import json
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

app = FastAPI(title="INCOTEXCO Dashboard API", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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

# ── SQL optimizado ────────────────────────────────────────────────────────────
# v1.1: 23 columnas, GROUP BY 20, JOINs a ecat_fala + cod_color, filtro TIENDA en JS
# v2.0: 6 columnas, GROUP BY 4, sin JOINs innecesarios, T.tipo='TIENDA' en SQL
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
    syv.local,
    syv.ciudad,
    to_char(syv.fecha, 'YY') || '/' || to_char(syv.n_sem, 'FM00') || ' - ' || to_char(syv.fecha, 'MM/DD') AS "semanas",
    SUM(syv.v_cant) AS "cant_venta",
    SUM(syv.s_cant) AS "cant_stock",
    NULLIF(ROUND(SUM(syv.v_cant * syv.v_pvp) / NULLIF(SUM(syv.v_cant), 0), 0), 0) AS "pvp_prom"
FROM (
    SELECT
        T.local,
        T.ciudad,
        (date_trunc('week', ST.fecha))::date AS fecha,
        SEM.n_sem,
        0 AS "v_cant",
        ST.cant AS "s_cant",
        0 AS "v_pvp"
    FROM dbo.dwh_stock AS ST
    JOIN dbo.cat_sku AS EC ON ST.ean = EC.ean
    JOIN dbo.tiendas AS T ON ST.num_local = T.codigo AND T.ini_cliente = ST.ini_cliente AND T.tipo = 'TIENDA' AND UPPER(T.local) != 'CACIQUE'
    LEFT JOIN dbo.monitoreo AS M ON EC.ref_modelo = M.modelo AND EC.marca = M.marca
    LEFT JOIN dbo.marca_subclase AS MS ON ST.ini_cliente = MS.ini_cliente AND substring(EC.categoria from 1 for 7) = MS.subcategoria
    LEFT JOIN dbo.marca AS MA ON EC.marca = MA.marca_bd
    JOIN Valid_Marca_Tipo AS VMT ON VMT.vmt_tipo = M.tipo
        AND VMT.vmt_fit IS NOT DISTINCT FROM M.fit
        AND VMT.vmt_marca = COALESCE(MS.marca, MA.new_marca, EC.marca)
    JOIN dbo.semanas AS SEM ON (date_trunc('week', ST.fecha))::date = SEM.dia_inicio
    WHERE ST.ini_cliente = %(ini_cliente)s
      AND ST.fecha BETWEEN %(fecha_inicio)s AND %(fecha_fin)s

    UNION ALL

    SELECT
        T.local,
        T.ciudad,
        (date_trunc('week', VT.fecha))::date AS fecha,
        SEM.n_sem,
        VT.cant AS "v_cant",
        0 AS "s_cant",
        VT.pvp_unit AS "v_pvp"
    FROM dbo.dwh_ventas AS VT
    JOIN dbo.cat_sku AS EC ON VT.ean = EC.ean
    JOIN dbo.tiendas AS T ON VT.num_local = T.codigo AND T.ini_cliente = VT.ini_cliente AND T.tipo = 'TIENDA' AND UPPER(T.local) != 'CACIQUE'
    LEFT JOIN dbo.monitoreo AS M ON EC.ref_modelo = M.modelo AND EC.marca = M.marca
    LEFT JOIN dbo.marca_subclase AS MS ON VT.ini_cliente = MS.ini_cliente AND substring(EC.categoria from 1 for 7) = MS.subcategoria
    LEFT JOIN dbo.marca AS MA ON EC.marca = MA.marca_bd
    JOIN Valid_Marca_Tipo AS VMT ON VMT.vmt_tipo = M.tipo
        AND VMT.vmt_fit IS NOT DISTINCT FROM M.fit
        AND VMT.vmt_marca = COALESCE(MS.marca, MA.new_marca, EC.marca)
    JOIN dbo.semanas AS SEM ON (date_trunc('week', VT.fecha))::date = SEM.dia_inicio
    WHERE VT.ini_cliente = %(ini_cliente)s
      AND VT.fecha BETWEEN %(fecha_inicio)s AND %(fecha_fin)s
) AS syv
GROUP BY syv.local, syv.ciudad, syv.fecha, syv.n_sem
"""

# ── Endpoint: marcas disponibles ──────────────────────────────────────────────
@app.get("/api/marcas")
def get_marcas(ini_cliente: str = Query(default="FL")):
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
    try:
        fi_prev = datetime.date.fromisoformat(fecha_inicio_prev)
        ff_prev = datetime.date.fromisoformat(fecha_fin_prev)
        fi_curr = datetime.date.fromisoformat(fecha_inicio_curr)
        ff_curr = datetime.date.fromisoformat(fecha_fin_curr)
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de fecha inválido. Usar YYYY-MM-DD")

    def run_query(fecha_inicio, fecha_fin):
        fi_str = fecha_inicio.isoformat()
        ff_str = fecha_fin.isoformat()

        # 1. Obtener max_fecha rápidamente para evitar escaneo completo
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT MAX(fecha) FROM dbo.dwh_stock WHERE ini_cliente = %(ini_cliente)s AND fecha <= %(fecha_fin)s",
                    {"ini_cliente": ini_cliente, "fecha_fin": fecha_fin}
                )
                max_fecha = cur.fetchone()[0]

        if not max_fecha:
            return "[]"

        params = {
            "ini_cliente": ini_cliente,
            "stock_threshold": stock_threshold,
            "marca": marca,
            "tipo_programa": tipo_programa,
            "max_fecha": max_fecha
        }
        
        sql = QUERY_DATA
        
        # Filtros para el CTE Valid_Marca_Tipo (esto filtra al principio y acelera el JOIN)
        marca_filter = " AND COALESCE(MS.marca, MA.new_marca, EC.marca) = %(marca)s "
        tipo_filter = "" if tipo_programa == "TODOS" else " AND M.tipo = %(tipo_programa)s "
        
        sql = sql.replace(
            "AND ST.fecha = (SELECT MAX(fecha) FROM dbo.dwh_stock WHERE ini_cliente = %(ini_cliente)s AND fecha <= %(fecha_fin)s)",
            "AND ST.fecha = %(max_fecha)s\n      " + marca_filter + tipo_filter
        )
        
        # Inline fechas para asegurar el Partition Pruning en PostgreSQL
        sql = sql.replace(
            "AND ST.fecha BETWEEN %(fecha_inicio)s AND %(fecha_fin)s",
            f"AND ST.fecha BETWEEN '{fi_str}' AND '{ff_str}'"
        )
        sql = sql.replace(
            "AND VT.fecha BETWEEN %(fecha_inicio)s AND %(fecha_fin)s",
            f"AND VT.fecha BETWEEN '{fi_str}' AND '{ff_str}'"
        )

        final_sql = f"""
        WITH raw_data AS (
            {sql}
        )
        SELECT COALESCE(json_agg(row_to_json(raw_data))::text, '[]') FROM raw_data
        """

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL work_mem = '1GB';") # Aumentado a 1GB ya que la DB tiene 3GB libres
                cur.execute("SET LOCAL enable_nestloop = off;") # Force Hash Join
                cur.execute(final_sql, params)
                json_str = cur.fetchone()[0]

        return json_str

        return json_str


    def extract_week(s):
        if not s or '/' not in s:
            return -1
        try:
            return int(s.split('/')[1].split(' ')[0])
        except:
            return -1

    def process_data_python(data_prev, data_curr, brand_name):
        weeks_prev_map = {}
        for r in data_prev:
            wn = extract_week(r.get('semanas', ''))
            if wn >= 0:
                weeks_prev_map[wn] = r.get('semanas')
                
        weeks_curr_map = {}
        for r in data_curr:
            wn = extract_week(r.get('semanas', ''))
            if wn >= 0:
                weeks_curr_map[wn] = r.get('semanas')
                
        common_nums = sorted(list(set(weeks_prev_map.keys()).intersection(set(weeks_curr_map.keys()))))
        
        if not common_nums:
            return None
            
        week_labels = [f"S{str(n).zfill(2)}" for n in common_nums]
        num_to_idx = {n: i for i, n in enumerate(common_nums)}
        nw = len(common_nums)
        
        def aggregate(rows):
            map_stores = {}
            for r in rows:
                store = r.get('local', '')
                wn = extract_week(r.get('semanas', ''))
                if wn not in num_to_idx:
                    continue
                idx = num_to_idx[wn]
                if store not in map_stores:
                    map_stores[store] = {
                        'ciudad': r.get('ciudad', ''),
                        'v': [0] * nw,
                        'st': [0] * nw,
                        'vd': [0] * nw
                    }
                
                try:
                    qty = float(r.get('cant_venta') or 0)
                except:
                    qty = 0
                try:
                    pvp = float(r.get('pvp_prom') or 0)
                except:
                    pvp = 0
                try:
                    stock = float(r.get('cant_stock') or 0)
                except:
                    stock = 0
                    
                map_stores[store]['v'][idx] += qty
                map_stores[store]['st'][idx] += stock
                if qty > 0 and pvp > 0:
                    map_stores[store]['vd'][idx] += (qty * pvp)
            return map_stores

        agg_p = aggregate(data_prev)
        agg_c = aggregate(data_curr)
        
        all_s = set(agg_p.keys()).union(set(agg_c.keys()))
        store_names = list(all_s)
        
        stores = {}
        gv25 = [0]*nw; gv26 = [0]*nw; gs25 = [0]*nw; gs26 = [0]*nw; gvd25 = [0]*nw; gvd26 = [0]*nw
        
        for s in store_names:
            p = agg_p.get(s)
            c = agg_c.get(s)
            
            ciudad = (p['ciudad'] if p else '') or (c['ciudad'] if c else '')
            
            v25 = p['v'] if p else [0]*nw
            st25 = p['st'] if p else [0]*nw
            vd25 = p['vd'] if p else [0]*nw
            
            v26 = c['v'] if c else [0]*nw
            st26 = c['st'] if c else [0]*nw
            vd26 = c['vd'] if c else [0]*nw
            
            stores[s] = {
                "ciudad": ciudad,
                "v25": v25, "v26": v26,
                "st25": st25, "st26": st26,
                "vd25": vd25, "vd26": vd26
            }
            
            for i in range(nw):
                gv25[i] += v25[i]
                gv26[i] += v26[i]
                gs25[i] += st25[i]
                gs26[i] += st26[i]
                gvd25[i] += vd25[i]
                gvd26[i] += vd26[i]
                
        store_names.sort(key=lambda x: sum(stores[x]['v25']), reverse=True)
        
        return {
            "week_labels": week_labels,
            "stores": stores,
            "global": {
                "v25": gv25, "v26": gv26,
                "st25": gs25, "st26": gs26,
                "vd25": gvd25, "vd26": gvd26
            },
            "store_order": store_names,
            "brand": brand_name
        }

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_prev = executor.submit(run_query, fi_prev, ff_prev)
            future_curr = executor.submit(run_query, fi_curr, ff_curr)
            data_prev_str = future_prev.result()
            data_curr_str = future_curr.result()
            
            data_prev = json.loads(data_prev_str)
            data_curr = json.loads(data_curr_str)
            
            processed_data = process_data_python(data_prev, data_curr, marca)
            
            if not processed_data:
                # Si no hay data o semanas comunes, retornar empty
                return Response(content='{}', media_type="application/json")
                
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error de consulta: {str(e)}")

    return Response(
        content=json.dumps(processed_data),
        media_type="application/json"
    )

# ── Servir index.html ─────────────────────────────────────────────────────────
@app.get("/")
def root():
    return FileResponse("index.html")

if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")
