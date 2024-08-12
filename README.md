# ctypes_all_lifecycle

## ctypes_cycle.py
This code shows how to manage modules lifecycle via DLLWrapper.

Test on Linux:
```cmd
(xu_pytorch) xu@xu-G3-3590:~/xu_github/ctypes_all_lifecycle$ python ctypes_cycle.py
cpp_code:  /home/xu/xu_github/ctypes_all_lifecycle/csrc/test_cpp.cpp
module_path:  /home/xu/xu_github/ctypes_all_lifecycle/csrc/test_cpp.so
Linux --> initialize
cpp_add --> c:  3
Linux -- > finalize
Linux --> initialize
cpp_add --> c:  5
Linux -- > finalize
(xu_pytorch) xu@xu-G3-3590:~/xu_github/ctypes_all_lifecycle$
```

Test on Windows:
```cmd
(win_mkl_static) D:\xu_git\ctypes_all_lifecycle>python ctypes_cycle.py
cpp_code:  D:\xu_git\ctypes_all_lifecycle\csrc\test_cpp.cpp
module_path:  D:/xu_git/ctypes_all_lifecycle/csrc/test_cpp.pyd
Win --> initialize
cpp_add --> c:  3
Win --> finalize
Win --> initialize
cpp_add --> c:  5
Win --> finalize

(win_mkl_static) D:\xu_git\ctypes_all_lifecycle>
```

## ctypes_from_path.py
This code shows how to manage modules lifecycle via CDLL. CDLL doesn't have `close` attribute, and it will raise error on Windows. I write a `unload_module_from_path` function to close module.

Test on Linux:
```cmd
(xu_pytorch) xu@xu-G3-3590:~/xu_github/ctypes_all_lifecycle$ python ctypes_from_path.py
cpp_code:  /home/xu/xu_github/ctypes_all_lifecycle/csrc/test_cpp.cpp
module_path:  /home/xu/xu_github/ctypes_all_lifecycle/csrc/test_cpp.so
Linux --> initialize
cpp_add --> c:  3
close module success
remove module_path success.
cpp_add --> c:  5
Linux -- > finalize
(xu_pytorch) xu@xu-G3-3590:~/xu_github/ctypes_all_lifecycle$
```

Test on Windows:
```cmd
(win_mkl_static) D:\xu_git\ctypes_all_lifecycle>python ctypes_from_path.py
cpp_code:  D:\xu_git\ctypes_all_lifecycle\csrc\test_cpp.cpp
module_path:  D:/xu_git/ctypes_all_lifecycle/csrc/test_cpp.pyd
Win --> initialize
cpp_add --> c:  3
close exception:  function 'close' not found
remove exception:  [WinError 5] 拒绝访问。: 'D:/xu_git/ctypes_all_lifecycle/csrc/test_cpp.pyd'
Win --> finalize
retry remove module_path success.
Win --> initialize
cpp_add --> c:  5
Win --> finalize
```