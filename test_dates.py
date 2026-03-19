import os
import psycopg2
from dotenv import load_dotenv

load_dotenv(".env")

conn = psycopg2.connect(
    host=os.getenv("DB_SERVER"),
    port=os.getenv("DB_PORT", 5432),
    dbname=os.getenv("DB_DATABASE"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD")
)
cur = conn.cursor()
cur.execute("SELECT MIN(fecha), MAX(fecha) FROM dbo.dwh_ventas WHERE ini_cliente='FL'")
print("Ventas:", cur.fetchone())
cur.execute("SELECT MIN(fecha), MAX(fecha) FROM dbo.dwh_stock WHERE ini_cliente='FL'")
print("Stock:", cur.fetchone())
