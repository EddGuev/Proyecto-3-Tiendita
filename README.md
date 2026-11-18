# Proyecto 3 — Tiendita Ed (FastAPI, Pandas y Dashboard)

Continuación del Proyecto 2. La tiendita ya no guarda el inventario en memoria: ahora los productos y las ventas se guardan en archivos CSV que se leen y escriben con Pandas, así que los datos no se pierden al reiniciar la API. Cada compra queda registrada en `ventas.csv` y con eso se arma un dashboard en el frontend con Chart.js.

## Estructura

```
Proyecto-3-Tiendita/
├── backend/
│   ├── main.py          # API con FastAPI, lectura/escritura de CSV con Pandas
│   ├── productos.csv    # Inventario (id, nombre, precio, cantidad)
│   └── ventas.csv       # Registro de ventas (id_venta, producto_id, nombre, precio, cantidad, total, timestamp)
├── frontend/
│   ├── index.html       # Dashboard + catálogo con Bootstrap y Chart.js
│   └── app.js           # Consumo de la API con fetch y armado de gráficas
└── locust.py            # Prueba de carga sobre la compra del producto 3
```

## Inventario inicial

| ID | Producto        | Precio | Stock |
|----|-----------------|--------|-------|
| 1  | Galletas Maria  | 12     | 30    |
| 2  | Fanta           | 18     | 25    |
| 3  | Jugo de Naranja | 22     | **1** |
| 4  | Chocolate       | 25     | 20    |
| 5  | Agua Mineral    | 10     | 50    |
| 6  | Pan Blanco      | 15     | 12    |

El producto 3 se dejó con stock 1 para seguir probando la venta relámpago con Locust.

## Cómo correrlo

### Backend (puerto 8000)

```bash
cd backend
pip install fastapi uvicorn pandas
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

La documentación automática queda en http://127.0.0.1:8000/docs

### Frontend

Se puede abrir `frontend/index.html` directo en el navegador o con Live Server en VS Code. También funciona con el servidor de Python:

```bash
cd frontend
python -m http.server 3000 --bind 127.0.0.1
```

y luego entrar a http://127.0.0.1:3000. El frontend apunta a `http://127.0.0.1:8000`, así que la API tiene que estar levantada antes.

### Locust

```bash
pip install locust
locust -f locust.py --host http://127.0.0.1:8000
```

Interfaz en http://127.0.0.1:8089

## Endpoints

| Método | Ruta                             | Qué hace |
|--------|----------------------------------|----------|
| GET    | `/productos`                     | Regresa todo el inventario |
| GET    | `/productos/{id}`                | Regresa un producto por ID |
| POST   | `/productos`                     | Agrega un producto nuevo al CSV (201) |
| DELETE | `/productos/{id}`                | Elimina el producto del CSV |
| POST   | `/productos/{id}`                | Compra piezas de un producto: descuenta stock y registra la venta |
| GET    | `/dashboard/kpis`                | Transacciones, ingresos totales, ticket promedio y producto estrella |
| GET    | `/dashboard/ventas-por-producto` | Piezas e ingresos por producto (gráfica de barras) |
| GET    | `/dashboard/ventas-por-tiempo`   | Piezas e ingresos agrupados por hora (gráfica de línea) |

Para comprar se puede mandar `{"cantidad": 3}` en el body; si no se manda nada se compra una pieza. Si el producto no existe se regresa 404, y si no alcanza el stock se regresa 400.

## Concurrencia

Al comprar, la API tiene que leer el CSV, revisar el stock, descontar, guardar y registrar la venta. Si dos peticiones hacen eso al mismo tiempo, las dos pueden leer el mismo stock y se vende de más (condición de carrera). Para evitarlo todo ese bloque está dentro de un `asyncio.Lock()`, igual que en el Proyecto 2. Agregar y eliminar productos también usan el lock porque reescriben el mismo archivo.

Con Locust se puede comprobar: aunque lleguen muchas compras al producto 3, solo una sale bien y el stock se queda en 0.

## Autor

Jorge Edwin Guevara Ayala — Programación 4, Proyecto 3.
