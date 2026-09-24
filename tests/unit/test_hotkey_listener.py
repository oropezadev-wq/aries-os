"""Pruebas para HotkeyListener.

No hay forma de simular una pulsación de teclado *física* en una corrida
de pytest (headless, sin sesión interactiva) — lo que sí se prueba es
TODA la plomería real de Win32 (ventana oculta, registro del hotkey,
loop de mensajes, callback) usando `PostMessageW`/`SendMessageW` para
entregar el mismo mensaje `WM_HOTKEY` que mandaría el sistema operativo
al presionar la combinación de verdad. Es la forma correcta de probar
esto: no mockea `ctypes`, ejercita el código real contra `user32.dll`
real.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import threading
import time

import pytest

from aries.voice.hotkey_listener import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_SHIFT,
    WM_HOTKEY,
    HotkeyListener,
    HotkeyRegistrationError,
    _declare_argtypes,
    parse_hotkey_combo,
)


def _user32_for_test() -> ctypes.WinDLL:
    """Mismo motivo que dentro del propio módulo: sin `argtypes`
    declarados, `PostMessageW` devuelve éxito pero el mensaje no llega
    armado correctamente a la cola — verificado empíricamente (el mismo
    bug que tenía la implementación real antes de declarar argtypes
    ahí)."""
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    _declare_argtypes(user32)
    return user32


class TestParseHotkeyCombo:
    def test_parses_modifiers_and_letter(self) -> None:
        modifiers, vk = parse_hotkey_combo("ctrl+alt+shift+v")

        assert modifiers == MOD_CONTROL | MOD_ALT | MOD_SHIFT
        assert vk == ord("V")

    def test_parses_single_digit(self) -> None:
        modifiers, vk = parse_hotkey_combo("ctrl+1")

        assert modifiers == MOD_CONTROL
        assert vk == ord("1")

    def test_case_insensitive(self) -> None:
        modifiers, vk = parse_hotkey_combo("CTRL+ALT+V")

        assert modifiers == MOD_CONTROL | MOD_ALT
        assert vk == ord("V")

    def test_rejects_missing_modifier(self) -> None:
        with pytest.raises(ValueError, match="inválida"):
            parse_hotkey_combo("v")

    def test_rejects_multi_char_final_key(self) -> None:
        # "alt" es el último segmento acá -- se interpreta como la tecla
        # final, no como un tercer modificador, y falla por ser multi-char.
        with pytest.raises(ValueError, match="no soportada"):
            parse_hotkey_combo("ctrl+alt")

    def test_rejects_unknown_modifier(self) -> None:
        with pytest.raises(ValueError, match="Modificador desconocido"):
            parse_hotkey_combo("cmd+v")

    def test_rejects_multi_char_key(self) -> None:
        with pytest.raises(ValueError, match="no soportada"):
            parse_hotkey_combo("ctrl+space")


class TestHotkeyListenerRealWin32Plumbing:
    """Combinaciones poco comunes a propósito, para minimizar la chance
    de colisionar con un hotkey que ya tenga registrado otra cosa
    corriendo en la máquina donde se ejecuten estos tests."""

    def test_start_registers_and_stop_cleans_up(self) -> None:
        listener = HotkeyListener("ctrl+alt+shift+9", on_press=lambda: None)
        listener.start()
        try:
            assert listener._hwnd is not None
        finally:
            listener.stop()

    def test_on_press_fires_on_synthetic_wm_hotkey(self) -> None:
        pressed = threading.Event()
        listener = HotkeyListener("ctrl+alt+shift+8", on_press=pressed.set)
        listener.start()
        try:
            user32 = _user32_for_test()
            # Mismo mensaje que mandaría Windows al presionar la
            # combinación real — wparam = id del hotkey (siempre 1, ver
            # _HOTKEY_ID en el módulo).
            posted = user32.PostMessageW(listener._hwnd, WM_HOTKEY, 1, 0)
            assert posted, f"PostMessageW falló (código {ctypes.get_last_error()})"

            assert pressed.wait(timeout=2.0), "on_press no se llamó tras el WM_HOTKEY sintético"
        finally:
            listener.stop()

    def test_on_press_not_called_for_unrelated_message(self) -> None:
        pressed = threading.Event()
        listener = HotkeyListener("ctrl+alt+shift+7", on_press=pressed.set)
        listener.start()
        try:
            user32 = _user32_for_test()
            # WM_HOTKEY con un wparam distinto al id registrado -- no
            # debería disparar on_press (mismo chequeo que hace Windows
            # de verdad cuando hay más de un hotkey registrado por
            # proceso, aunque acá solo se registre uno).
            user32.PostMessageW(listener._hwnd, WM_HOTKEY, 999, 0)
            time.sleep(0.3)

            assert not pressed.is_set()
        finally:
            listener.stop()

    def test_duplicate_combo_raises_registration_error(self) -> None:
        first = HotkeyListener("ctrl+alt+shift+6", on_press=lambda: None)
        first.start()
        try:
            second = HotkeyListener("ctrl+alt+shift+6", on_press=lambda: None)
            with pytest.raises(HotkeyRegistrationError, match="ya está tomado"):
                second.start()
        finally:
            first.stop()

    def test_stop_is_safe_to_call_twice(self) -> None:
        listener = HotkeyListener("ctrl+alt+shift+5", on_press=lambda: None)
        listener.start()
        listener.stop()
        listener.stop()  # no debe lanzar
