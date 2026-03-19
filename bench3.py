import psycopg2, time, os
from dotenv import load_dotenv
from api import QUERY_DATA

load_dotenv()
conn = psycopg2.connect(
    host=os.getenv('DB_SERVER', 'localhost'),
    port=os.getenv('DB_PORT', '5432'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    dbname=os.getenv('DB_DATABASE')
)

params = {
    "ini_cliente": "FL",
    "fecha_inicio": "2024-01-01",
    "fecha_fin": "2024-12-31",
    "stock_threshold": 800,
}

t0 = time.time()
with conn.cursor() as cur:
    cur.execute("EXPLAIN ANALYZE " + QUERY_DATA, params)
    rows = cur.fetchall()
print("QUERY_DATA baseline took:", time.time() - t0)
