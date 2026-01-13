/* Linker script for Frostbite RISC-V VM */
ENTRY(_start)

SECTIONS
{
    . = 0x0;

    .text : {
        *(.text._start)
        *(.text .text.*)
    }

    .rodata : {
        *(.rodata .rodata.*)
    }

    .data : {
        *(.data .data.*)
    }

    .bss : {
        *(.bss .bss.*)
    }

    /DISCARD/ : {
        *(.eh_frame)
        *(.comment)
        *(.riscv.attributes)
    }
}
