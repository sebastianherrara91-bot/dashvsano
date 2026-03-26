# INCOTEXCO Dashboard Comparativo - Documentación Técnica y Arquitectura

Este documento sirve como "memoria técnica" e introducción al contexto del proyecto para cualquier agente de Inteligencia Artificial (ej: Claude, ChatGPT) o desarrollador humano que se integre al análisis o mantenimiento de la aplicación.

## 1. Naturaleza del Proyecto
* **Nombre:** DashVentasAno (INCOTEXCO Dashboard Comparativo Interanual).
* **Propósito:** Es una Single Page Application (SPA) que consolida, compara y visualiza interanualmente (Semana a Semana) métricas clave como: *Ventas (cantidades), Inventario (cantidades) y Precios Promedio Ponderados* (PVP) segmentados detalladamente para la operación en "Red Falabella Colombia".
* **Estructura Cero-Fricciones:** En lugar de alojar la página web publicamente en GoDaddy y exponer la base de datos a internet crudo (lo cual causaba graves errores de SSL/CORS), el proyecto consolidó **Frontend y Backend dentro de la misma máquina local** (Un contenedor aislado).


## 2. Pila Tecnológica (Tech Stack)
* **Frontend:** Archivo monolítico `index.html` (Vanilla Javascript, HTML5, CSS Nativo responsivo con sistema `.form-row` de cuadrícula grid y librerías externas de interfaz como `Chart.js` inyectadas estáticamente).
* **Backend:** `FastAPI` (Framework de Python asíncrono ultrarrápido).
* **Base de Datos:** PostgreSQL local en LAN corporativa (Base de datos: `DWH_INCO`).
* **Web Server y Gateway:** `Nginx` y `Uvicorn` (Gestionado mediante `systemd`).


## 3. Infraestructura y Montaje (LXC en Proxmox)
La máquina que sostiene la aplicación en producción es un contenedor LXC con **Ubuntu 24.04** ejecutándose bajo Proxmox y expuesto a internet mediante un túnel NAT/Proxy. 

### Patrón de Despliegue (Systemctl Dæmon)
El backend de Python está administrado por sistema bajo el servicio `ventasapi.service` (`/etc/systemd/system/ventasapi.service`).
* En lugar de especificar `uvicorn` explícitamente y limitarlo al GIL (Global Interpreter Lock) mononúcleo de Python, el sistema corre un archivo intermedio llamado `run.py`.
* `run.py` detecta automáticamente (con `multiprocessing.cpu_count()`) cuántos núcleos/vCPUs tiene el contenedor en Proxmox en el instante de encendido y **escala el Backend creando esa misma cantidad exacta de Workers** nativos para procesar consultas simultáneas (balanceo de carga interno a nivel CPU).

### Red y Proxy Inverso (Nginx)
El puerto 9091 del Mikrotik principal enruta el tráfico hacia el puerto estandar `80` del contenedor Proxmox.
Nginx intercepta el puerto 80 nativo, lo fortalece con escudos anti-ataques (Slowloris/headers), y retransmite las peticiones web en sigilo al puerto local `127.0.0.1:8000` (El nido de los workers de Uvicorn/FastAPI). 
Todo el enrutamiento API usa ubicaciones relativas (ej: `fetch('/api/marcas')`).

### Credenciales y Entorno (Security)
Las credenciales de PostgreSQL jamás se exponen en Git. Se alimentan desde un archivo `.env` manual que reside en el servidor de Proxmox en `/opt/DashVentasAno/.env` utilizando `python-dotenv`.


## 4. Optimizaciones Críticas (Backend & SQL)
El volumen de datos de PostgreSQL `dwh_stock` y `dwh_ventas` contiene millones de registros. Se lograron velocidades de retorno milimétricas mediante tres fuertes inyecciones arquitectónicas:

1. **Paralelismo de Red (I/O) en Python:**
   En el endpoint `/api/consultar`, las peticiones gigantes de "Año Anterior" y "Año Actual" no se ejecutan secuencialmente. Se procesan asíncronamente en paralelo usando `concurrent.futures.ThreadPoolExecutor`, liberando el GIL de Python durante el tiempo de latencia de PostgreSQL e intersecando los tiempos a la mitad.
   
2. **Consultas con Pushdown Dinámico:**
   La consulta maestra (`QUERY_DATA`) **NO** obtiene los agregados de toda la corporación para pasarlos después al filtro de Python (Un gravísimo cuello de botella previo). FastAPI intercepta textualmente la consulta en SQL usando `.replace()` e inyecta literalmente los filtros `marca` y `tipo_programa` dentro de los bloques `WHERE` del CTE (`Valid_Marca_Tipo`), `dwh_stock` y `dwh_ventas` *antes de que se proceda con el gigantesco `GROUP BY` de 19 columnas de la BD*.
   
