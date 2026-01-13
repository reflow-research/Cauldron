# Frostbite VM CMake helper
#
# Usage:
#   include(/path/to/toolchain/scripts/frostbite.cmake)
#   frostbite_add_executable(myprog src/main.c)
#
# Optional environment:
#   FROSTBITE_TOOLCHAIN=/path/to/frostbite/toolchain

if(NOT DEFINED FROSTBITE_TOOLCHAIN)
  if(DEFINED ENV{FROSTBITE_TOOLCHAIN})
    set(FROSTBITE_TOOLCHAIN "$ENV{FROSTBITE_TOOLCHAIN}")
  else()
    get_filename_component(_FB_SCRIPT_DIR "${CMAKE_CURRENT_LIST_DIR}" ABSOLUTE)
    get_filename_component(FROSTBITE_TOOLCHAIN "${_FB_SCRIPT_DIR}/.." ABSOLUTE)
  endif()
endif()

set(FROSTBITE_INCLUDE_DIR "${FROSTBITE_TOOLCHAIN}/include")
set(FROSTBITE_LINKER_SCRIPT "${FROSTBITE_TOOLCHAIN}/lib/frostbite.ld")
set(FROSTBITE_CRT0 "${FROSTBITE_TOOLCHAIN}/lib/crt0.c")
set(FROSTBITE_ALLOC "${FROSTBITE_TOOLCHAIN}/lib/frostbite_alloc.c")
set(FROSTBITE_SOFTFLOAT "${FROSTBITE_TOOLCHAIN}/lib/frostbite_softfloat.c")

set(FROSTBITE_COMPILE_OPTIONS
  -target riscv64
  -march=rv64im
  -mabi=lp64
  -ffreestanding
  -fno-builtin
  -fno-stack-protector
  -fno-exceptions
  -fno-unwind-tables
  -fno-asynchronous-unwind-tables
  -O2
)

set(FROSTBITE_LINK_OPTIONS
  -nostdlib
  -Wl,-T,${FROSTBITE_LINKER_SCRIPT}
)

function(frostbite_add_executable target)
  set(_fb_runtime ${FROSTBITE_CRT0})
  if(EXISTS "${FROSTBITE_ALLOC}")
    list(APPEND _fb_runtime ${FROSTBITE_ALLOC})
  endif()
  if(EXISTS "${FROSTBITE_SOFTFLOAT}")
    list(APPEND _fb_runtime ${FROSTBITE_SOFTFLOAT})
  endif()
  add_executable(${target} ${ARGN} ${_fb_runtime})
  target_include_directories(${target} PRIVATE ${FROSTBITE_INCLUDE_DIR})
  target_compile_options(${target} PRIVATE ${FROSTBITE_COMPILE_OPTIONS})
  target_link_options(${target} PRIVATE ${FROSTBITE_LINK_OPTIONS})
endfunction()
