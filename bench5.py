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

sql_new = """
    EXPLAIN ANALYZE
    SELECT DISTINCT M.tipo AS tipo
    FROM dbo.monitoreo M
    WHERE M.tipo IS NOT NULL
      AND EXISTS (
          SELECT 1 
          FROM dbo.cat_sku EC
          LEFT JOIN dbo.marca_subclase MS ON substring(EC.categoria from 1 for 7) = MS.subcategoria AND MS.ini_cliente = 'FL'
          LEFT JOIN dbo.marca MA ON EC.marca = MA.marca_bd
          WHERE EC.ref_modelo = M.modelo 
            AND EC.marca = M.marca
            AND COALESCE(MS.marca, MA.new_marca, EC.marca) = 'LINEA MUJER'
      )
    ORDER BY 1
"""

t0 = time.time()
with conn.cursor() as cur:
    cur.execute(sql_new)
    print("Fast query took:", time.time() - t0)
    for r in cur.fetchall():
        print(r[0])
