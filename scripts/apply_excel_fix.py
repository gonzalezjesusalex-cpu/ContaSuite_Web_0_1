"""Reversible code-only correction for an existing isolated local installation."""

import argparse, json, shutil, threading, queue
from datetime import datetime, timezone
from pathlib import Path
from local_setup import marker
from local_runtime import stop, start, alive
from install_release import verify


def apply(source, target, extra_files=()):
    source = source.resolve()
    target = target.resolve()
    marker(target)
    if source == target or target.is_relative_to(source) or source.is_relative_to(target):
        raise ValueError('Elige la carpeta INSTALADA, distinta de la carpeta de esta actualización.')
    verify(source)
    files = ['app/backend/app/company_xlsx.py', 'app/backend/app/company_import_api.py']
    for name in extra_files:
        if name not in {
            'app/agent/agent.py',
            'app/scripts/managed_agent.py',
            'app/scripts/local_runtime.py',
            'app/scripts/windows_service.py',
            'app/backend/app/main.py',
            'app/backend/app/storage/indexer.py',
            'app/backend/app/models.py',
            'app/backend/migrations/versions/0005_index_job_status.py',
        }:
            raise ValueError('Archivo de actualización no permitido.')
        files.append(name)
    files += [p.relative_to(source).as_posix() for p in (source / 'app/frontend/dist').rglob('*') if p.is_file()]
    backup = target / 'updates' / ('excel-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f'))
    backup.mkdir(parents=True, exist_ok=False)
    running = alive(target)
    stop(target)
    previous = {}
    try:
        for name in files:
            destination = target / name
            existed = destination.is_file()
            if destination.is_file():
                saved = backup / name
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(destination, saved)
            previous[name] = existed
        (backup / 'rollback.json').write_text(json.dumps(previous, indent=2), encoding='utf-8')
        for name in files:
            destination = target / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / name, destination)
        if running:
            start(target)
        (target / 'EXCEL_CORREGIDO.txt').write_text(
            'Actualización de código aplicada; base y configuración conservadas.\nRespaldo: ' + str(backup) + '\n',
            encoding='utf-8',
        )
        return {'updated': True, 'backup': str(backup), 'database_migrated': False, 'was_running': running}
    except BaseException:
        # Stop any failed new launch before restoring only the files we changed.
        stop(target)
        for name, existed in previous.items():
            if existed:
                shutil.copy2(backup / name, target / name)
            else:
                (target / name).unlink(missing_ok=True)
        if running:
            start(target)
        raise


def main(extra_files=()):
    import tkinter as tk
    from tkinter import filedialog, messagebox

    window = tk.Tk()
    window.withdraw()
    source = Path(__file__).resolve().parents[2]
    directory = filedialog.askdirectory(
        title='Selecciona la carpeta INSTALADA que contiene LOCAL_INSTALLATION.json', parent=window
    )
    if not directory:
        return
    target = Path(directory)
    try:
        marker(target)
    except Exception:
        messagebox.showerror(
            'ContaSuite',
            'No es la carpeta instalada. Selecciona la que contiene ABRIR_CONTASUITE y LOCAL_INSTALLATION.json.',
            parent=window,
        )
        return
    if not messagebox.askokcancel(
        'Actualizar ContaSuite',
        'Se detendrá temporalmente esta instalación y se actualizarán '
        + ('el agente Windows, el indexador y la interfaz' if extra_files else 'el lector Excel y la interfaz')
        + '. Se conservarán la base, las credenciales y la configuración, con respaldo del código anterior.\n\n'
        + str(target),
        parent=window,
    ):
        return
    window.deiconify()
    window.title('ContaSuite · corrección Excel')
    window.geometry('510x130')
    tk.Label(window, text='Actualizando el importador. Espera a que termine…', padx=20, pady=30).pack()
    events = queue.Queue()

    def worker():
        try:
            events.put((True, apply(source, target, extra_files)))
        except BaseException as exc:
            events.put((False, type(exc).__name__))

    def poll():
        try:
            ok, result = events.get_nowait()
        except queue.Empty:
            window.after(150, poll)
            return
        if ok:
            messagebox.showinfo(
                'ContaSuite',
                'Corrección aplicada. Recarga el navegador con Ctrl + F5.\nSi la aplicación estaba detenida, usa ABRIR_CONTASUITE.',
                parent=window,
            )
        else:
            messagebox.showerror(
                'ContaSuite',
                'No se completó la actualización ('
                + result
                + '). Se intentó restaurar el código anterior; conserva la carpeta updates y revisa los registros. No se ejecutaron migraciones.',
                parent=window,
            )
        window.destroy()

    window.protocol('WM_DELETE_WINDOW', lambda: None)
    threading.Thread(target=worker, daemon=True).start()
    poll()
    window.mainloop()


if __name__ == '__main__':
    main()
