#include "frostbite.h"

int main(void) {
    fb_print("Hello from Frostbite VM!\n");

    for (int i = 0; i < 5; i++) {
        fb_print("The current number is: %d\n", i);
    }

    int8_t a[] = {1, 2, 3, 4};
    int8_t b[] = {4, 3, 2, 1};
    int32_t dot = fb_dot_i8(a, b, 4);

    fb_print("dot computed; exit code is %d\n", dot);
    return dot;
}
