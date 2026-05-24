#!/usr/bin/env python3
"""Static panel self-test for diagnosing flicker — no app logic, just the matrix.

If a STATIC fill flickers here, the cause is the panel/PWM/power/timing, not
TransitHub. Use it to sweep settings live until the flicker is gone, then copy
the winning values into config.yaml's `matrix:` section.

Run on the Pi (needs root for GPIO timing):
  sudo .venv/bin/python scripts/panel-test.py
  sudo .venv/bin/python scripts/panel-test.py --slowdown 1 --pwm-bits 8
  sudo .venv/bin/python scripts/panel-test.py --mapping adafruit-hat-pwm   # after the GPIO4-18 jumper
"""
import argparse


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--rows", type=int, default=32)
    p.add_argument("--cols", type=int, default=64)
    p.add_argument("--mapping", default="adafruit-hat", help="adafruit-hat or adafruit-hat-pwm")
    p.add_argument("--slowdown", type=int, default=1, help="GPIO slowdown (Pi 3: 1, Pi 4: 3-4)")
    p.add_argument("--pwm-bits", type=int, default=11, help="lower (7-8) = higher refresh = less flicker")
    p.add_argument("--limit-refresh", type=int, default=0,
                   help="cap refresh to a steady Hz (e.g. 100) to stop flicker from rate dips")
    p.add_argument("--brightness", type=int, default=60)
    p.add_argument("--color", default="white", choices=["white", "red", "green", "blue"])
    args = p.parse_args()

    from rgbmatrix import RGBMatrix, RGBMatrixOptions
    o = RGBMatrixOptions()
    o.rows, o.cols = args.rows, args.cols
    o.hardware_mapping = args.mapping
    o.gpio_slowdown = args.slowdown
    o.pwm_bits = args.pwm_bits
    o.limit_refresh_rate_hz = args.limit_refresh
    o.brightness = args.brightness
    o.drop_privileges = False
    o.show_refresh_rate = True   # prints the achieved Hz to the console — watch it

    rgb = {"white": (255, 255, 255), "red": (255, 0, 0),
           "green": (0, 255, 0), "blue": (0, 0, 255)}[args.color]
    matrix = RGBMatrix(options=o)
    canvas = matrix.CreateFrameCanvas()
    canvas.Fill(*rgb)
    matrix.SwapOnVSync(canvas)

    print(f"Static {args.color} @ mapping={args.mapping} slowdown={args.slowdown} "
          f"pwm_bits={args.pwm_bits} limit_refresh={args.limit_refresh}. Watch the refresh Hz above.")
    try:
        input("Flickering? Note the Hz, then Ctrl-C / Enter to quit.\n")
    except (KeyboardInterrupt, EOFError):
        pass


if __name__ == "__main__":
    main()
