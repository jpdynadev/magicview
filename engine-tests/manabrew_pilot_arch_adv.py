#!/usr/bin/env python3
import manabrew_pilot_v91_adversarial  # install pod-aware opponent policy first
import manabrew_pilot_arch as arch
import manabrew_pilot_v8 as runner

runner.PILOT_VERSION = 'arch-aware-v1-adversarial'

if __name__ == '__main__':
    raise SystemExit(runner.main())
