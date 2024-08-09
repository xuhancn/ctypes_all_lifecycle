# ctypes_all_lifecycle

Test on Linux:
```cmd
(xu_pytorch) xu@xu-G3-3590:~/xu_github/ctypes_all_lifecycle$ python ctypes_cycle.py
cpp_code:  /home/xu/xu_github/ctypes_all_lifecycle/csrc/test_cpp.cpp
module_path:  /home/xu/xu_github/ctypes_all_lifecycle/csrc/test_cpp.so
Linux --> initialize
cpp_add --> c:  3
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

(win_mkl_static) D:\xu_git\ctypes_all_lifecycle>
```