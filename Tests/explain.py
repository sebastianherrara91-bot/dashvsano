import psycopg2
import sys
import os

from api import get_conn, QUERY_DATA

sql = QUERY_DATA
ini_cliente = 'FL'
fecha_inicio = '2025-01-01'
fecha_fin = '2026-03-24'
stock_threshold = 800
marca = 'BEARCLIFF'
tipo_programa = 'PROGRAMA'

marca_filter = " AND COALESCE(MS.marca, MA.new_marca, EC.marca) = %(marca)s "
tipo_filter = " AND M.tipo = %(tipo_programa)s "

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

explain_sql = "EXPLAIN ANALYZE " + sql

params = {
    "ini_cliente": ini_cliente,
    "fecha_inicio": fecha_inicio,
    "fecha_fin": fecha_fin,
    "stock_threshold": stock_threshold,
    "marca": marca,
    "tipo_programa": tipo_programa
}

try:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(explain_sql, params)
            rows = cur.fetchall()
            for r in rows:
                print(r[0])
except Exception as e:
    print("Error:", e)
