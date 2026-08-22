#!/usr/bin/env python3
import manabrew_pilot_v89
import manabrew_pilot_v8 as runner
runner.PILOT_VERSION='tutor-sweep-v1'
runner.VARIANT_FILES['T2']='Kinnan_TUTOR_T2.dck'
runner.VARIANT_FILES['T4']='Kinnan_TUTOR_T4.dck'
runner.VARIANT_FILES['T6']='Kinnan_TUTOR_T6.dck'
if __name__=='__main__': raise SystemExit(runner.main())
