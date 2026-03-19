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

with conn.cursor() as cur:
    sql_old = """
    EXPLAIN ANALYZE
    SELECT DISTINCT M.tipo AS tipo
    FROM dbo.dwh_stock AS ST
    LEFT JOIN dbo.cat_sku AS EC ON ST.ean = EC.ean
    LEFT JOIN dbo.marca_subclase AS MS
        ON ST.ini_cliente = MS.ini_cliente
        AND substring(EC.categoria from 1 for 7) = MS.subcategoria
    LEFT JOIN dbo.marca AS MA ON EC.marca = MA.marca_bd
    LEFT JOIN dbo.monitoreo AS M ON EC.ref_modelo = M.modelo AND EC.marca = M.marca
    WHERE ST.ini_cliente = 'FL'
      AND COALESCE(MS.marca, MA.new_marca, EC.marca) = 'LINEA MUJER'
      AND M.tipo IS NOT NULL
      AND ST.fecha = (SELECT MAX(fecha) FROM dbo.dwh_stock WHERE ini_cliente = 'FL')
    ORDER BY 1
    """

    sql_new = """
    EXPLAIN ANALYZE
    SELECT DISTINCT M.tipo AS tipo
    FROM dbo.dwh_stock AS ST
    INNER JOIN dbo.cat_sku AS EC ON ST.ean = EC.ean
    LEFT JOIN dbo.marca_subclase AS MS
        ON ST.ini_cliente = MS.ini_cliente
        AND substring(EC.categoria from 1 for 7) = MS.subcategoria
    LEFT JOIN dbo.marca AS MA ON EC.marca = MA.marca_bd
    INNER JOIN dbo.monitoreo AS M ON EC.ref_modelo = M.modelo AND EC.marca = M.marca
    WHERE ST.ini_cliente = 'FL'
      AND COALESCE(MS.marca, MA.new_marca, EC.marca) = 'LINEA MUJER'
      AND M.tipo IS NOT NULL
      AND ST.fecha = (SELECT MAX(fecha) FROM dbo.dwh_stock WHERE ini_cliente = 'FL')
    ORDER BY 1
    """

    t0 = time.time()
    cur.execute(sql_old)
    _ = cur.fetchall()
    print("Old:", time.time() - t0)

    t0 = time.time()
    cur.execute(sql_new)
    _ = cur.fetchall()
    print("New:", time.time() - t0)
