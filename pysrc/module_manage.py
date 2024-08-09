import sys
from ctypes import c_void_p, CDLL, cdll
from typing import Any, Callable
from typing_extensions import Self


def is_linux():
    return sys.platform.startswith("linux")

def is_windows():
    return sys.platform == "win32"

class DLLWrapper:
    """A wrapper for a dynamic library."""

    def __init__(
        self,
        lib_path: str,
    ) -> None:
        self.lib_path = lib_path
        self.is_open = False
        self.DLL = cdll.LoadLibrary(lib_path)
        self.is_open = True

    def close(self) -> None:
        if self.is_open:
            self._dlclose()
            self.is_open = False

    def _dlclose(self) -> None:
        f_dlclose = None

        if is_linux():
            syms = CDLL(None)
            if not hasattr(syms, "dlclose"):
                # Apline Linux
                syms = CDLL("libc.so")

            if hasattr(syms, "dlclose"):
                f_dlclose = syms.dlclose
        elif is_windows():
            import _ctypes
            f_dlclose = _ctypes.FreeLibrary
        else:
            raise NotImplementedError("Unsupported env, failed to do dlclose!")

        if f_dlclose is not None:
            if is_linux():
                f_dlclose.argtypes = [c_void_p]
                f_dlclose(self.DLL._handle)
            elif is_windows():
                f_dlclose(self.DLL._handle)
        else:
            raise RuntimeError(
                "dll unloading function was not found, library may not be unloaded properly!"
            )

    def __getattr__(self, name: str) -> Callable[..., None]:
        if not self.is_open:
            raise RuntimeError(f"Cannot use closed DLL library: {self.lib_path}")

        method = getattr(self.DLL, name)

        def _wrapped_func(*args: Any) -> None:
            err = method(*args)
            if err:
                raise RuntimeError(f"Error in function: {method.__name__}")

        return _wrapped_func

    def __enter__(self) -> Self:  # noqa: PYI034
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()
