/*
 * xcolor.h -- optional color layer for Foundation TerminalOS's rogue5.4.
 *
 * NOT upstream. Dropped into src/ and wired in by the vendor patch set
 * (vendor/rogue5.4/patches/) at ISO build time, so the vendored src/ tree
 * stays verbatim (docs/FEEDBACK-FIRST-HARDWARE-RUN.md item 2). This gives the
 * 1985 build its classic PC-Rogue color rendition -- matching the real game
 * and keeping it visually distinct from the deliberately-monochrome 1981
 * vintage (the operator's "there are two of the 1981 games" report).
 *
 * Mechanism: rogue.h includes this header after extern.h, so every translation
 * unit sees the wrapped character-plotting primitives below. Each map/creature
 * cell drawn with addch/mvaddch/waddch/mvwaddch is OR'd with a color pair
 * chosen from its symbol. Color lives only in the attribute bits; the game
 * reads the map back with CCHAR() (cell & A_CHARTEXT), which masks those bits
 * off, so coloring is purely cosmetic and cannot perturb game logic.
 */
#ifndef ROGUE_XCOLOR_H
#define ROGUE_XCOLOR_H

#include <curses.h>

void   roguecolor_start(void);    /* start_color + init_pair; once, after initscr */
chtype roguecolor(chtype cell);   /* color attribute for a drawn cell, or 0 */

/*
 * Wrap the four character-plotting primitives Rogue uses to paint the map and
 * its creatures. Statement expressions (a GNU extension; the build runs
 * -std=gnu17) evaluate each argument exactly once, so the side-effecting forms
 * -- e.g. waddch(w, mvwinch(...)) in things.c -- stay correct.
 *
 * The bare function names inside the macros are the real libncurses functions:
 * ncurses' own same-named convenience macros are #undef'd first, and the C
 * preprocessor never re-expands a macro inside its own expansion (so `addch`
 * within the addch macro resolves to the library function, not back to us).
 */
#undef addch
#undef mvaddch
#undef waddch
#undef mvwaddch

#define addch(c) \
    ({ chtype _rc = (chtype)(c); (addch)(_rc | roguecolor(_rc)); })
#define mvaddch(y, x, c) \
    ({ chtype _rc = (chtype)(c); (mvaddch)((y), (x), _rc | roguecolor(_rc)); })
#define waddch(w, c) \
    ({ chtype _rc = (chtype)(c); (waddch)((w), _rc | roguecolor(_rc)); })
#define mvwaddch(w, y, x, c) \
    ({ chtype _rc = (chtype)(c); (mvwaddch)((w), (y), (x), _rc | roguecolor(_rc)); })

#endif /* ROGUE_XCOLOR_H */
