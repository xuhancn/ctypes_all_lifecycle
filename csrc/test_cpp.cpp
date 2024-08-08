#include <stdio.h>

#ifdef _WIN32
#include <windows.h>
#endif



/*
Debug for attach/deattach module
*/
#ifdef _WIN32
void initialize()
{
    printf("initialize\n");
}

void finalize()
{
    printf("finalize\n");
}

BOOL WINAPI DllMain(HINSTANCE hinstDLL,
                    DWORD fdwReason,
                    LPVOID lpReserved)
{
    switch(fdwReason) 
    { 
        case DLL_PROCESS_ATTACH:
            initialize();
            break;

        case DLL_PROCESS_DETACH:
            finalize();
    }
    return TRUE;
}
#else
void __attribute__((constructor)) initialize()
{
    printf("initialize\n");
}

void __attribute__((destructor)) finalize()
{
    printf("finalize\n");
}
#endif