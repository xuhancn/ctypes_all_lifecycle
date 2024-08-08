import os
from pysrc.cpp_builder import CppBuilder, CppOptions, get_name_and_dir_from_output_file_path


def test_case():
    cpp_code = os.path.join(os.getcwd(), "csrc", "test_cpp.cpp")
    print("cpp_code: ", cpp_code)



 
if __name__ == "__main__":
    test_case()