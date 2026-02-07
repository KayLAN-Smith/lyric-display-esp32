#!/usr/bin/env python3
"""
ASCII Art Fish Animation
A fun terminal animation of fish swimming across the screen.
"""

import sys
import time
import os
import random

# Fish frames for animation (swimming motion)
FISH_FRAMES = [
    [
        "       ><>",
        "      ><>",
        "     ><>",
    ],
    [
        "       ><))°>",
        "      ><))°>",
        "     ><))°>",
    ],
    [
        "       ><)))°>",
        "      ><)))°>",
        "     ><)))°>",
    ],
    [
        "       ><))°>",
        "      ><))°>",
        "     ><))°>",
    ],
]

# Different fish types
FISH_TYPES = [
    ["  ><>"],
    ["  ><))°>"],
    ["  ><)))°>"],
    ["  ><(((°>"],  # Fish going left
    ["  <°)))><"],  # Fish going left
    ["  <°))><"],   # Fish going left
    [
        "    /\\",
        "><_/  \\_",
        "   \\__/",
    ],
    [
        "       ..",
        "     ><'>",
    ],
    [
        "  ,__,",
        " >.  )_",
        "   \\/  \\",
        "    \\__/",
    ],
]

# Big fish art
BIG_FISH = [
    "                 ___",
    "    _____       /   \\",
    "   /     \\     /     \\",
    "  /       \\___/       \\",
    " /    O                 \\",
    "/                        >",
    " \\                      /",
    "  \\                    /",
    "   \\                  /",
    "    \\                /",
    "     \\______________/",
]

BUBBLE = "°"
SEAWEED_FRAMES = [
    ["}", "{", "}", "{"],
    ["{", "}", "{", "}"],
]


