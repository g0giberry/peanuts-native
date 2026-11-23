// Mesa Turnip (tu_knl_kgsl.cc) creates KGSL draw contexts without
// KGSL_CONTEXT_PWR_CONSTRAINT (0x00000800). On host-DCVS Adreno kernels (where
// GMU does not own DCVS), IOCTL_KGSL_SETPROPERTY KGSL_PROP_PWR_CONSTRAINT
// succeeds (returns 0) but the dispatcher ignores the constraint unless the
// context (or cmdbatch) carries KGSL_CONTEXT_PWR_CONSTRAINT.
//
// libadrenotools preloads libhook_impl.so with DF_1_GLOBAL (-Wl,-z,global) into
// each custom driver's linker namespace before loading the vendor driver.
// Exporting ioctl() here intercepts only the custom driver's calls, without
// touching dm/third_party/ or the system driver path.
#ifdef __ANDROID__
#include <android/log.h>
#endif
#include <errno.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/syscall.h>
#include <unistd.h>

#define KGSL_IOC_TYPE 0x09
#define KGSL_CONTEXT_PWR_CONSTRAINT 0x00000800u

struct kgsl_drawctxt_create_compat {
    unsigned int flags;
    unsigned int drawctxt_id;
};

#define KGSL_IOCTL_DRAWCTXT_CREATE _IOWR(KGSL_IOC_TYPE, 0x13, struct kgsl_drawctxt_create_compat)

static int is_kgsl_fd(int fd) {
    char proc_path[48];
    char target[64];
    snprintf(proc_path, sizeof proc_path, "/proc/self/fd/%d", fd);
    ssize_t n = readlink(proc_path, target, sizeof target - 1);
    if (n <= 0) return 0;
    target[n] = '\0';
    return strncmp(target, "/dev/kgsl-3d", 12) == 0;
}

static int kgsl_floor_enabled(void) {
    const char *e = getenv("DM_VK_GPU_FLOOR_KGSL");
    return !e || !*e || atoi(e) != 0;
}

__attribute__((visibility("default")))
#ifdef __ANDROID__
int ioctl(int fd, int op, ...) {
#else
int ioctl(int fd, unsigned long op, ...) {
#endif
    va_list ap;
    va_start(ap, op);
    unsigned long arg = va_arg(ap, unsigned long);
    va_end(ap);

    uint32_t req = (uint32_t)op;
    if (req == (uint32_t)KGSL_IOCTL_DRAWCTXT_CREATE && arg != 0 && kgsl_floor_enabled() && is_kgsl_fd(fd)) {
        struct kgsl_drawctxt_create_compat *orig = (struct kgsl_drawctxt_create_compat *)(uintptr_t)arg;
        if (!(orig->flags & KGSL_CONTEXT_PWR_CONSTRAINT)) {
            unsigned int orig_flags = orig->flags;
            struct kgsl_drawctxt_create_compat copy = *orig;
            copy.flags |= KGSL_CONTEXT_PWR_CONSTRAINT;
            int r = (int)syscall(SYS_ioctl, fd, (unsigned long)req, &copy);
            if (r == 0) {
                *orig = copy;
#ifdef __ANDROID__
                __android_log_print(ANDROID_LOG_INFO, "hook_impl",
                                    "KGSL drawctxt %u: added KGSL_CONTEXT_PWR_CONSTRAINT (flags 0x%x -> 0x%x)",
                                    copy.drawctxt_id, orig_flags, copy.flags);
#else
                (void)orig_flags;
#endif
                return 0;
            }
            if (errno != EINVAL) return r;
            // Fallback to original flags if the kernel rejects KGSL_CONTEXT_PWR_CONSTRAINT.
        }
    }
    return (int)syscall(SYS_ioctl, fd, (unsigned long)req, arg);
}
