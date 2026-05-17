import multiprocessing
import uvicorn

if __name__ == "__main__":
    # Lee automáticamente la cantidad total de núcleos asignados al contenedor/máquina
    nucleos_disponibles = multiprocessing.cpu_count()
    
    print(f"Iniciando servidor FastAPI con {nucleos_disponibles} workers (núcleos).")
    
    # Lanza uvicorn inyectando dinámicamente el número de núcleos encontrados
    uvicorn.run("api:app", host="127.0.0.1", port=8000, workers=nucleos_disponibles)
