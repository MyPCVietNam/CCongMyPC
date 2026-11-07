# Freeze vs tip timeline (truthful; immutable pins not rewritten)

## Prior V2 (PID safety — harness unsafe; superseded)

- packaging_freeze=`0ea4264440bf330f005af7447bbd6bdb6cfabb46`
- feature=`ae003b8f703e62144feb1eed77e0462b536d74dd`
- complete_sha256=`58017ee3f09b5e6f21dd6097c390058ff48616cf83cc8b1932e93a32627a0e6a`
- complete_bytes=3873439

## Prior V1 ownership / VT_BSTR (historical)

- packaging_freeze_v1=`59148ebd1d545aa887c4cb4a6288d9c8c394ba1b`
- feature_pid_ownership=`3c989facccc9443c351e0526dc76db7ee2f742a0`
- baseline_vtbstr_freeze=`e18e3e234084bbc752366bbc22b011b416914115`

## This corrective (PID safety V3)

- baseline_pre_fix=`a3b995ef4e78d67830192b22b2b6cc0e69a5beb5` (independent RED 6/6)
- feature_pid_safety_v3=`FEATURE_AT_COMMIT`
- packaging_freeze=`FREEZE_AT_ZIP_COMMIT`
- tip_url_pin=`TIP_AFTER_PUSH`
- baseline_pr26=`146d04cb930a446f891f48178a33672f0537b95e`
- owner_windows_physical=`BLOCKED`
- do_not_start_stop_or_runtime_until_v3_audit=`true`
