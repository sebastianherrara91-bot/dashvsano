import psycopg2, time, os
from dotenv import load_dotenv

load_dotenv()
conn = psycopg2.connect(
    host=os.getenv('DB_SERVER', 'localhost'),
    port=os.getenv('DB_PORT', '5432'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    dbname=os.getenv('DB_DATABASE')
)

sql1 = """
    SELECT DISTINCT M.tipo AS tipo
    FROM dbo.dwh_stock AS ST
    LEFT JOIN dbo.cat_sku AS EC ON ST.ean = EC.ean
    LEFT JOIN dbo.marca_subclase AS MS
        ON ST.ini_cliente = MS.ini_cliente
        AND substring(EC.categoria from 1 for 7) = MS.subcategoria
    LEFT JOIN dbo.marca AS MA ON EC.marca = MA.marca_bd
    LEFT JOIN dbo.monitoreo AS M ON EC.ref_modelo = M.modelo AND EC.marca = M.marca
    WHERE ST.ini_cliente = 'FL'
      AND COALESCE(MS.marca, MA.new_marca, EC.marca) = 'NAF NAF'
      AND M.tipo IS NOT NULL
      AND ST.fecha = (SELECT MAX(fecha) FROM dbo.dwh_stock WHERE ini_cliente = 'FL')
"""

t0 = time.time()
with conn.cursor() as cur:
    cur.execute(sql1)
    rows1 = cur.fetchall()
print('Complex query took:', time.time() - t0, rows1)

sql2 = """
    SELECT DISTINCT M.tipo AS tipo
    FROM dbo.monitoreo AS M
    LEFT JOIN dbo.marca AS MA ON M.marca = MA.marca_bd
    WHERE COALESCE(MA.new_marca, M.marca) = 'NAF NAF'
      AND M.tipo IS NOT NULL
"""
t0 = time.time()
with conn.cursor() as cur:
    cur.execute(sql2)
    rows2 = cur.fetchall()
print('Simple query took:', time.time() - t0, rows2)
