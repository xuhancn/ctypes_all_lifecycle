import os
import ctypes
from pysrc.cpp_builder import CppBuilder, CppOptions, get_name_and_dir_from_output_file_path
from pysrc.module_manage import DLLWrapper

def test_case():
    cpp_code = os.path.join(os.getcwd(), "csrc", "test_cpp.cpp")
    print("cpp_code: ", cpp_code)

    output_name, output_dir = get_name_and_dir_from_output_file_path(
        cpp_code
    )
    build_options = CppOptions()
    module_builder = CppBuilder(
        name=output_name,
        sources=cpp_code,
        output_dir=output_dir,
        BuildOption=build_options)
    
    module_builder.build()
    module_path = module_builder.get_target_file_path()
    print("module_path: ", module_path)

    module = DLLWrapper(module_path)

    a = 1
    b = 2
    module.DLL.cpp_add.restype = ctypes.c_int
    module.DLL.cpp_add.argtypes = [ctypes.c_int, ctypes.c_int]
    c = module.DLL.cpp_add(a, b)
    print("cpp_add --> c: ", c)

    module.close()


    module = DLLWrapper(module_path)

    a = 2
    b = 3
    module.DLL.cpp_add.restype = ctypes.c_int
    module.DLL.cpp_add.argtypes = [ctypes.c_int, ctypes.c_int]
    c = module.DLL.cpp_add(a, b)
    print("cpp_add --> c: ", c)

    module.close()    
 
if __name__ == "__main__":
    test_case()