"""Selectores y textos del portal del SAT, aislados para actualizarlos sin tocar la lógica de descarga.

Origen: ContaSuite 0.6 (Declara v0.2.6). Si el SAT cambia la página, sólo este archivo debe cambiar.
"""

# La pantalla de consulta se reconoce por la URL o por los encabezados de la tabla.
CONSULTA_URL_PARTS = ('consulta/consulta', 'pstdcypisr')
CONSULTA_HEADERS = ('NO. DE OPERACION', 'TIPO DE DECLARACION')

# Columnas de la tabla: se buscan por encabezado; si no aparece, se usa el índice del original.
COLUMNS = {
    'operacion': ('NO. DE OPERACION',),
    'tipo': ('TIPO DE DECLARACION',),
    'periodo': ('PERIODO',),
    'ejercicio': ('EJERCICIO',),
}
FALLBACK_INDEX = {'tipo': 2, 'periodo': 6}

# Control PDF de una fila, del más específico al más general.
PDF_CONTROLS = (
    "a:has(img[src*='pdf' i])",
    "a:has(img[alt*='pdf' i])",
    "a:has(img[title*='pdf' i])",
    "button:has(img[src*='pdf' i])",
    "button:has(img[alt*='pdf' i])",
    "input[type='image'][src*='pdf' i]",
    "a[title*='pdf' i]",
    "a[aria-label*='pdf' i]",
    "button[title*='pdf' i]",
)
# El original ubica el icono en la primera celda cuando ninguno de los anteriores coincide.
FIRST_CELL_CONTROLS = "a, button, input[type='image'], [role='button']"

# Controles de paginación: la prueba en seco avisa si la tabla tiene más páginas (el agente sólo lee la visible).
PAGINATION_CONTROLS = (
    "a[rel='next']",
    "[aria-label*='siguiente' i]",
    "a:has-text('Siguiente')",
    "button:has-text('Siguiente')",
    '.pagination',
    '.paginate_button',
)

# Ritmo: una descarga a la vez, con espera máxima por fila y pausa entre filas.
DOWNLOAD_TIMEOUT_MS = 25_000
ROW_PAUSE_MS = 350
# Una fila que falla por red o por tiempo se reintenta; un archivo que no es PDF no (sesión vencida).
RETRIES = 2
RETRY_PAUSE_MS = 2_000
# Descargas seguidas que no son PDF: la sesión del SAT venció y seguir sólo repetiría el error.
MAX_CONSECUTIVE_NOT_PDF = 3

# Entrada guiada (como el original): pestaña «Declara» y luego «Pagos provisionales del ISR». Nunca se fuerza la URL
# del inicio de sesión: si algo no aparece, la persona sigue a mano.
GUIDE_TAB_TEXT = 'Declara'
GUIDE_TAB_CONTROLS = "button, a, [role='button'], [role='tab'], div"
GUIDE_LINK_PATTERN = r'Pagos\s+provisionales\s+del\s+ISR'
GUIDE_WAIT_MS = 15_000
# Personas físicas: su propia dirección de portal (`sat.base_url_fisicas` en la configuración del agente) y la misma
# entrada guiada. Sin probar contra el portal real.

# Acceso con e.firma (rediseño de Declara, 4.4). Sin probar contra el portal real: si algún control no aparece, el
# agente no adivina y la persona termina de iniciar sesión a mano. El captcha de la CIEC siempre lo resuelve la persona.
FIEL_BUTTON_TEXTS = ('e.firma', 'e.Firma', 'FIEL')
FIEL_CER_INPUT = (
    "input[type='file'][accept*='cer' i], input[type='file']#fileCertificate, input[type='file'][name*='cer' i]"
)
FIEL_KEY_INPUT = (
    "input[type='file'][accept*='key' i], input[type='file']#filePrivateKey, input[type='file'][name*='key' i]"
)
FIEL_PASSWORD_INPUT = (
    "input[type='password']#privateKeyPassword, input[type='password'][name*='pass' i], input[type='password']"
)
FIEL_SUBMIT = "button#submit, input#submit, button:has-text('Enviar'), input[type='submit']"
FIEL_WAIT_MS = 20_000
