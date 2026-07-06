# Trigger firmware (Raspberry Pi Pico, MicroPython)

Generates the shared FSIN pulse for both cameras and strobes the two lasers in
phase with it (default pattern `AB0`: laser A / laser B / dark).

## Flash

1. Install MicroPython on the Pico (hold BOOTSEL, copy the official `.uf2`).
2. Copy `main.py` to the Pico (`mpremote cp main.py :main.py`), reboot.
3. Sanity check: `mpremote` REPL or `echo PING > /dev/ttyACM0` → `ok pong`.

## Wiring

| Pico pin | Goes to |
|---|---|
| GP2 | FSIN/trigger pin of both cameras (fanned out) |
| GP3 | laser A MOSFET gate |
| GP4 | laser B MOSFET gate |
| GP5 | grip button (other leg to GND) |
| GND | common ground with both cameras and laser supplies |

Check the trigger pin location and expected polarity/pulse width in Arducam's
documentation for your exact module, and set the cameras to external-trigger
mode with Arducam's config tool. Adjust `FSIN_PULSE_US` / polarity in
`main.py` if needed.
