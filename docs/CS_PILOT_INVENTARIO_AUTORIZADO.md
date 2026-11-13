# Inventario preliminar autorizado de las carpetas piloto

Se recibió autorización del usuario para utilizar las dos carpetas dentro de la ruta indicada. Se enumeraron exclusivamente metadatos mediante el proveedor local de sólo lectura, con exclusiones obligatorias; no se abrió contenido documental ni se importaron empresas/documentos.

| Identificador | Documentos admitidos | Tamaño en bytes | Incidencias de recorrido |
|---|---:|---:|---:|
| P-01 | 25.289 | 897.714.847 | 0 |
| P-02 | 4.571 | 174.091.274 | 0 |
| Total | 29.860 | 1.071.806.121 | 0 |

El recuento sólo incluye PDF/XML/CER no excluidos; no representa todos los archivos físicos ni una clasificación fiscal. No se calcularon hashes de los contenidos. No hubo operaciones de escritura sobre los originales, conexiones SMB/SAT ni modificación de bases existentes.

El volumen excede el máximo configurable del piloto actual (1.000 documentos/500 MB), además del límite de 5.000 entradas por raíz del recorrido de vista previa. No se ejecutó una vista previa parcial ni se presentaron omisiones como análisis completo. Tampoco se creó una base vacía innecesariamente antes de resolver este límite.

Para continuar hace falta seleccionar un periodo/subconjunto acotado, o implementar y ensayar un flujo reanudable por lotes con conteos globales y detección de UUID entre lotes. No basta con incrementar los límites: deben conservarse integridad, memoria acotada, recuperación, permisos e historial. La autorización de análisis de estas carpetas está recibida; la importación definitiva sigue pendiente de confirmación explícita dentro de ContaSuite.
