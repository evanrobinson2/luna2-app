#!/usr/bin/env python3

import pyfiglet
import random

def show_ascii_banner(text: str):
    """
    Pick a random figlet font and print the given text in that font.
    """
    all_fonts = pyfiglet.FigletFont.getFonts()
    chosen_font = random.choice(all_fonts)
    ascii_art = pyfiglet.figlet_format(text, font=chosen_font)
    return(ascii_art)

def main():
    # 1) Show a big, randomly-fonted "LunaBot" banner
    print(show_ascii_banner("LUNABOT"))
    print(show_ascii_banner("LUNABOT"))
    print(show_ascii_banner("LUNABOT"))
    print(show_ascii_banner("LUNABOT"))
    print(show_ascii_banner("LUNABOT"))

if __name__ == "__main__":
    main()
