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
    cur.execute("""
        SELECT DISTINCT COALESCE(MS.marca, MA.new_marca, EC.marca)
        FROM dbo.dwh_stock AS ST
        LEFT JOIN dbo.cat_sku AS EC ON ST.ean = EC.ean
        LEFT JOIN dbo.marca_subclase AS MS ON ST.ini_cliente = MS.ini_cliente AND substring(EC.categoria from 1 for 7) = MS.subcategoria
        LEFT JOIN dbo.marca AS MA ON EC.marca = MA.marca_bd
        WHERE ST.ini_cliente = 'FL'
          AND ST.fecha = (SELECT MAX(fecha) FROM dbo.dwh_stock WHERE ini_cliente = 'FL')
        LIMIT 1
    """)
    marca = cur.fetchone()[0]
    print("Test brand:", marca)

    sql = """
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
      AND COALESCE(MS.marca, MA.new_marca, EC.marca) = %(marca)s
      AND M.tipo IS NOT NULL
      AND ST.fecha = (SELECT MAX(fecha) FROM dbo.dwh_stock WHERE ini_cliente = 'FL')
    ORDER BY 1
    """

    t0 = time.time()
    cur.execute(sql, {'marca': marca})
    rows = cur.fetchall()
    t1 = time.time()
    print("tipos_programa EXPLAIN took:", t1 - t0)
    for r in rows:
        print(r[0])
