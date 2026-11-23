"""The driver-namespace KGSL ioctl shim: adds KGSL_CONTEXT_PWR_CONSTRAINT on
/dev/kgsl-3d* DRAWCTXT_CREATE calls so KGSL_PROP_PWR_CONSTRAINT takes effect on
host-DCVS Adreno kernels, with fallback on -EINVAL and opt-out via
DM_VK_GPU_FLOOR_KGSL=0."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'android/host/adreno_kgsl_compat.c'


@unittest.skipUnless(shutil.which('clang'), 'no clang')
class KgslCompat(unittest.TestCase):
    def test_drawctxt_flag_and_fallbacks(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'test.c'
            src.write_text(r'''
#include <assert.h>
#include <errno.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/syscall.h>
#include <unistd.h>

static const char *mock_link = "/dev/kgsl-3d0";
static int mock_calls;
static unsigned int mock_seen_flags[4];
static unsigned long mock_seen_req;
static int mock_fail_einval_once;
static int mock_fail_eperm;

static ssize_t probe_readlink(const char *path, char *buf, size_t bufsiz) {
    (void)path;
    if (!mock_link) { errno = ENOENT; return -1; }
    size_t n = strlen(mock_link);
    if (n > bufsiz) n = bufsiz;
    memcpy(buf, mock_link, n);
    return (ssize_t)n;
}

static long probe_syscall(long number, ...) {
    assert(number == SYS_ioctl);
    va_list ap;
    va_start(ap, number);
    int fd = va_arg(ap, int);
    unsigned long req = va_arg(ap, unsigned long);
    unsigned long arg = va_arg(ap, unsigned long);
    va_end(ap);
    (void)fd;
    mock_seen_req = req;
    if (req == 0xc0080913u && arg != 0) {
        struct { unsigned int flags; unsigned int id; } *p = (void *)(uintptr_t)arg;
        if (mock_calls < 4) mock_seen_flags[mock_calls] = p->flags;
        mock_calls++;
        if (mock_fail_einval_once && (p->flags & 0x800u)) {
            mock_fail_einval_once = 0;
            errno = EINVAL;
            return -1;
        }
        if (mock_fail_eperm) {
            errno = EPERM;
            return -1;
        }
        p->flags |= 0x8000u;
        p->id = 42u;
        return 0;
    }
    mock_calls++;
    return 0;
}

#define readlink probe_readlink
#define syscall probe_syscall
#define ioctl probe_ioctl
''' + '#include "' + str(SOURCE) + '"\n' + r'''
#undef ioctl
#undef syscall
#undef readlink

int main(void) {
    assert((uint32_t)KGSL_IOCTL_DRAWCTXT_CREATE == 0xc0080913u);

    // 1. KGSL fd without KGSL_CONTEXT_PWR_CONSTRAINT: flag is added and _IOWR outputs copied back.
    unsetenv("DM_VK_GPU_FLOOR_KGSL");
    mock_link = "/dev/kgsl-3d0";
    mock_calls = 0;
    struct kgsl_drawctxt_create_compat c = { .flags = 0x13u, .drawctxt_id = 0 };
    assert(probe_ioctl(7, KGSL_IOCTL_DRAWCTXT_CREATE, &c) == 0);
    assert(mock_calls == 1);
    assert(mock_seen_flags[0] == (0x13u | 0x800u));
    assert(c.drawctxt_id == 42u);
    assert(c.flags == (0x13u | 0x800u | 0x8000u));

    // 2. Already-flagged context: forwarded directly.
    mock_calls = 0;
    c = (struct kgsl_drawctxt_create_compat){ .flags = 0x813u, .drawctxt_id = 0 };
    assert(probe_ioctl(7, KGSL_IOCTL_DRAWCTXT_CREATE, &c) == 0);
    assert(mock_calls == 1 && mock_seen_flags[0] == 0x813u && c.drawctxt_id == 42u);

    // 3. Non-KGSL fd: flags untouched.
    mock_link = "/dev/null";
    mock_calls = 0;
    c = (struct kgsl_drawctxt_create_compat){ .flags = 0x13u, .drawctxt_id = 0 };
    assert(probe_ioctl(7, KGSL_IOCTL_DRAWCTXT_CREATE, &c) == 0);
    assert(mock_calls == 1 && mock_seen_flags[0] == 0x13u);

    // 4. DM_VK_GPU_FLOOR_KGSL=0: flags untouched even on KGSL fd.
    mock_link = "/dev/kgsl-3d0";
    setenv("DM_VK_GPU_FLOOR_KGSL", "0", 1);
    mock_calls = 0;
    c = (struct kgsl_drawctxt_create_compat){ .flags = 0x13u, .drawctxt_id = 0 };
    assert(probe_ioctl(7, KGSL_IOCTL_DRAWCTXT_CREATE, &c) == 0);
    assert(mock_calls == 1 && mock_seen_flags[0] == 0x13u);

    // 5. Kernel -EINVAL fallback: retries with original flags and succeeds.
    unsetenv("DM_VK_GPU_FLOOR_KGSL");
    mock_fail_einval_once = 1;
    mock_calls = 0;
    c = (struct kgsl_drawctxt_create_compat){ .flags = 0x13u, .drawctxt_id = 0 };
    assert(probe_ioctl(7, KGSL_IOCTL_DRAWCTXT_CREATE, &c) == 0);
    assert(mock_calls == 2);
    assert(mock_seen_flags[0] == (0x13u | 0x800u));
    assert(mock_seen_flags[1] == 0x13u);
    assert(c.drawctxt_id == 42u);

    // 6. Non-EINVAL error: returned immediately without retry.
    mock_fail_eperm = 1;
    mock_calls = 0;
    c = (struct kgsl_drawctxt_create_compat){ .flags = 0x13u, .drawctxt_id = 0 };
    assert(probe_ioctl(7, KGSL_IOCTL_DRAWCTXT_CREATE, &c) == -1 && errno == EPERM);
    assert(mock_calls == 1);
    mock_fail_eperm = 0;

    // 7. Unrelated ioctl passes straight through.
    mock_calls = 0;
    assert(probe_ioctl(7, 0x12345678u, 0) == 0);
    assert(mock_calls == 1 && mock_seen_req == 0x12345678u);
    return 0;
}
''')
            exe = Path(tmp) / 'test'
            subprocess.run(['clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-Wno-deprecated-declarations', str(src), '-o', str(exe)],
                           check=True, capture_output=True, text=True)
            subprocess.run([str(exe)], check=True, capture_output=True, text=True)


if __name__ == '__main__':
    unittest.main()