def clear_screen():
    """Clear the terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')


def get_terminal_size():
    """Get terminal dimensions."""
    try:
        columns, rows = os.get_terminal_size()
        return columns, rows
    except OSError:
        return 80, 24


def create_ocean(width, height):
    """Create an empty ocean (2D array of spaces)."""
    return [[' ' for _ in range(width)] for _ in range(height)]


def draw_bubbles(ocean, bubbles, width, height):
    """Draw bubbles on the ocean."""
    new_bubbles = []
    for x, y in bubbles:
        y -= 1  # Bubbles rise
        if y >= 0 and x < width:
            ocean[y][x] = BUBBLE
            new_bubbles.append((x, y))

    # Randomly add new bubbles
    if random.random() < 0.3:
        new_bubbles.append((random.randint(0, width - 1), height - 1))

    return new_bubbles


def draw_seaweed(ocean, frame, width, height):
    """Draw animated seaweed at the bottom."""
    seaweed_pattern = SEAWEED_FRAMES[frame % 2]
    seaweed_positions = [int(width * 0.1), int(width * 0.3), int(width * 0.7), int(width * 0.9)]

    for i, pos in enumerate(seaweed_positions):
        if pos < width:
            for j, char in enumerate(seaweed_pattern):
                y = height - 1 - j
                if y >= 0:
                    ocean[y][pos] = char


def draw_fish(ocean, fish_art, x, y, width, height):
    """Draw a fish on the ocean at position (x, y)."""
    for i, line in enumerate(fish_art):
        row = y + i
        if 0 <= row < height:
            for j, char in enumerate(line):
                col = x + j
                if 0 <= col < width and char != ' ':
                    ocean[row][col] = char


def render_ocean(ocean):
    """Render the ocean to a string."""
    # Add water effect at top
    output = "~" * len(ocean[0]) + "\n"
    for row in ocean:
        output += ''.join(row) + '\n'
    # Add sandy bottom
    output += "." * len(ocean[0])
    return output


def swimming_fish_animation():
    """Main animation showing fish swimming across the screen."""
    width, height = get_terminal_size()
    width = min(width - 1, 100)
    height = min(height - 4, 30)

    # Fish state: [fish_art, x, y, speed, direction]
    fish_list = []

    # Add some initial fish
    for _ in range(5):
        fish_art = random.choice(FISH_TYPES[:3])  # Right-swimming fish
        x = random.randint(-20, width)
        y = random.randint(1, height - 3)
        speed = random.uniform(0.5, 2)
        fish_list.append([fish_art, x, y, speed, 1])  # 1 = right

    bubbles = []
    frame = 0

    print("\033[?25l", end="")  # Hide cursor

    try:
        while True:
            ocean = create_ocean(width, height)

            # Draw seaweed
            draw_seaweed(ocean, frame, width, height)

            # Draw and move bubbles
            bubbles = draw_bubbles(ocean, bubbles, width, height)

            # Draw and move fish
            new_fish_list = []
            for fish_data in fish_list:
                fish_art, x, y, speed, direction = fish_data

                # Move fish
                x += speed * direction

                # If fish is off screen, respawn it
                if direction == 1 and x > width + 10:
                    fish_art = random.choice(FISH_TYPES[:3])
                    x = -len(fish_art[0])
                    y = random.randint(1, height - 3)
                    speed = random.uniform(0.5, 2)
                elif direction == -1 and x < -20:
                    fish_art = random.choice(FISH_TYPES[3:6])
                    x = width
                    y = random.randint(1, height - 3)
                    speed = random.uniform(0.5, 2)

                # Slight vertical wobble
                if random.random() < 0.1:
                    y += random.choice([-1, 1])
                    y = max(1, min(height - 3, y))

                draw_fish(ocean, fish_art, int(x), int(y), width, height)
                new_fish_list.append([fish_art, x, y, speed, direction])

            fish_list = new_fish_list

            # Occasionally add new fish
            if random.random() < 0.02 and len(fish_list) < 10:
                if random.random() < 0.5:
                    fish_art = random.choice(FISH_TYPES[:3])
                    x = -len(fish_art[0])
                    direction = 1
                else:
                    fish_art = random.choice(FISH_TYPES[3:6])
                    x = width
                    direction = -1
                y = random.randint(1, height - 3)
                speed = random.uniform(0.5, 2)
                fish_list.append([fish_art, x, y, speed, direction])

            # Render
            clear_screen()
            print("\n🐟 ASCII Fish Aquarium 🐟")
            print(render_ocean(ocean))
            print("\nPress Ctrl+C to exit")

            frame += 1
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\033[?25h", end="")  # Show cursor
        print("\n\nThanks for watching the fish! 🐠")


def simple_fish_animation():
    """Simple single fish swimming animation."""
    fish_frames = [
        "  ><>",
        "  ><))°>",
        "  ><)))°>",
        "  ><))°>",
    ]

    width, _ = get_terminal_size()
    width = min(width - 20, 80)

    print("\033[?25l", end="")  # Hide cursor

    try:
        position = 0
        frame = 0
        direction = 1

        while True:
            fish = fish_frames[frame % len(fish_frames)]

            # Create the swimming line
            padding = " " * position
            line = padding + fish

            # Clear line and print
            print(f"\r{' ' * (width + 15)}", end="")
            print(f"\r{line}", end="", flush=True)

            # Move fish
            position += direction

            # Bounce at edges
            if position >= width:
                direction = -1
                fish_frames = [
                    "  <><",
                    "  <°))><",
                    "  <°)))><",
                    "  <°))><",
                ]
            elif position <= 0:
                direction = 1
                fish_frames = [
                    "  ><>",
                    "  ><))°>",
                    "  ><)))°>",
                    "  ><))°>",
                ]

            frame += 1
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\033[?25h")  # Show cursor
        print("\n\nBye bye fish! 🐟")


def nemo_animation():
    """Special Nemo fish animation."""
    nemo_frames = [
        [
            "        ,--._",
            "      /`     `.",
            "     /  __   __\\",
            "    |  /  \\ /  \\|",
            "    | |    |    ||",
            "    |  \\__/ \\__/|",
            "     \\   ____   /",
            "      `./    \\.'",
            "        `----'",
        ],
        [
            "        ,--._",
            "      /`  _  `.",
            "     /  .' '.  \\",
            "    |  | o o |  |",
            "    |  |     |  |",
            "    |  '. .' '  |",
            "     \\   `-'   /",
            "      `.     .'",
            "        `---'",
        ],
    ]

    print("\033[?25l", end="")  # Hide cursor

    try:
        frame = 0
        while True:
            clear_screen()
            print("\n🐠 Finding Nemo... 🐠\n")

            for line in nemo_frames[frame % 2]:
                print("    " + line)

            print("\n    Just keep swimming! 🌊")
            print("\n    Press Ctrl+C to exit")

            frame += 1
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\033[?25h")  # Show cursor
        print("\n\n    Found him! 🐟")


def school_of_fish():
    """A school of fish swimming together."""
    print("\033[?25l", end="")  # Hide cursor

    width, _ = get_terminal_size()
    width = min(width - 30, 100)

    school = [
        "    ><>",
        "  ><>    ><>",
        "    ><>      ><>",
        "  ><>    ><>",
        "    ><>",
    ]

    try:
        position = 0
        while True:
            clear_screen()
            print("\n🐟 School of Fish 🐟\n")
            print("~" * (width + 30))

            for line in school:
                padding = " " * position
                print(padding + line)

            print("." * (width + 30))
            print("\nPress Ctrl+C to exit")

            position += 1
            if position > width:
                position = 0

            time.sleep(0.15)

    except KeyboardInterrupt:
        print("\033[?25h")  # Show cursor
        print("\n\nThe school swam away! 🐠")


def main():
    """Main entry point with menu."""
    while True:
        clear_screen()
        print("""
╔═══════════════════════════════════════╗
║     🐟 ASCII Fish Animation 🐟        ║
╠═══════════════════════════════════════╣
║                                       ║
║   1. Full Aquarium (recommended)      ║
║   2. Simple Swimming Fish             ║
║   3. School of Fish                   ║
║   4. Nemo Animation                   ║
║   5. Exit                             ║
║                                       ║
╚═══════════════════════════════════════╝

        ><((°>   <°))><   ><((°>
        """)

        choice = input("Choose an animation (1-5): ").strip()

        if choice == '1':
            swimming_fish_animation()
        elif choice == '2':
            simple_fish_animation()
        elif choice == '3':
            school_of_fish()
        elif choice == '4':
            nemo_animation()
        elif choice == '5':
            print("\n🐠 Goodbye! Thanks for watching the fish! 🐟\n")
            break
        else:
            print("Invalid choice. Please try again.")
            time.sleep(1)


if __name__ == "__main__":
    main()
