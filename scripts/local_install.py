"""Native guided installer and launcher for an independent local test installation."""

import argparse, json, os, queue, sys, threading, webbrowser
from pathlib import Path


def main():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    from datetime import datetime

    parser = argparse.ArgumentParser()
    parser.add_argument('--open', type=Path)
    parser.add_argument('--stop', type=Path)
    parser.add_argument('--configure', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    window = tk.Tk()
    window.title('ContaSuite · instalación de pruebas')
    window.geometry('750x740')
    window.minsize(650, 590)
    canvas = tk.Canvas(window, highlightthickness=0)
    scrollbar = ttk.Scrollbar(window, orient='vertical', command=canvas.yview)
    scrollbar.pack(side='right', fill='y')
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side='left', fill='both', expand=True)
    frame = ttk.Frame(canvas, padding=24)
    content = canvas.create_window((0, 0), window=frame, anchor='nw')
    frame.bind('<Configure>', lambda event: canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.bind('<Configure>', lambda event: canvas.itemconfigure(content, width=event.width))
    canvas.bind_all('<MouseWheel>', lambda event: canvas.yview_scroll(-int(event.delta / 120), 'units'))
    ttk.Label(frame, text='ContaSuite v1.0 RC1', font=('Segoe UI', 20, 'bold')).pack(anchor='w')
    ttk.Label(frame, text='Instalación local independiente · no modifica el piloto existente', wraplength=650).pack(
        anchor='w', pady=(0, 16)
    )
    events = queue.Queue()
    busy = [False]
    progress = tk.StringVar(value='')

    def work(action, on_done):
        if busy[0]:
            return
        busy[0] = True

        def run():
            try:
                events.put(('done', on_done, action()))
            except BaseException as exc:  # noqa: BLE001 - installer UI: shows the failure; installation and logs are kept
                events.put(
                    (
                        'error',
                        str(exc)
                        if isinstance(exc, (ValueError, RuntimeError))
                        else 'No se completó la operación ('
                        + type(exc).__name__
                        + '). La instalación y los registros se conservaron.',
                    )
                )

        threading.Thread(target=run, daemon=True).start()

    def poll():
        while True:
            try:
                event = events.get_nowait()
            except queue.Empty:
                break
            if event[0] == 'progress':
                progress.set(event[1])
            elif event[0] == 'error':
                busy[0] = False
                progress.set('Operación no completada.')
                messagebox.showerror('ContaSuite', event[1], parent=window)
            else:
                busy[0] = False
                event[1](event[2])
        window.after(100, poll)

    def close():
        if busy[0]:
            messagebox.showinfo('ContaSuite', 'Espera a que termine la operación.', parent=window)
        else:
            window.destroy()

    window.protocol('WM_DELETE_WINDOW', close)
    if args.open or args.stop:
        target = (args.open or args.stop).resolve()
        ttk.Label(frame, text='Preparando tu instalación local…').pack(anchor='w')
        ttk.Label(frame, textvariable=progress, wraplength=650).pack(anchor='w', pady=20)
        from local_runtime import start, stop

        def complete(values):
            if args.open:
                webbrowser.open('http://localhost:' + str(values['api_port']))
            else:
                messagebox.showinfo('ContaSuite', 'Aplicación y PostgreSQL detenidos.', parent=window)
            window.destroy()

        window.after(200, lambda: work(lambda: start(target) if args.open else stop(target), complete))
    else:
        configuring = args.configure is not None
        destination = tk.StringVar(
            value=str(args.configure.resolve())
            if configuring
            else str(
                Path(os.environ['LOCALAPPDATA'])
                / 'ContaSuite'
                / ('Pruebas-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
            )
        )
        username = tk.StringVar(value='')
        password = tk.StringVar()
        repeat = tk.StringVar()
        port = tk.StringVar(value='8072')

        def field(label, var, secret=False):
            ttk.Label(frame, text=label).pack(anchor='w')
            entry = ttk.Entry(frame, textvariable=var, show='*' if secret else '')
            entry.pack(fill='x', pady=(0, 7))
            return entry

        entry = field('Carpeta de instalación nueva', destination)
        if configuring:
            entry.configure(state='readonly')
        else:
            field('Tu usuario administrador (sin espacios)', username)
            row = ttk.Frame(frame)
            row.pack(fill='x')
            left = ttk.Frame(row)
            left.pack(side='left', fill='x', expand=True)
            right = ttk.Frame(row)
            right.pack(side='left', fill='x', expand=True, padx=(12, 0))
            for parent, label, var in [
                (left, 'Contraseña (mínimo 12 caracteres)', password),
                (right, 'Repetir contraseña', repeat),
            ]:
                ttk.Label(parent, text=label).pack(anchor='w')
                ttk.Entry(parent, textvariable=var, show='*').pack(fill='x')
            field('Puerto de ContaSuite (8072 para no usar el piloto 8062)', port)
        ttk.Label(frame, text='Carpetas locales autorizadas (opcional, una por línea; hasta 20)').pack(
            anchor='w', pady=(10, 0)
        )
        folders = tk.Text(frame, height=5, wrap='none')
        folders.pack(fill='x')
        if configuring:
            from secure_config import load

            config = load(Path(destination.get()) / 'private/service.json')
            folders.insert('1.0', '\n'.join(json.loads(config['CS_LOCAL_IMPORT_ROOTS'])))

        def browse():
            path = filedialog.askdirectory(parent=window, title='Autorizar carpeta local de documentos')
            if path:
                if folders.get('1.0', 'end').strip():
                    folders.insert('end', '\n')
                folders.insert('end', path)

        ttk.Button(frame, text='Agregar carpeta…', command=browse).pack(anchor='w', pady=5)
        consent = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            frame, text='Autorizo estas rutas. Los archivos sólo se leerán al analizar en ContaSuite.', variable=consent
        ).pack(anchor='w')
        ttk.Label(
            frame,
            text='No se importará nada al instalar. El análisis conserva límites de 200 documentos / 100 MB / 90 s y exige revisión antes de confirmar.',
            wraplength=650,
        ).pack(anchor='w', pady=7)
        ttk.Label(frame, textvariable=progress, wraplength=650).pack(anchor='w', pady=7)

        def submit():
            if busy[0]:
                return
            paths = [v.strip() for v in folders.get('1.0', 'end').splitlines() if v.strip()]
            if paths and not consent.get():
                messagebox.showerror(
                    'ContaSuite', 'Confirma la autorización de las rutas seleccionadas.', parent=window
                )
                return
            target = Path(destination.get())
            from local_setup import install, validate, validate_roots, marker, write_secret

            if configuring:
                try:
                    paths = validate_roots(paths, forbidden=(target,))
                    marker(target)
                except ValueError as exc:
                    messagebox.showerror('ContaSuite', str(exc), parent=window)
                    return

                def update():
                    from local_runtime import stop
                    from secure_config import load

                    stop(target)
                    config = load(target / 'private/service.json')
                    config.update(CS_LOCAL_IMPORT_ROOTS=json.dumps(paths), CS_STORAGE_ALLOWED_ROOTS=json.dumps(paths))
                    write_secret(target / 'private/service.json', config)

                work(
                    update,
                    lambda _: messagebox.showinfo(
                        'ContaSuite',
                        'Carpetas autorizadas guardadas. Abre ABRIR_CONTASUITE para iniciar con esta configuración.',
                        parent=window,
                    ),
                )
            else:
                try:
                    if password.get() != repeat.get():
                        raise ValueError('Las contraseñas no coinciden.')
                    selected_port = int(port.get())
                    validate(root, target, username.get(), password.get(), selected_port, paths)
                except (ValueError, OSError) as exc:
                    messagebox.showerror('ContaSuite', str(exc), parent=window)
                    return
                user = username.get()
                secret = password.get()
                password.set('')
                repeat.set('')

                def complete(values):
                    progress.set('Instalación terminada. Abre ABRIR_CONTASUITE en la carpeta de instalación.')
                    messagebox.showinfo(
                        'ContaSuite',
                        'Instalación preparada.\nUsuario: '
                        + values['username']
                        + '\nUsa la contraseña que elegiste.\n\nCarpeta: '
                        + str(target),
                        parent=window,
                    )
                    os.startfile(str(target))

                work(
                    lambda: install(
                        root, target, user, secret, selected_port, paths, lambda msg: events.put(('progress', msg))
                    ),
                    complete,
                )

        ttk.Button(
            frame, text='Guardar carpetas' if configuring else 'Instalar ContaSuite de pruebas', command=submit
        ).pack(anchor='e', pady=8)
    poll()
    window.mainloop()


if __name__ == '__main__':
    main()