3. **Omisión de Stock Exhaustivo en Metadatos:**
   El endpoint dinámico que nutre la interfaz de menús deplegables `/api/tipos_programa` ignora toda lectura lineal hacia la enorme tabla de stock (anteriormente la bloqueaba calculando rangos). Ahora procesa directa y exclusivamente combinaciones vivas dentro de `dbo.monitoreo` vinculadas condicionalmente por un `EXISTS` hacia diccionarios de claves en `cat_sku`, reaccionando nativamente en <50 milisegundos.

4. **Tuning de Memoria Dinámica (work_mem):**
   Debido al inmenso tamaño del `UNION ALL` que agrupa años enteros de transacciones contra media docena de tablas maestras, el planificador de Postgres colapsaba al superar su RAM estándar (4MB), lanzando un agónico `External Disk Merge Sort` de >120MB que demoraba la consulta hasta 40 segundos. En `api.py`, la transacción inyecta preventivamente `SET LOCAL work_mem = '256MB';`, forzando cruces nativos en memoria (`HashAggregate`) y desplomando la latencia a ~1 segundo.

5. **Ablación de Excel y Delegación Frontend:**
   Se erradicó completamente el viejo código de carga manual, dependencias de `xlsx.js` y drag-and-drop. El sistema mutó a una arquitectura 100% autogestionada por DB. Para no enloquecer al motor SQL filtrando strings de tiendas en cruces tempranos, el Backend arroja el campo `Tipo_Tienda`, confiando en la extrema velocidad matemática local de Javascript (`index.html`) para purgar las Bodegas de la interfaz en fracciones de milisegundo mediante validaciones ligeras como `!== 'TIENDA'`. Adicionalmente, se configuró auto-selección en caliente para "BEARCLIFF" y rangos retroactivos amplificados a 12 semanas ISO consecutivas.

## 5. Mantenimiento y Actualizaciones del Proyecto
El "Source of Truth" es el repositorio principal en Github. En caso de realizar adaptaciones de código en un ambiente de desarrollo local (como cambios en `api.py` o en estilos `index.html`), luego del `git commit + push`, el pase a producción en Proxmox se resuelve ejecutando esta triada como administrador sobre el contenedor LXC:

```bash
cd /opt/DashVentasAno
git pull
sudo systemctl restart ventasapi
```
*(No es necesario reiniciar Nginx. Bastará recargar el servicio core para que Uvicorn lance al instante a sus "Workers" detectando el nuevo código).*


## 6. Changelog v2.0 — Optimización SQL + Quick Selects

### Backend (`api.py`)
| Aspecto | v1.1 | v2.0 |
|---|---|---|
| SELECT final | 23 columnas | **6 columnas** (`local`, `ciudad`, `semanas`, `cant_venta`, `cant_stock`, `pvp_prom`) |
| GROUP BY | 20 columnas | **4 columnas** (`local`, `ciudad`, `fecha`, `n_sem`) |
| JOIN `ecat_fala` (CF) | presente (lookup UPC) | **eliminado** (no se usa) |
| JOIN `cod_color` (CO) | presente (nombre/hexa color) | **eliminado** (no se usa) |
| JOIN `tiendas` | LEFT JOIN | **INNER JOIN** con `T.tipo = 'TIENDA'` |
| JOIN `Valid_Marca_Tipo` | LEFT JOIN | **INNER JOIN** (descarta filas sin match) |
| JOIN `semanas` | LEFT JOIN | **INNER JOIN** |
| Filtro bodegas | ausente en SQL, hecho en JS | **en SQL** (`T.tipo = 'TIENDA'` en ambos bloques UNION) |
| Líneas de código | 311 | **248** (-20%) |

**Impacto de rendimiento esperado:**
- PostgreSQL procesa menos columnas en el GROUP BY (4 vs 20), reduciendo memoria y tiempo de HashAggregate.
- Se eliminan 2 JOINs completos por bloque UNION (4 JOINs menos en total), reduciendo lookups de I/O.
- INNER JOINs descartan filas huérfanas temprano en el plan, reduciendo el volumen del UNION ALL.
- El JSON de respuesta es ~75% más liviano (6 campos vs 23 por fila), reduciendo serialización y transferencia.
- El frontend ya no recibe ni filtra bodegas (antes descartaba filas post-descarga).

### Frontend (`index.html`)
- **Eliminado:** Filtro `Tipo_Tienda` en JavaScript (`processData`). Ahora el SQL garantiza solo tiendas retail.
- **Agregado:** Quick Selects con 3 botones de período rápido:
  - **Últimas 4 semanas** — calcula semanas ISO cerradas hacia atrás, compara vs mismo rango año anterior.
  - **Últimas 8 semanas** — ídem con 8 semanas (es el default al cargar).
  - **Año a la fecha** — desde semana ISO 01 del año actual hasta la semana actual, vs mismo rango año anterior.
- Los Quick Selects pre-llenan los 4 campos de semana (`input type="week"`) y el usuario puede ajustar manualmente después.
- `processData` solo accede a los 6 campos que devuelve el API: `r.local`, `r.ciudad`, `r.semanas`, `r.cant_venta`, `r.cant_stock`, `r.pvp_prom`.
