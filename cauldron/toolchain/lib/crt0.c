/**
 * Frostbite C Runtime Startup (RV64IMAC)
 *
 * This file provides the entry point and initialization for C programs
 * running on the Frostbite VM. It:
 *   1. Sets up the stack pointer
 *   2. Initializes the global pointer (for relaxation)
 *   3. Zeros the BSS section
 *   4. Calls main() or _start()
 *   5. Exits with the return value
 *
 * Compile with: clang -target riscv64 -march=rv64imac -c crt0.c
 */

/* Forward declarations */
void _start(void) __attribute__((weak));
int main(void) __attribute__((weak));

/* BSS section boundaries (from linker script) */
extern char __bss_start[];
extern char __bss_end[];

/* Exit syscall */
static inline __attribute__((noreturn)) void _exit(long code) {
    register long a0 asm("a0") = code;
    register long a7 asm("a7") = 93;
    asm volatile("ecall" : : "r"(a0), "r"(a7));
    __builtin_unreachable();
}

/* Zero BSS section */
static inline void _init_bss(void) {
    for (char *p = __bss_start; p < __bss_end; p++) {
        *p = 0;
    }
}

/* True entry point - called by hardware at address 0 */
void __attribute__((naked, section(".init"))) _entry(void) {
    asm volatile(
        /* Initialize stack pointer to top of memory (256KB - 16, aligned) */
        "lui sp, 0x40\n"
        "addi sp, sp, -16\n"
        /* Initialize global pointer (for relaxation) */
        ".option push\n"
        ".option norelax\n"
        "la gp, __global_pointer$\n"
        ".option pop\n"
        /* Jump to C init */
        "j _crt_init\n"
    );
}

/* C initialization and main call */
void __attribute__((noreturn)) _crt_init(void) {
    _init_bss();

    int ret = 0;
    if (main) {
        ret = main();
    } else if (_start) {
        _start();
    }
    _exit(ret);
}

/* Provide __global_pointer$ symbol */
asm(".global __global_pointer$\n"
    ".hidden __global_pointer$\n"
    ".weak __global_pointer$\n"
    "__global_pointer$ = . + 0x800\n");
