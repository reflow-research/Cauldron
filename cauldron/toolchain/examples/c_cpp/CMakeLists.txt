cmake_minimum_required(VERSION 3.15)
project(frostbite_c_example C)

include(${CMAKE_CURRENT_LIST_DIR}/../../scripts/frostbite.cmake)

frostbite_add_executable(hello hello.c)
frostbite_add_executable(syscall_smoke syscalls.c)
