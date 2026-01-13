/*
 * Frostbite VM Linker Script (RV64IMAC)
 *
 * Memory Layout:
 *   0x00000000 - 0x0003FFFF : RAM (256KB)
 *   Stack grows down from 0x3FFF0
 */

ENTRY(_start)

MEMORY {
    RAM (rwx) : ORIGIN = 0x00000000, LENGTH = 256K
}

SECTIONS {
    /* Entry point and init code */
    . = 0x0;

    .init : {
        *(.init)
        *(.init.*)
    } > RAM

    /* Code */
    .text : {
        *(.text._start)
        *(.text.main)
        *(.text*)
    } > RAM

    /* Read-only data */
    .rodata : {
        *(.rodata*)
        *(.srodata*)
    } > RAM

    /* Initialized data */
    .data : {
        *(.data*)
        *(.sdata*)
    } > RAM

    /* Uninitialized data (zeroed by CRT) */
    .bss : {
        __bss_start = .;
        *(.bss*)
        *(.sbss*)
        *(COMMON)
        __bss_end = .;
    } > RAM

    /* Heap starts after BSS */
    . = ALIGN(16);
    __heap_start = .;

    /* Stack at top of RAM */
    . = 0x3FFF0;
    __stack_top = .;
}

/* Required symbols */
PROVIDE(__global_pointer$ = . + 0x800);
