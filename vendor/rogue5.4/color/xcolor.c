/*
 * xcolor.c -- classic PC-Rogue color mapping for Foundation TerminalOS's
 * rogue5.4. See xcolor.h for the how/why. NOT upstream; added by the vendor
 * patch set at ISO build time.
 */
#include <curses.h>
#include "xcolor.h"

/*
 * Color-pair ids, initialised in roguecolor_start(). Pair 0 is the terminal
 * default and is what unmapped cells (spaces, digits, status text) keep.
 */
enum {
    CP_FLOOR = 1, CP_WALL, CP_PASSAGE, CP_DOOR, CP_PLAYER, CP_STAIRS,
    CP_TRAP, CP_GOLD, CP_POTION, CP_SCROLL, CP_FOOD, CP_WEAPON, CP_ARMOR,
    CP_MAGIC, CP_MONSTER
};

void
roguecolor_start(void)
{
    if (!has_colors())
        return;
    start_color();
    /*
     * Classic PC-Rogue palette, approximated on the kernel VT's 8 base colors.
     * foundationhub-session restores the VT's stock palette while a full_color
     * game runs (see hub theme.vt_stock_palette), so these land on true hues
     * instead of the phosphor amber the Hub otherwise tunes the console to.
     */
    init_pair(CP_FLOOR,   COLOR_GREEN,   COLOR_BLACK);
    init_pair(CP_WALL,    COLOR_YELLOW,  COLOR_BLACK);
    init_pair(CP_PASSAGE, COLOR_YELLOW,  COLOR_BLACK);
    init_pair(CP_DOOR,    COLOR_YELLOW,  COLOR_BLACK);
    init_pair(CP_PLAYER,  COLOR_WHITE,   COLOR_BLACK);
    init_pair(CP_STAIRS,  COLOR_CYAN,    COLOR_BLACK);
    init_pair(CP_TRAP,    COLOR_RED,     COLOR_BLACK);
    init_pair(CP_GOLD,    COLOR_YELLOW,  COLOR_BLACK);
    init_pair(CP_POTION,  COLOR_CYAN,    COLOR_BLACK);
    init_pair(CP_SCROLL,  COLOR_WHITE,   COLOR_BLACK);
    init_pair(CP_FOOD,    COLOR_RED,     COLOR_BLACK);
    init_pair(CP_WEAPON,  COLOR_CYAN,    COLOR_BLACK);
    init_pair(CP_ARMOR,   COLOR_CYAN,    COLOR_BLACK);
    init_pair(CP_MAGIC,   COLOR_MAGENTA, COLOR_BLACK);
    init_pair(CP_MONSTER, COLOR_RED,     COLOR_BLACK);
}

chtype
roguecolor(chtype cell)
{
    int ch = (int)(cell & A_CHARTEXT);

    switch (ch) {
        case '.': return COLOR_PAIR(CP_FLOOR);
        case '|':
        case '-': return COLOR_PAIR(CP_WALL);
        case '#': return COLOR_PAIR(CP_PASSAGE);
        case '+': return COLOR_PAIR(CP_DOOR);
        case '@': return COLOR_PAIR(CP_PLAYER) | A_BOLD;
        case '%': return COLOR_PAIR(CP_STAIRS);
        case '^': return COLOR_PAIR(CP_TRAP);
        case '*': return COLOR_PAIR(CP_GOLD)   | A_BOLD;
        case '!': return COLOR_PAIR(CP_POTION);
        case '?': return COLOR_PAIR(CP_SCROLL);
        case ':': return COLOR_PAIR(CP_FOOD);
        case ')': return COLOR_PAIR(CP_WEAPON);
        case ']': return COLOR_PAIR(CP_ARMOR);
        case '$': return COLOR_PAIR(CP_MAGIC);
        case '/': return COLOR_PAIR(CP_WEAPON);   /* wands / staves */
        case '=': return COLOR_PAIR(CP_GOLD);     /* rings */
        case ',': return COLOR_PAIR(CP_GOLD);     /* the amulet */
        default:
            if (ch >= 'A' && ch <= 'Z')           /* monsters are A-Z */
                return COLOR_PAIR(CP_MONSTER) | A_BOLD;
            return 0;   /* spaces, digits, punctuation, status text: default */
    }
}
