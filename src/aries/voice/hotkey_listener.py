"""voice/hotkey_listener.py — hotkey global de Windows para push-to-talk
(`docs/specs/Voice.spec.md`), sin dependencias nuevas: `ctypes` (stdlib)
sobre `user32.dll` en vez de una librería de terceros (`keyboard`/
`pynput`) — decisión del usuario, 2026-09-24.

`RegisterHotKey` es la única forma de capturar una tecla *global* en
Windows (funciona aunque Aries no tenga foco — no tiene ventana visible
en absoluto) sin instalar un hook de bajo nivel más invasivo. Exige una
ventana con loop de mensajes para recibir `WM_HOTKEY`; acá se crea una
ventana "message-only" (`HWND_MESSAGE`) — nunca visible, no aparece en la
barra de tareas, solo existe para que Windows tenga a quién mandarle el
mensaje. El loop corre en su propio hilo (`threading.Thread`, daemon) para
no bloquear el event loop de asyncio — mismo criterio que
`MicrophoneListener`/captura de audio, que también bloquea en un hilo
aparte vía `asyncio.to_thread`.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import itertools
import threading
from collections.abc import Callable

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
# Sin esto, mantener la tecla apretada dispara WM_HOTKEY repetidamente al
# ritmo de repetición del teclado del sistema — un solo evento por
# apretada física es lo que necesita push-to-talk (una pulsación, no un
# hold-to-talk; ver docs/specs/Voice.spec.md).
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010

# Ventana "message-only": Windows nunca la muestra ni le asigna un HWND
# de escritorio real — no hace falta ShowWindow ni nada visible.
HWND_MESSAGE = wintypes.HWND(-3)

_HOTKEY_ID = 1  # un solo hotkey por proceso — no hace falta más de un id
# Windows guarda el WNDPROC a nivel de CLASE al registrarla (WNDCLASS.
# lpfnWndProc), no por ventana — dos instancias de HotkeyListener con el
# mismo nombre de clase terminarían compartiendo el callback de la
# PRIMERA que logró registrarla (verificado empíricamente: un segundo
# HotkeyListener en el mismo proceso recibía WM_HOTKEY pero invocaba el
# `on_press` del primero). Nombre único por instancia, no una constante.
_CLASS_NAME_PREFIX = "AriesVoiceHotkeyListener"
_class_name_counter = itertools.count()

_MODIFIER_NAMES: dict[str, int] = {
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
}


class HotkeyRegistrationError(RuntimeError):
    """La combinación pedida no se pudo registrar (típicamente: ya está
    tomada por otra aplicación) o falló la creación de la ventana oculta
    que necesita `RegisterHotKey` para recibir el evento."""


def _declare_argtypes(user32: ctypes.WinDLL) -> None:
    """Sin esto, ctypes adivina el tipo C de cada argumento a partir del
    valor Python que se le pasa — y falla ("int too long to convert")
    con handles de 64 bits como `hInstance` (un entero Python grande no
    se adivina como puntero, se adivina como `int` de 32 bits). Verificado
    empíricamente: `CreateWindowExW` revienta así sin esta declaración."""
    user32.RegisterClassW.argtypes = [ctypes.c_void_p]
    user32.RegisterClassW.restype = wintypes.ATOM

    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HWND,
        wintypes.HMENU,
        wintypes.HINSTANCE,
        ctypes.c_void_p,
    ]
    user32.CreateWindowExW.restype = wintypes.HWND

    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.DestroyWindow.restype = wintypes.BOOL

    user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
    user32.RegisterHotKey.restype = wintypes.BOOL

    user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.UnregisterHotKey.restype = wintypes.BOOL

    user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.GetMessageW.restype = ctypes.c_int

    user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.TranslateMessage.restype = wintypes.BOOL

    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.restype = ctypes.c_long

    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.DefWindowProcW.restype = ctypes.c_long

    user32.PostQuitMessage.argtypes = [ctypes.c_int]
    user32.PostQuitMessage.restype = None

    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL


def parse_hotkey_combo(combo: str) -> tuple[int, int]:
    """`"ctrl+alt+shift+v"` -> `(modifiers, virtual_key_code)`.

    Solo soporta letras/dígitos sueltos como tecla final (alcanza para el
    caso de uso real: una combinación rara tipo `ctrl+alt+shift+<letra>`
    — no hace falta cubrir F-keys/teclas de navegación todavía)."""
    parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
    if len(parts) < 2:
        raise ValueError(f"Combinación de hotkey inválida (necesita al menos un modificador + una tecla): {combo!r}")

    *mod_names, key = parts
    modifiers = 0
    for name in mod_names:
        if name not in _MODIFIER_NAMES:
            raise ValueError(f"Modificador desconocido en {combo!r}: {name!r} (válidos: {sorted(_MODIFIER_NAMES)})")
        modifiers |= _MODIFIER_NAMES[name]

    if len(key) != 1 or not key.isalnum():
        raise ValueError(f"Tecla no soportada en {combo!r}: {key!r} (por ahora, solo una letra o dígito suelto)")
    # Código de tecla virtual de Win32 para A-Z/0-9 coincide con el ASCII
    # en mayúscula — no hace falta una tabla de conversión.
    vk = ord(key.upper())

    return modifiers, vk


class HotkeyListener:
    """Escucha un hotkey global en un hilo propio y llama a `on_press`
    (sincrónico, corre en ESE hilo — no en el event loop de asyncio) cada
    vez que se presiona. El caller es responsable de puentear al mundo
    async si hace falta (ver `VoicePipeline`, que usa un
    `threading.Event` para eso — nada de `asyncio` acá adentro)."""

    def __init__(self, combo: str, on_press: Callable[[], None]) -> None:
        self._combo = combo
        self._modifiers, self._vk = parse_hotkey_combo(combo)
        self._on_press = on_press
        self._class_name = f"{_CLASS_NAME_PREFIX}_{next(_class_name_counter)}"
        self._thread: threading.Thread | None = None
        self._hwnd: int | None = None
        self._user32: ctypes.WinDLL | None = None
        self._ready = threading.Event()
        self._error: Exception | None = None
        self._wndproc_ref: object | None = None  # referencia viva obligatoria — ver _run

    def start(self) -> None:
        """Arranca el hilo, espera a que el hotkey quede realmente
        registrado (o falle) antes de volver — así un caller sabe de
        entrada si la combinación estaba tomada, en vez de enterarse
        recién cuando alguien la presiona y nunca pasa nada."""
        self._thread = threading.Thread(target=self._run, name="HotkeyListener", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=5.0):
            raise HotkeyRegistrationError(f"Timeout esperando que el listener de hotkey ({self._combo!r}) arrancara")
        if self._error is not None:
            raise self._error

    def stop(self) -> None:
        if self._hwnd is not None and self._user32 is not None:
            self._user32.PostMessageW(self._hwnd, WM_CLOSE, 0, 0)
        if self._thread is not None:
            self._thread.join(timeout=5.0)

    def _run(self) -> None:
        # `use_last_error=True`: sin esto, `ctypes.get_last_error()` no es
        # confiable (ctypes no garantiza preservar el código de error de
        # Windows entre la llamada C y el retorno a Python a menos que se
        # pida explícitamente).
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._user32 = user32
        _declare_argtypes(user32)

        try:
            self._register_and_pump(user32)
        except Exception as error:  # red de seguridad: cualquier falla acá NUNCA debe dejar
            # `start()` colgado esperando `_ready` para siempre — un hilo
            # (a diferencia de una corrutina) que revienta sin capturar
            # simplemente desaparece en silencio, así que sin este except
            # `self._ready.wait(timeout=5)` del lado del caller expiraría
            # con un timeout genérico en vez del error real.
            self._error = error
            self._ready.set()

    def _register_and_pump(self, user32: ctypes.WinDLL) -> None:
        wndproc_type = ctypes.WINFUNCTYPE(ctypes.c_long, wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM)

        def _wndproc(hwnd: int, msg: int, wparam: int, lparam: int) -> int:
            if msg == WM_HOTKEY and wparam == _HOTKEY_ID:
                self._on_press()
                return 0
            if msg == WM_CLOSE:
                user32.DestroyWindow(hwnd)
                return 0
            if msg == WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
            return int(user32.DefWindowProcW(hwnd, msg, wparam, lparam))

        # GC se comería la callback de ctypes si no queda una referencia
        # viva más allá de este método — el loop de mensajes corre
        # indefinidamente después de que este método "termina" de
        # ejecutar el bloque de setup, así que se guarda en el objeto.
        self._wndproc_ref = wndproc_type(_wndproc)

        class _WNDCLASS(ctypes.Structure):
            _fields_ = [
                ("style", ctypes.c_uint),
                ("lpfnWndProc", wndproc_type),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HICON),
                ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
            ]

        wndclass = _WNDCLASS()
        wndclass.lpfnWndProc = self._wndproc_ref
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        # Mismo motivo que _declare_argtypes: sin restype explícito,
        # ctypes trunca el handle de 64 bits que devuelve esta llamada a
        # un `int` de 32 bits por default — corrompiendo el valor en vez
        # de fallar ruidosamente, más peligroso todavía que el
        # "ArgumentError" de CreateWindowExW.
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        wndclass.hInstance = kernel32.GetModuleHandleW(None)
        wndclass.lpszClassName = self._class_name

        _ERROR_CLASS_ALREADY_EXISTS = 1410
        if not user32.RegisterClassW(ctypes.byref(wndclass)):
            last_error = ctypes.get_last_error()
            # `self._class_name` es único por instancia (`_class_name_counter`)
            # así que esto no debería pasar nunca en la práctica — se
            # deja como resguardo defensivo, no como camino esperado (a
            # diferencia de una versión anterior de este código que
            # reusaba un nombre de clase fijo entre instancias: ahí SÍ
            # pasaba siempre en la segunda instancia del mismo proceso,
            # y traía un bug real -- Windows guarda el WNDPROC a nivel de
            # clase, no de ventana, así que la segunda instancia
            # terminaba disparando el callback de la primera).
            if last_error != _ERROR_CLASS_ALREADY_EXISTS:
                raise HotkeyRegistrationError(f"No se pudo registrar la clase de ventana oculta (código {last_error})")

        hwnd = user32.CreateWindowExW(
            0, self._class_name, self._class_name, 0, 0, 0, 0, 0, HWND_MESSAGE, None, wndclass.hInstance, None
        )
        if not hwnd:
            raise HotkeyRegistrationError(f"No se pudo crear la ventana oculta para el hotkey (código {ctypes.get_last_error()})")
        self._hwnd = hwnd

        if not user32.RegisterHotKey(hwnd, _HOTKEY_ID, self._modifiers | MOD_NOREPEAT, self._vk):
            last_error = ctypes.get_last_error()
            user32.DestroyWindow(hwnd)
            self._hwnd = None
            raise HotkeyRegistrationError(
                f"No se pudo registrar el hotkey {self._combo!r} (código {last_error}) "
                "— probablemente ya está tomado por otra aplicación (elegir otra combinación en "
                "Settings.voice_hotkey_combo)."
            )

        self._ready.set()

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        user32.UnregisterHotKey(hwnd, _HOTKEY_ID)
