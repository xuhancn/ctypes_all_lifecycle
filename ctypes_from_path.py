import os
import ctypes
from pysrc.cpp_builder import CppBuilder, CppOptions, get_name_and_dir_from_output_file_path
from ctypes import CDLL

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

    module = CDLL(module_path)

    a = 1
    b = 2
    module.cpp_add.restype = ctypes.c_int
    module.cpp_add.argtypes = [ctypes.c_int, ctypes.c_int]
    c = module.cpp_add(a, b)
    print("cpp_add --> c: ", c)

    try:
        '''
        it will occured exception on Windows: AttributeError: function 'close' not found
        but no exception on Linux.
        ref: https://github.com/pytorch/pytorch/pull/132630
        '''
        module.close()
    except Exception as e:
        print("close exception: ", e)

    try:
        '''
        On Linux: it is works well to delete loaded module.
        On Windows: when we delete the loaded module, it will catch exception:
            PermissionError: [WinError 5] 拒绝访问。
        '''
        os.remove(module_path)
    except Exception as e:
        print("remove exception: ", e)
 
if __name__ == "__main__":
    test_case()