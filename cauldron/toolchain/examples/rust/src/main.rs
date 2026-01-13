#![no_std]
#![no_main]

use core::panic::PanicInfo;
use frostbite_sdk as fb;

#[no_mangle]
pub extern "C" fn main() -> i32 {
    fb::print("Frostbite Rust example\n");

    let a: [i8; 4] = [1, 2, 3, 4];
    let b: [i8; 4] = [4, 3, 2, 1];
    let dot = fb::dot_i8(&a, &b).unwrap_or(0);

    fb::print("dot computed; exit code is dot\n");
    dot
}

#[panic_handler]
fn panic(_info: &PanicInfo) -> ! {
    fb::print("panic\n");
    fb::exit(1);
}
