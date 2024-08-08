# This CPP builder is designed to support both Windows and Linux OS.
# The design document please check this RFC: https://github.com/pytorch/pytorch/issues/124245

import copy
import errno
import functools
import json
import logging
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import sysconfig
import warnings
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple, Union

# Windows need setup a temp dir to store .obj files.
_BUILD_TEMP_DIR = "CxxBuild"

# initialize variables for compilation
_IS_LINUX = sys.platform.startswith("linux")
_IS_MACOS = sys.platform.startswith("darwin")
_IS_WINDOWS = sys.platform == "win32"

SUBPROCESS_DECODE_ARGS = ("oem",) if _IS_WINDOWS else ()

log = logging.getLogger(__name__)


@functools.lru_cache(None)
def check_compiler_exist_windows(compiler: str) -> None:
    """
    Check if compiler is ready, in case end user not activate MSVC environment.
    """
    try:
        output_msg = (
            subprocess.check_output([compiler, "/help"], stderr=subprocess.STDOUT)
            .strip()
            .decode(*SUBPROCESS_DECODE_ARGS)
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Compiler: {compiler} is not found.") from exc


def get_cpp_compiler() -> str:
    if _IS_WINDOWS:
        compiler = os.environ.get("CXX", "cl")
        check_compiler_exist_windows(compiler)
    else:
        compiler = os.environ.get("CXX", "gcc")
    return compiler


@functools.lru_cache(None)
def _is_apple_clang(cpp_compiler: str) -> bool:
    version_string = subprocess.check_output([cpp_compiler, "--version"]).decode("utf8")
    return "Apple" in version_string.splitlines()[0]


def _is_clang(cpp_compiler: str) -> bool:
    # Mac OS apple clang maybe named as gcc, need check compiler info.
    if sys.platform == "darwin":
        return _is_apple_clang(cpp_compiler)
    return bool(re.search(r"(clang|clang\+\+)", cpp_compiler))


def _is_gcc(cpp_compiler: str) -> bool:
    if sys.platform == "darwin" and _is_apple_clang(cpp_compiler):
        return False
    return bool(re.search(r"(gcc|g\+\+)", cpp_compiler))


@functools.lru_cache(None)
def _is_msvc_cl(cpp_compiler: str) -> bool:
    if not _IS_WINDOWS:
        return False

    try:
        output_msg = (
            subprocess.check_output([cpp_compiler, "/help"], stderr=subprocess.STDOUT)
            .strip()
            .decode(*SUBPROCESS_DECODE_ARGS)
        )
        return "Microsoft" in output_msg.splitlines()[0]
    except FileNotFoundError as exc:
        return False

    return False


@functools.lru_cache(None)
def is_gcc() -> bool:
    return _is_gcc(get_cpp_compiler())


@functools.lru_cache(None)
def is_clang() -> bool:
    return _is_clang(get_cpp_compiler())


@functools.lru_cache(None)
def is_apple_clang() -> bool:
    return _is_apple_clang(get_cpp_compiler())


@functools.lru_cache(None)
def is_msvc_cl() -> bool:
    return _is_msvc_cl(get_cpp_compiler())


def get_compiler_version_info(compiler: str) -> str:
    env = os.environ.copy()
    env["LC_ALL"] = "C"  # Don't localize output
    try:
        version_string = subprocess.check_output(
            [compiler, "-v"], stderr=subprocess.STDOUT, env=env
        ).decode(*SUBPROCESS_DECODE_ARGS)
    except Exception as e:
        try:
            version_string = subprocess.check_output(
                [compiler, "--version"], stderr=subprocess.STDOUT, env=env
            ).decode(*SUBPROCESS_DECODE_ARGS)
        except Exception as e:
            return ""
    # Mutiple lines to one line string.
    version_string = version_string.replace("\r", "_")
    version_string = version_string.replace("\n", "_")
    return version_string


# =============================== cpp builder ===============================
def _append_list(dest_list: List[str], src_list: List[str]) -> None:
    for item in src_list:
        dest_list.append(copy.deepcopy(item))


def _remove_duplication_in_list(orig_list: List[str]) -> List[str]:
    new_list: List[str] = []
    for item in orig_list:
        if item not in new_list:
            new_list.append(item)
    return new_list


def _create_if_dir_not_exist(path_dir: str) -> None:
    if not os.path.exists(path_dir):
        try:
            Path(path_dir).mkdir(parents=True, exist_ok=True)
        except OSError as exc:  # Guard against race condition
            if exc.errno != errno.EEXIST:
                raise RuntimeError(  # noqa: TRY200 (Use `raise from`)
                    f"Fail to create path {path_dir}"
                )


def _remove_dir(path_dir: str) -> None:
    if os.path.exists(path_dir):
        for root, dirs, files in os.walk(path_dir, topdown=False):
            for name in files:
                file_path = os.path.join(root, name)
                os.remove(file_path)
            for name in dirs:
                dir_path = os.path.join(root, name)
                os.rmdir(dir_path)
        os.rmdir(path_dir)


def run_command_line(cmd_line: str, cwd: str) -> bytes:
    cmd = shlex.split(cmd_line)
    try:
        status = subprocess.check_output(args=cmd, cwd=cwd, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        output = e.output.decode("utf-8")
        raise RuntimeError(status)
    return status


def normalize_path_separator(orig_path: str) -> str:
    if _IS_WINDOWS:
        return orig_path.replace(os.sep, "/")
    return orig_path


class BuildOptionsBase:
    """
    This is the Base class for store cxx build options, as a template.
    Acturally, to build a cxx shared library. We just need to select a compiler
    and maintains the suitable args.
    """

    def __init__(
        self,
        compiler: str = "",
        definitions: Optional[List[str]] = None,
        include_dirs: Optional[List[str]] = None,
        cflags: Optional[List[str]] = None,
        ldflags: Optional[List[str]] = None,
        libraries_dirs: Optional[List[str]] = None,
        libraries: Optional[List[str]] = None,
        passthrough_args: Optional[List[str]] = None,
        aot_mode: bool = False,
        use_absolute_path: bool = False,
        compile_only: bool = False,
    ) -> None:
        self._compiler = compiler
        self._definations: List[str] = definitions or []
        self._include_dirs: List[str] = include_dirs or []
        self._cflags: List[str] = cflags or []
        self._ldflags: List[str] = ldflags or []
        self._libraries_dirs: List[str] = libraries_dirs or []
        self._libraries: List[str] = libraries or []
        # Some args is hard to abstract to OS compatable, passthough it directly.
        self._passthough_args: List[str] = passthrough_args or []

        self._aot_mode: bool = aot_mode
        self._use_absolute_path: bool = use_absolute_path
        self._compile_only: bool = compile_only

    def _remove_duplicate_options(self) -> None:
        self._definations = _remove_duplication_in_list(self._definations)
        self._include_dirs = _remove_duplication_in_list(self._include_dirs)
        self._cflags = _remove_duplication_in_list(self._cflags)
        self._ldflags = _remove_duplication_in_list(self._ldflags)
        self._libraries_dirs = _remove_duplication_in_list(self._libraries_dirs)
        self._libraries = _remove_duplication_in_list(self._libraries)
        self._passthough_args = _remove_duplication_in_list(self._passthough_args)

    def get_compiler(self) -> str:
        return self._compiler

    def get_definations(self) -> List[str]:
        return self._definations

    def get_include_dirs(self) -> List[str]:
        return self._include_dirs

    def get_cflags(self) -> List[str]:
        return self._cflags

    def get_ldflags(self) -> List[str]:
        return self._ldflags

    def get_libraries_dirs(self) -> List[str]:
        return self._libraries_dirs

    def get_libraries(self) -> List[str]:
        return self._libraries

    def get_passthough_args(self) -> List[str]:
        return self._passthough_args

    def get_aot_mode(self) -> bool:
        return self._aot_mode

    def get_use_absolute_path(self) -> bool:
        return self._use_absolute_path

    def get_compile_only(self) -> bool:
        return self._compile_only

    def save_flags_to_file(self, file: str) -> None:
        attrs = {
            "compiler": self.get_compiler(),
            "definitions": self.get_definations(),
            "include_dirs": self.get_include_dirs(),
            "cflags": self.get_cflags(),
            "ldflags": self.get_ldflags(),
            "libraries_dirs": self.get_libraries_dirs(),
            "libraries": self.get_libraries(),
            "passthrough_args": self.get_passthough_args(),
            "aot_mode": self.get_aot_mode(),
            "use_absolute_path": self.get_use_absolute_path(),
            "compile_only": self.get_compile_only(),
        }

        with open(file, "w") as f:
            json.dump(attrs, f)


def _get_warning_all_cflag(warning_all: bool = True) -> List[str]:
    if not _IS_WINDOWS:
        return ["Wall"] if warning_all else []
    else:
        return []


def _get_cpp_std_cflag(std_num: str = "c++17") -> List[str]:
    if _IS_WINDOWS:
        """
        On Windows, only c++20 can support `std::enable_if_t`.
        Ref: https://learn.microsoft.com/en-us/cpp/overview/cpp-conformance-improvements-2019?view=msvc-170#checking-for-abstract-class-types # noqa: B950
        TODO: discuss upgrade pytorch to c++20.
        """
        std_num = "c++20"
        return [f"std:{std_num}"]
    else:
        return [f"std={std_num}"]


def _get_os_related_cpp_cflags(cpp_compiler: str) -> List[str]:
    if _IS_WINDOWS:
        cflags = [
            "wd4819",
            "wd4251",
            "wd4244",
            "wd4267",
            "wd4275",
            "wd4018",
            "wd4190",
            "wd4624",
            "wd4067",
            "wd4068",
            "EHsc",
        ]
    else:
        cflags = ["Wno-unused-variable", "Wno-unknown-pragmas"]
        if _is_clang(cpp_compiler):
            cflags.append("Werror=ignored-optimization-argument")
    return cflags


def _get_optimization_cflags() -> List[str]:
    if _IS_WINDOWS:
        return ["O2"]
    else:
        cflags = ["O0", "g"] 
        cflags.append("ffast-math")
        cflags.append("fno-finite-math-only")

        if sys.platform != "darwin":
            # https://stackoverflow.com/questions/65966969/why-does-march-native-not-work-on-apple-m1
            # `-march=native` is unrecognized option on M1
            if platform.machine() == "ppc64le":
                cflags.append("mcpu=native")
            else:
                cflags.append("march=native")

        return cflags


def _get_shared_cflag(compile_only: bool) -> List[str]:
    if _IS_WINDOWS:
        """
        MSVC `/MD` using python `ucrtbase.dll` lib as runtime.
        https://learn.microsoft.com/en-us/cpp/c-runtime-library/crt-library-features?view=msvc-170
        """
        SHARED_FLAG = ["DLL", "MD"]
    else:
        if compile_only:
            return ["fPIC"]
        if platform.system() == "Darwin" and "clang" in get_cpp_compiler():
            # This causes undefined symbols to behave the same as linux
            return ["shared", "fPIC", "undefined dynamic_lookup"]
        else:
            return ["shared", "fPIC"]

    return SHARED_FLAG


def get_cpp_options(
    cpp_compiler: str,
    compile_only: bool,
    warning_all: bool = True,
    extra_flags: Sequence[str] = (),
) -> Tuple[List[str], List[str], List[str], List[str], List[str], List[str], List[str]]:
    definations: List[str] = []
    include_dirs: List[str] = []
    cflags: List[str] = []
    ldflags: List[str] = []
    libraries_dirs: List[str] = []
    libraries: List[str] = []
    passthough_args: List[str] = []

    cflags = (
        _get_shared_cflag(compile_only)
        + _get_optimization_cflags()
        + _get_warning_all_cflag(warning_all)
        + _get_cpp_std_cflag()
        + _get_os_related_cpp_cflags(cpp_compiler)
    )

    passthough_args.append(" ".join(extra_flags))

    return (
        definations,
        include_dirs,
        cflags,
        ldflags,
        libraries_dirs,
        libraries,
        passthough_args,
    )


class CppOptions(BuildOptionsBase):
    """
    This class is inherited from BuildOptionsBase, and as cxx build options.
    This option need contains basic cxx build option, which contains:
    1. OS related args.
    2. Toolchains related args.
    3. Cxx standard related args.
    Note:
    1. This Options is good for assist modules build, such as x86_isa_help.
    """

    def __init__(
        self,
        compile_only: bool = False,
        warning_all: bool = True,
        extra_flags: Sequence[str] = (),
        use_absolute_path: bool = False,
    ) -> None:
        super().__init__()
        self._compiler = get_cpp_compiler()
        self._use_absolute_path = use_absolute_path
        self._compile_only = compile_only

        (
            definations,
            include_dirs,
            cflags,
            ldflags,
            libraries_dirs,
            libraries,
            passthough_args,
        ) = get_cpp_options(
            cpp_compiler=self._compiler,
            compile_only=compile_only,
            extra_flags=extra_flags,
            warning_all=warning_all,
        )

        _append_list(self._definations, definations)
        _append_list(self._include_dirs, include_dirs)
        _append_list(self._cflags, cflags)
        _append_list(self._ldflags, ldflags)
        _append_list(self._libraries_dirs, libraries_dirs)
        _append_list(self._libraries, libraries)
        _append_list(self._passthough_args, passthough_args)
        self._remove_duplicate_options()


def get_name_and_dir_from_output_file_path(
    file_path: str,
) -> Tuple[str, str]:
    """
    This function help prepare parameters to new cpp_builder.
    Example:
        input_code: /tmp/tmpof1n5g7t/5c/c5crkkcdvhdxpktrmjxbqkqyq5hmxpqsfza4pxcf3mwk42lphygc.cpp
        name, dir = get_name_and_dir_from_output_file_path(input_code)
    Run result:
        name = c5crkkcdvhdxpktrmjxbqkqyq5hmxpqsfza4pxcf3mwk42lphygc
        dir = /tmp/tmpof1n5g7t/5c/

    put 'name' and 'dir' to CppBuilder's 'name' and 'output_dir'.
    CppBuilder --> get_target_file_path will format output path accoding OS:
    Linux: /tmp/tmppu87g3mm/zh/czhwiz4z7ca7ep3qkxenxerfjxy42kehw6h5cjk6ven4qu4hql4i.so
    Windows: [Windows temp path]/tmppu87g3mm/zh/czhwiz4z7ca7ep3qkxenxerfjxy42kehw6h5cjk6ven4qu4hql4i.dll
    """
    name_and_ext = os.path.basename(file_path)
    name, ext = os.path.splitext(name_and_ext)
    dir = os.path.dirname(file_path)

    return name, dir


class CppBuilder:
    """
    CppBuilder is a cpp jit builder, and it supports both Windows, Linux and MacOS.
    Args:
        name:
            1. Build target name, the final target file will append extension type automatically.
            2. Due to the CppBuilder is supports mutliple OS, it will maintains ext for OS difference.
        sources:
            Source code file list to be built.
        BuildOption:
            Build options to the builder.
        output_dir:
            1. The output_dir the taget file will output to.
            2. The default value is empty string, and then the use current dir as output dir.
            3. Final target file: output_dir/name.ext
    """

    def __get_python_module_ext(self) -> str:
        SHARED_LIB_EXT = ".pyd" if _IS_WINDOWS else ".so"
        return SHARED_LIB_EXT

    def __get_object_ext(self) -> str:
        EXT = ".obj" if _IS_WINDOWS else ".o"
        return EXT

    def __init__(
        self,
        name: str,
        sources: Union[str, List[str]],
        BuildOption: BuildOptionsBase,
        output_dir: str = "",
    ) -> None:
        self._compiler = ""
        self._cflags_args = ""
        self._definations_args = ""
        self._include_dirs_args = ""
        self._ldflags_args = ""
        self._libraries_dirs_args = ""
        self._libraries_args = ""
        self._passthough_parameters_args = ""

        self._output_dir = ""
        self._target_file = ""

        self._use_absolute_path: bool = False
        self._aot_mode: bool = False

        self._name = name

        # Code start here, initial self internal veriables firstly.
        self._compiler = BuildOption.get_compiler()
        self._use_absolute_path = BuildOption.get_use_absolute_path()
        self._aot_mode = BuildOption.get_aot_mode()

        """
        TODO: validate and remove:
        if len(output_dir) == 0:
            self._output_dir = os.path.dirname(os.path.abspath(__file__))
        else:
            self._output_dir = output_dir
        """
        self._output_dir = output_dir

        self._compile_only = BuildOption.get_compile_only()
        file_ext = (
            self.__get_object_ext()
            if self._compile_only
            else self.__get_python_module_ext()
        )
        self._target_file = os.path.join(self._output_dir, f"{self._name}{file_ext}")

        if isinstance(sources, str):
            sources = [sources]

        self._sources_args = " ".join(sources)

        for cflag in BuildOption.get_cflags():
            if _IS_WINDOWS:
                self._cflags_args += f"/{cflag} "
            else:
                self._cflags_args += f"-{cflag} "

        for defination in BuildOption.get_definations():
            if _IS_WINDOWS:
                self._definations_args += f"/D {defination} "
            else:
                self._definations_args += f"-D {defination} "

        for inc_dir in BuildOption.get_include_dirs():
            if _IS_WINDOWS:
                self._include_dirs_args += f"/I {inc_dir} "
            else:
                self._include_dirs_args += f"-I{inc_dir} "

        for ldflag in BuildOption.get_ldflags():
            if _IS_WINDOWS:
                self._ldflags_args += f"/{ldflag} "
            else:
                self._ldflags_args += f"-{ldflag} "

        for lib_dir in BuildOption.get_libraries_dirs():
            if _IS_WINDOWS:
                self._libraries_dirs_args += f'/LIBPATH:"{lib_dir}" '
            else:
                self._libraries_dirs_args += f"-L{lib_dir} "

        for lib in BuildOption.get_libraries():
            if _IS_WINDOWS:
                self._libraries_args += f'"{lib}.lib" '
            else:
                self._libraries_args += f"-l{lib} "

        for passthough_arg in BuildOption.get_passthough_args():
            self._passthough_parameters_args += f"{passthough_arg} "

    def get_command_line(self) -> str:
        def format_build_command(
            compiler: str,
            sources: str,
            include_dirs_args: str,
            definations_args: str,
            cflags_args: str,
            ldflags_args: str,
            libraries_args: str,
            libraries_dirs_args: str,
            passthougn_args: str,
            target_file: str,
        ) -> str:
            if _IS_WINDOWS:
                # https://learn.microsoft.com/en-us/cpp/build/walkthrough-compile-a-c-program-on-the-command-line?view=msvc-1704
                # https://stackoverflow.com/a/31566153
                cmd = (
                    f"{compiler} {include_dirs_args} {definations_args} {cflags_args} {sources} "
                    f"{passthougn_args} /LD /Fe{target_file} /link {libraries_dirs_args} {libraries_args} {ldflags_args} "
                )
                cmd = normalize_path_separator(cmd)
            else:
                compile_only_arg = "-c" if self._compile_only else ""
                cmd = re.sub(
                    r"[ \n]+",
                    " ",
                    f"""
                    {compiler} {sources} {definations_args} {cflags_args} {include_dirs_args}
                    {passthougn_args} {ldflags_args} {libraries_args} {libraries_dirs_args} {compile_only_arg} -o {target_file}
                    """,
                ).strip()
            return cmd

        command_line = format_build_command(
            compiler=self._compiler,
            sources=self._sources_args,
            include_dirs_args=self._include_dirs_args,
            definations_args=self._definations_args,
            cflags_args=self._cflags_args,
            ldflags_args=self._ldflags_args,
            libraries_args=self._libraries_args,
            libraries_dirs_args=self._libraries_dirs_args,
            passthougn_args=self._passthough_parameters_args,
            target_file=self._target_file,
        )
        return command_line

    def get_target_file_path(self) -> str:
        return normalize_path_separator(self._target_file)

    def build(self) -> Tuple[bytes, str]:
        """
        It is must need a temperary directory to store object files in Windows.
        After build completed, delete the temperary directory to save disk space.
        """
        _create_if_dir_not_exist(self._output_dir)
        _build_tmp_dir = os.path.join(
            self._output_dir, f"{self._name}_{_BUILD_TEMP_DIR}"
        )
        _create_if_dir_not_exist(_build_tmp_dir)

        build_cmd = self.get_command_line()

        status = run_command_line(build_cmd, cwd=_build_tmp_dir)

        _remove_dir(_build_tmp_dir)
        return status, self._target_file
