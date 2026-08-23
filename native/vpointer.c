/*
 * vpointer - inject pointer events into a wlroots-based compositor
 * (Hyprland) via zwlr_virtual_pointer_unstable_v1.
 *
 * Exists because ydotool is not installed and /dev/uinput is root-only on
 * this box, so evdev-based injection is unavailable without sudo.
 *
 * Reads a tiny command script from stdin, one command per line:
 *
 *   move   <x> <y>          absolute motion, layout coords (see -W/-H)
 *   down   <button>         press   (left|middle|right or a raw evdev code)
 *   up     <button>         release
 *   click  <button>         down+up with a short gap
 *   scroll <ticks>          vertical wheel, negative = up
 *   sleep  <ms>
 *
 * Every pointer command is followed by a frame() so the compositor commits it.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <wayland-client.h>
#include "wlr-virtual-pointer-unstable-v1-client-protocol.h"

#define BTN_LEFT 0x110
#define BTN_RIGHT 0x111
#define BTN_MIDDLE 0x112

static struct wl_seat *seat = NULL;
static struct zwlr_virtual_pointer_manager_v1 *mgr = NULL;
static struct zwlr_virtual_pointer_v1 *ptr = NULL;
static uint32_t extent_w = 0, extent_h = 0;

static uint32_t now_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint32_t)(ts.tv_sec * 1000 + ts.tv_nsec / 1000000);
}

static void msleep(long ms) {
    struct timespec ts = {ms / 1000, (ms % 1000) * 1000000L};
    nanosleep(&ts, NULL);
}

static void reg_global(void *data, struct wl_registry *reg, uint32_t name,
                       const char *iface, uint32_t version) {
    (void)data; (void)version;
    if (!strcmp(iface, wl_seat_interface.name))
        seat = wl_registry_bind(reg, name, &wl_seat_interface, 1);
    else if (!strcmp(iface, zwlr_virtual_pointer_manager_v1_interface.name))
        mgr = wl_registry_bind(reg, name, &zwlr_virtual_pointer_manager_v1_interface, 1);
}
static void reg_remove(void *d, struct wl_registry *r, uint32_t n) { (void)d;(void)r;(void)n; }
static const struct wl_registry_listener reg_listener = { reg_global, reg_remove };

static int button_code(const char *s) {
    if (!strcmp(s, "left")) return BTN_LEFT;
    if (!strcmp(s, "right")) return BTN_RIGHT;
    if (!strcmp(s, "middle")) return BTN_MIDDLE;
    return atoi(s);
}

static void do_move(double x, double y) {
    zwlr_virtual_pointer_v1_motion_absolute(ptr, now_ms(), (uint32_t)x, (uint32_t)y,
                                            extent_w, extent_h);
    zwlr_virtual_pointer_v1_frame(ptr);
}

static void do_button(int code, int state) {
    zwlr_virtual_pointer_v1_button(ptr, now_ms(), code, state);
    zwlr_virtual_pointer_v1_frame(ptr);
}

static void do_scroll(double ticks) {
    /* wl_pointer axis value is in surface-local "scroll units"; 15 per notch */
    zwlr_virtual_pointer_v1_axis_source(ptr, 0 /* wheel */);
    zwlr_virtual_pointer_v1_axis_discrete(ptr, now_ms(), 0 /* vertical */,
                                          wl_fixed_from_double(ticks * 15.0),
                                          (int32_t)ticks);
    zwlr_virtual_pointer_v1_frame(ptr);
    zwlr_virtual_pointer_v1_axis_stop(ptr, now_ms(), 0);
    zwlr_virtual_pointer_v1_frame(ptr);
}

int main(int argc, char **argv) {
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "-W") && i + 1 < argc) extent_w = atoi(argv[++i]);
        else if (!strcmp(argv[i], "-H") && i + 1 < argc) extent_h = atoi(argv[++i]);
    }
    if (!extent_w || !extent_h) {
        fprintf(stderr, "usage: vpointer -W <layout_w> -H <layout_h>  (script on stdin)\n");
        return 2;
    }

    struct wl_display *dpy = wl_display_connect(NULL);
    if (!dpy) { fprintf(stderr, "vpointer: cannot connect to wayland display\n"); return 1; }
    struct wl_registry *reg = wl_display_get_registry(dpy);
    wl_registry_add_listener(reg, &reg_listener, NULL);
    wl_display_roundtrip(dpy);
    if (!mgr) {
        fprintf(stderr, "vpointer: compositor lacks zwlr_virtual_pointer_manager_v1\n");
        return 1;
    }
    ptr = zwlr_virtual_pointer_manager_v1_create_virtual_pointer(mgr, seat);
    wl_display_roundtrip(dpy);

    char line[512];
    while (fgets(line, sizeof line, stdin)) {
        char cmd[64] = {0}, a[64] = {0}, b[64] = {0};
        int n = sscanf(line, "%63s %63s %63s", cmd, a, b);
        if (n < 1 || cmd[0] == '#') continue;
        if (!strcmp(cmd, "move") && n >= 3) {
            do_move(atof(a), atof(b));
        } else if (!strcmp(cmd, "down") && n >= 2) {
            do_button(button_code(a), 1);
        } else if (!strcmp(cmd, "up") && n >= 2) {
            do_button(button_code(a), 0);
        } else if (!strcmp(cmd, "click") && n >= 2) {
            int c = button_code(a);
            do_button(c, 1);
            wl_display_flush(dpy); msleep(40);
            do_button(c, 0);
        } else if (!strcmp(cmd, "scroll") && n >= 2) {
            do_scroll(atof(a));
        } else if (!strcmp(cmd, "sleep") && n >= 2) {
            wl_display_flush(dpy);
            msleep(atol(a));
            continue;
        } else {
            fprintf(stderr, "vpointer: bad command: %s", line);
            continue;
        }
        wl_display_flush(dpy);
        msleep(8);
    }
    wl_display_flush(dpy);
    wl_display_roundtrip(dpy);
    zwlr_virtual_pointer_v1_destroy(ptr);
    wl_display_disconnect(dpy);
    return 0;
}
