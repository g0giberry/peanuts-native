# DOOM (`0100416004C00000`)

<!-- PEANUTS: a Peanuts Native profile and note (Banana Native has none for this title). -->

Update 1.4.1 (`v327680`), SDK 6.4.0, NVN 53.313. id Tech 6 engine with Wwise audio and Bink (`.bik`/`.bk2`) videos. Modules: `main`, `sdk`, `rtld`, 0-byte `subsdk0`.

**Status (current): boots and plays on Android (both Turnip and Qualcomm's system driver).** Reaches *The UAC* opening 3D level at ~30 fps on an AYN Odin 3 (Adreno 830) with 0 skipped draws and 0 missing shaders.

## Builds

| Version | Module | Build ID |
|---|---|---|
| 1.4.1 (v327680) | `main` | `c638a0730217792b1ceaecf0d635f410` |
| 1.4.1 (v327680) | `sdk` | `e29be8ad6778527aa248310d0c71a8a5` |

## What it needs

| Setting | Where | Why |
|---|---|---|
| `mem_reserve 0x100000000`, `mem_alias 0x10000000`, `mem_stack 0x10000000`, `mem_used 0x5800000`, `app_pool 0xCD500000` | `game.tsv` | `main` sets a heap up to pool minus 64 MB minus 42 MB bss |
| `sys_resource 0x0` | `game.tsv` | NPDM declares no system resource |
| `place_join_mb 1024` | `game.tsv` | Coalesce placed memory allocations into 1 GiB regions |
| `modules main sdk` | `game.tsv` | Active guest modules |

No game-specific rewriter patches are needed.

## Files and shaders

- Shaders live in `base/gameresources_003.patch` (`\x05SER` `.index`/`.pindex` + `.patch` `.sb` GLSLC outputs), extracted by `dm/gfx/tools/shader_split.py`.
- 863 shaders: 262 vertex, 560 pixel, 6 geometry, 35 compute; 584 variation pairs; 35 compute answers (`1,189` SPIR-V modules in `dmsh_vk.lib`).

## Frame rate

- **Odin 3 (Adreno 830), *The UAC* opening level (20 s roaming + combat):**
  - **Qualcomm system driver (`driverID` 8, `[auto] DM_VK_LRZ_TOUCH=1`):** 29.6 fps, 880 draws (0 skipped), 16 dispatches, 316 render passes, recording 21.12 ms, GPU 20.25 ms, 0 missing shaders.
  - **Turnip (`driverID` 18):** 30.0 fps, 894 draws (0 skipped), 16 dispatches, 314 render passes, recording 14.28 ms, GPU 14.88 ms, 0 missing shaders.
  - **Turnip (`Turnip_v27.0.0-R3`), 60 fps (`fpslocker` rows):** 59.6–60.0 fps in gameplay (60.7 fps after `R.dread` pass-merge fix: Turnip indoors `89` passes, GPU p50/p90 `11.5/12.5 ms`, CPU recording `2.3–2.5 ms` down from `306` passes / `13.1/14.1 ms` GPU / `3.4–3.5 ms` CPU; Turnip Mars outdoors `62` passes for `1,098` draws, GPU p50/p90 `13.2/13.4 ms`; Qualcomm system driver Mars outdoors `467 → 63` passes, `40.4 → 60.7 fps`, GPU `18.8/19.0 → 15.7/16.9 ms`, CPU recording `24.4 → 11.0 ms`; `uac.nvncap` `nxreplay` Qualcomm `89` passes, `14.56 ms` GPU). `30 fps` is the default (`fps_limit 30`), while `20–60 fps` and `Game owned` are unlocked via `fpslocker` memory rows (adapted from [masagrator's FPSLocker Warehouse config](https://github.com/masagrator/FPSLocker-Warehouse/blob/v4/SaltySD/plugins/FPSLocker/patches/0100416004C00000/C638A0730217792B.yaml) with every BSS offset verified in `main`'s `.rela.dyn`): `com_adaptiveTick=1` (`@0x66b1560`), `com_adaptiveTickMinHz=15` (`@0x66b3eb8`), `com_adaptiveTickMaxHz` (`@0x66b3f50`/`+4`), dynamic resolution budgets `rs_raiseMilliseconds` (`@0x593e9ec`, `0.966×`) and `rs_dropMilliseconds` (`@0x593e954`, `0.99×`), and `flag_cap_u8` at `@0x7377d64` (`0:30`) so fixed-speed scripted scenes (cutscenes, imp deaths, Praetor suit, Bink intro) automatically lock back to 30 fps while normal gameplay runs at up to 60 fps with live switching between numeric caps and no code patches.

## Found on this game

- [Simultaneous depth-read and depth-write draws splitting Pre-Z into 1-draw passes (Android)](../../../docs/reference/rendering.md#simultaneous-depth-read-and-depth-write-draws-splitting-pre-z-into-1-draw-passes-android): Pre-Z geometry shaders (`38d8127afde928b3`, `ffdce93f088cbe5c`, `e174c6bd26026776`) sample the active `1280x720` depth buffer while writing depth, previously triggering `R.dread` pass splits after every draw (`306 → 62–89` passes on Turnip, `467 → 63` passes / `40.4 → 60.7 fps` on Qualcomm).

- [Cross-format in-place compute storage image aliasing (Android)](../../../docs/reference/rendering.md#cross-format-in-place-compute-storage-image-aliasing-android): `computedeferredcomposite_cs` (`7376789d2f755269`) reads `serial 2` (`B10G11R11`) via `R32_UINT` (`binding 7`) while writing `serial 2` via `B10G11R11` (`binding 8`), causing `8x4` wave/tile corruption (`65024` white/green bloom flashes) on Adreno until reading from a cached copy.

- [Packed 32-bit float formats bound as integer storage images](../../../docs/reference/rendering.md#packed-32-bit-float-formats-bound-as-integer-storage-images): `computedeferredcomposite_cs` reads the `1280x720` `VK_FORMAT_B10G11R11_UFLOAT_PACK32` HDR target through an `R32_UINT` storage image view; without a `class_twin` mapping, binding 7 was left unbound and the 3D scene rendered too dark on both drivers.
- [Primitive restart enabled on non-strip and non-fan topologies](../../../docs/reference/rendering.md#primitive-restart-enabled-on-non-strip-and-non-fan-topologies): id Tech 6 leaves NVN primitive restart index `0xffff` set across `TRIANGLE_LIST` draws.
- [Stale LRZ bins across depth-buffer switches on Qualcomm's driver (Android)](../../../docs/reference/rendering.md#stale-lrz-bins-across-depth-buffer-switches-on-qualcomms-driver-android): caused 8x8 / 8x4 blocky artifacts across world geometry and weapon on Qualcomm's system driver until `DM_VK_LRZ_TOUCH=1` was enabled by default for `driverID` 8.
- [Single-lane subgroup rewrite leaving subgroup capabilities on geometry stages](../../../docs/reference/shaders.md#single-lane-subgroup-rewrite-leaving-subgroup-capabilities-on-geometry-stages): caused Qualcomm Pre-Z geometry-shader indirect draws to produce `0/32` non-zero counts, and GS passthrough linking duplicated existing `Location` inputs.
- [Unfenced nvnSyncWait returning timeout on early spin](../../../docs/reference/nvn-objects.md#unfenced-nvnsyncwait-returning-timeout-on-early-spin): unblocks DOOM's render thread before its first `nvnWindowAcquireTexture`.

## Open

- **Bink intro videos (`Boot_Sequence.bik`):** `ctl-shot` framebuffer capture during playback (`1280x720` Y + `640x360` U/V double-buffered `R8` textures) is tear-free; visual tearing during intro stems from presentation timing while initial loading / background asset streaming triggers heavy write-protection faults (~505k–813k faults during `Boot_Sequence.bik`).
- **Large joystick deadzone feel:** `DM_PAD_DEADZONE=0.1` in `dm/host/android/input_android.c` stacks with DOOM's own large in-game radial deadzone. Setting `DM_PAD_DEADZONE=0` (or `0.02`) avoids double-deadzone on Hall-effect sticks.
