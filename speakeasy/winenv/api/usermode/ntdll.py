# Copyright (C) 2020 FireEye, Inc. All Rights Reserved.

import os
import binascii

from .. import api

import speakeasy.winenv.defs.nt.ddk as ddk
import speakeasy.winenv.defs.nt.ntoskrnl as ntos
import speakeasy.windows.common as winemu


class Ntdll(api.ApiHandler):

    """
    Implements exported native functions from ntdll.dll. If a function is not supported
    here, but is supported in the ntoskrnl handler (e.g. NtCreateFile) it will be handled by
    the kernel export handler.
    """

    name = "ntdll"
    apihook = api.ApiHandler.apihook
    impdata = api.ApiHandler.impdata

    def __init__(self, emu):

        super(Ntdll, self).__init__(emu)

        self.funcs = {}
        self.data = {}

        super(Ntdll, self).__get_hook_attrs__(self)

    @apihook("RtlGetLastWin32Error", argc=0)
    def RtlGetLastWin32Error(self, emu, argv, ctx={}):
        """DWORD RtlGetLastWin32Error();"""

        return emu.get_last_error()

    @apihook("RtlFlushSecureMemoryCache", argc=2)
    def RtlFlushSecureMemoryCache(self, emu, argv, ctx={}):
        """DWORD RtlFlushSecureMemoryCache(PVOID arg0, PVOID arg1);"""
        return True

    @apihook("RtlAddVectoredExceptionHandler", argc=2)
    def RtlAddVectoredExceptionHandler(self, emu, argv, ctx={}):
        """
        PVOID AddVectoredExceptionHandler(
            ULONG                       First,
            PVECTORED_EXCEPTION_HANDLER Handler
        );
        """
        First, Handler = argv

        emu.add_vectored_exception_handler(First, Handler)

        return Handler

    @apihook("NtYieldExecution", argc=0)
    def NtYieldExecution(self, emu, argv, ctx={}):
        """
        NtYieldExecution();
        """
        return 0

    @apihook("RtlRemoveVectoredExceptionHandler", argc=1)
    def RtlRemoveVectoredExceptionHandler(self, emu, argv, ctx={}):
        """
        ULONG RemoveVectoredExceptionHandler(
            PVOID Handle
        );
        """
        (Handler,) = argv

        emu.remove_vectored_exception_handler(Handler)

        return Handler

    @apihook("LdrLoadDll", argc=4)
    def LdrLoadDll(self, emu, argv, ctx={}):
        """NTSTATUS
        NTAPI
        LdrLoadDll(
        IN PWSTR SearchPath OPTIONAL,
        IN PULONG LoadFlags OPTIONAL,
        IN PUNICODE_STRING Name,
        OUT PVOID *BaseAddress OPTIONAL
        );"""

        SearchPath, LoadFlags, Name, BaseAddress = argv

        hmod = 0

        req_lib = self.read_unicode_string(Name)
        lib = winemu.normalize_dll_name(req_lib)

        hmod = emu.load_library(lib)

        flags = {
            0x1: "DONT_RESOLVE_DLL_REFERENCES",
            0x10: "LOAD_IGNORE_CODE_AUTHZ_LEVEL",
            0x2: "LOAD_LIBRARY_AS_DATAFILE",
            0x40: "LOAD_LIBRARY_AS_DATAFILE_EXCLUSIVE",
            0x20: "LOAD_LIBRARY_AS_IMAGE_RESOURCE",
            0x200: "LOAD_LIBRARY_SEARCH_APPLICATION_DIR",
            0x1000: "LOAD_LIBRARY_SEARCH_DEFAULT_DIRS",
            0x100: "LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR",
            0x800: "LOAD_LIBRARY_SEARCH_SYSTEM32",
            0x400: "LOAD_LIBRARY_SEARCH_USER_DIRS",
            0x8: "LOAD_WITH_ALTERED_SEARCH_PATH",
        }

        pretty_flags = " | ".join(
            [name for bit, name in flags.items() if LoadFlags & bit]
        )

        if SearchPath:
            argv[0] = self.read_mem_string(SearchPath, 2)

        argv[2] = req_lib
        argv[1] = pretty_flags

        if not hmod:
            STATUS_DLL_NOT_FOUND = 0xC0000135
            return STATUS_DLL_NOT_FOUND

        if BaseAddress:
            self.mem_write(BaseAddress, hmod.to_bytes(self.get_ptr_size(), "little"))

        return 0

    @apihook("LdrGetProcedureAddress", argc=4)
    def LdrGetProcedureAddress(self, emu, argv, ctx={}):
        """
        NTSTATUS LdrGetProcedureAddress(
            HMODULE ModuleHandle,
            PANSI_STRING FunctionName,
            WORD Oridinal,
            OUT PVOID *FunctionAddress
        );
        """

        hmod, proc_name, ordinal, func_addr = argv
        rv = ddk.STATUS_PROCEDURE_NOT_FOUND

        if proc_name:
            fn = ntos.STRING(emu.get_ptr_size())
            fn = self.mem_cast(fn, proc_name)

            proc = self.read_mem_string(fn.Buffer, 1)
            argv[1] = proc

        elif ordinal:
            proc = "ordinal_%d" % (proc_name)

        mods = emu.get_user_modules()
        for mod in mods:
            if mod.get_base() == hmod:
                bn = mod.get_base_name()
                mname, _ = os.path.splitext(bn)
                addr = emu.get_proc(mname, proc)
                rv = ddk.STATUS_SUCCESS
                self.mem_write(func_addr, addr.to_bytes(self.get_ptr_size(), "little"))

        return rv

    @apihook("RtlZeroMemory", argc=2)
    def RtlZeroMemory(self, emu, argv, ctx={}):
        """
        void RtlZeroMemory(
            void*  Destination,
            size_t Length
        );
        """
        dest, length = argv
        buf = b"\x00" * length
        self.mem_write(dest, buf)

    @apihook("NtSetInformationProcess", argc=4)
    def NtSetInformationProcess(self, emu, argv, ctx={}):
        """
        NTSTATUS
        NTAPI
        NtSetInformationProcess(
            _In_ HANDLE ProcessHandle,
            _In_ PROCESSINFOCLASS ProcessInformationClass,
            _In_ PVOID ProcessInformation,
            _In_ ULONG ProcessInformationLength
        );
        """
        return 0

    @apihook("RtlEncodePointer", argc=1)
    def RtlEncodePointer(self, emu, argv, ctx={}):
        """
        PVOID
        NTAPI
        RtlEncodePointer(IN PVOID Pointer)
        """
        (Ptr,) = argv
        # Just increment the pointer for now like kernel32.EncodePointer
        rv = Ptr + 1

        return rv

    @apihook("RtlDecodePointer", argc=1)
    def RtlDecodePointer(self, emu, argv, ctx={}):
        """
        PVOID
        NTAPI
        RtlDecodePointer(IN PVOID Pointer)
        """
        (Ptr,) = argv
        # Just decrement the pointer for now like kernel32.DecodePointer
        rv = Ptr - 1

        return rv

    @apihook("NtWaitForSingleObject", argc=3)
    def NtWaitForSingleObject(self, emu, argv, ctx={}):
        """
        NTSYSAPI
        NTSTATUS
        NtWaitForSingleObject(
            HANDLE         Handle,
            BOOLEAN        Alertable,
            PLARGE_INTEGER Timeout
        );
        """
        hHandle, alertable, timeout = argv

        # Other documented return status are:
        #      STATUS_TIMEOUT = 0x00000102
        #      STATUS_ACCESS_DENIED = 0xC0000022
        #      STATUS_ALERTED = 0x00000101
        #      STATUS_INVALID_HANDLE = 0xC0000008
        #      STATUS_USER_APC = 0x000000C0
        rv = ddk.STATUS_SUCCESS

        return rv

    @apihook("strlen", argc=2)
    def Strlen(self, emu, argv, ctx={}):
        string_ptr, local = argv
        string = self.read_mem_string(string_ptr, 1)
        argv[0] = string
        return len(string)

    @apihook('RtlComputeCrc32', argc=3)
    def RtlComputeCrc32(self, emu, argv, ctx={}):
        '''
        DWORD RtlComputeCrc32(
            DWORD       dwInitial,
            const BYTE* pData,
            INT         iLen
        )
        '''
        dwInitial, pData, iLen = argv

        data_to_compute = self.mem_read(pData, iLen)
        dwInitial = binascii.crc32(data_to_compute)

        return dwInitial
