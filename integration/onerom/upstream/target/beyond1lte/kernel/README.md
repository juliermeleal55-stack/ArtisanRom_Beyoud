# S10 Kernel: OneKernel 9.0

## Overview

OneROM Delta 9.0 packages **OneKernel 9.0** for the Samsung Galaxy S10 LTE (`beyond1lte`, Exynos 9820).

- **Kernel Name**: OneKernel 9.0
- **Base**: ExtremeKRNL 2.6.5 by Creeeeger
- **Upstream Repository**: [https://github.com/Creeeeger/9820_kernel](https://github.com/Creeeeger/9820_kernel)
- **Linux Base**: 4.14.356 (openela-rc1)
- **Features**:
  - Exynos 9820 CPU overclock up to 3.04 GHz
  - GPU frequency optimizations
  - Integrated KernelSU Next (v3.2.0)
  - Full compatibility with One UI 9 / Android 17 on Exynos 9820

Because Creeeeger's ExtremeKRNL 2.6.5 base runs One UI 9 / Android 17 directly without modifications, no separate kernel source fork was required. Users and contributors are directed to [Creeeeger's kernel repository](https://github.com/Creeeeger/9820_kernel) for source code and build instructions.

## Bundled Kernel Binaries

The repository provides the validated kernel binaries:
- `boot.img`
- `dtb.img`
- `dtbo.img`

Verified checksums are tracked in `SHA256SUMS`.
