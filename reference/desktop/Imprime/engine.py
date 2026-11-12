"""PDF layout and Windows spooler. UI-free; no global printer changes."""
from dataclasses import dataclass
from pathlib import Path
import sys
import fitz
from PIL import Image, ImageOps

PAPERS = {'Carta': (1, 612, 792), 'A4': (9, 595.276, 841.89), 'Legal': (5, 612, 1008)}

@dataclass(frozen=True)
class Settings:
    printer: str = ''
    paper: str = 'Carta'
    orientation: str = 'Automática'
    scale: str = 'Ajustar a página'
    copies: int = 1
    duplex: str = 'Una cara'
    color: str = 'Color'
    dpi: int = 300

class PrintCancelled(Exception):
    pass

def pages_from_text(text, count):
    """One-based inclusive ranges, returned as unique ordered zero-based pages."""
    if not text.strip():
        return list(range(count))
    result = []
    for part in text.split(','):
        bits = part.strip().split('-')
        if len(bits) not in (1, 2) or any(not b.strip().isdigit() for b in bits):
            raise ValueError('Escribe páginas como 1, 3-5, 8.')
        a, b = int(bits[0]), int(bits[-1])
        if not 1 <= a <= b <= count:
            raise ValueError(f'Las páginas deben estar entre 1 y {count}, en orden ascendente por rango.')
        for n in range(a-1, b):
            if n not in result:
                result.append(n)
    return result

def inspect_pdf(path):
    with fitz.open(path) as doc:
        if doc.needs_pass:
            raise ValueError('PDF protegido con contraseña. Abre una copia sin protección.')
        if not doc.is_pdf or not doc.page_count:
            raise ValueError('El archivo no es un PDF válido con páginas.')
        return doc.page_count

def paper_points(settings, first_rect):
    _, w, h = PAPERS[settings.paper]
    if settings.orientation == 'Horizontal' or (settings.orientation == 'Automática' and first_rect.width > first_rect.height):
        w, h = h, w
    return w, h

def placement(page_w, page_h, area_w, area_h, scale):
    factor = min(area_w/page_w, area_h/page_h) if scale == 'Ajustar a página' else 1.0
    w, h = page_w*factor, page_h*factor
    return (area_w-w)/2, (area_h-h)/2, w, h

def preview(path, page_index, settings, max_size=(850, 1000)):
    """Paper preview with physical page size; hardware margins are printer dependent."""
    with fitz.open(path) as doc:
        pw, ph = paper_points(settings, doc[0].rect)
        factor = min(max_size[0]/pw, max_size[1]/ph)
        sheet = Image.new('RGB', (max(1, round(pw*factor)), max(1, round(ph*factor))), 'white')
        page = doc[page_index]
        x, y, w, h = placement(page.rect.width, page.rect.height, pw, ph, settings.scale)
        render_scale = min(factor*w/page.rect.width, 3)
        pix = page.get_pixmap(matrix=fitz.Matrix(render_scale, render_scale), alpha=False, colorspace=fitz.csRGB)
        im = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
        if settings.color == 'Escala de grises':
            im = ImageOps.grayscale(im).convert('RGB')
        im = im.resize((max(1, round(w*factor)), max(1, round(h*factor))), Image.Resampling.LANCZOS)
        sheet.paste(im, (round(x*factor), round(y*factor)))
        return sheet

def windows_modules():
    if sys.platform != 'win32':
        raise RuntimeError('La impresión requiere Windows. La vista previa funciona sin impresora.')
    import win32print, win32gui
    from PIL import ImageWin
    return win32print, win32gui, ImageWin

def printers():
    wp, _, _ = windows_modules()
    names = sorted({p[2] for p in wp.EnumPrinters(2 | 4)}, key=str.casefold)
    try:
        default = wp.GetDefaultPrinter()
    except Exception:
        default = ''
    return names, default

def print_pdf(path, settings, pages, cancel, progress=lambda: None):
    wp, wg, imagewin = windows_modules()
    with fitz.open(path) as doc:
        if cancel.is_set():
            raise PrintCancelled()
        hprinter = wp.OpenPrinter(settings.printer)
        try:
            dm = wp.GetPrinter(hprinter, 2)['pDevMode']
            if dm is None:
                raise RuntimeError('El controlador no devolvió configuración de impresión.')
            dm.PaperSize = PAPERS[settings.paper][0]
            dm.PaperLength = 0
            dm.PaperWidth = 0
            dm.Fields = (dm.Fields & ~(0x0C | 0x10000)) | 0x01 | 0x02 | 0x1000 | 0x100 | 0x800
            pw, ph = paper_points(settings, doc[0].rect)
            dm.Orientation = 2 if pw > ph else 1
            dm.Duplex = {'Una cara': 1, 'Borde largo': 2, 'Borde corto': 3}[settings.duplex]
            dm.Copies = 1  # application produces collated copies
            dm.Color = 1 if settings.color == 'Escala de grises' else 2
            if wp.DocumentProperties(0, hprinter, settings.printer, dm, dm, 10) < 0:
                raise RuntimeError('El controlador rechazó los ajustes.')
            if dm.PaperSize != PAPERS[settings.paper][0] or dm.Orientation != (2 if pw > ph else 1):
                raise RuntimeError('La impresora no aceptó el papel u orientación solicitados.')
            if dm.Duplex != {'Una cara': 1, 'Borde largo': 2, 'Borde corto': 3}[settings.duplex]:
                raise RuntimeError('La impresora no aceptó la opción de doble cara.')
            for copy in range(settings.copies):
                if cancel.is_set():
                    raise PrintCancelled()
                dc = wg.CreateDC('WINSPOOL', settings.printer, dm)
                started = False
                try:
                    wp.StartDoc(dc, (f'{Path(path).name} · copia {copy+1}', None, None, 0))
                    started = True
                    aw, ah = wp.GetDeviceCaps(dc, 8), wp.GetDeviceCaps(dc, 10)
                    dx, dy = wp.GetDeviceCaps(dc, 88), wp.GetDeviceCaps(dc, 90)
                    for index in pages:
                        if cancel.is_set():
                            raise PrintCancelled()
                        page = doc[index]
                        # Physical units ensure 100% scale even with asymmetric printer DPI.
                        x, y, w, h = placement(page.rect.width, page.rect.height, aw*72/dx, ah*72/dy, settings.scale)
                        pix = page.get_pixmap(matrix=fitz.Matrix(settings.dpi/72, settings.dpi/72), alpha=False, colorspace=fitz.csRGB)
                        im = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
                        if settings.color == 'Escala de grises':
                            im = ImageOps.grayscale(im).convert('RGB')
                        wp.StartPage(dc)
                        imagewin.Dib(im).draw(dc, (round(x*dx/72), round(y*dy/72), round((x+w)*dx/72), round((y+h)*dy/72)))
                        wp.EndPage(dc)
                        progress()
                    if cancel.is_set():
                        raise PrintCancelled()
                    wp.EndDoc(dc)
                    started = False
                except BaseException:
                    if started:
                        wp.AbortDoc(dc)
                    raise
                finally:
                    wg.DeleteDC(dc)
        finally:
            wp.ClosePrinter(hprinter)
