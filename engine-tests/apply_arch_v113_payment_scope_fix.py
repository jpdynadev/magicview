#!/usr/bin/env python3
"""Apply the v1.13 scope fix to the narrow v1.12 Kinnan payment repair.

The v1.12 canonical replay proved the payment-progress branch was being reached,
but its color-priority scorer referenced an undefined local/global name `policy`.
That raised NameError during payManaCost and converted an otherwise progressing
game into unsupported_prompt / ENGINE_ERROR.

v1.13 changes no Forge legality and no payment strategy. It only binds that
existing helper call to the policy module already imported by the runner as
`runner.policy`, then bumps the pilot identity so v1.12 evidence/cache cannot be
mistaken for compatible confirmation data.
"""
from pathlib import Path

P = Path(__file__).resolve().parent / 'manabrew_pilot_arch_adv.py'
text = P.read_text()

if "arch-aware-v1.13-adversarial" in text and "runner.policy.required_payment_colors(inp)" in text:
    print('v1.13 payment scope fix already applied')
    raise SystemExit(0)

old_version = "runner.PILOT_VERSION = 'arch-aware-v1.12-adversarial'"
if old_version not in text:
    raise SystemExit('expected v1.12 pilot identity not found; apply v1.12 first')
text = text.replace(old_version, "runner.PILOT_VERSION = 'arch-aware-v1.13-adversarial'", 1)

old_call = "required = set(policy.required_payment_colors(inp))"
new_call = "required = set(runner.policy.required_payment_colors(inp))"
if old_call not in text:
    raise SystemExit('expected v1.12 undefined policy call not found')
text = text.replace(old_call, new_call, 1)

P.write_text(text)
print('applied arch-aware-v1.13-adversarial payment scope fix')
